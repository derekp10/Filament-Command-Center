# Group 13: Recent Bugfixes (Weight + Dryer Display)

**Branch name:** `feature/recent-bugfixes-weight-dryer`
**Estimated effort:** ~6–8 hours
**Risk:** Medium — bug fixes span weight-overlay, dryer-box binding-sync, search/filter, and eject paths; 13.2 / 13.3 / 13.6 all touch the toolhead↔dryer-box binding sync surface so verify them together

## Goal

Fix nine recently-reported bugs surfaced post-quickswap-merge:
- A focus regression in the unified Quick-Weigh `<WeightEntry>` overlay (13.1)
- Two dryer-box display bugs around items being assigned but not rendered (13.2, 13.3)
- LOC: search box matching not fully working despite commit 883f6f4 (13.4 — continuing bug)
- Remove "ALEX cap" branding from the weight overlay's high-cap warning (13.5 — copy-edit)
- Toolhead↔dryer-box binding desync — direct toolhead assignment doesn't propagate to slot, and 0g unassignment leaves stale slot bindings (13.6)
- Gross-mode in the Quick-Weigh overlay shouldn't hard-block when empty-spool weight is missing — needs a skip path (13.7)
- Main-menu eject shouldn't be blocking on non-idle printer state, plus duplicate confirm modal that does nothing on Yes (13.8)
- Quick-Weigh default-mode preference — let user pick Gross / Additive / Net / Set Used as the on-open default (13.9)

13.2, 13.3, and 13.6 are bundled because they almost certainly share root-cause code in the dryer-box / toolhead binding-sync layer (`perform_smart_move`, `perform_smart_eject`, and the auto-archive-on-empty path).
13.1, 13.5, 13.7, 13.9 all live in the `<WeightEntry>` overlay (`weight_entry.js`) so they ship together with shared regression testing.

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

### 13.7 — Gross-mode shouldn't hard-block on missing empty-spool weight
**Buglist ref:** L148
**What:** "Forcing a empty spool weight fill in when updating a spool that doesn't have an empty spool weight, when using the gross function sholdn't prevent the user from entering a weight if the don't know, or can't find the empty spool weight. We need to check if this is the case, and if so, give the user the option to skip adding an empty spool weight. This is preventing me from updating the weight on a spool. This is while in the quick weight modal."

**Surface:** The `<WeightEntry>` overlay's Gross mode path (`weight_entry.js`). When the resolved empty-spool weight is missing, the existing preConfirm in `showArchiveEmptyWeightPrompt` (or the inline equivalent in the overlay) blocks save until the user fills it in. Derek hit this when he didn't know the tare and just wanted to record what he could.

**Approach:**
- When Gross mode is selected AND no empty weight resolves through the cascade (spool → filament → vendor), surface the "Empty-spool weight is missing — we'll ask you for it on Save" preview (already in `weight_entry.js:263`) and add a **third button option** alongside "Provide weight" and "Cancel": **"Skip — save as Used Weight"**.
- "Skip" downgrades the entry from Gross to Net for this submission only (no persistence change to the spool's stored tare). The math becomes `used_weight = initial_weight - net_weight` where net = the user's input treated as already-tared.
- Either that, OR display the `(none)` tare as 0 with a non-blocking warning banner. Pick whichever has less ambiguity for the user — the Skip-with-mode-downgrade is more accurate but more explanation; the warning-banner approach is simpler. Recommend the Skip path with a tooltip explaining the downgrade.
- Make sure the "missing tare" prompt for the cascade write path (where the user IS asked for the empty weight on save and the value is then persisted to the spool) stays available as the primary option. The skip is the escape hatch, not the default.

**Files:**
- `inventory-hub/static/js/modules/weight_entry.js` — overlay's missing-tare prompt + Save handler
- `inventory-hub/static/js/modules/inv_details.js` — `showArchiveEmptyWeightPrompt` (related but legacy; verify the overlay-path is the active one for Quick-Weigh)
- `inventory-hub/tests/test_weight_entry_overlay.py` — extend with a Skip-path test

**Acceptance criteria:**
- [ ] In Gross mode with no resolvable empty weight, Save offers three options: Provide weight (existing), Skip (new), Cancel (existing)
- [ ] Skip submits the value as Net (no Gross math applied; no tare persisted to the spool)
- [ ] The default flow (provide weight + save) still writes the tare to the spool extra
- [ ] Regression test for the Skip path; existing missing-tare-prompt test still passes

### 13.8 — Main-menu eject shouldn't block when printer is non-idle (+ duplicate confirm modal no-op)
**Buglist ref:** L150
**What:** "Ejecting from main menu while the printer is in a non idle state causes the location to not be updated/removed from the toolhead. I was in the process of preping to insert another new filament into the printer. This shouldn't be a blocking move. Also the modal to aprove came up twice, and did nothing when selecting yes. So theres that too."

Two compounding bugs:

**Part A — Eject blocks on non-idle state.** When the printer is mid-prep (heating, homing, anything not strictly idle), the eject path no-ops without surfacing why. Derek's case: he was prepping for a filament swap, eject is exactly the right operation at that moment. The `confirm_active_print` gate that landed during the locations refactor is over-broad — it should only block when an actual print is running and the spool's used_weight could still grow, not when the printer is in any non-idle state.

**Part B — Confirm modal shows twice + selecting Yes does nothing.** Indicates a duplicate listener / event-dispatch race — the confirm-overlay is being opened twice (likely once by the eject button handler, once by the smart-move path's own confirm), and the inner one's Yes handler is wired to a stale reference. Same family as the past nested-Swal bugs documented in CLAUDE.md.

**Files:**
- `inventory-hub/logic.py` — `perform_smart_eject` + `perform_smart_move` `confirm_active_print` gate
- `inventory-hub/static/js/modules/inv_cmd.js` — main-menu eject button handler (search for the eject command-deck button)
- `inventory-hub/static/js/modules/inv_details.js` — any eject confirm overlay shared with the main-menu button
- `inventory-hub/tests/test_force_eject_keyboard_e2e.py` or similar — extend with a non-idle-state eject test

**Acceptance criteria:**
- [ ] Eject from main menu succeeds when printer is non-idle but not actively printing (heating, prep, paused)
- [ ] Confirm modal shows exactly once on eject
- [ ] Selecting Yes on the confirm modal completes the eject and clears the toolhead binding
- [ ] PrusaLink state probe (see memory `reference_prusalink_state_probe.md`) classifies "active print" precisely — only `Printing` / `Pausing` / `Resuming` should trigger the block, not `Heating` / `Homing` / `Operational`
- [ ] Regression test covers each printer state classification

### 13.9 — Quick-Weigh default mode preference
**Buglist ref:** L152
**What:** "Quick weight modal, should have a way to set a perfered weighing methiod. I currently use gross more when I'm working on a filament swap than the additive. I'd like to be able to change the default mode, instead of it always defaulting to additive. Not sure how we do this. perhaps added to a general system configuration mode, which has yet to be implemented."

**Approach (ship now, surface later in Config):**
Use `localStorage` for the preference key `fcc.weighEntry.defaultMode` (one of `gross` / `additive` / `net` / `set`). On `<WeightEntry>` overlay open, read the key and select that mode tab. Add a small "Set as default" affordance (link or button next to the mode tabs) that writes the current mode to localStorage.

This is intentionally a *user-preference shortcut* rather than waiting on the Config system (L12, still NEEDS DESIGN). When the Config system lands, this preference can be migrated to its config schema as a routine value-move; no architectural decision is being made here that would block that migration. Document the key in CLAUDE.md so the Config-system design picks it up.

**Files:**
- `inventory-hub/static/js/modules/weight_entry.js` — read/write the preference, default selection on open
- `inventory-hub/static/js/modules/shortcuts_registry.js` — possibly register `D` (or similar) to "Set current mode as default" inside the overlay
- `CLAUDE.md` — note the localStorage key under a "User preferences (pre-Config-system)" subsection
- `inventory-hub/tests/test_weight_entry_overlay.py` — preference-persistence test

**Acceptance criteria:**
- [ ] Overlay opens to the last-selected default mode (not always Additive)
- [ ] "Set as default" persists the current mode for next open
- [ ] localStorage key documented so Config-system migration knows where to look
- [ ] Default-on-open fallback when localStorage is unavailable / corrupted

## Testing Checklist

- [ ] Manual repro and verify all 9 fixes in dev
- [ ] Existing Quick-Weigh tests still pass; new focus test added
- [ ] Existing Location Manager / dryer-box tests still pass; regression tests added for 13.2 + 13.3
- [ ] Full regression sweep before commit
- [ ] Activity Log + Toast coverage matches CLAUDE.md spec for any new failure paths

## Dependencies

- None. Group 1 + Group 2 are DONE so the unified weight + buffer-refresh paths are stable to build on.
- Coordinate with Location Manager Phase 1B (Phase tracker on buglist L207) — if that lands first, 13.2's investigation might want the new `parent_id` lookups instead of prefix splits.
