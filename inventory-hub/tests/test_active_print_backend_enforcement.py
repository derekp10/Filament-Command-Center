"""
Backend-level active-print safety net.

Verifies the shared `logic._active_print_info_for_location` helper and its
integration into every spool-move path so no avenue can bypass the check:

  - perform_smart_move (destination toolhead)
  - perform_smart_eject (source toolhead)
  - perform_force_unassign (source toolhead)
  - /api/manage_contents (add / remove / force_unassign / clear_location)
  - /api/smart_move
  - /api/identify_scan (LOC:X:SLOT:Y assignment branch)

Each endpoint must short-circuit with a requires_confirm response when the
affected toolhead is active, unless the caller passes confirm_active_print=True.
"""
from __future__ import annotations

import os
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import app as app_module  # noqa: E402
import logic  # noqa: E402
import state  # noqa: E402


FAKE_PRINTER_MAP = {
    "XL-1": {"printer_name": "XL", "position": 0},
    "CORE1-M0": {"printer_name": "Core One", "position": 0},
}
FAKE_LOCATIONS = [
    {"LocationID": "XL-1", "Type": "Tool Head", "Max Spools": "1", "Name": "XL-1"},
    {"LocationID": "CORE1-M0", "Type": "Tool Head", "Max Spools": "1", "Name": "M0"},
    {"LocationID": "LR-MDB-1", "Type": "Dryer Box", "Max Spools": "4", "Name": "LR MDB"},
    {"LocationID": "CR", "Type": "Room", "Max Spools": "0", "Name": "Computer Room"},
]


@pytest.fixture
def client():
    app_module.app.config["TESTING"] = True
    return app_module.app.test_client()


@pytest.fixture(autouse=True)
def isolate_state():
    prior_buffer = list(state.GLOBAL_BUFFER)
    prior_logs = list(state.RECENT_LOGS)
    state.GLOBAL_BUFFER = []
    state.RECENT_LOGS = []
    try:
        yield
    finally:
        state.GLOBAL_BUFFER = prior_buffer
        state.RECENT_LOGS = prior_logs


# ---------------------------------------------------------------------------
# _active_print_info_for_location: the shared helper.
# ---------------------------------------------------------------------------

def test_helper_returns_none_for_non_toolhead():
    """Dryer boxes and rooms are never active-print targets."""
    with patch.object(logic.config_loader, "load_config", return_value={"printer_map": FAKE_PRINTER_MAP}):
        assert logic._active_print_info_for_location("LR-MDB-1") is None
        assert logic._active_print_info_for_location("CR") is None
        assert logic._active_print_info_for_location("") is None
        assert logic._active_print_info_for_location(None) is None


def test_helper_returns_none_when_printer_idle():
    """Toolhead is in printer_map but PrusaLink says IDLE → no warning."""
    with patch.object(logic.config_loader, "load_config", return_value={"printer_map": FAKE_PRINTER_MAP}), \
         patch.object(logic.config_loader, "get_api_urls", return_value=("http://sm", "http://fb")), \
         patch("prusalink_api.get_printer_state", return_value={"state": "IDLE", "is_active": False}):
        assert logic._active_print_info_for_location("XL-1") is None


def test_helper_returns_info_when_printer_active():
    with patch.object(logic.config_loader, "load_config", return_value={"printer_map": FAKE_PRINTER_MAP}), \
         patch.object(logic.config_loader, "get_api_urls", return_value=("http://sm", "http://fb")), \
         patch("prusalink_api.get_printer_state", return_value={"state": "PRINTING", "is_active": True}):
        info = logic._active_print_info_for_location("XL-1")
    assert info == {"toolhead": "XL-1", "printer_name": "XL", "state": "PRINTING"}


def test_helper_returns_none_on_probe_exception():
    """If PrusaLink raises, fail open — never block moves because the
    printer's API hiccupped."""
    with patch.object(logic.config_loader, "load_config", return_value={"printer_map": FAKE_PRINTER_MAP}), \
         patch.object(logic.config_loader, "get_api_urls", return_value=("http://sm", "http://fb")), \
         patch("prusalink_api.get_printer_state", side_effect=RuntimeError("boom")):
        assert logic._active_print_info_for_location("XL-1") is None


# ---------------------------------------------------------------------------
# /api/manage_contents: add/remove/force_unassign/clear_location.
# ---------------------------------------------------------------------------

def test_manage_contents_add_returns_requires_confirm_for_active_toolhead(client):
    """POST manage_contents add → if destination is active, bail pre-move."""
    with patch.object(logic.locations_db, "load_locations_list", return_value=FAKE_LOCATIONS), \
         patch.object(logic.config_loader, "load_config", return_value={"printer_map": FAKE_PRINTER_MAP}), \
         patch.object(logic.config_loader, "get_api_urls", return_value=("http://sm", "http://fb")), \
         patch("prusalink_api.get_printer_state", return_value={"state": "PRINTING", "is_active": True}), \
         patch.object(logic, "resolve_scan", return_value={"type": "spool", "id": 42}), \
         patch.object(app_module.spoolman_api, "update_spool") as upd:
        r = client.post("/api/manage_contents", json={
            "action": "add",
            "location": "XL-1",
            "spool_id": "ID:42",
            "origin": "buffer",
        })
    body = r.get_json()
    assert body.get("status") == "requires_confirm"
    assert body.get("confirm_type") == "active_print"
    assert body["active_print"]["printer_name"] == "XL"
    assert body["active_print"]["state"] == "PRINTING"
    # update_spool must NOT have been called — we bailed before any write.
    upd.assert_not_called()


def test_manage_contents_add_proceeds_when_confirm_active_print_true(client):
    """Same request with confirm_active_print=True should flow through."""
    with patch.object(logic.locations_db, "load_locations_list", return_value=FAKE_LOCATIONS), \
         patch.object(logic.config_loader, "load_config", return_value={"printer_map": FAKE_PRINTER_MAP}), \
         patch.object(logic.config_loader, "get_api_urls", return_value=("http://sm", "http://fb")), \
         patch("prusalink_api.get_printer_state", return_value={"state": "PRINTING", "is_active": True}), \
         patch.object(logic, "resolve_scan", return_value={"type": "spool", "id": 42}), \
         patch.object(logic, "perform_smart_move", return_value={"status": "success"}) as mv:
        r = client.post("/api/manage_contents", json={
            "action": "add",
            "location": "XL-1",
            "spool_id": "ID:42",
            "origin": "buffer",
            "confirm_active_print": True,
        })
    assert r.status_code == 200
    assert r.get_json() == {"status": "success"}
    # perform_smart_move received the opt-in flag.
    _, kwargs = mv.call_args
    assert kwargs.get("confirm_active_print") is True


def test_manage_contents_remove_returns_requires_confirm_for_active_source(client):
    """Eject from an active-toolhead source should require confirmation."""
    with patch.object(logic.config_loader, "load_config", return_value={"printer_map": FAKE_PRINTER_MAP}), \
         patch.object(logic.config_loader, "get_api_urls", return_value=("http://sm", "http://fb")), \
         patch("prusalink_api.get_printer_state", return_value={"state": "PRINTING", "is_active": True}), \
         patch.object(app_module.spoolman_api, "get_spool",
                      return_value={"id": 42, "location": "XL-1", "extra": {}}), \
         patch.object(app_module.spoolman_api, "update_spool") as upd:
        r = client.post("/api/manage_contents", json={
            "action": "remove",
            "spool_id": "42",
        })
    body = r.get_json()
    assert body["success"] is False
    assert body["require_confirm"] is True
    assert body["confirm_type"] == "active_print"
    assert body["active_print"]["state"] == "PRINTING"
    upd.assert_not_called()


def test_manage_contents_force_unassign_returns_requires_confirm_for_active_source(client):
    with patch.object(logic.config_loader, "load_config", return_value={"printer_map": FAKE_PRINTER_MAP}), \
         patch.object(logic.config_loader, "get_api_urls", return_value=("http://sm", "http://fb")), \
         patch("prusalink_api.get_printer_state", return_value={"state": "PAUSED", "is_active": True}), \
         patch.object(app_module.spoolman_api, "get_spool",
                      return_value={"id": 42, "location": "XL-1", "extra": {}}), \
         patch.object(app_module.spoolman_api, "update_spool") as upd:
        r = client.post("/api/manage_contents", json={
            "action": "force_unassign",
            "spool_id": "42",
        })
    body = r.get_json()
    assert body["success"] is False
    assert body["require_confirm"] is True
    assert body["confirm_type"] == "active_print"
    assert body["active_print"]["state"] == "PAUSED"
    upd.assert_not_called()


def test_manage_contents_clear_location_bails_when_location_is_active_toolhead(client):
    with patch.object(logic.locations_db, "load_locations_list", return_value=FAKE_LOCATIONS), \
         patch.object(logic.config_loader, "load_config", return_value={"printer_map": FAKE_PRINTER_MAP}), \
         patch.object(logic.config_loader, "get_api_urls", return_value=("http://sm", "http://fb")), \
         patch("prusalink_api.get_printer_state", return_value={"state": "PRINTING", "is_active": True}), \
         patch.object(app_module.spoolman_api, "get_spools_at_location_detailed", return_value=[]), \
         patch.object(logic, "perform_smart_eject") as eject:
        r = client.post("/api/manage_contents", json={
            "action": "clear_location",
            "location": "XL-1",
        })
    body = r.get_json()
    assert body["success"] is False
    assert body["require_confirm"] is True
    assert body["confirm_type"] == "active_print"
    eject.assert_not_called()


# ---------------------------------------------------------------------------
# /api/smart_move: bulk-assign from scan.
# ---------------------------------------------------------------------------

def test_smart_move_endpoint_returns_requires_confirm_for_active_target(client):
    with patch.object(logic.locations_db, "load_locations_list", return_value=FAKE_LOCATIONS), \
         patch.object(logic.config_loader, "load_config", return_value={"printer_map": FAKE_PRINTER_MAP}), \
         patch.object(logic.config_loader, "get_api_urls", return_value=("http://sm", "http://fb")), \
         patch("prusalink_api.get_printer_state", return_value={"state": "BUSY", "is_active": True}), \
         patch.object(app_module.spoolman_api, "update_spool") as upd:
        r = client.post("/api/smart_move", json={
            "location": "CORE1-M0",
            "spools": [99],
            "origin": "buffer",
        })
    body = r.get_json()
    assert body["status"] == "requires_confirm"
    assert body["confirm_type"] == "active_print"
    upd.assert_not_called()


def test_smart_move_endpoint_threads_confirm_flag_through(client):
    with patch.object(logic.locations_db, "load_locations_list", return_value=FAKE_LOCATIONS), \
         patch.object(logic.config_loader, "load_config", return_value={"printer_map": FAKE_PRINTER_MAP}), \
         patch.object(logic.config_loader, "get_api_urls", return_value=("http://sm", "http://fb")), \
         patch.object(logic, "perform_smart_move", return_value={"status": "success"}) as mv:
        r = client.post("/api/smart_move", json={
            "location": "CORE1-M0",
            "spools": [99],
            "origin": "buffer",
            "confirm_active_print": True,
        })
    assert r.status_code == 200
    _, kwargs = mv.call_args
    assert kwargs.get("confirm_active_print") is True


# ---------------------------------------------------------------------------
# /api/identify_scan (slot-QR assignment branch).
# ---------------------------------------------------------------------------

def test_smart_move_checks_slot_binding_for_active_print(client):
    """A move into a Dryer Box slot that's bound to an active toolhead
    (via extra.slot_targets) should bail pre-move. The auto-deploy chain
    silently swallows requires_confirm from its recursive call, so the
    preflight check must walk the binding ITSELF to catch this path.

    User-reported scenario: swap a spool between slots 1 and 2 of
    LR-MDB-1 where slot 1 is bound to an active toolhead. Expected:
    requires_confirm before the swap happens."""
    # Fake dryer box with slot 1 bound to XL-1 (which we'll mark active).
    box_row = {
        "LocationID": "LR-MDB-1",
        "Type": "Dryer Box",
        "Max Spools": "4",
        "Name": "LR MDB",
        "extra": {"slot_targets": {"1": "XL-1"}},
    }
    locs_with_bound_slot = [box_row] + [
        row for row in FAKE_LOCATIONS if row["LocationID"] != "LR-MDB-1"
    ]
    with patch.object(logic.locations_db, "load_locations_list", return_value=locs_with_bound_slot), \
         patch.object(logic.config_loader, "load_config", return_value={"printer_map": FAKE_PRINTER_MAP}), \
         patch.object(logic.config_loader, "get_api_urls", return_value=("http://sm", "http://fb")), \
         patch("prusalink_api.get_printer_state", return_value={"state": "PRINTING", "is_active": True}), \
         patch.object(logic, "resolve_scan", return_value={"type": "spool", "id": 42}), \
         patch.object(app_module.spoolman_api, "update_spool") as upd:
        r = client.post("/api/manage_contents", json={
            "action": "add",
            "location": "LR-MDB-1",
            "slot": "1",
            "spool_id": "ID:42",
            "origin": "buffer",
        })
    body = r.get_json()
    assert body.get("status") == "requires_confirm"
    assert body.get("confirm_type") == "active_print"
    assert body["active_print"]["toolhead"] == "XL-1"
    upd.assert_not_called()


def test_smart_move_slot_binding_preflight_allows_idle_target(client):
    """Same slot-binding path, but the bound toolhead is IDLE — no bail."""
    box_row = {
        "LocationID": "LR-MDB-1",
        "Type": "Dryer Box",
        "Max Spools": "4",
        "Name": "LR MDB",
        "extra": {"slot_targets": {"1": "XL-1"}},
    }
    locs_with_bound_slot = [box_row] + [
        row for row in FAKE_LOCATIONS if row["LocationID"] != "LR-MDB-1"
    ]
    with patch.object(logic.locations_db, "load_locations_list", return_value=locs_with_bound_slot), \
         patch.object(logic.config_loader, "load_config", return_value={"printer_map": FAKE_PRINTER_MAP}), \
         patch.object(logic.config_loader, "get_api_urls", return_value=("http://sm", "http://fb")), \
         patch("prusalink_api.get_printer_state", return_value={"state": "IDLE", "is_active": False}), \
         patch.object(logic, "resolve_scan", return_value={"type": "spool", "id": 42}), \
         patch.object(logic, "perform_smart_move", return_value={"status": "success"}) as mv:
        r = client.post("/api/manage_contents", json={
            "action": "add",
            "location": "LR-MDB-1",
            "slot": "1",
            "spool_id": "ID:42",
            "origin": "buffer",
        })
    body = r.get_json()
    # Request flowed through to perform_smart_move.
    assert body == {"status": "success"}
    mv.assert_called_once()


def test_slot_qr_assignment_returns_requires_confirm_for_active_toolhead(client):
    """Scanning LOC:X:SLOT:Y to assign the buffered spool into a slot whose
    auto-deploy target is an active toolhead should bail. The target in the
    assignment branch is the box — but perform_smart_move's internal check
    also covers the auto-deploy target. For this test we exercise the
    simpler case: the scan target is itself a toolhead-typed location."""
    # Seed a buffered spool.
    state.GLOBAL_BUFFER = [{"id": 77}]
    # Make LR-MDB-1 a simple "container" in the fake locs — assignment branch
    # needs Max Spools > 0 and a container type.
    locs = [row for row in FAKE_LOCATIONS if row["LocationID"] != "LR-MDB-1"] + [
        {"LocationID": "LR-MDB-1", "Type": "Dryer Box", "Max Spools": "4", "Name": "MDB"},
    ]
    with patch.object(logic.locations_db, "load_locations_list", return_value=locs), \
         patch.object(app_module.locations_db, "load_locations_list", return_value=locs), \
         patch.object(logic.config_loader, "load_config", return_value={"printer_map": FAKE_PRINTER_MAP}), \
         patch.object(logic.config_loader, "get_api_urls", return_value=("http://sm", "http://fb")), \
         patch.object(logic, "perform_smart_move",
                      return_value={"status": "requires_confirm", "confirm_type": "active_print",
                                    "active_print": {"toolhead": "CORE1-M0", "printer_name": "Core One", "state": "PRINTING"},
                                    "msg": "Core One is PRINTING — ..."}):
        r = client.post("/api/identify_scan", json={
            "text": "LOC:LR-MDB-1:SLOT:2",
            "source": "barcode",
        })
    body = r.get_json()
    assert body["action"] == "assignment_requires_confirm"
    assert body["confirm_type"] == "active_print"
    # Spool stays in the buffer because we bailed.
    assert len(state.GLOBAL_BUFFER) == 1
