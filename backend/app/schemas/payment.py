from __future__ import annotations

from pydantic import BaseModel


class CheckoutSessionRequest(BaseModel):
    order_id: str
    amount: float
    success_url: str | None = None
    cancel_url: str | None = None


class CheckoutSessionResponse(BaseModel):
    checkout_url: str
    session_id: str
    provider: str | None = None
    status: str | None = None


class StripeCheckoutRequest(BaseModel):
    plan_id: str
    order_id: str


class StripeCheckoutResponse(BaseModel):
    checkout_url: str
    session_id: str
