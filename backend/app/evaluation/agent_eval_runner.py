from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from app.agent.procurement_agent import run_procurement_agent
from app.core.config import DATA_DIR
from app.evaluation.business_metrics import average, calculate_business_metrics
from app.evaluation.mock_eval_runner import DEFAULT_QUESTIONS, EVAL_FILE, _read_questions


def _context_from_product(product: dict[str, Any]) -> str:
    return (
        f"{product.get('name')} | {product.get('category')} | "
        f"${product.get('price')} | rating {product.get('rating')} | "
        f"stock {product.get('stock')} | delivery {product.get('delivery_days')} days"
    )


def _score_context_precision(retrieved_products: list[dict[str, Any]], plan: dict[str, Any]) -> float:
    if not retrieved_products:
        return 0.0
    selected_ids = {str(item.get("product_id")) for item in plan.get("items", [])}
    retrieved_ids = {str(product.get("product_id")) for product in retrieved_products}
    if not selected_ids:
        return 0.0
    return round(len(selected_ids & retrieved_ids) / len(selected_ids), 3)


def _score_context_recall(plan: dict[str, Any], intent_categories: list[str]) -> float:
    if not intent_categories:
        return 1.0 if plan.get("items") else 0.0
    selected_categories = {str(item.get("category")) for item in plan.get("items", [])}
    return round(len(selected_categories & set(intent_categories)) / len(intent_categories), 3)


def _score_answer_relevance(answer: str, plan: dict[str, Any]) -> float:
    if not answer:
        return 0.0
    total_mentions = 1 if str(plan.get("total_amount", "")) in answer else 0
    item_mentions = sum(
        1 for item in plan.get("items", []) if str(item.get("name", "")).lower() in answer.lower()
    )
    denominator = max(1, len(plan.get("items", [])) + 1)
    return round(min(1.0, (item_mentions + total_mentions) / denominator), 3)


def _score_faithfulness(answer: str, retrieved_products: list[dict[str, Any]], plan: dict[str, Any]) -> float:
    if not answer or not plan.get("items"):
        return 0.0
    product_names = {str(product.get("name", "")).lower() for product in retrieved_products}
    selected_names = {str(item.get("name", "")).lower() for item in plan.get("items", [])}
    unsupported = [name for name in selected_names if name and name not in product_names]
    return 0.0 if unsupported else 1.0


def run_agent_evaluation(questions: list[str] | None = None) -> list[dict[str, Any]]:
    questions = questions or _read_questions() or DEFAULT_QUESTIONS
    rows: list[dict[str, Any]] = []

    for index, question in enumerate(questions, start=1):
        result = run_procurement_agent(question, session_id=f"eval-agent-{index}", language="en")
        plan = result.get("recommended_plan", {})
        retrieved_products = result.get("retrieved_products", [])
        parsed_intent = result.get("parsed_intent", {})
        answer = str(result.get("answer") or "")
        row = {
            "log_id": index,
            "evaluation_mode": "agent",
            "question": question,
            "answer": answer,
            "contexts": [_context_from_product(product) for product in retrieved_products],
            "context_precision": _score_context_precision(retrieved_products, plan),
            "context_recall": _score_context_recall(plan, list(parsed_intent.get("categories") or [])),
            "faithfulness": _score_faithfulness(answer, retrieved_products, plan),
            "answer_relevance": _score_answer_relevance(answer, plan),
            "budget_compliance": plan.get("budget_status") != "over_budget",
            "inventory_validity": plan.get("inventory_status") == "valid",
            "constraint_satisfaction": plan.get("constraint_satisfaction") == "satisfied",
            "latency_ms": 0,
            "trace_id": result.get("trace_id"),
            "model_provider": result.get("model_provider"),
            "model_name": result.get("model_name"),
            "used_mock_llm": result.get("used_mock_llm"),
            "llm_error": result.get("llm_error"),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        rows.append(row)

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    EVAL_FILE.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
    return rows


def summarize_agent_evaluations() -> dict[str, Any]:
    if not EVAL_FILE.exists():
        rows = run_agent_evaluation()
    else:
        rows = json.loads(EVAL_FILE.read_text(encoding="utf-8"))
    business = calculate_business_metrics(rows)
    return {
        "context_precision": average(rows, "context_precision"),
        "context_recall": average(rows, "context_recall"),
        "faithfulness": average(rows, "faithfulness"),
        "answer_relevance": average(rows, "answer_relevance"),
        "average_latency": average(rows, "latency_ms"),
        "results": rows,
        **business,
    }
