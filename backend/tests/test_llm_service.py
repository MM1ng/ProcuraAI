from types import SimpleNamespace

from app.services import llm_service


def _settings(**overrides):
    values = {
        "USE_MOCK_LLM": False,
        "LLM_PROVIDER": "tongyi",
        "DASHSCOPE_API_KEY": "",
        "QWEN_MODEL": "qwen3.7-max",
        "QWEN_TOP_P": 0.8,
        "QWEN_MAX_TOKENS": 2000,
        "QWEN_TIMEOUT_SECONDS": 12,
        "QWEN_ENABLE_THINKING": False,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_safe_llm_invoke_uses_mock_when_api_key_is_missing(monkeypatch):
    monkeypatch.setattr(llm_service, "settings", _settings(DASHSCOPE_API_KEY=""))

    result = llm_service.safe_llm_invoke("hello", purpose="llm_test")

    assert result["model_provider"] == "mock"
    assert result["model_name"] == "qwen3.7-max"
    assert result["used_mock_llm"] is True
    assert "DASHSCOPE_API_KEY" in result["error"]
    assert result["content"]


def test_safe_llm_invoke_returns_tongyi_metadata_on_success(monkeypatch):
    class DummyDashScope:
        @staticmethod
        def call(model, prompt, api_key, top_p, max_tokens, timeout, enable_thinking):
            assert model == "qwen3.7-max"
            assert prompt == "who are you?"
            assert api_key == "dash-test"
            assert top_p == 0.8
            assert max_tokens == 2000
            assert timeout == 12
            assert enable_thinking is False
            return SimpleNamespace(
                output={
                    "choices": [
                        {
                            "message": {
                                "content": "I am qwen3.7-max.",
                            }
                        }
                    ]
                }
            )

    monkeypatch.setattr(llm_service, "settings", _settings(DASHSCOPE_API_KEY="dash-test"))
    monkeypatch.setattr(llm_service, "get_llm_model", lambda: DummyDashScope)

    result = llm_service.safe_llm_invoke("who are you?", purpose="llm_test")

    assert result["content"] == "I am qwen3.7-max."
    assert result["model_provider"] == "tongyi"
    assert result["model_name"] == "qwen3.7-max"
    assert result["used_mock_llm"] is False
    assert result["error"] is None
    assert result["fallback_reason"] is None
    assert result["latency_ms"] >= 0


def test_safe_llm_invoke_prefers_tongyi_even_when_mock_fallback_is_enabled(monkeypatch):
    class DummyDashScope:
        @staticmethod
        def call(**kwargs):
            return SimpleNamespace(output={"text": "real qwen answer"})

    monkeypatch.setattr(
        llm_service,
        "settings",
        _settings(USE_MOCK_LLM=True, DASHSCOPE_API_KEY="dash-test"),
    )
    monkeypatch.setattr(llm_service, "get_llm_model", lambda: DummyDashScope)

    result = llm_service.safe_llm_invoke("hello", purpose="llm_test")

    assert result["model_provider"] == "tongyi"
    assert result["content"] == "real qwen answer"
    assert result["used_mock_llm"] is False


def test_safe_llm_invoke_falls_back_to_mock_on_tongyi_error(monkeypatch):
    class FailingDashScope:
        @staticmethod
        def call(**kwargs):
            raise RuntimeError("dashscope timeout")

    monkeypatch.setattr(llm_service, "settings", _settings(DASHSCOPE_API_KEY="dash-test"))
    monkeypatch.setattr(llm_service, "get_llm_model", lambda: FailingDashScope)

    result = llm_service.safe_llm_invoke("hello", purpose="llm_test")

    assert result["model_provider"] == "mock"
    assert result["model_name"] == "qwen3.7-max"
    assert result["used_mock_llm"] is True
    assert result["error"] == "dashscope timeout"
    assert result["fallback_reason"] == "dashscope timeout"
