from __future__ import annotations

import time
from typing import Any

from app.core.config import get_settings


settings = get_settings()


def get_llm_model():
    if settings.LLM_PROVIDER.lower() == "tongyi":
        if not settings.DASHSCOPE_API_KEY:
            return None

        from dashscope import Generation

        return Generation

    return None


def mock_llm_response(prompt: str, purpose: str = "general") -> str:
    if purpose == "intent_parser":
        return """
{
  "people_count": 20,
  "budget": 3000,
  "categories": ["keyboard", "mouse", "headset"],
  "quantity_per_category": {
    "keyboard": 20,
    "mouse": 20,
    "headset": 20
  },
  "preferences": ["high rating", "fast delivery"],
  "constraints": ["within budget", "sufficient inventory"],
  "min_rating": 4.2,
  "max_delivery_days": 5,
  "need_cheaper_plan": false,
  "replacement_request": null,
  "replacement_categories": [],
  "replacement_brand": null
}
""".strip()
    if purpose == "plan_explanation":
        return f"This is a mock procurement explanation because {settings.QWEN_MODEL} is not configured or the API call failed."
    if purpose == "llm_test":
        return f"This is a mock response because {settings.QWEN_MODEL} is not configured or the API call failed."
    return f"This is a mock response because {settings.QWEN_MODEL} is not configured or the API call failed."


def _mock_result(prompt: str, purpose: str, error: str) -> dict[str, Any]:
    return {
        "content": mock_llm_response(prompt, purpose),
        "model_provider": "mock",
        "model_name": settings.QWEN_MODEL,
        "used_mock_llm": True,
        "error": error,
        "fallback_reason": error,
        "latency_ms": 0,
    }


def _extract_dashscope_content(response: Any) -> str:
    output = getattr(response, "output", None)
    if isinstance(output, dict):
        text = output.get("text")
        if isinstance(text, str) and text:
            return text
        choices = output.get("choices")
        if isinstance(choices, list) and choices:
            message = choices[0].get("message") if isinstance(choices[0], dict) else None
            content = message.get("content") if isinstance(message, dict) else None
            if isinstance(content, str) and content:
                return content
    raise ValueError(f"DashScope response did not contain text content: {getattr(response, 'message', '')}")


def safe_llm_invoke(prompt: str, purpose: str = "general") -> dict[str, Any]:
    start = time.perf_counter()
    try:
        llm = get_llm_model()
    except Exception as exc:
        result = _mock_result(prompt, purpose, str(exc))
        result["latency_ms"] = round((time.perf_counter() - start) * 1000, 2)
        return result

    if llm is None:
        reason = "DASHSCOPE_API_KEY is missing"
        if not settings.DASHSCOPE_API_KEY and settings.USE_MOCK_LLM:
            reason = "USE_MOCK_LLM is true and DASHSCOPE_API_KEY is missing"
        return _mock_result(
            prompt,
            purpose,
            reason,
        )

    try:
        response = llm.call(
            model=settings.QWEN_MODEL,
            prompt=prompt,
            api_key=settings.DASHSCOPE_API_KEY,
            top_p=settings.QWEN_TOP_P,
            max_tokens=settings.QWEN_MAX_TOKENS,
            timeout=settings.QWEN_TIMEOUT_SECONDS,
            enable_thinking=settings.QWEN_ENABLE_THINKING,
        )
        content = _extract_dashscope_content(response)
        return {
            "content": content,
            "model_provider": "tongyi",
            "model_name": settings.QWEN_MODEL,
            "used_mock_llm": False,
            "error": None,
            "fallback_reason": None,
            "latency_ms": round((time.perf_counter() - start) * 1000, 2),
        }
    except Exception as exc:
        result = _mock_result(prompt, purpose, str(exc))
        result["latency_ms"] = round((time.perf_counter() - start) * 1000, 2)
        return result
