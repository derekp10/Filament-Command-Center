import sys
import os
import pytest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import spoolman_api

def test_create_filament_live_logic():
    """Test filament creation sanitization and API calling"""
    payload = {
        "name": "Live API Multi-Color Test",
        "material": "PLA",
        "vendor_id": 1, 
        "weight": 1000,
        "diameter": 1.75,
        "density": 1.24,
        "extra": {
            "multi_color_hexes": "FF0000,00FF00,0000FF",
            "multi_color_direction": "coaxial"
        }
    }

    with patch('requests.post') as mock_post:
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.json.return_value = {"id": 999}
        mock_post.return_value = mock_response

        # Need to patch get_api_urls to not require config file presence during testing
        with patch('config_loader.get_api_urls', return_value=("http://spoolman", "http://filabridge")):
            result = spoolman_api.create_filament(payload)
            
            assert result is not None
            assert result['id'] == 999
            
            # Verify the call had sanitized JSON where needed
            mock_post.assert_called_once()
            args, kwargs = mock_post.call_args
            assert args[0] == "http://spoolman/api/v1/filament"
            assert "json" in kwargs
            # verify that "extra" strings got properly preserved
            assert kwargs['json']['extra']['multi_color_direction'] == '"coaxial"'
