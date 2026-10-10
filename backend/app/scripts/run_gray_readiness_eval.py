"""Provisional, isolated real-agent Shadow evidence; never enables authority.

Run from backend with the existing interpreter:
  python -m app.scripts.run_gray_readiness_eval
Outputs a new directory under artifacts; existing reports are never replaced.
The frozen labels are NOT human adjudicated and cannot authorize a rollout.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import math
import os
import runpy
import subprocess
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from app.decision.gateway import ShadowConfig
from app.scripts.run_shadow_observation import PROJECT_ROOT, ReplayCase, ShadowObservationRunner


DATASETS = {name: PROJECT_ROOT / "backend" / "evaluation" / "decision" / f"intent_{name}.jsonl"
            for name in ("dev", "test", "hard")}
SAFETY_SOURCE = PROJECT_ROOT / "backend" / "tests" / "test_transaction_safety_matrix.py"
TRANSACTION_LABELS = {"confirm_order", "payment", "cancel"}
# Candidate gold problems; only a human adjudicator can resolve these.
UNCERTAIN = {
    "dev/payment-008": "how-to payment question labeled as executable payment",
    "test/test-stat-03": "delivery question without an order reference or context",
    "test/test-stat-10": "purchase update could mean plan modification or order status",
}


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return round(ordered[max(math.ceil(len(ordered) * fraction) - 1, 0)], 2)


def _scores(rows: list[dict], prediction: str, labels: list[str]) -> dict:
    output = {}
    for label in labels:
        support = sum(row["gold"] == label for row in rows)
        predicted = sum(row.get(prediction) == label for row in rows)
        true_positive = sum(row["gold"] == label and row.get(prediction) == label for row in rows)
        precision = true_positive / predicted if predicted else None
        recall = true_positive / support if support else None
        f1 = 2 * true_positive / (support + predicted) if support + predicted else None
        output[label] = {
            "support": support, "predicted": predicted, "true_positive": true_positive,
            "precision": round(precision, 4) if precision is not None else None,
            "recall": round(recall, 4) if recall is not None else None,
            "f1": round(f1, 4) if f1 is not None else None,
        }
    f1_values = [value["f1"] for value in output.values() if value["support"]]
    return {"per_class": output, "macro_f1": round(sum(f1_values) / len(f1_values), 4) if f1_values else None}


def _load_dataset(path: Path, name: str) -> list[dict]:
    cases = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if len({row["id"] for row in cases}) != len(cases):
        raise ValueError(f"duplicate case id in {name}")
    if len({row["text"].strip().casefold() for row in cases}) != len(cases):
        raise ValueError(f"duplicate text in {name}")
    return cases


def _summarize(name: str, cases: list[dict], records: list[dict]) -> tuple[dict, list[dict], list[dict]]:
    by_id = {row["case_id"]: row for row in records}
    joined, disputed = [], []
    for case in cases:
        record = by_id.get(case["id"], {})
        key = f"{name}/{case['id']}"
        gold = case["label"]
        baseline = record.get("authoritative_label")
        jev = record.get("shadow_label") if record.get("provider_success") is True else None
        row = {
            "case_id": key, "gold": gold, "baseline": baseline, "jev": jev,
            "provider_success": record.get("provider_success"),
            "gold_status": "needs_human_review" if key in UNCERTAIN else "provisional_unreviewed",
            "gold_issue": UNCERTAIN.get(key),
            "response_type": record.get("response_type"),
            "baseline_model_provider": record.get("baseline_model_provider"),
            "baseline_model_name": record.get("baseline_model_name"),
            "baseline_used_mock_llm": record.get("baseline_used_mock_llm"),
            "baseline_llm_error_present": record.get("baseline_llm_error_present"),
            "transaction_gate": record.get("transaction_gate"),
            "decision_source": record.get("decision_source"),
            "fallback_used": record.get("fallback_used"),
            "order_created": record.get("order_created", False),
            "checkout_created": record.get("checkout_created", False),
            "provider_error_type": record.get("provider_error_type"),
            "provider_call_elapsed_ms": record.get("provider_call_elapsed_ms"),
        }
        if key in UNCERTAIN:
            row["attribution"] = "gold_uncertain"
        elif jev is None:
            row["attribution"] = "provider_failure_or_missing_record"
        elif jev == baseline:
            row["attribution"] = "agreement"
        elif jev == gold:
            row["attribution"] = "baseline_error_provisional"
        elif baseline == gold:
            row["attribution"] = "jev_error_provisional"
        else:
            row["attribution"] = "both_differ_from_gold_provisional"
        joined.append(row)
        if jev != baseline or key in UNCERTAIN:
            disputed.append(row)

    # Excluding known questionable rows prevents them from proving a lift;
    # remaining frozen labels are still provisional until human sign-off.
    scored = [row for row in joined if row["case_id"] not in UNCERTAIN]
    labels = sorted({case["label"] for case in cases})
    successes = [row for row in joined if row["provider_success"] is True]
    latencies = [float(row["provider_call_elapsed_ms"]) for row in joined
                 if row["provider_call_elapsed_ms"] is not None]
    errors = Counter(str(row["provider_error_type"] or "unknown") for row in joined
                     if row["provider_success"] is False)
    summary = {
        "dataset": name, "sample_count": len(cases), "scored_provisionally": len(scored),
        "known_gold_uncertain": len(cases) - len(scored),
        "human_adjudication_complete": False,
        "provider_success": len(successes), "provider_failures": sum(row["provider_success"] is False for row in joined),
        "provider_error_types": dict(errors),
        "baseline": _scores(scored, "baseline", labels),
        "baseline_mock_fallback_count": sum(row["baseline_used_mock_llm"] is True for row in joined),
        "baseline_llm_error_count": sum(row["baseline_llm_error_present"] is True for row in joined),
        "baseline_models_observed": sorted({str(row["baseline_model_name"]) for row in joined if row["baseline_model_name"]}),
        "jev": _scores(scored, "jev", labels),
        "agreement_with_real_agent": {
            "count": sum(row["jev"] == row["baseline"] for row in successes),
            "denominator": len(successes),
        },
        "jev_transaction_escalations_against_gold": sum(
            row["gold"] not in TRANSACTION_LABELS and row["jev"] in TRANSACTION_LABELS for row in scored
        ),
        "order_side_effects": sum(row["order_created"] for row in joined),
        "checkout_side_effects": sum(row["checkout_created"] for row in joined),
        "baseline_fallback_count": sum(row["fallback_used"] is True for row in joined),
        "latency_ms": {f"p{p}": _percentile(latencies, p / 100) for p in (50, 95, 99)},
    }
    return summary, joined, disputed


def main() -> None:
    parser = argparse.ArgumentParser(description="Isolated, provisional real-agent Jev Shadow replay")
    parser.add_argument("--safety-only", action="store_true", help="Recheck just the transaction matrix")
    args = parser.parse_args()
    if os.getenv("JEV_DECISION_TRAFFIC_PERCENT", "0").strip() not in {"", "0", "0.0"}:
        raise SystemExit("Refusing replay: authority traffic percent must be 0")
    if not (PROJECT_ROOT / "data" / "orders.json").exists() or not (PROJECT_ROOT / "data" / "observability_logs.json").exists():
        raise SystemExit("Expected production artifacts missing; refusing replay")
    code_paths = [PROJECT_ROOT / "backend" / path for path in (
        "app/scripts/run_gray_readiness_eval.py", "app/scripts/run_shadow_observation.py",
        "app/decision/tasks/intent.py", "app/decision/providers/jev.py",
        "app/decision/contracts.py", "app/decision/gateway.py",
        "app/agent/router.py", "app/agent/procurement_agent.py", "app/core/config.py",
    )]
    code_hashes_at_start = {str(path.relative_to(PROJECT_ROOT)): _sha(path) for path in code_paths}
    git_head_at_start = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=PROJECT_ROOT, text=True).strip()
    matrix = runpy.run_path(str(SAFETY_SOURCE))
    sources = {name: _load_dataset(path, name) for name, path in DATASETS.items()}
    all_texts = [case["text"].strip().casefold() for cases in sources.values() for case in cases]
    if len(all_texts) != len(set(all_texts)):
        raise SystemExit("Cross-dataset duplicate text; refusing aggregate claims")
    safety = [
        {"id": f"negative-{i:03d}", "text": text, "label": "non_transaction"}
        for i, text in enumerate(matrix["SAFETY_NEGATIVES"], 1)
    ] + [
        {"id": f"explicit-{i:03d}", "text": text, "label": label}
        for i, (label, text) in enumerate(matrix["EXPLICIT_TRANSACTIONS"], 1)
    ]
    sources["safety"] = safety
    source_counts = {name: len(cases) for name, cases in sources.items()}
    if args.safety_only:
        sources = {"safety": safety}
    config = ShadowConfig(enabled=True, timeout_ms=4000, sample_rate=1.0,
                          log_probabilities=False, max_in_flight=2)
    runner = ShadowObservationRunner(config=config, audit_forward=lambda _record: None)
    summaries, joined, disputes, harness, safety_records = {}, [], [], {}, []
    for name, cases in sources.items():
        result = runner.run_cases([ReplayCase(case_id=case["id"], text=case["text"]) for case in cases])
        if result.harness_errors or not result.production_orders_unchanged or not result.production_observability_unchanged:
            raise RuntimeError(f"Replay integrity failure in {name}: {result.harness_errors}")
        if name == "safety":
            by_id = {row["case_id"]: row for row in result.records}
            negatives = safety[:len(matrix["SAFETY_NEGATIVES"])]
            explicit = safety[len(negatives):]
            safety_records = [
                {"case_id": case["id"], "gold": case["label"], **by_id[case["id"]]}
                for case in safety
            ]
            safety_scored = []
            for case in safety:
                record = by_id[case["id"]]
                baseline = record.get("authoritative_label")
                jev = record.get("shadow_label") if record.get("provider_success") is True else None
                safety_scored.append({
                    "gold": case["label"],
                    "baseline": baseline if baseline in TRANSACTION_LABELS else "non_transaction",
                    "jev": jev if jev in TRANSACTION_LABELS else "non_transaction" if jev else None,
                })
            summaries[name] = {
                "sample_count": len(safety), "negative_count": len(negatives),
                "explicit_count": len(safety) - len(negatives),
                "negative_jev_transaction_escalations": sum(
                    by_id[case["id"]].get("shadow_label") in TRANSACTION_LABELS
                    for case in negatives if by_id[case["id"]].get("provider_success") is True
                ),
                "negative_provider_failures": sum(by_id[case["id"]].get("provider_success") is False for case in negatives),
                "explicit_provider_failures": sum(by_id[case["id"]].get("provider_success") is False for case in explicit),
                "explicit_jev_correct": sum(
                    by_id[case["id"]].get("provider_success") is True
                    and by_id[case["id"]].get("shadow_label") == case["label"] for case in explicit
                ),
                "explicit_baseline_correct": sum(
                    by_id[case["id"]].get("authoritative_label") == case["label"] for case in explicit
                ),
                "jev": _scores(safety_scored, "jev", ["non_transaction", "confirm_order", "payment", "cancel"]),
                "baseline": _scores(safety_scored, "baseline", ["non_transaction", "confirm_order", "payment", "cancel"]),
                "order_side_effects": sum(row.get("order_created") is True for row in result.records),
                "checkout_side_effects": sum(row.get("checkout_created") is True for row in result.records),
                "provider_failures": sum(row.get("provider_success") is False for row in result.records),
                "baseline_mock_fallback_count": sum(row.get("baseline_used_mock_llm") is True for row in result.records),
                "baseline_llm_error_count": sum(row.get("baseline_llm_error_present") is True for row in result.records),
                "baseline_models_observed": sorted({str(row.get("baseline_model_name")) for row in result.records if row.get("baseline_model_name")}),
                "latency_ms": {f"p{p}": _percentile([
                    float(row["provider_call_elapsed_ms"]) for row in result.records
                    if row.get("provider_call_elapsed_ms") is not None
                ], p / 100) for p in (50, 95, 99)},
            }
        else:
            summaries[name], rows, disagreement_rows = _summarize(name, cases, result.records)
            joined.extend(rows)
            disputes.extend(disagreement_rows)
        harness[name] = {"requests": result.candidate_requests,
                         "records": len(result.records), "harness_errors": result.harness_errors,
                         "production_orders_unchanged": result.production_orders_unchanged,
                         "production_observability_unchanged": result.production_observability_unchanged}

    source_hashes = {name: {"path": str(path), "sample_count": source_counts[name], "sha256": _sha(path)}
                     for name, path in DATASETS.items()}
    source_hashes["safety"] = {"path": str(SAFETY_SOURCE), "sample_count": len(safety),
                               "sha256": _sha(SAFETY_SOURCE)}
    try:
        sdk_version = importlib.metadata.version("typesafe-sdk")
    except importlib.metadata.PackageNotFoundError:
        sdk_version = None
    if any(_sha(path) != code_hashes_at_start[str(path.relative_to(PROJECT_ROOT))] for path in code_paths):
        raise RuntimeError("Source changed during replay; refusing to issue a provenance report")
    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "git_head": git_head_at_start,
        "code_sha256": code_hashes_at_start,
        "source_commit": "3e10a2225fe02459d6e1857b0e33d50b6eabacee",
        "source_provenance": "repository test fixture; no independent human gold adjudication found",
        "dataset_sources": source_hashes,
        "model": {"configured": os.getenv("JEV_MODEL") or os.getenv("TYPESAFE_DEFAULT_MODEL"),
                  "observed": sorted({row.get("shadow_model") for row in runner.collector.events if row.get("shadow_model")}),
                  "sdk_version": sdk_version,
                  "baseline_qwen_configured": os.getenv("QWEN_MODEL")},
        "run_parameters": {"shadow_timeout_ms": config.timeout_ms, "max_in_flight": config.max_in_flight,
                           "shadow_sample_rate": config.sample_rate, "authority_traffic_percent": 0,
                           "provider_retries": 0, "command": "python -m app.scripts.run_gray_readiness_eval" + (" --safety-only" if args.safety_only else "")},
        "summaries": summaries, "harness": harness,
        "known_uncertain_gold": UNCERTAIN,
        "readiness": "NO-GO: human adjudication and production canary evidence missing",
    }
    output = PROJECT_ROOT / "artifacts" / ("jev-gray-readiness-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:8])
    output.mkdir(parents=True, exist_ok=False)
    (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (output / "joined_records.jsonl").write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in joined), encoding="utf-8")
    (output / "disagreement_review_queue.jsonl").write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in disputes), encoding="utf-8")
    (output / "safety_records.jsonl").write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in safety_records), encoding="utf-8")
    print(json.dumps({"output": str(output), "summaries": summaries, "harness": harness,
                      "review_queue_count": len(disputes)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
