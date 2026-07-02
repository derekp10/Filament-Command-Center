# L316 — app.py Modularization Plan (the carve)

**Status:** IN PROGRESS 2026-07-01 on `feature/l316-app-modularization`.
**Precondition (DONE):** characterization layer committed (`32c59ac`) — `test_route_table_pin.py` (77 routes + `app.<name>` reachability) + 12 `test_l316_charact_*.py` files (282 tests, all host-runnable/offline). Baseline full sweep pinned: **21 failed / 1770 passed / 12 skipped** (`RUN_INTEGRATION=1`, 2026-07-01 — all 21 are the known Group-26 test-infra debt; exact list in the session scratchpad `baseline_sweep.txt`). Coverage audit + patch-target inventory + per-seam refactor notes saved in the session scratchpad (`audit_extract.json`, `refactor_notes.md`).

## Architecture

- **Shared-app registration, flat modules** (NOT blueprints, NOT a `routes/` subpackage):
  - `app_core.py` owns `app = Flask(...)` + the `add_header` after_request hook. Route modules do `from app_core import app` and keep their `@app.route(...)` decorators verbatim → endpoint names, URL map, and template/static resolution stay byte-identical.
  - Modules stay FLAT at `inventory-hub/` root: `tests/test_no_direct_extra_patch.py` scans `INV_HUB.glob('*.py')` NON-recursively — a subpackage would silently escape the sibling-wipe guard.
  - `app.py` remains the orchestrator + compatibility namespace: it imports every module (registration side effect), calls the startup functions at the same point in the import sequence as today, and re-exports moved symbols so `import app` / `app.<name>` keeps working.

## Test-compat rules (from the patch-target sweep — violating these silently rots tests)

1. **Module-qualified calls only** in moved code: `spoolman_api.update_spool(...)`, `locations_db.load_locations_list(...)`, `state.add_log_entry(...)`, `config_loader...`, `prusalink_api...`, `logic...`, bare `requests.get(...)` via `import requests`. NEVER `from spoolman_api import update_spool`. This keeps every `patch.object(app_module.spoolman_api, ...)` / `patch('app.submod.attr')` working (they mutate the shared module object).
2. **`spoolman_api.LAST_SPOOLMAN_ERROR` must stay an attribute read** (never from-imported) and stay adjacent to the failing call — order-sensitive error channel.
3. **App-namespace patches don't cross module boundaries.** `patch.object(app_module, '_helper')` only intercepts callers that resolve `_helper` from app.py's globals. When a symbol moves AND an internal caller moves with it, every test that patches it on `app` must be REPOINTED to the new module **in the same commit**. Re-exports in app.py cover direct calls and reads only.
4. **Mutable globals move with their subsystem** and tests repoint: `_PRINT_TRACKER`, `_PRINT_TRACKER_LOCK`, `_CANCEL_DEDUCT_RUN_ASYNC`, `_cancel_monitor_started`, `_CANCEL_FETCH_MAX_AGE_S` (monitor); `FIELD_ORDER`/`FIELD_ORDER_UNKNOWN` (inventory routes; re-export suffices — read-only from tests).
5. **`import app` must never spawn the daemon** — `_start_cancel_monitor` + creds seed stay under `__main__` in app.py.
6. Source-text canaries: `test_l271_phase3_printer_rows.py` greps app.py source for migration markers → repoint to `startup_migrations.py` when that block moves.

## Module map & commit order (one commit per step; after each: targeted suites + route-pin + charact set green, container boots, `git commit`)

| # | New module | Contents (current app.py lines) | Tests to repoint in the same commit |
|---|------------|--------------------------------|-------------------------------------|
| 1 | `app_core.py` | Flask instance + `add_header` (137, 397) | none (app.py re-imports `app`) |
| 2 | `startup_migrations.py` | the six locations.json migrations + backup prune, wrapped as `run_startup_migrations()`; cancel-review re-surface as `resurface_pending_cancel_reviews()` (196–390); called from app.py at the same import point | `test_l271_phase3_printer_rows.py` source canaries |
| 3 | `labels_csv.py` | label/text helpers (clean_string, hex_to_rgb, get_smart_type, get_color_name, get_best_hex, sanitize_label_text, flatten_json — 429–545) + `_write_label_csv` + `api_print_label`, `api_print_batch_csv` (546–555, 1365–1678) + `api_print_location_label` (3977–4092) | `test_label_csv_export.py`, `test_l316_charact_label_helpers.py`, `test_l316_charact_label_endpoints.py` |
| 4 | `routes_locations.py` | `api_get_locations` synthesizer, save/delete location, spool/filament delete, merge, undo, get_contents, spool/filament details (1679–2295) | `test_filament_merge.py` (`patch('app.requests.get')`), `test_l316_charact_record_deletes.py` |
| 5 | `routes_inventory.py` | vendor CRUD + edit-log formatter, read proxies, FIELD_ORDER cluster, wizard create/edit, `api_spool_update`, external search, `/api/search` (556–1364 minus labels/prusament) | `test_wizard_field_order.py` (re-export check), `test_l316_charact_wizard_error_paths.py` if it patches app-namespace |
| 6 | `routes_scan.py` | identify_scan, buffer/clear, manage_contents, update_filament + `_format_filament_edit_log`, Prusament cluster (`_pm_*`, `_compute_prusament_spool_weight_diff`, `_handle_prusament_url_scan`) + `api_prusament_apply_weights` (2296–3115 + 1230–1301) — the apply-weights endpoint forward-references `_pm_num`/`_PM_WEIGHT_TOL`, so it moves WITH the scan cluster | `test_prusament_scan.py` (direct call re-export ok; repoint if patching), `test_l316_charact_scan_audit.py`, `test_l316_charact_filament_edit_log.py` |
| 7 | `routes_bindings.py` | dryer-box bindings/slot_order, printer_state/map/creds, `_pm_prefix`, `_printer_map_blocked_removals`, quickswap + return, `api_machine_toolhead_slots`, `api_all_dryer_box_slots` (3116–3819) | `test_phase2_creds_gate.py` (`app.requests`), `test_l316_charact_bindings_errors.py` |
| 8 | `routes_print_queue.py` | pending, mark_printed, set_flag, flag_spool_labels (3820–3976) | `test_l316_charact_queue_flags.py` |
| 9 | `routes_config_attrs.py` | audit_session, config GET/PUT/export/import, filament_attributes manager (5400–6095) | `test_config_save.py` (function-level imports — verify), `test_l316_charact_filament_attributes_unit.py` |
| 10 | `print_deduct.py` | deduct engine incl. `_resolve_active_locs_for_printer` (483–528 moves here — its only callers + its app-namespace patchers are all deduct tests), `api_smart_move`, multi_spool/spools_by_filament/backfill endpoints, cancel_deduct routes (4093–5399) | `test_cancel_deduct.py`, `test_cancel_review.py`, `test_deduct_followups_22_4.py`, `test_spool_swap_22_3.py`, `test_spool_swap_22_3b.py`, `test_mmu_alias_dedup.py`, `test_l316_charact_deduct_misc.py` |
| 11 | `routes_state_pulse.py` + `print_monitor.py` | state/queue/logs/log_event + `_check_audit_idle_timeout` + pulse sections + dashboard_pulse (6096–6250, 7215–7384) ‖ `_PRINT_TRACKER` + edges + `_track_print_edge` + daemon + recovery + creds seed (6251–7214) — monitor imports print_deduct module-qualified; `_pulse_section_locations` imports routes_locations; `_pulse_section_logs` keeps its `api_get_logs_route()` call-through (audit-watchdog side effect is load-bearing) | `test_cancel_detection.py`, `test_cancel_recovery.py`, `test_completion_deduct.py`, `test_printer_status_box_bounding.py`, `test_dashboard_pulse_api.py` (if patching), `test_audit_auto_park_unknown.py`, `test_l316_charact_monitor_boot.py`, `test_l316_charact_pulse_state.py` |
| 12 | slim `app.py` | imports, build-version machinery + dashboard route, startup calls, module imports, re-export block, `__main__` | final audit: every route-pin `app.<name>` re-export present |
| 13 | docs | CLAUDE.md write-surface table gets new module:line homes + a module map; buglist note | — |

## Verification per step
- `pytest tests/test_route_table_pin.py tests/test_l316_charact_*.py <repointed suites> -q`
- Container boot: FCC_DEV=1 hot-reloads `.py` from the bind mount → `curl localhost:8000/` + one API GET.
- After steps 10–11 (the dangerous ones): full deduct-domain run (~233 tests).
- Final: full `RUN_INTEGRATION=1` sweep — must be **≤ the pinned 21 reds, zero new**.

## Known traps (from refactor_notes.md — read it before each step)
- `api_delete_location` relies on `logic.perform_toolhead_delete_cascade` MUTATING the passed list in place — don't copy.
- `api_filaments` deliberately returns raw double-encoded extras (wizard JS compensates) — preserve.
- Bare `except: pass` in `api_get_locations` Spoolman probe — preserve.
- `_format_version_from` reads module-global `BUILD_MTIME` (not pure) — build-version cluster stays together in app.py.
- `spoolman_api._is_delete_sentinel` + `logic._active_print_info_for_location` + `config_loader._canonicalize_printer_map` + `spoolman_api._parse_filament_attrs_value` — underscore-private cross-module deps; carry verbatim (formalizing is a follow-up).
- Vestigial `fb_url`/`filabridge_url` params — carry verbatim (separate buglist item).
- `import external_parsers` sits mid-file at app.py:1299 — lands in routes_inventory/scan; verify no order-dependent import-time work.
- Prod deploy: `update.sh` runs `setup_fields.py` then restarts — new modules ride the same `git reset`; `.dockerignore` excludes tests/ already; Dockerfile (`COPY . /app`, verified 2026-07-01) needs no change.
- **Container is Python 3.9** (`FROM python:3.9-slim`) — moved code is already 3.9-safe, but any NEW glue (app_core.py, wrapper functions) must avoid 3.10+ syntax (no `match`, no `X | Y` unions, no parenthesized context managers). Host tests run 3.14; the runtime does not.
