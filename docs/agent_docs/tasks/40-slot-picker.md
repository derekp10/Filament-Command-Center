# Group 40: 🎯 Slot Picker — Box, Printer and Return Placement

**Branch:** `feature/group-40-slot-picker`
**Estimated effort:** LARGE (~14–20 h, 2–3 sessions). Engine prerequisites ~3 h · shared picker ~4 h · box-label + slot-label doors ~3 h · printer picker ~3 h · Return picker ~2–3 h · wizard doors ~2 h · tests throughout.
**Risk:** **MEDIUM–HIGH.** Every sub-task edits `_perform_smart_move_impl`, the hottest write path in FCC, and 40.3 adds a new prompt on Derek's own daily path (slot-label scans). Everything else protects other users.

> **Status: `IN PROGRESS`.** Engine part built on `feature/group-40-slot-picker` (pushed): 40.0a, a 40.0b pin, 40.0d and item H (`ab69c56`, overnight 2026-10-13/14), then **40.0e and 40.0c (`e8a2706`, 2026-10-14 day session)**, reviewed in `wf_6946f24e-3da` (2 orange + 5 yellow fixed in `db1952a`; 21 notes deferred, listed before the decisions table). **40.1 built (`14c5bc5`) and 40.3 built (browser `d2f076f`; engine `4489cbf`), 2026-10-14 evening; reviewed in `wf_ca12a7f0-f09` (25 findings, none red, 4 orange: all fixed with the shipped-behaviour yellows in `f055def`; full `RUN_INTEGRATION` sweep 3499 passed, 0 failed), the fixes re-checked in `wf_0dddaf03-9a6`.** Derek's hands-on S1–S7 are in the buglist's ⏸️ PENDING DEREK section (they don't block anything). **Next:** `dev`; then 40.2 (its first step: the picker follow-ups at the end of 40.1) → 40.4 → 40.5 → 40.6 → 40.7. See [session-handoff-2026-10-14.md](session-handoff-2026-10-14.md), "Group 40, evening".
> **🔄 2026-10-14 (day) — 40.0e and 40.0c are built (`e8a2706`); where they differ from the 40.0c / 40.0e text below, the code and this note win:**
> - **One rule for the pick:** `logic.recommend_box_slot(max_slots, claims, own_slot, would_prompt)` (own slot → lowest free slot that won't ask → lowest free → none). 40.1's ⭐ reuses it with its own `would_prompt`. The engine's `would_prompt` also avoids a binding to something that isn't a head, and never asks about the head the spool is leaving.
> - **Confirm keys, not bare heads:** each `fed_heads` entry carries `confirm_key` ("XL-1#99": the head and the spools the question named). "Load it instead" sends the keys in `confirmed_fed_heads`; a key covers the head only while it runs exactly those spools (a different spool there is asked about again). A bare head id still covers it whatever it runs (internal callers, tests).
> - **`picked_slot`, not `target_slot`, on a replay:** answers carry the pick as `target_slot`; replays send it back as `picked_slot`, kept only while still free (else `blocked_reason: picked_slot_taken`, nothing written). An explicit `slot` keeps Overwrite semantics. Within one call, a picked slot that someone took during the printer probe refuses the spool (a single-slot box takes it unslotted). A pick feeding the head the spool is leaving stores it there, not loaded back.
> - **The chain guard keys on what the user saw:** `fed_check_from=(box, slot, the head's spools step 4 read)`; the chained deploy refuses to unload any spool that arrived after the question, whatever its trail (a spare scanned onto the head records the free slot as its trail, 40.0d).
> - **The stale-page rule keys on the field:** a head_fed question goes only to a request carrying `confirmed_fed_heads` (`logic.stale_fed_refusal` otherwise answers "Not moved: XL-1 is running #99, and this request can't ask before loading over it. Reload the page…"). Until 40.3 lands, the current browser gets that message wherever a bound head is fed from elsewhere; that's why the branch can't merge before 40.3.
> - **Answer fields for 40.3:** `title`, `body` (no "Continue?"), `spools`, `can_store`, `target_slot`, `fed_heads[].resident{id, display, trail, from, goes_to, goes}`; a printing-only answer on a bound slot carries `can_store` / `title` / `body` too. The doors read `logic.confirmed_fed_heads_from` / `logic.auto_deploy_requested`; the box doors also `picked_slot`.
> - **Claude's calls (not asked; Derek can overrule):** a spare whose trail 40.0d recorded as LR-MDB-1 slot 1 IS that slot's own spool for the same-slot swap (its toast named the slot); the store-only rule above; the non-head-binding rule above.
> - **Found on the way, fixed on `dev` (`bfb7bd0`):** `CMD:SLOT:<n>` with the Location Manager closed moved the buffered spool to Unassigned; a slot scan now needs a box open, and `manage_contents add` refuses a blank location.
> - **When Group 40 merges:** the buglist's ⏸️ PENDING DEREK mid-print checks 5 and 6 scan `LR-MDB-1` slot labels; when XL-1 / XL-2 runs a spool from elsewhere they meet the new question, so update their "pass if".
> **🔄 2026-10-14 — facts that changed overnight (Groups 41 and 42 landed on `dev`; read before building):**
> - 40.0a is built (branch): `locations_db.is_printer_row_not_head` + `printer_row_toolheads` (41.1) decide it, `logic.printer_row_refusal` words it, and a Printer row with no toolheads is refused too (Claude's call 26). The `inv_core.js` mirror is still to build (40.5 needs it).
> - 40.0d is built (branch) except the `record_source` keyword, whose only caller is the Printer picker (40.5): `_feed_slots_for` / `_free_feed_slots` record a slot only when exactly one is free, read strictly through the one slot rule, and answer `recorded_source`; the buffer scan's toast names it (the Location Manager's `doAssign` toast doesn't yet). 42.1 step 5 already keeps single-slot boxes out.
> - The one slot rule exists: `locations_db.effective_slot` (42.2), for 40.0c's same-slot comparison. The one strict "direct residents" reader exists: `logic.strict_direct_occupants(loc, exclude)` (42.3b), for 40.0c's fed-head read. `logic._holds_one_spool` is the engine's one-spool rule (Undo and Bulk Move use it).
> - A single-slot box is never a feed: no auto-deploy, no feeds head, no 13.6 home, not Return's fallback (`/api/dryer_boxes/slots` flags `single_slot`; Return's preview skips it). So 40.6's Return picker skips it too, 40.3 counts a resident whose trail names a PolyDryer as fed from elsewhere, and a Quick-Swap deposit into a PolyDryer promises no load (42 review); 40.3's prompt is for bound multi-slot slots.
> - Two spools claiming one slot are refused by `/api/quickswap` (`quickswap_ambiguous_slot`, `logic.spools_in_slot`). The location scan reads strictly and answers `contents_error`, and eject mode decides first in the location branch (42.5b): 40.2 and 40.5 build on that order.
> - The wizard's Location edit releases a single-slot box after its direct write (`logic.release_box_after_direct_write`); 40.7 replaces that write with the engine.
> **🔄 2026-10-12 (`/refresh-groups`):** item **H** was added (a multi-head Printer row is treated as single-occupancy by Bulk Move; build it with 40.0a). Q1 and Q2 were still open then (both answered 2026-10-13, see the next line). The printer-identity redesign in [Group 44](44-printer-first-class.md) may change what a "Printer row" is; 40.0a's rule should key on whether a row is one of its printer's toolheads, which survives either design.
> **✅ 2026-10-13 — Q1 and Q2 answered** (plain-language briefs, with the code checks behind them: [open-decisions-2026-10-13.md](open-decisions-2026-10-13.md)): **Q1 → loop**, one picker per buffered spool; Escape stops and the rest stay in the buffer (Derek's choice). **Q2 → (a)**, a full box offers the grid's Swap / Overwrite, so the incoming spool always gets a real slot (Claude's call; Derek reviewed it and didn't object). No open questions for Derek remain in this file; the veto points at manual checks R4 and W1 stay.
> Built from Derek's answers to D2, D3 and D5 ([open-decisions-2026-09-13.md](open-decisions-2026-09-13.md)).
> Evidence records: [active-print-chain-investigation-2026-09-12.md](active-print-chain-investigation-2026-09-12.md) (I1-03, I1-05, I1-06, I5-5, I5-8, I5-11) and [active-print-chain-diff-reviews-2026-09-12.md](active-print-chain-diff-reviews-2026-09-12.md) (R1-05, R2-03, R2-08, "Return overlay previews the first bound slot").
> Every `file:line` below was re-read on `dev` @ `be9f045`. Line numbers drift; re-grep the named function before editing.
>
> **⚠️ Stale facts found 2026-10-13 (re-check before building).** Re-verified read-only on `dev` @ `f0d00f3`. The spec below was not rewritten, so in places it still says otherwise.
> - **A multi-head Printer row is no longer single-occupancy.** Since the 2026-09-29 INDX hotfix, a Printer row counts as a head only when its Max Spools is ≤ 1 and its `toolheads[]` lists no head but itself (`logic.py:738-746`). So `LOC:XL` or `LOC:RCOI` with a buffer runs no Smart Load, and the generic branch (`logic.py:1120-1144`) files every buffered spool on the row itself. The door table's `LOC:XL` row and 40.0a's "Today" predate this; 40.0a's refusal is still needed. `_is_single_occupancy` (`logic.py:541-550`) and Bulk Move's `single_occ_types` (`logic.py:1317`, used at `:1348` / `:1408`) still count every Printer row (item H).
> - **Dev topology changed** (dev `inventory-hub/data/locations.json`, 81 rows). Dev has no CORE1: RCOI (Printer, Max 0, heads RCOI-1…RCOI-8) replaced it, and prod retired it too (per the docs' 2026-10-12 read-only check). So no dev Printer row is its own head, and manual checks P5 and W2 name a row that no longer exists. CR-MDB-1 has no bindings. TST-MDB-1 reads `{}`, and Derek confirmed on 2026-10-13 that it is just a test box (Group 45.5). PM-DB-1…PM-DB-10 exist. Dev's only bindings are LR-MDB-1 (1→XL-1, 2→XL-2, 3→XL-3, 4→`PRINTER:XL`) and LR-MDB-2 (1→XL-4, 2→XL-5). The examples that bind TST-MDB-1, or CR-MDB-1 slot 1 → CORE1 (the topology line under the door table, 40.0d, the 40.1 tests, 40.5, P5, Q2), are still fine as hermetic fixtures but no longer describe dev.
> - **Line refs drifted** since `be9f045`. For example: the pre-write contract comment is `logic.py:699-719`; auto-slot is `:851-882` (single-spool check `:858`) and still runs after the confirm (`:842-844`); PRINTER MOVE is `:1023-1098` (13.6 at `:1041-1075`); the chain starts at `:1148`; the location-scan branch is `inv_cmd.js:1705-1772` (L124 trim `:1730-1740`, Quick-Pick `:1747-1755`); `performContextAssign` is at `inv_cmd.js:1864` and already takes a `confirmedHeads` list; the grid's Swap / Overwrite prompt is `inv_loc_mgr.js:1269-1285`.
> - **Prerequisites have landed.** Group 39 merged on 2026-10-13 (`c389e26`). 40.0b's change is in: the pre-flight walks a named slot's binding only when `auto_deploy` (`logic.py:831-841`). `_requires_confirm_answer` (`logic.py:216-231`) reserves `fed_heads`, `can_store` and `target_slot`, but no picker code exists yet. `fix/core1-return-ejectall-guard` and `test/sweep-reds-hermetic` are both merged into `dev`, and `_printer_row_toolheads` is at `routes_bindings.py:335`.

---

## ⚠️ Read this first

1. **Who this is for.** Derek places spools with **slot labels** and **toolhead QRs**. He never scans a multi-slot box's own label (`LOC:LR-MDB-1`) or `LOC:XL`, and has no printer-as-storage QR. The exception is single-slot boxes (PolyDryers), whose box label he does scan. So most of this group (the box-label picker, the Printer picker, the wizard doors) is "shoring up an oversight" for other users, who won't print a label for every bay.
2. **The one part Derek will feel is 40.3**: a slot-label scan into a slot whose toolhead is already running a spool from *somewhere else* now asks first. Build it carefully and keep the same-slot swap prompt-free (see 40.3 "What counts as fed from elsewhere").
3. **Toolhead QR scans and Quick-Swap tile taps get NO new prompt.** They name the head explicitly; the user is looking at it. They keep only the active-print confirm (owned by [Group 39](39-confirm-on-every-door.md)).
   - **The Quick-Swap grid's ⬇️ Deposit is different: it DOES get the "already fed" prompt (40.3).**
   - It posts the slot label (`LOC:<box>:SLOT:<n>`, `inv_quickswap.js:637`) through the same slot-label route a scan uses, and the spool it drops in the slot chains onto the head.
   - This is recorded in the decisions table.
4. **Never mock `perform_smart_move` in a chaining test** ([[mocked engine hides chain bugs]]): every Return test did, and a five-month no-op stayed green. Drive the real engine over a fake Spoolman that mirrors the real merge, matcher and probe memo, and prove each new test fails on a `git archive HEAD` extract.
5. **No text `<input>` inside the picker.** A focused input disarms the hardware scanner (L298 lesson), and the picker must accept slot-QR and toolhead-QR scans.

---

## Items covered (quoted from `Feature-Buglist.md`)

| # | Buglist item | Derek's decision (2026-09-13) |
|---|---|---|
| **A** | **🟠 Active-print guard gaps left after the chain fix.** — item 1: *"A move with no slot into a multi-slot dryer box (Force Location, a buffer location-scan): auto-slot picks the lowest free slot AFTER the active-print pre-flight has run, so a free slot bound to a printing toolhead is never asked about."* | *"1. A box-label scan into a multi-slot box opens a **slot picker**. It shows each slot's spool and the toolhead it feeds, with a recommended slot (never assuming an empty one exists), chosen by touch or slot QR. 2. Before loading the chosen slot's toolhead, **confirm** when that printer is printing, OR the head is already fed from somewhere else (idle too; e.g. XL-1 running off a PolyDryer while slot 1 is prepped for later). Offer "load it instead" / "just store it". An empty head on an idle printer loads with no prompt. 3. **Slot-label scans** get the same "already fed" confirm. 4. **Force Location** into a box behaves exactly like a box-label scan."* Out of scope, for Group 37: *"onboarding that maps slots to toolheads when a box is assigned."* |
| **B** | **🟠 Only Smart Load enforces "one spool per toolhead" — other writers can still stack a second spool.** — item 4: *"Printer rows as targets. A virtual Printer row (dev `XL`, Max 0) counts as single-occupancy for Smart Load but is not a `printer_map` key, so no active-print confirm is ever asked, and spools can be seated on the row itself. The wizard and Force Location location lists offer Printer rows (`XL`, `CORE1`), and the wizard's edit path writes `location` straight to Spoolman (`api_edit_spool_wizard`), bypassing Smart Load and the guard."* | *"A picker, not a refusal. **Opens when:** you scan `LOC:XL`, or pick "XL" in Force Location or the wizard. **Lists:** XL-1…XL-5 (what's on each, and which box slots feed each), plus the Printer Pool slots. **Picking a head** runs the normal load with the D2 confirms. It then asks which feeding box slot to record as the spool's source, or none. **Picking a pool slot** only stages the spool. **Underneath,** the server refuses placement on the Printer row itself, keyed on "this row is not itself one of its printer's toolheads" so CORE1 stays loadable. **Priority:** low for Derek, who never scans `LOC:XL`; this protects other users."* Plus, from the decisions record: *"One is pre-selected only when exactly one free option exists."* |
| **C** | **🟡 Eject / Return UX leftovers.** — item 2: *"Return of a spool whose `physical_source` box has no recorded slot lets auto-slot take the lowest free slot, which can be bound to a DIFFERENT toolhead."* | *"A slot picker, shown only when Return has no usable slot (none recorded, or the recorded one is taken). **Shows** the box's slots, with what each holds and which head it feeds. **Pre-selects** this head's free slot, else a pool/spare slot, else "no slot". **A known, free recorded slot** keeps Return one tap. **Reuses** the D2 picker."* Derek: *"mostly a legacy-data case. He always slots spools… Floating spools are an annoyance, and a "5/4" count reads as "what went wrong"."* |
| **D** | **🟠 Found while briefing the six open decisions** — item 7: *"🟡 Return's display. The overlay preview doesn't model the auto-picked slot: it names no slot, or the taken one. The success toast reads `SLOT:null` when a spool lands unslotted. Fix together with the "Return with no recorded slot" decision."* | Fix with C (D5: *"The confirm preview and toast name the slot actually used (no more `SLOT:null`)."*) |
| **E** | Same entry — item 4: *"🟡 The ↩️ Return button on a DEPLOYED slot card redeploys to the same head."* | Not decided by Derek. **Decided here (40.6)**: route it through the canonical Return. |
| **F** | Same entry — item 8: *"🟡 `LOC:XL` with an empty buffer Quick-Picks one of the XL heads' spools… Fix together with the Printer-row placement decision / L271 Phase 5 prefix retirement."* | Not decided by Derek. **Decided here (40.5)**: fix the scan behaviour now; the flat matcher itself waits for Group 37. |
| **G** | The **13.6 reverse-binding**, which silently records a free bound feed slot as `physical_source` when a spool lands on a head with no meaningful source. Decisions record, D3: *"Derek's addition turns that into a visible choice."* | **Decided here (40.0d)**: a visible choice in the Printer picker; for scans, record only when exactly one free slot feeds the head and name it in the toast. |
| **H** | _(added 2026-10-12 by `/refresh-groups`)_ **"Bulk move treats a multi-head Printer row as single-occupancy."** After the 2026-09-29 INDX hotfix, a single move onto a multi-head Printer row (RCOI / XL) is a generic move, but dev's `_is_single_occupancy` (`logic.py:356`) and bulk-move `single_occ_types` (`logic.py:1047`, used at `:1078` / `:1138`) still include `'Printer'`, so a bulk move onto it is refused. *"Conservative, but align both on 'in printer_map or a toolhead Type'."* | Build with **40.0a**, which settles what a Printer row may hold. Keep the dual-role case (a Printer row that is its own toolhead, like the old `CORE1`) loadable. Bulk Moves ships behind the `fcc.bulkMove.enabled` flag (off on prod), so this is low urgency. |

**Not in this group:** D1 / R2-08 / the "Checking XL…" indicator / D6 / Force Location's active-print yes-path / the fail-closed resident read (R1-03) / the I1-06 pre-flight gate ([Group 39 — Confirm on Every Door](39-confirm-on-every-door.md)); the single-slot box release rule and the other "one spool per toolhead" items ([Group 42](42-single-slot-box-lifecycle.md)); Eject All / delete / Undo honesty ([Group 41 — Honest Bulk Results](41-honest-bulk-results.md)).

---

## Today's doors: how a spool gets placed without a choice

| Door | What happens today | Code (dev `be9f045`) |
|---|---|---|
| Box-label scan with a buffered spool (`LOC:LR-MDB-1`) | A Dryer Box is not single-occupancy in the L124 check, so the WHOLE buffer goes to `/api/smart_move` with `slot: null`. One spool → the engine picks the lowest free slot **after** the active-print pre-flight ran, then chains onto that slot's toolhead. Several spools → all land unslotted ("5/4"). | `inv_cmd.js:1659-1693` (whole buffer at `:1689`), `performContextAssign` `inv_cmd.js:1889-1911`, `/api/smart_move` `print_deduct.py:253-262`, pre-flight `logic.py:524-540`, auto-slot `logic.py:553-578` (one spool only `:554`, Max > 1 `:559`), chain `logic.py:885-952` |
| Force Location → a Dryer Box | `manage_contents add` with no slot and no confirm → the same auto-slot + chain. | list `inv_details.js:951-959`, payload `inv_details.js:1211-1222`, route `routes_scan.py:328-334` |
| Slot-label scan `LOC:LR-MDB-1:SLOT:1` | Explicit slot; the chain deploys onto XL-1 and Smart Load unloads whatever XL-1 held. Only an active-print confirm exists. | parse `logic.py:166-172`, route `routes_scan.py:1060-1195` (engine call `:1126-1129`, confirm answer `:1133-1142`), client replay `inv_cmd.js:1570-1643` |
| Location Manager grid tap / `CMD:SLOT:n` on a box | Explicit slot through `doAssign`; the client probes only when the TARGET is a toolhead type, so a box slot is never probed. | `inv_loc_mgr.js:1202-1240`, `:1242-1282` (probe gate `:1255-1262`), `inv_cmd.js:1497` |
| Quick-Swap deposit into an empty bound slot | Posts `LOC:box:SLOT:n` through the slot-label path. | `inv_quickswap.js:607-695` |
| `LOC:XL` with a buffered spool | `locType 'printer'` is not "tool/mmu/direct load" and Max is 0, so the L124 trim misses it and the whole buffer goes to row `XL`. Smart Load treats the row as single-occupancy (Type Printer). | `inv_cmd.js:1677-1689`, `logic.py:591`, `logic.py:605-678` |
| `LOC:XL` with an empty buffer | `parseInt(Max Spools) <= 1` is true for `0`, so it Quick-Picks `contents[0]`, which the flat prefix matcher fills with spools loaded on XL-1…XL-5. | `inv_cmd.js:1694-1702`, `spoolman_api.py:1467` |
| Deposit card on the XL view | `doAssign('XL', id, null)`; the card's QR is `LOC:XL`. | `inv_loc_mgr.js:1005-1015`, `:1127-1137` |
| Force Location / wizard → `XL` or `CORE1` | Both lists drop tool/mmu/direct-load types but keep `Printer`. | `inv_details.js:954`, `inv_wizard.js:1509` |
| Wizard edit that changes `location` | Diffed as a plain key and PATCHed straight to Spoolman: no Smart Load, no active-print guard, no Printer-row check. | `routes_inventory.py:633-636`, write `:659-660`; create default `:497-503` |
| Return with no recorded slot, or a taken one | `found_slot = src_slot or None`; a taken slot is dropped to `None`; the engine then auto-slots (possibly another head's feed slot). The preview never modelled that; the toast prints `SLOT:null` when the spool lands unslotted. | `routes_bindings.py:646`, `:689-698`, engine call `:711-714`, landed-slot read `:733-737`; preview `inv_quickswap.js:812`, `:872`; toast `inv_quickswap.js:580` |
| ↩️ Return on a DEPLOYED slot card | `doAssign(box, id, slot)` → `manage_contents add` with the slot and the default `auto_deploy=True` → the chain puts the spool straight back on its head. | list card `ui_builder.js:159`, grid card `ui_builder.js:214`, route `routes_scan.py:328-334`, chain `logic.py:888-913` |
| Spool lands on a head with no meaningful source (13.6) | The engine silently records the FIRST unclaimed bound slot (in `locations.json` order) as `physical_source`. | `logic.py:767-793`, `_find_box_slot_feeding_toolhead` `logic.py:70-96` (first match, `:79-80`) |

Dev topology these examples use (read-only `data/locations.json`): **LR-MDB-1** Max 4, slots 1→XL-1, 2→XL-2, 3→XL-3, 4→`PRINTER:XL` (pool) · **LR-MDB-2** Max 2, 1→XL-4, 2→XL-5 · **TST-MDB-1** Max 6, 1→`PRINTER:XL` · **CR-MDB-1** Max 4, 1→CORE1 · **PM-DB-1…8** Max 1 (PolyDryers, unbound at rest) · **XL** Printer, Max 0, `toolheads` XL-1…XL-5 · **CORE1** Printer, Max 1, `toolheads` ['CORE1'] (its own head).

---

## 40.0 — Engine prerequisites (backend, hermetic, build first)

### 40.0a Refuse placement on a Printer row that is not itself a toolhead

**Today.** `_perform_smart_move_impl` counts a Type `Printer` row as single-occupancy (`logic.py:591`) and runs Smart Load on it. For `XL` (Max 0, not a `printer_map` key) no active-print check can match (`logic.py:29-31`), so a spool is seated on the row itself. The Smart Load resident filter already skips prefix hits (`logic.py:645`), so it no longer unloads XL-1…XL-5.

**Design.** Early in `_perform_smart_move_impl`, right after the spool list resolves (`logic.py:512`), refuse when the target row is Type `Printer` and is **not one of its own `toolheads[]`**:
- the key is `loc_id in printer_map`:
  - `get_active_printer_map` is built only from the Printer rows' `toolheads[]` (`locations_db.py:1002-1015`);
  - the config fallback was removed in the Phase 4 cutover, and the "(dual-read)" comments at its call sites (e.g. `logic.py:501`, `routes_bindings.py:134`) are stale;
  - so a Printer row is "its own toolhead" exactly when some row's `toolheads[]` lists it, which is also the key Group 41.1 uses;
- `CORE1` lists itself in `toolheads`, so it stays loadable;
- answer `{"status": "error", "blocked_reason": "printer_row", "msg": "XL is a printer, not a toolhead — pick one of its heads (XL-1…XL-5) or a Printer Pool slot.", "failures": {sid: msg}}` and write nothing;
- log a WARNING. It is a refusal, not a Spoolman failure, so no `LAST_SPOOLMAN_ERROR` read.

**One shared helper**, `locations_db.is_printer_row_not_head(loc_id, row, printer_map)`, used by:
- this refusal;
- `api_edit_spool_wizard` (40.7);
- Group 41.1's `eject_all_block_reason`;
- an `inv_core.js` mirror, for 40.5's Quick-Pick check and 41.1's `triggerEjectAll`.

The core1 branch already adds `_printer_row_toolheads(loc_list, loc_id)` in `routes_bindings.py` (`:275` on `76398cb`). Move it into `locations_db` next to the new helper, rather than growing a second copy.

**Tests (hermetic).** Real engine over `FakeSpoolman` (see "Test conventions"):
- `perform_smart_move('XL', [42])` → `blocked_reason printer_row`, zero writes, XL-1/XL-3 spools untouched;
- `perform_smart_move('CORE1', [42])` with CORE1 holding #99 → Smart Load runs, CORE1 == [42];
- a Printer row with an empty `toolheads[]` → refused with *"XL has no registered toolheads"* (no config fallback exists to rescue it).

**Risks.** Legacy spools already sitting on `XL` stay where they are (no migration). Before merging, count them read-only on dev and prod; they render on the XL view and can be moved through the picker.

### 40.0b The slot-binding pre-flight respects `auto_deploy` (I1-06) — owned by Group 39

**Today.** The pre-flight walks the target slot's binding even when `auto_deploy=False` (`logic.py:528-533`), so a pure box store refuses during a print. No current caller hits it (Return passes `confirm_active_print=True`, `routes_bindings.py:711-714`), but "Just store it" (40.3) would.

**Owner.** [Group 39](39-confirm-on-every-door.md) makes this change in 39.2 ("walk a named slot's binding only `if auto_deploy`"). This group depends on it. If 40 is built first after all, make exactly that change here and note it for the Group 39 session.

**Test this group still adds.** `perform_smart_move('LR-MDB-1', [240], target_slot='3', auto_deploy=False)` with XL printing → `success`, #240 in slot 3, XL-3 untouched. It pins the "Just store it" path, whoever lands the fix.

### 40.0c A server-side "head already fed" confirm for the bound-slot chain (D2.2, D2.3)

**Today.** The chain deploys onto the bound head and Smart Load unloads its resident with no question when the printer is idle (`logic.py:895-913`, `:605-663`).

**What counts as "fed from elsewhere".** Let H be the head the chosen slot feeds, and R a spool whose OWN record says it is on H (`location == H`, not a ghost), excluding the spool being placed.
- **No R** → not fed. An idle printer loads without a prompt (Derek: *"An empty head on an idle printer loads without an extra prompt."*).
- **R's trail (`physical_source`, `physical_source_slot`) equals this box and slot** → a normal swap-out of the slot's own spool. **Not** "elsewhere", so no new prompt. This is Derek's everyday "replace the spool in LR-MDB-1 slot 3" path, and must stay one scan.
- **R's trail names another box or slot** (PolyDryer, another bay) → fed from elsewhere → confirm.
- **R has no trail** → FCC cannot tell where it is fed from → confirm. A wrong silent unload costs more than one tap.
- Compare slots normalized: strip quotes, and treat a single-slot box's blank slot as `1` (Group 42.2 writes `1`; legacy rows are blank).

**Design.**
- When `auto_deploy` is on and the target is a Dryer Box slot bound to a real head (not a `PRINTER:` sentinel, `logic.py:891-894`), read H's residents with `get_spools_at_location_detailed_strict` **before any write**. A read exception refuses the move (fail closed): `"couldn't read XL-1 from Spoolman — nothing moved"`.
- **Reuse Group 39's scoped-confirm contract (39.1), not a bare boolean.** 39.1 adds `confirmed_toolheads: [...]` (the heads whose printing warning the user saw; `perform_smart_move`'s `confirm_active_print` accepts that list) and answers `requires_confirm` with `active_prints: [{toolhead, printer_name, state, role, spools}]`. This check adds a sibling pair:
  - request field and engine keyword `confirmed_fed_heads: ["XL-1"]`: the heads whose "already fed" warning the user saw;
  - if H is fed from elsewhere and is not in `confirmed_fed_heads`, answer before writing:
    `{"status": "requires_confirm", "confirm_type": "head_fed", "fed_heads": [{"toolhead": "XL-1", "box": "LR-MDB-1", "slot": "1", "resident": {"id": 99, "display": "…", "trail": {"box": "PM-DB-2", "slot": "1"}}}], "active_prints": [...] (39.1, when printing), "can_store": true, "msg": "…"}`.
  - **A sibling list, not a role inside `active_prints`.** Group 39.1 reserves `fed_heads`, `can_store` and `target_slot` in its one shared answer shape, and this sub-task fills them. Reasons:
    - an idle fed head has no printer state;
    - 39.4's `_active_print_message` wording ("FCC stops charging this print…") doesn't fit it.
    - Both lists are scoped by head id, so a stale grid whose slot was rebound (R2-08) is asked again either way.
- **One prompt, not two.** Collect `active_prints` (39.1's `_uncovered_active_heads`, one probe per printer through the memo, `logic.py:441-474`) and `fed_heads` in the same pre-flight, before any write:
  - printing but not fed → 39.1's `active_print` answer unchanged, plus `can_store: true` for a box-slot target;
  - fed, printing or not → `head_fed`, carrying both lists.
- "Just store it" = the same call with `auto_deploy=False` (needs 40.0b).
- Thread the new fields through the **three** entries that can reach a bound box slot:
  - `manage_contents add` (`routes_scan.py:328-334`, which today passes no `auto_deploy`);
  - `/api/smart_move` (`print_deduct.py:253-262`);
  - the slot-label branch (`routes_scan.py:1125-1129`, reading `auto_deploy` and `confirmed_fed_heads` from `request.json`). The Quick-Swap grid's Deposit arrives here too.
- **Not** `/api/quickswap` or `/api/quickswap/return`; neither can trigger this check:
  - Quick-Swap's target is a toolhead (`routes_bindings.py:821-824`);
  - Return targets a box with `auto_deploy=False` (`:711-714`).

**Tests (hermetic, real engine).**
- Idle, XL-1 empty → deploys, no prompt.
- Idle, XL-1 holds #99 with trail `LR-MDB-1:1`, place #42 into LR-MDB-1 slot 1 → no prompt; #99 unloads home; XL-1 == [42].
- Idle, XL-1 holds #99 with trail `PM-DB-2` → `head_fed`, zero writes. Replay with `confirmed_fed_heads=["XL-1"]` → XL-1 == [42], #99 back in PM-DB-2. Replay with `auto_deploy=False` → #42 in slot 1, XL-1 still [99].
- Trail-less resident → `head_fed`.
- Printing + fed → one `head_fed` answer carrying `active_prints` and `fed_heads`; the replay needs both `confirmed_toolheads` and `confirmed_fed_heads`.
- The strict read raises → refused, zero writes.
- Slot rebound to XL-2 between prompt and replay, replay carries `confirmed_fed_heads=["XL-1"]` → asked again about XL-2, zero writes.
- The slot-label route through the Flask client: `assignment_requires_confirm` carries `confirm_type: head_fed`; the replay with `auto_deploy: false` answers `assignment_done` with no deploy.

**Risks.**
- One extra strict Spoolman read per bound-slot assign (~150 ms on the NAS). L3 put worst-case slot assigns at 6.5 s, mostly printer probes, so it is tolerable; log a timing if it shows up.
- Pins that assert an unconditional idle deploy onto an occupied head may need an explicit `confirmed_fed_heads` (grep `test_active_print_chain_confirm.py`, `test_smart_move_spoolman.py`, `test_deployed_flag_preservation.py`). Change each deliberately, with the reason in its docstring.

### 40.0d `record_source` for head loads, and a stricter 13.6 (item G)

**Today.** When a spool lands on a head with no meaningful source, `logic.py:767-793` records the first unclaimed bound slot (`_find_box_slot_feeding_toolhead`, first match in file order, `logic.py:79-80`). It already refuses a slot another spool claims (`logic.py:772-781`).

**Design.**
- New keyword on `perform_smart_move` for toolhead targets: `record_source=None` (legacy 13.6), `{'box': B, 'slot': n}` (use exactly this) or `''` (record nothing).
  - The server validates a named source: B is a Dryer Box, `slot_targets[n] == target head`, and no other spool claims the slot. Otherwise answer an error and write nothing.
  - It is honoured only when `_ghost_trail_from` gave no trail (the spool is not arriving from a box). Otherwise ignore it and say so (`record_source_ignored: true`).
- **Silent 13.6 for scans (Derek's toolhead-QR path) stays, with two changes:**
  1. Collect ALL unclaimed bound slots feeding the head. Record one only when **exactly one** is free, the same "pre-select only when exactly one free option exists" rule Derek gave for D3. With two or more free, record nothing and log INFO `"not guessing: LR-MDB-1:1 and TST-MDB-1:2 both feed XL-1"`.
  2. Return what was recorded (`recorded_source: "LR-MDB-1:1"`) so the scan toast can say *"#42 → XL-1 (recorded as from LR-MDB-1 slot 1)"* (`inv_cmd.js:1931`, `inv_loc_mgr.js:1456`).

**Keep single-slot boxes out of the candidates.** [Group 42.1](42-single-slot-box-lifecycle.md) step 5 lands this first; this sub-task builds on it. Without it, collecting every free slot would pick up PolyDryers, for three reasons:
- `_find_box_slot_feeding_toolhead` scans every Dryer Box (`logic.py:87-95`).
- The claimed-slot check compares an occupant's slot to the bound slot (`logic.py:777-781`). A PolyDryer's spool carries a blank slot (its ghost falls back to `container_slot ""`, `spoolman_api.py:1486-1488`), so that slot always reads as free.
- `loc_list` is read once (`logic.py:502`), before Smart Load's eject detaches the box (`logic.py:650-653` → `:1884`), so a just-released PolyDryer still looks bound.

**Worked example.** CORE1 runs #60 from PM-DB-4, and CR-MDB-1 slot 1 holds a staged spool. You scan a spare onto CORE1.
1. #60 goes home to PM-DB-4, and CR-MDB-1 slot 1 is claimed.
2. The only "free" candidate left is PM-DB-4 slot 1, so the spare is recorded as coming from PM-DB-4.
3. A later Return or eject lands the spare on top of #60, and Group 42.1's trail-keyed release treats PM-DB-4 as the spare's box.

Today's first-match code avoids this only by row order: CR-MDB-1 (row 20) and LR-MDB-1 (row 43) come before PM-DB-1…8 (rows 48-55) in dev `data/locations.json`.

**Fix.**
- Exclude single-slot Dryer Boxes (`locations_db._is_single_slot_dryer_box`) as reverse-binding candidates.
- Compare claimed slots with Group 42.2's `effective_slot`.
- With both in place the stale `loc_list` is harmless, because only single-slot bindings change during a move.

**Rationale.** A prompt on every toolhead-QR scan would slow Derek's main path. Naming the recorded slot makes the silent choice visible. Refusing to guess between two free slots, and never offering a single-slot box, removes the two cases where the choice could be wrong.

**Tests.**
- One free bound slot → recorded and reported.
- Two free → nothing recorded, INFO logged.
- `record_source={'box': 'LR-MDB-1', 'slot': '1'}` → recorded even when TST-MDB-1:2 is also free.
- `record_source=''` → nothing recorded.
- A claimed named slot → refused.
- A spool arriving from LR-MDB-2 slot 1 with `record_source` given → trail stays `LR-MDB-2:1`, `record_source_ignored`.
- The worked example above → nothing recorded, and PM-DB-4 is never a candidate.
- The existing head-to-head pins still pass (`test_active_print_chain_confirm.py:637-662`).

### 40.0e Auto-slot runs before the pre-flight (item A's engine gap)

**Today.**
- Auto-slot (`logic.py:553-578`) runs AFTER the active-print pre-flight (`logic.py:524-540`), so a slotless move into a multi-slot box never asks about the slot it picks.
- The chain then refuses to borrow a confirm that wasn't about that head (`confirm_active_print and explicit_slot`, `logic.py:909`), skips the deploy, and warns.
- The pickers (40.2, 40.4, 40.7) close the doors Derek's decision names. Any caller that isn't converted still reaches this gap, for example a direct `/api/smart_move` call.

**Design (decided here; Derek can overrule).** Move auto-slot rather than retire it:
- run it at step 3 of Group 39.1's pre-write order, before the pre-flight and 40.0c's fed-head check;
- pick with the picker's own recommendation rule (40.1): the lowest empty slot that would not prompt (unbound, a `PRINTER:` pool sentinel, or bound to a head with no resident, all from one `bucket_spools_by_location` read), else the lowest empty slot;
- treat the picked slot as named from then on, so the pre-flight and 40.0c ask about its head, and the confirm covers the chain;
- carry `target_slot` in the answer, and have the replay send it, so a second call can't auto-pick a different slot.

*Rejected:*
- **Retiring auto-slot.** A slotless move into a box would land unslotted: the "5/4" state Derek calls "what went wrong".
- **Keeping it after the pre-flight, warn-only.** A free slot bound to a printing head would still never ask.

**Tests (hermetic, real engine).**
- `perform_smart_move('LR-MDB-1', [42])` with XL idle; slots 2 and 3 full; slot 1 empty, but XL-1 running #99 from PM-DB-2; slot 4 (pool) empty → slot 4, no ask.
- Slots 2 (→ XL-2, empty head) and 4 empty, XL printing → slot 2 by the rule; the answer is `requires_confirm` naming XL-2, with `target_slot: "2"`, `can_store: true`, and zero writes. Replay with `target_slot="2"` and `confirmed_toolheads=["XL-2"]` → #42 on XL-2.
- The existing `test_auto_slot_pick.py` cases still pass, or change deliberately with the reason in the docstring.

---

## 40.1 — The shared picker component (`static/js/modules/slot_picker.js`)

One component serves all three pickers: box (D2), printer (D3) and return (D5).

### Data: one server model, one fetch

- **New read route** `GET /api/placement_options?location=<id>&spool=<sid>&toolhead=<th>`, registered in `routes_bindings.py` (it owns bindings and Quick-Swap). The builder lives in a new flat module `placement.py` at the `inventory-hub/` root (CLAUDE.md module rules; add a module-map row). Update `tests/test_route_table_pin.py` (`EXPECTED_ROUTES`, `:18`) and the `app.py` re-export block deliberately.
- **Model** (mode derived from the row):
  - `box` mode, a Dryer Box with Max > 1:
    - `slots[]` of `{slot, spool|null (id, display, color, is_ghost, deployed_to), feeds: {kind: "toolhead", id, printer, resident|null} | {kind: "pool", printer} | null, current: bool}`;
    - `recommended` (slot or null) plus `recommend_reason`;
    - `slot_order`, so an `rtl` box renders the way its grid does (`inv_loc_mgr.js:952-965`).
  - `printer` mode, a Printer row that is not its own head:
    - `heads[]` of `{id, position, resident|null, feeds[]: {box, slot, spool|null, claimed_by|null}}`;
    - `pool[]` of `{box, slot, spool|null}`;
    - enumerate heads from the row's `toolheads[]` / `printer_map` `printer_name`, **never** a `startsWith(prefix)` scan (that is why the Core One Return never works, buglist new-findings item 1);
    - pool entries from `locations_db.get_bindings_for_machine` (`locations_db.py:1771-1829`).
  - `return` mode: box mode for the Return's destination box, with the D5 recommendation (40.6).
- **Contents:**
  - resolve every needed location in ONE Spoolman fetch with `spoolman_api.bucket_spools_by_location` (`spoolman_api.py:1570`);
  - classify residents by **exact** location (`location == id`, `is_ghost` false), never by the flat prefix hit, so Group 37's matcher change cannot move picker behaviour;
  - check whether the bucket reader fails open; if it does, return `read_ok: false` and let the picker say "couldn't read Spoolman" rather than draw empty slots.
- **No printer probe inside the model.** The picker opens instantly. It then probes once per printer with Group 39.3's `fetchPrinterStateDetailed(toolhead)` (it tells "idle" from "couldn't ask"; backed by `/api/printer_state/<head>`, `routes_bindings.py:121-150`), wrapped in 39.3's `withPrinterCheck(printerName, promise, {timeoutMs})`. That shows the pinned **"⏳ Checking XL…"** pill after 300 ms and a plain "XL didn't answer" warning on timeout. That printer's tiles show "checking…" until the answer, then "printing", "idle" or "couldn't reach".

**Box recommendation rule (D2.1).**
1. If the spool is already in this box, its current slot.
2. Else the lowest-numbered empty slot that **would not prompt**: unbound, a pool sentinel, or bound to a head with no resident.
3. Else the lowest-numbered empty slot.
4. Else none: the box is full. Never assume an empty slot exists. A full box still opens the picker, and a tap on any slot offers the grid's Swap / Overwrite (Q2, decided 2026-10-13; see 40.2).

Rationale: other users scanning a box label mostly want to store, and a recommendation that can be confirmed with Enter should never surprise. Derek's own example, "the next empty one", is rule 3 whenever no prompt-free slot exists.

### UI contract

- **Mount** through `window.mountOverlay` (`overlay_mount.js:80-220`):
  - tier `standard`, or `confirm` when opened above a Swal-free Bootstrap modal that already has an overlay;
  - `host` = the Location Manager or spool modal when opened from one;
  - `occlude` any `<select>` underneath;
  - never nested Swal; Force Location's Swal is fully closed first (`.then` at `inv_details.js:1206`).
- **Keyboard** (CLAUDE.md idiom):
  - ←/→/↑/↓ move `.kb-active` with wrap;
  - `1`–`9` jump to slot or head N;
  - Enter picks; Escape cancels through `onEscape`, never a second Escape handler.
  - Register the keys with `window.registerShortcut` (`shortcuts_registry.js`; `CMD:SLOT:<n>` is listed at `:267`).
  - Reference implementation for nav + mountOverlay: the Group 34 tree picker, `inv_loc_mgr.js:2100-2234`.
- **Scan to select.** Add `window.routePickerScan(text)` and call it in `processScan` right after `routeConfirmScan` (`inv_cmd.js:1408`). While a picker is open it claims:
  - `LOC:<its box>:SLOT:<n>` and `CMD:SLOT:<n>` (the grid's own per-slot QRs, `inv_loc_mgr.js:989-990`) → select slot n;
  - in printer mode, `LOC:<head>` → select that head, and a pool slot label → select that pool slot;
  - `CMD:CANCEL` → cancel.
  - Any other scan → 7 s warning *"Finish or cancel the slot picker first"* plus an Activity Log line. Never fall through and act.
  - Follow the L298 shortcut rules: `stopImmediatePropagation()` plus a deferred `scanBuffer` clear.
- **Never open during a bulk-move session** (`state.bulkMoveActive`); location scans belong to the session.
- **Tiles**: `SpoolCardBuilder` for occupied slots, so colours match the grid. Feeds line `→ XL-1` (or `🏭 Printer Pool`). Resident line `XL-1 runs #99 (from PM-DB-2)`. A `⭐ Recommended` badge. An `🔗 Edit feeds` link that opens the box's Feeds editor, reusing `window._fccAutoExpandFeeds` (`inv_quickswap.js:1235`). Re-mapping inside the picker is deferred (see the Group 37 section).
- **Returns a Promise** resolving `{kind: 'slot'|'head'|'pool'|'none', box, slot, head}` or `null` on cancel. Callers own the write.

**Tests.**
- Hermetic `tests/test_placement_options.py` (model and recommendation over fake locations + fake bucket):
  - every rule branch;
  - a full box → `recommended: null`;
  - an `rtl` box;
  - `CORE1` as its own head;
  - pool slots from both LR-MDB-1:4 and TST-MDB-1:1;
  - a read failure → `read_ok: false`.
- Offline source canaries: the picker markup has no `<input`; it calls `mountOverlay`; `processScan` calls `routePickerScan` before the `CMD:` branches.
- Route-stubbed E2E `tests/test_slot_picker_e2e.py`, in the `test_move_result_consumers_e2e.py` pattern (`page.route` stubs, `require_server`, no dev writes):
  - arrow / number / Enter / Escape;
  - scan `LOC:LR-MDB-1:SLOT:3` selects slot 3;
  - a foreign scan is refused with a toast;
  - "Checking XL…" appears when `/api/printer_state` is delayed in-page (the Group 38 in-page fetch-delay lever) and turns into the timeout text.
- Visual baseline over stubbed data only. Never snapshot live dev contents (the `test_quickswap_visual` lesson).

### Before 40.2 wires the picker: what the 40.1 + 40.3 review found in it

The review (`wf_ca12a7f0-f09`, D-tests-picker) confirmed these in the built picker. They can't happen yet
(nothing opens `window.openSlotPicker` until 40.2), so they are 40.2's first step, each with a pin:
- **D1, scans and Enter.** A short numeric scan (a 1–2 digit spool id) moves the highlight with its digits and
  its Enter picks a slot; any scan while focus sits in an input behind the picker picks too. Yield Enter to
  `window.isScanInFlight()` (as `confirmActivePrint` does), never pick while `document.activeElement` is outside
  the panel, and take a digit as a hotkey only with an empty scan buffer and a gap of at least 50 ms.
- **D2, opening guards.** It stacks over another overlay (one Escape then cancels the dialog underneath, a second
  closes the picker), opens during an audit and over a gating dialog. Refuse to open (null, a 7 s warning, a log
  line) while another `[data-overlay-mount="1"]` is mounted or `state.auditActive` / `state.activeModal` /
  `state.processing` is set; close itself when a bulk move or an audit starts (`inventory:sync-pulse`).
- **D3, refusals nobody sees.** Its only refusal feedback is a toast, which sits under the panel (z 11000 vs
  20000): add a `role=alert` status line inside the panel (as the three-way has); keep a slot label scanned while
  the model loads and apply it once the tiles exist; toast and log `CMD:CANCEL`.
- **D4, what a caller sends.** The result carries no `send` / `expected_feed` and disables no tile, so a caller
  that sends the natural `slot` reloads a spool the tile promised to store ("stored here, not loaded back"). Return
  `send` (`picked_slot` for an empty or own-ghost slot, `slot` only after a Swap / Overwrite choice) and
  `expected_feed` (the tile's feed token), and disable doubly-claimed and non-head-binding slots (and occupied
  ones in return mode) with a why-string.
- Done already: D8 (printer mode no longer stars the spool's own head, `f055def`), D5 / D6 (pins), and
  `placement.py` in the slot_targets reader canary (`09c3d5a`).

---

## 40.2 — Box-label scan opens the picker (D2.1)

**Today.** See the door table: `inv_cmd.js:1659-1693` sends the buffer to `/api/smart_move` with no slot.

**Design.**
- In the location branch with a non-empty buffer: when the row is a Dryer Box with `Max Spools > 1`, open the picker (box mode) for the TOP buffered spool instead of `performContextAssign`.
- Single-slot boxes (PolyDryers) and every other type keep today's path.
- On a pick, call `performContextAssign(box, slot, false, [top.id])` (`inv_cmd.js:1889`), extended (after 39.1) to send `confirmed_toolheads` / `confirmed_fed_heads` and to handle `requires_confirm` with `confirm_type` `head_fed` / `active_print` via the three-way confirm (40.3).
- Picking an occupied slot → the same Swap / Overwrite choice the grid uses (`inv_loc_mgr.js:1212-1228`), as Q2 settled on 2026-10-13: no "store without a slot" tile and no refusal, so the incoming spool always gets a real slot.
- Several spools in the buffer → see **Q1**, answered 2026-10-13: **loop**. After each pick the picker reopens for the next spool that was in the buffer when the label was scanned; Escape stops, and the rest stay in the buffer. Build note: iterate over that scan-time list, so a spool that a Swap pushes onto the end of the buffer (`inv_loc_mgr.js:1493-1497`) is not offered again and the loop always ends. The old default (place only the top spool) no longer applies.

**Tests.** Route-stubbed E2E: `LOC:LR-MDB-1` with one buffered spool opens the picker; picking slot 2 posts `{location: LR-MDB-1, slot: "2", spools: [top]}`; a `head_fed` answer opens the three-way confirm; the buffer keeps the spool on Cancel; with two buffered spools, the picker reopens for the second after the first pick, and Escape leaves it in the buffer (Q1); on a full box, a tap on an occupied slot opens Swap / Overwrite (Q2). Hermetic: none new (engine covered by 40.0).

**Risk.** `state.lastScannedLoc` double-scan (`inv_cmd.js:1658`) opens the manager on a second scan of the same label. Keep that behaviour when no picker is open.

---

## 40.3 — Slot-label scans, grid taps and deposits get the "already fed" confirm (D2.2, D2.3)

### Built first: what the server now expects from the browser (built 2026-10-14 with 40.0c / 40.0e)

The server half of 40.3 shipped with 40.0c. The browser half is what 40.3 builds:

1. **Every request to the three doors sends `confirmed_fed_heads`** (at least `[]`): the slot-label scan and every
   replay of it, the Quick-Swap ⬇️ Deposit, Location Manager grid taps / Swap / Overwrite / `CMD:SLOT:n`
   (`doAssign` → `_doAssignFinalize`), the ↩️ on a DEPLOYED grid card, `performContextAssign`, Force Location, and the
   Location Manager ID field's typed `LOC:…:SLOT:n` (`manualAddSpool`; route its non-spool text through `processScan`,
   which also fixes its "Invalid Code" toast for a slot move that landed). A request without the key gets the
   stale-page "reload" refusal instead of the question. Add a source canary: every POST to `/api/identify_scan`,
   `/api/smart_move` and `manage_contents` action `add` sends the key, or sits on an allow-list with a reason
   (`CMD:AUDIT` / `CMD:CANCEL` / `CMD:DONE` posts, the `ID:` pickup).
2. **Branch on `confirm_type === 'head_fed'` (and on `can_store`) before every active-print fallback.** An idle
   head_fed answer has `active_print: null` and `active_prints: []`; today's handlers would invent a "… is
   PRINTING" banner (askAndReplay, `_reaskFromServer`, `confirmActivePrint`, `_doAssignFinalize`,
   `performContextAssign`). Pin: an idle head_fed answer never renders "is PRINTING" or "Continue Anyway" (node vm).
3. **The dialog**: `title` asks ("Load #57 onto XL-1?"), `body` explains (Derek's wording; no "Continue?"), buttons
   **Load it instead** · **Just store it in LR-MDB-1 slot 1** · **Cancel**, each with a scan QR (`CMD:CONFIRM`,
   `CMD:STORE`, `CMD:CANCEL`). Enter = Just store it (Derek's answer 5). A printing-only answer with `can_store` also
   has `title` and `body` and uses the same dialog.
4. **Replays** (both name what the question was about):
   - **Load it instead** = the original request + `confirmed_fed_heads`: the union of every answer's
     `fed_heads[].confirm_key` so far ("XL-1#99": the head and the spools the question named; a different spool on the
     head is asked again) + `confirmed_toolheads`: `unionConfirmHeads(prior, answer)` + `picked_slot: answer.target_slot`
     (box doors, when the first request named no slot) + the spool ids in `answer.spools`.
   - **Just store it** = the original request + `auto_deploy: false` + `picked_slot` + the spools + `confirmed_toolheads`
     for every printing head that is NOT a `feeds` entry (a spool leaving a printing head still asks about that head).
   - Both lists accumulate across rounds: add `unionConfirmFedHeads(prior, answer)` beside `unionConfirmHeads` in
     `inv_core.js`, or an idle head_fed answer followed by a print starting ping-pongs between two dialogs. Pin with a
     node-vm run across active_print → head_fed → active_print.
5. **Answers the current UI already shows correctly** (no work): `picked_slot_taken` (an error with the reason), the
   chain guard's "XL-1 started running #7 … use XL-1's Quick-Swap" (the existing 7 s "NOT deployed" warning).
6. **Test debt for 40.3**: the `NEEDS_CONFIRM` stub in `test_move_result_consumers_e2e.py` has no `confirm_type`
   (keep "missing ⇒ active_print" in the rewritten handlers, or update the stub deliberately); add a stubbed visual
   baseline for the three-way dialog (don't reuse the Quick-Swap ones).
7. **For 40.2** (heads-up): `test_toolhead_scan_single_spool.py::test_multispool_dryer_box_scan_still_sends_full_buffer`
   breaks once a box label opens the picker (every dev Max>1 non-tool row is a Dryer Box); re-point it at a fake
   Cart / Shelf row or rewrite it in 40.2's commit.

### Derek's answers (2026-10-14, afternoon) — build 40.3 this way

- **Enter on a printing-only "Just store it" dialog stores** (as on the fed dialog): a toolhead can't be loaded
  mid-print. His follow-up worry, the load you must remember after the print, is a buglist item ("A spool 'just
  stored' in a bound slot mid-print leaves a load to remember after the print").
- **Quick-Swap Deposit onto a fed head: one dialog, the three-way.** His scenario (load LR-MDB-1 slot 1 onto XL-1 and
  swap out the PolyDryer spool) IS "Load it instead": the body names #99 and where it goes ("XL-1 is running #99 (from
  PM-DB-2) … sends #99 back to PM-DB-2"); "Just store it" leaves #99 on XL-1. Nothing new.
- **A slot re-pointed to another head while the dialog was open asks again, even an empty idle head** (Derek
  overruled the default: multi-user awareness; he fills slot 1 because a slicer file depends on it). New in 40.3:
  every replay of a bound-slot question also sends the head the question named for the slot (e.g. `expected_feed:
  "XL-1"`; the answers already carry it in `fed_heads[].toolhead` / the `feeds` entry of `active_prints`); the doors
  thread it, and the engine answers a new question (nothing written) when `_slot_binding(box, slot)` differs, naming
  both heads ("LR-MDB-1 slot 1 now feeds XL-2 (it fed XL-1 when you were asked). Load #57 onto XL-2?"). Pin it with
  the existing rebind test plus an empty idle XL-2. The general audit is a buglist item ("Multi-user awareness").
- **Claude's calls kept:** (a) a spare whose 40.0d toast named LR-MDB-1 slot 1 is that slot's own spool ("scans to
  heads are effectively scans to the associated dry box, except transient boxes like the PolyDryer or the Prusa
  USS"); (b) Force Location into the feeding box stores the spool (Force Location is a last resort; easier
  non-barcode assignment to INDX heads is a buglist item); (c) auto-slot passes over non-head bindings (an unbound
  slot is a storage slot; lazily filling the next free slot, bound or not, is fine).

### As built (2026-10-14, evening): browser `d2f076f`, engine `4489cbf`

This replaces the pre-build "Today / Design / Tests / Risks" text (dropped by `d6cac7d`; recoverable from git).
The contract is in CLAUDE.md ("One move question, one replay builder, …"); this is the map.

**Browser (`d2f076f`).**
- **One dialog.** `window.confirmActivePrint` (inv_core.js) gained a three-way mode, used when the answer has a
  `title`: **Load it instead** (`.fcc-apc-yes`) · **Just store it in LR-MDB-1 slot 1** (`.fcc-apc-store`) ·
  **Cancel**. Enter stores (it cancels when the dialog offers no store), and an answer with `can_load: false`
  shows no Load button; Tab / ← / → move between the buttons; the QRs are `CMD:CONFIRM:<sid>` /
  `CMD:STORE:<sid>` / `CMD:CANCEL:<sid>` (`attachConfirmQRs` / `routeConfirmScan` gained STORE, and a stale STORE
  QR is guarded like a stale CONFIRM). While it is open, any other scan is held off with a 7 s warning
  (`window._fccOpenMoveQuestion`, read by `processScan`; `CMD:CANCEL` cancels it), and its host modal closing
  cancels it.
- **One router.** `window.askMoveConfirm(answer, ctx)`: `window.moveConfirmKind` sends `head_fed`, `feed_changed`
  and an `active_print` answer with `can_store` to `window.confirmHeadLoad` (the three-way); any other
  `active_print` (or a missing `confirm_type`) to the two-way confirm; anything else is a 7 s warning, nothing
  moved. Cancel: "Cancelled — nothing moved" + an INFO log line.
- **One replay builder.** `window.buildMoveReplay(door, original, answer, choice, prior)`: Load = the union of
  every answer's `fed_heads[].confirm_key` (`window.unionConfirmFedHeads`) + `window.unionConfirmHeads`; Store =
  `auto_deploy: false`, keys unchanged, only the printing heads that aren't a `feeds` entry, and a store stays a
  store in later rounds. Both send `expected_feed` (the answer's `feed`), `picked_slot` when the answer says
  `slot_picked`, and the spools the question named (`spool_id` at the slot scan, `spools` at `/api/smart_move`).
  It never re-applies `_doAssignFinalize`'s MMU 0-based correction: a replay re-sends the original `slot`.
- **Doors:** the slot-label scan and `performContextAssign` (inv_cmd.js); the Location Manager's
  `_doAssignFinalize` (via `_postManageAdd`; the DEPLOYED card's ↩️ now sends `auto_deploy: false`, so it no longer
  offers a load; `manualAddSpool` routes typed `LOC:` / `CMD:` text through `processScan`); Force Location
  (inv_details.js, split into the unassign and the add); the Quick-Swap ⬇️ Deposit (inv_quickswap.js). The deposit
  is ONE dialog: when the slot's head runs a spool or its printer prints, it posts at once and the server's
  three-way is the question; an idle, empty head keeps the deposit overlay. Its first request carries
  `expected_feed` (the tile's head, or "" for a Printer Pool tile; none for a single-slot box).

**Engine (`4489cbf`).** `expected_feed` → `confirm_type: "feed_changed"` (nothing written, even for an empty idle
head; since `f055def` a store replay is asked as a store, with no Load button); `target` / `slot_picked` / `feed` /
`can_load` on every question; the `identify_scan` slot branch relays every engine key; and the engine review's
deferred notes marked ✅ 40.3 below.

**The review's fixes (`f055def`).** `seen_printing` (the deposit sends the print it saw, so a fail-open probe still
asks); `printing` on every question; one unanswered dialog per overlay id (a replaced one is settled as
superseded, no false "Cancelled"); one deposit at a time; `window.storeToastTail` ("taken off XL-1"); a slot whose
own spool runs on another head takes no new spool; a printing answer offers the store only when the head the slot
loads is mid-print; "None" / "null" bindings read as unbound. Round trips through both halves:
`tests/roundtrip_harness.py` + `tests/test_move_question_round_trip.py`.

**Tests.** `test_head_load_confirm_js.py` (node-vm: the dialog, the router, the replay builder across rounds,
the Location Manager's recorded-source toast), `test_door_fed_heads_canary.py` (every POST to the three doors
sends `confirmed_fed_heads`, or is on the allow-list with a reason), `test_head_load_confirm_e2e.py` (route-stubbed
three-way: click, Enter, each QR; stubbed visual `head-load-confirm-fed.png`), `test_expected_feed_40_3.py` (the
engine and the three doors), the deferred-note pins in `test_fed_head_confirm_40_0c.py` and
`test_auto_slot_before_preflight_40_0e.py`; deliberate updates in `test_move_result_consumers_e2e.py`
(`PRINTING_STORE_Q`, the Force Location body) and `test_quickswap_deposit_and_header.py` (route stubs, so no run
can post a real deposit).

**Risks (kept from the design).**
- This is the prompt Derek meets on his own path. The same-slot swap (S2) and a blind first slot scan into an
  empty idle head (S1) must stay prompt-free: pinned (`test_the_slots_own_spool_coming_back_out_asks_nothing`,
  `test_a_first_slot_scan_never_gets_a_feed_change`).
- `routeConfirmScan` is on the scan hot path; its regex stays minimal and keeps the sid's case.
- Not from 40.3: S2's swap sends the old spool back into the box unslotted (`engine:s2-swap-old-spool-unslotted`,
  filed as a standalone buglist item).

## 40.4 — Force Location into a multi-slot box or a Printer row (D2.4, D3.1)

**Today.** `promptEditLocation` (`inv_details.js:942-1244`) posts `manage_contents add` with no slot and no confirm (`:1211-1216`). A `requires_confirm` answer shows *"Override failed"* (`:1236`). Group 39.5 adds the active-print yes-path (39.4's shared confirm, retry with `confirmed_toolheads`).

**Design.** After the Swal resolves with a location:
- a Dryer Box with Max > 1 → box picker, then `manage_contents add` with `slot`, handling `head_fed` / `active_print` through `_confirmHeadLoad`;
- a Printer row that is not its own head → printer picker (40.5);
- `CORE1` and everything else → today's path.

Leave the list filter as is: Printer rows stay listed because picking one now opens the picker.

**Tests.** Route-stubbed E2E extending `test_move_result_consumers_e2e.py::test_force_location_override_with_a_failure_shows_the_error`: picking LR-MDB-1 opens the picker; picking XL opens the printer picker; CORE1 posts directly.

**Dependency.** Built on 39.5's Force Location yes-path, which 39's own plan calls "the confirm step that picker calls". Without it this re-creates the same dead end for `head_fed`.

---

## 40.5 — The Printer picker (D3) and the `LOC:XL` Quick-Pick (item F)

**Today.** See the door table rows for `LOC:XL`, the XL deposit card, and Force Location / wizard.

**Design.**
- **Openers:**
  - `LOC:XL` with a buffered spool (`inv_cmd.js:1659`);
  - the deposit card on a Printer-row view (`inv_loc_mgr.js:1015`), whose QR is `LOC:XL`;
  - Force Location (40.4);
  - the wizard (40.7).
- **Flow (Derek's order):**
  1. Pick a head, or a pool slot.
  2. **Pool slot** → `perform_smart_move(box, [sid], target_slot)`. A `PRINTER:` sentinel never deploys (`logic.py:891-894`). Done.
  3. **Head H** → load confirm, client-side from the model plus the printer probe:
     - H printing or H has a resident → the confirm names the consequence (*"XL-3 holds #99 (from LR-MDB-1 slot 3). Load #42 instead? #99 goes back to LR-MDB-1 slot 3."*): **Load it instead** / **Cancel**;
     - no store option; a head is not storage.
     - An empty head on an idle printer → no prompt.
  4. **"Record it as coming from…"**:
     - asked only when the spool is not arriving from a box (`_ghost_trail_from` would give no trail);
     - options: every box slot bound to H, free ones selectable, claimed ones shown disabled with their holder, plus **No box**;
     - pre-select only when exactly one free slot exists;
     - if the only option is No box, skip the question and say so in the toast.
  5. POST `/api/smart_move {location: H, spools: [sid], confirmed_toolheads, record_source}`. The server still re-checks (39.1 destination, 39.4 source, `record_source` validation); a changed state reopens the confirm.
- **`CORE1`**: its own head with no pool → skip the head list and go straight to step 3 on CORE1, then step 4 (CR-MDB-1 slot 1 feeds CORE1).
- **Several buffered spools** → Q1, answered 2026-10-13: loop, one head or Printer Pool slot per spool, as in 40.2; Escape stops.
- **Item F, decided: fix now, frontend only.** In the empty-buffer branch (`inv_cmd.js:1694-1702`):
  - Quick-Pick only when the scanned row is single-occupancy by type (Tool Head / MMU Slot / No MMU Direct Load, a Printer row that is its own head, or any other row with `Max Spools == 1`) AND the item is a DIRECT resident (`!is_ghost && location === res.id`);
  - a Printer row like XL → `openManage('XL')`, whose Quick-Swap grid already shows every head;
  - the direct-only filter also stops `LOC:PM-DB-2` from picking up the ghost of a spool that is actually loaded on XL-2.
  - The flat prefix matcher that lists XL-n spools "at XL" is left for Group 37.

**Tests.**
- Hermetic engine: `record_source` validation (40.0d); Printer-row refusal (40.0a).
- Route-stubbed E2E:
  - `LOC:XL` + buffer → head list with residents and feeds;
  - pick XL-4 → record-as question lists LR-MDB-2 slot 1;
  - pick LR-MDB-1 slot 4 (pool) → posts a box move;
  - `LOC:XL` + empty buffer → manager opens, buffer unchanged;
  - `LOC:PM-DB-2` + empty buffer with only a ghost → no pickup;
  - CORE1 skips the head list.

**Risk.** Printer rows with no Quick-Swap grid data (no `printer_map` entry) → the picker must show *"XL has no registered toolheads"* instead of an empty list.

---

## 40.6 — Return slot picker (D5), Return display (item D), DEPLOYED ↩️ (item E)

**Today.**
- `/api/quickswap/return` resolves the head and resident (`routes_bindings.py:566-620`), then the box and slot:
  - `physical_source` first (`:639-648`, `found_slot = src_slot or None` at `:646`);
  - else the first binding (`:651-663`);
  - a taken slot becomes `None` (`:689-698`).
- The engine then auto-slots (`:711-714`); the landed slot is read back for the log and response (`:733-737`).
- The client preview re-implements that priority without occupancy or auto-slot knowledge (`_resolveReturnDestination`, `inv_quickswap.js:773-824`, slot `:812`) and names the slot at `:872`; the success toast is `${body.box}:SLOT:${body.slot}` (`:580`).

**Design.**
- **Server — one source of truth, no new route.** `POST /api/quickswap/return` gains three optional body fields:
  - `dry_run: true` → no write; answer `{action: "return_plan", toolhead, active_toolhead, spool, display, box, slot, source, needs_choice, options: <placement model, return mode>, recommended}`;
  - `slot` → the user's choice: a slot number, or `"none"`. Validate that it exists and is free at write time; a taken slot answers `return_slot_taken` with fresh options;
  - `expected_spool` → refuse `return_spool_mismatch` if the head's resident is not that spool.
- **Two paths.**
  - Recorded slot present and free → unchanged, one tap.
  - **Behaviour change to flag: a head spool with NO trail.**
    - **Today:** when its bound slot is free, it returns in one tap through the first-binding fallback (`routes_bindings.py:651-663`).
    - **After this change:** D5's "none recorded" covers it, so it opens the picker, pre-selected on that free slot. Enter or one slot-QR scan still finishes it.
    - **Why it will come up more often than today's data suggests:** 40.0d leaves more head spools without a trail.
    - Recorded in the decisions table. Derek can overrule it at manual check R4; the alternative is one tap when exactly one free slot in the box is bound to this head.
  - Otherwise, without `slot` → `return_choose_slot` with the options; nothing written. Status codes follow Group 39.8: answers that need the user (`return_plan`, `return_choose_slot`) are **200**; refusals (`return_slot_taken`, `return_spool_mismatch`) are **409**.
- **D5 recommendation:**
  1. a free slot in the box bound to `active_toolhead`;
  2. else a free pool slot (`PRINTER:<printer>`) or free unbound slot;
  3. else `none`.
- **Client.** `returnToolheadToSlot` (`inv_quickswap.js:826-892`) calls the dry run instead of `_resolveReturnDestination`.
  - `needs_choice` → return-mode picker (pre-selected recommendation, touch or slot QR, plus a **No slot** tile).
  - The confirm preview then names the chosen slot, or *"no slot — LR-MDB-1 will show 5/4"*.
  - `performReturn({toolhead, slot, expected_spool})`.
  - Toast: `↩️ #42 → LR-MDB-1 slot 2`, or `↩️ #42 → LR-MDB-1 (no slot)`. The route's log line (`routes_bindings.py:739-743`) says `(no slot)` too.
  - Retire `_resolveReturnDestination` once nothing calls it.
- **Item E, decided: route the DEPLOYED ↩️ through the canonical Return.** The card's spool is deployed to `item.deployed_to` (`spoolman_api.py:1498`).
  - `deployed_to` is a toolhead → `/api/quickswap/return {toolhead: deployed_to, expected_spool: item.id}`. It returns to the spool's recorded source, which is this box and slot, and inherits the D5 picker, the collision handling and Group 39.4's source check (the head is being emptied).
  - `deployed_to` is not a toolhead (a stale trail, like dev #99 in 2026-09-12) → `doAssign(box, id, slot, …, {auto_deploy: false})`, a plain "pull it back into this slot" with no chain. `manage_contents add` gains `auto_deploy` (40.0c).
  - Rationale: `auto_deploy=false` on `doAssign` alone would still empty a printing head with no probe (the destination is a box), and would duplicate Return's slot and collision logic.

**Tests.**
- Hermetic Flask-client, real engine (`test_active_print_chain_confirm.py::client` fixture pattern, `:258-262`):
  - dry run on a free recorded slot → no write, slot named;
  - taken slot → `return_choose_slot`, zero writes, recommendation = XL-3's free slot;
  - box with no free slot → recommendation `none`;
  - replay with `slot: "none"` → unslotted, response slot `null`, log says `(no slot)`;
  - replay with a slot taken meanwhile → `return_slot_taken`;
  - `expected_spool` mismatch → refused.
  - Keep the 29.B3 contract (`toolhead` = requested, `active_toolhead`, `requested`) on every new action.
- Route-stubbed E2E, replacing `test_move_result_consumers_e2e.py::test_return_overlay_previews_the_spools_recorded_source_box` (`:600`):
  - preview names the free recorded slot;
  - taken slot opens the picker;
  - the toast never contains `null`;
  - the DEPLOYED ↩️ on a grid card posts `/api/quickswap/return` with `expected_spool`;
  - test debt from Move-pipeline follow-ups item 6: the virtual-printer ghost filter in `_resolveReturnTarget`. The core1 branch reworked that function, but none of its tests mention ghosts.
  - Also take the `tests/test_return_overlay_and_refresh.py:168-175` restore assertion (Group 39.2) if 40.6 lands first.

**Dependencies.** Land after Group 39.2 / 39.4 (Return answers `return_requires_confirm` from the source check on the head it empties) and after `fix/core1-return-ejectall-guard`, which edits `_resolveReturnTarget` in the same file. The dry run should run the same source check, so the preview shows the printing banner before any picker opens.

---

## 40.7 — Wizard doors (item B's wizard bypass)

**Today.** Wizard create writes `location` at create (`routes_inventory.py:497-503`). Wizard edit diffs `location` as a plain key (`:633-636`) and PATCHes it (`:659-660`): no Smart Load, no active-print guard, no Printer-row refusal. The location list keeps Printer rows (`inv_wizard.js:1509`), so a CORE1 edit can put a second spool on CORE1.

**Design.**
- **Server — the edit path.** Pull a changed `location` out of the dirty diff. Save the other fields first (existing error handling), then apply the location with `logic.perform_smart_move(new_loc, [spool_id], origin='wizard_edit', target_slot=<slot from the payload>, confirm_active_print=<confirmed_toolheads>, confirmed_fed_heads=…, record_source=…)`. Answer `location_result` (the engine dict) alongside `success`. A `requires_confirm` or refusal leaves the other fields saved and says the move did not happen.
- **Server — the create path.**
  - A Printer row that is not its own head → refuse before creating (`printer_row` message).
  - A single-occupancy head (`CORE1`) with quantity > 1 → refuse ("a toolhead holds one spool").
  - Otherwise create unassigned, then place each spool through the engine (one per call), and report per-spool results.
- **Client.** Picking a Printer row or a Dryer Box with Max > 1 in the wizard's location combobox opens the matching picker immediately. The result is held in `wizardState` as a pending placement `{location, slot, record_source}` and shown as `XL-3 (via XL)` / `LR-MDB-1 slot 2`. On save, the wizard sends it and handles `location_result` with `_confirmHeadLoad` / the active-print confirm.
- **Rationale.** Routing through the engine closes the last door that writes a spool location without Smart Load (the one-spool-per-head principle). Opening the box picker in the wizard extends D2.4 (*"Force Location into a box behaves exactly like a box-label scan"*) to the third hand-written-location door. Veto it at manual check W1 if it gets in the way.

**Tests.**
- Hermetic Flask-client:
  - edit `location: 'CORE1'` while CORE1 holds #99 → #99 unloads home, CORE1 == [the edited spool], other fields saved;
  - edit to `XL` → refused, other fields saved, `location_result.blocked_reason printer_row`;
  - edit to `LR-MDB-1` slot 1 on a fed XL-1 → `requires_confirm head_fed`;
  - create quantity 2 onto CORE1 → refused, nothing created.
  - Keep `test_wizard::test_edit_spool_wizard`'s pre-edit `get_spool` mock (Group 38.7).
- Route-stubbed E2E: picking XL in the wizard opens the printer picker; the saved payload carries the pending placement.

**Risks.**
- `api_edit_spool_wizard` is a documented write surface (CLAUDE.md table): update its row. Keep the `SYSTEM_MANAGED_EXTRAS` strip (`routes_inventory.py:620-630`); the engine owns those keys.
- The 24.F manual-weight log (`:669-674`) must still see the weight diff.

---

## Engine review (2026-10-14, `wf_6946f24e-3da`): deferred notes

The review confirmed 28 findings. The 2 orange and 5 yellow ones are fixed in `db1952a`. These 21 notes
are real but low-risk; take them with the sub-task that touches the same code (refs are `lens:id` in the
workflow journal).

- ✅ 40.3 (`4489cbf`). **fed_seen counts a resident the fed check skipped as 'left', so if it returns during the probe the chain unloads it without asking** (`engine:fed-seen-includes-left`). Fix: Build fed_seen only from the residents whose record still said bound_th (asked about, or classified as the slot's own spool).
- **Bulk Move still skips a spool filed on a head-less one-slot Printer row as 'loaded in a toolhead slot', against item H** (`engine:headless-printer-bulk-skip`). Fix: In the bulk plan's skip, count as loaded only a real head: in printer_map, or a row whose Type is in TOOLHEAD_TYPES (equivalently, _holds_one_spool and not is_printer_row_not_head).
- **Not from this diff: Derek's same-slot swap (S2) sends the old spool back into the box unslotted, so the box over-counts** (`engine:s2-swap-old-spool-unslotted`). Fix: Out of scope for this branch. File it as a standalone follow-up: either the chained Smart Load treats the resident whose trail is the slot being filled as leaving the box, or Derek decides where a swapped-out spool goes.
- **target_slot '0' now means 'no slot', but the Location Manager's 0-based MMU Slot grid sends 0 for its first slot** (`engine:slot-zero-dropped`). Fix: Either drop the 0-based correction in _doAssignFinalize (inv_loc_mgr.js:1462-1470), or keep the slot for MMU Slot rows.
- **40.0d's claimed-slot check compares slots raw, while the rest of the move normalizes them** (`engine:free-feed-slots-raw-compare`). Fix: Compare `_norm_slot(effective_slot(...)) == _norm_slot(slot)`, and normalize _feed_slots_for's slot.
- **Read cost: each bound-slot scan pays one more full spool-list GET (the head is now listed three times per scan), and step 3 pays one full-list GET per candidate head instead of the spec's single bucket read** (`io:daily-path-read-cost`). Fix: Optional. At step 3, make one strict full-list fetch and bucket it for [box, *bound heads] with bucket_spools_by_location(spools=...), feeding the memo.
- ✅ 40.3 (`4489cbf`). **The picked-slot race refusal blames 'checking the printer' even when no printer was asked, and picked_slot_taken says 'taken' for a slot that no longer exists** (`io:race-refusal-text-says-printer`). Fix: Say '…was filled by #77 meanwhile…' unless the memo shows a live probe.
- ✅ 40.3 (`4489cbf`). **The head_fed body loses "XL is PRINTING … so FCC stops charging this print to #99" whenever the fed head isn't a 'feeds' entry in active_prints** (`protocol:fed-text-drops-print-consequence`). Fix: For the fed sentence, take the fed head's printer state from the probe memo whatever the confirm or role, and keep the charging clause.
- ✅ 40.3 (answers carry `target` / `slot_picked` / `feed`; every door replays through `window.buildMoveReplay`). **A 40.3 replay can't be built from the answer alone: no pick-vs-named flag, no target, and the Location Manager replay still drops picked_slot** (`protocol:answer-cannot-drive-a-shared-replay`). Fix: In 40.3, thread picked_slot through _doAssignFinalize the way performContextAssign and Force Location do.
- ✅ 40.3 (CLAUDE.md's 40.3 bullet, the chain-guard exception and the unseat row). **CLAUDE.md's move-confirm convention and the slot-unseat row don't describe 40.0c/40.0e, and one sentence in them is now wrong** (`protocol:claude-md-door-contract-drift`). Fix: Extend CLAUDE.md:62 with the 40.0c door contract: the key-presence stale rule (checked before Group 39's), confirm keys, picked_slot, the head_fed shape, and the chain-guard exception.
- ✅ 40.3 (`test_a_pre_39_page_asked_a_fed_question_hears_the_fed_reload`). **The stale-rule order (fed before Group 39) is correct but no test pins it** (`protocol:stale-rule-order-unpinned`). Fix: Add one test, parametrized over the three doors, that sends {confirm_active_print: true} with a head_fed answer and asserts the fed message.
- ◐ 40.3 (`d2f076f`): the ↩️ now sends `auto_deploy: false`, so it offers no load; 40.6-E's reroute still stands. **Known item 40.6-E: the deployed card's ↩️ RETURN SPOOL is still a silent round trip, and its answer now advertises a load/store choice** (`protocol:lm-return-round-trip-now-offers-store`). Fix: Land 40.6-E's reroute before 40.3's three-way dialog reaches doAssign.
- **The HEAD-proof notes get HEAD's actual failure wrong for 4 of the 40.0e tests and some 40.0c ones, and two test docstrings repeat the wrong history** (`tests:head-proof-records-misdescribe-head`). Fix: Rewrite those docstrings from a real HEAD run, counting signature-only failures as controls.
- ✅ 40.3 (`test_the_lowest_slots_question_answered_load_and_store`). **No pin for the two 40.3 replays of a head_fed question about an auto-picked slot** (`tests:auto-picked-head-fed-replays-unpinned`). Fix: Extend test_auto_slot_before_preflight_40_0e.py:201 with both replays.
- **40.0d's rule that one unreadable feed box voids every candidate is unpinned; the blip test can't tell it apart from skipping that box** (`tests:free-feed-all-or-nothing-unpinned`). Fix: Add the TWO_FEEDS case with TST-MDB-1 unreadable, expecting nothing recorded and no recorded_source.…
- ✅ 40.3 (`4489cbf`: no chain to a non-head, and the ghost guard covers it). **The chain for a slot bound to something that isn't a head has no pin; with an explicit slot, a binding to a missing head still moves the spool out of the box and reports a deploy** (`tests:non-head-binding-chain-unpinned`). Fix: Chain only when loads_head (`bound_toolhead = bound_th if loads_head else None`), with a WARNING such as 'slot 1 is bound to XL-9, which isn't a toolhead'.
- **Nothing pins 40.0a's "refused before any read"; the tests only check that nothing is written** (`tests:printer-row-before-reads-unpinned`). Fix: In test_a_printer_row_that_is_not_a_head_takes_no_spool, use a counting FakeSpoolman and assert zero get_spool calls and zero list reads.…
- ◐ 40.3: (a), (b) pinned and (d) commented; (c) stays for 40.5. **Several narrow branches have no pin, and two are unreachable as wired** (`tests:narrow-branches-unpinned`). Fix: Pin (a) with a probe stub that moves the resident away, and (b) with picked_slot '9'.
- ◐ 40.3: the comment is true now that a 40.3 page sends the key; the full sweep is still due before `dev`. **The `scan` fixture comment says a current page sends confirmed_fed_heads (none does until 40.3), and e8a2706 records no full E2E run for its frontend change** (`tests:scan-fixture-comment-and-e2e-record`). Fix: Reword the comment to 'as a 40.3 page sends it', and run the full sweep before merging.…
- **Tests coupled to read order and to another test module, plus one artificial race state** (`tests:fragile-coupling`). Fix: Move the shared rows into move_engine_harness or a fixtures module.
- ✅ 40.3 (`d2f076f`: the toast, pinned in `test_head_load_confirm_js.py`). **The 13.6 recorded feed slot is still silent on the Location Manager's toolhead assign, and nothing pins that path** (`tests:lm-toolhead-recorded-source-toast`). Fix: When that follow-up lands, mirror the inv_cmd.js toast in _doAssignFinalize and add a node-vm pin like test_reverse_binding_40_0d_js.py.…

---

## Decisions taken in this doc (not asked of Derek), with rationale

| Question | Decision | Why |
|---|---|---|
| Does a same-slot swap count as "fed from elsewhere"? | **No** | Derek's words are "somewhere else". The slot's own spool coming back out is his normal switch-out. |
| Does a trail-less resident count? | **Yes, prompt** | FCC cannot tell where it is fed from; a silent unload is worse than one tap. |
| Offer "Just store it" during a print on an empty head? | **Yes** | His 2026-09-12 sync case; storing never touches the head. Needs 40.0b. |
| New prompt on toolhead-QR scans / Quick-Swap taps? | **No** | The user names the head; both are Derek's main paths. |
| Quick-Swap grid ⬇️ Deposit into a bound slot? | **Prompts when the head is fed from elsewhere** (40.3) | It posts the slot label through the slot-label route (`inv_quickswap.js:637`), and the spool chains onto the head. Only the swap tile names the head directly. |
| Printer picker: prompt when the chosen head has ANY resident (40.5 step 3)? | **Yes**, broader than D2's "fed from elsewhere" | The Printer picker has no "this slot", so there is no same-slot swap to exempt. Picking a head that holds a spool always unloads it. |
| Auto-slot for callers without a picker (40.0e) | **Move it ahead of the pre-flight**, using the picker's recommendation rule | Keeps slotless moves slotted, and makes their confirm cover the chain. Retiring it would bring back "5/4". |
| Return of a head spool with no trail whose bound slot is free (40.6) | **Opens the picker**, pre-selected on that slot | D5's "none recorded", read literally; one extra Enter. Derek can overrule at R4. |
| Single-slot boxes as 13.6 reverse-binding candidates (40.0d) | **Never** (lands in 42.1 step 5) | A PolyDryer's blank slot always reads as free, so a stranger would be recorded as its spool. |
| 13.6 reverse-binding | **Keep silent for scans; record only with exactly one free slot; name it in the toast; explicit choice in the Printer picker** | D3's pre-select rule applied everywhere, without slowing blind scanning. |
| DEPLOYED ↩️ (item E) | **Canonical Return** (fallback: move back into the slot without deploy) | One Return path, one set of confirms, no duplicated slot logic. |
| `LOC:XL` empty buffer (item F) | **Fix the scan now; matcher waits for 37** | A frontend guard, independent of the LocationID model. |
| Wizard bypass | **Route location changes through the engine; wizard opens the pickers** | Last direct location writer; D2.4 by extension. |
| Picker data | **One server model, exact-location matching, probe separate** | Fast open, testable hermetically, immune to the Group 37 matcher change. |

---

## Dependencies and build order

| Depends on | Why |
|---|---|
| **[Group 39 — Confirm on Every Door](39-confirm-on-every-door.md)** | 39.1 scoped confirms (`confirmed_toolheads`, `active_prints`) and the test-harness extraction; 39.2 Return re-check and the I1-06 gate (40.0b); 39.3 `withPrinterCheck`; 39.4 source guard and the shared confirm; 39.5 Force Location yes-path; 39.7 fail-closed resident read. 40.0c, 40.3, 40.4 and 40.6 build on them. **Build 39 first** (its own plan says the same). |
| **[Group 42 — single-slot box lifecycle](42-single-slot-box-lifecycle.md)** | Both groups edit the PRINTER MOVE branch and the Smart Load block of `_perform_smart_move_impl` (`logic.py:605-816`). **Build 42 before 40.** From 42 this group needs: <br>• the slot-1 normalization (42.2), which makes 40.3's same-slot comparison correct for PolyDryers; <br>• the 13.6 single-slot exclusion (42.1 step 5), which 40.0d builds on; <br>• the stateful locations store this group's tests reuse; <br>• 42.5b (eject mode + a location scan), which fixes the `inv_cmd.js` location-branch order before 40.2 and 40.5 rewrite that branch. |
| `fix/core1-return-ejectall-guard` (`1fb5678` + `76398cb`, local only) | Edits the Return route (`_printer_row_toolheads`), `_resolveReturnTarget` and Eject All. 40.6 builds on it, and so does 40.0a's shared classifier. Merge to `dev` first. |
| `test/sweep-reds-hermetic` (`d785444`, local only) | Fixes the PM-DB-1 fixtures and the Quick-Swap grid snapshot. This group's visual tests must be stubbed from day one, not copies of those fixtures. Merge to `dev` first. |
| [Group 41 — Honest Bulk Results](41-honest-bulk-results.md) | No hard dependency. 41.6 (a rejected unseat refuses to seat the incoming spool) edits the slot-assignment block that 40.2's Swap / Overwrite relies on: merge order only. |

**Recommended order across the four groups:** 39 → 41 → 42 → 40 (see Cross-plan notes).

**Order inside the group:** 40.0 (a → b → e → c → d) → 40.1 → **40.3** (Derek's path; get his manual check early) → 40.2 → 40.4 → 40.5 → 40.6 → 40.7. Commit each sub-task separately; run the offline suite after each, and the full sweep (with the E2E) before merging to `dev`.

---

## Cross-plan notes (Groups 39–42, reviewed 2026-09-13)

### Recommended build order across the four groups

The full reasoning is in [Group 39's Cross-plan notes](39-confirm-on-every-door.md).

0. Merge `fix/core1-return-ejectall-guard` (`1fb5678`, `76398cb`) and `test/sweep-reds-hermetic` (`d785444`) into `dev`. Both are local only.
1. Ask Derek the three contract-shaping questions first: Group 41's Q1, Group 39's Q1 and Group 42's Q-B (all three answered 2026-09-18). This doc's Q1 and Q2 can wait for 40.2 (both answered 2026-10-13).
2. Build in this order: Group 39, then Group 41, then Group 42, then **Group 40** (this group, last). Group 40 goes last because:
   - it is the largest group;
   - it builds on 39.1, 39.3, 39.4 and 39.5, and on 42.1, 42.2 and 42.5b;
   - most of it protects other users.

   Inside it, build 40.3 early, and get Derek's S1–S6 checks before the pickers.

### Overlaps that concern this group

**The pre-write contract.**
- Group 39.1 defines the order and the one `requires_confirm` shape: `active_prints` + `fed_heads` + `can_store` + `target_slot`.
- Where this group's sub-tasks sit in that order:
  - 40.0a is step 2;
  - 40.0e is step 3;
  - 40.0c is steps 4–5;
  - 40.0d is step 6.

**One Printer-row classifier.**
- These three answer the same question, "is this a Printer row that isn't its own toolhead?":
  - 40.0a's `locations_db.is_printer_row_not_head`;
  - Group 41.1's `eject_all_block_reason`;
  - 40.5's Quick-Pick check in `inv_cmd.js`.
- The core1 branch's `_printer_row_toolheads` (`routes_bindings.py:275` on `76398cb`) moves into `locations_db` beside it, with an `inv_core.js` mirror.

**From Group 42.**
- The effective slot (42.2).
- The 13.6 single-slot exclusion (42.1 step 5).
- The stateful locations store for tests.
- The location-scan check order (42.5b).

**One strict "direct residents" reader.**
- Group 39.7 builds it, and it serves 40.0c's fed-head read.
- The picker model (40.1) classifies by exact location, from one `bucket_spools_by_location` fetch.

**The frontend confirm component.**
- 40.3's `_confirmHeadLoad` wraps Group 39.4's `window.confirmActivePrint`.
- It adds a STORE action to `attachConfirmQRs` / `routeConfirmScan` (`inv_core.js:387`, `:459`).
- Group 39's Q1 sets its keyboard default.

**The waiting UI.** 40.1's per-printer "checking…" tiles use 39.3's `withPrinterCheck` and `fetchPrinterStateDetailed`, including its `no_credentials` reason.

**The `inv_cmd.js` location-scan branch (`:1652-1719`).**
- 40.2, 40.5 and 40.1's `routePickerScan` hook (`:1408`) follow the check order in [Group 42.5b](42-single-slot-box-lifecycle.md).
- 42.5b lands first.

**The Return route and overlay.**
- They are also touched by the core1 branch, 39.2 (server re-check), 39.8 (status codes) and 42.1 (release on Return).
- Three of these edit `performReturn` (`inv_quickswap.js:571-582`). 40.6 goes last.

**Move-pipeline follow-ups item 6 (test debt).**
- This group takes `not_deployed` in the confirmed slot-QR replay, and `auto_deploy_skipped` in `_doAssignFinalize` (40.3).
- It also takes the virtual-printer ghost filter (40.6).
- Eject / Return item 5's restore assertion lands in 39.2, or in 40.6 if that comes first.

**The read-only count before 40.0c.**
- It is the same GET that Group 42.1 and 41.3 want: head spools with no trail, and non-head spools with a trail.
- Do it once.

**Group 34.**
- 40.1 reuses Group 34's tree picker as its keyboard and mount reference (`inv_loc_mgr.js:2100-2234`).
- It adds a "never during a bulk session" guard next to L298's.
- No conflict with S5 or the auto-generated-id slice.

**Group 37.**
- The flat first-segment matcher (`spoolman_api.py:1467`) stays; 40.5 only stops acting on `LOC:XL`'s prefix contents.
- Slot-to-toolhead onboarding stays with 37 (D2.5).
- For `Max Spools "0"`, see 42.7.

**Group 35.** No conflict. Placement keys on LocationID and `toolheads[]`, while Group 35 keys settings by printer Name.

**Shared test pins.**
- `test_l316_charact_bindings_errors.py` (39.2, 39.8, 40.6);
- `test_active_print_chain_confirm.py:637` (40.0d; 42.6 keeps it green);
- `test_move_result_consumers_e2e.py` `:535` / `:600` (39.5, 40.4, 40.6);
- `test_confirm_chain_reshow_e2e.py` (39.6, 39.9, 40.3);
- `test_auto_slot_pick.py` (40.0e);
- `test_route_table_pin.py` (40.1's new route).

---

## Overlap: Group 37 (Location System Redesign) and L271 Phase 5

- **Slot→toolhead onboarding belongs to Group 37** (Derek, D2.5). The picker's optional "re-map slots from here" (D2.1: *"Possibly allow re-mapping slots from there (optional; may be out of scope)"*) is **deferred to 37**. The picker only links to the existing Feeds editor, so onboarding has one home and one UX. Add a cross-reference line in `37-location-system-redesign.md` when this group starts.
- **Should NOT wait for 37:** D2, D3 and D5 key on `Type`, `Max Spools`, `slot_targets` and `toolheads[]`. None of that depends on 37's open fork 1 (the LocationID model), and none needs a forced relabel. Slot labels stay `LOC:<box>:SLOT:<n>`; `CMD:SLOT:<n>` keeps working.
- **Waits for 37:**
  - the flat first-segment matcher that makes `get_contents('XL')` list XL-n spools (37 root cause, `spoolman_api.py:1467`; fork 2 makes contents transitive and grouped) — 40.5 only stops acting on it;
  - any structure-aware placement into carts or rows.
- **`Max Spools "0"` on a Dryer Box:** the flag for Group 37 lives in one place, [Group 42.7](42-single-slot-box-lifecycle.md). For this group it means a Dryer Box with `0` skips the picker (whose test is `Max > 1`) and behaves as a PolyDryer.
- **L271 Phase 5 prefix retirement shipped** (Group 34, `2b16869`): the alias was deleted, and the matchers deliberately stay flat. Printer-map prefix grouping was ruled out of scope there (P5 decision (b)). Three consumers still group heads by `startsWith(prefix)`: `_resolveReturnTarget` `inv_quickswap.js:747-753`, `openBindSlotPicker` `:1117-1121`, and `get_bindings_for_machine` `locations_db.py:1805-1808`. **This group enumerates heads from `toolheads[]`**, so the Core One and any future non-prefixed printer work without waiting for a prefix retirement.

---

## Test conventions for this group

- **Allowed command** (from `inventory-hub/` in the group's worktree): `"C:/Python314/python.exe" -m pytest <paths> -p no:cacheprovider -q --offline`. The route-stubbed E2E files skip there and run in the full pre-merge sweep.
- **Shared harness.** Group 39.1 extracts `FakeSpoolman`, `WireSpoolman`, `_probe_for` and `_run` from `tests/test_active_print_chain_confirm.py` (`:114-305`) into `tests/move_engine_harness.py`. Reuse it; if 40 is built first, create it under that name. This group needs two additions:
  - reuse Group 42's stateful in-memory locations store (42 is its first real user and builds before 40). It patches `load_locations_list` / `save_locations_list` so that the real `attach`, `detach` and `set_dryer_box_bindings` run, instead of `_run`'s fixed return values at `:280-283`. Create it here only if 40 somehow lands first;
  - keep the probe patched BELOW the per-move memo (`prusalink_api._probe_printer_state`).
- **Real engine only.** No new test mocks `perform_smart_move`, `perform_smart_eject` or `_perform_smart_move_impl`.
- **Prove every new hermetic test fails on HEAD:** `git archive HEAD inventory-hub | tar -x -C <scratch>`, copy the new test files in, run them, and record the failure reason in the commit message.
- **Pin changes in the same commit** as the behaviour change, with the reason in the docstring (the L316 contract).
- Python 3.9 syntax in backend modules; module-qualified collaborator calls; patch helpers on their defining module (CLAUDE.md).

---

## Manual checks for Derek (add to the handoff checklist)

Dev container, after the branch is merged to `dev`. Empty the scan buffer before each row unless it says otherwise.

| # | Check | Steps | Pass if |
|---|---|---|---|
| S1 | **Slot label, empty idle head** (your path) | XL-2 empty and XL idle. Buffer a spool, scan `LOC:LR-MDB-1:SLOT:2` | Loads onto XL-2 with no new prompt |
| S2 | **Slot label, same slot's own spool** (your path) | XL-3 runs a spool that came from LR-MDB-1 slot 3. Buffer a new spool, scan `LOC:LR-MDB-1:SLOT:3` | No new prompt; the old spool goes back to LR-MDB-1, the new one is on XL-3 |
| S3 | **Slot label, head fed from a PolyDryer** | Load a spool from PM-DB-2 onto XL-1 (scan it, then the XL-1 QR). Buffer another spool, scan `LOC:LR-MDB-1:SLOT:1` | A prompt names the PolyDryer spool and offers Load it instead / Just store it / Cancel. Try **Just store it**: spool in slot 1, XL-1 unchanged. Repeat with **Load it instead**: PolyDryer spool back in PM-DB-2, new spool on XL-1 |
| S4 | **Scan the choice** | Repeat S3 and scan the on-screen QRs for each choice instead of clicking | Each QR does what its label says; Cancel writes nothing |
| S5 | **Printing prompt offers store** | While the XL prints, scan a slot label for an empty head | The printing banner shows with the store option; Just store it leaves the head alone |
| S6 | **Deposit, head fed from a PolyDryer** | As in S3, XL-1 runs the PM-DB-2 spool. Open XL-1 → Quick-Swap grid → ⬇️ Deposit a buffered spool into `LR-MDB-1` slot 1 | The same three-way prompt as S3. Just store it leaves XL-1 alone |
| B1 | **Box label opens the picker** | Buffer one spool, scan `LOC:LR-MDB-1` | Picker shows 4 slots with contents, `→ XL-1…XL-3`, `🏭 Printer Pool` on slot 4, and a ⭐ recommendation |
| B2 | **Pick by scanning** | In B1's picker, scan `LOC:LR-MDB-1:SLOT:4` | Slot 4 is selected; confirming stores the spool (no deploy) |
| B3 | **Keyboard and cancel** | Open B1 again: arrows, a number key, Escape | Highlight moves and wraps; Escape closes; the spool stays in the buffer |
| B4 | **Other scans are held off** | With a picker open, scan a spool label | A warning says to finish or cancel the picker; nothing else happens |
| F1 | **Force Location into a box** | Spool details → Force Location → `LR-MDB-2` | The picker opens instead of silently picking a slot |
| P1 | **Printer picker** | Buffer one spool, scan `LOC:XL` | Lists XL-1…XL-5 (what's on each, which slots feed each) plus the Printer Pool slots; "Checking XL…" shows until the printer answers |
| P2 | **Record it as coming from** | In P1 pick an empty XL-4 | Asks to record it as from LR-MDB-2 slot 1 (pre-selected if it is the only free one) or no box; the toast names the choice |
| P3 | **Pool slot only stages** | In P1 pick LR-MDB-1 slot 4 | Spool is in LR-MDB-1 slot 4; no head changes |
| P4 | **`LOC:XL` with an empty buffer** | Empty buffer, scan `LOC:XL` | Opens the XL view; nothing is picked up into the buffer |
| P5 | **CORE1 stays loadable** | Force Location → `CORE1` | No head list; loads CORE1 (after a prompt if CORE1 already holds a spool) and asks about CR-MDB-1 slot 1 |
| P6 | **Printer offline** | With the XL powered off, repeat P1 | "Checking XL…" then a plain "couldn't reach XL" message, never a frozen screen |
| R1 | **Return, recorded slot free** | Return a spool deployed from LR-MDB-1 slot 3 | One tap; toast `→ LR-MDB-1 slot 3` |
| R2 | **Return, recorded slot taken** | Put another spool in the slot first, then Return | Picker opens with a recommendation; choosing No slot gives a toast that says `(no slot)`, never `SLOT:null` |
| R3 | **DEPLOYED card ↩️** | Open LR-MDB-1, press ↩️ on a DEPLOYED card | The spool comes back into that slot and stays OFF the head |
| R4 | **Return, no recorded slot** (a call made for you) | XL idle, XL-3 empty. Put a spare spool in `LR-MDB-1` slot 3. Force Location another spare onto XL-3; slot 3 is taken, so no home is recorded. Move slot 3's spool to a shelf. Then open XL-3 → ↩️ Return | The picker opens with slot 3 pre-selected, and Enter returns the spool there. **Tell us if you'd rather this stay one tap** (today's behaviour) |
| W1 | **Wizard to a Printer row** | Edit a spool, set location `XL` | The printer picker opens; saving places it on the chosen head. If the picker gets in your way here, say so (veto point) |
| W2 | **Wizard onto a loaded CORE1** | Edit a spool, set location `CORE1` while CORE1 holds a spool | The old spool goes home; CORE1 never holds two |
| T1 | **Toolhead QR unchanged** (your path) | Buffer a spool, scan an idle, loaded XL head's QR | Swaps as today, no new prompt; toast says which slot was recorded |

---

## Open questions for Derek

### Q1 — Several spools in the buffer when a box label or `LOC:XL` is scanned — ✅ ANSWERED 2026-10-13: (a) loop

**Derek chose (a), loop (2026-10-13).** One scan of a multi-slot box's label or a Printer row's label opens the picker once per buffered spool, top first, and each spool still gets its own load confirms; Escape stops the loop and the rest stay in the buffer. For `LOC:XL` (or `LOC:RCOI`) each spool picks a head or a Printer Pool slot. Build it that way; the background below is kept for the record.

**Background.** The pickers place ONE spool. Today, a box-label scan with several buffered spools puts all of them in the box with no slot, because the engine only auto-picks a slot for a single spool (`logic.py:554`). That is exactly the floating "5/4" state you called "what went wrong". A Printer-row scan today sends the whole buffer to the row.

**Where you'd meet it.** Mostly other users. You would only meet it if you buffered several spools and scanned a box's own label.

**Worked example.** Buffer holds #150, #151 and #152. LR-MDB-2 (2 slots: 1 → XL-4, 2 → XL-5) is empty. You scan `LOC:LR-MDB-2`.
- **(a) Loop (recommended).** The picker opens for #150 and recommends slot 1. You confirm, and it reopens for #151, recommending slot 2. For #152 the box is full, so it shows "no empty slot" and lets you swap into an occupied slot or stop; #152 stays in the buffer. Escape stops at any point.
- **(b) Top spool only.** #150 goes into the slot you pick. #151 and #152 stay in the buffer until you scan again.
- **(c) Keep today's behaviour** for multi-spool buffers (all in, unslotted). The picker only opens when one spool is buffered.

For `LOC:XL`, (a) means picking a head (or pool slot) per spool, because each head holds one.

**Default if unanswered:** (b), the least surprising. _(No longer applies: Derek chose (a) on 2026-10-13.)_

### Q2 — What the box picker offers when the box is full — ✅ ANSWERED 2026-10-13: (a), same as the grid

**Decided 2026-10-13 (Claude's call; Derek reviewed it and didn't object): (a), the same as the Location Manager grid.** A full box shows no ⭐, and tapping or scanning an occupied slot asks Swap / Overwrite exactly as the grid does (now `inv_loc_mgr.js:1269-1285`), so the incoming spool always gets a real slot; there is no "store without a slot" tile and no refusal. Build it that way; the background below is kept for the record.

**Background.** D2 says the picker "recommends a slot … without assuming one exists", but not what happens when no slot is free. The Location Manager grid already answers a tap on an occupied slot with **Swap** (the old spool goes to your buffer) or **Overwrite** (the old spool stays in the box, unslotted) (`inv_loc_mgr.js:1212-1228`).

**Where you'd meet it.** Scanning a full box's label with a spool buffered, or Force Location into a full box.

**Worked example.** CR-MDB-1 has all 4 slots filled (slot 1 feeds CORE1). #160 is buffered and you scan `LOC:CR-MDB-1`.
- **(a) Same as the grid (recommended).** Tapping slot 3 asks Swap / Overwrite. Swap puts #160 in slot 3 and puts slot 3's spool in your buffer. No unslotted option is offered.
- **(b) Grid choices plus a dimmed "Store without a slot"** tile, which warns that the box will read 5/4.
- **(c) Refuse.** "CR-MDB-1 is full — take a spool out first."

Tapping slot 1 (the CORE1 feed) additionally runs the load prompt, since the swapped-in spool would deploy.

**Default if unanswered:** (a). _(No longer applies: (a) was decided on 2026-10-13.)_

---

## Files expected to change

| Area | Files |
|---|---|
| Engine | `inventory-hub/logic.py` (`_perform_smart_move_impl`, a Printer-row helper, 13.6 refinement) |
| New module | `inventory-hub/placement.py` (placement model + recommendations; add a CLAUDE.md module-map row) |
| Routes | `routes_bindings.py` (`/api/placement_options`, Return `dry_run` / `slot` / `expected_spool`), `routes_scan.py` (`manage_contents add` flags, slot-label flags), `print_deduct.py` (`/api/smart_move` flags), `routes_inventory.py` (wizard create/edit through the engine), `app.py` (re-export) |
| Frontend | new `static/js/modules/slot_picker.js`, plus the template include (find where `inv_quickswap.js` is loaded); `inv_cmd.js`, `inv_core.js` (`attachConfirmQRs` / `routeConfirmScan` STORE), `inv_loc_mgr.js`, `inv_quickswap.js`, `inv_details.js`, `inv_wizard.js`, `ui_builder.js`, `shortcuts_registry.js` entries |
| Tests | `tests/move_engine_harness.py` (shared; created by 39.1), `test_slot_picker_engine.py`, `test_placement_options.py`, `test_return_slot_choice.py`, `test_wizard_location_through_engine.py`, `test_slot_picker_e2e.py` (+ stubbed visual), `test_route_table_pin.py`, deliberate pin updates |
| Docs | CLAUDE.md write-surfaces rows (`api_edit_spool_wizard`, Return, `manage_contents add`), module map, keyboard shortcut notes |
