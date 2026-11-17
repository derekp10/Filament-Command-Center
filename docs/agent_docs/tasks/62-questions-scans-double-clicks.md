# Group 62: ⌨️ Questions, Scans & Double Clicks

**Branch name (when started):** `feature/group-62-questions-scans-double-clicks`
**Estimated effort:** MEDIUM–LARGE (~12–21 h, 2–3 sessions, plus the full sweep and one review round). 62.1 ~0.5–1 h · 62.2 ~1.5–2.5 h · 62.3 ~2.5–4 h (the double-click sweep, and the ~40 test files that press a question's yes) · 62.4 ~2–3.5 h · 62.5 ~0.5–1 h · 62.6 ~1–1.5 h · 62.7 ~1.5–2.5 h · 62.8 ~1.5–2.5 h · 62.9 ~0.25 h for (a), ~1.5–2.5 h for (b) or (c). Estimates here have run about 30% low, so plan on the upper half.
**Risk:** **MEDIUM.** Every member sits on the scan path or on a question's keys, and those run all day. The hazards are:
- a hold-off that refuses a scan a person meant (62.2: the question's own QRs and a bare `CMD:CANCEL` must still answer it);
- two defaults that change every question or overlay at once (62.3's arming, 62.4's `trapTab`);
- two Tab handlers on the document, which move the focus twice;
- the delete flow's port (62.8), the one action here that can't be undone.

No Spoolman write changes, unless Derek picks (b) for 62.9.

> **🔄 2026-11-16 (after the grouping): 62.10 added**, the slot picker's missing CR LF Enter rule, found by the investigation of Group 40's dropped hand checks. ~1–2 h with its pins.
>
> **Status: IN PROGRESS, started 2026-11-17** on `feature/group-62-questions-scans-double-clicks` (from `dev` `453b472`; no app code had changed since the grounding at `3388c7d`, so its anchors held). **Derek's answers at the start (2026-11-17):** 62.9 **(a) keep Eject All as it is**; Claude's calls below: *"Go ahead as planned"* (DEPOSIT HERE's QR included). On 62.10 he added: *"I can't confirm in the inateck app what values the scanner sends at the end. The option in the configuration just says enter … So I don't want to expect a CR LF if we only send a CR or just a LF."* The fix assumes neither: it drops only an Enter within 100 ms of a scan's own, so one Enter changes nothing and a doubled one loses its second.
>
> **Filed 2026-11-16** (/refresh-groups; Derek approved the grouping the same day: "otherwise this seems fine"). **First in the recommended order**: it holds the daily scan path's two 🟠 (62.1, 62.2). **Starts ready:** 62.1–62.8 need nothing from Derek. 62.9 is one question at the group's start (see Decisions), and it blocks nothing else.
> **Grounded the same day**, read-only, on `dev` @ `3388c7d`. Every member is still live; each row below says what was found. Two of the four overlays 62.4 names were only partly right. Grounding also found three siblings, now folded in:
> - the Quick-Swap confirm holds off no scans either (62.2);
> - a card's own 🗑️ isn't stopped during an audit (62.7);
> - a `CMD:EJECTALL` scan during a bulk move opens "Nuke all?" behind the bulk panel (62.7).
>
> Code anchors were read on `dev` @ `3388c7d` (2026-11-16). Line numbers drift, so re-grep before editing.

## Items covered (quoted from `Feature-Buglist.md`)

| # | Buglist item | Direction |
|---|---|---|
| **62.1** 🟠 | *"A `CMD:EJECTALL` scan that isn't the exact text turns Eject mode on (found 2026-11-10, Group 55). `logic.resolve_scan` tests `"CMD:EJECT" in upper_text` before `"CMD:EJECTALL"` (`logic.py` ~:1012-1014), so every EJECTALL text the page's exact match misses (`inv_cmd.js` ~:3415; a key left in front of the scan, say) comes back as `eject`, which toggles Eject mode, and the next spool scanned is ejected. The page's own `ejectall` branch (~:3542) is never reached. Test the longer command first."* | **Live** (`logic.py:1012` comes before `:1014`). Test the longer command first, and pin the whole ladder. |
| **62.2** 🟠 | *"The printing yes / no question holds off no scans and ignores a bare CMD:CANCEL (found 2026-11-10, Group 55). The shorter "Continue Anyway / Cancel" form of `confirmActivePrint` (a move straight onto or off a printing head, Undo, EJECT ALL, a location delete) registers in `window._fccOpenMoveQuestions` only for the three-way (`inv_core.js` ~:605-632), so a slot label scanned meanwhile starts a second move behind it, the hazard the three-way's hold-off was added for, and a plain `CMD:CANCEL` reaches no handler (`inv_cmd.js` ~:3322-3348, ~:3534-3542). The shortcut list says CMD:CANCEL cancels "the load question on screen" and that other scans are held off."* | **Live** (`inv_core.js:636` registers the question only `if (threeWay)`). The yes / no registers too, and so does the Quick-Swap confirm (found while grounding). |
| **62.3** | *"🖱️ A double click can answer the other doors' questions too (found 2026-11-02, Group 58's review). A question can open with its yes under the pointer, and the second click of a double click on the button that asked it then answers a question nobody has read. On the audit's Done that parked a whole batch, so Group 58 gave `window.confirmActivePrint` the option `armAfterMs` (the yes takes no click until that long after it opens). It is opt-in and only `askAuditDone` passes it: every other caller (`askMoveConfirm`, `confirmHeadLoad`, the printing yes / no in inv_cmd.js, inv_details.js, inv_loc_mgr.js and inv_wizard.js) takes the click at once, and opening on Cancel protects only the keyboard. Whether a door is exposed depends on where its question opens, which on the audit's Done was only at some window and Text sizes. Wanted: a real mouse double click on each door at laptop sizes (`tests/test_audit_done_question_58_e2e.py` has the audit's), then the option there, or as the default."* | **Live** (only `inv_cmd.js:2573` passes `armAfterMs`). The sweep first, then the default. |
| **62.4** | *"⌨️ A click on a question's own background leaves its keys dead (found 2026-11-02, Group 58's re-review). `window.confirmActivePrint` (inv_core.js) hears its keys on its own overlay (`ov.addEventListener('keydown', …, true)`), and a click on the question's text or background (not a button) moves the focus to the page, so Enter and the arrows reach nothing while the hint still says what Enter does; only Escape (mountOverlay's) and the mouse answer it. Every door that uses it: Done's question, the move questions, the printing yes / no. … Wanted: a mousedown `preventDefault` on the question off its buttons, or its keys heard on the document while it is on top."* | **Live** (`inv_core.js:563`). Its keys are heard on the document while it is on top. |
| | *"⌨️ Done's question keeps Tab inside it only while the focus is inside it (found 2026-11-02, Group 58's re-review). Its Tab handler is the question's own (`confirmActivePrint`), and the panel's `trapTab` stands down under it (`isTopOverlay`), so with the focus outside the question (after a click on its background, above) Tab walks the page behind it, to the 📜 log pill and on. Nothing there can be pressed (the press rule refuses it), but the keyboard is lost where nobody can see it. Wanted: the question passes `trapTab: true` to its `mountOverlay`."* | **Live** (`inv_core.js:515` mounts it without `trapTab`). The same change as the row above fixes it; `trapTab` itself would fight the question's own Tab order (see Design). |
| | *"⌨️ `trapTab` is opt-in, and the large overlays don't pass it (found 2026-11-02, Group 58's review). `mountOverlay`'s `trapTab` keeps Tab inside an overlay while it is on top; the audit panel, the 🧺 list and the legacy picker pass it. Bulk Move's panel, the slot picker, Force Location and the other large overlays don't, so Tab walks out behind them. A Space or an Enter there presses nothing (`mouseCouldReach`), but the focus is gone from what is on screen. Wanted: `trapTab: true` on each, or as the default with a way out for a small one."* | **Live for Bulk Move's panel and 18 other overlays.** 24 of the 29 `mountOverlay` calls pass no `trapTab`; 19 of those have no Tab handler of their own. **Partly true for two:** the slot picker cycles Tab itself (`slot_picker.js:914-926`) and lets it out only from a field behind it; Force Location is a SweetAlert2 popup, which cycles Tab while the focus is inside it (could not tell, without a browser, whether a click on its dim loses it). Make `trapTab` the default, with a way out. |
| | *"🟡 The empty-weight prompt doesn't trap Tab (found 2026-11-09, Group 54's review, R6). After Save weight, Tab walks onto the dashboard (where Enter and Space are refused). Pass `trapTab: true` to its `mountOverlay`."* | **Live** (`inv_details.js:1639`). The default covers it. |
| **62.5** | *"⌨️ An N under the ⌨️ list stays in the scan buffer for 2 s (found 2026-11-02, Group 58's re-review). The audit panel's N stands down while the list is up (inv_cmd.js), so the scan accumulator keeps the 'n' as the start of a scan; a person's Enter under 500 ms after closing the list then reads as a scan of "n" (`enterIsAScan`'s in-flight rule) and toasts an unknown code. Group 58 made the Space after it press nothing a mouse couldn't reach; the Enter is this item. Wanted: the list's own keys (its N, its letters) take a person's key out of the buffer, as its ? does (`clearScanBuffer`)."* | **Live** (`inv_cmd.js:2365-2366` stands down; the list's `_close` clears nothing). Strictly, the window is 500 ms from the N itself, and two keys left make it the full 2 s. Closing the list takes a person's keys with it. |
| **62.6** | *"🟡 ⬇️ DEPOSIT HERE: a click and a scan of its QR do different things (found 2026-11-10, Group 55). The click places only the spool READY TO SLOT shows (`inv_loc_mgr.js` ~:1129-1145), while its QR is the place's own `LOC:` label, which files the whole buffer or opens a picker for each spool (`inv_cmd.js` ~:3728-3750). The code's comment says they match. The help says what each does meanwhile."* | **Live** (the click at `inv_loc_mgr.js:1138-1154`, the scan at `inv_cmd.js:3700-3752`). The QR does what the click does (Claude's call, for veto). |
| **62.7** | Group 55's word check, *"Smaller ones from Group 55's word check (found 2026-11-11, when the help stopped naming scan codes)"*, in four parts.<br>(a) *"The location window's Done / Sync QR is `CMD:DONE`, the same text that finishes an audit (Done's question) and commits a bulk move, so scanned while either runs it does that instead of closing the window, which can be open under a hidden audit or bulk panel (`inv_loc_mgr.js` ~:300; `routes_scan.py` ~:1323-1424; `logic.py` ~:3975-3999, ~:7363-7365); the help says so meanwhile, and a code of its own would end it."*<br>(b) *"EJECT ALL's button isn't stopped during an audit, though its QR is (`inv_cmd.js` ~:273, `inv_loc_mgr.js` ~:1374)."*<br>(c) *"The slot picker draws no 📷 CANCEL QR while it loads or on its "couldn't read" message (`slot_picker.js` ~:534-558); a cancel scan still cancels there."*<br>(d) *"The 📡 log pill compares clock times as text (`'HH:MM:SS'`, `state.py` ~:103, `inv_core.js` ~:2839), so after midnight a line earlier than the last-seen time never raises it, and `dashboard.html`'s comment (~:188-191) says it follows whether Live Activity is on screen, which the code doesn't (it counts every line since its list was last opened)."* | **All four live.**<br>(a) The QR gets a code of its own.<br>(b) The button is refused as the scan is, and so is a card's own 🗑️ (found while grounding).<br>(c) The QR is drawn in both views.<br>(d) A stamp that sorts, and the comment fixed.<br>The item's EJECT ALL list-view part is 62.9. |
| **62.8** | Pre-refresh audit, `[G15:15.2-delete-confirm]`: *"Group 4's delete-confirm overlay was skipped as 'doesn't exist yet', but it existed and still mounts inside its modal without mountOverlay."* (Its code: `inv_details.js` `_renderDeleteOverlay`, with `position:absolute`, `z-index 1100` and `data-fcc-cover`.) | **Live** (`inv_details.js:3010-3116`). Route it through `mountOverlay`. |
| **62.9** ❓ | Pre-refresh audit, `[G41:eject-all-removal]`: *"Whether to remove Eject All altogether (Derek: 'A case could be made for removing it'); recorded as 'not decided', so it stays."*<br>And from Group 55's word check: *"EJECT ALL is drawn only in a box's grid, under Unslotted Items while the box holds spools with no slot; a plain place's window has none (its list view still draws a QR into a target that doesn't exist, `inv_loc_mgr.js` ~:76-81, ~:1329), so emptying a shelf at once takes a printed command label: decide whether the list view gets the button."* | **Live** (the dead call is `inv_loc_mgr.js:1329`). Derek decides at the group's start. |
| **62.10** | Added 2026-11-16 by the refresh's investigation of Group 40's dropped hand checks (`wf_5b3929ac-47d`; by reading the code, not run): *"The slot picker misses a CR LF scanner's second Enter… the slot picker's own rule, `_enterIsAScans` (`slot_picker.js`), never got [`enterIsAScan`'s 100 ms] clause. So the second Enter (1) after a refused scan picks the highlighted ⭐ slot, and (2) after a scanned occupied slot's label, answers the picker's Swap question with its first button."* (buglist: "⌨️ The slot picker misses a CR LF scanner's second Enter") | Keep the hotkey exception first, then apply `enterIsAScan`'s 100 ms clause (`state.lastScanEnterAt`, `inv_core.js`). Pin two Enters after a refused scan (grid and choice view) and after a scanned occupied / on-feed slot label, on a fake clock (`tests/test_slow_scan_confirms_js.py`'s pattern). Ground the anchors first (`_enterIsAScans` ~:839-846, `_choiceKeys` ~:889-897, the capture listener ~:1009). Asked of Derek 2026-11-16: does his scanner end a scan with CR LF? The fix is right either way. |

> **Gained since this file was written (2026-11-17, the refresh, from Groups 70 and 73's task files):** 62.3's item adds the Print Queue's 📄 Send (it closes its window under the pointer); 62.4 gains an item, the location manager's capture-phase Escape handler (by reading only: check it in a browser first); 62.5's item adds Shift+B under the ⌨️ list; 62.8's item adds Edit Filament's "Close without saving?". Read those items in `Feature-Buglist.md` before building them.

## Decisions

### For Derek, at the group's start: Eject All (62.9 ❓)

- **What it is.** EJECT ALL empties the place whose Location Manager window is open, in one go. Each spool goes back where it came from (its box and slot), or to Unassigned after one more question. In a box it leaves alone the spools that have a slot, and anything loaded on a toolhead.
- **Where it is today.** Only in a dryer box's window: a red ☢️ DANGER ZONE with its QR, under "Unslotted Items", shown only while that box holds a spool with no slot.
  - A cart's, a shelf's or a toolhead's window has no EJECT ALL button.
  - There, the only way is to scan a printed `CMD:EJECTALL` label with that window open.
- **Example.**
  - The cart row CR-CT-2-R1 holds six spools. To send them all home at once today, you need the printed label.
  - LR-MDB-1, with two spools that have no slot, shows EJECT ALL under them.
- **What it asks.** First FCC refuses a room or a printer. Then it asks "Nuke all unslotted in CR-CT-2-R1?" (the FORCE EXECUTE button). Then it asks one "Unassign?" for the spools with no home.
- **Background.**
  - Your D4 (2026-09-13) refused rooms and printers ("an eject all on a room would be catastrophic") and kept Eject All for "boxes, carts, shelves and toolheads". Only a box's window ever drew the button.
  - Your words the same day: "I may have used it once or twice, but I don't recall the last time… A case could be made for removing it." Removal was left undecided.
- **Options.**
  - **(a) Keep it as it is.** Only the dead code goes (the list view draws a QR into a box that isn't there).
  - **(b) Remove it:** the button, its QR and the command. An old printed `CMD:EJECTALL` label then says "Eject All was removed" and does nothing. It never turns on Eject mode (62.1 makes sure of that).
  - **(c) Add it to every window D4 keeps it for.** Carts, shelves and toolheads get the same ☢️ DANGER ZONE after their spools, with the same questions. Rooms and printers still have none.
- **Recommendation: (a).**
  - You rarely use it.
  - The window that has it is the one where spools with no slot pile up.
  - A printed label still empties a shelf.
  - (c) puts a button that moves every spool into every window, and (b) takes away something you have used.
- **If you don't answer:** (a). 62.9 blocks nothing else in the group.
- **✅ Answered 2026-11-17: (a) keep it as it is.** Only the dead list-view QR call and its comment go.

### Claude's calls (for veto)

- **62.1:** reorder the ladder (`CMD:EJECTALL` before `CMD:EJECT`), and pin every command three ways: alone, with a key in front, and with a label glued after. The two tests that stub the server's answer as `ejectall` take their answer from the real `logic.resolve_scan`; their stub is what hid this.
- **62.2:** the yes / no joins the hold-off exactly as the three-way does:
  - its own QRs answer it;
  - a bare `CMD:CANCEL` cancels it;
  - any other scan is refused with a 7 s warning and a line on the question itself.

  The Quick-Swap confirm joins too. It is the same class, found while grounding, and not filed.
- **62.3:** arm every question's yes by default, for 700 ms (Group 58's double-press figure), and the three-way's "Just store it" too.
  - Cancel never waits, and neither do Enter and the QRs.
  - Arm it even on a door the sweep finds safe: where a question opens depends on the window and Text size (Group 58's lesson), and nobody reads a question in under 700 ms.
  - The Quick-Swap confirm's Yes gets the same.
- **62.4:**
  - The question hears its keys on the document while it is on top (the item's second "Wanted"). That fixes the dead keys and Done's Tab with one change.
  - `trapTab` becomes `mountOverlay`'s default. The five overlays that cycle Tab themselves opt out, with a comment naming their handler; a blanket default would move their focus twice.
  - A canary keeps it so.
- **62.5:** clear the scan buffer when a person closes the ⌨️ list, not at the N: under the list a letter can be a scan's first key.
- **62.6:** the DEPOSIT card's QR gets a code of its own that does what the click does (the spool shown), checked against the place whose window is open. The place's printed `LOC:` label keeps filing the whole buffer. **Veto option:** keep both as they are and fix only the comment; the help already says what each does.
- **62.7:**
  - **(a)** The location window's Done / Sync QR becomes `CMD:CLOSE`, a code only the page reads, which closes the window whatever else is running.
  - **(b)** EJECT ALL's button and a card's own 🗑️ are refused during an audit, with the scan's words. Both wait during a bulk move, as `CMD:TRASH:` does. The refusal lives in the page only, as the scan's refusal does.
  - **(d)** Fix the pill's comment, not when the pill shows. It has shown every new line since its list was last opened for months. Making it hide while Live Activity is on screen would be a look change, for Derek to ask for.
- **62.8:**
  - Keep the delete flow's two steps and its typed confirm. Deleting a spool is the one action here with no Undo, and CLAUDE.md's "no typed-word confirms" is a default, not a ban.
  - `data-fcc-cover` loses its only user, so its rule goes from `mouseCouldReach`.

## Today's code (anchors, `dev` @ `3388c7d`)

### The ladder (62.1)
- `logic.resolve_scan` is `logic.py:993-1054`: `"CMD:EJECT" in upper_text` at `:1012`, then `"CMD:EJECTALL"` at `:1014`.
- Outside a session, `api_identify_scan` returns the command as resolved (`routes_scan.py:1799`).
- The page's table maps `eject` to `toggleEjectMode` (`inv_cmd.js:3534`; `toggleEjectMode` is `:113-116`). Its `ejectall` branch (`:3542`) is reached by no text.
- The page's exact match is `inv_cmd.js:3415`. `ejectAllFromScan` (`:3094-3110`) holds the open-window guard.
- In an audit the server refuses both ("Command not allowed in Audit", `logic.process_audit_scan` `:7363-7370`).
- Pins today:
  - `tests/test_bulk_move_session.py:161-167` checks `CMD:EJECT` alone.
  - `tests/test_core1_return_ejectall_js.py:431-448` and `tests/test_core1_return_ejectall_e2e.py:96-101` stub the server as answering `ejectall` for "label CMD:EJECTALL" and "FCC-TEST CMD:EJECTALL". The real server answers `eject`.

### The hold-off (62.2)
- `window.confirmActivePrint` is `inv_core.js:387-665`.
  - The question object is built and registered only `if (threeWay)` (`:636-663`).
  - The status line exists only for the three-way (`:462-464`).
  - Cleanup unregisters the question (`:484-493`).
- The yes / no's callers:
  - `inv_cmd.js:3909` (`_confirmActivePrintScan`) and `:4559` (Undo);
  - `inv_core.js:905` (`askMoveConfirm`'s `active_print`);
  - `inv_details.js:1383` (Force Location to Unassigned);
  - `inv_loc_mgr.js:1633` (a grid assign), `:2113` (EJECT ALL) and `:3087` (a location delete);
  - `inv_wizard.js:3973`.
- processScan's hold-off is `inv_cmd.js:3317-3348`, after `routeConfirmScan` (`:3316`).
- The Quick-Swap confirm is `inv_quickswap.js:549-752` (`showConfirmOverlay`), with no hold-off.
- The words that describe today's gap: `help_texts.js:172`, `shortcuts_registry.js:734` (CMD:CANCEL) and `:763`.
- **Found while grounding:** with the audit panel hidden, a bare `CMD:CANCEL` scanned at a yes / no question goes to the server's audit gate (`routes_scan.py:1323-1365`) and cancels the audit.

### Arming (62.3)
- `armAfterMs` is `inv_core.js:261-265` and `:534-535`; it arms the yes only.
- Only `askAuditDone` passes it (`inv_cmd.js:2573`; `DOUBLE_PRESS_MS` is 700, at `:1301`).
- The three-way doors:
  - `confirmHeadLoad` (`inv_core.js:676-705`);
  - `_confirmHeadPick` (`inv_cmd.js:4164-4180`). A click on a head tile in the Printer picker opens it at once, with no server round trip.
- The Quick-Swap confirm's Yes is `inv_quickswap.js:748`; on an idle head it has the focus first (`:711`).
- Gating dialogs already take no click while they fade in (`global.css:1554-1572`).
- The sweep to copy is `tests/test_audit_double_click_58_e2e.py` (its `SIZES`, and `GAP_MS` 120).

### Keys and Tab (62.4)
- The question's keys are heard on its overlay (`inv_core.js:563-609`), and its mount has no `trapTab` (`:515-522`).
- `mountOverlay`'s `trapTab` is opt-in (`overlay_mount.js:135`). Its handler (`:211-225`) stops only propagation.
- 5 of the 29 calls pass it:
  - `duplicate_picker.js:146`;
  - `inv_audit_find.js:572`;
  - `inv_cmd.js:2104` (the audit panel) and `:2758` (the report window);
  - `inv_loose.js:381`.
- Five overlays cycle Tab themselves:
  - `confirmActivePrint`;
  - the record-source question (`inv_cmd.js:4301`; its keys are on its overlay too);
  - the Quick-Swap confirm (`inv_quickswap.js:679-696`, on the document);
  - the slot picker (`slot_picker.js:905-926`, on the document, standing aside when the focus is on a field behind it, `:911`);
  - Force Location's "Cancel Override?" (`inv_details.js:1143-1149`).
- The overlays the item names:
  - Bulk Move's panel, `inv_cmd.js:1178`;
  - the empty-weight prompt, `inv_details.js:1639`;
  - the slot picker, `slot_picker.js:958`;
  - Force Location, `inv_details.js:1043`. It is a `Swal.fire` popup (sweetalert2@11, from `scripts.html:2`), with `allowOutsideClick: false`.

### The ⌨️ list (62.5)
- The audit panel's key handler is `inv_cmd.js:2357-2372`; it stands down while the list is up (`:2365-2366`).
- The list's own keys are `shortcuts_registry.js:486-582`:
  - Escape, `:560-569`;
  - Enter clears the buffer, `:570-581`;
  - `?` clears it, `:558`.
- `_close` (`:241-274`) clears nothing.
- The scan helpers: `isScanInFlight` (`inv_core.js:91-96`, 500 ms from the first key), `enterIsAScan` (`:159-167`) and `clearScanBuffer` (`:174-185`). The accumulator's 2 s reset is `scripts.html:456-461`.

### DEPOSIT HERE (62.6)
- The card is `inv_loc_mgr.js:1113-1192`.
  - The click (`:1138-1154`) places `state.heldSpools[0]` only.
  - The QR is `LOC:<id>` (`:1161`), drawn at `:1187`, `:1331-1333` and `:1339-1341`.
  - The comment that says they match is `:1141-1145`.
- The scan is `inv_cmd.js:3700-3752`:
  - the whole buffer, `:3749`;
  - one picker per buffered spool for a multi-slot box or a Printer row, `:3728-3742`;
  - the top spool for a one-spool place, `:3743-3747`.
- The help is `help_texts.js:51-52`. The test is `tests/test_deposit_card_race_e2e.py`.

### Group 55's four (62.7)
- **(a)**
  - The QR: `inv_loc_mgr.js:300` (`generateSafeQR('qr-modal-done', 'CMD:DONE', 58)`), drawn into `modals_loc_mgr.html:312`.
  - The audit gate: `routes_scan.py:1323-1365` and `logic.py:7364-7365`.
  - The bulk gate: `routes_scan.py:1404-1424`. With Bulk Moves off, it answers only CMD:CANCEL.
  - `closeManage` is `inv_loc_mgr.js:360`; the help line is `help_texts.js:57`.
- **(b)**
  - The button: `inv_loc_mgr.js:1374`, which calls `window.triggerEjectAll` (`:2069-2096`, no audit check).
  - A card's 🗑️ is `window.ejectSpool` (`:1844-1869`); it refuses only the pickup (`:1849`).
  - The scan refusals are `inv_cmd.js:270-287`, and `window.auditPressRefused` is `:292-296`.
  - `CMD:TRASH:` waits during a bulk move (`inv_cmd.js:3430-3434`); `CMD:EJECTALL` doesn't (`:3415`).
  - The server's `manage_contents` has no audit gate (`routes_scan.py:275+`).
- **(c)** `_renderLoading` is `slot_picker.js:534-544` and `_renderMessage` is `:546-558`. The CANCEL QR is drawn only in `_render` (`:588`).
- **(d)**
  - `state.add_log_entry` is `state.py:102-155`: `time.strftime("%H:%M:%S")` at `:104`, and the entry `{time, msg, type, meta}` at `:143`.
  - `_updateLogPill` is `inv_core.js:2835-2853`, with the text compare at `:2839`.
  - `openLogPillOverlay` is `:2865-2906`; it writes the last-seen time at `:2870`.
  - `_renderLogsPayload` calls it (`:2961`).
  - The comment is `dashboard.html:188-196`, and the localStorage key is `fcc.logPill.lastSeenTime` (`inv_core.js:2825`).

### The delete question (62.8)
- `_renderDeleteOverlay` is `inv_details.js:3005-3116`:
  - an in-window div, `position:absolute; z-index:1100`;
  - `data-fcc-cover`, `:3021`;
  - Bootstrap's keyboard suspended, `:3047-3059`;
  - its own Escape handlers, `:3096-3115`;
  - Enter in the typed box presses the confirm with no `enterIsAScan` check, `:3085-3091`.
- The flows are `:3118-3153` (spool) and `:3407-3450` (filament); the wiring is `:3452-3522`.
- Its targets are `modals_details.html:6` and `:116`.
- `mouseCouldReach`'s cover rule is `scripts.html:347-349`.
- Tests: `tests/test_delete_ui_e2e.py` and `tests/test_enter_presses_buttons_50_6.py:753-763`.

### Eject All (62.9)
- `renderGrid` (`inv_loc_mgr.js:1041`) calls `renderUnslotted` (`:1109`). That draws the DANGER ZONE (`:1348-1388`), with its QR at `:1385`.
- `renderList` (`:1227`) draws no button, and its `generateSafeQR('qr-eject-all-list', …)` (`:1329`) has no target. The comment is `:76-81`.
- `triggerEjectAll` asks the server first (`check_only`, `:2085`), then "Nuke all unslotted in …?" (`:2093`).
- The refusals are `logic.eject_all_block_reason` (`logic.py:1592`). The write is `routes_scan.py:308+` (`clear_location`, in CLAUDE.md's write-surface table).
- Derek's D4 is `open-decisions-2026-09-13.md:76-81`; see also `41-honest-bulk-results.md:41`.

## Design, by sub-task

### 62.1 — the longer command first
- In `resolve_scan`, test `CMD:EJECTALL` before `CMD:EJECT`. Any text holding `CMD:EJECTALL` then comes back as `ejectall`, which reaches `ejectAllFromScan`'s open-window guard, never Eject mode.
- Checked 2026-11-16: no other command in the ladder holds another's text. (`CMD:CANCEL:<sid>` and `CMD:CONFIRM:<sid>` hold theirs on purpose.) The ladder pin below keeps it so.
- 62.9's answer doesn't change this: even (b) needs the ladder to say "removed" for an old label, never Eject.

### 62.2 — the yes / no holds scans too
- `confirmActivePrint` builds and registers its question for both forms (drop the `if (threeWay)` at `:636`). The yes / no's question gets:
  - a `title`: its header, such as "XL is PRINTING";
  - a `hint`: "Answer the question on screen first: Continue Anyway or Cancel";
  - a status line, drawn for both forms, so a refused scan is said on the question itself (toasts sit under it).
- processScan needs no change:
  - its own QRs are answered before the hold-off (`routeConfirmScan`);
  - a bare `CMD:CANCEL` cancels the question (`:3335`);
  - anything else is refused with a 7 s warning and a WARNING line.
- With the audit panel hidden, a bare `CMD:CANCEL` then cancels the question, no longer the audit.
- The Quick-Swap confirm registers the same way, with the hint "Answer the question on screen first: Yes, swap or No, cancel" and a status line of its own. It unregisters in its `close`.
- Change the words that describe the gap: `help_texts.js:172`, `shortcuts_registry.js:734` and `:763`, and CLAUDE.md's "One move question" paragraph (scans are held off while any question is open, not only a three-way).

### 62.3 — a double click answers nothing
- **First, the sweep.** A real mouse double click (120 ms apart) on the button that asks each question, at the audit sweep's five laptop sizes, with every non-GET answered in the browser. Red on `3388c7d` wherever a yes lands under the pointer. The doors:
  - a grid slot's assign;
  - the Printer picker's head pick ("Load #42 onto XL-3?"), the most exposed, since it opens with no round trip;
  - Undo on a printing head;
  - EJECT ALL's FORCE EXECUTE on a printing head;
  - Force Location to Unassigned;
  - a location delete;
  - the wizard's Save;
  - a Quick-Swap tile, and Printer Status's ✓ I loaded it;
  - for the record, the gating dialogs ("Clear entire Buffer?", Undo's question), which already take no click while they fade in.
- **Then the default.** `armAfterMs` is 700 ms for every `confirmActivePrint`, on its yes and on its store.
  - Cancel takes a click at once. Enter and the QRs never wait.
  - The Quick-Swap confirm's Yes gets the same.
  - A door may pass `armAfterMs: 0` only with a comment saying why.
- **A test seam.** About 40 test files press or name a question's yes. Give the harnesses one page value they can set to 0 (say `window.fccQuestionArmMs`), read when each question opens. The tests that are about arming keep 700 ms.
- **A chained question needs the same care.** After "Load it instead" in the Printer picker, "Record it as coming from…" opens where the first question was. Its buttons are its own, not `confirmActivePrint`'s, so the sweep includes it.

### 62.4 — keys and Tab stay with what is on screen
- **The question's keys.** Move `confirmActivePrint`'s key handler (`:563-609`) from its overlay to the document, in the capture phase.
  - It acts only while `window.isTopOverlay(ov)` and while the ⌨️ list is down (`window.fccShortcutsUp()`). `cleanup` removes it.
  - A click on the question's text or background then leaves Enter, the arrows and Tab working. Tab from anywhere comes back to its first button (with Shift, its last). That fixes Done's question's Tab too.
  - In the yes / no, an Enter on no button cancels, as its hint says; today it does nothing.
  - The record-source question (`inv_cmd.js:4301`) gets the same change.
- **`trapTab` by default.** `overlay_mount.js:135` reads `o.trapTab !== false`.
  - The overlays that cycle Tab themselves pass `trapTab: false`, with a `// own-tab:` comment naming their handler: `confirmActivePrint`, the record-source question, the Quick-Swap confirm, the slot picker and Force Location's "Cancel Override?".
  - The reason they opt out: `mountOverlay`'s handler stops only propagation, so a handler of their own on the document would move the focus a second time.
- **The slot picker.** A Tab with the focus on a field behind it comes into its panel. Today D1 lets it through (`:911`); D1 is about a scan's keys, and Tab is never one.
- **Each overlay newly trapped.** A list whose rows rove (`.kb-active`) keeps the highlighted row in the tab order (CLAUDE.md's trapTab rule). Look at each once: the Low stock list, the 🛑 review, the parent tree picker and the log list.
- **Force Location** is a SweetAlert2 popup. Check in the browser whether Tab, after a click on the dim outside the popup, walks the window behind it. If it does, fix that case only. Swal's `keydownListenerCapture: true` is one way; mind its Escape handler, which listens on the window in the capture phase.

### 62.5 — a key left under the ⌨️ list goes when it closes
- When a person closes the list (Escape, its ✕, its backdrop, or `?` again), `_close` clears the scan buffer unless `window.scanIsArriving()`. It doesn't clear when the list closes because its dialog went.
- Any key the dialogs under the list stood down for then goes with the close: the audit panel's N, the Quick-Weigh's D, the grid's Q.
- A scan read under the list is unaffected: its Enter came before the close.

### 62.6 — DEPOSIT HERE's QR does what its click does
- The card's QR becomes `CMD:DEPOSIT:<place>`, a code only the page reads, as `CMD:TRASH:` is.
  - Scanned while the Location Manager is open on that place, it runs the card's click: the spool READY TO SLOT shows, through the slot or Printer picker where the click would open one.
  - Anywhere else, it gives a 7 s warning and a log line, and moves nothing.
  - It is refused during an audit and during a bulk move, as `CMD:TRASH:` is.
  - A read that isn't the exact text reaches the server, which answers "Malformed Command".
- The QR is still drawn once per window (Group 46.1: it never depends on the spool shown). The spool is read at the scan, as the click reads it at the click.
- Change the comment (`inv_loc_mgr.js:1141-1145`) and the help line (`help_texts.js:52`) to match. The place's printed `LOC:` label is unchanged.

### 62.7 — four small ones
- **(a)** `qr-modal-done` draws `CMD:CLOSE`. processScan's exact matches (beside `CMD:LOCATIONS`) close the window with `closeManage`. The help line `:57` loses its "except during an audit" clause. `CMD:DONE` then belongs to the audit and the bulk move only.
- **(b)** `triggerEjectAll` and `ejectSpool` (not the pickup) ask `window.auditPressRefused` first; CMD:TRASH's words join `_AUDIT_REFUSES`. Both wait during a bulk move, as `CMD:TRASH:` does.
  - The `CMD:EJECTALL` scan waits during a bulk move too. Today it opens "Nuke all?" behind the bulk panel (z 1100, under the panel's 20000), and the gating dialog then swallows every scan meant for the session. That is the deadlock Group 39.9 closed for `CMD:TRASH:`.
- **(c)** `_renderLoading` and `_renderMessage` draw the footer's 📷 CANCEL QR (`fcc-sp-qr-<id>-cancel`), as the grid does.
- **(d)** Each log entry gains `ts`, in epoch milliseconds; the time text stays for the lines.
  - The pill counts the entries whose `ts` is newer than the last one seen, stored under a new key (`fcc.logPill.lastSeenTs`).
  - An entry with no `ts` (from an older FCC) uses the old compare. An old stored time reads as "nothing seen", once.
  - `dashboard.html`'s comment says what the code does, and CLAUDE.md's preferences table names the new key.

### 62.8 — the delete question through `mountOverlay`
- `_renderDeleteOverlay` mounts with `window.mountOverlay`:
  - tier `standard`, above the spool and filament windows;
  - `host`: the window;
  - `trapTab`;
  - `onEscape`: its Cancel;
  - `initialFocus`: Cancel at step 1, the typed box at step 2.

  Its words and its two steps stay.
- These go: the two in-window divs, the Bootstrap keyboard suspension and its own Escape handlers. The windows' own Escape code (`:3512-3520`) asks `window.getOverlay` instead of reading the div.
- Its typed box's Enter asks `window.enterIsAScan()` first, so a scan's Enter never presses Delete forever.
- `data-fcc-cover` has no user left. Its rule leaves `mouseCouldReach` (`scripts.html:347-349`) and CLAUDE.md's Enter paragraph. The two cover tests in `test_enter_presses_buttons_50_6.py` change to the top-overlay rule.
- Use the named text sizes. A ? for this dialog is Group 73's.

### 62.9 — Eject All, on Derek's answer
- **(a)** Remove the dead `generateSafeQR('qr-eject-all-list', …)` (`:1329`) and fix the comment (`:76-81`).
- **(b)** Remove:
  - the DANGER ZONE and its QR;
  - `ejectAllFromScan`, `triggerEjectAll` and `_runEjectAll`;
  - `clear_location`, with its write-surface row and its `WRITE_SITES` registration;
  - the shortcut and help lines.

  The ladder answers `ejectall` with "Eject All was removed, so nothing was moved." The Eject All tests are retired or rewritten.
- **(c)** The list view draws the same ☢️ DANGER ZONE after its spools, for a cart, a shelf or a toolhead that holds at least one spool.
  - Never for a room or a Printer row. The page mirrors `eject_all_block_reason`, using `window.isHeadOrPrinterType` and the room rule, and the click still asks the server first.
  - It is refused during an audit (62.7 b).

## Tests

Every new test must fail on `3388c7d` (check with `git archive` into a scratch folder). Hermetic tests use `isolated_page` (the real modules in a browser with no network) or the node driver (`run_js`). No member needs dev's data.

- **62.1:** offline tests of `resolve_scan`.
  - Every command answers itself, `CMD:EJECTALL` included, alone, with a key in front (`qCMD:EJECTALL`), in lower case and with a label glued after.
  - For every pair of command texts where one holds the other, the longer wins.
  - The two stubbed tests take their answer from `logic.resolve_scan`.
- **62.2:** `isolated_page`, with the real `inv_core.js`, `inv_cmd.js` and `inv_quickswap.js`. With each yes / no door's question open, and with the Quick-Swap confirm open:
  - a slot label is refused: no `/api/identify_scan`, the 7 s warning, the status line;
  - a bare `CMD:CANCEL` cancels it (onCancel, no request);
  - its own `CMD:CONFIRM:<sid>` answers it;
  - answering it, Escape, the host closing and a superseded question each free scans again;
  - two open questions hold scans until both are answered;
  - during an audit, a bare `CMD:CANCEL` cancels the question, not the audit.

  `tests/test_head_load_confirm_js.py` is the three-way's twin.
- **62.3:**
  - Playwright on the real dashboard, with every non-GET answered in the browser (the audit sweep's pattern): a real double click on each door at the five sizes. The second click answers nothing and sends nothing.
  - Hermetic: the yes and the store take no click for 700 ms; Cancel takes one at once; Enter and the QRs answer at once; a door with `armAfterMs: 0` takes the click at once.
- **62.4:**
  - `isolated_page`: after a click on a question's text or background, Enter, the arrows and Tab answer it. Cover the yes / no, the three-way, Done's question and the record-source question.
  - With the focus on the page, Tab comes back into the question and wraps.
  - Tab stays inside Bulk Move's panel, the empty-weight prompt and each newly trapped overlay.
  - In the Quick-Swap confirm and the slot picker, one Tab moves one step.
  - An offline source canary (say `tests/test_overlay_tab_canary.py`): a `mountOverlay({` call with `trapTab: false` and no `// own-tab:` comment is red.
- **62.5:** `isolated_page`, with the real scan accumulator on a fake clock (as `tests/test_slow_scan_slash_js.py` lifts it).
  - N under the list, Escape, then Enter within 500 ms: no scan of "n", no request, no toast.
  - The same with two keys and an Enter within 2 s.
  - A scan read under the list still goes out whole.
- **62.6:** node or `isolated_page`.
  - The card's QR text is the new code.
  - Its scan, with the window open on that place, deposits the spool shown only, and opens the picker for that one spool on a box or a Printer row.
  - With the window closed, on another place, during an audit or during a bulk move, it is refused and said, and nothing is sent.
  - The place's own `LOC:` label still files the buffer.
  - Extend `tests/test_deposit_card_race_e2e.py`.
- **62.7:**
  - **(a)** The window's QR closes it with an audit or a bulk move running, and sends nothing. `CMD:DONE` still asks the audit's Done.
  - **(b)** EJECT ALL's button and a card's 🗑️ during an audit are refused with the scan's words, and make no request (beside `tests/test_audit_page_58_js.py`'s ALWAYS family). `CMD:EJECTALL` during a bulk move opens no safety prompt.
  - **(c)** The loading and message views draw the CANCEL QR.
  - **(d)** Offline: each entry's `ts` increases. Hermetic: lines at 23:59:58 and then 00:00:01 raise the pill after midnight, and an old stored time doesn't hide new lines.
- **62.8:** `tests/test_delete_ui_e2e.py` on the new overlay. Keep the ids the tests use on the mounted root.
  - Both steps and the typed confirm work.
  - Escape closes only it, and the window stays.
  - Tab stays inside it, and the host closing removes it.
  - The window's buttons can't be pressed under it.
  - The DELETE request is routed and never reaches dev.
- **62.9**, per Derek's answer:
  - **(a)** `renderList` makes no QR call for a missing target.
  - **(b)** Every door is gone; an old label is refused aloud and never turns on Eject mode; the write-surface canary is updated.
  - **(c)** The list view's DANGER ZONE shows on a cart, a shelf and a toolhead, and on no room or Printer row; its click asks the server first.
- **Standing orders that apply:**
  - the contrast guard and the text-size guards for every new or moved surface: the yes / no's status line, the picker's CANCEL QR in its two views, the ported delete question, and a new DANGER ZONE;
  - named text sizes only;
  - the keyboard idiom and scanner-safe keys (`enterIsAScan`, `scanIsArriving`, `personMayPress`, `fccShortcutsUp`);
  - `mountOverlay` for any overlay;
  - the help texts and their tests (`tests/test_help_texts_55.py`, `tests/test_help_buttons_55_js.py`) for every changed line, with no scan code in a help line;
  - plain words and made-up examples in anything a person reads;
  - the toolhead-Type canary for any Type test (62.9 c);
  - the load-order canary for any new top-level read;
  - Activity Log lines escaped (`escLog`);
  - no new Spoolman write, so `tests/test_spoolman_write_sites.py` changes only with 62.9 (b).
- **The full sweep before merging** (every member touches the frontend), and one review round with the review checklist's lenses: a scanner is a keyboard; a double click's second press; stacked overlays.

## Done when

- A scan of any text holding `CMD:EJECTALL` never turns on Eject mode.
- No question lets a scan start a second move behind it, and a bare `CMD:CANCEL` cancels whichever question is open.
- A double click answers no question at the laptop sizes.
- A click on a question's background leaves its keys working, and Tab never leaves the overlay on top.
- A key left under the ⌨️ list never makes the next Enter a scan.
- DEPOSIT HERE's QR does what its click does.
- The location window's Done / Sync QR closes it, whatever else is running.
- EJECT ALL and a card's 🗑️ wait for an audit to end.
- The slot picker shows its CANCEL QR from the start.
- The 📡 pill counts lines across midnight.
- The delete question is a `mountOverlay`.
- Eject All is as Derek chose.

## Risks

- **Scans refused that were meant.** After 62.2 a scan is refused while any question is open. Its own QRs and `CMD:CANCEL` must still answer it, and the refusal says why on the question.
- **Every question at once.** 62.3's arming touches every door, and about 40 test files press a yes; they need the seam or a 700 ms wait. 62.4's default touches 19 overlays, and each gets one look for rows that rove.
- **Two Tab handlers.** An overlay that cycles Tab on the document must opt out, or the focus moves twice. The canary names them.
- **The delete flow.** It is the one action with no Undo. Its port keeps every step and word, and its tests never send the DELETE.
- **62.9 (b)** removes a write path: CLAUDE.md's write-surface table and the write-site canary change in the same commit.
