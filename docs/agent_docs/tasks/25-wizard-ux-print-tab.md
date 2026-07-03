# Group 25: Wizard UX — Print, Tab-Confirm & Spool-Label Parity

**Branch name (when started):** `feature/wizard-ux-print-tab`
**Estimated effort:** ~3–4 hours
**Risk:** **LOW.** Pure-frontend, all in [inv_wizard.js](../../../inventory-hub/static/js/modules/inv_wizard.js). No backend / Spoolman-write changes (25.3 reuses the existing `flag_spool_labels` endpoint). The label "print" here means **queue a label** (`window.addToQueue`), NOT the print-usage deduct (Group 22) — different subsystem.

> **Status: ✅ DONE 2026-07-01** (`feature/group-25-wizard-ux-print-tab` → `dev`). All 3 items shipped, pure-frontend `inv_wizard.js`. **25.I**: `Tab` branch in the shared `wizardBindCombobox` keydown confirms the highlighted/typed item (location + vendor) without `preventDefault` so focus advances. **25.3**: extracted `window.wizardBuildFilamentLabelDiff(orig, fPayload)` + added the `original_color` comparison it was missing, so a wizard Color-name edit flags spool labels via the shared `_maybePromptLabelReprint` (parity with the primary Edit-Filament path). **25.H**: extracted `window.wizardRenderPostSaveQueueActions(...)` — a "🖨️ Queue All" button for multi-create rounds + a queue chip in edit mode (previously none). 11-agent adversarial review found + fixed 1 real bug (a pass-through Tab fired a bubbling `change` → spurious `isDirty` flip → false "Unsaved Changes" prompt; now guarded on actual-change, applied to Enter too). 13 new tests (`test_wizard_group25.py`) + 34 green regression, 0 regressions. Original scope below.
>
> _Original (filed 2026-06-15 by `/refresh-groups`; 25.3 added 2026-06-29 from the Group 23 cleanup verification):_ Three small add/edit-wizard interaction-polish items that share one file. **Did NOT nest under the DONE Group 10 (Wizard UX Overhaul) or Group 17 (post-create chips)** — completed epics get lifted on archive, so nested follow-ups vanish ([[feedback_standalone_followups_not_under_completed_epics]]).

## Why these are one group

All three are self-contained UX/parity polish on the Add/Edit Wizard in the SAME file (`inv_wizard.js`) — the post-create/edit print affordance (25.H), a combobox keydown tweak (25.I), and the edit_spool change-diff parity fix (25.3). They share no surface with the now-DONE Group 23 (which was `inv_details.js` editfilExternal import/scrape), though 25.3 restores parity with a Group 23.3 behavior. Cohesive, low-risk, ship together.

## Items

### 25.H — Print-filament button for existing filaments + "Print All" for multi-create (buglist 2026-06-15, item H)
**Buglist:** "Add/edit wizard should have a print filament button for existing filaments. And there should be a print all option if creating multiple. (Had an 8-filament round where I just had to click the 8 different buttons.)"
**Grounded:**
- Post-create label chips exist ONLY in the create path: on a successful CREATE, [inv_wizard.js:2809-2838](../../../inventory-hub/static/js/modules/inv_wizard.js#L2809) renders one `🖨️ #{sid}` chip per created spool into `#wiz-postcreate-actions`, each wired to `window.addToQueue({id, type:'spool'})` (single-spool; Group 17.3 lineage). **No "print all" / bulk-queue helper exists** — `addToQueue` ([inv_queue.js:24](../../../inventory-hub/static/js/modules/inv_queue.js#L24)) only ever adds ONE item. So an 8-spool round = 8 chips to click individually.
- The chip block is **gated off in edit mode** (`wizardState.mode !== 'edit_spool'`, line 2811), so the edit-spool path ([inv_wizard.js:3088-3220](../../../inventory-hub/static/js/modules/inv_wizard.js#L3088), mode set at :3111) renders **no print/queue button** for the existing spool being edited.
**Fix:**
- Add a **"🖨️ Queue All"** button beside the per-spool chips that iterates `data.created_spools` calling `addToQueue` once each (de-dupe against `window.labelQueue` like the per-chip handler at :2826).
- Add a **print/queue button in the edit-spool path** for the existing `wizardState.editSpoolId` (`window.addToQueue({id: editSpoolId, type:'spool'})`).
**Open Qs (Derek):** (1) should "Queue All" auto-disable/turn green like the per-spool chips (:2832) once clicked + de-dupe already-queued spools? (2) should queuing from edit also flip `needs_label_print` (Group 17.1 un-hid that field)?
**Surface:** `inv_wizard.js:2809-2838` (post-create chips) + `:3088-3220` (edit-spool path); `inv_queue.js:24` (`addToQueue` — the only queue primitive; a bulk helper could optionally live here).

### 25.I — Location/vendor combobox: Tab should confirm the highlighted item like Enter (buglist 2026-06-15, item I)
**Buglist:** "Location field in add/edit filament, when typing a match, hitting Tab should confirm the highlighted item into the field (just like Enter does)."
**Grounded:** the combobox keydown handler `window.wizardBindCombobox` ([inv_wizard.js:935-971](../../../inventory-hub/static/js/modules/inv_wizard.js#L935)) handles ArrowDown/ArrowUp (moves the `.active bg-primary` highlight), **Enter** (confirms: sets `search.value`/`hidden.value` from the active `.autocomplete-option`, falls back to `visible[0]`, closes the dropdown, fires `change`), and Escape — but has **no `Tab` branch**, so Tab falls through to the browser default: focus leaves WITHOUT confirming the highlight (and the `input` handler only captures a value on an EXACT label match, so partial-match-then-Tab leaves `hidden.value` empty). The helper is shared by the location combobox (bound at `:1385`) AND vendor (`:1268`), so one fix covers both.
**Fix:** add a `Tab` branch mirroring the Enter branch (confirm `.active`, fallback `visible[0]`). **UX choice (Derek's wording implies Enter's behavior):** confirm-then-let-Tab's-default-advance-focus (do NOT `preventDefault`) — Enter confirms + closes but doesn't advance focus; letting Tab proceed gives the natural "confirm and move on." ~5 lines.
**Surface:** `inv_wizard.js:935-971` (`wizardBindCombobox` keydown; Enter branch at :957-967 is the template).

### 25.3 — Spool-label flag parity: wizard `edit_spool` omits `original_color` (buglist 2026-06-29, from the Group 23 cleanup verification)
**Buglist:** the Group 23.3 spool-label flag (`POST /api/filament/<id>/flag_spool_labels`, raised when a spool-visible field — Brand/Type/Color-name — changes so the spool's `needs_label_print` is set) fires correctly from the PRIMARY Edit-Filament modal (`inv_details.js`), but the wizard `edit_spool` save **re-implements its own change-diff** (`inv_wizard.js:~2896-2927`) and **OMITS `original_color`** — so editing ONLY the color name through the wizard won't flag the filament's spools for reprint.
**Grounded (Group 23 verification, 2026-06-29):** the wizard reuse path diffs only `filament_attributes` into its `changedExtras`, not `original_color`; the primary path's `spoolLabelChanged` (inv_details.js) correctly triggers on `original_color`. Secondary-surface partial-reuse gap — not a failure of 23.3 itself (which is DONE + verified).
**Fix:** include `original_color` in the wizard `edit_spool` `changedExtras` diff so it fires the same `flag_spool_labels` call. **Better:** extract the shared "which fields flag spool labels" trigger into one helper used by BOTH `inv_details` and `inv_wizard` so the two diffs can't drift again. No backend change (the endpoint already exists).
**Surface:** `inv_wizard.js:~2896-2927` (the edit_spool change-diff); reference `inv_details.js` `spoolLabelChanged` (the correct trigger) + `POST /api/filament/<id>/flag_spool_labels`.

## Recommended order
1. **25.I** (highest value / lowest risk — ~5-line keydown branch, fixes keyboard muscle-memory on every location/vendor field).
2. **25.3** (small, contained — add `original_color` to the wizard edit_spool diff; ideally extract the shared trigger helper while you're there).
3. **25.H** "Queue All" (small loop in the existing chip block), then the print-existing button in the edit-spool path.

## Out of scope / do NOT do
- Backend / Spoolman changes — both items are frontend-only.
- Confusing this "print" (label queue) with Group 22's print-usage deduct.
- Nesting under the DONE Group 10/17.
