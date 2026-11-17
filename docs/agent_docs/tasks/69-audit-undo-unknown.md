# Group 69: ↩️ Audit, Undo & Unknown

**Branch name (when started):** `feature/group-69-audit-undo-unknown`
**Estimated effort:** MEDIUM–LARGE (~12–20 h, 2–3 sessions, with this project's usual ~30% overrun counted in). This is more than the proposal's ~6–10 h, because grounding found two things: 69.1 is a new window with its own write and question, and 69.2 has to drop deleted spools and keep a record's own spools together. Per member, before the overrun: 69.1 ~4–6 h · 69.2 ~2–3 h · 69.3 ~1–1.5 h · 69.4 ~0.5–1 h · 69.5 ~1–1.5 h · 69.6 ~0.5–4 h, depending on Derek's three answers. On top of that come one review pass and the full run (~70 min).
**Risk:** **LOW–MEDIUM.** Two writes change. One is Undo: every move's Undo goes through `logic.perform_undo`. The other is a new bulk archive. Both read strictly before they write, and they say what they did. The rest is words, one stock rule and one page fix.

> **Status: TODO, filed 2026-11-16** (/refresh-groups; Derek approved the grouping the same day: "otherwise this seems fine").
> Fifth in the recommended order, beside 70 and 71. Before it come 62, then 63, then 64 and 65, then 66, 67 and 68. It is ready to start. It opens with three small calls of Derek's (69.6), asked cold and one at a time. Nothing else waits on him. 69.1's window gets a picture before the merge, because it is a new look.
> This group holds Undo's leftovers from Group 58's re-review, a one-step way to archive spools that are really lost, the audit panel's words, and three small label and stock calls.
> Every member was checked against the code on `dev` @ `3388c7d` on 2026-11-16, and all of them are live. Line numbers drift, so re-grep before editing.

**Read first:** Group 63's answer on archived spools (63.1). Its trace touches "an archive at Unknown". 69.1 writes no weight, so it writes no pre-archive note, but check that nothing in 63's answer contradicts it. Also read Group 67.1. It changes `get_spool` callers, and `perform_undo` is one of them. If 67 lands first, re-check 69.2's anchors.

**Related, not a member:** a Redo for Undo. Derek: undecided, "a maybe-later (the command deck is already crowded); don't build it".

## Items covered (quoted from `Feature-Buglist.md`)

The quotes are taken from `dev` 3388c7d, without their "**Standalone.**" tag. Every item is **live** on `dev`; the evidence is under "Today's code".

| # | Buglist item | Direction |
|---|---|---|
| **69.1** | **🗑️ Clear spools out of Unknown in one go (filed 2026-11-02, Group 58's build spec).** An audit's Done parks the spools it didn't find at Unknown, and each now says which audit lost it, but a spool that is really gone takes a visit to its own window to archive. Derek wants lost spools "easy to find, assign or clear later". Wanted: a bulk write-off from the Unknown list: tick the ones that are gone, one question, and they are archived (nothing moved, their note kept). Where: the Unknown list in the Location Manager (`inv_loc_mgr.js`, the `loc_list` cards in `ui_builder.js`), the writes through `update_spool` with `archived: true`. Bulk Move's plan from `UNKNOWN` already lists parked spools (behind its flag), but it moves them, it can't archive them. | **Live.** A 📦 Archive lost spools… button on the Unknown view opens a tick list. One question shows every ticked spool as a colour tile and opens on Cancel. Each ticked spool still filed at Unknown is archived where it is, with its note kept. Picture before the merge. |
| **69.2** | **↩️ Ordinary Undo pops its record before its checks (found 2026-11-02, Group 58's re-review).** `logic.perform_undo` takes the record off the stack first (`state.UNDO_STACK.pop()`), and for a record with no `only_if_at` (every move but an audit's park) a restore that fails, or a spool that can't be read, answers "Undo partly failed" with the record gone, so the spools it didn't reach can't be put back with Undo Last Move. Group 58's guarded records put a copy holding only those spools back in the record's place (`retry`); ordinary records don't. Wanted: the same for them, or the record kept until the restores are known. | **Live.** Ordinary records get the park's retry copy, with the same id and in the same place on the stack. A deleted spool is dropped and named, so it never blocks Undo. A spool that waits on another spool of the same record waits with it. |
| **69.3** | **↩️ A park's Undo in a Spoolman outage takes a read timeout per spool (found 2026-11-02, Group 58's re-review).** `perform_undo` reads each spool of an audit's park right before its write (`_undo_guard_kind` → `get_spool_answer`), so with Spoolman down every remaining spool waits out its own read (about 3 s each), and a 30-spool park takes most of the page's 120 s before it answers "Press Undo Last Move again". Wanted: after two reads in a row that get no answer, count the rest unreadable without reading them (they stay on the retry copy). | **Live, and wider than written:** the question pays the same cost (`_undo_guard`). One counter per request covers the question's reads and the Yes's reads alike. The words stay the same. |
| **69.4** | **↩️ Return names Unknown as the place a spool came from (found 2026-11-02, Group 58's re-review).** A spool on a head whose trail (`physical_source`) is `UNKNOWN`, written before Group 58 made Unknown no home (`_ghost_trail_from`), reaches `_return_plan` (routes_bindings.py), which finds no row for it and says "#57 came from UNKNOWN, which isn't in the location list any more". Unknown is the lost list, never a row and never a home: the eject already reads such a trail as none (`_eject_destination`). Wanted: Return reads it as no recorded box too, with words to match. | **Live.** Return reads that trail as none. Grounding found a sibling with the same root: the Unknown list still shows such a spool as a DEPLOYED card (`_build_location_match`), so this member fixes that too (Claude's call). |
| **69.5a** | **📜 A refusal notice shrinks the audit panel's body, so the keyboard's tile can slip under the strip (found 2026-11-02, Group 58's re-review).** `#fcc-audit-panel-notice` sits outside the scrolling `#fcc-audit-panel-body`, so a refusal shown there takes height from the body, and the tile the arrows last cleared of the Last found strip (`_tileClear`, inv_cmd.js) can sit under the strip until the next key moves it. Wanted: `_tileClear` again when the notice changes, for the tile with the keyboard. | **Live, reworded.** Group 58 replaced the sticky strip with a dock under the list. The gap remains in another form (pre-refresh audit, finding I-56-61-8): a notice can push the keyboard's tile past the bottom edge of the scrolling part, just above the dock. The fix is the one the item asks for. |
| **69.5b** | **🖨️ The legacy picker's "Print new label" toast lands under the audit panel (found 2026-11-02, Group 58).** During an audit the picker opens over the panel. Its 🖨️ closes it and says "Added Spool #57 to Print Queue" (or "Label already in queue") in a toast, and the toast layer is under the panel, so the person sees the picker close and nothing else. `#fcc-audit-panel-notice` repeats scan refusals only. Where: `onPrintClick` in duplicate_picker.js; `window.auditPanelNotice` would say it on the panel as well. | **Live.** The same words also go on the panel's notice line. |
| **69.6a** | **🏷️ A scan outside an audit clears a reprint flag (filed 2026-11-02, Group 58's Decision 3).** Outside an audit an `ID:` label read confirms any status that isn't already confirmed, a flagged one too (`routes_scan._verify_spool_label`). So after a filament rename flags its spools, scanning one of their old labels takes it out of the 🏷️ Backlog with the reprint forgotten, and nothing on screen says so. Inside an audit a scan now confirms only a missing status (`_audit_label_check`, Derek's default (b)). Wanted: a look at the same rule outside one. The catch: a freshly stuck label needs some scan to clear its flag. | **Live. ❓ Derek's call 1**, asked at the start. |
| **69.6b** | **🏷️ A `LEG:` label reads as "no label read" on the audit's strip (found 2026-11-02, Group 58.2).** Only an `ID:` label read by a scanner counts as a label read (`routes_scan._is_label_read`, the same test as outside an audit, as the spec says), so a spool found by its old `LEG:` label gets "No label was read for #57" on the Last found strip (`_stripLabel`, inv_cmd.js) and "found, no label read" on its tile (`_labelWords`), though a label really was read. It writes nothing, so it is only a nudge at the wrong spool, and maybe only needs different words. Its own small decision: does an old label count as a read? | **Live. ❓ Derek's call 2**, asked at the start. |
| **69.6c** | **🟡 Low stock counts spools parked at Unknown (found 2026-11-01, Group 58's study).** `stock_report.py` has no location handling, so a spool at UNKNOWN (physically lost) still adds its grams and can keep a filament off the Low list. Its own small decision: does a lost spool count as stock? | **Live. ❓ Derek's call 3**, asked at the start. |

## Decisions

### For Derek, at the group's start (69.6): three small calls, asked cold and one at a time

**Call 1 (69.6a): a label scan outside an audit, on a spool flagged for a new label.**
- **What it is.** When a spool's printed label is out of date, FCC raises its "needs a label" flag, and the spool shows in the 🏷️ Label Backlog. Today, outside an audit, any scan of the spool's `ID:` label marks the label as confirmed, even over that flag, and the spool leaves the Backlog. During an audit, a scan confirms only a spool that has no label status at all, and a flag stays up. That was your rule (b) for Group 58.
- **Where.** The scan path, `routes_scan._verify_spool_label`.
- **A real example.** You change filament #12's colour name. FCC flags the labels of its spools #57, #58 and #60, and they show in the Backlog. The next day you move #57 to XL-2 and scan its old label, as usual. FCC marks it confirmed, #57 leaves the Backlog, and its new label is never printed. Nothing on screen says so. The Activity Log only says "✔️ Spool #57 Label Verified".
- **The catch.** The new label holds the same text as the old one (`ID:57`), so FCC can't tell them apart. The Backlog's own help says "Scan a new label to confirm it: its row leaves the list within a few seconds". So today, a scan is how a freshly printed label gets confirmed.
- **Options.**
  - **(a) Keep the rule, but show it.** A scan that clears a flag says so, in a toast and its log line: "#57's label is confirmed, and its 'needs a new label' flag is cleared."
  - **(b) Your audit rule everywhere.** A scan confirms only a spool with no label status. A flag stays up until you press ✔️ Mark Printed in the Backlog, which replaces the Backlog's "scan to confirm" step.
  - **(c) A scan clears a flag only while the 🏷️ Label Backlog window is open.** That is the Backlog's own workflow: "Keep this window open while you label a batch, and scan each label as it goes on". Anywhere else the flag stays, and the scan says so: "#57 still needs a new label: once it's on, scan it with the Label Backlog open."
- **Recommendation: (c).** The Backlog workflow keeps working, and a routine scan of an old label can't erase a reprint reminder.
- **If he doesn't answer: (a).** The rule stays the same; only the words change.

**Call 2 (69.6b): an old `LEG:` label read during an audit.**
- **What it is.** Many spools still wear a label from your old spreadsheet, `LEG:<number>`. That number names a filament, not one spool. When the filament has one spool in stock, the scan finds that spool. When it has two or more, a picker asks which one. During an audit, only a scanned `ID:` label counts as "a label was read".
- **Where.** `routes_scan._is_label_read`, plus the audit panel's words in inv_cmd.js: the Last found box (`_stripLabel`) and the tiles (`_labelWords`).
- **A real example.** You audit LR-MDB-1. #57 still wears only its old label, LEG:12. You scan it. The Last found box says "No label was read for #57", and its tile says "✅ found, no label read", even though you just scanned a label. On dev, which is a copy of your data, 135 of 191 filaments carry a legacy number, and 99 of them have exactly one spool in stock. For those, the scan goes straight to the spool.
- **Options.**
  - **(a) Leave it as it is.**
  - **(b) Count it as a label read.** A spool with no label status gets marked as confirmed, as an `ID:` scan does. FCC would then treat it as wearing a good FCC label, which it doesn't. Your planned repair of the spools with no label status (a PENDING DEREK item) could no longer find it.
  - **(c) Say what happened, and write nothing.** The Last found box says "#57 was found by its old label (LEG:12): it has no FCC label yet", and the tile says "found by its old label".
- **Recommendation: (c).** The words become true, and they point toward Needs a label.
- **If he doesn't answer: (c).** It only changes words and writes nothing.

**Call 3 (69.6c): a lost spool in Low stock.**
- **What it is.** Low stock adds up the grams of every spool in stock: not archived, with grams left. A spool an audit parked at ❓ Unknown still counts as in stock, so its grams are added.
- **Where.** `stock_report.in_stock`. It is the one rule behind the Low stock list, the title bar's ⚠️ count and the low-stock warning.
- **A real example.** An audit of LR-MDB-1 parks #57 (Galaxy Black, 600 g) at Unknown. Your only other Galaxy Black spool has 100 g left. Low stock counts 700 g, which is over the 250 g line, so Galaxy Black isn't on the Low list. Yet the only Galaxy Black spool you can find has 100 g.
- **Options.**
  - **(a) Keep counting it (today's rule).** A spool that is really gone leaves stock once you archive it, and 69.1 makes that one step.
  - **(b) Stop counting a spool at Unknown, and say so on its filament's Low or Out row:** "+ 1 lost at ❓ Unknown (600 g)". You can then look for it before buying.
  - **(c) Stop counting it, and say nothing.**
- **Recommendation: (b).** Low stock answers "should I buy more?", and a spool nobody can find won't print. The row still tells you that one may turn up.
- **If he doesn't answer: (a).** Nothing changes.

### Claude's calls (for veto)

- **69.1, the window.** A button on the Unknown view opens a window of its own with a tick on each row. The ticks don't go on the cards themselves, because `SpoolCardBuilder.buildCard` is shared by every list.
  - Its words say "Archive", FCC's word for it (the wizard's Archived box), and it uses 📦, as FCC's archive log lines do.
  - It has no QR. Archiving lost spools is done at a desk.
  - A scan while it is open goes on to the scan path as usual.
- **69.1, no Undo.** To bring a spool back, open it and untick Archived. It then returns to the Unknown list with its note. Undo Last Move puts moves back, and an archive isn't a move. If Derek wants an Undo for it, `perform_undo` needs to restore `archived` too, about 1 h more.
- **69.1, what gets archived.** Only a spool whose own location is still Unknown, that isn't archived already and isn't in the scan buffer, is archived. Any other spool is left as it is and named: one that turned up meanwhile, one in your hand, one already archived, or one that is gone from Spoolman. The write-off is refused while an audit runs or a bulk move is armed, as Undo is (`routes_locations.py:1105-1112`).
- **69.2, deleted spools.** A deleted spool is dropped from an ordinary record and named, as a park's Undo already does. Today a deleted spool makes an ordinary Undo's question refuse for good. Group 58 pinned that on purpose as "still refuses" (`test_audit_undo_58.py::test_an_ordinary_undo_with_a_deleted_spool_still_refuses`). With a retry copy it would become a permanent block, so the pin changes on purpose.
- **69.2, the writes.** Ordinary restores write through `logic._move_write`, as the park's Undo does. A write whose answer was lost is read back, and counts as done if it landed, instead of being offered again.
- **69.3, scope.** The cutoff counts per-spool reads only. A place's read is already made once per Undo. The cutoff also covers ordinary records, once 69.2 makes their reads go through the same helper.
- **69.4, scope.** The Unknown list's ghost card is fixed along with Return. One rule says a trail of `UNKNOWN` is no trail, and every reader of a trail uses it.
- **69.5b, the look.** The message goes on the panel's notice line as that line is today (amber). There is no new "good news" tone; that would be a new look.

## Today's code (anchors, `dev` @ `3388c7d`)

Line numbers drift, so re-grep before editing.

### 69.1: the Unknown list
- **The row.** The `/api/locations` builder always adds the virtual row `{"LocationID": "UNKNOWN", "Type": "Unknown", ...}` at the bottom (`routes_locations.py:309-325`). Its count includes only spools filed there (`:119-122`).
- **The view.** `window.openManage` (`inv_loc_mgr.js:206`) draws it as a list (`_isGridLoc` `:192` is false) from a strict read (`_readContentsStrict` `:199`, `/api/get_contents?id=UNKNOWN&strict=1`, `api_get_contents_route`, `routes_locations.py:1131`). `renderList` (`:1227-1346`) builds each card with `SpoolCardBuilder.buildCard(s, 'loc_list')` (`ui_builder.js:198-262`), whose ❓ Lost badge (`unknownBadge`, `:44-50`) reads `details.lost_from` (`spoolman_api.audit_lost_from`, `:2369-2390`).
- **The read.** `get_spools_at_location_detailed` (`spoolman_api.py:2566`) leaves archived spools out, so a spool archived at Unknown leaves the list. It goes through `_build_location_match` (`:2490-2563`), which **also lists a spool whose trail is `UNKNOWN` as a ghost** (`:2531-2538`): a DEPLOYED card with ↩️ RETURN. See 69.4.
- **The write it needs.** `spoolman_api.update_spool(sid, {'archived': True})` (`:833`). The write carries no weight key, so the archive edge `_auto_archive_on_empty` (`:495`, returns at `:535`) adds nothing to it. The spool keeps location `UNKNOWN` and all its extras, `fcc_pre_audit_location` included, and no pre-archive note is written. Once the write lands, `update_spool` logs one line per spool ("📦 Archived Spool #N — still at UNKNOWN", `_archive_line` `:751`). A write whose answer was lost goes through `_after_unanswered_write` (`:984-1016`).
- **Patterns to reuse.**
  - Ticks: the 🏷️ Backlog's checkboxes, Select All and "🖨️ Queue Selected (N)" (`inv_backlog.js:185-316`).
  - A list window: the 🧺 Loose spools list (`inv_loose.js`, `window.openLooseList` `:369`: `mountOverlay` with `trapTab`, `.kb-active` rows, registered shortcuts).
  - A question of colour tiles: Done's (`confirmActivePrint` with `sections` of `tiles: true`, `window.fccSpoolTileHtml`, `armAfterMs`, `fccFitQuestion`).
- **Help.** The location window's entry (`help_texts.js:46-70`, key `location-window`) has `sections` with `when` selectors, which is where a line for the Unknown view's button goes.

### 69.2: ordinary Undo
- **The pop.** `logic.perform_undo` (`logic.py:5198-5603`) pops at `:5225` (`stack_place` `:5226`).
- **The park's retry copy.** `logic.py:5582-5591`: `copy = dict(last, moves=retry)`, then `state.UNDO_STACK.insert(stack_place, copy)`, with the same id, under anything pushed meanwhile.
- **The ordinary path.**
  - Moved spools: `cur = spoolman_api.get_spool(sid) or {}` (`:5391`); `_blocked` reads a one-spool head strictly (`:5271-5296`), and a read error is a plain failure (`:5292`); the write is `spoolman_api.update_spool(sid, payload)` (`:5415`), and a failure is final (`:5427-5431`).
  - Smart Load's unloaded residents: `ejections` (`:5439-5466`).
  - A stored spool a Swap took out: `displaced` (`:5472-5503`).
  - The answer is "Undo could not put back …", and the record is gone (`:5595-5601`).
- **The question.** `undo_confirm_answer` (`:5151-5195`) and `_undo_current_heads` (`:5113-5136`) read `get_spool` for each spool. A deleted spool (Spoolman's 404 body, a dict with no id) counts as unreadable, so the question refuses with "Couldn't read #1 from Spoolman…" (`:5161-5169`).
- **The records.** `_push_undo` (`:1706`) is called from the move engine at `:2801` (a Smart Load that only unloaded) and `:3260` (every move). A chained auto-deploy's records are folded into the parent record (`:3348-3358`). The record's keys are listed at `:2653`.
- **The route and the page.** The route is `api_undo` (`routes_locations.py:1082-1129`; it asks `undo_confirm_answer` again before `perform_undo`, `:1126`). The page is `triggerUndo` (`inv_cmd.js:4547-4586`), which shows a failed answer's `msg` for 7 s. The heartbeat's `undo_available` (`routes_state_pulse.py:255`) keeps the Undo tile lit.
- **The write canary.** `tests/test_spoolman_write_sites.py:380`: `perform_undo` → `update_spool`, 3 calls. `:400-401`: `_move_write` and `_undo_filed`.

### 69.3: a park's Undo in an outage
- **The read.** `_undo_guard_read` (`logic.py:4733-4749`) calls `spoolman_api.get_spool_answer` (`spoolman_api.py:203-226`, `timeout=3`), where `(None, False)` means no answer. Everything that sorts a spool reads through it:
  - `_undo_guard_kind` (`:4768`);
  - `_undo_guard` (`:4782`, the question);
  - `_undo_filed_kind` / `_undo_filed_guard` (`:4818`, `:4829`);
  - `_undo_filed` (`:4925`);
  - `_undo_hold_parked` (`:5002`, `:5029`);
  - the park's loop in `perform_undo` (`:5364-5377`).
- **Every spool is read at least twice on the Yes.** The route asks `undo_confirm_answer` again (`routes_locations.py:1126`), then `perform_undo` reads each spool again. In an outage the cost lands on whichever runs first.
- **A refused connection fails at once.** The ~3 s per spool comes from a hung Spoolman or an unreachable NAS.
- **The precedent.** `logic.get_live_spools_data` (`:7379`, docstring `:7390-7398`) stops a buffer refresh at the first unanswered read.
- **The page** gives an Undo 120 s (`UNDO_TIMEOUT_MS`, `inv_cmd.js:4526`).
- **The existing outage tests.** `test_audit_undo_58.py:364-393` (an outage at the question and at the Yes), `:608-616` (`test_an_outage_mid_batch_is_said_once_too`), and `_during_the_undo` (`:496`).

### 69.4: Return and the Unknown list
- **The plan.** `_return_plan` (`routes_bindings.py:742-869`) reads `src = _u(extra.get('physical_source'))` (`:765`) and puts it in `recorded` (`:770`). Locations.json has no `UNKNOWN` row (dev's has none), so `:819-821` says "#57 came from UNKNOWN, which isn't in the location list any more". It then goes on to the head's feed slots (`:825`).
- **The chosen slot.** `_return_choice` (`:872-895`) carries the same `recorded`.
- **Where the words show.** The note reaches the Return confirm (`inv_quickswap.js:1376-1377`) and the Activity Log (`routes_bindings.py:1188-1194`, `:1234-1235`).
- **Already fixed by Group 58:** new trails (`logic._ghost_trail_from`, `:1248-1275`) and the eject (`logic._eject_destination`, `:4236-4239`).
- **Not fixed:** `spoolman_api._build_location_match` (`:2531-2538`) still makes such a spool a ghost in the Unknown list.
- **The tests' home.** `test_audit_lost_spools_58.py::test_a_trail_already_written_is_no_home_either` (`:351`).

### 69.5: the audit panel
- **(a) The notice.** `window.auditPanelNotice` (`inv_cmd.js:1840-1849`) fills `#fcc-audit-panel-notice` (markup `:2082-2084`), which sits above `#fcc-audit-panel-scroll` (`:2090`). The panel keeps its height, so the notice takes room from the scrolling part. That part's `ResizeObserver` runs only `_fitDock` (`:2127-2132`). `_tileClear` (`:2273-2281`) runs only from `_keyArrow` (`:2342`) and from `_tileFocused` (`:2289-2293`, keyboard focus only). The scroller is `_scroller` (`:2261-2266`).
- **(b) The picker.** `onPrintClick` (`duplicate_picker.js:178-197`) calls `cleanup()` and then `showToast` (`:188-191`). Toasts sit at z 11000, under the panel (standard tier, 20000).
  - `auditPanelNotice` hands its words to the report window when the panel is hidden, and that window ignores them unless it is open (`:2819-2827`).
  - The tests' home is `test_audit_no_label_58_js.py` (the hermetic `live` page). `:948` is `test_every_tile_the_arrows_reach_is_in_view`, and `test_audit_stacking_58_js.py` covers the picker over the panel.

### 69.6: the three calls
- **(a) Labels outside an audit.**
  - `routes_scan._verify_spool_label` (`:1182-1222`) treats only an explicit False as "already". A flagged status (True) is written False at `:1211`. It is called outside an audit from the spool branch (`:1464`). In an audit, `_audit_label_check` (`:1225-1258`) confirms only a missing status. The filament side, a `FIL:` scan (`:1520-1537`), has the same shape.
  - Flags come from `set_flag` (`routes_print_queue.py:171-215`), from `flag_spool_labels` (`:217-253`: a Brand, Type or colour-name edit, Group 23.3) and from the audit's Needs a label. Mark Printed (`:118-169`) clears one.
  - The help calls the scan the Backlog's confirm step (`help_texts.js:229`, `:242-243`).
  - The page shows no toast for a confirmed label.
  - Pinned today: `test_print_queue.py:82` (`test_identify_scan_barcode_clears_flag`) and `test_audit_no_label_58.py:309` (`test_outside_an_audit_a_label_read_still_clears_a_flag`).
- **(b) `LEG:`.**
  - `_is_label_read` (`routes_scan.py:1149-1153`) and `_audit_find_how` (`:1163-1179`).
  - `resolve_scan` (`logic.py:1066-1078`) resolves `LEG:` / `LEGACY:` / `OLD:` through `find_spools_by_legacy_id` (`spoolman_api.py:2719`, the filament's `external_id`): one spool means that spool, two or more open the picker.
  - The session's `found_by` (`logic.py:5673-5676`, set at `:6361`, the label kind by `routes_scan.py:1237`) becomes `label_read` on the panel's rows (`routes_state_pulse.py:106`).
  - The page's words: `_labelWords` (`inv_cmd.js:1323-1329`) and `_stripLabel` (`:1490-1497`).
- **(c) Low stock.** `stock_report.in_stock` (`:187-193`) reads `archived` and grams only. It is used by:
  - `stock_of` (`:196`);
  - `_members` (`:404-422`, the one rule for the list and the count);
  - `low_out_count` (`:425`);
  - `glance` (`:449`, the heartbeat's count, from the tick's non-archived list, whose spools carry `location`);
  - `_crossing` (`:783-845`, the warning).

### Prod facts (read-only, not blocking)
Dev's Spoolman (read on 2026-11-16, a copy of prod as of 2026-11-13) has 301 spools, archived ones included. None of them is at Unknown, none has an `UNKNOWN` trail, and none carries an audit note. So 69.4 may have no spool to act on at release. Whether prod has any since then needs one read, never a write: `GET http://192.168.1.29:7912/api/v1/spool?allow_archived=true`, then count `location == "UNKNOWN"` and `extra.physical_source` == `"\"UNKNOWN\""`. Prod reads weren't authorised for this file. Nothing in the build depends on the answer.

## Design, by member

### 69.1: archive lost spools in one step
- **The server.** A new `POST /api/unknown/archive` in routes_locations.py (it owns the Unknown list and the spool deletes), with its work in `logic.archive_lost_spools(ids)`. A request with no ids is refused with a 400 before anything is read. It is refused while an audit runs or a bulk move is armed, with the words `/api/undo` uses.
- **Each spool:**
  - It is read strictly (`get_spool_answer`). A deleted spool is named "no longer in Spoolman". A spool that can't be read is not written and is named once, in one sentence.
  - Only a spool whose own location is still `UNKNOWN`, that isn't archived and isn't in `state.GLOBAL_BUFFER`, is written. Anything else is left as it is, with why: "it turned up: FCC has it at SHELF-2", "in the scan buffer", "already archived".
  - A loaded spool shown at Unknown through an old trail is never written. Its own location is a head, and 69.4 also stops listing it.
  - The write is `update_spool(sid, {'archived': True})`. A write reported failed is read again, and counts as done when the record is archived and still at Unknown, as `_move_write` does for moves. A refused write gets an ERROR line with `spoolman_api.LAST_SPOOLMAN_ERROR`, and each reason is said once.
- **The answer** is `{success, archived, stayed: [{id, why}], failed: [{id, why}], msg}`. `msg` names up to three spools and counts past that (`_undo_names`' rule), for example: "Archived #57, #58 and #60 at Unknown, their notes kept."
- **The log.** One INFO summary line, escaped, beside `update_spool`'s own 📦 line per spool. The audit's park also writes a line per spool, so this follows its precedent.
- **The page.** In the Unknown view only, `renderList` draws a "📦 Archive lost spools…" button above the cards. It opens a `mountOverlay` window at the standard tier, with `host` set to `#manageModal` (it closes with the window) and `trapTab`.
  - Its rows come from the strict read the view already makes, keeping only `!is_ghost` rows whose own location is Unknown. Each row is a colour tile (`fccSpoolTileHtml`): the swatch, the name, the grams and "❓ Lost: LR-MDB-1 slot 2, on 2026-11-01" (`auditLostWords`).
  - Each row has a tick, and none is ticked when the window opens. There is a Select all, and "📦 Archive N" stays disabled at 0.
  - The keyboard idiom applies: arrows move `.kb-active`, a person's Space ticks (never inside a scan: `scanIsArriving`, `mouseCouldReach`), Enter on Archive opens the question (`personMayPress`, `enterIsAScan`), and Escape closes only the top window.
  - Its shortcuts are registered with `window.registerShortcut`.
- **The question** goes through `window.confirmActivePrint`, with one `tiles: true` section that lists every ticked spool.
  - Title: "Archive 3 spools at Unknown?"
  - Words: "They stay at Unknown, archived, with their notes. Low stock stops counting them. To bring one back, open it and untick Archived."
  - Its yes is "Archive them" / "Archive it". It opens on Cancel, as a hard-to-undo yes must (standing order), and passes `armAfterMs` so a double click can't answer it.
  - The answer's `msg` is toasted (4 s for a success, 7 s with a warning), and the view redraws from its next read.
- **Help.** The window gets a `registerHelp` entry and draws its ? with `fccCornerHelpHtml`. The location window's entry gets a section `when` the button shows. The help uses made-up examples.

### 69.2: ordinary Undo keeps what it couldn't put back
- **The pop stays,** because a second press must not run the same record at the same time. At the end, a copy holding only the spools that weren't put back, for a reason that says nothing about them, goes back in the record's own place (`stack_place`) with the same id. This is the park's rule, extended to an ordinary record's other keys: `moves` / `extras` / `labels`, `ejections` / `ejection_extras` / `ejection_released`, `displaced`, `released` and `buffered`, each filtered to the spools still waiting.
- **What waits for a retry:**
  - a spool that can't be read (no answer, or a 5xx, through `get_spool_answer`);
  - a one-spool head, or a slot, that can't be read;
  - a write that failed and can't be shown to have landed (`_move_write` reads it back);
  - a head or slot held by a spool of the same record that is itself waiting. For example, Smart Load's incoming spool failed to go back, so the resident can't go back onto the head yet. Or a Swap's incoming spool still sits in the slot of the spool it took out. Those wait together, in the record's order.
- **What is final.** A head or slot held by a spool that isn't in this record. It is left out of the copy, with an ERROR line as today, so it doesn't bury older records.
- **A deleted spool** is dropped and named ("#57 is no longer in Spoolman"), in the question too: `_undo_current_heads` reads with `get_spool_answer` and sorts deleted spools apart from unreadable ones.
- **The words.** "Undo could not put back #57 (could not be read from Spoolman). Press Undo Last Move again to try it again." The answer carries `retry` beside them. One helper builds this for the park's answer and the ordinary one, so the two can't drift apart.
- **`origin: 'buffer'`** puts a restored spool back at the top of the scan buffer only once its restore lands, on the first try or a retry. `unbuffered` lists only restored spools, as today.
- **The page** needs no change.

### 69.3: an outage costs two reads, not one per spool
- **One counter per request**, kept by the Undo read helper (`_undo_guard_read`, or a thin wrapper it shares with the ordinary path after 69.2). After two reads in a row that get no answer (`get_spool_answer`'s `(None, False)`), the rest count as unreadable without a read.
- **An answer resets the count to zero.** A 5xx or a body that isn't JSON is an answer: a broken record mustn't stop the reads of the spools after it, the precedent in `get_live_spools_data`.
- **The same counter covers everything in the request:** `_undo_guard` for the question, the parked and the filed groups, `_undo_hold_parked`, and after 69.2 the ordinary question and restore loop.
- **The answers' words stay exactly as they are** ("Couldn't read 6 spools from Spoolman…", "Undo could not put back 6 spools (could not be read from Spoolman). Press Undo Last Move again…"), and every spool not read stays on the retry copy.

### 69.4: Unknown is never a trail
- **One rule,** for example `locations_db.is_lost_trail(value)`: `UNKNOWN`, in any case, with or without quotes or spaces, is no trail. It is read where `_eject_destination` reads it today, and also by:
  - `_return_plan` and `_return_choice`, so `src` is `''`, `recorded.box` is None, and the words are "#57 has no recorded slot";
  - `_build_location_match`, so a trail of `UNKNOWN` never makes a ghost, which `get_spools_at_location_detailed` and `bucket_spools_by_location` both follow.
- **Nothing is written.** The stale trail is replaced at the spool's next move, as it is today.

### 69.5: the panel says it, and keeps the keyboard's tile in view
- **(a)** In the scrolling part's `ResizeObserver` callback (`inv_cmd.js:2129-2131`), call `_fitDock()` first. Then, when the focused element is a `.fcc-audit-tile` or `.fcc-audit-tile-tag` inside the panel with `:focus-visible`, call `_tileClear(_cellOf(el))`. That covers the notice, the note, the tally, a window resize and a Text size change. A tile focused by a mouse isn't moved, as in `_tileFocused`.
- **(b)** In `onPrintClick`, after the toast, also put the toast's own words on the notice line during an audit (`state.auditActive && window.auditPanelNotice`). The next good scan clears it, as it does a refusal. With the panel hidden, the toast is not covered, and `auditPanelNotice` passes to a report window only when one is open.

### 69.6: by Derek's answers
- **(a)** For (a): one toast and one log line when a scan clears a flag. For (b): `_verify_spool_label` gets the audit's rule. For (c): the page sends `label_confirm: true` with a scan while `#backlogModal` is shown, and the server clears a flag only then; elsewhere it answers a `warning` that the page toasts for 7 s.
  - Under (b) or (c), update the print-queue and label-backlog help lines and the two pins above, on purpose.
  - Claude's call: the `FIL:` scan follows the same answer.
- **(b)** For (c): a third find kind, `AUDIT_FOUND_BY_OLD_LABEL`, set by the route for a `LEG:` / `LEGACY:` / `OLD:` scanner read that resolves to one spool. `_audit_find_how` words it "by its old label". The panel row gets `old_label` beside `label_read`. `_stripLabel` and `_labelWords` gain those words. Nothing is written.
- **(c)** For (b): `in_stock` also requires that the spool's own location isn't `UNKNOWN`. That one rule changes the list, the title-bar count and the warning together. A Low or Out row gets `lost` (a count and grams) and inv_stock.js draws "+ 1 lost at ❓ Unknown (600 g)". CLAUDE.md's stock_report paragraph changes with it.

## Tests

Prove each new pin RED on `3388c7d` first (the project's rule: a pin that passes on the old code proves nothing).

- **69.1**
  - **Backend, offline:** a new `tests/test_unknown_archive_69.py`, through the real route and the real `update_spool` on `tests/spoolman_extra_fake.SpoolmanHTTPFake`. It checks:
    - a ticked spool at Unknown is archived and stays at Unknown, with `fcc_pre_audit_location` intact;
    - a spool that turned up, one in the scan buffer, one already archived and a deleted one are each left alone and named;
    - an unreadable spool (`down`) writes nothing;
    - a write that times out but landed counts;
    - a refused write gets one escaped ERROR line;
    - the summary line is escaped;
    - the route refuses during an audit or an armed bulk move, and refuses no ids with a 400;
    - a loaded spool with an old `UNKNOWN` trail is never written.
  - **Registries:**
    - the new write site in `tests/test_spoolman_write_sites.py`'s `WRITE_SITES`, with its anchor (`archive_lost_spools`) in a new row of CLAUDE.md's "Spool / Filament write surfaces" table;
    - the route in `tests/test_route_table_pin.py`, with app.py's re-export;
    - a new JS module, if one is made, loaded once in the page's order (`tests/test_load_order_canary_js.py`).
  - **Page, hermetic** (the `live` harness of `test_audit_no_label_58_js.py`, or a small sibling): the button shows in the Unknown view only; no tick at open; Select all; the question lists every ticked spool, opens on Cancel and ignores a double click; Escape closes only the top window; a scan goes on to the scan path and ticks nothing; the window closes with `#manageModal`; Tab stays inside it.
  - **E2E:** one run on the real dashboard with a `throwaway_spool` parked at Unknown, at 1600×1300 and at phone width.
  - **Guards:** `tests/test_contrast_guard.py` (the window and its question), `tests/test_text_size_floor.py` / `test_text_size_guard.py` (named sizes only), and `tests/test_help_texts_55.py` (the new entry and its ?).
- **69.2**
  - **Backend, offline:** in `test_undo_last_move_41_4.py` (the real engine over `move_engine_harness`) and in the "Ordinary Undo" block of `test_audit_undo_58.py` (`SpoolmanHTTPFake`). It checks:
    - a restore whose write fails and didn't land leaves a copy holding only that spool, with the same id and under a newer move, and the next Undo offers exactly it;
    - a write that timed out but landed counts and isn't offered again;
    - a head held by another spool is final and isn't in the copy;
    - Smart Load's incoming spool and its resident wait together, and come back in order on the retry;
    - a Swap's taken-out spool waits for the incoming spool;
    - a deleted spool is dropped and named, at the question and at the Yes;
    - `origin: 'buffer'` puts a spool back into the buffer only once it has landed.
  - **Pins changed on purpose:** `test_an_ordinary_undo_with_a_deleted_spool_still_refuses`, and `WRITE_SITES`' `perform_undo` counts (`update_spool` down, `_move_write` up). The write-surface table's `perform_undo` row is reworded with its anchor kept.
- **69.3**
  - **Backend, offline,** in `test_audit_undo_58.py`, counting the fake's spool GETs. It checks:
    - with Spoolman down at the question, a 6-spool park reads at most 2 spools, and the message is word for word as today;
    - an outage mid-batch (`_during_the_undo`) also reads at most 2, and all 6 stay on the retry copy;
    - one unanswered read followed by an answer doesn't trip the cutoff (`test_a_spool_read_blip_mid_batch_keeps_only_that_spool` stays green);
    - a 5xx doesn't count toward it;
    - the filed group shares the counter.
  - After 69.2, the same checks on an ordinary record.
- **69.4**
  - **Backend, offline,** beside `test_a_trail_already_written_is_no_home_either` in `test_audit_lost_spools_58.py`, on the trail spellings that test already uses:
    - a Return dry run of a spool on XL-1 with an `UNKNOWN` trail never names Unknown, and `recorded.box` is None;
    - with one free feed slot, the Return is one tap;
    - the Unknown list doesn't show the spool;
    - a spool filed at Unknown with no trail is still listed.
- **69.5**
  - **Hermetic page** (`live`):
    - **(a)** with the keyboard on the bottom-most tile still in view, a refusal notice keeps that tile's whole cell and ring inside the scrolling part; a tile focused by a mouse doesn't move.
    - **(b)** during an audit, the picker's 🖨️ puts "Added Spool #57 to Print Queue" ("Label already in queue" the second time) on the panel's notice line.
  - The contrast guard already scores the notice.
- **69.6,** by his answers:
  - (a) the label rule over `SpoolmanHTTPFake`, plus the page's `label_confirm`, plus the help lines (`test_help_texts_55.py`);
  - (b) the find words, with `test_audit_no_label_58.py`'s "writes nothing" pin;
  - (c) `test_low_stock_glance_57.py`'s list-equals-count proof on fixtures with a spool at Unknown, plus `test_low_stock_warning.py`, plus the row's words in `test_low_stock_panel.py`.
- **Standing orders that apply** (CLAUDE.md):
  - readable contrast in everything new (the contrast guard);
  - named text sizes only;
  - the keyboard idiom and scanner-safe keys (`enterIsAScan`, `scanIsArriving`, `personMayPress`, `mouseCouldReach`);
  - every overlay through `mountOverlay`, with `host` and `trapTab`;
  - a hard-to-undo yes opens on its safe answer;
  - the write-surface table and `tests/test_spoolman_write_sites.py` for every new or changed Spoolman write;
  - Activity Log text escaped (`html.escape(..., quote=False)`, `logic._audit_esc`);
  - the toolhead-type one-list canary (no head Type string in new JS);
  - the load-order canary for any new module;
  - no setup's own names in what a user reads: help and examples use SHELF-1 and #42, while text built from the user's own data stays as it is.
- **The full run before merging** (frontend changes), after one review pass. Use the checklist's lenses "a scanner is a keyboard", "a double click's second press", "stacked overlays", "honest reads and writes" and "ordering and staleness" (`docs/agent_docs/review-checklist.md`).

## Done when

- A lost spool that is really gone can be archived from the Unknown view in one question, staying at Unknown with its note.
- Undo Last Move never loses the spools it couldn't put back, never sticks on a deleted spool, and answers in seconds in a Spoolman outage.
- Return and the Unknown list never treat Unknown as a home.
- The audit panel keeps the keyboard's tile in view and says what the picker's 🖨️ did.
- Derek's three answers are built, and the help text and CLAUDE.md say what the code does.

## Risks

- Every move's Undo shares `perform_undo`, so 69.2's change reaches every door. Keep the park's code path as it is, and run both Undo test families.
- A retry copy that can never succeed would bury older records. Only reasons that say nothing about the spool go into the copy, and a deleted spool is dropped.
- 69.1 archives in bulk. Only spools still filed at Unknown qualify, every spool is read right before its write, and the question opens on Cancel.
