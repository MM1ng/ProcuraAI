from __future__ import annotations

from app.decision.base import DecisionProvider
from app.decision.providers.baseline import BaselineIntentProvider


def get_provider(name: str) -> DecisionProvider:
    if name.strip().lower() == "baseline":
        return BaselineIntentProvider()
    raise ValueError(f"Unknown decision provider: {name}")
