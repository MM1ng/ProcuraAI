from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from app.core.config import DATA_DIR
from app.services.caller_identity import require_caller, require_owner
from app.services.confirmed_transaction import require_snapshot
from app.services.order_service import get_order
from app.services.transaction_lock import transaction_locked


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


@transaction_locked
def create_history_record(payload: dict[str, Any]) -> dict[str, Any]:
    actor = require_caller()
    plans = [payload[key] for key in ("selected_plan", "procurement_plan") if payload.get(key)]
    if not plans:
        raise ValueError("An owned server plan is required.")
    canonical = [require_snapshot(p.get("session_id"), p.get("plan_id"), p.get("plan_hash"), p.get("plan_version")) for p in plans]
    selected_plan = canonical[0]
    if any(p["plan_id"] != selected_plan["plan_id"] for p in canonical):
        raise ValueError("History plans must refer to the same selection.")
    order = None
    if payload.get("order_draft"):
        order = get_order(payload["order_draft"].get("order_id"))
        require_owner(order)
        if order.get("procurement_plan", {}).get("plan_id") != selected_plan["plan_id"]:
            raise ValueError("Order does not belong to this plan.")
    parsed_intent = payload.get("parsed_intent") or payload.get("agent_understanding") or {}
    record = {
        "id": f"HIST-{uuid.uuid4().hex[:10].upper()}",
        "owner_actor_id": actor.actor_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "original_request": payload.get("original_request", ""),
        "parsed_intent": parsed_intent,
        "agent_understanding": payload.get("agent_understanding", parsed_intent),
        "selected_plan": selected_plan,
        "procurement_plan": selected_plan,
        "total_cost": _extract_total_cost(selected_plan),
        "trace": payload.get("trace") or {},
        "reasoning_summary": payload.get("reasoning_summary", ""),
        "messages": payload.get("messages", []),
        "order_draft": order,
    }
    records = _read_history()
    records.append(record)
    _write_history(records)
    return record


def list_history_records() -> list[dict[str, Any]]:
    actor = require_caller()
    return sorted([record for record in _read_history() if record.get("owner_actor_id") == actor.actor_id],
                  key=lambda item: item.get("created_at", ""), reverse=True)


def get_history_record(history_id: str) -> dict[str, Any] | None:
    require_caller()
    for record in _read_history():
        if record.get("id") == history_id:
            require_owner(record)
            return record
    return None


@transaction_locked
def delete_history_record(history_id: str) -> bool:
    if get_history_record(history_id) is None:
        return False
    records = _read_history()
    remaining = [record for record in records if record.get("id") != history_id]
    if len(remaining) == len(records):
        return False
    _write_history(remaining)
    return True
