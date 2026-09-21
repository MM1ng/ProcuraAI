from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class OrderItemSelection(BaseModel):
    # Accept legacy payloads, but never retain their prices or product metadata.
    model_config = ConfigDict(extra="ignore")

    product_id: str = Field(min_length=1, strict=True)
    quantity: int = Field(gt=0, strict=True)


class OrderPlanSelection(BaseModel):
    model_config = ConfigDict(extra="ignore")

    items: list[OrderItemSelection] = Field(min_length=1)
    plan_option_id: str | None = None
    plan_id: str | None = None
    # A requested spending limit, not proof of approval or execution eligibility.
    budget: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    # Recommendation restrictions may only veto execution, never grant it.
    over_budget: bool | None = Field(default=None, strict=True)
    budget_status: str | None = None
    inventory_status: str | None = None
    constraint_satisfaction: str | None = None
    missing_categories: list[str] = Field(default_factory=list)
    constraints_relaxed: bool = Field(default=False, strict=True)
    selectable: bool | None = Field(default=None, strict=True)


class OrderCreateRequest(BaseModel):
    user_id: str = "demo-user"
    plan: OrderPlanSelection


class OrderResponse(BaseModel):
    order_id: str
    user_id: str
    plan_id: str | None = None
    procurement_plan: dict[str, Any] | None = None
    order_items: list[dict[str, Any]] = Field(default_factory=list)
    total_amount: float
    status: str
    stripe_session_id: str | None = None
    processed_payment_event_ids: list[str] = Field(default_factory=list)
    created_at: str
