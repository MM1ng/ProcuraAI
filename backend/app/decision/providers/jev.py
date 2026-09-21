from __future__ import annotations

import importlib.metadata
import os
from time import perf_counter
from typing import Any

from app.decision.base import DecisionProviderPredictionError, DecisionProviderUnavailableError
from app.decision.schemas import DecisionResult, IntentLabel
from app.decision.tasks.intent import INTENT_DEFINITIONS, INTENT_INSTRUCTIONS


class JevProvider:
    """Optional TypeSafe Jev SDK adapter; never falls back to Baseline."""

    name = "jev"

    def __init__(self) -> None:
        self._request_count = 0
        self._input_chars = 0

    @staticmethod
    def _configured_model() -> str | None:
        return os.getenv("JEV_MODEL") or os.getenv("TYPESAFE_DEFAULT_MODEL") or None

    @staticmethod
    def _timeout_seconds() -> float:
        try:
            return float(os.getenv("JEV_TIMEOUT_SECONDS", "10"))
        except ValueError:
            return 10.0

    @staticmethod
    def _sdk() -> tuple[Any, Any]:
        try:
            from typesafe_sdk import Choice, TypeSafeClient
        except ImportError as exc:
            raise DecisionProviderUnavailableError(
                "Jev provider unavailable: typesafe-sdk is not installed."
            ) from exc
        return Choice, TypeSafeClient

    def classify_intent(self, text: str, context: dict[str, Any] | None = None) -> DecisionResult:
        if not os.getenv("TYPESAFE_API_KEY"):
            raise DecisionProviderUnavailableError(
                "Jev provider unavailable: TYPESAFE_API_KEY is not configured."
            )
        Choice, TypeSafeClient = self._sdk()
        self._request_count += 1
        self._input_chars += len(text)
        started = perf_counter()
        try:
            question = Choice(instructions=INTENT_INSTRUCTIONS, criteria=INTENT_DEFINITIONS)
            with TypeSafeClient(model=self._configured_model(), timeout=self._timeout_seconds()) as client:
                response = client.system_one(
                    state={"message": text, "context": context or {}}, questions={"intent": question}
                )
            answer = response.choices["intent"]
            label = IntentLabel(getattr(answer, "choice", None))
        except ValueError as exc:
            raise DecisionProviderPredictionError("Jev provider returned an invalid intent label.") from exc
        except DecisionProviderUnavailableError:
            raise
        except Exception as exc:
            raise DecisionProviderPredictionError(f"Jev provider prediction failed: {type(exc).__name__}") from exc
        try:
            request_id = response.request_id
        except Exception:
            request_id = None
        metadata = {
            "request_id": request_id,
            "input_chars": len(text),
        }
        return DecisionResult(
            label=label, confidence=getattr(answer, "confidence", None),
            probabilities=getattr(answer, "probabilities", None), provider=self.name,
            model=getattr(response, "model", None) or self._configured_model(),
            latency_ms=(perf_counter() - started) * 1000, metadata=metadata,
        )

    def runtime_metadata(self) -> dict[str, Any]:
        try:
            sdk_version = importlib.metadata.version("typesafe-sdk")
        except importlib.metadata.PackageNotFoundError:
            sdk_version = None
        return {
            "provider": self.name, "model": self._configured_model(), "remote": True,
            "device": None, "sdk_version": sdk_version, "request_count": self._request_count,
            "input_chars": self._input_chars, "cost": None,
        }
