from app.decision.metrics import calculate_metrics


def test_metrics_include_macro_f1_confusion_latency_and_transaction_escalation_rate():
    metrics = calculate_metrics(
        ["recommend", "confirm_order", "clarify", "payment"],
        ["confirm_order", "confirm_order", "clarify", "payment"],
        [1.0, 2.0, 3.0, 4.0],
    )
    assert metrics["accuracy"] == 0.75
    assert metrics["per_class"]["confirm_order"]["precision"] == 0.5
    assert metrics["per_class"]["clarify"]["recall"] == 1.0
    assert metrics["transaction_escalation_errors"] == 1
    assert metrics["transaction_escalation_error_rate"] == 0.25
    assert metrics["latency_ms"] == {"mean": 2.5, "p50": 2.5, "p95": 3.8499999999999996}
