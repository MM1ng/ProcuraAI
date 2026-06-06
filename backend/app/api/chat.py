from __future__ import annotations

from fastapi import APIRouter

from typing import Any

from app.agent.plan_generator import generate_procurement_plan
from app.agent.plan_variants import generate_plan_options
from app.agent.procurement_agent import run_procurement_agent
from app.observability.local_tracer import new_trace_id
from app.rag.retriever import retrieve_products
from app.schemas.chat import ChatRequest, ChatResponse, ProcurementPlanRequest, QuickOptimizationRequest
from app.services.llm_service import settings


router = APIRouter(prefix="/api", tags=["agent"])


@router.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    result = run_procurement_agent(
        request.message,
        request.session_id,
        previous_intent=request.previous_intent,
        previous_plan=request.previous_plan,
        language=request.language,
    )
    return ChatResponse.model_validate(result)


def _products_from_plan(plan: dict[str, Any]) -> list[dict[str, Any]]:
    products: list[dict[str, Any]] = []
    for item in plan.get("items", []) or []:
        product = dict(item)
        product["price"] = product.get("unit_price", product.get("price", 0))
        products.append(product)
    return products


def _option_for_action(action: str, plan_options: list[dict[str, Any]]) -> dict[str, Any] | None:
    strategy_by_action = {
        "make_cheaper": "cost_optimized",
        "improve_quality": "premium",
        "faster_delivery": "balanced",
        "regenerate": "balanced",
    }
    strategy = strategy_by_action.get(action)
    return next((option for option in plan_options if option.get("strategy") == strategy), None)


def _answer_for_optimization(action: str, plan: dict[str, Any]) -> str:
    label_by_action = {
        "make_cheaper": "Made the current plan cheaper where matching alternatives were available.",
        "improve_quality": "Improved quality by prioritizing higher-rated products.",
        "faster_delivery": "Optimized the plan for faster delivery.",
        "prefer_dell": "Re-generated the plan with a Dell preference where matching catalog items were available.",
        "regenerate": "Re-generated the procurement plan from the current understanding.",
    }
    return f"{label_by_action.get(action, 'Updated the procurement plan')} Total amount: ${float(plan.get('total_amount', 0) or 0):.2f}."


@router.post("/chat/optimize", response_model=ChatResponse)
def quick_optimize(request: QuickOptimizationRequest) -> ChatResponse:
    intent = dict(request.parsed_intent)
    intent["raw_message"] = request.message or intent.get("raw_message") or request.action
    if request.action == "make_cheaper":
        intent["need_cheaper_plan"] = True
        intent["revision_intent"] = "cheaper"
    elif request.action == "prefer_dell":
        intent["replacement_brand"] = "Dell"

    retrieved_products = retrieve_products(str(intent.get("raw_message") or request.action), intent, top_k=30)
    if not retrieved_products:
        retrieved_products = _products_from_plan(request.current_plan)

    candidate_products = retrieved_products
    if request.action == "prefer_dell":
        dell_products = [
            product for product in retrieved_products if str(product.get("brand", "")).lower() == "dell"
        ]
        if dell_products:
            candidate_products = dell_products

    plan_options = generate_plan_options(candidate_products, intent)
    selected_option = _option_for_action(request.action, plan_options)
    if selected_option:
        plan = selected_option["plan"]
    elif request.action == "make_cheaper":
        plan = generate_procurement_plan(candidate_products, intent, previous_plan=request.current_plan)
        plan["plan_option_id"] = "quick_make_cheaper"
        plan["plan_strategy"] = "cost_optimized"
    else:
        plan = generate_procurement_plan(candidate_products, intent, previous_plan=request.current_plan)
        plan["plan_option_id"] = f"quick_{request.action}"
        plan["plan_strategy"] = request.action

    if request.current_plan.get("total_amount") is not None and plan.get("previous_total_amount") is None:
        previous_total = round(float(request.current_plan.get("total_amount") or 0), 2)
        plan["previous_total_amount"] = previous_total
        plan["savings_amount"] = round(previous_total - float(plan.get("total_amount", 0) or 0), 2)

    if plan_options and not any(option.get("id") == plan.get("plan_option_id") for option in plan_options):
        plan_options = [
            {
                "id": str(plan.get("plan_option_id")),
                "name": "Quick Plan",
                "strategy": str(plan.get("plan_strategy")),
                "description": request.action.replace("_", " ").title(),
                "plan": plan,
            },
            *plan_options,
        ]

    trace_id = new_trace_id()
    answer = _answer_for_optimization(request.action, plan)
    plan["recommendation_reason"] = answer
    plan["recommendation_summary"] = answer
    return ChatResponse.model_validate(
        {
            "session_id": request.session_id,
            "parsed_intent": intent,
            "recommended_plan": plan,
            "plan_options": plan_options,
            "selected_plan_id": plan.get("plan_option_id"),
            "answer": answer,
            "trace_id": trace_id,
            "retrieved_products": retrieved_products[:12],
            "model_provider": "quick_action",
            "model_name": settings.QWEN_MODEL,
            "used_mock_llm": True,
            "llm_error": None,
            "used_previous_context": True,
            "previous_trace_id": None,
        }
    )


@router.post("/procurement/plan")
def procurement_plan(request: ProcurementPlanRequest) -> dict:
    if request.parsed_intent:
        intent = request.parsed_intent
        message = request.message or intent.get("raw_message", "procurement plan")
        products = retrieve_products(message, intent, top_k=30)
        return {
            "session_id": request.session_id,
            "parsed_intent": intent,
            "recommended_plan": generate_procurement_plan(products, intent),
            "retrieved_products": products[:12],
        }
    message = request.message or "Recommend office equipment for a team of 10 people."
    result = run_procurement_agent(message, request.session_id, language=request.language)
    return result
