import re
from typing import Literal

RouteType = Literal["search", "recommendation", "order", "compare", "unknown"]

_KNOWN_CATEGORIES = {
    "laptop", "monitor", "keyboard", "mouse", "headset", "webcam",
    "printer", "office chair", "standing desk", "tablet", "projector",
    "router", "docking station", "external ssd", "conference speaker",
    "phone",
}

def route_intent(message: str) -> dict:
    text = message.strip()
    lowered = text.lower()

    # --- Order ---
    order_patterns = [
        r"\b(?:place|create|make)\s*(?:an?\s*)?order\b",
        r"\b(?:checkout|buy|purchase|order\s*now|add\s*to\s*cart)\b",
        r"\b下单|购买|加入购物车|结算\b",
    ]
    for pat in order_patterns:
        if re.search(pat, lowered):
            return {"route": "order", "confidence": 0.9, "matched_by": "order_keywords"}

    # --- Compare ---
    compare_patterns = [
        r"\b(?:compare|vs\.?|versus|difference between|or\s+\w+\s+or)\b",
        r"\b哪个好|比较|对比|有什么区别\b",
    ]
    for pat in compare_patterns:
        if re.search(pat, lowered):
            return {"route": "compare", "confidence": 0.85, "matched_by": "compare_keywords"}

    # --- Recommendation ---
    recommend_patterns = [
        r"\b(?:recommend|suggest|need|want|looking for|setup|配置|配一套)\b",
        r"\b预算\s*\d+",
        r"\b推荐|预算|买[一\d]",
        r"\b推荐\s*\d+\s*台",
    ]
    for pat in recommend_patterns:
        if re.search(pat, lowered):
            return {"route": "recommendation", "confidence": 0.8, "matched_by": "recommend_keywords"}

    # --- Search ---
    search_patterns = [
        r"\b(?:find|search|show|list|display|look\s*for|search\s*for)\b",
        r"\b查找|搜索|列出|显示|找\b",
    ]
    for pat in search_patterns:
        if re.search(pat, lowered):
            return {"route": "search", "confidence": 0.8, "matched_by": "search_keywords"}

    # --- Guess by category mention ---
    for cat in _KNOWN_CATEGORIES:
        if cat in lowered or any(cat.split()[:1] == w for w in lowered.split() if len(w) > 2):
            pass
    # If message mentions product-like words but no explicit intent verb
    product_words = {"laptop", "monitor", "keyboard", "mouse", "printer", "chair", "desk", "tablet"}
    if any(w in lowered for w in product_words):
        return {"route": "recommendation", "confidence": 0.6, "matched_by": "product_mention"}

    return {"route": "unknown", "confidence": 0.0, "matched_by": None}
