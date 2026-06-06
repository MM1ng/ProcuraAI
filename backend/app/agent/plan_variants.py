from __future__ import annotations

from collections import defaultdict
from typing import Any, Callable

from app.agent.plan_generator import generate_procurement_plan


PlanSelector = Callable[[list[dict[str, Any]]], dict[str, Any]]


def _group_by_category(products: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for product in products:
        grouped[str(product.get("category", ""))].append(product)
    return grouped


def _quantity_for(intent: dict[str, Any], category: str) -> int:
    quantity_by_category = intent.get("quantity_by_category") or intent.get("quantity_per_category") or {}
    return int(quantity_by_category.get(category, intent.get("people_count") or 1))


def _eligible_candidates(candidates: list[dict[str, Any]], intent: dict[str, Any], category: str) -> list[dict[str, Any]]:
    quantity = _quantity_for(intent, category)
    min_rating = intent.get("min_rating")
    max_delivery_days = intent.get("max_delivery_days")
    eligible = [
        product
        for product in candidates
        if int(product.get("stock", 0) or 0) >= quantity
        and (min_rating is None or float(product.get("rating", 0) or 0) >= float(min_rating))
        and (max_delivery_days is None or int(product.get("delivery_days", 999) or 999) <= int(max_delivery_days))
    ]
    return eligible or candidates


def _cost_optimized(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    return sorted(
        candidates,
        key=lambda product: (
            float(product.get("price", 999999) or 999999),
            int(product.get("delivery_days", 999) or 999),
            -float(product.get("rating", 0) or 0),
        ),
    )[0]


def _balanced(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    return sorted(
        candidates,
        key=lambda product: (
            int(product.get("delivery_days", 999) or 999),
            -float(product.get("rating", 0) or 0),
            float(product.get("price", 999999) or 999999),
        ),
    )[0]


def _premium(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    return sorted(
        candidates,
        key=lambda product: (
            -float(product.get("rating", 0) or 0),
            -int(product.get("warranty_months", 0) or 0),
            int(product.get("delivery_days", 999) or 999),
            -float(product.get("price", 0) or 0),
        ),
    )[0]


def _selected_products_for_strategy(
    products: list[dict[str, Any]],
    intent: dict[str, Any],
    selector: PlanSelector,
) -> list[dict[str, Any]]:
    categories = intent.get("categories") or sorted({product.get("category") for product in products})
    grouped = _group_by_category(products)
    selected: list[dict[str, Any]] = []
    for category in categories:
        candidates = grouped.get(str(category), [])
        if not candidates:
            return []
        selected.append(selector(_eligible_candidates(candidates, intent, str(category))))
    return selected


def _build_option(
    option_id: str,
    name: str,
    strategy: str,
    description: str,
    products: list[dict[str, Any]],
    intent: dict[str, Any],
    selector: PlanSelector,
) -> dict[str, Any] | None:
    selected_products = _selected_products_for_strategy(products, intent, selector)
    if not selected_products:
        return None
    plan = generate_procurement_plan(selected_products, intent)
    if plan.get("missing_categories"):
        return None
    plan["plan_option_id"] = option_id
    plan["plan_strategy"] = strategy
    return {
        "id": option_id,
        "name": name,
        "strategy": strategy,
        "description": description,
        "plan": plan,
    }


def generate_plan_options(products: list[dict[str, Any]], intent: dict[str, Any]) -> list[dict[str, Any]]:
    definitions: list[tuple[str, str, str, str, PlanSelector]] = [
        ("plan_a", "Plan A", "cost_optimized", "Cost Optimized", _cost_optimized),
        ("plan_b", "Plan B", "balanced", "Balanced", _balanced),
        ("plan_c", "Plan C", "premium", "Premium", _premium),
    ]
    options: list[dict[str, Any]] = []
    for option_id, name, strategy, description, selector in definitions:
        option = _build_option(option_id, name, strategy, description, products, intent, selector)
        if option:
            options.append(option)
    return options if len(options) == len(definitions) else []
