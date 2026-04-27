---
description: Re-analyze Feature-Buglist.md and refresh the working groups. Run after adding new bugs/features.
---

**Role:** You are Zellyn's backlog organizer. Your job is to re-analyze `Feature-Buglist.md` and update the working group system.

**Step 1: Read Current State**
* Read `Feature-Buglist.md` to see all current items (including any newly added ones).
* Read `docs/agent_docs/working-groups.md` to see existing groups and their statuses.
* Read `completed-archive.md` header area to know what's already been done.

**Step 2: Identify Changes**
* Find any NEW items in `Feature-Buglist.md` that aren't covered by an existing group.
* Find any items in existing groups that have been completed/removed from the buglist.
* Check if any group's status should change (e.g., all items done → `DONE`).

**Step 3: Propose Updates**
Present a summary to Zellyn:
1. **New items found** — list them with a suggested group assignment (existing group or new group).
2. **Completed items** — items that are in a group but no longer in the buglist.
3. **Groups to update** — any status changes.
4. **Ungrouped items** — anything that doesn't fit an existing group (suggest creating a new group or leaving standalone).
* *Pause and wait for Zellyn's approval before making changes.*

**Step 4: Apply Updates (after approval)**
* Update `docs/agent_docs/working-groups.md` with:
  - New items added to appropriate groups
  - Status updates for completed groups
  - New groups if needed (create corresponding task file in `docs/agent_docs/tasks/`)
* Update individual task files in `docs/agent_docs/tasks/` as needed.
* Do NOT modify `Feature-Buglist.md` itself — that's the source of truth.

**Step 5: Report**
* Confirm what was updated.
* Show the current group status overview table.
