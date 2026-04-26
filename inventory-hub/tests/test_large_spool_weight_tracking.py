"""
Regression coverage for >1kg spool weight tracking.

Backlog item: "Possible issues with >1kg spools and tracking weights?"
— decision was test-coverage-only: confirm the existing deduction path
treats large starting weights correctly and stores them without silent
truncation, caps at initial_weight on over-deduction, and carries the
full value round-trip through update_spool.

Tests drive Spoolman directly to create a 3000g spool, then exercise
`spoolman_api.update_spool` (the single helper every deduction call site
funnels through) with both normal and over-deduction scenarios.
"""
from __future__ import annotations

import os
import sys

import pytest
import requests

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import spoolman_api  # noqa: E402

SPOOLMAN = "http://192.168.1.29:7913"


def _sm_ok() -> bool:
    try:
        return requests.get(f"{SPOOLMAN}/api/v1/health", timeout=3).ok
    except requests.RequestException:
        return False


@pytest.fixture
def large_throwaway_spool():
    if not _sm_ok():
        pytest.skip("Spoolman dev instance unreachable")
    v_resp = requests.get(f"{SPOOLMAN}/api/v1/vendor", timeout=5)
    if not v_resp.ok or not v_resp.json():
        pytest.skip("no vendor in Spoolman")
    vendor_id = v_resp.json()[0]["id"]

    fil = requests.post(
        f"{SPOOLMAN}/api/v1/filament",
        json={
            "name": "LARGE-SPOOL-TEST",
            "material": "PETG",
            "vendor_id": vendor_id,
            "weight": 3000,         # 3kg net filament weight
            "spool_weight": 350,
            "density": 1.27,
            "diameter": 1.75,
            "color_hex": "FFFFFF",
        },
        timeout=5,
    )
    assert fil.ok, fil.text
    fid = fil.json()["id"]

    sp = requests.post(
        f"{SPOOLMAN}/api/v1/spool",
        json={"filament_id": fid, "initial_weight": 3000, "used_weight": 0},
        timeout=5,
    )
    assert sp.ok, sp.text
    sid = sp.json()["id"]

    try:
        yield sid
    finally:
        requests.delete(f"{SPOOLMAN}/api/v1/spool/{sid}", timeout=5)
        requests.delete(f"{SPOOLMAN}/api/v1/filament/{fid}", timeout=5)


def test_initial_weight_above_1kg_stored_intact(large_throwaway_spool):
    """Round-trip check — a 3000g initial_weight survives create/read."""
    sp = spoolman_api.get_spool(large_throwaway_spool)
    assert sp is not None
    assert float(sp.get("initial_weight") or 0) == 3000.0
    assert float(sp.get("used_weight") or 0) == 0.0


def test_partial_deduction_above_1kg_persists(large_throwaway_spool):
    """Deducting 1500g from a 3kg spool must store 1500g, not clip to 1000."""
    res = spoolman_api.update_spool(large_throwaway_spool, {"used_weight": 1500})
    assert res is not None
    sp = spoolman_api.get_spool(large_throwaway_spool)
    assert float(sp.get("used_weight") or 0) == pytest.approx(1500.0)


def test_deduction_near_initial_weight_persists(large_throwaway_spool):
    """Used weight just shy of initial must store verbatim."""
    res = spoolman_api.update_spool(large_throwaway_spool, {"used_weight": 2999})
    assert res is not None
    sp = spoolman_api.get_spool(large_throwaway_spool)
    assert float(sp.get("used_weight") or 0) == pytest.approx(2999.0)


def test_over_deduction_caps_at_initial_weight(large_throwaway_spool):
    """Asking to set used_weight above initial must clamp, not overflow."""
    res = spoolman_api.update_spool(large_throwaway_spool, {"used_weight": 3500})
    assert res is not None
    sp = spoolman_api.get_spool(large_throwaway_spool)
    # spoolman_api.update_spool caps via "[ALEX FIX] Ensure used_weight
    # never crashes SQLAlchemy due to constraint by artificially capping
    # to initial_weight" — verify the cap holds for >1kg spools too.
    assert float(sp.get("used_weight") or 0) == pytest.approx(3000.0)


def test_successive_deductions_accumulate_correctly(large_throwaway_spool):
    """Two sequential deductions on a >1kg spool must sum, not overwrite."""
    sid = large_throwaway_spool
    spoolman_api.update_spool(sid, {"used_weight": 800})
    current = float(spoolman_api.get_spool(sid).get("used_weight") or 0)
    # Second deduction: compute new_used the same way the usage pipeline does
    # (see app.py: new_used = used + weight_used).
    spoolman_api.update_spool(sid, {"used_weight": current + 950})
    final = float(spoolman_api.get_spool(sid).get("used_weight") or 0)
    assert final == pytest.approx(1750.0)
