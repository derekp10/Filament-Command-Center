"""feature/scan-match-pipeline — Prusament-QR scan pipeline.

A physical Prusament spool label encodes a https://prusament.com/spool/<id>/<hash>/
URL. resolve_scan must recognize it as a dedicated `prusament_url` type (matched by
the numeric spool <id>) so /api/identify_scan can either backfill nozzle/bed temps
onto the matching existing filament or onboard a brand-new spool.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from unittest.mock import patch  # noqa: E402

import pytest  # noqa: E402

from logic import resolve_scan  # noqa: E402
import app as app_module  # noqa: E402


def test_resolve_scan_recognizes_prusament_url():
    res = resolve_scan("https://prusament.com/spool/17705/5b1a183b26/")
    assert res == {
        "type": "prusament_url",
        "url": "https://prusament.com/spool/17705/5b1a183b26/",
        "spool_id": "17705",
    }


def test_resolve_scan_prusament_url_without_scheme():
    # Some scanners strip the scheme; the substring match should still catch it.
    res = resolve_scan("prusament.com/spool/42/abc/")
    assert res["type"] == "prusament_url"
    assert res["spool_id"] == "42"


def test_resolve_scan_prusament_url_is_case_insensitive():
    res = resolve_scan("HTTPS://PRUSAMENT.COM/SPOOL/999/DEADBEEF/")
    assert res["type"] == "prusament_url"
    assert res["spool_id"] == "999"


def test_resolve_scan_generic_url_is_not_mistaken_for_prusament():
    res = resolve_scan("https://example.com/whatever/")
    assert res["type"] != "prusament_url"


# ---------------------------------------------------------------------------
# Stage 2b — /api/identify_scan handler for a Prusament-URL scan. The Spoolman
# and parser boundaries are mocked so no real data/network is touched; the real
# resolve_scan + compute_dirty_extras run, exercising the handler's decisions.
# ---------------------------------------------------------------------------

_URL = "https://prusament.com/spool/17705/5b1a183b26/"


@pytest.fixture
def client():
    app_module.app.config["TESTING"] = True
    return app_module.app.test_client()


def _parsed_obj(**over):
    """A standard_obj as PrusamentParser.search would return it."""
    obj = {
        "name": "Prusament PLA Galaxy Black",
        "material": "PLA",
        "vendor": {"name": "Prusament"},
        "settings_extruder_temp": 215,
        "settings_bed_temp": 60,
        "extra": {
            "nozzle_temp_max": "230",
            "bed_temp_max": "65",
            "prusament_manufacturing_date": "2026-01-02",
            "prusament_length_m": "330",
        },
    }
    obj.update(over)
    return obj


def _scan(client, url=_URL):
    return client.post("/api/identify_scan", json={"text": url, "source": "barcode"}).get_json()


def test_prusament_scan_no_match_returns_new_for_onboarding(client):
    with patch("external_parsers.search_external", return_value=[_parsed_obj()]), \
         patch("spoolman_api.get_all_spools", return_value=[
             {"id": 1, "extra": {"product_url": "https://prusament.com/spool/99999/abc/"}},
         ]):
        res = _scan(client)
    assert res["type"] == "prusament_new"
    assert res["spool_id"] == "17705"
    assert res["parsed"]["material"] == "PLA"


def test_prusament_scan_match_backfills_blank_temps(client):
    matched = {"id": 42, "extra": {"product_url": _URL}, "filament": {"id": 7}}
    blank_fil = {"id": 7, "name": "Prusament PLA", "settings_extruder_temp": None,
                 "settings_bed_temp": None, "extra": {"product_url": _URL}}
    with patch("external_parsers.search_external", return_value=[_parsed_obj()]), \
         patch("spoolman_api.get_all_spools", return_value=[matched]), \
         patch("spoolman_api.get_filament", return_value=blank_fil), \
         patch("spoolman_api.get_spools_for_filament", return_value=[matched]), \
         patch("spoolman_api.update_spool", return_value={"id": 42}), \
         patch("spoolman_api.update_filament_or_raise", return_value={"id": 7}) as upd:
        res = _scan(client)
    assert res["type"] == "prusament_matched" and res["status"] == "ok"
    assert res["filament_id"] == 7
    fid, data = upd.call_args[0]
    assert fid == 7
    assert data["settings_extruder_temp"] == 215
    assert data["settings_bed_temp"] == 60
    assert data["extra"]["nozzle_temp_max"] == "230"
    assert data["extra"]["bed_temp_max"] == "65"
    assert set(res["filled"]) == {
        "settings_extruder_temp", "settings_bed_temp", "nozzle_temp_max", "bed_temp_max",
    }
    assert res["conflicts"] == []


def test_prusament_scan_differing_temps_suggested_when_no_active_spools(client):
    matched = {"id": 42, "extra": {"product_url": _URL}, "filament": {"id": 7}, "archived": True}
    existing = {"id": 7, "name": "Prusament PLA", "settings_extruder_temp": 210,
                "settings_bed_temp": 60, "extra": {"nozzle_temp_max": "225", "bed_temp_max": "65"}}
    with patch("external_parsers.search_external", return_value=[_parsed_obj()]), \
         patch("spoolman_api.get_all_spools", return_value=[matched]), \
         patch("spoolman_api.get_filament", return_value=existing), \
         patch("spoolman_api.get_spools_for_filament", return_value=[matched]), \
         patch("spoolman_api.update_spool", return_value={"id": 42}), \
         patch("spoolman_api.update_filament_or_raise", return_value={"id": 7}):
        res = _scan(client)
    assert res["type"] == "prusament_matched"
    fields = {c["field"] for c in res["conflicts"]}
    assert "settings_extruder_temp" in fields   # 210 -> 215
    assert "nozzle_temp_max" in fields           # 225 -> 230
    assert "settings_bed_temp" not in fields     # 60 == 60
    assert "bed_temp_max" not in fields          # 65 == 65


def test_prusament_scan_differing_temps_suppressed_when_active_spool(client):
    matched = {"id": 42, "extra": {"product_url": _URL}, "filament": {"id": 7}, "archived": False}
    existing = {"id": 7, "name": "Prusament PLA", "settings_extruder_temp": 210,
                "settings_bed_temp": 60, "extra": {"nozzle_temp_max": "225", "bed_temp_max": "65"}}
    with patch("external_parsers.search_external", return_value=[_parsed_obj()]), \
         patch("spoolman_api.get_all_spools", return_value=[matched]), \
         patch("spoolman_api.get_filament", return_value=existing), \
         patch("spoolman_api.get_spools_for_filament", return_value=[matched]), \
         patch("spoolman_api.update_spool", return_value={"id": 42}), \
         patch("spoolman_api.update_filament_or_raise", return_value={"id": 7}):
        res = _scan(client)
    assert res["type"] == "prusament_matched"
    assert res["conflicts"] == []  # active spool in use -> suggestion suppressed


def test_prusament_scan_fetch_failure_is_reported(client):
    with patch("external_parsers.search_external", return_value=[]):
        res = _scan(client)
    assert res["type"] == "prusament_url"
    assert res["status"] == "fetch_failed"
