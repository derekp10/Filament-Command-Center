"""Group 49.2a: the ⚠️ Low-stock list (stock_report.build_report, GET /api/stock_report)
and its `low_stock_g` setting.

Stock is counted per FILAMENT across its in-stock spools (not archived, grams
left). Low = under `low_stock_g` (default 250 g). Out = spools on record, none in
stock; a filament with no spools at all is never listed, and a "One-off" filament
stays off "out". The list reads Spoolman once, strictly: a failed read answers an
error, never an empty or "all out" list.

Hermetic: Spoolman is a fake (the strict read or `requests.get` is patched), the
config is patched. Runs under --offline.
"""
from __future__ import annotations

import copy
import json
import os
import sys
from unittest.mock import MagicMock

import pytest
import requests

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import app as app_module  # noqa: E402  (registers the routes)
import config_loader  # noqa: E402
import config_schema  # noqa: E402
import spoolman_api  # noqa: E402
import stock_report  # noqa: E402


def _fil(fid, name="Galaxy Black", vendor="Prusament", material="PLA", attrs=None,
         color_hex="222222", weight=1000, extra=None, **more):
    ex = {"original_color": name}
    if attrs is not None:
        ex["filament_attributes"] = list(attrs)
    ex.update(extra or {})
    f = {"id": fid, "name": name, "material": material, "color_hex": color_hex,
         "vendor": {"id": 1, "name": vendor}, "weight": weight, "extra": ex}
    f.update(more)
    return f


def _spool(sid, fil, remaining, archived=False, location=""):
    """A spool as Spoolman lists it (parsed form): remaining_weight computed."""
    used = fil["weight"] - remaining
    return {"id": sid, "filament": copy.deepcopy(fil), "initial_weight": fil["weight"],
            "used_weight": used, "remaining_weight": remaining, "archived": archived,
            "location": location, "extra": {}}


@pytest.fixture
def cfg(monkeypatch):
    """The config build_report reads (threshold + Buy More template)."""
    holder = {"low_stock_g": 250}
    monkeypatch.setattr(config_loader, "load_config", lambda: dict(holder))
    return holder


@pytest.fixture
def spoolman(monkeypatch):
    """The strict all-spools read, answering whatever the test puts in it."""
    holder = {"spools": [], "calls": []}

    def _read(allow_archived=False):
        holder["calls"].append(allow_archived)
        return copy.deepcopy(holder["spools"])
    monkeypatch.setattr(spoolman_api, "get_all_spools_strict", _read)
    return holder


def _ids(rows):
    return [r["filament_id"] for r in rows]


# --- the rules ------------------------------------------------------------------

def test_two_spools_adding_up_under_the_threshold_are_low(cfg, spoolman):
    """80 g + 140 g = 220 g is low at 250."""
    f = _fil(10)
    spoolman["spools"] = [_spool(1, f, 80), _spool(2, f, 140)]
    rep = stock_report.build_report()
    assert rep["success"] is True
    assert _ids(rep["low"]) == [10]
    row = rep["low"][0]
    assert row["grams"] == 220.0 and row["spools"] == 2 and row["spools_total"] == 2
    assert row["display"] == "Prusament - PLA - Galaxy Black"
    assert rep["out"] == []
    assert spoolman["calls"] == [True], "one strict read, archived spools included"


def test_at_or_above_the_threshold_is_not_low(cfg, spoolman):
    f, g = _fil(10), _fil(11, name="Jet Black")
    spoolman["spools"] = [_spool(1, f, 250), _spool(2, g, 900), _spool(3, g, 10)]
    rep = stock_report.build_report()
    assert rep["low"] == [] and rep["out"] == []


def test_a_filament_whose_spools_are_all_archived_is_out(cfg, spoolman):
    f = _fil(20, name="Lipstick Red")
    spoolman["spools"] = [_spool(5, f, 0, archived=True), _spool(6, f, 0, archived=True)]
    rep = stock_report.build_report()
    assert rep["low"] == []
    assert _ids(rep["out"]) == [20]
    row = rep["out"][0]
    assert row["grams"] == 0 and row["spools"] == 0 and row["spools_total"] == 2


def test_archived_spools_never_count_as_stock(cfg, spoolman):
    """An archived spool with grams left on record adds nothing: 100 g in stock
    plus an archived 900 g is 100 g, low; an archived spool with grams left and
    nothing else is out."""
    f, g = _fil(30), _fil(31, name="Mint")
    spoolman["spools"] = [_spool(1, f, 100), _spool(2, f, 900, archived=True),
                          _spool(3, g, 700, archived=True)]
    rep = stock_report.build_report()
    assert _ids(rep["low"]) == [30] and rep["low"][0]["grams"] == 100.0
    assert rep["low"][0]["spools"] == 1 and rep["low"][0]["spools_total"] == 2
    assert _ids(rep["out"]) == [31]


def test_an_empty_unarchived_spool_is_not_stock(cfg, spoolman):
    """remaining 0 but not (yet) archived is not in stock either."""
    f = _fil(40)
    spoolman["spools"] = [_spool(1, f, 0)]
    rep = stock_report.build_report()
    assert _ids(rep["out"]) == [40] and rep["low"] == []


def test_a_one_off_filament_is_never_out_but_can_be_low(cfg, spoolman):
    """A "One-off" filament stays off "out" (any case, with or without the dash);
    while it has stock it can be low, with its tag shown."""
    used_up = _fil(50, name="Sparkle", attrs=["Silk", "One-off"])
    used_up2 = _fil(51, name="Glow", attrs=["one off"])
    low_one = _fil(52, name="Tiny", attrs=["ONEOFF"])
    spoolman["spools"] = [_spool(1, used_up, 0, archived=True), _spool(2, used_up2, 0, archived=True),
                          _spool(3, low_one, 90)]
    rep = stock_report.build_report()
    assert rep["out"] == []
    assert _ids(rep["low"]) == [52]
    assert rep["low"][0]["one_off"] is True
    assert rep["low"][0]["attributes"] == ["ONEOFF"]


def test_a_filament_with_no_spools_is_never_listed(cfg, spoolman):
    """Only filaments with spools on record are seen at all (the spool list is
    the only read), so a filament that was never stocked can't be "out"."""
    f = _fil(60)
    spoolman["spools"] = [_spool(1, f, 800)]
    rep = stock_report.build_report()
    assert rep["low"] == [] and rep["out"] == []
    assert rep["filaments"] == 1


def test_a_spool_of_unknown_weight_keeps_its_filament_off_both_lists(cfg, spoolman):
    """A spool whose remaining Spoolman can't compute (no weight on it or its
    filament) can't be called empty: its filament is not out, and not judged low."""
    f = _fil(70, weight=None)
    s = {"id": 1, "filament": f, "initial_weight": None, "used_weight": 12,
         "archived": False, "location": "", "extra": {}}
    spoolman["spools"] = [s]
    rep = stock_report.build_report()
    assert rep["low"] == [] and rep["out"] == []


def test_low_runs_from_fewest_grams_and_out_by_name(cfg, spoolman):
    a, b, c = _fil(1, name="Aqua"), _fil(2, name="Blue"), _fil(3, name="Cyan")
    x, y = _fil(4, name="Zinc", vendor="Acme"), _fil(5, name="Amber", vendor="Acme")
    spoolman["spools"] = [_spool(1, a, 200), _spool(2, b, 15), _spool(3, c, 120),
                          _spool(4, x, 0, archived=True), _spool(5, y, 0, archived=True)]
    rep = stock_report.build_report()
    assert _ids(rep["low"]) == [2, 3, 1]
    assert _ids(rep["out"]) == [5, 4]   # "Acme - PLA - Amber" before "Acme - PLA - Zinc"


def test_the_threshold_comes_from_the_setting(cfg, spoolman):
    f = _fil(10)
    spoolman["spools"] = [_spool(1, f, 400)]
    cfg["low_stock_g"] = 500
    rep = stock_report.build_report()
    assert _ids(rep["low"]) == [10] and rep["threshold_g"] == 500.0
    cfg["low_stock_g"] = 0          # 0 = nothing is ever low
    assert stock_report.build_report()["low"] == []


@pytest.mark.parametrize("raw", [None, "abc", -5, float("nan"), float("inf"), [1]])
def test_a_missing_or_broken_threshold_falls_back_to_250(monkeypatch, raw):
    monkeypatch.setattr(config_loader, "load_config", lambda: {"low_stock_g": raw})
    assert stock_report.low_stock_g() == 250.0
    monkeypatch.setattr(config_loader, "load_config", lambda: {})
    assert stock_report.low_stock_g() == 250.0


def test_the_setting_is_a_behaviour_field_defaulting_to_250():
    f = config_schema.get_field("low_stock_g")
    assert f is not None
    assert f.default == 250 and f.type == "float"
    assert f.section == "behavior" and f.scope == "server"
    assert "per filament" in f.help.lower()
    assert "low_stock_g" in config_schema.SERVER_KEYS
    assert config_schema.coerce_and_validate("low_stock_g", "300") == 300.0
    with pytest.raises(config_schema.ConfigValidationError):
        config_schema.coerce_and_validate("low_stock_g", -1)
    ui = {x["key"]: x for x in config_schema.schema_for_ui()["fields"]}
    assert ui["low_stock_g"]["section"] == "behavior"


# --- the rows -------------------------------------------------------------------

def test_a_row_carries_the_swatch_colour_and_names_like_the_cards(cfg, spoolman):
    multi = _fil(80, name="galaxy dust", color_hex="111111",
                 multi_color_hexes="05AADD,A88FE0", multi_color_direction="coaxial")
    spoolman["spools"] = [_spool(1, multi, 50)]
    row = stock_report.build_report()["low"][0]
    assert row["color"] == "05AADD,A88FE0" and row["color_direction"] == "coaxial"
    assert (row["brand"], row["material"], row["color_name"]) == ("Prusament", "PLA", "Galaxy Dust")
    plain = _fil(81, name="Red", material="petg", vendor=None)
    plain["vendor"] = None
    spoolman["spools"] = [_spool(2, plain, 50)]
    row = stock_report.build_report()["low"][0]
    assert row["color"] == "222222" and row["color_direction"] == "longitudinal"
    assert row["display"] == "Generic - PETG - Red"


def test_buy_more_uses_the_filaments_own_purchase_link_first(cfg, spoolman):
    cfg["buy_more_url_template"] = "https://shop.example/s?q={{vendor}}+{{material}}+{{color}}"
    f = _fil(90, extra={"purchase_url": "https://www.amazon.com/dp/B0F6MPJS11?th=1"})
    spoolman["spools"] = [_spool(1, f, 10)]
    assert stock_report.build_report()["low"][0]["buy_url"] == "https://www.amazon.com/dp/B0F6MPJS11?th=1"


def test_buy_more_falls_back_to_the_template_encoded_like_the_details_windows(cfg, spoolman):
    """{{vendor}} / {{material}} / {{color}} are filled in encodeURIComponent-style
    (the details windows' rule); a purchase_url that isn't a web link doesn't count."""
    cfg["buy_more_url_template"] = "https://shop.example/s?q={{vendor}}+{{material}}+{{color}}"
    f = _fil(91, name="Galaxy Black & Gold", vendor="Hello World's",
             extra={"purchase_url": "ask Bob"})
    spoolman["spools"] = [_spool(1, f, 10)]
    url = stock_report.build_report()["low"][0]["buy_url"]
    assert url == "https://shop.example/s?q=Hello%20World's+PLA+Galaxy%20Black%20%26%20Gold"


def test_no_buy_more_link_when_nothing_resolves(cfg, spoolman):
    f = _fil(92)
    spoolman["spools"] = [_spool(1, f, 10)]
    assert stock_report.build_report()["low"][0]["buy_url"] is None
    # Never anything but an http(s) link, whatever the template or the record holds.
    cfg["buy_more_url_template"] = "javascript:alert({{vendor}})"
    g = _fil(93, extra={"purchase_url": "javascript:alert(1)"})
    spoolman["spools"] = [_spool(2, g, 10)]
    assert stock_report.build_report()["low"][0]["buy_url"] is None


# --- a failed read is an error, never an empty list ------------------------------

def test_a_failed_strict_read_raises_not_an_empty_list(cfg, monkeypatch):
    def _boom(allow_archived=False):
        raise requests.exceptions.ConnectionError("Spoolman is down")
    monkeypatch.setattr(spoolman_api, "get_all_spools_strict", _boom)
    with pytest.raises(stock_report.StockReadError):
        stock_report.build_report()


def test_an_answer_that_isnt_a_spool_list_is_a_failed_read(cfg, monkeypatch):
    monkeypatch.setattr(spoolman_api, "get_all_spools_strict", lambda allow_archived=False: {"detail": "x"})
    with pytest.raises(stock_report.StockReadError):
        stock_report.build_report()


def test_the_real_strict_read_is_asked_for_archived_spools_and_fails_closed(cfg, monkeypatch):
    """Through the real spoolman_api.get_all_spools_strict: the request asks for
    archived spools, the wire-form extras are decoded (a One-off tag on the
    wire is seen), and an HTTP 500 is a failed read, not [] (which the fail-open
    get_all_spools would answer)."""
    f = _fil(95, attrs=None, extra={"filament_attributes": '["One-off"]', "original_color": '"Blue"'})
    wire = [_spool(1, f, 0, archived=True), _spool(2, _fil(96), 40)]
    seen = []

    def _get(url, timeout=None, **kw):
        seen.append(url)
        r = MagicMock()
        r.ok, r.status_code = True, 200
        r.json.return_value = json.loads(json.dumps(wire))
        r.raise_for_status.return_value = None
        return r
    monkeypatch.setattr(spoolman_api.requests, "get", _get)
    rep = stock_report.build_report()
    assert seen and seen[0].endswith("/api/v1/spool?allow_archived=true")
    assert rep["out"] == [] and _ids(rep["low"]) == [96]

    def _get500(url, timeout=None, **kw):
        r = MagicMock()
        r.ok, r.status_code = False, 500
        r.raise_for_status.side_effect = requests.exceptions.HTTPError("500 Server Error")
        return r
    monkeypatch.setattr(spoolman_api.requests, "get", _get500)
    with pytest.raises(stock_report.StockReadError):
        stock_report.build_report()


# --- the route ----------------------------------------------------------------------

@pytest.fixture
def client():
    app_module.app.config["TESTING"] = True
    with app_module.app.test_client() as c:
        yield c


def test_route_answers_the_report(client, cfg, spoolman):
    f, g = _fil(10), _fil(11, name="Mint")
    spoolman["spools"] = [_spool(1, f, 80), _spool(2, f, 140), _spool(3, g, 0, archived=True)]
    r = client.get("/api/stock_report")
    assert r.status_code == 200
    body = r.get_json()
    assert body["success"] is True and body["threshold_g"] == 250.0
    assert _ids(body["low"]) == [10] and _ids(body["out"]) == [11]


def test_route_answers_an_error_when_spoolman_doesnt_answer(client, cfg, monkeypatch):
    """Never `success: true` with empty lists: the page must not show "Nothing is
    low" (or everything out) when it simply couldn't ask."""
    def _boom(allow_archived=False):
        raise requests.exceptions.ReadTimeout("read timed out")
    monkeypatch.setattr(spoolman_api, "get_all_spools_strict", _boom)
    r = client.get("/api/stock_report")
    assert r.status_code == 502
    body = r.get_json()
    assert body["success"] is False
    assert "low" not in body and "out" not in body
    assert "Spoolman didn't answer" in body["msg"]


def test_route_answers_an_error_on_any_other_failure(client, cfg, monkeypatch):
    def _bug():
        raise KeyError("boom")
    monkeypatch.setattr(stock_report, "build_report", _bug)
    r = client.get("/api/stock_report")
    assert r.status_code == 500
    body = r.get_json()
    assert body["success"] is False and "low" not in body
