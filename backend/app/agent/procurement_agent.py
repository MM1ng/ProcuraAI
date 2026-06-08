from __future__ import annotations

from typing import Any

from app.agent.intent_parser import parse_purchase_request
from app.agent.plan_generator import generate_plan_explanation, generate_procurement_plan
from app.agent.plan_variants import generate_plan_options
from app.agent.prompts import ERROR_MESSAGES, PLAN_RESPONSE_TEMPLATES
from app.agent.session_state import get_session_state, save_session_state
from app.observability.langfuse_client import LangfuseClient
from app.observability.local_tracer import elapsed_ms, log_observability_event, new_trace_id, now_ms
from app.rag.retriever import RetrievalResult, retrieve_products, retrieve_products_with_evidence
from app.services.llm_service import settings

_ORIGINAL_RETRIEVE_PRODUCTS = retrieve_products


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


STATUS_LABELS = {
    "en": {
        "within_budget": "within budget",
        "no_budget_provided": "no budget provided",
        "over_budget": "over budget",
        "valid": "valid",
        "insufficient_stock": "insufficient stock",
        "satisfied": "satisfied",
        "needs_review": "needs review",
    },
    "zh": {
        "within_budget": "预算内",
        "no_budget_provided": "未提供预算",
        "over_budget": "超预算",
        "valid": "有效",
        "insufficient_stock": "库存不足",
        "satisfied": "已满足",
        "needs_review": "需审查",
    },
    "fr": {
        "within_budget": "dans le budget",
        "no_budget_provided": "budget non fourni",
        "over_budget": "hors budget",
        "valid": "valide",
        "insufficient_stock": "stock insuffisant",
        "satisfied": "satisfait",
        "needs_review": "à vérifier",
    },
}


def _status_label(status: Any, language: str) -> str:
    value = str(status or "")
    return STATUS_LABELS.get(language, STATUS_LABELS["en"]).get(value, value)


def _format_currency(value: Any) -> str:
    return f"${float(value or 0):.2f}"


def _item_detail_lines(items: list[dict[str, Any]], language: str) -> list[str]:
    if not items:
        return []

    lines: list[str] = []
    if language == "zh":
        lines.append("推荐明细：")
        for item in items:
            subtotal = float(item.get("unit_price", 0) or 0) * int(item.get("quantity", 0) or 0)
            lines.append(
                f"- {item.get('name')}（{item.get('category')}）：数量 {item.get('quantity')}，"
                f"单价 {_format_currency(item.get('unit_price'))}，小计 {_format_currency(subtotal)}，"
                f"配送 {item.get('delivery_days')} 天，评分 {item.get('rating')}。"
            )
        return lines

    if language == "fr":
        lines.append("Détails recommandés :")
        for item in items:
            subtotal = float(item.get("unit_price", 0) or 0) * int(item.get("quantity", 0) or 0)
            lines.append(
                f"- {item.get('name')} ({item.get('category')}) : quantité {item.get('quantity')}, "
                f"prix unitaire {_format_currency(item.get('unit_price'))}, sous-total {_format_currency(subtotal)}, "
                f"livraison {item.get('delivery_days')} jours, note {item.get('rating')}."
            )
        return lines

    lines.append("Recommended details:")
    for item in items:
        subtotal = float(item.get("unit_price", 0) or 0) * int(item.get("quantity", 0) or 0)
        lines.append(
            f"- {item.get('name')} ({item.get('category')}): quantity {item.get('quantity')}, "
            f"unit price {_format_currency(item.get('unit_price'))}, subtotal {_format_currency(subtotal)}, "
            f"delivery {item.get('delivery_days')} days, rating {item.get('rating')}."
        )
    return lines


def _answer_from_plan(
    plan: dict[str, Any],
    language: str,
    intent: dict[str, Any] | None = None,
    plan_options: list[dict[str, Any]] | None = None,
) -> str:
    language = _language(language)
    answer = PLAN_RESPONSE_TEMPLATES[language].format(
        item_count=len(plan.get("items", [])),
        total_amount=float(plan.get("total_amount", 0) or 0),
        budget_status=_status_label(plan.get("budget_status"), language),
        inventory_status=_status_label(plan.get("inventory_status"), language),
        constraint_satisfaction=_status_label(plan.get("constraint_satisfaction"), language),
    )
    notes: list[str] = _item_detail_lines(plan.get("items", []), language)
    plan_options = plan_options or []
    if plan_options:
        executable = [option.get("name") for option in plan_options if option.get("plan", {}).get("selectable") is not False]
        blocked = [option.get("name") for option in plan_options if option.get("plan", {}).get("selectable") is False]
        if blocked:
            if language == "zh":
                notes.append(
                    f"共生成 {len(plan_options)} 个候选方案，仅 {', '.join(executable)} 满足预算约束；"
                    f"{', '.join(blocked)} 因超预算仅供参考。"
                )
            elif language == "fr":
                notes.append(
                    f"{len(plan_options)} options ont été générées ; seules {', '.join(executable)} respectent le budget. "
                    f"{', '.join(blocked)} restent des références non sélectionnables."
                )
            else:
                notes.append(
                    f"Generated {len(plan_options)} candidate plans; only {', '.join(executable)} "
                    f"meets the budget constraint. {', '.join(blocked)} are reference-only."
                )

    max_delivery_days = (intent or {}).get("max_delivery_days")
    if max_delivery_days is not None:
        slow_items = [
            item for item in plan.get("items", []) if int(item.get("delivery_days", 999) or 999) > int(max_delivery_days)
        ]
        if slow_items:
            slow_names = ", ".join(str(item.get("name")) for item in slow_items)
            if language == "zh":
                notes.append(f"{slow_names} 超过 {max_delivery_days} 天快速配送偏好，如需更快到货请切换快速配送备选方案。")
            elif language == "fr":
                notes.append(
                    f"{slow_names} dépasse la préférence de livraison de {max_delivery_days} jours ; "
                    "utilisez une option livraison rapide si cette contrainte est stricte."
                )
            else:
                notes.append(
                    f"{slow_names} exceeds the {max_delivery_days}-day fast-delivery preference; "
                    "switch to a faster delivery option if that timing is strict."
                )

    return " ".join([answer, *notes]).strip()


def _combine_llm_error(*errors: str | None) -> str | None:
    values = [error for error in errors if error]
    return " | ".join(values) if values else None


def _empty_retrieval_evidence() -> dict[str, Any]:
    return {
        "products": [],
        "policies": [],
        "suppliers": [],
        "constraints": {},
        "constraints_relaxed": False,
        "retrieval_mode": "not_available",
    }


def _retrieve_products_for_agent(message: str, intent: dict[str, Any], top_k: int) -> RetrievalResult:
    if retrieve_products is not _ORIGINAL_RETRIEVE_PRODUCTS:
        return RetrievalResult(
            products=retrieve_products(message, intent, top_k=top_k),
            evidence=_empty_retrieval_evidence(),
        )
    return retrieve_products_with_evidence(message, intent, top_k=top_k)


def select_default_plan_option(plan_options: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not plan_options:
        return None
    balanced = next((option for option in plan_options if option.get("id") == "plan_b"), None)
    if balanced and balanced.get("plan", {}).get("budget_status") != "over_budget":
        return balanced
    within_budget = [
        option
        for option in plan_options
        if option.get("plan", {}).get("budget_status") == "within_budget"
    ]
    if within_budget:
        return sorted(within_budget, key=lambda option: float(option.get("plan", {}).get("total_amount", 0) or 0))[0]
    return balanced or plan_options[0]


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

        retrieval_result = _retrieve_products_for_agent(message, intent, top_k=30)
        retrieved_products = retrieval_result.products
        retrieval_evidence = retrieval_result.evidence
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
            default_option = select_default_plan_option(plan_options)
            if default_option:
                plan = default_option["plan"]
        tool_calls.append({"name": "generate_procurement_plan", "status": "success"})
        fallback_answer = _answer_from_plan(plan, language, intent=intent, plan_options=plan_options)
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
        retrieval_evidence = _empty_retrieval_evidence()
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
        "retrieval_evidence": retrieval_evidence,
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
        "selected_plan_id": plan.get("plan_option_id") if plan_options else None,
        "answer": answer,
        "trace_id": trace_id,
        "retrieved_products": retrieved_products[:12],
        "retrieval_evidence": retrieval_evidence,
        "model_provider": model_provider,
        "model_name": model_name,
        "used_mock_llm": used_mock_llm,
        "llm_error": llm_error,
        "llm_timings": llm_timings,
        "used_previous_context": used_previous_context,
        "previous_trace_id": session_state.get("trace_id") if session_state else None,
    }
