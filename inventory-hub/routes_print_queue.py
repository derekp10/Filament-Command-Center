"""Print-queue + label-flag routes (L316 step 8).

Moved verbatim from app.py: /api/print_queue/pending (raw requests.get to
Spoolman with the inline URL-encoded extra filter — deliberately bypasses
spoolman_api; tests patch 'requests.get' directly), mark_printed and
set_flag (full-extra read-modify-write Spoolman surfaces; their behavioral
asymmetries — int-coercion, missing-id handling, HTTP-200 error bodies —
are pinned by tests/test_l316_charact_queue_flags.py, do not normalize),
and the Group 23.3 /api/filament/<fid>/flag_spool_labels bulk-flag endpoint
(deliberate PARTIAL extra write relying on _merge_extras_with_existing
sibling preservation).

Python 3.9 runtime (the container image) — keep syntax 3.9-safe.
"""
from flask import request, jsonify  # type: ignore
import requests  # type: ignore

import state  # type: ignore
import config_loader  # type: ignore
import spoolman_api  # type: ignore

from app_core import app

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
    # 27.3 — also catch TypeError: a JSON-array/object id (e.g. [123]) raises
    # TypeError from int(), which a ValueError-only guard let escape as an
    # unhandled 500. Non-scalar ids now return the same JSON error contract.
    try:
        item_id = int(item_id)
    except (ValueError, TypeError):
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

