"""L324 / L — FilaBridge ↔ Spoolman reconcile utility.

Tests for the new /api/filabridge/reconcile (scan) and
/api/filabridge/reconcile/apply (resolve) endpoints. Uses Flask's
test_client + monkeypatched FilaBridge + Spoolman so we don't depend
on live services.
"""
from __future__ import annotations

import json
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import app as app_module  # noqa: E402


@pytest.fixture
def client():
    app_module.app.config["TESTING"] = True
    return app_module.app.test_client()


def _fb_status_with(mappings: dict):
    """Build a fake FilaBridge /status JSON shape."""
    return {"toolhead_mappings": mappings}


def _patches(fb_payload: dict, get_spool_fn, printer_map=None):
    """Build the standard patch stack the reconcile endpoint needs."""
    if printer_map is None:
        printer_map = {
            "XL-1": {"printer_name": "🦝 XL", "position": 0},
            "XL-2": {"printer_name": "🦝 XL", "position": 1},
        }

    mock_response = MagicMock()
    mock_response.ok = True
    mock_response.status_code = 200
    mock_response.json.return_value = fb_payload

    return [
        patch.object(app_module.config_loader, "get_api_urls",
                     return_value=("http://spoolman", "http://filabridge")),
        patch.object(app_module.config_loader, "load_config",
                     return_value={"printer_map": printer_map}),
        patch.object(app_module.requests, "get", return_value=mock_response),
        patch.object(app_module.spoolman_api, "get_spool", side_effect=get_spool_fn),
        patch.object(app_module.spoolman_api, "format_spool_display",
                     return_value={"text": "Test Display", "color": "#fff"}),
    ]


def test_reconcile_scan_reports_no_mismatches_when_in_sync(client):
    """Spool #42 on FilaBridge th 0 (= XL-1); Spoolman says XL-1. Clean."""
    fb = _fb_status_with({"🦝 XL": {"0": {"spool_id": 42, "printer_name": "🦝 XL"}}})

    def _get(sid):
        return {"id": int(sid), "location": "XL-1"} if int(sid) == 42 else None

    ctx = _patches(fb, _get)
    for m in ctx: m.start()
    try:
        r = client.get("/api/filabridge/reconcile")
    finally:
        for m in reversed(ctx): m.stop()

    body = r.get_json()
    assert body["success"] is True
    assert body["matched"] == 1
    assert body["mismatches"] == []


def test_reconcile_scan_flags_location_disagreement(client):
    """FilaBridge says #42 is on XL-1; Spoolman says it's at CR-CT-1.
    That's a ghost mismatch — should appear in the report."""
    fb = _fb_status_with({"🦝 XL": {"0": {"spool_id": 42, "printer_name": "🦝 XL"}}})

    def _get(sid):
        return {"id": int(sid), "location": "CR-CT-1"} if int(sid) == 42 else None

    ctx = _patches(fb, _get)
    for m in ctx: m.start()
    try:
        r = client.get("/api/filabridge/reconcile")
    finally:
        for m in reversed(ctx): m.stop()

    body = r.get_json()
    assert body["success"] is True
    assert body["matched"] == 0
    assert len(body["mismatches"]) == 1
    mm = body["mismatches"][0]
    assert mm["spool_id"] == 42
    assert mm["fb_location"] == "XL-1"
    assert mm["sm_location"] == "CR-CT-1"
    assert "diverged" in mm["reason"].lower() or "ghost" in mm["reason"].lower()


def test_reconcile_scan_flags_unknown_toolhead_position(client):
    """FilaBridge reports a position with no entry in printer_map. Surface
    it as a mismatch with `fb_location=None` so the UI can offer an unmap."""
    # Position 7 isn't in printer_map (only 0 + 1 are configured).
    fb = _fb_status_with({"🦝 XL": {"7": {"spool_id": 99, "printer_name": "🦝 XL"}}})

    ctx = _patches(fb, lambda sid: {"id": int(sid), "location": ""})
    for m in ctx: m.start()
    try:
        r = client.get("/api/filabridge/reconcile")
    finally:
        for m in reversed(ctx): m.stop()

    body = r.get_json()
    assert body["matched"] == 0
    assert len(body["mismatches"]) == 1
    assert body["mismatches"][0]["fb_location"] is None
    assert body["mismatches"][0]["spool_id"] == 99


def test_reconcile_scan_skips_zero_spool_entries(client):
    """A toolhead with spool_id=0 means 'empty'. Not a mismatch."""
    fb = _fb_status_with({"🦝 XL": {"0": {"spool_id": 0, "printer_name": "🦝 XL"}}})

    ctx = _patches(fb, lambda sid: None)
    for m in ctx: m.start()
    try:
        r = client.get("/api/filabridge/reconcile")
    finally:
        for m in reversed(ctx): m.stop()

    body = r.get_json()
    assert body["matched"] == 0
    assert body["mismatches"] == []


def test_reconcile_apply_trust_spoolman_calls_fb_unmap(client):
    """trust_spoolman → write spool_id=0 to that toolhead via _fb_write."""
    fb_writes = []

    def _fake_fb_write(printer, th, spool, fb_url=None):
        fb_writes.append((printer, th, spool))
        return (True, "ok")

    with patch.object(app_module.config_loader, "get_api_urls",
                      return_value=("http://spoolman", "http://filabridge")), \
         patch.object(app_module.logic, "_fb_write", side_effect=_fake_fb_write):
        r = client.post(
            "/api/filabridge/reconcile/apply",
            json={
                "spool_id": 42,
                "action": "trust_spoolman",
                "fb_printer": "🦝 XL",
                "fb_toolhead": 0,
                "fb_location": "XL-1",
                "sm_location": "CR-CT-1",
            },
        )
    assert r.get_json()["success"] is True
    assert fb_writes == [("🦝 XL", 0, 0)]


def test_reconcile_apply_trust_filabridge_updates_spoolman(client):
    """trust_filabridge → write Spoolman location to FilaBridge's value."""
    captured = []

    def _fake_update(sid, payload):
        captured.append((sid, payload))
        return {"id": sid, **payload}

    with patch.object(app_module.config_loader, "get_api_urls",
                      return_value=("http://spoolman", "http://filabridge")), \
         patch.object(app_module.spoolman_api, "get_spool",
                      return_value={"id": 42, "location": "CR-CT-1",
                                    "extra": {"container_slot": "1"}}), \
         patch.object(app_module.spoolman_api, "update_spool",
                      side_effect=_fake_update):
        r = client.post(
            "/api/filabridge/reconcile/apply",
            json={
                "spool_id": 42,
                "action": "trust_filabridge",
                "fb_printer": "🦝 XL",
                "fb_toolhead": 0,
                "fb_location": "XL-1",
                "sm_location": "CR-CT-1",
            },
        )
    assert r.get_json()["success"] is True
    assert len(captured) == 1
    sid, payload = captured[0]
    assert sid == 42
    assert payload["location"] == "XL-1"
    # Existing system-managed extras preserved — reconcile doesn't disturb them.
    assert payload["extra"].get("container_slot") == "1"


def test_reconcile_apply_rejects_unknown_action(client):
    r = client.post("/api/filabridge/reconcile/apply",
                    json={"spool_id": 42, "action": "delete_everything",
                          "fb_printer": "x", "fb_toolhead": 0})
    assert r.get_json()["success"] is False


def test_reconcile_apply_trust_filabridge_needs_fb_location(client):
    r = client.post("/api/filabridge/reconcile/apply",
                    json={"spool_id": 42, "action": "trust_filabridge",
                          "fb_printer": "x", "fb_toolhead": 0, "fb_location": ""})
    assert r.get_json()["success"] is False
