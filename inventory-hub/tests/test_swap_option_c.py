"""Group 40, Swap option C (Derek, 2026-10-15 evening; all three points
confirmed the same evening). A slot's stored spool that a Swap takes out (the
Location Manager grid's Swap, the slot picker's) goes into the scan buffer as
before, AND is filed back where it sat before it went into that slot:

  - another slot, or a single-slot box, only while no other spool claims it
    ("shouldn't bump a spool in a slot if it's not empty"), and never the slot
    it was just swapped out of;
  - else the last plain place it sat in before any slot (a cart, shelf,
    drawer: "a non slot ... like a cart, a box, a wall shelf, whatever");
  - a spool slotted before FCC kept that record: Unassigned + the buffer, never
    the box without a slot (the 5/4 he wants gone): "seems right for now".
  - The same-slot swap's old spool (built as Unassigned + the buffer in 40.2)
    follows the same rule: "one rule".

FCC remembers "where it sat before" in the same note single-slot boxes already
keep (`fcc_pre_box_location`, Group 42.6): "LR-MDB-2:1>CR-CT-2-R1" is the slot it
came from, then the plain place behind it. Undo puts a swapped spool back in its
slot and out of the buffer.

The REAL engine runs over tests/move_engine_harness.py ([[mocked engine hides
chain bugs]]); the doors run through the Flask test client.
HEAD proof (0b0eeb7): see the commit message.
"""
from __future__ import annotations

import copy
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import logic  # noqa: E402
import state  # noqa: E402
from move_engine_harness import IDLE, FakeSpoolman, LocationsStore, run_move  # noqa: E402

NOTE = logic.PRE_BOX_KEY
PRINTER_MAP = {f"XL-{n}": {"printer_name": "XL", "position": n - 1} for n in (1, 2, 3)}
ROWS = [
    {"LocationID": "LR", "Type": "Room", "Max Spools": "0"},
    {"LocationID": "XL", "Type": "Printer", "Max Spools": "0", "parent_id": "LR",
     "toolheads": [{"location_id": f"XL-{n}", "position": n - 1} for n in (1, 2, 3)]},
    *[{"LocationID": f"XL-{n}", "Type": "Tool Head", "Max Spools": "1", "parent_id": "XL"} for n in (1, 2, 3)],
    {"LocationID": "LR-MDB-1", "Type": "Dryer Box", "Max Spools": "4", "parent_id": "LR",
     "extra": {"slot_targets": {"1": "XL-1", "2": "XL-2", "3": "XL-3", "4": "PRINTER:XL"}}},
    {"LocationID": "LR-MDB-2", "Type": "Dryer Box", "Max Spools": "2", "parent_id": "LR", "extra": {}},
    {"LocationID": "PM-DB-2", "Type": "Dryer Box", "Max Spools": "1", "parent_id": "LR", "extra": {}},
    {"LocationID": "CR-CT-2-R1", "Type": "Cart Row", "Max Spools": "0", "parent_id": "LR"},
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


@pytest.fixture
def client():
    import app as app_module
    app_module.app.config["TESTING"] = True
    return app_module.app.test_client()


def _sp(loc, slot="", note=None, src="", src_slot=""):
    extra = {"container_slot": str(slot)}
    if src:
        extra["physical_source"] = src
        extra["physical_source_slot"] = str(src_slot)
    if note is not None:
        extra[NOTE] = note
    return {"location": loc, "extra": extra}


def _move(sm, target, spools, slot=None, store=None, probe=IDLE, **kw):
    store = store or LocationsStore(ROWS)
    res = run_move(sm, probe=probe, store=store, printer_map=PRINTER_MAP,
                   target=target, raw_spools=list(spools), target_slot=slot, origin="test", **kw)
    return res, store


def _call(sm, fn, store=None, probe=IDLE):
    return run_move(sm, probe=probe, store=store or LocationsStore(ROWS), printer_map=PRINTER_MAP, call=fn)


def _note(sm, sid):
    return (sm.spools[sid].get("extra") or {}).get(NOTE, "")


def _where(sm, sid):
    extra = sm.spools[sid].get("extra") or {}
    return (sm.spools[sid]["location"], extra.get("container_slot", ""),
            extra.get("physical_source", ""), extra.get("physical_source_slot", ""))


def _buffer_ids():
    return [b.get("id") for b in state.GLOBAL_BUFFER if isinstance(b, dict)]


# ---- the note: where a spool sat before its slot ----------------------------------------------------

def test_a_spool_put_in_a_slot_from_a_cart_remembers_the_cart():
    sm = FakeSpoolman({57: _sp("CR-CT-2-R1")})
    res, _ = _move(sm, "LR-MDB-2", [57], slot="1")
    assert res["status"] == "success" and not res["failures"], res
    assert _where(sm, 57)[:2] == ("LR-MDB-2", "1")
    assert _note(sm, 57) == "CR-CT-2-R1"


def test_slot_to_slot_remembers_the_slot_and_the_cart_behind_it():
    sm = FakeSpoolman({57: _sp("LR-MDB-2", slot=1, note="CR-CT-2-R1")})
    res, _ = _move(sm, "LR-MDB-1", [57], slot="4")
    assert res["status"] == "success" and not res["failures"], res
    assert _note(sm, 57) == "LR-MDB-2:1>CR-CT-2-R1"


def test_a_slot_change_inside_one_box_remembers_the_old_slot():
    sm = FakeSpoolman({57: _sp("LR-MDB-2", slot=1, note="CR-CT-2-R1")})
    _move(sm, "LR-MDB-2", [57], slot="2")
    assert _where(sm, 57)[:2] == ("LR-MDB-2", "2")
    assert _note(sm, 57) == "LR-MDB-2:1>CR-CT-2-R1"


def test_off_a_head_into_another_slot_remembers_the_slot_it_was_deployed_from():
    sm = FakeSpoolman({57: _sp("XL-2", note="CR-CT-2-R1", src="LR-MDB-2", src_slot=1)})
    res, _ = _move(sm, "LR-MDB-1", [57], slot="4")
    assert res["status"] == "success" and not res["failures"], res
    assert _note(sm, 57) == "LR-MDB-2:1>CR-CT-2-R1"


def test_back_into_the_slot_it_was_deployed_from_keeps_what_it_remembers():
    """A Return (or a scan back into its own slot) puts it where it was: the note
    still says where it sat before that slot, for a later Swap."""
    sm = FakeSpoolman({57: _sp("XL-2", note="CR-CT-2-R1", src="LR-MDB-2", src_slot=1)})
    _move(sm, "LR-MDB-2", [57], slot="1", auto_deploy=False)
    assert _where(sm, 57) == ("LR-MDB-2", "1", "", "")
    assert _note(sm, 57) == "CR-CT-2-R1"


def test_onto_a_head_from_a_cart_remembers_the_cart():
    """So a spool put in a slot straight off the head still knows where it sat
    (scanned off the cart onto XL-2, later stored in a slot, later swapped out:
    back to the cart)."""
    sm = FakeSpoolman({57: _sp("CR-CT-2-R1")})
    res, _ = _move(sm, "XL-2", [57])
    assert res["status"] == "success" and sm.direct_at("XL-2") == [57], res
    assert _note(sm, 57) == "CR-CT-2-R1"


def test_a_deploy_from_a_slot_keeps_the_note():
    sm = FakeSpoolman({57: _sp("LR-MDB-1", slot=2, note="CR-CT-2-R1")})
    res, _ = _move(sm, "XL-2", [57])
    assert res["status"] == "success" and sm.direct_at("XL-2") == [57], res
    assert _note(sm, 57) == "CR-CT-2-R1"


def test_moving_to_a_plain_place_uses_the_note_up():
    sm = FakeSpoolman({57: _sp("LR-MDB-2", slot=1, note="CR-CT-2-R1")})
    _move(sm, "CR-SHELF", [57])
    assert sm.spools[57]["location"] == "CR-SHELF" and _note(sm, 57) == ""


@pytest.mark.parametrize("start", ["", "LR"], ids=["unassigned", "a-room"])
def test_into_a_slot_from_a_place_fcc_never_records_remembers_nothing(start):
    """A room is a pain to find (D4) and Unassigned is no place: a stale note is
    dropped, so a later Swap leaves the spool Unassigned rather than guessing."""
    sm = FakeSpoolman({57: _sp(start, note="CR-CT-2-R1")})
    _move(sm, "LR-MDB-2", [57], slot="2")
    assert _where(sm, 57)[:2] == ("LR-MDB-2", "2")
    assert _note(sm, 57) == ""


# ---- Swap: the grid's and the picker's ---------------------------------------------------------------

def _swap_setup(note77, more=None):
    spools = {57: _sp("CR-SHELF"), 77: _sp("LR-MDB-1", slot=4, note=note77)}
    spools.update(more or {})
    return FakeSpoolman(spools)


def test_swap_files_the_old_spool_back_on_its_cart_and_buffers_it():
    state.GLOBAL_BUFFER = [{"id": 57, "display": "#57"}, {"id": 58, "display": "#58"}]
    sm = _swap_setup("CR-CT-2-R1", more={58: _sp("CR-SHELF")})
    res, _ = _move(sm, "LR-MDB-1", [57], slot="4", swap_out=True)
    assert res["status"] == "success" and not res["failures"], res
    assert _where(sm, 57)[:2] == ("LR-MDB-1", "4")
    assert _where(sm, 77) == ("CR-CT-2-R1", "", "", ""), sm.spools[77]
    assert _note(sm, 77) == ""
    # In the user's hand: at the END of the buffer, behind the spools waiting there.
    assert _buffer_ids() == [57, 58, 77]
    [entry] = res["to_buffer"]
    assert entry["id"] == 77 and entry["filed_to"] == "CR-CT-2-R1" and entry["off_head"] == "", entry
    assert any("Swapped #77 out of LR-MDB-1 slot 4 into the scan buffer; FCC files it back in CR-CT-2-R1"
               in str(row) for row in state.RECENT_LOGS), state.RECENT_LOGS


def test_swap_puts_the_old_spool_back_in_the_free_slot_it_came_from():
    sm = _swap_setup("LR-MDB-2:1>CR-CT-2-R1")
    res, _ = _move(sm, "LR-MDB-1", [57], slot="4", swap_out=True)
    assert res["status"] == "success" and not res["failures"], res
    assert _where(sm, 77) == ("LR-MDB-2", "1", "", "")
    # Back where it sat, its note is what it was there: the cart behind it.
    assert _note(sm, 77) == "CR-CT-2-R1"
    assert res["to_buffer"][0]["filed_to"] == "LR-MDB-2 slot 1"


@pytest.mark.parametrize("holder", [
    _sp("LR-MDB-2", slot=1),                                 # stored in it
    _sp("XL-3", src="LR-MDB-2", src_slot=1),                 # deployed from it (still holds it)
], ids=["stored", "deployed-from"])
def test_swap_never_bumps_a_spool_from_the_slot_it_came_from(holder):
    sm = _swap_setup("LR-MDB-2:1>CR-CT-2-R1", more={80: holder})
    before80 = copy.deepcopy(sm.spools[80])
    res, _ = _move(sm, "LR-MDB-1", [57], slot="4", swap_out=True)
    assert res["status"] == "success" and not res["failures"], res
    assert _where(sm, 77) == ("CR-CT-2-R1", "", "", "")
    assert sm.spools[80] == before80
    assert res["to_buffer"][0]["filed_to"] == "CR-CT-2-R1"


def test_swap_never_files_it_back_into_the_slot_it_is_leaving():
    sm = _swap_setup("LR-MDB-1:4>CR-CT-2-R1")
    _move(sm, "LR-MDB-1", [57], slot="4", swap_out=True)
    assert _where(sm, 77) == ("CR-CT-2-R1", "", "", "")


def test_swap_into_a_free_single_slot_box_it_came_from():
    sm = _swap_setup("PM-DB-2>CR-CT-2-R1")
    res, _ = _move(sm, "LR-MDB-1", [57], slot="4", swap_out=True)
    assert _where(sm, 77) == ("PM-DB-2", "1", "", "")
    assert _note(sm, 77) == "CR-CT-2-R1"
    assert res["to_buffer"][0]["filed_to"] == "PM-DB-2"


def test_swap_with_no_record_leaves_it_unassigned_in_the_buffer():
    """Spools slotted before FCC kept the note: Unassigned + the buffer, never
    the box without a slot (Derek: "seems right for now")."""
    sm = _swap_setup(None)
    res, _ = _move(sm, "LR-MDB-1", [57], slot="4", swap_out=True)
    assert _where(sm, 77) == ("", "", "", "")
    assert _buffer_ids() == [77] and res["to_buffer"][0]["filed_to"] == ""
    assert any("Unassigned until it is scanned somewhere" in str(row) for row in state.RECENT_LOGS)


def test_overwrite_still_leaves_the_old_spool_in_the_box_without_a_slot():
    """Not a Swap: unchanged (the grid's and the picker's Overwrite)."""
    sm = _swap_setup("CR-CT-2-R1")
    res, _ = _move(sm, "LR-MDB-1", [57], slot="4")
    assert res["status"] == "success" and "to_buffer" not in res, res
    assert _where(sm, 77)[:2] == ("LR-MDB-1", "")
    assert _note(sm, 77) == "CR-CT-2-R1" and _buffer_ids() == []


def test_a_swap_out_spoolman_rejects_moves_nothing():
    sm = _swap_setup("CR-CT-2-R1")
    sm.reject_ids = {77}
    res, _ = _move(sm, "LR-MDB-1", [57], slot="4", swap_out=True)
    assert res["failures"].get("57", "").startswith("couldn't swap #77 out of slot 4"), res
    assert _where(sm, 57)[0] == "CR-SHELF" and _where(sm, 77)[:2] == ("LR-MDB-1", "4")
    assert _buffer_ids() == [] and "to_buffer" not in res and state.UNDO_STACK == []


def test_undo_puts_the_swapped_spool_back_in_its_slot_and_out_of_the_buffer():
    state.GLOBAL_BUFFER = [{"id": 57, "display": "#57"}]
    sm = _swap_setup("CR-CT-2-R1")
    store = LocationsStore(ROWS)
    _move(sm, "LR-MDB-1", [57], slot="4", swap_out=True, store=store)
    assert _buffer_ids() == [57, 77]
    record = state.UNDO_STACK[-1]
    assert record["displaced"]["77"]["location"] == "LR-MDB-1", record
    asked = _call(sm, lambda: logic.describe_undo(record, PRINTER_MAP), store=store)
    assert asked == "Undo: put #57 back in CR-SHELF and #77 back in LR-MDB-1 slot 4?", asked
    res = _call(sm, logic.perform_undo, store=store)
    assert res["success"] is True, res
    assert _where(sm, 57)[:2] == ("CR-SHELF", "")
    assert _where(sm, 77)[:2] == ("LR-MDB-1", "4") and _note(sm, 77) == "CR-CT-2-R1"
    assert res["unbuffered"] == [77] and 77 not in _buffer_ids(), res
    assert res["restored"] == [57, 77], res
    assert "#77 is back in LR-MDB-1 slot 4" in res["msg"], res


def test_undo_never_puts_the_swapped_spool_on_top_of_one_that_holds_its_slot():
    sm = _swap_setup("CR-CT-2-R1")
    store = LocationsStore(ROWS)
    _move(sm, "LR-MDB-1", [57], slot="4", swap_out=True, store=store)
    sm.reject_ids = {57}   # #57's own restore fails, so it still holds slot 4
    res = _call(sm, logic.perform_undo, store=store)
    assert res["success"] is False, res
    assert "#77 (LR-MDB-1 slot 4 holds #57)" in res["msg"], res
    assert _where(sm, 77)[0] == "CR-CT-2-R1"


# ---- the same-slot swap: one rule ---------------------------------------------------------------------

def test_the_same_slot_swap_files_the_old_spool_back_where_it_sat_before_the_slot():
    """Derek's S2 path: XL-1 runs #99 from LR-MDB-1 slot 1 (it sat on CR-CT-2-R1
    before it went into the slot); #42 is scanned into slot 1. #99 comes off the
    head into the buffer AND is filed back on CR-CT-2-R1 (it used to go to
    Unassigned)."""
    state.GLOBAL_BUFFER = [{"id": 42, "display": "#42"}]
    sm = FakeSpoolman({42: _sp("CR-SHELF"),
                       99: _sp("XL-1", note="CR-CT-2-R1", src="LR-MDB-1", src_slot=1)})
    store = LocationsStore(ROWS)
    res, _ = _move(sm, "LR-MDB-1", [42], slot="1", store=store)
    assert res["status"] == "success" and res.get("auto_deployed_to") == "XL-1", res
    assert sm.direct_at("XL-1") == [42]
    assert _where(sm, 99) == ("CR-CT-2-R1", "", "", "") and _note(sm, 99) == ""
    [entry] = res["to_buffer"]
    assert entry["id"] == 99 and entry["off_head"] == "XL-1" and entry["filed_to"] == "CR-CT-2-R1", entry
    undone = _call(sm, logic.perform_undo, store=store)
    assert undone["success"] is True, undone
    assert _where(sm, 99) == ("XL-1", "", "LR-MDB-1", "1") and _note(sm, 99) == "CR-CT-2-R1"
    assert 99 not in _buffer_ids()


def test_a_spool_ejected_home_into_its_slot_keeps_its_note():
    """Smart Load's eject (and a plain eject) send a head's spool back into the
    slot it was deployed from; its note still says where it sat before that slot
    (it used to be dropped), so a later Swap can file it back there."""
    sm = FakeSpoolman({99: _sp("XL-1", note="CR-CT-2-R1", src="LR-MDB-1", src_slot=1)})
    out = _call(sm, lambda: logic.perform_smart_eject(99, confirm_active_print=True))
    assert out is True
    assert _where(sm, 99)[:2] == ("LR-MDB-1", "1") and _note(sm, 99) == "CR-CT-2-R1"


# ---- a PolyDryer whose noted slot is taken ----------------------------------------------------------

def test_out_of_a_polydryer_whose_noted_slot_is_taken_goes_to_the_plain_place():
    """The same rule for a single-slot box's own "before the box" note (Claude's
    call, listed for Derek's veto): the slot it came from is taken, so the plain
    place behind it, never the box without a slot."""
    sm = FakeSpoolman({60: _sp("PM-DB-2", slot=1, note="LR-MDB-2:1>CR-CT-2-R1"),
                       80: _sp("LR-MDB-2", slot=1)})
    assert _call(sm, lambda: logic.perform_smart_eject(60)) is True
    assert _where(sm, 60) == ("CR-CT-2-R1", "", "", "")


def test_an_old_polydryer_note_with_no_plain_place_keeps_claudes_call_21():
    """A note from before Swap C names no plain place: back into the box,
    unslotted, as Group 42.6 built it."""
    sm = FakeSpoolman({60: _sp("PM-DB-2", slot=1, note="LR-MDB-2:1"),
                       80: _sp("LR-MDB-2", slot=1)})
    assert _call(sm, lambda: logic.perform_smart_eject(60)) is True
    assert _where(sm, 60)[:2] == ("LR-MDB-2", "")


# ---- the doors ------------------------------------------------------------------------------------------

@pytest.mark.parametrize("path, body", [
    ("/api/manage_contents", {"action": "add", "location": "LR-MDB-1", "slot": "4", "spool_id": "ID:57",
                              "confirmed_toolheads": [], "confirmed_fed_heads": []}),
    ("/api/smart_move", {"location": "LR-MDB-1", "spools": [57], "slot": "4", "origin": "buffer",
                         "confirmed_toolheads": [], "confirmed_fed_heads": []}),
], ids=["location-manager", "smart-move"])
@pytest.mark.parametrize("swap", [True, False], ids=["swap", "overwrite"])
def test_the_doors_pass_the_swap(client, path, body, swap):
    sm = _swap_setup("CR-CT-2-R1")
    payload = dict(body, swap=True) if swap else dict(body)
    res = _call(sm, lambda: client.post(path, json=payload)).get_json()
    assert res["status"] == "success" and not res["failures"], res
    if swap:
        assert _where(sm, 77)[0] == "CR-CT-2-R1" and [i["id"] for i in res["to_buffer"]] == [77], res
    else:
        assert _where(sm, 77)[:2] == ("LR-MDB-1", "") and "to_buffer" not in res, res


@pytest.mark.parametrize("value, expected", [
    (True, True), ("true", True), ("True", True), (False, False), (None, False), ("1", False), (1, False),
])
def test_swap_requested_reads_only_a_real_true(value, expected):
    assert logic.swap_requested({"swap": value}) is expected
    assert logic.swap_requested({}) is False and logic.swap_requested(None) is False


# ---- the pure helpers -----------------------------------------------------------------------------------

ROW_MAP = {r["LocationID"]: r for r in ROWS}


@pytest.mark.parametrize("note, place, plain", [
    ("LR-MDB-2:1>CR-CT-2-R1", ("LR-MDB-2", "1"), "CR-CT-2-R1"),
    ("CR-CT-2-R1", ("CR-CT-2-R1", ""), "CR-CT-2-R1"),
    ("LR-MDB-2:1", ("LR-MDB-2", "1"), ""),
    ("PM-DB-2", ("PM-DB-2", ""), ""),              # a box is never the plain place
    ('"cr-ct-2-r1"', ("CR-CT-2-R1", ""), "CR-CT-2-R1"),
    ("", ("", ""), ""),
], ids=["slot+plain", "plain", "slot-only", "single-slot-box", "quoted", "none"])
def test_the_note_reads_its_place_and_the_plain_place_behind_it(note, place, plain):
    assert logic._pre_box_place(note) == place
    assert logic._pre_box_plain(note, ROW_MAP) == plain


def test_an_unreadable_slot_is_passed_over_never_bumped():
    def _boom(box):
        raise RuntimeError("Spoolman down (test)")
    assert logic._swap_out_place("LR-MDB-2:1>CR-CT-2-R1", "LR-MDB-1", "4", ROW_MAP, _boom) == ("CR-CT-2-R1", "")
    assert logic._swap_out_place("LR-MDB-2:1", "LR-MDB-1", "4", ROW_MAP, _boom) == ("", "")


def test_a_plain_place_that_no_longer_exists_is_unassigned():
    assert logic._swap_out_place("GONE-SHELF", "LR-MDB-1", "4", ROW_MAP, lambda b: set()) == ("", "")
    assert logic._swap_out_place("LR-MDB-2:9>CR-CT-2-R1", "LR-MDB-1", "4", ROW_MAP, lambda b: set()) \
        == ("CR-CT-2-R1", "")   # a slot the box doesn't have


# ---- the picker says where a Swap files it ----------------------------------------------------------

def test_the_picker_model_says_where_a_swap_files_each_stored_spool():
    from test_placement_options import _build, _sp as _psp, _slot
    s77 = _psp(77, "LR-MDB-1", slot=2)
    s77["extra"][NOTE] = "CR-CT-2-R1"
    s78 = _psp(78, "LR-MDB-1", slot=3)                  # no record
    s79 = _psp(79, "LR-MDB-1", slot=4)
    s79["extra"][NOTE] = "LR-MDB-2:2>CR-CT-2-R1"        # LR-MDB-2 slot 2 is free
    model, status = _build([s77, s78, s79, _psp(42, "CR-CT-2-R1")], "LR-MDB-1", spool=42)
    assert status == 200
    assert _slot(model, 2)["swap_to"] == "CR-CT-2-R1"
    assert _slot(model, 3)["swap_to"] == ""
    assert _slot(model, 4)["swap_to"] == "LR-MDB-2 slot 2"
    assert _slot(model, 1)["swap_to"] is None           # empty
