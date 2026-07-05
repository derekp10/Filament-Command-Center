"""Inventory wizard / vendor / CRUD / search routes (L316 step 5).

Moved verbatim from app.py: vendor CRUD (+ `_format_vendor_edit_log`),
filament/spool read proxies, the Spoolman extra-field schema cluster
(FIELD_ORDER / `_enrich_field_order` / external fields + restore_field_order
+ add_choice), the wizard create/edit endpoints, the generic
/api/spool/update partial-update (auto-archive surfacing), external-parser
search dispatch, and global inventory search. `_log_manual_weight_change`
is the shared before→after log for BOTH manual weight funnels
(api_spool_update + api_edit_spool_wizard — CLAUDE.md Group 24.F).

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
         # 28.B6 — a missing required field is a client validation error → 400.
         return jsonify({"success": False, "msg": "Missing required fields."}), 400
         
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
        # 28.B5 — track whether the spool half actually persisted so a later
        # filament rejection reports partial success accurately (the spool write
        # commits BEFORE the filament write; a filament failure must not be
        # reported as if nothing landed).
        spool_committed = False
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
                    return jsonify({
                        "success": False,
                        "msg": f"Failed to update Spool {spool_id}: {err}",
                        "error": err,
                    })
                spool_committed = True
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
                # 28.B5 — if the spool half already committed, say so (partial
                # persist reported honestly, not as a total failure). Retry is
                # benign: the spool diff comes up empty on the second pass.
                msg = (f"Spool saved, but filament update rejected: {err}"
                       if spool_committed else f"Filament update rejected: {err}")
                return jsonify({
                    "success": False,
                    "msg": msg,
                    "error": err,
                    "spool_saved": spool_committed,
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

