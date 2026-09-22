from __future__ import annotations

from typing import Any

from app.observability.langfuse_client import LangfuseClient
from app.observability.local_tracer import log_observability_event


def emit_shadow_audit(record: dict[str, Any]) -> None:
    """Reuse the existing audit sinks without adding user text or secrets."""
    log_observability_event(record)
    LangfuseClient().trace(**record)
