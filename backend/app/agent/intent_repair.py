import re
from typing import Any

from app.agent.intent_schema import CATEGORY_ALIASES, BRAND_ALIASES, VALID_CATEGORIES

# Chinese number parsing
CN_NUMS = {"零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}

def _parse_cn_number(text: str) -> int | None:
    text = text.strip()
    if text.isdigit():
        return int(text)
    if text in CN_NUMS:
        return CN_NUMS[text]
    return None

def _find_quantity(raw: str) -> int | None:
    m = re.search(r"(\d+)\s*台", raw)
    if m:
        return int(m.group(1))
    m = re.search(r"(\d+)\s*个", raw)
    if m:
        return int(m.group(1))
    m = re.search(r"(\d+)\s*部", raw)
    if m:
        return int(m.group(1))
    m = re.search(r"[买一](一|二|两|三|四|五|六|七|八|九|十|1|2|3|4|5|6|7|8|9|10)\s*台", raw)
    if m:
        return _parse_cn_number(m.group(1))
    m = re.search(r"\b(one|two|three|four|five|six|seven|eight|nine|ten)\s+", raw.lower())
    word_map = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}
    if m:
        return word_map.get(m.group(1))
    return None

def _find_budget(raw: str) -> float | None:
    m = re.search(r"预算\s*(\d+[\d.]*)\s*(?:美元|元|\$)?", raw)
    if m:
        return float(m.group(1))
    m = re.search(r"budget\s*(?:of\s*)?\$?(\d+[\d.]*)", raw.lower())
    if m:
        return float(m.group(1))
    m = re.search(r"\$(\d+[\d.]*)", raw)
    if m:
        return float(m.group(1))
    m = re.search(r"under\s*\$?(\d+[\d.]*)", raw.lower())
    if m:
        return float(m.group(1))
    return None

def _resolve_category(text: str) -> str | None:
    lowered = text.lower().strip()
    # Direct match
    for cat in VALID_CATEGORIES:
        if cat.lower() == lowered:
            return cat
    # Alias match
    if text in CATEGORY_ALIASES:
        return CATEGORY_ALIASES[text]
    # Partial match
    for cn_alias, eng_cat in CATEGORY_ALIASES.items():
        if cn_alias in text:
            return eng_cat
    for cat in VALID_CATEGORIES:
        if cat.lower() in lowered or lowered in cat.lower():
            return cat
    return None

def _resolve_brand(text: str) -> str | None:
    if text in BRAND_ALIASES:
        return BRAND_ALIASES[text]
    lowered = text.lower().strip()
    for alias, eng in BRAND_ALIASES.items():
        if alias.lower() == lowered:
            return eng
    for alias, eng in BRAND_ALIASES.items():
        if alias.lower() in lowered:
            return eng
    return text if text else None

def _normalize_category_list(categories: list) -> list[str]:
    if not categories:
        return []
    resolved = []
    for cat in categories:
        r = _resolve_category(str(cat))
        if r:
            resolved.append(r)
    return resolved

def repair_intent(payload: dict, raw_message: str, fallback: dict | None = None) -> dict:
    result = dict(payload)
    changes = []
    raw = raw_message or payload.get("raw_query") or payload.get("raw_message") or ""

    # --- Repair categories ---
    cats = payload.get("categories") or []
    if isinstance(cats, list):
        repaired_cats = _normalize_category_list(cats)
        if repaired_cats != cats:
            result["categories"] = repaired_cats
            changes.append("categories_normalized")
    if not result.get("categories"):
        # Try extracting from raw message
        for cn_alias, eng_cat in CATEGORY_ALIASES.items():
            if cn_alias in raw:
                result["categories"] = [eng_cat]
                changes.append("categories_extracted_from_raw:" + eng_cat)
                break

    # --- Repair brand ---
    brand = payload.get("brand") or payload.get("brands")
    if isinstance(brand, list):
        brand = brand[0] if brand else None
    if brand:
        resolved = _resolve_brand(str(brand))
        if resolved and resolved != brand:
            result["brand"] = resolved
            changes.append("brand_resolved:" + resolved)
    # Try extracting from raw
    if not result.get("brand"):
        for cn_alias, eng_brand in BRAND_ALIASES.items():
            if cn_alias in raw or eng_brand.lower() in raw.lower():
                result["brand"] = eng_brand
                if cn_alias in raw:
                    changes.append("brand_extracted_from_raw:" + eng_brand)
                break

    # Also populate brands list
    if result.get("brand"):
        result["brands"] = [result["brand"]]

    # --- Repair quantity ---
    qty = payload.get("quantity") or 1
    if qty is None or qty == 1:
        found = _find_quantity(raw)
        if found is not None:
            result["quantity"] = found
            if found > 1 or "台" in raw or "个" in raw:
                changes.append("quantity_extracted:" + str(found))

    # --- Repair per_category_quantities ---
    per_cat = payload.get("per_category_quantities") or payload.get("quantity_per_category") or {}
    if not per_cat and result.get("categories"):
        q = result.get("quantity", 1)
        result["per_category_quantities"] = {cat: q for cat in result["categories"]}

    # --- Repair budget ---
    budget = payload.get("budget")
    if budget is None:
        found = _find_budget(raw)
        if found:
            result["budget"] = found
            changes.append("budget_extracted:" + str(found))

    # --- Ensure people_count ---
    if result.get("people_count") is None:
        result["people_count"] = result.get("quantity", 1)

    result["intent_repair_applied"] = len(changes) > 0
    result["intent_repair_changes"] = changes
    return result
