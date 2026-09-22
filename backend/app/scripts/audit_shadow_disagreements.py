"""Join safe Shadow observation records with DEV truth without any API calls."""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Sequence

from app.scripts.run_shadow_observation import DEV_DATASET, DEFAULT_RECORDS_PATH, load_records


TRANSACTION_LABELS = {"confirm_order", "payment"}
DEFAULT_OUTPUT_PATH = Path(__file__).with_name("shadow_observation_disagreement_audit.json")


def load_truth(dataset_path: Path = DEV_DATASET) -> dict[str, str]:
    return {
        str(row["id"]): str(row["label"])
        for row in (json.loads(line) for line in dataset_path.read_text(encoding="utf-8").splitlines() if line.strip())
    }


def _case_view(record: dict[str, Any], truth_label: str) -> dict[str, Any]:
    return {
        "case_id": record["case_id"], "truth_label": truth_label,
        "router_label": record.get("authoritative_label"), "shadow_label": record.get("shadow_label"),
    }


def audit_records(records: Sequence[dict[str, Any]], truth_by_case: dict[str, str]) -> dict[str, Any]:
    successful = [record for record in records if record.get("provider_success") is True]
    escalations = [record for record in successful if record.get("transaction_escalation_disagreement") is True]
    deescalations = [record for record in successful if record.get("transaction_deescalation_disagreement") is True]
    disagreements = [record for record in successful if record.get("agreement") is False]
    cross_table: Counter[str] = Counter()
    deescalation_cross_table: Counter[str] = Counter()
    for record in disagreements:
        truth = truth_by_case[str(record["case_id"])]
        cross_table[f"{record.get('shadow_label')} x {truth}"] += 1
    for record in deescalations:
        truth = truth_by_case[str(record["case_id"])]
        deescalation_cross_table[f"{record.get('shadow_label')} x {truth}"] += 1

    escalation_cases = []
    counts = Counter()
    upgrade_vs_truth_count = 0
    for record in escalations:
        truth = truth_by_case[str(record["case_id"])]
        shadow = str(record.get("shadow_label") or "")
        router = str(record.get("authoritative_label") or "")
        if shadow == truth:
            classification = "jev_equals_truth_router_miss"
        elif router == truth:
            classification = "router_equals_truth_jev_genuine_upgrade"
        else:
            classification = "jev_not_truth_manual_review"
        if shadow in TRANSACTION_LABELS and truth not in TRANSACTION_LABELS:
            upgrade_vs_truth_count += 1
        counts[classification] += 1
        escalation_cases.append({**_case_view(record, truth), "classification": classification})

    return {
        "successful_record_count": len(successful),
        "escalation_cases": escalation_cases,
        "escalation_classification_counts": dict(sorted(counts.items())),
        "deescalation_cases": [_case_view(record, truth_by_case[str(record["case_id"])]) for record in deescalations],
        "deescalation_count": len(deescalations),
        "deescalation_shadow_x_truth_cross_table": dict(sorted(deescalation_cross_table.items())),
        "disagreement_shadow_x_truth_cross_table": dict(sorted(cross_table.items())),
        "jev_transaction_upgrade_vs_truth_count": upgrade_vs_truth_count,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit D03.3R Shadow disagreements against DEV truth.")
    parser.add_argument("--records-path", type=Path, default=DEFAULT_RECORDS_PATH)
    parser.add_argument("--dataset-path", type=Path, default=DEV_DATASET)
    parser.add_argument("--output-path", type=Path, default=DEFAULT_OUTPUT_PATH)
    args = parser.parse_args()
    report = audit_records(load_records(args.records_path), load_truth(args.dataset_path))
    args.output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
