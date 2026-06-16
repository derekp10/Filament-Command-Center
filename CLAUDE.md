Architecture & Environment:
Dev: Runs in a local Docker instance. Always provide terminal and execution commands in a Docker context (e.g., docker exec, docker-compose).
Front end for dev can be found here: http://localhost:8000/
Spoolman for dev can be found here: http://192.168.1.29:7913/
Filabridge: **DECOMMISSIONED 2026-06-13** (FilaBridge Phase-2 cutover — FCC absorbed all of its responsibilities and the container was stopped). FCC is now standalone; there is no FilaBridge process/URL. The `needo37` image is kept pinned as a do-nothing fallback only. Residual `fb_url`/`filabridge_url` params still threaded through the code are vestigial back-compat signatures — see the `Feature-Buglist.md` "vestigial FilaBridge artifacts" cleanup item.
Prod: Hosted on a TrueNAS server. Keep deployment, storage, and networking suggestions strictly compatible with TrueNAS architecture.

## Testing

- **pytest + Playwright run on the host**, not inside the Docker image. Install once: `pip install -r requirements-dev.txt && playwright install chromium`. All E2E tests then hit `http://localhost:8000` of the running container.
- **Windows pip ↔ pytest interpreter mismatch (Derek's machine)**: bare `pip install <pkg>` resolves to `D:\Programming\Languages\Python\Python311\python.exe`, but `pytest` runs under `C:\Python314\python.exe`. Packages installed via bare `pip` are invisible to the sweep. Canonical install command for this machine: `"C:/Python314/python.exe" -m pip install <pkg>` (or `... -r requirements-dev.txt`). This bit the Group 14.5 BS4 install — beautifulsoup4 went into 3.11, the sweep imported under 3.14, and `test_amazon_parser_matching` skipped with `ModuleNotFoundError`.
- **Visual regression**: baselines live at `inventory-hub/tests/__screenshots__/chromium-1600x1300/` — PIL-backed diff with a 1% pixel tolerance. Set `UPDATE_VISUAL_BASELINES=1` to recapture. The 1600×1300 viewport matches your dev testing window; prod / Framework 12 viewports can be added later without touching the harness.
- **Shared fixtures**: `inventory-hub/tests/conftest.py` exposes `page`, `api_base_url`, `clean_buffer`, `with_held_spool`, `seed_dryer_box`, `seed_via_ui`, `snapshot`, `scan`, and `require_server` (which skips with a friendly message when the server is down).
- **Production deploy hygiene**: the Docker image is built from `inventory-hub/Dockerfile` with `.dockerignore` excluding `tests/`, `pytest.ini`, `__screenshots__/`, `conftest.py`, and any stray `test_*.py` at the inventory-hub root. Dev-only deps stay in `requirements-dev.txt`; the image's hand-installed `flask requests` remain prod-only.

## Dryer Box ↔ Toolhead Bindings (Phase 2/3)

- **Storage**: per-slot, on each Dryer Box record in `inventory-hub/locations.json` under `extra.slot_targets` — a dict keyed by slot number (string), values are Toolhead / MMU Slot / No MMU Direct Load LocationIDs, or absent = unassigned (staging/drying).
- Example:
  ```json
  { "LocationID": "PM-DB-XL-L", "Type": "Dryer Box", "Max Spools": "4",
    "extra": { "slot_targets": { "1": "XL-1", "2": "XL-2", "3": "XL-3" } } }
  ```
  Slot 4 is absent → staging only. Split boxes (one box per printer side) are first-class; the model has no `default_printer` concept.
- **Editing UI**: Location Manager → open a Dryer Box → "🔗 Slot → Toolhead Feeds" collapsible section. Dropdowns are grouped by printer via `<optgroup>`.
- **Quick-Swap**: Location Manager → open a toolhead (Tool Head / MMU Slot / No MMU Direct Load) → "⚡ Quick-Swap Slots" grid aggregates every (box, slot) feeding that toolhead. Tap or keyboard-nav + Enter to swap. `Q` focuses the grid; arrow keys move; Enter triggers confirm overlay (inline div, never nested Swal).
- **Keyboard shortcut reference**: `?` button in the dashboard title bar (or the `?` key anywhere outside inputs). Any new shortcut added elsewhere should call `window.registerShortcut({id, scope, keys, description})` in `static/js/modules/shortcuts_registry.js` so the overlay stays complete.
- **Indxx forward-compat**: the model scales to an arbitrary number of toolheads by simply adding entries to `config.json:printer_map`. No schema change required for the planned Core One+ → indxx upgrade (8–10 toolheads).
- **Legacy**: the old `config.json:feeder_map` key was retired in M7. A back-compat migration in `app.py` still runs on startup so any surviving install gets its entries imported into `slot_targets` automatically the first time it boots the new code.

## Project Conventions

- **Inline overlays MUST route through `window.mountOverlay()`** (Group 15 — see [docs/agent_docs/tasks/15-canonical-overlay-mount.md](docs/agent_docs/tasks/15-canonical-overlay-mount.md) for the rationale). Don't `createElement` + `document.body.appendChild` + custom `focusin`/`keydown` listeners; the helper owns the z-index ladder, the focus-guard that defeats Bootstrap's `_enforceFocus`, host-close cleanup, occlusion of underlying selects, and idempotent teardown. Reference implementations: [weight_entry.js](inventory-hub/static/js/modules/weight_entry.js), [weight_utils.js](inventory-hub/static/js/modules/weight_utils.js) (missing-tare prompt), [duplicate_picker.js](inventory-hub/static/js/modules/duplicate_picker.js), [inv_quickswap.js](inventory-hub/static/js/modules/inv_quickswap.js) (Quick-Swap confirm), [inv_details.js](inventory-hub/static/js/modules/inv_details.js) (force-location escape-confirm).
  - **Z-index ladder** (constants on `window.OVERLAY_Z`):
    - `STANDARD = 20000` — single overlay above any Bootstrap modal/offcanvas. Pass `tier: 'standard'` (default).
    - `CONFIRM = 20100` — confirm overlay above a standard overlay (e.g. missing-tare prompted from inside WeightEntry). Pass `tier: 'confirm'`.
    - Toast layer is 11000 — intentionally BELOW overlays so a confirm isn't drowned out by toast noise.
  - **Focus guard** is the working pattern from `89c6f39`: capture-phase `focusin` listener on `document` that `stopImmediatePropagation`s events targeting the overlay subtree. Mounting INSIDE the modal subtree to escape `_enforceFocus` was tried and reverted (13.1) — it loses the z-index war. Do NOT subtree-mount overlays.
  - **Escape contract**: `mountOverlay`'s `onEscape` (or default cleanup) uses `stopImmediatePropagation`, so sibling capture-phase listeners on `document` won't fire. Callers must NOT also handle Escape — pass `onEscape: () => yourCancel()` if you need a custom cancel side-effect.
  - **Host cascade**: pass `host: someBootstrapModalEl` to auto-clean the overlay when the host emits `hidden.bs.modal` / `hidden.bs.offcanvas`. No overlay outlives its parent.
  - **No nested `Swal.fire()`** — the original prohibition stands. Nested Swals don't stack and dismiss each other; route confirmation dialogs through `mountOverlay` instead.
  - **Z-order incident symptom checklist** — each symptom maps to a `mountOverlay` behavior; if you see one, suspect a bypassed `mountOverlay`:
    - Click triggered something but I can't see it → mount target wrong (must be `document.body`).
    - Overlay rendered behind sibling modal chrome → wrong tier or subtree-mounted.
    - Brief processing flash then "nothing" → overlay closed itself but parent listener didn't know.
    - Inline overlay's Escape closes BOTH the overlay and its host modal → caller is also handling Escape; let `mountOverlay` own it.
    - Overlay lingers after host modal closes → didn't pass `host`.
    - `<select>` dropdown under the host intercepts overlay clicks → didn't pass `occlude`.
- **Keyboard nav idiom**: arrow keys move a `.kb-active` class between focusable items (wraps at edges), Enter confirms, Escape cancels or prompts. Auto-focus the primary input when a modal opens. Force Location modal + Quick-Swap grid are reference implementations.
- **Activity Log + Toasts**: every scan outcome (success, warning, error, partial) writes an Activity Log entry AND raises a toast. Error toasts use ≥7 s durations so blind-scanning failures don't slip past. Success toasts 4 s. `showToast(msg, type, duration)` where `type` is one of `success` / `error` / `warning` / `info`.

## Spool / Filament write surfaces

Every code path that calls `spoolman_api.update_spool` or `update_filament` has the same two failure modes: (1) Spoolman replaces the whole `extra` dict on PATCH so partial payloads silently wipe siblings; (2) on rejection both functions return `None` and most callers don't surface the actual error body. Both are the root of the 2026-04-26 / 2026-04-27 prod outages.

Conventions every write surface MUST follow:

- **Use the helper, not inline diff loops.** `spoolman_api.compute_dirty_extras(existing, requested, system_managed=...)` returns `(dirty_dict, stripped_keys)`. Pass `system_managed=spoolman_api.SYSTEM_MANAGED_EXTRAS` whenever the surface is user-driven editing (wizard, vendor edit modal, manufacturer edit modal, etc.) — that frozenset enumerates the keys owned exclusively by `perform_smart_move` / `perform_smart_eject` (`container_slot`, `physical_source`, `physical_source_slot`).
- **Surface `LAST_SPOOLMAN_ERROR` on failure.** Both `update_spool` and `update_filament` populate the module-global on every rejection (the symmetry was fixed 2026-04-27 — pre-fix, only `update_filament` did). Read it in your `else:` branch and either (a) write to the activity log via `state.add_log_entry(..., "ERROR", "ff4444")`, or (b) return it in the JSON response so the frontend can `showToast(err, "error", 7000)`.
- **For high-stakes paths use `_or_raise`.** `update_spool_or_raise` and `update_filament_or_raise` raise `spoolman_api.SpoolmanRejection` instead of returning `None`. Use these on slot assignment, label-confirm scans, force-move, and weigh-out — paths where silent failure left the user with no signal.
- **Don't add `force_reset=True` to `setup_fields.py` lightly.** A field-schema delete wipes that extra on every record. The existing `migrate_container_slot_to_text()` is the template for any future legitimate type migration: snapshot values, force_reset, restore. Steady-state setup_fields runs MUST be value-preserving.

Inventory of current production write surfaces (keep this list updated when adding new ones):

| File:Line | Endpoint / Function | Notes |
|-----------|--------------------|-------|
| `app.py:1095` | `api_edit_spool_wizard` spool save | Uses `compute_dirty_extras` with SYSTEM_MANAGED_EXTRAS guard. |
| `app.py:1106` | `api_edit_spool_wizard` filament save | Surfaces `LAST_SPOOLMAN_ERROR` in response JSON. |
| `app.py:1932` | `/api/locations` cascade unassign | Best-effort fire-and-forget; logs each failure. |
| `app.py:1145` | `/api/spool/update` generic partial update | `update_spool` (read-merge-write extras + `used_weight ≤ initial_weight` cap + auto-archive/unarchive on remaining); surfaces `LAST_SPOOLMAN_ERROR` in the `error`/`msg` response fields. ⚠️ Sending `initial_weight` here runs `_auto_archive_on_empty`/`_auto_unarchive_on_refill` — a too-low total can silently archive+unassign a loaded spool. The L200 path deliberately does NOT use this; see the dedicated endpoint below. |
| `app.py:1227` | `/api/spool/prusament_apply_weights` (L200) | Confirm-apply for the Prusament-scan spool-weight correction. RE-VALIDATES against the live spool (refuses if archived, or if the new total would leave remaining ≤ ~0 and trip auto-archive), writes only `initial_weight`/`spool_weight` via `update_spool_or_raise` (used_weight preserved). Returns `status: success`/`blocked`/`error`. Hardened per the 2026-06-05 adversarial review. |
| `app.py:2221` | `/api/update_filament` quick-edit | Reference impl — surfaces error in response JSON. |
| `app.py:2718` | spool label-confirm scan | Logs ERROR with Spoolman body; emits "already verified" info path. |
| `app.py:2791` | filament label-confirm scan | Same pattern as spool side. |
| `app.py:3723` | `/api/print_queue/mark_printed` (spool) | Returns Spoolman error in response. |
| `app.py:3734` | `/api/print_queue/mark_printed` (filament) | Returns Spoolman error in response. |
| `app.py:3758` | `/api/print_queue/set_flag` (spool) | Returns Spoolman error in response. |
| `app.py:3768` | `/api/print_queue/set_flag` (filament) | Returns Spoolman error in response. |
| `app.py:4014` | `/api/backfill_spool_weights` | Per-spool `errors` list in response. |
| `app.py:4087` | print deduct — `_apply_usage_to_printer` | **FCC-native print-usage deduct** (replaced the FilaBridge auto-deduct in the 2026-06-13 Phase-2 cutover). Writes `used_weight` via `update_spool` per toolhead; the shared primitive for BOTH the cancelled-print partial deduct (`deduct_cancelled_print`, app.py:4218 — decode `.bgcode` + per-tool prefix-parse to the cancel/M73 point) AND the FINISHED completion deduct. Exactly-once via `print_deduct_ledger`; activity-log on failure. |
| `app.py:4638` | cancel/ambiguous-review confirm-apply | User-confirmed deduct: re-reads CURRENT `used_weight` (so a weigh-out between preview and confirm isn't clobbered), clamps grams to real remaining, writes `used_weight` via `update_spool`; activity-log on success/failure. |
| `app.py:679` | `PATCH /api/vendors/<id>` Vendor Edit modal save | Uses `update_vendor_or_raise`; merges `extra` against existing record so partial PATCH preserves siblings; activity log on both success and rejection; surfaces Spoolman error body in response JSON for the modal to toast at 7s. |
| `logic.py:524` | `perform_smart_move` unseat existing | Read-merge-write reference impl; logs failure. |
| `logic.py:575` | `perform_smart_move` toolhead branch | Activity log on failure with Spoolman body. |
| `logic.py:603` | `perform_smart_move` dryer branch | Activity log on failure. |
| `logic.py:628` | `perform_smart_move` generic branch | Activity log on failure. |
| `logic.py:827` | `perform_smart_eject` return-home | Activity log on failure. |
| `logic.py:853` | `perform_smart_eject` relocate | Activity log on failure. |
| `logic.py:1007` | `perform_force_unassign` | Activity log on failure. |
| `inv_details.js:promptEditSlicerProfile` | Pencil overlay on filament details modal | Client-side merges current `extra` from `/api/filaments/<id>` before POST to `/api/update_filament` so siblings (`nozzle_temp_max`, `sheet_link`, `filament_attributes`, etc.) are preserved. Surfaces error in Swal. Fires `add_choice` POST after successful save when user typed a brand-new profile name. |

### Weight-entry surfaces (known fragmentation hot-spot)

Within the table above, the weight-touching entries are themselves a fragmented sub-system: `app.py:3723` (mark_printed), `app.py:4014` (backfill), `app.py:4087`/`4638` (FCC-native print deduct `_apply_usage_to_printer` + cancel-review confirm — replaced the retired FilaBridge deduct paths), plus the frontend modals (`inv_weigh_out.js` weigh-out, `inv_wizard.js` empty-weight fields, `inv_details.js` post-archive prompt + filament edit). Each accepts a slightly different input form (gross / net / additive / delta / field-only) with inconsistent terminology and inconsistent empty-spool-weight resolution.

Phase 1 (current branch) extracted `resolveEmptySpoolWeight` into `static/js/modules/weight_utils.js` so the cascade has one canonical home. Phase 2 (separate branch — see `Feature-Buglist.md` "Unified weight-entry component") will build a single `<WeightEntry>`-style component reused by every weight surface, with mode-aware input (gross / net / additive / delta), shared missing-empty-weight prompt, and a preview of the computed `used_weight` before submit. **Don't add new weight-entry UI before Phase 2** — feed any new requirements into that design instead.

## User preferences (pre-Config-system)

Until the Config system (Feature-Buglist.md L9) lands, a small number of user preferences are persisted client-side in `localStorage` so the user doesn't have to re-pick them every session. When the Config system arrives, these keys should be migrated into its schema as routine value-moves; no architectural decisions live in here.

| Key | Type | Values | Owner |
|-----|------|--------|-------|
| `fcc.weighEntry.defaultMode` | string | `gross` / `net` / `additive` / `set_used` | `<WeightEntry>` overlay — last mode the user clicked "Set as default" on (or `D` shortcut). Read on overlay open, falls through to the caller-supplied `defaultMode` option when unset/invalid. |
| `fcc.fab.pos` | JSON `{left,bottom}` | px distances from the viewport's left / bottom edges | `fab_drag.js` (shared `draggable_pill.js` engine) — the draggable global search FAB's parked position (buglist 21.1). Written on drag-end; long-press resets to the default. Loaded + viewport-clamped on page load; absent/invalid → bottom-left cmd-deck-band default (clear of buffer weights + the WEIGH QR). |
| `fcc.logPill.pos` | JSON `{left,bottom}` | px distances from the viewport's left / bottom edges | `fab_drag.js` (shared `draggable_pill.js` engine) — the draggable Activity-Log "N new" pill's parked position (2026-06-15, `#fcc-log-pill`). Written on drag-end; long-press resets to default. Loaded + viewport-clamped on page load; absent/invalid → a bottom-right default lifted above the cmd-deck band (diagonally opposite the FAB). Position is independent of the pill's JS-toggled show/hide (the separate `fcc.logPill.lastSeenTime` "unseen" gate). |

## Working Groups (Batched Tasks)

Tasks from `Feature-Buglist.md` are organized into batched working groups for efficient execution. Each group bundles related items that share code surfaces.

- **Index:** `docs/agent_docs/working-groups.md` — status table, recommended order, usage instructions.
- **Task files:** `docs/agent_docs/tasks/01-*.md` through `11-*.md` — self-contained specs per group.
- **Commands:** `/project:work-group <N>` to start a group, `/project:finish-group` to wrap up, `/project:refresh-groups` to re-analyze the buglist after adding new items.
