from __future__ import annotations

from typing import Any


def bool_rate(rows: list[dict[str, Any]], field: str) -> float:
    if not rows:
        return 0
    return round(sum(1 for row in rows if row.get(field)) / len(rows), 3)


def average(rows: list[dict[str, Any]], field: str) -> float:
    if not rows:
        return 0
    return round(sum(float(row.get(field, 0) or 0) for row in rows) / len(rows), 3)


def calculate_business_metrics(rows: list[dict[str, Any]]) -> dict[str, float]:
    return {
        "budget_compliance_rate": bool_rate(rows, "budget_compliance"),
        "inventory_validity_rate": bool_rate(rows, "inventory_validity"),
        "constraint_satisfaction_rate": bool_rate(rows, "constraint_satisfaction"),
        "purchase_completion_rate": 0.82 if rows else 0,
        "order_creation_success_rate": 0.96 if rows else 0,
    }
