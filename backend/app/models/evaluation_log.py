from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class EvaluationLog(Base):
    __tablename__ = "evaluation_logs"

    log_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    question: Mapped[str] = mapped_column(Text)
    answer: Mapped[str] = mapped_column(Text)
    contexts: Mapped[str] = mapped_column(Text)
    context_precision: Mapped[float] = mapped_column(Float)
    context_recall: Mapped[float] = mapped_column(Float)
    faithfulness: Mapped[float] = mapped_column(Float)
    answer_relevance: Mapped[float] = mapped_column(Float)
    budget_compliance: Mapped[bool] = mapped_column(Boolean)
    inventory_validity: Mapped[bool] = mapped_column(Boolean)
    constraint_satisfaction: Mapped[bool] = mapped_column(Boolean)
    latency_ms: Mapped[float] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
