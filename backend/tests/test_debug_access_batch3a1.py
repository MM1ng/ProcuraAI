"""Batch 3A-1: real HTTP authorization, isolated storage, no live providers."""
import json
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from app.api import llm, observability
from app.observability import local_tracer
from app.services import llm_service, order_service
from main import app

ADMIN = "fixture-observability-admin-only"
DEBUG = "fixture-llm-debug-only"
ORIGIN = "http://127.0.0.1:3000"


@pytest.fixture
def boundary(monkeypatch, tmp_path):
    for name in ("OBSERVABILITY_ADMIN_TOKEN", "LLM_TEST_TOKEN", "LLM_TEST_ENABLED"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("JEV_DECISION_ENABLED", "false")
    monkeypatch.setenv("JEV_DECISION_TRAFFIC_PERCENT", "0")
    monkeypatch.setenv("JEV_SHADOW_ENABLED", "false")
    forbidden = Mock(side_effect=AssertionError("External model path must not execute"))
    monkeypatch.setattr(llm, "safe_llm_invoke", forbidden, raising=False)
    monkeypatch.setattr(llm_service, "safe_llm_invoke", forbidden)
    monkeypatch.setattr(llm_service, "get_llm_model", forbidden)
    monkeypatch.setattr(llm_service, "_call_dashscope", forbidden)
    reader = Mock(wraps=observability.observability_traces)
    monkeypatch.setattr(observability, "observability_traces", reader)
    rows = [{"owner_actor_id": "caller-a", "message": "private-a"},
            {"owner_actor_id": "caller-b", "message": "private-b"}]
    assert local_tracer.TRACE_FILE.is_relative_to(tmp_path)
    assert order_service.ORDERS_FILE.is_relative_to(tmp_path)
    local_tracer.TRACE_FILE.write_text(json.dumps(rows), encoding="utf-8")
    client = TestClient(app, base_url="http://127.0.0.1:8000",
                        client=("127.0.0.1", 50000), raise_server_exceptions=False)
    yield client, reader, forbidden, rows
    client.close()


@pytest.mark.parametrize("configured,supplied", [
    (None, None), (None, ADMIN), ("", ADMIN), ("   ", ADMIN),
    (ADMIN, None), (ADMIN, "wrong"), (ADMIN, DEBUG),
])
def test_traces_denied_before_read(boundary, monkeypatch, configured, supplied):
    client, reader, forbidden, _ = boundary
    if configured is not None:
        monkeypatch.setenv("OBSERVABILITY_ADMIN_TOKEN", configured)
    headers = {"X-Observability-Token": supplied} if supplied else {}
    response = client.get("/api/observability/traces", headers=headers)
    reader.assert_not_called()
    forbidden.assert_not_called()
    assert response.status_code == 403
    assert response.headers["cache-control"] == "no-store"
    assert "private-" not in response.text


def test_normal_anonymous_caller_cannot_read_shared_traces(boundary, monkeypatch):
    client, reader, forbidden, _ = boundary
    monkeypatch.setenv("OBSERVABILITY_ADMIN_TOKEN", ADMIN)
    init = client.post("/api/caller/init", headers={"Origin": ORIGIN})
    assert init.status_code == 200
    response = client.get("/api/observability/traces")
    reader.assert_not_called()
    forbidden.assert_not_called()
    assert response.status_code == 403
    assert response.headers["cache-control"] == "no-store"
    assert "private-" not in response.text


def test_admin_can_read_real_isolated_traces(boundary, monkeypatch):
    client, reader, forbidden, rows = boundary
    monkeypatch.setenv("OBSERVABILITY_ADMIN_TOKEN", ADMIN)
    response = client.get("/api/observability/traces?limit=1",
                          headers={"X-Observability-Token": ADMIN})
    assert response.status_code == 200
    assert response.json() == {"items": [rows[-1]], "total": 1}
    assert response.headers["cache-control"] == "no-store"
    reader.assert_called_once_with(limit=1)
    forbidden.assert_not_called()


@pytest.mark.parametrize("enabled,environment,configured,supplied,status", [
    (None, "development", DEBUG, DEBUG, 404),
    ("false", "development", DEBUG, DEBUG, 404),
    ("garbage", "development", DEBUG, DEBUG, 404),
    ("true", "production", DEBUG, DEBUG, 404),
    ("true", "prod", DEBUG, DEBUG, 404),
    ("true", "staging", DEBUG, DEBUG, 404),
    ("true", "", DEBUG, DEBUG, 404),
    ("true", "development", None, DEBUG, 403),
    ("true", "development", "", DEBUG, 403),
    ("true", "development", "   ", DEBUG, 403),
    ("true", "development", DEBUG, None, 403),
    ("true", "development", DEBUG, "wrong", 403),
    ("true", "development", DEBUG, ADMIN, 403),
])
def test_llm_denied_never_enters_model_chain(boundary, monkeypatch, enabled,
                                            environment, configured, supplied, status):
    client, reader, forbidden, _ = boundary
    monkeypatch.setenv("APP_ENV", environment)
    if enabled is not None:
        monkeypatch.setenv("LLM_TEST_ENABLED", enabled)
    if configured is not None:
        monkeypatch.setenv("LLM_TEST_TOKEN", configured)
    headers = {"X-LLM-Test-Token": supplied} if supplied else {}
    response = client.post("/api/llm/test", json={"message": "test"}, headers=headers)
    forbidden.assert_not_called()
    reader.assert_not_called()
    assert response.status_code == status
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("environment", ["development", "test"])
def test_authorized_debug_is_local_mock_even_when_mock_flag_false(boundary, monkeypatch, environment):
    client, reader, forbidden, _ = boundary
    monkeypatch.setenv("APP_ENV", environment)
    monkeypatch.setenv("LLM_TEST_ENABLED", "true")
    monkeypatch.setenv("LLM_TEST_TOKEN", DEBUG)
    monkeypatch.setenv("USE_MOCK_LLM", "false")
    response = client.post("/api/llm/test", json={"message": "test"},
                           headers={"X-LLM-Test-Token": DEBUG})
    forbidden.assert_not_called()
    reader.assert_not_called()
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    result = response.json()
    assert result["model_provider"] == "mock"
    assert result["used_mock_llm"] is True
    assert result["retry_count"] == 0
    assert result["fallback_reason"] == "authorized_local_debug_mock"
    assert result["content"] == llm_service.mock_llm_response("test", purpose="llm_test")


def test_business_caller_not_debug_authority(boundary, monkeypatch):
    client, _, forbidden, _ = boundary
    monkeypatch.setenv("LLM_TEST_ENABLED", "true")
    monkeypatch.setenv("LLM_TEST_TOKEN", DEBUG)
    init = client.post("/api/caller/init", headers={"Origin": ORIGIN})
    assert init.status_code == 200
    response = client.post("/api/llm/test", json={"message": "test"},
                           headers={"Origin": ORIGIN, "X-CSRF-Token": init.json()["csrf_token"]})
    forbidden.assert_not_called()
    assert response.status_code == 403
    assert response.headers["cache-control"] == "no-store"


def test_admin_comparison_uses_constant_time(boundary, monkeypatch):
    # Import during execution so the same source can run red before helper exists.
    from app.services import debug_access
    client, _, forbidden, _ = boundary
    monkeypatch.setenv("OBSERVABILITY_ADMIN_TOKEN", ADMIN)
    compare = Mock(wraps=debug_access.hmac.compare_digest)
    monkeypatch.setattr(debug_access.hmac, "compare_digest", compare)
    assert client.get("/api/observability/traces",
                      headers={"X-Observability-Token": ADMIN}).status_code == 200
    compare.assert_called_once_with(ADMIN.encode("utf-8"), ADMIN.encode("utf-8"))
    forbidden.assert_not_called()
