from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException

from app.core.config import get_settings
from app.decision.runtime import set_decision_enabled, status, RUNTIME_STORAGE_ERRORS, report_runtime_fault


router = APIRouter(prefix="/api/decision", tags=["decision"])


def _unavailable(operation: str) -> HTTPException:
    return HTTPException(status_code=503, detail={
        "code": "DECISION_RUNTIME_UNAVAILABLE", "runtime_available": False,
        "runtime_faults": [operation],
    })


def _control_change(enabled: bool, reason: str) -> dict:
    try:
        return set_decision_enabled(enabled, reason)
    except RUNTIME_STORAGE_ERRORS:
        report_runtime_fault("runtime_control_write_failed")
        raise _unavailable("runtime_control_write_failed") from None


def _require_control_access(token: str | None, *, action: str) -> None:
    settings = get_settings()
    environment = settings.decision_control_env.strip().lower()
    production_rollback = environment in {"prod", "production"} and action == "rollback"
    if environment not in {"dev", "development", "test", "local"} and not production_rollback:
        raise HTTPException(status_code=404, detail="Decision control is unavailable in this environment")
    if not settings.decision_control_token or token != settings.decision_control_token:
        raise HTTPException(status_code=401, detail="Decision control authentication required")


@router.get("/status")
def get_decision_status() -> dict:
    return status()


@router.post("/rollback")
def rollback_jev(x_decision_token: str | None = Header(default=None), reason: str = "manual_rollback") -> dict:
    _require_control_access(x_decision_token, action="rollback")
    change = _control_change(False, reason)
    return {"status": "rolled_back", "decision_source": "baseline", "change": change}


@router.post("/enable")
def enable_jev(x_decision_token: str | None = Header(default=None), reason: str = "manual_enable") -> dict:
    _require_control_access(x_decision_token, action="enable")
    change = _control_change(True, reason)
    state = status()
    if not state["runtime_available"]:
        raise _unavailable("runtime_status_read_failed")
    return {
        "status": "enabled",
        "decision_source": "mixed" if state["jev_authority_active"] else "baseline",
        "jev_decision_traffic_percent": state["jev_decision_traffic_percent"],
        "change": change,
    }
