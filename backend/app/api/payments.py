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


@router.post("/mock-success")
def mock_payment_success(payload: dict) -> dict:
    """Idempotent mock payment success endpoint.

    Sets order status to 'paid'. If already paid, returns current status.
    """
    order_id = payload.get("order_id")
    if not order_id:
        raise HTTPException(status_code=400, detail="order_id is required")

    order = get_order(order_id)
    if not order:
        raise HTTPException(status_code=404, detail=f"Order {order_id} not found")

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
    """Confirm payment by order_id or session_id.

    Used by the payment success page when the user is redirected back
    from Stripe Checkout (real or mock). This handles the local-dev case
    where no Stripe webhook reaches the backend.
    """
    order_id = payload.get("order_id")
    session_id = payload.get("session_id")

    if not order_id and not session_id:
        raise HTTPException(status_code=400, detail="order_id or session_id is required")

    order = None
    if order_id:
        order = get_order(order_id)
    elif session_id:
        order = get_order_by_stripe_session_id(session_id)

    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    if order.get("status") == "paid":
        return {
            "order_id": order.get("order_id"),
            "status": "paid",
            "message": "Order was already paid",
        }

    updated = update_order(order.get("order_id"), {"status": "paid"})
    return {
        "order_id": updated.get("order_id"),
        "status": "paid",
        "message": "Payment confirmed successfully",
        "order": updated,
    }
