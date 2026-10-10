import re
from typing import Literal

RouteType = Literal["search", "recommendation", "confirm_order", "payment", "order_status", "compare", "unknown"]


TransactionIntent = Literal["recommend", "confirm_order", "payment", "cancel"]


def transaction_intent(message: str) -> TransactionIntent:
    """Recognize explicit commands, never transaction words embedded in prose.

    Fail closed for questions, negations, quoted examples and ambiguous wording.
    Procurement requirements such as buy/purchase are not authorization.
    """
    text = message.strip()
    # These forms are deliberately fail-closed. They may contain a transaction
    # word, but they do not authorize a side effect.
    unsafe_transaction_forms = (
        r"^(?:please\s+)?(?:do\s+not|don't|dont|never)\s+(?:pay|checkout|place|create|submit)\b.*[.!?。！？]?$",
        r"^(?:不要|暂时不要|先不要|别)\s*(?:支付|付款|下单|创建订单|取消订单).*[。！？!?]?$",
        r"^(?:how|what|can|could)\b.*\b(?:pay|payment|checkout)\b.*[?？]$",
        r"^(?:怎么|如何|有哪些|能否)\s*(?:支付|付款|结账|下单).*[?？]$",
        r"^(?:if|whether)\b.*\b(?:pay|payment|place|order)\b.*[?？]$",
        r"^(?:如果|要是).*(?:支付|付款|下单).*[？?]$",
        r"^.*(?:演示|说明|解释|意思).*(?:支付|付款|下单).*$",
        r"^.*[\"“”].*(?:支付|付款|下单|cancel order).*[\"“”].*$",
    )
    if any(re.fullmatch(pattern, text, re.IGNORECASE) for pattern in unsafe_transaction_forms):
        return "recommend"
    order_patterns = (
        r"(?:please\s+)?(?:confirm|approve)\s+(?:(?:this|the|selected)\s+)?"
        r"plan(?:\s+[abc])?\s+and\s+(?:place|create)\s+(?:(?:an?|the)\s+)?order",
        r"(?:please\s+)?(?:place|create)\s+(?:(?:an?|the)\s+)?order(?:\s+now)?",
        r"(?:请)?确认\s*(?:(?:这个|该|所选)?方案\s*[ABCabc]?\s*(?:并|并且|然后))?\s*下单",
        r"(?:请)?确认\s*(?:这个|该|所选)?方案\s*下单",
        r"(?:请)?(?:现在|立即)?(?:提交|创建|生成)\s*(?:(?:这|该|当前|所选)\s*)?(?:采购)?订单",
        r"(?:please\s+)?(?:submit|place|create)\s+(?:this|the|current|selected)?\s*(?:purchase\s+)?order(?:\s+now)?",
        r"(?:please\s+)?submit\s+(?:the\s+)?current\s+purchase\s+order(?:\s+now)?",
        r"(?:please\s+)?create\s+the\s+selected\s+order(?:\s+now)?",
    )
    payment_patterns = (
        r"(?:please\s+)?(?:pay\s+now|proceed\s+to\s+(?:payment|checkout)|confirm\s+payment)",
        r"(?:请)?(?:确认|立即)\s*(?:支付|付款|结账)",
        r"(?:请)?(?:我(?:要|想)?|帮我|现在去|现在|去|立即)?\s*(?:支付|付款|结账)(?:(?:这个|该)?订单)?",
        r"(?:请)?(?:为|给)\s*订单\s*(?:号|编号)?\s*[A-Za-z0-9_-]+\s*(?:支付|付款)",
        r"(?:请)?(?:进入|前往)\s*结账",
        r"(?:please\s+)?(?:pay|checkout)\s+(?:(?:this|the)\s+)?order(?:\s+[A-Za-z0-9_-]+)?(?:\s+now)?",
    )
    cancel_patterns = (
        r"(?:请)?(?:取消|撤销)\s*(?:这个|该|当前)?\s*(?:采购)?订单(?:\s*(?:号|编号)?\s*[A-Za-z0-9_-]+)?",
        r"(?:please\s+)?cancel\s+(?:this|the)?\s*order(?:\s+[A-Za-z0-9_-]+)?",
    )
    for intent, patterns in (("confirm_order", order_patterns), ("payment", payment_patterns), ("cancel", cancel_patterns)):
        if any(re.fullmatch(pattern + r"[.!。！]?", text, re.IGNORECASE) for pattern in patterns):
            return intent
    return "recommend"

_KNOWN_CATEGORIES = {
    "laptop", "monitor", "keyboard", "mouse", "headset", "webcam",
    "printer", "office chair", "standing desk", "tablet", "projector",
    "router", "docking station", "external ssd", "conference speaker",
    "phone",
}

def order_status_reference(message: str) -> tuple[bool, str | None]:
    """Recognize bounded read requests; a reference never grants ownership."""
    patterns = (
        r"(?:请)?(?:查询|查看)\s*订单状态(?:\s*[#：:]?\s*(?P<reference>[A-Za-z0-9_-]+))?",
        r"(?:please\s+)?(?:show|check|get)\s+(?:the\s+)?order\s+status(?:\s+(?P<reference>[A-Za-z0-9_-]+))?",
        r"order\s+status(?:\s+(?P<reference>[A-Za-z0-9_-]+))?",
    )
    for pattern in patterns:
        match = re.fullmatch(pattern + r"[?？.!。！]?", message.strip(), re.IGNORECASE)
        if match:
            return True, match.group("reference")
    return False, None


def route_intent(message: str) -> dict:
    text = message.strip()
    lowered = text.lower()

    transaction = transaction_intent(text)
    if transaction != "recommend":
        return {"route": transaction, "confidence": 0.9, "matched_by": "explicit_transaction_command"}

    if order_status_reference(text)[0]:
        return {"route": "order_status", "confidence": 0.9, "matched_by": "readonly_order_status"}

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
