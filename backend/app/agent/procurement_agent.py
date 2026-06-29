from __future__ import annotations

from typing import Any

from app.agent.intent_parser import parse_purchase_request
from app.agent.plan_generator import generate_plan_explanation, generate_procurement_plan
from app.agent.plan_variants import generate_plan_options
from app.agent.prompts import ERROR_MESSAGES, PLAN_RESPONSE_TEMPLATES
from app.agent.session_state import get_session_state, save_session_state
from app.observability.langfuse_client import LangfuseClient
from app.observability.local_tracer import elapsed_ms, log_observability_event, new_trace_id, now_ms
from app.rag.query_rewriter import rewrite_query, should_rewrite
from app.rag.retriever import RetrievalResult, retrieve_products, retrieve_products_with_evidence
from app.services.llm_service import settings
from app.services.order_service import create_order_from_plan, save_order
from app.tools.stripe_ai_tools import create_checkout_for_selected_plan

_ORIGINAL_RETRIEVE_PRODUCTS = retrieve_products


def _language(language: str) -> str:
    return language if language in PLAN_RESPONSE_TEMPLATES else "en"


STATUS_LABELS = {
    "en": {
        "within_budget": "within budget", "no_budget_provided": "no budget provided",
        "over_budget": "over budget", "valid": "valid",
        "insufficient_stock": "insufficient stock", "satisfied": "satisfied",
        "needs_review": "needs review",
    },
    "zh": {
        "within_budget": "预算内", "no_budget_provided": "未提供预算",
        "over_budget": "超预算", "valid": "有效",
        "insufficient_stock": "库存不足", "satisfied": "已满足",
        "needs_review": "需审查",
    },
}


def _status_label(status: Any, language: str) -> str:
    value = str(status or "")
    return STATUS_LABELS.get(language, STATUS_LABELS["en"]).get(value, value)


def _format_currency(value: Any) -> str:
    return f"${float(value or 0):.2f}"


def _combine_llm_error(*errors: str | None) -> str | None:
    values = [error for error in errors if error]
    return " | ".join(values) if values else None


def _empty_retrieval_evidence() -> dict[str, Any]:
    return {
        "products": [], "policies": [], "suppliers": [],
        "constraints": {}, "constraints_relaxed": False,
        "retrieval_mode": "not_available",
    }


def _retrieve_products_for_agent(message: str, intent: dict[str, Any], top_k: int) -> RetrievalResult:
    if retrieve_products is not _ORIGINAL_RETRIEVE_PRODUCTS:
        return RetrievalResult(
            products=retrieve_products(message, intent, top_k=top_k),
            evidence=_empty_retrieval_evidence(),
        )
    return retrieve_products_with_evidence(message, intent, top_k=top_k)


def _determine_response_type(
    intent: dict[str, Any],
    plan: dict[str, Any],
    message: str,
) -> str | None:
    """Determine response type from parsed intent and plan context.

    Priority:
      1) Explicit order/payment keywords → order/payment
      2) Search/browse + categories → product_results
      3) Plan signals (recommend/need/budget/multi+qty) → recommendation_plan
      4) Fallback: plan has items → recommendation_plan
    """
    lowered = message.lower()
    revision_intent = str(intent.get("revision_intent", "") or "")
    categories = intent.get("categories") or []
    budget = intent.get("budget")

    if any(w in lowered for w in ["order", "checkout", "pay", "payment", "buy", "purchase", "订单", "下单", "结账", "支付", "付款", "买", "购买"]):
        return "payment" if any(w in lowered for w in ["pay", "checkout", "支付", "付款", "结账"]) else "order"

    has_search_kw = any(
        w in lowered for w in [
            "find", "search", "browse", "list", "show", "look",
            "查找", "搜索", "浏览", "列出", "显示", "找", "看看",
        ]
    )
    has_plan_kw = any(
        w in lowered for w in [
            "recommend", "plan", "procurement", "procure", "purchase", "buy", "need",
            "推荐", "方案", "采购", "购买", "需要", "买",
        ]
    )
    is_replacement = revision_intent in ("replace_product",)
    is_multi = isinstance(categories, list) and len(categories) > 1
    has_qty = (
        intent.get("quantity_per_category")
        and isinstance(intent.get("quantity_per_category"), dict)
        and any(v > 1 for v in intent["quantity_per_category"].values())
    )

    if has_plan_kw and (budget is not None or is_multi or has_qty):
        return "recommendation_plan"
    if has_plan_kw and not has_search_kw:
        return "recommendation_plan"
    if is_multi and has_qty:
        return "recommendation_plan"

    if categories and (has_search_kw or not has_plan_kw):
        return "product_results"
    if revision_intent == "new_plan" and categories and budget is None and not is_multi:
        return "product_results"
    if is_replacement:
        return "product_results"

    if plan.get("items") and len(plan.get("items", [])) > 0:
        return "recommendation_plan"

    return None


def _summarize_search_message(
    products: list[dict[str, Any]],
    message: str,
    language: str,
) -> str:
    total = len(products)
    if total == 0:
        if language == "zh":
            return "未找到匹配的商品。请尝试调整品类、预算或配送时间等约束条件后重试。"
        return "No matching products found. Try adjusting categories, budget, or delivery time constraints and try again."
    examples = products[:3]
    if language == "zh":
        example_text = "、".join(
            f"{product.get('name')}（¥{float(product.get('price') or 0):.2f}，评分{product.get('rating')}）"
            for product in examples
        )
        return (
            f"已为你找到 {total} 件商品，优先展示评分高、库存充足的。"
            f"例如：{example_text}等。"
        )
    example_text = ", ".join(
        f"{product.get('name')} (${float(product.get('price') or 0):.2f}, rating {product.get('rating')})"
        for product in examples
    )
    return (
        f"I found {total} products, prioritized by high ratings, sufficient stock, "
        f"and fast delivery. For example: {example_text}."
    )


def select_default_plan_option(plan_options: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not plan_options:
        return None
    balanced = next((o for o in plan_options if o.get("id") == "plan_b"), None)
    if balanced and balanced.get("plan", {}).get("budget_status") != "over_budget":
        return balanced
    within = [o for o in plan_options if o.get("plan", {}).get("budget_status") == "within_budget"]
    if within:
        return sorted(within, key=lambda o: float(o.get("plan", {}).get("total_amount", 0) or 0))[0]
    return balanced or plan_options[0]


def run_procurement_agent(
    message: str,
    session_id: str,
    previous_intent: dict[str, Any] | None = None,
    previous_plan: dict[str, Any] | None = None,
    language: str = "en",
    skip_plan_explanation: bool = False,
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
        if intent.get("response_language") in ("zh", "en"):
            language = intent["response_language"]
        tool_calls.append({"name": "parse_purchase_request", "status": "success"})
        model_provider = str(intent.get("model_provider") or model_provider)
        model_name = str(intent.get("model_name") or model_name)
        used_mock_llm = bool(intent.get("used_mock_llm"))
        llm_error = intent.get("llm_error")

        # Query Rewrite: bridge multi-turn conversational wording and retrieval terms.
        if should_rewrite(message, previous_intent):
            rewritten = rewrite_query(message, previous_intent)
            retrieval_query = rewritten if rewritten and rewritten != message else message
        else:
            retrieval_query = message

        retrieval_result = _retrieve_products_for_agent(retrieval_query, intent, top_k=30)
        retrieved_products = retrieval_result.products
        retrieval_evidence = retrieval_result.evidence
        tool_calls.append({"name": "search_products", "status": "success", "count": len(retrieved_products)})

        plan = generate_procurement_plan(retrieved_products, intent, previous_plan=previous_plan)
        plan_options = (
            generate_plan_options(retrieved_products, intent)
            if intent.get("revision_intent") == "new_plan" else []
        )
        if plan_options:
            default_option = select_default_plan_option(plan_options)
            if default_option:
                plan = default_option["plan"]
        tool_calls.append({"name": "generate_procurement_plan", "status": "success"})

        response_type = _determine_response_type(intent, plan, message)

        if response_type == "product_results":
            answer = _summarize_search_message(retrieved_products, message, language)
            plan["recommendation_reason"] = answer
            plan["recommendation_summary"] = answer
            explanation = None
            if not skip_plan_explanation:
                explanation = generate_plan_explanation(intent, retrieved_products, plan, answer, language)
                plan["recommendation_reason"] = explanation["content"]
                plan["recommendation_summary"] = explanation["content"]
                llm_answer = str(explanation.get("content") or "").strip()
                if llm_answer and len(llm_answer) > 30 and not bool(explanation.get("used_mock_llm")):
                    answer = llm_answer
                    plan["recommendation_reason"] = answer
                    plan["recommendation_summary"] = answer
                model_provider = str(explanation.get("model_provider") or model_provider)
                model_name = str(explanation.get("model_name") or model_name)
                used_mock_llm = used_mock_llm or bool(explanation.get("used_mock_llm"))
                llm_error = _combine_llm_error(llm_error, explanation.get("llm_error"))
            llm_timings = {
                "intent_parser_ms": intent.get("llm_latency_ms"),
                "plan_explanation_ms": explanation.get("latency_ms") if explanation else None,
            }
        else:
            # Always generate the structured itemized answer as the base response
            answer = _answer_from_plan(plan, language, intent, plan_options)
            plan["recommendation_reason"] = answer
            plan["recommendation_summary"] = answer
            # Try LLM for a richer explanation
            explanation = None
            if not skip_plan_explanation:
                explanation = generate_plan_explanation(intent, retrieved_products, plan, answer, language)
                tool_calls.append({"name": "generate_plan_explanation", "status": "success"})
                llm_answer = str(explanation.get("content") or "").strip()
                # Only use LLM answer if it returned something meaningfully different
                if llm_answer and len(llm_answer) > 80 and llm_answer != answer:
                    answer = llm_answer
                    plan["recommendation_reason"] = answer
                    plan["recommendation_summary"] = answer
            llm_timings = {
                "intent_parser_ms": intent.get("llm_latency_ms"),
                "plan_explanation_ms": explanation.get("latency_ms") if explanation else None,
            }
            if explanation:
                model_provider = str(explanation.get("model_provider") or model_provider)
                model_name = str(explanation.get("model_name") or model_name)
                used_mock_llm = used_mock_llm or bool(explanation.get("used_mock_llm"))
                llm_error = _combine_llm_error(llm_error, explanation.get("llm_error"))
    except Exception as exc:
        intent = previous_intent or {}
        retrieved_products = []
        retrieval_evidence = _empty_retrieval_evidence()
        plan = {
            "items": [], "selected_items": [],
            "total_amount": 0, "budget_status": "unknown",
            "inventory_status": "unknown", "constraint_satisfaction": "needs_review",
        }
        answer = ERROR_MESSAGES[language]
        error = str(exc)
        llm_error = _combine_llm_error(llm_error, error)
        llm_timings, plan_options, response_type = {}, [], None
        tool_calls.append({"name": "agent_workflow", "status": "error", "error": error})

    event = {
        "trace_id": trace_id, "session_id": session_id, "language": language,
        "user_query": message, "parsed_intent": intent,
        "retrieved_products": retrieved_products[:8], "retrieval_evidence": retrieval_evidence,
        "selected_products": plan.get("items", []), "final_answer": answer,
        "model_provider": model_provider, "model_name": model_name,
        "used_mock_llm": used_mock_llm, "llm_error": llm_error, "llm_timings": llm_timings,
        "used_previous_context": used_previous_context,
        "previous_trace_id": session_state.get("trace_id") if session_state else None,
        "tool_calls": tool_calls, "latency_ms": elapsed_ms(start), "error": error,
    }
    log_observability_event(event)
    LangfuseClient().trace(**event)
    save_session_state(session_id, intent, plan, retrieved_products[:12], trace_id)

    products = None
    if response_type == "product_results":
        products = [
            {
                "product_id": p.get("product_id"), "name": p.get("name"),
                "brand": p.get("brand"), "category": p.get("category"),
                "price": p.get("price"), "rating": p.get("rating"),
                "stock": p.get("stock"), "delivery_days": p.get("delivery_days"),
                "supplier": p.get("supplier"), "description": p.get("description"),
                "compliance_level": p.get("compliance_level"),
                "warranty_months": p.get("warranty_months"), "tags": p.get("tags"),
            }
            for p in retrieved_products[:25]
        ]

    recommendation_plan = plan if response_type == "recommendation_plan" else None

    # Auto-order + checkout for order/payment intents
    order_id = None
    order_status = None
    checkout_url = None
    if response_type in ("order", "payment") and plan.get("items"):
        try:
            if plan_options:
                first_valid = next((o for o in plan_options if o.get("plan", {}).get("budget_status") != "over_budget"), plan_options[0])
                selected_plan = first_valid["plan"]
            else:
                selected_plan = plan
            order = create_order_from_plan(selected_plan)
            order = save_order(order)
            order_id = order.get("order_id", "")
            order_status = order.get("status", "pending_payment")
            checkout = create_checkout_for_selected_plan(
                plan_id=str(selected_plan.get("plan_option_id", selected_plan.get("budget_status", "plan_auto"))),
                order_id=order_id,
            )
            checkout_url = checkout.get("checkout_url", "")
            if language == "zh":
                answer += "\n\n已为您创建订单 #" + order_id + "，正在跳转支付..."
            else:
                answer += "\n\nOrder #" + order_id + " created. Redirecting to payment..."
            tool_calls.append({"name": "auto_checkout", "status": "success", "order_id": order_id})
        except Exception as exc:
            error = str(exc)
            llm_error = _combine_llm_error(llm_error, error)
            tool_calls.append({"name": "auto_checkout", "status": "error", "error": error})

    return {
        "session_id": session_id, "parsed_intent": intent,
        "recommended_plan": plan, "plan_options": plan_options,
        "selected_plan_id": plan.get("plan_option_id") if plan_options else None,
        "answer": answer, "trace_id": trace_id,
        "retrieved_products": retrieved_products[:12], "retrieval_evidence": retrieval_evidence,
        "model_provider": model_provider, "model_name": model_name,
        "used_mock_llm": used_mock_llm, "llm_error": llm_error, "llm_timings": llm_timings,
        "used_previous_context": used_previous_context,
        "previous_trace_id": session_state.get("trace_id") if session_state else None,
        "type": response_type, "products": products,
        "recommendation_plan": recommendation_plan, "actions": [],
        "order_id": order_id, "order_status": order_status, "checkout_url": checkout_url,
    }


def _answer_from_plan(
    plan: dict[str, Any],
    language: str,
    intent: dict[str, Any] | None = None,
    plan_options: list[dict[str, Any]] | None = None,
) -> str:
    language = _language(language)
    items = plan.get("items", [])
    total_amount = float(plan.get("total_amount", 0) or 0)
    item_count = len(items)

    # Build item-level breakdown lines
    item_lines: list[str] = []
    cats: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        name = str(item.get("name", ""))
        qty = int(item.get("quantity", 0) or 0)
        price = float(item.get("unit_price", 0) or 0)
        subtotal = float(item.get("subtotal", 0) or 0)
        cat = str(item.get("category", ""))
        delivery = int(item.get("delivery_days", 0) or 0)
        if language == "zh":
            item_lines.append(f"  - {name} x{qty}, 单价 ${price:.2f}, 小计 ${subtotal:.2f}, {delivery}天送达")
        else:
            item_lines.append(f"  - {name} x{qty}, unit ${price:.2f}, subtotal ${subtotal:.2f}, {delivery}-day delivery")
        cats.setdefault(cat, []).append(item)

    parts: list[str] = []

    # Summary line
    budget_label = _status_label(plan.get("budget_status"), language)
    inventory_label = _status_label(plan.get("inventory_status"), language)
    constraint_label = _status_label(plan.get("constraint_satisfaction"), language)
    avg_rating = plan.get("avg_rating")
    rating_str = f", avg rating {avg_rating}" if avg_rating else ""

    if language == "zh":
        summary = (
            f"已为您生成采购方案：共 {item_count} 件商品，"
            f"总金额 ${total_amount:.2f}{rating_str}。"
            f"预算：{budget_label}，库存：{inventory_label}，约束：{constraint_label}。"
        )
    else:
        summary = (
            f"I generated a procurement plan with {item_count} items, "
            f"total ${total_amount:.2f}{rating_str}. "
            f"Budget: {budget_label}, Inventory: {inventory_label}, "
            f"Constraints: {constraint_label}."
        )
    parts.append(summary)

    # Item detail lines
    if item_lines:
        if language == "zh":
            parts.append("商品明细：")
        else:
            parts.append("Item details:")
        parts.extend(item_lines)

    # Category summary
    if len(cats) > 1:
        cat_summaries = []
        if language == "zh":
            cat_summaries = [f"{cat} {len(items)}件" for cat, items in sorted(cats.items())]
            parts.append("品类分布：" + " | ".join(cat_summaries))
        else:
            cat_summaries = [f"{cat}: {len(items)} item(s)" for cat, items in sorted(cats.items())]
            parts.append("Category breakdown: " + " | ".join(cat_summaries))

    # Delivery range
    delivery_days_list = [
        int(item.get("delivery_days", 0) or 0) for item in items if item.get("delivery_days")
    ]
    if delivery_days_list:
        min_d, max_d = min(delivery_days_list), max(delivery_days_list)
        if language == "zh":
            parts.append(f"预计配送时间：{min_d}-{max_d}天")
        else:
            parts.append(f"Estimated delivery: {min_d}-{max_d} days")

    # Plan options notes
    notes: list[str] = []
    plan_options = plan_options or []
    if plan_options:
        executable = [o.get("name") for o in plan_options if o.get("plan", {}).get("selectable") is not False]
        blocked = [o.get("name") for o in plan_options if o.get("plan", {}).get("selectable") is False]
        if blocked:
            if language == "zh":
                notes.append(
                    f"共生成 {len(plan_options)} 个候选方案，仅 {', '.join(executable)} 满足预算约束；"
                    f"{', '.join(blocked)} 因超预算仅供参考。"
                )
            else:
                notes.append(
                    f"Generated {len(plan_options)} candidate plans; only {', '.join(executable)} "
                    f"meets the budget constraint. {', '.join(blocked)} are reference-only."
                )
    max_delivery_days = (intent or {}).get("max_delivery_days")
    if max_delivery_days is not None:
        slow_items = [
            item for item in items
            if int(item.get("delivery_days", 999) or 999) > int(max_delivery_days)
        ]
        if slow_items:
            slow_names = ", ".join(str(item.get("name")) for item in slow_items)
            if language == "zh":
                notes.append(f"{slow_names} 超过 {max_delivery_days} 天快速配送偏好。")
            else:
                notes.append(f"{slow_names} exceeds the {max_delivery_days}-day fast-delivery preference.")

    if notes:
        parts.extend(notes)

    return "\n\n".join(parts).strip()
