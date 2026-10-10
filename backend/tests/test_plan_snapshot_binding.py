from copy import deepcopy

from fastapi.testclient import TestClient

from app.agent.session_state import get_session_state, save_session_state, validate_plan_snapshot
from app.services import order_service, product_service
from app.services.confirmed_transaction import issue_confirmation
from main import app


def _plan(price=10.0, stock=20, delivery=3):
    return {
        "plan_option_id": "plan-snapshot-1",
        "items": [{
            "product_id": "p1", "name": "Keyboard", "quantity": 2,
            "unit_price": price, "subtotal": price * 2,
            "stock": stock, "delivery_days": delivery,
        }],
        "total_amount": price * 2,
        "budget": 100,
        "budget_status": "within_budget",
        "inventory_status": "valid",
        "constraint_satisfaction": "satisfied",
        "selectable": True,
    }


def test_snapshot_hash_is_server_owned_and_version_increments(monkeypatch):
    monkeypatch.setattr(product_service, "load_products_from_csv", lambda: [{
        "product_id": "p1", "name": "Keyboard", "price": 10.0,
        "stock": 20, "delivery_days": 3,
    }])
    save_session_state("snapshot-session", {}, _plan(), [], "trace-1")
    first = get_session_state("snapshot-session")
    save_session_state("snapshot-session", {}, {**_plan(), "total_amount": 18.0}, [], "trace-2")
    second = get_session_state("snapshot-session")
    assert first["plan_hash"] != second["plan_hash"]
    assert second["recommended_plan"]["plan_version"] == first["recommended_plan"]["plan_version"] + 1


def test_repeated_and_explanation_only_plan_saves_keep_identity_and_hash():
    save_session_state("stable-session", {}, _plan(), [], "trace-first")
    first = get_session_state("stable-session")["recommended_plan"]
    save_session_state(
        "stable-session", {}, {**_plan(), "recommendation_reason": "first explanation"}, [], "trace-second"
    )
    second = get_session_state("stable-session")["recommended_plan"]
    save_session_state(
        "stable-session", {}, {**_plan(), "recommendation_summary": "different wording"}, [], "trace-third"
    )
    third = get_session_state("stable-session")["recommended_plan"]

    assert first["plan_id"] == second["plan_id"] == third["plan_id"]
    assert first["plan_hash"] == second["plan_hash"] == third["plan_hash"]
    assert first["plan_version"] == second["plan_version"] == third["plan_version"]


def test_frontend_shaped_order_payload_with_plan_id_uses_server_snapshot(monkeypatch):
    monkeypatch.setattr(product_service, "load_products_from_csv", lambda: [{
        "product_id": "p1", "name": "Keyboard", "price": 10.0,
        "stock": 20, "delivery_days": 3,
    }])
    save_session_state("frontend-order-session", {}, _plan(), [], "trace-frontend")
    state = get_session_state("frontend-order-session")
    plan = state["recommended_plan"]

    response = TestClient(app).post("/api/orders", json={
        "user_id": "test-user",
        "session_id": "frontend-order-session",
        "plan_id": plan["plan_id"],
        "plan_version": plan["plan_version"],
        "plan_hash": plan["plan_hash"],
        "confirmation_id": issue_confirmation("frontend-order-session", plan["plan_id"], plan["plan_hash"], plan["plan_version"], "test-user"),
        "plan": {
            "plan_id": plan["plan_id"],
            "plan_option_id": plan.get("plan_option_id"),
            "items": [{"product_id": "p1", "quantity": 2}],
        },
    })
    assert response.status_code == 200
    assert response.json()["plan_id"] == plan["plan_id"]


def test_order_endpoint_rejects_hash_mismatch_without_writing_order(monkeypatch):
    monkeypatch.setattr(product_service, "load_products_from_csv", lambda: [{
        "product_id": "p1", "name": "Keyboard", "price": 10.0,
        "stock": 20, "delivery_days": 3,
    }])
    save_session_state("order-session", {}, _plan(), [], "trace-order")
    state = get_session_state("order-session")
    response = TestClient(app).post("/api/orders", json={
        "session_id": "order-session",
        "plan_id": state["plan_id"],
        "plan_version": state["recommended_plan"]["plan_version"],
        "plan_hash": "tampered",
        "confirmation_id": "confirmation-1",
        "plan": {"plan_id": state["plan_id"], "items": [{"product_id": "p1", "quantity": 99}]},
    })
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "PLAN_SNAPSHOT_INVALID"


def test_snapshot_validation_detects_price_stock_and_delivery_drift(monkeypatch):
    save_session_state("drift-session", {}, _plan(), [], "trace-drift")
    state = get_session_state("drift-session")
    monkeypatch.setattr(product_service, "load_products_from_csv", lambda: [{
        "product_id": "p1", "name": "Keyboard", "price": 11.0,
        "stock": 1, "delivery_days": 7,
    }])
    _, reasons = validate_plan_snapshot("drift-session", state["plan_id"], state["plan_hash"], state["recommended_plan"]["plan_version"])
    assert "price_changed:p1" in reasons
    assert "stock_changed:p1" in reasons
    assert "delivery_changed:p1" in reasons


def test_order_endpoint_returns_drift_reasons_without_creating_order(monkeypatch):
    save_session_state("drift-order-session", {}, _plan(), [], "trace-drift-order")
    state = get_session_state("drift-order-session")
    monkeypatch.setattr(product_service, "load_products_from_csv", lambda: [{
        "product_id": "p1", "name": "Keyboard", "price": 11.0,
        "stock": 1, "delivery_days": 7,
    }])

    response = TestClient(app).post("/api/orders", json={
        "session_id": "drift-order-session",
        "plan_id": state["plan_id"],
        "plan_version": state["recommended_plan"]["plan_version"],
        "plan_hash": state["plan_hash"],
        "confirmation_id": "drift-confirmation",
        "plan": {
            "plan_id": state["plan_id"],
            "plan_option_id": state["recommended_plan"].get("plan_option_id"),
            "items": [{"product_id": "p1", "quantity": 2}],
        },
    })

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "PLAN_SNAPSHOT_INVALID"
    assert set(response.json()["detail"]["reasons"]) == {
        "price_changed:p1", "stock_changed:p1", "delivery_changed:p1",
    }
    assert order_service.list_orders() == []
