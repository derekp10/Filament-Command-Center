"""Group 63 review, round 3: the server half of its findings.

Round 3 read round 2's fixes and found, on the server:
  - an Edit Spool weigh to empty with locations.json unreadable said the spool "is
    archived at XL-1 … stays hidden there", though its own archive edge had just
    taken it off (Unassigned);
  - an Edit Spool refill (or untick) with a Location change: a spool taken off a
    one-spool place another spool holds was said to be "Unassigned — scan it to
    where you put it" beside the move that put it where the person asked, and one
    archived ON a head logged "FCC asks where it goes" while nothing asked;
  - the listed line's "Take it off" button, pressed after a try had left the spool
    where it was moved to (an archived spool stays where it was put), said to set
    its Location to Unassigned;
  - a Save that archives on a head and moves the spool, whose take-off and
    filament write were both refused, never said the spool was stuck on the head;
  - (the critic) the take-off store's backoff pin ran on another clock, so it held
    with no backoff at all (fixed in test_archive_takeoff_63_2.py itself).

The REAL route, update_spool and engine over tests/move_engine_harness, and
archive_takeoff's real reads and writes over SpoolmanHTTPFake. Every test is RED on
7a4f9ab (the group's head before round 3's fixes) unless its docstring says control.
"""
from __future__ import annotations

import os
import sys
from contextlib import ExitStack

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import archive_takeoff  # noqa: E402
import locations_db  # noqa: E402
import state  # noqa: E402
from move_engine_harness import IDLE, LocationsStore, _probe_for, run_move  # noqa: E402
from test_archive_takeoff_63_2 import _stuck_on_xl1, http  # noqa: E402,F401
from test_wizard_refill_review_63 import (  # noqa: E402
    DOOR, PRINTER_MAP, ROWS, _FilamentRefused, _Spoolman, _spool, _TakeOffRefused, _unreadable)


@pytest.fixture(autouse=True)
def _isolate_state():
    prior = (state.RECENT_LOGS, state.UNDO_STACK, state.GLOBAL_BUFFER)
    state.RECENT_LOGS, state.UNDO_STACK, state.GLOBAL_BUFFER = [], [], []
    try:
        yield
    finally:
        state.RECENT_LOGS, state.UNDO_STACK, state.GLOBAL_BUFFER = prior
        locations_db._LAST_READ.failed = False


@pytest.fixture
def client():
    import app as app_module
    app_module.app.config["TESTING"] = True
    return app_module.app.test_client()


def _edit(client, sm, spool_data, rows=ROWS, probe=IDLE, inner=None, **body):
    def call():
        with ExitStack() as st:
            for p in (inner or []):
                st.enter_context(p)
            return client.post("/api/edit_spool_wizard", json=dict(
                {"spool_id": 57, "spool_data": spool_data}, **DOOR, **body))
    return run_move(sm, probe=probe, store=LocationsStore(rows), printer_map=PRINTER_MAP, call=call).get_json()


def _log_text():
    return [str(e.get("msg", e)) for e in state.RECENT_LOGS]


# ---- a weigh to empty, its places unreadable -------------------------------------------------------------

UNREAD_WORDS = "couldn't read its list of places"


@pytest.mark.parametrize("place", ["XL-1", "CR-CT-2-R2"], ids=["on-a-head", "on-a-cart"])
@pytest.mark.parametrize("shape", ["corrupt", "disk-refused"])
def test_a_weigh_to_empty_fcc_cant_read_the_places_for_says_where_the_spool_is(client, shape, place):
    """#57 is in stock at `place`, and the Save weighs it to empty with locations.json
    unreadable. Its archive edge took it off (Unassigned), and the answer says so,
    never that it "stays hidden" where it was. RED on 7a4f9ab: location_now '' and,
    in the same answer, "#57 is archived at XL-1, and FCC couldn't read its list of
    places … or it stays hidden there"."""
    sm = _Spoolman({57: _spool(place, archived=False, used=300)})
    body = _edit(client, sm, {"location": place, "used_weight": 1000}, inner=[_unreadable(shape)])
    assert body["success"] is True, body
    assert sm.spools[57]["archived"] is True and sm.spools[57]["location"] == "", sm.spools[57]
    assert body["location_now"] == "" and body["location_where"] == "Unassigned", body
    assert UNREAD_WORDS not in body.get("warning", ""), body


@pytest.mark.parametrize("shape", ["corrupt", "disk-refused"])
def test_a_weigh_to_empty_with_a_refused_filament_says_nothing_of_a_hidden_spool(client, shape):
    """Its twin with the filament write refused: the failed answer's words leave it
    out too. RED on 7a4f9ab."""
    sm = _Spoolman({57: _spool("XL-1", archived=False, used=300)})
    body = _edit(client, sm, {"location": "XL-1", "used_weight": 1000},
                 inner=[_unreadable(shape), _FilamentRefused().p], filament_id=7, filament_data={"comment": "x"})
    assert body["success"] is False and body["spool_saved"] is True, body
    assert body["location_now"] == "", body
    assert UNREAD_WORDS not in body["msg"], body


# ---- a refill with a Location change ---------------------------------------------------------------------

BOX_ROWS = ROWS + [{"LocationID": "PM-DB-1", "Type": "Dryer Box", "Max Spools": "1", "parent_id": "LR"}]
TAKEN = "so it is Unassigned"


@pytest.mark.parametrize("spool_data", [
    {"location": "CR-CT-2-R2", "used_weight": 600},
    {"location": "CR-CT-2-R2", "archived": False},
], ids=["refill", "untick"])
def test_a_refill_whose_move_lands_never_says_it_is_unassigned(client, spool_data):
    """#57 is archived in PM-DB-1 (a single-slot box) and #12 is in it now; the Save
    weighs #57 back (or unticks it) and moves it to a cart. It lands there, and the
    answer has no word that it is Unassigned. RED on 7a4f9ab: a 7 s warning "#57 is
    back in stock …, but PM-DB-1 now holds #12, so it is Unassigned — scan it to where
    you put it." beside "✅ #57 → CR-CT-2-R2"."""
    sm = _Spoolman({57: _spool("PM-DB-1", archived=True, used=1000, container_slot="1"),
                    12: _spool("PM-DB-1", archived=False, used=100, container_slot="1")})
    body = _edit(client, sm, spool_data, rows=BOX_ROWS)
    assert body["success"] is True and body["location_moved"] is True, body
    assert sm.spools[57]["location"] == "CR-CT-2-R2" and sm.spools[57]["archived"] is False, sm.spools[57]
    assert TAKEN not in body.get("warning", ""), body


def test_control_a_refill_whose_move_doesnt_land_says_it_is_unassigned(client):
    """Control: the same refill, its move onto XL-2 asked about (XL is printing): the
    spool really is Unassigned, and the warning says so."""
    sm = _Spoolman({57: _spool("PM-DB-1", archived=True, used=1000, container_slot="1"),
                    12: _spool("PM-DB-1", archived=False, used=100, container_slot="1")})
    body = _edit(client, sm, {"location": "XL-2", "used_weight": 600}, rows=BOX_ROWS, probe=_probe_for({"XL"}))
    assert body["success"] is False and body["location_moved"] is False, body
    assert sm.spools[57]["location"] == "" and sm.spools[57]["archived"] is False, sm.spools[57]
    assert TAKEN in body.get("warning", ""), body


@pytest.mark.parametrize("spool_data", [
    {"location": "CR-CT-2-R2", "used_weight": 600},
    {"location": "CR-CT-2-R2", "archived": False},
], ids=["refill", "untick"])
def test_a_refill_off_a_head_with_a_move_never_says_fcc_asks(client, spool_data):
    """#57 is stuck archived ON XL-1 (#99 runs there) and the Save weighs it back and
    moves it to a cart: its first write takes it off XL-1, and the Activity Log says
    so, never "FCC asks where it goes" (nothing asks: the move decides). RED on
    7a4f9ab: "📤 Auto-unarchived Spool #57 (weight refilled) — Unassigned for now: it
    came off XL-1, and FCC asks where it goes", then "🚚 #57 -> CR-CT-2-R2"."""
    sm = _Spoolman({57: _spool("XL-1", archived=True, used=1000, physical_source="PM-DB-2"),
                    99: _spool("XL-1", archived=False, used=100)})
    body = _edit(client, sm, spool_data)
    assert body["success"] is True and "refill_ask" not in body, body
    rec = sm.spools[57]
    assert rec["location"] == "CR-CT-2-R2" and rec["archived"] is False, rec
    assert not str(rec["extra"].get("physical_source") or "").strip('"'), rec
    logs = _log_text()
    assert not any("FCC asks where it goes" in m for m in logs), logs
    assert any("taken off XL-1, now Unassigned" in m for m in logs), logs
    assert sm.spools[99]["location"] == "XL-1"


def test_an_archived_spool_on_a_head_comes_off_it_before_its_move(client):
    """#57 is archived ON XL-1 and the Save changes only its comment and its Location,
    onto XL-2: an archived spool is never loaded onto a head ("untick Archived to load
    it"), so the move is refused, and #57 is no longer left hidden on XL-1: the first
    write took it off, archived, and the answer says where it is. RED on 7a4f9ab: it
    stayed archived ON XL-1."""
    sm = _Spoolman({57: _spool("XL-1", archived=True, used=1000)})
    body = _edit(client, sm, {"location": "XL-2", "comment": "x"})
    assert body["success"] is False and body["location_moved"] is False, body
    assert sm.spools[57]["location"] == "" and sm.spools[57]["archived"] is True, sm.spools[57]
    assert "so it was taken off XL-1: it is Unassigned." in body["msg"], body
    assert any("📦 #57 is archived, so it was taken off XL-1 before its move" in m for m in _log_text())


# ---- the Take it off button after a try left the spool where it was moved -----------------------------

def test_the_button_after_a_try_left_the_spool_where_it_was_moved_says_so(http, client):
    """#57, written down archived on XL-1, was moved to CR-SHELF while archived; a try
    left it there and forgot it. A press on its listed line's button (naming XL-1)
    says it was left where it is, never to unassign it. RED on 7a4f9ab: "set its
    Location to Unassigned in Edit Spool to take it off", a few lines below "FCC left
    it there"."""
    _stuck_on_xl1(http)
    http.records["spool"][57]["location"] = "CR-SHELF"
    archive_takeoff.retry_due(now=1031.0)
    assert archive_takeoff.pending() == []
    body = client.post("/api/spool/archive_takeoff", json={"id": 57, "place": "XL-1"}).get_json()
    assert body == {"success": True, "msg": "#57 isn't at XL-1 any more, so it was left where it is."}, body
    assert http.records["spool"][57]["location"] == "CR-SHELF"


def test_the_button_pressed_twice_answers_the_same(http, client):
    """The first press finds the record and leaves the spool where it was moved; the
    second, with nothing written down, answers the same. RED on 7a4f9ab: the second
    flipped to "set its Location to Unassigned"."""
    _stuck_on_xl1(http)
    http.records["spool"][57]["location"] = "CR-SHELF"
    first = client.post("/api/spool/archive_takeoff", json={"id": 57, "place": "XL-1"}).get_json()
    second = client.post("/api/spool/archive_takeoff", json={"id": 57, "place": "XL-1"}).get_json()
    assert first["success"] is True and "left where it is" in first["msg"], first
    assert second["success"] is True and "left where it is" in second["msg"], second


@pytest.mark.parametrize("place", ["XL-1", None], ids=["at-the-listed-place", "an-older-line"])
def test_control_a_spool_still_at_its_place_with_no_record_is_told_to_unassign_it(http, client, place):
    """Control (round 2's rule): the store was set aside and #57 is still archived on
    XL-1, the place its line names (or a line from before round 3, naming none)."""
    http.add("spool", 57, {}, location="XL-1", initial_weight=1000.0, used_weight=1000.0, archived=True)
    body = client.post("/api/spool/archive_takeoff",
                       json={"id": 57, "place": place} if place else {"id": 57}).get_json()
    assert body["success"] is False and "set its Location to Unassigned" in body["msg"], body


# ---- a refused filament after a failed take-off, with a move ---------------------------------------------

def test_a_refused_filament_with_a_move_names_where_the_spool_is_stuck(client):
    """The Save ticks Archived on #57 (on XL-1) and moves it to a cart; its take-off
    is refused, and so is the filament write, so the move never runs: the words say
    #57 is still on XL-1 and FCC keeps trying. RED on 7a4f9ab: only "#57 was not
    moved to CR-CT-2-R2 either"."""
    sm = _TakeOffRefused({57: _spool("XL-1", archived=False, used=300)})
    body = _edit(client, sm, {"location": "CR-CT-2-R2", "archived": True},
                 inner=[_FilamentRefused().p], filament_id=7, filament_data={"comment": "x"})
    assert body["success"] is False and body["spool_saved"] is True, body
    assert "#57 is archived but still at XL-1: FCC couldn't take it off there, and keeps trying." in body["msg"], body
    assert sm.spools[57]["location"] == "XL-1" and sm.spools[57]["archived"] is True
