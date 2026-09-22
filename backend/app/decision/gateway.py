from __future__ import annotations

import hashlib
import threading
from dataclasses import dataclass
from typing import Callable

from app.core.config import get_settings
from app.decision.observability import emit_shadow_audit
from app.decision.providers.jev import JevProvider
from app.decision.schemas import DecisionResult
from app.decision.shadow import (
    AuthoritativeIntentDecision,
    failure_record,
    skip_record,
    success_record,
)


@dataclass(frozen=True)
class ShadowConfig:
    enabled: bool
    timeout_ms: int
    sample_rate: float
    log_probabilities: bool
    max_in_flight: int

    @classmethod
    def from_settings(cls) -> "ShadowConfig":
        settings = get_settings()
        return cls(
            enabled=settings.jev_shadow_enabled,
            timeout_ms=max(settings.jev_shadow_timeout_ms, 1),
            sample_rate=min(max(settings.jev_shadow_sample_rate, 0.0), 1.0),
            log_probabilities=settings.jev_shadow_log_probabilities,
            max_in_flight=max(settings.jev_shadow_max_in_flight, 1),
        )


class ShadowCapacityGate:
    """A process-local cap on real provider calls, not just wait threads."""

    def __init__(self, max_in_flight: int) -> None:
        self.max_in_flight = max(max_in_flight, 1)
        self._semaphore = threading.BoundedSemaphore(self.max_in_flight)
        self._lock = threading.Lock()
        self._in_flight = 0

    def try_acquire(self) -> int | None:
        if not self._semaphore.acquire(blocking=False):
            return None
        with self._lock:
            self._in_flight += 1
            return self._in_flight

    def release_after_provider_completion(self) -> None:
        with self._lock:
            self._in_flight -= 1
        self._semaphore.release()

    def current_in_flight(self) -> int:
        with self._lock:
            return self._in_flight


_capacity_gates: dict[int, ShadowCapacityGate] = {}
_capacity_gates_lock = threading.Lock()


def _capacity_gate(max_in_flight: int) -> ShadowCapacityGate:
    """Share capacity by configured limit without replacing gates holding calls."""
    bounded_limit = max(max_in_flight, 1)
    with _capacity_gates_lock:
        gate = _capacity_gates.get(bounded_limit)
        if gate is None:
            gate = ShadowCapacityGate(bounded_limit)
            _capacity_gates[bounded_limit] = gate
        return gate


def is_sampled(trace_id: str, sample_rate: float) -> bool:
    if sample_rate <= 0:
        return False
    if sample_rate >= 1:
        return True
    bucket = int(hashlib.sha256(trace_id.encode("utf-8")).hexdigest()[:16], 16) / (16**16)
    return bucket < sample_rate


def _safe_emit(emit: Callable[[dict], None], record: dict) -> None:
    """Observability is optional and can never make the authority path fail."""
    try:
        emit(record)
    except Exception:
        pass


def run_shadow_evaluation(
    *,
    text: str,
    trace_id: str,
    authoritative_decision: AuthoritativeIntentDecision,
    config: ShadowConfig,
    capacity_gate: ShadowCapacityGate,
    in_flight_at_dispatch: int,
    provider_factory: Callable[[], JevProvider] = JevProvider,
    emit: Callable[[dict], None] = emit_shadow_audit,
) -> None:
    """Wait only briefly; the slot releases when the real SDK call finally ends."""
    completed = threading.Event()
    outcome: dict[str, DecisionResult | Exception] = {}

    def classify() -> None:
        try:
            outcome["result"] = provider_factory().classify_intent(text)
        except Exception as exc:  # SDK failures must always be isolated.
            outcome["error"] = exc
        finally:
            # A timeout does not release capacity. This runs only after the SDK returns.
            capacity_gate.release_after_provider_completion()
            completed.set()

    provider_thread = threading.Thread(target=classify, daemon=True, name="jev-shadow-provider")
    try:
        provider_thread.start()
    except Exception:
        capacity_gate.release_after_provider_completion()
        _safe_emit(emit, failure_record(
            trace_id=trace_id,
            text=text,
            authoritative_decision=authoritative_decision,
            error_type="provider_thread_start_error",
            in_flight_at_dispatch=in_flight_at_dispatch,
            max_in_flight=config.max_in_flight,
        ).as_event())
        return
    if not completed.wait(config.timeout_ms / 1000):
        _safe_emit(emit, failure_record(
            trace_id=trace_id,
            text=text,
            authoritative_decision=authoritative_decision,
            error_type="timeout",
            in_flight_at_dispatch=in_flight_at_dispatch,
            max_in_flight=config.max_in_flight,
        ).as_event())
        return

    error = outcome.get("error")
    if error is not None:
        _safe_emit(emit, failure_record(
            trace_id=trace_id,
            text=text,
            authoritative_decision=authoritative_decision,
            error_type=type(error).__name__,
            in_flight_at_dispatch=in_flight_at_dispatch,
            max_in_flight=config.max_in_flight,
        ).as_event())
        return

    result = outcome.get("result")
    if not isinstance(result, DecisionResult):
        _safe_emit(emit, failure_record(
            trace_id=trace_id,
            text=text,
            authoritative_decision=authoritative_decision,
            error_type="invalid_response",
            in_flight_at_dispatch=in_flight_at_dispatch,
            max_in_flight=config.max_in_flight,
        ).as_event())
        return
    _safe_emit(emit, success_record(
        trace_id=trace_id,
        text=text,
        authoritative_decision=authoritative_decision,
        result=result,
        log_probabilities=config.log_probabilities,
        in_flight_at_dispatch=in_flight_at_dispatch,
        max_in_flight=config.max_in_flight,
    ).as_event())


def dispatch_jev_shadow(
    *,
    text: str,
    trace_id: str,
    authoritative_decision: AuthoritativeIntentDecision,
    config: ShadowConfig | None = None,
    capacity_gate: ShadowCapacityGate | None = None,
    emit: Callable[[dict], None] = emit_shadow_audit,
    provider_factory: Callable[[], JevProvider] = JevProvider,
) -> bool:
    """Start audit-only work only after a real provider-call capacity slot is held."""
    effective_config = config or ShadowConfig.from_settings()
    if not effective_config.enabled:
        _safe_emit(emit, skip_record(
            trace_id=trace_id,
            text=text,
            authoritative_decision=authoritative_decision,
            reason="disabled",
            in_flight_at_dispatch=None,
            max_in_flight=effective_config.max_in_flight,
        ).as_event())
        return False
    if not is_sampled(trace_id, effective_config.sample_rate):
        _safe_emit(emit, skip_record(
            trace_id=trace_id,
            text=text,
            authoritative_decision=authoritative_decision,
            reason="sampling",
            in_flight_at_dispatch=None,
            max_in_flight=effective_config.max_in_flight,
        ).as_event())
        return False

    gate = capacity_gate or _capacity_gate(effective_config.max_in_flight)
    in_flight_at_dispatch = gate.try_acquire()
    if in_flight_at_dispatch is None:
        _safe_emit(emit, skip_record(
            trace_id=trace_id,
            text=text,
            authoritative_decision=authoritative_decision,
            reason="capacity",
            in_flight_at_dispatch=gate.current_in_flight(),
            max_in_flight=gate.max_in_flight,
        ).as_event())
        return False

    try:
        threading.Thread(
            target=run_shadow_evaluation,
            kwargs={
                "text": text,
                "trace_id": trace_id,
                "authoritative_decision": authoritative_decision,
                "config": effective_config,
                "capacity_gate": gate,
                "in_flight_at_dispatch": in_flight_at_dispatch,
                "provider_factory": provider_factory,
                "emit": emit,
            },
            daemon=True,
            name="jev-shadow-dispatch",
        ).start()
    except Exception:
        gate.release_after_provider_completion()
        _safe_emit(emit, failure_record(
            trace_id=trace_id,
            text=text,
            authoritative_decision=authoritative_decision,
            error_type="dispatch_error",
            in_flight_at_dispatch=in_flight_at_dispatch,
            max_in_flight=gate.max_in_flight,
        ).as_event())
        return False
    return True
