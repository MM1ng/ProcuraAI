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


def mock_llm_response(prompt: str, purpose: str = "general", language: str = "en") -> str:
    if purpose == "intent_parser":
        return """
{
  "people_count": 20,
  "budget": null,
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
        if language == "zh":
            return (
                f"\u5df2\u4e3a\u60a8\u751f\u6210\u91c7\u8d2d\u65b9\u6848\u3002\u7531\u4e8e{settings.QWEN_MODEL}\u672a\u914d\u7f6e\u6216API\u8c03\u7528\u5931\u8d25\uff0c\u6b64\u4e3a\u6a21\u62df\u54cd\u5e94\u3002"
                f"\u8bf7\u914d\u7f6eDASHSCOPE_API_KEY\u4ee5\u83b7\u53d6\u5b9e\u9645\u7684\u91c7\u8d2d\u65b9\u6848\u8bf4\u660e\u3002"
            )
        return f"This is a mock procurement explanation because {settings.QWEN_MODEL} is not configured or the API call failed."
    if purpose == "llm_test":
        if language == "zh":
            return f"\u8fd9\u662f\u4e00\u6761\u6a21\u62df\u54cd\u5e94\uff0c\u56e0\u4e3a{settings.QWEN_MODEL}\u672a\u914d\u7f6e\u6216API\u8c03\u7528\u5931\u8d25\u3002"
        return f"This is a mock response because {settings.QWEN_MODEL} is not configured or the API call failed."
    if language == "zh":
        return f"\u8fd9\u662f\u4e00\u6761\u6a21\u62df\u54cd\u5e94\uff0c\u56e0\u4e3a{settings.QWEN_MODEL}\u672a\u914d\u7f6e\u6216API\u8c03\u7528\u5931\u8d25\u3002"
    return f"This is a mock response because {settings.QWEN_MODEL} is not configured or the API call failed."


def _mock_result(prompt: str, purpose: str, error: str, language: str = "en") -> dict[str, Any]:
    return {
        "content": mock_llm_response(prompt, purpose, language),
        "model_provider": "mock",
        "model_name": settings.QWEN_MODEL,
        "used_mock_llm": True,
        "error": error,
        "fallback_reason": error,
        "latency_ms": 0,
    }


def _is_retryable_llm_error(exc: Exception) -> bool:
    if isinstance(exc, (ConnectionError, TimeoutError)):
        return True
    message = str(exc).lower()
    if any(code in message for code in ("400", "401", "403")):
        return False
    return any(code in message for code in ("429", "500", "502", "503", "504", "timeout", "connection"))


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


def safe_llm_invoke(prompt: str, purpose: str = "general", language: str = "en") -> dict[str, Any]:
    start = time.perf_counter()
    retry_count = 0
    try:
        llm = get_llm_model()
    except Exception as exc:
        result = _mock_result(prompt, purpose, str(exc), language)
        result["latency_ms"] = round((time.perf_counter() - start) * 1000, 2)
        result["retry_count"] = retry_count
        return result

    if llm is None:
        reason = "DASHSCOPE_API_KEY is missing"
        if not settings.DASHSCOPE_API_KEY and settings.USE_MOCK_LLM:
            reason = "USE_MOCK_LLM is true and DASHSCOPE_API_KEY is missing"
        result = _mock_result(
            prompt,
            purpose,
            reason,
            language,
        )
        result["retry_count"] = retry_count
        return result

    last_error: Exception | None = None
    for attempt in range(2):
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
                "retry_count": retry_count,
            }
        except Exception as exc:
            last_error = exc
            if attempt == 0 and _is_retryable_llm_error(exc):
                retry_count += 1
                time.sleep(2)
                continue
            break

    result = _mock_result(prompt, purpose, str(last_error), language)
    result["latency_ms"] = round((time.perf_counter() - start) * 1000, 2)
    result["retry_count"] = retry_count
    return result


async def safe_llm_stream(prompt: str, purpose: str = "general", language: str = "en"):
    """Stream incremental LLM text chunks, falling back to a mock response."""
    try:
        llm = get_llm_model()
    except Exception:
        llm = None

    if llm is None:
        yield {"delta": mock_llm_response(prompt, purpose, language), "finish_reason": None}
        yield {"delta": "", "finish_reason": "stop"}
        return

    try:
        stream = llm.call(
            model=settings.QWEN_MODEL,
            prompt=prompt,
            api_key=settings.DASHSCOPE_API_KEY,
            top_p=settings.QWEN_TOP_P,
            max_tokens=settings.QWEN_MAX_TOKENS,
            timeout=settings.QWEN_TIMEOUT_SECONDS,
            enable_thinking=settings.QWEN_ENABLE_THINKING,
            stream=True,
            incremental_output=True,
        )
        for chunk in stream:
            delta = _extract_dashscope_content(chunk)
            if delta:
                yield {"delta": delta, "finish_reason": None}
        yield {"delta": "", "finish_reason": "stop"}
    except Exception:
        yield {"delta": mock_llm_response(prompt, purpose, language), "finish_reason": None}
        yield {"delta": "", "finish_reason": "stop"}
