# **New and Unsorted Features/Bugs**



* Ability to add/customize/change type in the Edit Loction Modal, for creating or editing existing locations. I think we moved this off of a .CSV basede list, and now it generates and stores based on spoolman data? But I'm not sure. Toolhead appears to be missing from this list.

* Better grouping of locations lists data. The encoded id's can sometimes be used to generate a grouping, (anything that starts with CR, is in the Computer room, DR, Dining room, LR, living room etc...)


* A help window that contains at the very least the a cheat sheet for the different XXX: codes and what they mean. (FIL: for filament, LOC: for location, etc.) Will need to hunt through the code for this one.

* "Deposit here" barcode for adding items to a location from the buffer throws an error when scanning, but clicking on it works fine.


* Keeping the screen on when afk, still causes the screen to blank out. Confirmed on laptop, not on desktop.

* Scanning a new spool into a dryer box slot doesn't imidiately unload the currently existing spool. We may want to entirely re think the way the eject process works when replacing one spool out for another. This is mostly a dryer box thing.

* Loading a dryer box, at the very least, slots load with an initial data set, and then i think the 5 second tick goes off, and fills them in completely. Seems to be a difference between what the initial card load does, and the data provided from the 5 second tick. We should probably make the initial card load load the same data as the 5 second tick.

* Adjust filament list and stystem to allow for unassigned filaments to fall back to a room based location, based on the dryerbox location (LR for Living room, CR for Computer room) So that we can avoid the spool instantly going into the unassigned zone. Will need to parent locations to rooms, and allow rooms to have a list of filaments that includes all sub-locations. (Dryerboxes, carts, shelves etc...)

* Filament Edit button? To access the fiament to make changes. (Updating the spool weight, or other attributes.) Might also make sense to add a way to edit the manufacture to add an empty spool weight as well. We would need a way to populate some weights into existing spools, if the spool weight is currently 0. As I don't think spoolman retroactivly updates past spools with a an empty spool weight of 0.

* If a spools remaining weight is 0, suggest, or possibly auto set archived to true. Possibly also move to unassigned location.

* Clicking on scales on the filament card should bring up the scales modal for directly handling all the various way we would want to update weight. (Mostly what's found in the weight section on the edit modal, but including location possibly and archive/unarchive.)

* Modify add inventory wizzard/editor to support Coextruded and Logitudinal options for the colors assigned to a filament. For reference from spoolmans line on this: "Filaments can have multiple colors in two ways: either through coextrusion, like dual-color filaments with consistent multi-colors, or through longitudinal color changes, like gradient filaments that shift colors along the spool."

* Ability to edit filament specific data in some fassion. currently there isn't a way to directly edit a filament that's used as the basis of other spools, without opening a spool.

* No easy way to create a new spool using only the filament display modal. (No clone button, but cloning wouldn't make sense here.)

* A way to display inactive spools in the filament modals spool's list. (Perhaps a toggle or someting to enable showning all spools.) Incase something get set to archive when it shouldn't have.

* Fix spools that don't have a purchase link in the purchase link section of spoolman (custom field I believe.), revert to using the filaments purchase link. If the spool is saved, propigate that data forward. (To fix spools that somehow didn't get updated when we added the purchase link field to spools.)

* Config button, for configuing certain things in the system without having to edit a config file manually in a text editor. (I'm not sure what all we'd want to put here, but it'd be nice to have.)

# **Active Backlog (Organized by Feature Area)**

## 🎨 UI & Theming
* High-Contrast Pop (White Text/colored text + Heavy Black Shadow/or similar color shadowing) - EVERYWHERE. Adaptive High-Contrast Pop (Shadows Only) on colors. Maintain existing colors, but give them a pop appropriate for their color.
* Sometimes the swatch isn't showing the right color I think. Also doesn't handle multi-color spools currently.
* Improve readability for the status line, that includes Location type and Amount of spools (1/x) Assigning a color to full boxes (possibly red or something that works with the theme).

## 🗂️ Modals & Add Inventory Wizard
* Bring in more data from Spoolman into the details modals. It'd be nice to see a purchase link to easily get more of the same filament.
    - Some fields we might not want to bring in. Will need to go over the list of fields to bring in and leave alone.
    - Add a button to the details modal to easily get more of the same filament. (Configure in config file).
    - A confirmation maybe to auto add a new spool of the same filament when the button is clicked. Or an easy button to fill in standard data, but prompt for unique info (price, product link).
* Help button to provide information on how to use a modal, and to try and store information about how things work in the code.
* For existing filaments, advanced search should also be able to accept a Filament from the search function. Seemed to be some sort of bug.
* Maintain the ability to add multiple spools of the same type at the same time.
* Create an assignment tool/system to pair existing/migrated Spoolman IDs directly to physical legacy spools being updated (specifically for bulk-imported identical spools sharing a single legacy ID).

## 🔍 Search, Display & Filtering
* Search by deployment status. Maybe under an advanced search set that is hidden but can be shown, so it doesn't take up a lot of extra space.
* Search by and filter by remaining weight.
* Track unprinted filament samples and create a button/queue like we have for labels.
* Loading spools into buffer from filament definition doesn't load all spool data into card.

## 📍 Location Management & Scanning
* Spools sometimes retain a location assignment in the database.
* Removing an item from a toolhead/MMU slot should set filabridge slot to empty.
* Ejecting something from a toolhead/MMU slot removes it from the slot as well as marking it as unslotted. It should retain the slot, but be unmarked as deployed.
* The ability to configure a box to change the slot order to go from left to right, or right to left.
* Ability to assign a box slot to a printhead/MMU, so that a scan to that box slot will auto load the spool.
* CR-MDB-1:SLOT:4 is treated as a location not a slot in a box.

* 🔄 **Bulk Moves**: The ability to scan Box A (Source) and Shelf B (Destination) and say "Move EVERYTHING from Box A to Shelf B."
* Shapeshifting QR Codes in more places (like Audit button).
* Slots CSV generation seems to put in 2 versions, one with the cleaned name, and one without.
* Slots CSV should include Slot + # (Slot 1, Slot 2, etc) as a field.
* Slot Based QR codes are not sending the scanned item to the slot in the location it's attached to.
* Scanning a storage location (Any, dryerbox, Cart, etc) doesn't assign all items in the buffer to that cart, it requires you to scan the location multiple times in order to assign them all to it.
* Location Manager not syncing status across browser instances?
* Unable to send items to the unassigned location in the location list with a QR code scan.

## 🎟️ Print Queue, Labels & Filament Usage
* Add ability for a scan to update the label printed/filament printed status to true/yes, Spoolman Reprint (Label).
    - Label Printed in Spoolman Spool data can be used to determine if a new Label has been printed.
    - Filaments: Spoolman Reprint field is set to Yes for items that need to have a label reprinted. Null or No mean that it already has a label with the Spoolman ID.
* It's too easy to have multiple legacy spools with no exact ID, where we could be assigning the wrong item... perhaps a pop-up when there could be more than 1 spool attached to the legacy ID, asking the user if they want to see the list of spools, or just reprint a new label.
* Confirmed label print should be displayed somewhere on the card. Perhaps changing the printer icon to a checkmark for confirmed spools.
* Add label print button to filament sample cards.
* Some values in Print Queue are being set to yes, most are null. What is the process for setting them to true?
* Refresh ticks seem to be clearing the print queue? that or refreshes? Search button also broke for some reason.

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

# **New related project to be integrated **

* [Feature] Build Project Color Loadout Add-on -> (See /docs/Project-Color-Loadout/)