from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass
from typing import Any, Literal

from app.agent.router import route_intent, transaction_intent
from app.decision.schemas import DecisionResult, IntentLabel


TRANSACTION_LABELS = {IntentLabel.CONFIRM_ORDER, IntentLabel.PAYMENT}
LOW_CONFIDENCE_THRESHOLD = 0.7
Resolution = Literal["exact", "coarse", "fallback_clarify"]


@dataclass(frozen=True)
class AuthoritativeIntentDecision:
    """Existing production decision represented in the Jev taxonomy only."""

    label: IntentLabel
    resolution: Resolution
    source: str

    @property
    def comparable(self) -> bool:
        # Coarse mappings are intentionally excluded from quality-rate denominators.
        return self.resolution == "exact"


def resolve_authoritative_intent(
    message: str,
    intent: dict[str, Any],
    response_type: str | None,
) -> AuthoritativeIntentDecision:
    """Represent, but never change, the existing router's decision."""
    transaction = transaction_intent(message)
    if transaction == "confirm_order":
        return AuthoritativeIntentDecision(IntentLabel.CONFIRM_ORDER, "exact", "transaction_intent")
    if transaction == "payment":
        return AuthoritativeIntentDecision(IntentLabel.PAYMENT, "exact", "transaction_intent")

    revision_intent = str(intent.get("revision_intent") or "")
    if revision_intent in {"cheaper", "replace_product"}:
        return AuthoritativeIntentDecision(IntentLabel.MODIFY_PLAN, "exact", "revision_intent")

    route = route_intent(message).get("route")
    if route == "compare":
        return AuthoritativeIntentDecision(IntentLabel.COMPARE_PLAN, "exact", "router")
    if route in {"recommendation", "search"}:
        return AuthoritativeIntentDecision(IntentLabel.RECOMMEND, "exact", "router")
    if response_type == "recommendation_plan":
        return AuthoritativeIntentDecision(IntentLabel.RECOMMEND, "exact", "response_type")
    return AuthoritativeIntentDecision(IntentLabel.CLARIFY, "fallback_clarify", "fallback")


def authoritative_intent_label(
    message: str,
    intent: dict[str, Any],
    response_type: str | None,
) -> IntentLabel:
    """Backward-compatible label-only projection for existing callers."""
    return resolve_authoritative_intent(message, intent, response_type).label


@dataclass(frozen=True)
class ShadowAuditRecord:
    event: str
    trace_id: str
    provider: str
    text_sha256: str
    authoritative_label: str
    authoritative_label_resolution: Resolution
    authoritative_label_source: str
    comparable: bool
    shadow_attempted: bool
    shadow_skipped: bool
    shadow_skipped_reason: str | None
    in_flight_at_dispatch: int | None
    max_in_flight: int | None
    shadow_label: str | None
    agreement: bool | None
    transaction_escalation_disagreement: bool
    transaction_deescalation_disagreement: bool
    low_confidence: bool | None
    shadow_confidence: float | None
    shadow_probabilities: dict[str, float] | None
    shadow_latency_ms: float | None
    shadow_model: str | None
    shadow_request_id: str | None
    provider_success: bool | None
    provider_error_type: str | None

    def as_event(self) -> dict[str, Any]:
        return asdict(self)


def _text_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def success_record(
    *,
    trace_id: str,
    text: str,
    authoritative_decision: AuthoritativeIntentDecision,
    result: DecisionResult,
    log_probabilities: bool,
    in_flight_at_dispatch: int,
    max_in_flight: int,
) -> ShadowAuditRecord:
    shadow_label = result.label
    authoritative_is_transaction = authoritative_decision.label in TRANSACTION_LABELS
    shadow_is_transaction = shadow_label in TRANSACTION_LABELS
    return ShadowAuditRecord(
        event="decision_shadow",
        trace_id=trace_id,
        provider=result.provider,
        text_sha256=_text_sha256(text),
        authoritative_label=authoritative_decision.label.value,
        authoritative_label_resolution=authoritative_decision.resolution,
        authoritative_label_source=authoritative_decision.source,
        comparable=authoritative_decision.comparable,
        shadow_attempted=True,
        shadow_skipped=False,
        shadow_skipped_reason=None,
        in_flight_at_dispatch=in_flight_at_dispatch,
        max_in_flight=max_in_flight,
        shadow_label=shadow_label.value,
        agreement=authoritative_decision.label == shadow_label,
        transaction_escalation_disagreement=not authoritative_is_transaction and shadow_is_transaction,
        transaction_deescalation_disagreement=authoritative_is_transaction and not shadow_is_transaction,
        low_confidence=(result.confidence is not None and result.confidence < LOW_CONFIDENCE_THRESHOLD),
        shadow_confidence=result.confidence,
        shadow_probabilities=result.probabilities if log_probabilities else None,
        shadow_latency_ms=result.latency_ms,
        shadow_model=result.model,
        shadow_request_id=str(result.metadata.get("request_id") or "") or None,
        provider_success=True,
        provider_error_type=None,
    )


def failure_record(
    *,
    trace_id: str,
    text: str,
    authoritative_decision: AuthoritativeIntentDecision,
    error_type: str,
    in_flight_at_dispatch: int,
    max_in_flight: int,
) -> ShadowAuditRecord:
    return ShadowAuditRecord(
        event="decision_shadow",
        trace_id=trace_id,
        provider="jev",
        text_sha256=_text_sha256(text),
        authoritative_label=authoritative_decision.label.value,
        authoritative_label_resolution=authoritative_decision.resolution,
        authoritative_label_source=authoritative_decision.source,
        comparable=authoritative_decision.comparable,
        shadow_attempted=True,
        shadow_skipped=False,
        shadow_skipped_reason=None,
        in_flight_at_dispatch=in_flight_at_dispatch,
        max_in_flight=max_in_flight,
        shadow_label=None,
        agreement=None,
        transaction_escalation_disagreement=False,
        transaction_deescalation_disagreement=False,
        low_confidence=None,
        shadow_confidence=None,
        shadow_probabilities=None,
        shadow_latency_ms=None,
        shadow_model=None,
        shadow_request_id=None,
        provider_success=False,
        provider_error_type=error_type,
    )


def skip_record(
    *,
    trace_id: str,
    text: str,
    authoritative_decision: AuthoritativeIntentDecision,
    reason: Literal["disabled", "sampling", "capacity"],
    in_flight_at_dispatch: int | None,
    max_in_flight: int | None,
) -> ShadowAuditRecord:
    return ShadowAuditRecord(
        event="decision_shadow_skip",
        trace_id=trace_id,
        provider="jev",
        text_sha256=_text_sha256(text),
        authoritative_label=authoritative_decision.label.value,
        authoritative_label_resolution=authoritative_decision.resolution,
        authoritative_label_source=authoritative_decision.source,
        comparable=authoritative_decision.comparable,
        shadow_attempted=False,
        shadow_skipped=True,
        shadow_skipped_reason=reason,
        in_flight_at_dispatch=in_flight_at_dispatch,
        max_in_flight=max_in_flight,
        shadow_label=None,
        agreement=None,
        transaction_escalation_disagreement=False,
        transaction_deescalation_disagreement=False,
        low_confidence=None,
        shadow_confidence=None,
        shadow_probabilities=None,
        shadow_latency_ms=None,
        shadow_model=None,
        shadow_request_id=None,
        provider_success=None,
        provider_error_type=None,
    )
