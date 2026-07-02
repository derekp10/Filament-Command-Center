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

def _resolve_active_locs_for_printer(printer_map, printer_name, filabridge_url):
    """Return [(loc_id, p_info)] for `printer_name`, ordered so the
    physically-active location for each position comes first.

    Background: printer_map can have two entries sharing the same position
    — e.g. CORE1-M0 (direct feed) and CORE1-M1 (MMU-routed). Only one is
    active per print. We query PrusaLink /api/v1/info.mmu to decide:
      - mmu=True  → M1-suffix aliases are preferred (MMU routed)
      - mmu=False → M0-suffix aliases are preferred (direct feed)
      - unknown   → printer_map insertion order is used (fallback)

    Downstream code iterates this ordering and deducts from the first
    location per position that actually has a spool assigned.
    """
    import prusalink_api  # local import keeps this helper usable at import time
    candidates = [
        (loc_id, p_info) for loc_id, p_info in printer_map.items()
        if p_info.get('printer_name') == printer_name
    ]
    if not candidates:
        return []

    positions_seen = {}
    for _, p_info in candidates:
        positions_seen[p_info.get('position', 0)] = positions_seen.get(p_info.get('position', 0), 0) + 1
    if not any(count > 1 for count in positions_seen.values()):
        return candidates  # no aliases — nothing to re-order

    mmu = None
    try:
        mmu = prusalink_api.get_printer_mmu_flag(filabridge_url, printer_name)
    except Exception:
        mmu = None
    if mmu is None:
        return candidates  # can't tell which is active — keep insertion order

    def _sort_key(item):
        loc_id = str(item[0]).upper()
        # Preferred alias sorts first (0), non-preferred second (1).
        if mmu:
            return (0 if loc_id.endswith('-M1') else 1, loc_id)
        return (0 if loc_id.endswith('-M0') else 1, loc_id)

    return sorted(candidates, key=_sort_key)


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

# --- REPLACED: Multi-Spool Logic instead of Multi-Color ---
@app.route('/api/get_multi_spool_filaments', methods=['GET'])
def api_get_multi_spool_filaments():
    sm_url, _ = config_loader.get_api_urls()
    try:
        # 1. Get ALL active spools
        resp = requests.get(f"{sm_url}/api/v1/spool", timeout=10)
        if not resp.ok: return jsonify([])
        all_spools = resp.json()
        
        # 2. Group by Filament ID
        fil_counts = {}
        fil_spools = {}
        fil_names = {}
        fil_vendors = {}
        
        if isinstance(all_spools, list):
            for s in all_spools:
                if not isinstance(s, dict) or s.get('archived'): continue # Skip archived
                fid = s.get('filament', {}).get('id')
                if not fid: continue
                
                if fid not in fil_counts: 
                    fil_counts[fid] = 0
                    fil_spools[fid] = []
                    fil_names[fid] = s.get('filament', {}).get('name', '')
                    fil_vendors[fid] = s.get('filament', {}).get('vendor', {}).get('name', '')
                    
                fil_counts[fid] += 1
                fil_spools[fid].append(s['id'])
            
        # 3. Filter for > 1
        candidates = []
        for fid, count in fil_counts.items():
            if count > 1:
                display_name = f"{fil_vendors.get(fid, '')} - {fil_names.get(fid, '')}".strip(" -")
                candidates.append({
                    "id": fid,
                    "display": display_name,
                    "count": count,
                    "spool_ids": fil_spools.get(fid, [])
                })
        
        return jsonify(candidates)
    except Exception as e:
        state.logger.error(f"Multi-Spool Error: {e}")
        return jsonify([])

# --- NEW ROUTE: Fetch Active Spools for a specific Filament ---
@app.route('/api/spools_by_filament', methods=['GET'])
def api_get_spools_by_filament():
    fid = request.args.get('id')
    if not fid: return jsonify([])
    
    allow_archived = request.args.get('allow_archived', 'false').lower() == 'true'
    
    sm_url, _ = config_loader.get_api_urls()
    try:
        # Get spools filtered by filament_id
        # We ask Spoolman directly: "Give me all spools for Filament ID X"
        sm_req_url = f"{sm_url}/api/v1/spool?filament_id={fid}"
        if allow_archived:
            sm_req_url += "&allow_archived=true"
        resp = requests.get(sm_req_url, timeout=5)
        if resp.ok:
            if allow_archived:
                spools = resp.json()
            else:
                spools = [s for s in resp.json() if not s.get('archived')]
            return jsonify(spools)
        return jsonify([])
    except:
        return jsonify([])


@app.route('/api/backfill_spool_weights/<int:fid>', methods=['POST'])
def api_backfill_spool_weights(fid):
    """Backfill spool_weight on historical spools that saved as 0 before the
    inheritance chain landed. Resolves the inheritable empty-spool weight from
    the filament (then its vendor), then PATCHes every spool under this
    filament whose own spool_weight is null or <= 0. Archived spools are
    included so old empty-weight references stay accurate.
    """
    try:
        fil = spoolman_api.get_filament(fid)
        if not fil:
            return jsonify({"success": False, "msg": f"Filament #{fid} not found."}), 404

        def _positive(v):
            try: return v is not None and float(v) > 0
            except (TypeError, ValueError): return False

        fil_wt = fil.get('spool_weight')
        vendor_wt = (fil.get('vendor') or {}).get('empty_spool_weight')

        if _positive(fil_wt):
            target = float(fil_wt); source = 'filament'
        elif _positive(vendor_wt):
            target = float(vendor_wt); source = 'vendor'
        else:
            return jsonify({
                "success": False,
                "msg": "No inheritable empty-spool weight on this filament or its vendor — set one on the filament or the vendor first."
            }), 400

        sm_url, _ = config_loader.get_api_urls()
        resp = requests.get(f"{sm_url}/api/v1/spool?filament_id={fid}&allow_archived=true", timeout=5)
        if not resp.ok:
            return jsonify({"success": False, "msg": "Failed to fetch spools from Spoolman."}), 502
        spools = resp.json() or []

        updated_ids = []
        skipped = 0
        errors = []
        for sp in spools:
            sid = sp.get('id')
            sp_wt = sp.get('spool_weight')
            if _positive(sp_wt):
                skipped += 1
                continue
            res = spoolman_api.update_spool(sid, {'spool_weight': target})
            if res:
                updated_ids.append(sid)
            else:
                errors.append(sid)

        return jsonify({
            "success": True,
            "filament_id": fid,
            "target_weight": target,
            "source": source,
            "updated": len(updated_ids),
            "updated_ids": updated_ids,
            "skipped": skipped,
            "errors": errors,
        })
    except Exception as e:
        state.logger.error(f"api_backfill_spool_weights({fid}) failed: {e}")
        return jsonify({"success": False, "msg": str(e)}), 500


@app.route('/api/smart_move', methods=['POST'])
def api_smart_move():
    payload = request.json or {}
    return jsonify(logic.perform_smart_move(
        payload.get('location'),
        payload.get('spools'),
        target_slot=payload.get('slot'),
        origin=payload.get('origin', ''),
        confirm_active_print=bool(payload.get('confirm_active_print', False)),
    ))


def _apply_usage_to_printer(printer_name, usage_map, fb_url, strategy_label="",
                            active_locs=None):
    """Deduct per-toolhead grams from the spools currently mapped to
    `printer_name`'s toolheads. `usage_map` is {toolhead_position: grams}.

    The single canonical deduct loop, shared by the FilaBridge error-recovery
    aggressive parse (full-print estimate) and the cancelled-print PARTIAL
    deduct (prefix-parsed grams). MMU-alias positions (e.g. CORE1-M0 vs
    CORE1-M1 — same position in printer_map) are deduped via
    `processed_positions` so one usage slice isn't applied twice. Within a single
    toolhead, `spoolman_api.select_deduct_targets` drops a stale physical_source
    GHOST in favour of the directly-loaded spool so a leftover ghost trail can't
    double-charge the position (22.4(1)); a genuinely-ambiguous toolhead (2+
    distinct loaded spools, physically impossible at one-spool-per-head) is WARNed
    and SKIPPED — never silently over-deducted — so its grams surface as a
    shortfall the caller can true up (vs the interactive preview, which keeps both
    rows so the reviewer can pick). Writes ONLY `{used_weight}` per the CLAUDE.md
    write-surface contract — never bundles initial_weight/location/extra, so a
    partial deduct can't wipe siblings or silently archive a loaded spool. Surfaces
    LAST_SPOOLMAN_ERROR on rejection.

    `active_locs` may be passed pre-resolved (by a caller that already resolved it,
    e.g. the no_spool confirm) so an MMU printer's info.mmu ordering probe runs ONCE
    instead of per call (22.4(5)); None re-resolves it here.

    Returns (spools_updated, details, known_positions) where details is a list of
    {sid, grams, remaining} for each successful deduct and known_positions is the set
    of this printer's real toolhead positions — surfaced so the caller's shortfall
    (requested-but-not-applied) excludes orphan tool indices, which already got their
    own WARNING here, instead of double-warning them (22.4(3)).
    """
    if active_locs is None:
        printer_map = locations_db.get_active_printer_map()  # L271 P4 step 2
        active_locs = _resolve_active_locs_for_printer(printer_map, printer_name, fb_url)
    spools_updated = 0
    details = []
    processed_positions = set()
    for loc_id, p_info in active_locs:
        toolhead_idx = p_info.get('position', 0)
        if toolhead_idx in processed_positions:
            continue
        if toolhead_idx not in usage_map:
            continue
        weight_used = usage_map[toolhead_idx]
        loc_spools = spoolman_api.get_spools_at_location(loc_id)
        if not loc_spools:
            continue  # try the next alias for this position
        processed_positions.add(toolhead_idx)
        # >1 spool at one toolhead = a stale GHOST + the current load (or two
        # mis-assignments). Resolve to the directly-loaded spool; only fetch the
        # detailed/ghost info in this rare case so the single-spool common path is
        # untouched. 2+ distinct LOADED spools is unresolvable — warn + skip rather
        # than guess (which over-deducts or hits the wrong spool); the grams then
        # show up as a shortfall.
        if len(loc_spools) > 1:
            loc_spools, ambiguous = spoolman_api.select_deduct_targets(loc_id)
            if ambiguous:
                state.add_log_entry(
                    f"⚠️ {printer_name}: toolhead {str(loc_id).upper()} has "
                    f"{len(loc_spools)} spools assigned (sids {sorted(loc_spools)}) — "
                    f"can't tell which is loaded; {weight_used:.2f}g not deducted, "
                    f"weigh the spool to true up.", "WARNING", "ffaa00")
                continue
        for sid in loc_spools:
            spool_data = spoolman_api.get_spool(sid)
            if spool_data and weight_used > 0:
                used = float(spool_data.get('used_weight', 0))
                initial = float(spool_data.get('initial_weight', 0) or 0)
                remaining = max(0, initial - used)
                new_remaining = max(0, remaining - weight_used)
                new_used = used + weight_used
                if spoolman_api.update_spool(sid, {"used_weight": new_used}):
                    spools_updated += 1
                    # Spoolman caps used_weight ≤ initial, so a near-empty spool
                    # absorbs only `remaining`, not the full `weight_used`. Record the
                    # ACTUALLY-absorbed grams (= remaining - new_remaining) so the
                    # ledger and the callers' shortfall math reflect reality — else an
                    # over-capacity deduct reads as fully applied and the gap is
                    # silently lost (the clamp the partial-confirm loop also guards).
                    actual_g = min(float(weight_used), remaining)
                    info = spoolman_api.format_spool_display(spool_data)
                    label = strategy_label or "Auto-deduct"
                    state.add_log_entry(
                        f"✔️ Auto-deducted {actual_g:.1f}g from Spool #{sid} ({label}): "
                        f"[{remaining:.1f}g at start ➔ {new_remaining:.1f}g remaining]",
                        "SUCCESS", info['color'])
                    details.append({"sid": sid, "grams": actual_g, "remaining": new_remaining})
                else:
                    err = spoolman_api.LAST_SPOOLMAN_ERROR or "unknown error"
                    state.add_log_entry(
                        f"❌ Failed to auto-deduct from Spool #{sid}: {err}", "ERROR", "ff4444")
    # Surface gcode tool indices that don't correspond to ANY of this printer's
    # toolhead positions (a cross-machine gcode, or a tool↔position mismatch) —
    # those grams can't be deducted, so make the loss visible instead of
    # silently dropping it. (A position that exists but has no spool loaded is
    # benign and not flagged here.)
    known_positions = {p_info.get('position', 0) for _, p_info in active_locs}
    orphaned = {t: g for t, g in usage_map.items()
                if t not in known_positions and g > 0}
    if orphaned:
        lost = round(sum(orphaned.values()), 2)
        state.add_log_entry(
            f"⚠️ {printer_name}: {lost:.2f}g on tool index(es) {sorted(orphaned)} "
            f"map to no toolhead position on this printer — not deducted "
            f"(weigh the spool if this looks wrong).", "WARNING", "ffaa00")
    return spools_updated, details, known_positions


def _record_applied_deduct(printer_name, job_id, *, filename, scale, details,
                           usage_map, known_positions=None, confirmed=False):
    """Single source of truth for the tail of an auto-applied deduct: record the
    ACTUALLY-applied grams in the exactly-once ledger, then surface any shortfall
    (requested-but-not-applied grams) as a 2dp WARNING so it's never silently lost.
    Returns (applied, shortfall), both rounded to 2dp.

    Erases the drift the auto-apply sites had grown (22.4(2)/(4)):
      • the ledger records APPLIED (sum of `details`), not the requested estimate —
        deduct_cancelled_print used to record sum(usage_map) (the full requested),
        over-stating it and, via the single (printer,job_id) key, blocking an
        unbound position's later recovery; the completed/cancel-review paths already
        recorded applied, so this just aligns the three;
      • the shortfall WARN is 2dp here, matching the `shortfall_g` API field (the
        inline sites logged 1dp).
    `known_positions` (22.4(3)) restricts `requested` to tool indices on a real
    toolhead so an orphan index doesn't double-fire (its own orphan WARNING already
    fired inside _apply_usage_to_printer). None means "all indices are known".

    NOT for the api_cancel_deduct_confirm per-sid loop — that deducts user-chosen
    grams (no requested/usage_map concept), so a shortfall is meaningless there."""
    applied = round(sum(d['grams'] for d in details), 2)
    if known_positions is None:
        requested = round(sum(usage_map.values()), 2)
    else:
        requested = round(sum(g for t, g in usage_map.items()
                              if t in known_positions), 2)
    extra = {"confirmed": True} if confirmed else {}
    print_deduct_ledger.record_deduct(printer_name, job_id, filename=filename,
                                      scale=scale, grams=applied, **extra)
    shortfall = round(max(0.0, requested - applied), 2)
    if shortfall > 0.05:
        state.add_log_entry(
            f"⚠️ {printer_name}: {shortfall:.2f}g of '{filename}' wasn't deducted "
            f"(no bound spool, a failed write, or a near-empty spool) — weigh that "
            f"spool to true up.", "WARNING", "ffaa00")
    return applied, shortfall


def _snapshot_active_spools(printer_name, fb_url, active_locs=None):
    """Resolve {toolhead_position: the single loaded sid, or None} for `printer_name`,
    using the SAME per-position alias-fallthrough + ghost-vs-current pick as
    _apply_usage_to_printer — so a print-START snapshot and a completion snapshot
    compare apples-to-apples (22.3 mid-print spool-swap detection). A position is
    None when it's EMPTY or AMBIGUOUS (2+ distinct loaded spools), so ONLY a clean
    1→1 sid change between two snapshots ever flags a swap.

    Best-effort: any failure (Spoolman blip, no printer_map) returns {}, so the
    caller degrades to today's auto-apply rather than crashing the deduct. Per-
    position cost mirrors the apply loop (one get_spools_at_location per position;
    select_deduct_targets only on the rare >1 case) — bounded, once per job at start
    and once at completion; bucket_spools_by_location could collapse it to one fetch
    later if it shows in a perf trace."""
    snap = {}
    try:
        if active_locs is None:
            printer_map = locations_db.get_active_printer_map()
            active_locs = _resolve_active_locs_for_printer(printer_map, printer_name, fb_url)
        processed = set()
        for loc_id, p_info in active_locs:
            pos = p_info.get('position', 0)
            if pos in processed:
                continue
            sids = spoolman_api.get_spools_at_location(loc_id)
            if not sids:
                continue  # try the next alias for this position (mirror the apply loop)
            processed.add(pos)
            if len(sids) > 1:
                sids, _amb = spoolman_api.select_deduct_targets(loc_id)
            snap[pos] = sids[0] if len(sids) == 1 else None
    except Exception:
        return {}
    return snap


def _validated_start_spools(src, job_id):
    """Return src's `start_spools` snapshot ONLY if it belongs to `job_id`, else None.
    `src` is the tracker entry (restart) or the fire dict (live edge). Both job_id
    sides are str-coerced — get_printer_job can hand back an int job_id while
    `snapshot_job` is stored as a string, so a bare == would silently invalidate a
    good snapshot (int 9 != '9'). Guards a stale snapshot from a previous job."""
    if not src:
        return None
    if str(src.get('snapshot_job')) != str(job_id):
        return None
    return src.get('start_spools')


def _validated_swap_log(src, job_id):
    """22.3(b): return src's `swap_log` (ordered mid-print swap events) ONLY if its
    snapshot belongs to `job_id`. swap_log is captured under the same `snapshot_job`
    as start_spools and popped alongside it on a job change, so it shares the guard —
    a stale log from a previous job is never carried into a completion deduct."""
    if not src:
        return None
    if str(src.get('snapshot_job')) != str(job_id):
        return None
    return src.get('swap_log')


def _is_sid_swap(before, after):
    """True iff `before`→`after` is a confident, clean 1→1 spool change at one toolhead
    position: both sides present (a None = an EMPTY or ambiguous toolhead, never a
    confident swap) AND different. Compared as STRINGS so (a) a JSON int↔str round-trip
    can't make the same sid read as changed, and (b) a non-numeric sid can never raise —
    the bare `int(a) != int(b)` this replaces could throw a ValueError that the callers'
    best-effort `except` swallowed into a SILENT full-footer auto-apply (the exact
    mis-attribution the swap guard exists to prevent). Single source of truth for "did the
    spool at this position change", shared by the capture (_record_swap_events) and the
    completion-time detector (deduct_completed_print) so the two can't drift."""
    return before is not None and after is not None and str(before) != str(after)


def _record_swap_events(entry, end_snap, progress):
    """22.3(b): append ordered mid-print spool-swap events to entry['swap_log'] by
    diffing a resume-time snapshot (`end_snap` = {position: loaded sid or None}) against
    the mapping in effect for the segment just printed — start_spools advanced by the
    destination (`to_sid`) of any prior swap at each position. Only a clean 1→1 sid
    change flags: None on EITHER side (an empty or ambiguous toolhead) is not a
    confident swap, mirroring the completion-time guard. Mutates `entry` in place; the
    caller holds the tracker lock. Returns the count of new events appended.

    Each event is {seq, position, progress, from_sid, to_sid}. `progress` is the
    boundary % at the pause (the segment that just ended reached it); `seq` is the
    append order so a downstream apportionment can align segment k → the spool loaded
    after the k-th resume. Detection only fires when the spool MAPPING changes — i.e.
    an FCC eject/load at the pause updates Spoolman `location`; a purely physical roll
    swap with no FCC action is invisible (documented limitation, same as 22.3(c))."""
    start = entry.get('start_spools') or {}
    log = list(entry.get('swap_log') or [])
    # Reconstruct what the just-printed segment was feeding from: the start mapping,
    # advanced by each prior swap's destination at that position.
    running = {str(k): v for k, v in start.items()}
    for ev in log:
        running[str(ev.get('position'))] = ev.get('to_sid')
    added = 0
    for pos, to_sid in end_snap.items():
        from_sid = running.get(str(pos))
        if not _is_sid_swap(from_sid, to_sid):
            continue  # empty/ambiguous on either side, or unchanged — not a swap
        log.append({
            "seq": len(log),
            "position": pos,
            "progress": float(progress or 0.0),
            "from_sid": from_sid,
            "to_sid": to_sid,
        })
        added += 1
    if added:
        entry['swap_log'] = log
    return added


def _log_cancel_uncomputable(printer_name, filename, reached_fraction, content):
    """Operator-facing log for a cancel whose partial we couldn't compute,
    distinguishing the three reasons so a cancel never goes SILENTLY
    un-deducted. Returns the status string the caller should surface.
      content is None      → download failed / binary .bgcode  → 'error' (WARNING)
      footer present        → genuine zero-extrusion cancel      → 'no_usage' (INFO)
      footer absent         → unrecognized gcode (non-Prusa?)    → 'no_usage' (WARNING)
    """
    pct = max(0.0, min(1.0, float(reached_fraction))) * 100
    if not content:
        state.add_log_entry(
            f"🛑 Cancelled print on {printer_name} ('{filename}', ~{pct:.0f}%) — "
            f"couldn't fetch/parse the gcode (binary .bgcode or printer "
            f"unreachable); no partial deduct. Weigh the spool to true it up.",
            "WARNING", "ffaa00")
        return "error"
    has_footer = ('filament used [g]' in content and 'filament used [mm]' in content)
    if has_footer:
        state.add_log_entry(
            f"🛑 Cancelled print on {printer_name} ('{filename}', ~{pct:.0f}%) — "
            f"no partial usage to deduct (cancelled before any extrusion).",
            "INFO")
    else:
        state.add_log_entry(
            f"🛑 Cancelled print on {printer_name} ('{filename}', ~{pct:.0f}%) — "
            f"gcode has no recognized per-tool 'filament used' footer "
            f"(non-Prusa slicer?); can't compute the partial. Weigh the spool.",
            "WARNING", "ffaa00")
    return "no_usage"


def _compute_cancel_usage(printer_name, filename, job_id, reached_fraction,
                          ip_address, api_key, use_footer=False):
    """Download + parse a print → (usage_map, terminal).
    On success: (usage_map, None). On a can't-compute outcome: (None, status
    dict). Shared by the cancel paths (auto-apply deduct_cancelled_print + preview
    _create_pending_cancel_review) AND the Phase-2 completion path
    (deduct_completed_print).

    use_footer=False (cancel/partial): prefix-parse the body up to the cancel
    point. use_footer=True (COMPLETED print): parse the full per-tool footer (the
    exact slicer estimate = what FilaBridge billed — the cancel prefix-parse's
    high-water-mark E omits the final wipe/ram tail, which a completion should
    keep). Both yield {tool_index: grams} in the same space, so the single-tool
    fold + downstream resolution are identical.

    fetch_cancel_gcode transparently decodes binary G-code (.bgcode — Derek's
    whole fleet) and remaps the progress fraction from compressed-file space to
    the decoded text, so the prefix-parse runs correctly on real prints. The
    decoded text also carries the footer, so use_footer reads it from the same
    download."""
    prepared = prusalink_api.fetch_cancel_gcode(
        ip_address, api_key, filename, reached_fraction)
    if not prepared or not prepared.get("gcode"):
        # Download failed. The dominant cause is NOT a permanent error: PrusaLink
        # 404s the raw-file download while the file is the SELECTED/active print
        # — i.e. while the printer sits in STOPPED with the cancel-summary screen
        # up, which is EXACTLY when we fire (confirmed live 2026-06-11; §9.10).
        # The file un-locks once the print is cleared (→ IDLE). So this is
        # RETRYABLE: return without a terminal "weigh the spool" log and let the
        # caller stash a deferred-fetch retry (the monitor re-attempts each tick
        # once the printer leaves STOPPED). (Was an immediate terminal error.)
        return None, {"status": "error", "reason": "download_failed", "job_id": job_id}
    content = prepared["gcode"]
    if use_footer:
        # Completion: the full per-tool slicer footer (exact, = FilaBridge).
        usage_map = prusalink_api.parse_footer_usage(content)
    else:
        usage_map = prusalink_api.parse_partial_filament_usage(content, prepared["fraction"])
    if not usage_map:
        if not use_footer:
            # Cancel-specific "weigh the spool" log. A completion with an empty
            # footer is a degenerate no-op — its caller logs its own line.
            _log_cancel_uncomputable(printer_name, filename, reached_fraction, content)
        return None, {"status": "no_usage", "job_id": job_id}

    # Single-toolhead printer + single-material print (Derek's Core One: one
    # head, one spool): the slicer's tool INDEX can differ from the printer's
    # toolhead POSITION (an MMU-profile file marks slot 1 even when one head
    # exists), so re-key that lone tool onto the sole position — otherwise it
    # orphans to a non-existent position and goes un-deducted. Guarded to a
    # SINGLE footer tool so a real multi-material MMU print (several spools
    # swapped through one head) is NOT summed onto one spool (over-deduct); that
    # genuinely-ambiguous case falls through to the orphan warning instead.
    # Multi-head printers (XL / future INDX toolchanger) keep their per-tool map
    # untouched — there the tool index IS the toolhead position (1:1).
    try:
        if len(usage_map) == 1:
            pm = locations_db.get_active_printer_map()
            positions = {info.get('position', 0) for info in pm.values()
                         if info.get('printer_name') == printer_name}
            if len(positions) == 1:
                sole = next(iter(positions))
                grams = next(iter(usage_map.values()))
                usage_map = {sole: grams}
    except Exception:
        pass

    return usage_map, None


def deduct_cancelled_print(printer_name, filename, job_id, reached_fraction,
                           fb_url=None, ip_address=None, api_key=None):
    """Compute + AUTO-APPLY the PARTIAL filament deduct for a CANCELLED print
    (FilaBridge absorption design §9). Exactly-once via the (printer, job_id)
    ledger; NEVER deducts the full estimate (that's the ~10x over-charge a
    cancel must avoid). Returns a status dict:

      status='skipped'   already deducted (ledger hit) — no-op
      status='no_usage'  cancelled before extrusion / no metadata — recorded, 0g
      status='deducted'  partial grams applied; carries spools_updated + details
      status='error'     credentials / gcode download failed (NOT recorded, so a
                         later retry can still deduct)

    NOTE: the live cancel-EDGE no longer calls this — slice 5 routes cancels
    through _create_pending_cancel_review (preview-and-confirm, §9.7). This
    remains the canonical "compute-and-apply-in-one-shot" primitive (a future
    opt-in auto-mode / recompute action can call it) and shares its compute half
    with the preview path via _compute_cancel_usage.
    """
    if fb_url is None:
        _, fb_url = config_loader.get_api_urls()

    if print_deduct_ledger.was_deducted(printer_name, job_id):
        return {"status": "skipped", "reason": "already deducted", "job_id": job_id}

    if not (ip_address and api_key):
        creds = prusalink_api.fetch_printer_credentials(fb_url, printer_name)
        if not creds:
            return {"status": "error", "reason": "no credentials", "job_id": job_id}
        ip_address, api_key = creds.get('ip_address'), creds.get('api_key')

    usage_map, terminal = _compute_cancel_usage(
        printer_name, filename, job_id, reached_fraction, ip_address, api_key)
    if terminal is not None:
        if terminal["status"] == "no_usage":
            print_deduct_ledger.record_deduct(printer_name, job_id, filename=filename,
                                              scale=reached_fraction, grams=0)
        elif terminal["status"] == "error":
            # This one-shot auto-apply primitive has no retry loop, so surface the
            # download failure (the live preview path defers/retries instead).
            _log_cancel_uncomputable(printer_name, filename, reached_fraction, None)
        return terminal

    pct = max(0.0, min(1.0, float(reached_fraction))) * 100
    spools_updated, details, known = _apply_usage_to_printer(
        printer_name, usage_map, fb_url, strategy_label="Cancel")
    if spools_updated == 0:
        # Usage WAS computed but no spool is bound to the toolhead — don't burn a
        # terminal grams=0 ledger entry (it permanently blocks recovery). Stash a
        # RECOVERABLE no_spool review carrying the usage_map, mirroring the completed
        # path's guard, so binding the toolhead later recovers it. (This one-shot
        # primitive isn't on the live edge today — the cancel edge routes through
        # _create_pending_cancel_review — but keep the three apply sites uniform.)
        return _stash_unresolved_review(printer_name, filename, job_id, reached_fraction,
                                        usage_map=usage_map, no_spool=True)
    total = round(sum(d["grams"] for d in details), 1)
    state.add_log_entry(
        f"🛑 Cancelled-print partial deduct on {printer_name}: {total:.1f}g across "
        f"{spools_updated} spool(s) at ~{pct:.0f}% progress ('{filename}').",
        "WARNING")
    # Record the APPLIED grams (was sum(usage_map) = the full requested — the drift
    # the completed/cancel-review paths didn't have; 22.4(2)) + surface any shortfall
    # over known positions (22.4(3)).
    _record_applied_deduct(
        printer_name, job_id, filename=filename, scale=reached_fraction,
        details=details, usage_map=usage_map, known_positions=known)
    return {"status": "deducted", "spools_updated": spools_updated,
            "details": details, "usage_map": usage_map, "job_id": job_id}


def deduct_completed_print(printer_name, filename, job_id, fb_url=None,
                           ip_address=None, api_key=None, start_spools=None,
                           swap_log=None):
    """Compute + AUTO-APPLY the full per-tool deduct for a COMPLETED (FINISHED)
    print — FCC's Phase-2 takeover of FilaBridge's completion deduct. Uses the
    slicer FOOTER (the full per-tool estimate, exact = what FilaBridge billed;
    neither side handles M486), NOT the cancel prefix-parse. Exactly-once via the
    (printer, job_id) ledger. Auto-applies SILENTLY with a ✅ log line — NO
    preview/confirm, because a completion's grams are exact (the cancel review
    exists to nudge the M486/partial over-estimate, which doesn't apply here).

    `start_spools` (22.3): the {position: sid} snapshot captured at print-START. If a
    USED toolhead's mapped spool CHANGED between start and completion (a mid-print
    runout/M600 replace), the full footer would dump the whole tool's usage on the
    REPLACEMENT spool and record 0g on the run-out spool — both wrong. In that case
    we route the completion to the cancel-REVIEW pipeline (for a manual split)
    instead of auto-applying. None (the deferred-fetch retry, a restart that lost
    the snapshot, a capture failure) → skip detection → today's auto-apply (safe).

    `swap_log` (22.3(b)): the ordered list of mid-print swap events captured at each
    resume (see _record_swap_events). It catches a swap the coarse start-vs-end diff
    MISSES — most importantly A→B→A (a spool ran out, was replaced, then the original
    re-loaded, so start==end) — and carries the per-segment history a future
    apportionment will split on. Today a non-empty swap_log at a USED position routes
    the completion to the same manual-split review (safe degrade); the validated
    automatic per-segment split lands once Derek's real M600 data confirms the math.

    On a download lock/blip returns 'awaiting_fetch' and queues a deferred fetch
    (kind='complete'): a Connect-STARTED finished print locks the file behind the
    finish screen, exactly like a cancel's cancel-screen lock — the monitor
    retries once the printer leaves FINISHED. Same status-dict shape as
    deduct_cancelled_print. Gated by the fcc_owns_completion_deduct flag at the
    EDGE (this primitive itself is unconditional, so the deferred-fetch retry can
    still finish a completion enqueued while the flag was on)."""
    if fb_url is None:
        _, fb_url = config_loader.get_api_urls()
    if print_deduct_ledger.was_deducted(printer_name, job_id):
        return {"status": "skipped", "reason": "already deducted", "job_id": job_id}
    if not (ip_address and api_key):
        creds = prusalink_api.fetch_printer_credentials(fb_url, printer_name)
        if not creds:
            _enqueue_cancel_fetch(printer_name, filename, job_id, 1.0, kind="complete",
                                  start_spools=start_spools, swap_log=swap_log)
            return {"status": "awaiting_fetch", "reason": "no credentials", "job_id": job_id}
        ip_address, api_key = creds.get('ip_address'), creds.get('api_key')

    usage_map, terminal = _compute_cancel_usage(
        printer_name, filename, job_id, 1.0, ip_address, api_key, use_footer=True)
    if terminal is not None:
        if terminal["status"] == "no_usage":
            print_deduct_ledger.record_deduct(printer_name, job_id, filename=filename,
                                              scale=1.0, grams=0)
            state.add_log_entry(
                f"✅ Completed print on {printer_name} ('{filename}') — no filament "
                f"usage in the footer; nothing to deduct.", "INFO")
        elif terminal["status"] == "error":
            # Download failed — the Connect finish-screen LOCK (the completion
            # analogue of the cancel-screen lock §9.10). Defer; the monitor
            # retries once the printer leaves FINISHED (→ IDLE, file unlocked).
            # Carry start_spools + swap_log so the retry still detects a mid-print
            # spool swap (the live latch is gone by then; 22.3 deferred-completion fix).
            _enqueue_cancel_fetch(printer_name, filename, job_id, 1.0, kind="complete",
                                  start_spools=start_spools, swap_log=swap_log)
            return {"status": "awaiting_fetch", "reason": terminal.get("reason"),
                    "job_id": job_id}
        return terminal

    # Resolve the printer's active toolheads ONCE and share it with both the swap
    # detection read and the apply, so an MMU printer's info.mmu ordering probe runs
    # once (22.4(5) pattern).
    printer_map = locations_db.get_active_printer_map()
    active_locs = _resolve_active_locs_for_printer(printer_map, printer_name, fb_url)
    # 22.3: mid-print spool-swap guard. If a USED toolhead's mapped spool changed
    # during the print, the full footer would mis-attribute the whole tool's usage to
    # the replacement — route to a manual-split review instead of auto-applying. Two
    # detectors, unioned: (22.3c) a coarse start-vs-END snapshot diff, and (22.3b) the
    # ordered swap_log captured at each resume. swap_log catches a swap the 2-point
    # diff misses — notably A→B→A (ran out, replaced, original re-loaded → start==end).
    # Best-effort: any detection error falls through to auto-apply (NEVER block/drop a
    # completion on a detection bug).
    if start_spools or swap_log:
        try:
            changed = set()
            used_positions = {p for p, g in usage_map.items() if g > 0}
            if start_spools:
                end_snap = _snapshot_active_spools(printer_name, fb_url, active_locs=active_locs)
                for pos in used_positions:
                    # Only a clean 1→1 sid change flags. None on EITHER side (empty/
                    # ambiguous/orphan at start or end) is NOT a confident swap signal —
                    # the no_spool/shortfall/ambiguous-skip machinery covers those. Shared
                    # _is_sid_swap predicate (string-compare; no int() so a non-numeric sid
                    # can't ValueError into a silently-swallowed auto-apply).
                    if _is_sid_swap(start_spools.get(str(pos)), end_snap.get(pos)):
                        changed.add(pos)
            if swap_log:
                # A captured resume swap at a USED position — already validated 1→1 at
                # capture time (_record_swap_events), so no re-snapshot needed.
                for ev in swap_log:
                    if ev.get('position') in used_positions:
                        changed.add(ev.get('position'))
            if changed:
                return _route_completion_to_review(
                    printer_name, filename, job_id, usage_map, fb_url, sorted(changed),
                    active_locs=active_locs, swap_log=swap_log)
        except Exception:
            pass  # detection is best-effort; fall through to auto-apply

    spools_updated, details, known = _apply_usage_to_printer(
        printer_name, usage_map, fb_url, strategy_label="Complete", active_locs=active_locs)
    if spools_updated == 0:
        # Footer had usage but NO spool is bound at the active toolhead(s). Don't
        # burn a terminal grams=0 ledger entry (it permanently blocks recovery —
        # the 2026-06-13 silent-loss bug); stash a RECOVERABLE review carrying the
        # footer usage_map so the confirm path re-resolves + applies once a spool is
        # bound. apply wrote nothing when spools_updated==0, so there's nothing to
        # undo.
        return _stash_unresolved_review(printer_name, filename, job_id, 1.0,
                                        usage_map=usage_map, no_spool=True)
    # Record what was ACTUALLY deducted, not the full footer estimate: on a
    # multi-tool print where one toolhead has a spool and another doesn't,
    # _apply_usage_to_printer deducts only the bound one(s), so sum(usage_map) would
    # over-state the ledger and (single (printer,job_id) key) the unbound position's
    # grams can't be held pending alongside this recorded deduct. _record_applied_deduct
    # records the applied grams + surfaces any shortfall over KNOWN positions (an
    # orphan tool index already warned inside the apply loop, so it's excluded here
    # to avoid a double-warn — 22.4(2)/(3)).
    applied = round(sum(d["grams"] for d in details), 2)
    state.add_log_entry(
        f"✅ Completed-print deduct on {printer_name}: {applied:.1f}g across "
        f"{spools_updated} spool(s) ('{filename}').", "SUCCESS")
    _record_applied_deduct(
        printer_name, job_id, filename=filename, scale=1.0, details=details,
        usage_map=usage_map, known_positions=known)
    return {"status": "deducted", "spools_updated": spools_updated,
            "details": details, "usage_map": usage_map, "job_id": job_id}


def _route_completion_to_review(printer_name, filename, job_id, usage_map, fb_url,
                               changed_positions, active_locs=None, swap_log=None):
    """22.3 minimum-viable: a COMPLETED print where a used toolhead's mapped spool
    CHANGED mid-print is NOT auto-applied (the full footer would dump the whole
    tool's usage on the replacement spool, zeroing the run-out spool). Stash a
    'spool_changed' review carrying the completion-time preview rows so the user
    splits the grams manually — reusing the cancel-review confirm pipeline verbatim
    (api_cancel_deduct_confirm routes any kind with `spools` rows through the per-sid
    partial loop). Writes NO ledger (confirm/dismiss owns that), so exactly-once
    holds via the review store + ledger guards.

    `swap_log` (22.3(b)) is persisted on the review record for two reasons: it's the
    per-segment history a validated automatic apportionment will split on, and it lets
    the review surface "this spool ran during segment k" context. It does NOT change
    today's behavior (the user still splits manually) — it's carried, not yet consumed
    for the math."""
    if print_deduct_ledger.was_deducted(printer_name, job_id):
        # Already settled — clear any stale pending so "ledger ⟹ no pending" holds.
        cancel_review_store.pop_pending(printer_name, job_id)
        return {"status": "skipped", "reason": "already processed", "job_id": job_id}
    if cancel_review_store.has_pending(printer_name, job_id):
        return {"status": "skipped", "reason": "already pending", "job_id": job_id}
    rows = _resolve_usage_to_spools(printer_name, usage_map, fb_url, active_locs=active_locs)
    if not rows:
        # The replacement isn't bound right now — still recoverable via no_spool.
        # (Shouldn't usually reach here: a flagged position has a bound end spool.)
        return _stash_unresolved_review(printer_name, filename, job_id, 1.0,
                                        usage_map=usage_map, no_spool=True)
    # Claim the deferred-fetch slot too, so a queued kind='complete' retry (a prior
    # finish-screen lock) can't later auto-apply the full footer behind this review.
    cancel_fetch_store.pop_pending(printer_name, job_id)
    total = round(sum(r['grams'] for r in rows), 2)
    record = {
        "printer_name": printer_name,
        "job_id": str(job_id),
        "filename": filename,
        "progress": 1.0,
        "total_grams": total,
        "spools": rows,
        "ambiguous": False,
        "kind": "spool_changed",
        "changed_positions": sorted(changed_positions),
        # 22.3(b): the ordered mid-print swap history (empty when only the coarse
        # start-vs-end diff fired). Carried for the future per-segment apportionment;
        # the review still splits manually today.
        "swap_log": list(swap_log) if swap_log else [],
        "created": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    cancel_review_store.add_pending(record)
    state.add_log_entry(
        f"🔁 {printer_name}: spool changed mid-print ('{filename}') at toolhead "
        f"position(s) {sorted(changed_positions)} — full footer NOT auto-applied; "
        f"review the split: {total:.2f}g across {len(rows)} spool(s).",
        "WARNING", rows[0]['color'],
        meta={"type": "cancel_deduct_pending",
              "printer_name": printer_name, "job_id": str(job_id)})
    return {"status": "pending_spool_changed", "spools": len(rows), "job_id": str(job_id)}


def _resolve_usage_to_spools(printer_name, usage_map, fb_url, active_locs=None):
    """Read-only resolution of {toolhead_position: grams} → the per-spool rows a
    deduct WOULD touch — the cancel-review PREVIEW (no write). Mirrors
    _apply_usage_to_printer's MMU-alias/dedup AND ghost-vs-current resolution
    (`select_deduct_targets`), minus the write, so the preview is faithful to what
    a confirm will deduct. The one deliberate divergence: where the autonomous
    apply SKIPS a genuinely-ambiguous toolhead (2+ distinct loaded spools), this
    interactive preview KEEPS both rows flagged `ambiguous` so the reviewer can see
    the bad assignment and choose. Each row carries a snapshot of the spool's
    current used/remaining for display; the actual write (confirm) re-reads current
    used and applies additively, so a weigh-out between preview and confirm can't be
    clobbered. `active_locs` may be passed pre-resolved to share an MMU probe with a
    paired _apply_usage_to_printer call (22.4(5)); None re-resolves it here.
    """
    if active_locs is None:
        printer_map = locations_db.get_active_printer_map()
        active_locs = _resolve_active_locs_for_printer(printer_map, printer_name, fb_url)
    rows = []
    processed_positions = set()
    for loc_id, p_info in active_locs:
        pos = p_info.get('position', 0)
        if pos in processed_positions:
            continue
        if pos not in usage_map:
            continue
        grams = usage_map[pos]
        if grams <= 0:
            continue
        loc_spools = spoolman_api.get_spools_at_location(loc_id)
        if not loc_spools:
            continue  # try the next alias for this position
        processed_positions.add(pos)
        # Mirror the apply loop's ghost-vs-current resolution (22.4(1)); only the
        # rare >1 case fetches the detailed/ghost info, so the single-spool path is
        # unchanged. Preview keeps an ambiguous toolhead's rows (flagged) rather
        # than skipping, so the reviewer can resolve it.
        ambiguous = False
        if len(loc_spools) > 1:
            loc_spools, ambiguous = spoolman_api.select_deduct_targets(loc_id)
        for sid in loc_spools:
            spool = spoolman_api.get_spool(sid)
            if not spool:
                continue
            used = float(spool.get('used_weight', 0) or 0)
            initial = float(spool.get('initial_weight', 0) or 0)
            remaining_before = max(0.0, initial - used)
            remaining_after = max(0.0, remaining_before - grams)
            disp = spoolman_api.format_spool_display(spool)
            rows.append({
                'sid': sid,
                'toolhead': str(loc_id).upper(),
                'position': pos,
                'grams': round(float(grams), 2),
                'current_used': round(used, 2),
                'initial_weight': round(initial, 2),
                'remaining_before': round(remaining_before, 1),
                'remaining_after': round(remaining_after, 1),
                'display': disp.get('text', f"#{sid}"),
                'color': disp.get('color', '888888'),
                'ambiguous': bool(ambiguous),
            })

    # Merge rows that resolve to the SAME spool. One physical spool can feed more
    # than one toolhead position (a shared-spool config, or the dev XL-4/XL-5=
    # #230 case), producing two rows for one sid. The confirm path keys updates
    # by sid (frontend `updates[sid]` + backend `rec_rows={sid:row}`), so two
    # same-sid rows would COLLAPSE to a single deduct — a silent under-deduct
    # (found 2026-06-12: job 690 previewed 1.65g but only ~0.8g applied). Sum the
    # grams here so there's exactly one row per spool: the spool loses filament
    # once, totalled across every position it fed.
    merged = {}
    for r in rows:
        m = merged.get(r['sid'])
        if m is None:
            merged[r['sid']] = r
        else:
            m['grams'] = round(m['grams'] + r['grams'], 2)
            m['remaining_after'] = round(max(0.0, m['remaining_before'] - m['grams']), 1)
            if str(r['toolhead']) not in str(m['toolhead']).split(', '):
                m['toolhead'] = f"{m['toolhead']}, {r['toolhead']}"
            # Same-sid rows can't differ in `ambiguous` by construction (a 2+-distinct
            # case yields different sids that never merge), but OR defensively so the
            # flag can't be silently dropped if the row schema grows.
            m['ambiguous'] = bool(m.get('ambiguous')) or bool(r.get('ambiguous'))
    return list(merged.values())


def _stash_unresolved_review(printer_name, filename, job_id, reached_fraction,
                             usage_map=None, *, no_spool=False,
                             progress_unknown=False, ambiguous=False):
    """Stash a persistent, RECOVERABLE review for a print whose usage couldn't be
    finalized — INSTEAD of writing a destructive terminal grams=0 ledger entry that
    would permanently block recovery (the 2026-06-13 silent-loss bug). Two kinds:

      no_spool         — usage WAS computed (real grams in `usage_map`) but NO spool
                         is bound to the toolhead, so there's nowhere to deduct. The
                         confirm endpoint RE-RESOLVES `usage_map` to whatever spool is
                         bound at apply time, so binding the toolhead later recovers it.
      progress_unknown — the print was replaced (a back-to-back job change) before we
                         ever sampled a real progress, so its usage is genuinely
                         UNMEASURABLE (`usage_map` is None). Surfaced non-destructively
                         ("weigh the spool and adjust it directly, or Discard").

    Writes NO ledger entry — the review stays recoverable until confirm/dismiss.
    Idempotent: no-ops if a review is already pending or the job was already settled.
    Returns a status dict."""
    if print_deduct_ledger.was_deducted(printer_name, job_id):
        return {"status": "skipped", "reason": "already processed", "job_id": job_id}
    if cancel_review_store.has_pending(printer_name, job_id):
        return {"status": "skipped", "reason": "already pending", "job_id": job_id}

    usage_map = usage_map or {}
    total = round(sum(usage_map.values()), 2) if usage_map else 0.0
    # Binary on purpose: this helper ONLY stashes UNRESOLVED reviews. A neither-flag
    # call must NOT produce kind='partial' — that record (empty spools, no usage_map)
    # would route into the confirm partial loop and 0g-burn the ledger. Default the
    # (caller-error) neither case to the non-destructive progress_unknown kind.
    kind = "no_spool" if no_spool else "progress_unknown"

    if no_spool:
        msg = (f"⚠️ {printer_name}: print used ~{total:.2f}g ('{filename}') but it "
               f"couldn't be deducted (no spool bound to the toolhead, or the write was "
               f"rejected) — Review to apply once it's bound, or Discard.")
    else:  # progress_unknown
        msg = (f"❓ {printer_name}: couldn't measure how much '{filename}' used (replaced "
               f"before a progress reading) — Review to weigh the spool, or Discard.")

    record = {
        "printer_name": printer_name,
        "job_id": str(job_id),
        "filename": filename,
        "progress": float(reached_fraction or 0.0),
        "total_grams": total,
        "spools": [],
        "ambiguous": bool(ambiguous),
        "kind": kind,
        # usage_map drives the confirm RE-RESOLVE for a no_spool review. JSON
        # stringifies int keys on save, so store them as strings explicitly and let
        # the confirm path coerce back to int (the resolve keys on int positions).
        "usage_map": ({str(k): v for k, v in usage_map.items()}
                      if (no_spool and usage_map) else None),
        "created": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    cancel_review_store.add_pending(record)
    state.add_log_entry(msg, "WARNING", "ffaa00",
                        meta={"type": "cancel_deduct_pending",
                              "printer_name": printer_name, "job_id": str(job_id)})
    return {"status": "pending_unresolved", "kind": kind, "total_grams": total,
            "job_id": str(job_id)}


def _enqueue_cancel_fetch(printer_name, filename, job_id, reached_fraction, kind="cancel",
                          ambiguous=False, start_spools=None, swap_log=None):
    """Queue a print whose gcode couldn't be fetched yet (the selected-file
    download LOCK, §9.10) for the monitor to retry. `kind` is 'cancel' (default)
    or 'complete' — a COMPLETED Connect-started print locks behind the FINISH
    screen the same way a cancel locks behind the cancel screen; the kind is
    stashed on the record so _process_pending_cancel_fetches routes the retry to
    the right handler (cancel→review, complete→auto-apply). `ambiguous` (carried
    on the record, only meaningful for kind='cancel') means the edge couldn't
    confirm cancel vs completion, so the retried review stays flagged.
    `start_spools` (22.3, kind='complete' only) is the print-start spool snapshot —
    persisted on the record so the deferred completion retry still gets mid-print
    spool-swap detection (the live latch is gone by retry time). `swap_log` (22.3(b),
    kind='complete') is the ordered mid-print swap history, persisted the same way so a
    deferred completion still detects an A→B→A swap the start-vs-end diff would miss.
    Idempotent:
    re-queuing the same job bumps `attempts`, PRESERVES `first_seen` (so the
    max-age give-up window is measured from the FIRST sighting), and does NOT
    re-nudge. The nudge logs exactly ONCE, on first queue. Returns True if newly
    queued (nudged), False if it was already queued."""
    if cancel_fetch_store.has_pending(printer_name, job_id):
        rec = cancel_fetch_store.get_pending(printer_name, job_id) or {}
        rec.update({"printer_name": printer_name, "job_id": str(job_id),
                    "filename": filename, "progress": float(reached_fraction),
                    "kind": kind, "ambiguous": bool(ambiguous),
                    # Preserve an already-captured snapshot/log if this re-queue lacks one.
                    "start_spools": start_spools or rec.get("start_spools"),
                    "swap_log": swap_log or rec.get("swap_log"),
                    "attempts": int(rec.get("attempts", 0)) + 1})
        cancel_fetch_store.add_pending(rec)
        return False
    cancel_fetch_store.add_pending({
        "printer_name": printer_name, "job_id": str(job_id), "filename": filename,
        "progress": float(reached_fraction), "first_seen": time.time(),
        "kind": kind, "ambiguous": bool(ambiguous), "start_spools": start_spools,
        "swap_log": swap_log,
        "attempts": 1, "last_status": "awaiting_fetch",
    })
    pct = max(0.0, min(1.0, float(reached_fraction))) * 100
    if ambiguous:
        # The ambiguous edge fires at IDLE (file already unlocked), so this path
        # is only a transient blip — use neutral wording (NOT "clear the screen").
        state.add_log_entry(
            f"❓ Print on {printer_name} (~{pct:.0f}%, '{filename}') ended without a "
            f"clear cancel/finish signal and its gcode isn't readable yet — I'll "
            f"retry and surface a review when it's readable.",
            "WARNING", "ffaa00",
            meta={"type": "cancel_deduct_awaiting",
                  "printer_name": printer_name, "job_id": str(job_id)})
    elif kind == "complete":
        state.add_log_entry(
            f"✅ Completed print on {printer_name} ('{filename}') detected — the "
            f"printer is still showing the finish screen, so the gcode is locked. "
            f"Clear it on the printer and I'll record the deduct automatically.",
            "INFO",
            meta={"type": "complete_deduct_awaiting",
                  "printer_name": printer_name, "job_id": str(job_id)})
    else:
        state.add_log_entry(
            f"🛑 Cancelled print on {printer_name} (~{pct:.0f}%, '{filename}') detected — "
            f"the printer is still showing the cancel screen, so the gcode is locked. "
            f"Clear it on the printer and I'll record the partial deduct automatically.",
            "WARNING", "ffaa00",
            meta={"type": "cancel_deduct_awaiting",
                  "printer_name": printer_name, "job_id": str(job_id)})
    return True


def _create_pending_cancel_review(printer_name, filename, job_id, reached_fraction,
                                  fb_url=None, ambiguous=False, progress_unknown=False):
    """Compute the cancelled-print partial and STASH it for review instead of
    auto-writing (FilaBridge absorption design §9.7). Idempotent against the
    ledger (already confirmed/dismissed) and the pending store (already queued).
    On success raises a 'cancel_deduct_pending' activity-log line (with meta) so
    the dashboard shows a "🛑 Review" button. Returns a status dict.

    ambiguous=True (2026-06-13): the print reached idle WITHOUT an observed
    terminal state, so we couldn't confirm cancel vs completion. The compute is
    identical (the partial at `reached_fraction`, the retained progress = the
    confidence hint), but the record is flagged and the log/overlay reword to
    "couldn't confirm". Still NEVER auto-deducts — it's a review either way."""
    if fb_url is None:
        _, fb_url = config_loader.get_api_urls()

    if print_deduct_ledger.was_deducted(printer_name, job_id):
        # Already confirmed/dismissed. Clear any stale pending so the invariant
        # "ledger ⟹ no pending" holds even after an odd crash sequence.
        cancel_review_store.pop_pending(printer_name, job_id)
        return {"status": "skipped", "reason": "already processed", "job_id": job_id}
    if cancel_review_store.has_pending(printer_name, job_id):
        return {"status": "skipped", "reason": "already pending", "job_id": job_id}

    if progress_unknown:
        # We never sampled a real progress for this job (a back-to-back job change
        # replaced it before the monitor measured it). Prefix-parsing at 0% would
        # fold to a misleading no_usage 0g and permanently lose it; the footer would
        # massively over-deduct. So don't compute or download — stash a
        # non-destructive "couldn't measure usage — weigh the spool" review.
        return _stash_unresolved_review(printer_name, filename, job_id,
                                        reached_fraction, usage_map=None,
                                        progress_unknown=True, ambiguous=ambiguous)

    creds = prusalink_api.fetch_printer_credentials(fb_url, printer_name)
    if not creds:
        # No creds right now (FilaBridge blip / printer briefly unreachable) —
        # retryable, so queue a deferred fetch rather than telling Derek to weigh.
        _enqueue_cancel_fetch(printer_name, filename, job_id, reached_fraction,
                              ambiguous=ambiguous)
        return {"status": "awaiting_fetch", "reason": "no credentials", "job_id": job_id}

    usage_map, terminal = _compute_cancel_usage(
        printer_name, filename, job_id, reached_fraction,
        creds.get('ip_address'), creds.get('api_key'))
    if terminal is not None:
        if terminal["status"] == "no_usage":
            print_deduct_ledger.record_deduct(printer_name, job_id, filename=filename,
                                              scale=reached_fraction, grams=0)
        elif terminal["status"] == "error":
            # Download failed — almost always the selected-file LOCK (§9.10): the
            # file un-locks once Derek clears the cancel screen (→ IDLE). Queue a
            # deferred fetch; the monitor retries each tick once the printer
            # leaves STOPPED, then computes + pops the 🛑 Review automatically.
            # (For the ambiguous edge the file is already unlocked at IDLE, so
            # this is just a transient-blip safety net — but carry the flag so a
            # retried review stays flagged "couldn't confirm".)
            _enqueue_cancel_fetch(printer_name, filename, job_id, reached_fraction,
                                  ambiguous=ambiguous)
            return {"status": "awaiting_fetch", "reason": terminal.get("reason"),
                    "job_id": job_id}
        return terminal

    rows = _resolve_usage_to_spools(printer_name, usage_map, fb_url)
    pct = max(0.0, min(1.0, float(reached_fraction))) * 100
    lead = ("❓ Print on {p} reached idle (~{pct:.0f}%, couldn't confirm cancel vs "
            "complete)").format(p=printer_name, pct=pct) if ambiguous else \
           "🛑 Cancelled print on {p} (~{pct:.0f}%)".format(p=printer_name, pct=pct)
    if not rows:
        # The print extruded filament but NO spool is bound to the active
        # toolhead(s) — nothing to deduct from RIGHT NOW. Don't burn a terminal
        # grams=0 ledger entry (that permanently blocks recovery — the 2026-06-13
        # silent-loss bug); stash a RECOVERABLE review carrying the computed
        # usage_map so the confirm path can re-resolve + apply once Derek binds the
        # toolhead.
        return _stash_unresolved_review(printer_name, filename, job_id,
                                        reached_fraction, usage_map=usage_map,
                                        no_spool=True, ambiguous=ambiguous)

    # Re-check after the (slow) gcode download+parse — if the job was processed
    # in the meantime, don't stash a stale pending.
    if print_deduct_ledger.was_deducted(printer_name, job_id):
        return {"status": "skipped", "reason": "already processed", "job_id": job_id}

    total = round(sum(r['grams'] for r in rows), 2)
    record = {
        "printer_name": printer_name,
        "job_id": str(job_id),
        "filename": filename,
        "progress": float(reached_fraction),
        "total_grams": total,
        "spools": rows,
        "ambiguous": bool(ambiguous),
        "created": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    cancel_review_store.add_pending(record)
    state.add_log_entry(
        f"{lead} — review {'computed' if ambiguous else 'partial'} "
        f"deduct: {total:.2f}g across {len(rows)} spool(s) ('{filename}').",
        "WARNING", rows[0]['color'],
        meta={"type": "cancel_deduct_pending",
              "printer_name": printer_name, "job_id": str(job_id)})
    return {"status": "pending", "spools": len(rows), "total_grams": total,
            "job_id": str(job_id)}


@app.route('/api/cancel_deduct/pending', methods=['GET'])
def api_cancel_deduct_pending():
    """All pending cancelled-print partial-deduct reviews awaiting confirm/
    dismiss. Drives the preview overlay (§9.7) and survives log scroll-off /
    restart."""
    return jsonify({"pending": cancel_review_store.list_pending()})


def _confirm_no_spool_review(printer, job_id, rec):
    """Apply a `no_spool` review (the record was already popped = the claim). The
    usage was computed when the print ended but no spool was bound; RE-RESOLVE the
    stored usage_map against whatever spool is bound to the toolhead NOW and apply
    it additively (ONLY {used_weight}, archive-on-empty discipline, via the canonical
    _apply_usage_to_printer loop). If still unbound, RE-STASH the record so it stays
    recoverable and report `still_no_spool` — never a terminal 0g."""
    _, fb_url = config_loader.get_api_urls()
    # Resolve the printer's active toolheads ONCE and thread it to BOTH the preview
    # resolve and the apply, so an MMU printer's info.mmu ordering probe runs once,
    # not twice (22.4(5)). The apply returns the real toolhead positions (`known`)
    # so the shortfall excludes orphan tool indices (22.4(3)).
    printer_map = locations_db.get_active_printer_map()
    active_locs = _resolve_active_locs_for_printer(printer_map, printer, fb_url)
    # JSON stringified the int positions on save — coerce back so the resolve (which
    # keys on int positions from printer_map) matches. Without this the re-resolve
    # silently finds nothing and always says "still no spool".
    umap = {}
    for k, v in (rec.get("usage_map") or {}).items():
        try:
            umap[int(k)] = float(v)
        except (TypeError, ValueError):
            continue
    rows = _resolve_usage_to_spools(printer, umap, fb_url, active_locs=active_locs) if umap else []
    if not rows:
        cancel_review_store.add_pending(rec)  # re-stash UNCHANGED — still recoverable
        return jsonify({"status": "still_no_spool",
                        "msg": "No spool is bound to this printer's toolhead yet — "
                               "bind it in the Location Manager, then Apply."})
    # A monitor retry could have settled this job between the pop and now.
    if print_deduct_ledger.was_deducted(printer, job_id):
        return jsonify({"status": "already_handled"})
    spools_updated, details, known = _apply_usage_to_printer(
        printer, umap, fb_url, strategy_label="Cancel-review", active_locs=active_locs)
    if spools_updated == 0:
        cancel_review_store.add_pending(rec)
        return jsonify({"status": "still_no_spool",
                        "msg": "No spool is bound to this printer's toolhead yet."})
    total = round(sum(d["grams"] for d in details), 2)
    state.add_log_entry(
        f"✔️ Cancel-review deduct {total:.2f}g across {spools_updated} spool(s) on "
        f"{printer} (toolhead now bound).", "SUCCESS")
    # Record applied + surface any shortfall via the shared helper (records confirmed,
    # 2dp warn matching the shortfall_g field, orphan-excluded — 22.4(2)/(3)/(4)).
    _, shortfall = _record_applied_deduct(
        printer, job_id, filename=rec.get('filename'), scale=rec.get('progress'),
        details=details, usage_map=umap, known_positions=known, confirmed=True)
    return jsonify({"status": "confirmed", "applied": details, "shortfall_g": shortfall})


@app.route('/api/cancel_deduct/confirm', methods=['POST'])
def api_cancel_deduct_confirm():
    """Apply a reviewed (optionally nudged) cancel partial-deduct. Body:
    {printer_name, job_id, updates: {sid: grams}}. Pops the pending record
    atomically (the CLAIM — a double-submit gets 'already_handled'), then
    deducts each spool ADDITIVELY against its CURRENT used_weight (re-read now,
    so a weigh-out between preview and confirm isn't clobbered) sending ONLY
    {used_weight} (archive-on-empty discipline)."""
    data = request.json or {}
    printer = data.get('printer_name')
    job_id = data.get('job_id')
    updates = data.get('updates') or {}
    if not printer or job_id is None:
        return jsonify({"status": "error", "msg": "missing printer_name/job_id"}), 400

    rec = cancel_review_store.pop_pending(printer, job_id)
    if rec is None:
        return jsonify({"status": "already_handled"})

    kind = rec.get("kind", "partial")
    if kind == "no_spool":
        # Usage was computed earlier but no spool was bound. RE-RESOLVE the stored
        # usage_map against whatever's bound NOW (Derek just bound the toolhead) and
        # apply. The pop above is the claim; _confirm_no_spool_review re-stashes if
        # still unbound so the review is never lost (no terminal 0g). Guard the whole
        # call: an UNEXPECTED raise (corrupt local JSON, a probe error) between the
        # pop and its controlled re-stash points would otherwise lose the popped
        # review with no ledger entry — a silent loss. Re-stash + surface on any raise.
        try:
            return _confirm_no_spool_review(printer, job_id, rec)
        except Exception as e:
            cancel_review_store.add_pending(rec)
            state.add_log_entry(
                f"❌ Cancel-review apply failed for {printer} (job {job_id}): {e} — "
                f"review kept for retry.", "ERROR", "ff4444")
            return jsonify({"status": "error", "msg": str(e)}), 500
    if kind == "progress_unknown":
        # No measured usage + no preview spools — nothing to auto-apply. Don't let
        # the partial loop below 0g-"confirm" it (that would re-lose it). Re-stash
        # and tell the user to weigh + adjust the spool directly, or Discard.
        cancel_review_store.add_pending(rec)
        return jsonify({"status": "manual_only",
                        "msg": "Usage couldn't be measured — weigh the spool and "
                               "adjust it directly, or Discard this review."})

    # Only spools that were in the reviewed preview may be deducted — a stray /
    # crafted update for an out-of-scope sid must never touch a different spool.
    rec_rows = {r["sid"]: r for r in rec.get("spools", [])}

    applied, errors = [], []
    failed_sids = set()
    for sid_raw, grams_raw in updates.items():
        try:
            sid = int(sid_raw)
            grams = float(grams_raw)
        except (TypeError, ValueError):
            continue
        if grams <= 0:
            continue
        if sid not in rec_rows:
            errors.append({"sid": sid, "error": "not in this review"})
            failed_sids.add(sid)
            continue
        spool = spoolman_api.get_spool(sid)
        if not spool:
            errors.append({"sid": sid, "error": "spool not found"})
            failed_sids.add(sid)
            continue
        # Re-read CURRENT used (a weigh-out between preview and confirm isn't
        # clobbered) and clamp grams to the spool's real remaining so the deduct
        # never exceeds capacity and the reported figures match what Spoolman
        # actually stores (update_spool silently caps used_weight ≤ initial).
        used = float(spool.get('used_weight', 0) or 0)
        initial = float(spool.get('initial_weight', 0) or 0)
        grams = min(grams, max(0.0, initial - used))
        if grams <= 0:
            # Spool already empty — nothing to deduct, but it's not a failure.
            applied.append({"sid": sid, "grams": 0.0, "remaining": 0.0})
            continue
        new_used = used + grams
        if spoolman_api.update_spool(sid, {"used_weight": new_used}):
            remaining = max(0.0, initial - new_used)
            info = spoolman_api.format_spool_display(spool)
            state.add_log_entry(
                f"✔️ Cancel-deduct {grams:.2f}g from Spool #{sid} (confirmed): "
                f"[➔ {remaining:.1f}g remaining]", "SUCCESS", info.get('color', '888888'))
            applied.append({"sid": sid, "grams": round(grams, 2), "remaining": round(remaining, 1)})
        else:
            err = spoolman_api.LAST_SPOOLMAN_ERROR or "unknown error"
            errors.append({"sid": sid, "error": err})
            failed_sids.add(sid)
            state.add_log_entry(
                f"❌ Cancel-deduct failed for Spool #{sid}: {err}", "ERROR", "ff4444")

    if errors:
        # Re-queue ONLY the spools that DIDN'T apply, so a retry can't double-
        # deduct the ones that did. Don't burn the ledger — the job isn't fully
        # done — so the edge stays blocked (has_pending) but a retry is possible.
        leftover = {r["sid"]: r for r in rec.get("spools", []) if r["sid"] in failed_sids}
        if leftover:
            retry_rec = dict(rec)
            retry_rec["spools"] = list(leftover.values())
            cancel_review_store.add_pending(retry_rec)
            # Re-emit the Review affordance so the retry is discoverable even if
            # the original cancel log line has scrolled off.
            state.add_log_entry(
                f"🛑 {len(leftover)} spool(s) still need a cancel-deduct review on "
                f"{printer} (a deduct failed) — Review to retry.",
                "WARNING", "ffaa00",
                meta={"type": "cancel_deduct_pending",
                      "printer_name": printer, "job_id": str(job_id)})
        status = "confirmed" if applied else "error"
        return jsonify({"status": status, "applied": applied, "errors": errors})

    # Full success — commit the ledger (exactly-once across restart/retry).
    print_deduct_ledger.record_deduct(
        printer, job_id, filename=rec.get('filename'), scale=rec.get('progress'),
        grams=round(sum(a['grams'] for a in applied), 2), confirmed=True)
    return jsonify({"status": "confirmed", "applied": applied, "errors": errors})


@app.route('/api/cancel_deduct/dismiss', methods=['POST'])
def api_cancel_deduct_dismiss():
    """Dismiss a pending cancel review without deducting. Body:
    {printer_name, job_id}. Records the ledger (so it can't re-surface) and pops
    the pending record."""
    data = request.json or {}
    printer = data.get('printer_name')
    job_id = data.get('job_id')
    if not printer or job_id is None:
        return jsonify({"status": "error", "msg": "missing printer_name/job_id"}), 400
    rec = cancel_review_store.pop_pending(printer, job_id)
    if rec is None:
        return jsonify({"status": "already_handled"})
    print_deduct_ledger.record_deduct(
        printer, job_id, filename=rec.get('filename'), scale=rec.get('progress'),
        grams=0, dismissed=True)
    state.add_log_entry(
        f"🚫 Dismissed cancel-deduct review for {printer} (job {job_id}) — "
        f"no weight deducted.", "INFO")
    return jsonify({"status": "dismissed"})


@app.route('/api/audit_session', methods=['GET'])
def api_audit_session():
    """L154 / 18.2 Part B — current audit session snapshot for the visual
    audit panel. Returns the location being audited plus enriched expected/
    scanned/rogue lists (each with the spool's display label, color,
    remaining weight, and slot if known) so the frontend can render a
    grid of tiles without doing per-id Spoolman lookups itself.

    Cheap when no audit is active (returns {active: False} immediately).

    Runs the idle-timeout watchdog first so even a direct poll heals a
    stale session — the dashboard's heartbeat hits /api/logs every 5s,
    but in case anything skips that path the same check here closes
    the loop."""
    _check_audit_idle_timeout()
    sess = state.AUDIT_SESSION
    if not sess.get('active'):
        return jsonify({"active": False})

    expected = list(sess.get('expected_items') or [])
    scanned = set(sess.get('scanned_items') or [])
    rogue = list(sess.get('rogue_items') or [])

    def _enrich(sid):
        try:
            sp = spoolman_api.get_spool(sid) or {}
        except Exception:
            sp = {}
        info = spoolman_api.format_spool_display(sp) if sp else {}
        fil = (sp.get('filament') or {})
        return {
            "id": int(sid),
            "display": info.get('text') or f"#{sid}",
            "color": fil.get('color_hex') or info.get('color') or '',
            "color_direction": fil.get('multi_color_direction') or 'longitudinal',
            "multi_color_hexes": fil.get('multi_color_hexes') or '',
            "remaining_weight": sp.get('remaining_weight'),
            "slot": (sp.get('extra') or {}).get('container_slot') or '',
        }

    expected_rows = []
    for sid in expected:
        row = _enrich(sid)
        row['found'] = (sid in scanned)
        expected_rows.append(row)
    rogue_rows = [{**_enrich(sid), 'found': True, 'rogue': True} for sid in rogue]

    return jsonify({
        "active": True,
        "location_id": sess.get('location_id'),
        "expected": expected_rows,
        "rogue": rogue_rows,
        "stats": {
            "total_expected": len(expected),
            "found": sum(1 for r in expected_rows if r['found']),
            "missing": sum(1 for r in expected_rows if not r['found']),
            "rogue": len(rogue),
        },
    })


# L316 step 9: the config-system endpoints + the filament-attributes manager
# live in routes_config_attrs.py. (api_audit_session stays below — it moves
# with _check_audit_idle_timeout + /api/logs in step 11.)
from routes_config_attrs import (  # noqa: E402,F401
    api_get_config, api_put_config, api_config_export, api_config_import,
    api_filament_attributes_report, api_filament_attributes_bulk_set,
    api_filament_attributes_add_choice, api_filament_attributes_remove_choice,
    api_filament_attributes_sweep_unused,
)

# --- PERSISTENCE ROUTES ---
@app.route('/api/state/buffer', methods=['GET', 'POST'])
def api_state_buffer():
    if request.method == 'POST':
        state.GLOBAL_BUFFER = request.json.get('buffer', [])
        return jsonify({"success": True})
    return jsonify(state.GLOBAL_BUFFER)

@app.route('/api/state/queue', methods=['GET', 'POST'])
def api_state_queue():
    if request.method == 'POST':
        state.GLOBAL_QUEUE = request.json.get('queue', [])
        return jsonify({"success": True})
    return jsonify(state.GLOBAL_QUEUE)

@app.route('/api/spools/refresh', methods=['POST'])
def api_spools_refresh():
    spools = request.json.get('spools', [])
    if not isinstance(spools, list):
        return jsonify({"error": "spools must be a list"}), 400
    if len(spools) == 0:
        return jsonify({})
    return jsonify(logic.get_live_spools_data(spools))

@app.route('/api/log_event', methods=['POST'])
def api_log_event():
    msg = request.json.get('msg', '')
    level = request.json.get('level', 'INFO')
    if msg: state.add_log_entry(msg, level)
    return jsonify({"success": True})

def _check_audit_idle_timeout():
    """Auto-cancel an audit session that's gone stale.

    A closed tab, browser crash, or server-restart-then-relaunch can
    leave AUDIT_SESSION.active=True with no real user behind the wheel.
    Without this watchdog the audit panel keeps auto-opening on every
    subsequent dashboard load until someone explicitly scans CMD:CANCEL
    or the process restarts. Checked on every /api/logs poll (every 5s
    from the dashboard heartbeat), so the recovery latency is ≤ 5s
    after the timeout window expires.
    """
    if not state.AUDIT_SESSION.get('active'):
        return
    last = float(state.AUDIT_SESSION.get('last_activity_ts') or 0.0)
    if last <= 0:
        # No timestamp at all (legacy session from before this watchdog
        # landed). Plant `now` so the timer starts NOW rather than
        # auto-cancelling immediately.
        state.AUDIT_SESSION['last_activity_ts'] = time.time()
        return
    if (time.time() - last) > state.AUDIT_IDLE_TIMEOUT_SECONDS:
        loc = state.AUDIT_SESSION.get('location_id') or ''
        state.add_log_entry(
            f"🕒 Audit auto-cancelled after "
            f"{state.AUDIT_IDLE_TIMEOUT_SECONDS // 60} min of inactivity"
            + (f" (was on {loc})" if loc else "")
            + " — no spools moved.",
            "WARNING", "ffaa00",
        )
        state.reset_audit()


@app.route('/api/logs', methods=['GET'])
def api_get_logs_route():
    # Cheap pre-flight: clear any abandoned audit session before the
    # frontend sees audit_active=True and auto-opens the panel.
    _check_audit_idle_timeout()
    sm_url, _ = config_loader.get_api_urls()
    sm_ok = False
    try: sm_ok = requests.get(f"{sm_url}/api/v1/health", timeout=3).ok
    except: pass

    return jsonify({
        "logs": state.RECENT_LOGS,
        "undo_available": len(state.UNDO_STACK) > 0,
        "audit_active": state.AUDIT_SESSION.get('active', False),
        "status": {"spoolman": sm_ok}
    })


# ---------------------------------------------------------------------------
# L206 — Aggregated dashboard heartbeat
#
# startSmartSync used to fan out to ~6 separate endpoints every 5s
# (logs, locations, get_contents for an open manage modal, spools/refresh,
# printer_map + N x toolhead_slots + M x get_contents for printer status).
# At peak ~15 requests per heartbeat — the load that pushed L28 over the
# socket-buffer edge on 2026-05-18.
#
# This endpoint replaces that fan-out with a single bulk call. Callers
# specify which sections they need via `?include=logs,locations,...`,
# the backend assembles them in parallel via a ThreadPoolExecutor, and
# the frontend dispatches each section to its existing renderer. Net
# effect: ~12 requests/5s -> 1 request/5s, same data, lower overhead.
# ---------------------------------------------------------------------------

_VALID_PULSE_SECTIONS = frozenset({
    'logs', 'status', 'locations', 'buffer', 'manage', 'printer_status'
})


def _pulse_section_logs():
    """Invoke the /api/logs handler and unwrap its JSON. Preserves the
    audit-idle-watchdog side effect because the bulk endpoint REPLACES the
    legacy heartbeat that used to drive it - losing it would silently break
    audit cancellation."""
    resp = api_get_logs_route()
    return resp.get_json()


def _pulse_section_locations():
    """Invoke the /api/locations handler and unwrap. Handles the 500
    locations-corrupt path by returning {'error': ...} so the caller
    can decide how to surface it; the bulk endpoint as a whole still
    returns 200 since other sections may have valid data."""
    rv = api_get_locations()
    if isinstance(rv, tuple):
        resp, status = rv[0], rv[1]
        return {'error': resp.get_json(), 'status': status}
    return rv.get_json()


def _pulse_section_manage(loc_id):
    """Mirror of /api/get_contents for one location."""
    return {
        'id': loc_id,
        'contents': spoolman_api.get_spools_at_location_detailed(loc_id),
    }


# ---------------------------------------------------------------------------
# Cancelled-print detection — rides the dashboard-pulse printer-state probe
# (FilaBridge absorption design §9.3 / build slice 2a).
#
# _pulse_section_printer_status already probes every printer's PrusaLink state
# on each heartbeat. We piggyback on that probe: while a print is IN PROGRESS we
# latch its filename / job_id / monotonic byte-progress (PrusaLink tears the job
# block down the instant the print STOPS, so we MUST capture it beforehand),
# and on the →STOPPED/ERROR edge we fire deduct_cancelled_print with the latched
# values on a background thread. The persistent print_deduct_ledger keeps the
# deduct exactly-once across ticks and restarts.
#
# First ship is cancel-only (STOPPED/ERROR). FINISHED stays with FilaBridge
# until the Phase-2 atomic cutover — firing on FINISHED here would
# double-deduct prints FilaBridge already deducts.
# ---------------------------------------------------------------------------

# {printer_name: {"state": str, "job_id", "filename", "progress", "file_meta"}}
_PRINT_TRACKER = {}
_PRINT_TRACKER_LOCK = threading.Lock()

# A print is "running" (so we latch the job) in any of these states — a pause is
# still running. Mirrors the frontend Phase-0 _PRINT_INPROGRESS_STATES.
_INPROGRESS_PRINT_STATES = frozenset({"PRINTING", "PAUSING", "RESUMING", "PAUSED"})
# 22.3(b): a mid-print PAUSE/ATTENTION condition that a resume (→PRINTING) follows.
# An M600 / "Color Change" / filament runout parks the printer at ATTENTION (on
# /api/v1/status); a user pause shows PAUSED; RESUMING is the brief resume
# transient. When the SAME (already-snapshotted) job re-enters PRINTING from one
# of these, the loaded spool MAY have been swapped — that's the swap-event hook
# that captures the ordered swap_log for per-segment apportionment. A resume from
# any of these is a safe over-trigger (a no-op when the mapping didn't change).
_PAUSED_CONDITION_STATES = frozenset({"PAUSED", "PAUSING", "RESUMING", "ATTENTION"})
# Terminal states that, reached FROM an in-progress state, mean a CANCEL/abort.
# Cancel terminal states (reached FROM in-progress = a CANCEL/abort). This set
# ALSO doubles as the "file still download-locked, don't fetch yet" gate in
# _process_pending_cancel_fetches — do NOT add FINISHED here (it would break the
# retry queue); completions use the separate set below.
_CANCEL_TERMINAL_STATES = frozenset({"STOPPED", "ERROR"})

# Phase-2 cutover: COMPLETION terminal state. Kept SEPARATE from the cancel set
# (above) precisely because that one is reused as a lock gate. A FINISHED edge
# fires FCC's own completion deduct ONLY when the fcc_owns_completion_deduct flag
# is on — otherwise FilaBridge still owns completions and firing here would
# double-deduct. (Default off → this code ships DARK; flip it the same moment the
# FilaBridge container is stopped.)
_COMPLETE_TERMINAL_STATES = frozenset({"FINISHED"})

# Idle / ready states reached FROM an in-progress state WITHOUT our ever sampling
# the terminal STOPPED or FINISHED. This is the AMBIGUOUS edge (2026-06-13): a
# fast cancel→restart that slipped the poll, or a PRINTING→offline→IDLE printer
# power-cycle. We can't tell a cancel from a completion, so we NEVER auto-deduct
# — but we must NOT silently drop it either; it routes to the cancel-REVIEW
# pipeline flagged "couldn't confirm" with the retained progress as the hint.
# Deliberately an ALLOW-LIST (not "everything non-terminal") so a mid-print
# ATTENTION/BUSY (filament runout / heating) can NEVER masquerade as an
# end-of-print idle and fire a spurious review. The real fleet reports v1 "IDLE"
# / "READY"; "OPERATIONAL" covers legacy /api/printer firmware idle text.
_IDLE_READY_STATES = frozenset({"IDLE", "READY", "OPERATIONAL"})

# Tests flip this to False so the deduct runs synchronously + deterministically
# instead of on a daemon thread.
_CANCEL_DEDUCT_RUN_ASYNC = True


def _fcc_owns_completion_deduct():
    """The Phase-2 cutover flag (default False → FilaBridge owns completions, this
    code stays dark). Only consulted on an actual in-progress→FINISHED edge."""
    try:
        return bool(config_loader.load_config().get("fcc_owns_completion_deduct", False))
    except Exception:
        return False


def _on_cancel_edge(printer_name, filename, job_id, progress, fb_url):
    """Action taken when a cancel edge is detected. SLICE 5: compute the partial
    and stash it for preview-and-confirm (§9.7) — Derek reviews/nudges before it
    writes (automating the manual Connect-reading he does today). The detector
    reaches this only through _dispatch_cancel_edge, so the threading contract
    (off the heartbeat thread) is unchanged from slice 2a."""
    # INSTANT ACK (2026-06-13): log the moment the STOPPED edge fires, BEFORE the
    # slow async gcode download+decode. On a slow XL .bgcode download the review
    # line is 30-60s out; without this the user faces silence and thinks nothing
    # happened. INFO (no toast spam) — the actual review line below raises the
    # "🛑 Review" affordance.
    try:
        pct = max(0.0, min(1.0, float(progress or 0.0))) * 100
        state.add_log_entry(
            f"🛑 Cancel detected on {printer_name} (~{pct:.0f}%) — computing the partial…",
            "INFO")
    except Exception:
        pass
    try:
        _create_pending_cancel_review(printer_name, filename, job_id, progress, fb_url=fb_url)
    except Exception as e:
        try:
            state.add_log_entry(
                f"❌ Cancelled-print review failed for {printer_name} "
                f"('{filename}'): {e}", "ERROR", "ff4444")
        except Exception:
            pass


def _dispatch_cancel_edge(printer_name, filename, job_id, progress, fb_url):
    """Run the cancel-edge action OFF the heartbeat thread, so a slow gcode
    download never stalls the pulse. Synchronous when _CANCEL_DEDUCT_RUN_ASYNC
    is False (tests)."""
    if _CANCEL_DEDUCT_RUN_ASYNC:
        threading.Thread(
            target=_on_cancel_edge,
            args=(printer_name, filename, job_id, progress, fb_url),
            daemon=True).start()
    else:
        _on_cancel_edge(printer_name, filename, job_id, progress, fb_url)


def _on_completion_edge(printer_name, filename, job_id, fb_url, start_spools=None,
                        swap_log=None):
    """Action on a →FINISHED edge (Phase-2, flag-gated): compute + AUTO-APPLY the
    completion deduct from the slicer footer. No preview/confirm — the grams are
    exact for a completion. `start_spools` (22.3) is the print-start snapshot and
    `swap_log` (22.3(b)) the ordered mid-print swap history, both for spool-swap
    detection. Reaches here only through _dispatch_completion_edge so the
    off-heartbeat threading contract matches the cancel path."""
    try:
        deduct_completed_print(printer_name, filename, job_id, fb_url=fb_url,
                               start_spools=start_spools, swap_log=swap_log)
    except Exception as e:
        try:
            state.add_log_entry(
                f"❌ Completed-print deduct failed for {printer_name} "
                f"('{filename}'): {e}", "ERROR", "ff4444")
        except Exception:
            pass


def _dispatch_completion_edge(printer_name, filename, job_id, fb_url, start_spools=None,
                              swap_log=None):
    """Run the completion-edge action OFF the heartbeat thread (mirrors
    _dispatch_cancel_edge). Synchronous when _CANCEL_DEDUCT_RUN_ASYNC is False
    (tests)."""
    if _CANCEL_DEDUCT_RUN_ASYNC:
        threading.Thread(
            target=_on_completion_edge,
            args=(printer_name, filename, job_id, fb_url),
            kwargs={"start_spools": start_spools, "swap_log": swap_log},
            daemon=True).start()
    else:
        _on_completion_edge(printer_name, filename, job_id, fb_url,
                            start_spools=start_spools, swap_log=swap_log)


def _on_ambiguous_edge(printer_name, filename, job_id, progress, fb_url,
                       progress_unknown=False):
    """Action when a latched in-progress job reaches IDLE/READY WITHOUT our ever
    sampling the terminal STOPPED or FINISHED (2026-06-13): a fast cancel→restart
    that slipped the poll, or a PRINTING→offline→IDLE printer power-cycle. We
    can't tell a cancel from a completion, so route it to the cancel-REVIEW
    pipeline flagged ambiguous (compute the partial at the RETAINED progress as
    the confidence hint) — NEVER auto-deduct (that's FilaBridge's cancel
    over-deduct bug). Reaches here only through _dispatch_ambiguous_edge so the
    off-heartbeat threading contract matches the cancel/completion paths.

    progress_unknown=True (the back-to-back job change): we never sampled a real
    progress for this job, so its usage is unmeasurable — _create_pending_cancel_
    review short-circuits to a non-destructive "weigh the spool" review rather than
    computing a misleading 0g at 0%."""
    # Instant ack (the ambiguous analogue of the cancel instant-ack), so the user
    # isn't met with silence during the async download.
    try:
        if progress_unknown:
            state.add_log_entry(
                f"❓ Print on {printer_name} ('{filename}') was replaced before its "
                f"progress could be measured — surfacing a review (couldn't measure "
                f"usage)…", "INFO")
        else:
            pct = max(0.0, min(1.0, float(progress or 0.0))) * 100
            state.add_log_entry(
                f"❓ Print on {printer_name} reached idle without a clear cancel/finish "
                f"signal (~{pct:.0f}% reached) — computing a review (couldn't confirm "
                f"completed vs cancelled)…", "INFO")
    except Exception:
        pass
    try:
        _create_pending_cancel_review(printer_name, filename, job_id, progress,
                                      fb_url=fb_url, ambiguous=True,
                                      progress_unknown=progress_unknown)
    except Exception as e:
        try:
            state.add_log_entry(
                f"❌ Ambiguous-print review failed for {printer_name} "
                f"('{filename}'): {e}", "ERROR", "ff4444")
        except Exception:
            pass


def _dispatch_ambiguous_edge(printer_name, filename, job_id, progress, fb_url,
                             progress_unknown=False):
    """Run the ambiguous-edge action OFF the heartbeat thread (mirrors
    _dispatch_cancel_edge). Synchronous when _CANCEL_DEDUCT_RUN_ASYNC is False
    (tests)."""
    if _CANCEL_DEDUCT_RUN_ASYNC:
        threading.Thread(
            target=_on_ambiguous_edge,
            args=(printer_name, filename, job_id, progress, fb_url),
            kwargs={"progress_unknown": progress_unknown},
            daemon=True).start()
    else:
        _on_ambiguous_edge(printer_name, filename, job_id, progress, fb_url,
                           progress_unknown=progress_unknown)


def _track_print_edge(printer_name, state_info, fb_url):
    """Latch the active job while printing; fire the cancelled-print partial
    deduct on the →STOPPED/ERROR edge. Called once per printer per heartbeat
    from fetch_for_printer (best-effort — the caller wraps it so a failure never
    breaks the Printer Status widget). See the section header for the full
    rationale.

    `state_info is None` (offline/unreachable) is NOT treated as an edge — we
    leave any existing latch intact so a real STOPPED reached across a transient
    offline blip still deducts with the pre-blip latch.
    """
    if state_info is None:
        return
    cur = str(state_info.get('state', '')).upper()
    if not cur:
        # An empty state string can't happen from _probe_printer_state (it
        # returns None or a non-empty state), so this only guards a malformed
        # dict. Treat it like offline: don't update the latch, so a real
        # terminal state on the next poll still detects the edge.
        return

    if cur in _INPROGRESS_PRINT_STATES:
        # Latch the live job — the network call stays OUTSIDE the lock so a slow
        # printer doesn't serialize the other printers' tracker updates.
        job = None
        try:
            job = prusalink_api.get_printer_job(fb_url, printer_name)
        except Exception:
            job = None
        job_changed = None
        prev_job = None  # outgoing job's latched details, for the ambiguous review
        need_snapshot = False  # 22.3: flag a once-per-job start-spool snapshot
        snap_jid = None
        need_swap_snapshot = False  # 22.3(b): flag a resume-edge mid-print swap capture
        swap_jid = None
        swap_progress = None
        with _PRINT_TRACKER_LOCK:
            entry = _PRINT_TRACKER.setdefault(printer_name, {})
            prev_state = entry.get('state')  # 22.3(b): pre-overwrite, for resume detection
            entry['state'] = cur
            if job:
                # Reject blank/zero ids (None/''/'0'/0) — same "blank job" set
                # print_deduct_ledger keys on, so the tracker and the ledger
                # agree on what can't be deduped restart-safely.
                new_jid = job.get('job_id')
                new_jid = new_jid if new_jid not in (None, '', '0', 0) else None
                old_jid = entry.get('job_id')
                # A different (valid) job_id while still in-progress means a NEW
                # print started without us sampling the previous one's terminal
                # state (cancel→reslice→restart faster than the poll, a missed
                # STOPPED, or a Connect auto-queue where the previous job COMPLETED
                # and the next one auto-started inside a single tick). Reset the
                # stale latch so the new job does NOT inherit the old progress
                # high-water (which would over-state its %, then over-deduct on its
                # own cancel) — but FIRST capture the outgoing job so we can route
                # it to the AMBIGUOUS REVIEW (the same "couldn't confirm cancel vs
                # complete" path the live active→IDLE edge uses). This used to be
                # logged INFO-only, which silently dropped a completed-then-requeued
                # job's deduct — the one true silent-loss path (2026-06-13). It
                # NEVER auto-deducts, and a reslice cancelled before extrusion folds
                # to no_usage in the compute (no review line), so this doesn't spam
                # reviews for normal cancel→reslice churn.
                if new_jid is not None and old_jid not in (None, '') and str(new_jid) != str(old_jid):
                    job_changed = (old_jid, new_jid)
                    if entry.get('filename'):
                        prev_job = {
                            'filename': entry.get('filename'),
                            'job_id': old_jid,
                            'progress': float(entry.get('progress', 0.0)),
                            # `progress` is set (5854-ish) only from a REAL job sample,
                            # so its presence tells us whether we ever measured this
                            # job's progress. Absent ⇒ replaced before any sample ⇒
                            # its usage is unmeasurable (route to a progress_unknown
                            # review, not a misleading 0g — the 1053 silent-loss bug).
                            'progress_sampled': 'progress' in entry,
                        }
                    entry.pop('progress', None)
                    entry.pop('filename', None)
                    entry.pop('file_meta', None)
                    # 22.3: drop the previous job's start-spool snapshot so the new
                    # job re-captures its OWN start mapping (the snapshot_job!=jid
                    # guard below would catch it anyway, but pop defensively so a
                    # replacement job can never inherit the old start spools).
                    entry.pop('start_spools', None)
                    entry.pop('snapshot_job', None)
                    # 22.3(b): and its mid-print swap history — a replacement job must
                    # never inherit the old job's swap_log (it's keyed to snapshot_job).
                    entry.pop('swap_log', None)
                if job.get('filename'):
                    entry['filename'] = job['filename']
                if new_jid is not None:
                    entry['job_id'] = new_jid
                # file_meta (the slicer's per-tool 'filament used' estimate) is
                # latched for slice 5's preview UX, which shows the estimate
                # alongside the computed partial without re-fetching the job.
                if job.get('file_meta'):
                    entry['file_meta'] = job['file_meta']
                prog = job.get('progress')
                if isinstance(prog, (int, float)):
                    entry['progress'] = max(float(entry.get('progress', 0.0)), float(prog))
                # 22.3: flag a once-per-job start-spool snapshot — ONLY on a true
                # PRINTING tick (a job first SEEN mid-pause/runout must not capture the
                # post-swap mapping as 'start'). The snapshot_job!=jid clause makes it
                # fire exactly once per job; the Spoolman read happens AFTER the lock.
                if (cur == 'PRINTING' and new_jid is not None
                        and entry.get('snapshot_job') != str(new_jid)):
                    need_snapshot = True
                    snap_jid = new_jid
                # 22.3(b): a resume INTO printing from a pause/ATTENTION condition on
                # the SAME, already-snapshotted job → a mid-print spool swap MAY have
                # happened (M600 / Color-Change / runout, with an FCC eject/load at the
                # pause). Flag an off-lock snapshot to diff the mapping. Mutually
                # exclusive with the START snapshot above (that fires when snapshot_job
                # != jid; this requires ==), so it can't fire on the job's first
                # PRINTING tick nor after a job change (which popped snapshot_job).
                elif (cur == 'PRINTING' and new_jid is not None
                        and prev_state in _PAUSED_CONDITION_STATES
                        and entry.get('snapshot_job') == str(new_jid)):
                    need_swap_snapshot = True
                    swap_jid = new_jid
                    # The progress high-water at the resume ≈ where this segment ended
                    # (the print resumes from the pause point). Recorded as a COARSE HINT
                    # only — it can read slightly high (a PAUSED pause re-samples progress;
                    # an ATTENTION/M600 park doesn't) so the deferred per-segment math will
                    # take the authoritative cut from the gcode `;COLOR_CHANGE` byte
                    # boundary (parse_color_change_segments), not this %.
                    swap_progress = float(entry.get('progress', 0.0))
        # 22.3 (off-lock, like get_printer_job): capture the start-spool snapshot for
        # mid-print swap detection. ONLY when FCC owns completions — deduct_completed_print
        # is the sole consumer, so it's dead weight (and a wasted Spoolman read) on
        # cancel-only prints. _snapshot_active_spools is best-effort ({} on failure), so a
        # blip leaves start_spools unset and the completion degrades to today's auto-apply.
        if need_snapshot and _fcc_owns_completion_deduct():
            snap = _snapshot_active_spools(printer_name, fb_url)
            with _PRINT_TRACKER_LOCK:
                e = _PRINT_TRACKER.get(printer_name)
                # Store only if (a) the read returned something — an empty {} means a
                # transient Spoolman blip (or a genuinely empty fleet), so DON'T flag
                # snapshot_job, leaving the once-per-job guard open to retry on the
                # next PRINTING tick rather than permanently disabling detection for
                # this job; and (b) the SAME job is still latched (a fast job change
                # during the off-lock read would otherwise mis-key the snapshot).
                if snap and e is not None and str(e.get('job_id')) == str(snap_jid):
                    e['start_spools'] = {str(k): v for k, v in snap.items()}
                    e['snapshot_job'] = str(snap_jid)
        # 22.3(b) (off-lock, like the start snapshot): a resume from a pause/ATTENTION
        # MAY mean the loaded spool was swapped. Snapshot the live mapping and diff it
        # against the mapping in effect for the segment just printed (start_spools +
        # any prior swaps) — each clean 1→1 sid change appends an ordered swap_log
        # event. Best-effort: an empty/failed snapshot just skips (retries next resume).
        # Same flag gate + same-job re-check as the start snapshot. This release-then-
        # re-acquire is safe because _track_print_edge has a SINGLE sequential caller
        # (the _cancel_monitor daemon's per-printer loop) — the job_id re-check guards a
        # fast job change, not a concurrent same-job writer (none exists). If this is ever
        # re-attached to the dashboard pulse (it historically was), revisit the locking.
        if need_swap_snapshot and _fcc_owns_completion_deduct():
            snap = _snapshot_active_spools(printer_name, fb_url)
            if snap:
                with _PRINT_TRACKER_LOCK:
                    e = _PRINT_TRACKER.get(printer_name)
                    if e is not None and str(e.get('job_id')) == str(swap_jid):
                        _record_swap_events(e, snap, swap_progress)
        if prev_job:
            # Surface the outgoing job as an ambiguous review (off-heartbeat,
            # idempotent via the (printer, job_id) ledger + review store) instead of
            # silently dropping it. Never auto-deducts. When we never measured the
            # outgoing job's progress (replaced before any sample), flag it
            # progress_unknown so the review is a non-destructive "weigh the spool"
            # prompt instead of a misleading 0g computed at 0% (the 1053 bug).
            progress_unknown = not prev_job.get('progress_sampled', False)
            try:
                detail = ("without measuring its progress — surfacing a review to weigh"
                          if progress_unknown else
                          "without a sampled end state — reviewing the previous job "
                          "(couldn't confirm completed vs cancelled)")
                state.add_log_entry(
                    f"❓ {printer_name}: print job changed ({job_changed[0]}→{job_changed[1]}) "
                    f"{detail}.", "INFO")
            except Exception:
                pass
            _dispatch_ambiguous_edge(printer_name, prev_job['filename'],
                                     prev_job['job_id'], prev_job['progress'], fb_url,
                                     progress_unknown=progress_unknown)
        elif job_changed:
            # job_changed but nothing was latched to review (the previous job_id had
            # no PRINTING sample → no filename). Preserve the original INFO log.
            try:
                state.add_log_entry(
                    f"ℹ️ {printer_name}: print job changed ({job_changed[0]}→{job_changed[1]}) "
                    f"without a sampled end state; previous job not auto-deducted.", "INFO")
            except Exception:
                pass
        return

    # Non-in-progress state: detect a CANCEL, a (Phase-2) COMPLETION, or an
    # AMBIGUOUS-idle edge against the latched prev state.
    fire = None
    cancel_without_latch = False
    with _PRINT_TRACKER_LOCK:
        entry = _PRINT_TRACKER.get(printer_name)
        prev = entry.get('state') if entry else None
        # `prev_active` = the printer was mid-something (a job in flight), NOT
        # already idle/ready and NOT a clean terminal we already handled. This is
        # BROADER than _INPROGRESS_PRINT_STATES (the LATCH set) on purpose: a
        # filament runout / M600 parks the printer at ATTENTION, and a hard reset
        # / power-cycle can surface BUSY on the way back up — neither is
        # "in-progress" for latching, but a print that ENDS from them (ATTENTION→
        # IDLE on a hard reset, ATTENTION→STOPPED on a cancel-from-the-prompt) is
        # still a real edge that today would be silently dropped (2026-06-13,
        # Derek's live Core One at ATTENTION 91%). A resolved cancel/complete
        # resets the latch (clearing `filename`), and prev is guarded against
        # idle/terminal here, so neither a bare idle→idle nor a second terminal
        # tick can re-fire — and the latch branch only ever sets `filename` during
        # a real printing state, so pre-print heating (IDLE→BUSY→IDLE) never has a
        # filename to fire on.
        prev_active = (prev is not None
                       and prev not in _IDLE_READY_STATES
                       and prev not in _CANCEL_TERMINAL_STATES
                       and prev not in _COMPLETE_TERMINAL_STATES)
        # Cancel = active → STOPPED/ERROR (always owned by FCC).
        is_cancel_edge = prev_active and cur in _CANCEL_TERMINAL_STATES
        # Completion = active → FINISHED, but ONLY when the cutover flag is on
        # (else FilaBridge still owns completions → firing here double-deducts).
        # `_COMPLETE_TERMINAL_STATES` is deliberately SEPARATE from the cancel set
        # (which doubles as the fetch lock-gate). Short-circuit AND so the config
        # read happens only on an actual active→FINISHED transition.
        is_complete_edge = (prev_active and cur in _COMPLETE_TERMINAL_STATES
                            and _fcc_owns_completion_deduct())
        # Ambiguous = active → IDLE/READY WITHOUT our ever sampling the terminal
        # STOPPED or FINISHED (2026-06-13): a fast cancel→restart that slipped the
        # poll, a PRINTING→offline→IDLE power-cycle, or a hard reset out of the
        # ATTENTION filament-prompt (prev=ATTENTION/BUSY → IDLE). We can't tell
        # cancel from completion, so route it to the REVIEW pipeline flagged
        # "couldn't confirm" — NEVER auto-deduct. Fires regardless of the cutover
        # flag (it's a safe review, not a write; the proven prod signature
        # `{state:IDLE, job_id:693, progress:0.26}` was captured pre-cutover, and
        # visibility beats a silent drop). A clean completion FCC actually
        # observed (PRINTING→FINISHED→…) is NOT ambiguous (prev=FINISHED is a
        # handled terminal → prev_active False), so this can't spam reviews for
        # normal prints; only a genuinely-missed terminal triggers it.
        is_ambiguous_edge = prev_active and cur in _IDLE_READY_STATES
        if is_cancel_edge:
            edge_kind = 'cancel'
        elif is_complete_edge:
            edge_kind = 'complete'
        elif is_ambiguous_edge:
            edge_kind = 'ambiguous'
        else:
            edge_kind = None
        if edge_kind and entry and entry.get('filename'):
            fire = {
                'kind': edge_kind,
                'filename': entry.get('filename'),
                'job_id': entry.get('job_id', ''),
                'progress': float(entry.get('progress', 0.0)),
                # Whether we ever sampled a REAL progress for this job (entry sets
                # 'progress' only from a job sample). Absent ⇒ a latched-but-unsampled
                # job (e.g. caught at ATTENTION before any PRINTING tick) → route the
                # ambiguous edge to a non-destructive progress_unknown review instead
                # of computing a misleading 0% partial (22.4(6); mirrors the
                # job-changed path's progress_sampled check).
                'progress_sampled': 'progress' in entry,
                # 22.3: the print-start spool snapshot rides the fire dict to the
                # completion handler (the latch is reset right below, so the entry's
                # copy is gone). _validated_start_spools re-checks snapshot_job==job_id.
                'start_spools': entry.get('start_spools'),
                'snapshot_job': entry.get('snapshot_job'),
                # 22.3(b): the ordered mid-print swap history rides along too (same
                # snapshot_job guard via _validated_swap_log).
                'swap_log': entry.get('swap_log'),
            }
            # Reset the latch to the terminal state so the edge can't re-fire.
            _PRINT_TRACKER[printer_name] = {'state': cur}
        else:
            if is_cancel_edge:
                cancel_without_latch = True
            if entry is not None:
                entry['state'] = cur
            else:
                _PRINT_TRACKER[printer_name] = {'state': cur}

    if cancel_without_latch:
        state.add_log_entry(
            f"🛑 Cancel detected on {printer_name}, but no active job was latched "
            f"(print too short to sample between heartbeats) — no partial deduct.",
            "INFO")
    if fire:
        if fire['kind'] == 'complete':
            _dispatch_completion_edge(
                printer_name, fire['filename'], fire['job_id'], fb_url,
                start_spools=_validated_start_spools(fire, fire['job_id']),
                swap_log=_validated_swap_log(fire, fire['job_id']))
        elif fire['kind'] == 'ambiguous':
            _dispatch_ambiguous_edge(
                printer_name, fire['filename'], fire['job_id'], fire['progress'],
                fb_url, progress_unknown=not fire.get('progress_sampled', False))
        else:
            _dispatch_cancel_edge(printer_name, fire['filename'], fire['job_id'],
                                  fire['progress'], fb_url)


# ---------------------------------------------------------------------------
# Cancelled-print monitor — a dedicated server-side poller, INDEPENDENT of the
# dashboard pulse (Derek 2026-06-11). Detection must NOT depend on a browser
# having the dashboard open or focused: an unattended print is the common case,
# and FCC usually isn't in focus. So _track_print_edge no longer rides
# _pulse_section_printer_status; this daemon probes every printer on a fixed
# ~30s tick regardless of UI state. The frontend pulse still probes state for
# the widget, and its Phase-0 fast-poll burst still snaps the displayed weight
# after a deduct — but it's no longer load-bearing for catching cancels.
# ---------------------------------------------------------------------------

# ADAPTIVE poll cadence (2026-06-13, Derek wants the monitor more responsive).
# Poll FAST while anything is happening on the fleet, back off to the slow rate
# when every printer is idle. The cancel/poll-miss gap (a fast cancel→restart
# that slips a slow tick) closes the most by sampling often WHILE a print runs,
# so we can catch the STOPPED edge before the screen is cleared. Perf is fine:
# each state probe is ~30ms, runs in parallel with a bounded timeout, and the
# costly bgcode download fires only on an EDGE, never per tick — so a 10s tick
# doesn't hammer Buddy's tiny HTTP pool. "Busy" = any printer in-progress OR
# sitting on a terminal screen (STOPPED/ERROR/FINISHED), so the whole
# print→clear lifecycle (incl. waiting out the deferred-fetch lock) stays
# responsive; the fleet idles down to the slow rate only when truly nothing's up.
_CANCEL_MONITOR_FAST_S = 10
_CANCEL_MONITOR_IDLE_S = 30
# How long to keep retrying a deferred fetch before giving up (§9.10). The
# cancelled file stays download-LOCKED until Derek clears the cancel screen on
# the printer; he's usually at the printer, but this buffers a cancel-and-walk-
# away (e.g. over a weekend). Retrying is nearly free — it only hits the network
# once the printer leaves STOPPED — so the window is generous.
_CANCEL_FETCH_MAX_AGE_S = 72 * 3600
_cancel_monitor_started = False
_cancel_monitor_lock = threading.Lock()


def _cancel_monitor_tick():
    """One detection sweep: probe every printer's state + run the latch/edge
    detector, then service the deferred-fetch retry queue (§9.10) using the
    states just probed. Per-printer probes fan out so a slow/offline printer
    doesn't block the rest. Best-effort throughout.

    Returns True when the fleet is BUSY (any printer in-progress or on a terminal
    screen) so the loop can poll on the FAST cadence; False when everything is
    idle/offline (back off to the slow cadence). The return is the only signal
    the adaptive loop needs — it never raises."""
    from concurrent.futures import ThreadPoolExecutor
    try:
        printer_map = locations_db.get_active_printer_map()
        _, fb_url = config_loader.get_api_urls()
    except Exception:
        return False
    names = sorted({info.get('printer_name') for info in printer_map.values()
                    if info.get('printer_name')})
    if not names:
        return False

    probed = {}

    def _probe(name):
        try:
            state_info = prusalink_api.get_printer_state(fb_url, name)
        except Exception:
            state_info = None
        probed[name] = state_info  # distinct keys per thread → GIL-safe
        try:
            _track_print_edge(name, state_info, fb_url)
        except Exception as e:
            try:
                state.logger.debug(f"cancel-monitor probe failed for {name}: {e}")
            except Exception:
                pass

    workers = max(1, min(8, len(names)))
    with ThreadPoolExecutor(max_workers=workers) as ex:
        list(ex.map(_probe, names))

    # Prune tracker entries for printers no longer in the map so a removed /
    # renamed printer's stale latch can't linger or mis-fire on re-add.
    with _PRINT_TRACKER_LOCK:
        for stale in [p for p in _PRINT_TRACKER if p not in names]:
            _PRINT_TRACKER.pop(stale, None)
        snapshot = {k: dict(v) for k, v in _PRINT_TRACKER.items()}

    # Slice 7: persist the latch snapshot so an in-flight print survives an FCC /
    # host restart (reconciled on monitor start via _recover_print_tracker_on_
    # start). Best-effort — print_tracker_store.save swallows its own errors.
    print_tracker_store.save(snapshot)

    # Retry any cancels whose gcode was download-locked at the edge (§9.10).
    try:
        _process_pending_cancel_fetches(probed, fb_url)
    except Exception as e:
        try:
            state.logger.debug(f"cancel-fetch retry pass failed: {e}")
        except Exception:
            pass

    # Tell the loop whether to stay FAST: any reachable printer that is NOT
    # idle/ready is "busy" — printing, paused, ATTENTION (filament prompt), BUSY,
    # or sitting on a terminal STOPPED/ERROR/FINISHED screen. Poll fast across
    # that whole window so a cancel→restart is sampled in time and the deferred-
    # fetch lock drains soon after the screen clears. Offline (None/'') and
    # idle/ready → back off to the slow cadence.
    busy = False
    for st in probed.values():
        s = str((st or {}).get('state', '')).upper()
        if s and s not in _IDLE_READY_STATES:
            busy = True
            break
    return busy


def _process_pending_cancel_fetches(states, fb_url):
    """Service the deferred-fetch queue (§9.10): for each cancelled print whose
    gcode couldn't be downloaded at the edge (selected-file LOCK), re-attempt the
    compute ONCE the printer has left STOPPED (the file un-locks → IDLE), then
    stash the 🛑 Review and drop the queue entry. Gives up after
    _CANCEL_FETCH_MAX_AGE_S with a "weigh the spool" warning.

    `states` maps printer_name -> the state dict get_printer_state returned this
    tick (or None when offline). Best-effort per entry; one bad record never
    blocks the rest.
    """
    pendings = cancel_fetch_store.list_pending()
    if not pendings:
        return
    now = time.time()
    for rec in pendings:
        try:
            printer = rec.get("printer_name")
            job_id = rec.get("job_id")
            filename = rec.get("filename")
            progress = float(rec.get("progress", 0.0) or 0.0)
            kind = rec.get("kind", "cancel")  # 'cancel' (review) | 'complete' (auto-apply)
            ambiguous = bool(rec.get("ambiguous", False))  # cancel-review "couldn't confirm" flag
            start_spools = rec.get("start_spools")  # 22.3: carried for the deferred completion swap check
            swap_log = rec.get("swap_log")  # 22.3(b): ordered mid-print swap history
            if not printer or job_id in (None, ""):
                cancel_fetch_store.pop_pending(printer, job_id)
                continue

            # Resolved elsewhere (confirmed/dismissed, or a review already
            # stashed) → drop the queue entry. Keeps "ledger/review ⟹ no fetch".
            if (print_deduct_ledger.was_deducted(printer, job_id)
                    or cancel_review_store.has_pending(printer, job_id)):
                cancel_fetch_store.pop_pending(printer, job_id)
                continue

            # Give up after the max-age window so a deleted/abandoned file's
            # entry can't linger forever. Record grams=0 so it can't re-queue.
            first_seen = float(rec.get("first_seen", now) or now)
            if now - first_seen > _CANCEL_FETCH_MAX_AGE_S:
                pct = max(0.0, min(1.0, progress)) * 100
                hrs = _CANCEL_FETCH_MAX_AGE_S // 3600
                if kind == "complete":
                    state.add_log_entry(
                        f"✅ Gave up fetching the completed print's gcode on {printer} "
                        f"('{filename}') after {hrs}h — no deduct recorded. "
                        f"Weigh the spool to true it up.", "WARNING", "ffaa00")
                else:
                    state.add_log_entry(
                        f"🛑 Gave up fetching the cancelled print's gcode on {printer} "
                        f"('{filename}', ~{pct:.0f}%) after {hrs}h — no partial deduct. "
                        f"Weigh the spool to true it up.", "WARNING", "ffaa00")
                print_deduct_ledger.record_deduct(printer, job_id, filename=filename,
                                                  scale=progress, grams=0)
                cancel_fetch_store.pop_pending(printer, job_id)
                continue

            # Gate on state: the selected file is reliably download-UNLOCKED only
            # once the printer is genuinely IDLE/READY (the print cleared off the
            # screen). Any other reachable state means it's still busy/locked —
            # PRINTING (new job), the cancel screen (STOPPED/ERROR), the finish
            # screen (FINISHED), an ATTENTION filament-prompt, or a transient BUSY
            # — so wait. Offline (None/'') → wait. (Allow-list, not deny-list, so
            # we never hammer Buddy's tiny HTTP pool retrying a locked file mid-
            # ATTENTION — the live Core One @91% bug, 2026-06-13.)
            st = states.get(printer)
            cur = str((st or {}).get("state", "")).upper() if st else ""
            if cur not in _IDLE_READY_STATES:
                continue

            if kind == "complete":
                # Re-check the flag HERE, not just at the edge: a completion can
                # sit queued behind the finish-screen lock for up to 72h without a
                # ledger record. If the cutover is rolled back in that window (flag
                # OFF + FilaBridge restarted), FilaBridge owns completions again —
                # firing FCC's deduct now would double-bill (the ledger can't span
                # processes). Abandon the queued completion instead.
                if not _fcc_owns_completion_deduct():
                    cancel_fetch_store.pop_pending(printer, job_id)
                    continue
                # start_spools + swap_log (if captured before the finish-screen lock)
                # ride the fetch record so the deferred completion still detects a
                # mid-print spool swap (22.3/22.3(b)); None when not captured → auto-apply.
                result = deduct_completed_print(printer, filename, job_id, fb_url=fb_url,
                                                start_spools=start_spools, swap_log=swap_log)
            else:
                result = _create_pending_cancel_review(
                    printer, filename, job_id, progress, fb_url=fb_url, ambiguous=ambiguous)
            status = (result or {}).get("status")
            if status == "awaiting_fetch":
                # Still couldn't fetch (the file 404'd despite a ready state — a
                # transient, or the file was deleted). Leave queued; the re-queue
                # already bumped attempts. The max-age window bounds the retries.
                continue
            # Any terminal outcome (pending review / pending_unresolved / no_usage /
            # skipped) resolves this entry.
            cancel_fetch_store.pop_pending(printer, job_id)
        except Exception as e:
            try:
                state.logger.debug(f"cancel-fetch retry failed for {rec}: {e}")
            except Exception:
                pass


def _recover_print_tracker_on_start():
    """Slice 7 — power-loss latch persistence. On monitor start, reconcile the
    persisted in-flight latch against each printer's CURRENT state so a cancel
    that happened (or a print that was running) during an FCC / host restart
    isn't silently lost. Resolution table (persisted = was in-progress + a
    latched job):

        now PRINTING, SAME job_id  → it resumed: restore the latch
        now PRINTING, DIFFERENT job → old outcome unknown: warn (manual), latch new
        now STOPPED / ERROR        → cancel/failure: fire the deduct at persisted %
        now FINISHED               → completed: leave to FilaBridge (no deduct)
        now IDLE / READY           → cleared during outage, ambiguous: warn (manual)
        offline (unreachable)      → restore the latch, defer to normal detection
        (no latched job)           → seed the baseline state only

    Idempotent: _dispatch_cancel_edge dedups via the (printer, job_id) ledger +
    review store, so a double restart can't double-deduct."""
    persisted = print_tracker_store.load()
    if not persisted:
        return
    try:
        _, fb_url = config_loader.get_api_urls()
    except Exception:
        fb_url = None
    recovered = 0
    for name, entry in list(persisted.items()):
        try:
            if _recover_one_print_latch(name, entry, fb_url):
                recovered += 1
        except Exception as e:
            try:
                state.logger.debug(f"print-latch recovery failed for {name}: {e}")
            except Exception:
                pass
    if recovered:
        try:
            state.logger.info(
                f"🛑 Reconciled {recovered} persisted print latch(es) after restart.")
        except Exception:
            pass


def _recover_one_print_latch(name, entry, fb_url):
    """Reconcile one persisted latch (see _recover_print_tracker_on_start for the
    table). Returns True if it acted, False for a no-op (bare entry / completion)."""
    job_id = entry.get('job_id')
    filename = entry.get('filename')
    progress = float(entry.get('progress', 0.0) or 0.0)
    # Whether a REAL progress was ever sampled for this latched job (the latch sets
    # 'progress' only from a job sample; print_tracker_store round-trips it verbatim).
    # Absent ⇒ unsampled → the ambiguous-idle branch routes to a non-destructive
    # progress_unknown review instead of recovering at a misleading 0% (22.4(6)).
    progress_sampled = 'progress' in entry
    if not (job_id and filename):
        # No latched job (a bare terminal/idle snapshot) — nothing to recover;
        # seed the baseline state so the first edge-detect has a `prev`.
        with _PRINT_TRACKER_LOCK:
            _PRINT_TRACKER[name] = {'state': str(entry.get('state', '')).upper()}
        return False

    cur_info = prusalink_api.get_printer_state(fb_url, name) if fb_url else None
    cur = str((cur_info or {}).get('state', '')).upper() if cur_info else None
    pct = max(0.0, min(1.0, progress)) * 100

    # Offline on restart → can't resolve; restore the latch and let normal
    # edge-detection handle it when the printer is reachable again (mirrors the
    # in-tick "offline preserves the latch" rule).
    if cur is None:
        with _PRINT_TRACKER_LOCK:
            _PRINT_TRACKER[name] = dict(entry)
        return True

    if cur in _INPROGRESS_PRINT_STATES:
        job = prusalink_api.get_printer_job(fb_url, name) or {}
        cur_jid = job.get('job_id')
        cur_jid = cur_jid if cur_jid not in (None, '', '0', 0) else None
        if cur_jid is not None and str(cur_jid) == str(job_id):
            # Same job still running → it RESUMED. Restore the latch (incl. the
            # progress high-water) so normal detection continues from here.
            with _PRINT_TRACKER_LOCK:
                _PRINT_TRACKER[name] = dict(entry)
            return True
        # A DIFFERENT job is printing → the old one ended during the outage and
        # we can't tell cancel from completion → manual review; latch the new job.
        state.add_log_entry(
            f"⚠️ {name}: a print ('{filename}', ~{pct:.0f}%) was in progress when FCC "
            f"restarted and a different job is printing now — its outcome is unknown, "
            f"not auto-deducted. Weigh the spool if that print was cancelled.",
            "WARNING", "ffaa00")
        with _PRINT_TRACKER_LOCK:
            _PRINT_TRACKER[name] = {
                'state': cur, 'job_id': cur_jid, 'filename': job.get('filename'),
                'progress': float(job.get('progress') or 0.0),
                'file_meta': job.get('file_meta') or {}}
        return True

    if cur in _CANCEL_TERMINAL_STATES:
        # Did NOT resume — still STOPPED/ERROR → a real cancel/failure. Fire the
        # deduct from the persisted progress (Derek's "resolve from last pull
        # status if it doesn't resume").
        state.add_log_entry(
            f"🛑 Recovering a cancel missed during an FCC restart on {name} "
            f"('{filename}', ~{pct:.0f}%) — printer still {cur}.", "WARNING", "ffaa00")
        _dispatch_cancel_edge(name, filename, job_id, progress, fb_url)
        with _PRINT_TRACKER_LOCK:
            _PRINT_TRACKER[name] = {'state': cur}
        return True

    if cur == "FINISHED":
        if _fcc_owns_completion_deduct():
            # Phase-2: FCC owns completions → recover the completion deduct missed
            # during the restart. Still FINISHED = unambiguous (a completion, not a
            # cleared-then-reprinted job). Idempotent via the (printer, job_id)
            # ledger, so a double restart can't double-deduct.
            state.add_log_entry(
                f"✅ Recovering a completion missed during an FCC restart on {name} "
                f"('{filename}') — printer still FINISHED.", "INFO")
            # 22.3: the persisted entry round-trips start_spools/snapshot_job/swap_log,
            # so a restart AFTER the snapshot was captured still detects a mid-print
            # swap; a restart BEFORE capture has no snapshot → None → auto-apply.
            _dispatch_completion_edge(name, filename, job_id, fb_url,
                                      start_spools=_validated_start_spools(entry, job_id),
                                      swap_log=_validated_swap_log(entry, job_id))
            with _PRINT_TRACKER_LOCK:
                _PRINT_TRACKER[name] = {'state': cur}
            return True
        # Flag off → FilaBridge still owns completions → no deduct.
        with _PRINT_TRACKER_LOCK:
            _PRINT_TRACKER[name] = {'state': cur}
        return False

    if cur in _IDLE_READY_STATES:
        # in-progress → cleared during the outage. Can't tell a cancelled-then-
        # cleared print from a completed-then-cleared one → route it to the
        # AMBIGUOUS REVIEW (download the now-unlocked file, compute the partial at
        # the persisted progress, surface "couldn't confirm") instead of only
        # telling Derek to weigh. Same machinery + wording as the live ambiguous
        # edge; idempotent via the (printer, job_id) ledger + review store, so a
        # double restart can't double-surface. NEVER auto-deducts.
        state.add_log_entry(
            f"❓ A print ('{filename}', ~{pct:.0f}%) was in progress on {name} when FCC "
            f"restarted and it's now {cur or 'idle'} — surfacing a review (couldn't "
            f"confirm completed vs cancelled).", "WARNING", "ffaa00")
        _dispatch_ambiguous_edge(name, filename, job_id, progress, fb_url,
                                 progress_unknown=not progress_sampled)
        with _PRINT_TRACKER_LOCK:
            _PRINT_TRACKER[name] = {'state': cur}
        return True

    # Any OTHER state (ATTENTION filament-prompt, BUSY, or an unknown transient) =
    # the print is still mid-something, NOT ended. Restore the latch and defer to
    # live edge-detection (mirrors the offline case) — the live monitor fires the
    # cancel/ambiguous/completion edge when it actually reaches a terminal/idle.
    with _PRINT_TRACKER_LOCK:
        _PRINT_TRACKER[name] = dict(entry)
    return True


def _cancel_monitor_loop():
    # Slice 7: reconcile the persisted in-flight latch BEFORE the first tick so a
    # cancel missed during an FCC/host restart is recovered (or surfaced) up front.
    try:
        _recover_print_tracker_on_start()
    except Exception as e:
        try:
            state.logger.warning(f"print-latch recovery pass failed: {e}")
        except Exception:
            pass
    while True:
        busy = False
        try:
            busy = _cancel_monitor_tick()
        except Exception as e:
            try:
                state.logger.warning(f"cancel-monitor tick error: {e}")
            except Exception:
                pass
        # Adaptive cadence: fast while the fleet is busy, slow when idle.
        time.sleep(_CANCEL_MONITOR_FAST_S if busy else _CANCEL_MONITOR_IDLE_S)


def _seed_printer_credentials_from_filabridge():
    """FilaBridge Phase-2 cutover — credential gate. ONE-TIME, prime-only seed:
    relocate each printer's ip_address + api_key OFF FilaBridge `GET /printers`
    and ONTO its first-class Type:"Printer" row (printer_creds field), so the
    whole PrusaLink read path (state/job/MMU probe, cancel-deduct download) stops
    depending on FilaBridge being up. Pulls /printers ONLY when a Printer row is
    still missing creds, and never overwrites a row that already has them (a
    Settings edit wins). Idempotent — once every row has creds (or FilaBridge is
    gone) it does nothing. Lives in the SERVING-process launch path (not module
    import) because it makes a network call; mirrors the Phase-3/4 migrations'
    load→migrate→backup→save shape. Best-effort: never blocks startup."""
    try:
        _cred_locs = locations_db.load_locations_list()
    except Exception as _e:
        state.logger.warning(f"printer-creds seed: could not load locations: {_e}")
        return
    _needs_seed = any(
        isinstance(r, dict)
        and str(r.get('Type', '')).strip().lower() == 'printer'
        and not (isinstance(r.get(locations_db.PRINTER_CREDS_KEY), dict)
                 and str((r.get(locations_db.PRINTER_CREDS_KEY) or {}).get('ip_address', '') or '').strip())
        for r in (_cred_locs or [])
    )
    if not _needs_seed:
        return
    try:
        _, _cred_fb_url = config_loader.get_api_urls()
        _fb_printers = prusalink_api.fetch_all_filabridge_printers(_cred_fb_url)
    except Exception as _e:
        state.logger.warning(f"printer-creds seed: FilaBridge pull failed: {_e}")
        return
    if not _fb_printers:
        state.logger.info(
            "🔐 Printer-creds seed: FilaBridge /printers unreachable or empty; "
            "will retry next boot (rows still missing creds).")
        return
    _cred_migrated, _cred_changed = locations_db.seed_printer_credentials(
        _cred_locs, _fb_printers, prime_only=True)
    if not _cred_changed:
        return
    try:
        import shutil, time as _t
        _stamp = _t.strftime('%Y%m%d-%H%M%S')
        _backup = f"{locations_db.JSON_FILE}.pre-printer-creds-seed-{_stamp}.bak"
        shutil.copy2(locations_db.JSON_FILE, _backup)
        state.logger.info(f"📦 Backed up locations.json → {_backup}")
        _prune_locations_backups()
    except Exception as _bk_err:
        state.logger.warning(f"Could not write pre-printer-creds-seed backup: {_bk_err}")
    if locations_db.save_locations_list(_cred_migrated):
        state.logger.info(
            "🔐 Seeded printer credentials from FilaBridge onto Printer rows — "
            "FilaBridge Phase-2 credential gate primed (FCC now reaches PrusaLink "
            "without FilaBridge).")
    else:
        state.logger.error(
            "❌ Printer-creds seed save FAILED — locations.json left unchanged; "
            "will retry next boot.")


def _start_cancel_monitor():
    """Start the cancel-monitor daemon thread once per process. Called from the
    __main__ launch path only (never on a bare import, so tests don't spawn it).
    Idempotent."""
    global _cancel_monitor_started
    with _cancel_monitor_lock:
        if _cancel_monitor_started:
            return
        _cancel_monitor_started = True
    threading.Thread(target=_cancel_monitor_loop, name="cancel-monitor",
                     daemon=True).start()
    try:
        state.logger.info(
            f"🛑 Cancelled-print monitor started (adaptive poll: "
            f"{_CANCEL_MONITOR_FAST_S}s busy / {_CANCEL_MONITOR_IDLE_S}s idle, "
            f"dashboard-independent).")
    except Exception:
        pass


def _pulse_section_printer_status():
    """Server-side aggregator for the Printer Status widget. Replaces
    the client-side fan-out of printer_map + N x toolhead_slots +
    M x get_contents fetches with one server-side call. Toolhead
    occupancy for ALL toolheads is resolved in a single Spoolman fetch
    via `bucket_spools_by_location`; the per-printer work (bindings +
    PrusaLink state probe) then runs in its own thread (capped at 8) so
    a slow/offline printer doesn't serially block the rest.

    Occupancy keys off the toolhead LOCATION (the spool's own
    `location` / `physical_source`), NOT dryer-box `slot_targets`, so a
    dryer-box-less / direct-fed printer (Derek's Core One) shows the
    spool actually loaded on each toolhead. `unbound` is a pure binding
    hint (no dryer box feeds this toolhead) used only for the widget's
    "🔗 no bound slot" affordance — it never gates contents. (FilaBridge
    auto-deduct is likewise toolhead-driven, not box-mediated, so a
    direct-fed spool's weight still ticks after a print.)

    L56: each printer's payload also carries a `state` dict pulled
    directly from PrusaLink (`prusalink_api.get_printer_state`), which
    has no binding dependency. `state` is None when the printer is
    offline or unreachable so the widget can show an offline indicator.
    """
    from concurrent.futures import ThreadPoolExecutor

    cfg = config_loader.load_config()
    printer_map = locations_db.get_active_printer_map()  # L271 P4 step 2: Printer-row toolheads[] (dual-read)
    _, fb_url = config_loader.get_api_urls()
    grouped = {}
    for loc_id, info in printer_map.items():
        name = info.get('printer_name', 'Unknown')
        grouped.setdefault(name, []).append({
            'location_id': str(loc_id).upper(),
            'position': info.get('position', 0),
        })
    for entries in grouped.values():
        entries.sort(key=lambda e: (e['position'], e['location_id']))

    if not grouped:
        return {}

    # Box-bounding fix: a toolhead's `item` (the spool physically loaded on
    # it) must reflect ACTUAL occupancy at the toolhead location, NOT whether
    # a dryer box happens to feed it. Previously the contents lookup was gated
    # behind `is_bound` (a pure dryer-box slot_targets flag), so a directly-fed
    # toolhead with no bound box — e.g. Core One run dryer-box-less — showed
    # empty even with a spool loaded. We now bucket every printer_map toolhead's
    # occupancy in ONE Spoolman fetch (instead of one per bound toolhead, which
    # was both wrong AND an N-fetch fan-out) and keep `unbound` as a binding-only
    # display hint. Occupancy matches get_spools_at_location_detailed exactly
    # (direct location + physical_source ghost).
    all_tids = [str(loc_id).upper() for loc_id in printer_map.keys()]
    spools_by_tid = spoolman_api.bucket_spools_by_location(all_tids)

    def fetch_for_printer(item):
        name, entries = item
        bindings_result = locations_db.get_bindings_for_machine(name, printer_map)
        bindings = bindings_result.get('toolheads', {})
        toolheads = []
        for entry in entries:
            tid = entry['location_id']
            is_bound = bool(bindings.get(tid, []))
            contents = spools_by_tid.get(tid, [])
            item_data = contents[0] if contents else None
            toolheads.append({
                'id': tid,
                'position': entry['position'],
                'item': item_data,
                'unbound': not is_bound,
            })
        toolheads.sort(key=lambda t: (t['position'], t['id']))
        # Direct PrusaLink probe — runs regardless of dryer-box bindings,
        # so the widget ticks for dryer-box-less printers (L56). NOTE: cancel
        # DETECTION no longer rides this probe — it runs in the dashboard-
        # independent _cancel_monitor daemon (so an unattended print with FCC
        # unfocused/closed is still caught). This probe is widget-display only.
        try:
            state_info = prusalink_api.get_printer_state(fb_url, name)
        except Exception:
            state_info = None
        return name, {'toolheads': toolheads, 'state': state_info}

    out = {}
    max_workers = max(1, min(8, len(grouped)))
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        for name, payload in ex.map(fetch_for_printer, grouped.items()):
            out[name] = payload
    return out


@app.route('/api/dashboard_pulse', methods=['GET', 'POST'])
def api_dashboard_pulse():
    """Aggregated heartbeat - see L206 docstring block above.

    Query params:
      include   comma-separated section names. Valid: logs, status,
                locations, buffer, manage, printer_status. Unknown
                names are silently ignored (forward-compat).
      manage_id required when 'manage' is in include - the LocationID
                whose contents to fetch.
    Body (POST): {"refresh_spool_ids": [123, 124, ...]} - if present
                and non-empty, the response includes a "spools_refresh"
                section keyed by spool id, equivalent to a POST to
                /api/spools/refresh.

    Returns: {section_name: payload, ...}. Sections that error
    individually return {"error": "..."} in their slot; the response
    as a whole stays 200 so a partial failure doesn't blank the
    dashboard.
    """
    raw_include = (request.args.get('include') or '').strip()
    requested = set(s.strip().lower() for s in raw_include.split(',') if s.strip())
    include = requested & _VALID_PULSE_SECTIONS
    manage_id = (request.args.get('manage_id') or '').strip().upper()

    refresh_spool_ids = []
    if request.method == 'POST' and request.is_json:
        body = request.get_json(silent=True) or {}
        refresh_spool_ids = body.get('refresh_spool_ids') or []
        if not isinstance(refresh_spool_ids, list):
            refresh_spool_ids = []

    out = {}

    # logs and status share the underlying Spoolman+FilaBridge health
    # check, so we invoke the handler at most once per request.
    if 'logs' in include or 'status' in include:
        try:
            logs_payload = _pulse_section_logs()
        except Exception as e:
            logs_payload = {'error': str(e)}
        if 'logs' in include:
            out['logs'] = logs_payload
        if 'status' in include and isinstance(logs_payload, dict) and 'status' in logs_payload:
            out['status'] = {
                'spoolman': logs_payload['status'].get('spoolman', False),
                'audit_active': logs_payload.get('audit_active', False),
                'undo_available': logs_payload.get('undo_available', False),
            }

    if 'locations' in include:
        try:
            out['locations'] = _pulse_section_locations()
        except Exception as e:
            out['locations'] = {'error': str(e)}

    if 'buffer' in include:
        out['buffer'] = state.GLOBAL_BUFFER

    if 'manage' in include and manage_id:
        try:
            out['manage'] = _pulse_section_manage(manage_id)
        except Exception as e:
            out['manage'] = {'error': str(e), 'id': manage_id}

    if 'printer_status' in include:
        try:
            out['printer_status'] = _pulse_section_printer_status()
        except Exception as e:
            out['printer_status'] = {'error': str(e)}

    if refresh_spool_ids:
        try:
            out['spools_refresh'] = logic.get_live_spools_data(refresh_spool_ids)
        except Exception as e:
            out['spools_refresh'] = {'error': str(e)}

    return jsonify(out)


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
        _seed_printer_credentials_from_filabridge()
        _start_cancel_monitor()
    app.run(host='0.0.0.0', port=8000, use_reloader=_dev, debug=False)