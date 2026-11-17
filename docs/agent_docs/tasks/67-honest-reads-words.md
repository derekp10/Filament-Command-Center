# Group 67: 🧾 Honest Reads & Words

**Branch name (when started):** `feature/group-67-honest-reads-words`
**Estimated effort:** LARGE (~17–25 h, 2–3 sessions). The refresh guessed MEDIUM (~8–12 h). Grounding found Spoolman's error body read as a record by about 35 callers, not ten, and about 50 unescaped Activity Log lines. 67.1 ~5–7 h · 67.2 ~3–4.5 h · 67.3 ~2.5–3.5 h · 67.4 ~2–3 h · 67.5 ~2–3 h · 67.6 ~0.5–1 h · 67.7 ~2–3 h. These ranges already allow for the usual ~30% overrun. A review round and the full browser sweep (~70 min) come on top.
**Risk:** **MEDIUM.** 67.1 changes what `get_spool` / `get_filament` hand back to about 35 callers, the move engine among them. The change only goes the safe way (an error body becomes "couldn't read"), but 71 test files patch `get_spool`. 67.2 makes Delete this filament also delete the filament's archived spools, which its warning has always counted. 67.3 makes a filament or vendor save wait up to 15 s instead of 2 s. No prod data is touched.

> **Status: TODO, filed 2026-11-16** (/refresh-groups; Derek approved the grouping the same day: "otherwise this seems fine").
> **Place in the recommended order:** step 4, together with 66 and 68. The order is 62 → 63 → 64 and 65 → 66, 67, 68. Whatever the order, 68.3 (one line in `update.sh`) goes in before the next release. Group 70.1 (Send to P-Touch CSV drops a label) has the same root as 67.1 and is built after it.
> **Starts:** ready. Derek has one small call, D1 (a startup log line). It has a default, so nothing waits on him. No picture is needed: the only new thing on screen is a "couldn't read" line in the filament window, in Group 52's existing notice style.
> **Grounded on `dev` @ `3388c7d` (2026-11-16):** every member is still live, and none is fixed yet. The dev probes were read-only GETs. The build re-checks each item when it starts (the refresh's call).
> Code anchors were read on `dev` @ `3388c7d` (2026-11-16). Line numbers drift, so re-grep before editing.

## Items covered (quoted from `Feature-Buglist.md`)

| # | Buglist item | Direction |
|---|---|---|
| **67.1** 🟠 | *"🟠 Spoolman's error body is still read as a record by most callers of `get_filament` and `get_spool` … `spoolman_api.get_filament` hands back Spoolman's parsed body whatever the status, so a 404's `{"message": "No filament with ID 9 found."}` or a 500's `{"message": "database is locked"}` is a truthy "filament". … Still reading a body as a record: `labels_csv.api_print_batch_csv`, `print_deduct.api_backfill_spool_weights`, `routes_inventory.api_get_filament`, `routes_locations.api_delete_filament` (its label snapshot) and `api_filament_details`, `routes_print_queue` mark_printed and set_flag, `routes_scan.api_update_filament` (the edit log's "before") and `api_identify_scan`'s filament-label branch; `get_spool` has the same root. Also: both `*_answer` helpers read any 4xx other than 404 that has a JSON body as "no such record" …, and `get_spool_answer`, unlike `get_filament_answer`, logs nothing of what came back … Fix: route each through the `*_answer` helper and its id check …, or make `get_filament` / `get_spool` return None for anything that isn't the record."* | **Live.** Every named caller is unchanged. On dev, `GET /api/filaments/999999` answers 200 `{"success": true, "data": {"message": "No filament with ID 999999 found."}}`. `/api/spools/<id>`, `/api/spool_details` and `/api/filament_details` answer the same way. Grounding found about 25 more `get_spool` callers that test only the answer's truth. Two of them guard writes. Fix at the root, then give the doors their words (C1). |
| **67.1** | Pre-refresh audit leftover `G54:54-spool-update-pre-read`: *"/api/spool/update keeps a 5xx body from its pre-read as `pre` (routes_inventory.py:1581 `get_spool(spool_id) or {}`), so _log_manual_weight_change logs a made-up 'before' and the low-stock check reads it."* | **Live**, at `:1581`. The root fix covers it. The weight line then says the "before" wasn't read. |
| **67.2** 🟠 | *"🟠 The filament window reads a failed spool list as "No spools found" … `/api/spools_by_filament` answers `[]` on any failure …, so with Spoolman not answering the window says "No spools found" with a count of 0, Delete this filament…'s warning loses its "will also delete N spools" line and its second step asks for the filament's number instead of CONFIRM (the server still deletes every spool it can list), and Merge's count reads 0 the same way … Group 52's rule: a read that fails says "couldn't read"."* | **Live.** It also reads through Spoolman's deprecated `filament_id` alias. Merge's filament list fails the same way ("No other filaments exist to merge into."). |
| **67.2** | *"🟡 Filament delete's cascade reads its spool list loosely … `get_spools_for_filament` … reads `GET /api/v1/spool` without `allow_archived` (archived children are neither listed nor deleted, and the filament delete then meets them) and answers `[]` on a refused or failed read, which reads as "no children" and goes straight to `delete_filament` … Read strictly (`filament.id` + `allow_archived=true`, every entry checked), refuse before any delete."* | **Live.** The same loose helper also feeds the label-flag route and the Prusament scan's temp prompt. One strict per-filament read serves all of them (C3). |
| **67.3** | Pre-refresh audit leftover `G47:47.3-slot-order-silent`: *"a refused slot-order save is silent. The route answers 400 with no log line (routes_bindings.py:65-67), and putSlotOrder ignores the status (inv_loc_mgr.js:812-829, `.then(() => {…})`), so the save looks applied until a reload."* | **Live.** The route logs and the page reads the answer (C7). |
| **67.3** | Pre-refresh audit leftover `G47:47.8-filament-vendor-2s-timeout`: *"update_filament and update_vendor PATCH with timeout=2 (spoolman_api.py:1578, :1783), so a slow Spoolman can show a false failure while the write lands."* | **Live**, at `:1578` and `:1783`. Use 15 s, and read a lost answer back once (C6). |
| **67.3** | From *"🟡 Smaller loose ends from Group 53"*: *"When `ensure_required_extras` can't register a required extra at boot, only hub.log says so: one Activity Log line naming it would explain the refusals that follow (Derek's call), and `ensure_extra_field` answers True when a label update was refused."* | **Live.** Derek's call D1. |
| **67.4** | *"📋 Other modules still put outside text into the Activity Log unescaped … about 20 lines in `logic.py` (e.g. force-unassign, …) log `{err}` = `spoolman_api.LAST_SPOOLMAN_ERROR` or `{why}` raw, and `routes_locations.py` / `routes_scan.py` / `routes_config_attrs.py` / `routes_inventory.py` log `{e}` / `{err}` raw. … `routes_inventory.py:74` logs a typed filament name raw (`'Silk <Gold>'` shows as 'Silk ') … `logic._move_write`'s WARNING line … puts the target and `LAST_SPOOLMAN_ERROR` in raw. Direction: move the escaper to `state` (e.g. `state.esc`) and widen the canary to every module."* Plus, from the "Words" item: *"the slot-label scan's refusal line puts the scanned target and the row's Type into the HTML Activity Log unescaped."* | **Live.** Group 56's own rule, run read-only over every module, finds 48 lines in 8 modules: logic.py 24, routes_scan.py 6, routes_config_attrs.py 5, routes_inventory.py 4, routes_locations.py 4, labels_csv.py 3, routes_bindings.py 1, and 1 false alarm in stock_report.py. About a dozen more lines carry typed names the rule can't see. |
| **67.5** | *"🟡 Words a person reads, around the writes Group 53 touched … The attributes manager's bulk add / remove toasts "Bulk-set failed: unknown" when every id fails …; remove a tag (HIDE) still hides the choice after a partial failure, while the failed filaments keep it invisibly; the Add wizard's create paths answer a refused create with generic words …; `/api/create_filament` answers raw `LAST_SPOOLMAN_ERROR` …; `update_extra_field_choices` answers a refused POST with Spoolman's raw body ("POST failed: …") and an exception with Python's raw text, and logs none of its refusals; the Prusament link scan's page-fetch failure (`{type: "prusament_url", status: "fetch_failed"}`) has no page branch, so it raises no toast …, and its refused backfill answers raw `str(e)`, logged unescaped; `spoolman_api.refusal_words` passes an exception text it doesn't recognise straight through (requests' InvalidURL names Spoolman's URL); … Merge Filament's mid-loop refusal toast doesn't name the spools that already moved."* | **Live**, every part. The slot-label line moves to 67.4. |
| **67.6** | *"🧯 A stray scan with no prefix reads locations.json unguarded … `logic.resolve_scan`'s legacy location fallback (step 8, "Len > 2") calls `locations_db.load_locations_list()` and reads `row['LocationID']` with no guard, so with the file unreadable or corrupt, or a row with no LocationID, any unprefixed text longer than two characters answers an HTML 500 instead of "Unknown Code". … Wanted: the same guard here."* | **Live**, at `logic.py:1164-1177`. The slot-label scan has the same read (C12). |
| **67.7** | *"🟡 Write-surface table rows for the create, delete and schema writes … `tests/test_spoolman_write_sites.py` registers them with no doc anchor because no row describes them: `api_create_filament`, `api_create_vendor`, `api_delete_spool`, `api_delete_filament`'s cascade, the two add_choice routes (`update_extra_field_choices`), the filament-attribute schema rebuild (`remove_choice` with `purge`, `sweep_unused`, the boot `ensure_filament_attributes_cleaned`: …), `api_spoolman_restore_field_order` and the startup field registration. Add a row each, then give the registry entries their anchors (and consider requiring anchors for them)."* | **Live.** Every one of those entries is `(…, None)`. Require the anchors (C11). |
| **67.7** | From *"🟡 Smaller loose ends from Group 53"*: *"No browser test covers the Location Manager title's "Move all →" button, Merge Filament or the attributes bulk add / remove (their routes are pinned offline). `scripts.html`'s comment above `inv_quickswap.js` ("hooks into state.printerMap") describes a load-time dependency that no longer exists."* | **Live.** Only route tests exist. The comment is still at `scripts.html:74-75`. |
| **67.7** | Pre-refresh audit leftover `G47:47.6-stale-pause-comments`: *"Comments still say a paused Activity Log swaps 'logs' for 'status' (routes_state_pulse.py:621-626, inv_core.js:3078-3082). That has been untrue since 2026-08-05 (inv_core.js:3098, :3460)."* | **Live.** Comments only. |

> **Gained since this file was written (2026-11-17, the refresh, from Groups 70, 72 and 73's task files):** 67.2 gains an item (the 📡 pill's `/api/logs` read has no catch); 67.6's item adds `locations_db.load_locations_list` answering `[]` for a file it can't open; 67.7's comments item adds a stale docstring (`logic._active_print_info_for_location`), a stale z-index comment (`fab_drag.js`) and two dead z-index rules (`global.css`). Read those items in `Feature-Buglist.md`.

## Decisions

### For Derek (one; it has a default, so nothing waits)

**D1. A line in the Activity Log when FCC can't register one of its fields at startup (67.3).**
- **What it is.** Spoolman refuses any save that carries an extra field it doesn't know. So each time FCC starts, it checks that Spoolman knows the ten fields FCC writes. Two examples: "Pre-Box Location (system)" on spools, which moves and Undo write, and "Excluded From Low Stock" on filaments. If Spoolman doesn't answer at that moment, or refuses, only FCC's server log (`hub.log`) says so.
- **Where.** FCC's start: `app.py`, which calls `spoolman_api.ensure_required_extras`.
- **A real example.** TrueNAS starts FCC a few seconds before Spoolman, right after a release that added a new field. From then on every move is refused with "Unknown extra field", and nothing on the dashboard says why.
- **Options.**
  - (a) One WARNING line in the Activity Log, only when something failed, naming each field: "⚠️ When FCC started, Spoolman didn't answer, so 2 of FCC's fields weren't registered: Pre-Box Location (system), Excluded From Low Stock. Spoolman refuses a save that carries one until FCC registers it at its next start."
  - (b) The same line, and it also names a field whose label Spoolman wouldn't rename. Saves still work in that case; only Spoolman's own label is out of date.
  - (c) As now: `hub.log` only.
- **Recommendation:** (a), with (b) in the same line. A normal start writes nothing.
- **If he doesn't answer:** built as recommended.
- **Why it's his:** the buglist item leaves it to him. The refresh didn't mark it ❓, so it can also be treated as a Claude's call.
- **Not offered:** registering again later on its own. A field stays registered in Spoolman once it is there, so a failure at startup matters only for a field that is new in that release.

### Claude's calls (offered for veto)

- **C1 (67.1) Fix the root, then the words.** `get_spool` / `get_filament` hand back the record only: a dict whose `id` is the one asked for, compared as numbers (`get_spool("0057")` asks Spoolman for 57). Anything else is None. That fixes every caller at once, the ~25 that test only the answer's truth included, and it fails safe: an error body becomes "couldn't read". The doors a person reads then go through the `*_answer` helpers, so they can say "not found" or "couldn't read" (the list is under Design). The buglist offered either fix; this is both.
- **C2 (67.1)** Only a 404 means "no such record". In both `*_answer` helpers, any other 4xx reads as "couldn't read": an auth proxy's 401 with a JSON body, or a 422. `get_spool_answer` gets the same single hub.log line `get_filament_answer` writes for an answer that isn't the record. It writes it at most once a minute per spool, because the buffer refresh reads every 5 s and a deleted spool in the buffer would otherwise fill the log.
- **C3 (67.2)** One strict per-filament spool read in `spoolman_api`. It uses `?filament.id=<id>` with `allow_archived` as asked, and checks that every entry is a spool record of that filament (Merge's `_merge_source_spools` rule). It answers `(spools, None)` or `(None, why)`. Merge, the delete cascade, `/api/spools_by_filament`, the weight backfill, the label flag and the Prusament temp prompt all read through it. After this, nothing uses the deprecated `filament_id` alias. Dev's 0.27.1 still honours that alias, and it answers every spool for a query name it doesn't know.
- **C4 (67.2) Delete this filament deletes its archived spools too.**
  - Its warning has always counted them: the page reads the list with `allow_archived=true`.
  - Today the server deletes only the spools in stock, then asks Spoolman to delete the filament. By the route's own docstring, Spoolman refuses to delete a filament that still has spools. So the archived ones keep the filament alive, and the delete is left half done. (Not checked on dev: it needs a write.)
  - After the fix, the warning names how many are archived: "3 spools, 2 of them archived".
  - The other way is to refuse while archived spools remain, which keeps their history. Say so if you prefer that.
- **C5 (67.2) A question that can't show its count doesn't open.** Delete this filament… and Merge say "Couldn't count #12's spools, so nothing was deleted (merged). Try again in a moment." (7 s). They never show a count of 0. The filament window keeps the rows it already showed, says "couldn't read" (Group 52's rule) and shows the count as "?".
- **C6 (67.3)** Filament and vendor writes wait 15 s, as a spool write does (a read timeout). A write whose answer was lost is read back once, inside `update_filament` / `update_vendor`. "Lost" means no answer in time, a dropped or cut-off connection, or a 200 that isn't JSON. If every field sent reads back as sent, the write counts as saved, and a WARNING says the answer was lost. Anything else stays a failure. One rule in the two helpers, instead of one in each of their ten callers.
- **C7 (67.3)** A refused slot-order save writes an Activity Log line. The page keeps the old order and says why (7 s). On the way, the Feeds save's own error toasts go from 5 s to 7 s (CLAUDE.md: 7 s or more for an error).
- **C8 (67.5)** Remove a tag (HIDE) hides nothing after a partial failure, just as it already hides nothing when every strip fails. The filaments that failed keep the tag, and it stays visible on them. The toast names them, and a second Remove strips only those, then hides the tag.
- **C9 (67.5)** `refusal_words` never puts Spoolman's address in front of a person. In text it doesn't recognise, any address becomes "Spoolman's address". The log line keeps the full text.
- **C10 (67.4)** One escaper: `state.esc` (`html.escape(str(x), quote=False)`). `print_deduct._esc` and `logic._audit_esc` call it, or are removed. The canary moves to its own file and reads every `inventory-hub/*.py`. It has a short allowlist, each entry with its reason, and a floor.
- **C11 (67.7)** Doc anchors become required for the create, delete and field-schema callers (widen `NEEDS_DOC_ANCHOR`). The helpers' own HTTP lines stay optional. A new write of that kind then can't land without a table row.
- **C12 (67.6)** The slot-label scan's identical unguarded read (`routes_scan.py:1575-1576`) gets the guard too. The same subscript in the move engine and in `/api/locations` is left alone (see "Found while grounding").

## Today's code (anchors, `dev` @ `3388c7d`)

**67.1, the error body read as a record**
- `spoolman_api.get_spool` `:196-200` and `get_filament` `:417-421`: `requests.get(...).json()` whatever the status, a bare `except` for no answer.
- `get_spool_answer` `:203-226`: no log line; a 4xx JSON body is returned as if it were the record.
- `get_filament_answer` `:229-270`: one WARNING line; a 4xx JSON body is returned the same way.
- The named callers:
  - The label CSV, `labels_csv.api_print_batch_csv` `:228`, spool `:297` and filament `:373`. A 404 or 5xx body becomes a label row of "Unknown … 0g" with a good QR, and Spoolman's message becomes one of its columns.
  - The weight backfill, `print_deduct.api_backfill_spool_weights` `:202`, at `:210`. A deleted filament answers 400 "No inheritable empty-spool weight…".
  - `routes_inventory.api_get_filament` `:217-226` and `api_get_spool` `:228-237`: dev answers 200 `success: true` with the 404 body.
  - `routes_locations.api_delete_filament` `:816`: the label snapshot at `:825`.
  - `api_spool_details` `:1258` and `api_filament_details` `:1270`: they pass Spoolman's body through.
  - `routes_print_queue.api_print_queue_mark_printed` `:119` (`:144`, `:155`) and `api_print_queue_set_flag` `:172` (`:191`, `:202`). A deleted record answers `msg: "HTTP 404: {…}"`, which the page toasts as is (`inv_backlog.js:346`, `inv_queue.js:68`).
  - `routes_scan.api_update_filament` `:165`: the "before" at `:214`. After a failed read every field logs "∅ → new".
  - `api_identify_scan` `:1262`, spool branch `:1461`. `resolve_scan` doesn't check an `ID:` / `SPL:` id (`logic.py:1081-1084`), so a deleted spool's 404 body passes `if data:`. The label check then tries a write, and a "#? [No Filament Data]" card joins the scan buffer where "Spool #57 not found" should be.
  - `api_identify_scan`, filament branch `:1515-1559`. A deleted filament's `FIL:` answers `display: "Unknown Filament"` and opens the filament window, and a label read tries a write.
- Callers the item doesn't name, with the same root. These two guard writes:
  - `routes_scan.api_prusament_apply_weights` `:40`, its record read `live` at `:58`. A 5xx body hides `archived` and reads the used weight as 0. That lets the L200 guard pass, the guard that keeps a correction from archiving a loaded spool or un-archiving an archived one. `update_spool`'s own read then acts on the real record.
  - `logic._perform_smart_move_impl` step 4 at `:2282` (`if not rec`). A 5xx body reads as a spool with no place, so a spool leaving a printing head isn't asked about. The step's own comment says an unreadable spool fails closed.
- About 20 more callers test only the answer's truth: `logic.py:941, 2324, 2737, 2817, 2988, 4308, 4580, 4648, 5391, 5452, 5493, 5520, 7417`, `print_deduct.py:2877, 3465`, `routes_bindings.py:1089`, `labels_csv.py:154`.
- About 15 others already check the id, for example `logic.py:496`, `print_deduct._spool_read` `:317-322`, `routes_state_pulse.py:84` and `spoolman_api.py:883`, `:1005`. None found on 2026-11-16 wants the 404 body as "deleted": those callers use `get_spool_answer`.
- `routes_scan.py:58` passes the 28.B3-style check with a body. So does `routes_locations.api_delete_spool` `:790`: its `if snapshot is None` at `:799` lets a 5xx body through, so the delete goes out on a blip, which is what that guard's own comment says it prevents.
- `/api/spool/update` (`routes_inventory.api_spool_update` `:1545`): `pre = spoolman_api.get_spool(spool_id) or {}` at `:1581` feeds `_direct_location_write`, `logic.release_box_after_direct_write` and `_log_manual_weight_change` `:989`. That function's `if not pre: return` (`:1006`) skips only a None, so a 5xx body logs "[0.0g ➔ …]" and `stock_report.check_after_weight_change` reads a "before" of 0 g. `pre_archived` is also False whenever `pre` is blank, so `auto_archived` can be claimed for a spool that was already archived.

**67.2, failed lists read as empty**
- `print_deduct.api_get_spools_by_filament` `:176-197`: `?filament_id=` at `:186`, `[]` on any failure at `:196-197`. Dev: `/api/spools_by_filament?id=999999` answers 200 `[]`.
- `spoolman_api.get_spools_for_filament` `:1664-1680`: no `allow_archived`; `[]` on a refused or failed read. Its callers:
  - `routes_locations.api_delete_filament` `:830`.
  - `routes_print_queue.api_flag_spool_labels` `:232`. A failed read flags nothing and answers `success: true`, and the page drops every failure (`inv_details.js:2895-2903`), so the reprint reminders are lost silently.
  - The Prusament scan's temp prompt, `routes_scan.py:1042`. A failed read reads as "no spool in use", so the prompt is offered.
- `print_deduct.api_backfill_spool_weights` `:232`: `?filament_id=…&allow_archived=true`, entries unchecked. It writes `spool_weight` to every listed spool that has none.
- The model, Merge's strict read: `routes_locations._merge_source_spools` `:918`, used by `api_merge_filament` `:1009`.
- The pages, in `inv_details.js`:
  - `openFilamentDetails` `:294`, its spools read at `:503`, and "No spools found." with a count of 0 at `:630-632`.
  - `_showMergeFilamentFlow` `:3160`: its count at `:3175-3182`, and a failed `/api/filaments` read becomes "No other filaments exist to merge into." at `:3207`.
  - Delete: the count at `:3471-3491` reads 0, so `_showDeleteFilamentFlow` `:3407` drops the cascade note and asks for the id, not CONFIRM.
- Pins of today's behaviour, to change on purpose:
  - `tests/test_delete_helpers.py`'s `test_returns_empty_on_http_failure` `:108` and `test_returns_empty_on_transport_exception` `:115`.
  - The cascade tests in `tests/test_l316_charact_record_deletes.py`, which patch `get_spools_for_filament`.

**67.3, silent saves**
- Slot order:
  - `routes_bindings.api_dryer_box_slot_order_put` `:57-74` answers 400 with no log line at `:65-67`.
  - `locations_db.set_dryer_box_slot_order` `:1905` refuses on a bad order, no row, a Type that isn't Dryer Box, or a refused save.
  - `inv_loc_mgr.js` `saveFeedsSection` `:770` calls `putSlotOrder` `:812-829`, whose `.then(() => {…})` never reads `r.ok` and whose `.catch(() => {})` swallows errors.
  - The Feeds save's own toasts last 5 s (`:846`, `:856`, `:863`).
- The 2 s writes:
  - `spoolman_api.update_filament` `:1533` PATCHes with `timeout=2` at `:1578`, and `update_vendor` `:1744` does the same at `:1783`.
  - `update_spool` uses 15 s (`:960`) plus `_after_unanswered_write` (`:984`).
  - The read-back models are `/api/spool/update`'s `_write_may_have_landed` / `_landed_as_sent` (`routes_inventory.py:1493`, `:1505`, used at `:1608`) and `stock_report.exclude_filament` / `include_again` (`:612-623`, `:644-650`).
  - Callers with no read-back: `routes_scan.py:216`, `:983` (`_or_raise`) and `:1536`; `routes_inventory.py:175` and `:1333`; `routes_print_queue.py:159` and `:206`; `routes_config_attrs.py:336` and `:486`.
- The startup registration:
  - `app.py:341-359`, under `__main__`, calls `spoolman_api.ensure_required_extras` `:1928-1938`, which drops each result.
  - `ensure_extra_field` `:1808-1873` writes only hub.log, and answers True after a refused label rename (`:1849-1854`).
  - `tests/test_spoolman_write_sites.py`'s `ALLOWED_DISCARDS` (`:325-332`) allows exactly those three dropped results. It goes stale, which turns the canary red, the moment 67.3 reads them.

**67.4, unescaped Activity Log lines**
- `print_deduct._esc` `:46` and a second copy, `logic._audit_esc` `:5718`.
- The canary is `tests/test_deduct_accuracy_56.py`'s `_unescaped_free_text` `:515`, applied to four modules at `:588-600`. Its escapes are `_esc`, `print_deduct._esc` and `html.escape`. Its outside-text names are `e`, `err`, `exc`, `why`, `filename` and `LAST_SPOOLMAN_ERROR`.
- Its rule, run read-only over every module on 2026-11-16 with `_audit_esc` counted as an escape:
  - `logic.py`: `_move_write`'s WARNING at `:1749`; the move refusals' `why` at `:2162-2703`; force-unassign at `:4687`; Undo's eject restore at `:5430-5502`; others.
  - `routes_scan.py` `:92, 348, 991, 1035, 1454, 1543`.
  - `routes_config_attrs.py` `:164, 673, 705, 938, 972`.
  - `routes_inventory.py` `:189, 811, 1089, 1390`.
  - `routes_locations.py` `:752, 809, 841, 862`.
  - `labels_csv.py` `:464, 488`.
  - `routes_bindings.py` `:1191`.
  - `stock_report.py:621` is a false alarm: its `why` is built from escaped parts.
- Lines the rule can't see, which carry typed or Spoolman names:
  - `routes_inventory.api_create_filament` `:75-78` (the buglist's `'Silk <Gold>'`) and `api_create_vendor` `:116`.
  - `_format_vendor_edit_log` `:126` and `routes_scan._format_filament_edit_log` `:108`, every value.
  - The slot-label scan's refusals at `routes_scan.py:1594-1597` and `:1615-1619` (the scanned target, the row's Type, the slot).
  - The attributes manager's lines at `routes_config_attrs.py:345`, `:389`, `:598`, `:608` and `:777` (typed tag names).
- No `why` carries FCC's own markup today (checked 2026-11-16), so escaping one breaks nothing.
- `/api/log_event` (`routes_state_pulse.py:179-184`) passes the page's text as it is. The page escapes its own text (CLAUDE.md), and that is outside this canary.

**67.5, refusals in words**
- Bulk add / remove:
  - `routes_config_attrs.api_filament_attributes_bulk_set` `:272-363`: each id's `msg` is raw `LAST_SPOOLMAN_ERROR` (`:341-342`), and there is no top-level `msg` (`:358-363`).
  - The page, `inv_config.js` `configAttrsBulkApply` `:559-585`, toasts "Bulk-set failed: unknown" (`:572`), and its partial toast only counts the errors.
- HIDE:
  - `api_filament_attributes_remove_choice` `:497` takes the HIDE path at `:590-619`, through `_strip_choice_from_carriers` `:474-494`.
  - It hides after a partial failure (`:603-619`). The page's 7 s toast names the ids that keep the tag (`inv_config.js:788-812`).
- Creates:
  - `api_create_inventory_wizard` `:839` answers "Failed to create new Filament in Spoolman." (`:913`) and "…every spool creation failed. Check Spoolman logs…" (`:972`). Each failed spool create logs only "A spool creation failed during bulk wizard execution." (`:962`).
  - `api_create_filament` (`:84-85`) and `api_create_vendor` (`:119-120`) answer `LAST_SPOOLMAN_ERROR` raw.
- `spoolman_api.update_extra_field_choices` `:2302-2335`:
  - It answers "POST failed: {post_r.text}" (`:2326`) and `str(e)` (`:2335`), and never logs a refusal.
  - It is called by `routes_config_attrs.api_filament_attributes_add_choice` `:366` and `routes_inventory.api_external_fields_add_choice` `:448-461`.
  - The page fires several add_choice requests and drops the answers (`inv_details.js:801-806`, `:2668`, `:2676`), so a refusal leaves no trace at all.
- Prusament (`routes_scan._handle_prusament_url_scan` `:849`):
  - A page-fetch failure answers `{type: "prusament_url", status: "fetch_failed"}` (`:921-926`), and `inv_cmd.js` has no branch for that type. It only has `prusament_matched` (`:3836`) and `prusament_new`. So no toast.
  - The refused backfill answers `str(e)` and logs `{e}` raw (`:988-996`).
- `spoolman_api.refusal_words` `:104-141` returns unrecognised text as it is (`:141`).
- Merge's mid-loop refusal:
  - The server answers "Some spools could not be re-parented; source filament left in place." with `reparented_spool_ids` and `spool_errors` (`routes_locations.py:1047-1054`).
  - The page toasts only "Merge failed: …" (`inv_details.js:3380`).

**67.6, a stray scan**
- `logic.resolve_scan` `:993`, step 8 at `:1164-1177`:
  - `locations_db.load_locations_list()` at `:1167` raises `LocationsCorruptError` on a corrupt file, by design (`locations_db.py:172-205`).
  - `row['LocationID'].upper()` at `:1168` raises on a row with no LocationID, or one holding a number.
- It is called from `api_identify_scan` (`routes_scan.py:1265`) and from `manage_contents` add (`:438`).
- The page's catch then says "Scan Error" (`inv_cmd.js:3890-3895`). During an audit it adds "FCC didn't answer", which isn't what happened.
- The model is the audit's guarded read: `logic.py:6223-6227`, with `AUDIT_LOCATIONS_UNREAD` at `:5667`.
- The same read on the next branch: the slot-label scan's map, `routes_scan.py:1575-1576`.

**67.7, paperwork**
- `tests/test_spoolman_write_sites.py`:
  - `WRITE_SITES` (`:354`) has an anchor of None for every site the item lists.
  - Check 3 needs anchors only for `NEEDS_DOC_ANCHOR = RECORD_UPDATES | RAISING_UPDATES` (`:263`).
  - CLAUDE.md's write-surface table has no row for any of these sites.
- Only route tests exist: `tests/test_filament_merge.py`, `tests/test_filament_attributes_bulk_api.py` (API, container) and `tests/test_bulk_move_session.py`.
- The page halves:
  - "Move all →": `inv_loc_mgr.js:76-120`, behind `window.FCC_BULK_MOVE_ENABLED`. `triggerBulkMove` (`:2027`) POSTs to `/api/bulk_move_session`.
  - Merge: `inv_details.js:3160-3400`.
  - The attributes bulk add / remove: `inv_config.js:559-585`.
- The stale comments: `templates/components/scripts.html:74-75`, `routes_state_pulse.py:621-626` and `inv_core.js:3078-3082`. The rule today is at `inv_core.js:3098` and `:3460`.

## Design

The models are CLAUDE.md's Group 52 rule ("A display read says 'couldn't read', never 'empty'"), the `get_filament_answer` / `get_spool_answer` contracts, Merge Filament's strict list read (Group 53.2), `/api/spool/update`'s read-back (Group 54 review R5-2) and the audit's guarded locations read.

**Build order:**
1. 67.1, the root.
2. 67.2, which shares 67.1's helpers and patterns.
3. 67.6.
4. 67.3.
5. 67.5.
6. 67.4, the escaping sweep. It goes after the others, which write their new log lines escaped from the start.
7. 67.7, last, so the table rows describe the final code.

If the size matters, 67.4 and 67.7 can be a second session: nothing else depends on them.

### 67.1 — never an error body as a record
- **The root (C1, C2).** `get_spool` / `get_filament` return the record or None. Then:
  - Only a 404 is "no such record" in the `*_answer` helpers.
  - `get_spool_answer` logs like `get_filament_answer` does, once a minute per spool at most.
  - Callers that test only the answer's truth now fail closed, the two write guards among them.
- **The doors, each in words.** A scan's door also writes an escaped WARNING line.
  - **An `ID:` / `SPL:` scan.** A 404 is today's 27.10 "Spool #57 not found". A 5xx or no answer says "Couldn't read spool #57 from Spoolman, so the scan did nothing. Scan it again in a moment." (`type: error`, 7 s). Neither writes a label or adds a buffer card.
  - **A `FIL:` scan**, the same way. It writes no label and opens no window.
  - **`/api/spools/<id>` and `/api/filaments/<id>`.** A 404 answers `{success: false, msg: "There is no spool #57 in Spoolman."}`. A failed read answers 502 with "Couldn't read spool #57 from Spoolman. Try again in a moment." The page's readers already check the id. Where they say "couldn't find", they show `msg` instead (`cancel_review.js:1513`).
  - **`/api/spool_details` and `/api/filament_details`.** They answer the record, or `{error: <words>}` with 404 or 502. Pages test `d.id`, so they keep working. Where they toast "Spool Not Found" or "Filament Data Missing!", they show `error` instead.
  - **Delete spool.** Spoolman's 404 alone answers "There is no spool #57 in Spoolman." (404). A 5xx or no answer refuses with "Couldn't read spool #57, so nothing was deleted." (502).
  - **Mark Printed and set_flag.** A 404 and a failed read each get their own words, and a refused write goes through `refusal_words`.
  - **The weight backfill.** A 404 and a failed read get words before anything else is read.
  - **The label CSV.** An error body is never a label row; the root makes it a skip, as a None is today. Saying so and keeping the queue is 70.1's job.
  - **`/api/update_filament`.** When the "before" couldn't be read, the edit log says "(before not read)" and never "∅ → new".
  - **`/api/spool/update`** (the G54 leftover). With no "before", the weight line says so. The low-stock check gets no made-up 0 g; it skips its crossing test. `auto_archived` comes from what the write did, not from a blank `pre`.
  - **The L200 apply-weights guard.** A spool it can't read refuses with "Couldn't read spool #57, so its weights weren't changed."
- **Left out:** `/api/print_label`, the `CMD:PRINT:` QR's door. 70.3 decides whether to queue it or retire it.
- **Patch semantics.** When a door moves from `get_spool` to `get_spool_answer`, any test that patches `get_spool` for it stops intercepting anything (71 test files patch `get_spool`). Move each patch with its door, or the test reads the configured Spoolman for real. A door that needs no "not found / couldn't read" split keeps `get_spool`: the root fix is enough there.

### 67.2 — a failed list says "couldn't read"
- **The helper (C3)** and its callers:
  - **`/api/spools_by_filament`** answers the bare list as now, or 502 `{read_ok: false, error: <words>}`.
  - **The delete cascade.**
    - It reads strictly, with `allow_archived=true`, before anything else, and a failed read answers 502 with nothing deleted.
    - Then it deletes the spools, archived ones too (C4), then the filament.
    - Its label snapshot goes through `get_filament_answer`: a 404 answers "There is no filament #12 in Spoolman." (404) before any delete.
  - **The backfill** reads through the helper, with no alias and every entry checked.
  - **The label flag** answers `success: false` with words when its read fails. The page now shows the failures it used to drop, at 7 s.
  - **The Prusament temp prompt** offers nothing when its read fails, and logs one INFO line.
- **The pages (C5).**
  - The filament window keeps its rows, shows the notice and a "?" count, and the next sync pulse redraws it.
  - Delete and Merge don't open without a count. Merge also refuses when the filament list can't be read.
  - The Delete flow's catch no longer falls back to the badge's count.
  - The notice uses Group 52's read-notice look and `var(--fcc-fs-small)`.

### 67.3 — saves that say what happened
- **Slot order (C7).**
  - The route writes an Activity Log line with words for each refusal. The LocationID comes from the URL, so it is escaped.
  - `putSlotOrder` reads `r.ok`. On a refusal it leaves `state.allLocations` alone, puts the reason in `#feeds-status`, and toasts for 7 s.
  - When FCC doesn't answer, it says "FCC didn't answer, so the slot order wasn't saved."
- **The timeouts (C6).**
  - Comparing what was sent with what reads back: `vendor_id` reads back as `vendor.id`; numbers match within a tolerance; text matches exactly; an extra sent as the delete sentinel reads back blank.
  - A field it can't compare means "can't tell", and the answer says so, the way `/api/spool/update`'s `may_have_saved` does.
  - `stock_report`'s own read-back stays, or folds into this.
- **The startup line (D1).**
  - `ensure_required_extras` reads each result and writes the one line.
  - `ensure_extra_field` tells its caller when a label rename was refused, and still answers True for "registered".
  - Remove the `ALLOWED_DISCARDS` entry in the same commit, because a stale allowance turns the canary red. Update `HOW_IT_FAILS`'s text too.

### 67.4 — one escaper, one canary over every module
- **The escaper.** `state.esc` (C10). It wraps the outside text in the 48 lines the rule finds and in the typed-name lines it can't see. Never escape FCC's own markup. Check each line.
- **The canary.** A new `tests/test_activity_log_escaped.py` takes the AST rule from `test_deduct_accuracy_56.py` and widens it:
  - It reads every module, non-recursively, as `test_no_direct_extra_patch.py` does.
  - Escapes: `state.esc`, `html.escape`, plus `_esc` / `_audit_esc` while they remain.
  - Names: `e`, `err`, `exc`, `why`, `filename`, `name`, `display`, `target`, `choice` and `label`, plus `.get('name' / 'material' / 'comment')` subscripts.
  - It has an `ALLOWED` list (site, count, why) and a floor of escapes it must see.
- **Group 56's test** then imports the rule, so it isn't written twice.
- **CLAUDE.md's paragraph "Activity Log messages are HTML"** is rewritten. Its last sentence names this follow-up.

### 67.5 — refusals in words
- **Bulk add / remove.** When nothing was processed, there is a top-level `msg`: "Couldn't change any of the 3 filaments: …". Each id's `msg` goes through `refusal_words`, and the raw text goes in the WARNING line. The page's partial toast names the filaments that failed.
- **HIDE (C8).**
- **Creates.**
  - `api_create_inventory_wizard` answers "Couldn't create the filament: <words>" or "The filament is saved, but no spool was created: <words>", from `refusal_words(LAST_SPOOLMAN_ERROR)`.
  - Each failed spool create logs its reason.
  - `/api/create_filament` and the `/api/vendors` POST answer in words, with the raw text in hub.log.
- **`update_extra_field_choices`.** Each refusal gets its own words and one escaped WARNING Activity Log line naming the field and the choice. The page's fire-and-forget callers leave a trace that way.
- **Prusament.**
  - A page branch for `prusament_url` with `status: fetch_failed`: a 7 s warning, "Couldn't read that spool's Prusament page, so nothing was changed. Check the connection and scan it again."
  - The refused backfill's answer goes into words, and its log line is escaped.
- **`refusal_words` (C9).**
- **Merge's toast** names the spools moved and the spools left, from `reparented_spool_ids` and `spool_errors`. Past three it counts them, as `logic._undo_names` does. It says that Merge again moves the rest.

### 67.6 — a stray scan never answers a 500
- **The guard in `resolve_scan`.**
  - Catch the read, whether `LocationsCorruptError` or any other exception.
  - Skip rows that aren't dicts or whose `LocationID` isn't text.
  - On a failed read, answer `{'type': 'error', 'msg': "Couldn't read the locations file, so FCC couldn't check that scan. Scan it again in a moment."}` with one escaped WARNING line. hub.log keeps the file's own error.
- **The slot-label scan (C12)** gets the same guard. It answers "Couldn't read the locations file, so nothing was moved."

### 67.7 — paperwork in code
- **Table rows.** One row each in CLAUDE.md's write-surface table:
  - `api_create_filament` / `api_create_vendor`.
  - `api_delete_spool`.
  - `api_delete_filament`'s cascade, as 67.2 leaves it.
  - The two add_choice routes, for `update_extra_field_choices`.
  - The filament-attribute schema rebuild: PURGE, `sweep_unused`, and the startup `ensure_filament_attributes_cleaned`, each a field DELETE, a field POST and `attr_migration.restore_extras`.
  - `api_spoolman_restore_field_order`.
  - The startup registration (`ensure_required_extras` / `ensure_extra_field`).
- **Anchors.** Then give those `WRITE_SITES` entries their anchors, and widen check 3 (C11).
- **Browser tests.** Prefer hermetic `isolated_page` tests that run the real modules with stubbed answers, as `tests/test_low_stock_glance_57_js.py` does: they run under `--offline` and touch no dev data.
  - **"Move all →"**, with `window.FCC_BULK_MOVE_ENABLED` true. The panel opens armed on that place, and `/api/bulk_move_session` is answered in the page, so dev's shared session never sees it.
  - **Merge**: the picker, MERGE, the toast, and 67.5's toast on a mid-loop refusal.
  - **The attributes bulk add / remove**, and 67.5's words.
- **Comments.**
  - `scripts.html:74-75`: say what holds today (nothing is read at load), or remove the comment.
  - `routes_state_pulse.py:621-626` and `inv_core.js:3078-3082`: a pause freezes the render, not the fetch.

## Tests

- **For every member:**
  - New tests fail on `dev` `3388c7d` (`git archive`), as `docs/agent_docs/review-checklist.md` asks.
  - Drive the real write functions over `tests/spoolman_extra_fake.SpoolmanHTTPFake`, never a mocked `update_spool`.
  - Extend the fake once, for the whole group:
    - Lift Group 53's per-path canned answers (`_Spoolman.canned` in `tests/test_filament_answer_53.py`) into it.
    - Filter the spool list by `filament.id`, as Spoolman does. Today the fake answers every spool.
    - Add a DELETE of a record.
    - Add a PATCH that lands and then raises `ReadTimeout`: a lost answer.
- **67.1:**
  - Each door with four answers: Spoolman's real 404 body (`{"message": "No spool with ID 57 found."}`, as dev's 0.27.1 answers), a 5xx (`{"message": "database is locked"}`), a 401 with a JSON body, and no answer.
  - An `ID:` scan of a deleted spool adds no buffer card and writes nothing.
  - The L200 guard and the move engine's step 4 refuse a 5xx body with nothing written. Drive step 4 through the real `perform_smart_move` on `tests/move_engine_harness`.
  - A label CSV never holds a row built from an error body.
  - `/api/spool/update`'s weight line when there is no "before".
  - `get_spool("0057")`.
  - The once-a-minute log line.
- **67.2:**
  - Each caller on the fake with `list_reads_fail` and with `down`: nothing deleted or written. A list holding another filament's spool is refused. Archived children are deleted.
  - The page halves in an `isolated_page` test: "couldn't read" and "?" in the filament window, both on a first read and on a refresh that keeps the rows; Delete and Merge don't open; Merge's filament list.
  - `tests/test_contrast_guard.py` for the notice. Score its parent, not the notice itself: `assert_contrast` reads descendants only.
  - `tests/test_text_size_floor.py`.
  - Change the two `[]` pins in `tests/test_delete_helpers.py` and the cascade pins in `tests/test_l316_charact_record_deletes.py` on purpose.
- **67.3:**
  - A lost PATCH that landed counts as saved, with a WARNING. One that didn't land stays failed. A refused PATCH is never read back. `vendor_id` against `vendor.id`. The delete sentinel.
  - Slot order: the route's escaped log line, and `putSlotOrder` in an `isolated_page` test (a 400 keeps the old order and says why for 7 s).
  - Startup: a failing field list writes one escaped line naming the fields, a normal start writes none, and `tests/test_spoolman_write_sites.py` is green once its `ALLOWED_DISCARDS` entry is gone.
- **67.4:**
  - The new canary is red on `3388c7d`, with a unit test of its own rule, like Group 56's `test_the_escape_canary_catches_raw_outside_text`.
  - One log line per module, driven with `Silk <Gold> & "Co"`, comes out escaped.
- **67.5:**
  - Each change gets a backend pin (its words, no address, the log lines) or an `isolated_page` pin: the bulk toasts, Merge's mid-loop toast, and the Prusament `fetch_failed` branch through processScan's answer handling.
  - `refusal_words` over requests' exception texts (`InvalidURL`, `ConnectionError`, `SSLError`): what it returns holds no address.
- **67.6:** `resolve_scan` gets an error answer, never a raise, when `load_locations_list` raises `LocationsCorruptError`, when a row has no LocationID, and when an id is a number. Through the Flask test client the route answers JSON. The slot-label scan likewise.
- **67.7:** check 3, widened, sees the new anchors. The three browser tests. Comments need no test.
- **Standing orders that apply:**
  - Activity Log escaping covers every new line, in 67.2, 67.3, 67.5 and 67.6.
  - The write-surface table and `tests/test_spoolman_write_sites.py` cover 67.2's cascade and backfill, 67.3's read-back and 67.5's add_choice logging.
  - Readable contrast and the named text sizes apply to 67.2's notice and 67.3's status line.
  - Error toasts last 7 s or more.
  - No setup's own names in words a person reads. A toast that names the person's own records is fine; an example is not.
  - No new key, so no new shortcut.
  - No new overlay. The delete question stays where it is; 62.8 moves it into `mountOverlay`.
  - The load-order canary covers any new code that runs as a page module loads.
  - The toolhead-type one-list canary: no head Type in new strings.
  - Module-qualified calls, and Python 3.9 syntax.
- **Runs:**
  - `--offline` while building, in the background (~20 min).
  - The full run before merging, because the frontend changes (~70 min).
  - The full run writes to dev (CLAUDE.md), so not while another chat runs one.

## Done when

- No caller reads Spoolman's error body as a record. Every door a person reads says "not found" or "couldn't read", whichever is true.
- No failed list reads as empty: the filament window, Delete, Merge, the cascade, the backfill, the label flag and the Prusament prompt all say "couldn't read".
- A refused slot order says so. A slow Spoolman no longer turns a landed filament or vendor save into a failure. A field FCC couldn't register at startup shows in the Activity Log (D1).
- Every Activity Log line escapes its outside text, and one canary over every module keeps it that way.
- Refusals read in words, with no Spoolman address.
- A stray scan never answers an HTML 500.
- The write-surface table names every write, and anchors are required. The three browser tests and the comments are done.

## Risks

- **67.1** changes what about 35 callers get back. It only goes the safe way, but a caller that wants the 404 body as "deleted" has to use an `*_answer` helper. None was found on 2026-11-16; check again in the build. 71 test files patch `get_spool`.
- **67.2** deletes archived spools along with their filament (C4).
- **67.3:** a hung Spoolman can hold a filament or vendor save for up to 15 s. Today it gives up after 2 s and reports a failure that may be false.
- **67.4:** escaping FCC's own markup by mistake. None was found; check each line.
- **The full sweep writes to dev.**

## Found while grounding (not in this group's items; for the refresh to file or fold in)

> **Filed 2026-11-16 by the refresh:** (1) joined 67.2's filament-window item, so it is this group's to build with 67.2; (2) and (3) joined 67.6's item, so build them with 67.6 (the same guard, and Group 52's "couldn't read"); (4) joined 71.2's item (Group 71).

1. **The Prusament scan's spool match reads the spool list loosely** (`routes_scan.py:899`, `get_all_spools`, which answers `[]` on a failure). With Spoolman not answering, scanning the QR of a Prusament spool you already own says "isn't in inventory yet" and opens the Add wizard to onboard it a second time. It fits 66 (the wizard's Prusament scans) or 67.2.
2. **A bare-number scan reads a Spoolman that didn't answer as "ID Not Found"** (`logic.py:1141-1162`).
3. **`/api/locations` and the move engine read `row['LocationID']` with no guard** (`routes_locations.py:68`, `logic.py:1991-1992`). One hand-edited row with no LocationID breaks the dashboard and every move.
4. **Merge's windows put Spoolman's names into HTML unescaped** (`inv_details.js:3229`, `:3328-3332`; the datalist at `:3214` escapes only quotes). The filament window's spool rows do the same with their place (`:540`). That breaks CLAUDE.md's rule "Spoolman's free text in a card is HTML text". It fits 71.2.
5. **No prod fact is needed for this group.** Every answer above comes from dev's code and read-only GETs to dev.
