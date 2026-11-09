"""Group 54.6 — the archive edge reads `remaining_weight`.

`spoolman_api._auto_archive_on_empty` counted only `used_weight` and
`initial_weight` as a weight write, while its twin, the refill edge
(`_auto_unarchive_on_refill`), has read `remaining_weight` since the Group 51
review (engine-5). The one page that sends `remaining_weight` is the weigh-out
list's fallback row, used when the spool's details couldn't be read
(`inv_weigh_out.js`, Net mode only). Weighing a spool to 0 g that way left it in
stock; with the window's Auto-Archive switch on, the page archived it itself and
unassigned it in a second call, so it got no pre-archive note (a later weigh-back
couldn't put it back), its trail wasn't cleared in the same write, and its
single-slot box let go only on that second call.

Now a write carrying `remaining_weight` and no `used_weight` is a weight write
whose weight left is the one sent, exactly as the refill edge reads it; a value
that isn't a number changes nothing. Everything after that is today's archive
edge: `archived` and `location` only when the caller didn't set them, the note,
the trail blanks, the Activity Log line and the single-slot box release.

The unit cases call the edge itself; the rest run the REAL update_spool over
tests/spoolman_extra_fake.SpoolmanHTTPFake, or the REAL /api/spool/update and
update_spool over tests/move_engine_harness with only Spoolman's HTTP faked
([[mocked engine hides chain bugs]]).

Base proof (7cb6988): every test marked RED fails there; the controls pass.

Review R1-1 (2026-11-09): the fallback row runs only when the spool's details
couldn't be read, so FCC's own reads of the spool can fail too. With no record,
the edge decided from the weight alone and blanked the location and the trail
without knowing where the spool was, and nothing could release its single-slot
box afterwards. Now update_spool runs the archive edge only on a record it read
(one with an id); an unread spool goes out as the caller sent it. The tests
marked "RED on d60c86e" fail on the branch before that fix.
"""
from __future__ import annotations

import copy
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import spoolman_api as sm_api  # noqa: E402
import state  # noqa: E402
from move_engine_harness import IDLE, LocationsStore, WeighedWireSpoolman, run_move  # noqa: E402
from spoolman_extra_fake import SpoolmanHTTPFake  # noqa: E402

TRAIL = ("container_slot", "physical_source", "physical_source_slot")


@pytest.fixture(autouse=True)
def _isolate_state():
    prior = (state.RECENT_LOGS, state.UNDO_STACK, state.GLOBAL_BUFFER)
    state.RECENT_LOGS, state.UNDO_STACK, state.GLOBAL_BUFFER = [], [], []
    try:
        yield
    finally:
        state.RECENT_LOGS, state.UNDO_STACK, state.GLOBAL_BUFFER = prior


def _logs(fragment):
    return [e for e in state.RECENT_LOGS if fragment in str(e.get("message", e))]


# ---- the edge itself ------------------------------------------------------------------------------------

def _edge(write, *, initial=1000, used=700, location="CR-SHELF", filament_weight=None):
    """The archive edge on a copy of `write`, for a spool of `initial` g with
    `used` g used, filed at `location`."""
    data = copy.deepcopy(write)
    sm_api._auto_archive_on_empty(data, initial, used, existing_location=location,
                                  existing_filament_weight=filament_weight)
    return data


@pytest.mark.parametrize("left", [0, 0.0, "0", -0.0], ids=["int", "float", "text", "minus-zero"])
def test_a_weight_left_of_nothing_archives_unassigns_and_notes_where_it_was(left):
    """RED on the base: a `remaining_weight` write was no weight write at all."""
    data = _edge({"remaining_weight": left})
    assert data["archived"] is True and data["location"] == "", data
    extra = data["extra"]
    assert extra["fcc_pre_archive_location"] == "CR-SHELF", data
    assert all(extra[k] == "" for k in TRAIL), data
    assert data["remaining_weight"] == left, data


@pytest.mark.parametrize("left", [0.4, 250, "x", None, "nan", float("nan")],
                         ids=["some-left", "plenty-left", "text", "null", "nan-text", "nan"])
def test_a_weight_left_above_nothing_or_not_a_number_changes_nothing(left):
    """Control: as the refill edge reads it, a weight left that isn't a number
    is no reading. A NaN is not a number either (`nan > 0` is False, so a bare
    float() would have archived the spool)."""
    write = {"remaining_weight": left}
    data = _edge(write)
    assert set(data) == {"remaining_weight"}, data
    assert "archived" not in data and "location" not in data and "extra" not in data, data


def test_used_weight_beside_it_decides():
    """Control: with both (Spoolman refuses the pair anyway) the used weight
    decides, as in the refill edge: 300 of 1000 used leaves 700 g."""
    data = _edge({"used_weight": 300, "remaining_weight": 0})
    assert "archived" not in data and "location" not in data, data


def test_the_weight_left_decides_over_a_new_initial_weight():
    """As in the refill edge, a write carrying the weight left says how much is
    left, whatever total it also sends. RED on the base (1200 - 100 > 0)."""
    data = _edge({"initial_weight": 1200, "remaining_weight": 0}, used=100)
    assert data["archived"] is True and data["location"] == "", data


def test_it_needs_no_known_capacity():
    """The weight left needs no initial weight: a spool whose capacity FCC
    doesn't know (none of its own, none on its filament) is still archived when
    the write says nothing is left. RED on the base."""
    data = _edge({"remaining_weight": 0}, initial=None, used=None)
    assert data["archived"] is True, data


def test_a_callers_own_location_is_kept_with_no_note_and_no_blanks():
    """The caller's location wins, as on the used-weight path: no note, no trail
    blanks (the caller is taking over the move). RED on the base (not archived)."""
    data = _edge({"remaining_weight": 0, "location": "CR-CT-2-R1"})
    assert data["archived"] is True and data["location"] == "CR-CT-2-R1", data
    assert "extra" not in data, data


def test_a_spool_already_unassigned_gets_no_note():
    """Nothing to remember when it is already Unassigned (the used-weight path's
    rule). RED on the base (not archived)."""
    data = _edge({"remaining_weight": 0}, location="")
    assert data["archived"] is True and data["location"] == "", data
    assert "fcc_pre_archive_location" not in data["extra"], data


# ---- update_spool over a whole Spoolman ---------------------------------------------------------------

SPOOL_FIELDS = [
    *[{"key": k, "field_type": "text", "name": k} for k in (
        "container_slot", "physical_source", "physical_source_slot",
        "fcc_pre_archive_location", "fcc_pre_box_location", "fcc_pre_audit_location")],
    {"key": "needs_label_print", "field_type": "boolean", "name": "Needs Label Print"},
]


@pytest.fixture
def http(monkeypatch):
    """spoolman_api's HTTP seam on a Spoolman 0.27 (SpoolmanHTTPFake). The archive
    edge's box release asks for the printer map: none here, so nothing reads
    config.json or locations.json."""
    fake = SpoolmanHTTPFake(version="0.27.0", fields={"spool": copy.deepcopy(SPOOL_FIELDS)})
    monkeypatch.setattr(sm_api.config_loader, "get_api_urls", lambda: ("http://sm.test", "http://fb"))
    monkeypatch.setattr(sm_api.requests, "get", fake.get)
    monkeypatch.setattr(sm_api.requests, "patch", fake.patch)
    monkeypatch.setattr(sm_api.locations_db, "get_active_printer_map", lambda: {})
    for name in ("_FIELD_SCHEMA_CACHE", "_SPOOLMAN_VERSION_CACHE"):
        getattr(sm_api, name, {}).clear()
    yield fake
    for name in ("_FIELD_SCHEMA_CACHE", "_SPOOLMAN_VERSION_CACHE"):
        getattr(sm_api, name, {}).clear()


def test_update_spool_archives_a_spool_whose_weight_left_is_nothing(http):
    """RED on the base: the PATCH carried the weight alone, so the spool stayed
    in stock in LR-MDB-1 slot 2 at 0 g."""
    http.add("spool", 57, {"container_slot": '"2"', "needs_label_print": "false"},
             location="LR-MDB-1", initial_weight=1000.0, used_weight=700.0, archived=False)
    out = sm_api.update_spool(57, {"remaining_weight": 0})
    assert out is not None, sm_api.LAST_SPOOLMAN_ERROR
    (_entity, _sid, body), = http.patches
    assert body["remaining_weight"] == 0 and body["archived"] is True and body["location"] == "", body
    extra = body["extra"]
    assert extra["fcc_pre_archive_location"] == '"LR-MDB-1"', body
    assert all(extra[k] == '""' for k in TRAIL), body
    assert extra["needs_label_print"] == "false", body   # a sibling rides along untouched
    rec = http.records["spool"][57]
    assert rec["archived"] is True and rec["location"] == "", rec
    assert _logs("📦 Auto-archived Spool #57"), state.RECENT_LOGS


def test_an_archived_spool_weighed_to_nothing_again_makes_the_idempotent_write(http):
    """The used-weight path's idempotent write (test_already_archived_zero_weight_
    update_is_idempotent): `archived: True, location: ''`, its old note kept (it
    is already Unassigned, so no new one), and no "Auto-archived" line because
    nothing changed state. RED on the base (the PATCH carried the weight alone)."""
    http.add("spool", 57, {"fcc_pre_archive_location": '"CR-SHELF"'},
             location="", initial_weight=1000.0, used_weight=1000.0, archived=True)
    assert sm_api.update_spool(57, {"remaining_weight": 0}) is not None, sm_api.LAST_SPOOLMAN_ERROR
    (_entity, _sid, body), = http.patches
    assert body["archived"] is True and body["location"] == "", body
    assert body["extra"]["fcc_pre_archive_location"] == '"CR-SHELF"', body   # the old note, as it was
    assert http.records["spool"][57]["extra"]["fcc_pre_archive_location"] == '"CR-SHELF"'
    assert not _logs("Auto-archived") and not _logs("📤"), state.RECENT_LOGS


# ---- the door: /api/spool/update, the weigh-out row's fallback ----------------------------------------

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


@pytest.fixture
def client():
    import app as app_module
    app_module.app.config["TESTING"] = True
    return app_module.app.test_client()


def _post(sm, client, body, store):
    return run_move(sm, probe=IDLE, store=store, printer_map=PRINTER_MAP,
                    call=lambda: client.post("/api/spool/update", json=body)).get_json()


def test_the_fallback_row_weighing_a_loaded_spool_to_nothing_archives_it_and_its_box_lets_go(client):
    """#57 is on XL-1, loaded from the single-slot box PM-DB-1 (bound to XL-1).
    The weigh-out row's fallback sends `remaining_weight: 0`: the spool is
    archived and Unassigned in that one write, with a note saying XL-1 and its
    trail cleared, the answer says `auto_archived`, and PM-DB-1 lets go of XL-1
    (Derek's rule: a single-slot box lets go when its own spool leaves the head
    by any path). RED on the base: nothing archived, the box stayed bound."""
    sm = WeighedWireSpoolman({57: {"location": "XL-1", "initial_weight": 1000, "used_weight": 700,
                                   "archived": False,
                                   "extra": {"physical_source": "PM-DB-1", "physical_source_slot": "1"}}})
    store = LocationsStore(ROWS)
    assert store.bound("PM-DB-1") == "XL-1"
    res = _post(sm, client, {"id": 57, "updates": {"remaining_weight": 0}}, store)
    assert res["status"] == "success" and res["auto_archived"] is True, res
    spool = sm.spools[57]
    assert spool["archived"] is True and spool["location"] == "", spool
    assert spool["used_weight"] == 1000.0, spool          # Spoolman's own reading of "0 g left"
    assert spool["extra"]["fcc_pre_archive_location"] == "XL-1", spool
    assert all(spool["extra"].get(k) == "" for k in TRAIL), spool
    assert store.bound("PM-DB-1") == "", store.row("PM-DB-1")
    assert _logs("📦 Auto-archived Spool #57"), state.RECENT_LOGS
    assert _logs("PM-DB-1 detached from XL-1"), state.RECENT_LOGS


def test_control_the_fallback_row_weighing_an_archived_spool_back_unarchives_it(client):
    """Control (green on the base too, since the Group 51 review): 40 g left on a
    spool archived empty off CR-SHELF brings it back into stock there."""
    sm = WeighedWireSpoolman({57: {"location": "", "initial_weight": 1000, "used_weight": 1000,
                                   "archived": True, "extra": {"fcc_pre_archive_location": "CR-SHELF"}}})
    res = _post(sm, client, {"id": 57, "updates": {"remaining_weight": 40}}, LocationsStore(ROWS))
    assert res["status"] == "success" and res["auto_archived"] is False, res
    spool = sm.spools[57]
    assert spool["archived"] is False and spool["location"] == "CR-SHELF", spool
    assert spool["used_weight"] == 960.0, spool
    assert spool["extra"]["fcc_pre_archive_location"] == "", spool


# ---- a spool FCC couldn't read (review R1-1) ----------------------------------------------------------

# How FCC's bare read (spoolman_api.get_spool) fails: no answer (a timeout, or no
# connection: None), or a 5xx, whose JSON error body get_spool hands back as a
# truthy dict with no id.
READ_FAILURES = [None, {"message": "database is locked"}]
READ_FAILURE_IDS = ["no-answer", "5xx-body"]


class _UnreadSpoolman(WeighedWireSpoolman):
    """WeighedWireSpoolman whose `get_spool` (FCC's read of a spool) fails while
    `blind` is set, as `failure` says. The plain GET of the record that the
    pre-merge extras read makes still answers."""

    def __init__(self, spools, failure=None):
        super().__init__(spools)
        self.blind = False
        self.failure = failure

    def get_spool(self, sid):
        if self.blind:
            return copy.deepcopy(self.failure)
        return super().get_spool(sid)


def _on_xl1_from_pm_db_1():
    return {57: {"location": "XL-1", "initial_weight": 1000, "used_weight": 700, "archived": False,
                 "extra": {"physical_source": "PM-DB-1", "physical_source_slot": "1"}}}


@pytest.mark.parametrize("failure", READ_FAILURES, ids=READ_FAILURE_IDS)
def test_the_fallback_row_on_a_spool_fcc_couldnt_read_archives_it_in_place_and_its_box_lets_go(client, failure):
    """#57 is on XL-1, loaded from the single-slot box PM-DB-1. The weigh-out row's
    fallback, with Auto-Archive on, sends {remaining_weight: 0, archived: true} and
    then force-unassigns, as the page does (inv_weigh_out.js). FCC's reads of #57
    fail during the first call (the route's and update_spool's own); the pre-merge
    extras read answers. The write goes out as the page sent it, so #57 is archived
    where it is with its trail, and the force-unassign takes it off XL-1 and lets
    PM-DB-1 go, as before 54.6. RED on d60c86e: the edge decided from the weight
    alone, the PATCH blanked the location and the trail without knowing where #57
    was (no note), so the edge saw no head, the route's `pre` was empty, the
    force-unassign found the trail blank, and PM-DB-1 stayed bound to XL-1."""
    sm = _UnreadSpoolman(_on_xl1_from_pm_db_1(), failure=failure)
    store = LocationsStore(ROWS)
    sm.blind = True
    res = _post(sm, client, {"id": 57, "updates": {"remaining_weight": 0, "archived": True},
                             "auto_archive": True}, store)
    sm.blind = False
    assert res["status"] == "success", res
    (sid, first), = sm.patch_bodies
    assert sid == 57 and first == {"remaining_weight": 0, "archived": True}, first
    assert "location" not in first and "extra" not in first, first
    spool = sm.spools[57]
    assert spool["archived"] is True and spool["location"] == "XL-1", spool
    assert spool["extra"]["physical_source"] == "PM-DB-1", spool
    assert "fcc_pre_archive_location" not in spool["extra"], spool

    out = run_move(sm, probe=IDLE, store=store, printer_map=PRINTER_MAP,
                   call=lambda: client.post("/api/manage_contents", json={
                       "action": "force_unassign", "spool_id": 57, "location": ""})).get_json()
    assert out.get("success") is True, out
    spool = sm.spools[57]
    assert spool["archived"] is True and spool["location"] == "", spool
    assert all(spool["extra"].get(k) == "" for k in TRAIL), spool
    assert store.bound("PM-DB-1") == "", store.row("PM-DB-1")
    assert _logs("PM-DB-1 detached from XL-1"), state.RECENT_LOGS


@pytest.mark.parametrize("failure", READ_FAILURES, ids=READ_FAILURE_IDS)
@pytest.mark.parametrize("write", [{"remaining_weight": 0}, {"used_weight": 1000, "initial_weight": 1000}],
                         ids=["weight-left", "used-and-initial"])
def test_update_spool_never_runs_the_edge_on_a_spool_it_couldnt_read(http, monkeypatch, write, failure):
    """With no record, FCC can't know where the spool is, so the edge doesn't run:
    the write goes out as the caller sent it, with no `archived`, no location blank,
    no note and no trail blanks, and the spool stays where it is. That covers a
    write carrying the weight left and a write carrying both the used and the
    initial weight. RED on d60c86e: the PATCH carried `archived: True`,
    `location: ''` and the trail blanks, decided from the weight alone."""
    http.add("spool", 57, {"physical_source": '"PM-DB-1"', "physical_source_slot": '"1"'},
             location="XL-1", initial_weight=1000.0, used_weight=700.0, archived=False)
    monkeypatch.setattr(sm_api, "get_spool", lambda sid: copy.deepcopy(failure))
    out = sm_api.update_spool(57, dict(write))
    assert out is not None, sm_api.LAST_SPOOLMAN_ERROR
    (_entity, _sid, body), = http.patches
    assert body == write, body
    rec = http.records["spool"][57]
    assert rec["archived"] is False and rec["location"] == "XL-1", rec
    assert rec["extra"] == {"physical_source": '"PM-DB-1"', "physical_source_slot": '"1"'}, rec


def test_control_a_spool_read_with_no_known_capacity_is_still_archived(http):
    """Control (green on d60c86e too): the edge needs a record, not a capacity. A
    spool FCC read, with no weight of its own and none on its filament, weighed to
    nothing left is archived and Unassigned, its note saying where it was."""
    http.add("spool", 57, {}, location="CR-SHELF", initial_weight=None, used_weight=None, archived=False)
    assert sm_api.update_spool(57, {"remaining_weight": 0}) is not None, sm_api.LAST_SPOOLMAN_ERROR
    (_entity, _sid, body), = http.patches
    assert body["archived"] is True and body["location"] == "", body
    assert body["extra"]["fcc_pre_archive_location"] == '"CR-SHELF"', body
