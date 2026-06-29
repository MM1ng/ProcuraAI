SYSTEM_PROMPT = """
You are Enterprise Procurement Agent, an internal procurement assistant.
Parse purchase intent, retrieve compliant products, verify budget, inventory,
supplier and delivery constraints, then produce an auditable procurement plan.
Use mock-safe deterministic tools when model credentials are unavailable.
""".strip()


# Fallback response templates used when LLM is mocked or unavailable.
# The answer is enriched with item-level details in _answer_from_plan().
PLAN_RESPONSE_TEMPLATES = {
    "en": (
        "I found {item_count} recommended product lines with a total estimated cost of "
        "${total_amount:.2f}. Budget status: {budget_status}. Inventory status: "
        "{inventory_status}. Constraint status: {constraint_satisfaction}."
    ),
    "zh": (
        "我找到了 {item_count} 条推荐采购商品线，总预估成本为 ${total_amount:.2f}。"
        "预算状态：{budget_status}。库存状态：{inventory_status}。约束状态：{constraint_satisfaction}。"
    ),
}

ERROR_MESSAGES = {
    "en": "I could not complete the procurement workflow. Please check the request and try again.",
    "zh": "我无法完成本次采购流程。请检查需求后重试。",
}
