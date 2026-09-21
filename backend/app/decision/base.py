from __future__ import annotations

from typing import Any, Protocol

from app.decision.schemas import DecisionResult


class DecisionProvider(Protocol):
    """Minimal interface for an offline benchmark provider."""

    name: str

    def classify_intent(self, text: str, context: dict[str, Any] | None = None) -> DecisionResult: ...
