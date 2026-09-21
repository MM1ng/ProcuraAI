import sys
from types import ModuleType, SimpleNamespace

import pytest

from app.decision.base import DecisionProviderPredictionError, DecisionProviderUnavailableError
from app.decision.providers.jev import JevProvider
from app.decision.tasks.intent import INTENT_DEFINITIONS


def _install_fake_sdk(monkeypatch, response=None, error=None):
    module = ModuleType("typesafe_sdk")

    class Choice:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    class Client:
        captured_question = None

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def system_one(self, **kwargs):
            Client.captured_question = kwargs["questions"]["intent"]
            if error:
                raise error
            return response

    module.Choice = Choice
    module.TypeSafeClient = Client
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
