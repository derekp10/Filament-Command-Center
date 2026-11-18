"""Group 63.2: a spool weighed to empty that FCC couldn't take off its place.

When FCC can't read a spool just before a weigh to empty, the archive edge can't
run and the page's own `archived: true` archives it where it stands. Since 63.2,
/api/spool/update takes it off in the same request (archive_takeoff.take_off, from
the record Spoolman answered); a take-off that fails too is written down
(archive_takeoff.note_stuck) and tried again: by the print monitor's loop
(retry_due: ~30 s, then backing off), before any move onto that place (retry_at;
Derek, 2026-11-18), and by the listed line's "Take it off" button
(take_off_now, POST /api/spool/archive_takeoff) once 5 retries have failed. Each
try re-reads the spool strictly and writes only while it is still archived exactly
where the record says.

The unit tests run archive_takeoff's REAL update_spool over
tests/spoolman_extra_fake.SpoolmanHTTPFake (Spoolman 0.27, its field types
checked); the route and the move hook run the REAL route and engine over
tests/move_engine_harness. Every test here is RED on e1b22f4 (the module, the
route's take-off and the hook are new), except where a docstring says control.
"""
from __future__ import annotations

import copy
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import archive_takeoff  # noqa: E402
import logic  # noqa: E402
import spoolman_api as sm_api  # noqa: E402
import state  # noqa: E402
from move_engine_harness import IDLE, LocationsStore, WeighedWireSpoolman, run_move  # noqa: E402
from spoolman_extra_fake import SpoolmanHTTPFake  # noqa: E402

TRAIL = ("container_slot", "physical_source", "physical_source_slot")
SPOOL_FIELDS = [
    {"key": k, "field_type": "text", "name": k} for k in (
        "container_slot", "physical_source", "physical_source_slot",
        "fcc_pre_archive_location", "fcc_pre_box_location", "fcc_pre_audit_location")
]
PRINTER_MAP = {f"XL-{n}": {"printer_name": "XL", "position": n - 1} for n in (1, 2)}
ROWS = [
    {"LocationID": "LR", "Type": "Room", "Max Spools": "0"},
    {"LocationID": "XL", "Type": "Printer", "Max Spools": "0", "parent_id": "LR",
     "toolheads": [{"location_id": f"XL-{n}", "position": n - 1} for n in (1, 2)]},
    *[{"LocationID": f"XL-{n}", "Type": "Tool Head", "Max Spools": "1", "parent_id": "XL"} for n in (1, 2)],
    {"LocationID": "PM-DB-1", "Type": "Dryer Box", "Max Spools": "1", "parent_id": "LR",
     "extra": {"slot_targets": {"1": "XL-1"}}},
    {"LocationID": "CR-SHELF", "Type": "Shelf", "Max Spools": "12", "parent_id": "LR"},
]


@pytest.fixture(autouse=True)
def _isolate_state():
    prior = (state.RECENT_LOGS, state.UNDO_STACK, state.GLOBAL_BUFFER)
    state.RECENT_LOGS, state.UNDO_STACK, state.GLOBAL_BUFFER = [], [], []
    try:
        yield
    finally:
        state.RECENT_LOGS, state.UNDO_STACK, state.GLOBAL_BUFFER = prior


def _logs(fragment):
    return [e for e in state.RECENT_LOGS if fragment in str(e.get("msg", e))]


@pytest.fixture
def http(monkeypatch):
    """archive_takeoff's REAL reads and writes over a Spoolman 0.27."""
    fake = SpoolmanHTTPFake(version="0.27.0", fields={"spool": copy.deepcopy(SPOOL_FIELDS)})
    fake.refuse_patches = False
    real_patch = fake.patch

    def patch_(url, json=None, timeout=None, **kw):  # noqa: A002
        if fake.refuse_patches:
            fake.patches.append(("refused", url, copy.deepcopy(json)))
            return MagicMock(ok=False, status_code=500, text='{"message": "database is locked"}',
                             json=MagicMock(return_value={"message": "database is locked"}))
        return real_patch(url, json=json, timeout=timeout, **kw)

    detached = []
    monkeypatch.setattr(sm_api.config_loader, "get_api_urls", lambda: ("http://sm.test", "http://fb"))
    monkeypatch.setattr(sm_api.requests, "get", fake.get)
    monkeypatch.setattr(sm_api.requests, "patch", patch_)
    monkeypatch.setattr(sm_api.locations_db, "get_active_printer_map", lambda *a, **k: PRINTER_MAP)
    monkeypatch.setattr(sm_api.locations_db, "load_locations_list", lambda *a, **k: copy.deepcopy(ROWS))
    monkeypatch.setattr(sm_api.locations_db, "detach_single_slot_box",
                        lambda box, head: detached.append((box, head)) or True)
    for name in ("_FIELD_SCHEMA_CACHE", "_SPOOLMAN_VERSION_CACHE"):
        getattr(sm_api, name, {}).clear()
    fake.detached = detached
    yield fake
    for name in ("_FIELD_SCHEMA_CACHE", "_SPOOLMAN_VERSION_CACHE"):
        getattr(sm_api, name, {}).clear()


def _stuck_on_xl1(http, sid=57, location="XL-1"):
    """#57, archived on XL-1 with its trail from PM-DB-1 (a take-off that failed)."""
    http.add("spool", sid, {"physical_source": '"PM-DB-1"', "physical_source_slot": '"1"'},
             location=location, initial_weight=1000.0, used_weight=1000.0, archived=True)
    return archive_takeoff.note_stuck(sid, location, "HTTP 500: database is locked", now=1000.0)


# ---- the store ---------------------------------------------------------------------------------------

def test_a_failed_take_off_is_written_down_with_its_first_retry_in_30_s():
    rec = archive_takeoff.note_stuck(57, "XL-1", "HTTP 500: database is locked", now=1000.0)
    assert rec == {"sid": 57, "since": 1000.0, "tries": 0, "listed": False, "place": "XL-1",
                   "last_error": "HTTP 500: database is locked", "next_at": 1030.0}
    assert archive_takeoff.pending() == [rec]
    assert os.path.basename(archive_takeoff._STORE_PATH) == "pending_archive_takeoffs.json"


def test_written_down_again_it_keeps_its_tries_and_listing():
    archive_takeoff.note_stuck(57, "XL-1", "first", now=1000.0)
    with archive_takeoff._LOCK:
        data = archive_takeoff._load()
        data["57"].update(tries=6, listed=True)
        archive_takeoff._save(data)
    rec = archive_takeoff.note_stuck(57, "XL-1", "second", now=2000.0)
    assert rec["tries"] == 6 and rec["listed"] is True and rec["since"] == 1000.0, rec
    assert rec["last_error"] == "second" and rec["next_at"] == 2030.0, rec


# ---- the retry: it writes only while the spool is still archived exactly there ----------------------

def test_a_due_retry_takes_it_off_and_forgets_it(http):
    _stuck_on_xl1(http)
    archive_takeoff.retry_due(now=1031.0)
    rec = http.records["spool"][57]
    assert rec["archived"] is True and rec["location"] == "", rec
    assert all(rec["extra"][k] == '""' for k in TRAIL), rec
    assert rec["extra"]["fcc_pre_archive_location"] == '"XL-1"', rec
    assert http.detached == [("PM-DB-1", "XL-1")], http.detached
    assert archive_takeoff.pending() == []
    assert _logs("Took archived Spool #57 off XL-1 on a later try"), state.RECENT_LOGS


def test_a_retry_that_isnt_due_does_nothing(http):
    _stuck_on_xl1(http)
    archive_takeoff.retry_due(now=1029.0)
    assert http.patches == [] and http.gets == []
    assert len(archive_takeoff.pending()) == 1


@pytest.mark.parametrize("change, outcome, words", [
    ({"archived": False}, "refilled", "back in stock, so FCC no longer takes it off XL-1"),
    ({"location": "CR-SHELF"}, "moved", "is at CR-SHELF now, so FCC left it there"),
    ({"location": ""}, "off", "is off XL-1 now (Unassigned)"),
], ids=["weighed-back", "moved", "already-off"])
def test_a_spool_changed_since_is_dropped_never_written(http, change, outcome, words):
    _stuck_on_xl1(http)
    http.records["spool"][57].update(change)
    assert archive_takeoff._try(archive_takeoff.get(57), 1031.0, "retry") == outcome
    assert http.patches == [], http.patches
    assert archive_takeoff.pending() == []
    assert _logs(words), state.RECENT_LOGS


def test_a_deleted_spool_is_dropped(http):
    _stuck_on_xl1(http)
    del http.records["spool"][57]
    assert archive_takeoff._try(archive_takeoff.get(57), 1031.0, "retry") == "gone"
    assert archive_takeoff.pending() == [] and http.patches == []


def test_a_spoolman_that_doesnt_answer_counts_as_a_failed_try(http):
    _stuck_on_xl1(http)
    http.down = True
    assert archive_takeoff._try(archive_takeoff.get(57), 1031.0, "retry") == "failed"
    rec = archive_takeoff.get(57)
    assert rec["tries"] == 1 and rec["next_at"] == 1031.0 + 60, rec
    assert rec["last_error"] == "Spoolman didn't answer.", rec


def test_five_failed_retries_list_it_once_with_its_button_and_it_keeps_trying(http):
    """The backoff: 30, 60, 120, 240, 480 s; listed after the 5th failed retry, then
    tried every 10 minutes. One WARNING line, its button in the line itself."""
    _stuck_on_xl1(http)
    http.refuse_patches = True
    now = 1000.0
    expected_gaps = [60, 120, 240, 480, 600, 600]
    for n, gap in enumerate(expected_gaps, start=1):
        due = archive_takeoff.get(57)["next_at"]
        archive_takeoff.retry_due(now=due)
        rec = archive_takeoff.get(57)
        assert rec["tries"] == n and rec["next_at"] == due + gap, (n, rec)
        assert rec["listed"] is (n >= 5), (n, rec)
        now = due
    listed = [e for e in state.RECENT_LOGS if "is archived but still at XL-1" in e["msg"]]
    assert len(listed) == 1, state.RECENT_LOGS
    line = listed[0]
    assert line["type"] == "WARNING" and line.get("meta") == {
        "type": "archive_takeoff_pending", "spool_id": 57, "place": "XL-1"}, line
    assert ('<button type="button" class="btn btn-sm btn-outline-warning ms-2 py-0 px-1 fcc-takeoff-btn" '
            'data-takeoff-spool="57">Take it off</button>') in line["msg"], line
    assert "(Spoolman refused it: database is locked)" in line["msg"], line


def test_the_listed_line_escapes_the_place(http):
    http.add("spool", 58, {}, location="<b>Bin</b>", initial_weight=1000.0, used_weight=1000.0, archived=True)
    archive_takeoff.note_stuck(58, "<b>Bin</b>", "x", now=0.0)
    archive_takeoff._log_listed(archive_takeoff.get(58))
    (line,) = _logs("is archived but still at")
    assert "&lt;b&gt;Bin&lt;/b&gt;" in line["msg"] and "<b>Bin" not in line["msg"], line


# ---- before a move onto that place (Derek's hook) ----------------------------------------------------

def test_retry_at_tries_only_the_spools_written_down_at_that_place(http):
    _stuck_on_xl1(http)
    http.add("spool", 60, {}, location="XL-2", initial_weight=1000.0, used_weight=1000.0, archived=True)
    archive_takeoff.note_stuck(60, "XL-2", "x", now=1000.0)
    archive_takeoff.retry_at("xl-1", now=1001.0)   # before its retry is due, any case
    assert http.records["spool"][57]["location"] == "" and http.records["spool"][60]["location"] == "XL-2"
    assert [r["sid"] for r in archive_takeoff.pending()] == [60]
    assert _logs("Took archived Spool #57 off XL-1 before a move onto it"), state.RECENT_LOGS


def test_a_move_onto_the_place_takes_the_stuck_spool_off_first():
    """#57 is archived on XL-1 and written down; a move of #99 onto XL-1 tries it
    first (the real engine), so #99 doesn't land beside a hidden spool. RED on
    e1b22f4: nothing remembered #57."""
    store = LocationsStore(ROWS)
    sm = WeighedWireSpoolman({
        57: {"location": "XL-1", "initial_weight": 1000, "used_weight": 1000, "archived": True,
             "extra": {"physical_source": "PM-DB-1", "physical_source_slot": "1"}},
        99: {"location": "CR-SHELF", "initial_weight": 1000, "used_weight": 100, "archived": False, "extra": {}},
    })
    archive_takeoff.note_stuck(57, "XL-1", "x", now=0.0)
    with patch.object(sm_api, "get_spool_answer", side_effect=lambda sid: (sm.get_spool(sid), True)):
        res = run_move(sm, probe=IDLE, store=store, printer_map=PRINTER_MAP, target="XL-1", raw_spools=[99])
    assert logic.smart_move_failure(res, 99) == "", res
    assert sm.spools[57]["location"] == "" and sm.spools[57]["archived"] is True, sm.spools[57]
    assert sm.spools[99]["location"] == "XL-1"
    assert archive_takeoff.pending() == []
    assert store.bound("PM-DB-1") == "", store.row("PM-DB-1")


def test_control_a_move_with_nothing_written_down_reads_nothing_more():
    """Control: no record, no extra read (the hook reads only its own store)."""
    sm = WeighedWireSpoolman({99: {"location": "CR-SHELF", "initial_weight": 1000, "used_weight": 100,
                                   "archived": False, "extra": {}}})
    with patch.object(sm_api, "get_spool_answer", side_effect=AssertionError("no read")):
        res = run_move(sm, probe=IDLE, store=LocationsStore(ROWS), printer_map=PRINTER_MAP,
                       target="XL-1", raw_spools=[99])
    assert logic.smart_move_failure(res, 99) == "", res


# ---- the listed line's button, and after a restart ----------------------------------------------------

@pytest.fixture
def client():
    import app as app_module
    app_module.app.config["TESTING"] = True
    return app_module.app.test_client()


def test_the_button_takes_it_off_now(http, client):
    _stuck_on_xl1(http)
    body = client.post("/api/spool/archive_takeoff", json={"id": 57}).get_json()
    assert body == {"success": True, "msg": "Took #57 off XL-1: it is Unassigned now."}, body
    assert http.records["spool"][57]["location"] == "" and archive_takeoff.pending() == []


def test_the_button_says_why_when_it_still_cant(http, client):
    _stuck_on_xl1(http)
    http.refuse_patches = True
    body = client.post("/api/spool/archive_takeoff", json={"id": 57}).get_json()
    assert body["success"] is False, body
    assert body["msg"] == ("Couldn't take #57 off XL-1: Spoolman refused it: database is locked "
                           "FCC keeps trying."), body
    assert archive_takeoff.get(57)["tries"] == 1


@pytest.mark.parametrize("payload, status", [({"id": 57}, 200), ({}, 400), ({"id": True}, 400),
                                             ({"id": "x"}, 400), (None, 400)],
                         ids=["nothing-written-down", "no-id", "bool", "text", "no-body"])
def test_the_button_route_reads_its_id_strictly(client, payload, status):
    resp = client.post("/api/spool/archive_takeoff", json=payload) if payload is not None \
        else client.post("/api/spool/archive_takeoff", data="x", content_type="text/plain")
    assert resp.status_code == status, resp.get_json()
    if status == 200:
        assert resp.get_json() == {"success": True, "msg": "FCC has nothing left to take off for #57."}


def test_a_listed_spool_is_listed_again_after_a_restart(http):
    archive_takeoff.note_stuck(57, "XL-1", "HTTP 500: database is locked", now=0.0)
    archive_takeoff.note_stuck(58, "XL-2", "x", now=0.0)
    with archive_takeoff._LOCK:
        data = archive_takeoff._load()
        data["57"]["listed"] = True
        archive_takeoff._save(data)
    import startup_migrations
    startup_migrations.resurface_pending_archive_takeoffs()
    lines = _logs("is archived but still at")
    assert len(lines) == 1 and "Still waiting from before FCC restarted: Spool #57" in lines[0]["msg"], lines
    assert 'data-takeoff-spool="57"' in lines[0]["msg"]


# ---- the save itself: a take-off that fails is written down ------------------------------------------

class _TakeOffRefused(WeighedWireSpoolman):
    """The route's first write lands (FCC couldn't read #57 first, so it archives it
    in place); every later PATCH that takes it off is refused, as Spoolman's
    "database is locked" would."""

    def __init__(self, spools):
        super().__init__(spools)
        self.blind = True

    def get_spool(self, sid):
        return None if self.blind else super().get_spool(sid)

    def _http_patch(self, url, json=None, **k):
        if (json or {}).get("location") == "":
            self.patch_bodies.append((57, copy.deepcopy(json)))
            return MagicMock(ok=False, status_code=500, text='{"message": "database is locked"}',
                             json=MagicMock(return_value={"message": "database is locked"}))
        return super()._http_patch(url, json=json, **k)


def test_a_weigh_whose_take_off_fails_says_still_at_and_writes_it_down(client):
    sm = _TakeOffRefused({57: {"location": "XL-1", "initial_weight": 1000, "used_weight": 700, "archived": False,
                               "extra": {"physical_source": "PM-DB-1", "physical_source_slot": "1"}}})
    with patch.object(sm_api, "get_spool_answer", side_effect=lambda sid: (sm.spools.get(int(sid)) and
                                                                          {"id": int(sid), **sm.spools[int(sid)]},
                                                                          True)):
        res = run_move(sm, probe=IDLE, store=LocationsStore(ROWS), printer_map=PRINTER_MAP,
                       call=lambda: client.post("/api/spool/update", json={
                           "id": 57, "updates": {"remaining_weight": 0, "archived": True},
                           "auto_archive": True})).get_json()
    assert res["status"] == "success", res
    assert res.get("still_at") == "XL-1" and res.get("location_now") == "XL-1", res
    assert sm.spools[57]["archived"] is True and sm.spools[57]["location"] == "XL-1"
    (rec,) = archive_takeoff.pending()
    assert rec["sid"] == 57 and rec["place"] == "XL-1" and rec["tries"] == 0, rec
    assert "database is locked" in rec["last_error"], rec
    (line,) = _logs("is archived but still at XL-1")
    assert line["type"] == "WARNING" and "FCC will keep trying" in line["msg"], line


def test_control_with_the_switch_off_an_archived_spool_weighed_to_nothing_stays_where_it_is(client):
    """Control (Group 54.7: off means off): an archived spool on a shelf weighed to
    0 g with Auto-Archive off stays archived there, and nothing takes it off."""
    sm = WeighedWireSpoolman({57: {"location": "CR-SHELF", "initial_weight": 1000, "used_weight": 900,
                                   "archived": True, "extra": {}}})
    res = run_move(sm, probe=IDLE, store=LocationsStore(ROWS), printer_map=PRINTER_MAP,
                   call=lambda: client.post("/api/spool/update", json={
                       "id": 57, "updates": {"used_weight": 1000}, "auto_archive": False})).get_json()
    assert res["status"] == "success" and "still_at" not in res, res
    assert sm.spools[57]["location"] == "CR-SHELF" and archive_takeoff.pending() == []

class _Unread(WeighedWireSpoolman):
    """FCC's reads of the spool fail (get_spool answers nothing); writes land."""

    def get_spool(self, sid):
        return None


def test_control_a_spool_archived_by_hand_weighed_with_grams_left_stays_where_it_is(client):
    """Control: the take-off runs only when the page asked to archive. A spool
    archived by hand on CR-SHELF and weighed with 300 g left while FCC couldn't read
    it first is no refill FCC can see and no archive the page asked for: it stays
    archived on CR-SHELF (Derek's 43.2 rule), with nothing written down."""
    sm = _Unread({57: {"location": "CR-SHELF", "initial_weight": 1000, "used_weight": 1000, "archived": True,
                       "extra": {}}})
    res = run_move(sm, probe=IDLE, store=LocationsStore(ROWS), printer_map=PRINTER_MAP,
                   call=lambda: client.post("/api/spool/update", json={
                       "id": 57, "updates": {"used_weight": 700}, "auto_archive": True})).get_json()
    assert res["status"] == "success" and "still_at" not in res, res
    assert sm.spools[57]["location"] == "CR-SHELF" and sm.spools[57]["archived"] is True, sm.spools[57]
    assert [b for _sid, b in sm.patch_bodies if b.get("location") == ""] == [], sm.patch_bodies
    assert archive_takeoff.pending() == []

