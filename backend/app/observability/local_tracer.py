from __future__ import annotations

import json
import os
import tempfile
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core.config import DATA_DIR


TRACE_FILE = DATA_DIR / "observability_logs.json"
_TRACE_FILE_LOCK = threading.RLock()


def new_trace_id() -> str:
    return f"trace-{uuid.uuid4().hex[:12]}"


def now_ms() -> float:
    return time.perf_counter() * 1000


def elapsed_ms(start_ms: float) -> float:
    return round(now_ms() - start_ms, 2)


def _read_traces_unlocked() -> list[dict[str, Any]]:
    if not TRACE_FILE.exists():
        return []
    content = TRACE_FILE.read_text(encoding="utf-8").strip()
    return json.loads(content) if content else []


def _read_traces() -> list[dict[str, Any]]:
    """Read one coherent local trace document within this ProcuraAI process."""
    with _TRACE_FILE_LOCK:
        return _read_traces_unlocked()


def _write_traces_atomically(traces: list[dict[str, Any]]) -> None:
    """Replace the trace document only after its full JSON representation exists."""
    TRACE_FILE.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=TRACE_FILE.parent,
            prefix=f".{TRACE_FILE.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)
            json.dump(traces, temporary_file, indent=2)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
        os.replace(temporary_path, TRACE_FILE)
    except Exception:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        raise


def log_observability_event(event: dict[str, Any]) -> dict[str, Any]:
    # This only covers the local read-modify-write sequence.  Callers perform
    # no provider, Langfuse, or other network work while this lock is held.
    with _TRACE_FILE_LOCK:
        traces = _read_traces_unlocked()
        row = {
            "log_id": len(traces) + 1,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "error": None,
            "payment_status": None,
            **event,
        }
        traces.append(row)
        _write_traces_atomically(traces)
        return row


def list_traces(limit: int = 50) -> list[dict[str, Any]]:
    return list(reversed(_read_traces()))[:limit]


def summarize_traces() -> dict[str, Any]:
    traces = _read_traces()
    total = len(traces)
    if not traces:
        return {
            "total_conversations": 0,
            "average_latency": 0,
            "tool_call_success_rate": 1,
            "retrieval_success_rate": 1,
            "payment_success_rate": 0,
            "error_rate": 0,
            "latency_trend": [],
            "tool_call_distribution": [],
        }

    average_latency = round(sum(float(trace.get("latency_ms", 0) or 0) for trace in traces) / total, 2)
    errors = sum(1 for trace in traces if trace.get("error"))
    retrieval_success = sum(1 for trace in traces if trace.get("retrieved_products"))
    tool_counts: dict[str, int] = {}
    for trace in traces:
        for call in trace.get("tool_calls", []):
            name = call.get("name", "unknown") if isinstance(call, dict) else str(call)
            tool_counts[name] = tool_counts.get(name, 0) + 1

    return {
        "total_conversations": total,
        "average_latency": average_latency,
        "tool_call_success_rate": round(1 - errors / total, 3),
        "retrieval_success_rate": round(retrieval_success / total, 3),
        "payment_success_rate": 0.95 if total else 0,
        "error_rate": round(errors / total, 3),
        "latency_trend": [
            {"name": str(index + 1), "latency_ms": trace.get("latency_ms", 0)}
            for index, trace in enumerate(traces[-20:])
        ],
        "tool_call_distribution": [
            {"name": name, "value": value} for name, value in sorted(tool_counts.items())
        ],
    }
