from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services import history_service


router = APIRouter(prefix="/api/history", tags=["history"])


class HistoryCreateRequest(BaseModel):
    original_request: str = ""
    parsed_intent: dict[str, Any] | None = None
    agent_understanding: dict[str, Any] | None = None
    selected_plan: dict[str, Any] | None = None
    procurement_plan: dict[str, Any] | None = None
    trace: dict[str, Any] = Field(default_factory=dict)
    reasoning_summary: str = ""
    messages: list[dict[str, Any]] = Field(default_factory=list)
    order_draft: dict[str, Any] | None = None


@router.get("")
def get_history() -> dict[str, Any]:
    records = history_service.list_history_records()
    return {"items": records, "total": len(records)}


@router.post("")
def save_history(request: HistoryCreateRequest) -> dict[str, Any]:
    return history_service.create_history_record(request.model_dump())


@router.get("/{history_id}")
def get_history_detail(history_id: str) -> dict[str, Any]:
    record = history_service.get_history_record(history_id)
    if not record:
        raise HTTPException(status_code=404, detail="History record not found")
    return record


@router.delete("/{history_id}")
def delete_history(history_id: str) -> dict[str, Any]:
    deleted = history_service.delete_history_record(history_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="History record not found")
    return {"deleted": True, "id": history_id}
