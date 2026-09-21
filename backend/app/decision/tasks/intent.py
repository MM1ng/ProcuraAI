from app.decision.schemas import IntentGoldCase, IntentLabel


INTENT_DEFINITIONS = {
    IntentLabel.RECOMMEND.value: "New procurement need seeking products or recommendations, without order authorization.",
    IntentLabel.MODIFY_PLAN.value: "Change an existing plan's budget, brand, quantity, product, delivery, or constraint.",
    IntentLabel.COMPARE_PLAN.value: "Compare plans, options, suppliers, or alternatives.",
    IntentLabel.EXPLAIN_PLAN.value: "Explain a recommendation, price, budget, selection reason, or current plan.",
    IntentLabel.CONFIRM_ORDER.value: "Explicitly authorize creating an order from an existing plan.",
    IntentLabel.PAYMENT.value: "Explicitly authorize payment for an existing order.",
    IntentLabel.ORDER_STATUS.value: "Ask about order, payment, delivery, or fulfillment status without authorizing payment.",
    IntentLabel.CLARIFY.value: "Ambiguous preference, hesitation, condition, quoted text, negated transaction, or unsafe-to-classify input.",
}

INTENT_INSTRUCTIONS = (
    "Classify the procurement message into exactly one choice. A request to buy products is recommend, not confirm_order. "
    "Only explicit authorization to create an order is confirm_order; only explicit authorization to pay an existing order is payment. "
    "Ambiguous, conditional, quoted, negated, or question-form transaction language is clarify unless it asks for order status."
)

__all__ = ["IntentGoldCase", "IntentLabel", "INTENT_DEFINITIONS", "INTENT_INSTRUCTIONS"]
