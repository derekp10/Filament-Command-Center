# Group 13: Recent Bugfixes (Weight + Dryer Display)

**Branch name:** `feature/recent-bugfixes-weight-dryer`
**Estimated effort:** ~4–6 hours
**Risk:** Medium — focused bug fixes; 13.2 / 13.3 / 13.6 all touch the toolhead↔dryer-box binding sync surface so verify them together

## Goal

Fix six recently-reported bugs surfaced post-quickswap-merge:
- A focus regression in the unified Quick-Weigh `<WeightEntry>` overlay (13.1)
- Two dryer-box display bugs around items being assigned but not rendered (13.2, 13.3)
- LOC: search box matching not fully working despite commit 883f6f4 (13.4 — continuing bug)
- Remove "ALEX cap" branding from the weight overlay's high-cap warning (13.5 — copy-edit)
- Toolhead↔dryer-box binding desync — direct toolhead assignment doesn't propagate to slot, and 0g unassignment leaves stale slot bindings (13.6)

13.2, 13.3, and 13.6 are bundled because they almost certainly share root-cause code in the dryer-box / toolhead binding-sync layer (`perform_smart_move`, `perform_smart_eject`, and the auto-archive-on-empty path).

## Items to Complete

### 13.1 — Quick-Weigh value field can't receive focus
**Buglist ref:** L135 + L150 (additional repro detail)
**What:** "Quick weight modal that displays when adjusting weights on spools won't let me change the value in the text field, seems that it won't receve focus?"

**Repro narrowed (L150, commit 20df38c):** "the weight update bug (that happens in the dedicated weight modal), the text box un-editable one, seems to occure when accessing from filament cards in location mamanger? Up and down works, but text input directly is impossible for them for some reason."

Key signal: arrow keys (up/down) DO work, but the text input itself rejects keystrokes. That rules out "input is missing entirely" or "wrong element focused" — the input exists and is reachable, but something is intercepting/preventing key events. Strong suspects:
1. A `keydown` handler higher up in the DOM is calling `e.preventDefault()` or `e.stopPropagation()` on character keys but letting arrow keys through.
2. The Location Manager modal's keyboard nav scope is swallowing events before the overlay's input sees them — Location Manager's `kb-active` arrow-key handler may not yield to nested overlays.
3. The Bootstrap modal containing the Location Manager card has `tabindex` / focus-trap behavior that's stealing focus back to the modal on every keystroke.

**Likely surface:** The Phase-2 `<WeightEntry>` overlay (`inventory-hub/static/js/modules/weight_entry.js`) interacting with the Location Manager modal's keyboard scope.

**Investigation steps:**
- Open Quick-Weigh **specifically from a filament card inside Location Manager** in dev (`http://localhost:8000/`) — the dashboard buffer-card path may not reproduce.
- DevTools → Elements panel → confirm the overlay's value `<input>` is `document.activeElement` after open.
- Listen on the input: `inp.addEventListener('keydown', e => console.log('keydown', e.key, 'defaultPrevented?', e.defaultPrevented))`. Type a digit. If `defaultPrevented` is true OR the listener never fires, an ancestor handler is the culprit.
- Inspect Location Manager's keydown handlers (`inv_loc_mgr.js`) and any modal-level keyboard scope; check whether they call `e.preventDefault()` unconditionally or only on arrow/Enter/Escape.
- Confirm that opening Quick-Weigh from a buffer card on the dashboard does NOT repro — that's the data point that points at Location Manager scope leakage.

**Files:**
- `inventory-hub/static/js/modules/weight_entry.js` — overlay open + focus logic
- `inventory-hub/static/js/modules/inv_loc_mgr.js` — Location Manager keyboard scope; check whether it yields to nested overlays
- `inventory-hub/static/js/modules/inv_quickswap.js` and/or `inv_cmd.js` — Quick-Weigh trigger sites (note: from-Location-Manager trigger may live in `inv_loc_mgr.js` or `ui_builder.js`)
- `inventory-hub/tests/test_weight_entry_overlay.py` — extend with a focus + keystroke-passthrough test for the from-LocMgr path

**Acceptance criteria:**
- [ ] Opening Quick-Weigh focuses the value input automatically
- [ ] Typing digits/`.`/`-`/`+` updates the field — verified in BOTH dashboard-buffer AND Location-Manager-filament-card paths
- [ ] Arrow keys still work (no regression on the case that already works)
- [ ] Existing overlay tests still pass; new test asserts keystrokes reach the input from the Location Manager open path
- [ ] Verified manually in browser from a Location Manager filament card

### 13.2 — Dryer-box ghost spool after auto-eject (assigned but invisible)
**Buglist ref:** L137
**What:** "A Spool in LR-MDB-2 When auto ejected, was still assigned to the dryer box (2/2) but wasn't visible in the UI. Need to find out why and fix. Had to be found/scanned and force moved to get it fixed."

**Repro context from buglist:**
```
[00:11:40] ↩️ Returned #106 -> LR-MDB-2
[00:11:40] ⚠️ Smart Load: Ejecting #106 from XL-4...
[00:11:40] 📦 #230 IIID Max PLA (Transition (Color Change)) -> Dryer LR-MDB-2 [Slot 1]
```

**Likely surfaces:**
- `inventory-hub/logic.py` — `perform_smart_eject` / `perform_smart_move` — the auto-eject path may not be flushing the prior spool's binding before assigning the new one (count goes 2/2 because the old assignment lingered).
- `inventory-hub/static/js/modules/inv_loc_mgr.js` — Location Manager dryer-box card render: confirm whether ghost spools (assigned but matching no `slot_targets` row) are filtered out by the renderer.
- Dashboard buffer / location refresh: check `liveRefreshBuffer` or its location-fetch sibling for the same diff-key gap pattern that hit Group 2.

**Investigation steps:**
- Reproduce by smart-loading a spool that auto-ejects another from a slot it was occupying.
- Hit `/api/locations` against dev directly and check whether the box record actually shows the ghost spool ID.
- If backend is correct, the renderer is dropping it; if backend is wrong, the eject path needs a forced unbind.

**Files:**
- `inventory-hub/logic.py` — eject path
- `inventory-hub/static/js/modules/inv_loc_mgr.js` — dryer-box render
- Possibly `inventory-hub/spoolman_api.py` — slot-clear write surface

**Acceptance criteria:**
- [ ] After auto-eject, the prior spool's `container_slot` is cleared OR the new spool's binding overwrites it cleanly (no residual count)
- [ ] Box card (X/Y) reflects only items actually in the box
- [ ] Activity Log entry is emitted for any auto-clear that fires
- [ ] Regression test added covering the swap-into-occupied-slot path

### 13.3 — Dryer-box overflow items hidden from "unsorted" list
**Buglist ref:** L142
**What:** "Seems to be that the unsorted list is missing in dryerbox locations now? anything that seem so fall into this catagory just doesn't show up, even though the box states (5/4) need to investigate whats going on there."

**Likely surface:** Same dryer-box card render code as 13.2. The "unsorted" / overflow section that lists items in a box but not bound to a specific slot has either (a) been removed during a recent refactor, or (b) is being filtered out by an over-aggressive predicate.

**Investigation steps:**
- Open Location Manager → Dryer Box with overflow items in dev.
- Confirm via `/api/locations` that the items exist and are bound to the box.
- Check the dryer-box render template/JS for an "unsorted" or "overflow" section — see if it's commented out, conditionally rendered, or filtering against `slot_targets` keys.

**Files:**
- `inventory-hub/static/js/modules/inv_loc_mgr.js` — dryer-box card render path
- Possibly `inventory-hub/static/js/modules/ui_builder.js` — `SpoolCardBuilder` variant for box contents
- `inventory-hub/templates/components/modals_*.html` — Location Manager templates

**Acceptance criteria:**
- [ ] Items in a box without a slot binding render in an "Unsorted" / "Overflow" section
- [ ] Box header count (X/Y) matches total visible cards
- [ ] Regression test covering an overflow scenario

### 13.4 — Location search box should support LOC: value lookup (continuing)
**Buglist ref:** L144
**What:** "Location search boxes should also be able to search based on the LOC: Value (LR-MDB-1)"
**Status:** Continuing bug. Commit 883f6f4 (`feat: add support for searching location boxes by LOC value`) added partial support but Derek reports several surfaces still won't match the `XX-XXX-X` LOC pattern (e.g. typing `LR-MDB-1` finds nothing in some search boxes). Coverage gap, not a full regression — works in some places, not others.

**Investigation steps:**
- Enumerate every location search/filter input in the app and test each one with a real LOC value (`LR-MDB-1`, `PM-DB-XL-L`, `XL-1`, etc.). Identify the failing surfaces explicitly so the fix can target the same code path used by the working ones.
- Diff commit 883f6f4 to see which search call sites it modified — the failing surfaces are almost certainly ones that weren't touched and still match against `Name` only, not `LocationID`.
- Confirm the LOC matcher is case-insensitive AND tolerant of partial/prefix input (e.g. `LR-MDB` should suggest all matching boxes).

**Surfaces to verify:**
- Dashboard location search FAB
- Wizard location combobox (`inv_wizard.js`)
- Location Manager filter input (`inv_loc_mgr.js`)
- Force-location modal in spool/filament details
- Manage-contents → set location
- Backlog / Cart Queue location filter (if applicable)

**Files:**
- `inventory-hub/static/js/modules/inv_loc_mgr.js`, `inv_wizard.js`, `inv_search.js` — possible search/filter call sites
- Backend search endpoint(s) in `app.py` if matching is server-side

**Acceptance criteria:**
- [ ] Typing a LOC value (e.g. `LR-MDB-1`) into any location search/filter box surfaces the matching box
- [ ] Friendly-name search still works (no regression)
- [ ] Regression test added covering the LOC: prefix path

### 13.5 — Remove "ALEX cap" branding from weight modal warning
**Buglist ref:** L152
**What:** "Remove 'Alex Clamp' text from warning in weight modal when weight is < 0g. This text in the warning doesn't need to be in there. Its just a feature added by another AI."

**Exact location:** [weight_entry.js:272](inventory-hub/static/js/modules/weight_entry.js#L272) — the high-cap branch reads `'⚠ Value clamped to initial_weight (ALEX cap).'`. (Note: Derek said "< 0g" but the only user-visible "(ALEX cap)" string is on the high-cap branch, not the low. The low-cap text at L273 is already clean.) Remove the `(ALEX cap)` parenthetical so the message reads `'⚠ Value clamped to initial_weight.'`.

**Files:**
- `inventory-hub/static/js/modules/weight_entry.js` line 272 — string edit only
- Internal `// [ALEX FIX]` comments throughout the codebase are NOT user-visible and out of scope here. Leave those alone.

**Acceptance criteria:**
- [ ] High-cap warning no longer mentions "ALEX cap"
- [ ] Existing weight-overlay tests still pass (no test currently asserts the parenthetical text — confirm by grep before changing)
- [ ] Verified manually by entering a value > initial_weight in the Quick-Weigh overlay

### 13.6 — Toolhead ↔ dryer-box binding desync (assign + auto-archive)
**Buglist ref:** L154
**What:** "Assigning a spool directly to a toolhead, doens't properly update the slot in the dryerbox. Dryer box has to be updated agagain seperatly. The dryerbox and tool head (slot assignments seem to desync if toolhead is the first target.) Filaments hitting 0 also cause some weird unassignment sync. It will get removed from the slot location in filabrige, but still remain in locations/slots. This whole systenm needs another pass to to work more logically."

Two distinct desync failures, same broken-sync class:

**Part A — Toolhead-first assignment doesn't propagate to slot:**
When a spool is assigned directly to a toolhead (e.g. via scan + force-move, or dropping into a toolhead-typed location) and the toolhead has a `slot_targets` binding back to a dryer-box slot, the box's slot record never gets the spool. User must manually re-assign on the box for the binding to appear correct. Likely cause: `perform_smart_move`'s toolhead branch only writes the toolhead `location` and skips the symmetric write that would set `container_slot` on the binding-source dryer-box slot.

**Part B — Empty-spool unassignment is asymmetric:**
When `remaining_weight` hits 0 and auto-archive fires, FilaBridge correctly drops its toolhead → spool mapping, but FCC's spoolman state retains the `container_slot` / dryer-box slot binding. Result: the box still shows the spool occupying a slot in the UI even though FilaBridge has released it. Likely cause: auto-archive's `_auto_archive_on_empty` path moves the spool to UNASSIGNED but doesn't clear the `container_slot` extra (or its parent box's `slot_targets`-driven view of "what's in slot N").

This pairs with **13.2** (ghost spool after auto-eject) — both are facets of the same architectural gap: writes to one side of the toolhead↔box pair don't always propagate to the other.

**Investigation steps:**
- Reproduce Part A: pick a spool not currently bound, scan/force-move directly to a toolhead with a `slot_targets` binding back to a slot. Read the box record from `/api/locations` and confirm whether the binding-target slot now lists the spool. If it doesn't, that's the bug.
- Reproduce Part B: drain a spool to 0g (or fake it via `/api/spool/<id>/update_weight` to set used = initial), trigger auto-archive, then read the box record. Confirm `container_slot` on the spool was cleared AND the box's slot view drops it.
- Audit `perform_smart_move` (`logic.py`) for the symmetric write — does the toolhead-target branch write the binding-source slot? Compare against the dryer-box-target branch (which presumably already does write `container_slot`).
- Audit `_auto_archive_on_empty` (`spoolman_api.py`) for `container_slot` cleanup parity with the breadcrumb (`extra.fcc_pre_archive_location`) it already plants.

**Files:**
- `inventory-hub/logic.py` — `perform_smart_move` toolhead branch (Part A); `perform_smart_eject` if it shares this code
- `inventory-hub/spoolman_api.py` — `_auto_archive_on_empty` cleanup (Part B); `compute_dirty_extras` + `SYSTEM_MANAGED_EXTRAS` ensure the symmetric write isn't blocked
- `inventory-hub/tests/test_archive_unarchive_helpers.py` — extend with a Part B regression test (slot binding cleared on auto-archive)
- New test for Part A — toolhead-first assign propagates to box slot — likely `test_dryer_bindings.py` or `test_smart_move_toolhead_to_slot_sync.py`

**Acceptance criteria:**
- [ ] Part A: Assigning a spool directly to a toolhead with a `slot_targets` binding writes the binding-source slot's `container_slot` in one operation — no manual second update required
- [ ] Part B: Auto-archive-on-empty clears `container_slot` (and the box's slot view drops the spool) symmetrically with the FilaBridge unmap that already fires
- [ ] Activity Log entries for both paths describe what was cleared (e.g. `Cleared slot binding LR-MDB-2:SLOT:1 (auto-archive)`)
- [ ] Regression tests covering both parts; existing 13.2 ghost-spool test continues to pass
- [ ] Verified manually in dev for both repros

## Testing Checklist

- [ ] Manual repro and verify all 6 fixes in dev
- [ ] Existing Quick-Weigh tests still pass; new focus test added
- [ ] Existing Location Manager / dryer-box tests still pass; regression tests added for 13.2 + 13.3
- [ ] Full regression sweep before commit
- [ ] Activity Log + Toast coverage matches CLAUDE.md spec for any new failure paths

## Dependencies

- None. Group 1 + Group 2 are DONE so the unified weight + buffer-refresh paths are stable to build on.
- Coordinate with Location Manager Phase 1B (Phase tracker on buglist L207) — if that lands first, 13.2's investigation might want the new `parent_id` lookups instead of prefix splits.
