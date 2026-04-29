# Group 10: Add/Edit Wizard UX Overhaul

**Branch name:** `feature/wizard-ux-overhaul`
**Estimated effort:** ~5.5–7 hours (can split into two sessions)
**Risk:** HIGH — wizard is 144KB, complex, regression-prone

## Goal

Modernize the Add/Edit Inventory Wizard's UX flow and fix field-level bugs.

> ⚠️ **This is the highest-risk group.** Plan for a dedicated testing pass. Consider splitting into two sessions: Session A (items 10.1–10.3: flow & defaults) and Session B (items 10.4–10.8: field fixes & audit).

## Items to Complete

### 10.1 — Wizard UX cleanup pass
**Buglist ref:** L41
**What:** The wizard is functional but clunky — too much data shown at once, not intuitive. Needs modernization without losing functionality.

**Approach:** Audit the step flow, identify what can be collapsed/hidden behind progressive disclosure, improve visual hierarchy. Do NOT remove functionality — reorganize it.

### 10.2 — Location selector is clunky
**Buglist ref:** L37
**What:** User has to delete existing text to see the full location list. Needs a proper searchable dropdown/combobox pattern.

### 10.3 — New spools should default to unassigned
**Buglist ref:** L35
**What:** If no location is provided, newly created spools should default to "Unassigned" rather than requiring explicit selection.

### 10.4 — Consolidate duplicate purchase link fields
**Buglist ref:** L160
**What:** Two purchase links exist — one inherited from filament, one on the spool. Need to consolidate to one field or implement smart fallback (prefer spool-specific, fall back to filament). One field doesn't clear between usages.

### 10.5 — New slicer profile should auto-add to current filament
**Buglist ref:** L161
**What:** Creating a new slicer profile from within the wizard should auto-associate it with the filament being edited.

### 10.6 — Spoolman field ordering bug
**Buglist ref:** L162
**What:** Custom fields move around when modified or when new items are added. Need to lock down field order.

### 10.7 — Maintain multi-spool creation ability
**Buglist ref:** L158
**What:** Guard/verify that the ability to add multiple spools of the same type at once still works after any wizard changes.

### 10.8 — SweetAlert2 nested modal audit
**Buglist ref:** L163
**What:** Audit existing code for nested `Swal.fire()` calls and replace with inline overlay divs per project convention.

**Primary file:** `inventory-hub/static/js/modules/inv_wizard.js` (144KB)
**Template:** `inventory-hub/templates/components/modals_wizard.html`
**Backend:** `inventory-hub/app.py` — wizard endpoints

### 10.9 — Filament-attributes input validation (prevention guards)
**Buglist ref:** L219–L237
**What:** The filament-attributes choice list has dead/bogus entries (`Tran`, `F`, `Carbon-Fiber`, etc.) created by unchecked input. Spoolman makes new choices permanent — removal requires a destructive snapshot-restore migration. Prevention guards in the wizard's "+ Add new attribute" flow will stop new garbage entries from being created.

**Guards to implement:**
- **Minimum length** (≥3 chars) — blocks single-char typos like `F`
- **Trim + reject leading/trailing punctuation** (`;`, `,`, `:`, `/`) — blocks separator confusions like `Transparent; High-Speed`
- **Fuzzy/prefix match warning** — when new value is ≤2 Levenshtein edits of an existing choice, or is a prefix of one, or collapses to the same normalized string: show "Did you mean: <existing>?" with Use existing (default) vs. Add as new (confirm) — catches `Tran`→`Transparent`, `Carbon-Fiber`→`Carbon Fiber`
- **Two-step confirm for add-new** — confirm dialog: "Add '<value>' as a permanent new filament attribute? This cannot be undone via the UI."
- **Live preview of canonical stored value** — show post-trim/normalization result before commit

**Files:**
- `inventory-hub/static/js/modules/inv_wizard.js` — "+ Add new" handler on materials/attributes multiselect
- Apply same guards to any other add-new-choice entry point (Edit Filament parity surface)

**Acceptance criteria:**
- [ ] Single-char inputs rejected with inline error
- [ ] Leading/trailing punctuation trimmed or rejected
- [ ] Fuzzy-match prompt fires for near-duplicates
- [ ] Two-step confirm before a new choice is committed to Spoolman
- [ ] Existing choices can still be selected without any prompt

### 10.10 — Location search box should show all locations after selection
**Buglist ref:** L129
**What:** Once a valid location is selected or loaded in the wizard, the location search/combobox should display the full location list (not filter it down). Same fix should propagate to all other location search text boxes in the app.

**Files:**
- `inventory-hub/static/js/modules/inv_wizard.js` — wizard location combobox
- Any other location search/combobox instances

**Acceptance criteria:**
- [ ] Selecting a location in the wizard doesn't permanently filter the dropdown
- [ ] Full location list is accessible after a selection is made
- [ ] Consistent behavior across all location search boxes

## Dependencies

- Ideally do after Group 1 (Weight Unification) so weight fields in the wizard use the unified path.
- Group 7 (Testing) being done first means tests are in better shape for regression catching.
