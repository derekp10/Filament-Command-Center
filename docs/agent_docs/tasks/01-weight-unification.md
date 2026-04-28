# Group 1: Weight Handling Unification

> **Status: Phase 1 DONE 2026-04-27** — L34 (wizard auto-prefill + badge) and L46 (post-archive prompt Enter key) shipped on `feature/weight-unification`. L48 was partially addressed (extracted `resolveEmptySpoolWeight` to `weight_utils.js`); the full unification plus L38 (gross-weight workflow) were rolled into **Group 12 — Weight Entry Unified Component (Phase 2)** for a focused design pass. See `tasks/12-weight-entry-component.md` and `completed-archive.md` for details.

**Branch name:** `feature/weight-unification`
**Estimated effort:** ~3–4 hours
**Risk:** Medium — touches multiple UI flows but logic is straightforward

## Goal

Eliminate the fragmented weight-update logic scattered across 4+ code paths. Create a single shared module/function that all weight operations call, ensuring empty spool weight is always subtracted and keyboard interactions work consistently.

## Items to Complete

### 1.1 — Unify all weight handling code
**Buglist ref:** L48
**What:** Currently, weight update logic is copy-pasted in the wizard, main-menu QR button, weigh-out flow, and details modal — each with slightly different math. Create a single `calculateNetFilamentWeight(totalWeight, spoolWeight)` utility (or equivalent) that every path calls.

**Files to audit:**
- `inventory-hub/static/js/modules/inv_wizard.js` — wizard weight fields
- `inventory-hub/static/js/modules/inv_weigh_out.js` — weigh-out flow
- `inventory-hub/static/js/modules/inv_core.js` — main-menu weight update button
- `inventory-hub/static/js/modules/inv_details.js` — details modal weight display
- `inventory-hub/app.py` — backend weight update endpoints
- `inventory-hub/logic.py` — smart_move / smart_eject weight handling
- `inventory-hub/spoolman_api.py` — Spoolman write calls for weight

**Acceptance criteria:**
- [ ] Single shared function for net-weight calculation exists
- [ ] All weight-update paths call the shared function
- [ ] Unit test proves `totalWeight - spoolWeight = netWeight`

### 1.2 — Weight update button doesn't subtract empty spool weight
**Buglist ref:** L38
**What:** The QR-code weight update button on the main menu sets `remaining_weight` to the raw total weight without subtracting `spool_weight` (empty spool weight). This overwrites the correct value with a too-high number.

**Root cause:** The code behind the weight update button doesn't look up the spool's `spool_weight` field before writing. Fix by using the unified function from 1.1.

**Acceptance criteria:**
- [ ] Weight update button reads `spool_weight` from the spool record
- [ ] Subtracts it before writing to `remaining_weight`
- [ ] If `spool_weight` is null/0, prompts user or uses total as-is with a warning

### 1.3 — Add empty spool weight pull from parent filament
**Buglist ref:** L34
**What:** The Edit Filament modal already supports setting `empty_spool_weight` on the filament. This should propagate to the wizard and other places as a default when creating/editing spools (if the spool doesn't have its own override).

**Files:**
- `inventory-hub/static/js/modules/inv_wizard.js` — add inheritance lookup
- `inventory-hub/app.py` — ensure API returns filament's `empty_spool_weight` in spool context

**Acceptance criteria:**
- [ ] Wizard pre-fills spool weight from parent filament's `empty_spool_weight` if spool's own value is empty
- [ ] User can override the inherited value
- [ ] Clear visual indicator that value is "inherited from filament"

### 1.4 — Missing spool weight dialog doesn't accept Enter
**Buglist ref:** L46
**What:** When the missing-spool-weight dialog pops up asking the user to enter an empty spool weight, pressing Enter does nothing — user must click the confirm button with the mouse.

**Fix:** Add `keydown` listener for Enter on the dialog's input field that triggers the confirm action.

**Acceptance criteria:**
- [ ] Enter key submits the missing spool weight dialog
- [ ] Escape key dismisses it
- [ ] Focus is auto-set to the input field when the dialog opens

## Testing Checklist

- [ ] Enter a weight via main-menu QR button on a spool that has `spool_weight` set → verify `remaining_weight` = entered - spool_weight
- [ ] Enter a weight on a spool with NO `spool_weight` → verify prompt appears
- [ ] Create a new spool via wizard for a filament that has `empty_spool_weight` → verify pre-fill
- [ ] Override the pre-filled spool weight → verify override sticks
- [ ] Test missing-spool-weight dialog with Enter key
- [ ] Run existing weight-related tests: `test_weight_setting_dispatches_events.py`

## Dependencies

- None — this is the recommended first group to tackle.
