import pytest
import sys
import os

# Ensure the inventory-hub is in the path to mock imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'inventory-hub')))

import spoolman_api

def test_sanitize_outbound_data_json_strings():
    """
    Ensures that specifically designated JSON string fields inside the 'extra' dict 
    are properly wrapped in explicit double quotes for Spoolman compatibility.
    """
    
    # Test Data Payload simulating a spool edit
    mock_data = {
        "location": "DRYER-1",
        "extra": {
            "product_url": "https://example.com/spool/123",
            "physical_source_slot": "4",
            "is_refill": True,
            "spool_weight": 1000,
            "random_field": "Should Not Quote"
        }
    }
    
    sanitized = spoolman_api.sanitize_outbound_data(mock_data)
    extra = sanitized.get("extra", {})
    
    # Assertions
    # 1. product_url MUST be wrapped in double quotes
    assert extra.get("product_url") == '"https://example.com/spool/123"'
    
    # 2. physical_source_slot MUST be wrapped in double quotes
    assert extra.get("physical_source_slot") == '"4"'
    
    # 3. Booleans must be stringified to "true" / "false"
    assert extra.get("is_refill") == "true"
    
    # 4. Normal types are stringified but NOT explicitly double-quoted 
    assert extra.get("spool_weight") == "1000"
    assert extra.get("random_field") == "Should Not Quote"

def test_sanitize_outbound_data_handles_existing_quotes():
    """
    Ensures that if the data is already wrapped in double quotes, 
    the sanitizer doesn't double-wrap it (e.g., '""https://...""')
    """
    
    mock_data = {
        "extra": {
            "product_url": '"https://alreadyquoted.com"'
        }
    }
    
    sanitized = spoolman_api.sanitize_outbound_data(mock_data)
    extra = sanitized.get("extra", {})
    
    assert extra.get("product_url") == '"https://alreadyquoted.com"'
