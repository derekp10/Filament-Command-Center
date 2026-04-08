import pytest
import sys
import os
from unittest.mock import patch, MagicMock

# Add parent directory to python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import logic

def test_universal_fallback_move():
    """Verify perform_smart_move records physical_source when moving from any location to a printer."""
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
        assert data['location'] == "PRINTER-1"
        assert data['extra']['physical_source'] == "SHELF-1"
        return True

    with patch('locations_db.load_locations_list', return_value=mock_loc_list):
        with patch('config_loader.load_config', return_value={"printer_map": mock_printer_map}):
            with patch('spoolman_api.get_spools_at_location', return_value=[]):
                with patch('spoolman_api.get_spool', return_value=mock_spool):
                    with patch('spoolman_api.format_spool_display', return_value={"text": "Test", "color": "000"}):
                        with patch('spoolman_api.update_spool', side_effect=fake_update):
                            with patch('requests.post') as mock_post:
                                res = logic.perform_smart_move("PRINTER-1", [5])
                                assert res['status'] == 'success'
                                mock_post.assert_called_once()
                                assert mock_post.call_args[1]['json']['spool_id'] == 5

def test_smart_eject_clears_filabridge_and_unassigns_if_no_source():
    """Verify ejecting from a printer without physical_source goes to Unassigned and clears FB."""
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
                    with patch('requests.post') as mock_post:
                        res = logic.perform_smart_eject(6, confirmed_unassign=True)
                        assert res is True
                        mock_post.assert_called_once()
                        assert mock_post.call_args[1]['json']['spool_id'] == 0

def test_force_unassign_clears_filabridge():
    """Verify perform_force_unassign clears filabridge toolhead."""
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
                    with patch('requests.post') as mock_post:
                        res = logic.perform_force_unassign(7)
                        assert res is True
                        mock_post.assert_called_once()
                        assert mock_post.call_args[1]['json']['spool_id'] == 0

def test_smart_move_suppresses_unmap():
    """Verify swapping a spool suppresses the 0 signal to protect active prints."""
    mock_printer_map = {
        "PRINTER-4": {"printer_name": "TestPrinter4", "position": 1}
    }
    
    # Target spool we are loading (Spool 8)
    mock_spool_8 = {"id": 8, "location": "BUFFER", "extra": {}}
    
    # Resident spool we are ejecting (Spool 9)
    # We stub a side-effect to ensure perform_smart_eject respects the suppress flag
    with patch('spoolman_api.get_spools_at_location', return_value=[9]):
        with patch('spoolman_api.get_spool', return_value=mock_spool_8):
            with patch('config_loader.load_config', return_value={"printer_map": mock_printer_map}):
                with patch('locations_db.load_locations_list', return_value=[]):
                    with patch('spoolman_api.format_spool_display', return_value={"text": "", "color": "000"}):
                        with patch('spoolman_api.update_spool', return_value=True):
                            with patch('logic.perform_smart_eject') as mock_eject:
                                with patch('requests.post') as mock_post:
                                    res = logic.perform_smart_move("PRINTER-4", [8])
                                    
                                    # Eject should be called on the resident with suppress flag
                                    mock_eject.assert_called_once_with(9, suppress_fb_unmap=True)
                                    
                                    # Post should only be called ONCE to map Spool 8
                                    mock_post.assert_called_once()
                                    assert mock_post.call_args[1]['json']['spool_id'] == 8
