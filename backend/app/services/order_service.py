from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core.config import DATA_DIR


ORDERS_FILE = DATA_DIR / "orders.json"


def _read_orders() -> list[dict[str, Any]]:
    if not ORDERS_FILE.exists():
        return []
    return json.loads(ORDERS_FILE.read_text(encoding="utf-8"))


def _write_orders(orders: list[dict[str, Any]]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    ORDERS_FILE.write_text(json.dumps(orders, indent=2), encoding="utf-8")


def create_order_from_plan(plan: dict[str, Any], user_id: str = "demo-user") -> dict[str, Any]:
    order_items = []
    for item in plan.get("items", []):
        quantity = int(item.get("quantity", 0) or 0)
        unit_price = float(item.get("unit_price", item.get("price", 0)) or 0)
        subtotal = round(float(item.get("subtotal", unit_price * quantity) or 0), 2)
        order_items.append(
            {
                "order_item_id": str(uuid.uuid4()),
                "product_id": item.get("product_id"),
                "name": item.get("name", ""),
                "quantity": quantity,
                "unit_price": round(unit_price, 2),
                "subtotal": subtotal,
            }
        )

    total_amount = round(float(plan.get("total_amount", sum(item["subtotal"] for item in order_items)) or 0), 2)
    return {
        "order_id": f"ORD-{uuid.uuid4().hex[:10].upper()}",
        "user_id": user_id,
        "order_items": order_items,
        "total_amount": total_amount,
        "status": "pending_payment",
        "stripe_session_id": None,
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
