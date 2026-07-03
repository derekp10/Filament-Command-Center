# Group 23: Edit-Filament Import/Scrape, Product-URL & Label-Invalidation

**Branch name (when started):** `feature/edit-filament-import-label`
**Estimated effort:** ~5–8 hours (grew 2026-06-15 with the product_url cluster 23.4/23.5/23.6)
**Risk:** **LOW-MEDIUM overall, but 23.4 is the exception → MEDIUM/HIGHER.** Most of this is the frontend edit-filament flow + the external scraper, but **23.4 changes shared extras-merge semantics** (a delete-sentinel in `_merge_extras_with_existing` / `compute_dirty_extras`) used by EVERY write surface in the CLAUDE.md write-surface table — do it deliberately, not casually. 23.1/23.4 touch the filament write surface — follow the CLAUDE.md conventions (`compute_dirty_extras` + `SYSTEM_MANAGED_EXTRAS`, surface `LAST_SPOOLMAN_ERROR`). The label-reprint side (23.3) is `needs_label_print` lifecycle.

> **Status: ✅ DONE 2026-06-29** (`feature/group-23-edit-filament-import-scrape` → `dev`; commits `359e97f` + follow-up `1766573`). All 6 items + the 23.3 label-scope follow-up shipped; archived to `completed-archive.md` (2026-06-29 block). **Verified 2026-06-29** (`/refresh-groups` cleanup double-check): **82/82** Group-23 backend+E2E tests green (delete-sentinel 12, flag-spool 4, prusament-scan 32, external-import/parsers/merge/vendor-edit/sample-label 34) **+ a 6-agent adversarial source check returned `implemented`/high-confidence on all 6 items** (23.1–23.6), no over-claims.
>
> **⚠️ Open follow-ups surfaced by the verification (minor, NOT blockers — file separately in the buglist if wanted):**
> - **(a) 23.3 wizard reuse gap (real, minor):** the spool-label-flag trigger's WIZARD `edit_spool` reuse path (`inv_wizard.js:~2896-2927`) re-implements its own change-diff and **omits `original_color`** — so a Color-name-only edit made via the wizard's edit-spool path won't flag spool labels. The PRIMARY edit-filament modal (`inv_details.js`) handles `original_color` correctly. Secondary-surface partial-reuse gap.
> - **(b) test-coverage gaps (no functional shortfall):** the FE behaviors are verified by code-read but not pinned by tests — 23.1 apply-map landing (color_hex synthetic-input + URLs, the 3-digit-expand + bad-hex toast), 23.2 anti-leak-on-reopen, 23.5 the `📄 product` chip, 23.6 the canonical-URL write + idempotent skip. The 23.4 delete-sentinel + 23.3 endpoint backend invariants ARE test-pinned (16 cases).
>
> _Original filing:_ filed 2026-06-13 by `/refresh-groups` (23.1–23.3); **grew to 6 on 2026-06-15** with the product_url cluster (23.4 won't-save-blank, 23.5 link badge, 23.6 scan-persists-product_url), each grounded against real code by a 7-agent triage workflow. All cluster on the Edit-Filament modal + the `product_url`/link family + the **label-validity** concern.

## Why these are one group

23.1 and 23.2 are the **same Import-from-External flow** in [inv_details.js](../../../inventory-hub/static/js/modules/inv_details.js) (the `editfilExternal*` family, ~3231–3375) + [external_parsers.py](../../../inventory-hub/external_parsers.py): one is a missing field on apply, the other is stale state between uses. 23.3 is the label-side sibling — when that same edit changes label-bearing data (hex/RGB), the printed label is now wrong and should prompt a reprint. **23.4/23.5/23.6 (added 2026-06-15) are the `product_url`/link family** that rides the same surfaces: 23.4 is the save-side counterpart to 23.1 (both about a URL round-tripping through the filament write path), 23.5 is a small wizard link-badge sibling, 23.6 is the Prusament-scan persist of `product_url`. All six live in the edit-filament / product-link surface.

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

### 23.4 — Blanking a product_url (or ANY edit-filament extra) won't save (buglist 2026-06-15, item B) — ⚠️ higher-risk
**Buglist:** "Product URL modifications on filament edit window do not save. Won't save BLANK, but a url-ish value (`//test`) clears it. Make sure ALL fields can be blanked out and save appropriately."
**Grounded root cause (NOT frontend):** the FE already does the right thing — when `product_url===''`, `inv_details.js:2114` sets `dirtyExtras.product_url=''` and the merge loop at `2253-2254` `delete`s the key so it's OMITTED from the submitted `extra`. The block is **backend**: `/api/update_filament` → `spoolman_api.update_filament` re-runs `_merge_extras_with_existing(existing, caller)` ([spoolman_api.py:471-473](../../../inventory-hub/spoolman_api.py#L471)), which starts from ALL existing extras and only overlays keys the caller SENT — an omitted key is treated as "unchanged", so the old value survives. A deletion can never propagate → blanking is a no-op. The `//test` clears because a non-empty value IS in the payload. Affects **every** edit-filament extra (purchase_url, sheet_link, original_color, nozzle/bed max), matching "make ALL fields blankable."
**Fix:** introduce an explicit delete sentinel — send the key with `null` (or `""`) and have `_merge_extras_with_existing` / `compute_dirty_extras` honor an explicit null/empty as a DELETE (vs an omitted key = keep). **⚠️ This changes shared write-surface semantics** (the omit-means-keep guard exists to stop partial PATCHes wiping siblings — the 252/253/157 prod incident), so review against the full CLAUDE.md write-surface inventory. **Open scope Q (Derek):** do this narrowly (edit-filament extras only) or as a general write-surface capability? — that sets the risk/effort.
**Surface:** `spoolman_api.py:461-502` (`_merge_extras_with_existing` + `update_filament`) + `compute_dirty_extras`; `app.py:2196-2235` (`/api/update_filament`); FE already correct at `inv_details.js:2248-2260`.

### 23.5 — Product-link "filled" badge in the wizard metadata panel (buglist 2026-06-15, item G) — trivial
**Buglist:** "Pricing/metadata should note that a product link AND a purchase link are added. Currently only works for purchase links — do the same for product links (same style, matching icon)."
**Grounded:** the wizard's `wiz-spool-metadata-panel` collapsible-summary builder ([inv_wizard.js:356-367](../../../inventory-hub/static/js/modules/inv_wizard.js#L356)) reads ONLY `wiz-spool-purchase_url` (line 360) and emits one `🔗 link` badge — no read of `wiz-spool-product_url` (the input exists, populated at `:643-644` + saved at `:2630-2634`). The detail-modal buttons already cover both (`detail-btn-product-url` inv_details.js:213 / `detail-btn-buy-more` :234) — only the wizard summary indicator is purchase-only.
**Fix:** add a parallel `product_url` read + a matching-style badge (distinct icon) in that builder. ~15 min.

### 23.6 — Prusament scan should persist the scanned URL to the matched spool's product_url (buglist 2026-06-15, item J)
**Buglist:** "Using a URL to get spool data should save the url to the product link section (for Prusament, if it doesn't already exist) on an EXISTING spool."
**Grounded:** `_handle_prusament_url_scan` ([app.py:2473-2649](../../../inventory-hub/app.py#L2473)) backfills temps + per-spool metadata + a confirm-gated weight diff, but **never writes the scanned `url` into the matched spool's `extra.product_url`**. Structural chicken-and-egg: the matcher (`app.py:2522`) only finds a spool whose stored `product_url` ALREADY contains the scanned hash/id — so the highest-value cases are (a) a **legacy/hash-less** scan matched on the bare product-id needle (`app.py:2519`) where the stored URL is the short id form, and (b) any matched spool whose `product_url` is present-but-thin — neither gets upgraded to the freshly-scanned canonical URL.
**Fix:** persist/UPGRADE the canonical scanned URL onto the matched spool via `update_spool` (CLAUDE.md write-surface conventions). Frame as "save/upgrade", not just "if absent."
**Surface:** `app.py:2473-2649` (`_handle_prusament_url_scan`); `spoolman_api.update_spool`.

## Recommended order
1. **23.2** (cleanest — a state reset; prevents the wrong-link data-corruption risk).
2. **23.1** (hex overwrite + product_url scrape audit — same flow, builds on 23.2's reset). Note: the import preview maps at `inv_details.js:3193-3220` currently OMIT `product_url`/`purchase_url` entirely — 23.1 should add them so import → form → save round-trips (pairs with 23.4).
3. **23.5** (trivial wizard product-link badge — quick win, no backend).
4. **23.6** (Prusament-scan persists/upgrades product_url — small `update_spool` write).
5. **23.4** (the delete-sentinel — **do this deliberately + reviewed**; it's the riskiest and unblocks "blank any field"; decide narrow-vs-general scope first).
6. **23.3** (label-invalidation prompt — needs the "label-bearing field set" decision first; do after 23.1 so the hex-change path is the first trigger).

## Out of scope / do NOT do
- Raw PATCH of filament extras — route through `update_filament` / `compute_dirty_extras` per CLAUDE.md (sibling-wipe hazard).
- Auto-reprinting without user confirmation (23.3 is a *prompt*, not an automatic queue).
