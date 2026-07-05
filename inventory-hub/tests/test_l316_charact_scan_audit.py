"""L316 characterization tests — pins pre-carve behavior of the
/api/identify_scan audit-branch family (CMD:AUDIT activation, active-session
delegation, spool-branch ghost payload) and the /api/manage_contents
non-active-print branches (app.py 2296-3115). Generated from the 2026-07-01
coverage audit. Do not weaken these to make a refactor pass.

Everything here is host-runnable and offline: logic.resolve_scan is exercised
for real (its CMD:/ID:/LOC: prefix branches make no outbound calls) and every
Spoolman / logic side-effect surface is patched. Audit state is module-global
(state.AUDIT_SESSION), so an autouse fixture resets it around every test to
avoid poisoning other files in a shared sweep — the same idiom used by
tests/test_audit_session_endpoint.py and tests/test_audit_auto_park_unknown.py.
"""
from __future__ import annotations

import os
import sys
import time
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import app as app_module  # noqa: E402
import state  # noqa: E402


@pytest.fixture
def client():
    app_module.app.config["TESTING"] = True
    return app_module.app.test_client()


@pytest.fixture(autouse=True)
def _isolated_audit_session():
    """AUDIT_SESSION is a module-global dict mutated in place by the routes
    under test. Reset to the canonical inactive state before AND after each
    test so (a) a poisoned session from another file can't skew us and
    (b) we never leave an active session behind for the rest of the sweep."""
    state.reset_audit()
    yield
    state.reset_audit()


# ---------------------------------------------------------------------------
# 1. /api/identify_scan — CMD:AUDIT activation.
# ---------------------------------------------------------------------------

def test_cmd_audit_activates_session_and_returns_clear(client):
    """CMD:AUDIT flips AUDIT_SESSION.active on, stamps the idle-watchdog
    timestamp, logs the two kickoff Activity-Log lines, and answers the
    scanner with {'type':'command','cmd':'clear'} (buffer-wipe signal).
    A pure-move that drops the timestamp stamp would break the 30-min
    idle-timeout watchdog with nothing else going red."""
    before = time.time()
    with patch.object(app_module.state, "add_log_entry") as log:
        r = client.post("/api/identify_scan",
                        json={"text": "CMD:AUDIT", "source": "barcode"})
    after = time.time()

    assert r.status_code == 200
    assert r.get_json() == {"type": "command", "cmd": "clear"}
    assert state.AUDIT_SESSION["active"] is True
    ts = state.AUDIT_SESSION["last_activity_ts"]
    assert before <= ts <= after, f"watchdog ts not stamped fresh: {ts}"

    # Exactly two kickoff log lines, in order, with the pinned category/color.
    assert log.call_count == 2
    first_args = log.call_args_list[0][0]
    assert "AUDIT MODE STARTED" in first_args[0]
    assert first_args[1] == "INFO"
    assert first_args[2] == "ff00ff"
    second_args = log.call_args_list[1][0]
    assert second_args[0] == "Scan a Location label to begin checking."


def test_cmd_audit_during_active_session_is_noop_preserves_state(client):
    """27.5 FIX — the CMD:AUDIT branch now checks for an active session FIRST:
    re-scanning CMD:AUDIT mid-audit no longer silently reset_audit()s and wipes
    in-progress scanned/expected/rogue state. It's a no-op that refreshes the
    idle watchdog and logs an 'already in progress' info line; the user ends the
    audit explicitly via CMD:CANCEL/CMD:DONE. process_audit_scan is NOT called
    (no delegation) and the response is still {'cmd':'clear'}."""
    state.AUDIT_SESSION.update({
        "active": True,
        "location_id": "LR-MDB-1",
        "expected_items": [101, 102],
        "scanned_items": [101],
        "rogue_items": [999],
        "last_activity_ts": time.time() - 999.0,
    })
    before = time.time()
    with patch.object(app_module.state, "add_log_entry") as log, \
         patch.object(app_module.logic, "process_audit_scan") as pas:
        r = client.post("/api/identify_scan",
                        json={"text": "CMD:AUDIT", "source": "barcode"})

    assert r.get_json() == {"type": "command", "cmd": "clear"}
    pas.assert_not_called()  # no-op, not delegation
    sess = state.AUDIT_SESSION
    assert sess["active"] is True
    assert sess["location_id"] == "LR-MDB-1"       # preserved
    assert sess["expected_items"] == [101, 102]     # preserved
    assert sess["scanned_items"] == [101]           # preserved
    assert sess["rogue_items"] == [999]             # preserved
    assert sess["last_activity_ts"] >= before       # watchdog refreshed
    assert any("already in progress" in c[0][0] for c in log.call_args_list)


# ---------------------------------------------------------------------------
# 2. /api/identify_scan — active-session delegation (pre-empts normal dispatch).
# ---------------------------------------------------------------------------

def test_active_audit_hijacks_spool_scan_and_refreshes_watchdog(client):
    """With an active audit session, an ID:<n> scan must be handed to
    logic.process_audit_scan and must NOT reach the normal spool branch —
    even a 'barcode'-source ID: scan (which would otherwise flip the
    needs_label_print flag via update_spool). The route also refreshes
    last_activity_ts BEFORE delegating, and returns {'cmd':'clear'}
    regardless of what process_audit_scan reports."""
    stale = time.time() - 999.0
    state.AUDIT_SESSION.update({
        "active": True,
        "location_id": "LR-MDB-1",
        "expected_items": [10],
        "scanned_items": [],
        "rogue_items": [],
        "last_activity_ts": stale,
    })
    before = time.time()
    with patch.object(app_module.logic, "process_audit_scan",
                      return_value={"status": "error", "msg": "not allowed"}) as pas, \
         patch.object(app_module.spoolman_api, "get_spool") as gs, \
         patch.object(app_module.spoolman_api, "update_spool") as us:
        r = client.post("/api/identify_scan",
                        json={"text": "ID:10", "source": "barcode"})
    after = time.time()

    # Route response is 'clear' even though the (patched) audit handler
    # reported an error — the delegation result is discarded.
    # NOTE: pins current behavior; see suspected_bugs.
    assert r.get_json() == {"type": "command", "cmd": "clear"}
    pas.assert_called_once_with({"type": "spool", "id": 10})
    gs.assert_not_called()   # normal spool branch never ran
    us.assert_not_called()   # label-verify write never ran
    ts = state.AUDIT_SESSION["last_activity_ts"]
    assert ts > stale and before <= ts <= after, "watchdog ts not refreshed"


def test_active_audit_hijacks_location_scan(client):
    """LOC:<id> during an active audit is delegated to process_audit_scan;
    the normal location branch (contents lookup + '🔎' log) must not run."""
    state.AUDIT_SESSION.update({
        "active": True,
        "last_activity_ts": time.time(),
    })
    with patch.object(app_module.logic, "process_audit_scan",
                      return_value={"status": "success"}) as pas, \
         patch.object(app_module.spoolman_api,
                      "get_spools_at_location_detailed") as gl:
        r = client.post("/api/identify_scan",
                        json={"text": "LOC:LR-MDB-1", "source": "barcode"})

    assert r.get_json() == {"type": "command", "cmd": "clear"}
    pas.assert_called_once_with({"type": "location", "id": "LR-MDB-1"})
    gl.assert_not_called()


def test_inactive_audit_location_scan_uses_normal_branch(client):
    """Control for the hijack tests: with NO active audit session, the same
    LOC: scan flows to the normal location branch and returns the pinned
    {'type':'location', 'id', 'display', 'contents'} shape."""
    with patch.object(app_module.logic, "process_audit_scan") as pas, \
         patch.object(app_module.spoolman_api, "get_spools_at_location_detailed",
                      return_value=[]) as gl, \
         patch.object(app_module.state, "add_log_entry") as log:
        r = client.post("/api/identify_scan",
                        json={"text": "LOC:LR-MDB-1", "source": "barcode"})

    pas.assert_not_called()
    gl.assert_called_once_with("LR-MDB-1")
    assert r.get_json() == {
        "type": "location",
        "id": "LR-MDB-1",
        "display": "LOC: LR-MDB-1",
        "contents": [],
    }
    assert any("0 item(s)" in c[0][0] for c in log.call_args_list)


def test_cmd_cancel_during_audit_ends_session_cleanly(client):
    """Deactivation path: CMD:CANCEL while active routes through the audit
    delegation into the REAL process_audit_scan, which emits the Audit
    Report + 'Audit Mode Ended.' log lines and reset_audit()s. The route's
    pre-delegation timestamp refresh is deliberately ordered BEFORE the
    handler so the reset wins — final last_activity_ts is back to 0.0."""
    state.AUDIT_SESSION.update({
        "active": True,
        "location_id": "LR-MDB-1",
        "expected_items": [],
        "scanned_items": [],
        "rogue_items": [],
        "last_activity_ts": time.time(),
    })
    log_calls = []
    with patch.object(app_module.state, "add_log_entry",
                      side_effect=lambda *a, **k: log_calls.append(a)), \
         patch.object(app_module.spoolman_api, "get_spool") as gs, \
         patch.object(app_module.spoolman_api, "update_spool") as us:
        r = client.post("/api/identify_scan",
                        json={"text": "CMD:CANCEL", "source": "barcode"})

    assert r.get_json() == {"type": "command", "cmd": "clear"}
    assert state.AUDIT_SESSION["active"] is False
    assert state.AUDIT_SESSION["last_activity_ts"] == 0.0
    assert any("Audit Report" in c[0] for c in log_calls)
    assert any("Audit Mode Ended." in c[0] for c in log_calls)
    # Cancel with nothing missing/rogue makes no Spoolman writes.
    gs.assert_not_called()
    us.assert_not_called()


# ---------------------------------------------------------------------------
# 3. /api/identify_scan — spool-branch ghost payload.
# ---------------------------------------------------------------------------

GHOST_SPOOL = {
    "id": 9,
    "location": "XL-1",
    "extra": {
        "physical_source": '"PM-DB-XL-L"',      # JSON-wrapped, as stored
        "physical_source_slot": '"3"',
    },
    "remaining_weight": 500,
}

DISPLAY_INFO = {
    "text": "PLA Galaxy",
    "color": "#ff0000",
    "slot": "1",
    "details": {"brand": "Prusament"},
}


def test_spool_scan_ghost_payload_full_shape(client):
    """Ghost computation: quote-stripped extra.physical_source differing from
    the live location (case-insensitive) flips is_ghost, swaps `location` to
    the physical source, exposes the live location as `deployed_to`, and
    lets extra.physical_source_slot OVERRIDE the display slot. Keyboard
    source skips the label-verify write entirely. Exact response-dict pin."""
    with patch.object(app_module.spoolman_api, "get_spool",
                      return_value=dict(GHOST_SPOOL)) as gs, \
         patch.object(app_module.spoolman_api, "format_spool_display",
                      return_value=dict(DISPLAY_INFO)), \
         patch.object(app_module.spoolman_api, "update_spool") as us:
        r = client.post("/api/identify_scan",
                        json={"text": "ID:9", "source": "keyboard"})

    gs.assert_called_once_with(9)
    us.assert_not_called()  # keyboard source never flips needs_label_print
    assert r.get_json() == {
        "type": "spool",
        "id": 9,
        "display": "PLA Galaxy",
        "color": "#ff0000",
        "color_direction": "longitudinal",   # default when info omits it
        "remaining_weight": 500,
        "details": {"brand": "Prusament"},
        "archived": False,
        "location": "PM-DB-XL-L",            # quote-stripped physical source
        "is_ghost": True,
        "slot": "3",                          # ghost slot overrides display '1'
        "deployed_to": "XL-1",                # live location moved here
        "label_already_verified": False,
    }


def test_spool_scan_non_ghost_when_location_matches_source_case_insensitive(client):
    """location == physical_source compared case-insensitively → NOT a ghost:
    `location` stays the RAW stored location string (no canonicalization),
    deployed_to is None, and the slot comes from format_spool_display even
    though a physical_source_slot extra is present."""
    spool = {
        "id": 9,
        "location": "pm-db-xl-l",             # lower-case on purpose
        "extra": {
            "physical_source": '"PM-DB-XL-L"',
            "physical_source_slot": '"4"',
        },
        "remaining_weight": 250,
        "archived": True,
    }
    with patch.object(app_module.spoolman_api, "get_spool", return_value=spool), \
         patch.object(app_module.spoolman_api, "format_spool_display",
                      return_value=dict(DISPLAY_INFO)):
        r = client.post("/api/identify_scan",
                        json={"text": "ID:9", "source": "keyboard"})

    assert r.get_json() == {
        "type": "spool",
        "id": 9,
        "display": "PLA Galaxy",
        "color": "#ff0000",
        "color_direction": "longitudinal",
        "remaining_weight": 250,
        "details": {"brand": "Prusament"},
        "archived": True,
        "location": "pm-db-xl-l",             # raw casing preserved
        "is_ghost": False,
        "slot": "1",                           # from display info, not the extra
        "deployed_to": None,
        "label_already_verified": False,
    }


def test_spool_scan_ghost_without_slot_extra_keeps_display_slot(client):
    """Ghost with NO physical_source_slot extra: is_ghost still flips, but
    final_slot falls back to the format_spool_display slot."""
    spool = {
        "id": 9,
        "location": "XL-1",
        "extra": {"physical_source": '"PM-DB-XL-L"'},
        "remaining_weight": 500,
    }
    with patch.object(app_module.spoolman_api, "get_spool", return_value=spool), \
         patch.object(app_module.spoolman_api, "format_spool_display",
                      return_value=dict(DISPLAY_INFO)):
        r = client.post("/api/identify_scan",
                        json={"text": "ID:9", "source": "keyboard"})
    body = r.get_json()
    assert body["is_ghost"] is True
    assert body["location"] == "PM-DB-XL-L"
    assert body["deployed_to"] == "XL-1"
    assert body["slot"] == "1"


def test_spool_scan_unknown_spool_returns_error_payload(client):
    """27.10 FIX — get_spool → None (deleted/unknown id) now returns a
    renderable scan-failure payload {'type':'error','msg':...} (the frontend
    toasts res.type=='error') plus a WARNING Activity-Log line, instead of
    falling through to the bare, unrenderable {'type':'spool','id':N}."""
    with patch.object(app_module.spoolman_api, "get_spool", return_value=None), \
         patch.object(app_module.spoolman_api, "format_spool_display") as fsd, \
         patch.object(app_module.state, "add_log_entry") as log:
        r = client.post("/api/identify_scan",
                        json={"text": "ID:424242", "source": "keyboard"})
    fsd.assert_not_called()
    assert r.get_json() == {"type": "error", "msg": "Spool #424242 not found"}
    assert any("not found" in c[0][0] for c in log.call_args_list)


def test_filament_scan_unknown_filament_returns_error_payload(client):
    """27.10 FIX (filament side) — get_filament → None returns the same
    renderable {'type':'error'} scan-failure payload + WARNING log rather than
    the bare {'type':'filament','id':N} the UI would try to open as real."""
    with patch.object(app_module.spoolman_api, "get_filament", return_value=None), \
         patch.object(app_module.state, "add_log_entry") as log:
        r = client.post("/api/identify_scan",
                        json={"text": "FIL:99999", "source": "keyboard"})
    assert r.get_json() == {"type": "error", "msg": "Filament #99999 not found"}
    assert any("not found" in c[0][0] for c in log.call_args_list)


# ---------------------------------------------------------------------------
# 4. /api/manage_contents — remove-action result mapping.
# ---------------------------------------------------------------------------

def test_remove_legacy_require_confirm_string_translated_to_json(client):
    """perform_smart_eject's legacy 'REQUIRE_CONFIRM' string return is
    translated to a {success:false, require_confirm:true} JSON with the
    exact unassign-to-nowhere prompt. Also pins the default kwargs the
    route forwards (confirmed=False, confirm_active_print=False)."""
    with patch.object(app_module.logic, "perform_smart_eject",
                      return_value="REQUIRE_CONFIRM") as eject:
        r = client.post("/api/manage_contents",
                        json={"action": "remove", "spool_id": "55"})
    assert r.get_json() == {
        "success": False,
        "require_confirm": True,
        "msg": "Spool is already in a room. Confirm true unassign to nowhere?",
    }
    eject.assert_called_once_with(
        55, confirmed_unassign=False, confirm_active_print=False)


def test_remove_true_maps_to_success_and_confirmed_flag_passthrough(client):
    """perform_smart_eject → True maps to bare {success:true}; the caller's
    `confirmed` flag rides through as confirmed_unassign."""
    with patch.object(app_module.logic, "perform_smart_eject",
                      return_value=True) as eject:
        r = client.post("/api/manage_contents", json={
            "action": "remove", "spool_id": "55", "confirmed": True,
        })
    assert r.get_json() == {"success": True}
    eject.assert_called_once_with(
        55, confirmed_unassign=True, confirm_active_print=False)


@pytest.mark.parametrize("eject_result", [False, None])
def test_remove_falsy_result_maps_to_db_update_failed(client, eject_result):
    """Any falsy non-string eject result (False or None) collapses to the
    generic 'DB Update Failed' message — the actual Spoolman error is NOT
    surfaced on this path."""
    with patch.object(app_module.logic, "perform_smart_eject",
                      return_value=eject_result):
        r = client.post("/api/manage_contents",
                        json={"action": "remove", "spool_id": "55"})
    assert r.get_json() == {"success": False, "msg": "DB Update Failed"}


def test_remove_non_numeric_spool_input_is_spool_not_found(client):
    """remove (unlike add) does NOT run resolve_scan — a prefixed scan code
    like 'ID:55' fails isdigit() and dead-ends at 'Spool not found'."""
    with patch.object(app_module.logic, "perform_smart_eject") as eject:
        r = client.post("/api/manage_contents",
                        json={"action": "remove", "spool_id": "ID:55"})
    assert r.get_json() == {"success": False, "msg": "Spool not found"}
    eject.assert_not_called()


# ---------------------------------------------------------------------------
# 5. /api/manage_contents — add-action result mapping.
# ---------------------------------------------------------------------------

def test_add_resolve_error_message_passes_through(client):
    """resolve_scan → {'type':'error'} short-circuits before any move; the
    resolver's msg is surfaced verbatim."""
    with patch.object(app_module.logic, "resolve_scan",
                      return_value={"type": "error", "msg": "boom"}), \
         patch.object(app_module.logic, "perform_smart_move") as mv:
        r = client.post("/api/manage_contents", json={
            "action": "add", "location": "LR-MDB-1", "spool_id": "garbage",
        })
    assert r.get_json() == {"success": False, "msg": "boom"}
    mv.assert_not_called()


@pytest.mark.parametrize("resolution", [
    None,                                   # resolver came up empty
    {"type": "location", "id": "LR-MDB-1"},  # resolved, but not to a spool
])
def test_add_non_spool_resolution_is_spool_not_found(client, resolution):
    """A None or non-spool/non-error resolution leaves spool_id unset and
    dead-ends at the generic 'Spool not found' guard."""
    with patch.object(app_module.logic, "resolve_scan",
                      return_value=resolution), \
         patch.object(app_module.logic, "perform_smart_move") as mv:
        r = client.post("/api/manage_contents", json={
            "action": "add", "location": "LR-MDB-1", "spool_id": "whatever",
        })
    assert r.get_json() == {"success": False, "msg": "Spool not found"}
    mv.assert_not_called()


def test_add_without_spool_input_is_spool_not_found(client):
    """Missing spool_id: resolve_scan is never even called."""
    with patch.object(app_module.logic, "resolve_scan") as rs:
        r = client.post("/api/manage_contents",
                        json={"action": "add", "location": "LR-MDB-1"})
    assert r.get_json() == {"success": False, "msg": "Spool not found"}
    rs.assert_not_called()


def test_add_returns_perform_smart_move_result_verbatim(client):
    """Happy path: the perform_smart_move dict is jsonify'd UNCHANGED (no
    success-key normalization), the location is strip().upper()
    canonicalized, and slot/origin/confirm flags pass through."""
    sentinel = {"status": "success", "moved": [7], "auto_deployed_to": "XL-1"}
    with patch.object(app_module.logic, "resolve_scan",
                      return_value={"type": "spool", "id": 7}) as rs, \
         patch.object(app_module.logic, "perform_smart_move",
                      return_value=sentinel) as mv:
        r = client.post("/api/manage_contents", json={
            "action": "add",
            "location": " lr-mdb-1 ",
            "spool_id": "ID:7",
            "slot": "2",
            "origin": "buffer",
        })
    assert r.get_json() == sentinel
    rs.assert_called_once_with("ID:7")
    args, kwargs = mv.call_args
    assert args == ("LR-MDB-1", [7])
    assert kwargs == {
        "target_slot": "2",
        "origin": "buffer",
        "confirm_active_print": False,
    }


# ---------------------------------------------------------------------------
# 6. /api/manage_contents — clear_location mapping.
# ---------------------------------------------------------------------------

def test_clear_location_ejects_unslotted_and_surfaces_slotted_survivors(client):
    """27.6 FIX — clear_location still skips ghosts (documented ALEX FIX) AND
    still does NOT auto-eject slotted spools (loaded into a toolhead/MMU —
    ejecting them on a bulk clear would unassign a live feed), but it no longer
    reports a bare success: the slotted survivors are surfaced in the response
    (ejected[] + skipped_slotted[] + msg) and a WARNING Activity-Log line names
    them. Only unslotted spools ('' / 'None' / missing) get perform_smart_eject,
    each with confirm_active_print=True (bulk clear bypasses per-spool prompts)."""
    contents = [
        {"id": 1, "is_ghost": True, "slot": ""},   # ghost → skipped (not surfaced)
        {"id": 2, "slot": "2"},                     # slotted → kept + surfaced
        {"id": 3, "slot": ""},                      # empty slot → ejected
        {"id": 4, "slot": "None"},                  # 'None' string → ejected
        {"id": 5},                                  # no slot key → ejected
    ]
    with patch.object(app_module.spoolman_api, "get_spools_at_location_detailed",
                      return_value=contents) as gl, \
         patch.object(app_module.logic, "_active_print_info_for_location",
                      return_value=None) as ap, \
         patch.object(app_module.logic, "perform_smart_eject") as eject, \
         patch.object(app_module.state, "add_log_entry") as log:
        r = client.post("/api/manage_contents", json={
            "action": "clear_location", "location": "lr-mdb-1",
        })

    body = r.get_json()
    assert body["success"] is True
    assert body["ejected"] == [3, 4, 5]
    assert body["skipped_slotted"] == [2]          # slotted survivor surfaced
    assert "left in place" in body["msg"]
    gl.assert_called_once_with("LR-MDB-1")   # strip().upper() canonicalized
    ap.assert_called_once_with("LR-MDB-1")
    ejected = [c[0][0] for c in eject.call_args_list]
    assert ejected == [3, 4, 5]
    for c in eject.call_args_list:
        assert c[1] == {"confirm_active_print": True}
    assert any("slotted spool(s) left in place" in c[0][0]
               for c in log.call_args_list)


def test_clear_location_confirm_flag_skips_active_print_probe(client):
    """confirm_active_print=True bypasses the pre-flight printer probe
    entirely (it is not merely ignored — never called)."""
    with patch.object(app_module.spoolman_api, "get_spools_at_location_detailed",
                      return_value=[{"id": 3, "slot": ""}]), \
         patch.object(app_module.logic, "_active_print_info_for_location") as ap, \
         patch.object(app_module.logic, "perform_smart_eject") as eject:
        r = client.post("/api/manage_contents", json={
            "action": "clear_location", "location": "XL-1",
            "confirm_active_print": True,
        })
    assert r.get_json() == {"success": True}
    ap.assert_not_called()
    eject.assert_called_once_with(3, confirm_active_print=True)


# ---------------------------------------------------------------------------
# 7. /api/manage_contents — force_unassign + unknown-action mapping.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("result,expected", [
    (True, {"success": True}),
    (False, {"success": False, "msg": "DB Update Failed"}),
    (None, {"success": False, "msg": "DB Update Failed"}),
])
def test_force_unassign_truthiness_mapping(client, result, expected):
    """force_unassign maps any truthy result to success and any falsy one to
    the generic 'DB Update Failed' (no Spoolman error surfaced)."""
    with patch.object(app_module.logic, "perform_force_unassign",
                      return_value=result) as fu:
        r = client.post("/api/manage_contents",
                        json={"action": "force_unassign", "spool_id": "55"})
    assert r.get_json() == expected
    fu.assert_called_once_with(55, confirm_active_print=False)


def test_unknown_action_returns_spool_not_found(client):
    """An unrecognized action never sets spool_id, so it dead-ends at the
    'Spool not found' guard — NOT the terminal bare {'success': False}
    (that line is unreachable in practice).
    # NOTE: pins current behavior; see suspected_bugs (misleading message)."""
    r = client.post("/api/manage_contents",
                    json={"action": "frobnicate", "spool_id": "55"})
    assert r.get_json() == {"success": False, "msg": "Spool not found"}
