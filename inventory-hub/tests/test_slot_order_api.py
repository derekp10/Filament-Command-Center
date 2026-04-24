"""
Tests for the per-dryer-box slot render-order API:

  GET  /api/dryer_box/<id>/slot_order
  PUT  /api/dryer_box/<id>/slot_order   body: {"order": "ltr" | "rtl"}
  GET  /api/dryer_box/<id>/bindings      (now also returns slot_order)

slot_order is persisted under extra.slot_order on the dryer box record.
Defaults to 'ltr' when unset. Values outside {ltr, rtl} are rejected.

The underlying locations_db writes to locations.json, so we patch those
IO helpers where needed to avoid mutating the test environment.
"""
from __future__ import annotations

import os
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import app as app_module  # noqa: E402
import locations_db  # noqa: E402


FAKE_DB_ROWS = [
    {
        "LocationID": "LR-MDB-1",
        "Type": "Dryer Box",
        "Max Spools": "4",
        "Name": "LR MDB",
        "extra": {},
    },
    {
        "LocationID": "CORE1-M0",
        "Type": "Tool Head",
        "Max Spools": "1",
        "Name": "M0",
        "extra": {},
    },
]


@pytest.fixture
def client():
    app_module.app.config["TESTING"] = True
    return app_module.app.test_client()


@pytest.fixture
def isolated_locations():
    """Patch locations_db's IO so tests mutate an in-memory copy instead of disk."""
    import copy
    store = {"rows": copy.deepcopy(FAKE_DB_ROWS)}

    def _load():
        return copy.deepcopy(store["rows"])

    def _save(rows):
        store["rows"] = copy.deepcopy(rows)

    with patch.object(locations_db, "load_locations_list", side_effect=_load), \
         patch.object(locations_db, "save_locations_list", side_effect=_save):
        yield store


# ---------------------------------------------------------------------------
# GET /slot_order
# ---------------------------------------------------------------------------

def test_slot_order_get_defaults_to_ltr_when_unset(client, isolated_locations):
    resp = client.get("/api/dryer_box/LR-MDB-1/slot_order")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["location"] == "LR-MDB-1"
    assert body["order"] == "ltr"


def test_slot_order_get_returns_404_for_non_dryer_box(client, isolated_locations):
    resp = client.get("/api/dryer_box/CORE1-M0/slot_order")
    assert resp.status_code == 404
    body = resp.get_json()
    assert body["error"] == "not_a_dryer_box"


def test_slot_order_get_returns_404_for_missing_location(client, isolated_locations):
    resp = client.get("/api/dryer_box/NOT-REAL/slot_order")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# PUT /slot_order
# ---------------------------------------------------------------------------

def test_slot_order_put_persists_rtl(client, isolated_locations):
    resp = client.put(
        "/api/dryer_box/LR-MDB-1/slot_order",
        json={"order": "rtl"},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["order"] == "rtl"

    # Round-trip: GET should now return rtl.
    resp2 = client.get("/api/dryer_box/LR-MDB-1/slot_order")
    assert resp2.get_json()["order"] == "rtl"


def test_slot_order_put_rejects_invalid_order(client, isolated_locations):
    resp = client.put(
        "/api/dryer_box/LR-MDB-1/slot_order",
        json={"order": "upside-down"},
    )
    assert resp.status_code == 400
    body = resp.get_json()
    assert body["error"] == "invalid_request"
    assert "upside-down" in body["msg"]


def test_slot_order_put_rejects_missing_body(client, isolated_locations):
    resp = client.put("/api/dryer_box/LR-MDB-1/slot_order", json={})
    assert resp.status_code == 400


def test_slot_order_put_normalizes_case(client, isolated_locations):
    resp = client.put(
        "/api/dryer_box/LR-MDB-1/slot_order",
        json={"order": "RTL"},
    )
    assert resp.status_code == 200
    assert resp.get_json()["order"] == "rtl"


# ---------------------------------------------------------------------------
# Bindings GET now includes slot_order
# ---------------------------------------------------------------------------

def test_bindings_get_includes_slot_order(client, isolated_locations):
    # Set rtl first.
    client.put("/api/dryer_box/LR-MDB-1/slot_order", json={"order": "rtl"})

    resp = client.get("/api/dryer_box/LR-MDB-1/bindings")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["slot_order"] == "rtl"
    # slot_targets is still present and untouched.
    assert "slot_targets" in body


def test_bindings_get_default_slot_order_is_ltr(client, isolated_locations):
    resp = client.get("/api/dryer_box/LR-MDB-1/bindings")
    body = resp.get_json()
    assert body["slot_order"] == "ltr"
