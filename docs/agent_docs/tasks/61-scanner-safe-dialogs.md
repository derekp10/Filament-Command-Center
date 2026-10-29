# Group 61: ⌨️ Scanner-Safe Dialogs

**Branch name (when started):** `feature/group-61-scanner-safe-dialogs`
**Estimated effort:** SMALL–MEDIUM (~4–6 h, one night session plus one review).
**Risk:** **LOW–MEDIUM.** Key handling only, no server change. The hazard is the same one Group 57's eleven review rounds kept finding: a handler that acts on an Enter (or a Space) a scanner sent, or a scan that is lost or glued to the next one.

> **Status: `IN PROGRESS` — built 2026-10-29 (night) in `a95163c` (from Group 57's tip, rebased onto `dev` once Group 57 was merged into it); the review and the full run follow.** Derek made it the priority after Group 57 (2026-10-28: "a priority after we get this group … done"; before the phone work, which leans on scanning too) and answered its two design questions on 2026-10-29 before bed.
> _Filed from the buglist item "⌨️ Four older dialogs answer a scan's Enter as a person's" (found 2026-10-27 by the Group 57 review, round 5, reproduced on dev, read-only; older than Group 57)._

## The rule it applies

CLAUDE.md's keyboard standing order: a handler that acts on an Enter leaves a scan's Enter to the scan accumulator (`window.enterIsAScan()`), and a handler that claims a printable key a scan can carry asks `window.scanIsArriving()` first. It must work out of the box with any scanner, no special line ending (Derek: "I wanted this to work out of the box with little modifications for anyone wanting to use it").

Two shapes, as FCC already has them:
- **A question or a picker holds scans until it is answered** (the move questions, the slot picker, "Record it as coming from…"): its own labels answer it, `CMD:CANCEL` cancels it, any other scan is refused with a 7 s note and does nothing. Registered through `window._fccOpenMoveQuestions` / `window._fccOpenMoveQuestion`, which `processScan` reads (`inv_cmd.js`).
- **Anything else passes a scan on**: its Enter (and a Space inside a scan) goes to the scan accumulator, and the scan does what it always does.

## Items

### 61.1 The legacy-ID duplicate picker (`duplicate_picker.js`)
Opened when an old legacy label (the spreadsheet's id, stored as the filament's Spoolman `external_id`; `spoolman_api.find_spools_by_legacy_id`) matches more than one spool of that filament. Today its Enter answers every scan: "Use selected" adds the first spool to the buffer, and the scan's own text stays in the scan buffer, glued to the next scan for 2 s ("ID:57ID:58").
**Derek's answer (2026-10-29): hold until answered, and a listed spool's own label picks it.** ("hold until answered is probably the better option, or if the ID matches a spool for the group, than maybe select that spool"; "any data from the scanner should go to the buffer", never into the dialog's buttons.) So: its Enter leaves a scan's Enter to the accumulator; it registers as an open question: an `ID:<n>` label of one of its spools picks that spool (as "Use selected"), `CMD:CANCEL` cancels, any other scan is refused with a 7 s note in the picker and a toast. Mouse and keyboard use is unchanged.

### 61.2 The location editor (`inv_loc_mgr.js`, Group 46.2)
- **The Type select (and the editor's other controls off a text field):** its Enter-to-save steps aside only for a scanner burst or a ':' / '/', so a slower scanner's bare-number label ("57") saves the form. A scan buffer of digits alone is a scan too: no type starts with a digit, so typeahead never makes one, and a person's typeahead ("dr", then Enter) still saves (46.2's design).
- **The Name box:** a label typed slower than the field capture's 150 ms is saved as the location's name ("LOC:LR-MDB-1"). **Derek's answer (2026-10-29): OK** ("A user shouldn't be using it to input a location name into the name field … if a scan came in, it should go to a buffer or load a card, but not input data"). A whole FCC label (the scan path's prefixes, `LOC:` `ID:` `FIL:` `LEG:` `LEGACY:` `OLD:` `SPL:` `SPOOL:` `CMD:`, or a web address) at the end of the box, typed at any speed, goes to the scan path at its Enter and the box keeps what it held before it; anything else stays a name ("Shelf: top" too).

### 61.3 The smaller ones
- **A focused wizard section header** (`inv_wizard.js`): its Enter / Space toggle the section and stop the event, so a scan's Enter collapses it and the scan stays in the buffer.
- **The floating pills** (`draggable_pill.js`): Enter / Space on the focused 🔍 opens the search, and the scan is processed too.
- **The filament editor's "Close without saving?"** (`inv_details.js`): with Close Anyway focused a scan's Enter closes the editor unsaved (Keep Editing has the focus by default), and with either button the scan stays in the buffer.
- **The parent tree picker** (`inv_loc_mgr.js`, Group 34): Enter picks the highlighted parent and clears the scan buffer, so a scan picks a parent and is lost.
Claude's calls (following Derek's 61.1 answer and the slot picker's rule): the parent tree picker is a picker, so it holds scans as the slot picker does, and a selectable location's own `LOC:` label picks it as the parent; the other three pass a scan on.

## Proof

Hermetic, on a fake clock where speed matters (round 3's `tests/test_slow_scan_confirms_js.py` pattern): each dialog driven by a slow scanner and a burst scanner, each red on the code before the group; a person's keys still work (Enter on each button, typeahead + Enter on the Type select, a name with ':' in it); mutants. Then one review (1 lens, one batched skeptic) and a full run.

## Files to touch

`static/js/modules/duplicate_picker.js`, `static/js/modules/inv_loc_mgr.js`, `static/js/modules/inv_core.js` (the field capture's opt-in label rule; a shared prefix list), `static/js/modules/inv_wizard.js`, `static/js/modules/draggable_pill.js`, `static/js/modules/inv_details.js`, `templates/components/scripts.html` (cache-bust versions), tests, CLAUDE.md (the keyboard idiom), the buglist item (FIXED).

## Build notes

Built in `a95163c`:
- **61.1** `duplicate_picker.js`: its Enter answers only a person's (`window.enterIsAScan()`), a Space inside a scan presses no button, and it registers as an open question (`route(text, source)`: a listed spool's `ID:` / `SPL:` label or bare number picks it, with the scan's own source; another spool's id is refused with "#999 isn't one of the spools listed", a flash in the picker and a 7 s toast; any other scan gets processScan's "Answer the question on screen first" note). `inv_cmd.js`: processScan passes `source` to an open question's `route`, and the picker's pick goes out with its own source, `keyboard` for "Use selected": as `barcode` it marked the picked spool's label printed and verified (`routes_scan.py`'s label-confirm), so the spool left the label backlog though it has no label of its own (found while building this). Note: the picker's list starts with nothing chosen, so a scan's Enter on the old code either closed it ("Use selected" with nothing chosen) or added the spool a person had clicked.
- **61.2** `inv_loc_mgr.js`: the Enter-to-save leaves digits alone (a slow bare-number label) to the scan path; the editor's field capture has `labels: true`. `inv_core.js`: `installFieldScanCapture({..., labels})` sends a whole label at the end of the box (`window.fccLabelAtEnd`) to the scan path at any speed and gives the box back what it held: the text before the label, or, when the label is all there is (typed over the name the editor selects as it opens), what the box held before that run of keys (a run ends after a 2 s pause, the accumulator's reset). Not covered: a slow scan into Max Spools, a number box, which reads a label as empty.
- **61.3** `inv_loc_mgr.js`'s parent tree picker: its Enter leaves a scan's to the accumulator, a Space inside a scan presses no node, and it registers as an open question (a place's own `LOC:` label picks it as the parent; the location itself, one inside it or not a place is refused with "… isn't one of the parents offered here"; it unregisters on a pick, Cancel and Escape, and processScan drops it once its overlay leaves the page any other way). `inv_wizard.js` (a section header), `draggable_pill.js` (the floating pills; a person's press now also keeps its Enter from the accumulator and clears a key they left) and `inv_details.js` ("Close without saving?"): a scan's Enter and a Space inside a scan pass on.
- Proof: `tests/test_scanner_safe_dialogs_61_js.py` (69 tests: the REAL accumulator, processScan and modules in an isolated page; fake-clock keys at 1 to 400 ms a key, real keys for the boxes' text and for a Space's own button press): 45 red on `ca1a701` (the 12 that pass there are a person's keys and a burst label the old rule already caught); 23 mutants, all killed (each checked to still parse: one written wrong first, a dropped quote, was killed by a syntax error and redone).
