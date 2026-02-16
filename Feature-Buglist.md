# **New Issues:**


# ** General **
* High-Contrast Pop (White Text/colored text + Heavy Black Shadow/or similar color shadowning) - EVERYWHERE () If we have color, I'd like to maintain it, but just give it that bit of pop use a compatible color. I don't wish to change every item of text to Black/White, so maintain existing colors, but give them a pop approperiate for there color.
* Set the Scanner Paused state to eat the first mouse click on it to give the window focus if possible, to prevent accidental clicking on unentended items.
* Black filaments need a better way to show border or a better gradiant in the color
* Smart assign (I think thats what we called it) isn't working for non-dryerbox locations. I have to scan the location multiple times to unload the buffer into it, instead of it realizing it's a mass storage locaiton and just assigning it to the location.
* Doens't seem to handle 4+ colors in a swatch for generating gradiant 
* Loading spools into buffer from filament definition doesn't load all spool data into card.
* Undo should put back into buffer if it came from buffer.
* Slots CSV generation seems to put in 2 versions, one with the cleaned name, and one without (Effectivly doubling the line count.)
* Slots CSV should include Slot + # (Slot 1, Slot 2, etc)


# **Location Manger Items**
Ejecting from slot is not soing as being ejected (setting slot to empty) Is this bug, or design? Possibly an ejecting last slot item bug? Seems to happen on slots and unassigned intems in the box.

# **Print Queue Items**
1. No support for Unicode on P-touch, need to address in CSV (🦝 XL -> Raccoon XL)

# **Command Center Items**
1. Add ability for an scan to update the label printed/filament printed status to true/yes, Spoolman Reprint (Label)
2. Set it so that the screen don't sleep.
3. Clicking on the Spoolman or Filabridge Status Buttons should opening there respective apps.

# **Details (Filament/Spool) Modal **
1. Sometimes the swatch isn't showing the right color I think. Also Doesn't handle multi-color spools currently.

# **Location List**
1. Add unassigned Location in Location List.
2. Fix Gray text on Gray background and X close button.
3. Fix first line (Headers scrolling with the window)
4. Improve readibility for the status line, that includes Location type and Amount of spools (1/x) Assigning a color to full boxes (possibly red or something that works with the theme)
    - High-Contrast Pop (White Text + Heavy Black Shadow) - EVERYWHERE ()

# **Next Steps Items:**

## **Current:**
Production Functionality Fix list
6. Fix Location Manager UI Dryer box slot locations not correctly displaying all filament information



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

6. Shapeshifting QR Codes in more places.

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