# **New and Unsorted Features/Bugs**

* A help window that contains at the very least the a cheat sheet for the different XXX: codes and what they mean. (FIL: for filament, LOC: for location, etc.) Will need to hunt through the code for this one.
* Keeping the screen on when afk, still causes the screen to blank out. Confirmed on laptop, not on desktop.
* Scanning a new spool into a dryer box slot doesn't imidiately unload the currently existing spool. We may want to entirely re think the way the eject process works when replacing one spool out for another. This is mostly a dryer box thing.
* Loading a dryer box, at the very least, slots load with an initial data set, and then i think the 5 second tick goes off, and fills them in completely. Seems to be a difference between what the initial card load does, and the data provided from the 5 second tick. We should probably make the initial card load load the same data as the 5 second tick.
* Filament Edit button? To access the fiament to make changes. (Updating the spool weight, or other attributes.) Might also make sense to add a way to edit the manufacture to add an empty spool weight as well. We would need a way to populate some weights into existing spools, if the spool weight is currently 0. As I don't think spoolman retroactivly updates past spools with a an empty spool weight of 0.
* If a spools remaining weight is 0, suggest, or possibly auto set archived to true. Possibly also move to unassigned location.

* Ability to edit filament specific data inside Filament command center. Currently there isn't a way to directly edit a filament that's used as the basis of other spools, without opening a spool. Some sort of edit workflow for chaing data directly related to filaments.

* Config button, for configuing certain things in the system without having to edit a config file manually in a text editor. (I'm not sure what all we'd want to put here, but it'd be nice to have.)

* In location manager, if an item is added to a loction that has slots, and there is a free slot, auto assign the item into that free slot. (If there are multiple free slots, fill the first empty one.)

* I know we fixed it for scanning items, but hand typed id's into the command center's main page can sometimes add an item, that then gets imidiately removed on backend refresh. We need to fix this from happening when loading items without the use of a barcode. (Basically bring the protections we recently added to barcode scans reguarding this issue, to also preserve manual entries too.)
* Fix getting lagacy location scann errors with barcodes generated as part of the UI. All barcodes should use there proper prefex and be displayed using the current standards defined. I shouldn't see a lagacy barcode error when using the deploy QR code on a Manage Location window.
* Review and unify update logic across the program, we have to many versions of update that keep getting orphined, or cause problems later on when they aren't included in a recent design change. We need to have a discussion on how best to fix this, so I want to have an implementation plan in place to iterate off of.
* Figure out why playright can't be run or is not installed on the local docker if that is the issue, otherwise find out if we need to add it to dev, and if needed add it to live/prod if it makes sense.

* Filabridge status light is still blinking on and of, just more eraticly now. Need to look into this further.

* Force location modal needs to be able to work with keyboard inputs, in that Up/down arrow move up and down the list. Enter selects the item, and Escape closes the modal. Focus should also start in the text box, so user doesn't have to click it to begin typing.

* Check to make sure that when a new filament barcode is scanned, that the proper database fields are updated to mark the filament as labeled, so it doesn't appear in the Backlog queue. I scanned on e but didn't see a message in the Live Activity log. Needs label print for (FIL:58) lists as null, don't know if this was because it was blank in the spoolman UI, because this is an old filament physical swatch.

* Check to see if changes to spool card gradint/coextredud color modificaitons were also applied to the Filament cards. (They should have been, this is supposed to be a unified code set for this type of item.)

* Double archive Badge. I want to keep one version over the other. The one that has the shadow backdrop and is on the same line as the color name is the one I like better. We need to move that one down to where the other one is to replace it, and then remove it from the color line. This may mean we need to look into how the cards display archived in all there various versions we have.

* Adding filament to an archived filament should automatically unarchive the filament.

* Add a cleaner easier way to see what filaments are on a printer, with out having to drill down into location list, and location manager to see them.

* Ejecting a fillament while in the command center main menu buffer, doesn't clear the deployed status of the spool.

* We either need a way to detect if MMU mode is one. Or change how M0 & M1 work for weight deductions. I did a test with a filament in both M0 and M1, and it deducted value from both I think. I'm not sure on this as I didn't mark down how much was in M1 before the test. But we shouldn't have seen any deduction from M0. Perhaps we just bind the two together, where no matter what mode M1 is alwasy either the first MMU slot or for when the mmu is disabled and the filamentjust direct feeds into the toolhead.

* Smart eject doesn't seem to be called when a new spool is assigned to a toolhead that already has a spool assigned to it. (CoreOne+ Noticed issue)

* Clicking on the edit button with a spool in a location (not slotted), dismissing the edit spool modal causes the details modal to pop up. Details should only pop up when the edit button was used from the details window. We need to work on this better to make the windows work right. A recent change is causing this bug. Adding the re-opening of the details modal after exiting edit i believe, is not considering the sorce of the edit click. We should probably look over the whole modal system because i thought we were using a better system than this that was more dynamic.

* Eject button on unslotted location items doesn't actully remove from list, and pops up a modal/window for a second to confirm setting it to unassinged, but dissipears. The item should just be removed from the list, and set to it's last location. if it's last location is unknow, set to unassinged, or propt user about it, or warn in live activity.

* An unknow issue caused the frontend to lock up, causing it to no longer update to take barcodes. A hard refresh (Control shift R and Control F5) fixed it. We need to figure out what caused this, and fix it so it doesn't happen again. This could be related to the eject button issue above. Also seemed to have cause updates to filabridge to stop until the front end was refreshed.

* Spool cards displayed on the filament command center's main menu buffer, do not display there locations. This needs to be added so the user doesn't need to bring up the display modal to see it's current location.

* It appears that while I was editing a spool's filament data that was sloted into a print head, saving caused it to be removed. We need to check to see why that is. Or the filament's location was listed the correct location, but it the location was regestring as empty 0/1 on location list modal, and nothing assigned inside the location manager modal.

* Currently using temp (Bed, Nozzle/Toolhead) in spoolman to store the low tempratures, but I really think we need to track the high tempratures for those values. Will need to look into the code and see what we can do to fix this. Will need to add extra fields for this on the filament side, and treat them not as custom fields in the ui placement, but as actual fields. Will need to reinfource the location of those fieds in the UI as custom fields have a tendency to re-order themselves. I have a line item for hammering down the field locations so they don't move around eveythime a custom entry is added into an extra field, so we should probably include this in that as well.


# **Active Backlog (Organized by Feature Area)**

## 🎨 UI & Theming
* Refactor the longer "strip" cards used in the Location Manager window. Merge the horizontal layout with modern grid card features without cramping the text or making the button layout look weird.
* High-Contrast Pop (White Text/colored text + Heavy Black Shadow/or similar color shadowing) - EVERYWHERE. Adaptive High-Contrast Pop (Shadows Only) on colors. Maintain existing colors, but give them a pop appropriate for their color.
* Theres a little animation and modal that appears when you add a new Slicer Profile in the Add/edit enventory wizzard. Its so nifty I want this used in other places. (I'm not sure if this is a sweetalert2 thing, or if we implemented ourselves.)


## 🗂️ Modals & Add Inventory Wizard
* Help button to provide information on how to use a modal, and to try and store information about how things work in the code.
* For existing filaments, advanced search should also be able to accept a Filament from the search function. Seemed to be some sort of bug.
* Maintain the ability to add multiple spools of the same type at the same time.
* Create an assignment tool/system to pair existing/migrated Spoolman IDs directly to physical legacy spools being updated (specifically for bulk-imported identical spools sharing a single legacy ID).
* For the add/edit inventory wizzard modal, make the location searchable like in the filament/spool display modal's version.
* We now have 2 purchase links for spools, one that virtually links to the filament value, the other is on it's own but part of the spool. We need to look into the code here and pair down to only one fied if possible, but retain functionality. Linked field enharrenting the value possibly. Or we just fix the code so it looks at what is available and takes the one that exists, with a preference for the spool specific one, which may be more uptodate, or specific for the pricing. One of them, the first one on the page, seems to not clear between usanges.
* Filament ID and Spool ID should be visible on the edit version of the add inventory wizzard, so that a user can easily see what one they are working on.
* Vendor should be searchable with keyboard shortcuts and a list that doesn't take up the full screen.
* Adding a new slicer profile should automatically add that profile to the current filament being edited.
* Spoolmans field ordering bug causing fields in the Add/Edit enventory window to move if a custom field is modified or has new items added to it. Need to look at locking down the order of things.

## 🔍 Search, Display & Filtering
* Search by deployment status. Maybe under an advanced search set that is hidden but can be shown, so it doesn't take up a lot of extra space.
* Search by and filter by remaining weight.



## 📍 Location Management & Scanning
* Refactor the entire location managment system from the ground up. It's currently being a bit too complicated, and I think it can be cleaned up a bit if we just rethink the flow of this process. We've bolted a lot of stuff onto this system, and the has caused it to become a bit too cumbersome to both code and work with. I think we need to build in a better system for linking locations and device/boxes/storage things. We need to have a discussion on how best to fix this, so I want to have an implementation plan in place to iterate off of.


* The ability to configure a box to change the slot order to go from left to right, or right to left.
* Ability to assign a box slot to a printhead/MMU, so that a scan to that box slot will auto load the spool.
* CR-MDB-1:SLOT:4 is treated as a location not a slot in a box. (I believe this was fixed, we need to check on it.)

* 🔄 **Bulk Moves**: The ability to scan Box A (Source) and Shelf B (Destination) and say "Move EVERYTHING from Box A to Shelf B."
* Shapeshifting QR Codes in more places (like Audit button).

* Slot Based QR codes are not sending the scanned item to the slot in the location it's attached to.
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

## Stuff to watch ##

# ** Filabridge Error Recovery **
* Keep an eye on filabridge errors and note the type of recovery method used to fill in the missing weight data. (Fast-Fetch or RAM-Fetch) To see if Fast-Fetch (Based on a HTTP Range request of a file.) works.

# **New related project to be integrated **

* [Feature] Build Project Color Loadout Add-on -> (See /docs/Project-Color-Loadout/)