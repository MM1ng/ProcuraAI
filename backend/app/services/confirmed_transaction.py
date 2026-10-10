"""Server-issued capabilities for chat confirmation and independent carts."""
from copy import deepcopy
from datetime import datetime, timezone
from uuid import uuid4

from app.agent.session_state import (
    calculate_plan_hash, get_session_state, save_session_state,
    validate_plan_snapshot, validate_snapshot_content,
)
from app.services import order_service
from app.services.transaction_lock import TRANSACTION_LOCK
from app.services.caller_identity import require_caller, require_owner, resources_for_owner, save_resource, read_resource

_CONFIRMATIONS: dict[str, dict] = {}
_CART_QUOTES: dict[str, dict] = {}


class SnapshotInvalid(ValueError):
    def __init__(self, reasons):
        self.reasons = reasons
        self.detail = {"code": "PLAN_SNAPSHOT_INVALID", "reasons": reasons,
                       "message": "方案已变化或确认信息无效，请重新展示并再次确认。"}
        super().__init__(", ".join(reasons))


def require_snapshot(session_id, plan_id, plan_hash, plan_version):
    snapshot, reasons = validate_plan_snapshot(session_id, plan_id, plan_hash, plan_version)
    if reasons:
        raise SnapshotInvalid(reasons)
    return snapshot


def _binding(session_id, plan_id, plan_hash, plan_version, user_id):
    return {"session_id": session_id, "plan_id": plan_id, "plan_hash": plan_hash,
            "plan_version": plan_version, "user_id": user_id}


def require_matching_rebuild(snapshot, order):
    def selection(items):
        return [(i["product_id"], i["quantity"], i.get("unit_price"), i.get("delivery_days"), i.get("stock")) for i in items]
    if selection(snapshot["items"]) != selection(order["order_items"]) or order["total_amount"] != snapshot.get("total_amount"):
        raise SnapshotInvalid(["catalog_changed_during_order"])


def issue_confirmation(session_id, plan_id, plan_hash, plan_version, user_id=None):
    with TRANSACTION_LOCK:
        user_id = require_caller().actor_id
        require_snapshot(session_id, plan_id, plan_hash, plan_version)
        binding = _binding(session_id, plan_id, plan_hash, plan_version, user_id)
        binding["owner_actor_id"] = user_id
        _CONFIRMATIONS.update(resources_for_owner("confirmation"))
        # Repeated clicks/retries for this displayed version share one confirmation.
        for token, existing in _CONFIRMATIONS.items():
            if existing == binding:
                return token
        token = uuid4().hex
        _CONFIRMATIONS[token] = binding
        save_resource("confirmation", token, binding)
        return token


def create_confirmed_order(session_id, plan_id, plan_hash, plan_version, confirmation_id, user_id=None):
    with TRANSACTION_LOCK:
        caller = require_caller()
        user_id = caller.actor_id
        snapshot = require_snapshot(session_id, plan_id, plan_hash, plan_version)
        binding = _binding(session_id, plan_id, plan_hash, plan_version, user_id)
        binding["owner_actor_id"] = caller.actor_id
        # Persisted order binding permits retries after the transient token map
        # was cleared, provided the current server snapshot still validates.
        existing = next((o for o in order_service.list_orders() if o.get("confirmation_id") == confirmation_id or o.get("confirmation_binding") == binding), None)
        issued = _CONFIRMATIONS.get(confirmation_id) or read_resource("confirmation", confirmation_id)
        persisted_confirmation = (existing and existing.get("confirmation_id") == confirmation_id
                                  and existing.get("confirmation_binding") == binding)
        if not confirmation_id or (issued != binding and not persisted_confirmation):
            raise SnapshotInvalid(["confirmation_binding_invalid"])
        if existing:
            require_owner(existing, caller)
            if existing.get("confirmation_binding") != binding:
                raise SnapshotInvalid(["confirmation_binding_invalid"])
            return existing
        order = order_service.create_order_from_plan(snapshot, user_id)
        # Verify the canonical rebuild didn't race a catalog update.
        require_matching_rebuild(snapshot, order)
        require_snapshot(session_id, plan_id, plan_hash, plan_version)
        order.update({"source": "chat", "confirmation_id": confirmation_id,
                      "confirmation_binding": binding, "owner_actor_id": caller.actor_id})
        return order_service.save_order(order)


def require_confirmed_order_for_payment(session_id, plan_id, plan_hash, plan_version, confirmation_id):
    """Resolve a previously created owned order without creating or signing."""
    with TRANSACTION_LOCK:
        caller = require_caller()
        require_snapshot(session_id, plan_id, plan_hash, plan_version)
        binding = _binding(session_id, plan_id, plan_hash, plan_version, caller.actor_id)
        binding["owner_actor_id"] = caller.actor_id
        order = next((o for o in order_service.list_orders()
                      if o.get("owner_actor_id") == caller.actor_id
                      and o.get("confirmation_id") == confirmation_id
                      and o.get("confirmation_binding") == binding), None)
        issued = _CONFIRMATIONS.get(confirmation_id) or read_resource("confirmation", confirmation_id)
        if not confirmation_id or (issued != binding and order is None):
            raise SnapshotInvalid(["confirmation_binding_invalid"])
        if order is None:
            raise ValueError("An existing confirmed order is required before payment.")
        require_owner(order, caller)
        validate_order_confirmation(order)
        if order.get("status") == "paid":
            raise ValueError("This order is already paid.")
        if order.get("status") not in {"draft", "pending_payment"}:
            raise ValueError("This order is not payable.")
        return order


def select_registered_plan(session_id, plan_id, plan_hash, plan_version, selected_plan_id, selected_plan_hash, selected_plan_version):
    with TRANSACTION_LOCK:
        require_snapshot(session_id, plan_id, plan_hash, plan_version)
        state = get_session_state(session_id)
        candidate = next((o["plan"] for o in state.get("plan_options", []) if o["plan"].get("plan_id") == selected_plan_id), None)
        if candidate is None:
            raise SnapshotInvalid(["selected_plan_not_registered"])
        if candidate.get("plan_hash") != selected_plan_hash or candidate.get("plan_version") != selected_plan_version:
            raise SnapshotInvalid(["selected_plan_binding_mismatch"])
        reasons = validate_snapshot_content(candidate)
        if reasons:
            raise SnapshotInvalid(reasons)
        return save_session_state(session_id, state["parsed_intent"], candidate,
                                  state["retrieved_products"], state["trace_id"], state["plan_options"])


def issue_cart_quote(plan, user_id=None):
    with TRANSACTION_LOCK:
        caller = require_caller()
        user_id = caller.actor_id
        order = order_service.create_order_from_plan(plan, user_id)
        snapshot = order["procurement_plan"]
        token = uuid4().hex
        snapshot.update({"plan_id": f"cart-{token}", "created_at": datetime.now(timezone.utc).isoformat()})
        snapshot["plan_hash"] = calculate_plan_hash(snapshot)
        _CART_QUOTES[token] = {"plan": deepcopy(snapshot), "user_id": user_id, "owner_actor_id": caller.actor_id}
        save_resource("cart_quote", token, _CART_QUOTES[token])
        return {"cart_token": token, "plan": snapshot}


def create_cart_order(cart_token, user_id=None):
    with TRANSACTION_LOCK:
        caller = require_caller()
        user_id = caller.actor_id
        quote = _CART_QUOTES.get(cart_token) or read_resource("cart_quote", cart_token)
        require_owner(quote, caller)
        if not quote or quote["user_id"] != user_id:
            raise SnapshotInvalid(["cart_quote_required"])
        reasons = validate_snapshot_content(quote["plan"])
        if reasons:
            raise SnapshotInvalid(reasons)
        existing = next((o for o in order_service.list_orders() if o.get("cart_token") == cart_token), None)
        if existing:
            require_owner(existing, caller)
            return existing
        order = order_service.create_order_from_plan(quote["plan"], user_id)
        require_matching_rebuild(quote["plan"], order)
        reasons = validate_snapshot_content(quote["plan"])
        if reasons:
            raise SnapshotInvalid(reasons)
        order.update({"source": "cart", "cart_token": cart_token, "source_snapshot": deepcopy(quote["plan"]), "owner_actor_id": caller.actor_id})
        return order_service.save_order(order)


def validate_order_confirmation(order):
    require_owner(order)
    if order.get("source") == "chat":
        binding = order.get("confirmation_binding") or {}
        snapshot = require_snapshot(binding.get("session_id"), binding.get("plan_id"),
                                    binding.get("plan_hash"), binding.get("plan_version"))
        require_matching_rebuild(snapshot, order)
        if order.get("plan_id") != binding.get("plan_id"):
            raise SnapshotInvalid(["order_plan_binding_invalid"])
    elif order.get("source") == "cart":
        reasons = validate_snapshot_content(order.get("source_snapshot") or {})
        if reasons:
            raise SnapshotInvalid(reasons)
        require_matching_rebuild(order["source_snapshot"], order)


def clear_transaction_capabilities():
    with TRANSACTION_LOCK:
        _CONFIRMATIONS.clear()
        _CART_QUOTES.clear()
