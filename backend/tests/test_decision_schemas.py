import pytest
from pydantic import ValidationError

from app.decision.schemas import DecisionResult, IntentLabel


def test_decision_result_requires_a_known_label_and_keeps_optional_probabilities_empty():
    result = DecisionResult(label="recommend", provider="test", latency_ms=0.0)
    assert result.label is IntentLabel.RECOMMEND
    assert result.confidence is None
    assert result.probabilities is None
    with pytest.raises(ValidationError):
        DecisionResult(label="invent_label", provider="test", latency_ms=0.0)
