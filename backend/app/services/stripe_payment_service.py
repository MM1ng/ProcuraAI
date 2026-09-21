from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
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


def _load_payable_plan(plan_id: str | None, order_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    order = get_order(order_id)
    if not order:
        raise ValueError("Order not found.")
    if order.get("status") not in PAYABLE_ORDER_STATUSES:
        raise ValueError("Order is not payable.")

    plan = order.get("procurement_plan")
    if not isinstance(plan, dict) or not plan:
        raise ValueError("Plan not found.")
    if plan_id is not None and _plan_id(plan) != plan_id:
        raise ValueError("Plan not found.")
    if (
        plan.get("selectable") is False
        or plan.get("over_budget") is True
        or plan.get("status") not in PAYABLE_PLAN_STATUSES
    ):
        raise ValueError(OVER_BUDGET_ERROR)
    return order, plan


def _amount_to_cents(value: Any) -> int:
    try:
        amount = Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        if not amount.is_finite() or amount <= 0:
            raise ValueError("Invalid persisted order amount.")
    except InvalidOperation as exc:
        raise ValueError("Invalid persisted order amount.") from exc
    return int((amount * 100).to_integral_value(rounding=ROUND_HALF_UP))


def _checkout_amount(order: dict[str, Any]) -> tuple[int, list[dict[str, Any]]]:
    """Use the Task 02 order snapshot, never a request or a reconstructed plan."""
    total_cents = _amount_to_cents(order.get("total_amount"))
    line_items = [_line_item(item) for item in order.get("order_items", []) or []]
    line_total = sum(item["price_data"]["unit_amount"] * item["quantity"] for item in line_items)
    if line_total != total_cents:
        raise ValueError("Order total does not match persisted order items.")
    return total_cents, line_items


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


def create_procurement_checkout_session(plan_id: str | None, order_id: str) -> dict[str, str]:
    order, plan = _load_payable_plan(plan_id, order_id)
    plan_id = _plan_id(plan)
    settings = get_settings()
    total_cents, line_items = _checkout_amount(order)
    total_amount = Decimal(total_cents) / 100
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
        update_order(order_id, {"stripe_session_id": session_id})
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
        line_items=line_items,
        metadata=metadata,
        payment_intent_data={"metadata": metadata},
        client_reference_id=order_id,
        idempotency_key=f"procuraai-checkout-{order_id}-{plan_id}",
    )
    update_order(order_id, {"stripe_session_id": session.id})
    return {"checkout_url": session.url, "session_id": session.id}


class PaymentProviderError(RuntimeError):
    """Stripe confirmation could not be verified; callers must not mark paid."""


def confirm_order_payment(order: dict[str, Any], session_id: str | None = None) -> dict[str, Any]:
    """Confirm an existing order using only its server-bound Stripe session."""
    stored_session_id = order.get("stripe_session_id")
    if session_id is not None and session_id != stored_session_id:
        raise ValueError("Checkout session does not match this order.")
    if order.get("status") == "paid":
        return order
    if not isinstance(stored_session_id, str) or not stored_session_id or stored_session_id.startswith("mock_"):
        raise ValueError("Order has no real Stripe checkout session.")

    settings = get_settings()
    if not settings.stripe_secret_key:
        raise PaymentProviderError("Stripe payment verification is unavailable.")
    try:
        session = _stripe_module().checkout.Session.retrieve(
            stored_session_id, api_key=settings.stripe_secret_key,
        )
        # Current Stripe SDK objects are not dictionaries; support both SDK and test responses.
        if not isinstance(session, dict):
            session = session.to_dict()
        if not isinstance(session, dict):
            raise TypeError("Invalid Stripe session response")
    except Exception as exc:
        raise PaymentProviderError("Unable to verify payment with Stripe.") from exc

    if session.get("id") != stored_session_id:
        raise ValueError("Stripe returned a different checkout session.")
    if session.get("payment_status") != "paid":
        raise ValueError("Stripe checkout session is not paid.")
    metadata = session.get("metadata")
    if metadata is not None and not isinstance(metadata, dict):
        raise ValueError("Invalid Stripe checkout metadata.")
    metadata_order_id = (metadata or {}).get("order_id")
    client_reference_id = session.get("client_reference_id")
    for provider_order_id in (metadata_order_id, client_reference_id):
        if provider_order_id is not None and provider_order_id != order["order_id"]:
            raise ValueError("Stripe checkout session belongs to a different order.")
    if "amount_total" in session:
        amount_total = session["amount_total"]
        if type(amount_total) is not int or amount_total != _amount_to_cents(order.get("total_amount")):
            raise ValueError("Stripe payment amount does not match the order.")
    if "currency" in session and session["currency"] != "usd":
        raise ValueError("Stripe payment currency does not match the order.")

    updated = update_order(order["order_id"], {"status": "paid"})
    if updated is None:
        raise ValueError("Order no longer exists.")
    return updated


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
