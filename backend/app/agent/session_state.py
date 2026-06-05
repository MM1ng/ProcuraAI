from __future__ import annotations

from copy import deepcopy
from typing import Any


_SESSIONS: dict[str, dict[str, Any]] = {}


def get_session_state(session_id: str) -> dict[str, Any] | None:
    state = _SESSIONS.get(session_id)
    return deepcopy(state) if state else None


def save_session_state(
    session_id: str,
    intent: dict[str, Any],
    plan: dict[str, Any],
    retrieved_products: list[dict[str, Any]],
    trace_id: str,
) -> None:
    _SESSIONS[session_id] = {
        "parsed_intent": deepcopy(intent),
        "recommended_plan": deepcopy(plan),
        "retrieved_products": deepcopy(retrieved_products),
        "trace_id": trace_id,
    }


def clear_session_state(session_id: str | None = None) -> None:
    if session_id is None:
        _SESSIONS.clear()
        return
    _SESSIONS.pop(session_id, None)
