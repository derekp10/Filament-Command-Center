import sys
import os
import pytest
from unittest.mock import patch, MagicMock

# Ensure inventory-hub can be imported
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import spoolman_api

def test_get_spools_at_location_detailed_ghost():
    """Test that ghosts correctly provide color_direction and physical source logic"""
    # Mock Spoolman API response
    mock_data = [
        {
            "id": 100,
            "location": "PRINTER-1",
            "filament": {
                "id": 10,
                "name": "Magic Filament",
                "color_hex": "FF0000",
                "vendor": {"name": "Test Vendor"},
                "material": "PLA",
                "multi_color_direction": "coaxial",
                "multi_color_hexes": "FF0000,00FF00"
            },
            "extra": {
                "physical_source": "DRYER-1",
                "physical_source_slot": "3"
            }
        }
    ]

    with patch('requests.get') as mock_get:
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.json.return_value = mock_data
        mock_get.return_value = mock_response

        # Call our method looking for DRYER-1 (where the ghost lives)
        results = spoolman_api.get_spools_at_location_detailed("DRYER-1")
        
        assert len(results) == 1
        res = results[0]
        assert res['id'] == 100
        assert res['is_ghost'] is True
        assert res['location'] == 'DRYER-1' # Because we fixed it to report p_source
        assert res['slot'] == '3'
        assert res['color_direction'] == 'coaxial' # Ensuring our new fix propagates
        assert res['deployed_to'] == 'PRINTER-1'

