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


def test_smart_eject_lands_unslotted_when_home_slot_already_claimed():
    """13.2 — if the saved home slot is already occupied by another spool
    (direct OR ghost from a different spool), perform_smart_eject must land
    the returning spool unslotted instead of creating a 2-in-1-slot
    collision that hides one of them in the dryer-box grid.

    Repro: Spool #106 returning to LR-MDB-2 slot 1, but Spool #230's ghost
    already claims slot 1 (because #230 was just deployed from there to the
    toolhead). Pre-fix: #106 landed in slot 1, render collision, one spool
    invisible. Post-fix: #106 lands unslotted in LR-MDB-2."""
    spool_106 = {
        "id": 106,
        "location": "XL-4",
        "extra": {
            "physical_source": "LR-MDB-2",
            "physical_source_slot": "1",
            "container_slot": "",
        },
    }
    other_at_box = [
        # Ghost from #230 (deployed to XL-4 but bound to LR-MDB-2 slot 1).
        {"id": 230, "slot": "1", "is_ghost": True, "location": "LR-MDB-2"},
    ]
    captured = {}

    def fake_update(sid, data):
        captured["sid"] = sid
        captured["data"] = data
        return True

    with patch("spoolman_api.get_spool", return_value=spool_106):
        with patch("spoolman_api.update_spool", side_effect=fake_update):
            with patch("spoolman_api.get_spools_at_location_detailed",
                       return_value=other_at_box):
                with patch("state.add_log_entry"):
                    with patch("state.logger"):
                        res = logic.perform_smart_eject(106, confirm_active_print=True)
                        assert res is True
    assert captured["sid"] == 106
    assert captured["data"]["location"] == "LR-MDB-2"
    # The whole point: slot 1 was taken, so land unslotted.
    assert captured["data"]["extra"]["container_slot"] == ""
    assert captured["data"]["extra"]["physical_source_slot"] == ""


def test_smart_eject_keeps_slot_when_only_self_claims_it():
    """13.2 sibling — the collision check must skip the returning spool's
    OWN ghost listing. Without this guard, a spool with physical_source =
    its home box would match itself and always land unslotted."""
    spool_77 = {
        "id": 77,
        "location": "XL-2",
        "extra": {
            "physical_source": "PM-DB-XL-L",
            "physical_source_slot": "2",
            "container_slot": "",
        },
    }
    # Spool 77's OWN ghost is what `get_spools_at_location_detailed` would
    # return when scanning PM-DB-XL-L — it's the spool we're moving, so it
    # shouldn't count as a collision.
    self_ghost = [
        {"id": 77, "slot": "2", "is_ghost": True, "location": "PM-DB-XL-L"},
    ]
    captured = {}

    def fake_update(sid, data):
        captured["data"] = data
        return True

    with patch("spoolman_api.get_spool", return_value=spool_77):
        with patch("spoolman_api.update_spool", side_effect=fake_update):
            with patch("spoolman_api.get_spools_at_location_detailed",
                       return_value=self_ghost):
                with patch("state.add_log_entry"):
                    with patch("state.logger"):
                        res = logic.perform_smart_eject(77, confirm_active_print=True)
                        assert res is True
    # Slot is restored — only the spool's own ghost was in the way.
    assert captured["data"]["extra"]["container_slot"] == "2"

def test_get_room_from_location_parsing():
    """Verify get_room_from_location parses parent rooms and filters exclusions."""
    # We must patch locations database because it tries to load it to check for printers
    with patch('locations_db.load_locations_list', return_value=[]):
        assert logic.get_room_from_location("LR-MDB-1") == "LR"
        assert logic.get_room_from_location("GAR-SHELF-5") == "GAR"
        assert logic.get_room_from_location("BOX") == "" # No hyphen
        assert logic.get_room_from_location("") == ""
        assert logic.get_room_from_location("TST-TUBE") == "" # Excluded TST
        assert logic.get_room_from_location("TEST-123") == "" # Excluded TEST
        assert logic.get_room_from_location("PM-123") == "" # Excluded PM
        assert logic.get_room_from_location("PJ-CART1") == "" # Excluded PJ
        
        # Tools/Printers are NO LONGER excluded, they generate root systems correctly
        assert logic.get_room_from_location("PRINTER-1") == "PRINTER"
        assert logic.get_room_from_location("CORE1-MMU") == "CORE1"

def test_smart_eject_falls_back_to_room():
    """Verify normal slotted ejection from a Box falls back to its Room and preserves ghost slot."""
    mock_db = {
        "id": 2,
        "location": "LR-MDB-1",
        "extra": {
            "physical_source": "",
            "physical_source_slot": "",
            "container_slot": "5"
        }
    }
    
    def fake_update(sid, data):
        assert data['location'] == "LR"
        assert data['extra']['container_slot'] == ""
        # Verifying Ghost logic is strictly wiped on unslotted demotion
        assert data['extra']['physical_source'] == ""
        assert data['extra']['physical_source_slot'] == ""
        return True

    with patch('spoolman_api.get_spool', return_value=mock_db):
        with patch('spoolman_api.update_spool', side_effect=fake_update):
            with patch('state.add_log_entry'):
                with patch('locations_db.load_locations_list', return_value=[]):
                    res = logic.perform_smart_eject(2)
                    assert res is True

def test_smart_eject_requires_confirm_for_unassigned():
    """Verify ejecting from a Room (or no hyphen location) requires confirmation before moving to Unassigned."""
    mock_db = {
        "id": 3,
        "location": "LR",
        "extra": {
            "physical_source": "LR-MDB-1",
            "physical_source_slot": "5"
        }
    }
    
    with patch('spoolman_api.get_spool', return_value=mock_db):
        res = logic.perform_smart_eject(3)
        assert res == "REQUIRE_CONFIRM"
        
        # When confirmed, goes to Unassigned and wipes container slot
        def fake_update_confirm(sid, data):
            assert data['location'] == ""
            assert data['extra']['container_slot'] == ""
            return True
            
        with patch('spoolman_api.update_spool', side_effect=fake_update_confirm):
            with patch('state.add_log_entry'):
                res2 = logic.perform_smart_eject(3, confirmed_unassign=True)
                assert res2 is True
