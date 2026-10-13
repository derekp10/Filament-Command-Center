# Session handoff — 2026-10-13 overnight run (unattended)

Plan and rules: [overnight-run-2026-10-13.md](overnight-run-2026-10-13.md). This file is the running log;
it is updated after every milestone and committed on `dev` at every merge.

## Morning summary

_Checkpoint 07:40. The run started at `dev` @ `c895d36` (the plan commit, on top of `e818d0c`)._

- **Landed on `dev` (nothing pushed):** Group 46 (`PARTIAL`, only 46.3 left), both standalone fixes, and Group 43
  (`PARTIAL`: 43.1, 43.5, 43.3's review-card spool picker and 43.6, plus 16 fixes from its adversarial review;
  43.2 and 43.4 left). Each merge passed offline, targeted E2E and, where the frontend changed, a triaged full sweep.
- **Group 39 (confirm on every door):** on `feature/group-39-confirm-on-every-door`, **fully built** (39.1-39.9
  plus 43.4) and tested (offline + the E2E files for every changed door). Its adversarial review found 16
  confirmed issues (3 medium); I'm fixing those now, then the full sweep, then the merge (see Parked).
- **Needs you:** the Questions below (15, each with my recommended answer); the manual checks; and pushing `dev`.

## Landed

### Group 46 — Quick-Fix Sweep → `PARTIAL` (merged `36d7318`)

- **Commits:** `0d2cd8d` (46.1, 46.2, 46.4, 46.5), `986a1d4` (review fixes), `bb2f755` (shortcuts-overlay baseline).
- **What changed for you:**
  - **46.1** The DEPOSIT card now always deposits the spool in the centre of the carousel, and its label changes
    the moment you press ◀/▶. I reproduced your report first (a delayed fetch + a quick click deposited the
    previous spool on the old code).
  - **46.2** Enter saves the location editor from any field; "t" + Enter on the Type dropdown no longer scans "t".
  - **46.4** The `feeder_map` boot import no longer re-binds a box whose slots you cleared.
  - **46.5** A blank Location ID is refused; the editor won't open your blank TestCart row (it says to delete it and
    re-add it); 🗑️ on that row now actually deletes it. I did not delete it.
  - From the review: the **Quick-Swap deposit** now writes the spool its confirm named (it could deposit a different
    one if you rotated the carousel during the ~3 s printer check); a late refresh can't repaint another location
    under you; a barcode scanned into an editor text field is a scan, not a saved name; confirm prompts name the
    spool they move.
- **Tests:** every new pin was proven red on the old code. `--offline`: 1891 passed, 1 red (the TestCart row).
  Full `RUN_INTEGRATION` sweep: 28 failed / 2697 passed / 1 error in **41:40** (quiet baseline 26:17; my review
  workflow ran beside it). Triage: 2 expected TestCart reds; the error was a dev-Spoolman read timeout; **21
  passed in isolation**; 1 was the `?`-overlay visual baseline (recaptured, it grew by the new row); **4 flake
  identically on `dev`'s code** (`test_prusament_new_scan_opens_prefilled_add_wizard` and three
  `test_wizard_auto_prefill_empty_weight` tests, 5 samples each side), so they're pre-existing.
- **Review:** 5 agents, 1.31M tokens, 13 findings → 12 confirmed + 1 plausible, 0 refuted, all fixed.
- **Left:** 46.3 (Question 1 below).

### Standalone fixes → done (merged `b7ed885`)

- **Commits:** `545562d` (both fixes), `e481987` (review fix), plus a CLAUDE.md convention line.
- **Bulk Moves flag:** with `fcc.bulkMove.enabled` off, `POST /api/bulk_move` now answers 403, a server-side
  `CMD:BULKMOVE` scan no longer arms a session, and an armed session only answers `CMD:CANCEL` (a scanned
  `CMD:DONE` used to commit it). Prod is dark, so this changes nothing you'd see there.
- **`slot_targets` readers:** one malformed Dryer Box row can no longer break moves onto toolheads, the Quick-Swap
  bind picker and Return, the Feeds save, single-slot attach/detach, toolhead deletes, or every toolhead removal in
  Settings. The review caught that my migration made a hand-edited `false` binding auto-deploy to a location named
  "FALSE"; fixed.
- **Tests:** `--offline` 1921 passed, 1 red (TestCart). Targeted E2E for every touched surface: 252 passed,
  1 failed (`test_feeds_section_hidden_for_non_dryer_box`: 5/5 in isolation; it also failed in the Group 46 sweep
  before this code existed). Backend-only, so no full sweep (the plan's rule).
- **Review:** 4 agents, ~828K tokens, 1 finding (confirmed, low), fixed.

### Group 43 — Deduct Recovery & Attribution → `PARTIAL` (merged `985aba8`)

- **Commits:** `da55081` (43.1), `dcf8bc8` (43.5), `0c12aa6` (43.6), `491713d` (the shared
  `tests/deduct_wire_harness.py`), `a3533b4` (43.3), `aa59e14` (CLAUDE.md rows), `380fd42` (the review's fixes),
  `dbcee3b` (buglist / working-groups / banner).
- **What changed for you:**
  - **43.1** A spool with no weight of its own (it inherits its filament's) is now charged and recorded correctly; it
    used to record 0 g while the full grams landed, a double charge waiting to happen once shortfalls are
    recoverable.
  - **43.5** Deduct log lines name the printer and toolhead (`✔️ 🦝 Core One INDX RCOI-2: auto-deducted 7.4g …`).
  - **43.3** Every line on a review card has a picker: the spool that was on a head when FCC logged the print, one on
    a head now, or any spool by #id. This is your job-1104/1105 case: a print sliced for T0 that you ran from T1.
  - **43.6** Retrying a cancel review whose first write timed out (but landed) no longer charges twice.
  - From the review: a retry no longer loses a print's grams after a later print charged the spool; a redirected
    retry row can't double-charge; a timed-out-but-landed **completion** deduct is now counted (pre-existing hole);
    a near-empty pick previews amber and reports what it couldn't take; "Another spool by #ID" actually finds spools
    (it said "not found" for every one); a stale card can no longer drop the review; charging an archived spool keeps
    it archived and where it is.
- **Tests:** every new pin was proven red on the pre-fix code (14 of 15 review pins; the 15th guards that a refusal
  stays narrow). `--offline` 1975 passed, 1 red (TestCart). Targeted E2E 14 passed. Full `RUN_INTEGRATION` sweep:
  13 failed / 2806 passed / 35 skipped in **36:42**. Triage: the 2 TestCart reds; **10 passed 5/5** on the quiet
  container afterwards; and `test_doassign_does_not_shift_buffer_on_failed_response`, an order-dependent flake: 2/5
  in the same 11-test batch on the branch AND 2/5 with every Group 43 product file swapped back to `dev`'s, 10/10
  solo. ⚠️ Part of the sweep overlapped my own small test runs in the Group 39 worktree, which I stopped once I
  noticed (the load lesson in memory).
- **Review:** 5 agents, 1.35M tokens, 32 raw findings → 15 confirmed + 1 plausible, all fixed.
- **Left:** 43.2 (Question 2) and 43.4 (with or after Group 39.4).

## Parked

- **Group 39** — parked; see below. (Groups 46 and 43 and the standalone fixes all landed; see Landed.)

### Group 39 — Confirm on Every Door → parked on `feature/group-39-confirm-on-every-door`

The branch is checked out in the main tree, rebased on `dev` @ `d9f954b` (after Group 43). It was started in a
scratchpad worktree while Group 43 owned the main tree; that worktree is now detached and can be deleted.
**Everything below is tested** unless the row says otherwise: `--offline` 2028 passed (the TestCart red only), and
the 21 E2E files that drive a changed door pass apart from two Quick-Swap button tests that fail only after other
tests (3/3 solo). Every new pin was proven red on `dev`'s code first. No adversarial review or full sweep yet.

| Commit | Sub-task | What it does | Pin |
|---|---|---|---|
| `8074d0c` | 39.1 prep | The real-engine move harness, extracted to `tests/move_engine_harness.py` | (refactor) |
| `0a47e42` | 39.1 engine | `confirm_active_print` is True / falsy / **a list of head ids**; `_uncovered_active_heads` asks ONE confirm and never probes a covered head; the shared answer shape; the pre-write contract comment block | `test_scoped_confirm_39_1.py` |
| `8390b39` | 39.7 | Smart Load's resident list is read **strictly**: a Spoolman blip refuses the load instead of stacking two spools on one head | `test_smart_load_fail_closed_39_7.py` |
| `fb7a077` | 39.4 engine | **Ask before moving a spool OFF a printing head (D6)**, in your wording ("#42 is loaded on XL-3. Moving it to CR-CT-2-R1 means FCC stops charging this print to it. Continue?"); an unreadable record fails closed | `test_source_confirm_39_4.py` |
| `e92440a` | 39.2 engine | A named slot's binding is walked only when the move deploys (I1-06) | `test_bound_slot_walk_39_2.py` |
| `804ca88` + `9360ff6` | 39.6 | `_eject_destination` (pure, the code `perform_smart_eject` runs); ejecting a homeless spool off a printing head is ONE prompt and one Yes, not three | `test_one_eject_confirm_39_6.py`, `test_one_yes_answers_both_print_and_unassign` |
| `364c035` + `1c92673` + `81ebc7c` | 39.1 wire, 39.2 routes | The five move doors read `confirmed_toolheads`; a bare legacy `true` covers no head; Quick-Swap and Return re-check on the server (`quickswap_requires_confirm` / `return_requires_confirm`); every Yes sends the UNION of heads confirmed so far. ⚠️ `364c035` says "UNTESTED" in its message; `1c92673` and `81ebc7c` are its tests | `test_confirmed_heads_routes_39_1.py`, the flipped pins |
| `98748d5` | 39.9 | `CMD:TRASH` while a bulk move is armed explains instead of opening a confirm behind the panel | `test_trash_scan_during_a_bulk_move_opens_no_confirm` |
| `5810179` + `3ce3c43` | 39.8 | Quick-Swap/Return failures answer 409; a non-JSON answer reads "server answered 502" | the failure-toast E2E (5) |
| `a446bcc` | 39.5 + the shared confirm | `window.confirmActivePrint` (inv_core.js), the one shared active-print confirm; Force Location gets a yes-path through it | 3 Force Location E2E |
| `e7818e0` | 39.3 backend | `/api/printer_state` answers `no_credentials` for a printer with no login (it said "unreachable") | `test_printer_state_reasons_39_3.py` |
| `ee89219` | 39.2 test hygiene | The Return-overlay test's restore asserts it landed (it was a silent `try/except`) | — |
| `70d1bd9` | docs | CLAUDE.md: "Move confirms name their heads", plus the two engine rows | — |
| `715c352` | 39.4 frontend | The Location Manager and scan-assign confirms render through `window.confirmActivePrint` (their DOM ids kept) and show the server's D6 message when the backend asked. The scan-path canary now counts guard LINES (counting occurrences let inv_cmd.js's Shift+B line alone satisfy the old minimum) | `test_the_shared_active_print_confirm_owns_the_enter_guard` |
| `d7164e9` + `cf31aeb` | 39.3 client | The "⏳ Checking XL…" pill (after 300 ms; "XL didn't answer" + a WARNING past 3 s), `fetchPrinterStateDetailed`, the overlay's "FCC has no login for XL" / "Couldn't reach XL" line, the dim's label on slot scans and buffer location scans. The Quick-Swap visuals stub the new probe seam (baselines unchanged) | 4 E2E with the fetch-delay lever, `test_printer_check_budgets_39_3.py` |
| `795529c` | 43.4 | A cancel review keeps every head: a head with no spool (emptied mid-print, the everyday case once D6 lets you move a spool off a printing head) is carried as `unresolved_usage` with the heads at the end; the card offers 43.3's picker for it (`{position, sid, grams}`), and whatever nobody picks is the job's reported shortfall instead of vanishing | `test_cancel_review_keeps_every_head_43_4.py`, 2 picker E2E |

**Next, in order:**

1. **Fix the review's 16 confirmed findings** (`wf_d989c332-cda`; the medium ones first): a same-printer
   "feeds" sentence the message dropped; the Quick-Swap deposit re-ask showing stale text instead of the
   server's; a `spool_changed` completion review dropping its empty heads (the 43.4 hole on the other path);
   plus 13 lows (a stale pre-39 browser tab looping on a bare `true`; the dim label naming no printer before
   the printer map loads; a double tap leaking a keydown handler; a bulk commit refusing a whole batch on one
   unreadable spool; the slot-QR replay missing a second ask; an LM head-to-head move asking twice; a stale
   cancel-review row deleting the review without its ledger entry; four test-hygiene items).
2. The full `RUN_INTEGRATION` sweep, then merge. The group merges only whole (the plan's rule).
3. Small leftovers: the "no login" line could link to Config's credentials grid; the scratchpad worktree
   (`git worktree list`) is detached and can be removed with `git worktree remove --force <path>`.

Known E2E flakes met on this branch, all pre-existing (A/B'd, or passing solo): `test_doassign_buffer_safety`
(`..._swap_pushes_displaced_only_on_success` 2/5 here vs 3/5 with `dev`'s `inv_loc_mgr.js`), the two
`test_deployed_flag_preservation` Quick-Swap button tests and `test_escape_key_walks_out_of_three_level_stack`
("`#manageModal` never opened" after other tests; they pass solo), and a 5 s server read timeout in
`test_empty_slot_disabled_when_buffer_empty`.

## Notes from the run

- **An accidental ~11-minute full-suite run (03:18–03:30).** A command meant to re-run only the Group 46 sweep's
  reds had a broken `sed` expression, so its test list came out empty and pytest started the whole suite
  (`RUN_INTEGRATION`, against dev). I stopped it and killed the orphaned pytest process. Mid-test kills skip
  fixture teardown, so I checked: in that window `hub.log` shows only `PM-DB-1`/`PM-DB-2` borrowed and restored,
  no location rows created or deleted, and all four `DEV_BOX_BINDING_BASELINES` boxes read `{}` live afterwards.
  `TST-MDB-1` reads `{}` too; its last writes were at 03:16 during the real sweep, which set and restored it.

- **43.1 exposure count (read-only):** dev Spoolman has **0** active spools without their own `initial_weight`
  (237 active). The **prod** count could not be run: the read-only `GET http://192.168.1.29:7912/api/v1/spool`
  was denied by the session's permission classifier, and I didn't route around it. The check, for whoever runs
  it (GET only): in `GET :7912/api/v1/spool?allow_archived=false`, count spools whose `initial_weight` is null,
  and of those, the ones whose `location` is a toolhead (a Tool Head row, or a `toolheads[].location_id` on a
  Printer row in prod's `locations.json`). 43.1 is safe either way: it changes behaviour only for a spool with
  no `initial_weight` of its own.

## Questions for Derek

Each one blocks only its own item; nothing here holds up a release. My recommended answer comes first.

1. **46.3 — How should Printer Status label a toolhead?** A display preference (`fcc.printerStatus.toolheadLabel`)
   for showing a head as its full id (`XL-1`), a bare number, or a tool name. The open part is the tool name:
   - **Recommended: "Tool 1" (1-based).** It matches the printer's own screen and the Feeds dropdown, which is
     where you look while loading.
   - "T0" (0-based) matches the gcode, which you rarely read.
   *Group 46 ends `PARTIAL` on this one item.*
2. **43.2 — When a print's shortfall review comes up and the spool it should charge was auto-archived at 0 g
   (job 1104: spool #99 took 34.2 g of 61.32 g and was archived; 27.12 g went nowhere), where does the top-up go?**
   - **Recommended:** the shortfall card uses 43.3's spool picker. It defaults to the spool that was loaded on
     the head when the print ended. If that spool is archived, the card asks you to pick another one (the joined
     spool, in the SpoolJoin case). Picking an archived spool charges it anyway (it stays archived) rather than
     unarchiving it.
   - Alternative: unarchive the picked spool and charge it.
3. **Group 41 Q3 — Bulk Move's "the source is printing" prompt can never appear** (it is checked after every
   loaded spool is already skipped).
   - **Recommended: A, remove it** and its fake test. Bulk Move stays "never moves a loaded spool"; a real mid-print
     move goes through a single move, which asks.
   - B: make it cover staged box slots bound to a printing head. C: leave it (dead but harmless).
4. **Group 41 Q4 — Deleting a Room also unassigns the spools in its boxes and shelves** (by name prefix), although
   those child rows survive.
   - **Recommended: C, refuse to delete a Room that still has locations inside it** ("LR still contains LR-MDB-1, …
     — move or delete them first"). A delete records no Undo.
   - A (today's reach, minus toolheads; the default if unanswered). B: only spools filed on the Room itself.
5. **Group 42 Q-A caveat (blocks 42.6)** — you chose "the PolyDryer follows its spool head-to-head", but asked FCC not
   to forget where the spool lived *before* the box (e.g. a cart). `physical_source` holds one level today.
   - **Recommended:** a separate "before the box" field written when a spool enters a single-slot box, and restored
     when it leaves the box. It's smaller than a general "last non-container location" on every move, and it doesn't
     change how any other move records its source.
   - Alternative: record the last non-container location on every move (wider, touches every move branch).
   *Group 42 itself waits for Group 41.*
6. **Group 40 Q1 — Several spools in the buffer when you scan a box label or `LOC:XL`.**
   - **Recommended: (a) loop.** The slot picker opens once per spool, recommending the next free slot each time.
   - (b) places only the top spool and leaves the rest in the buffer. This is the default if unanswered.
7. **Group 40 Q2 — What the box picker offers when the box is full.**
   - **Recommended: (a) the same as the grid:** tapping an occupied slot asks Swap / Overwrite. This is also the
     default if unanswered.
8. **Group 44 — the design pass (what identifies a printer).** It needs a no-code design session with you before any
   build. **Recommended:** run it together with Group 37's fork 1 (next item). The answer to "a stable id, not the
   Name and not the LocationID prefix" should match fork 1's answer for locations.
9. **Group 37 fork 1 — Is the human-readable composite LocationID still the right model?**
   - **Recommended:** keep every existing id and label as-is (NO FORCED RELABELING), but stop deriving structure from
     the string. The composite becomes a display label and scan alias, and `parent_id` becomes the only source of
     hierarchy. That's a smaller, safer change than swapping the id model, and Group 34's Phase 0 already started it.
10. **The weight-undo decision** — Undo reverts moves only; after a weigh-out it reverts the last *move*, and since
    2026-06-15 its empty message says so.
    - **Recommended: keep Undo move-only.** Wiring weight-undo touches all six weight surfaces, needs a typed undo
      stack, and must reconcile with the print-deduct ledger so an undone weigh can't double-count.
11. **Group 45.3 — The dark-contrast guard ignores a translucent text colour**, and fixing it immediately flags the
    OFFLINE printer chip (4.41:1, under the 4.5:1 bar).
    - **Recommended:** land the guard fix together with the CSS change: the chip's text alpha goes 0.45 → 0.50
      (5.29:1, which you won't see).
12. **Group 45.4 — `test_feeds_section_save_with_some_slots_none` can never run** (its box has 1 slot).
    - **Recommended:** widen one baseline box (PM-DB-1) to 2 slots in dev `locations.json` and register it in
      `DEV_BOX_BINDING_BASELINES`. It needs your OK because it edits dev `locations.json`.
13. **Group 45.5 — Three tests still borrow your real dev bindings.**
    - **Recommended:** convert each to fixed baselines (`borrow_box_bindings`). First answer: is TST-MDB-1's
      `{"1": "PRINTER:XL"}` binding deliberate? And should the printer-status widget test get stubbed data rather
      than clearing every dryer box?
14. **Group 45.6 — Refresh dev from prod.**
    - **Recommended:** a scripted, read-only-against-prod `--refresh-from-prod` that copies `locations.json` and
      the Spoolman inventory but keeps the dev-only fixtures (the baseline boxes, the virtual test spools). Explicitly
      not urgent.
15. **Dev's blank-LocationID `TestCart` row** — your repro for 46.5. It is the only cause of the two standing sweep
    reds (`test_locations_json_integrity`, `test_location_combobox_highlights_current_selection_on_focus`).
    - **Recommended:** delete it now that 46.5 has shipped the repair path: Location Manager → its 🗑️ → "Delete the
      location with a blank Location ID ("TestCart")?". I left it alone, as you asked.

## Manual checks for Derek

Belt-and-braces: each of these already has an automated test that fails on the old code.

| # | Check | Steps | Pass if |
|---|---|---|---|
| 46-a | **Deposit follows the carousel** | Put 3 spools in the buffer. Open a toolhead (or any shelf) in the Location Manager. Press ▶ next, then click ⬇️ DEPOSIT HERE straight away. Repeat while a print is running (the slow case) | The card's spool name changes the instant the centre card does, and the spool deposited is always the centre one |
| 46-b | **Type + "t" + Enter saves** | Location Manager → ✏️ a location → click the Type dropdown → type `t` → Enter | The location saves and the editor closes. No "Unknown code t" error |
| 46-c | **Enter saves from any field** | Same editor, cursor in Friendly Name → Enter | Saves |
| 46-d | **Blank ID refused** | ➕ Add Location → leave Location ID empty → 💾 Save | Toast "Enter a Location ID before saving."; nothing is saved |
| 46-e | **Delete dev's TestCart row (only if you want it gone)** | Location Manager → the TestCart row's 🗑️ | The prompt reads "Delete the location with a blank Location ID ("TestCart")?"; Yes removes only that row. The two standing sweep reds then clear |
| 43-a | **A review charges the head the print really ran on** (the task file's check) | The next `no_spool` review for an INDX print you started from a different head than it was sliced for → 🛑 Review → on its T-line pick the spool on the head it really used → Apply | The deduct lands on that spool (Activity Log names the printer and head), nothing on the sliced-for head |
| 43-b | **"Another spool by #ID" finds the spool** | Any review card → a line's picker → "Another spool by #ID…" → type a real spool id, Tab away | The line shows the spool's name and location (it used to say "not found" for every spool) |
| 43-c | **A near-empty pick says what it can't take** | On a review row, pick a spool with less left than the row's grams | The row's preview turns amber at once; Apply charges what fits and a warning names the grams nobody took |

## To push

Nothing has been pushed tonight (rule 2). Waiting on `dev`, oldest first:

- `e818d0c` docs(buglist): file Group 47's two leftovers
- `c895d36` docs(tasks): plan for the unattended 2026-10-13 overnight run
- `6eba7d7` docs(handoff): start the run log
- `36d7318` Merge Group 46 (+ its three branch commits) and the docs commit after it
- `b7ed885` Merge the standalone fixes (+ its three branch commits) and the docs commit after it
- `985aba8` Merge Group 43 (+ its eight branch commits) and the docs commit after it

Not for pushing yet: `feature/group-39-confirm-on-every-door` is a local, parked branch (it lives in a scratchpad
worktree; see Parked).

## Budget log

| Workflow | Unit | Agents | Tokens | Notes |
|---|---|---|---|---|
| `wf_0e44faf0-934` review-group-46 | Group 46 | 5 (4 lenses + 1 batched skeptic) | 1,311,429 subagent | 41 min, 311 tool calls; 13 findings → 12 confirmed + 1 plausible, 0 refuted, all fixed |
| `wf_4a2dec42-133` review-standalone | Standalone fixes | 4 (3 lenses + 1 batched skeptic) | 828,479 subagent | 35 min, 229 tool calls; 1 finding, confirmed (low), fixed |
| `wf_4573e3ac-aca` review-group-43 | Group 43 | 5 (4 lenses + 1 batched skeptic) | 1,346,059 subagent | 34 min, 236 tool calls; 32 raw findings → 15 confirmed + 1 plausible; the 16 refuted were duplicates (15) or not a defect (1); all 16 fixed |
| `wf_d989c332-cda` review-group-39 | Group 39 | 5 (4 lenses + 1 batched skeptic) | 2,022,606 subagent | 49 min, 431 tool calls; 22 raw findings → 16 confirmed (3 medium), 6 refuted (all duplicates) |
