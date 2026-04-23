# **New and Unsorted Features/Bugs**

* **[IMPORTANT]** Spoolman filament archiving is broken on the installed version — `PATCH /api/v1/filament/<id>` with `{"archived": true}` returns 200 but the flag is silently dropped; subsequent GETs never include the `archived` key on filaments (only spools). Dev and prod point at the same Spoolman. Impact: the wizard's auto-unarchive code (`inventory-hub/app.py` in `api_create_inventory_wizard`, added 2026-04-22) correctly calls `spoolman_api.update_filament(fid, {'archived': False})` whenever the parent filament looks archived — but that branch is effectively unreachable today because Spoolman never reports `archived: true` on a filament. `test_wizard_ux_polish.py::test_create_spool_auto_unarchives_parent_filament` skips on this basis. Next steps: (a) check whether Spoolman supports filament archival on a newer version and upgrade, or (b) track archive state on the filament via a custom `extra` field instead of the native flag. Related active-backlog entry: "Adding filament to an archived filament should automatically unarchive the filament" — code is in place, blocked on Spoolman support.


* Keeping the screen on when afk, still causes the screen to blank out. Confirmed on laptop, not on desktop. _[ON HOLD — OS-level power management, not fixable in app code. Candidate mitigations if we care: Wake Lock API (`navigator.wakeLock.request('screen')`) gated behind a toggle in the nav bar; only works when the tab is foreground. Worth considering if we add a kiosk/shop-floor mode.]_
* Filament Edit follow-ups (Edit Filament MVP landed 2026-04-22):
  * Backfill tool for historical spools stored with `spool_weight=0` so they adopt the parent filament/vendor value (the live inheritance resolver handles new reads, but old saved-zero values don't auto-update). _[NEEDS INPUT: should this be a one-shot admin script, a UI button on the Filament Details modal, or a batch endpoint that fires on a timer? The correct scope depends on whether we want it user-facing.]_
  * ~~Vendor and `color_hex` editing — currently the direct Edit Filament form omits these; still need the full wizard path. Consider adding them to `openEditFilamentForm` as follow-up.~~ **DONE 2026-04-23** — `openEditFilamentForm` now renders a Vendor `<select>` (loaded from `/api/vendors`) and a paired color picker + hex input. Dirty-diff handles both fields and validates hex format.
  * **Edit Filament Wave 1 expansion DONE 2026-04-23** — added Spoolman default fields (diameter, filament net weight, price, external_id/legacy ID) and multi-color picker matching the wizard's pattern (+ button adds extra rows, direction selector appears when 2+ colors, Spoolman `multi_color_hexes` CSV round-trips correctly). Covered by `test_filament_edit_button.py` (17 tests).
  * ~~**Edit Filament Wave 2**~~ **DONE 2026-04-23** — most of the gaps vs. the wizard are now closed:
    - Searchable Material input via `<input list>` + datalist populated from `/api/materials`.
    - Searchable Vendor with inline new-vendor creation: `<input list>` + hidden id, "+ NEW" badge shown when typed name doesn't match. On save, POSTs `/api/vendors` first (new endpoint, `api_create_vendor`), then PATCHes the filament with the returned id. Old flat `<select>` retired.
    - Collapsible Advanced section (`<details>`) now holds: Original Color, Filament Attributes (comma-separated → JSON array round-trip), Product URL, Purchase URL, Sheet Link, Legacy/External ID.
    - Extras merge is safe: preConfirm clones the filament's existing `extra` and only overrides the fields the user touched, so Spoolman's wholesale-replace PATCH no longer drops untouched keys (`price_total`, `sample_printed`, `flush_multiplier`, etc.).
    - 24 tests in `test_filament_edit_button.py` cover the new fields + merge behavior.
  * ~~**Edit Filament Wave 3 (DEFERRED)**~~ **PARTIALLY DONE 2026-04-23** — promoted from SweetAlert to a Bootstrap tabbed modal (`#editFilamentModal` in `modals_details.html`). Four tabs (Basic / Colors / Specs / Advanced) keep each pane short even for filaments with many colors. The modal body is scrollable, so overflow is handled at the viewport level. Covered by `test_filament_edit_button.py` (22 tests).
    - Remaining Wave 3 gaps (deferred again):
      1. External-metadata import panel (Prusament / open-filament-database).
      2. Richer `filament_attributes` UI — still a freeform comma-separated text input. A chip-picker with known attributes (Silk, Matte, Carbon Fiber, Glow, etc.) would be safer.

* ~~Ability to edit filament specific data inside Filament command center. Currently there isn't a way to directly edit a filament that's used as the basis of other spools, without opening a spool. Some sort of edit workflow for chaing data directly related to filaments.~~ **DONE** — covered by the Edit Filament MVP (2026-04-22) + vendor/color follow-up (2026-04-23).

* Config button, for configuing certain things in the system without having to edit a config file manually in a text editor. (I'm not sure what all we'd want to put here, but it'd be nice to have.) _[NEEDS INPUT — scope is unclear: minimum viable config would surface `printer_map`, Spoolman URL, filabridge URL, toast durations, and extra-field propagation pairs. Bigger version pulls in the "Make as much of Command Center user configurable as possible" item below. Want to decide: start small (3-5 fields in a modal) or design the full schema first?]_

* ~~In location manager, if an item is added to a loction that has slots, and there is a free slot, auto assign the item into that free slot. (If there are multiple free slots, fill the first empty one.)~~ **DONE 2026-04-23** — `perform_smart_move` now picks the lowest-numbered free slot for single-spool moves into Max-Spools>1 containers. Bulk moves intentionally skip the auto-pick (they'd share one slot and unseat each other). Covered by `test_auto_slot_pick.py`.

* Review and unify update logic across the program, we have to many versions of update that keep getting orphined, or cause problems later on when they aren't included in a recent design change. We need to have a discussion on how best to fix this, so I want to have an implementation plan in place to iterate off of. _[ON HOLD — requires a design-discussion session before any code changes. Candidate approach when we sit down for it: inventory every caller that writes to Spoolman spool/filament/location records, classify by "edit surface" (wizard, quick edit, scan handler, auto-unmap), define a single dirty-diff helper that every surface funnels through, then migrate one surface at a time. Same shape as the `openEditFilamentForm` dirty-diff already uses.]_

* Filabridge status light is still blinking on and of, just more eraticly now. Need to look into this further. _[ON HOLD — hardware/firmware on the filabridge device itself. Not actionable from this repo until we can instrument the device side or get a usage log with timestamps correlated to filabridge-side network events.]_


* Check why FIL:58 wasn't marked as labeled when scanned. The `label_printed` field was retired in M7 and replaced with `needs_label_print` (boolean) — barcode-scan path now updates this field at `app.py:921-922, 968-969`. The FIL:58 case specifically needs manual repro to see whether the update fires and why Activity Log was silent. Could be because FIL:58 is an old physical swatch with no prior spoolman state. _[NEEDS REPRO — scan FIL:58 fresh with browser devtools open; check Network tab for `/api/identify_scan` response and Activity Log ticker. Without the repro we can't tell whether the scan hit the FIL branch at all or silently returned `unknown`.]_


* Adding filament to an archived filament should automatically unarchive the filament.

* We either need a way to detect if MMU mode is one. Or change how M0 & M1 work for weight deductions. I did a test with a filament in both M0 and M1, and it deducted value from both I think. I'm not sure on this as I didn't mark down how much was in M1 before the test. But we shouldn't have seen any deduction from M0. Perhaps we just bind the two together, where no matter what mode M1 is alwasy either the first MMU slot or for when the mmu is disabled and the filamentjust direct feeds into the toolhead. _[NEEDS INPUT — decision between (a) querying PrusaLink/printer firmware for MMU-enabled flag per print, or (b) the "bind M0 ≡ M1-slot-0" aliasing suggestion. (b) is simpler and probably right. Before coding either, we need a controlled repro: start a non-MMU print with known weights in both M0 and M1, capture the filabridge usage-map output. The new `/api/printer_state/<id>` endpoint (shipped 2026-04-23) is the hook for reading printer-side flags if we go with (a).]_

* Sub-bug: "Display modal on Display modal" — suspect this is the filament→spool chain at [inv_details.js:304](inventory-hub/static/js/modules/inv_details.js#L304) interacting with the silent-refresh paths at lines 386/395. Needs its own reproduction trace before fixing. _[NEEDS REPRO — capture exact click sequence that triggers it; ideally video + console.trace wrapper around `openFilamentDetails` and `openSpoolDetails` to see the call stack at the double-open.]_

* An unknow issue caused the frontend to lock up, causing it to no longer update to take barcodes. A hard refresh (Control shift R and Control F5) fixed it. We need to figure out what caused this, and fix it so it doesn't happen again. This could be related to the eject button issue above. Also seemed to have cause updates to filabridge to stop until the front end was refreshed. _[NEEDS REPRO + LOGS — next occurrence: DON'T hard-refresh first. Open DevTools → Console and Network tabs, screenshot pending XHRs and any red errors, then hard-refresh. Most likely an unhandled promise rejection in the scan-handler pipeline leaving `state.processing` stuck true.]_

* It appears that while I was editing a spool's filament data that was sloted into a print head, saving caused it to be removed. We need to check to see why that is. Or the filament's location was listed the correct location, but it the location was regestring as empty 0/1 on location list modal, and nothing assigned inside the location manager modal. _[NEEDS REPRO — unclear which path caused the removal. Candidates: wizard save that writes `location=''`, a filabridge unmap kicked off by a stray update, or an overwrite that cleared `container_slot`. Next time: reproduce with Spoolman DB dump before + after + browser Network tab so we can see the exact write payload.]_

* Currently using temp (Bed, Nozzle/Toolhead) in spoolman to store the low tempratures, but I really think we need to track the high tempratures for those values. Will need to look into the code and see what we can do to fix this. Will need to add extra fields for this on the filament side, and treat them not as custom fields in the ui placement, but as actual fields. Will need to reinfource the location of those fieds in the UI as custom fields have a tendency to re-order themselves. I have a line item for hammering down the field locations so they don't move around eveythime a custom entry is added into an extra field, so we should probably include this in that as well. _[NEEDS DESIGN DISCUSSION — bundle with the "Spoolman field ordering bug" item in Modals & Wizard below. Proposed: add `nozzle_temp_high` and `bed_temp_high` extra fields, render them as first-class inputs (pinned ordering) in both the wizard and the Edit Filament form with side-by-side "min / max" pairs. The existing low-temp fields become the "min" side.]_

* Possible issues with >1kg spools and tracking weights? _[NEEDS REPRO — no known failure, just a lingering concern. Next time you work with a >1kg spool, compare the UI's remaining_weight across a print against the actual scale delta. If they match, close this out.]_


* ~~`test_manual_loc_override_e2e` — offcanvas-intercept bug fixed in M0. Currently xfailed because the Force Location modal was refactored from `<select>` to a searchable list; step 6 still drives the old select. Rewrite test against the new search+list UI.~~ **DONE 2026-04-23** — Test rewritten for the new `.swal-loc-item[data-id=""]` click pattern. Added a keyboard-path variant (ArrowDown + Enter). xfail marker removed; both tests pass green.

* FCC Main Main screen buffer cards still don't always update after several backend changes. Setting filament to 0, doesn't seem to update to unassinged or it's deployed status. _[NEEDS REPRO — the dashboard relies on `inventory:sync-pulse` and `inventory:locations-changed` events to rerender. Find one path that sets a spool's weight to 0 and see whether either event fires. The auto-archive path (`app.py`) fires them; manual-weight-zero via the wizard might not.]_





* Need to do something about the fact that if a toolhead has multiple slots assigned to it for a dryer box, that new spool assignments don't automatically take over the current toolhead's assigned spool. _[NEEDS INPUT — this conflicts with the Quick-Swap design where "slot → toolhead" bindings are explicit. Options: (a) auto-switch the toolhead's active spool to the most-recently-assigned slot whenever a new spool lands in any bound slot, (b) prompt with a Quick-Swap-style confirmation overlay, (c) leave it to the user via Quick-Swap. Decision needs your call before coding.]_

* ~~Warn if a spool reassignment to a toolhead is happening during an active print.~~ **DONE 2026-04-23** — `prusalink_api.get_printer_state()` best-effort probes `/api/v1/status` then legacy `/api/printer` for state. New `/api/printer_state/<toolhead_id>` endpoint exposes it. `doAssign` in `inv_loc_mgr.js` shows an inline confirm overlay on PRINTING/PAUSED/BUSY; `inv_quickswap.js` prepends a warning banner inside the existing confirm overlay. Fail-open on any network hiccup so a cold printer doesn't block moves. **Follow-up 2026-04-23** (after user tested and got no warning): the state probe was previously only wired into 1 of 4 `showConfirmOverlay` call sites. Moved the probe into `showConfirmOverlay` itself so every caller (quick-swap, deposit, return-to-slot, empty-return) now gets the banner automatically when the target printer reports PRINTING/PAUSED/BUSY. The probe fires async so the overlay still opens instantly — banner slots in when the response lands. Covered by `test_printer_state_api.py` and `test_active_print_warning_e2e.py`.

* If a spool isn't activly deployed to a toolhead during an update to the Filament Command Center, it looses it's current slot assignment, and has to be reassigned. (This might happen during other senerios, but this one is the first I've noticed.) _[NEEDS REPRO — "update" is ambiguous here. Which write? Probably `container_slot` is getting cleared when `update_spool` runs without merging prior extras. This class of bug has been fixed in `perform_smart_move` (the read-merge-write pattern on line 321-330 of logic.py); there may still be surfaces that write a bare `{'extra': {'container_slot': ''}}` and clobber siblings. Audit all `update_spool` callers.]_

* No way to assigne a slot to a printer without having a toolhead assigned to it. It would be nice if we could assign slots to a printer so they show up for possible easy swaping, but not actually being assigned to a toolhead. (in cases where the dryer box is basically ment for a printer, but we can't use a slot because of layout. Prusa XL and LR-MDB-1:SLOT:4 is a good example.) _[NEEDS DESIGN — today `slot_targets` values are strict toolhead LocationIDs. We'd need a new sentinel value (e.g. `"PRINTER:XL"` or a separate `slot_printer_hints` dict) that the Quick-Swap grid would render but that `perform_smart_move`'s auto-deploy would skip. Model change is small; UI change (Location Manager feeds editor dropdown grouping + Quick-Swap grid banner) is the bigger chunk.]_

# **Active Backlog (Organized by Feature Area)**

## 📋 Activity Log
* Make the Activity Log more ubiquitous so it can be the authoritative feedback channel instead of toasts. Currently the log pane sits on the dashboard only — modal-heavy workflows (Location Manager, Wizard, Details) hide it, so the toast has to carry the full message + display time for the blind-scanner case. Candidate approaches (pick one, or stack them):
    - **Persistent mini-log widget**: a small scrollable strip that survives at the bottom/corner of the screen even when modals are open. Z-index above `.modal-backdrop` so it never gets covered. Shows the last N entries with category icons.
    - **"N new events" pill** in a corner that flashes when the log ticks. Click opens a compact log overlay. Same discipline as the `?` shortcuts overlay.
    - **Modal-aware docking**: while any modal is open, a condensed log bar docks to the modal itself (top or bottom of the modal body). Hides when no entries have arrived recently.
  Once the log is always visible, toast durations can drop further and we can rely on the log for the full narrative — toasts become purely "happened now" flashes.

## 🎨 UI & Theming
* Refactor the longer "strip" cards used in the Location Manager window. Merge the horizontal layout with modern grid card features without cramping the text or making the button layout look weird.
* High-Contrast Pop (White Text/colored text + Heavy Black Shadow/or similar color shadowing) - EVERYWHERE. Adaptive High-Contrast Pop (Shadows Only) on colors. Maintain existing colors, but give them a pop appropriate for their color.
* Theres a little animation and modal that appears when you add a new Slicer Profile in the Add/edit enventory wizzard. Its so nifty I want this used in other places. (I'm not sure if this is a sweetalert2 thing, or if we implemented ourselves.)


## ⌨️ Keyboard Navigation
* Audit and implement consistent keyboard navigation across the entire UI. Currently only the force location modal and wizard material/multiselect dropdowns support arrow keys, Enter, and Escape. Every modal, dropdown, list, and interactive element should have a unified keyboard interaction pattern: arrow keys to navigate, Enter to select/confirm, Escape to dismiss/go back, Tab to move between controls, and auto-focus on the primary input when a modal opens.

## 🗂️ Modals & Add Inventory Wizard
* Help button to provide information on how to use a modal, and to try and store information about how things work in the code.
* Maintain the ability to add multiple spools of the same type at the same time.
* Create an assignment tool/system to pair existing/migrated Spoolman IDs directly to physical legacy spools being updated (specifically for bulk-imported identical spools sharing a single legacy ID).
* We now have 2 purchase links for spools, one that virtually links to the filament value, the other is on it's own but part of the spool. We need to look into the code here and pair down to only one fied if possible, but retain functionality. Linked field enharrenting the value possibly. Or we just fix the code so it looks at what is available and takes the one that exists, with a preference for the spool specific one, which may be more uptodate, or specific for the pricing. One of them, the first one on the page, seems to not clear between usanges.
* Adding a new slicer profile should automatically add that profile to the current filament being edited.
* Spoolmans field ordering bug causing fields in the Add/Edit enventory window to move if a custom field is modified or has new items added to it. Need to look at locking down the order of things.
* SweetAlert2 does not support nested modals — calling `Swal.fire()` while one is already open replaces the first one. Any future confirmation dialogs inside SweetAlert modals must use inline overlay divs (see force location modal's `#fcc-escape-confirm-overlay` pattern) instead of nested `Swal.fire()` calls. Audit existing code for any other nested Swal usage.

## 🔍 Search, Display & Filtering
* ~~Search by deployment status. Maybe under an advanced search set that is hidden but can be shown, so it doesn't take up a lot of extra space.~~ **DONE 2026-04-23** — `/api/search` accepts a new `deployed` query param ('deployed'|'undeployed'|'' or 'any'). A spool counts as deployed when its Spoolman location is in `printer_map` OR it carries a ghost `extra.physical_source` pointing at a toolhead. Filter is silently skipped for filaments. Frontend: small select dropdown added to the search offcanvas next to Min Weight. Covered by `test_search_deployed_filter.py`. **Follow-up 2026-04-23**: Reset button now also clears this filter (was leaving it stuck on deployed/undeployed after reset). _Note: we didn't hide this behind "advanced filters" since the select only adds ~140px of width; revisit if more filters accumulate._
* Search by and filter by remaining weight.



## ⚡ Quick-Swap Enhancements
* **Denser spool/filament cards inside the Quick-Swap grid**: reuse the existing `SpoolCardBuilder` system (the one that renders cards in the dashboard, Location Manager, etc.) so each bound slot shows a real filament card instead of the current custom button. That would unlock integrating more actions — Eject, Details, Edit, Print Queue — directly from the Quick-Swap view without extra trips through other modals. Needs a new card variant (e.g. `'quickswap'` mode) that omits some details to keep the grid compact while retaining the shared styling and interaction code. Reference: [inv_quickswap.js](inventory-hub/static/js/modules/inv_quickswap.js) grid render + [ui_builder.js](inventory-hub/static/js/modules/ui_builder.js) `SpoolCardBuilder.buildCard()`.

## 📍 Location Management & Scanning
* Refactor the entire location managment system from the ground up. It's currently being a bit too complicated, and I think it can be cleaned up a bit if we just rethink the flow of this process. We've bolted a lot of stuff onto this system, and the has caused it to become a bit too cumbersome to both code and work with. I think we need to build in a better system for linking locations and device/boxes/storage things. We need to have a discussion on how best to fix this, so I want to have an implementation plan in place to iterate off of. _[ON HOLD — needs design session. Large refactor, bundles with the DB-driven parent/child hierarchy item below since they'd share a schema change. When we sit down: first define the hierarchy model (ParentLocation FK vs prefix parsing), then draft a migration plan, then split the location-manager UI work into vertical slices.]_
* ~~The ability to configure a box to change the slot order to go from left to right, or right to left.~~ **DONE 2026-04-23** — per-dryer-box `extra.slot_order` ('ltr'|'rtl'), new `/api/dryer_box/<id>/slot_order` GET/PUT endpoints, radio toggle in the Location Manager feeds editor. `renderGrid` reverses iteration when rtl. Covered by `test_slot_order_api.py` + `test_slot_order_ui_e2e.py`. **Follow-up 2026-04-23**: after Save Feeds the grid now re-renders immediately in the new direction (was previously requiring a close+reopen) — busts `state.lastLocRenderHash` before calling `refreshManageView`.

* 🔄 **Bulk Moves**: The ability to scan Box A (Source) and Shelf B (Destination) and say "Move EVERYTHING from Box A to Shelf B."
* Shapeshifting QR Codes in more places (like Audit button).

* Scanning a storage location (Any, dryerbox, Cart, etc) doesn't assign all items in the buffer to that cart, it requires you to scan the location multiple times in order to assign them all to it. _[LIKELY ALREADY FIXED — `performContextAssign` at inv_cmd.js:270 and `/api/smart_move` both accept a `spools[]` list and iterate the entire buffer. See the `[ALEX FIX] Bulk Assign` comment on inv_cmd.js:272. On next occurrence, capture the Network tab's `/api/smart_move` POST payload to confirm only one spool id was sent — if so the bug is upstream of the payload construction, in the buffer state. Otherwise close this out.]_
* Location Manager not syncing status across browser instances? _[ON HOLD — requires a real-time transport (SSE / WebSocket) on the backend. Current architecture is pull-only via `/api/locations` polling. Non-trivial; revisit after mobile mode since that work will establish the multi-client baseline anyway.]_
* Refactor Locations Database to support true DB-driven Parent/Child hierarchies. Currently, location hierarchy (Room -> Box -> Slot) is handled via string prefix parsing (`LR-MDB-1` means `LR`). This breaks portable/transient containers like `PJ` or `PM` boxes when they move rooms, because moving them implies renaming them, which destroys their printed barcode (`LOC:LR-PM-1`). Need to add a `ParentLocation` column to the locations database and detach the barcode ID string from the physical hierarchy tree.

## 🎟️ Print Queue, Labels & Filament Usage
* Add ability for a scan to update the label printed/filament printed status to true/yes, Spoolman Reprint (Label).
    - Label Printed in Spoolman Spool data can be used to determine if a new Label has been printed.
    - Filaments: Spoolman Reprint field is set to Yes for items that need to have a label reprinted. Null or No mean that it already has a label with the Spoolman ID.
* It's too easy to have multiple legacy spools with no exact ID, where we could be assigning the wrong item... perhaps a pop-up when there could be more than 1 spool attached to the legacy ID, asking the user if they want to see the list of spools, or just reprint a new label.
* ~~Confirmed label print should be displayed somewhere on the card. Perhaps changing the printer icon to a checkmark for confirmed spools.~~ **DONE 2026-04-23** — `format_spool_display` now emits a normalized `needs_label_print` bool in its details dict. `SpoolCardBuilder.buildCard` renders a small green ✅ next to the 🖨️ Add-to-Queue button when the flag is explicitly `false`. Kept the 🖨️ button untouched so the "add to queue" affordance is preserved; the ✅ is purely a status indicator. Missing details stays quiet. Covered by `test_label_confirmed_indicator.py`.
* Add label print button to filament sample cards.

* Some values in Print Queue are being set to yes, most are null. What is the process for setting them to true?
* Refresh ticks seem to be clearing the print queue? that or refreshes? Search button also broke for some reason.

## 🧪 Testing
* conftest.py groundwork landed in M0 (`inventory-hub/tests/conftest.py` with page, api_base_url, snapshot, scan, seed_dryer_box, with_held_spool, require_server). Remaining work: migrate existing test files to use these shared fixtures instead of their duplicated setup sequences.

## ⚙️ App Flow, Architecture & Database
* **MOBILE** Make the entire app mobile friendly so NFC/Scanning works on phones. (Perhaps a desktop mode to utalize barcode scanners, and a mobile mode of mostly touch interface and scanning barcodes/QR codes and NFC tags). The main difference being that mobile mode won't relye on all the inlaid barcode/qr codes we currently have in the interface currently for interacting with the UI elements.
* Refactor dashboard to be more modular if possible, and reduce token size/context requirements.
* Make as much of Command Center user configurable as possible, using UI elements and a config import/export feature.
* When changes are made to Spoolman extra fields, they usually ignore sort order in the database. We need a way to restore sort order.
* Clean up filament attributes, remove/consolidate (X;Y items and similar items such as Carbon-Fiber & Carbon Fiber). Requires Setup_fields.py changes.
* Continue to support Spoolman's "Import from External" feature for filaments...
    - open-filament-database
    - Prusament spool specific data links
    - Open Print Tags (Initialize, Read, and Write)
* Maybe we should figure out a way to set up a dev version for Spoolman and filabridge.
* Change auto refresh to be a pause button instead for live activity.
* COME BACK AND ADDRESS ISSUES IN setup_fields.py (Non destructive of existing choice fields, check error codes).
* Need to add a routine to clean up the logs after a while.
* Refactoring setup code to be dynamic. On brand new installs, maintain existing code to get it started.
* Continue to support Spoolman's ability to pull data from the vendor up to filament (Empty Weight), and from Filament to Spool (price, etc.)
* Add the ability to configure which extra fields should be bound and propagated to the other type of item. (Filament <-> Spool).
* Spools might need to have a text field added to store the product data (Prusament link, etc.).
* Add background refreshing used in Location Manager, etc... to update spool text (update weight other data).
* Python server auto-reload on new code changes.


# **On Hold**
* Amazon Parser: Multi-pack spools with different colors (e.g. 4x1kg) currently calculate as a single 4000g spool instead of 4 individual 1000g spools.
* `test_amazon_parser_matching` is failing — BeautifulSoup4 is not installed in the Docker container. Parser returns empty results because the import fails silently. Blocked until `pip install beautifulsoup4` is added to the Docker image. Found during structural test fix work (4/15/2026).
* Continue to support Spoolman's "Import from External" feature... Purchase emails, or Amazon/Vendor product pages, Onlyspoolz.com.
* Standardize the size of all QR codes to match that of the sizes used on the command center. (Audit, eject, drop, etc).
* If legacy barcode has no spools attached to it, UI should warn about this, perhaps give option to add new spool?
* Spoolman ExternalID is not a visible field in Spoolman UI. Very low priority.


# **Overarching Issue**
I think we've inadvertently created 3 levels of logic/complexity here:
1. The physical, Scanning stuff and efficiently Moving it
2. A UI layer, for debugging, but should only really need to be looked at to confirm things
3. A full on interface that is easier to move spools around than having to use Spoolman's lackluster interface.
All 3 of these things are important and have value. We should table for now, and come back to once we've gotten more of the functionality in place.

## Stuff to watch ##

# ** Filabridge Error Recovery **
* Keep an eye on filabridge errors and note the type of recovery method used to fill in the missing weight data. (Fast-Fetch or RAM-Fetch) To see if Fast-Fetch (Based on a HTTP Range request of a file.) works.
* **Filabridge ↔ Spoolman reconcile utility.** Admin action (button in Config or a top-bar widget) that reads `/api/status` from filabridge and cross-checks every non-zero toolhead mapping against Spoolman's `location` field. For each mismatch, offer two choices: (a) "Trust Spoolman — unmap filabridge" (clears the stale entry) or (b) "Trust filabridge — update Spoolman" (writes the toolhead into Spoolman's `location`). Today this is fixable only via a manual Python one-liner (see `acf309c` / `efa15dd` discussion 2026-04-22). The new `_fb_spool_location()` pre-flight in `logic.py` prevents *new* desyncs, but doesn't heal ghost mappings created by earlier bugs, manual DB edits, or the retired `suppress_fb_unmap` code path — once a ghost exists, it persists until the affected spool gets moved through the fixed path.

# **New related project to be integrated **

* [Feature] Build Project Color Loadout Add-on -> (See /docs/Project-Color-Loadout/)