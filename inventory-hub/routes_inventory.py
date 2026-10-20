"""Inventory wizard / vendor / CRUD / search routes (L316 step 5).

Moved verbatim from app.py: vendor CRUD (+ `_format_vendor_edit_log`),
filament/spool read proxies, the Spoolman extra-field schema cluster
(FIELD_ORDER / `_enrich_field_order` / external fields + restore_field_order
+ add_choice), the wizard create/edit endpoints, the generic
/api/spool/update partial-update (auto-archive surfacing), external-parser
search dispatch, and global inventory search. `_log_manual_weight_change`
is the shared before→after log for BOTH manual weight funnels
(api_spool_update + api_edit_spool_wizard — CLAUDE.md Group 24.F).
Group 40.7: the wizard's Location (edit and create) is a move through the
engine (`_wizard_move`, `_place_created`), and /api/spool/update's location
path is checked by `_direct_location_write`.

Preserved quirks (do not 'fix' in a move — see the carve plan):
- api_filaments deliberately returns raw double-encoded extras (no
  parse_inbound_data) — the wizard JS compensates.
- spoolman_api.LAST_SPOOLMAN_ERROR is read as a module attribute immediately
  after a None-returning update (order-sensitive error channel).
- The mid-module `import external_parsers` keeps its pre-carve position at
  the top of the search section.

Python 3.9 runtime (the container image) — keep syntax 3.9-safe.
"""
from flask import request, jsonify  # type: ignore
import requests  # type: ignore

import state  # type: ignore
import config_loader  # type: ignore
import spoolman_api  # type: ignore
# Group 42 review: single-slot box release on a direct edit. Group 40.7: the
# wizard's Location goes through the move engine.
import logic  # type: ignore
import locations_db  # type: ignore  # Group 40.7: Printer-row / one-spool checks before a create
import attr_migration  # type: ignore  # Group 36: hidden filament-attribute choices

from app_core import app

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
        # 28.B4 — surface the Spoolman rejection body (matches api_create_vendor
        # and the CLAUDE.md error-surfacing convention) instead of a fixed
        # generic message the user can't act on.
        err = spoolman_api.LAST_SPOOLMAN_ERROR or "Spoolman rejected the filament create."
        return jsonify({"success": False, "msg": err}), 500
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


def _hide_suppressed_attr_choices(fields):
    """Strip FCC-hidden choices from the filament_attributes field definition.

    Hiding a choice deliberately does NOT touch Spoolman's schema (that would
    mean the destructive DELETE + recreate migration), so the raw proxy payload
    still carries it. Every consumer of this endpoint treats `choices` as "what
    the user may pick", which is exactly what the hidden list overrides.
    """
    for f in fields or []:
        if f.get("key") == "filament_attributes":
            f["choices"] = attr_migration.visible_choices(f.get("choices") or [])
    return fields


@app.route('/api/external/fields', methods=['GET'])
def api_external_fields():
    """Proxy route to fetch Spoolman custom Extra fields configuration (e.g. Filament Attributes, Spool Types).

    Group 36 — hidden filament-attribute choices are stripped here. This proxy
    is the SINGLE source every tag picker reads (the wizard's
    `_knownFilamentAttributes`, the Edit Filament modal's chip picker, and
    `splitMaterialAndAttributes`'s auto-assign), so filtering only in
    `/api/filament_attributes/report` left a "removed" tag still offered
    everywhere it actually gets applied — and re-applying it produced a tag the
    Choices Manager could no longer see or strip.
    """
    sm_url, _ = config_loader.get_api_urls()
    out = {"filament": [], "spool": []}
    try:
        rf = requests.get(f"{sm_url}/api/v1/field/filament", timeout=5)
        if rf.ok: out["filament"] = _hide_suppressed_attr_choices(_enrich_field_order("filament", rf.json()))

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
         # 28.B6 — a missing required field is a client validation error → 400.
         return jsonify({"success": False, "msg": "Missing required fields."}), 400
         
    res = spoolman_api.update_extra_field_choices(entity_type, key, [new_choice])
    return jsonify(res)

# --- Group 40.7: the wizard's Location goes through the move engine ------------------
# Derek, 2026-10-19 (answer 7): a Location change in the Add / Edit Spool wizard
# behaves like Force Location. Save writes the other edits first, then MOVES the
# spool through the engine (Smart Load, the active-print and "already fed"
# questions, the Printer-row refusal), so this last direct location writer can no
# longer stack a second spool on a toolhead, file one on a printer row, or leave the
# old slot and trail behind.

def _loc_key(value):
    """A spool location in the one form the wizard and /api/spool/update compare:
    quotes and blanks stripped, upper-cased, and "UNASSIGNED" read as '' (the
    Unassigned list). The engine upper-cases its target the same way."""
    s = str(value if value is not None else '').strip().strip('"').strip().upper()
    return '' if s == 'UNASSIGNED' else s


def _is_question(result):
    return isinstance(result, dict) and result.get('status') == 'requires_confirm'


def _move_why(result, sid, stale=None, can_ask=True):
    """Why a wizard move did not land, worded for "…was not moved to X: <why>"."""
    if stale:
        why = str(stale)
    elif result is True:
        return ''
    elif result is False or result is None:
        return ("FCC couldn't unassign it (Spoolman didn't answer or refused the write; "
                "see the Activity Log)")
    elif _is_question(result):
        body = str(result.get('body') or result.get('msg') or 'a printer is busy').strip()
        if body.endswith('Continue?'):
            body = body[:-len('Continue?')].strip()
        why = f"FCC has to ask first — {body}"
        if not can_ask:
            # A page from before 40.7 sends none of the door contract and can't
            # show the question, so saving again would only ask again.
            why = why.rstrip('.') + ". Reload the page (Ctrl+F5) and save again to answer it."
    else:
        why = logic.smart_move_failure(result, sid) or 'the move did not land'
    for lead in ('Not moved: ', 'Not loaded: '):
        if why.startswith(lead):
            why = why[len(lead):]
    if why.startswith('This '):
        why = 'this ' + why[len('This '):]
    return why


def _not_moved_msg(sid, new_loc, why, saved_other):
    """ "Saved your other changes, but #57 was not moved to LR-MDB-1: …" — the
    answer's `msg`, true even for a page from before 40.7 (it shows `msg`)."""
    lead = "Saved your other changes, but " if saved_other else ""
    text = f"{lead}#{sid} was not moved to {new_loc or 'Unassigned'}: {why}"
    return text if text.endswith(('.', '?', '!')) else text + '.'


def _wizard_move(sid, new_loc, data, placement=None, current_loc='', origin='wizard_edit'):
    """Group 40.7 — apply one wizard Location, one spool per call: Unassigned
    through perform_force_unassign (Force Location's own path), anything else
    through perform_smart_move. Returns (moved, result, stale): `result` is the
    engine's answer untouched (perform_force_unassign answers True, False or a
    requires_confirm dict); `stale` is the message the move doors answer instead
    of a question this request can't ask (logic.stale_fed_refusal, then
    logic.stale_confirm_refusal, in that order), else None.

    `placement`: the slot fields (`slot`, `picked_slot`, `expected_feed`,
    `auto_deploy`, and the picker's `record_source` / `swap`, Groups 40.5 and
    Swap option C): the edit request itself, or one `placements` entry of a
    create. `data`: the door contract (`confirmed_toolheads`,
    `confirmed_fed_heads`, `seen_printing`). `current_loc`: where the spool is,
    so an unassign's confirm covers only the head the user was asked about."""
    p = placement if isinstance(placement, dict) else {}
    if not new_loc:
        # Force-unassign keeps its boolean confirm (39.1): covered only when the
        # request confirmed the head the spool sits on, so a bare legacy flag or
        # another head's confirm is asked again.
        here = _loc_key(current_loc)
        result = logic.perform_force_unassign(
            sid, confirm_active_print=bool(here) and here in logic.confirmed_heads(data))
    else:
        result = logic.perform_smart_move(
            new_loc, [sid], origin=origin,
            target_slot=p.get('slot'),
            picked_slot=p.get('picked_slot'),
            auto_deploy=logic.auto_deploy_requested(p),
            confirm_active_print=logic.confirmed_heads(data),
            confirmed_fed_heads=logic.confirmed_fed_heads_from(data),
            expected_feed=logic.expected_feed_from(p),
            seen_printing=logic.seen_printing_from(data),
            # Group 40.5: the Printer picker's "came from" answer for a head
            # ('' = No box); absent, the engine's silent 13.6 rule.
            record_source=logic.record_source_from(p),
            # Swap option C: the slot picker's Swap of a slot's stored spool.
            swap_out=logic.swap_requested(p),
        )
    stale = None
    if isinstance(result, dict):
        stale = logic.stale_fed_refusal(data, result) or logic.stale_confirm_refusal(data, result)
    if not new_loc:
        return result is True, result, stale
    moved = (isinstance(result, dict) and result.get('status') == 'success'
             and not logic.smart_move_failure(result, sid))
    return moved, result, stale


def _is_multi_slot_box(row):
    """A multi-slot Dryer Box row (Max Spools above 1): the box picker's rows."""
    if not isinstance(row, dict) or row.get('Type') != locations_db.DRYER_BOX_TYPE:
        return False
    try:
        return int(str(row.get('Max Spools', '0')).strip() or '0') > 1
    except (TypeError, ValueError):
        return False


def _reslot_asked(data, spool, loc):
    """Group 40.7 — the request asks for a slot (`slot` / `picked_slot`) of the
    multi-slot Dryer Box the spool already sits in, other than its own: a spool
    floating in LR-MDB-1 given a slot of it. That is a move too, though the
    Location doesn't change."""
    asked = data.get('slot')
    if asked in (None, ''):
        asked = data.get('picked_slot')
    asked = logic._norm_slot(asked)
    own = logic._norm_slot(((spool or {}).get('extra') or {}).get('container_slot'))
    if not asked or asked == own:
        return False
    row = next((r for r in (locations_db.load_locations_list() or []) if isinstance(r, dict)
                and str(r.get('LocationID', '')).strip().upper() == loc), None)
    return _is_multi_slot_box(row)


def _landed_at(sid, target, result):
    """Where a placed spool landed, as (words, location_now): the toast's short
    arrows ("LR-MDB-1 slot 2 → XL-2", "CR-CT-2-R1", "Unassigned") and the
    LocationID it is filed on now ('' = Unassigned; the head, for a move whose
    chain loaded one). Read back from Spoolman, because the engine's answer
    doesn't name a slot it picked; a failed read names the target (and the head
    the answer says it loaded).

    Group 40.7 review (wizard-resave-unloads-head): the wizard puts
    `location_now` in its Location field after a move, so a second Save in the
    same session compares the head with the head and moves nothing. It used to
    keep the box, and the second Save stored the spool back in it (its own
    slot, which feeds the head it was leaving), unloading the head unasked."""
    head = str((result or {}).get('auto_deployed_to') or '').strip().upper() if isinstance(result, dict) else ''

    def _clean(value):
        return str(value if value is not None else '').strip().strip('"').strip()

    rec = spoolman_api.get_spool(sid)
    if not isinstance(rec, dict) or rec.get('id') is None:
        return (f"{target} → {head}" if head else (target or 'Unassigned')), (head or target or '')
    extra = rec.get('extra') if isinstance(rec.get('extra'), dict) else {}
    loc = _clean(rec.get('location')).upper()
    if head and loc == head:
        box = _clean(extra.get('physical_source')).upper() or target
        slot = _clean(extra.get('physical_source_slot'))
        return f"{box}{' slot ' + slot if slot else ''} → {head}", loc
    if not loc:
        return 'Unassigned', ''
    slot = _clean(extra.get('container_slot'))
    return f"{loc}{' slot ' + slot if slot else ''}", loc


def _landed_where(sid, target, result):
    """_landed_at's words alone: "LR-MDB-1 slot 2 → XL-2", "CR-CT-2-R1", "Unassigned"."""
    return _landed_at(sid, target, result)[0]


def _pick_refused(data, new_loc, result, sid):
    """Group 40.7 review (wizard-refused-pick-resent): True when a move was
    refused over the picker's own choice, which the page holds and would send
    again on every Save, only to be refused again: the slot it picked was taken
    meanwhile (`picked_slot_taken`), the head's "came from" slot can't be
    recorded (`record_source`), or the slot it named is still claimed by a
    spool deployed from it (`slot_claimed`, the engine's ghost guard,
    logic._ghost_claim_refusal; Group 51.3: it used to be told by its words).
    The page then drops the pick, so its next Save opens the picker again. A
    refusal about anything else (Spoolman rejecting the write, a read that
    failed) keeps the pick: saving again may work."""
    if not isinstance(result, dict):
        return False
    return result.get('blocked_reason') in ('picked_slot_taken', 'record_source', 'slot_claimed')


def _deploy_skipped_note(sid, target, result):
    """The warning for a spool placed in a bound slot but not loaded onto its head."""
    if not isinstance(result, dict):
        return ''
    why = (result.get('auto_deploy_skipped') or {}).get(str(sid))
    if not why:
        return ''
    note = f"#{sid} is in {target} but was NOT deployed to {result.get('auto_deploy_target') or 'its toolhead'}: {why}"
    return note if note.endswith(('.', '?', '!')) else note + '.'


_PLACEMENT_KEYS = ('location', 'slot', 'picked_slot', 'expected_feed', 'auto_deploy',
                   # Group 40.5 / Swap option C: the picker's answers ride along.
                   'record_source', 'swap')


def _create_wants(data, spool_data, spool_iter):
    """Group 40.7 — where each new spool goes ({location, slot, picked_slot,
    expected_feed, auto_deploy}), index-aligned with the spools to create; None
    leaves that spool Unassigned. A 40.7 page sends `placements`: a spool with no
    entry stays Unassigned, which is how the browser's per-spool picker loop for a
    multi-slot box works (Claude's call 29: the chosen slot first, the loop for
    the rest). A request without the key (a page from before 40.7) places every
    spool where `spool_data` says (or its own spool override, which wins as it
    always did), through the engine, except onto a toolhead (_create_guards)."""
    out = []
    raw = data.get('placements')
    if isinstance(raw, list):
        for i in range(len(spool_iter)):
            entry = raw[i] if i < len(raw) else None
            if isinstance(entry, str):
                entry = {'location': entry}
            loc = _loc_key(entry.get('location')) if isinstance(entry, dict) else ''
            out.append(dict({k: entry[k] for k in _PLACEMENT_KEYS if k in entry}, location=loc) if loc else None)
        return out
    for override in spool_iter:
        src = override if isinstance(override, dict) and 'location' in override else spool_data
        loc = _loc_key(src.get('location'))
        out.append({'location': loc} if loc else None)
    return out


def _no_slot(want):
    return not logic._norm_slot(want.get('slot')) and not logic._norm_slot(want.get('picked_slot'))


def _create_guards(data, wants):
    """Group 40.7 review — two belts on a create's placements, applied once
    _create_refusal has passed them (so its refusals are unchanged). Returns the
    wants, a new dict for each one changed:
      - a placement into a multi-slot Dryer Box that names no slot (`slot` /
        `picked_slot`) is a store, `auto_deploy: false`
        (wizard-slotless-create-loads-empty-head): the engine would take the
        lowest free slot that "loads no busy toolhead", and a slot bound to an
        EMPTY head qualifies, so the chain loaded a sealed new spool onto that
        head with no question and no slot shown. A 40.7 page opens the slot
        picker before it sends a box, so only an older page or another caller
        sends one without a slot;
      - a request without `placements` (a page from before 40.7) never puts a
        new spool on a toolhead (wizard-stale-page-create-onto-head): that
        page's reset left the last edited spool's head in its hidden Location,
        so it could send XL-1 while showing Unassigned, and the engine's Smart
        Load would unload XL-1's spool (unasked while idle) for the sealed one.
        It is created Unassigned (`stale_page_head`; _place_created says to
        reload in `warning`)."""
    if not any(wants):
        return wants
    loc_list = locations_db.load_locations_list() or []
    printer_map = locations_db.get_active_printer_map() or {}
    rows = {str(r.get('LocationID', '')).strip().upper(): r for r in loc_list if isinstance(r, dict)}
    stale_page = not isinstance((data or {}).get('placements'), list)
    out = []
    for want in wants:
        if want:
            loc = want['location']
            if stale_page and logic._holds_one_spool(loc, printer_map, rows):
                want = dict(want, stale_page_head=True)
            elif _is_multi_slot_box(rows.get(loc)) and _no_slot(want):
                want = dict(want, auto_deploy=False)
        out.append(want)
    return out


def _create_refusal(wants):
    """Group 40.7 — why a wizard create is refused before anything is created, as
    (blocked_reason, why), or None: a Printer row that isn't itself a toolhead
    (40.0a's rule and wording), or more than one new spool onto a place that holds
    one (the engine's one-spool rule; 42.3a refuses the same in a move)."""
    counts = {}
    for want in wants:
        if want:
            counts[want['location']] = counts.get(want['location'], 0) + 1
    if not counts:
        return None
    loc_list = locations_db.load_locations_list() or []
    printer_map = locations_db.get_active_printer_map() or {}
    rows = {str(r.get('LocationID', '')).strip().upper(): r for r in loc_list if isinstance(r, dict)}
    for loc, n in counts.items():
        row = rows.get(loc)
        if locations_db.is_printer_row_not_head(loc, row, printer_map):
            return 'printer_row', logic.printer_row_refusal(loc, row, loc_list)
        if n > 1 and logic._holds_one_spool(loc, printer_map, rows):
            return 'single_occupancy', (f"{loc} holds one spool, so FCC can't create {n} spools there — "
                                        f"create one there and put the rest on a shelf or in a box.")
    return None


def _place_created(created, wants, data):
    """Group 40.7 — place each new spool through the engine, one call each.
    A placement that is refused or asks a question never undoes the creation:
    that spool stays Unassigned and is named in `unplaced`. Returns the answer's
    placement fields (see api_create_inventory_wizard)."""
    placed, unplaced, results, tried, to_buffer, notes = {}, [], {}, {}, [], []
    can_ask = 'confirmed_toolheads' in data
    skipped = False
    for index, sid in created:
        want = wants[index] if index < len(wants) else None
        if not want:
            unplaced.append(sid)
            continue
        loc = want['location']
        if want.get('stale_page_head'):
            # _create_guards: a page from before 40.7 never loads a toolhead.
            skipped = True
            unplaced.append(sid)
            note = (f"#{sid} was created but is Unassigned, not on {loc}: this page is out of date, so "
                    f"FCC won't load {loc} from it. Reload the page (Ctrl+F5), then scan #{sid} onto {loc}.")
            state.add_log_entry(f"⚠️ {note}", "WARNING", "ffaa00")
            notes.append(note)
            continue
        try:
            moved, result, stale = _wizard_move(sid, loc, data, placement=want, origin='wizard_create')
        except Exception as e:   # the spool exists: report it, never fail the create
            state.add_log_entry(f"❌ New spool #{sid} was not placed in {loc}: {e}", "ERROR", "ff4444")
            moved, result, stale = False, {"status": "error", "msg": f"the move crashed ({e})"}, None
        results[str(sid)] = result
        tried[str(sid)] = {k: want[k] for k in _PLACEMENT_KEYS if want.get(k) is not None}
        if isinstance(result, dict):
            to_buffer.extend(i for i in (result.get('to_buffer') or []) if isinstance(i, dict))
        if moved:
            placed[str(sid)] = _landed_where(sid, loc, result)
            note = _deploy_skipped_note(sid, loc, result)
            if note:
                notes.append(note)
            continue
        unplaced.append(sid)
        why = _move_why(result, sid, stale=stale, can_ask=can_ask)
        note = f"#{sid} was created but not placed in {loc}, so it is Unassigned: {why}"
        notes.append(note if note.endswith(('.', '?', '!')) else note + '.')
    out = {"placed": placed, "unplaced": unplaced, "location_results": results,
           "placement_requests": tried, "placements_ok": len(placed) == len(results) and not skipped}
    if to_buffer:
        out["to_buffer"] = to_buffer
    if notes:
        # A page from before 40.7 toasts `warning` for 7 s; a 40.7 page reads
        # location_results instead.
        out["warning"] = " ".join(notes)
    return out


@app.route('/api/create_inventory_wizard', methods=['POST'])
def api_create_inventory_wizard():
    """Monolithic endpoint to handle creating Filaments and Spools in one shot.

    Group 40.7: every spool is created Unassigned and then placed through the move
    engine, one call each (Derek's answer 7: the wizard behaves like Force
    Location). Refused before ANYTHING is created (the filament included), with
    `blocked_reason`: a Printer row that isn't itself a toolhead (`printer_row`),
    and more than one new spool onto a place that holds one (`single_occupancy`).
    Request: `placements` (optional), index-aligned with the spools to create,
    each {location, slot | picked_slot, expected_feed, auto_deploy} or null (that
    spool stays Unassigned: the browser's per-spool picker loop places it); the
    door contract (`confirmed_toolheads`, `confirmed_fed_heads`, `seen_printing`)
    at the top level. Without `placements` every spool goes where `spool_data`
    says. Group 40.7 review (_create_guards): a placement into a multi-slot box
    that names no slot is stored, never loaded onto the head its slot feeds; and
    a request without `placements` never puts a spool on a toolhead (it stays
    Unassigned, and `warning` says to reload the page).
    Answer (when anything was to be placed, or `placements` was sent):
    `placed` {id: where it landed}, `unplaced` [ids left Unassigned],
    `location_results` {id: the engine's answer, for every placement tried},
    `placement_requests` {id: the entry tried}, `placements_ok`, `to_buffer` (a
    same-slot swap's old spool) and `warning` (what wasn't placed, for a page
    from before 40.7). `success` stays true whenever spools were created: an
    older page would otherwise let the user Create again and duplicate them."""
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
        # Group 40.7: where each new spool goes, decided before anything is created
        # (the filament included), so a refused place leaves nothing behind.
        wants = []
        spool_iter = []
        if spool_data:
            if spool_overrides and isinstance(spool_overrides, list):
                spool_iter = spool_overrides
            else:
                spool_iter = [None] * quantity
            wants = _create_wants(data, spool_data, spool_iter)
            refused = _create_refusal(wants)
            if refused:
                reason, why = refused
                msg = f"{why.rstrip('.')}. Nothing was created."
                state.add_log_entry(f"⚠️ Not created: {msg}", "WARNING", "ffaa00")
                return jsonify({"success": False, "blocked_reason": reason, "msg": msg,
                                "created_spools": []})
            # Group 40.7 review: a slotless box placement stores; an older page
            # never loads a toolhead.
            wants = _create_guards(data, wants)

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

            # Per-spool override list takes precedence over `quantity` when present
            # (`spool_iter`, decided above). Each entry shallow-merges onto
            # spool_data, with `extra` deep-merged so per-spool fields (e.g.
            # prusament_manufacturing_date) don't clobber wizard-wide extras (e.g.
            # needs_label_print).
            created = []   # (index into spool_iter, new spool id), for the placements
            for index, override in enumerate(spool_iter):
                payload = dict(spool_data)
                if override:
                    base_extra = dict(payload.get('extra') or {})
                    override_extra = override.get('extra') or {}
                    payload.update({k: v for k, v in override.items() if k != 'extra'})
                    if base_extra or override_extra:
                        base_extra.update(override_extra)
                        payload['extra'] = base_extra
                # Group 40.7: created Unassigned, then placed through the engine below.
                payload['location'] = ''
                new_spool = spoolman_api.create_spool(payload)
                if new_spool and 'id' in new_spool:
                    created_spool_ids.append(new_spool['id'])
                    created.append((index, new_spool['id']))
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

        out = {
            "success": True,
            "filament_id": filament_id,
            "created_spools": created_spool_ids
        }
        if spool_data and (isinstance(data.get('placements'), list) or any(wants)):
            out.update(_place_created(created, wants, data))
        return jsonify(out)

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


def _take_archived_off(sid, original, written, dirty):
    """Group 40.7 review (wizard-archive-before-asked-move) — an edit that
    archived the spool (it weighed it out to empty, or ticked Archived) AND
    changes its Location. The edit's first write names where the spool still is,
    so update_spool's archive edge archived it IN PLACE: on its head, with its
    trail, its single-slot box still attached. The engine's move came after, and
    a move it asked about (the head is printing) or refused left it there,
    archived ON the head and hidden from FCC's views, and a later weight fix
    unarchived it on that head next to whatever was loaded since.

    So before the move, this writes the archive edge's own outcome: location ''
    and the trail cleared (`_TRAIL_KEYS`, as _direct_location_write blanks them)
    and the spool's own single-slot box released, unasked even mid-print, as the
    archive edge has always taken a used-up spool off its head. `archived: True`
    rides along (belt and braces since Group 51.1, when a write without a weight
    stopped counting as a refill). No
    `fcc_pre_archive_location` note: the user asked for the spool elsewhere, so a
    later refill must not put it back here. The move then starts from Unassigned
    (it asks about nothing it leaves) and stores the spool, never loading the
    head a slot feeds (api_edit_spool_wizard); when it doesn't land, the spool
    is archived and Unassigned, which is where an archive without a move leaves it.

    `original` / `written` / `dirty`: the spool before the edit, the edit's first
    write's answer and what that write sent. Whether it archived the spool is
    the answer's `archived` (Spoolman answers the whole record), else a re-read,
    and only when the write touched a weight or Archived. Returns the LocationID
    it was taken off, or None (nothing archived here, already Unassigned, or the
    write failed: then the move runs from where it is, as before)."""
    was = _loc_key((original or {}).get('location'))
    if not was or (original or {}).get('archived'):
        return None
    if not any(k in (dirty or {}) for k in ('used_weight', 'initial_weight', 'archived')):
        return None
    if isinstance(written, dict) and 'archived' in written:
        archived_now = bool(written.get('archived'))
    else:
        rec = spoolman_api.get_spool(sid)
        archived_now = bool(isinstance(rec, dict) and rec.get('id') is not None and rec.get('archived'))
    if not archived_now:
        return None
    pre_extra = original.get('extra') if isinstance(original.get('extra'), dict) else {}
    extra = {k: '' for k in _TRAIL_KEYS if str(pre_extra.get(k) or '').strip().strip('"')}
    payload = dict({'location': '', 'archived': True}, **({'extra': extra} if extra else {}))
    res = spoolman_api.update_spool(sid, payload)
    if not res:
        err = spoolman_api.LAST_SPOOLMAN_ERROR or "Spoolman rejected the update"
        state.add_log_entry(f"❌ #{sid} was archived but is still filed on {was}: FCC couldn't take it "
                            f"off ({err})", "ERROR", "ff4444")
        return None
    logic.release_box_after_direct_write(sid, original, res)
    state.add_log_entry(f"📦 #{sid} is archived (used up), so it was taken off {was} before its move",
                        "INFO", "00ccff")
    return was


def _archived_off_note(sid, was):
    return f"#{sid} is archived (used up), so it was taken off {was}: it is Unassigned."


@app.route('/api/edit_spool_wizard', methods=['POST'])
def api_edit_spool_wizard():
    """Endpoint to handle natively editing Filaments and Spools from the Wizard Edit UI.

    Group 40.7 (Derek, 2026-10-19, answer 7): a changed Location is a MOVE, as in
    Force Location. Every other edit is saved first (the spool, then the
    filament); the location then goes through the engine: Unassigned through
    perform_force_unassign, anything else through perform_smart_move (Smart Load,
    the active-print and "already fed" questions, the Printer-row refusal). A
    refused or asked move leaves the other edits saved. The request's extra
    fields, read only when the location changes (the move doors' contract):
      slot           an explicit slot (the picker's Swap / Overwrite)
      picked_slot    a free slot the picker chose, kept only while still free
      expected_feed  what that slot fed when the user chose it ('' = no toolhead)
      auto_deploy    false: store it there, never load the head the slot feeds
      confirmed_toolheads / confirmed_fed_heads / seen_printing   as at the doors
    A slot (`slot` / `picked_slot`) other than the spool's own in the box it is
    already in is a move too (a floating spool into a slot of its own box).
    Answer, when the location changes: `spool_saved` (every other edit is saved,
    also when there was none), `location_moved`, `location_result` (the engine's
    answer, untouched), `location_where` (where it landed, once moved),
    `location_now` (the LocationID it is filed on once moved, '' = Unassigned:
    the page's Location field shows it, so a second Save moves nothing; Group
    40.7 review) and `to_buffer` (a same-slot swap's old spool). `success` is
    true only when the move landed too; otherwise `msg` says what was saved and
    why it didn't move, in words a page from before 40.7 can show ("Saved your
    other changes, but #57 was not moved to LR-MDB-1: …"), `stale_page` marks a
    question such a page can't answer (logic.stale_fed_refusal, then
    stale_confirm_refusal), and `pick_refused` a refusal over the picker's own
    choice (_pick_refused: the page drops it and picks again).
    Group 40.7 review: an edit that archives the spool and changes its Location
    takes it off where it is first (_take_archived_off), so a move that is asked
    about or refused never leaves an archived spool on a head; the move then
    stores it (`auto_deploy: false`) and it stays archived (Group 51.1: a move's
    write is no refill, so it no longer needs archiving again where it lands)."""
    data = request.json
    spool_id = data.get('spool_id')
    filament_id = data.get('filament_id')
    filament_data = data.get('filament_data')
    spool_data = data.get('spool_data')

    if not spool_id:
        return jsonify({"success": False, "msg": "Missing Spool ID for edit session."})

    # Group 40.7: where the spool moves to ('' = Unassigned), when the edit moves it.
    new_location = None
    original_spool = None
    spool_res = None
    # Group 40.7 review: where an archived spool was taken off before its move.
    archived_off = None
    try:
        # 28.B5 — track whether the spool half actually persisted so a later
        # filament rejection reports partial success accurately (the spool write
        # commits BEFORE the filament write; a filament failure must not be
        # reported as if nothing landed).
        spool_committed = False
        fil_committed = False
        # Update Spool First
        if spool_data:
            # Prevent 500 errors by only passing actual changes to Spoolman
            original_spool = spoolman_api.get_spool(spool_id)
            if original_spool:
                dirty_spool_data = {}
                for k, v in spool_data.items():
                    if k == 'location':
                        # Group 40.7: a changed Location is a move, made through the
                        # engine below once the other edits are saved, never a
                        # direct write. One form (case, quotes, "UNASSIGNED"), so
                        # the same place typed differently moves nothing.
                        if _loc_key(v) != _loc_key(original_spool.get('location')):
                            new_location = _loc_key(v)
                        elif _loc_key(v) and _reslot_asked(data, original_spool, _loc_key(v)):
                            new_location = _loc_key(v)
                        continue
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

                if new_location is not None and dirty_spool_data:
                    # update_spool's archive and unarchive edges move a spool
                    # themselves when a write names no location (to Unassigned, or
                    # back where it was archived from), and they have always left a
                    # location the caller named alone. The move is the engine's, so
                    # this write names where the spool is now.
                    dirty_spool_data['location'] = original_spool.get('location') or ''
                spool_data = dirty_spool_data
                state.logger.info(f"DIRTY SPOOL DATA: {dirty_spool_data}")
            else:
                # 27.1 — a Spoolman blip on the pre-fetch (get_spool -> None)
                # must NOT degrade into a raw full-overwrite PATCH: without the
                # original we can't run the dirty-diff OR the SYSTEM_MANAGED
                # strip, so forwarding the raw payload would ship container_slot
                # / physical_source verbatim and reopen the Item-4 slot-clobber
                # window (the April-outage class the write-surface conventions
                # exist to prevent). Fail closed and surface the error.
                err = spoolman_api.LAST_SPOOLMAN_ERROR or (
                    f"Could not read Spool {spool_id} before edit")
                state.logger.warning(
                    f"edit_spool_wizard: pre-edit get_spool({spool_id}) returned "
                    f"None; refusing to write a raw-payload PATCH. {err}")
                return jsonify({
                    "success": False,
                    "msg": f"Failed to update Spool {spool_id}: {err}",
                    "error": err,
                })

            if spool_data:
                spool_res = spoolman_api.update_spool(spool_id, spool_data)
                if not spool_res:
                    err = spoolman_api.LAST_SPOOLMAN_ERROR or "Spoolman rejected the update"
                    failed = {
                        "success": False,
                        "msg": f"Failed to update Spool {spool_id}: {err}",
                        "error": err,
                    }
                    if new_location is not None:
                        failed.update(spool_saved=False, location_moved=False)
                        failed["msg"] += f" Nothing was saved, and #{spool_id} was not moved."
                    return jsonify(failed)
                spool_committed = True
                # Group 42 review: a write that changed the spool's location off a
                # head releases its own single-slot box. Since 40.7 a Location edit
                # is the engine's move (below), which releases the box itself, and
                # this write names where the spool already is, so only the archive
                # edge's own move off a head can reach here (it released already,
                # and a second release finds nothing to do).
                logic.release_box_after_direct_write(spool_id, original_spool, spool_res)
                # 24.F — the wizard edit-spool save is ALSO a manual weight surface.
                # Log the before➔after breakdown when a weight field was dirty
                # (`spool_data` is the dirty diff at this point; `original_spool` is
                # the pre snapshot — None when get_spool blipped, handled by helper).
                if any(k in spool_data for k in ("used_weight", "initial_weight")):
                    _log_manual_weight_change(spool_id, original_spool, spool_res)
                if new_location is not None:
                    # Group 40.7 review: an archived spool leaves where it is
                    # before its move, even if a filament rejection stops below.
                    archived_off = _take_archived_off(spool_id, original_spool, spool_res, spool_data)

        # Unassigned was asked, and taking an archived spool off made it so.
        unassigned_by_archive = archived_off is not None and new_location == ''

        # Update Filament Second (if applicable)
        if filament_id and filament_data:
            fil_res = spoolman_api.update_filament(filament_id, filament_data)
            if not fil_res:
                err = spoolman_api.LAST_SPOOLMAN_ERROR or "Spoolman rejected the update"
                state.logger.warning(f"Failed to cleanly update Filament {filament_id} during spool edit: {err}")
                # 28.B5 — if the spool half already committed, say so (partial
                # persist reported honestly, not as a total failure). Retry is
                # benign: the spool diff comes up empty on the second pass.
                msg = (f"Spool saved, but filament update rejected: {err}"
                       if spool_committed else f"Filament update rejected: {err}")
                failed = {
                    "success": False,
                    "msg": msg,
                    "error": err,
                    "spool_saved": spool_committed,
                }
                if unassigned_by_archive:
                    failed["location_moved"] = True
                    failed["msg"] += f" {_archived_off_note(spool_id, archived_off)}"
                elif new_location is not None:
                    # Group 40.7: the move comes last, so nothing moved; saving
                    # again moves it (the spool's diff is empty by then).
                    failed["location_moved"] = False
                    failed["msg"] += (f" #{spool_id} was not moved to {new_location or 'Unassigned'} "
                                      f"either: save again to move it.")
                    if archived_off:
                        failed["msg"] += f" {_archived_off_note(spool_id, archived_off)}"
                return jsonify(failed)
            fil_committed = True

        out = {"success": True, "spool_id": spool_id}
        warnings = []
        # Group 42.3c: see /api/spool/update.
        if spool_data and isinstance(spool_res, dict) and spool_res.get('fcc_warning'):
            warnings.append(spool_res['fcc_warning'])
        if new_location is not None:
            # Group 40.7: the Location, last, through the engine.
            if unassigned_by_archive:
                # Group 40.7 review: _take_archived_off made it Unassigned already.
                moved, result, stale = True, True, None
            else:
                try:
                    # An archived spool is stored, never loaded onto the head a
                    # box slot feeds (that would leave it archived on a head).
                    moved, result, stale = _wizard_move(
                        spool_id, new_location, data,
                        placement=dict(data, auto_deploy=False) if archived_off else data,
                        current_loc='' if archived_off else (original_spool or {}).get('location'))
                except Exception as e:   # the other edits are saved: say so
                    state.add_log_entry(f"❌ Wizard edit: #{spool_id} was not moved to "
                                        f"{new_location or 'Unassigned'}: {e}", "ERROR", "ff4444")
                    moved, result, stale = False, {"status": "error", "msg": f"the move crashed ({e})"}, None
            out.update(spool_saved=True, location_moved=moved, location_result=result)
            if isinstance(result, dict) and result.get('to_buffer'):
                out["to_buffer"] = result['to_buffer']
            if moved:
                if new_location:
                    out["location_where"], out["location_now"] = _landed_at(spool_id, new_location, result)
                else:
                    out["location_where"], out["location_now"] = 'Unassigned', ''
                note = _deploy_skipped_note(spool_id, new_location, result)
                if note:
                    warnings.append(note)
            else:
                out["success"] = False
                why = _move_why(result, spool_id, stale=stale, can_ask='confirmed_toolheads' in data)
                out["msg"] = _not_moved_msg(spool_id, new_location, why,
                                            saved_other=spool_committed or fil_committed)
                if stale:
                    out["stale_page"] = True
                if _pick_refused(data, new_location, result, spool_id):
                    out["pick_refused"] = True
                if archived_off:
                    note = _archived_off_note(spool_id, archived_off)
                    out["msg"] += f" {note}"
                    if _is_question(result) and not stale:
                        # A 40.7 page shows the question, not `msg`.
                        warnings.append(note)
        if warnings:
            out["warning"] = " ".join(warnings)
        return jsonify(out)

    except Exception as e:
        state.logger.error(f"Wizard Edit Error: {e}")
        return jsonify({"success": False, "msg": str(e)})

_TRAIL_KEYS = ('container_slot', 'physical_source', 'physical_source_slot', logic.PRE_BOX_KEY)


def _direct_location_write(sid, pre, updates):
    """Group 40.7 — the location part of a /api/spool/update, which writes straight
    to Spoolman (no browser page sends it a location today: the weigh screens send
    weights only, and a location is a move, which the doors make). Returns
    (refusal or None, updates to write).

    A toolhead, or a Printer row that isn't one, is refused with NOTHING written:
    a head takes a spool through a move (Smart Load unloads the spool there first,
    and a print is asked about), so a direct write could stack two. Any other
    change of location blanks the slot and trail of the place the spool LEFT
    (`container_slot`, `physical_source`, `physical_source_slot`, and a
    `fcc_pre_box_location` note; Derek, 2026-10-15: a forced location shouldn't
    still flag the spool as coming from its old slot). Written as '', never
    omitted, because the extras merge keeps an omitted key; a key the caller sent
    itself is written as sent."""
    if not isinstance(pre, dict) or pre.get('id') is None:
        msg = f"Couldn't read #{sid} from Spoolman to check where it is, so nothing was written. Try again."
        state.add_log_entry(f"⚠️ {msg}", "WARNING", "ffaa00")
        return {"status": "error", "msg": msg}, updates
    new_loc = _loc_key(updates.get('location'))
    if new_loc == _loc_key(pre.get('location')):
        return None, updates
    loc_list = locations_db.load_locations_list() or []
    printer_map = locations_db.get_active_printer_map() or {}
    rows = {str(r.get('LocationID', '')).strip().upper(): r for r in loc_list if isinstance(r, dict)}
    row = rows.get(new_loc)
    if locations_db.is_printer_row_not_head(new_loc, row, printer_map):
        msg = f"{logic.printer_row_refusal(new_loc, row, loc_list).rstrip('.')}. Nothing was written."
        state.add_log_entry(f"⚠️ #{sid} not moved: {msg}", "WARNING", "ffaa00")
        return {"status": "error", "blocked_reason": "printer_row", "msg": msg}, updates
    if logic._holds_one_spool(new_loc, printer_map, rows):
        msg = (f"{new_loc} is a toolhead: a spool goes onto one through a move, which unloads the spool "
               f"there first and asks when it is printing. Nothing was written — scan #{sid} onto "
               f"{new_loc}, or use Force Location.")
        state.add_log_entry(f"⚠️ #{sid} not moved: {msg}", "WARNING", "ffaa00")
        return {"status": "error", "blocked_reason": "toolhead", "msg": msg}, updates
    pre_extra = pre.get('extra') if isinstance(pre.get('extra'), dict) else {}
    left = [k for k in _TRAIL_KEYS if str(pre_extra.get(k) or '').strip().strip('"')]
    if not left:
        return None, updates
    out = dict(updates)
    extra = dict(updates['extra']) if isinstance(updates.get('extra'), dict) else {}
    for k in left:
        extra.setdefault(k, '')
    out['extra'] = extra
    return None, out


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

    Group 40.7: a `location` that changes is checked first (_direct_location_write):
    a toolhead or a Printer row is refused with nothing written (`blocked_reason`
    "toolhead" / "printer_row"), and any other new place blanks the slot and trail
    the spool left behind.
    """
    try:
        data = request.json
        spool_id = data.get('id')
        updates = data.get('updates')

        if not spool_id or not updates:
            return jsonify({"status": "error", "msg": "Missing id or updates"})

        pre = spoolman_api.get_spool(spool_id) or {}
        pre_archived = bool(pre.get('archived', False))

        if isinstance(updates, dict) and 'location' in updates:
            refusal, updates = _direct_location_write(spool_id, pre, updates)
            if refusal:
                return jsonify(refusal)

        res = spoolman_api.update_spool(spool_id, updates)
        if not res:
            err = spoolman_api.LAST_SPOOLMAN_ERROR or "Spoolman rejected the update"
            return jsonify({"status": "error", "msg": f"Failed to update spool: {err}", "error": err})
        # Group 42 review: a location change off a head releases the spool's own
        # single-slot box, as a move would (the engine never ran).
        logic.release_box_after_direct_write(spool_id, pre, res)

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

        out = {
            "status": "success",
            "auto_archived": auto_archived,
            "needs_empty_weight_prompt": needs_prompt,
            "filament_id": filament_id,
        }
        # Group 42.3c: an auto-unarchived spool whose old toolhead holds another
        # spool now went to Unassigned; the weigh screen toasts this at 7 s.
        if res.get('fcc_warning'):
            out["warning"] = res['fcc_warning']
        return jsonify(out)
    except Exception as e:
        state.logger.error(f"Spool Update Error: {e}")
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

