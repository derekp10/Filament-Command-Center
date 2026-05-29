# Working Groups — Batched Task Sessions

> Tasks from `Feature-Buglist.md` grouped by shared code surfaces for efficient batch execution.
> Each group has a detailed task file in `docs/agent_docs/tasks/`.

## Session Order (Recommended)

| # | Group | Items | Est. Effort | Status | Task File |
|---|-------|-------|-------------|--------|-----------|
| 1 | 🔵 Weight Handling Unification — Phase 1 | 3 | ~3–4 hrs | `DONE` 2026-04-27 | [01-weight-unification.md](tasks/01-weight-unification.md) |
| 2 | 🟢 Buffer Cards & Main-Menu Refresh | 3 | ~1.5–2 hrs | `DONE` 2026-04-28 | [02-buffer-cards-refresh.md](tasks/02-buffer-cards-refresh.md) |
| 3 | 🔴 Print Queue & Label Management | 7 | ~2.5–3.5 hrs | `DONE` 2026-04-28 | [03-print-queue-labels.md](tasks/03-print-queue-labels.md) |
| 4 | 🔶 Archive / Delete / Cleanup Lifecycle | 4 | ~3 hrs | `PARTIAL` 2026-04-28 (4.4 deferred) | [04-archive-delete-lifecycle.md](tasks/04-archive-delete-lifecycle.md) |
| 5 | 🟡 Edit Filament & Details Modal (small adds) | 2 | ~3 hrs | `DONE` 2026-05-08 | [05-edit-modal-small.md](tasks/05-edit-modal-small.md) |
| 6 | 🟡 Edit Filament & Details Modal (new panels) | 2 | ~3 hrs | `DONE` 2026-05-11 | [06-edit-modal-large.md](tasks/06-edit-modal-large.md) |
| 7 | 🧪 Testing Housekeeping | 2 | ~1–1.5 hrs | `DONE` 2026-05-07 | [07-testing-housekeeping.md](tasks/07-testing-housekeeping.md) |
| 8 | 🟣 Keyboard Navigation & Dialog Polish | 4 | ~3.5 hrs | `DONE` 2026-05-12 (8.1 partial — 12 button-only modals deferred as Bootstrap-default-acceptable) | [08-keyboard-nav-polish.md](tasks/08-keyboard-nav-polish.md) |
| 9 | 🟢 Quick-Swap Grid Enhancements & Printer Status Widget | 3 | ~4–5 hrs | `DONE` 2026-05-13 | [09-quickswap-grid.md](tasks/09-quickswap-grid.md) |
| 10 | 🟠 Add/Edit Wizard UX Overhaul | 11 | ~6.5–8 hrs | `DONE` 2026-05-14 (Sessions A+B+C — 10.1 progressive-disclosure cleanup shipped on `feature/wizard-cleanup-aggressive` across 9 commits / 6 feedback rounds; merged to dev + main) | [10-wizard-ux-overhaul.md](tasks/10-wizard-ux-overhaul.md) |
| 11 | ⚫ External Parsers & Prusament Cleanup | 3 | ~3 hrs | `DONE` 2026-05-13 | [11-external-parsers.md](tasks/11-external-parsers.md) |
| 12 | 🔵 Weight Entry Unified Component — Phase 2 | 2 | ~6–10 hrs | `DONE` 2026-04-27 | [12-weight-entry-component.md](tasks/12-weight-entry-component.md) |
| 13 | 🐛 Recent Bugfixes (Weight + Dryer Display + LOC Search + Bind Desync + Eject) | 9 | ~6–8 hrs | `DONE` 2026-05-11 | [13-recent-bugfixes.md](tasks/13-recent-bugfixes.md) |
| 14 | 🧪 Test-Sweep Flake Stabilization | 6 | ~3–5 hrs | `DONE` 2026-05-12 | [14-test-sweep-flake-stabilization.md](tasks/14-test-sweep-flake-stabilization.md) |
| 15 | 🪟 Canonical Overlay-Mount Helper | 3 | ~5–7 hrs | `DONE` 2026-05-11 (Path A — 5 inline overlays migrated; 4 non-inline surfaces deferred) | [15-canonical-overlay-mount.md](tasks/15-canonical-overlay-mount.md) |
| 16 | 🧰 Testing Hardening & Helper Consolidation | 4 | ~3–4 hrs | `DONE` 2026-05-12 | [16-testing-hardening.md](tasks/16-testing-hardening.md) |
| 17 | 🪟 Details Modal, Queue & Wizard End-State Polish | 5 | ~3–4 hrs | `DONE` 2026-05-14/15 (all 5 items shipped on `feature/buglist-sweep-2026-05-14`; 17.1 edit-toggle side completed 2026-05-15 by un-hiding `needs_label_print` from the wizard's hide list) | [17-details-queue-wizard-polish.md](tasks/17-details-queue-wizard-polish.md) |
| 18 | 📍 Unknown Location + Audit Mode Refinement | 2 | ~4–6 hrs | `DONE` 2026-05-15/16 (18.1 Unknown bucket + 18.2 Part A auto-park + Part B visual panel + idle watchdog all shipped on `feature/buglist-sweep-2026-05-14`; parent/child rollup deferred as future enhancement on top of the multi-location audit) | [18-unknown-location-audit.md](tasks/18-unknown-location-audit.md) |

## Items NOT Grouped (Solo, Deferred, or On Hold)

These items remain in `Feature-Buglist.md` but aren't part of a batch session:

| Item | Reason |
|------|--------|
| `locations.json` corruption recurring (L25) | `PARTIAL` 2026-05-12 — Hardening (1) per-call unique temp filename + (2) verify-after-write tripwire shipped on `feature/locations-json-write-hardening`. Monitor prod hub.log for `verify-after-write FAILED` critical lines. (3) explicit truncate + (4) Docker named volume deferred pending recurrence signal. |
| Screen blanking / wake lock (L17) | ON HOLD — OS-level issue |
| Config system design (L18) | NEEDS DESIGN SESSION for full schema. Config UI scaffold now shipped 2026-05-16 as the host for Filabridge reconcile + Build Info cards — adding future sections is just dropping another `.card` into `modals_config.html`. Full schema design (key/label/type/default/validation, import/export, hierarchy) still pending. |
| Filabridge status light (L20) | ON HOLD — all-software (FilaBridge process ↔ FCC `/api/status` polling). Defer until correlated logs from both sides + a clear repro of flicker-vs-solid behavior are available. |
| FIL:58 label scan (L23) | ON HOLD — needs physical label |
| Display modal on Display modal (L26) | `PARTIAL` 2026-05-12 + FOLLOW-UP 2026-05-14 — details↔details and wizard↔details stacking now both close siblings via `window.hideAllDetailsModals`. Retest the L28 freeze with same scenario. |
| Frontend lock-up (L28) | `DONE` 2026-05-19 on `feature/l28-frontend-lockup-ghost-eject` — root cause was polling-flood / socket-buffer exhaustion, **not** modal-on-modal as initially suspected. The 2026-05-18 DevTools console showed `net::ERR_NO_BUFFER_SPACE` cascading + uncaught `updateLogState` rejections. Added in-flight guards + `.catch()`/`.finally()` to 5 polling functions (`updateLogState`, `fetchLocations`, `loadBuffer`, `liveRefreshBuffer`, `refreshManageView`). Printer Status `_aggregate` already had one. Regression coverage in `test_polling_inflight_guards.py` (6 tests). Steady-state load remains high — see new L29 polling-reduction follow-up. |
| Unknown crash after auto-deduct (L69) | ON HOLD — needs repro; server logs suggest container restart mid-session |
| Printer Status: Core1 state-read badge (L56) | `DONE` 2026-05-25 on `feature/buglist-trio-2026-05-20`. `_pulse_section_printer_status` now joins `prusalink_api.get_printer_state` per-printer; PRINTING/PAUSED/IDLE/OFFLINE chip rendered. Latent dual-path bug (sync-pulse wiping badge between bulk pulses) also fixed via `refresh()` merging cached state. Full write-up in `completed-archive.md`. |
| Filament-attributes manager UI (L58) | `DONE` 2026-05-25 on `feature/buglist-trio-2026-05-20`. New Admin/Config → 🏷️ Filament Attributes panel with Choices Manager (add/remove/sweep-unused with styled `mountOverlay` confirm) + Per-Filament Bulk Editor (filter bar, bulk add/remove against selection). 4 new backend endpoints. Surfaced + fixed a `extra`-PATCH sibling-wipe across 3 production write surfaces (snapshot-restore now full-dict); meta-test `test_no_direct_extra_patch_in_production_code` guards CI. Full write-up in `completed-archive.md`. |
| **NEW** Make Activity Log more ubiquitous (L238) | Persistent mini-log widget OR "N new events" pill OR modal-aware docking so the log is always visible during modal-heavy workflows. Once log is always-visible, toast durations can drop and toasts can become purely "happened now" flashes. Candidate approaches stack — pick one or all. (Partial progress: corner `#fcc-log-pill` "N new" flash + click-to-open compact log overlay shipped under L286 follow-on — but the in-modal docking ask is still open.) |
| Prusa metrics tooling research (L161) | Research / future inspiration — `prusa_exporter` + Prusa-Firmware-Buddy metrics docs. Could feed 9.3 (Printer Status widget), filabridge reconcile, or richer state probing. Not actionable as a discrete task. |
| **NEW** Prusament temp scans should update existing filaments (L198) | Scan should update min/max bed + nozzle temps on existing filaments (currently doesn't backfill legacy data). |
| **NEW** Prusament data-link spool scan should update existing fields (L200) | Scanning the QR into the spool search field should update all available fields on the existing spool, preserving current usage (weight differs → legacy spool used; preserve current weight, update total weight + other metadata). |
| Edit Filament > Import from External collapse glitch (L202) | `DONE` 2026-05-25 on `feature/buglist-trio-2026-05-20`. Snap-collapse CSS on `#editfil-import-panel.collapsing` + `overflow: hidden` removes the Bootstrap-animation sliver. Regression coverage in `test_edit_filament_external_import.py::test_l202_collapse_leaves_no_sliver`. |
| **NEW** Box slot → empty doesn't propagate to filabridge (L204) | Setting a dryerbox slot (attached to a toolhead) to empty leaves FilaBridge thinking the old spool is still there. Sibling of L206. |
| **NEW** Color section: name/count cramped in collapsed wizard view (L15) | Edit/add wizard rolled-up Color collapsed section needs spacing between color name and color count (multicolor; possibly single). Small CSS fix. |
| **NEW** Filament label-confirm doesn't also confirm sample-printed + no UI for sample status (L17) | Label-confirm scan should mark sample-printed in a pair; also no editable surface for sample-printed exists today. Touches the scan-handler + Edit Filament + Display modal. |
| **NEW** In-progress printing modal: QR codes appear on right side (L19) | Sometimes the in-progress printing update modal renders its QR codes on the right side instead of the expected position. Seemed to coincide with a background toast — possibly unrelated. Needs repro. |
| **NEW** Search filaments by most-spools-available (L21) | New search/sort axis — surface filaments ranked by spool count. Touches `/api/search` + offcanvas search. |
| **NEW** Computer-room cart 2 labels constantly reappear in print queue (L23) | Location labels for `CR-CART-2` (or similar) keep being re-added to the print queue. Likely a label-re-enqueue bug in the print-queue maintenance / label-needed path. |
| **NEW** Print Status not updating weight on print-finish (L25) | When a print finishes, the Print Status doesn't reflect the new weight — likely missing a hook into the live-update path. Flagged at commit `cfe00ed7` 2026-05-19. Plausibly clusters with L204 (box-slot empty doesn't propagate). |
| Polling architecture reduction (L206) | `DONE` 2026-05-19 on `feature/l28-frontend-lockup-ghost-eject` (shared with L28). Bulk `/api/dashboard_pulse` endpoint + adaptive cadence (5s active / 15s idle / 30s hidden). ~3 req/sec → ~0.2 req/sec active. Regression coverage in `test_dashboard_pulse_api.py` (13) + `test_dashboard_pulse_frontend.py` (6). |
| Box-slot ↔ toolhead spool-switching inconsistency (L206) | **NEEDS INVESTIGATION** — continuing-bug observation 2026-05-12: eject doesn't fully clear toolhead bind when box slot is bound to a toolhead. Despite Group 13.6 (toolhead-first assign + auto-archive cleanup), the eject path still leaves stale state. 10 min of Activity Log capture included as raw data for diagnosis. Likely a new flavor of the same architectural gap — different code path than 13.6 covered. L204 is the narrower sibling. |
| Refactor strip cards in Location Manager (L241) | UI/Theming standalone — merge horizontal layout with modern grid card features |
| High-Contrast Pop everywhere (L242) | Large UI/Theming pass — White Text + Heavy Black Shadow + adaptive variants per color |
| Slicer Profile animation reuse (L243) | Small standalone — identify the nifty animation, reuse elsewhere |
| Help button per modal (L250) | Standalone — modal-specific help affordance |
| Legacy ID assignment tool (L252) | Standalone — pair existing Spoolman IDs to physical legacy spools (bulk-import case) |
| Location Manager redesign (L271) | IN PROGRESS — multi-phase, Phase 1A shipped (parent_id additive); Phases 1B+ separately tracked |
| Bulk Moves (L298) | Blocked by Location Manager Phase 3+ |
| Shapeshifting QR codes (L299) | Small UX win — extend shapeshift pattern to more places (Audit button, etc.) |
| Location Manager cross-browser sync (L302) | ON HOLD — needs SSE/WS transport |
| Mobile mode (L315) | Large standalone architectural effort |
| Dashboard modularization (L316) | Large standalone refactor |
| Make as much configurable (L317) | Folds into Config system (L18) — see scaffold note |
| Spoolman extras sort order restore (L318) | Standalone — extras drift order when modified |
| Clean up filament attributes (L319) | `PARTIAL` 2026-05-16 + AUTO-RUN 2026-05-19 — script shipped at `setup-and-rebuild/migrate_filament_attributes.py` + auto-cleanup at startup via `spoolman_api.ensure_filament_attributes_cleaned()`. `For Infill` + `Matte Pro` pending Derek's prod check before promotion to DELETE_CHOICES. |
| Continue supporting Spoolman Import from External (L341) | Tracks gap list of unimplemented sources (open-filament-database, Prusament spool-specific, Open Print Tags) |
| Dev Spoolman/filabridge environment (L345) | Standalone — set up isolated dev versions |
| Log cleanup routine (L347) | Standalone — log file rotation/cleanup |
| Dynamic setup code refactor (L348) | Standalone — keep brand-new-install path working |
| Continue Spoolman vendor→filament→spool cascade (L349) | Continuing |
| Configure extras propagation Filament↔Spool (L350) | Standalone — relates to Config system |
| Spool product data text field (L351) | Standalone — Prusament link, etc. |
| Background refresh in Location Manager (L352) | Standalone — periodic spool text updates |
| Project Color Loadout (L391) | Blocked by Location Manager Phase 3 |
| Core One MMU rows cleanup (Derek aside) | Not yet a discrete buglist entry — Derek 2026-05-16 noted: remove unused `CORE1-M1`–`CORE1-M5` MMU rows + decide whether `CORE1-M0` should be renamed from "No MMU Direct Load" to simply "Tool Head". File as a buglist item next time. |
| All "On Hold" section items | ON HOLD |

**Note on test flakes:** The `test_quickswap_visual` baseline mismatch, `test_ui_details_modal_e2e` offcanvas-backdrop flake, and `test_amazon_parser_matching` BS4-missing issue were all closed by Group 14 (14.4 / 14.3 / 14.5 respectively). Detailed write-up in `completed-archive.md`. Post-Group-14 follow-ups (parallel `tests/` directory, `_open_manage` consolidation, `reset_dom_state_js` audit, Windows pip footgun) are bundled into Group 16.

## How to Use

**With Claude Code:**
```
/project:work-group 1          # Start Group 1 (Weight Unification)
/project:work-group weight     # Same — matches by keyword
/project:finish-group           # When done — commit, archive, update status
```

**With Gemini / Antigravity:**
- Point at the specific task file: "Read `docs/agent_docs/tasks/01-weight-unification.md` and implement it"
- Or use the `/startnewtask` workflow which now knows about these groups
