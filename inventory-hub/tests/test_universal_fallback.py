"""Behavior guards for logic.perform_smart_move / perform_smart_eject /
perform_force_unassign.

History (Group 26.2): these tests originally ALSO asserted a FilaBridge
`requests.post` push (`_fb_write`) on every move/eject/unassign
(`mock_post.assert_called_once()`). The FilaBridge Phase-2 cutover
(2026-06-13) removed that writer entirely — FCC no longer POSTs to FilaBridge
on any path, and `logic.py` now contains no `requests.post` at all — so those
assertions pinned retired behavior and failed with "Called 0 times". Rewritten
to keep the still-valid invariants: physical_source recording on a
move-to-printer, unassign-on-no-source, the eject-before-remap ordering, and
the return contracts. (The retired FilaBridge-clearing behavior is part of the
standalone "vestigial FilaBridge artifacts" cleanup.)
"""
import pytest
import sys
import os
from unittest.mock import patch

# Add parent directory to python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import logic


@pytest.fixture(autouse=True)
def _printer_map_from_config(monkeypatch):
    """L271 P4 step 2: logic.py reads printer_map via
    locations_db.get_active_printer_map() now; these tests inject printer_map
    through the config_loader.load_config stub, so make the accessor delegate to
    it — mirrors the pre-swap `cfg.get('printer_map')` source exactly."""
    monkeypatch.setattr(
        logic.locations_db, "get_active_printer_map",
        lambda loc_list=None: (logic.config_loader.load_config() or {}).get("printer_map", {}) or {},
    )


def test_universal_fallback_move():
    """perform_smart_move records physical_source when moving from any
    location to a printer, and reports success."""
    mock_loc_list = [
        {"LocationID": "SHELF-1", "Type": "Shelf"},
        {"LocationID": "PRINTER-1", "Type": "Printer"}
    ]

    mock_printer_map = {
        "PRINTER-1": {"printer_name": "TestPrinter", "position": 1}
    }

    mock_spool = {
        "id": 5,
        "location": "SHELF-1",
        "extra": {}
    }

    def fake_update(sid, data):
        # The move lands the spool on the printer and records the origin as
        # its physical_source (the "return home" trail).
        assert data['location'] == "PRINTER-1"
        assert data['extra']['physical_source'] == "SHELF-1"
        return True

    with patch('locations_db.load_locations_list', return_value=mock_loc_list):
        with patch('config_loader.load_config', return_value={"printer_map": mock_printer_map}):
            with patch('spoolman_api.get_spools_at_location', return_value=[]):
                with patch('spoolman_api.get_spool', return_value=mock_spool):
                    with patch('spoolman_api.format_spool_display', return_value={"text": "Test", "color": "000"}):
                        with patch('spoolman_api.update_spool', side_effect=fake_update):
                            res = logic.perform_smart_move("PRINTER-1", [5])
                            assert res['status'] == 'success'


def test_smart_eject_unassigns_if_no_source():
    """Ejecting from a printer without a physical_source goes to Unassigned
    (empty location)."""
    mock_spool = {
        "id": 6,
        "location": "PRINTER-2",
        "extra": {}
    }

    mock_printer_map = {
        "PRINTER-2": {"printer_name": "TestPrinter2", "position": 1}
    }

    def fake_update(sid, data):
        assert data['location'] == ""
        return True

    with patch('spoolman_api.get_spool', return_value=mock_spool):
        with patch('config_loader.load_config', return_value={"printer_map": mock_printer_map}):
            with patch('spoolman_api.update_spool', side_effect=fake_update):
                with patch('state.add_log_entry'):
                    res = logic.perform_smart_eject(6, confirmed_unassign=True)
                    assert res is True


def test_force_unassign_unassigns():
    """perform_force_unassign returns True on a clean unassign."""
    mock_spool = {
        "id": 7,
        "location": "PRINTER-3",
        "extra": {}
    }

    mock_printer_map = {
        "PRINTER-3": {"printer_name": "TestPrinter3", "position": 1}
    }

    with patch('spoolman_api.get_spool', return_value=mock_spool):
        with patch('config_loader.load_config', return_value={"printer_map": mock_printer_map}):
            with patch('spoolman_api.update_spool', return_value=True):
                with patch('state.add_log_entry'):
                    res = logic.perform_force_unassign(7)
                    assert res is True


def test_smart_move_ejects_resident_before_remap():
    """Smart Load ejects the resident of the target toolhead before loading
    the incoming spool.

    The old code passed a `suppress_fb_unmap` flag that skipped the FilaBridge
    unmap of the target toolhead, leaving FilaBridge thinking the resident was
    still there and rejecting the incoming spool. The flag was deleted; FCC now
    ejects the resident unconditionally before remapping. FilaBridge is gone,
    but the eject-before-remap ordering invariant remains and is what this test
    pins."""
    mock_printer_map = {
        "PRINTER-4": {"printer_name": "TestPrinter4", "position": 1}
    }

    # Target spool we are loading (Spool 8)
    mock_spool_8 = {"id": 8, "location": "BUFFER", "extra": {}}

    # Resident spool we are ejecting (Spool 9)
    with patch('spoolman_api.get_spools_at_location', return_value=[9]):
        with patch('spoolman_api.get_spool', return_value=mock_spool_8):
            with patch('config_loader.load_config', return_value={"printer_map": mock_printer_map}):
                with patch('locations_db.load_locations_list', return_value=[]):
                    with patch('spoolman_api.format_spool_display', return_value={"text": "", "color": "000"}):
                        with patch('spoolman_api.update_spool', return_value=True):
                            with patch('logic.perform_smart_eject') as mock_eject:
                                res = logic.perform_smart_move("PRINTER-4", [8])

                                # The resident (#9) is ejected exactly once,
                                # before the incoming spool is remapped onto the
                                # toolhead.
                                mock_eject.assert_called_once_with(9)
                                assert res['status'] == 'success'
