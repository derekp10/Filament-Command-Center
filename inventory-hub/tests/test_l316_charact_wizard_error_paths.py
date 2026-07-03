"""L316 characterization tests — pins pre-carve behavior of the wizard/vendor/CRUD
write-surface error paths (app.py 546-1364). Generated from the 2026-07-01
coverage audit. Do not weaken these to make a refactor pass.

Surfaces pinned (all host-runnable, no live server / no live Spoolman):
  - POST /api/edit_spool_wizard   — update_spool/update_filament rejection
    branches (LAST_SPOOLMAN_ERROR surfacing), the compute_dirty_extras +
    SYSTEM_MANAGED_EXTRAS guard, and the get_spool-None raw-forward fallthrough.
  - POST /api/create_filament     — success log + Spoolman-rejection 500.
  - PATCH /api/vendors/<vid>      — success (delegation + _format_vendor_edit_log
    activity line), SpoolmanRejection -> 400 with error body, generic 500.
  - POST /api/external/fields/add_choice — delegation + verbatim passthrough.
  - GET  /api/external/search     — {success, source, results} envelope,
    ValueError vs generic-Exception mapping, default source.
  - GET  /api/filaments           — deliberate raw-proxy quirk (extras returned
    JSON-double-encoded, no parse_inbound_data).

Every outbound call is mocked via monkeypatch on app_module.spoolman_api /
app_module.external_parsers / app_module.requests — the point of this file is
a fast offline safety net for the pure-move modularization.
"""
from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import app as app_module  # noqa: E402


# --- shared helpers ---------------------------------------------------------


def _client():
    return app_module.app.test_client()


def _capture_logs(monkeypatch):
    """Capture every state.add_log_entry call as (msg, args, kwargs)."""
    calls = []
    monkeypatch.setattr(
        app_module.state, "add_log_entry",
        lambda msg, *a, **k: calls.append((msg, a, k)),
    )
    return calls


class _FakeResp:
    """Minimal stand-in for a requests.Response (only .ok / .json used here)."""

    def __init__(self, ok, payload=None):
        self.ok = ok
        self._payload = payload

    def json(self):
        return self._payload


# ============================================================================
# POST /api/edit_spool_wizard — rejection / guard branches
# ============================================================================


def test_wizard_update_spool_rejection_surfaces_spoolman_error(monkeypatch):
    """update_spool -> None surfaces LAST_SPOOLMAN_ERROR verbatim in BOTH the
    msg ('Failed to update Spool <id>: <body>') and the `error` key, and no
    24.F weight-breakdown log line fires for the failed write."""
    pre = {"id": 42, "archived": False, "initial_weight": 1000,
           "used_weight": 200, "remaining_weight": 800}
    monkeypatch.setattr(app_module.spoolman_api, "get_spool", lambda sid: pre)
    monkeypatch.setattr(app_module.spoolman_api, "update_spool", lambda sid, data: None)
    monkeypatch.setattr(app_module.spoolman_api, "LAST_SPOOLMAN_ERROR",
                        "HTTP 400: Unknown extra field", raising=False)
    calls = _capture_logs(monkeypatch)

    r = _client().post("/api/edit_spool_wizard", json={
        "spool_id": 42,
        "spool_data": {"used_weight": 550},
    })
    body = r.get_json()
    assert body["success"] is False
    assert body["msg"] == "Failed to update Spool 42: HTTP 400: Unknown extra field"
    assert body["error"] == "HTTP 400: Unknown extra field"
    assert [c for c in calls if "Weight updated" in c[0]] == []


def test_wizard_update_spool_rejection_fallback_message(monkeypatch):
    """When LAST_SPOOLMAN_ERROR is unset (None) the rejection branch falls back
    to the generic 'Spoolman rejected the update' text in msg AND error."""
    pre = {"id": 42, "archived": False, "used_weight": 200}
    monkeypatch.setattr(app_module.spoolman_api, "get_spool", lambda sid: pre)
    monkeypatch.setattr(app_module.spoolman_api, "update_spool", lambda sid, data: None)
    monkeypatch.setattr(app_module.spoolman_api, "LAST_SPOOLMAN_ERROR", None, raising=False)
    _capture_logs(monkeypatch)

    r = _client().post("/api/edit_spool_wizard", json={
        "spool_id": 42,
        "spool_data": {"used_weight": 550},
    })
    body = r.get_json()
    assert body["success"] is False
    assert body["msg"] == "Failed to update Spool 42: Spoolman rejected the update"
    assert body["error"] == "Spoolman rejected the update"


def test_wizard_update_filament_rejection_surfaces_spoolman_error(monkeypatch):
    """update_filament -> None returns the filament-flavored rejection
    ('Filament update rejected: <LAST_SPOOLMAN_ERROR>') with the error key."""
    monkeypatch.setattr(app_module.spoolman_api, "update_filament", lambda fid, data: None)
    monkeypatch.setattr(app_module.spoolman_api, "LAST_SPOOLMAN_ERROR",
                        "HTTP 422: bad density", raising=False)
    _capture_logs(monkeypatch)

    r = _client().post("/api/edit_spool_wizard", json={
        "spool_id": 77,
        "filament_id": 5,
        "filament_data": {"name": "X"},
        # no spool_data -> spool branch skipped entirely
    })
    body = r.get_json()
    assert body["success"] is False
    assert body["msg"] == "Filament update rejected: HTTP 422: bad density"
    assert body["error"] == "HTTP 422: bad density"


def test_wizard_spool_committed_before_filament_rejection(monkeypatch):
    """Spool is written FIRST; a subsequent filament rejection still returns
    success:False even though the spool change already persisted.
    # NOTE: pins current behavior; see suspected_bugs (partial-write reported
    # as overall failure, response carries no hint the spool part landed)."""
    pre = {"id": 77, "archived": False, "initial_weight": 1000,
           "used_weight": 200, "remaining_weight": 800}
    post = {"id": 77, "archived": False, "initial_weight": 1000,
            "used_weight": 550, "remaining_weight": 450}
    spool_writes = []
    monkeypatch.setattr(app_module.spoolman_api, "get_spool", lambda sid: pre)
    monkeypatch.setattr(
        app_module.spoolman_api, "update_spool",
        lambda sid, data: (spool_writes.append((sid, data)), post)[1])
    monkeypatch.setattr(app_module.spoolman_api, "update_filament", lambda fid, data: None)
    monkeypatch.setattr(app_module.spoolman_api, "LAST_SPOOLMAN_ERROR",
                        "HTTP 422: nope", raising=False)
    _capture_logs(monkeypatch)

    r = _client().post("/api/edit_spool_wizard", json={
        "spool_id": 77,
        "spool_data": {"used_weight": 550},
        "filament_id": 5,
        "filament_data": {"name": "X"},
    })
    body = r.get_json()
    assert len(spool_writes) == 1, "spool write must have been attempted before the filament save"
    assert spool_writes[0][0] == 77
    assert body["success"] is False
    assert body["msg"] == "Filament update rejected: HTTP 422: nope"


def test_wizard_extras_diff_uses_system_managed_guard(monkeypatch):
    """The extras diff funnels through spoolman_api.compute_dirty_extras with
    system_managed=SYSTEM_MANAGED_EXTRAS (the Item-4 fix): a system-managed key
    the JS sends (container_slot) is STRIPPED from the update payload and a
    warning is logged, while a legitimately-dirty sibling extra goes through."""
    original = {"id": 42, "archived": False,
                "extra": {"container_slot": '"XL-1"', "purchase_url": '"old"'}}
    diff_calls = []
    real_diff = app_module.spoolman_api.compute_dirty_extras

    def spy_diff(existing, requested, **kw):
        diff_calls.append((existing, requested, kw))
        return real_diff(existing, requested, **kw)

    sent = {}
    monkeypatch.setattr(app_module.spoolman_api, "get_spool", lambda sid: original)
    monkeypatch.setattr(app_module.spoolman_api, "compute_dirty_extras", spy_diff)
    monkeypatch.setattr(
        app_module.spoolman_api, "update_spool",
        lambda sid, data: sent.update({"sid": sid, "data": data}) or {"id": sid})
    fake_logger = MagicMock()
    monkeypatch.setattr(app_module.state, "logger", fake_logger)
    _capture_logs(monkeypatch)

    r = _client().post("/api/edit_spool_wizard", json={
        "spool_id": 42,
        "spool_data": {"extra": {"container_slot": "XL-9", "purchase_url": "new"}},
    })
    assert r.get_json()["success"] is True
    # The guard frozenset is passed by keyword — the enforcement seam.
    assert len(diff_calls) == 1
    assert diff_calls[0][2] == {
        "system_managed": app_module.spoolman_api.SYSTEM_MANAGED_EXTRAS}
    # Only the non-system-managed dirty extra reaches update_spool.
    assert sent["data"] == {"extra": {"purchase_url": "new"}}
    warn_msgs = [str(c.args[0]) for c in fake_logger.warning.call_args_list]
    assert any("refused to write system-managed extras" in m for m in warn_msgs)


def test_wizard_get_spool_none_forwards_raw_payload(monkeypatch):
    """When the pre-fetch blips (get_spool -> None) the handler SKIPS the
    dirty-diff AND the system-managed strip and forwards the raw request
    payload — including container_slot — straight to update_spool.
    # NOTE: pins current behavior; see suspected_bugs (a Spoolman blip
    # reopens the Item-4 slot-clobber window)."""
    sent = {}
    monkeypatch.setattr(app_module.spoolman_api, "get_spool", lambda sid: None)
    monkeypatch.setattr(
        app_module.spoolman_api, "update_spool",
        lambda sid, data: sent.update({"sid": sid, "data": data}) or {"id": sid})
    _capture_logs(monkeypatch)

    payload = {"used_weight": 550,
               "extra": {"container_slot": "XL-9", "purchase_url": "x"}}
    r = _client().post("/api/edit_spool_wizard", json={
        "spool_id": 42,
        "spool_data": payload,
    })
    assert r.get_json()["success"] is True
    assert sent["sid"] == 42
    assert sent["data"] == payload  # verbatim, system-managed key included


def test_wizard_no_dirty_changes_skips_update_spool(monkeypatch):
    """An edit whose fields all equal the current spool produces an empty dirty
    diff — update_spool is never called and the response is still success."""
    original = {"id": 42, "archived": False, "comment": "same", "used_weight": 200}

    def _boom(sid, data):
        raise AssertionError("update_spool must not be called for a no-op edit")

    monkeypatch.setattr(app_module.spoolman_api, "get_spool", lambda sid: original)
    monkeypatch.setattr(app_module.spoolman_api, "update_spool", _boom)
    _capture_logs(monkeypatch)

    r = _client().post("/api/edit_spool_wizard", json={
        "spool_id": 42,
        "spool_data": {"comment": "same"},
    })
    body = r.get_json()
    assert body == {"success": True, "spool_id": 42}


# ============================================================================
# POST /api/create_filament
# ============================================================================


def test_create_filament_success_logs_and_returns_filament(monkeypatch):
    """Happy path: create_filament result echoed under `filament`, and a
    SUCCESS/00ff00 Activity-Log entry names the new id + material + name."""
    created = {"id": 7, "material": "PLA", "name": "X"}
    seen = {}
    monkeypatch.setattr(
        app_module.spoolman_api, "create_filament",
        lambda data: seen.update({"data": data}) or created)
    calls = _capture_logs(monkeypatch)

    r = _client().post("/api/create_filament",
                       json={"data": {"material": "PLA", "name": "X"}})
    body = r.get_json()
    assert r.status_code == 200
    assert body["success"] is True
    assert body["filament"] == created
    assert seen["data"] == {"material": "PLA", "name": "X"}
    assert len(calls) == 1
    msg, args, _ = calls[0]
    assert "Filament #7 created (PLA: X)" in msg
    assert args == ("SUCCESS", "00ff00")


def test_create_filament_rejection_returns_500_generic_msg(monkeypatch):
    """create_filament -> None maps to HTTP 500 with the fixed generic msg.
    # NOTE: pins current behavior; see suspected_bugs — unlike its sibling
    # api_create_vendor, this branch does NOT surface LAST_SPOOLMAN_ERROR."""
    monkeypatch.setattr(app_module.spoolman_api, "create_filament", lambda data: None)
    monkeypatch.setattr(app_module.spoolman_api, "LAST_SPOOLMAN_ERROR",
                        "HTTP 400: vendor_id unknown", raising=False)
    calls = _capture_logs(monkeypatch)

    r = _client().post("/api/create_filament",
                       json={"data": {"material": "PLA", "name": "X"}})
    body = r.get_json()
    assert r.status_code == 500
    assert body["success"] is False
    assert body["msg"] == "Spoolman rejected the filament create."
    assert "HTTP 400" not in body["msg"]  # the Spoolman body is NOT surfaced today
    assert calls == []  # no SUCCESS log on rejection


def test_create_filament_exception_returns_500_with_str(monkeypatch):
    """An exception inside the create maps to HTTP 500 with msg == str(e)."""
    def _boom(data):
        raise RuntimeError("kaput")

    monkeypatch.setattr(app_module.spoolman_api, "create_filament", _boom)
    _capture_logs(monkeypatch)

    r = _client().post("/api/create_filament",
                       json={"data": {"material": "PLA"}})
    assert r.status_code == 500
    body = r.get_json()
    assert body == {"success": False, "msg": "kaput"}


# ============================================================================
# PATCH /api/vendors/<vid>
# ============================================================================


def test_update_vendor_success_forwards_data_and_logs_diff(monkeypatch):
    """Happy path: the route forwards `data` VERBATIM to update_vendor_or_raise
    (the extra-merge lives inside spoolman_api.update_vendor, not the route),
    returns {success, vendor}, and writes the _format_vendor_edit_log
    before->after line at SUCCESS/00ff00."""
    before = {"id": 5, "name": "Old", "extra": {"website": "a"}}
    updated = {"id": 5, "name": "New", "extra": {"website": "b"}}
    seen = {}
    monkeypatch.setattr(app_module.spoolman_api, "get_vendor", lambda vid: before)
    monkeypatch.setattr(
        app_module.spoolman_api, "update_vendor_or_raise",
        lambda vid, data: seen.update({"vid": vid, "data": data}) or updated)
    calls = _capture_logs(monkeypatch)

    payload = {"name": "New", "extra": {"website": "b"}}
    r = _client().patch("/api/vendors/5", json={"data": payload})
    body = r.get_json()
    assert r.status_code == 200
    assert body == {"success": True, "vendor": updated}
    assert seen["vid"] == 5
    assert seen["data"] == payload  # verbatim — no route-level merge
    assert len(calls) == 1
    msg, args, _ = calls[0]
    assert "Vendor #5 edited" in msg
    assert "name: Old → New" in msg
    assert "extra.website: a → b" in msg
    assert args == ("SUCCESS", "00ff00")


def test_update_vendor_delete_sentinel_renders_cleared(monkeypatch):
    """Group 23.4 contract: an extra sent as DELETE_EXTRA_SENTINEL renders as
    '→ (cleared)' in the activity line and the raw token never leaks."""
    before = {"id": 5, "name": "Old", "extra": {"website": "a"}}
    monkeypatch.setattr(app_module.spoolman_api, "get_vendor", lambda vid: before)
    monkeypatch.setattr(app_module.spoolman_api, "update_vendor_or_raise",
                        lambda vid, data: {"id": 5, "name": "Old"})
    calls = _capture_logs(monkeypatch)

    sentinel = app_module.spoolman_api.DELETE_EXTRA_SENTINEL
    r = _client().patch("/api/vendors/5",
                        json={"data": {"extra": {"website": sentinel}}})
    assert r.get_json()["success"] is True
    assert len(calls) == 1
    msg = calls[0][0]
    assert "extra.website: a → (cleared)" in msg
    assert sentinel not in msg


def test_update_vendor_rejection_maps_to_400_with_error_body(monkeypatch):
    """SpoolmanRejection -> HTTP 400 with the rejection body verbatim in msg
    (the modal's 7s-toast source) plus an ERROR/ff4444 activity entry naming
    the vendor id."""
    monkeypatch.setattr(app_module.spoolman_api, "get_vendor", lambda vid: {"id": 5, "name": "Old"})

    def _reject(vid, data):
        raise app_module.spoolman_api.SpoolmanRejection("HTTP 400: name must be unique")

    monkeypatch.setattr(app_module.spoolman_api, "update_vendor_or_raise", _reject)
    calls = _capture_logs(monkeypatch)

    r = _client().patch("/api/vendors/5", json={"data": {"name": "Dup"}})
    body = r.get_json()
    assert r.status_code == 400
    assert body == {"success": False, "msg": "HTTP 400: name must be unique"}
    assert len(calls) == 1
    msg, args, _ = calls[0]
    assert "Vendor #5 edit rejected" in msg
    assert "HTTP 400: name must be unique" in msg
    assert args == ("ERROR", "ff4444")


def test_update_vendor_generic_exception_maps_to_500(monkeypatch):
    """A non-SpoolmanRejection exception maps to HTTP 500 with msg == str(e)
    and does NOT write an activity-log entry (only logger.error)."""
    monkeypatch.setattr(app_module.spoolman_api, "get_vendor", lambda vid: {"id": 5})

    def _boom(vid, data):
        raise RuntimeError("kaput")

    monkeypatch.setattr(app_module.spoolman_api, "update_vendor_or_raise", _boom)
    calls = _capture_logs(monkeypatch)

    r = _client().patch("/api/vendors/5", json={"data": {"name": "X"}})
    assert r.status_code == 500
    assert r.get_json() == {"success": False, "msg": "kaput"}
    assert calls == []


# ============================================================================
# POST /api/external/fields/add_choice
# ============================================================================


def test_add_choice_delegates_and_passes_result_through(monkeypatch):
    """The route wraps the single new_choice in a LIST for
    update_extra_field_choices and returns the delegate's result dict
    verbatim (extra keys included)."""
    seen = {}
    result = {"success": True, "msg": "Choices updated", "extra_key": 123}
    monkeypatch.setattr(
        app_module.spoolman_api, "update_extra_field_choices",
        lambda entity_type, key, new_choices: seen.update(
            {"args": (entity_type, key, new_choices)}) or result)

    r = _client().post("/api/external/fields/add_choice", json={
        "entity_type": "filament",
        "key": "filament_attributes",
        "new_choice": "Silk",
    })
    assert r.status_code == 200
    assert seen["args"] == ("filament", "filament_attributes", ["Silk"])
    assert r.get_json() == result


def test_add_choice_missing_field_returns_200_success_false(monkeypatch):
    """Missing new_choice: validation failure returns HTTP 200 (not 400) with
    the fixed msg, and the schema-write delegate is never called.
    # NOTE: pins current behavior; see suspected_bugs (200-not-400 quirk)."""
    called = []
    monkeypatch.setattr(
        app_module.spoolman_api, "update_extra_field_choices",
        lambda *a: called.append(a))

    r = _client().post("/api/external/fields/add_choice", json={
        "entity_type": "filament",
        "key": "filament_attributes",
    })
    assert r.status_code == 200
    assert r.get_json() == {"success": False, "msg": "Missing required fields."}
    assert called == []


# ============================================================================
# GET /api/external/search
# ============================================================================


def test_external_search_envelope_and_query_strip(monkeypatch):
    """Happy path pins the {success, source, results} envelope and that the q
    param is .strip()ed before reaching external_parsers.search_external."""
    seen = {}
    results = [{"name": "Galaxy Black", "material": "PLA"}]
    monkeypatch.setattr(
        app_module.external_parsers, "search_external",
        lambda source, query: seen.update({"args": (source, query)}) or results)

    r = _client().get("/api/external/search",
                      query_string={"source": "prusament", "q": "  XYZ  "})
    assert r.status_code == 200
    assert seen["args"] == ("prusament", "XYZ")
    assert r.get_json() == {"success": True, "source": "prusament", "results": results}


def test_external_search_default_source_is_spoolman(monkeypatch):
    """Absent source param defaults to 'spoolman' — both in the delegate call
    and echoed back in the envelope."""
    seen = {}
    monkeypatch.setattr(
        app_module.external_parsers, "search_external",
        lambda source, query: seen.update({"args": (source, query)}) or [])

    r = _client().get("/api/external/search", query_string={"q": "abc"})
    assert seen["args"] == ("spoolman", "abc")
    assert r.get_json() == {"success": True, "source": "spoolman", "results": []}


def test_external_search_unknown_source_valueerror_mapping(monkeypatch):
    """ValueError (unknown source) maps to HTTP 200 {success:False, msg} with
    the exception text VERBATIM (no 'An error occurred' wrapper)."""
    def _unknown(source, query):
        raise ValueError("Unknown external source: bogus")

    monkeypatch.setattr(app_module.external_parsers, "search_external", _unknown)

    r = _client().get("/api/external/search",
                      query_string={"source": "bogus", "q": "x"})
    assert r.status_code == 200
    assert r.get_json() == {"success": False, "msg": "Unknown external source: bogus"}


def test_external_search_generic_exception_mapping(monkeypatch):
    """Any non-ValueError exception maps to the wrapped
    'An error occurred pulling data: <e>' msg (still HTTP 200)."""
    def _boom(source, query):
        raise RuntimeError("upstream 503")

    monkeypatch.setattr(app_module.external_parsers, "search_external", _boom)

    r = _client().get("/api/external/search",
                      query_string={"source": "prusament", "q": "x"})
    assert r.status_code == 200
    body = r.get_json()
    assert body["success"] is False
    assert body["msg"] == "An error occurred pulling data: upstream 503"


# ============================================================================
# GET /api/filaments — deliberate raw-proxy quirk
# ============================================================================


def test_filaments_raw_proxy_preserves_double_encoded_extras(monkeypatch):
    """The proxy returns Spoolman's filament list RAW — extra values stay
    JSON-double-encoded ('"Prusa PLA"' keeps its quotes) because the route
    deliberately bypasses parse_inbound_data; the wizard JS compensates.
    A refactor that 'helpfully' routes this through spoolman_api unwrapping
    would break the wizard's quote-stripping. Also pins the upstream URL."""
    payload = [{
        "id": 1,
        "name": "Test",
        "extra": {"slicer_profile": '"Prusa PLA"', "price_total": "24.99"},
    }]
    seen = {}

    def fake_get(url, timeout=None, **kw):
        seen["url"] = url
        return _FakeResp(True, payload)

    monkeypatch.setattr(app_module.config_loader, "get_api_urls",
                        lambda: ("http://sm.test:9999", "http://fb.test/api"))
    monkeypatch.setattr(app_module.requests, "get", fake_get)

    r = _client().get("/api/filaments")
    assert r.status_code == 200
    body = r.get_json()
    assert seen["url"] == "http://sm.test:9999/api/v1/filament"
    assert body["success"] is True
    assert body["filaments"] == payload
    # The load-bearing quirk: the wrapping quotes survive byte-for-byte.
    assert body["filaments"][0]["extra"]["slicer_profile"] == '"Prusa PLA"'


def test_filaments_fetch_failure_returns_success_false_empty_list(monkeypatch):
    """Both failure modes — requests.get raising AND a non-ok response — map
    to HTTP 200 {'success': False, 'filaments': []} (no error body surfaced)."""
    monkeypatch.setattr(app_module.config_loader, "get_api_urls",
                        lambda: ("http://sm.test:9999", "http://fb.test/api"))

    def _raise(url, timeout=None, **kw):
        raise RuntimeError("connection refused")

    monkeypatch.setattr(app_module.requests, "get", _raise)
    r = _client().get("/api/filaments")
    assert r.status_code == 200
    assert r.get_json() == {"success": False, "filaments": []}

    monkeypatch.setattr(app_module.requests, "get",
                        lambda url, timeout=None, **kw: _FakeResp(False))
    r2 = _client().get("/api/filaments")
    assert r2.status_code == 200
    assert r2.get_json() == {"success": False, "filaments": []}
