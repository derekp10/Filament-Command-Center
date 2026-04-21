"""
API-path E2E tests for Phase 1 slot-QR assignment.

These run against the live inventory_hub container at base_url. The guard
paths don't move any real spools, so this suite is safe to run repeatedly.
The happy path runs only when EXPLICIT_SPOOL_FOR_ASSIGNMENT_TEST is set
(requires a throwaway spool the user approves for real movement).
"""
from __future__ import annotations

import os
import pytest


@pytest.mark.usefixtures("require_server", "clean_buffer")
def test_slot_scan_no_buffer_returns_warning(scan):
    result = scan("LOC:LR-MDB-1:SLOT:2", source="test")
    assert result["type"] == "assignment"
    assert result["action"] == "assignment_no_buffer"
    assert result["location"] == "LR-MDB-1"
    assert result["slot"] == "2"


@pytest.mark.usefixtures("require_server", "clean_buffer")
def test_slot_scan_bad_target_is_rejected(api_base_url):
    import requests
    r = requests.post(
        f"{api_base_url}/api/identify_scan",
        json={"text": "LOC:NOT-A-REAL-LOCATION:SLOT:1", "source": "test"},
        timeout=5,
    )
    assert r.status_code == 400
    body = r.json()
    assert body["action"] == "assignment_bad_target"
    assert body["found_type"] == "missing"


@pytest.mark.usefixtures("require_server", "clean_buffer")
def test_slot_scan_bad_slot_is_rejected(api_base_url):
    """LR-MDB-1 has Max Spools 4; slot 99 is out of range."""
    import requests
    r = requests.post(
        f"{api_base_url}/api/identify_scan",
        json={"text": "LOC:LR-MDB-1:SLOT:99", "source": "test"},
        timeout=5,
    )
    assert r.status_code == 400
    body = r.json()
    assert body["action"] == "assignment_bad_slot"
    assert body["max_slots"] == 4


@pytest.mark.usefixtures("require_server")
def test_buffer_clear_endpoint_exists(api_base_url):
    import requests
    r = requests.post(f"{api_base_url}/api/buffer/clear", timeout=5)
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert body["buffer"] == []


@pytest.mark.skipif(
    not os.environ.get("EXPLICIT_SPOOL_FOR_ASSIGNMENT_TEST"),
    reason="Happy-path test moves a real spool; set EXPLICIT_SPOOL_FOR_ASSIGNMENT_TEST=<spool_id> to enable.",
)
@pytest.mark.usefixtures("require_server", "clean_buffer")
def test_slot_scan_happy_path_moves_real_spool(api_base_url, scan):
    """Opt-in test that actually moves a real spool. User must set the env var."""
    import requests
    spool_id = int(os.environ["EXPLICIT_SPOOL_FOR_ASSIGNMENT_TEST"])
    target = os.environ.get("EXPLICIT_TARGET_FOR_ASSIGNMENT_TEST", "LR-MDB-1")
    target_slot = os.environ.get("EXPLICIT_SLOT_FOR_ASSIGNMENT_TEST", "1")

    # Seed buffer with the spool.
    r = requests.post(
        f"{api_base_url}/api/state/buffer",
        json={"buffer": [{"id": spool_id, "display": "test", "color": "ffffff"}]},
        timeout=5,
    )
    assert r.ok

    result = scan(f"LOC:{target}:SLOT:{target_slot}", source="test")
    assert result["action"] in ("assignment_done", "assignment_partial")
    assert result["moved"] == spool_id
