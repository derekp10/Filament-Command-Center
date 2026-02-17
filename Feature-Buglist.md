# **New Issues:**


# ** General **
* High-Contrast Pop (White Text/colored text + Heavy Black Shadow/or similar color shadowning) - EVERYWHERE () If we have color, I'd like to maintain it, but just give it that bit of pop use a compatible color. I don't wish to change every item of text to Black/White, so maintain existing colors, but give them a pop approperiate for there color.
* Smart assign (I think thats what we called it) isn't working for non-dryerbox locations. I have to scan the location multiple times to unload the buffer into it, instead of it realizing it's a mass storage locaiton and just assigning it to the location. Can't recall if this was a design choice, or if it's a bug.
* Add ability for an scan to update the label printed/filament printed status to true/yes, Spoolman Reprint (Label) (On hold needs better plan of attack)
    - Label Printed in Spoolman Spool data can be used to determin if a new (Spoolman Based ID) Label has been printed.
* Fix backend logging to not repeate this filling the logs with non useful data. 
    - 2026-02-14 06:01:08,706 - INFO - ✅ Loaded Prod Config: /config.json
* Find spool functionality. Basically make finding a spool/filament easier than using spoolman. Better support for color searches.




# **Location Manger Items**
* Ejecting from slot is not showing as being ejected by setting slot to empty. Is this bug, or design? Possibly an ejecting last slot item bug? Seems to happen on slots and unassigned items in the box.
* Trash button, which I think doese the same thing as ejecting, also doesn't seem to work here.
* Slot Based QR codes are not sending the scanned item to the slot in the location it's attached to. This might be because we added the LOC: indicater, and it might just not be parcing correctly now.
    - Could be advantagous to have the slots have there own loation in Spoolman.
    - Definitely need to support loading locations from Spoolman, but perhaps store in a config the information about the location, and not rely on the Locations.csv file as much.

# **Print Queue Items**
* For filament Queue, the spools in the list for that filament list No Loc for all items, even the ones with a loc. This needs to be fixed.


# **Command Center Items**
* Set it so that the screen don't sleep. (Needs to be tested on laptop)
    - Doesn't seem to work on Laptop
* Undo should put back into buffer if it came from buffer.
* Eject should auto disable if we move off of the command screen to anyother screen or modal
* Fix swatch circles in "Live Activity" window/pane to work with multi-color filament/spools.
* Add the ability to have Command Center Notify if Filabridge had an issue reading data from printer for spool weight update, so user can see without having to open filabridge.
* Set the Scanner Paused state to eat the first mouse click on it to give the window focus if possible, to prevent accidental clicking on unentended items.
* Black filaments need a better way to show border or a better gradiant in the color


# **Details (Filament/Spool) Modal **


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

6. Shapeshifting QR Codes in more places. (Audit button)

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

4. Refactoring setup code to be dynamic. For existing instances when someone is installing command center for the first time on an existing spoolman server, we just add the needed data fields that command center needs/uses. But on brand new installs (with no existing data) We can maintain existing code to get it started, or leverage the inport/export data for this in some way.

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