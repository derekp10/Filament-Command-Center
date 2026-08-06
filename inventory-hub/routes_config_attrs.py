"""Config-system + filament-attributes manager routes (L316 step 9).

Moved verbatim from app.py: the L18 config HTTP surface (GET/PUT /api/config,
export with redacted secrets via app.response_class, import with dry-run
diff) and the L58 filament-attributes manager (report, bulk_set, add_choice,
the ~170-line destructive remove_choice schema migration, sweep_unused).
Function-local `import requests as _req` / `import json as _json` kept
verbatim (deliberate lazy imports). Offline behavior pinned by
tests/test_l316_charact_filament_attributes_unit.py.

NOTE: this module stays FLAT at the inventory-hub root on purpose —
tests/test_no_direct_extra_patch.py scans INV_HUB.glob('*.py')
non-recursively for raw extra-PATCH calls, and remove_choice/sweep_unused
carry the only sanctioned (noqa-marked) ones.

api_audit_session did NOT move here: it calls _check_audit_idle_timeout,
which is coupled to the /api/logs heartbeat — the trio moves together in
step 11 (routes_state_pulse).

Python 3.9 runtime (the container image) — keep syntax 3.9-safe.
"""
from flask import request, jsonify  # type: ignore
import json
import threading

import state  # type: ignore
import config_loader  # type: ignore
import config_schema  # type: ignore
import spoolman_api  # type: ignore
import attr_migration  # type: ignore

from app_core import app

# Serializes the destructive schema migration. It rewrites every
# attribute-bearing record inside ONE request, which can run for minutes;
# Flask's dev server is threaded, so without this a second click (or a second
# tab) could DELETE the field while the first run is still restoring — request
# B's filament GET landing after request A's DELETE snapshots records that have
# already lost the key, and B then "restores" that emptiness over A's work.
_MIGRATION_LOCK = threading.Lock()

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

    # 36.4 — choices FCC suppresses locally. Removing a choice for real costs a
    # full schema rebuild across every attribute-bearing record, so the default
    # "remove" hides it instead. A hidden choice must not appear in `choices`
    # (or the picker would still offer it) and must not be counted as rogue
    # (it is deliberately suppressed, not orphaned), so it gets its own bucket.
    # Intersect with the LIVE schema: a hidden entry for a choice that no
    # longer exists in Spoolman (purged here, swept, or removed by hand) is
    # stale, and reporting it would put a dead name in the Hidden strip with an
    # "unhide" button that could never bring anything back.
    schema_choices = set(choices)
    hidden_choices = [c for c in attr_migration.load_hidden_choices()
                      if c in schema_choices]
    hidden_set = set(hidden_choices)
    choices = [c for c in choices if c not in hidden_set]

    filaments = []
    counts = {c: 0 for c in choices}
    hidden_counts = {}         # 36.4 — usage still carried by a HIDDEN choice
    rogue_counts = {}          # 29.A1 — attrs carried by a filament but NOT in the schema
    # 36.4 — how many records a PURGE would rewrite. The destructive migration
    # touches every filament carrying the key, so the confirm dialog can state
    # the real cost instead of letting the user discover it afterwards.
    affected_records = 0
    choice_set = set(choices)
    for f in raw:
        fid = f.get("id")
        if fid is None:
            continue
        extras = f.get("extra") or {}
        if "filament_attributes" in extras:
            affected_records += 1
        attrs = spoolman_api._parse_filament_attrs_value(extras.get("filament_attributes"))
        for a in attrs:
            # 29.A1 — keep `counts` restricted to the schema choice list (the
            # live report-shape test asserts counts keys are a SUBSET of
            # choices). A rogue attribute — one a record still carries that is
            # no longer a schema choice — is surfaced explicitly in
            # `rogue_counts` instead of silently inflating `counts`.
            if a in choice_set:
                counts[a] += 1
            elif a in hidden_set:
                hidden_counts[a] = hidden_counts.get(a, 0) + 1
            else:
                rogue_counts[a] = rogue_counts.get(a, 0) + 1
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
        "rogue_counts": rogue_counts,
        "hidden_choices": hidden_choices,
        "hidden_counts": hidden_counts,
        "affected_records": affected_records,
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
    # 29.A3 — reflect per-id failure in the top-level result. `success` is True
    # only when at least one id was actually processed (updated, or already
    # correct); an all-errored call (updated == 0 and unchanged == 0) now
    # reports success:false so a caller reading only `success` can't mistake a
    # total failure for a win. Partial success (>=1 processed) stays True with
    # the per-id detail in errors[].
    return jsonify({
        "success": updated > 0 or unchanged > 0,
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
        # Adding a name is the unambiguous statement "I want that tag back", so
        # un-hide it. Without this, re-adding a HIDDEN choice is a no-op union
        # against Spoolman's schema (it was never removed) that reports success
        # while the tag stays invisible — a success toast for an action with no
        # effect, and the documented bulk re-tag recovery path stays unusable.
        was_hidden = choice in attr_migration.load_hidden_choices()
        if was_hidden:
            res = dict(res)
            res['hidden_choices'] = attr_migration.unhide_choice(choice)
            res['unhidden'] = True
        state.add_log_entry(
            f"🏷️ Filament Attributes: {'un-hid' if was_hidden else 'added'} choice {choice!r}",
            "INFO", "00ccff"
        )
    return jsonify(res)


def _report_restore_failures(op, restore_failures, extras_snapshot):
    """Log every casualty of a partial schema migration, by id, with the exact
    payload we failed to write back.

    Thin delegate to :func:`attr_migration.report_restore_failures`. The
    implementation lives there because all THREE force_reset sites need it —
    these two endpoints plus `spoolman_api.ensure_filament_attributes_cleaned`,
    which runs at boot and used to report a bare count with no ids at all. A
    private per-module copy is exactly how the three drifted apart in the first
    place.

    ⚠️ Pass the POST-filter payloads (what the PATCH actually sent), never
    the pre-filter snapshot — see the delegate's docstring for why.
    """
    return attr_migration.report_restore_failures(op, restore_failures, extras_snapshot)


def _recreate_field_payload(attr_field, new_choices):
    """Rebuild the field definition for the POST that follows a schema DELETE.

    Echoes back every property Spoolman gave us rather than only the four the
    original draft sent: `order`, `unit` and `default_value` were silently
    dropped, so each migration quietly reset them to schema defaults. Only keys
    actually present and non-null are forwarded, so a field that never had them
    is recreated exactly as before.

    `multi_choice` uses an `is not False` test, not `.get(..., True)`: a
    dict-default does not protect against Spoolman explicitly returning null,
    which would forward null and could bring the field back SINGLE-choice —
    silently making every multi-tag record invalid.
    """
    out = {
        "name": attr_field.get("name") or "Filament Attributes",
        "field_type": attr_field.get("field_type") or "choice",
        "multi_choice": attr_field.get("multi_choice") is not False,
        "choices": new_choices,
    }
    for k in ("order", "unit", "default_value"):
        v = attr_field.get(k)
        if v is not None:
            out[k] = v
    return out


def _build_restore_payloads(raw_fils, drop):
    """Map fid -> the exact extras dict to write back after the schema rebuild.

    Two deliberate narrowings versus the original loop:

    * **Only records that actually carry `filament_attributes`.** The DELETE
      drops rows for that key alone, so a filament without it loses nothing and
      needs no write. Measured on live dev (2026-08-06): 176 records written
      before, 158 after — 18 fewer independent chances to fail, and 18 fewer
      lost-update windows over extras edited since the list was read.
      (158 is the count carrying the KEY; only 112 carry a non-empty tag list,
      but the DELETE drops the row either way, so key-presence is the correct
      test.)
    * **The payload is POST-filter**, i.e. exactly what the PATCH sends. It is
      what gets snapshotted to disk and what gets logged on failure, so a
      hand-recovery can be replayed verbatim.

    The whole extras dict is still sent per record — Spoolman's PATCH replaces
    the entire `extra` sub-document, so a partial payload wipes siblings.
    """
    payloads = {}
    for f in raw_fils:
        fid = f.get('id')
        if fid is None:
            continue
        extras = f.get('extra') or {}
        if 'filament_attributes' not in extras:
            continue
        extras_out = dict(extras)
        attrs = spoolman_api._parse_filament_attrs_value(extras_out['filament_attributes'])
        extras_out['filament_attributes'] = json.dumps([a for a in attrs if a not in drop])
        payloads[fid] = extras_out
    return payloads


def _strip_choice_from_carriers(users, choice):
    """Remove `choice` from each carrier via the SAFE read-merge-write path.

    `spoolman_api.update_filament` merges the partial payload against the live
    record, so siblings survive (CLAUDE.md write-surface convention). This is
    how the hide path avoids the schema rebuild entirely: N carrier writes
    instead of a full-population force_reset, and every one of them is
    individually recoverable because nothing was deleted first.
    """
    stripped, errors = 0, []
    for fid, attrs in users:
        remaining = [a for a in attrs if a != choice]
        result = spoolman_api.update_filament(
            fid, {"extra": {"filament_attributes": json.dumps(remaining)}}
        )
        if result is None:
            errors.append({"id": fid,
                           "msg": spoolman_api.LAST_SPOOLMAN_ERROR or "unknown error"})
            continue
        stripped += 1
    return stripped, errors


@app.route('/api/filament_attributes/remove_choice', methods=['POST'])
def api_filament_attributes_remove_choice():
    """Remove a choice from the filament-attributes picker.

    TWO modes, because the destructive one is wildly disproportionate:

    **HIDE (default).** Strips the tag from the N filaments that carry it via
    `update_filament`'s read-merge-write, then records the choice in FCC's
    hidden list so it disappears from the manager, the picker and the sweep.
    Spoolman's schema is untouched, and it is reversible via `unhide_choice`.
    This is the default because Spoolman (0.23.1) cannot shrink a choice list
    in place — `add_or_update_extra_field` raises "Cannot remove existing
    choices" — so genuinely deleting ONE choice costs a DELETE + recreate of
    the whole field plus a PATCH of every attribute-bearing record. That is a
    production-shaped migration, and it was firing on a single click of an
    18x18px red X.

    **PURGE (`purge: true`).** The real schema removal, for when the choice must
    leave Spoolman itself. Same order as before (snapshot -> DELETE -> recreate
    -> restore), but hardened: a transient-empty-list guard, a last-choice
    guard, a recovery snapshot written to DISK before the DELETE, a bounded
    transport retry with verify-by-re-read on each restore, and an honest
    `success: false` when any record is left unrestored.

    Both modes keep the usage gate: if the choice is in use and `force` is not
    truthy, it refuses and returns `usage_count` so the UI can prompt.
    """
    import requests as _req
    payload = request.get_json(silent=True) or {}
    choice = str(payload.get('choice', '')).strip()
    force = bool(payload.get('force'))
    purge = bool(payload.get('purge'))
    if not choice:
        return jsonify({"success": False, "msg": "choice is required"}), 400
    if len(choice) > 80:
        return jsonify({"success": False, "msg": "choice too long (max 80 chars)"}), 400

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

    # Transient-state guard. sweep_unused has had this since it shipped;
    # remove_choice never did, and the asymmetry was a mass-loss path: with an
    # empty list `users` is empty (so the confirm gate is skipped) and the
    # restore set is empty, so the endpoint would DELETE the field, recreate
    # it, restore NOTHING and report success — wiping filament_attributes from
    # EVERY record because Spoolman happened to blink.
    if not raw_fils:
        return jsonify({
            "success": False,
            "msg": "Spoolman returned 0 filaments — refusing to act on a possibly-transient empty list.",
        })

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
                    f"records.")
        })

    # ---------------- HIDE (the default) ----------------
    if not purge:
        stripped, errors = _strip_choice_from_carriers(users, choice)
        if users and stripped == 0:
            # Nothing was stripped — do NOT hide, or the tag vanishes from the
            # UI while every record still carries it.
            state.add_log_entry(
                f"🏷️ Filament Attributes: could not hide {choice!r} — all "
                f"{len(errors)} strip write(s) failed. Choice left visible.",
                "ERROR", "ff4444",
            )
            return jsonify({
                "success": False, "mode": "hidden", "stripped": 0, "errors": errors,
                "msg": f"Could not strip {choice!r} from any filament — nothing was hidden.",
            })
        hidden = attr_migration.hide_choice(choice)
        state.add_log_entry(
            f"🏷️ Filament Attributes: hid choice {choice!r} "
            f"(stripped from {stripped}/{len(users)} filament(s); Spoolman schema untouched"
            + (f"; {len(errors)} write error(s)" if errors else "")
            + "). Reversible from the Choices Manager.",
            "INFO" if not errors else "WARNING",
            "00ccff" if not errors else "ffaa00",
        )
        return jsonify({
            "success": True,
            "mode": "hidden",
            "stripped": stripped,
            "errors": errors,
            "hidden_choices": hidden,
        })

    # ---------------- PURGE (explicit opt-in) ----------------
    new_choices = sorted(c for c in current_choices if c != choice)
    # Spoolman's ExtraFieldParameters requires `choices` to be a non-empty array
    # (or null); [] matches neither. Recreating with [] is rejected, which
    # leaves the schema MISSING and the restore loop never reached — every
    # filament permanently loses its attributes. Refuse BEFORE the DELETE.
    if not new_choices:
        return jsonify({
            "success": False,
            "msg": (f"{choice!r} is the last remaining choice. Spoolman cannot store a "
                    f"choice field with an empty option list, so purging it would leave "
                    f"the schema missing. Hide it instead, or add another choice first."),
        })

    if not _MIGRATION_LOCK.acquire(False):
        return jsonify({
            "success": False,
            "msg": "Another filament-attribute schema migration is already running. "
                   "Wait for it to finish — starting a second one can corrupt the first.",
        }), 409
    snap_path = None
    try:
        payloads = _build_restore_payloads(raw_fils, {choice})
        # The safety net goes to DISK before anything destructive happens. Until
        # now the snapshot lived only in this request's memory, so a crash
        # between the DELETE and the last restore was unbounded, untraced loss —
        # and in DEV, editing any .py restarts the container mid-flight.
        snap_path = attr_migration.write_recovery_snapshot(
            f"remove_choice({choice!r})", payloads)

        try:
            d_resp = _req.delete(
                f"{sm_url}/api/v1/field/filament/filament_attributes", timeout=15
            )
            if not d_resp.ok and d_resp.status_code != 404:
                attr_migration.clear_recovery_snapshot(snap_path)
                return jsonify({
                    "success": False,
                    "msg": f"Schema DELETE failed ({d_resp.status_code}): {d_resp.text[:200]}",
                })
        except Exception as e:
            # KEEP the snapshot. A returned status code (the branch above) is a
            # real answer meaning the field is intact, so clearing there is
            # right — but an EXCEPTION is a ReadTimeout/ConnectionError, and
            # that is precisely the case where Spoolman may have committed the
            # DELETE and only the response was lost. Discarding the recovery
            # payload here would re-create the exact failure this endpoint
            # exists to prevent: every attribute-bearing record stripped, and
            # the only durable copy of what to write back deleted with it.
            state.add_log_entry(
                f"⚠ Filament Attributes: schema DELETE outcome UNKNOWN ({e}) — the "
                f"field may already be gone. Recovery data kept at {snap_path}. "
                f"Check Spoolman before retrying.",
                "ERROR", "ff4444",
            )
            return jsonify({
                "success": False,
                "msg": f"Schema DELETE error: {e}. Outcome unknown — recovery data kept at {snap_path}.",
                "recovery_snapshot": snap_path,
            })

        payload_out = _recreate_field_payload(attr_field, new_choices)
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
                    "msg": f"Schema POST failed: {post_r.text[:200]}. Schema is now MISSING — "
                           f"re-run setup_fields.py. Restore data: {snap_path}",
                    "recovery_snapshot": snap_path,
                })
        except Exception as e:
            state.add_log_entry(
                f"⚠ Filament Attributes: schema POST error during {choice!r} removal: {e} — "
                f"re-run setup_fields.py to restore.",
                "ERROR", "ff4444",
            )
            return jsonify({
                "success": False,
                "msg": f"Schema POST error: {e}. Restore data: {snap_path}",
                "recovery_snapshot": snap_path,
            })

        restored, restore_failures, recovered = attr_migration.restore_extras(
            sm_url, payloads)
    finally:
        _MIGRATION_LOCK.release()

    # The POST-filter payloads are what the PATCH actually sent, so the logged
    # recovery data can be replayed verbatim. Logging the pre-filter snapshot
    # (as this used to) put the just-removed choice back into the "recovery"
    # payload, where it is no longer a legal value and would 400 on replay.
    lost_ids = _report_restore_failures(
        f"remove_choice({choice!r})", restore_failures, payloads)
    if not restore_failures:
        attr_migration.clear_recovery_snapshot(snap_path)
    # The choice is gone from the schema now, so a hidden entry for it is
    # meaningless — and worse, it would keep suppressing the name if the user
    # ever re-added it. Purging from the Hidden strip is the ONLY route to this
    # branch, so without this every purge leaves one behind.
    attr_migration.unhide_choice(choice)

    level = "INFO" if not restore_failures else "ERROR"
    color = "00ccff" if not restore_failures else "ff4444"
    state.add_log_entry(
        f"🏷️ Filament Attributes: purged choice {choice!r} from the schema "
        f"(stripped from {len(users)} filament(s); restored {restored}/{len(payloads)} "
        f"attribute-bearing records"
        + (f", {recovered} confirmed by re-read after a reported failure" if recovered else "")
        + (f"; ⚠️ LOST filament_attributes on filament(s) {lost_ids} — recovery payload in "
           f"hub.log and {snap_path}" if restore_failures else "")
        + ").",
        level, color,
    )
    return jsonify({
        # Honest: a record left unrestored is data loss, so this is NOT a
        # success. It used to return success:True regardless, which is why the
        # frontend showed a green toast over every one of these losses.
        "success": not restore_failures,
        "mode": "purged",
        "stripped": len(users),
        "restored": restored,
        "recovered": recovered,
        "restore_failures": restore_failures,
        "lost_ids": lost_ids,
        "recovery_snapshot": snap_path if restore_failures else None,
        "msg": (f"Purged {choice!r}, but {len(restore_failures)} filament(s) {lost_ids} "
                f"could not be restored and have LOST their attributes. "
                f"Recovery data: {snap_path}" if restore_failures else ""),
    })


@app.route('/api/filament_attributes/unhide_choice', methods=['POST'])
def api_filament_attributes_unhide_choice():
    """Bring a hidden choice back into the picker.

    The counterpart to remove_choice's default (hide) mode — hiding has to be
    reversible, or it is just deletion with extra steps.
    """
    payload = request.get_json(silent=True) or {}
    choice = str(payload.get('choice', '')).strip()
    if not choice:
        return jsonify({"success": False, "msg": "choice is required"}), 400
    hidden = attr_migration.unhide_choice(choice)
    state.add_log_entry(
        f"🏷️ Filament Attributes: un-hid choice {choice!r}.", "INFO", "00ccff"
    )
    return jsonify({"success": True, "hidden_choices": hidden})


@app.route('/api/filament_attributes/sweep_unused', methods=['POST'])
def api_filament_attributes_sweep_unused():
    """Find and (optionally) remove every choice with zero usage.

    Replaces the boot-time auto-promote path that was drained 2026-05-20
    to avoid the "add a new choice + forget to tag before next reboot →
    silently re-stripped" footgun. Same capability, but explicitly user-
    triggered: the UI previews the list (`force` omitted/false) and only
    commits with `force: true` after the user confirms.

    Preview shape:  { success, unused: [str, ...], total_choices: int,
                      affected_records: int }
    Commit shape:   { success, removed: [str, ...], restored: int,
                      restore_failures: [{id, msg}, ...], lost_ids: [...] }

    `choices` (optional, commit-only): restrict the sweep to a specific
    subset of the unused list. The Choices Manager UI uses this so the
    user can keep some currently-unused tags if they're about to be
    re-applied. The intersection with the freshly-computed unused list
    is enforced server-side — passing in a name that is NOT zero-usage
    will be silently dropped rather than risk wiping a tagged choice.

    ⚠️ Committing runs the SAME destructive schema migration as
    remove_choice's purge mode, so it carries the same hardening: a
    recovery snapshot on disk before the DELETE, a last-choice guard, a
    bounded transport retry with verify-by-re-read, the migration lock, and
    an honest `success: false` when a record is left unrestored.

    HIDDEN choices are excluded from the unused list. A hidden choice has
    already been dealt with from the user's point of view, and sweeping it
    would fire a full ~150-record migration for zero visible change.
    """
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

    usage = {c: 0 for c in current_choices}
    attr_bearing = 0
    for f in raw_fils:
        fid = f.get('id')
        if fid is None:
            continue
        extras = f.get('extra') or {}
        if 'filament_attributes' in extras:
            attr_bearing += 1
        attrs = spoolman_api._parse_filament_attrs_value(extras.get('filament_attributes'))
        for a in attrs:
            usage[a] = usage.get(a, 0) + 1
    hidden_set = set(attr_migration.load_hidden_choices())
    unused = sorted(c for c in current_choices
                    if not usage.get(c) and c not in hidden_set)

    if not force:
        return jsonify({
            "success": True,
            "unused": unused,
            "total_choices": len(current_choices),
            # So the confirm dialog can state the real cost instead of leaving
            # the user to discover that one click rewrites their whole library.
            "affected_records": attr_bearing,
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
    # Same last-choice guard as remove_choice's purge: Spoolman rejects a
    # choice field with an empty option list, and that rejection lands AFTER
    # the DELETE — schema missing, restore loop never reached, every filament
    # loses its attributes. Sweeping every remaining choice at once is
    # reachable from the UI, whose checkboxes default to all-checked.
    if not new_choices:
        return jsonify({
            "success": False,
            "msg": ("That would sweep every remaining choice. Spoolman cannot store a "
                    "choice field with an empty option list, so the field would be left "
                    "missing. Keep at least one choice, or hide them instead."),
        })

    if not _MIGRATION_LOCK.acquire(False):
        return jsonify({
            "success": False,
            "msg": "Another filament-attribute schema migration is already running. "
                   "Wait for it to finish — starting a second one can corrupt the first.",
        }), 409
    snap_path = None
    try:
        # Only attribute-bearing records need restoring: the DELETE drops rows
        # for `filament_attributes` alone, so a filament without it loses
        # nothing. The swept choices are zero-usage by construction, so the
        # filter below is defensive only.
        payloads = _build_restore_payloads(raw_fils, unused_set)
        snap_path = attr_migration.write_recovery_snapshot(
            f"sweep_unused({unused})", payloads)

        try:
            d_resp = _req.delete(
                f"{sm_url}/api/v1/field/filament/filament_attributes", timeout=15
            )
            if not d_resp.ok and d_resp.status_code != 404:
                attr_migration.clear_recovery_snapshot(snap_path)
                return jsonify({
                    "success": False,
                    "msg": f"Schema DELETE failed ({d_resp.status_code}): {d_resp.text[:200]}",
                })
        except Exception as e:
            # KEEP the snapshot. A returned status code (the branch above) is a
            # real answer meaning the field is intact, so clearing there is
            # right — but an EXCEPTION is a ReadTimeout/ConnectionError, and
            # that is precisely the case where Spoolman may have committed the
            # DELETE and only the response was lost. Discarding the recovery
            # payload here would re-create the exact failure this endpoint
            # exists to prevent: every attribute-bearing record stripped, and
            # the only durable copy of what to write back deleted with it.
            state.add_log_entry(
                f"⚠ Filament Attributes: schema DELETE outcome UNKNOWN ({e}) — the "
                f"field may already be gone. Recovery data kept at {snap_path}. "
                f"Check Spoolman before retrying.",
                "ERROR", "ff4444",
            )
            return jsonify({
                "success": False,
                "msg": f"Schema DELETE error: {e}. Outcome unknown — recovery data kept at {snap_path}.",
                "recovery_snapshot": snap_path,
            })

        payload_out = _recreate_field_payload(attr_field, new_choices)
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
                    "msg": f"Schema POST failed: {post_r.text[:200]}. Schema is now MISSING — "
                           f"re-run setup_fields.py. Restore data: {snap_path}",
                    "recovery_snapshot": snap_path,
                })
        except Exception as e:
            # The exception path used to write NOTHING to the Activity Log, so a
            # network blip here left the schema MISSING with no trace anywhere
            # but the HTTP response — which the frontend drops into a toast.
            state.add_log_entry(
                f"⚠ Filament Attributes: schema POST error during sweep: {e} — "
                f"re-run setup_fields.py to restore.",
                "ERROR", "ff4444",
            )
            return jsonify({
                "success": False,
                "msg": f"Schema POST error: {e}. Restore data: {snap_path}",
                "recovery_snapshot": snap_path,
            })

        restored, restore_failures, recovered = attr_migration.restore_extras(
            sm_url, payloads)
    finally:
        _MIGRATION_LOCK.release()

    lost_ids = _report_restore_failures(
        f"sweep_unused({unused})", restore_failures, payloads)
    if not restore_failures:
        attr_migration.clear_recovery_snapshot(snap_path)

    state.add_log_entry(
        f"🧹 Filament Attributes: swept {len(unused)} unused choice(s): {unused} "
        f"(restored {restored}/{len(payloads)} attribute-bearing records"
        + (f", {recovered} confirmed by re-read after a reported failure" if recovered else "")
        + (f"; ⚠️ LOST filament_attributes on filament(s) {lost_ids} — recovery payload in "
           f"hub.log and {snap_path}" if restore_failures else "")
        + ").",
        "INFO" if not restore_failures else "ERROR",
        "00ccff" if not restore_failures else "ff4444",
    )
    return jsonify({
        "success": not restore_failures,
        "removed": unused,
        "restored": restored,
        "recovered": recovered,
        "restore_failures": restore_failures,
        "lost_ids": lost_ids,
        "recovery_snapshot": snap_path if restore_failures else None,
        "msg": (f"Swept {len(unused)} choice(s), but {len(restore_failures)} filament(s) "
                f"{lost_ids} could not be restored and have LOST their attributes. "
                f"Recovery data: {snap_path}" if restore_failures else ""),
    })
