# **Old Things:**
7. Way to resync filabridge & spoolman current state into the command center, for changes done outside of the command center. possibly just incorperate in regular actions, or schedule it?
10. still missing logic for assigning items from a MDB to a toolhead. (QR Code for slot assignments?) {See: 📦 The "Multi-Slot" Logic (MDB/MMU)}

# **New Issues:**
1. Logic behind CORE1-M0/M1 Needs to be refiend. Updating one, or the other will change the current Toolhead0 slot to what ever was last placed into M0 or M1. But with no flag to tell when in MMU mode, it's hard to know what should take priority here... This is assuming that using 5 toolheads to emulate a MMU is the correct answer here for this.
2. May want to make the assignment grid more flexible instead of a 2 by X, perhaps 3 or 4 by X depending on how large. Try to keep as many of the slots available on the screen as we can to prevent scrolling, WITHOUT sacraficing the information being displayed.
3. Cannot seem to move items between slots in a dryerbox. Perhaps using the unassigned section again for this would be good.
4. Find and change any hidden gray text in the UI. (Number of locations in location manager, Slot empty in dryerbox slot assignment screen.)
5. Done QR code in location manager window is giving malformed command error


# **Next Steps Items:**

## **Current:**

1. Working on bugs found during testing of new feature.


## **Future:**
2. ⚖️ The "Weigh-Out" Protocol
The Issue: When you click Eject, the spool is removed, but the weight remains whatever Spoolman last recorded.

The Missing Feature:

An option (perhaps a toggle or a specific "Weigh & Eject" button) to update the remaining weight before removing the spool.

Crucial for keeping inventory accurate after a print job or manual usage.

3. 🏷️ Label Printing Integration
The Context: You uploaded scripts like generate_location_labels.py.

The Missing Feature:

A button in the Hub (e.g., inside the "Manage" window or "Edit Location" modal) to trigger a label print for that specific Spool or Location directly from the UI.

Currently, you have to run those scripts manually on the backend.

4. 🖨️ Direct "Storage-to-Printer" Loading
The Issue: Right now, moving a spool from a Shelf to a Printer is a two-step dance (Eject from Shelf -> Add to Printer).

The Missing Feature:

"Smart Load": If you scan a Spool that is currently on a "Shelf", and then immediately scan a "Printer Toolhead", the system should intelligently Move it (updating Location AND FilaBridge) in one action, without needing to manually clear the old location first.

5. 🔄 Bulk Moves
The Discussion: We briefly touched on moving entire boxes.

The Missing Feature:

The ability to scan Box A (Source) and Shelf B (Destination) and say "Move EVERYTHING from Box A to Shelf B."


# **Overarching issue**
I think we've inadverntaly created 3 levels of logic/complexity here. 1. The physical, Scanning stuff and efficiently Moving it, 2. A UI layer, for debugging, but should only really need to be looked at to confirm things when where you were expecting, and 3, a full on interface that is easier to move spools around than having to use spoolmans lack luster interface.

All 3 of these things are important and have value. And I think this is something that we should table for now, and come back to once we've gotten more of the functionality in place and working.