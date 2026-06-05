from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class OrderCreateRequest(BaseModel):
    user_id: str = "demo-user"
    plan: dict[str, Any]


class OrderResponse(BaseModel):
    order_id: str
    user_id: str
    order_items: list[dict[str, Any]] = Field(default_factory=list)
    total_amount: float
    status: str
    stripe_session_id: str | None = None
    created_at: str
