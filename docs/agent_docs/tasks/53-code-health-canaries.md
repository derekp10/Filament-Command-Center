# Group 53: 🧹 Code-Health Canaries

**Branch name (when started):** `feature/group-53-code-health-canaries`
**Estimated effort:** SMALL–MEDIUM (~5–9 h, 1 session). 53.1 ~1.5–3 h · 53.2 ~1–2 h · 53.3 ~2–4 h.
**Risk:** **LOW–MEDIUM.** 53.1 touches daily paths (the Quick-Swap grid, eject mode, the Printer picker, "Move all →"); 53.2 and 53.3 are tests only.

> **Status: `TODO` — filed 2026-10-19 (`/refresh-groups`). No Derek decision needed.** Not in the 48 + 49 + 51 + 52 bundle.
> One frontend toolhead-Type list, and two classes of bug turned into cheap automatic source checks instead of agent reviews. Every decision: [refresh-2026-10-19.md](refresh-2026-10-19.md).
> Code anchors were read on `dev` @ `c5c5aa6` (the refresh's grounding) and spot-checked at `08c4b10`. Line numbers drift, so re-grep before editing.

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
- **(d):** about 34 `spoolman_api.update_spool` / `update_filament` call sites across 7 modules, none checked against CLAUDE.md's write-surface rules. Patterns to copy: `tests/test_requests_timeout_canary.py`, `tests/source_family.py:read_app_family()`.
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
