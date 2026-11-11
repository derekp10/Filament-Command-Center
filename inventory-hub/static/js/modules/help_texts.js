// ---------------------------------------------------------------------------
// In-app help (Group 55.3): what each daily dialog is for, in plain words.
//
// One window.registerHelp({...}) per dialog (shortcuts_registry.js draws it in the
// shortcut window, from the ? button in the dialog's header, or for the ? key
// while the dialog is on top):
//   key       the dialog's help key; its ? button says data-fcc-help="<key>".
//   title     the dialog's name, as a person sees it.
//   match     what the dialog is on screen: {modal: 'id'}, {overlay: 'id' or [...]}
//             or {overlayHas: 'selector'} (see shortcuts_registry.js).
//   lines     a few plain sentences: what it is for, what its main buttons do,
//             which scans work while it is open.
//   scopes    the shortcut scopes whose keys are listed under the lines.
//   sections  parts shown only while their `when` selector is on screen.
//
// Rules for the words (CLAUDE.md): plain words for the person using FCC, never
// code; made-up examples only (SHELF-1, DRYBOX-1, PRINTER-1, HEAD-1, #42), never
// the owner's own ids or names; no "|" (the toolhead-Type canary reads it); and
// only what the code does: each line was checked against it (Group 55), so a
// change to a dialog's buttons, keys or scans changes its lines here too.
// tests/test_help_texts_55.py checks the form.
// ---------------------------------------------------------------------------

(function () {
    const help = window.registerHelp;
    if (typeof help !== 'function') return;

    help({
        key: 'location-list',
        title: 'Location List',
        match: { modal: 'locMgrModal' },
        lines: [
            'Every place FCC knows, from rooms and shelves to dryer boxes, printers and their toolheads, with how many spools each holds.',
            'Manage opens a place\'s own window. On a row, 📱 QR shows its label code, ➕ adds a place inside it, ✏️ edits it, and 🗑️ deletes it after a question that says where its spools go (to Unassigned).',
            'Unassigned, always the first row, holds the spools with no place; Unknown, the last, the ones FCC has lost track of.',
            '➕ Add Location makes a new place, 📌 Pin Printers keeps the printers at the top, and 🧺 Loose spools lists the spools filed on a room or a cart itself.',
            'Click a column heading to sort by it. Sorted by ID the list is a tree, and the - beside a place folds away what is inside it.',
            'Scans work as on the dashboard: a place\'s label puts your buffered spools there (a dryer box with slots asks which slot, a printer which toolhead).',
            'With your buffer empty, a one-spool place\'s label (a toolhead, a single dryer) hands you its spool, and any other place\'s label opens its window.',
            'A yellow ? in the Status column means Spoolman didn\'t answer, so that place\'s spools weren\'t counted just now.',
        ],
    });

    help({
        key: 'location-window',
        title: 'Location window',
        match: { modal: 'manageModal', overlay: ['fcc-quickswap-confirm-overlay'] },
        lines: [
            'One place and its spools: a box with several slots as its numbered slots, any other place as a list.',
            'Scan a spool and it waits under READY TO SLOT (◀ PREV and NEXT ▶ pick another from your buffer). Click an empty slot, or ⬇️ DEPOSIT HERE, to put it here; a slot that feeds a toolhead loads it onto that toolhead too. A full slot asks first.',
            'A click on ⬇️ DEPOSIT HERE puts only the spool shown; scanning its QR (this place\'s own label) puts your whole buffer here.',
            'On a spool: ✋ PICK puts it in your buffer, ⏏️ EJECT or 🗑️ TRASH takes it out of this place after asking, ✏️ edits it, and 🖨️ adds its label to the print queue. A loaded spool\'s ↩️ RETURN SPOOL puts it back in its slot.',
            'A dryer box has 🔗 Slot → Toolhead Feeds (press Show): choose which toolhead each slot feeds, then 💾 Save Feeds.',
            'Scans while it is open: a slot\'s code (CMD:SLOT:2) does what clicking that slot does, and this place\'s own label puts your buffer here.',
            'CMD:EJECTALL asks, then takes out every spool here that has no slot. CMD:DONE, like ✅ Done / Sync, closes the window, or goes back to the place you came from.',
            '🖨️ Print Location Label adds this place\'s label to the print queue, and its small QR opens bigger, to scan from the screen.',
        ],
        sections: [{
            title: '⚡ Quick-Swap (a toolhead or a printer)',
            when: '#manage-quickswap-section',
            lines: [
                'Every dryer box slot feeding this toolhead (a printer shows all its toolheads\'). Tap a slot\'s spool, then Yes, swap: it goes onto the toolhead, and the spool it replaces goes back where it came from (with no record, the printer\'s room or Unassigned).',
                'With a spool in your buffer, an empty slot shows ⬇️ Deposit from buffer: it puts that spool in the slot and onto the toolhead, asking first.',
                '↩️ Return to Slot puts the loaded spool back in a slot, asking first. 🔗 Bind a Slot… links another box slot to this toolhead, and 🛠️ Edit Full Bindings opens the box\'s feeds.',
                'A one-spool dryer marked 🔗 attached goes with its own spool from toolhead to toolhead.',
            ],
            scopes: ['Quick-Swap'],
        }],
    });

    help({
        key: 'spool-window',
        title: 'Spool Details',
        match: { modal: 'spoolModal' },
        lines: [
            'One spool: where it is, its filament, temperatures and slicer profile, and how much is used and left.',
            'Click the location badge to open that place. The ✏️ beside it moves the spool to a place you pick from a list, with no scanning.',
            '🧬 Swatch opens its filament, 🐑 Clone starts a new spool copied from this one, and ✏️ Edit opens it for editing.',
            '➕ Queue Label adds its label to the print queue, and Spoolman ↗️ opens it in Spoolman. Its slicer profile comes from the filament: (from the filament) opens it there, to change it.',
            '⚙️ holds Delete this spool…, which asks twice before it deletes anything.',
            'Scans still work here: a spool\'s label puts it in your buffer, and a place\'s label puts your buffer there.',
        ],
        scopes: ['Force Location Modal'],
    });

    help({
        key: 'filament-window',
        title: 'Filament Definition (Swatch)',
        match: { modal: 'filamentModal' },
        lines: [
            'One filament, the brand, material and colour its spools share: its temperatures, weights, swatch and label status, and its spools.',
            'Associated Spools lists its spools and where each one is: 🔍 opens one, ✏️ edits it, 📥 puts it in your buffer, 🖨️ queues its label. Show Inactive adds the archived ones.',
            '➕ New Spool starts a spool of this filament, ✏️ Edit Filament changes the filament itself, and ➕ Queue Label adds its swatch label to the print queue.',
            'The ✏️ beside Swatch Printed or Slicer Profile changes it in place. The ✏️ beside Brand opens Edit Manufacturer, which changes the brand itself, for every filament of it.',
            '⚙️ holds Merge into another filament… (its spools move to the other one) and Delete this filament…, which deletes its spools too. Each asks first.',
            'Scans still work here: a spool\'s label puts it in your buffer, and another filament\'s label shows that filament instead.',
        ],
    });

    help({
        key: 'wizard',
        title: 'Add Inventory Wizard',
        match: { modal: 'wizardModal' },
        lines: [
            'Adds new spools, or edits a spool and its filament.',
            'Step 1 picks the filament: Existing Filament (search yours, or 🔍 Advanced Search), Import Database, or New Manual Form.',
            'Step 2 is the filament\'s details: changing them changes the filament for every spool of it. Step 3 is the spools: how many, Location, weight (⚖️ Weigh from scale…) and price.',
            'A Location that is a dryer box with slots, or a printer, asks which slot or toolhead first.',
            'CREATE INVENTORY (SAVE CHANGES when editing) saves. After a create the window stays open for the next batch, and 🖨️ #42 queues that new spool\'s label. Cancel, ✕ or Esc asks first when something isn\'t saved.',
            'When adding spools, scan a Prusament spool\'s QR into its Spool box under 📷 Per-spool Prusament scan in Step 3: that spool is created with the weights and date it reads. In an edit, such a scan isn\'t saved.',
        ],
        scopes: ['Wizard'],
    });

    help({
        key: 'weigh-out',
        title: 'Weigh-Out',
        match: { modal: 'weighOutModal' },
        lines: [
            'Weigh the spools in your scan buffer one after another: each has a box for its weight and a preview of what will be saved.',
            'The buttons at the top say how a number is read. Gross: the scale reading with the spool on it; FCC takes off the empty spool\'s weight, and asks for it when it doesn\'t know it.',
            'Net: the filament alone. Additive: grams added to what was used, like +25, or -10 to take some back. Set Used: the used weight itself.',
            'Type the weight and press Enter, or click 💾: the line goes away and the next box is ready. A weighed spool stays in your scan buffer.',
            'Auto-Archive 0g is on each time this opens: a spool weighed down to 0 g is archived and taken off its place. Turn it off to keep such a spool where it is.',
            'Scan a spool\'s label to add it to the list, or to jump to its box, then type its weight. A place\'s label still puts your buffered spools there, weighed or not, and they leave this list.',
        ],
        scopes: ['Weigh-Out'],
    });

    help({
        key: 'quick-weigh',
        title: 'Quick-Weigh',
        // The wizard's "Weigh from scale" is drawn by the same window, without the switch.
        match: { overlayHas: '#fcc-we-auto-archive' },
        lines: [
            'Changes one spool\'s weight. It opens from the ⚖️ weight on a spool\'s card.',
            'Pick a mode: Gross (the scale reading with the spool on it), Net (the filament alone), Additive (grams added to what was used, like +25 or -10) or Set Used (the used weight itself). The preview shows what is left before you save.',
            'Save Update, or Enter, saves it; Cancel, × or Esc closes without saving. Set as default makes the mode you are on the one it opens in next time.',
            'Auto Archive & Eject if Empty (0g) is on each time it opens: a spool saved at 0 g is archived and taken off its place.',
            'In Gross, when the empty spool\'s weight isn\'t known, Save asks for it first. Skip there saves your number as the filament left (as Net does).',
        ],
        scopes: ['Weigh / Quick-Weigh Overlay'],
    });

    help({
        key: 'move-question',
        title: 'Load or store question',
        match: { overlay: ['fcc-active-print-confirm-overlay', 'fcc-active-print-scan-overlay'] },
        lines: [
            'FCC asks before a move would load a toolhead: the slot you chose feeds HEAD-1, and HEAD-1 already runs a spool from somewhere else, or its printer is printing.',
            'Load it instead: the spool goes in the slot and onto HEAD-1, and the spool on HEAD-1 comes off (the question says where it goes).',
            'Just store it: the spool goes in the slot, and HEAD-1 is left as it was. Cancel: nothing moves.',
            'Enter stores it, or cancels when there is no Just store it. Scan the QR under a button to answer with it. Any other scan is ignored, and the question says so: scan it again once you have answered.',
            'If what the slot feeds changes while you decide, FCC asks again and names the new toolhead.',
            'Some actions during a print (a move straight onto or off a printing toolhead, an Undo, EJECT ALL) ask a shorter question instead: Continue Anyway or Cancel. It opens on Cancel, so a stray Enter moves nothing.',
        ],
        scopes: ['Load / Store Question'],
    });

    help({
        key: 'slot-picker',
        title: 'Slot picker',
        match: { overlayHas: '[data-fcc-picker-mode="box"], [data-fcc-picker-mode="return"]' },
        lines: [
            'Pick the slot of a box a spool goes in. Each tile shows the spool in that slot (or EMPTY), the toolhead the slot feeds, and what that toolhead runs now.',
            '⭐ marks the slot FCC would choose itself. A greyed-out slot says why it can\'t take the spool.',
            'Picking a slot that feeds a toolhead loads the spool onto it too: FCC asks first when that toolhead runs a spool from elsewhere or its printer is printing. A tile that says the spool is stored there doesn\'t load it.',
            'A slot that holds a spool asks first: Swap sends that spool to your scan buffer and files it back where it sat before; Overwrite leaves it in the box with no slot.',
            'Scan a slot\'s label, or the QR on its tile, to pick it. CMD:CANCEL cancels. Any other scan does nothing and says so: scan it again once the picker has closed.',
            'With several spools in your buffer it opens once for each one (1 of 3, 2 of 3). Esc stops there, and the rest stay in your buffer.',
            'From ↩️ Return it asks which slot the spool goes back to, and nothing is loaded.',
        ],
        scopes: ['Slot Picker'],
    });

    help({
        key: 'printer-picker',
        title: 'Printer picker',
        match: {
            overlayHas: '[data-fcc-picker-mode="printer"]',
            // Its two questions, after a toolhead is picked.
            overlay: ['fcc-head-pick-confirm', 'fcc-record-source'],
        },
        lines: [
            'Pick where on a printer the spool goes: one of its toolheads, or a Printer Pool slot, which holds the spool ready without loading a toolhead.',
            'Each toolhead tile shows its spool (or EMPTY), whether the printer is printing, and the box slots that feed it. ⭐ marks the one FCC suggests.',
            'A toolhead that holds a spool asks first: Load it instead loads the new spool, and the question says where the old one goes. Cancel goes back to the picker.',
            'For a spool that is Unassigned, in Unknown or on another toolhead, FCC asks which slot to record it as coming from: a free slot that feeds that toolhead, or No box. ↩️ Return and ⏏️ Eject use that slot later.',
            'Scan a toolhead\'s label, or a tile\'s QR, to pick it. CMD:CANCEL cancels.',
        ],
        scopes: ['Slot Picker'],
    });

    help({
        key: 'print-queue',
        title: 'Print Queue',
        match: { modal: 'queueModal' },
        lines: [
            'The labels waiting to be printed: spools, filaments and places you queued.',
            '📄 Send to P-Touch CSV (Batch) writes them into the CSV files P-touch Editor prints from. When every file is written, the queue empties.',
            'Overwrite CSV File (Clear Old) on: each file holds only this batch. Off: the batch is added after what each file already holds.',
            '❌ takes one label off, and 🗑️ Clear Queue takes them all off after asking. 🧵 Find Multi-Spool Filaments offers every spool of each filament you have two or more spools of.',
            'Queueing a label also lists it in the 🏷️ Label Backlog, and sending marks nothing printed: it stays there until its new label is scanned (or ✔️ Mark Printed there). Taking it off this queue leaves it there too.',
            'When P-touch Editor (or another program) has a file open, that file can\'t be written and the queue stays: close it there, then send again. With Overwrite off, a file written the first time gets the batch twice.',
        ],
    });

    help({
        key: 'label-backlog',
        title: 'Label Backlog',
        match: { modal: 'backlogModal' },
        lines: [
            'The spools and filaments that still need a printed label.',
            'Tick rows (or Select All), then 🖨️ Queue Selected adds their labels to the Print Queue. They stay here until each new label is scanned or marked printed.',
            '✔️ Mark Printed takes a row off by hand. Click a row\'s colour, number or name to open it.',
            'Scan a new label to confirm it: its row leaves the list within a few seconds. A spool\'s label also puts that spool in your scan buffer, so a place\'s label scanned next files them all there.',
            'Keep this window open while you label a batch, and scan each label as it goes on.',
        ],
    });
})();
