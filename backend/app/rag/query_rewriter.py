from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

from app.core.config import get_settings
from app.services.llm_service import safe_llm_invoke


CHINESE_REFERENCES = (
    "上次",
    "刚才",
    "之前",
    "前面",
    "这个",
    "那个",
    "这些",
    "那些",
    "它",
    "它们",
    "他",
    "他们",
    "她",
    "她们",
    "其",
    "该",
    "方案里",
)

ENGLISH_REFERENCE_PATTERN = re.compile(
    r"\b(previous|last|earlier|before|it|its|that|this|these|those|them|they|one|ones|same)\b",
    re.IGNORECASE,
)


class _SettingsProxy:
    def __getattr__(self, name: str) -> Any:
        return getattr(get_settings(), name)


settings = _SettingsProxy()


def _contains_reference(message: str) -> bool:
    if not message:
        return False
    return any(token in message for token in CHINESE_REFERENCES) or bool(
        ENGLISH_REFERENCE_PATTERN.search(message)
    )


def should_rewrite(message: str, previous_intent: dict[str, Any] | None) -> bool:
    if not getattr(settings, "query_rewrite_enabled", True):
        return False
    if previous_intent:
        return True
    return _contains_reference(message)


def _format_previous_context(previous_intent: dict[str, Any] | None) -> str:
    previous_intent = previous_intent or {}
    categories = previous_intent.get("categories") or []
    categories_text = "、".join(str(category) for category in categories) if categories else "未知品类"
    people_count = previous_intent.get("people_count") or "未知"
    return f"用户之前要采购 {categories_text}，人数 {people_count} 人"


def _build_rewrite_prompt(message: str, previous_intent: dict[str, Any] | None) -> str:
    return f"""你是一个查询改写助手。用户正在进行多轮采购对话。请将用户的口语化表达改写成更适合检索的规范化查询。
规则：
- 消除指代词（"上次那个""这个""它"），替换为具体内容
- 补全省略的信息
- 保留关键约束条件（品牌、价格、评分等）
- 只输出改写后的查询文本，不要解释

对话上下文：{_format_previous_context(previous_intent)}
用户当前输入：{message}
改写后查询：""".strip()


def rewrite_query(
    message: str,
    previous_intent: dict[str, Any] | None,
    llm_invoke: Callable[..., dict[str, Any]] = safe_llm_invoke,
) -> str:
    if not should_rewrite(message, previous_intent):
        return message

    try:
        result = llm_invoke(
            _build_rewrite_prompt(message, previous_intent),
            purpose="query_rewrite",
            language="zh",
        )
    except Exception:
        return message

    if bool((result or {}).get("used_mock_llm")):
        return message

    content = str((result or {}).get("content") or "").strip()
    if not content:
        return message
    return content
