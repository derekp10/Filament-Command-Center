# Group 51: 🔒 Move & Archive Integrity

**Branch name (when started):** `feature/group-51-move-archive-integrity`
**Estimated effort:** MEDIUM (~6–10 h, 1–1.5 sessions). 51.1 ~1–2 h · 51.2 under 1 h · 51.3 ~1 h · 51.4 minutes · 51.5–51.7 ~3–5 h · tests throughout.
**Risk:** **MEDIUM.** `update_spool` is the hottest write path (every move, deduct and weigh-out passes through it), and 51.5–51.7 extend the move engine's pre-write contract: extend a step, never reorder it (the comment block in `_perform_smart_move_impl`; CLAUDE.md "Move confirms name their heads").

> **Status: `TODO` — filed 2026-10-19 (`/refresh-groups`) from the "🟡 Group 40 leftovers" and Derek's multi-user item. No Derek decision needed.** Planned FIRST in the bundle run with Groups 48, 49 and 52 ([bundle-2026-10-19.md](bundle-2026-10-19.md)): 51.1 is a real bug on the hot write path, so it gets the engine-lens review.
> **Theme: a move does what the screen showed, and nothing else.** Every decision: [refresh-2026-10-19.md](refresh-2026-10-19.md).
> Code anchors were read on `dev` @ `c5c5aa6` (the refresh's grounding) and spot-checked at `08c4b10`. Line numbers drift, so re-grep before editing.

## ⚠️ Read this first

- **Drive the real engine in tests** ([[mocked engine hides chain bugs]]): no mocked `perform_smart_move`; a faithful fake Spoolman that mirrors `update_spool`'s merge, cap and archive edges (`tests/move_engine_harness.py` / `FakeSpoolman` where they exist).
- **Prove each new test red on the base** (`git archive` into a scratch dir).
- **Every new request field is optional** (absent = no check), so a page opened before the release keeps working, as with Return's `expected_spool`.
- **Guard only the accidental case** (Derek, [[no hard stop on corrections]]): refuse and refresh when what the dialog showed changed; a deliberate retry just works.
- Container runtime is Python 3.9.

## Items covered (quoted from `Feature-Buglist.md`)

| # | Buglist item | Direction |
|---|---|---|
| **51.1** | "🟡 Group 40 leftovers" (1), filed 2026-10-19: *"Moving a hand-archived spool unarchives it. `spoolman_api.update_spool`'s refill edge treats any write without `archived: True` as a refill, so an engine move (Force Location, a scan, the wizard) of a spool archived by hand that still has weight left un-archives it."* **Wider than filed:** the `ID:` label-verify scan does it too. | Only a weight write is a refill (fix in `update_spool`). |
| **51.2** | Same item, (2): *"'Stored only' on Return's slot chooser. A slot that feeds a different head shows that head and its spool, but Return only stores there; the tile could say so."* | The return-mode tile says "stored only". |
| **51.3** | Same item, (3): *"The ghost-guard refusal has no `blocked_reason`. The wizard's `_pick_refused` recognises '<box> slot <n> still holds #…' by its wording… a `blocked_reason: slot_claimed` at both refusal sites in `logic.py` (the question path and step 6) would be cleaner."* | `blocked_reason: "slot_claimed"` at both sites; the wizard checks the reason. |
| **51.4** | Same item, (5), the one live note of the deferred engine-review notes: 40.0d's raw slot compare. | Compare through `_norm_slot`. |
| **51.5–51.7** | Derek, 2026-10-14 ("🟡 Multi-user awareness"): *"One user might not be aware"* that another changed something while a dialog was open… *"Audit the other doors for the same pattern (Quick-Swap, Return, Bulk Move commit, the wizard)."* | The doors that still send less than they showed: the Quick-Swap tap (51.5), the Printer picker's head pick (51.6), the Location Manager grid's Swap (51.7). |

**Already done, not in this group:** the multi-user item's first case (a re-pointed slot is asked again, `feed_changed`, Group 40.3, `logic.py:2255-2257`); Return and the wizard already send what they showed (Return pins the spool and slot; the wizard sends `expected_feed`).
**Elsewhere:** the leftovers' (4), a Return chooser spanning two boxes that feed one head → [Group 37](37-location-system-redesign.md). The multi-user item's door 4, the Bulk Move commit vs its preview (`logic.py:3824-3862`), waits for Bulk Moves to be switched on (the buglist's "🔀 Bulk Move polish"). The extra full spool-list read per bound-slot scan (leftovers (5)) is a [Group 52](52-spoolman-read-load.md) note. **Left parked:** (5)'s MMU Slot grid sending a 0-based first slot while `'0'` means "no slot" (dormant: no MMU Slot rows exist) and Bulk Move's skip via `_holds_one_spool` (dark on prod); the open test-hygiene notes in `40-slot-picker.md`.

## Decisions

- **No Derek decision.** Claude's calls, offered for veto on 2026-10-19 (none vetoed): *"A move or an `ID:` label scan never un-archives a spool you archived by hand; only a weight change that leaves weight on it does"* (his example: archive a spool by hand with 300 g left, Force Location it onto `CR-CT-2-R1`; today it comes back into stock and may jump back to where it sat before it was archived; after the fix it moves and stays archived), and *"Quick-Swap, the grid's Swap and the Printer picker send the spool they showed; if it changed meanwhile, FCC refuses and refreshes instead of moving a spool you weren't shown."*
- This matches Derek's 43.2 answer: an archived spool stays archived.

## Today's code (anchors, `dev` @ `c5c5aa6`)

### 51.1 — the refill edge (a real bug, wider than filed)
- `_auto_unarchive_on_refill` (`spoolman_api.py:282-330`) un-archives any archived spool with weight left unless the payload says `archived: True`. When the write carries no `used_weight` it takes the record's (`:306-307`), so a **location- or extra-only write counts as a refill**, and it also restores `fcc_pre_archive_location`.
- Hit by **every engine move** (`_move_write` sends `location` + `extra` only, `logic.py:1616-1625`) and by the **`ID:` label-verify scan's** extra-only write (`routes_scan.py:1165-1166`).
- Only the wizard re-archives afterwards (`_keep_archived`, `routes_inventory.py:1050-1061`); only the Location Manager's assign refuses an archived buffered spool (`inv_loc_mgr.js:1555-1560`). The deduct already sends `archived: True` for an archived spool (Group 43.2, `_deduct_payload`).

### 51.2 — Return's chooser
- Return sends `auto_deploy: false` (`routes_bindings.py:1277`), but a free slot that feeds another head isn't `stores_only`: `_stores_only` counts only the head the spool leaves and its own deployed-from slot (`placement.py:193-200`). So the return-mode tile shows "→ XL-2" and that head's spool, with no "stored only" note (`slot_picker.js:339-350`).

### 51.3 — the ghost-guard refusals
- Neither carries a `blocked_reason`: the question path (`logic.py:2386-2393`) and step 6 (`logic.py:2688-2696`). The wizard recognises them by their wording (`_pick_refused`, `routes_inventory.py:623-645`), pinned by `test_a_named_slot_whose_own_spool_runs_on_a_head_is_a_refused_pick`.

### 51.4 — 40.0d's slot compare
- The free-feed-slot check compares `effective_slot(…) == slot` without `_norm_slot` (`logic.py:890-891`).

### 51.5–51.7 — doors that send less than they showed
- **51.5 Quick-Swap tap:** the confirm names the slot's spool (`inv_quickswap.js:1117-1129`) but the request sends only toolhead, box and slot (`:1099-1103`). The server re-checks the binding (`routes_bindings.py:1432-1444`) and then loads **whatever spool is in the slot now** (`find_spool_in_slot`, `:1449`).
- **51.6 Printer picker head pick:** it asks "XL-3 holds #99" in the page (`_confirmHeadPick`, `inv_cmd.js:2211-2227`) but sends only the head (`inv_cmd.js:2407-2414`), so a **different resident is unloaded without asking**.
- **51.7 Location Manager grid Swap:** sends `slot` + `swap: true` (`inv_loc_mgr.js:1578-1592`), not the spool it showed.

## Design, by sub-task

### 51.1 — only a weight write is a refill
- Fix in `update_spool`, not in `_move_write` (label-confirm and other extra-only writes hit it too): a write is a refill only when it carries `used_weight` or `initial_weight`. Quick Weigh, weigh-out, wizard weight edits and the Group 42.3c restore keep working; a location- or extra-only write never un-archives.
- Then `_keep_archived` can likely go; keep it if a test shows the wizard's own save still needs it.
- Update the CLAUDE.md write-surface table's `/api/spool/update` and `logic.py` rows in the same commit.

### 51.2 — "stored only" on Return's tiles
- In return mode, mark every slot `stores_only` (Return never loads), or word the tile "stored here, not loaded": a small `placement.py` / `slot_picker.js` change.

### 51.3 — `blocked_reason: "slot_claimed"`
- Add it at both sites; `_pick_refused` checks the reason, not the wording. Update the pin.

### 51.4 — `_norm_slot`
- Compare both sides through `logic._norm_slot`.

### 51.5–51.7 — send what was shown; refuse and refresh when it changed
- **51.5:** `/api/quickswap` takes an optional `expected_spool`; when the slot's spool differs, answer 409 `quickswap_spool_mismatch` (the shape of Return's `return_spool_mismatch`) and the grid refreshes.
- **51.6:** the head pick sends the residents it showed (the fed-head confirm-key idea, "XL-3#99", fits); the engine refuses (the picker reopens) when the head's strict resident list differs, at the step that already reads residents strictly (Group 39.7). Extend that step; don't add a new one.
- **51.7:** the grid's Swap sends `expected_occupant`, checked against the strict slot read (Group 41.6).
- All three optional: absent = today's behaviour.

## Tests (real engine, no mocked `perform_smart_move`; each proven red on the base)

- A hand-archived spool with weight left **keeps `archived` and its place** after a Force Location move, a slot-label scan, an `ID:` label-verify scan and the Undo of such a move. A weigh-out that leaves weight still un-archives (`tests/test_archive_unarchive_helpers.py` pins); the 42.3c restore still lands.
- Return chooser: a slot that feeds another head reads "stored only".
- `blocked_reason` on both refusals; the wizard drops a refused pick by its reason.
- Quick-Swap: 409 when the slot's spool changed; no check without the field.
- node-vm: the picker and the grid send the expected fields; the engine refuses a changed head or slot and writes nothing.
- The door canaries (`tests/test_door_fed_heads_canary.py`, `tests/test_door_to_buffer_canary.py`) updated deliberately.

## Risks

- `update_spool`: every move, deduct and weigh-out passes through it; the 42.3c unarchive redirect must keep working.
- The pre-write contract's order (CLAUDE.md; the comment block in `_perform_smart_move_impl`).
- Pages opened before the release: every new field optional.
