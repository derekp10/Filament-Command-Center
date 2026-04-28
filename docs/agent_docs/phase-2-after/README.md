# Phase 2 After (Weight Entry Unified Component)

Snapshot of every weight-entry UI surface taken **after the Phase 2 unified
component shipped** on `feature/weight-entry-unified-component`. Captured the
same way as `../phase-2-baseline/`, with the same Playwright fixtures and the
same script (`../phase-2-baseline/capture_baseline.py`) so the only thing that
should differ between the two directories is the actual UI changes.

## Diff workflow

Open both PNG sets in any image-diff tool (VS Code's built-in image diff, or
ImageMagick `compare`):

```bash
for f in 01_bulk_weigh_out 02_quick_weigh_nested 03_wizard_empty_weight \
         04_edit_filament_spool_weight 05_post_archive_prompt 06_filabridge_manual_recovery; do
    compare "../phase-2-baseline/screenshots/${f}.png" \
            "screenshots/${f}.png" \
            "${f}_diff.png"
done
```

## What changed

| File | Surface | What's new |
|---|---|---|
| `01_bulk_weigh_out.png` | Bulk Weigh-Out | Modal-level Mode picker (Gross/Net/Additive/Set Used) at top with formula hint; per-row mini-preview line "→ used Xg · remaining Yg" under each row. |
| `02_quick_weigh_nested.png` | Quick-Weigh | Inline overlay (no longer a nested Bootstrap modal). Mode tabs, source-aware tare badge, formula hint, live preview panel, ALEX-cap warnings. |
| `03_wizard_empty_weight.png` | Wizard Spool tab | Visually unchanged. The auto-clear-on-input behavior is now owned by the shared `<EmptyWeightField>` component — same UX, less code. |
| `04_edit_filament_spool_weight.png` | Edit Filament Specs | Visually unchanged. The "⇩ Copy Vendor Weight" affordance is now driven by `<EmptyWeightField>` — same behavior, dedup'd code. |
| `05_post_archive_prompt.png` | Post-archive Swal | Visually unchanged. The Swal stays as-is because its 3-button Save/Later/Cancel UX is meaningfully different from the inline-overlay pattern; conversion deferred. |
| `06_filabridge_manual_recovery.png` | FilaBridge Manual Recovery | New mode badge at the top of the spool list (`Additive (delta consumed)` with formula hint). Per-row inputs accept `+/-` prefix syntax (e.g. `+50`). New mini-preview row under each input showing the resulting `used_weight` + `remaining`. |

## Re-running the capture

Same as the baseline script — see `../phase-2-baseline/README.md`. From a host
shell with the dev container up at `localhost:8000`:

```bash
cd inventory-hub
PHASE2_AFTER=1 python -c "
import sys, importlib.util
spec = importlib.util.spec_from_file_location('cb', '../docs/agent_docs/phase-2-baseline/capture_baseline.py')
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
from pathlib import Path
m.SCREENSHOTS_DIR = Path('../docs/agent_docs/phase-2-after/screenshots').resolve()
sys.exit(m.main())
"
```
