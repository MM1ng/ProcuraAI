from __future__ import annotations

import time
from copy import deepcopy
from unittest.mock import Mock

import pytest

import app.agent.procurement_agent as agent
import app.scripts.audit_shadow_disagreements as audit_module
import app.scripts.run_shadow_observation as runner_module
from app.decision.gateway import ShadowConfig
from app.decision.schemas import DecisionResult, IntentLabel
from app.rag.retriever import RetrievalResult
from app.services import product_service


def _result() -> DecisionResult:
    return DecisionResult(
        label=IntentLabel.RECOMMEND,
        provider="jev",
        confidence=0.9,
        probabilities={"recommend": 0.9},
        model="jev-test",
        latency_ms=5.0,
        metadata={"request_id": "runner-test"},
    )


def _configure_agent(monkeypatch):
    product = {"product_id": "mouse-1", "name": "Mouse", "category": "Mouse", "brand": "Acme", "supplier": "Supplier", "rating": 4.8, "stock": 50, "delivery_days": 2, "price": 10}
    plan = {"items": [{"product_id": "mouse-1", "quantity": 2, "unit_price": 10, "subtotal": 20}], "total_amount": 20, "budget_status": "within_budget"}
    monkeypatch.setattr(agent, "get_session_state", lambda *_: None)
    monkeypatch.setattr(agent, "should_rewrite", lambda *_: False)
    monkeypatch.setattr(agent, "parse_purchase_request", lambda *_: {"categories": ["Mouse"], "quantity_by_category": {"Mouse": 2}, "revision_intent": "new_plan", "used_mock_llm": True})
    monkeypatch.setattr(agent, "_retrieve_products_for_agent", lambda *_, **__: RetrievalResult(products=[product], evidence={"constraints_relaxed": False}))
    monkeypatch.setattr(agent, "generate_procurement_plan", lambda *_, **__: deepcopy(plan))
    monkeypatch.setattr(agent, "generate_plan_options", lambda *_: [])
    monkeypatch.setattr(product_service, "load_products_from_csv", lambda: [product])
    monkeypatch.setattr(agent.LangfuseClient, "trace", lambda *_, **__: None)


def test_collector_wrapper_receives_real_gateway_record_and_forwards(monkeypatch):
    forwarded = Mock()
    runner = runner_module.ShadowObservationRunner(
        config=ShadowConfig(True, 100, 1.0, True, 1),
        provider_factory=lambda: type("Provider", (), {"classify_intent": lambda self, _: _result()})(),
        audit_forward=forwarded,
    )
    decision = runner_module.procurement_agent.resolve_authoritative_intent("recommend mice", {"revision_intent": "new_plan"}, "recommendation_plan")
    with runner._patched_agent_dispatch():
        assert runner_module.procurement_agent.dispatch_jev_shadow(text="recommend mice", trace_id="collector", authoritative_decision=decision)
    event = runner.collector.wait_for_trace("collector", 1)
    assert event is not None and event["event"] == "decision_shadow"
    forwarded.assert_called_once_with(event)


def test_wait_for_trace_returns_record_or_timeout():
    collector = runner_module.ShadowEventCollector(forward=lambda _: None)
    assert collector.wait_for_trace("missing", 0.01) is None
    collector.emit({"event": "decision_shadow_skip", "trace_id": "present"})
    assert collector.wait_for_trace("present", 0.01)["trace_id"] == "present"


def test_slow_provider_has_no_late_production_audit_write(monkeypatch):
    _configure_agent(monkeypatch)
    production_trace = runner_module.PROJECT_ROOT / "data" / "observability_logs.json"
    before = production_trace.read_bytes()

    class SlowProvider:
        def classify_intent(self, _):
            time.sleep(0.08)
            return _result()

    runner = runner_module.ShadowObservationRunner(
        config=ShadowConfig(True, 10, 1.0, True, 1),
        provider_factory=SlowProvider,
        audit_forward=lambda _: None,
    )
    result = runner.run_cases([runner_module.ReplayCase("slow", "recommend mice")])
    time.sleep(0.12)
    assert result.harness_errors == []
    assert result.production_observability_unchanged is True
    assert production_trace.read_bytes() == before


def test_mini_replay_keeps_production_data_unchanged(monkeypatch):
    _configure_agent(monkeypatch)
    runner = runner_module.ShadowObservationRunner(
        config=ShadowConfig(True, 100, 1.0, True, 1),
        provider_factory=lambda: type("Provider", (), {"classify_intent": lambda self, _: _result()})(),
        audit_forward=lambda _: None,
    )
    result = runner.run_cases([
        runner_module.ReplayCase("one", "recommend mice"),
        runner_module.ReplayCase("two", "recommend monitors"),
    ])
    assert result.harness_errors == []
    assert result.candidate_requests == 2
    assert result.collector_event_count == 2
    assert result.production_orders_unchanged is True
    assert result.production_observability_unchanged is True
    assert all(set(record) == {
        "case_id", "retried", "trace_id", "event", "authoritative_label",
        "authoritative_label_resolution", "shadow_label", "agreement",
        "transaction_escalation_disagreement", "transaction_deescalation_disagreement",
        "provider_success", "provider_error_type", "shadow_latency_ms",
    } for record in result.records)


def test_merge_replaces_a_failed_case_with_a_successful_retry():
    failed = {"case_id": "case-1", "provider_success": False, "provider_error_type": "timeout", "retried": False}
    success = {"case_id": "case-1", "provider_success": True, "provider_error_type": None, "retried": True}
    assert runner_module.merge_records([failed], [success]) == [success]
    assert runner_module._provider_error_type_distribution([failed, success]) == {"timeout": 1}
    assert runner_module.summarize_records([success]) == {
        "record_count": 1, "shadow_successes": 1, "shadow_failures": 0,
        "agreement_count": 0, "agreement_rate": 0.0,
        "latency_mean_ms": 0.0, "latency_p50_ms": 0.0, "latency_p95_ms": 0.0,
    }


def test_audit_distinguishes_router_miss_from_jev_upgrade_against_truth():
    records = [
        {"case_id": "router-miss", "provider_success": True, "agreement": False, "authoritative_label": "recommend", "shadow_label": "payment", "transaction_escalation_disagreement": True, "transaction_deescalation_disagreement": False},
        {"case_id": "jev-upgrade", "provider_success": True, "agreement": False, "authoritative_label": "recommend", "shadow_label": "payment", "transaction_escalation_disagreement": True, "transaction_deescalation_disagreement": False},
    ]
    report = audit_module.audit_records(records, {"router-miss": "payment", "jev-upgrade": "recommend"})
    assert report["jev_transaction_upgrade_vs_truth_count"] == 1
    assert report["escalation_classification_counts"] == {
        "jev_equals_truth_router_miss": 1,
        "router_equals_truth_jev_genuine_upgrade": 1,
    }
    assert report["deescalation_shadow_x_truth_cross_table"] == {}
