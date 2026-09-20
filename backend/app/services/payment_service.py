from __future__ import annotations

from app.services.stripe_service import create_stripe_checkout_session


def create_checkout(order_id: str, amount: float | None = None, success_url: str | None = None, cancel_url: str | None = None) -> dict[str, str]:
    """Compatibility entrypoint; legacy amount/redirect arguments are ignored."""
    return create_stripe_checkout_session(order_id=order_id)
