# **New and Unsorted Features/Bugs**






* Keeping the screen on when afk, still causes the screen to blank out. Confirmed on laptop, not on desktop. _[ON HOLD — OS-level power management, not fixable in app code. Candidate mitigations if we care: Wake Lock API (`navigator.wakeLock.request('screen')`) gated behind a toggle in the nav bar; only works when the tab is foreground. Worth considering if we add a kiosk/shop-floor mode.]_
* Filament Edit follow-ups (Edit Filament Waves 0–8 shipped 2026-04-22 / 2026-04-23):
  * External-metadata import panel for the Edit Filament modal — Prusament spool-specific data links and open-filament-database lookup, parity with the wizard's "Import from External" button. **Decision: Build a slim single-URL quick-paste panel as a new dedicated section in the Edit Filament modal** (not inside Advanced — it deserves its own section so parsed results can be reviewed before applying). Reuse as much of the wizard's existing importer/parser code as possible on both the backend parse path and the result-display layer. The new section should show a preview of what the parser found, with field-by-field confirmation before writing.

* Config button, for configuing certain things in the system without having to edit a config file manually in a text editor. **Decision: Full-schema design first.** The architecture must be extensible so adding new configurable items "just works" without code changes to the config UI itself. The schema should be self-describing (key, label, type, default, section, validation rules) so the UI can render any new entry automatically. This will pull in the "Make as much of Command Center user configurable as possible" item. When we sit down for design: define the schema format, config storage (JSON file vs. DB table), import/export format, and a section hierarchy. _[NEEDS DESIGN SESSION — schedule a dedicated design discussion before any code starts.]_

* Filabridge status light is still blinking on and of, just more eraticly now. Need to look into this further. _[ON HOLD — hardware/firmware on the filabridge device itself. Not actionable from this repo until we can instrument the device side or get a usage log with timestamps correlated to filabridge-side network events.]_


* Check why FIL:58 wasn't marked as labeled when scanned. The `label_printed` field was retired in M7 and replaced with `needs_label_print` (boolean) — barcode-scan path now updates this field at `app.py:921-922, 968-969`. The FIL:58 case specifically needs manual repro to see whether the update fires and why Activity Log was silent. Could be because FIL:58 is an old physical swatch with no prior spoolman state. _[ON HOLD — need to locate or reprint the FIL:58 physical label/swatch before repro can be attempted. When found: scan with DevTools open → Network tab → `/api/identify_scan` response + Activity Log ticker.]_


* Sub-bug: "Display modal on Display modal" — suspect this is the filament→spool chain at [inv_details.js:304](inventory-hub/static/js/modules/inv_details.js#L304) interacting with the silent-refresh paths at lines 386/395. Needs its own reproduction trace before fixing. _[PARTIAL REPRO 2026-04-29 — Derek reports the crash appears to happen when the spool/filament details modal and the Add/Edit Wizard are both engaged simultaneously. Observed twice. This is likely the same root cause as the frontend lock-up at L22 below — a modal-on-modal race condition leaving `state.processing` stuck or an unhandled promise rejection. Next occurrence: capture DevTools Console + Network tabs BEFORE refreshing; `console.trace` wrapper around `openFilamentDetails` / `openSpoolDetails` / wizard open to see the call stack at the double-open.]_

* An unknow issue caused the frontend to lock up, causing it to no longer update to take barcodes. A hard refresh (Control shift R and Control F5) fixed it. We need to figure out what caused this, and fix it so it doesn't happen again. This could be related to the eject button issue above. Also seemed to have cause updates to filabridge to stop until the front end was refreshed. _[RECURRED 2026-04-29 — now believed to be the same root cause as the "Display modal on Display modal" bug at L20. Derek observed the crash twice when the details modal and the Add/Edit Wizard were both open. Likely a modal-on-modal race condition (e.g. wizard open fires while details modal's silent-refresh is mid-flight → unhandled promise rejection → `state.processing` stuck true → all barcode input and FilaBridge updates freeze). Next occurrence: DON'T hard-refresh first. Open DevTools → Console and Network tabs, screenshot pending XHRs and any red errors, then refresh.]_




* Need to do something about the fact that if a toolhead has multiple slots assigned to it for a dryer box, that new spool assignments don't automatically take over the current toolhead's assigned spool. **Decision: (c) Leave it to the user via Quick-Swap.** Intent is ambiguous — a new spool landing in a shared box may not mean the user wants to switch the active toolhead assignment (e.g., staging spools for later). Quick-Swap is the deliberate, explicit action for swapping. No auto-switch or auto-prompt. _[RESOLVED — no code change needed.]_

* No way to assigne a slot to a printer without having a toolhead assigned to it. It would be nice if we could assign slots to a printer so they show up for possible easy swaping, but not actually being assigned to a toolhead. (in cases where the dryer box is basically ment for a printer, but we can't use a slot because of layout. Prusa XL and LR-MDB-1:SLOT:4 is a good example.) **Decision: Sentinel value approach** — `slot_targets` will accept a `"PRINTER:<id>"` value (e.g. `"PRINTER:XL"`) in addition to strict toolhead LocationIDs. The Quick-Swap grid renders these as printer-affiliated slots (with a distinct visual treatment), but `perform_smart_move`'s auto-deploy logic skips sentinel-valued targets so no toolhead assignment is made. Changes needed: ~~(1) `slot_targets` validation to allow the new prefix~~ _[DONE 2026-04-23 — `validate_slot_targets` + `is_printer_sentinel` in `locations_db.py`]_, ~~(2) Location Manager dropdown to include printers as targets (grouped separately from toolheads)~~ _[DONE 2026-04-23 — `_printerSentinelOptions` inside the Feeds combobox, `buildFeedsCombobox` + `_comboHydrate` both pick them up]_, (3) Quick-Swap grid to render a "Printer Pool" banner row for sentinel slots _[NEEDS IMPLEMENTATION — sentinels round-trip through save/load correctly but do not surface in the Quick-Swap grid yet. When picked up, the natural place is the printer-aggregation view in `inv_quickswap.js` (Printer-type locations aggregate per-toolhead rows today via `resolvePrinterNameForPrinterLoc`); add a "Printer Pool" row that lists every (box, slot) whose target === `PRINTER:<thisPrinter>`. Tap/Enter should probably hand off to the existing deposit flow since there's no toolhead to swap.]_, ~~(4) `perform_smart_move` guard to skip auto-deploy for sentinel targets~~ _[DONE 2026-04-23 — guard at `logic.py` perform_smart_move bound_toolhead section]_. Backend tests: `test_dryer_bindings.py::test_validate_accepts_printer_sentinel_with_known_prefix` + siblings. UI E2E: `test_loc_mgr_bindings_ui_e2e.py::test_feeds_combobox_exposes_printer_sentinel_options` + round-trip.

* **[Feature] Manufacturer/Vendor Edit Modal (V1)** — Add an Edit Manufacturer/Vendor modal that mirrors the Edit Filament modal in look and function — same layout patterns, tab structure if applicable, save/cancel behavior, and visual design. **V1 scope is strictly Spoolman-native manufacturer fields only** (name, website, comment/notes — whatever Spoolman exposes for a vendor record by default). No custom `extra` fields, no backfill utility, no external-metadata import in this pass. The goal is a clean, functional edit surface that feels consistent with the filament edit experience. Future stretch goals (backfill, inheritance surfacing, external import, standalone Manufacturer Manager) can be layered on top once V1 is solid.

* Slicer profile information missing from Edit Filament modal.

* Newly created spools generated by the add/edit wizzard, should default to unassigned if a location isn't provided.

* Need to retool how the location selector works in the add/edit wizzard. It doesn't "Flow" properly. Having to delete the existing text to get the full list to change it is a bit clunky.

* Add Max tempratures to the details modals for spools and filaments. Perferably side by side. Min left of max, should be same row with own titles like the min's currently have.

* I think the add/edit inventory wizard is too complicated, we should definitely do a clean up pass on this and all of it's processes. I like what's here, but it's a lot of data. The functionality is good, but it just really needs some modernization or something. it's very clunky. We should try and make it more intuitive to use.

* Lagacy QR code scans cause the ? button to engage and pop up the help window. Not sure if theres a good fix for this.

* Fix version number that no longer gets updated. (Remove, or find a way to update it when we do updates.)

* Unknown crash on Filament command center after auto deduct fired. Had to refresh browser window to get QR code scans working? Need to check code for any breaks.
Logs Below from Prod server:
2026-04-27 18:04:33.899463+00:00Collecting flask
2026-04-27 18:04:33.976420+00:00Downloading flask-3.1.3-py3-none-any.whl.metadata (3.2 kB)
2026-04-27 18:04:34.019279+00:00Collecting requests
2026-04-27 18:04:34.032112+00:00Downloading requests-2.33.1-py3-none-any.whl.metadata (4.8 kB)
2026-04-27 18:04:34.056354+00:00Collecting blinker>=1.9.0 (from flask)
2026-04-27 18:04:34.069011+00:00Downloading blinker-1.9.0-py3-none-any.whl.metadata (1.6 kB)
2026-04-27 18:04:34.100922+00:00Collecting click>=8.1.3 (from flask)
2026-04-27 18:04:34.114885+00:00Downloading click-8.3.3-py3-none-any.whl.metadata (2.6 kB)
2026-04-27 18:04:34.139339+00:00Collecting itsdangerous>=2.2.0 (from flask)
2026-04-27 18:04:34.151649+00:00Downloading itsdangerous-2.2.0-py3-none-any.whl.metadata (1.9 kB)
2026-04-27 18:04:34.178137+00:00Collecting jinja2>=3.1.2 (from flask)
2026-04-27 18:04:34.194351+00:00Downloading jinja2-3.1.6-py3-none-any.whl.metadata (2.9 kB)
2026-04-27 18:04:34.264374+00:00Collecting markupsafe>=2.1.1 (from flask)
2026-04-27 18:04:34.277629+00:00Downloading markupsafe-3.0.3-cp311-cp311-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl.metadata (2.7 kB)
2026-04-27 18:04:34.316278+00:00Collecting werkzeug>=3.1.0 (from flask)
2026-04-27 18:04:34.328327+00:00Downloading werkzeug-3.1.8-py3-none-any.whl.metadata (4.0 kB)
2026-04-27 18:04:34.453735+00:00Collecting charset_normalizer<4,>=2 (from requests)
2026-04-27 18:04:34.465855+00:00Downloading charset_normalizer-3.4.7-cp311-cp311-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl.metadata (40 kB)
2026-04-27 18:04:34.472784+00:00━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 40.9/40.9 kB 6.7 MB/s eta 0:00:00
2026-04-27 18:04:34.498572+00:00Collecting idna<4,>=2.5 (from requests)
2026-04-27 18:04:34.518411+00:00Downloading idna-3.13-py3-none-any.whl.metadata (8.0 kB)
2026-04-27 18:04:34.561527+00:00Collecting urllib3<3,>=1.26 (from requests)
2026-04-27 18:04:34.573095+00:00Downloading urllib3-2.6.3-py3-none-any.whl.metadata (6.9 kB)
2026-04-27 18:04:34.608041+00:00Collecting certifi>=2023.5.7 (from requests)
2026-04-27 18:04:34.624093+00:00Downloading certifi-2026.4.22-py3-none-any.whl.metadata (2.5 kB)
2026-04-27 18:04:34.666017+00:00Downloading flask-3.1.3-py3-none-any.whl (103 kB)
2026-04-27 18:04:34.683495+00:00━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 103.4/103.4 kB 6.1 MB/s eta 0:00:00
2026-04-27 18:04:34.705494+00:00Downloading requests-2.33.1-py3-none-any.whl (64 kB)
2026-04-27 18:04:34.709807+00:00━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 64.9/64.9 kB 20.5 MB/s eta 0:00:00
2026-04-27 18:04:34.727383+00:00Downloading blinker-1.9.0-py3-none-any.whl (8.5 kB)
2026-04-27 18:04:34.744259+00:00Downloading certifi-2026.4.22-py3-none-any.whl (135 kB)
2026-04-27 18:04:34.760510+00:00━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 135.7/135.7 kB 9.4 MB/s eta 0:00:00
2026-04-27 18:04:34.772258+00:00Downloading charset_normalizer-3.4.7-cp311-cp311-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl (214 kB)
2026-04-27 18:04:34.798196+00:00━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 214.1/214.1 kB 8.5 MB/s eta 0:00:00
2026-04-27 18:04:34.817317+00:00Downloading click-8.3.3-py3-none-any.whl (110 kB)
2026-04-27 18:04:34.826891+00:00━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 110.5/110.5 kB 12.7 MB/s eta 0:00:00
2026-04-27 18:04:34.844838+00:00Downloading idna-3.13-py3-none-any.whl (68 kB)
2026-04-27 18:04:34.850785+00:00━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 68.6/68.6 kB 13.5 MB/s eta 0:00:00
2026-04-27 18:04:34.862310+00:00Downloading itsdangerous-2.2.0-py3-none-any.whl (16 kB)
2026-04-27 18:04:34.879394+00:00Downloading jinja2-3.1.6-py3-none-any.whl (134 kB)
2026-04-27 18:04:34.890062+00:00━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 134.9/134.9 kB 13.9 MB/s eta 0:00:00
2026-04-27 18:04:34.907644+00:00Downloading markupsafe-3.0.3-cp311-cp311-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl (22 kB)
2026-04-27 18:04:34.927759+00:00Downloading urllib3-2.6.3-py3-none-any.whl (131 kB)
2026-04-27 18:04:34.942405+00:00━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 131.6/131.6 kB 9.5 MB/s eta 0:00:00
2026-04-27 18:04:34.962707+00:00Downloading werkzeug-3.1.8-py3-none-any.whl (226 kB)
2026-04-27 18:04:34.988332+00:00━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 226.5/226.5 kB 9.0 MB/s eta 0:00:00
2026-04-27 18:04:35.069738+00:00Installing collected packages: urllib3, markupsafe, itsdangerous, idna, click, charset_normalizer, certifi, blinker, werkzeug, requests, jinja2, flask
2026-04-27 18:04:37.434452+00:00Successfully installed blinker-1.9.0 certifi-2026.4.22 charset_normalizer-3.4.7 click-8.3.3 flask-3.1.3 idna-3.13 itsdangerous-2.2.0 jinja2-3.1.6 markupsafe-3.0.3 requests-2.33.1 urllib3-2.6.3 werkzeug-3.1.8
2026-04-27 18:04:37.434642+00:00WARNING: Running pip as the 'root' user can result in broken permissions and conflicting behaviour with the system package manager. It is recommended to use a virtual environment instead: https://pip.pypa.io/warnings/venv
2026-04-27 18:04:37.552489+00:002026-04-27T18:04:37.552489452Z
2026-04-27 18:04:37.552530+00:00[notice] A new release of pip is available: 24.0 -> 26.1
2026-04-27 18:04:37.552541+00:00[notice] To update, run: pip install --upgrade pip
2026-04-27 18:04:37.922140+00:002026-04-27 11:04:37,921 - INFO - 🛠️ Server v154.26 (Scale Weights Update) Started
2026-04-27 18:04:37.931279+00:00* Serving Flask app 'app'
2026-04-27 18:04:37.931305+00:00* Debug mode: off
2026-04-27 18:12:28.591071+00:002026-04-27 11:12:28,590 - INFO - DIRTY SPOOL DATA: {'used_weight': 553}
2026-04-27 20:47:23.870960+00:002026-04-27 13:47:23,870 - INFO - DIRTY SPOOL DATA: {'used_weight': 574}
2026-04-27 20:55:33.876324+00:002026-04-27 13:55:33,876 - WARNING - ⚠️ <b>Smart Load:</b> Ejecting #254 from CORE1-M0...
2026-04-27 20:55:34.246172+00:002026-04-27 13:55:34,246 - INFO - 🖨️ #225 [Legacy: 137] Stronghero3D PETG (Chameleon Mirror Chrome) -> CORE1-M0
2026-04-27 20:56:18.554475+00:002026-04-27 13:56:18,554 - INFO - 🪑 Auto-slot: CR-MDB-1 has free slot 4 — assigning spool there
2026-04-27 20:56:18.927858+00:002026-04-27 13:56:18,927 - INFO - 📦 #254 [Legacy: 125] Prusament PC (Black) -> Dryer CR-MDB-1 [Slot 4]
2026-04-27 20:56:18.967039+00:002026-04-27 13:56:18,966 - INFO - ⚡ Auto-deployed Spool #254 — Prusament PC (Black) → <b>CORE1-M0</b> (source: CR-MDB-1:SLOT:4)
2026-04-27 22:09:22.457261+00:002026-04-27 15:09:22,456 - INFO - 🔄 Auto-Recovering FilaBridge Error for 🦝 XL...
2026-04-27 22:28:47.552550+00:002026-04-27 15:28:47,552 - INFO - ✔️ Auto-deducted 193.3g from Spool #228 (RAM-Fetch): [542.0g at start ➔ 348.7g remaining]
2026-04-27 22:28:47.841658+00:002026-04-27 15:28:47,841 - INFO - ✔️ Auto-deducted 26.4g from Spool #226 (RAM-Fetch): [972.1g at start ➔ 945.8g remaining]
2026-04-27 22:28:48.063675+00:002026-04-27 15:28:48,063 - INFO - ✔️ Auto-deducted 110.5g from Spool #240 (RAM-Fetch): [937.0g at start ➔ 826.5g remaining]
2026-04-27 22:28:48.323606+00:002026-04-27 15:28:48,323 - INFO - ✔️ Auto-deducted 25.8g from Spool #230 (RAM-Fetch): [627.0g at start ➔ 601.2g remaining]
2026-04-28 05:43:08.762694+00:002026-04-27 22:43:08,762 - INFO - ℹ️ Spool #225 already verified
2026-04-28 05:45:44.058353+00:002026-04-27 22:45:44,058 - INFO - 📦 Auto-archived Spool #225 (remaining weight hit 0) — moved to UNASSIGNED
2026-04-28 05:45:44.543018+00:002026-04-27 22:45:44,542 - WARNING - 🗑️ Force Unassigned #225
2026-04-28 05:48:22.747416+00:002026-04-27 22:48:22,747 - INFO - ✔️ Spool #246 Label Verified
2026-04-28 05:48:27.938720+00:002026-04-27 22:48:27,938 - INFO - 🔎 CORE1-M0: 0 item(s)
2026-04-28 05:48:27.956696+00:002026-04-27 22:48:27,956 - WARNING - SCAN LOG: Legacy Location Barcode Scanned (CORE1-M0)
2026-04-28 05:48:28.502090+00:002026-04-27 22:48:28,501 - INFO - 🖨️ #246 [Legacy: 137] Stronghero3D PETG (Chameleon Mirror Chrome) -> CORE1-M0


* Spools on a toolhead (yes, some how multiple are on there.) Cannot be changed once a print is started becasue the confirm change modal is being blocked, canceled, or hidden, preventing the user from swaping out filaments while a print is warming up. This wasn't intended. As I can easily forget to change a spool out during the begining of a print.

* Scanning a toolhead with multiple filaments in the command center buffer, cause all filaments to be assigned to the toolhead. This shouldn't happen. Only the top most item on the list should be assigned to the toolhead. The rest should stay in the buffer. Scan was the toolhead QR code directly (Core1-M0).

* Location search box should display all locations once a vaild location is selected or loaded in the Add/Edit wizzard. This should be propigated to other location search text boxes, if not already present.

* Constantly being prompted that a filament or spool is verified every scan on the activity log, is a bit much, we need a way to tone that down some, or as I hate to say it, possibly turn it off. We should have another way for the user to verify this. Instead of continuing to notifying them in the Activity Log.

* Forcing a location using the location edit in the spool display modal, should proably update depolyed status to be off, unless the location selected is a toolhead. (Asuming toolheads are a valid target for this location update.)

## Prusament Enhancements ##
* Ability to merge duplicate filaments. Sometimes created when the existing filament card and the one the parcer generates based on prusament filaments don't match exactly. _[PARTIAL 2026-04-26 — duplicate **prevention** is in: tier-1 product-id matcher prefers filaments tagged with the same /spool/<id>/ as the scan, plus a duplicate-picker UI when the matcher can't disambiguate so the user picks (or chooses Create new). What's still missing: **merging existing duplicates** — a UI affordance that re-points all spools from one filament to another and archives/deletes the source. The picker prevents you from making MORE duplicates; you still need a way to clean up the ones already in the DB.]_

* **[Cleanup]** Audit the wizard's "Import from External" panel — which parsers actually still work, which are stale, what's the current dropdown showing? The user reported "I've completely forgotten what parcers we have set up there that work" — the Step 2 import-from-external surface needs a documentation pass and probably a deprecation pass. Code lives in `inventory-hub/external_parsers.py` (PrusamentParser, AmazonParser, SpoolmanParser, possibly others) and the dropdown is wired in `templates/components/modals_wizard.html`. As of 2026-04-26, Prusament works (per the per-spool scan flow); Amazon needs BeautifulSoup4 which isn't installed in dev (test_external_parsers.py::test_amazon_parser_matching fails locally for that reason); 3DFP / Spoolman-native should be re-tested. Worth combining with a UX refresh if we're touching that surface.

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

  _[IN PROGRESS — Phase 1A shipped 2026-04-25 on `feature/locations-parent-id-phase-1a`. Subsequent phases tracked below.]_

  **Phase tracker (kept here so we don't lose the thread between sessions):**
  - [x] **Phase 1A — additive plumbing** (2026-04-25). Added `parent_id` field, `derive_parent_id_from_prefix`, `resolve_parent`, and `migrate_parent_ids_if_needed` to [locations_db.py](inventory-hub/locations_db.py); wired the startup migration into [app.py](inventory-hub/app.py) with timestamped backup; added ~15 unit tests in [test_dryer_bindings.py](inventory-hub/tests/test_dryer_bindings.py) plus 3 integrity-contract tests in [test_locations_json_integrity.py](inventory-hub/tests/test_locations_json_integrity.py). **No consumer reads `parent_id` yet** — purely sets up the data so Phases 1B/2 can migrate consumers safely.
  - [ ] **Phase 1B — first consumer migration**: replace `split('-')[0]` at [app.py:879](inventory-hub/app.py#L879) (room-occupancy parent extraction in the synthesizer) with `locations_db.resolve_parent`. Smallest possible consumer change; proves the abstraction works in production.
  - [ ] **Phase 2 — remaining backend consumer migrations**: [app.py:900](inventory-hub/app.py#L900) (synthesizer printer-prefix seed); [locations_db.py:210](inventory-hub/locations_db.py#L210) (`_known_printer_prefixes`); [logic.py:596](inventory-hub/logic.py#L596) (smart_eject room prefix); [spoolman_api.py:456,464](inventory-hub/spoolman_api.py#L456) (child-of-parent matching for spool location queries). One per commit; each gets its own integration test.
  - [ ] **Phase 2.5 — frontend consumer migrations**: [inv_core.js:407–408,498](inventory-hub/static/js/modules/inv_core.js#L407) (sort + parent-row styling); [inv_loc_mgr.js:344](inventory-hub/static/js/modules/inv_loc_mgr.js#L344) (sentinel-option derivation). API surface stays the same; JS reads the new `parent_id` field instead of splitting LocationID.
  - [ ] **Phase 3 — first-class `Printer` rows on disk**: persist what the synthesizer at [app.py:872–958](inventory-hub/app.py#L872) currently conjures. Add `Printer` to the required-Type list in `_required_keys_for`. Migrate `printer_name` from `config.json:printer_map` into the Printer row's `Name` field. Retire the runtime synthesizer. Tighten `parent_id` validation: every non-null `parent_id` must point to a real on-disk row. **This is the phase that unblocks Project Color Loadout.**
  - [ ] **Phase 4 — fold `printer_map` into `locations.json`**: add a `toolheads` array on the Printer row carrying `position` and `mmu_routed`. Retire `config.json:printer_map`. Update `_resolve_active_locs_for_printer`, `get_bindings_for_machine`, `validate_slot_targets`, and `/api/printer_map` to read from the new shape. MMU M0/M1 alias dedup heuristic dissolves (a Printer with `mmu_attached: true` has exactly one toolhead per position).
  - [ ] **Phase 5 — retire prefix parsing**: delete `derive_parent_id_from_prefix` and the fallback inside `resolve_parent`. Remove all remaining `split('-')[0]` sites. Add write-time schema validation that rejects `save_locations_list` calls with missing or orphan `parent_id`. Decouple printed barcodes from hierarchy strings (per recommendation #3 above).

* 🔄 **Bulk Moves**: The ability to scan Box A (Source) and Shelf B (Destination) and say "Move EVERYTHING from Box A to Shelf B."
* Shapeshifting QR Codes in more places (like Audit button).

* Scanning a storage location (Any, dryerbox, Cart, etc) doesn't assign all items in the buffer to that cart, it requires you to scan the location multiple times in order to assign them all to it. _[LIKELY ALREADY FIXED — `performContextAssign` at inv_cmd.js:270 and `/api/smart_move` both accept a `spools[]` list and iterate the entire buffer. See the `[ALEX FIX] Bulk Assign` comment on inv_cmd.js:272. On next occurrence, capture the Network tab's `/api/smart_move` POST payload to confirm only one spool id was sent — if so the bug is upstream of the payload construction, in the buffer state. Otherwise close this out.]_
* Location Manager not syncing status across browser instances? _[ON HOLD — requires a real-time transport (SSE / WebSocket) on the backend. Current architecture is pull-only via `/api/locations` polling. Non-trivial; revisit after mobile mode since that work will establish the multi-client baseline anyway.]_

## 🎟️ Print Queue, Labels & Filament Usage
*(Group 3 — Print Queue & Label Management — completed 2026-04-28; see `completed-archive.md` for resolved items.)*

## 🧪 Testing
* conftest.py groundwork landed in M0 (`inventory-hub/tests/conftest.py` with page, api_base_url, snapshot, scan, seed_dryer_box, with_held_spool, require_server). Remaining work: migrate existing test files to use these shared fixtures instead of their duplicated setup sequences.
* `test_return_and_breadcrumb.py::test_return_prefers_physical_source_over_first_binding` is failing with `TypeError: fake_move() got an unexpected keyword argument 'confirm_active_print'`. Found 2026-04-25 during the Phase-1A locations refactor — confirmed pre-existing on `dev` (failure reproduces on a clean checkout, unrelated to that branch's changes). Likely a `confirm_active_print` parameter was added to `logic.perform_smart_move` (or whichever function the test mocks) without updating the mock's signature in this test. Fix: open the test, find the `fake_move` lambda/function, add `confirm_active_print=None` (or `**kwargs`) to its signature so it absorbs the new keyword. Quick — but verify the test then asserts the correct behavior under the new arg, not just stops crashing.

## ⚙️ App Flow, Architecture & Database
* **MOBILE** Make the entire app mobile friendly so NFC/Scanning works on phones. (Perhaps a desktop mode to utalize barcode scanners, and a mobile mode of mostly touch interface and scanning barcodes/QR codes and NFC tags). The main difference being that mobile mode won't relye on all the inlaid barcode/qr codes we currently have in the interface currently for interacting with the UI elements.
* Refactor dashboard to be more modular if possible, and reduce token size/context requirements.
* Make as much of Command Center user configurable as possible, using UI elements and a config import/export feature.
* When changes are made to Spoolman extra fields, they usually ignore sort order in the database. We need a way to restore sort order.
* **Clean up filament attributes** — remove dead/duplicate entries from the `filament_attributes` choice list, AND add input validation so new garbage entries can't be created in the first place. _[2026-04-28 audit: Spoolman is the source of truth (CSVs no longer authoritative). Total 34 choices on the field; 27 actually used across 180 filaments. Spoolman's API rejects choice removal via POST (`400 "Cannot remove existing choices."`), so a true cleanup requires the snapshot-restore migration pattern (template: `migrate_container_slot_to_text` in `setup-and-rebuild/setup_fields.py`): snapshot all filaments' `filament_attributes` values → `force_reset` delete the field schema → recreate with cleaned choices → restore filtered values. Heavy for purely cosmetic dropdown cleanup; deferred until the migration is worth the time.

  **Prevention (actionable now — ship before any cleanup migration; an ounce of prevention is worth a pound of cure since removal is so expensive):** Every dead choice in the audit looks like an input-time error that the API made permanent: `Tran` (truncated — user hit enter before finishing `Transparent`), `Wood` (typed before `Wood Filled` existed), `Carbon-Fiber` (hyphen-vs-space dupe of `Carbon Fiber`), `Transparent; High-Speed` (semicolon-as-separator misuse), `F` (1-char typo). Concrete guards to add to the wizard's "+ Add new attribute" affordance (and any future Edit Filament parity surface):
    - **Minimum length** (≥3 chars) — blocks `F`-class typos.
    - **Trim + reject leading/trailing whitespace or punctuation** (`;`, `,`, `:`, `/`) — blocks `Transparent; High-Speed`-class separator confusions; users trying to add multiple attributes that way should be redirected to add them one at a time.
    - **Fuzzy/prefix match warning** — when the new value is within 1–2 Levenshtein edits of an existing choice, OR is a prefix of an existing choice, OR collapses to the same string after lowercasing + removing non-alphanumerics, surface a "Did you mean: <existing>?" prompt with two options: "Use existing" (the safe default) vs. "Add as new anyway" (requires deliberate confirmation). This is the single highest-value guard — would catch `Tran` → `Transparent`, `Wood` → `Wood Filled`, `Carbon-Fiber` → `Carbon Fiber` automatically.
    - **Two-step confirm for add-new** — adding a new choice to a field schema is rare and high-impact (Spoolman makes it permanent). The affordance should feel more like a settings change than a casual dropdown pick. After the fuzzy-match warning passes, surface a confirm dialog: "Add '<value>' as a permanent new filament attribute? This cannot be undone via the UI."
    - **Live preview of the canonical stored value** — show what will be stored after trim/normalization so users can see e.g. that `  Wood Filled  ` collapses to `Wood Filled` (and that `wood filled` would become a *new* choice distinct from `Wood Filled` if case-sensitivity bites).

    Likely lives in the wizard's dynamic-extra add-choice flow — search `inv_wizard.js` for the existing "+ Add new" handler on the materials/attributes multiselect (the same surface that landed in Edit Filament Wave 5/6). Apply the same guards consistently to any other add-new-choice entry point. Worth doing as its own small group/task even though the bulk cleanup migration stays deferred — prevention pays off the next time someone adds an attribute, while the migration only pays off once.

  **Confirmed safe to delete** (Derek 2026-04-28): `Carbon-Fiber` (dupe of `Carbon Fiber`), `Tran` (truncated), `Transparent; High-Speed` (semicolon-bogus), `Wood` (superseded by `Wood Filled`), `F` (typo).
  **Keep:** `+` — represents PLA+ filaments (currently displayed as `+ PLA`, but the value itself is intentional). Filament #132 (Creality Rainbow) uses it correctly.
  **Investigate before deciding:** `For Infill` — was used to flag color-switch / prototype-only filaments not meant for visible prints. Codebase grep confirms no replacement mechanism exists; if Derek wants a different infill-flag UX, that should be a separate item. Otherwise keep.
  `Matte Pro` — likely orphaned from a prior wipe-and-replace, currently unused. Probably safe to delete but Derek wants to confirm origin first.

  **Bad data to fix** (out of scope for choice cleanup): no orphaned values found in actual records — everything stored references either a still-valid choice or `+` (intentional).

  **Approach when ready:** Write `setup-and-rebuild/migrate_filament_attributes.py` following `migrate_container_slot_to_text` template. Should be runnable from host with config_loader path setup, ask for confirmation, snapshot → force_reset → recreate → restore. Verify against a live Spoolman dev instance with backup before touching prod.]_
* Continue to support Spoolman's "Import from External" feature for filaments...
    - open-filament-database
    - Prusament spool specific data links
    - Open Print Tags (Initialize, Read, and Write)
* Maybe we should figure out a way to set up a dev version for Spoolman and filabridge.
* Change auto refresh to be a pause button instead for live activity.
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