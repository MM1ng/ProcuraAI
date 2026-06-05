from __future__ import annotations

from app.evaluation.mock_eval_runner import summarize_evaluations
from app.observability.local_tracer import list_traces, summarize_traces


def observability_summary() -> dict:
    return summarize_traces()


def observability_traces(limit: int = 50) -> list[dict]:
    return list_traces(limit=limit)


def evaluation_summary() -> dict:
    return summarize_evaluations()
