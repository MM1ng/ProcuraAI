from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.agent.intent_parser import parse_purchase_request
from app.core.config import DATA_DIR, get_settings
from app.rag.knowledge_base import load_procurement_policies, load_supplier_profiles
from app.rag.retriever import retrieve_products_with_evidence
from app.rag.vector_store import PRODUCT_COLLECTION, query_vector_collection, rebuild_vector_collections
from app.services.product_service import load_products_from_csv


REPORT_FILE = DATA_DIR / "embedding_retrieval_comparison.json"
DEFAULT_TOP_K = 5
PRODUCTS_PER_CATEGORY = 8
EVALUATION_MODES = ["pure_vector", "hybrid"]


@dataclass(frozen=True)
class EvaluationCase:
    query: str
    intent: dict[str, Any]
    expected_categories: list[str]


def _evaluation_cases() -> list[EvaluationCase]:
    cases: list[tuple[str, list[str], dict[str, Any]]] = [
        (
            "We need keyboards, mice and headsets for 20 interns under $3000.",
            ["Keyboard", "Mouse", "Headset"],
            {"people_count": 20, "budget": 3000},
        ),
        (
            "Recommend webcams, headsets and docking stations for a remote team of 10 people.",
            ["Webcam", "Headset", "Docking Station"],
            {"people_count": 10},
        ),
        (
            "Find high rating monitors and keyboards with delivery within 5 days.",
            ["Monitor", "Keyboard"],
            {"min_rating": 4.2, "max_delivery_days": 5},
        ),
        (
            "Find fast delivery office chairs and standing desks for a new office.",
            ["Office Chair", "Standing Desk"],
            {"max_delivery_days": 5},
        ),
        (
            "Need external SSDs and routers for the IT team.",
            ["External SSD", "Router"],
            {"people_count": 8},
        ),
        (
            "采购摄像头、耳机和扩展坞，给10名远程员工使用。",
            ["Webcam", "Headset", "Docking Station"],
            {"people_count": 10},
        ),
    ]
    return [
        EvaluationCase(
            query=query,
            intent={
                **parse_purchase_request(query),
                **extra_intent,
                "categories": expected_categories,
            },
            expected_categories=expected_categories,
        )
        for query, expected_categories, extra_intent in cases
    ]


def _set_embedding_env(provider: str) -> None:
    os.environ["EMBEDDING_PROVIDER"] = provider
    os.environ["EMBEDDING_DIMENSION"] = "1024"
    os.environ["EMBEDDING_MODEL"] = _default_embedding_model()
    if provider in {"tongyi", "dashscope", "bailian"}:
        os.environ["EMBEDDING_STRICT"] = "true"
    else:
        os.environ.pop("EMBEDDING_STRICT", None)
    get_settings.cache_clear()


def _provider_index_dir(provider: str, run_id: str) -> Path:
    return DATA_DIR / "embedding_eval" / run_id / provider


def _build_provider_index(provider: str, cases: list[EvaluationCase], run_id: str) -> Path:
    _set_embedding_env(provider)
    persist_dir = _provider_index_dir(provider, run_id)
    persist_dir.mkdir(parents=True, exist_ok=True)
    products = _sample_products_for_cases(load_products_from_csv(), cases)
    rebuild_vector_collections(
        products=products,
        policies=load_procurement_policies(),
        suppliers=load_supplier_profiles(),
        persist_dir=persist_dir,
    )
    return persist_dir


def _sample_products_for_cases(
    products: list[dict[str, Any]],
    cases: list[EvaluationCase],
    per_category: int = PRODUCTS_PER_CATEGORY,
) -> list[dict[str, Any]]:
    wanted_categories = {
        category
        for case in cases
        for category in case.expected_categories
    }
    selected: list[dict[str, Any]] = []
    counts: dict[str, int] = {}
    for product in products:
        category = str(product.get("category"))
        if category not in wanted_categories:
            continue
        if counts.get(category, 0) >= per_category:
            continue
        selected.append(product)
        counts[category] = counts.get(category, 0) + 1
    return selected


def _first_relevant_rank(products: list[dict[str, Any]], expected_categories: set[str]) -> int | None:
    for index, product in enumerate(products, start=1):
        if str(product.get("category")) in expected_categories:
            return index
    return None


def _score_case_results(
    case: EvaluationCase,
    products: list[dict[str, Any]],
    latency_ms: float,
) -> dict[str, Any]:
    expected = set(case.expected_categories)
    retrieved_categories = [str(product.get("category")) for product in products]
    matched_categories = expected & set(retrieved_categories)
    unique_categories = sorted({category for category in retrieved_categories if category})
    missing_categories = sorted(expected - set(retrieved_categories))
    first_rank = _first_relevant_rank(products, expected)
    return {
        "query": case.query,
        "expected_categories": case.expected_categories,
        "retrieved_categories": retrieved_categories,
        "top_product_ids": [str(product.get("product_id")) for product in products],
        "top_product_names": [str(product.get("name")) for product in products],
        "hit_at_5": first_rank is not None and first_rank <= DEFAULT_TOP_K,
        "first_relevant_rank": first_rank,
        "mrr": round(1 / first_rank, 4) if first_rank else 0.0,
        "category_coverage": round(len(matched_categories) / len(expected), 4) if expected else 0.0,
        "unique_categories_returned": unique_categories,
        "missing_categories": missing_categories,
        "latency_ms": round(latency_ms, 2),
    }


def _summarize_provider(provider: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    count = len(rows)
    if count == 0:
        return {
            "provider": provider,
            "cases": 0,
            "hit_rate_at_5": 0.0,
            "mean_reciprocal_rank": 0.0,
            "mean_category_coverage": 0.0,
            "average_latency_ms": 0.0,
        }
    return {
        "provider": provider,
        "cases": count,
        "hit_rate_at_5": round(sum(1 for row in rows if row["hit_at_5"]) / count, 4),
        "mean_reciprocal_rank": round(sum(float(row["mrr"]) for row in rows) / count, 4),
        "mean_category_coverage": round(sum(float(row["category_coverage"]) for row in rows) / count, 4),
        "average_latency_ms": round(sum(float(row["latency_ms"]) for row in rows) / count, 2),
    }


def _pure_vector_products(case: EvaluationCase, persist_dir: Path, top_k: int = DEFAULT_TOP_K) -> list[dict[str, Any]]:
    categories = [str(category) for category in case.intent.get("categories") or []]
    rows: list[dict[str, Any]] = []
    if len(categories) > 1:
        by_id: dict[str, dict[str, Any]] = {}
        for category in categories:
            for row in query_vector_collection(
                PRODUCT_COLLECTION,
                f"{case.query} {category}",
                top_k=top_k,
                persist_dir=persist_dir,
            ):
                existing = by_id.get(str(row.get("id")))
                if existing is None or float(row.get("score", 0) or 0) > float(existing.get("score", 0) or 0):
                    by_id[str(row.get("id"))] = row
        rows = sorted(by_id.values(), key=lambda row: -float(row.get("score", 0) or 0))[:top_k]
    else:
        rows = query_vector_collection(PRODUCT_COLLECTION, case.query, top_k=top_k, persist_dir=persist_dir)

    products: list[dict[str, Any]] = []
    for row in rows:
        product = dict(row.get("metadata") or {})
        product["retrieval_score"] = row.get("score", 0)
        products.append(product)
    return products


def _evaluate_provider_mode(
    provider: str,
    cases: list[EvaluationCase],
    run_id: str,
    mode: str,
) -> dict[str, Any]:
    persist_dir = _provider_index_dir(provider, run_id)
    rows: list[dict[str, Any]] = []
    for case in cases:
        started = time.perf_counter()
        if mode == "pure_vector":
            products = _pure_vector_products(case, persist_dir)
        else:
            result = retrieve_products_with_evidence(
                query=case.query,
                intent=case.intent,
                top_k=DEFAULT_TOP_K,
                persist_dir=persist_dir,
            )
            products = result.products
        elapsed_ms = (time.perf_counter() - started) * 1000
        rows.append(_score_case_results(case, products, elapsed_ms))
    return {
        "summary": _summarize_provider(provider, rows),
        "rows": rows,
    }


def run_embedding_retrieval_comparison(
    providers: list[str] | None = None,
    output_path: Path = REPORT_FILE,
) -> dict[str, Any]:
    providers = providers or ["hash", "tongyi"]
    cases = _evaluation_cases()
    run_id = time.strftime("%Y%m%d-%H%M%S")
    report = {
        "top_k": DEFAULT_TOP_K,
        "run_id": run_id,
        "embedding_model": _default_embedding_model(),
        "embedding_dimension": 1024,
        "modes": EVALUATION_MODES,
        "providers": {},
    }
    for provider in providers:
        report["providers"][provider] = {}
        try:
            _build_provider_index(provider, cases, run_id)
            for mode in EVALUATION_MODES:
                report["providers"][provider][mode] = _evaluate_provider_mode(provider, cases, run_id, mode)
        except Exception as exc:
            report["providers"][provider]["error"] = {
                "summary": _summarize_provider(provider, []),
                "rows": [],
                "error": str(exc),
            }
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return report


def _default_embedding_model() -> str:
    return os.getenv("EMBEDDING_MODEL", "text-embedding-v4")
