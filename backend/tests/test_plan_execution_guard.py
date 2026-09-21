from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from app.services import order_service, product_service, stripe_payment_service
from main import app


def valid_plan():
    return {
        "items": [{"product_id": "A", "quantity": 2}], "budget": 100,
        "budget_status": "within_budget", "over_budget": False, "selectable": True,
        "inventory_status": "valid", "constraint_satisfaction": "satisfied",
        "missing_categories": [], "constraints_relaxed": False,
    }


BLOCKERS = [
    ({"over_budget": True}, "over_budget"),
    ({"budget_status": "over_budget"}, "over_budget"),
    ({"inventory_status": "insufficient_stock"}, "insufficient_stock"),
    ({"inventory_status": None}, "insufficient_stock"),
    ({"missing_categories": ["Monitor"]}, "missing_categories"),
    ({"constraint_satisfaction": "needs_review"}, "hard_constraints_failed"),
    ({"constraint_satisfaction": None}, "hard_constraints_failed"),
    ({"constraints_relaxed": True}, "retrieval_constraints_relaxed"),
    ({"selectable": False}, "not_selectable"),
]


@pytest.fixture
def execution_context(monkeypatch, tmp_path):
    products = [{"product_id": "A", "name": "Mouse", "category": "Mouse", "price": 25,
                 "stock": 10, "rating": 4.6, "delivery_days": 2}]
    monkeypatch.setattr(product_service, "load_products_from_csv", lambda: deepcopy(products))
    monkeypatch.setattr(order_service, "ORDERS_FILE", tmp_path / "orders.json")
    settings = SimpleNamespace(use_mock_payment=False, stripe_secret_key="sk_test_fixture",
                               stripe_success_url="", stripe_cancel_url="", frontend_base_url="http://localhost:3000")
    monkeypatch.setattr(stripe_payment_service, "get_settings", lambda: settings)
    create = Mock(return_value=SimpleNamespace(id="cs_test_guard", url="https://checkout.stripe.test/guard"))
    monkeypatch.setattr(stripe_payment_service, "_stripe_module", lambda: SimpleNamespace(
        checkout=SimpleNamespace(Session=SimpleNamespace(create=create)),
    ))
    return SimpleNamespace(products=products, create=create, settings=settings)


def post_order(plan):
    return TestClient(app, raise_server_exceptions=False).post("/api/orders", json={"plan": plan})


def assert_blocked(response, *reasons):
    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["code"] == "PLAN_NOT_EXECUTABLE"
    assert set(reasons) <= set(detail["blocking_reasons"])


def test_valid_plan_is_executable():
    from app.services.plan_execution_guard import PlanExecutionGuard

    result = PlanExecutionGuard.evaluate(valid_plan())
    assert result.model_dump() == {"executable": True, "blocking_reasons": [], "warnings": []}


@pytest.mark.parametrize("override, reason", BLOCKERS)
def test_guard_reports_each_failure(override, reason):
    from app.services.plan_execution_guard import PlanExecutionGuard

    result = PlanExecutionGuard.evaluate({**valid_plan(), **override})
    assert result.executable is False
    assert reason in result.blocking_reasons


def test_guard_reports_all_blocking_reasons_without_mutation():
    from app.services.plan_execution_guard import PlanExecutionGuard

    plan = {**valid_plan(), "over_budget": True, "inventory_status": "insufficient_stock",
            "missing_categories": ["Monitor"], "constraint_satisfaction": "needs_review",
            "constraints_relaxed": True}
    original = deepcopy(plan)
    result = PlanExecutionGuard.evaluate(plan)
    assert set(result.blocking_reasons) == {
        "over_budget", "insufficient_stock", "missing_categories",
        "hard_constraints_failed", "retrieval_constraints_relaxed",
    }
    assert plan == original


@pytest.mark.parametrize("override, reason", BLOCKERS)
def test_order_endpoint_blocks_unexecutable_plan(execution_context, override, reason):
    assert_blocked(post_order({**valid_plan(), **override}), reason)
    assert order_service.list_orders() == []


def test_canonical_budget_and_stock_cannot_be_overridden_by_positive_client_flags(execution_context):
    plan = {**valid_plan(), "budget": 1, "items": [{"product_id": "A", "quantity": 11, "unit_price": 0.01}],
            "total_amount": 0.11, "executable": True}
    assert_blocked(post_order(plan), "over_budget", "insufficient_stock")
    assert order_service.list_orders() == []


def test_duplicate_product_lines_cannot_hide_insufficient_stock(execution_context):
    plan = {"items": [{"product_id": "A", "quantity": 6}, {"product_id": "A", "quantity": 6}]}
    assert_blocked(post_order(plan), "insufficient_stock")


def test_direct_service_entrypoint_also_blocks_plan(execution_context):
    with pytest.raises(ValueError):
        order_service.create_order_from_plan({**valid_plan(), "missing_categories": ["Monitor"]})


@pytest.mark.parametrize("endpoint", ["/api/payments/stripe/checkout", "/api/payments/create-checkout-session"])
@pytest.mark.parametrize("override, reason", BLOCKERS)
def test_checkout_rechecks_persisted_plan_before_stripe(execution_context, endpoint, override, reason):
    order = order_service.save_order(order_service.create_order_from_plan(valid_plan()))
    order["procurement_plan"].update(override)
    order_service.update_order(order["order_id"], {"procurement_plan": order["procurement_plan"]})
    response = TestClient(app).post(endpoint, json={"order_id": order["order_id"]})
    assert_blocked(response, reason)
    execution_context.create.assert_not_called()
    assert order_service.get_order(order["order_id"])["stripe_session_id"] is None


def test_incomplete_persisted_plan_is_not_assumed_executable(execution_context):
    order = order_service.save_order(order_service.create_order_from_plan(valid_plan()))
    order["procurement_plan"].pop("inventory_status", None)
    order["procurement_plan"].pop("constraint_satisfaction", None)
    order_service.update_order(order["order_id"], {"procurement_plan": order["procurement_plan"]})
    response = TestClient(app).post("/api/payments/stripe/checkout", json={"order_id": order["order_id"]})
    assert_blocked(response, "insufficient_stock", "hard_constraints_failed")
    execution_context.create.assert_not_called()


def test_valid_order_and_checkout_flow_preserves_canonical_amount(execution_context, monkeypatch):
    response = post_order({**valid_plan(), "total_amount": 0.01})
    assert response.status_code == 200
    order = response.json()
    assert order["total_amount"] == 50
    assert order["procurement_plan"]["inventory_status"] == "valid"
    assert order["procurement_plan"]["constraint_satisfaction"] == "satisfied"
    monkeypatch.setattr(product_service, "load_products_from_csv", Mock(side_effect=AssertionError("No stock refresh")))
    checkout = TestClient(app).post("/api/payments/stripe/checkout", json={"order_id": order["order_id"]})
    assert checkout.status_code == 200
    execution_context.create.assert_called_once()
    assert execution_context.create.call_args.kwargs["metadata"]["total_amount"] == "50.00"


def test_relaxed_retrieval_is_carried_into_all_agent_plans_and_blocks_order(execution_context, monkeypatch):
    import app.agent.procurement_agent as agent
    from app.rag.retriever import RetrievalResult

    monkeypatch.setattr(agent, "get_session_state", lambda *_: None)
    monkeypatch.setattr(agent, "save_session_state", lambda *_: None)
    monkeypatch.setattr(agent, "log_observability_event", lambda *_: None)
    monkeypatch.setattr(agent.LangfuseClient, "trace", lambda *_, **__: None)
    monkeypatch.setattr(agent, "should_rewrite", lambda *_: False)
    monkeypatch.setattr(agent, "parse_purchase_request", lambda *_: {
        "categories": ["Mouse"], "quantity_by_category": {"Mouse": 2}, "budget": 100,
        "revision_intent": "new_plan", "used_mock_llm": True,
    })
    monkeypatch.setattr(agent, "_retrieve_products_for_agent", lambda *_, **__: RetrievalResult(
        products=execution_context.products, evidence={"constraints_relaxed": True},
    ))
    checkout = Mock()
    monkeypatch.setattr(agent, "create_checkout_for_selected_plan", checkout)
    result = agent.run_procurement_agent("确认方案B并下单", "guard-test", skip_plan_explanation=True)
    assert result["recommended_plan"]["constraints_relaxed"] is True
    assert result["plan_options"]
    assert all(option["plan"]["constraints_relaxed"] for option in result["plan_options"])
    assert result["order_id"] is None
    assert order_service.list_orders() == []
    checkout.assert_not_called()
