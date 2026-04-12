import pytest
from unittest.mock import patch, MagicMock
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../inventory-hub')))

@pytest.fixture
def mock_app():
    with patch("app.spoolman_api"), \
         patch("app.config_loader"), \
         patch("app.state") as mock_state:
        
        mock_state.AUDIT_SESSION = {"active": False}
        mock_state.UNDO_STACK = []
        mock_state.RECENT_LOGS = []
        mock_state.ACKNOWLEDGED_FILABRIDGE_ERRORS = set()
        
        import app as flask_app
        flask_app.app.config['TESTING'] = True
        yield flask_app.app.test_client()

def test_fb_recovery_spools(mock_app):
    with patch("app.config_loader.load_config") as mock_load:
        mock_load.return_value = {
            "printer_map": {
                "l-1": {"printer_name": "TestPrinter"}
            }
        }
        with patch("app.spoolman_api.get_spools_at_location_detailed") as mock_detailed:
            mock_detailed.return_value = [{"id": 1, "extra": {}}]
            
            res = mock_app.get("/api/fb_recovery_spools?printer_name=TestPrinter")
            assert res.status_code == 200
            data = res.get_json()
            assert data["success"] is True
            assert len(data["spools"]) == 1
            assert data["spools"][0]["id"] == 1

def test_fb_aggressive_parse(mock_app):
    with patch("app.config_loader.get_api_urls", return_value=("http://spool", "http://fb/api")), \
         patch("app.prusalink_api.fetch_printer_credentials", return_value={"ip_address": "1.2.3.4", "api_key": "abc"}), \
         patch("app.prusalink_api.download_gcode_and_parse_usage", return_value={0: 10.5}), \
         patch("app.config_loader.load_config") as mock_load, \
         patch("app.spoolman_api.get_spools_at_location", return_value=[123]), \
         patch("app.spoolman_api.get_spool", return_value={"id": 123, "used_weight": 10}), \
         patch("app.spoolman_api.format_spool_display", return_value={"color": "000000"}), \
         patch("app.spoolman_api.update_spool", return_value=True) as mock_update, \
         patch("app.prusalink_api.acknowledge_filabridge_error", return_value=True) as mock_ack:
         
        mock_load.return_value = {
            "printer_map": {
                "l-1": {"printer_name": "MyPrinter", "position": 0}
            }
        }
        
        res = mock_app.post("/api/fb_aggressive_parse", json={
            "printer_name": "MyPrinter",
            "filename": "test.gcode",
            "error_id": "err_1"
        })
        
        assert res.status_code == 200
        data = res.get_json()
        assert data["success"] is True
        
        # Verify it deducted 10.5g
        mock_update.assert_called_once_with(123, {"used_weight": 20.5})
        mock_ack.assert_called_once_with("http://fb/api", "err_1")

def test_prusalink_parser_fast_fetch():
    import prusalink_api as pa
    
    with patch("prusalink_api.requests.get") as mock_get:
        # Mock Range Request Success
        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.status_code = 206
        mock_resp.text = "; metadata block\n; filament used [g] = 3.14, 5.22\n; end"
        mock_get.return_value = mock_resp
        
        usage = pa.download_gcode_and_parse_usage("1.2.3.4", "key", "test.bgcode")
        assert usage == {0: 3.14, 1: 5.22}
        assert mock_get.call_count == 1
        assert pa.FB_PARSE_STATUS == "Fast"

def test_prusalink_parser_ram_fallback():
    import prusalink_api as pa
    
    with patch("prusalink_api.requests.get") as mock_get:
        # 1. Mock Range Request Fail (e.g. 416 or just 200 without meta)
        fail_resp = MagicMock()
        fail_resp.ok = False
        fail_resp.status_code = 416
        
        # 2. Mock Fallback RAM Success
        success_resp = MagicMock()
        success_resp.ok = True
        success_resp.status_code = 200
        success_resp.text = "; full file\n; filament used [g] = 10.0, 20.0"
        
        mock_get.side_effect = [fail_resp, success_resp]
        
        usage = pa.download_gcode_and_parse_usage("1.2.3.4", "key", "test.bgcode")
        assert usage == {0: 10.0, 1: 20.0}
        assert mock_get.call_count == 2
        assert "RAM" in pa.FB_PARSE_STATUS

def test_fb_error_snapshotting(mock_app):
    import json
    with patch("app.config_loader.get_api_urls", return_value=("http://spool", "http://fb/api")), \
         patch("app.requests.get") as mock_get, \
         patch("app.config_loader.load_config") as mock_load, \
         patch("app.spoolman_api.get_spools_at_location_detailed", return_value=[{"id": 999, "extra": {}}]):
         
         # Mock Spoolman and FilaBridge Health Checks
         health_resp = MagicMock()
         health_resp.ok = True
         
         # Mock FilaBridge Print Errors
         err_resp = MagicMock()
         err_resp.ok = True
         err_resp.json.return_value = {
             "errors": [{"id": "err_snap_1", "printer_name": "TestSnapPrinter", "acknowledged": False}]
         }
         mock_get.side_effect = [health_resp, health_resp, err_resp]
         
         mock_load.return_value = {
             "printer_map": {"l-1": {"printer_name": "TestSnapPrinter"}},
             "auto_recover_filabridge_errors": False
         }
         
         # Call the log poller which triggers the snapshot hook
         mock_app.get("/api/logs")
         
         snap_path = os.path.join(os.path.dirname(__file__), "../inventory-hub/data/filabridge_error_snapshots.json")
         assert os.path.exists(snap_path)
         with open(snap_path, "r") as f:
             data = json.load(f)
             assert "err_snap_1" in data
             assert data["err_snap_1"][0]["id"] == 999
