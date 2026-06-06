from fastapi.testclient import TestClient

from main import app


client = TestClient(app)


def _plan(total: float = 200.0) -> dict:
    return {
        "items": [
            {
                "product_id": "laptop-premium",
                "name": "Premium Laptop",
                "category": "Laptop",
                "brand": "Lenovo",
                "supplier": "Acme Tech",
                "quantity": 2,
                "unit_price": total / 2,
                "subtotal": total,
                "rating": 4.5,
                "stock": 20,
                "delivery_days": 5,
                "reason": "Selected for quality.",
            }
        ],
        "selected_items": [],
        "total_amount": total,
        "budget_status": "within_budget",
        "inventory_status": "valid",
        "constraint_satisfaction": "satisfied",
    }


def test_quick_optimization_returns_compatible_chat_response(monkeypatch):
    products = [
        {
            "product_id": "laptop-cheap",
            "name": "Budget Laptop",
            "category": "Laptop",
            "brand": "Dell",
            "supplier": "Budget Supplier",
            "price": 70.0,
            "rating": 4.2,
            "stock": 15,
            "delivery_days": 3,
            "description": "Affordable business laptop.",
        },
        {
            "product_id": "laptop-fast",
            "name": "Fast Laptop",
            "category": "Laptop",
            "brand": "HP",
            "supplier": "Fast Supplier",
            "price": 95.0,
            "rating": 4.4,
            "stock": 15,
            "delivery_days": 1,
            "description": "Ships quickly.",
        },
        {
            "product_id": "laptop-premium",
            "name": "Premium Laptop",
            "category": "Laptop",
            "brand": "Lenovo",
            "supplier": "Acme Tech",
            "price": 100.0,
            "rating": 4.8,
            "stock": 20,
            "delivery_days": 5,
            "description": "High quality device.",
        },
    ]

    monkeypatch.setattr("app.api.chat.retrieve_products", lambda *_args, **_kwargs: products)

    response = client.post(
        "/api/chat/optimize",
        json={
            "action": "make_cheaper",
            "session_id": "quick-test",
            "parsed_intent": {
                "raw_message": "Buy laptops for 2 analysts",
                "categories": ["Laptop"],
                "people_count": 2,
                "quantity_by_category": {"Laptop": 2},
                "budget": 250,
            },
            "current_plan": _plan(),
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["recommended_plan"]["items"][0]["product_id"] == "laptop-cheap"
    assert payload["recommended_plan"]["total_amount"] == 140.0
    assert payload["recommended_plan"]["savings_amount"] == 60.0
    assert payload["plan_options"]
    assert payload["selected_plan_id"] == payload["recommended_plan"]["plan_option_id"]
    assert payload["used_previous_context"] is True
