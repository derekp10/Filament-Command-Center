# Group 2: Buffer Cards & Main-Menu Refresh

**Branch name:** `feature/buffer-cards-refresh`
**Estimated effort:** ~1.5–2 hours
**Risk:** Low — mostly event plumbing and CSS fixes

## Goal

Ensure buffer/spool cards on the main dashboard always reflect the latest backend state, and fix the visual overlap bug on smaller screens.

## Items to Complete

### 2.1 — Buffer cards don't always update after backend changes
**Buglist ref:** L24 (Partial)
**What:** Setting a spool's weight to 0 doesn't reliably update the card's status on the main dashboard (deployed vs unassigned). The regression guards added in `test_weight_setting_dispatches_events.py` confirm dispatch exists, but the UI re-render may not be picking up the new state.

**Files to audit:**
- `inventory-hub/static/js/modules/inv_core.js` — event listeners for `inventory:buffer-updated`, `inventory:sync-pulse`, poll loop
- `inventory-hub/static/js/modules/ui_builder.js` — `SpoolCardBuilder.buildCard()` — does it re-read the latest data or use stale state?

**Remaining work per L24 note:** Backend-only writes (filabridge auto-deduct, server-side auto-archive) rely on polling. If lag is specifically from those paths, consider a manual-refresh button. For now, verify the polling loop propagates within one interval.

**Acceptance criteria:**
- [ ] Setting weight to 0 updates the buffer card within one poll tick
- [ ] Archive status change updates the buffer card
- [ ] No stale card state after wizard save, weigh-out, or force-location override

### 2.2 — Location updates not propagating to buffer cards
**Buglist ref:** L40
**What:** When a spool's location changes (via scan, Location Manager, or Quick-Swap), the buffer cards on the main menu don't reflect the new location. Possibly related to archive status not updating.

**Root cause:** Likely the same event dispatch pipeline as 2.1 — the card rebuild isn't triggered or isn't reading fresh location data.

**Acceptance criteria:**
- [ ] Moving a spool to a new location updates its buffer card immediately (or within one poll tick)
- [ ] Card shows correct location badge after assignment

### 2.3 — Weight QR code blocked by search badge on smaller screens
**Buglist ref:** L36
**What:** On certain smaller or Windows-scaled screens, the weight QR code on the main menu is partially or fully blocked by the search badge in the lower-right corner.

**Fix:** CSS z-index and/or responsive position adjustment.

**Files:**
- Dashboard CSS (likely `inventory-hub/static/css/` or inline in `index.html`)
- Check for `position: fixed` or `position: absolute` on both elements

**Acceptance criteria:**
- [ ] Weight QR code is fully visible and scannable at 100%, 125%, and 150% Windows scaling
- [ ] Search badge doesn't overlap any interactive elements at those scales

## Testing Checklist

- [ ] Scan a spool into the buffer → verify card appears
- [ ] Change spool location via Location Manager → verify buffer card updates
- [ ] Set weight to 0 via weigh-out → verify card status changes
- [ ] Resize browser to small viewport → verify QR code not obscured
- [ ] Run: `test_weight_setting_dispatches_events.py`

## Dependencies

- None, but if Group 1 (Weight Unification) is done first, the weight-related card updates will use the unified path.
