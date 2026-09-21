from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import stripe
from fastapi.testclient import TestClient

from app.agent.tools import create_stripe_checkout
from app.services import order_service, payment_service, product_service, stripe_payment_service, stripe_service
from main import app


ENDPOINTS = ["/api/payments/create-checkout-session", "/api/payments/stripe/checkout"]


@pytest.fixture
def checkout_context(monkeypatch, tmp_path):
    products = [{"product_id": "A", "name": "Canonical product", "price": 25.00, "stock": 100}]
    monkeypatch.setattr(product_service, "load_products_from_csv", lambda: deepcopy(products))
    monkeypatch.setattr(order_service, "ORDERS_FILE", tmp_path / "orders.json")

    def save_order(quantity=4):
        order = order_service.create_order_from_plan({
            "plan_option_id": "plan_b", "items": [{"product_id": "A", "quantity": quantity}],
        })
        return order_service.save_order(order)

    order = save_order()
    settings = SimpleNamespace(
        use_mock_payment=False, stripe_secret_key="sk_test_fixture",
        stripe_success_url="http://localhost:3000/payment/success",
        stripe_cancel_url="http://localhost:3000/payment/cancel",
        frontend_base_url="http://localhost:3000",
    )
    create = Mock(return_value=SimpleNamespace(id="cs_test_amount", url="https://checkout.stripe.test/amount"))
    monkeypatch.setattr(stripe_payment_service, "get_settings", lambda: settings)
    monkeypatch.setattr(stripe_service, "get_settings", lambda: settings, raising=False)
    monkeypatch.setattr(stripe_payment_service, "_stripe_module", lambda: SimpleNamespace(
        checkout=SimpleNamespace(Session=SimpleNamespace(create=create)),
    ))
    monkeypatch.setattr(stripe.checkout.Session, "create", create)
    return SimpleNamespace(order=order, products=products, save_order=save_order, create=create, settings=settings)


def post_checkout(endpoint, order_id, **extra):
    return TestClient(app, raise_server_exceptions=False).post(endpoint, json={"order_id": order_id, **extra})


def stripe_total(context):
    context.create.assert_called_once()
    return sum(item["price_data"]["unit_amount"] * item["quantity"]
               for item in context.create.call_args.kwargs["line_items"])


@pytest.mark.parametrize("endpoint", ENDPOINTS)
@pytest.mark.parametrize("forgery", [
    {"amount": 1}, {"amount": 0.01}, {"amount": 999999},
    {"price": 0.01}, {"total": 0.01}, {"unit_amount": 1},
])
def test_client_amount_fields_cannot_change_stripe_total(checkout_context, endpoint, forgery):
    context = checkout_context
    response = post_checkout(endpoint, context.order["order_id"], **{
        "plan_id": "plan_b", "amount": 1, **forgery,
    })
    assert response.status_code == 200
    assert stripe_total(context) == 10000
    assert context.create.call_args.kwargs["metadata"]["total_amount"] == "100.00"
    assert order_service.get_order(context.order["order_id"])["total_amount"] == 100


@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_order_id_only_creates_checkout_for_pending_order(checkout_context, endpoint):
    context = checkout_context
    assert context.order["status"] == "pending_payment"
    response = post_checkout(endpoint, context.order["order_id"])
    assert response.status_code == 200
    assert response.json()["session_id"] == "cs_test_amount"
    assert stripe_total(context) == 10000
    assert context.create.call_args.kwargs["metadata"]["plan_id"] == "plan_b"


@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_missing_order_is_rejected_before_stripe(checkout_context, endpoint):
    response = post_checkout(endpoint, "DOES_NOT_EXIST", amount=1, plan_id="plan_b")
    assert response.status_code == 400
    assert response.json()["detail"] == "Order not found."
    checkout_context.create.assert_not_called()


@pytest.mark.parametrize("endpoint", ENDPOINTS)
@pytest.mark.parametrize("price, cents", [(10.25, 1025), (0.29, 29), (0.07, 7)])
def test_decimal_minor_unit_conversion(checkout_context, endpoint, price, cents):
    context = checkout_context
    context.products[0]["price"] = price
    order = context.save_order(quantity=1)
    response = post_checkout(endpoint, order["order_id"], amount=999999, plan_id="plan_b")
    assert response.status_code == 200
    assert stripe_total(context) == cents


@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_payment_uses_order_snapshot_not_plan_or_current_catalog(checkout_context, endpoint, monkeypatch):
    context = checkout_context
    # The Task 02 order snapshot stays authoritative even if nested plan data is stale.
    plan = deepcopy(context.order["procurement_plan"])
    plan["items"][0]["unit_price"] = 0.01
    plan["total_amount"] = 0.04
    order_service.update_order(context.order["order_id"], {"procurement_plan": plan})
    monkeypatch.setattr(product_service, "load_products_from_csv", Mock(side_effect=AssertionError("No repricing")))
    response = post_checkout(endpoint, context.order["order_id"], amount=0.01, plan_id="plan_b")
    assert response.status_code == 200
    assert stripe_total(context) == 10000
    assert order_service.get_order(context.order["order_id"])["total_amount"] == 100


@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_inconsistent_persisted_total_is_rejected_not_overwritten(checkout_context, endpoint):
    context = checkout_context
    order_service.update_order(context.order["order_id"], {"total_amount": 1})
    response = post_checkout(endpoint, context.order["order_id"], amount=1, plan_id="plan_b")
    assert response.status_code == 400
    context.create.assert_not_called()
    assert order_service.get_order(context.order["order_id"])["total_amount"] == 1


@pytest.mark.parametrize("endpoint", ENDPOINTS)
@pytest.mark.parametrize("total", [None, 0, -1, "invalid", "NaN", "Infinity"])
def test_invalid_persisted_total_is_rejected(checkout_context, endpoint, total):
    context = checkout_context
    order_service.update_order(context.order["order_id"], {"total_amount": total})
    response = post_checkout(endpoint, context.order["order_id"], amount=1, plan_id="plan_b")
    assert response.status_code == 400
    context.create.assert_not_called()


@pytest.mark.parametrize("entrypoint", [
    payment_service.create_checkout, stripe_service.create_stripe_checkout_session, create_stripe_checkout,
])
def test_legacy_service_and_agent_amount_arguments_are_ignored(checkout_context, entrypoint):
    context = checkout_context
    result = entrypoint(order_id=context.order["order_id"], amount=0.01)
    assert result["session_id"] == "cs_test_amount"
    assert stripe_total(context) == 10000


@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_mock_checkout_also_requires_order_and_uses_snapshot(checkout_context, endpoint):
    context = checkout_context
    context.settings.use_mock_payment = True
    response = post_checkout(endpoint, context.order["order_id"], amount=0.01, plan_id="plan_b")
    assert response.status_code == 200
    session_id = response.json()["session_id"]
    saved = order_service.get_order(context.order["order_id"])
    assert saved["total_amount"] == 100
    assert saved["stripe_session_id"] == session_id
    missing = post_checkout(endpoint, "DOES_NOT_EXIST", amount=1, plan_id="plan_b")
    assert missing.status_code == 400
    context.create.assert_not_called()


@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_extra_payload_fields_are_not_used_as_checkout_inputs(checkout_context, endpoint):
    context = checkout_context
    response = post_checkout(endpoint, context.order["order_id"],
                             amount="invalid", unit_amount=-1, total=0.01, price=0.01,
                             plan_id="untrusted-plan", plan={"total_amount": 0.01},
                             success_url="https://example.invalid/untrusted")
    assert response.status_code == 200
    assert stripe_total(context) == 10000
    arguments = context.create.call_args.kwargs
    assert arguments["metadata"]["plan_id"] == "plan_b"
    assert arguments["success_url"].startswith("http://localhost:3000/payment/success")


@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_multi_item_checkout_matches_persisted_order_total(checkout_context, endpoint):
    context = checkout_context
    context.products[0]["price"] = 100
    context.products.append({"product_id": "B", "name": "Second product", "price": 50, "stock": 100})
    order = order_service.save_order(order_service.create_order_from_plan({
        "items": [{"product_id": "A", "quantity": 2}, {"product_id": "B", "quantity": 3}],
    }))
    response = post_checkout(endpoint, order["order_id"], amount=0.01)
    assert response.status_code == 200
    assert stripe_total(context) == 35000
    assert context.create.call_args.kwargs["metadata"]["total_amount"] == "350.00"
    assert order_service.get_order(order["order_id"])["total_amount"] == 350
