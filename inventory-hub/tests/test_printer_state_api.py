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
        app_module.locations_db, "get_active_printer_map", return_value=fake_map
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
        app_module.locations_db, "get_active_printer_map", return_value=fake_map
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
        app_module.locations_db, "get_active_printer_map", return_value=fake_map
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
# 13.8 Part A — narrower active-print state classification in get_printer_state
# ---------------------------------------------------------------------------

import prusalink_api  # noqa: E402


class _FakeResp:
    def __init__(self, ok, body):
        self.ok = ok
        self._body = body
    def json(self):
        return self._body


@pytest.fixture
def fake_creds(monkeypatch):
    """Stub `fetch_printer_credentials` so get_printer_state doesn't try to
    talk to the real filabridge."""
    monkeypatch.setattr(
        prusalink_api, "fetch_printer_credentials",
        lambda fb_url, name: {"ip_address": "1.2.3.4", "api_key": "test"},
    )


@pytest.mark.parametrize("state_str,expected_active", [
    ("PRINTING", True),
    ("PAUSING", True),
    ("RESUMING", True),
    # 13.8 — these used to flag as active and block eject. Now they don't,
    # so Derek's prep-for-swap (heating/paused/operational) flow works.
    ("PAUSED", False),
    ("BUSY", False),
    ("IDLE", False),
    ("OPERATIONAL", False),
    ("FINISHED", False),
    ("STOPPED", False),
    ("ATTENTION", False),
    ("READY", False),
])
def test_v1_state_classification(state_str, expected_active, fake_creds, monkeypatch):
    """13.8 Part A — only PRINTING/PAUSING/RESUMING set is_active=True so
    eject / smart-move / quick-swap don't block on heating-or-paused
    states (Derek's filament-swap prep)."""
    monkeypatch.setattr(
        prusalink_api.requests, "get",
        lambda url, headers=None, timeout=None: _FakeResp(True, {
            "printer": {"state": state_str},
        }),
    )
    result = prusalink_api.get_printer_state("http://filabridge", "TestPrinter")
    assert result is not None, f"expected dict for state={state_str!r}"
    assert result["state"] == state_str
    assert result["is_active"] is expected_active, (
        f"state={state_str!r}: expected is_active={expected_active}, got {result['is_active']}"
    )


def test_legacy_endpoint_paused_no_longer_blocks(fake_creds, monkeypatch):
    """13.8 Part A — legacy /api/printer's `paused` flag used to set
    is_active=True alongside `printing`. Post-fix only the `printing` flag
    counts so paused-mid-print doesn't block the eject Derek wants to do."""
    # v1 endpoint not-ok → falls through to legacy /api/printer.
    call_log = []

    def fake_get(url, headers=None, timeout=None):
        call_log.append(url)
        if "/api/v1/status" in url:
            return _FakeResp(False, {})
        # Legacy endpoint shape
        return _FakeResp(True, {
            "state": {"text": "Paused", "flags": {"paused": True, "printing": False}},
        })

    monkeypatch.setattr(prusalink_api.requests, "get", fake_get)
    result = prusalink_api.get_printer_state("http://filabridge", "TestPrinter")
    assert result is not None
    assert result["is_active"] is False, (
        f"legacy `paused` flag must no longer flag is_active; got {result!r}"
    )


def test_legacy_endpoint_printing_still_blocks(fake_creds, monkeypatch):
    """13.8 Part A guard — legacy `printing` flag still correctly
    classifies the print as active so we don't accidentally unblock
    eject during a real running print."""
    def fake_get(url, headers=None, timeout=None):
        if "/api/v1/status" in url:
            return _FakeResp(False, {})
        return _FakeResp(True, {
            "state": {"text": "Printing", "flags": {"paused": False, "printing": True}},
        })

    monkeypatch.setattr(prusalink_api.requests, "get", fake_get)
    result = prusalink_api.get_printer_state("http://filabridge", "TestPrinter")
    assert result is not None
    assert result["is_active"] is True


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
