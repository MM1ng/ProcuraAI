import json
import math
import sys
import types

import app.evaluation.ragas_runner as ragas_runner


def test_run_ragas_evaluation_writes_scores_and_skips_mock_cases(monkeypatch, tmp_path):
    questions_file = tmp_path / "evaluation_questions.csv"
    questions_file.write_text(
        "question,ground_truth\n"
        "\"Need headsets.\",\"Should recommend valid headsets.\"\n"
        "\"Need mice.\",\"Should recommend valid mice.\"\n",
        encoding="utf-8",
    )
    log_file = tmp_path / "ragas_evaluation_logs.json"

    monkeypatch.setattr(ragas_runner, "QUESTIONS_FILE", questions_file)
    monkeypatch.setattr(ragas_runner, "RAGAS_EVAL_FILE", log_file)

    def fake_agent(
        question,
        session_id,
        previous_intent=None,
        previous_plan=None,
        language="en",
    ):
        if "mice" in question:
            return {
                "answer": "Mock answer",
                "retrieved_products": [],
                "used_mock_llm": True,
                "model_provider": "mock",
                "model_name": "qwen-turbo",
            }
        return {
            "answer": "Recommended Team Headset.",
            "retrieved_products": [
                {
                    "product_id": "P-1",
                    "name": "Team Headset",
                    "category": "Headset",
                    "price": 55,
                    "rating": 4.4,
                    "stock": 20,
                    "delivery_days": 4,
                }
            ],
            "used_mock_llm": False,
            "model_provider": "tongyi",
            "model_name": "qwen-turbo",
            "recommended_plan": {
                "total_amount": 55,
                "budget_status": "within_budget",
                "inventory_status": "valid",
                "constraint_satisfaction": "satisfied",
                "avg_rating": 4.4,
                "items": [],
            },
        }

    monkeypatch.setattr(ragas_runner, "run_procurement_agent", fake_agent)
    monkeypatch.setattr(
        ragas_runner,
        "_evaluate_ragas_samples",
        lambda samples, llm=None: [
            {
                "faithfulness": 0.9,
                "answer_relevancy": 0.8,
                "context_precision": 0.7,
                "context_recall": 0.6,
            }
        ],
    )

    rows = ragas_runner.run_ragas_evaluation()

    assert len(rows) == 2
    assert rows[0]["ragas_skipped"] is False
    assert rows[0]["faithfulness"] == 0.9
    assert rows[0]["answer_relevance"] == 0.8
    assert rows[0]["contexts"] == [
        "Team Headset | Headset | $55 | rating 4.4 | stock 20 | delivery 4 days",
        (
            "Plan metadata: total_amount=$55, budget_status=within_budget, "
            "inventory_status=valid, constraint_satisfaction=satisfied, avg_rating=4.4"
        ),
    ]
    assert rows[1]["ragas_skipped"] is True
    assert rows[1]["skip_reason"] == "Agent used mock LLM; RAGAS judging skipped."
    assert json.loads(log_file.read_text(encoding="utf-8")) == rows


def test_summarize_ragas_evaluations_matches_agent_summary_shape(monkeypatch, tmp_path):
    log_file = tmp_path / "ragas_evaluation_logs.json"
    log_file.write_text(
        json.dumps(
            [
                {
                    "faithfulness": 0.9,
                    "answer_relevance": 0.8,
                    "context_precision": 0.7,
                    "context_recall": 0.6,
                    "ragas_skipped": False,
                    "latency_ms": 100,
                    "budget_compliance": True,
                    "inventory_validity": True,
                    "constraint_satisfaction": True,
                },
                {
                    "faithfulness": None,
                    "answer_relevance": None,
                    "context_precision": None,
                    "context_recall": None,
                    "ragas_skipped": True,
                    "latency_ms": 0,
                    "budget_compliance": False,
                    "inventory_validity": True,
                    "constraint_satisfaction": False,
                },
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(ragas_runner, "RAGAS_EVAL_FILE", log_file)

    summary = ragas_runner.summarize_ragas_evaluations()

    assert summary["faithfulness"] == 0.9
    assert summary["answer_relevance"] == 0.8
    assert summary["context_precision"] == 0.7
    assert summary["context_recall"] == 0.6
    assert summary["evaluated_cases"] == 1
    assert summary["skipped_cases"] == 1
    assert len(summary["results"]) == 2


def test_evaluate_ragas_samples_wraps_samples_in_evaluation_dataset(monkeypatch):
    captured = {}

    class FakeEvaluationDataset:
        def __init__(self, samples):
            self.samples = samples

    class FakeResult:
        def to_pandas(self):
            class FakeFrame:
                def to_dict(self, orient):
                    assert orient == "records"
                    return [
                        {
                            "faithfulness": 0.9,
                            "answer_relevancy": math.nan,
                            "answer_correctness": 0.75,
                            "context_precision": 0.7,
                            "context_recall": 0.6,
                            "budget_compliance_aspect": 1.0,
                            "category_coverage": 0.5,
                            "constraint_adherence": 0.25,
                        }
                    ]

            return FakeFrame()

    def fake_evaluate(dataset, metrics, llm, embeddings):
        captured["dataset"] = dataset
        captured["llm"] = llm
        captured["embeddings"] = embeddings
        captured["metrics"] = metrics
        return FakeResult()

    class FakeAspectCritic:
        def __init__(self, name, definition):
            self.name = name
            self.definition = definition

    monkeypatch.setitem(
        sys.modules,
        "ragas",
        types.SimpleNamespace(EvaluationDataset=FakeEvaluationDataset, evaluate=fake_evaluate),
    )
    monkeypatch.setitem(
        sys.modules,
        "ragas.metrics",
        types.SimpleNamespace(
            AspectCritic=FakeAspectCritic,
            answer_correctness="answer_correctness",
            answer_relevancy="answer_relevancy",
            context_precision="context_precision",
            context_recall="context_recall",
            faithfulness="faithfulness",
        ),
    )
    monkeypatch.setattr(
        ragas_runner,
        "embed_text",
        lambda text, text_type="document": [1.0, 0.0] if text_type == "query" else [0.0, 1.0],
    )
    monkeypatch.setattr(
        ragas_runner,
        "embed_texts",
        lambda texts, text_type="document": [[0.0, 1.0] for _ in texts],
    )

    scores = ragas_runner._evaluate_ragas_samples(["sample"], llm=types.SimpleNamespace())

    assert isinstance(captured["dataset"], FakeEvaluationDataset)
    assert captured["dataset"].samples == ["sample"]
    assert type(captured["embeddings"]).__name__ == "TongyiRagasEmbeddings"
    assert captured["embeddings"].embed_query("abc") == [1.0, 0.0]
    assert captured["embeddings"].embed_documents(["doc"]) == [[0.0, 1.0]]
    metric_names = [getattr(metric, "name", metric) for metric in captured["metrics"]]
    assert metric_names == [
        "faithfulness",
        "answer_relevancy",
        "answer_correctness",
        "context_precision",
        "context_recall",
        "budget_compliance_aspect",
        "category_coverage",
        "constraint_adherence",
    ]
    assert scores == [
        {
            "faithfulness": 0.9,
            "answer_relevancy": None,
            "answer_correctness": 0.75,
            "context_precision": 0.7,
            "context_recall": 0.6,
            "budget_compliance_aspect": 1.0,
            "category_coverage": 0.5,
            "constraint_adherence": 0.25,
        }
    ]


def test_tongyi_ragas_embeddings_delegates_to_project_embedding_service(monkeypatch):
    calls = []

    def fake_embed_text(text, text_type="document"):
        calls.append(("query", text, text_type))
        return [0.1, 0.2]

    def fake_embed_texts(texts, text_type="document"):
        calls.append(("documents", texts, text_type))
        return [[0.3, 0.4] for _ in texts]

    monkeypatch.setattr(ragas_runner, "embed_text", fake_embed_text)
    monkeypatch.setattr(ragas_runner, "embed_texts", fake_embed_texts)

    embeddings = ragas_runner.TongyiRagasEmbeddings()

    assert embeddings.embed_query("question") == [0.1, 0.2]
    assert embeddings.embed_documents(["context one", "context two"]) == [[0.3, 0.4], [0.3, 0.4]]
    assert calls == [
        ("query", "question", "query"),
        ("documents", ["context one", "context two"], "document"),
    ]


def test_row_from_agent_result_appends_selected_items_and_plan_metadata():
    row = ragas_runner._row_from_agent_result(
        index=1,
        question="Need keyboards and mice.",
        ground_truth="A valid plan recommends keyboards and mice.",
        result={
            "answer": "Recommended Keyboard A and Mouse B. Budget: within budget.",
            "retrieved_products": [
                {
                    "product_id": "P-1",
                    "name": "Keyboard A",
                    "category": "Keyboard",
                    "price": 20,
                    "rating": 4.5,
                    "stock": 50,
                    "delivery_days": 3,
                }
            ],
            "recommended_plan": {
                "total_amount": 700,
                "budget_status": "within_budget",
                "inventory_status": "valid",
                "constraint_satisfaction": "satisfied",
                "avg_rating": 4.4,
                "items": [
                    {
                        "product_id": "P-1",
                        "name": "Keyboard A",
                        "category": "Keyboard",
                        "unit_price": 20,
                        "quantity": 10,
                        "subtotal": 200,
                        "rating": 4.5,
                        "stock": 50,
                        "delivery_days": 3,
                        "supplier": "OfficeCo",
                    },
                    {
                        "product_id": "P-2",
                        "name": "Mouse B",
                        "category": "Mouse",
                        "unit_price": 15,
                        "quantity": 10,
                        "subtotal": 150,
                        "rating": 4.3,
                        "stock": 80,
                        "delivery_days": 2,
                        "supplier": "DeskCo",
                    },
                ],
            },
            "plan_options": [
                {"name": "Plan A", "plan": {"budget_status": "within_budget"}},
                {"name": "Plan B", "plan": {"budget_status": "over_budget"}},
                {"name": "Plan C", "plan": {"budget_status": "over_budget"}},
            ],
        },
        latency_ms=12.345,
    )

    assert row["contexts"] == [
        (
            "Keyboard A | Keyboard | $20 | rating 4.5 | stock 50 | delivery 3 days "
            "| quantity 10 | subtotal $200 | supplier OfficeCo"
        ),
        (
            "Mouse B | Mouse | $15 | rating 4.3 | stock 80 | delivery 2 days "
            "| quantity 10 | subtotal $150 | supplier DeskCo"
        ),
        (
            "Plan metadata: total_amount=$700, budget_status=within_budget, "
            "inventory_status=valid, constraint_satisfaction=satisfied, avg_rating=4.4"
        ),
        "Plan options: 3 candidate plans generated. 1 plans within budget, 2 plans over budget.",
    ]


def test_row_from_agent_result_adds_previous_plan_context_before_retrieved_noise():
    row = ragas_runner._row_from_agent_result(
        index=2,
        question="Replace the previous headset.",
        ground_truth="A cheaper headset replaces the previous headset.",
        result={
            "answer": "Jabra Ergo Headset replaces Logitech Ultra Headset.",
            "retrieved_products": [
                {
                    "product_id": "P-noise",
                    "name": "Unrelated Mouse",
                    "category": "Mouse",
                    "price": 99,
                    "rating": 4.0,
                    "stock": 10,
                    "delivery_days": 2,
                }
            ],
            "recommended_plan": {
                "items": [
                    {
                        "product_id": "P-new",
                        "name": "Jabra Ergo Headset",
                        "category": "Headset",
                        "unit_price": 60.4,
                        "quantity": 20,
                        "subtotal": 1208,
                        "rating": 4.5,
                        "stock": 225,
                        "delivery_days": 4,
                    }
                ],
                "total_amount": 1208,
                "budget_status": "within_budget",
                "inventory_status": "valid",
                "constraint_satisfaction": "satisfied",
                "avg_rating": 4.5,
            },
        },
        latency_ms=1,
        previous_plan={
            "items": [
                {
                    "product_id": "P-old",
                    "name": "Logitech Ultra Headset",
                    "category": "Headset",
                    "unit_price": 45.46,
                    "quantity": 20,
                    "subtotal": 909.2,
                    "rating": 4.5,
                    "stock": 219,
                    "delivery_days": 12,
                }
            ],
            "total_amount": 1869.2,
            "budget_status": "within_budget",
            "inventory_status": "valid",
            "constraint_satisfaction": "satisfied",
            "avg_rating": 4.3,
        },
    )

    assert row["contexts"][0].startswith("Jabra Ergo Headset | Headset | $60.4")
    assert row["contexts"][1].startswith("Plan metadata: total_amount=$1208")
    assert row["contexts"][2].startswith("Previous plan metadata: total_amount=$1869.2")
    assert row["contexts"][3].startswith("Previous plan item: Logitech Ultra Headset")
    assert all("Unrelated Mouse" not in context for context in row["contexts"])


def test_row_from_product_results_prioritizes_retrieved_products():
    row = ragas_runner._row_from_agent_result(
        index=3,
        question="Find keyboards.",
        ground_truth="The answer lists keyboard products.",
        result={
            "type": "product_results",
            "answer": "I found Keyboard Alpha.",
            "retrieved_products": [
                {
                    "product_id": "P-r",
                    "name": "Keyboard Alpha",
                    "category": "Keyboard",
                    "price": 29.99,
                    "rating": 4.7,
                    "stock": 50,
                    "delivery_days": 3,
                }
            ],
            "recommended_plan": {
                "items": [
                    {
                        "product_id": "P-plan",
                        "name": "Keyboard Plan Choice",
                        "category": "Keyboard",
                        "unit_price": 20,
                        "quantity": 1,
                        "subtotal": 20,
                        "rating": 4.6,
                        "stock": 20,
                        "delivery_days": 2,
                    }
                ],
                "total_amount": 20,
                "budget_status": "no_budget_provided",
                "inventory_status": "valid",
                "constraint_satisfaction": "satisfied",
                "avg_rating": 4.6,
            },
        },
        latency_ms=1,
    )

    assert row["contexts"][0].startswith("Keyboard Alpha | Keyboard")
    assert row["contexts"][1].startswith("Keyboard Plan Choice | Keyboard")


def test_row_from_agent_result_adds_intent_summary_context():
    row = ragas_runner._row_from_agent_result(
        index=1,
        question="Need team gear.",
        ground_truth="A plan for 10 people includes webcams and headsets.",
        result={
            "answer": "Recommended webcams and headsets for 10 people.",
            "retrieved_products": [],
            "parsed_intent": {
                "people_count": 10,
                "categories": ["Webcam", "Headset"],
                "budget": 3000,
                "quantity_per_category": {"Webcam": 10, "Headset": 10},
                "min_rating": 4.2,
                "max_delivery_days": 5,
            },
            "recommended_plan": {
                "items": [],
                "total_amount": 1200,
                "budget_status": "within_budget",
                "inventory_status": "valid",
                "constraint_satisfaction": "satisfied",
                "avg_rating": 4.4,
            },
        },
        latency_ms=1,
    )

    assert row["contexts"][0] == (
        "Intent summary: people_count=10, categories=Webcam, Headset, budget=$3000, "
        "quantity_per_category=Webcam:10, Headset:10, min_rating=4.2, max_delivery_days=5"
    )


def test_run_ragas_evaluation_reuses_dependency_session_and_previous_context(monkeypatch, tmp_path):
    questions_file = tmp_path / "evaluation_questions.csv"
    questions_file.write_text(
        "question,ground_truth,depends_on\n"
        "\"Base request.\",\"Base ground truth.\",\n"
        "\"Follow-up request.\",\"Follow-up ground truth.\",1\n",
        encoding="utf-8",
    )
    log_file = tmp_path / "ragas_evaluation_logs.json"
    calls = []

    monkeypatch.setattr(ragas_runner, "QUESTIONS_FILE", questions_file)
    monkeypatch.setattr(ragas_runner, "RAGAS_EVAL_FILE", log_file)

    def fake_agent(
        question,
        session_id,
        previous_intent=None,
        previous_plan=None,
        language="en",
    ):
        calls.append(
            {
                "question": question,
                "session_id": session_id,
                "previous_intent": previous_intent,
                "previous_plan": previous_plan,
            }
        )
        return {
            "answer": f"Answer for {question}",
            "retrieved_products": [],
            "recommended_plan": {
                "items": [],
                "total_amount": len(calls),
                "budget_status": "within_budget",
                "inventory_status": "valid",
                "constraint_satisfaction": "satisfied",
                "avg_rating": 4.5,
            },
            "parsed_intent": {"case": question},
            "used_mock_llm": False,
        }

    monkeypatch.setattr(ragas_runner, "run_procurement_agent", fake_agent)
    monkeypatch.setattr(
        ragas_runner,
        "_evaluate_ragas_samples",
        lambda samples, llm=None: [
            {
                "faithfulness": 0.9,
                "answer_relevancy": 0.8,
                "context_precision": 0.7,
                "context_recall": 0.6,
            }
            for _ in samples
        ],
    )

    rows = ragas_runner.run_ragas_evaluation()

    assert rows[1]["depends_on"] == "1"
    assert calls[0]["session_id"] == "eval-ragas-1"
    assert calls[0]["previous_intent"] is None
    assert calls[0]["previous_plan"] is None
    assert calls[1]["session_id"] == "eval-ragas-1"
    assert calls[1]["previous_intent"] == {"case": "Base request."}
    assert calls[1]["previous_plan"]["total_amount"] == 1


def test_summarize_ragas_evaluations_includes_new_ragas_metrics(monkeypatch, tmp_path):
    log_file = tmp_path / "ragas_evaluation_logs.json"
    log_file.write_text(
        json.dumps(
            [
                {
                    "faithfulness": 0.9,
                    "answer_relevancy": 0.8,
                    "answer_relevance": 0.8,
                    "answer_correctness": 0.7,
                    "context_precision": 0.6,
                    "context_recall": 0.5,
                    "budget_compliance_aspect": 1.0,
                    "category_coverage": 0.75,
                    "constraint_adherence": 0.25,
                    "ragas_skipped": False,
                }
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(ragas_runner, "RAGAS_EVAL_FILE", log_file)

    summary = ragas_runner.summarize_ragas_evaluations()

    assert summary["answer_correctness"] == 0.7
    assert summary["budget_compliance_aspect"] == 1.0
    assert summary["category_coverage"] == 0.75
    assert summary["constraint_adherence"] == 0.25
