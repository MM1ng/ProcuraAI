from __future__ import annotations

import importlib.metadata
import os
from time import perf_counter
from typing import Any

from app.decision.base import DecisionProviderPredictionError, DecisionProviderUnavailableError
from app.decision.schemas import DecisionResult, IntentLabel
from app.decision.tasks.intent import INTENT_DEFINITIONS, INTENT_INSTRUCTIONS


class VonProvider:
    """Optional local Von adapter; model loading is owned by the official SDK."""

    name = "von"

    def __init__(self) -> None:
        self._request_count = 0
        self._input_chars = 0

    @staticmethod
    def _sdk() -> Any:
        try:
            import von
        except ImportError as exc:
            raise DecisionProviderUnavailableError("Von provider unavailable: von-sdk is not installed.") from exc
        return von

    def classify_intent(self, text: str, context: dict[str, Any] | None = None) -> DecisionResult:
        if os.getenv("VON_ENABLED", "").strip().lower() not in {"1", "true", "yes", "on"}:
            raise DecisionProviderUnavailableError("Von provider unavailable: VON_ENABLED is not true.")
        von = self._sdk()
        self._request_count += 1
        self._input_chars += len(text)
        started = perf_counter()
        try:
            response = von.decide(
                state={"message": text, "context": context or {}},
                choices=INTENT_DEFINITIONS,
                instructions=INTENT_INSTRUCTIONS,
            )
            label = IntentLabel(getattr(response, "choice", None))
        except ValueError as exc:
            raise DecisionProviderPredictionError("Von provider returned an invalid intent label.") from exc
        except DecisionProviderUnavailableError:
            raise
        except Exception as exc:
            raise DecisionProviderPredictionError(f"Von provider prediction failed: {type(exc).__name__}") from exc
        return DecisionResult(
            label=label, confidence=getattr(response, "confidence", None),
            probabilities=getattr(response, "probabilities", None), provider=self.name,
            model=getattr(response, "model", None) or os.getenv("VON_MODEL") or None,
            latency_ms=(perf_counter() - started) * 1000,
            metadata={"device": getattr(response, "device", None), "input_chars": len(text)},
        )

    def runtime_metadata(self) -> dict[str, Any]:
        try:
            sdk_version = importlib.metadata.version("von-sdk")
        except importlib.metadata.PackageNotFoundError:
            sdk_version = None
        return {
            "provider": self.name, "model": os.getenv("VON_MODEL") or None, "remote": False,
            "device": None, "sdk_version": sdk_version, "request_count": self._request_count,
            "input_chars": self._input_chars, "cost": None,
        }
