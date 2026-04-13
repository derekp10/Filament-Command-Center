---
description: Merges, commits, and archives completed tasks in one go.
disable-model-invocation: true
---

**Role:** You are Zellyn's automated Git wrap-up, merge assistant, and token-saving janitor.

**Step 1: The Paperwork (List Cleanup)**
* Cross-reference the completed code changes with the `@feature-buglist.md` file.
* Remove the completed line items entirely from `@feature-buglist.md` to keep it lightweight.
* Open the `@completed-archive.md` file and safely insert the finished items at the **very top** of the list (right underneath the header).
* **Strict Constraint:** Do not modify, refactor, or touch any actual system code during this paperwork step. 

**Step 2: The Automated Commit**
* Review the exact code changes made during the current session.
* Generate a concise, professional commit message based on those changes (e.g., "feat: integrate Spoolman API logic" or "fix: adjust Docker network ports").
* Execute `git add .` followed by `git commit -m "[Your Generated Message]"`.

**Step 3: The Merge & Sweep**
* Execute `git checkout dev` to safely return to the main development branch.
* Execute `git merge <name-of-the-current-feature-branch>` to combine the new code.
* Execute `git branch -d <name-of-the-current-feature-branch>` to delete the temporary branch.

** Step 4: Finishing up
* Sync changes so the user doesn't have to.
* Provide the option to merge dev changes into main for deployment.

**Step 5: The Handoff**
* Gracefully confirm that the code is merged, the branch is clean, and the lists are updated!