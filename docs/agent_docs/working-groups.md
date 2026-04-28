# Working Groups — Batched Task Sessions

> Tasks from `Feature-Buglist.md` grouped by shared code surfaces for efficient batch execution.
> Each group has a detailed task file in `docs/agent_docs/tasks/`.

## Session Order (Recommended)

| # | Group | Items | Est. Effort | Status | Task File |
|---|-------|-------|-------------|--------|-----------|
| 1 | 🔵 Weight Handling Unification — Phase 1 | 3 | ~3–4 hrs | `DONE` 2026-04-27 | [01-weight-unification.md](tasks/01-weight-unification.md) |
| 2 | 🟢 Buffer Cards & Main-Menu Refresh | 3 | ~1.5–2 hrs | `READY` | [02-buffer-cards-refresh.md](tasks/02-buffer-cards-refresh.md) |
| 3 | 🔴 Print Queue & Label Management | 6 | ~2–3 hrs | `READY` | [03-print-queue-labels.md](tasks/03-print-queue-labels.md) |
| 4 | 🔶 Archive / Delete / Cleanup Lifecycle | 4 | ~3 hrs | `READY` | [04-archive-delete-lifecycle.md](tasks/04-archive-delete-lifecycle.md) |
| 5 | 🟡 Edit Filament & Details Modal (small adds) | 2 | ~3 hrs | `READY` | [05-edit-modal-small.md](tasks/05-edit-modal-small.md) |
| 6 | 🟡 Edit Filament & Details Modal (new panels) | 2 | ~3 hrs | `READY` | [06-edit-modal-large.md](tasks/06-edit-modal-large.md) |
| 7 | 🧪 Testing Housekeeping | 2 | ~1–1.5 hrs | `READY` | [07-testing-housekeeping.md](tasks/07-testing-housekeeping.md) |
| 8 | 🟣 Keyboard Navigation & Dialog Polish | 3 | ~3 hrs | `READY` | [08-keyboard-nav-polish.md](tasks/08-keyboard-nav-polish.md) |
| 9 | ⬜ Quick-Swap Grid Enhancements | 2 | ~2–3 hrs | `READY` | [09-quickswap-grid.md](tasks/09-quickswap-grid.md) |
| 10 | 🟠 Add/Edit Wizard UX Overhaul | 8 | ~5–6 hrs | `READY` | [10-wizard-ux-overhaul.md](tasks/10-wizard-ux-overhaul.md) |
| 11 | ⚫ External Parsers & Prusament Cleanup | 3 | ~3 hrs | `READY` | [11-external-parsers.md](tasks/11-external-parsers.md) |
| 12 | 🔵 Weight Entry Unified Component — Phase 2 | 2 | ~6–10 hrs | `READY` | [12-weight-entry-component.md](tasks/12-weight-entry-component.md) |

## Items NOT Grouped (Solo, Deferred, or On Hold)

These items remain in `Feature-Buglist.md` but aren't part of a batch session:

| Item | Reason |
|------|--------|
| Screen blanking / wake lock (L6) | ON HOLD — OS-level issue |
| Filabridge status light (L12) | ON HOLD — hardware/firmware |
| FIL:58 label scan (L15) | ON HOLD — needs physical label |
| Frontend lock-up (L22) | ON HOLD — hasn't recurred |
| Legacy QR → help button (L62) | Small standalone fix |
| Version number broken (L64) | Small standalone fix |
| Config system design (L10) | NEEDS DESIGN SESSION — large standalone |
| Location Manager redesign (L108–133) | IN PROGRESS — multi-phase, separately tracked |
| Mobile mode (L156) | Large standalone architectural effort |
| Dashboard modularization (L157) | Large standalone refactor |
| Activity Log ubiquity (L74–79) | Standalone design decision |
| Bulk Moves (L135) | Blocked by Location Manager Phase 3+ |
| Buffer scan assign-all (L138) | Likely already fixed — verify & close |
| Location Manager cross-browser sync (L139) | ON HOLD — needs SSE/WS |
| Filabridge reconcile utility (L197) | Standalone admin tool |
| Project Color Loadout (L201) | Blocked by Location Manager Phase 3 |
| All "On Hold" section items (L177–183) | ON HOLD |

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
