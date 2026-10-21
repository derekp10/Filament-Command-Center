"""Excluded from Low and Out (Derek, 2026-10-20; called "Excluded", not "Not buying
again", since 2026-10-21): POST / DELETE /api/filament/<id>/stock_exclusion
(stock_report.exclude_filament / include_again), from the ⚠️ Low stock list.

Marking a filament stores three text extras: `fcc_stock_excluded` (the reason, as its
label), `fcc_stock_excluded_note` and `fcc_stock_excluded_at` (the day it was first marked).
Including it again clears all three. Both read the filament strictly first and
write once through the REAL spoolman_api.update_filament (read-merge: every other
extra is kept), here against a fake Spoolman HTTP layer that behaves like the
real one where it matters, in both of its ways of taking a PATCH's `extra`:
Spoolman 0.23 replaces the whole sub-document (a key left out is gone) and 0.27
(dev's, checked 2026-10-20) merges it (a key left out is KEPT, so a key is
cleared only by writing it blank: the delete sentinel clears nothing there). An
unregistered extra or a text extra that isn't a JSON string is refused (400), and
a filament that doesn't exist is a 404.

What the list does with the mark is pinned by test_stock_report.py; the page by
test_low_stock_panel.py. Hermetic: runs under --offline.
"""
from __future__ import annotations

import copy
import json
import os
import re
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import requests

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import app as app_module  # noqa: E402  (registers the routes)
import config_loader  # noqa: E402
import spoolman_api  # noqa: E402
import state  # noqa: E402
import stock_report  # noqa: E402

HUB = Path(__file__).resolve().parent.parent
KEYS = ("fcc_stock_excluded", "fcc_stock_excluded_note", "fcc_stock_excluded_at")
# What this fake Spoolman knows as filament extras: the three new ones are
# registered (startup does it: REQUIRED_FILAMENT_EXTRAS), plus a few siblings.
REGISTERED = {"original_color", "product_url", "filament_attributes", "nozzle_temp_max"} | set(KEYS)
TEXT = {"original_color", "product_url", "nozzle_temp_max"} | set(KEYS)


class FakeSpoolman:
    def __init__(self, mode="merge"):
        self.mode = mode           # "merge" (Spoolman 0.27) or "replace" (0.23)
        self.filaments = {}
        self.calls = []            # (method, path)
        self.fail_get = None       # an exception to raise on a GET
        self.patch_answer = None   # (status, body) to refuse a PATCH with
        self.patch_lands_then_times_out = False
        self.registered = set(REGISTERED)

    def add(self, fid, name="Galaxy Black", vendor="Prusament", extra=None):
        ex = {"original_color": json.dumps(name), "product_url": json.dumps("https://example.com/p"),
              "filament_attributes": json.dumps(["Silk"]), "nozzle_temp_max": json.dumps("230")}
        ex.update(extra or {})
        self.filaments[fid] = {"id": fid, "name": name, "material": "PLA", "color_hex": "222222",
                               "vendor": {"id": 1, "name": vendor}, "weight": 1000, "extra": ex}

    def _resp(self, status, body):
        r = MagicMock()
        r.status_code, r.ok = status, 200 <= status < 300
        r.json.return_value = copy.deepcopy(body)
        r.text = json.dumps(body)
        if not r.ok:
            r.raise_for_status.side_effect = requests.exceptions.HTTPError(f"{status} error")
        return r

    def get(self, url, timeout=None, **kw):
        path = url.split("spoolman.test:7000", 1)[-1]
        self.calls.append(("GET", path))
        if self.fail_get:
            raise self.fail_get
        m = re.fullmatch(r"/api/v1/filament/(\d+)", path)
        if not m:
            raise AssertionError(f"unexpected GET {path}")
        fil = self.filaments.get(int(m.group(1)))
        return self._resp(200, fil) if fil else self._resp(404, {"message": "Item not found"})

    def patch(self, url, json=None, timeout=None, **kw):     # noqa: A002  (requests' own name)
        path = url.split("spoolman.test:7000", 1)[-1]
        self.calls.append(("PATCH", path))
        if self.patch_answer:
            return self._resp(*self.patch_answer)
        fid = int(re.fullmatch(r"/api/v1/filament/(\d+)", path).group(1))
        extra = (json or {}).get("extra")
        for k, v in (extra or {}).items():
            if k not in self.registered:
                return self._resp(400, {"message": f"Unknown extra field {k}"})
            if k in TEXT and not isinstance(_loads(v), str):
                return self._resp(400, {"message": f"Value is not a string: {k}"})
        if self.mode == "replace":
            self.filaments[fid]["extra"] = dict(extra)       # 0.23: the sub-document is replaced
        else:
            self.filaments[fid]["extra"].update(extra)       # 0.27: key by key; a key left out stays
        if self.patch_lands_then_times_out:
            raise requests.exceptions.ReadTimeout("read timed out")
        return self._resp(200, self.filaments[fid])

    def decoded(self, fid):
        return {k: _loads(v) for k, v in self.filaments[fid]["extra"].items()}


def _loads(v):
    try:
        return json.loads(v)
    except (TypeError, ValueError):
        return None


@pytest.fixture(params=["merge", "replace"])
def env(monkeypatch, request):
    fake = FakeSpoolman(mode=request.param)
    monkeypatch.setattr(spoolman_api.requests, "get", fake.get)
    monkeypatch.setattr(spoolman_api.requests, "patch", fake.patch)
    monkeypatch.setattr(spoolman_api, "_RAW_EXTRAS_RETRY_DELAY_S", 0)
    monkeypatch.setattr(config_loader, "load_config",
                        lambda: {"server_ip": "spoolman.test", "spoolman_port": 7000})
    monkeypatch.setattr(stock_report, "_server_day", lambda: "2026-10-20")
    logs = []
    monkeypatch.setattr(state, "add_log_entry", lambda msg, cat="INFO", color=None, meta=None:
                        logs.append((msg, cat, color)))
    app_module.app.config["TESTING"] = True
    with app_module.app.test_client() as client:
        yield {"fake": fake, "logs": logs, "client": client}


def _post(env, fid, body):
    return env["client"].post(f"/api/filament/{fid}/stock_exclusion", json=body)


def _delete(env, fid):
    return env["client"].delete(f"/api/filament/{fid}/stock_exclusion")


def _writes(env):
    return [c for c in env["fake"].calls if c[0] == "PATCH"]


def _mark_keys(env, fid):
    """The three keys as stored, a blank or missing one as ""."""
    ex = env["fake"].decoded(fid)
    return {k: ex.get(k) or "" for k in KEYS}


SIBLINGS = {"original_color": "Galaxy Black", "product_url": "https://example.com/p",
            "filament_attributes": ["Silk"], "nozzle_temp_max": "230"}


# --- marking ------------------------------------------------------------------------

def test_marking_writes_the_three_extras_and_keeps_every_other(env):
    env["fake"].add(7)
    r = _post(env, 7, {"reason": "discontinued", "note": "Prusa stopped making it"})
    assert r.status_code == 200, r.get_json()
    body = r.get_json()
    assert body["success"] is True and body["filament_id"] == 7
    assert body["display"] == "Prusament - PLA - Galaxy Black"
    assert body["excluded"] == {"reason": "Discontinued", "code": "discontinued",
                                    "note": "Prusa stopped making it", "at": "2026-10-20"}
    assert body["was"] is None
    assert body["msg"] == "Excluded Prusament - PLA - Galaxy Black from Low and Out (Discontinued)."
    assert env["fake"].decoded(7) == dict(SIBLINGS, fcc_stock_excluded="Discontinued",
                                          fcc_stock_excluded_note="Prusa stopped making it",
                                          fcc_stock_excluded_at="2026-10-20")
    assert len(_writes(env)) == 1
    assert env["logs"] == [("🔕 Excluded Prusament PLA Galaxy Black from Low and Out (Discontinued: Prusa stopped making it)",
                            "INFO", "222222")]


@pytest.mark.parametrize("today, day", [
    ("2026-10-19", "2026-10-19"),      # the page's evening, the server's (UTC) morning
    ("2026-10-22", "2026-10-22"),
    ("2026-10-25", "2026-10-20"),      # too far from the server's clock: the server's day
    ("2026-02-31", "2026-10-20"),      # not a date
    ("yesterday", "2026-10-20"),
    (None, "2026-10-20"),
])
def test_a_new_mark_takes_the_pages_own_day_when_it_is_believable(env, today, day):
    env["fake"].add(7)
    body = {"reason": "discontinued"}
    if today is not None:
        body["today"] = today
    assert _post(env, 7, body).status_code == 200
    assert env["fake"].decoded(7)["fcc_stock_excluded_at"] == day


def test_marking_again_changes_why_and_keeps_the_day(env):
    env["fake"].add(7, extra={"fcc_stock_excluded": json.dumps("Discontinued"),
                              "fcc_stock_excluded_note": json.dumps("old note"),
                              "fcc_stock_excluded_at": json.dumps("2026-01-02")})
    r = _post(env, 7, {"reason": "one_off", "note": "", "today": "2026-10-21"})
    assert r.status_code == 200, r.get_json()
    assert r.get_json()["was"]["reason"] == "Discontinued"
    ex = env["fake"].decoded(7)
    assert ex["fcc_stock_excluded"] == "One-off" and ex["fcc_stock_excluded_at"] == "2026-01-02"
    assert _mark_keys(env, 7)["fcc_stock_excluded_note"] == ""   # a blank note clears the old one
    assert {k: ex[k] for k in SIBLINGS} == SIBLINGS
    assert env["logs"][-1][0] == "🔕 Excluded Prusament PLA Galaxy Black from Low and Out (One-off)"


@pytest.mark.parametrize("note", ["123", "true", "[1, 2]", '"quoted"', "  spaced  "])
def test_a_note_that_looks_like_json_stays_text(env, note):
    """The keys are text extras: Spoolman refuses a number or a boolean there, and
    the note must read back exactly as typed (trimmed)."""
    env["fake"].add(7)
    r = _post(env, 7, {"reason": "other", "note": note})
    assert r.status_code == 200, r.get_json()
    assert env["fake"].decoded(7)["fcc_stock_excluded_note"] == note.strip()
    fil = spoolman_api.parse_inbound_data(copy.deepcopy(env["fake"].filaments[7]))
    assert stock_report.exclusion_of(fil)["note"] == note.strip()


@pytest.mark.parametrize("body, error", [
    ({}, "bad_reason"),
    ({"reason": "nope"}, "bad_reason"),
    ({"reason": None, "note": "x"}, "bad_reason"),
    ({"reason": "other"}, "note_needed"),
    ({"reason": "other", "note": "   "}, "note_needed"),
    ({"reason": "discontinued", "note": "x" * 501}, "note_too_long"),
    ({"reason": "discontinued", "note": 123}, "bad_note"),
])
def test_a_bad_request_is_refused_before_anything_is_read_or_written(env, body, error):
    env["fake"].add(7)
    r = _post(env, 7, body)
    assert r.status_code == 400 and r.get_json() == {"success": False, "error": error,
                                                    "msg": r.get_json()["msg"]}
    assert env["fake"].calls == [] and env["logs"] == []


def test_cant_find_it_is_a_reason_of_its_own(env):
    """Derek, 2026-10-21: one he can't get any more may be one he liked."""
    env["fake"].add(7)
    r = _post(env, 7, {"reason": "cant_find", "note": "Not on Amazon or the maker's store"})
    assert r.status_code == 200, r.get_json()
    assert r.get_json()["excluded"]["reason"] == "Can't find it"
    assert env["fake"].decoded(7)["fcc_stock_excluded"] == "Can't find it"


def test_a_note_of_500_characters_is_fine(env):
    env["fake"].add(7)
    assert _post(env, 7, {"reason": "didnt_like", "note": "x" * 500}).status_code == 200
    assert env["fake"].decoded(7)["fcc_stock_excluded"] == "Didn't like it"


def test_a_filament_that_doesnt_exist_is_a_404_with_nothing_written(env):
    r = _post(env, 99, {"reason": "discontinued"})
    assert r.status_code == 404 and r.get_json()["error"] == "no_filament"
    assert "#99" in r.get_json()["msg"]
    assert _writes(env) == [] and env["logs"] == []
    assert _delete(env, 99).status_code == 404


def test_spoolman_not_answering_is_a_502_with_nothing_written(env):
    env["fake"].add(7)
    env["fake"].fail_get = requests.exceptions.ConnectionError("down")
    for r in (_post(env, 7, {"reason": "discontinued"}), _delete(env, 7)):
        assert r.status_code == 502 and r.get_json()["error"] == "spoolman_unreachable"
        assert "nothing was changed" in r.get_json()["msg"]
    assert _writes(env) == [] and env["logs"] == []


def test_a_refused_write_says_why_and_logs_it(env):
    """Spoolman's own words reach the page and the Activity Log (an ERROR line)."""
    env["fake"].add(7)
    env["fake"].registered -= {"fcc_stock_excluded"}         # a Spoolman that missed the startup registration
    r = _post(env, 7, {"reason": "discontinued"})
    assert r.status_code == 502
    body = r.get_json()
    assert body["error"] == "write_failed" and "Unknown extra field fcc_stock_excluded" in body["msg"]
    assert [c for _, c, _ in env["logs"]] == ["ERROR"]
    assert env["logs"][0][0].startswith("❌ Couldn't exclude Prusament PLA Galaxy Black from Low and Out: ")
    assert "Unknown extra field fcc_stock_excluded" in env["logs"][0][0]
    assert "fcc_stock_excluded" not in env["fake"].decoded(7)


def test_a_write_reported_failed_that_landed_counts(env):
    """update_filament's PATCH has a 2 s read timeout: it can land and still
    report failure. Read back, it counts (no ERROR, no second write)."""
    env["fake"].add(7)
    env["fake"].patch_lands_then_times_out = True
    r = _post(env, 7, {"reason": "one_off", "note": "gift"})
    assert r.status_code == 200, r.get_json()
    assert env["fake"].decoded(7)["fcc_stock_excluded"] == "One-off"
    assert len(_writes(env)) == 1
    assert [c for _, c, _ in env["logs"]] == ["INFO"]


# --- including again --------------------------------------------------------------------

def test_include_again_clears_all_three_and_keeps_every_other(env):
    env["fake"].add(7, extra={"fcc_stock_excluded": json.dumps("Discontinued"),
                              "fcc_stock_excluded_note": json.dumps("n"),
                              "fcc_stock_excluded_at": json.dumps("2026-01-02")})
    r = _delete(env, 7)
    assert r.status_code == 200, r.get_json()
    body = r.get_json()
    assert body["success"] is True and body["changed"] is True and body["excluded"] is None
    assert body["was"]["reason"] == "Discontinued"
    assert body["msg"] == "Prusament - PLA - Galaxy Black is included again."
    ex = env["fake"].decoded(7)
    assert {k: ex[k] for k in SIBLINGS} == SIBLINGS
    assert _mark_keys(env, 7) == {k: "" for k in KEYS}    # cleared in either Spoolman
    fil = spoolman_api.parse_inbound_data(copy.deepcopy(env["fake"].filaments[7]))
    assert stock_report.exclusion_of(fil) is None
    # A second Include again finds nothing to clear.
    assert _delete(env, 7).get_json()["changed"] is False and len(_writes(env)) == 1
    assert env["logs"] == [("↩️ Prusament PLA Galaxy Black is included in Low and Out again (it was excluded: Discontinued)",
                            "INFO", "222222")]


def test_include_again_on_a_filament_not_marked_writes_nothing(env):
    env["fake"].add(7, extra={k: json.dumps("") for k in KEYS})      # blank: as one included again
    r = _delete(env, 7)
    assert r.status_code == 200 and r.get_json()["changed"] is False
    assert r.get_json()["msg"] == "Prusament - PLA - Galaxy Black wasn't excluded."
    assert _writes(env) == [] and env["logs"] == []


def test_a_refused_include_again_says_why(env):
    env["fake"].add(7, extra={"fcc_stock_excluded": json.dumps("Discontinued")})
    env["fake"].patch_answer = (500, {"message": "database is locked"})
    r = _delete(env, 7)
    assert r.status_code == 502 and "database is locked" in r.get_json()["msg"]
    assert env["logs"][0][1] == "ERROR" and "Couldn't include" in env["logs"][0][0]
    assert env["fake"].decoded(7)["fcc_stock_excluded"] == "Discontinued"


def test_the_log_lines_are_escaped(env):
    """The Activity Log renders a message as HTML; names and notes are free text."""
    env["fake"].add(7, name="<b>Bold</b>", vendor="A&B")
    _post(env, 7, {"reason": "other", "note": "<script>x</script>"})
    msg = env["logs"][0][0]
    assert "<b>" not in msg and "<script>" not in msg
    assert "A&amp;B" in msg and "&lt;script&gt;x&lt;/script&gt;" in msg


# --- where the fields come from ----------------------------------------------------------

def test_the_fields_are_registered_at_startup_and_in_setup_fields():
    """Spoolman refuses a write carrying an unregistered extra: startup registers
    them (REQUIRED_FILAMENT_EXTRAS) and setup_fields.py does on a rebuild. They
    are text kept as JSON strings (JSON_STRING_FIELDS)."""
    req = {k: (n, t) for k, n, t in spoolman_api.REQUIRED_FILAMENT_EXTRAS}
    assert req["fcc_stock_excluded"] == ("Excluded From Low Stock", "text")
    assert req["fcc_stock_excluded_note"] == ("Excluded From Low Stock: Note", "text")
    assert req["fcc_stock_excluded_at"] == ("Excluded From Low Stock: Since", "text")
    assert set(KEYS) <= set(spoolman_api.JSON_STRING_FIELDS)
    setup = (HUB.parent / "setup-and-rebuild" / "setup_fields.py").read_text(encoding="utf-8")
    for key, name in (("fcc_stock_excluded", "Excluded From Low Stock"),
                      ("fcc_stock_excluded_note", "Excluded From Low Stock: Note"),
                      ("fcc_stock_excluded_at", "Excluded From Low Stock: Since")):
        assert f'("{key}", "{name}", "text")' in setup
    assert stock_report.EXCLUDE_KEYS == KEYS


def test_the_wizard_never_draws_them_as_plain_fields():
    """The wizard draws every filament extra it doesn't hide as an input; these
    are set from the Low stock list, which checks the reason and keeps the day."""
    src = (HUB / "static" / "js" / "modules" / "inv_wizard.js").read_text(encoding="utf-8")
    hide = src[src.index("if (['sheet_link', 'price_total'"):]
    hide = hide[:hide.index("].includes(field.key)) return;")]
    for key in KEYS:
        assert f"'{key}'" in hide, key
