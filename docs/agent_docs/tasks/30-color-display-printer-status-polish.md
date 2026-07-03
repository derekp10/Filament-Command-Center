# Group 30: Color Display & Printer-Status Polish (2026-07-01 sweep)

**Branch name (when started):** `feature/group-30-color-display-printer-status`
**Estimated effort:** ~3–5 hours (four small frontend touches)
**Risk:** **LOW.** Mostly frontend — a display addition, a color-input sync, a CSS sizing tweak, and one printer-status text add (a small pulse-payload field if the material isn't already surfaced). No data migration. Verify visually against the running dev container (screenshots / the visual-regression harness where it applies).

> **Status: TODO** — filed 2026-07-01 by `/refresh-groups`; **30.4 added 2026-07-03** (`/refresh-groups`). Four small new UI items from the buglist (lines 5, 7, 9 + Derek's 2026-07-03 print-status material-type ask). Bundled as one sweep because two share color-handling code (hex ↔ RGB ↔ picker) and two touch the printer-status widget — all quick, low-risk frontend polish (the Group 21 "new-bug sweep" shape).

## Why these are one group

30.1 and 30.2 are the same subsystem — hex/RGB/color-picker translation — just on two surfaces (the details modal's swatch display vs. the search box's color-location input). 30.3 and 30.4 are both printer-status-widget polish (panel breathing room + a material-type line), folded in as cheap same-session touches. Batching keeps the shared color-conversion helper consistent between 30.1/30.2 and the two printer-status tweaks in the same file.

## Items

### 30.1 — Show RGB alongside the hex value near color swatches (buglist line 5)
> "Places where we have the Hex value of a color (near swatch color examples in the filament/spool details modal as an example) should also display the RGB values as well."

Wherever a hex value is shown next to a swatch (start with the **filament/spool details modal**), also render the RGB triplet. **Approach:** reuse the existing hex→RGB conversion (there's already `hex_to_rgb` server-side in `labels_csv.py` and likely a JS equivalent — find/consolidate one client-side helper rather than adding a third). Audit the other swatch-display sites so the addition is consistent, not one-off. Keep it readable in dark theme (see `[[feedback_ui_dark_contrast_no_reflow]]`).

### 30.2 — Pasting a hex into the search box updates the picker + RGB + swatch live (buglist line 7)
> "Pasting a hex value into the search box (color location) should also update and translate the color picker to the currently pasted color in the field. (So the RGB should be populated, and the color example updated when that field is changed/pasted into.)"

On `input`/`paste`/`change` of the color-location field in the search UI, parse the hex, and update: (a) the color picker, (b) the RGB readout, (c) the swatch example. **Approach:** normalize/validate the hex first (3-digit expand, `#`-optional, reject garbage without clobbering) — mirror the hardening the Group 23.1 import-apply already does for `color_hex` (`inv_details.js`), reuse that path if possible. Handle paste (not just keystroke) so a pasted `#RRGGBB` triggers the sync.

### 30.3 — Printer-status toolhead panels need a little more vertical breathing room (buglist line 9)
> "Printer status tool head (larger view) panels should be a little larger … so that the lower color text isn't clipping into the bounding box of the panel … just a little more breathing room."

On the **expanded (larger-view)** printer-status toolhead panels, the lower color-name text sits right against the panel's bottom edge (worst on the XL). The unboxed-filament-with-warning case already looks right (the warning gives it room), so this is a small height/padding bump on the panel — **not** a big resize. **Approach:** tweak the panel's min-height / bottom padding in the printer-status widget CSS; keep the overall size ~the same. Re-capture the printer-status visual baseline if the change moves pixels (`UPDATE_VISUAL_BASELINES=1`) and eyeball the diff. **Do this together with 30.4** — adding a material-type line (30.4) needs the extra room this creates.

### 30.4 — Show material type on the expanded print-status panel (buglist, 2026-07-03)
> Derek: "Expanded print status, might be nice to have the material type on there so that you can see without having to open the filament details."

On the expanded printer-status toolhead panel, show the loaded filament's MATERIAL/type (e.g. "PETG") alongside the brand/color already rendered, so the material is visible without opening the filament-details modal. **Approach:** the printer-status pulse (`_pulse_section_printer_status` → `get_spools_at_location_detailed`) already resolves the loaded item per toolhead — check whether `material` / `filament.material` is in the payload; if so it's a pure `inv_printer_status.js` render add; if not, surface it on the pulse `item` dict (and add it to the widget dedup fingerprint so it repaints). Pairs tightly with 30.3 (same expanded panel — the added text is exactly what needs 30.3's breathing room). Re-capture the printer-status visual baseline if it moves pixels.

## Recommended order
1. **30.1 + 30.2 together** — settle on ONE client-side hex↔RGB helper first, then wire the details-modal display (30.1) and the search-box live-sync (30.2) onto it. Doing them back-to-back avoids two divergent conversion paths.
2. **30.3 + 30.4 together** — same expanded printer-status panel: add the material-type line (30.4) and give the panel the breathing room (30.3) in one pass, then recapture the visual baseline once.

## Out of scope / do NOT do
- A big printer-status panel resize (30.3) — Derek was explicit: the size is generally right, it needs only "a little more breathing room." Don't reflow the whole widget.
- Adding a third hex→RGB conversion implementation — consolidate onto the existing one.
- Touching backend color storage — this is display/input only; hex stays the stored form.
