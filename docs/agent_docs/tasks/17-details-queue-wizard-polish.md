# Group 17: Details Modal, Queue & Wizard End-State Polish

**Branch name:** `feature/details-queue-wizard-polish`
**Estimated effort:** ~3–4 hours
**Risk:** Low-Medium — five small UX polish items across stable surfaces; one (17.4) extends the existing `duplicate_picker.js` flow

## Goal

Tighten the details-modal / print-queue / wizard-end-state UX with five small fixes Derek flagged during Group 10 wrap-up. All items share neighbor surfaces (`inv_details.js` / `inv_queue.js` / `inv_wizard.js` / `duplicate_picker.js`) — bundle them so one branch ships the cluster.

## Items to Complete

### 17.1 — Filament sample status in display + edit modals
**Buglist ref:** L144
**What:** "Add filament sample status to the display modal, as well as the edit section. So that I can easily see if a swatch has be created for an item. Perhaps also include if a label print has been confirmed, to help trace down lagacy labels that need to be updated."

**Approach:**
- Surface the `has_sample` / `sample_print_confirmed` extras (or whichever field name we use today — confirm via `/api/filament/<id>` payload) on the Filament Details modal as a fact-card row alongside the existing rows.
- Mirror on the Edit Filament modal so users can flip the flag without going through a separate workflow.
- Add a "Label printed (confirmed)" indicator separately — useful for tracking legacy labels needing reprint. Pull from `extra.needs_label_print` (true → not yet confirmed; false → confirmed; null → never touched).

**Files:**
- `inventory-hub/static/js/modules/inv_details.js` — `openFilamentDetails` rendering + Edit Filament modal save handler
- `inventory-hub/templates/components/modals_details.html` — fact-card row markup
- `inventory-hub/tests/test_filament_edit_button.py` — extend with status-display tests

**Acceptance criteria:**
- [ ] Details modal shows sample-status (Yes / No / —) and label-print-confirmed status
- [ ] Edit Filament modal exposes both as toggleable fields
- [ ] Existing details/edit tests still pass

### 17.2 — Don't auto-open print queue from Filament Display modal
**Buglist ref:** L146
**What:** "I don't think the queue all active spools in the Filament Display modal should automatically open the print queue window, it causes firction if I also need to print a new label for the filament, or need to queue up more labels from other filaments/spools."

**Approach:**
- Remove the auto-open-queue call from the "Queue all active spools" button handler in the Filament Display modal.
- Replace with a toast confirmation ("N labels queued") and leave the queue panel where it was.
- Verify the existing queue-add path still works (the auto-open was layered on top of a working flow).

**Files:**
- `inventory-hub/static/js/modules/inv_details.js` — "Queue all active spools" button click handler
- `inventory-hub/static/js/modules/inv_queue.js` — verify `addToQueue` doesn't itself open the panel

**Acceptance criteria:**
- [ ] Clicking "Queue all active spools" enqueues labels and toasts confirmation
- [ ] Print queue panel does NOT auto-open
- [ ] User can continue adding labels from other filaments/spools without re-closing the panel

### 17.3 — Queue-label button on just-created spool (wizard end state)
**Buglist ref:** L148
**What:** "Add a queue labe for a spool that was just created. in the bottom section, that becomes visible once it's created. So that I can easily queue a label from there with out having to find it in the filament spool list."

**Approach:**
- Save Group 10's "shipped spool ID list" at the bottom of the wizard's success state (Session A/B/C already display the count).
- Add a "🖨️ Queue label" button next to each shipped spool ID.
- Click fires `addToQueue({type: 'spool', id: <id>})` and toasts confirmation. Stays in wizard UI; doesn't navigate.

**Files:**
- `inventory-hub/static/js/modules/inv_wizard.js` — success-state rendering + new button handler

**Acceptance criteria:**
- [ ] After spool creation, each just-shipped spool ID has a Queue-label button
- [ ] Click queues label without leaving the wizard
- [ ] Multi-spool creation: each row gets its own button
- [ ] Regression test covering the new affordance

### 17.4 — "Add new" path in duplicate Legacy ID picker
**Buglist ref:** L150
**What:** "Multiple spools share Legacy ID XX, should have an add new button if one isn't sure if any of the items on the list are the correct one."

**Approach:**
- Extend [duplicate_picker.js](inventory-hub/static/js/modules/duplicate_picker.js) so the picker overlay (currently showing candidate spools) adds a "➕ Create new spool" button.
- Click routes through the existing add-inventory wizard with the legacy id pre-populated.
- Pattern reference: same idea as Group 6's vendor-create flow — fall back to wizard create-mode when no existing entity is the right match.

**Files:**
- `inventory-hub/static/js/modules/duplicate_picker.js` — picker overlay rendering + Add-new button
- `inventory-hub/static/js/modules/inv_wizard.js` — accept legacy-id prefill option on launch
- `inventory-hub/tests/test_print_queue.py` (or wherever duplicate_picker tests live) — new test for the add-new path

**Acceptance criteria:**
- [ ] Ambiguous Legacy ID scan picker shows "➕ Create new" alongside candidates
- [ ] Add-new launches the wizard with legacy id pre-filled
- [ ] Existing "use selected" + "print new label" paths still work
- [ ] Regression test covering the add-new path

### 17.5 — Show empty-spool weight on backfill button (or filament details modal)
**Buglist ref:** L152
**What:** "Back fill weight from filament modal button should show the empty spool weight being use for back fill, or we should just add that to the filament details modal. So the user doesn't have to load up the edit modal to see what the value is."

**Approach (pick one — recommend B):**
- **A.** Update the Backfill button label/tooltip to include the empty-spool weight resolved through the cascade. Compact, but only visible at click time.
- **B.** Add `Empty Spool Weight: <N>g <inheritance badge>` as a fact-card row on the Filament Details modal. Use `resolveEmptySpoolWeightSource` (already exists in `weight_utils.js`) so the inheritance badge ("↩ from vendor" / "↩ from filament" / etc.) matches the Edit Filament modal.

**Recommendation:** Ship B. Persistent visibility, no Edit-modal round-trip, and we already have the resolver.

**Files:**
- `inventory-hub/static/js/modules/inv_details.js` — Filament Details fact-card row
- `inventory-hub/templates/components/modals_details.html` — markup
- `inventory-hub/static/js/modules/weight_utils.js` — already exposes `resolveEmptySpoolWeightSource`, reuse it

**Acceptance criteria:**
- [ ] Filament Details modal shows the resolved empty-spool weight + inheritance badge
- [ ] Badge accurately reflects the cascade source (filament's own value vs. vendor inheritance)
- [ ] Regression test covering the new row

## Testing Checklist

- [ ] Manual repro and verify all 5 fixes in dev
- [ ] Full sweep stays green
- [ ] Each fix is its own commit so bisect remains clean

## Dependencies

- Group 9 (Quick-Swap + Printer Status, DONE) — no overlap, but the 9.3 prod regression at L140 is unrelated to this group
- Group 10 (Wizard UX Overhaul, DONE) — 17.3 uses the success-state surface Session C polished
- Group 15 (Canonical Overlay-Mount Helper, DONE) — 17.4 should use `mountOverlay()` for the add-new confirm flow
