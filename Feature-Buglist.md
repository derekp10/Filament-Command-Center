3. The live activity list box under the buffer list, should just also print that the item is in the buffer alreaedy, instead of just looking like it's just continuing to add the same item over and over again. Keep the toast, but last update should also reflect that it was already scanned into the buffer.
4. undo when working with a active buffer/container should remove the last item added
5. toasts hould be a bit larger, and more prominate, maybe center of the screen?
6. items added to a toolhead are not being added to the toolhead in filabridge
7. Way to resync filabridge & spoolman current state into the command center, for changes done outside of the command center. possibly just incorperate in regular actions, or schedule it?
8. still not prompting for MDB container location when assigning to a multislot dryer box
10. still missing logic for assigning items from a MDB to a toolhead. (QR Code for slot assignments?)

1. 📦 The "Multi-Slot" Logic (MDB/MMU)
The Issue: Right now, the Hub treats every location like a generic "Bucket." If you add 3 spools to PM-DB-1 (a 4-slot dryer), it just lists them. It doesn't know which slot (1, 2, 3, or 4) they are in.

The Missing Feature:

When adding to a location defined as a "Dryer Box" or "MMU", the UI should ask for a Slot Number (or auto-assign the first empty one).

Visualizing "Slot 1: Full, Slot 2: Empty" instead of just a list.

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