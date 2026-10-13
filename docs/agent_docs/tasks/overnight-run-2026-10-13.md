# Overnight run — 2026-10-13 (Derek is asleep)

**Read this whole file before doing anything, and re-read it after any context compaction.** It is the
plan and the rules for an unattended run. Your running log is
`docs/agent_docs/tasks/session-handoff-2026-10-13.md`: create it first, and update it after every milestone.

## Goal

Get as much **decision-free** work done as possible, in the queue order below. Each unit lands cleanly
(merged to `dev` only once verified), so whatever is unfinished when the usage window ends blocks nothing
tomorrow. Derek picks up in the morning from the handoff file.

Starting state: `dev` @ `e818d0c`, one commit ahead of `origin/dev`, unpushed. The dev container
(`inventory_hub`, `inventory-hub/docker-compose.yml`) is up on `http://localhost:8000`. If it isn't:
`docker compose -f inventory-hub/docker-compose.yml up -d`.

## Hard rules (nobody can answer you tonight)

1. **No questions, no waiting.** Don't use AskUserQuestion. When an item needs a decision:
   - if its task file names a default ("build the default until Derek answers"), build the default and record it;
   - otherwise skip the item, add the question to the handoff's **Questions for Derek**, and move on.
   A denied tool call is a signal: don't retry it verbatim. Park that unit and continue.
2. **No push, no pull, no `main`, no release.** Everything stays local on `dev` and feature branches.
   The handoff lists what to push.
3. **Prod is read-only, and only if a task needs it:** GET `http://192.168.1.29:7912/api/v1/...`, and
   PowerShell reads of `\\TRUENAS\App_Data\InventoryHub`. Never write to prod. Never GET the prod
   dashboard (`192.168.1.29:8000`), because it rewrites `.build_info` on the share.
4. **Dev data:** dev Spoolman spools are agent fixtures, so move or clear them freely. Don't hand-edit
   `inventory-hub/data/locations.json`. Leave its blank-LocationID `TestCart` row (Derek's repro) alone.
   No `pytest --reset-dev`, no `--prune`.
5. **Full E2E sweeps: you have Derek's OK tonight.** Several task files ask for it before merging frontend
   work; this is it.
   - Run a sweep only when nothing else is using the container.
   - Edit nothing under `inventory-hub/` while a sweep runs: `FCC_DEV=1` hot-reloads code into the app under test.
   - Expected reds: `test_locations_json_integrity` and `test_location_combobox_highlights_current_selection_on_focus`.
     Both come from the TestCart row. Any other red is signal.
   - Triage reds per CLAUDE.md and memory: capture the traceback, and take ≥ 5 isolated samples before
     calling something a flake, or blaming either load or your change.
6. **Never touch the ⏸️ PENDING DEREK section** of `Feature-Buglist.md`.
7. **Budget.** This subscription is shared with Derek's paid work.
   - Derek opts in to the Workflow tool for grounding and for **one adversarial review per unit's diff**.
   - Keep each workflow ≤ 8 agents, and batch the verify stage: never one agent per finding.
   - Log each workflow's agent count and tokens in the handoff.
   - Never enable or rely on pay-as-you-go or extra usage.
   - If the window looks nearly spent, park the current unit cleanly rather than starting a new one.
8. **Never leave `dev` broken.** Merge a branch only after all of these pass:
   - its `--offline` suite;
   - the targeted E2E files;
   - a full sweep, if anything frontend changed (green apart from the expected reds).

   A unit you can't finish stays on its branch, unmerged, with a precise handoff note.
9. **Gotchas.**
   - Use Python, not `grep -i`, on the docs: Git Bash `grep -i` aborts on them.
   - Write regexes via files, not heredocs.
   - Commit by name, never `git add .`.

## Per-unit workflow

This replaces `/work-group` and `/finish-group`. Derek pre-approves the task files' plans, so skip the
approval pause.

1. `git switch dev` with a clean tree, then `git switch -c feature/<group-or-topic>`.
2. Read the task file and the code it names. Re-grep the code anchors: they were read on `3949aba`, and
   files have moved since. Follow the task file's build order.
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
   - update CLAUDE.md where a convention or a write-surface row changed.
8. Commit, then `git switch dev && git merge --no-ff <branch> -m "Merge <unit>"`, then delete the branch.
9. Update the handoff file, and commit it on `dev`.

## The queue

Work in this order. Skip whatever is blocked. Stop when the window ends.

### 1. Group 46: Quick-Fix Sweep (`46-quick-fix-sweep-2026-10.md`)

- **46.1: the buffer carousel deposits the previous spool.** Highest value: it's a wrong-spool write on
  Derek's daily path.
  - **Reproduce first** with Group 38's in-page fetch-delay lever: delay `/api/get_contents`, press next,
    click DEPOSIT. Route-stub the backend so nothing is written to dev.
  - Then fix per the task file:
    - resolve the spool at click time;
    - re-render the DEPOSIT card synchronously on `inventory:buffer-updated`;
    - check `renderGrid` and Quick-Swap's `quickSwapDeposit` for the same capture-at-render bug.
- **46.2: Type + "t" + Enter.** Add a `#locModal` keydown handler. Do NOT make the scanner skip all `SELECT`s.
  Apply the L298 lesson: `stopImmediatePropagation()`, plus a *deferred* `scanBuffer` clear.
- **46.4:** retire the `feeder_map` boot import, and update CLAUDE.md's "Legacy" bullet.
- **46.5: blank LocationID.**
  - Build: a 400 guard on save, `required` on `#edit-id` plus a client check, and an explicit blank-id DELETE path.
  - **Not** a startup migration: it would touch prod's row.
  - Don't delete dev's TestCart row.
- **Skip 46.3.** It needs Derek's call: "Tool 1" or "T0". Put it in the Questions, and the group ends `PARTIAL`.

### 2. Standalone fixes (one branch, `fix/standalone-2026-10-13`)

- **🟡 The Bulk Moves flag doesn't gate three backend doors** (see the buglist entry).
  - Check `_bulk_moves_enabled()` at `POST /api/bulk_move`, at the `CMD:BULKMOVE` interceptor, and at the
    armed-session gate in `api_identify_scan`.
  - Keep `cancel` / `CMD:CANCEL` allowed.
  - Pin all three doors in `tests/test_bulk_move_feature_gate.py`.
- **Finish the `slot_targets` reader migration** (buglist entry; 10 sites in 9 functions).
  - Route the pure reads through `locations_db.bindings_from_row`.
  - Give each writer an `isinstance(extra, dict)` guard.
  - Add a poisoned-row test per site, in the style of `tests/test_bindings_from_row_malformed.py`.

### 3. Group 43: Deduct Recovery (`43-deduct-recovery.md`), in its build order

- Build **43.1 → 43.5 → 43.3 → 43.6**.
- Skip **43.2**: it has an open question for Derek, which goes in the Questions.
- Skip **43.4**: it lands with or after Group 39.4. The group ends `PARTIAL`.
- 43.1's "exposure count" may read prod (GET `:7912`), read-only.
- Update CLAUDE.md's `_apply_usage_to_printer` / `api_cancel_deduct_confirm` rows if their contracts change.

### 4. Group 39: Confirm on Every Door (`39-confirm-on-every-door.md`), only if time remains

- **It is unblocked.** The task file's "before any build, ask Derek three questions" step is already done:
  its Q1, Group 41's Q1 and Group 42's Q-B were all answered 2026-09-18 (`working-groups.md`, 2026-10-12 refresh).
- It's ~2 sessions of work. Work it in its own order on `feature/group-39-confirm-on-every-door`.
- Build 43.4 alongside 39.4 if you get there.
- Merge only if the whole group is done and swept. Otherwise leave the branch with an exact handoff:
  what's done, what's next, and the test state.

### 5. Filler: Group 45's decision-free items

Do these only if everything above is done or blocked: 45.1(c) (the sweep wall-clock warning), then
45.1(b)/(a), then 45.2 (traceback first). 45.3–45.6 need Derek.

## Not tonight (blocked on Derek): list each under Questions with your recommended default

- **Group 41:** Q3 and Q4.
- **Group 42:** waits for 41; 42.6 also needs the Q-A caveat settled.
- **Group 40:** Q1 and Q2.
- **Group 44:** its design pass.
- **Group 37:** fork 1.
- **46.3** and **43.2**.
- The weight-undo decision.
- **45.3–45.6.**
- Removing dev's TestCart row: it would clear the two standing sweep reds.

## The handoff file (`docs/agent_docs/tasks/session-handoff-2026-10-13.md`)

Create it first. Update it after every milestone, and commit it on `dev` at every merge and at the end.
Sections:

- **Morning summary** at the top, in 5–10 lines: what landed, what's parked, what needs Derek.
- **Landed:** per unit, the commits and merge sha; the tests run, with pass/fail counts and wall-clock;
  the review findings fixed.
- **Parked:** the branch, its exact state, and the next step.
- **Questions for Derek:** batched, each with your recommended default.
- **Manual checks for Derek:** pull these from the task files (e.g. Group 43's), plus anything new.
- **To push:** the commits waiting on `dev`, starting with `e818d0c`.
- **Budget log:** the workflows run, with agent counts and tokens.
