"""Scan pipeline + Prusament cluster routes (L316 step 6).

Moved verbatim from app.py: the /api/identify_scan dispatcher (every barcode
flows through it — spool/filament label-confirm, location, assignment,
CMD:AUDIT activation + active-session delegation, Prusament URLs),
/api/buffer/clear, /api/manage_contents, /api/update_filament + the shared
`_format_filament_edit_log` formatter, and the Prusament scan cluster
(_pm_norm/_pm_num/_pm_first_pos, _PM_TEMP_LABELS/_PM_WEIGHT_TOL,
_compute_prusament_spool_weight_diff, _handle_prusament_url_scan) together
with /api/spool/prusament_apply_weights — the L200 confirm-apply endpoint
that forward-references the _pm_* helpers by design.

Preserved semantics (do not 'fix' in a move — see the carve plan):
- state.GLOBAL_BUFFER is READ via getattr and REASSIGNED as an attribute of
  the state module (never from-imported) — the frontend buffer replica
  depends on the reassignment being visible module-wide.
- spoolman_api.LAST_SPOOLMAN_ERROR reads stay adjacent to the failing write.
- Both label-confirm branches mutate the fetched extra dict and send the
  FULL dict back, relying on update_spool/update_filament's read-merge-write
  sibling preservation.
- logic._active_print_info_for_location is a deliberate private-name
  cross-module call (formalizing it is a follow-up, not part of the move).

Python 3.9 runtime (the container image) — keep syntax 3.9-safe.
"""
from flask import request, jsonify  # type: ignore
import time

import state  # type: ignore
import locations_db  # type: ignore
import spoolman_api  # type: ignore
import logic  # type: ignore
import external_parsers  # type: ignore

from app_core import app

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
    except Exception as e:
        state.logger.error(f"Failed to update filament #{fid}: {e}")
        return jsonify({"success": False, "msg": str(e)})

    if not updated:
        # Surface the stashed Spoolman error body so the UI can tell the user
        # WHY the update was rejected (invalid field, bad vendor_id, etc.)
        # instead of showing an opaque "rejected" message.
        err = spoolman_api.LAST_SPOOLMAN_ERROR or "No response body"
        return jsonify({"success": False, "msg": f"Spoolman rejected update: {err}"})

    # 27.8 — the write COMMITTED. Format+log the audit line in its OWN guarded
    # block, OUTSIDE the success-determining try: a formatter/logger crash must
    # NOT invert a committed write into success:false (which made the user retry
    # and double-write). Log the log-failure and still report success.
    try:
        state.add_log_entry(
            _format_filament_edit_log(fid, before, data),
            "SUCCESS", "00ff00",
        )
    except Exception as e:
        state.logger.error(
            f"Filament #{fid} updated OK but activity-log write failed: {e}")
    return jsonify({"success": True, "filament": updated})

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

    # 28.C1 — reject an unrecognized action with an accurate message. Without
    # this an unknown action fell through to the 'Spool not found' guard below
    # (misleading — nothing was looked up) and the terminal bare return was
    # unreachable.
    if action not in ('clear_location', 'add', 'remove', 'force_unassign'):
        return jsonify({"success": False, "msg": f"Unknown action: {action}"})

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
        ejected_ids = []
        skipped_slotted = []
        for spool in contents:
            # [ALEX FIX] Protect "Ghost" items from being ejected when a box is cleared
            if spool.get('is_ghost'):
                continue

            slot_val = spool.get('slot', '')
            if not slot_val or slot_val == 'None' or slot_val == '':
                logic.perform_smart_eject(spool['id'], confirm_active_print=True)
                ejected_ids.append(spool['id'])
            else:
                # 27.6 — a spool loaded into a real slot (toolhead / MMU) is
                # deliberately NOT auto-ejected by a bulk clear (that would
                # silently unassign a live feed). Collect the survivors so the
                # caller learns the location isn't actually empty rather than
                # getting a bare success.
                skipped_slotted.append(spool['id'])
        if skipped_slotted:
            _surv = ", ".join(str(i) for i in skipped_slotted)
            state.add_log_entry(
                f"⚠️ Cleared {loc_id}: {len(ejected_ids)} unslotted spool(s) "
                f"ejected; {len(skipped_slotted)} slotted spool(s) left in place "
                f"(IDs {_surv}) — unload the slot to remove.",
                "WARNING", "ffaa00")
            return jsonify({
                "success": True,
                "ejected": ejected_ids,
                "skipped_slotted": skipped_slotted,
                "msg": f"{len(skipped_slotted)} slotted spool(s) left in place — "
                       f"unload the slot to remove them.",
            })
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
    # 28.C1 — the action set is validated at the top, so control never reaches
    # here; a defensive JSON error keeps Flask from returning None if it ever did.
    return jsonify({"success": False, "msg": f"Unknown action: {action}"})

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
        if state.AUDIT_SESSION.get('active'):
            # 27.5 — re-scanning CMD:AUDIT mid-audit must NOT silently
            # reset_audit() and wipe in-progress scanned/expected/rogue state.
            # No-op: refresh the idle watchdog and tell the user an audit is
            # already running (they end it explicitly via CMD:CANCEL/CMD:DONE).
            state.AUDIT_SESSION['last_activity_ts'] = time.time()
            state.add_log_entry(
                "🕵️‍♀️ Audit already in progress — scan a Location to continue, "
                "or CMD:CANCEL to end.", "INFO", "ff00ff")
            return jsonify({"type": "command", "cmd": "clear"})
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
        audit_res = logic.process_audit_scan(res)
        # 28.C2 — propagate an audit-scan error to the scanner UI (the frontend
        # toasts res.type=='error') instead of always answering cmd:clear and
        # leaving the failure in the Activity Log only. A successful audit scan
        # still returns the buffer-clear signal.
        if isinstance(audit_res, dict) and audit_res.get('status') == 'error':
            return jsonify({
                "type": "error",
                "msg": audit_res.get('msg') or "Scan not allowed during audit.",
            })
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

        # 27.10 — unknown/deleted spool id (get_spool -> None): the branch above
        # was skipped, so return a renderable scan-failure payload (the frontend
        # toasts res.type=='error') + a WARNING log, instead of falling through
        # to the bare resolver dict {'type':'spool','id':N} the UI can't render.
        state.add_log_entry(
            f"❌ Spool #{sid} not found (deleted or unknown id) — scan dropped",
            "WARNING", "ffaa00")
        return jsonify({"type": "error", "msg": f"Spool #{sid} not found"})

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

        # 27.10 — unknown/deleted filament id (get_filament -> None): same
        # renderable scan-failure contract as the spool branch, instead of
        # falling through to the bare {'type':'filament','id':N} resolver dict
        # (which the UI would try to open as a real filament).
        state.add_log_entry(
            f"❌ Filament #{fid} not found (deleted or unknown id) — scan dropped",
            "WARNING", "ffaa00")
        return jsonify({"type": "error", "msg": f"Filament #{fid} not found"})

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

