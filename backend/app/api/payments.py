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
from app.services.stripe_payment_service import (
    PaymentProviderError,
    confirm_order_payment,
    create_procurement_checkout_session,
    handle_stripe_webhook,
)
from app.services.order_service import get_order, get_order_by_stripe_session_id, update_order


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


@router.post("/create-checkout-session", response_model=CheckoutSessionResponse, deprecated=True)
def create_checkout_session(request: CheckoutSessionRequest) -> CheckoutSessionResponse:
    try:
        session = create_checkout(order_id=request.order_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return CheckoutSessionResponse(**session)


@router.post("/stripe/checkout", response_model=StripeCheckoutResponse)
def create_stripe_checkout(request: StripeCheckoutRequest) -> StripeCheckoutResponse:
    try:
        session = create_procurement_checkout_session(plan_id=None, order_id=request.order_id)
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


@router.post("/mock-success")
def mock_payment_success(payload: dict) -> dict:
    """Explicitly enabled local-only mock confirmation; never confirm real sessions."""
    settings = get_settings()
    if (
        settings.app_env not in {"development", "test"}
        or not settings.allow_mock_payment
        or not (settings.use_mock_payment or not settings.stripe_secret_key)
    ):
        raise HTTPException(status_code=403, detail="Mock payment confirmation is disabled.")
    order_id = payload.get("order_id")
    if not order_id:
        raise HTTPException(status_code=400, detail="order_id is required")

    order = get_order(order_id)
    if not order:
        raise HTTPException(status_code=404, detail=f"Order {order_id} not found")

    stored_session_id = order.get("stripe_session_id")
    if stored_session_id and not str(stored_session_id).startswith("mock_"):
        raise HTTPException(status_code=403, detail="Real checkout sessions require Stripe verification.")

    if order.get("status") == "paid":
        return {
            "order_id": order_id,
            "status": "paid",
            "message": "Order was already paid (idempotent)",
        }

    updated = update_order(order_id, {"status": "paid"})
    return {
        "order_id": order_id,
        "status": "paid",
        "message": "Payment successful. Your order has been created.",
        "order": updated,
    }


@router.post("/confirm")
def confirm_payment(payload: dict) -> dict:
    """Look up the order, then verify its bound checkout session with Stripe."""
    order_id = payload.get("order_id")
    session_id = payload.get("session_id")

    if any(value is not None and (not isinstance(value, str) or not value.strip()) for value in (order_id, session_id)):
        raise HTTPException(status_code=400, detail="order_id and session_id must be non-empty strings")
    if not order_id and not session_id:
        raise HTTPException(status_code=400, detail="order_id or session_id is required")

    order = None
    if order_id:
        order = get_order(order_id)
    elif session_id:
        order = get_order_by_stripe_session_id(session_id)

    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    try:
        updated = confirm_order_payment(order, session_id=session_id)
    except PaymentProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "order_id": updated.get("order_id"),
        "status": updated.get("status"),
        "message": "Order was already paid" if order.get("status") == "paid" else "Payment verified with Stripe",
        "order": updated,
    }
