import pytest
from unittest.mock import patch
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app import app

@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client

@patch('app.spoolman_api.create_filament')
@patch('app.spoolman_api.create_spool')
def test_create_inventory_temps(mock_create_spool, mock_create_filament, client):
    """Ensure temperatures are mapped natively instead of dumping to 'extra'."""
    mock_create_filament.return_value = {'id': 1}
    mock_create_spool.return_value = {'id': 100}

    payload = {
        "filament_data": {
            "name": "Test Fil",
            "material": "PLA",
            "settings_extruder_temp": 220,
            "settings_bed_temp": 65,
            "extra": {}
        },
        "spool_data": {
            "initial_weight": 1000,
            "location": "A1"
        },
        "quantity": 1
    }

    response = client.post('/api/create_inventory_wizard', json=payload)
    assert response.status_code == 200
    data = response.json
    assert data['success'] is True

    # Check filament is created with native temps
    mock_create_filament.assert_called_once()
    fil_call_args = mock_create_filament.call_args[0][0]
    assert fil_call_args.get('settings_extruder_temp') == 220
    assert fil_call_args.get('settings_bed_temp') == 65

@patch('app.spoolman_api.update_filament')
@patch('app.spoolman_api.update_spool')
def test_edit_spool_wizard(mock_update_spool, mock_update_filament, client):
    """Ensure Edit Spool endpoint calls update_spool and update_filament cleanly."""
    mock_update_spool.return_value = {'id': 100}
    mock_update_filament.return_value = {'id': 1}

    payload = {
        "spool_id": 100,
        "filament_id": 1,
        "filament_data": {
            "name": "Updated Fil",
            "settings_extruder_temp": 230,
            "extra": {}
        },
        "spool_data": {
            "used_weight": 500,
            "comment": "Edited directly"
        }
    }

    response = client.post('/api/edit_spool_wizard', json=payload)
    assert response.status_code == 200
    data = response.json
    assert data['success'] is True

    # Assert Spool Update
    mock_update_spool.assert_called_once_with(100, payload['spool_data'])
    
    # Assert Filament Update
    mock_update_filament.assert_called_once_with(1, payload['filament_data'])

@patch('app.spoolman_api.create_filament')
@patch('app.spoolman_api.create_spool')
def test_filament_attributes_chips(mock_create_spool, mock_create_filament, client):
    """Ensure that the wizard gracefully handles chip arrays inside the extra dictionary."""
    mock_create_filament.return_value = {'id': 2}
    mock_create_spool.return_value = {'id': 101}

    payload = {
        "filament_data": {
            "name": "Chip Test",
            "extra": {
                "filament_attributes": ["Matte", "High Speed", "Tough"]
            }
        },
        "spool_data": {
            "location": "B2"
        },
        "quantity": 1
    }

    response = client.post('/api/create_inventory_wizard', json=payload)
    assert response.status_code == 200
    
    mock_create_filament.assert_called_once()
    fil_call_args = mock_create_filament.call_args[0][0]
    assert "filament_attributes" in fil_call_args['extra']
    assert isinstance(fil_call_args['extra']['filament_attributes'], list)
    assert "Matte" in fil_call_args['extra']['filament_attributes']
