"""Runtime failures must preserve baseline authority and expose degraded state."""
from contextlib import contextmanager
import hashlib
import json
import sqlite3
from threading import Event
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from app.core.config import get_settings
from app.decision import gateway, runtime
from app.decision.contracts import decision_context
from app.decision.schemas import DecisionResult, IntentLabel
from main import app
from test_session_http_process_recovery import server, _client, _init, _ok


@pytest.fixture
def enabled(monkeypatch):
    monkeypatch.setenv("JEV_DECISION_ENABLED", "true")
    monkeypatch.setenv("JEV_DECISION_TRAFFIC_PERCENT", "100")
    monkeypatch.setenv("JEV_SHADOW_ENABLED", "false")
    get_settings.cache_clear()
    runtime.set_decision_enabled(True, "isolated-test-setup")


def result(label=IntentLabel.MODIFY_PLAN):
    return DecisionResult(label=label, provider="jev", model="fixture", latency_ms=1)


def resolve(provider=None, label=IntentLabel.RECOMMEND):
    return gateway.resolve_jev_decision(text="make plan cheaper", cohort_key="fault-test-session",
        fallback_label=label, provider_factory=provider or (lambda: SimpleNamespace(classify_intent=lambda *a, **k: result())))


def assert_baseline(outcome, fault, reason=None):
    assert outcome.label is IntentLabel.RECOMMEND
    assert outcome.decision_source == "baseline" and outcome.authoritative is True
    assert outcome.fallback_used is True
    assert outcome.fallback_reason == (reason or fault)
    audit = decision_context(contract=outcome, transaction_gate="block")
    assert audit["runtime_available"] is False
    assert audit["runtime_faults"] == [fault]


@contextmanager
def broken_store(mode, monkeypatch):
    path = runtime.RUNTIME_STATE_PATH
    connection = None
    if mode == "corrupt":
        path.write_bytes(b"not a SQLite database\n")
    elif mode in {"last_change_json", "count", "override", "last_change_shape", "last_change_timestamp"}:
        runtime.set_decision_enabled(get_settings().jev_decision_enabled, "fixture")
        with sqlite3.connect(path) as db:
            if mode == "last_change_json":
                db.execute("UPDATE decision_runtime_state SET last_change_json='{' WHERE singleton=1")
            elif mode == "count":
                db.execute("UPDATE decision_runtime_state SET consecutive_failures='invalid-counter' WHERE singleton=1")
            elif mode == "override":
                db.execute("PRAGMA ignore_check_constraints=ON")
                db.execute("UPDATE decision_runtime_state SET enabled_override='invalid-override' WHERE singleton=1")
            else:
                change = [] if mode == "last_change_shape" else {"enabled": True, "reason": "fixture", "changed_at": "invalid-date"}
                db.execute("UPDATE decision_runtime_state SET last_change_json=? WHERE singleton=1", (json.dumps(change),))
    elif mode == "locked":
        runtime.set_decision_enabled(True, "fixture")
        connection = sqlite3.connect(path)
        connection.execute("BEGIN EXCLUSIVE")
    elif mode == "path":
        parent = path.parent / "file-not-directory"
        parent.write_bytes(b"fixture")
        path = parent / "runtime.sqlite3"
        monkeypatch.setattr(runtime, "RUNTIME_STATE_PATH", path)
    elif mode == "permission":
        def denied(*args):
            raise PermissionError("synthetic-private-path-do-not-leak")
        monkeypatch.setattr(runtime.DecisionRuntimeStore, "_connect", denied)
    before = path.read_bytes() if path.is_file() else None
    try:
        yield path
        assert (path.read_bytes() if path.is_file() else None) == before
    finally:
        if connection is not None:
            connection.rollback(); connection.close()


@pytest.mark.parametrize("mode", ["corrupt", "last_change_json", "locked", "path", "permission", "count", "override", "last_change_shape", "last_change_timestamp"])
def test_initial_runtime_read_fault_returns_baseline_without_repair(enabled, monkeypatch, mode):
    provider = Mock(side_effect=AssertionError("provider must not run"))
    with broken_store(mode, monkeypatch):
        outcome = resolve(provider)
        assert_baseline(outcome, "runtime_initial_read_failed")
    provider.assert_not_called()


@pytest.mark.parametrize("percent,configured", [(0, True), (100, False)])
@pytest.mark.parametrize("mode", ["corrupt", "count"])
def test_zero_or_disabled_runtime_fault_never_calls_provider(monkeypatch, percent, configured, mode):
    monkeypatch.setenv("JEV_DECISION_TRAFFIC_PERCENT", str(percent))
    monkeypatch.setenv("JEV_DECISION_ENABLED", str(configured).lower())
    get_settings.cache_clear()
    provider = Mock(side_effect=AssertionError("provider must not run"))
    with broken_store(mode, monkeypatch):
        assert_baseline(resolve(provider), "runtime_initial_read_failed")
    provider.assert_not_called()


@pytest.mark.parametrize("mode,reason", [("capacity", "capacity"), ("timeout", "timeout"),
    ("exception", "RuntimeError"), ("schema", "invalid_response"),
    ("mapping", "mapping_error"), ("thread_start", "thread_start_error")])
@pytest.mark.parametrize("write_error", [sqlite3.OperationalError, PermissionError])
def test_provider_fallback_retains_reason_and_separate_failure_write_fault(enabled, monkeypatch, mode, reason, write_error):
    def unavailable(*args):
        raise write_error("synthetic-private-detail-do-not-leak")
    monkeypatch.setattr(gateway, "record_provider_failure", unavailable)
    release, finished = Event(), Event()
    gate = gateway.ShadowCapacityGate(1)
    monkeypatch.setattr(gateway, "_authority_capacity_gate", lambda *_: gate)
    if mode == "capacity":
        gate.try_acquire()
    if mode == "thread_start":
        monkeypatch.setattr(gateway.threading.Thread, "start", lambda *_: (_ for _ in ()).throw(RuntimeError("start")))
    if mode == "mapping":
        monkeypatch.setattr(gateway, "map_decision_label", lambda *_: (_ for _ in ()).throw(ValueError("map")))
    if mode == "timeout":
        settings = get_settings()
        monkeypatch.setattr(gateway, "get_settings", lambda: SimpleNamespace(**{**settings.__dict__, "jev_timeout_ms": 1}))
    def classify(*args, **kwargs):
        try:
            if mode == "timeout":
                release.wait(2)
            if mode == "exception":
                raise RuntimeError("synthetic-provider-detail-do-not-leak")
            return object() if mode == "schema" else result()
        finally:
            finished.set()
    try:
        outcome = resolve(lambda: SimpleNamespace(classify_intent=classify))
        assert_baseline(outcome, "runtime_failure_write_failed", reason)
        assert "do-not-leak" not in json.dumps(decision_context(contract=outcome, transaction_gate="block"))
    finally:
        release.set()
        if mode == "capacity":
            gate.release_after_provider_completion()
        if mode == "timeout":
            assert finished.wait(2)


@pytest.mark.parametrize("operation", ["success_write", "final_read"])
def test_verified_provider_result_discarded_when_runtime_cannot_be_verified(enabled, monkeypatch, operation):
    if operation == "success_write":
        monkeypatch.setattr(gateway, "record_provider_success", lambda: (_ for _ in ()).throw(sqlite3.OperationalError("locked")))
        fault = "runtime_success_write_failed"
    else:
        calls = 0
        original = gateway.decision_enabled
        def read():
            nonlocal calls
            calls += 1
            if calls == 2:
                raise sqlite3.DatabaseError("private database")
            return original()
        monkeypatch.setattr(gateway, "decision_enabled", read)
        fault = "runtime_final_read_failed"
    assert_baseline(resolve(), fault)


@pytest.mark.parametrize("label", [IntentLabel.CONFIRM_ORDER, IntentLabel.PAYMENT, IntentLabel.CANCEL, IntentLabel.ORDER_STATUS])
def test_runtime_fault_preserves_protected_baseline_label(enabled, monkeypatch, label):
    provider = Mock(side_effect=AssertionError("protected route must not invoke provider"))
    with broken_store("corrupt", monkeypatch):
        outcome = resolve(provider, label)
        assert outcome.label is label and outcome.decision_source == "baseline" and outcome.authoritative
        assert outcome.runtime_faults == ("runtime_initial_read_failed",)
    provider.assert_not_called()


@pytest.mark.parametrize("mode", ["corrupt", "last_change_json", "locked", "path", "permission", "count", "override", "last_change_shape", "last_change_timestamp"])
def test_status_reports_degraded_unknown_fields_without_repair(enabled, monkeypatch, mode):
    with broken_store(mode, monkeypatch):
        response = TestClient(app, raise_server_exceptions=False).get("/api/decision/status")
        assert response.status_code == 200
        state = response.json()
        assert state["runtime_available"] is False
        assert state["runtime_faults"] == ["runtime_status_read_failed"]
        assert state["jev_decision_enabled"] is False and state["jev_authority_active"] is False
        assert state["consecutive_failures"] is None and state["last_change"] is None
        assert "do-not-leak" not in response.text


@pytest.mark.parametrize("action", ["enable", "rollback"])
@pytest.mark.parametrize("mode", ["corrupt", "count", "override", "last_change_shape"])
def test_control_write_failure_is_503_after_existing_auth_gate(enabled, monkeypatch, action, mode):
    monkeypatch.setenv("DECISION_CONTROL_TOKEN", "synthetic-control-only")
    get_settings.cache_clear()
    with broken_store(mode, monkeypatch):
        client = TestClient(app, raise_server_exceptions=False)
        assert client.post(f"/api/decision/{action}").status_code == 401
        response = client.post(f"/api/decision/{action}", headers={"X-Decision-Token": "synthetic-control-only"})
        assert response.status_code == 503
        assert response.json()["detail"]["code"] == "DECISION_RUNTIME_UNAVAILABLE"
        assert "status" not in response.json()


def test_control_enable_cannot_report_success_when_post_write_status_unavailable(enabled, monkeypatch):
    monkeypatch.setenv("DECISION_CONTROL_TOKEN", "synthetic-control-only")
    get_settings.cache_clear()
    import app.api.decision as api
    original = api.set_decision_enabled
    def commit_then_break(*args):
        change = original(*args)
        with sqlite3.connect(runtime.RUNTIME_STATE_PATH) as db:
            db.execute("UPDATE decision_runtime_state SET last_change_json='{' WHERE singleton=1")
        return change
    monkeypatch.setattr(api, "set_decision_enabled", commit_then_break)
    response = TestClient(app, raise_server_exceptions=False).post("/api/decision/enable", headers={"X-Decision-Token": "synthetic-control-only"})
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "DECISION_RUNTIME_UNAVAILABLE"


def test_rollback_during_provider_call_does_not_count_failure_or_overwrite_manual_reason(enabled, monkeypatch):
    monkeypatch.setenv("JEV_AUTO_ROLLBACK_ERROR_THRESHOLD", "1")
    get_settings.cache_clear()
    before = None
    def classify(*args, **kwargs):
        nonlocal before
        runtime.set_decision_enabled(False, "manual-runtime-fault-regression")
        before = runtime.DecisionRuntimeStore(runtime.RUNTIME_STATE_PATH).get_state()
        return result()
    outcome = resolve(lambda: SimpleNamespace(classify_intent=classify))
    after = runtime.DecisionRuntimeStore(runtime.RUNTIME_STATE_PATH).get_state()
    assert outcome.decision_source == "baseline" and outcome.authoritative is True
    assert outcome.fallback_reason == "rollback_during_provider_call"
    assert after == before
    assert after["consecutive_failures"] == 0
    assert after["last_change"]["reason"] == "manual-runtime-fault-regression"


def test_healthy_runtime_remains_available_and_authoritative_provider_is_allowed(enabled):
    outcome = resolve()
    assert outcome.decision_source == "jev" and outcome.label is IntentLabel.MODIFY_PLAN
    assert outcome.runtime_available is True and outcome.runtime_faults == ()
    assert outcome.fallback_used is False
    state = TestClient(app).get("/api/decision/status").json()
    assert state["runtime_available"] is True and state["runtime_faults"] == []
    assert state["consecutive_failures"] == 0


def test_success_counter_write_cannot_silently_repair_bad_persisted_count(enabled, monkeypatch):
    with broken_store("count", monkeypatch):
        with pytest.raises(Exception) as caught:
            runtime.record_provider_success()
        assert type(caught.value).__name__ == "RuntimeDataError"


@pytest.mark.parametrize("mode,reason", [("provider_failure", "RuntimeError"), ("capacity", "capacity")])
def test_sqlite_max_failure_counter_saturates_and_still_trips_rollback(enabled, monkeypatch, mode, reason):
    maximum = 9223372036854775807
    with sqlite3.connect(runtime.RUNTIME_STATE_PATH) as db:
        db.execute("UPDATE decision_runtime_state SET consecutive_failures=? WHERE singleton=1", (maximum,))
        schema = db.execute("SELECT sql FROM sqlite_master WHERE type='table'").fetchall()
    gate = gateway.ShadowCapacityGate(1)
    monkeypatch.setattr(gateway, "_authority_capacity_gate", lambda *_: gate)
    provider_calls = []
    if mode == "capacity":
        gate.try_acquire()
    def classify(*args, **kwargs):
        provider_calls.append(1)
        raise RuntimeError("synthetic provider failure")
    try:
        outcome = resolve(lambda: SimpleNamespace(classify_intent=classify))
        assert outcome.decision_source == "baseline" and outcome.authoritative is True
        assert outcome.fallback_used is True and outcome.fallback_reason == reason
        assert outcome.runtime_available is True and outcome.runtime_faults == ()
        assert provider_calls == ([] if mode == "capacity" else [1])
        state = runtime.DecisionRuntimeStore(runtime.RUNTIME_STATE_PATH).get_state()
        assert state["consecutive_failures"] == maximum
        assert state["override"] is False
        assert state["last_change"]["reason"] == f"auto_rollback:{reason}"
        with sqlite3.connect(runtime.RUNTIME_STATE_PATH) as db:
            assert db.execute("SELECT sql FROM sqlite_master WHERE type='table'").fetchall() == schema
            assert db.execute("SELECT count(*) FROM decision_runtime_state").fetchone()[0] == 1
    finally:
        if mode == "capacity":
            gate.release_after_provider_completion()


def test_real_http_agent_and_transaction_gates_survive_corrupt_runtime(server):
    path = server.root / "data/decision_runtime.sqlite3"
    path.write_bytes(b"broken SQLite runtime\n")
    original = hashlib.sha256(path.read_bytes()).hexdigest()
    with _client() as client:
        _init(client)
        sid = _ok(client.post("/api/chat/session"))["session_id"]
        displayed = _ok(client.post("/api/chat", json={"session_id": sid, "message": "请给2名员工推荐办公键盘，预算50元。"}))
        assert displayed["recommended_plan"]["items"]
        assert displayed["recommended_plan"]["plan_id"]
        expected_traces = {displayed["trace_id"]}
        for message in ("不要付款", "暂时不要下单", "How do I pay?", "如果下单会怎样？", "确认这个方案并下单", "确认支付"):
            response = _ok(client.post("/api/chat", json={"session_id": sid, "message": message}))
            expected_traces.add(response["trace_id"])
        assert _ok(client.get("/api/orders"))["total"] == 0
        state = _ok(client.get("/api/decision/status"))
        assert state["runtime_available"] is False and state["jev_authority_active"] is False
    traces = json.loads((server.root / "data/observability_logs.json").read_text(encoding="utf-8"))
    # Each request also emits the unchanged audit-only Shadow skip row.
    traces = [row for row in traces if "session_id" in row]
    assert len(traces) == 7 and {row["trace_id"] for row in traces} == expected_traces
    for trace in traces:
        assert trace["error"] is None
        assert trace["decision_source"] == "baseline" and trace["authoritative"] is True
        assert trace["runtime_available"] is False and trace["runtime_faults"] == ["runtime_initial_read_failed"]
    assert hashlib.sha256(path.read_bytes()).hexdigest() == original
