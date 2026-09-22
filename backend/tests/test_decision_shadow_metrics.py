from __future__ import annotations

from app.decision.shadow_metrics import summarize_shadow_events


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
        _event(provider_success=False, agreement=None, comparable=False, shadow_latency_ms=None),
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
