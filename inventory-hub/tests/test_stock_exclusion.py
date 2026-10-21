"""Excluded from Low and Out (Derek, 2026-10-20; called "Excluded", not "Not buying
again", since 2026-10-21): POST / DELETE /api/filament/<id>/stock_exclusion
(stock_report.exclude_filament / include_again), from the ⚠️ Low stock list.

Marking a filament stores three text extras: `fcc_stock_excluded` (the reason, as its
label), `fcc_stock_excluded_note` and `fcc_stock_excluded_at` (the day it was first marked).
Including it again clears all three. Both read the filament strictly first and
write once through the REAL spoolman_api.update_filament (read-merge: every other
extra is kept), here against tests/spoolman_extra_fake.SpoolmanHTTPFake, which
stores a PATCH's `extra` as each Spoolman version does and checks every value by
its field type: 0.27.0 (dev and prod) merges key by key and drops a key sent as
JSON null, so a clear (FCC's delete sentinel) removes the keys; 0.23.1 replaces a
filament's `extra` and refuses a null, so the same clear writes text blanks. An
unregistered extra is refused (400), and a filament that doesn't exist is a 404.
A reason Spoolman keeps after a clear is a failure (still excluded); an old note
it keeps is answered as a `warning`.

What the list does with the mark is pinned by test_stock_report.py; the page by
test_low_stock_panel.py. Hermetic: runs under --offline.
"""
from __future__ import annotations

import copy
import json
import os
import sys
from pathlib import Path

import pytest
import requests

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import app as app_module  # noqa: E402  (registers the routes)
import config_loader  # noqa: E402
import spoolman_api  # noqa: E402
import state  # noqa: E402
import stock_report  # noqa: E402
from spoolman_extra_fake import SpoolmanHTTPFake, _Resp, unwire  # noqa: E402

HUB = Path(__file__).resolve().parent.parent
KEYS = ("fcc_stock_excluded", "fcc_stock_excluded_note", "fcc_stock_excluded_at")
# What this fake Spoolman knows as filament extras: the three new ones are
# registered (startup does it: REQUIRED_FILAMENT_EXTRAS), plus a few siblings.
FIELDS = [{"key": k, "name": k, "field_type": "text"}
          for k in ("original_color", "product_url", "nozzle_temp_max") + KEYS] + [
    {"key": "filament_attributes", "name": "Filament Attributes", "field_type": "choice",
     "multi_choice": True, "choices": ["Silk", "Matte"]}]


class FakeSpoolman(SpoolmanHTTPFake):
    """The shared faithful fake, plus this file's levers: `fail_get` (an exception
    every GET raises), `patch_answer` ((status, body) refusing every PATCH),
    `patch_lands_then_times_out`, and `ignore_clears` (a Spoolman that keeps a key
    sent as null or blank: the stored value is put back in the PATCH it applies)."""

    def __init__(self, version):
        super().__init__(version=version, fields={"filament": copy.deepcopy(FIELDS)})
        self.calls = []            # (method, path)
        self.fail_get = None
        self.patch_answer = None
        self.patch_lands_then_times_out = False
        self.ignore_clears = False
        self.filaments = self.records["filament"]

    def add(self, fid, name="Galaxy Black", vendor="Prusament", extra=None):  # noqa: D401
        ex = {"original_color": json.dumps(name), "product_url": json.dumps("https://example.com/p"),
              "filament_attributes": json.dumps(["Silk"]), "nozzle_temp_max": json.dumps("230")}
        ex.update(extra or {})
        return super().add("filament", fid, extra=ex, name=name, material="PLA", color_hex="222222",
                           vendor={"id": 1, "name": vendor}, weight=1000)

    def unregister(self, key):
        self.fields["filament"] = [f for f in self.fields["filament"] if f["key"] != key]

    def get(self, url, timeout=None, **kw):
        self.calls.append(("GET", str(url).split("spoolman.test:7000", 1)[-1]))
        if self.fail_get:
            raise self.fail_get
        return super().get(url, timeout=timeout, **kw)

    def patch(self, url, json=None, timeout=None, **kw):     # noqa: A002  (requests' own name)
        self.calls.append(("PATCH", str(url).split("spoolman.test:7000", 1)[-1]))
        if self.patch_answer:
            return _Resp(*self.patch_answer)
        body = copy.deepcopy(json)
        if self.ignore_clears and isinstance((body or {}).get("extra"), dict):
            # Whatever FCC sent to clear a key, the stored value goes back in.
            stored = self.filaments.get(int(str(url).rstrip("/").rsplit("/", 1)[-1]), {}).get("extra", {})
            for k, v in list(body["extra"].items()):
                if (v is None or unwire(v) in ("", [])) and k in stored:
                    body["extra"][k] = stored[k]
        r = super().patch(url, json=body, timeout=timeout, **kw)
        if self.patch_lands_then_times_out:
            raise requests.exceptions.ReadTimeout("read timed out")
        return r

    def decoded(self, fid):
        return {k: unwire(v) for k, v in self.filaments[fid]["extra"].items()}


@pytest.fixture(params=["0.27.0", "0.23.1"])
def env(monkeypatch, request):
    fake = FakeSpoolman(request.param)
    monkeypatch.setattr(spoolman_api.requests, "get", fake.get)
    monkeypatch.setattr(spoolman_api.requests, "patch", fake.patch)
    monkeypatch.setattr(spoolman_api, "_RAW_EXTRAS_RETRY_DELAY_S", 0)
    # The clear's version and field-list reads are cached per Spoolman url.
    monkeypatch.setattr(spoolman_api, "_FIELD_SCHEMA_CACHE", {})
    monkeypatch.setattr(spoolman_api, "_SPOOLMAN_VERSION_CACHE", {})
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
    env["fake"].unregister("fcc_stock_excluded")             # a Spoolman that missed the startup registration
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
    if env["fake"].nulls_ok():
        assert not set(KEYS) & set(ex), ex                 # 0.27: gone, not blank
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


def test_a_reason_spoolman_keeps_is_a_failure(env):
    """Include again that Spoolman doesn't apply: the filament would stay
    excluded, so the answer is a failure (spoolman_api logs the WARNING)."""
    env["fake"].add(7, extra={"fcc_stock_excluded": json.dumps("Discontinued"),
                              "fcc_stock_excluded_at": json.dumps("2026-01-02")})
    env["fake"].ignore_clears = True
    r = _delete(env, 7)
    assert r.status_code == 502, r.get_json()
    assert r.get_json()["error"] == "not_cleared"
    assert "not cleared" in r.get_json()["msg"]
    assert [c for _, c, _ in env["logs"]] == ["WARNING"]
    assert env["fake"].decoded(7)["fcc_stock_excluded"] == "Discontinued"


def test_an_old_note_spoolman_keeps_is_said(env):
    """Excluding again with the note emptied: the exclusion lands; an old note
    Spoolman keeps is answered as a `warning` (the page toasts it)."""
    env["fake"].add(7, extra={"fcc_stock_excluded": json.dumps("Discontinued"),
                              "fcc_stock_excluded_note": json.dumps("old note")})
    env["fake"].ignore_clears = True
    r = _post(env, 7, {"reason": "one_off", "note": ""})
    assert r.status_code == 200, r.get_json()
    assert "not cleared" in r.get_json()["warning"]
    assert env["fake"].decoded(7)["fcc_stock_excluded"] == "One-off"


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
