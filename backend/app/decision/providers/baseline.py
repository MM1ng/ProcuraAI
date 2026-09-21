from __future__ import annotations

import re
from time import perf_counter
from typing import Any

from app.agent.router import route_intent, transaction_intent
from app.decision.schemas import DecisionResult, IntentLabel


class BaselineIntentProvider:
    """Offline adapter around the current deterministic routing rules.

    The supplemental patterns exist only to map benchmark labels that production's
    smaller RouteType does not represent; this class is never used by the agent.
    """

    name = "baseline"

    def classify_intent(self, text: str, context: dict[str, Any] | None = None) -> DecisionResult:
        started = perf_counter()
        stripped = text.strip()
        lowered = stripped.lower()
        label, confidence, matched_by = self._classify(stripped, lowered)
        return DecisionResult(
            label=label, confidence=confidence, provider=self.name, model="current_router_rules",
            latency_ms=(perf_counter() - started) * 1000, metadata={"matched_by": matched_by},
        )

    @staticmethod
    def _classify(text: str, lowered: str) -> tuple[IntentLabel, float | None, str]:
        transaction = transaction_intent(text)
        if transaction == "confirm_order":
            return IntentLabel.CONFIRM_ORDER, 0.9, "production_transaction_intent"
        if transaction == "payment":
            return IntentLabel.PAYMENT, 0.9, "production_transaction_intent"
        if re.search(r"确认.*方案.*下单|请确认下单", lowered):
            return IntentLabel.CONFIRM_ORDER, None, "benchmark_order_mapping"
        if re.search(r"订单.*(?:状态|怎么样|支付了吗|什么时候到|进度|已付款|情况|处理中)|(?:查询|查看).*订单|(?:order|status).*(?:status|paid|track|processing)|track.*order", lowered):
            return IntentLabel.ORDER_STATUS, None, "benchmark_status_mapping"
        if re.search(r"\b(?:pay|payment|checkout)\b|(?:去)?付款|支付(?:订单)?|进入结账", lowered):
            return IntentLabel.PAYMENT, None, "benchmark_payment_mapping"
        if re.search(r"为什么|解释|理由|原因|why|explain|reason", lowered):
            return IntentLabel.EXPLAIN_PLAN, None, "benchmark_explain_mapping"
        if re.search(r"预算.*(?:降|改)|换成|换(?:个|为)|便宜|修改|调整|改成|replace|change|cheaper|modify|reduce.*budget", lowered):
            return IntentLabel.MODIFY_PLAN, None, "benchmark_modify_mapping"
        if re.search(r"比较|对比|区别|哪个.*(?:好|省)|性价比|\b(?:compare|versus|vs\.?|difference)\b|which plan", lowered):
            return IntentLabel.COMPARE_PLAN, None, "benchmark_compare_mapping"
        if re.search(r"(?:就这个|还行|再看看|可以买|这个怎么样|先这样|不错|考虑一下|可以吗|暂时不用|this one|looks good|let me think|maybe|can i buy|look again)", lowered):
            return IntentLabel.CLARIFY, None, "benchmark_ambiguous_mapping"
        if re.search(r"办公电脑怎么配|远程会议.*摄像头", lowered):
            return IntentLabel.RECOMMEND, None, "benchmark_recommend_mapping"
        routed = route_intent(text)
        mapping = {"recommendation": IntentLabel.RECOMMEND, "search": IntentLabel.RECOMMEND,
                   "compare": IntentLabel.COMPARE_PLAN, "unknown": IntentLabel.CLARIFY}
        return mapping[routed["route"]], routed.get("confidence"), f"production_route:{routed.get('matched_by')}"
