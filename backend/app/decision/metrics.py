from __future__ import annotations

from statistics import fmean
from typing import Any, Iterable

from app.decision.schemas import IntentLabel


TRANSACTION_LABELS = {IntentLabel.CONFIRM_ORDER.value, IntentLabel.PAYMENT.value}
NON_TRANSACTION_LABELS = {
    IntentLabel.RECOMMEND.value, IntentLabel.MODIFY_PLAN.value, IntentLabel.COMPARE_PLAN.value,
    IntentLabel.EXPLAIN_PLAN.value, IntentLabel.CLARIFY.value, IntentLabel.ORDER_STATUS.value,
}


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = (len(ordered) - 1) * percentile
    lower, upper = int(index), min(int(index) + 1, len(ordered) - 1)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (index - lower)


def calculate_metrics(expected: Iterable[str], predicted: Iterable[str], latencies_ms: Iterable[float]) -> dict[str, Any]:
    actual, guesses, latency = list(expected), list(predicted), list(latencies_ms)
    if len(actual) != len(guesses) or len(actual) != len(latency):
        raise ValueError("Expected labels, predicted labels, and latencies must have the same length.")
    labels = [label.value for label in IntentLabel]
    matrix = {truth: {guess: 0 for guess in labels} for truth in labels}
    for truth, guess in zip(actual, guesses):
        if truth not in matrix or guess not in labels:
            raise ValueError("Metrics received an unknown intent label.")
        matrix[truth][guess] += 1
    per_class: dict[str, dict[str, float]] = {}
    for label in labels:
        tp = matrix[label][label]
        fp = sum(matrix[truth][label] for truth in labels if truth != label)
        fn = sum(matrix[label][guess] for guess in labels if guess != label)
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        per_class[label] = {
            "precision": precision, "recall": recall,
            "f1": 2 * precision * recall / (precision + recall) if precision + recall else 0.0,
        }
    escalation_errors = sum(
        truth in NON_TRANSACTION_LABELS and guess in TRANSACTION_LABELS
        for truth, guess in zip(actual, guesses)
    )
    return {
        "accuracy": sum(truth == guess for truth, guess in zip(actual, guesses)) / len(actual) if actual else 0.0,
        "macro_f1": fmean(row["f1"] for row in per_class.values()),
        "per_class": per_class,
        "confusion_matrix": matrix,
        "transaction_escalation_errors": escalation_errors,
        "transaction_escalation_error_rate": escalation_errors / len(actual) if actual else 0.0,
        "latency_ms": {
            "mean": fmean(latency) if latency else 0.0,
            "p50": _percentile(latency, 0.50),
            "p95": _percentile(latency, 0.95),
        },
    }
