from app.evaluation.embedding_retrieval_comparison import (
    EvaluationCase,
    _score_case_results,
    _summarize_provider,
)


def test_score_case_results_calculates_hits_mrr_and_category_coverage():
    case = EvaluationCase(
        query="Need webcams and headsets for remote meetings",
        intent={"categories": ["Webcam", "Headset"]},
        expected_categories=["Webcam", "Headset"],
    )
    products = [
        {"product_id": "p1", "category": "Mouse", "retrieval_score": 0.9},
        {"product_id": "p2", "category": "Webcam", "retrieval_score": 0.8},
        {"product_id": "p3", "category": "Headset", "retrieval_score": 0.7},
    ]

    row = _score_case_results(case, products, latency_ms=12.5)

    assert row["hit_at_5"] is True
    assert row["first_relevant_rank"] == 2
    assert row["mrr"] == 0.5
    assert row["category_coverage"] == 1.0
    assert row["unique_categories_returned"] == ["Headset", "Mouse", "Webcam"]
    assert row["missing_categories"] == []
    assert row["top_product_ids"] == ["p1", "p2", "p3"]
    assert row["latency_ms"] == 12.5


def test_summarize_provider_averages_quality_and_latency():
    rows = [
        {"hit_at_5": True, "mrr": 1.0, "category_coverage": 1.0, "latency_ms": 10.0},
        {"hit_at_5": False, "mrr": 0.0, "category_coverage": 0.5, "latency_ms": 20.0},
    ]

    summary = _summarize_provider("hash", rows)

    assert summary == {
        "provider": "hash",
        "cases": 2,
        "hit_rate_at_5": 0.5,
        "mean_reciprocal_rank": 0.5,
        "mean_category_coverage": 0.75,
        "average_latency_ms": 15.0,
    }


def test_comparison_defaults_to_text_embedding_v4(monkeypatch):
    monkeypatch.delenv("EMBEDDING_MODEL", raising=False)
    from app.evaluation.embedding_retrieval_comparison import _default_embedding_model

    assert _default_embedding_model() == "text-embedding-v4"


def test_comparison_report_contains_pure_vector_and_hybrid_modes(monkeypatch, tmp_path):
    from app.evaluation import embedding_retrieval_comparison as comparison

    monkeypatch.setattr(comparison, "_evaluation_cases", lambda: [
        EvaluationCase(
            query="Need webcams",
            intent={"categories": ["Webcam"]},
            expected_categories=["Webcam"],
        )
    ])
    monkeypatch.setattr(comparison, "_build_provider_index", lambda provider, cases, run_id: tmp_path)
    monkeypatch.setattr(
        comparison,
        "_evaluate_provider_mode",
        lambda provider, cases, run_id, mode: {
            "summary": {
                "provider": provider,
                "cases": 1,
                "hit_rate_at_5": 1.0,
                "mean_reciprocal_rank": 1.0,
                "mean_category_coverage": 1.0,
                "average_latency_ms": 1.0,
            },
            "rows": [],
        },
    )

    report = comparison.run_embedding_retrieval_comparison(providers=["hash"], output_path=tmp_path / "report.json")

    assert set(report["modes"]) == {"pure_vector", "hybrid"}
    assert set(report["providers"]["hash"]) == {"pure_vector", "hybrid"}
