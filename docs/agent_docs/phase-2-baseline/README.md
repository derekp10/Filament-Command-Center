# Phase 2 Baseline (Weight Entry Unified Component)

Snapshot of every weight-entry UI surface taken **immediately after the Phase 1 merge** (`feature/weight-unification` → `dev`, 2026-04-27). Use this directory as the "before" reference when reviewing the Phase 2 unified weight-entry component (Group 12).

## What's here

```
phase-2-baseline/
├── README.md              ← you are here
├── capture_baseline.py    ← Playwright script that produced the screenshots
└── screenshots/           ← PNG of each weight-entry surface in its Phase 1 state
```

## Reference points

- **Git tag:** `phase-2-baseline` — points at the merge commit (`e8bd7d0` or current `dev` HEAD post-merge). Diff against this tag to see the full Phase 2 delta:
  ```bash
  git diff phase-2-baseline..HEAD -- inventory-hub/static/js/modules
  git diff phase-2-baseline..HEAD -- inventory-hub/templates/components
  ```
- **Visual baselines:** the existing Playwright visual-regression baselines at `inventory-hub/tests/__screenshots__/chromium-1600x1300/` are the *automated* before-pictures; this directory is the *curated* reference for design review.

## Surfaces captured

Each screenshot shows ONE weight-entry surface in a known state, populated via fetch stubs so the layout is deterministic and reproducible. Phase 2 will replace or wrap each of these with the unified `<WeightEntry>` component.

| Filename | Surface | Source | Notes |
|---|---|---|---|
| `01_bulk_weigh_out.png` | Bulk Weigh-Out modal | `inv_weigh_out.js:openWeighOutModal` | Table of held spools with per-row weight inputs. Shows the auto-archive toggle, `force_unassign` chain hint. |
| `02_quick_weigh_nested.png` | Quick-Weigh nested modal | `inv_weigh_out.js:openQuickWeigh` | The `+/-` prefix delta-entry syntax. Drilled in from the bulk modal. |
| `03_wizard_empty_weight.png` | Wizard Spool tab empty-weight area | `inv_wizard.js:openNewSpoolFromFilamentWizard` | **Phase 1 NEW**: shows the "↩ from filament/vendor" badge and pre-filled value. |
| `04_edit_filament_spool_weight.png` | Edit Filament modal — Specs tab | `inv_details.js:openEditFilamentForm` | Vendor hint badge + "⇩ Copy Vendor Weight" button. |
| `05_post_archive_prompt.png` | Post-archive empty-weight Swal | `inv_details.js:showArchiveEmptyWeightPrompt` | **Phase 1 FIXED**: Enter key now submits. Vendor/material context display. |
| `06_filabridge_manual_recovery.png` | FilaBridge Manual Recovery modal | `templates/components/modals_filabridge_recovery.html` | Per-spool delta-input table ("Grams Used") with Auto-Parse / Browse-Local-GCode actions. Captured by stubbing `/api/fb_recovery_spools` and calling `window.openFilaBridgeRecovery` directly with a synthetic error meta. |

## Re-running the capture

If the dev container's UI changes and you need fresh screenshots:

```bash
# Make sure the dev container is up at localhost:8000
cd inventory-hub
python ../docs/agent_docs/phase-2-baseline/capture_baseline.py
```

The script clobbers existing PNGs in `screenshots/`. If you want to preserve a prior set, copy the directory first.

## Phase 2 comparison workflow

When Phase 2 is ready for review:

1. Check out the Phase 2 branch (`feature/weight-entry-unified-component`)
2. Restart the dev container
3. Run `capture_baseline.py` writing to a NEW directory (e.g. `phase-2-after/`)
4. Diff side-by-side: open both PNG sets in any image-diff tool, or use ImageMagick:
   ```bash
   compare phase-2-baseline/screenshots/01_bulk_weigh_out.png phase-2-after/01_bulk_weigh_out.png diff_01.png
   ```
5. The PR description should embed before/after pairs for each surface that changed.
