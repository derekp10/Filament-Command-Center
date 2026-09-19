# 🔁 Session Handoff — 2026-09-18 (follow-up branches tested; ready to merge)

> Continues [session-handoff-2026-09-13.md](session-handoff-2026-09-13.md), whose **manual-check tables for Derek still stand** — he has not run them yet. Decisions record: [open-decisions-2026-09-13.md](open-decisions-2026-09-13.md).

## ▶️ START HERE — what's left, in order

1. **Test `test/sweep-reds-hermetic`** (commands below). It is the only untested branch.
2. **Integration sweep:** merge both branches into a scratch branch and run the full `RUN_INTEGRATION=1` sweep.
3. **Merge both to `dev`** (`--no-ff`) and push.
4. **Build Group 39**, then 41 → 42 → 40, with an unblocked Group 22.5 alongside 39.4.
5. Derek's manual checks on dev are still open (2026-09-13 handoff).

⚠️ **Never run E2E while Derek is testing on dev**, and never two runs at once. Ask before driving the dev container: the auto-mode classifier treats it as a shared-resource change, so say what will run and get an explicit go-ahead.

## State (2026-09-18)

| Ref | State |
|---|---|
| `dev` | `8ec143f`, pushed. Clean tree except this handoff and the doc edits it describes |
| `fix/core1-return-ejectall-guard` | `cfb997d`, local only, **tested green**, unmerged |
| `test/sweep-reds-hermetic` | `657ed95`, local only, **E2E not yet run**, unmerged |
| `main` | `b49158b`. Release still held on Derek's manual checks |
| Dev data | PM-DB-1/2/4/5 all at `slot_targets {}` (what the new fixtures require); spool #99 has no trail |

## What was verified on `fix/core1-return-ejectall-guard`

- **Offline suite (main checkout):** 1 failed, 1744 passed. The one failure is the known Group 37.1 blank-`LocationID` row.
- **Browser tests:** its own 7 Core One / Eject-All cases pass, plus 172 passed across the Quick-Swap, Return, eject, shortcuts, bind-picker, lockout, move-result and confirm-chain files.
- **Two test-only fixes** were needed and are committed as `cfb997d`:
  - **Wake Lock noise:** the new E2E asserts on uncaught page errors, and headless chromium's Wake Lock denial surfaces as an unhandled rejection (FCC has a documented fallback). `_IGNORED_PAGE_ERRORS` now filters it.
  - **Shortcuts baseline:** the overlay grew 21 px because this branch reworded the `CMD:EJECTALL` entry to two lines ("ignored when none is open"). Recaptured and eyeballed; the rest of the overlay is unchanged.
- **Still red on this branch, as expected:** `test_visual_quickswap_grid` / `_kb_active` (the dev-data drift that `test/sweep-reds-hermetic` fixes by stubbing).

## Next: test `test/sweep-reds-hermetic`

With the container up and Derek not using dev, from the repo root:

```
git checkout test/sweep-reds-hermetic          # wait for the container to reload, then:
cd inventory-hub
# 1. recapture the two now-hermetic grid baselines, inspect the PNGs, then re-run without the variable
UPDATE_VISUAL_BASELINES=1 "C:/Python314/python.exe" -m pytest tests/test_quickswap_visual.py::test_visual_quickswap_grid tests/test_quickswap_visual.py::test_visual_quickswap_kb_active -p no:cacheprovider -q
"C:/Python314/python.exe" -m pytest tests/test_quickswap_visual.py tests/test_contrast_guard.py tests/test_feeds_section_visual.py -p no:cacheprovider -q
# 2. the converted binding borrowers (they fail loudly unless PM-DB-1/2/4/5 are at slot_targets {})
"C:/Python314/python.exe" -m pytest tests/test_bind_slot_picker.py tests/test_deployed_flag_preservation.py tests/test_loc_mgr_bindings_ui_e2e.py tests/test_loc_mgr_bindings_api_e2e.py tests/test_printer_status_widget.py tests/test_quickswap_ui_e2e.py tests/test_return_and_breadcrumb.py -p no:cacheprovider -q
```

Then the integration sweep (~27 min, writes dev data):

```
git checkout -b integration/followups-2026-09-18 dev
git merge --no-ff fix/core1-return-ejectall-guard
git merge --no-ff test/sweep-reds-hermetic
cd inventory-hub && RUN_INTEGRATION=1 "C:/Python314/python.exe" -m pytest tests/ -p no:cacheprovider -q -rfE
```

**Expected reds:** the Group 37.1 pair (`test_locations_json_integrity`, `test_location_combobox_highlights_current_selection_on_focus`) and nothing else. The contrast pair should now pass even while a printer prints, since the compositing fix is the point of that branch.

## Derek's answers to the four group questions (2026-09-18)

| Q | Answer |
|---|---|
| **41 Q1** — an ejected spool with no saved home | **Unassigned, after one prompt**; Eject All asks once for the batch. Smart Load's homeless resident keeps the printer's-Room rule |
| **39 Q1** — a mid-print Quick-Swap confirm | **Keep today's overlay** (Yes focused; Enter, click or CONFIRM QR), with only the new wording |
| **42 Q-B** — a LOCATION scan in eject mode | **Eject that head's one loaded spool**, with the eject button's confirms; warn and do nothing on a box, shelf, room, or a head holding 0 or 2 spools |
| **42 Q-A** — does a single-slot box follow its spool head→head | **Yes, it follows** — with the caveat below |

**⚠️ Open design question from Q-A, needed before 42.6.** Derek: "we shouldn't overwrite the spool location before the box load. (Say it was on a cart or something, so that if we unload it from the box, we know where it was before and move it back to that location.)" `physical_source` is one level deep today, so a spool that went cart → PolyDryer → head has lost the cart. Options to put to him: a home chain (box plus a separate "before the box" field), or a general "last non-container location". It touches Group 42 and Group 40's "record it as coming from" prompt.

Groups 39/41/42's question sections are annotated with these answers; the remaining open ones are 40 Q1/Q2, 41 Q3/Q4 and 42's design question above.

## Worth carrying forward

- **Node.js is now a test prerequisite** (on the bugs branch): `test_core1_return_ejectall_js.py` runs the real JS modules under node's `vm`, which is how the frontend fixes are proven to fail on pre-fix code without a browser. It skips with a warning when node is missing, and `FCC_REQUIRE_NODE=1` makes that a hard failure. The branch adds a CLAUDE.md bullet.
- **Workflow worktrees start at `main`**, not the current branch, and have no git-ignored runtime data, so a fresh worktree's `--offline` run shows 2 extra Amazon-parser reds. Name the base branch explicitly in agent prompts.
- **Derek wants background before any choice:** where he meets it, what it's for, and a worked example with his real boxes and heads.
- **Dev spools are virtual test fixtures** (move or clear freely when no test or open issue needs them); `locations.json` bindings still need his OK.
