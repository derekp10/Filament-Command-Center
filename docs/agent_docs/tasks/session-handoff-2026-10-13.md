# Session handoff — 2026-10-13 overnight run (unattended)

Plan and rules: [overnight-run-2026-10-13.md](overnight-run-2026-10-13.md). This file is the running log;
it is updated after every milestone and committed on `dev` at every merge.

## Morning summary

_In progress — the run started at `dev` @ `c895d36` (the plan commit, on top of `e818d0c`)._

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

## Parked

_Nothing parked yet. In flight (checkpoint 02:47, updated as units land):_

- **Group 46** — merged (`36d7318`); see Landed.
- **Standalone fixes** — `fix/standalone-2026-10-13` @ `f9f9982`, worktree `<scratchpad>/wt-standalone`
  (backend only). Review done (1 finding, fixed in `f9f9982`). Next: bring onto `dev` in the main tree → offline +
  targeted E2E → merge.
- **Group 43** — `feature/group-43-deduct-recovery` @ `cb0ed16`, worktree `<scratchpad>/wt-g43`: 43.1, 43.5, 43.6,
  the harness extraction and 43.3 (backend + `cancel_review.js` picker) committed; 39 hermetic pins + deduct suites
  green. 43.3's E2E file (`test_cancel_review_picker_e2e.py`) is written but NOT yet run (needs the main tree).
  Next: bring into the main tree → run E2E → review → sweep → merge.

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

## To push

Nothing has been pushed tonight (rule 2). Waiting on `dev`, oldest first:

- `e818d0c` docs(buglist): file Group 47's two leftovers
- `c895d36` docs(tasks): plan for the unattended 2026-10-13 overnight run
- `6eba7d7` docs(handoff): start the run log
- `36d7318` Merge Group 46 (+ its three branch commits) and the docs commit after it

## Budget log

| Workflow | Unit | Agents | Tokens | Notes |
|---|---|---|---|---|
| `wf_0e44faf0-934` review-group-46 | Group 46 | 5 (4 lenses + 1 batched skeptic) | 1,311,429 subagent | 41 min, 311 tool calls; 13 findings → 12 confirmed + 1 plausible, 0 refuted, all fixed |
| `wf_4a2dec42-133` review-standalone | Standalone fixes | 4 (3 lenses + 1 batched skeptic) | 828,479 subagent | 35 min, 229 tool calls; 1 finding, confirmed (low), fixed |
