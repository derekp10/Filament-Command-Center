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

# --- INVENTORY WIZARD ---
@app.route('/api/external/vendors', methods=['GET'])
def api_external_vendors():
    """Proxy route to fetch Spoolman vendors for the Wizard dropdowns."""
    vendors = spoolman_api.get_vendors()
    return jsonify({"success": True, "vendors": vendors})

@app.route('/api/vendors', methods=['GET'])
def api_vendors():
    """Returns a list of all vendors in Spoolman."""
    try:
        return jsonify({"success": True, "vendors": spoolman_api.get_vendors()})
    except Exception as e:
        return jsonify({"success": False, "msg": str(e)}), 500


@app.route('/api/create_filament', methods=['POST'])
def api_create_filament():
    """Create a new filament in Spoolman. Body: {"data": {...filament fields...}}.

    Used by the Edit Filament modal's "Add" mode (when openAddFilamentForm is
    called with no existing filament). Returns {success, filament|msg}.
    Mirrors api_update_filament's shape so the frontend can share response
    handling.
    """
    payload = request.json or {}
    data = payload.get('data') or {}
    if not isinstance(data, dict) or not data:
        return jsonify({"success": False, "msg": "No fields to create with."}), 400
    if not data.get('material'):
        return jsonify({"success": False, "msg": "Material is required."}), 400
    try:
        created = spoolman_api.create_filament(data)
        if created and created.get('id') is not None:
            state.add_log_entry(
                f"➕ Filament #{created['id']} created ({data.get('material', '')}: {data.get('name', '')})",
                "SUCCESS", "00ff00",
            )
            return jsonify({"success": True, "filament": created})
        return jsonify({"success": False, "msg": "Spoolman rejected the filament create."}), 500
    except Exception as e:
        state.logger.error(f"Failed to create filament: {e}")
        return jsonify({"success": False, "msg": str(e)}), 500


@app.route('/api/vendors', methods=['POST'])
def api_create_vendor():
    """Create a vendor in Spoolman.

    Two accepted body shapes for back-compat with the Edit Filament inline
    "+ Create vendor" affordance, which still sends `{name: "..."}`:
      - `{"name": "..."}` — legacy short form, name-only create
      - `{"data": {...vendor fields and/or extra...}}` — full-form payload
        from the Vendor Edit modal's create mode (Group 6.2 cleanup).

    Returns {success, vendor}. Activity log records the create.
    """
    payload = request.json or {}
    # Resolve the data dict from either shape.
    if isinstance(payload.get('data'), dict):
        data = dict(payload['data'])
    else:
        data = {"name": str(payload.get('name') or '').strip()}
    name = str(data.get('name') or '').strip()
    if not name:
        return jsonify({"success": False, "msg": "Vendor name required."}), 400
    data['name'] = name
    try:
        created = spoolman_api.create_vendor(data)
        if created and created.get('id') is not None:
            state.add_log_entry(f"➕ Vendor '{name}' created", "SUCCESS", "00ff00")
            return jsonify({"success": True, "vendor": created})
        # Surface Spoolman's rejection body when create_vendor returned None.
        err = spoolman_api.LAST_SPOOLMAN_ERROR or "Spoolman rejected the vendor create."
        return jsonify({"success": False, "msg": err}), 500
    except Exception as e:
        state.logger.error(f"Failed to create vendor '{name}': {e}")
        return jsonify({"success": False, "msg": str(e)}), 500


def _format_vendor_edit_log(vid, before, data):
    """Build a per-field before→after activity log line for a vendor edit.
    Mirrors `_format_filament_edit_log` so the Vendor Edit modal save path
    leaves the same kind of audit trail (user can see what value the field
    actually changed from/to, not just which keys were dirty)."""
    parts = []
    before = before or {}
    before_extra = before.get('extra') or {}
    for key, value in (data or {}).items():
        if key == 'extra':
            for ek, ev in (value or {}).items():
                old = before_extra.get(ek, '')
                if spoolman_api._is_delete_sentinel(ev):
                    # 23.4 — blank-to-clear, not a literal sentinel write.
                    parts.append(f"extra.{ek}: {old or '(empty)'} → (cleared)")
                elif str(old) != str(ev):
                    parts.append(f"extra.{ek}: {old or '(empty)'} → {ev or '(empty)'}")
            continue
        old = before.get(key, '')
        if str(old) != str(value):
            parts.append(f"{key}: {old or '(empty)'} → {value or '(empty)'}")
    if not parts:
        return f"✏️ Vendor #{vid} edited (no fields)"
    return f"✏️ Vendor #{vid} edited — " + " · ".join(parts)


@app.route('/api/vendors/<int:vid>', methods=['PATCH'])
def api_update_vendor(vid):
    """Edit a vendor in Spoolman. Body: {"data": {...vendor fields and/or extra...}}.

    Backs the Manufacturer/Vendor Edit modal V1 (Group 6 — Edit Modal new
    panels). Uses update_vendor_or_raise on the high-stakes user-driven
    save path so silent failure can't strand the user without a signal.
    Surfaces the actual Spoolman rejection body in the response so the
    modal can toast it at 7s duration per the activity-log + toast contract.

    Vendor has no system-managed extras today (SYSTEM_MANAGED_EXTRAS is
    spool-only), so compute_dirty_extras isn't needed here — but the
    `extra` payload is still merged with the existing record inside
    update_vendor() so partial PATCHes preserve sibling extras.
    """
    payload = request.json or {}
    data = payload.get('data') or {}
    if not isinstance(data, dict) or not data:
        return jsonify({"success": False, "msg": "No fields to update."}), 400
    before = spoolman_api.get_vendor(vid) or {}
    try:
        updated = spoolman_api.update_vendor_or_raise(vid, data)
        state.add_log_entry(
            _format_vendor_edit_log(vid, before, data),
            "SUCCESS", "00ff00",
        )
        return jsonify({"success": True, "vendor": updated})
    except spoolman_api.SpoolmanRejection as e:
        err = str(e) or "Spoolman rejected the vendor edit."
        state.add_log_entry(
            f"❌ Vendor #{vid} edit rejected — {err}",
            "ERROR", "ff4444",
        )
        return jsonify({"success": False, "msg": err}), 400
    except Exception as e:
        state.logger.error(f"Failed to update vendor #{vid}: {e}")
        return jsonify({"success": False, "msg": str(e)}), 500

@app.route('/api/materials', methods=['GET'])
def api_materials():
    """Returns a list of all unique materials in Spoolman."""
    try:
        return jsonify({"success": True, "materials": spoolman_api.get_materials()})
    except Exception as e:
        return jsonify({"success": False, "msg": str(e)}), 500

@app.route('/api/filaments', methods=['GET'])
def api_filaments():
    """Proxy route to fetch Spoolman filaments, preventing CORS on port mismatch."""
    sm_url, _ = config_loader.get_api_urls()
    try:
        r = requests.get(f"{sm_url}/api/v1/filament", timeout=5)
        if r.ok:
            return jsonify({"success": True, "filaments": r.json()})
    except Exception as e:
        state.logger.error(f"API Error fetching filaments: {e}")
    return jsonify({"success": False, "filaments": []})

@app.route('/api/filaments/<int:filament_id>', methods=['GET'])
def api_get_filament(filament_id):
    """Fetches a specific filament to read its details."""
    try:
        data = spoolman_api.get_filament(filament_id)
        if data:
            return jsonify({"success": True, "data": data})
        return jsonify({"success": False, "msg": "Filament not found"}), 404
    except Exception as e:
        return jsonify({"success": False, "msg": str(e)}), 500

@app.route('/api/spools/<int:spool_id>', methods=['GET'])
def api_get_spool(spool_id):
    """Fetches a specific spool to read its complete filament mapping."""
    try:
        spool = spoolman_api.get_spool(spool_id)
        if spool:
            return jsonify({"success": True, "data": spool})
        return jsonify({"success": False, "msg": "Spool not found"}), 404
    except Exception as e:
        return jsonify({"success": False, "msg": str(e)}), 500

# Canonical presentation order for wizard / details-modal extras.
# Spoolman's /api/v1/field/{entity} response has no `order` key, so the wizard's
# existing sort step (inv_wizard.js — `.sort((a,b) => (a.order||0) - (b.order||0))`)
# was a no-op. Group 10.6 fix: enrich each field dict with an `order` index here.
# Unknown keys sort to the end (FIELD_ORDER_UNKNOWN).
FIELD_ORDER_UNKNOWN = 9999
FIELD_ORDER = {
    "filament": [
        "filament_attributes",
        "shore_hardness",
        "slicer_profile",
        "product_url",
        "purchase_url",
        "sheet_link",
        "price_total",
        "original_color",
        "nozzle_temp_max",
        "bed_temp_max",
        "drying_temp",
        "drying_time",
        "flush_multiplier",
        "multi_color_direction",
        "needs_label_print",
        "sample_printed",
    ],
    "spool": [
        "spool_type",
        "spool_temp",
        "container_slot",
        "physical_source",
        "physical_source_slot",
        "product_url",
        "purchase_url",
        # Prusament-import spool-instance metadata (read-mostly; surfaced
        # via external_parsers on label scan).
        "original_color",
        "nozzle_temp_max",
        "bed_temp_max",
        "prusament_manufacturing_date",
        "prusament_length_m",
        "is_refill",
        "needs_label_print",
        "fcc_pre_archive_location",
    ],
}


def _enrich_field_order(entity_type, fields):
    """Stamp each field dict with `order` per FIELD_ORDER; unknown keys go to the end."""
    order_list = FIELD_ORDER.get(entity_type, [])
    for f in fields or []:
        key = f.get("key")
        f["order"] = order_list.index(key) if key in order_list else FIELD_ORDER_UNKNOWN
    return fields


@app.route('/api/external/fields', methods=['GET'])
def api_external_fields():
    """Proxy route to fetch Spoolman custom Extra fields configuration (e.g. Filament Attributes, Spool Types)."""
    sm_url, _ = config_loader.get_api_urls()
    out = {"filament": [], "spool": []}
    try:
        rf = requests.get(f"{sm_url}/api/v1/field/filament", timeout=5)
        if rf.ok: out["filament"] = _enrich_field_order("filament", rf.json())

        rs = requests.get(f"{sm_url}/api/v1/field/spool", timeout=5)
        if rs.ok: out["spool"] = _enrich_field_order("spool", rs.json())

        return jsonify({"success": True, "fields": out})
    except Exception as e:
        state.logger.error(f"API Error fetching extra fields config: {e}")
    return jsonify({"success": False, "fields": out})

@app.route('/api/spoolman/restore_field_order', methods=['POST'])
def api_spoolman_restore_field_order():
    """L318 — write FIELD_ORDER's canonical index back to each Spoolman
    field's `order` property so Spoolman's own UI renders extras in
    the same order FCC's wizard / details modal do.

    Spoolman's `POST /api/v1/field/{entity}/{key}` is an upsert: the
    POST body must carry the full ExtraFieldParameters payload (name,
    field_type, choices, etc.) — sending only `order` would clobber
    the other properties to their defaults. We GET the current field
    def, splice in the canonical order index, and POST it back, ALWAYS
    echoing every property the GET returned so nothing else changes.

    Idempotent: re-running just writes the same order values; no
    side effects on the actual filament / spool data.

    Query param `dry_run` (default: false) — when `true`/`1`/`yes`,
    the endpoint reports what WOULD change without writing back to
    Spoolman. The UI uses this to preview before committing. The
    `changes` list per entity carries `{key, from_order, to_order}`
    so the user sees exactly which fields move and by how much.
    Derek 2026-05-28: previously tried setting field order once and
    "it got overwritten" — the dry-run preview lets the user verify
    the plan before pressing Apply.
    """
    sm_url, _ = config_loader.get_api_urls()
    dry_run = (request.args.get('dry_run') or '').strip().lower() in ('1', 'true', 'yes', 'on')
    summary = {
        "filament": {"updated": 0, "would_update": 0, "skipped": 0,
                     "changes": [], "errors": []},
        "spool":    {"updated": 0, "would_update": 0, "skipped": 0,
                     "changes": [], "errors": []},
    }

    for entity_type in ("filament", "spool"):
        order_list = FIELD_ORDER.get(entity_type, [])
        try:
            r = requests.get(f"{sm_url}/api/v1/field/{entity_type}", timeout=10)
            if not r.ok:
                summary[entity_type]["errors"].append(f"GET failed: {r.status_code}")
                continue
            fields = r.json() or []
        except Exception as e:
            summary[entity_type]["errors"].append(f"GET error: {e}")
            continue

        for fld in fields:
            key = fld.get("key")
            if not key or key not in order_list:
                summary[entity_type]["skipped"] += 1
                continue
            new_order = order_list.index(key)
            current_order = int(fld.get("order") or 0)
            if current_order == new_order:
                # Already in the right slot — skip the round-trip.
                summary[entity_type]["skipped"] += 1
                continue
            summary[entity_type]["changes"].append({
                "key": key,
                "name": fld.get("name", key),
                "from_order": current_order,
                "to_order": new_order,
            })
            if dry_run:
                summary[entity_type]["would_update"] += 1
                continue
            # Build the upsert payload — preserve every other ExtraFieldParameters
            # property the GET returned. Spoolman POST clobbers omitted fields
            # to schema defaults (e.g. choices→null), so we MUST echo them back.
            # Covers the full schema: name, field_type (required), unit,
            # default_value, choices, multi_choice (nullable).
            payload = {
                "name": fld.get("name", key),
                "field_type": fld.get("field_type", "text"),
                "order": new_order,
            }
            for prop in ("unit", "default_value", "choices", "multi_choice"):
                if prop in fld and fld[prop] is not None:
                    payload[prop] = fld[prop]
            try:
                w = requests.post(
                    f"{sm_url}/api/v1/field/{entity_type}/{key}",
                    json=payload, timeout=10,
                )
                if not w.ok:
                    summary[entity_type]["errors"].append(
                        f"{key}: HTTP {w.status_code} {(w.text or '')[:140]}"
                    )
                    continue
                summary[entity_type]["updated"] += 1
            except Exception as e:
                summary[entity_type]["errors"].append(f"{key}: {e}")

    total_updated = sum(s["updated"] for s in summary.values())
    total_would = sum(s["would_update"] for s in summary.values())
    total_errors = sum(len(s["errors"]) for s in summary.values())
    if dry_run:
        state.add_log_entry(
            f"🔢 Field-order dry-run — {total_would} field(s) would move, {total_errors} error(s)",
            "INFO", "00d4ff",
        )
    elif total_updated or total_errors:
        state.add_log_entry(
            f"🔢 Restored Spoolman field order — {total_updated} updated, {total_errors} error(s)",
            "INFO", "00d4ff",
        )
    return jsonify({
        "success": total_errors == 0,
        "dry_run": dry_run,
        "summary": summary,
    })


@app.route('/api/external/fields/add_choice', methods=['POST'])
def api_external_fields_add_choice():
    """Appends a new choice to a multi-choice field in Spoolman and updates the schema."""
    data = request.json
    entity_type = data.get('entity_type')
    key = data.get('key')
    new_choice = data.get('new_choice')
    
    if not all([entity_type, key, new_choice]):
         return jsonify({"success": False, "msg": "Missing required fields."})
         
    res = spoolman_api.update_extra_field_choices(entity_type, key, [new_choice])
    return jsonify(res)

@app.route('/api/create_inventory_wizard', methods=['POST'])
def api_create_inventory_wizard():
    """Monolithic endpoint to handle creating Filaments and Spools in one shot."""
    data = request.json
    filament_id = data.get('filament_id')
    filament_data = data.get('filament_data')
    spool_data = data.get('spool_data')
    quantity = int(data.get('quantity', 1))
    # Optional per-spool override list. When present, drives the spool count
    # (one created per entry) and merges onto spool_data per index. Used by
    # the per-spool Prusament scan flow in Step 3 of the wizard so each box's
    # actual weight / manufacture date / product URL lands on the right spool.
    spool_overrides = data.get('spool_overrides')

    created_spool_ids = []

    try:
        # Step 1: Resolve Filament
        if not filament_id and filament_data:
            # New filaments auto-flag for label print so they show up in the
            # Backlog immediately. The user's first physical scan of the new
            # FIL:NN label flips it to False (positive verification).
            extra = filament_data.get('extra', {})
            if 'needs_label_print' not in extra:
                extra['needs_label_print'] = True
            filament_data['extra'] = extra

            # Create a brand new filament
            new_fil = spoolman_api.create_filament(filament_data)
            if new_fil and 'id' in new_fil:
                filament_id = new_fil['id']
            else:
                return jsonify({"success": False, "msg": "Failed to create new Filament in Spoolman."})
        
        if not filament_id:
            return jsonify({"success": False, "msg": "Missing Filament ID or valid Filament Data."})

        # Step 2: Create Spool(s)
        if spool_data:
            spool_data['filament_id'] = filament_id

            # New spools auto-flag for label print (same rationale as new
            # filaments above). Set on spool_data so per-spool overrides
            # inherit unless they explicitly override `needs_label_print`.
            sp_extra = spool_data.get('extra')
            if sp_extra is None:
                sp_extra = {}
                spool_data['extra'] = sp_extra
            if 'needs_label_print' not in sp_extra:
                sp_extra['needs_label_print'] = True

            # Group 10.3: explicit default-to-Unassigned. The wizard already
            # sends `location: ''` when the user leaves the combobox blank, but
            # if a future caller drops the field entirely or sends None,
            # fall through to '' so spoolman_api.create_spool's UNASSIGNED-coerce
            # path receives a string rather than letting Spoolman invent state.
            if spool_data.get('location') is None:
                spool_data['location'] = ''

            # Per-spool override list takes precedence over `quantity` when present.
            # Each entry shallow-merges onto spool_data, with `extra` deep-merged
            # so per-spool fields (e.g. prusament_manufacturing_date) don't clobber
            # wizard-wide extras (e.g. needs_label_print).
            if spool_overrides and isinstance(spool_overrides, list):
                spool_iter = spool_overrides
            else:
                spool_iter = [None] * quantity

            for override in spool_iter:
                payload = dict(spool_data)
                if override:
                    base_extra = dict(payload.get('extra') or {})
                    override_extra = override.get('extra') or {}
                    payload.update({k: v for k, v in override.items() if k != 'extra'})
                    if base_extra or override_extra:
                        base_extra.update(override_extra)
                        payload['extra'] = base_extra
                new_spool = spoolman_api.create_spool(payload)
                if new_spool and 'id' in new_spool:
                    created_spool_ids.append(new_spool['id'])
                else:
                    state.logger.error("A spool creation failed during bulk wizard execution.")

            # Surface failure when spool creation was requested but produced
            # zero results — otherwise the wizard reports "Success!" and the
            # user only notices the missing spools much later.
            if len(created_spool_ids) == 0:
                return jsonify({
                    "success": False,
                    "filament_id": filament_id,
                    "created_spools": [],
                    "msg": "Filament was created/found but every spool creation failed. Check Spoolman logs for the rejection reason (e.g. unknown extra field).",
                })

        return jsonify({
            "success": True,
            "filament_id": filament_id,
            "created_spools": created_spool_ids
        })

    except Exception as e:
        state.logger.error(f"Wizard Creation Error: {e}")
        return jsonify({"success": False, "msg": str(e)})


def _log_manual_weight_change(spool_id, pre, post):
    """24.F — write a before➔after Activity-Log breakdown for a MANUAL weight
    adjustment (mirrors the auto-deduct wording at _apply_usage_to_printer).

    Shared by every manual weight funnel — the generic /api/spool/update and
    the wizard edit-spool save — so "all manual weight adjustments display a
    breakdown" holds consistently. Best-effort: a log failure never breaks the
    caller's response. Skips silently when `pre` (the pre-update snapshot) is
    missing — a transient get_spool blip — rather than logging fabricated
    0.0g "before" values. Callers gate on a weight field actually being dirty
    so non-weight edits never reach here. The L200 Prusament correction has its
    own dedicated log and does NOT route through this.
    """
    if not pre:
        return
    try:
        def _wf(d, k):
            v = (d or {}).get(k)
            return float(v) if isinstance(v, (int, float)) else 0.0
        old_rem, new_rem = _wf(pre, 'remaining_weight'), _wf(post, 'remaining_weight')
        old_used, new_used = _wf(pre, 'used_weight'), _wf(post, 'used_weight')
        old_init, new_init = _wf(pre, 'initial_weight'), _wf(post, 'initial_weight')
        total_note = (f"  [total {old_init:.1f}g ➔ {new_init:.1f}g]"
                      if abs(old_init - new_init) >= 0.05 else "")
        color = (spoolman_api.format_spool_display(post) or {}).get('color', '888888')
        state.add_log_entry(
            f"✏️ Weight updated — Spool #{spool_id}: "
            f"[{old_rem:.1f}g ➔ {new_rem:.1f}g remaining] "
            f"(used {old_used:.1f}g ➔ {new_used:.1f}g){total_note}",
            "INFO", color)
    except Exception as _log_e:
        state.logger.warning(f"24.F weight-log skipped for spool {spool_id}: {_log_e}")


@app.route('/api/edit_spool_wizard', methods=['POST'])
def api_edit_spool_wizard():
    """Endpoint to handle natively editing Filaments and Spools from the Wizard Edit UI."""
    data = request.json
    spool_id = data.get('spool_id')
    filament_id = data.get('filament_id')
    filament_data = data.get('filament_data')
    spool_data = data.get('spool_data')

    if not spool_id:
        return jsonify({"success": False, "msg": "Missing Spool ID for edit session."})

    try:
        # Update Spool First
        if spool_data:
            # Prevent 500 errors by only passing actual changes to Spoolman
            original_spool = spoolman_api.get_spool(spool_id)
            if original_spool:
                dirty_spool_data = {}
                for k, v in spool_data.items():
                    if k == 'spool_weight':
                        if v != original_spool.get('spool_weight'):
                            dirty_spool_data['spool_weight'] = v
                    elif k == 'extra':
                        # Diff extra fields via the shared helper. Strips
                        # system-managed keys (container_slot,
                        # physical_source, physical_source_slot) before the
                        # diff so the wizard CANNOT clobber a slotted
                        # spool's toolhead assignment regardless of what
                        # the JS sends — Item 4 fix in Feature-Buglist.
                        original_extra = original_spool.get('extra', {})
                        dirty_extra, stripped = spoolman_api.compute_dirty_extras(
                            original_extra, v,
                            system_managed=spoolman_api.SYSTEM_MANAGED_EXTRAS,
                        )
                        if stripped:
                            state.logger.warning(
                                f"edit_spool_wizard refused to write system-managed extras "
                                f"on spool {spool_id}: {stripped}. Use perform_smart_move / "
                                f"perform_smart_eject for these keys."
                            )
                        if dirty_extra:
                            dirty_spool_data['extra'] = dirty_extra
                    elif k in original_spool and original_spool[k] != v:
                        dirty_spool_data[k] = v
                    elif k not in original_spool:
                         dirty_spool_data[k] = v

                spool_data = dirty_spool_data
                state.logger.info(f"DIRTY SPOOL DATA: {dirty_spool_data}")

            if spool_data:
                spool_res = spoolman_api.update_spool(spool_id, spool_data)
                if not spool_res:
                    err = spoolman_api.LAST_SPOOLMAN_ERROR or "Spoolman rejected the update"
                    return jsonify({
                        "success": False,
                        "msg": f"Failed to update Spool {spool_id}: {err}",
                        "error": err,
                    })
                # 24.F — the wizard edit-spool save is ALSO a manual weight surface.
                # Log the before➔after breakdown when a weight field was dirty
                # (`spool_data` is the dirty diff at this point; `original_spool` is
                # the pre snapshot — None when get_spool blipped, handled by helper).
                if any(k in spool_data for k in ("used_weight", "initial_weight")):
                    _log_manual_weight_change(spool_id, original_spool, spool_res)

        # Update Filament Second (if applicable)
        if filament_id and filament_data:
            fil_res = spoolman_api.update_filament(filament_id, filament_data)
            if not fil_res:
                err = spoolman_api.LAST_SPOOLMAN_ERROR or "Spoolman rejected the update"
                state.logger.warning(f"Failed to cleanly update Filament {filament_id} during spool edit: {err}")
                return jsonify({
                    "success": False,
                    "msg": f"Filament update rejected: {err}",
                    "error": err,
                })

        return jsonify({"success": True, "spool_id": spool_id})

    except Exception as e:
        state.logger.error(f"Wizard Edit Error: {e}")
        return jsonify({"success": False, "msg": str(e)})

@app.route('/api/spool/update', methods=['POST'])
def api_spool_update():
    """Generic endpoint to partially update a spool from frontend modules.

    Also surfaces two post-update flags so the frontend can respond to
    user-visible state transitions:
      - `auto_archived`: True when this call is the one that archived the
        spool (weight-0 auto-archive logic in spoolman_api.update_spool).
      - `needs_empty_weight_prompt`: True when the spool was just archived
        AND its parent filament has no empty_spool_weight recorded. Triggers
        the Archive Empty-Weight modal on the frontend.
    """
    try:
        data = request.json
        spool_id = data.get('id')
        updates = data.get('updates')

        if not spool_id or not updates:
            return jsonify({"status": "error", "msg": "Missing id or updates"})

        pre = spoolman_api.get_spool(spool_id) or {}
        pre_archived = bool(pre.get('archived', False))

        res = spoolman_api.update_spool(spool_id, updates)
        if not res:
            err = spoolman_api.LAST_SPOOLMAN_ERROR or "Spoolman rejected the update"
            return jsonify({"status": "error", "msg": f"Failed to update spool: {err}", "error": err})

        # 24.F — Manual weight adjustments leave a before➔after breakdown in the
        # Activity Log. Fire ONLY when a weight field was actually requested so
        # location/extra-only edits don't spam the log. `pre` is the pre-update
        # snapshot fetched above; `res` is the live post-update spool dict (Spoolman
        # may have clamped used_weight ≤ initial, so post values come from `res`).
        # Shared with the wizard edit-spool save via _log_manual_weight_change.
        if any(k in updates for k in ("used_weight", "initial_weight", "remaining_weight")):
            _log_manual_weight_change(spool_id, pre, res)

        post_archived = bool(res.get('archived', False))
        auto_archived = (not pre_archived) and post_archived
        needs_prompt = False
        filament_id = None
        if auto_archived:
            fil = res.get('filament') or {}
            filament_id = fil.get('id')
            fil_weight = fil.get('spool_weight')
            vendor_weight = (fil.get('vendor') or {}).get('empty_spool_weight')
            # A filament is "missing empty spool weight" when both its own value
            # and its vendor's fallback are null/0 — matches the frontend
            # resolveEmptySpoolWeight chain so we don't prompt pointlessly.
            def _missing(v):
                return v is None or (isinstance(v, (int, float)) and v <= 0)
            needs_prompt = _missing(fil_weight) and _missing(vendor_weight)

        return jsonify({
            "status": "success",
            "auto_archived": auto_archived,
            "needs_empty_weight_prompt": needs_prompt,
            "filament_id": filament_id,
        })
    except Exception as e:
        state.logger.error(f"Spool Update Error: {e}")
        return jsonify({"status": "error", "msg": str(e)})


@app.route('/api/spool/prusament_apply_weights', methods=['POST'])
def api_prusament_apply_weights():
    """L200 confirm-apply for a Prusament-scan spool-weight correction.

    Re-validates against the LIVE spool (the scan-time diff can be minutes stale
    and FilaBridge may auto-deduct in between) so a correction can NEVER:
      - resurrect an archived spool, or
      - drive remaining to <= 0 and trip update_spool's auto-archive-on-empty
        (which would silently unassign a loaded spool + clear its slot bindings).
    Writes ONLY initial_weight / spool_weight; used_weight is preserved so the
    consumption history is untouched. High-stakes -> update_spool_or_raise.
    """
    try:
        data = request.json or {}
        sid = data.get('spool_id') or data.get('id')
        req = data.get('updates') or {}
        if not sid:
            return jsonify({"status": "error", "msg": "Missing spool_id"})

        live = spoolman_api.get_spool(sid)
        if not live:
            return jsonify({"status": "error", "msg": f"Spool #{sid} not found"})
        if live.get('archived'):
            return jsonify({
                "status": "blocked",
                "msg": "Spool is archived — not changing its weights "
                       "(that would return it to active inventory).",
            })

        live_used = _pm_num(live.get('used_weight')) or 0.0
        updates = {}
        new_initial = _pm_num(req.get('initial_weight'))
        new_tare = _pm_num(req.get('spool_weight'))
        if new_initial is not None and new_initial > 0:
            # Hard floor against the live used — never let a correction zero out
            # and auto-archive a still-loaded spool.
            if new_initial <= live_used + _PM_WEIGHT_TOL:
                return jsonify({
                    "status": "blocked",
                    "msg": f"Total {new_initial:g}g would leave ~0g against the "
                           f"{live_used:g}g already used — not applied "
                           f"(it would archive/unassign the spool).",
                })
            updates['initial_weight'] = new_initial
        if new_tare is not None and new_tare > 0:
            updates['spool_weight'] = new_tare
        if not updates:
            return jsonify({"status": "noop", "msg": "Nothing to update"})

        try:
            spoolman_api.update_spool_or_raise(sid, updates)
        except spoolman_api.SpoolmanRejection as e:
            state.add_log_entry(
                f"❌ Prusament weight apply failed for spool #{sid}: {e}",
                "ERROR", "ff4444",
            )
            return jsonify({"status": "error", "msg": str(e)})

        summary = ", ".join(f"{k}={v:g}" for k, v in updates.items())
        state.add_log_entry(
            f"📦 Updated spool #{sid} weights from Prusament scan ({summary})",
            "SUCCESS", "00ff00",
        )
        return jsonify({"status": "success", "updates": updates})
    except Exception as e:
        state.logger.error(f"Prusament weight apply error: {e}")
        return jsonify({"status": "error", "msg": str(e)})


import external_parsers # Added for plugin architecture


@app.route('/api/external/search', methods=['GET'])
def api_external_search():
    """
    Extensible handler for pulling template parameters from external databases.
    Powered by `external_parsers.py` Plugins.
    """
    source = request.args.get('source', 'spoolman')
    query = request.args.get('q', '').strip()
    
    try:
        results = external_parsers.search_external(source, query)
        return jsonify({"success": True, "source": source, "results": results})
    except ValueError as e:
        state.logger.warning(f"External API Router Error: {e}")
        return jsonify({"success": False, "msg": str(e)})
    except Exception as e:
        state.logger.error(f"External Search Handler Error: {e}")
        return jsonify({"success": False, "msg": f"An error occurred pulling data: {e}"})

@app.route('/api/search', methods=['GET'])
def api_search_inventory():
    """
    Search endpoint for finding spools based on fuzzy queries, attributes, and colors.
    Used by the new global Offcanvas search component.
    """
    query = request.args.get('q', '')
    material = request.args.get('material', '')
    vendor = request.args.get('vendor', '')
    color_hex = request.args.get('hex', '')
    
    only_in_stock = request.args.get('in_stock', 'false').lower() == 'true'
    empty = request.args.get('empty', 'false').lower() == 'true'
    min_weight = request.args.get('min_weight', '')
    max_weight = request.args.get('max_weight', '')
    target_type = request.args.get('type', 'spool')
    # Deployment status filter: '' | 'any' = no filter, 'deployed' = toolhead/ghost only,
    # 'undeployed' = not on a toolhead. Filaments ignore this.
    deployed_state = request.args.get('deployed', '').strip().lower()
    # Sort axis. Currently filament-only: 'spools_desc' / 'spools_asc'.
    # Empty / unknown tokens fall through to the default sort path.
    sort = request.args.get('sort', '').strip().lower()

    try:
        results = spoolman_api.search_inventory(
            query=query,
            material=material,
            vendor=vendor,
            color_hex=color_hex,
            only_in_stock=only_in_stock,
            empty=empty,
            target_type=target_type,
            min_weight=min_weight,
            max_weight=max_weight,
            deployed_state=deployed_state,
            sort=sort,
        )
        return jsonify({"success": True, "results": results})
    except Exception as e:
        state.logger.error(f"API Search Error: {e}")
        return jsonify({"success": False, "msg": str(e)})

# ... (Imports same as before) ...

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

def _format_filament_edit_log(fid, before, requested):
    """Build a Filament-edit activity-log line that shows actual before→after
    values per field — both native and extras — so the user has a real
    audit trail rather than just a list of keys.

    `before` is the pre-patch full filament dict (from get_filament).
    `requested` is the partial-update payload the wizard/edit form sent —
    the authoritative source for the "new value" since Spoolman's PATCH
    response doesn't always echo every field.

    Always emits an `old → new` entry for each requested field even when
    they appear equal — the user explicitly asked for these to be visible
    so a no-op PATCH still tells the story (rather than collapsing into
    a bare key list with no values, which the user reported as unhelpful)."""
    parts = []

    def _short(v):
        if v is None or v == "":
            return "∅"
        if isinstance(v, list):
            return "[" + ", ".join(str(x) for x in v) + "]"
        s = str(v)
        return s if len(s) <= 60 else s[:57] + "…"

    before_extra = (before.get('extra') if isinstance(before, dict) else {}) or {}

    for key in sorted(requested.keys()):
        if key == 'extra':
            ex_req = requested.get('extra') or {}
            for ek in sorted(ex_req.keys()):
                old = before_extra.get(ek)
                new = ex_req.get(ek)
                if spoolman_api._is_delete_sentinel(new):
                    # 23.4 — render a blank-to-clear as a real deletion rather
                    # than leaking the internal delete-sentinel token.
                    parts.append(f"extra.{ek}: {_short(old)} → (cleared)")
                elif old == new:
                    parts.append(f"extra.{ek}: {_short(old)} (unchanged)")
                else:
                    parts.append(f"extra.{ek}: {_short(old)} → {_short(new)}")
            continue
        old = before.get(key) if isinstance(before, dict) else None
        new = requested.get(key)
        if old == new:
            parts.append(f"{key}: {_short(old)} (unchanged)")
        else:
            parts.append(f"{key}: {_short(old)} → {_short(new)}")

    if not parts:
        return f"✏️ Filament #{fid} edited (no fields)"
    return f"✏️ Filament #{fid} edited — " + " · ".join(parts)


@app.route('/api/update_filament', methods=['POST'])
def api_update_filament():
    """Direct filament-level edit hook for the Edit Filament button on the
    Filament Details modal. Accepts {id, data} where `data` is any subset of
    Spoolman filament fields (name, material, vendor_id, spool_weight,
    density, color_hex, settings_extruder_temp, settings_bed_temp, comment,
    extra, archived, etc.). Returns {success, filament|msg}.

    Deliberately thinner than /api/edit_spool_wizard — no spool coupling,
    no cross-inherit logic — since this endpoint's sole caller is the
    filament-only edit flow.
    """
    payload = request.json or {}
    fid = payload.get('id')
    data = payload.get('data') or {}
    if not fid:
        return jsonify({"success": False, "msg": "Missing filament id."})
    if not isinstance(data, dict) or not data:
        return jsonify({"success": False, "msg": "No fields to update."})
    # Snapshot the existing record BEFORE the update so the activity-log
    # entry can show concrete before→after values per field. Older code
    # only logged which keys changed, leaving the user with no audit
    # trail of what the value actually went from/to.
    before = spoolman_api.get_filament(fid) or {}
    try:
        updated = spoolman_api.update_filament(fid, data)
        if updated:
            state.add_log_entry(
                _format_filament_edit_log(fid, before, data),
                "SUCCESS", "00ff00",
            )
            return jsonify({"success": True, "filament": updated})
        # Surface the stashed Spoolman error body so the UI can tell the user
        # WHY the update was rejected (invalid field, bad vendor_id, etc.)
        # instead of showing an opaque "rejected" message.
        err = spoolman_api.LAST_SPOOLMAN_ERROR or "No response body"
        return jsonify({"success": False, "msg": f"Spoolman rejected update: {err}"})
    except Exception as e:
        state.logger.error(f"Failed to update filament #{fid}: {e}")
        return jsonify({"success": False, "msg": str(e)})

@app.route('/api/manage_contents', methods=['POST'])
def api_manage_contents():
    data = request.json
    action = data.get('action')
    loc_id = data.get('location', '').strip().upper()
    spool_input = data.get('spool_id')
    slot_arg = data.get('slot')
    # Caller opts into the active-print-confirmed branch by passing this
    # flag alongside the main payload. Added 2026-04-23 so ejects, force-
    # unassigns, and clear-location ops all inherit the same safety net.
    confirm_active_print = bool(data.get('confirm_active_print', False))

    if action == 'clear_location':
        contents = spoolman_api.get_spools_at_location_detailed(loc_id)
        # Pre-flight: if the box being cleared is itself a toolhead that's
        # actively printing, bail. Individual per-spool checks are bypassed
        # (we don't want per-spool prompts during a bulk clear).
        if not confirm_active_print:
            ap = logic._active_print_info_for_location(loc_id)
            if ap:
                return jsonify({
                    "success": False,
                    "require_confirm": True,
                    "confirm_type": "active_print",
                    "active_print": ap,
                    "msg": f"{ap['printer_name']} is {ap['state']} — clearing this location will disrupt the print.",
                })
        for spool in contents:
            # [ALEX FIX] Protect "Ghost" items from being ejected when a box is cleared
            if spool.get('is_ghost'):
                continue

            slot_val = spool.get('slot', '')
            if not slot_val or slot_val == 'None' or slot_val == '':
                logic.perform_smart_eject(spool['id'], confirm_active_print=True)
        return jsonify({"success": True})

    spool_id = None
    if action == 'add':
        if spool_input:
            resolution = logic.resolve_scan(str(spool_input))
            if resolution and resolution['type'] == 'spool':
                spool_id = resolution['id']
            elif resolution and resolution['type'] == 'error':
                 return jsonify({"success": False, "msg": resolution['msg']})
    elif action in ['remove', 'force_unassign']:
        if str(spool_input).isdigit(): spool_id = int(spool_input)

    if not spool_id: return jsonify({"success": False, "msg": "Spool not found"})

    if action == 'remove':
        is_confirmed = data.get('confirmed', False)
        result = logic.perform_smart_eject(
            spool_id,
            confirmed_unassign=is_confirmed,
            confirm_active_print=confirm_active_print,
        )
        if isinstance(result, dict) and result.get('status') == 'requires_confirm':
            return jsonify({
                "success": False,
                "require_confirm": True,
                "confirm_type": result.get('confirm_type'),
                "active_print": result.get('active_print'),
                "msg": result.get('msg', 'Confirmation required.'),
            })
        if result == "REQUIRE_CONFIRM":
            return jsonify({"success": False, "require_confirm": True, "msg": "Spool is already in a room. Confirm true unassign to nowhere?"})
        elif result is True:
            return jsonify({"success": True})
        else:
            return jsonify({"success": False, "msg": "DB Update Failed"})
    elif action == 'force_unassign':
        result = logic.perform_force_unassign(spool_id, confirm_active_print=confirm_active_print)
        if isinstance(result, dict) and result.get('status') == 'requires_confirm':
            return jsonify({
                "success": False,
                "require_confirm": True,
                "confirm_type": result.get('confirm_type'),
                "active_print": result.get('active_print'),
                "msg": result.get('msg', 'Confirmation required.'),
            })
        if result:
            return jsonify({"success": True})
        return jsonify({"success": False, "msg": "DB Update Failed"})
    elif action == 'add':
        origin = data.get('origin', '')
        return jsonify(logic.perform_smart_move(
            loc_id, [spool_id],
            target_slot=slot_arg, origin=origin,
            confirm_active_print=confirm_active_print,
        ))
    return jsonify({"success": False})

def _pm_norm(v):
    """Normalize a stored temp/URL value (a native number, or a possibly
    JSON-wrapped extra string) to a comparable trimmed string; '' if blank."""
    if v is None:
        return ''
    return str(v).strip().strip('"').strip()


_PM_TEMP_LABELS = {
    'settings_extruder_temp': 'Nozzle (min)',
    'nozzle_temp_max': 'Nozzle (max)',
    'settings_bed_temp': 'Bed (min)',
    'bed_temp_max': 'Bed (max)',
}

# L200 — grams of float noise to ignore when deciding a weight field "differs".
_PM_WEIGHT_TOL = 1.0


def _pm_num(v):
    """Coerce a weight-ish value (number or numeric string) to float, or
    None when blank / unparseable. Mirrors _pm_norm's tolerance for the
    JSON-wrapped/native ambiguity but yields a number for arithmetic."""
    if v is None or v == '':
        return None
    try:
        return float(str(v).strip().strip('"').strip())
    except (TypeError, ValueError):
        return None


def _pm_first_pos(*vals):
    """First strictly-positive numeric among vals, else None. Mirrors the
    frontend resolveEmptySpoolWeight chain, which treats null/''/0/<=0 as UNSET
    — important because Spoolman stores an un-set tare/initial as 0.0 (not null)
    on most spools, so a None-only guard would treat 0 as a real value."""
    for v in vals:
        n = _pm_num(v)
        if n is not None and n > 0:
            return n
    return None


def _compute_prusament_spool_weight_diff(matched, fil, obj):
    """Build the proposed SPOOL weight-field updates from a Prusament scan (L200).

    Model (confirmed with Derek 2026-06-05):
      - `used_weight` is the source of truth for consumption (FilaBridge
        auto-deduct writes it directly; it is tare-independent) → PRESERVED.
      - `initial_weight` ← scanned net (manufacturer truth) when it differs
        from the spool's *effective* initial (own value, else filament.weight).
      - `spool_weight` (tare) ← scanned tare when it differs from the
        *effective* tare (own value, else filament.spool_weight, else the
        vendor's empty_spool_weight — the same resolveEmptySpoolWeight chain
        the frontend uses, with 0 treated as unset).
      - Spoolman derives remaining = initial - used, so correcting the total
        recomputes remaining "as if the correct weight had been used from the
        start" without touching the real consumption history.

    Safety gates (added after the 2026-06-05 adversarial review):
      - Returns None for an ARCHIVED matched spool — a weight correction must
        not silently un-archive + relocate a retired spool.
      - Ignores the parser's hardcoded 1000g default (weight_is_default) so a
        page-format drift can't propose a bogus total on a non-1kg spool.
      - Refuses any total that would drive remaining to <= ~0 (would trip
        update_spool's auto-archive-on-empty and unassign a loaded spool).

    Returns a dict the matched-overlay renders + sends back on confirm (the
    APPLY re-validates against the live spool — see api_prusament_apply_weights),
    or None when nothing meaningful changes. NEVER applies the write itself.
    """
    matched = matched or {}
    fil = fil or {}
    fil_vendor = fil.get('vendor') or {}

    # Never silently resurrect an archived spool via a weight correction —
    # mirrors the temp-conflict path's archived gate.
    if matched.get('archived'):
        return None

    scanned_net = _pm_num(obj.get('weight'))
    # The Prusament parser falls back to a hardcoded 1000g when the page blob
    # omits the net weight; that default is indistinguishable from a real 1kg
    # reading, so refuse to offer it as a total correction.
    if obj.get('weight_is_default'):
        scanned_net = None
    scanned_tare = _pm_num(obj.get('spool_weight'))

    cur_used = _pm_num(matched.get('used_weight')) or 0.0
    # Effective current values: treat 0/blank as UNSET and fall through
    # spool -> filament -> vendor, exactly like resolveEmptySpoolWeight.
    eff_initial = _pm_first_pos(matched.get('initial_weight'), fil.get('weight'))
    eff_tare = _pm_first_pos(
        matched.get('spool_weight'),
        fil.get('spool_weight'),
        fil_vendor.get('empty_spool_weight'),
    )

    updates = {}
    rows = []
    blocked = None

    # initial_weight (net / total). Refuse any correction that would leave
    # remaining <= ~0 — Spoolman's auto-archive-on-empty would then silently
    # archive the spool, clear its location, and wipe its slot bindings.
    if scanned_net and scanned_net > 0:
        if eff_initial is None or abs(scanned_net - eff_initial) > _PM_WEIGHT_TOL:
            if scanned_net <= cur_used + _PM_WEIGHT_TOL:
                blocked = (f"Scanned total {scanned_net:g}g would leave ~0g against the "
                           f"{cur_used:g}g already used — leaving the total unchanged "
                           f"(applying it would archive/unassign the spool).")
            else:
                updates['initial_weight'] = scanned_net
                rows.append({"key": "initial_weight", "label": "Total (net)",
                             "current": eff_initial, "scanned": scanned_net})

    # spool_weight (empty / tare)
    if scanned_tare and scanned_tare > 0:
        if eff_tare is None or abs(scanned_tare - eff_tare) > _PM_WEIGHT_TOL:
            updates['spool_weight'] = scanned_tare
            rows.append({"key": "spool_weight", "label": "Empty spool (tare)",
                         "current": eff_tare, "scanned": scanned_tare})

    if not updates and not blocked:
        return None

    new_initial = updates.get('initial_weight', eff_initial)
    remaining = None
    if new_initial is not None:
        remaining = {
            "current": (eff_initial - cur_used) if eff_initial is not None else None,
            "new": new_initial - cur_used,
        }

    return {
        "updates": updates,   # used-preserving: never includes used_weight
        "rows": rows,
        "used": cur_used,
        "remaining": remaining,
        "blocked": blocked,
    }


def _handle_prusament_url_scan(res):
    """Prusament spool-QR scan (feature/scan-match-pipeline).

    Fetch the spool page via the Prusament parser, then:
      - MATCH an existing spool by its stored extra.product_url (the URL saved
        at import time) -> backfill the PARENT FILAMENT's *blank* temps
        (nozzle/bed min+max) silently. For temps that are present but DIFFER
        from the scan, surface an update suggestion ONLY when the filament has
        no unarchived spools (else quiet-log — don't interrupt active use).
        Also fills blank per-spool Prusament metadata. -> type 'prusament_matched'.
      - NO MATCH -> hand the parsed object back so the UI can pre-fill the Add
        wizard (Stage 3). -> type 'prusament_new'.

    Filament writes go through update_filament_or_raise with a PARTIAL extra —
    update_filament merges against the live record, so siblings survive.
    """
    spool_id = res.get('spool_id')
    spool_hash = res.get('spool_hash')
    url = res.get('url', '')

    # Match FIRST — deciding a match needs only the scanned id/hash vs. stored
    # product_urls, NOT the (slow) prusament.com page fetch. So a no-match
    # "onboard" responds fast (just a Spoolman spool list); the page fetch is
    # deferred to the matched/backfill path and the Add wizard (Stage 3).
    #
    # Match on the spool-UNIQUE hash so a scan resolves to the EXACT physical
    # spool, not the first owned duplicate of the same product (two spools can
    # share a product <id> — e.g. dev #196/#197, both 17705 — and the old
    # product-id-only needle corrected whichever came first). When the scanned
    # URL carried a hash but NO owned spool (incl. archived) matches it we do
    # NOT fall back to a product-id match — that would silently operate on a
    # different physical spool. Instead we onboard (Derek 2026-06-05): an
    # unowned exact spool is a brand-new spool. Only a hash-less scan (rare /
    # degenerate) falls back to product-id granularity. Compared lower-cased
    # because _pm_norm doesn't fold case and stored hashes are lowercase hex.
    if spool_hash:
        # The unique spool hash appears either in the PATH form
        # (/spool/<id>/<hash>) the physical QR encodes, or in the QUERY form
        # (?spoolId=<hash>) some imports store. Match EITHER — the hash is
        # unique per physical spool, so this resolves the exact spool whatever
        # the stored URL shape, and never matches a sibling (a sibling carries
        # a different hash). Lower-cased: _pm_norm doesn't fold case and stored
        # hashes are lowercase hex.
        h = spool_hash.lower()
        needles = (f"/spool/{spool_id}/{h}", f"spoolid={h}")
    else:
        # Hash-less scan (rare / degenerate) — best we can do is product-id
        # granularity (the legacy behavior; may resolve the wrong duplicate).
        needles = (f"/spool/{spool_id}/".lower(),)
    matched = None
    for s in spoolman_api.get_all_spools(allow_archived=True):
        pu = _pm_norm((s.get('extra') or {}).get('product_url'))
        if pu and any(n in pu.lower() for n in needles):
            matched = s
            break

    if not matched:
        state.add_log_entry(
            "🆕 Scanned a Prusament spool that isn't in inventory yet — ready to onboard",
            "INFO", "00ccff",
        )
        return jsonify({
            "type": "prusament_new",
            "spool_id": spool_id,
            # Carry the unique hash so onboarding can record the EXACT spool.
            "spool_hash": spool_hash,
            "url": url,
        })

    # Matched — NOW fetch the spool page for its temps.
    parsed = external_parsers.search_external('prusament', url) or []
    if not parsed:
        state.add_log_entry(
            f"⚠️ Matched spool #{matched.get('id')} but couldn't read its Prusament "
            f"page — check the connection",
            "WARNING", "ffaa00",
        )
        return jsonify({"type": "prusament_url", "status": "fetch_failed", "spool_id": spool_id})
    obj = parsed[0]
    obj_extra = obj.get('extra') or {}

    sid = matched.get('id')
    fid = (matched.get('filament') or {}).get('id')
    # Re-fetch the filament fresh — the spool's embedded copy can be stale.
    fil = spoolman_api.get_filament(fid) or (matched.get('filament') or {})
    fil_extra = fil.get('extra') or {}

    # field -> (current on filament, scanned from parser, is_native_field)
    temp_fields = {
        'settings_extruder_temp': (fil.get('settings_extruder_temp'), obj.get('settings_extruder_temp'), True),
        'settings_bed_temp':      (fil.get('settings_bed_temp'),      obj.get('settings_bed_temp'),      True),
        'nozzle_temp_max':        (fil_extra.get('nozzle_temp_max'),  obj_extra.get('nozzle_temp_max'),  False),
        'bed_temp_max':           (fil_extra.get('bed_temp_max'),     obj_extra.get('bed_temp_max'),     False),
    }
    native_fill, extra_fill, conflicts = {}, {}, []
    for field, (cur, scanned, is_native) in temp_fields.items():
        sc = _pm_norm(scanned)
        if not sc:
            continue  # parser had nothing for this field
        if not _pm_norm(cur):
            (native_fill if is_native else extra_fill)[field] = scanned
        elif _pm_norm(cur) != sc:
            conflicts.append({
                "field": field, "label": _PM_TEMP_LABELS.get(field, field),
                "current": _pm_norm(cur), "scanned": sc, "native": is_native,
            })

    # --- Write the blank-fills (partial extra; update_filament merges) ---
    filled = []
    data = dict(native_fill)
    if extra_fill:
        dirty, _stripped = spoolman_api.compute_dirty_extras(
            fil_extra, extra_fill, system_managed=spoolman_api.SYSTEM_MANAGED_EXTRAS,
        )
        if dirty:
            data['extra'] = dirty
    if data:
        try:
            spoolman_api.update_filament_or_raise(fid, data)
            filled = list(native_fill.keys()) + list((data.get('extra') or {}).keys())
            state.add_log_entry(
                f"🌡️ Backfilled {', '.join(filled)} on filament #{fid} from Prusament scan",
                "SUCCESS", "00ff00",
            )
        except spoolman_api.SpoolmanRejection as e:
            state.add_log_entry(
                f"❌ Prusament temp backfill failed for filament #{fid}: {e}",
                "ERROR", "ff4444",
            )
            return jsonify({
                "type": "prusament_matched", "status": "error",
                "spool_id": sid, "filament_id": fid, "msg": str(e),
            })

    # --- Best-effort refresh of blank per-spool Prusament metadata ---
    pm_fill = {}
    spool_extra = matched.get('extra') or {}
    for k in ('prusament_manufacturing_date', 'prusament_length_m'):
        if _pm_norm(obj_extra.get(k)) and not _pm_norm(spool_extra.get(k)):
            pm_fill[k] = obj_extra.get(k)
    # 23.6 — persist/normalize the scanned URL onto the matched spool's
    # product_url ("save the url to the product link section"). The matcher
    # already required the stored product_url to contain the scanned id/hash,
    # so this UPGRADES a non-canonical shape (query form ?spoolId=<hash>,
    # trailing-slash/cruft, casing) to the canonical /spool/<id>/<hash> path
    # form. Idempotent: once stored == canonical the differ-guard skips, so no
    # per-scan churn. Gated on a hash (canonical needs it); the matched URL is
    # always a spool-instance URL (it matched the needle), so this never
    # clobbers a deliberately-set product-PAGE link.
    if spool_hash:
        canonical_purl = f"https://prusament.com/spool/{spool_id}/{spool_hash.lower()}"
        if _pm_norm(spool_extra.get('product_url')) != _pm_norm(canonical_purl):
            pm_fill['product_url'] = canonical_purl
    if pm_fill:
        if spoolman_api.update_spool(sid, {'extra': pm_fill}):
            if 'product_url' in pm_fill:
                state.add_log_entry(
                    f"🔗 Saved the scanned Prusament link to spool #{sid}'s product URL",
                    "INFO", "00ccff",
                )
        else:
            err = spoolman_api.LAST_SPOOLMAN_ERROR or "unknown error"
            state.add_log_entry(
                f"⚠️ Couldn't refresh Prusament metadata on spool #{sid}: {err}",
                "WARNING", "ffaa00",
            )

    # --- Differ-suggest gate: only prompt when no unarchived spools remain ---
    suggest = []
    if conflicts:
        siblings = spoolman_api.get_spools_for_filament(fid) or []
        active = [s for s in siblings if not s.get('archived')]
        if active:
            state.add_log_entry(
                f"ℹ️ Prusament scan: filament #{fid} has differing temps available, but "
                f"{len(active)} active spool(s) are in use — not prompting",
                "INFO", "00ccff",
            )
        else:
            suggest = conflicts

    # --- L200: propose SPOOL weight-field corrections (confirm-gated) ---
    # Computed only; never auto-applied. The matched overlay shows the
    # before→after (total / tare / recomputed remaining) and the user clicks
    # to commit. used_weight is preserved so the print history is untouched.
    spool_weight = _compute_prusament_spool_weight_diff(matched, fil, obj)

    return jsonify({
        "type": "prusament_matched",
        "status": "ok",
        "spool_id": sid,
        "filament_id": fid,
        "filament_name": fil.get('name', 'Unknown'),
        "filled": filled,
        "conflicts": suggest,  # frontend (2c) shows the suggest-overlay when non-empty
        "spool_weight": spool_weight,  # L200: weight diff or None
    })


@app.route('/api/identify_scan', methods=['POST'])
def api_identify_scan():
    text = request.json.get('text', '')
    source = request.json.get('source', '')
    res = logic.resolve_scan(text)

    if res and res.get('type') == 'command' and res.get('cmd') == 'audit':
        state.reset_audit()
        state.AUDIT_SESSION['active'] = True
        state.AUDIT_SESSION['last_activity_ts'] = time.time()
        state.add_log_entry("🕵️‍♀️ <b>AUDIT MODE STARTED</b>", "INFO", "ff00ff")
        state.add_log_entry("Scan a Location label to begin checking.", "INFO")
        return jsonify({"type": "command", "cmd": "clear"})

    if state.AUDIT_SESSION.get('active'):
        # Refresh the watchdog timestamp on every audit-mode scan so the
        # idle-timeout in _check_audit_idle_timeout() only fires after a
        # real abandonment. Updating BEFORE process_audit_scan so an
        # explicit CMD:DONE/CMD:CANCEL still ends the session cleanly.
        state.AUDIT_SESSION['last_activity_ts'] = time.time()
        logic.process_audit_scan(res)
        return jsonify({"type": "command", "cmd": "clear"})

    if not res: return jsonify({"type": "unknown"})

    # Item 3.6 — multiple spools share this legacy id. Surface the
    # candidate list to the UI so the user can disambiguate rather than
    # silently auto-picking. The picker either re-submits with an
    # explicit `ID:NNN` (continues normal flow) or queues a new label
    # for the chosen spool (helps unwind the ambiguity over time).
    if res['type'] == 'ambiguous':
        state.add_log_entry(
            f"⚠️ Legacy ID {res.get('legacy_id', '?')} matches "
            f"{len(res.get('candidates') or [])} spools — pick one to continue",
            "WARNING", "ffaa00",
        )
        return jsonify({
            "type": "ambiguous",
            "legacy_id": res.get('legacy_id'),
            "candidates": res.get('candidates') or [],
        })

    if res['type'] == 'location':
        lid = res['id']; 
        items = spoolman_api.get_spools_at_location_detailed(lid)
        state.add_log_entry(f"🔎 {lid}: {len(items)} item(s)")
        return jsonify({"type": "location", "id": lid, "display": f"LOC: {lid}", "contents": items})
        
    if res['type'] == 'spool':
        sid = res['id']; data = spoolman_api.get_spool(sid)
        label_already_verified = False  # response flag — see L128 below
        if data:
            if source == 'barcode' and text.strip().upper().startswith('ID:'):
                extra = data.get('extra', {})
                raw_flag = extra.get('needs_label_print')
                # Tri-state: True = needs print, False = positively verified,
                # null/missing = unknown (legacy record predating the feature,
                # or a record created via a path that didn't auto-flag).
                # A valid scan should verify both True AND null states — only
                # an explicit False is treated as "already verified" and
                # short-circuits the flag flip.
                already_verified = (
                    raw_flag is False or raw_flag == 'false' or raw_flag == 'False'
                )
                if not already_verified:
                    extra['needs_label_print'] = False
                    if spoolman_api.update_spool(sid, {'extra': extra}):
                        state.add_log_entry(f"✔️ Spool #{sid} Label Verified", "SUCCESS", "00ff00")
                    else:
                        # Surface the actual Spoolman rejection body so the
                        # user can see WHY (Phase B fix). Without this, the
                        # 2026-04-27 outage stayed undiagnosed for hours.
                        err = spoolman_api.LAST_SPOOLMAN_ERROR or "unknown error"
                        state.add_log_entry(
                            f"❌ Failed to verify Spool #{sid} label: {err}", "ERROR", "ff4444"
                        )
                else:
                    # L128 follow-up (2026-05-15): toast-only ack felt
                    # noisier than the log line it replaced, so revert
                    # to writing to the Activity Log. The log is bounded
                    # at 50 entries server-side and the user can pause
                    # it via the click-to-pause indicator — both better
                    # mitigations for blind-scan volume than a 1.5s
                    # toast for every scan.
                    state.add_log_entry(f"ℹ️ Spool #{sid} already verified", "INFO", "00ccff")
                    label_already_verified = True
            
            info = spoolman_api.format_spool_display(data)
            
            # Ensure ghost and slot location logic is provided directly in buffer payloads
            sloc = str(data.get('location', '')).strip()
            extra = data.get('extra', {})
            is_ghost = False
            p_source = str(extra.get('physical_source', '')).strip().replace('"', '')
            if p_source and sloc.upper() != p_source.upper():
                is_ghost = True
            ghost_slot = str(extra.get('physical_source_slot', '')).strip('"')
            
            final_slot = info.get('slot', '')
            if is_ghost and ghost_slot:
                final_slot = ghost_slot

            return jsonify({
                "type": "spool",
                "id": int(sid),
                "display": info['text'],
                "color": info['color'],
                "color_direction": info.get("color_direction", "longitudinal"),
                "remaining_weight": data.get("remaining_weight"),
                "details": info.get("details", {}),
                "archived": data.get("archived", False),
                "location": p_source if is_ghost else sloc,
                "is_ghost": is_ghost,
                "slot": final_slot,
                "deployed_to": sloc if is_ghost else None,
                "label_already_verified": label_already_verified
            })
            
    if res['type'] == 'filament':
        fid = res['id']
        data = spoolman_api.get_filament(fid)
        label_already_verified = False  # response flag — see L128 (spool branch)
        if data:
            if source == 'barcode' and text.strip().upper().startswith('FIL:'):
                extra = data.get('extra', {})
                raw_flag = extra.get('needs_label_print')
                # Tri-state semantics — see spool branch above for rationale.
                already_verified = (
                    raw_flag is False or raw_flag == 'false' or raw_flag == 'False'
                )
                if not already_verified:
                    extra['needs_label_print'] = False
                    # L17 — a physical FIL: label exists on a swatch, so
                    # the sample must have been printed too. Confirm both
                    # in a pair so users don't have to maintain
                    # sample_printed separately. The Activity Log line
                    # already advertised "Label & Sample Verified"; the
                    # code now matches the message.
                    extra['sample_printed'] = True
                    if spoolman_api.update_filament(fid, {'extra': extra}):
                        state.add_log_entry(f"✔️ Filament #{fid} Label & Sample Verified", "SUCCESS", "00ff00")
                    else:
                        # Surface Spoolman rejection body — Item 6 regression
                        # for FIL:126 silent-fail.
                        err = spoolman_api.LAST_SPOOLMAN_ERROR or "unknown error"
                        state.add_log_entry(
                            f"❌ Failed to verify Filament #{fid} label: {err}", "ERROR", "ff4444"
                        )
                else:
                    # L128 follow-up (2026-05-15): see spool branch — reverted
                    # to Activity Log entry. Response flag still emitted in case
                    # any future surface needs the signal, but the toast on the
                    # frontend has been removed.
                    state.add_log_entry(f"ℹ️ Filament #{fid} already verified", "INFO", "00ccff")
                    label_already_verified = True

            name = data.get('name', 'Unknown Filament')
            return jsonify({"type": "filament", "id": int(fid), "display": name, "label_already_verified": label_already_verified})

    if res['type'] == 'prusament_url':
        return _handle_prusament_url_scan(res)

    # --- SLOT ASSIGNMENT (Phase 1) ---
    # LOC:X:SLOT:Y scans mean "drop the buffered spool into slot Y of location X".
    # perform_smart_move already handles auto-eject, container_slot, physical_source,
    # and the Filabridge map_toolhead notification when the target is a printer.
    if res.get('type') == 'assignment':
        target = str(res.get('location', '')).strip().upper()
        slot = str(res.get('slot', '')).strip()
        loc_list = locations_db.load_locations_list()
        loc_info_map = {row['LocationID'].upper(): row for row in loc_list}
        tgt_info = loc_info_map.get(target)

        # Validate target exists and is a container type.
        # L271 Phase 3: "Printer" is a valid slot target — a dual-role printer
        # like the Core One IS its own single deploy slot (Type:"Printer",
        # Max Spools "1"). Without this, LOC:CORE1:SLOT:1 scans would 400.
        container_types = {'Dryer Box', 'MMU Slot', 'Tool Head', 'No MMU Direct Load', 'Printer'}
        if not tgt_info or tgt_info.get('Type') not in container_types:
            found_type = tgt_info.get('Type') if tgt_info else 'missing'
            state.add_log_entry(
                f"❌ Slot scan target <b>{target}</b> invalid (type={found_type}) — scan dropped",
                "ERROR", "ff0000"
            )
            return jsonify({
                "type": "assignment",
                "action": "assignment_bad_target",
                "location": target, "slot": slot,
                "found_type": found_type,
            }), 400

        # Validate slot is within Max Spools range.
        try:
            max_slots = int(str(tgt_info.get('Max Spools', '0')).strip() or '0')
        except ValueError:
            max_slots = 0
        try:
            slot_num = int(slot)
        except ValueError:
            slot_num = 0
        if max_slots > 0 and (slot_num < 1 or slot_num > max_slots):
            state.add_log_entry(
                f"❌ Slot <b>{slot}</b> out of range for {target} (has {max_slots} slots) — scan dropped",
                "ERROR", "ff0000"
            )
            return jsonify({
                "type": "assignment",
                "action": "assignment_bad_slot",
                "location": target, "slot": slot,
                "max_slots": max_slots,
            }), 400

        # Pull the first spool off the buffer.
        # Note: if the buffer is empty, the frontend treats the scan as a
        # "pickup" request (read slot contents and put them in the buffer).
        # That path emits its own log entry on success, so we don't add one
        # here — otherwise every pickup would generate a misleading warning.
        buffer = getattr(state, 'GLOBAL_BUFFER', []) or []
        first_spool = next((item for item in buffer if isinstance(item, dict) and item.get('id')), None)
        if not first_spool:
            return jsonify({
                "type": "assignment",
                "action": "assignment_no_buffer",
                "location": target, "slot": slot,
            }), 200

        spool_id = int(first_spool['id'])
        # Slot-QR scans pass the caller's confirm-active-print flag through
        # transparently. Frontend slot-QR paths pre-probe too, but the
        # backend check is the authoritative safety net — if the printer
        # went active between the probe and the scan, we still bail.
        confirm_active_print = bool(request.json.get('confirm_active_print', False))
        move_result = logic.perform_smart_move(
            target, [spool_id], target_slot=slot, origin='slot_qr_scan',
            confirm_active_print=confirm_active_print,
        )
        # If perform_smart_move bailed on an active-print check, surface the
        # confirmation prompt to the client. Frontend slot-QR path (scan
        # handler) renders this as a modal and retries on confirm.
        if isinstance(move_result, dict) and move_result.get('status') == 'requires_confirm':
            return jsonify({
                "type": "assignment",
                "action": "assignment_requires_confirm",
                "location": target, "slot": slot,
                "confirm_type": move_result.get('confirm_type'),
                "active_print": move_result.get('active_print'),
                "msg": move_result.get('msg'),
                "moved": spool_id,
            }), 200
        # perform_smart_move now handles auto-deploy internally when the
        # target slot is bound to a toolhead. Pick up the deployed-to
        # hint from its response so we can surface it in the toast.
        auto_deployed_to = (move_result or {}).get('auto_deployed_to')

        # Remove the spool from the backend's buffer replica.
        state.GLOBAL_BUFFER = [
            item for item in buffer
            if not (isinstance(item, dict) and int(item.get('id') or 0) == spool_id)
        ]
        remaining = len(state.GLOBAL_BUFFER)
        action = 'assignment_partial' if remaining > 0 else 'assignment_done'

        suffix = f" ({remaining} still in buffer)" if remaining else ""
        if auto_deployed_to:
            log_msg = (
                f"✅ Spool #{spool_id} → <b>{target}:SLOT:{slot}</b> "
                f"→ <b>{auto_deployed_to}</b>{suffix}"
            )
        else:
            log_msg = f"✅ Spool #{spool_id} → <b>{target}:SLOT:{slot}</b>{suffix}"
        state.add_log_entry(log_msg, "SUCCESS", "00ff00")
        return jsonify({
            "type": "assignment",
            "action": action,
            "location": target, "slot": slot,
            "moved": spool_id,
            "auto_deployed_to": auto_deployed_to,
            "remaining_buffer": remaining,
            "smart_move": move_result,
        }), 200

    return jsonify(res)


@app.route('/api/buffer/clear', methods=['POST'])
def api_buffer_clear():
    """Wipe the backend's buffer replica. Used by tests + frontend reset."""
    state.GLOBAL_BUFFER = []
    return jsonify({"success": True, "buffer": []})


# ---------------------------------------------------------------------------
# Phase 2 — Dryer Box ↔ Toolhead bindings
# ---------------------------------------------------------------------------

@app.route('/api/dryer_box/<loc_id>/bindings', methods=['GET'])
def api_dryer_box_bindings_get(loc_id):
    bindings = locations_db.get_dryer_box_bindings(loc_id)
    if bindings is None:
        return jsonify({"error": "not_a_dryer_box", "location": loc_id}), 404
    order = locations_db.get_dryer_box_slot_order(loc_id) or 'ltr'
    return jsonify({"location": loc_id, "slot_targets": bindings, "slot_order": order})


@app.route('/api/dryer_box/<loc_id>/slot_order', methods=['GET'])
def api_dryer_box_slot_order_get(loc_id):
    order = locations_db.get_dryer_box_slot_order(loc_id)
    if order is None:
        return jsonify({"error": "not_a_dryer_box", "location": loc_id}), 404
    return jsonify({"location": loc_id, "order": order})


@app.route('/api/dryer_box/<loc_id>/slot_order', methods=['PUT'])
def api_dryer_box_slot_order_put(loc_id):
    """Persist a dryer box's slot-grid render direction. Body: {"order": "ltr"|"rtl"}.
    Pure UI preference — doesn't touch bindings or any Spoolman data.
    """
    data = request.get_json(silent=True) or {}
    order = data.get('order')
    ok, msg = locations_db.set_dryer_box_slot_order(loc_id, order)
    if not ok:
        return jsonify({"error": "invalid_request", "location": loc_id, "msg": msg}), 400
    # Read back the stored (normalized) value so the response + log entry
    # reflect exactly what's on disk, not the caller's input casing.
    normalized = locations_db.get_dryer_box_slot_order(loc_id) or 'ltr'
    state.add_log_entry(
        f"🔁 Slot order for <b>{loc_id}</b> set to {normalized.upper()}",
        "INFO", "00d4ff",
    )
    return jsonify({"location": loc_id, "order": normalized})


@app.route('/api/dryer_box/<loc_id>/bindings', methods=['PUT'])
def api_dryer_box_bindings_put(loc_id):
    data = request.get_json(silent=True) or {}
    slot_targets = data.get('slot_targets')
    if slot_targets is None:
        state.add_log_entry(
            f"❌ Feeds save rejected on <b>{loc_id}</b>: missing slot_targets",
            "ERROR", "ff0000"
        )
        return jsonify({"error": "missing_slot_targets"}), 400
    printer_map = locations_db.get_active_printer_map()  # L271 P4 step 2: Printer-row toolheads[] (dual-read)
    ok, errors, warnings = locations_db.set_dryer_box_bindings(loc_id, slot_targets, printer_map)
    if not ok:
        reasons = "; ".join(f"slot {e[0]} → {e[1]}: {e[2]}" for e in errors) or "validation failed"
        state.add_log_entry(
            f"❌ Feeds save rejected on <b>{loc_id}</b>: {reasons}",
            "ERROR", "ff0000"
        )
        return jsonify({
            "error": "validation_failed",
            "location": loc_id,
            "errors": [
                {"slot": e[0], "target": e[1], "reason": e[2]} for e in errors
            ],
        }), 400
    state.add_log_entry(
        f"🔗 Bindings updated for <b>{loc_id}</b>"
        + (f" ⚠️ {len(warnings)} warning(s)" if warnings else ""),
        "INFO", "00d4ff"
    )
    for w_slot, w_target, w_reason in warnings:
        state.add_log_entry(
            f"⚠️ Binding warning on <b>{loc_id}</b> slot {w_slot} → {w_target}: {w_reason}",
            "WARNING", "ffaa00"
        )
    return jsonify({
        "location": loc_id,
        "slot_targets": locations_db.get_dryer_box_bindings(loc_id) or {},
        "warnings": [
            {"slot": w[0], "target": w[1], "reason": w[2]} for w in warnings
        ],
    })


@app.route('/api/printer_state/<path:toolhead_id>', methods=['GET'])
def api_printer_state(toolhead_id):
    """Return PrusaLink state for the printer that owns `toolhead_id`.

    toolhead_id is a location ID like "CORE1-M0" or "XL-3". If the location
    doesn't map to a printer or PrusaLink is unreachable, returns
    {"known": false} — callers treat that as "don't block the user."
    Successful response: {"known": true, "state": "PRINTING", "is_active": true}.

    Deliberately fail-open so a UI pre-check never stalls on a cold/rebooting
    printer, wrong API key, or missing filabridge entry.
    """
    import prusalink_api  # local import keeps the module optional at module load
    printer_map = locations_db.get_active_printer_map()  # L271 P4 step 2: Printer-row toolheads[] (dual-read)
    info = printer_map.get((toolhead_id or '').strip().upper())
    if not info:
        return jsonify({"known": False, "reason": "not_in_printer_map"})
    printer_name = info.get('printer_name')
    if not printer_name:
        return jsonify({"known": False, "reason": "no_printer_name"})
    _, fb_url = config_loader.get_api_urls()
    result = prusalink_api.get_printer_state(fb_url, printer_name)
    if not result:
        return jsonify({"known": False, "reason": "prusalink_unreachable"})
    return jsonify({
        "known": True,
        "state": result.get('state'),
        "is_active": bool(result.get('is_active')),
        "printer_name": printer_name,
    })


@app.route('/api/printer_map', methods=['GET'])
def api_printer_map():
    """Read-only view of the printer_map, grouped for UI use:
    {
      "printers": {
        "🦝 XL": [{"location_id": "XL-1", "position": 0}, ...],
        "🦝 Core One": [...]
      }
    }

    L271 Phase 4 (step 3): now sourced from the first-class Printer rows'
    toolheads[] (via get_active_printer_map) instead of config.json — the same
    {entries, printers} shape, so the 4 JS modules that fetch /api/printer_map
    are unchanged (compat shim). Dual-read: falls back to config until folded.
    """
    loc_rows = locations_db.load_locations_list()
    printer_map = locations_db.get_active_printer_map(loc_rows)
    grouped = {}
    for loc_id, info in printer_map.items():
        name = info.get('printer_name', 'Unknown')
        grouped.setdefault(name, []).append({
            "location_id": loc_id.upper(),
            "position": info.get('position', 0),
        })
    # Stable sort within each printer by position.
    for entries in grouped.values():
        entries.sort(key=lambda e: (e['position'], e['location_id']))
    # Flat, editable view for the Phase 3 config editor. Coerce position to int
    # so a hand-edited / legacy non-int value can't TypeError the sort (the
    # editor must load to let the user self-repair).
    def _posint(v):
        try:
            return int(v)
        except (TypeError, ValueError):
            return 0
    flat = [
        {"location_id": loc_id.upper(),
         "printer_name": info.get('printer_name', ''),
         "position": _posint(info.get('position', 0))}
        for loc_id, info in printer_map.items()
    ]
    flat.sort(key=lambda e: (e['printer_name'], e['position'], e['location_id']))
    # FilaBridge Phase-2: per-printer PrusaLink connection (ip + api_key) for the
    # "Printer Connections" block folded into this editor. ip_address is a LAN
    # address (not secret); api_key is MASKED to SECRET_SENTINEL when present
    # (never the plaintext) — the PUT keeps the stored key when it gets the
    # sentinel back. Keyed by printer Name (the same key the rest of this view
    # uses), so a printer with no creds yet still shows an empty editable row.
    creds_view = {}
    for _row in (loc_rows or []):
        if not isinstance(_row, dict) or str(_row.get('Type', '')).strip().lower() != 'printer':
            continue
        _nm = str(_row.get('Name', ''))
        if not _nm:
            continue
        _c = _row.get(locations_db.PRINTER_CREDS_KEY)
        _c = _c if isinstance(_c, dict) else {}
        creds_view[_nm] = {
            "ip_address": (_c.get("ip_address") or ""),
            "api_key": config_schema.SECRET_SENTINEL if _c.get("api_key") else "",
        }
    return jsonify({"printers": grouped, "entries": flat, "printer_creds": creds_view})


@app.route('/api/printer_creds', methods=['PUT'])
def api_put_printer_creds():
    """FilaBridge Phase-2: set a printer's PrusaLink connection (ip_address +
    api_key) on its Type:"Printer" row in locations.json. Powers the "Printer
    Connections" block in the printer-map editor.

    SECRET_SENTINEL contract for api_key (mirrors the Config editor): receiving
    the sentinel means "unchanged" → keep the stored key; any other value
    replaces it (empty string → no key). A blank ip_address CLEARS the whole
    creds object. Body: {printer_name, ip_address, api_key}. 404 if no Printer
    row carries that Name."""
    payload = request.get_json(silent=True) or {}
    name = str(payload.get('printer_name', '')).strip()
    ip = str(payload.get('ip_address', '') or '').strip()
    api_key_in = payload.get('api_key', '')
    if not name:
        return jsonify({"ok": False, "error": "printer_name is required"}), 400
    try:
        rows = locations_db.load_locations_list()
    except Exception as e:
        return jsonify({"ok": False, "error": f"could not read locations: {e}"}), 500
    # Confirm the Printer row exists before any write (changed=False is ambiguous —
    # it also means "value unchanged" — so we can't use it to detect a bad name).
    if not any(isinstance(r, dict)
               and str(r.get('Type', '')).strip().lower() == 'printer'
               and str(r.get('Name', '')) == name
               for r in (rows or [])):
        return jsonify({"ok": False, "error": f"No Printer named {name!r}"}), 404
    # Sentinel = keep the stored key; otherwise take the sent value (blank → None).
    if api_key_in == config_schema.SECRET_SENTINEL:
        existing = locations_db.get_printer_credentials(name, rows) or {}
        api_key = existing.get('api_key')
    else:
        api_key = api_key_in if api_key_in else None
    rows, changed = locations_db.set_printer_credentials(rows, name, ip, api_key)
    if changed and not locations_db.save_locations_list(rows):
        state.add_log_entry(f"🔐 Printer connection save FAILED for {name}", "ERROR", "ff4444")
        return jsonify({"ok": False, "error": "could not persist printer connection"}), 500
    state.add_log_entry(f"🔐 Printer connection updated for {name}", "INFO")
    return jsonify({"ok": True, "error": None})


def _pm_prefix(k):
    """Printer prefix of a toolhead LocationID (the part before the first '-'),
    matching locations_db._known_printer_prefixes."""
    k = str(k).strip().upper()
    return k.split('-', 1)[0] if '-' in k else k


def _printer_map_blocked_removals(old_map, new_map):
    """L18 Phase 3 referential guard. Adding toolheads + editing an existing
    toolhead's name/position is always safe. Removing/renaming a key is BLOCKED
    if the LocationID is still referenced:
      - a dryer-box slot_target bound directly to it,
      - a PRINTER:<prefix> pool slot whose prefix this key is the LAST toolhead of,
      - spools physically at it.
    FAILS CLOSED: if references cannot be verified (locations.json unreadable, or
    Spoolman unreachable), the removal is blocked with a retryable reason rather
    than allowed. Returns a list of {location_id, reasons}."""
    old_keys = {str(k).strip().upper() for k in (old_map or {})}
    new_keys = {str(k).strip().upper() for k in (new_map or {})}
    removed = old_keys - new_keys
    if not removed:
        return []

    # Prefixes that DISAPPEAR after this edit (the last toolhead of a printer is
    # being removed) — a PRINTER:<prefix> pool sentinel on those would dangle.
    lost_prefixes = {_pm_prefix(k) for k in old_keys} - {_pm_prefix(k) for k in new_keys}

    # Scan dryer-box slot_targets: direct toolhead bindings + PRINTER: sentinels.
    bound = set()              # toolhead LocationIDs directly bound
    sentinel_prefixes = set()  # printer prefixes referenced via PRINTER:<prefix>
    slots_verified = True
    try:
        for row in locations_db.load_locations_list():
            targets = (row.get('extra') or {}).get('slot_targets') or {}
            for tgt in targets.values():
                if not tgt:
                    continue
                if locations_db.is_printer_sentinel(tgt):
                    sentinel_prefixes.add(str(tgt).strip().upper().split(':', 1)[1])
                else:
                    bound.add(str(tgt).strip().upper())
    except Exception as e:
        state.logger.warning(f"printer_map guard: could not scan slot_targets, failing closed: {e}")
        slots_verified = False  # FAIL CLOSED — block all removals below

    blocked = []
    for key in sorted(removed):
        reasons = []
        if key in bound:
            reasons.append("a dryer-box slot is bound to it")
        pfx = _pm_prefix(key)
        if pfx in lost_prefixes and pfx in sentinel_prefixes:
            reasons.append(f"a dryer-box pool slot still feeds printer '{pfx}' (PRINTER:{pfx})")
        if not slots_verified:
            reasons.append("could not verify dryer-box bindings (locations unreadable) — refusing")
        # Spools physically at this toolhead — STRICT check raises on outage.
        try:
            if spoolman_api.get_spools_at_location_strict(key):
                reasons.append("spool(s) are stored there")
        except Exception as e:
            state.logger.warning(f"printer_map guard: spool check unverifiable for {key}, failing closed: {e}")
            reasons.append("could not verify spools (Spoolman unreachable) — refusing")
        if reasons:
            blocked.append({"location_id": key, "reasons": reasons})
    return blocked


@app.route('/api/printer_map', methods=['PUT'])
def api_put_printer_map():
    """Persist an edited printer_map. Adding toolheads + editing name/position is
    free; removing/renaming a key still referenced by a dryer-box slot or holding
    spools is BLOCKED (409).

    L271 Phase 4 (step 4 — the cutover): the printer_map now lives ON the first-
    class Type:"Printer" rows as toolheads[] in locations.json — NOT in
    config.json. This handler (1) validates/canonicalizes the edit, (2) runs the
    referential guard against the ROW-sourced active map, then (3) writes the edit
    onto the rows as the SOLE persistence: a Type:"Printer" row is created for any
    brand-new printer, each row's toolheads[] is re-synced from the edited map
    (positions stored VERBATIM — never auto-renumbered), and each row's Name is
    synced from the edited printer_name (the row Name is the single source of truth
    for the display name). config:printer_map is no longer written — it survives
    only as the boot-time priming seed. Returns {ok, error, printer_map}."""
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        payload = {}
    new_map = payload.get('printer_map')
    if not isinstance(new_map, dict):
        return jsonify({"ok": False, "error": "printer_map must be an object"}), 400

    # Validate + canonicalize (uppercase keys, require name, position >= 0, reject
    # case-collisions). Pure validator, no I/O — a bad shape is a client 400.
    canonical, verr = config_loader._canonicalize_printer_map(new_map)
    if verr:
        state.add_log_entry(f"⚙️ Printer-map save failed: {verr}", "ERROR", "ff4444")
        return jsonify({"ok": False, "error": verr}), 400

    # Referential guard vs the ROW-sourced active map (Step 4: rows are the source
    # of truth — this was config-sourced during the dual-read window). If the
    # active map can't be read (locations.json unreadable), FAIL CLOSED with a
    # retryable 409 rather than risk an unguarded removal.
    try:
        old_map = locations_db.get_active_printer_map() or {}
    except Exception as _read_err:
        state.logger.warning(f"printer_map guard: could not read active map, failing closed: {_read_err}")
        reason = "could not read the current printer map (locations unreadable) — refusing"
        state.add_log_entry(f"⚙️ Printer-map save blocked — {reason}", "ERROR", "ff4444")
        return jsonify({"ok": False, "error": reason,
                        "blocked": [{"location_id": "*", "reasons": [reason]}]}), 409
    blocked = _printer_map_blocked_removals(old_map, canonical)
    if blocked:
        msg = "Can't remove/rename toolhead(s) still in use: " + "; ".join(
            f"{b['location_id']} ({', '.join(b['reasons'])})" for b in blocked)
        state.add_log_entry(f"⚙️ Printer-map save blocked — {msg}", "ERROR", "ff4444")
        return jsonify({"ok": False, "error": msg, "blocked": blocked}), 409

    # Persist the edit onto the Printer rows AUTHORITATIVELY — this is the only
    # write now, so a failure to persist is a server 500 (not best-effort).
    try:
        _locs = locations_db.load_locations_list()
        # Create a Type:"Printer" row for any brand-new printer first…
        _locs, _ = locations_db.migrate_printers_to_rows_if_needed(_locs, canonical)
        # …then re-sync every Printer row's toolheads[] from the edited map (full
        # re-sync — NOT prime_only — so an edit actually applies; positions kept
        # verbatim, no auto-renumber).
        _locs, _ = locations_db.migrate_printer_map_to_toolheads_if_needed(_locs, canonical)
        # …and sync each Printer row's Name from the edited printer_name (the row
        # Name is the single source of truth for the display name, so a rename in
        # the editor must propagate — neither migration above touches Name).
        _names_by_prefix = {}
        for _k, _info in canonical.items():
            _pfx = _k.split('-', 1)[0] if '-' in _k else _k
            _names_by_prefix.setdefault(_pfx, _info.get('printer_name', ''))
        for _row in _locs:
            if not isinstance(_row, dict) or str(_row.get('Type', '')).strip().lower() != 'printer':
                continue
            _pid = str(_row.get('LocationID', '')).strip().upper()
            _new_name = _names_by_prefix.get(_pid)
            if _new_name and _row.get('Name') != _new_name:
                _row['Name'] = _new_name
        if not locations_db.save_locations_list(_locs):
            reason = "could not persist the printer rows"
            state.add_log_entry(f"⚙️ Printer-map save failed: {reason}", "ERROR", "ff4444")
            return jsonify({"ok": False, "error": reason}), 500
    except Exception as _write_err:
        state.logger.error(f"printer_map row write failed: {_write_err}")
        state.add_log_entry(f"⚙️ Printer-map save failed: {_write_err}", "ERROR", "ff4444")
        return jsonify({"ok": False, "error": str(_write_err)}), 500

    state.add_log_entry(f"⚙️ Printer map updated ({len(canonical)} toolheads)", "INFO")
    return jsonify({"ok": True, "error": None, "printer_map": canonical})


@app.route('/api/dryer_boxes/slots', methods=['GET'])
def api_all_dryer_box_slots():
    """Enumerate every slot across every Dryer Box, flat. Each entry carries
    current binding (may be null). Powers the "bind a slot to this toolhead"
    quick-picker. Cheap — single locations.json read, no Spoolman calls.
    """
    loc_list = locations_db.load_locations_list()
    out = []
    for row in loc_list:
        if row.get('Type') != locations_db.DRYER_BOX_TYPE:
            continue
        box_id = str(row.get('LocationID', '')).strip()
        try:
            max_slots = int(str(row.get('Max Spools', '0')).strip() or '0')
        except ValueError:
            max_slots = 0
        targets = (row.get('extra') or {}).get('slot_targets') or {}
        for n in range(1, max_slots + 1):
            slot = str(n)
            target = targets.get(slot)
            out.append({
                "box": box_id,
                "box_name": row.get('Name', box_id),
                "slot": slot,
                "target": target,  # None => unbound
            })
    # Sort: unbound first (so the picker can promote quickly), then by box id.
    out.sort(key=lambda e: (e['target'] is not None, e['box'], int(e['slot'])))
    return jsonify({"slots": out})


@app.route('/api/dryer_box/<loc_id>/bindings/<slot>', methods=['PUT'])
def api_single_slot_binding_put(loc_id, slot):
    """Patch a single slot's binding without needing to send the whole
    slot_targets map. Used by the quick-bind picker on the toolhead view.
    """
    data = request.get_json(silent=True) or {}
    target = data.get('target')

    # Load current bindings, update just this slot, persist through the
    # full validator so the same rules apply.
    current = locations_db.get_dryer_box_bindings(loc_id)
    if current is None:
        state.add_log_entry(
            f"❌ Binding rejected: <b>{loc_id}</b> is not a dryer box",
            "ERROR", "ff0000"
        )
        return jsonify({"error": "not_a_dryer_box", "location": loc_id}), 404
    next_targets = dict(current)
    if target in (None, '', 'null', 'None'):
        next_targets.pop(str(slot), None)
    else:
        next_targets[str(slot)] = str(target)

    printer_map = locations_db.get_active_printer_map()  # L271 P4 step 2: Printer-row toolheads[] (dual-read)
    ok, errors, warnings = locations_db.set_dryer_box_bindings(loc_id, next_targets, printer_map)
    if not ok:
        reasons = "; ".join(f"slot {e[0]} → {e[1]}: {e[2]}" for e in errors) or "validation failed"
        state.add_log_entry(
            f"❌ Binding rejected on <b>{loc_id}</b>: {reasons}",
            "ERROR", "ff0000"
        )
        return jsonify({
            "error": "validation_failed",
            "location": loc_id, "slot": slot,
            "errors": [{"slot": e[0], "target": e[1], "reason": e[2]} for e in errors],
        }), 400
    suffix = f" → {target}" if target else " → (none)"
    state.add_log_entry(
        f"🔗 {loc_id} slot {slot}{suffix}"
        + (f" ⚠️ {len(warnings)} warning(s)" if warnings else ""),
        "INFO", "00d4ff"
    )
    for w_slot, w_target, w_reason in warnings:
        state.add_log_entry(
            f"⚠️ Binding warning on <b>{loc_id}</b> slot {w_slot} → {w_target}: {w_reason}",
            "WARNING", "ffaa00"
        )
    return jsonify({
        "location": loc_id,
        "slot": slot,
        "slot_targets": locations_db.get_dryer_box_bindings(loc_id) or {},
        "warnings": [{"slot": w[0], "target": w[1], "reason": w[2]} for w in warnings],
    })


@app.route('/api/quickswap/return', methods=['POST'])
def api_quickswap_return():
    """Reverse quick-swap: take whatever spool is currently on `toolhead`
    and send it back to the first dryer-box slot bound to that toolhead.

    Accepts either a specific toolhead location ID (e.g. "XL-1") or a
    virtual-printer prefix (e.g. "XL") — in the latter case we fan out
    across every toolhead of that printer and return the first one that
    has a spool loaded.
    """
    data = request.get_json(silent=True) or {}
    toolhead = str(data.get('toolhead', '')).strip().upper()
    if not toolhead:
        state.add_log_entry(
            "❌ Return rejected: missing toolhead in request",
            "ERROR", "ff0000"
        )
        return jsonify({"action": "return_bad_request", "error": "toolhead required"}), 400

    cfg = config_loader.load_config()
    printer_map = locations_db.get_active_printer_map()  # L271 P4 step 2: Printer-row toolheads[] (dual-read)

    # Build the list of toolhead IDs we should check. For a virtual
    # printer prefix, this is every toolhead in printer_map that starts
    # with "<prefix>-". For a specific toolhead, it's just that ID.
    pm_keys_up = {k.upper() for k in printer_map.keys()}
    candidate_toolheads = []
    if toolhead in pm_keys_up:
        candidate_toolheads = [toolhead]
    else:
        prefix = toolhead + '-'
        candidate_toolheads = sorted(k for k in pm_keys_up if k.startswith(prefix))

    if not candidate_toolheads:
        state.add_log_entry(
            f"⚠️ Return: {toolhead} is not a registered toolhead or printer",
            "WARNING", "ffaa00"
        )
        return jsonify({"action": "return_bad_toolhead", "toolhead": toolhead}), 404

    # 1) Find the first candidate toolhead that has a loaded spool.
    active_toolhead, spool_id = None, None
    for th in candidate_toolheads:
        residents = spoolman_api.get_spools_at_location(th)
        if residents:
            active_toolhead = th
            spool_id = int(residents[0])
            break
    if not active_toolhead:
        names = ", ".join(candidate_toolheads) if len(candidate_toolheads) > 1 else candidate_toolheads[0]
        state.add_log_entry(
            f"⚠️ Return: {names} is empty — nothing to return",
            "WARNING", "ffaa00"
        )
        return jsonify({
            "action": "return_no_spool",
            "toolhead": toolhead,
            "candidates": candidate_toolheads,
        }), 404

    # 2) Figure out where to send the spool back.
    #    Preferred: the spool's recorded physical_source (where it came
    #    from when it was deployed to this toolhead). That's what the
    #    user's mental model of "return" maps to, and it handles the
    #    multi-box-per-toolhead case correctly.
    #    Fallback: the first dryer-box slot bound to this toolhead.
    spool_data = spoolman_api.get_spool(spool_id) or {}
    extra = spool_data.get('extra') or {}
    src_loc = str(extra.get('physical_source', '') or '').strip().strip('"').upper()
    src_slot = str(extra.get('physical_source_slot', '') or '').strip().strip('"')

    loc_list = locations_db.load_locations_list()
    found_box, found_slot, found_source = None, None, None

    # Preferred path: physical_source points at a Dryer Box and that slot
    # is currently bound to `active_toolhead`. If the slot has drifted
    # (e.g. user reassigned it elsewhere), we still honor physical_source
    # as long as the box exists — it's where the user pulled the spool from.
    if src_loc:
        for row in loc_list:
            if str(row.get('LocationID', '')).strip().upper() != src_loc:
                continue
            if row.get('Type') != locations_db.DRYER_BOX_TYPE:
                break
            found_box = row['LocationID']
            found_slot = src_slot or None
            found_source = 'physical_source'
            break

    # Fallback: scan bindings for the first dryer-box slot bound to this toolhead.
    if not found_box:
        for row in loc_list:
            if row.get('Type') != locations_db.DRYER_BOX_TYPE:
                continue
            targets = (row.get('extra') or {}).get('slot_targets') or {}
            for slot, target in targets.items():
                if target and str(target).upper() == active_toolhead:
                    found_box = row['LocationID']
                    found_slot = slot
                    found_source = 'first_binding'
                    break
            if found_box:
                break

    if not found_box:
        state.add_log_entry(
            f"⚠️ Return: {active_toolhead} has no bound dryer box slot and no physical_source — can't return",
            "WARNING", "ffaa00"
        )
        return jsonify({
            "action": "return_no_binding",
            "toolhead": active_toolhead,
            "requested": toolhead,
        }), 404
    # Re-tag toolhead in the response to the actual one we acted on.
    toolhead = active_toolhead

    # 3) Send the spool back. perform_smart_move handles Filabridge + extras.
    # The destination is a dryer box (not a toolhead), so the destination
    # active-print check won't fire. The source-side disruption was already
    # surfaced by the Quick-Swap confirm overlay's banner before this
    # endpoint was called — backend just passes confirm_active_print=True
    # unconditionally here because the user already saw the warning.
    move_result = logic.perform_smart_move(
        found_box, [spool_id], target_slot=found_slot, origin='quickswap_return',
        confirm_active_print=True,
    )
    src_note = " (original source)" if found_source == 'physical_source' else " (first bound slot)"
    slot_part = f":SLOT:{found_slot}" if found_slot else ""
    state.add_log_entry(
        f"↩️ Return: Spool #{spool_id} from <b>{toolhead}</b> → <b>{found_box}{slot_part}</b>{src_note}",
        "SUCCESS", "00ff00"
    )
    return jsonify({
        "action": "return_done",
        "moved": spool_id,
        "toolhead": toolhead,
        "box": found_box,
        "slot": found_slot,
        "source": found_source,
        "smart_move": move_result,
    }), 200


@app.route('/api/quickswap', methods=['POST'])
def api_quickswap():
    """Tap-to-swap: move the spool currently in (box, slot) into the given
    toolhead. Reuses perform_smart_move for the actual move — that
    function already handles auto-eject of any occupant, container_slot
    cleanup, physical_source tracking, and the Filabridge map_toolhead
    notification.
    """
    data = request.get_json(silent=True) or {}
    toolhead = str(data.get('toolhead', '')).strip().upper()
    box = str(data.get('box', '')).strip().upper()
    slot = str(data.get('slot', '')).strip()

    if not toolhead or not box or not slot:
        state.add_log_entry(
            f"❌ Quick-swap rejected: missing required field "
            f"(toolhead={toolhead or '—'}, box={box or '—'}, slot={slot or '—'})",
            "ERROR", "ff0000"
        )
        return jsonify({
            "action": "quickswap_bad_request",
            "error": "toolhead, box, and slot are all required",
        }), 400

    # Verify the binding actually exists. Guards against stale UI state
    # racing against a concurrent binding edit elsewhere.
    bindings = locations_db.get_dryer_box_bindings(box)
    if bindings is None:
        state.add_log_entry(
            f"❌ Quick-swap rejected: <b>{box}</b> is not a dryer box",
            "ERROR", "ff0000"
        )
        return jsonify({
            "action": "quickswap_bad_box",
            "box": box,
            "error": "not a dryer box",
        }), 404
    bound_target = bindings.get(slot)
    if not bound_target or str(bound_target).upper() != toolhead:
        state.add_log_entry(
            f"⚠️ Quick-swap: stale binding — <b>{box}:SLOT:{slot}</b> is "
            f"bound to <b>{bound_target or '(nothing)'}</b>, not {toolhead}",
            "WARNING", "ffaa00"
        )
        return jsonify({
            "action": "quickswap_not_bound",
            "box": box, "slot": slot, "toolhead": toolhead,
            "bound_to": bound_target,
            "error": "slot is not bound to this toolhead",
        }), 400

    spool_id = logic.find_spool_in_slot(box, slot)
    if not spool_id:
        state.add_log_entry(
            f"⚠️ Quick-swap: slot {box}:SLOT:{slot} is empty — no spool to move to {toolhead}",
            "WARNING", "ffaa00"
        )
        return jsonify({
            "action": "quickswap_empty_slot",
            "box": box, "slot": slot, "toolhead": toolhead,
        }), 404

    # Quick-Swap confirm overlay already probed the destination toolhead and
    # surfaced the warning banner before this endpoint was called, so the
    # user has already opted in. Pass confirm_active_print=True so the
    # backend check doesn't re-prompt.
    move_result = logic.perform_smart_move(
        toolhead, [spool_id], target_slot=None, origin='quickswap',
        confirm_active_print=True,
    )
    state.add_log_entry(
        f"⚡ Quick-swap: Spool #{spool_id} from <b>{box}:SLOT:{slot}</b> → <b>{toolhead}</b>",
        "SUCCESS", "00ff00"
    )
    return jsonify({
        "action": "quickswap_done",
        "moved": spool_id,
        "toolhead": toolhead, "box": box, "slot": slot,
        "smart_move": move_result,
    }), 200


@app.route('/api/machine/<path:printer_name>/toolhead_slots', methods=['GET'])
def api_machine_toolhead_slots(printer_name):
    """Reverse lookup: for a printer, return every (box, slot) pair that
    feeds each of its toolheads. `printer_name` may contain emoji and
    spaces — the <path:> converter keeps them intact across the URL."""
    printer_map = locations_db.get_active_printer_map()  # L271 P4 step 2: Printer-row toolheads[] (dual-read)
    result = locations_db.get_bindings_for_machine(printer_name, printer_map)
    # 404 when the printer_name matches zero printer_map entries.
    if not result['toolheads']:
        return jsonify({
            "printer_name": printer_name,
            "toolheads": {},
            "error": "printer_not_found",
        }), 404
    return jsonify(result)

@app.route('/api/print_queue/pending', methods=['GET'])
def api_print_queue_pending():
    filter_type = request.args.get('filter', 'all')
    sort_type = request.args.get('sort', 'created_newest')
    
    sm_url, _ = config_loader.get_api_urls()
    items = []
    
    try:
        # Fetch Spools
        if filter_type in ['all', 'spool']:
            r_spools = requests.get(f"{sm_url}/api/v1/spool?extra=%7B%22needs_label_print%22%3Atrue%7D", timeout=2)
            if r_spools.ok:
                for s in r_spools.json():
                    s['type'] = 'spool'
                    if 'vendor' in s.get('filament', {}): s['brand'] = s['filament']['vendor'].get('name', 'Unknown')
                    items.append(s)
        
        # Fetch Filaments
        if filter_type in ['all', 'filament']:
            r_fils = requests.get(f"{sm_url}/api/v1/filament?extra=%7B%22needs_label_print%22%3Atrue%7D", timeout=2)
            if r_fils.ok:
                for f in r_fils.json():
                    f['type'] = 'filament'
                    if 'vendor' in f: f['brand'] = f['vendor'].get('name', 'Unknown')
                    items.append(f)
        
        # Sorting
        if sort_type == 'created_newest':
            items.sort(key=lambda x: x.get('registered', ''), reverse=True)
        elif sort_type == 'created_oldest':
            items.sort(key=lambda x: x.get('registered', ''))
        elif sort_type == 'id_desc':
            items.sort(key=lambda x: x.get('id', 0), reverse=True)
        elif sort_type == 'id_asc':
            items.sort(key=lambda x: x.get('id', 0))
        elif sort_type == 'brand_asc':
            items.sort(key=lambda x: (x.get('brand', '').lower(), x.get('id', 0)))
            
        return jsonify({"success": True, "items": items})
    except Exception as e:
        state.logger.error(f"Error fetching pending print queue: {e}")
        return jsonify({"success": False, "msg": str(e)})

@app.route('/api/print_queue/mark_printed', methods=['POST'])
def api_print_queue_mark_printed():
    data = request.json
    item_id = data.get('id')
    item_type = data.get('type')
    
    if not item_id or not item_type:
        return jsonify({"success": False, "msg": "Missing ID or Type"})
        
    # Strictly reject legacy IDs (they usually start with strings or have weird formats). Make sure it's int convertible.
    try:
        item_id = int(item_id)
    except ValueError:
        return jsonify({"success": False, "msg": "Legacy IDs cannot be manually marked printed. Please scan."})
        
    try:
        if item_type == 'spool':
            spool_data = spoolman_api.get_spool(item_id)
            if spool_data:
                extra = spool_data.get('extra', {})
                extra['needs_label_print'] = False
                res = spoolman_api.update_spool(item_id, {'extra': extra})
                if res:
                    return jsonify({"success": True})
                err = spoolman_api.LAST_SPOOLMAN_ERROR or "Spoolman rejected the update"
                state.logger.error(f"mark_printed: spool {item_id} update failed: {err}")
                return jsonify({"success": False, "msg": err})
        elif item_type == 'filament':
            fil_data = spoolman_api.get_filament(item_id)
            if fil_data:
                extra = fil_data.get('extra', {})
                extra['needs_label_print'] = False
                res = spoolman_api.update_filament(item_id, {'extra': extra})
                if res:
                    return jsonify({"success": True})
                err = spoolman_api.LAST_SPOOLMAN_ERROR or "Spoolman rejected the update"
                state.logger.error(f"mark_printed: filament {item_id} update failed: {err}")
                return jsonify({"success": False, "msg": err})

        return jsonify({"success": False, "msg": "Item not found or update failed"})
    except Exception as e:
        state.logger.error(f"Error marking {item_type} #{item_id} printed: {e}")
        return jsonify({"success": False, "msg": str(e)})

@app.route('/api/print_queue/set_flag', methods=['POST'])
def api_print_queue_set_flag():
    data = request.json
    item_id = data.get('id')
    item_type = data.get('type')

    try:
        if item_type == 'spool':
            sd = spoolman_api.get_spool(item_id)
            if sd:
                ex = sd.get('extra', {})
                ex['needs_label_print'] = True
                if spoolman_api.update_spool(item_id, {'extra': ex}):
                    return jsonify({"success": True})
                err = spoolman_api.LAST_SPOOLMAN_ERROR or "Spoolman rejected the update"
                state.logger.error(f"set_flag: spool {item_id} update failed: {err}")
                return jsonify({"success": False, "msg": err})
        elif item_type == 'filament':
            fd = spoolman_api.get_filament(item_id)
            if fd:
                ex = fd.get('extra', {})
                ex['needs_label_print'] = True
                if spoolman_api.update_filament(item_id, {'extra': ex}):
                    return jsonify({"success": True})
                err = spoolman_api.LAST_SPOOLMAN_ERROR or "Spoolman rejected the update"
                state.logger.error(f"set_flag: filament {item_id} update failed: {err}")
                return jsonify({"success": False, "msg": err})
        return jsonify({"success": False})
    except Exception as e:
        state.logger.error(f"Error setting needs_label_print: {e}")
        return jsonify({"success": False, "msg": str(e)})

@app.route('/api/filament/<fid>/flag_spool_labels', methods=['POST'])
def api_flag_spool_labels(fid):
    """23.3 follow-up — a filament edit changed a SPOOL-label-visible field
    (Brand / Type / Color-name), so the printed labels on that filament's
    physical spools are now stale. Light touch (no prompt, per Derek): raise
    needs_label_print on the filament's UNARCHIVED spools so the spool details
    badge + print queue surface them as needing a reprint. Hex/RGB are NOT
    printed on the spool label, so the caller only invokes this for non-hex
    changes. Best-effort + per-spool error surfacing."""
    try:
        try:
            fid_int = int(fid)
        except (TypeError, ValueError):
            return jsonify({"success": False, "msg": "Invalid filament id"})
        spools = spoolman_api.get_spools_for_filament(fid_int) or []
        flagged, errors = [], []
        for s in spools:
            if s.get('archived'):
                continue
            sid = s.get('id')
            # Partial extra — _merge_extras_with_existing preserves siblings.
            if spoolman_api.update_spool(sid, {'extra': {'needs_label_print': True}}):
                flagged.append(sid)
            else:
                err = spoolman_api.LAST_SPOOLMAN_ERROR or 'unknown'
                errors.append({'id': sid, 'error': err})
                state.logger.warning(f"flag_spool_labels: spool {sid} update failed: {err}")
        if flagged:
            state.add_log_entry(
                f"🏷️ Flagged {len(flagged)} spool label(s) of filament #{fid_int} as out-of-date after a label-field edit",
                "INFO", "ffaa00",
            )
        return jsonify({"success": True, "flagged": flagged, "errors": errors})
    except Exception as e:
        state.logger.error(f"flag_spool_labels error for filament {fid}: {e}")
        return jsonify({"success": False, "msg": str(e)})

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


@app.route('/api/config', methods=['GET'])
def api_get_config():
    """L18 Config System — return the declarative schema + current values for
    the settings renderer. Server-scope values come from the live config;
    client-scope fields return their default (the browser overrides them from
    localStorage)."""
    cfg = config_loader.load_config()
    schema = config_schema.schema_for_ui()
    values = {}
    for f in schema['fields']:
        if f['scope'] != 'server':
            values[f['key']] = f['default']
        elif f['type'] == 'secret':
            # NEVER send the plaintext secret to the browser — surface only
            # whether one is currently set (the sentinel) vs. empty.
            values[f['key']] = config_schema.SECRET_SENTINEL if cfg.get(f['key']) else ""
        else:
            values[f['key']] = cfg.get(f['key'], f['default'])
    return jsonify({"schema": schema, "values": values})


@app.route('/api/config', methods=['PUT'])
def api_put_config():
    """L18 Config System — persist server-scope settings. Validation/write
    errors are surfaced in the response JSON (the frontend toasts at 7s) and
    written to the Activity Log; success is logged too. Accepts either
    {"values": {...}} or a bare {...} body."""
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        payload = {}
    inner = payload.get('values')
    values = inner if isinstance(inner, dict) else payload
    result = config_loader.save_config(values)
    if result.get('ok'):
        saved = result.get('saved') or []
        if saved:
            state.add_log_entry(f"⚙️ Config updated: {', '.join(saved)}", "INFO")
        return jsonify(result)
    state.add_log_entry(f"⚙️ Config save failed: {result.get('error')}", "ERROR", "ff4444")
    return jsonify(result), 400


@app.route('/api/config/export', methods=['GET'])
def api_config_export():
    """L18 Phase 4 — export the current config as a JSON download for backup /
    transfer. Secret values are REDACTED to the sentinel unless
    ?include_secrets=1, so an export is shareable without leaking the API key."""
    include_secrets = request.args.get('include_secrets', '').lower() in ('1', 'true', 'yes')
    raw = config_loader.load_config_raw()
    if raw is None:
        # Present-but-unreadable config: refuse rather than serving an EMPTY {}
        # that masquerades as a full backup (the save/import paths already refuse
        # on None for the same reason). {} only legitimately means "fresh install".
        return jsonify({"ok": False,
                        "error": "current config is unreadable — refusing to export an empty "
                                 "backup; repair config.json first"}), 409
    out = dict(raw)
    if not include_secrets:
        for k in config_schema.SECRET_KEYS:
            if out.get(k):
                out[k] = config_schema.SECRET_SENTINEL
    body = json.dumps(out, indent=4, ensure_ascii=False)
    resp = app.response_class(body, mimetype='application/json')
    resp.headers['Content-Disposition'] = 'attachment; filename="fcc-config-export.json"'
    return resp


@app.route('/api/config/import', methods=['POST'])
def api_config_import():
    """L18 Phase 4 — import config SETTINGS from an uploaded JSON. PATCH-only:
    applies ONLY schema-managed server keys present in the file (printer_map /
    dryer_slots / paths / comments are NOT touched — they keep their own editors).
    Body: {"config": {...}, "dry_run": bool}. dry_run returns the diff without
    writing. A secret arriving as the sentinel keeps the existing value."""
    # Parse defensively: request.get_json(silent=True) swallows JSONDecodeError
    # but NOT RecursionError (deeply-nested JSON), which would 500. Cap the body
    # (config is tiny) and catch both -> clean 400/413, the contract the UI expects.
    raw = request.get_data(cache=False, as_text=True) or ''
    if len(raw) > 512 * 1024:
        return jsonify({"ok": False, "error": "import file too large"}), 413
    try:
        payload = json.loads(raw) if raw.strip() else None
    except (ValueError, RecursionError):
        return jsonify({"ok": False, "error": "import file is not valid JSON (or too deeply nested)"}), 400
    if not isinstance(payload, dict):
        return jsonify({"ok": False, "error": "import body must be a JSON object"}), 400
    incoming = payload.get('config')
    if not isinstance(incoming, dict):
        return jsonify({"ok": False, "error": "import body needs a 'config' object"}), 400
    dry_run = bool(payload.get('dry_run'))

    cfg = config_loader.load_config()
    fields = {f.key: f for f in config_schema.CONFIG_SCHEMA if f.scope == 'server'}
    applicable = {k: v for k, v in incoming.items() if k in fields}
    ignored = sorted(k for k in incoming if k not in fields)

    coerced, errors = config_schema.validate_payload(applicable)
    if errors:
        return jsonify({"ok": False, "error": "; ".join(errors), "ignored": ignored}), 400

    # Diff (current -> incoming) for the confirmation overlay; secrets masked.
    diff = []
    for k in sorted(coerced):
        f = fields[k]
        if f.type == 'secret':
            diff.append({"key": k, "label": f.label,
                         "from": "(set)" if cfg.get(k) else "(unset)", "to": "(new secret)"})
        else:
            cur, new = cfg.get(k, f.default), coerced[k]
            if str(cur) != str(new):
                diff.append({"key": k, "label": f.label, "from": cur, "to": new})

    if dry_run:
        return jsonify({"ok": True, "dry_run": True, "diff": diff, "ignored": ignored})

    result = config_loader.save_config(applicable)
    if not result.get('ok'):
        # Validation already passed above. "refusing to save…" = the EXISTING
        # config.json is corrupt (repair it, don't retry) -> 409; anything else is
        # a genuine write/IO fault -> 500.
        err = result.get('error') or ''
        code = 409 if err.startswith('refusing to save') else 500
        state.add_log_entry(f"⚙️ Config import failed: {err}", "ERROR", "ff4444")
        return jsonify({"ok": False, "error": err, "ignored": ignored}), code
    state.add_log_entry(
        f"⚙️ Config imported ({len(result.get('saved') or [])} settings, {len(ignored)} ignored)", "INFO")
    return jsonify({"ok": True, "saved": result.get('saved'), "ignored": ignored, "diff": diff})


# --- FILAMENT ATTRIBUTES MANAGER (L58) ----------------------------------------
# Sibling of L319 (auto-cleanup at startup, schema-level). This is the
# per-record editor side: report which filaments have which flags, and
# apply add/remove in bulk to a chosen set of filament IDs. The bulk-add
# path is the recovery mechanism for the "For Infill" incident — when a
# prior bulk-op stripped a flag from many filaments at once, the user
# can re-stamp it across all affected records without per-record clicks.
#
# /api/filament_attributes/report     GET  → choices + per-filament attrs + counts
# /api/filament_attributes/bulk_set   POST → apply {add:[], remove:[]} to filament_ids
@app.route('/api/filament_attributes/report', methods=['GET'])
def api_filament_attributes_report():
    """Return a snapshot of every filament's filament_attributes value
    plus the canonical choice list and per-choice usage counts."""
    import requests as _req
    sm_url, _ = config_loader.get_api_urls()
    try:
        ch_resp = _req.get(f"{sm_url}/api/v1/field/filament", timeout=10)
        if not ch_resp.ok:
            return jsonify({"success": False, "msg": f"Spoolman field list HTTP {ch_resp.status_code}"})
        fields = ch_resp.json() or []
        attr_field = next((f for f in fields if f.get("key") == "filament_attributes"), None)
        choices = list((attr_field or {}).get("choices") or [])
    except Exception as e:
        return jsonify({"success": False, "msg": f"Spoolman field list error: {e}"})

    try:
        f_resp = _req.get(f"{sm_url}/api/v1/filament", timeout=20)
        if not f_resp.ok:
            return jsonify({"success": False, "msg": f"Spoolman filament list HTTP {f_resp.status_code}"})
        raw = f_resp.json() or []
    except Exception as e:
        return jsonify({"success": False, "msg": f"Spoolman filament list error: {e}"})

    filaments = []
    counts = {c: 0 for c in choices}
    for f in raw:
        fid = f.get("id")
        if fid is None:
            continue
        extras = f.get("extra") or {}
        attrs = spoolman_api._parse_filament_attrs_value(extras.get("filament_attributes"))
        for a in attrs:
            counts[a] = counts.get(a, 0) + 1
        filaments.append({
            "id": fid,
            "name": f.get("name") or "",
            "material": f.get("material") or "",
            "vendor": (f.get("vendor") or {}).get("name") or "",
            "color_hex": f.get("color_hex") or "",
            "archived": bool(f.get("archived")),
            "attributes": attrs,
        })
    filaments.sort(key=lambda x: (x["archived"], (x["vendor"] or "").lower(),
                                  (x["material"] or "").lower(), (x["name"] or "").lower(), x["id"]))
    return jsonify({
        "success": True,
        "choices": choices,
        "filaments": filaments,
        "counts": counts,
    })


@app.route('/api/filament_attributes/bulk_set', methods=['POST'])
def api_filament_attributes_bulk_set():
    """Apply {add: [...], remove: [...]} to filament_attributes on each
    filament in `filament_ids`. Per-filament set semantics (idempotent):
    `add` is union'd into the existing list, `remove` is subtracted.

    Goes through spoolman_api.update_filament which merges the partial
    {extra: {filament_attributes: ...}} payload against the existing
    record's extras (CLAUDE.md write-surface convention — Spoolman's
    PATCH replaces the whole `extra` dict, so partial payloads silently
    wipe siblings otherwise). Surfaces LAST_SPOOLMAN_ERROR per-failure.
    """
    import json as _json
    payload = request.get_json(silent=True) or {}
    ids = payload.get('filament_ids') or []
    add_list = list(payload.get('add') or [])
    remove_list = list(payload.get('remove') or [])
    if not isinstance(ids, list) or not ids:
        return jsonify({"success": False, "msg": "filament_ids must be a non-empty list"}), 400
    if not add_list and not remove_list:
        return jsonify({"success": False, "msg": "Nothing to do — pass `add` and/or `remove`."}), 400

    add_set = {str(x) for x in add_list if str(x)}
    remove_set = {str(x) for x in remove_list if str(x)}

    updated, unchanged, errors = 0, 0, []
    for raw_id in ids:
        try:
            fid = int(raw_id)
        except (ValueError, TypeError):
            errors.append({"id": raw_id, "msg": "not an integer id"})
            continue
        fil = spoolman_api.get_filament(fid)
        if not fil:
            errors.append({"id": fid, "msg": "filament not found"})
            continue
        existing_attrs = spoolman_api._parse_filament_attrs_value(
            (fil.get('extra') or {}).get('filament_attributes')
        )
        existing_set = set(existing_attrs)
        new_set = (existing_set | add_set) - remove_set
        if new_set == existing_set:
            unchanged += 1
            continue
        # Preserve order: keep existing attrs that survive, then append
        # newly-added in user-specified order. Avoids gratuitous shuffles.
        merged = [a for a in existing_attrs if a in new_set]
        for a in add_list:
            sa = str(a)
            if sa in new_set and sa not in merged:
                merged.append(sa)
        result = spoolman_api.update_filament(
            fid, {"extra": {"filament_attributes": _json.dumps(merged)}}
        )
        if result is None:
            errors.append({"id": fid, "msg": spoolman_api.LAST_SPOOLMAN_ERROR or "unknown error"})
            continue
        updated += 1

    state.add_log_entry(
        f"🏷️ Filament Attributes bulk-set: +{sorted(add_set)} / -{sorted(remove_set)} "
        f"across {len(ids)} filament(s) — {updated} updated, {unchanged} unchanged, "
        f"{len(errors)} error(s).",
        "INFO" if not errors else "WARNING",
        "00ccff" if not errors else "ffaa00",
    )
    return jsonify({
        "success": True,
        "updated": updated,
        "unchanged": unchanged,
        "errors": errors,
    })


@app.route('/api/filament_attributes/add_choice', methods=['POST'])
def api_filament_attributes_add_choice():
    """Add a new choice to the Spoolman filament_attributes field. Thin
    wrapper around update_extra_field_choices that scopes to the right
    entity/key and validates the user's input."""
    payload = request.get_json(silent=True) or {}
    choice = str(payload.get('choice', '')).strip()
    if not choice:
        return jsonify({"success": False, "msg": "choice is required"}), 400
    if len(choice) > 80:
        return jsonify({"success": False, "msg": "choice too long (max 80 chars)"}), 400
    res = spoolman_api.update_extra_field_choices('filament', 'filament_attributes', [choice])
    if res.get('success'):
        state.add_log_entry(
            f"🏷️ Filament Attributes: added choice {choice!r}", "INFO", "00ccff"
        )
    return jsonify(res)


@app.route('/api/filament_attributes/remove_choice', methods=['POST'])
def api_filament_attributes_remove_choice():
    """Remove a choice from the Spoolman filament_attributes field.

    Safety: counts usage across all filaments first. If usage > 0 and
    `force` is not truthy, refuses and returns `usage_count` so the UI
    can prompt the user. With `force: true`, strips the choice from
    every filament that carries it BEFORE deleting from the schema —
    that ordering matters so a mid-operation crash doesn't leave the
    field referencing a value still attached to records.
    """
    import json as _json
    import requests as _req
    payload = request.get_json(silent=True) or {}
    choice = str(payload.get('choice', '')).strip()
    force = bool(payload.get('force'))
    if not choice:
        return jsonify({"success": False, "msg": "choice is required"}), 400

    sm_url, _ = config_loader.get_api_urls()
    # Pull current field def + filaments.
    try:
        ch_resp = _req.get(f"{sm_url}/api/v1/field/filament", timeout=10)
        if not ch_resp.ok:
            return jsonify({"success": False, "msg": f"Spoolman field list HTTP {ch_resp.status_code}"})
        fields = ch_resp.json() or []
    except Exception as e:
        return jsonify({"success": False, "msg": f"Spoolman field list error: {e}"})
    attr_field = next((f for f in fields if f.get("key") == "filament_attributes"), None)
    if not attr_field:
        return jsonify({"success": False, "msg": "filament_attributes field not found"})
    current_choices = list(attr_field.get('choices') or [])
    if choice not in current_choices:
        return jsonify({"success": False, "msg": f"{choice!r} is not a current choice"})

    try:
        f_resp = _req.get(f"{sm_url}/api/v1/filament", timeout=20)
        if not f_resp.ok:
            return jsonify({"success": False, "msg": f"Spoolman filament list HTTP {f_resp.status_code}"})
        raw_fils = f_resp.json() or []
    except Exception as e:
        return jsonify({"success": False, "msg": f"Spoolman filament list error: {e}"})

    users = []  # [(fid, attrs)]
    for f in raw_fils:
        fid = f.get('id')
        if fid is None:
            continue
        attrs = spoolman_api._parse_filament_attrs_value(
            (f.get('extra') or {}).get('filament_attributes')
        )
        if choice in attrs:
            users.append((fid, attrs))

    if users and not force:
        return jsonify({
            "success": False,
            "needs_confirm": True,
            "usage_count": len(users),
            "msg": (f"{len(users)} filament(s) still have {choice!r}. "
                    f"Re-send with force=true to strip the tag from those "
                    f"records and delete the choice.")
        })

    # Snapshot the FULL extras dict (raw wire form) per filament — see
    # sweep_unused for the same fix rationale. Sending only
    # {filament_attributes: ...} would make Spoolman's PATCH replace
    # the whole extras dict and wipe siblings (product_url, etc.).
    extras_snapshot = {}
    for f in raw_fils:
        fid = f.get('id')
        if fid is None:
            continue
        extras = f.get('extra') or {}
        if extras:
            extras_snapshot[fid] = dict(extras)

    new_choices = sorted(c for c in current_choices if c != choice)
    try:
        d_resp = _req.delete(
            f"{sm_url}/api/v1/field/filament/filament_attributes", timeout=15
        )
        if not d_resp.ok and d_resp.status_code != 404:
            return jsonify({
                "success": False,
                "msg": f"Schema DELETE failed ({d_resp.status_code}): {d_resp.text[:200]}",
            })
    except Exception as e:
        return jsonify({"success": False, "msg": f"Schema DELETE error: {e}"})

    payload_out = {
        "name": attr_field.get("name") or "Filament Attributes",
        "field_type": attr_field.get("field_type") or "choice",
        "multi_choice": attr_field.get("multi_choice", True),
        "choices": new_choices,
    }
    try:
        post_r = _req.post(
            f"{sm_url}/api/v1/field/filament/filament_attributes",
            json=payload_out, timeout=10,
        )
        if not post_r.ok:
            state.add_log_entry(
                f"⚠ Filament Attributes: deleted field for {choice!r} removal "
                f"but POST recreate failed ({post_r.status_code}): {post_r.text[:200]}. "
                f"Re-run setup_fields.py to restore the schema.",
                "ERROR", "ff4444",
            )
            return jsonify({
                "success": False,
                "msg": f"Schema POST failed: {post_r.text[:200]}. Schema is now MISSING — re-run setup_fields.py.",
            })
    except Exception as e:
        state.add_log_entry(
            f"⚠ Filament Attributes: schema POST error during {choice!r} removal: {e} — "
            f"re-run setup_fields.py to restore.",
            "ERROR", "ff4444",
        )
        return jsonify({"success": False, "msg": f"Schema POST error: {e}"})

    # Restore every filament's FULL extras dict (with the deleted
    # choice filtered out of filament_attributes). Sending the whole
    # dict back is what preserves siblings — partial PATCH on `extra`
    # makes Spoolman replace the whole sub-document. See sweep_unused
    # for the same fix rationale + the regression that pins it.
    restored, restore_failures = 0, []
    for fid, extras_in in extras_snapshot.items():
        extras_out = dict(extras_in)
        if 'filament_attributes' in extras_out:
            attrs = spoolman_api._parse_filament_attrs_value(extras_out['filament_attributes'])
            cleaned = [a for a in attrs if a != choice]
            extras_out['filament_attributes'] = _json.dumps(cleaned)
        # noqa: spoolman-extra-patch — extras_out is the FULL extras
        # snapshot, not a partial dict, so Spoolman's replace-on-PATCH
        # semantics preserve every sibling field. The choice was already
        # filtered out of filament_attributes above. test_no_direct_extra_patch
        # honors this marker as an audited exception.
        try:
            pr = _req.patch(  # noqa: spoolman-extra-patch
                f"{sm_url}/api/v1/filament/{fid}",
                json={"extra": extras_out},
                timeout=10,
            )
            if pr.ok:
                restored += 1
            else:
                restore_failures.append({"id": fid, "msg": f"HTTP {pr.status_code}: {pr.text[:120]}"})
        except _req.RequestException as e:
            restore_failures.append({"id": fid, "msg": str(e)[:200]})

    level = "INFO" if not restore_failures else "WARNING"
    color = "00ccff" if not restore_failures else "ffaa00"
    state.add_log_entry(
        f"🏷️ Filament Attributes: removed choice {choice!r} "
        f"(stripped from {len(users)} filament(s); restored {restored}/{len(extras_snapshot)} "
        f"sibling-attr records"
        + (f"; {len(restore_failures)} restore failure(s)" if restore_failures else "")
        + ").",
        level, color,
    )
    return jsonify({
        "success": True,
        "stripped": len(users),
        "restored": restored,
        "restore_failures": restore_failures,
    })


@app.route('/api/filament_attributes/sweep_unused', methods=['POST'])
def api_filament_attributes_sweep_unused():
    """Find and (optionally) remove every choice with zero usage.

    Replaces the boot-time auto-promote path that was drained 2026-05-20
    to avoid the "add a new choice + forget to tag before next reboot →
    silently re-stripped" footgun. Same capability, but explicitly user-
    triggered: the UI previews the list (`force` omitted/false) and only
    commits with `force: true` after the user confirms.

    Preview shape:  { success, unused: [str, ...], total_choices: int }
    Commit shape:   { success, removed: [str, ...], restored: int,
                      restore_failures: [{id, msg}, ...] }

    `choices` (optional, commit-only): restrict the sweep to a specific
    subset of the unused list. The Choices Manager UI uses this so the
    user can keep some currently-unused tags if they're about to be
    re-applied. The intersection with the freshly-computed unused list
    is enforced server-side — passing in a name that is NOT zero-usage
    will be silently dropped rather than risk wiping a tagged choice.
    """
    import json as _json
    import requests as _req
    payload = request.get_json(silent=True) or {}
    force = bool(payload.get('force'))
    selected_choices = payload.get('choices')
    if selected_choices is not None and not isinstance(selected_choices, list):
        return jsonify({"success": False, "msg": "`choices` must be a list when provided"}), 400

    sm_url, _ = config_loader.get_api_urls()
    try:
        ch_resp = _req.get(f"{sm_url}/api/v1/field/filament", timeout=10)
        if not ch_resp.ok:
            return jsonify({"success": False, "msg": f"Spoolman field list HTTP {ch_resp.status_code}"})
        fields = ch_resp.json() or []
    except Exception as e:
        return jsonify({"success": False, "msg": f"Spoolman field list error: {e}"})
    attr_field = next((f for f in fields if f.get("key") == "filament_attributes"), None)
    if not attr_field:
        return jsonify({"success": False, "msg": "filament_attributes field not found"})
    current_choices = list(attr_field.get('choices') or [])

    try:
        f_resp = _req.get(f"{sm_url}/api/v1/filament", timeout=20)
        if not f_resp.ok:
            return jsonify({"success": False, "msg": f"Spoolman filament list HTTP {f_resp.status_code}"})
        raw_fils = f_resp.json() or []
    except Exception as e:
        return jsonify({"success": False, "msg": f"Spoolman filament list error: {e}"})

    # Transient-state guard: if Spoolman returns zero filaments but the
    # field exists, treat as "ask me later" rather than "everything is
    # unused, nuke them all." Mirrors the same guard in
    # ensure_filament_attributes_cleaned on the auto-cleanup path.
    if not raw_fils:
        return jsonify({
            "success": False,
            "msg": "Spoolman returned 0 filaments — refusing to compute usage from a possibly-transient empty list.",
        })

    # Snapshot the FULL extras dict (raw wire form) per filament so
    # siblings (product_url, nozzle_temp_max, original_color, ...)
    # survive the DELETE → POST → restore cycle. Earlier draft only
    # snapshotted the filament_attributes value and then PATCH'd
    # `{extra: {filament_attributes: ...}}` — which made Spoolman
    # replace the WHOLE extras dict, silently wiping every sibling.
    # Symptom: filaments end up bimodal (only-attrs OR only-siblings,
    # never both). Captured in test_sweep_preserves_sibling_extras.
    usage = {c: 0 for c in current_choices}
    extras_snapshot = {}  # fid -> {full extras dict, raw wire form}
    for f in raw_fils:
        fid = f.get('id')
        if fid is None:
            continue
        extras = f.get('extra') or {}
        if extras:
            extras_snapshot[fid] = dict(extras)
        attrs = spoolman_api._parse_filament_attrs_value(extras.get('filament_attributes'))
        for a in attrs:
            usage[a] = usage.get(a, 0) + 1
    unused = sorted(c for c in current_choices if not usage.get(c))

    if not force:
        return jsonify({
            "success": True,
            "unused": unused,
            "total_choices": len(current_choices),
        })

    # Honor optional `choices` subset. Always intersect with the
    # freshly-computed unused list so an out-of-date client (stale
    # preview) can't ask us to sweep a now-tagged choice.
    if selected_choices is not None:
        unused_set = set(unused) & {str(c) for c in selected_choices}
    else:
        unused_set = set(unused)
    if not unused_set:
        return jsonify({"success": True, "removed": [], "restored": 0, "restore_failures": []})
    unused = sorted(unused_set)
    new_choices = sorted(c for c in current_choices if c not in unused_set)
    try:
        d_resp = _req.delete(
            f"{sm_url}/api/v1/field/filament/filament_attributes", timeout=15
        )
        if not d_resp.ok and d_resp.status_code != 404:
            return jsonify({
                "success": False,
                "msg": f"Schema DELETE failed ({d_resp.status_code}): {d_resp.text[:200]}",
            })
    except Exception as e:
        return jsonify({"success": False, "msg": f"Schema DELETE error: {e}"})

    payload_out = {
        "name": attr_field.get("name") or "Filament Attributes",
        "field_type": attr_field.get("field_type") or "choice",
        "multi_choice": attr_field.get("multi_choice", True),
        "choices": new_choices,
    }
    try:
        post_r = _req.post(
            f"{sm_url}/api/v1/field/filament/filament_attributes",
            json=payload_out, timeout=10,
        )
        if not post_r.ok:
            state.add_log_entry(
                f"⚠ Filament Attributes: sweep deleted field but POST recreate failed "
                f"({post_r.status_code}): {post_r.text[:200]}. Re-run setup_fields.py to restore.",
                "ERROR", "ff4444",
            )
            return jsonify({
                "success": False,
                "msg": f"Schema POST failed: {post_r.text[:200]}. Schema is now MISSING — re-run setup_fields.py.",
            })
    except Exception as e:
        return jsonify({"success": False, "msg": f"Schema POST error: {e}"})

    # Restore each filament's FULL extras dict. Since we only removed
    # zero-usage choices, the filament_attributes value in the snapshot
    # is already correct — but we still pass it through to keep the wire
    # form consistent. The critical piece is sending the WHOLE dict so
    # Spoolman's replace-on-PATCH preserves siblings.
    restored, restore_failures = 0, []
    for fid, extras_in in extras_snapshot.items():
        extras_out = dict(extras_in)
        # Defensive: if any swept choice still appears in this filament's
        # attribute list (shouldn't, since usage was zero), strip it.
        if 'filament_attributes' in extras_out:
            attrs = spoolman_api._parse_filament_attrs_value(extras_out['filament_attributes'])
            cleaned = [a for a in attrs if a not in unused_set]
            extras_out['filament_attributes'] = _json.dumps(cleaned)
        # noqa: spoolman-extra-patch — extras_out is the FULL extras
        # snapshot (siblings preserved); only filament_attributes is filtered.
        # See test_no_direct_extra_patch for the bypass-marker contract.
        try:
            pr = _req.patch(  # noqa: spoolman-extra-patch
                f"{sm_url}/api/v1/filament/{fid}",
                json={"extra": extras_out},
                timeout=10,
            )
            if pr.ok:
                restored += 1
            else:
                restore_failures.append({"id": fid, "msg": f"HTTP {pr.status_code}: {pr.text[:120]}"})
        except _req.RequestException as e:
            restore_failures.append({"id": fid, "msg": str(e)[:200]})

    state.add_log_entry(
        f"🧹 Filament Attributes: swept {len(unused)} unused choice(s): {unused} "
        f"(restored {restored}/{len(extras_snapshot)} sibling records"
        + (f"; {len(restore_failures)} failure(s)" if restore_failures else "")
        + ").",
        "INFO" if not restore_failures else "WARNING",
        "00ccff" if not restore_failures else "ffaa00",
    )
    return jsonify({
        "success": True,
        "removed": unused,
        "restored": restored,
        "restore_failures": restore_failures,
    })


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