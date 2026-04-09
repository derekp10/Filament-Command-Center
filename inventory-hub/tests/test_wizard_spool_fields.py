"""Tests for spool_weight mapping, price field, and purchase_url
in the inventory wizard creation and edit endpoints."""
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
def test_spool_weight_passes_through(mock_create_spool, mock_create_filament, client):
    """Ensure spool_weight is passed directly to Spoolman (not as empty_weight)."""
    mock_create_filament.return_value = {'id': 10}
    mock_create_spool.return_value = {'id': 200}

    payload = {
        "filament_data": {
            "name": "Weight Test",
            "material": "PLA",
            "extra": {}
        },
        "spool_data": {
            "spool_weight": 250,
            "used_weight": 0,
            "location": "A1",
            "extra": {}
        },
        "quantity": 1
    }

    response = client.post('/api/create_inventory_wizard', json=payload)
    assert response.status_code == 200
    assert response.json['success'] is True

    # Verify create_spool received spool_weight (not empty_weight)
    mock_create_spool.assert_called_once()
    spool_call_args = mock_create_spool.call_args[0][0]
    assert 'spool_weight' in spool_call_args
    assert spool_call_args['spool_weight'] == 250
    assert 'empty_weight' not in spool_call_args


@patch('app.spoolman_api.create_filament')
@patch('app.spoolman_api.create_spool')
def test_price_passes_through(mock_create_spool, mock_create_filament, client):
    """Ensure price field is passed as a native Spoolman spool field."""
    mock_create_filament.return_value = {'id': 11}
    mock_create_spool.return_value = {'id': 201}

    payload = {
        "filament_data": {
            "name": "Price Test",
            "material": "PLA",
            "extra": {}
        },
        "spool_data": {
            "price": 24.99,
            "used_weight": 0,
            "location": "",
            "extra": {}
        },
        "quantity": 1
    }

    response = client.post('/api/create_inventory_wizard', json=payload)
    assert response.status_code == 200
    assert response.json['success'] is True

    mock_create_spool.assert_called_once()
    spool_call_args = mock_create_spool.call_args[0][0]
    assert 'price' in spool_call_args
    assert spool_call_args['price'] == 24.99


@patch('app.spoolman_api.create_filament')
@patch('app.spoolman_api.create_spool')
def test_purchase_url_in_spool_extra(mock_create_spool, mock_create_filament, client):
    """Ensure purchase_url is stored inside spool extra, not as a top-level field."""
    mock_create_filament.return_value = {'id': 12}
    mock_create_spool.return_value = {'id': 202}

    payload = {
        "filament_data": {
            "name": "Purchase URL Test",
            "material": "PLA",
            "extra": {}
        },
        "spool_data": {
            "used_weight": 0,
            "location": "",
            "extra": {
                "purchase_url": "https://amazon.com/example-filament"
            }
        },
        "quantity": 1
    }

    response = client.post('/api/create_inventory_wizard', json=payload)
    assert response.status_code == 200
    assert response.json['success'] is True

    mock_create_spool.assert_called_once()
    spool_call_args = mock_create_spool.call_args[0][0]
    assert 'extra' in spool_call_args
    assert spool_call_args['extra']['purchase_url'] == "https://amazon.com/example-filament"


@patch('app.spoolman_api.create_spool')
def test_clone_spool_weight_existing_filament(mock_create_spool, client):
    """Simulate a clone scenario: existing filament mode with spool_weight set.
    The wizard sends spool_weight directly when cloning."""
    mock_create_spool.return_value = {'id': 203}

    payload = {
        "filament_id": 5,  # Using existing filament
        "spool_data": {
            "spool_weight": 180,
            "used_weight": 0,
            "location": "B3",
            "extra": {}
        },
        "quantity": 1
    }

    response = client.post('/api/create_inventory_wizard', json=payload)
    assert response.status_code == 200
    assert response.json['success'] is True

    mock_create_spool.assert_called_once()
    spool_call_args = mock_create_spool.call_args[0][0]
    assert spool_call_args['spool_weight'] == 180
    assert spool_call_args['filament_id'] == 5


@patch('app.spoolman_api.update_filament')
@patch('app.spoolman_api.update_spool')
@patch('app.spoolman_api.get_spool')
def test_edit_spool_weight_dirty_diff(mock_get_spool, mock_update_spool, mock_update_filament, client):
    """Ensure the edit wizard correctly diffs spool_weight and passes it through."""
    mock_get_spool.return_value = {
        'id': 300,
        'spool_weight': 200,
        'used_weight': 100,
        'location': 'C1',
        'comment': '',
        'extra': {},
        'filament': {'id': 15}
    }
    mock_update_spool.return_value = {'id': 300}
    mock_update_filament.return_value = {'id': 15}

    payload = {
        "spool_id": 300,
        "filament_id": 15,
        "filament_data": {
            "name": "Edit Test",
            "extra": {}
        },
        "spool_data": {
            "spool_weight": 250,  # Changed from 200 to 250
            "used_weight": 100,
            "location": "C1",
            "comment": "",
            "extra": {}
        }
    }

    response = client.post('/api/edit_spool_wizard', json=payload)
    assert response.status_code == 200
    assert response.json['success'] is True

    # Assert spool was updated with the new weight
    mock_update_spool.assert_called_once()
    dirty_data = mock_update_spool.call_args[0][1]
    assert 'spool_weight' in dirty_data
    assert dirty_data['spool_weight'] == 250
