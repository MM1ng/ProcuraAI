from __future__ import annotations

from app.evaluation.embedding_retrieval_comparison import run_embedding_retrieval_comparison


def main() -> None:
    report = run_embedding_retrieval_comparison()
    for provider, modes in report["providers"].items():
        if modes.get("error"):
            print(f"{provider}: ERROR {modes['error']['error']}")
            continue
        for mode, result in modes.items():
            summary = result["summary"]
            print(
                f"{provider}/{mode}: hit@5={summary['hit_rate_at_5']:.4f}, "
                f"mrr={summary['mean_reciprocal_rank']:.4f}, "
                f"coverage={summary['mean_category_coverage']:.4f}, "
                f"avg_latency_ms={summary['average_latency_ms']:.2f}"
            )


if __name__ == "__main__":
    main()
