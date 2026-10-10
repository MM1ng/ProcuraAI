from __future__ import annotations

import json
import logging
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core.config import DATA_DIR, get_settings


RUNTIME_STATE_PATH = DATA_DIR / "decision_runtime.sqlite3"


class RuntimeDataError(RuntimeError):
    """Persisted control state cannot be trusted; never expose its raw values."""


RUNTIME_STORAGE_ERRORS = (sqlite3.Error, OSError, json.JSONDecodeError, RuntimeDataError)
logger = logging.getLogger(__name__)


def report_runtime_fault(operation: str) -> None:
    # Stable operation only: storage exception messages can expose private paths.
    logger.warning("decision_runtime_unavailable operation=%s", operation)


class DecisionRuntimeStore:
    """SQLite-backed decision control state shared by workers on one host."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=5.0, isolation_level=None)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("PRAGMA busy_timeout = 5000")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS decision_runtime_state (
                    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
                    enabled_override INTEGER NULL CHECK (enabled_override IN (0, 1) OR enabled_override IS NULL),
                    last_change_json TEXT NULL,
                    consecutive_failures INTEGER NOT NULL DEFAULT 0 CHECK (consecutive_failures >= 0)
                )
                """
            )
        except sqlite3.Error:
            connection.close()
            raise
        return connection

    @staticmethod
    def _read_state(connection: sqlite3.Connection) -> dict[str, Any]:
        row = connection.execute(
            "SELECT enabled_override, last_change_json, consecutive_failures "
            "FROM decision_runtime_state WHERE singleton = 1"
        ).fetchone()
        if row is None:
            return {"override": None, "last_change": None, "consecutive_failures": 0}
        override, failures = row["enabled_override"], row["consecutive_failures"]
        if override is not None and (type(override) is not int or override not in (0, 1)):
            raise RuntimeDataError("invalid_runtime_state")
        if type(failures) is not int or failures < 0:
            raise RuntimeDataError("invalid_runtime_state")
        change = None
        encoded_change = row["last_change_json"]
        if encoded_change is not None:
            if not isinstance(encoded_change, str):
                raise RuntimeDataError("invalid_runtime_state")
            try:
                change = json.loads(encoded_change)
                if (not isinstance(change, dict) or type(change.get("enabled")) is not bool
                        or not isinstance(change.get("reason"), str)
                        or not isinstance(change.get("changed_at"), str)
                        or datetime.fromisoformat(change["changed_at"]).tzinfo is None):
                    raise RuntimeDataError("invalid_runtime_state")
            except (json.JSONDecodeError, ValueError) as exc:
                raise RuntimeDataError("invalid_runtime_state") from None
        return {
            "override": None if override is None else bool(override),
            "last_change": change,
            "consecutive_failures": failures,
        }

    def get_state(self) -> dict[str, Any]:
        with closing(self._connect()) as connection:
            return self._read_state(connection)

    def decision_enabled(self, configured_enabled: bool) -> bool:
        override = self.get_state()["override"]
        return bool(configured_enabled) if override is None else override

    def set_decision_enabled(self, enabled: bool, reason: str) -> dict[str, Any]:
        changed = {
            "enabled": bool(enabled),
            "reason": str(reason),
            "changed_at": datetime.now(timezone.utc).isoformat(),
        }
        with closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "INSERT OR IGNORE INTO decision_runtime_state (singleton) VALUES (1)"
            )
            self._read_state(connection)
            connection.execute(
                "UPDATE decision_runtime_state SET enabled_override = ?, last_change_json = ?, "
                "consecutive_failures = CASE WHEN ? = 1 THEN 0 ELSE consecutive_failures END "
                "WHERE singleton = 1",
                (int(bool(enabled)), json.dumps(changed), int(bool(enabled))),
            )
            connection.commit()
        return changed

    def record_provider_failure(self, reason: str, threshold: int) -> bool:
        bounded_threshold = max(int(threshold), 1)
        with closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "INSERT OR IGNORE INTO decision_runtime_state (singleton) VALUES (1)"
            )
            state = self._read_state(connection)
            # SQLite INTEGER is signed 64-bit; retain a saturated failure count.
            failures = min(state["consecutive_failures"] + 1, (1 << 63) - 1)
            tripped = failures >= bounded_threshold
            if tripped:
                changed = {
                    "enabled": False,
                    "reason": f"auto_rollback:{reason}",
                    "changed_at": datetime.now(timezone.utc).isoformat(),
                }
                connection.execute(
                    "UPDATE decision_runtime_state SET enabled_override = 0, last_change_json = ?, "
                    "consecutive_failures = ? WHERE singleton = 1",
                    (json.dumps(changed), failures),
                )
            else:
                connection.execute(
                    "UPDATE decision_runtime_state SET consecutive_failures = ? WHERE singleton = 1",
                    (failures,),
                )
            connection.commit()
        return tripped

    def record_provider_success(self) -> None:
        with closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._read_state(connection)
            connection.execute(
                "UPDATE decision_runtime_state SET consecutive_failures = 0 WHERE singleton = 1"
            )
            connection.commit()


def decision_enabled() -> bool:
    settings = get_settings()
    if str(getattr(settings, "app_env", "")).strip().lower() in {"prod", "production"}:
        return False
    return DecisionRuntimeStore(RUNTIME_STATE_PATH).decision_enabled(settings.jev_decision_enabled)


def set_decision_enabled(enabled: bool, reason: str) -> dict[str, Any]:
    return DecisionRuntimeStore(RUNTIME_STATE_PATH).set_decision_enabled(enabled, reason)


def record_provider_failure(reason: str) -> bool:
    threshold = max(get_settings().jev_auto_rollback_error_threshold, 1)
    return DecisionRuntimeStore(RUNTIME_STATE_PATH).record_provider_failure(reason, threshold)


def record_provider_success() -> None:
    DecisionRuntimeStore(RUNTIME_STATE_PATH).record_provider_success()


def status() -> dict[str, Any]:
    settings = get_settings()
    runtime_available = True
    try:
        state = DecisionRuntimeStore(RUNTIME_STATE_PATH).get_state()
    except RUNTIME_STORAGE_ERRORS:
        runtime_available = False
        report_runtime_fault("runtime_status_read_failed")
        state = {"override": None, "last_change": None, "consecutive_failures": None}
    effective_enabled = (
        False
        if not runtime_available or str(getattr(settings, "app_env", "")).strip().lower() in {"prod", "production"}
        else settings.jev_decision_enabled if state["override"] is None else state["override"]
    )
    return {
        "runtime_available": runtime_available,
        "runtime_faults": [] if runtime_available else ["runtime_status_read_failed"],
        "jev_shadow_enabled": settings.jev_shadow_enabled,
        "jev_decision_enabled": effective_enabled,
        "jev_decision_traffic_percent": settings.jev_decision_traffic_percent,
        "jev_authority_active": bool(
            effective_enabled and 0 < settings.jev_decision_traffic_percent <= 100
        ),
        "jev_decision_configured": settings.jev_decision_enabled,
        "jev_fallback_enabled": settings.jev_fallback_enabled,
        "override": state["override"],
        "last_change": state["last_change"],
        "consecutive_failures": state["consecutive_failures"],
    }
