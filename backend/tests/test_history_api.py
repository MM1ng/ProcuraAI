from fastapi.testclient import TestClient

from app.api import history
from main import app


def test_history_api_saves_lists_gets_and_deletes_records(tmp_path, monkeypatch):
    history_file = tmp_path / "procurement_history.json"
    monkeypatch.setattr(history.history_service, "HISTORY_FILE", history_file)
    client = TestClient(app)

    payload = {
        "original_request": "Buy keyboards and mice for 5 people",
        "parsed_intent": {"people_count": 5, "categories": ["Keyboard", "Mouse"]},
        "procurement_plan": {
            "items": [
                {
                    "product_id": "P-001",
                    "name": "Reliable Keyboard",
                    "quantity": 5,
                    "unit_price": 40.0,
                    "subtotal": 200.0,
                }
            ],
            "total_amount": 200.0,
        },
        "trace": {"trace_id": "trace-123", "summary": "Selected high-stock keyboard"},
    }

    create_response = client.post("/api/history", json=payload)

    assert create_response.status_code == 200
    created = create_response.json()
    assert created["id"].startswith("HIST-")
    assert created["created_at"]
    assert created["original_request"] == payload["original_request"]
    assert created["total_cost"] == 200.0
    assert created["selected_plan"] == payload["procurement_plan"]

    list_response = client.get("/api/history")

    assert list_response.status_code == 200
    listed = list_response.json()
    assert listed["total"] == 1
    assert listed["items"][0]["id"] == created["id"]
    assert listed["items"][0]["total_cost"] == 200.0

    detail_response = client.get(f"/api/history/{created['id']}")

    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert detail["parsed_intent"] == payload["parsed_intent"]
    assert detail["trace"]["trace_id"] == "trace-123"

    delete_response = client.delete(f"/api/history/{created['id']}")

    assert delete_response.status_code == 200
    assert delete_response.json() == {"deleted": True, "id": created["id"]}
    assert client.get("/api/history").json() == {"items": [], "total": 0}


def test_history_api_returns_404_for_missing_records(tmp_path, monkeypatch):
    history_file = tmp_path / "procurement_history.json"
    monkeypatch.setattr(history.history_service, "HISTORY_FILE", history_file)
    client = TestClient(app)

    detail_response = client.get("/api/history/HIST-MISSING")
    delete_response = client.delete("/api/history/HIST-MISSING")

    assert detail_response.status_code == 404
    assert detail_response.json()["detail"] == "History record not found"
    assert delete_response.status_code == 404
    assert delete_response.json()["detail"] == "History record not found"
