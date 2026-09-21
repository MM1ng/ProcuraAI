import json

import app.decision.benchmark as benchmark
from app.decision.base import DecisionProviderPredictionError
from app.decision.benchmark import dataset_sha256, load_intent_gold_set, run_intent_benchmark, write_result
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
    result = run_intent_benchmark("baseline", "dev")
    path = write_result(result, tmp_path / "results")
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["task"] == "intent"
    assert payload["provider"] == "baseline"
    assert payload["dataset_size"] >= 120
    assert payload["dataset_name"] == "dev"
    assert payload["dataset_sha256"]
    assert "transaction_escalation_error_rate" in payload
    assert order_service.list_orders() == before


def test_three_dataset_results_use_distinct_filenames(tmp_path):
    paths = [write_result(run_intent_benchmark("baseline", dataset), tmp_path) for dataset in ("dev", "test", "hard")]
    assert len(set(paths)) == 3
    assert {path.name for path in paths} == {
        "baseline_intent_dev.json", "baseline_intent_test.json", "baseline_intent_hard.json",
    }
    assert dataset_sha256(__import__("app.decision.benchmark", fromlist=["dataset_path"]).dataset_path("test")) == (
        run_intent_benchmark("baseline", "test")["dataset_sha256"]
    )


def test_provider_prediction_failures_are_reported_without_relabeling_cases(monkeypatch):
    class FailingProvider:
        name = "failing"

        def classify_intent(self, *_args, **_kwargs):
            raise DecisionProviderPredictionError("network failure")

    monkeypatch.setattr(benchmark, "get_provider", lambda _: FailingProvider())
    result = benchmark.run_intent_benchmark("failing", "hard")
    assert result["attempted_samples"] == 48
    assert result["successful_predictions"] == 0
    assert result["failed_predictions"] == 48
    assert result["provider_failure_rate"] == 1.0
    assert result["provider_failures"] == 48
    assert result["provider_failure_details"][0]["error_type"] == "DecisionProviderPredictionError"
