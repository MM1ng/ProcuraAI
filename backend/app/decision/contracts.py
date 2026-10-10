from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.agent.router import transaction_intent
from app.decision.schemas import DecisionResult, IntentLabel


TRANSACTION_LABELS = {IntentLabel.CONFIRM_ORDER, IntentLabel.PAYMENT, IntentLabel.CANCEL}
RETRIEVAL_LABELS = {
    IntentLabel.RECOMMEND,
    IntentLabel.MODIFY_PLAN,
    IntentLabel.COMPARE_PLAN,
    IntentLabel.EXPLAIN_PLAN,
}
JEV_ROUTE_MAP = {
    IntentLabel.RECOMMEND: IntentLabel.RECOMMEND,
    IntentLabel.MODIFY_PLAN: IntentLabel.MODIFY_PLAN,
    IntentLabel.COMPARE_PLAN: IntentLabel.COMPARE_PLAN,
    IntentLabel.EXPLAIN_PLAN: IntentLabel.EXPLAIN_PLAN,
    IntentLabel.CONFIRM_ORDER: IntentLabel.CONFIRM_ORDER,
    IntentLabel.PAYMENT: IntentLabel.PAYMENT,
    IntentLabel.CANCEL: IntentLabel.CANCEL,
    IntentLabel.ORDER_STATUS: IntentLabel.ORDER_STATUS,
    IntentLabel.CLARIFY: IntentLabel.CLARIFY,
    IntentLabel.UNKNOWN: IntentLabel.CLARIFY,
}


@dataclass(frozen=True)
class DecisionContract:
    """The validated decision that application code is allowed to consume."""

    label: IntentLabel
    decision_source: str
    authoritative: bool
    fallback_used: bool
    fallback_reason: str | None = None
    provider_result: DecisionResult | None = None
    authority_bucket: str = "baseline"
    authority_traffic_percent: float = 0.0
    runtime_available: bool = True
    runtime_faults: tuple[str, ...] = ()

    @property
    def allows_retrieval_rewrite(self) -> bool:
        return self.label in RETRIEVAL_LABELS

    @property
    def is_transaction(self) -> bool:
        return self.label in TRANSACTION_LABELS


def map_decision_label(label: IntentLabel) -> IntentLabel:
    """Keep the Jev taxonomy explicit; never silently turn unknown into recommend."""
    if not isinstance(label, IntentLabel) or label not in JEV_ROUTE_MAP:
        raise ValueError("unmapped_jev_label")
    return JEV_ROUTE_MAP[label]


def transaction_gate_passes(message: str, label: IntentLabel) -> bool:
    """Model classification never grants transaction authority by itself."""
    if label == IntentLabel.CONFIRM_ORDER:
        return transaction_intent(message) == "confirm_order"
    if label == IntentLabel.PAYMENT:
        return transaction_intent(message) == "payment"
    if label == IntentLabel.CANCEL:
        return transaction_intent(message) == "cancel"
    return True


def decision_context(
    *,
    contract: DecisionContract,
    transaction_gate: str,
    plan_id: str | None = None,
    plan_hash: str | None = None,
) -> dict[str, Any]:
    result = contract.provider_result
    return {
        "decision_source": contract.decision_source,
        "authoritative": contract.authoritative,
        "jev_label": result.label.value if result else None,
        "mapped_route": contract.label.value,
        "fallback_used": contract.fallback_used,
        "fallback_reason": contract.fallback_reason,
        "authority_bucket": contract.authority_bucket,
        "authority_traffic_percent": contract.authority_traffic_percent,
        "runtime_available": contract.runtime_available,
        "runtime_faults": list(contract.runtime_faults),
        "transaction_gate": transaction_gate,
        "plan_id": plan_id,
        "plan_hash": plan_hash,
        "provider_latency_ms": result.latency_ms if result else None,
        "provider_error": contract.fallback_reason if contract.fallback_used else None,
        "timeout": contract.fallback_reason == "timeout",
    }
