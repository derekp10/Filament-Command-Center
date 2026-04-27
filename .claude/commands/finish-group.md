---
description: Finish a working group — commit, archive completed items, update group status.
---

**Role:** You are Zellyn's automated wrap-up assistant for batched working groups.

**Step 1: Identify What Was Done**
* Review the code changes made during this session.
* Cross-reference with the active group's task file in `docs/agent_docs/tasks/`.
* Identify which items from the group were completed vs. still open.

**Step 2: Update the Buglist (The Paperwork)**
* Remove completed items from `Feature-Buglist.md`.
* Insert them at the **top** of `completed-archive.md` (under the header).
* **Strict Constraint:** Do not modify any system code during this step.

**Step 3: Update Group Status**
* In `docs/agent_docs/working-groups.md`, update the completed group's status from `READY` to `DONE` (or `PARTIAL` if not all items were finished).
* If `PARTIAL`, note which sub-items remain in the task file.

**Step 4: Commit & Merge**
* `git add .`
* `git commit -m "feat(<group-scope>): <summary of changes>"`
* `git checkout dev`
* `git merge <current-branch>`
* `git branch -d <current-branch>`

**Step 5: The Handoff**
* Report what was completed, what remains, and suggest the next group to tackle.
