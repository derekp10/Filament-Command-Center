"""
API-path E2E tests for Phase 2 bindings against the live container.

Exercises the actual /api/dryer_box/.../bindings + /api/machine/.../toolhead_slots
endpoints to catch wiring regressions unit tests can't. Uses a real Dryer
Box from the running locations.json. After each test, restores original
bindings so test runs don't contaminate each other.
"""
from __future__ import annotations

import pytest
import requests

TEST_BOX = "PM-DB-1"  # Dryer Box that exists in the fixture locations.json
TEST_PRINTER = "🦝 XL"


@pytest.fixture
def saved_bindings(api_base_url):
    """Snapshot + restore the bindings for TEST_BOX around a test."""
    snap = requests.get(f"{api_base_url}/api/dryer_box/{TEST_BOX}/bindings", timeout=5).json()
    original = snap.get("slot_targets", {})
    try:
        yield original
    finally:
        requests.put(
            f"{api_base_url}/api/dryer_box/{TEST_BOX}/bindings",
            json={"slot_targets": original},
            timeout=5,
        )


@pytest.mark.usefixtures("require_server")
def test_printer_map_endpoint_returns_grouped_toolheads(api_base_url):
    r = requests.get(f"{api_base_url}/api/printer_map", timeout=5)
    assert r.status_code == 200
    body = r.json()
    assert "printers" in body
    # The running config has both 🦝 XL and 🦝 Core One Upgraded printers.
    assert any("XL" in name for name in body["printers"].keys())


@pytest.mark.usefixtures("require_server")
def test_bindings_put_then_get_round_trip(api_base_url, saved_bindings):
    r = requests.put(
        f"{api_base_url}/api/dryer_box/{TEST_BOX}/bindings",
        json={"slot_targets": {"1": "XL-1"}},
        timeout=5,
    )
    assert r.status_code == 200, r.text
    assert r.json()["slot_targets"] == {"1": "XL-1"}

    r2 = requests.get(f"{api_base_url}/api/dryer_box/{TEST_BOX}/bindings", timeout=5)
    assert r2.status_code == 200
    assert r2.json()["slot_targets"] == {"1": "XL-1"}


@pytest.mark.usefixtures("require_server")
def test_bindings_put_rejects_bad_target(api_base_url, saved_bindings):
    r = requests.put(
        f"{api_base_url}/api/dryer_box/{TEST_BOX}/bindings",
        json={"slot_targets": {"1": "XL-999"}},
        timeout=5,
    )
    assert r.status_code == 400
    body = r.json()
    assert body["error"] == "validation_failed"
    assert len(body["errors"]) == 1
    assert body["errors"][0]["slot"] == "1"


@pytest.mark.usefixtures("require_server")
def test_bindings_null_target_drops_from_storage(api_base_url, saved_bindings):
    r = requests.put(
        f"{api_base_url}/api/dryer_box/{TEST_BOX}/bindings",
        json={"slot_targets": {"1": "XL-1", "2": None}},
        timeout=5,
    )
    assert r.status_code == 200
    body = r.json()
    # Null slot is dropped from storage — absence == unassigned.
    assert body["slot_targets"] == {"1": "XL-1"}
    assert "2" not in body["slot_targets"]


@pytest.mark.usefixtures("require_server")
def test_machine_toolhead_slots_returns_aggregation(api_base_url, saved_bindings):
    # Set up: PM-DB-1 slot 1 → XL-1.
    requests.put(
        f"{api_base_url}/api/dryer_box/{TEST_BOX}/bindings",
        json={"slot_targets": {"1": "XL-1"}},
        timeout=5,
    )
    r = requests.get(f"{api_base_url}/api/machine/{TEST_PRINTER}/toolhead_slots", timeout=5)
    assert r.status_code == 200
    body = r.json()
    # XL-1 must now include PM-DB-1 slot 1 as a source.
    assert any(
        e.get("box") == TEST_BOX and e.get("slot") == "1"
        for e in body["toolheads"].get("XL-1", [])
    )


@pytest.mark.usefixtures("require_server")
def test_machine_toolhead_slots_unknown_printer_404(api_base_url):
    r = requests.get(f"{api_base_url}/api/machine/no-such-printer-xyz/toolhead_slots", timeout=5)
    assert r.status_code == 404
    assert r.json()["error"] == "printer_not_found"
