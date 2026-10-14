# Overnight run — night of 2026-10-13 → 14 (Derek is on vacation, asleep from ~00:30–01:00)

**Read this whole file before doing anything, and re-read it after any context compaction.** It is the
plan and the rules for the run. Your running log is
`docs/agent_docs/tasks/session-handoff-2026-10-14.md`: update it after every milestone.

## Goal

Work Derek's chosen order as far as the night goes. Each unit lands cleanly: it merges to `dev` only once
verified, and is pushed. Whatever is unfinished blocks nothing tomorrow. Derek picks up from the handoff file.

Starting state: `dev` @ `4203ffe` (= `origin/dev`) plus this plan commit. The dev container
(`inventory_hub`, `inventory-hub/docker-compose.yml`) is up on `http://localhost:8000`. If it isn't:
`docker compose -f inventory-hub/docker-compose.yml up -d`.

## Derek's answers this evening (2026-10-13, ~18:15)

- **Order:** the recommended one (the proposal earlier in this session): 43.2 → 46.3 → Group 45 → 41 → 42 → 40.
- **Budget:** 55% of the usage window used at ~18:10, reset ~19:00. He is on vacation, so no headroom is
  needed for work.
- **Full test runs against dev:** yes, all night.
- **Push:** push `dev` to `origin` after each merge. Never `main`: it stays held, and nothing is released
  without asking him.
- **Prod reads:** approved; done at ~18:25 (the counts are below).
- **Questions:** get every one to him before he goes to bed (~00:30–01:00).

## Hard rules

1. **Questions.**
   - **Until Derek goes to bed** (~00:30–01:00), ask with AskUserQuestion, explained cold (memory
     *explain decisions cold*: what it is, where he'd meet it, a real example from his setup, options with
     what each changes, your recommendation, what is built if he never answers; group numbers only as a
     trailing ref). One to three per call, recommended option first.
   - **After that, no questions.** If the task file names a default, build the default and record it.
     Otherwise skip the item, add the question to the handoff's **Questions for Derek**, and move on.
   - A denied tool call is a signal: don't retry it verbatim. Park that unit and continue.
2. **Push `dev` after each merge** (`git push origin dev`). No pull, no force push, no `main`, no release.
3. **Prod is read-only, and only if a task needs it:** GET `http://192.168.1.29:7912/api/v1/...`, and
   PowerShell reads of `\\TRUENAS\App_Data\InventoryHub`. Never write to prod. Never GET the prod dashboard
   (`192.168.1.29:8000`), because it rewrites `.build_info` on the share. Tonight's counts are already taken.
4. **Dev data:** dev Spoolman spools are agent fixtures, so move or clear them freely. Don't hand-edit
   `inventory-hub/data/locations.json` (45.4 and 45.5 change the committed reset seed and the tests, not dev
   data). No `pytest --reset-dev`, no `--prune`.
5. **Full E2E sweeps: you have Derek's OK all night.**
   - Run a sweep only when nothing else is using the container.
   - Edit nothing under `inventory-hub/` while a sweep runs: `FCC_DEV=1` hot-reloads code into the app under test.
   - The TestCart pair of standing reds is gone (the row was deleted on 2026-10-13).
   - **Known recurring reds until Group 45's new 45.8 fixes them:**
     - `test_prusament_new_scan_opens_prefilled_add_wizard`;
     - the three `test_wizard_auto_prefill_empty_weight` tests, and `test_prefill_falls_back_to_vendor_shows_vendor_badge`;
     - `test_doassign_does_not_shift_buffer_on_failed_response` and `test_doassign_swap_pushes_displaced_only_on_success`;
     - the two `test_deployed_flag_preservation` Quick-Swap button tests;
     - `test_feeds_section_hidden_for_non_dryer_box`;
     - `test_filament_details_renders_sample_and_label_status_rows`.
     These still need ≥ 5 isolated samples before you call them flakes. Any other red is signal.
   - Triage per CLAUDE.md and memory: capture the traceback; ≥ 5 isolated samples before blaming load or your change.
6. **Never touch the ⏸️ PENDING DEREK section** of `Feature-Buglist.md`.
7. **Budget.**
   - Derek is on vacation, but CLAUDE.md's workflow rules stand: ≤ 8 agents per workflow, the verify stage
     batched (never one agent per finding), and each workflow's agent count and tokens logged in the handoff.
   - One adversarial review per unit's diff (last night's shape: 4 lenses + 1 batched skeptic).
   - Never enable or rely on pay-as-you-go or extra usage.
   - If a window looks nearly spent, park the current unit cleanly rather than starting a new one.
   - A session-only hourly check-in (CronCreate, at :43) re-wakes the session if a usage limit stalls it.
     Delete it (CronDelete) when the run ends.
8. **Never leave `dev` broken.** Merge a branch only after all of these pass:
   - its `--offline` suite;
   - the targeted E2E files;
   - a full sweep, if anything frontend changed.

   A unit you can't finish stays on its branch, unmerged, with a precise handoff note.
9. **Gotchas.**
   - Use Python, not `grep -i`, on the docs: Git Bash `grep -i` aborts on them.
   - Write regexes via files, not heredocs.
   - Commit by name, never `git add .`.
   - The container runs Python 3.9: no 3.10+ syntax in backend modules.

## Per-unit workflow

Pre-approved by Derek; skip `/work-group`'s approval pause.

1. `git switch dev` with a clean tree, then `git switch -c feature/<group-or-topic>`.
2. **Reconcile first.** Start from the pre-flight results (workflow `wf_1a1ff135-1c6`, summarised in the
   handoff), then re-read the task file and re-grep every code anchor on the branch. Fold the stale-claim
   corrections into the task file in the unit's housekeeping commit.
3. **Pin first.** Write the test, then prove it fails on the old code (`git archive HEAD` into a scratch
   dir, or a stash A/B). Then fix. Drive the real engine, with fakes that mirror the real Spoolman merge;
   don't mock the engine away (memory: *mocked engine hides chain bugs*).
4. Iterate from `inventory-hub/` with `"C:/Python314/python.exe" -m pytest tests/ -p no:cacheprovider -q --offline`.
   Run the targeted E2E files for anything frontend.
5. **Adversarial review** of the branch diff (≤ 8 agents, batched verify). Fix the confirmed findings, then re-test.
6. Full sweep, if frontend changed (`RUN_INTEGRATION=1` when the unit touches Spoolman paths).
7. **Housekeeping is yours** (memory: *agent owns housekeeping*):
   - archive the done items from `Feature-Buglist.md` to the top of `completed-archive.md`, in the per-group block style;
   - narrow any partial items in place;
   - update the group's `working-groups.md` row and its task-file banner (`DONE`, or `PARTIAL` naming what's left);
   - update CLAUDE.md where a convention, a user-preference key or a write-surface row changed.
8. Commit, then `git switch dev && git merge --no-ff <branch> -m "Merge <unit>"`, delete the branch, and
   `git push origin dev`.
9. Update the handoff file, commit it on `dev`, and push.

## The queue

Work in this order. Skip whatever is blocked. Stop when the night ends.

### 1. Finish Groups 43 and 46: 43.2 + 46.3 (one branch, `feature/finish-groups-43-46`)

- **43.2, the shortfall review card** (`43-deduct-recovery.md`, "43.2", answered 2026-10-13: charge a picked
  archived spool and leave it archived). Build the filed design:
  - stash the shortfall review **before** `record_deduct`, under the derived key `"<job_id>#shortfall"`;
  - add a `shortfall_review_min_g` config value (~1.0 g);
  - record the shortfall on the ledger entry;
  - `_rows_from_charges` stops refusing archived picks, and so does the card's typed-#id lookup (`cancel_review.js`);
  - the card's default spool comes from the deduct's own details, not a heads snapshot taken afterwards;
  - pin that `api_cancel_deduct_confirm` can't lose the grams a second time.
- **46.3, the toolhead label setting** (`46-quick-fix-sweep-2026-10.md`, "46.3", answered: "Tool 1"):
  - choices: the full id (today's look, the default), a bare number, or "Tool N" (position + 1);
  - visible text only (`data-toolhead` and titles keep the full id), with the mode in `_fingerprint`;
  - the collapsed strip keeps the full id; the 🛑 review card keeps its "T0 · RCOI-1" lines;
  - add `fcc.printerStatus.toolheadLabel` to CLAUDE.md's user-preferences table.
- Housekeeping closes **both groups** (`DONE`).

### 2. Group 45: Sweep Load-Tolerance & Test Hygiene (`feature/group-45-sweep-hygiene`)

- First file **45.8**, the recurring reds above (buglist entry + task-file row), from the pre-flight notes.
- Build order: 45.1(c) (wall-clock warning) → 45.1(b)/(a) (a conftest default, then triage each `timeout=3000`
  site; Group 38's lesson: fix races, raise only pure waits) → 45.2 (traceback first) → 45.3 (guard fix +
  OFFLINE alpha 0.45 → 0.50, recapture only the baselines that change) → 45.5 → 45.4 → 45.8.
- **Skip 45.6** (the dev-from-prod refresh: an evening with Derek) and **45.1(d)** (auto-retry, only if still
  needed). The group ends `PARTIAL`, naming 45.6.

### 3. Group 41: Honest Bulk Results (`feature/group-41-honest-bulk-results`)

- Reconcile its ⚠️ note first. Then its build order: 41.1 → 41.2 → 41.6 → 41.5 → 41.4 → 41.3 → 41.7 / 41.8 → 41.9.
- 41.4 carries Derek's "Undo Last Move" answer; 41.3 carries the Room-delete refusal.

### 4. Group 42: Single-Slot Box Lifecycle (`feature/group-42-single-slot-box-lifecycle`)

- Reconcile its ⚠️ note first (Q-B and Group 41's Q1 are answered; line refs drifted). Then its build order.

### 5. Group 40: Slot Picker (`feature/group-40-slot-picker`)

- Engine prerequisites first, then **40.3** (the "already fed from elsewhere" confirm on Derek's daily path)
  before the other doors. It spans 2–3 sessions: leave an exact handoff if unfinished.

## Not tonight

- **45.6** (needs Derek awake for the prod reads, and maybe TrueNAS).
- **Groups 44 and 37 fork 1** (one design sit-down); **35** (waits on 44); **34**'s leftovers (wait on 37);
  **22**'s M600 split (waits on data).
- **44.2**'s early rename refusal: only if Derek asks.

## Read-only counts taken 2026-10-13 ~18:25 (dev and prod, GET only)

| Count | Dev | Prod | Used by |
|---|---|---|---|
| Active spools | 237 | 267 | — |
| On a toolhead | 3 | 10: #242 XL-4 and #230 XL-5 (from `LR-MDB-2`), #243 RCOI-8 (trail `CR`), #295–#301 RCOI-1…7 | 42.1 |
| On a toolhead with no "came from" trail | 0 | 7 (#295–#301, the ColorMix set on RCOI-1…7) | 42.1 |
| Off a toolhead but still carrying a trail | 0 | 0 | 41.3, 42.1, 45.7 |
| Toolheads holding 2+ spools | 0 | 0 | 42.4 |
| Filed on a Printer row itself (`XL`, `RCOI`) | 0 | 0 | 40.0a |
| Printer rows that are their own head | none | none | 41.1, 40.0a |
| Active spools with no `initial_weight` | 0 | 0 | 43.1 (last night's unrun prod count) |
| In a single-slot box with a blank `container_slot` | 7 (#1, 18, 137, 139, 140, 141, 150) | 10 (#18, 29, 66, 137, 141, 147, 150, 254, 262, 268) | 42.2 (confirms its premise) |
| Trail names a single-slot box with a blank slot | 0 | 0 | 42.2 |
| Archived with a toolhead as pre-archive location | 2 | 4, all 0 g: #95 RCOI-5, #99 RCOI-1, #226 XL-3, #241 XL-2 | 42.3c |
| … whose head is now occupied | 1 (#240 → XL-3) | 2: #99 → RCOI-1 (holds #299), #95 → RCOI-5 (holds #301) | 42.3c |
| Spools filed on a Room itself | 21 | 57 | 41.8 |
| Single-slot boxes bound to a head | 0 | 0 | 42.5c |

## The handoff file (`docs/agent_docs/tasks/session-handoff-2026-10-14.md`)

Update it after every milestone, and commit + push it on `dev` at every merge and at the end. Sections:

- **Morning summary** at the top, in 5–10 lines: what landed, what's parked, what needs Derek.
- **Landed:** per unit, the commits and merge sha; the tests run, with pass/fail counts and wall-clock;
  the review findings fixed.
- **Parked:** the branch, its exact state, and the next step.
- **Questions for Derek:** the ones asked before bed with his answers, then any left for the morning, each with
  your recommended default.
- **Manual checks for Derek:** pull these from the task files, plus anything new. Screen-only flows already
  pinned by browser tests stay off his list (2026-10-13 rule). The rest stay in the handoff; they move into
  `Feature-Buglist.md`'s ⏸️ PENDING DEREK section only with Derek's OK in the morning (rule 6), as last night.
- **Budget log:** the workflows run, with agent counts and tokens.
