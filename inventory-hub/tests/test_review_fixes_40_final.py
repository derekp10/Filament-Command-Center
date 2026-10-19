"""Group 40's final review (2026-10-19): the engine and placement fixes, over the
REAL move engine (move_engine_harness: FakeSpoolman + LocationsStore; nothing
mocks perform_smart_move) and the real placement model.

Pinned here:
  - engine-1: an eject out of a PolyDryer back into the box its note names keeps
    the plain place behind the note, so a later Swap or eject still finds it;
  - engine-2: the plain place behind '>' is trusted only while it is still a
    plain place (a cart, shelf, row): never a deleted location, never a head;
  - R1 (engine part): a slot move onto a Room never unseats the spools of the
    boxes in it (the read also lists their spools, by prefix);
  - engine-4: Undo asks about a printing head a Swap's displaced spool sits on
    now, and a Swap into a bound slot asks head_fed, then its Load replay swaps;
  - BD-3: the Printer picker's model says when a spool keeps its own trail
    (its PolyDryer follows it head to head), and the engine names that trail
    when it ignores a "came from" answer.

HEAD proof: every test here except the marked controls fails on 7976b72 (see
the commit message).
"""
from __future__ import annotations

import pytest

import logic
import state
from move_engine_harness import IDLE, FakeSpoolman, LocationsStore, _probe_for, run_move

NOTE = logic.PRE_BOX_KEY
PRINTER_MAP = {f"XL-{n}": {"printer_name": "XL", "position": n - 1} for n in (1, 2, 3, 4, 5)}
ROWS = [
    {"LocationID": "LR", "Type": "Room", "Max Spools": "0"},
    {"LocationID": "XL", "Type": "Printer", "Max Spools": "0", "parent_id": "LR",
     "toolheads": [{"location_id": f"XL-{n}", "position": n - 1} for n in (1, 2, 3, 4, 5)]},
    *[{"LocationID": f"XL-{n}", "Type": "Tool Head", "Max Spools": "1", "parent_id": "XL"} for n in (1, 2, 3, 4, 5)],
    {"LocationID": "LR-MDB-1", "Type": "Dryer Box", "Max Spools": "4", "parent_id": "LR",
     "extra": {"slot_targets": {"1": "XL-1", "2": "XL-2", "3": "XL-3", "4": "PRINTER:XL"}}},
    {"LocationID": "LR-MDB-2", "Type": "Dryer Box", "Max Spools": "2", "parent_id": "LR",
     "extra": {"slot_targets": {"1": "XL-4"}}},
    {"LocationID": "PM-DB-1", "Type": "Dryer Box", "Max Spools": "1", "parent_id": "LR", "extra": {}},
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


# --- engine-1 ----------------------------------------------------------------------------

def test_control_the_engine_keeps_the_plain_place_from_a_polydryer_into_a_slot():
    """Control (green on 7976b72): the engine's own move writes the note."""
    sm = FakeSpoolman({60: _sp("PM-DB-2", slot=1, note="LR-MDB-2:2>CR-CT-2-R1")})
    res, _ = _move(sm, "LR-MDB-2", [60], slot="2", auto_deploy=False)
    assert res["status"] == "success" and not res["failures"], res
    assert _note(sm, 60) == "PM-DB-2>CR-CT-2-R1"


def test_an_eject_out_of_a_polydryer_into_its_noted_slot_keeps_the_plain_place():
    sm = FakeSpoolman({60: _sp("PM-DB-2", slot=1, note="LR-MDB-2:2>CR-CT-2-R1")})
    assert _call(sm, lambda: logic.perform_smart_eject(60)) is True
    assert _where(sm, 60)[:2] == ("LR-MDB-2", "2")
    assert _note(sm, 60) == "CR-CT-2-R1", _note(sm, 60)


def test_then_a_swap_files_it_back_on_the_cart_not_unassigned():
    sm = FakeSpoolman({60: _sp("PM-DB-2", slot=1, note="LR-MDB-2:2>CR-CT-2-R1"), 57: _sp("CR-SHELF")})
    store = LocationsStore(ROWS)
    assert _call(sm, lambda: logic.perform_smart_eject(60), store=store) is True
    res, _ = _move(sm, "LR-MDB-2", [57], slot="2", swap_out=True, auto_deploy=False, store=store)
    assert res["status"] == "success" and not res["failures"], res
    assert _where(sm, 60)[0] == "CR-CT-2-R1", _where(sm, 60)
    assert [b["id"] for b in res["to_buffer"]] == [60] and res["to_buffer"][0]["filed_to"] == "CR-CT-2-R1", res


def test_an_eject_back_to_the_noted_polydryer_then_again_reaches_the_cart():
    sm = FakeSpoolman({60: _sp("PM-DB-2", slot=1, note="PM-DB-1>CR-CT-2-R1")})
    store = LocationsStore(ROWS)
    assert _call(sm, lambda: logic.perform_smart_eject(60), store=store) is True
    assert sm.spools[60]["location"] == "PM-DB-1" and _note(sm, 60) == "CR-CT-2-R1", sm.spools[60]
    assert _call(sm, lambda: logic.perform_smart_eject(60), store=store) is True
    assert sm.spools[60]["location"] == "CR-CT-2-R1" and _note(sm, 60) == "", sm.spools[60]


def test_control_an_eject_to_the_plain_place_uses_the_note_up():
    """Control (green on 7976b72): the noted slot is taken, so the spool goes to
    the cart behind the note, which uses the note up."""
    sm = FakeSpoolman({60: _sp("PM-DB-2", slot=1, note="LR-MDB-2:1>CR-CT-2-R1"), 80: _sp("LR-MDB-2", slot=1)})
    assert _call(sm, lambda: logic.perform_smart_eject(60)) is True
    assert sm.spools[60]["location"] == "CR-CT-2-R1" and _note(sm, 60) == "", sm.spools[60]


# --- engine-2 ----------------------------------------------------------------------------

def test_the_eject_fallback_never_files_a_spool_at_a_deleted_place():
    """The cart behind the note was deleted since: Claude's call 21 instead (back
    into the noted box with no slot), never a location FCC no longer has."""
    sm = FakeSpoolman({60: _sp("PM-DB-2", slot=1, note="LR-MDB-2:1>CR-GONE"), 80: _sp("LR-MDB-2", slot=1)})
    assert _call(sm, lambda: logic.perform_smart_eject(60)) is True
    assert _where(sm, 60)[:2] == ("LR-MDB-2", ""), _where(sm, 60)


def test_the_eject_fallback_never_files_a_spool_onto_a_head_its_note_names():
    sm = FakeSpoolman({60: _sp("PM-DB-2", slot=1, note="LR-MDB-2:1>XL-3"), 80: _sp("LR-MDB-2", slot=1),
                       33: _sp("XL-3", src="LR-MDB-1", src_slot=3)})
    assert _call(sm, lambda: logic.perform_smart_eject(60)) is True
    assert sm.direct_at("XL-3") == [33], sm.spools[60]
    assert _where(sm, 60)[:2] == ("LR-MDB-2", ""), _where(sm, 60)


def test_a_swap_never_files_a_spool_onto_a_head_its_note_names():
    sm = FakeSpoolman({57: _sp("CR-SHELF"), 77: _sp("LR-MDB-1", slot=4, note="LR-MDB-2:1>XL-3"),
                       80: _sp("LR-MDB-2", slot=1), 33: _sp("XL-3", src="LR-MDB-1", src_slot=3)})
    res, _ = _move(sm, "LR-MDB-1", [57], slot="4", swap_out=True, probe=_probe_for({"XL"}))
    assert sm.direct_at("XL-3") == [33], (res, sm.spools[77])
    assert sm.spools[77]["location"] == "", sm.spools[77]          # Unassigned (and buffered)


def test_the_swap_place_rule_refuses_a_head_behind_the_note():
    rows = {r["LocationID"]: r for r in ROWS}
    assert logic._swap_out_place("XL-3", "LR-MDB-1", "4", rows, lambda b: set()) == ("", "")
    assert logic._swap_out_place("LR-MDB-2:1>XL-3", "LR-MDB-1", "4", rows, lambda b: {"1"}) == ("", "")
    assert logic._swap_out_place("LR-MDB-2:1>CR-CT-2-R1", "LR-MDB-1", "4", rows,
                                 lambda b: {"1"}) == ("CR-CT-2-R1", "")
    assert logic._is_plain_place("CR-CT-2-R1", rows) is True
    for place in ("XL-3", "XL", "LR", "LR-MDB-2", "PM-DB-1", "CR-GONE", ""):
        assert logic._is_plain_place(place, rows) is False, place


# --- R1 (engine part) --------------------------------------------------------------------

def test_a_slot_move_onto_a_room_unseats_nobody_in_its_boxes():
    """The stale-trail DEPLOYED ↩️ in a Room view used to send exactly this:
    location 'LR', slot 1. The read of 'LR' lists every LR-* box's spools by
    prefix, and each slot-1 spool lost its slot."""
    sm = FakeSpoolman({60: _sp("CR-CT-2-R1", src="LR-MDB-1", src_slot=1),
                       57: _sp("LR-MDB-1", slot=1), 58: _sp("LR-MDB-2", slot=1)})
    _move(sm, "LR", [60], slot="1", auto_deploy=False)
    assert [w for w in sm.writes if w[0] in (57, 58)] == [], sm.writes
    assert _where(sm, 57)[:2] == ("LR-MDB-1", "1") and _where(sm, 58)[:2] == ("LR-MDB-2", "1")


# --- engine-4 ----------------------------------------------------------------------------

def test_undo_asks_about_a_printing_head_a_displaced_spool_sits_on_now():
    sm = FakeSpoolman({57: _sp("CR-SHELF"), 77: _sp("LR-MDB-1", slot=4, note="CR-CT-2-R1")})
    store = LocationsStore(ROWS)
    _move(sm, "LR-MDB-1", [57], slot="4", swap_out=True, store=store)
    record = state.UNDO_STACK[-1]
    assert str(77) in (record.get("displaced") or {}), record
    # #77 since went onto XL-3 by a writer that records no undo (a hand edit).
    sm.spools[77]["location"] = "XL-3"
    ans = _call(sm, lambda: logic.undo_confirm_answer(record), store=store, probe=_probe_for({"XL"}))
    assert ans.get("confirm_type") == "active_print", ans
    assert any(a.get("toolhead") == "XL-3" for a in ans.get("active_prints") or []), ans


def test_a_swap_into_a_bound_slot_asks_head_fed_then_its_load_replay_swaps_and_undo_restores_all():
    sm = FakeSpoolman({57: _sp("CR-SHELF"), 77: _sp("LR-MDB-1", slot=1, note="CR-CT-2-R1"),
                       99: _sp("XL-1", src="PM-DB-2", src_slot=1)})
    store = LocationsStore(ROWS)
    res, _ = _move(sm, "LR-MDB-1", [57], slot="1", swap_out=True, store=store, expected_feed="XL-1")
    assert res["status"] == "requires_confirm" and res["confirm_type"] == "head_fed", res
    assert sm.writes == []
    key = res["fed_heads"][0]["confirm_key"]
    res2, _ = _move(sm, "LR-MDB-1", [57], slot="1", swap_out=True, store=store, expected_feed="XL-1",
                    confirmed_fed_heads=[key])
    assert res2["status"] == "success" and res2.get("auto_deployed_to") == "XL-1", res2
    assert _where(sm, 77)[0] == "CR-CT-2-R1" and sm.direct_at("XL-1") == [57]
    undone = _call(sm, logic.perform_undo, store=store)
    assert undone["success"] is True, undone
    assert sm.direct_at("XL-1") == [99] and _where(sm, 77)[:2] == ("LR-MDB-1", "1")
    assert _where(sm, 57)[0] == "CR-SHELF"


# --- BD-3 --------------------------------------------------------------------------------

def test_the_engine_names_the_trail_it_kept_over_a_came_from_answer():
    rows = [r if r["LocationID"] != "PM-DB-2" else dict(r, extra={"slot_targets": {"1": "XL-2"}}) for r in ROWS]
    sm = FakeSpoolman({50: _sp("XL-2", src="PM-DB-2", src_slot=1)})
    res, store = _move(sm, "XL-3", [50], store=LocationsStore(rows),
                       record_source={"box": "LR-MDB-1", "slot": "3"})
    assert res["status"] == "success" and res.get("record_source_ignored") is True, res
    assert res.get("record_source_kept") == "PM-DB-2", res
    assert _where(sm, 50)[2] == "PM-DB-2" and store.bound("PM-DB-2") == "XL-3"


def _printer_model(spools, pm_target):
    from test_placement_options import ROWS as PROWS, _box, _build
    rows = [r if r["LocationID"] != "PM-DB-2" else _box("PM-DB-2", 1, {"1": pm_target} if pm_target else {})
            for r in PROWS]
    model, status = _build(spools, "XL", rows=rows, spool=spools[0]["id"])
    assert status == 200 and model["mode"] == "printer", model
    return model


def _psp(sid, loc, src="", src_slot=""):
    from test_placement_options import _sp as psp
    return psp(sid, loc, src=src, src_slot=src_slot)


def test_the_printer_model_says_a_polydryer_spool_keeps_its_trail_head_to_head():
    model = _printer_model([_psp(50, "XL-2", src="PM-DB-2", src_slot=1)], "XL-2")
    assert model["spool_keeps_trail"] == "PM-DB-2", model


@pytest.mark.parametrize("spool,pm_target", [
    (lambda: _psp(50, "XL-2", src="PM-DB-2", src_slot=1), "XL-1"),     # its box is attached to another head
    (lambda: _psp(61, "XL-2", src="LR-MDB-1", src_slot=2), "XL-2"),    # a multi-slot trail: dropped head to head
    (lambda: _psp(62, "CR-CT-2-R1"), "XL-2"),                          # not on a head
])
def test_the_printer_model_keeps_no_trail_otherwise(spool, pm_target):
    model = _printer_model([spool()], pm_target)
    assert model["spool_keeps_trail"] == "", model
