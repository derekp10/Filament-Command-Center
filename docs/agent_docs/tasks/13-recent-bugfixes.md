# Group 13: Recent Bugfixes (Weight + Dryer Display)

**Branch name:** `feature/recent-bugfixes-weight-dryer`
**Estimated effort:** ~3–4 hours
**Risk:** Low-Medium — focused bug fixes; 13.2/13.3 share dryer-box render surface so verify both together

## Goal

Fix four recently-reported bugs surfaced post-quickswap-merge:
- A focus regression in the unified Quick-Weigh `<WeightEntry>` overlay (13.1)
- Two dryer-box display bugs around items being assigned but not rendered (13.2, 13.3)
- LOC: search box matching not fully working despite commit 883f6f4 (13.4 — continuing bug)

13.2 and 13.3 are bundled because they almost certainly share root-cause code in the dryer-box card render path.

## Items to Complete

### 13.1 — Quick-Weigh value field can't receive focus
**Buglist ref:** L135
**What:** "Quick weight modal that displays when adjusting weights on spools won't let me change the value in the text field, seems that it won't receve focus?"

**Likely surface:** The Phase-2 `<WeightEntry>` overlay (`inventory-hub/static/js/modules/weight_entry.js`). Phase 2 (Group 12) replaced the legacy `#quickWeighModal` Bootstrap markup with an inline overlay; if focus management didn't carry over the user can't type into the value input.

**Investigation steps:**
- Open Quick-Weigh on a spool in dev (`http://localhost:8000/`).
- DevTools → Elements panel → confirm overlay opened with the value `<input>`.
- Check whether `document.activeElement` is the input or something else (overlay container, body, prior trigger).
- Compare against the Phase-1 reference flow (the wizard `wiz-spool-empty_weight` field auto-focus).

**Files:**
- `inventory-hub/static/js/modules/weight_entry.js` — overlay open + focus logic
- `inventory-hub/static/js/modules/inv_quickswap.js` and/or `inv_cmd.js` — Quick-Weigh trigger sites
- `inventory-hub/tests/test_weight_entry_overlay.py` — extend with a focus-after-open assertion

**Acceptance criteria:**
- [ ] Opening Quick-Weigh focuses the value input automatically
- [ ] Typing immediately updates the field
- [ ] Existing overlay tests still pass; new focus-on-open test added
- [ ] Verified manually with a real spool in browser

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

## Testing Checklist

- [ ] Manual repro and verify all 4 fixes in dev
- [ ] Existing Quick-Weigh tests still pass; new focus test added
- [ ] Existing Location Manager / dryer-box tests still pass; regression tests added for 13.2 + 13.3
- [ ] Full regression sweep before commit
- [ ] Activity Log + Toast coverage matches CLAUDE.md spec for any new failure paths

## Dependencies

- None. Group 1 + Group 2 are DONE so the unified weight + buffer-refresh paths are stable to build on.
- Coordinate with Location Manager Phase 1B (Phase tracker on buglist L207) — if that lands first, 13.2's investigation might want the new `parent_id` lookups instead of prefix splits.
