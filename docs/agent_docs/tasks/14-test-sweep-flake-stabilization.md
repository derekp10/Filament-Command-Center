# Group 14: Test-Sweep Flake Stabilization

**Branch name:** `feature/test-sweep-flake-stabilization`
**Estimated effort:** ~3–5 hours
**Risk:** Low — test/infrastructure work; production code only touched if a real regression turns up

> ⚠️ **Block-for-next-session priority.** Derek tagged this `[PRIORITY — block for next session, delegate-friendly]`. The goal is a clean green sweep so future group regression runs can be trusted at face value, without having to bisect "is this my change or pre-existing noise" every time.

## Goal

Triage the 18-failure / 6-error fingerprint from the 2026-05-11 post-Group-13 sweep into "real bug" / "test isolation issue" / "missing dep" / "baseline re-capture" buckets and fix each in the smallest possible commit.

**Initial sweep state (2026-05-11):** 772 passed, 12 failed, 6 errors. NONE traced to Group 13 changes (verified by re-running impacted suites in isolation — they pass clean).

## Items to Complete

### 14.1 — `test_delete_ui_e2e.py` × 5 failures
**What:** Group 4 delete-flow surface. Five tests failing:
- `test_spool_gear_dropdown_exposes_delete`
- `test_spool_delete_step1_renders_warning`
- `test_spool_delete_step2_requires_id_match`
- `test_spool_delete_escape_closes_overlay`
- `test_spool_delete_overlay_clears_when_modal_closes`

**Triage steps:**
- Run the file in isolation first to bisect: real regression in gear-dropdown wiring vs. test-state pollution from a prior test leaving a spool in a delete-prone state.
- If isolated runs pass: identify which test ahead in the sweep order leaks state, fix that test's teardown, or pin delete-flow setup to be self-cleaning.
- If isolated runs also fail: real regression — investigate the gear-dropdown / delete-overlay code (Group 4 surface from `completed-archive.md` 2026-04-28 entry).

**Files (potential):**
- `inventory-hub/tests/test_delete_ui_e2e.py` — the failing tests
- `inventory-hub/static/js/modules/inv_details.js` — gear dropdown + delete overlay
- `inventory-hub/templates/components/modals_details.html` — modal markup

### 14.2 — Quick-Swap deposit/refresh × 2 failures
**What:**
- `test_quickswap_deposit_and_header.py::test_deposit_confirm_overlay_names_the_spool_and_toolhead`
- `test_return_overlay_and_refresh.py::test_quickswap_refreshes_manage_view_after_yes`

Confirm overlay either doesn't appear, or the refresh-after-Yes doesn't fire.

**Triage steps:**
- Reproduce by running the quickswap suite alone.
- Either real flake (timing/race) or pre-existing test-isolation issue. Same playbook as 14.1.

**Files:**
- `inventory-hub/tests/test_quickswap_deposit_and_header.py`
- `inventory-hub/tests/test_return_overlay_and_refresh.py`
- `inventory-hub/static/js/modules/inv_quickswap.js` — only if a real regression turns up

### 14.3 — `test_ui_details_modal_e2e.py::test_details_modal_interactions`
**What:** Offcanvas-backdrop click intercept. Already tracked at buglist L233 (offcanvas-backdrop flake from prior 2026-05-07 Group 7 sweep).

**Note:** May be partially absorbed by the canonical overlay-mount helper (Group 15) when that lands. Until then: defensive offcanvas-close at test-setup time, OR quarantine the test + sort-order-pin so it always runs first.

**Files:**
- `inventory-hub/tests/test_ui_details_modal_e2e.py`
- `inventory-hub/tests/conftest.py` — defensive offcanvas-close fixture if that's the approach

### 14.4 — Visual baseline re-captures × 3
**What:**
- `test_quickswap_visual.py::test_visual_quickswap_grid`
- `test_quickswap_visual.py::test_visual_quickswap_kb_active`
- `test_visual_shortcuts_overlay`
- Plus `test_feeds_section_visual.py::test_visual_feeds_section_collapsed`

Baselines stale relative to current renders.

**Approach:**
- Visually verify each layout is correct (open in browser at the canonical 1600×1300 viewport).
- Once verified: `UPDATE_VISUAL_BASELINES=1 pytest <file>` to re-capture.
- Commit the updated PNGs under `inventory-hub/tests/__screenshots__/chromium-1600x1300/`.

**Files:**
- `inventory-hub/tests/__screenshots__/chromium-1600x1300/*.png` — re-captured baselines

### 14.5 — `test_external_parsers.py::test_amazon_parser_matching` BS4 missing
**What:** `beautifulsoup4` not installed in dev environment / Docker container. Parser returns empty results because the import fails silently. Already tracked at buglist L317 / L324 ("On Hold" section).

**Two options:**
- **A.** `pip install beautifulsoup4` into the dev container + add to `requirements-dev.txt`. Lets the test run.
- **B.** Skip-decorate the test with `@pytest.mark.skipif(not _BS4_AVAILABLE, reason="...")` so it doesn't fail the sweep.

Recommend **A** unless there's a reason not to install BS4 (image bloat is minimal).

**Files:**
- `requirements-dev.txt` — add beautifulsoup4
- `inventory-hub/tests/test_external_parsers.py` — or add the skipif if going with option B

### 14.6 — `test_force_location_keyboard_e2e.py` × 6 errors
**What:** ALL 6 errored in the sweep but ALL 7 PASS when the file runs in isolation. Pure test-isolation / state-pollution issue.

**Triage steps:**
- Run the file in isolation to confirm: pass clean? → bisect against the full sweep to find the polluting predecessor.
- Once the polluting test is identified: fix that test's teardown to clear the leaked state, OR add defensive setup to `test_force_location_keyboard_e2e.py` that resets focus/arrow/Enter/Escape state.

**Files:**
- `inventory-hub/tests/test_force_location_keyboard_e2e.py` — defensive setup if that's the approach
- The polluting test (TBD) — fix its teardown

## Definition of Done

- [ ] Full sweep: green or every remaining failure has a documented skip-decorator with a tracking buglist link
- [ ] Each fix lands in its own small commit so a future bisect can isolate any side effects
- [ ] If any test reveals a real production regression: that fix lands as a separate commit (not bundled with the test fix) and gets a buglist + activity-log mention

## Dependencies

- Group 15 (Canonical Overlay-Mount Helper) may partially absorb 14.3 once it lands — sequence is optional but doing Group 15 first would shrink Group 14's scope. Coordinate with Derek.
