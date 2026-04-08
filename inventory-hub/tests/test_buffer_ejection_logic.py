import pytest
import sys
import os
from unittest.mock import patch, MagicMock

# Add parent directory to python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import logic

def test_get_live_spools_data_retains_ghost_context():
    """Verify get_live_spools_data correctly infers and attaches ghost slot context."""
    
    mock_db = {
        1: {
            "id": 1,
            "location": "",
            "extra": {
                "physical_source": "DRYER_BOX",
                "physical_source_slot": "4",
                "container_slot": "99" # Suppose deployed to toolhead MMU Slot 99
            }
        }
    }
    
    def fake_get_spool(sid):
        return mock_db.get(sid)
        
    def fake_format_spool_display(data):
        return {"text": "Test Display", "color": "fff", "slot": "99"}

    with patch('spoolman_api.get_spool', side_effect=fake_get_spool):
        with patch('spoolman_api.format_spool_display', side_effect=fake_format_spool_display):
            res = logic.get_live_spools_data([1])
            
            payload = res.get('1')
            assert payload is not None
            assert payload['is_ghost'] is True
            assert payload['location'] == "DRYER_BOX"
            assert payload['slot'] == "4" # It should pull physical_source_slot since it's a ghost
            assert payload['deployed_to'] == ""

def test_smart_eject_restores_home_slot():
    """Verify perform_smart_eject restores physical_source_slot payload back to container_slot when homing."""
    mock_db = {
        "id": 1,
        "location": "MMU_TOOLHEAD",
        "extra": {
            "physical_source": "DRYER_BOX",
            "physical_source_slot": "4",
            "container_slot": "1" # Currently in slot 1 of MMU
        }
    }
    
    def fake_update(sid, data):
        # We want to assert the payload 'data' passed to update_spool
        assert data['location'] == "DRYER_BOX"
        assert data['extra']['physical_source'] == ""
        assert data['extra']['container_slot'] == "4" # Restored successfully
        assert data['extra']['physical_source_slot'] == ""
        return True

    with patch('spoolman_api.get_spool', return_value=mock_db):
        with patch('spoolman_api.update_spool', side_effect=fake_update):
            with patch('state.add_log_entry'):
                res = logic.perform_smart_eject(1)
                assert res is True
