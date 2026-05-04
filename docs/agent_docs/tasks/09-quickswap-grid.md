# Group 9: Quick-Swap Grid Enhancements & Printer Status Widget

**Branch name:** `feature/quickswap-grid`
**Estimated effort:** ~4–5 hours
**Risk:** Medium — modifying an interactive grid with existing keyboard nav; new at-a-glance widget shares aggregation code

## Goal

Upgrade the Quick-Swap grid with richer spool cards, add the Printer Pool banner row for sentinel slots, and ship a new at-a-glance Printer Status widget that reuses the same aggregation surface.

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

### 9.3 — Printer Status at-a-glance widget
**Buglist ref:** L148
**What:** "Easy way to see what filaments are active on the printers at a glance, and how much filament is left in them. … I keep doing it lately to check to see if I should change spools now, or see if I can fit in one more print."

**Why it lives here:** Group 9 is already adding a `'quickswap'` `SpoolCardBuilder` variant (9.1) and per-printer aggregation logic (9.2 Printer Pool). A compact Printer Status widget falls out of those same primitives — it's a third consumer of the same per-printer toolhead aggregation, just rendered as a passive at-a-glance view rather than an interactive swap surface.

**Scope (V1, not Project Color Loadout):**
- A dashboard widget (likely top-bar or collapsible side panel) showing one row per printer
- Each row lists active toolheads with: filament name/color, remaining weight (g), and a quick visual cue when remaining is low (e.g. <100g warning)
- Source data: `_resolve_active_locs_for_printer` + FilaBridge weights via the existing live-spools refresh pulse — no new backend endpoints
- Read-only; clicking a toolhead can hand off to the existing Quick-Swap flow but no new editing affordances in V1
- Project Color Loadout integration explicitly out of scope (Loadout is blocked by Location Manager Phase 3 anyway)

**Files:**
- `inventory-hub/static/js/modules/ui_builder.js` — extend `SpoolCardBuilder` with a `'printer-status'` variant (compact, no actions)
- `inventory-hub/static/js/modules/inv_quickswap.js` — extract per-printer aggregation helper so 9.1, 9.2, and the new widget share it
- New module `inventory-hub/static/js/modules/inv_printer_status.js` — widget render + auto-refresh on `inventory:sync-pulse`
- `inventory-hub/templates/index.html` — widget mount point
- Possibly `inventory-hub/static/css/dashboard.css` — widget styling

**Acceptance criteria:**
- [ ] Widget shows every printer with at least one bound toolhead
- [ ] Each toolhead row shows filament identity + remaining weight, color-coded for low (<100g) / empty
- [ ] Auto-refreshes on the same sync-pulse cadence as the buffer
- [ ] Click on a toolhead row opens Quick-Swap focused on that printer (reusing existing flow)
- [ ] Widget is collapsible / dismissible for users who don't want it on screen
- [ ] Visual baseline captured for the Playwright snapshot suite

## Dependencies

- The sentinel validation and Location Manager UI for sentinels is already done (per L32 notes).
- 9.1's `'quickswap'` `SpoolCardBuilder` variant should land before 9.3 so the new `'printer-status'` variant can extend it; doing 9.3 standalone would mean re-doing the same `SpoolCardBuilder` plumbing twice.
- 9.3 is V1-only — Project Color Loadout integration is explicitly deferred until Location Manager Phase 3 lands.
