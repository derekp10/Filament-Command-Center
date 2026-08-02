"""
Unit tests for the L298 Bulk Moves Phase 2 scan session (CMD:BULKMOVE).

Phase 1 shipped the stateless POST /api/bulk_move. Phase 2 adds the scan-driven
session that both entries (the CMD:BULKMOVE deck QR and the Location-Manager
"Move all →" button) drive:

  state.BULK_MOVE_SESSION  — idle → awaiting_source → awaiting_dest → preview
  logic.process_bulk_move_scan  — routes scans into the active session
  logic.commit_bulk_move_session — re-plans against LIVE state, then executes
  GET  /api/bulk_move_session   — the panel poll (+ lazy idle watchdog)
  POST /api/bulk_move_session   — start / set_dest / commit / cancel

The load-bearing invariants pinned here:
  - scanning a DESTINATION never auto-commits (a bulk move is too destructive
    to fire on a stray scan) — it lands in `preview` and waits;
  - re-scanning CMD:BULKMOVE mid-session must NOT wipe a captured source
    (the audit 27.5 guard, cloned);
  - commit RE-PLANS from live state rather than trusting the stored preview;
  - the session and the stateless endpoint share ONE plan/execute core, so the
    preview a user confirms cannot disagree with what the commit guards.
"""
from __future__ import annotations

import contextlib
import os
import sys
import time
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import app as app_module  # noqa: E402
import logic  # noqa: E402
import locations_db  # noqa: E402
import routes_state_pulse  # noqa: E402
import spoolman_api  # noqa: E402
import state  # noqa: E402


FAKE_LOCATIONS = [
    {"LocationID": "PM-DB-A", "Type": "Dryer Box", "Max Spools": "4", "Name": "Box A"},
    {"LocationID": "SHELF-B", "Type": "Wall Shelf", "Max Spools": "0", "Name": "Shelf B"},
    {"LocationID": "CR", "Type": "Room", "Max Spools": "0", "Name": "Computer Room"},
    {"LocationID": "XL-1", "Type": "Tool Head", "Max Spools": "1", "Name": "XL-1"},
]
FAKE_PRINTER_MAP = {"XL-1": {"printer_name": "XL", "position": 0}}


@pytest.fixture
def client():
    app_module.app.config["TESTING"] = True
    return app_module.app.test_client()


@pytest.fixture(autouse=True)
def _clean_session():
    """Every test starts and ends with a cleared session (it's module state)."""
    state.reset_bulk_move()
    prior_logs = list(state.RECENT_LOGS)
    state.RECENT_LOGS = []
    try:
        yield
    finally:
        state.reset_bulk_move()
        state.RECENT_LOGS = prior_logs


def _spool(sid, location="PM-DB-A", is_ghost=False, archived=False):
    return {"id": sid, "location": location, "is_ghost": is_ghost,
            "archived": archived, "slot": "", "display": f"#{sid}", "color": "ffffff"}


@contextlib.contextmanager
def _env(*, strict_map=None, readback=None, active_print_for=None,
         move_result=None, buffer=None):
    """Patch every collaborator the plan/execute core touches."""
    strict_map = strict_map or {}
    readback = readback or {}

    def _strict(loc):
        return list(strict_map.get(str(loc).upper(), []))

    def _detailed(loc):
        return list(readback.get(str(loc).upper(), []))

    def _ap(loc, pm=None):
        return (active_print_for or {}).get(str(loc).upper())

    with contextlib.ExitStack() as stack:
        stack.enter_context(patch.object(locations_db, "load_locations_list", return_value=FAKE_LOCATIONS))
        stack.enter_context(patch.object(locations_db, "get_active_printer_map", return_value=FAKE_PRINTER_MAP))
        stack.enter_context(patch.object(spoolman_api, "get_spools_at_location_detailed_strict", side_effect=_strict))
        stack.enter_context(patch.object(spoolman_api, "get_spools_at_location_detailed", side_effect=_detailed))
        stack.enter_context(patch.object(spoolman_api, "get_spool", return_value=None))
        stack.enter_context(patch.object(logic, "_active_print_info_for_location", side_effect=_ap))
        stack.enter_context(patch.object(state, "GLOBAL_BUFFER", buffer or []))
        mv = stack.enter_context(patch.object(
            logic, "perform_smart_move", return_value=(move_result or {"status": "success"})))
        yield mv


# ---------------------------------------------------------------------------
# resolve_scan — the new command
# ---------------------------------------------------------------------------

def test_resolve_scan_recognizes_bulkmove():
    assert logic.resolve_scan("CMD:BULKMOVE") == {"type": "command", "cmd": "bulkmove"}


def test_bulkmove_does_not_shadow_other_commands():
    """The ladder is substring-matched — CMD:BULKMOVE must not be swallowed by
    (or swallow) a neighbouring command."""
    assert logic.resolve_scan("CMD:DONE")["cmd"] == "done"
    assert logic.resolve_scan("CMD:CANCEL")["cmd"] == "cancel"
    assert logic.resolve_scan("CMD:EJECT")["cmd"] == "eject"
    assert logic.resolve_scan("CMD:AUDIT")["cmd"] == "audit"


# ---------------------------------------------------------------------------
# Session lifecycle via the scan dispatcher
# ---------------------------------------------------------------------------

def test_cmd_bulkmove_starts_session(client):
    r = client.post("/api/identify_scan", json={"text": "CMD:BULKMOVE"})
    assert r.get_json() == {"type": "command", "cmd": "clear"}
    assert state.BULK_MOVE_SESSION["active"] is True
    assert state.BULK_MOVE_SESSION["stage"] == "awaiting_source"


def test_rescanning_bulkmove_does_not_wipe_captured_source(client):
    """The audit 27.5 guard, cloned: a second CMD:BULKMOVE mid-session is a
    no-op, not a reset that would silently drop the armed source."""
    logic.start_bulk_move_session("PM-DB-A")
    assert state.BULK_MOVE_SESSION["stage"] == "awaiting_dest"
    r = client.post("/api/identify_scan", json={"text": "CMD:BULKMOVE"})
    assert r.get_json() == {"type": "command", "cmd": "clear"}
    assert state.BULK_MOVE_SESSION["source_id"] == "PM-DB-A"
    assert state.BULK_MOVE_SESSION["stage"] == "awaiting_dest"


def test_location_scans_capture_source_then_dest_without_moving(client):
    """The core Phase-2 flow — and the safety invariant: scanning the DEST
    computes a preview but NEVER commits."""
    with _env(strict_map={"PM-DB-A": [_spool(1), _spool(2)]}) as mv:
        client.post("/api/identify_scan", json={"text": "CMD:BULKMOVE"})
        r1 = client.post("/api/identify_scan", json={"text": "LOC:PM-DB-A"})
        assert r1.get_json() == {"type": "command", "cmd": "clear"}
        assert state.BULK_MOVE_SESSION["source_id"] == "PM-DB-A"
        assert state.BULK_MOVE_SESSION["stage"] == "awaiting_dest"

        r2 = client.post("/api/identify_scan", json={"text": "LOC:SHELF-B"})
        assert r2.get_json() == {"type": "command", "cmd": "clear"}
        assert state.BULK_MOVE_SESSION["dest_id"] == "SHELF-B"
        assert state.BULK_MOVE_SESSION["stage"] == "preview"
        # THE invariant: nothing moved on the dest scan.
        mv.assert_not_called()
        assert state.BULK_MOVE_SESSION["preview"]["movable_ids"] == [1, 2]


def test_cmd_done_commits_the_preview(client):
    with _env(strict_map={"PM-DB-A": [_spool(1), _spool(2)]}) as mv:
        client.post("/api/identify_scan", json={"text": "CMD:BULKMOVE"})
        client.post("/api/identify_scan", json={"text": "LOC:PM-DB-A"})
        client.post("/api/identify_scan", json={"text": "LOC:SHELF-B"})
        r = client.post("/api/identify_scan", json={"text": "CMD:DONE"})
    assert r.get_json() == {"type": "command", "cmd": "clear"}
    mv.assert_called_once()
    args, kwargs = mv.call_args
    assert args[0] == "SHELF-B"
    assert args[1] == [1, 2]
    assert kwargs.get("auto_deploy") is False
    # Session cleared after a successful commit.
    assert state.BULK_MOVE_SESSION["active"] is False


def test_cmd_done_before_a_dest_is_refused(client):
    with _env(strict_map={"PM-DB-A": [_spool(1)]}) as mv:
        client.post("/api/identify_scan", json={"text": "CMD:BULKMOVE"})
        client.post("/api/identify_scan", json={"text": "LOC:PM-DB-A"})
        r = client.post("/api/identify_scan", json={"text": "CMD:DONE"})
    body = r.get_json()
    assert body["type"] == "error"
    mv.assert_not_called()
    # Session survives so the user can still scan a destination.
    assert state.BULK_MOVE_SESSION["active"] is True


def test_cmd_cancel_ends_session_without_moving(client):
    with _env(strict_map={"PM-DB-A": [_spool(1)]}) as mv:
        client.post("/api/identify_scan", json={"text": "CMD:BULKMOVE"})
        client.post("/api/identify_scan", json={"text": "LOC:PM-DB-A"})
        r = client.post("/api/identify_scan", json={"text": "CMD:CANCEL"})
    assert r.get_json() == {"type": "command", "cmd": "clear"}
    assert state.BULK_MOVE_SESSION["active"] is False
    mv.assert_not_called()


def test_rescanning_a_location_at_preview_retargets_the_dest(client):
    """The user changed their mind before committing — re-scan re-targets
    rather than erroring."""
    with _env(strict_map={"PM-DB-A": [_spool(1)]}):
        client.post("/api/identify_scan", json={"text": "CMD:BULKMOVE"})
        client.post("/api/identify_scan", json={"text": "LOC:PM-DB-A"})
        client.post("/api/identify_scan", json={"text": "LOC:SHELF-B"})
        client.post("/api/identify_scan", json={"text": "LOC:CR"})
    assert state.BULK_MOVE_SESSION["dest_id"] == "CR"
    assert state.BULK_MOVE_SESSION["stage"] == "preview"


def test_spool_scan_during_session_is_rejected(client):
    with _env(strict_map={"PM-DB-A": [_spool(1)]}):
        client.post("/api/identify_scan", json={"text": "CMD:BULKMOVE"})
        r = client.post("/api/identify_scan", json={"text": "ID:42"})
    body = r.get_json()
    assert body["type"] == "error"
    assert "LOCATION" in body["msg"].upper()


def test_blocked_dest_surfaces_error_and_keeps_session(client):
    """A single-occupancy dest is refused at preview time; the session stays so
    the user can scan a different destination."""
    with _env(strict_map={"PM-DB-A": [_spool(1)]}) as mv:
        client.post("/api/identify_scan", json={"text": "CMD:BULKMOVE"})
        client.post("/api/identify_scan", json={"text": "LOC:PM-DB-A"})
        r = client.post("/api/identify_scan", json={"text": "LOC:XL-1"})
    body = r.get_json()
    assert body["type"] == "error"
    assert "single-spool" in body["msg"].lower()
    assert state.BULK_MOVE_SESSION["active"] is True
    mv.assert_not_called()


# ---------------------------------------------------------------------------
# Commit re-plans against LIVE state
# ---------------------------------------------------------------------------

def test_commit_replans_and_refuses_when_world_changed(client):
    """A spool moved / a print started between preview and commit must be
    caught: the commit re-plans instead of trusting the stored preview."""
    with _env(strict_map={"PM-DB-A": [_spool(1)]}):
        client.post("/api/identify_scan", json={"text": "CMD:BULKMOVE"})
        client.post("/api/identify_scan", json={"text": "LOC:PM-DB-A"})
        client.post("/api/identify_scan", json={"text": "LOC:SHELF-B"})
        assert state.BULK_MOVE_SESSION["preview"]["movable_ids"] == [1]

    # Now the source is EMPTY (someone moved the spool) — commit must not move.
    with _env(strict_map={"PM-DB-A": []}) as mv:
        result = logic.commit_bulk_move_session()
    assert result["success"] is True
    assert result["moved"] == 0
    mv.assert_not_called()


def test_commit_requires_confirm_on_source_active_print(client):
    ap = {"printer_name": "XL", "state": "PRINTING", "toolhead": "PM-DB-A"}
    with _env(strict_map={"PM-DB-A": [_spool(1)]}):
        client.post("/api/identify_scan", json={"text": "CMD:BULKMOVE"})
        client.post("/api/identify_scan", json={"text": "LOC:PM-DB-A"})
        client.post("/api/identify_scan", json={"text": "LOC:SHELF-B"})

    with _env(strict_map={"PM-DB-A": [_spool(1)]}, active_print_for={"PM-DB-A": ap}) as mv:
        result = logic.commit_bulk_move_session()
    assert result["require_confirm"] is True
    assert result["confirm_type"] == "active_print"
    mv.assert_not_called()
    # Session left standing so the UI can confirm + retry.
    assert state.BULK_MOVE_SESSION["active"] is True

    with _env(strict_map={"PM-DB-A": [_spool(1)]}, active_print_for={"PM-DB-A": ap}) as mv:
        result = logic.commit_bulk_move_session(confirm_active_print=True)
    assert result["success"] is True
    mv.assert_called_once()


# ---------------------------------------------------------------------------
# The session HTTP surface
# ---------------------------------------------------------------------------

def test_get_session_reports_idle(client):
    r = client.get("/api/bulk_move_session")
    assert r.get_json() == {"active": False, "stage": "idle"}


def test_post_start_with_source_jumps_to_awaiting_dest(client):
    """The Location-Manager 'Move all →' entry."""
    r = client.post("/api/bulk_move_session", json={"action": "start", "source": "pm-db-a"})
    body = r.get_json()
    assert body["success"] is True
    assert body["session"]["stage"] == "awaiting_dest"
    assert body["session"]["source_id"] == "PM-DB-A"


def test_post_set_dest_then_commit(client):
    with _env(strict_map={"PM-DB-A": [_spool(1), _spool(2)]}) as mv:
        client.post("/api/bulk_move_session", json={"action": "start", "source": "PM-DB-A"})
        r1 = client.post("/api/bulk_move_session", json={"action": "set_dest", "dest": "SHELF-B"})
        b1 = r1.get_json()
        assert b1["success"] is True
        assert b1["session"]["stage"] == "preview"
        assert b1["session"]["preview"]["stats"]["movable"] == 2
        mv.assert_not_called()          # set_dest must not move anything

        r2 = client.post("/api/bulk_move_session", json={"action": "commit"})
        b2 = r2.get_json()
    assert b2["success"] is True
    assert b2["moved"] == 2
    mv.assert_called_once()
    assert state.BULK_MOVE_SESSION["active"] is False


def test_post_cancel_clears_session(client):
    logic.start_bulk_move_session("PM-DB-A")
    r = client.post("/api/bulk_move_session", json={"action": "cancel"})
    assert r.get_json()["success"] is True
    assert state.BULK_MOVE_SESSION["active"] is False


def test_post_action_without_session_is_refused(client):
    r = client.post("/api/bulk_move_session", json={"action": "commit"})
    body = r.get_json()
    assert body["success"] is False
    assert "no bulk move session" in body["msg"].lower()


def test_post_unknown_action_refused(client):
    logic.start_bulk_move_session("PM-DB-A")
    r = client.post("/api/bulk_move_session", json={"action": "frobnicate"})
    body = r.get_json()
    assert body["success"] is False
    assert "unknown action" in body["msg"].lower()


def test_snapshot_enriches_preview_rows(client):
    """The panel renders spool tiles — the snapshot must carry display+color."""
    def _fake_get_spool(sid):
        return {"id": sid, "name": "Test"}

    with _env(strict_map={"PM-DB-A": [_spool(1), _spool(2, is_ghost=True)]}):
        with patch.object(spoolman_api, "get_spool", side_effect=_fake_get_spool), \
             patch.object(spoolman_api, "format_spool_display",
                          return_value={"text": "Sunlu PLA (Black)", "color": "000000"}):
            client.post("/api/bulk_move_session", json={"action": "start", "source": "PM-DB-A"})
            client.post("/api/bulk_move_session", json={"action": "set_dest", "dest": "SHELF-B"})
            r = client.get("/api/bulk_move_session")
    body = r.get_json()
    assert body["active"] is True
    assert body["stage"] == "preview"
    assert body["preview"]["movable"][0]["display"] == "Sunlu PLA (Black)"
    assert body["preview"]["skipped"][0]["reason"] == "deployed to a live toolhead"


# ---------------------------------------------------------------------------
# Idle watchdog
# ---------------------------------------------------------------------------

def test_idle_watchdog_cancels_stale_session():
    logic.start_bulk_move_session("PM-DB-A")
    state.BULK_MOVE_SESSION["last_activity_ts"] = time.time() - (state.BULK_MOVE_IDLE_TIMEOUT_SECONDS + 60)
    routes_state_pulse._check_bulk_move_idle_timeout()
    assert state.BULK_MOVE_SESSION["active"] is False


def test_idle_watchdog_leaves_fresh_session_alone():
    logic.start_bulk_move_session("PM-DB-A")
    routes_state_pulse._check_bulk_move_idle_timeout()
    assert state.BULK_MOVE_SESSION["active"] is True


def test_idle_watchdog_plants_timestamp_instead_of_insta_cancelling():
    """A session with no timestamp (hand-built / pre-watchdog) must get `now`
    planted, not be cancelled on the first poll."""
    state.BULK_MOVE_SESSION.update({"active": True, "stage": "awaiting_source",
                                    "last_activity_ts": 0.0})
    routes_state_pulse._check_bulk_move_idle_timeout()
    assert state.BULK_MOVE_SESSION["active"] is True
    assert state.BULK_MOVE_SESSION["last_activity_ts"] > 0


def test_logs_route_exposes_bulk_move_flag(client):
    logic.start_bulk_move_session("PM-DB-A")
    with patch.object(routes_state_pulse.config_loader, "get_api_urls",
                      return_value=("http://sm", "http://fb")), \
         patch.object(routes_state_pulse.requests, "get", side_effect=RuntimeError("offline")):
        r = client.get("/api/logs")
    assert r.get_json()["bulk_move_active"] is True


# ---------------------------------------------------------------------------
# Adversarial-review fixes (2026-08-01)
# ---------------------------------------------------------------------------

def test_partial_failure_does_not_report_success_to_the_scanner(client):
    """REVIEW FIX (high): execute_bulk_move's partial-failure return carries
    success=False but NO 'msg', so a msg-gated check let it fall through and the
    scanner was told the move succeeded. A partial failure MUST surface."""
    with _env(strict_map={"PM-DB-A": [_spool(1), _spool(2)]},
              readback={"PM-DB-A": [_spool(1)]}):     # spool 1 never left → failed
        client.post("/api/identify_scan", json={"text": "CMD:BULKMOVE"})
        client.post("/api/identify_scan", json={"text": "LOC:PM-DB-A"})
        client.post("/api/identify_scan", json={"text": "LOC:SHELF-B"})
        r = client.post("/api/identify_scan", json={"text": "CMD:DONE"})
    body = r.get_json()
    assert body["type"] == "error"
    assert "failed to move" in body["msg"].lower()


def test_double_commit_is_refused(client):
    """REVIEW FIX (med): a re-entrant commit must not run perform_smart_move
    twice (double move + a no-op undo record burying the real one)."""
    with _env(strict_map={"PM-DB-A": [_spool(1)]}):
        client.post("/api/bulk_move_session", json={"action": "start", "source": "PM-DB-A"})
        client.post("/api/bulk_move_session", json={"action": "set_dest", "dest": "SHELF-B"})
        # Simulate a commit already in flight.
        assert logic._BULK_MOVE_COMMIT_LOCK.acquire(False)
        try:
            result = logic.commit_bulk_move_session()
        finally:
            logic._BULK_MOVE_COMMIT_LOCK.release()
    assert result["success"] is False
    assert "already running" in result["msg"].lower()


def test_bulk_move_refused_while_audit_active(client):
    """REVIEW FIX (med): the audit gate runs FIRST in api_identify_scan, so a
    bulk session armed during an audit would be unreachable by any scan."""
    state.AUDIT_SESSION["active"] = True
    try:
        r = client.post("/api/identify_scan", json={"text": "CMD:BULKMOVE"})
        body = r.get_json()
        assert body["type"] == "error"
        assert "audit" in body["msg"].lower()
        assert state.BULK_MOVE_SESSION["active"] is False
        # The HTTP entry (LM button) refuses too.
        r2 = client.post("/api/bulk_move_session", json={"action": "start", "source": "PM-DB-A"})
        assert r2.get_json()["success"] is False
    finally:
        state.reset_audit()


def test_audit_refused_while_bulk_move_armed(client):
    """REVIEW FIX (med): the reverse direction — an audit started over an armed
    bulk move would swallow the next location scan as a DESTINATION on end."""
    logic.start_bulk_move_session("PM-DB-A")
    r = client.post("/api/identify_scan", json={"text": "CMD:AUDIT"})
    body = r.get_json()
    assert body["type"] == "error"
    assert "bulk move" in body["msg"].lower()
    assert state.AUDIT_SESSION["active"] is False


def test_start_refuses_to_silently_replace_an_armed_session(client):
    """REVIEW FIX (med): the scan path's 27.5 no-op guard had no HTTP twin, so a
    second 'Move all →' silently re-armed a DIFFERENT source."""
    client.post("/api/bulk_move_session", json={"action": "start", "source": "PM-DB-A"})
    r = client.post("/api/bulk_move_session", json={"action": "start", "source": "CR"})
    body = r.get_json()
    assert body["success"] is False
    assert body["already_active"] is True
    assert state.BULK_MOVE_SESSION["source_id"] == "PM-DB-A"   # unchanged
    # An explicit replace DOES re-arm.
    r2 = client.post("/api/bulk_move_session",
                     json={"action": "start", "source": "CR", "replace": True})
    assert r2.get_json()["success"] is True
    assert state.BULK_MOVE_SESSION["source_id"] == "CR"


def test_logs_exposes_stage_so_other_tabs_paint_correctly(client):
    """REVIEW FIX (high): without the stage on the heartbeat a reloaded tab
    painted 'idle' over a live session, turning the deck button into a
    disguised Cancel."""
    logic.start_bulk_move_session("PM-DB-A")
    with patch.object(routes_state_pulse.config_loader, "get_api_urls",
                      return_value=("http://sm", "http://fb")), \
         patch.object(routes_state_pulse.requests, "get", side_effect=RuntimeError("offline")):
        d = client.get("/api/logs").get_json()
    assert d["bulk_move_active"] is True
    assert d["bulk_move_stage"] == "awaiting_dest"


def test_snapshot_rows_carry_color_direction(client):
    """The preview swatch renders via makeSwatchHtml, which needs the direction
    to draw a multi-colour spool's gradient."""
    with _env(strict_map={"PM-DB-A": [_spool(1)]}):
        with patch.object(spoolman_api, "get_spool", return_value={"id": 1}), \
             patch.object(spoolman_api, "format_spool_display",
                          return_value={"text": "Dual", "color": "ff0000,0000ff",
                                        "color_direction": "coaxial"}):
            client.post("/api/bulk_move_session", json={"action": "start", "source": "PM-DB-A"})
            client.post("/api/bulk_move_session", json={"action": "set_dest", "dest": "SHELF-B"})
            body = client.get("/api/bulk_move_session").get_json()
    row = body["preview"]["movable"][0]
    assert row["color"] == "ff0000,0000ff"
    assert row["color_direction"] == "coaxial"


# ---------------------------------------------------------------------------
# Shared-core parity: the session and the stateless endpoint agree
# ---------------------------------------------------------------------------

def test_session_and_endpoint_share_one_plan(client):
    """Both entries must compute the SAME movable/skipped set — a preview that
    can't disagree with the commit."""
    contents = [_spool(1), _spool(2, is_ghost=True), _spool(3)]
    with _env(strict_map={"PM-DB-A": contents}):
        endpoint_plan = logic.plan_bulk_move("PM-DB-A", "SHELF-B")
        client.post("/api/bulk_move_session", json={"action": "start", "source": "PM-DB-A"})
        client.post("/api/bulk_move_session", json={"action": "set_dest", "dest": "SHELF-B"})
        session_plan = state.BULK_MOVE_SESSION["preview"]
    assert endpoint_plan["movable_ids"] == session_plan["movable_ids"] == [1, 3]
    assert endpoint_plan["skipped"] == session_plan["skipped"]
