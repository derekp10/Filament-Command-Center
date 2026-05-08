"""
Backend API test for /api/backfill_spool_weights/<fid>.

Creates a throwaway filament with spool_weight=250 and two spools under it
(one with spool_weight=0, one with spool_weight=200), hits the backfill
endpoint, and asserts that only the zero-weight spool is rewritten.
"""
from __future__ import annotations

import pytest
import requests


@pytest.fixture
def backfill_test_filament(require_spoolman: str):
    """Create a filament with `spool_weight=250` plus two spools (one zero,
    one preset to 200g) so the backfill endpoint has both update + skip cases
    in scope. Local override of the conftest `throwaway_filament` fixture
    because the backfill endpoint needs two controlled-weight spools, not
    just a bare filament.
    """
    spoolman_url = require_spoolman
    # Need *some* vendor. Reuse the first one Spoolman reports, else skip.
    v_resp = requests.get(f"{spoolman_url}/api/v1/vendor", timeout=5)
    if not v_resp.ok or not v_resp.json():
        pytest.skip("no vendor in Spoolman to attach throwaway filament to")
    vendor_id = v_resp.json()[0]["id"]

    fil = requests.post(
        f"{spoolman_url}/api/v1/filament",
        json={
            "name": "BACKFILL-TEST",
            "material": "PLA",
            "vendor_id": vendor_id,
            "spool_weight": 250,  # The inheritable value the endpoint should propagate.
            "density": 1.24,
            "diameter": 1.75,
            "color_hex": "FFFFFF",
        },
        timeout=5,
    )
    assert fil.ok, fil.text
    fid = fil.json()["id"]

    created_spools = []
    try:
        s_zero = requests.post(
            f"{spoolman_url}/api/v1/spool",
            json={"filament_id": fid, "spool_weight": 0, "used_weight": 0},
            timeout=5,
        )
        assert s_zero.ok, s_zero.text
        created_spools.append(s_zero.json()["id"])

        s_set = requests.post(
            f"{spoolman_url}/api/v1/spool",
            json={"filament_id": fid, "spool_weight": 200, "used_weight": 0},
            timeout=5,
        )
        assert s_set.ok, s_set.text
        created_spools.append(s_set.json()["id"])

        yield {
            "fid": fid,
            "zero_sid": created_spools[0],
            "set_sid": created_spools[1],
        }
    finally:
        for sid in created_spools:
            requests.delete(f"{spoolman_url}/api/v1/spool/{sid}", timeout=5)
        requests.delete(f"{spoolman_url}/api/v1/filament/{fid}", timeout=5)


def test_backfill_updates_only_zero_weight_spools(
    require_server: str, dev_spoolman_url: str, backfill_test_filament
):
    api_base_url = require_server
    fid = backfill_test_filament["fid"]
    zero_sid = backfill_test_filament["zero_sid"]
    set_sid = backfill_test_filament["set_sid"]

    resp = requests.post(f"{api_base_url}/api/backfill_spool_weights/{fid}", timeout=10)
    assert resp.ok, resp.text
    body = resp.json()
    assert body.get("success") is True, body
    assert body["target_weight"] == 250
    assert body["source"] == "filament"
    assert body["updated"] == 1, body
    assert body["skipped"] == 1, body
    assert zero_sid in body["updated_ids"]
    assert set_sid not in body["updated_ids"]

    # Verify Spoolman now reports the backfilled weight on the zero spool and
    # leaves the preset one alone.
    after_zero = requests.get(f"{dev_spoolman_url}/api/v1/spool/{zero_sid}", timeout=5).json()
    after_set = requests.get(f"{dev_spoolman_url}/api/v1/spool/{set_sid}", timeout=5).json()
    assert float(after_zero.get("spool_weight") or 0) == 250.0
    assert float(after_set.get("spool_weight") or 0) == 200.0


def test_backfill_rejects_filament_without_inheritable_weight(
    require_server: str, require_spoolman: str
):
    api_base_url = require_server
    spoolman_url = require_spoolman
    v_resp = requests.get(f"{spoolman_url}/api/v1/vendor", timeout=5)
    if not v_resp.ok or not v_resp.json():
        pytest.skip("no vendor in Spoolman")
    vendor_id = v_resp.json()[0]["id"]
    # Clear vendor empty_spool_weight so neither filament nor vendor has one.
    saved_vendor_wt = v_resp.json()[0].get("empty_spool_weight")
    requests.patch(
        f"{spoolman_url}/api/v1/vendor/{vendor_id}", json={"empty_spool_weight": 0}, timeout=5
    )

    fil = requests.post(
        f"{spoolman_url}/api/v1/filament",
        json={
            "name": "BACKFILL-TEST-NO-INHERIT",
            "material": "PLA",
            "vendor_id": vendor_id,
            "spool_weight": 0,
            "density": 1.24,
            "diameter": 1.75,
            "color_hex": "FFFFFF",
        },
        timeout=5,
    )
    assert fil.ok, fil.text
    fid = fil.json()["id"]
    try:
        resp = requests.post(f"{api_base_url}/api/backfill_spool_weights/{fid}", timeout=10)
        assert resp.status_code == 400
        body = resp.json()
        assert body.get("success") is False
        assert "inheritable" in (body.get("msg") or "").lower()
    finally:
        requests.delete(f"{spoolman_url}/api/v1/filament/{fid}", timeout=5)
        if saved_vendor_wt is not None:
            requests.patch(
                f"{spoolman_url}/api/v1/vendor/{vendor_id}",
                json={"empty_spool_weight": saved_vendor_wt},
                timeout=5,
            )
