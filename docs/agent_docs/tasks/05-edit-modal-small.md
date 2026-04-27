# Group 5: Edit Filament & Details Modal — Small Additions

**Branch name:** `feature/edit-modal-small-adds`
**Estimated effort:** ~3 hours
**Risk:** Low — additive changes to existing stable modal

## Goal

Add missing data fields to the Edit Filament and Spool/Filament Details modals.

## Items to Complete

### 5.1 — Slicer profile info missing from Edit Filament modal
**Buglist ref:** L44
**What:** The Edit Filament modal doesn't show slicer profile information. Slicer profiles are created and assigned elsewhere but should be viewable/editable from the filament edit surface.

**Files:**
- `inventory-hub/static/js/modules/inv_details.js` — Edit Filament modal rendering
- `inventory-hub/templates/components/modals_details.html` — template markup
- `inventory-hub/app.py` — ensure slicer profile data is included in the filament API response

**Acceptance criteria:**
- [ ] Edit Filament modal shows associated slicer profiles
- [ ] Profiles can be added/removed from the edit modal
- [ ] Changes persist on save

### 5.2 — Add max temperatures to details modals
**Buglist ref:** L54
**What:** Details modals for spools and filaments currently show min temperatures but not max. Both should display side-by-side: min on the left, max on the right, same row, each with its own label.

**Files:**
- `inventory-hub/static/js/modules/inv_details.js` — temperature display section
- `inventory-hub/templates/components/modals_details.html` — layout markup

**Layout spec:**
```
Nozzle Temp:   190°C – 230°C
Bed Temp:       55°C – 70°C
```
Or:
```
Nozzle Min: 190°C    Nozzle Max: 230°C
Bed Min:     55°C    Bed Max:     70°C
```

**Acceptance criteria:**
- [ ] Both min and max temps displayed side-by-side for nozzle and bed
- [ ] Handles missing max gracefully (shows "—" or just the min)
- [ ] Consistent formatting across spool and filament detail views

## Testing Checklist

- [ ] Open Edit Filament modal for a filament with slicer profiles → verify they appear
- [ ] Open details modal for a filament with both min/max temps → verify layout
- [ ] Open details modal for a filament with only min temps → verify graceful handling
- [ ] Save slicer profile changes → re-open modal → verify persistence

## Dependencies

- None. These are additive features on a stable surface.
