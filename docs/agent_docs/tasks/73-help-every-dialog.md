# Group 73: 📖 Help for Every Dialog

**Branch name (when started):** `feature/group-73-help-every-dialog`
**Estimated effort:** MEDIUM–LARGE (~14–20 h, 2–3 sessions, for D1's (a); the parts below add up to it, and estimates here have run about 30% low, so plan on the upper half). D1's (b), the recommendation, adds ~2–3 h; its (c) ~3–5 h more. The proposal's ~6–10 h came before grounding, which found 18 named dialogs (not ~15) plus the delete question Group 62 hands over, two kinds of dialog the help registry can't match yet (the search panel is a Bootstrap offcanvas, Force Location a SweetAlert2 popup), and Done's question's three "no ?" pins. Group 55's word check found 12 wrong lines in 143, so the independent check is part of the build. Per part: A the registry ~1.5–2.5 h (+1 h for the Swal kind) · B the entries and their ?s ~6–8 h · C keys and on-screen words ~0.5–1 h · D Done's question ~0.5–1 h · E a re-check of the 13 entries that exist ~1 h · F tests ~3–4 h · G the independent word check and its fixes ~1.5–2 h. One review round and the full run (~70 min) come on top.
**Risk:** **LOW.** Words, ? buttons and one change to how the help finds the dialog on top. No Spoolman write, no backend change. The hazards: help that says what the code doesn't do (Group 55's 12 in 143), a dialog's hotkey that doesn't stand down under the help, and `_helpContext()` picking the wrong dialog once it knows an offcanvas (every `?` press reads it).

> **Status: TODO, filed 2026-11-16** (/refresh-groups; Derek approved the grouping the same day: "otherwise this seems fine").
> **Place in the recommended order:** 12th, after 59 (Settings may be redesigned) and 66 (the wizard, Edit Filament and the vendor editor change). Grounding adds: after 62 (62.8 hands this group the delete question's ?; 62.2, 62.6, 62.7 and 62.9 change lines that exist), 67 (67.2 changes Delete this filament's count), 69 and 72 (each new window writes its own help), 70 (70.4 changes Find Multi-Spool Filaments' failed read; 70's file also changes the location window's 🖨️ line, `help_texts.js:53`) and 64 / 72 (the 🛑 review's cards). By the time this group is next, all of those but 59 have run.
> **Starts with:** two questions for Derek, asked cold and one at a time (D1, D2). D2 is asked only if Group 59's Settings and vendor-editor pictures (59.3, 59.10) haven't been built by then. Nothing else waits on him.
> **Grounded 2026-11-17**, read-only, on `dev` @ `95531a6` (code unchanged since `3388c7d`; the commits between are docs and the deploy script). The member is **live**: none of the 18 dialogs it names has help, each checked in its own markup and in `help_texts.js`. Line numbers will drift by the time this group runs, so re-grep before editing.

## Items covered (quoted from `Feature-Buglist.md`)

| # | Buglist item | Direction |
|---|---|---|
| **73.1** | *"📖 In-app help for the dialogs that don't have it yet (the documentation overhaul). Group 55.3 put help one click away in the daily dialogs: the round ? beside the ✕ (or in a question's top right corner) and the `?` key while that dialog is on top, the words in `help_texts.js` (13 entries; CLAUDE.md, "In-app help", says how a dialog gets its words and its ?). Still without help: ⚙️ Settings, Edit Filament, the location editor (Add / Edit Location), the vendor editor, the 🧵 Multi-Spool Search, a location's QR view, the audit's panel and its windows (Done's question, the report, 🔎 Find a spool, the 🧺 Loose spools list), the ⚠️ Low stock list and its reason dialog, the 🔍 search panel, Bulk Move's panel, the 🛑 cancelled-print review, the legacy-ID picker and the parent picker. Check each one's words against its code before they go in: Group 55's check found 12 wrong lines in 143. Derek, 2026-10-19: "no one really reads documentation… keeping the information available at a quick click is important.""* | **Live, all 18.** Each gets a `registerHelp` entry, its ? and lines checked against its code (Group 55's model and process). Grounding adds: the spool and filament delete question (62.8 hands its ? here), two match kinds the registry needs (the search panel, and Force Location if D1 picks (b)), Done's question's pins, and four more working windows and about a dozen plain questions without help (D1). |

## Decisions

### For Derek, at the group's start

**D1. Which dialogs get a ?**
- **What it is.** In 13 windows today, a round **?** beside the ✕ (or in a question's top right corner) opens a few lines on what the window is for, what its buttons do and which scans work in it, then its keys. The **?** key does the same for the window on top. Your buglist item names 18 more windows. Grounding found 4 more working windows with no help, and about a dozen plain yes / no questions.
- **Where you'd see it.** For example the 🔀 Bulk Move panel, beside its Hide; the 🛑 Print Reviews window, beside its ×; "⚠️ Clear Queue?", beside its ✕.
- **A real example.** In 🛑 Print Reviews the ? would say: each card is a print whose grams FCC didn't charge on its own; its green button charges them; 🗑️ Discard needs two presses; closing keeps every card for later.
- **Options.**
  - **(a) The 18 the item names**, plus the spool and filament delete question (Group 62.8 moves it to the overlay helper and hands its ? to this group).
  - **(b) (a), plus the 4 working windows grounding found:** Force Location (the list of places behind the ✏️ beside a spool's location), the 🎯 Matched Prusament spool window, 🔗 Merge filament, and the wizard's ⚖️ Weigh from scale.
  - **(c) (b), plus every plain question:** the yellow ⚠️ Confirmation, the red ⛔ Safety interlock, Slot Occupied, Clear Queue?, Close without saving?, Unsaved Changes, the "Printed label is now out of date" nudge, the empty-weight prompt after an archive, the missing-tare prompt, 🔗 Link Field, ➕ Add New option, and the 📡 Activity Log list.
- **Recommendation: (b).** The four are windows you work in, with lists, boxes and more than two buttons. A plain question already says in a line or two what each of its buttons does, so a ? there adds little.
- **If you don't answer:** (b). Help only adds words and a button; nothing changes how a window works.

**D2. Settings and the vendor editor, if Group 59 hasn't changed them yet** (asked only then).
- **What it is.** Two windows may change shape before long. ⚙️ Settings may become a side panel (Group 59.3's picture: section names down the left, the open section on the right), and Group 35 adds settings per printer. The vendor editor ("✏️ Edit Manufacturer") may get one name, "vendor", and a ✏️ that looks like a button (Group 59.10). Their help says what each part does, so it would need rewording after either.
- **Where you'd see it.** ⚙️ at the right of the title bar; the ✏️ beside a filament's vendor.
- **A real example.** Settings' help would say "🖨️ Printers & Toolheads: each toolhead's ID, its printer and its number on it; Save toolheads saves them". After 59.3 the line still holds; only where that part sits changes.
- **Options.**
  - **(a) Write their help now, on today's windows.** Groups 59 and 35 change its lines when they change the windows, as every group already does for help.
  - **(b) Leave both without help** until 59.3 and 59.10 are built, and those builds write it.
  - **(c) Hold the whole group** until 59's pictures are built.
- **Recommendation: (a).** The lines describe what each part does, which a new layout keeps; rewording is about half an hour each. (c) would hold 16 other windows on a picture session.
- **If you don't answer:** (a).

### Claude's calls (for veto)

1. **One entry per window.** A window's own small questions are sections of its entry (shown only while the question is on screen), and each draws its ? in its top right corner (`window.fccCornerHelpHtml`): Low stock's reason dialog, Settings' Sweep Unused Tags, import review and tag remove / purge questions, Merge's second step, Force Location's "Cancel Override?". Printer picker precedent (Group 55).
2. **Two new match kinds.** The search panel is a Bootstrap offcanvas, which the registry can't see today: `{offcanvas: 'offcanvasSearch'}`. With D1 (b), Force Location stays a SweetAlert2 popup (a port to `mountOverlay` is out of scope) and gets `{swal: 'fcc-force-location'}`, matched by a class on its popup. The registry, its tests and CLAUDE.md learn both.
3. **Done's question gets its ?.** Group 55 left it without help, its markup as it was; the item lists it now. An entry naming its overlay makes `confirmActivePrint` draw the ? with no change there. The three pins that say it has none change on purpose. Its look changes only by the ? and its title's padding, the move questions' look, so no picture.
4. **Register the keys the two pickers already answer** (a "Parent Picker" scope: ↑ ↓, Enter, Esc; a "Legacy Label Picker" scope: Enter presses the focused button, Esc cancels, typing a spool's number jumps to it), so their help lists them, as the standing order asks of every key. The full shortcut list's picture is retaken.
5. **A dialog's own words follow the help's rule.** While its help is written, a dialog's on-screen words and toasts stop naming scan codes, as Group 55 did for the box grid's banner: Bulk Move's "Review below, then Commit (or scan CMD:DONE)" and its Hide tooltip's "or scan CMD:CANCEL" become the QR under the button; the legacy picker's "queue a fresh ID:-format label" becomes "a label with the spool's own number". Activity Log lines keep naming what was scanned: they are the record.
6. **Group 55's process for the words.** Map each dialog's buttons, keys and scans from its code, write the lines, then an independent check of every line against the code before the merge. The check also covers the 13 entries that exist, because Groups 62–72 change several of their dialogs (`help_texts.js:52`, `:53`, `:56`, `:57`, `:127`, `:172`). Read-only agents, batched (CLAUDE.md's budget rule: state the count and the cost first; about 3 mappers and 2 checkers, ~3–4M tokens).
7. **One look.** The ? is the existing `.fcc-help-btn`, beside the window's ✕, Hide or Close (just before it); a window with neither gets the corner ?. The search panel's header needs one CSS rule to place it. No new look, so no picture.
8. **Every helped dialog's hotkeys stand down under the help.** A letter, digit, arrow, Delete or Escape handler asks `window.fccShortcutsUp()`, or checks the list itself. Checked by reading for every dialog below; all are fine today except Shift+B with nothing else open (found below).
9. **The lines say what the code does today, gaps included** (Edit Filament's Cancel closes it unsaved; a scan in the search box is typed in). The group that closes a gap changes the line.
10. **The location window's help gains a section** for 🔀 Move all → and 🔀 Show bulk move, shown only while one is on screen (Bulk Moves on): the way into the Bulk Move panel this group documents. It also answers one line of the buglist's Bulk Move polish item ("an undocumented entry point", `Feature-Buglist.md:625`), which is not this group's: say so there at the merge.
11. **A dialog Groups 62–72 add without help is covered here too.** Two already plan their own: 69.1's archive window (69's design) and 72's mid-print question (`print-change-question`, 72's design). Check both landed with their ?.

## Today's code (anchors, `dev` @ `95531a6`)

### The help machinery (Group 55.3)
- **The words.** `static/js/modules/help_texts.js`, 13 `window.registerHelp` entries: `location-list` :29, `location-window` :45, `swap-question` :72, `spool-window` :86, `filament-window` :103, `wizard` :117, `weigh-out` :132, `quick-weigh` :147, `move-question` :162, `slot-picker` :177, `printer-picker` :193, `print-queue` :220, `label-backlog` :234. Its header (:1–23) holds the word rules.
- **The registry**, `shortcuts_registry.js`:
  - `registerHelp` :37–40; `fccHelpKeyForOverlayId` :48–54 (it reads `{overlay}` only).
  - `_entryForOverlay` :304–315; `_entryForModal` :316–321 (`{modal}` only).
  - `_topModal` :322–328 reads `.modal.show` only, sorted by z-index, then by shown order.
  - `_helpContext` :329–341: a visible Swal answers null at :330, so the `?` key over Force Location gives the full list. Otherwise the top `mountOverlay` decides, then the top modal.
  - The help closes on `hidden.bs.modal` (:375–379) and `fcc:overlay-closed` (:381–384). It also closes when another dialog opens over its own (`show.bs.modal` :388–390, `fcc:overlay-opened` :391–394). No offcanvas event is heard.
  - The delegated ? click finds its dialog with `closest('[data-overlay-mount="1"]') || closest('.modal')` (:465).
  - The window's keys (:486–582) take Tab, the arrows, a person's Space, Escape and Enter from whatever it covers, and let letters and digits through (a scan's). So a dialog's letter, digit and Delete hotkeys ask `window.fccShortcutsUp()` (:404) themselves: today the Quick-Weigh, the Quick-Swap grid's Q, the Low stock list and Force Location's Escape do.
- **Drawn ?s.** `fccCornerHelpHtml` `inv_core.js:379–385`. `confirmActivePrint`'s `help` defaults to its overlay's help (:403–407), and Enter on its ? opens the help (:562–577). `slot_picker.js:522`, `weight_entry.js:174` (only for a caller that names a `helpKey`), `inv_quickswap.js:591`, `inv_cmd.js:4252`.
- **The look.** `global.css:929–975`: `.fcc-help-btn`; dark on a `bg-warning`, `bg-info` or `bg-light` header (:948–953); placed in a `.modal-header` (:964–965); the corner ? (:969–970). Nothing places one in an `.offcanvas-header`.
- **Load order.** `scripts.html:84` loads `shortcuts_registry.js` after the dialogs' modules (`inv_cmd.js`, `inv_details.js`, `inv_loc_mgr.js`, `inv_stock.js`, `cancel_review.js` and the rest), and `help_texts.js` follows at :87. Only `draggable_pill.js`, `fab_drag.js`, Settings' two modules, `text_size.js` and `titlebar_prefs.js` load after it (:90–105). A document key listener a module adds at load runs before the help's own; one added when a dialog opens runs after it.
- **Stacking.**
  - Each Bootstrap window, as it shows, gets an inline z-index of 1055 plus 10 for each window already open (`inv_core.js:3628-3632`, `!important`). That beats the stylesheet's own: `.fcc-modal-top`'s 2000 on Clear Queue? and Multi-Spool Search (`global.css:1458`), and the 1100 rule (`:1545-1553`).
  - The search offcanvas sits at z 1090 (`.fcc-offcanvas-search`, `global.css:1461`), above the first four windows open under it (a fifth would get 1095). Showing any Bootstrap window hides it first (`inv_core.js:3621-3626`), so no window ever opens over it; it can only be opened over one, as the wizard's 🔍 Advanced Search does.
  - `mountOverlay` at 20000 and 20100; the help at 20201.
- **Its tests.**
  - `tests/test_help_texts_55.py` (offline, node). `FIRST_DIALOGS` :153–159. Well formed :166–189: 2–8 lines, each 260 characters at most, no "<" or ">", and `match` names `modal`, `overlay` or `overlayHas`. Each dialog exists :202–227. Every question an entry matches draws its ? :230–249, through `confirmActivePrint` or `fccCornerHelpHtml` only, so a window that draws its ? in its own header fails it as written. `SCRIPT_DRAWN` :275–284. ? buttons are named buttons :301–325. Setup names :54–57, 332–339. No "|" :342–346. No scan codes, in the lines and in every key row of a listed scope :358–422. Passed 20 / 20 offline on `95531a6`.
  - `tests/test_help_buttons_55_js.py` (node): Done's question is the "no help" row of `CALLS` (:44–45), and `CORNER` expects '' for it (:219, :234).
  - `tests/test_in_app_help_55_e2e.py` (dev container): `WINDOWS` :206–219; `test_only_questions_with_help_draw_a_help_button` :529–551 pins that Done's question has no ?.
  - `tests/test_contrast_guard.py`: each window's ? :1409–1437 (seven modals), the drawn ?s :1439+.
  - Visual baselines that a new ? or new key rows change: `editfil-*-tab.png` (4, `test_edit_filament_visual.py`), `search-offcanvas-empty.png` (`test_visual_baseline.py:183`), `shortcuts-overlay-default.png` (`test_quickswap_visual.py:314`).

### Every dialog, and whether it has help
- **Bootstrap windows** (`templates/components/`).
  - With help: `spoolModal`, `filamentModal`, `locMgrModal`, `manageModal`, `backlogModal`, `queueModal`, `weighOutModal`, `wizardModal`.
  - Without: `configModal` (⚙️ Admin / Config, `modals_config.html:5`), `editFilamentModal` (`modals_details.html:363`), `vendorEditModal` (:660), `locQrViewModal` (`modals_loc_mgr.html:2`), `locModal` (:58), `multiSpoolModal` (`modals_queue.html:58`), `clearQueueConfirmModal` (:40), and the three gating dialogs `actionModal` / `confirmModal` / `safetyModal` (`modals_core.html:1`, `:18`, `:45`).
  - The search panel `offcanvasSearch` (`offcanvas_search.html:1`) is an offcanvas, not a modal, so the registry can't match it yet.
- **`mountOverlay` dialogs** (29 calls).
  - With help: the move questions (`fcc-active-print-confirm-overlay`, `fcc-active-print-scan-overlay`), the Printer picker's two questions (`fcc-head-pick-confirm`, `fcc-record-source`), the Quick-Swap question, the slot and Printer pickers (`fcc-slot-picker`, by its mode), the Quick-Weigh (`fcc-weight-entry-overlay`, only with its Auto Archive switch).
  - Without:
    - the audit's four windows: `fcc-audit-panel-overlay` (`inv_cmd.js:2098`), Done's question `fcc-audit-done-question` (:2401, drawn by `confirmActivePrint` :2561), `fcc-audit-report` (:2753), `fcc-audit-find` (`inv_audit_find.js:568`);
    - the lists and panels: `fcc-loose-list` (`inv_loose.js:376`), `fcc-low-stock-overlay` (`inv_stock.js:1254`) and `fcc-low-stock-reason` (:811), `fcc-bulkmove-panel-overlay` (`inv_cmd.js:1178`), `fcc-cancel-review-overlay` (`cancel_review.js:1299`);
    - seven of these are mounted through a constant that holds their id, not the id written out: Done's question (`QUESTION_ID`, `inv_cmd.js:2401`, passed as `ids: { overlay: QUESTION_ID }` at `:2566`), the report (`REPORT_ID`, `:2615`), Find (`OVERLAY_ID`, `inv_audit_find.js:55`), the 🧺 list (`inv_loose.js:31`), Low stock's list and reason dialog (`OVERLAY_ID` / `DIALOG_ID`, `inv_stock.js:46-47`) and the 🛑 review (`cancel_review.js:26`). `tests/test_help_texts_55.py` can't see those (Tests, below);
    - the pickers: `fcc-legacy-picker-overlay` (`duplicate_picker.js:142`), `fcc-parent-tree-picker` (`inv_loc_mgr.js:2969`);
    - `fcc-prusament-matched-overlay` (`inv_cmd.js:2992`), `fcc-merge-filament-overlay` and `fcc-merge-confirm-overlay` (`inv_details.js:3249`, `:3350`), the wizard's Weigh from scale (`inv_wizard.js:1602`, a weigh window with no help key);
    - Settings' own questions: `fcc-attr-remove-confirm` and `fcc-attr-purge-confirm` (`inv_config.js:349`, `:377`, both drawn by `_dangerConfirm` `:21-56`, which mounts with the id it is handed), `fcc-sweep-unused-overlay` (:694), `fcc-config-import-overlay` (`inv_settings.js:694`);
    - the small ones: `fcc-log-pill-overlay` (`inv_core.js:2893`), `fcc-escape-confirm-overlay` (Cancel Override?, `inv_details.js:1120`), `fcc-archive-empty-overlay` (:1639), `fcc-label-reprint-prompt` (:2963), `fcc-missing-empty-weight-overlay` (`weight_utils.js:249`), `fcc-wiz-unsaved-changes` (`inv_wizard.js:160`), `fcc-wiz-fieldsync` (:2262), `fcc-wiz-newchoice` (:2709).
- **SweetAlert2 popups** (`inv_details.js`): Force Location Override (:1043; its keys sit under the spool window's help, scope "Force Location", but it has no help of its own and opens from cards too); Change Slicer Profile (:705) and 🎨 Swatch Printed? (:853), both named in the filament window's help. The rest are error notices.
- **Drawn inside their window, not through `mountOverlay`:**
  - the delete question (`#fcc-spool-delete-overlay`, `#fcc-filament-delete-overlay`: drawn by `_renderDeleteOverlay`, `inv_details.js:3016–3116`, for the flows at `:3118–3153` and `:3407–3450`), which 62.8 ports;
  - Edit Filament's "Close without saving?" (`#editfil-esc-confirm`, :2776–2854), found while grounding, below;
  - 🔗 Bind a Slot (`#fcc-bind-picker-overlay`, `modals_loc_mgr.html:203–231`), covered by the location window's Quick-Swap section, since that window stays the top dialog.

### Anchors for the dialogs this group covers
- **Settings.**
  - Template: `modals_config.html:5–154`; title :9–11 ("⚙️ Admin / Config"), ✕ :12, Close :150.
  - Cards: 🏷️ Filament Attributes :16–49 (`inv_config.js:102–490`: Load report, ＋ Add new tag, a tag's ✕ → strip from every filament and hide (:349), a hidden tag's ↩ unhide and 🗑 purge (:166–172; purge's question :377), 🧹 Sweep unused (button :215, `configAttrsSweepUnused` :619–785; CLAUDE.md calls it Sweep Unused Tags), the bulk editor :214–239); 🔢 Restore Spoolman Field Order :51–90 (Preview, then Apply, :492–534); ⚙️ Settings :92–102 (`inv_settings.js` `render` :86–145, `save` :147–223); 🖨️ Printers & Toolheads :104–114 (`pmRender` :324, Printer Connections :383–420); 📦 Import / Export :116–133 (the review opens on Cancel, :655–730); 📦 Build Info :138–147.
  - Sections come from `config_schema.SECTIONS` (`config_schema.py:56–62`). In 🖥️ This Browser, Text size, the three title-bar choices and the three Printer Status choices apply on change (`text_size.js:75`, `titlebar_prefs.js:100`, `inv_printer_status.js:980`). Default weigh-in mode waits for Save settings.
  - No keys of its own. Scans go on while it is open, except into a text box: the scan accumulator skips one (`scripts.html:364`).
- **Edit Filament.**
  - Template: `modals_details.html:363–647`; title :367, ✕ :368, tabs :373–386, Import from External :595–637, Cancel :644, 💾 Save :645.
  - Opens only from the filament window's ✏️ Edit Filament (`inv_details.js:484`); its "➕ Add Filament" mode has no caller.
  - `_editfilOpenModal` :1754. Its only unsaved-changes guard is Escape's (`escGuardHandler` :2748–2766): Cancel, ✕ and a click outside close it unasked, and by reading, an Escape with the keyboard outside a text box does too (Found while grounding 2).
  - After a save that changed a label's words: `_maybePromptLabelReprint` (:2882) flags its spools' labels (:2894–2902) and offers the reprint nudge (`_showLabelReprintPrompt` :2938–2988).
  - No field scan capture.
- **Vendor editor.** Template :660–715, title :664, ✕ :665, Cancel :711, 💾 Save :712. Openers: `openVendorEditModal` / `openVendorCreateModal` (`inv_details.js:3567`, `:3541`), from `modals_details.html:133` (the filament window), `:424` (Edit Filament) and `modals_wizard.html:121`, `:130` (the wizard's ✏️ and ➕). No unsaved guard, no field capture.
- **Location editor.**
  - Template: `modals_loc_mgr.html:58–109`; title :62 (also in Add mode, below), ✕ :63, 🌳 Browse… :94–95, footer :104–107.
  - `openEdit` `inv_loc_mgr.js:2370–2423`: the ID is locked for a printer with heads, or a head on a printer (:2389–2397). `closeEdit` :2425. `saveLocation` :2430, back to the list :2476.
  - Add: `_openLocModalForCreate` :2742–2782; Type, Max and an ID suggested from the parent :2694–2735.
  - Its boxes' scan capture :2543–2560; its dropdowns' and buttons' scan rules :2612–2670 (Group 61); Enter saves :2672–2677 (scope "Location Editor").
- **Parent picker.** `openParentTreePicker` `inv_loc_mgr.js:2814`. Header and ✕ :2877–2878. ↑ ↓ / Enter :2939–2967. Mount :2969 (backdrop closes it). A place's label picks it as the parent :2980–3000. Its keys aren't registered.
- **Location QR view.** `showGlobalQrModal` `inv_core.js:2806–2818`, opened from the Location List's 📱 QR (`scripts.html:191`) and the window's small QR (`modals_loc_mgr.html:117`). Template :2–16.
- **Multi-Spool Search.** `inv_queue.js:267–325` (the route `print_deduct.py:109`; archived spools skipped). Template `modals_queue.html:58–74`, ✕ :63 on a cyan header, so the existing dark-? rule applies. `executeMultiSpoolAdd` reopens the Print Queue.
- **Search panel.**
  - `inv_search.js:1–362`; `open` :183–220; select mode for the wizard's 🔍 Advanced Search (`inv_wizard.js:2961–3010`).
  - What a word matches: the id, name, material, vendor, colour name and tags, every word somewhere (`spoolman_api.search_inventory` :2880+).
  - A spool card (`ui_builder.js:144–197`): a click and 📥 send `ID:<id>` with source `search`; 🔍 opens it, ✏️ edits it, 🖨️ queues its label, ✅ its label is confirmed, 📍 opens its place, the ✏️ beside 📍 moves it.
  - Template `offcanvas_search.html:1–123`, header :4–33, ✕ :9–10. / and Ctrl+K open it (`fab_drag.js:133–161`).
- **Low stock.** `inv_stock.js`:
  - the list: shell :332–345 (✕ :340), rows :282–330 (🛒 Buy, 🔕, ✏️ on Excluded), its keys and the stand-down :981, shortcuts :1391–1422 (scope "Low Stock List"), open :1241–1319;
  - the reason dialog: `_dialogHtml` :598–640 (Why?, Note, 🔕 Exclude or Save, ↩️ Include again, Cancel), mount :811.
- **🧺 Loose spools.** `inv_loose.js:1–423`: header :113–118 (✕ :117), open :369, shortcuts :409–422 (scope "Loose Spools List").
- **🔎 Find a spool.** `inv_audit_find.js:1–630`: header :170–175 (✕ :174), open :556, its keys stand down under the list :417–419 and :498–500, shortcuts :612–629 (scope "Find a Spool").
- **The audit panel.** `openAuditPanel` `inv_cmd.js:2053–2138`: header :2064–2081 (🔎 Find a spool, 🧺 Loose spools, Hide :2078). Render :1895–1975 (tally, Expected here, Extra, Loaded from here; the dock with Needs a label, Done… and Cancel Audit). Its keys :2357–2372 stand down under the list. Shortcuts :2374–2391 (scope "Audit Panel"). How it handles scans: `logic.process_audit_scan` `logic.py:7343–7380` (a second place's label, "Already auditing X. Finish first!", `logic.py:6197`).
- **Done's question.** `askAuditDone` `inv_cmd.js:2537–2611`, through `confirmActivePrint` (:2561; Back to the audit, `armAfterMs`, `keepWhole`, its sections).
- **The audit report.** `_reportHtml` `inv_cmd.js:2670–2722` (Close :2714). `openAuditReport` :2749–2780. Opened after Done's yes, and from the report line's 📝 Read the report.
- **Bulk Move panel.**
  - `inv_cmd.js:843–1219`; open :1159–1196, header :1169–1173 (Hide :1171–1172).
  - The prompt :996–1000 ("Review below, then Commit (or scan CMD:DONE).") and the Hide tooltip :1172 ("…or scan CMD:CANCEL.").
  - Commit and Cancel with their QRs :1077–1116. Shortcuts :825–840 (scope "Bulk Move"); Shift+B :765–818.
  - Every scan goes to the session: `logic.process_bulk_move_scan` `logic.py:3954–4037`; the gate is `routes_scan.py:1404–1424`. Commit is one `perform_smart_move`, so Undo Last Move takes it back (`logic.py:3716`).
  - 🔀 Move all → / 🔀 Show bulk move in a place's window: `inv_loc_mgr.js:76–121`.
- **🛑 Print Reviews.** `panelHtml` `cancel_review.js:1134–1160` (× :1146–1149, Close — keep for later :1158). Mount :1299. Green buttons "Confirm deduct" (:1126) and "Apply to the picked spool(s)" (:915, :997). 🗑️ Discard takes two presses (:1582–1593). The spool box's hint :481. A label scanned into a grams box goes to the scan path (:1267–1281). Opened from the 🛑 badge in Live Activity's header (`dashboard.html:260`) and Printer Status's 🛑 count (`cancel_review.js:1209`). **Since Group 65 (2026-11-24; line numbers above are from before it, so re-grep):** a ❓ card has Charge the whole print and How far it got (type how far the print got, then Work it out or Enter; an Enter pressed while the card is busy is worked out once the card is drawn again), and a card after lost contact has a 📡 line saying when FCC lost sight of the print and when it saw the printer again. The help says what these do.
- **The legacy-ID picker.** `duplicate_picker.js:43–306`. Title :110 (no ✕), body :111–113 (the "ID:-format label" words), buttons :116–123, mount :142. Keys :216–254. The scans it takes :266–303.
- **The delete question.** `_renderDeleteOverlay` `inv_details.js:3016`. The spool's two steps :3118–3150 (Continue →, then type its number, Delete forever); the filament's :3407–3450 (type CONFIRM, or its number when it has no spools). 62.8 moves it onto `mountOverlay`, keeping its ids.
- **With D1 (b).**
  - Force Location: `promptEditLocation` `inv_details.js:1011`; Swal :1043–1065; its keys :1205–1262; Cancel Override? :1120.
  - The 🎯 window: `promptPrusamentMatched` `inv_cmd.js:2916–3060` (title :2981, no ✕).
  - Merge: `_showMergeFilamentFlow` `inv_details.js:3160`, its second step :3305 (type MERGE).
  - Weigh from scale: `wizardOpenWeightEntry` `inv_wizard.js:1572–1640`.

## Design, by member

### 73.1, part A — the registry learns the search panel (and, with D1 (b), Force Location)
- **`{offcanvas: 'offcanvasSearch'}`.**
  - `_topModal()` reads `.modal.show, .offcanvas.show`, with the same z-index and shown-order sort. The search panel (z 1090) then wins over a Bootstrap window it covers (the wizard's Advanced Search). No Bootstrap window opens over it: showing one hides the search panel first (`inv_core.js:3621-3626`), so the sort only has to put the panel over the windows opened before it.
  - `_entryForModal` matches `modal` or `offcanvas`.
  - `hidden.bs.offcanvas` closes the help like `hidden.bs.modal`, and `show.bs.offcanvas` like `show.bs.modal`. `_shownOrder` counts offcanvases too.
  - The delegated click adds `|| closest('.offcanvas')`. `global.css` places a ? in an `.offcanvas-header` beside its ✕.
- **`{swal: 'fcc-force-location'}`, with D1 (b).**
  - Force Location's `Swal.fire` adds `customClass: {popup: 'fcc-force-location'}`.
  - `_helpContext()` returns that entry when the visible Swal's popup has the class, else null, as today.
  - Its `willClose` calls `window.fccCloseHelpFor(popup)`. Its ? sits in the popup's top right corner, drawn in its `html`.
  - SweetAlert2's own key handler listens in the bubble phase (FCC sets no `keydownListenerCapture`, which would move it to the window's capture phase), so the help's document capture handler hears Tab and Escape first and keeps them; check it in the browser. Force Location's own Escape handler, on the window in the capture phase (`inv_details.js:1241–1253`), runs before the help's and already stands down for it (`fccShortcutsUp`, `:1248`). Its ↑ ↓ / Enter are on its search box, so the help's document handler stops them.
- **Not changed:** an overlay a `mountOverlay` mounts still wins over every Bootstrap window, and a Swal with no class still gives the full list.

### 73.1, part B — the entries
Each entry: its `key`, `title` (the dialog's name as a person sees it), `match`, 2–8 lines (≤ 260 characters each), `scopes` where a registered scope exists, `sections` where noted. The lines below are drafts from today's code, for the builder to re-map after Groups 62–72 and then check. They use made-up examples (SHELF-1, DRYBOX-1, HEAD-1, #42), name buttons and the QRs beside them, never a scan code, and hold no "|". Lines marked "today" describe a known gap, and the group that closes it changes them.

**`settings`** — ⚙️ Settings. `{modal: 'configModal'}`, plus its own questions in `overlay` (Sweep, import review, tag remove, tag purge), each a section with a corner ?. ? beside its ✕. D2 decides when.
1. Settings FCC keeps on the server for every browser, and This Browser's own, kept in this browser only.
2. 🏷️ Filament Attributes: Load report lists every attribute tag and how many filaments carry it. ＋ Add new tag; ✕ on a tag takes it off every filament and hides it (↩ unhide offers it again, on no filament); 🗑 purge deletes a hidden tag from Spoolman itself.
3. Tick filaments in the table (the filter narrows it), then add or remove a tag on all of them at once. 🧹 Sweep unused clears the tags no filament uses, after a list you can untick.
4. 🔢 Restore Spoolman Field Order: Preview changes lists the fields that would move in Spoolman's own forms; only Apply writes.
5. ⚙️ Settings: Connection (where Spoolman is), Behavior (print deducts, the low-stock line, Bulk Moves) and 🖥️ This Browser. Save settings saves; Text size, the title bar's and Printer Status's choices change as soon as you pick them.
6. 🖨️ Printers & Toolheads: each toolhead's ID, its printer and its number on it (+ Add toolhead, 🗑 removes one), then Save toolheads. Printer Connections: each printer's IP address and API key, so FCC can read its prints.
7. 📦 Import / Export: Export config saves the settings to a file (without the API key); Import settings… lists what would change and opens on Cancel.
8. Scans go on while it is open, except into a text box, where a label's text is typed in.

**`edit-filament`** — Edit Filament. `{modal: 'editFilamentModal'}`. ? beside its ✕. After Group 66 (66.1, 66.6, 66.7 change it).
1. Changes one filament: the brand, material and colour every spool of it shares.
2. Basic: its name, material and vendor (✏️ beside Vendor edits the vendor itself), the colour's original name, its tags and notes. +NEW means Save adds that material or vendor.
3. Colors: one colour or several (+ Add Color, ▲ ▼ to order them) and how they run. Specs: empty spool weight (Use Vendor copies the vendor's), density, diameter, net weight, price, nozzle and bed temperatures.
4. Advanced: its slicer profile, links and old label number. 📥 Import from External reads details from Spoolman's own list, a Prusament link or an Amazon page: tick the ones to use, and Apply Selected fills the boxes.
5. 💾 Save saves the filament. A change to its name, material, vendor, colour name or tags marks its spools' labels out of date (they show in the 🏷️ Label Backlog), and FCC offers a new swatch label when its old one was printed.
6. Today: with the keyboard in a box, Esc asks first when something isn't saved; Cancel, ✕ and a click outside close it without asking.
7. Today: scans go on while it is open, except into a text box, where a label's text is typed in.

**`location-editor`** — Location editor. `{modal: 'locModal'}`, `scopes: ['Location Editor']`. ? beside its ✕.
1. Adds a place, or changes one: its ID (the code on its label), its name, its Type, where it sits, and how many spools it holds.
2. ➕ Add Location opens it blank. A row's ➕ opens it under that place, with a Type, a capacity and an ID suggested from it (SHELF-1-R2, say); change any of them.
3. Type: pick one, or type a new one in the box under it. Parent: Auto works it out from the ID, Top level puts it at the top, and 🌳 Browse… picks it from the tree.
4. Max Spools: how many spools it holds. 0 means no limit, except in a dryer box, where 0 or 1 makes a one-spool dryer. (Check against Group 37's fork 4 if it has landed.)
5. The ID of a printer that has toolheads, or of a toolhead on a printer, can't change here: spools are filed under it. Change its name instead.
6. Enter or 💾 Save Changes saves, from any box or list. Today: Cancel or ✕ goes back to the Location List; Esc closes it.
7. A label scanned with the keyboard in one of its boxes or lists goes to the scan path, and the box keeps what it had.

**`parent-picker`** — Pick a parent location (its header's own words). `{overlay: 'fcc-parent-tree-picker'}`, `scopes: ['Parent Picker']` (new, Claude's call 4). ? beside its ✕.
1. Picks where a place sits: Top level, Auto (worked out from its ID), or any place in the tree. The place itself, and the places inside it, aren't offered.
2. ↑ ↓ move and Enter (or a click) picks; ✕, Esc or a click outside closes it with nothing changed.
3. Scan a place's label to pick it. Any other scan is refused while it is open; scan it again once you have picked.

**`vendor-editor`** — Vendor editor. `{modal: 'vendorEditModal'}`. ? beside its ✕. After 66.1 (a name in use is refused) and 59.10 (its name), or D2.
1. A vendor: its name, website, empty spool weight, an outside ID and notes. It opens from the ✏️ beside a filament's vendor, and from the wizard's ✏️ and ➕ beside its vendor box.
2. Empty Spool Weight is what an empty spool of this vendor weighs: a filament or spool with no empty weight of its own uses it.
3. 💾 Save changes it for every filament of this vendor. Cancel, ✕ or Esc closes it without saving.
4. Today: scans go on while it is open, except into a text box, where a label's text is typed in.

**`multi-spool`** — Multi-Spool Search. `{modal: 'multiSpoolModal'}`. ? beside its ✕ (dark on its cyan header, as the Print Queue's).
1. From the Print Queue's 🧵 Find Multi-Spool Filaments: the filaments you have two or more spools of (archived spools don't count), and how many spools that is.
2. ➕ Add All to Queue adds each of those spools' labels to the print queue (one already queued isn't added twice), then the Print Queue shows again. Cancel adds nothing.

**`location-qr`** — Location QR Code (its title). `{modal: 'locQrViewModal'}`. ? beside its ✕.
1. A place's label code, big enough to scan from the screen. It opens from 📱 QR on a Location List row, and from the small code at the top of a place's window.
2. Scanning it does what scanning the place's printed label does. 🖨️ Print Location Label, in the place's window, queues a label to stick on. ✕ or Esc closes it.

Builder's note: by reading, an Esc with the QR view over a place's window closes or steps back that window instead (Found while grounding 2). Check it, and word line 2 as the code does.

**`search`** — Search. `{offcanvas: 'offcanvasSearch'}` (part A). ? beside its ✕. Its header reads "🔍 FIND SPOOL", close to the audit's "🔎 Find a spool" (another window): pick a title that keeps the two apart in the shortcut window.
1. Finds spools, or filaments (the switch at the top), by words from the name, material, brand, colour name or tags, or a number. Every word has to match.
2. Narrow it by colour (the picker or a hex code; closest first), material, grams left, on a printer or not, and In Stock (off: archived spools too). Reset 🗑️ clears them; Refresh 🔄 searches again.
3. A click on a spool puts it in your scan buffer (during an audit it counts as found, with no label read). On a card, 🔍 opens it, ✏️ edits it, 🖨️ queues its label, 📍 opens its place, and the ✏️ beside 📍 moves it.
4. A click on a filament opens it. ⚠️ Low stock opens the list of filaments running low.
5. From the wizard's 🔍 Advanced Search, a click picks that filament for the wizard.
6. / or Ctrl+K opens it from anywhere, and Esc closes it. Today: a label scanned while the keyboard is in its box is typed in as words to find.

**`low-stock`** — Low stock. `{overlay: ['fcc-low-stock-overlay', 'fcc-low-stock-reason']}`, `scopes: ['Low Stock List']`. ? beside its ✕; the reason dialog's in its corner.
1. Per filament, across its spools in stock: Low is under the line set in ⚙️ Settings → Behavior; Out has none in stock; Excluded is what you took off both, with why.
2. A click on a filament (or Enter) opens it, and the list comes back where it was once you close it. 🛒 Buy opens its shop page, when FCC knows one.
3. 🔕 (or Del) takes a filament off Low and Out, after asking why. On Excluded, ✏️ (or Del) changes why, or puts it back.
4. / filters by brand, material, colour, tag, reason or note, and ← → switch lists. A label scanned into the filter goes to the scan path, and the filter stays as it was.

Section "Exclude from Low and Out", while the reason dialog is open:
- Pick why (Discontinued, Can't find it, One-off, Didn't like it, or Other with a note). 🔕 Exclude, or Save when changing it, saves; Enter does too, except in the note (Ctrl+Enter there).
- ↩️ Include again puts it back on Low and Out. Esc or Cancel closes only this.

(Two lines: as one it ran to 263 characters, over the 260 that `test_every_entry_is_well_formed` allows, section lines included.)

**`bulk-move`** — Bulk Move. `{overlay: 'fcc-bulkmove-panel-overlay'}`, `scopes: ['Bulk Move']`. ? before Hide.
1. Moves every spool from one place to another in one go. Scan the place they come from, then the place they go to; scanning another place after that changes where they go.
2. It shows what will move, and what stays where it is and why (on a printer, in your scan buffer, archived…). Nothing moves until Commit Move.
3. 🔀 Commit Move, or the QR under it, moves them, and Undo Last Move puts them back. ❌ Cancel, or the QR under it, ends it with nothing moved.
4. Hide (or Esc) keeps it armed behind the 🔀 pill; the BULK MOVE tile, the pill or Shift+B bring it back. It clears itself after a while with no scan, with nothing moved.
5. While it is armed, every scan goes to it: a spool's label is refused.

Plus a section in `location-window`, while 🔀 Move all → or 🔀 Show bulk move is on screen: "🔀 Move all → starts a bulk move from this place; 🔀 Show bulk move brings back one already armed."

**`audit-panel`** — Audit. `{overlay: 'fcc-audit-panel-overlay'}`, `scopes: ['Audit Panel']`. ? before Hide.
1. An audit checks one place against what FCC has filed there. Scan the place's label to start: its spools show under Expected here.
2. Scan each spool's label as you find it: its tile moves to Found. No label to scan? Press its tile (or scan the QR beside it), or 🔎 Find a spool searches by name, colour, brand or number.
3. A spool found here that FCC has somewhere else is an Extra; its tile says where FCC has it. Press an Extra's tile if it isn't here after all.
4. 🏷️ on a found tile, or Needs a label, marks that spool for a new label (it shows in the 🏷️ Label Backlog). Press it again to take the mark back.
5. Done… asks before it moves anything: the spools not scanned go to Unknown, and the Extras are filed here. Cancel Audit ends it with nothing moved.
6. Hide keeps it running behind the 🕵️ pill, and every scan still goes to it. 🧺 Loose spools lists the spools filed only at a room or a cart.
7. While it runs, another place's label and most commands are refused. It ends by itself after a while with no scan, with nothing moved.

**`audit-done`** — Done's question. `{overlay: 'fcc-audit-done-question'}`. Its ? comes from `confirmActivePrint`'s default (part D).
1. Done asks before it moves anything. Not scanned, to park at Unknown: the spools FCC had here that weren't found. Each goes to Unknown and says where it was lost.
2. Found here, FCC had them elsewhere: the Extras, filed here. Left where they are: spools that stay, each saying why.
3. Its yes (Park, File or Do both) does it; for a moment after the question opens it takes no click, so a double click can't answer it. Back to the audit moves nothing.
4. Enter goes back to the audit. Scan the QR under a button to answer with it. Undo Last Move puts every spool back.

**`audit-report`** — Audit report. `{overlay: 'fcc-audit-report'}`. ? before Close.
1. What an audit did, spool by spool, grouped by what happened to each: parked at Unknown, filed here, left where they are, couldn't be moved, not scanned, Extras, loaded from here, marked as needing a label.
2. It opens after Done's yes, and from 📝 Read the report on the audit's line in the Activity Log (and in the 📡 pill's list).
3. Close or Esc closes it. A scan closes it and goes on as usual. Undo Last Move puts back what the audit parked and filed.

**`audit-find`** — Find a spool. `{overlay: 'fcc-audit-find'}`, `scopes: ['Find a Spool']`. ? before its ✕.
1. During an audit, finds a spool that has no label to scan: type part of its name, colour, brand or number.
2. Each row says where FCC has it, and whether it is on this audit's list or found already. Archived spools aren't listed.
3. Pick one (a click, or ↓ then Enter): it counts as found here with no label read, or as an Extra if FCC has it elsewhere. Esc closes it with nothing changed.
4. A label scanned into its box goes to the audit, not into the search.

**`loose-list`** — Loose spools. `{overlay: 'fcc-loose-list'}`, `scopes: ['Loose Spools List']`. ? before its ✕.
1. Every spool filed at a room or a cart itself, with no shelf, row or box: the ones to put somewhere more exact. It changes nothing.
2. Grouped by place. A click on a spool, or Enter, opens its place (not during an audit). If Spoolman didn't answer it says so, with ↻ Try again.

**`print-reviews`** — Print Reviews. `{overlay: 'fcc-cancel-review-overlay'}`. ? before its ×.
1. Prints whose filament FCC didn't charge on its own: a cancelled print, an end FCC couldn't measure, or grams a spool couldn't take. Each card asks you to check them.
2. Change a card's grams if they look wrong (→ shows what will be left), then press its green button to charge them.
3. A toolhead with no spool, or with several, asks which spool: type its number, or scan its label, in the box.
4. 🗑️ Discard drops a card and charges nothing; it takes two presses. Close (or ×, Esc) keeps every card for later: the 🛑 count in Live Activity and in Printer Status opens this again.
5. A label scanned into a grams box goes to the scan path. (Group 64.2 (11) may change how fast a scan must be; word it after 64.)

**`legacy-picker`** — Old label picker. `{overlay: 'fcc-legacy-picker-overlay'}`, `scopes: ['Legacy Label Picker']` (new). Corner ? (no ✕).
1. An old label's number belongs to a filament, and you have more than one spool of it: pick the spool you scanned.
2. Pick it in the list (typing its number jumps to it), then ✓ Use selected: it goes on as the scan would have.
3. 🖨️ Print new label queues a label with that spool's own number, so it can be scanned by itself from then on. ➕ Add new spool starts a new spool of that filament in the wizard.
4. Scanning a listed spool's own label picks it. Cancel or Esc cancels. Any other scan is refused while it is open; scan it again once you have answered.
5. During an audit, the list shows where each spool stands in it.

**`delete-question`** — Delete question. `{overlay: [the two ids 62.8 keeps]}`. Corner ?.
1. Deletes a spool, or a filament and every spool of it, from Spoolman for good. There is no Undo.
2. The first step says what will go. The second asks you to type a word (the spool's number, CONFIRM, or the filament's number when it has no spools) before Delete forever works.
3. Cancel or Esc closes it with nothing deleted, and the window stays.

**With D1 (b):**
- **`force-location`** — Force Location. `{swal: 'fcc-force-location'}` plus `{overlay: 'fcc-escape-confirm-overlay'}` (Cancel Override? as a section, corner ?), `scopes: ['Force Location']`. Lines: it moves a spool to a place picked from a list, with no scanning; typing narrows the list; ↑ ↓ and Enter pick; Force Move moves it, and a box with slots or a printer asks which slot or toolhead next; Cancel or Esc asks first; it opens from the ✏️ beside a spool's location, in its window and on its card.
- **`prusament-match`** — Matched Prusament spool. `{overlay: 'fcc-prusament-matched-overlay'}`, corner ?. Lines: a Prusament spool's QR matched one of your spools, and FCC filled the filament's blank temperatures from Prusament's page; Update to Prusament's spec changes temperatures that differ; 📦 Update spool weights corrects the spool's full and empty weights and keeps what it used; 🏷️ Queue label; Done or Esc closes it.
- **`merge-filament`** — Merge filament. `{overlay: ['fcc-merge-filament-overlay', 'fcc-merge-confirm-overlay']}`, corner ?. Lines: moves every spool of this filament onto another and deletes this one (for a filament made twice); pick the one to keep, Continue →, then type MERGE before Merge forever; Cancel or Esc changes nothing. (After 67.2: a count it can't read stops it.)
- **`wizard-weigh`** — Weigh from scale. A `helpKey` passed by `wizardOpenWeightEntry` and a `match` on the window without the Auto Archive switch. Lines: works out the wizard's weights from a scale reading and saves nothing until the wizard's own Save; Gross and Net (Additive and Set Used once the spool's full weight is known); with none known, what is on the spool becomes its full weight; Save Update or Enter fills the boxes, Cancel, × or Esc closes it. After Group 66.

**With D1 (c):** one or two lines each for the plain questions listed under D1, matched by their own ids, each with a corner ?. The three gating dialogs are shared by many callers, so their lines stay general ("FCC asks before it does what the question says; YES (or the QR above it) does it, NO doesn't"); check what Enter does on each first.

### 73.1, part C — keys, and words that name scan codes
- **Register the two pickers' keys** (Claude's call 4): "Parent Picker" (↑ ↓, Enter, Esc) and "Legacy Label Picker" (Enter presses the focused button, Use selected when the list has the keyboard; Esc cancels; typing a spool's number jumps to it). Use the load-safe idiom: the shim at the top of `scripts.html` queues a call made before the registry loads. No row names a scan code (`test_no_help_names_a_scan_code` reads every row of a listed scope).
- **Words on screen** (Claude's call 5):
  - `inv_cmd.js:1000`: "Review below, then Commit (or scan the QR under it)."
  - `:1172` (Hide's tooltip): "…use ❌ Cancel here, or scan the QR under it."
  - `duplicate_picker.js:112`: "…queue a label with the chosen spool's own number…"
  - Bulk Move's refusal toasts and Activity Log lines (`logic.py:4032`, `:4037`, `routes_scan.py:1395`) are the Bulk Move polish item's (buglist :616). Leave them, and note it there.

### 73.1, part D — Done's question
- A `registerHelp` entry with `match: {overlay: 'fcc-audit-done-question'}` makes `confirmActivePrint` draw its ? (`inv_core.js:403–407`) and give its title 2.5rem padding on each side, as the move questions have.
- Change on purpose:
  - `test_help_buttons_55_js.py`: the `CALLS` row :44–45 (None → the new key) and `CORNER`'s `done`. `test_a_question_with_no_help_is_drawn_as_it_was` keeps its other no-help row.
  - `test_in_app_help_55_e2e.py:529–551`: Done's question now has its ?.
  - `test_help_texts_55.py`'s two mount checks: the question passes its id through a constant (`ids: { overlay: QUESTION_ID }`, `inv_cmd.js:2566`), which neither check can see today (Tests, below).
  - CLAUDE.md's "(Done's question has none)".
- Re-run, and keep green: the double-click sweep (`test_audit_double_click_58_e2e.py`: the second press of Done…'s double click must still reach nothing; `_shieldPage` covers the question), `test_audit_done_question_58_e2e.py`, `test_audit_place_ids_whole_58_js.py`, and Done's question at phone width (its title has 5rem less room).

### 73.1, part E — the existing 13, and what waits
- Re-check the 13 entries' lines against the code at the group's start (Claude's call 6). Groups 62, 66, 69 and 70 change their dialogs and should have changed these lines; this is the check that they did.
- **Waits for Group 59 or D2:** Settings (59.3, and Group 35) and the vendor editor (59.10).
- **Waits for Group 66** (it comes first in the order): Edit Filament, the vendor editor (66.1), the wizard's existing lines (66.3 drops `help_texts.js:127`'s last sentence), the wizard's Weigh from scale and its questions (66.2).
- **Ready now:** everything else.
- With D2 (a), add a line to `59-design-samples.md` (59.3, 59.10) and `35-config-cluster.md`: "change Settings' or the vendor editor's help lines with the build".

## Tests

Every new test must fail on `95531a6` (prove it with a `git archive` of the base). Hermetic tests use node (`run_js`) where the opener runs under the stub DOM, else `isolated_page` (the real modules in a browser with no network).

- **Offline:**
  - `tests/test_help_texts_55.py`, extended:
    - `match` may name `offcanvas` (and `swal`). `test_each_entrys_dialog_exists` checks an `offcanvas` id against an element with class `offcanvas` in a template, and a `swal` class against a script's `customClass`.
    - `test_every_question_an_entry_matches_draws_its_help_button` learns a third way: the module that mounts the overlay id holds `data-fcc-help="<key>"` in its own markup.
    - Both checks also read an id held in a constant: `const NAME = '<id>'` in a module that mounts with `id: NAME` or passes `overlay: NAME`. As written they look only for the id written out (`id: '<id>'`, `overlay: '<id>'`, `|| '<id>'`, `fccCornerHelpHtml('<id>')`), so seven of this group's overlays would fail them (the list under "Every dialog"). Settings' tag questions go through `_dangerConfirm`, whose id is a parameter: its corner ? is `fccCornerHelpHtml(id)`, a form the checks must also accept, or the ? is drawn with the literal key there.
    - A `GROUP_73_DIALOGS` set beside `FIRST_DIALOGS`, holding D1's set.
    - `SCRIPT_DRAWN` gains any ? drawn with its key in a variable (draw literal keys where you can).
    - The new key rows pass `test_no_help_names_a_scan_code`.
  - New `tests/test_help_buttons_73_js.py` (node or `isolated_page`): each new ? drawn by its real opener, with its key, in its header just before its ✕, Hide or Close (the order check of `test_each_picker_draws_its_own_help_button`), or in its corner. Cover:
    - the Low stock list and its reason dialog, the 🧺 list, 🔎 Find a spool;
    - the legacy picker, the parent picker;
    - the Bulk Move panel, the audit panel, the report window, the 🛑 review;
    - Settings' four questions, the delete question after 62.8;
    - with D1 (b), the 🎯 window, Merge's two steps, Force Location, Weigh from scale.
    - The registry: `fccHelpContextKey()` gives `search` with the offcanvas shown, over the wizard too (its 🔍 Advanced Search); the Low stock list (a `mountOverlay`) over it wins; the help closes on `hidden.bs.offcanvas`, and when a Bootstrap window shown from the panel hides it (`inv_core.js:3621-3626`). With D1 (b), a visible Swal with the class gives `force-location`, and one without gives null, as today.
  - Change on purpose: `tests/test_help_buttons_55_js.py` (part D).
  - Keep green: `tests/test_text_size_floor.py` (new CSS in rem and named sizes), `tests/test_toolhead_types_one_list.py` (no head-Type words in a regex, a words list or a string with "|"), `tests/test_load_order_canary_js.py` (no top-level read of a name another script defines).
- **On the dev container** (read-only: `test_text_size_guard._read_only`, every write answered in the browser):
  - `tests/test_in_app_help_55_e2e.py`'s `WINDOWS` gains `configModal`, `editFilamentModal`, `vendorEditModal`, `locModal`, `locQrViewModal` and `multiSpoolModal`. Each ? sits beside the ✕ and opens its help above the window; Escape closes only the help, and the keyboard goes back where it was.
  - A new `tests/test_in_app_help_73_e2e.py` for the search panel and the overlays:
    - each ? opens its help, and the `?` key does too while the dialog is on top and the keyboard isn't in a text box;
    - Escape closes only the help, and the help closes with its dialog (the dialog's own Escape, its host closing, the offcanvas hiding);
    - a double click on a ? leaves the help up;
    - the Bulk Move panel with Bulk Moves on (dev has it on), and the audit panel, Done's question and the report, each with its session answered in the browser (`_read_only`'s `extra_get`), so no audit or bulk move is ever armed on dev's shared container;
    - each dialog's hotkeys do nothing under the help: the audit's N and arrows, Low stock's Del and /, Find's /, Shift+B over the Bulk Move panel.
  - `test_only_questions_with_help_draw_a_help_button` changes on purpose (part D).
  - `tests/test_contrast_guard.py`: `test_each_windows_help_button_is_readable`'s list gains the six modals (the Multi-Spool Search's ? is dark on cyan). A sibling test scores the search panel's ? and the overlays', plain and hovered (`_the_question_mark_is_scored`).
  - Keep green: the audit sweeps (part D), and `tests/test_quickswap_visual.py`'s shortcut list after its deliberate recapture.
  - Visual baselines, recaptured deliberately (`UPDATE_VISUAL_BASELINES=1`) after a look at each diff: `editfil-basic-tab`, `-specs-tab`, `-colors-tab`, `-advanced-tab`; `search-offcanvas-empty`; `shortcuts-overlay-default` (the new key rows). No baseline or sample of Settings: it shows printer API keys.
- **Before merging:** the independent word check (Claude's call 6), the full run (frontend changes), and one review round with the review checklist's lenses: "what a person reads" first (each line against the code), then "a double click's second press", "stacked overlays", "a scanner is a keyboard".

## Done when

- Every dialog in D1's set has its ? and its help, every line checked against the code. The `?` key opens it while that dialog is on top.
- The search panel (and, with D1 (b), Force Location) answer the `?` key and their ?.
- Done's question has its ?, and the audit's double-click sweep is still green.
- The two pickers' keys show in their help and in the full list.
- No helped dialog's own words name a scan code.
- The 13 existing entries still say what the code does.
- CLAUDE.md and the README say which dialogs have help.

## Risks

- **Words that drift from the code.** Group 55's check found 12 wrong lines in 143. The check is a build step, and it runs after Groups 62–72 have changed several of these dialogs.
- **The wrong help.** `_helpContext()` decides every `?` press. Adding offcanvases changes its sort: the search panel sits at z 1090, above the Bootstrap windows open under it. Pin the orders in part A's test.
- **A hotkey that acts under the help.** A listener added at load before `shortcuts_registry.js` runs before the help's own; letters and digits always pass. Check each dialog (Claude's call 8).
- **Done's question.** Its title loses 5rem of room on a phone, and its pins change on purpose.
- **Settings.** It shows printer API keys: never put it in a picture, a sample or a README shot.
- **On a phone.** The location window's header already hides its ? and ✕ (Group 55 review R4-2, filed for Group 60.2). New ?s in narrow headers can join it; check at phone width, and file what goes wrong for 60.2.

## Owed to CLAUDE.md at the merge

- **"In-app help"** (Project Conventions):
  - the entry count, and the new `match` kinds (`{offcanvas}`, and `{swal}` with D1 (b));
  - "(Done's question has none)" goes;
  - the list of scripts that draw a ? gains the new ones;
  - "Dialogs without help yet come in the documentation overhaul" becomes the list D1 leaves without help;
  - the rule that a dialog's own words follow the help's no-scan-code rule;
  - the new tests (`test_help_buttons_73_js.py`, `test_in_app_help_73_e2e.py`).
- **The README:** `README.md:58–62` ("Help inside the app") names the new windows and drops "(the audit, Low stock, search)". `tests/test_readme_55.py` stays green.

## Prod facts (read-only, optional)

None needed: help is words and buttons, and it reads no data.

## Found while grounding (not in this group's items; for the refresh to file)

> **Filed 2026-11-17 by the refresh:** 1 joined 62.8's item; 2's Edit Filament half became an item of a new member, 66.8, and the location manager's handler an item of 62.4 (check it in a browser first); 3 and 4 became items of 73.1; 5's toasts and log lines joined the Bulk Move polish item; 6 joined 62.5's; 7 became an item of 67.2; 8's box joined 66.4's item and its escaping 71.2's; 9 became 66.8's second item; 10 is already in Group 70's design, which rewrites that toast. The check's other finds: the stale docstring and the dead z-index rules joined 67.7's comments item, the Bind a Slot width 60.2's phone item.

1. **Edit Filament's "Close without saving?" is drawn inside its window, not through `mountOverlay`.** `_editfilShowEscapeConfirm` (`inv_details.js:2776–2854`) appends `#editfil-esc-confirm` to the window's content (`position:absolute; z-index:20000`), with its own document key listener and its own Tab trap. Same class as 62.8's delete question, and missing from Group 15's list (`15-canonical-overlay-mount.md:40` names Force Location's). **Fits: 62.8.**
2. **Edit Filament asks before closing unsaved only on Escape.**
   - Its Cancel and ✕ (`data-bs-dismiss`, `modals_details.html:368`, `:644`) and a click outside close it with no question. It has no `hide.bs.modal` guard (only `escGuardHandler`, `inv_details.js:2748–2766`), where the wizard asks on all of them (`inv_wizard.js:140–175`).
   - By reading, not run: the location manager's Escape handler (`inv_loc_mgr.js:417–461`) listens on the document in the capture phase, so it hears an Escape before any window does. With the keyboard outside a text box (a tab, a dropdown, a button), it acts first:
     - With a place's window open anywhere underneath, its first branch closes or steps back that window (`:435–440`, `closeManage`), and the window on top stays open. That takes the Escape from any window opened over a place's window: Edit Filament, a spool's or a filament's window, the QR view.
     - Otherwise it hides the top Bootstrap window by z-index, unless that window opts out with `data-bs-keyboard="false"`. The page gives each window it shows a z-index above the ones already open (`inv_core.js:3628-3632`), so over the filament window that is Edit Filament itself, closed unasked.
     - Either way Edit Filament's question is skipped. Check both in a browser.
   - **Fits: 66** (Edit Filament's window); the location manager's handler is its own item, for the refresh.
3. **The location editor says "Edit Location" when it adds one** (`modals_loc_mgr.html:62`; `_openLocModalForCreate`, `inv_loc_mgr.js:2742`, never sets the title). Esc closes it without bringing the Location List back, as Cancel, ✕ and Save do (`closeEdit` :2425, :2476). **Fits: 73** (its words) **or 37.**
4. **Settings' own words carry setup and developer words.** No test reads `config_schema.py`'s help for setup names.
   - "Typical: ~2 g short-path (Core One), ~4 g longer-path (XL)" (`config_schema.py:90`): two of the setup-name canary's own patterns.
   - Enable Bulk Moves' help: "(L298)", "dev", "prod", "config.json", "localStorage", "API" (:186–197).
   - "the weight-entry overlay" (:111).
   - "an MMU / indxx upgrade" (`inv_settings.js:329`), "(relocated off FilaBridge)" (:393).
   - "the Edit Filament modal's chip picker" (`modals_config.html:40–41`), `order: 0` and `FIELD_ORDER` (:65–79).
   - The window is "Admin / Config" in its title and tooltip (`modals_config.html:10`, `dashboard.html:144`) and "Settings" in every toast.
   - **Fits: 73** (Settings' word pass, with its help) **or 35 / 59.3.**
5. **The Bulk Move panel and the legacy picker name scan codes on screen** (`inv_cmd.js:1000`, `:1172`; `duplicate_picker.js:112`). **Fits: 73,** folded in by Claude's call 5. Bulk Move's toasts and log lines (`logic.py:4032`, `:4037`, `routes_scan.py:1395`) fit the Bulk Move polish item.
6. **Shift+B arms a bulk move behind the ⌨️ list.**
   - Its handler (`inv_cmd.js:765–818`) checks for a `mountOverlay` and a Bootstrap window, not the list. So with nothing else open, Shift+B pressed while reading the list (it lists Shift+B) arms a session and opens its panel under the list, where it can't be seen.
   - `/` and Ctrl+K stand down under the list (`fab_drag.js:128–132`).
   - **Fits: 62.5** (the ⌨️ list's keys).
7. **Tapping the 📡 pill when FCC doesn't answer opens nothing and says nothing.** `openLogPillOverlay` (`inv_core.js:2865–2868`) fetches `/api/logs` with no catch. **Fits: 67.**
8. **The search panel.**
   - Its box takes a scanned label as words to find: the accumulator skips text boxes (`scripts.html:364`), and "ID:57" matches nothing. Low stock's filter and Find's box send such a scan to the scan path (`installFieldScanCapture`).
   - It draws the server's error text and the materials list as HTML, unescaped: `inv_search.js:280` (`${data.msg}`), `:286` (`${e.message}`), `:340` (`<option value="${m}">${m}</option>`). That breaks Group 58's free-text rule.
   - **Fits:** the "Scanner-OK fields" idea or 66.4's capture for the first; **71** for the second.
9. **The wizard's 🔍 Advanced Search.**
   - A spool picked there whose filament can't be read raises the browser's own `alert()` (`inv_wizard.js:3001`), and its fetch has no catch.
   - The panel then says "Select a spool to insert it into the form." (`inv_search.js:212`) while the wizard has switched it to Filaments (`inv_wizard.js:2964–2966`).
   - The pick writes the filament's vendor, material and name into the page as HTML, unescaped (`inv_wizard.js:2980`, `:2987`): Group 58's free-text rule again.
   - **Fits: 66** (71 for the escaping).
10. **Find Multi-Spool Filaments' network failure is a 2-second "Search Error" toast** (`inv_queue.js:294`; `showToast`'s default is 2000 ms, and errors are owed 7 s). **Fits: 70.4,** beside its failed read.
