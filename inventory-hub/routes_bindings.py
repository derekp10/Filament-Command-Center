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
- api_quickswap_return's unused cfg = config_loader.load_config() was
  vestigial FilaBridge residue — REMOVED in Group 29 (finding 45), so it is
  no longer part of the vestigial-FB-artifacts buglist item.

Python 3.9 runtime (the container image) — keep syntax 3.9-safe.
"""
import re

from flask import request, jsonify  # type: ignore

import state  # type: ignore
import config_loader  # type: ignore
import config_schema  # type: ignore
import locations_db  # type: ignore
import spoolman_api  # type: ignore
import logic  # type: ignore
import prusalink_api  # type: ignore
import placement  # type: ignore

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
    # Group 39.3: "FCC has no login for XL" is not "couldn't reach XL". The probe
    # returns None for both, so check the Printer row's credentials first (a
    # locations.json read, no network): the fix is entering the login, not
    # checking the network.
    creds = prusalink_api.fetch_printer_credentials(fb_url, printer_name)
    if not creds or not creds.get('ip_address'):
        return jsonify({"known": False, "reason": "no_credentials", "printer_name": printer_name})
    result = prusalink_api.get_printer_state(fb_url, printer_name)
    if not result:
        return jsonify({"known": False, "reason": "prusalink_unreachable", "printer_name": printer_name})
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
    #
    # Hotfix 2026-09-29: `printer_rows` is the same view per Printer ROW, keyed by
    # LocationID — what the editor renders and saves against, so a rename or a
    # shared Name can no longer point the grid at one row and the save at
    # another. `printer_creds` (by Name) stays for older callers; on a shared
    # Name it now shows the row that holds an ip, matching the runtime lookup.
    creds_view = {}
    printer_rows = []
    for _row in (loc_rows or []):
        if not isinstance(_row, dict) or str(_row.get('Type', '')).strip().lower() != 'printer':
            continue
        _nm = str(_row.get('Name', ''))
        _c = _row.get(locations_db.PRINTER_CREDS_KEY)
        _c = _c if isinstance(_c, dict) else {}
        _view = {
            "ip_address": (_c.get("ip_address") or ""),
            "api_key": config_schema.SECRET_SENTINEL if _c.get("api_key") else "",
        }
        printer_rows.append({
            "location_id": str(_row.get('LocationID', '')).strip().upper(),
            "name": _nm,
            **_view,
            "toolhead_count": sum(1 for _t in (_row.get('toolheads') or []) if isinstance(_t, dict)),
        })
        if not _nm:
            continue
        if _nm in creds_view and creds_view[_nm]["ip_address"] and not _view["ip_address"]:
            continue
        creds_view[_nm] = _view
    printer_rows.sort(key=lambda p: (p["name"].lower(), p["location_id"]))
    return jsonify({"printers": grouped, "entries": flat, "printer_creds": creds_view,
                    "printer_rows": printer_rows})


@app.route('/api/printer_creds', methods=['PUT'])
def api_put_printer_creds():
    """FilaBridge Phase-2: set a printer's PrusaLink connection (ip_address +
    api_key) on its Type:"Printer" row in locations.json. Powers the "Printer
    Connections" block in the printer-map editor.

    SECRET_SENTINEL contract for api_key (mirrors the Config editor): receiving
    the sentinel means "unchanged" → keep the stored key; any other value
    replaces it (empty string → no key). A blank ip_address CLEARS the whole
    creds object. Body: {location_id | printer_name, ip_address, api_key}.

    Hotfix 2026-09-29: `location_id` (the Printer row's LocationID) is the
    editor's address and wins when sent — 404 unless it names a Printer row.
    `printer_name` remains for older callers — 404 if no Printer row carries it."""
    payload = request.get_json(silent=True) or {}
    name = str(payload.get('printer_name', '')).strip()
    loc_id = str(payload.get('location_id', '') or '').strip().upper()
    ip = str(payload.get('ip_address', '') or '').strip()
    api_key_in = payload.get('api_key', '')
    if not name and not loc_id:
        return jsonify({"ok": False, "error": "printer_name is required"}), 400
    # Hotfix 2026-09-29: a blank IP clears the whole connection, so a NEW key sent
    # with a blank IP used to delete the saved connection while the editor toasted
    # success — refuse it instead (blank IP + blank/sentinel key still clears).
    if not ip and api_key_in not in (None, '', config_schema.SECRET_SENTINEL):
        return jsonify({"ok": False,
                        "error": "Enter the printer's IP address too — an API key can't be saved without it."}), 400
    # Group 38 follow-up — the whole load→mutate→save cycle is serialized. Both
    # reads and the write must sit inside one critical section; locking only the
    # save would leave the interleave (a concurrent writer's snapshot reverting
    # this one) wide open. Pure CPU in here — no Spoolman I/O — so the lock is
    # held only for the file operations.
    with locations_db.locations_write_lock():
        try:
            rows = locations_db.load_locations_list()
        except Exception as e:
            return jsonify({"ok": False, "error": f"could not read locations: {e}"}), 500
        if loc_id:
            return _put_printer_creds_by_id(rows, loc_id, ip, api_key_in)
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
        if changed:
            if not locations_db.save_locations_list(rows):
                state.add_log_entry(f"🔐 Printer connection save FAILED for {name}", "ERROR", "ff4444")
                return jsonify({"ok": False, "error": "could not persist printer connection"}), 500
            # 29.B2 — only log the "updated" INFO line on an ACTUAL change; a no-op
            # PUT with identical creds no longer emits a misleading "updated" entry.
            state.add_log_entry(f"🔐 Printer connection updated for {name}", "INFO")
    return jsonify({"ok": True, "error": None})


def _put_printer_creds_by_id(rows, loc_id, ip, api_key_in):
    """Hotfix 2026-09-29 — the `location_id` branch of PUT /api/printer_creds.
    Same sentinel, persist-failure and changed-guard contract as the Name branch
    above, addressed by the Printer row's LocationID. Caller MUST hold
    locations_write_lock() (it read `rows` inside it and this writes them back)."""
    row = locations_db.find_printer_row(rows, loc_id)
    if row is None:
        return jsonify({"ok": False, "error": f"No Printer with LocationID {loc_id!r}"}), 404
    label = str(row.get('Name', '') or loc_id)
    if api_key_in == config_schema.SECRET_SENTINEL:
        stored = row.get(locations_db.PRINTER_CREDS_KEY)
        api_key = stored.get('api_key') if isinstance(stored, dict) else None
    else:
        api_key = api_key_in if api_key_in else None
    rows, changed = locations_db.set_printer_credentials_by_id(rows, loc_id, ip, api_key)
    if changed:
        if not locations_db.save_locations_list(rows):
            state.add_log_entry(f"🔐 Printer connection save FAILED for {label}", "ERROR", "ff4444")
            return jsonify({"ok": False, "error": "could not persist printer connection"}), 500
        state.add_log_entry(f"🔐 Printer connection updated for {label}", "INFO")
    return jsonify({"ok": True, "error": None})


def _pm_prefix(k):
    """Printer prefix of a toolhead LocationID (the part before the first '-'),
    matching locations_db._known_printer_prefixes."""
    k = str(k).strip().upper()
    return k.split('-', 1)[0] if '-' in k else k


def _natural_key(s):
    """29.B1 — natural/numeric sort key so "XL-2" orders before "XL-10"
    (lexicographic sort put "XL-10" first, which the 10+-toolhead indxx
    forward-compat cares about — CLAUDE.md "Indxx forward-compat"). Splits a
    LocationID into alternating text/number runs; digit runs compare as ints.
    """
    return [int(t) if t.isdigit() else t for t in re.split(r'(\d+)', str(s))]


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
            # The guarded reader: a malformed row used to raise here, and the
            # except below then failed closed — blocking EVERY toolhead removal.
            targets = locations_db.bindings_from_row(row)
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
    # Group 38 follow-up — one critical section from the read to the write, so a
    # concurrent writer's snapshot can't revert the printer rows written here.
    # Pure CPU inside (the migrations are functions over `_locs`), so the lock
    # is held only for the file I/O.
    try:
        with locations_db.locations_write_lock():
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
            # Hotfix 2026-09-29: refuse a save that leaves two printers sharing a
            # Name this edit sets — creds, status and deducts resolve a printer by
            # Name. Toolheads of ONE printer share its LocationID prefix, so a second
            # prefix under the same name is a second printer.
            _shared = locations_db.shared_printer_names(_locs, set(_names_by_prefix.values()))
            if _shared:
                reason = "; ".join(
                    f"printer name {nm!r} would be shared by {' and '.join(ids)}"
                    for nm, ids in sorted(_shared.items()))
                reason += (" — give each printer its own name (all toolheads of one printer "
                           "share its ID prefix, e.g. RCOI-1…RCOI-8)")
                state.add_log_entry(f"⚙️ Printer-map save blocked — {reason}", "ERROR", "ff4444")
                return jsonify({"ok": False, "error": reason}), 400
            # …and keep the Location Manager in step: a new toolhead gets its Tool
            # Head row (spools can only be put on a real location), and a toolhead
            # the guard just cleared for removal loses its now-empty row.
            _locs, _created_heads = locations_db.ensure_toolhead_rows(_locs, canonical)
            # "Removed" = what the re-sync actually took off the Printer rows, not
            # old-minus-submitted: the re-sync is a no-op for an empty map, and
            # dropping rows on that basis would orphan heads the printers still list.
            _still_listed = set(locations_db.build_printer_map_from_rows(_locs))
            _removed_keys = {str(k).strip().upper() for k in old_map} - _still_listed
            _locs, _dropped_heads = locations_db.remove_unused_toolhead_rows(_locs, _removed_keys)
            if not locations_db.save_locations_list(_locs):
                reason = "could not persist the printer rows"
                state.add_log_entry(f"⚙️ Printer-map save failed: {reason}", "ERROR", "ff4444")
                return jsonify({"ok": False, "error": reason}), 500
    except Exception as _write_err:
        state.logger.error(f"printer_map row write failed: {_write_err}")
        state.add_log_entry(f"⚙️ Printer-map save failed: {_write_err}", "ERROR", "ff4444")
        return jsonify({"ok": False, "error": str(_write_err)}), 500

    state.add_log_entry(f"⚙️ Printer map updated ({len(canonical)} toolheads)", "INFO")
    if _created_heads:
        state.add_log_entry(
            f"🧩 Toolhead location(s) created: {', '.join(_created_heads)}", "INFO")
    if _dropped_heads:
        state.add_log_entry(
            f"🧹 Removed toolhead location(s): {', '.join(_dropped_heads)}", "INFO")
    return jsonify({"ok": True, "error": None, "printer_map": canonical,
                    "created_toolhead_rows": _created_heads,
                    "removed_toolhead_rows": _dropped_heads})


@app.route('/api/dryer_boxes/slots', methods=['GET'])
def api_all_dryer_box_slots():
    """Enumerate every slot across every Dryer Box, flat. Each entry carries
    current binding (may be null). Powers the "bind a slot to this toolhead"
    quick-picker. Cheap — single locations.json read, no Spoolman calls.
    """
    loc_list = locations_db.load_locations_list()
    out = []
    for row in loc_list:
        if not isinstance(row, dict) or row.get('Type') != locations_db.DRYER_BOX_TYPE:
            continue
        box_id = str(row.get('LocationID', '')).strip()
        try:
            max_slots = int(str(row.get('Max Spools', '0')).strip() or '0')
        except ValueError:
            max_slots = 0
        # The guarded reader (a malformed row 500'd the whole picker). It also
        # reports a blank binding as None, which is what "unbound" means here.
        targets = locations_db.bindings_from_row(row)
        # Group 42 review: Return's preview skips a single-slot box's lifecycle
        # binding, as the server does, so it needs to know which boxes those are.
        single = locations_db._is_single_slot_dryer_box(row)
        for n in range(1, max_slots + 1):
            slot = str(n)
            target = targets.get(slot)
            entry = {
                "box": box_id,
                "box_name": row.get('Name', box_id),
                "slot": slot,
                "target": target,  # None => unbound
            }
            if single:
                entry["single_slot"] = True
            out.append(entry)
    # Sort: unbound first (so the picker can promote quickly), then by box id.
    out.sort(key=lambda e: (e['target'] is not None, e['box'], int(e['slot'])))
    return jsonify({"slots": out})


@app.route('/api/placement_options', methods=['GET'])
def api_placement_options():
    """Group 40.1 — what the slot picker shows for a place: a multi-slot box's
    slots (spool, the toolhead each feeds and what it runs now, the ⭐), a
    Printer row's heads and Printer Pool slots, or (mode=return) the box a
    head's spool goes back to. Read-only: one strict Spoolman read, no printer
    probe (the picker asks each printer itself). Query: location (required),
    spool, toolhead, mode ('return'; box / printer come from the row).
    `read_ok: false` (200) when Spoolman can't be read; 404 for an unknown
    location; 400 for a place no picker opens on."""
    args = request.args
    model, status = placement.build_placement_options(
        args.get('location', ''), spool=args.get('spool'),
        toolhead=args.get('toolhead'), mode=args.get('mode'))
    return jsonify(model), status


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
    # Group 42 review: the toolhead grid's Unbind names the head it showed. A
    # repaint is 5-30 s behind, and meanwhile the box can follow its spool onto
    # another head; detaching it from there unbound a box whose spool runs on it.
    expected = str(data.get('expected_target') or '').strip().upper()
    if expected and target in (None, '', 'null', 'None'):
        bound_now = str(current.get(str(slot)) or '').strip().upper()
        if bound_now and bound_now != expected:
            msg = (f"{loc_id} is attached to {bound_now} now, not {expected}, so nothing was changed. "
                   f"Reopen {expected} to see where it is.")
            state.add_log_entry(f"⚠️ Unbind refused: {msg}", "WARNING", "ffaa00")
            return jsonify({"error": "binding_moved", "msg": msg, "location": loc_id,
                            "slot": slot, "bound_to": bound_now}), 409
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


# ---------------------------------------------------------------------------
# Return (Group 40.6): where the spool on a head goes back to, read strictly.
# ---------------------------------------------------------------------------

def _u(v):
    return str(v if v is not None else '').strip().strip('"').upper()


def _flag(value):
    """A request flag the way a page may spell it: true, "true", "1"."""
    return value is True or str(value).strip().lower() in ('true', '1', 'yes')


def _ids_text(ids):
    return logic._and_list(f"#{i}" for i in ids)


class _ReturnReadError(Exception):
    """A box Return needed couldn't be read from Spoolman."""

    def __init__(self, box, err):
        super().__init__(f"{box}: {err}")
        self.box = box
        self.err = err


def _return_reader():
    """Each box read STRICTLY at most once per request: a Spoolman blip raises
    (_ReturnReadError) instead of reading a taken slot as free. The fail-open
    read answered [] on a timeout, so a taken slot looked free."""
    cache = {}

    def read(box):
        b = _u(box)
        if b not in cache:
            try:
                cache[b] = spoolman_api.get_spools_at_location_detailed_strict(b) or []
            except Exception as e:
                raise _ReturnReadError(b, e)
        return cache[b]
    return read


def _slot_holders(row, box, items, sid, slot):
    """The other spools that claim `slot` of `box`, in it or deployed from it
    (the one slot rule, 42.2's effective_slot, through logic.box_slot_claims)."""
    claims, _own, _ghost = logic.box_slot_claims(row, box, items, [sid])
    return list(claims.get(logic._norm_slot(slot)) or [])


def _return_occupancy(items, sid, row):
    """What the box's count reads once #sid is in it: every other spool it shows
    (in a slot, deployed from one, or unslotted) plus #sid, out of Max Spools.
    The slot picker's "No slot" tile counts the same way."""
    others = {str(i.get('id')) for i in (items or []) if str(i.get('id')) != str(sid)}
    return {"after": len(others) + 1, "max": placement._max_slots(row)}


def _slotless_box(row):
    """A Dryer Box with no slot count: its Max Spools is blank or unreadable, so
    it is neither 20.2's single-slot box nor a multi-slot one ("a blank isn't
    managed"). Group 40.6 review, R2: Return keeps its pre-40.6 rule for such a
    box (the recorded slot while no other spool claims it, else no slot) and
    never offers it as a feed, since FCC can't say which of its slots exist and
    the slot picker doesn't open on it."""
    return (isinstance(row, dict) and row.get('Type') == locations_db.DRYER_BOX_TYPE
            and not locations_db._is_single_slot_dryer_box(row) and placement._max_slots(row) <= 1)


def _head_feeds(rows, loc_list, head, sid, read):
    """(feeds, free, attached) for `head`: every (box, slot) of a multi-slot box
    bound to it (single-slot boxes never feed, 42.1 step 5, and neither does a
    box with no slot count, _slotless_box), the ones no other spool claims (read
    strictly), and the single-slot boxes attached to it (a PolyDryer's slot-1
    binding: Derek's builder note counts it as a second feed)."""
    feeds = [(box, slot) for box, slot in logic._feed_slots_for(head, loc_list)
             if placement._max_slots(rows.get(box)) > 1]
    free = []
    for box, slot in feeds:
        row = rows.get(box)
        s = logic._norm_slot(slot)
        if not (s.isdigit() and 1 <= int(s) <= placement._max_slots(row)):
            continue
        if not _slot_holders(row, box, read(box), sid, s):
            free.append((box, s))
    attached = [_u(r.get('LocationID')) for r in loc_list
                if locations_db._is_single_slot_dryer_box(r) and logic._slot_binding(r, '1') == head]
    return feeds, free, attached


def _return_plan(rows, loc_list, printer_map, head, sid, spool_data, read):
    """Where Return sends #sid off `head` when the request names no slot (Group
    40.6: Derek's D5, and his 2026-10-13 answer 6, "one tap when the answer is
    obvious"). Writes nothing. A dict: `box`, `slot` (where it lands, None for
    no slot), `source`, `mode` ('pick': a free slot of a multi-slot box, taken
    only while still free; 'legacy': a single-slot box, as before), or
    `needs_choice` (with the box the chooser shows), or `no_binding`.
      1. The recorded slot, while it exists and no other spool claims it: one
         tap ('physical_source').
      2. A recorded single-slot box: back there, slot 1 while free, else no
         slot; the engine's own 42.2 pick decides at write time (send_slot
         None). A recorded Dryer Box with no slot count (_slotless_box): back
         there as before 40.6, in its recorded slot while free, else no slot.
      3. Otherwise (no slot recorded, the recorded one taken or gone, or a trail
         that isn't a Dryer Box): exactly one free slot of a multi-slot box
         bound to `head`, with no single-slot box attached to `head` (a second
         feed: Derek's builder note), is one tap ('feed_slot'); anything else
         needs a choice, on one box: the recorded multi-slot box or a box
         feeding `head`, whichever offers the best D5 slot (one feeding `head`,
         else a spare), the recorded box then locations.json order on a tie.
      4. No such box: `no_binding`.
    `read(box)` raises _ReturnReadError when Spoolman can't say."""
    extra = (spool_data or {}).get('extra') or {}
    src = _u(extra.get('physical_source'))
    src_slot = logic._norm_slot(extra.get('physical_source_slot'))
    src_row = rows.get(src) if src else None
    plan = {"box": None, "slot": None, "source": None, "mode": None, "needs_choice": False,
            "send_slot": None, "taken_by": [], "note": "", "occupancy": None,
            "recorded": {"box": src or None, "slot": src_slot or None}}
    is_box = isinstance(src_row, dict) and src_row.get('Type') == locations_db.DRYER_BOX_TYPE
    preferred = None
    if is_box and locations_db._is_single_slot_dryer_box(src_row):
        # A single-slot box has slot 1 only: back there, in slot 1 while free
        # (whatever slot its trail names, 42.2), else no slot. Group 40.6
        # review: the plan names only "1" or no slot, the two answers the Yes
        # takes (R2: a recorded "3" was named, then refused); and the engine's
        # own 42.2 pick decides at write time (send_slot None), taking slot 1
        # only while still free, so a spool put in the box while FCC checks the
        # printer is never unseated (R4: an explicit slot 1 was an Overwrite).
        items = read(src)
        taken = _slot_holders(src_row, src, items, sid, '1')
        plan.update(box=src, source='physical_source', mode='legacy', taken_by=taken, checked_slot='1',
                    slot=None if taken else '1', send_slot=None,
                    occupancy=_return_occupancy(items, sid, src_row))
        if taken:
            plan['note'] = f"{src} slot 1 holds {_ids_text(taken)}, so #{sid} goes in without a slot"
        return plan
    if _slotless_box(src_row):
        # Group 40.6 review, R2: a Dryer Box with no slot count keeps the
        # pre-40.6 rule, its recorded slot while no other spool claims it, else
        # no slot. (It used to fall into the single-slot branch above: the plan
        # named slot 3 and the Yes refused it, "has one slot, not slot 3".)
        # The engine has no picked slot for a box without a slot count, so the
        # slot goes as before 40.6: checked free here, then sent as is.
        items = read(src)
        taken = _slot_holders(src_row, src, items, sid, src_slot) if src_slot else []
        keep = src_slot if (src_slot and not taken) else None
        plan.update(box=src, source='physical_source', mode='legacy', taken_by=taken, checked_slot=src_slot,
                    slot=keep, send_slot=keep, occupancy=_return_occupancy(items, sid, src_row))
        if taken:
            plan['note'] = f"{src} slot {src_slot} holds {_ids_text(taken)}, so #{sid} goes in without a slot"
        return plan
    if is_box:
        items = read(src)
        held = _slot_holders(src_row, src, items, sid, src_slot) if src_slot else []
        exists = src_slot.isdigit() and 1 <= int(src_slot) <= placement._max_slots(src_row)
        if exists and not held:
            plan.update(box=src, slot=src_slot, source='physical_source', mode='pick',
                        occupancy=_return_occupancy(items, sid, src_row))
            return plan
        if not src_slot:
            why_not = f"#{sid} has no slot recorded in {src}"
        elif held:
            why_not = f"{src} slot {src_slot}, where it came from, holds {_ids_text(held)}"
        else:
            why_not = f"{src} has no slot {src_slot} any more"
        preferred = src
    elif src:
        why_not = (f"#{sid} came from {src}, which isn't a dryer box" if isinstance(src_row, dict)
                   else f"#{sid} came from {src}, which isn't in the location list any more")
    else:
        why_not = f"#{sid} has no recorded slot"

    feeds, free, attached = _head_feeds(rows, loc_list, head, sid, read)
    if len(free) == 1 and not attached:
        box, s = free[0]
        plan.update(box=box, slot=s, source='feed_slot', mode='pick',
                    note=f"{why_not}; {box} slot {s} is the only free slot that feeds {head}",
                    occupancy=_return_occupancy(read(box), sid, rows.get(box)))
        return plan

    candidates = [preferred] if preferred else []
    for box, _slot in feeds:
        if box not in candidates:
            candidates.append(box)
    if not candidates:
        plan['no_binding'] = True
        # Group 40.6 review, R2: a box that feeds the head but has no slot count
        # isn't offered (the picker can't open on it). Say so, and what makes it
        # work, rather than "no bound dryer box slot" while its Feeds show one.
        slotless = list(dict.fromkeys(box for box, _s in logic._feed_slots_for(head, loc_list)
                                      if _slotless_box(rows.get(box))))
        if slotless:
            one = len(slotless) == 1
            plan['note'] = (f"{why_not}; {logic._and_list(slotless)} {'feeds' if one else 'feed'} {head} but "
                            f"{'has' if one else 'have'} no slot count (Max Spools is blank), so Return can't "
                            f"pick a slot there: set {'its' if one else 'their'} Max Spools to return spools there")
        return plan
    best, best_rank = candidates[0], None
    for box in candidates:
        row = rows.get(box)
        claims, _own, ghost = logic.box_slot_claims(row, box, read(box), [sid])
        slot_ids = [str(i) for i in range(1, placement._max_slots(row) + 1)]
        _pick, why = placement._return_recommendation(row, slot_ids, claims, ghost, head, loc_list, printer_map)
        rank = {'recorded_slot': 0, 'head_slot': 0, 'spare_slot': 1}.get(why, 2)
        if best_rank is None or rank < best_rank:
            best, best_rank = box, rank
    reasons = [why_not]
    if len(free) > 1:
        reasons.append(f"{len(free)} free slots feed {head}")
    elif not free:
        reasons.append(f"no free slot feeds {head}")
    if attached:
        reasons.append(f"{logic._and_list(attached)} {'is' if len(attached) == 1 else 'are'} "
                       f"attached to {head} too")
    plan.update(box=best, needs_choice=True, note="; ".join(reasons),
                occupancy=_return_occupancy(read(best), sid, rows.get(best)))
    return plan


def _return_choice(rows, loc_list, head, sid, spool_data, box, choice, read):
    """The slot the request chose (`choice`: a slot number, or 'none' for no slot
    on purpose) in `box`, checked at write time against a strict read (Group
    40.6). A dict like _return_plan's, or one with `refused` ({status, action,
    error, taken_by}): a slot that doesn't exist or that another spool claims,
    in it or deployed from it, is `return_slot_taken`; a box that isn't a Dryer
    Box, or a slot a single-slot box doesn't have, is a bad request. Its
    `source` says why that slot, as the plan would: the slot it came from, the
    only free slot feeding the head (the confirm's one-tap answer), or a
    choice."""
    row = rows.get(_u(box))
    if not (isinstance(row, dict) and row.get('Type') == locations_db.DRYER_BOX_TYPE):
        return {"refused": {"status": 400, "action": "return_bad_request", "taken_by": [],
                            "error": f"{box or 'That place'} isn't a dryer box to return a spool into"}}
    box = _u(box)
    extra = (spool_data or {}).get('extra') or {}
    src = _u(extra.get('physical_source'))
    src_slot = logic._norm_slot(extra.get('physical_source_slot'))
    items = read(box)
    mx = placement._max_slots(row)
    dest = {"box": box, "slot": None, "source": 'physical_source' if box == src else 'chosen',
            "mode": None, "needs_choice": False, "send_slot": None, "taken_by": [], "note": "",
            "occupancy": _return_occupancy(items, sid, row),
            "recorded": {"box": src or None, "slot": src_slot or None}}
    if locations_db._is_single_slot_dryer_box(row):
        # A single-slot box has slot 1 only; it keeps the old rule (slot 1
        # while free, else unslotted with a warning), never a refusal. "none"
        # (the confirm said no slot, because slot 1 was taken) stays no slot.
        # Group 40.6 review, R4: slot 1 goes to the engine's own 42.2 pick
        # (send_slot None), which takes it only while still free at write time;
        # an explicit slot 1 unseated a spool put there during the printer check.
        if choice not in ('1', 'none'):
            return {"refused": {"status": 400, "action": "return_bad_request", "taken_by": [],
                                "error": f"{box} has one slot, not slot {choice}"}}
        taken = _slot_holders(row, box, items, sid, '1')
        if choice == 'none' and not taken:
            dest.update(mode='unslotted', source='chosen')
            return dest
        dest.update(mode='legacy', taken_by=taken, checked_slot='1', slot=None if taken else '1',
                    send_slot=None)
        if taken:
            dest['note'] = f"{box} slot 1 holds {_ids_text(taken)}, so #{sid} goes in without a slot"
        return dest
    if _slotless_box(row):
        # Group 40.6 review, R2: a Dryer Box with no slot count (Max Spools
        # blank) keeps the pre-40.6 rule, as the plan does: the slot named
        # while no other spool claims it (sent as is: the engine has no picked
        # slot for a box without a slot count), else no slot with a warning,
        # never a refusal. It used to take the single-slot branch above, which
        # refused the recorded slot the confirm had just named.
        if choice == 'none':
            dest.update(mode='unslotted', source='chosen')
            return dest
        taken = _slot_holders(row, box, items, sid, choice)
        keep = None if taken else choice
        dest.update(mode='legacy', taken_by=taken, checked_slot=choice, slot=keep, send_slot=keep,
                    source='physical_source' if (box == src and choice == src_slot) else 'chosen')
        if taken:
            dest['note'] = f"{box} slot {choice} holds {_ids_text(taken)}, so #{sid} goes in without a slot"
        return dest
    if choice == 'none':
        dest.update(mode='unslotted', source='chosen')
        return dest
    if not (choice.isdigit() and 1 <= int(choice) <= mx):
        return {"refused": {"status": 409, "action": "return_slot_taken", "taken_by": [], "box": box,
                            "slot": choice, "error": f"{box} has no slot {choice}, so nothing was moved"}}
    taken = _slot_holders(row, box, items, sid, choice)
    if taken:
        return {"refused": {"status": 409, "action": "return_slot_taken", "taken_by": taken, "box": box,
                            "slot": choice,
                            "error": f"{box} slot {choice} holds {_ids_text(taken)} now, so nothing was moved"}}
    source = 'chosen'
    if box == src and choice == src_slot:
        source = 'physical_source'
    elif logic._slot_binding(row, choice) == head:
        _feeds, free, attached = _head_feeds(rows, loc_list, head, sid, read)
        if free == [(box, choice)] and not attached:
            source = 'feed_slot'
    dest.update(slot=choice, mode='pick', source=source)
    return dest


def _return_options(box, sid, head):
    """The slot picker's model for `box` in return mode, and its ⭐, for an
    answer that lets the user choose (placement.build_placement_options)."""
    try:
        model, status = placement.build_placement_options(box, spool=sid, toolhead=head, mode='return')
    except Exception as e:
        state.logger.warning(f"Return: couldn't build the slot choices for {box}: {e}")
        return None, None
    return model, (model.get('recommended') if status == 200 else None)


# How the success line names why a slot was used.
_RETURN_SOURCE_NOTE = {"physical_source": " (original source)", "chosen": " (chosen)"}


@app.route('/api/quickswap/return', methods=['POST'])
def api_quickswap_return():
    """Reverse quick-swap: take the spool on `toolhead` back to a dryer-box slot.

    `toolhead` is a toolhead id (e.g. "XL-1") or a Printer row / virtual-printer
    prefix (e.g. "XL"); a printer fans out over its toolheads and acts on the
    first one that has a spool loaded.

    Group 40.6 (Derek's D5, and his 2026-10-13 answer 6), optional body fields:
      - `dry_run: true` writes nothing and answers `return_plan` (200): the box
        and the exact slot this Return would use (`slot` null = no slot), or
        `needs_choice` with the slot picker's model in return mode (`options`)
        and its ⭐ (`recommended`);
      - `slot`: the user's choice, a slot number or "none" (no slot, on
        purpose), in `box` (default: the plan's box), checked at write time
        against a strict read: a slot that is gone, or that another spool
        claims, answers `return_slot_taken` (409) with fresh `options`, and
        nothing is written. A chosen slot is sent to the engine as
        `picked_slot`, so a spool that takes it meanwhile is never unseated;
      - `expected_spool`: the spool the page showed. Any other spool on the
        head answers `return_spool_mismatch` (409), nothing written. On a head
        holding two spools it picks the one to return (the DEPLOYED card's
        repair; the other stays), where a request without it is
        `return_ambiguous` (Group 40.6 review, R5).
    Without `slot`: the recorded slot, present and free, is one tap; so is the
    only free slot that feeds the head when no single-slot box is attached to
    it; anything else answers `return_choose_slot` (200), nothing written, with
    an `error` / `msg` telling the page to reload and `stale_page: true` (only
    a page older than 40.6 posts no slot, R3). A recorded single-slot box works
    as before (slot 1 while free at write time, else unslotted with a warning),
    and so does a Dryer Box with no slot count (its recorded slot while free,
    else unslotted, R2); a box with no slot count is never offered as a feed.
    Answers that need the user are 200, refusals 409
    (Group 39.8); every new action carries the 29.B3 keys (`toolhead` =
    requested, `active_toolhead`, `requested`). An unslotted landing reads
    `slot: null` and "(no slot)" in the log.
    """
    data = request.get_json(silent=True) or {}
    toolhead = str(data.get('toolhead', '')).strip().upper()
    if not toolhead:
        state.add_log_entry(
            "❌ Return rejected: missing toolhead in request",
            "ERROR", "ff0000"
        )
        return jsonify({"action": "return_bad_request", "error": "toolhead required"}), 400

    def _bad_request(msg):
        state.add_log_entry(f"❌ Return rejected: {msg}", "ERROR", "ff0000")
        return jsonify({"action": "return_bad_request", "toolhead": toolhead, "requested": toolhead,
                        "error": msg}), 400

    # Group 40.6: the page's choice and what it showed.
    dry_run = _flag(data.get('dry_run'))
    choice = None
    raw_slot = data.get('slot')
    slot_text = str(raw_slot if raw_slot is not None else '').strip().strip('"').strip()
    if slot_text:
        if slot_text.lower() == 'none':
            choice = 'none'
        else:
            choice = logic._norm_slot(slot_text)
            if not choice.isdigit() or int(choice) < 1:
                return _bad_request(f'slot must be a slot number or "none" (got {raw_slot!r})')
    box_req = _u(data.get('box')) or None
    expected_spool = None
    if data.get('expected_spool') not in (None, ''):
        try:
            expected_spool = int(str(data.get('expected_spool')).strip().strip('"'))
        except (TypeError, ValueError):
            return _bad_request(f"expected_spool must be a spool number (got {data.get('expected_spool')!r})")

    # 29.N1 — the vestigial `cfg = config_loader.load_config()` (unused
    # FilaBridge residue) was removed here; printer_map is the sole source.
    # Read locations.json once and hand it to every consumer: the printer_map
    # build (which would otherwise reload the file itself), the Printer-row
    # lookup below, and the destination search in step 2.
    loc_list = locations_db.load_locations_list()
    printer_map = locations_db.get_active_printer_map(loc_list)  # L271 P4 step 2: Printer-row toolheads[]

    # Build the list of toolhead IDs we should check:
    #   * a registered toolhead -> just that ID (the Core One's single head
    #     shares its Printer row's id, CORE1, and lands here);
    #   * a Printer row -> the toolheads[] on that row (L271: the row, not a
    #     "<id>-" spelling, says which heads are its own);
    #   * anything else -> the legacy "<prefix>-" fan-out, kept until L271
    #     Phase 5 retires prefix matching.
    # 29.B1 — natural sort (XL-2 before XL-10), not lexicographic. This order
    # determines both the probe order and which loaded toolhead the return
    # acts on when a printer fans out.
    pm_keys_up = {k.upper() for k in printer_map.keys()}
    candidate_toolheads = []
    if toolhead in pm_keys_up:
        candidate_toolheads = [toolhead]
    else:
        row_heads = locations_db.printer_row_toolheads(loc_list, toolhead)
        if row_heads:
            candidate_toolheads = sorted(
                {t for t in row_heads if t in pm_keys_up}, key=_natural_key)
        else:
            prefix = toolhead + '-'
            candidate_toolheads = sorted(
                (k for k in pm_keys_up if k.startswith(prefix)), key=_natural_key)

    if not candidate_toolheads:
        state.add_log_entry(
            f"⚠️ Return: {toolhead} is not a registered toolhead or printer",
            "WARNING", "ffaa00"
        )
        return jsonify({"action": "return_bad_toolhead", "toolhead": toolhead}), 404

    # 1) Find the first candidate toolhead that has a loaded spool. Only a spool
    #    whose OWN record says it is on the toolhead counts: the location matcher
    #    also returns ghosts (a stale physical_source naming the head), and
    #    Return used to grab one of those off a different head (2026-09-12).
    active_toolhead, spool_id, spool_data = None, None, {}
    unreadable_at = {}  # toolhead -> ids Spoolman couldn't return a record for
    also_on_head = []   # a doubled head's other spools, when the request named one (R5)
    for th in candidate_toolheads:
        loaded = []
        for rid in spoolman_api.get_spools_at_location(th):
            rec = spoolman_api.get_spool(rid)
            if not rec:
                unreadable_at.setdefault(th, []).append(int(rid))
            elif str(rec.get('location') or '').strip().upper() == th:
                loaded.append((int(rid), rec))
        named = [(sid, rec) for sid, rec in loaded if sid == expected_spool] if len(loaded) > 1 else []
        if named:
            # Group 40.6 review, R5: a DEPLOYED card names its spool
            # (`expected_spool`), and that spool is one of the head's, so the
            # card can repair a doubled head (legacy data, an old Location edit):
            # Return acts on it and leaves the other spool where it is. Its ↩️
            # did that before 40.6; without a named spool it is still a guess.
            active_toolhead = th
            spool_id, spool_data = named[0]
            also_on_head = [sid for sid, _ in loaded if sid != expected_spool]
            break
        if len(loaded) > 1:
            ids = ", ".join(f"#{sid}" for sid, _ in loaded)
            msg = f"{th} holds {len(loaded)} spools ({ids}) — eject the wrong one first"
            state.add_log_entry(f"⚠️ Return: {msg}", "WARNING", "ffaa00")
            return jsonify({
                "action": "return_ambiguous",
                "toolhead": toolhead,
                "active_toolhead": th,
                "requested": toolhead,
                "spools": [sid for sid, _ in loaded],
                "error": msg,
            }), 409
        if loaded:
            active_toolhead = th
            spool_id, spool_data = loaded[0]
            break
    if not active_toolhead and unreadable_at:
        # A spool Spoolman couldn't read is not an empty toolhead (2026-09-12
        # review): say the read failed rather than "nothing to return".
        th, ids = next(iter(unreadable_at.items()))
        msg = (f"could not read {', '.join(f'#{sid}' for sid in ids)} from Spoolman — "
               f"{th} may still be loaded")
        state.add_log_entry(f"❌ Return: {msg}", "ERROR", "ff4444")
        return jsonify({
            "action": "return_failed",
            "toolhead": toolhead,
            "active_toolhead": th,
            "requested": toolhead,
            "error": msg,
        }), 409
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

    # 29.B3: on every answer below `toolhead` is the REQUESTED value (return_done
    # alone re-tags it to the head acted on), `active_toolhead` the head the
    # fan-out landed on, and `requested` a back-compat alias.
    requested = toolhead
    head = active_toolhead
    keys = {"toolhead": requested, "active_toolhead": head, "requested": requested}

    # Group 40.6: the page named the spool it showed. Another one on the head
    # (it was swapped meanwhile) is not returned in its place.
    if expected_spool is not None and int(spool_id) != expected_spool:
        msg = (f"{head} holds #{spool_id} now, not #{expected_spool}, so nothing was moved. "
               f"Reopen {head} to see what is on it.")
        state.add_log_entry(f"⚠️ Return refused: {msg}", "WARNING", "ffaa00")
        return jsonify({"action": "return_spool_mismatch", **keys, "spool": spool_id,
                        "expected_spool": expected_spool, "error": msg}), 409

    # 2) Where it goes: the plan (no slot named) or the request's own choice,
    #    each box read strictly.
    rows = {_u(r.get('LocationID')): r for r in loc_list if isinstance(r, dict)}
    read = _return_reader()
    try:
        display = spoolman_api.format_spool_display(spool_data).get('text') or f"#{spool_id}"
    except Exception:
        display = f"#{spool_id}"
    try:
        if choice is None:
            dest = _return_plan(rows, loc_list, printer_map, head, spool_id, spool_data, read)
        else:
            box, dest = box_req, None
            if not box:
                # The chosen slot is in the box this Return would show.
                dest = _return_plan(rows, loc_list, printer_map, head, spool_id, spool_data, read)
                box = dest.get('box')   # none: no_binding stands
            if box:
                dest = _return_choice(rows, loc_list, head, spool_id, spool_data, box, choice, read)
    except _ReturnReadError as e:
        msg = f"couldn't read {e.box} from Spoolman ({e.err}), so nothing was moved — try again"
        state.add_log_entry(f"❌ Return: Spool #{spool_id} off <b>{head}</b>: {msg}", "ERROR", "ff4444")
        return jsonify({"action": "return_failed", **keys, "spool": spool_id, "box": e.box,
                        "error": msg}), 409

    if dest.get('no_binding'):
        why = dest.get('note') or ''
        state.add_log_entry(
            f"⚠️ Return: Spool #{spool_id} off <b>{head}</b> not moved: {why}" if why else
            f"⚠️ Return: {head} has no bound dryer box slot and no physical_source — can't return",
            "WARNING", "ffaa00"
        )
        no_binding = {
            # 29.B3 — `toolhead` uniformly means the REQUESTED value in every
            # error branch; the head the fan-out landed on is `active_toolhead`.
            "action": "return_no_binding",
            **keys,
        }
        if why:
            # Group 40.6 review, R2: a box feeds the head but has no slot count;
            # the page's no-op overlay says so, and how to make it work.
            no_binding['msg'] = why
        return jsonify(no_binding), 404
    refused = dest.get('refused')
    if refused:
        if refused['action'] != 'return_slot_taken':
            state.add_log_entry(f"❌ Return rejected: {refused['error']}", "ERROR", "ff0000")
            return jsonify({"action": refused['action'], **keys, "spool": spool_id,
                            "error": refused['error']}), refused['status']
        options, recommended = _return_options(refused['box'], spool_id, head)
        state.add_log_entry(f"⚠️ Return: Spool #{spool_id} off <b>{head}</b> not moved: {refused['error']}",
                            "WARNING", "ffaa00")
        return jsonify({"action": "return_slot_taken", **keys, "spool": spool_id, "display": display,
                        "box": refused['box'], "slot": refused['slot'], "taken_by": refused['taken_by'],
                        "error": refused['error'], "options": options, "recommended": recommended}), 409

    plan_answer = {**keys, "spool": spool_id, "display": display, "box": dest['box'],
                   "slot": dest.get('slot'), "source": dest.get('source'),
                   "needs_choice": bool(dest.get('needs_choice')), "note": dest.get('note') or "",
                   "recorded": dest.get('recorded'), "occupancy": dest.get('occupancy'),
                   "options": None, "recommended": None}
    if also_on_head:
        # R5: the confirm says the head's other spool stays where it is.
        stays = (f"{head} also holds {_ids_text(also_on_head)}, which "
                 f"{'stays' if len(also_on_head) == 1 else 'stay'} there")
        plan_answer['note'] = "; ".join(n for n in (plan_answer['note'], stays) if n)
    if dest.get('needs_choice'):
        plan_answer['options'], plan_answer['recommended'] = _return_options(dest['box'], spool_id, head)
    if dry_run:
        return jsonify({"action": "return_plan", **plan_answer}), 200
    if dest.get('needs_choice'):
        state.add_log_entry(f"ℹ️ Return: Spool #{spool_id} off <b>{head}</b> waits for a slot choice in "
                            f"{dest['box']}: {plan_answer['note']}", "INFO")
        # Group 40.6 review, R3: only a page loaded before 40.6 posts a Return
        # with no slot (this one asks a dry run first, then sends the slot it
        # showed). Such a page toasts `error`, else the bare action ("Return
        # failed: return_choose_slot"), so the answer says what to do, as the
        # move doors' stale-page answers do. This page never shows it: it
        # dispatches on the action and opens the slot picker.
        why = plan_answer['note'] or f"#{spool_id} needs a slot choice"
        reload_msg = f"{why}, so nothing was moved: reload the page (Ctrl+F5) to choose a slot"
        return jsonify({"action": "return_choose_slot", **plan_answer, "error": reload_msg, "msg": reload_msg,
                        "stale_page": True}), 200

    found_box, found_slot, mode = dest['box'], dest.get('slot'), dest['mode']
    found_source = dest.get('source')
    if mode == 'legacy' and dest.get('taken_by'):
        # A single-slot box has no other slot: the engine leaves the spool
        # unslotted there (it never takes slot 1 from the spool holding it).
        state.add_log_entry(
            f"⚠️ Return: {found_box} slot {dest.get('checked_slot') or '1'} already holds "
            f"{_ids_text(dest['taken_by'])} — #{spool_id} goes back into {found_box} unslotted",
            "WARNING", "ffaa00")

    # 3) Send the spool back. perform_smart_move handles Filabridge + extras.
    # Group 39.2: the server re-checks. The spool's own location is the head
    # being emptied, so 39.4's source check probes it and answers
    # requires_confirm when that printer is printing: "Return probes the head
    # it empties" with no route-specific probe. The browser sends the heads
    # whose warning the user saw (`confirmed_toolheads`); this used to pass
    # True unconditionally, so a probe that timed out emptied a printing head
    # with no warning.
    # auto_deploy=False (2026-09-12): the slot is normally bound to this same
    # toolhead, so the auto-deploy chain put the spool straight back onto it
    # while this route still answered return_done. Every Return was a silent
    # round trip, and it would have become one mid-print too once the chain
    # honoured the caller's confirm.
    # Group 40.6: a slot of a multi-slot box goes as `picked_slot`, taken only
    # while still free (a spool that takes it during the printer check is
    # never unseated, nothing moves); "No slot" goes in unslotted on purpose
    # (`unslotted`, else the engine would pick a slot). 'legacy' sends
    # `target_slot=send_slot`: None for a single-slot box, so the engine's 42.2
    # pick takes slot 1 only while still free (Group 40.6 review, R4), and a
    # box with no slot count its recorded slot as before 40.6 (R2).
    move_kwargs = {"origin": 'quickswap_return', "auto_deploy": False,
                   "confirm_active_print": logic.confirmed_heads(data)}
    if also_on_head:
        state.add_log_entry(
            f"⚠️ Return: {head} holds {len(also_on_head) + 1} spools; returning #{spool_id}, the one the page "
            f"named, and {_ids_text(also_on_head)} {'stays' if len(also_on_head) == 1 else 'stay'} on {head}",
            "WARNING", "ffaa00")
    if mode == 'pick':
        move_result = logic.perform_smart_move(found_box, [spool_id], picked_slot=found_slot, **move_kwargs)
    elif mode == 'unslotted':
        move_result = logic.perform_smart_move(found_box, [spool_id], unslotted=True, **move_kwargs)
    else:
        move_result = logic.perform_smart_move(found_box, [spool_id], target_slot=dest.get('send_slot'),
                                               **move_kwargs)
    stale = logic.stale_confirm_refusal(data, move_result)
    if stale:
        return jsonify({
            "action": "return_failed",
            "spool": spool_id,
            **keys,
            "box": found_box,
            "slot": found_slot,
            "error": stale,
            "stale_page": True,
        }), 409
    if isinstance(move_result, dict) and move_result.get('status') == 'requires_confirm':
        state.add_log_entry(
            f"⚠️ Return: Spool #{spool_id} off <b>{head}</b> waits for a confirm: "
            f"{move_result.get('msg')}", "WARNING", "ffaa00")
        return jsonify({
            # 29.B3: `toolhead` is the REQUESTED value outside return_done.
            "action": "return_requires_confirm",
            "spool": spool_id,
            **keys,
            "box": found_box,
            "slot": found_slot,
            "confirm_type": move_result.get('confirm_type'),
            "active_print": move_result.get('active_print'),
            "active_prints": move_result.get('active_prints') or [],
            "msg": move_result.get('msg'),
        }), 200
    move_failed = logic.smart_move_failure(move_result, spool_id)
    if move_failed and mode == 'pick':
        # The slot was taken while FCC checked the printer (the engine refuses a
        # picked slot someone took): offer the slots again, nothing written.
        try:
            holders = _slot_holders(rows.get(found_box), found_box,
                                    spoolman_api.get_spools_at_location_detailed_strict(found_box) or [],
                                    spool_id, found_slot)
        except Exception:
            holders = []
        if holders or (isinstance(move_result, dict) and move_result.get('blocked_reason') == 'picked_slot_taken'):
            options, recommended = _return_options(found_box, spool_id, head)
            state.add_log_entry(
                f"⚠️ Return: Spool #{spool_id} off <b>{head}</b> not moved: {move_failed}", "WARNING", "ffaa00")
            return jsonify({"action": "return_slot_taken", **keys, "spool": spool_id, "display": display,
                            "box": found_box, "slot": found_slot, "taken_by": holders, "error": move_failed,
                            "options": options, "recommended": recommended}), 409
    if move_failed:
        state.add_log_entry(
            f"❌ Return: Spool #{spool_id} was NOT returned to <b>{found_box}</b> — {move_failed}",
            "ERROR", "ff4444"
        )
        return jsonify({
            "action": "return_failed",
            "spool": spool_id,
            # 29.B3: `toolhead` is the REQUESTED value in every error branch.
            **keys,
            "box": found_box,
            "slot": found_slot,
            "error": move_failed,
            "smart_move": move_result,
        }), 409
    landed = found_slot if mode == 'pick' else None
    if mode == 'legacy':
        landed = dest.get('send_slot')
        if not landed:
            # The engine decided (42.2: a single-slot box's slot 1 while still
            # free, else no slot): report where the spool actually landed.
            landed_rec = spoolman_api.get_spool(spool_id)
            if isinstance(landed_rec, dict) and landed_rec.get('id') is not None:
                landed_extra = landed_rec.get('extra') or {}
                landed = str(landed_extra.get('container_slot') or '').strip().strip('"') or None
                if dest.get('slot') and not landed:
                    # R4: the slot the confirm named was free when checked and
                    # taken before the write; the engine put the spool in with
                    # no slot rather than unseat the one that took it.
                    state.add_log_entry(
                        f"⚠️ Return: {found_box} slot {dest['slot']} was taken meanwhile, so #{spool_id} "
                        f"went back into {found_box} without a slot", "WARNING", "ffaa00")
            else:
                # Couldn't re-read it: the slot the plan expected (a spool
                # taking it in the moment FCC checked the printer is rare).
                landed = dest.get('slot')
    if landed:
        where = f"{found_box} slot {landed}"
        src_note = (f" (the only free slot that feeds {head})" if found_source == 'feed_slot'
                    else _RETURN_SOURCE_NOTE.get(found_source, ""))
    else:
        where, src_note = found_box, " (no slot)"
    state.add_log_entry(
        f"↩️ Return: Spool #{spool_id} from <b>{head}</b> → <b>{where}</b>{src_note}",
        "SUCCESS", "00ff00"
    )
    return jsonify({
        "action": "return_done",
        "moved": spool_id,
        # return_done names the head it acted on (the fan-out's pick).
        "toolhead": head,
        "active_toolhead": head,
        "requested": requested,
        "box": found_box,
        "slot": landed,
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

    Group 51.5: `expected_spool` (optional), the spool the tapped card showed.
    Another spool in the slot now answers `quickswap_spool_mismatch` (409,
    nothing written; the grid refreshes), as Return's `return_spool_mismatch`
    does, instead of loading a spool the user wasn't shown. Absent: no check.
    """
    data = request.get_json(silent=True) or {}
    toolhead = str(data.get('toolhead', '')).strip().upper()
    box = str(data.get('box', '')).strip().upper()
    slot = str(data.get('slot', '')).strip()
    expected_spool = None
    if data.get('expected_spool') not in (None, ''):
        try:
            expected_spool = int(str(data.get('expected_spool')).strip().strip('"'))
        except (TypeError, ValueError):
            return jsonify({
                "action": "quickswap_bad_request",
                "error": f"expected_spool must be a spool number (got {data.get('expected_spool')!r})",
            }), 400

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

    # Two spools claiming the slot: the grid's card named one of them, and moving
    # either could load a different spool than the user picked (Group 42 review).
    claimants: list = []
    spool_id = logic.find_spool_in_slot(box, slot, claimants=claimants)
    if len(claimants) > 1:
        msg = (f"{box} slot {slot} is claimed by {logic._and_list([f'#{c}' for c in claimants])} — "
               f"open {box} and move one of them first")
        state.add_log_entry(f"⚠️ Quick-swap: {msg}", "WARNING", "ffaa00")
        return jsonify({
            "action": "quickswap_ambiguous_slot",
            "box": box, "slot": slot, "toolhead": toolhead,
            "spools": claimants, "error": msg,
        }), 409
    if not spool_id:
        state.add_log_entry(
            f"⚠️ Quick-swap: slot {box}:SLOT:{slot} is empty — no spool to move to {toolhead}",
            "WARNING", "ffaa00"
        )
        return jsonify({
            "action": "quickswap_empty_slot",
            "box": box, "slot": slot, "toolhead": toolhead,
        }), 404
    if expected_spool is not None and int(spool_id) != expected_spool:
        msg = (f"{box} slot {slot} holds #{spool_id} now, not #{expected_spool}, so nothing was loaded "
               f"onto {toolhead}. The slots have been refreshed: tap again if you still want it.")
        state.add_log_entry(f"⚠️ Quick-swap refused: {msg}", "WARNING", "ffaa00")
        return jsonify({
            "action": "quickswap_spool_mismatch",
            "box": box, "slot": slot, "toolhead": toolhead,
            "spool": spool_id, "expected_spool": expected_spool, "error": msg,
        }), 409

    # Group 39.2: the server re-checks. The overlay's probe shows the banner on
    # the usual path and the browser sends the heads whose warning the user saw
    # (`confirmed_toolheads`); this catches only what that probe missed (it
    # fails open on a timeout), so a mid-print Quick-Swap is still one confirm.
    # It used to pass True unconditionally, so a probe that timed out unloaded
    # a printing head's spool with no warning at all (D1 / R2-06).
    move_result = logic.perform_smart_move(
        toolhead, [spool_id], target_slot=None, origin='quickswap',
        confirm_active_print=logic.confirmed_heads(data),
    )
    stale = logic.stale_confirm_refusal(data, move_result)
    if stale:
        return jsonify({
            "action": "quickswap_failed",
            "spool": spool_id,
            "toolhead": toolhead, "box": box, "slot": slot,
            "error": stale,
            "stale_page": True,
        }), 409
    if isinstance(move_result, dict) and move_result.get('status') == 'requires_confirm':
        state.add_log_entry(
            f"⚠️ Quick-swap: Spool #{spool_id} → <b>{toolhead}</b> waits for a confirm: "
            f"{move_result.get('msg')}", "WARNING", "ffaa00")
        return jsonify({
            "action": "quickswap_requires_confirm",
            "spool": spool_id,
            "toolhead": toolhead, "box": box, "slot": slot,
            "confirm_type": move_result.get('confirm_type'),
            "active_print": move_result.get('active_print'),
            "active_prints": move_result.get('active_prints') or [],
            "msg": move_result.get('msg'),
        }), 200
    # 2026-09-12: a rejected write, or a resident Smart Load could not unload,
    # used to be logged and answered as quickswap_done.
    move_failed = logic.smart_move_failure(move_result, spool_id)
    if move_failed:
        state.add_log_entry(
            f"❌ Quick-swap: Spool #{spool_id} was NOT loaded onto <b>{toolhead}</b> — {move_failed}",
            "ERROR", "ff4444"
        )
        return jsonify({
            "action": "quickswap_failed",
            "spool": spool_id,
            "toolhead": toolhead, "box": box, "slot": slot,
            "error": move_failed,
            "smart_move": move_result,
        }), 409
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

