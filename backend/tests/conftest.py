import pytest

from app.services import llm_service


@pytest.fixture(autouse=True)
def disable_real_qwen_calls(monkeypatch):
    monkeypatch.setattr(llm_service, "get_llm_model", lambda: None)
