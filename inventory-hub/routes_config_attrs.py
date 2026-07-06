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

import state  # type: ignore
import config_loader  # type: ignore
import config_schema  # type: ignore
import spoolman_api  # type: ignore

from app_core import app

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
    rogue_counts = {}          # 29.A1 — attrs carried by a filament but NOT in the schema
    choice_set = set(choices)
    for f in raw:
        fid = f.get("id")
        if fid is None:
            continue
        extras = f.get("extra") or {}
        attrs = spoolman_api._parse_filament_attrs_value(extras.get("filament_attributes"))
        for a in attrs:
            # 29.A1 — keep `counts` restricted to the schema choice list (the
            # live report-shape test asserts counts keys are a SUBSET of
            # choices). A rogue attribute — one a record still carries that is
            # no longer a schema choice — is surfaced explicitly in
            # `rogue_counts` instead of silently inflating `counts`.
            if a in choice_set:
                counts[a] += 1
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
        state.add_log_entry(
            f"🏷️ Filament Attributes: added choice {choice!r}", "INFO", "00ccff"
        )
    return jsonify(res)


@app.route('/api/filament_attributes/remove_choice', methods=['POST'])
def api_filament_attributes_remove_choice():
    """Remove a choice from the Spoolman filament_attributes field.

    Safety: counts usage across all filaments first. If usage > 0 and
    `force` is not truthy, refuses and returns `usage_count` so the UI
    can prompt the user.

    With `force: true`, runs the destructive schema migration in this
    order (29.A2 — docstring corrected to match the shipped implementation;
    an earlier draft claimed strip-BEFORE-delete, which is NOT what runs):
      1. snapshot every filament's FULL extras dict (raw wire form),
      2. DELETE the field from the schema,
      3. POST-recreate it without the doomed choice,
      4. restore each filament's extras with the choice filtered out of
         filament_attributes.
    Sending the WHOLE extras dict back on restore is what preserves
    siblings (Spoolman's PATCH replaces the entire `extra` sub-document).
    If the recreate POST fails the field is left MISSING and the response
    says so (re-run setup_fields.py). A per-filament restore failure is
    collected into `restore_failures` without aborting the remaining
    restores.
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
        except Exception as e:
            # 29.A4 — broadened from _req.RequestException: any OTHER exception
            # raised mid-restore (AFTER the schema was already deleted +
            # recreated) previously escaped as a bare HTTP 500 with some
            # filaments unrestored and NO restore_failures report. Catch it so
            # a partial restore stays visible in restore_failures instead of
            # surfacing as an opaque 500 over a half-migrated schema.
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
        except Exception as e:
            # 29.A4 — broadened from _req.RequestException: any OTHER exception
            # raised mid-restore (AFTER the schema was already deleted +
            # recreated) previously escaped as a bare HTTP 500 with some
            # filaments unrestored and NO restore_failures report. Catch it so
            # a partial restore stays visible in restore_failures instead of
            # surfacing as an opaque 500 over a half-migrated schema.
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

