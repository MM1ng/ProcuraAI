from copy import deepcopy

import pytest
from fastapi.testclient import TestClient

from app.services import order_service, product_service
from main import app


@pytest.fixture
def catalog(monkeypatch, tmp_path):
    products = [
        {"product_id": "A", "name": "Canonical A", "price": 100.0},
        {"product_id": "B", "name": "Canonical B", "price": 50.0},
        {"product_id": "C", "name": "Decimal cents", "price": 0.29},
    ]
    monkeypatch.setattr(product_service, "load_products_from_csv", lambda: deepcopy(products))
    monkeypatch.setattr(order_service, "ORDERS_FILE", tmp_path / "orders.json")
    return products


def post_order(plan):
    return TestClient(app, raise_server_exceptions=False).post(
        "/api/orders", json={"user_id": "test-user", "plan": plan}
    )


@pytest.mark.parametrize("forgery", [
    {"unit_price": 0.01}, {"price": 0.01}, {"subtotal": 1},
    {"unit_price": "not-a-price", "subtotal": None},
])
def test_tampered_item_amounts_are_ignored(catalog, forgery):
    response = post_order({"items": [{"product_id": "A", "quantity": 10, **forgery}]})
    assert response.status_code == 200
    order = response.json()
    assert order["order_items"][0]["unit_price"] == 100
    assert order["order_items"][0]["subtotal"] == 1000
    assert order["total_amount"] == 1000
    assert order_service.get_order(order["order_id"])["total_amount"] == 1000


@pytest.mark.parametrize("total_fields", [
    {"total": 1}, {"total_amount": 1}, {"total": -999, "total_amount": 999999},
])
def test_tampered_total_is_ignored(catalog, total_fields):
    response = post_order({"items": [{"product_id": "A", "quantity": 10}], **total_fields})
    assert response.status_code == 200
    order = response.json()
    assert order["total_amount"] == 1000
    assert order["procurement_plan"]["total_amount"] == 1000
    assert order["procurement_plan"]["total"] == 1000


def test_multiple_items_use_catalog_prices(catalog):
    response = post_order({"items": [
        {"product_id": "A", "quantity": 2, "unit_price": 1, "subtotal": 1},
        {"product_id": "B", "quantity": 3, "unit_price": 1, "subtotal": 1},
    ], "total_amount": 1})
    assert response.status_code == 200
    order = response.json()
    assert [item["subtotal"] for item in order["order_items"]] == [200, 150]
    assert order["total_amount"] == 350


@pytest.mark.parametrize("items", [
    [{"product_id": "DOES_NOT_EXIST", "quantity": 1}],
    [{"product_id": "A", "quantity": 1}, {"product_id": "DOES_NOT_EXIST", "quantity": 1}],
])
def test_unknown_product_rejected_without_saving_partial_order(catalog, items):
    response = post_order({"items": items})
    assert response.status_code in {400, 404, 422}
    assert order_service.list_orders() == []


@pytest.mark.parametrize("quantity", [0, -1, 1.5, 2.0, "2", "invalid", True, None])
def test_invalid_quantity_is_rejected(catalog, quantity):
    response = post_order({"items": [{"product_id": "A", "quantity": quantity}]})
    assert response.status_code == 422
    assert order_service.list_orders() == []


@pytest.mark.parametrize("plan", [
    {}, {"items": []}, {"items": None}, {"items": [{}]},
    {"items": [{"product_id": "A"}]}, {"items": [{"product_id": "", "quantity": 1}]},
])
def test_empty_or_incomplete_selection_is_rejected(catalog, plan):
    response = post_order(plan)
    assert response.status_code == 422
    assert order_service.list_orders() == []


def test_valid_selection_produces_canonical_immutable_snapshot(catalog):
    plan = {"plan_option_id": "plan_b", "items": [
        {"product_id": "C", "quantity": 3, "name": "Forged name", "price": 0.01,
         "unit_price": 0.01, "subtotal": 0.03}
    ], "total": 0.03, "total_amount": 0.03,
        "selected_items": [{"product_id": "FORGED", "unit_price": 0.01}],
        "budget_status": "over_budget", "status": "paid", "executable": True,
        "selectable": False, "over_budget": True}
    original = deepcopy(plan)
    order = order_service.create_order_from_plan(plan)
    assert plan == original
    assert order["status"] == "pending_payment"
    assert order["plan_id"] == "plan_b"
    assert order["total_amount"] == 0.87
    snapshot = order["procurement_plan"]
    assert snapshot["items"][0]["name"] == "Decimal cents"
    assert snapshot["items"][0]["unit_price"] == 0.29
    assert snapshot["items"][0]["subtotal"] == 0.87
    assert "price" not in snapshot["items"][0]
    assert snapshot["total"] == snapshot["total_amount"] == 0.87
    assert snapshot["budget_status"] == "no_budget_provided"
    assert snapshot["status"] == "no_budget_provided"
    assert snapshot["selectable"] is True
    assert snapshot["over_budget"] is False
    assert "executable" not in snapshot
    assert all(item["product_id"] == "C" for item in snapshot.get("selected_items", []))
    plan["items"][0]["quantity"] = 999
    catalog[2]["price"] = 500
    assert snapshot["items"][0]["quantity"] == 3
    assert snapshot["items"][0]["unit_price"] == 0.29


def test_budget_status_is_recomputed_using_canonical_total(catalog):
    response = post_order({"items": [{"product_id": "A", "quantity": 2, "unit_price": 1}],
                           "budget": 150, "total_amount": 2, "budget_status": "within_budget",
                           "status": "within_budget", "selectable": True, "over_budget": False})
    assert response.status_code == 200
    snapshot = response.json()["procurement_plan"]
    assert snapshot["total_amount"] == 200
    assert snapshot["budget_status"] == "over_budget"
    assert snapshot["selectable"] is False


@pytest.mark.parametrize("quantity", [0, -1, 1.5, "2", True])
def test_agent_and_tool_service_entrypoint_also_validates_quantity(catalog, quantity):
    with pytest.raises(ValueError):
        order_service.create_order_from_plan({"items": [{"product_id": "A", "quantity": quantity}]})


def test_service_entrypoint_rejects_unknown_product(catalog):
    with pytest.raises(ValueError):
        order_service.create_order_from_plan({"items": [{"product_id": "UNKNOWN", "quantity": 1}]})


@pytest.mark.parametrize("price", [0, -1, float("nan"), float("inf"), "invalid", 0.001])
def test_invalid_catalog_price_cannot_fall_back_to_client_price(catalog, price):
    catalog[0]["price"] = price
    response = post_order({"items": [{"product_id": "A", "quantity": 1, "unit_price": 100}]})
    assert response.status_code == 422
    assert order_service.list_orders() == []


def test_normal_order_from_real_catalog_can_be_saved_and_read(monkeypatch, tmp_path):
    monkeypatch.setattr(order_service, "ORDERS_FILE", tmp_path / "orders.json")
    product = product_service.load_products_from_csv()[0]
    response = post_order({"plan_option_id": "plan_b", "items": [
        {"product_id": product["product_id"], "quantity": 2},
    ]})
    assert response.status_code == 200
    order = response.json()
    assert order["status"] == "pending_payment"
    assert order["user_id"] == "test-user"
    assert order["order_items"][0]["unit_price"] == product["price"]
    assert order["total_amount"] == round(product["price"] * 2, 2)
    saved = TestClient(app).get(f"/api/orders/{order['order_id']}")
    assert saved.status_code == 200
    assert saved.json() == order
