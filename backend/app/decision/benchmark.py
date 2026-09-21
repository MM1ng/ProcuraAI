from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from app.core.config import DATA_DIR
from app.decision.metrics import calculate_metrics
from app.decision.registry import get_provider
from app.decision.schemas import IntentGoldCase


GOLD_SET_PATH = Path(__file__).resolve().parents[2] / "evaluation" / "decision" / "intent_gold.jsonl"
RESULTS_DIR = DATA_DIR / "decision_eval" / "results"


def load_intent_gold_set(path: Path = GOLD_SET_PATH) -> list[IntentGoldCase]:
    with path.open(encoding="utf-8") as handle:
        return [IntentGoldCase.model_validate_json(line) for line in handle if line.strip()]


def run_intent_benchmark(provider_name: str, dataset_path: Path = GOLD_SET_PATH) -> dict[str, Any]:
    provider, cases = get_provider(provider_name), load_intent_gold_set(dataset_path)
    results = [provider.classify_intent(case.text, case.context) for case in cases]
    metrics = calculate_metrics(
        [case.label.value for case in cases], [result.label.value for result in results],
        [result.latency_ms for result in results],
    )
    return {"task": "intent", "provider": provider.name, "dataset_size": len(cases), **metrics}


def write_result(result: dict[str, Any], output_dir: Path = RESULTS_DIR) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{result['provider']}_{result['task']}.json"
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Run an offline ProcuraAI decision benchmark.")
    parser.add_argument("--task", choices=["intent"], required=True)
    parser.add_argument("--provider", required=True)
    parser.add_argument("--dataset", type=Path, default=GOLD_SET_PATH)
    parser.add_argument("--output-dir", type=Path, default=RESULTS_DIR)
    args = parser.parse_args()
    result = run_intent_benchmark(args.provider, args.dataset)
    path = write_result(result, args.output_dir)
    print(json.dumps({**result, "output_path": str(path)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
