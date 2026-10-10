"""Real loopback HTTP across OS-process exits; no identity/snapshot/order mocks.

The child entry point lives here so evidence runs need no disposable Python helper.
Only the model/vector provider is local; parsing, planning and transaction gates
are the application's implementations. Credentials stay in client memory.
"""
import hashlib
import json
import os
from pathlib import Path
import signal
import socket
import sqlite3
import subprocess
import sys
import time
from uuid import uuid4


def _serve(root):
    root = Path(root).resolve()
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    for name in ("OPENAI_API_KEY", "DASHSCOPE_API_KEY", "STRIPE_SECRET_KEY",
                 "STRIPE_WEBHOOK_SECRET", "LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY",
                 "TYPESAFE_API_KEY", "DECISION_CONTROL_TOKEN"):
        os.environ[name] = ""
    os.environ.update(APP_ENV="development", ANONYMOUS_CALLER_ENABLED="true",
                      JEV_DECISION_ENABLED="false", JEV_DECISION_TRAFFIC_PERCENT="0",
                      JEV_SHADOW_ENABLED="false", USE_MOCK_LLM="true",
                      LLM_PROVIDER="local-recovery-fixture", EMBEDDING_PROVIDER="hash",
                      USE_MOCK_PAYMENT="true", ALLOW_MOCK_PAYMENT="true",
                      PROCURA_IDENTITY_REGISTRY=str(root / "data/identity/registry.sqlite3"),
                      PROCURA_ORDERS_FILE=str(root / "data/orders.json"),
                      DATABASE_URL="sqlite:///" + (root / "data/database.sqlite3").as_posix())
    import dotenv
    dotenv.load_dotenv = lambda *a, **k: False
    from app.core import config
    config.PROJECT_ROOT = root
    config.DATA_DIR = root / "data"
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    for name in ("orders.json", "observability_logs.json", "procurement_history.json",
                 "suppliers.json", "procurement_policies.json"):
        path = config.DATA_DIR / name
        if not path.exists():
            path.write_text("[]", encoding="utf-8")
    catalog = config.DATA_DIR / "products.csv"
    if not catalog.exists():
        catalog.write_text("product_id,name,category,brand,price,rating,stock,supplier,delivery_days,warranty_months,compliance_level,description,tags\n"
                           "REC-KB-A,Recovery keyboard A,Keyboard,Local,10,4.5,100,Local,3,12,standard,office keyboard,keyboard\n"
                           "REC-KB-B,Recovery keyboard B,Keyboard,Local,15,4.9,100,Local,2,12,standard,office keyboard,keyboard\n", encoding="utf-8")

    # Reject external connections and writes outside this run's dedicated root.
    from urllib.parse import unquote, urlsplit

    def check_path(value):
        if isinstance(value, int) or value is None:
            return
        value = os.fsdecode(value)
        if value.startswith("file:"):
            value = unquote(urlsplit(value).path)
            if os.name == "nt" and len(value) > 2 and value[0] == "/" and value[2] == ":":
                value = value[1:]
        if not Path(value).resolve().is_relative_to(root):
            raise RuntimeError("ISOLATION_WRITE_OUTSIDE_ROOT")

    def audit(event, args):
        if event == "socket.connect" and args[1][0] not in ("127.0.0.1", "::1"):
            raise RuntimeError("EXTERNAL_NETWORK_FORBIDDEN")
        if event == "socket.getaddrinfo" and args[0] not in (None, "127.0.0.1", "::1", "localhost"):
            raise RuntimeError("EXTERNAL_DNS_FORBIDDEN")
        if event == "open":
            mode, flags = args[1], args[2]
            if (isinstance(mode, str) and any(c in mode for c in "wax+")) or flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC):
                check_path(args[0])
        elif event in ("os.mkdir", "os.remove", "os.rmdir", "sqlite3.connect"):
            check_path(args[0])
        elif event in ("os.rename", "os.replace"):
            check_path(args[0]); check_path(args[1])
    sys.addaudithook(audit)
    from app.rag import vector_store
    vector_store._chromadb = lambda: None
    from main import app
    import uvicorn
    (root / "ready.json").write_text(json.dumps({"pid": os.getpid(), "boot": uuid4().hex}), encoding="utf-8")
    uvicorn.run(app, host="127.0.0.1", port=8000, access_log=False)


if __name__ == "__main__" and len(sys.argv) == 3 and sys.argv[1] == "--serve":
    _serve(sys.argv[2])
    raise SystemExit

import pytest
import httpx

URL = "http://127.0.0.1:8000"
ORIGIN = "http://127.0.0.1:3000"


def _check(condition, message):
    # Avoid assertion introspection of HTTP objects containing credentials.
    if not condition:
        raise AssertionError(message)


def _ok(response, expected=200):
    _check(response.status_code == expected, f"HTTP status {response.status_code}; expected {expected}")
    return response.json()


def _client():
    return httpx.Client(base_url=URL, headers={"Origin": ORIGIN}, trust_env=False, timeout=20)


def _init(client):
    context = _ok(client.post("/api/caller/init"))
    client.headers["X-CSRF-Token"] = context["csrf_token"]


class Server:
    def __init__(self, root):
        self.root, self.process, self.receipt = root, None, None
        self.exits, self.boots = [], []

    def start(self):
        with socket.socket() as probe:
            _check(probe.connect_ex(("127.0.0.1", 8000)) != 0, "8000 occupied; existing service must remain untouched")
        ready = self.root / "ready.json"
        if ready.exists():
            ready.unlink()
        self.log = (self.root / f"server-{len(self.boots) + 1}.log").open("w", encoding="utf-8")
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHON_DOTENV_DISABLED="1")
        self.process = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "--serve", str(self.root)],
                                        stdout=self.log, stderr=self.log, env=env,
                                        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        deadline = time.monotonic() + 25
        with _client() as client:
            while time.monotonic() < deadline:
                if ready.exists():
                    self.receipt = json.loads(ready.read_text())
                if self.process.poll() is not None:
                    raise AssertionError("isolated server exited during startup; inspect its local log")
                try:
                    if self.receipt and client.get("/api/caller/context").status_code == 401:
                        self.boots.append(self.receipt)
                        return
                except httpx.TransportError:
                    pass
                time.sleep(.1)
        self.stop()
        raise AssertionError("isolated server startup timeout")

    def stop(self):
        if self.process is None:
            return
        if self.process.poll() is None:
            # Windows venv launcher and base Python can have different PIDs.
            # ready.json names only this run's freshly spawned server child.
            if self.receipt:
                os.kill(self.receipt["pid"], signal.SIGTERM)
            else:
                self.process.terminate()
            self.exits.append(self.process.wait(timeout=10))
        self.log.close()
        self.process = None
        self.receipt = None
        with socket.socket() as probe:
            _check(probe.connect_ex(("127.0.0.1", 8000)) != 0, "owned server did not release 8000")


@pytest.fixture
def server(tmp_path):
    root = tmp_path / "http-recovery"
    root.mkdir()
    service = Server(root)
    try:
        service.start()
        yield service
    finally:
        service.stop()
        (root / "process-evidence.json").write_text(json.dumps({"boots": service.boots, "exit_codes": service.exits}), encoding="utf-8")


def _db_state(server):
    path = server.root / "data/identity/registry.sqlite3"
    with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) as db:
        # Tokens/digests/CSRF are excluded from returned data and artifacts.
        actors = db.execute("SELECT actor_id,created_at,expires_at,revoked FROM actors ORDER BY actor_id").fetchall()
        resources = db.execute("SELECT kind,resource_id,owner_actor_id,payload FROM resources ORDER BY kind,resource_id").fetchall()
    return actors, resources


def _snapshot(server, sid):
    for kind, resource_id, _, payload in _db_state(server)[1]:
        if kind == "session" and resource_id == sid:
            return json.loads(payload)["recommended_plan"]
    raise AssertionError("persisted session missing")


def _seed(client):
    _init(client)
    sid = _ok(client.post("/api/chat/session"))["session_id"]
    shown = _ok(client.post("/api/chat", json={"session_id": sid, "message": "请给2名员工推荐办公键盘，预算50元。"}))["recommended_plan"]
    _check(bool(shown.get("items")), "real planner did not display executable items")
    binding = {"session_id": sid, **{k: shown[k] for k in ("plan_id", "plan_hash", "plan_version")}}
    confirmation = _ok(client.post("/api/chat/confirm", json=binding))["confirmation_id"]
    payload = {**binding, "confirmation_id": confirmation, "plan": shown}
    order = _ok(client.post("/api/orders", json=payload))
    history = _ok(client.post("/api/history", json={"original_request": "恢复证据", "selected_plan": shown,
                                                  "procurement_plan": shown, "order_draft": order}))
    return sid, shown, binding, payload, order, history


def test_http_process_restart_restores_exact_session_snapshot_and_owned_resources(server):
    with _client() as a, _client() as b, _client() as missing:
        sid, shown, binding, payload, order, history = _seed(a)
        credential = dict(a.cookies)
        before = _db_state(server)
        snapshot = _snapshot(server, sid)
        _check(snapshot == shown, "display differs from original persisted snapshot")
        registry_sha = hashlib.sha256((server.root / "data/identity/registry.sqlite3").read_bytes()).hexdigest()
        files = {name: (server.root / "data" / name).read_bytes() for name in ("orders.json", "procurement_history.json")}
        server.stop()
        _check(len(server.exits) == 1, "first OS process did not exit")
        server.start()
        _check(server.boots[0]["pid"] != server.boots[1]["pid"] and server.boots[0]["boot"] != server.boots[1]["boot"], "not a fresh OS process")
        context = a.get("/api/caller/context")
        _ok(context)
        _check("set-cookie" not in context.headers and dict(a.cookies) == credential, "recovery rotated credential")
        recovered = _ok(a.get(f"/api/chat/session/{sid}"))
        _check(recovered["session_id"] == sid, "session identity changed")
        _check(_db_state(server) == before, "read-only recovery rewrote actor or resource state")
        _check(hashlib.sha256((server.root / "data/identity/registry.sqlite3").read_bytes()).hexdigest() == registry_sha,
               "read-only recovery changed registry bytes")
        _check(_snapshot(server, sid) == snapshot, "recovery rewrote full snapshot")
        for name, content in files.items():
            _check((server.root / "data" / name).read_bytes() == content, "recovery rewrote order/history file")
        # Confirmation validates the loaded snapshot; original submission is reused.
        confirmation = _ok(a.post("/api/chat/confirm", json=binding))
        _check(confirmation["confirmation_id"] == payload["confirmation_id"], "persisted confirmation was not reused")
        retry = _ok(a.post("/api/orders", json=payload))
        _check(retry["order_id"] == order["order_id"], "retry created another order")
        _check(_ok(a.get("/api/orders"))["total"] == 1, "more than one owned order")
        _check(_ok(a.get(f'/api/history/{history["id"]}')) == history, "owned history changed")
        _check(_snapshot(server, sid) == snapshot, "confirmation/retry rehashed snapshot")
        _init(b)
        _ok(b.get(f"/api/chat/session/{sid}"), 403)
        _ok(b.get(f'/api/orders/{order["order_id"]}'), 403)
        _ok(b.get(f'/api/history/{history["id"]}'), 403)
        _check(_ok(b.get("/api/orders"))["total"] == 0 and _ok(b.get("/api/history"))["total"] == 0, "second actor saw owned resources")
        actor_count = len(_db_state(server)[0])
        for path in ("/api/caller/context", f"/api/chat/session/{sid}", "/api/orders", "/api/history"):
            response = missing.get(path)
            _ok(response, 401)
            _check("set-cookie" not in response.headers, "missing credential was silently initialized")
        response = missing.post("/api/chat/session")
        _ok(response, 401)
        _check("set-cookie" not in response.headers, "missing credential mutation initialized actor")
        _check(len(_db_state(server)[0]) == actor_count, "missing credential created actor")
        for name, content in files.items():
            _check((server.root / "data" / name).read_bytes() == content, "retry/denial modified order/history")


@pytest.mark.parametrize("invalid", ["revoked", "expired"])
def test_http_process_restart_rejects_invalid_actor_without_automatic_init(server, invalid):
    with _client() as a:
        sid, _, _, payload, _, _ = _seed(a)
        credential = dict(a.cookies)
        server.stop()
        db_path = server.root / "data/identity/registry.sqlite3"
        with sqlite3.connect(db_path) as db:
            actor = db.execute("SELECT owner_actor_id FROM resources WHERE kind='session' AND resource_id=?", (sid,)).fetchone()[0]
            column = "revoked=1" if invalid == "revoked" else "expires_at=0"
            _check(db.execute(f"UPDATE actors SET {column} WHERE actor_id=?", (actor,)).rowcount == 1, "invalidated wrong test actor")
        before = _db_state(server)
        files = {name: (server.root / "data" / name).read_bytes() for name in ("orders.json", "procurement_history.json")}
        server.start()
        _check(len(server.exits) == 1 and server.boots[0]["pid"] != server.boots[1]["pid"], "invalid-actor case did not restart OS process")
        for method, path, body in [("GET", "/api/caller/context", None), ("GET", f"/api/chat/session/{sid}", None),
                                   ("GET", "/api/orders", None), ("GET", "/api/history", None),
                                   ("POST", "/api/orders", payload), ("POST", "/api/caller/init", None)]:
            response = a.request(method, path, json=body)
            _ok(response, 401)
            _check("set-cookie" not in response.headers and dict(a.cookies) == credential, "invalid credential silently replaced")
        _check(_db_state(server) == before, "invalid credential mutated actor/session/capability state")
        for name, content in files.items():
            _check((server.root / "data" / name).read_bytes() == content, "invalid credential caused order/history side effect")
