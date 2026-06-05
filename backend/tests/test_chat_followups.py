from fastapi.testclient import TestClient

import app.agent.procurement_agent as procurement_agent
from main import app


PRODUCTS = [
    {
        "product_id": "P-premium-headset",
        "name": "Premium Headset",
        "category": "Headset",
        "brand": "AudioMax",
        "price": 120.0,
        "rating": 4.8,
        "stock": 20,
        "supplier": "Northwind Office",
        "delivery_days": 2,
    },
    {
        "product_id": "P-team-headset",
        "name": "Team Headset",
        "category": "Headset",
        "brand": "AudioMax",
        "price": 55.0,
        "rating": 4.4,
        "stock": 20,
        "supplier": "Northwind Office",
        "delivery_days": 4,
    },
    {
        "product_id": "P-premium-keyboard",
        "name": "Premium Keyboard",
        "category": "Keyboard",
        "brand": "KeyPro",
        "price": 95.0,
        "rating": 4.8,
        "stock": 20,
        "supplier": "Northwind Office",
        "delivery_days": 2,
    },
    {
        "product_id": "P-team-keyboard",
        "name": "Team Keyboard",
        "category": "Keyboard",
        "brand": "KeyPro",
        "price": 35.0,
        "rating": 4.4,
        "stock": 20,
        "supplier": "Northwind Office",
        "delivery_days": 4,
    },
]


def test_chat_followup_cheaper_uses_previous_session_intent_and_plan(monkeypatch):
    monkeypatch.setattr(procurement_agent, "retrieve_products", lambda message, intent, top_k=30: PRODUCTS)
    client = TestClient(app)

    first = client.post(
        "/api/chat",
        json={
            "session_id": "followup-cheaper-session",
            "message": "We need headsets and keyboards for 5 people. Prefer high rating.",
        },
    ).json()
    followup = client.post(
        "/api/chat",
        json={
            "session_id": "followup-cheaper-session",
            "message": "Make this cheaper but keep rating above 4.2.",
        },
    ).json()

    assert first["recommended_plan"]["total_amount"] == 1075.0
    assert followup["used_previous_context"] is True
    assert followup["parsed_intent"]["people_count"] == 5
    assert followup["parsed_intent"]["categories"] == ["Keyboard", "Headset"]
    assert followup["parsed_intent"]["revision_intent"] == "cheaper"
    assert followup["recommended_plan"]["total_amount"] == 450.0
    assert followup["recommended_plan"]["savings_amount"] == 625.0


def test_chat_followup_replacement_preserves_unmentioned_previous_items(monkeypatch):
    monkeypatch.setattr(procurement_agent, "retrieve_products", lambda message, intent, top_k=30: PRODUCTS)
    client = TestClient(app)

    client.post(
        "/api/chat",
        json={
            "session_id": "followup-replacement-session",
            "message": "We need headsets and keyboards for 5 people. Prefer high rating.",
        },
    )
    followup = client.post(
        "/api/chat",
        json={
            "session_id": "followup-replacement-session",
            "message": "Replace the headset with a lower cost model delivered within 5 days.",
        },
    ).json()

    by_category = {
        item["category"]: item["product_id"]
        for item in followup["recommended_plan"]["items"]
    }
    assert followup["used_previous_context"] is True
    assert followup["parsed_intent"]["revision_intent"] == "replace_product"
    assert by_category == {
        "Headset": "P-team-headset",
        "Keyboard": "P-premium-keyboard",
    }
