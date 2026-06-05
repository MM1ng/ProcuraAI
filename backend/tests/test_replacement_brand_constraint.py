from fastapi.testclient import TestClient

from main import app


def test_replacement_followup_enforces_requested_brand_and_preserves_other_items():
    client = TestClient(app)
    session_id = "replacement-brand-constraint-session"

    first = client.post(
        "/api/chat",
        json={
            "session_id": session_id,
            "message": (
                "Please recommend office equipment for a remote team of 10 people. "
                "Each person needs a webcam, headset and docking station. Budget is under $4000. "
                "Prefer products with rating above 4.2 and delivery within 5 days."
            ),
        },
    ).json()
    followup = client.post(
        "/api/chat",
        json={
            "session_id": session_id,
            "message": "Replace the docking station with a Dell model, but keep the webcam and headset unchanged.",
        },
    ).json()

    first_by_category = {
        item["category"]: item
        for item in first["recommended_plan"]["items"]
    }
    followup_by_category = {
        item["category"]: item
        for item in followup["recommended_plan"]["items"]
    }

    assert followup["used_previous_context"] is True
    assert followup["parsed_intent"]["replacement_brand"] == "Dell"
    assert followup["parsed_intent"]["replacement_categories"] == ["Docking Station"]
    assert followup_by_category["Docking Station"]["brand"] == "Dell"
    assert followup_by_category["Webcam"]["product_id"] == first_by_category["Webcam"]["product_id"]
    assert followup_by_category["Headset"]["product_id"] == first_by_category["Headset"]["product_id"]
