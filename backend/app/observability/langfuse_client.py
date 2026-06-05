from __future__ import annotations

from typing import Any

from app.core.config import get_settings


class LangfuseClient:
    """Tiny optional adapter so the app can run without Langfuse credentials."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self.enabled = bool(self.settings.langfuse_public_key and self.settings.langfuse_secret_key)

    def trace(self, **payload: Any) -> None:
        if not self.enabled:
            return
        try:
            from langfuse import Langfuse

            client = Langfuse(
                public_key=self.settings.langfuse_public_key,
                secret_key=self.settings.langfuse_secret_key,
                host=self.settings.langfuse_host,
            )
            trace = client.trace(name="enterprise-procurement-agent", metadata=payload)
            trace.update(output=payload.get("final_answer"))
            client.flush()
        except Exception:
            return
