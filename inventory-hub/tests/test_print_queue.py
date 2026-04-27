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
