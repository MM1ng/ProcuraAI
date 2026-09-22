from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass
from typing import Any

from app.agent.router import route_intent, transaction_intent
from app.decision.schemas import DecisionResult, IntentLabel


TRANSACTION_LABELS = {IntentLabel.CONFIRM_ORDER, IntentLabel.PAYMENT}
LOW_CONFIDENCE_THRESHOLD = 0.7


def authoritative_intent_label(
    message: str,
    intent: dict[str, Any],
    response_type: str | None,
) -> IntentLabel:
    """Represent the existing router's decision without changing it."""
    transaction = transaction_intent(message)
    if transaction == "confirm_order":
        return IntentLabel.CONFIRM_ORDER
    if transaction == "payment":
        return IntentLabel.PAYMENT

    revision_intent = str(intent.get("revision_intent") or "")
    if revision_intent in {"cheaper", "replace_product"}:
        return IntentLabel.MODIFY_PLAN

    route = route_intent(message).get("route")
    if route == "compare":
        return IntentLabel.COMPARE_PLAN
    if route in {"recommendation", "search"}:
        return IntentLabel.RECOMMEND
    if response_type == "recommendation_plan":
        return IntentLabel.RECOMMEND
    return IntentLabel.CLARIFY


@dataclass(frozen=True)
class ShadowAuditRecord:
    event: str
    trace_id: str
    provider: str
    text_sha256: str
    authoritative_label: str
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
    provider_success: bool
    provider_error_type: str | None

    def as_event(self) -> dict[str, Any]:
        return asdict(self)


def _text_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def success_record(
    *,
    trace_id: str,
    text: str,
    authoritative_label: IntentLabel,
    result: DecisionResult,
    log_probabilities: bool,
) -> ShadowAuditRecord:
    shadow_label = result.label
    authoritative_is_transaction = authoritative_label in TRANSACTION_LABELS
    shadow_is_transaction = shadow_label in TRANSACTION_LABELS
    return ShadowAuditRecord(
        event="decision_shadow",
        trace_id=trace_id,
        provider=result.provider,
        text_sha256=_text_sha256(text),
        authoritative_label=authoritative_label.value,
        shadow_label=shadow_label.value,
        agreement=authoritative_label == shadow_label,
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
    authoritative_label: IntentLabel,
    error_type: str,
) -> ShadowAuditRecord:
    return ShadowAuditRecord(
        event="decision_shadow",
        trace_id=trace_id,
        provider="jev",
        text_sha256=_text_sha256(text),
        authoritative_label=authoritative_label.value,
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
