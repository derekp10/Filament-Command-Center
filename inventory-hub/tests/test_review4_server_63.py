"""Group 63 review, round 4: the server half of its findings.

Round 4 read round 3's fixes (7a4f9ab..3612032) and found, on the server, in Edit
Spool's take-off of a spool archived ON a toolhead when the Save changes its
Location (63.2's stuck spool):
  - (orange) it ran only when the Save changed another field too: a Save that
    changed only the Location (what "set its Location to Unassigned in Edit Spool"
    advises) wrote nothing first, so the spool stayed hidden on the head when its
    move was refused, a print question named it as loaded, and a single-slot box
    another spool runs from was let go (K24);
  - it left an older pre-archive note in place, so a later refill restored the
    spool to that stale place;
  - its write's lost answer was never read back: the Save said "Nothing was saved,
    and #57 was not moved" though the spool had come off the head, and its
    single-slot box stayed attached there for good.

The REAL route, update_spool and engine over tests/move_engine_harness, location
reads hiding archived spools as Spoolman's do. Every test is RED on 3612032 (the
group's head before round 4's fixes) unless its docstring says control.
"""
from __future__ import annotations

import os
import sys
from contextlib import ExitStack
from unittest.mock import patch

import pytest
import requests

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import archive_takeoff  # noqa: E402
import spoolman_api  # noqa: E402
import state  # noqa: E402
from move_engine_harness import IDLE, LocationsStore, _probe_for, run_move  # noqa: E402
from test_wizard_refill_review_63 import DOOR, PRINTER_MAP, ROWS, _Spoolman, _spool  # noqa: E402

BOX_ROWS = ROWS + [{"LocationID": "PM-DB-2", "Type": "Dryer Box", "Max Spools": "1", "parent_id": "LR",
                    "extra": {"slot_targets": {"1": "XL-1"}}}]


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


def _edit(client, sm, store, spool_data, probe=IDLE, inner=None):
    def call():
        with ExitStack() as st:
            for p in (inner or []):
                st.enter_context(p)
            return client.post("/api/edit_spool_wizard", json=dict(
                {"spool_id": 57, "spool_data": spool_data}, **DOOR))
    return run_move(sm, probe=probe, store=store, printer_map=PRINTER_MAP, call=call).get_json()


def _stuck_on_xl1(note=None, box=False):
    """#57 archived ON XL-1 (63.2's stuck spool), its record holding a comment, so
    a Save that changes only the Location has nothing else to write; #99 runs on
    XL-1, from PM-DB-2 when `box`."""
    trail = {"physical_source": "PM-DB-2", "physical_source_slot": "1"} if box else {}
    s57 = _spool("XL-1", archived=True, used=1000, note=note, **trail)
    s57["comment"] = "a note of its own"
    return _Spoolman({57: s57, 99: _spool("XL-1", archived=False, used=100, **trail)})


def _log_text():
    return [str(e.get("msg", e)) for e in state.RECENT_LOGS]


# ---- a Save that changes only the Location (orange) -------------------------------------------------------

def test_a_location_only_save_onto_another_head_takes_the_spool_off_its_own_first(client):
    """Onto XL-2: an archived spool is never loaded onto a head, so the move is
    refused, and #57 no longer stays hidden on XL-1. RED on 3612032: nothing was
    written first, and it stayed archived ON XL-1."""
    sm = _stuck_on_xl1()
    body = _edit(client, sm, LocationsStore(ROWS), {"location": "XL-2"})
    assert body["success"] is False and body["location_moved"] is False, body
    assert sm.spools[57]["location"] == "" and sm.spools[57]["archived"] is True, sm.spools[57]
    assert "so it was taken off XL-1: it is Unassigned." in body["msg"], body


def test_a_location_only_save_to_a_cart_asks_no_print_question(client):
    """To a cart with XL printing: #57 isn't on XL-1 as far as any print is
    concerned (no head reader lists an archived spool), so it lands with no
    question. RED on 3612032: "#57 is loaded on XL-1. Moving it to CR-CT-2-R2 means
    FCC stops charging this print to it."."""
    sm = _stuck_on_xl1()
    body = _edit(client, sm, LocationsStore(ROWS), {"location": "CR-CT-2-R2"}, probe=_probe_for({"XL"}))
    assert body["success"] is True and body.get("location_moved") is True, body
    assert sm.spools[57]["location"] == "CR-CT-2-R2" and sm.spools[57]["archived"] is True, sm.spools[57]


@pytest.mark.parametrize("to", ["", "CR-CT-2-R2"], ids=["unassigned", "a-cart"])
def test_a_location_only_save_keeps_the_box_another_spool_runs_from(client, to):
    """#57 and #99 both came from PM-DB-2, and #99 runs on XL-1 from it: taking #57
    off keeps PM-DB-2 attached to XL-1 (K24). RED on 3612032: Unassigned went
    through force-unassign, a cart through the engine's move, and either let
    PM-DB-2 go."""
    store = LocationsStore(BOX_ROWS)
    sm = _stuck_on_xl1(box=True)
    body = _edit(client, sm, store, {"location": to})
    assert body["success"] is True, body
    assert sm.spools[57]["location"] == to and sm.spools[57]["archived"] is True, sm.spools[57]
    assert store.bound("PM-DB-2") == "XL-1", store.row("PM-DB-2")
    assert not any("Force Unassigned" in m for m in _log_text()), _log_text()


# ---- its older note ---------------------------------------------------------------------------------------

def test_the_take_off_clears_an_older_note_so_a_later_refill_restores_no_stale_place(client):
    """#57, stuck archived ON XL-1, still holds an old note (PJ-CT-1, dev's #108
    shape). The Save moves it onto XL-2, which is refused; the take-off clears the
    note (the person asked for it elsewhere), so a later weigh back into stock
    leaves it Unassigned. RED on 3612032: the note survived, and the refill put #57
    back on PJ-CT-1."""
    sm = _stuck_on_xl1(note="PJ-CT-1")
    _edit(client, sm, LocationsStore(ROWS), {"location": "XL-2", "comment": "x"})
    assert sm.spools[57]["location"] == "" and sm.spools[57]["archived"] is True, sm.spools[57]
    assert not str(sm.spools[57]["extra"].get("fcc_pre_archive_location") or "").strip('"'), sm.spools[57]
    res = run_move(sm, probe=IDLE, store=LocationsStore(ROWS), printer_map=PRINTER_MAP,
                   call=lambda: client.post("/api/spool/update", json={
                       "id": 57, "updates": {"used_weight": 600}})).get_json()
    assert res.get("location_now", "") == "", res
    assert sm.spools[57]["location"] == "" and sm.spools[57]["archived"] is False, sm.spools[57]


# ---- its write's lost answer -------------------------------------------------------------------------------

class _TakeOffAnswerLost(_Spoolman):
    """The take-off PATCH (location '') lands, and its answer is lost (a read
    timeout: update_spool's timeout is a READ timeout)."""

    lost = False

    def _http_patch(self, url, json=None, **k):
        if (json or {}).get("location") == "" and not self.lost:
            self.lost = True
            super()._http_patch(url, json=json, **k)
            raise requests.exceptions.ReadTimeout("Read timed out. (read timeout=15) (test)")
        return super()._http_patch(url, json=json, **k)


def test_a_take_off_whose_answer_was_lost_is_read_back_and_the_save_goes_on(client):
    """The take-off landed but its answer was lost: it is read back, the Save goes
    on (to the cart), and PM-DB-2, no spool running from it now, lets go. RED on
    3612032: "Nothing was saved, and #57 was not moved", and PM-DB-2 stayed attached
    to XL-1 for good."""
    store = LocationsStore(BOX_ROWS)
    s57 = _spool("XL-1", archived=True, used=1000, physical_source="PM-DB-2", physical_source_slot="1")
    s57["comment"] = "a note of its own"
    sm = _TakeOffAnswerLost({57: s57})
    # The harness fakes Spoolman's reads through get_spool; the read-back's own helper
    # reads the same fake (as test_archive_takeoff_63_2 does).
    body = _edit(client, sm, store, {"location": "CR-CT-2-R2", "comment": "x"},
                 inner=[patch.object(spoolman_api, "get_spool_answer", side_effect=lambda sid: (sm.get_spool(sid), True))])
    assert "Nothing was saved" not in body.get("msg", ""), body
    assert body["success"] is True and body.get("location_moved") is True, body
    assert sm.spools[57]["location"] == "CR-CT-2-R2", sm.spools[57]
    assert store.bound("PM-DB-2") == "", store.row("PM-DB-2")


def test_a_take_off_fcc_couldnt_read_back_says_it_cant_tell_and_is_written_down(client):
    """Its read-back gets no answer either: the Save says it can't tell, never
    "Nothing was saved", and the take-off is written down for archive_takeoff
    (quietly: forgotten if it came off). RED on 3612032."""
    store = LocationsStore(BOX_ROWS)
    s57 = _spool("XL-1", archived=True, used=1000, physical_source="PM-DB-2", physical_source_slot="1")
    s57["comment"] = "a note of its own"
    sm = _TakeOffAnswerLost({57: s57})
    body = _edit(client, sm, store, {"location": "CR-CT-2-R2", "comment": "x"},
                 inner=[patch.object(spoolman_api, "get_spool_answer", return_value=(None, False))])
    assert body["success"] is False and body.get("may_have_saved") is True, body
    assert body["msg"].startswith("Couldn't tell whether Spool #57 saved: ") and "Nothing was saved" not in body["msg"]
    assert "It may be off XL-1 already, and was not moved to CR-CT-2-R2" in body["msg"], body
    (rec,) = archive_takeoff.pending()
    assert rec["sid"] == 57 and rec["place"] == "XL-1" and rec.get("quiet") is True, rec
