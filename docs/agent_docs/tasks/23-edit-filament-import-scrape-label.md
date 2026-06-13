# Group 23: Edit-Filament Import/Scrape & Label-Invalidation

**Branch name (when started):** `feature/edit-filament-import-label`
**Estimated effort:** ~3–5 hours
**Risk:** **LOW-MEDIUM.** Frontend edit-filament flow + the external scraper. 23.1 touches a Spoolman write surface (filament update) — follow the CLAUDE.md write-surface conventions (`compute_dirty_extras` + `SYSTEM_MANAGED_EXTRAS`, surface `LAST_SPOOLMAN_ERROR`). The label-reprint side (23.3) is `needs_label_print` lifecycle, already a known field.

> **Status: TODO** — filed 2026-06-13 by `/refresh-groups`. Three bugs that cluster on the Edit-Filament modal's **Import-from-External** flow + the **label-validity** concern. Surfaced while Derek used a Prusa link to update filament data.

## Why these three are one group

23.1 and 23.2 are the **same Import-from-External flow** in [inv_details.js](../../../inventory-hub/static/js/modules/inv_details.js) (the `editfilExternal*` family, ~3231–3375) + [external_parsers.py](../../../inventory-hub/external_parsers.py): one is a missing field on apply, the other is stale state between uses. 23.3 is the label-side sibling — when that same edit changes label-bearing data (hex/RGB), the printed label is now wrong and should prompt a reprint. All three live in the edit-filament surface.

## Items

### 23.1 — Missing hex overwrite on apply + product_url not scraped (buglist line 17)
**Buglist:** line 17. Two parts:
- **Hex not overwritten** — applying an Import-from-External result to a filament doesn't overwrite the hex/RGB (found using a Prusa link to update data). `editfilExternalApplySelected` ([inv_details.js:3375](../../../inventory-hub/static/js/modules/inv_details.js#L3375)) should include the scraped color in the applied fields.
- **product_url not captured while scraping** — the scraper doesn't appear to grab the page's available `product_url`. Audit the scrape so we capture **everything available regardless of where we scrape** (Edit Filament, Add/Edit wizard, etc.) — check `external_parsers.py` per-source parsers return `product_url`, and that all apply paths persist it.
**Surface:** `editfilExternalApplySelected` / `editfilExternalRenderPreview` (inv_details.js) + `external_parsers.py` per-source field extraction.

### 23.2 — Import-from-External link does NOT reset between uses (buglist line 15)
**Buglist:** line 15. The external-link input in Edit Filament keeps its previous value after the user finishes, so the next filament edit could **accidentally apply the wrong product link to the wrong filament**. Reset the import search/link field (and any stashed editing-target — see the "Group 6.1 stash" comment at [inv_details.js:1359](../../../inventory-hub/static/js/modules/inv_details.js#L1359)) when the edit-filament modal opens/closes, so each edit starts clean.
**Surface:** the `editfilExternal*` state + the editing-target stash; reset on modal open (mirror the wizard's `wizardReset()` discipline).

### 23.3 — Surface label invalidation + push a reprint when label-bearing data changes (buglist line 11)
**Buglist:** line 11. If we update a filament's data in a way that invalidates the printed label (hex/RGB the most obvious — the swatch color), we should **surface that** and give the user a path to **reprint the label + replace it on the existing sample**. Natural mechanism: when an edit changes a label-bearing field, set/raise `needs_label_print` and prompt (toast + an inline "reprint" affordance, or queue the label). **Open scope-time Q:** which fields count as "label-bearing" (hex/RGB for sure; brand/material/name?) — define the set explicitly. Ties into the existing label-confirm + `needs_label_print` lifecycle (Group 3 / 17 / the sample-status work).
**Surface:** edit-filament save path + `needs_label_print` + the label queue.

## Recommended order
1. **23.2** (cleanest — a state reset; prevents the wrong-link data-corruption risk).
2. **23.1** (hex overwrite + product_url scrape audit — same flow, builds on 23.2's reset).
3. **23.3** (label-invalidation prompt — needs the "label-bearing field set" decision first; do after 23.1 so the hex-change path is the first trigger).

## Out of scope / do NOT do
- Raw PATCH of filament extras — route through `update_filament` / `compute_dirty_extras` per CLAUDE.md (sibling-wipe hazard).
- Auto-reprinting without user confirmation (23.3 is a *prompt*, not an automatic queue).
