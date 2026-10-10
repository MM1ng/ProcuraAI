from __future__ import annotations

from types import SimpleNamespace
from threading import Event, Thread

import pytest
from fastapi.testclient import TestClient

import app.decision.gateway as gateway
from app.decision.contracts import map_decision_label
from app.decision.runtime import set_decision_enabled
import app.decision.runtime as runtime
from app.decision.schemas import DecisionResult, IntentLabel
from main import app


def resolve_jev_decision(**kwargs):
    return gateway.resolve_jev_decision(cohort_key="authority-contract-test", **kwargs)


@pytest.fixture(autouse=True)
def reset_authority_runtime(isolate_runtime_storage, monkeypatch):
    monkeypatch.setenv("JEV_DECISION_TRAFFIC_PERCENT", "100")
    from app.core.config import get_settings
    get_settings.cache_clear()
    set_decision_enabled(False, "test_setup")
    yield
    set_decision_enabled(False, "test_cleanup")


def _result(label: IntentLabel) -> DecisionResult:
    return DecisionResult(
        label=label,
        confidence=0.95,
        provider="jev",
        model="jev-test",
        latency_ms=5.0,
    )


def test_disabled_authority_keeps_baseline(monkeypatch):
    set_decision_enabled(False, "test")
    outcome = resolve_jev_decision(
        text="recommend keyboards",
        fallback_label=IntentLabel.RECOMMEND,
        provider_factory=lambda: SimpleNamespace(classify_intent=lambda *_args, **_kwargs: _result(IntentLabel.MODIFY_PLAN)),
    )
    assert outcome.decision_source == "baseline"
    assert outcome.label == IntentLabel.RECOMMEND
    assert outcome.fallback_used is False


def test_enabled_authority_uses_jev_for_safe_non_transaction(monkeypatch):
    set_decision_enabled(True, "test")
    outcome = resolve_jev_decision(
        text="make the keyboard plan cheaper",
        fallback_label=IntentLabel.RECOMMEND,
        provider_factory=lambda: SimpleNamespace(classify_intent=lambda *_args, **_kwargs: _result(IntentLabel.MODIFY_PLAN)),
    )
    assert outcome.decision_source == "jev"
    assert outcome.label == IntentLabel.MODIFY_PLAN
    set_decision_enabled(False, "test_cleanup")


def test_transaction_label_cannot_bypass_deterministic_gate():
    set_decision_enabled(True, "test")
    outcome = resolve_jev_decision(
        text="How do I pay?",
        fallback_label=IntentLabel.CLARIFY,
        provider_factory=lambda: SimpleNamespace(classify_intent=lambda *_args, **_kwargs: _result(IntentLabel.PAYMENT)),
    )
    assert outcome.decision_source == "baseline"
    assert outcome.fallback_used is True
    assert outcome.fallback_reason == "transaction_gate_blocked"
    set_decision_enabled(False, "test_cleanup")


def test_manual_rollback_disables_authority(monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DECISION_CONTROL_TOKEN", "test-control-token")
    from app.core.config import get_settings
    get_settings.cache_clear()
    set_decision_enabled(True, "test")
    response = TestClient(app).post("/api/decision/rollback", headers={"X-Decision-Token": "test-control-token"})
    assert response.status_code == 200
    assert response.json()["decision_source"] == "baseline"
    status = TestClient(app).get("/api/decision/status")
    assert status.json()["jev_decision_enabled"] is False


def test_decision_control_rejects_missing_authentication(monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DECISION_CONTROL_TOKEN", "test-control-token")
    from app.core.config import get_settings
    get_settings.cache_clear()
    response = TestClient(app).post("/api/decision/rollback")
    assert response.status_code == 401


def test_authoritative_capacity_is_fail_closed(monkeypatch):
    started = Event()
    release = Event()

    class BlockingProvider:
        def classify_intent(self, *_args, **_kwargs):
            started.set()
            release.wait(2)
            return _result(IntentLabel.RECOMMEND)

    settings = SimpleNamespace(
        jev_max_in_flight=1, jev_timeout_ms=1000, jev_fallback_enabled=True,
        jev_decision_traffic_percent=100,
        jev_auto_rollback_error_threshold=3,
    )
    monkeypatch.setattr(gateway, "get_settings", lambda: settings)
    set_decision_enabled(True, "capacity-test")
    first_result = {}
    worker = Thread(target=lambda: first_result.setdefault("value", resolve_jev_decision(
        text="recommend keyboards", fallback_label=IntentLabel.RECOMMEND,
        provider_factory=BlockingProvider,
    )))
    worker.start()
    assert started.wait(1)
    second = resolve_jev_decision(
        text="recommend mice", fallback_label=IntentLabel.RECOMMEND,
        provider_factory=BlockingProvider,
    )
    assert second.decision_source == "baseline"
    assert second.fallback_used is True
    assert second.fallback_reason == "capacity"
    release.set()
    worker.join(2)
    set_decision_enabled(False, "capacity-test-cleanup")


def test_consecutive_provider_failures_trip_automatic_rollback(monkeypatch):
    settings = SimpleNamespace(
        app_env="test",
        jev_max_in_flight=2, jev_timeout_ms=1000, jev_fallback_enabled=True,
        jev_decision_traffic_percent=100,
        jev_auto_rollback_error_threshold=2,
        jev_shadow_enabled=False, jev_decision_enabled=True,
    )
    monkeypatch.setattr(gateway, "get_settings", lambda: settings)
    monkeypatch.setattr(runtime, "get_settings", lambda: settings)
    set_decision_enabled(True, "provider-failure-test")
    calls = 0

    class FailingProvider:
        def classify_intent(self, *_args, **_kwargs):
            nonlocal calls
            calls += 1
            raise RuntimeError("provider unavailable")

    for _ in range(2):
        result = resolve_jev_decision(
            text="recommend keyboards", fallback_label=IntentLabel.RECOMMEND,
            provider_factory=FailingProvider,
        )
        assert result.decision_source == "baseline"
        assert result.fallback_used is True
        assert result.fallback_reason == "RuntimeError"

    assert calls == 2
    assert runtime.decision_enabled() is False
    assert runtime.status()["last_change"]["reason"] == "auto_rollback:RuntimeError"

    third = resolve_jev_decision(
        text="recommend mice", fallback_label=IntentLabel.RECOMMEND,
        provider_factory=FailingProvider,
    )
    assert third.decision_source == "baseline"
    assert third.fallback_used is False
    assert calls == 2


def test_capacity_exhaustion_counts_toward_automatic_rollback(monkeypatch):
    started = Event()
    release = Event()
    settings = SimpleNamespace(
        app_env="test",
        jev_max_in_flight=1, jev_timeout_ms=2000, jev_fallback_enabled=True,
        jev_decision_traffic_percent=100,
        jev_auto_rollback_error_threshold=2,
        jev_shadow_enabled=False, jev_decision_enabled=True,
    )
    monkeypatch.setattr(gateway, "get_settings", lambda: settings)
    monkeypatch.setattr(runtime, "get_settings", lambda: settings)
    set_decision_enabled(True, "capacity-auto-rollback-test")
    calls = 0

    class BlockingProvider:
        def classify_intent(self, *_args, **_kwargs):
            nonlocal calls
            calls += 1
            started.set()
            release.wait(2)
            return _result(IntentLabel.RECOMMEND)

    worker = Thread(target=lambda: resolve_jev_decision(
        text="recommend keyboards", fallback_label=IntentLabel.RECOMMEND,
        provider_factory=BlockingProvider,
    ))
    worker.start()
    assert started.wait(1)

    for text in ("recommend mice", "recommend monitors"):
        result = resolve_jev_decision(
            text=text, fallback_label=IntentLabel.RECOMMEND,
            provider_factory=BlockingProvider,
        )
        assert result.decision_source == "baseline"
        assert result.fallback_used is True
        assert result.fallback_reason == "capacity"

    assert runtime.decision_enabled() is False
    assert runtime.status()["last_change"]["reason"] == "auto_rollback:capacity"
    after_rollback = resolve_jev_decision(
        text="recommend chairs", fallback_label=IntentLabel.RECOMMEND,
        provider_factory=BlockingProvider,
    )
    assert after_rollback.decision_source == "baseline"
    assert after_rollback.fallback_used is False
    assert calls == 1

    release.set()
    worker.join(2)
    assert not worker.is_alive()
    assert runtime.decision_enabled() is False


def test_unknown_jev_label_maps_to_clarify():
    assert map_decision_label(IntentLabel.UNKNOWN) is IntentLabel.CLARIFY


def test_provider_error_returns_baseline_even_when_fallback_flag_is_disabled(monkeypatch):
    settings = SimpleNamespace(
        jev_max_in_flight=1, jev_timeout_ms=1000, jev_fallback_enabled=False,
        jev_decision_traffic_percent=100,
        jev_auto_rollback_error_threshold=3,
    )
    monkeypatch.setattr(gateway, "get_settings", lambda: settings)
    set_decision_enabled(True, "fallback-disabled-test")

    class FailingProvider:
        def classify_intent(self, *_args, **_kwargs):
            raise RuntimeError("provider unavailable")

    result = resolve_jev_decision(
        text="make the plan cheaper",
        fallback_label=IntentLabel.RECOMMEND,
        provider_factory=FailingProvider,
    )
    assert result.label is IntentLabel.RECOMMEND
    assert result.decision_source == "baseline"
    assert result.fallback_used is True
    assert result.fallback_reason == "RuntimeError"
    set_decision_enabled(False, "fallback-disabled-test-cleanup")


def test_timeout_returns_baseline_even_when_fallback_flag_is_disabled(monkeypatch):
    release = Event()
    settings = SimpleNamespace(
        jev_max_in_flight=1, jev_timeout_ms=1, jev_fallback_enabled=False,
        jev_decision_traffic_percent=100,
        jev_auto_rollback_error_threshold=3,
    )
    monkeypatch.setattr(gateway, "get_settings", lambda: settings)
    set_decision_enabled(True, "fallback-disabled-timeout-test")

    class SlowProvider:
        def classify_intent(self, *_args, **_kwargs):
            release.wait(2)
            return _result(IntentLabel.CONFIRM_ORDER)

    result = resolve_jev_decision(
        text="make the plan cheaper",
        fallback_label=IntentLabel.RECOMMEND,
        provider_factory=SlowProvider,
    )
    assert result.label is IntentLabel.RECOMMEND
    assert result.decision_source == "baseline"
    assert result.fallback_used is True
    assert result.fallback_reason == "timeout"
    release.set()
    set_decision_enabled(False, "fallback-disabled-timeout-cleanup")
