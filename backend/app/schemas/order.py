from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class OrderCreateRequest(BaseModel):
    user_id: str = "demo-user"
    plan: dict[str, Any]


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
