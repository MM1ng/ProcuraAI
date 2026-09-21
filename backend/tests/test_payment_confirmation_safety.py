from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import stripe
from fastapi.testclient import TestClient

from app.api import payments as payments_api
from app.core.config import Settings
from app.services import order_service, product_service, stripe_payment_service
from main import app


@pytest.fixture
def confirmation(monkeypatch, tmp_path):
    monkeypatch.setattr(order_service, "ORDERS_FILE", tmp_path / "orders.json")
    monkeypatch.setattr(product_service, "load_products_from_csv", lambda: [
        {"product_id": "A", "name": "Canonical product", "price": 25},
    ])
    order = order_service.create_order_from_plan({"items": [{"product_id": "A", "quantity": 4}]})
    order["stripe_session_id"] = "cs_test_bound"
    order_service.save_order(order)
    settings = SimpleNamespace(app_env="production", allow_mock_payment=False,
                               use_mock_payment=False, stripe_secret_key="sk_test_fixture")
    monkeypatch.setattr(payments_api, "get_settings", lambda: settings)
    monkeypatch.setattr(stripe_payment_service, "get_settings", lambda: settings)
    response = {
        "id": "cs_test_bound", "object": "checkout.session", "payment_status": "paid",
        "metadata": {"order_id": order["order_id"]}, "client_reference_id": order["order_id"],
        "amount_total": 10000, "currency": "usd",
    }
    # Return the installed SDK's real Session object, not just a dictionary stub.
    retrieve = Mock(side_effect=lambda *_, **__: stripe.checkout.Session.construct_from(
        deepcopy(response), "sk_test_fixture",
    ))
    create = Mock(side_effect=AssertionError("Confirmation must not create checkout"))
    monkeypatch.setattr(stripe_payment_service, "_stripe_module", lambda: SimpleNamespace(
        checkout=SimpleNamespace(Session=SimpleNamespace(retrieve=retrieve, create=create)),
    ))
    update = Mock(wraps=order_service.update_order)
    monkeypatch.setattr(payments_api, "update_order", update)
    monkeypatch.setattr(stripe_payment_service, "update_order", update)
    return SimpleNamespace(order=order, settings=settings, response=response,
                           retrieve=retrieve, create=create, update=update)


def post_confirm(context, **payload):
    return TestClient(app, raise_server_exceptions=False).post(
        "/api/payments/confirm", json=payload or {"order_id": context.order["order_id"]},
    )


def assert_pending(context):
    saved = order_service.get_order(context.order["order_id"])
    assert saved["status"] == "pending_payment"
    assert saved["total_amount"] == 100
    context.update.assert_not_called()
    context.create.assert_not_called()


@pytest.mark.parametrize("environment", ["production", "prod", "staging", "unknown", ""])
def test_production_and_unknown_environments_block_mock_success(confirmation, environment):
    context = confirmation
    context.settings.app_env = environment
    context.settings.allow_mock_payment = True
    context.settings.use_mock_payment = True
    order_service.update_order(context.order["order_id"], {"stripe_session_id": "mock_local"})
    response = TestClient(app).post("/api/payments/mock-success", json={"order_id": context.order["order_id"]})
    assert response.status_code == 403
    assert_pending(context)


@pytest.mark.parametrize("environment", ["development", "test"])
@pytest.mark.parametrize("stored_session", [None, "mock_local"])
def test_explicit_local_mock_success_remains_available_and_idempotent(confirmation, environment, stored_session):
    context = confirmation
    context.settings.app_env = environment
    context.settings.allow_mock_payment = True
    context.settings.use_mock_payment = True
    order_service.update_order(context.order["order_id"], {"stripe_session_id": stored_session})
    client = TestClient(app)
    for _ in range(2):
        result = client.post("/api/payments/mock-success", json={"order_id": context.order["order_id"]})
        assert result.status_code == 200
        assert result.json()["status"] == "paid"
    assert order_service.get_order(context.order["order_id"])["status"] == "paid"
    context.update.assert_called_once()
    context.retrieve.assert_not_called()


def test_mock_success_requires_explicit_permission(confirmation):
    context = confirmation
    context.settings.app_env = "development"
    context.settings.use_mock_payment = True
    order_service.update_order(context.order["order_id"], {"stripe_session_id": "mock_local"})
    response = TestClient(app).post("/api/payments/mock-success", json={"order_id": context.order["order_id"]})
    assert response.status_code == 403
    assert_pending(context)


@pytest.mark.parametrize("use_mock", [True, False])
def test_mock_success_cannot_confirm_a_real_checkout(confirmation, use_mock):
    context = confirmation
    context.settings.app_env = "development"
    context.settings.allow_mock_payment = True
    context.settings.use_mock_payment = use_mock
    response = TestClient(app).post("/api/payments/mock-success", json={"order_id": context.order["order_id"]})
    assert response.status_code == 403
    assert_pending(context)


@pytest.mark.parametrize("stored_session", [None, "mock_local"])
def test_confirm_cannot_bypass_verification_with_missing_or_mock_session(confirmation, stored_session):
    context = confirmation
    order_service.update_order(context.order["order_id"], {"stripe_session_id": stored_session})
    result = post_confirm(context)
    assert result.status_code == 400
    assert_pending(context)
    context.retrieve.assert_not_called()


def test_fake_request_session_cannot_confirm_an_order(confirmation):
    context = confirmation
    result = post_confirm(context, order_id=context.order["order_id"], session_id="fake-session")
    assert result.status_code == 400
    assert_pending(context)
    context.retrieve.assert_not_called()


@pytest.mark.parametrize("provider_error", [TimeoutError("timeout"), ConnectionError("network"),
                                           RuntimeError("provider error"), ValueError("invalid session")])
def test_provider_errors_fail_closed(confirmation, provider_error):
    context = confirmation
    context.retrieve.side_effect = provider_error
    result = post_confirm(context)
    assert result.status_code == 502
    assert str(provider_error) not in result.text
    assert_pending(context)
    context.retrieve.assert_called_once()


@pytest.mark.parametrize("payment_status", ["unpaid", "no_payment_required", None])
def test_unpaid_or_unknown_provider_status_cannot_mark_paid(confirmation, payment_status):
    context = confirmation
    context.response["payment_status"] = payment_status
    result = post_confirm(context)
    assert result.status_code == 400
    assert_pending(context)


@pytest.mark.parametrize("mismatch", [
    {"id": "cs_test_other"}, {"metadata": {"order_id": "ORDER-B"}},
    {"client_reference_id": "ORDER-B"}, {"amount_total": 1}, {"currency": "eur"},
])
def test_paid_session_must_match_order_binding_and_amount(confirmation, mismatch):
    context = confirmation
    context.response.update(mismatch)
    result = post_confirm(context)
    assert result.status_code == 400
    assert_pending(context)


@pytest.mark.parametrize("request_kind", ["order", "session", "both"])
def test_correct_paid_session_is_verified_before_marking_paid(confirmation, request_kind):
    context = confirmation
    payload = {}
    if request_kind in {"order", "both"}:
        payload["order_id"] = context.order["order_id"]
    if request_kind in {"session", "both"}:
        payload["session_id"] = context.order["stripe_session_id"]
    result = post_confirm(context, **payload)
    assert result.status_code == 200
    assert result.json()["status"] == "paid"
    context.retrieve.assert_called_once_with("cs_test_bound", api_key="sk_test_fixture")
    context.update.assert_called_once_with(context.order["order_id"], {"status": "paid"})
    context.create.assert_not_called()
    assert order_service.get_order(context.order["order_id"])["total_amount"] == 100


def test_duplicate_confirmation_is_idempotent(confirmation):
    context = confirmation
    first = post_confirm(context)
    second = post_confirm(context)
    assert first.status_code == second.status_code == 200
    assert first.json()["status"] == second.json()["status"] == "paid"
    context.retrieve.assert_called_once()
    context.update.assert_called_once()
    context.create.assert_not_called()
    orders = order_service.list_orders()
    assert len(orders) == 1
    assert orders[0]["total_amount"] == 100
    assert orders[0]["stripe_session_id"] == "cs_test_bound"


def test_missing_stripe_credentials_fail_closed(confirmation):
    context = confirmation
    context.settings.stripe_secret_key = ""
    result = post_confirm(context)
    assert result.status_code == 502
    assert_pending(context)
    context.retrieve.assert_not_called()


def test_mock_success_is_blocked_when_real_payment_mode_is_active(confirmation):
    context = confirmation
    context.settings.app_env = "development"
    context.settings.allow_mock_payment = True
    order_service.update_order(context.order["order_id"], {"stripe_session_id": None})
    result = TestClient(app).post("/api/payments/mock-success", json={"order_id": context.order["order_id"]})
    assert result.status_code == 403
    assert_pending(context)


def test_mock_mode_does_not_bypass_confirm_provider_verification(confirmation):
    context = confirmation
    context.settings.use_mock_payment = True
    context.response["payment_status"] = "unpaid"
    result = post_confirm(context)
    assert result.status_code == 400
    context.retrieve.assert_called_once()
    assert_pending(context)


def test_fake_stored_session_rejected_by_provider_cannot_mark_paid(confirmation):
    context = confirmation
    order_service.update_order(context.order["order_id"], {"stripe_session_id": "fake-session"})
    context.retrieve.side_effect = RuntimeError("No such checkout session")
    result = post_confirm(context, order_id=context.order["order_id"], session_id="fake-session")
    assert result.status_code == 502
    context.retrieve.assert_called_once_with("fake-session", api_key="sk_test_fixture")
    assert_pending(context)


def test_malformed_provider_response_fails_closed(confirmation):
    context = confirmation
    context.retrieve.side_effect = None
    context.retrieve.return_value = None
    assert post_confirm(context).status_code == 502
    assert_pending(context)


@pytest.mark.parametrize("payload", [{"order_id": "UNKNOWN"}, {"session_id": "fake-session"}])
def test_unknown_order_or_session_never_calls_provider(confirmation, payload):
    context = confirmation
    assert post_confirm(context, **payload).status_code == 404
    assert_pending(context)
    context.retrieve.assert_not_called()


def test_already_paid_order_still_rejects_mismatched_requested_session(confirmation):
    context = confirmation
    assert post_confirm(context).status_code == 200
    result = post_confirm(context, order_id=context.order["order_id"], session_id="cs_other")
    assert result.status_code == 400
    context.retrieve.assert_called_once()
    context.update.assert_called_once()
    assert order_service.get_order(context.order["order_id"])["status"] == "paid"


@pytest.mark.parametrize("environment, flag, expected_env, expected_flag", [
    (None, None, "", False), ("production", "true", "production", True),
    (" development ", "true", "development", True), ("test", "garbage", "test", False),
])
def test_new_environment_settings_are_read_explicitly_and_fail_closed(
    monkeypatch, environment, flag, expected_env, expected_flag,
):
    for name, value in (("APP_ENV", environment), ("ALLOW_MOCK_PAYMENT", flag)):
        if value is None:
            monkeypatch.delenv(name, raising=False)
        else:
            monkeypatch.setenv(name, value)
    settings = Settings()
    assert settings.app_env == expected_env
    assert settings.allow_mock_payment is expected_flag
