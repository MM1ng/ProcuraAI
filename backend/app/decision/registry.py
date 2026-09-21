from __future__ import annotations

from app.decision.base import DecisionProvider
from app.decision.providers.baseline import BaselineIntentProvider
from app.decision.providers.jev import JevProvider
from app.decision.providers.von import VonProvider


def get_provider(name: str) -> DecisionProvider:
    if name.strip().lower() == "baseline":
        return BaselineIntentProvider()
    if name.strip().lower() == "jev":
        return JevProvider()
    if name.strip().lower() == "von":
        return VonProvider()
    raise ValueError(f"Unknown decision provider: {name}")
