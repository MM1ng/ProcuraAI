"""Real HTTP/agent/session/order/checkout composition with isolated persistence."""
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

import app.agent.procurement_agent as agent
import app.api.chat as chat_api
from app.agent import session_state as sessions
from app.services import order_service, product_service, stripe_payment_service
from main import app


def plan(product="p1", quantity=2):
    price = 10 if product == "p1" else 15
    return {"plan_option_id": "plan_b" if product == "p1" else "plan_a",
            "items": [{"product_id": product, "name": product, "quantity": quantity,
                       "unit_price": price, "subtotal": price * quantity, "stock": 20, "delivery_days": 3}],
            "total_amount": price * quantity, "budget": 100,
            "budget_status": "within_budget", "inventory_status": "valid",
            "constraint_satisfaction": "satisfied", "selectable": True}


@pytest.fixture
def ctx(monkeypatch):
    sessions.clear_session_state()
    products = [{"product_id": p, "name": p, "category": "Keyboard", "price": price,
                 "stock": 20, "delivery_days": 3, "rating": 4.5}
                for p, price in [("p1", 10), ("p2", 15)]]
    monkeypatch.setattr(product_service, "load_products_from_csv", lambda: deepcopy(products))
    monkeypatch.setattr(agent, "parse_purchase_request", lambda *_: {
        "categories": ["Keyboard"], "budget": 100, "revision_intent": "new_plan",
        "quantity_by_category": {"Keyboard": 2}, "used_mock_llm": True})
    monkeypatch.setattr(agent, "retrieve_products", lambda *_, **__: deepcopy(products))
    monkeypatch.setattr(chat_api, "retrieve_products", lambda *_, **__: deepcopy(products))
    monkeypatch.setattr(agent, "generate_procurement_plan", lambda *_, **__: plan())
    options = lambda *_: [{"id": "plan_b", "strategy": "balanced", "plan": plan()},
                         {"id": "plan_a", "strategy": "premium", "plan": plan("p2")}]
    monkeypatch.setattr(agent, "generate_plan_options", options)
    monkeypatch.setattr(chat_api, "generate_plan_options", options)
    monkeypatch.setattr(agent, "generate_plan_explanation", lambda *_, **__: {"content": "Displayed plan", "used_mock_llm": True})
    monkeypatch.setattr(agent.LangfuseClient, "trace", lambda *_, **__: None)
    monkeypatch.setattr(agent, "dispatch_jev_shadow", lambda **_: None)
    monkeypatch.setattr(stripe_payment_service, "get_settings", lambda: SimpleNamespace(
        use_mock_payment=False, stripe_secret_key="sk_test_fixture", stripe_success_url="",
        stripe_cancel_url="", frontend_base_url="http://localhost:3000"))
    provider = Mock(return_value=SimpleNamespace(id="cs_test_batch1", url="https://payment.invalid/test"))
    monkeypatch.setattr(stripe_payment_service, "_stripe_module", lambda: SimpleNamespace(
        checkout=SimpleNamespace(Session=SimpleNamespace(create=provider))))
    from app.services.caller_identity import CURRENT_CALLER, COOKIE_NAME
    # The browser credential is obtained only from the explicit HTTP initializer.
    client = TestClient(app, base_url="http://127.0.0.1:8000", client=("127.0.0.1", 50000))
    response = client.post("/api/caller/init", headers={"Origin": "http://127.0.0.1:3000"})
    assert response.status_code == 200
    from app.services.caller_identity import resolve_credential
    caller, record = resolve_credential(client.cookies.get(COOKIE_NAME))
    client.headers.update({"Origin": "http://127.0.0.1:3000", "X-CSRF-Token": record["csrf_token"]})
    context_token = CURRENT_CALLER.set(caller)
    # Stable fixture IDs retain the original tamper/concurrency assertions.
    # Production IDs are exclusively issued by /api/chat/session.
    for sid in ("s1", "s2"):
        sessions._SESSIONS[sid] = {"owner_actor_id": caller.actor_id, "parsed_intent": {}, "recommended_plan": {}}
    yield SimpleNamespace(client=client, products=products, provider=provider, caller=caller)
    CURRENT_CALLER.reset(context_token)
    sessions.clear_session_state()


def display(ctx, session="s1"):
    r = ctx.client.post("/api/chat", json={"session_id": session, "message": "Recommend 2 keyboards"})
    assert r.status_code == 200
    return r.json()


def binding(p, session="s1"):
    return {"session_id": session, "plan_id": p["plan_id"], "plan_hash": p["plan_hash"], "plan_version": p["plan_version"]}


def confirm(ctx, p, session="s1"):
    r = ctx.client.post("/api/chat/confirm", json=binding(p, session))
    assert r.status_code == 200, r.text
    return r.json()["confirmation_id"]


def order_payload(p, token, session="s1"):
    return {**binding(p, session), "confirmation_id": token, "plan": p}


def assert_no_side_effects(ctx):
    assert order_service.list_orders() == []
    ctx.provider.assert_not_called()


def test_agent_rejects_tampered_original_without_rehash_or_save(ctx, monkeypatch):
    p = display(ctx)["recommended_plan"]
    sessions._SESSIONS["s1"]["recommended_plan"]["items"][0]["quantity"] = 3
    before = sessions.get_session_state("s1")
    rewrite = Mock(side_effect=AssertionError("transaction must not rewrite"))
    monkeypatch.setattr(agent, "should_rewrite", rewrite)
    r = ctx.client.post("/api/chat", json={"message": "确认这个方案并下单", **binding(p), "confirmation_id": "old-confirmation"})
    assert r.status_code == 200
    assert r.json()["error_code"] == "PLAN_SNAPSHOT_INVALID"
    assert "plan_snapshot_tampered" in r.json()["snapshot_drift"]
    assert sessions.get_session_state("s1") == before
    rewrite.assert_not_called()
    assert_no_side_effects(ctx)


@pytest.mark.parametrize("field,value", [("plan_id", None), ("plan_id", "wrong"), ("plan_hash", None),
    ("plan_hash", "wrong"), ("plan_version", None), ("plan_version", 999)])
def test_orders_require_exact_display_binding(ctx, field, value):
    p = display(ctx)["recommended_plan"]
    payload = order_payload(p, "unissued")
    payload[field] = value
    if field == "plan_id":
        payload["plan"]["plan_id"] = value
    r = ctx.client.post("/api/orders", json=payload)
    assert r.status_code in (409, 422)
    assert_no_side_effects(ctx)


def test_stripping_all_chat_binding_does_not_become_cart(ctx):
    p = display(ctx)["recommended_plan"]
    for payload in ({"plan": p}, {"plan": {"items": [{"product_id": "p1", "quantity": 2}]}}):
        assert ctx.client.post("/api/orders", json=payload).status_code == 409
    assert_no_side_effects(ctx)


@pytest.mark.parametrize("mode", ["default", "alternative", "optimized"])
def test_display_confirm_order_checkout_composition(ctx, mode):
    shown = display(ctx)
    p = shown["recommended_plan"]
    if mode == "alternative":
        alternative = shown["plan_options"][1]["plan"]
        r = ctx.client.post("/api/chat/select", json={**binding(p), "selected_plan_id": alternative["plan_id"],
            "selected_plan_hash": alternative["plan_hash"], "selected_plan_version": alternative["plan_version"]})
        assert r.status_code == 200, r.text
        p = r.json()["recommended_plan"]
        assert p["items"][0]["product_id"] == "p2"
    elif mode == "optimized":
        r = ctx.client.post("/api/chat/optimize", json={"action": "improve_quality", "session_id": "s1",
            "parsed_intent": shown["parsed_intent"], "current_plan": p})
        assert r.status_code == 200, r.text
        p = r.json()["recommended_plan"]
        assert p["plan_version"] > shown["recommended_plan"]["plan_version"]
    assert sessions.get_session_state("s1")["recommended_plan"] == p
    token = confirm(ctx, p)
    payload = order_payload(p, token)
    first = ctx.client.post("/api/orders", json=payload)
    assert first.status_code == 200, first.text
    second = ctx.client.post("/api/orders", json=payload)
    assert second.json()["order_id"] == first.json()["order_id"]
    assert len(order_service.list_orders()) == 1
    o = first.json()
    assert o["plan_id"] == o["procurement_plan"]["plan_id"] == p["plan_id"]
    r = ctx.client.post("/api/payments/stripe/checkout", json={"order_id": o["order_id"]})
    assert r.status_code == 200, r.text
    assert ctx.provider.call_args.kwargs["metadata"]["plan_id"] == p["plan_id"]
    assert ctx.provider.call_args.kwargs["metadata"]["total_amount"] == f'{p["total_amount"]:.2f}'


def test_old_confirmation_after_concurrent_selection_requires_reconfirmation(ctx):
    shown = display(ctx)
    p = shown["recommended_plan"]
    token = confirm(ctx, p)
    sessions.save_session_state("s1", {}, plan("p2"), ctx.products, "concurrent-update")
    before = sessions.get_session_state("s1")
    r = ctx.client.post("/api/orders", json=order_payload(p, token))
    assert r.status_code == 409
    assert sessions.get_session_state("s1") == before
    assert_no_side_effects(ctx)


def test_concurrent_confirmation_retries_create_one_order(ctx):
    p = display(ctx)["recommended_plan"]
    payload = order_payload(p, confirm(ctx, p))
    with ThreadPoolExecutor(max_workers=4) as pool:
        responses = list(pool.map(lambda _: ctx.client.post("/api/orders", json=payload), range(8)))
    assert all(r.status_code == 200 for r in responses)
    assert len({r.json()["order_id"] for r in responses}) == 1
    assert len(order_service.list_orders()) == 1


@pytest.mark.parametrize("field,value,reason", [("price", 11, "price_changed:p1"),
    ("stock", 1, "stock_changed:p1"), ("stock", 19, "stock_changed:p1"), ("delivery_days", 7, "delivery_changed:p1")])
def test_drift_blocks_order_and_checkout(ctx, field, value, reason):
    p = display(ctx)["recommended_plan"]
    token = confirm(ctx, p)
    o = ctx.client.post("/api/orders", json=order_payload(p, token)).json()
    ctx.products[0][field] = value
    assert ctx.client.post("/api/orders", json=order_payload(p, token)).status_code == 409
    assert ctx.client.post("/api/payments/stripe/checkout", json={"order_id": o["order_id"]}).status_code == 409
    ctx.provider.assert_not_called()


@pytest.mark.parametrize("message", ["不要确认这个方案并下单", "如果确认这个方案并下单会怎样？", "How do I pay?", "What payment options are available?"])
def test_safety_negatives_have_no_side_effects_with_valid_confirmation(ctx, message):
    p = display(ctx)["recommended_plan"]
    token = confirm(ctx, p)
    r = ctx.client.post("/api/chat", json={"message": message, **binding(p), "confirmation_id": token})
    assert r.status_code == 200
    assert r.json()["order_id"] is None
    assert_no_side_effects(ctx)


def test_agent_confirm_then_pay_reuses_same_order(ctx):
    p = display(ctx)["recommended_plan"]
    token = confirm(ctx, p)
    r = ctx.client.post("/api/chat", json={"message": "确认这个方案并下单", **binding(p), "confirmation_id": token})
    assert r.status_code == 200
    assert r.json()["order_id"], r.text
    assert r.json()["checkout_url"] is None
    r2 = ctx.client.post("/api/chat", json={"message": "Pay now", **binding(p), "confirmation_id": token})
    assert r2.json()["order_id"] == r.json()["order_id"]
    assert r2.json()["checkout_url"]
    assert len(order_service.list_orders()) == 1


def test_independent_cart_requires_server_quote_and_keeps_guard(ctx):
    payload = {"plan": {"items": [{"product_id": "p1", "quantity": 2}]}}
    assert ctx.client.post("/api/orders/cart", json=payload).status_code in (409, 422)
    quote = ctx.client.post("/api/orders/cart/quote", json=payload)
    assert quote.status_code == 200, quote.text
    r = ctx.client.post("/api/orders/cart", json={"cart_token": quote.json()["cart_token"]})
    assert r.status_code == 200, r.text
    assert r.json()["total_amount"] == 20
    ctx.products[0]["stock"] = 1
    blocked = ctx.client.post("/api/orders/cart/quote", json=payload)
    assert blocked.status_code == 409
    assert blocked.json()["detail"]["code"] == "PLAN_NOT_EXECUTABLE"


def test_expired_snapshot_rejected_without_refresh(ctx):
    from datetime import datetime, timedelta, timezone
    p = display(ctx)["recommended_plan"]
    token = confirm(ctx, p)
    sessions._SESSIONS["s1"]["recommended_plan"]["created_at"] = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    before = sessions.get_session_state("s1")
    r = ctx.client.post("/api/chat", json={"message": "Pay now", **binding(p), "confirmation_id": token})
    assert "plan_snapshot_expired" in r.json()["snapshot_drift"]
    assert sessions.get_session_state("s1") == before
    assert_no_side_effects(ctx)


def test_confirmation_cannot_be_forged_or_moved_to_another_session_or_user(ctx):
    p = display(ctx)["recommended_plan"]
    token = confirm(ctx, p)
    other = display(ctx, "s2")["recommended_plan"]
    for payload in [order_payload(p, "unissued"), order_payload(other, token, "s2"),
                    {**order_payload(p, token), "user_id": "different-user"}]:
        assert ctx.client.post("/api/orders", json=payload).status_code in (409, 422)
    assert_no_side_effects(ctx)


def test_unselected_option_cannot_trade_by_local_switch(ctx):
    shown = display(ctx)
    alternative = shown["plan_options"][1]["plan"]
    assert ctx.client.post("/api/chat/confirm", json=binding(alternative)).status_code == 409
    assert ctx.client.post("/api/orders", json=order_payload(alternative, "unissued")).status_code == 409
    assert_no_side_effects(ctx)


def test_update_between_agent_read_and_execution_is_rejected(ctx, monkeypatch):
    p = display(ctx)["recommended_plan"]
    token = confirm(ctx, p)
    parser = agent.parse_purchase_request
    def update_during_parse(*args):
        sessions.save_session_state("s1", {}, plan("p2"), ctx.products, "concurrent")
        return parser(*args)
    monkeypatch.setattr(agent, "parse_purchase_request", update_during_parse)
    r = ctx.client.post("/api/chat", json={"message": "确认这个方案并下单", **binding(p), "confirmation_id": token})
    assert r.json()["error_code"] == "PLAN_SNAPSHOT_INVALID"
    assert sessions.get_session_state("s1")["recommended_plan"]["items"][0]["product_id"] == "p2"
    assert_no_side_effects(ctx)


def test_quick_optimization_uses_registered_context_and_rejects_stale_binding(ctx):
    shown = display(ctx)
    p = shown["recommended_plan"]
    forged = {**p, "items": [{"product_id": "untrusted", "quantity": 999}]}
    r = ctx.client.post("/api/chat/optimize", json={"action": "improve_quality", "session_id": "s1",
        "parsed_intent": {"budget": 1}, "current_plan": forged})
    assert r.status_code == 200
    assert r.json()["parsed_intent"]["budget"] == 100
    again = ctx.client.post("/api/chat/optimize", json={"action": "improve_quality", "session_id": "s1",
        "parsed_intent": {}, "current_plan": p})
    assert again.status_code == 409


def test_chat_explicit_confirmation_with_display_binding_issues_server_confirmation(ctx):
    """Migration v2: retain the historical case, require prior endpoint signing."""
    p = display(ctx)["recommended_plan"]
    r = ctx.client.post("/api/chat", json={"message": "确认这个方案并下单", **binding(p)})
    assert r.json()["order_id"] is None, r.text
    assert r.json()["error_code"] == "PLAN_SNAPSHOT_INVALID"
    assert_no_side_effects(ctx)
    token = confirm(ctx, p)
    r = ctx.client.post("/api/chat", json={"message": "确认这个方案并下单", **binding(p), "confirmation_id": token})
    assert r.json()["order_id"], r.text
    saved = order_service.get_order(r.json()["order_id"])
    assert saved["confirmation_binding"]["plan_version"] == p["plan_version"]
    assert saved["confirmation_id"]
    assert saved["confirmation_id"] == token
    retry = ctx.client.post("/api/chat", json={"message": "确认这个方案并下单", **binding(p), "confirmation_id": token})
    assert retry.json()["order_id"] == saved["order_id"]
    ctx.provider.assert_not_called()


def test_selection_cannot_use_unseen_changed_alternative(ctx):
    shown = display(ctx)
    p, target = shown["recommended_plan"], shown["plan_options"][1]["plan"]
    sessions._SESSIONS["s1"]["plan_options"][1]["plan"]["items"][0]["quantity"] = 3
    # Even a newly hashed alternative cannot be substituted for the shown one.
    altered = sessions._SESSIONS["s1"]["plan_options"][1]["plan"]
    altered["plan_hash"] = sessions.calculate_plan_hash(altered)
    r = ctx.client.post("/api/chat/select", json={**binding(p), "selected_plan_id": target["plan_id"],
        "selected_plan_hash": target["plan_hash"], "selected_plan_version": target["plan_version"]})
    assert r.status_code == 409
    assert sessions.get_session_state("s1")["plan_id"] == p["plan_id"]


def test_expired_display_can_be_regenerated_and_reconfirmed(ctx):
    from datetime import datetime, timedelta, timezone
    old = display(ctx)["recommended_plan"]
    sessions._SESSIONS["s1"]["recommended_plan"]["created_at"] = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    new = display(ctx)["recommended_plan"]
    assert new["plan_version"] > old["plan_version"]
    assert confirm(ctx, new)


@pytest.mark.parametrize("field,value", [("plan_id", None), ("plan_id", "wrong"), ("plan_hash", None),
    ("plan_hash", "wrong"), ("plan_version", None), ("plan_version", 999)])
def test_agent_requires_exact_binding_without_snapshot_mutation(ctx, monkeypatch, field, value):
    p = display(ctx)["recommended_plan"]
    before = sessions.get_session_state("s1")
    forbidden = Mock(side_effect=AssertionError("confirmation cannot regenerate or save"))
    for name in ("with_plan_snapshot", "save_session_state", "rewrite_query", "_retrieve_products_for_agent", "generate_procurement_plan", "generate_plan_options"):
        monkeypatch.setattr(agent, name, forbidden)
    payload = {"message": "Pay now", **binding(p)}
    payload[field] = value
    r = ctx.client.post("/api/chat", json=payload)
    assert r.status_code == 200
    assert r.json()["error_code"] == "PLAN_SNAPSHOT_INVALID"
    forbidden.assert_not_called()
    assert sessions.get_session_state("s1") == before
    assert_no_side_effects(ctx)


def test_catalog_changes_during_order_rebuild_are_rejected(ctx, monkeypatch):
    p = display(ctx)["recommended_plan"]
    token = confirm(ctx, p)
    calls = 0
    def racing_catalog():
        nonlocal calls
        calls += 1
        if calls == 2:
            ctx.products[0]["price"] = 11
        return deepcopy(ctx.products)
    monkeypatch.setattr(product_service, "load_products_from_csv", racing_catalog)
    r = ctx.client.post("/api/orders", json=order_payload(p, token))
    assert r.status_code == 409
    assert_no_side_effects(ctx)


def test_cart_quote_cannot_change_price_during_order_rebuild(ctx, monkeypatch):
    quote = ctx.client.post("/api/orders/cart/quote", json={"plan": {"items": [{"product_id": "p1", "quantity": 2}]}}).json()
    calls = 0
    def racing_catalog():
        nonlocal calls
        calls += 1
        if calls == 2:
            ctx.products[0]["price"] = 11
        return deepcopy(ctx.products)
    monkeypatch.setattr(product_service, "load_products_from_csv", racing_catalog)
    r = ctx.client.post("/api/orders/cart", json={"cart_token": quote["cart_token"]})
    assert r.status_code == 409
    assert_no_side_effects(ctx)


def test_cart_aggregated_stock_drift_blocks_checkout(ctx):
    quote = ctx.client.post("/api/orders/cart/quote", json={"plan": {"items": [
        {"product_id": "p1", "quantity": 6}, {"product_id": "p1", "quantity": 6}]}}).json()
    o = ctx.client.post("/api/orders/cart", json={"cart_token": quote["cart_token"]}).json()
    ctx.products[0]["stock"] = 10
    r = ctx.client.post("/api/payments/stripe/checkout", json={"order_id": o["order_id"]})
    assert r.status_code == 409
    ctx.provider.assert_not_called()


@pytest.mark.parametrize("mode", ["default", "alternative", "optimized"])
def test_real_planner_api_agent_order_checkout_chain(ctx, monkeypatch, mode):
    from app.agent.plan_generator import generate_procurement_plan
    from app.agent.plan_variants import generate_plan_options
    monkeypatch.setattr(agent, "generate_procurement_plan", generate_procurement_plan)
    monkeypatch.setattr(agent, "generate_plan_options", generate_plan_options)
    monkeypatch.setattr(chat_api, "generate_plan_options", generate_plan_options)
    shown = display(ctx)
    p = shown["recommended_plan"]
    if mode == "alternative":
        target = next(o["plan"] for o in shown["plan_options"] if o["plan"]["plan_id"] != p["plan_id"])
        r = ctx.client.post("/api/chat/select", json={**binding(p), "selected_plan_id": target["plan_id"],
            "selected_plan_hash": target["plan_hash"], "selected_plan_version": target["plan_version"]})
        assert r.status_code == 200, r.text
        p = r.json()["recommended_plan"]
    elif mode == "optimized":
        r = ctx.client.post("/api/chat/optimize", json={"action": "improve_quality", "session_id": "s1",
            "parsed_intent": shown["parsed_intent"], "current_plan": p})
        assert r.status_code == 200, r.text
        p = r.json()["recommended_plan"]
    token = confirm(ctx, p)
    r = ctx.client.post("/api/chat", json={"message": "确认这个方案并下单", **binding(p), "confirmation_id": token})
    assert r.json()["order_id"], r.text
    assert ctx.provider.call_count == 0
    paid = ctx.client.post("/api/chat", json={"message": "Pay now", **binding(p), "confirmation_id": token})
    assert paid.json()["order_id"] == r.json()["order_id"]
    assert paid.json()["checkout_url"]
    assert len(order_service.list_orders()) == 1
    assert order_service.list_orders()[0]["plan_id"] == p["plan_id"]
    assert ctx.provider.call_args.kwargs["metadata"]["plan_id"] == p["plan_id"]
