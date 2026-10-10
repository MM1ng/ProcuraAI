from copy import deepcopy
from unittest.mock import Mock

import pytest

import app.agent.procurement_agent as agent
from app.agent.router import route_intent
from caller_test_support_m1 import direct_agent_context, registered_confirmation, api_test_context


@pytest.fixture
def caller_session():
    with direct_agent_context() as context:
        yield context


@pytest.fixture
def transaction_spies(monkeypatch, caller_session):
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
    monkeypatch.setattr(agent, "create_confirmed_order", lambda *_: save(create(plan)))
    return create, save, checkout


def assert_recommendation(message, spies, caller_session):
    result = agent.run_procurement_agent(message, caller_session.session_id, skip_plan_explanation=True)
    assert result["type"] == "recommendation_plan"
    assert result["recommendation_plan"]["items"]
    assert result["order_id"] is None
    assert result["checkout_url"] is None
    for spy in spies:
        spy.assert_not_called()


def test_buy_request_does_not_create_order(transaction_spies, caller_session):
    assert_recommendation("I want to buy 20 mice", transaction_spies, caller_session)


def test_chinese_buy_request_does_not_create_order(transaction_spies, caller_session):
    assert_recommendation("我想购买20个鼠标", transaction_spies, caller_session)


def test_procurement_request_does_not_create_order(transaction_spies, caller_session):
    assert_recommendation("帮我采购10台显示器", transaction_spies, caller_session)


@pytest.mark.parametrize("message", ["确认这个方案并下单", "确认方案B并下单", "Confirm this plan and place the order"])
def test_explicit_confirm_order_can_create_order(message, transaction_spies, monkeypatch, caller_session):
    session_plan = {
        "plan_id": "plan-transaction-test-v1", "plan_version": 1, "plan_hash": "server-hash",
        "items": [{"product_id": "mouse-1", "name": "Mouse", "quantity": 20,
                   "unit_price": 10, "subtotal": 200}],
        "total_amount": 200, "budget_status": "within_budget",
    }
    session_plan, confirmation_id = registered_confirmation(caller_session, session_plan)
    session_state = {
        "recommended_plan": session_plan, "retrieved_products": [],
        "parsed_intent": {}, "trace_id": "prior-trace",
    }
    monkeypatch.setattr(agent, "get_session_state", lambda *_: deepcopy(session_state))
    result = agent.run_procurement_agent(message, caller_session.session_id, skip_plan_explanation=True,
        plan_id=session_plan["plan_id"], plan_hash=session_plan["plan_hash"], plan_version=session_plan["plan_version"],
        confirmation_id=confirmation_id)
    assert result["type"] == "order"
    assert result["order_id"] == "test-order"
    transaction_spies[0].assert_called_once()
    transaction_spies[1].assert_called_once()
    transaction_spies[2].assert_not_called()


@pytest.mark.parametrize("message", ["确认方案A并下单", "确认支付", "Pay now"])
def test_explicit_transaction_without_server_snapshot_is_blocked(message, transaction_spies, caller_session):
    result = agent.run_procurement_agent(message, caller_session.session_id, skip_plan_explanation=True)
    assert result["type"] == "clarify"
    assert result["order_id"] is None
    assert result["checkout_url"] is None
    assert result["transaction_gate"] == "block"
    transaction_spies[0].assert_not_called()
    transaction_spies[1].assert_not_called()
    transaction_spies[2].assert_not_called()


def test_plan_snapshot_drift_returns_actionable_structured_response(transaction_spies, monkeypatch, caller_session):
    session_plan = {
        "plan_id": "drift-plan-v1", "plan_version": 1, "plan_hash": "server-hash",
        "items": [{"product_id": "mouse-1", "name": "Mouse", "quantity": 2,
                   "unit_price": 10, "subtotal": 20}],
        "total_amount": 20, "budget_status": "within_budget",
    }
    monkeypatch.setattr(agent, "get_session_state", lambda *_: {
        "recommended_plan": deepcopy(session_plan), "retrieved_products": [],
        "parsed_intent": {}, "trace_id": "previous-trace",
    })
    monkeypatch.setattr(agent, "validate_plan_snapshot", lambda *_: (
        deepcopy(session_plan), ["price_changed:mouse-1", "stock_changed:mouse-1"]
    ))

    result = agent.run_procurement_agent(
        "确认这个方案并下单", caller_session.session_id, skip_plan_explanation=True,
    )

    assert result["error_code"] == "PLAN_SNAPSHOT_INVALID"
    assert result["snapshot_drift"] == ["price_changed:mouse-1", "stock_changed:mouse-1"]
    assert result["transaction_gate"] == "block"
    assert result["transaction_gate_reason"] == "snapshot_drift"
    assert "方案已变化" in result["answer"]
    assert "重新生成方案" in result["answer"]
    assert "再次确认" in result["answer"]
    assert result["order_id"] is None
    assert result["checkout_url"] is None
    for spy in transaction_spies:
        spy.assert_not_called()


def test_m1_http_missing_identity_remains_rejected(caller_session):
    from fastapi.testclient import TestClient
    from main import app
    from app.services import order_service
    with TestClient(app,base_url="http://127.0.0.1:8000",client=("127.0.0.1",50001)) as anonymous:
        response=anonymous.post("/api/chat",json={"message":"确认这个方案并下单","session_id":caller_session.session_id},
            headers={"Origin":"http://127.0.0.1:3000"})
    assert response.status_code==401
    assert order_service.list_orders()==[]


def test_m1_http_foreign_session_remains_rejected(caller_session):
    from app.services import order_service
    with api_test_context() as other:
        assert other.caller.actor_id!=caller_session.caller.actor_id
        response=other.client.post("/api/chat",json={"message":"确认这个方案并下单","session_id":caller_session.session_id})
    assert response.status_code==403
    assert order_service.list_orders()==[]


@pytest.mark.parametrize("csrf",["wrong",None])
def test_m1_http_wrong_or_missing_csrf_remains_rejected(caller_session,csrf):
    from app.services import order_service
    client=caller_session.client
    if csrf is None:
        del client.headers["X-CSRF-Token"]
        response=client.post("/api/chat",json={"message":"确认这个方案并下单","session_id":caller_session.session_id})
    else:
        response=client.post("/api/chat",json={"message":"确认这个方案并下单","session_id":caller_session.session_id},
            headers={"X-CSRF-Token":csrf})
    assert response.status_code==403
    assert order_service.list_orders()==[]


def test_m1_direct_agent_missing_identity_remains_rejected():
    from app.services.caller_identity import CURRENT_CALLER,CallerDenied
    from app.services import order_service
    with api_test_context() as context:
        current=CURRENT_CALLER.set(None)
        try:
            with pytest.raises(CallerDenied,match="CALLER_REQUIRED"):
                agent.run_procurement_agent("确认这个方案并下单",context.session_id,skip_plan_explanation=True)
        finally:
            CURRENT_CALLER.reset(current)
    assert order_service.list_orders()==[]


def test_m1_direct_agent_foreign_session_remains_rejected():
    from app.services.caller_identity import CURRENT_CALLER,CallerDenied
    from app.services import order_service
    with api_test_context() as owner,api_test_context() as other:
        current=CURRENT_CALLER.set(other.caller)
        try:
            with pytest.raises(CallerDenied,match="RESOURCE_NOT_OWNED"):
                agent.run_procurement_agent("确认这个方案并下单",owner.session_id,skip_plan_explanation=True)
        finally:
            CURRENT_CALLER.reset(current)
    assert order_service.list_orders()==[]


def test_m1_direct_caller_context_is_restored_after_exception():
    from app.services.caller_identity import CURRENT_CALLER,require_caller
    previous=CURRENT_CALLER.get()
    with pytest.raises(RuntimeError,match="fixture teardown probe"):
        with direct_agent_context() as context:
            assert require_caller().actor_id==context.caller.actor_id
            raise RuntimeError("fixture teardown probe")
    assert CURRENT_CALLER.get() is previous


def test_chat_api_preserves_structured_snapshot_drift_fields(monkeypatch, caller_session):
    import app.api.chat as chat_api
    from fastapi.testclient import TestClient
    from main import app

    monkeypatch.setattr(chat_api, "run_procurement_agent", lambda *_args, **_kwargs: {
        "session_id": "chat-drift-api-test",
        "parsed_intent": {},
        "recommended_plan": {"items": []},
        "answer": "The plan changed; generate and confirm it again.",
        "trace_id": "trace-chat-drift-api-test",
        "model_provider": "mock",
        "model_name": "test",
        "used_mock_llm": True,
        "error_code": "PLAN_SNAPSHOT_INVALID",
        "snapshot_drift": ["price_changed:mouse-1"],
        "transaction_gate_reason": "snapshot_drift",
    })

    response = caller_session.client.post("/api/chat", json={"message": "confirm the plan", "session_id":caller_session.session_id})

    assert response.status_code == 200
    assert response.json()["error_code"] == "PLAN_SNAPSHOT_INVALID"
    assert response.json()["snapshot_drift"] == ["price_changed:mouse-1"]
    assert response.json()["transaction_gate_reason"] == "snapshot_drift"


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
def test_mentions_negations_and_questions_have_no_transaction_side_effects(message, transaction_spies, caller_session):
    result = agent.run_procurement_agent(message, caller_session.session_id, skip_plan_explanation=True)
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
def test_generic_chat_api_has_no_transaction_side_effects(message, transaction_spies, caller_session):
    from fastapi.testclient import TestClient
    from main import app

    response = caller_session.client.post("/api/chat", json={"message": message, "session_id": caller_session.session_id})
    assert response.status_code == 200
    result = response.json()
    assert result["type"] == "recommendation_plan"
    assert result["recommendation_plan"]["items"]
    assert result["order_id"] is None
    assert result["checkout_url"] is None
    for spy in transaction_spies:
        spy.assert_not_called()


@pytest.mark.parametrize(
    "message,categories,revision_intent,has_previous_context",
    [
        ("上次那个方案里的键盘不太行", ["Keyboard"], "replace_product", True),
        ("那个换成便宜点的", ["Keyboard"], "cheaper", True),
        ("Set up a workstation for 3 engineers", ["Laptop", "Monitor"], "new_plan", False),
        ("为设计团队配 3 台电脑", ["Laptop"], "new_plan", False),
    ],
)
def test_uncertain_jev_route_still_allows_ordinary_retrieval(
    message, categories, revision_intent, has_previous_context,
    transaction_spies, monkeypatch, caller_session,
):
    previous_intent = (
        {"categories": ["Keyboard"], "quantity_by_category": {"Keyboard": 1}}
        if has_previous_context else None
    )
    previous_plan = {
        "items": [{"product_id": "mouse-1", "name": "Mouse", "quantity": 1,
                   "unit_price": 10, "subtotal": 10}],
        "total_amount": 10,
    }
    monkeypatch.setattr(agent, "get_session_state", lambda *_: (
        {"parsed_intent": previous_intent, "recommended_plan": previous_plan,
         "retrieved_products": [], "trace_id": "previous-trace"}
        if previous_intent else None
    ))
    monkeypatch.setattr(agent, "parse_purchase_request", lambda *_: {
        "response_language": "zh" if any(ord(char) > 127 for char in message) else "en",
        "categories": categories,
        "quantity_per_category": {category: 3 for category in categories},
        "quantity_by_category": {category: 3 for category in categories},
        "budget": None,
        "revision_intent": revision_intent,
        "used_mock_llm": True,
    })
    products = [{"product_id": "mouse-1", "name": "Mouse", "price": 10,
                 "stock": 10, "rating": 4.5}]
    retrieval = Mock(return_value=products)
    monkeypatch.setattr(agent, "retrieve_products", retrieval)
    rewrite_check = Mock(return_value=has_previous_context)
    rewrite = Mock(return_value="contextualized procurement query")
    monkeypatch.setattr(agent, "should_rewrite", rewrite_check)
    monkeypatch.setattr(agent, "rewrite_query", rewrite)

    result = agent.run_procurement_agent(message, caller_session.session_id, skip_plan_explanation=True)

    retrieval.assert_called_once()
    assert result["type"] != "clarify"
    assert result["recommended_plan"]["items"]
    assert result["order_id"] is None
    assert result["checkout_url"] is None
    transaction_spies[0].assert_not_called()
    transaction_spies[1].assert_not_called()
    transaction_spies[2].assert_not_called()
    if has_previous_context:
        assert rewrite_check.call_args.args[2] == "modify_plan"
        rewrite.assert_called_once()
        assert rewrite.call_args.kwargs["route_label"] == "modify_plan"
    else:
        assert rewrite_check.call_args.args[2] == "recommend"


def test_uncertain_route_without_retrieval_context_asks_for_clarification(
    transaction_spies, monkeypatch, caller_session,
):
    monkeypatch.setattr(agent, "parse_purchase_request", lambda *_: {
        "response_language": "en", "categories": [], "quantity_per_category": {},
        "quantity_by_category": {}, "budget": None, "constraints": [],
        "preferences": [], "revision_intent": "new_plan", "used_mock_llm": True,
    })
    retrieval = Mock(return_value=[])
    monkeypatch.setattr(agent, "retrieve_products", retrieval)

    result = agent.run_procurement_agent("Could you help?", caller_session.session_id, skip_plan_explanation=True)

    assert result["type"] == "clarify"
    assert result["order_id"] is None
    assert result["checkout_url"] is None
    retrieval.assert_not_called()
    for spy in transaction_spies:
        spy.assert_not_called()
