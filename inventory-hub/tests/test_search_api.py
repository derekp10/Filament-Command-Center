import pytest
import requests
from unittest.mock import patch, MagicMock
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import app as flask_app
import spoolman_api

# Mock spoolman response data
MOCK_SPOOLS = [
    {
        "id": 1,
        "remaining_weight": 1000,
        "location": "Shelf A",
        "filament": {
            "name": "Standard PLA",
            "material": "PLA",
            "color_hex": "FF0000",
            "vendor": {"name": "Prusament"},
            "extra": {"original_color": "Lipstick Red"}
        }
    },
    {
        "id": 2,
        "remaining_weight": 0,
        "location": "Trash",
        "filament": {
            "name": "Galaxy Black",
            "material": "PETG",
            "color_hex": "000000",
            "vendor": {"name": "Prusament"},
            "extra": {"original_color": "Space Black"}
        }
    },
    {
        "id": 3,
        "remaining_weight": 500,
        "location": "Shelf B",
        "filament": {
            "name": "Silk White",
            "material": "PLA",
            "color_hex": "FFFFFF",
            "multi_color_hexes": "00FF00,0000FF",  # Gradient for testing (No Red)
            "vendor": {"name": "Generic"},
            "extra": {"original_color": "Bone White"}
        }
    }
]

MOCK_FILAMENTS = [
    {
        "id": 99,
        "name": "Silk White",
        "material": "PLA",
        "color_hex": "FFFFFF",
        "vendor": {"name": "Generic"},
        "extra": {"original_color": "Bone White"}
    }
]

@pytest.fixture
def client():
    flask_app.config['TESTING'] = True
    with flask_app.test_client() as client:
        yield client

@patch('spoolman_api.requests.get')
def test_search_spools_basic_query(mock_get):
    """Test tokenized fuzzy matching by text fields."""
    mock_response = MagicMock()
    mock_response.ok = True
    mock_response.json.return_value = MOCK_SPOOLS
    mock_get.return_value = mock_response

    # Strict token search matching "PLA" and "Black" in id 2 context
    results = spoolman_api.search_inventory(query="black petg")
    assert len(results) == 1
    assert results[0]['id'] == 2
    
    # Assert Order doesn't matter (tokenization)
    results = spoolman_api.search_inventory(query="petg black")
    assert len(results) == 1
    assert results[0]['id'] == 2
    
    results = spoolman_api.search_inventory(query="PLA")
    assert len(results) == 2

@patch('spoolman_api.requests.get')
def test_search_spools_color_hex(mock_get):
    """Test Euclidean distance sorting for colors, including multi-color gradient support."""
    mock_response = MagicMock()
    mock_response.ok = True
    mock_response.json.return_value = MOCK_SPOOLS
    mock_get.return_value = mock_response

    # #FEEFEF is very close to white (FFFFFF), however ID 3 defines a multi_color_hexes of RED, GREEN, BLUE.
    # So if we search for Pure Green (#00FF00), ID 3 should win because its multi_color gradient contains Green.
    results = spoolman_api.search_inventory(color_hex="#00FF00")
    assert len(results) == 3
    assert results[0]['id'] == 3 # ID 3 contains the exact green in its gradient

    # #880000 is closest to red (FF0000), ID 1 should be first
    results = spoolman_api.search_inventory(color_hex="#880000")
    assert len(results) == 3
    assert results[0]['id'] == 1

@patch('spoolman_api.requests.get')
def test_search_spools_stock_filters(mock_get):
    """Test only_in_stock and empty parameters for spools."""
    mock_response = MagicMock()
    mock_response.ok = True
    mock_response.json.return_value = MOCK_SPOOLS
    mock_get.return_value = mock_response

    results = spoolman_api.search_inventory(only_in_stock=True)
    assert len(results) == 2
    assert 2 not in [r['id'] for r in results]

    results = spoolman_api.search_inventory(empty=True)
    assert len(results) == 1
    assert results[0]['id'] == 2

@patch('spoolman_api.requests.get')
def test_search_filament_target_type(mock_get):
    """Test searching raw filaments instead of spools."""
    mock_response = MagicMock()
    mock_response.ok = True
    mock_response.json.return_value = MOCK_FILAMENTS
    mock_get.return_value = mock_response

    results = spoolman_api.search_inventory(query="Silk", target_type="filament")
    assert len(results) == 1
    assert results[0]['id'] == 99
    assert results[0]['type'] == 'filament'

def test_api_endpoint(client):
    """Test the Flask API endpoint wrapper."""
    with patch('spoolman_api.search_inventory') as mock_search:
        mock_search.return_value = [{"id": 99, "display": "Mock Spool"}]
        
        response = client.get('/api/search?q=test&material=PLA&in_stock=true&type=filament')
        assert response.status_code == 200
        
        data = response.json
        assert data['success'] is True
        assert len(data['results']) == 1
        assert data['results'][0]['id'] == 99
        
        # Verify the arguments were passed to the logic layer correctly
        mock_search.assert_called_once_with(
            query="test",
            material="PLA",
            vendor="",
            color_hex="",
            only_in_stock=True,
            empty=False,
            target_type="filament"
        )
