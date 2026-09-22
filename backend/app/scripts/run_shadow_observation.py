"""Run a controlled, sequential Jev Shadow observation without JSON polling.

Run from ``backend`` with the temporary D03.3R environment variables set, for
example ``python -m app.scripts.run_shadow_observation``.  The runner stores
Shadow audit records in memory, forwards them to the existing audit sink, and
uses the D03.3A temporary order/observability storage context.
"""

from __future__ import annotations

import argparse
import json
import math
import threading
import time
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Iterator, Sequence

import app.agent.procurement_agent as procurement_agent
from app.decision.gateway import ShadowConfig, dispatch_jev_shadow
from app.decision.observability import emit_shadow_audit
from app.decision.providers.jev import JevProvider
from app.decision.shadow_metrics import summarize_shadow_events
from app.decision.shadow_observation import isolated_shadow_observation_storage


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEV_DATASET = PROJECT_ROOT / "backend" / "evaluation" / "decision" / "intent_dev.jsonl"
DEFAULT_REPORT_PATH = Path(__file__).with_name("shadow_observation_report.json")
DEFAULT_RECORDS_PATH = Path(__file__).with_name("shadow_observation_records.jsonl")


@dataclass(frozen=True)
class ReplayCase:
    case_id: str
    text: str


class ShadowEventCollector:
    """Thread-safe completion signals for real Gateway audit records."""

    def __init__(self, forward: Callable[[dict[str, Any]], None] = emit_shadow_audit) -> None:
        self._forward = forward
        self._condition = threading.Condition()
        self.events: list[dict[str, Any]] = []
        self._by_trace_id: dict[str, dict[str, Any]] = {}

    def emit(self, record: dict[str, Any]) -> None:
        # Forward first: a waiter returning means this audit sink invocation has
        # completed (or failed), preventing a late audit write after context exit.
        try:
            self._forward(record)
        finally:
            with self._condition:
                captured = dict(record)
                self.events.append(captured)
                trace_id = str(captured.get("trace_id") or "")
                if trace_id:
                    self._by_trace_id[trace_id] = captured
                self._condition.notify_all()

    def wait_for_trace(self, trace_id: str, timeout_seconds: float) -> dict[str, Any] | None:
        deadline = time.monotonic() + timeout_seconds
        with self._condition:
            while trace_id not in self._by_trace_id:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return None
                self._condition.wait(remaining)
            return dict(self._by_trace_id[trace_id])


@dataclass(frozen=True)
class ShadowObservationResult:
    candidate_requests: int
    harness_errors: list[dict[str, str]]
    summary: dict[str, int | float]
    production_orders_unchanged: bool
    production_observability_unchanged: bool
    completed_trace_count: int
    collector_event_count: int
    provider_error_type_distribution: dict[str, int]
    records: list[dict[str, Any]]

    def as_report(self) -> dict[str, Any]:
        report = asdict(self)
        report.pop("records")
        return report


class ShadowObservationRunner:
    """Sequential full-Agent replay with a real Gateway dispatch wrapper."""

    def __init__(
        self,
        *,
        config: ShadowConfig | None = None,
        provider_factory: Callable[[], JevProvider] = JevProvider,
        audit_forward: Callable[[dict[str, Any]], None] = emit_shadow_audit,
        wait_margin_seconds: float = 2.0,
    ) -> None:
        self.config = config or ShadowConfig.from_settings()
        self.provider_factory = provider_factory
        self.collector = ShadowEventCollector(audit_forward)
        self.wait_margin_seconds = wait_margin_seconds

    @contextmanager
    def _patched_agent_dispatch(self) -> Iterator[None]:
        original_dispatch = procurement_agent.dispatch_jev_shadow

        def collecting_dispatch(**kwargs: Any) -> bool:
            return dispatch_jev_shadow(
                **kwargs,
                config=self.config,
                provider_factory=self.provider_factory,
                emit=self.collector.emit,
            )

        procurement_agent.dispatch_jev_shadow = collecting_dispatch
        try:
            yield
        finally:
            procurement_agent.dispatch_jev_shadow = original_dispatch

    def run_cases(self, cases: Sequence[ReplayCase], *, retried: bool = False) -> ShadowObservationResult:
        production_orders = PROJECT_ROOT / "data" / "orders.json"
        production_observability = PROJECT_ROOT / "data" / "observability_logs.json"
        orders_before = production_orders.read_bytes()
        observability_before = production_observability.read_bytes()
        harness_errors: list[dict[str, str]] = []
        completed_trace_ids: set[str] = set()
        records: list[dict[str, Any]] = []

        with isolated_shadow_observation_storage():
            with self._patched_agent_dispatch():
                for case in cases:
                    result = procurement_agent.run_procurement_agent(
                        case.text,
                        session_id=f"shadow-observation-{case.case_id}",
                        skip_plan_explanation=True,
                    )
                    trace_id = str(result["trace_id"])
                    event = self.collector.wait_for_trace(
                        trace_id,
                        self.config.timeout_ms / 1000 + self.wait_margin_seconds,
                    )
                    if event is None:
                        harness_errors.append({"case_id": case.case_id, "trace_id": trace_id})
                    else:
                        completed_trace_ids.add(trace_id)
                        records.append(_record_for_case(case.case_id, event, retried=retried))

                # Every expected audit has completed its forward call. Gateway
                # provider threads that outlive a timeout only release capacity;
                # they do not emit another audit record after this point.
                expected_trace_count = len(cases)
                if len(completed_trace_ids) != expected_trace_count:
                    harness_errors.append({
                        "case_id": "drain",
                        "trace_id": f"completed={len(completed_trace_ids)}/{expected_trace_count}",
                    })

        orders_unchanged = production_orders.read_bytes() == orders_before
        observability_unchanged = production_observability.read_bytes() == observability_before
        if not orders_unchanged or not observability_unchanged:
            raise RuntimeError(
                "Controlled Shadow observation modified production persistence: "
                f"orders_unchanged={orders_unchanged}, observability_unchanged={observability_unchanged}"
            )
        summary = summarize_shadow_events(self.collector.events)
        return ShadowObservationResult(
            candidate_requests=len(cases),
            harness_errors=harness_errors,
            summary=summary,
            production_orders_unchanged=orders_unchanged,
            production_observability_unchanged=observability_unchanged,
            completed_trace_count=len(completed_trace_ids),
            collector_event_count=len(self.collector.events),
            provider_error_type_distribution=_provider_error_type_distribution(records),
            records=records,
        )


def load_dev_cases(dataset_path: Path = DEV_DATASET) -> list[ReplayCase]:
    return [
        ReplayCase(case_id=str(row["id"]), text=str(row["text"]))
        for row in (json.loads(line) for line in dataset_path.read_text(encoding="utf-8").splitlines() if line.strip())
    ]


def _record_for_case(case_id: str, event: dict[str, Any], *, retried: bool) -> dict[str, Any]:
    """Persist only audit-safe, case-joinable fields; never replay text."""
    fields = (
        "trace_id", "event", "authoritative_label", "authoritative_label_resolution",
        "shadow_label", "agreement", "transaction_escalation_disagreement",
        "transaction_deescalation_disagreement", "provider_success", "provider_error_type",
        "shadow_latency_ms",
    )
    return {"case_id": case_id, "retried": retried, **{field: event.get(field) for field in fields}}


def _provider_error_type_distribution(records: Sequence[dict[str, Any]]) -> dict[str, int]:
    distribution: dict[str, int] = {}
    for record in records:
        if record.get("provider_success") is not False:
            continue
        error_type = str(record.get("provider_error_type") or "unknown")
        distribution[error_type] = distribution.get(error_type, 0) + 1
    return dict(sorted(distribution.items()))


def load_records(records_path: Path) -> list[dict[str, Any]]:
    if not records_path.exists():
        return []
    return [json.loads(line) for line in records_path.read_text(encoding="utf-8").splitlines() if line.strip()]


def merge_records(existing: Sequence[dict[str, Any]], replayed: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep one canonical row per DEV case; successful retry replaces failure."""
    by_case = {str(record["case_id"]): dict(record) for record in existing}
    for record in replayed:
        case_id = str(record["case_id"])
        prior = by_case.get(case_id)
        if prior is None or record.get("provider_success") is True or prior.get("provider_success") is not True:
            by_case[case_id] = dict(record)
    return [by_case[case_id] for case_id in sorted(by_case)]


def write_records(records_path: Path, records: Sequence[dict[str, Any]]) -> None:
    records_path.write_text(
        "".join(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n" for record in records),
        encoding="utf-8",
    )


def summarize_records(records: Sequence[dict[str, Any]]) -> dict[str, int | float]:
    """Summarize one canonical record per case after an optional retry merge."""
    successes = [record for record in records if record.get("provider_success") is True]
    failures = [record for record in records if record.get("provider_success") is False]
    latencies = [float(record["shadow_latency_ms"]) for record in successes if record.get("shadow_latency_ms") is not None]
    ordered = sorted(latencies)
    percentile = lambda fraction: round(ordered[max(math.ceil(len(ordered) * fraction) - 1, 0)], 2) if ordered else 0.0
    agreements = sum(record.get("agreement") is True for record in successes)
    return {
        "record_count": len(records), "shadow_successes": len(successes), "shadow_failures": len(failures),
        "agreement_count": agreements, "agreement_rate": round(agreements / len(successes), 4) if successes else 0.0,
        "latency_mean_ms": round(sum(latencies) / len(latencies), 2) if latencies else 0.0,
        "latency_p50_ms": percentile(0.5), "latency_p95_ms": percentile(0.95),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the D03.3R controlled Jev Shadow observation.")
    parser.add_argument("--limit", type=int, default=None, help="Limit DEV cases for a controlled smoke run.")
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT_PATH)
    parser.add_argument("--records-path", type=Path, default=DEFAULT_RECORDS_PATH)
    parser.add_argument("--only-case-ids", nargs="+", default=None, help="Replay only these DEV case ids.")
    parser.add_argument("--merge-into", type=Path, default=None, help="Merge a retry into an existing records JSONL file.")
    args = parser.parse_args()
    cases = load_dev_cases()
    if args.limit is not None:
        cases = cases[:max(args.limit, 0)]
    if args.only_case_ids is not None:
        selected = set(args.only_case_ids)
        cases = [case for case in cases if case.case_id in selected]
        missing = selected - {case.case_id for case in cases}
        if missing:
            parser.error("Unknown DEV case ids: " + ", ".join(sorted(missing)))
    result = ShadowObservationRunner().run_cases(cases, retried=args.merge_into is not None)
    merged_records = merge_records(load_records(args.merge_into), result.records) if args.merge_into else result.records
    write_records(args.records_path, merged_records)
    report = result.as_report()
    report["record_count"] = len(merged_records)
    report["provider_error_type_distribution"] = _provider_error_type_distribution(merged_records)
    report["merged_summary"] = summarize_records(merged_records)
    args.report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if result.harness_errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
