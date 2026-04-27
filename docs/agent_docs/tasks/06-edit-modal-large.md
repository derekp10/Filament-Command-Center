# Group 6: Edit Filament & Details Modal — New Panels

**Branch name:** `feature/edit-modal-new-panels`
**Estimated effort:** ~3 hours
**Risk:** Medium — new modal surfaces, but following established patterns

## Goal

Build the external-metadata import panel for the Edit Filament modal and create the new Manufacturer/Vendor Edit Modal V1.

## Items to Complete

### 6.1 — External-metadata import panel for Edit Filament modal
**Buglist ref:** L8
**Decision made:** Build a slim single-URL quick-paste panel as a new dedicated section (not inside Advanced).

**Design spec:**
1. New section in Edit Filament modal: "Import from External"
2. Single URL input field with a "Parse" button
3. Preview panel showing what the parser found, field by field
4. Each field has a checkbox to apply/skip
5. "Apply Selected" button writes the checked fields

**Reuse from wizard:**
- Backend: `inventory-hub/external_parsers.py` parse logic
- Frontend: Result display patterns from `inv_wizard.js` import panel

**Files:**
- `inventory-hub/static/js/modules/inv_details.js` — new import section
- `inventory-hub/templates/components/modals_details.html` — section markup
- `inventory-hub/app.py` — parse endpoint (may already exist for wizard, reuse)
- `inventory-hub/external_parsers.py` — ensure parsers return data in a format the edit modal can consume

**Acceptance criteria:**
- [ ] New "Import from External" section visible in Edit Filament modal
- [ ] Pasting a Prusament URL and clicking Parse shows a preview
- [ ] User can select which fields to apply
- [ ] Applied fields update the modal's form values (saved on modal save)
- [ ] Section is separate from Advanced (its own collapsible or tab)

### 6.2 — Manufacturer/Vendor Edit Modal V1
**Buglist ref:** L42
**What:** New modal that mirrors the Edit Filament modal in look and function. V1 scope is strictly Spoolman-native manufacturer fields only: name, website, comment/notes.

**Design spec:**
- Same visual design language as Edit Filament modal
- Same save/cancel behavior
- Same layout patterns (card header, sections, action buttons)
- No custom `extra` fields in V1
- No backfill utility or external-metadata import in V1

**Files:**
- `inventory-hub/static/js/modules/inv_details.js` — new modal or new file `inv_vendor_edit.js`
- `inventory-hub/templates/components/modals_details.html` — or new `modals_vendor.html`
- `inventory-hub/app.py` — CRUD endpoints for manufacturer/vendor
- `inventory-hub/spoolman_api.py` — Spoolman manufacturer API calls

**Spoolman manufacturer API:**
- `GET /api/v1/vendor` — list all
- `GET /api/v1/vendor/<id>` — get one
- `PATCH /api/v1/vendor/<id>` — update
- Verify actual field names in Spoolman docs

**Acceptance criteria:**
- [ ] Manufacturer Edit modal opens from appropriate entry points (details modal, etc.)
- [ ] Displays name, website, and comment/notes fields
- [ ] Save writes to Spoolman successfully
- [ ] Cancel discards changes
- [ ] Visual design matches Edit Filament modal
- [ ] Activity log records edits

## Testing Checklist

- [ ] Parse a Prusament URL in Edit Filament modal → verify preview → apply → save → verify data persists
- [ ] Open Manufacturer Edit → change name → save → verify in Spoolman
- [ ] Cancel manufacturer edit → verify no changes saved
- [ ] Visual consistency check: Edit Filament vs Manufacturer Edit side by side

## Dependencies

- Group 5 (small additions) should ideally land first so the Edit Filament modal is stable before adding the import panel.
- Group 11 (External Parsers audit) is complementary — if done first, you'll know which parsers work before building the import panel.
