# Review checklist

These are the lenses that found real bugs in FCC's reviews (Groups 50, 57, 58 and 61, 2026-10 and 11). They're here so that a review run from a new chat starts with them and doesn't rediscover them. Use the lenses that fit the change, prove every finding on the real code or page, and state the failure as concrete inputs or state leading to a wrong result or a crash.

## 1. A scanner is a keyboard
A scan is keys followed by an Enter. Check each of these against every key handler, dialog, button, box and list the change touches:
- **The scan's Enter.** It ends the scan and presses nothing. A handler that acts on Enter asks `window.enterIsAScan()` first. A scanner set to send CR LF sends a second Enter, so allow for one 100 ms after the first.
- **The scan's letters.** A label's own letters before its ':' can reach a letter shortcut: the I and D of `ID:`, the L, O and C of `LOC:`, the F of `FIL:`, the S of `SPL:`, the C of `CMD:`. The shortcut must leave the scan whole. A key a scan can carry (a '/' in a URL) is claimed only when `window.scanIsArriving()` says no.
- **A Space inside a scan.** It presses no button, link, `[role=button]`, `summary` or checkbox. A LocationID can hold a Space.
- **Slow scanners.** Keys can arrive 40 to 150 ms apart, a scanner can stall for up to 2 s, a scan can be split across a focus move, and two scans can arrive glued together. `isScanInFlight` alone is never enough.
- **Upper case.** Caps Lock, or a scanner set to upper case, sends a QR's payload upper-cased. An id compared case-sensitively then misses.
- **A QR's text must not contain another command.** `logic.resolve_scan` matches commands by substring: a name containing `CMD:AUDIT` is read as the audit toggle, and one containing `CMD:CANCEL` as cancel.
- **A double read.** The same label read twice must do nothing more the second time, and must never toggle.
- **A scan into a text box** goes to the scan path (`installFieldScanCapture`), never into the box. The box gets its text and caret back.

## 2. A double click, a double tap, a held key
- **The second press of a double click lands on whatever is now under the pointer** when the first press removed, moved or brought something there: a dialog closing or opening, a panel hiding or showing, a strip appearing. Try every press that changes what is on screen, at several window sizes and list lengths (`tests/test_audit_double_click_58_e2e.py` shows the shape).
- A held Enter auto-repeats. A repeat must never answer the next dialog.
- A press made twice inside 700 ms does what it did once.

## 3. Overlays stack
- Only the overlay on top answers Escape, Enter and its own keys (`window.isTopOverlay`). The ⌨️ shortcut list sits above everything.
- Toasts sit under overlays, so a message the person must read while an overlay is up also goes on the overlay.
- When a host closes, everything it opened closes with it. Tab stays inside a window that traps it.
- Nothing may be pressed through a covering overlay, a processing dim, or a Bootstrap dialog that is fading.

## 4. Run it for real
- **Writes:** drive the real write functions over `tests/spoolman_extra_fake.SpoolmanHTTPFake`, never a mocked `update_spool` or `perform_smart_move`. Mocked engines hid a 5-month no-op.
- **New tests must fail on the old code** (`git archive <old sha>`). A test that passes on both proves nothing.
- **The page:** check it on the real dashboard at several sizes: 1600×1300, 1366×768, a short laptop window and 390 px phone width. Do the same at Text size Large and Extra Large, and with long lists.
- **Reds during a busy run:** a red in a BUSY RUN, or while something CPU-heavy is running, may be load noise. Run it again on its own before believing it.

## 5. Reads and writes tell the truth
- A read that fails says "couldn't read". It never says empty, none or 0.
- Read strictly before writing. Take one last look at each record right before its write, and if anything changed, leave the record alone rather than write.
- `update_spool` timing out is a READ timeout, so the write may have landed. Re-read before calling it failed.
- Clear an extra by sending the delete sentinel. The extras merge keeps a key that is left out. Respect `SYSTEM_MANAGED_EXTRAS`.

## 6. Order and staleness
- An older answer never paints over a newer one: order answers by request sequence.
- A question names what it is about (a session or record id), and a Yes for something that has ended or changed is refused.
- An end, a restart or a second tab can happen at any moment. A scan or press meant for something that has ended does nothing, and says so.

## 7. Spools and places
- Never take a spool off a printing head, and never load a head, unless the person was asked.
- One slot holds one spool, and a one-spool place holds one. Two records must never claim the same slot.
- Archived spools, deleted spools (Spoolman's 404 body is a truthy dict) and spools in the scan buffer all need handling.
- Every move has an Undo, or says why it has none. Undo reads where things are now.

## 8. What a person reads
- Activity Log messages are HTML: escape any outside text that goes into them. A value in an inline handler goes through `SpoolCardBuilder.jsArg`.
- Text in front of the user never uses Derek's own IDs or names as examples.
- Check readable contrast (the contrast guard), the named text sizes (no hand-typed size under the floor), and keyboard navigation (arrows, Enter, Escape, the primary input focused).
- Register every new shortcut with `window.registerShortcut`.

## 9. The repo's own rules
- Call collaborators module-qualified. Patch a private helper on its defining module.
- The container runs Python 3.9 syntax.
- New modules stay flat. Update `tests/test_route_table_pin.py` deliberately.
- The write-surface table in CLAUDE.md lists every write path.
