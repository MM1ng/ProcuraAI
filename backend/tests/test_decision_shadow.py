from __future__ import annotations

import threading
import time

import pytest

from app.decision.base import DecisionProviderUnavailableError
from app.decision.gateway import ShadowCapacityGate, ShadowConfig, dispatch_jev_shadow, is_sampled, run_shadow_evaluation
from app.decision.schemas import DecisionResult, IntentLabel
from app.decision.shadow import (
    AuthoritativeIntentDecision,
    resolve_authoritative_intent,
    success_record,
)


CONFIG = ShadowConfig(True, 100, 1.0, True, 1)
EXACT_RECOMMEND = AuthoritativeIntentDecision(IntentLabel.RECOMMEND, "exact", "router")


def _result(label: IntentLabel = IntentLabel.RECOMMEND, **overrides) -> DecisionResult:
    payload = {
        "label": label,
        "provider": "jev",
        "confidence": 0.91,
        "probabilities": {label.value: 0.91},
        "model": "jev-test",
        "latency_ms": 12.5,
        "metadata": {"request_id": "request-1"},
    }
    payload.update(overrides)
    return DecisionResult(**payload)


def _wait_for(predicate, timeout: float = 1.0) -> None:
    deadline = time.monotonic() + timeout
    while not predicate():
        if time.monotonic() >= deadline:
            raise AssertionError("condition did not become true")
        time.sleep(0.005)


def test_disabled_and_sampling_skips_are_audited_without_threads(monkeypatch):
    emitted = []

    class FailThread:
        def __init__(self, *args, **kwargs):
            raise AssertionError("no thread should be created for a skip")

    monkeypatch.setattr("app.decision.gateway.threading.Thread", FailThread)
    assert not dispatch_jev_shadow(
        text="sensitive request", trace_id="disabled", authoritative_decision=EXACT_RECOMMEND,
        config=ShadowConfig(False, 100, 1.0, True, 4), emit=emitted.append,
    )
    assert not dispatch_jev_shadow(
        text="sensitive request", trace_id="sampling", authoritative_decision=EXACT_RECOMMEND,
        config=ShadowConfig(True, 100, 0.0, True, 4), emit=emitted.append,
    )
    assert [event["shadow_skipped_reason"] for event in emitted] == ["disabled", "sampling"]
    assert all("sensitive request" not in str(event) for event in emitted)
    assert not is_sampled("any-trace", 0.0)
    assert is_sampled("any-trace", 1.0)


def test_observability_and_dispatch_start_failures_are_isolated(monkeypatch):
    def broken_emit(_record):
        raise OSError("log store unavailable")

    assert not dispatch_jev_shadow(
        text="request", trace_id="broken-audit", authoritative_decision=EXACT_RECOMMEND,
        config=ShadowConfig(False, 100, 1.0, True, 1), emit=broken_emit,
    )

    class FailThread:
        def __init__(self, *args, **kwargs):
            pass

        def start(self):
            raise RuntimeError("thread creation unavailable")

    gate = ShadowCapacityGate(1)
    emitted = []
    monkeypatch.setattr("app.decision.gateway.threading.Thread", FailThread)
    assert not dispatch_jev_shadow(
        text="request", trace_id="broken-thread", authoritative_decision=EXACT_RECOMMEND,
        config=CONFIG, capacity_gate=gate, emit=emitted.append,
    )
    assert gate.current_in_flight() == 0
    assert emitted[-1]["provider_error_type"] == "dispatch_error"


def test_provider_thread_start_failure_releases_the_capacity_slot(monkeypatch):
    class FailThread:
        def __init__(self, *args, **kwargs):
            pass

        def start(self):
            raise RuntimeError("provider thread unavailable")

    gate = ShadowCapacityGate(1)
    assert gate.try_acquire() == 1
    emitted = []
    monkeypatch.setattr("app.decision.gateway.threading.Thread", FailThread)
    run_shadow_evaluation(
        text="request", trace_id="provider-thread", authoritative_decision=EXACT_RECOMMEND,
        config=CONFIG, capacity_gate=gate, in_flight_at_dispatch=1, emit=emitted.append,
    )
    assert gate.current_in_flight() == 0
    assert emitted[-1]["provider_error_type"] == "provider_thread_start_error"


def test_capacity_gate_prevents_a_second_provider_call_and_records_skip():
    emitted = []
    gate = ShadowCapacityGate(1)
    started = threading.Event()
    release = threading.Event()
    calls = []

    class BlockingProvider:
        def classify_intent(self, _text):
            calls.append("call")
            started.set()
            release.wait(1)
            return _result()

    assert dispatch_jev_shadow(
        text="first", trace_id="first", authoritative_decision=EXACT_RECOMMEND,
        config=CONFIG, capacity_gate=gate, provider_factory=BlockingProvider, emit=emitted.append,
    )
    assert started.wait(1)
    assert not dispatch_jev_shadow(
        text="second", trace_id="second", authoritative_decision=EXACT_RECOMMEND,
        config=CONFIG, capacity_gate=gate, provider_factory=BlockingProvider, emit=emitted.append,
    )
    assert calls == ["call"]
    assert emitted[-1]["shadow_skipped_reason"] == "capacity"
    assert emitted[-1]["in_flight_at_dispatch"] == 1
    release.set()
    _wait_for(lambda: gate.current_in_flight() == 0)


def test_timeout_retains_slot_until_provider_call_really_ends():
    emitted = []
    gate = ShadowCapacityGate(1)
    started = threading.Event()
    release = threading.Event()

    class BlockingProvider:
        def classify_intent(self, _text):
            started.set()
            release.wait(1)
            return _result()

    timeout_config = ShadowConfig(True, 10, 1.0, True, 1)
    assert dispatch_jev_shadow(
        text="first", trace_id="timeout-first", authoritative_decision=EXACT_RECOMMEND,
        config=timeout_config, capacity_gate=gate, provider_factory=BlockingProvider, emit=emitted.append,
    )
    assert started.wait(1)
    _wait_for(lambda: any(event.get("provider_error_type") == "timeout" for event in emitted))
    assert gate.current_in_flight() == 1
    assert not dispatch_jev_shadow(
        text="second", trace_id="timeout-second", authoritative_decision=EXACT_RECOMMEND,
        config=timeout_config, capacity_gate=gate, provider_factory=BlockingProvider, emit=emitted.append,
    )
    assert emitted[-1]["shadow_skipped_reason"] == "capacity"

    release.set()
    _wait_for(lambda: gate.current_in_flight() == 0)
    assert dispatch_jev_shadow(
        text="third", trace_id="timeout-third", authoritative_decision=EXACT_RECOMMEND,
        config=timeout_config, capacity_gate=gate,
        provider_factory=lambda: type("Provider", (), {"classify_intent": lambda self, text: _result()})(),
        emit=emitted.append,
    )
    _wait_for(lambda: any(event.get("trace_id") == "timeout-third" for event in emitted))


def test_success_failure_and_invalid_response_are_audit_only_and_safe():
    emitted = []
    gate = ShadowCapacityGate(1)

    class ErrorProvider:
        def classify_intent(self, _text):
            raise RuntimeError("Authorization: secret-value")

    assert dispatch_jev_shadow(
        text="payment credentials must not appear", trace_id="error", authoritative_decision=EXACT_RECOMMEND,
        config=CONFIG, capacity_gate=gate, provider_factory=ErrorProvider, emit=emitted.append,
    )
    _wait_for(lambda: len(emitted) == 1)
    assert emitted[0]["provider_error_type"] == "RuntimeError"
    assert "secret-value" not in str(emitted[0])
    assert "payment credentials" not in str(emitted[0])

    assert dispatch_jev_shadow(
        text="invalid", trace_id="invalid", authoritative_decision=EXACT_RECOMMEND,
        config=CONFIG, capacity_gate=gate,
        provider_factory=lambda: type("Provider", (), {"classify_intent": lambda self, text: object()})(),
        emit=emitted.append,
    )
    _wait_for(lambda: len(emitted) == 2)
    assert emitted[-1]["provider_error_type"] == "invalid_response"


@pytest.mark.parametrize(
    ("error", "expected_type"),
    [
        (DecisionProviderUnavailableError("TYPESAFE_API_KEY=secret"), "DecisionProviderUnavailableError"),
        (RuntimeError("HTTP 429 Authorization: secret"), "RuntimeError"),
        (RuntimeError("HTTP 503 Authorization: secret"), "RuntimeError"),
    ],
)
def test_provider_unavailable_and_http_failures_stay_isolated(error, expected_type):
    emitted = []

    class ErrorProvider:
        def classify_intent(self, _text):
            raise error

    assert dispatch_jev_shadow(
        text="private request", trace_id=f"failure-{expected_type}", authoritative_decision=EXACT_RECOMMEND,
        config=CONFIG, capacity_gate=ShadowCapacityGate(1), provider_factory=ErrorProvider, emit=emitted.append,
    )
    _wait_for(lambda: len(emitted) == 1)
    assert emitted[0]["provider_success"] is False
    assert emitted[0]["provider_error_type"] == expected_type
    assert "secret" not in str(emitted[0])


def test_authoritative_resolution_marks_exact_and_fallback_mappings():
    cases = [
        ("确认方案A并下单", {"revision_intent": "new_plan"}, "recommendation_plan", IntentLabel.CONFIRM_ORDER, "transaction_intent"),
        ("确认支付", {"revision_intent": "new_plan"}, "recommendation_plan", IntentLabel.PAYMENT, "transaction_intent"),
        ("make it cheaper", {"revision_intent": "cheaper"}, "recommendation_plan", IntentLabel.MODIFY_PLAN, "revision_intent"),
        ("compare the plans", {"revision_intent": "new_plan"}, "recommendation_plan", IntentLabel.COMPARE_PLAN, "router"),
        ("recommend laptops", {"revision_intent": "new_plan"}, "recommendation_plan", IntentLabel.RECOMMEND, "router"),
    ]
    for message, intent, response_type, label, source in cases:
        decision = resolve_authoritative_intent(message, intent, response_type)
        assert decision.label is label
        assert decision.resolution == "exact"
        assert decision.source == source
        assert decision.comparable is True

    fallback = resolve_authoritative_intent("hello", {"revision_intent": "new_plan"}, "clarification")
    assert fallback.label is IntentLabel.CLARIFY
    assert fallback.resolution == "fallback_clarify"
    assert fallback.source == "fallback"
    assert fallback.comparable is False


def test_comparable_agreement_and_transaction_risk_are_separate():
    exact_match = success_record(
        trace_id="exact", text="recommend", authoritative_decision=EXACT_RECOMMEND,
        result=_result(), log_probabilities=False, in_flight_at_dispatch=1, max_in_flight=1,
    ).as_event()
    exact_disagreement = success_record(
        trace_id="different", text="recommend", authoritative_decision=EXACT_RECOMMEND,
        result=_result(IntentLabel.COMPARE_PLAN), log_probabilities=True, in_flight_at_dispatch=1, max_in_flight=1,
    ).as_event()
    fallback = AuthoritativeIntentDecision(IntentLabel.CLARIFY, "fallback_clarify", "fallback")
    taxonomy_gap = success_record(
        trace_id="gap", text="status", authoritative_decision=fallback,
        result=_result(IntentLabel.ORDER_STATUS), log_probabilities=True, in_flight_at_dispatch=1, max_in_flight=1,
    ).as_event()
    escalation = success_record(
        trace_id="risk", text="pay", authoritative_decision=fallback,
        result=_result(IntentLabel.PAYMENT), log_probabilities=True, in_flight_at_dispatch=1, max_in_flight=1,
    ).as_event()

    assert (exact_match["agreement"], exact_match["comparable"]) == (True, True)
    assert (exact_disagreement["agreement"], exact_disagreement["comparable"]) == (False, True)
    assert (taxonomy_gap["agreement"], taxonomy_gap["comparable"]) == (False, False)
    assert escalation["transaction_escalation_disagreement"] is True


def test_probability_log_switch_is_preserved():
    event = success_record(
        trace_id="probabilities", text="recommend", authoritative_decision=EXACT_RECOMMEND,
        result=_result(), log_probabilities=False, in_flight_at_dispatch=1, max_in_flight=1,
    ).as_event()
    assert event["shadow_probabilities"] is None
    assert len(event["text_sha256"]) == 64
