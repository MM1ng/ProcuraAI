import sys
from types import ModuleType, SimpleNamespace

import pytest

from app.decision.base import DecisionProviderPredictionError, DecisionProviderUnavailableError
from app.decision.providers.von import VonProvider
from app.decision.tasks.intent import INTENT_DEFINITIONS


def _install_fake_von(monkeypatch, response=None, error=None):
    module = ModuleType("von")

    def decide(**kwargs):
        module.captured = kwargs
        if error:
            raise error
        return response

    module.decide = decide
    monkeypatch.setitem(sys.modules, "von", module)
    return module


def test_von_maps_sdk_choice_and_real_returned_calibration_fields(monkeypatch):
    module = _install_fake_von(monkeypatch, SimpleNamespace(
        choice="payment", confidence=0.91, probabilities={"payment": 0.91}, model="von-test", device="cpu",
    ))
    monkeypatch.setenv("VON_ENABLED", "true")
    result = VonProvider().classify_intent("Pay this order")
    assert result.label.value == "payment"
    assert result.confidence == 0.91
    assert result.probabilities == {"payment": 0.91}
    assert result.metadata["device"] == "cpu"
    assert module.captured["choices"] == INTENT_DEFINITIONS


def test_von_rejects_invalid_label_and_model_failure_without_fallback(monkeypatch):
    monkeypatch.setenv("VON_ENABLED", "true")
    _install_fake_von(monkeypatch, SimpleNamespace(choice="unknown"))
    with pytest.raises(DecisionProviderPredictionError, match="invalid intent label"):
        VonProvider().classify_intent("message")
    _install_fake_von(monkeypatch, error=RuntimeError("load failed"))
    with pytest.raises(DecisionProviderPredictionError, match="prediction failed"):
        VonProvider().classify_intent("message")


def test_von_disabled_or_sdk_unavailable_is_explicit(monkeypatch):
    monkeypatch.setenv("VON_ENABLED", "false")
    with pytest.raises(DecisionProviderUnavailableError, match="VON_ENABLED"):
        VonProvider().classify_intent("message")
    monkeypatch.setenv("VON_ENABLED", "true")
    # D02.2 may install the real SDK in the project venv.  A None sentinel
    # keeps this unit test on its intended unavailable-SDK path without a
    # local model import or download.
    monkeypatch.setitem(sys.modules, "von", None)
    with pytest.raises(DecisionProviderUnavailableError, match="von-sdk"):
        VonProvider().classify_intent("message")
