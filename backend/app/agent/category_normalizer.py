from __future__ import annotations

import csv
import difflib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.core.config import DATA_DIR
from app.services.llm_service import safe_llm_invoke


BASIC_CATEGORY_ALIASES = {
    "显示器": "Monitor",
    "显示屏": "Monitor",
    "屏幕": "Monitor",
    "电脑显示器": "Monitor",
    "笔记本": "Laptop",
    "笔记本电脑": "Laptop",
    "开发电脑": "Laptop",
    "键盘": "Keyboard",
    "鼠标": "Mouse",
    "打印机": "Printer",
    "交换机": "Network Switch",
    "会议大屏": "Meeting Display",
    "大屏": "Meeting Display",
    "会议室大屏": "Meeting Display",
}

PRODUCTS_CSV = DATA_DIR / "products.csv"


@dataclass(frozen=True)
class CategoryNormalizationResult:
    original_category: str
    normalized_category: str
    normalization_method: str
    allowed_categories: list[str]
    warning: str | None = None


def get_allowed_categories(path: Path = PRODUCTS_CSV) -> list[str]:
    if not path.exists():
        return []
    categories: set[str] = set()
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            category = str(row.get("category", "")).strip()
            if category:
                categories.add(category)
    return sorted(categories)


def _standard_allowed_category(value: str, allowed_categories: list[str]) -> str | None:
    lowered = value.lower()
    for category in allowed_categories:
        if category.lower() == lowered:
            return category
    return None


def _alias_match(value: str, allowed_categories: list[str]) -> str | None:
    target = BASIC_CATEGORY_ALIASES.get(value.strip())
    if not target:
        return None
    return _standard_allowed_category(target, allowed_categories) or target


def _similarity_match(value: str, allowed_categories: list[str]) -> str | None:
    if not value.isascii():
        return None
    matches = difflib.get_close_matches(value.lower(), [item.lower() for item in allowed_categories], n=1, cutoff=0.84)
    if not matches:
        return None
    return _standard_allowed_category(matches[0], allowed_categories)


def _llm_category_choice(value: str, allowed_categories: list[str]) -> str | None:
    if not allowed_categories:
        return None
    prompt = f"""
Choose the closest procurement category for the user category.
Return ONLY JSON in this shape:
{{"category": string or null, "confidence": number}}

Allowed categories:
{json.dumps(allowed_categories, ensure_ascii=False)}

User category:
{value}

Rules:
- The category must be one of the allowed categories.
- If confidence is below 0.75, return null.
""".strip()
    result = safe_llm_invoke(prompt, purpose="category_normalization")
    if result.get("used_mock_llm"):
        return None
    try:
        payload = json.loads(str(result.get("content") or "{}"))
    except json.JSONDecodeError:
        return None
    category = payload.get("category")
    confidence = float(payload.get("confidence", 0) or 0)
    if confidence < 0.75 or not isinstance(category, str):
        return None
    return _standard_allowed_category(category, allowed_categories)


def normalize_category(value: Any, allowed_categories: list[str] | None = None) -> CategoryNormalizationResult:
    original = str(value or "").strip()
    allowed = allowed_categories if allowed_categories is not None else get_allowed_categories()
    if not original:
        return CategoryNormalizationResult(original, original, "empty", allowed, "empty_category")

    exact = next((category for category in allowed if category == original), None)
    if exact:
        return CategoryNormalizationResult(original, exact, "exact", allowed)

    case_match = _standard_allowed_category(original, allowed)
    if case_match:
        return CategoryNormalizationResult(original, case_match, "case_insensitive", allowed)

    alias = _alias_match(original, allowed)
    if alias:
        return CategoryNormalizationResult(original, alias, "alias", allowed)

    similar = _similarity_match(original, allowed)
    if similar:
        return CategoryNormalizationResult(original, similar, "similarity", allowed)

    llm_choice = _llm_category_choice(original, allowed)
    if llm_choice:
        return CategoryNormalizationResult(original, llm_choice, "llm", allowed)

    return CategoryNormalizationResult(original, original, "unmatched", allowed, "low_confidence_category_match")


def normalize_categories(values: Any, allowed_categories: list[str] | None = None) -> tuple[list[str], list[dict[str, Any]]]:
    if not isinstance(values, list):
        return [], []
    categories: list[str] = []
    traces: list[dict[str, Any]] = []
    allowed = allowed_categories if allowed_categories is not None else get_allowed_categories()
    for value in values:
        result = normalize_category(value, allowed)
        if result.normalized_category and result.normalized_category not in categories:
            categories.append(result.normalized_category)
        traces.append(
            {
                "original_category": result.original_category,
                "normalized_category": result.normalized_category,
                "normalization_method": result.normalization_method,
                "allowed_categories": result.allowed_categories,
                "warning": result.warning,
            }
        )
    order = {category: index for index, category in enumerate(allowed)}
    categories = sorted(categories, key=lambda category: order.get(category, 999))
    return categories, traces
