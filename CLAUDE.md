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
- **Legacy**: the old `config.json:feeder_map` key was retired in M7. A back-compat migration in `startup_migrations.py` (called from `app.py` at import) still runs on startup so any surviving install gets its entries imported into `slot_targets` automatically the first time it boots the new code.

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

## Backend module map (L316 modularization, 2026-07-01)

`app.py` (7,429 lines pre-carve) was split into flat modules at the `inventory-hub/` root. `app.py` (~370 lines) is now the orchestrator + compatibility namespace: build-version machinery + the `/` dashboard route, the startup-migration calls, one import per module (which registers its routes), a re-export block per module (so `app.<name>` keeps working for tests and cross-module callers), and the `__main__` launch block.

| Module | Owns |
|--------|------|
| `app_core.py` | The Flask `app` object + the Cache-Control after_request hook. Route modules do `from app_core import app`. |
| `startup_migrations.py` | The six idempotent locations.json migrations + backup prune + pending-cancel-review re-surface, called from app.py at import. |
| `labels_csv.py` | Label/text helpers (emoji map, hex/color/type resolution, flatten_json), `_write_label_csv`, and the three label endpoints. |
| `routes_locations.py` | `/api/locations` synthesizer, location save/delete, spool/filament delete, merge, undo, contents/details. |
| `routes_inventory.py` | Vendor CRUD, read proxies, FIELD_ORDER schema cluster, wizard create/edit, `/api/spool/update`, external + global search. |
| `routes_scan.py` | `api_identify_scan` dispatcher, buffer/clear, manage_contents, update_filament + edit-log formatter, the Prusament cluster + apply_weights. |
| `routes_bindings.py` | Dryer-box bindings/slot-order, printer state/map/creds, Quick-Swap, machine toolhead_slots. |
| `routes_print_queue.py` | Queue pending/mark_printed/set_flag + flag_spool_labels. |
| `routes_config_attrs.py` | L18 config GET/PUT/export/import + the L58 filament-attributes manager. |
| `print_deduct.py` | The FCC-native deduct engine (cancel/completion, review pipeline, cancel_deduct routes, smart_move, `_resolve_active_locs_for_printer`). |
| `print_monitor.py` | `_PRINT_TRACKER` latch, edge handlers, the cancel-monitor daemon, restart recovery, boot creds seed. Imports `print_deduct` (one-way). No routes. |
| `routes_state_pulse.py` | audit_session + audit-idle watchdog + `/api/logs`, persistence routes, pulse sections, `/api/dashboard_pulse`. |

Rules that keep the test suite's patch semantics intact (violating these silently rots tests — they stop intercepting without failing):

- **Module-qualified collaborator calls only** (`spoolman_api.update_spool(...)`, `state.add_log_entry(...)`); NEVER `from spoolman_api import update_spool` — tests patch attributes on the shared module objects.
- **`spoolman_api.LAST_SPOOLMAN_ERROR` is always an attribute read**, adjacent to the failing call.
- **Patch a private helper on its DEFINING module** (`patch.object(print_deduct, '_apply_usage_to_printer')`), not on `app` — app's re-exports serve reads/direct calls only; internal callers resolve names from their own module globals.
- **New backend modules stay FLAT at `inventory-hub/` root** — `tests/test_no_direct_extra_patch.py` scans `*.py` non-recursively, and the deploy/Dockerfile (`COPY . /app`) needs no change for flat files.
- **Nothing may start the cancel-monitor daemon at import** — the spawn + creds seed live under app.py's `__main__` only.
- **Source-text canaries** use `tests/source_family.py:read_app_family()` (app.py + all carve modules) — never grep app.py alone.
- The route table is pinned by `tests/test_route_table_pin.py` (all 77 routes + strict `app.<name>` identity). Adding/removing a route means updating the pin deliberately.
- Container runtime is **Python 3.9** — no 3.10+ syntax in backend modules.

## Spool / Filament write surfaces

Every code path that calls `spoolman_api.update_spool` or `update_filament` has the same two failure modes: (1) Spoolman replaces the whole `extra` dict on PATCH so partial payloads silently wipe siblings; (2) on rejection both functions return `None` and most callers don't surface the actual error body. Both are the root of the 2026-04-26 / 2026-04-27 prod outages.

Conventions every write surface MUST follow:

- **Use the helper, not inline diff loops.** `spoolman_api.compute_dirty_extras(existing, requested, system_managed=...)` returns `(dirty_dict, stripped_keys)`. Pass `system_managed=spoolman_api.SYSTEM_MANAGED_EXTRAS` whenever the surface is user-driven editing (wizard, vendor edit modal, manufacturer edit modal, etc.) — that frozenset enumerates the keys owned exclusively by `perform_smart_move` / `perform_smart_eject` (`container_slot`, `physical_source`, `physical_source_slot`).
- **Surface `LAST_SPOOLMAN_ERROR` on failure.** Both `update_spool` and `update_filament` populate the module-global on every rejection (the symmetry was fixed 2026-04-27 — pre-fix, only `update_filament` did). Read it in your `else:` branch and either (a) write to the activity log via `state.add_log_entry(..., "ERROR", "ff4444")`, or (b) return it in the JSON response so the frontend can `showToast(err, "error", 7000)`.
- **For high-stakes paths use `_or_raise`.** `update_spool_or_raise` and `update_filament_or_raise` raise `spoolman_api.SpoolmanRejection` instead of returning `None`. Use these on slot assignment, label-confirm scans, force-move, and weigh-out — paths where silent failure left the user with no signal.
- **Don't add `force_reset=True` to `setup_fields.py` lightly.** A field-schema delete wipes that extra on every record. The existing `migrate_container_slot_to_text()` is the template for any future legitimate type migration: snapshot values, force_reset, restore. Steady-state setup_fields runs MUST be value-preserving.
- **To DELETE an extra, send the delete-sentinel — don't omit the key (Group 23.4).** Because the read-merge starts from the full existing extras and only overlays keys the caller SENT, an OMITTED key means "keep" (the sibling-wipe guard). A blanked field can therefore never be cleared by omission. A surface that wants to clear an extra sends `spoolman_api.DELETE_EXTRA_SENTINEL` (frontend: `window.FCC_DELETE_EXTRA`, defined in `inv_core.js`) as that key's value; `_merge_extras_with_existing` pops it (it is NEVER forwarded to Spoolman or stored literally), and `_is_delete_sentinel` matches the quote-stripped form so it survives `sanitize_outbound_data` wrapping. The merge refuses to pop a `SYSTEM_MANAGED_EXTRAS` key even if sent the sentinel (slot-binding backstop), and `compute_dirty_extras` suppresses a sentinel for an absent/blank key (no spurious PATCH). Edit surfaces should only emit the sentinel in EDIT mode (on CREATE a blank is just omitted). Edit-log formatters render it as `→ (cleared)`. Pin behavior with `tests/test_delete_sentinel.py`.

Inventory of current production write surfaces (keep this list updated when adding new ones):

| Module (post-L316) | Endpoint / Function | Notes |
|--------------------|--------------------|-------|
| `routes_inventory.py` | `api_edit_spool_wizard` spool save | Uses `compute_dirty_extras` with SYSTEM_MANAGED_EXTRAS guard. |
| `routes_inventory.py` | `api_edit_spool_wizard` filament save | Surfaces `LAST_SPOOLMAN_ERROR` in response JSON. |
| `routes_locations.py` | `/api/locations` cascade unassign | Best-effort fire-and-forget; logs each failure. |
| `routes_inventory.py` | `/api/spool/update` generic partial update | `update_spool` (read-merge-write extras + `used_weight ≤ initial_weight` cap + auto-archive/unarchive on remaining); surfaces `LAST_SPOOLMAN_ERROR` in the `error`/`msg` response fields. ⚠️ Sending `initial_weight` here runs `_auto_archive_on_empty`/`_auto_unarchive_on_refill` — a too-low total can silently archive+unassign a loaded spool. The L200 path deliberately does NOT use this; see the dedicated endpoint below. |
| `routes_scan.py` | `/api/spool/prusament_apply_weights` (L200) | Confirm-apply for the Prusament-scan spool-weight correction. RE-VALIDATES against the live spool (refuses if archived, or if the new total would leave remaining ≤ ~0 and trip auto-archive), writes only `initial_weight`/`spool_weight` via `update_spool_or_raise` (used_weight preserved). Returns `status: success`/`blocked`/`error`. Hardened per the 2026-06-05 adversarial review. |
| `routes_scan.py` | `/api/update_filament` quick-edit | Reference impl — surfaces error in response JSON. |
| `routes_scan.py` | spool label-confirm scan (in `api_identify_scan`) | Logs ERROR with Spoolman body; emits "already verified" info path. |
| `routes_scan.py` | filament label-confirm scan (in `api_identify_scan`) | Same pattern as spool side. |
| `routes_print_queue.py` | `/api/print_queue/mark_printed` (spool) | Returns Spoolman error in response. |
| `routes_print_queue.py` | `/api/print_queue/mark_printed` (filament) | Returns Spoolman error in response. |
| `routes_print_queue.py` | `/api/print_queue/set_flag` (spool) | Returns Spoolman error in response. |
| `routes_print_queue.py` | `/api/print_queue/set_flag` (filament) | Returns Spoolman error in response. |
| `routes_print_queue.py` | `/api/filament/<id>/flag_spool_labels` (Group 23.3) | Light label-invalidation: raises `needs_label_print` on a filament's UNARCHIVED spools when a spool-label-visible filament field (Brand/Type/Color-name, NOT hex) changed. Partial extra via `update_spool` (siblings preserved, no archive side-effect — no weight fields); per-spool best-effort + `errors[]` in response. |
| `print_deduct.py` | `/api/backfill_spool_weights` | Per-spool `errors` list in response. |
| `print_deduct.py` | print deduct — `_apply_usage_to_printer` | **FCC-native print-usage deduct** (replaced the FilaBridge auto-deduct in the 2026-06-13 Phase-2 cutover). Writes `used_weight` via `update_spool` per toolhead; the shared primitive for BOTH the cancelled-print partial deduct (`deduct_cancelled_print` — decode `.bgcode` + per-tool prefix-parse to the cancel/M73 point) AND the FINISHED completion deduct. Exactly-once via `print_deduct_ledger`; activity-log on failure. |
| `print_deduct.py` | cancel/ambiguous-review confirm-apply (`api_cancel_deduct_confirm`) | User-confirmed deduct: re-reads CURRENT `used_weight` (so a weigh-out between preview and confirm isn't clobbered), clamps grams to real remaining, writes `used_weight` via `update_spool`; activity-log on success/failure. |
| `routes_inventory.py` | `PATCH /api/vendors/<id>` Vendor Edit modal save | Uses `update_vendor_or_raise`; merges `extra` against existing record so partial PATCH preserves siblings; activity log on both success and rejection; surfaces Spoolman error body in response JSON for the modal to toast at 7s. |
| `logic.py:524` | `perform_smart_move` unseat existing | Read-merge-write reference impl; logs failure. |
| `logic.py:575` | `perform_smart_move` toolhead branch | Activity log on failure with Spoolman body. |
| `logic.py:603` | `perform_smart_move` dryer branch | Activity log on failure. |
| `logic.py:628` | `perform_smart_move` generic branch | Activity log on failure. |
| `logic.py:827` | `perform_smart_eject` return-home | Activity log on failure. |
| `logic.py:853` | `perform_smart_eject` relocate | Activity log on failure. |
| `logic.py:1007` | `perform_force_unassign` | Activity log on failure. |
| `inv_details.js:promptEditSlicerProfile` | Pencil overlay on filament details modal | Client-side merges current `extra` from `/api/filaments/<id>` before POST to `/api/update_filament` so siblings (`nozzle_temp_max`, `sheet_link`, `filament_attributes`, etc.) are preserved. Surfaces error in Swal. Fires `add_choice` POST after successful save when user typed a brand-new profile name. |

### Weight-entry surfaces (known fragmentation hot-spot)

Within the table above, the weight-touching entries are themselves a fragmented sub-system: `routes_print_queue.py` (mark_printed), `print_deduct.py` (backfill + the FCC-native print deduct `_apply_usage_to_printer` + cancel-review confirm — replaced the retired FilaBridge deduct paths), plus the frontend modals (`inv_weigh_out.js` weigh-out, `inv_wizard.js` empty-weight fields, `inv_details.js` post-archive prompt + filament edit). Each accepts a slightly different input form (gross / net / additive / delta / field-only) with inconsistent terminology and inconsistent empty-spool-weight resolution.

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
