from __future__ import annotations

import json
import math
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


def summarize_shadow_events(events: Iterable[dict[str, Any]]) -> dict[str, int | float]:
    """Summarize existing audit rows only; this function never calls Jev."""
    rows = [event for event in events if event.get("event") in {"decision_shadow", "decision_shadow_skip"}]
    attempted = [event for event in rows if event.get("shadow_attempted") is True]
    successes = [event for event in attempted if event.get("provider_success") is True]
    failures = [event for event in attempted if event.get("provider_success") is False]
    skipped = [event for event in rows if event.get("shadow_skipped") is True]
    comparable = [event for event in successes if event.get("comparable") is True]
    comparable_agreements = [event for event in comparable if event.get("agreement") is True]
    agreement_count = sum(event.get("agreement") is True for event in successes)
    escalation_count = sum(event.get("transaction_escalation_disagreement") is True for event in successes)
    deescalation_count = sum(event.get("transaction_deescalation_disagreement") is True for event in successes)
    low_confidence_count = sum(event.get("low_confidence") is True for event in successes)
    latencies = [float(event["shadow_latency_ms"]) for event in successes if event.get("shadow_latency_ms") is not None]

    return {
        "eligible_requests": len(rows),
        "sampled_requests": len(attempted) + sum(event.get("shadow_skipped_reason") == "capacity" for event in skipped),
        "shadow_attempts": len(attempted),
        "shadow_successes": len(successes),
        "shadow_failures": len(failures),
        "shadow_failure_rate": _rate(len(failures), len(attempted)),
        "shadow_skipped": len(skipped),
        "skip_disabled": sum(event.get("shadow_skipped_reason") == "disabled" for event in skipped),
        "skip_sampling": sum(event.get("shadow_skipped_reason") == "sampling" for event in skipped),
        "skip_capacity": sum(event.get("shadow_skipped_reason") == "capacity" for event in skipped),
        "agreement_count": agreement_count,
        "agreement_rate": _rate(agreement_count, len(successes)),
        "comparable_count": len(comparable),
        "comparable_agreement_count": len(comparable_agreements),
        "comparable_agreement_rate": _rate(len(comparable_agreements), len(comparable)),
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
    }


def summarize_local_shadow_events(trace_file: Path = TRACE_FILE) -> dict[str, int | float]:
    if not trace_file.exists():
        return summarize_shadow_events([])
    content = trace_file.read_text(encoding="utf-8").strip()
    rows = json.loads(content) if content else []
    return summarize_shadow_events(rows if isinstance(rows, list) else [])


if __name__ == "__main__":
    print(json.dumps(summarize_local_shadow_events(), ensure_ascii=False, indent=2))
