# 🔁 Session Handoff — 2026-09-12, evening (active-print fix built → commit, sweep, release)

> For a fresh context window. Supersedes this file's morning version (the Bulk Move manual-check table
> is carried forward below, updated). That version superseded
> [session-handoff-2026-08-06.md](session-handoff-2026-08-06.md).

## ▶️ START HERE (next chat, 2026-09-13) — Derek's answers from the end of the last chat

The previous chat ran out of context. Derek answered its four asks:

1. **Commit: approved.** Done on `fix/active-print-chain-confirm`. It is NOT pushed and NOT merged; the sweep and merge steps below are still open.
2. **Dev spool #99's stale trail: approved to clear** (it isn't needed for any test), but the auto-mode classifier blocked the write as a shared-resource change. Ask Derek to approve it, then run:
   `docker exec -w /app inventory_hub python -c "import spoolman_api as s; print(s.update_spool(99, {'extra': {'physical_source': '', 'physical_source_slot': ''}}))"`
   Read `get_spool(99)` first and confirm it is still in `LR-MDB-1` with `physical_source CR-MDB-1`. Afterwards `CR-MDB-1` shows no ghost, so check 3 needs a spool really deployed from `CR-MDB-1`.
3. **Check 4 = "bulk move during an active print": yes, still to do** (the table below). It is now meaningful because the auto-deploy and Smart Load bugs it would have hit are fixed.
4. **The 5 open decisions** (section below): Derek needs background on each first — where it lives, what it's for, and what each option changes for him. Explain them plainly, one at a time, before asking.

**Standing goal (Derek):** keep growing his manual checklist, so hands-on testing weeds out issues like the ones today's active-print bulk-move test found. Add a check whenever a fix changes behaviour he can see.

## ⚠️ Next: `fix/active-print-chain-confirm` is built, reviewed, green and COMMITTED (not merged)

Branch off `dev` at `cff5707`. Next steps, in order:

1. ~~Derek's OK to commit~~ — done 2026-09-13.
2. **Full `RUN_INTEGRATION=1` sweep before merging:** frontend changed. ⚠️ It writes dev data and takes about
   27 min; never run it next to another E2E run. Expected reds: the blank-LocationID `TestCart` row
   (Group 37.1).
3. Merge to `dev` (`--no-ff`), run the manual checks below, then release `dev` → `main`, then Derek's
   TrueNAS pull.

**Derek's report, as proven.** The raw report is at the top of `Feature-Buglist.md`, and both triage entries under
it now carry the resolution.

| Symptom | Proven cause |
|---|---|
| Box assign mid-print didn't reach the toolhead | The auto-deploy chain dropped `confirm_active_print`, then logged "⚡ Auto-deployed" for any non-None result |
| Two spools on one toolhead | Smart Load's `if perform_smart_eject(rid):` read truthy refusals (the active-print dict, `"REQUIRE_CONFIRM"`) as success. Reachable from his exact flow |
| Eject "did nothing until I came back" / "bulk-move timeout breaks slot-card eject" | **One cause, not bulk move.** FCC re-showed `#confirmModal` from inside its own close callback; Bootstrap 5.3 ignores `show()` mid-fade (~150 ms), and real backend latency lands inside it. Not a Bootstrap bug — FCC's call order |

**Evidence (committed with the branch):**
- `docs/agent_docs/tasks/active-print-chain-investigation-2026-09-12.md`: 7-agent verified investigation, 58 findings.
- `docs/agent_docs/tasks/active-print-chain-diff-reviews-2026-09-12.md`: 4-agent backend and 2-agent frontend adversarial reviews.

Every confirmed finding in those two reviews was applied on the branch or filed in the buglist.

## What's on the branch

| Area | Fix |
|---|---|
| Auto-deploy chain (`logic.py`) | Forwards the confirm only for a caller-named slot; deploys only spools whose box write landed, one per slot; per-spool success; skips → WARNING + `auto_deploy_skipped` / `auto_deploy_target`; its undo record folds into the parent **by identity** |
| Smart Load | Only residents whose own record is on the head (ghosts and Printer-row prefix hits skipped); forwards the confirm + `homeless_destination`; only `is True` counts; an unmovable or unreadable resident refuses the load (`status: error` + `failures`) |
| Ghost trails | A toolhead is never written as `physical_source` (`_ghost_trail_from`); eject treats a toolhead source as stale; the 13.6 reverse-binding never claims an occupied slot; dryer/generic branches write `""` (a `pop()` was KEPT by the extras merge) |
| Eject | The Group 20.2 PolyDryer detach runs only after the write lands |
| Undo | Restores an ejected resident with its extras, but only onto a head the strict read shows empty; otherwise ERROR + `success: False` |
| Quick-Swap Return (`routes_bindings.py`) | `auto_deploy=False` (it was a silent round trip on dev — every XL head); direct residents only; 409 on a doubled head; 502 `return_failed` for a rejected write or an unreadable resident; never unseats a staged spool; 29.B3 fields |
| Quick-Swap / slot-QR assign | `quickswap_failed` / `assignment_failed` instead of success for rejected writes; `not_deployed` reason in the slot-QR response |
| Confirm dialogs (`inv_core.js`, `inv_cmd.js`, `global.css`) | Phase tracker queues the one `show`/`hide` Bootstrap drops; CONFIRM scans fire only a visible (hit-tested) dialog; a fading dialog is click-inert; stale `CMD:CONFIRM:<sid>` ignored; cause-aware, quiet-when-harmless ignore toast; `CMD:CLEAR` blocked mid-bulk-move |
| Frontend consumers | Deposit sends its confirm (click, Enter and QR) and re-confirms with the backend's banner; every assign UI honours `failures` / `auto_deploy_skipped` with ≥ 7 s toasts; Return preview reads the spool's real `physical_source` and refuses 0 or 2+ direct residents; Force Location honours failures; confirm wording matches the Room/Unassigned decision |
| `CLAUDE.md` | Write-surfaces table updated (function names, Smart Load, undo); new gating-dialog convention |

**Tests:**
- `tests/test_active_print_chain_confirm.py`: 44 hermetic tests. The real extras merge, prefix matcher and probe memo are in the loop.
- `tests/test_confirm_chain_reshow_e2e.py`: 29 E2E tests, all non-GET requests route-stubbed.
- `tests/test_move_result_consumers_e2e.py`: 19 E2E tests, route-stubbed.
- **Proof against HEAD's JavaScript:** 24 of 29 and 16 of 19 fail there, each at its intended assertion. The FE-1 double-click test was also shown to fail with the CSS rule overridden.
- **Runs:** each E2E file passed 3× in serial runs; the browser regression set passed 54/54; `--offline` gave 1713 passed and 1 failed (the known TestCart red).
- **Existing tests changed deliberately:**
  - The head→head test no longer pins the old-toolhead trail.
  - Two resident mocks are now realistic.
  - Return kwargs gained `auto_deploy=False`.
  - Two L130 pins now require the key to be present and empty.

**Derek's decisions this session:**
- A homeless Smart Load resident goes to its printer's Room when the location tree knows it, otherwise Unassigned.
- A resident that can't be moved refuses the load.
- Budget: "Burst — run it all".

## Open decisions for Derek (all filed in `Feature-Buglist.md`)
- **R2-06:** should Quick-Swap and Return stop trusting their overlay? They still hard-code `confirm_active_print=True`, and the overlay probe fails open.
- **Slotless moves into a bound multi-slot box** (Force Location, buffer location-scan): should they auto-deploy at all?
- **Placement on Printer rows** (dev `XL`, Max 0): refuse it?
- **Room-level "Eject all":** one batch unassign confirm, or skip with a count?
- **Return with no recorded slot:** land unslotted, or prefer a same-head / unbound free slot?

## Git state (2026-09-12 evening)

| Ref | State |
|---|---|
| `fix/active-print-chain-confirm` | **Uncommitted** working tree on top of `cff5707`; 16 tracked files changed, plus 3 new test files and 2 evidence docs |
| `dev` | `cff5707`; pushed. 78+ commits ahead of `main` |
| `main` | `b49158b` (2026-07-07). **Release HELD** on the Bulk Move sign-off |
| Merged, not deleted | `feature/group-36-attribute-force-reset-data-loss`, `feature/group-38-hermeticity-residuals`, `fix/locations-json-write-lock` — local AND origin. Safe to delete on Derek's OK |

## 🧪 Remaining Bulk Move (L298) manual checks — Derek, on dev, AFTER the branch is merged

**Already passed:** a row→row move and back, `CR-CT-2-R3` ⇄ `CR-TC-2-R1`.

**Starting state, as of the 2026-09-12 morning read of Spoolman (re-check first):**
- `CR-TC-2` and its three rows: 0 spools.
- `CR-CT-2-R1` / `R2` / `R3`: 3 / 3 / 2.
- `LR-MDB-2`: 2 slots, 0 used.
- `CR-MDB-1`: 4 slots, 1 "ghost".
- `LR-MDB-1`: 1 direct spool.

**Empty the scan buffer first** — bulk move skips any spool sitting in it. Dev's dryer boxes also drifted from
live; refresh dev data before the pass.

| # | Check | Steps | Pass if |
|---|---|---|---|
| 1 | **Undo** | `CR-CT-2-R3` → `CR-TC-2-R1`, commit, then `CMD:UNDO` | Both spools back in `CR-CT-2-R3`. Stronger: move `LR-MDB-1`'s spool out and undo — same box AND same slot |
| 2 | **Capacity block (D3)** | `CR-CT-2-R1` (3 spools) → `LR-MDB-2` (2 free) | The whole batch is refused with a capacity message and nothing moves |
| 3 | **Deployed-spool skip** | `CR-MDB-1` → `CR-TC-2-R2` | The deployed spool is listed as skipped, with a reason. ⚠️ **The `CR-MDB-1` "ghost" is dev spool #99, a STALE trail** (it sits in `LR-MDB-1` slot 4 with `physical_source CR-MDB-1:1`), so this would pass for the wrong reason. Clear its trail first (dev write — Derek's OK), or deploy a real spool from `CR-MDB-1` |
| 4 | **Active print** | Only while printing: a move that touches its loaded spool | An explicit in-panel confirm before anything moves. Now meaningful — the auto-deploy and Smart Load bugs are fixed on the branch |

**Also worth re-running mid-print, since these are Derek's original flows:**
- Assign into a bound dryer-box slot: the spool reaches the toolhead.
- Replace a loaded spool from the print-status toolhead view: the old spool goes home, and only one stays on the head.
- Eject from a printing head: the second prompt appears.
- Quick-Swap Return: the spool stays in the box.

Optional sanity checks:
- Source == destination is blocked.
- A destination inside the source is blocked.
- A toolhead destination is blocked.
- Reloading the page while armed brings the pill back.

**Known, NOT a failure:** scanning a cart *parent* such as `CR-CT-2` as the source finds only its direct spools
(Group 37.4). Test at row level.

## Open threads
- **Group 37 — location redesign** gets its own chat. It carries 37.4 (cart-subtree bug) and 37.1 (blank LocationID →
  the known sweep red).
- **New standalone buglist items from this session** (top of `Feature-Buglist.md`):
  - Eject-all / location delete / undo success claims.
  - Other single-occupancy doors: auto-unarchive, undo, multi-spool `/api/smart_move`, Printer rows.
  - Active-print guard gaps.
  - Bulk-move tally / failed slot unseat.
  - Dev spool #99 stale ghost trail.
  - Eject / Return UX leftovers.
  - Diff-review follow-ups: R1-03 fail-open resident list, R2-06, R2-08, 502 codes, `CMD:TRASH` behind the bulk panel, remaining E2E test debt.
- Carried: PolyDryer unattach feedback (item 3 is now fixed on the branch), bulk-move empty-source dead end, Group 34
  `PARTIAL`, Group 35 `TODO`, Group 22 `PARTIAL`, README item, `CR-TC-2` test cart cleanup.

## Conventions worth carrying forward
- **Truthy refusals:** `perform_smart_eject` returns truthy values for refusals, so test `is True`, never truthiness. A move's `status: success` can still carry per-spool `failures`; read them with `logic.smart_move_failure`.
- **A toolhead is never a spool's home** (`physical_source`). **`pop()` on an extras key does not clear it** — the merge keeps omitted keys, so write `""`.
- **Never `.show()` / `.hide()` the three Bootstrap gating dialogs directly** — use the `inv_core.js` helpers (CLAUDE.md).
- **Route tests for chaining flows must run the REAL engine.** Every Return test mocked `perform_smart_move`, which hid a
  months-old no-op. Make fakes mirror the real merge, matcher and probe memo, and prove a new test fails on
  `git archive HEAD` in a scratch dir.
- **pytest here is SERIAL and deterministic**, and run position ≠ alphabetical file order.
- **Derek's buglist edits are often unsaved or uncommitted when he mentions them** — check `git diff` first.
- **Docker Desktop may not be running after a reboot:** `docker compose -f inventory-hub/docker-compose.yml up -d`.
