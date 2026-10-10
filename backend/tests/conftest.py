import pytest
import threading
import time

from app.services import llm_service
from app.observability import local_tracer
from app.services import order_service
from app.core.config import get_settings


def _wait_for_jev_test_threads(timeout: float = 2.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        active = [
            thread for thread in threading.enumerate()
            if thread.name in {"jev-shadow-provider", "jev-shadow-dispatch", "jev-authoritative-provider"}
        ]
        if not active:
            return
        for thread in active:
            thread.join(timeout=0.05)


@pytest.fixture(autouse=True)
def disable_real_qwen_calls(monkeypatch):
    monkeypatch.setattr(llm_service, "get_llm_model", lambda: None)


@pytest.fixture(autouse=True)
def isolate_runtime_storage(monkeypatch, tmp_path, request):
    """Keep tests away from the user's orders and observability artifacts."""
    from app.decision import runtime as decision_runtime
    from app.agent.session_state import clear_session_state
    from app.services.confirmed_transaction import clear_transaction_capabilities
    from app.observability.langfuse_client import LangfuseClient

    clear_session_state()
    clear_transaction_capabilities()
    monkeypatch.setattr(LangfuseClient, "trace", lambda *_, **__: None)

    monkeypatch.setattr(decision_runtime, "RUNTIME_STATE_PATH", tmp_path / "decision-runtime.sqlite3")
    # This module owns its own explicit isolation fixture and needs to observe
    # the production paths before entering that context.
    if request.path.name == "test_shadow_observation_isolation.py":
        _wait_for_jev_test_threads()
        yield
        return
    orders_file = tmp_path / "orders.json"
    traces_file = tmp_path / "observability_logs.json"
    orders_file.write_text("[]", encoding="utf-8")
    traces_file.write_text("[]", encoding="utf-8")
    monkeypatch.setattr(order_service, "ORDERS_FILE", orders_file)
    monkeypatch.setattr(local_tracer, "TRACE_FILE", traces_file)
    from app.services.transaction_lock import order_writer_lease
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("ANONYMOUS_CALLER_ENABLED", "true")
    monkeypatch.setenv("PROCURA_IDENTITY_REGISTRY", str(tmp_path / "identity" / "registry.sqlite3"))
    get_settings.cache_clear()
    with order_writer_lease(orders_file):
        yield
    _wait_for_jev_test_threads()
    get_settings.cache_clear()
