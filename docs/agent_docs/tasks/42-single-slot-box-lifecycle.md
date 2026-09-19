# Group 42: 🔓 Single-Slot Box Lifecycle & One Loaded Spool per Toolhead

**Branch:** `feature/group-42-single-slot-box-lifecycle`
**Estimated effort:** MEDIUM (~8–12 h, 1–2 sessions). Release rule + pins ~3 h · slot-1 normalization ~1 h · one-spool engine guards + undo ~2 h · eject feedback + visibility ~2–3 h · tests throughout.
**Risk:** **MEDIUM.** It adds `locations.json` writes to more move paths and touches `spoolman_api.update_spool` (the auto-archive edge). Every change is best-effort on the binding side and must never fail or roll back the spool write it follows.

> **Status: `TODO` — scoped 2026-09-13, not started.**
> Built from Derek's single-slot box release rule and his one-spool principle ([open-decisions-2026-09-13.md](open-decisions-2026-09-13.md) § D3).
> Evidence: [active-print-chain-investigation-2026-09-12.md](active-print-chain-investigation-2026-09-12.md) (I5-8, I5-9, I5-10, I5-15, I5-17, and the verifier's "A refused eject still detaches…") and [active-print-chain-diff-reviews-2026-09-12.md](active-print-chain-diff-reviews-2026-09-12.md) (R1-01, R1-03, R3-06).
> Every `file:line` was re-read on `dev` @ `be9f045`. Re-grep the named function before editing.
> **Sweep-triage item 3** (the five E2E fixtures that borrow PM-DB-1 → XL-1 and "restore" whatever they saw) is being fixed separately on `test/sweep-reds-hermetic`. This group's tests must not borrow a real dev box either.

---

## ⚠️ Read this first

**Derek's rule (decided):** *"A single-slot box stays bound to a toolhead until ITS OWN spool leaves that head, by any path (eject, Return, Quick-Swap, any move). Ejecting a different spool from the head no longer unbinds it."*

**Derek's principle (decided):** *"a toolhead should never have two spools attached to it directly… If looking at the toolhead, I should only ever see one in there."* Showing *loaded* and *assigned/feeding* as separate statuses is fine. A head never shows two loaded spools.

- **Test through the real engine and the real binding helpers.** The existing chain tests mock the Group 20.2 attach/detach to fixed return values (`tests/test_active_print_chain_confirm.py:280-283`), so they cannot see a binding survive or vanish across hops. Lifecycle tests need a real in-memory `locations.json` (see "Test conventions"), and must prove they fail on a `git archive HEAD` extract ([[mocked engine hides chain bugs]]).
- **The binding write is plumbing, never contents.** Only a *single-slot* box's slot 1 is lifecycle-driven. Multi-slot `slot_targets` stay user config and are never auto-changed (CLAUDE.md, Group 20.2, L298 Phase 4).
- **Spoolman I/O stays outside `locations_write_lock()`.** The release runs after the spool write returns, and only the file cycle is locked (the Group 38 write-lock rule).

---

## Items covered (quoted from `Feature-Buglist.md`)

| # | Buglist item | Decision / principle |
|---|---|---|
| **A** | **🟠 Found while briefing the six open decisions** — item 5: *"🟡 Quick-Swap Return skips the Group 20.2 single-slot box detach that eject runs, so a PolyDryer stays bound to a head after its spool is Returned."* | Covered by the release rule (item C below). |
| **B** | Same entry — item 9: *"🟡 A move off a toolhead that isn't an eject never releases a single-slot box. The Group 20.2 detach runs only inside `perform_smart_eject`. Moving a PolyDryer's spool off its head by a buffer scan to another location, Force Location, or a Location Manager assign (`perform_smart_move`) leaves the box bound."* | *"**Decided 2026-09-13 (Derek):** a single-slot box stays bound until ITS OWN spool leaves that head, by any path (eject, Return, Quick-Swap, any move). Ejecting a different spool from the head no longer unbinds it. One rule covers this item, item 5, and the toolhead-keyed detach in "Only Smart Load enforces one spool per toolhead" item 5. Derek's principle: a toolhead only ever shows ONE loaded spool, though loaded vs feeding may be shown as separate statuses."* |
| **C** | **🟠 Only Smart Load enforces "one spool per toolhead" — other writers can still stack a second spool.** — item 5: *"**The Group 20.2 box detach is keyed on the toolhead, not the spool,** so ejecting the wrong spool from a doubled head unbinds the PolyDryer feeding the one that stays."* | The release rule. |
| **D** | Same entry — item 2: *"**Undo** restores a spool's origin with no occupancy check, so undoing after a placement that pushed no undo record (auto-unarchive, wizard, direct edit) can double up a head."* | The one-spool principle. |
| **E** | Same entry — item 3: *"**`/api/smart_move` with several spools** writes all of them onto a toolhead; L124's one-spool trim exists only in the frontend location-scan path."* | The one-spool principle. |
| **F** | Same entry — item 6: *"**Visibility:** the printer-status bar renders only the first item, so a second spool on a head is invisible there. Suggest a "2 spools on a single-spool head" warning chip on the status bar and the toolhead view."* | The one-spool principle ("loaded vs feeding may be separate statuses"). |
| **G** | **Unattaching a single-spool box (PolyDryer) from a toolhead is unclear — eject does it, but tells you almost nothing.** Derek: *"No clear/easy way to unattach a single spool box (Polydryer) from a tool location… I had to dig a little to I think confirm that the spool was back in the box?"* Directions to decide: *"(a) make the eject result say where it went… (b) decide what a location scan in eject mode SHOULD mean — eject that toolhead's resident spool, or at minimum warn that eject mode doesn't apply to locations; (c) optionally show a toolhead's current box binding on its manage view, so "is it attached?" is answerable at a glance."* | (a) and (c) designed here; (b) is **Q-B** for Derek. The item's line refs are stale: attach is now `logic.py:801-806`, the detach helper `logic.py:1776-1792`, the eject toast `inv_loc_mgr.js:1560`, the eject-mode spool branch `inv_cmd.js:1722`, the location branch `inv_cmd.js:1652-1719`. |
| **H** | **"Only Smart Load…"** — item 1: *"**Auto-unarchive** (`spoolman_api.update_spool`, `fcc_pre_archive_location`): a print deduct that takes a loaded spool to 0 g archives it and records its toolhead as the breadcrumb. After a new spool is loaded there, any later weight correction on the old spool writes it back onto that toolhead, with no occupancy check and only an INFO log. The deduct-to-0 archive itself also runs with no active-print guard."* | No Derek decision. [Group 39](39-confirm-on-every-door.md) excluded it and assigned it to this group, with the fix direction *"restore only if the head is empty, else Room/Unassigned plus a WARNING"*. Adopted as 42.3c. |

**Considered, owned elsewhere:**
- **🟡 Move-pipeline follow-ups** item 1 (R1-03): *"Smart Load's resident LIST read is still fail-open… a blip makes an occupied head look empty and the load stacks a second spool with `status: success`."* Same one-spool invariant, but **owned by [Group 39.7](39-confirm-on-every-door.md)**, which does the move-test mock pass it needs together with 39.4. This group relies on it and does not re-plan it.

---

## How the binding works today (confirmed in code)

- **Who is lifecycle-managed.** A row with `Type` exactly `"Dryer Box"` and `Max Spools` that parses to ≤ 1 (`locations_db._is_single_slot_dryer_box`, `locations_db.py:1612-1625`).
  - Blank or unparseable `Max Spools` → NOT managed (fail safe).
  - `"0"` → managed.
- **Attach.** After a spool's write onto a `printer_map` head succeeds, `attach_single_slot_box_to_toolhead(current_loc, target)` binds the box it came from (`logic.py:795-806`; helper `locations_db.py:1628-1658`, idempotent at `:1650-1651`). A spool coming from a multi-slot box, a room or another head attaches nothing.
- **Detach, today.** Only in `perform_smart_eject`. After the spool's own write lands (the 2026-09-12 fix, `logic.py:1776-1792`), it calls `detach_single_slot_boxes_from_toolhead(current_location)`, which unbinds **every** single-slot box bound to that head, whichever spool left (`locations_db.py:1661-1685`, the match at `:1678`).

Dev rows used in the examples below (read-only `data/locations.json`): **PM-DB-1…PM-DB-8** are Dryer Boxes with Max 1 and no bindings at rest (parent `PM`, a pseudo-room prefix, `locations_db.py:600`). **LR-MDB-1** Max 4 (1→XL-1, 2→XL-2, 3→XL-3, 4→`PRINTER:XL`). **LR-MDB-2** Max 2 (1→XL-4, 2→XL-5). **CR-MDB-1** Max 4 (1→CORE1). **XL** is a Printer row with heads XL-1…XL-5; **CORE1** is a Printer that is its own head.

### Every way a spool leaves a head, and what happens to its single-slot box

| Path | Code | Box released today? | After this group |
|---|---|---|---|
| Eject, return-home | `perform_smart_eject` write `logic.py:1882-1885` | Yes, but **toolhead-keyed** (all single-slot boxes on the head) | Only the spool's own box |
| Eject, no home (confirmed unassign, or Smart Load's `homeless_destination`) | `logic.py:1912-1916` | Yes, toolhead-keyed | Only the spool's own box |
| Smart Load unloading a resident (Quick-Swap, deposit chain, toolhead QR, Location Manager assign) | `logic.py:650-653` → `perform_smart_eject` | Via eject, toolhead-keyed | Via eject, spool-keyed |
| Quick-Swap Return | `routes_bindings.py:711-714` → DRYER branch `logic.py:819-836` | **No** (item A) | Yes |
| Buffer scan / Force Location / LM assign / `/api/smart_move` to a box, room or shelf | DRYER `logic.py:819-836`, GENERIC `logic.py:839-862` | **No** (item B) | Yes |
| Head → head move | PRINTER MOVE `logic.py:742-816`; `_ghost_trail_from` drops a head-sourced trail `logic.py:382-383` | **No** | Released from the old head; re-attach at the new head is **Q-A** |
| Force Location → Unassigned (`force_unassign`) | `perform_force_unassign` write `logic.py:2067` | **No** | Yes (also covers an archive that still has weight left, see 42.1b) |
| Weigh-out to 0 g | `inv_weigh_out.js` first sends `archived: true` with the weight through `/api/spool/update` (`:416`, `:432`), then `force_unassign` (`:493`). Inside that update, `_auto_archive_on_empty` has already set the location to `''` and cleared the trail (`spoolman_api.py:215-241`). `perform_force_unassign` therefore sees an unassigned spool, and its "left a head" gate never fires | **No** | Yes, through **42.1b** (the archive edge), **not** the `force_unassign` call |
| Undo of a deploy | `perform_undo` moves restore `logic.py:2096-2111` | **No** | Yes (and attach on the reverse, 42.3b) |
| A print deduct drives the spool to 0 g → auto-archive + unassign | `spoolman_api._auto_archive_on_empty` `spoolman_api.py:215-241`, applied in `update_spool` `:317-333` | **No** | Yes (42.1b) |
| Toolhead row deleted | `perform_toolhead_delete_cascade` drops every `slot_targets` entry feeding the head, `logic.py:2003-2022` | Yes (all) | Unchanged: the head no longer exists |
| Eject All on a location | `routes_scan.py:256` → `perform_smart_eject` | Via eject | Via eject, spool-keyed |

---

## 42.1 — Spool-keyed release on every path (items A, B, C)

**The rule, made precise.**
- When a spool **S** leaves head **H** (a successful write whose new location is not H), look at S's trail as it was **before** the move (`extra.physical_source`, quotes stripped).
- If that trail names a single-slot Dryer Box **B** whose slot `1` is bound to H → unbind B.
- Nothing else unbinds B.

Why the trail is a reliable "its own spool" key while S sits on H:
- the wizard cannot write system-managed extras (`routes_inventory.py:620-630`);
- a re-scan onto the same head keeps the trail (`logic.py:750-754`);
- the 13.6 reverse-binding only fills an EMPTY trail (`logic.py:767-770`). **But it can fill that trail WITH a single-slot box**, which would make a stranger look like the box's own spool:
  - `_find_box_slot_feeding_toolhead` scans every Dryer Box (`logic.py:87-95`);
  - the claimed-slot check (`logic.py:777-781`) reads a PolyDryer spool's blank slot as free.

  Design step 5 below closes that. Without it, this premise doesn't hold.

Consequences:
- **Doubled head:** ejecting the other spool (no B trail) leaves B bound, which is the item C fix.
- **A stale binding that no spool on H carries** (Derek's 2026-09-13 dev observation, PM-DB-1 → XL-1) is never auto-released. Clearing it on an unrelated eject would break "a different spool no longer unbinds it". 42.5c makes it visible, and the existing Unbind clears it.

**Design.**
1. **`locations_db.detach_single_slot_box(box_id, toolhead_id)`** → `bool`.
   - Under `locations_write_lock()`: no-op unless the row is single-slot AND `slot_targets['1']` equals the head.
   - Pops only that key; returns False on a persist failure.
   - Replaces the runtime use of `detach_single_slot_boxes_from_toolhead`. Delete that helper and rewrite its three pins (`tests/test_l271_single_slot_autoattach.py:90-125`), so a toolhead-keyed detach cannot creep back.
2. **`logic._release_single_slot_box(sid, from_loc, pre_extra, printer_map, loc_info_map)`**:
   - gate: `from_loc` is a `printer_map` head, the same gate as attach (`logic.py:742`) and today's detach (`logic.py:1783`);
   - reads the pre-move trail and calls (1);
   - logs INFO `🔓 PM-DB-2 detached from XL-2 — its spool #50 left the head`;
   - returns the released box id or `None`;
   - best-effort `try/except` that logs a WARNING and never fails the move (mirrors attach, `logic.py:801-806`).
3. **Call sites**, each only after the spool's own write succeeded:
   - `perform_smart_eject`: capture `orig_trail = extra.get('physical_source')` right after `extra` is read (`logic.py:1759`), **before** the loop guards and the `""` writes mutate it (`:1799`, `:1809`, `:1880`). Replace both `_detach_single_slot_boxes()` calls (`:1884`, `:1915`) and delete the inner helper.
   - `_perform_smart_move_impl` per-spool loop: after a successful write in PRINTER MOVE (`logic.py:795`), DRYER (`:828`) or GENERIC (`:855`), when `current_loc` (`:699`) is a head and differs from `target`, using `current_extra` (`:701`). Smart Load residents are released inside their own eject, never twice.
   - `perform_force_unassign`: after `logic.py:2067`. This covers Force Location → Unassigned and an archive that still has weight left. A weigh-out to 0 g is released by 42.1b instead.
   - `perform_undo`: see 42.3b.
4. **42.1b — the auto-archive edge.** In `spoolman_api.update_spool`, call (1) directly after a successful PATCH when all of these hold:
   - `_auto_archive_on_empty` just archived the spool (`data.get('archived') and not pre_archived`, `spoolman_api.py:326`);
   - the same update cleared its location (`data.get('location') == ''`);
   - the existing location was a head;
   - the existing trail is a single-slot box.

   Notes:
   - **Where this matters.** This is the path a weigh-out to 0 g takes. Its later `force_unassign` finds the spool already unassigned (see the path table).
   - **An archive that still has weight left is different.** It skips `_auto_archive_on_empty`, which returns while `remaining > 0` (`spoolman_api.py:212`), so the spool keeps its location. The `force_unassign` that follows releases it instead.
   - **The location condition keeps the release honest.** It stops a box being released while its spool is still on the head.
   - **No new import.** `spoolman_api` already imports `locations_db` at module level (`spoolman_api.py:4`).
   - **Cost.** Keep the check on the archive edge only, so the hot path pays nothing.
   - **Rationale:** "by any path". A spool printed to empty has left the head, and the PolyDryer now holds an empty core.
5. **Keep 13.6 away from single-slot boxes.**
   - **The change:** exclude single-slot Dryer Boxes (`locations_db._is_single_slot_dryer_box`) from `_find_box_slot_feeding_toolhead`'s candidates, and compare claimed slots with 42.2's `effective_slot`.
   - **Why:** a single-slot box is attached only by its own spool (the Group 20.2 attach, `logic.py:801-806`), never by reverse binding.
   - **Worked example:** CORE1 runs #60 from PM-DB-4, and CR-MDB-1 slot 1 holds a staged spool. You scan a spare onto CORE1.
     - #60 goes home to PM-DB-4, and CR-MDB-1 slot 1 is claimed.
     - The blank-slot PolyDryer then looks like the only free feed. `loc_list` was read before the eject detached it (`logic.py:502`), so PM-DB-4 still looks bound.
     - Without this step, Group 40.0d's collect-all 13.6 would record the spare as coming from PM-DB-4. A later Return or eject would then land the spare on top of #60, and (2) would treat PM-DB-4 as the spare's box.
   - **Why today's code doesn't hit it:** today's first-match code avoids it only by row order. In dev `data/locations.json`, CR-MDB-1 (row 20) and LR-MDB-1 (row 43) come before PM-DB-1…8 (rows 48-55).
   - Group 40.0d builds on this step.

**Before building: a read-only count.** Run it on dev and prod: a GET of `/api/v1/spool`, with Derek's OK, no writes. It counts two things:
- **Spools on a toolhead with no trail.** This sizes how often a doubled head can't be told apart.
- **Spools NOT on a toolhead that still carry a trail** (the count the spool #99 buglist item asks for). This tests the "the trail is its own spool" premise and sizes the drift.

**Tests (hermetic, real engine, real in-memory `locations.json`).** Seed PM-DB-2 slot 1 → XL-2 and #50 on XL-2 with trail `PM-DB-2`.

Released:
- eject return-home;
- eject no-home (`confirmed_unassign`);
- Smart Load onto XL-2 from LR-MDB-1 slot 2 (#50 unloads);
- `/api/quickswap/return` through the Flask client;
- `perform_smart_move('CR', [50])`;
- `perform_smart_move('LR-MDB-1', [50], target_slot='4')`;
- `manage_contents add` (Force Location) through the Flask client;
- `perform_force_unassign(50)`;
- `WireSpoolman.update_spool(50, {'used_weight': <initial>})` (the auto-archive edge through the REAL `update_spool`);
- the weigh-out sequence: `update_spool(50, {'used_weight': <initial>, 'archived': True})`, then `perform_force_unassign(50)`. The box is released once, by the archive edge, and the second call finds nothing to release.

Never recorded:
- step 5's worked example (CORE1 running #60 from PM-DB-4, CR-MDB-1 slot 1 staged, a spare scanned onto CORE1) → the spare gets no trail, and PM-DB-4 is never a 13.6 candidate.

Stays bound:
- a doubled head (#60 with no trail) — eject #60 → PM-DB-2 still → XL-2 (the I5-15 regression test);
- a refused eject (`REQUIRE_CONFIRM`) — keep `test_refused_eject_leaves_the_single_slot_box_bound` (`tests/test_active_print_chain_confirm.py:743`);
- a rejected spool write;
- a multi-slot trail (#240 from LR-MDB-1:2) leaving XL-2 → no `locations.json` save at all.

Also:
- rewrite `test_successful_eject_detaches_the_box_after_the_spool_write` (`:761-779`) to the spool-keyed helper: its `returns-home` case uses a MULTI-slot trail and must now assert *no* detach; add a PM-DB-2 case;
- parametrize the matrix over **PM-DB-2 and a non-`PM` box `SD-DB-1`** (42.7).

**Risks.**
- More `locations.json` writes per move. Each is a no-op read-then-return unless a single-slot binding actually matches; saves happen only on a real release.
- A persist failure leaves the box bound: logged, visible (42.5c), recoverable with Unbind.
- `update_spool` is the most-called write in FCC: keep the new branch behind the archive edge and inside `try/except`, and keep `LAST_SPOOLMAN_ERROR` handling untouched.
- **Same functions as sibling groups.** The release call sits after each successful write, so it survives all of these changes, but merge carefully:
  - Group 39.6 combines the eject's two confirms inside `manage_contents remove`, and deliberately leaves `perform_smart_eject`'s return contract unchanged (42.5a relies on that);
  - Group 41.8 edits the no-home branch (`logic.py:1890-1905`);
  - Group 41.2 reworks `clear_location`'s per-spool results.

---

## 42.2 — A single-slot box's spool is in slot 1 (code-traced, confirm first)

**Found while scoping; not yet seen in the UI.**
- A spool stored in a PolyDryer by box-label scan lands with **no slot**:
  - L124 treats Max 1 as single-occupancy and sends `slot: null` (`inv_cmd.js:1683-1689`);
  - auto-slot runs only for Max > 1 (`logic.py:559`);
  - the DRYER branch writes `container_slot ""` (`logic.py:737-739`).
- When that spool is deployed, `_ghost_trail_from` copies the blank slot into its trail (`logic.py:384`), so its ghost item in PM-DB-2 has slot `""` (`spoolman_api.py:1361`, `:1486-1488`).
- The Quick-Swap grid only maps items with a non-empty slot (`inv_quickswap.js:160-166`). XL-2's grid therefore most likely shows **PM-DB-2 Slot 1 as an empty (or "Deposit from buffer") tile while its spool is loaded on XL-2**.
- `/api/quickswap` on that tile looks for slot `1` (`logic.find_spool_in_slot`, `logic.py:2375-2391`) and answers `quickswap_empty_slot`.
- Bulk move already works around the same blank (`logic.py:1244-1255`: "One capacity => the spool IS in slot 1").
- Group 40.0c needs the same normalization to tell a same-slot swap from "fed elsewhere".

**Design.**
- **Write time:** in the DRYER branch, when the target row is single-slot and no slot was given, write `container_slot "1"`.
- **Read time**, for legacy rows: one helper `locations_db.effective_slot(box_row, slot)` that returns `"1"` for a single-slot box with a blank slot, used in:
  - `find_spool_in_slot`;
  - the eject return-home slot restore (`logic.py:1844-1877`);
  - the Quick-Swap `slotMap` (`inv_quickswap.js:160-166`), where the model can carry `single_slot` from `get_bindings_for_machine` (42.5c);
  - every other place that compares an occupant's slot string with a slot:
    - the slot-assignment unseat (`logic.py:720`);
    - the 13.6 claimed-slot check (`logic.py:777-781`; see 42.1 step 5);
    - the eject slot-collision check (`logic.py:1860`);
    - Return's taken-slot check (`routes_bindings.py:690-693`);
  - Bulk Move's own copy of "one capacity means slot 1" (`logic.py:1244-1255`). Replace that copy with the helper, so there is one rule.
- Group 40 uses the same helper, for 40.0c's same-slot comparison, 40.0d's claimed check and 40.1's placement model.

**Tests.**
- Hermetic: `perform_smart_move('PM-DB-2', [50])` → `container_slot "1"`; deploy → trail slot `"1"`; `find_spool_in_slot('PM-DB-2', '1')` finds a legacy blank-slot ghost.
- Route-stubbed E2E: a stubbed XL-2 grid with a blank-slot PM-DB-2 ghost renders the spool card, not "empty".

**Risk.** Behaviour change for a *second* spool placed into an occupied PolyDryer: the slot-assignment unseat (`logic.py:716-736`) now sees slot `1` and unseats the first spool to slotless. Both spools still sit in the box either way. A Max-1 box has never refused a second spool, and that remains out of scope (worth filing standalone if Derek wants it).

---

## 42.3 — One loaded spool per toolhead: the engine guards (items D, E, H)

### 42.3a Refuse several spools onto a single-occupancy target (item E)

**Today.** `/api/smart_move` passes the list through (`print_deduct.py:253-262`). The per-spool loop writes every spool (`logic.py:688-862`). Smart Load only unloads residents (`logic.py:605-678`). The only trim is the frontend L124 check (`inv_cmd.js:1677-1687`). A raw location string also expands to every spool there (`logic.py:506-510`).

**Design.** Right after `is_printer` / `is_toolhead` are known (`logic.py:582-591`) and before Smart Load: if either is true and `len(spools) > 1`, answer `{"status": "error", "blocked_reason": "single_occupancy", "msg": "XL-1 holds one spool — move them one at a time (got 2)", "failures": {sid: msg for each}}` and write nothing. It matches Bulk Move's single-occupancy block (`logic.py:1061-1064`, `BULK_MOVE_SINGLE_OCC_MSG` at `:976`). The chain already sends one spool (`logic.py:902`).

**Tests.**
- Flask client `/api/smart_move {location: 'XL-1', spools: [42, 43]}` → refused, zero writes.
- `perform_smart_move('CORE1', [42, 43])` → refused.
- `perform_smart_move('XL-1', ['LR-MDB-2'])` where LR-MDB-2 holds two spools → refused.
- One spool is unaffected.
- `performContextAssign`'s else-branch shows `msg` for 7 s (`inv_cmd.js:1948`).

### 42.3b Undo: occupancy check on the moves restore, and the box lifecycle (item D)

**Today.**
- The ejections restore checks the head is free (`logic.py:2124-2149`, added 2026-09-12).
- The **moves** restore does not (`logic.py:2096-2111`): move #77 off XL-1, let a non-recording writer put #42 on XL-1, then `CMD:UNDO` → XL-1 holds [42, 77] and undo says success (I5-10).
- Undo never touches single-slot bindings.

**Design.**
- Before restoring a move onto a single-occupancy location (`_is_single_occupancy`, `logic.py:356-365`):
  - strict-read its direct occupants, excluding the spool itself, with the same code shape as `:2129-2149`;
  - if any is there or the read raises → skip that restore, ERROR-log it, and add it to `blocked_restores` (already returned as `success: False` at `:2201-2203`).
- **Release:** if the spool is currently on a head (re-read before restoring) and the restore takes it elsewhere, run `_release_single_slot_box` with its current trail. Example: undo of a PolyDryer deploy puts #50 back in PM-DB-2 and PM-DB-2 lets go of XL-2.
- **Attach:** if the restore puts a spool onto a head and its snapshot trail (`extras`, `ejection_extras`) is a single-slot box → `attach_single_slot_box_to_toolhead`. Example: undo of "#50 moved XL-2 → shelf" puts #50 back on XL-2 and PM-DB-2 re-binds.
- **Reporting and frontend: owned by [Group 41.4](41-honest-bulk-results.md).** 41.4 collects failed and blocked restores into one `success: false` answer, stops recording undo for writes that never landed, and makes `triggerUndo` (`inv_cmd.js:1953`) toast the result. This group's blocked restores feed that same list. If 42 lands first, add only a 7 s toast of `msg` when `success` is false, and let 41.4 replace it.
- **Group 41.4 also edits these restore loops.** It adds D6's printing-head ask, through Group 39's `_uncovered_active_heads`, by default. There is no logic dependency; whichever lands second merges the loops.

**Tests (real engine).**
- The I5-10 sequence → undo refused, XL-1 == [42], ERROR names #77.
- Undo of a PM-DB-2 → XL-2 deploy → #50 in PM-DB-2 and the binding cleared.
- Undo of #50 XL-2 → CR → #50 on XL-2 and PM-DB-2 → XL-2 restored.
- The three existing undo tests still pass (`tests/test_active_print_chain_confirm.py:786-869`).

### 42.3c Auto-unarchive never puts a spool back onto an occupied head (item H)

**Today.**
- A print deduct that drives a loaded spool to 0 g auto-archives it, plants `fcc_pre_archive_location = <toolhead>` and unassigns it (`spoolman_api.py:215-241`).
- Any later weight correction on that spool (weigh-out, quick-weigh, wizard, `/api/spool/update`) auto-unarchives it and writes `location = <toolhead>` (`spoolman_api.py:282-287`), with no occupancy read and only an INFO log (`:338-346`). If another spool was loaded there meanwhile, the head now holds two (I5-9).

**Design.**
- In `_auto_unarchive_on_refill`, when the breadcrumb names a single-occupancy location (a `printer_map` head, or a row whose Type is a toolhead type or `Printer`):
  - strict-read its direct residents (`get_spools_at_location_detailed_strict`);
  - empty → restore there, as today;
  - occupied, or the read raises → restore to the Room its printer sits in, else Unassigned (the rule Derek chose for a homeless Smart Load resident on 2026-09-12), and log a WARNING such as `📤 Auto-unarchived #77 — XL-1 now holds #42, so it went to Room LR instead`.
- `spoolman_api` must not import `logic` (circular).
  - Move `logic._known_room_of` (`logic.py:387-405`) into `locations_db` as `known_room_of`, and have `logic` call `locations_db.known_room_of` (module-qualified, per CLAUDE.md).
  - No test patches `logic._known_room_of` as of `be9f045`. Grep again before moving it, in case that has changed.
- **Wait for [Group 41](41-honest-bulk-results.md)'s Q1, and its Smart Load follow-up, before building this sub-task.**
  - The Room default comes from Derek's 2026-09-12 rule, which was chosen for a spool Smart Load pushes off a head beside its printer.
  - An auto-unarchived spool is different: an old, emptied spool whose weight was corrected later. It is probably not beside the printer.
  - Sending it to `LR` creates exactly the Room-only spool D4 calls hard to find.
  - Build the redirect to whatever 41's Q1 lands, through the one shared resolver (`locations_db.known_room_of`), rather than retrofitting it afterwards.
- **The deduct-to-0 archive itself stays unguarded.** It runs from the print-monitor daemon, where nobody can answer a prompt, and archiving an empty spool is correct. This group only makes that edge release the spool's single-slot box (42.1b).

**Tests (hermetic, `WireSpoolman`, real `update_spool`).**
- Archived #77 with breadcrumb `XL-1`, XL-1 empty, refill → `location XL-1`.
- XL-1 holds #42 → the PATCH body sets the destination Group 41's Q1 chose (the printer's Room, or `""`), a WARNING names #42, and XL-1 still holds only #42.
- The strict read raises → not restored onto XL-1.
- A breadcrumb naming a shelf → restored there with no occupancy read (the read is only for single-occupancy rows).

**Risk.** `update_spool` is the most-called write in FCC. The new read runs only on the unarchive edge (`pre_archived and data.get('archived') is False`, `spoolman_api.py:338`), which is rare.

---

## 42.4 — Visibility: "N spools" on a single-spool head (item F)

**Today.**
- The printer-status pulse picks `contents[0]` per head (`routes_state_pulse.py:364-365`), and `contents` includes ghosts (`:351-352`).
- The client-side fallback aggregator does the same with `items[0]` (`inv_printer_status.js:117-118`).
- The tile renders one spool (`inv_printer_status.js:164-250`).
- The toolhead's Location Manager list renders every card (`renderList`, `inv_loc_mgr.js:999`).
- The deduct warns and skips an ambiguous head (`print_deduct.py:320-325`).
- A second loaded spool is therefore visible only in the Location Manager, and only if you think to look.

**Design ("loaded" vs "feeding").**
- **The tile shows the one LOADED spool**:
  - pulse and client aggregator pick `(direct or contents)[0]`, where `direct` = items that are not ghosts;
  - add `loaded_count` and, when above 1, `loaded_ids`;
  - include `loaded_count` in the widget fingerprint (`inv_printer_status.js:133-140`) so it repaints.
- **When `loaded_count > 1`:**
  - the tile adds a chip `⚠️ 2 spools` with an **opaque** dark background (the contrast guard mis-reads translucent backgrounds, sweep-triage item 1);
  - the chip title reads *"XL-2 holds #42 and #50 — a toolhead holds one spool. Open XL-2 and eject the one that isn't loaded."*;
  - the head's Location Manager view gets the same message as a banner above its cards.
- **Feeding stays where it already is.** The Quick-Swap grid under the head lists the box slots that feed it, with 42.5c's "attached" label. Nothing about feeding moves onto the tile.

**Tests.**
- Hermetic `_pulse_section_printer_status`, with `bucket_spools_by_location`, `get_active_printer_map`, `get_bindings_for_machine` and `prusalink_api.get_printer_state` patched on their defining modules:
  - ghost first then direct → `item` is the direct spool;
  - two direct → `loaded_count 2`, `loaded_ids`;
  - one → no `loaded_ids`.
- Route-stubbed E2E: a stubbed `/api/dashboard_pulse` with `loaded_count: 2` shows the chip and passes `test_contrast_guard`'s checker; a stubbed `/api/get_contents` for XL-2 with two direct items shows the banner.

**Risk.** Preferring a direct spool over a ghost changes which spool a tile shows only when a legacy toolhead-valued trail exists (0 on dev per R1-04). That is the intended fix.

---

## 42.5 — Say what eject did, and show what is attached (item G)

### 42.5a Eject result names the destination and the released box (G(a))

**Today.**
- The eject toast is `"Ejected"` (`inv_loc_mgr.js:1560`).
- The route answers a bare `{"success": true}` (`routes_scan.py:311-312`).
- The destination and the detach exist only in the Activity Log (`logic.py:1883`, `:1914`, `:1788-1790`).

**Design.**
- `perform_smart_eject(..., report=None)`: on success, fill the caller's dict with `{"from": "XL-2", "to": "PM-DB-2" | "LR" | "", "slot": "1" | "", "released_boxes": ["PM-DB-2"]}`.
- **The return contract does not change** (True / False / `"REQUIRE_CONFIRM"` / a dict). Callers test `is True` (`logic.py:654`, `routes_scan.py:311`), and a new return type would re-open the truthy-refusal class.
- `manage_contents remove` passes a dict and returns `{"success": true, **report}`.
- `doEject` toasts one of:
  - `⏏️ #50 → back in PM-DB-2 (PM-DB-2 detached from XL-2)`
  - `⏏️ #50 → Room LR`
  - `⏏️ #50 → Unassigned`
- The toast is 4 s (success). The eject-mode spool scan uses the same `doEject` (`inv_cmd.js:1722` → `inv_loc_mgr.js:1511`), so it inherits it.
- Rewrite the log line to name the spool: `🔓 PM-DB-2 detached from XL-2 — its spool #50 left the head`.
- **Coordinate with Group 39.6**, which makes `doEject` send both confirm flags on one Yes and rewords `manage_contents remove`'s prompt. The `report` fields ride on the final success answer, so the two compose; whichever lands second merges `doEject`'s success branch.

**Tests.**
- Flask client `manage_contents remove` for #50 → body has `to: PM-DB-2`, `released_boxes: [PM-DB-2]`; the store shows the binding gone.
- A spool with no box trail → `released_boxes: []`.
- Route-stubbed E2E: the toast text for the card eject and for an eject-mode spool scan.

### 42.5c Show a single-slot box's attachment on the toolhead view (G(c))

**Today.** The toolhead's Quick-Swap grid already lists every box slot bound to the head, single-slot boxes included (`locations_db.get_bindings_for_machine`, `locations_db.py:1771-1829`; render `inv_quickswap.js:168-251`). Without 42.2 the PolyDryer tile reads empty, and nothing tells a lifecycle attachment apart from a user binding.

**Design.**
- Add `single_slot: true` to single-slot entries in `get_bindings_for_machine` (`locations_db.py:1818-1820`).
- The grid labels such a tile **`🔗 attached — follows #50`** when a spool whose trail is that box is on this head.
- When no spool on the head carries the box (a stale attachment, like Derek's dev PM-DB-1 → XL-1), the grid shows **`🔗 attached, but its spool isn't on XL-1`** with an **Unbind** button. The button reuses the single-slot binding PUT (`routes_bindings.py:466-518`), as the bind picker's Unbind does (`inv_quickswap.js:1054-1091`).
- Depends on 42.2.

**Tests.** Hermetic: `get_bindings_for_machine` marks PM-DB-2 `single_slot` and leaves LR-MDB-1 unmarked. Route-stubbed E2E: "attached — follows" and the stale variant render; Unbind posts `{target: null}`.

### 42.5b What a LOCATION scan in eject mode means (G(b)) — **Q-B**

**Today.**
- `CMD:EJECT` arms eject mode (`inv_cmd.js:1429`, `:106`), but only the spool branch honours it (`inv_cmd.js:1722`).
- A location scan ignores it:
  - with a buffered spool, scanning a head **assigns** that spool to the head while eject stays armed (`inv_cmd.js:1659-1693`);
  - with an empty buffer, it Quick-Picks the head's spool into the buffer (`inv_cmd.js:1694-1702`).

**Until Derek answers Q-B:** in eject mode a location scan does nothing, and warns for 7 s: *"Eject mode ejects spools — scan the spool's label, or turn eject mode off"*. The same text goes to the Activity Log. This is the safe minimum: it stops the surprise assign.

**Where this sits: the location-scan check order, written once here.** Group 40 builds on it.
- Four changes edit the same `inv_cmd.js` location branch (`:1652-1719`): 42.5b's guard, Group 40.2's box picker, and 40.5's Printer picker and `LOC:XL` Quick-Pick.
- Land 42.5b before Group 40 touches the branch. The recommended order (39 → 41 → 42 → 40) does that.
- 42.5b could live in Group 40 instead. It stays here because its question (Q-B) comes from this group's item G.

The order a location scan must take:
1. **In the browser, before the scan reaches the server:**
   - `routeConfirmScan`;
   - then 40.1's `routePickerScan` (an open picker claims the scan);
   - then the `CMD:` intercepts (`inv_cmd.js:1408-1442`).
2. **On the server:** an armed bulk-move session consumes every location scan as its source or destination (`routes_scan.py:891`), and none of the steps below run. 40.1 never opens a picker during a session.
3. **In the location branch:**
   - **eject mode** (42.5b);
   - the legacy-label warning (informational only);
   - a double scan opens the manager (`:1658`).
   - **With a buffered spool:**
     - the Wall Shelf / Row refusal (`:1672-1676`);
     - the **multi-slot box picker** (40.2);
     - the **Printer picker** (40.5);
     - the one-spool trim (`:1683-1687`, backed on the server by 42.3a);
     - context assign.
   - **With an empty buffer:**
     - **Quick-Pick**, under 40.5's direct-resident rule (`:1694-1702`);
     - the empty-location warning;
     - open the manager.

---

## 42.6 — Head → head: does the box follow its spool? — **Q-A**

**Today.** A spool moving XL-2 → XL-4 gets no trail from `_ghost_trail_from` (`logic.py:382-383`), because a toolhead is never a home (2026-09-12). The PolyDryer trail is lost with it. The 13.6 reverse-binding may then record XL-4's free bound slot (`logic.py:767-793`). Attach does not fire, since the spool did not come from a box (`logic.py:802`).

**Decided part (42.1):** PM-DB-2 is released from XL-2.

**Pending Q-A:** whether PM-DB-2 re-binds to XL-4 and #50 keeps PM-DB-2 as its home. If yes, the change is narrow: in the PRINTER MOVE branch, when the spool comes from a head and its old trail is a **single-slot** Dryer Box, keep that trail and attach the box to the new head. Head-valued and multi-slot trails keep today's behaviour. **Default until answered:** release only.

**Tests (whichever answer):**
- #50 XL-2 → XL-4 with trail PM-DB-2 → PM-DB-2 not bound to XL-2;
- (if yes) bound to XL-4, and #50's trail is PM-DB-2;
- a multi-slot trail is unchanged.
- `test_head_to_head_move_takes_the_new_heads_bound_box` (`tests/test_active_print_chain_confirm.py:637`) stays green.

---

## 42.7 — How a future non-Polymaker single-spool dryer inherits all of this

Nothing here keys on the `PM` prefix or on Polymaker. To add, say, a SUNLU single-spool dryer:
1. Create a location with **Type `Dryer Box`** and **`Max Spools` = `1`**, under a real Room (for example `SD-DB-1`, parent `LR`).
2. Print its box label. Single-slot boxes skip Group 40's slot picker (it opens only for Max > 1), so the box label stays the one-scan way in.
3. Scan a spool into it, then load that spool onto a head as usual. The box attaches (`logic.py:801-806`), shows as "attached" on the head (42.5c), and releases when that spool leaves the head by any path (42.1).

Caveats:
- **Use `1`, not `0`.** `_is_single_slot_dryer_box` treats `0` as single-slot today (`locations_db.py:1623`), but Group 37's fork 4 defines `0`/blank as "no cap" for locations. Flag this for Group 37, and write `1` meanwhile. This is the one place the flag lives; Group 40's Group 37 overlap section links here.
- **Blank `Max Spools` is not managed at all** (fail safe, `locations_db.py:1619-1621`).
- A two-spool dryer is a *multi-slot* box: its slots are wired to heads in the Feeds editor and never change on their own.

**Pin it:** parametrize the 42.1 lifecycle matrix over `PM-DB-2` and `SD-DB-1`, so a future prefix check fails a test.

---

## 42.8 — Docs

- **CLAUDE.md "Spool / Filament write surfaces" table:**
  - `perform_smart_eject`: spool-keyed release after the write, `report`;
  - `perform_force_unassign`: now releases;
  - `perform_undo`: moves-restore occupancy check, attach/release;
  - `_perform_smart_move_impl`: release after a move off a head, single-occupancy multi-spool refusal;
  - `spoolman_api.update_spool`: auto-archive releases a single-slot box; auto-unarchive never restores onto an occupied head.
- **CLAUDE.md "Dryer Box ↔ Toolhead Bindings":** add the single-slot lifecycle rule, and "use Max Spools 1 for a single-spool dryer".

---

## Dependencies and build order

| Relation | Detail |
|---|---|
| **Before [Group 40 (slot picker)](40-slot-picker.md)** | Both edit `_perform_smart_move_impl` (Smart Load block `logic.py:605-678`, PRINTER MOVE `:742-816`). **Build 42 first.** Group 40 builds on four pieces from here: <br>• 42.2's slot-1 normalization, for 40.0c's same-slot comparison; <br>• 42.1 step 5's 13.6 single-slot exclusion, for 40.0d; <br>• the stateful locations store, for its tests; <br>• 42.5b's scan-branch order, for 40.2 and 40.5. |
| **[Group 39 — Confirm on Every Door](39-confirm-on-every-door.md)** | Build 39 first. From it this group uses: <br>• 39.1's shared test harness (`tests/move_engine_harness.py`) and the pre-write contract; <br>• 39.4's source-side check in the same pre-flight; <br>• 39.6, which combines the eject confirms in the route and keeps the eject return contract unchanged (42.5a relies on that); <br>• 39.7's fail-closed resident read (R1-03). |
| **[Group 41 — Honest Bulk Results](41-honest-bulk-results.md)** | **Build 41 before 42.** <br>• 41.4 owns Undo reporting and the `triggerUndo` toast; 42.3b's blocked restores feed that list instead of a fallback toast. <br>• 41's Q1 decides where a homeless spool goes, and 42.3c waits for it. <br>• 41.2 reworks Eject All's per-spool results. <br>If Derek wants this group first, swap them: 42.3b uses its fallback toast, and 42.3c still waits for Q1. |
| `fix/core1-return-ejectall-guard` (`1fb5678` + `76398cb`, local only) | Edits the Return route and `clear_location`, both of which 42.1's release reaches. Merge to `dev` first. |
| `test/sweep-reds-hermetic` (`d785444`, local only) | Fixes the PM-DB-1 E2E fixtures. Merge to `dev` first. Don't add new fixtures that borrow a real dev box. |
| Group 22 | 42.1b releases a box on the deduct-to-0 archive edge, which runs inside the print-monitor daemon's `_apply_usage_to_printer`. 42.4's two-spool chip complements `select_deduct_targets`' skip of an ambiguous head (`print_deduct.py:319-327`). |
| Group 37 | `Max Spools = 0` meaning for Dryer Boxes (42.7). |

**Recommended order across the four groups:** 39 → 41 → 42 → 40 (see Cross-plan notes).

**Order inside the group:** 42.1 (+ pin rewrites) → 42.2 → 42.3a → 42.5b (its safe default; the Q-B answer when it comes) → 42.3b (after, or alongside, 41.4) → 42.3c (after 41's Q1) → 42.5a → 42.4 → 42.5c → 42.6 once Derek answers Q-A → 42.8. Run the offline suite after each commit, and the full sweep before merging to `dev`.

---

## Cross-plan notes (Groups 39–42, reviewed 2026-09-13)

### Recommended build order across the four groups

The full reasoning is in [Group 39's Cross-plan notes](39-confirm-on-every-door.md).

0. **Merge the prerequisite branches into `dev`:** `fix/core1-return-ejectall-guard` (`1fb5678`, `76398cb`) and `test/sweep-reds-hermetic` (`d785444`). Both are local only.
1. **Ask Derek the three contract-shaping questions first:**
   - Group 41's Q1: where a spool with no home goes. This gates 42.3c.
   - Group 39's Q1: the confirm component's keyboard default.
   - This doc's **Q-B**: what a location scan does in eject mode. This fixes the scan-branch order in 42.5b.
2. **Group 39**, then **Group 41**, then **Group 42** (this group), then **Group 40**.

### Overlaps that concern this group

**The pre-write contract.**
- Group 39.1 defines the order of `_perform_smart_move_impl`'s pre-write section, and the one `requires_confirm` shape.
- 42.3a's `single_occupancy` refusal is its step 2. 42.1's release and 42.2's slot 1 sit in its step 6.
- Extend that contract; don't redefine it.

**`perform_smart_eject`'s answer.**
- 39.6 keeps the return contract unchanged, and 42.5a's `report` dict relies on that.
- 41.2 (per-spool lists) and 41.8 (the no-home branch) also edit it.
- The release call after each successful write survives all three.

**The 13.6 single-slot exclusion (42.1 step 5).** Group 40.0d's collect-all reverse binding needs it. Land it here first.

**One effective-slot helper (42.2).** Group 40 also uses it: 40.0c (same-slot swap vs fed from elsewhere), 40.0d, and 40.1's placement model.

**One strict "direct residents" reader, built in 39.7.**
- It serves 42.3b's Undo moves restore (the same shape as `logic.py:2136-2140`) and 42.3c's auto-unarchive check.
- Don't add a second copy.

**One no-home resolver.**
- 42.3c moves `logic._known_room_of` into `locations_db.known_room_of`.
- Group 39.6's `_eject_destination` and Group 41.8 use the same resolver.
- 41.8 decides whether `get_room_from_location` (`logic.py:1713-1735`) moves behind it too.

**The test harness.** 39.1 extracts `tests/move_engine_harness.py`. This group adds the stateful in-memory locations store, and Group 40 reuses it.

**`perform_undo` (`logic.py:2076-2204`).** 42.3b and Group 41.4 (honest reporting plus the D6 ask) edit the same loops. Whichever lands second merges.

**`spoolman_api.update_spool`.**
- 42.1b (the archive-edge release) and 42.3c (the unarchive redirect) are the only new branches in FCC's most-called write.
- The archive edge also runs inside the print-monitor daemon's `_apply_usage_to_printer`, which is Group 22's surface.
- Keep both branches behind their edges and inside `try/except`.

**The `inv_cmd.js` location branch (`:1652-1719`).** Group 40.2 and 40.5 build on 42.5b's check order.

**The Return route.**
- It is also touched by the core1 branch, 39.2, 39.8 and 40.6.
- 42.1's Return release sits after the write, so rebase it after 39.2.

**Group 22.**
- 42.1b runs on the deduct-to-0 archive edge.
- 42.4's two-spool chip complements `select_deduct_targets`' skip of an ambiguous head (`print_deduct.py:319-327`).
- The unblocked 22.5 recommended alongside Group 39.4 doesn't touch this group's code.

**Group 37.** A Dryer Box with `Max Spools "0"` counts as single-slot here (`locations_db.py:1619-1623`), while 37's fork 4 says `0` means "no cap". The flag lives in 42.7.

**The read-only count (42.1).** Spools on a head with no trail, and non-head spools with a trail. Group 40.0c and 41.3 want the same numbers, so do it once.

**Shared test pins.**
- `test_l271_single_slot_autoattach.py:90-125` (42.1 rewrites these).
- `test_active_print_chain_confirm.py`:
  - `:743` and `:761-779` (42.1);
  - `:637` (42.6; also 40.0d);
  - `:786-869` (42.3b; also 41.4).
- `test_contrast_guard` (42.4's opaque chip, together with the sweep branch's compositing fix).

---

## Test conventions for this group

- **Allowed command** (from `inventory-hub/` in the group's worktree): `"C:/Python314/python.exe" -m pytest <paths> -p no:cacheprovider -q --offline`. Route-stubbed E2E files skip there and run in the full pre-merge sweep.
- **Shared harness.** Group 39.1 extracts `FakeSpoolman`, `WireSpoolman`, `_probe_for` and `_run` from `tests/test_active_print_chain_confirm.py` (`:114-305`) into `tests/move_engine_harness.py`. Reuse it (create it under that name if 42 is built first). This group adds:
  - **a real in-memory locations store**: patch `locations_db.load_locations_list` / `save_locations_list` over one mutable list, so the real attach / detach / release helpers run and binding state is observable across hops (the `_patch_locs` pattern, `tests/test_l271_single_slot_autoattach.py:16-26`, made stateful);
  - the probe patched below the per-move memo (`prusalink_api._probe_printer_state`);
  - `WireSpoolman` for anything that relies on the real extras merge or the auto-archive edge.
- **Real engine only.** Never mock `perform_smart_move`, `perform_smart_eject` or the binding helpers in a lifecycle test.
- **Prove fail-on-HEAD** for every new hermetic test (`git archive HEAD inventory-hub` into scratch, run the new file), and record the reason in the commit message.
- Change existing pins deliberately, in the same commit, with the reason in the docstring.
- Python 3.9 syntax; module-qualified collaborator calls; patch private helpers on their defining module (CLAUDE.md).

---

## Manual checks for Derek (add to the handoff checklist)

Dev container. Dev spools are virtual test constructs (your standing rule), but box bindings in `locations.json` still get your OK. Rows L0 and L5 need a small setup.

| # | Check | Steps | Pass if |
|---|---|---|---|
| L0 | **Confirm the PolyDryer tile finding** — *before building 42.2* | Put a spool into PM-DB-2 by scanning PM-DB-2's label, then load it onto XL-2 (scan the spool, then the XL-2 QR). Open XL-2 and look at its Quick-Swap grid | **Expected today (the bug):** the PM-DB-2 Slot 1 tile reads empty or "Deposit from buffer" although the spool is on XL-2. After the fix: it shows the spool, labelled "attached — follows #N" |
| L1 | **Eject says what happened** | Eject that spool from XL-2's card | The toast says it went back to PM-DB-2 and that PM-DB-2 detached from XL-2; PM-DB-2 disappears from XL-2's grid |
| L2 | **Return releases the box** | Reload it onto XL-2, then Quick-Swap **↩️ Return to Slot** on XL-2 | Spool back in PM-DB-2; PM-DB-2 no longer attached to XL-2 |
| L3 | **Any move releases the box** | Reload it onto XL-2. Pick it up from XL-2's view, then scan a shelf label | Spool on the shelf; PM-DB-2 detached; the Activity Log line names the spool |
| L4 | **Force Location releases the box** | Reload it onto XL-2, then Force Location → a Room | Same as L3 |
| L5 | **The other spool doesn't unbind it** | Reload the PM-DB-2 spool onto XL-2. In dev Spoolman's web page, set a second spool's location to `XL-2` | The status bar shows **⚠️ 2 spools** on XL-2, and XL-2's view shows the banner. Eject the *second* spool: PM-DB-2 stays attached, and the chip goes away |
| L6 | **Printed to empty** | With the PM-DB-2 spool on XL-2, weigh it out to 0 g | Spool archived and unassigned; PM-DB-2 detached (the archive edge releases it, 42.1b) |
| L7 | **Undo won't stack two spools** | Move a spool off XL-1 to a shelf. In dev Spoolman's web page, put a different spool on XL-1. Scan `CMD:UNDO` | A 7 s message says it could not put the first spool back; XL-1 still holds one |
| L8 | **Undo follows the box** | Load the PM-DB-2 spool onto XL-2, then `CMD:UNDO` | Spool back in PM-DB-2, and PM-DB-2 not attached to XL-2 |
| L8b | **A refill never doubles a head** | Weigh a spare spool that is loaded on XL-1 out to 0 g (it archives and leaves XL-1). Load a different spool onto XL-1. Then correct the first spool's weight back up with quick-weigh | The first spool comes back where you told Group 41's Q1 a spool with no home should go (the printer's Room, or Unassigned), with a warning, not onto XL-1. XL-1 still holds one |
| L9 | **A future dryer works the same** (optional) | Create Dryer Box `SD-DB-1` with Max Spools **1** in LR. Put a spool in, load it onto XL-5, eject it | Attaches, then detaches, exactly like a PolyDryer (delete the row afterwards if you like) |
| L10 | **Eject mode + location scan** (after Q-B) | Scan `CMD:EJECT`, then the CORE1 label, with CORE1 loaded | Behaves as you chose in Q-B. Until then: a warning, and nothing is assigned or picked up |
| L11 | **Head to head** (after Q-A) | Load the PM-DB-2 spool onto XL-2, pick it up, scan XL-4's QR | Behaves as you chose in Q-A. PM-DB-2 is never still attached to XL-2 |

---

## Open questions for Derek

### Q-A — When a PolyDryer spool moves from one head to another, does the PolyDryer follow it? — ✅ ANSWERED 2026-09-18: option (a), with a caveat

**Derek chose (a): the box follows.** His caveat, which needs a design answer BEFORE this is built: "we shouldn't overwrite the spool location before the box load. (Say it was on a cart or something, so that if we unload it from the box, we know where it was before and move it back to that location.)"
- Today `physical_source` holds one level only, so a spool that came from a cart into a PolyDryer and then onto a head has lost the cart.
- Options to put to him: a home chain (the box in `physical_source`, plus a separate "before the box" field), or a general "last non-container location" recorded on every move.
- Coordinate with Group 40's "record it as coming from" prompt, which is where a second level would be captured or shown.

**Background.** Your rule says a single-slot box lets go when its own spool leaves the head, so PM-DB-2 releases XL-2 either way. The open part is what happens at the NEW head. Today a head-to-head move deliberately forgets where the spool came from, because remembering "it came from XL-2" once caused spools to be sent back onto the wrong head. That also forgets the PolyDryer.

**Where you'd meet it.** Picking a PolyDryer-fed spool up from one XL head and scanning another head's QR, or moving it from an XL head to CORE1. In practice the PolyDryer sits next to the printer and moves with the spool.

**Worked example.** #50 lives in PM-DB-2 and is loaded on XL-2 (PM-DB-2 attached to XL-2). You pick #50 up from XL-2 and scan XL-4's QR.
- **(a) The box follows (recommended).** PM-DB-2 attaches to XL-4, and #50 still remembers PM-DB-2 as home. Ejecting #50 later puts it back in PM-DB-2, and XL-4's grid shows "attached — follows #50".
- **(b) Release only.** PM-DB-2 is unattached. #50's home becomes LR-MDB-2 slot 1 (the free slot that feeds XL-4) or nothing. Ejecting #50 later would send it to LR-MDB-2 slot 1, not back into the PolyDryer.

**Default if unanswered:** (b), because it is only the part you already decided.

### Q-B — What should scanning a LOCATION do while eject mode is on? — ✅ ANSWERED 2026-09-18: option (a)

**Derek chose (a): eject that head's one loaded spool**, with the same confirms as the eject button, and warn-and-do-nothing on a box, shelf or room, or on a head holding 0 or 2 spools. Build 42.5b that way; the background below is kept for the record.

**Background.** `CMD:EJECT` turns on eject mode, but today only spool labels honour it. Scanning a toolhead label in eject mode either *assigns* whatever is in your buffer to that head (eject mode stays on), or, with an empty buffer, picks the head's spool up into the buffer. So the "scan eject, then scan the Core One label" you tried on 2026-09-12 most likely did not eject by itself. Whatever eject happened after that is what detached the PolyDryer.

**Where you'd meet it.** Blind-scanning an unload: eject, then the head's QR.

**Worked example.** CORE1 is running #60 from PM-DB-4. You scan `CMD:EJECT`, then the CORE1 label.
- **(a) Eject that head's loaded spool (recommended).** Same confirm as the eject button (the printing prompt if CORE1 is printing). #60 goes back to PM-DB-4, PM-DB-4 detaches, and the toast says both. On a box, shelf or room, or a head holding 0 or 2 spools, it warns and does nothing.
- **(b) Locations never act in eject mode.** Always warn: "eject mode ejects spools — scan the spool's label".
- **(c) Keep today's behaviour** (assign or pick up).

**Default if unanswered:** (b), the safe minimum that stops the surprise assign.

---

## Files expected to change

| Area | Files |
|---|---|
| Engine | `inventory-hub/logic.py` (`_perform_smart_move_impl` release + multi-spool refusal + slot 1, `perform_smart_eject`, `perform_force_unassign`, `perform_undo`, `find_spool_in_slot`) |
| Binding store | `inventory-hub/locations_db.py` (`detach_single_slot_box`, `effective_slot`, `known_room_of` moved from `logic`, `get_bindings_for_machine` `single_slot`; remove `detach_single_slot_boxes_from_toolhead`) |
| Spoolman | `inventory-hub/spoolman_api.py` (auto-archive edge release; auto-unarchive occupancy redirect) |
| Routes | `routes_scan.py` (`manage_contents remove` report), `routes_state_pulse.py` (`loaded_count`) |
| Frontend | `inv_loc_mgr.js` (eject toast, toolhead banner), `inv_printer_status.js` (chip, fingerprint, fallback aggregator), `inv_quickswap.js` (slot-1 map, attached / stale tile, Unbind), `inv_cmd.js` (eject-mode location scan, undo toast if needed) |
| Tests | `tests/move_engine_harness.py` (shared, from 39.1; add the stateful locations store), `tests/test_auto_unarchive_occupancy.py`, new `tests/test_single_slot_box_lifecycle.py`, `tests/test_one_spool_per_toolhead.py`, `tests/test_printer_status_loaded_count.py`, route-stubbed `tests/test_single_slot_lifecycle_e2e.py`; deliberate rewrites in `test_l271_single_slot_autoattach.py` and `test_active_print_chain_confirm.py` (E section) |
| Docs | CLAUDE.md write-surfaces rows and the Dryer Box bindings section |
