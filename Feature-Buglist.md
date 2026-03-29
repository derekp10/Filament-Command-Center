# **Active Backlog (Organized by Feature Area)**

## 🎨 UI & Theming
* Fix the borders on black filaments not standing out in the correct spot in the list (Lost contrast against dark UI backgrounds).
* High-Contrast Pop (White Text/colored text + Heavy Black Shadow/or similar color shadowing) - EVERYWHERE. Adaptive High-Contrast Pop (Shadows Only) on colors. Maintain existing colors, but give them a pop appropriate for their color.
* Sometimes the swatch isn't showing the right color I think. Also doesn't handle multi-color spools currently.
* Side Quest: Spool card coloring system doesn't seem to handle 4+ colors in a swatch for generating gradient.
* Improve readability for the status line, that includes Location type and Amount of spools (1/x) Assigning a color to full boxes (possibly red or something that works with the theme).
* Spool 'Archived' status badge colors are inconsistent (some yellow, most red). Standardize to a single color (e.g. Red) globally across all views.

## 🗂️ Modals & Add Inventory Wizard
* Step 1: Material Selection should have a more fitting name, as it is more the method of creating a new item than it is about selecting a material.
* Give material type the ability to auto-complete based on existing types in the database. (Enter should complete, mirror selecting (Up/Down to select) from the filament attributes field).
* Background refreshes on the spool list for a filament can cause a button click to be lost if occurring during a refresh. Should only refresh if changed hash changes, used elsewhere. This only happens on the 2nd item on the list, possibly more.
* Bring in more data from Spoolman into the details modals. It'd be nice to see a purchase link to easily get more of the same filament.
    - Some fields we might not want to bring in. Will need to go over the list of fields to bring in and leave alone.
    - Add a button to the details modal to easily get more of the same filament. (Configure in config file).
    - A confirmation maybe to auto add a new spool of the same filament when the button is clicked. Or an easy button to fill in standard data, but prompt for unique info (price, product link).
* Help button to provide information on how to use a modal, and to try and store information about how things work in the code.
* For existing filaments, advanced search should also be able to accept a Filament from the search function. Seemed to be some sort of bug.
* Extruder and bed temps are missing from the filament side for data entry.
* Maintain the ability to add multiple spools of the same type at the same time.
* Create an assignment tool/system to pair existing/migrated Spoolman IDs directly to physical legacy spools being updated (specifically for bulk-imported identical spools sharing a single legacy ID).


## 🔍 Search, Display & Filtering
* Search by and filter by remaining weight.
* Track unprinted filament samples and create a button/queue like we have for labels.
* Loading spools into buffer from filament definition doesn't load all spool data into card.

## 📍 Location Management & Scanning
* Spools sometimes retain a location assignment in the database.
* Add ability to manually edit and assign location data directly on a spool (fallback for when a barcode scan update gets missed or fails).
* Removing an item from a toolhead/MMU slot should set filabridge slot to empty.
* Ejecting something from a toolhead/MMU slot removes it from the slot as well as marking it as unslotted. It should retain the slot, but be unmarked as deployed.
* The ability to configure a box to change the slot order to go from left to right, or right to left.
* Ability to assign a box slot to a printhead/MMU, so that a scan to that box slot will auto load the spool.
* CR-MDB-1:SLOT:4 is treated as a location not a slot in a box.
* ⚖️ **The "Weigh-Out" Protocol**: Option (toggle or specific "Weigh & Eject" button) to update remaining weight before removing the spool. Important for spools with a QR code on them. This should be done when filabridge reports an error, or perhaps adding a way to update the spools in the ui based off the printer interface data.
* 🔄 **Bulk Moves**: The ability to scan Box A (Source) and Shelf B (Destination) and say "Move EVERYTHING from Box A to Shelf B."
* Shapeshifting QR Codes in more places (like Audit button).
* Locations QR Codes should contain a `LOC:` code, and a `LOC:` code should be used to help identify locations. (Keep existing logic to allow for backwards compatibility, but allow for `LOC:` codes for future items). Legacy Location QR codes (WIthout the LOC: prefix) should have a warning attached in the live activity log.
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