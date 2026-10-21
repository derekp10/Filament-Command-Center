"""Group 49.2a: the ⚠️ Low-stock list (stock_report.build_report, GET /api/stock_report)
and its `low_stock_g` setting.

Stock is counted per FILAMENT across its in-stock spools (not archived, grams
left). Low = under `low_stock_g` (default 250 g). Out = none in stock, a filament
with no spool on record at all included (after the others, `no_spools`; Derek,
2026-10-20). A filament marked "not buying again" is neither: it is listed under
`not_rebuying` with its reason and stock (Derek, 2026-10-20; the mark and its
route are pinned by test_not_buying_again.py). The list reads Spoolman's spools
and filaments, strictly: a failed read answers an error, never an empty or "all
out" list.

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
    """The strict all-spools read, answering whatever the test puts in it, and the
    strict all-filaments read: `filaments` when a test sets it, else the
    filaments the spools carry (so no filament is without a spool)."""
    holder = {"spools": [], "calls": [], "filaments": None}

    def _read(allow_archived=False):
        holder["calls"].append(allow_archived)
        return copy.deepcopy(holder["spools"])

    def _filaments():
        if holder["filaments"] is not None:
            return copy.deepcopy(holder["filaments"])
        seen = {}
        for sp in holder["spools"]:
            seen.setdefault(sp["filament"]["id"], copy.deepcopy(sp["filament"]))
        return list(seen.values())
    monkeypatch.setattr(spoolman_api, "get_all_spools_strict", _read)
    monkeypatch.setattr(stock_report, "_all_filaments_strict", _filaments)
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


def _not_rebuying(reason="Discontinued", note=None, at="2026-10-20"):
    """The three "not buying again" extras, decoded (as the strict read gives them)."""
    ex = {"fcc_no_rebuy": reason, "fcc_no_rebuy_at": at}
    if note is not None:
        ex["fcc_no_rebuy_note"] = note
    return ex


def test_a_filament_not_bought_again_is_never_low_or_out_and_is_listed_with_why(cfg, spoolman):
    """Derek, 2026-10-20: marked from the list, with a reason. Low stock, used up
    or never stocked, it leaves Low and Out and is listed under `not_rebuying`
    (by name) with its stock, reason, note and day. RED on 68a9b9d (no such
    list: they stayed on Low and Out)."""
    low_one = _fil(50, name="Tiny", extra=_not_rebuying("One-off", note="A gift"))
    used_up = _fil(51, name="Sparkle", extra=_not_rebuying("Discontinued", note='Prusa said "no more"'))
    never = _fil(52, name="Aqua", extra=_not_rebuying("Didn't like it", at="2026-01-02"))
    plain_low, plain_out = _fil(53, name="Mint"), _fil(54, name="Zinc")
    spoolman["spools"] = [_spool(1, low_one, 90), _spool(2, low_one, 0, archived=True),
                          _spool(3, used_up, 0, archived=True),
                          _spool(4, plain_low, 100), _spool(5, plain_out, 0, archived=True)]
    spoolman["filaments"] = [low_one, used_up, never, plain_low, plain_out]
    rep = stock_report.build_report()
    assert _ids(rep["low"]) == [53] and _ids(rep["out"]) == [54]
    assert _ids(rep["not_rebuying"]) == [52, 51, 50]          # Aqua, Sparkle, Tiny
    aqua, sparkle, tiny = rep["not_rebuying"]
    assert tiny["not_rebuying"] == {"reason": "One-off", "code": "one_off", "note": "A gift", "at": "2026-10-20"}
    assert (tiny["grams"], tiny["spools"], tiny["spools_total"]) == (90.0, 1, 2)
    assert tiny["stock_unknown"] is False and "no_spools" not in tiny
    assert sparkle["not_rebuying"]["note"] == 'Prusa said "no more"', sparkle   # quotes kept
    assert sparkle["not_rebuying"]["code"] == "discontinued" and sparkle["spools"] == 0
    assert aqua["no_spools"] is True and aqua["not_rebuying"]["code"] == "didnt_like"
    assert aqua["not_rebuying"]["at"] == "2026-01-02" and aqua["not_rebuying"]["note"] == ""
    # Every row says whether it is marked.
    assert rep["low"][0]["not_rebuying"] is None and rep["out"][0]["not_rebuying"] is None
    assert rep["filaments"] == 5


def test_a_reason_typed_in_spoolman_by_hand_counts(cfg, spoolman):
    """Any reason that isn't blank marks it; one matching a label (any case or
    punctuation) gets its code, any other reads as "other". A blank one doesn't
    mark anything."""
    a = _fil(60, name="A", extra=_not_rebuying("too brittle"))
    b = _fil(61, name="B", extra=_not_rebuying("didnt like it"))
    c = _fil(62, name="C", extra=_not_rebuying("ONE OFF"))
    blank = _fil(63, name="D", extra=_not_rebuying("   "))
    spoolman["spools"] = [_spool(1, a, 10), _spool(2, b, 10), _spool(3, c, 10), _spool(4, blank, 10)]
    rep = stock_report.build_report()
    assert _ids(rep["low"]) == [63]
    codes = {r["filament_id"]: (r["not_rebuying"]["reason"], r["not_rebuying"]["code"]) for r in rep["not_rebuying"]}
    assert codes == {60: ("too brittle", "other"), 61: ("didnt like it", "didnt_like"), 62: ("ONE OFF", "one_off")}


def test_the_one_off_attribute_no_longer_hides_a_filament(cfg, spoolman):
    """The One-off attribute rule (dev only, never released) is gone: a filament
    tagged One-off is low or out like any other, its tag shown."""
    used_up = _fil(50, name="Sparkle", attrs=["Silk", "One-off"])
    low_one = _fil(52, name="Tiny", attrs=["ONEOFF"])
    spoolman["spools"] = [_spool(1, used_up, 0, archived=True), _spool(3, low_one, 90)]
    rep = stock_report.build_report()
    assert _ids(rep["out"]) == [50] and _ids(rep["low"]) == [52]
    assert rep["low"][0]["attributes"] == ["ONEOFF"] and "one_off" not in rep["low"][0]
    assert rep["not_rebuying"] == []


def test_a_marked_filament_with_a_spool_of_unknown_weight_says_so(cfg, spoolman):
    """Its grams are then a floor (`stock_unknown`); it is listed all the same."""
    f = _fil(70, weight=None, extra=_not_rebuying())
    s = {"id": 1, "filament": f, "initial_weight": None, "used_weight": 12,
         "archived": False, "location": "", "extra": {}}
    spoolman["spools"] = [s, _spool(2, _fil(70, extra=_not_rebuying()), 40)]
    row = stock_report.build_report()["not_rebuying"][0]
    assert row["stock_unknown"] is True and row["spools"] == 2 and row["grams"] == 40.0


def test_a_filament_with_no_spool_on_record_is_out_after_the_others(cfg, spoolman):
    """Derek, 2026-10-20: "please include those, they are technically out" (on
    prod, 11 filaments from the first import never had a spool record). Listed
    after the used-up ones, marked `no_spools`; one marked not buying again
    stays off. RED on 74d780a (never listed)."""
    used_up, stocked = _fil(60, name="Zebra"), _fil(61, name="Mint")
    never_a, never_b = _fil(70, name="Apple"), _fil(71, name="Kiwi")
    never_rebuy = _fil(72, name="Plum", extra=_not_rebuying())
    spoolman["spools"] = [_spool(1, used_up, 0, archived=True), _spool(2, stocked, 800)]
    spoolman["filaments"] = [used_up, stocked, never_a, never_b, never_rebuy]
    rep = stock_report.build_report()
    assert _ids(rep["out"]) == [60, 70, 71], rep["out"]
    assert [r.get("no_spools", False) for r in rep["out"]] == [False, True, True], rep["out"]
    apple = rep["out"][1]
    assert (apple["grams"], apple["spools"], apple["spools_total"]) == (0.0, 0, 0), apple
    assert apple["display"] == "Prusament - PLA - Apple", apple
    assert _ids(rep["not_rebuying"]) == [72] and rep["not_rebuying"][0]["no_spools"] is True
    assert rep["filaments"] == 5


def test_a_failed_filament_read_is_a_failed_read(cfg, spoolman, monkeypatch):
    """The spools read, the filaments didn't: an error, never a list missing them."""
    spoolman["spools"] = [_spool(1, _fil(60), 0, archived=True)]

    def _boom():
        raise requests.exceptions.ReadTimeout("read timed out")
    monkeypatch.setattr(stock_report, "_all_filaments_strict", _boom)
    with pytest.raises(stock_report.StockReadError):
        stock_report.build_report()
    monkeypatch.setattr(stock_report, "_all_filaments_strict", lambda: {"detail": "x"})
    with pytest.raises(stock_report.StockReadError):
        stock_report.build_report()


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
    archived spools, the wire-form extras are decoded (a "not buying again" mark
    on the wire is seen), and an HTTP 500 is a failed read, not [] (which the
    fail-open get_all_spools would answer)."""
    f = _fil(95, attrs=None, extra={"fcc_no_rebuy": '"Discontinued"', "fcc_no_rebuy_note": '"say \\"no\\""',
                                    "original_color": '"Blue"'})
    wire = [_spool(1, f, 0, archived=True), _spool(2, _fil(96), 40)]
    seen = []

    def _get(url, timeout=None, **kw):
        seen.append(url)
        r = MagicMock()
        r.ok, r.status_code = True, 200
        # The filament list (every filament here has a spool), else the spools.
        body = [f, _fil(96)] if url.split("?")[0].endswith("/api/v1/filament") else wire
        r.json.return_value = json.loads(json.dumps(body))
        r.raise_for_status.return_value = None
        return r
    monkeypatch.setattr(spoolman_api.requests, "get", _get)
    rep = stock_report.build_report()
    assert seen and seen[0].endswith("/api/v1/spool?allow_archived=true")
    assert rep["out"] == [] and _ids(rep["low"]) == [96]
    assert _ids(rep["not_rebuying"]) == [95]
    assert rep["not_rebuying"][0]["not_rebuying"]["note"] == 'say "no"'

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
