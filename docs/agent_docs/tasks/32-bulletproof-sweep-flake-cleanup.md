# Group 32: Bulletproof-Sweep Flake Cleanup

**Branch name (when started):** `feature/group-32-bulletproof-sweep-flake-cleanup`
**Estimated effort:** ~2–4 hours (2 test-infra fixes + one small cross-platform product-code hardening)
**Risk:** **LOW.** Mostly test-infra (timeouts / readiness). 32.1 carries a genuine but small product-code fix in `cancel_fetch_store.py` — a missing `encoding='utf-8'` (real cross-platform hardening; prod is Linux) and a Windows `os.replace` retry (dev robustness). Pin both with the existing test.

> **Status: TODO** — filed 2026-07-03 by `/refresh-groups` (Derek's call). The **3 load-sensitive flakes** surfaced by the Group-26 verification sweep (`RUN_INTEGRATION=1`, ~23 min: **2102 passed / 3 failed / 11 skipped**) — all **pass in isolation**, failing only under heavy concurrent sweep load. Explicitly NOT covered by Group 26 (which scoped the 21 cataloged reds + the wizard-cancel/doassign flakes). The buglist frames this as "the natural next batch after Group 26 if a truly bulletproof sweep is wanted." Buglist item: `16b5b39`.

## Why these are one group

All three only fail under the saturated full sweep (background threads + a loaded dev container + a loaded Spoolman), and all three are the same class: **concurrency/timeout robustness that a serial run never exercises.** Fixing them together is what finally makes `RUN_INTEGRATION=1` a trustworthy green — the last mile after Group 26 cleared the 21 static reds. Small, self-contained, test-only except the one `cancel_fetch_store.py` hardening.

## Items

### 32.1 — (flake 1) `cancel_fetch_store.py` atomic-write race + missing UTF-8 encoding
**Test:** `test_cancel_review.py::test_process_fetch_gated_off_while_locked`.
Two defects, both surfacing when the cancel-monitor background thread writes `fetches.json` concurrently with the test:
- **Windows `os.replace(tmp, final)` → `PermissionError [WinError 5]`** at [`cancel_fetch_store.py:55`](../../../inventory-hub/cancel_fetch_store.py#L55) when another handle holds the target mid-write (the atomic-rename race). **Fix:** retry `os.replace` a few times on `PermissionError` with a short backoff (the same pattern the label-CSV atomic write and `locations.json` writer already use for held-file cases). Windows-dev robustness — prod (Linux) doesn't hit this, but the retry is harmless there.
- **cp1252 `UnicodeDecodeError` reading `fetches.json`** — the read opens without `encoding='utf-8'`, so a non-ASCII byte trips the Windows default codec. **Fix:** open the file with `encoding='utf-8'` on BOTH read and write. This is real cross-platform hardening (JSON is UTF-8), not just a test fix.

Pin both with the existing test (make it deterministically pass under a simulated concurrent hold, or assert the retry/encoding path). Cross-ref the `PYTHONUTF8` / stream-reconfigure console note from Group 26.2 (same family of Windows-encoding papercuts).

### 32.2 — (flakes 2+3) `test_filament_attributes_bulk_api` integration read-timeouts under load
**Tests:** `test_filament_attributes_bulk_api.py::{test_bulk_set_add_then_remove, test_bulk_set_validates_payload}`.
Real-Spoolman (`192.168.1.29:7913`, 2 s) / localhost (`:8000`, 10 s) **read-timeouts** when the dev container + Spoolman are saturated by the concurrent sweep — the request is fine, the fixed timeout is just too tight under load. **Fix (test-infra):** bump the timeouts and/or retry on `ReadTimeout`, or gate the tests behind a readiness poll (wait for the container/Spoolman to be responsive before asserting), consistent with the `require_server` / poll-not-fixed-sleep idioms already in `conftest.py`. Do NOT mask a real slowdown — if a bulk_set is genuinely slow, note it; the evidence (passes in isolation, fails only saturated) says it's load, not a regression.

## Recommended order
1. **32.1** first — it's the one with a product-code component; the `encoding='utf-8'` + `os.replace` retry are quick and reused patterns, and it removes a real Windows papercut.
2. **32.2** — the two integration-timeout tests; bump/retry or readiness-gate. Re-run `RUN_INTEGRATION=1` at the end and confirm a clean **0 failed** sweep (the whole point of the group).

## Out of scope / do NOT do
- Reopening Group 26 — it's DONE; this is the follow-on round ([[feedback_standalone_followups_not_under_completed_epics]]).
- Silencing 32.2 with a blanket `skip` or a huge fixed timeout — use a readiness poll / bounded retry so it still asserts the behavior.
- Masking 32.1's race by only widening the test timeout — fix the actual `os.replace`/encoding in `cancel_fetch_store.py` so prod-adjacent code is hardened, then pin it.
