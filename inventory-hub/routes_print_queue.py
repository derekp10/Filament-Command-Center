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

def _needs_label(item):
    """True when a spool's or filament's `needs_label_print` extra is set. Spoolman
    stores extras as JSON text ("true"); None (never set) and "false" (verified, e.g.
    by scanning its label) are not in the backlog."""
    v = ((item or {}).get('extra') or {}).get('needs_label_print')
    return str(v).strip().strip('"').lower() == 'true'


def backlog_count(spools, spools_error=None, filaments_read=None):
    """The 🏷️ Backlog button's count for the dashboard heartbeat (Group 52.1a).
    `spools` is the heartbeat's own non-archived spool list (the records
    /api/print_queue/pending reads), or None when that read failed. Reads the
    filament list once and counts the records whose `needs_label_print` is set,
    with the same `_needs_label` test the backlog list uses (works on raw and
    parsed extras alike: "true" or True). `filaments_read` (Group 57.2): the
    tick's shared spoolman_api.FilamentListRead, which the low_stock section
    counts from too; without one it reads the list itself.

    Answers {'read_ok': True, 'count', 'spools', 'filaments'}, or
    {'read_ok': False, 'read_error'} when either list couldn't be read, so the
    page keeps the count it shows instead of a false number."""
    if spools is None:
        return {'read_ok': False, 'read_error': f"couldn't read Spoolman's spools ({spools_error})"}
    if filaments_read is not None:
        filaments, err = filaments_read.get(), filaments_read.error
    else:
        filaments, err = spoolman_api.read_filament_list()
    if filaments is None:
        return {'read_ok': False, 'read_error': f"couldn't read Spoolman's filaments ({err})"}
    n_spools = sum(1 for s in spools if isinstance(s, dict) and _needs_label(s))
    n_filaments = sum(1 for f in filaments if isinstance(f, dict) and _needs_label(f))
    return {'read_ok': True, 'count': n_spools + n_filaments,
            'spools': n_spools, 'filaments': n_filaments}


@app.route('/api/print_queue/pending', methods=['GET'])
def api_print_queue_pending():
    filter_type = request.args.get('filter', 'all')
    sort_type = request.args.get('sort', 'created_newest')
    
    sm_url, _ = config_loader.get_api_urls()
    items = []
    
    try:
        # Spoolman's list endpoints IGNORE an `extra=` query filter (they return every
        # record: 2026-10-19, dev's backlog listed 414 items, 53 of which needed a
        # label, so a scanned label never left it). Filter here instead.
        # Group 52.1a: a list that couldn't be read is an error, not a shorter
        # backlog. It used to be skipped silently, so a blip on the spool read
        # answered the filaments alone, and the open backlog showed that as the
        # whole list (and its count on the 🏷️ button).
        # Fetch Spools
        if filter_type in ['all', 'spool']:
            r_spools = requests.get(f"{sm_url}/api/v1/spool", timeout=2)
            if not r_spools.ok:
                return jsonify({"success": False,
                                "msg": f"Spoolman didn't answer the spool list (HTTP {r_spools.status_code})"})
            for s in r_spools.json():
                if not _needs_label(s):
                    continue
                s['type'] = 'spool'
                if 'vendor' in s.get('filament', {}): s['brand'] = s['filament']['vendor'].get('name', 'Unknown')
                items.append(s)

        # Fetch Filaments
        if filter_type in ['all', 'filament']:
            r_fils = requests.get(f"{sm_url}/api/v1/filament", timeout=2)
            if not r_fils.ok:
                return jsonify({"success": False,
                                "msg": f"Spoolman didn't answer the filament list (HTTP {r_fils.status_code})"})
            for f in r_fils.json():
                if not _needs_label(f):
                    continue
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
    # 28.C6 — parse leniently so malformed JSON / wrong content-type return this
    # endpoint's JSON {success:false,msg} contract instead of a framework
    # 400/415 (the api_quickswap idiom).
    data = request.get_json(silent=True) or {}
    item_id = data.get('id')
    item_type = data.get('type')

    # 28.C7 — id=0 is a real (if out-of-range) id, not "missing"; only None /
    # '' / absent count as missing (Spoolman ids start at 1, so 0 will simply
    # fail the lookup below).
    if item_id in (None, '') or not item_type:
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
    # 28.C3–C7 — harmonized with mark_printed (they are mirror endpoints):
    #   C6 lenient parse (JSON error contract, not framework 400/415),
    #   C3 missing-id/type guard, C7 id=0 is a real id (not "missing"),
    #   C4 int-coerce + reject legacy ids, C5 every fall-through carries a msg.
    data = request.get_json(silent=True) or {}
    item_id = data.get('id')
    item_type = data.get('type')

    if item_id in (None, '') or not item_type:
        return jsonify({"success": False, "msg": "Missing ID or Type"})

    try:
        item_id = int(item_id)
    except (ValueError, TypeError):
        return jsonify({"success": False, "msg": "Legacy IDs cannot be flagged. Please scan."})

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
            return jsonify({"success": False, "msg": f"Spool #{item_id} not found"})
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
            return jsonify({"success": False, "msg": f"Filament #{item_id} not found"})
        return jsonify({"success": False, "msg": f"Unknown type: {item_type}"})
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

