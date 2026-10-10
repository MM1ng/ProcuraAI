from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, ConfigDict


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message: str
    session_id: str
    language: Literal["en", "zh"] = "en"
    previous_intent: dict[str, Any] | None = None
    previous_plan: dict[str, Any] | None = None
    plan_id: str | None = None
    plan_hash: str | None = None
    plan_version: int | None = Field(default=None, strict=True, gt=0)
    confirmation_id: str | None = None


class PlanBindingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    session_id: str
    plan_id: str
    plan_hash: str
    plan_version: int = Field(strict=True, gt=0)


class PlanSelectRequest(PlanBindingRequest):
    selected_plan_id: str
    selected_plan_hash: str
    selected_plan_version: int = Field(strict=True, gt=0)


class ProcurementPlanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message: str | None = None
    parsed_intent: dict[str, Any] | None = None
    session_id: str
    language: Literal["en", "zh"] = "en"


class QuickOptimizationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["make_cheaper", "improve_quality", "faster_delivery", "prefer_dell", "regenerate"]
    session_id: str
    language: Literal["en", "zh"] = "en"
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
    type: str | None = None
    products: list[dict[str, Any]] | None = None
    recommendation_plan: dict[str, Any] | None = None
    actions: list[dict[str, Any]] | None = None
    order_id: str | None = None
    order_status: str | None = None
    checkout_url: str | None = None
    error_code: str | None = None
    snapshot_drift: list[str] | None = None
    transaction_gate_reason: str | None = None
