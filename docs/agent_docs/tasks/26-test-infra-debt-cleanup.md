# Group 26: Test-Infra Debt Cleanup

**Branch name (when started):** `feature/group-26-test-infra-debt`
**Estimated effort:** ~5–8 hours (mostly small, independent test-infra fixes)
**Risk:** **LOW.** Test-only changes (assertions, fixtures, baselines, poll-not-sleep) + one shared-conftest fixture seed. No product code. The value is making a red sweep MEAN something again — today 21 pre-existing reds mask real regressions and make `RUN_INTEGRATION=1` noisy.

> **Status: TODO** — filed 2026-07-01 by `/refresh-groups` (consolidation). Bundles the **21 pre-existing reds** cataloged on `feature/group-24-weight-transparency-1000g` (clean full sweep: 21 failed / 1759 passed / 10 skipped, `RUN_INTEGRATION=1`, ~22 min; ALL 21 confirmed PRE-EXISTING, none touch product surfaces) **PLUS the intermittent flake rows + the Group-23 FE test-backfill** that the reds item itself named "siblings of the same test-infra debt." One batchable session so a green sweep becomes a real signal.

## Why these are one group

All of it is **test-infra debt, not product bugs** — stale canaries/assertions, missing fixtures, drifted baselines, order-pollution, poll-vs-fixed-sleep flakes, and coverage backfill. Fixing them together (a) makes the full sweep trustworthy in one pass, (b) shares the same triage recipe / fixtures (see `[[reference_fcc_e2e_sweep_pollution]]`), and (c) lets a reviewer confirm "0 reds, and the greens actually assert the shipped behavior." No product-code changes, so it can land as one low-risk test-only PR. Cross-refs the standalone **vestigial-FilaBridge-artifacts** cleanup (bucket 26.2 belongs there too) and **Group 23** (26.6 + 26.9 are Group-23 test-debt).

## Items

### The 21-red sweep (6 buckets — buglist line 273)

#### 26.1 — `test_buffer_card_refresh_propagates_location.py` (8) — STALE source-canary
Regex-scans `liveRefreshBuffer` in `inv_cmd.js` for the diff/mutation logic, but L206 moved it into `_renderSpoolsRefreshPayload` (logic intact). **Fix:** point `_find_live_refresh_buffer` at `_renderSpoolsRefreshPayload` (or assert against the real diff site).

#### 26.2 — `test_universal_fallback.py` (4) — STALE post-FilaBridge
`test_universal_fallback_move` / `test_smart_move_ejects_resident_without_suppress_flag` / `test_smart_eject_clears_filabridge_and_unassigns_if_no_source` / `test_force_unassign_clears_filabridge` assert `mock_post.assert_called_once()` (the retired `_fb_write` push) + FilaBridge-clearing behavior removed in the Phase-2 cutover. **Fix:** delete/rewrite — belongs under the **vestigial-FilaBridge-artifacts cleanup** item. Side note: they spew noisy `UnicodeEncodeError` cp1252 tracebacks from emoji in `state.add_log_entry` on the Windows console — a `PYTHONUTF8`/stream-reconfigure fix is cheap to do while in here.

#### 26.3 — Overlay tests need a bound+loaded slot in dev state (6)
`test_quickswap_ui_e2e.py` (3) + `test_return_text_and_overlay_close.py::{test_confirm_overlay_dismisses_when_modal_closes_via_x, test_bind_picker_dismisses_when_modal_closes_via_x}` (2) + `test_quickswap_visual.py::test_visual_quickswap_confirm_overlay` (1). All wait on `#fcc-quickswap-confirm-overlay` / `#fcc-bind-picker-overlay`, which only render when a real bound+loaded slot exists; on a bare dev state the overlay stays hidden. **Fix:** seed a deterministic bound+loaded-slot fixture (some sibling tests already `pytest.skip` when absent — make these do the same, or seed it).

#### 26.4 — Visual baseline DRIFT (1)
`test_quickswap_visual.py::test_visual_shortcuts_overlay` (baseline 800×1602 vs actual 800×1986 — the shortcuts overlay grew as shortcuts were registered). **Fix:** recapture with `UPDATE_VISUAL_BASELINES=1` (recapture the quickswap-grid baseline at the same time — it drifts the same way as dev data grows).

#### 26.5 — Order-dependent pollution (1)
`test_return_and_breadcrumb.py::test_escape_key_walks_out_of_three_level_stack` **passes in isolation**, fails only mid-sweep (a prior test leaves a modal/focus state; `#manageModal` reads hidden). **Fix:** reset modal state between tests, or make the escape-walk robust to a leftover modal (await `hidden.bs.modal` rather than a fixed assertion).

#### 26.6 — Stale vs the Group 23.4 delete-sentinel (1)
`test_filament_edit_button.py::test_edit_modal_slicer_profile_clear` asserts `"slicer_profile" not in extra` (the pre-23.4 omit-to-clear behavior), but 23.4 now SENDS `__FCC_DELETE_EXTRA__` to clear an extra. **Fix:** assert `extra["slicer_profile"] == "__FCC_DELETE_EXTRA__"` (`window.FCC_DELETE_EXTRA`). (Group-23 test-debt — the delete-sentinel change didn't update this assertion.)

### Intermittent flakes (folded in 2026-07-01 — the reds item's named "siblings")

#### 26.7 — `test_wizard_group10_session_a::test_edit_wizard_cancel_from_spool_details_reopens_details`
Intermittently fails at `_force_close_wizard` — after `m.hide()` (`forceClose=true`, `isDirty=false`) `#wizardModal` stays `.show`, so the chained details reopen never fires. Wizard-on-top-of-spool-details on a LIVE first-result spool → dev-data + modal-transition sensitive. A/B-confirmed pre-existing. **Fix:** await `hidden.bs.modal` (or retry `hide()` once); and/or seed a stable spool instead of `results[0]`.

#### 26.8 — `test_doassign_buffer_safety`
Intermittently fails (`assert <id> in []` — `state.heldSpools` empty); a DIFFERENT test in the file fails on different runs. The live buffer poll (`liveRefreshBuffer`/`loadBuffer` → `/api/state/buffer`) races the test's locally-injected `state.heldSpools` during the ~400 ms wait. A/B-confirmed pre-existing. **Fix:** stub/suspend the buffer poll for these tests, or gate the assertion on a deterministic hook rather than a fixed `wait_for_timeout`.

### Missing coverage backfill (folded in 2026-07-01 — Group-23 FE test-debt)

#### 26.9 — Group-23 FE behaviors not pinned (no functional shortfall)
Group 23 backend invariants ARE pinned (`test_delete_sentinel.py` 12 + `test_flag_spool_labels.py` 4), but several FE behaviors are verified-by-code-read only and a regression would pass the suite: **23.1** import-apply landing the scraped `color_hex` (synthetic color-input) + `product_url`/`purchase_url` + the 3-digit-hex expand + bad-hex skip-toast; **23.2** `editfilExternalReset` anti-leak on modal reopen; **23.5** the `📄 product` wizard chip; **23.6** the canonical Prusament `product_url` write + idempotent skip. **Fix:** add focused assertions — extend `test_edit_filament_external_import.py` (apply-map + reset), `test_wizard_*` (chip), `test_prusament_scan.py` (URL write).

## Recommended order
1. **Cheap assertion/baseline fixes first** — 26.1 (repoint canary), 26.6 (23.4 sentinel assertion), 26.2 (delete/rewrite stale FB tests + the UTF-8 console fix), 26.4 (recapture baselines). Each is a few lines and clears 14 of the 21 reds.
2. **26.3** seed the bound+loaded-slot fixture (clears the 6 overlay reds; the biggest single win, shared fixture).
3. **26.5** order-pollution robustness (1 red).
4. **26.7 / 26.8** the two intermittent flakes (poll-not-sleep / await hidden.bs.modal).
5. **26.9** the Group-23 FE coverage backfill (net-new tests — do last; it's additive, not a red).

## Out of scope / do NOT do
- Product-code changes to make a test pass — if a test red reflects a REAL behavior change, that's a product bug, not test-debt (none of the 21 are — all confirmed stale/infra). Re-triage before "fixing" a test by changing product code.
- Silencing a flake with a blanket `pytest.mark.skip` — fix the race/fixture; a skip hides signal.
- Recapturing a visual baseline without eyeballing the diff first (26.4) — confirm the drift is benign growth, not a real visual regression.
