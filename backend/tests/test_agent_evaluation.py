from pathlib import Path

from fastapi.testclient import TestClient

import app.evaluation.agent_eval_runner as agent_eval_runner
from main import app


def test_run_agent_evaluation_records_real_agent_outputs(monkeypatch, tmp_path):
    eval_file = tmp_path / "evaluation_logs.json"
    monkeypatch.setattr(agent_eval_runner, "EVAL_FILE", eval_file)
    monkeypatch.setattr(
        agent_eval_runner,
        "run_procurement_agent",
        lambda message, session_id, language="en": {
            "answer": "Recommended Team Headset for the current procurement request.",
            "retrieved_products": [
                {
                    "product_id": "P-1",
                    "name": "Team Headset",
                    "category": "Headset",
                    "price": 55,
                    "rating": 4.4,
                    "stock": 20,
                    "delivery_days": 4,
                    "supplier": "Northwind Office",
                }
            ],
            "recommended_plan": {
                "items": [{"product_id": "P-1", "category": "Headset"}],
                "budget_status": "within_budget",
                "inventory_status": "valid",
                "constraint_satisfaction": "satisfied",
            },
            "trace_id": "trace-eval",
            "model_provider": "tongyi",
            "model_name": "qwen3.7-max",
            "used_mock_llm": False,
            "llm_error": None,
        },
    )

    rows = agent_eval_runner.run_agent_evaluation(["Need headsets for 5 people."])

    assert len(rows) == 1
    assert rows[0]["evaluation_mode"] == "agent"
    assert rows[0]["answer"] == "Recommended Team Headset for the current procurement request."
    assert rows[0]["contexts"] == ["Team Headset | Headset | $55 | rating 4.4 | stock 20 | delivery 4 days"]
    assert rows[0]["model_provider"] == "tongyi"
    assert rows[0]["used_mock_llm"] is False
    assert Path(eval_file).exists()


def test_run_agent_evaluation_endpoint(monkeypatch, tmp_path):
    monkeypatch.setattr(agent_eval_runner, "EVAL_FILE", tmp_path / "evaluation_logs.json")
    monkeypatch.setattr(
        agent_eval_runner,
        "run_agent_evaluation",
        lambda questions=None: [{"log_id": 1}, {"log_id": 2}],
    )
    client = TestClient(app)

    response = client.post("/api/evaluation/run-agent")

    assert response.status_code == 200
    assert response.json() == {"status": "completed", "generated_rows": 2}
