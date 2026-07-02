"""L316 characterization tests — pins pre-carve behavior of the filament-edit
formatting + rejection paths (app.py 2296-2825). Generated from the 2026-07-01
coverage audit. Do not weaken these to make a refactor pass.

Three surfaces, all host-runnable (no live server / Spoolman — every outbound
call is mocked):

1. `_format_filament_edit_log` by DIRECT call — the audit-trail line the
   Activity Log shows for every filament edit: native vs extra keys, the
   Group-23.4 delete-sentinel rendering as '(cleared)', unchanged-value
   rendering, the empty-set symbol for blanks, list join, 60-char truncation,
   sorted-key ordering, and the non-dict-`before` tolerance.

2. POST /api/update_filament rejection + exception branches — the
   LAST_SPOOLMAN_ERROR surfacing contract mandated by the 2026-04-27 outage
   postmortem, and the generic-Exception shape.

3. `_handle_prusament_url_scan` failure sub-branches by DIRECT call —
   SpoolmanRejection from the temps write, spool-extras write failure
   (update_spool -> None), and the Group-23.6 idempotent product_url-upgrade
   skip. (test_prusament_scan.py already covers the matcher happy paths —
   deliberately NOT duplicated here.)
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from unittest.mock import patch  # noqa: E402

import pytest  # noqa: E402

import app as app_module  # noqa: E402
import spoolman_api  # noqa: E402

SENTINEL = spoolman_api.DELETE_EXTRA_SENTINEL


@pytest.fixture
def client():
    app_module.app.config["TESTING"] = True
    return app_module.app.test_client()


# ---------------------------------------------------------------------------
# 1. _format_filament_edit_log — direct-call pins.
# The exact strings matter: this line IS the user's audit trail (Derek asked
# for real before→after values, not a bare key list).
# ---------------------------------------------------------------------------


def test_edit_log_native_change_renders_old_arrow_new():
    """A changed native field renders 'key: old → new' with the standard
    '✏️ Filament #N edited — ' prefix. Pins the full line verbatim."""
    msg = app_module._format_filament_edit_log(5, {"name": "Old"}, {"name": "New"})
    assert msg == "✏️ Filament #5 edited — name: Old → New"


def test_edit_log_unchanged_native_value_renders_unchanged_marker():
    """An equal requested value still emits an entry — rendered '(unchanged)'
    — because the user explicitly asked for no-op PATCHes to tell the story."""
    msg = app_module._format_filament_edit_log(5, {"name": "Same"}, {"name": "Same"})
    assert msg == "✏️ Filament #5 edited — name: Same (unchanged)"


def test_edit_log_extra_change_and_unchanged_render_with_extra_prefix():
    """Extras render as 'extra.<key>' — changed gets the arrow, equal gets
    '(unchanged)' — and extra keys are emitted in sorted order."""
    before = {"extra": {"sheet_link": "https://a", "slicer_profile": "PLA"}}
    requested = {"extra": {"slicer_profile": "PLA", "sheet_link": "https://b"}}
    msg = app_module._format_filament_edit_log(7, before, requested)
    assert msg == (
        "✏️ Filament #7 edited — "
        "extra.sheet_link: https://a → https://b · "
        "extra.slicer_profile: PLA (unchanged)"
    )


def test_edit_log_delete_sentinel_renders_cleared_and_never_leaks_token():
    """Group 23.4 — an extra sent as DELETE_EXTRA_SENTINEL renders as a real
    deletion 'old → (cleared)'; the internal token must never appear in the
    Activity Log line."""
    before = {"extra": {"sheet_link": "https://old.example"}}
    requested = {"extra": {"sheet_link": SENTINEL}}
    msg = app_module._format_filament_edit_log(7, before, requested)
    assert msg == (
        "✏️ Filament #7 edited — "
        "extra.sheet_link: https://old.example → (cleared)"
    )
    assert SENTINEL not in msg


def test_edit_log_quote_wrapped_delete_sentinel_also_renders_cleared():
    """The sentinel check is quote-strip tolerant (_is_delete_sentinel) so a
    sanitize_outbound_data-wrapped sentinel still renders '(cleared)'."""
    before = {"extra": {"sheet_link": "https://old.example"}}
    requested = {"extra": {"sheet_link": '"' + SENTINEL + '"'}}
    msg = app_module._format_filament_edit_log(7, before, requested)
    assert "(cleared)" in msg
    assert SENTINEL not in msg


def test_edit_log_blank_values_render_empty_set_symbol():
    """None and '' both render as the empty-set symbol — yet None != '' so the
    entry still renders as a CHANGE (arrow), not '(unchanged)'."""
    msg = app_module._format_filament_edit_log(5, {"name": None}, {"name": ""})
    assert msg == "✏️ Filament #5 edited — name: ∅ → ∅"


def test_edit_log_list_value_renders_bracketed_join():
    """List values render as '[a, b]' (comma-space join inside brackets)."""
    msg = app_module._format_filament_edit_log(5, {}, {"tags": ["a", "b"]})
    assert msg == "✏️ Filament #5 edited — tags: ∅ → [a, b]"


def test_edit_log_long_value_truncated_to_57_chars_plus_ellipsis():
    """Values over 60 chars are cut to the first 57 chars + a single-char
    ellipsis; exactly-60-char values pass through whole (boundary pin)."""
    long_val = "x" * 70
    msg = app_module._format_filament_edit_log(5, {}, {"comment": long_val})
    assert msg == (
        "✏️ Filament #5 edited — comment: ∅ → "
        + "x" * 57 + "…"
    )
    exact_60 = "y" * 60
    msg60 = app_module._format_filament_edit_log(5, {}, {"comment": exact_60})
    assert msg60.endswith("→ " + exact_60)
    assert "…" not in msg60


def test_edit_log_empty_payload_renders_no_fields_fallback():
    """An empty requested payload renders the '(no fields)' fallback line."""
    msg = app_module._format_filament_edit_log(5, {"name": "Old"}, {})
    assert msg == "✏️ Filament #5 edited (no fields)"


def test_edit_log_non_dict_before_does_not_raise():
    """before=None (get_filament failed / returned nothing) must not crash —
    every old value renders as the empty-set symbol. A crash here would turn
    a COMMITTED Spoolman write into a success:false response."""
    msg = app_module._format_filament_edit_log(9, None, {"name": "X", "extra": {"k": "v"}})
    assert msg == (
        "✏️ Filament #9 edited — "
        "extra.k: ∅ → v · name: ∅ → X"
    )


def test_edit_log_multi_key_ordering_sorts_keys_with_extra_block_inline():
    """Top-level keys are emitted in sorted order and the 'extra' block sits
    inline at its own sorted position ('comment' < 'extra' < 'name'), parts
    joined by ' · '. Pins the whole assembled line."""
    before = {"name": "Old", "comment": "hi", "extra": {"a": "0"}}
    requested = {"name": "New", "extra": {"b": "2", "a": "1"}, "comment": "hi"}
    msg = app_module._format_filament_edit_log(5, before, requested)
    assert msg == (
        "✏️ Filament #5 edited — "
        "comment: hi (unchanged) · "
        "extra.a: 0 → 1 · "
        "extra.b: ∅ → 2 · "
        "name: Old → New"
    )


# ---------------------------------------------------------------------------
# 2. POST /api/update_filament — rejection + exception branches.
# ---------------------------------------------------------------------------


def test_update_filament_rejection_surfaces_last_spoolman_error(client):
    """update_filament returning None must surface the stashed Spoolman error
    body in msg ('Spoolman rejected update: <body>') — the 2026-04-27
    error-surfacing convention — with success:false, HTTP 200, and NO
    Activity-Log entry (the log line is success-path only)."""
    with patch("spoolman_api.get_filament", return_value={"id": 5, "name": "Old"}), \
         patch("spoolman_api.update_filament", return_value=None), \
         patch.object(app_module.spoolman_api, "LAST_SPOOLMAN_ERROR",
                      "HTTP 400: bad vendor_id"), \
         patch.object(app_module.state, "add_log_entry") as log:
        r = client.post("/api/update_filament", json={"id": 5, "data": {"name": "X"}})
    assert r.status_code == 200
    body = r.get_json()
    assert body["success"] is False
    assert body["msg"] == "Spoolman rejected update: HTTP 400: bad vendor_id"
    log.assert_not_called()


def test_update_filament_rejection_falls_back_to_no_response_body(client):
    """When LAST_SPOOLMAN_ERROR is None (rejection with no stashed body) the
    msg falls back to the literal 'No response body'."""
    with patch("spoolman_api.get_filament", return_value={"id": 5}), \
         patch("spoolman_api.update_filament", return_value=None), \
         patch.object(app_module.spoolman_api, "LAST_SPOOLMAN_ERROR", None):
        r = client.post("/api/update_filament", json={"id": 5, "data": {"name": "X"}})
    body = r.get_json()
    assert body["success"] is False
    assert body["msg"] == "Spoolman rejected update: No response body"


def test_update_filament_generic_exception_returns_200_with_str(client):
    """A raising update_filament is caught: success:false with msg == str(e),
    state.logger.error fired naming the filament id.
    # NOTE: pins current behavior; see suspected_bugs — the generic-Exception
    # branch returns HTTP 200 (not a 500) with the raw exception text."""
    with patch("spoolman_api.get_filament", return_value={"id": 5}), \
         patch("spoolman_api.update_filament", side_effect=RuntimeError("boom")), \
         patch.object(app_module.state.logger, "error") as logerr:
        r = client.post("/api/update_filament", json={"id": 5, "data": {"name": "X"}})
    assert r.status_code == 200
    body = r.get_json()
    assert body == {"success": False, "msg": "boom"}
    logerr.assert_called_once()
    assert "Failed to update filament #5" in logerr.call_args[0][0]


def test_update_filament_success_logs_formatted_edit_line(client):
    """Success glue: the route snapshots the record BEFORE the update and logs
    the _format_filament_edit_log line at SUCCESS/00ff00, returning the
    updated record verbatim."""
    with patch("spoolman_api.get_filament",
               return_value={"id": 5, "name": "Old", "extra": {}}), \
         patch("spoolman_api.update_filament",
               return_value={"id": 5, "name": "New"}), \
         patch.object(app_module.state, "add_log_entry") as log:
        r = client.post("/api/update_filament", json={"id": 5, "data": {"name": "New"}})
    body = r.get_json()
    assert body["success"] is True
    assert body["filament"] == {"id": 5, "name": "New"}
    log.assert_called_once_with(
        "✏️ Filament #5 edited — name: Old → New",
        "SUCCESS", "00ff00",
    )


def test_update_filament_committed_write_with_raising_logger_reports_failure(client):
    """If add_log_entry raises AFTER a successful Spoolman write, the except
    swallows it and the response says success:false even though the write
    COMMITTED — the user retries and double-writes.
    # NOTE: pins current behavior; see suspected_bugs."""
    with patch("spoolman_api.get_filament", return_value={"id": 5, "name": "Old"}), \
         patch("spoolman_api.update_filament", return_value={"id": 5, "name": "New"}), \
         patch.object(app_module.state, "add_log_entry",
                      side_effect=RuntimeError("log boom")), \
         patch.object(app_module.state.logger, "error") as logerr:
        r = client.post("/api/update_filament", json={"id": 5, "data": {"name": "New"}})
    body = r.get_json()
    assert body == {"success": False, "msg": "log boom"}
    logerr.assert_called_once()


# ---------------------------------------------------------------------------
# 3. _handle_prusament_url_scan — failure sub-branches by DIRECT call.
# The matcher happy paths live in test_prusament_scan.py; these pin only the
# write-failure handling and the product_url-upgrade idempotence.
# ---------------------------------------------------------------------------

_URL = "https://prusament.com/spool/17705/5b1a183b26/"
_HASH = "5b1a183b26"
# The canonical form the 23.6 upgrade writes: NO trailing slash, lowercase hash.
_CANONICAL = f"https://prusament.com/spool/17705/{_HASH}"


def _parsed_obj(**over):
    """A standard_obj as PrusamentParser.search would return it (no weight
    fields, so the L200 spool_weight diff computes to None here)."""
    obj = {
        "name": "Prusament PLA Galaxy Black",
        "material": "PLA",
        "vendor": {"name": "Prusament"},
        "settings_extruder_temp": 215,
        "settings_bed_temp": 60,
        "extra": {
            "nozzle_temp_max": "230",
            "bed_temp_max": "65",
            "prusament_manufacturing_date": "2026-01-02",
            "prusament_length_m": "330",
        },
    }
    obj.update(over)
    return obj


# A filament whose temps already MATCH the parsed page, so the temp-backfill
# write and the differ-suggest gate both stay quiet — isolating the spool-extras
# write branches under test.
_FIL_SYNCED = {
    "id": 7, "name": "Prusament PLA",
    "settings_extruder_temp": 215, "settings_bed_temp": 60,
    "extra": {"nozzle_temp_max": "230", "bed_temp_max": "65"},
}


def _direct_scan():
    """Call the helper directly (it jsonify()s, so it needs a request ctx)."""
    res = {"type": "prusament_url", "url": _URL,
           "spool_id": "17705", "spool_hash": _HASH}
    with app_module.app.test_request_context():
        return app_module._handle_prusament_url_scan(res).get_json()


def test_prusament_temps_write_rejection_returns_error_payload_and_skips_spool_write():
    """SpoolmanRejection from the temps backfill (update_filament_or_raise)
    early-returns a {type:'prusament_matched', status:'error', msg} payload,
    logs ERROR/ff4444 naming the filament + body, and never reaches the
    spool-extras / product_url-upgrade write."""
    matched = {"id": 42, "extra": {"product_url": _URL}, "filament": {"id": 7}}
    blank_fil = {"id": 7, "name": "Prusament PLA", "settings_extruder_temp": None,
                 "settings_bed_temp": None, "extra": {}}
    with patch("external_parsers.search_external", return_value=[_parsed_obj()]), \
         patch("spoolman_api.get_all_spools", return_value=[matched]), \
         patch("spoolman_api.get_filament", return_value=blank_fil), \
         patch("spoolman_api.update_filament_or_raise",
               side_effect=spoolman_api.SpoolmanRejection("HTTP 400: nope")), \
         patch("spoolman_api.update_spool") as upd_spool, \
         patch.object(app_module.state, "add_log_entry") as log:
        res = _direct_scan()
    assert res == {
        "type": "prusament_matched", "status": "error",
        "spool_id": 42, "filament_id": 7, "msg": "HTTP 400: nope",
    }
    upd_spool.assert_not_called()
    log.assert_called_once()
    msg, level, color = log.call_args[0]
    assert "Prusament temp backfill failed for filament #7" in msg
    assert "HTTP 400: nope" in msg
    assert (level, color) == ("ERROR", "ff4444")


def test_prusament_spool_extras_write_failure_warns_with_spoolman_body():
    """update_spool returning None on the metadata/product_url refresh logs a
    WARNING/ffaa00 naming the spool + LAST_SPOOLMAN_ERROR body while the
    response STAYS status:'ok' (best-effort write, matched flow continues).
    Also pins the 23.6 upgrade payload: the query-form stored URL is sent back
    as the canonical /spool/<id>/<hash> form alongside the blank-metadata
    backfill, and the 'Saved the scanned Prusament link' INFO line is NOT
    emitted when the write failed."""
    matched = {"id": 71,
               "extra": {"product_url": f"https://prusament.com/spool/?spoolId={_HASH}"},
               "filament": {"id": 7}}
    with patch("external_parsers.search_external", return_value=[_parsed_obj()]), \
         patch("spoolman_api.get_all_spools", return_value=[matched]), \
         patch("spoolman_api.get_filament", return_value=_FIL_SYNCED), \
         patch("spoolman_api.get_spools_for_filament", return_value=[]), \
         patch("spoolman_api.update_filament_or_raise") as upd_fil, \
         patch("spoolman_api.update_spool", return_value=None) as upd_spool, \
         patch.object(app_module.spoolman_api, "LAST_SPOOLMAN_ERROR",
                      "HTTP 400: Unknown extra field"), \
         patch.object(app_module.state, "add_log_entry") as log:
        res = _direct_scan()
    assert res["type"] == "prusament_matched"
    assert res["status"] == "ok"          # best-effort: failure does not error the scan
    assert res["filled"] == []            # temps already matched -> no filament write
    upd_fil.assert_not_called()
    upd_spool.assert_called_once()
    sid, payload = upd_spool.call_args[0]
    assert sid == 71
    assert payload == {"extra": {
        "prusament_manufacturing_date": "2026-01-02",
        "prusament_length_m": "330",
        "product_url": _CANONICAL,
    }}
    log.assert_called_once()
    msg, level, color = log.call_args[0]
    assert msg.endswith(
        "Couldn't refresh Prusament metadata on spool #71: HTTP 400: Unknown extra field"
    )
    assert (level, color) == ("WARNING", "ffaa00")
    assert "Saved the scanned Prusament link" not in msg


def test_prusament_product_url_upgrade_skips_when_already_canonical():
    """Idempotence pin (23.6): a stored product_url already in the canonical
    form (compared quote-strip tolerant via _pm_norm) plus already-present
    Prusament metadata means pm_fill stays empty — update_spool is never
    called, no log entry fires, and the scan still reports status:'ok' with
    spool_weight None (no weight data in the parsed page)."""
    matched = {"id": 42,
               "extra": {"product_url": '"' + _CANONICAL + '"',
                         "prusament_manufacturing_date": "2026-01-02",
                         "prusament_length_m": "330"},
               "filament": {"id": 7}}
    with patch("external_parsers.search_external", return_value=[_parsed_obj()]), \
         patch("spoolman_api.get_all_spools", return_value=[matched]), \
         patch("spoolman_api.get_filament", return_value=_FIL_SYNCED), \
         patch("spoolman_api.get_spools_for_filament", return_value=[]), \
         patch("spoolman_api.update_filament_or_raise") as upd_fil, \
         patch("spoolman_api.update_spool") as upd_spool, \
         patch.object(app_module.state, "add_log_entry") as log:
        res = _direct_scan()
    assert res["type"] == "prusament_matched"
    assert res["status"] == "ok"
    assert res["spool_id"] == 42
    assert res["filled"] == []
    assert res["conflicts"] == []
    assert res["spool_weight"] is None
    upd_fil.assert_not_called()
    upd_spool.assert_not_called()
    log.assert_not_called()
