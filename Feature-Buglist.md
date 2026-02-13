# **Old Things:**
7. Way to resync filabridge & spoolman current state into the command center, for changes done outside of the command center. possibly just incorperate in regular actions, or schedule it?

# **New Issues:**
1. Logic behind CORE1-M0/M1 Needs to be refiend. Updating one, or the other will change the current Toolhead0 slot to what ever was last placed into M0 or M1. But with no flag to tell when in MMU mode, it's hard to know what should take priority here... This is assuming that using 5 toolheads to emulate a MMU is the correct answer here for this.
2. If legacy barcode has no spools attached to it, UI should warn about this, perhapes give option to add new spool?
3. Spoolman ExternalID is not a visible field to add to the data when viewing it in spoolman. As much as I don't want to duplicate data in the database, being able to see that data in the view lists might be handy. But this is very low priority, and may be achived by other means like inport/export Process or not needed depending on UI/config/features added. We should evaluate this after we've added more features to Command Center.

5. Add unassigned Location in Location List.

7. No support for Unicode on P-touch, need to address in CSV

# **Location Manger Items**
8. Make the slot unassigned QR codes brighter
9. Cannot add buffered items to Single Slot Spaces. (Toolheads Possibly Polymaker Dryerboxes)
# **Print Queue Items**
6. Location Label CSV doesn't seem to generat on the Live server, but does on dev.
10. Spool Details should have a button back to filament details, and filament should have one back to Spool. (But with filament, how do we hand >1 spools)
# **Command Center Items**
1. Filament/spool buffer on command center needs to be persistant acrost all open instances. Same with the Label Print Queue


# **Next Steps Items:**

## **Current:**
Production Functionality Fix list
1. QR codes not scanning into buffer
2. QR Button codes not have enought white space for the scanner to read them.
3. Increase the size of all QR Codes
4. Add functionality to print location Labels (With support for slot based assignments on DryerBox types)
5. add the ability to find filament/swatches with multiple filaments and easily add those to the print queue
6. Fix Location Manager UI Dryer box slot locations not correctly displaying all filament information



## **Future:**
2. ⚖️ The "Weigh-Out" Protocol
The Issue: When you click Eject, the spool is removed, but the weight remains whatever Spoolman last recorded.

The Missing Feature:

An option (perhaps a toggle or a specific "Weigh & Eject" button) to update the remaining weight before removing the spool.

Crucial for keeping inventory accurate after a print job or manual usage.

This is pretty important for spools with a QR code on them. So we may want to tread this one differently, and hash it out better as things evolve.

3. 🏷️ Label Printing Integration
The Context: You uploaded scripts like generate_location_labels.py.

The Missing Feature:

A button in the Hub (e.g., inside the "Manage" window or "Edit Location" modal) to trigger a label print for that specific Spool or Location directly from the UI.

Currently, you have to run those scripts manually on the backend.

5. 🔄 Bulk Moves
The Discussion: We briefly touched on moving entire boxes.

The Missing Feature:

The ability to scan Box A (Source) and Shelf B (Destination) and say "Move EVERYTHING from Box A to Shelf B."

6. Shapeshifting QR Codes in more places.

7. Refactor dashboard to be more modular if possible, and reduce token size/context requirements for some modifications.


# **New/Future Features **
1. High-Contrast Pop (White Text + Heavy Black Shadow) - EVERYWHERE ()

2. Maybe we should probably figure out a way to set up a dev version for Spoolman and filabridge. So that I can test in dev, and maybe start using the prod version for actual prod activities, without messing up existing configurations in the database. This would probably be highly reliant on being able to sync data from Prod to test. We will probably have to build a list of apps or code to handling this, like the Import/Export feature. But also some sort of configuration UI within Command Center, for setting up the config files. We should probably refactor out hard coded configs that are bound to my instance and gear it more twords customzation, so that if others want to use this they can.

3. On the front of 2, make as much of command Center user configuarble as possible, using UI elements and a config inport/export feature.

4. Refactoring setup code to be dynamic. For existing instances when someone is installing command center for the first time on an existing spoolman server, we just add the needed data fields that command center needs/uses. But on brand new installs (with no existing data) We can maintain existing code to get it started, or leverage the inport/export data for this in some way.

# **Overarching issue**
I think we've inadverntaly created 3 levels of logic/complexity here. 1. The physical, Scanning stuff and efficiently Moving it, 2. A UI layer, for debugging, but should only really need to be looked at to confirm things when where you were expecting, and 3, a full on interface that is easier to move spools around than having to use spoolmans lack luster interface.

All 3 of these things are important and have value. And I think this is something that we should table for now, and come back to once we've gotten more of the functionality in place and working.