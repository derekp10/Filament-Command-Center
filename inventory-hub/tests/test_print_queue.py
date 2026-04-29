import pytest
import sys
import os
import json
from unittest.mock import patch, MagicMock

# Add parent directory to python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app import app
import spoolman_api

@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client

def test_get_pending_queue(client):
    """Test fetching the print queue backlog and filtering"""
    with patch('requests.get') as mock_get, patch('config_loader.get_api_urls', return_value=('http://mock', 'http://mock')):
        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.json.return_value = [{"id": 1, "registered": "2023-01-01"}]
        mock_get.return_value = mock_resp
        
        res = client.get('/api/print_queue/pending?filter=spool&sort=id_asc')
        assert res.status_code == 200
        data = res.get_json()
        assert data['success'] is True
        assert len(data['items']) == 1
        assert data['items'][0]['type'] == 'spool'

def test_mark_printed_rejects_legacy(client):
    """Test that manual mark printed rejects non-numeric legacy IDs"""
    res = client.post('/api/print_queue/mark_printed', json={"id": "legacy_foo", "type": "spool"})
    data = res.get_json()
    assert data['success'] is False
    assert "Legacy IDs cannot be manually marked" in data['msg']

def test_mark_printed_success(client):
    """Test that manual mark printed successfully clears the flag"""
    with patch('spoolman_api.get_spool') as mock_get, patch('spoolman_api.update_spool') as mock_update:
        mock_get.return_value = {"id": 10, "extra": {"needs_label_print": True}}
        mock_update.return_value = True
        
        res = client.post('/api/print_queue/mark_printed', json={"id": 10, "type": "spool"})
        data = res.get_json()
        assert data['success'] is True
        
        # Check that update_spool was called with needs_label_print = False
        mock_update.assert_called_once()
        args, _ = mock_update.call_args
        assert args[0] == 10
        assert args[1]['extra']['needs_label_print'] is False

def test_identify_scan_barcode_clears_flag(client):
    """Test that a physical barcode scan clears the needs_label_print flag and sets label_printed"""
    with patch('logic.resolve_scan') as mock_resolve, patch('spoolman_api.get_spool') as mock_get, patch('spoolman_api.update_spool') as mock_update, patch('state.add_log_entry') as mock_log, patch('spoolman_api.format_spool_display', return_value={'text':'foo', 'color':'#fff'}):
        mock_resolve.return_value = {"type": "spool", "id": 10}
        mock_get.return_value = {"id": 10, "extra": {"needs_label_print": True}}
        mock_update.return_value = {"id": 10} # Success
        
        res = client.post('/api/identify_scan', json={"text": "ID:10", "source": "barcode"})
        data = res.get_json()
        assert data['type'] == 'spool'
        
        # It should update the spool to clear the flag
        mock_update.assert_called_once()
        args, _ = mock_update.call_args
        assert args[1]['extra']['needs_label_print'] is False
        
        # Check success log
        mock_log.assert_called_once()
        assert "Label Verified" in mock_log.call_args[0][0]

def test_identify_scan_barcode_filament(client):
    """Test that a physical barcode scan on a filament clears needs_label_print"""
    with patch('logic.resolve_scan') as mock_resolve, patch('spoolman_api.get_filament') as mock_get, patch('spoolman_api.update_filament') as mock_update, patch('state.add_log_entry') as mock_log:
        mock_resolve.return_value = {"type": "filament", "id": 5}
        mock_get.return_value = {"id": 5, "extra": {"needs_label_print": True}}
        mock_update.return_value = {"id": 5} # Success
        
        res = client.post('/api/identify_scan', json={"text": "FIL:5", "source": "barcode"})
        data = res.get_json()
        assert data['type'] == 'filament'
        
        mock_update.assert_called_once()
        args, _ = mock_update.call_args
        assert args[1]['extra']['needs_label_print'] is False

def test_identify_scan_barcode_database_rejection(client):
    """A failed Spoolman update on label-confirm scan must surface as ERROR
    (not WARNING) and include the Spoolman error body so the user can see
    WHY the update was rejected. The 2026-04-27 prod outage stayed
    undiagnosed for hours because this used to be a generic warning with
    no Spoolman body — fixed in Phase B."""
    with patch('logic.resolve_scan') as mock_resolve, patch('spoolman_api.get_spool') as mock_get, patch('spoolman_api.update_spool') as mock_update, patch('state.add_log_entry') as mock_log, patch('spoolman_api.format_spool_display', return_value={'text':'foo', 'color':'#fff'}):
        mock_resolve.return_value = {"type": "spool", "id": 10}
        mock_get.return_value = {"id": 10, "extra": {"needs_label_print": True}}
        # Simulate Spoolman API rejecting the payload (e.g. 400 Bad Request).
        # In real code, update_spool sets LAST_SPOOLMAN_ERROR before
        # returning None — patch the attribute so the code path can read it.
        mock_update.return_value = None
        import spoolman_api
        spoolman_api.LAST_SPOOLMAN_ERROR = "HTTP 400: Unknown extra field"

        try:
            res = client.post('/api/identify_scan', json={"text": "ID:10", "source": "barcode"})
            data = res.get_json()
            assert data['type'] == 'spool'

            # It should attempt the update
            mock_update.assert_called_once()

            # Check failure log: ERROR severity (was WARNING pre-fix), and
            # message must include the Spoolman error body for diagnosis.
            mock_log.assert_called_once()
            log_msg = mock_log.call_args[0][0]
            log_level = mock_log.call_args[0][1]
            assert "Failed to verify" in log_msg
            assert "Unknown extra field" in log_msg, (
                f"Spoolman error body must be surfaced in the activity log; got: {log_msg!r}"
            )
            assert log_level == "ERROR"
        finally:
            spoolman_api.LAST_SPOOLMAN_ERROR = None

def test_identify_scan_keyboard_keeps_flag(client):
    """Test that manual keyboard typing does NOT clear the needs_label_print flag"""
    with patch('logic.resolve_scan') as mock_resolve, patch('spoolman_api.get_spool') as mock_get, patch('spoolman_api.update_spool') as mock_update, patch('spoolman_api.format_spool_display', return_value={'text':'foo', 'color':'#fff'}):
        mock_resolve.return_value = {"type": "spool", "id": 10}
        mock_get.return_value = {"id": 10, "extra": {"needs_label_print": True}}

        res = client.post('/api/identify_scan', json={"text": "ID:10", "source": "keyboard"})
        data = res.get_json()
        assert data['type'] == 'spool'

        # It should NOT update the spool
        mock_update.assert_not_called()


# ---------------------------------------------------------------------------
# 3.7B — verify-on-scan tri-state (true/null/false) coverage.
# Bug history: pre-fix, the inner gate was
#   needs_print = raw_flag is True or raw_flag == 'true' or raw_flag == 'True'
# which treated null/missing the same as False, silently skipping verification
# on legacy records (or any record created via a path that didn't auto-flag).
# The new gate inverts to "already_verified iff raw_flag is False" so True AND
# null both fire the verify.
# ---------------------------------------------------------------------------

def test_identify_scan_clears_null_flag_spool(client):
    """A barcode scan on a spool with `needs_label_print` absent (None) MUST
    fire the verify and flip the flag to False. This is the previously-broken
    path — legacy spools predating the feature, or any spool created via a
    non-wizard path that didn't auto-flag, would silently no-op pre-fix."""
    with patch('logic.resolve_scan') as mock_resolve, patch('spoolman_api.get_spool') as mock_get, patch('spoolman_api.update_spool') as mock_update, patch('state.add_log_entry') as mock_log, patch('spoolman_api.format_spool_display', return_value={'text':'foo', 'color':'#fff'}):
        mock_resolve.return_value = {"type": "spool", "id": 11}
        # No needs_label_print key at all → null/missing state.
        mock_get.return_value = {"id": 11, "extra": {}}
        mock_update.return_value = {"id": 11}

        res = client.post('/api/identify_scan', json={"text": "ID:11", "source": "barcode"})
        assert res.get_json()['type'] == 'spool'

        mock_update.assert_called_once()
        args, _ = mock_update.call_args
        assert args[1]['extra']['needs_label_print'] is False

        mock_log.assert_called_once()
        assert "Label Verified" in mock_log.call_args[0][0]


def test_identify_scan_skips_when_explicitly_false_spool(client):
    """A spool already marked False (positively verified) should NOT trigger
    another update — the only short-circuit case in the new tri-state logic."""
    with patch('logic.resolve_scan') as mock_resolve, patch('spoolman_api.get_spool') as mock_get, patch('spoolman_api.update_spool') as mock_update, patch('state.add_log_entry') as mock_log, patch('spoolman_api.format_spool_display', return_value={'text':'foo', 'color':'#fff'}):
        mock_resolve.return_value = {"type": "spool", "id": 12}
        mock_get.return_value = {"id": 12, "extra": {"needs_label_print": False}}

        res = client.post('/api/identify_scan', json={"text": "ID:12", "source": "barcode"})
        assert res.get_json()['type'] == 'spool'

        mock_update.assert_not_called()
        mock_log.assert_called_once()
        assert "already verified" in mock_log.call_args[0][0]


@pytest.mark.parametrize("flag_value", ['false', 'False'])
def test_identify_scan_skips_when_string_false_spool(client, flag_value):
    """Stringified 'false'/'False' must also short-circuit — Spoolman boolean
    extras can round-trip as strings depending on parse_inbound_data."""
    with patch('logic.resolve_scan') as mock_resolve, patch('spoolman_api.get_spool') as mock_get, patch('spoolman_api.update_spool') as mock_update, patch('spoolman_api.format_spool_display', return_value={'text':'foo', 'color':'#fff'}):
        mock_resolve.return_value = {"type": "spool", "id": 13}
        mock_get.return_value = {"id": 13, "extra": {"needs_label_print": flag_value}}

        client.post('/api/identify_scan', json={"text": "ID:13", "source": "barcode"})
        mock_update.assert_not_called()


def test_identify_scan_clears_null_flag_filament(client):
    """Mirror of the spool null-state test for the filament branch."""
    with patch('logic.resolve_scan') as mock_resolve, patch('spoolman_api.get_filament') as mock_get, patch('spoolman_api.update_filament') as mock_update, patch('state.add_log_entry') as mock_log:
        mock_resolve.return_value = {"type": "filament", "id": 6}
        mock_get.return_value = {"id": 6, "extra": {}}  # null flag
        mock_update.return_value = {"id": 6}

        res = client.post('/api/identify_scan', json={"text": "FIL:6", "source": "barcode"})
        assert res.get_json()['type'] == 'filament'

        mock_update.assert_called_once()
        args, _ = mock_update.call_args
        assert args[1]['extra']['needs_label_print'] is False
        mock_log.assert_called_once()
        assert "Label & Sample Verified" in mock_log.call_args[0][0]


def test_identify_scan_legacy_barcode_does_not_clear_spool(client):
    """Legacy barcodes (text not starting with `ID:`) must NOT clear the flag —
    legacy is the OLD label, and the whole reason `needs_label_print` exists.
    The text-prefix gate on app.py:1351 enforces this."""
    with patch('logic.resolve_scan') as mock_resolve, patch('spoolman_api.get_spool') as mock_get, patch('spoolman_api.update_spool') as mock_update, patch('spoolman_api.format_spool_display', return_value={'text':'foo', 'color':'#fff'}):
        # Legacy barcode '39' resolves to spool #229, but `text` lacks the ID: prefix.
        mock_resolve.return_value = {"type": "spool", "id": 229}
        mock_get.return_value = {"id": 229, "extra": {"needs_label_print": True}}

        client.post('/api/identify_scan', json={"text": "39", "source": "barcode"})
        mock_update.assert_not_called()


# ---------------------------------------------------------------------------
# 3.7A — wizard auto-flags new spools and filaments with needs_label_print=true
# so they auto-populate the Backlog. Edit-mode goes through a different
# endpoint so existing flag state is preserved.
# ---------------------------------------------------------------------------

def test_create_inventory_wizard_auto_flags_new_spool(client):
    """A wizard create with no explicit needs_label_print must default to True
    on the spool extra so the new spool lands in the Backlog immediately."""
    with patch('spoolman_api.create_spool') as mock_create_spool:
        mock_create_spool.return_value = {"id": 99}

        client.post('/api/create_inventory_wizard', json={
            "filament_id": 7,  # existing filament — skip filament create
            "spool_data": {"extra": {}},
            "quantity": 1,
        })

        mock_create_spool.assert_called_once()
        payload = mock_create_spool.call_args[0][0]
        assert payload['extra']['needs_label_print'] is True


def test_create_inventory_wizard_auto_flags_new_filament(client):
    """A wizard create that produces a brand-new filament must default
    needs_label_print=True on the filament extra."""
    with patch('spoolman_api.create_filament') as mock_create_fil, \
         patch('spoolman_api.create_spool') as mock_create_spool:
        mock_create_fil.return_value = {"id": 50}
        mock_create_spool.return_value = {"id": 100}

        client.post('/api/create_inventory_wizard', json={
            "filament_data": {"name": "TestFil", "extra": {}},
            "spool_data": {"extra": {}},
            "quantity": 1,
        })

        mock_create_fil.assert_called_once()
        fil_payload = mock_create_fil.call_args[0][0]
        assert fil_payload['extra']['needs_label_print'] is True


def test_create_inventory_wizard_respects_explicit_flag(client):
    """If the wizard payload explicitly sets needs_label_print=false (e.g. an
    automation/clone path that already verified the label), the backend must
    not stomp it back to True."""
    with patch('spoolman_api.create_spool') as mock_create_spool:
        mock_create_spool.return_value = {"id": 101}

        client.post('/api/create_inventory_wizard', json={
            "filament_id": 7,
            "spool_data": {"extra": {"needs_label_print": False}},
            "quantity": 1,
        })

        mock_create_spool.assert_called_once()
        payload = mock_create_spool.call_args[0][0]
        assert payload['extra']['needs_label_print'] is False


# ---------------------------------------------------------------------------
# 3.6 — Legacy-ID disambiguation: when 2+ spools share a legacy id,
# resolve_scan returns {'type': 'ambiguous', ...} so the frontend can prompt
# the user instead of silently picking the first non-empty candidate.
# ---------------------------------------------------------------------------

def _mock_spool(sid, fil_id, *, weight=500, location='', archived=False):
    return {
        'id': sid,
        'remaining_weight': weight,
        'location': location,
        'archived': archived,
        'filament': {
            'id': fil_id,
            'name': 'White',
            'material': 'PETG',
            'vendor': {'name': 'Creality'},
            'color_hex': 'FFFFFF',
        },
        'extra': {},
    }


def _patch_legacy_lookup_responses(mock_get, *, fil_legacy_id, fil_id, spools):
    """Make two-call sequence (filament list, then spool list) deterministic
    for `find_spools_by_legacy_id`. parse_inbound_data is the identity for
    plain dicts so we can pass raw structures."""
    fil_resp = MagicMock()
    fil_resp.ok = True
    fil_resp.json.return_value = [{
        'id': fil_id,
        'external_id': fil_legacy_id,
        'name': 'White',
        'material': 'PETG',
        'vendor': {'name': 'Creality'},
    }]
    spool_resp = MagicMock()
    spool_resp.ok = True
    spool_resp.json.return_value = spools
    mock_get.side_effect = [fil_resp, spool_resp]


def test_find_spools_by_legacy_id_returns_all_candidates():
    """The new helper returns every matching spool (sorted: non-empty first)."""
    import logic  # noqa: E402 — import lazily so the patch above takes effect
    with patch('requests.get') as mock_get, \
         patch('config_loader.get_api_urls', return_value=('http://mock', 'http://mock')):
        _patch_legacy_lookup_responses(
            mock_get, fil_legacy_id='39', fil_id=37,
            spools=[
                _mock_spool(229, 37, weight=1000),
                _mock_spool(230, 37, weight=5),     # near-empty
                _mock_spool(231, 37, weight=750),
                _mock_spool(99, 99, weight=500),    # different filament — excluded
            ],
        )
        spools = spoolman_api.find_spools_by_legacy_id('39')
        ids = [s['id'] for s in spools]
        assert ids == [229, 231, 230], f"expected non-empty first, got {ids}"
        del logic  # unused outside the patched scope


def test_find_spool_by_legacy_id_back_compat_picks_first():
    """The old `find_spool_by_legacy_id` is a thin wrapper that now picks the
    first candidate (non-empty preference is preserved by the underlying
    sort). Existing callers must keep working."""
    with patch('requests.get') as mock_get, \
         patch('config_loader.get_api_urls', return_value=('http://mock', 'http://mock')):
        _patch_legacy_lookup_responses(
            mock_get, fil_legacy_id='39', fil_id=37,
            spools=[_mock_spool(229, 37, weight=1000)],
        )
        assert spoolman_api.find_spool_by_legacy_id('39') == 229


def test_find_spools_by_legacy_id_no_match():
    """No filament with the legacy id → empty list."""
    with patch('requests.get') as mock_get, \
         patch('config_loader.get_api_urls', return_value=('http://mock', 'http://mock')):
        fil_resp = MagicMock()
        fil_resp.ok = True
        fil_resp.json.return_value = [{'id': 1, 'external_id': '999', 'name': 'X'}]
        mock_get.return_value = fil_resp
        assert spoolman_api.find_spools_by_legacy_id('39') == []


def test_resolve_scan_ambiguous_for_legacy_prefix():
    """LEGACY:39 with 2+ matching spools → ambiguous response carrying the
    candidate list."""
    import logic
    with patch('spoolman_api.find_spools_by_legacy_id') as mock_find, \
         patch('spoolman_api.format_spool_display', return_value={'text': 'Spool snippet'}):
        mock_find.return_value = [
            _mock_spool(229, 37, weight=1000, location='CR'),
            _mock_spool(231, 37, weight=750, location='Unassigned'),
        ]
        result = logic.resolve_scan('LEGACY:39')
        assert result['type'] == 'ambiguous'
        assert result['legacy_id'] == '39'
        assert len(result['candidates']) == 2
        assert {c['id'] for c in result['candidates']} == {229, 231}
        # Display data is denormalized so the picker doesn't need a second round-trip.
        c0 = result['candidates'][0]
        assert c0['vendor_name'] == 'Creality'
        assert c0['material'] == 'PETG'
        assert 'display' in c0


def test_resolve_scan_single_match_still_returns_spool():
    """When only one spool matches the legacy id, behavior is unchanged —
    pure {'type': 'spool', 'id': N}."""
    import logic
    with patch('spoolman_api.find_spools_by_legacy_id') as mock_find:
        mock_find.return_value = [_mock_spool(229, 37, weight=1000)]
        result = logic.resolve_scan('LEGACY:39')
        assert result == {'type': 'spool', 'id': 229}


def test_resolve_scan_pure_number_ambiguous():
    """A raw number scan that falls through to legacy spool lookup (Priority 3
    of resolve_scan's pure-number stack) should also surface ambiguity."""
    import logic
    with patch('spoolman_api.get_spool', return_value=None), \
         patch('spoolman_api.get_filament', return_value=None), \
         patch('spoolman_api.find_spools_by_legacy_id') as mock_find, \
         patch('spoolman_api.format_spool_display', return_value={'text': 'Spool snippet'}):
        mock_find.return_value = [
            _mock_spool(229, 37),
            _mock_spool(231, 37),
        ]
        result = logic.resolve_scan('39')
        assert result['type'] == 'ambiguous'
        assert result['legacy_id'] == '39'


def test_identify_scan_passes_ambiguous_to_frontend(client):
    """The /api/identify_scan endpoint must surface the ambiguous payload
    intact — frontend duplicate_picker depends on the candidates list."""
    with patch('logic.resolve_scan') as mock_resolve, \
         patch('state.add_log_entry'):
        mock_resolve.return_value = {
            'type': 'ambiguous',
            'legacy_id': '39',
            'candidates': [
                {'id': 229, 'remaining_weight': 1000, 'location': 'CR',
                 'vendor_name': 'Creality', 'material': 'PETG',
                 'filament_name': 'White', 'archived': False, 'display': '#229'},
                {'id': 231, 'remaining_weight': 750, 'location': '',
                 'vendor_name': 'Creality', 'material': 'PETG',
                 'filament_name': 'White', 'archived': False, 'display': '#231'},
            ],
        }
        res = client.post('/api/identify_scan', json={'text': 'LEGACY:39', 'source': 'barcode'})
        data = res.get_json()
        assert data['type'] == 'ambiguous'
        assert data['legacy_id'] == '39'
        assert len(data['candidates']) == 2
        assert {c['id'] for c in data['candidates']} == {229, 231}
