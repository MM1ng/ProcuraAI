from __future__ import annotations

import hashlib
import math
import threading
from dataclasses import dataclass
from time import perf_counter
from typing import Any, Callable

from app.core.config import get_settings
from app.decision.observability import emit_shadow_audit
from app.decision.contracts import DecisionContract, map_decision_label, transaction_gate_passes
from app.decision.runtime import (
    decision_enabled, record_provider_failure, record_provider_success,
    RUNTIME_STORAGE_ERRORS, report_runtime_fault,
)
from app.decision.providers.jev import JevProvider
from app.decision.schemas import DecisionResult
from app.decision.shadow import (
    AuthoritativeIntentDecision,
    failure_record,
    skip_record,
    success_record,
)
from app.decision.schemas import IntentLabel


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


def resolve_jev_decision(
    *,
    text: str,
    fallback_label,
    context: dict[str, Any] | None = None,
    cohort_key: str | None = None,
    provider_factory: Callable[[], JevProvider] = JevProvider,
) -> DecisionContract:
    """Resolve Jev synchronously only when the feature flag is enabled.

    The timeout is a user-visible authority budget. A late provider result is
    deliberately ignored and can only be observed by the provider thread.
    """
    settings = get_settings()
    from app.decision.contracts import DecisionContract

    percent = getattr(settings, "jev_decision_traffic_percent", 0.0)
    if not isinstance(percent, (int, float)) or not math.isfinite(percent) or not 0 <= percent <= 100:
        percent = 0.0
    runtime_faults: list[str] = []

    def runtime_fault(operation: str) -> None:
        runtime_faults.append(operation)
        report_runtime_fault(operation)

    def baseline_contract(reason: str | None = None, *, bucket: str = "baseline") -> DecisionContract:
        return DecisionContract(
            label=fallback_label,
            decision_source="baseline",
            authoritative=True,
            fallback_used=reason is not None,
            fallback_reason=reason,
            authority_bucket=bucket,
            authority_traffic_percent=percent,
            runtime_available=not runtime_faults,
            runtime_faults=tuple(runtime_faults),
        )

    def failure_contract(reason: str, *, record_failure: bool = True) -> DecisionContract:
        # An invalid Jev outcome never becomes a new safety/transaction route.
        if record_failure:
            try:
                record_provider_failure(reason)
            except RUNTIME_STORAGE_ERRORS:
                runtime_fault("runtime_failure_write_failed")
        return baseline_contract(reason, bucket="jev")

    try:
        enabled = decision_enabled()
    except RUNTIME_STORAGE_ERRORS:
        runtime_fault("runtime_initial_read_failed")
        return baseline_contract("runtime_initial_read_failed", bucket="disabled")
    if not enabled:
        return baseline_contract(bucket="disabled")
    if not authority_is_sampled(cohort_key, percent):
        return baseline_contract(bucket="not_sampled")
    if fallback_label in {
        IntentLabel.CONFIRM_ORDER, IntentLabel.PAYMENT, IntentLabel.CANCEL,
        IntentLabel.ORDER_STATUS,
    }:
        return baseline_contract(bucket="protected_route")

    authority_gate = _authority_capacity_gate(settings.jev_max_in_flight)
    authority_slot = authority_gate.try_acquire()
    if authority_slot is None:
        return failure_contract("capacity")

    completed = threading.Event()
    outcome: dict[str, Any] = {}

    def classify() -> None:
        try:
            outcome["result"] = provider_factory().classify_intent(text, context=context or {})
        except Exception as exc:
            outcome["error"] = exc
        finally:
            # Capacity is held until the provider actually returns, including
            # after an authority timeout, so late results cannot stampede the SDK.
            authority_gate.release_after_provider_completion()
            completed.set()

    thread = threading.Thread(target=classify, daemon=True, name="jev-authoritative-provider")
    try:
        thread.start()
    except Exception as exc:
        authority_gate.release_after_provider_completion()
        return failure_contract("thread_start_error")
    if not completed.wait(max(settings.jev_timeout_ms, 1) / 1000):
        return failure_contract("timeout")

    error = outcome.get("error")
    result = outcome.get("result")
    if error is not None or result is None:
        reason = type(error).__name__ if error is not None else "invalid_response"
        return failure_contract(reason)

    if not isinstance(result, DecisionResult):
        return failure_contract("invalid_response")
    try:
        label = map_decision_label(result.label)
    except ValueError:
        return failure_contract("mapping_error")
    try:
        enabled = decision_enabled()
    except RUNTIME_STORAGE_ERRORS:
        runtime_fault("runtime_final_read_failed")
        return baseline_contract("runtime_final_read_failed", bucket="jev")
    if not enabled:
        return failure_contract("rollback_during_provider_call", record_failure=False)
    try:
        record_provider_success()
    except RUNTIME_STORAGE_ERRORS:
        runtime_fault("runtime_success_write_failed")
        return baseline_contract("runtime_success_write_failed", bucket="jev")
    if label in {IntentLabel.CONFIRM_ORDER, IntentLabel.PAYMENT, IntentLabel.CANCEL} and not transaction_gate_passes(text, label):
        return DecisionContract(
            label=fallback_label,
            decision_source="baseline",
            authoritative=True,
            fallback_used=True,
            fallback_reason="transaction_gate_blocked",
            provider_result=result,
            authority_bucket="jev",
            authority_traffic_percent=percent,
        )
    if label in {IntentLabel.CONFIRM_ORDER, IntentLabel.PAYMENT, IntentLabel.CANCEL}:
        # This stage only canaries non-transactional routing. Explicit user
        # commands still run through the existing baseline transaction chain.
        return DecisionContract(
            label=fallback_label,
            decision_source="baseline",
            authoritative=True,
            fallback_used=True,
            fallback_reason="transaction_route_baseline_only",
            provider_result=result,
            authority_bucket="jev",
            authority_traffic_percent=percent,
        )
    return DecisionContract(
        label=label,
        decision_source="jev",
        authoritative=True,
        fallback_used=False,
        provider_result=result,
        authority_bucket="jev",
        authority_traffic_percent=percent,
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
_authority_capacity_gates: dict[int, ShadowCapacityGate] = {}
_authority_capacity_gates_lock = threading.Lock()


def _capacity_gate(max_in_flight: int) -> ShadowCapacityGate:
    """Share capacity by configured limit without replacing gates holding calls."""
    bounded_limit = max(max_in_flight, 1)
    with _capacity_gates_lock:
        gate = _capacity_gates.get(bounded_limit)
        if gate is None:
            gate = ShadowCapacityGate(bounded_limit)
            _capacity_gates[bounded_limit] = gate
        return gate


def _authority_capacity_gate(max_in_flight: int) -> ShadowCapacityGate:
    """Keep authoritative and audit-only provider capacity independent."""
    bounded_limit = max(max_in_flight, 1)
    with _authority_capacity_gates_lock:
        gate = _authority_capacity_gates.get(bounded_limit)
        if gate is None:
            gate = ShadowCapacityGate(bounded_limit)
            _authority_capacity_gates[bounded_limit] = gate
        return gate


def is_sampled(trace_id: str, sample_rate: float) -> bool:
    if sample_rate <= 0:
        return False
    if sample_rate >= 1:
        return True
    bucket = int(hashlib.sha256(trace_id.encode("utf-8")).hexdigest()[:16], 16) / (16**16)
    return bucket < sample_rate


def authority_is_sampled(cohort_key: str | None, percent: float) -> bool:
    """Stable across requests and processes; missing identity is baseline-only."""
    if (not isinstance(cohort_key, str) or not cohort_key.strip()
            or cohort_key == "demo-session-001" or percent <= 0):
        return False
    if percent >= 100:
        return True
    bucket = int.from_bytes(hashlib.sha256(cohort_key.encode("utf-8")).digest()[:8], "big")
    return bucket / (1 << 64) < percent / 100


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
    provider_factory: Callable[[], JevProvider] | None = None,
    emit: Callable[[dict], None] = emit_shadow_audit,
) -> None:
    """Wait only briefly; the slot releases when the real SDK call finally ends."""
    completed = threading.Event()
    outcome: dict[str, Any] = {}

    def classify() -> None:
        provider = None
        provider_started = perf_counter()
        try:
            if provider_factory is None:
                # Keep the SDK request inside the outer Shadow deadline. The
                # default SDK retries can otherwise outlive this budget and
                # hold a Shadow capacity slot for tens of seconds.
                provider_timeout = max((config.timeout_ms - 500) / 1000, 0.1)
                provider = JevProvider(timeout_seconds=provider_timeout, max_retries=0)
            else:
                provider = provider_factory()
            outcome["result"] = provider.classify_intent(text)
        except Exception as exc:  # SDK failures must always be isolated.
            outcome["error"] = exc
        finally:
            measured_elapsed_ms = (perf_counter() - provider_started) * 1000
            metrics = getattr(provider, "last_call_metrics", {}) if provider is not None else {}
            if not isinstance(metrics, dict):
                metrics = {}
            outcome["provider_call_elapsed_ms"] = metrics.get("provider_call_elapsed_ms") or measured_elapsed_ms
            outcome["provider_retry_count"] = metrics.get("provider_retry_count")
            outcome["provider_final_error_type"] = metrics.get(
                "provider_final_error_type",
                type(outcome["error"]).__name__ if outcome.get("error") is not None else None,
            )
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
            shadow_timeout_ms=config.timeout_ms,
        ).as_event())
        return
    shadow_timed_out = not completed.wait(config.timeout_ms / 1000)
    if shadow_timed_out:
        # This dispatcher runs off the user-facing request thread. Wait for the
        # SDK's own bounded retry/HTTP timeouts so the audit row can contain the
        # true completion time, final error and actual HTTP retry count.
        completed.wait()
        _safe_emit(emit, failure_record(
            trace_id=trace_id,
            text=text,
            authoritative_decision=authoritative_decision,
            error_type="timeout",
            in_flight_at_dispatch=in_flight_at_dispatch,
            max_in_flight=config.max_in_flight,
            shadow_timeout_ms=config.timeout_ms,
            provider_call_elapsed_ms=outcome.get("provider_call_elapsed_ms"),
            provider_retry_count=outcome.get("provider_retry_count"),
            provider_final_error_type=outcome.get("provider_final_error_type"),
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
            shadow_timeout_ms=config.timeout_ms,
            provider_call_elapsed_ms=outcome.get("provider_call_elapsed_ms"),
            provider_retry_count=outcome.get("provider_retry_count"),
            provider_final_error_type=outcome.get("provider_final_error_type"),
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
            shadow_timeout_ms=config.timeout_ms,
            provider_call_elapsed_ms=outcome.get("provider_call_elapsed_ms"),
            provider_retry_count=outcome.get("provider_retry_count"),
            provider_final_error_type=outcome.get("provider_final_error_type"),
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
        shadow_timeout_ms=config.timeout_ms,
    ).as_event())


def dispatch_jev_shadow(
    *,
    text: str,
    trace_id: str,
    authoritative_decision: AuthoritativeIntentDecision,
    config: ShadowConfig | None = None,
    capacity_gate: ShadowCapacityGate | None = None,
    emit: Callable[[dict], None] = emit_shadow_audit,
    provider_factory: Callable[[], JevProvider] | None = None,
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
            shadow_timeout_ms=effective_config.timeout_ms,
        ).as_event())
        return False
    return True
