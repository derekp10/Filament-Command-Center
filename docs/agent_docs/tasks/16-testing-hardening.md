# Group 16: Testing Hardening & Helper Consolidation

**Branch name:** `feature/testing-hardening-helpers`
**Estimated effort:** ~3–4 hours
**Risk:** Low — test-infrastructure work; production code only touched if 16.1 reveals a real coverage gap

## Goal

Wrap up the post-Group-14 test-hygiene follow-ups. Group 14 stabilized the sweep; this group prevents the next sweep-order shift from re-introducing the same class of flakes, and dispositions the parallel project-root `tests/` directory.

## Items to Complete

### 16.1 — Disposition the parallel project-root `tests/` directory
**Buglist ref:** L229
**What:** A separate test suite lives at repo-root [tests/](tests/) (6 files, 28 tests: `test_filabridge_recovery.py`, `test_frontend.py`, `test_locations_db.py`, `test_logic.py`, `test_spoolman_api.py`, `test_state.py`). The dev workflow runs only `inventory-hub/tests/` (804 tests), so these never appear in the sweep we trust as the regression gate.

**Known stale test:** `tests/test_spoolman_api.py::test_sanitize_outbound_data_json_strings` — asserts plain-string `extra` fields aren't JSON-quoted, but post-ALEX-FIX (2026-04-27) Spoolman strictly requires all custom Extra fields to be valid JSON strings, so plain strings are `json.dumps`-wrapped. Test reflects pre-ALEX-FIX contract.

**Decision needed (with Derek):**
- **(a) Consolidate** the 6 files into `inventory-hub/tests/`, fix/delete the stale test, add the rest to the regression sweep.
- **(b) Delete** the project-root suite as legacy if its coverage is duplicated in `inventory-hub/tests/`. Quick audit: `test_spoolman_api_symmetry.py` may already supersede `test_spoolman_api.py`; check the rest.

**Minimum quick fix if neither (a) nor (b) ships:** update the assertion in `tests/test_spoolman_api.py::test_sanitize_outbound_data_json_strings` to expect `'"Should Not Quote"'` (post-ALEX-FIX value) so the test passes when someone happens to run that suite. Doesn't address consolidation.

**Files:**
- `tests/test_filabridge_recovery.py`, `tests/test_frontend.py`, `tests/test_locations_db.py`, `tests/test_logic.py`, `tests/test_spoolman_api.py`, `tests/test_state.py` — coverage audit
- `inventory-hub/tests/test_spoolman_api_symmetry.py` and siblings — identify overlap

**Acceptance criteria:**
- [ ] Decision recorded (in commit message or this task file)
- [ ] If (a): all 6 files moved; stale test fixed or removed; sweep covers them
- [ ] If (b): all 6 files removed; commit explains why each was redundant
- [ ] If quick fix: only the stale assertion line is updated

### 16.2 — Promote `_open_manage` to shared conftest fixture
**Buglist ref:** L237
**What:** The same `_open_manage(page, base_url, loc_id)` helper is duplicated across 5 test files:
- [test_quickswap_visual.py](inventory-hub/tests/test_quickswap_visual.py)
- [test_feeds_section_visual.py](inventory-hub/tests/test_feeds_section_visual.py)
- [test_bind_slot_picker.py](inventory-hub/tests/test_bind_slot_picker.py)
- [test_contrast_guard.py](inventory-hub/tests/test_contrast_guard.py)
- [test_loc_mgr_bindings_ui_e2e.py](inventory-hub/tests/test_loc_mgr_bindings_ui_e2e.py)

Each has slightly-different timing. Group 14.4 added an explicit `wait_for_function` on `state.allLocations.length > 0` to only `test_quickswap_visual.py` because the modal silently no-ops when locations aren't loaded yet. The other four still rely on a fixed 400ms sleep and are flake candidates the next time the sweep adds latency.

**Approach:**
- Add `open_manage_modal(page, base_url, loc_id)` to [inventory-hub/tests/conftest.py](inventory-hub/tests/conftest.py) (alongside `reset_dom_state_js`)
- Include the `state.allLocations.length > 0` wait so it always waits for readiness, not a fixed sleep
- Migrate all 5 files; remove the local `_open_manage` helpers
- One commit per migrated file so bisect can isolate any regression

**Acceptance criteria:**
- [ ] `open_manage_modal` exists in conftest with the locations-loaded wait
- [ ] All 5 files use the shared fixture, no local copies remain
- [ ] Full sweep stays green
- [ ] Each migration is its own commit

### 16.3 — Audit remaining e2e tests for `reset_dom_state_js` adoption
**Buglist ref:** L239
**What:** Group 14 promoted the defensive DOM-pollution teardown to a `conftest.py` fixture (`reset_dom_state_js`). Currently used by 4 test files. Many other e2e tests open the search offcanvas / a Bootstrap modal as part of their setup and may inherit the same orphan-backdrop / stale-`<select>` / leaked-offcanvas flakes if sweep order shifts.

**Surfaces to audit (per buglist):**
- `test_search_e2e.py`
- `test_search_deployed_filter.py`
- `test_filament_new_spool_e2e.py`
- `test_ui_structural.py`
- Plus any other test that grep `'nav button:has-text("SEARCH")'` finds

**Approach:**
- Grep for the SEARCH-button selector to enumerate all callers
- For each test file, evaluate whether the setup chain involves offcanvas/Bootstrap modal subtrees
- Add the `reset_dom_state_js` teardown where appropriate

**Acceptance criteria:**
- [ ] List of audited files in the commit message
- [ ] Each adoption is its own small commit (bisect-friendly)
- [ ] Full sweep stays green

### 16.4 — Document the Windows pip / pytest Python-version mismatch
**Buglist ref:** L241
**What:** On Derek's machine, `pip install <pkg>` resolves to Python 3.11 (`D:\Programming\Languages\Python\Python311\python.exe`), but `pytest` runs under Python 3.14.4 (`C:\Python314\python.exe`). Caught 2026-05-12 wrapping Group 14.5: BS4 installed into 3.11, pytest's 3.14 didn't see it.

**Recommended fix:**
- **Primary (one-line):** Add a short note to `CLAUDE.md`'s Testing section calling out the version mismatch and the canonical install command: `"C:\Python314\python.exe" -m pip install <pkg>`
- **Optional:** Commit a tiny `scripts/install-dev-deps.{cmd,sh}` wrapper that always targets the right interpreter

**Files:**
- `CLAUDE.md` — Testing section
- (Optional) `scripts/install-dev-deps.cmd` + `scripts/install-dev-deps.sh`

**Acceptance criteria:**
- [ ] CLAUDE.md Testing section mentions the version mismatch and the canonical install command
- [ ] If wrapper script: works on Derek's machine, references `requirements-dev.txt`

## Definition of Done

- [ ] All 4 items shipped (or 16.1 explicitly deferred with a one-line note)
- [ ] Full sweep stays green
- [ ] Each fix is in its own commit so bisect remains clean

## Dependencies

- Group 14 (DONE 2026-05-12) — this group is its direct follow-up
- Group 15 (DONE 2026-05-11) — `mountOverlay()` is settled, no overlay-related test churn expected
