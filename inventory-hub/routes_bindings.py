"""Dryer-box bindings / printer map + creds / Quick-Swap routes (L316 step 7).

Moved verbatim from app.py: the dryer-box slot_targets bindings CRUD +
slot-order endpoints, the printer-state probe, the printer_map GET/PUT (with
its private validators _pm_prefix / _printer_map_blocked_removals — their
only caller), the printer_creds PUT (the FilaBridge Phase-2 credential
gate), the all-dryer-box-slots aggregate, single-slot binding PUT, both
Quick-Swap endpoints, and the machine toolhead_slots reverse-lookup.

Preserved semantics (see the carve plan):
- api_printer_state keeps its deliberate function-local prusalink_api import
  (module also imported here at top level, same sys.modules object — tests
  patching app_module.prusalink_api attributes keep intercepting).
- config_loader._canonicalize_printer_map is a deliberate private-name
  cross-module dependency of the PUT validator; carried verbatim.
- api_quickswap_return's unused cfg = config_loader.load_config() is
  vestigial FilaBridge residue — kept verbatim in the pure move (removal
  belongs to the vestigial-FB-artifacts buglist item).

Python 3.9 runtime (the container image) — keep syntax 3.9-safe.
"""
from flask import request, jsonify  # type: ignore

import state  # type: ignore
import config_loader  # type: ignore
import config_schema  # type: ignore
import locations_db  # type: ignore
import spoolman_api  # type: ignore
import logic  # type: ignore
import prusalink_api  # type: ignore

from app_core import app

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

