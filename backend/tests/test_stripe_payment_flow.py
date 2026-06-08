from __future__ import annotations

import json
from types import SimpleNamespace

from fastapi.testclient import TestClient

import app.services.stripe_payment_service as stripe_payment_service
from app.services import order_service
from main import app


def _plan(**overrides):
    plan = {
        "plan_option_id": "plan_a",
        "items": [
            {
                "product_id": "P-1",
                "name": "Team Keyboard",
                "category": "Keyboard",
                "supplier": "Northwind",
                "quantity": 2,
                "unit_price": 25.25,
                "subtotal": 50.5,
            }
        ],
        "total_amount": 50.5,
        "budget": 100,
        "over_budget": False,
        "selectable": True,
        "status": "within_budget",
        "budget_status": "within_budget",
    }
    plan.update(overrides)
    return plan


def _save_order(tmp_path, monkeypatch, plan=None, status="pending_payment"):
    orders_file = tmp_path / "orders.json"
    monkeypatch.setattr(order_service, "ORDERS_FILE", orders_file)
    order = order_service.create_order_from_plan(plan or _plan(), user_id="demo-user")
    order["status"] = status
    order_service.save_order(order)
    return order


class FakeCheckoutSession:
    @staticmethod
    def create(**kwargs):
        FakeCheckoutSession.last_kwargs = kwargs
        return SimpleNamespace(id="cs_test_123", url="https://checkout.stripe.test/session")


def _stripe_settings():
    return SimpleNamespace(
        use_mock_payment=False,
        stripe_secret_key="sk_test_value",
        stripe_webhook_secret="whsec_value",
        stripe_success_url="http://localhost:3000/payment/success",
        stripe_cancel_url="http://localhost:3000/payment/cancel",
        frontend_base_url="http://localhost:3000",
    )


def test_budget_plan_can_create_stripe_checkout_session(tmp_path, monkeypatch):
    order = _save_order(tmp_path, monkeypatch)
    monkeypatch.setattr(stripe_payment_service, "get_settings", _stripe_settings)
    monkeypatch.setattr(
        stripe_payment_service,
        "_stripe_module",
        lambda: SimpleNamespace(checkout=SimpleNamespace(Session=FakeCheckoutSession)),
    )

    session = stripe_payment_service.create_procurement_checkout_session("plan_a", order["order_id"])

    assert session == {
        "checkout_url": "https://checkout.stripe.test/session",
        "session_id": "cs_test_123",
    }
    assert FakeCheckoutSession.last_kwargs["metadata"]["order_id"] == order["order_id"]
    assert FakeCheckoutSession.last_kwargs["metadata"]["plan_id"] == "plan_a"
    assert FakeCheckoutSession.last_kwargs["metadata"]["total_amount"] == "50.50"
    assert FakeCheckoutSession.last_kwargs["metadata"]["source"] == "procuraai"
    assert FakeCheckoutSession.last_kwargs["line_items"][0]["price_data"]["unit_amount"] == 2525
    assert FakeCheckoutSession.last_kwargs["line_items"][0]["quantity"] == 2
    assert order_service.get_order(order["order_id"])["stripe_session_id"] == "cs_test_123"


def test_no_budget_plan_can_create_stripe_checkout_session(tmp_path, monkeypatch):
    plan = _plan(
        plan_option_id="plan_b",
        budget=None,
        budget_status="no_budget_provided",
        status="no_budget_provided",
        over_budget=False,
        selectable=True,
    )
    order = _save_order(tmp_path, monkeypatch, plan)
    monkeypatch.setattr(stripe_payment_service, "get_settings", _stripe_settings)
    monkeypatch.setattr(
        stripe_payment_service,
        "_stripe_module",
        lambda: SimpleNamespace(checkout=SimpleNamespace(Session=FakeCheckoutSession)),
    )

    session = stripe_payment_service.create_procurement_checkout_session("plan_b", order["order_id"])

    assert session["session_id"] == "cs_test_123"
    assert FakeCheckoutSession.last_kwargs["metadata"]["plan_id"] == "plan_b"


def test_over_budget_plan_cannot_create_stripe_checkout_session(tmp_path, monkeypatch):
    order = _save_order(tmp_path, monkeypatch, _plan(over_budget=True, selectable=False, status="over_budget"))

    try:
        stripe_payment_service.create_procurement_checkout_session("plan_a", order["order_id"])
    except ValueError as exc:
        assert str(exc) == "Over-budget plans cannot be paid directly."
    else:
        raise AssertionError("Expected over-budget plan to be rejected")


def test_unselectable_plan_cannot_create_stripe_checkout_session(tmp_path, monkeypatch):
    order = _save_order(tmp_path, monkeypatch, _plan(selectable=False))

    try:
        stripe_payment_service.create_procurement_checkout_session("plan_a", order["order_id"])
    except ValueError as exc:
        assert str(exc) == "Over-budget plans cannot be paid directly."
    else:
        raise AssertionError("Expected unselectable plan to be rejected")


def test_stripe_checkout_api_returns_session(tmp_path, monkeypatch):
    order = _save_order(tmp_path, monkeypatch)
    monkeypatch.setattr(
        "app.api.payments.create_procurement_checkout_session",
        lambda plan_id, order_id: {"checkout_url": "https://checkout.stripe.test/session", "session_id": "cs_test_123"},
    )

    response = TestClient(app).post(
        "/api/payments/stripe/checkout",
        json={"plan_id": "plan_a", "order_id": order["order_id"]},
    )

    assert response.status_code == 200
    assert response.json() == {
        "checkout_url": "https://checkout.stripe.test/session",
        "session_id": "cs_test_123",
    }


def test_stripe_webhook_completed_marks_order_paid_once(tmp_path, monkeypatch):
    order = _save_order(tmp_path, monkeypatch)
    event = {
        "id": "evt_1",
        "type": "checkout.session.completed",
        "data": {"object": {"metadata": {"order_id": order["order_id"], "plan_id": "plan_a"}}},
    }
    monkeypatch.setattr(stripe_payment_service, "get_settings", _stripe_settings)
    monkeypatch.setattr(stripe_payment_service, "_construct_event", lambda payload, signature, secret: event)

    client = TestClient(app)
    first = client.post("/api/payments/stripe/webhook", content=b"{}", headers={"stripe-signature": "sig"})
    second = client.post("/api/payments/stripe/webhook", content=b"{}", headers={"stripe-signature": "sig"})

    assert first.status_code == 200
    assert second.status_code == 200
    saved = json.loads((tmp_path / "orders.json").read_text(encoding="utf-8"))[0]
    assert saved["status"] == "paid"
    assert saved["processed_payment_event_ids"] == ["evt_1"]


def test_stripe_webhook_completed_can_use_client_reference_id(tmp_path, monkeypatch):
    order = _save_order(tmp_path, monkeypatch)
    event = {
        "id": "evt_client_reference",
        "type": "checkout.session.completed",
        "data": {"object": {"client_reference_id": order["order_id"], "metadata": {}}},
    }
    monkeypatch.setattr(stripe_payment_service, "get_settings", _stripe_settings)
    monkeypatch.setattr(stripe_payment_service, "_construct_event", lambda payload, signature, secret: event)

    response = TestClient(app).post("/api/payments/stripe/webhook", content=b"{}", headers={"stripe-signature": "sig"})

    assert response.status_code == 200
    saved = json.loads((tmp_path / "orders.json").read_text(encoding="utf-8"))[0]
    assert saved["status"] == "paid"


def test_stripe_webhook_completed_can_use_checkout_session_id(tmp_path, monkeypatch):
    order = _save_order(tmp_path, monkeypatch)
    order_service.update_order(order["order_id"], {"stripe_session_id": "cs_test_from_event"})
    event = {
        "id": "evt_session_id",
        "type": "checkout.session.completed",
        "data": {"object": {"id": "cs_test_from_event", "metadata": {}}},
    }
    monkeypatch.setattr(stripe_payment_service, "get_settings", _stripe_settings)
    monkeypatch.setattr(stripe_payment_service, "_construct_event", lambda payload, signature, secret: event)

    response = TestClient(app).post("/api/payments/stripe/webhook", content=b"{}", headers={"stripe-signature": "sig"})

    assert response.status_code == 200
    saved = json.loads((tmp_path / "orders.json").read_text(encoding="utf-8"))[0]
    assert saved["status"] == "paid"
