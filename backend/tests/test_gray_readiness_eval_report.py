from app.scripts.run_gray_readiness_eval import _summarize


def test_disputed_gold_is_excluded_from_provisional_lift_and_queued():
    cases = [
        {"id": "payment-008", "text": "这个订单怎么支付", "label": "payment"},
        {"id": "payment-001", "text": "去付款", "label": "payment"},
    ]
    records = [
        {"case_id": "payment-008", "provider_success": True,
         "authoritative_label": "clarify", "shadow_label": "clarify",
         "provider_call_elapsed_ms": 10.0},
        {"case_id": "payment-001", "provider_success": True,
         "authoritative_label": "recommend", "shadow_label": "payment",
         "provider_call_elapsed_ms": 12.0},
    ]
    summary, joined, disputes = _summarize("dev", cases, records)
    assert summary["sample_count"] == 2
    assert summary["scored_provisionally"] == 1
    assert summary["known_gold_uncertain"] == 1
    assert summary["jev"]["per_class"]["payment"]["true_positive"] == 1
    assert joined[0]["attribution"] == "gold_uncertain"
    assert joined[1]["attribution"] == "baseline_error_provisional"
    assert {row["case_id"] for row in disputes} == {"dev/payment-008", "dev/payment-001"}


def test_provider_failure_is_not_counted_as_safe_prediction():
    cases = [{"id": "negative-001", "text": "不要付款", "label": "clarify"}]
    records = [{"case_id": "negative-001", "provider_success": False,
                "authoritative_label": "clarify", "shadow_label": None,
                "provider_error_type": "timeout", "provider_call_elapsed_ms": 4000.0}]
    summary, joined, _ = _summarize("test", cases, records)
    assert summary["provider_failures"] == 1
    assert summary["jev"]["per_class"]["clarify"]["recall"] == 0
    assert joined[0]["attribution"] == "provider_failure_or_missing_record"
