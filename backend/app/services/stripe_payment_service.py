from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Any
import uuid
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from app.core.config import get_settings
from app.services.order_service import get_order, get_order_by_stripe_session_id, mark_payment_event_processed, update_order


OVER_BUDGET_ERROR = "Over-budget plans cannot be paid directly."
PAYABLE_ORDER_STATUSES = {"draft", "pending_payment"}
PAYABLE_PLAN_STATUSES = {"within_budget", "no_budget_provided"}
EVENT_STATUS_BY_TYPE = {
    "checkout.session.completed": "paid",
    "checkout.session.expired": "expired",
    "payment_intent.payment_failed": "payment_failed",
}


def _stripe_module():
    import stripe

    return stripe


def _construct_event(payload: bytes, signature: str, secret: str) -> dict[str, Any]:
    stripe = _stripe_module()
    return stripe.Webhook.construct_event(payload, signature, secret)


def _plan_id(plan: dict[str, Any]) -> str:
    return str(plan.get("plan_option_id") or plan.get("plan_id") or "")


def _load_payable_plan(plan_id: str, order_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    order = get_order(order_id)
    if not order:
        raise ValueError("Order not found.")
    if order.get("status") not in PAYABLE_ORDER_STATUSES:
        raise ValueError("Order is not payable.")

    plan = order.get("procurement_plan")
    if not isinstance(plan, dict) or not plan:
        raise ValueError("Plan not found.")
    if _plan_id(plan) != plan_id:
        raise ValueError("Plan not found.")
    if (
        plan.get("selectable") is False
        or plan.get("over_budget") is True
        or plan.get("status") not in PAYABLE_PLAN_STATUSES
    ):
        raise ValueError(OVER_BUDGET_ERROR)
    return order, plan


def _amount_to_cents(value: Any) -> int:
    amount = Decimal(str(value or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return int((amount * 100).to_integral_value(rounding=ROUND_HALF_UP))


def _recalculated_total(plan: dict[str, Any]) -> Decimal:
    total = Decimal("0.00")
    for item in plan.get("items", []) or []:
        unit_price = Decimal(str(item.get("unit_price", item.get("price", 0)) or 0))
        quantity = Decimal(str(int(item.get("quantity", 0) or 0)))
        total += unit_price * quantity
    return total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _line_item(item: dict[str, Any]) -> dict[str, Any]:
    name = str(item.get("name") or "Procurement item")
    category = str(item.get("category") or "")
    supplier = str(item.get("supplier") or "")
    return {
        "price_data": {
            "currency": "usd",
            "product_data": {
                "name": name,
                "metadata": {
                    "category": category,
                    "supplier": supplier,
                    "product_id": str(item.get("product_id") or ""),
                },
            },
            "unit_amount": _amount_to_cents(item.get("unit_price", item.get("price", 0))),
        },
        "quantity": int(item.get("quantity", 0) or 0),
    }


def _url_with_params(url: str, params: dict[str, str]) -> str:
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query.update(params)
    encoded_query = urlencode(query).replace("%7B", "{").replace("%7D", "}")
    return urlunsplit((parts.scheme, parts.netloc, parts.path, encoded_query, parts.fragment))


def create_procurement_checkout_session(plan_id: str, order_id: str) -> dict[str, str]:
    order, plan = _load_payable_plan(plan_id, order_id)
    settings = get_settings()
    total_amount = _recalculated_total(plan)
    metadata = {
        "order_id": order_id,
        "plan_id": plan_id,
        "total_amount": f"{total_amount:.2f}",
        "source": "procuraai",
    }
    success_base_url = settings.stripe_success_url or f"{settings.frontend_base_url}/payment/success"
    success_url = _url_with_params(success_base_url, {"order_id": order_id})
    cancel_url = settings.stripe_cancel_url or f"{settings.frontend_base_url}/payment/cancel?order_id={order_id}"

    if settings.use_mock_payment or not settings.stripe_secret_key:
        session_id = f"mock_{uuid.uuid4().hex[:16]}"
        update_order(order_id, {"stripe_session_id": session_id, "total_amount": float(total_amount)})
        return {
            "checkout_url": _url_with_params(success_url, {"mock": "true", "session_id": session_id}),
            "session_id": session_id,
        }

    if not settings.stripe_secret_key.startswith("sk_test_"):
        raise ValueError("Stripe checkout requires a test mode secret key.")

    stripe = _stripe_module()
    stripe.api_key = settings.stripe_secret_key
    session = stripe.checkout.Session.create(
        mode="payment",
        success_url=_url_with_params(success_url, {"session_id": "{CHECKOUT_SESSION_ID}"}),
        cancel_url=cancel_url,
        line_items=[_line_item(item) for item in plan.get("items", []) or []],
        metadata=metadata,
        payment_intent_data={"metadata": metadata},
        client_reference_id=order_id,
        idempotency_key=f"procuraai-checkout-{order_id}-{plan_id}",
    )
    update_order(order_id, {"stripe_session_id": session.id, "total_amount": float(total_amount)})
    return {"checkout_url": session.url, "session_id": session.id}


def handle_stripe_webhook(payload: bytes, signature: str | None) -> dict[str, Any]:
    settings = get_settings()
    if not settings.stripe_webhook_secret:
        raise ValueError("Stripe webhook secret is not configured.")
    if not signature:
        raise ValueError("Missing Stripe signature.")

    event = _construct_event(payload, signature, settings.stripe_webhook_secret)
    event_type = str(event.get("type") or "")
    status = EVENT_STATUS_BY_TYPE.get(event_type)
    if not status:
        return {"received": True, "ignored": True}

    event_object = (event.get("data") or {}).get("object") or {}
    metadata = event_object.get("metadata") or {}
    order_id = metadata.get("order_id") or event_object.get("client_reference_id")
    if not order_id and event_object.get("id"):
        order = get_order_by_stripe_session_id(str(event_object.get("id")))
        order_id = order.get("order_id") if order else None
    if not order_id:
        raise ValueError("Webhook event missing order_id metadata.")

    order = mark_payment_event_processed(str(order_id), event.get("id"), status)
    if not order:
        raise ValueError("Order not found.")
    return {"received": True, "order_id": str(order_id), "status": order.get("status")}
