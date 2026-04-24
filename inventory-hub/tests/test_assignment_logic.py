"""
Unit tests for the Phase 1 slot-QR assignment branch in app.api_identify_scan.

Exercises /api/identify_scan with mocked Spoolman + Filabridge so we can assert
on Activity Log output, buffer mutation, and the arguments handed to
logic.perform_smart_move. Runs on the host without a live Docker container.
"""
from __future__ import annotations

import os
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import app as app_module  # noqa: E402
import state  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures local to this module
# ---------------------------------------------------------------------------

@pytest.fixture
def client():
    app_module.app.config["TESTING"] = True
    return app_module.app.test_client()


@pytest.fixture(autouse=True)
def isolate_state():
    """Reset GLOBAL_BUFFER and RECENT_LOGS around each test."""
    prior_buffer = list(state.GLOBAL_BUFFER)
    prior_logs = list(state.RECENT_LOGS)
    state.GLOBAL_BUFFER = []
    state.RECENT_LOGS = []
    try:
        yield
    finally:
        state.GLOBAL_BUFFER = prior_buffer
        state.RECENT_LOGS = prior_logs


@pytest.fixture
def fake_locations():
    """A minimal location DB returned by locations_db.load_locations_list()."""
    return [
        {
            "LocationID": "LR-MDB-1",
            "Type": "Dryer Box",
            "Max Spools": "4",
            "Name": "Living Room MDB",
        },
        {
            "LocationID": "CORE1-M1",
            "Type": "MMU Slot",
            "Max Spools": "1",
            "Name": "Core One MMU Slot 1",
        },
        {
            "LocationID": "CR",
            "Type": "Room",
            "Max Spools": "0",
            "Name": "Computer Room",
        },
    ]


def _last_log_entries(n=3):
    return list(state.RECENT_LOGS)[-n:]


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

def test_assignment_happy_path_moves_spool_and_clears_buffer(client, fake_locations):
    state.GLOBAL_BUFFER = [{"id": 42, "display": "Test Spool", "color": "ff0000"}]

    with patch.object(app_module.locations_db, "load_locations_list", return_value=fake_locations), \
         patch.object(app_module.logic, "perform_smart_move", return_value={"status": "success"}) as mv:
        resp = client.post("/api/identify_scan", json={"text": "LOC:LR-MDB-1:SLOT:2", "source": "barcode"})

    assert resp.status_code == 200
    body = resp.get_json()
    assert body["type"] == "assignment"
    assert body["action"] == "assignment_done"
    assert body["location"] == "LR-MDB-1"
    assert body["slot"] == "2"
    assert body["moved"] == 42
    assert body["remaining_buffer"] == 0
    mv.assert_called_once_with("LR-MDB-1", [42], target_slot="2", origin="slot_qr_scan", confirm_active_print=False)
    assert state.GLOBAL_BUFFER == []
    assert any("Spool #42" in e["msg"] for e in _last_log_entries())


def test_assignment_partial_keeps_remaining_buffer(client, fake_locations):
    state.GLOBAL_BUFFER = [
        {"id": 42, "display": "First"},
        {"id": 43, "display": "Second"},
    ]
    with patch.object(app_module.locations_db, "load_locations_list", return_value=fake_locations), \
         patch.object(app_module.logic, "perform_smart_move", return_value={"status": "success"}):
        resp = client.post("/api/identify_scan", json={"text": "LOC:LR-MDB-1:SLOT:1", "source": "barcode"})

    body = resp.get_json()
    assert body["action"] == "assignment_partial"
    assert body["remaining_buffer"] == 1
    assert len(state.GLOBAL_BUFFER) == 1
    assert state.GLOBAL_BUFFER[0]["id"] == 43


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------

def test_assignment_no_buffer_returns_action_code(client, fake_locations):
    """No backend log is emitted — the frontend treats this as a pickup
    request and emits its own log entry on success."""
    state.GLOBAL_BUFFER = []
    log_count_before = len(state.RECENT_LOGS)
    with patch.object(app_module.locations_db, "load_locations_list", return_value=fake_locations), \
         patch.object(app_module.logic, "perform_smart_move") as mv:
        resp = client.post("/api/identify_scan", json={"text": "LOC:LR-MDB-1:SLOT:2", "source": "barcode"})

    assert resp.status_code == 200
    body = resp.get_json()
    assert body["action"] == "assignment_no_buffer"
    assert body["location"] == "LR-MDB-1"
    assert body["slot"] == "2"
    mv.assert_not_called()
    # No backend log emitted for this case.
    assert len(state.RECENT_LOGS) == log_count_before


def test_assignment_bad_target_type_rejects(client, fake_locations):
    state.GLOBAL_BUFFER = [{"id": 7}]
    with patch.object(app_module.locations_db, "load_locations_list", return_value=fake_locations), \
         patch.object(app_module.logic, "perform_smart_move") as mv:
        # CR is Type="Room" — not a container.
        resp = client.post("/api/identify_scan", json={"text": "LOC:CR:SLOT:1", "source": "barcode"})

    assert resp.status_code == 400
    body = resp.get_json()
    assert body["action"] == "assignment_bad_target"
    assert body["location"] == "CR"
    mv.assert_not_called()
    # Buffer unchanged.
    assert len(state.GLOBAL_BUFFER) == 1
    assert any(e["type"] == "ERROR" for e in _last_log_entries())


def test_assignment_missing_target_rejects(client, fake_locations):
    state.GLOBAL_BUFFER = [{"id": 7}]
    with patch.object(app_module.locations_db, "load_locations_list", return_value=fake_locations), \
         patch.object(app_module.logic, "perform_smart_move") as mv:
        resp = client.post("/api/identify_scan", json={"text": "LOC:NOT-A-PLACE:SLOT:1", "source": "barcode"})

    assert resp.status_code == 400
    body = resp.get_json()
    assert body["action"] == "assignment_bad_target"
    assert body["found_type"] == "missing"
    mv.assert_not_called()


def test_assignment_slot_out_of_range_rejects(client, fake_locations):
    state.GLOBAL_BUFFER = [{"id": 7}]
    with patch.object(app_module.locations_db, "load_locations_list", return_value=fake_locations), \
         patch.object(app_module.logic, "perform_smart_move") as mv:
        # LR-MDB-1 has Max Spools 4 → slot 9 is invalid.
        resp = client.post("/api/identify_scan", json={"text": "LOC:LR-MDB-1:SLOT:9", "source": "barcode"})

    assert resp.status_code == 400
    body = resp.get_json()
    assert body["action"] == "assignment_bad_slot"
    assert body["max_slots"] == 4
    mv.assert_not_called()


def test_assignment_slot_zero_rejects(client, fake_locations):
    state.GLOBAL_BUFFER = [{"id": 7}]
    with patch.object(app_module.locations_db, "load_locations_list", return_value=fake_locations), \
         patch.object(app_module.logic, "perform_smart_move") as mv:
        resp = client.post("/api/identify_scan", json={"text": "LOC:LR-MDB-1:SLOT:0", "source": "barcode"})

    assert resp.status_code == 400
    body = resp.get_json()
    assert body["action"] == "assignment_bad_slot"
    mv.assert_not_called()


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

def test_assignment_lowercase_target_normalizes_to_upper(client, fake_locations):
    """Scan text like `loc:lr-mdb-1:slot:2` should still hit the right target."""
    state.GLOBAL_BUFFER = [{"id": 42, "display": "Test"}]
    with patch.object(app_module.locations_db, "load_locations_list", return_value=fake_locations), \
         patch.object(app_module.logic, "perform_smart_move", return_value={"status": "success"}) as mv:
        resp = client.post("/api/identify_scan", json={"text": "loc:lr-mdb-1:slot:2", "source": "barcode"})

    assert resp.status_code == 200
    body = resp.get_json()
    assert body["action"] == "assignment_done"
    assert body["location"] == "LR-MDB-1"
    # First positional arg is the normalized target.
    args, kwargs = mv.call_args
    assert args[0] == "LR-MDB-1"


def test_assignment_non_spool_items_in_buffer_are_skipped(client, fake_locations):
    """Filament or command entries in the buffer should not be moved as spools."""
    state.GLOBAL_BUFFER = [
        {"type": "filament", "display": "Shared Filament"},  # no 'id'
        {"id": 99, "display": "Real Spool"},
    ]
    with patch.object(app_module.locations_db, "load_locations_list", return_value=fake_locations), \
         patch.object(app_module.logic, "perform_smart_move", return_value={"status": "success"}) as mv:
        resp = client.post("/api/identify_scan", json={"text": "LOC:LR-MDB-1:SLOT:1", "source": "barcode"})

    body = resp.get_json()
    assert body["action"] == "assignment_partial"
    assert body["moved"] == 99
    mv.assert_called_once_with("LR-MDB-1", [99], target_slot="1", origin="slot_qr_scan", confirm_active_print=False)
    # Non-spool item stays.
    assert any(e.get("type") == "filament" for e in state.GLOBAL_BUFFER)


def test_buffer_clear_endpoint(client):
    state.GLOBAL_BUFFER = [{"id": 1}, {"id": 2}]
    resp = client.post("/api/buffer/clear")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["success"] is True
    assert body["buffer"] == []
    assert state.GLOBAL_BUFFER == []


# ---------------------------------------------------------------------------
# Resolve-scan contract check
# ---------------------------------------------------------------------------

def test_resolve_scan_still_returns_assignment_type():
    """Guard against regressions that re-break the assignment parse."""
    from logic import resolve_scan
    assert resolve_scan("LOC:LR-MDB-1:SLOT:2") == {
        "type": "assignment",
        "location": "LR-MDB-1",
        "slot": "2",
    }
