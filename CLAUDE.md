Architecture & Environment:
Dev: Runs in a local Docker instance. Always provide terminal and execution commands in a Docker context (e.g., docker exec, docker-compose).
Front end for dev can be found here: http://localhost:8000/
Spoolman for dev can be found here: http://192.168.1.29:7913/
Filabridge for dev can be found here: http://192.168.1.29:5001/
Prod: Hosted on a TrueNAS server. Keep deployment, storage, and networking suggestions strictly compatible with TrueNAS architecture.

## Testing

- **pytest + Playwright run on the host**, not inside the Docker image. Install once: `pip install -r requirements-dev.txt && playwright install chromium`. All E2E tests then hit `http://localhost:8000` of the running container.
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

- **No nested `Swal.fire()`** — use inline overlay divs following the `#fcc-escape-confirm-overlay` / `#fcc-quickswap-confirm-overlay` pattern. Nested Swals don't stack and dismiss each other.
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
| `app.py:408` | `api_create_inventory_wizard` auto-unarchive | Logs `LAST_SPOOLMAN_ERROR` on failure; warning level (best-effort). |
| `app.py:507` | `api_edit_spool_wizard` spool save | Uses `compute_dirty_extras` with SYSTEM_MANAGED_EXTRAS guard. |
| `app.py:521` | `api_edit_spool_wizard` filament save | Surfaces `LAST_SPOOLMAN_ERROR` in response JSON. |
| `app.py:555` | `/api/manage_contents` set_meta | Returns `error` field with Spoolman body. |
| `app.py:1079` | `/api/locations` cascade unassign | Best-effort fire-and-forget; logs each failure. |
| `app.py:1183` | `/api/update_filament` quick-edit | Reference impl — surfaces error in response JSON. |
| `app.py:1331` | spool label-confirm scan | Logs ERROR with Spoolman body; emits "already verified" info path. |
| `app.py:1388` | filament label-confirm scan | Same pattern as spool side. |
| `app.py:2068` | `/api/print_queue/mark_printed` (spool) | Returns Spoolman error in response. |
| `app.py:2079` | `/api/print_queue/mark_printed` (filament) | Returns Spoolman error in response. |
| `app.py:2103` | `/api/print_queue/set_flag` (spool) | Returns Spoolman error in response. |
| `app.py:2113` | `/api/print_queue/set_flag` (filament) | Returns Spoolman error in response. |
| `app.py:2359` | `/api/backfill_spool_weights` | Per-spool `errors` list in response. |
| `app.py:2496` | filabridge auto-deduct | Activity log on failure with Spoolman body. |
| `app.py:2533` | filabridge manual recovery | Same pattern as auto-deduct. |
| `app.py:2659` | filabridge auto-recover task (threaded) | Activity log on failure. |
| `logic.py:432` | `perform_smart_move` unseat existing | Read-merge-write reference impl; logs failure. |
| `logic.py:484` | `perform_smart_move` toolhead branch | Activity log on failure with Spoolman body. |
| `logic.py:498` | `perform_smart_move` dryer branch | Activity log on failure. |
| `logic.py:509` | `perform_smart_move` generic branch | Activity log on failure. |
| `logic.py:692` | `perform_smart_eject` return-home | Activity log on failure. |
| `logic.py:714` | `perform_smart_eject` relocate | Activity log on failure. |
| `logic.py:754` | `perform_force_unassign` | Activity log on failure. |

## Working Groups (Batched Tasks)

Tasks from `Feature-Buglist.md` are organized into batched working groups for efficient execution. Each group bundles related items that share code surfaces.

- **Index:** `docs/agent_docs/working-groups.md` — status table, recommended order, usage instructions.
- **Task files:** `docs/agent_docs/tasks/01-*.md` through `11-*.md` — self-contained specs per group.
- **Commands:** `/project:work-group <N>` to start a group, `/project:finish-group` to wrap up, `/project:refresh-groups` to re-analyze the buglist after adding new items.
