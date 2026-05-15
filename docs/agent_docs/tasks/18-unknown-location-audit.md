# Group 18: Unknown Location + Audit Mode Refinement

**Branch name:** `feature/unknown-location-and-audit`
**Estimated effort:** ~4–6 hours
**Risk:** Medium — adds a first-class location category (data layer touches) and revamps audit-mode semantics

## Goal

Introduce `Unknown` as a first-class location category for "spools that aren't where their tag says they are" (18.1), then refine Audit mode to use it as the default target for anything not scan-confirmed at its expected location (18.2). Includes smart-handling of virtual / parent locations (carts containing shelves) so audit doesn't insist on scanning the parent when only the leaf is the truth.

> ⚠️ **Order matters.** 18.1 is the foundation; 18.2 consumes it. Ship them on the same branch but in order — 18.2 won't have anything to point at until 18.1 lands.

## Items to Complete

### 18.1 — Add `Unknown` location as a first-class category
**Buglist ref:** L142
**What:** "Need to add an unknow location to the location list. I tried to add one manually, but it was a bit weird in how it displayed. I need a place to put spools that I just can't find, because they aren't where there location tag seays they are."

**Why standalone:** Derek already tried adding one manually. "A bit weird in how it displayed" implies the schema treats it as an unmodeled exception. First-class support means:
- A defined type (e.g. `Type: "Unknown"` in `locations.json`) so the synthesizer + grouping logic recognize it
- Rendering convention (icon, color, position in lists) — probably wants to sort first or last consistently
- Clear semantics: spools here are "physically lost" (we expected them somewhere; they're not there)

**Approach:**
- Add `Unknown` as a recognized `Type` in `locations_db.py`'s `_required_keys_for` table.
- Seed a single `LocationID: "UNKNOWN"` row with `Name: "❓ Unknown"` or similar at install / migration time (additive — don't disturb existing data).
- Update rendering in `inv_loc_mgr.js` and `inv_core.js` to give Unknown a distinct visual treatment (badge, icon, sort position).
- Update spool-card rendering so spools at `location: "UNKNOWN"` render with a clear "❓ Unknown" badge instead of treating it as just-another-location.
- Add to the Location Manager UI as a non-editable special row (you can move spools into it; you can't delete or rename the row itself).

**Files:**
- `inventory-hub/locations_db.py` — `_required_keys_for` accepts the new Type
- `inventory-hub/app.py` — migration on startup to ensure the `UNKNOWN` row exists
- `inventory-hub/static/js/modules/inv_loc_mgr.js` — render logic + non-deletable guard
- `inventory-hub/static/js/modules/inv_core.js` — location-badge styling
- `inventory-hub/static/js/modules/ui_builder.js` — `SpoolCardBuilder` location badge
- `inventory-hub/tests/test_dryer_bindings.py` (or new file) — schema acceptance test
- `inventory-hub/tests/test_locations_json_integrity.py` — integrity check covering the Unknown row

**Acceptance criteria:**
- [ ] `Unknown` type validated by `_required_keys_for`
- [ ] Startup migration seeds the `UNKNOWN` row idempotently
- [ ] Spool cards at `UNKNOWN` location show a distinct "❓ Unknown" badge
- [ ] Location Manager shows the row but blocks delete/rename
- [ ] Regression tests covering schema + migration + render

### 18.2 — Audit mode refinement
**Buglist ref:** L154
**What:** "Audit mode needs refinement possibly using the new unknow location for anything not scanned and confirmed to be in that locaiton. Also needs to be smart about virtual locations like carts where theres a cart location that contains sever shelves, as an example."

**Two distinct refinements:**

**Part A — Move unconfirmed spools to `UNKNOWN`.**
At audit end, any spool that was expected at the audited location but wasn't scan-confirmed gets moved to `UNKNOWN`. Today (pre-18.2) these spools either stay at their stale location (silently incorrect) or get force-unassigned (losing breadcrumb context). `UNKNOWN` is the correct intermediate state: "we don't know where it is, but we know it's not where the tag says."

- Plant the pre-audit location on the spool's `extra.fcc_pre_audit_location` (similar pattern to `fcc_pre_archive_location` from Group 4) so a recovery scan can restore.
- Activity Log entry per move: `❓ Audit: moved Spool #N to UNKNOWN (was expected at <loc>, not scanned)`.

**Part B — Virtual/parent location smart-handling.**
A cart location like `CR-1` may contain shelves `CR-1-S1`, `CR-1-S2`, etc. Today audit may insist on scanning the parent (`CR-1`) to confirm everything underneath, which is meaningless if the user is actually scanning the shelves. The parent's audit state should be derived from its children: parent "audited" iff every child is audited.

- Audit-mode UI: parent locations show a derived "X/Y children audited" status; scanning a child counts toward the parent's audit.
- Don't force a parent-scan if all children scanned.

**Files:**
- `inventory-hub/audit.py` (or wherever audit lives — confirm path) — end-of-audit cleanup + child-rollup logic
- `inventory-hub/static/js/modules/inv_audit.js` or equivalent — UI updates for parent-derived status
- `inventory-hub/spoolman_api.py` — `SYSTEM_MANAGED_EXTRAS` adds `fcc_pre_audit_location` (so wizard/vendor-edit can't clobber)
- `inventory-hub/setup-and-rebuild/setup_fields.py` — register the new extra
- `inventory-hub/tests/test_audit_unknown_location.py` (new) — Part A + B coverage

**Acceptance criteria:**
- [ ] Audit end moves unconfirmed spools to `UNKNOWN` with breadcrumb planted
- [ ] Activity Log entry for each move
- [ ] Parent locations show derived audit status; child-scans count toward parent
- [ ] Regression tests for both parts
- [ ] `fcc_pre_audit_location` migrated through setup_fields idempotently

## Testing Checklist

- [ ] Manual repro of "spool lost" scenario: move to Unknown, then find and force-relocate back
- [ ] Manual repro of parent-derived audit: scan all shelves in a cart, verify cart shows "complete"
- [ ] Full sweep stays green
- [ ] Activity Log entries readable and accurate

## Dependencies

- Location Manager redesign (NOT-GROUPED, IN PROGRESS) — Phase 1A `parent_id` work would make Part B's parent/child logic much cleaner. Coordinate: if Phase 1B+ lands before this group, 18.2 should use `parent_id` instead of the prefix-split approach.
- Group 4 (Archive / Cleanup) — `fcc_pre_archive_location` pattern is the template for `fcc_pre_audit_location`.
- Group 13 (Recent Bugfixes) — audit's force-relocate path may interact with the box↔toolhead bind-sync work; verify no regressions.
