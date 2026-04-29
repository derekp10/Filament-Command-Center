# Group 4: Archive / Delete / Cleanup Lifecycle

**Branch name:** `feature/archive-delete-lifecycle`
**Estimated effort:** ~3 hours
**Risk:** Medium — delete is destructive, needs careful confirmation UX

## Goal

Close out the unreachable filament-archive feature, add a symmetric spool auto-unarchive on weight refill, add delete capability with safety rails, and clean up duplicate/malformed filament attributes.

## Items to Complete

### 4.1 — Filament archive is a non-feature — remove dead code [DONE 2026-04-28]
**Buglist ref:** L3 (closed in `completed-archive.md`)
**What:** Spoolman silently drops `archived: true` on filaments and exposes no UI for filament archiving. Per Derek 2026-04-28, filament-level archiving is not a feature FCC needs (the "0 spools" use case is covered by search).

**Done:**
- [x] Removed unreachable auto-unarchive branch in `app.py:api_create_inventory_wizard`
- [x] Deleted always-skipped `test_wizard_ux_polish.py::test_create_spool_auto_unarchives_parent_filament`
- [x] Closed L3 in `Feature-Buglist.md`; close-out note in `completed-archive.md`
- [x] Reworded L18 in place to capture the spool-side recovery (4.2 below)

### 4.2 — Spool auto-unarchive on weight refill (re-scoped from L18)
**Buglist ref:** L18
**What:** When an archived spool gets a weight write that pushes `remaining_weight` back above 0 (typo recovery, mid-print weigh-out correction, etc.), automatically un-archive the spool. The 0g auto-archive in `spoolman_api._auto_archive_on_empty` already does the inverse direction — this adds the symmetric path so the user never has to bounce into Spoolman to recover.

**Design:**
- Always-on (no UI toggle) — refilling an archived spool means you want it active.
- Mirror the shape of `_auto_archive_on_empty`: a sibling `_auto_unarchive_on_refill` that mutates `data` to set `archived: False` when `remaining > 0` AND `existing.archived is True`.
- If a pre-archive location breadcrumb exists, restore it; otherwise leave at UNASSIGNED. Watch out for hard-unassign code paths that intentionally clear location — those should NOT plant a breadcrumb.
- Activity log entry mirroring the auto-archive log: `📤 Auto-unarchived Spool #N (weight refilled to Xg)`.
- Wire-up via `update_spool` so every weight-write surface (weigh-out, wizard, FilaBridge manual recovery, backfill, etc.) inherits the behavior for free.

**Files:**
- `inventory-hub/spoolman_api.py` — new `_auto_unarchive_on_refill` helper, called from `update_spool` near the existing auto-archive call.
- `inventory-hub/app.py` — surface the un-archive verdict in the wizard-edit response if useful for toasts.

**Acceptance criteria:**
- [ ] Setting `used_weight` such that `remaining > 0` on an archived spool flips `archived: false` automatically
- [ ] Activity log records the auto-unarchive
- [ ] Toast confirms via existing wizard/weigh-out response shape (no new modal needed)
- [ ] Pre-archive location breadcrumb restored when present; UNASSIGNED otherwise
- [ ] Auto-archive direction unchanged (regression test)

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

### 4.4 — Clean up filament attributes [DEFERRED 2026-04-28]
**Buglist ref:** L219 (audit results captured there)
**What:** Audit completed; deferred to a follow-up branch. Spoolman blocks per-choice removal via POST (`"Cannot remove existing choices"`), so the cleanup requires the heavy snapshot-restore migration pattern. Cost-vs-benefit favors deferring — the dead choices are unused (no broken data), just dropdown clutter.

**Status:**
- [x] Audit of all filament attribute values completed (5 confirmed dead, 1 keep, 2 needing investigation)
- [ ] Migration deferred — see updated buglist entry for confirmed-safe-to-delete list and the migration template (`migrate_container_slot_to_text`)

## Testing Checklist

- [ ] Archive a filament → verify it's tracked as archived
- [ ] Create a spool under an archived filament → verify auto-unarchive
- [ ] Delete a spool via UI → verify two-step confirmation → verify deletion
- [ ] Delete a filament with child spools → verify cascade confirmation → verify all deleted
- [ ] Verify attribute cleanup didn't break any existing filament records

## Dependencies

- 4.2 is blocked by 4.1 (same group, done sequentially).
- 4.3 and 4.4 are independent of each other and of 4.1/4.2.
