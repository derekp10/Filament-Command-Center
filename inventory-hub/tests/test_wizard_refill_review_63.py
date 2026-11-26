"""Group 63 review: what an Edit Spool Save's own write did to where the spool is.

The wizard's Save sends the Location field every time, and the route diffs it
against the live record; a changed Location is a move through the engine (Group
40.7). Since Group 63, update_spool's edges move a spool themselves on a Save that
names no new Location: a refill takes a spool archived ON a head off it (and the
page asks where it goes), or sends it back to its note's place; an archive takes
it off its place. The field kept the old place, so the next Save in the same
session moved the spool back (onto the head, unloading the spool loaded there
since). Now:
  - K01 / K02: the answer carries `location_now` / `location_where` whenever the
    Save's own write moved the spool (the page shows it, so the next Save moves
    nothing);
  - K16 / K30: a Save that archives a spool on a head with no move notes the head
    it leaves, as the archive edge does (a tick noted nothing), and a weigh to
    empty whose archive edge took the spool off already writes nothing more (its
    second write cleared the head note the edge had just written);
  - C2: a take-off write that fails is written down for archive_takeoff's
    retries, and the answer says the spool is still on its head;
  - C4: a filament write refused after a refill keeps the refill question (the
    note is used up, so nobody would ever ask again).

The REAL route, update_spool and engine over tests/move_engine_harness (location
reads hide archived spools, as Spoolman's do). Every test is RED on 8153b81 (the
group's head before the review's fixes) unless its docstring says control.
"""
from __future__ import annotations

import copy
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import archive_takeoff  # noqa: E402
import spoolman_api  # noqa: E402
import state  # noqa: E402
from move_engine_harness import IDLE, LocationsStore, WeighedWireSpoolman, _probe_for, run_move  # noqa: E402

PRINTER_MAP = {f"XL-{n}": {"printer_name": "XL", "position": n - 1} for n in (1, 2)}
ROWS = [
    {"LocationID": "LR", "Type": "Room", "Max Spools": "0"},
    {"LocationID": "CR", "Type": "Room", "Max Spools": "0"},
    {"LocationID": "XL", "Type": "Printer", "Max Spools": "0", "parent_id": "LR", "Name": "XL",
     "toolheads": [{"location_id": f"XL-{n}", "position": n - 1} for n in (1, 2)]},
    *[{"LocationID": f"XL-{n}", "Type": "Tool Head", "Max Spools": "1", "parent_id": "XL"} for n in (1, 2)],
    {"LocationID": "CR-CT-2-R2", "Type": "Cart Row", "Max Spools": "0", "parent_id": "CR"},
    {"LocationID": "PJ-CT-1", "Type": "Cart", "Max Spools": "0", "parent_id": "CR"},
]
DOOR = {"confirmed_toolheads": [], "confirmed_fed_heads": []}


class _Spoolman(WeighedWireSpoolman):
    """Location reads list spools in stock only, as Spoolman's do."""

    def _match(self, rec, loc):
        return None if rec.get("archived") else super()._match(rec, loc)


@pytest.fixture(autouse=True)
def _isolate_state():
    prior = (state.RECENT_LOGS, state.UNDO_STACK, state.GLOBAL_BUFFER)
    state.RECENT_LOGS, state.UNDO_STACK, state.GLOBAL_BUFFER = [], [], []
    try:
        yield
    finally:
        state.RECENT_LOGS, state.UNDO_STACK, state.GLOBAL_BUFFER = prior


@pytest.fixture
def client():
    import app as app_module
    app_module.app.config["TESTING"] = True
    return app_module.app.test_client()


def _spool(location, *, archived, used, note=None, **extra):
    ex = dict(extra)
    if note is not None:
        ex["fcc_pre_archive_location"] = note
    return {"location": location, "archived": archived, "initial_weight": 1000, "used_weight": used,
            "filament": {"id": 7, "weight": 1000}, "extra": ex}


def _edit(client, sm, spool_data, **body):
    return run_move(sm, probe=IDLE, store=LocationsStore(ROWS), printer_map=PRINTER_MAP,
                    call=lambda: client.post("/api/edit_spool_wizard", json=dict(
                        {"spool_id": 57, "spool_data": spool_data}, **DOOR, **body))).get_json()


def _note(sm):
    return sm.spools[57]["extra"].get("fcc_pre_archive_location")


# ---- K01 / K02: the answer says where the Save's own write left the spool ----------------------------

def test_a_refill_that_takes_the_spool_off_its_head_says_it_is_unassigned_now(client):
    """#57 is archived ON XL-1 (63.2's stuck spool) and #99 was loaded there since.
    Weighed back in Edit Spool, it is taken off XL-1 and the page asks where it goes;
    the answer says it is Unassigned, so the Location field stops saying XL-1. RED on
    8153b81: no location_now, the field kept XL-1, and the next Save loaded #57 back
    onto XL-1, unloading #99."""
    sm = _Spoolman({57: _spool("XL-1", archived=True, used=1000),
                    99: _spool("XL-1", archived=False, used=100)})
    body = _edit(client, sm, {"location": "XL-1", "used_weight": 600})
    assert body["success"] is True, body
    assert body["location_now"] == "" and body["location_where"] == "Unassigned", body
    assert body["refill_ask"] == {"place": "XL-1", "room": "LR", "held_by": [99]}, body
    assert sm.spools[57]["location"] == "" and sm.spools[99]["location"] == "XL-1"


def test_a_refill_back_to_its_notes_place_says_where_it_went(client):
    """#57 is archived Unassigned, its note CR-CT-2-R2: weighed back, it goes there,
    and the answer says so. RED on 8153b81: the field kept Unassigned, and the next
    Save force-unassigned it."""
    sm = _Spoolman({57: _spool("", archived=True, used=1000, note="CR-CT-2-R2")})
    body = _edit(client, sm, {"location": "", "used_weight": 600})
    assert body["success"] is True and body["location_now"] == "CR-CT-2-R2", body
    assert body["location_where"] == "CR-CT-2-R2" and "refill_ask" not in body, body
    assert sm.spools[57]["location"] == "CR-CT-2-R2"


def test_control_a_save_that_moves_nothing_says_nothing_about_a_place(client):
    sm = _Spoolman({57: _spool("CR-CT-2-R2", archived=False, used=100)})
    body = _edit(client, sm, {"location": "CR-CT-2-R2", "comment": "hello"})
    assert body["success"] is True and "location_now" not in body and "location_moved" not in body, body


# ---- K16 / K30: the head a Save archives the spool off is noted ---------------------------------------

def test_a_weigh_to_empty_on_a_head_keeps_the_head_as_its_note(client):
    """#57 is in stock on XL-1 with an old note (PJ-CT-1, dev's #108 shape). Weighed
    to empty in Edit Spool, the archive edge takes it off and notes XL-1; nothing
    writes over that. RED on 8153b81: a second take-off write cleared the note, so
    the refill that followed asked nothing."""
    sm = _Spoolman({57: _spool("XL-1", archived=False, used=300, note="PJ-CT-1")})
    body = _edit(client, sm, {"location": "XL-1", "used_weight": 1000})
    assert body["success"] is True, body
    rec = sm.spools[57]
    assert rec["archived"] is True and rec["location"] == "" and _note(sm) == "XL-1", rec
    assert len([b for _s, b in sm.patch_bodies if "location" in b]) == 1, sm.patch_bodies
    # ...so a refill later asks where it goes (Derek: "only after a tool head").
    res = run_move(sm, probe=IDLE, store=LocationsStore(ROWS), printer_map=PRINTER_MAP,
                   call=lambda: client.post("/api/spool/update", json={
                       "id": 57, "updates": {"used_weight": 600}})).get_json()
    assert res["refill_ask"]["place"] == "XL-1", res


def test_a_tick_on_a_head_notes_the_head(client):
    """A tick of Archived on a spool on XL-1: the Save takes it off the head (2026-10-20
    review) and notes XL-1, so an untick or a refill later asks. RED on 8153b81: the
    take-off noted nothing."""
    sm = _Spoolman({57: _spool("XL-1", archived=False, used=300)})
    body = _edit(client, sm, {"location": "XL-1", "archived": True})
    assert body["success"] is True and body["location_now"] == "", body
    assert sm.spools[57]["location"] == "" and _note(sm) == "XL-1", sm.spools[57]


# ---- C2: a take-off that fails is written down ---------------------------------------------------------

class _TakeOffRefused(_Spoolman):
    """Every PATCH that takes #57 off its place is refused ("database is locked")."""

    def _http_patch(self, url, json=None, **k):
        if (json or {}).get("location") == "":
            self.patch_bodies.append((57, copy.deepcopy(json)))
            return MagicMock(ok=False, status_code=500, text='{"message": "database is locked"}',
                             json=MagicMock(return_value={"message": "database is locked"}))
        return super()._http_patch(url, json=json, **k)


def test_a_tick_whose_take_off_fails_is_written_down_and_said(client):
    """The tick archives #57 on XL-1; taking it off is refused. It is written down for
    archive_takeoff's retries, and the Save's warning says so. RED on 8153b81: an
    ERROR line only, nothing retried, and the Save answered plain success: #57 hidden
    on XL-1 with nothing to show it."""
    sm = _TakeOffRefused({57: _spool("XL-1", archived=False, used=300)})
    body = _edit(client, sm, {"location": "XL-1", "archived": True})
    assert body["success"] is True, body
    assert "#57 is archived but still at XL-1: FCC couldn't take it off there, and keeps trying." \
        in body.get("warning", ""), body
    (rec,) = archive_takeoff.pending()
    assert rec["sid"] == 57 and rec["place"] == "XL-1" and "database is locked" in rec["last_error"], rec
    assert sm.spools[57]["archived"] is True and sm.spools[57]["location"] == "XL-1"


# ---- C4: a filament refused after a refill keeps the question ------------------------------------------

def test_a_refused_filament_write_keeps_the_refill_question(client):
    """Weighed back off XL-1 with a filament field changed, and Spoolman refuses the
    filament write: the spool's write landed (Unassigned, its note used up), so the
    answer still asks where it goes and says where it is. RED on 8153b81: the failed
    answer carried no refill_ask, and nobody asked."""
    sm = _Spoolman({57: _spool("", archived=True, used=1000, note="XL-1")})

    def refuse(fid, data):
        spoolman_api.LAST_SPOOLMAN_ERROR = 'HTTP 500: {"message": "database is locked"}'
        return None
    with patch.object(spoolman_api, "update_filament", side_effect=refuse):
        body = _edit(client, sm, {"location": "", "used_weight": 600},
                     filament_id=7, filament_data={"comment": "x"})
    assert body["success"] is False and body["spool_saved"] is True, body
    assert body["refill_ask"]["place"] == "XL-1" and body["archived_now"] is False, body
    assert sm.spools[57]["archived"] is False and sm.spools[57]["location"] == ""


# ---- Group 63 review, round 2 -------------------------------------------------------------------------

def _edit_with(client, sm, spool_data, probe=IDLE, inner=None, **body):
    """_edit, with a probe and, inside the request, `inner` (a list of patches)."""
    def call():
        from contextlib import ExitStack
        with ExitStack() as st:
            for p in (inner or []):
                st.enter_context(p)
            return client.post("/api/edit_spool_wizard", json=dict(
                {"spool_id": 57, "spool_data": spool_data}, **DOOR, **body))
    return run_move(sm, probe=probe, store=LocationsStore(ROWS), printer_map=PRINTER_MAP, call=call).get_json()


def _unreadable(shape):
    import json as _json
    import locations_db as _ldb
    if shape == "corrupt":
        def load(*a, **k):
            raise _ldb.LocationsCorruptError("data/locations.json", _json.JSONDecodeError("Expecting value (test)", "{", 1))
    else:
        def load(*a, **k):
            _ldb._LAST_READ.failed = True
            return []
    return patch.object(_ldb, "load_locations_list", side_effect=load)


@pytest.mark.parametrize("shape", ["corrupt", "disk-refused"])
def test_a_tick_on_a_head_fcc_cant_read_the_places_for_says_so(client, shape):
    """Review round 2 (server-edges-1, the wizard): with locations.json unreadable
    FCC can't tell whether XL-1 is a head, so a ticked spool stays where it is and
    the Save says so. RED on 0f3162c: corrupt, the error escaped after the spool's
    write landed (success false, nothing said about the spool); refused by the disk,
    XL-1 read as no head, and the Save said nothing while #57 sat hidden on it."""
    import locations_db as _ldb
    sm = _Spoolman({57: _spool("XL-1", archived=False, used=300)})
    try:
        body = _edit_with(client, sm, {"location": "XL-1", "archived": True}, inner=[_unreadable(shape)])
    finally:
        _ldb._LAST_READ.failed = False
    assert body["success"] is True, body
    assert ("#57 is archived at XL-1, and FCC couldn't read its list of places to check whether that is a "
            "toolhead") in body.get("warning", ""), body
    assert sm.spools[57]["archived"] is True and sm.spools[57]["location"] == "XL-1"


@pytest.mark.parametrize("spool_data", [
    {"location": "CR-CT-2-R2", "used_weight": 600},
    {"location": "CR-CT-2-R2", "archived": False},
], ids=["refill-and-move", "untick-and-move"])
def test_a_refill_with_a_move_never_brings_the_spool_back_on_its_head(client, spool_data):
    """Review round 2 (server-edges-3). #57 is stuck archived ON XL-1 and #99 runs
    there; the Save weighs it back (or unticks it) AND moves it to a cart, with XL
    printing. The refill takes it off the head first, so the move asks nothing about
    a print and it lands on the cart. RED on 0f3162c: the first write named XL-1, so
    #57 came back in stock ON XL-1 beside #99, and the move asked about the print."""
    sm = _Spoolman({57: _spool("XL-1", archived=True, used=1000),
                    99: _spool("XL-1", archived=False, used=100)})
    body = _edit_with(client, sm, spool_data, probe=_probe_for({"XL"}))
    assert body["success"] is True, body
    assert sm.spools[57]["location"] == "CR-CT-2-R2" and sm.spools[57]["archived"] is False, sm.spools[57]
    assert sm.spools[99]["location"] == "XL-1"


class _FilamentRefused:
    def __init__(self):
        self.p = patch.object(spoolman_api, "update_filament", side_effect=self.refuse)

    @staticmethod
    def refuse(fid, data):
        spoolman_api.LAST_SPOOLMAN_ERROR = 'HTTP 500: {"message": "database is locked"}'
        return None


def test_a_tick_on_a_head_with_a_refused_filament_says_where_it_is(client):
    """Review round 2 (server-edges-4). The tick took #57 off XL-1 (its no-move
    take-off) and the filament write was refused: the failed answer says it is
    Unassigned (location_now ''), so the page's field stops saying XL-1. RED on
    0f3162c: no location_now, and the stale field's next Saves led to loading it
    back onto XL-1."""
    sm = _Spoolman({57: _spool("XL-1", archived=False, used=300)})
    body = _edit_with(client, sm, {"location": "XL-1", "archived": True},
                      inner=[_FilamentRefused().p], filament_id=7, filament_data={"comment": "x"})
    assert body["success"] is False and body["spool_saved"] is True, body
    assert body["location_now"] == "" and "location_moved" not in body, body
    assert "so it was taken off XL-1: it is Unassigned." in body["msg"], body


def test_a_refused_filament_after_a_failed_take_off_names_where_it_is_stuck(client):
    """Review round 2 (server-edges-4, with C2): the take-off was refused too; the
    failed answer's words say the spool is still at XL-1 and FCC keeps trying. RED
    on 0f3162c: the words left it out."""
    sm = _TakeOffRefused({57: _spool("XL-1", archived=False, used=300)})
    body = _edit_with(client, sm, {"location": "XL-1", "archived": True},
                      inner=[_FilamentRefused().p], filament_id=7, filament_data={"comment": "x"})
    assert body["success"] is False, body
    assert "#57 is archived but still at XL-1: FCC couldn't take it off there, and keeps trying." in body["msg"], body


def test_a_take_off_that_couldnt_be_written_down_never_says_keeps_trying(client):
    """Review round 2 (critic): the take-off was refused and the store couldn't write
    it down either, so nothing retries it: the Save's words say what finishes it.
    RED on 0f3162c: "and keeps trying"."""
    sm = _TakeOffRefused({57: _spool("XL-1", archived=False, used=300)})

    def refuse(*a, **k):
        raise PermissionError(13, "Permission denied")
    body = _edit_with(client, sm, {"location": "XL-1", "archived": True},
                      inner=[patch.object(archive_takeoff, "note_stuck", side_effect=refuse)])
    assert body["success"] is True, body
    assert "keeps trying" not in body.get("warning", ""), body
    assert ("#57 is archived but still at XL-1: FCC couldn't take it off there, and couldn't note it to try "
            "again: set its Location to Unassigned to finish it.") in body.get("warning", ""), body
