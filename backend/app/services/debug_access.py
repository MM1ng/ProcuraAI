"""Independent, deny-by-default access to the two diagnostic endpoints.

These secrets are server environment configuration, never caller credentials.
No identity, Jev control, logging or provider side effects occur here.
"""
import hmac
import os

from fastapi import HTTPException

NO_STORE = {"Cache-Control": "no-store"}


def _require_token(variable: str, supplied: str | None) -> None:
    expected = os.getenv(variable, "")
    if (not expected.strip() or not supplied
            or not hmac.compare_digest(expected.encode("utf-8"), supplied.encode("utf-8"))):
        raise HTTPException(status_code=403, detail="Diagnostic authorization required", headers=NO_STORE)


def require_traces_admin(token: str | None) -> None:
    _require_token("OBSERVABILITY_ADMIN_TOKEN", token)


def require_llm_debug(token: str | None) -> None:
    # Unknown/absent environments and non-explicit enables fail closed.
    environment = os.getenv("APP_ENV", "").strip().lower()
    enabled = os.getenv("LLM_TEST_ENABLED", "").strip().lower() == "true"
    if not enabled or environment not in {"development", "test"}:
        raise HTTPException(status_code=404, detail="Debug endpoint unavailable", headers=NO_STORE)
    _require_token("LLM_TEST_TOKEN", token)
