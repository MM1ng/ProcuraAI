from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class CheckoutSessionRequest(BaseModel):
    # Legacy amount/plan/redirect fields may be sent but are never trusted.
    model_config = ConfigDict(extra="ignore")

    order_id: str = Field(min_length=1, strict=True)


class CheckoutSessionResponse(BaseModel):
    checkout_url: str
    session_id: str
    provider: str | None = None
    status: str | None = None


class StripeCheckoutRequest(CheckoutSessionRequest):
    pass


class StripeCheckoutResponse(BaseModel):
    checkout_url: str
    session_id: str
