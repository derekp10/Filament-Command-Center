"""
Tests for the /api/printer_state/<toolhead_id> endpoint used by the
"warn before reassigning during an active print" pre-check.

Contract:
  - Unknown toolhead → {"known": false, "reason": "not_in_printer_map"}
  - PrusaLink unreachable / credentials missing → {"known": false, ...}
  - PrusaLink reports state → {"known": true, "state": "...", "is_active": bool,
                               "printer_name": "..."}

Runs against the live container (credentials + printer_map provided by config).
"""
from __future__ import annotations

import os
import sys
from unittest.mock import patch

import pytest
import requests

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import app as app_module  # noqa: E402


@pytest.fixture
def client():
    app_module.app.config["TESTING"] = True
    return app_module.app.test_client()


def test_printer_state_unknown_toolhead_returns_not_in_printer_map(client):
    resp = client.get("/api/printer_state/NOT-A-TOOLHEAD")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["known"] is False
    assert body["reason"] == "not_in_printer_map"


def test_printer_state_case_insensitive_toolhead_lookup(client):
    """The backend normalizes the toolhead ID to uppercase."""
    # Pick a known printer_map entry — use a mock printer_map to avoid depending
    # on the real config.
    fake_map = {"CORE1-M0": {"printer_name": "TestPrinter", "position": 0}}
    with patch.object(
        app_module.config_loader, "load_config", return_value={"printer_map": fake_map}
    ), patch.object(
        app_module.prusalink_api, "get_printer_state",
        return_value={"state": "IDLE", "is_active": False},
    ):
        resp = client.get("/api/printer_state/core1-m0")
    body = resp.get_json()
    assert body["known"] is True
    assert body["state"] == "IDLE"
    assert body["is_active"] is False
    assert body["printer_name"] == "TestPrinter"


def test_printer_state_unreachable_reports_known_false(client):
    """If PrusaLink is unreachable, get_printer_state returns None → endpoint
    surfaces {'known': False, 'reason': 'prusalink_unreachable'}."""
    fake_map = {"CORE1-M0": {"printer_name": "TestPrinter", "position": 0}}
    with patch.object(
        app_module.config_loader, "load_config", return_value={"printer_map": fake_map}
    ), patch.object(
        app_module.prusalink_api, "get_printer_state", return_value=None
    ):
        resp = client.get("/api/printer_state/CORE1-M0")
    body = resp.get_json()
    assert body["known"] is False
    assert body["reason"] == "prusalink_unreachable"


def test_printer_state_active_state_is_flagged(client):
    """PRINTING / PAUSED / BUSY states should set is_active=True."""
    fake_map = {"XL-3": {"printer_name": "XL", "position": 2}}
    with patch.object(
        app_module.config_loader, "load_config", return_value={"printer_map": fake_map}
    ), patch.object(
        app_module.prusalink_api, "get_printer_state",
        return_value={"state": "PRINTING", "is_active": True},
    ):
        resp = client.get("/api/printer_state/XL-3")
    body = resp.get_json()
    assert body["known"] is True
    assert body["is_active"] is True
    assert body["state"] == "PRINTING"


# ---------------------------------------------------------------------------
# Live integration — skipped if container is down.
# ---------------------------------------------------------------------------

def test_printer_state_live_endpoint_returns_well_shaped_body():
    """Hit the live container. This test asserts the response shape only,
    since we can't force a real printer into PRINTING during a unit run."""
    base_url = os.environ.get("INVENTORY_HUB_URL", "http://localhost:8000")
    try:
        r = requests.get(f"{base_url}/api/printer_state/NOT-A-TOOLHEAD", timeout=5)
    except requests.RequestException:
        pytest.skip("Container not responding")
    assert r.status_code == 200
    body = r.json()
    assert body["known"] is False
