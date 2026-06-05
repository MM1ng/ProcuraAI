from __future__ import annotations

from fastapi import APIRouter

from app.agent.plan_generator import generate_procurement_plan
from app.agent.procurement_agent import run_procurement_agent
from app.rag.retriever import retrieve_products
from app.schemas.chat import ChatRequest, ChatResponse, ProcurementPlanRequest


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
