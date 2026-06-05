from __future__ import annotations

from pydantic import BaseModel


class EvaluationRunResponse(BaseModel):
    status: str
    generated_rows: int


class EvaluationSummaryResponse(BaseModel):
    context_precision: float
    context_recall: float
    faithfulness: float
    answer_relevance: float
    budget_compliance_rate: float
    inventory_validity_rate: float
    constraint_satisfaction_rate: float
    purchase_completion_rate: float
    average_latency: float
    results: list[dict]
