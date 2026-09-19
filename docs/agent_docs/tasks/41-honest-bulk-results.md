# Group 41: 🧾 Honest Bulk Results

**Branch name (when started):** `feature/group-41-honest-bulk-results`
**Estimated effort:** MEDIUM, about 1–1.5 sessions (~8–12 h), once Derek has answered Q1 and Q3.
**Risk:** **MEDIUM.** Every change is on a destructive path: Eject All, location delete, Undo, and the bulk-move commit. It makes each path refuse more and report more. The hazards are a correct action now refused (a false block), and pinned wording or response shapes that tests assert.

> **Status: `TODO`.** Planned 2026-09-13 from Derek's D4 answer and the related buglist items
> ([open-decisions-2026-09-13.md](open-decisions-2026-09-13.md)). Nothing has been built yet.
> All code references were read on `dev` @ `be9f045`. Line numbers drift, so re-read before editing.
>
> ⛔ **Hard dependency:** `fix/core1-return-ejectall-guard` (`1fb5678` + `76398cb`, committed locally,
> not pushed or merged) refuses a blank location in `triggerEjectAll` and `clear_location`, the same
> two functions 41.1 and 41.2 rewrite. Merge it into `dev` first, then branch from `dev`.

---

## Read this first

- **Eject All is NOT being removed.** Derek: *"A case could be made for removing it."* Removal is undecided, so don't remove it or hide it beyond D4's block.
- **Anything that chains through a move or eject must run the REAL engine** ([[mocked engine hides chain bugs]]). Reuse the `FakeSpoolman` / `WireSpoolman` harness from `tests/test_active_print_chain_confirm.py` (Group 39 plans to extract it into `tests/move_engine_harness.py`; use that if it has landed).
- **Every new test must fail on the old code** (`git archive HEAD` into a scratch dir).
- **Group 37's invariant is binding:** *"A room-level clear/delete must never reach a live toolhead — but via an explicit guard, not the id-naming accident."* 41.1 and 41.3 build that explicit guard.
- **Container runtime is Python 3.9.** Update CLAUDE.md's "Spool / Filament write surfaces" table in the same commit as any change to `clear_location`, the location-delete cascade, or the unseat write.

---

## Buglist items covered

### Core

| # | Buglist item (title as filed) | Decision / direction |
|---|---|---|
| **41.1** | 🟠 **"'Eject all', location delete and Undo report success for work they didn't do."** (the D4 block) | *"Decided 2026-09-13 (Derek): block Eject All on Room and Printer views. On those views it moves nothing and points to Move all → instead. Derek: 'an eject all on a room would be catastrophic… I don't think I would ever want to blindly unassign filaments assigned to locations in a room to that scale.'"* Boxes, carts, shelves and toolheads keep Eject All, *"with honest per-spool results, a refusal when no location is open, and no sweeping of a printer's heads mid-print."* |
| **41.1** | 🟠 *Found while briefing the six open decisions*, item 3: **"Eject All on a Printer-row view unloads every head mid-print with no prompt."** | Fix direction as filed: *"skip head-loaded spools, as Bulk Move does."* D4's Printer-view block closes the user-facing door. 41.1 also adds that skip underneath. |
| **41.2** | Same Eject All item, part 1: **"Eject all (`clear_location`…) ignores every eject's result."** | *"Fix direction: branch on the real per-spool result; return `ejected` / `needs_confirm` / `failed` lists; toast failures at ≥ 7 s."* |
| **41.3** | Same item, part 2: **"Location delete… answers `success: true` when the cascade's unassign writes fail…"** | Same fix direction. |
| **41.4** | Same item, part 3: **"Undo (`perform_undo`) always answers `success: true`…; `triggerUndo` discards the response."** | Same fix direction. |
| **41.5** | 🟡 *Bulk-move tally and slot unseat can report success for rejected writes*, item 1: **the tally trusts a fail-open readback.** | Filed fix: *"always union `failures` into `failed`; read back with the strict reader and report the tally as unverified on an exception."* |
| **41.6** | Same item, item 2: **a rejected unseat still seats the incoming spool, so two spools claim one slot.** | Filed fix: *"record a failure and don't seat the incoming spool."* |
| **41.7** | Same item, item 3: **"Bulk Move's 'source is printing' confirm can never fire on real data."** | *"To decide: whether the confirm is dead code to remove, or should cover a real case."* → **Q3** below. |
| **41.8** | Derek's principle, under D4: **Room-only spool locations are hard to find.** | *"A spool whose location is only a Room is a pain to find ('assuming it's even still in the room and somehow didn't get a location update'). Bulk filament still in its purchase boxes is the tolerated exception."* Implication to check: *"the eject fallback sends a box/cart/shelf spool with no saved home UP to its Room's loose pile, which creates exactly these Room-only spools."* → **Q1** below. |

### Depended on, not re-planned

- 🟠 *Found while briefing the six open decisions*, item 2: **"A `CMD:EJECTALL` scan with no location open targets the Unassigned pile."** This is being fixed on **`fix/core1-return-ejectall-guard`**. This group assumes that refusal exists and doesn't re-plan it.

### Placed in Group 22, not here

- 🟡 *Found while briefing the six open decisions*, item 6: **the deduct side** (*"A cancelled print's review silently drops an uncharged head"*; *"A `no_spool` Review card never names a spool"*).
  - **Verdict: [Group 22](22-filabridge-phase2-detection-deduct-followups.md).**
  - **The review keeps only heads that resolved to a spool.** `_create_pending_cancel_review` stores just the rows `_resolve_usage_to_spools` returned (`print_deduct.py:1348`, record at `:1370-1380`). The confirm loop then commits the ledger on full success with no check against the computed usage (`:1561-1564`).
  - **The `no_spool` review names no spool.** `_confirm_no_spool_review` re-resolves against whatever is on the head at Apply time (`:1403-1450`), and the stored record carries no expected spool.
  - **Why Group 22:** these are the deduct engine and ledger functions Group 22's task file already owns (its 22.4 list names `_confirm_no_spool_review` and `deduct_cancelled_print`). Nothing in this group touches the deduct engine. The only thing the two share is the theme "say what really happened".
  - **But it must not wait behind Group 22's blocked item.** Group 22 is PARTIAL, and its only open item, 22.3(b), is blocked on data (`working-groups.md:116`). File this as an **unblocked 22.5**, built alongside [Group 39.4](39-confirm-on-every-door.md). D6 makes "a head emptied mid-print" a confirmed everyday action. Checked 2026-09-13:
    - A D6-confirmed move while PRINTING records no swap event, because swap snapshots are taken only on a resume (`print_monitor.py:421-438`).
    - **At completion**, a head left empty is not a "swap": `_is_sid_swap` needs a spool on both sides (`print_deduct.py:473-484`). So the deduct auto-applies, charges nobody for that head, and only logs the shortfall ("wasn't deducted", `:406`).
    - **At cancel**, the review is built from the spools still on the heads (`:1352-1366`), so the emptied head's grams vanish with no warning at all.
    - Filing it is a buglist and Group 22 task-file edit, not part of this group's build.

### Found while writing this plan (code-traced 2026-09-13, not reproduced, not yet in the buglist)

- 🟠 **Deleting a Dryer Box or a Room unassigns spools that are loaded on toolheads**, with no active-print check.
  - **Mechanism:**
    - The non-toolhead delete uses `get_spools_at_location` (`routes_locations.py:453`).
    - That reader also returns **ghosts**, spools whose `physical_source` names the box (`spoolman_api.py:1473-1479`, ids at `:1522-1523`).
    - It also returns **first-segment prefix matches** (`:1465-1468`).
    - Every returned id then gets `update_spool(sid, {"location": ""})` (`routes_locations.py:458`).
  - **Consequences:**
    - Deleting `LR-MDB-1` would take the spools deployed from it off XL-1…XL-3.
    - Deleting Room `LR` would do that for all five XL heads, and also empty every `LR-MDB-*` / `LR-SD-*` location, while those rows remain.
    - Each unassigned spool keeps a trail to the deleted box.
    - Deleting the Printer row `XL` would unassign the resident of every XL head. `Printer` is not in `TOOLHEAD_TYPES` (`locations_db.py:73`), so the delete takes the non-toolhead branch, and every XL-n spool is a first-segment match for `XL`.
  - **41.3 fixes this.** Derek may want to file it as its own standalone buglist line.

---

## Current behaviour (verified 2026-09-13)

### Eject All: where it can be triggered

- **The ☢️ DANGER ZONE EJECT ALL badge and its QR** render only inside `renderUnslotted` (`inv_loc_mgr.js:1169-1186`). That is reached only from the **grid** view (`renderGrid`, `:994`), which is used for a Dryer Box or MMU with `Max Spools` > 1 (`:172`), and only when a spool is unslotted.
- **The list view generates a `qr-eject-all-list` QR** (`:1125`) whose target element doesn't exist in any template (the comment at `:75-78` confirms). So on a **Room, Printer, toolhead, cart or shelf** view the only trigger is scanning a `CMD:EJECTALL` label:
  - the frontend intercept (`inv_cmd.js:1430`), or
  - the backend command (`logic.py:180`, handled at `inv_cmd.js:1498`).
- **Both paths act on whatever `#manage-loc-id` holds.**
- **"🔀 Move all →" is hidden on single-occupancy types, including `Printer`** (`inv_loc_mgr.js:81`, `:100`), because bulk move skips every loaded head.

### Eject All: what it does

- **`triggerEjectAll`** (`inv_loc_mgr.js:1662-1681`):
  - asks `promptSafety("Nuke all unslotted in <loc>?")`;
  - posts `clear_location` with no confirm flag;
  - reads only `skipped_slotted` and otherwise toasts "Cleared!".
- **`clear_location`** (`routes_scan.py:232-279`):
  - reads contents with the fail-open reader (`:233`), so an outage reads as "nothing here";
  - probes only the open location itself (`:237-246`), and `XL` is not a `printer_map` key (`logic.py:29-31`), so a Printer view never asks;
  - skips ghosts (`:251-252`) and slotted spools (`:254-264`);
  - calls `perform_smart_eject(…, confirm_active_print=True)` and appends the id **whatever the result** (`:256-257`);
  - answers `success: true` (`:279`).

### Eject All: what each view actually reaches

The matcher reaches a location's own spools and, for a Room, its whole subtree by first segment (`spoolman_api.py:1465-1468`). Real dev rows:

| Open view | Direct matches | What happens to them today |
|---|---|---|
| `LR` (Room) | Spools in `LR-MDB-1`, `LR-MDB-2`, `LR-SD-1`, `LR-SD-2` and on `LR` itself. Not `XL-n`, whose first segment is `XL`. | Slotted box spools are skipped. Unslotted drawer spools with no saved home go **up to `LR`** (`logic.py:1896-1900`). Loose `LR` spools answer `REQUIRE_CONFIRM`, which is ignored. "Cleared!" regardless. |
| `XL` (Printer, Max 0, toolheads `XL-1`…`XL-5`) | The resident of each of `XL-1`…`XL-5`, whose `container_slot` is empty after a toolhead move (`logic.py:739`) | Each is ejected with the print override: back to its `LR-MDB-1`/`LR-MDB-2` slot, or `REQUIRE_CONFIRM` (ignored). Each eject runs the Group 20.2 single-slot box detach (`logic.py:1776-1792`). **Mid-print, with no prompt.** |
| `CORE1` (Printer, Max 1, is its own `printer_map` key) | Its resident | Probed (it is a `printer_map` key), but the frontend never handles the `require_confirm` answer (I2-12), so it still toasts "Cleared!". |
| `XL-2` (Tool Head) | Its resident | Same as CORE1. |
| `CR-CT-2-R1` (cart row) | Its spools | Homeless ones go **up to `CR`**. |

### The Room fallback (Derek's principle)

- **An eject with no saved home** (`perform_smart_eject`, `logic.py:1890-1905`):
  - from a `printer_map` head → Unassigned, behind the "true unassign" prompt;
  - from anything else → `get_room_from_location` (`:1713-1735`), which walks `parent_id` to the top-level Room.
  - Two cases have no dash-derived Room, so they also get the unassign prompt: a dash-less id (a Room itself), and the pseudo-room prefixes `TST`/`TEST`/`PM`/`PJ` (`locations_db.py:600`). **PolyDryer spools (`PM-DB-n`) already get the prompt.**
- **Smart Load's resident with no saved home** goes to the printer's Room when the tree knows it, else Unassigned (`_known_room_of`, `logic.py:387-405`, used at `:647-653`). For example, XL-2 → `LR`. This was Derek's decision on 2026-09-12.

### Location delete

- **`DELETE /api/locations`** (`routes_locations.py:397-477`).
- **Toolhead branch** (`:409-447`):
  - the cascade collects errors (`logic.py:1924-2037`);
  - the row is removed and saved anyway (`:430-431`), and the route answers `success: true` (`:447`);
  - an active print answers 409 (`:428-429`).
- **Every other type** (`:449-477`):
  - fail-open, ghost- and prefix-matching contents (`:453`);
  - a location-only PATCH that leaves `container_slot` and `physical_source` behind (`:458`);
  - failures go to `hub.log` only (`:460-464`);
  - `success: true` (`:477`);
  - no active-print check (see "Found while writing this plan").
- **`deleteLoc`** (`inv_loc_mgr.js:2236`) is `fetch(DELETE).then(fetchLocations)`. It never reads the answer, so the 409 is a silent no-op.

### Undo

- **`perform_undo`** (`logic.py:2076-2204`):
  - "Nothing to undo" answers `success: false` with no log line (`:2077`);
  - a failed move-restore logs ERROR and carries on (`:2107-2111`), as does a failed ejection-restore (`:2160-2164`);
  - "↩️ Undid: …" is always logged (`:2200`);
  - `success: false` only for a resident blocked from an occupied head (`:2201-2204`).
- **The undo record is pushed even when every write of the original move failed** (`logic.py:864`).
- **`triggerUndo`** (`inv_cmd.js:1953`) discards the response. It is reached from:
  - the deck button (`templates/dashboard.html:180`);
  - the `CMD:UNDO` QR (`templates/components/scripts.html:148`), handled at `inv_cmd.js:1431`;
  - the backend `undo` command (`inv_cmd.js:1490`).

### Bulk move

- **Tally** (`execute_bulk_move`, `logic.py:1266-1342`):
  - the readback uses the fail-open reader (`:1307`);
  - per-spool `failures` are consulted only `if stuck` (`:1310-1329`);
  - an exception is only a log warning (`:1330-1331`);
  - the summary is SUCCESS whenever `failed` is empty (`:1335-1338`), and the session resets (`:1706`).
- **Unseat:** a rejected unseat only logs (`logic.py:729-734`). The incoming spool is still given that slot (`:736`) and written.
- **Source-print confirm** (`plan_bulk_move`, `logic.py:1168-1186`):
  - it runs only after the skip loop has removed ghosts ("deployed to a live toolhead", `:1107-1109`) and head-located spools ("loaded in a toolhead slot", `:1119-1126`);
  - a printing source therefore always ends as a skip or "Nothing to move" (`:1137-1140`);
  - its only test fakes a Dryer Box as printing (`tests/test_bulk_move.py:362-386`), which the real probe never reports.

---

## Design, by sub-task

### 41.1 — Block Eject All on Room and Printer views (D4 + new-findings item 3)

**Classification: one helper, mirrored in the frontend.**
- Backend: `logic.eject_all_block_reason(loc_id, loc_row, printer_map)` returns:
  - `"room_view"` when `Type == "Room"`;
  - `"printer_view"` when `Type == "Printer"` **and** `loc_id` is not a `printer_map` key. Use Group 40.0a's shared `locations_db.is_printer_row_not_head` rather than a third copy. `get_active_printer_map` is built only from Printer rows' `toolheads[]` (`locations_db.py:1002-1015`), so this means exactly "not its own toolhead";
  - `None` otherwise.
- The Printer key is the one D3 chose for its server refusal (*"this row is not itself one of its printer's toolheads' so CORE1 stays loadable"*). **So `XL` is blocked, and `CORE1` keeps Eject All as the toolhead it is.**
- Frontend: `triggerEjectAll` makes the same decision from `state.allLocations` and `state.printerMap` **before** `promptSafety`. The user then never answers a "Nuke all?" prompt only to be refused.

**Backend refusal.**
- `clear_location` returns `{"success": false, "blocked_reason": …, "msg": …}` before reading anything, and writes a WARNING Activity Log line.
- The fix branch's blank-location refusal runs first.

**Messages (toast ≥ 5 s + Activity Log).**
- **Room:** "Eject All is off for rooms — nothing was moved. To empty `LR`, use 🔀 Move all →. Its preview includes the spools in `LR`'s boxes and drawers too, so check it before you commit."
  - **Why the warning.** The bulk-move source reader uses the same flat matcher (`get_spools_at_location_detailed_strict` → `_build_location_match`, `spoolman_api.py:1633-1655`).
    - On `LR` it collects every sub-location's spools, including staged box spools in their slots.
    - It skips only ghosts, archived spools, buffered spools and head spools (`logic.py:1107-1126`).
    - The preview shows all this, but Derek should know before he follows the pointer.
- **Printer:** "Eject All is off for printers — nothing was moved. Open a head (`XL-1` … `XL-5`) to eject its spool, or use ↩️ Return."
  - ⚠️ This **adapts** D4's "point to Move all →". On a Printer view Move all is hidden (`inv_loc_mgr.js:81`) and bulk move skips every loaded head by design (`logic.py:1119-1126`), so pointing there would be a dead end. Manual check 41-b confirms the wording with Derek.

**Belt and braces for the views that keep Eject All.**
- `clear_location` skips any spool whose own location is a single-occupancy head other than the open location itself, and reports it in `skipped_loaded`. This mirrors `plan_bulk_move` `:1119-1126`.
- It means no future Type edit, naming accident or direct API call can sweep a printer's heads.

**Tests.**
- Hermetic Flask client, real engine:
  - `clear_location` on `LR`, and on `XL` with residents on XL-1…3 → `blocked_reason`, **zero PATCHes**, and the Activity Log names the reason;
  - on `CORE1` → it proceeds (probe-gated);
  - a cart whose matches include a head resident (a contrived prefix collision) → the resident lands in `skipped_loaded` and is untouched.
- Route-stubbed E2E, new file `tests/test_eject_all_honest_e2e.py`, patterned on `test_move_result_consumers_e2e.py`'s `FakeBackend`:
  - open a stubbed Room and scan `CMD:EJECTALL` → no `#safetyModal` show, no POST, the toast text;
  - the same for a stubbed Printer row;
  - a stubbed dual-role Printer → the safety prompt appears.

**Risk.** A Room row that is also used as a storage spot keeps its spools. That is correct: D4 blocks only the bulk sweep, and single ejects are unchanged.

### 41.2 — Eject All reports what really happened (part 1)

**Read strictly.** Use `get_spools_at_location_detailed_strict`. On an exception: `success: false`, "Couldn't read `<loc>` from Spoolman — nothing ejected", an ERROR log line, and nothing written.

**Branch on every result:**

| `perform_smart_eject` result | Goes to |
|---|---|
| `True` | `ejected` |
| `"REQUIRE_CONFIRM"` | `needs_unassign` |
| a `requires_confirm` dict | `failed`, with `_eject_refusal_reason` (should never happen; see below) |
| `False` | `failed`, with `_eject_refusal_reason` (`logic.py:408-419`) |

**No `needs_print_confirm` list: it could never fill.**
- `clear_location` checks the open location once, up front (`routes_scan.py:237-246`), then passes `confirm_active_print=True` to every eject (`:256`).
- 41.1's `skipped_loaded` removes every other head's spool first.
- So no eject reaches its active-print gate. A dict answer would mean something changed underneath; count it as `failed` rather than silently ejected.

**Allowed toolhead views** (XL-2, CORE1).
- The existing pre-flight answer (`routes_scan.py:237-246`) gets a frontend yes-path: the shared active-print confirm from [Group 39](39-confirm-on-every-door.md) 39.4, with D6's consequence wording.
- Then retry with `confirm_active_print: true`.
- Today that answer silently toasts "Cleared!" (I2-12).

**`needs_unassign` depends on Q1.**
- Under Q1 option B, and until Derek answers: one batch prompt, "3 spools on `CR-CT-2-R1` have no saved home. Unassign them?".
- A second POST then carries `confirmed_unassign_ids: [...]`. Only those ids get `confirmed_unassign=True`.

**Response and toast.**
- `success` is true only when nothing failed and nothing is left waiting on a decision.
- The response carries `ejected`, `needs_unassign`, `failed`, `skipped_slotted`, `skipped_loaded`.
- One summary toast: "Ejected 4 · 2 need a decision · 1 failed (#51: …)". It uses a 7 s error toast whenever anything failed.
- One Activity Log summary line: SUCCESS when clean, WARNING otherwise.

**Tests (hermetic, real engine, `WireSpoolman` rejecting chosen ids).**
- A cart with one returnable spool, one homeless spool and one rejected write → the three lists are exact, and `success` is false.
- The strict read raises → `success: false` with zero writes.
- The Group 20.2 detach runs only for spools whose write landed (already pinned; keep it green).
- Route-stubbed E2E: a stubbed mixed answer shows the counted toast, not "Cleared!"; a stubbed `require_confirm` shows the confirm and the retry carries the flag.
- **Test debt: the FE-1 double-click** (Move-pipeline follow-ups item 6), in `tests/test_confirm_chain_reshow_e2e.py`.
  - The existing double-click test covers only `#confirmModal`. This sub-task adds a follow-up prompt after `#safetyModal` ("Unassign N spools?").
  - Pin that double-clicking FORCE EXECUTE never confirms that follow-up unseen.
  - Pin the same for a `promptAction` chain, since the item names both dialogs.

**Risks.**
- The 27.6 pins on `skipped_slotted` (`test_l316_charact_scan_audit.py`) keep that key, but the success toast wording changes.
- `perform_smart_eject` answers "true unassign" for PolyDryer (`PM-DB-n`) spools already. They will now appear under `needs_unassign` instead of being silently counted.

### 41.3 — Location delete reports honestly, and never reaches a head (part 2 + the plan-time finding)

**Non-toolhead delete: keep what a delete reaches, and add the explicit guard Group 37 requires.**

**Don't narrow the reach.**
- Group 37 says "what may I destroy" is the one question that stays flat (`37-location-system-redesign.md:52-54`).
- Its invariant asks only that a room-level clear or delete never reach a live toolhead, via an explicit guard (`:253`).
- Narrowing "delete `LR`" to spools filed on `LR` itself would visibly change what happens to `LR-MDB-1`'s contents, and nobody has decided that.
- It is **Q4** below. Build the default until Derek answers.
- (An earlier draft of this plan narrowed the delete, and claimed Group 37 supported that. It had 37 backwards.)

**Read with the strict reader** (`get_spools_at_location_detailed_strict`), and sort each match:
- **A spool whose own `location` is a toolhead, or another single-occupancy location** (a head resident, or a prefix hit when the deleted row is a Printer row like `XL`) → **never touched**, and reported in `skipped_loaded`.
- **A ghost**, matched through `physical_source` (`spoolman_api.py:1473-1479`) → it keeps its location.
  - Clear its trail only when the trail names exactly the deleted row, as the toolhead cascade already does (`logic.py:1987-1993`).
  - A prefix-hit ghost whose trail names a surviving child keeps that trail.
- **Everything else** (direct matches, and, under the default, prefix hits in sub-locations) → unassigned with the trail cleared: `container_slot`, `physical_source` and `physical_source_slot` all `""`, through `update_spool`'s read-merge. This replaces today's location-only PATCH (`routes_locations.py:458`).

**Log** every failure to the Activity Log at ERROR, not only `hub.log`.

**Before building: a read-only count.** The spool #99 buglist item asks for the stale-trail count: spools whose `physical_source` is set while they are not on a head. A box delete now clears exactly the trails that name that box, so this count sizes how many spools a delete touches beyond its own contents.

**Any spool that couldn't be re-homed means the row is NOT deleted.**
- Answer `success: false` with `errors`.
- A retry is idempotent: already-unassigned spools simply don't match again.
- Toolhead branch: same rule. Skip the `save_locations_list` when `result["errors"]` is non-empty. The cascade's edits to `slot_targets` and `toolheads[]` live only in the unsaved `current` list (`routes_locations.py:425-431`), so nothing half-applies to disk.

**`deleteLoc`.**
- Read the JSON.
- **409 `requires_confirm`** → Group 39's shared confirm → retry with `&confirm_active_print=1`.
- **`success: false`** → a 7 s error toast listing the spools.
- **Success** → `fetchLocations()`.
- Optional: name the count in the first prompt ("Delete `CR-CT-2-R1`? Its 3 spools go to Unassigned.") with one `/api/get_contents` read.

**Tests (hermetic, real matcher through `FakeSpoolman`).**
- Deleting `LR-MDB-1` while `#57` is on `XL-1` with trail `LR-MDB-1:1` → `#57` is still on `XL-1`, its trail is cleared, the row is gone.
- Deleting `LR` (the default) → `LR-MDB-1`'s staged spools are unassigned with their trails cleared, as today. No spool on an XL head is touched, and a head spool whose trail names `LR-MDB-1` keeps it.
- Deleting the Printer row `XL` → every XL-1…XL-5 resident is untouched and listed in `skipped_loaded`.
- A rejected unassign → the row is still present, `success: false`, an ERROR line.
- The toolhead cascade with one rejected unassign → the row is kept and `save_locations_list` is not called.
- Route-stubbed E2E: a stubbed 409 opens the confirm and retries with the query flag.

**Risk.** Under the default, a Room delete reaches the same spools as today. It now spares head spools, clears the trails it leaves behind, and reports failures. If Derek picks Q4's option B or C, that is the visible change: pin it with its own test and manual check.

### 41.4 — Undo reports what really happened (part 3)

**`perform_undo`.**
- Collect failed move-restores and ejection-restores into `failed`.
- Answer `success: false, msg: "Undo could not restore #42 (…)"` when anything failed or was blocked.
- Write "↩️ Undid: …" only for what landed. Otherwise write "⚠️ Undo partly failed: …" as ERROR.

**"Nothing to undo."** Keep the answer and add an INFO Activity Log line: a `CMD:UNDO` scan is a scan outcome, so CLAUDE.md requires a log entry and a toast.

**Don't record undo for writes that never landed.**
- Filter `undo_record["moves"]` / `["extras"]` / `["labels"]` by `failures` before `_push_undo` (`logic.py:864`).
- If nothing moved and no resident was unloaded, push nothing at all.

**`triggerUndo`.**
- Read the JSON.
- On success: the existing refresh plus "↩️ Undone".
- "Nothing to undo": an info toast.
- Any other failure: `msg` in a 7 s error toast.

**Tests (hermetic, real engine).**
- Every restore write rejected → `success: false`, no "Undid" SUCCESS/WARNING line, ERROR lines present.
- A move whose single write was rejected pushes no undo record.
- Keep `test_logic_undo.py` and the four undo tests in `test_active_print_chain_confirm.py` (`:786-848`) green.
- Route-stubbed E2E: a stubbed failure raises the 7 s toast; "Nothing to undo" raises the info toast.

**Ask before touching a printing head (D6; built by default, and Q2 only confirms it).**

D6's rule is "before a move writes anything, if a moving spool's own location is a toolhead whose printer is PRINTING…". Undo writes spool moves (`logic.py:2096-2111`), so Undo asks, the same way a move does.
- **Collect the heads first.** Before any restore write, list the heads the undo would change: each move's current location and its restore target, and each ejection's original head. Pass them through Group 39.1's `_uncovered_active_heads`, which probes each printer once.
- **Answer before writing.** If any printer is active, the Undo route (`api_undo`, `routes_locations.py:673`) answers `requires_confirm` with D6's wording and writes nothing.
- **Frontend.** `triggerUndo` shows the shared confirm (Group 39.4) and retries with `confirm_active_print`.
- **Merge note.** Build it in the same restore loops that Group 42.3b edits (occupancy check, attach/release). Whichever lands second merges.
- **Test (hermetic, real engine).**
  - Undo of a Quick-Swap onto XL-2 while XL is PRINTING → `requires_confirm` naming XL-2, zero writes.
  - Confirmed → restored.
  - PAUSED → no ask.

### 41.5 — The bulk-move tally never counts a rejected spool as moved

- **Always union `move_result["failures"]` into `failed`**, independent of the readback.
- **Read back with the strict reader.** On an exception, add `"unverified": true` and log the summary as WARNING: "🔀 Bulk move `CR-CT-2-R1` → `CR-TC-2-R2`: moved 3 (couldn't verify with Spoolman), failed 0".
- The panel's commit handler (`inv_cmd.js`, the `commit` POST near `:436`) toasts the unverified warning at ≥ 7 s.
- **Tests (hermetic).** Move the investigation's I2-05 scratch case into `tests/test_bulk_move.py`: `get_all_spools` raises during the readback and every write is rejected → `failed` lists both, the summary is WARNING, `success` is false.

### 41.6 — A rejected unseat refuses to seat the incoming spool

- In the slot-assignment block (`logic.py:716-736`), when the unseat `update_spool` fails:
  - set `failures[str(sid)] = "couldn't unseat #7 from slot 2: <error>"`;
  - skip that spool's write (`continue`).
- Consumers already read `failures` (`smart_move_failure`, `logic.py:337-353`), and 41.4 keeps it out of the undo record.
- **Test (hermetic, real engine):** the unseat PATCH for `#7` is rejected → slot 2 holds only `#7`, `#42` stays where it was, `failures["42"]` names the unseat, and the ERROR line is present.

### 41.7 — Bulk Move's source-print confirm

Implement Derek's answer to **Q3**. Under the recommended option A:
- delete the pre-flight 4 block (`logic.py:1168-1186`) and its fake-box test (`tests/test_bulk_move.py:362-386`);
- keep the `/api/bulk_move` and session `require_confirm` plumbing, because a destination confirm can still come back from the engine (`logic.py:1289-1293`);
- update `L298-bulk-moves-plan.md`'s description of the flow.

### 41.8 — Room-only spools

Implement Derek's answer to **Q1** in `perform_smart_eject`'s no-home branch (`logic.py:1890-1905`), and, if he says so, in Smart Load's `_known_room_of` use (`:647-653`).

**Tests** (hermetic, real engine, one per location kind):
- a cart-row spool;
- a box spool;
- a drawer spool;
- a PolyDryer spool (unchanged);
- a Room spool (unchanged);
- a Smart Load resident.

---

## Dependencies and build order

- **Hard:** merge `fix/core1-return-ejectall-guard` (`1fb5678` + `76398cb`, local only) into `dev` first, because it edits the same functions.
- **Soft:** build [Group 39](39-confirm-on-every-door.md) first.
  - 41.2, 41.3 and 41.4 reuse its shared active-print confirm, its D6 wording, its `setProcessing(true, {label})` "Checking…" label, and its `_uncovered_active_heads` (for Undo).
  - If 41 has to go first, use a `mountOverlay` confirm local to `inv_loc_mgr.js`, never a Bootstrap confirm raised from inside another confirm's callback. Leave a note to fold it in later.
- **[Group 42](42-single-slot-box-lifecycle.md):** build 41 first.
  - 41.8 / Q1 settles the no-home rule before 42.3c copies it.
  - 41.4 gives 42.3b's blocked restores a reporting channel.
- **[Group 37](37-location-system-redesign.md):** compatible.
  - 41.1 classifies by `Type`, not by the flat matcher, so 37.4's transitive contents won't change it.
  - 41.3 keeps 37's flat reach for a delete and adds 37's explicit head guard. Q4 decides whether to narrow the reach.
- **Recommended order across the four groups:** 39 → 41 → 42 → 40 (see Cross-plan notes).
- **Order inside the group:**
  1. Get Derek's answers to **Q1**, **Q3** and **Q4**, and his confirmation of **Q2**. They change 41.2, 41.3, 41.4, 41.7 and 41.8.
  2. **41.1** the block.
  3. **41.2** honest Eject All.
  4. **41.6** unseat.
  5. **41.5** tally.
  6. **41.4** Undo, with Group 39's `_uncovered_active_heads`.
  7. **41.3** delete.
  8. **41.7** and **41.8**.

## Cross-plan notes (Groups 39–42, reviewed 2026-09-13)

### Recommended build order across the four groups

Full reasoning is in [Group 39's Cross-plan notes](39-confirm-on-every-door.md).

0. **Merge the two local-only branches into `dev`:**
   - `fix/core1-return-ejectall-guard` (`1fb5678`, `76398cb`), this group's hard dependency;
   - `test/sweep-reds-hermetic` (`d785444`).
1. **Ask Derek the three contract-shaping questions first.**
   - **This doc's Q1** is one of them. It shapes Group 39.6's wording, 41.2's lists and Group 42.3c's redirect.
   - The other two are Group 39's Q1 and Group 42's Q-B.
   - Q3, Q4 and the Q2 confirmation can wait for their sub-tasks.
2. **Build order:** Group 39 → **Group 41** (this group) → Group 42 → Group 40.
   - 41 is the smallest group, and it closes the destructive doors: Eject All on a Printer view mid-print, and deleting a box unassigning head spools.
   - If Derek wants the PolyDryer release first, 41 and 42 can swap.

### Overlaps that concern this group

**`perform_smart_eject`'s answer.**
- 41.2 maps its return contract (`True` / `False` / `"REQUIRE_CONFIRM"` / dict).
- Group 39.6 deliberately keeps that contract, and combines its two confirms in `manage_contents remove` instead.
- 41.8 edits the no-home branch that 39.6's `_eject_destination` helper factors out. Build 41.8 on that helper.
- Group 42.1 adds a release after each successful write.

**One no-home resolver.**
- Today several places decide where a spool with no home goes: `logic._known_room_of` (moving to `locations_db` in Group 42.3c), `get_room_from_location` (`logic.py:1713-1735`), 39.6's `_eject_destination`, and 41.8.
- Implement Q1's answer once, in that resolver.

**One Printer-row classifier.**
- 41.1 uses Group 40.0a's `locations_db.is_printer_row_not_head` and its `inv_core.js` mirror.
- The core1 branch's `_printer_row_toolheads` moves beside it.

**The pre-write contract.** 41.6's unseat refusal is step 6 of Group 39.1's order.

**One strict "direct residents" reader.** Built in 39.7; it serves 41.2's and 41.3's reads.

**`clear_location` / `triggerEjectAll`** are touched by:
- the core1 branch: the blank-location refusal, plus `triggerEjectAll` already returning early on a plain `success: false`;
- 41.1 (the block) and 41.2 (honest lists);
- Group 42.1, which reaches it through eject.

**`perform_undo` (`logic.py:2076-2204`).**
- 41.4 and Group 42.3b edit the same loops.
- 41.4's D6 ask uses Group 39.1's `_uncovered_active_heads`.

**Frontend confirm and waiting UI.** 41.2 (Eject All on a head), 41.3 (`deleteLoc`) and 41.4 (Undo) reuse Group 39.4's `window.confirmActivePrint` and 39.3's `setProcessing(true, {label})`.

**The read-only count before 41.3.** It is the same GET that Group 42.1 and 40.0c want. Do it once.

**Group 22.** Found-while-briefing item 6 becomes an unblocked 22.5, built alongside Group 39.4 (see "Placed in Group 22").

**Group 34.**
- 41.5 and 41.7 edit L298 bulk-move code, and 41.7 also updates `L298-bulk-moves-plan.md`.
- No conflict with S5 or the auto-generated-id slice.

**Group 37.**
- 41.1's `skipped_loaded` and 41.3's head guard implement 37's invariant: "a room-level clear/delete must never reach a live toolhead, via an explicit guard".
- 41.3 keeps 37's flat reach for a delete; Q4 decides whether to narrow it.
- 41.1's Room → Move all pointer inherits the room-wide bulk-move source (37's matcher root cause).

**Move-pipeline follow-ups item 6.** This group takes the FE-1 double-click on the safety and action dialogs (41.2).

**Shared test pins.**
- `test_l316_charact_scan_audit.py`: its 27.6 `skipped_slotted` pins (41.2). Group 39.6 flips `:388`.
- `test_active_print_chain_confirm.py:786-869` (41.4; also 42.3b).
- `test_l316_charact_record_deletes.py` `:537`, `:576` (41.3, the delete cascade).
- `test_bulk_move.py:362-386` (41.7).
- `test_confirm_chain_reshow_e2e.py` (41.2's FE-1 cases; also 39.6, 39.9 and 40.3).

---

## Verification

- **Iterate hermetically.** From `inventory-hub/`, run `"C:/Python314/python.exe" -m pytest tests/ -p no:cacheprovider -q --offline`.
- **Before merging**, run the full E2E sweep. ⚠️ It writes to shared dev data, so get Derek's OK and don't run it while he tests by hand.
- **The route table is unchanged**, so `tests/test_route_table_pin.py` needs no update.
- **Update CLAUDE.md's write-surfaces rows** for `/api/locations` cascade unassign, `perform_undo`, `clear_location`, and the `_perform_smart_move_impl` unseat.

---

## Manual checks for Derek (add to the checklist)

`CMD:EJECTALL` needs a scannable label. The ☢️ DANGER ZONE QR on a Dryer Box that has a floating spool works, printed or shown on a second screen. Dev spools are virtual test fixtures, so moving them is fine.

| # | Check | Steps | Pass if |
|---|---|---|---|
| 41-a | **Room view is blocked** | Open `LR` → scan `CMD:EJECTALL` | No "Nuke all?" prompt. The toast says Eject All is off for rooms, points to 🔀 Move all →, and warns that Move all's preview includes the spools in `LR`'s boxes and drawers. Nothing moves, and the Activity Log has the line. **Don't commit a Move all from `LR` as part of this check** |
| 41-b | **Printer view is blocked** | Open `XL` (ideally while printing) → scan `CMD:EJECTALL` | No prompt. The toast points to opening a head or ↩️ Return. Every XL-1…XL-5 spool stays loaded, and no PolyDryer loses its binding. **Also tell us whether this wording, instead of "use Move all →", reads right to you** |
| 41-c | **CORE1 keeps it** | CORE1 idle with a spool loaded → open `CORE1` → scan `CMD:EJECTALL` | The "Nuke all?" prompt appears, and the spool goes back to `CR-MDB-1` slot 1 (or you are asked about a spool with no home) |
| 41-d | **A toolhead mid-print asks** | XL printing → open `XL-2` → scan `CMD:EJECTALL` | A print warning appears, not "Cleared!". Cancel leaves the spool; Yes ejects it |
| 41-e | **Honest counts on a box** | Give `LR-MDB-1` a 5th spool with no slot (the "5/4" case) → its DANGER ZONE → EJECT ALL | The toast says how many were ejected, not just "Cleared!", and where they went (Activity Log) |
| 41-f | **A homeless spool on a cart row** | Force Location a spare spool onto `CR-CT-2-R1` (it now has no saved home) → EJECT ALL there (scan) | Behaves as you answered Q1 (e.g. one "Unassign 1 spool?" prompt). It does **not** silently land on `CR` |
| 41-g | **Deleting a location** | Add a throwaway Cart `TEST-DEL-CT` → Force Location a spare spool there → delete `TEST-DEL-CT` | The spool is Unassigned with no leftover box link. A toast names what happened |
| 41-h | **Deleting a box that feeds a head** | XL idle. Add a Dryer Box `TEST-DEL-DB` (Max 2), bind slot 1 → `XL-5`, scan its slot-1 label with a spare spool so it loads onto XL-5 → delete `TEST-DEL-DB` (then restore XL-5's original spool) | The spare spool is **still on XL-5**; only its "from box" link is gone |
| 41-i | **Undo with nothing to undo** | Refresh the page → press Undo twice | The second press shows "Nothing to undo" (today: nothing at all) |
| 41-j | **Undo after a move** | Move a spare spool `CR-CT-2-R3` → `CR-TC-2-R1` → Undo | A "↩️ Undone" toast; the spool is back in `CR-CT-2-R3` |
| 41-k | **Bulk Move source check** | Per Q3 (default: re-run Bulk Move check 4 while printing) | A skip reason for the loaded spool, never a prompt |
| 41-l | **Undo mid-print asks** (41.4, Q2) | XL idle: Quick-Swap `LR-MDB-1` slot 2 onto XL-2. Start an XL print. Press Undo | One prompt naming XL-2 and which spool FCC would charge this print to. Cancel changes nothing; Yes puts both spools back |

---

## Open questions for Derek

### Q1 — Where should a spool with no saved home go when it's ejected from a box, cart, drawer or shelf? — ✅ ANSWERED 2026-09-18: option B

**Derek chose B: Unassigned, after one "unassign?" prompt**, with Eject All asking once for the whole batch. The follow-up is confirmed too: Smart Load's homeless resident keeps the 2026-09-12 rule (the printer's Room). 39.6's wording and 42.3c's redirect follow from this. The background below is kept for the record.

**Background.**
- When FCC ejects a spool, it sends it back to the place it came from, if it recorded one.
  - For a spool that was loaded onto a head from a dryer-box slot, that place is the box slot.
  - For a spool that was simply placed on a cart row, drawer or shelf, nothing is recorded, so FCC has **no home** for it.
- Today FCC then moves it **up to the Room** that location sits in. It shows in that Room's "☁️ Loose / Floating" list, and the Location List shows only the Room as its location.
- You said Room-only spools are a pain to find. This fallback creates them.
- Two cases already work differently:
  - A **PolyDryer** spool (`PM-DB-n`) or a spool loose in a Room has no Room to fall back to, so you get the "true unassign?" prompt and it goes to Unassigned.
  - When **Smart Load** pushes a head's spool off to make room, a spool with no home goes to the printer's Room: you chose that on 2026-09-12 (XL-2 → `LR`).

**Where you meet it.**
- ⏏️ Eject on a spool card.
- Eject mode + a spool scan.
- EJECT ALL on a box, cart or shelf (41.2).
- Loading a spool onto a head that already holds one.

**Worked example.**
- `#88` sits on `CR-CT-2-R1`. It got there by a scan, so it has no saved home. You press ⏏️ Eject on its card.
  - **Today:** `#88` becomes location `CR`. Later the cart shows nothing, and the Location List just says `CR`.
  - The same happens to three such spools if you EJECT ALL on `CR-CT-2-R1`.

**Options.**
- **A. Keep the Room fallback** (today).
- **B. Unassigned, after one "unassign?" prompt** (the prompt a PolyDryer spool already gets). Unassigned is one list you can work through, and it says honestly that FCC doesn't know where the spool is. Eject All asks once for all of them. **(Recommended.)**
- **C. Refuse the eject:** "#88 has no home to go back to — scan where it's going." Nothing moves until you place it. This makes Eject All on such a cart mostly a list of refusals.

**Follow-up.** Should **Smart Load**'s homeless spool (pushed off XL-2 → `LR` today) follow the same rule?
- **Recommended: keep your 2026-09-12 decision.** That spool comes off a printer that really is in `LR`, and it usually gets set down right there. The painful case is spools filed on carts and shelves.

### Q2 — (confirm only) Undo asks before it takes a spool off, or puts one onto, a printing head

**Status.** Built as option A by default, because your D6 rule already covers it. This question only confirms that. Don't treat it as open.

**Background.**
- Undo (the deck button, or scanning `CMD:UNDO`) reverts the last move.
- Today it writes to Spoolman directly and **never checks the printer** (`logic.py:2096-2111`).
- Your D6 answer covers moves, and an Undo is a move, so 41.4 applies D6 to it. Say so if Undo should be the exception.

**Where you meet it.** The Undo deck button on the dashboard and the `CMD:UNDO` QR.

**Worked example.**
- 10:00, XL idle: you Quick-Swap `LR-MDB-1` slot 2 onto XL-2. `#57` goes on, and XL-2's old spool `#196` goes back to its box.
- 10:05: an XL print starts.
- 10:30: you press Undo (on purpose, or by scanning the wrong label). `#57` goes back into `LR-MDB-1` slot 2 and `#196` back onto XL-2, **mid-print, with no prompt**. FCC now charges XL-2's usage to `#196`, while `#57` is physically still feeding it.

**Options.**
- **A. Ask, like a move:** when a head the undo would change belongs to a printing printer, one prompt for the whole undo with D6's wording ("Undo takes #57 off XL-2 and puts #196 back while XL is printing, so FCC charges this print to #196. Continue?"). **(Recommended:** an undo can revert a move made long before the print started.)
- **B. Never ask:** Undo means "put back what I just did", and you already confirmed the original move.

### Q3 — Bulk Move's "the source is printing" prompt can never appear. Remove it, or make it cover something?

**Background.**
- Bulk Move always leaves loaded and deployed spools where they are: a spool on a toolhead, or a box spool deployed to one, is listed as skipped with a reason.
- Its "source is printing" prompt is checked only **after** those skips, and only when the source location is itself a toolhead. By then there is nothing left to move.
- So the prompt never shows on real data. It was only ever tested with a fake "printing dryer box".
- The current Bulk Move check 4 already expects a skip, not a prompt.

**Where you meet it.** 🔀 Move all → or the `CMD:BULKMOVE` scan, while a printer is printing.

**Worked example.**
- XL printing. Bulk move `LR-MDB-1` → `LR-SD-1`:
  - the spools in slots 1–3 are deployed to XL-1…XL-3, so they are **skipped**;
  - slot 4's spool (the XL pool, e.g. `#99`) moves;
  - no prompt, because nothing feeding the print moves.
- Bulk move `XL-3` → anywhere: you can't start it (Move all → is hidden on heads), and a scanned `XL-3` source gives "Nothing to move".

**Options.**
- **A. Remove the prompt** and its fake test. Bulk Move stays "never moves a loaded spool". Moving a real loaded spool mid-print goes through a single move, which asks under D6. **(Recommended.)**
- **B. Make it cover staged slots:** ask when a spool is taken from a box slot bound to a head whose printer is printing, e.g. a spool staged in `LR-MDB-1` slot 2 while XL-2 runs off a PolyDryer. That spool isn't feeding the print, so the prompt only matters when FCC is out of step with the printer.
- **C. Leave it as is** (dead but harmless).

### Q4 — When you delete a Room, should the spools in its boxes and shelves be unassigned too?

**Background.**
- Deleting a location in the Location Manager removes the row, then unassigns the spools FCC finds "in" it.
- For a Room, FCC counts everything whose name starts with the Room's code. For `LR` that is `LR-MDB-1`, `LR-MDB-2`, `LR-SD-1`, `LR-SD-2`, and anything filed on `LR` itself.
- Those child rows are **not** deleted with the Room, but their spools are unassigned anyway.
- Nothing stops you deleting a Room that still has locations inside it: the delete prompt is just "Delete LR?" (`inv_loc_mgr.js:2236`).
- Group 37 (the location redesign) decided two things about this:
  - a delete keeps that wide reach;
  - a delete must never reach a spool loaded on a toolhead.
- 41.3 adds the toolhead guard whatever you answer. The open part is the boxes and shelves.

**Where you meet it.** Location Manager → a Room row → delete.

**Worked example.** You reorganise and delete Room `LR`. `LR-MDB-1` slots 1-3 hold spools staged for XL-1…XL-3, slot 4 holds an XL pool spool, and `LR-SD-1` holds two drawer spools.

**Options.**
- **A. Keep today's reach, minus heads** (the default until you answer).
  - All six spools become Unassigned, with their box links cleared.
  - The spools loaded on XL-1…XL-5 stay loaded.
  - The `LR-MDB-1` and `LR-SD-1` rows still exist, now empty.
- **B. Only what's filed on `LR` itself.**
  - The six box and drawer spools stay where they are.
  - Only spools whose location is exactly `LR` become Unassigned.
- **C. Refuse to delete a Room that still has locations inside it.**
  - The message: "LR still contains LR-MDB-1, LR-MDB-2, LR-SD-1, LR-SD-2 — move or delete them first."
  - Nothing is unassigned by accident.
  - **Recommended.** Deleting a Room with live boxes inside is almost always a reorganisation. A delete records no Undo, so six emptied locations would have to be fixed by hand.
