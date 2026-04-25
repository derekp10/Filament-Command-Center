# **New and Unsorted Features/Bugs**

* **[IMPORTANT]** Spoolman filament archiving is broken on the installed version — `PATCH /api/v1/filament/<id>` with `{"archived": true}` returns 200 but the flag is silently dropped; subsequent GETs never include the `archived` key on filaments (only spools). Dev and prod point at the same Spoolman. Impact: the wizard's auto-unarchive code (`inventory-hub/app.py` in `api_create_inventory_wizard`, added 2026-04-22) correctly calls `spoolman_api.update_filament(fid, {'archived': False})` whenever the parent filament looks archived — but that branch is effectively unreachable today because Spoolman never reports `archived: true` on a filament. `test_wizard_ux_polish.py::test_create_spool_auto_unarchives_parent_filament` skips on this basis. Next steps: (a) check whether Spoolman supports filament archival on a newer version and upgrade, or (b) track archive state on the filament via a custom `extra` field instead of the native flag. Related active-backlog entry: "Adding filament to an archived filament should automatically unarchive the filament" — code is in place, blocked on Spoolman support.


* Keeping the screen on when afk, still causes the screen to blank out. Confirmed on laptop, not on desktop. _[ON HOLD — OS-level power management, not fixable in app code. Candidate mitigations if we care: Wake Lock API (`navigator.wakeLock.request('screen')`) gated behind a toggle in the nav bar; only works when the tab is foreground. Worth considering if we add a kiosk/shop-floor mode.]_
* Filament Edit follow-ups (Edit Filament Waves 0–8 shipped 2026-04-22 / 2026-04-23):
  * External-metadata import panel for the Edit Filament modal — Prusament spool-specific data links and open-filament-database lookup, parity with the wizard's "Import from External" button. **Decision: Build a slim single-URL quick-paste panel as a new dedicated section in the Edit Filament modal** (not inside Advanced — it deserves its own section so parsed results can be reviewed before applying). Reuse as much of the wizard's existing importer/parser code as possible on both the backend parse path and the result-display layer. The new section should show a preview of what the parser found, with field-by-field confirmation before writing.

* Config button, for configuing certain things in the system without having to edit a config file manually in a text editor. **Decision: Full-schema design first.** The architecture must be extensible so adding new configurable items "just works" without code changes to the config UI itself. The schema should be self-describing (key, label, type, default, section, validation rules) so the UI can render any new entry automatically. This will pull in the "Make as much of Command Center user configurable as possible" item. When we sit down for design: define the schema format, config storage (JSON file vs. DB table), import/export format, and a section hierarchy. _[NEEDS DESIGN SESSION — schedule a dedicated design discussion before any code starts.]_

* Review and unify update logic across the program, we have to many versions of update that keep getting orphined, or cause problems later on when they aren't included in a recent design change. We need to have a discussion on how best to fix this, so I want to have an implementation plan in place to iterate off of. _[ON HOLD — requires a design-discussion session before any code changes. Candidate approach when we sit down for it: inventory every caller that writes to Spoolman spool/filament/location records, classify by "edit surface" (wizard, quick edit, scan handler, auto-unmap), define a single dirty-diff helper that every surface funnels through, then migrate one surface at a time. Same shape as the `openEditFilamentForm` dirty-diff already uses.]_

* Filabridge status light is still blinking on and of, just more eraticly now. Need to look into this further. _[ON HOLD — hardware/firmware on the filabridge device itself. Not actionable from this repo until we can instrument the device side or get a usage log with timestamps correlated to filabridge-side network events.]_


* Check why FIL:58 wasn't marked as labeled when scanned. The `label_printed` field was retired in M7 and replaced with `needs_label_print` (boolean) — barcode-scan path now updates this field at `app.py:921-922, 968-969`. The FIL:58 case specifically needs manual repro to see whether the update fires and why Activity Log was silent. Could be because FIL:58 is an old physical swatch with no prior spoolman state. _[ON HOLD — need to locate or reprint the FIL:58 physical label/swatch before repro can be attempted. When found: scan with DevTools open → Network tab → `/api/identify_scan` response + Activity Log ticker.]_


* Adding filament to an archived filament should automatically unarchive the filament.

* Sub-bug: "Display modal on Display modal" — suspect this is the filament→spool chain at [inv_details.js:304](inventory-hub/static/js/modules/inv_details.js#L304) interacting with the silent-refresh paths at lines 386/395. Needs its own reproduction trace before fixing. _[NEEDS REPRO — exact trigger scenario is not currently remembered. When encountered again: capture exact click sequence; ideally console.trace wrapper around `openFilamentDetails` and `openSpoolDetails` to see the call stack at the double-open. Video would also help.]_

* An unknow issue caused the frontend to lock up, causing it to no longer update to take barcodes. A hard refresh (Control shift R and Control F5) fixed it. We need to figure out what caused this, and fix it so it doesn't happen again. This could be related to the eject button issue above. Also seemed to have cause updates to filabridge to stop until the front end was refreshed. _[ON HOLD — has not recurred recently. If it does: DON'T hard-refresh first. Open DevTools → Console and Network tabs, screenshot pending XHRs and any red errors, then refresh. Most likely an unhandled promise rejection leaving `state.processing` stuck true.]_

* It appears that while I was editing a spool's filament data that was sloted into a print head, saving caused it to be removed. We need to check to see why that is. Or the filament's location was listed the correct location, but it the location was regestring as empty 0/1 on location list modal, and nothing assigned inside the location manager modal. _[COLLABORATIVE REPRO NEEDED — will work through this together with step-by-step guidance. Steps when ready: (1) Take a Spoolman DB dump before editing, (2) Edit a spool that is actively slotted into a toolhead via the wizard, (3) Save, (4) Take a DB dump after, (5) Capture the Network tab POST payload during save. Candidates: wizard save clobbering `container_slot`, filabridge unmap triggered by a stray update, or `extra` field overwrite missing read-merge-write pattern.]_

* FCC Main Main screen buffer cards still don't always update after several backend changes. Setting filament to 0, doesn't seem to update to unassinged or it's deployed status. _[PARTIAL 2026-04-23 — regression guards added in `test_weight_setting_dispatches_events.py`: seven static asserts that each interactive weight-setting path (wizard save, weigh-out, force-location override, quick-swap, smart_move buffer assign, buffer-updated, poll loop) still contains its dispatch, plus one E2E spy that confirms `inventory:buffer-updated` / `inventory:sync-pulse` actually fires after a live scan. **Remaining work:** backend-only writes (filabridge auto-deduct, server-side auto-archive) currently rely on the `inv_core.js` polling loop — no synchronous UI refresh. If the user reports the lag is specifically from those paths, add a server-side push channel (SSE / WS) or a manual-refresh button. For now the polling loop fires sync-pulse on every tick, so a 0-weight save should visibly propagate within one poll interval.]_





* Need to do something about the fact that if a toolhead has multiple slots assigned to it for a dryer box, that new spool assignments don't automatically take over the current toolhead's assigned spool. **Decision: (c) Leave it to the user via Quick-Swap.** Intent is ambiguous — a new spool landing in a shared box may not mean the user wants to switch the active toolhead assignment (e.g., staging spools for later). Quick-Swap is the deliberate, explicit action for swapping. No auto-switch or auto-prompt. _[RESOLVED — no code change needed.]_

* If a spool isn't activly deployed to a toolhead during an update to the Filament Command Center, it looses it's current slot assignment, and has to be reassigned. (This might happen during other senerios, but this one is the first I've noticed.) _[NEEDS REPRO — "update" is ambiguous here. Which write? Probably `container_slot` is getting cleared when `update_spool` runs without merging prior extras. This class of bug has been fixed in `perform_smart_move` (the read-merge-write pattern on line 321-330 of logic.py); there may still be surfaces that write a bare `{'extra': {'container_slot': ''}}` and clobber siblings. Audit all `update_spool` callers.]_

* No way to assigne a slot to a printer without having a toolhead assigned to it. It would be nice if we could assign slots to a printer so they show up for possible easy swaping, but not actually being assigned to a toolhead. (in cases where the dryer box is basically ment for a printer, but we can't use a slot because of layout. Prusa XL and LR-MDB-1:SLOT:4 is a good example.) **Decision: Sentinel value approach** — `slot_targets` will accept a `"PRINTER:<id>"` value (e.g. `"PRINTER:XL"`) in addition to strict toolhead LocationIDs. The Quick-Swap grid renders these as printer-affiliated slots (with a distinct visual treatment), but `perform_smart_move`'s auto-deploy logic skips sentinel-valued targets so no toolhead assignment is made. Changes needed: ~~(1) `slot_targets` validation to allow the new prefix~~ _[DONE 2026-04-23 — `validate_slot_targets` + `is_printer_sentinel` in `locations_db.py`]_, ~~(2) Location Manager dropdown to include printers as targets (grouped separately from toolheads)~~ _[DONE 2026-04-23 — `_printerSentinelOptions` inside the Feeds combobox, `buildFeedsCombobox` + `_comboHydrate` both pick them up]_, (3) Quick-Swap grid to render a "Printer Pool" banner row for sentinel slots _[NEEDS IMPLEMENTATION — sentinels round-trip through save/load correctly but do not surface in the Quick-Swap grid yet. When picked up, the natural place is the printer-aggregation view in `inv_quickswap.js` (Printer-type locations aggregate per-toolhead rows today via `resolvePrinterNameForPrinterLoc`); add a "Printer Pool" row that lists every (box, slot) whose target === `PRINTER:<thisPrinter>`. Tap/Enter should probably hand off to the existing deposit flow since there's no toolhead to swap.]_, ~~(4) `perform_smart_move` guard to skip auto-deploy for sentinel targets~~ _[DONE 2026-04-23 — guard at `logic.py` perform_smart_move bound_toolhead section]_. Backend tests: `test_dryer_bindings.py::test_validate_accepts_printer_sentinel_with_known_prefix` + siblings. UI E2E: `test_loc_mgr_bindings_ui_e2e.py::test_feeds_combobox_exposes_printer_sentinel_options` + round-trip.

* Add empty spool weight pull from parent feature added to the filament edit modal in other places (wizzard being the primary one)

* Weight QR Code on Filament Command Center Main menu is sometimes blocked by searh badge in lower right cortner on certain smaller or windows scaled screens.

* Code behind weight update code attached to the button on the main menu of filament command center doesn't take into account empty spool weight when updating. Total weight then overwrites the current weight, with out taking into account the spools empty weight.

* Location updates are not propagating to the buffer spool cards on the main menu of filament command center. This might be related to the archive status not updating on them as well.

* **[Feature] Manufacturer/Vendor Edit Modal (V1)** — Add an Edit Manufacturer/Vendor modal that mirrors the Edit Filament modal in look and function — same layout patterns, tab structure if applicable, save/cancel behavior, and visual design. **V1 scope is strictly Spoolman-native manufacturer fields only** (name, website, comment/notes — whatever Spoolman exposes for a vendor record by default). No custom `extra` fields, no backfill utility, no external-metadata import in this pass. The goal is a clean, functional edit surface that feels consistent with the filament edit experience. Future stretch goals (backfill, inheritance surfacing, external import, standalone Manufacturer Manager) can be layered on top once V1 is solid.

* Slicer profile information missing from Edit Filament modal.

* Missing spool weight dialogbox, doesn't accept enter as a confirm value when entering an empty spool weight into it.

* Unify all the fragmented ways we handle updating spool/filament weights, so we have only one code set to work off of.

* Newly created spools generated by the add/edit wizzard, should default to unassigned if a location isn't provided.

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
* Search by and filter by remaining weight.



## ⚡ Quick-Swap Enhancements
* **Denser spool/filament cards inside the Quick-Swap grid**: reuse the existing `SpoolCardBuilder` system (the one that renders cards in the dashboard, Location Manager, etc.) so each bound slot shows a real filament card instead of the current custom button. That would unlock integrating more actions — Eject, Details, Edit, Print Queue — directly from the Quick-Swap view without extra trips through other modals. Needs a new card variant (e.g. `'quickswap'` mode) that omits some details to keep the grid compact while retaining the shared styling and interaction code. Reference: [inv_quickswap.js](inventory-hub/static/js/modules/inv_quickswap.js) grid render + [ui_builder.js](inventory-hub/static/js/modules/ui_builder.js) `SpoolCardBuilder.buildCard()`.

## 📍 Location Management & Scanning
* **[CRITICAL DESIGN — blocks Project Color Loadout]** Make the Location Manager less brittle and more concrete. The current model is held together by string-prefix tricks and synthesis heuristics, not real entity relationships:
  - **Printer is not a real entity.** `🦝 Core One Upgraded` exists nowhere on disk — it's conjured at runtime by grouping toolhead LocationIDs whose prefix splits the same way (`CORE1-M0`, `CORE1-M1`, … → synthetic `CORE1` with friendly name pulled from `printer_map.printer_name`). This session's regression proved how fragile that is: a stale `XL` parent row with `Type: ""` made the whole synthesizer skip and "🦝 Core One Upgraded" rendered under "Unassigned virtual storage" until I patched the synthesizer to also seed from `printer_map`.
  - **Hierarchy is encoded in strings, not data.** `LR-MDB-1` packs Room (`LR`), device class (`MDB`), and instance (`1`) into one barcode. Moving a portable box (PM/PJ class) to a new room would require renaming, which destroys the printed barcode. Today every consumer that wants to walk the tree calls `loc.split('-')[0]` — there are at least a dozen such call sites. One typo per row corrupts the entire dashboard rendering (proven this session twice).
  - **No formal Toolhead → Printer parentage.** `printer_map` lives in `config.json`, separate from `locations.json`'s toolhead rows. The two are joined by exact uppercase string match on LocationID. Drift between the two files (one has CORE1-M0/M1, other doesn't) silently breaks deduction + grouping. The MMU M0/M1 alias dedup we shipped this sweep is itself a heuristic patching that drift.
  - **Loaders fail silently.** Pre-bug-2 fix, `load_locations_list()` returned `[]` on JSONDecodeError and the dashboard rendered with no Names / Types / Grouping — the user blamed a feature commit. We loud-failed the loader, but the underlying schema is so loose that a single typo in a single string field still takes everything down. The integrity tests we added (`test_locations_json_integrity.py`) are guarding a brittle data shape, not a robust schema.

  **Concrete recommendations** for the design session:
  1. **First-class `Printer` entity in `locations.json`** with: `id`, `printer_name` (the user-facing label, owns the emoji), `model`, `mmu_attached: bool`, `prusalink_creds_ref`. Replace the synthesizer entirely.
  2. **`parent_id` foreign key on every row** (toolhead → printer; dryer-box-slot → toolhead; box → room or printer). Retire `loc.split('-')[0]` site-by-site. Once retired, a typo in a string field can't break grouping — the FK is the truth.
  3. **Decouple the printed barcode from the hierarchy.** Barcodes become opaque IDs (e.g. `B7DK29`) — the hierarchy lives in `parent_id`. A `PM` box can move rooms without re-printing.
  4. **Move `printer_map` into `locations.json`.** A Printer row owns a `toolheads: [{id, position, mmu_routed: bool}]` list. Eliminates the cross-file drift class entirely. The MMU alias problem dissolves: a Printer with `mmu_attached: true` has exactly one toolhead per position; alias rows go away.
  5. **Schema validation on write, not just on read.** `save_locations_list` rejects rows with missing `Type` / `parent_id` / unknown FK target. The empty-Type and orphan-parent classes cease to exist.
  6. **Migration path:** Phase 1 — introduce `parent_id` alongside prefix parsing, emit a migration that backfills FKs from existing prefix structure. Phase 2 — migrate consumers one at a time (synthesizer first, then `_resolve_active_locs_for_printer`, then `get_bindings_for_machine`, then the Location Manager UI grouping). Phase 3 — retire prefix parsing and delete the synthesizer.

  **Why this blocks Project Color Loadout** ([docs/Project-Color-Loadout/](docs/Project-Color-Loadout/)): a Loadout binds N filaments to a *specific Printer instance*. Today there is no Printer instance to bind to — only a synthesized name conjured from prefix grouping. A loadout would have nothing to anchor on; saving "Apply Loadout to 🦝 Core One Upgraded" would store a string that breaks the moment someone renames the printer in `printer_map`. Concrete schema makes loadouts trivial; without it, any loadout work pays the brittleness tax twice (once to ship, again when the loadout-to-printer link drifts).

  _[ON HOLD — needs design session before any code changes. Bundles the previously-separate "Refactor Locations Database for true DB-driven Parent/Child hierarchies" entry. When we sit down: first ratify the schema above, then draft a Phase-1 migration tooling, then split the Location-Manager UI into vertical slices.]_

* 🔄 **Bulk Moves**: The ability to scan Box A (Source) and Shelf B (Destination) and say "Move EVERYTHING from Box A to Shelf B."
* Shapeshifting QR Codes in more places (like Audit button).

* Scanning a storage location (Any, dryerbox, Cart, etc) doesn't assign all items in the buffer to that cart, it requires you to scan the location multiple times in order to assign them all to it. _[LIKELY ALREADY FIXED — `performContextAssign` at inv_cmd.js:270 and `/api/smart_move` both accept a `spools[]` list and iterate the entire buffer. See the `[ALEX FIX] Bulk Assign` comment on inv_cmd.js:272. On next occurrence, capture the Network tab's `/api/smart_move` POST payload to confirm only one spool id was sent — if so the bug is upstream of the payload construction, in the buffer state. Otherwise close this out.]_
* Location Manager not syncing status across browser instances? _[ON HOLD — requires a real-time transport (SSE / WebSocket) on the backend. Current architecture is pull-only via `/api/locations` polling. Non-trivial; revisit after mobile mode since that work will establish the multi-client baseline anyway.]_

## 🎟️ Print Queue, Labels & Filament Usage
* Add ability for a scan to update the label printed/filament printed status to true/yes, Spoolman Reprint (Label).
    - Label Printed in Spoolman Spool data can be used to determine if a new Label has been printed.
    - Filaments: Spoolman Reprint field is set to Yes for items that need to have a label reprinted. Null or No mean that it already has a label with the Spoolman ID.
* It's too easy to have multiple legacy spools with no exact ID, where we could be assigning the wrong item... perhaps a pop-up when there could be more than 1 spool attached to the legacy ID, asking the user if they want to see the list of spools, or just reprint a new label.
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
* A way to compare the specs of two filaments side by side.


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