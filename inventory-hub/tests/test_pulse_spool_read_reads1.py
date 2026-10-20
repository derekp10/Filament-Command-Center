"""Group 52 review, finding reads-1: a heartbeat whose shared spool read fails
says so, beside its sections, so the page never draws "couldn't read" as empty.

The dashboard heartbeat reads Spoolman's spool list ONCE per tick
(spoolman_api.SpoolListRead, Group 52.1a). When that read times out, the manage
section already answers read_ok: false, but the locations section still counts
every box 0/N and the printer_status section still answers every head with
item: None, and nothing told the page why: the Printer Status tiles flipped to
empty and the Locations table to 0/4 until the next good tick. Now:

  - the pulse carries `spool_read: {ok, error}`, a SIBLING key (never one
    inside printer_status, whose every key the page reads as a printer name),
    only on a tick whose sections read the list;
  - the sections keep their shape, so a page that ignores the new key draws
    exactly what it drew before;
  - the plain /api/locations answer (a bare list every caller iterates) says
    the same in its X-FCC-Spool-Read header.

Hermetic: Spoolman's HTTP API is faked at `requests.get`, locations.json, the
printer map and the PrusaLink probe are patched (the harness of
test_spoolman_read_load_52.py), so nothing reaches dev. The page half is
test_pulse_spool_read_reads1_page.py.

Proven RED on the bundle tip a5d8cb8 (no `spool_read`, no header), except the
two controls named in their docstrings.
"""
from __future__ import annotations

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import app as app_module  # noqa: E402
import locations_db  # noqa: E402
from test_spoolman_read_load_52 import (  # noqa: E402
    ALL_SPOOL_SECTIONS, PRINTER_MAP, SPOOL_LIST, HttpSpoolman, _run)

HEADER = "X-FCC-Spool-Read"


@pytest.fixture
def client():
    app_module.app.config["TESTING"] = True
    return app_module.app.test_client()


def _pulse(client, sm, include, manage_id=None, printer_map=PRINTER_MAP):
    url = f"/api/dashboard_pulse?include={include}"
    if manage_id:
        url += f"&manage_id={manage_id}"
    r = _run(sm, lambda: client.get(url), printer_map=printer_map)
    assert r.status_code == 200
    return r.get_json()


def test_a_failed_read_says_so_beside_sections_of_the_same_shape(client):
    """The heart of reads-1: Spoolman times out on the tick's one read. The
    tick says so in `spool_read`, and every section keeps the shape it had, so
    a page that ignores the new key keeps today's behaviour."""
    sm = HttpSpoolman(down={SPOOL_LIST})
    body = _pulse(client, sm, ALL_SPOOL_SECTIONS, manage_id="TST-DB-1")

    assert sm.count(SPOOL_LIST) == 1, sm.gets          # still one read per tick
    read = body["spool_read"]
    assert set(read) == {"ok", "error"} and read["ok"] is False, read
    assert "Spoolman didn't answer" in read["error"] and "timed out" in read["error"], read

    # A sibling key: printer_status keeps only printer names, each the usual
    # {toolheads, state}, every head empty because nothing was read.
    ps = body["printer_status"]
    assert set(ps) == {"Test Printer"}, ps
    assert set(ps["Test Printer"]) == {"toolheads", "state"}, ps
    assert ps["Test Printer"]["toolheads"] == [
        {"id": "TSTP-1", "position": 0, "item": None, "unbound": False, "loaded_count": 0}], ps

    # The locations section is still the bare list of rows (every count 0).
    assert isinstance(body["locations"], list), body["locations"]
    rows = {r["LocationID"]: r for r in body["locations"]}
    assert rows["TST-DB-1"]["Occupancy"] == "0/4" and rows["TST-DB-1"]["OccupancyRaw"] == 0, rows
    assert rows["Unassigned"]["Occupancy"] == "0 items", rows

    # manage and label_backlog already said it (Group 52.1a / 52.1b), unchanged.
    assert body["manage"]["read_ok"] is False and "contents" not in body["manage"], body["manage"]
    assert body["label_backlog"]["read_ok"] is False, body["label_backlog"]
    assert set(body) == {"locations", "manage", "printer_status", "label_backlog", "spool_read"}, set(body)


def test_a_good_read_says_ok(client):
    sm = HttpSpoolman()
    body = _pulse(client, sm, "locations,printer_status")
    assert body["spool_read"] == {"ok": True, "error": None}, body.get("spool_read")
    assert sm.count(SPOOL_LIST) == 1, sm.gets
    heads = body["printer_status"]["Test Printer"]["toolheads"]
    assert [(h["id"], (h["item"] or {}).get("id")) for h in heads] == [("TSTP-1", 902)], heads


@pytest.mark.parametrize("section", ["locations", "printer_status", "label_backlog"])
def test_any_one_spool_section_carries_the_outcome(client, section):
    """Whichever section asks first does the read; the outcome rides along."""
    for down, ok in ((set(), True), ({SPOOL_LIST}, False)):
        body = _pulse(client, HttpSpoolman(down=down), section)
        assert body["spool_read"]["ok"] is ok, (section, body)


@pytest.mark.parametrize("include, manage_id, printer_map", [
    ("buffer", None, PRINTER_MAP),          # no spool section
    ("buffer,manage", None, PRINTER_MAP),   # a manage section with no id asks nothing
    ("printer_status", None, {}),           # no printers: the section reads nothing
])
def test_a_tick_that_reads_nothing_carries_no_spool_read(client, include, manage_id, printer_map):
    """Only a tick whose sections read the list says how the read went: a
    page reading a key-less tick draws as before. A control (passes on the
    base too, which never sends it)."""
    sm = HttpSpoolman(down={SPOOL_LIST})
    body = _pulse(client, sm, include, manage_id=manage_id, printer_map=printer_map)
    assert sm.gets.count(SPOOL_LIST) == 0, sm.gets
    assert "spool_read" not in body, body


def test_the_locations_answer_says_in_a_header_whether_its_counts_were_read(client):
    """The page's own /api/locations fetch (every Location List open, every
    sort) gets the same answer, in a header: the body stays the bare list."""
    ok = _run(HttpSpoolman(), lambda: client.get("/api/locations"))
    assert ok.status_code == 200 and ok.headers.get(HEADER) == "ok", dict(ok.headers)
    down = _run(HttpSpoolman(down={SPOOL_LIST}), lambda: client.get("/api/locations"))
    assert down.status_code == 200 and down.headers.get(HEADER) == "failed", dict(down.headers)
    body = down.get_json()
    assert isinstance(body, list), body
    assert {r["LocationID"] for r in body} >= {"Unassigned", "TST-DB-1", "TSTP-1", "UNKNOWN"}, body


def test_the_header_leaves_the_pulse_locations_section_unchanged(client):
    """The pulse's locations section is the same list the plain route answers
    (the header never leaks into the body), read ok or not. A control (passes on
    the base too)."""
    for down in (set(), {SPOOL_LIST}):
        body = _pulse(client, HttpSpoolman(down=down), "locations")
        alone = _run(HttpSpoolman(down=down), lambda: client.get("/api/locations")).get_json()
        assert body["locations"] == alone


def test_a_corrupt_locations_file_still_reads_nothing_and_says_nothing(client):
    """locations.json is loaded before Spoolman is read, so a corrupt file
    answers its error with no read, and so no `spool_read`. A control (passes
    on the base too)."""
    err = locations_db.LocationsCorruptError("data/locations.json", json.JSONDecodeError("bad", "{", 1))

    def corrupt(*a, **k):
        raise err

    sm = HttpSpoolman()
    r = _run(sm, lambda: client.get("/api/dashboard_pulse?include=locations"), load=corrupt)
    body = r.get_json()
    assert body["locations"]["status"] == 500 and "spool_read" not in body, body
    assert sm.count(SPOOL_LIST) == 0, sm.gets
