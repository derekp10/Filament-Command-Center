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

