# Batch 3A-1 fixed-commit revalidation — BLOCKED

Client date: 2026-10-21 (Asia/Shanghai). No product/test assertion changes.

Fixed commit: `5c4c466f813a43500e56f9090ee8b84d847132c2`.
Tree: `356a527f3b1112cc365236ea2b7fc5a51f4e84fd`.
Isolated branch: `audit/batch-3a1-revalidation-20261021`.
Original dirty checkout and existing evidence branches were not switched or modified.

## Actual execution

1. First attempt: pytest startup encountered the write guard when its built-in logging handler opened Windows `NUL`. Pytest return code 3; guarded child process exit 97. No JUnit / no test execution. Original runner retained at `raw/initial-runner.py`.
2. Second attempt: only output locations and an explicit pytest `--log-file` inside the runtime directory were changed. No guard was relaxed. XML independently parsed by ElementTree and PowerShell: 26 total, 0 PASS, 26 FAIL, 0 ERROR, 0 SKIP. Pytest return code 1; guarded child process exit 97. Guard recorded 26 socket.connect blocks. Regression NOT_EXECUTED; no further retry.

The Windows Python runtime uses asyncio ProactorEventLoop._make_self_pipe -> socket.socketpair -> _fallback_socketpair -> loopback TCP connect. The blanket network hook conflicts with that TestClient infrastructure. Logs show incomplete event-loop initialization and HTTP 500 responses. This run is not valid evidence that the authorization patch regressed, and is not a successful fixed-version acceptance test. Guard logs do not include remote addresses, so do not claim each denied event was independently address-attributed.

## Safety and provenance

Before/after records were saved separately for each attempt: commit/tree, all tracked-file SHA256, status, and five original protected-file hashes. All tracked-source hashes and protected-file existence/hashes are unchanged in both attempts. Isolated worktree remains clean. No product files, test assertions, original evidence, runtime configurations, or original business data were edited. No dependencies or environments were created. Credentials were not inherited into test children: an explicit OS/runtime-only environment allowlist was used. No dotenv files exist in the isolated source checkout. Jev authority and Shadow were disabled, authority traffic zero, no real provider/order/payment operations were intentionally performed. Python socket connect/DNS/send attempts were denied. This audit hook is not an OS firewall/native-code sandbox.

Actual argv, cwd, child PID, OS process exit status, timestamps, source/protected snapshots, raw terminal logs and XML are retained locally. Files contain private machine paths and are NOT approved for publication. `blocked-manifest.json` freezes their SHA256; initial and second-attempt failures are retained, not overwritten. Nothing was committed or pushed, and no PR was created.

## Next action requiring a revised validation setup

Do not change product code or assertions. First establish an independently checkable offline harness that permits only the runtime's authenticated socketpair IPC while still blocking provider networking (or use an equivalent process-level external-network isolation mechanism). Do not permit arbitrary localhost connections or disable the guard merely to make tests pass. Preserve these failures, test the revised isolation controls separately, then perform a newly identified run of 26 and 77 tests. Historical provenance remains PARTIAL; fixed-commit execution acceptance remains BLOCKED.
