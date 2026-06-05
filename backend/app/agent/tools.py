from __future__ import annotations

from typing import Any

from app.agent.intent_parser import parse_purchase_request
from app.agent.plan_generator import calculate_budget_status, generate_procurement_plan
from app.observability.local_tracer import log_observability_event
from app.rag.hybrid_search import filter_products_by_constraints, search_products
from app.services.order_service import create_order_from_plan
from app.services.payment_service import create_checkout


def parse_purchase_request_tool(message: str, previous_intent: dict[str, Any] | None = None) -> dict[str, Any]:
    return parse_purchase_request(message, previous_intent)


def search_products_tool(products: list[dict[str, Any]], query: str, intent: dict[str, Any]) -> list[dict[str, Any]]:
    return search_products(
        products=products,
        query=query,
        categories=intent.get("categories"),
        min_rating=intent.get("min_rating"),
        min_stock=intent.get("people_count"),
        max_delivery_days=intent.get("max_delivery_days"),
    )


def check_inventory(plan: dict[str, Any]) -> str:
    return plan.get("inventory_status", "unknown")


def calculate_budget(total_amount: float, budget: float | None) -> str:
    return calculate_budget_status(total_amount, budget)


def evaluate_response_mock(plan: dict[str, Any]) -> dict[str, Any]:
    return {
        "budget_compliance": plan.get("budget_status") != "over_budget",
        "inventory_validity": plan.get("inventory_status") == "valid",
        "constraint_satisfaction": plan.get("constraint_satisfaction") == "satisfied",
    }


def create_order(plan: dict[str, Any], user_id: str = "demo-user") -> dict[str, Any]:
    return create_order_from_plan(plan, user_id=user_id)


def create_stripe_checkout(order_id: str, amount: float) -> dict[str, str]:
    return create_checkout(order_id=order_id, amount=amount)


__all__ = [
    "parse_purchase_request_tool",
    "search_products_tool",
    "filter_products_by_constraints",
    "check_inventory",
    "calculate_budget",
    "generate_procurement_plan",
    "create_order",
    "create_order_from_plan",
    "create_stripe_checkout",
    "create_checkout",
    "log_observability_event",
    "evaluate_response_mock",
]
