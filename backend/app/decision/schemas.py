from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class IntentLabel(str, Enum):
    RECOMMEND = "recommend"
    MODIFY_PLAN = "modify_plan"
    COMPARE_PLAN = "compare_plan"
    EXPLAIN_PLAN = "explain_plan"
    CONFIRM_ORDER = "confirm_order"
    PAYMENT = "payment"
    ORDER_STATUS = "order_status"
    CLARIFY = "clarify"


class DecisionResult(BaseModel):
    label: IntentLabel
    confidence: float | None = None
    probabilities: dict[str, float] | None = None
    provider: str
    model: str | None = None
    latency_ms: float
    fallback_used: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class IntentGoldCase(BaseModel):
    id: str
    text: str
    label: IntentLabel
    language: str
    context: dict[str, Any] = Field(default_factory=dict)
