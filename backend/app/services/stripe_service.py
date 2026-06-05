from __future__ import annotations

import uuid

from app.core.config import get_settings


def create_stripe_checkout_session(
    order_id: str,
    amount: float,
    success_url: str | None = None,
    cancel_url: str | None = None,
) -> dict[str, str]:
    settings = get_settings()
    success_url = success_url or f"{settings.frontend_base_url}/payment/success?order_id={order_id}"
    cancel_url = cancel_url or f"{settings.frontend_base_url}/payment/cancel?order_id={order_id}"

    if settings.use_mock_payment or not settings.stripe_secret_key:
        return {
            "checkout_url": f"{success_url}&mock=true&session_id=mock_{uuid.uuid4().hex[:10]}",
            "session_id": f"mock_{uuid.uuid4().hex[:16]}",
            "provider": "mock",
            "status": "created",
        }

    import stripe

    stripe.api_key = settings.stripe_secret_key
    session = stripe.checkout.Session.create(
        mode="payment",
        success_url=success_url,
        cancel_url=cancel_url,
        line_items=[
            {
                "price_data": {
                    "currency": "usd",
                    "product_data": {"name": f"Procurement Order {order_id}"},
                    "unit_amount": int(round(amount * 100)),
                },
                "quantity": 1,
            }
        ],
        metadata={"order_id": order_id},
    )
    return {
        "checkout_url": session.url,
        "session_id": session.id,
        "provider": "stripe",
        "status": "created",
    }
