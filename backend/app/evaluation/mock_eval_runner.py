from __future__ import annotations

import csv
import json
import random
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core.config import DATA_DIR
from app.evaluation.business_metrics import average, calculate_business_metrics


EVAL_FILE = DATA_DIR / "evaluation_logs.json"
QUESTIONS_FILE = DATA_DIR / "evaluation_questions.csv"


DEFAULT_QUESTIONS = [
    "We need keyboards, mice and headsets for 20 interns under $3000.",
    "Recommend webcams and headsets for a remote team of 10 people.",
    "Find docking stations with rating above 4.3 and delivery within 5 days.",
    "Make the plan cheaper while keeping rating above 4.2.",
    "Replace the headset with a lower cost model delivered within 5 days.",
]


def _read_questions() -> list[str]:
    if not QUESTIONS_FILE.exists():
        return DEFAULT_QUESTIONS
    with QUESTIONS_FILE.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        return [row["question"] for row in reader if row.get("question")]


def _read_rows() -> list[dict[str, Any]]:
    if not EVAL_FILE.exists():
        return []
    return json.loads(EVAL_FILE.read_text(encoding="utf-8"))


def run_mock_evaluation() -> list[dict[str, Any]]:
    random.seed(42)
    rows: list[dict[str, Any]] = []
    for index, question in enumerate(_read_questions(), start=1):
        rows.append(
            {
                "log_id": index,
                "question": question,
                "answer": "The agent produced a procurement plan with retrieved product contexts.",
                "contexts": [
                    "Product catalog context with price, rating, stock, supplier and delivery information."
                ],
                "context_precision": round(random.uniform(0.78, 0.94), 3),
                "context_recall": round(random.uniform(0.75, 0.92), 3),
                "faithfulness": round(random.uniform(0.8, 0.95), 3),
                "answer_relevance": round(random.uniform(0.82, 0.96), 3),
                "budget_compliance": index != 4,
                "inventory_validity": True,
                "constraint_satisfaction": index != 5,
                "latency_ms": round(random.uniform(280, 920), 2),
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        )
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    EVAL_FILE.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    return rows


def summarize_evaluations() -> dict[str, Any]:
    rows = _read_rows()
    if not rows:
        rows = run_mock_evaluation()
    business = calculate_business_metrics(rows)
    return {
        "context_precision": average(rows, "context_precision"),
        "context_recall": average(rows, "context_recall"),
        "faithfulness": average(rows, "faithfulness"),
        "answer_relevance": average(rows, "answer_relevance"),
        "average_latency": average(rows, "latency_ms"),
        "results": rows,
        **business,
    }
