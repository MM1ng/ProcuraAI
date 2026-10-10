import sys
from types import ModuleType, SimpleNamespace

import pytest

from app.decision.base import DecisionProviderPredictionError, DecisionProviderUnavailableError
from app.decision.providers.jev import JevProvider
from app.decision.tasks.intent import INTENT_DEFINITIONS


def _install_fake_sdk(monkeypatch, response=None, error=None, request_attempts=0):
    module = ModuleType("typesafe_sdk")

    class RetryPolicy:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    class Choice:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    class Client:
        captured_question = None
        captured_init_kwargs = None

        def __init__(self, **kwargs):
            self.kwargs = kwargs
            Client.captured_init_kwargs = kwargs

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def system_one(self, **kwargs):
            Client.captured_question = kwargs["questions"]["intent"]
            http_client = self.kwargs.get("http_client")
            for _ in range(request_attempts):
                http_client.request("POST", "https://typesafe.test/v1/system-one")
            if error:
                raise error
            return response

    module.Choice = Choice
    module.TypeSafeClient = Client
    module.RetryPolicy = RetryPolicy
    monkeypatch.setitem(sys.modules, "typesafe_sdk", module)
    return Client


def test_jev_maps_sdk_choice_and_real_returned_calibration_fields(monkeypatch):
    client = _install_fake_sdk(monkeypatch, SimpleNamespace(
        choices={"intent": SimpleNamespace(choice="recommend", confidence=0.88,
                                            probabilities={"recommend": 0.88, "clarify": 0.12})},
        request_id="req-1", model="jev-test",
    ))
    monkeypatch.setenv("TYPESAFE_API_KEY", "test-key")
    result = JevProvider().classify_intent("Need laptops")
    assert result.label.value == "recommend"
    assert result.confidence == 0.88
    assert result.probabilities == {"recommend": 0.88, "clarify": 0.12}
    assert result.metadata["request_id"] == "req-1"
    assert client.captured_question.kwargs["criteria"] == INTENT_DEFINITIONS


def test_jev_rejects_invalid_label_and_provider_errors_without_fallback(monkeypatch):
    monkeypatch.setenv("TYPESAFE_API_KEY", "test-key")
    _install_fake_sdk(monkeypatch, SimpleNamespace(choices={"intent": SimpleNamespace(choice="other")}))
    with pytest.raises(DecisionProviderPredictionError, match="invalid intent label"):
        JevProvider().classify_intent("message")
    _install_fake_sdk(monkeypatch, error=TimeoutError())
    with pytest.raises(DecisionProviderPredictionError, match="prediction failed"):
        JevProvider().classify_intent("message")


def test_jev_missing_key_is_explicitly_unavailable(monkeypatch):
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    with pytest.raises(DecisionProviderUnavailableError, match="TYPESAFE_API_KEY"):
        JevProvider().classify_intent("message")


def test_jev_exposes_call_duration_final_error_and_http_retry_count(monkeypatch):
    import app.decision.providers.jev as jev_module

    class FakeCountingHttpClient:
        def __init__(self, *, timeout):
            self.timeout = timeout
            self.request_count = 0

        def request(self, *_args, **_kwargs):
            self.request_count += 1

        def close(self):
            pass

    monkeypatch.setattr(jev_module, "_CountingHTTPClient", FakeCountingHttpClient)
    monkeypatch.setenv("TYPESAFE_API_KEY", "test-key")
    response = SimpleNamespace(
        choices={"intent": SimpleNamespace(choice="recommend", confidence=0.9, probabilities={"recommend": 0.9})},
        request_id="req-telemetry", model="jev-test",
    )
    _install_fake_sdk(monkeypatch, response=response, request_attempts=3)

    provider = JevProvider()
    result = provider.classify_intent("Need laptops")

    assert result.metadata["provider_retry_count"] == 2
    assert provider.last_call_metrics["provider_retry_count"] == 2
    assert provider.last_call_metrics["provider_call_elapsed_ms"] >= 0
    assert provider.last_call_metrics["provider_final_error_type"] is None

    _install_fake_sdk(monkeypatch, error=TimeoutError(), request_attempts=2)
    with pytest.raises(DecisionProviderPredictionError):
        provider.classify_intent("Need laptops")
    assert provider.last_call_metrics["provider_retry_count"] == 1
    assert provider.last_call_metrics["provider_final_error_type"] == "TimeoutError"


def test_shadow_can_bound_http_timeout_and_disable_sdk_retries(monkeypatch):
    client = _install_fake_sdk(monkeypatch, SimpleNamespace(
        choices={"intent": SimpleNamespace(choice="recommend", confidence=0.9,
                                            probabilities={"recommend": 0.9})},
        request_id="req-bounded-shadow", model="jev-test",
    ))
    monkeypatch.setenv("TYPESAFE_API_KEY", "test-key")

    result = JevProvider(timeout_seconds=5.5, max_retries=0).classify_intent("Need laptops")

    assert result.label.value == "recommend"
    assert client.captured_init_kwargs["timeout"] == 5.5
    assert client.captured_init_kwargs["http_client"].timeout.read == 5.5
    retry = client.captured_init_kwargs["retry"]
    assert retry.kwargs == {"max_retries": 0, "timeout": 5.5}


def test_transaction_criteria_separate_quoted_commands_and_payment_cancellation():
    confirm_order = INTENT_DEFINITIONS["confirm_order"]
    cancel = INTENT_DEFINITIONS["cancel"]

    assert isinstance(confirm_order, dict)
    assert "quoted" in confirm_order["not_for"].lower()
    assert "explain" in confirm_order["not_for"].lower()
    assert any(
        'Explain "确认方案B并下单"' in example and "clarify" in example
        for example in confirm_order["examples"]
    )

    assert isinstance(cancel, dict)
    assert "canceling a payment" in cancel["not_for"].lower()
    assert "取消支付" in cancel["not_for"]
    assert any("ORD-123" in example for example in cancel["examples"])

    clarify = INTENT_DEFINITIONS["clarify"]
    assert isinstance(clarify, dict)
    assert "agreement" in clarify["not_for"].lower()
    assert "就这个吧" in clarify["examples"]
    assert "可以买" in clarify["examples"]
