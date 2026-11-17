# Group 70: 🏷️ Labels & Print Queue

**Branch name (when started):** `feature/group-70-labels-print-queue`
**Estimated effort:** MEDIUM (~8–12 h, 1.5–2 sessions), plus 70.5's experiment (~2–4 h with Derek at the printer, and only after his two answers). The refresh guessed SMALL–MEDIUM (~5–8 h). Grounding found the "added" toast at ten doors, not three (70.4 a), and February's dead print code to take out with 70.3. Per member: 70.1 ~2–3 h · 70.2 ~1.5–2.5 h · 70.3 ~1–1.5 h · 70.4 ~3.5–5 h ((a) ~1–1.5, (b) ~0.5–1, (c) ~0.5, (d) ~1–1.5, (e) ~0.5) · 70.5 ~0.25 h to ask. These ranges already allow for the usual ~30% overrun. One review round and the full run (~70 min) come on top.
**Risk:** **LOW–MEDIUM.** No Spoolman write changes: the queue's `set_flag` write is untouched, so `tests/test_spoolman_write_sites.py` and the write-surface table stay as they are. The hazards are:
- 70.1 and 70.2 decide what leaves the queue: a wrong rule drops a label or writes it twice;
- the label CSVs are the P-touch templates' data source: their columns, column order, row values and QR text must not change;
- 70.3 removes a route and a template;
- 70.4 (d) shares Group 61's dropdown rule with the location editor;
- 70.5 touches Derek's PC, and only with his OK.

> **Status: TODO, filed 2026-11-16** (/refresh-groups; Derek approved the grouping the same day: "otherwise this seems fine").
> **Place in the recommended order:** step 5, beside 69 and 71 (62 → 63 → 64 and 65 → 66, 67, 68 → 69, 70, 71). **70.1 is built after 67.1** (the same root: Spoolman's error body read as a record). If 67 hasn't merged when this group starts, build 70.2–70.5 first and leave 70.1 for last.
> **Starts:** ready. 70.1–70.4 need nothing from Derek. 70.5 starts with two questions for him, asked cold and one at a time (see Decisions). Its experiment needs him at the printer, and it never holds the merge.
> **Grounded on `dev` @ `95531a6` (2026-11-17)**, read-only. Every member is live. 70.4's "added" toast is at ten doors, not the three the item names. Grounding also found three siblings, now folded in:
> - a double press of 📄 Send sends twice, which doubles rows the same way 70.2 does (70.2);
> - two queue handlers that never run (70.4 a);
> - February's leftover print CSS makes a printed dashboard come out blank (70.3 removes it).
>
> The buglist line numbers the refresh gave (at `706dde7`) are unchanged at `95531a6`. Code line numbers drift, so re-grep before editing.

## Items covered (quoted from `Feature-Buglist.md`)

| # | Buglist item | Direction |
|---|---|---|
| **70.1** 🟠 | *"🟠 Send to P-Touch CSV drops a label Spoolman didn't answer for (found 2026-11-10, Group 55). `get_spool` / `get_filament` give None on a timeout, the row is skipped, the batch still succeeds and the queue empties, so that label is lost; a 404 or 5xx body is truthy and is written as an "Unknown" label row (`labels_csv.py` ~:297-298, ~:373-374, ~:410, ~:469; `spoolman_api.py` ~:196-200, ~:417-421; `inv_queue.js` ~:256-262). The 🟠 "error body read as a record" item above is the same root."* | **Live**, as written. A timeout's None is skipped (`labels_csv.py:297-298`, `:373-374`), the batch answers success, and the page empties the queue (`inv_queue.js:256-263`). A 404 or 5xx body becomes a row of "Unknown … 0g" with a good `ID:` QR, and Spoolman's `message` joins its columns. 67.1 makes the error body a skip; this member says what wasn't written and keeps it in the queue. |
| **70.2** | *"🟡 Re-sending a Print Queue after a locked file doubles rows (found 2026-11-10, Group 55). One failed batch keeps the whole queue (`inv_queue.js` ~:251-262), so sending again sends every kind again, and with Overwrite off each file already written (another kind's, or `labels_locations.csv`, written before a locked `slots_to_print.csv`) gets the same rows twice (`labels_csv.py` ~:213-218, ~:440-450). Keep only the kinds that failed. The help warns of it meanwhile."* | **Live** (`inv_queue.js:256-263`; the two writes at `labels_csv.py:440-441` and `:443-450`; the help's warning at `help_texts.js:230`). **Folded in:** the Send button has no in-flight guard, so a double press sends twice and doubles the rows the same way. |
| **70.3** 🟠 | *"🟠 Scanning a spool card's 🖨️ LABEL QR ends on "Connection Error" and queues nothing (found 2026-11-10, Group 55). In a location window each spool card draws `CMD:PRINT:<id>` under its 🖨️ LABEL (`inv_loc_mgr.js` `renderBadgeQRs`, and the lazy QR draw ~:901). The scan runs `printLabel` (`inv_cmd.js` ~:3426, ~:4585), whose `/api/print_label` always answers `method: 'browser'` (`labels_csv.py` ~:149-157), and the page then writes into `#lbl-brand`, which no template has, so it throws into its catch. A click on the same button queues the label (`addToQueue`). This is what is left of the old browser-print attempt (see "Try printing labels straight to the P-touch again" above): make the QR queue the label as the click does, or retire `CMD:PRINT`. The shortcut list's `CMD:PRINT:<n>` line ("Print a label for the given spool / filament ID") goes with it."* | **Live.** `inv_cmd.js:3426` → `printLabel` (`:4588-4628`) → `/api/print_label` (`labels_csv.py:149-157`). `#lbl-brand` is in no template, so the page throws and toasts "Connection Error" (2 s). The QR queues the label as the click does (Claude's call C3), and February's print code goes with it. |
| **70.4** | *"🟡 Smaller ones from Group 55's map (found 2026-11-10). Queue Label toasts "added" when the label was already queued (`addToQueue` returns false, `inv_queue.js` ~:47-49; `scripts.html` ~:206-214, `inv_details.js` ~:465-467, ~:557). Find Multi-Spool Filaments reads a failed read as "No Multi-Spool Filaments Found" (`print_deduct.py` ~:113-114, ~:169-171; `inv_queue.js` ~:273). The Label Backlog's rows put Spoolman's brand, material and colour name into HTML unescaped (`inv_backlog.js` ~:204-207, ~:226, ~:245-246; Group 58's card-escape rule). A scan read with the Backlog's Type or Sort drop-down focused may move it by type-to-select, with nothing to put it back (reading of the code, not run; the location editor's fix is the model). `data/locations.json.example` is an old sample: the owner's own ids and emoji, no Printer row or `toolheads` list, and `data/README.md` claims types it lacks."* | **All five parts live.**<br>(a) **Wider than written:** ten doors toast "added" whatever `addToQueue` answered (nine live, one never runs), and Print Location Label says nothing at all.<br>(b) `print_deduct.py:115`, `:124`, `:170-172`; `inv_queue.js:273`.<br>(c) `inv_backlog.js:204-207`, `:226`, `:245-246`.<br>(d) Live by reading. The mechanism is proven: Group 61 saw a scan move the location editor's Parent by typeahead in a real browser (its finding s-8).<br>(e) 6 rows of Derek's own ids with 🦝, 5 Types, no Printer row, `toolheads`, `parent_id` or `slot_targets`. The README promises 8 Types and names 2 of today's runtime files. |
| **70.5** | *"🏷️ Try printing labels straight to the P-touch again, without the CSV step (Derek, 2026-11-10). Today FCC writes label CSVs (`labels_csv.py`) and Derek's P-touch Editor templates (the `.lbx` files) read them as their database to print. Only `print_settings.csv_path` is read: the old `print_settings.mode` switch (csv, or browser to print straight to the P-touch) is read nowhere. Derek: "The main reason we use csv's was because I couldn't get labels to print correctly using the ptouch as a printer. I'd love to try again, as the last LLM wasn't good at it, it was fiddly, and it ended up overwriting the whole thing later on. So Yah, maybe we come back and try again some time." The old attempt printed from the browser with a CSS label layout (commits of February 2026, e.g. `dbd846e` "Fix the Garbled CSS" and `c58b822`, both 02-09; it ended on 02-10 at `687f580`: "Last revision on this. Not going to bother anymore on it. Sticking with CSV for now."). Start by asking Derek what printed wrong, and keep the CSVs working beside it until direct printing is proven: they are his templates' data source today. Found while retiring the stale "Label Printer Options" note in `docs/Filament-Command-Center (FCC)/Notes.md` (Group 55.2)."* | **Live:** nothing has changed since 2026-11-10. Only `csv_path` is read (`labels_csv.py:243`, `:505`). Two corrections: the browser attempt ran 2026-02-04 to 02-10 and ended at `687f580` ("Sticking with CSV for now"); `f742981` reverted a CSV change in `api_print_location_label`. Facts gathered for the questions (2026-11-17, read-only): the printer is a Brother PT-P710BT on USB on Derek's PC; P-touch Editor is installed there; Brother's b-PAC kit is not. Starts with D1, then D2. |

## Decisions

### For Derek (70.5): two questions, asked cold and one at a time

Ask D1, wait for the answer, then ask D2. Nothing is built or installed for 70.5 before both are answered.

**D1 (70.5, first). What went wrong when FCC printed labels straight to the P-touch?**
- **What it is.** For a few days in February 2026, FCC printed labels through Chrome's print dialog, straight to your Brother PT-P710BT. A spool card's 🖨️ LABEL printed one label, and the Print Queue window's "🌐 Print via Browser (Now)" printed the whole queue. FCC drew each label on the page itself: the QR on the left, then the brand, colour, material, ID and RGB. On 2026-02-10 you stopped: "Last revision on this. Not going to bother anymore on it. Sticking with CSV for now." Since then FCC writes CSV files, and your P-touch Editor templates print from them. You'd like to try again ("I couldn't get labels to print correctly using the ptouch as a printer"). What went wrong decides which way to try.
- **Where you saw it.** In Chrome's print dialog, then on the tape coming out of the PT-P710BT.
- **What the old commits say happened** (to jog your memory; the other assistant wrote them):
  - a blank page;
  - a "garbled" layout;
  - the printer's "invisible margins" pushing the label right and down;
  - the label "splitting" across the tape;
  - the text made bigger, to be readable.
- **An example answer.** "It printed, but shifted down and right, the QR's edge was cut off, and each label left a long blank tail."
- **Options** (pick every one that happened):
  - (a) a blank label, or blank tape;
  - (b) the label shifted, or cut off at an edge;
  - (c) one label spread over two, or a long stretch of blank tape after it;
  - (d) text too small, cramped or overlapping, or a QR the scanner wouldn't read;
  - (e) the print dialog every time, or the wrong printer or tape size picked;
  - (f) something else (say what);
  - (g) I don't remember.
- **Recommendation.** Answer with whatever you remember; (g) is a fine answer. The first try then prints the same spool's label both ways, side by side, and you compare them.
- **If you don't answer:** nothing is installed or changed for 70.5. It goes back to the buglist as its own item, and the rest of the group goes ahead.

**D2 (70.5, after D1). Which way to try first?**
- **What it is.** FCC runs on the NAS (and dev runs in Docker on your PC), while your PT-P710BT is plugged into your PC by USB. So something on your PC has to do the printing. There are two ways to do it.
- **Where you'd see it.**
  - In (a), a "Print queued labels" shortcut on your desktop (later, maybe a button in FCC).
  - In (b), a 🖨️ Print button in FCC's Print Queue window, then Chrome's print dialog.
- **An example.** You queue #57, #58 and #60.
  - Today: 📄 Send to P-Touch CSV, then open the spool template in P-touch Editor and print.
  - With (a): Send, then double-click "Print queued labels". Three labels come out, from your own template.
  - With (b): 🖨️ Print, then Print in Chrome's dialog. Three labels come out, drawn by FCC.
- **Options.**
  - **(a) A small helper on your PC prints your own templates with FCC's data**, using Brother's free b-PAC kit.
    - The labels look exactly as today, because your templates do the layout, and the CSVs stay FCC's only output.
    - It needs b-PAC installed (it isn't, checked 2026-11-17).
    - b-PAC must support the PT-P710BT. That is checked on Brother's list before you're asked to install anything.
  - **(b) FCC draws the label and Chrome prints it**: February's way, redone with the tape's real size and a calibration setting.
    - Nothing to install.
    - The look is FCC's, not your template's, and Chrome's print dialog comes up every time.
    - The printer driver's margins and page size are what February's commits kept fighting.
  - **(c) Not now.** Keep the CSVs as they are.
- **Recommendation: (a)**, unless your D1 answer points at something b-PAC can't fix. It reuses the layout you have already tuned, and Brother's own software places it on the tape.
- **If you don't answer:** (c). Nothing is installed on your PC without your OK.

### Claude's calls (for veto)

- **C1 (70.1) Read each label strictly, and write a kind only when every label of it was read.**
  - Each spool and filament is read through the `*_answer` helpers (after 67.1).
  - **A label whose record is gone leaves the queue, with words.** That means Spoolman's 404, or an id that isn't a whole number. Example: "#59 is no longer in Spoolman, so its label was taken off the queue."
  - **A label FCC couldn't read keeps its whole kind in the queue**, and nothing of that kind is written. That covers no answer, a 5xx, a body that isn't JSON, or another record. Reading stops there: in an outage each read waits up to 3 s.
  - **Why the whole kind.** With Overwrite on (the window's default), a later send of only the leftovers would replace the file with the leftovers alone. The labels written the first time would vanish from it before they were printed.
  - **A persistent 5xx on one record holds its kind** until that label is taken off the queue. The words name it, so the person can.
- **C2 (70.2) A kind leaves the queue only once its files are written, and a send is one send.**
  - The page removes exactly the labels the answer lists as written or gone, so a label queued during the send stays.
  - With Overwrite off, the server checks every existing file it will append to before it writes any of them.
  - 📄 Send takes no second press while a send is out, nor for 700 ms after one ends.
- **C3 (70.3) The 🖨️ LABEL QR queues the label, as the click does, and February's browser-print code goes:** `printLabel`, `/api/print_label` and `label_spool.html`.
  - Git keeps that code (`687f580`). If D2 picks (b), the print view is built fresh from the queue.
  - **Veto option:** keep that code until 70.5 is decided. It is broken either way.
  - The audit still refuses the QR while its panel covers the window, as it does today.
- **C4 (70.4 a) `addToQueue` says what it did.**
  - `window.addToQueue(item, {say: true})` toasts by its own answer: "Added #57's label to the print queue." or "#57's label is already in the print queue."
  - Every single-label door uses it, Print Location Label included.
  - Bulk adds stay silent and say one summary, as now.
- **C5 (70.4 b)** Find Multi-Spool reads strictly (Group 52's rule). A failed read answers 502 with words, and only a good read with none says "none".
- **C6 (70.4 c)** The Backlog's rows escape Spoolman's text with `window.escHtml`, in the row's text, its `title` and its `data-display`.
- **C7 (70.4 d) One dropdown rule.**
  - The location editor's pure helpers (Group 61) move to `inv_core.js`, and the editor and the Backlog both use them.
  - Group 61's tests (`tests/test_scanner_safe_dialogs_61_js.py`) stay green unchanged.
- **C8 (70.4 e)** The sample locations file is rebuilt from the README demo's made-up seed: one row per built-in Type, with today's fields and no printer logins. `data/README.md` says what it holds and lists today's runtime files.
- **C9 (70.5) Guardrails for the experiment.**
  - Nothing is installed on Derek's PC, and no FCC change is made, before D1 and D2.
  - 📄 Send to P-Touch CSV stays exactly as it is.
  - Nothing marks a label printed by itself: the Backlog's scan or ✔️ Mark Printed still confirms one.
  - A helper lives outside `inventory-hub/`, so it never reaches the Docker image.
  - A "print now" button in FCC, if one ever comes, is a per-browser setting: only the PC with the printer can use it.
  - It uses a new key, never `print_settings.mode`. Dev's untracked `config.json` still says `"mode": "browser"`, and nothing reads it.

## Today's code (anchors, `dev` @ `95531a6`)

Line numbers drift, so re-grep before editing.

### The batch send (70.1, 70.2)
- **The route:** `labels_csv.api_print_batch_csv` (`labels_csv.py:227-491`).
  - The file name comes from the kind; `csv_path` gives only the folder when it holds one (`:236-252`). A bare file name is used as it is, for every kind.
  - A batch dedupes ids by their raw value (`seen_ids`, `:286-291`).
  - Spool kind: `get_spool` at `:297`, `if not raw_data: continue` at `:298`, the row at `:303-317`.
  - Filament kind: `get_filament` at `:373`, the same skip at `:374`, the row at `:379-404`.
  - Location kind: rows from `locations_db.load_locations_list()` (`:268-283`); the slot rows are generated at `:358-366`.
    - An id with no row there asks Spoolman's `/api/v1/location/<id>` for a name (2 s), and any failure names the label by its id (`:327-337`). So Spoolman never loses a location label. `test_batch_location_spoolman_fallback_failure_uses_raw_id` (`tests/test_l316_charact_label_endpoints.py:349`) pins it.
    - `load_locations_list` raises `LocationsCorruptError` only for a file that isn't valid JSON, and the batch's catch-all then answers the exception's text (`:485-491`), so the kind stays queued. Any other read failure comes back as no rows (`locations_db.py:199-201`), and every label is then named by its id.
  - "No valid data found" only when every id was skipped (`:410`).
  - The header logic: `file_exists` at `:417`, then `:420-435`.
  - Two writes: the main file (`:440-441`), then `slots_to_print.csv` (`:443-450`).
  - Success: one INFO Activity Log line and `{success, count, file, msg}` (`:452-469`).
  - A lock: `{success: false, locked: true, msg}` plus an ERROR line (`:471-484`). Anything else: `str(e)` (`:485-491`).
- **The writer:** `_write_label_csv` (`:160-224`).
  - Overwrite is a temp file plus `os.replace` (`:186-212`); append is `open(path, 'a')` (`:213-218`).
  - A held file raises a `PermissionError` tagged `fcc_locked_name` (`:219-224`).
  - The 2026-06-18 probe on this PC (Derek's memory note `project_ptouch_csv_lock.md`): `os.replace` fails whenever P-touch holds the file. An append fails only when P-touch shares the file read-only.
- **The reads:** `spoolman_api.get_spool` `:196-200` and `get_filament` `:417-421` return Spoolman's body whatever the status. `get_spool_answer` is `:203-226`; `get_filament_answer` is `:229-270`.
- **The page:** `inv_queue.js` `printQueueCSV` (`:225-264`).
  - It splits the queue by kind (`:229-231`) and sends one request per kind, all at once (`sendBatch`, `:233-249`).
  - The toasts: success "✅ spool Batch Saved!" at the 2 s default (`:241`); an error 7 s (`:246`); no answer, "connection error" (`:248`).
  - It clears the whole queue only when every kind succeeded (`:256-263`). Nothing stops a second press while a send is out.
- **The window:** `templates/components/modals_queue.html`. The Overwrite switch is `#chk-overwrite-csv`, checked by default (`:23-25`); the Send button is `:29`.
- **The help:** `help_texts.js:220-232` (key `print-queue`). `:226` says "When every file is written, the queue empties", and `:230` warns of the doubled rows.
- **Pins of today's behaviour, to change on purpose:**
  - `tests/test_l316_charact_label_endpoints.py:569-586` pins "No valid data found" by patching `get_spool` to None.
  - The same file patches `get_spool` / `get_filament` at `:464`, `:518`, `:546` and `:597`.
  - `tests/test_label_csv_export.py:98-112` (`_stub_label_helpers`) patches `get_spool`.
- **Contract pins that must stay green:** the label CSVs' columns, order, rows and QR text (`tests/test_l316_charact_label_endpoints.py`, `tests/test_l316_charact_label_helpers.py`, `tests/test_label_csv_export.py`).

### The 🖨️ LABEL QR and February's print code (70.3)
- **The QR:**
  - Drawn by `renderBadgeQRs` (`inv_loc_mgr.js:1394-1400`, `CMD:PRINT:` at `:1398`), redrawn by `_ensureManageQRsFilled` (`:897-912`, `CMD:PRINT:` at `:907`), into `ui_builder.js:251-254` (the loc_list card's 🖨️ LABEL).
  - The click on the same button is `printHoverClick` (`ui_builder.js:204`), which calls `addToQueue`.
- **The scan:**
  - `inv_cmd.js:3426` calls `window.printLabel(parts[2])`.
  - `printLabel` (`:4588-4628`) toasts "🖨️ Requesting Label...", POSTs `/api/print_label`, then writes `#lbl-brand` (`:4618`), which no template has. The throw lands in the catch's "Connection Error" (`:4627`). It is exported at `:4631`.
  - During an audit, `CMD:PRINT:` is refused while the panel covers the window (`_AUDIT_PANEL_COVERS`, `inv_cmd.js:278-287`).
  - A read with a key in front reaches the server, which answers "Malformed Command" (`logic.resolve_scan`'s command ladder, `logic.py:1008-1054`). That is unchanged.
- **The route:** `/api/print_label` (`labels_csv.py:149-157`) reads the spool and answers `method: 'browser'`.
  - Re-exported at `app.py:204-208` (its comment, `:201`, says "the three label endpoints"), pinned at `tests/test_route_table_pin.py:81`, named in the module docstring (`labels_csv.py:1-6`).
- **The template:** `templates/components/label_spool.html` ("STICKER FACTORY v3.0") is still included (`dashboard.html:330`).
  - Its `@media print { body * { visibility: hidden; } }` hides the whole page when printed, and its container (`#printable-queue-container`) is empty. So Ctrl+P on the dashboard prints a blank page.
  - It is the only file `tests/test_text_size_floor.py` allows (`ALLOWED`, `:60-63`). `test_every_allowed_file_still_exists` (`:186-189`) fails if the file goes and the entry stays.
- **The words:**
  - The shortcut list's line is `shortcuts_registry.js:716-720` ("Print a label for the given spool / filament ID"). Only spool cards draw the QR.
  - The location window's help says what the 🖨️ click does, not its QR (`help_texts.js:53`).
- **Test stubs:** `tests/test_audit_page_58_js.py:71` stubs `window.printLabel`, and `:1523` lists `CMD:PRINT:57` among the scans refused under the panel.
- **CLAUDE.md** mentions `printLabel`'s `#print-qr` in the label-confirm row of the write-surface table, and "the three label endpoints" in the module map.

### Queue doors and their toasts (70.4 a)
- **`addToQueue`** is `inv_queue.js:46-77`.
  - It returns false for a label already queued (`:47-49`).
  - Otherwise it posts `set_flag` for a spool or filament (`:53-72`; a failure is a 7 s error toast) and pushes the label (`:74-76`).
  - `addToQueueWithToast` (`:80-83`) says "Added spool to Print Queue" or "Label already in queue". Its only caller is the Prusament overlay's 🏷️ Queue label (`inv_cmd.js:3006-3011`).
- **Doors that toast "added" whatever it answered** (2 s, the `showToast` default):

| Door | Where | Toast |
|---|---|---|
| Spool window's ➕ Queue Label | `scripts.html:202-216` | "Label added to print queue!" |
| Filament window's ➕ Queue Label | `inv_details.js:463-469` | same |
| (its copy, replaced at every open, never runs) | `scripts.html:218-227` | same, and it hides the window |
| Filament window's spool rows, 🖨️ | `inv_details.js:556-560` | "Added to Queue" |
| Search card 🖨️ (spools and filaments) | `ui_builder.js:169` | "Added to Print Queue" |
| Location list card, corner 🖨️ and 🖨️ LABEL | `ui_builder.js:204` | same |
| Box grid tile 🖨️ | `ui_builder.js:268` | same |
| Quick-Swap card 🖨️ | `ui_builder.js:435-437` | same |
| Buffer card 🖨️ | `ui_builder.js:484` | same |
| READY TO SLOT card 🖨️ | `inv_loc_mgr.js:1010` | same; it strips quotes from the display instead of `SpoolCardBuilder.jsArg` |
| 🖨️ Print Location Label | `inv_loc_mgr.js:2149-2153` | none at all |

- **No caller:** `window.handleLabelClick` (`inv_loc_mgr.js:1035-1038`).
- **Doors that already read its answer** (each says "already", except Find Multi-Spool's Add All, which counts only what it added: "Added 0 spools!"):
  - the legacy picker, `duplicate_picker.js:178-197` (69.5b also touches its words);
  - the audit strip, `inv_cmd.js:1626-1636` (its words are the ones C4 uses);
  - the label-reprint prompt, `inv_details.js:2971-2986`;
  - the wizard's chips and Queue All, `inv_wizard.js:3567-3577` and `:3612-3630`;
  - the filament window's Queue All, `inv_details.js:569-590`;
  - the Backlog's Queue Selected, `inv_backlog.js:299-327`;
  - Find Multi-Spool's Add All, `inv_queue.js:297-321`.
- **Pins:**
  - `tests/test_card_buttons_48_review_js.py:100-135` finds each card's handler by the text `addToQueue(` and runs it with an apostrophe in the name.
  - `tests/test_label_queue_rows_48_1_js.py:115-122` pins `js-btn-label" onclick="${printHoverClick}"`.

### Find Multi-Spool (70.4 b)
- **The route:** `print_deduct.api_get_multi_spool_filaments` (`print_deduct.py:109-172`).
  - It reads `GET /api/v1/spool` with `timeout=10` (`:114`).
  - Three ways it answers `[]`: a response that isn't OK (`:115`), a body that isn't a list (`:124`), any exception (`:170-172`).
- **The helper to use:** `spoolman_api.read_spool_list()` (`:345-351`), which answers `(spools, None)` or `(None, why)`.
- **The page:** `inv_queue.js:267-295`. `data.length === 0` toasts "No Multi-Spool Filaments Found" (`:273`). A 502 body would throw in `reduce` and toast "Search Error" (2 s, `:294`).
- **Pins, to change on purpose,** in `tests/test_l316_charact_deduct_misc.py`:
  - `:85` asserts one `requests.get` with `timeout == 10` (the assertion is at `:123`);
  - `:174`, `:185` and `:196` pin `[]` for a failed read.

### The Label Backlog (70.4 c, d)
- **The rows:** built in `fetchBacklog` (`inv_backlog.js:147-273`).
  - `brand`, `material` and `colorOrName` are read at `:204-207`.
  - They are inserted raw into `data-display` (`:226`), the `title` (`:245`) and the text (`:246`).
  - `queueSelectedBacklog` reads `data-display` back (`:307`).
- **The escaper:** `window.escHtml` (`inv_core.js:1550-1554`) escapes `& < > " '`. Group 58's pin for cards is `tests/test_card_free_text_escaped_js.py`.
- **The drop-downs:** `#backlog-filter` (All Types / Spools Only / Filaments Only) and `#backlog-sort` (`modals_missing_labels.html:17-30`), each with `onchange="window.fetchBacklog()"`.
  - The scan accumulator skips only text fields (`scripts.html:364`), so a scan's letters reach a focused select and move it by typeahead.
  - By the options: `ID:` moves Sort to "ID Descending", `OLD:` moves Sort to "Oldest First", `FIL:` moves Type to "Filaments Only" and `SPL:` moves Type to "Spools Only".
  - The Backlog's own help asks for this workflow: keep the window open and scan each label as it goes on (`help_texts.js:243`).
- **The model:** `_installLocEditorEnterToSave` (`inv_loc_mgr.js:2488-2685`: its comment, the function to `:2678`, its install at `:2681-2685`).
  - Its dropdown helpers: `_locTypeaheadMatches` `:2536`, `burstAt` `:2568`, `searchOf` `:2575`, `scanFrom` `:2583`, `putSelectBack` `:2593`, `scanIsOnly` `:2605`.
  - The handler starts at `:2612`.
  - Group 61's proof is `tests/test_scanner_safe_dialogs_61_js.py` (64 test functions, many parametrized), with real keys where the browser's typeahead matters.

### The sample locations file (70.4 e)
- **`inventory-hub/data/locations.json.example`** has 6 rows: `CORE1-M0` and `XL-1` (Tool Head, "🦝 …"), `CR` (Room), `CR-CT-1` (Cart), `CR-MDB-1` (Dryer Box, 4) and `LR-SD-1` (Sliding Drawer). It has no `parent_id`, no Printer row, no `toolheads` and no `extra.slot_targets`.
  - Git keeps it (the root `.gitignore`'s `!` rules, `:23-25`), and `.dockerignore:37-39` ships it in the image. No code reads it; `.githooks/README.md:18` names it.
- **`inventory-hub/data/README.md`:**
  - Its "Seed file" section (`:53-58`) promises one record for each of 8 Types (it adds MMU Slot, Shelf and No MMU Direct Load).
  - Its runtime table (`:20-27`) names `locations.json` and one backup, written "by `app.py` startup".
- **The writers of today's data folder:**
  - `locations_db.py:61-72` (`locations.json`);
  - `startup_migrations.py` (the backups);
  - `cancel_review_store.py:24-28` and `cancel_fetch_store.py:41-45`;
  - `print_deduct_ledger.py:30`;
  - `print_tracker_store.py:29-31`;
  - `attr_migration.py:51-56` (hidden choices and recovery files);
  - `config_loader.py:61` (`config.json.bak`).
  - The `val_*.gcode` captures there are a test's input (`tests/test_deduct_accuracy_56.py:823`).
- **The made-up seed to start from:** `docs/readme-demo/locations.seed.json`, 14 rows: 2 rooms, 2 shelves, a bin (custom Type "Bin"), a 4-slot dryer box bound to heads, a single dryer, and 2 printers with `toolheads` and their 5 heads. Each Printer row carries the demo's fake `printer_creds`.
- **The built-in Types** the editor offers are `_LOC_BUILTIN_TYPES` (`inv_loc_mgr.js:2243-2258`).
- **The file integrity rules** are in `tests/test_locations_json_integrity.py`, which reads dev's real file.

### Direct printing (70.5)
- **What is read:** only `print_settings.csv_path` (`labels_csv.py:243`, and `:505` in the uncalled location route). Nothing reads `print_settings.mode`, and `config_schema.py` has no `print_settings` field, so Settings can't edit it. `config.json.example` holds `csv_path` only. Dev's untracked `config.json` says `{"mode": "browser", "csv_path": "/output/test_queue.csv"}`.
- **Where the CSVs go:** the container writes them to `/output`, which is `${LABEL_OUTPUT_PATH}` (`inventory-hub/docker-compose.yml:17`, `.env.example`).
- **February's attempt** (git history):
  - `90bc32f` (02-04) added the read of a spool for its label.
  - `4e3148f` (02-05) split out `label_spool.html`.
  - `c58b822` and `dbd846e` (02-09) dealt with a blank page and a "garbled" layout.
  - `3f7f857`, `20059fa`, `d281dc2`, `d7e26cb` and `c2816d5` (02-10), then `687f580`, were margin calibrations: the left offset tried from 1 to 6 mm, the top from 0 to 15 mm (8, 15, 11, 0, then 3.5), the label 54 to 70 mm wide in a 60 to 72 mm area, and "If it's splitting the page…".
  - `687f580` (02-10) was the last: "Last revision on this. Not going to bother anymore on it. Sticking with CSV for now."
  - The batch print was `printQueueBrowser` in the retired `static/js/inventory.js` (see `git show 687f580:inventory-hub/static/js/inventory.js`, around `:955`). It drew a 70 × 24 mm CSS label per spool: a QR with `ID:<id>`, then BRND / COLR / MATL / ID# / RGB. Then it called `window.print()`.
- **The printer and templates** (read-only, 2026-11-17):
  - Windows lists "Brother PT-P710BT" on port USB002, not shared.
  - P-touch Editor is installed. Brother's b-PAC is not: there is no `bpac.Document` COM class.
  - The 13 `.lbx` templates sit in the `Brother Labels` folder next to the repo's folder (memory note `reference_ptouch_lbx_label_templates.md`), and all of them target the PT-P710BT.
  - FCC's four templates (Spool, Filament, Location, Slots, each with a DEV twin) use 24 mm tape at fixed lengths: 48.5 mm for spool and filament labels, 60.4 mm for location and slot labels (the DEV location template is 67.5 mm).
- **A hypothesis for D1** (not a fact): February's CSS label was 24 mm tall on 24 mm tape. From memory of Brother's spec, the PT-P710BT prints at most about 18 mm of that height (128 dots at 180 dpi). The driver would then have shrunk or cut the label. Confirm the spec before relying on it.

## Design, by member

### 70.1 — a label that wasn't written stays in the queue, and says why

**What 70.1 takes from 67.1** (`docs/agent_docs/tasks/67-honest-reads-words.md`, 67.1 and its C1 / C2):
- **The root fix.** `get_spool` / `get_filament` hand back the record or None, so an error body is never a label row, even before 70.1 changes anything. 67's design says so in as many words: "The label CSV. An error body is never a label row; the root makes it a skip, as a None is today. Saying so and keeping the queue is 70.1's job."
- **The split.** In `get_spool_answer` / `get_filament_answer` only a 404 means "no such record"; any other answer that isn't the record reads as "couldn't read". Each helper writes the one hub.log line saying what came back, so 70.1 logs nothing about the read itself.
- **The test fake.** 67's tests lift Group 53's per-path canned answers (`_Spoolman.canned`, `tests/test_filament_answer_53.py`) into `tests/spoolman_extra_fake.SpoolmanHTTPFake`. 70.1 uses them for a 5xx on one record.
- **`refusal_words`** with no Spoolman address (67's C9), for any `why` a person reads.
- **If 67.1 hasn't landed:** 70.1 waits. Don't fix `get_spool` here.

**The server** (`labels_csv.api_print_batch_csv`), for the spool and filament kinds:
- **Each id, in queue order:**
  - An id that isn't a positive whole number is *gone* ("#abc isn't a spool number"). It is never read.
  - Otherwise `rec, answered = spoolman_api.get_spool_answer(id)` (`get_filament_answer` for a filament).
  - The record is the one asked for only when it is a dict whose `id` equals the id as a number. Then its row is built exactly as today.
  - Spoolman's 404 (answered, a dict with no `id`) is *gone*.
  - Anything else is *unread*: stop reading, and write nothing for this kind.
- **Dedupe** by the id as a number, so `57` and `"57"` are one label.
- **The answer** adds, beside today's `success`, `count`, `file`, `msg` and `locked`:
  - `written`: the ids whose rows are now in the file;
  - `gone`: `[{id, why}]`, labels to take off the queue;
  - `unread`: `[{id, why}]`, the label FCC couldn't read (its kind stays in the queue).

  `success` is true when the kind's file was written, or when nothing was left to write because every id was gone.
- **The words (`msg`)**, for example:
  - "Wrote 4 spool labels to labels_spool.csv."
  - "Wrote 4 spool labels to labels_spool.csv. #59 is no longer in Spoolman, so its label was taken off the queue."
  - "Couldn't read spool #58 from Spoolman (it didn't answer in time), so no spool labels were written. They stay in the queue: send again in a moment."
- **The Activity Log:** today's success line stays. A kind left unwritten, or a label dropped, gets one WARNING line saying so, escaped (`state.esc` once 67.4 has landed, else `html.escape(..., quote=False)`).
- **The location kind** reads `locations.json` first. It asks Spoolman only for the name of an id with no row, and names the label by its id when that fails (`:327-337`), so Spoolman never loses a location label; that fallback and its pin stay as they are.
  - A corrupt file (`LocationsCorruptError`) answers in 67.6's words, writes nothing, and keeps the kind: "Couldn't read the locations file, so no location labels were written. They stay in the queue." Today it answers the exception's text, with an unescaped log line (`:485-491`).
  - A file `load_locations_list` can't open comes back as no rows, by its contract (`locations_db.py:199-201`), so those labels are written named by their ids. That reader is outside this group (see "Found while grounding").
- **Unchanged:** the CSV columns and their order, every row's values and QR text, and the header rule.

**The page** (`inv_queue.js`):
- `sendBatch` resolves the answer, or null when FCC didn't answer.
- **After every kind settles,** remove from `labelQueue` exactly the `(type, id)` pairs in each answer's `written` and `gone`, compared as text the way `_queueKey` does (`spool:57`), since a door may have queued `57` or `"57"`.
  - Remove them in place: `labelQueue` is `window.labelQueue`, shared with the poll.
  - Then `_renderQueueList()` and `updateQueueUI()`.
  - A label queued during the send stays.
- **An answer from an older FCC** (no `written`): `success` true means every id sent of that kind was written; false means none was.
- **Toasts:** a written kind is a 4 s success; a kind with `gone` labels a 7 s warning; an unwritten kind a 7 s error with the answer's `msg`.
- The window closes only once the queue is empty.

### 70.2 — sending again writes each file once
- **The page** keeps only what didn't land (70.1's rule), so the next send sends only the kinds that failed. Never remove by kind: remove by the pairs the answer names.
- **One send at a time:**
  - a `_sending` flag; while a send is out, 📄 Send reads "Sending…" with `aria-disabled="true"` and a press does nothing. Not `disabled`, which would take the keyboard off the button (the audit strip's "✓ In the print queue" uses the same idiom);
  - a press under 700 ms after the last send ended does nothing (Group 58's double-press figure);
  - a person's Enter on the button goes through the scan accumulator as any button's does (`personMayPress`).
- **The server, in append mode (Overwrite off):**
  - Before writing anything for a kind, open each existing file it will write for append and close it again (`open(path, 'a')`, nothing written).
  - A held file raises there, so the kind writes nothing, and `locked` names that file.
  - Skip a file that doesn't exist yet. Opening it would create it empty, and the `file_exists` test (`:417`) would then never write its header.
- **Overwrite on** is unchanged: a temp file plus `os.replace` can't be checked before it is made.
  - A location send whose `slots_to_print.csv` is held after `labels_locations.csv` was replaced is harmless: the next send replaces both with the same rows.
- **The answer** also names each file and whether it was written (`files: [{name, written}]`), so the toast and the log line can say "labels_locations.csv was written; slots_to_print.csv is locked".
- **Residual, said in the help, not built:**
  - a template opened in P-touch in the milliseconds between two appends;
  - Overwrite switched off between a failed send and its resend.
- **The help** (`help_texts.js:226`, `:230`) says what the code does, and its "gets the batch twice" warning goes. Suggested words:
  - "Each kind (spools, filaments, places) leaves the queue once its file is written. A label FCC couldn't read from Spoolman stays, and nothing of its kind is written, so sending again is safe. One whose spool or filament is gone is taken off, and the toast names it."
  - "When P-touch Editor (or another program) has a file open, that kind stays in the queue and its file is left as it was: close it there, then send again."

### 70.3 — the 🖨️ LABEL QR queues the label
- **The scan.** processScan's branch (`inv_cmd.js:3426`) reads `/^CMD:PRINT:(\d+)$/` on the upper-cased text.
  - **A match** calls `window.addToQueue({id: Number(n), type: 'spool', display: 'Spool #' + n}, {say: true})`, which gives 70.4 (a)'s words. It also writes one INFO Activity Log line through `window.logClientEvent`, naming the spool ("🏷️ #57's label was queued from its card's QR").
  - **Anything else** after `CMD:PRINT:` is refused: a 7 s warning ("That label QR couldn't be read: scan it again."), a WARNING line, and nothing queued.
  - The queue window reads the spool's colour and name when it opens (Group 48.1), so the stored "Spool #57" is only its fallback.
- **Unchanged:**
  - the card's QR text (`CMD:PRINT:<id>`), so no card changes;
  - the audit's refusal while its panel covers the window (`_auditCommandRefusal`);
  - the server's "Malformed Command" for a read with a key in front.
- **February's code goes (C3):**
  - `printLabel` (`inv_cmd.js:4588-4628`) and its export (`:4631`);
  - `/api/print_label` (`labels_csv.py:149-157`), its re-export (`app.py:204-208`), its route pin (`tests/test_route_table_pin.py:81`) and the docstring lines that name it;
  - `label_spool.html` and its include (`dashboard.html:330`), with its `ALLOWED` entry in `tests/test_text_size_floor.py:60-63`.

  Side effect: Ctrl+P on the dashboard prints the page again.
- **The words:**
  - The shortcut line (`shortcuts_registry.js:716-720`) becomes: "Add that spool's label to the print queue (the QR under a card's 🖨️ LABEL)."
  - The location window's help (`help_texts.js:53`) says the QR under 🖨️ LABEL does what the button does. No scan code goes in a help line (Group 55's rule).
  - 62.6 and 62.7 also change this help entry: re-read it first.
- **The stub** at `tests/test_audit_page_58_js.py:71` names the new path, so the panel's refusal test still proves something.

### 70.4 — the smaller ones
- **(a) `addToQueue(item, {say: true})`.**
  - **The words:** a spool is "#57", a filament "filament #12", a place its id.
    - "Added #57's label to the print queue." (success, 4 s)
    - "#57's label is already in the print queue." (info, 4 s)
  - Without `say`, `addToQueue` stays silent, so the bulk doors keep their one summary.
  - **Every door in the table above** passes `{say: true}` and drops its own toast. Print Location Label gains one.
  - The Prusament overlay's `addToQueueWithToast` call becomes `addToQueue(item, {say: true})`, and `addToQueueWithToast` goes.
  - **Dead code goes:** `scripts.html:218-227` and `window.handleLabelClick`.
  - **While there:** READY TO SLOT's 🖨️ (`inv_loc_mgr.js:1010`) passes its display through `SpoolCardBuilder.jsArg`, CLAUDE.md's inline-handler rule.
  - **Keep the test filter working:** each card's handler still calls `addToQueue(`, so `tests/test_card_buttons_48_review_js.py` keeps finding it.
  - **The doors that already read its answer** (the second list above) can move to `say` with the same words, or stay as they are.
  - 69.5b also changes `onPrintClick`'s words: whichever group lands second re-reads it.
- **(b) Find Multi-Spool reads strictly.**
  - **The route** reads through `spoolman_api.read_spool_list()`. A failed read answers 502 `{read_ok: false, error}` with one hub.log WARNING; success stays a bare list.
  - **The page** says:
    - after a 502 or `read_ok === false`, a 7 s warning: "Couldn't read the spools from Spoolman, so FCC couldn't look for filaments with several spools. Try again in a moment.";
    - with no answer, a 7 s warning: "FCC didn't answer, so the search didn't run. Try again in a moment.";
    - after a good read with none, "No filament has two or more spools in stock." (4 s info).
  - 73.1 writes this dialog's help later; it reads these words.
- **(c) The Backlog's rows** escape `brand`, `material` and `colorOrName` with `window.escHtml` at `:226`, `:245` and `:246`.
  - The browser decodes `data-display` when `queueSelectedBacklog` reads it, so the queue gets the whole name.
  - The queue window escapes it when it draws it (`_queueEsc`).
- **(d) The Backlog's Type and Sort keep their value through a scan.**
  - Move the location editor's dropdown pieces to `inv_core.js` as one shared helper: `_locTypeaheadMatches`, `burstAt`, `searchOf`, `scanFrom` and `scanIsOnly`, with what they close over (`BURST_MS`, `TYPEAHEAD_MS`, `textOf`, `payload`), plus `putSelectBack` with the control's name passed in (today it names the control from `sel.id`, `:2598`). The editor calls them unchanged.
  - A small `keydown` listener on `#backlogModal` records the keys typed on a focused select, with the value before each.
  - At a `:` or `/`, or at the scan's Enter, a scan (by the editor's rule) puts the select back to its value from before the scan's first key.
    - It fires `change`, so the list reads again with the old value.
    - It toasts once, in the editor's words, with the option's whole text: `Sort is back to "Newest First (Created Date)": the scan's letters had changed it` (4 s info). The Type drop-down is named "Type".
    - The scan goes out whole (`scanIsOnly`), and a person's jump just before it stays.
  - A person's typeahead and Enter stay a person's, with no "Unknown code" toast.
  - Prove it red on the base in a real browser first. If Chromium doesn't move a focused select there, close this part as not real.
- **(e) The sample.** Rebuild `data/locations.json.example` from `docs/readme-demo/locations.seed.json`:
  - drop every `printer_creds`;
  - one row for each built-in Type (`_LOC_BUILTIN_TYPES`), adding Wall Shelf, Row, Section, Cart, Sliding Drawer, Storage, MMU Slot, No MMU Direct Load and Virtual Room where the demo lacks them;
  - `parent_id` on every row, and only made-up ids and names (SHELF-1, DRYBOX-1, PRINTER-1, HEAD-1), with no emoji;
  - keep the legacy columns the demo seed keeps, since the rows the app writes today carry them.

  Then rewrite `data/README.md`:
  - "Seed file" lists the Types the file holds and says the data is made up;
  - the runtime table lists today's files and what writes each (the anchors above), with `startup_migrations.py` in place of `app.py`;
  - check that `.githooks/README.md` still reads true.

### 70.5 — printing straight to the P-touch: an experiment, after D1 and D2
- **First, ask D1, then D2,** before anything is built (Decisions above). Record both answers in the buglist item, whatever they are.
- **If D2 is (a), the b-PAC helper:**
  1. Check Brother's b-PAC supported-model list for the PT-P710BT. If it isn't there, tell Derek, and offer (b) or (c).
  2. With Derek's OK, install the b-PAC client. Its bitness must match the program that calls it (a 64-bit Python needs the 64-bit client). P-touch Editor's own folder, `Program Files (x86)`, doesn't decide it.
  3. Write a small helper outside `inventory-hub/` (for example `tools/ptouch/`, with its own README). For each label CSV FCC wrote, it opens the matching template, fills its placed objects by name from each row (ID, QR, Brand, Type, Color and the hex chip, per the memory note) and prints.
     - Its paths come from a small local config that isn't committed (the repo is public).
     - It reads only the CSVs. It never talks to Spoolman or to FCC's write routes.
  4. **Proof:** one real spool's label, printed by the helper next to the same label from P-touch Editor. Derek compares the position and size, and scans the QR with his scanner (`ID:<id>` must read).
  5. **Later, only if he wants it:** a 🖨️ Print button in the queue window that calls the helper on `localhost`. It is a per-browser setting (Settings → This Browser), with its key in CLAUDE.md's preferences table.
- **If D2 is (b), a browser print view:**
  1. A print view drawn from the queue at the tape's real size (24 mm × 48.5 mm for a spool label), one label per page, `@page` sized to match.
  2. A per-browser calibration setting for the offsets. `687f580`'s CSS is the starting point, and D1's answer says what to fix first.
  3. The same side-by-side proof.
  4. Any dialog it opens goes through `mountOverlay`.
- **Either way:**
  - each sitting is time-boxed at about 2 h;
  - if it fails, write down what failed in the buglist item, so the next try starts from there;
  - the CSV send and its fixes above stay as they are, because they are the data path for (a) too.

## Tests

Every new test must fail on the group's base commit (check with `git archive` into a scratch folder). Hermetic tests use node's `vm` (`run_js`, as `tests/test_label_queue_rows_48_1_js.py` does) or `isolated_page`. No member needs dev's data.

- **70.1, server, offline:** a new `tests/test_label_batch_70.py`, through the real route and the real `*_answer` helpers over `SpoolmanHTTPFake`, with 67's canned answers for a 5xx on one record. It checks:
  - #57 and #58 are written; a deleted #59 is `gone`, with no row, and the rest are written;
  - a 5xx on #60 writes nothing for spools (the file's bytes are unchanged, in both modes), `unread` names #60, and there is no GET after it (count the GETs);
  - with `down`, nothing is written and there is one GET;
  - an id `"abc"` is gone and never read;
  - filaments behave the same way;
  - a corrupt locations file (`LocationsCorruptError`) writes nothing for places, answers in words and keeps them queued, while an id with no row is still named by its id (`test_batch_location_spoolman_fallback_failure_uses_raw_id` stays green);
  - the WARNING line is escaped;
  - the columns and rows of the labels written are unchanged.
- **Pins changed on purpose:** `tests/test_l316_charact_label_endpoints.py:569-586` (its `get_spool` patch stops intercepting, and the words change) and its `get_spool` / `get_filament` patches (`:464`, `:518`, `:546`, `:597`); `tests/test_label_csv_export.py:98-112`. Move each patch to the `*_answer` helpers in the same commit, or the test reads the configured Spoolman for real.
- **70.1 and 70.2, page, hermetic:** a new `tests/test_print_queue_send_70_js.py`, with the real `inv_core.js` and `inv_queue.js` under node. It checks:
  - `written` and `gone` labels leave, and `unread` labels stay;
  - a label queued during the send stays;
  - an older FCC's answer (no `written`) is read by `success`;
  - with two kinds and one locked, the next send sends only that kind (read the fetch bodies);
  - a double press sends once;
  - the window closes only once the queue is empty;
  - the toast durations.
- **70.2, server, offline** (in `test_label_batch_70.py`):
  - With Overwrite off and `slots_to_print.csv` held (a `PermissionError` from `open(…, 'a')` for that path), `labels_locations.csv` keeps its bytes and `locked` names the slots file.
  - A new file still gets its header: the check never creates one.
  - Overwrite on is unchanged: `tests/test_label_csv_export.py` stays green.
- **70.3, hermetic:** a new `tests/test_label_qr_70_js.py`, with the real `inv_cmd.js` and `inv_queue.js`. It checks:
  - `CMD:PRINT:57` queues #57 once, with one `set_flag` POST answered in the page, "Added #57's label…" and one INFO log line;
  - a second scan says "already";
  - `CMD:PRINT:57X` is refused with words, and nothing is queued;
  - under the audit panel it is still refused (`tests/test_audit_page_58_js.py`, its stub renamed);
  - a source canary: no `window.print(` and no `/api/print_label` under `static/js`, and no `label_spool.html` include.

  The route pin and the text-size floor change in the same commit.
- **70.4 (a), hermetic:** a new `tests/test_queue_label_words_70_js.py`. It checks:
  - each door in the table says "Added …" the first time and "… already in the print queue" the second, with no other toast;
  - the bulk doors keep one summary;
  - `tests/test_card_buttons_48_review_js.py` and `tests/test_label_queue_rows_48_1_js.py` stay green.
- **70.4 (b):** the route pins above, changed on purpose, plus a hermetic page check in `test_queue_label_words_70_js.py`: a 502 says "couldn't read", never "No Multi-Spool…", and no answer says "FCC didn't answer".
- **70.4 (c):** a Backlog row for `Odd "Quote" <b>Tag</b> & Co` (Group 58's pattern, `tests/test_card_free_text_escaped_js.py`). The text is whole, with no `<b>` element; the `title` is whole; and Queue Selected queues the whole name.
- **70.4 (d):** `isolated_page` with real keys, `tests/test_scanner_safe_dialogs_61_js.py`'s pattern, in a new `tests/test_backlog_dropdown_scan_70_js.py`. It checks:
  - with Sort focused, a burst `ID:57` then Enter: Sort is back, the list reads again with the old sort, the toast shows, and `ID:57` reaches processScan whole;
  - a slow scanner (100 ms a key) the same;
  - `OLD:12` on Sort and `FIL:12` on Type;
  - a person's "b" then Enter keeps Brand and sends no scan.

  Group 61's file stays green unchanged.
- **70.4 (e), offline:** a new `tests/test_locations_example_70.py`, or `tests/test_locations_json_integrity.py`'s file rules parametrized over the example. Leave out `test_every_printer_map_prefix_has_a_parent_or_is_synthesized` (`:211`): it asks the dev container's `/api/printer_map` and `/api/locations` over HTTP. It checks:
  - the file is valid JSON and passes the integrity rules;
  - one Printer row has `toolheads`, and its heads are rows parented to it;
  - a multi-slot Dryer Box's `slot_targets` name heads that are in the file;
  - no `printer_creds` and no emoji;
  - none of Derek's ids appear (a deny list: `XL-`, `RCOI`, `CORE1`, `CR-`, `LR-`, `PM-`);
  - every Type the README lists is present.
- **70.5:** the proof is Derek's side-by-side at the printer.
  - A helper script gets a unit test of its row-to-object mapping, with a stand-in for b-PAC and no printer.
  - A browser print view gets a hermetic test of its size and contents.
- **Help and shortcuts:** `tests/test_help_texts_55.py` and `tests/test_help_buttons_55_js.py` for every changed line. No scan code goes in a help line.
- **Standing orders that apply:**
  - toasts at 4 s for a success and 7 s or more for an error;
  - named text sizes, if any surface is touched;
  - the keyboard idiom and scanner-safe keys (`enterIsAScan`, `scanIsArriving`, `personMayPress`);
  - `mountOverlay` for any new overlay (none is planned);
  - plain words and made-up examples in help;
  - Activity Log lines escaped;
  - module-qualified calls, patched on their defining module, in Python 3.9 syntax;
  - the route pin;
  - the load-order canary: the shared dropdown helper is read only when code runs, never while a module loads;
  - `tests/test_spoolman_write_sites.py` unchanged, since no Spoolman write changes.
- **No member needs the dev container.**
  - The full run comes before merging, because the frontend changes.
  - No browser test may press 📄 Send against the real container unless `/api/print_batch_csv` is answered in the page. Dev's container writes the label CSVs into `/output`, the folder the DEV templates read.

## Done when

- A label Spoolman didn't answer for stays in the queue, a gone one leaves it with words, and no error body becomes a label row.
- Sending again writes each file once:
  - the kinds already written leave the queue;
  - a held file in append mode writes nothing of its kind;
  - a double press sends once.
- A card's 🖨️ LABEL QR queues the label as the click does, and February's print code and its route are gone.
- Every single-label door says "already in the print queue" when the label is already queued.
- Find Multi-Spool says "couldn't read" when it couldn't.
- The Backlog's rows are escaped, and a scan never leaves its Type or Sort moved.
- The sample locations file is made up and current, and its README says what it holds.
- **70.5:** D1 and D2 are answered and recorded. Then either the experiment has run (kept behind a per-browser setting, or written down as not working), or 70.5 is back in the buglist with his answers.
- The help, the shortcut list and CLAUDE.md say what the code does.

## Risks

- **What leaves the queue.** A wrong rule drops a label or writes it twice. Remove by the `(type, id)` pairs the answer names, never by kind, and test a label queued during the send.
- **A stuck kind.** A persistent 5xx on one record holds its whole kind until that label is taken off the queue. The words name it.
- **Patch semantics.** Once the route reads through the `*_answer` helpers, every test that patches `get_spool` / `get_filament` for it stops intercepting. Move the patches in the same commit.
- **A removed route.** The route pin, `app.py`'s re-export and the text-size allowance change in the same commit. A page loaded before the release still runs `printLabel` on a `CMD:PRINT` scan, and fails as it does today.
- **Group 61's code.** 70.4 (d) moves its dropdown helpers. Its tests guard them: run that file before and after.
- **Derek's PC.** Nothing is installed or run there without his OK, and the CSVs stay exactly as they are.
- **The full run writes to dev** (CLAUDE.md), and the queue's Send writes dev's label folder: route it in every browser test.

## Owed to CLAUDE.md at the merge

- **The module map's `labels_csv.py` row:**
  - name the label endpoints left after 70.3 (not "the three label endpoints");
  - one line on the batch's answer: a kind is written only when every label of it was read, and the answer names `written`, `gone`, `unread` and each file.
- **The label-confirm row** (`_verify_spool_label`) in the write-surface table: "(`labels_csv.py`; `printLabel`'s `#print-qr`, which no page has)" becomes "(`labels_csv.py`)".
- **A convention line:** a door that queues one label calls `window.addToQueue(item, {say: true})`; a bulk add stays silent and says one summary.
- **Group 61's sentence in the keyboard paragraph:** the shared dropdown helper's name, and that the Label Backlog's Type and Sort use it.
- **If 70.5 adds a per-browser setting:** its key in "User preferences".

## Prod facts (read-only, optional)

- **70.1–70.4** need no prod fact.
- **For 70.5 only: does prod's `config.json` carry `print_settings.mode`?** Dev's untracked one says `"browser"`, and `config.json.example` holds only `csv_path`. A new setting must not read that key either way. One read of prod's config on the share answers it, or Derek can look.
- **Does a template open on Derek's PC stop prod's CSV write at all?** Not known.
  - The 2026-06-18 lock probe ran on this PC, where dev's Docker writes into a Windows folder.
  - Prod writes on the NAS, and P-touch reads the files over the network share.
  - The 70.2 fix is right either way. Derek would see the answer in his normal use: a Send with the template open either writes or says "locked".

## Found while grounding (not in this group's items; for the refresh to file)

> **Filed 2026-11-17 by the refresh:** 1 joined 70.4's item; 2 70.3's; 3 70.2's; 4 joined 62.3's (Group 62's double-click sweep); 5 is done (the item now names `687f580`); 6 joined 67.6's item.

Folded in, not for the refresh: the double press of Send (70.2); the dead filament-window handler and `handleLabelClick` (70.4 a); READY TO SLOT's quote strip (70.4 a); the words for a corrupt locations file (70.1); the blank printed dashboard (70.3).

1. **Every queued label writes Spoolman, even when its flag is already up, and a bulk add writes them all at once.**
   - `addToQueue` posts `/api/print_queue/set_flag` for each spool or filament (`inv_queue.js:53-72`).
   - `set_flag` reads the record and writes `needs_label_print` whatever it held (`routes_print_queue.py:171-215`). With `update_spool`'s own pre-merge read, that is three Spoolman requests per label.
   - The bulk doors call it in a loop without waiting: Find Multi-Spool's Add All (`inv_queue.js:297-321`), the filament window's Queue All (`inv_details.js:569-590`) and the Backlog's Queue Selected (`inv_backlog.js:299-327`). Every Backlog row is flagged already, so each of its writes changes nothing.
   - Thirty labels are thirty `set_flag` requests at once, about ninety Spoolman requests in all, and each refusal is its own 7 s error toast.
   - **Wanted:** no write when the flag is already up (the audit's rule in `logic._audit_mark_label`), and one request for a bulk add.
   - **Fits:** 70.4, or a later label group.
2. **`/api/print_location_label` has no caller.**
   - 🖨️ Print Location Label queues the label instead (`inv_loc_mgr.js:2149-2153`).
   - So the route (`labels_csv.py:494-637`, about 145 lines that write `labels_locations.csv` and `slots_to_print.csv` directly) runs only in its tests (`tests/test_l316_charact_label_endpoints.py:113-280`).
   - **Fits:** 70.3's clean-up (with its route pin and re-export), or it stays.
3. **With Overwrite on, a location send leaves the last batch's slot labels in `slots_to_print.csv`** when none of its places has slots. The slots file is written only when one has (`labels_csv.py:443-450`), so the slots template still holds old rows. Probably as meant: one help line, or emptying that file on an Overwrite location send, would settle it. Low.
4. **📄 Send can close the Print Queue window under the pointer.** When every file is written, the window closes (`inv_queue.js:256-262`). After a quick send, a slow double click's second press may land on whatever lies behind the button: Group 58's double-press class. It isn't in 62.3's door list; add it to that sweep.
5. **Paperwork.** The buglist's 70.5 item cites `f742981` ("Reverting change.") as the end of the browser attempt. By its diff, that commit reverted a change to `api_print_location_label`'s CSV writing. The browser print ended at `687f580` (2026-02-10). Done 2026-11-17: the refresh corrected the item's text.
6. **`locations_db.load_locations_list` reads a file it can't open as "no locations".** It raises only for a file that isn't valid JSON (`LocationsCorruptError`); any other read error is logged to hub.log and answers `[]` (`locations_db.py:199-201`). Every reader then sees an empty location list: here, location labels written named by their ids; elsewhere, Group 52's "couldn't read, never empty" rule broken for the locations file. 67.6 guards `resolve_scan`'s own read only. **Fits:** a standalone item, or 67.6's family.
