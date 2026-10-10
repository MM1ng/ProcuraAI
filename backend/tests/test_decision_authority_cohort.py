"""Authority canary selection; all runtime state and stores are test-isolated."""

from __future__ import annotations

from threading import Event, Thread
from types import SimpleNamespace

import pytest

from app.core.config import get_settings
from app.decision.contracts import decision_context
from app.decision.contracts import JEV_ROUTE_MAP, map_decision_label
import app.decision.gateway as gateway
from app.decision.gateway import authority_is_sampled, resolve_jev_decision
from app.decision.runtime import set_decision_enabled
from app.decision.schemas import DecisionResult, IntentLabel


@pytest.fixture(autouse=True)
def isolated_canary(monkeypatch, isolate_runtime_storage):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("JEV_DECISION_ENABLED", "false")
    monkeypatch.setenv("JEV_DECISION_TRAFFIC_PERCENT", "0")
    get_settings.cache_clear()
    set_decision_enabled(False, "test_setup")
    yield
    set_decision_enabled(False, "test_cleanup")
    get_settings.cache_clear()


def _result(label=IntentLabel.MODIFY_PLAN):
    return DecisionResult(label=label, provider="jev", model="test", latency_ms=1.0)


def _provider(result=None):
    return lambda: SimpleNamespace(classify_intent=lambda *_args, **_kwargs: result or _result())


def _enable_percent(monkeypatch, percent):
    monkeypatch.setenv("JEV_DECISION_TRAFFIC_PERCENT", str(percent))
    get_settings.cache_clear()
    set_decision_enabled(True, "test_only_enable")


def test_zero_percent_and_missing_identity_never_call_jev(monkeypatch):
    calls = []
    _enable_percent(monkeypatch, 0)
    for key in ("same-session", None, "", "demo-session-001"):
        outcome = resolve_jev_decision(
            text="make the plan cheaper", cohort_key=key,
            fallback_label=IntentLabel.RECOMMEND,
            provider_factory=lambda: calls.append(1),
        )
        assert outcome.decision_source == "baseline"
        assert outcome.fallback_used is False
        assert outcome.authority_bucket == "not_sampled"
    assert calls == []
    _enable_percent(monkeypatch, 100)
    missing = resolve_jev_decision(
        text="make the plan cheaper", cohort_key=None,
        fallback_label=IntentLabel.RECOMMEND,
        provider_factory=lambda: calls.append(1),
    )
    assert missing.decision_source == "baseline"
    assert calls == []
    assert authority_is_sampled("demo-session-001", 100) is False


def test_five_percent_sticky_and_shadow_sampling_independent(monkeypatch):
    _enable_percent(monkeypatch, 5)
    monkeypatch.setenv("JEV_SHADOW_SAMPLE_RATE", "0")
    get_settings.cache_clear()
    keys = [f"session-{index}" for index in range(1000)]
    selected = [key for key in keys if authority_is_sampled(key, 5)]
    assert 30 <= len(selected) <= 70
    assert all(authority_is_sampled(key, 5) for key in selected)
    for key, expected_source in ((selected[0], "jev"), (next(k for k in keys if k not in selected), "baseline")):
        for _ in range(3):
            outcome = resolve_jev_decision(
                text="make the plan cheaper", cohort_key=key,
                fallback_label=IntentLabel.RECOMMEND, provider_factory=_provider(),
            )
            assert outcome.decision_source == expected_source
            audit = decision_context(contract=outcome, transaction_gate="block")
            assert audit["decision_source"] == expected_source
            assert audit["authority_traffic_percent"] == 5
            assert audit["authority_bucket"] == ("jev" if expected_source == "jev" else "not_sampled")
    shadow_rate = get_settings().jev_shadow_sample_rate
    assert shadow_rate == 0


@pytest.mark.parametrize("percent", ["nan", "inf", "-1", "101"])
def test_invalid_traffic_config_is_zero_not_all(monkeypatch, percent):
    _enable_percent(monkeypatch, percent)
    outcome = resolve_jev_decision(
        text="make the plan cheaper", cohort_key="session", fallback_label=IntentLabel.RECOMMEND,
        provider_factory=lambda: pytest.fail("invalid config must never call provider"),
    )
    assert outcome.decision_source == "baseline"
    assert outcome.authority_traffic_percent == 0


@pytest.mark.parametrize(
    ("invalid", "reason"),
    [(object(), "invalid_response"), (SimpleNamespace(label="alien"), "invalid_response")],
)
def test_invalid_schema_or_mapping_falls_back(monkeypatch, invalid, reason):
    _enable_percent(monkeypatch, 100)
    outcome = resolve_jev_decision(
        text="make the plan cheaper", cohort_key="session", fallback_label=IntentLabel.RECOMMEND,
        provider_factory=_provider(invalid),
    )
    assert outcome.decision_source == "baseline"
    assert outcome.fallback_used is True
    assert outcome.fallback_reason == reason


def test_all_labels_are_explicitly_mapped_and_unknown_clarifies():
    assert set(JEV_ROUTE_MAP) == set(IntentLabel)
    assert map_decision_label(IntentLabel.UNKNOWN) is IntentLabel.CLARIFY
    with pytest.raises(ValueError, match="unmapped"):
        map_decision_label("recommend")


def test_mapping_failure_is_recorded_as_baseline_fallback(monkeypatch):
    _enable_percent(monkeypatch, 100)
    monkeypatch.setattr(gateway, "map_decision_label", lambda _label: (_ for _ in ()).throw(ValueError("bad map")))
    outcome = resolve_jev_decision(
        text="make the plan cheaper", cohort_key="session", fallback_label=IntentLabel.RECOMMEND,
        provider_factory=_provider(),
    )
    assert outcome.decision_source == "baseline"
    assert outcome.fallback_used is True
    assert outcome.fallback_reason == "mapping_error"


@pytest.mark.parametrize("text", [
    "不要付款", "暂时不要下单", "How do I pay?", "取消支付",
    'Explain "确认方案B并下单"', "如果下单会怎样？",
])
def test_jev_cannot_upgrade_safety_negative_to_transaction(monkeypatch, text):
    _enable_percent(monkeypatch, 100)
    outcome = resolve_jev_decision(
        text=text, cohort_key="session", fallback_label=IntentLabel.CLARIFY,
        provider_factory=_provider(_result(IntentLabel.PAYMENT)),
    )
    assert outcome.decision_source == "baseline"
    assert outcome.fallback_used is True
    assert outcome.fallback_reason == "transaction_gate_blocked"


@pytest.mark.parametrize("text,label", [
    ("确认这个方案并下单", IntentLabel.CONFIRM_ORDER),
    ("确认支付", IntentLabel.PAYMENT),
    ("取消这个订单", IntentLabel.CANCEL),
    ("查询订单状态", IntentLabel.ORDER_STATUS),
])
def test_protected_route_stays_on_baseline_even_in_jev_bucket(monkeypatch, text, label):
    _enable_percent(monkeypatch, 100)
    outcome = resolve_jev_decision(
        text=text, cohort_key="session", fallback_label=label,
        provider_factory=lambda: pytest.fail("protected route must not call Jev authority"),
    )
    assert outcome.decision_source == "baseline"
    assert outcome.label is label
    assert outcome.fallback_used is False
    assert outcome.authority_bucket == "protected_route"


def test_rollback_while_provider_in_flight_discards_late_result(monkeypatch):
    _enable_percent(monkeypatch, 100)
    started, release = Event(), Event()

    class SlowProvider:
        def classify_intent(self, *_args, **_kwargs):
            started.set()
            release.wait(2)
            return _result()

    results = []
    worker = Thread(target=lambda: results.append(resolve_jev_decision(
        text="make the plan cheaper", cohort_key="session",
        fallback_label=IntentLabel.RECOMMEND, provider_factory=SlowProvider,
    )))
    worker.start()
    assert started.wait(1)
    set_decision_enabled(False, "manual_rollback_test")
    release.set()
    worker.join(2)
    assert not worker.is_alive()
    assert results[0].decision_source == "baseline"
    assert results[0].fallback_reason == "rollback_during_provider_call"
    after = resolve_jev_decision(
        text="make the plan cheaper", cohort_key="session",
        fallback_label=IntentLabel.RECOMMEND,
        provider_factory=lambda: pytest.fail("provider called after rollback"),
    )
    assert after.decision_source == "baseline"
    assert after.authority_bucket == "disabled"
