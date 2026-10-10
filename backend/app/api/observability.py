from __future__ import annotations

from fastapi import APIRouter, Header, Query, Response

from app.services.dashboard_service import observability_summary, observability_traces
from app.services.debug_access import require_traces_admin


router = APIRouter(prefix="/api/observability", tags=["observability"])


@router.get("/summary")
def get_observability_summary() -> dict:
    return observability_summary()


@router.get("/traces")
def get_observability_traces(
    response: Response,
    limit: int = Query(default=50, ge=1, le=200),
    x_observability_token: str | None = Header(default=None),
) -> dict:
    require_traces_admin(x_observability_token)
    response.headers["Cache-Control"] = "no-store"
    traces = observability_traces(limit=limit)
    return {"items": traces, "total": len(traces)}
