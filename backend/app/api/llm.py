from __future__ import annotations

from pydantic import BaseModel
from fastapi import APIRouter

from app.services.llm_service import safe_llm_invoke, settings


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
def llm_test(request: LLMTestRequest) -> dict[str, object]:
    return safe_llm_invoke(request.message, purpose="llm_test")
