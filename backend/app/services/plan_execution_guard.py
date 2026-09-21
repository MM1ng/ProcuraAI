from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class PlanExecutionResult(BaseModel):
    executable: bool
    blocking_reasons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class PlanNotExecutableError(ValueError):
    def __init__(self, result: PlanExecutionResult):
        self.result = result
        super().__init__("Plan is not executable: " + ", ".join(result.blocking_reasons))

    @property
    def detail(self) -> dict[str, Any]:
        return {"code": "PLAN_NOT_EXECUTABLE", **self.result.model_dump()}


class PlanExecutionGuard:
    """Evaluate existing plan evidence without inventory mutation or provider calls."""

    @staticmethod
    def evaluate(plan: dict[str, Any]) -> PlanExecutionResult:
        reasons: list[str] = []
        if plan.get("over_budget") is True or plan.get("budget_status") == "over_budget":
            reasons.append("over_budget")
        if plan.get("inventory_status") != "valid":
            reasons.append("insufficient_stock")
        if plan.get("missing_categories"):
            reasons.append("missing_categories")
        if plan.get("constraint_satisfaction") != "satisfied":
            reasons.append("hard_constraints_failed")
        if plan.get("constraints_relaxed") is True:
            reasons.append("retrieval_constraints_relaxed")
        # Preserve an existing explicit restriction; True is never authorization.
        if plan.get("selectable") is False:
            reasons.append("not_selectable")
        return PlanExecutionResult(executable=not reasons, blocking_reasons=reasons)

    @staticmethod
    def require_executable(plan: dict[str, Any]) -> PlanExecutionResult:
        result = PlanExecutionGuard.evaluate(plan)
        if not result.executable:
            raise PlanNotExecutableError(result)
        return result
