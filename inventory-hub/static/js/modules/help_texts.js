// ---------------------------------------------------------------------------
// In-app help (Group 55.3): what each daily dialog is for, in plain words.
//
// One window.registerHelp({...}) per dialog (shortcuts_registry.js draws it in the
// shortcut window, under the ? button in the dialog's header, or for the ? key
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
// only what the code does. tests/test_help_texts_55.py checks the form.
// ---------------------------------------------------------------------------

(function () {
    const help = window.registerHelp;
    if (typeof help !== 'function') return;

    help({
        key: 'location-window',
        title: 'Location window',
        match: { modal: 'manageModal' },
        lines: [
            'Shows what FCC has at this place: a box as its numbered slots, any other place as a list of spools.',
            'Scan a spool\'s label to put it here. In a box, tap a slot or scan the slot\'s own label (CMD:SLOT:2) to choose its slot.',
            '🖨️ Print Location Label adds this place\'s label to the print queue, and its small QR opens bigger to scan from the screen.',
            'CMD:EJECTALL takes every spool out of this place except those sitting in a slot. CMD:DONE closes the window.',
        ],
        sections: [{
            title: '⚡ Quick-Swap (a toolhead)',
            when: '#manage-quickswap-section',
            lines: [
                'Each tile is a box slot that feeds this toolhead. Tap one to load its spool here: the spool loaded now goes back to the box it came from.',
                '↩️ Return to Slot sends the loaded spool back to its slot. 🔗 Bind a Slot… links another box slot to this toolhead.',
            ],
            scopes: ['Quick-Swap'],
        }],
    });
})();
