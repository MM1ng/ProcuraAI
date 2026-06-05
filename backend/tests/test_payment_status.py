from types import SimpleNamespace

from fastapi.testclient import TestClient

import app.api.payments as payments_api
from main import app


def test_payment_status_reports_mock_or_stripe_mode(monkeypatch):
    monkeypatch.setattr(
        payments_api,
        "get_settings",
        lambda: SimpleNamespace(use_mock_payment=False, stripe_secret_key="sk_test_value"),
    )
    client = TestClient(app)

    response = client.get("/api/payments/status")

    assert response.status_code == 200
    assert response.json() == {
        "payment_provider": "stripe",
        "use_mock_payment": False,
        "has_stripe_secret_key": True,
    }
