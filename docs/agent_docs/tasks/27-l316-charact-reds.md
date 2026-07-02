# Group 27: L316 Characterization Findings — 🔴 Priority Reds

**Branch name (when started):** `feature/group-27-l316-charact-reds`
**Estimated effort:** ~5–8 hours (10 localized backend fixes, each + its pin-test update)
**Risk:** **MEDIUM.** Real behavior changes on live backend surfaces (edit-wizard, boot seed, print-queue, audit, deduct, pulse). Each is a small, well-scoped fix, but several touch write/startup paths — verify against the running dev container, not just unit tests.

> **Status: TODO** — filed 2026-07-01 by `/refresh-groups`. The 10 🔴 "real bug, fix soon" findings from the **L316 characterization layer** (buglist lines 11–22). Every finding is currently PINNED as *current* behavior by a named test in `tests/test_l316_charact_*.py`. **Fixing one means updating its pin test in the SAME commit** — the pin then asserts the corrected behavior. Full annotated write-up + exact pin-test names: [L316-characterization-findings.md](L316-characterization-findings.md) (numbered 1–50, matching the `(N)` tags below).

## Why these are one group

All 10 are the highest-severity findings the 284-test characterization layer surfaced during the L316 app.py modularization — genuine correctness bugs (silent data-clobber reopenings, unhandled 500s, config mis-parse that inverts a safety flag, silent audit-state wipe, false-failure double-writes). They share the L316 module surfaces and the **pin-test-update-in-same-commit** workflow, so batching keeps that discipline consistent and lets a reviewer confirm "each red became a green that asserts the FIX, not the bug."

## The pin-test contract (read first)

Each item below is guarded by a `test_l316_charact_*.py` test that currently encodes the BUGGY behavior. For every fix:
1. Change the product code.
2. Open the finding's pin test (name in [L316-characterization-findings.md](L316-characterization-findings.md)) and flip its assertion to the corrected behavior.
3. Keep it a *pin* — assert the new contract precisely so a future regression re-trips it.
4. If a fix touches CLAUDE.md-documented behavior, update CLAUDE.md too (see finding 28's note in Group 29 — the delete-sentinel render pin moved modules).

## Items

### 27.1 — (18) `api_edit_spool_wizard` slot-clobber window reopens on a Spoolman blip · `routes_inventory.py`
A `get_spool → None` mid-edit skips BOTH the dirty-diff AND the `SYSTEM_MANAGED_EXTRAS` strip and forwards the raw payload incl. `container_slot`/`physical_source` verbatim — the exact April-outage class the write-surface conventions exist to prevent. **Fix:** on a `None` existing-spool read, fail closed (surface `LAST_SPOOLMAN_ERROR`, do NOT forward the raw payload) rather than degrading to a full-overwrite PATCH. Cross-check the CLAUDE.md "Spool / Filament write surfaces" conventions.

### 27.2 — (40) Boot creds seed can kill server launch · `print_monitor.py`
The inner `locations_db.seed_printer_credentials` call AND its `__main__` call site are both unwrapped; a raising seed kills launch before the monitor starts — contradicting the "never blocks startup" docstring. **Fix:** wrap the seed (try/except + WARNING log) so a seed failure degrades gracefully and the monitor still starts.

### 27.3 — (34) `mark_printed` JSON-array id → unhandled 500 · `routes_print_queue.py`
A JSON-array id raises `TypeError` past the `ValueError`-only legacy gate → unhandled 500 in prod. **Fix:** broaden the guard to reject non-scalar ids with the JSON error contract (mirror the sibling validation), not a framework 500.

### 27.4 — (41) `fcc_owns_completion_deduct` mis-parsed — `"false"` ENABLES it · `print_monitor.py`
The config value is `bool()`-coerced, not parsed — the JSON string `"false"` is truthy, so it ENABLES the completion deduct. A safety flag that inverts on a string is dangerous. **Fix:** parse it properly (accept real bools + the `"true"/"false"/"1"/"0"` string forms) and default safely. Verify against the live prod value shape.

### 27.5 — (25) CMD:AUDIT during an ACTIVE audit silently wipes state · `routes_scan.py`
Scanning CMD:AUDIT while an audit session is active silently `reset_audit()`s — all in-progress scanned/expected/rogue state gone, no confirmation (the activation branch sits ABOVE the active-session delegation). **Fix:** when a session is active, do NOT re-activate/reset silently — either no-op with an info message or route to a confirm. Preserve in-progress state.

### 27.6 — (22) `manage_contents` clear_location silently skips slotted spools · `routes_scan.py`
`clear_location` only ejects UNSLOTTED spools yet returns success with no warning about the slotted survivors. **Fix:** either also clear slotted spools or return a warning naming the survivors so the caller knows the location isn't actually empty.

### 27.7 — (46) `api_get_multi_spool_filaments` — one bad spool poisons the whole response · `print_deduct.py`
One malformed spool (missing id, or `vendor: null`) trips the blanket `except` and poisons the whole response to `[]` (200), hiding every valid candidate. **Fix:** per-spool try/except so one bad record is skipped (logged) and the valid candidates still return.

### 27.8 — (27) `api_update_filament` false-failure after a COMMITTED write · `routes_scan.py`
The activity-log formatting runs INSIDE the try AFTER a successful Spoolman write; a formatter/logger crash reports `success:false` for a committed write → the user retries and double-writes. **Fix:** move the log-formatting out of the success-determining try (or guard it) so a formatter crash can't invert a committed-write result.

### 27.9 — (49) `dashboard_pulse` silently omits the `status` section on error · `routes_state_pulse.py`
When `_pulse_section_logs` raises, the derived `status` section is silently OMITTED instead of carrying `{"error": ...}` (contradicts the endpoint docstring); the nav spoolman/audit dot gets no signal. **Fix:** on a section error, emit the `{"error": ...}` shape the docstring promises so the frontend dot can react.

### 27.10 — (21) `identify_scan` unknown/deleted id echoes a bare resolver dict · `routes_scan.py`
The spool/filament branch with an unknown/deleted id echoes the bare resolver dict (no display/location/error fields) — the frontend gets an unrenderable `'spool'` payload with no failure signal. **Fix:** return a proper not-found/error payload the frontend can render as a scan failure.

## Recommended order
1. **27.4 (config flag inversion)** and **27.2 (boot seed crash)** first — both are startup/safety and cheap; a wrong `fcc_owns_completion_deduct` parse or a crashing seed have the widest blast radius.
2. **27.1 (slot-clobber)** — highest data-integrity risk; do it carefully with the write-surface conventions open.
3. **27.3 / 27.10 / 27.9** — the unhandled-500 / unrenderable-payload / missing-error-shape trio (input-contract hardening).
4. **27.8 / 27.7** — the false-failure and blanket-except-poisons-all fixes.
5. **27.5 / 27.6** — the audit-wipe and clear-location-survivors semantics (confirm the intended behavior with Derek if ambiguous).

## Out of scope / do NOT do
- Fixing a red by loosening its pin without correcting the product code — the pin must assert the FIXED behavior.
- Batching a 🟠/🟡 finding in here — those are Groups 28/29. Keep this group to the 10 reds so it stays a fast, high-value first session.
- Silent behavior changes to `clear_location` (27.6) or CMD:AUDIT (27.5) without deciding the intended UX — surface the choice if unclear rather than guessing.
