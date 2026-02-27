import pytest
import sys
import os
import json

# Add the parent directory to sys.path so we can import the modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from external_parsers import SpoolmanParser, PrusamentParser, search_external
from unittest.mock import patch, Mock

def test_spoolman_parser_mocked():
    # Mock the config loader and requests.get for Spoolman
    with patch('config_loader.get_api_urls', return_value=("http://mocked-spoolman:7942", "")), \
         patch('requests.get') as mock_get:
        
        # Create a mock response
        mock_response = Mock()
        mock_response.ok = True
        mock_response.json.return_value = [
            {"id": "ext1", "manufacturer": "Hatchbox", "material": "PLA", "color_name": "True Black"},
            {"id": "ext2", "vendor": {"name": "eSun"}, "material": "PETG", "name": "Solid Red"}
        ]
        mock_get.return_value = mock_response
        
        # Test blank search (returns all)
        res_all = SpoolmanParser.search("")
        assert len(res_all) == 2
        
        # Test querying
        res_pla = SpoolmanParser.search("Hatchbox PLA")
        assert len(res_pla) == 1
        assert res_pla[0]["manufacturer"] == "Hatchbox"
        
        res_red = SpoolmanParser.search("esun red")
        assert len(res_red) == 1
        assert res_red[0]["name"] == "Solid Red"

def test_prusament_parser_valid_url():
    url = "https://prusament.com/spool/17705/5b1a183b26/"
    
    # Mock requests.get to return a fake HTML snippet containing the JSON
    mock_html = """
    <html><body>
    <script>
    var spoolData = '{"ff_goods_id": 9999, "weight": 1050, "spool_weight": 250, "filament": {"name": "P PLA Black", "material": "PLA", "color_rgb": "#000000", "color_name": "Galaxy Black"}}';
    </script>
    </body></html>
    """
    
    with patch('requests.get') as mock_get:
        mock_response = Mock()
        mock_response.ok = True
        mock_response.text = mock_html
        mock_get.return_value = mock_response
        
        res = PrusamentParser.search(url)
    assert len(res) == 1
    spool = res[0]
    
    # Verify standard schema
    assert spool["id"] == "9999"
    assert spool["name"] == "P PLA Black"
    assert spool["material"] == "PLA"
    assert spool["vendor"]["name"] == "Prusament"
    assert spool["weight"] == 1050.0  # Exact scraped net weight
    assert spool["spool_weight"] == 250.0
    assert spool["color_hex"] == "000000"
    assert spool["color_name"] == "Galaxy Black"
    assert spool["external_link"] == url

def test_prusament_parser_invalid_query():
    # Sending a generic search term instead of a URL should return empty 
    # and not crash
    res = PrusamentParser.search("PLA Black")
    assert len(res) == 0

def test_router_function():
    # Ensure search_external correctly routes to the parser
    with patch.object(PrusamentParser, 'search', return_value=[{"id": "mocked"}]):
        res = search_external("prusament", "https://prusament.com/spool/123/")
        assert len(res) == 1
        assert res[0]["id"] == "mocked"
        
        with pytest.raises(ValueError):
            search_external("invalid_source", "test")
