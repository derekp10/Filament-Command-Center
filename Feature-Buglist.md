# **Active Backlog (Organized by Feature Area)**

## 🎨 UI & Theming
* High-Contrast Pop (White Text/colored text + Heavy Black Shadow/or similar color shadowing) - EVERYWHERE. Adaptive High-Contrast Pop (Shadows Only) on colors. Maintain existing colors, but give them a pop appropriate for their color.
* **[UI Standardization]** Convert hard-coded inline JS/HTML `style="..."` brute-force stylings across the entire application into standardized global CSS configurations.
* Sometimes the swatch isn't showing the right color I think. Also doesn't handle multi-color spools currently.
* Side Quest: Spool card coloring system doesn't seem to handle 4+ colors in a swatch for generating gradient.
* Improve readability for the status line, that includes Location type and Amount of spools (1/x) Assigning a color to full boxes (possibly red or something that works with the theme).

## 🗂️ Modals & Add Inventory Wizard
* **Feature:** Add the ability to directly toggle the `Archived` status of a spool from within the "Edit Spool" modal interface.
* Extra long filament/spool names cause the Add Inventory Wizard buttons to become skewed with cancel above Create Inventory. Text data and UI buttons should not be a part of the same frame.
* Step 1: Material Selection should have a more fitting name, as it is more the method of creating a new item than it is about selecting a material.
* Give material type the ability to auto-complete based on existing types in the database. (Enter should complete, mirror selecting (Up/Down to select) from the filament attributes field).
* Background refreshes on the spool list for a filament can cause a button click to be lost if occurring during a refresh. Should only refresh if changed hash changes, used elsewhere. This only happens on the 2nd item on the list, possibly more.
* No feedback when clicking on the + Queue Label button. (Need to add a toast notification or something similar).
* Bring in more data from Spoolman into the details modals. It'd be nice to see a purchase link to easily get more of the same filament.
    - Some fields we might not want to bring in. Will need to go over the list of fields to bring in and leave alone.
    - Add a button to the details modal to easily get more of the same filament. (Configure in config file).
    - A confirmation maybe to auto add a new spool of the same filament when the button is clicked. Or an easy button to fill in standard data, but prompt for unique info (price, product link).
* Help button to provide information on how to use a modal, and to try and store information about how things work in the code.
* For existing filaments, advanced search should also be able to accept a Filament from the search function. Seemed to be some sort of bug.

* Extruder and bed temps are missing from the filament side for data entry.
* No way to easily edit spool data after creation.
* Attempt to combine the creation of a new spool and filament into one step, so that the user doesn't need to create the filament first before being able to create the spool.
* Maintain the ability to add multiple spools of the same type at the same time.
* Implement a robust global window/modal management system to dynamically handle z-index stacking, backdrop layering, and body scrolling when multiple modals are open concurrently.

## 🔍 Search, Display & Filtering
* **Bug:** The `[📦 ARCHIVED]` badge is still failing to display natively on generated cards inside the Command Center buffer and the global Search UI.
* **Bug:** Displayed remaining weight for spools is sometimes rendering with excessively long unrounded decimal strings.
* Find spool functionality. Basically make finding a spool/filament easier than using Spoolman. Better support for color searches.
* For filaments, add count of rolls available of that color to the card. Use spool icon we've been using elsewhere. (🧵)
* Search by and filter by remaining weight.
* Track unprinted filament samples and create a button/queue like we have for labels.
* Loading spools into buffer from filament definition doesn't load all spool data into card.

## 📍 Location Management & Scanning
* Removing an item from a toolhead/MMU slot should set filabridge slot to empty.
* Ejecting something from a toolhead/MMU slot removes it from the slot as well as marking it as unslotted. It should retain the slot, but be unmarked as deployed.
* The ability to configure a box to change the slot order to go from left to right, or right to left.
* Ability to assign a box slot to a printhead/MMU, so that a scan to that box slot will auto load the spool.
* CR-MDB-1:SLOT:4 is treated as a location not a slot in a box.
* ⚖️ **The "Weigh-Out" Protocol**: Option (toggle or specific "Weigh & Eject" button) to update remaining weight before removing the spool. Important for spools with a QR code on them.
* 🔄 **Bulk Moves**: The ability to scan Box A (Source) and Shelf B (Destination) and say "Move EVERYTHING from Box A to Shelf B."
* Shapeshifting QR Codes in more places (like Audit button).
* Locations QR Codes should contain a `LOC:` code, and a `LOC:` code should be used to help identify locations. (Keep existing logic to allow for backwards compatibility, but allow for `LOC:` codes for future items).
* Slots CSV generation seems to put in 2 versions, one with the cleaned name, and one without.
* Slots CSV should include Slot + # (Slot 1, Slot 2, etc) as a field.
* Add unassigned Location in Location List.
* Slot Based QR codes are not sending the scanned item to the slot in the location it's attached to.
* Scanning a storage location (Any, dryerbox, Cart, etc) doesn't assign all items in the buffer to that cart, it requires you to scan the location multiple times in order to assign them all to it.
* Location Manager not syncing status across browser instances?
* Unable to send items to the unassigned location in the location list with a QR code scan.

## 🎟️ Print Queue, Labels & Filament Usage
* Add ability for a scan to update the label printed/filament printed status to true/yes, Spoolman Reprint (Label).
    - Label Printed in Spoolman Spool data can be used to determine if a new Label has been printed.
    - Filaments: Spoolman Reprint field is set to Yes for items that need to have a label reprinted. Null or No mean that it already has a label with the Spoolman ID.
* It's too easy to have multiple legacy spools with no exact ID, where we could be assigning the wrong item... perhaps a pop-up when there could be more than 1 spool attached to the legacy ID, asking the user if they want to see the list of spools, or just reprint a new label.
* Should be able to decode filament IDs that were scanned in using the barcode scanner (using input speed check to determine if marked as printed).
* Confirmed label print should be displayed somewhere on the card. Perhaps changing the printer icon to a checkmark for confirmed spools.
* Add label print button to filament sample cards.
* Some values in Print Queue are being set to yes, most are null. What is the process for setting them to true?
* Need a way to add newly created Filament/Spools to the print queue based on print flags in the database.
* Needs a window/modal that lists all the spools/filaments missing a confirmed label printing (By database check box).
* Data in the missing label window should be filterable or sortable (Oldest first, Newest first).
* Things sent to the print queue should be flagged for printing in the database, so that they can be placed and tracked in a separate list.
* Refresh ticks seem to be clearing the print queue? that or refreshes? Search button also broke for some reason.

## ⚙️ App Flow, Architecture & Database
* **MOBILE** Make the entire app mobile friendly so NFC/Scanning works on phones.
* Refactor dashboard to be more modular if possible, and reduce token size/context requirements.
* Make as much of Command Center user configurable as possible, using UI elements and a config import/export feature.
* **[UI Testing]** Implement comprehensive Playwright E2E structural testing across all UI elements globally. Verify that elements are not cutting, squishing, or overlapping each other.
* Empty spool weight doesn't always seem to update the backend correctly.
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
* Continue to support Spoolman's "Import from External" feature... Purchase emails, or Amazon/Vendor product pages.
* Standardize the size of all QR codes to match that of the sizes used on the command center. (Audit, eject, drop, etc).
* If legacy barcode has no spools attached to it, UI should warn about this, perhaps give option to add new spool?
* Spoolman ExternalID is not a visible field in Spoolman UI. Very low priority.


# **Overarching Issue**
I think we've inadvertently created 3 levels of logic/complexity here:
1. The physical, Scanning stuff and efficiently Moving it
2. A UI layer, for debugging, but should only really need to be looked at to confirm things
3. A full on interface that is easier to move spools around than having to use Spoolman's lackluster interface.
All 3 of these things are important and have value. We should table for now, and come back to once we've gotten more of the functionality in place.


# **Done**
* **UI/UX:** Add ability to clone/easy fill filament details for creating a new spool & filament.
* **UI/UX:** Clone button on a spool didn't properly load in the spool/filament to be duplicated into the existing filament section of the add inventory wizard.
* **UI/UX:** Fix Location Manager UI Dryer box slot locations not correctly displaying all filament information.
* **Modals:** Add spool button on the list of spools in the filament details modal that links you to the details of the spool.
* **Modals:** Added "Send to Print Queue" button for individual spools inside the Filament Details popup.
* **Bug Fix:** Live: Names are not working correctly on spools, shows "" instead of the name. (Fixed in `inv_loc_mgr.js`)
* **Bug Fix:** Live: Cannot create spools manually. (Fixed JSON serialization in `spoolman_api.py`)
* **Feature:** Support clone feature for Spools, to auto populate an existing spool. (Completed Epic 2)
* **Feature:** Figure out a way to fill in density for filaments. (Completed Epic 2)
* **Database:** Fix `container_slot` serialization error causing Spoolman database update rejections (`400 - Invalid extra field for key container_slot: Value is not a string`).
* **Location:** Added color coding to the badges on the location (Location Type).
* **Location:** Added color indicate of dryerbox/tool fullness (1/1 Green, 2/1 Red, < Max White).
* **Location:** Ejecting from slot is not showing as being ejected by setting slot to empty.
* **Location:** Trash button, which I think does the same thing as ejecting, also doesn't seem to work here, for spools that are assigned to the location, but doesn't have a slot attached to them.
* **Location:** Refactored Location DB to use JSON config instead of CSV, added native sync for Spoolman Location API, and built automated tests.
* **Logging:** Fix ghost `Label Verified` log spam when Spoolman API explicitly rejected backward backlog reductions.
* **Command Center:** Fixed Undo Buffer Restoration to correctly recall spools to the buffer and reversed Toolhead Ejection cascades.
* **Command Center:** Eject should auto disable if we move off of the command screen to any other screen or modal.
* **Command Center:** Fix backend logging to not repeat non-useful data in the logs.
* **Print Queue:** Fixed Print Queue displaying "No Loc" for all spools.
* **Live Activity:** Fixed swatch circles in the "Live Activity" Dashboard log pane to accurately display CSS conic gradients mathematically divided for multi-color filament spools.
* **Live Activity:** Implemented background polling for Filabridge `GET /api/print-errors` to expose `gcode` parsing errors in the Live Activity log.
* **System:** Engineered a native CSS physical shield inside `scripts.html` to consume hardware `mousedown`/`click` wake-up hits natively when the Scanner Pauses.
* **System:** Set it so that the screen don't sleep. Screen still times out on laptop. Fixed via robust native WakeLock API re-acquisition.
* **UI/UX:** Unify Filament/Spool UI Cards into a universal `SpoolCardBuilder` engine to guarantee all Command Center sections (Search, Location, Buffer) share the exact same structural HTML layout and style. 
* **UI/UX:** Fixed Location Manager footer action buttons squishing into each other and clipping their colorful backgrounds by properly wrapping the flexbox grid and padding the text elements.
* **UI/UX:** Addressed the "Black filaments need a better way to show border" bug by mathematically injecting a dark metallic/carbon diagonal gradient for perfectly dark spools in `getFilamentStyle`.
* **UI/UX:** Fixed the floating point display issue for weight metrics (`33.860000000014g`) by stripping backend calculations and handling clean structural `Math.round` execution securely inside the browser via the new card builder logic.
* **Bug Fix:** Fixed the Spool Edit modal bug where opening it over the Location Manager caused the editing dialog to pop up behind the backdrop, blocking interaction.
* **UI/UX:** Globally swapped the generic spool emoji (🧵) for the specific DNA vector (🧬) when referring to Filament roots across the Multi-Spool Queue Modal and UI Builders.
* **UI/UX:** Added a dedicated "Refresh" button directly natively integrated into the Search Offcanvas to easily pull immediate REST queries without clearing query states.
* **UI/UX:** Contextually renamed the "TRASH" interface button to "EJECT" inside Location Manager cards dynamically whenever the target spool does not hold a specific structural slot assignment, unifying command terminology.
* **UI/UX:** Injected `position: sticky; top: 0;` natively to all globally generated dark-table headers across the application so that structural dataset columns never vanish when scrolling a deep component list.
* **UI/UX:** Globally replaced the dark-grey-on-dark-grey Bootstrap modal close button arrays with the `.btn-close-white` variant, pushing the `X` into a high-contrast visual priority above the system backdrops.
* **UI/UX:** Explicitly unbound the `Tab` sequence bypass from the Filament Attributes multiselect tag engine loop; users can now safely form-tab to the next wizard field logically, while `Enter` retains explicit commit control logic.
* **Bug Fix:** Fixed Filament Attributes being completely non-functional — selections couldn't be made, items couldn't be added to the list, and the Add button had no effect.
* **UI/UX:** Relabeled "STEP 1: MATERIAL SELECTION" to "STEP 1: CREATION METHOD" across the Inventory Wizard structural HTML to clarify that you are determining *how* a spool is sourced rather than strictly mapping internal materials.
* **UI/UX:** Bound a global green `showToast()` confirmation feedback trigger natively onto the `+ Queue Label` action scripts within both the Filament and Spool view contexts to verify database insertion.
* **UI/UX:** Injected dynamic `item.archived` checks broadly into the universal `SpoolCardBuilder` string processor, appending a highly-visible red `[📦 ARCHIVED]` tag right onto the item name element directly dynamically so hidden obsolete artifacts are blatantly identifiable across all Location/Buffer/Search panes.
* **Bug Fix:** Fixed the Search UI completely ignoring the 'In Stock' toggle state by dynamically appending `?allow_archived=true` to the native Spoolman REST queries whenever the toggle is deactivated, bypassing Spoolman's default hidden state payload.
* **Bug Fix:** Fixed explicitly typed Command Center scan payloads dropping the archive identifier. Fixed a multi-layer disconnect where `/api/identify_scan` failed to map the JSON key, AND `inv_cmd.js` aggressively stripped unmapped keys from the `state.heldSpools` cache arrays before passing the object to the card builder.
* **Bug Fix:** Fixed explicit `[📦 ARCHIVED]` display omission across Search and Buffer UI. Resolved a secondary backend logic loop in `spoolman_api.py` dropping the archived dictionary flag during search generation, and concurrently softened Javascript boolean checks in `ui_builder.js` to ensure payload string conversions render correctly.