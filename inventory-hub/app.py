from flask import Flask, request, jsonify, render_template # type: ignore
import requests # type: ignore
import state # type: ignore
import config_loader # type: ignore
import config_schema # type: ignore
import locations_db # type: ignore
import spoolman_api # type: ignore
import logic # type: ignore
import csv
import os
import json
import logging
import time

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
app = Flask(__name__)

# L347 follow-up — prune old locations.json.pre-*.bak migration backups.
# Each migration that fires writes a timestamped .bak; nothing deletes
# them. A long-running prod install with several schema migrations would
# accumulate one per migration per restart-after-edit.
#
# MUST be defined ABOVE the startup migration/prune block below: that
# block runs at import time and calls _prune_locations_backups(). Before
# 2026-06-01 the def lived ~900 lines lower, so every boot the import-time
# call raised `NameError: name '_prune_locations_backups' is not defined`
# (caught + logged "backup prune skipped") and the prune never ran — .bak
# files accumulated unbounded, defeating the cap. Keep it up here.
MAX_LOCATIONS_BACKUPS = 5


def _prune_locations_backups(json_file_path=None, keep=MAX_LOCATIONS_BACKUPS):
    """Keep at most `keep` of the most-recently-modified
    `locations.json.pre-*.bak` files alongside `json_file_path`. Returns
    the list of deleted paths (empty when under the cap). Failures
    swallow themselves so a permissions issue can't break startup."""
    import glob
    if json_file_path is None:
        json_file_path = locations_db.JSON_FILE
    pattern = f"{json_file_path}.pre-*.bak"
    try:
        matches = glob.glob(pattern)
    except Exception:
        return []
    if len(matches) <= keep:
        return []
    try:
        matches.sort(key=lambda p: os.path.getmtime(p))
    except Exception:
        # If mtime lookup fails (permissions / race) fall through to
        # filename sort — the timestamp in the filename gives the right
        # order as a backstop.
        matches.sort()
    victims = matches[:-keep]
    deleted = []
    for p in victims:
        try:
            os.remove(p)
            deleted.append(p)
        except Exception:
            pass
    return deleted


# One-time feeder_map → slot_targets migration. Kept behind an explicit
# `feeder_map` key check so old installs that still have it get upgraded
# automatically the first time they boot the new code. No-op on modern
# installs where the key has been removed.
#
# Safety: the migration is purely additive (only sets extra.slot_targets
# on Dryer Box records; never removes keys). Spool data lives in
# Spoolman's DB and is untouched. Before the first successful migration
# we still write a timestamped backup of locations.json so there's a
# recovery path if anything ever goes wrong on a production restart.
try:
    _startup_cfg = config_loader.load_config()
    _legacy_feeder_map = _startup_cfg.get('feeder_map') or {}
    if _legacy_feeder_map:
        _startup_locs = locations_db.load_locations_list()
        _migrated, _changed = locations_db.migrate_feeder_map_if_needed(
            _startup_locs, _legacy_feeder_map
        )
        if _changed:
            # Backup before persisting — cheap insurance.
            try:
                import shutil, time as _t
                _stamp = _t.strftime('%Y%m%d-%H%M%S')
                _backup = f"{locations_db.JSON_FILE}.pre-feedermap-migration-{_stamp}.bak"
                shutil.copy2(locations_db.JSON_FILE, _backup)
                state.logger.info(f"📦 Backed up locations.json → {_backup}")
                _prune_locations_backups()
            except Exception as _bk_err:
                state.logger.warning(f"Could not write pre-migration backup: {_bk_err}")
            locations_db.save_locations_list(_migrated)
            state.logger.info("💾 Legacy feeder_map migrated into locations.json — you can safely delete feeder_map from config.json now.")
except Exception as _mig_err:
    state.logger.error(f"feeder_map migration skipped due to error: {_mig_err}")

# Phase-1A locations schema migration: backfill `parent_id` on every row.
# Purely additive — no consumer reads parent_id yet, so a defect here cannot
# affect dashboard rendering, scanning, smart-move, or any UI surface. Sits
# after the feeder_map migration so any rows it touched also get parent_id.
# Idempotent on second boot. See Feature-Buglist.md "[CRITICAL DESIGN —
# blocks Project Color Loadout]" for the multi-phase plan.
try:
    _phase1a_locs = locations_db.load_locations_list()
    _phase1a_migrated, _phase1a_changed = locations_db.migrate_parent_ids_if_needed(_phase1a_locs)
    if _phase1a_changed:
        try:
            import shutil, time as _t
            _stamp = _t.strftime('%Y%m%d-%H%M%S')
            _backup = f"{locations_db.JSON_FILE}.pre-parent-id-migration-{_stamp}.bak"
            shutil.copy2(locations_db.JSON_FILE, _backup)
            state.logger.info(f"📦 Backed up locations.json → {_backup}")
            _prune_locations_backups()
        except Exception as _bk_err:
            state.logger.warning(f"Could not write pre-parent-id-migration backup: {_bk_err}")
        locations_db.save_locations_list(_phase1a_migrated)
        state.logger.info("💾 parent_id backfilled across locations.json — Phase-1A migration complete.")
except Exception as _p1a_err:
    state.logger.error(f"parent_id migration skipped due to error: {_p1a_err}")

# L271 Phase 3 — first-class Printer rows. Persist each printer declared in
# config.json:printer_map as a Type:"Printer" row in locations.json so the
# /api/locations synthesizer no longer has to conjure them at runtime. Sits
# after the parent_id backfill so the new rows are parent_id-stamped (None for
# now — printers stay top-level roots; room-nesting is a later phase per
# Derek 2026-06-03). Also cleans the duplicate blank-Type CORE1 stub. Idempotent
# on second boot (a printer that already has a Type:"Printer" row is skipped);
# timestamped backup before the first write for a prod-restart recovery path.
try:
    _p3_cfg = config_loader.load_config()
    _p3_pm = _p3_cfg.get('printer_map', {}) or {}
    _p3_locs = locations_db.load_locations_list()
    _p3_migrated, _p3_changed = locations_db.migrate_printers_to_rows_if_needed(_p3_locs, _p3_pm)
    if _p3_changed:
        try:
            import shutil, time as _t
            _stamp = _t.strftime('%Y%m%d-%H%M%S')
            _backup = f"{locations_db.JSON_FILE}.pre-printer-rows-migration-{_stamp}.bak"
            shutil.copy2(locations_db.JSON_FILE, _backup)
            state.logger.info(f"📦 Backed up locations.json → {_backup}")
            _prune_locations_backups()
        except Exception as _bk_err:
            state.logger.warning(f"Could not write pre-printer-rows-migration backup: {_bk_err}")
        if locations_db.save_locations_list(_p3_migrated):
            state.logger.info("💾 First-class Printer rows written across locations.json — L271 Phase 3 migration complete.")
        else:
            state.logger.error("❌ L271 Phase 3 printer-rows migration save FAILED — locations.json left unchanged; will retry next boot.")
except Exception as _p3_err:
    state.logger.error(f"printer-rows migration skipped due to error: {_p3_err}")

# L271 Phase 3.5 — true multi-level nesting. Re-derive every row's parent_id
# from the flat first-segment to its IMMEDIATE parent (cart-row→cart, …) and
# nest printers under their room (XL→LR auto-derived from its toolheads'
# Location; CORE1→CR via the recorded override). MUST run AFTER the Phase 3
# printer-rows migration (it keys printers off Type:"Printer") and after the
# Phase 1A backfill (it only re-derives rows still carrying the flat default).
# Idempotent on second boot (changed=False); respects operator-set parent_ids;
# timestamped backup before the first write for a prod-restart recovery path.
try:
    _p35_locs = locations_db.load_locations_list()
    _p35_migrated, _p35_changed = locations_db.migrate_immediate_parent_ids_if_needed(_p35_locs)
    if _p35_changed:
        try:
            import shutil, time as _t
            _stamp = _t.strftime('%Y%m%d-%H%M%S')
            _backup = f"{locations_db.JSON_FILE}.pre-immediate-parent-migration-{_stamp}.bak"
            shutil.copy2(locations_db.JSON_FILE, _backup)
            state.logger.info(f"📦 Backed up locations.json → {_backup}")
            _prune_locations_backups()
        except Exception as _bk_err:
            state.logger.warning(f"Could not write pre-immediate-parent-migration backup: {_bk_err}")
        if locations_db.save_locations_list(_p35_migrated):
            state.logger.info("💾 parent_id re-derived to immediate parents + printers nested under rooms — L271 Phase 3.5 migration complete.")
        else:
            state.logger.error("❌ L271 Phase 3.5 immediate-parent migration save FAILED — locations.json left unchanged; will retry next boot.")
except Exception as _p35_err:
    state.logger.error(f"immediate-parent migration skipped due to error: {_p35_err}")

# L271 Phase 4 (step 1) — fold config.json:printer_map into a `toolheads[]`
# array on each first-class Type:"Printer" row. DUAL-READ: printer_map stays in
# config.json as the source of truth for one release; NO consumer reads
# toolheads[] yet (this is purely additive, like the Phase-1A parent_id
# backfill). MUST run AFTER the Phase 3 printer-rows migration (it keys off
# Type:"Printer" rows). Idempotent on second boot (re-syncs only when
# printer_map changed); timestamped backup before the first write for a
# prod-restart recovery path.
try:
    _p4_cfg = config_loader.load_config()
    _p4_pm = _p4_cfg.get('printer_map', {}) or {}
    _p4_locs = locations_db.load_locations_list()
    _p4_migrated, _p4_changed = locations_db.migrate_printer_map_to_toolheads_if_needed(_p4_locs, _p4_pm)
    if _p4_changed:
        try:
            import shutil, time as _t
            _stamp = _t.strftime('%Y%m%d-%H%M%S')
            _backup = f"{locations_db.JSON_FILE}.pre-toolheads-migration-{_stamp}.bak"
            shutil.copy2(locations_db.JSON_FILE, _backup)
            state.logger.info(f"📦 Backed up locations.json → {_backup}")
            _prune_locations_backups()
        except Exception as _bk_err:
            state.logger.warning(f"Could not write pre-toolheads-migration backup: {_bk_err}")
        if locations_db.save_locations_list(_p4_migrated):
            state.logger.info("💾 printer_map folded into Printer-row toolheads[] — L271 Phase 4 step-1 migration complete.")
        else:
            state.logger.error("❌ L271 Phase 4 toolheads migration save FAILED — locations.json left unchanged; will retry next boot.")
except Exception as _p4_err:
    state.logger.error(f"toolheads migration skipped due to error: {_p4_err}")

# L347 follow-up — also prune at startup so accumulated backups from
# previous boots get trimmed even when no migration fires this boot.
# Cheap glob; idempotent under the cap.
try:
    _pruned = _prune_locations_backups()
    if _pruned:
        state.logger.info(f"🧹 Pruned {len(_pruned)} old locations.json backup(s)")
except Exception as _prune_err:
    state.logger.warning(f"locations.json backup prune skipped: {_prune_err}")

# [ALEX FIX] Suppress Werkzeug Console Spam (Fixes Infinite Log Growth)
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

@app.after_request
def add_header(r):
    r.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return r

@app.route('/')
def dashboard():
    # Load config to generate the correct Spoolman URL
    cfg = config_loader.load_config()
    ip = cfg.get('server_ip', '127.0.0.1')
    if ip == '0.0.0.0': ip = '127.0.0.1'
    port = cfg.get('spoolman_port', 7912)
    sm_url = f"http://{ip}:{port}"
    # [Code Guardian] Fetch FilaBridge URL for Dashboard Button
    _, fb_api_url = config_loader.get_api_urls()
    fb_ui_url = fb_api_url.replace('/api', '')
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
        filabridge_url=fb_ui_url,
        buy_more_template=buy_more_url_template,
    )

# --- HELPER FUNCTIONS ---
def clean_string(s):
    if isinstance(s, str): return s.strip('"').strip("'")
    return s

def hex_to_rgb(hex_str):
    if not hex_str or len(hex_str) < 6: return "", "", ""
    try:
        clean_hex = hex_str.lstrip('#')
        return int(clean_hex[0:2], 16), int(clean_hex[2:4], 16), int(clean_hex[4:6], 16)
    except ValueError:
        return "", "", ""

def get_smart_type(material, extra_data):
    material = clean_string(material) or ""
    raw_attrs = extra_data.get('filament_attributes', '[]')
    try:
        attrs_list = json.loads(raw_attrs) if isinstance(raw_attrs, str) else raw_attrs
        if not isinstance(attrs_list, list): attrs_list = []
    except json.JSONDecodeError: attrs_list = []
    
    clean_attrs = [clean_string(a) for a in attrs_list if a]
    if clean_attrs: return f"{' '.join(clean_attrs)} {material}"
    return material

def get_color_name(item_data):
    extra = item_data.get('extra', {})
    if 'original_color' in extra:
        val = clean_string(extra['original_color'])
        if val: return val
    return item_data.get('name', 'Unknown')

def get_best_hex(item_data):
    extra = item_data.get('extra', {})
    multi_hex = item_data.get('multi_color_hexes') or extra.get('multi_color_hexes')
    if multi_hex:
        first_hex = multi_hex.split(',')[0].strip()
        if first_hex: return first_hex
    return item_data.get('color_hex', '')

def sanitize_label_text(text):
    if not isinstance(text, str): return str(text)
    # 🛠️ EMOJI TRANSLATION MAP
    replacements = {
        "🦝": "Raccoon",
        "⚡": "Bolt",
        "🔥": "Fire",
        "📦": "Box",
        "⚠️": "Warn"
    }
    for char, name in replacements.items():
        text = text.replace(char, name)
    return text

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


def flatten_json(y):
    out = {}
    def flatten(x, name=''):
        if type(x) is dict:
            for a in x:
                flatten(x[a], name + a + '_')
        elif type(x) is list:
            i = 0
            for a in x:
                flatten(a, name + str(i) + '_')
                i += 1
        else:
            out[name[:-1]] = x
    flatten(y)
    return out

# --- PRINT ROUTES ---
@app.route('/api/print_label', methods=['POST'])
def api_print_label():
    sid = request.json.get('id')
    if not sid: return jsonify({"success": False, "msg": "No ID provided"})

    spool = spoolman_api.get_spool(sid)

    # Browser Mode: Just return data
    return jsonify({"success": True, "method": "browser", "data": spool})

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
                if str(old) != str(ev):
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

import external_parsers # Added for plugin architecture


# L347 — bound the filabridge_error_snapshots.json size at the most-recent
# MAX_FB_ERROR_SNAPSHOTS entries. Each filabridge error appends an entry
# that's never deleted; on a long-running prod install this grows forever
# (~1KB per entry — the cost is unbounded disk + the JSON parse on every
# recovery lookup, not catastrophic but real). Python 3.7+ dict preserves
# insertion order, so dropping the head N entries evicts the oldest.
MAX_FB_ERROR_SNAPSHOTS = 100


def _evict_old_fb_snapshots(snapshots, cap=MAX_FB_ERROR_SNAPSHOTS):
    """Return a dict containing at most `cap` of the most-recently-inserted
    entries from `snapshots`. Insertion order is preserved by Python dicts
    (3.7+), so slicing the tail of items() gives the newest survivors."""
    if not isinstance(snapshots, dict) or len(snapshots) <= cap:
        return snapshots
    items = list(snapshots.items())
    return dict(items[-cap:])


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

@app.route('/api/print_batch_csv', methods=['POST'])
def api_print_batch_csv():
    data = request.json
    ids = data.get('ids', [])
    mode = data.get('mode', 'spool')
    clear_old = data.get('clear_old', False)
    
    if not ids: return jsonify({"success": False, "msg": "Empty Queue"})

    cfg = config_loader.load_config()
    
    # --- 1. DETERMINE FILENAME ---
    if mode == 'spool': filename = "labels_spool.csv"
    elif mode == 'location': filename = "labels_locations.csv"
    else: filename = "labels_swatch.csv"
    
    csv_path = cfg.get("print_settings", {}).get("csv_path", filename)
    
    # 🛠️ AUTO-CREATE FOLDER FIX
    if "/" in csv_path or "\\" in csv_path:
        folder = os.path.dirname(csv_path)
        try: 
            os.makedirs(folder, exist_ok=True)
        except Exception as e:
            state.logger.warning(f"Could not create folder {folder}: {e}")
        csv_path = os.path.join(folder, filename)

    try:
        items_to_print = []
        slots_to_print = []

        # --- 2. DEFINE HEADERS ---
        if mode == 'spool':
            core_headers = ['ID', 'Brand', 'Color', 'Type', 'Hex', 'Red', 'Green', 'Blue', 'Weight', 'QR_Code']
        elif mode == 'location':
            # [ALEX FIX] Added 'Slot' to headers
            core_headers = ['LocationID', 'Name', 'Cleaned_Name', 'QR_Code']
        else:
            core_headers = ['ID', 'Brand', 'Color', 'Type', 'Hex', 'Red', 'Green', 'Blue', 'Temp_Nozzle', 'Temp_Bed', 'Density', 'QR_Code']

        # --- 3. PRE-LOAD DATA (Optimization) ---
        loc_lookup = {}
        if mode == 'location':
            # Load local CSV first
            loc_list = locations_db.load_locations_list()
            loc_lookup = {str(row['LocationID']): row for row in loc_list}

        # --- 4. BUILD ROWS ---
        seen_ids = set() # [ALEX FIX] Deduplication tracker

        for item_id in ids:
            # [ALEX FIX] Prevent processing duplicates in the same batch
            if item_id in seen_ids: continue
            seen_ids.add(item_id)

            row_data = {}
            
            # === SPOOL MODE ===
            if mode == 'spool':
                raw_data = spoolman_api.get_spool(item_id)
                if not raw_data: continue
                fil_data = raw_data.get('filament', {})
                vendor_data = fil_data.get('vendor', {})
                fil_extra = fil_data.get('extra', {})
                
                row_data['ID'] = item_id
                row_data['Brand'] = sanitize_label_text(vendor_data.get('name', 'Unknown') if vendor_data else 'Unknown')
                row_data['Color'] = sanitize_label_text(get_color_name(fil_data))
                raw_material = fil_data.get('material', 'Unknown')
                row_data['Type'] = sanitize_label_text(get_smart_type(raw_material, fil_extra))
                hex_val = get_best_hex(fil_data)
                row_data['Hex'] = hex_val
                r, g, b = hex_to_rgb(hex_val)
                row_data['Red'] = r; row_data['Green'] = g; row_data['Blue'] = b
                row_data['Weight'] = f"{raw_data.get('remaining_weight', 0):.0f}g"
                row_data['QR_Code'] = f"ID:{item_id}"
                
                flat_data = flatten_json(raw_data)
                for k, v in flat_data.items():
                    if k not in row_data: row_data[k] = v

            # === LOCATION MODE (HYBRID LOOKUP) ===
            elif mode == 'location':
                # 1. Try Local CSV
                loc_data = loc_lookup.get(str(item_id)) 
                
                if loc_data:
                    name = loc_data.get('Name', 'Unknown')
                else:
                    # 2. Try Spoolman API (Fallback)
                    sm_url, _ = config_loader.get_api_urls()
                    try:
                        resp = requests.get(f"{sm_url}/api/v1/location/{item_id}", timeout=2)
                        if resp.ok:
                            s_data = resp.json()
                            name = s_data.get('name', str(item_id))
                        else:
                            name = str(item_id)
                    except:
                        name = str(item_id)
                
                row_data['LocationID'] = item_id
                row_data['Name'] = name
                # [ALEX FIX] Enforce LOC: prefix for Location QR Codes
                row_data['QR_Code'] = f"LOC:{item_id}" 

                # --- CLEAN NAME & SLOT GENERATION ---
                clean_name = sanitize_label_text(name)
                row_data['Cleaned_Name'] = clean_name

                max_spools = 0
                if loc_data:
                    for k, v in loc_data.items():
                        if k.strip().lower() == 'max spools':
                            try: max_spools = int(v)
                            except: max_spools = 0
                            break
                
                # [ALEX FIX] Removed the DUPLICATE "Slot Generation" block that was here.
                # [ALEX FIX] Added "Slot" column logic.
                if max_spools > 1:
                    for i in range(1, max_spools + 1):
                        slots_to_print.append({
                            "LocationID": item_id,
                            "Slot": f"Slot {i}", # <--- NEW FIELD
                            "Name": f"{name} Slot {i}",
                            "Cleaned_Name": f"{clean_name} Slot {i}",
                            "QR_Code": f"LOC:{item_id}:SLOT:{i}"
                        })

                items_to_print.append(row_data)
                continue 

            # === FILAMENT MODE ===
            else:
                raw_data = spoolman_api.get_filament(item_id)
                if not raw_data: continue
                fil_data = raw_data
                vendor_data = raw_data.get('vendor', {})
                fil_extra = raw_data.get('extra', {})
                
                row_data['ID'] = item_id
                row_data['Brand'] = vendor_data.get('name', 'Unknown') if vendor_data else 'Unknown'
                row_data['Color'] = get_color_name(fil_data)
                raw_material = fil_data.get('material', 'Unknown')
                row_data['Type'] = get_smart_type(raw_material, fil_extra)
                hex_val = get_best_hex(fil_data)
                row_data['Hex'] = hex_val
                r, g, b = hex_to_rgb(hex_val)
                row_data['Red'] = r; row_data['Green'] = g; row_data['Blue'] = b

                t_noz = fil_data.get('settings_extruder_temp')
                row_data['Temp_Nozzle'] = f"{t_noz}°C" if t_noz else ""
                t_bed = fil_data.get('settings_bed_temp')
                row_data['Temp_Bed'] = f"{t_bed}°C" if t_bed else ""
                dens = fil_data.get('density')
                row_data['Density'] = f"{dens} g/cm³" if dens else ""
                row_data['QR_Code'] = f"FIL:{item_id}"

                flat_data = flatten_json(raw_data)
                for k, v in flat_data.items():
                    if k not in row_data: row_data[k] = v
            
            # Append Spool/Filament rows
            if mode != 'location':
                items_to_print.append(row_data)

        if not items_to_print: return jsonify({"success": False, "msg": "No valid data found"})

        # --- SMART HEADER LOGIC ---
        file_exists = os.path.exists(csv_path)
        write_mode = 'w' if clear_old else 'a'
        
        target_headers = []

        if not clear_old and file_exists:
            try:
                with open(csv_path, 'r', encoding='utf-8') as f:
                    reader = csv.reader(f)
                    target_headers = next(reader, None)
            except: pass
        
        if not target_headers:
            target_headers = list(core_headers)
            all_keys = set()
            for item in items_to_print: all_keys.update(item.keys())
            extra_headers = sorted([k for k in all_keys if k not in core_headers])
            target_headers.extend(extra_headers)

        with open(csv_path, write_mode, newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=target_headers, extrasaction='ignore')
            if clear_old or not file_exists: writer.writeheader()
            writer.writerows(items_to_print)

        # --- WRITE SLOTS IF GENERATED ---
        slots_filename = "slots_to_print.csv"
        if slots_to_print:
            slots_path = os.path.join(folder, slots_filename)
            slots_exists = os.path.exists(slots_path)
            
            with open(slots_path, write_mode, newline='', encoding='utf-8') as f:
                # [ALEX FIX] Added "Slot" to fieldnames
                writer = csv.DictWriter(f, fieldnames=["LocationID", "Slot", "Name", "Cleaned_Name", "QR_Code"])
                if clear_old or not slots_exists: writer.writeheader()
                writer.writerows(slots_to_print)

        action_word = "Overwritten" if clear_old else "Appended"
        msg = f"{action_word} {len(items_to_print)} items."
        if slots_to_print: msg += f" (+{len(slots_to_print)} Slots)"
        
        return jsonify({"success": True, "count": len(items_to_print), "file": filename, "msg": msg})

    except PermissionError:
        return jsonify({"success": False, "msg": f"{filename} Locked! Close Excel."})
    except Exception as e:
        state.logger.error(f"Batch CSV Error: {e}")
        return jsonify({"success": False, "msg": str(e)})

# --- EXISTING ROUTES ---

@app.route('/api/locations', methods=['GET'])
def api_get_locations():
    try:
        local_rows = locations_db.load_locations_list()
    except locations_db.LocationsCorruptError as e:
        # Surface the corruption directly instead of falling back to an
        # empty list — silent fallback masks the failure as a UI-wide
        # "Names/Types/Grouping all gone" symptom.
        return jsonify({
            "error": "locations_corrupt",
            "path": str(e.path),
            "line": e.decode_error.lineno,
            "col": e.decode_error.colno,
            "msg": e.decode_error.msg,
        }), 500
    local_map = {str(row['LocationID']).upper(): row for row in local_rows}
    
    # 1. Fetch native Spoolman Locations
    sm_locations = spoolman_api.get_all_locations()
    for sm_loc in sm_locations:
        if not sm_loc or not isinstance(sm_loc, str): continue
        loc_name = sm_loc.strip()
        loc_id_upper = loc_name.upper()
        if loc_id_upper == "UNASSIGNED": continue # Prevent duplicate from legacy strings
        if loc_id_upper and loc_id_upper not in local_map:
            # Create a virtual entry for Spoolman native locations
            local_map[loc_id_upper] = {
                "LocationID": loc_name,
                "Name": loc_name,
                "Type": "Spoolman Native",
                "Max Spools": 0,
                # L271 Phase 2.5: carry parent_id like every other row so the
                # frontend tree reads it uniformly. Derived from the prefix
                # (uppercased); None for a dash-free native name. A Spoolman
                # name can be mixed-case, so the tree grouping in inv_core.js
                # compares parent_id vs LocationID case-insensitively.
                "parent_id": locations_db.derive_parent_id_from_prefix(loc_name),
            }
            
    csv_rows = list(local_map.values())
    occupancy_map: dict[str, int] = {}
    # L271 Phase 3.5 (review fix #2): per-spool (id, loc, ghost) so the ancestor
    # rollup can count DISTINCT physical spools — a deployed spool sits in
    # occupancy_map twice (toolhead loc + ghost home-box) and, now that a printer
    # nests under its home box's room, both rolled into the same room and
    # double-counted its Total. Dedup by spool id fixes that.
    spool_entries: list = []  # (sid, loc_or_'', ghost_or_'')
    unassigned_count: int = 0
    unknown_count: int = 0  # 18.1 — spools sitting at the virtual UNKNOWN bucket

    sm_url, _ = config_loader.get_api_urls()
    try:
        resp = requests.get(f"{sm_url}/api/v1/spool", timeout=5)
        if resp.ok:
            for s in resp.json():
                if not isinstance(s, dict): continue
                loc = str(s.get('location', '')).upper().strip()
                if loc == 'UNASSIGNED': loc = "" # Coerce to true blank
                extra = s.get('extra')
                if not isinstance(extra, dict): extra = {}

                if loc == 'UNKNOWN':
                    unknown_count += 1
                    # Don't add UNKNOWN to occupancy_map — it's a virtual
                    # bucket with no on-disk row to attach to.
                elif loc:
                    if loc not in occupancy_map:
                        occupancy_map[loc] = 1
                    else:
                        occupancy_map[loc] += 1
                else:
                    unassigned_count += 1 # type: ignore # pyre-ignore
                
                # [ALEX FIX] Ghost Occupancy Count
                # Ensure deployed items still count towards their home box's total
                p_source = str(extra.get('physical_source', '')).upper().strip().replace('"', '')
                if p_source and p_source != loc:
                    occupancy_map[p_source] = occupancy_map.get(p_source, 0) + 1

                # L271 Phase 3.5 (review fix #2): record this spool for the
                # distinct-count ancestor rollup. loc is '' for unassigned and
                # 'UNKNOWN' for the lost bucket — neither rolls into a room.
                spool_entries.append((
                    s.get('id'),
                    loc if (loc and loc != 'UNKNOWN') else '',
                    p_source,
                ))

    except: pass

    # [ALEX FIX] Support Room logic correctly by adding grouped floating data
    csv_rows = list(local_map.values())

    # 1. First Pass: TRANSITIVE subtree occupancy (L271 Phase 3.5).
    # parent_id now stores each row's IMMEDIATE parent, so a single-level rollup
    # would drop a spool sitting in a cart-ROW from its room's total (the row
    # rolls into the cart, not the room). For each spool, add its id to every
    # ancestor of BOTH its location and its ghost home-box, then a parent's
    # Total is the count of DISTINCT spool ids in its subtree. Deduping by id is
    # essential: a deployed spool appears at its toolhead loc AND its ghost
    # home-box, which (with the printer nested under the home-box's room) both
    # resolve into the same room — summing would double-count it (review fix #2).
    # `ancestors_of` stops at the PM/PJ/TST pseudo-prefixes so they never
    # aggregate into a room. Leaf display + the "floating" figure still use
    # occupancy_map (loc + ghost at the exact row) so a box keeps showing its
    # deployed ghosts.
    parent_map = locations_db.build_parent_map(csv_rows)

    # Immediate-child counts so a row can be classified parent-vs-leaf for the
    # occupancy display (a real parent shows a subtree Total; a leaf shows
    # curr/max). Pseudo-prefix parents never count as real parents.
    children_count: dict[str, int] = {}
    for _lid, _p in parent_map.items():
        if _p and _p not in locations_db.PSEUDO_ROOM_PREFIXES:
            children_count[_p] = children_count.get(_p, 0) + 1

    subtree_ids: dict[str, set] = {}   # ancestor -> set of distinct spool ids
    ancestor_hit: set[str] = set()     # non-row prefixes that need a Virtual Room
    for sid, loc, ghost in spool_entries:
        touched: set[str] = set()
        for base in (loc, ghost):
            if not base:
                continue
            ancs = list(locations_db.ancestors_of(base, parent_map))
            touched.add(base)
            touched.update(ancs)
            for anc in ancs:
                ancestor_hit.add(anc)
            if not ancs:
                # Top-level / unparented occupancy — its own "room" candidate
                # (mirrors the pre-3.5 seed of a virtual room for a dash-free
                # orphan). A pseudo-prefixed base (PM/PJ/TST box) yields no
                # ancestors and is itself a real row, so synthesis skips it.
                ancestor_hit.add(base)
        for t in touched:
            subtree_ids.setdefault(t, set()).add(sid)
    # subtree_occ = distinct spool count per row; direct/floating stays the
    # loc+ghost count at the exact row (occupancy_map).
    subtree_occ = {k: len(v) for k, v in subtree_ids.items()}
    direct_occ = occupancy_map

    # 2. Inject Virtual Rooms for occupancy-only prefixes.
    #
    # L271 Phase 3: printers are now first-class on-disk Type:"Printer" rows
    # (written by locations_db.migrate_printers_to_rows_if_needed at startup),
    # so this no longer synthesizes them — the printer-prefix seed and the
    # is_printer / printer_name detection were RETIRED. It now only conjures a
    # Virtual Room for a prefix that has spool occupancy today but no on-disk
    # parent row of its own. Any parent that already has a real on-disk row —
    # the first-class Printer rows included — is skipped by the existing-row
    # check below, so they flow through from disk untouched. `ancestor_hit` is
    # the set of prefixes that received rollup (plus dash-free orphan spool
    # locations) — the Phase 3.5 transitive equivalent of the old
    # room_occupancy.keys() candidate set.
    for parent in set(ancestor_hit):
        # Skip a parent that already has a real on-disk row. A blank-Type
        # placeholder (legacy/manual state that would otherwise strand the row
        # in "Unassigned" rendering) is promoted in place instead.
        existing = local_map.get(parent)
        existing_type_blank = bool(existing) and not str(existing.get('Type', '')).strip()
        if existing and not existing_type_blank:
            continue

        synthetic_row = {
            "LocationID": parent,
            "Name": f"{parent} (Room)",
            "Type": "Virtual Room",
            "Max Spools": 0,
            "OccupancyRaw": 0,
            # L271 Phase 2.5: expose parent_id so the frontend tree reads it
            # uniformly. `parent` is a dash-free top-level prefix → null.
            "parent_id": None,
        }

        if existing_type_blank:
            # Replace the broken blank-Type row in-place rather than appending
            # a duplicate (would trip duplicate-LocationID guards downstream).
            for i, r in enumerate(csv_rows):
                if str(r.get('LocationID', '')).upper() == parent:
                    csv_rows[i] = {**r, **synthetic_row}
                    break
        else:
            csv_rows.append(synthetic_row)

    final_list = []
    # [ALEX FIX] Inject Virtual Unassigned Row
    final_list.append({
        "LocationID": "Unassigned",
        "Name": "Workbench / Unsorted",
        "Type": "Virtual",
        "Occupancy": f"{unassigned_count} items",
        "Max Spools": 0,
        "parent_id": None,  # L271 Phase 2.5 — virtual top-level row
    })

    for row in csv_rows:
        lid = str(row.get('LocationID', '')).upper()
        if lid == "UNASSIGNED": continue # Skip if somehow in CSV
        # 18.1 — Skip any on-disk UNKNOWN row too. Derek experimented with
        # creating one manually before this feature landed; an on-disk
        # row with "Spoolman Native" Type would shadow the virtual yellow-
        # band row injected at the bottom. The virtual injection is the
        # single source of truth now. Stale on-disk rows can be deleted
        # via the Location Manager UI without breaking anything.
        if lid == "UNKNOWN": continue
        
        max_s = row.get('Max Spools', '')
        try:
            max_val = int(max_s) if max_s else 0
        except (ValueError, TypeError):
            max_val = 0
            
        direct_cnt = direct_occ.get(lid, 0)
        sub = subtree_occ.get(lid, direct_cnt)

        # L271 Phase 3.5: a row that is a PARENT in the tree (has child rows, or
        # is a synthesized Virtual Room) shows its TRANSITIVE subtree total +
        # the count floating directly at it; a leaf shows curr/max. This
        # replaces the old `"-" not in lid` dash-free gate, so nested parents
        # (carts, printers) now show a real subtree total instead of looking
        # empty when collapsed, and a room's total includes everything beneath
        # it (incl. a nested printer's toolhead spools).
        is_parent = bool(children_count.get(lid)) or str(row.get('Type', '')).strip() == 'Virtual Room'
        if is_parent:
            row['OccupancyRaw'] = sub
            if direct_cnt > 0:
                row['Occupancy'] = f"{sub} Total ({direct_cnt} floating)"
            else:
                row['Occupancy'] = f"{sub} Total"
        else:
            row['OccupancyRaw'] = direct_cnt
            if max_val > 0: row['Occupancy'] = f"{direct_cnt}/{max_val}"
            else: row['Occupancy'] = f"{direct_cnt} items"

        final_list.append(row)

    # 18.1 — virtual UNKNOWN bucket, pinned to the BOTTOM of the list
    # (Derek's pick: bottom over top because spools land here when they're
    # physically misplaced; finding them is the goal, so they shouldn't
    # crowd the top of the manager). Distinct from Unassigned (which is
    # "deliberately on the workbench, awaiting a destination"); Unknown
    # is "we don't know where it actually is — it's not at the location
    # its tag claims." Riff on Unassigned visual treatment but yellow
    # to flag as a caution state. The frontend renders the badge.
    final_list.append({
        "LocationID": "UNKNOWN",
        "Name": "❓ Unknown (Physically Lost)",
        "Type": "Unknown",
        "Occupancy": f"{unknown_count} items",
        "Max Spools": 0,
        "parent_id": None,  # L271 Phase 2.5 — virtual top-level row
    })
    return jsonify(final_list)

@app.route('/api/locations', methods=['POST'])
def api_save_location():
    data = request.json
    old_id = data.get('old_id')
    new_entry = data.get('new_data')
    current_list = locations_db.load_locations_list()
    old_row = None
    if old_id:
        old_row = next((r for r in current_list if r.get('LocationID') == old_id), None)
        current_list = [row for row in current_list if row['LocationID'] != old_id]
        state.add_log_entry(f"📝 Updated: {new_entry['LocationID']}")
    else:
        state.add_log_entry(f"✨ Created: {new_entry['LocationID']}")
    # L271 Phase 3.5 (review fix #4): stamp parent_id at write time, but PRESERVE
    # the existing parent_id on an IN-PLACE edit (same LocationID). The edit
    # modal only sends LocationID/Name/Type/Max Spools — never parent_id — so a
    # naive recompute would un-nest a Printer (immediate_parent_for('XL') → None,
    # there's no dashed ancestor) and silently revert an operator-set parent_id
    # on every field edit. Only CREATE or RENAME (re)derives the immediate parent
    # from the new LocationID; a Printer's room is then (re)resolved by the
    # startup migration. Respect an explicitly-supplied parent_id.
    if isinstance(new_entry, dict) and 'parent_id' not in new_entry:
        same_id = (old_row is not None
                   and str(old_row.get('LocationID', '')) == str(new_entry.get('LocationID', ''))
                   and 'parent_id' in old_row)
        if same_id:
            new_entry['parent_id'] = old_row.get('parent_id')
        else:
            new_entry['parent_id'] = locations_db.immediate_parent_for(
                new_entry.get('LocationID'), current_list)
    current_list.append(new_entry)
    current_list.sort(key=lambda x: str(x.get('LocationID', '')))
    locations_db.save_locations_list(current_list)
    return jsonify({"success": True})

@app.route('/api/locations', methods=['DELETE'])
def api_delete_location():
    target = request.args.get('id', '').strip()
    if not target: return jsonify({"success": False})
    try:
        contents = spoolman_api.get_spools_at_location(target)
        for sid in contents:
            # Best-effort cascade unassign on location delete. Don't raise
            # on individual failures — the location is going away regardless,
            # but log so a user can see partial completion.
            if not spoolman_api.update_spool(sid, {"location": ""}):
                err = spoolman_api.LAST_SPOOLMAN_ERROR or "unknown error"
                state.logger.warning(
                    f"location delete: failed to unassign Spool #{sid} from {target}: {err}"
                )
    except Exception as e:
        state.logger.warning(f"location delete: cascade unassign failed: {e}")
    
    current = locations_db.load_locations_list()
    new_list = [row for row in current if row['LocationID'] != target]
    locations_db.save_locations_list(new_list)
    state.add_log_entry(f"🗑️ Deleted: {target}", "WARNING")
    return jsonify({"success": True})


@app.route('/api/spool/<int:sid>', methods=['DELETE'])
def api_delete_spool(sid):
    """Hard-delete a spool from Spoolman. Triggered from the buried Delete
    action in the spool details modal (see inv_details.js). The frontend
    is responsible for the double-confirm UX (type-the-id pattern); this
    endpoint trusts the request and just executes the delete."""
    snapshot = spoolman_api.get_spool(sid) or {}
    label = f"#{sid}"
    fil = snapshot.get('filament') or {}
    if fil.get('name'):
        label = f"#{sid} ({fil.get('name')})"
    if not spoolman_api.delete_spool(sid):
        err = spoolman_api.LAST_SPOOLMAN_ERROR or "Spoolman rejected the delete"
        state.add_log_entry(f"❌ Failed to delete Spool {label}: {err}", "ERROR", "ff4444")
        return jsonify({"success": False, "error": err}), 502
    state.add_log_entry(f"🗑️ Deleted Spool {label}", "WARNING", "ff8800")
    return jsonify({"success": True, "deleted_spool_id": sid})


@app.route('/api/filament/<int:fid>', methods=['DELETE'])
def api_delete_filament(fid):
    """Cascade-delete a filament: removes every child spool first, then
    deletes the filament itself. Returns a per-spool error list so the
    frontend can surface partial failures.

    Spoolman refuses to delete a filament that still has child spools, so
    cascade is the only correct path from the UI side. Triggered from the
    buried Delete action in the filament details modal — the frontend
    enforces the double-confirm and the "type CONFIRM" cascade prompt."""
    snapshot = spoolman_api.get_filament(fid) or {}
    fil_label = f"#{fid}"
    if snapshot.get('name'):
        fil_label = f"#{fid} ({snapshot.get('name')})"

    children = spoolman_api.get_spools_for_filament(fid)
    deleted_spool_ids = []
    spool_errors = []
    for s in children:
        sid = s.get('id')
        if sid is None:
            continue
        if spoolman_api.delete_spool(sid):
            deleted_spool_ids.append(sid)
        else:
            err = spoolman_api.LAST_SPOOLMAN_ERROR or "Spoolman rejected the delete"
            state.add_log_entry(f"❌ Cascade delete: failed to delete Spool #{sid} (parent Filament {fil_label}): {err}",
                                "ERROR", "ff4444")
            spool_errors.append({"spool_id": sid, "error": err})

    if spool_errors:
        # Don't try to delete the filament if any child spool failed —
        # Spoolman will reject it anyway, and partial state is recoverable.
        return jsonify({
            "success": False,
            "error": "Some child spools could not be deleted; filament left in place.",
            "deleted_spool_ids": deleted_spool_ids,
            "spool_errors": spool_errors,
        }), 502

    if not spoolman_api.delete_filament(fid):
        err = spoolman_api.LAST_SPOOLMAN_ERROR or "Spoolman rejected the delete"
        state.add_log_entry(f"❌ Failed to delete Filament {fil_label}: {err}", "ERROR", "ff4444")
        return jsonify({
            "success": False,
            "error": err,
            "deleted_spool_ids": deleted_spool_ids,
        }), 502

    if deleted_spool_ids:
        state.add_log_entry(
            f"🗑️ Deleted Filament {fil_label} (cascade: {len(deleted_spool_ids)} child spool(s))",
            "WARNING", "ff8800",
        )
    else:
        state.add_log_entry(f"🗑️ Deleted Filament {fil_label}", "WARNING", "ff8800")
    return jsonify({
        "success": True,
        "deleted_filament_id": fid,
        "deleted_spool_ids": deleted_spool_ids,
    })


@app.route('/api/filament/<int:src_fid>/merge_into/<int:dst_fid>', methods=['POST'])
def api_merge_filament(src_fid, dst_fid):
    """Merge `src_fid` into `dst_fid`: re-parent every spool from source to
    target, then delete the now-orphan source filament. Used by the
    "Merge into another filament…" action on the Filament Details modal
    to clean up duplicates that pre-date the tier-1 product-id matcher
    (Group 11.2). Atomic-ish: if any spool re-parent fails, we abort
    before deleting the source so partial state stays recoverable.
    """
    if src_fid == dst_fid:
        return jsonify({
            "success": False,
            "error": "Source and target filaments must differ.",
        }), 400

    src = spoolman_api.get_filament(src_fid)
    if not src:
        return jsonify({
            "success": False,
            "error": f"Source filament #{src_fid} not found.",
        }), 404
    dst = spoolman_api.get_filament(dst_fid)
    if not dst:
        return jsonify({
            "success": False,
            "error": f"Target filament #{dst_fid} not found.",
        }), 404

    src_label = f"#{src_fid}" + (f" ({src.get('name')})" if src.get('name') else "")
    dst_label = f"#{dst_fid}" + (f" ({dst.get('name')})" if dst.get('name') else "")

    # Include archived — they're owned by the source filament too and have to
    # follow it to the target so we can safely delete the source.
    sm_url, _ = config_loader.get_api_urls()
    try:
        r = requests.get(
            f"{sm_url}/api/v1/spool?filament_id={src_fid}&allow_archived=true",
            timeout=5,
        )
        children = r.json() if r.ok else []
    except Exception as e:
        state.logger.error(f"Merge: failed to enumerate spools for filament {src_fid}: {e}")
        return jsonify({
            "success": False,
            "error": f"Could not list source spools: {e}",
        }), 502

    reparented_spool_ids = []
    spool_errors = []
    for s in children:
        sid = s.get('id')
        if sid is None:
            continue
        try:
            spoolman_api.update_spool_or_raise(sid, {"filament_id": dst_fid})
            reparented_spool_ids.append(sid)
        except spoolman_api.SpoolmanRejection as e:
            err = str(e) or "Spoolman rejected the re-parent"
            state.add_log_entry(
                f"❌ Merge {src_label} → {dst_label}: failed to re-parent Spool #{sid}: {err}",
                "ERROR", "ff4444",
            )
            spool_errors.append({"spool_id": sid, "error": err})

    if spool_errors:
        # Abort — leave source intact so the user can retry / inspect.
        return jsonify({
            "success": False,
            "error": "Some spools could not be re-parented; source filament left in place.",
            "reparented_spool_ids": reparented_spool_ids,
            "spool_errors": spool_errors,
        }), 502

    if not spoolman_api.delete_filament(src_fid):
        err = spoolman_api.LAST_SPOOLMAN_ERROR or "Spoolman rejected the delete"
        state.add_log_entry(
            f"❌ Merge {src_label} → {dst_label}: spools re-parented but source delete failed: {err}",
            "ERROR", "ff4444",
        )
        return jsonify({
            "success": False,
            "error": f"Spools re-parented, but source filament delete failed: {err}",
            "reparented_spool_ids": reparented_spool_ids,
        }), 502

    n = len(reparented_spool_ids)
    state.add_log_entry(
        f"🔗 Merged Filament {src_label} → {dst_label} ({n} spool{'' if n == 1 else 's'} re-parented; source deleted)",
        "INFO", "00ccff",
    )
    return jsonify({
        "success": True,
        "source_filament_id": src_fid,
        "target_filament_id": dst_fid,
        "reparented_spool_ids": reparented_spool_ids,
    })


@app.route('/api/undo', methods=['POST'])
def api_undo(): return jsonify(logic.perform_undo())

@app.route('/api/get_contents', methods=['GET'])
def api_get_contents_route():
    loc = request.args.get('id', '').strip().upper()
    return jsonify(spoolman_api.get_spools_at_location_detailed(loc))

@app.route('/api/spool_details', methods=['GET'])
def api_spool_details():
    sid = request.args.get('id')
    if not sid: return jsonify({})
    return jsonify(spoolman_api.get_spool(sid))

@app.route('/api/filament_details', methods=['GET'])
def api_filament_details():
    fid = request.args.get('id')
    if not fid: return jsonify({})
    return jsonify(spoolman_api.get_filament(fid))


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
                if old == new:
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
    url = res.get('url', '')

    # Match FIRST — deciding a match needs only the scanned id vs. stored
    # product_urls, NOT the (slow) prusament.com page fetch. So a no-match
    # "onboard" responds fast (just a Spoolman spool list); the page fetch is
    # deferred to the matched/backfill path and the Add wizard (Stage 3).
    needle = f"/spool/{spool_id}/"
    matched = None
    for s in spoolman_api.get_all_spools(allow_archived=True):
        pu = _pm_norm((s.get('extra') or {}).get('product_url'))
        if pu and needle in pu:
            matched = s
            break

    if not matched:
        state.add_log_entry(
            "🆕 Scanned a Prusament spool that isn't in inventory yet — ready to onboard",
            "INFO", "00ccff",
        )
        return jsonify({"type": "prusament_new", "spool_id": spool_id, "url": url})

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
    if pm_fill and not spoolman_api.update_spool(sid, {'extra': pm_fill}):
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

    return jsonify({
        "type": "prusament_matched",
        "status": "ok",
        "spool_id": sid,
        "filament_id": fid,
        "filament_name": fil.get('name', 'Unknown'),
        "filled": filled,
        "conflicts": suggest,  # frontend (2c) shows the suggest-overlay when non-empty
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
    """Read-only view of config.json's printer_map, grouped for UI use:
    {
      "printers": {
        "🦝 XL": [{"location_id": "XL-1", "position": 0}, ...],
        "🦝 Core One": [...]
      }
    }
    """
    cfg = config_loader.load_config()
    printer_map = cfg.get('printer_map', {}) or {}
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
    return jsonify({"printers": grouped, "entries": flat})


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
    """L18 Phase 3 — persist an edited printer_map. Adding toolheads + editing
    name/position is free; removing/renaming a key still referenced by a
    dryer-box slot or holding spools is BLOCKED (409). Canonicalization + the
    atomic write live in config_loader.save_printer_map."""
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        payload = {}
    new_map = payload.get('printer_map')
    if not isinstance(new_map, dict):
        return jsonify({"ok": False, "error": "printer_map must be an object"}), 400

    old_map = config_loader.load_config().get('printer_map', {}) or {}
    blocked = _printer_map_blocked_removals(old_map, new_map)
    if blocked:
        msg = "Can't remove/rename toolhead(s) still in use: " + "; ".join(
            f"{b['location_id']} ({', '.join(b['reasons'])})" for b in blocked)
        state.add_log_entry(f"⚙️ Printer-map save blocked — {msg}", "ERROR", "ff4444")
        return jsonify({"ok": False, "error": msg, "blocked": blocked}), 409

    result = config_loader.save_printer_map(new_map)
    if result.get('ok'):
        state.add_log_entry(
            f"⚙️ Printer map updated ({len(result.get('printer_map') or {})} toolheads)", "INFO")
        # L271 Phase 3: keep first-class Printer rows in sync with the edited
        # printer_map so a newly-added printer appears immediately — no reboot.
        # (The old runtime synthesizer injected printers on every request; that
        # path is retired, so the migration must run on this write too.)
        # Idempotent + best-effort; never block the printer_map save on it.
        try:
            _pm = result.get('printer_map') or new_map
            _locs = locations_db.load_locations_list()
            _locs, _chg_rows = locations_db.migrate_printers_to_rows_if_needed(_locs, _pm)
            # L271 Phase 4 (step 1): keep each Printer row's toolheads[] in sync
            # with the edited printer_map too (dual-read window). Runs on the same
            # loaded list so a single save persists both, and AFTER the rows
            # migration so a newly-added printer already has its Type:"Printer" row.
            _locs, _chg_th = locations_db.migrate_printer_map_to_toolheads_if_needed(_locs, _pm)
            if (_chg_rows or _chg_th) and not locations_db.save_locations_list(_locs):
                state.logger.error("printer-rows/toolheads sync after printer_map save FAILED to persist.")
        except Exception as _sync_err:
            state.logger.warning(f"printer-rows sync after printer_map save skipped: {_sync_err}")
        return jsonify(result)
    # Validation errors (all start with "printer_map…") are a client 400; write/IO
    # faults bubbled from the hardened writer ("config write failed…", "refusing
    # to save…", "…verify-after-write failed…") are a server 500.
    err = result.get('error') or ''
    code = 400 if err.startswith('printer_map') else 500
    state.add_log_entry(f"⚙️ Printer-map save failed: {err}", "ERROR", "ff4444")
    return jsonify(result), code


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

@app.route('/api/print_location_label', methods=['POST'])
def api_print_location_label():
    # 1. Robust Input Handling
    raw_id = request.json.get('id')
    if not raw_id: return jsonify({"success": False, "msg": "No ID provided"})
    target_id = str(raw_id).strip().upper()
    
    state.logger.info(f"🖨️ [LABEL] Request for: {target_id}")

    # 2. Determine Output Path
    cfg = config_loader.load_config()
    base_path = cfg.get("print_settings", {}).get("csv_path", "labels.csv")
    
    output_dir = os.path.dirname(base_path)
    if not output_dir or (os.name == 'nt' and output_dir.startswith(('/', '\\'))):
        output_dir = "."
    
    if output_dir != ".":
        try: os.makedirs(output_dir, exist_ok=True)
        except: output_dir = "." 

    loc_file = os.path.join(output_dir, "labels_locations.csv")
    slot_file = os.path.join(output_dir, "slots_to_print.csv")

    try:
        locs = locations_db.load_locations_list()
        
        # 3. Robust Lookup 
        loc_data = None
        if target_id == "UNASSIGNED":
             loc_data = {"LocationID": "Unassigned", "Name": "Unassigned", "Max Spools": 0}
        else:
            for row in locs:
                if not isinstance(row, dict): continue
                row_id = ""
                for k, v in row.items():
                    if str(k).strip().lower() == 'locationid': 
                        row_id = str(v).strip().upper()
                        break
                
                if row_id == target_id:
                    loc_data = row
                    break
        
        if not loc_data:
             state.logger.warning(f"❌ [LABEL] ID {target_id} not found in DB")
             return jsonify({"success": False, "msg": "ID Not Found in DB"})

        # Get Name safely
        loc_name = target_id
        if isinstance(loc_data, dict):
            for k, v in loc_data.items():
                if str(k).strip().lower() == 'name':
                    loc_name = str(v)
                    break
        
        # Sanitize
        clean_name = sanitize_label_text(loc_name)

        # 4. Write Main Label
        file_exists = os.path.exists(loc_file)
        with open(loc_file, 'a', newline='', encoding='utf-8') as f:
            headers = ["LocationID", "Name", "Cleaned_Name", "QR_Code"]
            writer = csv.DictWriter(f, fieldnames=headers)
            if not file_exists: writer.writeheader()
            writer.writerow({
                "LocationID": target_id, 
                "Name": loc_name,
                "Cleaned_Name": clean_name,
                "QR_Code": f"LOC:{target_id}" # [ALEX FIX] Added Prefix
            })
            
        # 5. Robust Slot Logic
        max_spools = 1
        if isinstance(loc_data, dict):
            for k, v in loc_data.items():
                if str(k).strip().lower() == 'max spools':
                    try: max_spools = int(v)
                    except: max_spools = 1
                    break
            
        state.logger.info(f"ℹ️ [LABEL] Found {target_id}. Max Spools: {max_spools}")

        slots_generated = False
        if max_spools > 1:
            slot_exists = os.path.exists(slot_file)
            with open(slot_file, 'a', newline='', encoding='utf-8') as f:
                # [ALEX FIX] Added "Slot" field
                headers = ["LocationID", "Slot", "Name", "Cleaned_Name", "QR_Code"]
                writer = csv.DictWriter(f, fieldnames=headers)
                if not slot_exists: writer.writeheader()
                
                for i in range(1, max_spools + 1):
                    writer.writerow({
                        "LocationID": target_id,
                        "Slot": f"Slot {i}",
                        "Name": f"{loc_name} Slot {i}",
                        "Cleaned_Name": f"{clean_name} Slot {i}",
                        "QR_Code": f"LOC:{target_id}:SLOT:{i}"
                    })
            slots_generated = True

        # 6. Build User Message
        abs_path = str(os.path.abspath(output_dir))
        short_path = "..." + abs_path[-30:] if len(abs_path) > 30 else abs_path # type: ignore
        
        msg = f"Queue: {target_id}"
        if slots_generated: msg += f" (+{max_spools} Slots)"
        msg += f" in {short_path}"
        
        return jsonify({"success": True, "msg": msg})

    except Exception as e:
        state.logger.error(f"Print Label Error: {e}")
        return jsonify({"success": False, "msg": str(e)})

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

# --- FILABRIDGE ERROR RECOVERY ROUTES ---

import prusalink_api

@app.route('/api/fb_recovery_spools', methods=['GET'])
def api_fb_recovery_spools():
    import os
    printer_name = request.args.get('printer_name')
    error_id = request.args.get('error_id')
    if not printer_name:
        return jsonify({"success": False, "msg": "Missing printer_name"})
        
    if error_id:
        try:
            snap_path = os.path.join(os.path.dirname(__file__), "data", "filabridge_error_snapshots.json")
            if os.path.exists(snap_path):
                with open(snap_path, 'r', encoding='utf-8') as f:
                    snapshots = json.load(f)
                if error_id in snapshots:
                    return jsonify({"success": True, "spools": snapshots[error_id]})
        except Exception:
            pass
        # L347 — snapshot store is bounded at MAX_FB_ERROR_SNAPSHOTS via
        # _evict_old_fb_snapshots(); an older error_id may have been
        # evicted. Falling through here returns the LIVE spool state at
        # the requested printer instead of the at-error snapshot. For
        # most recovery flows the live state is what the user actually
        # wants anyway; the snapshot was just a "what was on the
        # toolhead at the moment FilaBridge errored" reference. Missing
        # snapshot is NOT an error — only a missing printer_name is.
    
    printer_map = locations_db.get_active_printer_map()  # L271 P4 step 2: Printer-row toolheads[] (dual-read)

    # Find which FilaBridge toolheads map to which spoolman location keys
    # Typically, the location ID is the key in printer_map, and it has 'printer_name'
    target_locations = []
    for loc_id, p_info in printer_map.items():
        if p_info.get('printer_name') == printer_name:
            target_locations.append(loc_id)
            
    if not target_locations:
        return jsonify({"success": False, "msg": "Printer name not found in printer_map"})
        
    spools = []
    for loc in target_locations:
        loc_spools = spoolman_api.get_spools_at_location_detailed(loc)
        spools.extend(loc_spools)
        
    return jsonify({"success": True, "spools": spools})

@app.route('/api/fb_parse_status', methods=['GET'])
def api_fb_parse_status():
    import prusalink_api
    return jsonify({"msg": prusalink_api.FB_PARSE_STATUS})

@app.route('/api/fb_aggressive_parse', methods=['POST'])
def api_fb_aggressive_parse():
    data = request.json
    printer_name = data.get('printer_name')
    filename = data.get('filename')
    error_id = data.get('error_id')
    
    if not all([printer_name, filename, error_id]):
        return jsonify({"success": False, "msg": "Missing parameters"})
        
    _, fb_url = config_loader.get_api_urls()
    fb_base = fb_url.replace('/api', '')
    
    # 1. Fetch credentials
    creds = prusalink_api.fetch_printer_credentials(fb_url, printer_name)
    if not creds:
        return jsonify({"success": False, "msg": "Could not fetch printer credentials from FilaBridge"})
        
    ip_addr = creds['ip_address']
    api_key = creds['api_key']
    
    # 2. Parse GCode
    state.add_log_entry(f"🔍 Starting aggressive parse for '{filename}' on {printer_name}...", "INFO")
    usage_map = prusalink_api.download_gcode_and_parse_usage(ip_addr, api_key, filename)
    
    if not usage_map:
        return jsonify({"success": False, "msg": "Failed to parse filament usage from GCode"})
        
    # 3. Apply weights to mapped spools
    cfg = config_loader.load_config()
    printer_map = locations_db.get_active_printer_map()  # L271 P4 step 2: Printer-row toolheads[] (dual-read)

    _, _fb_url_for_mmu = config_loader.get_api_urls()
    active_locs = _resolve_active_locs_for_printer(printer_map, printer_name, _fb_url_for_mmu)
    spools_updated = 0
    # Track positions we've already processed so MMU-alias entries (CORE1-M0
    # vs CORE1-M1 — same position in printer_map) don't double-deduct the
    # same gcode usage slice.
    processed_positions = set()
    for loc_id, p_info in active_locs:
        toolhead_idx = p_info.get('position', 0)
        if toolhead_idx in processed_positions:
            continue
        if toolhead_idx in usage_map:
            weight_used = usage_map[toolhead_idx]
            loc_spools = spoolman_api.get_spools_at_location(loc_id)
            if not loc_spools:
                continue  # try the next alias for this position
            processed_positions.add(toolhead_idx)
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
                        info = spoolman_api.format_spool_display(spool_data)
                        strat = "Fast-Fetch" if "Fast" in prusalink_api.FB_PARSE_STATUS else "RAM-Fetch"
                        state.add_log_entry(f"✔️ Auto-deducted {weight_used:.1f}g from Spool #{sid} ({strat}): [{remaining:.1f}g at start ➔ {new_remaining:.1f}g remaining]", "SUCCESS", info['color'])
                    else:
                        err = spoolman_api.LAST_SPOOLMAN_ERROR or "unknown error"
                        state.add_log_entry(
                            f"❌ Failed to auto-deduct from Spool #{sid}: {err}", "ERROR", "ff4444"
                        )

    # 4. Acknowledge Error
    if spools_updated > 0:
        ack = prusalink_api.acknowledge_filabridge_error(fb_url, error_id)
        if ack:
            return jsonify({"success": True, "msg": f"Successfully parsed and updated {spools_updated} spools."})
        else:
            return jsonify({"success": True, "msg": "Updated spools but failed to acknowledge error."})
            
    return jsonify({"success": False, "msg": "Parsed usage but no matching active spools found."})

@app.route('/api/fb_manual_recovery', methods=['POST'])
def api_fb_manual_recovery():
    data = request.json
    error_id = data.get('error_id')
    updates = data.get('updates', {}) # dict of sid -> weight_used (diff)
    
    if not error_id:
        return jsonify({"success": False, "msg": "Missing error_id"})
        
    spools_updated = 0
    for sid, weight_used in updates.items():
        try:
            w = float(weight_used)
            if w > 0:
                spool_data = spoolman_api.get_spool(sid)
                if spool_data:
                    used = float(spool_data.get('used_weight', 0))
                    initial = float(spool_data.get('initial_weight', 0) or 0)
                    remaining = max(0, initial - used)
                    new_remaining = max(0, remaining - w)
                    new_used = used + w
                    if spoolman_api.update_spool(sid, {"used_weight": new_used}):
                        spools_updated += 1
                        info = spoolman_api.format_spool_display(spool_data)
                        state.add_log_entry(f"✔️ Manually deducted {w:.1f}g from Spool #{sid}: [{remaining:.1f}g at start ➔ {new_remaining:.1f}g remaining]", "SUCCESS", info['color'])
                    else:
                        err = spoolman_api.LAST_SPOOLMAN_ERROR or "unknown error"
                        state.add_log_entry(
                            f"❌ Failed to manually deduct from Spool #{sid}: {err}", "ERROR", "ff4444"
                        )
        except ValueError:
            pass
            
    _, fb_url = config_loader.get_api_urls()
    prusalink_api.acknowledge_filabridge_error(fb_url, error_id)

    return jsonify({"success": True, "msg": f"Updated {spools_updated} spools."})


# --- FILABRIDGE ↔ SPOOLMAN RECONCILE (L324) -----------------------------------
# Cross-checks every non-zero FilaBridge toolhead_mapping against the
# spool's Spoolman `location` field. Surfaces mismatches that the
# `_fb_spool_location()` pre-flight in logic.py prevents from being
# created NEW but doesn't heal once they exist (manual DB edits, prior
# bugs, the retired suppress_fb_unmap path, etc.).
#
# /api/filabridge/reconcile           GET  → list of mismatches
# /api/filabridge/reconcile/apply     POST → resolve one mismatch
#
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


@app.route('/api/filabridge/reconcile', methods=['GET'])
def api_filabridge_reconcile():
    """Walk FilaBridge /status, cross-check against Spoolman per-spool
    location. Return a JSON payload listing each mismatch with both views
    so the UI can offer 'Trust Spoolman' / 'Trust FilaBridge' actions."""
    _, fb_url = config_loader.get_api_urls()
    try:
        resp = requests.get(f"{fb_url}/status", timeout=5)
        if not resp.ok:
            return jsonify({"success": False, "msg": f"FilaBridge /status returned {resp.status_code}"})
        fb_data = resp.json() or {}
    except requests.RequestException as e:
        return jsonify({"success": False, "msg": f"FilaBridge unreachable: {e}"})

    printer_map = locations_db.get_active_printer_map()  # L271 P4 step 2: Printer-row toolheads[] (dual-read)
    # Build a reverse: (printer_name, position) → location_id, for the
    # mapping side that FB exposes as raw position numbers.
    pos_to_loc = {}
    for loc_id, info in printer_map.items():
        key = (info.get('printer_name'), int(info.get('position', 0)))
        pos_to_loc[key] = loc_id.upper()

    mismatches = []
    matched = 0
    fb_mappings = fb_data.get('toolhead_mappings', {}) or {}
    for _printer_key, toolheads in fb_mappings.items():
        for th_id, entry in (toolheads or {}).items():
            try:
                spool_id = int((entry or {}).get('spool_id') or 0)
            except (TypeError, ValueError):
                continue
            if spool_id <= 0:
                continue
            try:
                th_pos = int(th_id)
            except (TypeError, ValueError):
                continue
            fb_printer = (entry or {}).get('printer_name') or _printer_key
            fb_loc = pos_to_loc.get((fb_printer, th_pos))
            if not fb_loc:
                mismatches.append({
                    "spool_id": spool_id,
                    "fb_printer": fb_printer,
                    "fb_toolhead": th_pos,
                    "fb_location": None,
                    "sm_location": None,
                    "reason": "FilaBridge reports a toolhead position with no matching entry in printer_map; unmap recommended.",
                })
                continue
            sp = spoolman_api.get_spool(spool_id) or {}
            sm_loc = str(sp.get('location') or '').strip().upper()
            if sm_loc == fb_loc:
                matched += 1
                continue
            mismatches.append({
                "spool_id": spool_id,
                "fb_printer": fb_printer,
                "fb_toolhead": th_pos,
                "fb_location": fb_loc,
                "sm_location": sm_loc or None,
                "spool_display": spoolman_api.format_spool_display(sp).get('text', f"#{spool_id}") if sp else f"#{spool_id}",
                "reason": (
                    "FilaBridge says this spool is on the listed toolhead; "
                    "Spoolman records a different location. They diverged at some "
                    "point — likely a stale ghost from before _fb_spool_location pre-flight landed."
                ),
            })
    return jsonify({"success": True, "matched": matched, "mismatches": mismatches})


@app.route('/api/filabridge/reconcile/apply', methods=['POST'])
def api_filabridge_reconcile_apply():
    """Resolve one mismatch.

    Payload:
      {
        "spool_id": int,
        "action": "trust_spoolman" | "trust_filabridge",
        "fb_printer": str,
        "fb_toolhead": int,
        "fb_location": str | null,     # required for trust_filabridge
        "sm_location": str | null,
      }
    """
    data = request.json or {}
    action = data.get('action')
    spool_id = data.get('spool_id')
    fb_printer = data.get('fb_printer')
    try:
        fb_toolhead = int(data.get('fb_toolhead'))
    except (TypeError, ValueError):
        return jsonify({"success": False, "msg": "fb_toolhead must be an int"})
    if not spool_id or action not in ('trust_spoolman', 'trust_filabridge'):
        return jsonify({"success": False, "msg": "Bad payload"})

    _, fb_url = config_loader.get_api_urls()
    if action == 'trust_spoolman':
        # Clear FilaBridge's stale toolhead entry; Spoolman's location wins.
        ok, detail = logic._fb_write(fb_printer, fb_toolhead, 0, fb_url)
        if ok:
            state.add_log_entry(
                f"🔧 Reconcile: cleared FilaBridge {fb_printer}-{fb_toolhead} (trusted Spoolman for Spool #{spool_id})",
                "SUCCESS", "00ff00",
            )
            return jsonify({"success": True})
        state.add_log_entry(
            f"❌ Reconcile: failed to clear FilaBridge {fb_printer}-{fb_toolhead}: {detail}",
            "ERROR", "ff4444",
        )
        return jsonify({"success": False, "msg": detail})

    # action == 'trust_filabridge'
    fb_location = (data.get('fb_location') or '').strip().upper()
    if not fb_location:
        return jsonify({"success": False, "msg": "fb_location required for trust_filabridge"})
    sp = spoolman_api.get_spool(spool_id) or {}
    extra = dict((sp.get('extra') or {}))
    # Don't disturb container_slot / physical_source — perform_smart_move
    # would, but this is a "rewrite Spoolman to match the truth FilaBridge
    # already accepted" operation, so we leave the system-managed extras
    # alone and only set the location field.
    if spoolman_api.update_spool(spool_id, {"location": fb_location, "extra": extra}):
        state.add_log_entry(
            f"🔧 Reconcile: set Spoolman #{spool_id} location → {fb_location} (trusted FilaBridge)",
            "SUCCESS", "00ff00",
        )
        return jsonify({"success": True})
    err = spoolman_api.LAST_SPOOLMAN_ERROR or "unknown error"
    state.add_log_entry(
        f"❌ Reconcile: Spoolman rejected #{spool_id} → {fb_location}: {err}",
        "ERROR", "ff4444",
    )
    return jsonify({"success": False, "msg": err})


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
    sm_url, fb_url = config_loader.get_api_urls()
    sm_ok, fb_ok = False, False
    try: sm_ok = requests.get(f"{sm_url}/api/v1/health", timeout=3).ok
    except: pass
    
    try:
        # FilaBridge liveness probe (drives the status dot). Use /print-errors
        # — the lightweight endpoint we need anyway — NOT /status. The dedicated
        # /status endpoint polls every printer's live PrusaLink state and takes
        # ~5-6s to return on a prod-sized fleet, well past the old timeout=3, so
        # it timed out on EVERY heartbeat and pinned the dot RED even though
        # FilaBridge was up and serving (Derek 2026-06-02 "constantly red, even
        # though it's active"). It also added ~6s of latency to every dashboard
        # pulse since this runs in the /api/logs heartbeat path. /print-errors
        # returns ~instantly, so one fast call is both the liveness check AND
        # the error poll.
        fb_resp = requests.get(f"{fb_url}/print-errors", timeout=4)
        fb_ok = fb_resp.ok

        # [NEW] Check for FilaBridge Print Errors
        if fb_ok:
            try:
                err_resp = fb_resp  # reuse the liveness response — no second fetch
                if err_resp.ok:
                    # `errors` can be null when there are none; coerce to [].
                    fb_errors = err_resp.json().get('errors') or []

                    cfg = config_loader.load_config()
                    auto_recover = cfg.get("auto_recover_filabridge_errors", True)
                    
                    for err in fb_errors:
                        err_id = err.get('id')
                        # Only alert if we haven't seen it and the user hasn't naturally acknowledged it in FilaBridge
                        if err_id and not err.get('acknowledged', False):
                            if err_id not in state.ACKNOWLEDGED_FILABRIDGE_ERRORS:
                                state.ACKNOWLEDGED_FILABRIDGE_ERRORS.add(err_id)
                                p_name = err.get('printer_name', 'Unknown Printer')
                                f_name = err.get('filename', 'Unknown File')
                                err_msg = err.get('error', 'Unknown Error')
                                
                                # Snapshot active spools at time of error
                                try:
                                    import os
                                    target_locations = []
                                    printer_map = locations_db.get_active_printer_map()  # L271 P4 step 2: dual-read
                                    for loc_id, p_info in printer_map.items():
                                        if p_info.get('printer_name') == p_name:
                                            target_locations.append(loc_id)
                                    spools = []
                                    for loc in target_locations:
                                        spools.extend(spoolman_api.get_spools_at_location_detailed(loc))
                                    snap_path = os.path.join(os.path.dirname(__file__), "data", "filabridge_error_snapshots.json")
                                    snapshots = {}
                                    if os.path.exists(snap_path):
                                        with open(snap_path, 'r', encoding='utf-8') as f:
                                            snapshots = json.load(f)
                                    snapshots[err_id] = spools
                                    # L347 — bound the snapshot store; see
                                    # _evict_old_fb_snapshots above for rationale.
                                    snapshots = _evict_old_fb_snapshots(snapshots)
                                    os.makedirs(os.path.dirname(snap_path), exist_ok=True)
                                    with open(snap_path, 'w', encoding='utf-8') as f:
                                        json.dump(snapshots, f)
                                except Exception as snap_e:
                                    state.logger.error(f"Failed to snapshot spools for error {err_id}: {snap_e}")

                                def _auto_recover_task(e_id, printer_name, filename, error_msg):
                                    state.add_log_entry(f"🔄 Auto-Recovering FilaBridge Error for {printer_name}...", "INFO")
                                    creds = prusalink_api.fetch_printer_credentials(fb_url, printer_name)
                                    if creds:
                                        usage_map = prusalink_api.download_gcode_and_parse_usage(creds['ip_address'], creds['api_key'], filename)
                                        if usage_map:
                                            printer_map = locations_db.get_active_printer_map()  # L271 P4 step 2 (dual-read)
                                            spools_updated = 0
                                            # Same MMU-alias dedup as the primary auto-deduct path.
                                            ar_active_locs = _resolve_active_locs_for_printer(printer_map, printer_name, fb_url)
                                            ar_processed_positions = set()
                                            for loc_id, p_info in ar_active_locs:
                                                toolhead_idx = p_info.get('position', 0)
                                                if toolhead_idx in ar_processed_positions:
                                                    continue
                                                if toolhead_idx in usage_map:
                                                    w_used = usage_map[toolhead_idx]
                                                    loc_spools = spoolman_api.get_spools_at_location(loc_id)
                                                    if not loc_spools:
                                                        continue
                                                    ar_processed_positions.add(toolhead_idx)
                                                    for sid in loc_spools:
                                                        spool = spoolman_api.get_spool(sid)
                                                        if spool and w_used > 0:
                                                            used = float(spool.get('used_weight', 0))
                                                            initial = float(spool.get('initial_weight', 0) or 0)
                                                            remaining = max(0, initial - used)
                                                            new_rem = max(0, remaining - w_used)
                                                            new_used = used + w_used
                                                            if spoolman_api.update_spool(sid, {"used_weight": new_used}):
                                                                spools_updated += 1
                                                                inf = spoolman_api.format_spool_display(spool)
                                                                strat = "Fast-Fetch" if "Fast" in prusalink_api.FB_PARSE_STATUS else "RAM-Fetch"
                                                                state.add_log_entry(f"✔️ Auto-deducted {w_used:.1f}g from Spool #{sid} ({strat}): [{remaining:.1f}g at start ➔ {new_rem:.1f}g remaining]", "SUCCESS", inf['color'])
                                                            else:
                                                                err = spoolman_api.LAST_SPOOLMAN_ERROR or "unknown error"
                                                                state.add_log_entry(
                                                                    f"❌ Auto-recover failed for Spool #{sid}: {err}",
                                                                    "ERROR", "ff4444"
                                                                )
                                            if spools_updated > 0:
                                                prusalink_api.acknowledge_filabridge_error(fb_url, e_id)
                                                return # Success
                                                
                                    # Fallback if auto-recover fails or wasn't applicable
                                    state.add_log_entry(
                                        f"🔴 FilaBridge: [{printer_name}] failed to parse weight for '{filename}': {error_msg}",
                                        "WARNING",
                                        meta={"type": "filabridge_error", "error_id": e_id, "printer_name": printer_name, "filename": filename}
                                    )

                                if auto_recover:
                                    import threading
                                    threading.Thread(target=_auto_recover_task, args=(err_id, p_name, f_name, err_msg), daemon=True).start()
                                else:
                                    state.add_log_entry(
                                        f"🔴 FilaBridge: [{p_name}] failed to parse weight for '{f_name}': {err_msg}",
                                        "WARNING",
                                        meta={"type": "filabridge_error", "error_id": err_id, "printer_name": p_name, "filename": f_name}
                                    )
            except Exception as e:
                pass # Don't crash the log poller if FilaBridge errors endpoint times out
                
    except: pass
    
    return jsonify({
        "logs": state.RECENT_LOGS,
        "undo_available": len(state.UNDO_STACK) > 0,
        "audit_active": state.AUDIT_SESSION.get('active', False),
        "status": {"spoolman": sm_ok, "filabridge": fb_ok}
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
    audit-idle-watchdog and FilaBridge error auto-recover side effects
    because the bulk endpoint REPLACES the legacy heartbeat that used
    to drive them - losing them would silently break audit cancellation
    and recovery."""
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
        # so the widget ticks for dryer-box-less printers (L56).
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
                'filabridge': logs_payload['status'].get('filabridge', False),
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
    app.run(host='0.0.0.0', port=8000, use_reloader=_dev, debug=False)