from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str
    session_id: str = "demo-session-001"
    language: Literal["en", "zh", "fr"] = "en"
    previous_intent: dict[str, Any] | None = None
    previous_plan: dict[str, Any] | None = None


class ProcurementPlanRequest(BaseModel):
    message: str | None = None
    parsed_intent: dict[str, Any] | None = None
    session_id: str = "demo-session-001"
    language: Literal["en", "zh", "fr"] = "en"


class QuickOptimizationRequest(BaseModel):
    action: Literal["make_cheaper", "improve_quality", "faster_delivery", "prefer_dell", "regenerate"]
    session_id: str = "demo-session-001"
    language: Literal["en", "zh", "fr"] = "en"
    parsed_intent: dict[str, Any]
    current_plan: dict[str, Any]
    message: str | None = None


class ChatResponse(BaseModel):
    session_id: str
    parsed_intent: dict[str, Any]
    recommended_plan: dict[str, Any]
    plan_options: list[dict[str, Any]] = Field(default_factory=list)
    selected_plan_id: str | None = None
    answer: str
    trace_id: str
    retrieved_products: list[dict[str, Any]] = Field(default_factory=list)
    retrieval_evidence: dict[str, Any] = Field(default_factory=dict)
    model_provider: str
    model_name: str
    used_mock_llm: bool
    llm_error: str | None = None
    used_previous_context: bool = False
    previous_trace_id: str | None = None
