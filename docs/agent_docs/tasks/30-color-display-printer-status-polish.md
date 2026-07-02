# Group 30: Color Display & Printer-Status Polish (2026-07-01 sweep)

**Branch name (when started):** `feature/group-30-color-display-printer-status`
**Estimated effort:** ~2–4 hours (three small frontend touches)
**Risk:** **LOW.** Pure frontend — a display addition, a color-input sync, and a CSS sizing tweak. No backend, no data. Verify visually against the running dev container (screenshots / the visual-regression harness where it applies).

> **Status: TODO** — filed 2026-07-01 by `/refresh-groups`. Three small new UI items from the top of the buglist (lines 5, 7, 9). Bundled as one sweep because two of them share color-handling code (hex ↔ RGB ↔ picker) and all three are quick, low-risk frontend polish — the Group 21 "new-bug sweep" shape.

## Why these are one group

30.1 and 30.2 are the same subsystem — hex/RGB/color-picker translation — just on two surfaces (the details modal's swatch display vs. the search box's color-location input). 30.3 is a standalone CSS sizing tweak on the printer-status widget, folded in as a cheap same-session polish item. Batching keeps the shared color-conversion helper consistent between 30.1 and 30.2.

## Items

### 30.1 — Show RGB alongside the hex value near color swatches (buglist line 5)
> "Places where we have the Hex value of a color (near swatch color examples in the filament/spool details modal as an example) should also display the RGB values as well."

Wherever a hex value is shown next to a swatch (start with the **filament/spool details modal**), also render the RGB triplet. **Approach:** reuse the existing hex→RGB conversion (there's already `hex_to_rgb` server-side in `labels_csv.py` and likely a JS equivalent — find/consolidate one client-side helper rather than adding a third). Audit the other swatch-display sites so the addition is consistent, not one-off. Keep it readable in dark theme (see `[[feedback_ui_dark_contrast_no_reflow]]`).

### 30.2 — Pasting a hex into the search box updates the picker + RGB + swatch live (buglist line 7)
> "Pasting a hex value into the search box (color location) should also update and translate the color picker to the currently pasted color in the field. (So the RGB should be populated, and the color example updated when that field is changed/pasted into.)"

On `input`/`paste`/`change` of the color-location field in the search UI, parse the hex, and update: (a) the color picker, (b) the RGB readout, (c) the swatch example. **Approach:** normalize/validate the hex first (3-digit expand, `#`-optional, reject garbage without clobbering) — mirror the hardening the Group 23.1 import-apply already does for `color_hex` (`inv_details.js`), reuse that path if possible. Handle paste (not just keystroke) so a pasted `#RRGGBB` triggers the sync.

### 30.3 — Printer-status toolhead panels need a little more vertical breathing room (buglist line 9)
> "Printer status tool head (larger view) panels should be a little larger … so that the lower color text isn't clipping into the bounding box of the panel … just a little more breathing room."

On the **expanded (larger-view)** printer-status toolhead panels, the lower color-name text sits right against the panel's bottom edge (worst on the XL). The unboxed-filament-with-warning case already looks right (the warning gives it room), so this is a small height/padding bump on the panel — **not** a big resize. **Approach:** tweak the panel's min-height / bottom padding in the printer-status widget CSS; keep the overall size ~the same. Re-capture the printer-status visual baseline if the change moves pixels (`UPDATE_VISUAL_BASELINES=1`) and eyeball the diff.

## Recommended order
1. **30.1 + 30.2 together** — settle on ONE client-side hex↔RGB helper first, then wire the details-modal display (30.1) and the search-box live-sync (30.2) onto it. Doing them back-to-back avoids two divergent conversion paths.
2. **30.3** last — independent CSS tweak; verify with a screenshot + a visual-baseline recapture if needed.

## Out of scope / do NOT do
- A big printer-status panel resize (30.3) — Derek was explicit: the size is generally right, it needs only "a little more breathing room." Don't reflow the whole widget.
- Adding a third hex→RGB conversion implementation — consolidate onto the existing one.
- Touching backend color storage — this is display/input only; hex stays the stored form.
