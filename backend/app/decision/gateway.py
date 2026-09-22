from __future__ import annotations

import hashlib
import threading
from dataclasses import dataclass
from typing import Callable

from app.core.config import get_settings
from app.decision.observability import emit_shadow_audit
from app.decision.providers.jev import JevProvider
from app.decision.schemas import DecisionResult, IntentLabel
from app.decision.shadow import failure_record, success_record


@dataclass(frozen=True)
class ShadowConfig:
    enabled: bool
    timeout_ms: int
    sample_rate: float
    log_probabilities: bool

    @classmethod
    def from_settings(cls) -> "ShadowConfig":
        settings = get_settings()
        return cls(
            enabled=settings.jev_shadow_enabled,
            timeout_ms=max(settings.jev_shadow_timeout_ms, 1),
            sample_rate=min(max(settings.jev_shadow_sample_rate, 0.0), 1.0),
            log_probabilities=settings.jev_shadow_log_probabilities,
        )


def is_sampled(trace_id: str, sample_rate: float) -> bool:
    if sample_rate <= 0:
        return False
    if sample_rate >= 1:
        return True
    bucket = int(hashlib.sha256(trace_id.encode("utf-8")).hexdigest()[:16], 16) / (16**16)
    return bucket < sample_rate


def run_shadow_evaluation(
    *,
    text: str,
    trace_id: str,
    authoritative_label: IntentLabel,
    config: ShadowConfig,
    provider_factory: Callable[[], JevProvider] = JevProvider,
    emit: Callable[[dict], None] = emit_shadow_audit,
) -> None:
    """Run one bounded, audit-only Jev call outside the authority path."""
    completed = threading.Event()
    outcome: dict[str, DecisionResult | Exception] = {}

    def classify() -> None:
        try:
            outcome["result"] = provider_factory().classify_intent(text)
        except Exception as exc:  # SDK failures must always be isolated.
            outcome["error"] = exc
        finally:
            completed.set()

    worker = threading.Thread(target=classify, daemon=True, name="jev-shadow-provider")
    worker.start()
    if not completed.wait(config.timeout_ms / 1000):
        emit(failure_record(
            trace_id=trace_id, text=text, authoritative_label=authoritative_label, error_type="timeout"
        ).as_event())
        return

    error = outcome.get("error")
    if error is not None:
        emit(failure_record(
            trace_id=trace_id,
            text=text,
            authoritative_label=authoritative_label,
            error_type=type(error).__name__,
        ).as_event())
        return

    result = outcome.get("result")
    if not isinstance(result, DecisionResult):
        emit(failure_record(
            trace_id=trace_id, text=text, authoritative_label=authoritative_label, error_type="invalid_response"
        ).as_event())
        return
    emit(success_record(
        trace_id=trace_id,
        text=text,
        authoritative_label=authoritative_label,
        result=result,
        log_probabilities=config.log_probabilities,
    ).as_event())


def dispatch_jev_shadow(
    *,
    text: str,
    trace_id: str,
    authoritative_label: IntentLabel,
    config: ShadowConfig | None = None,
) -> bool:
    """Schedule shadow work and return immediately without changing authority."""
    effective_config = config or ShadowConfig.from_settings()
    if not effective_config.enabled or not is_sampled(trace_id, effective_config.sample_rate):
        return False
    threading.Thread(
        target=run_shadow_evaluation,
        kwargs={
            "text": text,
            "trace_id": trace_id,
            "authoritative_label": authoritative_label,
            "config": effective_config,
        },
        daemon=True,
        name="jev-shadow-dispatch",
    ).start()
    return True
