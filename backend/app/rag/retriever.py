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


@dataclass
class RetrievalResult:
    products: list[dict[str, Any]]
    evidence: dict[str, Any]


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


def _product_evidence(products: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "product_id": product.get("product_id"),
            "name": product.get("name"),
            "category": product.get("category"),
            "brand": product.get("brand"),
            "supplier": product.get("supplier"),
            "score": product.get("retrieval_score", 0),
            "reason": product.get("retrieval_reason", ""),
            "matched_fields": product.get("matched_fields", []),
        }
        for product in products
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
    vector_hits = _vector_product_hits(vector_query, intent, top_k, persist_dir)
    if not vector_hits:
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

    candidate_products = [
        _product_from_hit(hit, "vector_recall_structured_filter", constraints)
        for hit in vector_hits
    ]
    filtered = _filter_vector_products(candidate_products, intent, constraints)
    constraints_relaxed = False
    if not filtered:
        constraints_relaxed = True
        filtered = [
            _product_from_hit(hit, "vector_recall_constraints_relaxed", constraints)
            for hit in vector_hits
        ]

    ranked = sorted(
        filtered,
        key=lambda product: (
            -float(product.get("retrieval_score", 0) or 0),
            -float(product.get("rating", 0) or 0),
            int(product.get("delivery_days", 999) or 999),
            float(product.get("price", 999999) or 999999),
        ),
    )[:top_k]
    evidence = {
        "products": _product_evidence(ranked),
        "policies": _knowledge_evidence_with_fallback(POLICY_COLLECTION, vector_query, 5, persist_dir),
        "suppliers": _knowledge_evidence_with_fallback(SUPPLIER_COLLECTION, vector_query, 5, persist_dir),
        "constraints": constraints,
        "constraints_relaxed": constraints_relaxed,
        "retrieval_mode": "hybrid_vector_filter",
    }
    return RetrievalResult(products=ranked, evidence=evidence)


def retrieve_products(query: str, intent: dict[str, Any], top_k: int = 12) -> list[dict[str, Any]]:
    return retrieve_products_with_evidence(
        query=query,
        intent=intent,
        top_k=top_k,
    ).products
