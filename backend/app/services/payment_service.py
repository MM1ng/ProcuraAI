from __future__ import annotations

from app.services.stripe_service import create_stripe_checkout_session


def create_checkout(order_id: str, amount: float, success_url: str | None = None, cancel_url: str | None = None) -> dict[str, str]:
    return create_stripe_checkout_session(order_id, amount, success_url, cancel_url)
