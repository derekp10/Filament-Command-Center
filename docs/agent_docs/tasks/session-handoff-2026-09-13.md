# 🔁 Session Handoff — 2026-09-13 (active-print fix merged; six decisions answered)

> Supersedes [session-handoff-2026-09-12.md](session-handoff-2026-09-12.md). Its "What's on the branch" table and conventions still apply.

## ▶️ START HERE

1. **`fix/active-print-chain-confirm` is MERGED** into `dev` as `f35d5e3` (`--no-ff`) and pushed, along with the branch. `main` is still `b49158b`, and the **release is HELD** on Derek's manual checks (below).
2. **All six filed decisions are answered.** Full record: [open-decisions-2026-09-13.md](open-decisions-2026-09-13.md). Each is also written onto its buglist item.
3. **Decision docs committed and pushed** (`be9f045`). Later the same day, a follow-ups workflow built two LOCAL branches and plan docs 39–42 (see "Follow-ups built the same afternoon" below). Their browser tests are **not run yet**: the auto-mode safety check blocked driving the dev container without Derek's go-ahead.

## Pre-merge sweep (2026-09-13, `RUN_INTEGRATION=1`, `51d9a49`)

**2517 passed / 6 failed / 23 skipped in 27 min.** All six failures are explained, and none comes from the branch.

| Red | Cause | Filed as |
|---|---|---|
| `test_locations_json_integrity` + `test_location_combobox_highlights_current_selection_on_focus` | The known Group 37.1 blank-LocationID `TestCart` row | Group 37.1 |
| `test_contrast_guard` printer-status ×2 | The harness uses a translucent background's RGB as if opaque. It only fires while a printer is PRINTING, so its result flips with live printer state | Sweep-triage follow-ups, item 1 |
| `test_quickswap_visual` grid ×2 | The snapshot tracks dev Printer Pool contents (680 → 762 px) | Sweep-triage follow-ups, item 2 |

**Expect the contrast pair to go red again whenever a sweep overlaps a real print**, until item 1 is fixed.

## Decisions (short form — details in the decisions doc)

| # | Question | Derek's answer |
|---|---|---|
| D1 | Quick-Swap/Return trust their overlay (R2-06, R2-08) | **Server re-checks** when no banner was shown; Return probes the head it empties; every confirm names its toolhead. Quick-Swap is meant for non-active states; mid-print use is a deliberate sync correction |
| D2 | Slotless move into a bound box | **Slot picker** for box-label scans (loadout + feeds + recommendation, touch or QR). Before a load, confirm when the printer is printing OR the head is already fed from elsewhere. The same confirm applies to slot-label scans. Force Location behaves like a box-label scan |
| D3 | Spool on a Printer row | **Picker** of the printer's heads and its pool slots, then the D2 confirms, then "record it as coming from" a feeding slot or none. The server refuses the row itself. Low priority for Derek (he never scans `LOC:XL`) |
| — | Single-slot (PolyDryer-style) box | Stays bound until **its own spool** leaves the head, by any path. A head only ever shows ONE loaded spool |
| D4 | Room-level Eject All | **Block it on Room and Printer views.** Room-only spool locations are hard to find. Removing Eject All entirely came up but is NOT decided |
| D5 | Return with no usable slot | **Slot picker**, only in that case (a legacy-data case) |
| D6 | Moving a spool OFF a printing head | **Ask first, like Eject**, and build it with Force Location's yes-path |

**New UX ask:** show that FCC is waiting on a printer ("Checking XL…"), so a slow or offline printer never looks like a lock-up.

## Suggested build grouping (not started — confirm with Derek, or run `/project:refresh-groups`)

- **Confirm on every door:** D1 + R2-08 + the waiting indicator + D6 + Force Location's yes-path (guard gaps item 2).
- **Slot picker:** D2 + D5 + D3 share one picker component; also fix the Return preview and the `SLOT:null` toast.
- **Honest bulk results:**
  - D4 block;
  - Eject All, location delete and Undo report what really happened;
  - refuse a blank location;
  - never sweep a printer's heads.
- **Single-slot box lifecycle:** the release rule (decision-briefing findings items 5 and 9, plus the toolhead-keyed detach).
- **Small standalone bugs:**
  - 🟠 Quick-Swap Return can never run on the Core One.
  - 🟡 The DEPLOYED slot-card ↩️ Return button redeploys to the same head.
- **Test infra:**
  - the contrast guard's alpha handling;
  - a hermetic Quick-Swap grid snapshot;
  - the PM-DB-1 fixtures that "restore" whatever they observed.

## 🧪 Manual checks — Derek, on dev (it now runs the merged code)

**Already passed:** a row→row move and back (`CR-CT-2-R3` ⇄ `CR-TC-2-R1`).

**Before starting:**
- **Re-read the starting state.** The 2026-09-13 sweep rewrote dev data. In particular:
  - dev spool #99 no longer carries a trail;
  - `PM-DB-1` is no longer bound to `XL-1`;
  - `CR-MDB-1` shows no ghost.
- **Empty the scan buffer**, because bulk move skips spools that are in it.

| # | Check | Steps | Pass if |
|---|---|---|---|
| 1 | **Undo** | `CR-CT-2-R3` → `CR-TC-2-R1`, commit, then `CMD:UNDO` | Both spools are back in `CR-CT-2-R3`. For a stronger check, move `LR-MDB-1`'s spool out and undo: it returns to the same box AND the same slot |
| 2 | **Capacity block** | `CR-CT-2-R1` (3 spools) → `LR-MDB-2` (2 free) | The whole batch is refused with a capacity message, and nothing moves |
| 3 | **Deployed-spool skip** | First deploy a real spool from `CR-MDB-1` (scan its slot-1 label → loads CORE1). Then bulk move `CR-MDB-1` → `CR-TC-2-R2` | The deployed spool is listed as skipped, with a reason |
| 4 | **Active print** | While printing, a bulk move that touches the loaded spool | Bulk move refuses spools on a toolhead, so expect a skip, not a prompt |

**Mid-print re-runs of Derek's original flows:**

| Flow | Pass if |
|---|---|
| Assign into a bound dryer-box slot by **slot label** | The spool reaches the toolhead, after the print confirm |
| Replace a loaded spool from the print-status toolhead view | The old spool goes home, and only one spool stays on the head |
| Eject from a printing head | The second prompt appears |
| Quick-Swap Return, **on the XL only** | The spool stays in the box |

**Bug confirmations (code-traced, not yet seen in the UI):**

| Check | Steps | Expected today (= bug) |
|---|---|---|
| **Core One Return** | Open `CORE1` with a spool loaded → "↩️ Return to Slot" | "Nothing to return on CORE1" |
| ⚠️ **Do NOT try** `CMD:EJECTALL` with no location open | — | It targets the Unassigned pile |

**Optional sanity checks** (bulk move):
- Source == destination is blocked.
- A destination inside the source is blocked.
- A toolhead destination is blocked.
- Reloading the page while armed brings the pill back.

**Known, NOT a failure:** scanning a cart *parent* (e.g. `CR-CT-2`) as a bulk-move source finds only its direct spools (Group 37.4).

## Follow-ups built the same afternoon (workflow, 10 agents, ~3.1M tokens)

Derek chose "all of the above": fix the two small bugs, fix the test-infra reds, and plan the build groups. **Nothing is merged or pushed.**

### `fix/core1-return-ejectall-guard` — local, `1fb5678` + `76398cb`
- **Quick-Swap Return and the bind picker** now resolve a Printer row's `toolheads[]`. CORE1 works, and XL is unchanged.
- **Eject All refuses a blank location** in all three places: the scan, `triggerEjectAll`, and `clear_location`.
- **Review:** ship. 3 low findings, all applied. `--offline` is green in its worktree.
- **New test pattern:** node-vm JS tests.
  - **node is now a test prerequisite:** it must be on PATH.
  - **Missing node:** `FCC_REQUIRE_NODE=1` makes it fail loudly.
  - **CLAUDE.md:** the branch adds a Testing bullet for this.

### `test/sweep-reds-hermetic` — local, `d785444` + `657ed95`
- **Contrast guard:** now composites translucent backgrounds.
- **New `isolated_page` browser fixture:** a dead proxy plus a resolver rule, so it runs under `--offline`.
- **Quick-Swap grid snapshots:** route-stubbed.
- **`borrow_box_bindings`:** fixed baselines for PM-DB-1/2/4/5 across 10 files, plus a canary.
- **Review:** ship. 2 low findings; one applied a different way, one partly.
- **`--offline`:** green.

### ⚠️ Deferred — NOT run yet (needs the dev container serving the branch)
**Bugs branch:**
- `pytest tests/test_core1_return_ejectall_e2e.py`
- The existing Quick-Swap / Return / eject / shortcuts / confirm-dialog E2E. The CMD:EJECTALL shortcut text changed, so look at `test_visual_shortcuts_overlay`.

**Test-infra branch:**
1. **Recapture the grid baselines:** `UPDATE_VISUAL_BASELINES=1 pytest tests/test_quickswap_visual.py::test_visual_quickswap_grid tests/test_quickswap_visual.py::test_visual_quickswap_kb_active`, inspect both PNGs, then re-run without the variable.
2. **Run the visual and contrast files:** `tests/test_quickswap_visual.py`, `tests/test_contrast_guard.py`, `tests/test_feeds_section_visual.py`.
3. **Run the borrowers:** `test_bind_slot_picker`, `test_deployed_flag_preservation`, `test_loc_mgr_bindings_ui_e2e`, `test_loc_mgr_bindings_api_e2e`, `test_printer_status_widget`, `test_quickswap_ui_e2e`, `test_return_and_breadcrumb`. PM-DB-1/2/4/5 must be at `slot_targets {}`.

**Then:** a full `RUN_INTEGRATION=1` sweep on a local integration of both branches, before merging to dev.

**Why not run:** the auto-mode safety check blocked switching the main checkout (which the dev container serves) to the branch and running these tests, as a shared-resource change. It needs Derek's explicit go-ahead.

### Plan docs
[39-confirm-on-every-door.md](39-confirm-on-every-door.md), [40-slot-picker.md](40-slot-picker.md), [41-honest-bulk-results.md](41-honest-bulk-results.md), [42-single-slot-box-lifecycle.md](42-single-slot-box-lifecycle.md). Each has a "Cross-plan notes" section, and the reviewer's corrections are applied.

**Recommended order:**
1. Merge the two branches above.
2. Ask Derek the three contract-shaping questions below.
3. Build 39 → 41 → 42 → 40, starting an unblocked Group 22.5 alongside 39.4.

**The three questions to ask first** (each doc has the background and a worked example):
1. **Group 41 Q1:** where a spool with no saved home goes when it's ejected from a box, cart or shelf. Options: the Room (today), Unassigned after one prompt, or refuse.
2. **Group 39 Q1:** how deliberate a mid-print Quick-Swap confirm must be. Options: keep Yes focused, focus No, or QR/click only while printing.
3. **Group 42 Q-B:** what a location scan means in eject mode. Options: eject that head's loaded spool, or warn and do nothing.

## Git state (2026-09-13, evening)

| Ref | State |
|---|---|
| `dev` | `be9f045`, pushed (decision docs). Uncommitted: plan docs 39–42, plus the buglist, handoff and working-groups updates from the follow-ups |
| `fix/core1-return-ejectall-guard` | `76398cb`, local only, unmerged |
| `test/sweep-reds-hermetic` | `657ed95`, local only, unmerged |
| `fix/active-print-chain-confirm` | `51d9a49`, pushed, merged. Safe to delete on Derek's OK |
| `main` | `b49158b`. Release held on the manual checks |
| Merged, not deleted | `feature/group-36-attribute-force-reset-data-loss`, `feature/group-38-hermeticity-residuals`, `fix/locations-json-write-lock` (local and origin) |

## Conventions learned this session

- **Derek wants background before a choice.** Give where he meets it, what it's for, and a worked example with his real boxes and heads, then ask. Two questions this session went out without that and needed a second round.
- **Derek prefers a picker with a recommendation over FCC guessing a slot, head or box.**
- **Dev spools are virtual test fixtures** (memory `feedback_dev_spools_are_agent_fixtures`). `locations.json` bindings still need his OK.
- **The contrast guard and Quick-Swap grid snapshots depend on live state.** Read the failure before recapturing any baseline.
