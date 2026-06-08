from __future__ import annotations

import json
import re
from collections import defaultdict
from typing import Any

from app.services.llm_service import safe_llm_invoke


MAX_PLAN_EXPLANATION_CHARS = 800


def calculate_budget_status(total_amount: float, budget: float | None) -> str:
    if budget is None:
        return "no_budget_provided"
    return "within_budget" if total_amount <= budget else "over_budget"


def calculate_avg_rating(items: list[dict[str, Any]]) -> float:
    if not items:
        return 0
    return round(sum(float(item.get("rating", 0) or 0) for item in items) / len(items), 1)


def validate_plan_budget(plan: dict[str, Any], budget: float | None) -> dict[str, Any]:
    total = round(
        sum(
            float(item.get("unit_price", 0) or 0) * int(item.get("quantity", 0) or 0)
            for item in plan.get("items", [])
        ),
        2,
    )
    over_budget = bool(budget is not None and total > float(budget))
    plan["total"] = total
    plan["total_amount"] = total
    plan["budget"] = budget
    plan["over_budget"] = over_budget
    plan["budget_gap"] = round(total - float(budget), 2) if over_budget and budget is not None else 0
    plan["selectable"] = not over_budget
    plan["budget_status"] = calculate_budget_status(total, budget)
    plan["status"] = "over_budget" if over_budget else plan["budget_status"]
    return plan


def _product_score(product: dict[str, Any]) -> tuple[float, int, float]:
    return (
        -float(product.get("rating", 0) or 0),
        int(product.get("delivery_days", 999) or 999),
        float(product.get("price", 999999) or 999999),
    )


def _select_best_by_category(products: list[dict[str, Any]], categories: list[str]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for product in products:
        grouped[str(product.get("category", ""))].append(product)

    selected: list[dict[str, Any]] = []
    for category in categories:
        candidates = grouped.get(category, [])
        if not candidates:
            continue
        selected.append(sorted(candidates, key=_product_score)[0])
    return selected


def _select_budget_aware_by_category(
    products: list[dict[str, Any]],
    categories: list[str],
    quantity_by_category: dict[str, int],
    intent: dict[str, Any],
) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for product in products:
        grouped[str(product.get("category", ""))].append(product)

    selected: list[dict[str, Any]] = []
    min_rating = intent.get("min_rating")
    max_delivery_days = intent.get("max_delivery_days")
    for category in categories:
        quantity = int(quantity_by_category.get(category, intent.get("people_count") or 1))
        candidates = grouped.get(category, [])
        eligible = [
            product
            for product in candidates
            if int(product.get("stock", 0) or 0) >= quantity
            and (min_rating is None or float(product.get("rating", 0) or 0) >= float(min_rating))
            and (max_delivery_days is None or int(product.get("delivery_days", 999) or 999) <= int(max_delivery_days))
        ]
        pool = eligible or candidates
        if not pool:
            continue
        selected.append(
            sorted(
                pool,
                key=lambda product: (
                    float(product.get("price", 999999) or 999999),
                    int(product.get("delivery_days", 999) or 999),
                    -float(product.get("rating", 0) or 0),
                ),
            )[0]
        )
    return selected


def _group_products(products: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for product in products:
        grouped[str(product.get("category", ""))].append(product)
    return grouped


def _eligible_products(
    candidates: list[dict[str, Any]],
    quantity: int,
    intent: dict[str, Any],
    excluded_product_ids: set[str] | None = None,
    allow_constraint_fallback: bool = True,
) -> list[dict[str, Any]]:
    min_rating = intent.get("min_rating")
    max_delivery_days = intent.get("max_delivery_days")
    excluded_product_ids = excluded_product_ids or set()
    eligible = [
        product
        for product in candidates
        if str(product.get("product_id")) not in excluded_product_ids
        and int(product.get("stock", 0) or 0) >= quantity
        and (min_rating is None or float(product.get("rating", 0) or 0) >= float(min_rating))
        and (max_delivery_days is None or int(product.get("delivery_days", 999) or 999) <= int(max_delivery_days))
    ]
    if eligible or not allow_constraint_fallback:
        return eligible
    return [
        product for product in candidates if str(product.get("product_id")) not in excluded_product_ids
    ]


def _infer_replacement_categories(intent: dict[str, Any], previous_plan: dict[str, Any] | None) -> list[str]:
    structured_categories = list(intent.get("replacement_categories") or [])
    if structured_categories:
        return structured_categories
    request = str(intent.get("replacement_request") or intent.get("raw_message") or "").lower()
    categories = list(intent.get("categories") or [])
    if not previous_plan:
        return categories

    previous_categories = [str(item.get("category")) for item in previous_plan.get("items", [])]
    preserved = _infer_preserved_categories(request, previous_categories)
    matched = [
        category
        for category in previous_categories
        if category.lower() in request and category not in preserved
    ]
    if matched:
        return matched
    fallback = categories or previous_categories
    return [category for category in fallback if category not in preserved]


def _infer_preserved_categories(request: str, categories: list[str]) -> set[str]:
    preserved: set[str] = set()
    preserve_words = r"keep|preserve|unchanged|same"
    for category in categories:
        category_pattern = re.escape(category.lower())
        if re.search(rf"\b(?:{preserve_words})\b[^.?!,;]{{0,80}}\b{category_pattern}\b", request):
            preserved.add(category)
            continue
        if re.search(rf"\b{category_pattern}\b[^.?!,;]{{0,80}}\b(?:unchanged|same)\b", request):
            preserved.add(category)
    return preserved


def _item_from_previous(item: dict[str, Any]) -> dict[str, Any]:
    return dict(item)


def _candidate_total(
    selected: list[dict[str, Any]],
    quantity_by_category: dict[str, int],
    people_count: int,
) -> float:
    total = 0.0
    for product in selected:
        category = str(product.get("category"))
        quantity = int(quantity_by_category.get(category, people_count))
        unit_price = float(product.get("price", product.get("unit_price", 0)) or 0)
        subtotal = float(product.get("subtotal", unit_price * quantity) or 0)
        total += subtotal
    return round(total, 2)


def _candidate_subtotal(product: dict[str, Any], quantity: int) -> float:
    unit_price = float(product.get("price", product.get("unit_price", 0)) or 0)
    return round(float(product.get("subtotal", unit_price * quantity) or 0), 2)


def _select_followup_by_category(
    products: list[dict[str, Any]],
    categories: list[str],
    quantity_by_category: dict[str, int],
    intent: dict[str, Any],
    previous_plan: dict[str, Any] | None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    revision_intent = str(intent.get("revision_intent") or "new_plan")
    if revision_intent not in {"cheaper", "replace_product"} or not previous_plan:
        selected = (
            _select_budget_aware_by_category(products, categories, quantity_by_category, intent)
            if intent.get("budget") is not None or intent.get("need_cheaper_plan")
            else _select_best_by_category(products, categories)
        )
        return selected, {"revision_type": revision_intent}

    grouped = _group_products(products)
    previous_items = {str(item.get("category")): item for item in previous_plan.get("items", [])}
    previous_total_amount = round(float(previous_plan.get("total_amount") or 0), 2)

    selected: list[dict[str, Any]] = []
    metadata: dict[str, Any] = {"revision_type": revision_intent}
    replacement_categories = _infer_replacement_categories(intent, previous_plan)
    replacement_brand = str(intent.get("replacement_brand") or "").strip()
    actual_replacement_categories: list[str] = []
    request_text = str(intent.get("replacement_request") or intent.get("raw_message") or "").lower()
    requires_lower_cost_replacement = bool(re.search(r"lower cost|cheaper|less expensive|reduce cost", request_text))

    for category in categories:
        quantity = int(quantity_by_category.get(category, intent.get("people_count") or 1))
        previous_item = previous_items.get(category)
        candidates = grouped.get(category, [])

        if revision_intent == "replace_product" and category not in replacement_categories:
            if previous_item:
                selected.append(_item_from_previous(previous_item))
            continue

        excluded = {str(previous_item.get("product_id"))} if previous_item else set()
        if revision_intent == "replace_product" and replacement_brand and category in replacement_categories:
            candidates = [
                product
                for product in candidates
                if str(product.get("brand", "")).lower() == replacement_brand.lower()
            ]
            pool = _eligible_products(
                candidates,
                quantity,
                intent,
                excluded_product_ids=excluded,
                allow_constraint_fallback=False,
            )
            if not candidates or not pool:
                if previous_item:
                    selected.append(_item_from_previous(previous_item))
                metadata["status"] = "constraint_not_satisfied"
                metadata["revision_note"] = "replacement_brand_not_available"
                metadata["unsatisfied_constraints"] = [
                    f"{category} brand must be {replacement_brand}"
                ]
                continue
        else:
            pool = _eligible_products(candidates, quantity, intent, excluded_product_ids=excluded)
        if not pool:
            if previous_item:
                selected.append(_item_from_previous(previous_item))
            if revision_intent == "replace_product" and replacement_brand and category in replacement_categories:
                metadata["status"] = "constraint_not_satisfied"
                metadata["revision_note"] = "replacement_brand_not_available"
                metadata["unsatisfied_constraints"] = [
                    f"{category} brand must be {replacement_brand}"
                ]
            continue

        chosen = sorted(
            pool,
            key=lambda product: (
                float(product.get("price", 999999) or 999999),
                int(product.get("delivery_days", 999) or 999),
                -float(product.get("rating", 0) or 0),
            ),
        )[0]

        if (
            revision_intent == "replace_product"
            and requires_lower_cost_replacement
            and previous_item
            and _candidate_subtotal(chosen, quantity) >= _candidate_subtotal(previous_item, quantity)
        ):
            selected.append(_item_from_previous(previous_item))
            metadata["revision_note"] = "no_lower_cost_replacement_found"
            continue

        selected.append(chosen)
        if revision_intent == "replace_product" and (
            not previous_item or str(chosen.get("product_id")) != str(previous_item.get("product_id"))
        ):
            actual_replacement_categories.append(category)

    if revision_intent == "cheaper":
        people_count = int(intent.get("people_count") or 1)
        candidate_total = _candidate_total(selected, quantity_by_category, people_count)
        if candidate_total >= previous_total_amount:
            selected = [
                _item_from_previous(previous_items[category])
                for category in categories
                if category in previous_items
            ]
            metadata["revision_note"] = "no_cheaper_option_found"
    if revision_intent == "replace_product":
        metadata["replacement_categories"] = actual_replacement_categories
        if replacement_brand:
            metadata["replacement_brand"] = replacement_brand

    return selected, metadata


def generate_procurement_plan(
    products: list[dict[str, Any]],
    intent: dict[str, Any],
    previous_plan: dict[str, Any] | None = None,
) -> dict[str, Any]:
    categories = intent.get("categories") or sorted({product.get("category") for product in products})
    people_count = int(intent.get("people_count") or 1)
    quantity_by_category = intent.get("quantity_by_category") or {
        category: people_count for category in categories
    }
    selected, revision_metadata = _select_followup_by_category(
        products,
        categories,
        quantity_by_category,
        intent,
        previous_plan,
    )

    items: list[dict[str, Any]] = []
    inventory_valid = True
    constraints_satisfied = True
    min_rating = intent.get("min_rating")
    max_delivery_days = intent.get("max_delivery_days")

    for product in selected:
        category = str(product.get("category"))
        quantity = int(quantity_by_category.get(category, people_count))
        unit_price = round(float(product.get("price", product.get("unit_price", 0)) or 0), 2)
        subtotal = round(float(product.get("subtotal", unit_price * quantity) or 0), 2)
        stock = int(product.get("stock", 0) or 0)
        rating = float(product.get("rating", 0) or 0)
        delivery_days = int(product.get("delivery_days", 999) or 999)

        if stock < quantity:
            inventory_valid = False
        if min_rating is not None and rating < float(min_rating):
            constraints_satisfied = False
        if max_delivery_days is not None and delivery_days > int(max_delivery_days):
            constraints_satisfied = False

        items.append(
            {
                "product_id": product.get("product_id"),
                "name": product.get("name"),
                "category": category,
                "brand": product.get("brand", ""),
                "supplier": product.get("supplier", ""),
                "quantity": quantity,
                "unit_price": unit_price,
                "subtotal": subtotal,
                "rating": rating,
                "stock": stock,
                "delivery_days": delivery_days,
                "reason": (
                    f"Selected for {category}: rating {rating}, delivery in "
                    f"{delivery_days} days, stock {stock}, unit price ${unit_price:.2f}."
                ),
            }
        )

    total_amount = round(sum(item["subtotal"] for item in items), 2)
    budget_status = calculate_budget_status(total_amount, intent.get("budget"))
    if budget_status == "over_budget":
        constraints_satisfied = False

    missing_categories = [category for category in categories if category not in {item["category"] for item in items}]
    if missing_categories:
        constraints_satisfied = False
    if revision_metadata.get("status") == "constraint_not_satisfied":
        constraints_satisfied = False

    previous_total_amount = None
    savings_amount = None
    if previous_plan and previous_plan.get("total_amount") is not None:
        previous_total_amount = round(float(previous_plan.get("total_amount") or 0), 2)
        savings_amount = round(previous_total_amount - total_amount, 2)

    plan = {
        "items": items,
        "selected_items": items,
        "total_amount": total_amount,
        "total": total_amount,
        "previous_total_amount": previous_total_amount,
        "savings_amount": savings_amount,
        **revision_metadata,
        "budget": intent.get("budget"),
        "budget_status": budget_status,
        "inventory_status": "valid" if inventory_valid else "insufficient_stock",
        "constraint_satisfaction": "satisfied" if constraints_satisfied else "needs_review",
        "missing_categories": missing_categories,
        "recommendation_reason": (
            f"Recommended {len(items)} product lines for {people_count} people. "
            f"Total amount is ${total_amount:.2f}."
        ),
        "recommendation_summary": (
            f"Recommended {len(items)} product lines for {people_count} people. "
            f"Total amount is ${total_amount:.2f}."
        ),
        "status": revision_metadata.get("status", budget_status),
        "avg_rating": calculate_avg_rating(items),
    }
    return validate_plan_budget(plan, intent.get("budget"))


def _json_for_prompt(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, default=str)


def build_plan_explanation_prompt(
    parsed_intent: dict[str, Any],
    retrieved_products: list[dict[str, Any]],
    calculated_plan: dict[str, Any],
) -> str:
    return f"""
You are an enterprise procurement assistant.
You must explain the procurement plan based only on the provided product data and calculated plan.
Do not invent products, prices, stock, suppliers, delivery days, ratings, or discounts.

User intent:
{_json_for_prompt(parsed_intent)}

Retrieved products:
{_json_for_prompt(retrieved_products)}

Calculated procurement plan:
{_json_for_prompt(calculated_plan)}

Write a concise recommendation explanation for a business user.
Include:
1. selected items
2. total amount
3. budget status
4. inventory status
5. why this plan is recommended
6. any risk or limitation
""".strip()


def generate_plan_explanation(
    parsed_intent: dict[str, Any],
    retrieved_products: list[dict[str, Any]],
    calculated_plan: dict[str, Any],
    fallback_answer: str,
) -> dict[str, Any]:
    prompt = build_plan_explanation_prompt(parsed_intent, retrieved_products, calculated_plan)
    result = safe_llm_invoke(prompt, purpose="plan_explanation")
    content = str(result.get("content") or "").strip()
    if result.get("used_mock_llm") or not content or len(content) > MAX_PLAN_EXPLANATION_CHARS:
        content = fallback_answer

    return {
        "content": content,
        "model_provider": result.get("model_provider"),
        "model_name": result.get("model_name"),
        "used_mock_llm": bool(result.get("used_mock_llm")),
        "llm_error": result.get("error"),
        "llm_latency_ms": result.get("latency_ms"),
        "llm_fallback_reason": result.get("fallback_reason"),
    }
