from types import SimpleNamespace
import asyncio

import app.agent.plan_generator as plan_generator
from app.services import llm_service


def _settings(**overrides):
    values = {
        "USE_MOCK_LLM": False,
        "LLM_PROVIDER": "tongyi",
        "DASHSCOPE_API_KEY": "",
        "QWEN_MODEL": "qwen-turbo",
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
    assert result["model_name"] == "qwen-turbo"
    assert result["used_mock_llm"] is True
    assert "DASHSCOPE_API_KEY" in result["error"]
    assert result["content"]


def test_safe_llm_invoke_returns_tongyi_metadata_on_success(monkeypatch):
    class DummyDashScope:
        @staticmethod
        def call(model, prompt, api_key, top_p, max_tokens, timeout, enable_thinking):
            assert model == "qwen-turbo"
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
                                "content": "I am qwen-turbo.",
                            }
                        }
                    ]
                }
            )

    monkeypatch.setattr(llm_service, "settings", _settings(DASHSCOPE_API_KEY="dash-test"))
    monkeypatch.setattr(llm_service, "get_llm_model", lambda: DummyDashScope)

    result = llm_service.safe_llm_invoke("who are you?", purpose="llm_test")

    assert result["content"] == "I am qwen-turbo."
    assert result["model_provider"] == "tongyi"
    assert result["model_name"] == "qwen-turbo"
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
            raise RuntimeError("dashscope invalid parameter")

    monkeypatch.setattr(llm_service, "settings", _settings(DASHSCOPE_API_KEY="dash-test"))
    monkeypatch.setattr(llm_service, "get_llm_model", lambda: FailingDashScope)

    result = llm_service.safe_llm_invoke("hello", purpose="llm_test")

    assert result["model_provider"] == "mock"
    assert result["model_name"] == "qwen-turbo"
    assert result["used_mock_llm"] is True
    assert result["error"] == "dashscope invalid parameter"
    assert result["fallback_reason"] == "dashscope invalid parameter"
    assert result["retry_count"] == 0


def test_safe_llm_invoke_retries_network_error_once_then_succeeds(monkeypatch):
    calls: list[int] = []

    class FlakyDashScope:
        @staticmethod
        def call(**kwargs):
            calls.append(1)
            if len(calls) == 1:
                raise TimeoutError("temporary timeout")
            return SimpleNamespace(output={"text": "recovered"})

    sleep_calls: list[float] = []
    monkeypatch.setattr(llm_service, "settings", _settings(DASHSCOPE_API_KEY="dash-test"))
    monkeypatch.setattr(llm_service, "get_llm_model", lambda: FlakyDashScope)
    monkeypatch.setattr(llm_service.time, "sleep", lambda seconds: sleep_calls.append(seconds))

    result = llm_service.safe_llm_invoke("hello", purpose="llm_test")

    assert result["content"] == "recovered"
    assert result["model_provider"] == "tongyi"
    assert result["used_mock_llm"] is False
    assert result["retry_count"] == 1
    assert len(calls) == 2
    assert sleep_calls == [2]


def test_safe_llm_invoke_does_not_retry_auth_or_bad_request_errors(monkeypatch):
    calls: list[int] = []

    class AuthFailingDashScope:
        @staticmethod
        def call(**kwargs):
            calls.append(1)
            raise RuntimeError("DashScope 401 unauthorized")

    sleep_calls: list[float] = []
    monkeypatch.setattr(llm_service, "settings", _settings(DASHSCOPE_API_KEY="dash-test"))
    monkeypatch.setattr(llm_service, "get_llm_model", lambda: AuthFailingDashScope)
    monkeypatch.setattr(llm_service.time, "sleep", lambda seconds: sleep_calls.append(seconds))

    result = llm_service.safe_llm_invoke("hello", purpose="llm_test")

    assert result["model_provider"] == "mock"
    assert result["retry_count"] == 0
    assert len(calls) == 1
    assert sleep_calls == []


def test_safe_llm_invoke_retries_5xx_once_then_falls_back(monkeypatch):
    calls: list[int] = []

    class ServerFailingDashScope:
        @staticmethod
        def call(**kwargs):
            calls.append(1)
            raise RuntimeError("DashScope 503 service unavailable")

    sleep_calls: list[float] = []
    monkeypatch.setattr(llm_service, "settings", _settings(DASHSCOPE_API_KEY="dash-test"))
    monkeypatch.setattr(llm_service, "get_llm_model", lambda: ServerFailingDashScope)
    monkeypatch.setattr(llm_service.time, "sleep", lambda seconds: sleep_calls.append(seconds))

    result = llm_service.safe_llm_invoke("hello", purpose="llm_test")

    assert result["model_provider"] == "mock"
    assert result["error"] == "DashScope 503 service unavailable"
    assert result["retry_count"] == 1
    assert len(calls) == 2
    assert sleep_calls == [2]


def test_safe_llm_stream_yields_incremental_dashscope_chunks(monkeypatch):
    class DummyDashScope:
        @staticmethod
        def call(model, prompt, api_key, top_p, max_tokens, timeout, enable_thinking, stream, incremental_output):
            assert model == "qwen-turbo"
            assert prompt == "stream please"
            assert api_key == "dash-test"
            assert stream is True
            assert incremental_output is True
            yield SimpleNamespace(output={"text": "hello "})
            yield SimpleNamespace(output={"choices": [{"message": {"content": "world"}}]})

    async def collect():
        return [
            chunk
            async for chunk in llm_service.safe_llm_stream(
                "stream please",
                purpose="llm_test",
                language="en",
            )
        ]

    monkeypatch.setattr(llm_service, "settings", _settings(DASHSCOPE_API_KEY="dash-test"))
    monkeypatch.setattr(llm_service, "get_llm_model", lambda: DummyDashScope)

    assert asyncio.run(collect()) == [
        {"delta": "hello ", "finish_reason": None},
        {"delta": "world", "finish_reason": None},
        {"delta": "", "finish_reason": "stop"},
    ]


def test_safe_llm_stream_falls_back_to_mock_on_error(monkeypatch):
    class FailingDashScope:
        @staticmethod
        def call(**kwargs):
            raise RuntimeError("stream failed")

    async def collect():
        return [
            chunk
            async for chunk in llm_service.safe_llm_stream(
                "stream please",
                purpose="llm_test",
                language="en",
            )
        ]

    monkeypatch.setattr(llm_service, "settings", _settings(DASHSCOPE_API_KEY="dash-test"))
    monkeypatch.setattr(llm_service, "get_llm_model", lambda: FailingDashScope)

    chunks = asyncio.run(collect())

    assert chunks[0]["delta"]
    assert chunks[0]["finish_reason"] is None
    assert chunks[-1] == {"delta": "", "finish_reason": "stop"}


def test_generate_plan_explanation_uses_fallback_when_llm_answer_is_too_long(monkeypatch):
    monkeypatch.setattr(
        plan_generator,
        "safe_llm_invoke",
        lambda *_args, **_kwargs: {
            "content": "x" * 1400,
            "model_provider": "tongyi",
            "model_name": "qwen",
            "used_mock_llm": False,
            "error": None,
            "latency_ms": 1,
            "fallback_reason": None,
        },
    )

    result = plan_generator.generate_plan_explanation({}, [], {"items": []}, "short fallback")

    assert result["content"] == "short fallback"
