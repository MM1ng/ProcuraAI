from __future__ import annotations

from pydantic import BaseModel
from fastapi import APIRouter, Header, Response

from app.services.llm_service import mock_llm_response, settings
from app.services.debug_access import require_llm_debug


router = APIRouter(prefix="/api/llm", tags=["llm"])


class LLMTestRequest(BaseModel):
    message: str


@router.get("/status")
def llm_status() -> dict[str, object]:
    return {
        "llm_provider": settings.LLM_PROVIDER,
        "model_name": settings.QWEN_MODEL,
        "has_api_key": bool(settings.DASHSCOPE_API_KEY),
        "use_mock_llm": settings.USE_MOCK_LLM,
        "mock_fallback_enabled": settings.USE_MOCK_LLM,
        "qwen_timeout_seconds": settings.QWEN_TIMEOUT_SECONDS,
        "qwen_enable_thinking": settings.QWEN_ENABLE_THINKING,
    }


@router.post("/test")
def llm_test(
    request: LLMTestRequest,
    response: Response,
    x_llm_test_token: str | None = Header(default=None),
) -> dict[str, object]:
    require_llm_debug(x_llm_test_token)
    response.headers["Cache-Control"] = "no-store"
    # Never use safe_llm_invoke: USE_MOCK_LLM is a fallback, not a provider ban.
    return {
        "content": mock_llm_response(request.message, purpose="llm_test"),
        "model_provider": "mock",
        "model_name": settings.QWEN_MODEL,
        "used_mock_llm": True,
        "error": None,
        "fallback_reason": "authorized_local_debug_mock",
        "latency_ms": 0,
        "retry_count": 0,
    }
