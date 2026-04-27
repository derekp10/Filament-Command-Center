# Group 11: External Parsers & Prusament Cleanup

**Branch name:** `feature/external-parsers-cleanup`
**Estimated effort:** ~3 hours
**Risk:** Low-Medium — parser code is isolated, but merge-duplicates touches data

## Goal

Audit the external parser ecosystem, fix/deprecate broken parsers, and build a UI for merging duplicate filaments.

## Items to Complete

### 11.1 — Audit wizard's "Import from External" panel
**Buglist ref:** L70
**What:** The user has "completely forgotten what parsers we have set up there that work." Need a documentation and deprecation pass.

**Files:**
- `inventory-hub/external_parsers.py` — PrusamentParser, AmazonParser, SpoolmanParser, possibly others
- `inventory-hub/templates/components/modals_wizard.html` — dropdown wiring

**Known state (per L70):**
- Prusament: Works (confirmed via per-spool scan flow)
- Amazon: Needs BeautifulSoup4 which isn't installed in dev Docker image
- 3DFP / Spoolman-native: Needs re-testing

**Acceptance criteria:**
- [ ] Each parser tested and documented (works / broken / deprecated)
- [ ] Broken parsers either fixed or removed from the dropdown
- [ ] Working parsers have a brief doc comment explaining expected URL format
- [ ] Dropdown only shows parsers that actually work

### 11.2 — Merge duplicate filaments UI
**Buglist ref:** L68
**What:** Duplicate prevention is in (tier-1 product-id matcher + duplicate-picker UI). What's missing: a way to merge *existing* duplicates — re-point all spools from one filament to another and archive/delete the source.

**Design:**
- Accessible from the Details modal or a dedicated admin action
- Select source filament (the duplicate to remove) and target filament (the one to keep)
- Preview: "N spools will be moved from Source → Target"
- Confirm → re-parent spools → archive/delete source filament
- Activity log records the merge

**Files:**
- `inventory-hub/static/js/modules/inv_details.js` — merge action entry point
- `inventory-hub/app.py` — merge endpoint
- `inventory-hub/spoolman_api.py` — bulk spool re-parenting

**Acceptance criteria:**
- [ ] Merge UI accessible from filament details
- [ ] Shows preview of affected spools
- [ ] Re-parents all spools from source to target
- [ ] Source filament archived or deleted after merge
- [ ] Activity log records the merge with both filament IDs

### 11.3 — Continue supporting external import sources
**Buglist ref:** L161–163
**What:** Ongoing support for open-filament-database, Prusament spool-specific data links, and Open Print Tags.

**Scope for this session:** Verify existing support, document gaps, and create stubs for missing parsers. Full implementation of new parsers is out of scope.

**Acceptance criteria:**
- [ ] Document which external sources are supported and at what level
- [ ] Identify gaps for future work
- [ ] Any quick fixes for partially-working parsers

## Dependencies

- If Group 6 (Edit Modal import panel) is planned, doing this audit first tells you which parsers to wire into that panel.
