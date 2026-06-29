from types import SimpleNamespace

from fastapi.testclient import TestClient

from main import app
from app.api import llm as llm_api


def test_llm_status_reports_tongyi_configuration(monkeypatch):
    monkeypatch.setattr(
        llm_api,
        "settings",
        SimpleNamespace(
            LLM_PROVIDER="tongyi",
            QWEN_MODEL="qwen-turbo",
            QWEN_TIMEOUT_SECONDS=12,
            QWEN_ENABLE_THINKING=False,
            DASHSCOPE_API_KEY="dash-test",
            USE_MOCK_LLM=False,
        ),
    )
    client = TestClient(app)

    response = client.get("/api/llm/status")

    assert response.status_code == 200
    assert response.json() == {
        "llm_provider": "tongyi",
        "model_name": "qwen-turbo",
        "has_api_key": True,
        "use_mock_llm": False,
        "mock_fallback_enabled": False,
        "qwen_timeout_seconds": 12,
        "qwen_enable_thinking": False,
    }


def test_llm_test_invokes_safe_llm_service(monkeypatch):
    monkeypatch.setattr(
        llm_api,
        "safe_llm_invoke",
        lambda message, purpose: {
            "content": f"answered: {message}",
            "model_provider": "tongyi",
            "model_name": "qwen-turbo",
            "used_mock_llm": False,
            "error": None,
        },
    )
    client = TestClient(app)

    response = client.post("/api/llm/test", json={"message": "你是谁呀能做什么？"})

    assert response.status_code == 200
    assert response.json() == {
        "content": "answered: 你是谁呀能做什么？",
        "model_provider": "tongyi",
        "model_name": "qwen-turbo",
        "used_mock_llm": False,
        "error": None,
    }
