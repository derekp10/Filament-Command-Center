"""Group 63.5: a save whose answer was lost is judged from one read.

update_spool's PATCH timeout is a READ timeout, so a weigh whose answer was lost may
have landed. Two reads used to judge it: update_spool's own re-read
(_after_unanswered_write, for an archive or an un-archive: it wrote the 📦 / 📤
line from it) and /api/spool/update's read-back (Group 54 review R5-2: its
answer). So:
  - the answer came from a record that carried no `fcc_warning`, and a refill's
    42.3c warning ("#57 is back in stock, but … holds #99 …") reached only the
    Activity Log (R6-4); since Group 63.1 the same is true of the refill question;
  - every lost archive or refill read the spool twice;
  - a record that changed between the two reads could make the 📦 line and the
    answer disagree, or leave the line missing (R6-5).
Now update_spool's re-read is the one read (get_spool_answer, judged by
spoolman_api.landed_as_sent, moved from routes_inventory), its verdict kept per
thread for the caller (spoolman_api.take_unanswered), and the route answers from
it, its warning and question included. A write that neither archives nor
un-archives is still read back by the route itself.

The REAL route and update_spool over tests/spoolman_extra_fake.SpoolmanHTTPFake,
whose PATCH lands and then loses its answer (a ReadTimeout). Tests marked RED fail
on e1b22f4 (the branch's base).
"""
from __future__ import annotations

import copy
import os
import sys

import pytest
import requests

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import spoolman_api as sm_api  # noqa: E402
import state  # noqa: E402
from spoolman_extra_fake import SpoolmanHTTPFake  # noqa: E402

TIMEOUT = "HTTPConnectionPool(host='sm.test', port=80): Read timed out. (read timeout=15)"
SPOOL_FIELDS = [
    {"key": k, "field_type": "text", "name": k} for k in (
        "container_slot", "physical_source", "physical_source_slot",
        "fcc_pre_archive_location", "fcc_pre_box_location", "fcc_pre_audit_location")
]
PRINTER_MAP = {"XL-1": {"printer_name": "XL", "position": 0}}
ROWS = [
    {"LocationID": "LR", "Type": "Room", "Max Spools": "0"},
    {"LocationID": "XL", "Type": "Printer", "Max Spools": "0", "parent_id": "LR",
     "toolheads": [{"location_id": "XL-1", "position": 0}]},
    {"LocationID": "XL-1", "Type": "Tool Head", "Max Spools": "1", "parent_id": "XL"},
    {"LocationID": "PM-DB-2", "Type": "Dryer Box", "Max Spools": "1", "parent_id": "LR",
     "extra": {"slot_targets": {}}},
    {"LocationID": "CR-SHELF", "Type": "Shelf", "Max Spools": "0", "parent_id": "LR"},
]


@pytest.fixture(autouse=True)
def _isolate_state():
    prior = (state.RECENT_LOGS, state.UNDO_STACK, state.GLOBAL_BUFFER)
    state.RECENT_LOGS, state.UNDO_STACK, state.GLOBAL_BUFFER = [], [], []
    try:
        yield
    finally:
        state.RECENT_LOGS, state.UNDO_STACK, state.GLOBAL_BUFFER = prior


def _lines(icon):
    # A line with a swatch starts with its <span>: matched by what it holds.
    return [e["msg"] for e in state.RECENT_LOGS if icon in str(e.get("msg", ""))]


@pytest.fixture
def lost(monkeypatch):
    """A Spoolman 0.27 whose spool PATCH lands, then loses its answer. `after_patch`
    holds the GET paths read after it; `on_read(n, fake)` runs before the n-th of
    them is answered (1-based), so a record can change between two reads."""
    fake = SpoolmanHTTPFake(version="0.27.0", fields={"spool": copy.deepcopy(SPOOL_FIELDS)})
    fake.after_patch = None
    fake.on_read = None
    real_get, real_patch = fake.get, fake.patch

    def get_(url, timeout=None, **kw):
        if fake.after_patch is not None and "/api/v1/spool/" in str(url):
            fake.after_patch.append(str(url))
            if fake.on_read:
                fake.on_read(len(fake.after_patch), fake)
        return real_get(url, timeout=timeout, **kw)

    def patch_(url, json=None, timeout=None, **kw):  # noqa: A002
        real_patch(url, json=json, timeout=timeout, **kw)
        fake.after_patch = []
        raise requests.exceptions.ReadTimeout(TIMEOUT)

    monkeypatch.setattr(sm_api.config_loader, "get_api_urls", lambda: ("http://sm.test", "http://fb"))
    monkeypatch.setattr(sm_api.requests, "get", get_)
    monkeypatch.setattr(sm_api.requests, "patch", patch_)
    monkeypatch.setattr(sm_api.locations_db, "get_active_printer_map", lambda *a, **k: PRINTER_MAP)
    monkeypatch.setattr(sm_api.locations_db, "load_locations_list", lambda *a, **k: copy.deepcopy(ROWS))
    monkeypatch.setattr(sm_api.locations_db, "detach_single_slot_box", lambda box, head: False)
    for name in ("_FIELD_SCHEMA_CACHE", "_SPOOLMAN_VERSION_CACHE"):
        getattr(sm_api, name, {}).clear()
    yield fake
    for name in ("_FIELD_SCHEMA_CACHE", "_SPOOLMAN_VERSION_CACHE"):
        getattr(sm_api, name, {}).clear()


@pytest.fixture
def client():
    import app as app_module
    app_module.app.config["TESTING"] = True
    return app_module.app.test_client()


def _save(client, updates):
    return client.post("/api/spool/update", json={"id": 57, "updates": updates}).get_json()


def _archived(fake, note):
    fake.add("spool", 57, {"fcc_pre_archive_location": f'"{note}"'},
             location="", initial_weight=1000.0, used_weight=1000.0, archived=True)


# ---- the warning and the question reach the answer ---------------------------------------------------

def test_a_refill_whose_answer_was_lost_but_landed_still_hands_on_its_warning(lost, client):
    """RED on e1b22f4: the answer came from the route's own read-back, which carries
    no fcc_warning. PM-DB-2 (a single-slot dryer box) holds #42 now, so #57 is
    Unassigned, and the weigh screen toasts why."""
    _archived(lost, "PM-DB-2")
    lost.add("spool", 42, {}, location="PM-DB-2", initial_weight=1000.0, used_weight=100.0, archived=False)
    body = _save(client, {"used_weight": 600})
    assert body["status"] == "success", body
    assert body.get("warning", "").startswith("#57 is back in stock (400 g), but PM-DB-2 now holds #42"), body
    assert lost.records["spool"][57]["archived"] is False and lost.records["spool"][57]["location"] == ""


def test_a_refill_after_a_toolhead_whose_answer_was_lost_still_asks(lost, client):
    """RED on e1b22f4 (the question is new; on the base the 42.3c warning was lost
    the same way)."""
    _archived(lost, "XL-1")
    body = _save(client, {"used_weight": 600})
    assert body["status"] == "success", body
    assert body.get("refill_ask") == {"place": "XL-1", "room": "LR", "held_by": []}, body


# ---- one read, one verdict -------------------------------------------------------------------------

@pytest.mark.parametrize("make, updates", [
    (lambda f: f.add("spool", 57, {}, location="CR-SHELF", initial_weight=1000.0, used_weight=300.0,
                     archived=False), {"used_weight": 1000}),
    (lambda f: _archived(f, "CR-SHELF"), {"used_weight": 600}),
], ids=["archive", "refill"])
def test_a_lost_archive_or_refill_reads_the_spool_once(lost, client, make, updates):
    """RED on e1b22f4: update_spool re-read it, then the route read it again."""
    make(lost)
    body = _save(client, updates)
    assert body["status"] == "success", body
    assert lost.after_patch == ["http://sm.test/api/v1/spool/57"], lost.after_patch


def test_control_a_plain_weight_write_is_still_read_back_by_the_route(lost, client):
    """Control (green on e1b22f4 too): a write that neither archives nor un-archives
    is read by nobody in update_spool, so the route reads it back itself."""
    lost.add("spool", 57, {}, location="CR-SHELF", initial_weight=1000.0, used_weight=300.0, archived=False)
    body = _save(client, {"used_weight": 400})
    assert body["status"] == "success", body
    assert lost.after_patch == ["http://sm.test/api/v1/spool/57"], lost.after_patch


def test_a_record_that_changes_between_reads_cant_split_the_line_and_the_answer(lost, client):
    """RED on e1b22f4: the archive landed and update_spool's re-read logged "📦
    Auto-archived …"; someone put the spool back on CR-SHELF before the route read it
    again, so the route answered "Couldn't save" while the line said archived. Now
    the one read decides both: archived, and the line, whatever a later read says."""
    lost.add("spool", 57, {}, location="CR-SHELF", initial_weight=1000.0, used_weight=300.0, archived=False)

    def moved_back_on_the_second_read(n, fake):
        if n == 2:
            fake.records["spool"][57].update(archived=False, location="CR-SHELF")

    lost.on_read = moved_back_on_the_second_read
    body = _save(client, {"used_weight": 1000})
    assert body["status"] == "success" and body["auto_archived"] is True, body
    assert _lines("📦 Auto-archived Spool #57"), state.RECENT_LOGS


def test_the_verdict_is_taken_once(lost):
    """take_unanswered hands a write's verdict to the caller once; the next write to
    the spool starts from none."""
    _archived(lost, "CR-SHELF")
    assert sm_api.update_spool(57, {"used_weight": 600}) is None
    first = sm_api.take_unanswered(57)
    assert first["landed"] is True and first["record"]["location"] == "CR-SHELF", first
    assert sm_api.take_unanswered(57) is None
