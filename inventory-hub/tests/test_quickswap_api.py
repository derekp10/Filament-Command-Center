"""
Unit tests for /api/quickswap + logic.find_spool_in_slot.

Mocks Spoolman + locations_db so we can drive every branch without a
live container.
"""
from __future__ import annotations

import os
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import app as app_module  # noqa: E402
import logic  # noqa: E402
import state  # noqa: E402


@pytest.fixture
def client():
    app_module.app.config["TESTING"] = True
    return app_module.app.test_client()


@pytest.fixture(autouse=True)
def isolate_logs():
    prior_logs = list(state.RECENT_LOGS)
    state.RECENT_LOGS = []
    try:
        yield
    finally:
        state.RECENT_LOGS = prior_logs


# ---------------------------------------------------------------------------
# find_spool_in_slot
# ---------------------------------------------------------------------------

def test_find_spool_in_slot_matches_loose_slot_string():
    items = [
        {"id": 11, "slot": "1"},
        {"id": 22, "slot": '"2"'},  # Spoolman sometimes quote-wraps
        {"id": 33, "slot": "3"},
    ]
    with patch.object(logic.spoolman_api, "get_spools_at_location_detailed", return_value=items):
        assert logic.find_spool_in_slot("PM-DB-1", "2") == 22
        assert logic.find_spool_in_slot("PM-DB-1", "3") == 33
        assert logic.find_spool_in_slot("PM-DB-1", "9") is None


def test_find_spool_in_slot_empty_inputs():
    assert logic.find_spool_in_slot("", "1") is None
    assert logic.find_spool_in_slot("PM-DB-1", "") is None


# ---------------------------------------------------------------------------
# /api/quickswap — happy path + guards
# ---------------------------------------------------------------------------

def _patch_bindings(return_value):
    return patch.object(app_module.locations_db, "get_dryer_box_bindings", return_value=return_value)


def test_quickswap_happy_path(client):
    with _patch_bindings({"1": "XL-1"}), \
         patch.object(app_module.logic, "find_spool_in_slot", return_value=42), \
         patch.object(app_module.logic, "perform_smart_move", return_value={"status": "success"}) as mv:
        r = client.post("/api/quickswap", json={"toolhead": "XL-1", "box": "PM-DB-1", "slot": "1"})
    assert r.status_code == 200
    body = r.get_json()
    assert body["action"] == "quickswap_done"
    assert body["moved"] == 42
    mv.assert_called_once_with("XL-1", [42], target_slot=None, origin="quickswap")
    # Success log entry fired.
    assert any(e["type"] == "SUCCESS" for e in state.RECENT_LOGS)


def test_quickswap_missing_body_fields(client):
    r = client.post("/api/quickswap", json={"box": "PM-DB-1"})
    assert r.status_code == 400
    assert r.get_json()["action"] == "quickswap_bad_request"


def test_quickswap_rejects_non_dryer_box(client):
    # get_dryer_box_bindings returns None when location isn't a Dryer Box.
    with _patch_bindings(None), \
         patch.object(app_module.logic, "perform_smart_move") as mv:
        r = client.post("/api/quickswap", json={"toolhead": "XL-1", "box": "XL-2", "slot": "1"})
    assert r.status_code == 404
    assert r.get_json()["action"] == "quickswap_bad_box"
    mv.assert_not_called()


def test_quickswap_rejects_stale_binding(client):
    """Frontend had a cached binding showing PM-DB-1 slot 1 → XL-1, but the
    server state has since changed. We reject rather than move to the
    wrong toolhead."""
    with _patch_bindings({"1": "XL-3"}), \
         patch.object(app_module.logic, "perform_smart_move") as mv:
        r = client.post("/api/quickswap", json={"toolhead": "XL-1", "box": "PM-DB-1", "slot": "1"})
    assert r.status_code == 400
    body = r.get_json()
    assert body["action"] == "quickswap_not_bound"
    assert body["bound_to"] == "XL-3"
    mv.assert_not_called()


def test_quickswap_rejects_unbound_slot(client):
    with _patch_bindings({"2": "XL-2"}), \
         patch.object(app_module.logic, "perform_smart_move") as mv:
        # Slot 1 is missing from bindings (== unassigned).
        r = client.post("/api/quickswap", json={"toolhead": "XL-1", "box": "PM-DB-1", "slot": "1"})
    assert r.status_code == 400
    assert r.get_json()["action"] == "quickswap_not_bound"
    mv.assert_not_called()


def test_quickswap_empty_slot_yields_404(client):
    with _patch_bindings({"1": "XL-1"}), \
         patch.object(app_module.logic, "find_spool_in_slot", return_value=None), \
         patch.object(app_module.logic, "perform_smart_move") as mv:
        r = client.post("/api/quickswap", json={"toolhead": "XL-1", "box": "PM-DB-1", "slot": "1"})
    assert r.status_code == 404
    body = r.get_json()
    assert body["action"] == "quickswap_empty_slot"
    mv.assert_not_called()
    # Warning log fired.
    assert any(e["type"] == "WARNING" for e in state.RECENT_LOGS)


def test_quickswap_normalizes_case(client):
    """Accept lowercase box/toolhead inputs; store/compare in upper case."""
    with _patch_bindings({"1": "XL-1"}), \
         patch.object(app_module.logic, "find_spool_in_slot", return_value=7), \
         patch.object(app_module.logic, "perform_smart_move", return_value={"status": "success"}) as mv:
        r = client.post("/api/quickswap", json={"toolhead": "xl-1", "box": "pm-db-1", "slot": "1"})
    assert r.status_code == 200
    args, kwargs = mv.call_args
    assert args[0] == "XL-1"
    assert args[1] == [7]


def test_quickswap_core_one_shared_position(client):
    """CORE1-M0 and CORE1-M1 both map to printer position 0. Quick-swap to
    either should work independently — the backend doesn't dedup physical
    positions, and neither should quickswap."""
    # M1 is bound, we target M1 → succeeds.
    with _patch_bindings({"1": "CORE1-M1"}), \
         patch.object(app_module.logic, "find_spool_in_slot", return_value=99), \
         patch.object(app_module.logic, "perform_smart_move", return_value={"status": "success"}) as mv:
        r = client.post("/api/quickswap", json={"toolhead": "CORE1-M1", "box": "PM-DB-CORE1", "slot": "1"})
    assert r.status_code == 200
    mv.assert_called_once()
    # Now M0 scenario — bindings point at M0, we target M0.
    with _patch_bindings({"1": "CORE1-M0"}), \
         patch.object(app_module.logic, "find_spool_in_slot", return_value=100), \
         patch.object(app_module.logic, "perform_smart_move", return_value={"status": "success"}) as mv2:
        r2 = client.post("/api/quickswap", json={"toolhead": "CORE1-M0", "box": "PM-DB-CORE1", "slot": "1"})
    assert r2.status_code == 200
    mv2.assert_called_once()


def test_quickswap_scales_to_many_toolheads(client):
    """indxx forward-compat: a 10-toolhead printer uses exactly the same
    code path. This is just a shape check — if perform_smart_move and
    bindings both accept the new IDs, quickswap works."""
    for i in range(1, 11):
        th = f"INDXX-{i}"
        with _patch_bindings({str(i): th}), \
             patch.object(app_module.logic, "find_spool_in_slot", return_value=200 + i), \
             patch.object(app_module.logic, "perform_smart_move", return_value={"status": "success"}):
            r = client.post("/api/quickswap", json={"toolhead": th, "box": "PM-INDXX", "slot": str(i)})
        assert r.status_code == 200, f"quickswap failed for toolhead {th}"
