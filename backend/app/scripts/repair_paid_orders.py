from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from app.services import order_service


def _is_repairable(order: dict, include_checkout_sessions: bool) -> bool:
    if order.get("status") != "pending_payment":
        return False
    session_id = str(order.get("stripe_session_id") or "")
    if session_id.startswith("mock_"):
        return True
    return include_checkout_sessions and session_id.startswith("cs_test_")


def repair_paid_orders(apply: bool = False, include_checkout_sessions: bool = False) -> list[str]:
    orders = order_service._read_orders()
    repaired_ids = [
        str(order.get("order_id"))
        for order in orders
        if _is_repairable(order, include_checkout_sessions)
    ]
    if not apply or not repaired_ids:
        return repaired_ids

    backup_path = Path(f"{order_service.ORDERS_FILE}.{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}.bak")
    shutil.copy2(order_service.ORDERS_FILE, backup_path)
    for order in orders:
        if str(order.get("order_id")) in repaired_ids:
            order["status"] = "paid"
    order_service._write_orders(orders)
    return repaired_ids


def main() -> None:
    parser = argparse.ArgumentParser(description="Repair pending orders that are known to have completed payment.")
    parser.add_argument("--apply", action="store_true", help="Write changes. Without this flag, only prints a dry run.")
    parser.add_argument(
        "--all-checkout-sessions",
        action="store_true",
        help="Also mark pending orders with cs_test_* checkout sessions as paid.",
    )
    args = parser.parse_args()

    repaired_ids = repair_paid_orders(
        apply=args.apply,
        include_checkout_sessions=args.all_checkout_sessions,
    )
    mode = "updated" if args.apply else "would update"
    print(json.dumps({"mode": mode, "count": len(repaired_ids), "order_ids": repaired_ids}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
