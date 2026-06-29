from __future__ import annotations

import json
import re
from typing import Any

from app.agent.category_normalizer import normalize_categories, normalize_category as normalize_single_category
from app.services.llm_service import safe_llm_invoke


CATEGORIES = [
    "Laptop",
    "Monitor",
    "Keyboard",
    "Mouse",
    "Headset",
    "Webcam",
    "Office Chair",
    "Docking Station",
    "Printer",
    "Tablet",
    "Router",
    "External SSD",
    "Projector",
    "Conference Speaker",
    "Standing Desk",
]

KNOWN_BRANDS = [
    "Anker",
    "CalDigit",
    "Dell",
    "HP",
    "Jabra",
    "Lenovo",
    "Logitech",
    "Microsoft",
    "Poly",
    "Razer",
    "Samsung",
    "Sony",
    "Yealink",
]

CATEGORY_ALIASES = {
    "laptop": "Laptop",
    "notebook": "Laptop",
    "monitor": "Monitor",
    "screen": "Monitor",
    "keyboard": "Keyboard",
    "键盘": "Keyboard",
    "mouse": "Mouse",
    "mice": "Mouse",
    "鼠标": "Mouse",
    "headset": "Headset",
    "headphone": "Headset",
    "耳机": "Headset",
    "webcam": "Webcam",
    "camera": "Webcam",
    "摄像头": "Webcam",
    "chair": "Office Chair",
    "office chair": "Office Chair",
    "dock": "Docking Station",
    "docking station": "Docking Station",
    "扩展坞": "Docking Station",
    "printer": "Printer",
    "tablet": "Tablet",
    "router": "Router",
    "ssd": "External SSD",
    "external ssd": "External SSD",
    "projector": "Projector",
    "conference speaker": "Conference Speaker",
    "speaker": "Conference Speaker",
    "standing desk": "Standing Desk",
    "desk": "Standing Desk",
}


def _extract_people_count(text: str) -> int:
    patterns = [
        r"(\d+)\s+(?:interns?|people|employees?|users?|staff|members?|teammates?)",
        r"(\d+)\s*名?\s*(?:实习生|员工|用户|人员|人)",
        r"(?:team|group|department)\s+of\s+(\d+)",
        r"for\s+(\d+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return int(match.group(1))
    return 1


def _extract_budget(text: str) -> float | None:
    patterns = [
        r"(?:budget|under|below|less than|within|maximum|max)\D{0,20}\$?\s*([0-9][0-9,]*(?:\.[0-9]+)?)",
        r"预算\D{0,20}([0-9][0-9,]*(?:\.[0-9]+)?)\s*(?:美元|美金|usd|USD)?\s*(?:以内|以下|内)?",
        r"\$([0-9][0-9,]*(?:\.[0-9]+)?)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return float(match.group(1).replace(",", ""))
    return None


def _explicitly_removes_budget(text: str) -> bool:
    return bool(
        re.search(
            r"\b(?:no|without|unlimited|unrestricted)\s+budget\b|"
            r"\bbudget\s+(?:unlimited|unrestricted|not\s+limited|does\s+not\s+matter)\b|"
            r"(?:无|沒|没|没有|不设|不限|不限制|无需|不用)\s*预算|"
            r"预算\s*(?:不限|不限制|不设限|无上限|没有限制)",
            text,
            flags=re.IGNORECASE,
        )
    )


def _extract_categories(text: str) -> list[str]:
    found: list[str] = []
    for alias, category in sorted(CATEGORY_ALIASES.items(), key=lambda item: len(item[0]), reverse=True):
        if alias.isascii():
            matched = re.search(rf"\b{re.escape(alias)}s?\b", text, flags=re.IGNORECASE)
        else:
            matched = alias in text
        if matched:
            if category not in found:
                found.append(category)
    order = {category: index for index, category in enumerate(CATEGORIES)}
    return sorted(found, key=lambda category: order.get(category, 999))


def _extract_brand(text: str) -> str | None:
    for brand in KNOWN_BRANDS:
        if re.search(rf"(?<![a-zA-Z0-9_]){re.escape(brand)}(?![a-zA-Z0-9_])", text, flags=re.IGNORECASE):
            return brand
    match = re.search(r"\b(?:with|from|by)\s+([A-Z][A-Za-z0-9&-]+)\s+(?:brand|model)\b", text)
    if match:
        return match.group(1)
    return None


def _infer_preserved_categories(text: str, categories: list[str]) -> set[str]:
    lowered = text.lower()
    preserved: set[str] = set()
    preserve_words = r"keep|preserve|unchanged|same|保持不变"
    for category in categories:
        category_pattern = re.escape(category.lower())
        if re.search(rf"\b(?:{preserve_words})\b[^.?!,;]{{0,100}}\b{category_pattern}\b", lowered):
            preserved.add(category)
            continue
        if re.search(rf"\b{category_pattern}\b[^.?!,;]{{0,100}}\b(?:unchanged|same)\b", lowered):
            preserved.add(category)
    return preserved


def _extract_min_rating(text: str) -> float | None:
    match = re.search(r"(?:rating|rated|score)\s*(?:above|over|at least|>=?)\s*([0-9](?:\.[0-9])?)", text, re.I)
    if match:
        return float(match.group(1))
    if re.search(r"high rating|highly rated|good rating|top rated|高评分|评分高|质量好", text, re.I):
        return 4.2
    return None


def _extract_delivery_days(text: str) -> int | None:
    match = re.search(r"(?:within|under|less than|<=?)\s*(\d+)\s*days?", text, re.I)
    if match:
        return int(match.group(1))
    if re.search(r"fast delivery|quick delivery|urgent|deliver fast|short delivery|快速配送|尽快到货|配送快", text, re.I):
        return 5
    return None


def _constraints_list(budget: float | None, min_rating: float | None, max_delivery_days: int | None) -> list[str]:
    constraints: list[str] = []
    if budget is not None:
        constraints.append("within budget")
    if min_rating is not None:
        constraints.append(f"rating at least {min_rating}")
    if max_delivery_days is not None:
        constraints.append(f"delivery within {max_delivery_days} days")
    return constraints


def _normalize_category(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    return normalize_single_category(text).normalized_category


def _normalize_categories(values: Any) -> list[str]:
    categories, _trace = normalize_categories(values)
    return _sort_categories(categories)


def _normalize_categories_with_trace(values: Any) -> tuple[list[str], list[dict[str, Any]]]:
    categories, trace = normalize_categories(values)
    return _sort_categories(categories), trace


def _sort_categories(categories: list[str]) -> list[str]:
    order = {category: index for index, category in enumerate(CATEGORIES)}
    return sorted(categories, key=lambda category: order.get(category, 999))


def _normalize_quantity_map(value: Any, categories: list[str], people_count: int | None) -> dict[str, int]:
    default_quantity = int(people_count or 1)
    if not isinstance(value, dict):
        return {category: default_quantity for category in categories}

    normalized: dict[str, int] = {}
    for raw_category, raw_quantity in value.items():
        category = _normalize_category(raw_category)
        if not category:
            continue
        try:
            quantity = int(raw_quantity)
        except (TypeError, ValueError):
            quantity = default_quantity
        normalized[category] = max(quantity, 1)

    for category in categories:
        normalized.setdefault(category, default_quantity)
    return normalized


def _as_int_or_none(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _as_float_or_none(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    return bool(value)


def _build_intent_prompt(user_message: str, previous_intent: dict[str, Any] | None = None) -> str:
    previous_context = ""
    if previous_intent:
        safe_previous = {k: v for k, v in previous_intent.items() if k not in ("raw_message",)}
        previous_context = f"""

Previous structured intent:
{json.dumps(safe_previous, ensure_ascii=False, indent=2, default=str)}

Guidelines:
- Only inherit previous budget when the user explicitly says to keep it.
- If the user does NOT mention a budget in the new message, set "budget" to null.
- When user mentions a new category (e.g. "keyboard"), extract only that category.
- Do NOT inherit previous categories unless the user explicitly asks to continue.
"""
    return f"""
You are an intent extraction engine for an enterprise procurement agent.
Extract structured procurement intent from the user message.

Return ONLY valid JSON. Do not include markdown. Do not include explanation.

User message:
{user_message}
{previous_context}

Required JSON schema:
{{
  "people_count": number or null,
  "budget": number or null,
  "categories": array of strings,
  "quantity_per_category": object,
  "preferences": array of strings,
  "constraints": array of strings,
  "min_rating": number or null,
  "max_delivery_days": number or null,
  "need_cheaper_plan": boolean,
  "replacement_request": string or null,
  "replacement_categories": array of strings,
  "replacement_brand": string or null
}}
""".strip()


def _parse_json_object(content: Any) -> dict[str, Any]:
    if not isinstance(content, str):
        raise ValueError("LLM response content is not a string")
    text = content.strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError("LLM response did not contain a JSON object")
    parsed = json.loads(text[start : end + 1])
    if not isinstance(parsed, dict):
        raise ValueError("LLM JSON response was not an object")
    return parsed



def _wants_inherit_budget(text: str) -> bool:
    lowered = text.lower()
    patterns = [r"budget\s+(unchanged|same|keep|stay|as before|as previous)", r"(unchanged|same|keep|stay|continue).{0,30}budget"]
    if any(re.search(p, lowered) for p in patterns): return True
    if re.search(r"continue.{0,10}(?:budget|plan|config)", lowered): return True
    if re.search(r"预算不变", text): return True
    if re.search(r"沿用.*预算", text): return True
    if re.search(r"原预算", text): return True
    return False

def _resolve_budget(msg, extracted, prev):
    p = prev or {}
    if _explicitly_removes_budget(msg): return (None, "explicit")
    if extracted is not None: return (extracted, "explicit")
    if _wants_inherit_budget(msg) and p.get("budget") is not None: return (p["budget"], "inherited")
    return (None, "none")

def _resolve_people_count(msg, extracted, prev):
    p = prev or {}
    if extracted != 1: return extracted
    l = msg.lower()
    if any(w in l for w in ["continue","previous","same team","same group","same people","cheaper","replace","make this","更便宜","换","替换","继续","刚才"]): return p.get("people_count", 1)
    return 1

def _resolve_min_rating(msg, extracted, prev):
    if extracted is not None: return extracted
    p = prev or {}; l = msg.lower()
    if any(w in l for w in ["continue","previous","unchanged","same constraint","same rating","cheaper","replace"]): return p.get("min_rating")
    return None

def _resolve_max_delivery_days(msg, extracted, prev):
    if extracted is not None: return extracted
    p = prev or {}; l = msg.lower()
    if any(w in l for w in ["continue","previous","unchanged","same constraint","same delivery","cheaper","replace"]): return p.get("max_delivery_days")
    return None


def _detect_response_language(message: str) -> str:
    """Detect response language from user message.
    
    If the message contains any Chinese characters, return "zh".
    Otherwise return "en".
    """
    if re.search(r"""[\u4e00-\u9fff\u3400-\u4dbf]""", message):
        return "zh"
    return "en"


def _build_constraint_sources(msg, bs, budget, mr, emr, mdd, ed):
    s = {}; s["budget"] = bs
    s["min_rating"] = "explicit" if emr is not None else ("inherited" if mr is not None else "none")
    s["max_delivery_days"] = "explicit" if ed is not None else ("inherited" if mdd is not None else "none")
    return s
def _parse_purchase_request_rules(message: str, previous_intent: dict[str, Any] | None = None) -> dict[str, Any]:
    """Parse procurement intent with deterministic mock-safe rules."""

    text = message.strip()
    lowered = text.lower()
    previous_intent = previous_intent or {}

    extracted_people_count = _extract_people_count(text)
    people_count = _resolve_people_count(text, extracted_people_count, previous_intent)
    extracted_budget_val = _extract_budget(text)
    budget, budget_source = _resolve_budget(text, extracted_budget_val, previous_intent)
    extracted_categories = _extract_categories(text)
    categories = extracted_categories
    if not extracted_categories:
        l2 = text.lower()
        if any(w in l2 for w in ["continue", "previous", "same", "unchanged"]):
            categories = list(previous_intent.get("categories", []))
        else:
            categories = []
    extracted_min_rating = _extract_min_rating(text)
    min_rating = _resolve_min_rating(text, extracted_min_rating, previous_intent)
    extracted_delivery = _extract_delivery_days(text)
    max_delivery_days = _resolve_max_delivery_days(text, extracted_delivery, previous_intent)
    preferences: list[str] = []
    revision_intent = "new_plan"

    if any(word in lowered for word in ["cheaper", "lower cost", "less expensive", "reduce cost", "更便宜", "低价", "降低成本"]):
        revision_intent = "cheaper"
        preferences.append("lower cost")
    if any(word in lowered for word in ["faster", "fast delivery", "quick delivery", "within"]) or any(
        word in text for word in ["快速配送", "尽快到货", "配送快"]
    ):
        if "fast delivery" not in preferences:
            preferences.append("fast delivery")
    if min_rating is not None or "rating" in lowered or "rated" in lowered or any(
        word in text for word in ["高评分", "评分高", "质量好"]
    ):
        if "high rating" not in preferences:
            preferences.append("high rating")
    if any(word in lowered for word in ["replace", "swap", "换成", "替换"]):
        revision_intent = "replace_product"

    if revision_intent in {"cheaper", "replace_product"} and previous_intent.get("categories"):
        categories = list(dict.fromkeys([*previous_intent.get("categories", []), *categories]))

    previous_quantities = previous_intent.get("quantity_by_category") or previous_intent.get("quantity_per_category") or {}
    quantity_by_category = {
        category: int(previous_quantities.get(category, people_count))
        for category in categories
    }
    need_cheaper_plan = revision_intent == "cheaper"
    replacement_request = message if revision_intent == "replace_product" else None
    preserved_categories = _infer_preserved_categories(text, extracted_categories)
    replacement_categories = [
        category
        for category in extracted_categories
        if revision_intent == "replace_product" and category not in preserved_categories
    ]
    preferred_brand = _extract_brand(text)
    replacement_brand = preferred_brand if revision_intent == "replace_product" else None

    llm_brand = _extract_brand(message)
    response_language = _detect_response_language(message)
    return {
        "response_language": response_language,
        "people_count": people_count,
        "budget": budget,
        "budget_source": budget_source,
        "categories": categories,
        "quantity_per_category": quantity_by_category,
        "quantity_by_category": quantity_by_category,
        "preferences": preferences,
        "constraint_sources": _build_constraint_sources(
            text, budget_source, budget,
            min_rating, extracted_min_rating,
            max_delivery_days, extracted_delivery,
        ),
        "constraints": _constraints_list(budget, min_rating, max_delivery_days),
        "preferred_brand": preferred_brand,
        "min_rating": min_rating,
        "max_delivery_days": max_delivery_days,
        "need_cheaper_plan": need_cheaper_plan,
        "replacement_request": replacement_request,
        "replacement_categories": replacement_categories,
        "replacement_brand": replacement_brand,
        "revision_intent": revision_intent,
        "raw_message": message,
    }


def _intent_from_llm_json(
    payload: dict[str, Any],
    message: str,
    previous_intent: dict[str, Any] | None,
) -> dict[str, Any]:
    fallback = _parse_purchase_request_rules(message, previous_intent)
    people_count = _as_int_or_none(payload.get("people_count")) or fallback.get("people_count")
    budget = _as_float_or_none(payload.get("budget"))
    if _explicitly_removes_budget(message):
        budget = None
        budget_source = "explicit"
    elif budget is not None:
        budget_source = "explicit"
    else:
        budget = fallback.get("budget")
        budget_source = fallback.get("budget_source", "none")
    categories, category_trace = _normalize_categories_with_trace(payload.get("categories"))
    if not categories:
        categories = fallback.get("categories", [])
    quantity_by_category = _normalize_quantity_map(
        payload.get("quantity_per_category") or payload.get("quantity_by_category"),
        categories,
        people_count,
    )
    min_rating = _as_float_or_none(payload.get("min_rating"))
    if min_rating is None:
        min_rating = fallback.get("min_rating")
    max_delivery_days = _as_int_or_none(payload.get("max_delivery_days"))
    if max_delivery_days is None:
        max_delivery_days = fallback.get("max_delivery_days")
    preferences = payload.get("preferences") if isinstance(payload.get("preferences"), list) else fallback["preferences"]
    constraints = payload.get("constraints") if isinstance(payload.get("constraints"), list) else fallback.get("constraints", [])
    need_cheaper_plan = _as_bool(payload.get("need_cheaper_plan"))
    replacement_request = payload.get("replacement_request")
    if replacement_request is not None:
        replacement_request = str(replacement_request)
    replacement_categories = _normalize_categories(payload.get("replacement_categories")) or fallback.get(
        "replacement_categories",
        [],
    )
    replacement_brand = payload.get("replacement_brand") or fallback.get("replacement_brand")
    if replacement_brand is not None:
        replacement_brand = str(replacement_brand).strip() or None

    revision_intent = fallback.get("revision_intent", "new_plan")
    if need_cheaper_plan:
        revision_intent = "cheaper"
    if replacement_request:
        revision_intent = "replace_product"

    if revision_intent in {"cheaper", "replace_product"} and previous_intent and previous_intent.get("categories"):
        categories, category_trace = _normalize_categories_with_trace([*previous_intent.get("categories", []), *categories])

    llm_brand = _extract_brand(message)
    response_language = _detect_response_language(message)
    return {
        "response_language": response_language,
        "people_count": people_count,
        "budget": budget,
        "budget_source": budget_source,
        "categories": categories,
        "quantity_per_category": quantity_by_category,
        "quantity_by_category": quantity_by_category,
        "preferences": [str(item) for item in preferences],
        "constraint_sources": fallback.get("constraint_sources", {}),
        "constraints": [str(item) for item in constraints],
        "min_rating": min_rating,
        "max_delivery_days": max_delivery_days,
        "need_cheaper_plan": need_cheaper_plan,
        "replacement_request": replacement_request,
        "replacement_categories": replacement_categories if revision_intent == "replace_product" else [],
        "replacement_brand": replacement_brand if revision_intent == "replace_product" else None,
        "preferred_brand": replacement_brand or llm_brand,
        "revision_intent": revision_intent,
        "raw_message": message,
        "category_normalization": category_trace,
    }


def _with_llm_metadata(intent: dict[str, Any], llm_result: dict[str, Any], used_llm_parser: bool, error: str | None) -> dict[str, Any]:
    return {
        **intent,
        "used_llm_parser": used_llm_parser,
        "model_provider": llm_result.get("model_provider"),
        "model_name": llm_result.get("model_name"),
        "used_mock_llm": bool(llm_result.get("used_mock_llm")),
        "llm_error": error,
        "llm_latency_ms": llm_result.get("latency_ms"),
        "llm_fallback_reason": llm_result.get("fallback_reason"),
    }


def parse_purchase_request(message: str, previous_intent: dict[str, Any] | None = None) -> dict[str, Any]:
    prompt = _build_intent_prompt(message, previous_intent)
    llm_result = safe_llm_invoke(prompt, purpose="intent_parser")

    if llm_result.get("used_mock_llm"):
        intent = _parse_purchase_request_rules(message, previous_intent)
        return _with_llm_metadata(intent, llm_result, used_llm_parser=False, error=llm_result.get("error"))

    try:
        payload = _parse_json_object(llm_result.get("content"))
        intent = _intent_from_llm_json(payload, message, previous_intent)
        return _with_llm_metadata(intent, llm_result, used_llm_parser=True, error=llm_result.get("error"))
    except Exception as exc:
        intent = _parse_purchase_request_rules(message, previous_intent)
        error = f"LLM JSON parse failed: {exc}"
        return _with_llm_metadata(intent, llm_result, used_llm_parser=False, error=error)
