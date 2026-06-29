from __future__ import annotations

from fastapi.testclient import TestClient

from main import app
from app.api import chat as chat_api
import app.agent.procurement_agent as procurement_agent


def test_chat_sse_streams_llm_deltas_and_skips_sync_explanation(monkeypatch):
    calls: dict[str, object] = {}

    def fake_run_procurement_agent(*args, **kwargs):
        calls["skip_plan_explanation"] = kwargs.get("skip_plan_explanation")
        return {
            "session_id": "demo-session-001",
            "parsed_intent": {"categories": ["Monitor"]},
            "recommended_plan": {
                "items": [],
                "total_amount": 0,
                "budget_status": "no_budget_provided",
                "inventory_status": "valid",
                "constraint_satisfaction": "satisfied",
            },
            "plan_options": [],
            "selected_plan_id": None,
            "answer": "fallback answer",
            "trace_id": "trace-stream",
            "retrieved_products": [],
            "retrieval_evidence": {},
            "model_provider": "mock",
            "model_name": "qwen-turbo",
            "used_mock_llm": True,
            "llm_error": None,
            "used_previous_context": False,
            "previous_trace_id": None,
            "type": "recommendation_plan",
            "products": None,
            "recommendation_plan": {},
            "actions": [],
            "order_id": None,
            "order_status": None,
            "checkout_url": None,
        }

    async def fake_safe_llm_stream(prompt, purpose, language):
        calls["prompt"] = prompt
        calls["purpose"] = purpose
        calls["language"] = language
        yield {"delta": "hello", "finish_reason": None}
        yield {"delta": " world", "finish_reason": None}
        yield {"delta": "", "finish_reason": "stop"}

    def fail_generate_plan_explanation(*args, **kwargs):
        raise AssertionError("generate_plan_explanation should be skipped for SSE")

    monkeypatch.setattr(chat_api, "run_procurement_agent", fake_run_procurement_agent)
    monkeypatch.setattr(chat_api, "safe_llm_stream", fake_safe_llm_stream)
    monkeypatch.setattr(procurement_agent, "generate_plan_explanation", fail_generate_plan_explanation)

    response = TestClient(app).post(
        "/api/chat",
        json={"message": "recommend monitors", "session_id": "demo-session-001", "language": "en"},
        headers={"accept": "text/event-stream"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert 'data: {"delta": "hello"}' in response.text
    assert 'data: {"delta": " world"}' in response.text
    assert 'data: {"delta": "", "finish_reason": "stop"}' in response.text
    assert calls["skip_plan_explanation"] is True
    assert calls["purpose"] == "plan_explanation"
