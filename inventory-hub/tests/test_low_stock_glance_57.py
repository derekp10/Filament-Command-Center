"""Group 57 (Low Stock at a Glance), the backend half. Hermetic: Spoolman's HTTP
API is faked at `requests.get` (every reader resolves it through the shared
`requests` module, `spoolman_api.requests` and `stock_report.requests` alike),
and config, locations.json, the printer map and the PrusaLink probe are patched,
so nothing reaches dev.

  57.2  the ⚠️ Low stock title-bar count rides the heartbeat (`low_stock`): it
        is the list's own Low + Out (stock_report._members, shared with
        build_report), worked out from the tick's NON-archived spool list (an
        archived spool is never in stock, so it never decides Low or Out:
        checked here on every kind of filament and on random inventories), and
        it reads nothing of its own: the tick's one spool-list read, and one
        filament-list read shared with label_backlog. A failed read answers
        read_ok: false, never a count of 0.
  57.4  the Buy More link template reaches the page as a JS string with its
        `&` intact (it arrived as `&amp;`), and nothing in it can end the script.
  57.5  the buffer cards' live refresh answers every spool the tick's list
        holds from that list: one GET only for a spool it lacks (an archived
        one), one per spool only when the list read failed or the tick read no
        list. /api/spools/refresh keeps one GET per spool.

New symbols are looked up inside the tests, so the file imports on the base and
each test fails there for its own reason.
"""
from __future__ import annotations

import copy
import json
import os
import random
import re
import sys
from contextlib import ExitStack
from unittest.mock import patch
from urllib.parse import urlsplit

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import app as app_module  # noqa: E402
import config_loader  # noqa: E402
import locations_db  # noqa: E402
import logic  # noqa: E402
import prusalink_api  # noqa: E402
import spoolman_api  # noqa: E402
import stock_report  # noqa: E402

SPOOL_LIST = "/api/v1/spool"
FILAMENT_LIST = "/api/v1/filament"
THRESHOLD = 250.0

ROWS = [
    {"LocationID": "TST", "Name": "Test Room", "Type": "Room", "Max Spools": "0"},
    {"LocationID": "TST-DB-1", "Name": "Test box", "Type": "Dryer Box", "Max Spools": "4", "parent_id": "TST"},
    {"LocationID": "TSTP", "Name": "Test Printer", "Type": "Printer", "Max Spools": "0",
     "toolheads": [{"location_id": "TSTP-1", "position": 0}]},
    {"LocationID": "TSTP-1", "Name": "Head 1", "Type": "Tool Head", "Max Spools": "1", "parent_id": "TSTP"},
]
PRINTER_MAP = {"TSTP-1": {"printer_name": "Test Printer", "position": 0}}


# --- a small inventory, one filament of every kind ----------------------------------

def _filament(fid, name, excluded=None, weight=1000.0, label=False):
    extra = {}
    if excluded:
        extra["fcc_stock_excluded"] = json.dumps(excluded)
    if label:
        extra["needs_label_print"] = "true"
    fil = {"id": fid, "name": name, "material": "PLA", "color_hex": "336699",
           "vendor": {"id": 1, "name": "FCC Test"}, "extra": extra}
    if weight is not None:
        fil["weight"] = weight
    return fil


def _spool(sid, fil, remaining=None, archived=False, initial=None, used=0.0, location="TST-DB-1", extra=None):
    """A spool as Spoolman sends it. remaining=None leaves Spoolman's
    remaining_weight out (it is computed from initial / used, or unknown)."""
    s = {"id": sid, "filament": copy.deepcopy(fil), "archived": archived, "location": location,
         "used_weight": used, "extra": dict(extra or {})}
    if remaining is not None:
        s["remaining_weight"] = remaining
    if initial is not None:
        s["initial_weight"] = initial
    return s


F_LOW = _filament(1, "Low One")
F_PLENTY = _filament(2, "Plenty")
F_ARCHIVED_ONLY = _filament(3, "Archived Only")          # spools all archived: Out
F_NO_SPOOLS = _filament(4, "Never Stocked")              # no spool at all: Out
F_EMPTY = _filament(5, "Used Up")                        # a non-archived spool at 0 g: Out
F_UNKNOWN = _filament(6, "Unknown Weight", weight=None)  # a spool of unknown weight: never Low
F_EXCLUDED_LOW = _filament(7, "Excluded Low", excluded="Discontinued")
F_EXCLUDED_ARCHIVED = _filament(8, "Excluded Archived", excluded="One-off")
F_EXCLUDED_NONE = _filament(9, "Excluded Never", excluded="Didn't like it")
F_MIXED = _filament(10, "Archived Plus Low")             # an archived full spool + a low one: Low
F_LABEL = _filament(11, "Needs A Label", label=True)     # plenty; flagged for the backlog

FILAMENTS = [F_LOW, F_PLENTY, F_ARCHIVED_ONLY, F_NO_SPOOLS, F_EMPTY, F_UNKNOWN, F_EXCLUDED_LOW,
             F_EXCLUDED_ARCHIVED, F_EXCLUDED_NONE, F_MIXED, F_LABEL]

SPOOLS = [
    _spool(101, F_LOW, remaining=120.0),
    _spool(102, F_PLENTY, remaining=900.0),
    _spool(103, F_ARCHIVED_ONLY, remaining=600.0, archived=True),
    _spool(104, F_ARCHIVED_ONLY, remaining=0.0, archived=True),
    _spool(105, F_EMPTY, remaining=0.0),
    _spool(106, F_UNKNOWN),                                       # no weight anywhere
    _spool(107, F_UNKNOWN, remaining=10.0),
    _spool(108, F_EXCLUDED_LOW, remaining=50.0),
    _spool(109, F_EXCLUDED_ARCHIVED, remaining=300.0, archived=True),
    _spool(110, F_MIXED, remaining=800.0, archived=True),
    _spool(111, F_MIXED, remaining=90.0, location="TSTP-1"),
    _spool(112, F_LABEL, remaining=700.0, extra={"needs_label_print": "true"}),
]


class _Resp:
    def __init__(self, status, body):
        self.status_code = status
        self.ok = status < 400
        self._body = copy.deepcopy(body)
        self.text = json.dumps(body)

    def json(self):
        return copy.deepcopy(self._body)

    def raise_for_status(self):
        if not self.ok:
            raise spoolman_api.requests.exceptions.HTTPError(f"{self.status_code} (test)")


class HttpSpoolman:
    """Spoolman's HTTP API at `requests.get`: the spool list (archived spools
    only with allow_archived=true), the filament list and single spools.
    `down` holds the paths that time out. Every GET is recorded by path."""

    def __init__(self, spools=SPOOLS, filaments=FILAMENTS, down=()):
        self.spools = copy.deepcopy(list(spools))
        self.filaments = copy.deepcopy(list(filaments))
        self.down = set(down)
        self.gets = []

    def get(self, url, *a, **k):
        parts = urlsplit(str(url))
        path = parts.path
        self.gets.append(path)
        if path in self.down:
            raise spoolman_api.requests.exceptions.ReadTimeout("Read timed out. (read timeout=5) (test)")
        if path == SPOOL_LIST:
            archived_too = "allow_archived=true" in parts.query
            return _Resp(200, [s for s in self.spools if archived_too or not s.get("archived")])
        if path == FILAMENT_LIST:
            return _Resp(200, self.filaments)
        if path == "/api/v1/location":
            return _Resp(200, [])
        m = re.fullmatch(r"/api/v1/spool/(\d+)", path)
        if m:
            rec = next((s for s in self.spools if s["id"] == int(m.group(1))), None)
            return _Resp(200, rec) if rec else _Resp(404, {"message": "not found"})
        return _Resp(404, {"message": "not found"})

    def count(self, path):
        return self.gets.count(path)

    def single_gets(self):
        return [p for p in self.gets if re.fullmatch(r"/api/v1/spool/\d+", p)]


def _run(sm, call, config=None):
    cfg = {"low_stock_g": THRESHOLD} if config is None else config
    with ExitStack() as stack:
        for p in (
            patch.object(spoolman_api.requests, "get", side_effect=sm.get),
            patch.object(locations_db, "load_locations_list", side_effect=lambda *a, **k: copy.deepcopy(ROWS)),
            patch.object(locations_db, "get_active_printer_map", return_value=copy.deepcopy(PRINTER_MAP)),
            patch.object(config_loader, "get_api_urls", return_value=("http://sm", "http://fb")),
            patch.object(config_loader, "load_config", return_value=copy.deepcopy(cfg)),
            patch.object(prusalink_api, "get_printer_state", return_value=None),
        ):
            stack.enter_context(p)
        return call()


@pytest.fixture
def client():
    app_module.app.config["TESTING"] = True
    return app_module.app.test_client()


def _pulse(client, sm, include, body=None, config=None):
    url = f"/api/dashboard_pulse?include={include}"
    if body is None:
        r = _run(sm, lambda: client.get(url), config=config)
    else:
        r = _run(sm, lambda: client.post(url, json=body), config=config)
    assert r.status_code == 200
    return r.get_json()


def _report(sm, config=None):
    return _run(sm, stock_report.build_report, config=config)


def _names(rows):
    return sorted(r["display"].split(" - ")[-1] for r in rows)


# ---------------------------------------------------------------------------
# 57.2: the count is the list's Low + Out
# ---------------------------------------------------------------------------

def test_the_count_is_the_lists_low_and_out_on_every_kind_of_filament():
    """The list (every spool, archived ones too) and the count from the
    heartbeat's NON-archived list agree on each kind: an archived-only
    filament and one with no spool at all are Out either way, a spool of
    unknown weight keeps its filament off Low, excluded ones never count."""
    sm = HttpSpoolman()
    report = _report(sm)
    assert _names(report["low"]) == ["Archived Plus Low", "Low One"], report["low"]
    assert _names(report["out"]) == ["Archived Only", "Never Stocked", "Used Up"], report["out"]
    assert _names(report["excluded"]) == ["Excluded Archived", "Excluded Low", "Excluded Never"]

    in_stock_list = [s for s in sm.spools if not s.get("archived")]
    parsed = spoolman_api.parse_inbound_data(copy.deepcopy(in_stock_list))
    fils = spoolman_api.parse_inbound_data(copy.deepcopy(sm.filaments))
    assert stock_report.low_out_count(parsed, fils, THRESHOLD) == (2, 3)
    # Every spool, archived ones too, gives the same count.
    every = spoolman_api.parse_inbound_data(copy.deepcopy(sm.spools))
    assert stock_report.low_out_count(every, fils, THRESHOLD) == (2, 3)


@pytest.mark.parametrize("seed", [1, 2, 3, 57, 2026])
def test_the_count_matches_the_list_on_random_inventories(seed):
    """Random inventories mixing every kind of spool (archived with grams and
    empty, low, plenty, empty, unknown weight, over-used) and exclusions: the
    count from the non-archived list always equals the list's Low and Out."""
    rng = random.Random(seed)
    kinds = [
        dict(remaining=500.0, archived=True), dict(remaining=0.0, archived=True),
        dict(remaining=40.0), dict(remaining=180.0), dict(remaining=900.0), dict(remaining=0.0),
        dict(), dict(remaining=-5.0), dict(initial=1000.0, used=990.0), dict(initial=1000.0, used=100.0),
    ]
    filaments, spools, sid = [], [], 1000
    for fid in range(1, 151):
        excluded = rng.choice([None] * 4 + ["Discontinued"])
        fil = _filament(fid, f"Random {fid}", excluded=excluded, weight=rng.choice([1000.0, None]))
        filaments.append(fil)
        for _ in range(rng.choice([0, 0, 1, 1, 2, 3, 4])):
            sid += 1
            spools.append(_spool(sid, fil, **rng.choice(kinds)))
    sm = HttpSpoolman(spools=spools, filaments=filaments)
    report = _report(sm)
    in_stock_list = spoolman_api.parse_inbound_data([s for s in copy.deepcopy(spools) if not s.get("archived")])
    fils = spoolman_api.parse_inbound_data(copy.deepcopy(filaments))
    assert stock_report.low_out_count(in_stock_list, fils, THRESHOLD) == (len(report["low"]), len(report["out"]))
    assert report["low"] and report["out"], "the inventory should exercise both lists"


def test_the_list_itself_is_unchanged_by_the_shared_rule():
    """build_report still answers every row as it did: the no-spool rows last
    on Out with no_spools, the excluded ones with their stock and its floor."""
    sm = HttpSpoolman()
    report = _report(sm)
    out = report["out"]
    assert [r["display"].split(" - ")[-1] for r in out] == ["Archived Only", "Used Up", "Never Stocked"]
    assert [bool(r.get("no_spools")) for r in out] == [False, False, True]
    assert out[0]["spools"] == 0 and out[0]["spools_total"] == 2
    low = report["low"]
    assert [(r["display"].split(" - ")[-1], r["grams"], r["spools"], r["spools_total"]) for r in low] == [
        ("Archived Plus Low", 90.0, 1, 2), ("Low One", 120.0, 1, 1)]
    ex = {r["display"].split(" - ")[-1]: r for r in report["excluded"]}
    assert ex["Excluded Low"]["grams"] == 50.0 and ex["Excluded Low"]["stock_unknown"] is False
    assert ex["Excluded Never"].get("no_spools") is True and "stock_unknown" not in ex["Excluded Never"]
    assert report["filaments"] == len(FILAMENTS) and report["spools"] == len(SPOOLS)


# ---------------------------------------------------------------------------
# 57.2: the heartbeat's low_stock section
# ---------------------------------------------------------------------------

def test_the_heartbeat_counts_low_stock_with_no_read_of_its_own(client):
    """With the backlog count in the tick too (the dashboard always asks for
    both), the count costs nothing: one spool-list read and one filament-list
    read serve every section. RED before 57.2: no low_stock section."""
    sm = HttpSpoolman()
    body = _pulse(client, sm, "locations,printer_status,label_backlog,low_stock")
    assert sm.count(SPOOL_LIST) == 1, sm.gets
    assert sm.count(FILAMENT_LIST) == 1, sm.gets
    assert body["low_stock"] == {"read_ok": True, "count": 5, "low": 2, "out": 3, "threshold_g": THRESHOLD}, body
    assert body["label_backlog"] == {"read_ok": True, "count": 2, "spools": 1, "filaments": 1}, body
    assert body["spool_read"] == {"ok": True, "error": None}


def test_low_stock_alone_reads_each_list_once(client):
    sm = HttpSpoolman()
    body = _pulse(client, sm, "low_stock")
    assert (sm.count(SPOOL_LIST), sm.count(FILAMENT_LIST)) == (1, 1), sm.gets
    assert body["low_stock"]["count"] == 5


def test_the_count_is_never_the_list_itself(client):
    """The heartbeat counts from the non-archived list: it never reads the
    list the window reads (every spool, archived ones too)."""
    sm = HttpSpoolman()
    seen = []
    real = sm.get

    def get(url, *a, **k):
        seen.append(str(url))
        return real(url, *a, **k)
    sm.get = get
    _pulse(client, sm, "printer_status,label_backlog,low_stock")
    assert not any("allow_archived=true" in u for u in seen), seen


def test_a_failed_spool_read_is_no_count_and_no_filament_read(client):
    """Spoolman times out: the count says it couldn't read (the page keeps the
    one it shows), never 0, and the filament list isn't asked for."""
    sm = HttpSpoolman(down={SPOOL_LIST})
    body = _pulse(client, sm, "printer_status,label_backlog,low_stock")
    assert body["low_stock"]["read_ok"] is False and "count" not in body["low_stock"], body
    assert "Spoolman" in body["low_stock"]["read_error"], body
    assert sm.count(SPOOL_LIST) == 1 and sm.count(FILAMENT_LIST) == 0, sm.gets
    assert body["spool_read"]["ok"] is False


def test_a_failed_filament_read_is_tried_once_for_both_counts(client):
    sm = HttpSpoolman(down={FILAMENT_LIST})
    body = _pulse(client, sm, "label_backlog,low_stock")
    assert sm.count(FILAMENT_LIST) == 1, sm.gets
    for key in ("label_backlog", "low_stock"):
        assert body[key]["read_ok"] is False and "count" not in body[key], body
        assert "filaments" in body[key]["read_error"], body


def test_low_stock_is_a_sibling_key_never_a_printer(client):
    """The widget and _notePrinterStatesForFastPoll read every printer_status
    key as a printer's name."""
    sm = HttpSpoolman()
    body = _pulse(client, sm, "printer_status,low_stock")
    assert "low_stock" in body and "low_stock" not in body["printer_status"], body
    assert set(body["printer_status"]) == {"Test Printer"}


def test_an_older_page_gets_no_low_stock_and_no_extra_read(client):
    """A page from before 57.2 never asks for it: its tick reads what it did."""
    sm = HttpSpoolman()
    body = _pulse(client, sm, "locations,printer_status,label_backlog")
    assert "low_stock" not in body
    assert (sm.count(SPOOL_LIST), sm.count(FILAMENT_LIST)) == (1, 1), sm.gets


def test_the_setting_moves_the_line(client):
    """low_stock_g (⚙️ Behavior) is the list's line: at 1000 g every filament
    with stock but none of unknown weight is Low."""
    sm = HttpSpoolman()
    body = _pulse(client, sm, "low_stock", config={"low_stock_g": 1000})
    assert body["low_stock"]["low"] == 4 and body["low_stock"]["threshold_g"] == 1000.0, body
    report = _report(HttpSpoolman(), config={"low_stock_g": 1000})
    assert body["low_stock"]["low"] == len(report["low"]) and body["low_stock"]["out"] == len(report["out"])


def test_a_count_that_raises_keeps_the_others(client):
    sm = HttpSpoolman()
    with patch.object(stock_report, "low_out_count", side_effect=RuntimeError("boom")):
        body = _pulse(client, sm, "label_backlog,low_stock")
    assert body["low_stock"] == {"error": "boom", "read_ok": False}, body
    assert body["label_backlog"]["read_ok"] is True


# ---------------------------------------------------------------------------
# 57.5: the buffer cards' live refresh
# ---------------------------------------------------------------------------

def _old_answer(ids, spools=SPOOLS):
    """What the refresh answered before 57.5 (one GET per id), on the same data."""
    sm = HttpSpoolman(spools=spools)
    return _run(sm, lambda: logic.get_live_spools_data(ids))


def test_the_buffer_refresh_reads_no_spool_the_tick_already_has(client):
    """Ten buffered spools were ten GETs on every tick. Now the tick's list
    answers them: no single-spool GET, and the same answer as before. RED
    before 57.5: one GET per id."""
    ids = [101, 102, 105, 111, 112]
    sm = HttpSpoolman()
    body = _pulse(client, sm, "printer_status,label_backlog,low_stock", body={"refresh_spool_ids": ids})
    assert sm.single_gets() == [], sm.gets
    assert sm.count(SPOOL_LIST) == 1, sm.gets
    assert body["spools_refresh"] == _old_answer(ids)
    assert body["spools_refresh"]["111"]["location"] == "TSTP-1"


def test_an_archived_buffered_spool_is_read_on_its_own(client):
    """The tick's list is the non-archived one: an archived spool in the buffer
    costs its own GET, as before, and is answered as archived."""
    ids = [101, 110]
    sm = HttpSpoolman()
    body = _pulse(client, sm, "printer_status", body={"refresh_spool_ids": ids})
    assert sm.single_gets() == ["/api/v1/spool/110"], sm.gets
    assert body["spools_refresh"] == _old_answer(ids)
    assert body["spools_refresh"]["110"]["archived"] is True


def test_a_failed_list_read_falls_back_to_one_read_per_spool(client):
    ids = [101, 102]
    sm = HttpSpoolman(down={SPOOL_LIST})
    body = _pulse(client, sm, "printer_status", body={"refresh_spool_ids": ids})
    assert sm.single_gets() == ["/api/v1/spool/101", "/api/v1/spool/102"], sm.gets
    assert body["spools_refresh"] == _old_answer(ids)


def test_a_tick_that_read_no_list_starts_no_list_read_for_the_buffer(client):
    """No section read the list (an include with none of them): the buffer
    keeps one GET per spool rather than read the whole list for itself."""
    ids = [101]
    sm = HttpSpoolman()
    body = _pulse(client, sm, "buffer", body={"refresh_spool_ids": ids})
    assert sm.count(SPOOL_LIST) == 0 and sm.single_gets() == ["/api/v1/spool/101"], sm.gets
    assert body["spools_refresh"] == _old_answer(ids)
    assert "spool_read" not in body


def test_a_spool_that_is_gone_is_answered_as_before(client):
    """An id neither the list nor Spoolman knows: the same answer as before
    (whatever the old path made of Spoolman's 404 body), from one GET."""
    ids = [999]
    sm = HttpSpoolman()
    body = _pulse(client, sm, "printer_status", body={"refresh_spool_ids": ids})
    assert sm.single_gets() == ["/api/v1/spool/999"], sm.gets
    assert body["spools_refresh"] == _old_answer(ids)


def test_the_refresh_route_keeps_one_read_per_spool(client):
    """/api/spools/refresh (a local "something moved" signal, no tick) is
    unchanged: one GET per id, no list read."""
    ids = [101, 102]
    sm = HttpSpoolman()
    r = _run(sm, lambda: client.post("/api/spools/refresh", json={"spools": ids}))
    assert r.status_code == 200
    assert sm.count(SPOOL_LIST) == 0 and sm.single_gets() == ["/api/v1/spool/101", "/api/v1/spool/102"]
    assert r.get_json() == _old_answer(ids)


# ---------------------------------------------------------------------------
# 57.4: the Buy More link template
# ---------------------------------------------------------------------------

def _rendered_template(client, value, set_key=True):
    cfg = {"buy_more_url_template": value} if set_key else {}
    with patch.object(config_loader, "load_config", return_value=cfg):
        html = client.get("/").get_data(as_text=True)
    m = re.search(r"const BUY_MORE_URL_TEMPLATE = (.*?);\s*$", html, re.M)
    assert m, "dashboard.html no longer sets BUY_MORE_URL_TEMPLATE"
    return html, m.group(1)


def test_a_buy_more_template_keeps_its_ampersands(client):
    """It arrived as &amp; inside quotes, so the spool and filament windows'
    Buy More links carried &amp;color=… RED before 57.4."""
    template = "https://shop.example/s?q={{vendor}}+{{material}}&color={{color}}&ref=fcc"
    html, literal = _rendered_template(client, template)
    assert json.loads(literal) == template          # a JSON string is the JS string the page runs
    assert "&amp;" not in literal


def test_nothing_in_a_template_can_end_the_script(client):
    template = 'https://x.example/?a=1&b=2</script><script>alert("x")</script>'
    html, literal = _rendered_template(client, template)
    assert json.loads(literal) == template
    assert "</script><script>alert" not in html
    assert "<" not in literal and ">" not in literal


@pytest.mark.parametrize("value,expected", [("", ""), (None, None)])
def test_no_template_is_still_no_link(client, value, expected):
    """An empty or null setting stays falsy, so the windows show no Buy More
    (a null used to arrive as the text "None")."""
    _, literal = _rendered_template(client, value)
    assert json.loads(literal) == expected


def test_a_missing_setting_is_an_empty_string(client):
    _, literal = _rendered_template(client, None, set_key=False)
    assert json.loads(literal) == ""
