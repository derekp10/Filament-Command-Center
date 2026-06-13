"""FilaBridge Phase-2 cutover — the credential gate (L271 Phase 4 remainder).

Printer ip_address + api_key relocate OFF FilaBridge `GET /printers` and ONTO
the first-class Type:"Printer" row (`printer_creds` field), so the whole
PrusaLink read path (state/job/MMU probe, cancel-deduct download) stops
depending on FilaBridge being up. The MMU flag is NOT stored — it's a live
`/api/v1/info.mmu` probe gated only by these creds, so relocating creds covers
it for free.

Pinned here:
- locations_db.get_printer_credentials  — lookup by row Name, ip-required contract
- locations_db.seed_printer_credentials — prime-only boot auto-pull, idempotent
- locations_db.set_printer_credentials  — Settings-editor write (set / clear)
- prusalink_api.fetch_printer_credentials reads the LOCAL store now (signature
  unchanged so all 7 callers + ~12 test stubs are no-touch; filabridge_url ignored)
- prusalink_api.fetch_all_filabridge_printers parses /printers for the seed
- GET  /api/locations REDACTS printer_creds (api_key must never reach the browser)
- POST /api/locations PRESERVES printer_creds across a Location-Manager edit
  (the redaction means the edit modal can't echo it back, so a naive save would
  silently wipe it — same class as the parent_id-preserve right above it).
"""
import copy
from unittest.mock import patch, MagicMock

import pytest

import locations_db
import prusalink_api


XL_CREDS = {"ip_address": "192.168.1.50", "api_key": "XLKEY"}


def _rows():
    return [
        {"LocationID": "XL", "Type": "Printer", "Name": "🦝 XL", "parent_id": "LR",
         "printer_creds": dict(XL_CREDS)},
        {"LocationID": "CORE1", "Type": "Printer", "Name": "🦦 Core One Upgraded",
         "parent_id": "CR"},  # no creds yet — the seed target
        {"LocationID": "XL-1", "Type": "Tool Head", "Name": "XL T1", "parent_id": "XL"},
    ]


# --------------------------------------------------------------------------- #
# get_printer_credentials                                                      #
# --------------------------------------------------------------------------- #

def test_get_creds_matches_by_name():
    out = locations_db.get_printer_credentials("🦝 XL", _rows())
    assert out == XL_CREDS


def test_get_creds_row_without_creds_returns_none():
    assert locations_db.get_printer_credentials("🦦 Core One Upgraded", _rows()) is None


def test_get_creds_unknown_name_returns_none():
    assert locations_db.get_printer_credentials("Nope", _rows()) is None


def test_get_creds_empty_name_returns_none():
    assert locations_db.get_printer_credentials("", _rows()) is None
    assert locations_db.get_printer_credentials(None, _rows()) is None


def test_get_creds_blank_ip_returns_none():
    rows = [{"LocationID": "XL", "Type": "Printer", "Name": "🦝 XL",
             "printer_creds": {"ip_address": "  ", "api_key": "k"}}]
    assert locations_db.get_printer_credentials("🦝 XL", rows) is None


def test_get_creds_missing_api_key_still_returns_ip():
    rows = [{"LocationID": "XL", "Type": "Printer", "Name": "🦝 XL",
             "printer_creds": {"ip_address": "1.2.3.4"}}]
    assert locations_db.get_printer_credentials("🦝 XL", rows) == {
        "ip_address": "1.2.3.4", "api_key": None}


def test_get_creds_ignores_non_printer_row_with_same_name():
    rows = [{"LocationID": "X", "Type": "Tool Head", "Name": "🦝 XL",
             "printer_creds": {"ip_address": "9.9.9.9", "api_key": "k"}}]
    assert locations_db.get_printer_credentials("🦝 XL", rows) is None


# --------------------------------------------------------------------------- #
# seed_printer_credentials                                                     #
# --------------------------------------------------------------------------- #

def test_seed_fills_missing_row():
    rows = _rows()
    fb = {"🦦 Core One Upgraded": {"ip_address": "10.0.0.9", "api_key": "C1KEY"}}
    out, changed = locations_db.seed_printer_credentials(rows, fb)
    assert changed is True
    assert locations_db.get_printer_credentials("🦦 Core One Upgraded", out) == {
        "ip_address": "10.0.0.9", "api_key": "C1KEY"}


def test_seed_prime_only_never_overwrites_existing():
    rows = _rows()
    fb = {"🦝 XL": {"ip_address": "BOGUS", "api_key": "BOGUS"}}  # would clobber
    out, changed = locations_db.seed_printer_credentials(rows, fb, prime_only=True)
    assert changed is False
    assert locations_db.get_printer_credentials("🦝 XL", out) == XL_CREDS


def test_seed_idempotent_second_run():
    rows = _rows()
    fb = {"🦦 Core One Upgraded": {"ip_address": "10.0.0.9", "api_key": "C1KEY"}}
    out, c1 = locations_db.seed_printer_credentials(rows, fb)
    out, c2 = locations_db.seed_printer_credentials(out, fb)
    assert c1 is True and c2 is False


def test_seed_skips_blank_ip_and_missing_src():
    rows = _rows()
    fb = {"🦦 Core One Upgraded": {"ip_address": "   ", "api_key": "x"}}  # blank ip
    out, changed = locations_db.seed_printer_credentials(rows, fb)
    assert changed is False
    assert locations_db.get_printer_credentials("🦦 Core One Upgraded", out) is None


def test_seed_leaves_non_printer_rows_untouched():
    rows = _rows()
    fb = {"XL T1": {"ip_address": "1.1.1.1", "api_key": "k"}}  # a tool head name
    out, changed = locations_db.seed_printer_credentials(rows, fb)
    assert changed is False
    th = next(r for r in out if r["LocationID"] == "XL-1")
    assert "printer_creds" not in th


def test_seed_force_overwrite_when_not_prime_only():
    rows = _rows()
    fb = {"🦝 XL": {"ip_address": "2.2.2.2", "api_key": "NEW"}}
    out, changed = locations_db.seed_printer_credentials(rows, fb, prime_only=False)
    assert changed is True
    assert locations_db.get_printer_credentials("🦝 XL", out) == {
        "ip_address": "2.2.2.2", "api_key": "NEW"}


# --------------------------------------------------------------------------- #
# set_printer_credentials (Settings-editor write)                             #
# --------------------------------------------------------------------------- #

def test_set_creds_writes_and_updates():
    rows = _rows()
    out, changed = locations_db.set_printer_credentials(rows, "🦦 Core One Upgraded", "10.0.0.9", "K")
    assert changed is True
    assert locations_db.get_printer_credentials("🦦 Core One Upgraded", out) == {
        "ip_address": "10.0.0.9", "api_key": "K"}


def test_set_creds_blank_ip_removes():
    rows = _rows()
    out, changed = locations_db.set_printer_credentials(rows, "🦝 XL", "", "anything")
    assert changed is True
    assert "printer_creds" not in next(r for r in out if r["LocationID"] == "XL")


def test_set_creds_unchanged_is_noop():
    rows = _rows()
    out, changed = locations_db.set_printer_credentials(rows, "🦝 XL", "192.168.1.50", "XLKEY")
    assert changed is False


def test_set_creds_unknown_name_noop():
    rows = _rows()
    out, changed = locations_db.set_printer_credentials(rows, "Nope", "1.2.3.4", "k")
    assert changed is False


# --------------------------------------------------------------------------- #
# prusalink_api.fetch_printer_credentials — now reads the local store          #
# --------------------------------------------------------------------------- #

def test_fetch_printer_credentials_delegates_to_local_store_ignoring_fb_url():
    with patch.object(locations_db, "get_printer_credentials",
                      return_value={"ip_address": "1.2.3.4", "api_key": "k"}) as m:
        out = prusalink_api.fetch_printer_credentials("http://fb/api", "🦦 Core One Upgraded")
    assert out == {"ip_address": "1.2.3.4", "api_key": "k"}
    # filabridge_url is ignored — only the printer name is forwarded.
    m.assert_called_once_with("🦦 Core One Upgraded")


def test_fetch_printer_credentials_returns_none_on_error():
    with patch.object(locations_db, "get_printer_credentials", side_effect=RuntimeError("boom")):
        assert prusalink_api.fetch_printer_credentials("http://fb/api", "🦝 XL") is None


# --------------------------------------------------------------------------- #
# prusalink_api.fetch_all_filabridge_printers — the seed source                #
# --------------------------------------------------------------------------- #

def test_fetch_all_printers_parses_shape():
    resp = MagicMock()
    resp.ok = True
    resp.json.return_value = {"printers": {
        "p1": {"name": "🦦 Core One Upgraded", "ip_address": "1.2.3.4", "api_key": "k"},
        "p2": {"name": "🦝 XL", "ip_address": "5.6.7.8", "api_key": "k2"},
        "bad": {"ip_address": "9.9.9.9"},  # no name → skipped
    }}
    with patch.object(prusalink_api.requests, "get", return_value=resp):
        out = prusalink_api.fetch_all_filabridge_printers("http://fb/api")
    assert out == {
        "🦦 Core One Upgraded": {"ip_address": "1.2.3.4", "api_key": "k"},
        "🦝 XL": {"ip_address": "5.6.7.8", "api_key": "k2"},
    }


def test_fetch_all_printers_returns_empty_on_failure():
    resp = MagicMock()
    resp.ok = False
    with patch.object(prusalink_api.requests, "get", return_value=resp):
        assert prusalink_api.fetch_all_filabridge_printers("http://fb/api") == {}
    with patch.object(prusalink_api.requests, "get", side_effect=RuntimeError("down")):
        assert prusalink_api.fetch_all_filabridge_printers("http://fb/api") == {}


# --------------------------------------------------------------------------- #
# Endpoint surfaces — redaction + save-preserve                               #
# --------------------------------------------------------------------------- #

@pytest.fixture
def client():
    import app
    app.app.config["TESTING"] = True
    return app.app.test_client()


def test_get_locations_redacts_printer_creds(client):
    import app
    spool_resp = MagicMock()
    spool_resp.ok = True
    spool_resp.json.return_value = []
    with patch.object(app.locations_db, "load_locations_list", return_value=copy.deepcopy(_rows())), \
         patch.object(app.spoolman_api, "get_all_locations", return_value=[]), \
         patch.object(app.config_loader, "get_api_urls", return_value=("http://spool", "http://fb/api")), \
         patch.object(app.requests, "get", return_value=spool_resp):
        res = client.get("/api/locations")
    assert res.status_code == 200
    rows = res.get_json()
    assert any(r.get("LocationID") == "XL" for r in rows), "XL printer row should be present"
    assert all("printer_creds" not in r for r in rows), "printer_creds must be redacted from the GET"


def test_save_location_preserves_creds_on_rename(client):
    import app
    saved = {}

    def _capture(lst):
        saved["list"] = copy.deepcopy(lst)
        return True

    with patch.object(app.locations_db, "load_locations_list", return_value=copy.deepcopy(_rows())), \
         patch.object(app.locations_db, "save_locations_list", side_effect=_capture):
        res = client.post("/api/locations", json={
            "old_id": "XL",
            # The edit modal posts the visible fields only — never printer_creds.
            "new_data": {"LocationID": "XL", "Name": "🦝 XL Renamed",
                         "Type": "Printer", "Max Spools": "0"},
        })
    assert res.status_code == 200
    xl = next(r for r in saved["list"] if r.get("LocationID") == "XL")
    assert xl.get("printer_creds") == XL_CREDS, "creds must survive a Location-Manager edit"
    assert xl.get("Name") == "🦝 XL Renamed"


def test_save_location_explicit_creds_not_overridden_by_carry(client):
    import app
    saved = {}

    def _capture(lst):
        saved["list"] = copy.deepcopy(lst)
        return True

    new_creds = {"ip_address": "9.9.9.9", "api_key": "NEW"}
    with patch.object(app.locations_db, "load_locations_list", return_value=copy.deepcopy(_rows())), \
         patch.object(app.locations_db, "save_locations_list", side_effect=_capture):
        res = client.post("/api/locations", json={
            "old_id": "XL",
            "new_data": {"LocationID": "XL", "Name": "🦝 XL", "Type": "Printer",
                         "Max Spools": "0", "printer_creds": new_creds},
        })
    assert res.status_code == 200
    xl = next(r for r in saved["list"] if r.get("LocationID") == "XL")
    assert xl.get("printer_creds") == new_creds
