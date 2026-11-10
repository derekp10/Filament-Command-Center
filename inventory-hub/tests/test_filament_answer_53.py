"""A filament read that says what happened, and two sites that now read through
it (Group 53 review: D3, D4 / r3-4, D6 / r3-5).

spoolman_api.get_filament hands back Spoolman's parsed body whatever the status:
a 404's {"message": "No filament with ID 99 found."} and a 500's {"message":
"database is locked"} are truthy dicts, so a caller's `if not fil` never fired
and the body was read as the filament. get_filament_answer says what happened,
with get_spool_answer's contract:
  (record, True)  Spoolman answered JSON (a 404's body is a dict with no id),
  (None, True)    a 5xx, whatever its body, or a body that isn't JSON,
  (None, False)   no answer (no connection, a timeout).
The record is the filament only when it is a dict whose id is the one asked for.

Besides Merge Filament (test_filament_merge.py), two sites read through it:
  - bulk_set (/api/filament_attributes/bulk_set): a deleted filament was counted
    "unchanged" with success: true, and an add over it failed with the pre-merge
    read's refusal; a 5xx body read as a filament with no attributes, so an add
    wrote the added choice alone over its real ones. Now Spoolman's own "no such
    filament" is "filament not found", one it couldn't send is said so, and
    nothing is written for either.
  - the Prusament link scan: a 5xx body read as the filament, every temp read as
    blank, and the write a moment later overwrote all four set temps (and the
    differing-temps suggestion was skipped). Now a read that isn't the filament
    writes nothing (not even the spool's metadata) and answers the error the page
    toasts for 7 s, with a WARNING Activity Log line.

The real helper, the real routes and the real write helpers, against the repo's
Spoolman fake (spoolman_extra_fake.SpoolmanHTTPFake: a missing record answers
404 with a JSON body, as Spoolman does); only the prusament.com page is stubbed.
"""
from __future__ import annotations

import copy
import json
import os
import sys
from urllib.parse import urlsplit

import pytest
import requests

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import app as flask_app  # noqa: E402
import external_parsers  # noqa: E402
import spoolman_api  # noqa: E402
import state  # noqa: E402
from spoolman_extra_fake import SpoolmanHTTPFake, _Resp  # noqa: E402

SM = "http://spoolman.test:7913"
TIMEOUT = requests.exceptions.ReadTimeout(
    "HTTPConnectionPool(host='spoolman.test', port=7913): Read timed out. (read timeout=3)")


class _Spoolman(SpoolmanHTTPFake):
    """SpoolmanHTTPFake with canned answers for a GET path: `canned[path]` is a
    list of _Resp answers or errors to raise (as requests raises one when Spoolman
    doesn't answer), taken in turn; once it is empty the fake answers."""

    def __init__(self, **kw):
        super().__init__(**kw)
        self.canned = {}

    def get(self, url, timeout=None, **kw):
        path = urlsplit(str(url)).path.rstrip("/")
        queue = self.canned.get(path)
        if queue:
            answer = queue.pop(0)
            self.gets.append(path)
            if isinstance(answer, BaseException):
                raise answer
            return answer
        return super().get(url, timeout=timeout, **kw)


class _NotJson:
    """A 200 whose body isn't JSON (a proxy's page): requests' .json() raises."""
    ok, status_code, text = True, 200, "<html>Bad Gateway</html>"

    def json(self):
        raise requests.exceptions.JSONDecodeError("Expecting value", self.text, 0)


def _clear_caches():
    for name in ("_FIELD_SCHEMA_CACHE", "_SPOOLMAN_VERSION_CACHE"):
        getattr(spoolman_api, name, {}).clear()


@pytest.fixture
def wire(monkeypatch):
    """wire(fake): every Spoolman request on `fake`. requests.post is wired to
    fail the test: nothing here creates a record."""
    def _wire(fake):
        monkeypatch.setattr(spoolman_api.config_loader, "get_api_urls", lambda: (SM, "http://fb.test"))
        monkeypatch.setattr(spoolman_api.requests, "get", fake.get)
        monkeypatch.setattr(spoolman_api.requests, "patch", fake.patch)
        monkeypatch.setattr(spoolman_api.requests, "post", _no_post)
        monkeypatch.setattr(spoolman_api, "_RAW_EXTRAS_RETRY_DELAY_S", 0)
        _clear_caches()
        return fake
    yield _wire
    _clear_caches()


def _no_post(url, *a, **k):
    raise AssertionError(f"unexpected POST {url}")


@pytest.fixture
def logs(monkeypatch):
    calls = []
    monkeypatch.setattr(state, "add_log_entry", lambda msg, *a, **k: calls.append((msg, a[0] if a else None)))
    return calls


@pytest.fixture
def client():
    flask_app.config["TESTING"] = True
    with flask_app.test_client() as c:
        yield c


# ---------------------------------------------------------------------------
# D3: get_filament_answer, get_spool_answer's contract
# ---------------------------------------------------------------------------

def test_a_filament_spoolman_has_is_its_record_parsed(wire):
    fake = wire(_Spoolman())
    fake.add("filament", 7, {"nozzle_temp_max": '"225"'}, name="PLA Old")
    rec, answered = spoolman_api.get_filament_answer(7)
    assert answered is True
    assert rec["id"] == 7 and rec["name"] == "PLA Old"
    assert rec["extra"]["nozzle_temp_max"] == "225"     # parsed, as get_filament parses it
    assert fake.gets == ["/api/v1/filament/7"]


def test_a_filament_spoolman_has_no_record_of_is_its_404_body(wire):
    wire(_Spoolman())
    rec, answered = spoolman_api.get_filament_answer(99)
    assert answered is True
    assert rec == {"message": "No filament with ID 99 found."} and rec.get("id") is None


@pytest.mark.parametrize("status", [500, 502, 503])
def test_a_5xx_is_answered_and_unreadable_whatever_its_body(wire, status):
    fake = wire(_Spoolman())
    fake.add("filament", 7, name="PLA Old")
    fake.canned["/api/v1/filament/7"] = [_Resp(status, {"message": "database is locked"})]
    assert spoolman_api.get_filament_answer(7) == (None, True)


def test_a_body_that_isnt_json_is_answered_and_unreadable(wire):
    fake = wire(_Spoolman())
    fake.canned["/api/v1/filament/7"] = [_NotJson()]
    assert spoolman_api.get_filament_answer(7) == (None, True)


@pytest.mark.parametrize("raised", [
    TIMEOUT,
    requests.exceptions.ConnectionError(
        "HTTPConnectionPool(host='spoolman.test', port=7913): Max retries exceeded with url: /api/v1/filament/7"),
], ids=["timeout", "down"])
def test_no_answer_is_said(wire, raised):
    fake = wire(_Spoolman())
    fake.canned["/api/v1/filament/7"] = [raised]
    assert spoolman_api.get_filament_answer(7) == (None, False)


def test_a_spoolman_that_isnt_answering_at_all_is_no_answer(wire):
    fake = wire(_Spoolman())
    fake.down = True
    assert spoolman_api.get_filament_answer(7) == (None, False)


def test_the_read_is_one_get_of_the_filament_with_a_timeout(monkeypatch):
    seen = []

    def get(url, timeout=None, **kw):
        seen.append((url, timeout))
        return _Resp(200, {"id": 7})

    monkeypatch.setattr(spoolman_api.config_loader, "get_api_urls", lambda: (SM, "http://fb.test"))
    monkeypatch.setattr(spoolman_api.requests, "get", get)
    assert spoolman_api.get_filament_answer(7) == ({"id": 7}, True)
    assert len(seen) == 1 and seen[0][0] == f"{SM}/api/v1/filament/7" and seen[0][1]


# ---------------------------------------------------------------------------
# D4: bulk_set over a filament Spoolman has no record of, or couldn't send
# ---------------------------------------------------------------------------

ATTR_FIELDS = {"filament": [{"key": "filament_attributes", "field_type": "choice",
                             "multi_choice": True, "choices": ["Matte", "Silk"]}]}
NOT_READ = "couldn't read it from Spoolman, so nothing was changed on it"


def _attrs_fake():
    fake = _Spoolman(fields=copy.deepcopy(ATTR_FIELDS))
    fake.add("filament", 5, {"filament_attributes": json.dumps(["Matte"])}, name="PLA", material="PLA")
    return fake


def _attrs(fake, fid):
    return json.loads(fake.records["filament"][fid]["extra"]["filament_attributes"])


def _bulk(client, body):
    r = client.post("/api/filament_attributes/bulk_set", json=body)
    assert r.status_code == 200
    return r.get_json()


def test_a_remove_over_a_filament_spoolman_has_no_record_of_is_an_error_not_unchanged(client, wire, logs):
    fake = wire(_attrs_fake())
    body = _bulk(client, {"filament_ids": [99], "remove": ["Matte"]})
    assert body == {"success": False, "updated": 0, "unchanged": 0,
                    "errors": [{"id": 99, "msg": "filament not found"}]}
    assert fake.patches == []


def test_a_mixed_remove_counts_the_missing_filament_as_an_error(client, wire, logs):
    fake = wire(_attrs_fake())
    body = _bulk(client, {"filament_ids": [5, 99], "remove": ["Matte"]})
    assert body == {"success": True, "updated": 1, "unchanged": 0,
                    "errors": [{"id": 99, "msg": "filament not found"}]}
    assert [(entity, fid) for entity, fid, _body in fake.patches] == [("filament", 5)]
    assert _attrs(fake, 5) == []
    [(line, level)] = logs
    assert level == "WARNING" and "1 error(s)" in line


def test_an_add_over_a_filament_spoolman_has_no_record_of_is_not_found_and_tries_no_write(client, wire, logs):
    fake = wire(_attrs_fake())
    body = _bulk(client, {"filament_ids": [99], "add": ["Silk"]})
    assert body == {"success": False, "updated": 0, "unchanged": 0,
                    "errors": [{"id": 99, "msg": "filament not found"}]}
    assert fake.patches == []
    # One read: no write was tried, so no pre-merge read of it either.
    assert fake.gets.count("/api/v1/filament/99") == 1


@pytest.mark.parametrize("op", [{"remove": ["Matte"]}, {"add": ["Silk"]}], ids=["remove", "add"])
@pytest.mark.parametrize("answer", [
    _Resp(500, {"message": "database is locked"}),
    _Resp(503, {"message": "Service Unavailable"}),
    TIMEOUT,
], ids=["500", "503", "no answer"])
def test_a_filament_spoolman_couldnt_send_is_an_error_and_nothing_is_written(client, wire, logs, answer, op):
    """A 5xx body read as a filament with no attributes: a remove counted it
    "unchanged", and an add wrote ["Silk"] over its ["Matte"] once Spoolman
    answered the write's own read. No answer read as "filament not found"."""
    fake = wire(_attrs_fake())
    fake.canned["/api/v1/filament/5"] = [answer]
    body = _bulk(client, dict({"filament_ids": [5]}, **op))
    assert body == {"success": False, "updated": 0, "unchanged": 0,
                    "errors": [{"id": 5, "msg": NOT_READ}]}
    assert fake.patches == []
    assert _attrs(fake, 5) == ["Matte"]


def test_a_filament_spoolman_has_is_still_set(client, wire, logs):
    """The control: a readable filament gets the change, as before."""
    fake = wire(_attrs_fake())
    body = _bulk(client, {"filament_ids": [5], "add": ["Silk"]})
    assert body == {"success": True, "updated": 1, "unchanged": 0, "errors": []}
    assert _attrs(fake, 5) == ["Matte", "Silk"]


# ---------------------------------------------------------------------------
# D6: the Prusament link scan over a filament read that isn't the filament
# ---------------------------------------------------------------------------

PRUSAMENT_URL = "https://prusament.com/spool/17705/abcdef0123/"
CANONICAL = "https://prusament.com/spool/17705/abcdef0123"
TEMP_FIELDS = {"filament": [{"key": "nozzle_temp_max", "field_type": "text"},
                            {"key": "bed_temp_max", "field_type": "text"}],
               "spool": [{"key": "product_url", "field_type": "text"}]}
SET_TEMPS = {"settings_extruder_temp": 215, "settings_bed_temp": 55}
SET_EXTRA = {"nozzle_temp_max": '"225"', "bed_temp_max": '"60"'}
NOT_READ_SCAN = ("Couldn't read filament #7 from Spoolman, so its temps weren't changed. "
                 "Scan it again in a moment.")


def _prusament_fake(temps=SET_TEMPS, extra=SET_EXTRA):
    """Filament #7 (temps as given) and its spool #50, whose product link is the
    scanned label's, as Spoolman lists it: the filament nested in the spool."""
    fake = _Spoolman(fields=copy.deepcopy(TEMP_FIELDS))
    fil = fake.add("filament", 7, dict(extra), name="Prusament PLA Galaxy Black", material="PLA", **temps)
    fake.add("spool", 50, {"product_url": json.dumps(CANONICAL)}, filament=copy.deepcopy(fil),
             location="SHELF", archived=False)
    return fake


def _scanned_page(monkeypatch):
    """prusament.com's page for the spool, with temps that differ from #7's."""
    page = {"name": "Prusament PLA Galaxy Black", "material": "PLA",
            "settings_extruder_temp": 230, "settings_bed_temp": 65,
            "extra": {"nozzle_temp_max": "250", "bed_temp_max": "70"}}
    monkeypatch.setattr(external_parsers, "search_external", lambda source, url: [copy.deepcopy(page)])


def _scan(client):
    r = client.post("/api/identify_scan", json={"text": PRUSAMENT_URL, "source": "barcode"})
    assert r.status_code == 200
    return r.get_json()


@pytest.mark.parametrize("answer", [
    _Resp(500, {"message": "database is locked"}),
    _Resp(503, {"message": "Service Unavailable"}),
    TIMEOUT,
    _Resp(404, {"message": "No filament with ID 7 found."}),
], ids=["500", "503", "no answer", "404"])
def test_a_filament_read_that_isnt_the_filament_writes_nothing_and_says_so(client, wire, logs, monkeypatch,
                                                                          answer):
    """The review's case is the 500: its body read as the filament, all four set
    temps read as blank and were overwritten with prusament.com's. No answer fell
    back to the spool's embedded copy, which can be stale."""
    fake = wire(_prusament_fake())
    fake.canned["/api/v1/filament/7"] = [answer]
    _scanned_page(monkeypatch)
    res = _scan(client)

    assert res == {"type": "prusament_matched", "status": "error",
                   "spool_id": 50, "filament_id": 7, "msg": NOT_READ_SCAN}
    assert fake.patches == []
    fil = fake.records["filament"][7]
    assert {k: fil[k] for k in SET_TEMPS} == SET_TEMPS and fil["extra"] == SET_EXTRA
    warnings = [msg for msg, level in logs if level == "WARNING"]
    assert len(warnings) == 1 and "spool #50" in warnings[0] and "filament #7" in warnings[0], logs
    assert not [msg for msg, level in logs if level == "SUCCESS"]


def test_a_filament_read_that_is_the_filament_fills_its_blank_temps(client, wire, logs, monkeypatch):
    """The control: a filament read that answers backfills its blank temps through
    the real write, as before."""
    blank = {"settings_extruder_temp": None, "settings_bed_temp": None}
    fake = wire(_prusament_fake(temps=blank, extra={}))
    _scanned_page(monkeypatch)
    res = _scan(client)

    assert res["type"] == "prusament_matched" and res["status"] == "ok", res
    assert set(res["filled"]) == {"settings_extruder_temp", "settings_bed_temp", "nozzle_temp_max", "bed_temp_max"}
    fil = fake.records["filament"][7]
    assert (fil["settings_extruder_temp"], fil["settings_bed_temp"]) == (230, 65)
    assert json.loads(fil["extra"]["nozzle_temp_max"]) == "250"
