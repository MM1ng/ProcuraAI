from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from app.decision.shadow_metrics import summarize_local_shadow_events, summarize_shadow_events


def _event(**overrides):
    event = {
        "event": "decision_shadow",
        "shadow_attempted": True,
        "shadow_skipped": False,
        "shadow_skipped_reason": None,
        "provider_success": True,
        "agreement": True,
        "comparable": True,
        "authoritative_label_resolution": "exact",
        "transaction_escalation_disagreement": False,
        "transaction_deescalation_disagreement": False,
        "low_confidence": False,
        "shadow_latency_ms": 10.0,
    }
    event.update(overrides)
    return event


def test_shadow_summary_counts_attempts_skips_and_comparable_rates():
    summary = summarize_shadow_events([
        _event(shadow_latency_ms=10.0),
        _event(agreement=False, shadow_latency_ms=20.0, low_confidence=True),
        _event(
            provider_success=False,
            agreement=None,
            comparable=False,
            provider_error_type="TimeoutError",
            shadow_latency_ms=None,
        ),
        _event(event="decision_shadow_skip", shadow_attempted=False, shadow_skipped=True,
               shadow_skipped_reason="capacity", provider_success=None, agreement=None,
               comparable=True, authoritative_label_resolution="exact", shadow_latency_ms=None),
        _event(event="decision_shadow_skip", shadow_attempted=False, shadow_skipped=True,
               shadow_skipped_reason="sampling", provider_success=None, agreement=None,
               comparable=False, authoritative_label_resolution="fallback_clarify", shadow_latency_ms=None),
        _event(event="decision_shadow_skip", shadow_attempted=False, shadow_skipped=True,
               shadow_skipped_reason="disabled", provider_success=None, agreement=None,
               comparable=False, authoritative_label_resolution="coarse", shadow_latency_ms=None),
    ])
    assert summary["eligible_requests"] == 6
    assert summary["sampled_requests"] == 4
    assert summary["shadow_attempts"] == 3
    assert summary["shadow_successes"] == 2
    assert summary["shadow_failures"] == 1
    assert summary["shadow_failure_rate"] == 0.3333
    assert summary["provider_error_types"] == {"TimeoutError": 1}
    assert (summary["skip_disabled"], summary["skip_sampling"], summary["skip_capacity"]) == (1, 1, 1)
    assert summary["agreement_count"] == 1
    assert summary["agreement_rate"] == 0.5
    assert summary["comparable_count"] == 2
    assert summary["comparable_agreement_count"] == 1
    assert summary["comparable_agreement_rate"] == 0.5
    assert (summary["fallback_clarify_count"], summary["coarse_count"]) == (1, 1)
    assert summary["low_confidence_count"] == 1
    assert summary["low_confidence_rate"] == 0.5
    assert (summary["latency_mean_ms"], summary["latency_p50_ms"], summary["latency_p95_ms"]) == (15.0, 10.0, 20.0)


def test_shadow_summary_uses_safe_zero_denominators():
    summary = summarize_shadow_events([])
    for key in (
        "shadow_failure_rate", "agreement_rate", "comparable_agreement_rate",
        "transaction_escalation_disagreement_rate", "transaction_deescalation_disagreement_rate",
        "low_confidence_rate", "latency_mean_ms", "latency_p50_ms", "latency_p95_ms",
    ):
        assert summary[key] == 0.0


def test_per_class_comparison_uses_only_successful_exact_router_mappings():
    summary = summarize_shadow_events([
        _event(authoritative_label="recommend", shadow_label="recommend"),
        _event(authoritative_label="recommend", shadow_label="payment", agreement=False),
        _event(authoritative_label="payment", shadow_label="payment"),
        _event(authoritative_label="clarify", shadow_label="recommend", comparable=False),
        _event(authoritative_label="payment", shadow_label=None, provider_success=False, comparable=True),
    ])

    comparison = summary["per_class_comparison"]
    assert comparison["comparison_basis"] == "authoritative_router_proxy_not_gold"
    assert comparison["confusion_matrix"] == {
        "payment": {"payment": 1, "recommend": 0},
        "recommend": {"payment": 1, "recommend": 1},
    }
    assert comparison["per_class"]["recommend"] == {
        "support": 2,
        "jev_predictions": 1,
        "matched": 1,
        "precision_vs_router": 1.0,
        "recall_vs_router": 0.5,
        "f1_vs_router": 0.6667,
    }
    assert comparison["per_class"]["payment"]["support"] == 1


def test_since_filter_limits_live_events_and_counts_unusable_timestamps(tmp_path):
    trace_file = tmp_path / "observability.json"
    trace_file.write_text(json.dumps([
        _event(
            created_at="2026-09-27T10:00:00+00:00",
            authoritative_label="recommend",
            shadow_label="recommend",
        ),
        _event(
            created_at="2026-09-28T10:00:00Z",
            authoritative_label="payment",
            shadow_label="payment",
        ),
        _event(authoritative_label="recommend", shadow_label="recommend"),
        {"event": "agent", "created_at": "2026-09-28T11:00:00Z"},
    ]), encoding="utf-8")

    summary = summarize_local_shadow_events(
        trace_file,
        since=datetime(2026, 9, 28, 0, 0, tzinfo=timezone.utc),
    )

    assert summary["eligible_requests"] == 1
    assert summary["shadow_successes"] == 1
    assert summary["comparable_agreement_rate"] == 1.0
    assert summary["events_missing_or_invalid_timestamp_excluded"] == 1
    assert summary["window_start"] == "2026-09-28T00:00:00+00:00"


def test_since_requires_timezone():
    with pytest.raises(ValueError, match="timezone"):
        summarize_local_shadow_events(since=datetime(2026, 9, 28))
