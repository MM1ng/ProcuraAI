from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.decision.runtime import DecisionRuntimeStore
import app.decision.runtime as runtime
from main import app


def test_runtime_store_instances_share_rollback_and_failure_state(tmp_path):
    state_path = tmp_path / "shared-decision-runtime.sqlite3"
    worker_one = DecisionRuntimeStore(state_path)
    worker_two = DecisionRuntimeStore(state_path)

    worker_one.set_decision_enabled(True, "test-enable")
    assert worker_two.decision_enabled(configured_enabled=False) is True
    assert worker_two.record_provider_failure("timeout", threshold=2) is False
    assert worker_one.get_state()["consecutive_failures"] == 1

    assert worker_two.record_provider_failure("capacity", threshold=2) is True
    assert worker_one.decision_enabled(configured_enabled=True) is False
    assert worker_one.get_state()["last_change"]["reason"] == "auto_rollback:capacity"

    worker_two.set_decision_enabled(False, "manual-rollback")
    assert worker_one.get_state()["last_change"]["reason"] == "manual-rollback"


def test_success_resets_shared_failure_streak_without_reenabling_rollback(tmp_path):
    store = DecisionRuntimeStore(tmp_path / "decision-runtime.sqlite3")
    store.set_decision_enabled(True, "test-enable")
    assert store.record_provider_failure("timeout", threshold=3) is False
    store.record_provider_success()
    assert store.get_state()["consecutive_failures"] == 0
    assert store.decision_enabled(configured_enabled=False) is True

    store.record_provider_failure("timeout", threshold=1)
    assert store.decision_enabled(configured_enabled=True) is False
    store.record_provider_success()
    assert store.decision_enabled(configured_enabled=True) is False


def test_production_allows_authenticated_rollback_but_rejects_enable(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("DECISION_CONTROL_TOKEN", "test-control-token")
    monkeypatch.setenv("JEV_DECISION_ENABLED", "true")
    get_settings.cache_clear()
    runtime.set_decision_enabled(True, "seed-enabled-state")

    enable = TestClient(app).post(
        "/api/decision/enable", headers={"X-Decision-Token": "test-control-token"},
    )
    assert enable.status_code == 404
    assert TestClient(app).get("/api/decision/status").json()["jev_decision_enabled"] is False

    unauthenticated_rollback = TestClient(app).post("/api/decision/rollback")
    assert unauthenticated_rollback.status_code == 401

    rollback = TestClient(app).post(
        "/api/decision/rollback", headers={"X-Decision-Token": "test-control-token"},
    )
    assert rollback.status_code == 200
    status = TestClient(app).get("/api/decision/status").json()
    assert status["jev_decision_enabled"] is False
    assert status["last_change"]["reason"] == "manual_rollback"
    get_settings.cache_clear()


def test_authenticated_dev_enable_with_zero_traffic_still_reports_baseline(monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DECISION_CONTROL_TOKEN", "test-control-token")
    monkeypatch.setenv("JEV_DECISION_TRAFFIC_PERCENT", "0")
    get_settings.cache_clear()
    response = TestClient(app).post(
        "/api/decision/enable", headers={"X-Decision-Token": "test-control-token"},
    )
    assert response.status_code == 200
    assert response.json()["decision_source"] == "baseline"
    assert response.json()["jev_decision_traffic_percent"] == 0
    state = TestClient(app).get("/api/decision/status").json()
    assert state["jev_decision_enabled"] is True
    assert state["jev_authority_active"] is False
