"""Group 42.1 — a single-slot box is released when ITS OWN spool leaves the head,
by any path, and never by another spool.

Derek's rule (2026-09-13): "a single-slot box stays bound until ITS OWN spool
leaves that head, by any path (eject, Return, Quick-Swap, any move). Ejecting a
different spool from the head no longer unbinds it." Before this group only the
eject released a box, and it released EVERY single-slot box on the head,
whichever spool left (the I5-15 regression). Return, a buffer scan, Force
Location, a force-unassign and a print to empty all left the box bound.

Step 5 of 42.1: the 13.6 reverse-binding never takes a single-slot box as a
stranger's home. It read a PolyDryer spool's blank slot as free, so a spare
scanned onto a head with a PolyDryer attached (every RCOI head: nothing else
feeds the INDX) recorded that PolyDryer as its home.

The real engine and the REAL single-slot attach / release helpers run against
an in-memory locations.json (move_engine_harness.LocationsStore). Parametrized
over PM-DB-2 and a non-PM box under a real Room, SD-DB-1 (42.7: nothing keys
on the PM prefix).
"""
from __future__ import annotations

import os
import sys
from contextlib import ExitStack
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import app as app_module  # noqa: E402
import logic  # noqa: E402
import spoolman_api  # noqa: E402
import state  # noqa: E402
from deduct_wire_harness import WeightWireSpoolman  # noqa: E402
from move_engine_harness import IDLE, FakeSpoolman, LocationsStore, run_move  # noqa: E402

XL = "🦝 XL"
INDX = "🦝 Core One INDX"
PRINTER_MAP = {
    "XL-1": {"printer_name": XL, "position": 0},
    "XL-2": {"printer_name": XL, "position": 1},
    "XL-4": {"printer_name": XL, "position": 3},
    "RCOI-1": {"printer_name": INDX, "position": 0},
}
BASE = [
    {"LocationID": "LR", "Type": "Room", "Max Spools": "0"},
    {"LocationID": "XL", "Type": "Printer", "Max Spools": "0", "parent_id": "LR",
     "toolheads": [{"location_id": h, "position": p} for h, p in (("XL-1", 0), ("XL-2", 1), ("XL-4", 3))]},
    {"LocationID": "XL-1", "Type": "Tool Head", "Max Spools": "1", "parent_id": "XL"},
    {"LocationID": "XL-2", "Type": "Tool Head", "Max Spools": "1", "parent_id": "XL"},
    {"LocationID": "XL-4", "Type": "Tool Head", "Max Spools": "1", "parent_id": "XL"},
    {"LocationID": "LR-MDB-1", "Type": "Dryer Box", "Max Spools": "4", "parent_id": "LR",
     "extra": {"slot_targets": {"1": "XL-1"}}},
    {"LocationID": "CR", "Type": "Room", "Max Spools": "0"},
    {"LocationID": "CR-CT-2-R1", "Type": "Cart Row", "Max Spools": "0", "parent_id": "CR"},
    {"LocationID": "RCOI", "Type": "Printer", "Max Spools": "0", "parent_id": "CR",
     "toolheads": [{"location_id": "RCOI-1", "position": 0}]},
    {"LocationID": "RCOI-1", "Type": "Tool Head", "Max Spools": "1", "parent_id": "RCOI"},
    {"LocationID": "PM-DB-4", "Type": "Dryer Box", "Max Spools": "1", "parent_id": "PM",
     "extra": {"slot_targets": {"1": "RCOI-1"}}},
]
BOXES = ["PM-DB-2", "SD-DB-1"]


def _box_row(box, head="XL-2"):
    return {"LocationID": box, "Type": "Dryer Box", "Max Spools": "1",
            "parent_id": "PM" if box.startswith("PM-") else "LR",
            "extra": {"slot_targets": {"1": head} if head else {}}}


@pytest.fixture(autouse=True)
def _quiet(monkeypatch):
    monkeypatch.setattr(state, "UNDO_STACK", [])
    monkeypatch.setattr(state, "GLOBAL_BUFFER", [])


@pytest.fixture
def logs(monkeypatch):
    calls = []
    monkeypatch.setattr(state, "add_log_entry", lambda msg, *a, **k: calls.append((msg, a)))
    return calls


@pytest.fixture
def client():
    app_module.app.config["TESTING"] = True
    return app_module.app.test_client()


def _seed(box):
    """#50 lives in `box` and is loaded on XL-2, which `box` is attached to."""
    store = LocationsStore(BASE + [_box_row(box)])
    sm = FakeSpoolman({50: {"location": "XL-2", "extra": {"physical_source": box, "physical_source_slot": "1"}}})
    return store, sm


def _go(sm, store, call=None, **kw):
    return run_move(sm, probe=IDLE, store=store, printer_map=PRINTER_MAP, call=call, **kw)


# --- released: every path a spool leaves its head by --------------------------

@pytest.mark.parametrize("box", BOXES)
def test_eject_sends_it_home_releases_its_box_and_says_both(box, logs):
    store, sm = _seed(box)
    assert _go(sm, store, call=lambda: logic.perform_smart_eject(50)) is True
    assert sm.spools[50]["location"] == box
    assert store.bound(box) == ""
    # Derek, 2026-10-13: "a full sentence in the activity log".
    assert (f"⏏️ Ejected #50 from XL-2 back into {box}; {box} is no longer attached to XL-2.",
            ("WARNING",)) in logs, logs


@pytest.mark.parametrize("box", BOXES)
def test_smart_load_unloading_it_releases_its_box(box, logs):
    store, sm = _seed(box)
    sm.spools[77] = {"location": "CR-CT-2-R1", "extra": {}}
    res = _go(sm, store, target="XL-2", raw_spools=[77])
    assert logic.smart_move_failure(res, 77) == "", res
    assert sm.direct_at("XL-2") == [77] and sm.spools[50]["location"] == box
    assert store.bound(box) == ""


@pytest.mark.parametrize("box", BOXES)
def test_quickswap_return_releases_its_box(box, client, logs):
    """Item A: Return skipped the release entirely."""
    store, sm = _seed(box)
    body = _go(sm, store, call=lambda: client.post("/api/quickswap/return", json={"toolhead": "XL-2"})).get_json()
    assert body.get("action") == "return_done", body
    assert sm.spools[50]["location"] == box
    assert store.bound(box) == ""


@pytest.mark.parametrize("box", BOXES)
@pytest.mark.parametrize("dest, slot", [("CR-CT-2-R1", None), ("LR-MDB-1", "4")],
                         ids=["to-a-cart-row", "into-a-multi-slot-box"])
def test_any_move_off_the_head_releases_its_box(box, dest, slot, logs):
    """Item B: a buffer scan, a Location Manager assign or /api/smart_move off
    the head never released the box."""
    store, sm = _seed(box)
    kw = {"target_slot": slot} if slot else {}
    res = _go(sm, store, target=dest, raw_spools=[50], **kw)
    assert logic.smart_move_failure(res, 50) == "", res
    assert sm.spools[50]["location"] == dest and store.bound(box) == ""
    assert (f"🔓 {box} detached from XL-2 — its spool #50 left the head", ("INFO",)) in logs, logs


@pytest.mark.parametrize("box", BOXES)
def test_force_location_releases_its_box(box, client, logs):
    store, sm = _seed(box)
    body = _go(sm, store, call=lambda: client.post("/api/manage_contents", json={
        "action": "add", "location": "CR-CT-2-R1", "spool_id": 50})).get_json()
    assert logic.smart_move_failure(body, 50) == "", body
    assert sm.spools[50]["location"] == "CR-CT-2-R1" and store.bound(box) == ""


@pytest.mark.parametrize("box", BOXES)
def test_force_unassign_releases_its_box(box, logs):
    store, sm = _seed(box)
    assert _go(sm, store, call=lambda: logic.perform_force_unassign(50)) is True
    assert sm.spools[50]["location"] == "" and store.bound(box) == ""


def _wire_ctx(sm, store):
    """The REAL update_spool / get_spool over WeightWireSpoolman's wire, with the
    live locations store, so the archive edge runs as in production."""
    return [
        patch.object(spoolman_api.requests, "get", side_effect=sm._get),
        patch.object(spoolman_api.requests, "patch", side_effect=sm._patch),
        patch.object(spoolman_api.config_loader, "get_api_urls", return_value=("http://sm", "http://fb")),
        patch.object(logic.config_loader, "load_config", return_value={"printer_map": PRINTER_MAP}),
        patch.object(logic.locations_db, "get_active_printer_map", return_value=PRINTER_MAP),
        patch.object(logic.locations_db, "load_locations_list", side_effect=store.load),
        patch.object(logic.locations_db, "save_locations_list", side_effect=store.save),
        patch.object(logic, "_active_print_info_for_location", return_value=None),
    ]


def _weighed(box):
    return WeightWireSpoolman({50: {
        "location": "XL-2", "initial_weight": 1000, "used_weight": 900, "archived": False,
        "filament": {"weight": 1000},
        "extra": {"physical_source": box, "physical_source_slot": "1"}}})


@pytest.mark.parametrize("box", BOXES)
def test_printed_to_empty_releases_its_box_on_the_archive_edge(box, logs):
    """42.1b: a print deduct that empties the spool archives it and takes it off
    XL-2 inside update_spool, so that edge releases its box."""
    sm, store = _weighed(box), LocationsStore(BASE + [_box_row(box)])
    with ExitStack() as st:
        for p in _wire_ctx(sm, store):
            st.enter_context(p)
        assert spoolman_api.update_spool(50, {"used_weight": 1000})
    assert sm.spools[50]["archived"] is True and sm.spools[50]["location"] == ""
    assert store.bound(box) == ""
    assert (f"🔓 {box} detached from XL-2 — its spool #50 was archived empty", ("INFO",)) in logs, logs


@pytest.mark.parametrize("box", BOXES)
def test_a_weigh_out_to_zero_releases_its_box_once(box, logs):
    """The weigh-out sends the weight with archived: true, then force_unassign.
    The archive edge releases the box; the second call finds nothing to do."""
    sm, store = _weighed(box), LocationsStore(BASE + [_box_row(box)])
    with ExitStack() as st:
        for p in _wire_ctx(sm, store):
            st.enter_context(p)
        assert spoolman_api.update_spool(50, {"used_weight": 1000, "archived": True})
        assert len(store.saves) == 1 and store.bound(box) == ""
        assert logic.perform_force_unassign(50) is True
    assert len(store.saves) == 1, "the box was released twice"


def test_an_archive_that_keeps_its_place_releases_nothing(logs):
    """The caller kept the location (a deduct to a hand-archived spool sends its
    own location, Group 43.2): the spool is still on the head, so is its box."""
    sm, store = _weighed("PM-DB-2"), LocationsStore(BASE + [_box_row("PM-DB-2")])
    with ExitStack() as st:
        for p in _wire_ctx(sm, store):
            st.enter_context(p)
        assert spoolman_api.update_spool(50, {"used_weight": 1000, "location": "XL-2"})
    assert sm.spools[50]["archived"] is True and sm.spools[50]["location"] == "XL-2"
    assert store.saves == [] and store.bound("PM-DB-2") == "XL-2"


# --- stays bound -----------------------------------------------------------------

@pytest.mark.parametrize("box", BOXES)
def test_ejecting_the_other_spool_from_a_doubled_head_leaves_the_box_bound(box, logs):
    """Item C / I5-15: the detach was keyed on the head, so ejecting #60 (not the
    box's spool) unbound the box that feeds #50."""
    store, sm = _seed(box)
    sm.spools[60] = {"location": "XL-2", "extra": {}}
    assert _go(sm, store, call=lambda: logic.perform_smart_eject(60, confirmed_unassign=True)) is True
    assert sm.spools[60]["location"] == "" and store.bound(box) == "XL-2"
    assert store.saves == []


@pytest.mark.parametrize("box", BOXES)
def test_a_rejected_eject_leaves_the_box_bound(box, logs):
    store, sm = _seed(box)
    sm.reject_ids.add(50)
    assert _go(sm, store, call=lambda: logic.perform_smart_eject(50)) is False
    assert sm.spools[50]["location"] == "XL-2" and store.bound(box) == "XL-2"
    assert store.saves == []


def test_a_multi_slot_trail_leaving_the_head_saves_nothing(logs):
    """#240 came from LR-MDB-1 slot 2: a multi-slot box's bindings are user
    config. PM-DB-2, attached to the same head for another spool, stays bound."""
    store = LocationsStore(BASE + [_box_row("PM-DB-2")])
    sm = FakeSpoolman({240: {"location": "XL-2", "extra": {"physical_source": "LR-MDB-1",
                                                            "physical_source_slot": "2"}}})
    res = _go(sm, store, target="CR-CT-2-R1", raw_spools=[240])
    assert logic.smart_move_failure(res, 240) == "", res
    assert store.saves == [] and store.bound("PM-DB-2") == "XL-2"


# --- 42.1 step 5: never a stranger's home -----------------------------------------

def test_a_spare_scanned_onto_a_head_never_takes_its_polydryer_as_home(logs):
    """RCOI-1 runs #60 from PM-DB-4 (attached). Scanning the spare #61 onto
    RCOI-1 sends #60 home into PM-DB-4, and the 13.6 reverse-binding used to
    read PM-DB-4's blank slot as free and record it as #61's home: a later
    Return or eject landed #61 on top of #60."""
    store = LocationsStore(BASE)
    sm = FakeSpoolman({
        60: {"location": "RCOI-1", "extra": {"physical_source": "PM-DB-4", "physical_source_slot": ""}},
        61: {"location": "", "extra": {}},
    })
    res = _go(sm, store, target="RCOI-1", raw_spools=[61])
    assert logic.smart_move_failure(res, 61) == "", res
    assert sm.direct_at("RCOI-1") == [61] and sm.spools[60]["location"] == "PM-DB-4"
    assert (sm.spools[61]["extra"].get("physical_source") or "") == "", sm.spools[61]
    assert store.bound("PM-DB-4") == "", "#60, PM-DB-4's own spool, left RCOI-1"


# --- 42.2: a single-slot box's spool is in slot 1 ---------------------------------

@pytest.mark.parametrize("box", BOXES)
def test_a_spool_put_in_a_single_slot_box_is_in_slot_1_and_its_trail_says_so(box, logs):
    """A box-label scan sends no slot, so the spool was stored with a blank slot,
    and a toolhead's Quick-Swap grid read the PolyDryer as empty while its spool
    was loaded."""
    store = LocationsStore(BASE + [_box_row(box, head=None)])
    sm = FakeSpoolman({50: {"location": "CR-CT-2-R1", "extra": {}}})
    assert logic.smart_move_failure(_go(sm, store, target=box, raw_spools=[50]), 50) == ""
    assert sm.spools[50]["extra"]["container_slot"] == "1"
    assert logic.smart_move_failure(_go(sm, store, target="XL-2", raw_spools=[50]), 50) == ""
    assert sm.spools[50]["extra"]["physical_source"] == box
    assert sm.spools[50]["extra"]["physical_source_slot"] == "1"
    assert store.bound(box) == "XL-2"


def test_quickswap_finds_a_legacy_blank_slot_polydryer_spool(logs):
    """/api/quickswap looks the tile's spool up by (box, slot 1)."""
    store = LocationsStore(BASE + [_box_row("PM-DB-2")])
    sm = FakeSpoolman({50: {"location": "XL-2", "extra": {"physical_source": "PM-DB-2",
                                                           "physical_source_slot": ""}}})
    assert _go(sm, store, call=lambda: logic.find_spool_in_slot("PM-DB-2", "1")) == 50


def test_a_doubled_polydryer_has_no_slot_1(logs):
    """Claude's call 20: two blank-slot spools in a Max-1 box stay unsorted;
    neither becomes "slot 1" at random (dev's PM-DB-4 holds three)."""
    store = LocationsStore(BASE + [_box_row("PM-DB-2", head=None)])
    sm = FakeSpoolman({139: {"location": "PM-DB-2", "extra": {}},
                       140: {"location": "PM-DB-2", "extra": {}}})
    assert _go(sm, store, call=lambda: logic.find_spool_in_slot("PM-DB-2", "1")) is None


def test_eject_all_keeps_ejecting_a_polydryer_spool_in_slot_1(client, logs):
    """Claude's call 19: Eject All leaves slotted spools in place, so slot 1
    alone would have stopped it ejecting a PolyDryer's spool."""
    store = LocationsStore(BASE + [_box_row("PM-DB-2", head=None)])
    sm = FakeSpoolman({18: {"location": "PM-DB-2", "extra": {"container_slot": "1"}}})
    body = _go(sm, store, call=lambda: client.post("/api/manage_contents", json={
        "action": "clear_location", "location": "PM-DB-2", "confirmed_unassign_ids": [18]})).get_json()
    assert body["ejected"] == [18] and body["skipped_slotted"] == [], body


def test_a_spool_put_in_its_polydryer_is_not_deployed_by_the_lifecycle_binding(logs):
    """The box's slot 1 binding records where ITS spool is loaded; it isn't a
    feed. With slot 1 written, the auto-deploy chain would have pushed #77 onto
    XL-2 and unloaded #50, the box's own spool. (Passes before 42.2 too: no
    slot, no chain. It guards the slot-1 change.)"""
    store, sm = _seed("PM-DB-2")
    sm.spools[77] = {"location": "CR-CT-2-R1", "extra": {}}
    assert logic.smart_move_failure(_go(sm, store, target="PM-DB-2", raw_spools=[77]), 77) == ""
    assert sm.direct_at("XL-2") == [50] and sm.spools[77]["location"] == "PM-DB-2"
    assert store.bound("PM-DB-2") == "XL-2"


def test_a_legacy_blank_trail_returns_into_slot_1(logs):
    store, sm = _seed("PM-DB-2")
    sm.spools[50]["extra"]["physical_source_slot"] = ""
    assert _go(sm, store, call=lambda: logic.perform_smart_eject(50)) is True
    assert sm.spools[50]["location"] == "PM-DB-2"
    assert sm.spools[50]["extra"]["container_slot"] == "1"


def test_return_sees_a_lone_legacy_spool_holding_slot_1(client, logs):
    """Return's "that slot is taken" check reads PM-DB-2's lone blank-slot #18 as
    holding slot 1, through the same rule, and says so."""
    store = LocationsStore(BASE + [_box_row("PM-DB-2")])
    sm = FakeSpoolman({
        18: {"location": "PM-DB-2", "extra": {}},
        50: {"location": "XL-2", "extra": {"physical_source": "PM-DB-2", "physical_source_slot": "1"}},
    })
    body = _go(sm, store, call=lambda: client.post("/api/quickswap/return", json={"toolhead": "XL-2"})).get_json()
    assert body.get("action") == "return_done", body
    assert any("PM-DB-2 slot 1 already holds #18" in m for m, a in logs), logs


# --- 42.5c: the grid knows which boxes are single-slot ----------------------------

def test_bindings_for_machine_flags_single_slot_boxes():
    store = LocationsStore(BASE + [_box_row("PM-DB-2")])
    with patch.object(logic.locations_db, "load_locations_list", side_effect=store.load):
        out = logic.locations_db.get_bindings_for_machine(XL, PRINTER_MAP)
    assert out["toolheads"]["XL-2"] == [{"box": "PM-DB-2", "slot": "1", "single_slot": True}], out
    assert out["toolheads"]["XL-1"] == [{"box": "LR-MDB-1", "slot": "1"}], out


# --- 42.6: the box follows its spool, and the "before the box" note -----------------
# Derek's Q-A (2026-09-18): PM-DB-2 follows #50 from XL-2 to XL-4 and #50 keeps
# PM-DB-2 as its home; his caveat (settled 2026-10-13, option 1): remember where
# the spool was before the box, so ejecting it out of the box puts it back there.

BASE_42_6 = BASE + [_box_row("PM-DB-2", head=None),
                    {"LocationID": "CR-CT-2-R2", "Type": "Cart Row", "Max Spools": "0", "parent_id": "CR"}]
NOTE = "fcc_pre_box_location"


def _note(sm, sid):
    return (sm.spools[sid].get("extra") or {}).get(NOTE, "")


def test_derek_s_worked_example_end_to_end(logs):
    """#50 sits on CR-CT-2-R1. Into PM-DB-2 (the note records CR-CT-2-R1), onto
    XL-2, then to XL-4 (PM-DB-2 follows). Eject: back into PM-DB-2. Eject again:
    back on CR-CT-2-R1 with no "unassign?" prompt, and the note is used up."""
    store = LocationsStore(BASE_42_6)
    sm = FakeSpoolman({50: {"location": "CR-CT-2-R1", "extra": {}}})
    for target in ("PM-DB-2", "XL-2", "XL-4"):
        res = _go(sm, store, target=target, raw_spools=[50])
        assert logic.smart_move_failure(res, 50) == "", (target, res)
        assert _note(sm, 50) == "CR-CT-2-R1", (target, sm.spools[50])
    assert sm.spools[50]["extra"]["physical_source"] == "PM-DB-2", "#50 keeps PM-DB-2 as its home"
    assert store.bound("PM-DB-2") == "XL-4", "the box followed its spool"
    assert (f"🔗 PM-DB-2 follows its spool #50 to XL-4", ("INFO",)) in logs, logs

    assert _go(sm, store, call=lambda: logic.perform_smart_eject(50)) is True
    assert sm.spools[50]["location"] == "PM-DB-2" and _note(sm, 50) == "CR-CT-2-R1"
    assert store.bound("PM-DB-2") == ""

    report = {}
    assert _go(sm, store, call=lambda: logic.perform_smart_eject(50, report=report)) is True, \
        "ejecting out of the box asked 'unassign?'"
    assert sm.spools[50]["location"] == "CR-CT-2-R1" and _note(sm, 50) == ""
    assert report["to"] == "CR-CT-2-R1" and report["home"] is True, report
    assert ("⏏️ Ejected #50 from PM-DB-2 back to CR-CT-2-R1.", ("WARNING",)) in logs, logs


def test_a_spool_from_a_multi_slot_box_goes_back_to_its_slot(logs):
    """Claude's call 21: "LR-MDB-1 slot 4" goes back to slot 4 while it's free."""
    store = LocationsStore(BASE_42_6)
    sm = FakeSpoolman({60: {"location": "LR-MDB-1", "extra": {"container_slot": "4"}}})
    _go(sm, store, target="PM-DB-2", raw_spools=[60])
    assert _note(sm, 60) == "LR-MDB-1:4"
    assert _go(sm, store, call=lambda: logic.perform_smart_eject(60)) is True
    assert sm.spools[60]["location"] == "LR-MDB-1" and sm.spools[60]["extra"]["container_slot"] == "4"


def test_its_slot_taken_meanwhile_it_goes_back_unslotted_with_a_warning(logs):
    store = LocationsStore(BASE_42_6)
    sm = FakeSpoolman({60: {"location": "PM-DB-2", "extra": {"container_slot": "1", NOTE: "LR-MDB-1:4"}},
                       61: {"location": "LR-MDB-1", "extra": {"container_slot": "4"}}})
    assert _go(sm, store, call=lambda: logic.perform_smart_eject(60)) is True
    assert sm.spools[60]["location"] == "LR-MDB-1" and sm.spools[60]["extra"]["container_slot"] == ""
    assert any("#60 went back into LR-MDB-1 unslotted: slot 4" in m and a[0] == "WARNING" for m, a in logs), logs


@pytest.mark.parametrize("origin", ["CR", "XL-2", ""], ids=["a-room", "a-toolhead", "unassigned"])
def test_a_room_a_head_or_unassigned_is_never_recorded(origin, logs):
    store = LocationsStore(BASE_42_6)
    sm = FakeSpoolman({62: {"location": origin, "extra": {}}})
    assert logic.smart_move_failure(_go(sm, store, target="PM-DB-2", raw_spools=[62]), 62) == ""
    assert _note(sm, 62) == ""


@pytest.mark.parametrize("move", ["to-a-shelf", "force-unassign"])
def test_a_move_elsewhere_uses_the_note_up(move, logs):
    store = LocationsStore(BASE_42_6)
    sm = FakeSpoolman({50: {"location": "PM-DB-2", "extra": {"container_slot": "1", NOTE: "CR-CT-2-R1"}}})
    if move == "to-a-shelf":
        assert logic.smart_move_failure(_go(sm, store, target="CR-CT-2-R2", raw_spools=[50]), 50) == ""
    else:
        assert _go(sm, store, call=lambda: logic.perform_force_unassign(50)) is True
    assert _note(sm, 50) == ""


def test_a_deleted_origin_falls_back_to_the_prompt(logs):
    store = LocationsStore(BASE_42_6)
    sm = FakeSpoolman({50: {"location": "PM-DB-2", "extra": {"container_slot": "1", NOTE: "GONE-SHELF-9"}}})
    assert _go(sm, store, call=lambda: logic.perform_smart_eject(50)) == "REQUIRE_CONFIRM"
    assert sm.spools[50]["location"] == "PM-DB-2"


def test_the_note_is_a_registered_system_managed_text_field():
    """Spoolman rejects a whole PATCH carrying an unregistered extra, and every
    Undo / Smart Load snapshot writes the system-managed keys: the field must be
    registered at startup (ensure_required_extras) and by setup_fields.py."""
    assert NOTE in spoolman_api.SYSTEM_MANAGED_EXTRAS
    assert (NOTE, "Pre-Box Location (system)", "text") in spoolman_api.REQUIRED_SPOOL_EXTRAS
    assert NOTE in spoolman_api.JSON_STRING_FIELDS
    setup = open(os.path.join(os.path.dirname(__file__), "..", "..", "setup-and-rebuild", "setup_fields.py"),
                 encoding="utf-8").read()
    assert 'create_field("spool", "fcc_pre_box_location", "Pre-Box Location (system)", "text")' in setup
