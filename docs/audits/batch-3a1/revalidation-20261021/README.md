# Batch 3A-1 — fixed-commit isolated revalidation

Client date: 2026-10-21, Asia/Shanghai. Evidence-only delivery. No product or test-assertion changes.

## Decision

**PASS: Batch 3A-1 fixed-version targeted execution validation.** This is NOT approval for production, full-project release, Batch 3A-2, or Jev gray traffic. Historical execution provenance remains PARTIAL; new runs do not retroactively prove the historical environment or absence of historical writes.

- Tested commit: `5c4c466f813a43500e56f9090ee8b84d847132c2`.
- Tested tree: `356a527f3b1112cc365236ea2b7fc5a51f4e84fd`.
- Original baseline: `c047b9d1ee1b67c1e340e15e5122fb4fb26d1025`.
- Historical evidence commit: `0e38be2f434dcf7a9d8a8d2325323ddf6df1bb4e` (unchanged).
- Successful run: `attempt-04`. Its source HEAD was the tested commit and both source snapshots were clean, before publication files were added.
- UTC execution window: 2026-10-21T02:38:00.397932+00:00 to 2026-10-21T02:38:17.387451+00:00 (10:38 Asia/Shanghai).

## Actual results (do not add overlapping test selections)

| Selection | PASS | FAIL | ERROR | SKIP | pytest return | OS child process exit |
|---|---:|---:|---:|---:|---:|---:|
| Network isolation self-test | 12 | 0 | 0 | 0 | not pytest | 0 |
| Windows process policy self-test | 8 | 0 | 0 | 0 | not pytest | 0 |
| Fixed-source Green | 26 | 0 | 0 | 0 | 0 | 0 |
| Fixed-source targeted Regression | 77 | 0 | 0 | 0 | 0 | 0 |

The 77-case selection includes the same 26 new tests, 43 transaction snapshot tests and eight selected caller-ownership tests. It is NOT 103 unique product tests and NOT a full repository regression. Green elapsed process time: 3.156 seconds; regression: 12.782 seconds (not business latency benchmarks). Both runs emitted one existing Starlette/AnyIO deprecation warning, not skips or errors.

Raw subprocess output, actual argv/cwd, PID, return status, timestamps and JUnit are retained under `attempt-04/`. ElementTree recount and a separate PowerShell XML recount agree with suite attributes. `independent-verification.json` additionally checks duplicate names, fixed-source AST function presence, exact selection names against archived results, all 261 tracked-file hashes and five protected-file hashes.

## Isolation and why it is narrow

An independent Git worktree was created at the fixed code commit. The existing interpreter was reused; no environment or dependency was installed. Test children receive only allowlisted OS/runtime variables plus explicit test settings, not inherited provider keys/admin tokens. There are no `.env` files in the fixed worktree. Jev Shadow and decision are off, authority traffic 0. All JSON/SQLite/log output uses independent runtime directories or existing pytest temporary fixtures. Source files and test assertions are unchanged.

`ipc_guard.py` permits a socket bind/connect only when the executing frame is the actual captured stdlib Windows `_fallback_socketpair` code object, the audited socket is that frame's precise client/listener object and the destination is its own live loopback listener. No general loopback exception exists. Normal localhost service connections, arbitrary loopback, external IP, DNS, UDP send and connect_ex are negatively tested; concurrent IPC does not leak a global allowance. Successful product runs recorded 56 and 538 allowed IPC events respectively, and zero denied/unexpected events.

`process_guard.py` normalizes Windows Popen audit arguments, where executable may be None and argv a single command-line string. Only the exact `whoami /user /fo csv /nh` query and the product's narrow `icacls` ACL setup under the isolated runtime root are allowed. Python/shell/extra arguments/outside-root ACL/broad ACL grants are negatively tested. Actual identity command stdout and account SIDs are not published. SID literals in the self-test source are synthetic fixtures.

SQLite connection audit checks constrain databases to each isolated phase directory; successful runs recorded two and 95 distinct paths respectively. Existing source directories may receive idempotent mkdir calls, but other filesystem writes are confined to the phase runtime directory. Five original protected files were hashed separately before and after each phase; all unchanged. This proves sampled before/after state for these runs, NOT continuous interception of every possible native write and NOT historical immutability.

**Threat-model limit:** Python audit hooks protect this trusted-code verification workflow. They are not an OS firewall, not a hostile-native-code sandbox and not proof against arbitrary unaudited native networking. No production firewall or running service was modified. No real model/order/payment operation was requested.

## Failed attempts retained

| Attempt | Result | Explanation |
|---|---|---|
| Initial (`raw/`, `runtime/`) | No cases, pytest 3 / guarded exit 97 | Built-in pytest logging opened Windows NUL; write guard blocked it. |
| `attempt-02` | 0 PASS, 26 FAIL, pytest 1 / guarded exit 97 | Blanket network guard blocked asyncio's own Windows socketpair. |
| `attempt-03` | 24 PASS, 2 FAIL, pytest 1 / guarded exit 97 | IPC policy worked; Windows Popen None/string argument shape was misclassified, preventing caller ACL setup. |
| `attempt-04` | 26 PASS and 77 PASS, process exits 0 | Exact IPC and process argument policies, independently self-tested first. |

These are harness compatibility failures, not valid new Red evidence of the authorization patch. Their assertions/results were not changed. Regression was not run in failed attempts. The original historical Red/Green/Regression package is not rewritten or replaced.

`blocked-manifest.json` is a historical snapshot from before this continuation. Its entry named `validate.py` identifies the old runner content, now archived byte-for-byte at `attempt-02/raw/runner.py`; the root runner was subsequently modified with authorization. `verification-summary.json` records this verified relocation. Do not expect that historical manifest entry to match the current runner. `RESULT.md` is likewise the earlier blocked conclusion, preserved as historical evidence, not the final decision.

## Evidence publication and verification

All records in this directory are public COPIES or explicitly generated summaries. Raw originals remain local. Private path prefixes and hostnames are replaced with `[FIXED_SOURCE]`, `[ORIGINAL_REPO]`, `[VALIDATION_ROOT]`, `[WORKSPACE_ROOT]`, `[USER_HOME]`, `[HOST_REDACTED]`. JSON escapes are accounted for. Public files use UTF-8/LF with one terminal newline. Test names, statuses, failure reasons and command structure remain. Test fixture credentials remain synthetic source literals, never live configuration values. No business JSON/SQLite files, dotenv contents, live keys/tokens or user traces are included.

`sha256-manifest.json` binds original local raw hashes to each sanitized public file and records hashes for generated summaries. Its own bytes are bound by the Git evidence commit, not a self-hash. Paths are placeholders, not literally executed command paths. Current raw versions of the runner/guards and previous runner versions are included for inspection. Environment package versions were read from the same reused interpreter after the run, not captured from a recreated environment.

Publication checks covered all 60 scoped staged files and 59 manifest-bound staged blobs, with no hash mismatches or obvious credential/private-path findings. Eight sanitized test terminal logs were explicitly added despite the repository's generic log-ignore rule; no other ignored files were added. `git diff --cached --check` reports two original trailing-whitespace lines in the preserved attempt-02 traceback (exit 2); failure text was not edited to remove this formatting warning.

To inspect: independently hash public files, recount each XML, compare recorded test source SHA256 and Git tree with the fixed code commit, review each before/after pair and actual child exit status. Helpers are evidence tools, not product source. A rerun requires a fresh, separately identified isolated workspace and adapted local root paths, not running this published directory in place; do not overwrite existing runtime directories. `verify_evidence.py` accepts the original local validation-root layout and performs a read-only recount/AST/hash check without importing the application.

## Remaining limits / not executed

- No new historical Red execution; it remains in the prior fixed evidence commit.
- No full-project, browser/SSE, deployed-service, real-provider or real-payment tests.
- No Jev accuracy/benefit/latency or gray-release measurement; project/gray decision stays NO-GO.
- Local process records are traceable artifacts, not externally signed CI attestations.
- Hash sampling cannot prove every intermediate write/read, nor reconstruct missing historical run snapshots.
- An independent ChatGPT read-only review of this new evidence remains the next gate; no PR, main merge, deployment or Batch 3A-2 work is authorized by this result.
