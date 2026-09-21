from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.schemas.order import OrderCreateRequest, OrderResponse
from app.services.order_service import create_order_from_plan, get_order, list_orders, save_order
from app.services.plan_execution_guard import PlanNotExecutableError


router = APIRouter(prefix="/api/orders", tags=["orders"])


@router.post("", response_model=OrderResponse)
def create_order(request: OrderCreateRequest) -> OrderResponse:
    try:
        order = create_order_from_plan(request.plan.model_dump(exclude_unset=True), request.user_id)
    except PlanNotExecutableError as exc:
        raise HTTPException(status_code=409, detail=exc.detail) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return OrderResponse(**save_order(order))


@router.get("")
def get_orders() -> dict:
    orders = list_orders()
    return {"items": orders, "total": len(orders)}


@router.get("/{order_id}", response_model=OrderResponse)
def get_order_detail(order_id: str) -> OrderResponse:
    order = get_order(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return OrderResponse(**order)
