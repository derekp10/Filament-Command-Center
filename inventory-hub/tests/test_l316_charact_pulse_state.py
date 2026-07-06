"""L316 characterization tests — pins pre-carve behavior of the persistence/pulse
micro-endpoints (app.py ~6096-6250 + ~7215-7384). Generated from the 2026-07-01
coverage audit. Do not weaken these to make a refactor pass.

Covered surfaces:
  - /api/state/buffer  GET+POST — whole-list-replace persistence of state.GLOBAL_BUFFER
  - /api/state/queue   GET+POST — whole-list-replace persistence of state.GLOBAL_QUEUE
  - /api/log_event     POST     — passthrough to state.add_log_entry (msg, level)
  - /api/spools/refresh POST    — list validation + logic.get_live_spools_data passthrough
  - /api/dashboard_pulse GET/POST — the SECTION DISPATCH contract: which
    _pulse_section_* helpers fire for which include= payloads, per-section
    error isolation, the status-derived-from-logs envelope, manage_id
    handling, and the POST-only spools_refresh section.

These are host-runnable unit tests: no live server, no live Spoolman. Every
outbound seam (state globals, state.add_log_entry, logic.get_live_spools_data,
and the four _pulse_section_* helpers) is monkeypatched. The live-server e2e
suite (tests/test_dashboard_pulse_api.py) covers the same endpoint against
real data — this file complements it with the offline dispatch wiring that a
pure-move modularization could silently break.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import app as app_module
import routes_state_pulse  # L316: patch targets for moved symbols  # noqa: E402


def _client():
    return app_module.app.test_client()


def _fail_if_called(label):
    """A stand-in for a section helper that must NOT run for this request."""
    def _boom(*a, **k):
        raise AssertionError(f"{label} should not have been called")
    return _boom


def _capture_logs(monkeypatch):
    """Record every state.add_log_entry call as (msg, args, kwargs)."""
    calls = []
    monkeypatch.setattr(
        app_module.state, "add_log_entry",
        lambda msg, *a, **k: calls.append((msg, a, k)),
    )
    return calls


def _patch_all_pulse_sections_forbidden(monkeypatch):
    """Patch all four section helpers to explode if invoked — used by tests
    that pin which sections do NOT fire."""
    monkeypatch.setattr(routes_state_pulse, "_pulse_section_logs",
                        _fail_if_called("_pulse_section_logs"))
    monkeypatch.setattr(routes_state_pulse, "_pulse_section_locations",
                        _fail_if_called("_pulse_section_locations"))
    monkeypatch.setattr(routes_state_pulse, "_pulse_section_manage",
                        _fail_if_called("_pulse_section_manage"))
    monkeypatch.setattr(routes_state_pulse, "_pulse_section_printer_status",
                        _fail_if_called("_pulse_section_printer_status"))


# ---------------------------------------------------------------------------
# /api/state/buffer — GLOBAL_BUFFER persistence round-trip
# ---------------------------------------------------------------------------

def test_state_buffer_roundtrip_post_then_get(monkeypatch):
    """POST /api/state/buffer stores the 'buffer' list verbatim into
    state.GLOBAL_BUFFER and returns {success: true}; a subsequent GET
    returns the SAME list as a bare JSON array (no envelope). This is the
    dashboard buffer-card persistence contract."""
    monkeypatch.setattr(app_module.state, "GLOBAL_BUFFER", [])
    client = _client()
    payload = [{"id": 1, "label": "PLA Red"}, {"id": 2}]

    r = client.post("/api/state/buffer", json={"buffer": payload})
    assert r.status_code == 200
    assert r.get_json() == {"success": True}
    assert app_module.state.GLOBAL_BUFFER == payload

    r2 = client.get("/api/state/buffer")
    assert r2.status_code == 200
    assert r2.get_json() == payload  # bare array, not wrapped


def test_state_buffer_post_without_key_resets_to_empty(monkeypatch):
    """POST {} (no 'buffer' key) replaces GLOBAL_BUFFER with [] — the
    missing-key-defaults-empty / whole-list-replace semantics inv_core.js
    relies on to clear the buffer."""
    monkeypatch.setattr(app_module.state, "GLOBAL_BUFFER", [{"id": 9}])
    client = _client()

    r = client.post("/api/state/buffer", json={})
    assert r.get_json() == {"success": True}
    assert app_module.state.GLOBAL_BUFFER == []
    assert client.get("/api/state/buffer").get_json() == []


def test_state_buffer_post_non_list_value_rejected_400(monkeypatch):
    """29.C1 FIX — a non-list 'buffer' value is now REJECTED with 400 (mirrors
    /api/spools/refresh) instead of stored verbatim; GLOBAL_BUFFER is left
    untouched so one malformed client write can't poison the buffer served to
    every dashboard."""
    monkeypatch.setattr(app_module.state, "GLOBAL_BUFFER", [])
    client = _client()

    r = client.post("/api/state/buffer", json={"buffer": {"not": "a list"}})
    assert r.status_code == 400
    assert r.get_json() == {"error": "buffer must be a list"}
    # Unchanged: the bad write never landed.
    assert app_module.state.GLOBAL_BUFFER == []
    assert client.get("/api/state/buffer").get_json() == []


def test_state_queue_post_non_list_value_rejected_400(monkeypatch):
    """29.C1 FIX — the queue endpoint gains the same list-validation guard as
    the buffer: a non-list 'queue' value 400s and GLOBAL_QUEUE is untouched."""
    monkeypatch.setattr(app_module.state, "GLOBAL_QUEUE", [])
    client = _client()

    r = client.post("/api/state/queue", json={"queue": {"not": "a list"}})
    assert r.status_code == 400
    assert r.get_json() == {"error": "queue must be a list"}
    assert app_module.state.GLOBAL_QUEUE == []
    assert client.get("/api/state/queue").get_json() == []


# ---------------------------------------------------------------------------
# /api/state/queue — GLOBAL_QUEUE persistence round-trip
# ---------------------------------------------------------------------------

def test_state_queue_roundtrip_post_then_get(monkeypatch):
    """POST /api/state/queue stores the 'queue' list verbatim into
    state.GLOBAL_QUEUE and GET returns it as a bare JSON array — the
    inv_queue.js print-queue persistence contract, symmetric with buffer."""
    monkeypatch.setattr(app_module.state, "GLOBAL_QUEUE", [])
    client = _client()
    payload = [{"id": 7, "type": "spool"}]

    r = client.post("/api/state/queue", json={"queue": payload})
    assert r.status_code == 200
    assert r.get_json() == {"success": True}
    assert app_module.state.GLOBAL_QUEUE == payload
    assert client.get("/api/state/queue").get_json() == payload


def test_state_queue_post_without_key_resets_to_empty(monkeypatch):
    """POST {} (no 'queue' key) resets GLOBAL_QUEUE to [] — whole-list
    replacement, no merge."""
    monkeypatch.setattr(app_module.state, "GLOBAL_QUEUE", [{"id": 3}])
    client = _client()

    r = client.post("/api/state/queue", json={})
    assert r.get_json() == {"success": True}
    assert app_module.state.GLOBAL_QUEUE == []


# ---------------------------------------------------------------------------
# /api/log_event — Activity Log write passthrough
# ---------------------------------------------------------------------------

def test_log_event_forwards_msg_and_level_positionally(monkeypatch):
    """POST /api/log_event calls state.add_log_entry(msg, level) with EXACTLY
    two positional args — no color_hex, no meta. Color mapping is
    add_log_entry's own business (it derives the swatch internally); the
    route must not start passing one during the carve."""
    calls = _capture_logs(monkeypatch)
    client = _client()

    r = client.post("/api/log_event", json={"msg": "hello", "level": "WARNING"})
    assert r.status_code == 200
    assert r.get_json() == {"success": True}
    assert calls == [("hello", ("WARNING",), {})]


def test_log_event_level_defaults_to_info(monkeypatch):
    """Omitting 'level' logs at INFO — the frontend's bare log_event calls
    depend on this default."""
    calls = _capture_logs(monkeypatch)
    client = _client()

    client.post("/api/log_event", json={"msg": "y"})
    assert calls == [("y", ("INFO",), {})]


def test_log_event_blank_msg_is_noop_but_still_succeeds(monkeypatch):
    """Empty or missing msg writes NO log entry yet still returns
    {success: true} — callers can fire-and-forget without a guard."""
    calls = _capture_logs(monkeypatch)
    client = _client()

    r1 = client.post("/api/log_event", json={"msg": ""})
    r2 = client.post("/api/log_event", json={})
    assert r1.get_json() == {"success": True}
    assert r2.get_json() == {"success": True}
    assert calls == []


# ---------------------------------------------------------------------------
# /api/spools/refresh — validation + logic passthrough
# ---------------------------------------------------------------------------

def test_spools_refresh_rejects_non_list_with_400(monkeypatch):
    """A non-list 'spools' value is a 400 with the exact error string the
    dashboard buffer cards key off — and logic is never consulted."""
    monkeypatch.setattr(app_module.logic, "get_live_spools_data",
                        _fail_if_called("get_live_spools_data"))
    client = _client()

    r = client.post("/api/spools/refresh", json={"spools": "x"})
    assert r.status_code == 400
    assert r.get_json() == {"error": "spools must be a list"}


def test_spools_refresh_empty_list_short_circuits_to_empty_object(monkeypatch):
    """An empty spools list returns {} WITHOUT calling
    logic.get_live_spools_data — no gratuitous Spoolman fetch."""
    monkeypatch.setattr(app_module.logic, "get_live_spools_data",
                        _fail_if_called("get_live_spools_data"))
    client = _client()

    r = client.post("/api/spools/refresh", json={"spools": []})
    assert r.status_code == 200
    assert r.get_json() == {}


def test_spools_refresh_missing_key_defaults_to_empty(monkeypatch):
    """POST {} (no 'spools' key) behaves like an empty list: 200 {}."""
    monkeypatch.setattr(app_module.logic, "get_live_spools_data",
                        _fail_if_called("get_live_spools_data"))
    client = _client()

    r = client.post("/api/spools/refresh", json={})
    assert r.status_code == 200
    assert r.get_json() == {}


def test_spools_refresh_passes_ids_through_to_logic(monkeypatch):
    """A non-empty list is handed to logic.get_live_spools_data verbatim and
    the helper's return value is the response body, untransformed."""
    seen = []
    sentinel = {"1": {"remaining_weight": 42.0}, "2": {"remaining_weight": 7.5}}

    def fake_live(ids):
        seen.append(ids)
        return sentinel

    monkeypatch.setattr(app_module.logic, "get_live_spools_data", fake_live)
    client = _client()

    r = client.post("/api/spools/refresh", json={"spools": [1, 2]})
    assert r.status_code == 200
    assert r.get_json() == sentinel
    assert seen == [[1, 2]]


# ---------------------------------------------------------------------------
# /api/dashboard_pulse — SECTION DISPATCH contract
# ---------------------------------------------------------------------------

def test_pulse_empty_include_calls_no_sections_and_returns_empty(monkeypatch):
    """GET with no include= returns {} and invokes NONE of the section
    helpers — the pulse never assembles data nobody asked for."""
    _patch_all_pulse_sections_forbidden(monkeypatch)
    client = _client()

    r = client.get("/api/dashboard_pulse")
    assert r.status_code == 200
    assert r.get_json() == {}


def test_pulse_unknown_sections_silently_ignored(monkeypatch):
    """Unknown section names are dropped (forward-compat, no 4xx) — only
    the recognized 'buffer' section comes through, and no helper fires."""
    _patch_all_pulse_sections_forbidden(monkeypatch)
    monkeypatch.setattr(app_module.state, "GLOBAL_BUFFER", [{"id": 1}])
    client = _client()

    r = client.get("/api/dashboard_pulse?include=garbage,buffer,nonsense")
    assert r.status_code == 200
    assert r.get_json() == {"buffer": [{"id": 1}]}


def test_pulse_include_parsing_is_case_and_whitespace_insensitive(monkeypatch):
    """Section names are stripped and lowercased before matching — an
    include of ' Buffer , LOGS ' dispatches both sections."""
    logs_payload = {"logs": [], "status": {"spoolman": True},
                    "audit_active": False, "undo_available": False}
    calls = []
    monkeypatch.setattr(routes_state_pulse, "_pulse_section_logs",
                        lambda: calls.append("logs") or logs_payload)
    monkeypatch.setattr(app_module.state, "GLOBAL_BUFFER", [])
    client = _client()

    r = client.get("/api/dashboard_pulse?include=%20Buffer%20,%20LOGS%20")
    body = r.get_json()
    assert set(body.keys()) == {"buffer", "logs"}
    assert calls == ["logs"]


def test_pulse_logs_dispatch_passthrough(monkeypatch):
    """include=logs invokes _pulse_section_logs exactly once and places its
    return verbatim in the 'logs' slot; 'status' is NOT emitted unless
    requested."""
    logs_payload = {"logs": [{"msg": "x"}], "status": {"spoolman": True},
                    "audit_active": True, "undo_available": True}
    calls = []
    monkeypatch.setattr(routes_state_pulse, "_pulse_section_logs",
                        lambda: calls.append(1) or logs_payload)
    client = _client()

    r = client.get("/api/dashboard_pulse?include=logs")
    body = r.get_json()
    assert body == {"logs": logs_payload}
    assert len(calls) == 1


def test_pulse_status_derived_from_single_logs_call(monkeypatch):
    """include=status (alone) still runs _pulse_section_logs once (the
    health check lives there) but emits ONLY the derived 'status' section:
    {spoolman, audit_active, undo_available} — no 'filabridge' key (retired
    in Phase E Slice 4) and no 'logs' slot."""
    logs_payload = {"logs": [{"msg": "x"}], "status": {"spoolman": True},
                    "audit_active": True, "undo_available": False}
    calls = []
    monkeypatch.setattr(routes_state_pulse, "_pulse_section_logs",
                        lambda: calls.append(1) or logs_payload)
    client = _client()

    r = client.get("/api/dashboard_pulse?include=status")
    body = r.get_json()
    assert body == {"status": {
        "spoolman": True, "audit_active": True, "undo_available": False,
    }}
    assert len(calls) == 1


def test_pulse_status_defaults_false_on_sparse_logs_payload(monkeypatch):
    """The status derivation uses .get(..., False) at every hop — a logs
    payload of just {'status': {}} yields all-False status bits rather
    than a KeyError."""
    monkeypatch.setattr(routes_state_pulse, "_pulse_section_logs",
                        lambda: {"status": {}})
    client = _client()

    r = client.get("/api/dashboard_pulse?include=status")
    assert r.get_json() == {"status": {
        "spoolman": False, "audit_active": False, "undo_available": False,
    }}


def test_pulse_logs_and_status_share_one_section_call(monkeypatch):
    """Requesting logs AND status invokes _pulse_section_logs exactly ONCE
    (shared health check) and both sections agree on the spoolman bit."""
    logs_payload = {"logs": [], "status": {"spoolman": True},
                    "audit_active": False, "undo_available": True}
    calls = []
    monkeypatch.setattr(routes_state_pulse, "_pulse_section_logs",
                        lambda: calls.append(1) or logs_payload)
    client = _client()

    r = client.get("/api/dashboard_pulse?include=logs,status")
    body = r.get_json()
    assert set(body.keys()) == {"logs", "status"}
    assert len(calls) == 1
    assert body["logs"]["status"]["spoolman"] == body["status"]["spoolman"] is True
    assert body["status"]["undo_available"] is True


def test_pulse_status_section_carries_error_when_logs_helper_raises(monkeypatch):
    """27.9 FIX — when the shared _pulse_section_logs health check raises, the
    derived 'status' section now honors the endpoint's documented per-section
    isolation contract and carries {'error': str(e)} (so the nav-bar
    spoolman/audit/undo dot gets a signal), instead of being silently omitted."""
    def _boom():
        raise RuntimeError("health check exploded")

    monkeypatch.setattr(routes_state_pulse, "_pulse_section_logs", _boom)
    client = _client()

    r = client.get("/api/dashboard_pulse?include=logs,status")
    assert r.status_code == 200
    assert r.get_json() == {
        "logs": {"error": "health check exploded"},
        "status": {"error": "health check exploded"},
    }

    r2 = client.get("/api/dashboard_pulse?include=status")
    assert r2.status_code == 200
    assert r2.get_json() == {"status": {"error": "health check exploded"}}


def test_pulse_locations_dispatch_passthrough(monkeypatch):
    """include=locations invokes _pulse_section_locations once and returns
    its value verbatim in the 'locations' slot."""
    sentinel = [{"LocationID": "Unassigned"}, {"LocationID": "XL-1"}]
    calls = []
    monkeypatch.setattr(routes_state_pulse, "_pulse_section_locations",
                        lambda: calls.append(1) or sentinel)
    client = _client()

    r = client.get("/api/dashboard_pulse?include=locations")
    assert r.get_json() == {"locations": sentinel}
    assert len(calls) == 1


def test_pulse_locations_error_is_isolated(monkeypatch):
    """A raising locations section lands as {'error': str(e)} in its slot
    while the rest of the pulse (buffer here) still returns 200 — a partial
    failure must not blank the dashboard."""
    def _boom():
        raise RuntimeError("locations corrupt")

    monkeypatch.setattr(routes_state_pulse, "_pulse_section_locations", _boom)
    monkeypatch.setattr(app_module.state, "GLOBAL_BUFFER", [{"id": 5}])
    client = _client()

    r = client.get("/api/dashboard_pulse?include=locations,buffer")
    assert r.status_code == 200
    assert r.get_json() == {
        "locations": {"error": "locations corrupt"},
        "buffer": [{"id": 5}],
    }


def test_pulse_buffer_reads_global_buffer_directly(monkeypatch):
    """The buffer section is a direct state.GLOBAL_BUFFER read — no helper
    function, no copy. Pin the passthrough so a carve that reroutes it
    through a section helper keeps the same payload."""
    _patch_all_pulse_sections_forbidden(monkeypatch)
    monkeypatch.setattr(app_module.state, "GLOBAL_BUFFER",
                        [{"id": 11, "label": "PETG"}])
    client = _client()

    r = client.get("/api/dashboard_pulse?include=buffer")
    assert r.get_json() == {"buffer": [{"id": 11, "label": "PETG"}]}


def test_pulse_manage_omitted_without_manage_id(monkeypatch):
    """include=manage WITHOUT manage_id silently omits the section (no
    error) and never calls _pulse_section_manage; other sections still
    come through."""
    monkeypatch.setattr(routes_state_pulse, "_pulse_section_manage",
                        _fail_if_called("_pulse_section_manage"))
    monkeypatch.setattr(app_module.state, "GLOBAL_BUFFER", [])
    client = _client()

    r = client.get("/api/dashboard_pulse?include=manage,buffer")
    assert r.status_code == 200
    assert r.get_json() == {"buffer": []}


def test_pulse_manage_id_uppercased_and_payload_passthrough(monkeypatch):
    """manage_id is stripped + UPPERCASED before being handed to
    _pulse_section_manage, and the helper's return lands verbatim in the
    'manage' slot — the frontend keys the open modal off that id casing."""
    seen = []
    sentinel = {"id": "PM-DB-XL-L", "contents": [{"id": 1}]}

    def fake_manage(loc_id):
        seen.append(loc_id)
        return sentinel

    monkeypatch.setattr(routes_state_pulse, "_pulse_section_manage", fake_manage)
    client = _client()

    r = client.get(
        "/api/dashboard_pulse?include=manage&manage_id=%20pm-db-xl-l%20")
    assert r.get_json() == {"manage": sentinel}
    assert seen == ["PM-DB-XL-L"]


def test_pulse_manage_error_slot_carries_id(monkeypatch):
    """A raising manage section returns {'error': str(e), 'id': <manage_id>}
    so the frontend can match the failure to the open modal."""
    def _boom(loc_id):
        raise RuntimeError("spoolman down")

    monkeypatch.setattr(routes_state_pulse, "_pulse_section_manage", _boom)
    client = _client()

    r = client.get("/api/dashboard_pulse?include=manage&manage_id=xl-1")
    assert r.status_code == 200
    assert r.get_json() == {"manage": {"error": "spoolman down", "id": "XL-1"}}


def test_pulse_printer_status_dispatch_and_error_isolation(monkeypatch):
    """include=printer_status invokes _pulse_section_printer_status once
    (passthrough), and a raising helper degrades to {'error': str(e)} in
    the slot with the response still 200."""
    sentinel = {"XL": {"toolheads": [], "state": None}}
    calls = []
    monkeypatch.setattr(routes_state_pulse, "_pulse_section_printer_status",
                        lambda: calls.append(1) or sentinel)
    client = _client()

    r = client.get("/api/dashboard_pulse?include=printer_status")
    assert r.get_json() == {"printer_status": sentinel}
    assert len(calls) == 1

    def _boom():
        raise RuntimeError("probe failed")

    monkeypatch.setattr(routes_state_pulse, "_pulse_section_printer_status", _boom)
    r2 = client.get("/api/dashboard_pulse?include=printer_status")
    assert r2.status_code == 200
    assert r2.get_json() == {"printer_status": {"error": "probe failed"}}


def test_pulse_post_refresh_spool_ids_adds_spools_refresh_section(monkeypatch):
    """POST with {refresh_spool_ids: [...]} produces a 'spools_refresh'
    section built by logic.get_live_spools_data with the ids verbatim —
    independent of include= (works alongside other sections)."""
    seen = []
    sentinel = {"3": {"remaining_weight": 1.0}}

    def fake_live(ids):
        seen.append(ids)
        return sentinel

    monkeypatch.setattr(app_module.logic, "get_live_spools_data", fake_live)
    monkeypatch.setattr(app_module.state, "GLOBAL_BUFFER", [])
    client = _client()

    r = client.post("/api/dashboard_pulse?include=buffer",
                    json={"refresh_spool_ids": [3, 4]})
    body = r.get_json()
    assert body == {"buffer": [], "spools_refresh": sentinel}
    assert seen == [[3, 4]]


def test_pulse_post_non_list_refresh_ids_ignored(monkeypatch):
    """A non-list refresh_spool_ids is coerced to [] — no spools_refresh
    section, no logic call, no error."""
    monkeypatch.setattr(app_module.logic, "get_live_spools_data",
                        _fail_if_called("get_live_spools_data"))
    client = _client()

    r = client.post("/api/dashboard_pulse", json={"refresh_spool_ids": "x"})
    assert r.status_code == 200
    assert r.get_json() == {}

    r2 = client.post("/api/dashboard_pulse", json={"refresh_spool_ids": []})
    assert r2.get_json() == {}


def test_pulse_get_with_body_never_produces_spools_refresh(monkeypatch):
    """The spools_refresh section is POST-gated: a GET carrying a JSON body
    with refresh_spool_ids is ignored (the dashboard must opt in explicitly
    via POST, so ordinary GET pulses never re-fetch live spool data)."""
    monkeypatch.setattr(app_module.logic, "get_live_spools_data",
                        _fail_if_called("get_live_spools_data"))
    monkeypatch.setattr(app_module.state, "GLOBAL_BUFFER", [])
    client = _client()

    r = client.get("/api/dashboard_pulse?include=buffer",
                   json={"refresh_spool_ids": [1]})
    assert r.status_code == 200
    assert r.get_json() == {"buffer": []}


def test_pulse_spools_refresh_error_is_isolated(monkeypatch):
    """A raising get_live_spools_data degrades the spools_refresh slot to
    {'error': str(e)} while the response stays 200 with other sections
    intact."""
    def _boom(ids):
        raise RuntimeError("spoolman timeout")

    monkeypatch.setattr(app_module.logic, "get_live_spools_data", _boom)
    monkeypatch.setattr(app_module.state, "GLOBAL_BUFFER", [{"id": 8}])
    client = _client()

    r = client.post("/api/dashboard_pulse?include=buffer",
                    json={"refresh_spool_ids": [8]})
    assert r.status_code == 200
    assert r.get_json() == {
        "buffer": [{"id": 8}],
        "spools_refresh": {"error": "spoolman timeout"},
    }
