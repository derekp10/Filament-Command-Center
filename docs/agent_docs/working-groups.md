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
| 8 | 🟣 Keyboard Navigation & Dialog Polish | 4 | ~3.5 hrs | `READY` | [08-keyboard-nav-polish.md](tasks/08-keyboard-nav-polish.md) |
| 9 | ⬜ Quick-Swap Grid Enhancements & Printer Status Widget | 3 | ~4–5 hrs | `READY` | [09-quickswap-grid.md](tasks/09-quickswap-grid.md) |
| 10 | 🟠 Add/Edit Wizard UX Overhaul | 10 | ~6–7.5 hrs | `READY` | [10-wizard-ux-overhaul.md](tasks/10-wizard-ux-overhaul.md) |
| 11 | ⚫ External Parsers & Prusament Cleanup | 3 | ~3 hrs | `READY` | [11-external-parsers.md](tasks/11-external-parsers.md) |
| 12 | 🔵 Weight Entry Unified Component — Phase 2 | 2 | ~6–10 hrs | `DONE` 2026-04-27 | [12-weight-entry-component.md](tasks/12-weight-entry-component.md) |
| 13 | 🐛 Recent Bugfixes (Weight + Dryer Display + LOC Search + Bind Desync + Eject) | 9 | ~6–8 hrs | `DONE` 2026-05-11 | [13-recent-bugfixes.md](tasks/13-recent-bugfixes.md) |

## Items NOT Grouped (Solo, Deferred, or On Hold)

These items remain in `Feature-Buglist.md` but aren't part of a batch session:

| Item | Reason |
|------|--------|
| Screen blanking / wake lock (L8) | ON HOLD — OS-level issue |
| Config system design (L9) | NEEDS DESIGN SESSION — large standalone |
| Filabridge status light (L11) | ON HOLD — hardware/firmware |
| FIL:58 label scan (L14) | ON HOLD — needs physical label |
| Frontend lock-up (L19) | ON HOLD — hasn't recurred (modal-on-modal race partial repro) |
| Legacy QR → help button (L35) | Small standalone fix |
| Version number broken (L37) | Small standalone fix |
| Unknown crash after auto-deduct (L39+) | ON HOLD — needs repro; server logs suggest container restart mid-session |
| Confirm-change modal blocked during print (L117) | Standalone — scan/smart-move confirm_active_print path (related to 13.8) |
| Toolhead scan assigns ALL buffer spools (L119) | Standalone — toolhead must enforce max-1 spool; breaks FilaBridge sync |
| "Already verified" activity log spam (L123) | Standalone — activity log verbosity / label-verify UX |
| Force-location should clear deployed status (L125) | Standalone — force-location handler in details modal |
| Activity Log ubiquity (L167) | Standalone design decision |
| Prusa metrics tooling research (L154) | Research / future inspiration — `prusa_exporter` + Prusa-Firmware-Buddy metrics docs. Could feed 9.3 (Printer Status widget), filabridge reconcile, or richer state probing. Not actionable as a discrete task. |
| `test_quickswap_visual` baseline mismatch (L232) | Small standalone — re-capture with `UPDATE_VISUAL_BASELINES=1` after verifying the new overlay layout |
| `test_ui_details_modal_e2e` offcanvas-backdrop flake (L233) | Small standalone — test-isolation audit; same flake class as Apr 21 |
| Location Manager redesign (L195) | IN PROGRESS — multi-phase, separately tracked |
| Bulk Moves (L222) | Blocked by Location Manager Phase 3+ |
| Buffer scan assign-all (L225) | Likely already fixed — verify & close |
| Location Manager cross-browser sync (L226) | ON HOLD — needs SSE/WS |
| Mobile mode (L236) | Large standalone architectural effort |
| Dashboard modularization (L237) | Large standalone refactor |
| Filabridge reconcile utility (L295) | Standalone admin tool |
| Project Color Loadout (L299) | Blocked by Location Manager Phase 3 |
| All "On Hold" section items (L274+) | ON HOLD |

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
