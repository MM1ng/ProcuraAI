"""Anonymous browser boundary; real routes and isolated transaction services."""
from copy import deepcopy
import pytest
from fastapi.testclient import TestClient
from main import app
from test_transaction_snapshot_batch1 import ctx, binding, order_payload
from app.services import order_service
from concurrent.futures import ThreadPoolExecutor
import json
import os
import subprocess
import sys
from app.services import caller_identity as identities, stripe_payment_service

ORIGIN = "http://127.0.0.1:3000"

@pytest.fixture(autouse=True)
def identity_store(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("ANONYMOUS_CALLER_ENABLED", "true")
    monkeypatch.setenv("PROCURA_IDENTITY_REGISTRY", str(tmp_path / "identity" / "registry.sqlite3"))

def browser():
    return TestClient(app, base_url="http://127.0.0.1:8000", client=("127.0.0.1", 50000))

def initialize(client):
    r = client.post("/api/caller/init", headers={"Origin": ORIGIN})
    assert r.status_code == 200, r.text
    client.headers.update({"Origin": ORIGIN, "X-CSRF-Token": r.json()["csrf_token"]})
    return r

def session(client):
    r = client.post("/api/chat/session")
    assert r.status_code == 200, r.text
    return r.json()["session_id"]

def displayed(client, sid):
    r = client.post("/api/chat", json={"session_id": sid, "message": "Recommend 2 keyboards"})
    assert r.status_code == 200, r.text
    return r.json()["recommended_plan"]

def test_old_client_has_no_transaction_or_session_authority(ctx):
    r = browser().post("/api/chat", json={"session_id": "client-chosen", "message": "Recommend 2 keyboards"})
    assert r.status_code in (401, 403)
    assert order_service.list_orders() == []

def test_readonly_context_never_creates_actor():
    client = browser()
    r = client.get("/api/caller/context")
    assert r.status_code == 401
    assert "set-cookie" not in r.headers
    assert r.headers["cache-control"] == "no-store"

def test_cookie_origin_csrf_and_no_rotation(ctx):
    a = browser()
    issued = initialize(a)
    assert "httponly" in issued.headers["set-cookie"].lower()
    assert "domain=" not in issued.headers["set-cookie"].lower()
    original = dict(a.cookies)
    for _ in range(2):
        assert a.get("/api/caller/context").json()["csrf_token"] == issued.json()["csrf_token"]
        assert dict(a.cookies) == original
    for header, value in [("Origin", "http://localhost:3000"), ("X-CSRF-Token", "forged")]:
        r = a.post("/api/chat/session", headers={header: value})
        assert r.status_code == 403

def test_other_actor_cannot_copy_full_binding_or_order(ctx):
    a, b = browser(), browser()
    initialize(a); initialize(b)
    sid = session(a); p = displayed(a, sid)
    token = a.post("/api/chat/confirm", json=binding(p, sid)).json()["confirmation_id"]
    payload = order_payload(p, token, sid)
    assert b.post("/api/chat/confirm", json=binding(p, sid)).status_code == 403
    assert b.post("/api/orders", json=payload).status_code == 403
    created = a.post("/api/orders", json=payload)
    assert created.status_code == 200, created.text
    oid = created.json()["order_id"]
    assert b.get(f"/api/orders/{oid}").status_code == 403
    assert b.get("/api/orders").json()["items"] == []
    assert b.post("/api/payments/stripe/checkout", json={"order_id": oid}).status_code == 403
    ctx.provider.assert_not_called()

def test_client_user_id_cannot_remint_confirmation(ctx):
    a = browser(); initialize(a)
    sid = session(a); p = displayed(a, sid)
    assert a.post("/api/chat/confirm", json={**binding(p, sid), "user_id": "other"}).status_code == 422

def test_ownerless_order_is_unclaimable(ctx):
    order = order_service.create_order_from_plan({"items": [{"product_id": "p1", "quantity": 2}]})
    import json
    order_service.ORDERS_FILE.write_text(json.dumps([order]), encoding="utf-8")
    a = browser(); initialize(a)
    assert a.get(f'/api/orders/{order["order_id"]}').status_code == 403
    assert a.get("/api/orders").json()["items"] == []
    assert a.post("/api/payments/stripe/checkout", json={"order_id": order["order_id"]}).status_code == 403
    assert a.post("/api/payments/confirm", json={"order_id": order["order_id"]}).status_code == 403
    ctx.provider.assert_not_called()

def make_chat_order(a):
    sid = session(a)
    p = displayed(a, sid)
    token = a.post("/api/chat/confirm", json=binding(p, sid)).json()["confirmation_id"]
    payload = order_payload(p, token, sid)
    created = a.post("/api/orders", json=payload)
    assert created.status_code == 200, created.text
    return sid, p, token, payload, created.json()

@pytest.mark.parametrize("mode", ["no-cookie", "forged-cookie", "no-csrf", "wrong-csrf", "no-origin", "wrong-origin", "expired-cookie"])
def test_mutations_fail_closed_for_invalid_browser_context(ctx, mode):
    a = browser(); initialize(a)
    headers = dict(a.headers)
    cookie = a.cookies.get(identities.COOKIE_NAME)
    b = browser()
    b.headers.update({"Origin": ORIGIN, "X-CSRF-Token": headers["x-csrf-token"]})
    if mode != "no-cookie":
        b.cookies.set(identities.COOKIE_NAME, "forged" if mode == "forged-cookie" else cookie)
    if mode == "no-csrf": del b.headers["X-CSRF-Token"]
    if mode == "wrong-csrf": b.headers["X-CSRF-Token"] = "wrong"
    if mode == "no-origin": del b.headers["Origin"]
    if mode == "wrong-origin": b.headers["Origin"] = "http://localhost:3000"
    if mode == "expired-cookie":
        import sqlite3
        with sqlite3.connect(identities.registry_path()) as db:
            db.execute("UPDATE actors SET expires_at=0")
    result = b.post("/api/chat/session")
    assert result.status_code in (401, 403)
    assert "set-cookie" not in result.headers
    assert order_service.list_orders() == []

def test_explicit_init_reuses_actor_and_invalid_cookie_cannot_switch(ctx):
    a = browser(); first = initialize(a)
    cookie = dict(a.cookies)
    second = initialize(a)
    assert second.json() == first.json()
    assert "set-cookie" not in second.headers
    assert dict(a.cookies) == cookie
    a.cookies.clear(); a.cookies.set(identities.COOKIE_NAME, "forged")
    for path, method in [("/api/caller/context", "get"), ("/api/caller/init", "post")]:
        r = getattr(a, method)(path)
        assert r.status_code == 401
        assert "set-cookie" not in r.headers

def test_anonymous_mode_and_host_fail_closed(ctx, monkeypatch):
    a = browser(); initialize(a)
    assert a.get("/api/caller/context", headers={"Host": "localhost:8000"}).status_code == 403
    monkeypatch.setenv("APP_ENV", "production")
    assert a.post("/api/caller/init").status_code == 503
    assert a.post("/api/chat/session").status_code == 503

def test_copied_session_denied_at_every_plan_entry(ctx):
    a, b = browser(), browser(); initialize(a); initialize(b)
    sid = session(a); shown = a.post("/api/chat", json={"session_id": sid, "message": "Recommend 2 keyboards"}).json()
    p, alternative = shown["recommended_plan"], shown["plan_options"][1]["plan"]
    calls = [
        ("/api/chat", {"session_id": sid, "message": "确认这个方案并下单", **binding(p, sid)}),
        ("/api/procurement/plan", {"session_id": sid, "parsed_intent": {"categories": ["Keyboard"]}}),
        ("/api/chat/optimize", {"session_id": sid, "action": "improve_quality", "parsed_intent": {}, "current_plan": p}),
        ("/api/chat/select", {**binding(p, sid), "selected_plan_id": alternative["plan_id"], "selected_plan_hash": alternative["plan_hash"], "selected_plan_version": alternative["plan_version"]}),
    ]
    for path, payload in calls:
        assert b.post(path, json=payload).status_code == 403, path
    assert order_service.list_orders() == []
    ctx.provider.assert_not_called()

def test_cart_capability_and_payment_returns_belong_to_owner(ctx, monkeypatch):
    a, b = browser(), browser(); initialize(a); initialize(b)
    quote = a.post("/api/orders/cart/quote", json={"plan": {"items": [{"product_id": "p1", "quantity": 2}]}})
    token = quote.json()["cart_token"]
    assert b.post("/api/orders/cart", json={"cart_token": token}).status_code == 403
    order = a.post("/api/orders/cart", json={"cart_token": token}).json()
    oid = order["order_id"]
    # Even mock mode may not turn another actor's callback URL into authority.
    monkeypatch.setattr(stripe_payment_service, "get_settings", lambda: type("S", (), {"use_mock_payment": True, "stripe_secret_key": "", "frontend_base_url": ORIGIN, "stripe_success_url": "", "stripe_cancel_url": ""})())
    import app.api.payments as payments
    monkeypatch.setattr(payments, "get_settings", lambda: type("S", (), {"app_env": "test", "allow_mock_payment": True, "use_mock_payment": True, "stripe_secret_key": ""})())
    for path, payload in [
        ("/api/payments/stripe/checkout", {"order_id": oid}),
        ("/api/payments/create-checkout-session", {"order_id": oid}),
        ("/api/payments/confirm", {"order_id": oid}),
        ("/api/payments/mock-success", {"order_id": oid}),
    ]:
        response = b.post(path, json=payload)
        assert response.status_code == 403 and response.json()["detail"]["code"] == "RESOURCE_NOT_OWNED", path
    assert order_service.get_order(oid)["status"] == "pending_payment"

def test_same_actor_multitab_and_concurrent_confirmation_retry(ctx):
    a, tab = browser(), browser(); initialize(a)
    tab.cookies.update(a.cookies)
    recovered = tab.get("/api/caller/context")
    tab.headers.update({"Origin": ORIGIN, "X-CSRF-Token": recovered.json()["csrf_token"]})
    sid, p, token, payload, first = make_chat_order(a)
    assert tab.post("/api/chat/confirm", json=binding(p, sid)).json()["confirmation_id"] == token
    with ThreadPoolExecutor(max_workers=4) as pool:
        result = list(pool.map(lambda _: tab.post("/api/orders", json=payload), range(8)))
    assert all(r.status_code == 200 and r.json()["order_id"] == first["order_id"] for r in result)
    assert len(order_service.list_orders()) == 1

def test_original_credential_recovers_orders_in_clean_process_new_actor_cannot(ctx):
    a = browser(); initialize(a)
    _, _, _, _, first = make_chat_order(a)
    code = """
import json, sys
from fastapi.testclient import TestClient
from main import app
from app.services.caller_identity import COOKIE_NAME
client=TestClient(app, base_url="http://127.0.0.1:8000", client=("127.0.0.1", 50000))
client.cookies.set(COOKIE_NAME, sys.stdin.read())
context=client.get("/api/caller/context")
orders=client.get("/api/orders")
print(json.dumps({"context":context.status_code, "orders":orders.status_code, "ids":[o["order_id"] for o in orders.json().get("items",[])]}))
"""
    env = dict(os.environ, PROCURA_ORDERS_FILE=str(order_service.ORDERS_FILE), PYTHONPATH=str(__import__("pathlib").Path(__file__).resolve().parents[1]))
    r = subprocess.run([sys.executable, "-c", code], input=a.cookies.get(identities.COOKIE_NAME), text=True, capture_output=True, env=env, timeout=20)
    assert r.returncode == 0, r.stderr
    result = json.loads(r.stdout.strip().splitlines()[-1])
    assert result == {"context": 200, "orders": 200, "ids": [first["order_id"]]}
    b = browser(); initialize(b)
    assert b.get("/api/orders").json()["items"] == []
    assert b.get(f'/api/orders/{first["order_id"]}').status_code == 403

def test_os_writer_lease_excludes_second_process_and_releases(tmp_path):
    from pathlib import Path
    from app.services.transaction_lock import order_writer_lease
    file = tmp_path / "separate-orders.json"; file.write_text("[]")
    code = """
import sys
from pathlib import Path
from app.services.transaction_lock import order_writer_lease
from app.services.caller_identity import CallerDenied
try:
    with order_writer_lease(Path(sys.argv[1])): print("ACQUIRED")
except CallerDenied: print("DENIED"); sys.exit(9)
"""
    env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1]))
    with order_writer_lease(file):
        denied = subprocess.run([sys.executable, "-c", code, str(file.parent / "." / file.name)], capture_output=True, text=True, env=env, timeout=20)
        assert denied.returncode == 9 and "DENIED" in denied.stdout
    released = subprocess.run([sys.executable, "-c", code, str(file)], capture_output=True, text=True, env=env, timeout=20)
    assert released.returncode == 0 and "ACQUIRED" in released.stdout
    assert Path(str(file) + ".writer.lock").exists()

def test_signed_and_unsigned_webhook_write_boundary(ctx, monkeypatch):
    a = browser(); initialize(a)
    _, _, _, _, created = make_chat_order(a)
    oid = created["order_id"]
    actor, _ = identities.resolve_credential(a.cookies.get(identities.COOKIE_NAME))
    context_token = identities.CURRENT_CALLER.set(actor)
    try:
        order_service.update_order(oid, {"stripe_session_id": "cs_test_owned"})
    finally: identities.CURRENT_CALLER.reset(context_token)
    settings = type("Settings", (), {"stripe_webhook_secret": "test-verifier-fixture"})()
    monkeypatch.setattr(stripe_payment_service, "get_settings", lambda: settings)
    event = {"id": "evt_owned", "type": "checkout.session.completed", "data": {"object": {
        "id": "cs_test_owned", "metadata": {"order_id": oid}, "payment_status": "paid", "amount_total": 2000, "currency": "usd"}}}
    def verifier(payload, signature, secret):
        if signature != "verified-fixture": raise ValueError("Invalid provider signature")
        return deepcopy(event)
    monkeypatch.setattr(stripe_payment_service, "_construct_event", verifier)
    unauthenticated = browser()
    assert unauthenticated.post("/api/payments/webhook", json=event).status_code == 200
    assert order_service.get_order(oid)["status"] == "pending_payment"
    assert unauthenticated.post("/api/payments/stripe/webhook", content=b"event", headers={"stripe-signature": "forged"}).status_code == 400
    assert order_service.get_order(oid)["status"] == "pending_payment"
    assert unauthenticated.post("/api/payments/stripe/webhook", content=b"event", headers={"stripe-signature": "verified-fixture"}).status_code == 200
    assert order_service.get_order(oid)["status"] == "paid"
    assert unauthenticated.post("/api/payments/stripe/webhook", content=b"event", headers={"stripe-signature": "verified-fixture"}).status_code == 200
    assert order_service.get_order(oid)["processed_payment_event_ids"] == ["evt_owned"]

def test_no_caller_direct_agent_or_tools_cannot_use_demo_authority(ctx):
    from app.agent.procurement_agent import run_procurement_agent
    from app.agent.tools import create_order
    token = identities.CURRENT_CALLER.set(None)
    try:
        with pytest.raises(identities.CallerDenied): run_procurement_agent("确认这个方案并下单", "s1")
        with pytest.raises(identities.CallerDenied): create_order({"items": [{"product_id": "p1", "quantity": 1}]})
    finally: identities.CURRENT_CALLER.reset(token)

def test_lifespan_without_lease_cannot_start_second_process(ctx):
    from pathlib import Path
    code = """
import sys
from fastapi.testclient import TestClient
from main import app
from app.services.caller_identity import CallerDenied
try:
    with TestClient(app): pass
except CallerDenied: print("STARTUP_DENIED"); sys.exit(9)
"""
    env = dict(os.environ, PROCURA_ORDERS_FILE=str(order_service.ORDERS_FILE), PYTHONPATH=str(Path(__file__).resolve().parents[1]))
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env, timeout=20)
    assert r.returncode == 9 and "STARTUP_DENIED" in r.stdout

def test_session_and_capabilities_restore_without_rehash(ctx):
    from app.agent import session_state as sessions
    from app.services import confirmed_transaction as tx
    a = browser(); initialize(a)
    sid = session(a); p = displayed(a, sid)
    token = a.post("/api/chat/confirm", json=binding(p, sid)).json()["confirmation_id"]
    quote = a.post("/api/orders/cart/quote", json={"plan": {"items": [{"product_id": "p1", "quantity": 1}]}}).json()
    sessions.clear_session_state(); tx.clear_transaction_capabilities()
    assert a.get(f"/api/chat/session/{sid}").status_code == 200
    assert a.post("/api/chat/confirm", json=binding(p, sid)).json()["confirmation_id"] == token
    order = a.post("/api/orders", json=order_payload(p, token, sid))
    assert order.status_code == 200
    assert sessions._SESSIONS[sid]["recommended_plan"] == p
    assert a.post("/api/orders/cart", json={"cart_token": quote["cart_token"]}).status_code == 200

def test_valid_webhook_and_raw_writes_fail_without_live_lease(ctx, monkeypatch, tmp_path):
    # A different canonical order path has no acquired OS lease.
    unleased = tmp_path / "unleased.json"
    unleased.write_text("[]")
    monkeypatch.setattr(order_service, "ORDERS_FILE", unleased)
    with pytest.raises(identities.CallerDenied, match="ORDER_WRITER_LEASE"):
        order_service._write_orders([])
    with pytest.raises(identities.CallerDenied, match="ORDER_WRITER_LEASE"):
        order_service.update_order("unknown", {"status": "paid"})
    with pytest.raises(identities.CallerDenied, match="ORDER_WRITER_LEASE"):
        stripe_payment_service.handle_stripe_webhook(b"verified-event", "verified-fixture")
    assert unleased.read_text() == "[]"

def test_revoked_actor_cannot_rotate_or_claim_legacy_user_label(ctx):
    import sqlite3
    a = browser(); initialize(a)
    _, _, _, _, created = make_chat_order(a)
    with sqlite3.connect(identities.registry_path()) as db:
        db.execute("UPDATE actors SET revoked=1 WHERE credential_digest=?", (identities.resolve_credential(a.cookies.get(identities.COOKIE_NAME))[0].credential_digest,))
    assert a.get("/api/orders").status_code == 401
    assert a.post("/api/caller/init").status_code == 401
    b = browser(); initialize(b)
    assert b.get(f'/api/orders/{created["order_id"]}', headers={"X-User-ID": created["user_id"]}).status_code == 403

def test_mock_cart_display_confirm_order_checkout_return(ctx, monkeypatch):
    import app.api.payments as payments
    settings = type("S", (), {"app_env": "test", "allow_mock_payment": True, "use_mock_payment": True,
                            "stripe_secret_key": "", "frontend_base_url": ORIGIN, "stripe_success_url": "", "stripe_cancel_url": ""})()
    monkeypatch.setattr(stripe_payment_service, "get_settings", lambda: settings)
    monkeypatch.setattr(payments, "get_settings", lambda: settings)
    a = browser(); initialize(a)
    quote = a.post("/api/orders/cart/quote", json={"plan": {"items": [{"product_id": "p1", "quantity": 1}]}}).json()
    assert quote["plan"]["total_amount"] == 10
    order = a.post("/api/orders/cart", json={"cart_token": quote["cart_token"]}).json()
    checkout = a.post("/api/payments/stripe/checkout", json={"order_id": order["order_id"]}).json()
    assert checkout["checkout_url"].startswith(ORIGIN + "/payment/success?")
    assert a.get("/api/caller/context").status_code == 200
    assert a.post("/api/payments/mock-success", json={"order_id": order["order_id"], "session_id": checkout["session_id"]}).status_code == 200
    assert a.get(f'/api/orders/{order["order_id"]}').json()["status"] == "paid"

@pytest.mark.parametrize("origin", [None, "http://localhost:3000", "https://127.0.0.1:3000", "http://127.0.0.1:3001"])
def test_bootstrap_requires_exact_origin_and_never_issues_cookie(ctx, origin):
    a = browser()
    headers = {"Origin": origin} if origin else {}
    r = a.post("/api/caller/init", headers=headers)
    assert r.status_code == 403 and "set-cookie" not in r.headers

def test_real_sdk_signature_verification_without_browser_cookie(ctx, monkeypatch):
    import hmac, hashlib, time
    import stripe
    monkeypatch.setattr(stripe_payment_service, "_stripe_module", lambda: stripe)
    a = browser(); initialize(a)
    _, _, _, _, order = make_chat_order(a)
    actor, _ = identities.resolve_credential(a.cookies.get(identities.COOKIE_NAME))
    token = identities.CURRENT_CALLER.set(actor)
    try:
        order_service.update_order(order["order_id"], {"stripe_session_id": "cs_signed_fixture"})
    finally: identities.CURRENT_CALLER.reset(token)
    settings = type("S", (), {"stripe_webhook_secret": "whsec_fixture_only"})()
    monkeypatch.setattr(stripe_payment_service, "get_settings", lambda: settings)
    # Exercise the installed SDK verifier, not a mock of signature validation.
    event = {"id": "evt_sdk_fixture", "object": "event", "type": "checkout.session.completed", "data": {"object": {
        "id": "cs_signed_fixture", "object": "checkout.session", "metadata": {"order_id": order["order_id"]},
        "payment_status": "paid", "amount_total": 2000, "currency": "usd"}}}
    payload = json.dumps(event).encode()
    stamp = str(int(time.time()))
    digest = hmac.new(b"whsec_fixture_only", stamp.encode() + b"." + payload, hashlib.sha256).hexdigest()
    client = browser()
    invalid = client.post("/api/payments/stripe/webhook", content=payload, headers={"stripe-signature": f"t={stamp},v1=forged"})
    assert invalid.status_code == 400
    assert order_service.get_order(order["order_id"])["status"] == "pending_payment"
    valid = client.post("/api/payments/stripe/webhook", content=payload, headers={"stripe-signature": f"t={stamp},v1={digest}"})
    assert valid.status_code == 200, valid.text
    assert order_service.get_order(order["order_id"])["status"] == "paid"

def test_same_snapshot_cannot_remint_second_order_by_changing_user_id(ctx):
    a = browser(); initialize(a)
    sid, p, confirmation, payload, first = make_chat_order(a)
    assert a.post("/api/chat/confirm", json={**binding(p, sid), "user_id": "attacker"}).status_code == 422
    assert a.post("/api/orders", json={**payload, "user_id": "attacker"}).status_code == 422
    assert a.post("/api/chat/confirm", json=binding(p, sid)).json()["confirmation_id"] == confirmation
    assert a.post("/api/orders", json=payload).json()["order_id"] == first["order_id"]
    assert len(order_service.list_orders()) == 1

def test_unknown_confirmation_does_not_reuse_an_owned_existing_order(ctx):
    a = browser(); initialize(a)
    _, _, _, payload, _ = make_chat_order(a)
    response = a.post("/api/orders", json={**payload, "confirmation_id": "unissued"})
    assert response.status_code == 409
    assert len(order_service.list_orders()) == 1

def test_expired_payment_return_never_rotates_actor_or_updates_order(ctx):
    import sqlite3
    a = browser(); initialize(a)
    _, _, _, _, created = make_chat_order(a)
    with sqlite3.connect(identities.registry_path()) as db:
        db.execute("UPDATE actors SET expires_at=0")
    context = a.get("/api/caller/context")
    assert context.status_code == 401 and "set-cookie" not in context.headers
    response = a.post("/api/payments/mock-success", json={"order_id": created["order_id"]})
    assert response.status_code == 401 and "set-cookie" not in response.headers
    assert order_service.get_order(created["order_id"])["status"] == "pending_payment"
    assert len(order_service.list_orders()) == 1

def test_clean_process_restart_preserves_confirmation_idempotency_and_ownership(ctx, monkeypatch, tmp_path):
    from pathlib import Path
    from app.services.transaction_lock import order_writer_lease
    restarted_orders = tmp_path / "restart-orders.json"
    restarted_orders.write_text("[]")
    monkeypatch.setattr(order_service, "ORDERS_FILE", restarted_orders)
    a = browser()
    with order_writer_lease(restarted_orders):
        initialize(a)
        sid, p, confirmation, payload, created = make_chat_order(a)
    code = """
import json, sys
from fastapi.testclient import TestClient
from main import app
from app.services import product_service
from app.services.caller_identity import COOKIE_NAME
input_data=json.loads(sys.stdin.read())
product_service.load_products_from_csv=lambda:input_data["catalog"]
with TestClient(app,base_url="http://127.0.0.1:8000",client=("127.0.0.1",50000)) as client:
    client.cookies.set(COOKIE_NAME,input_data["credential"])
    context=client.get("/api/caller/context")
    client.headers.update({"Origin":"http://127.0.0.1:3000","X-CSRF-Token":context.json()["csrf_token"]})
    retry=client.post("/api/orders",json=input_data["payload"])
    own=client.get("/api/orders")
    other=TestClient(app,base_url="http://127.0.0.1:8000",client=("127.0.0.1",50000))
    other.post("/api/caller/init",headers={"Origin":"http://127.0.0.1:3000"})
    denied=other.get("/api/orders/"+input_data["order_id"])
    print(json.dumps({"context":context.status_code,"rotated":"set-cookie" in context.headers,"retry":retry.status_code,"same_order":retry.json().get("order_id")==input_data["order_id"],"own_count":own.json()["total"],"other_count":other.get("/api/orders").json()["total"],"other_detail":denied.status_code}))
"""
    env = dict(os.environ, PROCURA_ORDERS_FILE=str(restarted_orders), PYTHONPATH=str(Path(__file__).resolve().parents[1]))
    data = {"credential": a.cookies.get(identities.COOKIE_NAME), "catalog": ctx.products,
            "payload": payload, "order_id": created["order_id"]}
    r = subprocess.run([sys.executable, "-c", code], input=json.dumps(data), capture_output=True, text=True, env=env, timeout=20)
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout.strip().splitlines()[-1]) == {"context": 200, "rotated": False, "retry": 200,
        "same_order": True, "own_count": 1, "other_count": 0, "other_detail": 403}

def test_non_loopback_connection_cannot_bootstrap_insecure_cookie(ctx):
    client = TestClient(app, base_url="http://127.0.0.1:8000", client=("192.0.2.10", 50000))
    response = client.post("/api/caller/init", headers={"Origin": ORIGIN})
    assert response.status_code == 403 and "set-cookie" not in response.headers

@pytest.mark.parametrize("source", ["chat", "cart"])
def test_idempotent_retry_cannot_claim_order_with_missing_owner(ctx, source):
    a = browser(); initialize(a)
    if source == "chat":
        _, _, _, payload, created = make_chat_order(a)
        endpoint = "/api/orders"
    else:
        quote = a.post("/api/orders/cart/quote", json={"plan": {"items": [{"product_id": "p1", "quantity": 1}]}}).json()
        payload = {"cart_token": quote["cart_token"]}
        endpoint = "/api/orders/cart"
        created = a.post(endpoint, json=payload).json()
    saved = order_service.list_orders()
    saved[0].pop("owner_actor_id")
    order_service.ORDERS_FILE.write_text(json.dumps(saved), encoding="utf-8")
    before = order_service.ORDERS_FILE.read_bytes()
    assert a.post(endpoint, json=payload).status_code == 403
    assert order_service.ORDERS_FILE.read_bytes() == before
