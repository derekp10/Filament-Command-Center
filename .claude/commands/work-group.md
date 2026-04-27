---
description: Start working on a batched task group. Usage: /project:work-group <group-number-or-name>
---

**Role:** You are Zellyn's focused implementation partner. Your job is to execute a batched working group — multiple related items tackled together because they share code surfaces.

**Step 1: Load the Task**
* Read `docs/agent_docs/working-groups.md` to understand all available groups and their recommended order.
* If `$ARGUMENTS` is provided, find the matching group (by number like `1` or by keyword like `weight` or `wizard`).
* If no argument was given, present the available groups with their status and ask Zellyn which one to work on.

**Step 2: Git Prep**
* Execute: `git checkout dev && git pull`
* Create a feature branch: `git checkout -b feature/<group-short-name>` (e.g., `feature/weight-unification`)

**Step 3: Understand Scope**
* Read the specific group's task file from `docs/agent_docs/tasks/` (e.g., `docs/agent_docs/tasks/01-weight-unification.md`).
* Read any files listed in the "Files to Touch" section to understand current state.
* Present a brief implementation plan to Zellyn before writing any code.
* *Pause and wait for approval.*

**Step 4: Execute**
* Work through each item in the group systematically.
* After completing each sub-item, note it in your running summary.
* Run relevant tests after each logical change.
* When all items are done, present a summary of changes.

**Step 5: Wrap Up**
* Suggest running the `/project:finish-group` command to commit, archive, and clean up.
