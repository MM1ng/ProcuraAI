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
    assert metrics["transaction_escalation_eligible_samples"] == 2
    assert metrics["transaction_escalation_error_rate"] == 0.5
    assert metrics["transaction_escalation_error_rate_overall"] == 0.25
    assert metrics["utility"] == {
        "confirm_order_recall": 1.0, "payment_recall": 1.0, "transaction_macro_recall": 1.0,
    }
    assert metrics["latency_ms"] == {"mean": 2.5, "p50": 2.5, "p95": 3.8499999999999996}


def test_escalation_rate_is_zero_when_no_non_transaction_samples_are_eligible():
    metrics = calculate_metrics(
        ["confirm_order", "payment"], ["confirm_order", "payment"], [1.0, 1.0],
    )
    assert metrics["transaction_escalation_eligible_samples"] == 0
    assert metrics["transaction_escalation_error_rate"] == 0.0
    assert metrics["transaction_escalation_error_rate_overall"] == 0.0
