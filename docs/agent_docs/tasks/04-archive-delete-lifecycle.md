# Group 4: Archive / Delete / Cleanup Lifecycle

**Branch name:** `feature/archive-delete-lifecycle`
**Estimated effort:** ~3 hours
**Risk:** Medium — delete is destructive, needs careful confirmation UX

## Goal

Fix the broken Spoolman filament archiving, unblock the auto-unarchive feature, add delete capability with safety rails, and clean up duplicate/malformed filament attributes.

## Items to Complete

### 4.1 — [IMPORTANT] Spoolman filament archiving is broken
**Buglist ref:** L3
**What:** `PATCH /api/v1/filament/<id>` with `{"archived": true}` returns 200 but the flag is silently dropped. Spoolman never reports `archived: true` on filaments (only spools).

**Investigation steps:**
1. Check the installed Spoolman version — does it support filament archival?
2. If not supported: implement archive tracking via a custom `extra` field (e.g., `extra.fcc_archived`)
3. If supported on newer version: document the upgrade path

**Files:**
- `inventory-hub/spoolman_api.py` — `update_filament()` archive call
- `inventory-hub/app.py` — `api_create_inventory_wizard` auto-unarchive logic

**Acceptance criteria:**
- [ ] Filament archive state is trackable (either via native Spoolman or custom extra field)
- [ ] `test_wizard_ux_polish.py::test_create_spool_auto_unarchives_parent_filament` passes (currently skipped)

### 4.2 — Auto-unarchive when adding filament to archived filament
**Buglist ref:** L18
**What:** Adding a spool to an archived filament should automatically unarchive that filament. Code is already in place at `app.py:api_create_inventory_wizard` but is unreachable because of 4.1.

**Blocked by:** 4.1 — once archive tracking works, this should "just work." Verify and test.

**Acceptance criteria:**
- [ ] Creating a spool under an archived filament auto-unarchives the filament
- [ ] Activity log records the auto-unarchive
- [ ] Toast confirms: "Parent filament was automatically unarchived"

### 4.3 — Delete spools and filaments in UI
**Buglist ref:** L56
**What:** There's currently no way to delete spools or filaments from the UI. This should be hard to reach and require double confirmation. Deleting a filament should cascade and delete all child spools.

**Design:**
- Access via the Details modal → gear/settings icon → "Delete" option (buried, not prominent)
- First confirmation: "Are you sure? This will permanently delete this spool/filament."
- Second confirmation: "Type the spool/filament ID to confirm deletion." (destructive action pattern)
- For filament deletion with child spools: "This filament has N spools. Deleting it will also delete all N spools. Type CONFIRM to proceed."
- Use inline overlay confirmation (not nested Swal — per project convention)

**Files:**
- `inventory-hub/static/js/modules/inv_details.js` — add delete action to details modal
- `inventory-hub/templates/components/modals_details.html` — delete confirmation UI
- `inventory-hub/app.py` — delete endpoints
- `inventory-hub/spoolman_api.py` — Spoolman DELETE calls

**Acceptance criteria:**
- [ ] Delete action exists in the details modal but requires deliberate navigation to reach
- [ ] Two-step confirmation prevents accidental deletion
- [ ] Filament deletion cascades to all child spools
- [ ] Activity log records deletions
- [ ] Deleted items are removed from all UI views immediately

### 4.4 — Clean up filament attributes
**Buglist ref:** L160
**What:** Duplicate/inconsistent filament attributes exist (e.g., "Carbon-Fiber" vs "Carbon Fiber", "X;Y" items). Requires `setup_fields.py` changes.

**Files:**
- `inventory-hub/setup_fields.py` (or equivalent field configuration)
- Document current duplicates before fixing

**Acceptance criteria:**
- [ ] Audit of all filament attribute values completed
- [ ] Duplicates consolidated (with value migration for existing records)
- [ ] No data loss during consolidation

## Testing Checklist

- [ ] Archive a filament → verify it's tracked as archived
- [ ] Create a spool under an archived filament → verify auto-unarchive
- [ ] Delete a spool via UI → verify two-step confirmation → verify deletion
- [ ] Delete a filament with child spools → verify cascade confirmation → verify all deleted
- [ ] Verify attribute cleanup didn't break any existing filament records

## Dependencies

- 4.2 is blocked by 4.1 (same group, done sequentially).
- 4.3 and 4.4 are independent of each other and of 4.1/4.2.
