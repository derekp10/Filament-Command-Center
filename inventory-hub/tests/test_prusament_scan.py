"""feature/scan-match-pipeline — Prusament-QR scan pipeline.

A physical Prusament spool label encodes a https://prusament.com/spool/<id>/<hash>/
URL. resolve_scan must recognize it as a dedicated `prusament_url` type (matched by
the numeric spool <id>) so /api/identify_scan can either backfill nozzle/bed temps
onto the matching existing filament or onboard a brand-new spool.
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from unittest.mock import patch  # noqa: E402

import pytest  # noqa: E402
from playwright.sync_api import expect  # noqa: E402

from logic import resolve_scan  # noqa: E402
import app as app_module  # noqa: E402


def test_resolve_scan_recognizes_prusament_url():
    res = resolve_scan("https://prusament.com/spool/17705/5b1a183b26/")
    assert res == {
        "type": "prusament_url",
        "url": "https://prusament.com/spool/17705/5b1a183b26/",
        "spool_id": "17705",
        "spool_hash": "5b1a183b26",
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


def test_resolve_scan_captures_spool_hash():
    # The trailing URL segment is the unique *physical spool* hash. Capturing it
    # lets spool-level ops (e.g. L200 weight correction) target the exact spool
    # rather than the first owned duplicate of the same product <id>.
    res = resolve_scan("https://prusament.com/spool/17705/5b1a183b26/")
    assert res["spool_hash"] == "5b1a183b26"


def test_resolve_scan_captures_all_digit_spool_hash():
    # Some real Prusament hashes are all digits (e.g. seed-data 2117943310). The
    # greedy product-id group must stop at the '/' and NOT swallow the hash.
    res = resolve_scan("https://prusament.com/spool/17705/2117943310/")
    assert res["spool_id"] == "17705"
    assert res["spool_hash"] == "2117943310"


def test_resolve_scan_spool_hash_is_none_when_absent():
    # A bare product URL with no hash segment still recognizes (keyed on <id>),
    # and spool_hash is None so the matcher can fall back to product granularity.
    res = resolve_scan("https://prusament.com/spool/17705")
    assert res["type"] == "prusament_url"
    assert res["spool_id"] == "17705"
    assert res["spool_hash"] is None


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
    # No spool's product_url matches the scanned id -> fast onboard response
    # (match-first means NO prusament.com fetch on this path).
    with patch("spoolman_api.get_all_spools", return_value=[
        {"id": 1, "extra": {"product_url": "https://prusament.com/spool/99999/abc/"}},
    ]):
        res = _scan(client)
    assert res["type"] == "prusament_new"
    assert res["spool_id"] == "17705"
    assert res["url"] == _URL
    assert res["spool_hash"] == "5b1a183b26"   # surface #3: the hash rides along to onboarding


def test_prusament_scan_duplicate_product_matches_exact_hash_spool(client):
    # Two physical spools share product 17705 but have distinct hashes. Scanning
    # the SECOND one's hash must resolve to THAT spool (id 43), not the first
    # owned duplicate (id 42) the way the old product-id-only needle did.
    url_a = "https://prusament.com/spool/17705/5b1a183b26/"
    url_b = "https://prusament.com/spool/17705/6100497ffc/"
    spool_a = {"id": 42, "extra": {"product_url": url_a}, "filament": {"id": 7}}
    spool_b = {"id": 43, "extra": {"product_url": url_b}, "filament": {"id": 7}}
    blank_fil = {"id": 7, "name": "Prusament PLA", "settings_extruder_temp": None,
                 "settings_bed_temp": None, "extra": {}}
    with patch("external_parsers.search_external", return_value=[_parsed_obj()]), \
         patch("spoolman_api.get_all_spools", return_value=[spool_a, spool_b]), \
         patch("spoolman_api.get_filament", return_value=blank_fil), \
         patch("spoolman_api.get_spools_for_filament", return_value=[spool_a, spool_b]), \
         patch("spoolman_api.update_spool", return_value={"id": 43}), \
         patch("spoolman_api.update_filament_or_raise", return_value={"id": 7}):
        res = _scan(client, url=url_b)
    assert res["type"] == "prusament_matched"
    assert res["spool_id"] == 43   # the EXACT-hash spool, not the first duplicate (42)


def test_prusament_scan_unowned_hash_onboards_even_when_product_owned(client):
    # You own a sibling spool of the SAME product (hash A) but NOT the exact
    # physical spool being scanned (hash B). Per the design call, an unowned
    # exact spool is treated as brand-new (onboard) rather than silently
    # operating on the owned sibling. The unique hash rides along so the Add
    # wizard can record the exact spool. Match-first means NO page fetch here.
    url_a = "https://prusament.com/spool/17705/5b1a183b26/"
    url_b = "https://prusament.com/spool/17705/6100497ffc/"
    owned_sibling = {"id": 42, "extra": {"product_url": url_a}, "filament": {"id": 7}}
    with patch("spoolman_api.get_all_spools", return_value=[owned_sibling]):
        res = _scan(client, url=url_b)
    assert res["type"] == "prusament_new"
    assert res["spool_id"] == "17705"
    assert res["spool_hash"] == "6100497ffc"
    assert res["url"] == url_b


def test_prusament_scan_matches_query_form_stored_url_by_hash(client):
    # Some spools store product_url in the QUERY form (?spoolId=<hash>) rather
    # than the path form. The physical QR still scans as the path form
    # (/spool/<id>/<hash>); matching on the UNIQUE hash resolves the exact spool
    # regardless of stored URL shape. (Query-form spools were previously
    # unmatchable and would re-onboard.)
    scanned = "https://prusament.com/spool/17705/730b53b325/"
    stored = {"id": 71,
              "extra": {"product_url": "https://prusament.com/spool/?spoolId=730b53b325"},
              "filament": {"id": 7}}
    blank_fil = {"id": 7, "name": "Prusament PLA", "settings_extruder_temp": None,
                 "settings_bed_temp": None, "extra": {}}
    with patch("external_parsers.search_external", return_value=[_parsed_obj()]), \
         patch("spoolman_api.get_all_spools", return_value=[stored]), \
         patch("spoolman_api.get_filament", return_value=blank_fil), \
         patch("spoolman_api.get_spools_for_filament", return_value=[stored]), \
         patch("spoolman_api.update_spool", return_value={"id": 71}), \
         patch("spoolman_api.update_filament_or_raise", return_value={"id": 7}):
        res = _scan(client, url=scanned)
    assert res["type"] == "prusament_matched"
    assert res["spool_id"] == 71   # matched the query-form spool via its hash


def test_prusament_scan_query_form_hash_is_precise_not_sibling(client):
    # A query-form spool with a DIFFERENT hash must NOT match — matching is on
    # the unique hash, so an unowned scan still routes to onboard (never a
    # wrong-sibling correction).
    scanned = "https://prusament.com/spool/17705/730b53b325/"
    other = {"id": 71,
             "extra": {"product_url": "https://prusament.com/spool/?spoolId=d9e6fdadda"},
             "filament": {"id": 7}}
    with patch("spoolman_api.get_all_spools", return_value=[other]):
        res = _scan(client, url=scanned)
    assert res["type"] == "prusament_new"
    assert res["spool_hash"] == "730b53b325"


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
    # Each conflict carries the native flag + a friendly label for the overlay.
    by_field = {c["field"]: c for c in res["conflicts"]}
    assert by_field["settings_extruder_temp"]["native"] is True
    assert by_field["nozzle_temp_max"]["native"] is False
    assert by_field["settings_extruder_temp"]["label"] == "Nozzle (min)"
    assert by_field["nozzle_temp_max"]["label"] == "Nozzle (max)"


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
    # A match exists, but the Prusament page can't be read -> fetch_failed
    # (the fetch only happens on the matched path now).
    matched = {"id": 42, "extra": {"product_url": _URL}, "filament": {"id": 7}}
    with patch("spoolman_api.get_all_spools", return_value=[matched]), \
         patch("external_parsers.search_external", return_value=[]):
        res = _scan(client)
    assert res["type"] == "prusament_url"
    assert res["status"] == "fetch_failed"


# ---------------------------------------------------------------------------
# L200 — spool weight-field correction from a matched Prusament scan.
# `_compute_prusament_spool_weight_diff` is pure (used-preserving model);
# the handler attaches its result to the prusament_matched payload — computed,
# NEVER auto-applied (Derek chose a confirm overlay 2026-06-05).
# ---------------------------------------------------------------------------


def test_spool_weight_diff_fills_missing_tare_and_corrects_total():
    matched = {"id": 42, "initial_weight": 900, "used_weight": 300, "spool_weight": None}
    fil = {"id": 7, "weight": 900, "spool_weight": None, "vendor": {}}
    obj = {"weight": 1000.0, "spool_weight": 201.0}
    diff = app_module._compute_prusament_spool_weight_diff(matched, fil, obj)
    assert diff["updates"] == {"initial_weight": 1000.0, "spool_weight": 201.0}
    # used preserved → the consumption history is untouched, so the update
    # payload must never carry used_weight.
    assert "used_weight" not in diff["updates"]
    assert diff["used"] == 300
    assert diff["remaining"]["current"] == 600   # 900 - 300 (the OLD, wrong total)
    assert diff["remaining"]["new"] == 700        # 1000 - 300 (recomputed correctly)
    assert diff["blocked"] is None


def test_spool_weight_diff_none_when_already_correct():
    matched = {"id": 42, "initial_weight": 1000, "used_weight": 300, "spool_weight": 201}
    fil = {"id": 7, "weight": 1000, "spool_weight": 201, "vendor": {}}
    obj = {"weight": 1000.0, "spool_weight": 201.0}
    assert app_module._compute_prusament_spool_weight_diff(matched, fil, obj) is None


def test_spool_weight_diff_uses_filament_then_vendor_tare_fallback():
    # Spool has no own tare, but the filament carries one matching the scan →
    # no tare change proposed (effective-tare resolution mirrors the frontend).
    matched = {"id": 42, "initial_weight": 1000, "used_weight": 0, "spool_weight": None}
    fil = {"id": 7, "weight": 1000, "spool_weight": 201, "vendor": {}}
    obj = {"weight": 1000.0, "spool_weight": 201.0}
    assert app_module._compute_prusament_spool_weight_diff(matched, fil, obj) is None
    # vendor fallback too
    fil2 = {"id": 7, "weight": 1000, "spool_weight": None, "vendor": {"empty_spool_weight": 201}}
    assert app_module._compute_prusament_spool_weight_diff(matched, fil2, obj) is None


def test_spool_weight_diff_blocks_total_below_used():
    # A scanned net at/below what's already been used would zero remaining and
    # trip Spoolman's auto-archive. Refuse it; surface a warning.
    matched = {"id": 42, "initial_weight": 1200, "used_weight": 1100, "spool_weight": 201}
    fil = {"id": 7, "weight": 1200, "spool_weight": 201, "vendor": {}}
    obj = {"weight": 1000.0, "spool_weight": 201.0}
    diff = app_module._compute_prusament_spool_weight_diff(matched, fil, obj)
    assert "initial_weight" not in diff["updates"]
    assert diff["blocked"] and "already used" in diff["blocked"]


def test_prusament_scan_matched_includes_spool_weight_diff(client):
    matched = {"id": 42, "extra": {"product_url": _URL}, "filament": {"id": 7},
               "initial_weight": 900, "used_weight": 300, "spool_weight": None}
    fil = {"id": 7, "name": "Prusament PLA", "weight": 900, "spool_weight": None,
           "vendor": {}, "settings_extruder_temp": 215, "settings_bed_temp": 60,
           "extra": {"nozzle_temp_max": "230", "bed_temp_max": "65"}}
    obj = _parsed_obj(weight=1000.0, spool_weight=201.0)  # temps already match fil
    with patch("external_parsers.search_external", return_value=[obj]), \
         patch("spoolman_api.get_all_spools", return_value=[matched]), \
         patch("spoolman_api.get_filament", return_value=fil), \
         patch("spoolman_api.get_spools_for_filament", return_value=[matched]), \
         patch("spoolman_api.update_spool", return_value={"id": 42}), \
         patch("spoolman_api.update_filament_or_raise", return_value={"id": 7}):
        res = _scan(client)
    assert res["type"] == "prusament_matched" and res["status"] == "ok"
    sw = res["spool_weight"]
    assert sw is not None
    assert sw["updates"] == {"initial_weight": 1000.0, "spool_weight": 201.0}
    assert sw["remaining"]["current"] == 600 and sw["remaining"]["new"] == 700


# ---------------------------------------------------------------------------
# L200 hardening (2026-06-05 adversarial review) — safety gates on the diff and
# live re-validation on the apply.
# ---------------------------------------------------------------------------


def test_spool_weight_diff_skips_archived_spool():
    # An archived spool must NOT be silently resurrected by a weight correction.
    matched = {"id": 42, "initial_weight": 900, "used_weight": 300,
               "spool_weight": None, "archived": True}
    fil = {"id": 7, "weight": 900, "spool_weight": None, "vendor": {}}
    obj = {"weight": 1000.0, "spool_weight": 201.0}
    assert app_module._compute_prusament_spool_weight_diff(matched, fil, obj) is None


def test_spool_weight_diff_ignores_parser_default_weight():
    # The parser flags a fabricated 1000g (blob omitted weight); it must not be
    # offered as a total correction on a non-1kg spool.
    matched = {"id": 42, "initial_weight": 2000, "used_weight": 300, "spool_weight": 250}
    fil = {"id": 7, "weight": 2000, "spool_weight": 250, "vendor": {}}
    obj = {"weight": 1000.0, "weight_is_default": True, "spool_weight": 250.0}
    assert app_module._compute_prusament_spool_weight_diff(matched, fil, obj) is None


def test_spool_weight_diff_tare_falls_through_spoolman_zero_default():
    # Spoolman stores an un-set tare as 0.0 (not null) on most spools; treat 0 as
    # unset and inherit the filament/vendor tare → no spurious "0g → Ng" diff.
    matched = {"id": 42, "initial_weight": 1000, "used_weight": 0, "spool_weight": 0.0}
    fil = {"id": 7, "weight": 1000, "spool_weight": 201, "vendor": {}}
    obj = {"weight": 1000.0, "spool_weight": 201.0}
    assert app_module._compute_prusament_spool_weight_diff(matched, fil, obj) is None
    # vendor fallback also resolves through a 0.0 spool tare
    fil2 = {"id": 7, "weight": 1000, "spool_weight": 0.0, "vendor": {"empty_spool_weight": 201}}
    assert app_module._compute_prusament_spool_weight_diff(matched, fil2, obj) is None


def test_spool_weight_diff_blocks_correction_that_would_empty_spool():
    # Legacy over-entered initial (1050) on a near-fully-used spool (used 1000):
    # correcting the total to the true net (1000) would zero remaining and trip
    # auto-archive — so block it rather than propose it.
    matched = {"id": 42, "initial_weight": 1050, "used_weight": 1000, "spool_weight": 278}
    fil = {"id": 7, "weight": 1050, "spool_weight": 278, "vendor": {}}
    obj = {"weight": 1000.0, "spool_weight": 278.0}
    diff = app_module._compute_prusament_spool_weight_diff(matched, fil, obj)
    assert "initial_weight" not in diff["updates"]
    assert diff["blocked"] and "archive" in diff["blocked"]


def test_prusament_apply_weights_success(client):
    live = {"id": 42, "used_weight": 300, "initial_weight": 950, "archived": False}
    with patch("spoolman_api.get_spool", return_value=live), \
         patch("spoolman_api.update_spool_or_raise", return_value={"id": 42}) as upd:
        res = client.post("/api/spool/prusament_apply_weights", json={
            "spool_id": 42, "updates": {"initial_weight": 1065.0, "spool_weight": 278.0},
        }).get_json()
    assert res["status"] == "success"
    sid, data = upd.call_args[0]
    assert sid == 42
    assert data == {"initial_weight": 1065.0, "spool_weight": 278.0}
    assert "used_weight" not in data   # consumption preserved


def test_prusament_apply_weights_blocks_archived(client):
    live = {"id": 42, "used_weight": 300, "initial_weight": 900, "archived": True}
    with patch("spoolman_api.get_spool", return_value=live), \
         patch("spoolman_api.update_spool_or_raise") as upd:
        res = client.post("/api/spool/prusament_apply_weights", json={
            "spool_id": 42, "updates": {"initial_weight": 1065.0},
        }).get_json()
    assert res["status"] == "blocked"
    upd.assert_not_called()


def test_prusament_apply_weights_blocks_would_empty_against_live_used(client):
    # TOCTOU guard: live used has risen to 1065 since the scan; applying initial
    # 1065 would zero remaining + auto-archive — refuse against the LIVE value.
    live = {"id": 42, "used_weight": 1065, "initial_weight": 1200, "archived": False}
    with patch("spoolman_api.get_spool", return_value=live), \
         patch("spoolman_api.update_spool_or_raise") as upd:
        res = client.post("/api/spool/prusament_apply_weights", json={
            "spool_id": 42, "updates": {"initial_weight": 1065.0},
        }).get_json()
    assert res["status"] == "blocked"
    upd.assert_not_called()


def test_prusament_parser_emits_length_as_string():
    # Regression: prusament_length_m is a Spoolman TEXT field, so the parser must
    # emit a string — a raw int 400s the metadata backfill ("Value is not a
    # string") on the matched-scan path. (Found during the 2026-06-05 live demo.)
    import external_parsers  # noqa: E402
    blob = {
        "filament": {"name": "Prusament PETG Blue", "material": "PETG",
                     "color_rgb": "#1a0076", "color_name": "Blue",
                     "he_min": 240, "he_max": 260, "hb_min": 70, "hb_max": 90},
        "weight": 1020, "spool_weight": 278, "length": 336,
        "manufacture_date": "2026-01-25T17:07:56+01:00", "ff_goods_id": 17637,
    }
    resp = type("R", (), {"ok": True, "text": "var spoolData = '" + json.dumps(blob) + "';"})()
    with patch("external_parsers.requests.get", return_value=resp):
        out = external_parsers.PrusamentParser.search("https://prusament.com/spool/17637/abc")
    assert out and isinstance(out[0]["extra"]["prusament_length_m"], str)
    assert out[0]["extra"]["prusament_length_m"] == "336"
    assert out[0]["weight_is_default"] is False   # real reading, not the 1000g default


# ---------------------------------------------------------------------------
# Stage 3 (frontend) — a 'prusament_new' scan opens the Add wizard pre-filled
# from the scanned URL. Hermetic: the scan endpoint AND the wizard's external
# search are mocked via page.route, so no real backend / prusament.com hit.
# ---------------------------------------------------------------------------

@pytest.mark.usefixtures("require_server")
def test_prusament_new_scan_opens_prefilled_add_wizard(page, base_url, reset_dom_state_js):
    url = "https://prusament.com/spool/17705/abc123/"
    template = {
        "name": "Prusament PLA Galaxy Black", "material": "PLA",
        "vendor": {"name": "Prusament"}, "color_name": "Galaxy Black",
        "color_hex": "1a1a2e", "weight": 1000,
        "settings_extruder_temp": 215, "settings_bed_temp": 60,
    }
    page.goto(base_url)
    page.wait_for_selector("#command-buffer, #buffer-zone", timeout=10000)
    page.evaluate(reset_dom_state_js)
    page.wait_for_function(
        "typeof processScan === 'function' && typeof openWizardModal === 'function'",
        timeout=10000,
    )
    page.route("**/api/identify_scan", lambda route: route.fulfill(
        status=200, content_type="application/json",
        body=json.dumps({"type": "prusament_new", "spool_id": "17705", "url": url}),
    ))
    # Exactly one external result -> auto-applied; empty filament list -> the
    # dup-matcher finds nothing, so it FILLS the form (vs. auto-switch to existing).
    page.route("**/api/external/search**", lambda route: route.fulfill(
        status=200, content_type="application/json",
        body=json.dumps({"success": True, "results": [template]}),
    ))
    page.route("**/api/filaments", lambda route: route.fulfill(
        status=200, content_type="application/json", body=json.dumps({"filaments": []})))

    page.evaluate(f"processScan({json.dumps(url)}, 'barcode')")
    expect(page.locator("#wizardModal")).to_be_visible(timeout=6000)
    # Onboarding drives the Step-3 per-spool scan, which fills BOTH halves: the
    # spool override is captured AND (no filament match here) the filament fields
    # populate. Asserting the filament fields proves the per-spool scan ran end to
    # end — its spool-half (row.override) is set first, before the filament match.
    expect(page.locator("#wiz-fil-material")).to_have_value("PLA", timeout=6000)
    expect(page.locator("#wiz-fil-color_name")).to_have_value("Galaxy Black", timeout=4000)
    # The scanned URL is shown in the spool row's field (visible + copyable).
    expect(page.locator("[data-spool-row-idx] input[type='url']").first).to_have_value(url, timeout=4000)


@pytest.mark.usefixtures("require_server")
def test_prusament_matched_scan_overlay_updates_conflicting_temps(page, base_url, reset_dom_state_js):
    url = "https://prusament.com/spool/17705/abc/"
    matched_resp = {
        "type": "prusament_matched", "status": "ok", "spool_id": 42, "filament_id": 7,
        "filament_name": "Prusament PLA Galaxy Black", "filled": ["settings_bed_temp"],
        "conflicts": [
            {"field": "settings_extruder_temp", "label": "Nozzle (min)", "current": "210", "scanned": "215", "native": True},
            {"field": "nozzle_temp_max", "label": "Nozzle (max)", "current": "225", "scanned": "230", "native": False},
        ],
    }
    page.goto(base_url)
    page.wait_for_selector("#command-buffer, #buffer-zone", timeout=10000)
    page.evaluate(reset_dom_state_js)
    page.wait_for_function(
        "typeof processScan === 'function' && typeof window.mountOverlay === 'function'",
        timeout=10000,
    )
    page.route("**/api/identify_scan", lambda route: route.fulfill(
        status=200, content_type="application/json", body=json.dumps(matched_resp)))
    captured = {}

    def _capture(route):
        captured["body"] = route.request.post_data
        route.fulfill(status=200, content_type="application/json", body=json.dumps({"success": True}))

    page.route("**/api/update_filament", _capture)

    page.evaluate(f"processScan({json.dumps(url)}, 'barcode')")
    overlay = page.locator("#fcc-prusament-matched-overlay")
    expect(overlay).to_be_visible(timeout=6000)
    expect(overlay).to_contain_text("current spec differs")
    overlay.locator("#pm-update-temps").click()
    expect(overlay).to_be_hidden(timeout=6000)

    body = json.loads(captured["body"])
    assert body["id"] == 7
    assert body["data"]["settings_extruder_temp"] == 215        # native -> number
    assert body["data"]["extra"]["nozzle_temp_max"] == "230"    # extra -> string


@pytest.mark.usefixtures("require_server")
def test_prusament_matched_overlay_updates_spool_weights(page, base_url, reset_dom_state_js):
    # L200 — the matched overlay renders the spool weight diff (total / tare /
    # recomputed remaining) and POSTs the backend's used-preserving `updates`
    # verbatim to /api/spool/update on confirm.
    url = "https://prusament.com/spool/17705/abc/"
    matched_resp = {
        "type": "prusament_matched", "status": "ok", "spool_id": 42, "filament_id": 7,
        "filament_name": "Prusament PLA Galaxy Black", "filled": [], "conflicts": [],
        "spool_weight": {
            "updates": {"initial_weight": 1000.0, "spool_weight": 201.0},
            "rows": [
                {"key": "initial_weight", "label": "Total (net)", "current": 900, "scanned": 1000},
                {"key": "spool_weight", "label": "Empty spool (tare)", "current": None, "scanned": 201},
            ],
            "used": 300,
            "remaining": {"current": 600, "new": 700},
            "blocked": None,
        },
    }
    page.goto(base_url)
    page.wait_for_selector("#command-buffer, #buffer-zone", timeout=10000)
    page.evaluate(reset_dom_state_js)
    page.wait_for_function(
        "typeof processScan === 'function' && typeof window.mountOverlay === 'function'",
        timeout=10000,
    )
    page.route("**/api/identify_scan", lambda route: route.fulfill(
        status=200, content_type="application/json", body=json.dumps(matched_resp)))
    captured = {}

    def _capture(route):
        captured["body"] = route.request.post_data
        route.fulfill(status=200, content_type="application/json", body=json.dumps({"status": "success"}))

    page.route("**/api/spool/prusament_apply_weights", _capture)

    page.evaluate(f"processScan({json.dumps(url)}, 'barcode')")
    overlay = page.locator("#fcc-prusament-matched-overlay")
    expect(overlay).to_be_visible(timeout=6000)
    expect(overlay).to_contain_text("Total (net)")
    expect(overlay).to_contain_text("700g")   # recomputed remaining, used kept
    overlay.locator("#pm-update-weights").click()
    expect(overlay).to_be_hidden(timeout=6000)

    body = json.loads(captured["body"])
    assert body["spool_id"] == 42
    assert body["updates"] == {"initial_weight": 1000.0, "spool_weight": 201.0}
