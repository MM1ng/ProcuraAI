from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.rag.hybrid_search import filter_products_by_constraints, search_products
from app.rag.knowledge_base import load_procurement_policies, load_supplier_profiles
from app.rag.vector_store import (
    CHROMA_DIR,
    POLICY_COLLECTION,
    PRODUCT_COLLECTION,
    SUPPLIER_COLLECTION,
    load_local_index,
    query_vector_collection,
)
from app.services.product_service import load_products_from_csv
from app.rag.bm25_retriever import get_bm25_retriever


@dataclass
class RetrievalResult:
    products: list[dict[str, Any]]
    evidence: dict[str, Any]


RRF_K = 60


def _query_with_intent(query: str, intent: dict[str, Any]) -> str:
    parts = [query]
    categories = intent.get("categories") or []
    if categories:
        parts.append("categories " + " ".join(str(category) for category in categories))
    if intent.get("replacement_brand"):
        parts.append(f"brand {intent['replacement_brand']}")
    if intent.get("max_delivery_days"):
        parts.append(f"delivery within {intent['max_delivery_days']} days")
    if intent.get("min_rating"):
        parts.append(f"rating above {intent['min_rating']}")
    return " ".join(parts)


def _query_for_category(query: str, intent: dict[str, Any], category: str) -> str:
    scoped_intent = dict(intent)
    scoped_intent["categories"] = [category]
    return _query_with_intent(query, scoped_intent)


def _constraints(intent: dict[str, Any]) -> dict[str, Any]:
    return {
        "categories": intent.get("categories"),
        "brand": None,
        "min_rating": intent.get("min_rating"),
        "min_stock": int(intent.get("people_count") or 1),
        "max_delivery_days": intent.get("max_delivery_days"),
    }


def _vector_product_hits(
    vector_query: str,
    intent: dict[str, Any],
    top_k: int,
    persist_dir: Path | str,
) -> list[dict[str, Any]]:
    categories = [str(category) for category in intent.get("categories") or []]
    if not categories:
        return query_vector_collection(PRODUCT_COLLECTION, vector_query, top_k=top_k, persist_dir=persist_dir)

    by_id: dict[str, dict[str, Any]] = {}
    for category in categories:
        rows = query_vector_collection(
            PRODUCT_COLLECTION,
            f"{vector_query} {category}",
            top_k=top_k,
            persist_dir=persist_dir,
        )
        for row in rows:
            existing = by_id.get(str(row.get("id")))
            if existing is None or float(row.get("score", 0) or 0) > float(existing.get("score", 0) or 0):
                by_id[str(row.get("id"))] = row
    return sorted(by_id.values(), key=lambda row: -float(row.get("score", 0) or 0))


def _product_from_hit(hit: dict[str, Any], reason: str, constraints: dict[str, Any]) -> dict[str, Any]:
    metadata = dict(hit.get("metadata") or {})
    metadata["retrieval_score"] = hit.get("score", 0)
    metadata["retrieval_reason"] = reason
    metadata["matched_fields"] = ["name", "brand", "category", "supplier", "description", "tags"]
    metadata["constraints_applied"] = constraints
    return metadata


def _product_id(value: dict[str, Any]) -> str:
    return str(value.get("product_id") or value.get("id") or "")


def _rrf(rank: int, k: int = RRF_K) -> float:
    return 1.0 / (rank + k)


def _fuse_vector_and_bm25_results(
    vector_hits: list[dict[str, Any]],
    bm25_products: list[dict[str, Any]],
    constraints: dict[str, Any],
) -> list[dict[str, Any]]:
    fused: dict[str, dict[str, Any]] = {}

    for rank, hit in enumerate(vector_hits, start=1):
        product = _product_from_hit(hit, "vector_only", constraints)
        product_id = _product_id(product)
        if not product_id:
            continue
        product["rrf_score"] = _rrf(rank)
        product["retrieval_score"] = product["rrf_score"]
        product["vector_rank"] = rank
        product["bm25_rank"] = None
        product["retrieval_channels"] = ["vector"]
        fused[product_id] = product

    for rank, raw_product in enumerate(bm25_products, start=1):
        product = dict(raw_product)
        product_id = _product_id(product)
        if not product_id:
            continue
        if product_id in fused:
            existing = fused[product_id]
            existing["rrf_score"] = float(existing.get("rrf_score", 0) or 0) + _rrf(rank)
            existing["retrieval_score"] = existing["rrf_score"]
            existing["bm25_rank"] = rank
            existing["bm25_score"] = product.get("bm25_score", existing.get("bm25_score"))
            existing["bm25_matched_terms"] = product.get("bm25_matched_terms", existing.get("bm25_matched_terms", []))
            existing["retrieval_channels"] = ["vector", "bm25"]
            existing["retrieval_reason"] = "hybrid_rrf_vector_bm25"
            continue

        product["rrf_score"] = _rrf(rank)
        product["retrieval_score"] = product["rrf_score"]
        product["retrieval_reason"] = "bm25_only"
        product["matched_fields"] = product.get("bm25_matched_terms", [])
        product["constraints_applied"] = constraints
        product["vector_rank"] = None
        product["bm25_rank"] = rank
        product["retrieval_channels"] = ["bm25"]
        fused[product_id] = product

    return sorted(
        fused.values(),
        key=lambda product: (
            -float(product.get("rrf_score", 0) or 0),
            -float(product.get("rating", 0) or 0),
            int(product.get("delivery_days", 999) or 999),
            float(product.get("price", 999999) or 999999),
        ),
    )


def _product_evidence(products: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "source_id": f"来源{index}",
            "source_index": index,
            "product_id": product.get("product_id"),
            "name": product.get("name"),
            "category": product.get("category"),
            "brand": product.get("brand"),
            "supplier": product.get("supplier"),
            "score": product.get("retrieval_score", 0),
            "rrf_score": product.get("rrf_score"),
            "vector_rank": product.get("vector_rank"),
            "bm25_rank": product.get("bm25_rank"),
            "retrieval_channels": product.get("retrieval_channels", []),
            "reason": product.get("retrieval_reason", ""),
            "matched_fields": product.get("matched_fields", []),
        }
        for index, product in enumerate(products, start=1)
    ]


def _filter_vector_products(
    products: list[dict[str, Any]],
    intent: dict[str, Any],
    constraints: dict[str, Any],
) -> list[dict[str, Any]]:
    replacement_brand = intent.get("replacement_brand")
    replacement_categories = [str(category) for category in intent.get("replacement_categories") or []]
    if intent.get("revision_intent") == "replace_product" and replacement_brand and replacement_categories:
        preserved_categories = [
            str(category)
            for category in intent.get("categories") or []
            if str(category) not in replacement_categories
        ]
        replacement_products = filter_products_by_constraints(
            products,
            categories=replacement_categories,
            brand=str(replacement_brand),
            min_rating=constraints["min_rating"],
            min_stock=constraints["min_stock"],
            max_delivery_days=constraints["max_delivery_days"],
        )
        preserved_products = filter_products_by_constraints(
            products,
            categories=preserved_categories,
            min_rating=constraints["min_rating"],
            min_stock=constraints["min_stock"],
            max_delivery_days=constraints["max_delivery_days"],
        )
        return [*replacement_products, *preserved_products]

    return filter_products_by_constraints(
        products,
        categories=constraints["categories"],
        min_rating=constraints["min_rating"],
        min_stock=constraints["min_stock"],
        max_delivery_days=constraints["max_delivery_days"],
    )


def _sort_products(products: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        products,
        key=lambda product: (
            -float(product.get("rrf_score", product.get("retrieval_score", 0)) or 0),
            -float(product.get("rating", 0) or 0),
            int(product.get("delivery_days", 999) or 999),
            float(product.get("price", 999999) or 999999),
        ),
    )


def _select_with_category_quota(
    products: list[dict[str, Any]],
    categories: list[str],
    top_k: int,
) -> list[dict[str, Any]]:
    if top_k <= 0:
        return []
    ranked = _sort_products(products)
    if len(categories) <= 1:
        return ranked[:top_k]

    selected: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for category in categories:
        for product in ranked:
            product_id = _product_id(product)
            if product_id in seen_ids:
                continue
            if str(product.get("category")) == category:
                selected.append(product)
                seen_ids.add(product_id)
                break
        if len(selected) >= top_k:
            return selected

    for product in ranked:
        product_id = _product_id(product)
        if product_id in seen_ids:
            continue
        selected.append(product)
        seen_ids.add(product_id)
        if len(selected) >= top_k:
            break
    return selected


def _bm25_results(query: str, intent: dict[str, Any], top_k: int) -> list[dict[str, Any]]:
    try:
        bm25 = get_bm25_retriever()
        intent_cats = (intent or {}).get("categories") or []
        if intent_cats:
            return bm25.search_by_categories(query, intent_cats, top_k=top_k)
        return bm25.search_with_synonym_boost(query, intent, top_k=top_k)
    except Exception:
        return []


def _multi_category_vector_hits(
    query: str,
    intent: dict[str, Any],
    categories: list[str],
    top_k: int,
    persist_dir: Path | str,
) -> list[dict[str, Any]]:
    by_id: dict[str, dict[str, Any]] = {}
    per_category_k = max(3, top_k)
    for category in categories:
        rows = query_vector_collection(
            PRODUCT_COLLECTION,
            _query_for_category(query, intent, category),
            top_k=per_category_k,
            persist_dir=persist_dir,
        )
        for rank, row in enumerate(rows, start=1):
            row = dict(row)
            row["category_vector_rank"] = rank
            existing = by_id.get(str(row.get("id")))
            if existing is None or float(row.get("score", 0) or 0) > float(existing.get("score", 0) or 0):
                by_id[str(row.get("id"))] = row
    return sorted(by_id.values(), key=lambda row: -float(row.get("score", 0) or 0))


def _retrieve_multi_category_products(
    query: str,
    intent: dict[str, Any],
    categories: list[str],
    top_k: int,
    persist_dir: Path | str,
    constraints: dict[str, Any],
) -> tuple[list[dict[str, Any]], bool]:
    vector_hits = _multi_category_vector_hits(query, intent, categories, top_k, persist_dir)
    bm25_products = _bm25_results(query, intent, top_k=max(top_k, len(categories) * 2))
    fused = _fuse_vector_and_bm25_results(vector_hits, bm25_products, constraints)
    filtered = _filter_vector_products(fused, intent, constraints)
    constraints_relaxed = False
    if not filtered:
        constraints_relaxed = True
        filtered = fused
        for product in filtered:
            product["retrieval_reason"] = "hybrid_rrf_constraints_relaxed"
    return _select_with_category_quota(filtered, categories, top_k), constraints_relaxed


def _knowledge_evidence(collection: str, query: str, top_k: int, persist_dir: Path | str) -> list[dict[str, Any]]:
    rows = query_vector_collection(collection, query, top_k=top_k, persist_dir=persist_dir)
    evidence: list[dict[str, Any]] = []
    for row in rows:
        metadata = row.get("metadata") or {}
        evidence.append(
            {
                "id": row.get("id"),
                "title": metadata.get("title", metadata.get("supplier", "")),
                "supplier": metadata.get("supplier", ""),
                "category": metadata.get("category", ""),
                "risk_level": metadata.get("risk_level", ""),
                "text": metadata.get("text", row.get("document", "")),
                "score": row.get("score", 0),
            }
        )
    return evidence


def _token_score(query: str, text: str) -> float:
    query_tokens = {token for token in query.lower().replace("_", " ").split() if len(token) > 2}
    text_tokens = {token for token in text.lower().replace("_", " ").split() if len(token) > 2}
    if not query_tokens:
        return 0.01
    overlap = len(query_tokens & text_tokens)
    return round(overlap / len(query_tokens), 6)


def _local_knowledge_evidence(rows: list[dict[str, Any]], query: str, top_k: int) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    for row in rows:
        text = str(row.get("text") or row.get("content") or "")
        evidence.append(
            {
                "id": row.get("id"),
                "title": row.get("title", row.get("supplier", "")),
                "supplier": row.get("supplier", ""),
                "category": row.get("category", ""),
                "risk_level": row.get("risk_level", ""),
                "text": text,
                "score": _token_score(query, f"{row.get('title', '')} {row.get('supplier', '')} {text}"),
            }
        )
    return sorted(evidence, key=lambda item: -float(item.get("score", 0) or 0))[:top_k]


def _knowledge_evidence_with_fallback(collection: str, query: str, top_k: int, persist_dir: Path | str) -> list[dict[str, Any]]:
    vector_rows = _knowledge_evidence(collection, query, top_k, persist_dir)
    if vector_rows:
        return vector_rows
    if collection == POLICY_COLLECTION:
        return _local_knowledge_evidence(load_procurement_policies(), query, top_k)
    if collection == SUPPLIER_COLLECTION:
        return _local_knowledge_evidence(load_supplier_profiles(), query, top_k)
    return []


def _fallback_products(query: str, intent: dict[str, Any], top_k: int) -> list[dict[str, Any]]:
    index = load_local_index()
    products = [row["metadata"] for row in index] if index else load_products_from_csv()
    people_count = int(intent.get("people_count") or 1)
    replacement_brand = intent.get("replacement_brand")
    replacement_categories = intent.get("replacement_categories") or []
    if intent.get("revision_intent") == "replace_product" and replacement_brand and replacement_categories:
        preserved_categories = [
            category
            for category in intent.get("categories") or []
            if category not in replacement_categories
        ]
        replacement_products = search_products(
            products=products,
            query=query,
            categories=replacement_categories,
            brand=str(replacement_brand),
            min_rating=intent.get("min_rating"),
            min_stock=people_count,
            max_delivery_days=intent.get("max_delivery_days"),
            top_k=top_k,
        )
        preserved_products = search_products(
            products=products,
            query=query,
            categories=preserved_categories,
            min_rating=intent.get("min_rating"),
            min_stock=people_count,
            max_delivery_days=intent.get("max_delivery_days"),
            top_k=top_k,
        )
        results = [*replacement_products, *preserved_products][:top_k]
    else:
        results = search_products(
            products=products,
            query=query,
            categories=intent.get("categories"),
            min_rating=intent.get("min_rating"),
            min_stock=people_count,
            max_delivery_days=intent.get("max_delivery_days"),
            top_k=top_k,
        )
    constraints = _constraints(intent)
    for product in results:
        product["retrieval_score"] = product.get("retrieval_score", 0)
        product["retrieval_reason"] = "fallback_text_structured_filter"
        product["matched_fields"] = ["name", "brand", "category", "supplier", "description", "tags"]
        product["constraints_applied"] = constraints
    return results


def retrieve_products_with_evidence(
    query: str,
    intent: dict[str, Any],
    top_k: int = 12,
    persist_dir: Path | str = CHROMA_DIR,
) -> RetrievalResult:
    vector_query = _query_with_intent(query, intent)
    constraints = _constraints(intent)
    categories = [str(category) for category in intent.get("categories") or []]
    if len(categories) > 1:
        ranked, constraints_relaxed = _retrieve_multi_category_products(
            query=query,
            intent=intent,
            categories=categories,
            top_k=top_k,
            persist_dir=persist_dir,
            constraints=constraints,
        )
        if ranked:
            evidence = {
                "products": _product_evidence(ranked),
                "policies": _knowledge_evidence_with_fallback(POLICY_COLLECTION, vector_query, 5, persist_dir),
                "suppliers": _knowledge_evidence_with_fallback(SUPPLIER_COLLECTION, vector_query, 5, persist_dir),
                "constraints": constraints,
                "constraints_relaxed": constraints_relaxed,
                "retrieval_mode": "hybrid_rrf_vector_bm25",
            }
            return RetrievalResult(products=ranked, evidence=evidence)

    vector_hits = _vector_product_hits(vector_query, intent, top_k, persist_dir)
    bm25_products = _bm25_results(query, intent, top_k=top_k)
    fused = _fuse_vector_and_bm25_results(vector_hits, bm25_products, constraints)
    if not fused:
        products = _fallback_products(query, intent, top_k)
        return RetrievalResult(
            products=products,
            evidence={
                "products": _product_evidence(products),
                "policies": _knowledge_evidence_with_fallback(POLICY_COLLECTION, vector_query, 5, persist_dir),
                "suppliers": _knowledge_evidence_with_fallback(SUPPLIER_COLLECTION, vector_query, 5, persist_dir),
                "constraints": constraints,
                "constraints_relaxed": False,
                "retrieval_mode": "hybrid_vector_filter",
                "retrieval_fallback": "text_products",
            },
        )

    filtered = _filter_vector_products(fused, intent, constraints)
    constraints_relaxed = False
    if not filtered:
        constraints_relaxed = True
        filtered = fused
        for product in filtered:
            product["retrieval_reason"] = "hybrid_rrf_constraints_relaxed"

    ranked = _select_with_category_quota(filtered, categories, top_k)
    evidence = {
        "products": _product_evidence(ranked),
        "policies": _knowledge_evidence_with_fallback(POLICY_COLLECTION, vector_query, 5, persist_dir),
        "suppliers": _knowledge_evidence_with_fallback(SUPPLIER_COLLECTION, vector_query, 5, persist_dir),
        "constraints": constraints,
        "constraints_relaxed": constraints_relaxed,
        "retrieval_mode": "hybrid_rrf_vector_bm25",
    }
    return RetrievalResult(products=ranked, evidence=evidence)


def retrieve_products(query: str, intent: dict[str, Any], top_k: int = 12) -> list[dict[str, Any]]:
    return retrieve_products_with_evidence(
        query=query,
        intent=intent,
        top_k=top_k,
    ).products
