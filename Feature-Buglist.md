# **Old Things:**
3. The live activity list box under the buffer list, should just also print that the item is in the buffer alreaedy, instead of just looking like it's just continuing to add the same item over and over again. Keep the toast, but last update should also reflect that it was already scanned into the buffer.
4. undo when working with a active buffer/container should remove the last item added
5. toasts hould be a bit larger, and more prominate, maybe center of the screen?
6. items added to a toolhead are not being added to the toolhead in filabridge
7. Way to resync filabridge & spoolman current state into the command center, for changes done outside of the command center. possibly just incorperate in regular actions, or schedule it?
8. still not prompting for MDB container location when assigning to a multislot dryer box
10. still missing logic for assigning items from a MDB to a toolhead. (QR Code for slot assignments?) {See: 📦 The "Multi-Slot" Logic (MDB/MMU)}

# **New Issues:**
1. Logic behind CORE1-M0/M1 Needs to be refiend. Updating one, or the other will change the current Toolhead0 slot to what ever was last placed into M0 or M1. But with no flag to tell when in MMU mode, it's hard to know what should take priority here... This is assuming that using 5 toolheads to emulate a MMU is the correct answer here for this.
2. May want to make the assignment grid more flexible instead of a 2 by X, perhaps 3 or 4 by X depending on how large. Try to keep as many of the slots available on the screen as we can to prevent scrolling, WITHOUT sacraficing the information being displayed.
3. Screen not in focus waring doesn't seem to exist anymore or got disabled? Needs to be re-added back in.


# **Next Steps Items:**

## **Current:**
1. 📦 The "Multi-Slot" Logic (MDB/MMU)
The Issue: Right now, the Hub treats every location like a generic "Bucket." If you add 3 spools to PM-DB-1 (a 4-slot dryer), it just lists them. It doesn't know which slot (1, 2, 3, or 4) they are in.

The Missing Feature:

When adding to a location defined as a "Dryer Box" or "MMU", the UI should ask for a Slot Number (or auto-assign the first empty one).

Visualizing "Slot 1: Full, Slot 2: Empty" instead of just a list.

## 📋 The v106.0 Verification Checklist
1. 📦 The "Grid Trigger" Test
The Goal: Verify that the UI switches to "Grid Mode" only when appropriate.
Action:
Edit a location (e.g., PM-DB-1).
Set Type to Dryer Box (or MMU Slot).
Set Max Spools to 4.
Save.

Click "Manage" on that location.

✅ Pass: You see a 2x2 Grid of buttons labeled "1", "2", "3", "4".

❌ Fail: You still see the old vertical list.

2. 👆 The "Tap-to-Fill" Test
The Goal: Assign a spool to a specific slot using the touchscreen.

Action:

Open the "Manage" grid for PM-DB-1.

Scan/Type a Spool ID (e.g., #105) to add it to the Buffer.

Tap the button for Slot 1 (which should say "EMPTY").

✅ Pass:

The spool moves from the buffer to Slot 1.

The Slot 1 button turns Dark Grey/Blue and displays the spool info (Color/Brand).

The buffer clears.

❌ Fail: Nothing happens, or it adds it to the list without a slot number.

3. ⌨️ The "Scan-to-Slot" Test
The Goal: Verify that scanning a "Slot Command" works like a physical button press.

Action:

Scan a Spool (e.g., #126) into the buffer.

Type/Scan this text command into the input box: CMD:SLOT:2

Press Enter.

✅ Pass: Spool #126 instantly snaps into Slot 2 on the screen.

4. ⏏️ The "Slot Eject" Test
The Goal: Verify specific slot clearing.

Action:

Tap the Filled Slot 1 button (the one with Spool #105).

Confirm the prompt: "Eject spool #105?".

✅ Pass:

Spool #105 is removed.

Slot 1 reverts to "EMPTY".

(Bonus) If this was a Printer Location, verify the FilaBridge log says "Unloaded".

5. 🗄️ Persistence Check
The Goal: Ensure Spoolman actually saved the data.

Action:

Close the Manage window.

Refresh the Page (F5).

Open "Manage" on PM-DB-1 again.

✅ Pass: The spools are still in the exact slots you put them in.

❌ Fail: They are there, but the slots are scrambled or missing.

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