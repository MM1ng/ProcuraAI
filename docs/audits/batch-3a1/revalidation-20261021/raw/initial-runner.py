"""Evidence-only fixed-commit runner; does not alter product/tests or assertions."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from datetime import datetime, timezone
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "source"
RAW = ROOT / "raw"
RUNTIME = ROOT / "runtime"
FIXED = "5c4c466f813a43500e56f9090ee8b84d847132c2"
ORIGINAL = ROOT.parent / "work" / "ProcuraAI"
PYTHON = ORIGINAL / ".venv" / "Scripts" / "python.exe"
PROTECTED = ["backend/procurement.db", "data/decision_runtime.sqlite3",
             "data/observability_logs.json", "data/orders.json",
             "data/transaction_identity/registry.sqlite3"]
CALLER_TESTS = ["test_readonly_context_never_creates_actor", "test_cookie_origin_csrf_and_no_rotation",
                "test_other_actor_cannot_copy_full_binding_or_order", "test_client_user_id_cannot_remint_confirmation",
                "test_ownerless_order_is_unclaimable", "test_explicit_init_reuses_actor_and_invalid_cookie_cannot_switch",
                "test_anonymous_mode_and_host_fail_closed", "test_copied_session_denied_at_every_plan_entry"]


def stamp():
    return datetime.now(timezone.utc).isoformat()


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def git(*args):
    return subprocess.check_output(["git", "-C", str(SOURCE), *args]).decode("utf-8").strip()


def snapshot():
    names = git("ls-files", "-z").split("\0")
    return {"captured_at": stamp(), "commit": git("rev-parse", "HEAD"),
            "tree": git("rev-parse", "HEAD^{tree}"),
            "tracked_diff": git("diff", "--name-only", "HEAD"),
            "status": git("status", "--porcelain"),
            "tracked_sha256": {name: sha(SOURCE / name) for name in names if name}}


def protected():
    return {"captured_at": stamp(), "root": str(ORIGINAL), "files": {
        name: {"exists": (ORIGINAL / name).exists(),
               "sha256": sha(ORIGINAL / name) if (ORIGINAL / name).is_file() else None}
        for name in PROTECTED}}


def child_guard():
    """Installed before importing pytest or any application module."""
    phase = sys.argv[2]
    allow = (RUNTIME / phase).resolve()
    attempts = []
    sqlite_paths = set()

    def deny(event, detail):
        attempts.append({"event": event, "detail": str(detail)})
        raise PermissionError("REVALIDATION GUARD BLOCKED: " + event)

    def resolved(value):
        if isinstance(value, int):
            return None
        return Path(os.fsdecode(value)).resolve()

    def check_write(value, event):
        path = resolved(value)
        if path is not None and not path.is_relative_to(allow):
            deny(event, path)

    def hook(event, args):
        if event in {"socket.connect", "socket.getaddrinfo", "socket.sendto", "socket.sendmsg"}:
            deny(event, "network disabled")
        elif event == "open":
            value, mode, flags = args
            path = resolved(value)
            if path is not None and path.name == ".env":
                deny(event, "dotenv read forbidden")
            if flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND):
                check_write(value, event)
        elif event == "sqlite3.connect":
            value = os.fsdecode(args[0])
            if value != ":memory:":
                if value.startswith("file:"):
                    from urllib.parse import urlparse, unquote
                    value = unquote(urlparse(value).path).lstrip("/")
                check_write(value, event)
                sqlite_paths.add(str(resolved(value)))
        elif event == "os.mkdir":
            path = resolved(args[0])
            if path is not None and not path.is_dir():
                check_write(path, event)
        elif event in {"os.remove", "os.rmdir", "os.chmod", "os.truncate", "os.utime"}:
            check_write(args[0], event)
        elif event in {"os.rename", "os.link", "os.symlink"}:
            check_write(args[0], event)
            check_write(args[1], event)
        elif event == "subprocess.Popen":
            executable, argv, _, _ = args
            name = Path(str(executable)).name.lower()
            if name not in {"whoami", "whoami.exe", "icacls", "icacls.exe"}:
                deny(event, "unapproved child process")
            if name.startswith("icacls"):
                check_write(argv[1], event)
        elif event == "os.system":
            deny(event, "shell disabled")

    sys.addaudithook(hook)
    exit_code = 2
    try:
        import pytest
        # Fixed module import root, with unchanged source and pytest configuration.
        sys.path.insert(0, str(SOURCE / "backend"))
        exit_code = int(pytest.main(sys.argv[3:]))
    finally:
        save(allow / "guard.json", {"network_policy": "deny Python socket connect/DNS/send events",
             "write_allow_root": str(allow), "blocked_attempts": attempts,
             "sqlite_paths": sorted(sqlite_paths), "pytest_return_code": exit_code,
             "limitations": "Python audit hooks, not an OS firewall or hostile native-code sandbox"})
    return 97 if attempts else exit_code


def main():
    assert PYTHON.is_file(), "Existing Python missing; do not install/create environment"
    assert git("rev-parse", "HEAD") == FIXED
    assert git("status", "--porcelain") == "", "Fixed worktree must initially be clean"
    assert not (SOURCE / ".env").exists() and not (SOURCE / "backend" / ".env").exists()
    # Only explicitly allowlisted OS/runtime variables are copied. No provider keys or tokens.
    env = {key: os.environ[key] for key in ["SystemRoot", "WINDIR", "COMSPEC", "PATH", "PATHEXT",
           "SYSTEMDRIVE", "USERPROFILE", "APPDATA", "LOCALAPPDATA", "PROGRAMDATA"] if key in os.environ}
    env.update({"PYTHONDONTWRITEBYTECODE": "1", "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8",
                "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1", "APP_ENV": "test",
                "JEV_SHADOW_ENABLED": "false", "JEV_DECISION_ENABLED": "false",
                "JEV_DECISION_TRAFFIC_PERCENT": "0", "USE_MOCK_LLM": "true",
                "USE_MOCK_PAYMENT": "true", "ALLOW_MOCK_PAYMENT": "false",
                "QUERY_REWRITE_ENABLED": "false", "LANGFUSE_ENABLED": "false"})
    overall = {"fixed_commit": FIXED, "started_at": stamp(), "python": str(PYTHON),
               "runner_sha256": sha(Path(__file__)), "runs": []}
    save(RAW / "execution.json", overall)
    for phase, expected in [("green", 26), ("regression", 77)]:
        run_root = RUNTIME / phase
        run_root.mkdir()
        (run_root / "os-temp").mkdir()
        phase_env = dict(env, TEMP=str(run_root / "os-temp"), TMP=str(run_root / "os-temp"),
                         PROCURA_IDENTITY_REGISTRY=str(run_root / "identity" / "registry.sqlite3"),
                         DATABASE_URL="sqlite:///" + (run_root / "procurement.db").as_posix())
        args = ["tests/test_debug_access_batch3a1.py"]
        if phase == "regression":
            args += ["tests/test_transaction_snapshot_batch1.py"]
            args += ["tests/test_caller_ownership_batch2.py::" + name for name in CALLER_TESTS]
        args += ["-q", "-p", "no:cacheprovider", "--basetemp=" + str(run_root / "pytest"),
                 "--junitxml=" + str(run_root / (phase + ".xml"))]
        command = [str(PYTHON), "-B", str(Path(__file__)), "--child", phase, *args]
        before, data_before = snapshot(), protected()
        assert before["commit"] == FIXED and before["tracked_diff"] == ""
        save(RAW / (phase + "-source-before.json"), before)
        save(RAW / (phase + "-protected-before.json"), data_before)
        record = {"phase": phase, "started_at": stamp(), "cwd": str(SOURCE / "backend"),
                  "argv": command, "environment": {k: phase_env[k] for k in env if k not in os.environ or k.startswith(("JEV_", "USE_", "PYTEST_"))},
                  "expected_cases": expected, "timeout_seconds": 180}
        start = time.monotonic()
        with (RAW / (phase + ".log")).open("wb") as log:
            process = subprocess.Popen(command, cwd=SOURCE / "backend", env=phase_env,
                                       stdout=log, stderr=subprocess.STDOUT)
            try:
                code = process.wait(timeout=180)
            except subprocess.TimeoutExpired:
                process.kill()
                code = process.wait()
                record["timed_out"] = True
        record.update({"process_pid": process.pid, "process_exit_code": code,
                       "finished_at": stamp(), "elapsed_seconds": round(time.monotonic() - start, 3)})
        after, data_after = snapshot(), protected()
        save(RAW / (phase + "-source-after.json"), after)
        save(RAW / (phase + "-protected-after.json"), data_after)
        record["source_unchanged"] = before["tracked_sha256"] == after["tracked_sha256"] and after["tracked_diff"] == ""
        record["protected_unchanged"] = data_before["files"] == data_after["files"]
        guard_path = run_root / "guard.json"
        record["guard"] = json.loads(guard_path.read_text(encoding="utf-8")) if guard_path.exists() else None
        xml = run_root / (phase + ".xml")
        if xml.exists():
            cases = list(ET.parse(xml).getroot().iter("testcase"))
            counts = {"total": len(cases), "fail": sum(c.find("failure") is not None for c in cases),
                      "error": sum(c.find("error") is not None for c in cases),
                      "skip": sum(c.find("skipped") is not None for c in cases)}
            counts["pass"] = counts["total"] - counts["fail"] - counts["error"] - counts["skip"]
            record["junit"] = counts
        overall["runs"].append(record)
        save(RAW / "execution.json", overall)
        print(json.dumps({"phase": phase, "exit": code, "junit": record.get("junit"),
                          "source_unchanged": record["source_unchanged"],
                          "protected_unchanged": record["protected_unchanged"],
                          "blocked_attempts": len(record["guard"]["blocked_attempts"]) if record["guard"] else None}), flush=True)
        if (code != 0 or not record["source_unchanged"] or not record["protected_unchanged"]
                or not record["guard"] or record["guard"]["blocked_attempts"]
                or record.get("junit") != {"total": expected, "pass": expected, "fail": 0, "error": 0, "skip": 0}):
            raise SystemExit("STOP: verification gate failed; preserve outputs, do not relax guards")
    overall["finished_at"] = stamp()
    overall["result"] = "FIXED_COMMIT_TARGETED_VALIDATION_PASS"
    save(RAW / "execution.json", overall)


if __name__ == "__main__":
    if sys.argv[1:2] == ["--child"]:
        raise SystemExit(child_guard())
    main()
