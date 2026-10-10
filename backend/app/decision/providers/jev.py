from __future__ import annotations

import importlib.metadata
import os
import threading
from time import perf_counter
from typing import Any

import httpx2

from app.decision.base import DecisionProviderPredictionError, DecisionProviderUnavailableError
from app.decision.schemas import DecisionResult, IntentLabel
from app.decision.tasks.intent import INTENT_DEFINITIONS, INTENT_INSTRUCTIONS


class _CountingHTTPClient(httpx2.Client):
    """Count actual SDK HTTP attempts without changing its retry policy."""

    def __init__(self, *, timeout: float) -> None:
        super().__init__(timeout=timeout)
        self.request_count = 0
        self._request_count_lock = threading.Lock()

    def request(self, *args: Any, **kwargs: Any) -> httpx2.Response:
        with self._request_count_lock:
            self.request_count += 1
        return super().request(*args, **kwargs)


class JevProvider:
    """Optional TypeSafe Jev SDK adapter; never falls back to Baseline."""

    name = "jev"

    def __init__(self, *, timeout_seconds: float | None = None, max_retries: int | None = None) -> None:
        self._request_count = 0
        self._input_chars = 0
        self._timeout_seconds_override = timeout_seconds
        self._max_retries_override = max_retries
        self._last_call_metrics: dict[str, Any] = {
            "provider_call_elapsed_ms": None,
            "provider_retry_count": None,
            "provider_final_error_type": None,
        }

    @property
    def last_call_metrics(self) -> dict[str, Any]:
        return dict(self._last_call_metrics)

    def _record_call_metrics(
        self,
        started: float,
        http_client: _CountingHTTPClient | None,
        error: BaseException | None,
    ) -> float:
        elapsed_ms = (perf_counter() - started) * 1000
        attempts = http_client.request_count if http_client is not None else 0
        self._last_call_metrics = {
            "provider_call_elapsed_ms": elapsed_ms,
            "provider_retry_count": max(attempts - 1, 0),
            "provider_final_error_type": type(error).__name__ if error is not None else None,
        }
        return elapsed_ms

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
    def _sdk() -> tuple[Any, Any, Any]:
        try:
            from typesafe_sdk import Choice, RetryPolicy, TypeSafeClient
        except ImportError as exc:
            raise DecisionProviderUnavailableError(
                "Jev provider unavailable: typesafe-sdk is not installed."
            ) from exc
        return Choice, TypeSafeClient, RetryPolicy

    def classify_intent(self, text: str, context: dict[str, Any] | None = None) -> DecisionResult:
        started = perf_counter()
        http_client: _CountingHTTPClient | None = None
        try:
            if not os.getenv("TYPESAFE_API_KEY"):
                raise DecisionProviderUnavailableError(
                    "Jev provider unavailable: TYPESAFE_API_KEY is not configured."
                )
            Choice, TypeSafeClient, RetryPolicy = self._sdk()
            self._request_count += 1
            self._input_chars += len(text)
            question = Choice(instructions=INTENT_INSTRUCTIONS, criteria=INTENT_DEFINITIONS)
            timeout_seconds = self._timeout_seconds_override or self._timeout_seconds()
            http_client = _CountingHTTPClient(timeout=timeout_seconds)
            client_options: dict[str, Any] = {
                "model": self._configured_model(),
                "timeout": timeout_seconds,
                "http_client": http_client,
            }
            if self._max_retries_override is not None:
                client_options["retry"] = RetryPolicy(
                    max_retries=max(self._max_retries_override, 0),
                    timeout=timeout_seconds,
                )
            with TypeSafeClient(**client_options) as client:
                response = client.system_one(
                    state={"message": text, "context": context or {}}, questions={"intent": question}
                )
            answer = response.choices["intent"]
            label = IntentLabel(getattr(answer, "choice", None))
        except ValueError as exc:
            self._record_call_metrics(started, http_client, exc)
            raise DecisionProviderPredictionError("Jev provider returned an invalid intent label.") from exc
        except DecisionProviderUnavailableError as exc:
            self._record_call_metrics(started, http_client, exc)
            raise
        except Exception as exc:
            self._record_call_metrics(started, http_client, exc)
            raise DecisionProviderPredictionError(f"Jev provider prediction failed: {type(exc).__name__}") from exc
        try:
            request_id = response.request_id
        except Exception:
            request_id = None
        metadata = {
            "request_id": request_id,
            "input_chars": len(text),
        }
        elapsed_ms = self._record_call_metrics(started, http_client, None)
        return DecisionResult(
            label=label, confidence=getattr(answer, "confidence", None),
            probabilities=getattr(answer, "probabilities", None), provider=self.name,
            model=getattr(response, "model", None) or self._configured_model(),
            latency_ms=elapsed_ms,
            metadata={
                **metadata,
                "provider_call_elapsed_ms": elapsed_ms,
                "provider_retry_count": self._last_call_metrics["provider_retry_count"],
            },
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
