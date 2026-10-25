"""Group 52 (Spoolman read load & honest empties), the backend half.

Hermetic: Spoolman's HTTP API is faked at `requests.get` (the shared module every
reader resolves, `spoolman_api.requests` included), locations.json, the printer
map and the PrusaLink probe are patched, so nothing reaches dev.

  52.1a  one spool-list read per dashboard heartbeat, shared by the locations,
         manage, printer_status and label_backlog sections; the backlog count
         rides the heartbeat (only flagged records, filtered in FCC), and the
         backlog list refuses a partial read instead of showing it as complete;
  52.1b  the heartbeat's manage section tells "couldn't read" (read_ok: false,
         no contents) from "empty" (contents: []);
  52.1c  /api/get_contents?ids=A&ids=B answers several locations from one read,
         each list identical to /api/get_contents?id=<that id>;
  52.2   the pre-merge extras read gets a second try after a short pause, still
         through `spoolman_api.requests`; two failures refuse the write as before.

New symbols are looked up inside the tests, so the file imports on the base and
each test fails there for its own reason (proven on 52741e6).
"""
from __future__ import annotations

import copy
import inspect
import json
import os
import re
import sys
from contextlib import ExitStack
from unittest.mock import MagicMock, patch
from urllib.parse import urlsplit

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import app as app_module  # noqa: E402
import config_loader  # noqa: E402
import locations_db  # noqa: E402
import prusalink_api  # noqa: E402
import spoolman_api  # noqa: E402

SPOOL_LIST = "/api/v1/spool"
FILAMENT_LIST = "/api/v1/filament"

ROWS = [
    {"LocationID": "TST", "Name": "Test Room", "Type": "Room", "Max Spools": "0"},
    {"LocationID": "TST-DB-1", "Name": "Test box", "Type": "Dryer Box", "Max Spools": "4",
     "parent_id": "TST", "extra": {"slot_targets": {"1": "TSTP-1"}}},
    {"LocationID": "TST-DB-2", "Name": "Empty box", "Type": "Dryer Box", "Max Spools": "4",
     "parent_id": "TST"},
    {"LocationID": "TSTP", "Name": "Test Printer", "Type": "Printer", "Max Spools": "0",
     "toolheads": [{"location_id": "TSTP-1", "position": 0}]},
    {"LocationID": "TSTP-1", "Name": "Head 1", "Type": "Tool Head", "Max Spools": "1",
     "parent_id": "TSTP"},
]
PRINTER_MAP = {"TSTP-1": {"printer_name": "Test Printer", "position": 0}}


def _filament(fid, extra=None):
    return {"id": fid, "name": f"Fil {fid}", "material": "PLA", "color_hex": "112233",
            "vendor": {"id": 1, "name": "FCC Test"}, "registered": f"2026-01-0{fid % 9 + 1}",
            "extra": dict(extra or {})}


def _spool(sid, location, extra=None, archived=False):
    """A spool as Spoolman's API sends it: text extras JSON-encoded."""
    return {"id": sid, "location": location, "archived": archived,
            "remaining_weight": 500.0, "initial_weight": 1000.0, "used_weight": 500.0,
            "registered": f"2026-02-0{sid % 9 + 1}",
            "filament": _filament(70), "extra": dict(extra or {})}


SPOOLS = [
    # stored in TST-DB-1 slot 2, waiting for its label
    _spool(901, "TST-DB-1", {"container_slot": '"2"', "needs_label_print": "true"}),
    # loaded on TSTP-1, deployed from TST-DB-1 slot 1 (a ghost in the box)
    _spool(902, "TSTP-1", {"physical_source": '"TST-DB-1"', "physical_source_slot": '"1"',
                           "needs_label_print": "false"}),
    # on the workbench
    _spool(903, "", {}),
    # archived: Spoolman's default list leaves it out
    _spool(904, "TST-DB-1", {"container_slot": '"3"', "needs_label_print": "true"}, archived=True),
]
FILAMENTS = [_filament(71, {"needs_label_print": "true"}),
             _filament(72, {"needs_label_print": "false"}),
             _filament(73)]


def _resp(status, body):
    r = MagicMock()
    r.ok = status < 400
    r.status_code = status
    r.json.return_value = copy.deepcopy(body)
    r.text = json.dumps(body)
    return r


class HttpSpoolman:
    """Spoolman's HTTP API at `requests.get`. Its list endpoints answer EVERY
    record whatever the query says (they ignore an `extra=` filter, like the
    real Spoolman 0.27); `down` holds the paths that time out. Every GET is
    recorded by path."""

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
            return _resp(200, [s for s in self.spools if archived_too or not s.get("archived")])
        if path == FILAMENT_LIST:
            return _resp(200, self.filaments)
        if path == "/api/v1/location":
            return _resp(200, [])
        m = re.fullmatch(r"/api/v1/spool/(\d+)", path)
        if m:
            rec = next((s for s in self.spools if s["id"] == int(m.group(1))), None)
            return _resp(200, rec) if rec else _resp(404, {"message": "not found"})
        return _resp(404, {"message": "not found"})

    def count(self, path):
        return self.gets.count(path)


@pytest.fixture
def client():
    app_module.app.config["TESTING"] = True
    return app_module.app.test_client()


def _run(sm, call, rows=ROWS, printer_map=PRINTER_MAP, load=None):
    load = load or (lambda *a, **k: copy.deepcopy(rows))
    with ExitStack() as stack:
        for p in (
            patch.object(spoolman_api.requests, "get", side_effect=sm.get),
            patch.object(locations_db, "load_locations_list", side_effect=load),
            patch.object(locations_db, "get_active_printer_map", return_value=copy.deepcopy(printer_map)),
            patch.object(config_loader, "get_api_urls", return_value=("http://sm", "http://fb")),
            patch.object(config_loader, "load_config", return_value={}),
            patch.object(prusalink_api, "get_printer_state", return_value=None),
        ):
            stack.enter_context(p)
        return call()


def _pulse(client, sm, include, manage_id=None):
    url = f"/api/dashboard_pulse?include={include}"
    if manage_id:
        url += f"&manage_id={manage_id}"
    r = _run(sm, lambda: client.get(url))
    assert r.status_code == 200
    return r.get_json()


ALL_SPOOL_SECTIONS = "locations,manage,printer_status,label_backlog"


# ---------------------------------------------------------------------------
# 52.1a: one spool-list read per heartbeat
# ---------------------------------------------------------------------------

def test_a_heartbeat_reads_the_spool_list_once_for_every_section(client):
    """The locations table, an open Location Manager and the Printer Status
    widget each read Spoolman's whole spool list (213 KB on dev), so a busy tick
    read it three times, plus twice more for the backlog button's own poll. Now
    one spool read and one filament read serve every section. RED on 52741e6:
    three spool reads."""
    sm = HttpSpoolman()
    body = _pulse(client, sm, ALL_SPOOL_SECTIONS, manage_id="TST-DB-1")

    assert sm.count(SPOOL_LIST) == 1, sm.gets
    assert sm.count(FILAMENT_LIST) == 1, sm.gets

    # Every section still answers what its renderer reads.
    manage = body["manage"]
    assert manage["id"] == "TST-DB-1" and manage["read_ok"] is True, manage
    assert sorted((c["id"], c["is_ghost"], c["slot"]) for c in manage["contents"]) == [
        (901, False, "2"), (902, True, "1")], manage
    heads = body["printer_status"]["Test Printer"]["toolheads"]
    assert [(h["id"], (h["item"] or {}).get("id"), h["unbound"]) for h in heads] == [("TSTP-1", 902, False)], heads
    rows = {r["LocationID"]: r for r in body["locations"]}
    assert rows["TST-DB-1"]["Occupancy"] == "2/4", rows["TST-DB-1"]
    assert rows["TSTP-1"]["Occupancy"] == "1/1", rows["TSTP-1"]
    assert rows["Unassigned"]["Occupancy"] == "1 items", rows["Unassigned"]
    assert body["label_backlog"] == {"read_ok": True, "count": 2, "spools": 1, "filaments": 1}, body


def test_the_shared_read_matches_each_sections_own_read(client):
    """Each section answers exactly what it answered when it read Spoolman
    itself (the standalone /api/locations and /api/get_contents)."""
    sm = HttpSpoolman()
    body = _pulse(client, sm, ALL_SPOOL_SECTIONS, manage_id="TST-DB-1")
    alone = HttpSpoolman()
    locations = _run(alone, lambda: client.get("/api/locations")).get_json()
    contents = _run(alone, lambda: client.get("/api/get_contents?id=TST-DB-1")).get_json()
    assert body["locations"] == locations
    assert body["manage"]["contents"] == contents


def test_a_heartbeat_with_no_spool_section_reads_nothing(client):
    """Nothing is read until a section asks (a manage section with no id
    asks nothing). Passes on the base too: a control."""
    sm = HttpSpoolman()
    body = _pulse(client, sm, "buffer,manage")
    assert sm.gets == [], sm.gets
    assert set(body) == {"buffer"}, body


def test_a_corrupt_locations_file_answers_without_reading_spoolman(client):
    """The locations section loads locations.json before it reads Spoolman, so
    a corrupt file answers its error and costs no read."""
    sm = HttpSpoolman()
    err = locations_db.LocationsCorruptError("data/locations.json", json.JSONDecodeError("bad", "{", 1))

    def corrupt(*a, **k):
        raise err

    r = _run(sm, lambda: client.get("/api/dashboard_pulse?include=locations"), load=corrupt)
    body = r.get_json()
    assert body["locations"]["status"] == 500, body
    assert sm.count(SPOOL_LIST) == 0, sm.gets


def test_a_failed_read_is_tried_once_per_heartbeat_and_no_section_draws_it_as_empty(client):
    """Spoolman times out: the tick tries ONE read (it used to try three, each
    up to 5 s), the manage section says it couldn't read instead of answering an
    empty box, the backlog count says so too (the page keeps the count it
    shows), the locations table keeps its rows (zero counts, the old quirk) and
    the printer heads stay empty, as the fail-open read left them. RED on
    52741e6: three attempts and `contents: []`.

    PIN UPDATED DELIBERATELY (Group 52 review, reads-1, 2026-10-19): those
    zero counts and empty heads mean "nothing was read", and the tick now says
    so beside them in `spool_read` (never inside printer_status), so the page
    keeps the counts and tiles it drew. The sections themselves are unchanged
    (test_pulse_spool_read_reads1.py pins the rest)."""
    sm = HttpSpoolman(down={SPOOL_LIST})
    body = _pulse(client, sm, ALL_SPOOL_SECTIONS, manage_id="TST-DB-1")

    assert sm.count(SPOOL_LIST) == 1, sm.gets
    assert sm.count(FILAMENT_LIST) == 0, "no filament read once the spool read failed"
    manage = body["manage"]
    assert manage["read_ok"] is False and "contents" not in manage, manage
    assert manage["id"] == "TST-DB-1" and "Spoolman" in manage["read_error"], manage
    assert body["label_backlog"]["read_ok"] is False and "count" not in body["label_backlog"], body
    rows = {r["LocationID"]: r for r in body["locations"]}
    assert set(rows) >= {"TST-DB-1", "TSTP-1", "Unassigned", "UNKNOWN"}, rows
    heads = body["printer_status"]["Test Printer"]["toolheads"]
    assert [h["item"] for h in heads] == [None], heads
    assert body["spool_read"]["ok"] is False and "Spoolman" in body["spool_read"]["error"], body
    assert "spool_read" not in body["printer_status"], body["printer_status"]


def test_the_manage_section_tells_an_empty_box_from_a_failed_read(client):
    """52.1b: an empty box is `contents: []` with read_ok true; the page draws
    it EMPTY. RED on 52741e6: no read_ok."""
    body = _pulse(client, HttpSpoolman(), "manage", manage_id="tst-db-2")
    assert body["manage"] == {"id": "TST-DB-2", "contents": [], "read_ok": True}, body


def test_the_backlog_count_counts_only_flagged_records(client):
    """Spoolman ignores `extra=` filters and lists every record; the count is
    the flagged non-archived spools plus the flagged filaments, the same records
    /api/print_queue/pending lists (archived #904 is flagged but not listed)."""
    sm = HttpSpoolman()
    body = _pulse(client, sm, "label_backlog")
    pending = _run(HttpSpoolman(), lambda: client.get("/api/print_queue/pending?filter=all")).get_json()
    assert pending["success"] is True
    assert body["label_backlog"]["count"] == len(pending["items"]) == 2, (body, pending)
    assert sorted((i["type"], i["id"]) for i in pending["items"]) == [("filament", 71), ("spool", 901)]


def test_the_backlog_count_keeps_quiet_when_the_filaments_cant_be_read(client):
    sm = HttpSpoolman(down={FILAMENT_LIST})
    body = _pulse(client, sm, "label_backlog")
    assert body["label_backlog"]["read_ok"] is False and "count" not in body["label_backlog"], body
    assert "filament" in body["label_backlog"]["read_error"], body


@pytest.mark.parametrize("down, which", [(SPOOL_LIST, "spool"), (FILAMENT_LIST, "filament")])
def test_the_backlog_list_refuses_a_partial_read(client, down, which):
    """A list Spoolman didn't answer was skipped, so the open backlog showed the
    other list as the whole backlog, and the 🏷️ button counted it. RED on
    52741e6: success with half the records."""
    sm = HttpSpoolman()
    sm_get = sm.get

    def get(url, *a, **k):
        if urlsplit(str(url)).path == down:
            sm.gets.append(down)
            return _resp(503, {"message": "busy"})
        return sm_get(url, *a, **k)

    sm.get = get
    body = _run(sm, lambda: client.get("/api/print_queue/pending?filter=all")).get_json()
    assert body["success"] is False and which in body["msg"], body


# ---------------------------------------------------------------------------
# 52.1c: one batched contents read
# ---------------------------------------------------------------------------

def test_get_contents_ids_reads_once_for_every_location(client):
    """The Quick-Swap grid read the whole spool list once per feeding box.
    `ids` answers them all from one read, each list exactly what
    /api/get_contents?id=<that id> answers. RED on 52741e6: a bare []."""
    sm = HttpSpoolman()
    r = _run(sm, lambda: client.get("/api/get_contents?ids=TST-DB-1&ids=TSTP-1&ids=tst-db-2&ids=Unassigned"))
    assert r.status_code == 200
    body = r.get_json()
    assert sm.count(SPOOL_LIST) == 1, sm.gets
    assert body["read_ok"] is True and body["read_error"] is None, body
    # Keyed by the ids as sent (Flask's JSON sorts the keys; order means nothing).
    assert set(body["contents"]) == {"TST-DB-1", "TSTP-1", "tst-db-2", "Unassigned"}, body
    for lid, items in body["contents"].items():
        alone = _run(HttpSpoolman(), lambda: client.get(f"/api/get_contents?id={lid}")).get_json()
        assert items == alone, lid
    assert [c["id"] for c in body["contents"]["TSTP-1"]] == [902]
    assert body["contents"]["tst-db-2"] == []


def test_get_contents_ids_says_when_spoolman_didnt_answer(client):
    """One read serves every box, so a blip leaves FCC unable to tell any of
    them: read_ok false, never a list of empty boxes."""
    sm = HttpSpoolman(down={SPOOL_LIST})
    r = _run(sm, lambda: client.get("/api/get_contents?ids=TST-DB-1&ids=TST-DB-2"))
    assert r.status_code == 200
    body = r.get_json()
    assert body["read_ok"] is False and body["contents"] == {}, body
    assert "Spoolman" in body["read_error"], body
    assert sm.count(SPOOL_LIST) == 1, sm.gets


def test_get_contents_ids_with_only_blank_ids_reads_nothing(client):
    sm = HttpSpoolman()
    body = _run(sm, lambda: client.get("/api/get_contents?ids=&ids=%20")).get_json()
    assert body == {"read_ok": True, "read_error": None, "contents": {}}, body
    assert sm.gets == [], sm.gets


def test_single_id_get_contents_is_unchanged(client):
    """Control: one id still answers a bare list, and strict=1 a 502."""
    sm = HttpSpoolman()
    body = _run(sm, lambda: client.get("/api/get_contents?id=TST-DB-1")).get_json()
    assert isinstance(body, list) and sorted(c["id"] for c in body) == [901, 902], body
    down = HttpSpoolman(down={SPOOL_LIST})
    assert _run(down, lambda: client.get("/api/get_contents?id=TST-DB-1")).get_json() == []
    assert _run(down, lambda: client.get("/api/get_contents?id=TST-DB-1&strict=1")).status_code == 502


# ---------------------------------------------------------------------------
# 52.2: the pre-merge extras read gets a second try
# ---------------------------------------------------------------------------

class ExtrasSpoolman:
    """The extras read's Spoolman: `script` says what each GET of the record
    does in turn ('timeout', a status code, or 'ok'); PATCHes are kept."""

    def __init__(self, script, extra=None):
        self.script = list(script)
        self.extra = dict(extra or {"nozzle_temp_max": '"225"', "sheet_link": '"https://x"'})
        self.gets = []
        self.patches = []

    def get(self, url, *a, **k):
        self.gets.append(urlsplit(str(url)).path)
        step = self.script.pop(0) if self.script else "ok"
        if step == "timeout":
            raise spoolman_api.requests.exceptions.ConnectTimeout("connect timed out (test)")
        if step != "ok":
            return _resp(int(step), {"message": "error"})
        return _resp(200, {"id": 7, "extra": dict(self.extra)})

    def patch(self, url, json=None, **k):
        self.patches.append((urlsplit(str(url)).path, copy.deepcopy(json)))
        return _resp(200, {"id": 7})


@pytest.fixture
def no_pause(monkeypatch):
    monkeypatch.setattr(spoolman_api, "_RAW_EXTRAS_RETRY_DELAY_S", 0, raising=False)


def _write_filament(sm, data):
    with patch.object(spoolman_api.requests, "get", side_effect=sm.get), \
         patch.object(spoolman_api.requests, "patch", side_effect=sm.patch), \
         patch.object(config_loader, "get_api_urls", return_value=("http://sm", "http://fb")):
        return spoolman_api.update_filament(7, data)


@pytest.mark.usefixtures("no_pause")
def test_one_blip_on_the_extras_read_no_longer_refuses_the_write():
    """The read failed once and the write was refused (Group 36's guard). Now
    the second try reads the extras and the merged PATCH goes out, siblings
    kept. RED on 52741e6: refused after one GET."""
    sm = ExtrasSpoolman(["timeout", "ok"])
    res = _write_filament(sm, {"extra": {"filament_attributes": '["Basic"]'}})
    assert res is not None, spoolman_api.LAST_SPOOLMAN_ERROR
    assert sm.gets == ["/api/v1/filament/7", "/api/v1/filament/7"], sm.gets
    assert len(sm.patches) == 1, sm.patches
    sent = sm.patches[0][1]["extra"]
    assert sent["nozzle_temp_max"] == '"225"' and sent["sheet_link"] == '"https://x"', sent
    assert sent["filament_attributes"] == '["Basic"]', sent


@pytest.mark.usefixtures("no_pause")
def test_a_server_error_is_retried_too():
    sm = ExtrasSpoolman(["503", "ok"])
    assert _write_filament(sm, {"extra": {"filament_attributes": '["Basic"]'}}) is not None
    assert len(sm.gets) == 2 and len(sm.patches) == 1, (sm.gets, sm.patches)


@pytest.mark.usefixtures("no_pause")
def test_two_failures_refuse_the_write_as_before():
    """RED on 52741e6 only by the count: it gave up after one GET."""
    sm = ExtrasSpoolman(["timeout", "timeout"])
    assert _write_filament(sm, {"extra": {"filament_attributes": '["Basic"]'}}) is None
    assert sm.gets == ["/api/v1/filament/7", "/api/v1/filament/7"], sm.gets
    assert sm.patches == [], "no partial PATCH may reach Spoolman"
    assert "refusing to PATCH" in (spoolman_api.LAST_SPOOLMAN_ERROR or "")


@pytest.mark.usefixtures("no_pause")
def test_an_answer_is_not_asked_again():
    """A 404 is an answer: a deleted record stays deleted. One GET, refused.
    Passes on the base too: a control."""
    sm = ExtrasSpoolman(["404"])
    assert _write_filament(sm, {"extra": {"filament_attributes": '["Basic"]'}}) is None
    assert sm.gets == ["/api/v1/filament/7"], sm.gets
    assert sm.patches == []


@pytest.mark.usefixtures("no_pause")
def test_the_spool_write_path_retries_through_the_same_seam():
    """update_spool's merge reads through `_get_raw_extras` too (its own
    get_spool is patched out here so only the extras read hits HTTP)."""
    sm = ExtrasSpoolman(["timeout", "ok"], extra={"container_slot": '"2"', "needs_label_print": "true"})
    with patch.object(spoolman_api, "get_spool", return_value={"id": 7, "used_weight": 10, "initial_weight": 1000}), \
         patch.object(spoolman_api.requests, "get", side_effect=sm.get), \
         patch.object(spoolman_api.requests, "patch", side_effect=sm.patch), \
         patch.object(config_loader, "get_api_urls", return_value=("http://sm", "http://fb")):
        res = spoolman_api.update_spool(7, {"extra": {"needs_label_print": False}})
    assert res is not None, spoolman_api.LAST_SPOOLMAN_ERROR
    assert sm.gets == ["/api/v1/spool/7", "/api/v1/spool/7"], sm.gets
    assert sm.patches and sm.patches[0][1]["extra"]["container_slot"] == '"2"', sm.patches


def test_the_retry_waits_a_short_pause_between_tries(monkeypatch):
    """Two attempts, one pause of _RAW_EXTRAS_RETRY_DELAY_S (half a second)."""
    pauses = []
    monkeypatch.setattr(spoolman_api.time, "sleep", lambda s: pauses.append(s))
    sm = ExtrasSpoolman(["timeout", "timeout"])
    assert _write_filament(sm, {"extra": {"x": '"y"'}}) is None
    assert pauses == [spoolman_api._RAW_EXTRAS_RETRY_DELAY_S] and 0 < pauses[0] <= 1, pauses


def test_the_extras_read_stays_on_the_spoolman_api_requests_seam():
    """`http_retry` resolves `requests` from its own module, which the tests'
    `spoolman_api.requests` patches would not intercept (CLAUDE.md, Group 36)."""
    src = inspect.getsource(spoolman_api._get_raw_extras)
    assert "requests.get(" in src and "http_retry" not in src.split('"""')[-1], src
