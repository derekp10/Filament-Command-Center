"""Group 66.9 on dev's real Spoolman (integration: RUN_INTEGRATION=1 or --run-integration).

1. The Spoolman rule the merge is built around, which the offline fake in
   tests/test_vendor_merge_66_9.py models: DELETE /api/v1/vendor/<id> succeeds while
   filaments still name the vendor, and clears their vendor (0.27.1's API text; a dev
   probe on 2026-11-26). Merge Filament can lean on Spoolman refusing to delete a
   filament that still has spools; the manufacturer merge can't, and deletes only
   after its own strict re-list shows none left. If a Spoolman release starts
   refusing such a delete, this test goes red, and the fake should follow it.
2. The real merge route, through the real spoolman_api helpers, on throwaway records
   whose names start "__fcc_test_g66_9" (Spoolman takes a second vendor of a name in
   use: FCC's own create refuses it since Group 66.1), cleaned up whatever happens.

Never prod: conftest refuses a DEV_SPOOLMAN_URL on prod's port.
"""
from __future__ import annotations

import os
import sys
import uuid

import pytest
import requests
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

pytestmark = pytest.mark.integration

PREFIX = "__fcc_test_g66_9"


def _create(url, entity, body):
    r = requests.post(f"{url}/api/v1/{entity}", json=body, timeout=10)
    assert r.ok, f"couldn't create a throwaway {entity}: {r.status_code} {r.text}"
    return r.json()["id"]


def _delete(url, entity, eid):
    try:
        requests.delete(f"{url}/api/v1/{entity}/{eid}", timeout=10)
    except requests.RequestException:
        pass


def _gone(url, entity, eid):
    return requests.get(f"{url}/api/v1/{entity}/{eid}", timeout=10).status_code == 404


def test_spoolman_deletes_a_vendor_that_still_has_filaments_and_clears_their_vendor(require_spoolman):
    url = require_spoolman
    tag = uuid.uuid4().hex[:8]
    vid = fid = None
    try:
        vid = _create(url, "vendor", {"name": f"{PREFIX}_probe_{tag}"})
        fid = _create(url, "filament", {"name": f"{PREFIX}_probe_fil_{tag}", "vendor_id": vid,
                                        "density": 1.24, "diameter": 1.75})
        r = requests.delete(f"{url}/api/v1/vendor/{vid}", timeout=10)
        assert r.status_code == 200, (
            f"Spoolman now answers {r.status_code} to deleting a vendor that still has filaments: "
            f"{r.text}. The merge's fake (test_vendor_merge_66_9._VendorSpoolman.delete) models a 200 "
            f"that clears their vendor; make it follow.")
        fil = requests.get(f"{url}/api/v1/filament/{fid}", timeout=10).json()
        assert not fil.get("vendor"), f"the filament kept its vendor: {fil.get('vendor')}"
        assert _gone(url, "vendor", vid)
    finally:
        if fid is not None:
            _delete(url, "filament", fid)
        if vid is not None:
            _delete(url, "vendor", vid)
    assert _gone(url, "filament", fid) and _gone(url, "vendor", vid)


def test_the_merge_on_real_spoolman_carries_moves_and_deletes(require_spoolman):
    from app import app as flask_app
    import spoolman_api

    url = require_spoolman
    tag = uuid.uuid4().hex[:8]
    name = f"{PREFIX} Acme {tag}"
    src = dst = None
    fils = []
    try:
        src = _create(url, "vendor", {"name": name, "external_id": f"acme-{tag}"})
        dst = _create(url, "vendor", {"name": name, "empty_spool_weight": 150})
        for colour in ("Red", "Blue"):
            fils.append(_create(url, "filament", {"name": f"{PREFIX}_fil_{colour}_{tag}", "vendor_id": src,
                                                  "material": "PLA", "density": 1.24, "diameter": 1.75}))
        flask_app.config["TESTING"] = True
        with patch.object(spoolman_api.config_loader, "get_api_urls", return_value=(url, None)), \
             flask_app.test_client() as client:
            plan = client.post(f"/api/vendors/{src}/merge_into/{dst}", json={"dry_run": True}).get_json()
            assert plan["success"] is True, plan
            assert plan["default_keep"] == src            # it holds the filaments
            assert plan["plan"]["carry"] == {"external_id": f"acme-{tag}"}
            assert sorted(f["id"] for f in plan["plan"]["filaments"]) == sorted(fils)
            assert _gone(url, "vendor", src) is False     # the plan wrote nothing
            # The merge asks for itself (review round 1, S5; round 2, S1: `{}` here was
            # answered 400 once round 1 landed).
            r = client.post(f"/api/vendors/{src}/merge_into/{dst}", json={"merge": True})
            body = r.get_json()
        assert r.status_code == 200, body
        assert body["success"] is True, body
        assert sorted(body["moved_filament_ids"]) == sorted(fils)
        for fid in fils:
            fil = requests.get(f"{url}/api/v1/filament/{fid}", timeout=10).json()
            assert (fil.get("vendor") or {}).get("id") == dst, fil.get("vendor")
        assert _gone(url, "vendor", src)
        kept = requests.get(f"{url}/api/v1/vendor/{dst}", timeout=10).json()
        assert kept.get("external_id") == f"acme-{tag}"
        assert kept.get("empty_spool_weight") == 150
        assert kept.get("name") == name
    finally:
        for fid in fils:
            _delete(url, "filament", fid)
        for vid in (src, dst):
            if vid is not None:
                _delete(url, "vendor", vid)
    assert all(_gone(url, "filament", fid) for fid in fils)
    assert all(_gone(url, "vendor", vid) for vid in (src, dst) if vid is not None)
