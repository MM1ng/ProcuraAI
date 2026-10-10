"""Explicit loopback anonymous identity; client user IDs have no authority."""
from contextvars import ContextVar
from dataclasses import dataclass
import hashlib
import hmac
import os
from pathlib import Path
import secrets
import sqlite3
import subprocess
import time
import json
import ipaddress
from uuid import uuid4
from app.core.config import DATA_DIR

COOKIE_NAME = "procura_actor"
ORIGIN = "http://127.0.0.1:3000"
API_HOST = "127.0.0.1:8000"
ACTOR_TTL_SECONDS = 86400
CURRENT_CALLER = ContextVar("procura_trusted_caller", default=None)
VERIFIED_PROVIDER_EVENT = ContextVar("procura_verified_provider_event", default=False)

def require_order_write_owner(resource):
    if VERIFIED_PROVIDER_EVENT.get():
        if not resource or not resource.get("owner_actor_id"):
            raise CallerDenied("RESOURCE_NOT_OWNED", 403)
        return
    require_owner(resource)

class CallerDenied(Exception):
    def __init__(self, code="CALLER_REQUIRED", status=401):
        self.code, self.status = code, status
        super().__init__(code)

@dataclass(frozen=True)
class Caller:
    actor_id: str
    credential_digest: str

def registry_path():
    return Path(os.getenv("PROCURA_IDENTITY_REGISTRY", str(DATA_DIR / "transaction_identity" / "registry.sqlite3"))).resolve()

def require_dev_mode():
    if os.getenv("ANONYMOUS_CALLER_ENABLED", "").lower() != "true" or os.getenv("APP_ENV", "").lower() not in {"development", "test"}:
        raise CallerDenied("ANONYMOUS_MODE_UNAVAILABLE", 503)

def _record(digest):
    require_dev_mode()
    try:
        db = sqlite3.connect(registry_path().as_uri() + "?mode=ro", uri=True)
        db.row_factory = sqlite3.Row
        with db:
            row = db.execute("SELECT * FROM actors WHERE credential_digest=?", (digest,)).fetchone()
        db.close()
    except sqlite3.Error:
        raise CallerDenied("CALLER_REGISTRY_UNAVAILABLE", 503) from None
    if row is None or row["revoked"] or row["expires_at"] <= time.time():
        raise CallerDenied("CALLER_INVALID_OR_EXPIRED")
    return row

def resolve_credential(credential):
    require_dev_mode()
    if not credential:
        raise CallerDenied()
    row = _record(hashlib.sha256(credential.encode()).hexdigest())
    return Caller(row["actor_id"], row["credential_digest"]), row

def require_caller(caller=None):
    caller = caller if caller is not None else CURRENT_CALLER.get()
    if not isinstance(caller, Caller):
        raise CallerDenied()
    row = _record(caller.credential_digest)
    if row["actor_id"] != caller.actor_id:
        raise CallerDenied("CALLER_INVALID")
    return caller

def require_owner(resource, caller=None):
    caller = require_caller(caller)
    if not resource or resource.get("owner_actor_id") != caller.actor_id:
        raise CallerDenied("RESOURCE_NOT_OWNED", 403)
    return caller

def check_host(request):
    require_dev_mode()
    if request.url.scheme != "http" or request.headers.get("host") != API_HOST:
        raise CallerDenied("LOOPBACK_HOST_REQUIRED", 403)
    try:
        is_local = request.client is not None and ipaddress.ip_address(request.client.host).is_loopback
    except ValueError:
        is_local = False
    if not is_local:
        raise CallerDenied("LOOPBACK_CONNECTION_REQUIRED", 403)

def check_write(request, row):
    if request.headers.get("origin") != ORIGIN:
        raise CallerDenied("ORIGIN_INVALID", 403)
    token = request.headers.get("x-csrf-token", "")
    if not token or not hmac.compare_digest(token, row["csrf_token"]):
        raise CallerDenied("CSRF_INVALID", 403)

def _protect_new_directory(path):
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    if os.name == "nt":
        import csv
        result = subprocess.run(["whoami", "/user", "/fo", "csv", "/nh"], capture_output=True, text=True,
                                check=True, creationflags=subprocess.CREATE_NO_WINDOW)
        sid = next(csv.reader([result.stdout.strip()]))[1]
        result = subprocess.run(["icacls", str(path), "/inheritance:r", "/grant:r",
                                 f"*{sid}:(OI)(CI)F", "*S-1-5-18:(OI)(CI)F"], capture_output=True,
                                creationflags=subprocess.CREATE_NO_WINDOW)
        if result.returncode:
            raise CallerDenied("CALLER_REGISTRY_PROTECTION_FAILED", 503)
    else:
        path.chmod(0o700)

def initialize(credential=None):
    require_dev_mode()
    if credential:
        caller, row = resolve_credential(credential)
        return None, caller, dict(row)
    path = registry_path()
    try:
        if not path.exists():
            _protect_new_directory(path.parent)
        with sqlite3.connect(path) as db:
            db.execute("CREATE TABLE IF NOT EXISTS actors (credential_digest TEXT PRIMARY KEY, actor_id TEXT UNIQUE NOT NULL, csrf_token TEXT NOT NULL, created_at REAL NOT NULL, expires_at REAL NOT NULL, revoked INTEGER NOT NULL DEFAULT 0)")
            db.execute("CREATE TABLE IF NOT EXISTS resources (kind TEXT NOT NULL, resource_id TEXT NOT NULL, owner_actor_id TEXT NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(kind,resource_id))")
            token = secrets.token_urlsafe(32)
            row = dict(credential_digest=hashlib.sha256(token.encode()).hexdigest(), actor_id=uuid4().hex,
                       csrf_token=secrets.token_urlsafe(32), created_at=time.time(),
                       expires_at=time.time() + ACTOR_TTL_SECONDS, revoked=0)
            db.execute("INSERT INTO actors VALUES (:credential_digest,:actor_id,:csrf_token,:created_at,:expires_at,:revoked)", row)
        if os.name != "nt":
            path.chmod(0o600)
    except CallerDenied:
        raise
    except (OSError, sqlite3.Error, subprocess.SubprocessError):
        raise CallerDenied("CALLER_REGISTRY_UNAVAILABLE", 503) from None
    return token, Caller(row["actor_id"], row["credential_digest"]), row

def read_resource(kind, resource_id):
    require_caller()
    try:
        db = sqlite3.connect(registry_path().as_uri() + "?mode=ro", uri=True)
        with db:
            row = db.execute("SELECT payload FROM resources WHERE kind=? AND resource_id=?", (kind, resource_id)).fetchone()
        db.close()
        return json.loads(row[0]) if row else None
    except (sqlite3.Error, ValueError):
        raise CallerDenied("RESOURCE_REGISTRY_UNAVAILABLE", 503) from None

def resources_for_owner(kind):
    actor = require_caller()
    try:
        db = sqlite3.connect(registry_path().as_uri() + "?mode=ro", uri=True)
        with db:
            rows = db.execute("SELECT resource_id,payload FROM resources WHERE kind=? AND owner_actor_id=?", (kind, actor.actor_id)).fetchall()
        db.close()
        return {row[0]: json.loads(row[1]) for row in rows}
    except (sqlite3.Error, ValueError):
        raise CallerDenied("RESOURCE_REGISTRY_UNAVAILABLE", 503) from None

def save_resource(kind, resource_id, resource):
    from app.services.transaction_lock import TRANSACTION_LOCK, require_writer_lease
    actor = require_owner(resource)
    with TRANSACTION_LOCK:
        require_writer_lease()
        try:
            with sqlite3.connect(registry_path()) as db:
                existing = db.execute("SELECT owner_actor_id FROM resources WHERE kind=? AND resource_id=?", (kind, resource_id)).fetchone()
                if existing and existing[0] != actor.actor_id:
                    raise CallerDenied("RESOURCE_NOT_OWNED", 403)
                db.execute("INSERT INTO resources VALUES (?,?,?,?) ON CONFLICT(kind,resource_id) DO UPDATE SET payload=excluded.payload",
                           (kind, resource_id, actor.actor_id, json.dumps(resource, ensure_ascii=False)))
        except sqlite3.Error:
            raise CallerDenied("RESOURCE_REGISTRY_UNAVAILABLE", 503) from None
