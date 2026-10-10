from __future__ import annotations

import json
import math
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from app.observability.local_tracer import TRACE_FILE


def _rate(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(math.ceil(percentile * len(ordered)) - 1, 0)
    return round(ordered[index], 2)


def _comparison_metrics(events: list[dict[str, Any]]) -> dict[str, Any]:
    labels = sorted({
        str(event.get(field))
        for event in events
        for field in ("authoritative_label", "shadow_label")
        if event.get(field)
    })
    confusion = {label: {prediction: 0 for prediction in labels} for label in labels}
    for event in events:
        actual = str(event.get("authoritative_label") or "")
        predicted = str(event.get("shadow_label") or "")
        if actual in confusion and predicted in confusion[actual]:
            confusion[actual][predicted] += 1

    per_class: dict[str, dict[str, int | float]] = {}
    for label in labels:
        actual_support = sum(confusion[label].values())
        predicted_support = sum(row[label] for row in confusion.values())
        matched = confusion[label][label]
        precision = _rate(matched, predicted_support)
        recall = _rate(matched, actual_support)
        per_class[label] = {
            "support": actual_support,
            "jev_predictions": predicted_support,
            "matched": matched,
            "precision_vs_router": precision,
            "recall_vs_router": recall,
            "f1_vs_router": _rate(2 * matched, predicted_support + actual_support),
        }
    return {
        "comparison_basis": "authoritative_router_proxy_not_gold",
        "per_class": per_class,
        "confusion_matrix": confusion,
    }


def summarize_shadow_events(events: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Summarize existing audit rows only; this function never calls Jev."""
    rows = [event for event in events if event.get("event") in {"decision_shadow", "decision_shadow_skip"}]
    attempted = [event for event in rows if event.get("shadow_attempted") is True]
    successes = [event for event in attempted if event.get("provider_success") is True]
    failures = [event for event in attempted if event.get("provider_success") is False]
    provider_error_types = Counter(
        str(event.get("provider_error_type") or "unknown")
        for event in failures
    )
    skipped = [event for event in rows if event.get("shadow_skipped") is True]
    comparable = [event for event in successes if event.get("comparable") is True]
    comparable_agreements = [event for event in comparable if event.get("agreement") is True]
    comparison = _comparison_metrics(comparable)
    agreement_count = sum(event.get("agreement") is True for event in successes)
    escalation_count = sum(event.get("transaction_escalation_disagreement") is True for event in successes)
    deescalation_count = sum(event.get("transaction_deescalation_disagreement") is True for event in successes)
    low_confidence_count = sum(event.get("low_confidence") is True for event in successes)
    latencies = [float(event["shadow_latency_ms"]) for event in successes if event.get("shadow_latency_ms") is not None]
    completed_provider_calls = [event for event in attempted if event.get("provider_call_elapsed_ms") is not None]
    provider_call_latencies = [float(event["provider_call_elapsed_ms"]) for event in completed_provider_calls]
    known_retry_counts = [int(event["provider_retry_count"]) for event in completed_provider_calls if event.get("provider_retry_count") is not None]
    provider_final_error_types = Counter(
        str(event["provider_final_error_type"])
        for event in completed_provider_calls
        if event.get("provider_final_error_type")
    )

    return {
        "eligible_requests": len(rows),
        "sampled_requests": len(attempted) + sum(event.get("shadow_skipped_reason") == "capacity" for event in skipped),
        "shadow_attempts": len(attempted),
        "shadow_successes": len(successes),
        "shadow_failures": len(failures),
        "shadow_failure_rate": _rate(len(failures), len(attempted)),
        "provider_error_types": dict(sorted(provider_error_types.items())),
        "shadow_skipped": len(skipped),
        "skip_disabled": sum(event.get("shadow_skipped_reason") == "disabled" for event in skipped),
        "skip_sampling": sum(event.get("shadow_skipped_reason") == "sampling" for event in skipped),
        "skip_capacity": sum(event.get("shadow_skipped_reason") == "capacity" for event in skipped),
        "agreement_count": agreement_count,
        "agreement_rate": _rate(agreement_count, len(successes)),
        "comparable_count": len(comparable),
        "comparable_agreement_count": len(comparable_agreements),
        "comparable_agreement_rate": _rate(len(comparable_agreements), len(comparable)),
        "per_class_comparison": comparison,
        "fallback_clarify_count": sum(event.get("authoritative_label_resolution") == "fallback_clarify" for event in rows),
        "coarse_count": sum(event.get("authoritative_label_resolution") == "coarse" for event in rows),
        "transaction_escalation_disagreement_count": escalation_count,
        "transaction_escalation_disagreement_rate": _rate(escalation_count, len(successes)),
        "transaction_deescalation_disagreement_count": deescalation_count,
        "transaction_deescalation_disagreement_rate": _rate(deescalation_count, len(successes)),
        "low_confidence_count": low_confidence_count,
        "low_confidence_rate": _rate(low_confidence_count, len(successes)),
        "latency_mean_ms": round(sum(latencies) / len(latencies), 2) if latencies else 0.0,
        "latency_p50_ms": _percentile(latencies, 0.5),
        "latency_p95_ms": _percentile(latencies, 0.95),
        "provider_call_completed_count": len(completed_provider_calls),
        "provider_call_latency_mean_ms": round(sum(provider_call_latencies) / len(provider_call_latencies), 2) if provider_call_latencies else 0.0,
        "provider_call_latency_p50_ms": _percentile(provider_call_latencies, 0.5),
        "provider_call_latency_p95_ms": _percentile(provider_call_latencies, 0.95),
        "provider_retry_count_total": sum(known_retry_counts),
        "provider_retry_count_unknown": len(completed_provider_calls) - len(known_retry_counts),
        "provider_final_error_types": dict(sorted(provider_final_error_types.items())),
    }


def _parse_since(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("--since must be an ISO-8601 timestamp with a timezone") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("--since must include a timezone, for example +08:00 or Z")
    return parsed.astimezone(timezone.utc)


def summarize_local_shadow_events(
    trace_file: Path = TRACE_FILE,
    since: datetime | None = None,
) -> dict[str, Any]:
    if not trace_file.exists():
        rows: list[dict[str, Any]] = []
    else:
        content = trace_file.read_text(encoding="utf-8").strip()
        decoded = json.loads(content) if content else []
        rows = decoded if isinstance(decoded, list) else []
    if since is None:
        return summarize_shadow_events(rows)

    if since.tzinfo is None or since.utcoffset() is None:
        raise ValueError("since must include a timezone")
    since_utc = since.astimezone(timezone.utc)
    selected: list[dict[str, Any]] = []
    missing_or_invalid_timestamps = 0
    for row in rows:
        if row.get("event") not in {"decision_shadow", "decision_shadow_skip"}:
            continue
        created_at = row.get("created_at")
        try:
            event_time = datetime.fromisoformat(str(created_at).replace("Z", "+00:00"))
            if event_time.tzinfo is None or event_time.utcoffset() is None:
                raise ValueError("timestamp has no timezone")
        except (TypeError, ValueError):
            missing_or_invalid_timestamps += 1
            continue
        if event_time.astimezone(timezone.utc) >= since_utc:
            selected.append(row)

    summary = summarize_shadow_events(selected)
    summary["window_start"] = since_utc.isoformat()
    summary["events_missing_or_invalid_timestamp_excluded"] = missing_or_invalid_timestamps
    return summary


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Summarize Jev Shadow audit metrics without calling Jev.")
    parser.add_argument(
        "--since",
        type=_parse_since,
        help="Only include shadow events at or after this ISO-8601 timestamp with timezone.",
    )
    args = parser.parse_args()
    print(json.dumps(summarize_local_shadow_events(since=args.since), ensure_ascii=False, indent=2))
