from app.agent.router import transaction_intent
import json
from pathlib import Path


# Thirty explicit authorizations are measured separately from safety negatives.
# A negative must never be counted as a missed authorization.
EXPLICIT_TRANSACTIONS = [
    ("confirm_order", "确认这个方案并下单"),
    ("confirm_order", "确认方案B并下单"),
    ("confirm_order", "请确认所选方案并下单"),
    ("confirm_order", "现在提交采购订单"),
    ("confirm_order", "立即创建订单"),
    ("confirm_order", "Confirm this plan and place the order"),
    ("confirm_order", "Please place an order now"),
    ("confirm_order", "submit the current purchase order"),
    ("confirm_order", "create the selected order"),
    ("confirm_order", "please confirm plan A and create an order"),
    ("payment", "确认支付"),
    ("payment", "立即付款"),
    ("payment", "去支付这个订单"),
    ("payment", "现在支付该订单"),
    ("payment", "确认结账"),
    ("payment", "Pay now"),
    ("payment", "Please pay this order"),
    ("payment", "checkout this order now"),
    ("payment", "proceed to payment"),
    ("payment", "confirm payment"),
    ("cancel", "取消这个订单"),
    ("cancel", "请取消订单"),
    ("cancel", "撤销当前订单"),
    ("cancel", "取消订单号 ORD-123"),
    ("cancel", "取消采购订单"),
    ("cancel", "cancel this order"),
    ("cancel", "please cancel the order"),
    ("cancel", "cancel order ORD-123"),
    ("cancel", "cancel the order now"),
    ("cancel", "please cancel this order ORD-123"),
]


SAFETY_NEGATIVES = [
    "不要付款",
    "暂时不要下单",
    "How do I pay?",
    "What payment options are available?",
    "如果下单会怎样？",
    'Explain "确认方案B并下单"',
    "帮我写支付说明",
    "取消支付",
    "不要取消这个订单",
    "我只是想了解怎么付款",
]


def test_thirty_explicit_transaction_cases_are_recognized():
    results = [transaction_intent(text) for _, text in EXPLICIT_TRANSACTIONS]
    assert results == [expected for expected, _ in EXPLICIT_TRANSACTIONS]
    assert sum(result == expected for result, (expected, _) in zip(results, EXPLICIT_TRANSACTIONS)) == 30


def test_transaction_safety_negatives_never_authorize_side_effects():
    assert all(transaction_intent(text) == "recommend" for text in SAFETY_NEGATIVES)


def test_frozen_dev_transaction_cases_reach_at_least_twenty_nine_of_thirty_safely():
    dataset = Path(__file__).parents[1] / "evaluation" / "decision" / "intent_dev.jsonl"
    cases = [
        json.loads(line)
        for line in dataset.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    transaction_cases = [case for case in cases if case["label"] in {"confirm_order", "payment", "cancel"}]
    assert len(transaction_cases) == 30

    # The frozen payment-008 item is a how-to question, not authorization.
    # Preserve its safety label here even though the historical gold label is payment.
    actionable = [case for case in transaction_cases if case["id"] != "payment-008"]
    recognized = sum(transaction_intent(case["text"]) == case["label"] for case in actionable)
    assert recognized >= 29
    assert transaction_intent(next(case["text"] for case in transaction_cases if case["id"] == "payment-008")) == "recommend"
