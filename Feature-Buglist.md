# **New Issues:**


# ** General **
* High-Contrast Pop (White Text/colored text + Heavy Black Shadow/or similar color shadowning) - EVERYWHERE () If we have color, I'd like to maintain it, but just give it that bit of pop use a compatible color. I don't wish to change every item of text to Black/White, so maintain existing colors, but give them a pop approperiate for there color.
* Add ability for a scan to update the label printed/filament printed status to true/yes, Spoolman Reprint (Label) (On hold needs better plan of attack)
    - Label Printed in Spoolman Spool data can be used to determin if a new (Spoolman Based ID) Label has been printed.
    - Filaments: Spoolman Reprint field/extra data, is set to Yes for all items that need to have a label reprinted with the new Spoolman ID. Null or No, mean that it already has a label with the spoolman ID.
      For Label printed field/extra data, if it has a legacy ID, this will probably be Yes, if it's a no, then it's new, and a label needs to be printed.
* Find spool functionality. Basically make finding a spool/filament easier than using spoolman. Better support for color searches.
* Its too easy to have multiple legacy spools with no exact id, where we could be assigning the wrong item, though in those cases we should probably just reprint new labels. Perhaps a pop up when there could be more than 1 spool attached to the legacy id, asking the user if they want to see the list of spools, or just reprint a new label.


# **New Spool/Filament Creation**
* Attempt to combine the creation of a new spool and filament into one step. 
* Continue to support spoolmans ability to pull data from the vender up to filament (Empty Weight), and from Filament to Spool (Empty Spool Weight, price, etc.)
* Add the ability to configure which extra fieds should be bound and propagated to the other type of item. (Filament <-> Spool) (I believe we have a purchase link that would be an example of this, where it's set on the filament, but not on the spool.)
* Maintain the ability to add multiple spools of the same type at the same time. (THis is reperesented by the number box in spoolman next to add, allowing you to add more than one spool of the same filament at the same time)
* Support clone feature for Spools, to auto populate an existing spool. 
* Figure out a way to fill in density for filaments. This data isn't alwasy availabe from the vender, so we may need to use a default or calculate it somehow based on filament type.
* Continue to support Spoolman's "Import from External" feature for filaments, but also empower it to use other sites if possible. The list of sites that come to mind are as follows:
    - https://3dfilamentprofiles.com/
    - https://github.com/OpenFilamentCollective/open-filament-database
    - Prusament spool specific data links (Which are usually a QR code that links to a spools manufacturing data.)
    - Purchase emails, or Amazon/Vendor product pages.
    - Other sites I might not be aware of and which we can evaluate later for this data.
    - Support for Open Print Tags (Initialize,Read, and Write) (https://github.com/OpenPrintTag/openprinttag-specification)

# **Location Manger Items**
* The ability to configure a box to change the slot order to go from left to right, or right to left. (This would be a per box setting)
* Ability to assigne a box slot to a printhead/mmu, so that a scan to that box slot will auto load the spool into the printhead/mmu. (This would be a per box setting)
    - I think this exists, but need to confirm in code.


# **Print Queue Items**
* Need a way to add newly created Filament/Spools to the print queue. This chould be based on one of many print flags in the spoolman database. (Both buitl in and "extra Field" type data we've added to spoolman.)
* Needs a window/modal that lists all the spools/filaments missing a confirmed label printing (By database check box)
* Data in the window should be filterable or sortable. So that If I want oldest first to work on back log, or Newest first if I want to work on something I've just added.
* Things sent to the print queue should be flagged for printing in the database, so that they can be placed and tracked in a speprate list, so that once they are printed, it can be flagged as printed and updated as such in the database. (Database = Spoolman)


# **Command Center Items**

# **Details (Filament/Spool) Modal **
* Bring in more data from spoolman into the details modals. It be nice to see at purchase link to easily get more of the same filament.
    - Some fields we might not want to bring in. Will need to go over the list of fields to bring in. And to leave alone.
    - Add a button to the details modal to easily get more of the same filament. (This would be a custom button that we can configure in the config file, so that it can be different for different filaments.)
    - A confirmation maybe to auto add a new spool of the same filament to the database when the button is clicked if the user buys more filament. Or an easy button to add a new spool, that fills in most of the standard data, but stuff that would be unique to the new spool, like price, product link (if it happens to be one that provides a good link like prusament ones)
*Add spool button on the list of spools in the filament details modal that links you to the details of the spool.


# **Location List**


# **Next Steps Items:**

## **Current:**


## **Future:**
2. ⚖️ The "Weigh-Out" Protocol
The Issue: When you click Eject, the spool is removed, but the weight remains whatever Spoolman last recorded.

The Missing Feature:

An option (perhaps a toggle or a specific "Weigh & Eject" button) to update the remaining weight before removing the spool.

Crucial for keeping inventory accurate after a print job or manual usage.

This is pretty important for spools with a QR code on them. So we may want to tread this one differently, and hash it out better as things evolve.

5. 🔄 Bulk Moves
The Discussion: We briefly touched on moving entire boxes.

The Missing Feature:

The ability to scan Box A (Source) and Shelf B (Destination) and say "Move EVERYTHING from Box A to Shelf B."

6. Shapeshifting QR Codes in more places. (like Audit button)

7. Refactor dashboard to be more modular if possible, and reduce token size/context requirements for some modifications.

# **On Hold **
1. Standardize the size of all QR codes to match that of the sizes used on the command center. (Audit, eject, drop, etc)
2. If legacy barcode has no spools attached to it, UI should warn about this, perhapes give option to add new spool?
3. Spoolman ExternalID is not a visible field to add to the data when viewing it in spoolman. As much as I don't want to duplicate data in the database, being able to see that data in the view lists might be handy. But this is very low priority, and may be achived by other means like inport/export Process or not needed depending on UI/config/features added. We should evaluate this after we've added more features to Command Center.


# **New/Future Features **
1. High-Contrast Pop (White Text + Heavy Black Shadow) - EVERYWHERE ()
    - Adaptive High-Contrast Pop (Shadows Only) on colors

2. Maybe we should probably figure out a way to set up a dev version for Spoolman and filabridge. So that I can test in dev, and maybe start using the prod version for actual prod activities, without messing up existing configurations in the database. This would probably be highly reliant on being able to sync data from Prod to test. We will probably have to build a list of apps or code to handling this, like the Import/Export feature. But also some sort of configuration UI within Command Center, for setting up the config files. We should probably refactor out hard coded configs that are bound to my instance and gear it more twords customzation, so that if others want to use this they can.

3. On the front of 2, make as much of command Center user configuarble as possible, using UI elements and a config inport/export feature.


# **Overarching issue**
I think we've inadverntaly created 3 levels of logic/complexity here. 1. The physical, Scanning stuff and efficiently Moving it, 2. A UI layer, for debugging, but should only really need to be looked at to confirm things when where you were expecting, and 3, a full on interface that is easier to move spools around than having to use spoolmans lack luster interface.

All 3 of these things are important and have value. And I think this is something that we should table for now, and come back to once we've gotten more of the functionality in place and working.

# **I THINK there done?**
Production Functionality Fix list
* Fix Location Manager UI Dryer box slot locations not correctly displaying all filament information

# **Done**
* Sometimes the swatch isn't showing the right color I think. Also Doesn't handle multi-color spools currently.
* Loading spools into buffer from filament definition doesn't load all spool data into card.
* Side Quest: Spool card coloring system doens't seem to handle 4+ colors in a swatch for generating gradiant
* Locations QR Codes should contain a LOC: code, and a LOC: code should be used to help identify locations. (Too many manual entry items accidently turn into locations by accident on misstyping)
    - Pehraps we just refactor this code an check its logic.
    - Keep existing logic to allow for backwords compatibility, but allow for LOC: codes for future items.
* Slots CSV generation seems to put in 2 versions, one with the cleaned name, and one without (Effectivly doubling the line count.)
* Slots CSV should include Slot + # (Slot 1, Slot 2, etc) as a field
* Add unassigned Location in Location List.
* Fix Gray text on Gray background and X close button.
* Fix first line (Headers scrolling with the window)
* Improve readibility for the status line, that includes Location type and Amount of spools (1/x) Assigning a color to full boxes (possibly red or something that works with the theme)
    - High-Contrast Pop (White Text + Heavy Black Shadow) - EVERYWHERE ()
* Added color coding to the badges on the location (Location Type)
* Added color indicate of dryerbox/tool fullness (1/1 Green, 2/1 Red, < Max White)
* Ejecting from slot is not showing as being ejected by setting slot to empty. Is this bug, or design? Possibly an ejecting last slot item bug? Seems to happen on slots and unassigned items in the box.
* Trash button, which I think doese the same thing as ejecting, also doesn't seem to work here, for spools that are assigned to the location, but doesn't have a slot attached to them.
* Slot Based QR codes are not sending the scanned item to the slot in the location it's attached to. This might be because we added the LOC: indicater, and it might just not be parcing correctly now.
    - Currently items assigned using a slot QR code "LOC:CR-MDB-1:SLOT:4" are being stored in spoolman as a "CR-MDB-1:SLOT:4" location
        * Could be advantagous to have the slots have there own loation in Spoolman. But I don't have a direct use case currently for it. Perhapes you might have one.
* Scanning a storage location (Any, dryerbox, Cart, etc) doesn't assigne all items in the buffer to that cart, it requires you to scan the location multiple times in order to assign them all to it.
    - This should probably be the default for non-drier boxes.
* Location Manager not syncing status across browser instances?
* COME BACK AND ADDRESS ISSUES IN setup_fields.py (Non destructive of existing choice fields, check error codes)
* Fix backend logging to not repeate this filling the logs with non useful data. 
    - 2026-02-14 06:01:08,706 - INFO - ✅ Loaded Prod Config: /config.json
* Fixed Print Queue displaying "No Loc" for all spools.
* Added "Send to Print Queue" button for individual spools inside the Filament Details popup.
* Refactored Location DB to use JSON config instead of CSV, added native sync for Spoolman Location API, and built automated tests.
* Fixed Undo Buffer Restoration to correctly recall spools to the buffer and reversed Toolhead Ejection cascades.
* Fixed swatch circles in the "Live Activity" Dashboard log pane to accurately display CSS conic gradients mathematically divided for multi-color filament spools.
* Implemented background polling for Filabridge `GET /api/print-errors` to expose `gcode` parsing errors in the Live Activity log.
* Engineered a native CSS physical shield inside `scripts.html` to consume hardware `mousedown`/`click` wake-up hits natively when the Scanner Pauses, preventing accidental button triggers.
* Set it so that the screen don't sleep. (Needs to be tested on laptop)
    - Doesn't seem to work on Laptop
* Eject should auto disable if we move off of the command screen to anyother screen or modal
* Black filaments need a better way to show border or a better gradiant in the color
* Add background refreshing used in Location Manger, etc... to update spool text (update weight other data)
* Need to add a routine to clean up the logs after a while. We don't have that currently, and I'm sure things have gotten out of hand on production.
* Refactoring setup code to be dynamic. For existing instances when someone is installing command center for the first time on an existing spoolman server, we just add the needed data fields that command center needs/uses. But on brand new installs (with no existing data) We can maintain existing code to get it started, or leverage the inport/export data for this in some way.
* Spools might need to have a text field added to store the product data (Prusament: https://prusament.com/spool/17705/5b1a183b26/) as this is more spool level data, than filament level data.
* Unable to send items to the unassigned location in the location list with a QR code scan.