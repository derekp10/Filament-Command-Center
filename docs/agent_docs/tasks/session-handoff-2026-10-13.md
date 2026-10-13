# Session handoff — 2026-10-13 overnight run (unattended)

Plan and rules: [overnight-run-2026-10-13.md](overnight-run-2026-10-13.md). This file is the running log;
it is updated after every milestone and committed on `dev` at every merge.

## Morning summary

_Checkpoint 09:35. The run started at `dev` @ `c895d36` (the plan commit, on top of `e818d0c`)._

- **Everything in the queue up to Group 39 landed on `dev` (nothing pushed):** Group 46 (`PARTIAL`, only 46.3
  left), both standalone fixes, Group 43 (`PARTIAL`: only 43.2 left), and **Group 39, all nine items, plus 43.4**.
  Each merge passed offline, targeted E2E and a triaged full sweep where the frontend changed.
- **Group 39 changes what you see during a print:** every move that touches a printing head asks once, names
  the heads it touches (a spool LEAVING a printing head now asks too, in your D6 wording), and FCC shows
  "⏳ Checking XL…" while it waits on a printer. ⚠️ **After you deploy it, reload every open FCC tab**: a page
  loaded before Group 39 is told "This FCC page is out of date … reload" when it confirms a mid-print move.
- **Needs you:** the Questions below (15, each with my recommended answer), the manual checks (Group 39's are
  new: 39-a to 39-n), and pushing `dev`.
- **Stopped at 09:40, after Group 39, rather than start Group 45's filler** (45.1(c), the sweep wall-clock
  warning, is the next item, about 30-45 min). It's a weekday morning and this subscription is shared with your
  paid work, so I left the rest of the window to you. The main tree is on `dev` @ the latest handoff commit, clean.

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

### Group 39 — Confirm on Every Door → `DONE`, with 43.4 (merged `c389e26`)

- **Commits:** `8074d0c` (the real-engine move harness), `0a47e42` + `364c035` + `1c92673` + `81ebc7c` (39.1),
  `e92440a` + `ee89219` (39.2), `e7818e0` + `d7164e9` + `cf31aeb` (39.3), `fb7a077` + `715c352` (39.4), `a446bcc`
  (39.5 and the shared confirm), `804ca88` + `9360ff6` (39.6), `8390b39` (39.7), `5810179` + `3ce3c43` (39.8),
  `98748d5` (39.9), `795529c` (43.4), `70d1bd9` (CLAUDE.md), `8833329` + `9cf9f23` (the review's fixes),
  `ab6cbee` + `141678f` (buglist / working-groups / banners / archive).
- **What changed for you:**
  - **One question per move, naming its heads.** A Yes confirms exactly the heads it showed; a stale grid whose
    slot was rebound to another head is asked again (R2-08). Quick-Swap and Return now ask the server too, so a
    slow printer answer can't skip the warning (R2-06).
  - **Moving a spool OFF a printing head asks first (your D6):** "#42 is loaded on XL-3. Moving it to
    CR-CT-2-R1 means FCC stops charging this print to it. Continue?". Head to head on one printer is one
    question. A re-scan onto the head it already sits on asks nothing.
  - **"⏳ Checking XL…"** after 300 ms whenever FCC waits on a printer; past 3 s it says the printer didn't
    answer. A printer with no login says "FCC has no login for XL" instead of "unreachable".
  - **Force Location** mid-print opens a confirm (it was a red "failed" toast). **Eject** of a homeless spool
    mid-print is one prompt, not three. **Smart Load** refuses a load when Spoolman can't list the head (it
    used to stack two spools). **Quick-Swap/Return failures** say why (409, "server answered 502").
    `CMD:TRASH` during a bulk move explains instead of opening an invisible dialog.
  - **43.4:** a cancelled print's review keeps a head that had no spool at the end; pick a spool for it, or its
    grams are reported as the job's shortfall instead of vanishing.
  - From the review: a slot bound to a printing head is now NAMED in the question (the Yes covered it
    silently); the deposit's second question shows the server's words; a completed print's swap review keeps
    an emptied head too; a spool loaded during the printer check is unloaded rather than left under the new
    one; one unreadable spool no longer cancels a whole bulk commit; a slot scan asked twice re-asks instead of
    a green toast; a Location Manager head-to-head move asks once; the dim names the printer on a fresh page;
    a double tap during the Quick-Swap check no longer breaks Tab page-wide; a stale review card can't drop a
    review without its ledger entry.
- **Tests:** every new pin was proven red on the pre-change code. `--offline` 2056 passed, 1 red (TestCart). Targeted E2E (21 files): 190 passed, 3 failed, all three known order-dependent flakes (`test_doassign_does_not_shift_buffer_on_failed_response` and the two `test_deployed_flag_preservation` Quick-Swap button tests), 15/15 in isolation. The frontend review pins are hermetic node tests (`tests/test_confirm_replays_js.py`, run under `--offline`).
- **Full sweep:** 17 failed / 2904 passed / 30 skipped in **39:23** (Group 43's: 36:42). Triage: the 2 TestCart reds; **11 passed 5/5** in isolation; 4 flaky in isolation, each A/B'd against `dev`'s frontend modules with interleaved runs: `test_doassign_swap_pushes_displaced_only_on_success` 8/8 vs 8/8; `test_prefill_falls_back_to_vendor_shows_vendor_badge` 5/8 vs 6/8 (with its sibling at 4/5, the family Group 46 found flakes the same on `dev`); and `test_filament_details_renders_sample_and_label_status_rows`, the one that needed a closer look: 3/8 vs 8/8 in the interleaved A/B, but **24/24** in consecutive branch-only runs, and a timing probe shows its `/api/filament_details` call (a Spoolman read over the NAS) spiking to 4–5 s on both sides against the test's 5 s budget. The branch doesn't touch that modal's code. I couldn't explain why the interleaved arm was worse, so it's noted here rather than called settled.
- **Review:** 5 agents, 2.02M tokens, 22 raw findings → 16 confirmed (3 medium) + 6 refuted duplicates, all fixed.
- **Left:** nothing in Group 39. Groups 40, 41 and 42 build on its contract (their questions are below).

## Parked

- Nothing. (The scratchpad worktree Group 39 started in was clean and is removed.)

## Notes from the run

- **Deploy note for Group 39:** reload every open FCC tab after the update. A page loaded before it sends a
  bare "yes" that no longer covers any head; rather than ask it the same question forever, the server tells
  it to reload (`logic.stale_confirm_refusal`).

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

**Plain-language versions, with examples and what changed after checking the code:** [open-decisions-2026-10-13.md](open-decisions-2026-10-13.md) (morning of 2026-10-13). Five of these turned out to be calls Claude can make alone; that doc says which.

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

**Update (morning, Derek's call):** the ones that need a real print, a powered-off printer, the scanner or your
opinion are now in `Feature-Buglist.md` ⏸️ PENDING DEREK ("one session with a print running" and "the next INDX
cancel review…"): 39-a, b, d, e, f, g, h, i, j, l, m, n and 43-a, d. The rest (46-a…d, 43-b, 43-c, 39-c, 39-k) are
screen-only flows already pinned by browser tests that passed tonight, so they're off your list. 46-e is a
decision, not a check (Questions, item 15).

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
| 39-a | **Quick-Swap mid-print** | XL printing. Open XL-2 → tap the `LR-MDB-1` slot 2 tile | One confirm with the yellow "XL is PRINTING" banner. Yes → the new spool is on XL-2 and XL-2's old spool is back in its box. No second prompt |
| 39-b | **Return mid-print** | XL printing. Open XL-3 → ↩️ Return | The banner names XL (the head being emptied). Yes → the spool is in `LR-MDB-1` slot 3. No second prompt |
| 39-c | **Return while idle** | XL idle. Open XL-3 → ↩️ Return | No banner. One tap parks the spool |
| 39-d | **"Checking…" (offline printer)** | Core One INDX switched off. Location Manager → open `RCOI-1` → assign a buffered spool to it | "⏳ Checking 🦝 Core One INDX…" appears within about half a second, and the assign still goes through. (The task file said CORE1, which no longer exists on dev.) |
| 39-e | **"Checking…" on a scan** | Core One INDX switched off. Reload the page, put a spare spool in the buffer → scan `RCOI-1`'s toolhead label | The dimmed screen names the printer instead of a blank dim. The move then completes |
| 39-f | **Move off a printing head** | XL printing. Open XL-3 → pick its spool into the buffer → scan `CR-CT-2-R1` | One prompt naming the spool, XL-3, `CR-CT-2-R1` and "stops charging". Cancel → nothing moved. Repeat and choose Yes → moved |
| 39-g | **Paused never asks** | Pause the XL print → repeat 39-f | No prompt; the spool moves |
| 39-h | **Head to head asks once** | XL printing. Pick up XL-1's spool → scan XL-3's toolhead QR; then repeat from the Location Manager (open XL-3, assign it) | Exactly one prompt each time, naming both heads |
| 39-i | **Force Location mid-print** | XL printing. Details of XL-3's spool → Force Location → `CR-CT-2-R1` → Force Move. Then repeat with "-- Unassigned --" | Both times a confirm appears (not a red "failed" toast); Yes moves the spool |
| 39-j | **One eject prompt** | XL printing, a spool on XL-2 with no saved home (e.g. one put there with Force Location) → ⏏️ Eject on its card | Only one prompt beyond "Eject spool #N?". Its wording mentions XL-2 and Unassigned, not "already in a room" |
| 39-k | **Eject during a bulk move** | Open `CR-CT-2-R1` → 🔀 Move all → scan the TRASH QR on one of its spool cards | An info toast only. No invisible dialog; later scans still work |
| 39-l | **Deposit mid-print still works** | XL printing. XL-2 grid → Deposit a buffered spool into its slot; confirm once with Enter, once with a click, once with the scan QR | All three load the spool after one confirm |
| 39-m | **A bound slot is named** | XL printing. Pick XL-3's spool into the buffer → scan the label of a box slot bound to XL-2 | One prompt that names XL-3 AND says the slot feeds XL-2 ("…so this also loads #N onto XL-2 and unloads what XL-2 holds") |
| 39-n | **An old tab is told to reload** | Leave an FCC tab open across the deploy. XL printing → in that old tab, assign a spool to an XL head and press Continue | A 7 s message: "This FCC page is out of date … Reload the page". After Ctrl+F5 the same move asks normally |
| 43-d | **A head emptied mid-print keeps its grams** | XL multi-tool print. Mid-print, move one head's spool to a shelf (confirm), then cancel the print | The review lists that head as "no spool loaded" with its grams and a picker; Apply without a pick reports the grams as not charged |

## To push

**Pushed to `origin/dev` on the morning of 2026-10-13** (`d65bfbe..da9cfe5`, Derek's OK). `main` is NOT released: Derek said hold. What went up, oldest first:

- `e818d0c` docs(buglist): file Group 47's two leftovers
- `c895d36` docs(tasks): plan for the unattended 2026-10-13 overnight run
- `6eba7d7` docs(handoff): start the run log
- `36d7318` Merge Group 46 (+ its three branch commits) and the docs commit after it
- `b7ed885` Merge the standalone fixes (+ its three branch commits) and the docs commit after it
- `985aba8` Merge Group 43 (+ its eight branch commits) and the docs commit after it
- `c389e26` Merge Group 39 (+ its 24 branch commits), the archive commit `141678f`, and the handoff commits

## Budget log

| Workflow | Unit | Agents | Tokens | Notes |
|---|---|---|---|---|
| `wf_0e44faf0-934` review-group-46 | Group 46 | 5 (4 lenses + 1 batched skeptic) | 1,311,429 subagent | 41 min, 311 tool calls; 13 findings → 12 confirmed + 1 plausible, 0 refuted, all fixed |
| `wf_4a2dec42-133` review-standalone | Standalone fixes | 4 (3 lenses + 1 batched skeptic) | 828,479 subagent | 35 min, 229 tool calls; 1 finding, confirmed (low), fixed |
| `wf_4573e3ac-aca` review-group-43 | Group 43 | 5 (4 lenses + 1 batched skeptic) | 1,346,059 subagent | 34 min, 236 tool calls; 32 raw findings → 15 confirmed + 1 plausible; the 16 refuted were duplicates (15) or not a defect (1); all 16 fixed |
| `wf_d989c332-cda` review-group-39 | Group 39 | 5 (4 lenses + 1 batched skeptic) | 2,022,606 subagent | 49 min, 431 tool calls; 22 raw findings → 16 confirmed (3 medium), 6 refuted (all duplicates); all 16 fixed |
