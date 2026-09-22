from __future__ import annotations

import json
import threading
from copy import deepcopy
from pathlib import Path

import pytest

import app.agent.procurement_agent as agent
from app.decision.observability import emit_shadow_audit
from app.decision.shadow_observation import isolated_shadow_observation_storage
from app.observability import local_tracer
from app.rag.retriever import RetrievalResult
from app.services import order_service, product_service


def test_local_tracer_serializes_more_than_one_hundred_concurrent_events(monkeypatch, tmp_path):
    trace_file = tmp_path / "observability_logs.json"
    monkeypatch.setattr(local_tracer, "TRACE_FILE", trace_file)
    thread_count = 8
    writes_per_thread = 16
    barrier = threading.Barrier(thread_count)

    def write_events(thread_index: int) -> None:
        barrier.wait()
        for event_index in range(writes_per_thread):
            local_tracer.log_observability_event({
                "event": "concurrent_test",
                "event_id": f"{thread_index}-{event_index}",
            })

    threads = [threading.Thread(target=write_events, args=(index,)) for index in range(thread_count)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)
        assert not thread.is_alive()

    traces = json.loads(trace_file.read_text(encoding="utf-8"))
    expected_ids = {f"{thread_index}-{event_index}" for thread_index in range(thread_count) for event_index in range(writes_per_thread)}
    assert len(traces) == thread_count * writes_per_thread
    assert {trace["event_id"] for trace in traces} == expected_ids
    assert [trace["log_id"] for trace in traces] == list(range(1, len(traces) + 1))


def test_local_tracer_handles_agent_and_shadow_events_concurrently(monkeypatch, tmp_path):
    trace_file = tmp_path / "observability_logs.json"
    monkeypatch.setattr(local_tracer, "TRACE_FILE", trace_file)
    barrier = threading.Barrier(2)

    def write_agent_events() -> None:
        barrier.wait()
        for index in range(50):
            local_tracer.log_observability_event({"event": "agent", "trace_id": f"agent-{index}"})

    def write_shadow_events() -> None:
        barrier.wait()
        for index in range(50):
            local_tracer.log_observability_event({"event": "decision_shadow", "trace_id": f"shadow-{index}"})

    threads = [threading.Thread(target=write_agent_events), threading.Thread(target=write_shadow_events)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)
        assert not thread.is_alive()

    traces = json.loads(trace_file.read_text(encoding="utf-8"))
    assert len(traces) == 100
    assert sum(trace["event"] == "agent" for trace in traces) == 50
    assert sum(trace["event"] == "decision_shadow" for trace in traces) == 50


def test_atomic_write_failure_preserves_the_previous_valid_trace_document(monkeypatch, tmp_path):
    trace_file = tmp_path / "observability_logs.json"
    original = '[{"log_id": 1, "event": "existing"}]'
    trace_file.write_text(original, encoding="utf-8")
    monkeypatch.setattr(local_tracer, "TRACE_FILE", trace_file)

    def fail_dump(*_args, **_kwargs):
        raise OSError("simulated temporary write failure")

    monkeypatch.setattr(local_tracer.json, "dump", fail_dump)
    with pytest.raises(OSError, match="simulated temporary write failure"):
        local_tracer.log_observability_event({"event": "new"})

    assert trace_file.read_text(encoding="utf-8") == original
    assert json.loads(trace_file.read_text(encoding="utf-8")) == [{"log_id": 1, "event": "existing"}]


def test_controlled_transaction_replay_isolates_orders_and_observability(monkeypatch):
    production_orders_file = order_service.ORDERS_FILE
    production_observability_file = local_tracer.TRACE_FILE
    production_orders_before = production_orders_file.read_bytes()
    production_observability_before = production_observability_file.read_bytes()
    catalog_product = {
        "product_id": "mouse-1", "name": "Mouse", "category": "Mouse", "brand": "Acme",
        "supplier": "Supplier", "rating": 4.8, "stock": 50, "delivery_days": 2, "price": 10,
    }
    plan = {
        "items": [{"product_id": "mouse-1", "name": "Mouse", "quantity": 2, "unit_price": 10, "subtotal": 20}],
        "plan_option_id": "controlled-replay-plan", "total_amount": 20, "budget": 100, "budget_status": "within_budget",
        "inventory_status": "valid", "constraint_satisfaction": "satisfied", "selectable": True,
    }
    dispatched = []

    monkeypatch.setattr(agent, "get_session_state", lambda *_: None)
    monkeypatch.setattr(agent, "should_rewrite", lambda *_: False)
    monkeypatch.setattr(agent, "parse_purchase_request", lambda *_: {
        "categories": ["Mouse"], "quantity_by_category": {"Mouse": 2}, "budget": 100,
        "revision_intent": "new_plan", "used_mock_llm": True,
    })
    monkeypatch.setattr(agent, "_retrieve_products_for_agent", lambda *_, **__: RetrievalResult(
        products=[catalog_product], evidence={"constraints_relaxed": False},
    ))
    monkeypatch.setattr(agent, "generate_procurement_plan", lambda *_, **__: deepcopy(plan))
    monkeypatch.setattr(agent, "generate_plan_options", lambda *_: [])
    monkeypatch.setattr(product_service, "load_products_from_csv", lambda: [catalog_product])
    monkeypatch.setattr(agent.LangfuseClient, "trace", lambda *_, **__: None)

    def dispatch_shadow(**kwargs):
        dispatched.append(kwargs)
        emit_shadow_audit({
            "event": "decision_shadow", "trace_id": kwargs["trace_id"], "provider": "jev",
            "shadow_attempted": True, "shadow_skipped": False, "provider_success": True,
        })
        return True

    monkeypatch.setattr(agent, "dispatch_jev_shadow", dispatch_shadow)
    temporary_root: Path
    with isolated_shadow_observation_storage() as storage:
        temporary_root = storage.root
        result = agent.run_procurement_agent("确认这个方案并下单", "controlled-replay", skip_plan_explanation=True)
        temporary_orders = json.loads(storage.orders_file.read_text(encoding="utf-8"))
        temporary_events = json.loads(storage.observability_file.read_text(encoding="utf-8"))
        assert result["type"] == "order"
        assert result["order_id"] == temporary_orders[0]["order_id"]
        assert temporary_orders[0]["stripe_session_id"].startswith("mock_")
        assert any(event.get("event") == "decision_shadow" for event in temporary_events)
        assert any(event.get("session_id") == "controlled-replay" for event in temporary_events)

    assert dispatched
    assert dispatched[0]["authoritative_decision"].label.value == "confirm_order"
    assert production_orders_file.read_bytes() == production_orders_before
    assert production_observability_file.read_bytes() == production_observability_before
    assert not temporary_root.exists()
