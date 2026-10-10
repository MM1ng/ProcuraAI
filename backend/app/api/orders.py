from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.schemas.order import OrderCreateRequest, OrderResponse, CartQuoteRequest, CartOrderRequest
from app.services.order_service import get_order, list_orders
from app.services.plan_execution_guard import PlanNotExecutableError
from app.services.confirmed_transaction import SnapshotInvalid, create_confirmed_order, issue_cart_quote, create_cart_order
from app.services.caller_identity import require_caller, require_owner


router = APIRouter(prefix="/api/orders", tags=["orders"])


@router.post("", response_model=OrderResponse)
def create_order(request: OrderCreateRequest) -> OrderResponse:
    try:
        if not all((request.session_id, request.plan_id, request.plan_hash, request.plan_version, request.confirmation_id)):
            raise HTTPException(status_code=409, detail={"code": "PLAN_CONFIRMATION_REQUIRED"})
        if request.plan.plan_id != request.plan_id:
            raise SnapshotInvalid(["plan_id_mismatch"])
        order = create_confirmed_order(request.session_id, request.plan_id, request.plan_hash,
                                       request.plan_version, request.confirmation_id)
    except SnapshotInvalid as exc:
        raise HTTPException(status_code=409, detail=exc.detail) from exc
    except PlanNotExecutableError as exc:
        raise HTTPException(status_code=409, detail=exc.detail) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return OrderResponse(**order)


@router.post("/cart/quote")
def cart_quote(request: CartQuoteRequest):
    try:
        # Chat identities cannot be transported into the independent cart API.
        if request.plan.plan_id or request.plan.plan_option_id:
            raise SnapshotInvalid(["cart_selection_only"])
        return issue_cart_quote(request.plan.model_dump(exclude_unset=True))
    except (SnapshotInvalid, PlanNotExecutableError) as exc:
        raise HTTPException(status_code=409, detail=exc.detail) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/cart", response_model=OrderResponse)
def cart_order(request: CartOrderRequest):
    try:
        return OrderResponse(**create_cart_order(request.cart_token))
    except (SnapshotInvalid, PlanNotExecutableError) as exc:
        raise HTTPException(status_code=409, detail=exc.detail) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("")
def get_orders() -> dict:
    owner = require_caller().actor_id
    orders = [order for order in list_orders() if order.get("owner_actor_id") == owner]
    return {"items": orders, "total": len(orders)}


@router.get("/{order_id}", response_model=OrderResponse)
def get_order_detail(order_id: str) -> OrderResponse:
    order = get_order(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    require_owner(order)
    return OrderResponse(**order)
