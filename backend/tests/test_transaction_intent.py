from copy import deepcopy
from unittest.mock import Mock

import pytest

import app.agent.procurement_agent as agent
from app.agent.router import route_intent


@pytest.fixture
def transaction_spies(monkeypatch):
    plan = {
        "items": [{"product_id": "mouse-1", "name": "Mouse", "quantity": 20,
                   "unit_price": 10, "subtotal": 200}],
        "total_amount": 200, "budget_status": "within_budget",
    }
    monkeypatch.setattr(agent, "get_session_state", lambda *_: None)
    monkeypatch.setattr(agent, "save_session_state", lambda *_: None)
    monkeypatch.setattr(agent, "log_observability_event", lambda *_: None)
    monkeypatch.setattr(agent.LangfuseClient, "trace", lambda *_, **__: None)
    monkeypatch.setattr(agent, "should_rewrite", lambda *_: False)
    monkeypatch.setattr(agent, "retrieve_products", lambda *_, **__: [])
    monkeypatch.setattr(agent, "generate_procurement_plan", lambda *_, **__: deepcopy(plan))
    monkeypatch.setattr(agent, "generate_plan_options", lambda *_: [])
    create = Mock(return_value={"order_id": "test-order", "status": "pending_payment"})
    save = Mock(side_effect=lambda order: order)
    checkout = Mock(return_value={"checkout_url": "https://example.invalid/checkout"})
    monkeypatch.setattr(agent, "create_order_from_plan", create)
    monkeypatch.setattr(agent, "save_order", save)
    monkeypatch.setattr(agent, "create_checkout_for_selected_plan", checkout)
    return create, save, checkout


def assert_recommendation(message, spies):
    result = agent.run_procurement_agent(message, "transaction-test", skip_plan_explanation=True)
    assert result["type"] == "recommendation_plan"
    assert result["recommendation_plan"]["items"]
    assert result["order_id"] is None
    assert result["checkout_url"] is None
    for spy in spies:
        spy.assert_not_called()


def test_buy_request_does_not_create_order(transaction_spies):
    assert_recommendation("I want to buy 20 mice", transaction_spies)


def test_chinese_buy_request_does_not_create_order(transaction_spies):
    assert_recommendation("我想购买20个鼠标", transaction_spies)


def test_procurement_request_does_not_create_order(transaction_spies):
    assert_recommendation("帮我采购10台显示器", transaction_spies)


@pytest.mark.parametrize("message", ["确认这个方案并下单", "确认方案B并下单", "Confirm this plan and place the order"])
def test_explicit_confirm_order_can_create_order(message, transaction_spies):
    result = agent.run_procurement_agent(message, "transaction-test", skip_plan_explanation=True)
    assert result["type"] == "order"
    assert result["order_id"] == "test-order"
    for spy in transaction_spies:
        spy.assert_called_once()


@pytest.mark.parametrize("message", [
    "I want to buy 20 mice", "我想购买20个鼠标", "帮我采购10台显示器",
    "purchase 20 mice", "buy 20 mice",
])
def test_router_treats_purchase_as_recommendation(message):
    assert route_intent(message)["route"] == "recommendation"


@pytest.mark.parametrize("message", [
    "Do not place an order", "不要确认这个方案并下单", "取消支付",
    "How do I pay?", "show my orders", "payment options", "order status",
    'Explain "确认方案B并下单"', "如果确认这个方案并下单会怎样？",
])
def test_mentions_negations_and_questions_have_no_transaction_side_effects(message, transaction_spies):
    result = agent.run_procurement_agent(message, "transaction-test", skip_plan_explanation=True)
    assert result["type"] not in {"order", "payment"}
    for spy in transaction_spies:
        spy.assert_not_called()


@pytest.mark.parametrize("message, route", [
    ("确认这个方案并下单", "confirm_order"), ("确认方案B并下单", "confirm_order"),
    ("Confirm this plan and place the order", "confirm_order"),
    ("Pay now", "payment"), ("确认支付", "payment"),
])
def test_router_distinguishes_explicit_transactions(message, route):
    assert route_intent(message)["route"] == route


@pytest.mark.parametrize("message", ["I want to buy 20 mice", "我想购买20个鼠标", "帮我采购10台显示器"])
def test_generic_chat_api_has_no_transaction_side_effects(message, transaction_spies):
    from fastapi.testclient import TestClient
    from main import app

    response = TestClient(app).post("/api/chat", json={"message": message, "session_id": "safe-chat"})
    assert response.status_code == 200
    result = response.json()
    assert result["type"] == "recommendation_plan"
    assert result["recommendation_plan"]["items"]
    assert result["order_id"] is None
    assert result["checkout_url"] is None
    for spy in transaction_spies:
        spy.assert_not_called()
