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
import threading
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
    # A second BOUNDED box, so a capacity block can be exercised end to end.
    {"LocationID": "PM-DB-B", "Type": "Dryer Box", "Max Spools": "4", "Name": "Box B"},
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
    """Every test starts and ends with a cleared session (it's module state).

    Also guards `_BULK_MOVE_COMMIT_LOCK`, which several tests hand-acquire to
    simulate an in-flight commit. A leak there is silent and cross-contaminating:
    every later test that commits/cancels/re-targets takes the refusal branch and
    fails with an "already running"/"in progress" message that points at the
    feature instead of at the test that leaked. Assert on the way IN so the blame
    lands on the right test; force-reset on the way OUT so one leak doesn't cascade.
    """
    assert not logic._BULK_MOVE_COMMIT_LOCK.locked(), (
        "the bulk-move commit lock was left held by an earlier test")
    state.reset_bulk_move()
    prior_logs = list(state.RECENT_LOGS)
    state.RECENT_LOGS = []
    try:
        yield
    finally:
        if logic._BULK_MOVE_COMMIT_LOCK.locked():
            logic._BULK_MOVE_COMMIT_LOCK = threading.Lock()
        state.reset_bulk_move()
        state.RECENT_LOGS = prior_logs


def _spool(sid, location="PM-DB-A", is_ghost=False, archived=False,
           display=None, color="ffffff", color_direction="longitudinal",
           slot="", remaining_weight=None):
    """A detailed-item dict shaped like get_spools_at_location_detailed emits.

    Phase 3 leans on the DISPLAY fields (`display`/`color`/`color_direction`/
    `slot`/`remaining_weight`): the plan now caches them so the panel poll needs
    zero Spoolman I/O, so the tests must be able to vary them here.
    """
    return {"id": sid, "location": location, "is_ghost": is_ghost,
            "archived": archived, "slot": slot,
            "display": display or f"#{sid}", "color": color,
            "color_direction": color_direction,
            "remaining_weight": remaining_weight}


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
    # REVIEW FIX: a BLOCKED plan must NOT advance to 'preview' — the stage rides
    # the heartbeat, so that turned the deck tile green "COMMIT" (with a CMD:DONE
    # QR) for a move that can never run. Stay prompting for a valid destination.
    assert state.BULK_MOVE_SESSION["stage"] == "awaiting_dest"


@pytest.mark.parametrize("dest,expect", [
    ("XL-1", "awaiting_dest"),        # single-occupancy → blocked
    ("NOPE-404", "awaiting_dest"),    # unknown dest → blocked
    ("SHELF-B", "preview"),           # valid → advances
])
def test_stage_only_advances_for_a_committable_plan(client, dest, expect):
    with _env(strict_map={"PM-DB-A": [_spool(1)]}):
        client.post("/api/bulk_move_session", json={"action": "start", "source": "PM-DB-A"})
        client.post("/api/bulk_move_session", json={"action": "set_dest", "dest": dest})
    assert state.BULK_MOVE_SESSION["stage"] == expect


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
    """The panel renders spool tiles — the snapshot must carry the display data
    for BOTH lists, taken from the rows plan_bulk_move already read."""
    with _env(strict_map={"PM-DB-A": [
            _spool(1, display="Sunlu PLA (Black)", color="000000",
                   slot="2", remaining_weight=812.4),
            _spool(2, is_ghost=True, display="Prusament Galaxy Black")]}):
        client.post("/api/bulk_move_session", json={"action": "start", "source": "PM-DB-A"})
        client.post("/api/bulk_move_session", json={"action": "set_dest", "dest": "SHELF-B"})
        r = client.get("/api/bulk_move_session")
    body = r.get_json()
    assert body["active"] is True
    assert body["stage"] == "preview"
    mv = body["preview"]["movable"][0]
    assert mv["display"] == "Sunlu PLA (Black)"
    assert mv["color"] == "000000"
    # Phase 3 tiles show weight + slot, so both must survive into the payload.
    assert mv["slot"] == "2"
    assert mv["remaining_weight"] == 812.4
    sk = body["preview"]["skipped"][0]
    assert sk["reason"] == "deployed to a live toolhead"
    assert sk["display"] == "Prusament Galaxy Black"


def test_snapshot_does_zero_spoolman_io(client):
    """PHASE 3 — the panel polls this every 2 s for as long as it is open.

    Phase 2's snapshot re-fetched EVERY movable and EVERY skipped row one id at
    a time (`get_spool` per row) on every single tick, unbounded in the source
    size and multiplied by each open tab — the same synchronous-fan-out class as
    the L3 slot-assign latency memo. The plan already holds that data, so the
    snapshot must be pure formatting.
    """
    with _env(strict_map={"PM-DB-A": [_spool(i) for i in range(1, 8)]}):
        client.post("/api/bulk_move_session", json={"action": "start", "source": "PM-DB-A"})
        client.post("/api/bulk_move_session", json={"action": "set_dest", "dest": "SHELF-B"})
        # Assert at the TRANSPORT boundary, not just on three named readers:
        # patching only known functions would still pass if the snapshot grew a
        # call to some OTHER spoolman_api helper (or an inline requests.get).
        # Nothing may leave the process.
        with patch.object(spoolman_api, "requests") as rq, \
             patch.object(spoolman_api, "get_spool") as gs:
            for _ in range(5):
                body = client.get("/api/bulk_move_session").get_json()
            assert rq.get.call_count == 0, "the panel poll must not read Spoolman"
            assert rq.post.call_count == 0
            assert rq.patch.call_count == 0
            assert gs.call_count == 0          # readable secondary assertion
    assert len(body["preview"]["movable"]) == 7


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


def test_require_confirm_plan_still_carries_the_movable_set(client):
    """REVIEW FIX: the active-print confirm return dropped movable_ids, so the
    panel rendered '0 will move' and DISABLED Commit — the user could see the
    warning but had no way to act on it. The confirm path must stay reachable."""
    ap = {"printer_name": "XL", "state": "PRINTING", "toolhead": "PM-DB-A"}
    with _env(strict_map={"PM-DB-A": [_spool(1), _spool(2)]},
              active_print_for={"PM-DB-A": ap}):
        plan = logic.plan_bulk_move("PM-DB-A", "SHELF-B")
    assert plan["require_confirm"] is True
    assert plan["movable_ids"] == [1, 2]      # not dropped


def test_snapshot_rows_carry_color_direction(client):
    """The preview swatch renders via makeSwatchHtml, which needs the direction
    to draw a multi-colour spool's gradient."""
    with _env(strict_map={"PM-DB-A": [
            _spool(1, display="Dual", color="ff0000,0000ff", color_direction="coaxial")]}):
        client.post("/api/bulk_move_session", json={"action": "start", "source": "PM-DB-A"})
        client.post("/api/bulk_move_session", json={"action": "set_dest", "dest": "SHELF-B"})
        body = client.get("/api/bulk_move_session").get_json()
    row = body["preview"]["movable"][0]
    assert row["color"] == "ff0000,0000ff"
    assert row["color_direction"] == "coaxial"


def test_blocked_plan_still_reports_the_spools_it_refused(client):
    """PHASE 3 — a capacity block renders the block banner AND the tiles it
    refused, so "2 free of 4, source has 5" is actionable without another
    screen. The commit path must still see an EMPTY movable_ids: `would_move_ids`
    is display-only."""
    with _env(strict_map={"PM-DB-A": [_spool(i) for i in range(1, 6)],
                          "PM-DB-B": [_spool(90), _spool(91)]}):
        plan = logic.plan_bulk_move("PM-DB-A", "PM-DB-B")
        client.post("/api/bulk_move_session", json={"action": "start", "source": "PM-DB-A"})
        client.post("/api/bulk_move_session", json={"action": "set_dest", "dest": "PM-DB-B"})
        body = client.get("/api/bulk_move_session").get_json()
    assert plan["blocked_reason"] == "capacity"
    assert plan["movable_ids"] == []             # nothing the commit could act on
    assert plan["would_move_ids"] == [1, 2, 3, 4, 5]
    assert body["preview"]["ok"] is False
    assert len(body["preview"]["movable"]) == 5  # ...but the panel can show them
    # A blocked plan must NOT advance the stage (the deck tile would go green).
    assert body["stage"] == "awaiting_dest"


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


# ---------------------------------------------------------------------------
# L298 Phase 3 — deferred-findings fixes
# ---------------------------------------------------------------------------

def test_lm_button_start_then_scanned_dest_then_cmd_done(client):
    """The MIXED entry path had no coverage: the Location-Manager button arms the
    session over HTTP, then the user SCANS the destination and CMD:DONE.

    Every prior end-to-end test drove either all-HTTP or all-scan, so nothing
    pinned the composite — which is exactly the path a real bulk move takes when
    Derek starts it at the screen and finishes it at the shelf with a scanner.
    """
    with _env(strict_map={"PM-DB-A": [_spool(1), _spool(2)]}) as mv:
        r = client.post("/api/bulk_move_session",
                        json={"action": "start", "source": "PM-DB-A"})
        assert r.get_json()["session"]["stage"] == "awaiting_dest"

        # A scanned destination stages a preview — and moves NOTHING.
        r = client.post("/api/identify_scan", json={"text": "LOC:SHELF-B"})
        assert r.get_json() == {"type": "command", "cmd": "clear"}
        assert state.BULK_MOVE_SESSION["stage"] == "preview"
        assert state.BULK_MOVE_SESSION["dest_id"] == "SHELF-B"
        mv.assert_not_called()

        # ...then the explicit CMD:DONE commits exactly once.
        client.post("/api/identify_scan", json={"text": "CMD:DONE"})
        mv.assert_called_once()
        args, kwargs = mv.call_args
        assert args[0] == "SHELF-B"
        assert sorted(args[1]) == [1, 2]
        assert kwargs["auto_deploy"] is False
    assert state.BULK_MOVE_SESSION["active"] is False


def test_cancel_during_inflight_commit_is_refused(client):
    """A cancel racing a running commit CANNOT stop it, so it must not claim to.

    commit_bulk_move_session captures source/dest into locals before calling
    perform_smart_move, so resetting the session dict has zero effect on the
    in-flight move: every spool keeps being written and the aggregate SUCCESS
    line still fires — while the cancelling client was told "nothing moved".
    Holding the commit lock here simulates that window.
    """
    logic.start_bulk_move_session("PM-DB-A")
    assert logic._BULK_MOVE_COMMIT_LOCK.acquire(False)   # stand in for a commit
    try:
        r = client.post("/api/bulk_move_session", json={"action": "cancel"})
        body = r.get_json()
        assert body["success"] is False
        assert body["commit_in_flight"] is True
        assert "in progress" in body["msg"]
        # The session is NOT wiped — the commit still owns it.
        assert state.BULK_MOVE_SESSION["active"] is True
    finally:
        logic._BULK_MOVE_COMMIT_LOCK.release()

    # With the lock free again, the same cancel succeeds.
    r = client.post("/api/bulk_move_session", json={"action": "cancel"})
    assert r.get_json()["success"] is True
    assert state.BULK_MOVE_SESSION["active"] is False


def test_cmd_cancel_scan_during_inflight_commit_is_refused(client):
    """Same guard on the SCANNER path — CMD:CANCEL routes through the same
    primitive, so it can't bypass the lock the HTTP cancel respects."""
    logic.start_bulk_move_session("PM-DB-A")
    assert logic._BULK_MOVE_COMMIT_LOCK.acquire(False)
    try:
        res = logic.process_bulk_move_scan({"type": "command", "cmd": "cancel"})
        assert res["status"] == "error"
        assert "in progress" in res["msg"]
        assert state.BULK_MOVE_SESSION["active"] is True
    finally:
        logic._BULK_MOVE_COMMIT_LOCK.release()


# ---------------------------------------------------------------------------
# L298 Phase 3 — adversarial-review fixes (2026-08-02)
# ---------------------------------------------------------------------------

def test_commit_that_reblocks_demotes_the_stage(client):
    """A commit RE-PLANS against live state. When that re-plan comes back
    BLOCKED (a spool landed in the dest between preview and commit, or a
    transient Spoolman blip), the session must fall back to awaiting_dest.

    Leaving it at 'preview' made the deck tile keep painting a green COMMIT with
    a live CMD:DONE QR for a move every retry refused — and the deck is the
    surface Derek is looking at, at the shelf, with the panel hidden.
    """
    contents = {"PM-DB-A": [_spool(i) for i in range(1, 4)], "PM-DB-B": []}
    with _env(strict_map=contents):
        client.post("/api/bulk_move_session", json={"action": "start", "source": "PM-DB-A"})
        client.post("/api/bulk_move_session", json={"action": "set_dest", "dest": "PM-DB-B"})
        assert state.BULK_MOVE_SESSION["stage"] == "preview"

        # Someone fills the destination box before the commit lands.
        contents["PM-DB-B"] = [_spool(90), _spool(91), _spool(92), _spool(93)]
        r = client.post("/api/bulk_move_session", json={"action": "commit"})

    body = r.get_json()
    assert body["success"] is False
    assert body["blocked_reason"] == "capacity"
    assert state.BULK_MOVE_SESSION["active"] is True          # still armed
    assert state.BULK_MOVE_SESSION["stage"] == "awaiting_dest"  # ...but NOT committable
    assert body["session"]["stage"] == "awaiting_dest"


def test_dest_cannot_be_retargeted_while_a_commit_is_running(client):
    """The commit reads sess['dest_id'] INSIDE the lock, but the dest WRITERS
    had none — so a stray destination scan landing between the user's Commit
    click and the commit thread's read re-targeted the batch, moving spools to a
    location the user never previewed. A destructive op must only ever commit
    the destination that was on screen."""
    logic.start_bulk_move_session("PM-DB-A")
    state.BULK_MOVE_SESSION["dest_id"] = "SHELF-B"
    assert logic._BULK_MOVE_COMMIT_LOCK.acquire(False)   # stand in for a commit
    try:
        r = client.post("/api/bulk_move_session",
                        json={"action": "set_dest", "dest": "SHELF-C"})
        body = r.get_json()
        assert body["success"] is False
        assert "commit is in progress" in body["msg"]
        assert state.BULK_MOVE_SESSION["dest_id"] == "SHELF-B"   # unchanged

        # The SCAN path routes through the same setter, so it can't bypass it.
        res = logic.process_bulk_move_scan({"type": "location", "id": "SHELF-C"})
        assert res["status"] == "error"
        assert state.BULK_MOVE_SESSION["dest_id"] == "SHELF-B"
    finally:
        logic._BULK_MOVE_COMMIT_LOCK.release()


def test_idle_watchdog_does_not_wipe_a_session_mid_commit(client):
    """The watchdog rides the ~5s /api/logs heartbeat, so a long O(N) commit can
    cross the idle deadline while it runs. Resetting there would log
    'auto-cancelled — no spools moved' over a move that IS moving spools — the
    same lie the cancel guard exists to prevent."""
    logic.start_bulk_move_session("PM-DB-A")
    state.BULK_MOVE_SESSION["last_activity_ts"] = 1.0    # long past the deadline
    assert logic._BULK_MOVE_COMMIT_LOCK.acquire(False)
    try:
        routes_state_pulse._check_bulk_move_idle_timeout()
        assert state.BULK_MOVE_SESSION["active"] is True   # NOT wiped
    finally:
        logic._BULK_MOVE_COMMIT_LOCK.release()

    # With no commit running, the same stale session IS reaped.
    routes_state_pulse._check_bulk_move_idle_timeout()
    assert state.BULK_MOVE_SESSION["active"] is False


def test_plan_row_cache_matches_what_the_real_location_reader_emits(client):
    """CONTRACT: the whole zero-I/O snapshot rests on plan['rows'] being built
    from `_build_location_match`'s output. Every test above hand-rolls a row
    dict, so a rename in spoolman_api (say `display` -> `label`) would leave the
    mocks green while the live panel rendered '#123' and grey swatches for every
    spool. Pin it against the REAL builder."""
    raw = {
        "id": 4242,
        "location": "PM-DB-A",
        "archived": False,
        "remaining_weight": 640.5,
        "initial_weight": 1000,
        "extra": {},
        "filament": {"name": "Galaxy Black", "vendor": {"name": "Prusament"},
                     "color_hex": "2b2b3a", "material": "PLA"},
    }
    row = spoolman_api._build_location_match(raw, "PM-DB-A", False)
    assert row is not None
    # These are exactly the keys plan_bulk_move copies into plan['rows'].
    for key in ("id", "display", "color", "color_direction", "slot", "remaining_weight"):
        assert key in row, f"_build_location_match no longer emits '{key}' — plan['rows'] would go blank"
