# Group 33: Residual Bulletproof-Sweep Failures

**Branch name (when started):** `feature/group-33-residual-sweep-flakes`
**Estimated effort:** ~2–4 hours (4 test-infra hardenings + 1 visual-baseline recapture gated on a Derek decision)
**Risk:** **LOW.** Test-infra only + one screenshot-baseline recapture. No product code expected (unless the visual size-change turns out to be an unintended UI regression — see 33.4).

> **Status: ✅ DONE 2026-07-06** (`feature/group-33-residual-sweep-flakes`). All 5 filed flakes fixed + a **6th tail (33.6)** the first post-fix sweep surfaced, fixed in the same session. **Final proof: fresh full `RUN_INTEGRATION=1` sweep = `2138 passed / 0 failed / 11 skipped`** (SWEEP3_EXIT=0) — the trustworthy green sweep this group exists to produce (started from `2129 passed / 5 failed / 14 skipped`). A 4-lens adversarial review of the diff returned **BLOCK** with 2 real defects that were then fixed + verified (see "Review-driven fixes" below). Test-infra only; the sole remaining `1 warning` is a pre-existing Windows cp1252 decode in `test_setup_fields_does_not_wipe_container_slot_values` (present pre-Group-33, non-failing, unrelated).
>
> _(historical)_ **Filed TODO 2026-07-06** after the Group-32 verification sweep: the **5 failures that remained** on the full sweep after Group 32 fixed its 3 targeted flakes (`2129 passed / 5 failed / 14 skipped`). All 5 were A/B-confirmed PRE-EXISTING (fail identically with the Group-32 diff stashed) — a **grown tail** vs the Group-26 sweep's clean 3. The "if a truly green sweep is wanted" follow-on, exactly as Group 32 was to Group 26. Buglist item lives under `## 🧪 Testing`.

## What shipped (2026-07-06)

- **33.1** — poll for the `🖨️ Printers` loc-divider row instead of a fixed 500ms sleep after the async `toggleLocPinPrinters()`/`fetchLocations` re-render.
- **33.2** — 8s `wait_for_function` polling toast-OR-manageModal (was a fixed 1500ms + single check); + `state.heldSpools=[]` / `lastLocalBufferChange` stamp to keep the buffer empty so the PICKUP path is genuinely exercised.
- **33.3** — added the `window.lastLocalBufferChange=Date.now()` grace stamp into the `state.heldSpools` injection (the sibling `test_toolhead_scan_with_multi_spool_buffer_sends_only_topmost` already had it).
- **33.4** — the confirm-overlay visual test was nondeterministic BY DESIGN (the overlay grows the active-print warning banner + scan-to-confirm QR pair ~218px taller ONLY when the probed printer is actively printing; `bound_loaded_slot` can yield a live-printer toolhead). Split into **two deterministic tests**, each stubbing `window.fetchPrinterStateForToolhead`: base (probe→null, existing `quickswap-confirm-overlay` 284px baseline) + active (probe→PRINTING, new `quickswap-confirm-overlay-active` baseline). **"Pin both" per Derek.**
- **33.5** — the test never seeded the buffer; it waited for a `.buffer-item` that only exists if the dev buffer already held a spool (a prior `clean_buffer` empties it). Now seeds a synthetic spool through the real `renderBuffer()` path so it's independent of pre-existing state.
- **33.6 (NEW — the 6th tail)** — `test_return_and_breadcrumb.py::test_edit_full_bindings_auto_expands_feeds_section`. Clicking "Edit Full Bindings" chains **three** sequential fetches (`get_contents` → `Promise.all([fetchPrinterMap, bindings])`) before the Feeds section auto-expands; under saturation that outlasts the old fixed 700ms+5s. Replaced with polling the full end-state (section visible → `feeds-body` visible → toggle text 'Hide') at 12s. Passed in isolation → same load-flake family, fixed in-session rather than punted.

## Review-driven fixes (4-lens adversarial review → BLOCK → both applied + verified)

- **33.4 (HIGH):** the new active baseline captured the two QR codes, whose payload embeds a per-render session id (`fcc-cqr-<seq>-<Date.now>`), so QR pixels drift every run — a latent re-introduction of the exact flake class this group removes (it only passed initially via create-on-missing; empirically it stayed just under the 1% tolerance, but that's luck, not determinism). **Fix:** added `mask=` support to the `snapshot` harness (`conftest.py` `_capture_locator` now forwards screenshot kwargs) and masked `.fcc-confirm-qr-row`, so the banner/text/buttons stay pixel-pinned while the random QR region is blanked. Recaptured the baseline in a quiet container; **6/6** stress runs green.
- **33.5 (MEDIUM):** `renderBuffer()` hit the persist branch and POSTed the synthetic spool (id 990001) to the shared server `GLOBAL_BUFFER` with no teardown — a self-inflicted cross-test pollution source. **Fix:** wrapped the seed in `window.suppressBufferDirty` (renders the DOM, skips the persist). Verified: server buffer is `[]` after the test.
- Other four items (33.1/33.2/33.3/33.6) reviewed **sound** — genuine readiness-gates on the actual end-state, no weakened assertions.

> ⚠️ **Methodology note for the next flake-chaser:** do NOT run visual/E2E tests against the dev container while a full sweep is *concurrently* hammering it — double-saturation + shared-state mutation produced spurious visual failures during this session that vanished in a quiet container. Kill the sweep first, or run visual verification before launching the sweep.

## Why these are one group

Same class as Groups 26 + 32: concurrency/timeout/baseline robustness that only bites on the saturated full sweep (or on a post-sweep-degraded container), plus one stale visual baseline. Four are the buffer-poll-races-local-state / timing family ([[reference_fcc_e2e_sweep_pollution]] / the doassign-flake sibling); one is a screenshot baseline that drifted when the quickswap confirm overlay changed height. Fixing them together is what finally makes `RUN_INTEGRATION=1` a trustworthy green. Test-only.

## How the failures were classified (evidence)

Run in isolation after the sweep, each was retried alone (buffer cleared between):
- **Pass in isolation → load flakes:** 33.1, 33.2, 33.3.
- **Fail even in isolation → deterministic:** 33.4 (stale visual baseline), 33.5 (buffer-population).
- **A/B stash proof:** with the four store edits + the bulk_api test edit stashed, 33.4 and 33.5 fail identically → not Group 32's doing.

## Items

### 33.1 — (load flake) `test_l271_phase35_tree_e2e.py::test_pin_printers_floats_to_top`
Passes in isolation; times out only under concurrent sweep load. Tree-render/timing. **Fix (test-infra):** replace any fixed `wait_for_timeout` with a `wait_for_function`/`expect(...).to_be_visible` poll on the pinned-printer-floated-to-top condition; if it seeds state, gate the assertion on a deterministic hook rather than a sleep.

### 33.2 — (load flake) `test_slot_qr_scan_ui_e2e.py::test_ui_slot_scan_no_buffer_triggers_pickup_flow`
Passes in isolation; the live buffer poll (`liveRefreshBuffer`/`loadBuffer` → `/api/state/buffer`) races the test's locally-injected `state.heldSpools` under load. Same class as the Group-26 doassign flake (26.8). **Fix (test-infra):** stub/suspend the buffer poll for the test, or add a `lastLocalBufferChange` grace like 26.8, or readiness-gate before asserting.

### 33.3 — (load flake) `test_toolhead_scan_single_spool.py::test_multispool_dryer_box_scan_still_sends_full_buffer`
Passes in isolation; buffer-poll race (same family as 33.2). **Fix:** same as 33.2.

### 33.4 — (deterministic) `test_quickswap_visual.py::test_visual_quickswap_confirm_overlay` — stale visual baseline
Fails deterministically with a **size mismatch**, not a sub-pixel drift: `baseline=(540, 284)` vs `actual=(540, 502)` — the quickswap confirm overlay grew ~218px taller. Baseline lives at `inventory-hub/tests/__screenshots__/chromium-1600x1300/quickswap-confirm-overlay.png`.
- **⚠️ DECISION REQUIRED (Derek) BEFORE touching the baseline:** is the taller confirm overlay an *intended* UI change (a recent group added content to it), or an *unintended regression* (something is now rendering that shouldn't, or the overlay is mis-sized)? Do NOT blindly recapture — that would bake a regression into the baseline.
  - If **intended:** recapture with `UPDATE_VISUAL_BASELINES=1` (per CLAUDE.md: PIL-backed diff, 1% tolerance, 1600×1300 viewport) and eyeball the new PNG.
  - If **unintended:** file a product bug for the overlay height and fix the UI instead; the baseline stays.
- **Investigation lead:** `git log`-diff the quickswap confirm-overlay markup/CSS (`inv_quickswap.js` confirm overlay + `mountOverlay`) since the baseline was last captured to see what added height. Candidate windows: Groups 29/30 (color/printer-status) or the L316-era changes.

### 33.5 — (deterministic post-sweep) `test_ui_card_layouts_e2e.py::test_fancy_button_layout_applied` — buffer-population
Fails waiting for a `.buffer-item` that never renders (`Page.wait_for_selector` timeout). The test needs a spool in the buffer; the client-side `processScan`→`persistBuffer` write isn't landing/rendering deterministically (buffer-population, the same family as 33.2/33.3; note the SERVER buffer is populated by the client's `persistBuffer` POST, not by `identify_scan` alone). **Fix (test-infra):** seed the buffer via a deterministic hook and poll for `.buffer-item` (readiness-gate) rather than scanning + fixed-wait; or stub the buffer poll so a just-injected spool can't be overwritten mid-render.

## Recommended order
1. **33.4** first — resolve the DECISION (intended vs regression). If intended, it's a 1-command recapture; if a regression, it's a product bug that changes the group's scope. Do this before the flakes so you know whether Group 33 is pure test-infra.
2. **33.2 / 33.3 / 33.5** — the buffer-poll family; apply the Group-26 `lastLocalBufferChange`/readiness-gate pattern uniformly (one shared fix idiom likely covers all three).
3. **33.1** — the tree-render timing flake; poll-not-fixed-sleep.
4. Re-run `RUN_INTEGRATION=1` at the end and confirm a clean **0 failed** sweep (the point of the group). If a NEW tail appears, catalog it — a saturated sweep tends to surface the next layer.

## Out of scope / do NOT do
- Recapturing 33.4's baseline WITHOUT confirming the height change is intended (would mask a possible regression).
- Silencing any of these with a blanket `skip` or a giant fixed timeout — use readiness polls / bounded retries so the behavior is still asserted (same discipline as Group 32).
- Reopening Groups 26 or 32 — this is the follow-on round ([[feedback_standalone_followups_not_under_completed_epics]]).
