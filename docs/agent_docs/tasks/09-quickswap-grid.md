# Group 9: Quick-Swap Grid Enhancements

**Branch name:** `feature/quickswap-grid`
**Estimated effort:** ~2–3 hours
**Risk:** Medium — modifying an interactive grid with existing keyboard nav

## Goal

Upgrade the Quick-Swap grid with richer spool cards and add the Printer Pool banner row for sentinel slots.

## Items to Complete

### 9.1 — Denser spool/filament cards in Quick-Swap grid
**Buglist ref:** L105
**What:** Reuse `SpoolCardBuilder` system so each bound slot shows a real filament card instead of the current custom button. Needs a new card variant (e.g., `'quickswap'` mode) that omits some details for compactness.

**Files:**
- `inventory-hub/static/js/modules/inv_quickswap.js` — grid render
- `inventory-hub/static/js/modules/ui_builder.js` — `SpoolCardBuilder.buildCard()`, add `'quickswap'` variant

**Acceptance criteria:**
- [ ] Quick-Swap slots render using `SpoolCardBuilder` cards
- [ ] New `'quickswap'` variant is compact (no full details, just key info)
- [ ] Actions (Eject, Details, Edit, Print Queue) accessible from card
- [ ] Keyboard navigation still works on the new cards

### 9.2 — Printer Pool banner row for sentinel slots
**Buglist ref:** L32 (sub-item 3)
**What:** `slot_targets` now accepts `PRINTER:<id>` sentinel values. These round-trip correctly but don't surface in the Quick-Swap grid yet. Add a "Printer Pool" row.

**Design:**
- In the printer-aggregation view, add a "Printer Pool" row listing every (box, slot) whose target === `PRINTER:<thisPrinter>`
- Tap/Enter hands off to the existing deposit flow (no toolhead to swap)
- Distinct visual treatment from toolhead rows

**Files:**
- `inventory-hub/static/js/modules/inv_quickswap.js` — `resolvePrinterNameForPrinterLoc`, grid rendering
- `inventory-hub/locations_db.py` — `is_printer_sentinel()` helper already exists

**Acceptance criteria:**
- [ ] Printer Pool row appears in Quick-Swap grid for printers with sentinel slots
- [ ] Row lists all sentinel-targeted slots with their current spool info
- [ ] Tap/Enter on a pool slot triggers the deposit flow
- [ ] Visual distinction from toolhead rows (different banner color/icon)

## Dependencies

- The sentinel validation and Location Manager UI for sentinels is already done (per L32 notes). This is purely the Quick-Swap grid rendering.
