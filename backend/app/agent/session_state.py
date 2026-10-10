from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4
from collections import Counter
from app.services.transaction_lock import TRANSACTION_LOCK

from app.services import product_service
from app.services.caller_identity import require_caller, require_owner, read_resource, save_resource

_SESSIONS: dict[str, dict[str, Any]] = {}
SNAPSHOT_TTL_SECONDS = 1800

def create_session():
    caller = require_caller()
    session_id = uuid4().hex
    with TRANSACTION_LOCK:
        _SESSIONS[session_id] = {"owner_actor_id": caller.actor_id, "parsed_intent": {}, "recommended_plan": {}}
        save_resource("session", session_id, _SESSIONS[session_id])
    return session_id

def require_session_owner(session_id, caller=None):
    if session_id not in _SESSIONS:
        persisted = read_resource("session", session_id)
        if persisted:
            _SESSIONS[session_id] = persisted
    return require_owner(_SESSIONS.get(session_id), caller)

_NON_TRANSACTIONAL_PLAN_FIELDS = {
    "plan_hash",
    "plan_id",
    "plan_version",
    "created_at",
    "trace_id",
    "session_id",
    "recommendation_reason",
    "recommendation_summary",
}


def with_plan_snapshot(plan: dict[str, Any], session_id: str, trace_id: str) -> dict[str, Any]:
    """Attach a stable session-scoped identity to the executable plan content."""
    snapshot = deepcopy(plan)
    previous = _SESSIONS.get(session_id)
    candidate_hash = calculate_plan_hash(snapshot)
    previous_snapshot = (previous or {}).get("recommended_plan") or {}
    previous_hash = calculate_plan_hash(previous_snapshot) if previous_snapshot else None
    previous_version = int(previous_snapshot.get("plan_version", 0) or 0)

    fresh = False
    try:
        age = (datetime.now(timezone.utc) - datetime.fromisoformat(previous_snapshot["created_at"])).total_seconds()
        fresh = 0 <= age <= SNAPSHOT_TTL_SECONDS
    except (KeyError, ValueError, TypeError):
        pass
    if previous_hash == candidate_hash and previous_snapshot and fresh:
        version = previous_version
        created_at = previous_snapshot.get("created_at")
        plan_id = previous_snapshot["plan_id"]
    else:
        version = previous_version + 1 if previous_snapshot else 1
        created_at = datetime.now(timezone.utc).isoformat()
        # A new session incarnation must not reuse a pre-restart confirmation.
        plan_id = f"plan-{session_id}-v{version}-{uuid4().hex[:12]}"

    # A trace identifies a request, not a plan. The session and plan version
    # identify the user's current confirmed plan across repeated requests.
    snapshot["plan_version"] = version
    snapshot["plan_id"] = plan_id
    snapshot["session_id"] = session_id
    snapshot["created_at"] = created_at
    snapshot["plan_hash"] = candidate_hash
    return snapshot


def _canonical_plan_payload(plan: dict[str, Any]) -> dict[str, Any]:
    if isinstance(plan, dict):
        return {
            key: _canonical_plan_payload(value)
            for key, value in sorted(plan.items())
            if key not in _NON_TRANSACTIONAL_PLAN_FIELDS
        }
    if isinstance(plan, list):
        return [_canonical_plan_payload(value) for value in plan]
    return deepcopy(plan)


def calculate_plan_hash(plan: dict[str, Any]) -> str:
    canonical = json.dumps(
        _canonical_plan_payload(plan), ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def get_session_state(session_id: str) -> dict[str, Any] | None:
    require_session_owner(session_id)
    state = _SESSIONS.get(session_id)
    return deepcopy(state) if state else None


def save_session_state(
    session_id: str,
    intent: dict[str, Any],
    plan: dict[str, Any],
    retrieved_products: list[dict[str, Any]],
    trace_id: str,
    plan_options: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    with TRANSACTION_LOCK:
        return _save_session_state(session_id, intent, plan, retrieved_products, trace_id, plan_options)


def _save_session_state(session_id, intent, plan, retrieved_products, trace_id, plan_options):
    caller = require_session_owner(session_id)
    snapshot = with_plan_snapshot(plan, session_id, trace_id)
    options = deepcopy(plan_options or [])
    for index, option in enumerate(options):
        candidate = option["plan"]
        if candidate.get("plan_option_id") == snapshot.get("plan_option_id"):
            option["plan"] = deepcopy(snapshot)
        else:
            candidate.update({"plan_id": f'{snapshot["plan_id"]}-option-{index}',
                              "plan_version": snapshot["plan_version"], "session_id": session_id,
                              "created_at": snapshot["created_at"], "plan_hash": calculate_plan_hash(candidate)})
    _SESSIONS[session_id] = {
        "owner_actor_id": caller.actor_id,
        "parsed_intent": deepcopy(intent),
        "recommended_plan": snapshot,
        "plan_id": snapshot["plan_id"],
        "plan_hash": snapshot["plan_hash"],
        "retrieved_products": deepcopy(retrieved_products),
        "trace_id": trace_id,
        "plan_options": options,
    }
    save_resource("session", session_id, _SESSIONS[session_id])
    return deepcopy(_SESSIONS[session_id])


def validate_plan_snapshot(
    session_id: str,
    plan_id: str | None,
    plan_hash: str | None,
    plan_version: int | None = None,
) -> tuple[dict[str, Any] | None, list[str]]:
    require_session_owner(session_id)
    state = _SESSIONS.get(session_id)
    if not state:
        return None, ["plan_session_missing"]
    snapshot = deepcopy(state.get("recommended_plan") or {})
    reasons: list[str] = []
    if not plan_id or plan_id != snapshot.get("plan_id"):
        reasons.append("plan_id_mismatch")
    if not plan_hash or plan_hash != snapshot.get("plan_hash"):
        reasons.append("plan_hash_mismatch")
    if type(plan_version) is not int or plan_version != snapshot.get("plan_version"):
        reasons.append("plan_version_mismatch")
    reasons.extend(validate_snapshot_content(snapshot))
    return snapshot, reasons


def validate_snapshot_content(snapshot: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    if calculate_plan_hash(snapshot) != snapshot.get("plan_hash"):
        reasons.append("plan_snapshot_tampered")
    try:
        created = datetime.fromisoformat(snapshot["created_at"])
        age = (datetime.now(timezone.utc) - created).total_seconds()
        if age < 0 or age > SNAPSHOT_TTL_SECONDS:
            reasons.append("plan_snapshot_expired")
    except (KeyError, ValueError, TypeError):
        reasons.append("plan_snapshot_expired")

    catalog = {str(item.get("product_id")): item for item in product_service.load_products_from_csv()}
    quantities = Counter()
    for item in snapshot.get("items") or []:
        quantities[str(item.get("product_id") or "")] += int(item.get("quantity", 0) or 0)
    for item in snapshot.get("items") or []:
        product_id = str(item.get("product_id") or "")
        current = catalog.get(product_id)
        if current is None:
            reasons.append(f"product_missing:{product_id}")
            continue
        if round(float(item.get("unit_price", 0) or 0), 2) != round(float(current.get("price", 0) or 0), 2):
            reasons.append(f"price_changed:{product_id}")
        stock_changed = (
            int(current.get("stock", 0) or 0) < quantities[product_id]
            or ("stock" in item and int(item["stock"] or 0) != int(current.get("stock", 0) or 0))
        )
        if stock_changed and f"stock_changed:{product_id}" not in reasons:
            reasons.append(f"stock_changed:{product_id}")
        if int(item.get("delivery_days", 999) or 999) != int(current.get("delivery_days", 999) or 999):
            reasons.append(f"delivery_changed:{product_id}")
    return reasons


def clear_session_state(session_id: str | None = None) -> None:
    if session_id is None:
        _SESSIONS.clear()
        return
    _SESSIONS.pop(session_id, None)
