from __future__ import annotations

from typing import Any

from app.agent.intent_parser import parse_purchase_request
from app.agent.plan_generator import generate_plan_explanation, generate_procurement_plan
from app.agent.plan_variants import generate_plan_options
from app.agent.router import transaction_intent, order_status_reference
from app.decision.contracts import decision_context
from app.decision.gateway import dispatch_jev_shadow, resolve_jev_decision
from app.decision.shadow import resolve_authoritative_intent
from app.agent.prompts import ERROR_MESSAGES, PLAN_RESPONSE_TEMPLATES
from app.agent.session_state import get_session_state, save_session_state, validate_plan_snapshot, with_plan_snapshot
from app.observability.langfuse_client import LangfuseClient
from app.observability.local_tracer import elapsed_ms, log_observability_event, new_trace_id, now_ms
from app.rag.query_rewriter import rewrite_query, should_rewrite
from app.rag.retriever import RetrievalResult, retrieve_products, retrieve_products_with_evidence
from app.services.llm_service import settings
# Compatibility names remain available to existing agent extensions; actual
# chat transactions use the bound, idempotent service below.
from app.services.order_service import create_order_from_plan, save_order
from app.services.order_service import get_order, list_orders
from app.services.confirmed_transaction import create_confirmed_order, require_confirmed_order_for_payment, SnapshotInvalid
from app.tools.stripe_ai_tools import create_checkout_for_selected_plan
from app.services.caller_identity import require_caller
from app.agent.session_state import require_session_owner

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
    decision_label: str | None = None,
) -> str | None:
    """Determine response type from parsed intent and plan context.

    Priority:
      1) Explicit transaction commands → order/payment
      2) Search/browse + categories → product_results
      3) Plan signals (recommend/need/budget/multi+qty) → recommendation_plan
      4) Fallback: plan has items → recommendation_plan
    """
    lowered = message.lower()
    revision_intent = str(intent.get("revision_intent", "") or "")
    categories = intent.get("categories") or []
    budget = intent.get("budget")

    if decision_label == "order_status":
        return "order_status"
    transaction = transaction_intent(message)
    if transaction == "confirm_order":
        return "order"  # Preserve the public response schema.
    if transaction == "payment":
        return "payment"

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
    plan_id: str | None = None,
    plan_hash: str | None = None,
    plan_version: int | None = None,
    confirmation_id: str | None = None,
    user_id: str | None = None,
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
    caller = require_caller()
    require_session_owner(session_id, caller)
    user_id = caller.actor_id
    session_state = get_session_state(session_id)
    entry_transaction = transaction_intent(message) in {"confirm_order", "payment"}
    entry_order_status, status_reference = order_status_reference(message)
    status_order = None
    if previous_intent is None and session_state:
        previous_intent = session_state.get("parsed_intent")
    if previous_plan is None and session_state:
        previous_plan = session_state.get("recommended_plan")
    used_previous_context = bool(previous_intent or previous_plan)

    decision_contract = None
    block_for_missing_authority = False
    error_code = None
    snapshot_drift: list[str] | None = None
    transaction_gate_reason = None
    try:
        # Read requests never invoke the procurement parser or rewrite loop.
        intent = dict(previous_intent or {}) if entry_order_status else parse_purchase_request(message, previous_intent)
        if intent.get("response_language") in ("zh", "en"):
            language = intent["response_language"]
        tool_calls.append({"name": "readonly_order_status" if entry_order_status else "parse_purchase_request", "status": "success"})
        model_provider = str(intent.get("model_provider") or model_provider)
        model_name = str(intent.get("model_name") or model_name)
        used_mock_llm = bool(intent.get("used_mock_llm"))
        llm_error = intent.get("llm_error")

        baseline_decision = resolve_authoritative_intent(message, intent, None)
        decision_contract = resolve_jev_decision(
            text=message,
            fallback_label=baseline_decision.label,
            context={"previous_intent": previous_intent or {}, "has_previous_plan": bool(previous_plan)},
            cohort_key=session_id,
        )
        effective_label = decision_contract.label.value
        is_transactional = effective_label in {"confirm_order", "payment", "cancel", "order_status"}
        explicit_transaction = transaction_intent(message)
        original_snapshot_errors = []
        if entry_transaction and session_state:
            _, original_snapshot_errors = validate_plan_snapshot(session_id, plan_id, plan_hash, plan_version)
            if original_snapshot_errors:
                error_code = "PLAN_SNAPSHOT_INVALID"
                snapshot_drift = original_snapshot_errors
                transaction_gate_reason = "snapshot_drift"
        missing_server_snapshot = explicit_transaction in {"confirm_order", "payment"} and not session_state
        authority_safety_block = decision_contract.decision_source == "safety_block"
        unsupported_cancel = explicit_transaction == "cancel"
        unsupported_order_status = entry_order_status or effective_label == "order_status"
        if entry_order_status:
            if status_reference:
                candidate = get_order(status_reference)
                if candidate and candidate.get("owner_actor_id") == caller.actor_id:
                    status_order = candidate
            else:
                candidates = [o for o in list_orders() if o.get("owner_actor_id") == caller.actor_id
                              and (o.get("confirmation_binding") or {}).get("session_id") == session_id]
                if len(candidates) == 1:
                    status_order = candidates[0]
        uncertain_route = effective_label in {"clarify", "unknown"}
        has_retrieval_context = any((
            bool(intent.get("categories")),
            intent.get("budget") is not None,
            bool(intent.get("constraints")),
            bool(intent.get("preferences")),
            bool((previous_intent or {}).get("categories")),
        ))
        clarify_without_retrieval = uncertain_route and not has_retrieval_context
        block_for_missing_authority = any((
            missing_server_snapshot, authority_safety_block, unsupported_cancel,
            unsupported_order_status, clarify_without_retrieval,
            bool(original_snapshot_errors),
        ))
        retrieval_route_label = effective_label
        if uncertain_route:
            # An uncertain classifier result is not itself a reason to suppress
            # ordinary retrieval. Preserve contextual rewrite for follow-ups.
            retrieval_route_label = (
                "modify_plan"
                if previous_intent and previous_intent.get("categories")
                else "recommend"
            )

        # Query Rewrite: bridge multi-turn conversational wording and retrieval terms.
        rewrite_enabled = False
        if not entry_transaction and not is_transactional and not block_for_missing_authority:
            try:
                rewrite_enabled = should_rewrite(message, previous_intent, retrieval_route_label)
            except TypeError:
                rewrite_enabled = should_rewrite(message, previous_intent)
        if rewrite_enabled:
            try:
                rewritten = rewrite_query(message, previous_intent, route_label=retrieval_route_label)
            except TypeError:
                rewritten = rewrite_query(message, previous_intent)
            retrieval_query = rewritten if rewritten and rewritten != message else message
        else:
            retrieval_query = message

        # Confirm/payment/status/cancel requests use the previously displayed
        # snapshot. They must not silently retrieve and generate a replacement.
        if block_for_missing_authority:
            plan = (session_state or {}).get("recommended_plan") or {
                "items": [], "selected_items": [], "total_amount": 0,
                "budget_status": "unknown", "inventory_status": "unknown",
                "constraint_satisfaction": "needs_review",
            }
            retrieved_products = []
            retrieval_evidence = {
                "snapshot_reused": False,
                "transaction_block_reason": (
                    "plan_session_missing" if missing_server_snapshot
                    else "cancel_not_supported" if unsupported_cancel
                    else "order_status_lookup_unavailable" if unsupported_order_status
                    else "clarification_required" if clarify_without_retrieval
                    else decision_contract.fallback_reason
                ),
            }
            plan_options = []
            tool_calls.append({
                "name": "transaction_gate", "status": "blocked",
                "reason": retrieval_evidence["transaction_block_reason"],
            })
        elif (entry_transaction or is_transactional) and session_state:
            # The server-owned session snapshot is authoritative. A client
            # supplied previous_plan is never allowed to replace it.
            plan = session_state.get("recommended_plan") or {}
            retrieved_products = session_state.get("retrieved_products", [])
            retrieval_evidence = {"constraints_relaxed": bool(plan.get("constraints_relaxed")), "snapshot_reused": True}
            plan_options = []
        else:
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
            # Retrieval fallback is execution evidence, including for alternative plans.
            for candidate in [plan, *(option["plan"] for option in plan_options)]:
                candidate["constraints_relaxed"] = bool(
                    candidate.get("constraints_relaxed") or retrieval_evidence.get("constraints_relaxed")
                )
            tool_calls.append({"name": "generate_procurement_plan", "status": "success"})

        response_type = "clarify" if block_for_missing_authority else _determine_response_type(
            intent, plan, message, effective_label
        )
        if response_type is None and uncertain_route:
            response_type = "clarify"
        if entry_order_status:
            response_type = "order_status"
        # Audit-only Jev work is dispatched after the authoritative decision exists.
        # It never changes intent, response_type, plan, or transaction execution.
        dispatch_jev_shadow(
            text=message,
            trace_id=trace_id,
            authoritative_decision=resolve_authoritative_intent(message, intent, response_type),
        )

        if entry_order_status:
            if status_order:
                answer = (f"订单 #{status_order['order_id']} 状态：{status_order['status']}。" if language == "zh"
                          else f"Order #{status_order['order_id']} status: {status_order['status']}.")
            else:
                answer = ("未找到可查询的本人订单，请提供本人订单号。" if language == "zh"
                          else "No owned order is available. Please provide your order ID.")
            llm_timings = {"intent_parser_ms": None, "plan_explanation_ms": None}
        elif block_for_missing_authority:
            if original_snapshot_errors:
                answer = "方案已变化或确认信息缺失，请重新生成方案并再次确认。" if language == "zh" else "The plan changed or confirmation is missing. Display the plan and confirm it again."
            elif unsupported_cancel:
                answer = "当前暂不支持取消订单，请联系业务人员处理。" if language == "zh" else "Order cancellation is not available yet. Please contact the support team."
            elif unsupported_order_status:
                answer = "当前无法查询订单状态，请提供订单号并联系业务人员核实。" if language == "zh" else "Order status lookup is not available yet. Please provide the order ID and contact support."
            elif clarify_without_retrieval:
                answer = "我还不能确定你的需求，请补充品类、数量或希望调整的方案内容。" if language == "zh" else "I need a little more detail. Please specify the product category, quantity, or what you want changed in the plan."
            elif language == "zh":
                answer = "当前无法安全确认此操作，因为没有可验证的服务端方案或决策结果。请重新生成方案后再确认。"
            else:
                answer = "I can't safely confirm this action because there is no verifiable server-side plan or decision. Please generate a plan again before confirming."
            llm_timings = {"intent_parser_ms": intent.get("llm_latency_ms"), "plan_explanation_ms": None}
        elif response_type == "clarify":
            answer = "我还不能确定你的需求，请补充品类、数量或希望调整的方案内容。" if language == "zh" else "I need a little more detail. Please specify the product category, quantity, or what you want changed in the plan."
            llm_timings = {"intent_parser_ms": intent.get("llm_latency_ms"), "plan_explanation_ms": None}
        elif response_type == "product_results":
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
        elif entry_transaction:
            answer = "正在验证你确认的方案。" if language == "zh" else "Validating the plan you confirmed."
            llm_timings = {"intent_parser_ms": intent.get("llm_latency_ms"), "plan_explanation_ms": None}
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

    if decision_contract is None:
        baseline_decision = resolve_authoritative_intent(message, intent, response_type)
        decision_contract = resolve_jev_decision(text=message, fallback_label=baseline_decision.label, cohort_key=session_id)
    if error is None and not entry_transaction and not entry_order_status and not block_for_missing_authority and response_type != "clarify":
        registered = save_session_state(session_id, intent, plan, retrieved_products[:12], trace_id, plan_options)
        if registered:
            plan = registered["recommended_plan"]
            plan_options = registered["plan_options"]
        else:
            plan = with_plan_snapshot(plan, session_id, trace_id)
    decision_meta = decision_context(
        contract=decision_contract,
        transaction_gate=(
            "block" if block_for_missing_authority
            else "pass" if transaction_intent(message) != "recommend" else "block"
        ),
        plan_id=plan.get("plan_id"),
        plan_hash=plan.get("plan_hash"),
    )
    if error_code:
        decision_meta.update({"transaction_gate": "block", "error_code": error_code,
                              "snapshot_drift": snapshot_drift, "transaction_gate_reason": transaction_gate_reason})

    event = {
        "trace_id": trace_id, "session_id": session_id, "language": language,
        "user_query": message, "parsed_intent": intent,
        "retrieved_products": retrieved_products[:8], "retrieval_evidence": retrieval_evidence,
        "selected_products": plan.get("items", []), "final_answer": answer,
        "model_provider": model_provider, "model_name": model_name,
        "used_mock_llm": used_mock_llm, "llm_error": llm_error, "llm_timings": llm_timings,
        "used_previous_context": used_previous_context,
        **decision_meta,
        "previous_trace_id": session_state.get("trace_id") if session_state else None,
        "tool_calls": tool_calls, "latency_ms": elapsed_ms(start), "error": error,
    }
    log_observability_event(event)
    LangfuseClient().trace(**event)

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

    # Only explicit transaction commands may reach order/checkout side effects.
    order_id = status_order.get("order_id") if status_order else None
    order_status = status_order.get("status") if status_order else None
    checkout_url = None
    if (
        error is None
        and not block_for_missing_authority
        and response_type in ("order", "payment")
        and decision_contract.label.value in ("confirm_order", "payment")
        and transaction_intent(message) in ("confirm_order", "payment")
        and plan.get("items")
    ):
        try:
            if not confirmation_id:
                raise SnapshotInvalid(["confirmation_binding_invalid"])
            if response_type == "order":
                order = create_confirmed_order(session_id, plan_id, plan_hash, plan_version, confirmation_id, user_id)
            else:
                order = require_confirmed_order_for_payment(session_id, plan_id, plan_hash, plan_version, confirmation_id)
            order_id = order.get("order_id", "")
            order_status = order.get("status", "pending_payment")
            if response_type == "payment":
                checkout = create_checkout_for_selected_plan(plan_id=str(order["plan_id"]), order_id=order_id)
                checkout_url = checkout.get("checkout_url", "")
            if language == "zh":
                answer += "\n\n订单 #" + order_id + ("，正在跳转支付..." if checkout_url else " 已创建。")
            else:
                answer += "\n\nOrder #" + order_id + (". Redirecting to payment..." if checkout_url else " created.")
            tool_calls.append({"name": "auto_checkout", "status": "success", "order_id": order_id})
        except Exception as exc:
            error = str(exc)
            if isinstance(exc, SnapshotInvalid):
                error_code = "PLAN_SNAPSHOT_INVALID"
                snapshot_drift = exc.reasons
                transaction_gate_reason = "snapshot_drift"
            if error_code == "PLAN_SNAPSHOT_INVALID":
                drift_message = (
                    "方案已变化（价格、库存或配送条件可能更新）。为避免按旧信息下单，请重新生成方案并再次确认。"
                    if language == "zh"
                    else "The plan has changed (price, stock, or delivery details may have been updated). To avoid ordering from stale information, generate a new plan and confirm it again."
                )
                answer = f"{answer}\n\n{drift_message}".strip()
                decision_meta["transaction_gate"] = "block"
                decision_meta["transaction_gate_reason"] = transaction_gate_reason
                decision_meta["error_code"] = error_code
                decision_meta["snapshot_drift"] = snapshot_drift
                log_observability_event({
                    "event": "transaction_gate",
                    "trace_id": trace_id,
                    "session_id": session_id,
                    "decision_source": decision_contract.decision_source,
                    "transaction_gate": "block",
                    "transaction_gate_reason": transaction_gate_reason,
                    "error_code": error_code,
                    "snapshot_drift": snapshot_drift,
                    "plan_id": plan.get("plan_id"),
                    "plan_hash": plan.get("plan_hash"),
                })
            else:
                order_id = order_status = checkout_url = None
                error_code = "TRANSACTION_PRECONDITION_REQUIRED"
                transaction_gate_reason = "transaction_precondition_missing"
                decision_meta.update({"transaction_gate": "block", "error_code": error_code,
                                      "transaction_gate_reason": transaction_gate_reason})
                answer = ("请先确认并创建本人可付款订单；已支付或已取消的订单不能再次付款。" if language == "zh"
                          else "Please confirm and create an owned payable order first. Paid or cancelled orders cannot be paid again.")
                llm_error = _combine_llm_error(llm_error, error)
            tool_calls.append({"name": "auto_checkout", "status": "error", "error": error})

    return {
        "session_id": session_id, "parsed_intent": intent,
        "recommended_plan": plan, "plan_options": plan_options,
        "selected_plan_id": plan.get("plan_id"),
        "answer": answer, "trace_id": trace_id,
        "retrieved_products": retrieved_products[:12], "retrieval_evidence": retrieval_evidence,
        "model_provider": model_provider, "model_name": model_name,
        "used_mock_llm": used_mock_llm, "llm_error": llm_error, "llm_timings": llm_timings,
        "used_previous_context": used_previous_context,
        "previous_trace_id": session_state.get("trace_id") if session_state else None,
        "type": response_type, "products": products,
        "recommendation_plan": recommendation_plan, "actions": [],
        "order_id": order_id, "order_status": order_status, "checkout_url": checkout_url,
        "error_code": error_code,
        "snapshot_drift": snapshot_drift,
        "transaction_gate_reason": transaction_gate_reason,
        **decision_meta,
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
    product_line_count = len(items)
    unit_count = sum(int(item.get("quantity", 0) or 0) for item in items)

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
            f"已为您生成采购方案：共 {product_line_count} 条商品明细，合计 {unit_count} 件，"
            f"总金额 ${total_amount:.2f}{rating_str}。"
            f"预算：{budget_label}，库存：{inventory_label}，约束：{constraint_label}。"
        )
    else:
        summary = (
            f"I generated a procurement plan with {product_line_count} product lines, {unit_count} units in total, "
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
    if cats:
        cat_summaries = []
        if language == "zh":
            cat_summaries = [f"{cat} {sum(int(item.get('quantity', 0) or 0) for item in category_items)}件" for cat, category_items in sorted(cats.items())]
            parts.append("品类分布：" + " | ".join(cat_summaries))
        else:
            cat_summaries = [f"{cat}: {sum(int(item.get('quantity', 0) or 0) for item in category_items)} units" for cat, category_items in sorted(cats.items())]
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
