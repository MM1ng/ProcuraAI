from __future__ import annotations

from fastapi import APIRouter

from app.evaluation import agent_eval_runner
from app.evaluation.mock_eval_runner import run_mock_evaluation
from app.schemas.evaluation import EvaluationRunResponse, EvaluationSummaryResponse
from app.services.dashboard_service import evaluation_summary


router = APIRouter(prefix="/api/evaluation", tags=["evaluation"])


@router.get("/summary", response_model=EvaluationSummaryResponse)
def get_evaluation_summary() -> EvaluationSummaryResponse:
    return EvaluationSummaryResponse(**evaluation_summary())


@router.post("/run-mock", response_model=EvaluationRunResponse)
def run_mock() -> EvaluationRunResponse:
    rows = run_mock_evaluation()
    return EvaluationRunResponse(status="completed", generated_rows=len(rows))


@router.post("/run-agent", response_model=EvaluationRunResponse)
def run_agent() -> EvaluationRunResponse:
    rows = agent_eval_runner.run_agent_evaluation()
    return EvaluationRunResponse(status="completed", generated_rows=len(rows))
