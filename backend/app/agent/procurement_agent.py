from __future__ import annotations

from typing import Any

from app.agent.intent_parser import parse_purchase_request
from app.agent.plan_generator import generate_plan_explanation, generate_procurement_plan
from app.agent.plan_variants import generate_plan_options
from app.agent.prompts import ERROR_MESSAGES, PLAN_RESPONSE_TEMPLATES
from app.agent.session_state import get_session_state, save_session_state
from app.observability.langfuse_client import LangfuseClient
from app.observability.local_tracer import elapsed_ms, log_observability_event, new_trace_id, now_ms
from app.rag.retriever import retrieve_products
from app.services.llm_service import settings


def _language(language: str) -> str:
    return language if language in PLAN_RESPONSE_TEMPLATES else "en"


def _reason_from_item(item: dict[str, Any], language: str) -> str:
    if language == "zh":
        return (
            f"为 {item.get('category')} 选择了 {item.get('name')}：评分 {item.get('rating')}，"
            f"{item.get('delivery_days')} 天交付，库存 {item.get('stock')}，单价 ${item.get('unit_price'):.2f}。"
        )
    if language == "fr":
        return (
            f"Produit choisi pour {item.get('category')} : {item.get('name')}, note {item.get('rating')}, "
            f"livraison en {item.get('delivery_days')} jours, stock {item.get('stock')}, "
            f"prix unitaire ${item.get('unit_price'):.2f}."
        )
    return item.get("reason", "")


def _answer_from_plan(plan: dict[str, Any], language: str) -> str:
    language = _language(language)
    answer = PLAN_RESPONSE_TEMPLATES[language].format(
        item_count=len(plan.get("items", [])),
        total_amount=float(plan.get("total_amount", 0) or 0),
        budget_status=plan.get("budget_status"),
        inventory_status=plan.get("inventory_status"),
        constraint_satisfaction=plan.get("constraint_satisfaction"),
    )
    reasons = " ".join(_reason_from_item(item, language) for item in plan.get("items", []))
    return f"{answer} {reasons}".strip()


def _combine_llm_error(*errors: str | None) -> str | None:
    values = [error for error in errors if error]
    return " | ".join(values) if values else None


def run_procurement_agent(
    message: str,
    session_id: str,
    previous_intent: dict[str, Any] | None = None,
    previous_plan: dict[str, Any] | None = None,
    language: str = "en",
) -> dict[str, Any]:
    language = _language(language)
    start = now_ms()
    trace_id = new_trace_id()
    tool_calls: list[dict[str, Any]] = []
    error: str | None = None
    model_provider = "mock"
    model_name = settings.QWEN_MODEL
    used_mock_llm = True
    llm_error: str | None = None
    session_state = get_session_state(session_id)
    if previous_intent is None and session_state:
        previous_intent = session_state.get("parsed_intent")
    if previous_plan is None and session_state:
        previous_plan = session_state.get("recommended_plan")
    used_previous_context = bool(previous_intent or previous_plan)

    try:
        intent = parse_purchase_request(message, previous_intent)
        tool_calls.append({"name": "parse_purchase_request", "status": "success"})
        model_provider = str(intent.get("model_provider") or model_provider)
        model_name = str(intent.get("model_name") or model_name)
        used_mock_llm = bool(intent.get("used_mock_llm"))
        llm_error = intent.get("llm_error")

        retrieved_products = retrieve_products(message, intent, top_k=30)
        tool_calls.append(
            {
                "name": "search_products",
                "status": "success",
                "count": len(retrieved_products),
            }
        )

        plan = generate_procurement_plan(retrieved_products, intent, previous_plan=previous_plan)
        plan_options = (
            generate_plan_options(retrieved_products, intent)
            if intent.get("revision_intent") == "new_plan"
            else []
        )
        if plan_options:
            balanced = next((option for option in plan_options if option.get("id") == "plan_b"), None)
            if balanced:
                plan = balanced["plan"]
        tool_calls.append({"name": "generate_procurement_plan", "status": "success"})
        fallback_answer = _answer_from_plan(plan, language)
        explanation = generate_plan_explanation(intent, retrieved_products, plan, fallback_answer)
        tool_calls.append({"name": "generate_plan_explanation", "status": "success"})
        answer = explanation["content"]
        llm_timings = {
            "intent_parser_ms": intent.get("llm_latency_ms"),
            "plan_explanation_ms": explanation.get("llm_latency_ms"),
        }
        plan["recommendation_reason"] = answer
        plan["recommendation_summary"] = answer
        model_provider = str(explanation.get("model_provider") or model_provider)
        model_name = str(explanation.get("model_name") or model_name)
        used_mock_llm = used_mock_llm or bool(explanation.get("used_mock_llm"))
        llm_error = _combine_llm_error(llm_error, explanation.get("llm_error"))
    except Exception as exc:
        intent = previous_intent or {}
        retrieved_products = []
        plan = {
            "items": [],
            "selected_items": [],
            "total_amount": 0,
            "budget_status": "unknown",
            "inventory_status": "unknown",
            "constraint_satisfaction": "needs_review",
        }
        answer = ERROR_MESSAGES[language]
        error = str(exc)
        llm_error = _combine_llm_error(llm_error, error)
        llm_timings = {}
        plan_options = []
        tool_calls.append({"name": "agent_workflow", "status": "error", "error": error})

    event = {
        "trace_id": trace_id,
        "session_id": session_id,
        "language": language,
        "user_query": message,
        "parsed_intent": intent,
        "retrieved_products": retrieved_products[:8],
        "selected_products": plan.get("items", []),
        "final_answer": answer,
        "model_provider": model_provider,
        "model_name": model_name,
        "used_mock_llm": used_mock_llm,
        "llm_error": llm_error,
        "llm_timings": llm_timings,
        "used_previous_context": used_previous_context,
        "previous_trace_id": session_state.get("trace_id") if session_state else None,
        "tool_calls": tool_calls,
        "latency_ms": elapsed_ms(start),
        "error": error,
    }
    log_observability_event(event)
    LangfuseClient().trace(**event)
    save_session_state(session_id, intent, plan, retrieved_products[:12], trace_id)

    return {
        "session_id": session_id,
        "parsed_intent": intent,
        "recommended_plan": plan,
        "plan_options": plan_options,
        "selected_plan_id": "plan_b" if plan_options else None,
        "answer": answer,
        "trace_id": trace_id,
        "retrieved_products": retrieved_products[:12],
        "model_provider": model_provider,
        "model_name": model_name,
        "used_mock_llm": used_mock_llm,
        "llm_error": llm_error,
        "llm_timings": llm_timings,
        "used_previous_context": used_previous_context,
        "previous_trace_id": session_state.get("trace_id") if session_state else None,
    }
