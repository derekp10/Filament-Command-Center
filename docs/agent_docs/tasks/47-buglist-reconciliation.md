# Group 47: 🧹 Buglist Reconciliation — verify & archive shipped items

**Branch name (when started):** `chore/group-47-buglist-reconciliation`
**Estimated effort:** SMALL (~2–3 h, 1 session). Docs only.
**Risk:** **LOW for code, but it deletes text from Derek's source of truth.** Never archive an item just because a commit exists. Spot-check that the code does what the item asked.

> **Status: `TODO` — filed 2026-10-12 (`/refresh-groups`), not started.**
> Derek, 2026-10-12: *"If they truly are done, we should group them in a cleanup and get those worked through and cleaned up… You do the coding, I just pick the targets, so this just got missed somehow either because I failed to wrap up, or didn't realize it was part of a group or something."*
> **Why it's needed.** Groups 36 and 38 were merged on 2026-08-13 but `/finish-group` never ran for them. Several standalone fixes shipped without their buglist entries being archived. Two months of shipped work still reads as open in `Feature-Buglist.md`, which makes every "what's pending?" answer wrong.
> **Recommended next target**: it's cheap, and it makes the buglist trustworthy for every later group.

---

## ⚠️ Read this first

- **"Truly done" means two checks.**
  1. The fix commit is an ancestor of `main`. All of the commits below were checked on **2026-10-12**; re-run the check if `main` has moved.
  2. A behavior spot-check: grep the function or guard the item names and confirm it does what the item asked.
- **The ⏸️ PENDING DEREK section is live. Don't touch it.**
- **Release reference.** Unless noted, everything below shipped to `main` in **`e5b3a82` (2026-10-08)**. Prod gets it when Derek presses the TrueNAS update button.
- **Prod reads are read-only.** Prod files are at `\\TRUENAS\App_Data\InventoryHub` (use PowerShell for UNC paths). Prod Spoolman is `:7912`; never write to it.
- **Archive format.**
  - One dated block at the top of `completed-archive.md` for this group: `[2026-10-xx — 🧹 Buglist Reconciliation (Group 47)]`, with one bullet per item giving the title, shipping commits and release.
  - Groups **36** and **38** each get their own block in the established per-group format, since they're the missing `/finish-group` runs.
- **Remove** each archived item from `Feature-Buglist.md`. Where other text references it, leave a one-line breadcrumb instead.

---

## A. Archive: shipped and in `main` (spot-check, then archive)

| # | Buglist item (title as filed) | Shipped by | Notes |
|---|---|---|---|
| **47.1** | **Group 36 wrap-up:** 🔴 *"DATA LOSS: removing a filament-attribute choice can permanently wipe OTHER filaments' attributes, and never says which."* | `43389c6` + `a9a582d`, merged `415822b` (2026-08-13) | Do the `/finish-group` bookkeeping that never ran: archive block, task-file banner. The filed "suspected escalation" was **refuted** (36.1), so say so in the archive. ⚠️ Its follow-up, a read-only **prod→dev sibling-extras restore** for ~4 drained records (#4, #121, #175, #157), was never filed in the buglist. Route it to [Group 45](45-sweep-load-tolerance-test-hygiene.md) 45.6 (the dev-data refresh from prod covers it). |
| **47.2** | **Group 38 wrap-up:** 🧪 *"Flaky E2E: `test_weigh_out_preserve_text_e2e.py`…"*, 🧪 *"Flaky E2E: `test_return_and_breadcrumb.py::test_escape_key_walks_out_of_three_level_stack`…"* (the six-member family), and the four ✅ DONE rows in the `## 🧪 Testing` section | `2d36a62`, `1756259`, `ac93cb5`, `fe2fb61`, `8de0823`; merged `367e9c9` (2026-08-13) | Same bookkeeping. Group 38's lesson ("not one of the eight wanted a bigger timeout") belongs in the archive block. |
| **47.3** | 🔴 *"`locations.json` writes have NO concurrency control — a save can be silently reverted."* + 🟠 *"Two bindings writers discard `save_locations_list`'s failure boolean and report success anyway."* | `aa05526`, merged `ddbcdd9` (2026-08-13) | Spot-check: `locations_write_lock()` exists, and `set_dryer_box_slot_order` / `set_dryer_box_bindings` act on `if not save_locations_list(...)` (`locations_db.py`). The commit message says it "Closes the two Feature-Buglist items". |
| **47.4** | 🧪 *"The 'offline' sweep is NOT offline — 55 E2E test files hit the live dev container…"* | `4f10e35`; residuals closed by Group 38.7 / 38.8 | |
| **47.5** | 🔍 *"Scan-path integrity audit (axis (a) of the codebase-wide review) — DONE 2026-08-03…"* | `ef1e422`, `34d0fe3` | **Don't** archive the 🔎 codebase-wide review item: axes (b)–(e) are still open. |
| **47.6** | *"`registerShortcut` silently no-ops for any module loaded before `shortcuts_registry.js`."* + 📋 *"Activity-Log PAUSE is a fetch-freeze, not a render-freeze…"* | `e4031c0` | The PAUSE item left one engineering question: revert the L298 `bulk_move_active` / `bulk_move_stage` pulse keys now that pause keeps fetching? They're still at `routes_state_pulse.py:240`/`:455`. Decide in-session (default: keep, since they're harmless and pinned) and note the decision in the archive. |
| **47.7** | 🧪 *"`test_filament_attributes_bulk_api` mutates REAL dev inventory and wedges itself — plus: a filament carrying EVERY attribute should be SUPPORTED…"* | `6834b7f`, `34d0fe3` | The `sweep_unused` force_reset note inside it was addressed by Group 36. |
| **47.8** | *"`requests.patch` in `spoolman_api.update_spool` has NO timeout"* (⚙️ App Flow section) | `e20d264`, `cac02f4` | Its double-deduct follow-up now lives in [Group 43](43-deduct-recovery.md) 43.6. |
| **47.9** | 🔎 *"Deferred findings from the session-diff adversarial review (2026-08-05)."* | Groups 36 + 38 | Verified on 2026-10-12: the recovery payload now logs the **post**-filter payload, with a `...TRUNCATED` marker (`attr_migration.py:117`, `:305-326`); the aliased-timeout canary (38.9), `--offline` leaks (38.7), `scratch_filament` (38.10), the drain test (38.11) and the hook test (38.8) are all closed. **The two remaining sub-bullets live elsewhere:** the `_bindings_from_row` residual (its own item, 47.26) and the cancel-retry idempotency (Group 43.6). Archive. |
| **47.10** | 🔴 *"Dryer-box → toolhead auto-deploy silently SKIPS the toolhead during an active print — but logs '⚡ Auto-deployed' anyway."* + Derek's raw report (*"Bulk move testing, testing during an active print…"*) | `51d9a49`, merged `f35d5e3` (2026-09-13) | The item still says "✅ BUILT … (unmerged…)". Keep the raw report's surviving pieces: bulk-move discoverability (47.11) and dev/prod parity (Group 45.6). |
| **47.11** | 🔀 *"Bulk Move active-print testing report — remaining findings, triaged."* Items 1 and 2 | same | Narrow it to item 3, the discoverability polish. It's best merged into a single "Bulk Move polish (while the feature flag is off)" line beside the empty-source item. Item 4 goes to Group 45.6. |
| **47.12** | 🟠 *"Found while briefing the six open decisions"* items 1 (Core One Return) and 2 (`CMD:EJECTALL` with no location) | `1fb5678`, `76398cb`, merged `25168a8` (2026-10-08) | Mark both ✅ and keep the item. Its other sub-items are owned by Groups 40, 41, 42 and 43; annotate each with its owner. |
| **47.13** | 🧪 *"Sweep-triage follow-ups from the 2026-09-13 pre-merge sweep"* items 1–3 | `d785444`, `657ed95`, `0872b45`, merged `75e8279` (2026-10-08) | Item 3 still says "unmerged; E2E not yet run". Item 4 goes to Group 45.5. |
| **47.14** | ✅ *"HOTFIXED 2026-09-29 — INDX printer setup…"* + 🧪 *"`test_each_row_has_minimum_schema_for_its_type` relaxed 2026-10-08…"* | `fbdd5f7`, `aced051` (released `main ab48e45`); `6f32371` | Archive the hotfix only after 47.29 confirms every ask in Derek's raw INDX report is tracked. The schema record points at Group 44. |
| **47.15** | *"Assigning a filament to a slot takes incredibly long…"* (L3) | `e3b9481` (2026-06-10); the ~4 s tail went with FilaBridge (2026-06-13) | Its index row has said DONE since June. |
| **47.16** | *"Check to see if prusa slicer 2.9.6 or the latest firmware…"* | `6842424` (verdict: no impact) | Keep the forward-watch notes in the archive. The INDX one is now live, and its L316 finding 42 (natural sort) shipped in Group 29 (`_natural_key`, `routes_bindings.py:349`). |
| **47.17** | *"L316 characterization findings — 50 pinned behaviors / suspected bugs"* (the breadcrumb block) | Groups 27–29 (2026-07-05) | It was kept as a breadcrumb on purpose. All three groups are long released. |
| **47.18** | *"Deduct-path code-review follow-ups (recoverable-unresolved-deduct, 2026-06-13)"* (Group 22.4) | `e522d99`, merged `8592964` | It was kept only because it "shares the `feature/group-22-deduct-followups` branch" with 22.3(b). That branch was merged and deleted in June, so the reason no longer holds. |
| **47.19** | 🔄 *"**Bulk Moves** (L298)"* in the 📍 Active Backlog, which still says "Ready to build" | All 5 phases merged 2026-08-03; shipped behind a default-off flag (`71a1be9`) | The ⏸️ PENDING DEREK item tracks the hands-on pass. |
| **47.20** | *"Config button, for configuring certain things…"*, which still says "NEEDS DESIGN SESSION", + *"Make as much of Command Center user configurable as possible…"* | L18 Phases 1–4 shipped 2026-06-01 | Phase 5 and per-printer settings live in Group 35. Collapse both lines into one pointer, or archive them. |
| **47.21** | L271 *"Make the Location Manager less brittle and more concrete"* (the phase tracker in 📍) | Phases 1A–5 shipped; prefix retirement `2b16869` (Group 34); Phase 4 completed per the index row | The unchecked `[ ]` boxes for Phases 3.5, 4 and 5 are stale. The one unaddressed recommendation, #3 (decouple printed barcodes from hierarchy strings), is Group 37's fork 1. Leave a pointer there and archive the rest. |
| **47.22** | *"(Core One MMU rows cleanup … ⚠️ Prod replication still needed …)"* | Done on dev 2026-06-01 | Moot on prod since the INDX replaced the Core One. Verify read-only that prod's `locations.json` has no `CORE1-M1`…`M5` rows, then archive. |
| **47.23** | 🟡 *"Dev data: spool #99 carries a stale ghost trail…"* | Trail cleared before 2026-09-18 (per that day's handoff) | Verify with a read-only GET of dev spool #99's extras. The drift-count suggestion goes to Group 45.7. |

## B. Verify on prod (read-only), then archive

| # | Item | How to verify |
|---|---|---|
| **47.24** | *"I keep seeing this line in the activity log on prod … removed ['Wood'] …"*: fixed by `d1072d8` and *"kept open pending one prod-deploy confirmation."* | Read prod `hub.log` for `removed ['Wood']` lines after the fix deployed. If the line is absent across at least one later deploy, archive. |
| **47.25** | *"Add support to overwrite hex on edit filament advanced tab … parser field isn't resetting between different filament loads."* This was a prod-deploy gap: Group 23 wasn't in prod build `93d6d5be`. | Group 23's merge (`66d0e1e`) is in `main` (checked 2026-10-12). Confirm prod's deployed build is past it (the build string the prod dashboard shows, or prod's git HEAD), then archive. If Derek meant a separate manual hex-overwrite on the advanced tab, file that as a small residual instead. |

## C. Narrow: partly done, rewrite in place

| # | Item | Rewrite to |
|---|---|---|
| **47.26** | *"`locations_db._bindings_from_row` is duplicated in `logic.py` and crashes on a non-dict `extra`."* The canonical reader shipped (`e45496a`). | Only the residual: ~9 direct `extra.slot_targets` readers left to migrate, plus a malformed-row test at each. |
| **47.27** | *"Unattaching a single-spool box (PolyDryer) from a toolhead is unclear…"* Direction 3 shipped on the active-print branch. | A pointer to [Group 42](42-single-slot-box-lifecycle.md) item G (42.5a/b/c). Q-B was answered 2026-09-18. |
| **47.28** | *"Clean up filament attributes"* (L319): `For Infill` and `Matte Pro` are "pending Derek's prod check". | Derek's new search request (*"I was trying to find the 'For Infill' filaments"*) answers For Infill: he uses it, so keep it. Count both on prod (read-only). If Matte Pro is unused there, the existing boot auto-cleanup already promotes it (FLAG_CHOICES zero-usage rule). Narrow the item to whatever is left. |
| **47.29** | Derek's raw INDX report (*"Adding/Updating a printer … is an incredibly cumbersome process…"*) | Map every ask to where it's tracked, then archive the raw text together with the hotfix (47.14): delete-then-re-add flow and "auto-derive from id isn't apparent" → Group 44.0; IP resets after save → hotfix ✅; renaming and adding toolheads after setup → Groups 44.1/44.3; toolhead-number display → Group 46.3; a removed Spoolman-native location lingering → hotfix ✅ (hidden when only archived spools reference it); Settings toolheads not reaching the Location list → hotfix ✅; Type + "t" + Enter → Group 46.2. |

## D. Ask Derek once, batched: likely-obsolete items to close

Put these in ONE question. Give each its background, where he meets it, and the evidence. Only close the ones he agrees to.

| # | Item | Why it's probably obsolete |
|---|---|---|
| **47.30** | *"Unknown crash on Filament command center after auto deduct fired…"* (2026-04-27, ON HOLD, with FilaBridge-era logs) | FilaBridge's RAM-Fetch deduct is gone, and the L28 polling fix (2026-05-19) landed afterwards. There's been no recurrence report since. |
| **47.31** | *"There continues to be inconsistency with switching out spools when a box slot is attached to a head…"* (WATCH since 2026-06-05) | Already marked "likely RESOLVED by Group 20.1"; the active-print chain fix (2026-09-13) has rebuilt that path since. |
| **47.32** | *"Refactor dashboard to be more modular…"* | The backend half is done (L316). The item itself says "close it, or keep open only if you want a further frontend pass." |
| **47.33** | *"An unknown issue caused the frontend to lock up…"* (L28) + *"Sub-bug: 'Display modal on Display modal'"* | Fixed 2026-05-19, plus the 7th poll guard on 2026-07-06. Archive both, keeping a one-line "if it recurs, capture DevTools before refreshing" pointer. |

## Close-out

- Update `docs/agent_docs/working-groups.md`. Prune or mark ✅ ARCHIVED the NOT-Grouped rows whose items were archived (the 2026-06-05 cleanup pruned them).
- Flip this group's row and banner to `DONE`.
- Commit as one docs commit.
