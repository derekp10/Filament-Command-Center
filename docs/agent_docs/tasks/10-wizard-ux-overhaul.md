# Group 10: Add/Edit Wizard UX Overhaul

**Branch name:** `feature/wizard-ux-overhaul`
**Estimated effort:** ~5–6 hours (can split into two sessions)
**Risk:** HIGH — wizard is 144KB, complex, regression-prone

## Goal

Modernize the Add/Edit Inventory Wizard's UX flow and fix field-level bugs.

> ⚠️ **This is the highest-risk group.** Plan for a dedicated testing pass. Consider splitting into two sessions: Session A (items 10.1–10.3: flow & defaults) and Session B (items 10.4–10.8: field fixes & audit).

## Items to Complete

### 10.1 — Wizard UX cleanup pass
**Buglist ref:** L58
**What:** The wizard is functional but clunky — too much data shown at once, not intuitive. Needs modernization without losing functionality.

**Approach:** Audit the step flow, identify what can be collapsed/hidden behind progressive disclosure, improve visual hierarchy. Do NOT remove functionality — reorganize it.

### 10.2 — Location selector is clunky
**Buglist ref:** L52
**What:** User has to delete existing text to see the full location list. Needs a proper searchable dropdown/combobox pattern.

### 10.3 — New spools should default to unassigned
**Buglist ref:** L50
**What:** If no location is provided, newly created spools should default to "Unassigned" rather than requiring explicit selection.

### 10.4 — Consolidate duplicate purchase link fields
**Buglist ref:** L94
**What:** Two purchase links exist — one inherited from filament, one on the spool. Need to consolidate to one field or implement smart fallback (prefer spool-specific, fall back to filament). One field doesn't clear between usages.

### 10.5 — New slicer profile should auto-add to current filament
**Buglist ref:** L95
**What:** Creating a new slicer profile from within the wizard should auto-associate it with the filament being edited.

### 10.6 — Spoolman field ordering bug
**Buglist ref:** L96
**What:** Custom fields move around when modified or when new items are added. Need to lock down field order.

### 10.7 — Maintain multi-spool creation ability
**Buglist ref:** L92
**What:** Guard/verify that the ability to add multiple spools of the same type at once still works after any wizard changes.

### 10.8 — SweetAlert2 nested modal audit
**Buglist ref:** L97
**What:** Audit existing code for nested `Swal.fire()` calls and replace with inline overlay divs per project convention.

**Primary file:** `inventory-hub/static/js/modules/inv_wizard.js` (144KB)
**Template:** `inventory-hub/templates/components/modals_wizard.html`
**Backend:** `inventory-hub/app.py` — wizard endpoints

## Dependencies

- Ideally do after Group 1 (Weight Unification) so weight fields in the wizard use the unified path.
- Group 7 (Testing) being done first means tests are in better shape for regression catching.
