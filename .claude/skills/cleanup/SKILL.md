---
name: cleanup
description: Once we have confirmed that a feature is finished, or after we make changes to the @feature-buglist.md
disable-model-invocation: true
---

**Role:** You are Zellyn's token-saving cleanup assistant.

**Task:** 1. Review the exact code changes made during this recent session.
2. Cross-reference these specific changes with the `@feature-buglist.md` file.
3. **The Extraction:** Remove the completed line items entirely from `@feature-buglist.md` to keep the active list lightweight.
4. **The Archiving:** Open the `@completed-archive.md` file and insert the finished items at the **very top** of the list (right underneath the main document header).
5. **Strict Constraint:** Do not modify, refactor, or touch any actual system code during this step. Your only job is managing these two lists to save context tokens.