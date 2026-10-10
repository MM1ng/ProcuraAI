from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any
import uuid
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from app.core.config import get_settings
from app.services.order_service import get_order, get_order_by_stripe_session_id, mark_payment_event_processed, update_order
from app.services.plan_execution_guard import PlanExecutionGuard
from app.services.transaction_lock import transaction_locked
from app.services.caller_identity import require_owner, VERIFIED_PROVIDER_EVENT, ORIGIN
from app.services.confirmed_transaction import validate_order_confirmation


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
    try:
        event = stripe.Webhook.construct_event(payload, signature, secret)
        if not isinstance(event, dict):
            event = event.to_dict()
        if not isinstance(event, dict):
            raise TypeError("Invalid provider event")
        return event
    except Exception as exc:
        raise ValueError("Invalid or unverifiable Stripe signature.") from exc


def _plan_id(plan: dict[str, Any]) -> str:
    return str(plan.get("plan_id") or plan.get("plan_option_id") or "")


def _load_payable_plan(plan_id: str | None, order_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    order = get_order(order_id)
    if not order:
        raise ValueError("Order not found.")
    require_owner(order)
    if order.get("status") not in PAYABLE_ORDER_STATUSES:
        raise ValueError("Order is not payable.")
    validate_order_confirmation(order)

    plan = order.get("procurement_plan")
    if not isinstance(plan, dict) or not plan:
        raise ValueError("Plan not found.")
    if plan_id is not None and _plan_id(plan) != plan_id:
        raise ValueError("Plan not found.")
    PlanExecutionGuard.require_executable(plan)
    if plan.get("status") not in PAYABLE_PLAN_STATUSES:
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


@transaction_locked
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
    success_base_url = settings.stripe_success_url or f"{ORIGIN}/payment/success"
    success_url = _url_with_params(success_base_url, {"order_id": order_id})
    cancel_url = settings.stripe_cancel_url or f"{ORIGIN}/payment/cancel?order_id={order_id}"
    for return_url in (success_base_url, cancel_url):
        parsed = urlsplit(return_url)
        if f"{parsed.scheme}://{parsed.netloc}" != ORIGIN:
            raise ValueError("Payment return requires the configured loopback origin.")

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


@transaction_locked
def confirm_order_payment(order: dict[str, Any], session_id: str | None = None) -> dict[str, Any]:
    """Confirm an existing order using only its server-bound Stripe session."""
    require_owner(order)
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
    if not (metadata_order_id or client_reference_id):
        raise ValueError("Stripe checkout is missing its order reference.")
    for provider_order_id in (metadata_order_id, client_reference_id):
        if provider_order_id is not None and provider_order_id != order["order_id"]:
            raise ValueError("Stripe checkout session belongs to a different order.")
    amount_total = session.get("amount_total")
    if type(amount_total) is not int or amount_total != _amount_to_cents(order.get("total_amount")):
        raise ValueError("Stripe payment amount does not match the order.")
    if session.get("currency") != "usd":
        raise ValueError("Stripe payment currency does not match the order.")

    updated = update_order(order["order_id"], {"status": "paid"})
    if updated is None:
        raise ValueError("Order no longer exists.")
    return updated


@transaction_locked
def handle_stripe_webhook(payload: bytes, signature: str | None) -> dict[str, Any]:
    settings = get_settings()
    if not settings.stripe_webhook_secret:
        raise ValueError("Stripe webhook secret is not configured.")
    if not signature:
        raise ValueError("Missing Stripe signature.")

    event = _construct_event(payload, signature, settings.stripe_webhook_secret)
    event_type = str(event.get("type") or "")
    status = EVENT_STATUS_BY_TYPE.get(event_type)
    if not status or event_type == "payment_intent.payment_failed":
        return {"received": True, "ignored": True}

    data = event.get("data")
    if not isinstance(data, dict):
        raise ValueError("Invalid checkout evidence.")
    event_object = data.get("object") or {}
    if not isinstance(event_object, dict):
        raise ValueError("Invalid checkout evidence.")
    metadata = event_object.get("metadata") or {}
    if not isinstance(event_object, dict) or not isinstance(metadata, dict):
        raise ValueError("Invalid checkout evidence.")
    if not isinstance(event.get("id"), str) or not event["id"]:
        raise ValueError("Missing event ID.")
    order_id = metadata.get("order_id") or event_object.get("client_reference_id")
    if not order_id:
        raise ValueError("Webhook event missing order_id metadata.")

    from app.services.order_service import get_order
    stored = get_order(str(order_id))
    if not stored or not stored.get("owner_actor_id"):
        raise ValueError("Webhook order has no verified owner.")
    checkout_id = stored.get("stripe_session_id")
    if not isinstance(checkout_id, str) or not checkout_id or checkout_id.startswith("mock_") or checkout_id != event_object.get("id"):
        raise ValueError("Webhook checkout binding mismatch.")
    for reference in (metadata.get("order_id"), event_object.get("client_reference_id")):
        if reference is not None and reference != stored["order_id"]:
            raise ValueError("Webhook order reference mismatch.")
    if event_type == "checkout.session.completed":
        if event_object.get("payment_status") != "paid":
            return {"received": True, "ignored": True}
        if type(event_object.get("amount_total")) is not int or event_object["amount_total"] != _amount_to_cents(stored.get("total_amount")):
            raise ValueError("Webhook amount mismatch.")
        if event_object.get("currency") != "usd":
            raise ValueError("Webhook currency mismatch.")
    token = VERIFIED_PROVIDER_EVENT.set(True)
    try:
        order = mark_payment_event_processed(str(order_id), event.get("id"), status)
    finally:
        VERIFIED_PROVIDER_EVENT.reset(token)
    if not order:
        raise ValueError("Order not found.")
    return {"received": True, "order_id": str(order_id), "status": order.get("status")}
