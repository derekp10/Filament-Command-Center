"""Group 49.2b: ONE Activity Log WARNING when a write takes a filament under the
low-stock line (`low_stock_g`, default 250 g), or out of stock.

  - "⚠️ Prusament PLA Galaxy Black is running low: 220 g left in 2 spools" when a
    print or a weigh-out takes the filament from at or above the line to under it;
  - "⚠️ ... is out: #1 was its last spool in stock" when its last in-stock spool
    empties (the 0 g auto-archive);
  - neither for a filament marked "not buying again" (Derek, 2026-10-20);
  - quiet when the filament was already under the line (220 g -> 150 g).

The hook points are the print deduct's `_record_applied_deduct` (after its
exactly-once ledger write) and the manual weight funnel `_log_manual_weight_change`
(the wizard and /api/spool/update). The check must never raise into, refuse,
reorder or delay either write.

These drive the REAL engine (deduct_completed_print -> _apply_usage_to_printer ->
spoolman_api.update_spool with its auto-archive -> _record_applied_deduct, and the
real /api/spool/update route) against a small fake Spoolman HTTP layer, so the
check reads back exactly what the writes left (CLAUDE.md memory: mocked engines
hid chain bugs). The check runs inline here (`stock_report._RUN_ASYNC = False`);
one test pins that it runs on its own thread in the app. Hermetic: runs under
--offline.
"""
from __future__ import annotations

import copy
import json as _json
import os
import re
import sys
import threading
from urllib.parse import parse_qs, urlsplit

import pytest
import requests

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import app as app_module  # noqa: E402  (registers the routes)
import cancel_fetch_store  # noqa: E402
import cancel_review_store  # noqa: E402
import config_loader  # noqa: E402
import print_deduct  # noqa: E402
import print_deduct_ledger  # noqa: E402
import spoolman_api  # noqa: E402
import state  # noqa: E402
import stock_report  # noqa: E402


# --- a small, faithful Spoolman ------------------------------------------------

class _Resp:
    def __init__(self, status, payload):
        self.status_code = status
        self.ok = 200 <= status < 300
        self._payload = payload
        self.text = _json.dumps(payload)

    def json(self):
        return copy.deepcopy(self._payload)

    def raise_for_status(self):
        if not self.ok:
            raise requests.exceptions.HTTPError(f"{self.status_code} Error")


class FakeSpoolman:
    """GET /api/v1/spool/<id>, GET /api/v1/spool[?filament.id=..&allow_archived=..]
    and PATCH /api/v1/spool/<id>, answering in Spoolman's wire form (text extras
    JSON-encoded) with remaining_weight computed as Spoolman does."""

    def __init__(self, honour_filter=True):
        self.filaments, self.spools, self.calls = {}, {}, []
        self.honour_filter = honour_filter

    def add_filament(self, fid, name="Galaxy Black", vendor="Prusament", attrs=None,
                     color="222222", weight=1000.0):
        extra = {"original_color": _json.dumps(name)}
        if attrs is not None:
            extra["filament_attributes"] = _json.dumps(attrs)
        self.filaments[fid] = {"id": fid, "name": name, "material": "PLA", "color_hex": color,
                               "vendor": {"id": 1, "name": vendor, "extra": {}},
                               "weight": weight, "extra": extra}

    def add_spool(self, sid, fid, remaining, archived=False, location=""):
        cap = self.filaments[fid]["weight"]
        self.spools[sid] = {"id": sid, "fid": fid, "initial_weight": cap,
                            "used_weight": cap - remaining, "archived": archived,
                            "location": location, "extra": {}}

    def record(self, sid):
        s = self.spools[sid]
        rec = {k: copy.deepcopy(v) for k, v in s.items() if k != "fid"}
        rec["filament"] = copy.deepcopy(self.filaments[s["fid"]])
        cap = s["initial_weight"] if s["initial_weight"] is not None else rec["filament"]["weight"]
        rec["remaining_weight"] = cap - s["used_weight"]
        return rec

    def remaining(self, sid):
        return self.record(sid)["remaining_weight"]

    def at(self, loc):
        return [sid for sid, s in sorted(self.spools.items())
                if s["location"] == loc and not s["archived"]]

    def get(self, url, timeout=None, **kw):
        self.calls.append(("GET", url))
        parts = urlsplit(url)
        q = parse_qs(parts.query)
        m = re.fullmatch(r"/api/v1/spool/(\d+)", parts.path)
        if m:
            sid = int(m.group(1))
            if sid not in self.spools:
                return _Resp(404, {"message": f"No spool with ID {sid} found."})
            return _Resp(200, self.record(sid))
        if parts.path == "/api/v1/spool":
            allow = (q.get("allow_archived") or ["false"])[0] == "true"
            fids = None
            if self.honour_filter and "filament.id" in q:
                fids = {int(x) for x in q["filament.id"][0].split(",")}
            return _Resp(200, [self.record(sid) for sid, s in sorted(self.spools.items())
                               if (allow or not s["archived"]) and (fids is None or s["fid"] in fids)])
        return _Resp(404, {"message": "no such route"})

    def patch(self, url, timeout=None, **kw):
        body = kw.get("json") or {}
        self.calls.append(("PATCH", url, copy.deepcopy(body)))
        sid = int(re.fullmatch(r"/api/v1/spool/(\d+)", urlsplit(url).path).group(1))
        s = self.spools[sid]
        for k in ("used_weight", "initial_weight", "archived", "location"):
            if k in body:
                s[k] = body[k]
        if isinstance(body.get("extra"), dict):
            s["extra"] = dict(body["extra"])
        return _Resp(200, self.record(sid))


@pytest.fixture
def env(monkeypatch, tmp_path):
    """A fake Spoolman behind spoolman_api AND stock_report (one shared requests
    module), the config, temp ledger / review stores, a captured Activity Log,
    and the check run inline."""
    fake = FakeSpoolman()
    monkeypatch.setattr(spoolman_api.requests, "get", fake.get)
    monkeypatch.setattr(spoolman_api.requests, "patch", fake.patch)
    cfg = {"server_ip": "spoolman.test", "spoolman_port": 7000, "low_stock_g": 250}
    monkeypatch.setattr(config_loader, "load_config", lambda: dict(cfg))
    monkeypatch.setattr(print_deduct_ledger, "_LEDGER_PATH", str(tmp_path / "ledger.json"))
    monkeypatch.setattr(cancel_review_store, "_STORE_PATH", str(tmp_path / "review.json"))
    monkeypatch.setattr(cancel_fetch_store, "_STORE_PATH", str(tmp_path / "fetch.json"))
    logs = []
    monkeypatch.setattr(state, "add_log_entry", lambda msg, *a, **k: logs.append((msg, a, k)))
    monkeypatch.setattr(stock_report, "_RUN_ASYNC", False)
    monkeypatch.setattr(stock_report, "_RECENT", {})      # each test starts with no recent warnings
    return {"fake": fake, "cfg": cfg, "logs": logs, "monkeypatch": monkeypatch}


def _stock_warnings(logs):
    return [(m, a) for (m, a, k) in logs if "running low" in m or " is out:" in m]


def _deduct(env, usage, heads=("XL-1",), printer="XL", job="J-1"):
    """A FINISHED print through deduct_completed_print with `usage` {position:
    grams}; everything below the gcode fetch is the real engine."""
    mp = env["monkeypatch"]
    fake = env["fake"]
    pm = {h: {"printer_name": printer, "position": i} for i, h in enumerate(heads)}
    mp.setattr(print_deduct.locations_db, "get_active_printer_map", lambda: pm)
    mp.setattr(print_deduct, "_resolve_active_locs_for_printer", lambda m, p, fb: list(pm.items()))
    mp.setattr(print_deduct, "_compute_cancel_usage",
               lambda *a, **k: ({int(p): float(g) for p, g in usage.items()}, None))
    mp.setattr(print_deduct.spoolman_api, "get_spools_at_location", fake.at)
    return print_deduct.deduct_completed_print(printer, "part.gcode", job, fb_url="http://fb",
                                               ip_address="1.2.3.4", api_key="k")


def _galaxy(env, *spools, attrs=None, name="Galaxy Black", vendor="Prusament"):
    """Filament 10 with spools (sid, remaining, location[, archived])."""
    fake = env["fake"]
    fake.add_filament(10, name=name, vendor=vendor, attrs=attrs)
    for sp in spools:
        fake.add_spool(sp[0], 10, sp[1], location=sp[2], archived=(sp[3] if len(sp) > 3 else False))
    return fake


# --- the print deduct ------------------------------------------------------------

def test_a_print_that_takes_a_filament_under_the_line_warns_once(env):
    """300 g (160 + 140) -> 220 g: one WARNING naming the grams and spools left."""
    fake = _galaxy(env, (1, 160, "XL-1"), (2, 140, "SHELF-A"))
    res = _deduct(env, {0: 80})
    assert res["status"] == "deducted"
    assert fake.remaining(1) == 80
    warns = _stock_warnings(env["logs"])
    assert len(warns) == 1, env["logs"]
    msg, args = warns[0]
    assert msg == "⚠️ Prusament PLA Galaxy Black is running low: 220 g left in 2 spools"
    assert args[0] == "WARNING"
    # It reads the filament's spools through the filter, once.
    reads = [c[1] for c in fake.calls if c[0] == "GET" and "filament.id=" in c[1]]
    assert len(reads) == 1 and reads[0].endswith("/api/v1/spool?filament.id=10&allow_archived=true")


def test_a_print_on_a_filament_already_under_the_line_is_quiet(env):
    """220 g -> 150 g: already low, so nothing is logged (a print on a low
    filament doesn't log every time)."""
    _galaxy(env, (1, 80, "XL-1"), (2, 140, "SHELF-A"))
    res = _deduct(env, {0: 70})
    assert res["status"] == "deducted"
    assert _stock_warnings(env["logs"]) == []


def test_a_print_that_stays_above_the_line_is_quiet(env):
    _galaxy(env, (1, 600, "XL-1"))
    _deduct(env, {0: 100})
    assert _stock_warnings(env["logs"]) == []


def test_the_last_spool_emptying_says_out(env):
    """Its last in-stock spool printed to 0 g (auto-archived) -> "out", even
    though the filament was already under the line. Archived spools of the same
    filament are no stock."""
    fake = _galaxy(env, (1, 60, "XL-1"), (2, 0, "", True), (3, 500, "", True))
    res = _deduct(env, {0: 60})
    assert res["status"] == "deducted"
    assert fake.spools[1]["archived"] is True
    warns = _stock_warnings(env["logs"])
    assert [m for m, _ in warns] == ["⚠️ Prusament PLA Galaxy Black is out: #1 was its last spool in stock"]


def test_crossing_the_line_and_running_out_in_one_write_is_one_out_warning(env):
    """300 g in one spool, all of it printed: ONE warning, worded "out"."""
    _galaxy(env, (1, 300, "XL-1"))
    _deduct(env, {0: 300})
    assert [m for m, _ in _stock_warnings(env["logs"])] == \
        ["⚠️ Prusament PLA Galaxy Black is out: #1 was its last spool in stock"]


def test_a_filament_not_bought_again_is_quiet_both_ways(env):
    """Marked "not buying again": running out and going low are no news. RED on
    68a9b9d for the low one (only a One-off attribute silenced "out")."""
    fake = _galaxy(env, (1, 60, "XL-1"))
    fake.filaments[10]["extra"]["fcc_no_rebuy"] = _json.dumps("Discontinued")
    _deduct(env, {0: 60}, job="J-out")
    assert fake.spools[1]["archived"] is True
    assert _stock_warnings(env["logs"]) == []

    fake.add_filament(11, name="Tiny")
    fake.filaments[11]["extra"]["fcc_no_rebuy"] = _json.dumps("One-off")
    fake.add_spool(5, 11, 300, location="XL-1")
    _deduct(env, {0: 80}, job="J-low")
    assert fake.remaining(5) == 220
    assert _stock_warnings(env["logs"]) == []


def test_the_one_off_attribute_no_longer_silences_anything(env):
    """The One-off attribute rule (dev only) is gone: such a filament running out
    is logged like any other."""
    _galaxy(env, (1, 60, "XL-1"), attrs=["One-off"])
    _deduct(env, {0: 60}, job="J-out")
    assert [m for m, _ in _stock_warnings(env["logs"])] == \
        ["⚠️ Prusament PLA Galaxy Black is out: #1 was its last spool in stock"]


def test_two_heads_on_one_filament_give_one_warning(env):
    """An INDX print charging two heads that run the same filament: grouped,
    one read, one warning."""
    fake = _galaxy(env, (1, 150, "RCOI-1"), (2, 150, "RCOI-2"))
    _deduct(env, {0: 40, 1: 40}, heads=("RCOI-1", "RCOI-2"), printer="RCOI")
    assert [m for m, _ in _stock_warnings(env["logs"])] == \
        ["⚠️ Prusament PLA Galaxy Black is running low: 220 g left in 2 spools"]
    assert len([c for c in fake.calls if c[0] == "GET" and "filament.id=" in c[1]]) == 1


def test_the_check_runs_only_after_the_ledger_write(env):
    """The exactly-once ledger entry is written before the check starts, so a
    crash in the check can never re-run the deduct."""
    _galaxy(env, (1, 160, "XL-1"), (2, 140, "SHELF-A"))
    order = []
    real_record, real_check = print_deduct_ledger.record_deduct, stock_report._check

    def _record(*a, **k):
        order.append("ledger")
        return real_record(*a, **k)

    def _check(changes):
        order.append("check")
        assert print_deduct_ledger.was_deducted("XL", "J-1") is True
        return real_check(changes)
    env["monkeypatch"].setattr(print_deduct_ledger, "record_deduct", _record)
    env["monkeypatch"].setattr(stock_report, "_check", _check)
    _deduct(env, {0: 80})
    assert order == ["ledger", "check"]
    assert len(_stock_warnings(env["logs"])) == 1


def _deduct_outcome(env):
    fake = env["fake"]
    res = _deduct(env, {0: 80})
    entry = print_deduct_ledger._load()[print_deduct_ledger._key("XL", "J-1")]
    return res, entry, fake.remaining(1)


def test_a_failing_read_never_touches_the_deduct_or_its_ledger_entry(env):
    """Patch the check's read to throw: the deduct answers the same, the spool is
    charged the same, the ledger entry is the same, and nothing is logged beyond
    a debug line."""
    _galaxy(env, (1, 160, "XL-1"), (2, 140, "SHELF-A"))

    def _boom(fid):
        raise requests.exceptions.ConnectionError("Spoolman went away")
    env["monkeypatch"].setattr(stock_report, "_filament_spools_strict", _boom)
    debug = []
    env["monkeypatch"].setattr(state.logger, "debug", lambda m, *a, **k: debug.append(m))
    res, entry, left = _deduct_outcome(env)
    assert res["status"] == "deducted" and [d["sid"] for d in res["details"]] == [1]
    assert res["details"][0]["grams"] == 80.0
    assert entry["grams"] == 80.0 and left == 80
    assert _stock_warnings(env["logs"]) == []
    assert not [m for (m, a, k) in env["logs"] if a and a[0] == "ERROR"]
    assert any("49.2b" in m for m in debug), debug


def test_a_crashing_check_never_raises_into_the_deduct(env):
    """Even a bug that escapes the check itself stays out of the deduct."""
    _galaxy(env, (1, 160, "XL-1"), (2, 140, "SHELF-A"))

    def _bug(details):
        raise RuntimeError("bug in the check")
    env["monkeypatch"].setattr(stock_report, "check_after_deduct", _bug)
    res, entry, left = _deduct_outcome(env)
    assert res["status"] == "deducted" and entry["grams"] == 80.0 and left == 80


def test_record_applied_deduct_answers_the_same_with_or_without_the_check(env):
    """_record_applied_deduct's own answer (applied, shortfall) is unchanged."""
    _galaxy(env, (1, 160, "XL-1"))
    details = [{"sid": 1, "grams": 30.0, "remaining": 130.0, "toolhead": "XL-1", "position": 0}]
    out = print_deduct._record_applied_deduct("XL", "J-9", filename="a.gcode", scale=1.0,
                                              details=details, usage_map={0: 30.0})
    assert out == (30.0, 0.0)


def test_the_check_runs_off_the_calling_thread_in_the_app(env):
    """In the app (_RUN_ASYNC True) the check is handed to its own thread: the
    deduct doesn't wait for Spoolman."""
    env["monkeypatch"].setattr(stock_report, "_RUN_ASYNC", True)
    started, release, done = threading.Event(), threading.Event(), threading.Event()
    seen = {}

    def _slow_check(changes):
        seen["thread"] = threading.current_thread()
        started.set()
        release.wait(5)
        done.set()
    env["monkeypatch"].setattr(stock_report, "_check", _slow_check)
    stock_report.check_after_deduct([{"sid": 1, "grams": 5.0, "remaining": 95.0}])
    assert started.wait(5)
    assert seen["thread"] is not threading.current_thread()
    assert seen["thread"].daemon is True
    assert not done.is_set()        # the caller returned while the check still waited
    release.set()
    assert done.wait(5)


# --- the weight funnel: /api/spool/update (weigh-out, Quick Weigh) and the wizard -------

@pytest.fixture
def client():
    app_module.app.config["TESTING"] = True
    with app_module.app.test_client() as c:
        yield c


def test_a_weigh_out_that_takes_a_filament_under_the_line_warns(env, client):
    fake = _galaxy(env, (1, 160, ""), (2, 140, "SHELF-A"))
    r = client.post("/api/spool/update", json={"id": 1, "updates": {"used_weight": 920}})
    assert r.get_json()["status"] == "success"
    assert fake.remaining(1) == 80
    assert [m for m, _ in _stock_warnings(env["logs"])] == \
        ["⚠️ Prusament PLA Galaxy Black is running low: 220 g left in 2 spools"]
    # The weight line it always wrote is still there, before the warning.
    msgs = [m for (m, a, k) in env["logs"]]
    assert any("Weight updated" in m for m in msgs)
    assert msgs.index(next(m for m in msgs if "Weight updated" in m)) < msgs.index(_stock_warnings(env["logs"])[0][0])


def test_a_weigh_out_on_a_low_filament_is_quiet(env, client):
    _galaxy(env, (1, 80, ""), (2, 140, "SHELF-A"))
    client.post("/api/spool/update", json={"id": 1, "updates": {"used_weight": 990}})
    assert _stock_warnings(env["logs"]) == []


def test_a_weigh_out_that_empties_the_last_spool_says_out(env, client):
    fake = _galaxy(env, (1, 40, ""), (2, 0, "", True))
    r = client.post("/api/spool/update", json={"id": 1, "updates": {"used_weight": 1000}})
    body = r.get_json()
    assert body["status"] == "success" and body["auto_archived"] is True
    assert fake.spools[1]["archived"] is True
    assert [m for m, _ in _stock_warnings(env["logs"])] == \
        ["⚠️ Prusament PLA Galaxy Black is out: #1 was its last spool in stock"]


def test_a_refill_is_quiet_and_reads_nothing_more(env, client):
    fake = _galaxy(env, (1, 80, ""))
    before = len(fake.calls)
    client.post("/api/spool/update", json={"id": 1, "updates": {"used_weight": 100}})
    assert _stock_warnings(env["logs"]) == []
    assert not [c for c in fake.calls[before:] if c[0] == "GET" and "filament.id=" in c[1]]


def test_a_failing_read_never_touches_the_weight_write(env, client):
    fake = _galaxy(env, (1, 160, ""), (2, 140, "SHELF-A"))

    def _boom(fid):
        raise requests.exceptions.ReadTimeout("slow NAS")
    env["monkeypatch"].setattr(stock_report, "_filament_spools_strict", _boom)
    r = client.post("/api/spool/update", json={"id": 1, "updates": {"used_weight": 920}})
    assert r.get_json()["status"] == "success" and fake.remaining(1) == 80
    assert _stock_warnings(env["logs"]) == []


def test_the_wizard_save_goes_through_the_same_funnel(env, client):
    fake = _galaxy(env, (1, 160, ""), (2, 140, "SHELF-A"))
    r = client.post("/api/edit_spool_wizard", json={"spool_id": 1, "spool_data": {"used_weight": 920}})
    assert r.get_json()["success"] is True and fake.remaining(1) == 80
    assert [m for m, _ in _stock_warnings(env["logs"])] == \
        ["⚠️ Prusament PLA Galaxy Black is running low: 220 g left in 2 spools"]


# --- the rules, one by one -------------------------------------------------------------

def _rec(sid, fid, remaining, archived=False, attrs=None, vendor="Prusament", name="Galaxy Black"):
    fil = {"id": fid, "name": name, "material": "PLA", "color_hex": "222222",
           "vendor": {"name": vendor}, "weight": 1000.0,
           "extra": {"original_color": name, **({"filament_attributes": attrs} if attrs else {})}}
    return {"id": sid, "filament": fil, "initial_weight": 1000.0, "used_weight": 1000.0 - remaining,
            "remaining_weight": remaining, "archived": archived}


def test_a_spool_that_moved_on_since_the_write_makes_the_check_say_nothing(env):
    """The fresh read shows #1 at 50 g, not the 80 g the write left: something
    else wrote in between, so before/after can't be trusted. Silence."""
    change = {"sid": 1, "fid": 10, "before_g": 160.0, "after_g": 80.0, "before_in": True, "after_in": True}
    spools = [_rec(1, 10, 50.0), _rec(2, 10, 140.0)]
    assert stock_report._crossing([change], spools, 250.0) is None
    spools = [_rec(1, 10, 80.0), _rec(2, 10, 140.0)]
    assert stock_report._crossing([change], spools, 250.0)[0].endswith("220 g left in 2 spools")


def test_the_written_spool_missing_from_the_read_makes_the_check_say_nothing(env):
    change = {"sid": 1, "fid": 10, "before_g": 160.0, "after_g": 80.0, "before_in": True, "after_in": True}
    assert stock_report._crossing([change], [_rec(2, 10, 140.0)], 250.0) is None


def test_a_spool_archived_with_grams_left_was_never_stock_for_a_charge(env):
    """A print charging a spool archived by hand (it keeps grams on record and
    stays archived) moves no stock: it was out of stock before and after."""
    change = stock_report._changes_from_details([{"sid": 1, "grams": 30.0, "remaining": 270.0}])
    spools = [_rec(1, 10, 270.0, archived=True), _rec(2, 10, 200.0)]
    assert stock_report._crossing(change, spools, 250.0) is None


def test_a_charge_that_says_it_was_archived_moves_no_stock(env):
    """A review Apply may charge a spool archived by hand (Group 43.2). A charge
    that says so (`was_archived`) emptying it is not the filament running out;
    one that says it wasn't, or (the automatic deduct) says nothing, is."""
    spools = [_rec(1, 10, 0.0, archived=True)]
    hand = stock_report._changes_from_details([{"sid": 1, "grams": 30.0, "remaining": 0.0, "was_archived": True}])
    assert stock_report._crossing(hand, spools, 250.0) is None
    for detail in ({"sid": 1, "grams": 30.0, "remaining": 0.0, "was_archived": False},
                   {"sid": 1, "grams": 30.0, "remaining": 0.0}):
        found = stock_report._crossing(stock_report._changes_from_details([detail]), spools, 250.0)
        assert found[0] == "⚠️ Prusament PLA Galaxy Black is out: #1 was its last spool in stock"


def test_the_filament_name_is_escaped_for_the_activity_log(env):
    """The Activity Log renders a message as HTML; vendor and colour names are
    free text."""
    change = {"sid": 1, "fid": 10, "before_g": 300.0, "after_g": 220.0, "before_in": True, "after_in": True}
    msg, colour, kind = stock_report._crossing(
        [change], [_rec(1, 10, 220.0, vendor="<img src=x onerror=alert(1)>")], 250.0)
    assert "<img" not in msg and "&lt;img src=x onerror=alert(1)&gt;" in msg
    assert colour == "222222" and kind == "low"


def test_the_same_crossing_reported_twice_is_logged_once(env):
    """Two writes to one filament landing together can each see the same
    crossing (each reads the other's write): the warning is logged once. A
    different crossing of the same filament (it then runs out) still logs."""
    fake = _galaxy(env, (1, 80, ""), (2, 140, "SHELF-A"))
    low = {"sid": 1, "fid": 10, "before_g": 160.0, "after_g": 80.0, "before_in": True, "after_in": True}
    stock_report._check([dict(low)])
    stock_report._check([dict(low)])
    assert [m for m, _ in _stock_warnings(env["logs"])] == \
        ["⚠️ Prusament PLA Galaxy Black is running low: 220 g left in 2 spools"]
    fake.spools[1].update(used_weight=1000.0, archived=True)
    fake.spools[2].update(used_weight=1000.0, archived=True)
    out = {"sid": 2, "fid": 10, "before_g": 140.0, "after_g": 0.0, "before_in": True, "after_in": False}
    stock_report._check([out])
    assert len(_stock_warnings(env["logs"])) == 2
    assert _stock_warnings(env["logs"])[1][0].endswith("is out: #2 was its last spool in stock")


def test_the_filament_read_is_filtered_in_fcc_too(env):
    """Spoolman ignores a filter it doesn't know (its extra= filters are
    ignored); if it ever ignored filament.id the check must still see only that
    filament's spools."""
    fake = FakeSpoolman(honour_filter=False)
    env["monkeypatch"].setattr(spoolman_api.requests, "get", fake.get)
    fake.add_filament(10)
    fake.add_filament(11, name="Other")
    fake.add_spool(1, 10, 100)
    fake.add_spool(2, 11, 900)
    fake.add_spool(3, 10, 0, archived=True)
    got = stock_report._filament_spools_strict(10)
    assert sorted(s["id"] for s in got) == [1, 3]
    assert fake.calls[-1][1].endswith("/api/v1/spool?filament.id=10&allow_archived=true")


def test_a_404_or_an_unreadable_spool_logs_nothing(env):
    """A charge of a spool Spoolman no longer has (its truthy 404 body) or can't
    answer: no warning, no error line."""
    env["fake"].add_filament(10)
    stock_report._check([{"sid": 77, "fid": None, "before_g": 300.0, "after_g": 200.0,
                          "before_in": None, "after_in": None}])
    assert env["logs"] == []


def test_the_funnel_needs_both_records_of_the_same_spool(env):
    """A pre-read blip ({} or Spoolman's 404 body), or records without a filament
    (as most existing tests' fakes are), start no read at all."""
    fake = env["fake"]
    post = _rec(1, 10, 80.0)
    for pre in ({}, {"message": "not found"}, None):
        stock_report.check_after_weight_change(1, pre, post)
    # Records with no filament on them, as most existing tests' fakes are.
    stock_report.check_after_weight_change(1, {"id": 1, "remaining_weight": 160.0, "archived": False},
                                           {"id": 1, "remaining_weight": 80.0, "archived": False})
    # A `post` that is another spool's record.
    stock_report.check_after_weight_change(1, _rec(1, 10, 160.0), _rec(2, 10, 80.0))
    assert fake.calls == [] and env["logs"] == []


def test_the_threshold_setting_moves_the_line(env, client):
    env["cfg"]["low_stock_g"] = 100
    _galaxy(env, (1, 160, ""), (2, 140, "SHELF-A"))
    client.post("/api/spool/update", json={"id": 1, "updates": {"used_weight": 920}})   # 300 -> 220
    assert _stock_warnings(env["logs"]) == []
    client.post("/api/spool/update", json={"id": 2, "updates": {"used_weight": 950}})   # 220 -> 130
    assert _stock_warnings(env["logs"]) == []
    client.post("/api/spool/update", json={"id": 2, "updates": {"used_weight": 990}})   # 130 -> 90
    assert [m for m, _ in _stock_warnings(env["logs"])] == \
        ["⚠️ Prusament PLA Galaxy Black is running low: 90 g left in 2 spools"]
