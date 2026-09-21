"""Offline-only decision benchmark primitives.

This package is deliberately not imported by the production procurement flow.
"""

from app.decision.schemas import DecisionResult, IntentLabel

__all__ = ["DecisionResult", "IntentLabel"]
