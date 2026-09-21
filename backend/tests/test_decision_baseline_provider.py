import pytest

from app.decision.providers.baseline import BaselineIntentProvider
from app.decision.registry import get_provider
from app.decision.schemas import IntentLabel


@pytest.mark.parametrize(("text", "label"), [
    ("我要买20个鼠标", IntentLabel.RECOMMEND),
    ("预算降到3万", IntentLabel.MODIFY_PLAN),
    ("比较方案A和方案B", IntentLabel.COMPARE_PLAN),
    ("为什么推荐这个", IntentLabel.EXPLAIN_PLAN),
    ("确认方案A并下单", IntentLabel.CONFIRM_ORDER),
    ("去付款", IntentLabel.PAYMENT),
    ("订单支付了吗", IntentLabel.ORDER_STATUS),
    ("就这个吧", IntentLabel.CLARIFY),
])
def test_baseline_provider_adapts_current_rules_to_decision_result(text, label):
    result = BaselineIntentProvider().classify_intent(text)
    assert result.label is label
    assert result.provider == "baseline"
    assert result.model == "current_router_rules"
    assert result.latency_ms >= 0
    assert result.probabilities is None


def test_registry_only_exposes_registered_provider():
    assert get_provider("baseline").name == "baseline"
    with pytest.raises(ValueError, match="Unknown decision provider"):
        get_provider("jev")
