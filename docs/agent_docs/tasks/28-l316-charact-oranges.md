# Group 28: L316 Characterization Findings — 🟠 Labels/CSV + Deletes/Wizard + Scan/Queue

**Branch name (when started):** `feature/group-28-l316-charact-oranges`
**Estimated effort:** ~6–10 hours (25 mostly-small fixes across three module clusters, each + its pin-test update)
**Risk:** **LOW–MEDIUM.** Individually small, but they span label CSV generation (P-touch output correctness), delete/create endpoints, and the scan + print-queue input contracts. Verify label-mode changes against a real P-touch CSV, and the endpoint changes against the JSON error contract.

> **Status: TODO** — filed 2026-07-01 by `/refresh-groups`. The 25 🟠 findings from the **L316 characterization layer** (buglist lines 23–25). Every finding is PINNED as *current* behavior by a `tests/test_l316_charact_*.py` test — **fixing one = update its pin in the SAME commit.** Full annotated write-up + pin-test names: [L316-characterization-findings.md](L316-characterization-findings.md).

## Why these are one group

Three tightly-clustered surfaces from the same characterization pass: label/CSV output correctness (`labels_csv.py`), the delete + wizard-create endpoints (`routes_locations.py` / `routes_inventory.py`), and the scan + queue-flag input contracts (`routes_scan.py` / `routes_print_queue.py`). They share module boundaries and the pin-test-update workflow, and several are the same *class* of defect (missing/loose validation returning a bare `{success:false}` 200; sanitization gaps in label text). Batching keeps the pin discipline consistent per module.

## The pin-test contract (read first)

Each item is guarded by a `test_l316_charact_*.py` test encoding the BUGGY behavior. For every fix: change the code, then flip that finding's pin assertion to the corrected contract in the same commit (keep it a precise pin). Names in [L316-characterization-findings.md](L316-characterization-findings.md).

## Items

### Cluster A — Labels + CSV (`labels_csv.py`)
- **28.A1 — (1)** `hex_to_rgb` length-guard runs BEFORE the `#`-strip, so `'#AABBC'` mis-parses to a 1-digit blue channel instead of rejecting. **Fix:** strip `#` first, then length-guard.
- **28.A2 — (2)** `get_smart_type` emits a trailing space into the Type column when material is empty. **Fix:** trim / conditional join.
- **28.A3 — (3)** `get_color_name`'s name-fallback isn't quote-stripped (JSON-quoted names print with literal quotes). **Fix:** quote-strip the fallback.
- **28.A4 — (4)** `get_best_hex` abandons `multi_color_hexes` entirely on an empty FIRST segment. **Fix:** skip empty segments rather than bailing.
- **28.A5 — (5)** `sanitize_label_text` emoji map is VS16-inconsistent (bare ⚠ passes through; ⚡+VS16 leaves a stray invisible VS16). **Fix:** normalize VS16 handling across the emoji map.
- **28.A6 — (6)** `flatten_json` scalar input yields an empty-string CSV column header. **Fix:** give scalar input a sane header.
- **28.A7 — (7)** `flatten_json` mangled-key collisions are silent last-wins + empty containers vanish. **Fix:** decide + document the collision behavior; avoid silent loss.
- **28.A8 — (9)** batch location-mode uses EXACT `row['LocationID']` key access — one differently-cased row key fails the WHOLE batch (inconsistent with the case-insensitive 'Max Spools' matching in the same handler). **Fix:** case-insensitive key access to match the sibling.
- **28.A9 — (10)** filament/swatch mode does NOT run `sanitize_label_text` on Brand/Color/Type — emoji reach the P-touch swatch CSV. **Fix:** sanitize those fields in swatch mode.
- **28.A10 — (11)** a literal `0` bed/extruder temp renders as blank, not `'0°C'`. **Fix:** treat 0 as a valid value, not falsy-blank.
- **28.A11 — (12)** location labels write the UPPERCASED scanned id, not the row's stored casing (round-trip risk for lowercase-stored LocationIDs). **Fix:** write the stored casing.
- **28.A12 — (13)** cosmetic `'Overwritten 1 items.'` plural grammar. **Fix:** pluralize correctly.

> _Finding (8) — the silent lock failure on the single-location-label endpoint — is NOT in this group; it's the standalone "give `api_print_location_label` the friendly file-lock message" NOT-Grouped row (label-CSV robustness residual)._

### Cluster B — Deletes & wizard (`routes_locations.py` / `routes_inventory.py`)
- **28.B1 — (14)** DELETE `/api/locations` with a blank id → 200 `{"success": false}` with no msg (not 4xx). **Fix:** 4xx + a msg.
- **28.B2 — (15)** `api_delete_filament` "abort" only aborts the FILAMENT delete — the child-spool loop continues after a failure (callers reading "abort" expect stop-on-first-failure). **Fix:** honor stop-on-first-failure or rename the semantics.
- **28.B3 — (16)** `api_delete_spool` has no existence guard — a nonexistent id → 502 passthrough, not 404. **Fix:** existence guard → 404.
- **28.B4 — (17)** `api_create_filament` rejection returns a fixed generic msg WITHOUT surfacing `LAST_SPOOLMAN_ERROR` (breaks the CLAUDE.md convention; sibling `api_create_vendor` does it right). **Fix:** surface `LAST_SPOOLMAN_ERROR` like the sibling.
- **28.B5 — (19)** `api_edit_spool_wizard` commits the spool write (+24.F weight log) BEFORE the filament update — a filament rejection reports total failure for a half-persisted edit. **Fix:** order/transaction so a partial persist isn't reported as total failure (or report partial success accurately).
- **28.B6 — (20)** `add_choice` missing-field validation returns 200 `{success:false}`, not 400. **Fix:** 400.

### Cluster C — Scan / queue-flags (`routes_scan.py` / `routes_print_queue.py`)
- **28.C1 — (23)** unknown `manage_contents` action → misleading `'Spool not found'` msg (+ an unreachable terminal return). **Fix:** accurate "unknown action" msg; drop the dead return.
- **28.C2 — (24)** during an active audit, `process_audit_scan`'s error status is discarded — the route always answers `{'cmd':'clear'}`. **Fix:** propagate the audit-scan error status.
- **28.C3 — (30)** `set_flag` has NO missing-id validation (forwards `None` to a live Spoolman lookup, 200 bare failure) — asymmetric with `mark_printed`'s guard. **Fix:** add the missing-id guard.
- **28.C4 — (31)** `set_flag` doesn't int-coerce the id (`mark_printed` does — decide which wins). **Fix:** align id-coercion across both endpoints.
- **28.C5 — (32)** `set_flag` fall-throughs return 200 `{'success': false}` with NO msg key (frontend can only show its generic toast). **Fix:** include a msg.
- **28.C6 — (33)** both queue endpoints evaluate strict `request.json` BEFORE their try blocks — malformed JSON → framework HTML 400, wrong content-type → 415, bypassing the JSON error contract (unlike `api_quickswap`'s `get_json(silent=True)`). **Fix:** adopt the `get_json(silent=True)` idiom.
- **28.C7 — (35)** `mark_printed` treats `id=0` as missing (truthiness). **Fix:** distinguish 0 from missing.

## Recommended order
1. **Cluster A first** — self-contained pure functions in `labels_csv.py`, easy to unit-test, no endpoint contract to reason about. The `hex_to_rgb` (28.A1), 0-temp (28.A10), and swatch-sanitize (28.A9) ones are correctness bugs that reach the printed label; do those before the cosmetic 28.A12.
2. **Cluster C** — the scan/queue input-contract fixes are a coherent sub-batch (missing-id guards, int-coercion, the `get_json(silent=True)` idiom); do 28.C3–28.C7 together so the two queue endpoints end up symmetric.
3. **Cluster B** — the delete/create endpoints; 28.B4 (surface `LAST_SPOOLMAN_ERROR`) is the CLAUDE.md-convention one, do it with the write-surface conventions open.

## Out of scope / do NOT do
- Finding (8) — that's the standalone label-CSV friendly-lock-message residual, not this group.
- The 🔴 reds (Group 27) or 🟡 findings (Group 29) — keep this to the 25 oranges.
- Recapturing/regenerating a real P-touch CSV against prod hardware — verify label-mode changes with a generated CSV + the existing `test_l316_charact_label_endpoints.py` / label tests, not a live P-touch run.
