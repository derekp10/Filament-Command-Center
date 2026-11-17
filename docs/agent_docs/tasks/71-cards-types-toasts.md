# Group 71: 🃏 Cards, Types & Toasts

**Branch name (when started):** `feature/group-71-cards-types-toasts`
**Estimated effort:** MEDIUM–LARGE (~13–20 h, 2–3 sessions, with this project's usual ~30% overrun counted in), plus one review round and the full run (~70 min). The refresh guessed SMALL–MEDIUM (~5–8 h). Grounding found more in three members:
- 71.2's pattern also runs through the views that hold the cards (the Quick-Swap grid and its deposit question, the Location Manager's title and READY TO SLOT card);
- 71.4 is 90 reads of a row's Type in 9 backend modules, and about 35 hand-written Type tests in 7 page modules;
- 71.6's 2 s default hides 19 error toasts, and a toast never takes a mouse click (71.6b).

Per member: 71.1 ~1–1.5 h · 71.2 ~3.5–5 h · 71.3 ~0.5–1 h · 71.4 ~5–7.5 h · 71.5 ~1–1.5 h after Derek's pick · 71.6 ~2–3 h (with 71.6b) · 71.7 ~0.25–0.5 h after his pick. The two pictures are made in Group 59's session and counted there.
**Risk:** **LOW–MEDIUM.** No Spoolman write changes. The hazards:
- 71.4 rewrites the move engine's one-spool rule, its dryer branch and every other Type test. For the Types on file today nothing changes, but a slip in a mechanical rewrite reaches every move.
- 71.6 changes how long 71 toasts stay up (52 once Group 70 has landed), and 71.6b what a click on any toast does.
- 71.2 escapes values at about 80 places. Escaping FCC's own markup by mistake puts "&amp;" on screen.

> **Status: TODO, filed 2026-11-16** (/refresh-groups; Derek approved the grouping the same day: "otherwise this seems fine"). **Tenth in the recommended order**, in its fifth step with 69 and 70. **Starts ready:** 71.1–71.4 and 71.6 need nothing from Derek but one question at the start (Q1, a click on a toast). 71.5 and 71.7 wait for their pictures in [Group 59](59-design-samples.md)'s picture session (its "pictures for other groups" row). The rest merges without them.
> **Grounded 2026-11-17**, read-only, on `dev` @ `95531a6`. Every member is live. Two are only partly as written:
> - 71.1: no real card can reach the split the item names, because the server never sends the id. Every real card's legacy line is simply empty.
> - 71.6: most callers do pass a duration. The 67 that don't include 19 error toasts.
>
> Grounding also found siblings, now folded in:
> - the Quick-Swap grid, its deposit question, its tap's confirm body and Return's "Nothing to return", and the Location Manager's title and READY TO SLOT card put place ids and Spoolman's names into HTML as they are (71.2);
> - 11 error toasts pass 5 s, under CLAUDE.md's 7 s (71.6);
> - a toast never takes a mouse click: the click lands on what is under it (71.6b, Q1);
> - the Locations table never draws a "(Room)" row's Virtual look (71.5's picture).
>
> Others are listed at the end, for the refresh. Line numbers drift, so re-grep before editing.

**Read first:**
- **Group 70** builds first, and rewrites or removes 19 of the 71 toasts 71.6 counts (listed under 71.6 below). Its 70.4 (a) moves every single-label 🖨️ door's toast, the cards' seven "Added to Print Queue" among them, into `addToQueue(item, {say: true})` at 4 s; 70.3 removes `printLabel` and its five; 70.1 and 70.4 (b) rewrite the queue window's. Re-count 71.6's list when this group starts. 70.4 (a) also gives READY TO SLOT's 🖨️ `jsArg`, which 71.2 lists too.
- **Group 66** touches `inv_wizard.js`, where 71.2's handler canary finds ten lines to fix or mark. 66 builds first.
- **Group 59.8** (one design for the five spool cards) may redraw the cards 71.1 and 71.2 change. Build 71.1 and 71.2 regardless; 59.8 keeps the legacy line and the escaping.

**Related, not members:** Printer Status puts its heads' ids into its HTML as they are (found while grounding, below).

## Items covered (quoted from `Feature-Buglist.md`)

The quotes are taken from `dev` 95531a6 (buglist lines 447, 448, 449, 460, 466, 494 and 496), without their routing tags.

| # | Buglist item | Direction |
|---|---|---|
| **71.1** | *"🟡 A card's legacy-ID line shows "[Legacy:" instead of the ID (found 2026-10-30, Group 50.8's picture). `SpoolCardBuilder`'s main card (ui_builder.js, its weight row, `.fcc-subtext`) shows `info.line1.split(' ')[1]`, and `line1` is "#77 [Legacy: L-12]", so a spool with a legacy id reads "[Legacy:". Show the id itself (`item.details.external_id`), and pin it."* | **Live, but not as written.** The split is real (`ui_builder.js:586`), but no real card can reach it: the server never puts `external_id` in a card's `details` (`spoolman_api.py:2471-2483`), so every real card's legacy line is empty. The "[Legacy:" was on a test's staged card (`tests/test_text_on_filament_halo.py:73`). The server sends the id; the card shows "Legacy: 42". |
| **71.2** | *"🟡 A card's place IDs go into its HTML and its click handlers as they are (found 2026-11-03, Group 58's review). Group 58 escaped the Spoolman names a card draws (`SpoolCardBuilder.esc`, ui_builder.js; the item above), but not its LocationIDs: `item.location` in the 📍 badges and their `openManage('…')` onclick, `deployed_to`, and the Quick-Swap card's toolhead and `data-` attributes. They are FCC's own ids, but a spool's `location` in Spoolman is free text, so one typed there with a `'` or a `<` would break the click or the markup. Wanted: the inline-handler rule for them (`SpoolCardBuilder.jsArg`, or the `[^A-Za-z0-9_.:\-]` strip CLAUDE.md allows a LocationID) and `esc` in the markup, pinned with a location holding `'` and `<b>`. Also (2026-11-16, found while writing Group 67's task file): Merge's windows put Spoolman's names into their HTML unescaped (`inv_details.js` ~:3229, ~:3328-3332; the datalist at ~:3214 escapes only quotes), and the filament window's spool rows put their place in the same way (~:540), against CLAUDE.md's "Spoolman's free text in a card is HTML text"."* | **Live**, at every site the item and its note name. A card's `slot` is free text too, and the RETURN button passes it unstripped (`ui_builder.js:234`). The same pattern in the views that hold these cards is folded in (Claude's call). `jsArg` for every value in an inline handler (the strip goes), `esc` in markup, and a canary for the handler half. |
| **71.3** | *"🟡 The Location Manager's group headings guess an icon from Derek's own ID names (found 2026-11-09, Group 53.1). `inv_loc_mgr.js` (~:1282) picks 🖨️ or 📦 for a group heading by whether its ID holds PRINTER, CORE, XL or MK anywhere (a dryer box whose ID holds XL gets 🖨️), against the "no setup's own names" standing order, and puts `gLoc` unescaped into innerHTML and an inline onclick (use the row's Type, and `SpoolCardBuilder.jsArg` / an escape)."* | **Live** (`inv_loc_mgr.js:1291-1298`). On dev's data (a copy of prod), the guess is wrong only for the Core One INDX: `RCOI` and its heads `RCOI-1` to `RCOI-8` hold none of the four words, so opening RCOI shows each head's group under 📦. No dryer box id on dev holds XL; the item's example is a made-up one. The icon comes from the row's Type. |
| **71.4** | *"🟡 One Type rule for every door, and one Printer rule (found 2026-11-09, Group 53's review). Nothing writes a padded Type today (the location editor trims a custom Type; every backend writer writes exact strings), and a re-cased one only when a person types it as a custom Type (see below), so this is latent. The page's head-Type helpers (Group 53.1) trim the Type; `locations_db` trims its head-Type and Printer tests, but most of its Dryer Box tests don't (`get_dryer_box_bindings`, `_set_dryer_box_bindings_locked`, `get_bindings_for_machine` and four more compare untrimmed); the move engine doesn't (`logic._is_single_occupancy`, `_holds_one_spool`, its dryer branch, `box_feeds`, `feed_box`), nor `locations_db.validate_slot_targets` or the slot-label scan's target check (kept untrimmed on purpose until the engine trims). Read the Type through one helper (e.g. `locations_db.row_type(row)`), or strip it once on save. 'Printer' is tested exactly at some backend sites and as `.strip().lower() == 'printer'` at others, and by hand at nine page sites (exact at some, lower-cased at others). The location editor accepts a custom Type that differs from a built-in only in case or spacing (map it back or refuse it). The backend writes the head-or-printer sets out by hand: `TOOLHEAD_TYPES \| {'Printer'}` in `logic._is_single_occupancy` and `spoolman_api._unarchive_destination`, and `TOOLHEAD_TYPES \| {'Printer', 'Room', 'Virtual Room'}` in `logic._pre_box_note` and `_is_plain_place`: name each set once. `inv_cmd.js`'s `_isSingleHeadRow` and `inv_loc_mgr.js`'s `_isOneSpoolHeadRow` are the same function twice."* | **Live, and latent:** dev's 97 rows (prod's, as of 2026-11-13) hold no padded or re-cased Type. Every site the item names is as it says. Room is tested several ways too ('Room' exact at some sites, 'room' lower-cased at others). One read rule on each side, from one list of the Types FCC knows; the editor and the save route map a variant back; the sets named once; one single-head helper; a canary. |
| **71.5** | *"🎨 The Type badge colours read Types by substring, twice (found 2026-11-09, Group 53.1). The badge colour ladder exists in `inv_core.js` (the Locations table) and `inv_loc_mgr.js` (the Location Manager's title), and the two differ (only the Locations table's has a Room rung, and their Virtual rungs draw different badges). Its `t.includes('Toolhead')` never matches the Type 'Tool Head', so Tool Head rows get the grey default badge (MMU Slot and No MMU Direct Load rows are red, from the 'MMU' rung) while Printer rows are purple, and `t.includes('MMU')` colours a custom 'MMU Buffer' red like an MMU Slot. Both lines carry `// toolhead-type-ok: a badge colour only` for now. A look change: needs a before / after picture for Derek."* | **Live**, as written. Also: in the Locations table a "(Room)" row's Type, 'Virtual Room', takes the Room rung before the Virtual one, so only the Unassigned row is ever dashed. **Picture first (Q2);** built after Derek picks. |
| **71.6** | *"🟡 `showToast`'s default is 2 s; CLAUDE.md asks 4 s for a success toast (found 2026-11-09, Group 54's review). Most callers pass no duration, so a plain "Updated Spool #57" is up for 2 s. Either make 4 s the default, or correct CLAUDE.md; check the callers that rely on the short one."* | **Live, partly as written.** The default is 2 s (`inv_core.js:1572`), but most callers pass a duration: 67 of 401 `showToast` calls don't, plus 4 through cancel_review.js's own `toast`. Among them are 19 **error** toasts that last 2 s, against CLAUDE.md's 7 s. The default goes by type. The 11 error toasts that pass 5 s go to 7 s. **71.6b** (found while grounding): a toast never takes a mouse click (Q1). |
| **71.7** | *"🎨 A toast holding an unbroken string runs past its edge (found 2026-11-09, Group 54's review). `.toast-msg` (global.css) has no `overflow-wrap`, so any caller that toasts Spoolman's raw error (CLAUDE.md's pattern (b)) can overflow; R4-2 put the weigh screens' in words. `overflow-wrap: anywhere` would fix it but touches every toast (and their min-content widths), so check its look first."* | **Live** (`global.css:992-1002`). In this layout `#toast-container` has a width of its own, so a break opportunity is used only where a run can't fit: a toast that fits today draws exactly as it does. **Picture first (Q3).** |

## Decisions

### For Derek: three questions, asked cold, one at a time

**Q1 (71.6b), at the group's start: what a click on a toast does.**
- **What it is.** A toast is the big black message box in the middle of the screen after a scan or a save ("Updated Spool #57", "❌ Slot 9 invalid for LR-MDB-1"). Its code is written to clear it on a click: it has a "Click to dismiss" tooltip and a hand cursor. But the layer the toasts sit in lets every click through. A click on a toast never reaches it: the click lands on whatever is under the toast, and the toast stays up. (Escape does clear the newest toast.)
- **Where.** Every toast, in the middle of the screen, over whatever window is open.
- **Example.** You have #57 in your scan buffer and LR-MDB-1's window open. A scan of a wrong slot label raises a red "❌ Slot 9 invalid for LR-MDB-1 (has 4 slots)" over the slot grid. You click the toast to clear it. If the click lands on an EMPTY slot tile under it, FCC puts #57 in that slot, as if you had clicked the slot (a slot that feeds a toolhead loads it there too, asking first only when that toolhead is busy), and the toast is still there. The test that checks the click clears a toast clicks it from code, which a real mouse can't do, so it never saw this.
- **Options.**
  - **(a) A click on a toast clears it and goes no further.** The second click of a double click goes no further either. A toast then covers what is under it until it goes or is clicked: 4 to 7 s for most, up to 12 s for a few error toasts.
  - **(b) Keep clicks passing through.** A toast never blocks anything. The "Click to dismiss" tooltip and its code go, so nothing promises a click. Escape still clears a toast.
  - **(c) As (a), but only for error and warning toasts.** Success and info toasts let clicks through.
- **Recommendation: (a).** The toast does what it says, and a click aimed at a toast can't press something you didn't see. It matters more after this group, because error toasts that go by in 2 s today will stay up for 7 s.
- **If you don't answer: (b).** That is how toasts already behave under a real mouse; only the promise goes. (a) and (c) change what a click does on every toast, so they wait for your yes.

**Q2 (71.5), at Group 59's picture session: the Type badge colours.**
- **What it is.** Every place's Type has a coloured badge. Two pieces of code pick the colour, each its own way, by looking for a word inside the Type.
- **Where.** The 📍 Locations window, in each row's Type column; and a place's own window, beside its id in the title.
- **Example, from your data.**
  - XL and RCOI (Printers) are purple, but their heads XL-1 to XL-5 and RCOI-1 to RCOI-8 (Tool Head) are plain grey: the code looks for "Toolhead", and the Type is "Tool Head".
  - The rooms CR, DR and LR are white in the list and grey in their own windows.
  - The Unassigned row is a dashed outline in the list and white in its own window.
  - A Type you make up in the location editor that holds "MMU" ("MMU Buffer") would be red, like an MMU Slot.
- **Options.**
  - **(a) Heads take their printer's purple.** Every Type gets one badge, the same in both places (the list's white for rooms, its dashed outline for Unassigned). A Type you make up is always grey. On your data, only the 13 head badges change (grey to purple), plus the rooms' and Unassigned's own window titles.
  - **(b) As (a), but heads get a colour of their own:** the red an MMU Slot has today, for every head. Printers stay purple.
  - **(c) Only make the two places agree.** Heads stay grey.
- **Recommendation: (a).** A head is part of its printer, and one look per Type means a badge says the same thing wherever you see it.
- **If you don't answer:** nothing is built; 71.5 stays open in this group, and the rest merges without it.
- **The picture it needs** (made in Group 59's session, at 1600×1300, at Standard and Extra Large):
  - the Locations window's Type column and a place window's title badge, side by side, for XL and RCOI (Printer), XL-1 and RCOI-1 (Tool Head), LR (Room), a "(Room)" row such as PM (Virtual Room), LR-MDB-1 (Dryer Box), a cart, a section, a row, the wall shelf, LR-SD-1 (Sliding Drawer), Unassigned (Virtual) and Unknown;
  - drawn in the sample page only, never saved to dev: an MMU Slot, a No MMU Direct Load, a Storage box, a Shelf, and two made-up Types, "MMU Buffer" and "Toolbox";
  - columns: today's two ladders, then (a), (b) and (c);
  - each badge's contrast ratio under it (the guard's 4.5:1).

**Q3 (71.7), at Group 59's picture session: a toast with a long run of characters.**
- **What it is.** A toast wraps its words at spaces only. A run of characters with no space in it (an error that passes Spoolman's own text, a web address) doesn't wrap: it runs past the right edge of the black box, and off a phone's screen.
- **Where.** Any toast; most often an error that shows Spoolman's text as it came. (Groups 67 and 70 put several of those into words before this group, so a long run gets rarer, but any toast that passes outside text through can still hold one.)
- **Example.** `HTTP 422: {"detail":[{"type":"missing","loc":["body","filament_id"],"msg":"Field required"}]}`: a refusal in Spoolman's own shape (made up), as the 🖨️ Queue Label button toasts one today when Spoolman refuses its flag write. Everything from `{"detail"` to `"msg":"Field` is one run, about 70 characters, and at the toast's size it runs off the box on a laptop. On a phone, any run longer than about 13 characters does.
- **Options.**
  - **(a) A long run breaks at the box's edge** and goes on on the next line. A toast that fits today draws exactly as it does today.
  - **(b) As (a), and a toast longer than about three lines uses smaller text,** so a long error takes less of the screen.
  - **(c) Leave it.**
- **Recommendation: (a).** It fixes the overflow and changes nothing else. (b) is a new look for long messages, better decided in a wider look at toasts.
- **If you don't answer:** nothing is built; 71.7 stays open in this group.
- **The picture it needs** (drawn with the real `showToast` and `global.css` in an isolated page; no dev data), at 1600×1300 and a 390×844 phone, at Standard and Extra Large:
  - three toasts: the Spoolman error above; a connection error holding a web address (made up: `Couldn't save Spool #57: HTTPConnectionPool(host='spoolman.local', port=7912): Max retries exceeded with url: /api/v1/spool/57?allow_archived=true`); and a short "Updated Spool #57";
  - columns: today, (a) and (b), with the short toast marked as pixel-identical under (a).

### Claude's calls (for veto)

- **71.1, the legacy line.**
  - The server sends `details.external_id` from what `format_spool_display` already works out (the spool's own, else its filament's). No new read.
  - The card's reserved line shows "Legacy: 42", escaped. "Legacy" is FCC's own word for it: the display text's "[Legacy: 42]" and Edit Filament's "Legacy / External ID". `.fcc-subtext` takes `var(--fcc-fs-small)` (the same size at Standard, and it then follows the Text size).
  - A grid tile's first line then shows "#77 [Legacy: 42]", as its code and its pin (`tests/test_card_free_text_escaped_js.py:39-41`) always meant.
  - The Location Manager's own copy of `getRichInfo` goes; its READY TO SLOT card uses `SpoolCardBuilder.getRichInfo`.
  - It is a look change on most cards (135 of 191 filaments on dev carry a legacy number, per Group 69's grounding), so the merge's picture walk shows a before / after, as 54.8's mark was. **Veto option:** leave the line empty and delete the dead split.
- **71.2, one rule for values in a card.**
  - Every value in an inline handler goes through `SpoolCardBuilder.jsArg`, a place id too. The `[^A-Za-z0-9_.:\-]` strip (`ui_builder.js:87`, `:93`, `:94`) goes: it changes an id holding a space ("Bin 2" would open "Bin2"), and a LocationID may hold one (CLAUDE.md, Group 61).
  - Every value in markup, text or attribute, goes through `esc`. A `data-` attribute escaped this way reads back whole through `dataset`.
  - Folded in, the same class in the same views: the Quick-Swap grid, its tiles, its deposit question, its tap's confirm body, Return's "Nothing to return" and its bind list (`inv_quickswap.js`); the Location Manager's title and READY TO SLOT card (`inv_loc_mgr.js`).
  - A canary for the handler half (`tests/test_inline_handler_args.py`). The markup half has no reliable source rule, so each surface is pinned by a test.
  - Printer Status stays out (a different widget; listed for the refresh).
- **71.3, the icon.** 🖨️ for a head or a Printer row (`window.isHeadOrPrinterType`, through 71.4's rule); 📦 for any other row and for a place with no row. No new icons: more icons would be a look change. The heading is built with DOM calls: its id as text, and "Manage / View" as a button with a listener that opens the row's own LocationID (the group's id when no row matches). No inline handler.
- **71.4, one Type rule.**
  - **The rule:** a Type is read trimmed, with inner runs of spaces made one, and matched without case against the Types FCC knows. A match reads as that Type's own spelling; anything else is a custom Type, as typed (trimmed). It never recognises a row less than today: every site that matches a Type now still matches it.
  - This reverses one small builder's call of Group 53 (head Types read with case, 'printer' without). One rule needs one answer, and recognising more is the safe direction.
  - One list of known Types on each side: `locations_db.KNOWN_TYPES` (the existing constants, the location editor's other built-ins, and the synthesized rows' Types), and the page's copy in the `@fcc-toolhead-types` block, pinned equal by the canary, as `TOOLHEAD_TYPES` is.
  - Named sets in `locations_db`: `HEAD_OR_PRINTER_TYPES`, `ROOM_TYPES`, and `NOT_A_PLAIN_PLACE_TYPES` (a head, a printer or a room).
  - The location editor and the save route map a variant back to the built-in. No refusal and no question: the person meant the built-in.
  - Nothing migrates the rows on file. The read rule covers a hand-edited one, and dev's rows (prod's copy) need nothing.
  - One single-head helper on the page, `window.isOneSpoolHeadRow(row)`, replaces `_isSingleHeadRow` and `_isOneSpoolHeadRow`.
  - A canary (`tests/test_type_reads_one_rule.py`), with a marker for a line that must read the raw Type: the shelf migration's aliases, and a message quoting what a row holds.
- **71.6, toast durations.**
  - `showToast`'s duration defaults by type: error and warning 7 s, success and info 4 s. That is the norm the explicit callers already follow: 101 of 122 errors and 72 of 97 warnings pass 7 s; 47 of 58 successes and 26 of 45 infos pass 4 s.
  - The 11 error toasts that pass 5 s go to 7 s.
  - Exceptions are written out at their call: the DROP MODE and EJECT MODE notices take 4 s (a mode notice, not a failure; the deck tile shows the mode). "🖨️ Requesting Label..." would keep 2 s (its result toast follows at once), but 70.3 removes it with `printLabel`; only if it is still there.
  - A canary: an error toast with a literal duration under 7 s is red.
- **71.5 and 71.7:** nothing is built before Derek picks.

## Today's code (anchors, `dev` @ `95531a6`)

Line numbers drift, so re-grep before editing.

### 71.1: the legacy line
- **The card.** `SpoolCardBuilder.getRichInfo` is `ui_builder.js:55-70`: `legacy` reads `d.external_id` (`:57`), and `line1` is `#${item.id} ${legacy}` (`:65`).
  - The core card's weight row shows `info.line1.includes('Legacy') ? info.line1.split(' ')[1] : ''` (`:586`), so a staged id reads "[Legacy:".
  - The grid tiles draw `esc(info.line1)` (`:286` deployed, `:312` stored).
- **The server never sends the id.** `spoolman_api.format_spool_display` (`:2404`) works it out (`ext_id`, `:2409-2413`: the spool's own, else its filament's, quotes stripped, "None" read as none) and puts it only in the display text ("[Legacy: 42]", `:2446`). Its `details` (`:2471-2483`) has no `external_id`. The search builder's spool cards call it (`:3050`); its filament cards build their own `details` (`:3086-3093`), and a filament card shows no legacy line anyway.
- Nothing else sets it: no backend module and no page module writes `details.external_id`. Only two tests stage it: `tests/test_text_on_filament_halo.py:73` (the picture Group 50.8 saw) and `tests/test_card_free_text_escaped_js.py:28-31` (its `ITEM`).
- **The copy.** The Location Manager keeps its own `getRichInfo` (`inv_loc_mgr.js:969-982`), used only by the READY TO SLOT card (`:996`, `:1015-1016`).
- **The line's look.** `.fcc-subtext` is `global.css:1351-1356`: 0.85rem typed by hand, `#aaa`, the halo.

### 71.2: values in cards and the views that hold them
- **The helpers.** `SpoolCardBuilder.jsArg` (`ui_builder.js:16-20`) and `esc` (`:31-35`); `escHtml` / `escAttr` are `inv_core.js:1550-1559`.
- **The strip.** `deployedId`, `ownBoxId` and `viewId` (`ui_builder.js:87`, `:93`, `:94`).
- **Handlers holding a place** (`ui_builder.js`):
  - the search 📍 `badgeClick`, `openManage('${item.location}')` (`:180`), and the buffer's (`:500`);
  - the list card's body (`:202`), ✋ PICK (`:247`) and 🗑️ / ⏏️ (`:255`), each `ejectSpool(…, '${locId}', …)`;
  - ↩️ RETURN, `returnDeployedSpool(…, '${item.slot || ''}', …)` (`:234`; the slot is not stripped);
  - the grid's ↩️, ✋ and ⏏️ (`:292`, `:296`, `:318`, `:322`);
  - the Quick-Swap card's ⏏️, `ejectSpool(…, '${box}', false)` (`:474`).
- **Markup holding a place** (`ui_builder.js`):
  - 📍 badges: `📍 Deployed: ${item.location} (Slot ${item.slot})` and `📍 ${item.location}` (`:190-191`, `:505-507`);
  - "Currently at" `${item.deployed_to}` (`:221`, `:282`);
  - the Quick-Swap card: `→ ${toolhead}` (`:433`), `data-box` / `data-slot` / `data-toolhead` (`:447`), `Slot ${slot}` (`:456`), and `titleAttr` / `safeLabel`, which escape quotes only (`:426-427`).
- **Where the values come from.** `spoolman_api._build_location_match` (`:2490`): `location` is the spool's Spoolman location, or its `physical_source` for a ghost; `deployed_to` is its location; `slot` is `container_slot` or `physical_source_slot` (`:2553-2557`). All three are Spoolman text.
- **The Quick-Swap view** (`inv_quickswap.js`):
  - the box header: `openManage('${boxId}')`, its title and its text (`:314-323`);
  - `_attachedLabel`: titles, `data-box`, `data-toolhead` (`:25-38`);
  - the tiles (`:327-417`) and the Printer Pool tiles (`:436-492`): titles, `data-why`, `data-box` / `-slot` / `-toolhead`, `→ ${th}`, and the deposit tile's `bsDisplay`, a Spoolman display with only its quotes escaped (`:378-384`; the pool's, `:464-477`);
  - the deposit question: `box`, `slot` and `toolhead` from the tile's `dataset` and `bsDisplay` (`:967-970`), into an HTML body (`:1097-1110`);
  - the tap's confirm body: `'This moves that spool onto <b>' + opts.toolhead + '</b>'` (`:1218`), the toolhead read back from the tile's `dataset`;
  - Return's "Nothing to return" body on a printer with no head loaded: `No toolhead on <b>${vth}</b>` (`:1470`), the view's LocationID;
  - the bind list's `${s.box}` (`:1555`).
  - The Quick-Swap confirm itself escapes its title and spool label already (`:597`, `:1215-1216`, Group 50.4), and Return's other messages escape their head (`:1321-1374`).
- **The Location Manager** (`inv_loc_mgr.js`):
  - the title: `📍 ${loc.LocationID}` (`:121`) and the Type badge's `${loc.Type}` (`:74`). The Locations table escapes both (`inv_core.js:2644`, `:2694-2695`).
  - the READY TO SLOT card: `${curInfo.line3}` and `${curInfo.line2}`, Spoolman text (`:1015-1016`), and its 🖨️, which strips quotes from the display instead of using `jsArg` (`:1010`).
- **The note's sites** (`inv_details.js`):
  - the filament window's spool rows, in `openFilamentDetails` (`:294`): `<span class="badge …">${location}</span>` (`:540`, from `:524-527`);
  - Merge, `_showMergeFilamentFlow` (`:3160`): the datalist value escapes quotes only (`:3214`), and the picker's text holds `${srcLabel}` (`:3229`);
  - `_showMergeConfirmStep` (`:3305`): `${srcLabel}` / `${tgtLabel}` (`:3328-3332`). Its success toast (`:3387`) goes through `innerText` and is safe.
- **How big the handler class is.** A scan of `static/js` finds 108 `${…}` inside inline handlers: 47 are numbers (`item.id`), 1 is `jsArg`, and 60 are not. Of those 60, 36 sit inside a quoted JS string, the breakable shape: `ui_builder.js` 15, `inv_wizard.js` 17 (Spoolman field keys and the entity name, on ten lines, `:2294-2373`; `:2327`'s is an element id, `${inputId}`), `inv_loc_mgr.js` 2, `inv_quickswap.js` 1, `inv_backlog.js` 1. The other 24 are pre-built handler strings (`badgeClick`, `printHoverClick`, `actionTarget`) and Printer Status's own `_jsArg`.
- **The pin today.** `tests/test_card_free_text_escaped_js.py` (`isolated_page` through `test_slow_scan_slash_js`'s `scan_page`) covers Spoolman's names in every card mode. It holds no place value.

### 71.3: group headings
- `renderList` is `inv_loc_mgr.js:1227-1346`. Spools are grouped by their own `location` (`:1250-1255`). The guess is `:1291-1292`; the heading's markup (`${gLoc}` as HTML, `openManage('${gLoc}')`) is `:1293-1298`. The ☁️ Loose / Floating heading (`:1282-1288`) holds no id.
- `openManage` finds a row by exact id (`l.LocationID == id`, `:212`).
- **On dev** (a copy of prod's rows): a Printer row's view is a list (`_isGridLoc`, `:192`, is false for it), so opening RCOI groups its heads by id, and all nine RCOI rows get 📦. Every other row's guess happens to match its Type.

### 71.4: Type reads
- **The constants.** `locations_db.py:74-107`: `DRYER_BOX_TYPE`, `TOOLHEAD_TYPES` (`:82`), `PRINTER_ROW_TYPE` (`:90`), `WALL_TYPE` / `ROW_TYPE` / `SECTION_TYPE`, the migration aliases (`:105-107`). No Room constant.
- **90 reads of a row's Type in 9 backend modules** (`.get('Type')` and `['Type']`): `locations_db` 38, `logic` 17, `routes_locations` 14, `placement` 8, `routes_bindings` 7, `routes_scan` 3, `print_monitor`, `routes_inventory` and `spoolman_api` 1 each. (`labels_csv.py`'s 'Type' is a label CSV column, written only.) By shape:
  - **Dryer Box, untrimmed** — `locations_db`: `dryer_bindings_are_authoritative` (`:543`), `migrate_feeder_map_if_needed` (`:568`), `get_dryer_box_bindings` (`:1886`), `get_dryer_box_slot_order` (`:1898`), `set_dryer_box_slot_order` (`:1916`), `_set_dryer_box_bindings_locked` (`:2084`, `:2116`), `get_bindings_for_machine` (`:2187`). `logic`: `_find_box_slot_feeding_toolhead` (`:866`, the literal 'Dryer Box'), `_feed_slots_for` (`:896`), `printer_row_refusal` (`:1674`), `box_feeds` in `_residents_of` (`:2172`), `feed_box` in `_residents_changed` (`:2448`), the dryer branch ("DRYER MOVE", `:3173`, the literal), `_landed` (`:4352`). Also `placement` `:459`, `:572`; `routes_bindings` `api_all_dryer_box_slots` (`:538`), `_slotless_box` (`:717`), `_return_plan` (`:771`), `_return_choice` (`:883`); `routes_inventory._is_multi_slot_box` (`:577`); the slot-label scan (`routes_scan.py:1674`).
  - **Dryer Box, trimmed:** `locations_db._is_single_slot_dryer_box` (`:1938`), `loose_place_ids` (`:709-710`), `logic._is_dryer_box_row` (`:1359-1360`), `perform_toolhead_delete_cascade` (`:4607`), `routes_locations` `:508`.
  - **Heads, untrimmed:** `logic._is_single_occupancy` (`:1207-1216`), `_holds_one_spool` (`:1219-1235`), `locations_db.validate_slot_targets` (`:1873`), the slot-label scan (`routes_scan.py:1590-1592`; its comment, `:1582-1588`, says it stays untrimmed until the engine trims). `_no_home_unassign_msg` trims (`routes_scan.py:269`).
  - **Heads, trimmed:** `locations_db` `:926`, `:935`, `:1380`, `:1422`, `:1514`; `routes_locations` `:622`.
  - **Printer, with case:** `_is_single_occupancy` (`:1216`), `_holds_one_spool` (`:1237`), `_pre_box_note` (`:1324`), `_is_plain_place` (`:1395`), `spoolman_api._unarchive_destination` (`:704`), `validate_slot_targets` (`:1873`), the slot-label scan (`:1590`). The four middle ones trim first (`_pre_box_note`'s `typ`, `:1323`); the first and the last two don't.
  - **Printer, trimmed and lower-cased:** `locations_db` `:923`, `:1045`, `:1085`, `:1127`, `:1146`, `:1191`, `:1217`, `_is_printer_row` (`:1243-1244`), `:1572`; `logic.perform_toolhead_delete_cascade` (`:4633`); `placement` `:136`, `:582`; `print_monitor._note_printers_missing_credentials` (`:1727`); `routes_bindings` `:218`, `:285`, `:479`; `routes_locations` `:394`, `:410`, `:424`, `:630`.
  - **Room:** 'room' / 'virtual room' lower-cased in `loose_place_ids` (`:712`) and `logic.eject_all_block_reason` (`:1614-1615`); 'Room' exact in `logic._known_room_of` (`:1576`) and `_no_home_unassign_msg` (`routes_scan.py:267`, trimmed); 'Virtual Room' trimmed in `build_locations_response` (`routes_locations.py:283`); 'room' lower-cased in `locations_db`'s `ensure_toolhead_rows` (`:1327`), `migrate_immediate_parent_ids_if_needed` (`:1558`) and the shelf migration (`:1699`).
  - **The sets by hand:** `TOOLHEAD_TYPES | {'Printer'}` (`logic.py:1216`, `spoolman_api.py:704`); `TOOLHEAD_TYPES | {'Printer', 'Room', 'Virtual Room'}` (`logic.py:1324`, `:1395`); `TOOLHEAD_TYPES | {DRYER_BOX_TYPE, PRINTER_ROW_TYPE}` (`routes_scan.py:1590`).
- **The save.** `api_save_location` (`routes_locations.py:344`) refuses only a blank LocationID (`:354-356`); `_api_save_location_locked` (`:366`) stores the Type as sent, lower-casing it only for its Printer guards (`:409-410`, `:423-424`).
- **The page's helpers.** The marked block is `inv_core.js:1790-1796`: `TOOLHEAD_TYPES`, `isToolheadType` (trimmed, with case), `isHeadOrPrinterType` ('Printer' trimmed, with case). Beside it: `isPrinterRowNotHead` (`:1758-1766`, trimmed and lower-cased), `isMultiSlotBox` / `isSingleSlotBox` (`:1770-1776`, 'Dryer Box' exact).
- **The page's other Type tests:**
  - `inv_core.js`: `printerNameForHead` (`:1741`, exact), `printerLabelForTarget` (`:1829`, exact), the Locations tree's `isPrinterRow` (`:2454`, lower-cased), `NO_ADD_CHILD_TYPES` (`:2461-2470`), its Unknown row (`:2475`, upper-cased) and the table's `canEdit` ('Spoolman Native', `:2690`, exact);
  - `inv_cmd.js`: `_isSingleHeadRow` (`:3126-3133`, exact), `_ejectModeLocationScan`'s attached box (`:3159`, exact), `_quickPickItem` (`:3258-3263`, lower-cased), the location-scan branch (`:3710-3728`, lower-cased: 'wall shelf', 'row', 'dryer box');
  - `inv_loc_mgr.js`: `_isGridLoc` (`:192`, exact, marked), `renderFeedsSection` (`:698`), `_isOneSpoolHeadRow` (`:1199-1207`, the same as `_isSingleHeadRow`), `handleSlotInteraction`'s MMU Slot (`:1523`, marked) and `_doAssignFinalize`'s (`:1652`, marked), `_ejectToastText`'s list of Types (`:1880-1884`, exact), `_populateParentSelect` (`:2330-2332`), `openEdit` (`:2392-2393`, exact), `_inferChildDefaults` (`:2694-2702`, a `switch` on the lower-cased Type), `_TYPE_ABBR` / `_typeSegmentAbbr` (`:2706-2716`, keyed by it) and the parent tree picker's filter (`:2856-2857`, exact 'Virtual', 'Virtual Room', 'Unknown');
  - `inv_quickswap.js`: 'Printer' through the file's own constant `PRINTER_TYPE` (`:17`), exact, at `:166`, `:1236`, `:1450`, `:1461` and `:1726`;
  - `inv_details.js:1026-1031` and `inv_wizard.js:1881-1886` (lower-cased 'virtual', 'wall shelf', 'row'); `wizardIsHeadOrPrinterRow` (`inv_wizard.js:3851-3860`, lower-cased);
  - the badge ladders (71.5).
  - The other page reads (`inv_audit_find.js:279`, `inv_cmd.js:4201`, `inv_loc_mgr.js:1453`, `:1550`, `:1567`, `_isPrinterTopologyType` at `:3022`) already go through the block's helpers.
- **The editor.** `_LOC_BUILTIN_TYPES` is `inv_loc_mgr.js:2243-2258` (14 Types, the head Types marked). `_populateTypeSelect` (`:2278-2311`) already matches a Type to a built-in without case (`:2282`, `:2306`), so the dropdown shows "Dryer Box" for a stored "dryer box". `saveLocation` (`:2430-2451`) sends a custom Type trimmed only (`:2443-2445`) and keeps it in `fcc.locMgr.customTypes` (`_addLocCustomType`, `:2264-2272`).
- **The canary today.** `tests/test_toolhead_types_one_list.py` is green at `95531a6` (101 tests, run offline 2026-11-17). Its helper pins (`VALUES`, `:791-793`; `test_the_helpers_behave`, `:810-826`) say 'tool head', 'TOOL HEAD', 'Tool  Head', 'printer' and 'PRINTER' are no head and no Printer, and that the block adds exactly three window names.
- **On dev** (97 rows, prod's as of 2026-11-13, plus dev's test rows): Cart 30, Dryer Box 30, Tool Head 13, Section 12, Row 4, Room 3, Sliding Drawer 2, Printer 2, Wall Shelf 1. None is padded or re-cased.

### 71.5: the badge ladders
- **The Locations table**, `inv_core.js:2618-2644`: `const t = l.Type || ''` (`:2623`), Dryer (`:2624`), Storage, MMU (`:2626`, marked), Wall Shelf (`:2631`), Row, Section, Shelf, Cart, Printer or Toolhead (`:2636`, marked), Room (`:2637`), Virtual (`:2639`, dashed), Unknown (`:2642`). The badge escapes its Type (`:2644`).
- **The Location Manager's title**, `inv_loc_mgr.js:56-74`: the same rungs to `:69`, then Virtual (`:70`, white), Unknown (`:72`). No Room rung, and the badge doesn't escape its Type (`:74`).
- **The synthesized rows' Types** (`routes_locations.py`): 'Spoolman Native' (`:82`), 'Virtual Room' for a prefix with no row (`:222`; on dev PM, PJ, USS, INBXX and TST), 'Virtual' for Unassigned (`:249`), 'Unknown' (`:320`).
- **Pins.** The visual baseline `tests/__screenshots__/chromium-1600x1300/locations-modal-default.png` holds today's badges.

### 71.6: toasts
- `showToast` is `inv_core.js:1572-1592`: `duration = 2000` by default (`:1572`), `innerText` (`:1577`), a pointer cursor and "Click to dismiss" (`:1580-1581`), a click listener (`:1589`), removal 300 ms after a dismiss (`:1585-1588`). The Escape ladder (`:1600-1641`) clicks the newest toast from code.
- **Who takes the 2 s default.** 67 of the 401 `showToast` calls pass no duration (two more mentions sit in a comment, `inv_core.js:1594-1596`): 19 error, 16 success, 7 warning, 7 info and 18 untyped. cancel_review.js's own `toast` (`:44-46`) adds 4 more (`:1288`, `:1722`, `:1744`, `:1788`). By file:
  - **errors (19):** `inv_cmd.js` 3798, 4599, 4603, 4627; `inv_details.js` 92, 291, 312, 650, 1810, 2409, 2996; `inv_loc_mgr.js` 319, 1668, 1940; `inv_weigh_out.js` 979, 1019, 1346, 1400; `inv_queue.js` 294;
  - **warnings (7):** `inv_cmd.js` 98, 377 (DROP MODE), 381 (EJECT MODE), 3804; `inv_loc_mgr.js` 2009, 2017, 2037;
  - **untyped, as info (18):** among them `inv_cmd.js:4589` ("🖨️ Requesting Label..."), the cards' seven 🖨️ "Added to Print Queue" (`ui_builder.js:169`, `:204`, `:268`, `:436`, `:484`; `inv_details.js:557`; `inv_loc_mgr.js:1010`), `inv_cmd.js` 96 / 102 / 3759 and `inv_queue.js` 81 / 221 / 241 / 314.
- **Group 70 takes 19 of these 71 first** (it builds before this group): `printLabel`'s five (`inv_cmd.js:4589`, `:4599`, `:4600`, `:4603`, `:4627`; 70.3 removes it), the nine single-label queue doors' and the dead copy's (`ui_builder.js:169`, `:204`, `:268`, `:436`, `:484`; `inv_details.js:467`, `:557`; `inv_loc_mgr.js:1010`; `scripts.html:214`, `:225`; 70.4 (a) moves them into `addToQueue(item, {say: true})`), and the queue window's (`inv_queue.js:81`, `:241`, `:273`, `:294`; 70.1 and 70.4 (b)). Four of them are errors, so 15 error toasts are left.
- **Error toasts that pass 5 s (11):** `duplicate_picker.js:216`; `inv_cmd.js:3587`, `:3595`, `:3597` (slot-scan refusals); `inv_loc_mgr.js:856`, `:863`; `inv_quickswap.js:1650`, `:1655`, `:1691`, `:1696`, `:1782`.
- **The norm the explicit callers follow:** error 7000 (101 of 122), warning 7000 (72 of 97), success 4000 (47 of 58), info 4000 (26 of 45).
- **A toast never takes a click (71.6b).** `#toast-container` (`global.css:904-914`) has `pointer-events: none` (`:913`, since 2026-03-28), and the property is inherited, so `.toast-msg` (`:992-1002`) never gets the pointer: a mouse click falls through to what lies under the toast. The click-to-dismiss came later (`7711a0b`, 2026-04-21). `tests/test_slot_qr_scan_ui_e2e.py::test_ui_toast_click_dismisses_immediately` (`:145-161`) clicks it from code, "to bypass pointer-event hit testing". (By reading the CSS; the build checks it with a real mouse click first.) Its neighbour `test_ui_slot_scan_toast_error_is_long_enough_to_read` (`:131-141`) times the slot-scan refusals, which are 5 s today (`inv_cmd.js:3595`, `:3597`): its "Error duration is 5 s" (`:139`) and its docstring's "8 s to 5 s" (`:132-134`) go stale when 71.6 makes them 7 s.
- **What a fall-through click can do.** In a box's window with a spool in the scan buffer, a click on an EMPTY slot tile puts that spool in the slot at once, with no question from the page (`handleSlotInteraction`, `inv_loc_mgr.js:1516-1524`: `doAssign(…, {pickedSlot, shownEmpty})`); only the engine's own questions (a bound slot whose head is printing or holds another spool) still come.
- **While the ⌨️ list is up,** toasts are drawn over it (`global.css:921-923`, z 20300).
- **The precedent for timing a toast** in a test: `tests/test_weigh_save_failure_toast_js.py` (node `run_js` reads the duration exactly; `isolated_page` checks the toast is still up after 2 s).

### 71.7: the toast's text
- `.toast-msg` is `global.css:992-1002`: 2rem bold, 30px padding, a 4px border, no `overflow-wrap`. `#toast-container` (`:904-914`) is 80% of the window wide, at most 37.5rem, with `text-align: center`.
- A line too long for its box is drawn from its start and runs past the end edge.
- The words a toast holds are the caller's. One that passes Spoolman's text as it came: `addToQueue` toasts `set_flag`'s `msg` (`inv_queue.js:64-66`), which is `LAST_SPOOLMAN_ERROR` ("HTTP 422: {…}", `spoolman_api.py:975`) unchanged (`routes_print_queue.py:197-199`). Merge's "Merge failed: …" (`inv_details.js:3380`) is not one: its route puts each refusal through `spoolman_api.refusal_words`. Group 54's R4-2 put the weigh screens' errors in words, and 67.1 puts `set_flag`'s in words too, so a long run gets rarer; a long id, a file name or any outside text passed through can still make one.

## Design, by member

### 71.1: the card shows the old label's number
- **Server:** `format_spool_display` adds `"external_id": ext_id` to `details` (`''` when there is none). Spool cards from the search builder get it through the same call.
- **Page:** `getRichInfo` also returns `legacy` (the id, or `''`). `line1` is unchanged. The core card's line becomes `${info.legacy ? 'Legacy: ' + esc(info.legacy) : ''}`, with no split. An id holding a space stays whole.
- `.fcc-subtext` takes `font-size: var(--fcc-fs-small)`.
- `inv_loc_mgr.js`'s `getRichInfo` goes; `renderManagerNav` calls `SpoolCardBuilder.getRichInfo`.
- The two tests that stage `external_id` now stage the real shape and need no change.

### 71.2: a place is text in a card, and a JS string in its handlers
- **`ui_builder.js`:**
  - Each handler above passes `${this.jsArg(value)}` with no quotes around it: `openManage`, `ejectSpool`, `returnDeployedSpool` (every argument, the slot too). `badgeClick` and the other pre-built handler strings come out attribute-safe, because `jsArg` already escapes for the attribute, so they are never escaped again.
  - The strip goes; `deployedId` in the grid's ↩️ title goes through `esc`.
  - Each markup value above goes through `esc`: `location`, `slot`, `deployed_to`, and the Quick-Swap card's `box`, `slot` and `toolhead` (its text, its `data-` attributes and `titleAttr`). `safeLabel` uses `esc`.
  - `'${item.type}'` and `'${from}'` become `jsArg` too, for the canary.
- **`inv_quickswap.js`:** every place and Spoolman display above through `esc` (`_escapeHtml`, the file's own, is the same rule) in markup; the box header's `openManage` through `jsArg`. The deposit question escapes `box`, `toolhead`, `slot` and `bsDisplay` as it builds its body, and so do the tap's confirm body (`opts.toolhead`) and Return's "Nothing to return" (`vth`); the tile's `dataset` gives back the raw strings.
- **`inv_loc_mgr.js`:** the title's LocationID and Type through `esc`. On the READY TO SLOT card, `line2` and `line3` go through `esc`, and its 🖨️ passes `display` through `jsArg`, so "Robin's Egg Blue" is queued whole (70.4 (a) makes that 🖨️ change first; check it landed).
- **`inv_details.js`:** the spool row's place through `esc`. Merge's datalist value through `esc`: the browser decodes it back, so a picked option still equals `fmtFilament(f)`, and `&` in a name no longer forms an entity. `srcLabel` and `tgtLabel` through `esc` in both windows.
- **The canary**, `tests/test_inline_handler_args.py` (offline; it reuses the toolhead canary's JS lexer). In `static/js` and the templates' inline scripts, a `${…}` inside a quoted JS string inside an inline handler (`on…="…'${x}'…"`) is red.
  - The fix it names is `SpoolCardBuilder.jsArg` (or a local copy that is the same rule, as Printer Status's `_jsArg`).
  - A line that must keep such a value ends `// handler-arg-ok: <why>`.
  - `inv_wizard.js`'s ten lines (Spoolman field keys, `[a-z0-9_]` only, the entity name, and one element id built from them) take `jsArg`, or the marker if Group 66 has reshaped them. `inv_backlog.js:253` takes `jsArg`.
  - Its docstring lists what it can't see: a handler string built in a variable first and put in the attribute later; a value in markup outside a handler; a handler set with `addEventListener`.

### 71.3: the heading's icon comes from the Type
- For each group: `const row = (state.allLocations || []).find(l => String(l.LocationID || '').toUpperCase() === gLoc.toUpperCase())`.
- Icon: `row && window.isHeadOrPrinterType(row.Type) ? '🖨️' : '📦'`.
- The heading is built with `createElement`: the id goes in with `textContent`; "Manage / View" is a `<button type="button">` whose listener calls `openManage(row ? row.LocationID : gLoc)`. The −/+ toggle keeps its inline handler, which holds no value.

### 71.4: one Type rule
- **Backend (`locations_db`, flat, Python 3.9):**
  - `KNOWN_TYPES`: `TOOLHEAD_TYPES`, `PRINTER_ROW_TYPE`, `DRYER_BOX_TYPE`, new `ROOM_TYPE` 'Room' and `VIRTUAL_ROOM_TYPE` 'Virtual Room', `WALL_TYPE`, `ROW_TYPE`, `SECTION_TYPE`, and the editor's other built-ins ('Storage', 'Shelf', 'Cart', 'Sliding Drawer') and the synthesized rows' ('Virtual', 'Unknown', 'Spoolman Native'). The migration aliases stay separate.
  - `canonical_type(value)`: '' for anything not a string; else trimmed, inner whitespace made one space, then the known Type it equals without case, else the cleaned text. `row_type(row)` is `canonical_type(row.get('Type'))` for a dict, else ''.
  - Named sets: `HEAD_OR_PRINTER_TYPES = TOOLHEAD_TYPES | {PRINTER_ROW_TYPE}`, `ROOM_TYPES = {ROOM_TYPE, VIRTUAL_ROOM_TYPE}`, `NOT_A_PLAIN_PLACE_TYPES = HEAD_OR_PRINTER_TYPES | ROOM_TYPES`.
  - Predicates: `is_toolhead_row`, `is_printer_row` (`_is_printer_row` becomes it; no test patches the old name), `is_dryer_box_row` (`logic._is_dryer_box_row` moves here), `is_room_row`.
  - Every read above goes through them, with module-qualified calls (`locations_db.row_type(row)`). The slot-label scan's check and `validate_slot_targets` read the same rule as the engine, so `routes_scan.py:1582-1588`'s "untrimmed until the engine trims" comment goes.
  - Messages that quote what a row holds (`validate_slot_targets` `:1874`, `_set_dryer_box_bindings_locked` `:2085`, the slot-label scan's log line) keep the raw text, marked `# type-read-ok: <why>`. So do the shelf migration's alias reads (`:1757`, `:1805`).
  - The save route sets `new_entry['Type'] = locations_db.canonical_type(...)` for a non-blank string, before its Printer guards.
- **Page (`inv_core.js`):**
  - The marked block gains `window.PLACE_TYPES` (the known non-head Types, frozen), `window.rowType(type)` (the same rule), `window.isPrinterType`, `window.isDryerBoxType` and `window.isRoomType`. `isToolheadType` and `isHeadOrPrinterType` read through `rowType`.
  - Window properties only (the block's rule), and no head-Type literal outside `TOOLHEAD_TYPES` (the toolhead canary's rule 2).
  - `window.isOneSpoolHeadRow(row)` sits beside `isPrinterRowNotHead`, outside the block. It is today's twins' rule: a head row, or a Printer row whose own `toolheads[]` lists only itself.
  - Every page test above switches. The three marked MMU Slot lines (`:192`, `:1523`, `:1652`) keep their markers: an MMU's slots draw as a grid and number from 0. `inv_quickswap.js`'s `PRINTER_TYPE` constant goes; its five tests call `window.isPrinterType`.
- **The editor.** `saveLocation` sends `window.rowType(custom)` when the typed custom Type is a known one, and `_addLocCustomType` skips a known Type.
- **The canary**, `tests/test_type_reads_one_rule.py` (offline):
  - Backend (AST, `inventory-hub/*.py`): a load of `X.get('Type'…)` or `X['Type']` outside `canonical_type` / `row_type` is red, unless its line ends `# type-read-ok: <why>`; so is a set built from `TOOLHEAD_TYPES` outside `locations_db`.
  - Page (the toolhead canary's lexer): `.Type` or `['Type']`, bare or wrapped in `String(…)` or `(… || '')`, followed by `===`, `!==`, `==`, `!=`, `.toLowerCase(`, `.toUpperCase(`, `.trim(`, `.includes(`, `.startsWith(` or `.indexOf(` outside the marked block is red, unless its line ends `// type-test-ok: <why>`. The wrapped shape matters: ten of today's tests are `String(r.Type || '').trim().toLowerCase() === 'printer'` and its kin (`inv_core.js:1759`, `:1763`, `:2454`, `:2469`; `inv_cmd.js:3259`, `:3710`; `inv_details.js:1026`; `inv_wizard.js:1881`, `:3856`), which a rule on `.Type` followed directly by a compare would miss.
  - A test the lexer can't see is switched by hand: the Type kept in a variable first (`inv_loc_mgr.js:2330`, `:2856`, and the badge ladders until 71.5), a `switch` on the lower-cased Type (`_inferChildDefaults`), a lookup keyed by it (`_TYPE_ABBR`), a list's `.includes(` with the Type as its argument (`_ejectToastText`), a Type compared through a constant of the file's own (`inv_quickswap.js`'s `PRINTER_TYPE`).
  - The block's `PLACE_TYPES` plus `TOOLHEAD_TYPES` equal `locations_db.KNOWN_TYPES`.
  - Its docstring lists what it can't see: a Type kept in a variable first and tested later (the badge ladders' shape until 71.5), a `switch` on it, a lookup keyed by it, a list's `.includes(` with the Type as its argument, a constant standing for a Type, a read through `**row` or `getattr`, a script outside `inventory-hub/*.py`.

### 71.5: one badge per Type (after Derek's pick)
- One function, `window.typeBadgeLook(type)` in `inv_core.js`, returns `{cls, style}` keyed by `window.rowType(type)` exactly, with heads through `isToolheadType`. Both the Locations table and the title call it.
- Colours as Derek picks; a custom Type is grey under (a) and (b). The two `toolhead-type-ok` markers go.
- The title's Type is already escaped by 71.2.

### 71.6: how long a toast stays, and what a click on it does
- **The default.** `showToast(msg, type = 'info', duration)`: a missing or non-finite `duration` takes `{error: 7000, warning: 7000, success: 4000, info: 4000}[type]`, else 4000. A given duration wins.
- **The exceptions,** each with a comment saying why: `inv_cmd.js:377` and `:381` pass 4000; `:4589` passes 2000 if 70.3 hasn't removed it.
- **Re-count first.** Group 70 removes or rewrites 19 of the 71 (above); run the census again on this group's base and work from what is left.
- **The 11 explicit 5 s errors** pass 7000.
- **cancel_review.js's `toast`** passes its `dur` through, so its four calls without one take the type's default.
- **71.6b, by Q1's answer.**
  - (a): `.toast-msg { pointer-events: auto; }`; the container keeps `none`, so the space between toasts still lets clicks through. The click dismisses the toast. A toast dismissed by a click stays in place, see-through and catching clicks, until 700 ms after the press (Group 58's double-press figure), then goes, so the second press of a double click reaches nothing. Escape keeps its ladder.
  - (b): the cursor, the title and the listener go, with a comment saying a toast takes no click. Escape keeps its ladder (it clicks from code; it calls `dismiss` instead).
  - (c): (a) for `toast-error` and `toast-warning` only.
- **CLAUDE.md** says the default by type and the click rule (below).

### 71.7: a long run wraps (after Derek's pick)
- (a): `.toast-msg { overflow-wrap: anywhere; }`.
- (b): (a), plus a `toast-long` class that `showToast` adds to a message over a length to be set from the picture, with a smaller font.

## Tests

Prove every new pin RED on `95531a6` first (`git archive` into a scratch folder). Hermetic first: the node driver (`run_js`) or `isolated_page` (through `test_slow_scan_slash_js`'s `scan_page`, as `test_card_free_text_escaped_js.py` uses it). No member needs dev's data.

- **71.1**
  - New `tests/test_card_legacy_id_71.py` (offline, plain Python): `format_spool_display`'s `details.external_id` is the filament's id, '' when there is none, '' for "None", with quotes stripped. A spool card from the search builder carries it.
  - Extend `tests/test_card_free_text_escaped_js.py`: the search, list and buffer cards show "Legacy: <id>" in `.fcc-subtext`, never "[Legacy:". Its `LEGACY` value (`LEG<legx>1</legx>`) makes no element. A card with no id shows nothing. The grid's "#303 [Legacy: …]" pin stays.
  - The READY TO SLOT card uses the shared `getRichInfo` (its words come out the same).
  - `tests/test_text_on_filament_halo.py` stays green: the line keeps its halo.
- **71.2**
  - Extend `tests/test_card_free_text_escaped_js.py` with a place named `O'Brien <b>Shelf</b>` as `location`, `deployed_to`, `slot`, `locId`, `box` and `toolhead`, in every mode:
    - no `<b>` element, and the text reads whole;
    - each handler (📍 in search and buffer, the list card's body, ✋ PICK, 🗑️ / ⏏️, ↩️ RETURN in the list and the grid, the Quick-Swap ⏏️) calls its function with the exact strings (stub `openManage`, `ejectSpool` and `returnDeployedSpool`, and record their arguments);
    - an id with a space keeps its space.
  - New `tests/test_place_ids_escaped_71_js.py` (`isolated_page`), the same place and a spool named `Robin's <Egg> & Blue`, on:
    - the Quick-Swap grid: the box header and its click, the tiles' `data-` attributes read back through `dataset`, the titles, the deposit tile, the attached label, the deposit question's body, the tap's confirm body, Return's "Nothing to return", the bind list;
    - the Location Manager's title (its LocationID and Type) and its READY TO SLOT card (its 🖨️ queues the display with its apostrophe);
    - the filament window's spool rows;
    - Merge's picker (a filament name holding `"`, `&` and `<b>`: no element, and picking its option still resolves that filament) and its confirm.
  - New `tests/test_inline_handler_args.py` (offline): the rule on the real files, and on synthetic source (a quoted `${x}` in `onclick="…"` is caught; `jsArg`, a number and a marked line pass).
- **71.3:** `isolated_page` (or node, as `tests/test_review_fixes_42_js.py` drives `inv_loc_mgr.js`):
  - `renderList` for a Printer row's view puts its heads (RCOI-1, RCOI-2) under 🖨️;
  - a dryer box whose id holds XL (`PM-DB-XL-L`) goes under 📦, and so does a place with no row;
  - a heading whose id holds `'` and `<b>` reads whole, and its button opens it.
- **71.4**
  - New `tests/test_type_rule_71.py` (offline):
    - `canonical_type` and `row_type` (padding, inner spaces, case, None, a non-dict, a custom Type kept);
    - each rewritten backend function, given ' Dryer Box ', 'dryer box', 'tool head', ' Printer ' and 'room', acts as for the built-in. Prove each first on the built-in, with no change from today;
    - a head row no printer lists, typed ' Tool Head ' or 'tool head': the real engine (`move_engine_harness`) holds it to one spool. Today it files a second spool beside the first;
    - the slot-label scan (Flask test client) accepts a padded box;
    - the save route stores 'Dryer Box' for ' dryer  box ' (the run's own `FCC_DATA_DIR` copy).
  - Page (node, the block lifted as the toolhead canary does): `rowType`, `isPrinterType`, `isDryerBoxType`, `isRoomType` and `isOneSpoolHeadRow`. The editor's `saveLocation` sends 'Dryer Box' for a custom ' dryer  box ' and keeps no custom Type (node with `fetch` stubbed, or `isolated_page`).
  - New `tests/test_type_reads_one_rule.py`: its rules on the real files and on synthetic source.
  - **Pins changed on purpose:** `tests/test_toolhead_types_one_list.py`'s `VALUES` verdicts for 'tool head', 'TOOL HEAD', 'Tool  Head', 'printer' and 'PRINTER', its `added` list, and its docstring's "compare it untrimmed" note.
  - Run the move and binding families after the rewrite: `test_toolhead_resident_eject_21_3.py`, `test_undo_last_move_41_4.py`, the single-slot families (`test_single_slot_lifecycle_js.py` and the 42 files), `test_slot_targets_reader_migration.py`, the placement and Return tests.
- **71.5** (after the pick): hermetic. Every known Type gets the same badge in the table and the title; heads as picked; 'MMU Buffer' and 'Toolbox' grey; the two markers gone with the toolhead canary still green. `tests/test_contrast_guard.py` scores every badge. `locations-modal-default.png` is recaptured on purpose (`UPDATE_VISUAL_BASELINES=1`).
- **71.6**
  - Node (`run_js`, which reads the duration exactly, as `test_weigh_save_failure_toast_js.py` does): with no duration, error 7000, warning 7000, success 4000, info and none 4000; a given duration wins; cancel_review's `toast` with none takes the type's.
  - New `tests/test_toast_durations.py` (offline): no `showToast` with type 'error' and a literal duration under 7000, on the real files and on synthetic source.
  - 71.6b under (a) or (c): `isolated_page` with the real `global.css`. A real `page.mouse.click` at a toast's centre over a button clears the toast, and the button hears nothing; a double click's second press reaches nothing; Escape still clears the newest toast. `test_ui_toast_click_dismisses_immediately` clicks with the mouse. Under (b): a toast takes no pointer events, nothing says "Click to dismiss", and that test becomes "a mouse click on a toast reaches what is under it" (its click from code would find no listener). Either way `test_ui_slot_scan_toast_error_is_long_enough_to_read`'s comment and docstring say 7 s.
- **71.7** (after the pick): `isolated_page` with the real `global.css`. A toast holding a 70-character run keeps its text inside its box (`scrollWidth <= clientWidth`) at 1600 px and at 390 px; a short toast's box is the same size as before.
- **Standing orders that apply** (CLAUDE.md):
  - the contrast guard for every changed surface (the badges; the legacy line keeps the approved halo, `tests/test_text_on_filament_halo.py`);
  - named text sizes only (`.fcc-subtext`; `tests/test_text_size_floor.py`);
  - no new key, so no new shortcut; the heading's button is a real button Tab reaches;
  - no new overlay;
  - plain words, and no setup's own names in what a person reads ("Legacy: 42" is the person's own data);
  - the toolhead-Type canary (71.4 and 71.5 change it on purpose); the load-order canary (the new helpers are window properties read when the code runs);
  - module-qualified calls and Python 3.9 in the backend;
  - no Spoolman write and no route change, so `tests/test_spoolman_write_sites.py` and `tests/test_route_table_pin.py` don't change.
- **The full run before merging** (every member touches the frontend), after one review round. Use the checklist's lenses (`docs/agent_docs/review-checklist.md`): "a double click's second press" (71.6b), "spools and places" (71.4), "what a person reads" (71.1, 71.2, 71.6).

## Done when

- A spool card shows its old label's number, never "[Legacy:".
- No place id or Spoolman name reaches a card's HTML, or the HTML of the views that hold the cards, as it is. A place named `O'Brien <b>Shelf</b>` draws as text, and each click on it acts on that exact place.
- A group heading's icon comes from the row's Type.
- Every door reads a row's Type by one rule. A padded or re-cased Type acts as its built-in, and the location editor saves the built-in for it. The head-or-printer sets are named once, and the page has one single-head helper.
- After Derek's pick, a Type has one badge, the same in both places.
- A toast with no duration stays up for its type's time, no error toast lasts under 7 s, and a click on a toast does what Derek chose.
- After his pick, a long run in a toast stays inside it.

## Risks

- **71.4 reaches every move.** The engine's one-spool rule and dryer branch change shape. For the Types on file nothing changes; prove each rewritten function on the built-in first, and run the move families and the full run.
- **71.4 recognises more rows.** A hand-edited 'tool head' row becomes a head at every door. Today the slot-label scan refuses it, and the engine files spools on it as on a shelf. That is the point of the rule.
- **71.2 escapes about 80 values.** Escape only raw values, never a string that is already HTML or already `jsArg`'s output, or "&amp;" shows on screen.
- **71.6 changes 71 toasts** (52 once Group 70 has landed). The errors and warnings among them go from 2 s to 7 s (the two mode notices to 4 s), the rest from 2 s to 4 s, so more toasts stack in the middle of the screen at once. Escape clears a toast before it closes a window (the 2026-05-30 rule), so an Escape meant for a window is spent on a toast for longer. Tests that time a toast may need their numbers.
- **71.6b (a)** lets a toast cover what is under it while it is up: 4 to 7 s for most, up to 12 s for a few. One click clears it, and the double-press hold keeps that click's second press from reaching the page.
- **71.1** adds a line to most cards and lengthens a grid tile's first line.

## Owed to CLAUDE.md at the merge

- **"A value in an inline handler is a JS string first":** every value, a place id too, goes through `jsArg`. Take out "A LocationID can keep the existing strip", and name the new canary.
- **"Spoolman's free text in a card is HTML text":** add the place values (`location`, `slot`, `deployed_to`, `box`, `toolhead`) and the views folded into 71.2.
- **The head-Type sentences in "Every door that names a multi-slot box…":** the one rule (`locations_db.canonical_type` / `row_type`, `window.rowType`) and `window.isOneSpoolHeadRow`. Take out "compare the Type untrimmed" and "'Printer' is still tested by hand at several page sites … (one Printer rule is a follow-up)".
- **Testing:** the toolhead canary's bullet (its block now holds the known Types and their helpers), and a bullet each for the three new canaries (handler arguments, Type reads, toast durations), each saying what it can't see.
- **"Activity Log + Toasts":** `showToast`'s default by type, and the click rule from Q1.
- **Group 59's file:** the "(pictures for other groups)" row records the picks for 71.5 and 71.7.

## Prod facts (read-only, optional)

Nothing in the build depends on these.
- **71.4:** whether prod's `locations.json` holds a padded or re-cased Type. Dev's copy (prod's rows as of 2026-11-13) holds none.
- **71.2:** whether any prod spool's `location` or a slot holds `'`, `"`, `<` or a space. One read, never a write: `GET http://192.168.1.29:7912/api/v1/spool?allow_archived=true`, then count. Prod reads weren't authorised for this file.
- **71.1:** how many cards gain the line. Group 69's grounding read dev (a copy of prod) on 2026-11-16: 135 of 191 filaments carry a legacy number.

## Found while grounding (not in this group's items; for the refresh to file)

> **Filed 2026-11-17 by the refresh:** 1 and 2 joined 71.6's item; 4, 5 and 6 joined 71.2's (5 as a small decision for Derek at the build), with the search panel's unescaped words from Group 73's file.

1. **A toast never takes a mouse click** (`global.css:913`; `inv_core.js:1580-1591`). Folded in as **71.6b** (Q1). The refresh files its buglist line, routed to 71.6.
2. **11 error toasts pass 5 s,** under CLAUDE.md's 7 s (listed under 71.6). Folded into 71.6.
3. **The views that hold the cards put place ids and Spoolman names into HTML as they are:** the Quick-Swap grid, its deposit question, its tap's confirm body (`inv_quickswap.js:1218`), Return's "Nothing to return" (`:1470`), its attached label and its bind list; the Location Manager's title and READY TO SLOT card, whose 🖨️ also strips quotes from a name. Folded into 71.2, along with the Location Manager's copy of `getRichInfo` (folded into 71.1).
4. **Printer Status puts its heads' ids into its HTML as they are:** `data-toolhead`, titles and labels (`inv_printer_status.js:308`, `:316`, `:339`, `:355`, `:407-412`). A head's id comes from Settings → Toolheads. Not folded: a different widget. It fits a standalone item, or 71.2 if the refresh prefers.
5. **The location editor accepts any LocationID text:** only a blank is refused (`routes_locations.py:354-356`), so an id can hold `'`, `"`, `<` or a space, and every page rule has to assume it. Whether to refuse quotes and angle brackets at save is a small decision for Derek. A standalone item.
6. **`openManage` finds a row by exact LocationID** (`inv_loc_mgr.js:212`), so a spool whose Spoolman location differs from its row only in case ("lr-mdb-1") opens nothing from its 📍 badge or its group heading, with only a console warning. Small; standalone, or with 71.2.
7. **The Locations table never draws a "(Room)" row's Virtual look:** 'Virtual Room' takes the Room rung (`inv_core.js:2637`) before the Virtual one (`:2639`). Folded into 71.5's picture.
8. **71.1's own diagnosis was off:** the "[Legacy:" came from a staged test card. The fix stands; the item's words could say so when it is archived.
9. **Group 70 takes 19 of the toasts 71.6 counts:** the single-label queue doors' (70.4 (a) moves their toast into `addToQueue(item, {say: true})`), `printLabel`'s (70.3 removes it) and the queue window's (70.1, 70.4 (b)). Both groups also list READY TO SLOT's 🖨️ `jsArg`; 70 lands it first.
