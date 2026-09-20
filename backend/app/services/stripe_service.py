from __future__ import annotations

from app.core.config import get_settings
from app.services.stripe_payment_service import create_procurement_checkout_session


def create_stripe_checkout_session(
    order_id: str,
    amount: float | None = None,
    success_url: str | None = None,
    cancel_url: str | None = None,
) -> dict[str, str]:
    """Deprecated adapter: only the persisted order determines checkout values."""
    session = create_procurement_checkout_session(plan_id=None, order_id=order_id)
    settings = get_settings()
    return {
        **session,
        "provider": "mock" if settings.use_mock_payment or not settings.stripe_secret_key else "stripe",
        "status": "created",
    }
