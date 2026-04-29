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
| 5 | 🟡 Edit Filament & Details Modal (small adds) | 2 | ~3 hrs | `READY` | [05-edit-modal-small.md](tasks/05-edit-modal-small.md) |
| 6 | 🟡 Edit Filament & Details Modal (new panels) | 2 | ~3 hrs | `READY` | [06-edit-modal-large.md](tasks/06-edit-modal-large.md) |
| 7 | 🧪 Testing Housekeeping | 2 | ~1–1.5 hrs | `READY` | [07-testing-housekeeping.md](tasks/07-testing-housekeeping.md) |
| 8 | 🟣 Keyboard Navigation & Dialog Polish | 3 | ~3 hrs | `READY` | [08-keyboard-nav-polish.md](tasks/08-keyboard-nav-polish.md) |
| 9 | ⬜ Quick-Swap Grid Enhancements | 2 | ~2–3 hrs | `READY` | [09-quickswap-grid.md](tasks/09-quickswap-grid.md) |
| 10 | 🟠 Add/Edit Wizard UX Overhaul | 10 | ~6–7.5 hrs | `READY` | [10-wizard-ux-overhaul.md](tasks/10-wizard-ux-overhaul.md) |
| 11 | ⚫ External Parsers & Prusament Cleanup | 3 | ~3 hrs | `READY` | [11-external-parsers.md](tasks/11-external-parsers.md) |
| 12 | 🔵 Weight Entry Unified Component — Phase 2 | 2 | ~6–10 hrs | `DONE` 2026-04-27 | [12-weight-entry-component.md](tasks/12-weight-entry-component.md) |

## Items NOT Grouped (Solo, Deferred, or On Hold)

These items remain in `Feature-Buglist.md` but aren't part of a batch session:

| Item | Reason |
|------|--------|
| Screen blanking / wake lock (L8) | ON HOLD — OS-level issue |
| Config system design (L12) | NEEDS DESIGN SESSION — large standalone |
| Filabridge status light (L14) | ON HOLD — hardware/firmware |
| FIL:58 label scan (L17) | ON HOLD — needs physical label |
| Frontend lock-up (L22) | ON HOLD — hasn't recurred |
| Legacy QR → help button (L43) | Small standalone fix |
| Version number broken (L45) | Small standalone fix |
| Unknown crash after auto-deduct (L47–L122) | ON HOLD — needs repro; server logs suggest container restart mid-session |
| Confirm-change modal blocked during print (L125) | Standalone — scan/smart-move confirm_active_print path |
| Toolhead scan assigns ALL buffer spools (L127) | Standalone — toolhead must enforce max-1 spool; breaks FilaBridge sync |
| "Already verified" activity log spam (L131) | Standalone — activity log verbosity / label-verify UX |
| Activity Log ubiquity (L140–L145) | Standalone design decision |
| Location Manager redesign (L173–L199) | IN PROGRESS — multi-phase, separately tracked |
| Bulk Moves (L201) | Blocked by Location Manager Phase 3+ |
| Buffer scan assign-all (L204) | Likely already fixed — verify & close |
| Location Manager cross-browser sync (L205) | ON HOLD — needs SSE/WS |
| Mobile mode (L215) | Large standalone architectural effort |
| Dashboard modularization (L216) | Large standalone refactor |
| Filabridge reconcile utility (L274) | Standalone admin tool |
| Project Color Loadout (L278) | Blocked by Location Manager Phase 3 |
| All "On Hold" section items (L253–L260) | ON HOLD |

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
