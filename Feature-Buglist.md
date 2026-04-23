# **New and Unsorted Features/Bugs**

* **[IMPORTANT]** Spoolman filament archiving is broken on the installed version — `PATCH /api/v1/filament/<id>` with `{"archived": true}` returns 200 but the flag is silently dropped; subsequent GETs never include the `archived` key on filaments (only spools). Dev and prod point at the same Spoolman. Impact: the wizard's auto-unarchive code (`inventory-hub/app.py` in `api_create_inventory_wizard`, added 2026-04-22) correctly calls `spoolman_api.update_filament(fid, {'archived': False})` whenever the parent filament looks archived — but that branch is effectively unreachable today because Spoolman never reports `archived: true` on a filament. `test_wizard_ux_polish.py::test_create_spool_auto_unarchives_parent_filament` skips on this basis. Next steps: (a) check whether Spoolman supports filament archival on a newer version and upgrade, or (b) track archive state on the filament via a custom `extra` field instead of the native flag. Related active-backlog entry: "Adding filament to an archived filament should automatically unarchive the filament" — code is in place, blocked on Spoolman support.


* Keeping the screen on when afk, still causes the screen to blank out. Confirmed on laptop, not on desktop.
* Filament Edit button? To access the fiament to make changes. (Updating the spool weight, or other attributes.) Might also make sense to add a way to edit the manufacture to add an empty spool weight as well. We would need a way to populate some weights into existing spools, if the spool weight is currently 0. As I don't think spoolman retroactivly updates past spools with a an empty spool weight of 0.
  * ✅ **MVP landed 2026-04-22**: "✏️ Edit Filament" button on the Filament Details modal footer opens a Swal form (name, material, empty spool weight, density, nozzle/bed temps, notes) and saves via `/api/update_filament`. The empty-weight field also shows the vendor's empty_spool_weight as a placeholder hint. Other entry points (card action button, card list, etc.) can copy `window.openEditFilamentForm(fil)` — it's reusable.
  * ⏸ **Remaining**: (1) backfill tool for historical spools stored with spool_weight=0 so they adopt the parent filament/vendor value. (2) Vendor and color_hex editing still need to go through the full wizard.

* Ability to edit filament specific data inside Filament command center. Currently there isn't a way to directly edit a filament that's used as the basis of other spools, without opening a spool. Some sort of edit workflow for chaing data directly related to filaments.

* Config button, for configuing certain things in the system without having to edit a config file manually in a text editor. (I'm not sure what all we'd want to put here, but it'd be nice to have.)

* In location manager, if an item is added to a loction that has slots, and there is a free slot, auto assign the item into that free slot. (If there are multiple free slots, fill the first empty one.)

* Review and unify update logic across the program, we have to many versions of update that keep getting orphined, or cause problems later on when they aren't included in a recent design change. We need to have a discussion on how best to fix this, so I want to have an implementation plan in place to iterate off of.

* Filabridge status light is still blinking on and of, just more eraticly now. Need to look into this further.


* Check why FIL:58 wasn't marked as labeled when scanned. The `label_printed` field was retired in M7 and replaced with `needs_label_print` (boolean) — barcode-scan path now updates this field at `app.py:921-922, 968-969`. The FIL:58 case specifically needs manual repro to see whether the update fires and why Activity Log was silent. Could be because FIL:58 is an old physical swatch with no prior spoolman state.


* Adding filament to an archived filament should automatically unarchive the filament.

* We either need a way to detect if MMU mode is one. Or change how M0 & M1 work for weight deductions. I did a test with a filament in both M0 and M1, and it deducted value from both I think. I'm not sure on this as I didn't mark down how much was in M1 before the test. But we shouldn't have seen any deduction from M0. Perhaps we just bind the two together, where no matter what mode M1 is alwasy either the first MMU slot or for when the mmu is disabled and the filamentjust direct feeds into the toolhead.

* Sub-bug: "Display modal on Display modal" — suspect this is the filament→spool chain at [inv_details.js:304](inventory-hub/static/js/modules/inv_details.js#L304) interacting with the silent-refresh paths at lines 386/395. Needs its own reproduction trace before fixing.

* An unknow issue caused the frontend to lock up, causing it to no longer update to take barcodes. A hard refresh (Control shift R and Control F5) fixed it. We need to figure out what caused this, and fix it so it doesn't happen again. This could be related to the eject button issue above. Also seemed to have cause updates to filabridge to stop until the front end was refreshed.

* It appears that while I was editing a spool's filament data that was sloted into a print head, saving caused it to be removed. We need to check to see why that is. Or the filament's location was listed the correct location, but it the location was regestring as empty 0/1 on location list modal, and nothing assigned inside the location manager modal.

* Currently using temp (Bed, Nozzle/Toolhead) in spoolman to store the low tempratures, but I really think we need to track the high tempratures for those values. Will need to look into the code and see what we can do to fix this. Will need to add extra fields for this on the filament side, and treat them not as custom fields in the ui placement, but as actual fields. Will need to reinfource the location of those fieds in the UI as custom fields have a tendency to re-order themselves. I have a line item for hammering down the field locations so they don't move around eveythime a custom entry is added into an extra field, so we should probably include this in that as well.

* Possible issues with >1kg spools and tracking weights?


* `test_manual_loc_override_e2e` — offcanvas-intercept bug fixed in M0. Currently xfailed because the Force Location modal was refactored from `<select>` to a searchable list; step 6 still drives the old select. Rewrite test against the new search+list UI.

* FCC Main Main screen buffer cards still don't always update after several backend changes. Setting filament to 0, doesn't seem to update to unassinged or it's deployed status.




* When a Spool gets archived, and the filamen attached to it doesn't have an empty spool weight, propmt the user of the missing spool weight and offer to assist in updating that data after they way the empty spool.
  * ⏸ **Needs UX decision**: inline overlay vs dedicated modal for the weigh-assist flow. Tightly coupled to the auto-archive-on-zero-weight item above — designing them together would avoid two separate prompt dialogs. With the Empty Spool Weight priority chain now in place, the "no empty weight" check must walk Spool → Filament → Vendor before deciding to prompt.


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
* Search by deployment status. Maybe under an advanced search set that is hidden but can be shown, so it doesn't take up a lot of extra space.
* Search by and filter by remaining weight.



## ⚡ Quick-Swap Enhancements
* **Denser spool/filament cards inside the Quick-Swap grid**: reuse the existing `SpoolCardBuilder` system (the one that renders cards in the dashboard, Location Manager, etc.) so each bound slot shows a real filament card instead of the current custom button. That would unlock integrating more actions — Eject, Details, Edit, Print Queue — directly from the Quick-Swap view without extra trips through other modals. Needs a new card variant (e.g. `'quickswap'` mode) that omits some details to keep the grid compact while retaining the shared styling and interaction code. Reference: [inv_quickswap.js](inventory-hub/static/js/modules/inv_quickswap.js) grid render + [ui_builder.js](inventory-hub/static/js/modules/ui_builder.js) `SpoolCardBuilder.buildCard()`.

## 📍 Location Management & Scanning
* Refactor the entire location managment system from the ground up. It's currently being a bit too complicated, and I think it can be cleaned up a bit if we just rethink the flow of this process. We've bolted a lot of stuff onto this system, and the has caused it to become a bit too cumbersome to both code and work with. I think we need to build in a better system for linking locations and device/boxes/storage things. We need to have a discussion on how best to fix this, so I want to have an implementation plan in place to iterate off of.
* The ability to configure a box to change the slot order to go from left to right, or right to left.

* 🔄 **Bulk Moves**: The ability to scan Box A (Source) and Shelf B (Destination) and say "Move EVERYTHING from Box A to Shelf B."
* Shapeshifting QR Codes in more places (like Audit button).

* Scanning a storage location (Any, dryerbox, Cart, etc) doesn't assign all items in the buffer to that cart, it requires you to scan the location multiple times in order to assign them all to it.
* Location Manager not syncing status across browser instances?
* Refactor Locations Database to support true DB-driven Parent/Child hierarchies. Currently, location hierarchy (Room -> Box -> Slot) is handled via string prefix parsing (`LR-MDB-1` means `LR`). This breaks portable/transient containers like `PJ` or `PM` boxes when they move rooms, because moving them implies renaming them, which destroys their printed barcode (`LOC:LR-PM-1`). Need to add a `ParentLocation` column to the locations database and detach the barcode ID string from the physical hierarchy tree.

## 🎟️ Print Queue, Labels & Filament Usage
* Add ability for a scan to update the label printed/filament printed status to true/yes, Spoolman Reprint (Label).
    - Label Printed in Spoolman Spool data can be used to determine if a new Label has been printed.
    - Filaments: Spoolman Reprint field is set to Yes for items that need to have a label reprinted. Null or No mean that it already has a label with the Spoolman ID.
* It's too easy to have multiple legacy spools with no exact ID, where we could be assigning the wrong item... perhaps a pop-up when there could be more than 1 spool attached to the legacy ID, asking the user if they want to see the list of spools, or just reprint a new label.
* Confirmed label print should be displayed somewhere on the card. Perhaps changing the printer icon to a checkmark for confirmed spools.
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