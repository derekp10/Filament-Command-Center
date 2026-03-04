import pytest
import sys
import os
import json

# Add parent directory to python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import spoolman_api

def test_sanitize_outbound_data_string_numbers():
    """Test that numbers inside strings are strictly dumped as json strings if in JSON_STRING_FIELDS"""
    
    payload = {
        "id": 1,
        "extra": {
            "container_slot": "4", # Strictly typed in Spoolman DB as string
            "physical_source_slot": "99",
            "random_field": "123" # Not in JSON_STRING_FIELDS
        }
    }
    
    clean_payload = spoolman_api.sanitize_outbound_data(payload)
    clean_extra = clean_payload.get('extra', {})
    
    # "4" -> json.dumps -> '"4"'
    assert clean_extra.get('container_slot') == '"4"'
    assert clean_extra.get('physical_source_slot') == '"99"'
    
    # "123" -> json.loads -> 123 -> not enforced as string
    assert clean_extra.get('random_field') == "123"

def test_sanitize_outbound_data_naked_strings():
    """Test that arbitrary naked strings are wrapped in double quotes to satisfy Spoolman json constraints"""
    payload = {
        "id": 1,
        "extra": {
            "slicer_profile": "Basic PLA" # Naked string
        }
    }
    
    clean_payload = spoolman_api.sanitize_outbound_data(payload)
    
    assert clean_payload['extra']['slicer_profile'] == '"Basic PLA"'
