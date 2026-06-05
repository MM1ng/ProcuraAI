from __future__ import annotations

from fastapi import APIRouter, Query

from app.services.dashboard_service import observability_summary, observability_traces


router = APIRouter(prefix="/api/observability", tags=["observability"])


@router.get("/summary")
def get_observability_summary() -> dict:
    return observability_summary()


@router.get("/traces")
def get_observability_traces(limit: int = Query(default=50, ge=1, le=200)) -> dict:
    traces = observability_traces(limit=limit)
    return {"items": traces, "total": len(traces)}
