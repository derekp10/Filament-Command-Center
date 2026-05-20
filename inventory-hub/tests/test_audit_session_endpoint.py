"""18.2 Part B — /api/audit_session backend endpoint feeds the new
visual audit panel. Tests cover the active vs inactive payload shape
and the enrichment that turns bare spool IDs into renderable tiles.
"""
from __future__ import annotations

import os
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import app as app_module  # noqa: E402
import state  # noqa: E402


@pytest.fixture
def client():
    app_module.app.config["TESTING"] = True
    return app_module.app.test_client()


@pytest.fixture(autouse=True)
def _isolated_audit_session():
    state.reset_audit()
    yield
    state.reset_audit()


def test_audit_session_inactive_returns_active_false(client):
    r = client.get("/api/audit_session")
    assert r.get_json() == {"active": False}


def test_audit_session_active_returns_enriched_rows(client):
    state.AUDIT_SESSION.update({
        "active": True,
        "location_id": "LR-MDB-1",
        "expected_items": [101, 102, 103],
        "scanned_items": [101],
        "rogue_items": [999],
    })

    def _get(sid):
        return {
            "id": int(sid),
            "remaining_weight": 750.0 if int(sid) == 101 else 500.0,
            "filament": {"color_hex": "ff0000", "material": "PLA",
                          "name": f"Test #{sid}"},
            "extra": {"container_slot": str(int(sid) % 4)},
        }

    with patch.object(app_module.spoolman_api, "get_spool", side_effect=_get), \
         patch.object(app_module.spoolman_api, "format_spool_display",
                      side_effect=lambda sp: {"text": f"PLA Test #{sp['id']}", "color": "ff0000"}):
        r = client.get("/api/audit_session")

    body = r.get_json()
    assert body["active"] is True
    assert body["location_id"] == "LR-MDB-1"
    # Stats are derived from the lists.
    assert body["stats"] == {"total_expected": 3, "found": 1, "missing": 2, "rogue": 1}
    # Per-row enrichment: each expected entry carries display + found flag.
    expected_by_id = {row["id"]: row for row in body["expected"]}
    assert expected_by_id[101]["found"] is True
    assert expected_by_id[102]["found"] is False
    assert expected_by_id[103]["found"] is False
    assert "PLA Test #101" in expected_by_id[101]["display"]
    # Rogue row enrichment.
    assert len(body["rogue"]) == 1
    assert body["rogue"][0]["id"] == 999
    assert body["rogue"][0]["rogue"] is True


def test_audit_session_handles_missing_spool_gracefully(client):
    """If a spool record can't be fetched, the row still appears with
    a fallback display label so the panel doesn't break on bad data."""
    state.AUDIT_SESSION.update({
        "active": True,
        "location_id": "LR-MDB-1",
        "expected_items": [101],
        "scanned_items": [],
        "rogue_items": [],
    })
    with patch.object(app_module.spoolman_api, "get_spool", return_value=None), \
         patch.object(app_module.spoolman_api, "format_spool_display", return_value={}):
        r = client.get("/api/audit_session")
    body = r.get_json()
    assert body["active"] is True
    assert len(body["expected"]) == 1
    assert body["expected"][0]["id"] == 101
    # Display falls back to bare "#101" so the tile renders SOMETHING.
    assert body["expected"][0]["display"].startswith("#101")
