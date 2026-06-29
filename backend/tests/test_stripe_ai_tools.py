from __future__ import annotations

from types import SimpleNamespace

import app.services.stripe_payment_service as stripe_payment_service
from app.services import order_service
from app.tools.stripe_ai_tools import create_checkout_for_selected_plan


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
        "total_amount": 9999.99,
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
        return SimpleNamespace(id="cs_test_ai_tool", url="https://checkout.stripe.test/ai-tool")


def _stripe_settings():
    return SimpleNamespace(
        use_mock_payment=False,
        stripe_secret_key="sk_test_value",
        stripe_webhook_secret="whsec_value",
        stripe_success_url="http://localhost:3000/payment/success",
        stripe_cancel_url="http://localhost:3000/payment/cancel",
        frontend_base_url="http://localhost:3000",
    )


def _patch_stripe(monkeypatch):
    monkeypatch.setattr(stripe_payment_service, "get_settings", _stripe_settings)
    monkeypatch.setattr(
        stripe_payment_service,
        "_stripe_module",
        lambda: SimpleNamespace(checkout=SimpleNamespace(Session=FakeCheckoutSession)),
    )


def test_ai_tool_can_create_checkout_for_within_budget_plan(tmp_path, monkeypatch):
    order = _save_order(tmp_path, monkeypatch)
    _patch_stripe(monkeypatch)

    session = create_checkout_for_selected_plan("plan_a", order["order_id"])

    assert session == {
        "checkout_url": "https://checkout.stripe.test/ai-tool",
        "session_id": "cs_test_ai_tool",
    }
    assert FakeCheckoutSession.last_kwargs["metadata"]["order_id"] == order["order_id"]
    assert FakeCheckoutSession.last_kwargs["metadata"]["plan_id"] == "plan_a"


def test_ai_tool_rejects_over_budget_plan(tmp_path, monkeypatch):
    order = _save_order(tmp_path, monkeypatch, _plan(over_budget=True, selectable=False, status="over_budget"))

    try:
        create_checkout_for_selected_plan("plan_a", order["order_id"])
    except ValueError as exc:
        assert str(exc) == "Over-budget plans cannot be paid directly."
    else:
        raise AssertionError("Expected over-budget plan to be rejected")


def test_ai_tool_rejects_unselectable_plan(tmp_path, monkeypatch):
    order = _save_order(tmp_path, monkeypatch, _plan(selectable=False))

    try:
        create_checkout_for_selected_plan("plan_a", order["order_id"])
    except ValueError as exc:
        assert str(exc) == "Over-budget plans cannot be paid directly."
    else:
        raise AssertionError("Expected unselectable plan to be rejected")


def test_ai_tool_uses_backend_recalculated_item_amounts(tmp_path, monkeypatch):
    order = _save_order(tmp_path, monkeypatch)
    _patch_stripe(monkeypatch)

    create_checkout_for_selected_plan("plan_a", order["order_id"])

    assert FakeCheckoutSession.last_kwargs["metadata"]["total_amount"] == "50.50"
    assert FakeCheckoutSession.last_kwargs["line_items"][0]["price_data"]["unit_amount"] == 2525
    assert order_service.get_order(order["order_id"])["total_amount"] == 50.5
