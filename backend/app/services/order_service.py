from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Any

from app.core.config import DATA_DIR
from app.schemas.order import OrderPlanSelection
from app.services import product_service


ORDERS_FILE = DATA_DIR / "orders.json"


def _read_orders() -> list[dict[str, Any]]:
    if not ORDERS_FILE.exists():
        return []
    return json.loads(ORDERS_FILE.read_text(encoding="utf-8"))


def _write_orders(orders: list[dict[str, Any]]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    ORDERS_FILE.write_text(json.dumps(orders, indent=2), encoding="utf-8")


def create_order_from_plan(plan: dict[str, Any], user_id: str = "demo-user") -> dict[str, Any]:
    # Validate here too: Agent/tool callers bypass the HTTP request schema.
    selection = OrderPlanSelection.model_validate(plan)
    catalog = {product["product_id"]: product for product in product_service.load_products_from_csv()}
    order_items = []
    total = Decimal("0.00")
    for item in selection.items:
        product = catalog.get(item.product_id)
        if product is None:
            raise ValueError(f"Unknown product_id: {item.product_id}")
        try:
            unit_price = Decimal(str(product["price"]))
            if not unit_price.is_finite() or unit_price <= 0:
                raise ValueError(f"Invalid catalog price for product: {item.product_id}")
            unit_price = unit_price.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            if unit_price <= 0:
                raise ValueError(f"Invalid catalog price for product: {item.product_id}")
            subtotal = (unit_price * item.quantity).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            total += subtotal
        except (InvalidOperation, KeyError) as exc:
            raise ValueError(f"Invalid catalog amount for product: {item.product_id}") from exc
        order_items.append(
            {
                **{key: product[key] for key in ("category", "brand", "supplier", "rating", "stock", "delivery_days") if key in product},
                "order_item_id": str(uuid.uuid4()),
                "product_id": item.product_id,
                "name": product.get("name", ""),
                "quantity": item.quantity,
                "unit_price": float(unit_price),
                "subtotal": float(subtotal),
            }
        )

    total_amount = float(total)
    plan_id = selection.plan_option_id or selection.plan_id or ""
    over_budget = selection.budget is not None and total > Decimal(str(selection.budget))
    budget_status = "no_budget_provided" if selection.budget is None else ("over_budget" if over_budget else "within_budget")
    # Rebuild rather than copying the original plan: checkout also reads this snapshot.
    snapshot = {
        "plan_option_id": plan_id,
        "items": [{key: value for key, value in item.items() if key != "order_item_id"} for item in order_items],
        "total": total_amount,
        "total_amount": total_amount,
        "budget": selection.budget,
        "budget_status": budget_status,
        "status": budget_status,
        "over_budget": over_budget,
        "selectable": not over_budget,
    }
    return {
        "order_id": f"ORD-{uuid.uuid4().hex[:10].upper()}",
        "user_id": user_id,
        "plan_id": plan_id,
        "procurement_plan": snapshot,
        "order_items": order_items,
        "total_amount": total_amount,
        "status": "pending_payment",
        "stripe_session_id": None,
        "processed_payment_event_ids": [],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


def save_order(order: dict[str, Any]) -> dict[str, Any]:
    orders = _read_orders()
    orders.append(order)
    _write_orders(orders)
    return order


def list_orders() -> list[dict[str, Any]]:
    return sorted(_read_orders(), key=lambda item: item.get("created_at", ""), reverse=True)


def get_order(order_id: str) -> dict[str, Any] | None:
    for order in _read_orders():
        if order.get("order_id") == order_id:
            return order
    return None


def get_order_by_stripe_session_id(session_id: str) -> dict[str, Any] | None:
    for order in _read_orders():
        if order.get("stripe_session_id") == session_id:
            return order
    return None


def update_order(order_id: str, updates: dict[str, Any]) -> dict[str, Any] | None:
    orders = _read_orders()
    updated: dict[str, Any] | None = None
    for order in orders:
        if order.get("order_id") == order_id:
            order.update(updates)
            updated = order
            break
    if updated is None:
        return None
    _write_orders(orders)
    return updated


def mark_payment_event_processed(order_id: str, event_id: str | None, status: str) -> dict[str, Any] | None:
    orders = _read_orders()
    updated: dict[str, Any] | None = None
    for order in orders:
        if order.get("order_id") != order_id:
            continue
        processed = list(order.get("processed_payment_event_ids") or [])
        if event_id and event_id in processed:
            updated = order
            break
        order["status"] = status
        if event_id:
            processed.append(event_id)
        order["processed_payment_event_ids"] = processed
        updated = order
        break
    if updated is None:
        return None
    _write_orders(orders)
    return updated
