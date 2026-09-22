from __future__ import annotations

import threading
import time

from app.decision.gateway import ShadowConfig, dispatch_jev_shadow, is_sampled, run_shadow_evaluation
from app.decision.schemas import DecisionResult, IntentLabel
from app.decision.shadow import authoritative_intent_label, failure_record, success_record


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


def test_shadow_disabled_does_not_start_a_provider_thread(monkeypatch):
    started = []

    class FailThread:
        def __init__(self, *args, **kwargs):
            started.append((args, kwargs))

        def start(self):
            raise AssertionError("shadow thread must not start while disabled")

    monkeypatch.setattr("app.decision.gateway.threading.Thread", FailThread)
    assert not dispatch_jev_shadow(
        text="recommend laptops",
        trace_id="trace-disabled",
        authoritative_label=IntentLabel.RECOMMEND,
        config=ShadowConfig(False, 100, 1.0, True),
    )
    assert started == []


def test_sampling_skip_does_not_start_a_provider_thread(monkeypatch):
    monkeypatch.setattr("app.decision.gateway.threading.Thread", lambda *args, **kwargs: None)
    assert not dispatch_jev_shadow(
        text="recommend laptops",
        trace_id="trace-skip",
        authoritative_label=IntentLabel.RECOMMEND,
        config=ShadowConfig(True, 100, 0.0, True),
    )
    assert not is_sampled("any-trace", 0.0)
    assert is_sampled("any-trace", 1.0)


def test_successful_shadow_is_audit_only_and_redacts_user_text():
    emitted = []
    run_shadow_evaluation(
        text="payment credentials must not appear in audit",
        trace_id="trace-success",
        authoritative_label=IntentLabel.RECOMMEND,
        config=ShadowConfig(True, 100, 1.0, False),
        provider_factory=lambda: type("Provider", (), {"classify_intent": lambda self, text: _result()})(),
        emit=emitted.append,
    )
    assert len(emitted) == 1
    record = emitted[0]
    assert record["provider_success"] is True
    assert record["agreement"] is True
    assert record["shadow_probabilities"] is None
    assert "user_query" not in record
    assert "payment credentials" not in str(record)
    assert len(record["text_sha256"]) == 64


def test_transaction_disagreements_are_recorded_without_authority_change():
    escalation = success_record(
        trace_id="trace-escalation",
        text="recommend laptops",
        authoritative_label=IntentLabel.RECOMMEND,
        result=_result(IntentLabel.PAYMENT),
        log_probabilities=True,
    ).as_event()
    deescalation = success_record(
        trace_id="trace-deescalation",
        text="confirm this plan and place order",
        authoritative_label=IntentLabel.CONFIRM_ORDER,
        result=_result(IntentLabel.CLARIFY),
        log_probabilities=True,
    ).as_event()
    assert escalation["transaction_escalation_disagreement"] is True
    assert escalation["transaction_deescalation_disagreement"] is False
    assert deescalation["transaction_escalation_disagreement"] is False
    assert deescalation["transaction_deescalation_disagreement"] is True


def test_provider_error_and_invalid_response_are_isolated_to_shadow_audit():
    emitted = []

    class ErrorProvider:
        def classify_intent(self, _text):
            raise RuntimeError("authentication details must not escape")

    run_shadow_evaluation(
        text="recommend laptops",
        trace_id="trace-error",
        authoritative_label=IntentLabel.RECOMMEND,
        config=ShadowConfig(True, 100, 1.0, True),
        provider_factory=ErrorProvider,
        emit=emitted.append,
    )
    assert emitted[-1]["provider_success"] is False
    assert emitted[-1]["provider_error_type"] == "RuntimeError"
    assert "authentication details" not in str(emitted[-1])

    run_shadow_evaluation(
        text="recommend laptops",
        trace_id="trace-invalid",
        authoritative_label=IntentLabel.RECOMMEND,
        config=ShadowConfig(True, 100, 1.0, True),
        provider_factory=lambda: type("Provider", (), {"classify_intent": lambda self, text: object()})(),
        emit=emitted.append,
    )
    assert emitted[-1]["provider_success"] is False
    assert emitted[-1]["provider_error_type"] == "invalid_response"


def test_timeout_is_recorded_and_returns_without_waiting_for_provider_completion():
    emitted = []
    release = threading.Event()

    class SlowProvider:
        def classify_intent(self, _text):
            release.wait(1)
            return _result()

    started = time.perf_counter()
    run_shadow_evaluation(
        text="recommend laptops",
        trace_id="trace-timeout",
        authoritative_label=IntentLabel.RECOMMEND,
        config=ShadowConfig(True, 10, 1.0, True),
        provider_factory=SlowProvider,
        emit=emitted.append,
    )
    elapsed = time.perf_counter() - started
    release.set()
    assert elapsed < 0.25
    assert emitted[-1]["provider_success"] is False
    assert emitted[-1]["provider_error_type"] == "timeout"


def test_authoritative_label_uses_existing_transaction_router_first():
    assert authoritative_intent_label(
        "确认方案A并下单", {"revision_intent": "new_plan"}, "recommendation_plan"
    ) is IntentLabel.CONFIRM_ORDER
    assert authoritative_intent_label(
        "确认支付", {"revision_intent": "new_plan"}, "recommendation_plan"
    ) is IntentLabel.PAYMENT
    assert authoritative_intent_label(
        "compare the plans", {"revision_intent": "new_plan"}, "recommendation_plan"
    ) is IntentLabel.COMPARE_PLAN
    assert authoritative_intent_label(
        "make it cheaper", {"revision_intent": "cheaper"}, "recommendation_plan"
    ) is IntentLabel.MODIFY_PLAN


def test_failure_record_contains_only_safe_fields():
    record = failure_record(
        trace_id="trace-failure",
        text="raw sensitive input",
        authoritative_label=IntentLabel.RECOMMEND,
        error_type="DecisionProviderPredictionError",
    ).as_event()
    assert record["provider_success"] is False
    assert record["provider_error_type"] == "DecisionProviderPredictionError"
    assert "raw sensitive input" not in str(record)
    assert "api_key" not in record
