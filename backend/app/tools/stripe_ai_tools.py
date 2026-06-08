from __future__ import annotations

from app.services.stripe_payment_service import create_procurement_checkout_session


def create_checkout_for_selected_plan(plan_id: str, order_id: str) -> dict[str, str]:
    """ProcuraAI controlled Stripe AI tool for creating a Checkout Session.

    This tool is intentionally a thin, guarded wrapper around the production
    Stripe Checkout service. It does not call Stripe directly and does not trust
    model- or frontend-provided payment amounts; backend order, plan, budget,
    selectability, and item totals are validated by
    create_procurement_checkout_session.
    """
    return create_procurement_checkout_session(plan_id=plan_id, order_id=order_id)
