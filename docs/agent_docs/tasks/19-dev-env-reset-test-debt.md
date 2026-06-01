# Group 19: Dev-Env Reset & E2E Test-Debt Triage

**Branch name:** `feature/dev-env-reset-test-debt`
**Estimated effort:** ~4–6 hours
**Risk:** Low–Medium — the `reset-dev` script touches shared dev data (Spoolman 7913 + `locations.json`), but dev is isolated from prod (separate Spoolman instance 7913 vs 7912). The test-debt items are test-only edits.

## Goal

Get the pytest + Playwright E2E sweep back to a trustworthy green. The suite runs against the **shared, mutating dev backend**, so a full run (~986 tests) contaminates dev and reruns fail in clusters that have nothing to do with the code under test. Two halves:
1. **Eliminate the data-contamination class** — a single, idempotent `reset-dev` script that restores dev to a clean, reproducible baseline *before* a sweep, so it can't be forgotten or done wrong by hand.
2. **Pay down known TEST-DEBT** — stale assertions that would fail even in a pristine env (the 2026-05-28 Swal-pass leftovers + the wizard/material-split staleness called out in the L345 follow-up).

**Buglist source:** the L345-follow-up block + the two "Test debt — found during the 2026-05-28 Swal pass" bullets in `Feature-Buglist.md` (added 2026-05-28/30 on `feature/scan-match-pipeline`).

## Items to Complete

### 19.1 — `reset-dev` script (automate the clean-baseline restore)
**Buglist ref:** L345 follow-up ("automate dev-env reset for clean E2E runs")
**What:** One script to restore dev to a clean, reproducible baseline before a sweep.

**Reset surface (mutable shared state a sweep corrupts):**
- Dev **Spoolman DB** (`192.168.1.29:7913`) — spools / filaments / vendors + their `extra` (`container_slot`, `physical_source`, `needs_label_print`, `sample_printed`, temps, `product_url`…). The big one.
- **`inventory-hub/data/locations.json`** — FCC locations + dryer-box `slot_targets`. Gitignored live data; tracked seed = `data/locations.json.example`.
- **FilaBridge state** (`192.168.1.29:5001`) — toolhead ↔ filament maps (secondary).
- **NOT** `config.json` — untouched by sweeps (`printer_map` stable); tracked seed = `config.json.example`.
- In-memory FCC state (buffer / logs / undo / audit) — cleared by `docker restart inventory_hub`, not a data restore.

**Approach (lean: seed-based, option B):**
- (A) prod→dev copy (Spoolman 7912→7913 + locations.json) — safe (separate instances), realistic, but large + drifts → non-reproducible, and some tests assume a known state.
- **(B) restore-from-seed — preferred.** The tracked `.example` files imply this was the intended pattern. Add a curated Spoolman seed-dump → fast, reproducible, decoupled from prod.

**Approach steps:**
- Restore `locations.json` from the seed (`data/locations.json.example`).
- Spoolman import/restore from a curated seed-dump into 7913.
- Optional FilaBridge reset.
- `docker restart inventory_hub` to clear in-memory state.

**Files:**
- `setup-and-rebuild/reset-dev.*` (new) — the script (confirm host vs `docker exec` context; per CLAUDE.md, give Docker-context commands).
- `inventory-hub/data/locations.json.example` — confirm/curate as a test-ready seed.
- a curated Spoolman seed-dump (new, location TBD in investigation 19.1a).

**Acceptance criteria:**
- [ ] Running `reset-dev` from a contaminated dev yields a known baseline.
- [ ] Re-running it is idempotent (same end state).
- [ ] A full sweep immediately after a reset has no DATA-caused failures (see 19.1b bucket).

### 19.1a — Investigation: are the `.example` seeds test-ready?
**What:** Determine whether `data/locations.json.example` (and any config seed) carry the full toolhead / box / printer setup the E2E fixtures assume, or are minimal stubs. If stubs, curate a test-ready seed. Decide where the Spoolman seed-dump lives and how it's restored into 7913.

### 19.1b — Investigation: bucket the 77 sweep failures
**What:** From the 2026-05-30 full sweep (77 failed / 986 passed / 24 skipped; A/B-confirmed environmental, not branch-caused), split each failure into:
- **DATA-caused** — a `reset-dev` fixes it (manage-modal won't open, quickswap/locmgr/returns, buffer-card refresh, …).
- **TEST-DEBT** — fails in a pristine env too (→ 19.2 / 19.3 / 19.4 / 19.5).
Produce the bucketed list so the reset script's success criteria are measurable.

### 19.2 — Fix stale test: `test_wizard_escape_warns_when_dirty`
**Buglist ref:** Test debt (2026-05-28 Swal pass)
**What:** `tests/test_ui_structural.py::test_wizard_escape_warns_when_dirty` asserts a `.swal2-container` appears on dirty-wizard Escape, but that unsaved-changes guard was migrated to `window.mountOverlay()` (see the passing `test_wizard_overlay_migration.py`).
**Fix:** Update it to assert the `mountOverlay` (+ its Keep-Editing / Discard buttons) instead of the Swal — OR delete it as redundant with the migration suite.
**Files:** `inventory-hub/tests/test_ui_structural.py`.
**Acceptance:** [ ] Passes in a pristine env; no Swal assertion remains.

### 19.3 — Fix stale test: `test_structural_global_modals` text-truncate false-positive
**Buglist ref:** Test debt (2026-05-28 Swal pass)
**What:** `tests/test_ui_structural.py::test_structural_global_modals` flags the Global Search offcanvas's `.text-light fw-bold text-truncate` result spans as `OVERFLOW_CUTOFF`, but `text-truncate` is *designed* to clip with an ellipsis.
**Fix:** Add a `text-truncate` skip to `execute_global_scanner`'s whitelist (alongside `select2`, `navbar`, `justify-content-between`, `wizard-step`).
**Files:** `inventory-hub/tests/test_ui_structural.py` (the `execute_global_scanner` whitelist).
**Acceptance:** [ ] `text-truncate` spans no longer flagged; scanner still catches real overflow.

### 19.4 — Fix stale wizard collapsed-panel tests
**Buglist ref:** L345 follow-up caveat ("known TEST-DEBT")
**What:** Wizard tests assert `#wiz-fil-density` / `#wiz-fil-empty_weight` are visible, but those fields moved into a collapsed panel — the tests never expand the panel first, so they fail "not visible."
**Fix:** Have the tests expand the owning panel before asserting visibility (or assert presence, not visibility, per the field's new home).
**Files:** the wizard E2E test(s) referencing `#wiz-fil-density` / `#wiz-fil-empty_weight` (confirm exact file in 19.1b triage).
**Acceptance:** [ ] Tests expand the panel and pass in a pristine env.

### 19.5 — Fix material-split tests' choices dependency
**Buglist ref:** L345 follow-up caveat ("known TEST-DEBT")
**What:** Material-split tests depend on the `filament_attributes` *choices* config, so they fail when that config isn't in a known state.
**Fix:** Make the tests seed/stub the required `filament_attributes` choices themselves (fixture) rather than relying on ambient dev config — so they're hermetic regardless of dev state.
**Files:** the material-split test(s) + possibly `tests/conftest.py` (confirm in 19.1b triage).
**Acceptance:** [ ] Tests no longer depend on ambient `filament_attributes` choices; pass in a pristine env.

## Notes
- Per CLAUDE.md: pytest + Playwright run on the HOST against `http://localhost:8000`; the `reset-dev` script itself likely mixes host steps (locations.json seed) with `docker exec` / `docker restart` for the container. Give commands in Docker context.
- Windows interpreter footgun applies if any helper installs deps: use `"C:/Python314/python.exe" -m pip ...`.
- This group ties into **L345** (isolated dev Spoolman/filabridge environment) — the reset script is a stepping stone toward fully isolated dev instances.
