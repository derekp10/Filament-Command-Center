# Group 12: Weight Entry Unified Component (Phase 2)

**Branch name:** `feature/weight-entry-unified-component`
**Estimated effort:** ~6–10 hours
**Risk:** High — touches every weight-entry surface; visual baselines need a wholesale refresh
**Depends on:** Group 1 Phase 1 (DONE 2026-04-27) — `static/js/modules/weight_utils.js` foundation

## Goal

Build a single shared weight-entry component (`<WeightEntry>` or equivalent) used by every weight-entry surface in the app. The user reports frequently entering the wrong kind of value because today's UI doesn't make the expected input form clear, and each surface uses slightly different terminology and math. The component:

- Lets the user enter weight in **whatever form they have** (gross / net / additive / delta) and writes the correct `used_weight` to the backend
- Resolves `empty_spool_weight` via the cascade (using `resolveEmptySpoolWeightSource` from `weight_utils.js`) and prompts only when missing
- Uses unambiguous terminology so the user always knows what input is expected
- Supports keyboard navigation (Enter, Escape, Tab, +/- prefix syntax)
- Shows a **preview** of the computed `used_weight` write before submit so the user always knows what's about to happen
- Replaces the bespoke weight UI in: bulk weigh-out, Quick-Weigh nested modal, wizard, edit-filament modal, post-archive prompt, FilaBridge manual recovery

L38 (the original "main-menu QR weight button doesn't subtract empty spool weight" bug) is folded into this component as `mode=gross`.

## Items folded into this group

- **L38** — Gross-weight workflow ("put spool on scale, enter gross reading, system subtracts spool_weight")
- **L48 (full)** — Unify all the fragmented weight-update paths (Phase 1 only extracted the cascade resolver)

## Phase 2 design steps

### 1. Audit "best of breed" elements from each existing path

The user explicitly noted: *"we have a lot of really good ideas and implementations, it's just fragmented."* Catalogue each path's strongest moves and decide which to preserve in the unified component:

- Wizard's three-tier cascade resolution (`resolveEmptySpoolWeight` → `resolveEmptySpoolWeightSource`) — already extracted to `weight_utils.js`
- Quick-Weigh's `+/-` prefix delta syntax (`inv_weigh_out.js:228-340`)
- Bulk weigh-out's auto-archive toggle + force-unassign chain (`inv_weigh_out.js:176-181`)
- Post-archive prompt's vendor/material/color context display (`inv_details.js:showArchiveEmptyWeightPrompt`)
- Filament edit modal's vendor-hint badge + "⇩ Copy Vendor Weight" button (`inv_details.js:1280-1296`)
- FilaBridge manual recovery's per-spool table layout (`templates/components/modals_filabridge_recovery.html`)

### 2. Research Spoolman's weight UI as ONE reference among several

Don't copy it — the user finds Spoolman's UI clunky too. Pull screenshots/source from the open-source Spoolman repo, document its modes, then explicitly note what we're keeping vs. rejecting. Goal: pick the best parts of OUR existing implementations and merge them, with Spoolman as a sanity check, not a template.

### 3. Mockup the unified component

Single modal (or inline panel) with mode selector at top (Gross / Net / Additive / Set Used). Each mode has a labeled input, the resolved empty-spool-weight is always visible (with source badge from Phase 1 work), the resulting `used_weight` write is shown in a "preview" panel before submit so the user sees exactly what's about to happen.

### 4. Define the backend contract

Decide between:
- (a) One consolidated endpoint that accepts `{spool_id, mode, value}` and computes the right `used_weight` server-side, OR
- (b) A thin frontend helper that always submits to the existing `/api/spool/update` with the computed `used_weight`

Decide based on testability and surface area. Option (b) keeps the existing endpoint contracts intact and is probably the right call — the math lives in `weight_utils.js` and is unit-testable.

### 5. Adopt across all surfaces

Each existing weight UI is replaced or wrapped. Visual baselines refreshed.

### 6. Address L38 as part of Mode = Gross

When the user enters a value in Gross mode, compute `used_weight = initial_weight - (gross - empty_spool_weight)`. If `empty_spool_weight` is unresolved, show the shared "missing empty weight" prompt before submitting.

## Must-preserve features (regression watch)

These were caught by the Phase 1 audit. The unified component MUST keep all of these working:

1. Auto-archive on `remaining ≤ 0` (`spoolman_api.py:_auto_archive_on_empty`)
2. Auto-archive **toggle** in bulk weigh-out modal (user opt-out)
3. Force-unassign call after auto-archive (`inv_weigh_out.js:176-181`)
4. Post-archive empty-weight prompt only fires when filament AND vendor both lack `spool_weight`
5. Quick-Weigh `+/-` prefix syntax for delta entry
6. FilaBridge DELTA vs weigh-out ABSOLUTE input semantics (FilaBridge auto-deduct stays out of scope — it's a backend thread, not a user surface)
7. FilaBridge auto-recover acks on success only; manual recovery acks always
8. ALEX FIX: `update_spool` caps `used_weight` to `initial_weight`
9. `update_spool_or_raise` for high-stakes paths (per CLAUDE.md convention)
10. Backfill button in filament details (batch fan-out)
11. Vendor hint + "⇩ Copy Vendor Weight" button in filament edit modal
12. Wizard sync toggle — locks spool empty-weight to mirror filament empty-weight
13. `inventory:sync-pulse` / `inventory:buffer-updated` event dispatch after every weight write (covered by `test_weight_setting_dispatches_events.py`)
14. Activity Log strategy logging (Fast-Fetch vs RAM-Fetch) for FilaBridge auto-recover
15. `LAST_SPOOLMAN_ERROR` surfaced in HTTP responses (per CLAUDE.md convention)

## Before/after baseline

A `phase-2-baseline` git tag was placed on `dev` immediately after Phase 1 merged (2026-04-27). The `docs/agent_docs/phase-2-baseline/` directory contains:

- `README.md` — what each baseline screenshot represents
- `screenshots/` — Playwright-captured PNG of each weight-entry surface in its current state
- `capture_baseline.py` — the script that generated those screenshots (re-runnable)

When Phase 2 is ready for comparison, run the same script against the new build and diff side-by-side.

## Verification (Phase 2)

To be detailed once the component design is locked. At minimum:
- Existing test suite passes: `pytest tests/test_weight_setting_dispatches_events.py tests/test_backfill_spool_weights.py tests/test_empty_spool_weight_priority.py tests/test_archive_empty_weight_prompt.py tests/test_large_spool_weight_tracking.py tests/test_wizard_auto_prefill_empty_weight.py`
- New component tests cover each mode (gross/net/additive/delta), missing-empty-weight prompt, preview panel, keyboard nav
- Visual baselines refreshed (`UPDATE_VISUAL_BASELINES=1 pytest`) only after manual review of diffs against `phase-2-baseline`
- All 15 must-preserve features above remain working
