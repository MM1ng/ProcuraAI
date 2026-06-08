from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from app.core.config import get_settings
from app.schemas.payment import (
    CheckoutSessionRequest,
    CheckoutSessionResponse,
    StripeCheckoutRequest,
    StripeCheckoutResponse,
)
from app.services.payment_service import create_checkout
from app.services.stripe_payment_service import create_procurement_checkout_session, handle_stripe_webhook


router = APIRouter(prefix="/api/payments", tags=["payments"])


@router.get("/status")
def payment_status() -> dict[str, object]:
    settings = get_settings()
    use_mock = settings.use_mock_payment or not settings.stripe_secret_key
    return {
        "payment_provider": "mock" if use_mock else "stripe",
        "use_mock_payment": use_mock,
        "has_stripe_secret_key": bool(settings.stripe_secret_key),
    }


@router.post("/create-checkout-session", response_model=CheckoutSessionResponse)
def create_checkout_session(request: CheckoutSessionRequest) -> CheckoutSessionResponse:
    session = create_checkout(
        order_id=request.order_id,
        amount=request.amount,
        success_url=request.success_url,
        cancel_url=request.cancel_url,
    )
    return CheckoutSessionResponse(**session)


@router.post("/stripe/checkout", response_model=StripeCheckoutResponse)
def create_stripe_checkout(request: StripeCheckoutRequest) -> StripeCheckoutResponse:
    try:
        session = create_procurement_checkout_session(plan_id=request.plan_id, order_id=request.order_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return StripeCheckoutResponse(**session)


@router.post("/stripe/webhook")
async def stripe_signed_webhook(request: Request) -> dict:
    payload = await request.body()
    signature = request.headers.get("stripe-signature")
    try:
        return handle_stripe_webhook(payload, signature)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/webhook")
async def stripe_webhook(request: Request) -> dict:
    payload = await request.body()
    return {"received": True, "mode": "mock-safe", "payload_bytes": len(payload)}
