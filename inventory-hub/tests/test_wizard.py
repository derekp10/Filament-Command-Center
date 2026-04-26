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

@patch('app.spoolman_api.create_filament')
@patch('app.spoolman_api.create_spool')
def test_create_inventory_multi_color(mock_create_spool, mock_create_filament, client):
    """Ensure that the wizard cleanly passes through multi_color_hexes and directions."""
    mock_create_filament.return_value = {'id': 3}
    mock_create_spool.return_value = {'id': 102}

    payload = {
        "filament_data": {
            "name": "Multi Color Test",
            "material": "PLA",
            "color_hex": "FF0000",
            "multi_color_hexes": "FF0000,00FF00,0000FF",
            "multi_color_direction": "coextruded",
            "extra": {
                "color_hexes": "FF0000,00FF00,0000FF"
            }
        },
        "spool_data": {
            "location": ""
        },
        "quantity": 1
    }

    response = client.post('/api/create_inventory_wizard', json=payload)
    assert response.status_code == 200

    mock_create_filament.assert_called_once()
    fil_call_args = mock_create_filament.call_args[0][0]
    assert fil_call_args['multi_color_hexes'] == "FF0000,00FF00,0000FF"
    assert fil_call_args['multi_color_direction'] == "coextruded"
    assert fil_call_args['extra']['color_hexes'] == "FF0000,00FF00,0000FF"

@patch('app.spoolman_api.create_filament')
@patch('app.spoolman_api.create_spool')
def test_spool_overrides_new_filament(mock_create_spool, mock_create_filament, client):
    """Per-spool overrides drive count and merge onto spool_data per index."""
    mock_create_filament.return_value = {'id': 7}
    mock_create_spool.side_effect = [{'id': 200}, {'id': 201}]

    payload = {
        "filament_data": {"name": "Prusament PLA", "material": "PLA", "extra": {}},
        "spool_data": {
            "initial_weight": 1000,
            "spool_weight": 215,
            "location": "A1",
            "extra": {"needs_label_print": True},
        },
        "quantity": 99,  # ignored when spool_overrides is present
        "spool_overrides": [
            {
                "initial_weight": 998,
                "extra": {"prusament_manufacturing_date": "2026-03-12"},
                "product_url": "https://prusament.com/spool/1/aaa/",
            },
            {
                "initial_weight": 1003,
                "extra": {"prusament_manufacturing_date": "2026-03-13"},
                "product_url": "https://prusament.com/spool/2/bbb/",
            },
        ],
    }

    response = client.post('/api/create_inventory_wizard', json=payload)
    assert response.status_code == 200
    assert response.json['success'] is True
    assert response.json['created_spools'] == [200, 201]

    assert mock_create_spool.call_count == 2

    spool_one = mock_create_spool.call_args_list[0][0][0]
    spool_two = mock_create_spool.call_args_list[1][0][0]

    assert spool_one['initial_weight'] == 998
    assert spool_one['spool_weight'] == 215  # default preserved
    assert spool_one['filament_id'] == 7
    assert spool_one['product_url'] == "https://prusament.com/spool/1/aaa/"
    # Extras merged: per-spool field added, wizard-wide field preserved.
    assert spool_one['extra']['needs_label_print'] is True
    assert spool_one['extra']['prusament_manufacturing_date'] == "2026-03-12"

    assert spool_two['initial_weight'] == 1003
    assert spool_two['extra']['needs_label_print'] is True
    assert spool_two['extra']['prusament_manufacturing_date'] == "2026-03-13"

@patch('app.spoolman_api.create_filament')
@patch('app.spoolman_api.create_spool')
def test_spool_overrides_existing_filament(mock_create_spool, mock_create_filament, client):
    """When filament_id is provided, no filament create/update happens but
    per-spool overrides still apply correctly across N spools."""
    mock_create_spool.side_effect = [{'id': 300}, {'id': 301}]

    payload = {
        "filament_id": 42,
        "spool_data": {"initial_weight": 1000, "location": "B2", "extra": {}},
        "spool_overrides": [
            {"initial_weight": 996},
            {"initial_weight": 1001},
        ],
    }

    with patch('app.spoolman_api.get_filament', return_value={'id': 42, 'archived': False}):
        response = client.post('/api/create_inventory_wizard', json=payload)
    assert response.status_code == 200
    assert response.json['filament_id'] == 42
    assert response.json['created_spools'] == [300, 301]

    mock_create_filament.assert_not_called()
    assert mock_create_spool.call_count == 2
    assert mock_create_spool.call_args_list[0][0][0]['initial_weight'] == 996
    assert mock_create_spool.call_args_list[0][0][0]['filament_id'] == 42
    assert mock_create_spool.call_args_list[1][0][0]['initial_weight'] == 1001

def test_required_spool_extras_includes_prusament_fields():
    """Without auto-registering these at startup, every per-spool Prusament
    scan submit failed with 400 'Unknown extra field prusament_*'. Pin the
    list so a refactor can't drop them silently."""
    from spoolman_api import REQUIRED_SPOOL_EXTRAS
    keys = [k for k, _name, _ftype in REQUIRED_SPOOL_EXTRAS]
    assert 'prusament_manufacturing_date' in keys
    assert 'prusament_length_m' in keys
    # Both are text-type so sanitize_outbound_data's literal-quote behavior
    # round-trips them through Spoolman's string validator.
    for _k, _name, ftype in REQUIRED_SPOOL_EXTRAS:
        assert ftype == 'text', f"{_k} must stay text-type for Spoolman compat"


def test_ensure_required_extras_registers_spool_side(monkeypatch):
    """Confirm the startup hook actually walks REQUIRED_SPOOL_EXTRAS and
    calls ensure_extra_field('spool', ...) for each. A previous version
    only registered filament-side extras and silently broke per-spool
    scans on any Spoolman that hadn't been seeded by setup_fields.py."""
    import spoolman_api
    calls = []
    monkeypatch.setattr(
        spoolman_api,
        'ensure_extra_field',
        lambda entity, key, name, ftype: calls.append((entity, key)),
    )
    spoolman_api.ensure_required_extras()
    spool_keys = {key for entity, key in calls if entity == 'spool'}
    assert 'prusament_manufacturing_date' in spool_keys
    assert 'prusament_length_m' in spool_keys
    filament_keys = {key for entity, key in calls if entity == 'filament'}
    assert 'nozzle_temp_max' in filament_keys, "must not regress filament extras"


@patch('app.spoolman_api.create_filament')
@patch('app.spoolman_api.create_spool')
def test_spool_overrides_partial_row_uses_defaults(mock_create_spool, mock_create_filament, client):
    """A row with no scan must still produce a spool — the per-spool override
    list can mix populated entries with empty {} and the backend fills the
    blanks from spool_data. Mirrors the user's UX where row 3 is left empty
    while rows 1 and 2 are scanned."""
    mock_create_filament.return_value = {'id': 8}
    mock_create_spool.side_effect = [
        {'id': 400}, {'id': 401}, {'id': 402},
    ]
    payload = {
        "filament_data": {"name": "PLA", "material": "PLA", "extra": {}},
        "spool_data": {"initial_weight": 1000, "spool_weight": 215, "extra": {}},
        "spool_overrides": [
            {"initial_weight": 998, "extra": {"prusament_manufacturing_date": '"2026-03-12"'}},
            {},  # blank row → uses spool_data defaults
            {"initial_weight": 1003, "extra": {"prusament_manufacturing_date": '"2026-03-14"'}},
        ],
    }
    response = client.post('/api/create_inventory_wizard', json=payload)
    assert response.status_code == 200
    assert response.json['success'] is True
    assert len(response.json['created_spools']) == 3

    spools = [c[0][0] for c in mock_create_spool.call_args_list]
    assert spools[0]['initial_weight'] == 998
    assert spools[1]['initial_weight'] == 1000  # default
    assert spools[1]['spool_weight'] == 215     # default
    assert 'prusament_manufacturing_date' not in spools[1].get('extra', {})  # no scan extras
    assert spools[2]['initial_weight'] == 1003


@patch('app.spoolman_api.create_filament')
@patch('app.spoolman_api.create_spool')
def test_spool_overrides_extras_deep_merge_preserves_wizard_extras(mock_create_spool, mock_create_filament, client):
    """The wizard sets things like needs_label_print on every spool. A naive
    payload.update would replace the whole extras dict and wipe those flags.
    Confirm the merge keeps wizard-wide extras AND the per-spool ones."""
    mock_create_filament.return_value = {'id': 9}
    mock_create_spool.return_value = {'id': 500}
    payload = {
        "filament_data": {"name": "PLA", "material": "PLA", "extra": {}},
        "spool_data": {
            "initial_weight": 1000,
            "extra": {
                "needs_label_print": True,
                "purchase_url": '"https://example.com/buy"',
            },
        },
        "spool_overrides": [
            {"extra": {"prusament_manufacturing_date": '"2026-03-12"'}},
        ],
    }
    response = client.post('/api/create_inventory_wizard', json=payload)
    assert response.status_code == 200
    sent_extras = mock_create_spool.call_args_list[0][0][0]['extra']
    assert sent_extras['needs_label_print'] is True
    assert sent_extras['purchase_url'] == '"https://example.com/buy"'
    assert sent_extras['prusament_manufacturing_date'] == '"2026-03-12"'


@patch('app.spoolman_api.create_filament')
@patch('app.spoolman_api.create_spool')
def test_wizard_returns_failure_when_all_spools_fail(mock_create_spool, mock_create_filament, client):
    """If every spool create fails (e.g. unknown extra-field rejection from
    Spoolman) the parent endpoint must return success=False. Previously it
    returned success=True with an empty created_spools list, leaving the
    user with an orphan filament and no warning that nothing else worked."""
    mock_create_filament.return_value = {'id': 50}
    mock_create_spool.return_value = None  # every spool POST fails

    payload = {
        "filament_data": {"name": "Doomed PLA", "material": "PLA", "extra": {}},
        "spool_data": {"initial_weight": 1000, "extra": {}},
        "quantity": 2,
    }

    response = client.post('/api/create_inventory_wizard', json=payload)
    assert response.status_code == 200
    data = response.json
    assert data['success'] is False
    assert data['created_spools'] == []
    assert 'msg' in data and 'spool' in data['msg'].lower()
    # Filament was still created — that part succeeded — so the response
    # should still expose its id so the caller can decide whether to clean up.
    assert data['filament_id'] == 50
