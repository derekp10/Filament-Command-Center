# Group 53: 🧹 Code-Health Canaries

**Branch name (when started):** `feature/group-53-code-health-canaries`
**Estimated effort:** SMALL–MEDIUM (~5–9 h, 1 session). 53.1 ~1.5–3 h · 53.2 ~1–2 h · 53.3 ~2–4 h.
**Risk:** **LOW–MEDIUM.** 53.1 touches daily paths (the Quick-Swap grid, eject mode, the Printer picker, "Move all →"); 53.2 and 53.3 are tests only.

> **2026-11-10: DONE, merged to `dev` `f4bea52` (Derek: "Yes merge and file the followups"; `main` held). Nothing is left in the group; its follow-ups are standalone buglist items, the 🟠 error-body reads first. Build notes below.**
> **Status: `TODO` — filed 2026-10-19 (`/refresh-groups`). No Derek decision needed.** Not in the 48 + 49 + 51 + 52 bundle.
> One frontend toolhead-Type list, and two classes of bug turned into cheap automatic source checks instead of agent reviews. Every decision: [refresh-2026-10-19.md](refresh-2026-10-19.md).
> Code anchors were read on `dev` @ `c5c5aa6` (the refresh's grounding) and spot-checked at `08c4b10`. Line numbers drift, so re-grep before editing.

## Build notes, 2026-11-09 to 11-10

Built on `feature/group-53-code-health-canaries`, cut from `dev` `df271a5`, after Derek's "go" on the plan (ultracode on). Three builders worked in hand-made worktrees (the harness's `isolation: 'worktree'` refused them: the session's `d:\` against git's `D:/`), integrated as cherry-picks. Then two reviews (7 agents, then 4; no red), a fix round after each (4 fixers, then 3), and a final two-agent check; every confirmed finding was fixed, test-first wherever behaviour changed. Subagent tokens before the final check: about 9.6M (build 1.48M, review 2.83M, fixes 2.1M, review 1.72M, fixes 1.48M). The full offline run on `b29f151`: 7254 passed, 0 failed. The full sweep on `580701c`: 9030 passed, 0 failed, 46 skipped (38 integration-gated; 4 picture tools and 1 real move that run only on request; 3 that need something dev didn't have: a live print, an empty head on the virtual printer, a card in the scan buffer), 67:42 at load 1.06×.

**53.1, one toolhead-Type list.** `window.TOOLHEAD_TYPES`, `window.isToolheadType(type)` and `window.isHeadOrPrinterType(type)` sit in `inv_core.js` between `// @fcc-toolhead-types:begin` and `:end`. Every head-Type test on the page goes through them (16 sites: the 8 copies filed, 6 more listed in the build's brief (a list in `inv_audit_find.js`, four substring filters and `doAssign`'s check), and two lower-cased copies the builder found: `NO_ADD_CHILD_TYPES` in `inv_core.js` and `wizardIsHeadOrPrinterRow` in `inv_wizard.js`), except the 11 lines marked `// toolhead-type-ok: <why>` (badge colours, the MMU grid, the Type dropdown's entries). They read a Type as most backend reads do: trimmed, then exactly one of the list. **Behaviour change (Claude's call, not vetoed):** a custom Type that only contains a head Type's words ("Toolbox", "MMU Buffer") is no longer a head. Two smaller ones came with the switch (the builder's calls): the two lower-cased copies (the Locations table's Add child, the wizard's clone check) now read head Types case-sensitively, as the backend does ('printer' stays case-insensitive there), and every switched site trims the Type. `tests/test_toolhead_types_one_list.py` pins the block against `locations_db.TOOLHEAD_TYPES` and is red on another copy in `static/js` or an inline script, outside a line marked `// toolhead-type-ok: <why>`: a string that is a head Type, a regex, a words list, a string split where it is written, or the argument of a substring test (its docstring lists what it can't see, such as a Type built from pieces or inside a longer string). The shared node driver runs the block before any module, so a harness that loads a module without `inv_core.js` still has the helpers. The second review's rb-6 moved the slot-label scan's target check (`routes_scan.py`) onto `locations_db`'s constants, so the backend has one list too.

**53.2, every Spoolman write registered.** `tests/test_spoolman_write_sites.py`'s `WRITE_SITES` lists every call in `inventory-hub/*.py` that writes to Spoolman (the `spoolman_api` write helpers, direct HTTP writes, and calls of FCC's own wrappers in `WRAPPER_WRITERS`, `logic._move_write` among them), each with a count; every `update_spool` / `update_filament` / `update_vendor` (or `_or_raise`) site also carries a doc anchor that must appear in CLAUDE.md's write-surface section (a create, delete, field-schema, HTTP or wrapper site carries one only where the section already names its function). A result thrown away is red unless `ALLOWED_DISCARDS` says why (only the boot's three `ensure_extra_field` calls today). Building and reviewing it found real bugs, fixed here:
- Merge Filament read a spool list it couldn't read as "no spools" and went straight on to delete the source filament (only Spoolman's own refusal to delete a filament that still has spools kept them, and the answer blamed the delete); a 200 that wasn't a list iterated a dict's keys, or crashed part-way after re-parenting a spool. It now lists `?filament.id=<src>&allow_archived=true`, checks that every entry is a spool record of the source, and otherwise refuses with nothing written, in words.
- Four surfaces read Spoolman's 404 or 500 body as the record (`get_filament` / `get_spool` hand back the body whatever the status): Merge Filament's two filament reads; the attributes bulk add / remove (a 500 on its read made an add write the added tag alone over the filament's own, answered as success); the Prusament link scan (a 500's body read as blank temps, and all four set temps were overwritten); and Edit Spool's pre-edit read (every field written, and a Location in the form wrote the spool Unassigned before its move). The filament reads go through the new `spoolman_api.get_filament_answer` (`get_spool_answer`'s contract, plus one hub.log WARNING saying what came back); Edit Spool counts only a record whose `id` is the spool's. The rest of the class (about ten callers) is a standalone 🟠 follow-up.
- `create_spool` / `create_filament` set and clear `LAST_SPOOLMAN_ERROR` (a refused create left an earlier write's refusal there, which `/api/create_filament` answered as its own), and `update_extra_field_choices` answers a refused field-list read instead of None.

**53.3, the load-order canary.** `tests/test_load_order_canary_js.py` loads every script the dashboard loads, in the page's order, under node, each CDN bundle stood in for by the globals it sets (read from the real bundles), over a stub DOM that holds the templates' elements by position. Then it fires the DOMContentLoaded and load handlers and the zero-delay timers they queue. It is red when a script, while it loads, reads a name a later script (or only a page handler) defines, reads `window.X` of a top-level `const` / `let` / `class`, or throws; when a page handler or zero-delay timer throws against the stub; and when a file under `static/js` isn't loaded exactly once. It reproduces the 2026-08 `registerShortcut` drop. Today's page has no early read (`ALLOWED_EARLY_READS` is empty). It needs Node.js on PATH, a test prerequisite since 2026-09-13: without node it skips under its own reason, and `FCC_REQUIRE_NODE=1` makes a missing node an error, as for the other node-vm tests.

**Claude's calls, offered in the plan, none vetoed:** a custom Type is no head by substring; the write-site canary reads CLAUDE.md for its anchors; the Merge Filament fix went in this group. **And one made at the last integration (`e17f242`):** the slot-label scan compares the Type untrimmed, as the move engine does, until every door reads one trimmed Type (the second fix round had trimmed it, which would let a padded head row reach an engine that files a spool there without unloading the one on it).

**Left:** nothing in the group. Its ten follow-ups are standalone buglist items, filed 2026-11-10 at the top of "🗒️ Notes and standalone items", the 🟠 error-body reads first. Another chat's 📡 printer-dropout item rode along on the branch (`bb2f50a`, `64e1ff0`, buglist only) and stays in New and Unsorted.

## Items covered (quoted from `Feature-Buglist.md`)

| # | Buglist item | Direction |
|---|---|---|
| **53.1** | 🧹 Filed 2026-10-12: *"One source for the frontend's toolhead-Type lists… They agree today, so nothing has drifted, but a new toolhead Type would have to be added in every copy."* | `window.TOOLHEAD_TYPES` + helpers in `inv_core.js`, every copy switched, a canary against the backend list. |
| **53.2** | 🔎 The codebase-wide review, axis **(d) write-surface conformance**: *"the CLAUDE.md 'Spool / Filament write surfaces' table vs reality."* Derek (2026-08-03): stop finding the same CLASSES of bug one feature at a time. | A source canary that lists every Spoolman write call site. |
| **53.3** | The same item, axis **(e) load-order / export guards**: *"`if (window.X)` patterns vs `scripts.html` ordering."* | A node load-order canary. |

**Not here:** axes (b) overlay / confirm reachability and (c) silent failures stay parked: agent-heavy (about 0.5–1M tokens each), one idle window each, only with Derek's OK on the axis and the window. Axis (a), scan-path integrity, was done 2026-08-03/05.

## Decisions

- **No Derek decision.** Claude's call, offered for veto on 2026-10-19 (none vetoed): *"Two of the four 'bug-class' review categories become cheap automatic tests instead of agent reviews; the two agent-heavy ones stay parked."*

## Today's code (anchors, `dev` @ `c5c5aa6`)

- **Backend:** one frozenset, `locations_db.TOOLHEAD_TYPES` (`locations_db.py:73`).
- **Frontend: 8 hard-coded copies**, five of them adding `'Printer'`: `inv_quickswap.js:17`; `inv_loc_mgr.js:84` (`SINGLE_OCC`), `:1106` (`_isOneSpoolHeadRow`), `:1351` and `:1434` (`headTypes`), `:2690` (`_isPrinterTopologyType`); `inv_cmd.js:1359` (`_isSingleHeadRow`, eject mode) and `:2247` (`headTypes`, the Printer picker's "record it as coming from" step). Plus Force Location's substring filter ("mmu" / "tool" / "direct load", `inv_details.js:951-955`). No test pins them. Precedent: a backend inline list that missed "No MMU Direct Load" put two spools on one head (`tests/test_toolhead_resident_eject_21_3.py`).
- `inv_core.js` already hosts the classifiers (`isPrinterRowNotHead` `:938`, `isMultiSlotBox` `:950`, `isSingleSlotBox` `:951`) and loads first (`scripts.html:41`). `dashboard.html`'s inline bootstrap runs AFTER `scripts.html`, too late for `inv_quickswap.js:17`, which reads its list as it loads.
- **(d):** about 34 `spoolman_api.update_spool` / `update_filament` call sites across 7 modules, none checked against CLAUDE.md's write-surface rules. (Counted at the build, 2026-11-09: 38 record-update calls across 8 modules, plus 3 delegations inside `spoolman_api.py`; with creates, deletes and direct HTTP writes, 68 registered sites.) Patterns to copy: `tests/test_requests_timeout_canary.py`, `tests/source_family.py:read_app_family()`.
- **(e):** about 178 `if (window.X)` guards; modules load in a fixed order (`scripts.html:39-83`); a guard evaluated at load time before its provider loads silently does nothing. node is already a test prerequisite (`tests/test_core1_return_ejectall_js.py` and the other node-vm harnesses).

## Design, by sub-task

### 53.1 — one toolhead-Type list
- `window.TOOLHEAD_TYPES` + `isToolheadType(type)` + `isHeadOrPrinterType(type)` in `inv_core.js`; switch every copy (Force Location keeps its other exclusions).
- A source canary that compares the JS list with `locations_db.TOOLHEAD_TYPES` and fails on a new inline `['Tool Head', …]` literal anywhere in `static/js`.
- Serving the list from the backend is optional (the inline bootstrap runs too late, above).

### 53.2 — the write-site canary (axis d)
- List every `update_spool` / `update_filament` (and `_or_raise`) / `update_vendor` call site by module and function; a new one fails until it is added, and the failure message points at CLAUDE.md's write-surface rules (`compute_dirty_extras`, `SYSTEM_MANAGED_EXTRAS`, `LAST_SPOOLMAN_ERROR`, the surface table).

### 53.3 — the load-order canary (axis e)
- In node: load the modules in `scripts.html` order into a `vm` whose `window` is a Proxy, and record load-time reads of a `window` property that a later module defines. Reads inside functions (call time) are fine; keep a short, explained allowlist.

### Mutation-prove each
- A fake inline list, a fake write site, a fake early read → each canary goes red.

## Tests

- The three canaries; the existing Quick-Swap grid, eject-mode, Printer picker and "Move all →" tests stay green after 53.1.

## Risks

- A wrong toolhead list shows up quickly on daily paths (the Quick-Swap grid, eject mode, the Printer picker, "Move all →").
- False positives in the load-order canary: keep it to load-time reads.
- The frontend file-size pass (a standalone buglist item) should wait for 53.3: 20+ tests make "X not in source" assertions by file name, and a wrong load order makes `if (window.X)` guards skip silently.
