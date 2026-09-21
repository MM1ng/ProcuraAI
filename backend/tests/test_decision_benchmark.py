import json

from app.decision.benchmark import load_intent_gold_set, run_intent_benchmark, write_result
from app.decision.schemas import IntentLabel
from app.services import order_service


def test_gold_set_is_readable_has_valid_labels_and_is_majority_chinese():
    cases = load_intent_gold_set()
    assert len(cases) >= 120
    assert all(case.label in IntentLabel for case in cases)
    assert sum(case.language == "zh" for case in cases) / len(cases) >= 0.60


def test_offline_benchmark_serializes_result_without_mutating_orders(tmp_path, monkeypatch):
    monkeypatch.setattr(order_service, "ORDERS_FILE", tmp_path / "orders.json")
    before = order_service.list_orders()
    result = run_intent_benchmark("baseline")
    path = write_result(result, tmp_path / "results")
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["task"] == "intent"
    assert payload["provider"] == "baseline"
    assert payload["dataset_size"] >= 120
    assert "transaction_escalation_error_rate" in payload
    assert order_service.list_orders() == before
