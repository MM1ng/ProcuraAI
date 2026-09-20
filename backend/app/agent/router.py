import re
from typing import Literal

RouteType = Literal["search", "recommendation", "confirm_order", "payment", "compare", "unknown"]


def transaction_intent(message: str) -> Literal["recommend", "confirm_order", "payment"]:
    """Recognize explicit commands, never transaction words embedded in prose.

    Fail closed for questions, negations, quoted examples and ambiguous wording.
    Procurement requirements such as buy/purchase are not authorization.
    """
    text = message.strip()
    order_patterns = (
        r"(?:please\s+)?(?:confirm|approve)\s+(?:(?:this|the|selected)\s+)?"
        r"plan(?:\s+[abc])?\s+and\s+(?:place|create)\s+(?:(?:an?|the)\s+)?order",
        r"(?:please\s+)?(?:place|create)\s+(?:(?:an?|the)\s+)?order(?:\s+now)?",
        r"(?:请)?确认\s*(?:(?:这个|该|所选)?方案\s*[ABCabc]?\s*(?:并|并且|然后))?\s*下单",
    )
    payment_patterns = (
        r"(?:please\s+)?(?:pay\s+now|proceed\s+to\s+(?:payment|checkout)|confirm\s+payment)",
        r"(?:请)?(?:确认|立即)\s*(?:支付|付款|结账)",
    )
    for intent, patterns in (("confirm_order", order_patterns), ("payment", payment_patterns)):
        if any(re.fullmatch(pattern + r"[.!。！]?", text, re.IGNORECASE) for pattern in patterns):
            return intent
    return "recommend"

_KNOWN_CATEGORIES = {
    "laptop", "monitor", "keyboard", "mouse", "headset", "webcam",
    "printer", "office chair", "standing desk", "tablet", "projector",
    "router", "docking station", "external ssd", "conference speaker",
    "phone",
}

def route_intent(message: str) -> dict:
    text = message.strip()
    lowered = text.lower()

    transaction = transaction_intent(text)
    if transaction != "recommend":
        return {"route": transaction, "confidence": 0.9, "matched_by": "explicit_transaction_command"}

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
        r"\b(?:recommend|suggest|need|want|looking for|setup|buy|purchase|procure|procurement)\b",
        r"配置|配一套|采购|购买|买",
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
