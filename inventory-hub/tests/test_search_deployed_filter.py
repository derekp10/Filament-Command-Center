"""
Tests for the `deployed` query-string filter on /api/search.

Contract:
  - Accepts 'deployed', 'undeployed', or empty/'any'.
  - A spool is "deployed" if its Spoolman location is in printer_map OR its
    extra.physical_source points at a printer_map entry (ghost deploy).
  - Filter is silently ignored for target_type=filament.

Uses a live container for the E2E round-trip and patched helpers for the
unit-level behavior (avoids mutating Spoolman state).
"""
from __future__ import annotations

import os
import sys
from unittest.mock import patch

import pytest
import requests

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import spoolman_api  # noqa: E402


FAKE_SPOOLS = [
    # Deployed: location is a toolhead in the fake printer_map.
    {"id": 1, "archived": False, "remaining_weight": 500, "location": "CORE1-M0",
     "extra": {}, "filament": {"id": 10, "material": "PLA", "name": "Red",
                                "vendor": {"name": "V"}, "extra": {}}},
    # Undeployed: location is a dryer box.
    {"id": 2, "archived": False, "remaining_weight": 500, "location": "LR-MDB-1",
     "extra": {}, "filament": {"id": 11, "material": "PLA", "name": "Blue",
                                "vendor": {"name": "V"}, "extra": {}}},
    # Ghost-deployed: physical_source points at a toolhead.
    {"id": 3, "archived": False, "remaining_weight": 500, "location": "LR-MDB-1",
     "extra": {"physical_source": "XL-3"},
     "filament": {"id": 12, "material": "PLA", "name": "Green",
                   "vendor": {"name": "V"}, "extra": {}}},
    # Unassigned (no location).
    {"id": 4, "archived": False, "remaining_weight": 500, "location": "",
     "extra": {}, "filament": {"id": 13, "material": "PLA", "name": "Yellow",
                                "vendor": {"name": "V"}, "extra": {}}},
]

FAKE_PRINTER_MAP = {
    "CORE1-M0": {"printer_name": "C1", "position": 0},
    "XL-3": {"printer_name": "XL", "position": 2},
}


@pytest.fixture
def patched_search():
    """Stub the Spoolman HTTP fetch + config_loader so search_inventory runs
    against our fake rows. Yields a callable that invokes search_inventory
    with the given kwargs."""

    class _FakeResp:
        ok = True
        def json(self):
            return FAKE_SPOOLS

    def _runner(**kwargs):
        with patch.object(spoolman_api, "requests") as mreq, \
             patch.object(spoolman_api.config_loader, "load_config",
                          return_value={"printer_map": FAKE_PRINTER_MAP}), \
             patch.object(spoolman_api.config_loader, "get_api_urls",
                          return_value=("http://sm", "http://fb")), \
             patch.object(spoolman_api, "parse_inbound_data", side_effect=lambda d: d):
            mreq.get.return_value = _FakeResp()
            return spoolman_api.search_inventory(**kwargs)

    return _runner


# ---------------------------------------------------------------------------
# Filter behavior
# ---------------------------------------------------------------------------

def test_deployed_filter_returns_only_toolhead_and_ghost(patched_search):
    results = patched_search(deployed_state="deployed", target_type="spool")
    ids = sorted(r["id"] for r in results)
    # Spool 1 (direct toolhead) and spool 3 (ghost) qualify.
    assert ids == [1, 3]


def test_undeployed_filter_returns_everything_else(patched_search):
    results = patched_search(deployed_state="undeployed", target_type="spool")
    ids = sorted(r["id"] for r in results)
    assert ids == [2, 4]


def test_any_deployment_returns_all_spools(patched_search):
    results_any = patched_search(deployed_state="any", target_type="spool")
    results_empty = patched_search(deployed_state="", target_type="spool")
    assert len(results_any) == 4
    assert len(results_empty) == 4


def test_deployed_filter_ignored_for_filament_target(patched_search):
    """Filaments don't have a deployment state — filter must be a no-op."""
    # Swap the fake data to filaments (each item is itself the filament row).
    with patch.object(spoolman_api, "requests") as mreq, \
         patch.object(spoolman_api.config_loader, "load_config",
                      return_value={"printer_map": FAKE_PRINTER_MAP}), \
         patch.object(spoolman_api.config_loader, "get_api_urls",
                      return_value=("http://sm", "http://fb")), \
         patch.object(spoolman_api, "parse_inbound_data", side_effect=lambda d: d):
        class _R:
            ok = True
            def json(self):
                return [{"id": fil_id, "material": "PLA", "name": f"F{fil_id}",
                         "vendor": {"name": "V"}, "extra": {}}
                        for fil_id in range(1, 5)]
        mreq.get.return_value = _R()
        results = spoolman_api.search_inventory(
            target_type="filament", deployed_state="deployed"
        )
    # No filaments are filtered out.
    assert len(results) == 4


# ---------------------------------------------------------------------------
# Live integration against the running container (shape only).
# ---------------------------------------------------------------------------

def test_live_search_endpoint_accepts_deployed_param():
    base_url = os.environ.get("INVENTORY_HUB_URL", "http://localhost:8000")
    try:
        r = requests.get(
            f"{base_url}/api/search",
            params={"q": "", "type": "spool", "deployed": "deployed"},
            timeout=10,
        )
    except requests.RequestException:
        pytest.skip("Container not responding")
    assert r.status_code == 200
    body = r.json()
    assert body.get("success") is True
    # Shape: results is a list (possibly empty — we don't depend on live data).
    assert isinstance(body.get("results"), list)
