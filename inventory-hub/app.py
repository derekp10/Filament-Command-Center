from flask import request, jsonify, render_template # type: ignore
import requests # type: ignore
import state # type: ignore
import config_loader # type: ignore
import config_schema # type: ignore
import locations_db # type: ignore
import spoolman_api # type: ignore
import print_deduct_ledger # type: ignore
import cancel_review_store # type: ignore
import cancel_fetch_store # type: ignore
import print_tracker_store # type: ignore
import prusalink_api # type: ignore
import logic # type: ignore
# L316 step 5: the mid-file plugin import moved into routes_inventory.py with
# /api/external/search; kept HERE too because the Prusament scan cluster
# (moves in step 6) calls it and tests patch it via app.external_parsers.
import external_parsers # type: ignore
import csv
import os
import tempfile
import json
import logging
import time
import threading

def _compute_build_mtime():
    """L42 fix: derive a freshness-stamp from the newest source-file mtime.

    The manually-bumped VERSION constant was stale by ~25 commits when this
    was wired up. Walk the live code dirs (app's own dir + static + templates)
    and use the most recent mtime so the badge always reflects the actual
    build the user is looking at — no manual bump step to forget.

    Returns a UNIX timestamp (float). The frontend converts it to the user's
    local timezone so the badge isn't confusing when the container runs UTC
    and the user is in PDT.
    """
    here = os.path.dirname(os.path.abspath(__file__))
    newest = 0
    for sub in ('', 'static', 'templates'):
        root = os.path.join(here, sub) if sub else here
        if not os.path.isdir(root):
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            # Skip caches / generated artifacts.
            dirnames[:] = [d for d in dirnames if d not in ('__pycache__', '.git', 'data', '__screenshots__')]
            for name in filenames:
                if name.endswith(('.pyc', '.pyo', '.log', '.bak')):
                    continue
                # Skip self-rewriting artifacts so the build-info refresh
                # doesn't pump the mtime forward and falsely trigger "+local".
                if name in ('.build_info',):
                    continue
                try:
                    mt = os.path.getmtime(os.path.join(dirpath, name))
                    if mt > newest:
                        newest = mt
                except OSError:
                    continue
    return newest


def _load_build_commit():
    """L42 round 2: opportunistically resolve the current git commit so the
    dashboard badge shows the actual version running.

    Strategy:
      1. If .git is reachable from this file (host or .git-bind-mounted
         container), regenerate `inventory-hub/.build_info` so it's always
         fresh. Done via the standalone `_gen_build_info` helper so the
         same code path is usable from a git post-commit hook or a CI step.
      2. Read `.build_info` if present. Either way (we just wrote it, or
         it was baked into the prod image), parse SHA + optional unix ts.
      3. Return (sha, ts) or (None, None) — caller falls back to mtime.

    No git binary required; the helper parses .git/HEAD + logs/HEAD
    directly. Failures are silent — version-badge freshness shouldn't
    crash the server.
    """
    here = os.path.dirname(os.path.abspath(__file__))
    info_path = os.path.join(here, '.build_info')
    try:
        import _gen_build_info  # type: ignore
        _gen_build_info.write_build_info(info_path)
    except Exception:
        # Helper missing or .git unreachable — fine, fall through to
        # whatever (if anything) was previously baked in.
        pass
    if not os.path.isfile(info_path):
        return None, None
    try:
        with open(info_path, 'r', encoding='utf-8') as f:
            line = f.read().strip()
    except OSError:
        return None, None
    if not line:
        return None, None
    parts = line.split('|', 1)
    sha = parts[0].strip() or None
    ts = None
    if len(parts) > 1:
        try:
            ts = int(parts[1].strip())
        except (ValueError, TypeError):
            ts = None
    return sha, ts


BUILD_MTIME = _compute_build_mtime()
BUILD_COMMIT_SHA, BUILD_COMMIT_TS = _load_build_commit()


def _format_version():
    """Compose the dashboard badge string. Prefer commit info when we have
    it; fall back to the mtime stamp.

    Note: a `+local` suffix for uncommitted edits was considered but
    dropped — prod pulls reset file mtimes to the pull time, which
    would false-trigger on every deploy. Users who want to see dirty
    state can `git status` directly.
    """
    return _format_version_from(BUILD_COMMIT_SHA, BUILD_COMMIT_TS)


def _format_version_from(sha, ts):
    """Pure formatter so the dashboard route can re-render the badge
    using a freshly-read sha/ts pair without relying on the module-
    global BUILD_COMMIT_SHA/TS (which are frozen at startup)."""
    import time as _time
    if sha:
        label = f"commit {sha}"
        if ts:
            label += " • " + _time.strftime('%Y-%m-%d %H:%M UTC', _time.gmtime(ts))
        return label
    if BUILD_MTIME:
        return "build " + _time.strftime('%Y-%m-%d %H:%M UTC', _time.gmtime(BUILD_MTIME))
    return "build ?"


VERSION = _format_version()
# L316 step 1: the Flask instance + the Cache-Control after_request hook live
# in app_core.py so extracted route modules can register on the same object
# without importing this module. Re-imported here so `from app import app` /
# `app_module.app` keep working everywhere.
from app_core import app, add_header  # noqa: E402

# L316 step 2: the six locations.json startup migrations + backup pruning and
# the pending-cancel-review re-surface live in startup_migrations.py. They run
# HERE, at the same import point as pre-carve (before any route can serve),
# preserving the load->migrate->backup->prune->save ordering. The prune helper
# + cap are re-exported: tests call app._prune_locations_backups directly and
# the credentials seed below still calls it through this module's namespace.
import startup_migrations  # noqa: E402
from startup_migrations import MAX_LOCATIONS_BACKUPS, _prune_locations_backups  # noqa: E402
startup_migrations.run_startup_migrations()
startup_migrations.resurface_pending_cancel_reviews()

# [ALEX FIX] Suppress Werkzeug Console Spam (Fixes Infinite Log Growth)
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

@app.route('/')
def dashboard():
    # Load config to generate the correct Spoolman URL
    cfg = config_loader.load_config()
    ip = cfg.get('server_ip', '127.0.0.1')
    if ip == '0.0.0.0': ip = '127.0.0.1'
    port = cfg.get('spoolman_port', 7912)
    sm_url = f"http://{ip}:{port}"
    buy_more_url_template = cfg.get('buy_more_url_template', '')
    
    # Re-read .build_info on every dashboard render so a post-commit hook
    # update (host-side) takes effect without needing a container restart.
    # `_load_build_commit()` is cheap — at most one tiny file read and a
    # quick parse. The mtime walk stays at startup (more expensive, doesn't
    # need to be live). Recomposes VERSION too so the startup-log line and
    # the rendered badge can drift apart safely.
    live_sha, live_ts = _load_build_commit()
    live_version = _format_version_from(live_sha, live_ts) if (live_sha or BUILD_MTIME) else VERSION
    return render_template(
        'dashboard.html',
        version=live_version,
        build_mtime=BUILD_MTIME,
        build_commit_sha=live_sha or '',
        build_commit_ts=live_ts or 0,
        spoolman_url=sm_url,
        buy_more_template=buy_more_url_template,
    )

# --- HELPER FUNCTIONS ---
# L316 step 3: label/text helpers + the three label endpoints live in
# labels_csv.py (imported here both to register its routes on the shared app
# object and to re-export every moved symbol for app.<name> compatibility).
from labels_csv import (  # noqa: E402,F401
    clean_string, hex_to_rgb, get_smart_type, get_color_name, get_best_hex,
    sanitize_label_text, flatten_json, _write_label_csv,
    api_print_label, api_print_batch_csv, api_print_location_label,
)

# (_resolve_active_locs_for_printer moved to print_deduct.py — L316 step 10)


# (flatten_json + /api/print_label moved to labels_csv.py — L316 step 3)

# L316 step 5: the wizard/vendor/CRUD/search inventory routes live in
# routes_inventory.py (imported to register on the shared app + re-export for
# app.<name> compatibility; FIELD_ORDER/_enrich_field_order are read by
# tests/test_wizard_field_order.py through this namespace).
# NOTE: api_prusament_apply_weights deliberately remains below — it shares the
# _pm_* numeric helpers with the Prusament scan cluster and moves with it
# (step 6, routes_scan.py).
from routes_inventory import (  # noqa: E402,F401
    api_external_vendors, api_vendors, api_create_filament, api_create_vendor,
    _format_vendor_edit_log, api_update_vendor, api_materials, api_filaments,
    api_get_filament, api_get_spool, FIELD_ORDER, FIELD_ORDER_UNKNOWN,
    _enrich_field_order, api_external_fields, api_spoolman_restore_field_order,
    api_external_fields_add_choice, api_create_inventory_wizard,
    _log_manual_weight_change, api_edit_spool_wizard, api_spool_update,
    api_external_search, api_search_inventory,
)

# L316 step 6: the scan pipeline (identify_scan dispatcher, buffer/clear,
# manage_contents, update_filament + edit-log formatter) and the Prusament
# cluster (incl. api_prusament_apply_weights) live in routes_scan.py.
from routes_scan import (  # noqa: E402,F401
    api_prusament_apply_weights, _format_filament_edit_log, api_update_filament,
    api_manage_contents, _pm_norm, _PM_TEMP_LABELS, _PM_WEIGHT_TOL, _pm_num,
    _pm_first_pos, _compute_prusament_spool_weight_diff,
    _handle_prusament_url_scan, api_identify_scan, api_buffer_clear,
)

# (external-parser search + /api/search moved to routes_inventory.py — L316 step 5)
# (_write_label_csv + /api/print_batch_csv moved to labels_csv.py — L316 step 3)

# L316 step 4: the locations + record-lifecycle routes live in
# routes_locations.py (imported to register on the shared app + re-export
# for app.<name> compatibility; _pulse_section_locations also calls
# api_get_locations through this namespace).
from routes_locations import (  # noqa: E402,F401
    api_get_locations, api_save_location, api_delete_location,
    api_delete_spool, api_delete_filament, api_merge_filament,
    api_undo, api_get_contents_route, api_spool_details, api_filament_details,
)

# (scan pipeline + update_filament + manage_contents moved to routes_scan.py — L316 step 6)

# L316 step 7: dryer-box bindings, printer map/creds/state, and Quick-Swap
# live in routes_bindings.py.
from routes_bindings import (  # noqa: E402,F401
    api_dryer_box_bindings_get, api_dryer_box_slot_order_get,
    api_dryer_box_slot_order_put, api_dryer_box_bindings_put,
    api_printer_state, api_printer_map, api_put_printer_creds,
    _pm_prefix, _printer_map_blocked_removals, api_put_printer_map,
    api_all_dryer_box_slots, api_single_slot_binding_put,
    api_quickswap_return, api_quickswap, api_machine_toolhead_slots,
)

# L316 step 8: print-queue + label-flag routes live in routes_print_queue.py.
from routes_print_queue import (  # noqa: E402,F401
    api_print_queue_pending, api_print_queue_mark_printed,
    api_print_queue_set_flag, api_flag_spool_labels,
)
# (/api/print_location_label moved to labels_csv.py — L316 step 3)

# L316 step 10: the FCC-native deduct engine (cancel/completion deducts,
# review pipeline, smart_move + the adjacent spool read endpoints, and
# _resolve_active_locs_for_printer) lives in print_deduct.py. Deduct tests
# patch symbols on print_deduct directly; these re-exports keep direct
# calls, reads, and the strict route-pin identity working via app.<name>.
from print_deduct import (  # noqa: E402,F401
    _resolve_active_locs_for_printer, api_get_multi_spool_filaments,
    api_get_spools_by_filament, api_backfill_spool_weights, api_smart_move,
    _apply_usage_to_printer, _record_applied_deduct, _snapshot_active_spools,
    _validated_start_spools, _validated_swap_log, _is_sid_swap,
    _record_swap_events, _log_cancel_uncomputable, _compute_cancel_usage,
    deduct_cancelled_print, deduct_completed_print, _route_completion_to_review,
    _resolve_usage_to_spools, _stash_unresolved_review, _enqueue_cancel_fetch,
    _create_pending_cancel_review, api_cancel_deduct_pending,
    _confirm_no_spool_review, api_cancel_deduct_confirm, api_cancel_deduct_dismiss,
)


# L316 step 9: the config-system endpoints + the filament-attributes manager
# live in routes_config_attrs.py.
from routes_config_attrs import (  # noqa: E402,F401
    api_get_config, api_put_config, api_config_export, api_config_import,
    api_filament_attributes_report, api_filament_attributes_bulk_set,
    api_filament_attributes_add_choice, api_filament_attributes_remove_choice,
    api_filament_attributes_sweep_unused,
)

# L316 step 11: audit_session + the state/persistence routes + the audit
# watchdog + /api/logs + the dashboard pulse live in routes_state_pulse.py.
from routes_state_pulse import (  # noqa: E402,F401
    api_audit_session, api_state_buffer, api_state_queue, api_spools_refresh,
    api_log_event, _check_audit_idle_timeout, api_get_logs_route,
    _VALID_PULSE_SECTIONS, _pulse_section_logs, _pulse_section_locations,
    _pulse_section_manage, _pulse_section_printer_status, api_dashboard_pulse,
)
# L316 step 11: the print-edge tracker + cancel-monitor daemon live in
# print_monitor.py. Monitor tests patch/assign these symbols on
# print_monitor directly; the re-exports keep reads + direct calls working.
# _PRINT_TRACKER / _PRINT_TRACKER_LOCK are THE SAME objects (in-place
# mutation through either namespace is shared); the daemon spawn stays
# under __main__ below — importing this family never starts it.
import print_monitor  # noqa: E402
from print_monitor import (  # noqa: E402,F401
    _PRINT_TRACKER, _PRINT_TRACKER_LOCK, _INPROGRESS_PRINT_STATES,
    _PAUSED_CONDITION_STATES, _CANCEL_TERMINAL_STATES,
    _COMPLETE_TERMINAL_STATES, _IDLE_READY_STATES, _CANCEL_DEDUCT_RUN_ASYNC,
    _fcc_owns_completion_deduct, _on_cancel_edge, _dispatch_cancel_edge,
    _on_completion_edge, _dispatch_completion_edge, _on_ambiguous_edge,
    _dispatch_ambiguous_edge, _track_print_edge, _CANCEL_MONITOR_FAST_S,
    _CANCEL_MONITOR_IDLE_S, _CANCEL_FETCH_MAX_AGE_S, _cancel_monitor_started,
    _cancel_monitor_lock, _cancel_monitor_tick, _process_pending_cancel_fetches,
    _recover_print_tracker_on_start, _recover_one_print_latch,
    _cancel_monitor_loop, _seed_printer_credentials_from_filabridge,
    _start_cancel_monitor,
)
# (_pulse_section_printer_status + /api/dashboard_pulse live in routes_state_pulse.py — L316 step 11)


if __name__ == '__main__':
    state.logger.info(f"🛠️ Server {VERSION} Started")
    # Register required Spoolman extras (max-temps etc.) so saves from the
    # Edit Filament modal don't hit "Unknown extra field" errors on prod
    # instances that haven't run setup_fields.py since the new fields
    # were added. Idempotent — skips fields that already exist.
    try:
        spoolman_api.ensure_required_extras()
    except Exception as _e:
        state.logger.warning(f"ensure_required_extras failed at startup: {_e}")
    # Derek 2026-05-19: auto-clean the filament_attributes dropdown so we
    # never have to find + run the standalone migration script manually.
    # Idempotent — first boot does the cleanup; subsequent boots are a
    # cheap field-definition GET + early-return. Failures log and move
    # on, never block startup.
    try:
        spoolman_api.ensure_filament_attributes_cleaned()
    except Exception as _e:
        state.logger.warning(f"ensure_filament_attributes_cleaned failed at startup: {_e}")
    # L293 — opt-in dev-mode auto-reload. Set `FCC_DEV=1` (or `true`) in
    # the dev environment to have werkzeug watch files and restart the
    # server on edits. Defaults to off so the TrueNAS prod image keeps
    # its current behavior (one long-lived process, no reload churn).
    _dev = str(os.environ.get('FCC_DEV', '')).strip().lower() in ('1', 'true', 'yes', 'on')
    # ALSO opt into Jinja2 template auto-reload in dev — without this,
    # `use_reloader=True` only re-execs the Python process on .py edits;
    # template (.html) edits stay cached by Jinja2 for the lifetime of the
    # process and a server restart is required to see them. With debug=False
    # (which we keep so the interactive debugger never ships to prod) Flask
    # otherwise defaults to "don't auto-reload templates," which is the
    # production-safe default. 2026-05-28 — Derek caught L21's sort dropdown
    # not appearing in /search because the container had cached the pre-L21
    # template through a 3-day uptime; this prevents that footgun.
    if _dev:
        app.config['TEMPLATES_AUTO_RELOAD'] = True
    # Start the dashboard-independent cancelled-print monitor in the SERVING
    # process only: with the dev reloader that's the child (WERKZEUG_RUN_MAIN);
    # without it (prod) this single process. The reloader PARENT skips it so dev
    # doesn't run two pollers.
    if (not _dev) or os.environ.get('WERKZEUG_RUN_MAIN', '').lower() == 'true':
        # FilaBridge Phase-2 gate: relocate printer creds onto the Printer rows
        # (one-time, prime-only) BEFORE the cancel monitor starts, so its first
        # PrusaLink probe reads creds locally rather than from FilaBridge.
        print_monitor._seed_printer_credentials_from_filabridge()
        print_monitor._start_cancel_monitor()
    app.run(host='0.0.0.0', port=8000, use_reloader=_dev, debug=False)