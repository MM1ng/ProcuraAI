from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from app.core.config import DATA_DIR


HISTORY_FILE = DATA_DIR / "procurement_history.json"


def _read_history() -> list[dict[str, Any]]:
    if not HISTORY_FILE.exists():
        return []
    content = HISTORY_FILE.read_text(encoding="utf-8").strip()
    if not content:
        return []
    return json.loads(content)


def _write_history(records: list[dict[str, Any]]) -> None:
    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    HISTORY_FILE.write_text(json.dumps(records, indent=2), encoding="utf-8")


def _extract_total_cost(plan: dict[str, Any]) -> float:
    total = plan.get("total_amount", plan.get("total_cost", 0))
    if total:
        return round(float(total), 2)
    items = plan.get("items", plan.get("selected_items", []))
    return round(sum(float(item.get("subtotal", 0) or 0) for item in items), 2)


def create_history_record(payload: dict[str, Any]) -> dict[str, Any]:
    selected_plan = payload.get("selected_plan") or payload.get("procurement_plan") or {}
    parsed_intent = payload.get("parsed_intent") or payload.get("agent_understanding") or {}
    record = {
        "id": f"HIST-{uuid.uuid4().hex[:10].upper()}",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "original_request": payload.get("original_request", ""),
        "parsed_intent": parsed_intent,
        "agent_understanding": payload.get("agent_understanding", parsed_intent),
        "selected_plan": selected_plan,
        "procurement_plan": payload.get("procurement_plan", selected_plan),
        "total_cost": _extract_total_cost(selected_plan),
        "trace": payload.get("trace") or {},
        "reasoning_summary": payload.get("reasoning_summary", ""),
        "messages": payload.get("messages", []),
        "order_draft": payload.get("order_draft"),
    }
    records = _read_history()
    records.append(record)
    _write_history(records)
    return record


def list_history_records() -> list[dict[str, Any]]:
    return sorted(_read_history(), key=lambda item: item.get("created_at", ""), reverse=True)


def get_history_record(history_id: str) -> dict[str, Any] | None:
    for record in _read_history():
        if record.get("id") == history_id:
            return record
    return None


def delete_history_record(history_id: str) -> bool:
    records = _read_history()
    remaining = [record for record in records if record.get("id") != history_id]
    if len(remaining) == len(records):
        return False
    _write_history(remaining)
    return True
