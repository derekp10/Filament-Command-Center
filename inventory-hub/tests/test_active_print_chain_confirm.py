"""
The 2026-09-12 move-pipeline fixes. An active-print confirm must survive
perform_smart_move's INTERNAL hops, a hop that refuses must never be read as a
success, and a single-occupancy head must never end up holding two spools.

Derek, 2026-09-12 (bulk-move active-print testing report, Feature-Buglist.md):
syncing dev's dryer boxes to match live while a print was running, "items being
assigned to the box, didn't flow to the attached printer toolhead ... even
though i was confirming", and later "I somehow got 2 spools attached to one
toolhead".

  A. The dryer-box -> toolhead AUTO-DEPLOY chain called
     perform_smart_move(bound_toolhead, ...) without confirm_active_print. The
     chained call came back {"status": "requires_confirm"}, and the caller
     still logged "⚡ Auto-deployed" and set `auto_deployed_to`. The box got
     the spool; the toolhead kept its old one.
  B. The SMART LOAD resident eject did `if perform_smart_eject(rid):`. Two of
     that function's refusals are truthy: the active-print refusal (a dict) and
     the protected-unassign refusal (the string "REQUIRE_CONFIRM"). The resident
     stayed on the head and the incoming spool was written anyway -> two spools
     on one toolhead, the exact state Group 21.3 exists to prevent.

The verified investigation behind these fixes
(docs/agent_docs/tasks/active-print-chain-investigation-2026-09-12.md) proved
more defects on the same paths, and two adversarial reviews of the diff found
the rest; all pinned below:
  C. Toolhead-valued ghost trails. A head -> head move recorded the OLD head as
     physical_source; Smart Load then "ejected" a spool from another head back
     onto the target, and an eject returned a spool onto an occupied head.
  D. The dryer/generic branches "cleared" the trail with pop(), which the real
     extras merge KEEPS.
  E. A refused eject detached the toolhead's single-slot box before refusing.
  F. Undo of a Smart Load never put the resident back, an auto-deploy took two
     undos, and (once fixed) undo must not stack the resident onto a head that
     is still loaded.
  G. Quick-Swap Return was undone by the auto-deploy chain, could grab a ghost
     off another head, could unseat a spool staged in its slot, and Return /
     Quick-Swap / the slot-QR assign answered success for rejected writes.

Smart Load decisions (Derek, 2026-09-12):
  - A resident with no saved home goes to the Room its toolhead's printer sits
    in, when the location tree really knows that room; otherwise Unassigned.
  - A resident that cannot be moved (or read) means the incoming spool is NOT
    placed; the refusal is attributed and logged.

Hermetic. Spoolman, both locations.json writers (Group 20.2 attach/detach) and
the PrusaLink HTTP probe are mocked. The probe is patched BELOW the per-move
memo (prusalink_api._probe_printer_state), so the chain sees the same cached
state production does. The fake's location readers mirror
spoolman_api._build_location_match (first-segment prefix and ghost matches),
and WireSpoolman runs the REAL update_spool merge. Unlike
tests/test_toolhead_resident_eject_21_3.py, which mocks perform_smart_eject to
True (the reason it never saw B), these run the REAL perform_smart_eject.
"""
from __future__ import annotations

import copy
import json
import os
import sys
from contextlib import ExitStack
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import logic  # noqa: E402
import state  # noqa: E402

from move_engine_harness import (  # noqa: E402,F401
    IDLE, REAL_UPDATE_SPOOL, FakeSpoolman, LocationsStore, WireSpoolman, _probe_for, _unwire, _wire,
    run_move,
)


PRINTER_MAP = {
    "XL-1": {"printer_name": "XL", "position": 0},
    "XL-3": {"printer_name": "XL", "position": 2},
}
# Flat, prefix-derived tree: nothing says which room the XL printer is in.
LOCATIONS = [
    {"LocationID": "XL-1", "Type": "Tool Head", "Max Spools": "1", "Name": "XL-1"},
    {"LocationID": "XL-3", "Type": "Tool Head", "Max Spools": "1", "Name": "XL-3"},
    {"LocationID": "LR-MDB-1", "Type": "Dryer Box", "Max Spools": "4", "Name": "LR MDB",
     "extra": {"slot_targets": {"3": "XL-3"}}},
    {"LocationID": "CR", "Type": "Room", "Max Spools": "0", "Name": "Computer Room"},
]
# L271 nested tree: XL-1 -> printer XL -> Room LR.
LOCATIONS_PRINTER_IN_ROOM = [
    {"LocationID": "LR", "Type": "Room", "Max Spools": "0", "Name": "Living Room",
     "parent_id": None},
    {"LocationID": "XL", "Type": "Printer", "Max Spools": "0", "Name": "XL",
     "parent_id": "LR"},
    {"LocationID": "XL-1", "Type": "Tool Head", "Max Spools": "1", "Name": "XL-1",
     "parent_id": "XL"},
    {"LocationID": "CR", "Type": "Room", "Max Spools": "0", "Name": "Computer Room",
     "parent_id": None},
]
# Slot 1 (the one auto-slot picks first) feeds XL-3.
LOCATIONS_SLOT1_BOUND = [
    {"LocationID": "XL-3", "Type": "Tool Head", "Max Spools": "1", "Name": "XL-3"},
    {"LocationID": "LR-MDB-1", "Type": "Dryer Box", "Max Spools": "4", "Name": "LR MDB",
     "extra": {"slot_targets": {"1": "XL-3"}}},
    {"LocationID": "CR", "Type": "Room", "Max Spools": "0", "Name": "Computer Room"},
]
# Both heads fed from LR-MDB-1.
LOCATIONS_BOTH_BOUND = [
    {"LocationID": "XL-1", "Type": "Tool Head", "Max Spools": "1", "Name": "XL-1"},
    {"LocationID": "XL-3", "Type": "Tool Head", "Max Spools": "1", "Name": "XL-3"},
    {"LocationID": "LR-MDB-1", "Type": "Dryer Box", "Max Spools": "4", "Name": "LR MDB",
     "extra": {"slot_targets": {"1": "XL-1", "3": "XL-3"}}},
    {"LocationID": "CR", "Type": "Room", "Max Spools": "0", "Name": "Computer Room"},
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
    import app as app_module  # route registration; deferred so logic-only tests don't need it
    app_module.app.config["TESTING"] = True
    return app_module.app.test_client()


def _run(sm, *, probe, locations=None, call=None, **move_kwargs):
    """Run perform_smart_move(**move_kwargs), or `call()`, against the fakes."""
    return run_move(sm, probe=probe, locations=LOCATIONS if locations is None else locations,
                    printer_map=PRINTER_MAP, call=call, **move_kwargs)


def _logs(needle, types=None):
    return [e for e in state.RECENT_LOGS
            if needle in str(e.get("msg", ""))
            and (types is None or e.get("type") in types)]


# ---------------------------------------------------------------------------
# A. Dryer-box slot -> bound toolhead auto-deploy chain
# ---------------------------------------------------------------------------

def test_confirmed_box_move_deploys_onto_the_printing_bound_toolhead():
    """Derek's report, literally: the user confirmed disrupting the XL print, so
    the chained deploy onto XL-3 must land — not bounce off the same guard."""
    sm = FakeSpoolman({240: {"location": "CR", "extra": {}}})

    result = _run(sm, probe=_probe_for({"XL"}),
                  target="LR-MDB-1", raw_spools=[240], target_slot="3",
                  origin="test", confirm_active_print=True)

    assert sm.spools[240]["location"] == "XL-3", (
        f"the confirmed move must reach the bound toolhead; writes={sm.writes!r}")
    assert result.get("auto_deployed_to") == "XL-3", result


def test_autodeploy_refused_by_smart_load_is_not_reported_as_deployed():
    """The chained deploy is refused: XL-3's resident can't go home (Spoolman
    rejects the write). The box placement stands, but neither the result nor
    the Activity Log may claim a deploy, and the reason must be reported.

    #99 runs from LR-MDB-2, not from slot 3, so since Group 40.0c the move asks
    first; the user has said "Load it instead" (confirmed_fed_heads)."""
    sm = FakeSpoolman({
        240: {"location": "CR", "extra": {}},
        99: {"location": "XL-3",
             "extra": {"physical_source": "LR-MDB-2", "physical_source_slot": "1"}},
    }, reject_locations={"LR-MDB-2"})

    result = _run(sm, probe=IDLE,
                  target="LR-MDB-1", raw_spools=[240], target_slot="3", origin="test",
                  confirmed_fed_heads=["XL-3"])

    assert sm.spools[240]["location"] == "LR-MDB-1", sm.writes
    assert sm.direct_at("XL-3") == [99], sm.writes
    assert "auto_deployed_to" not in result, (
        f"a refused chain must not be reported as a deploy: {result!r}")
    assert "still holds #99" in (result.get("auto_deploy_skipped") or {}).get("240", ""), result
    assert result.get("auto_deploy_target") == "XL-3", result
    assert not _logs("Auto-deployed"), (
        f"no ⚡ Auto-deployed line for a deploy that did not happen: {state.RECENT_LOGS!r}")
    assert _logs("NOT deployed", types={"WARNING"}), state.RECENT_LOGS


def test_autodeploy_rejected_by_spoolman_is_not_reported_as_deployed():
    """Spoolman rejects the toolhead write. The chained call returns a
    `success` status with a per-spool `failures` entry — still not a deploy."""
    sm = FakeSpoolman({240: {"location": "CR", "extra": {}}}, reject_locations={"XL-3"})

    result = _run(sm, probe=IDLE,
                  target="LR-MDB-1", raw_spools=[240], target_slot="3", origin="test")

    assert sm.spools[240]["location"] == "LR-MDB-1", sm.writes
    assert "auto_deployed_to" not in result, result
    assert not _logs("Auto-deployed"), state.RECENT_LOGS


def test_autodeploy_skips_a_spool_whose_box_write_was_rejected():
    """The box write is rejected, so the spool never reached the slot. The chain
    used to deploy every spool it was handed anyway, writing it onto the toolhead
    straight from wherever it was."""
    sm = FakeSpoolman({240: {"location": "CR", "extra": {}}}, reject_locations={"LR-MDB-1"})

    result = _run(sm, probe=IDLE,
                  target="LR-MDB-1", raw_spools=[240], target_slot="3", origin="test")

    assert sm.spools[240]["location"] == "CR", sm.writes
    assert not [w for w in sm.writes if w[1].get("location") == "XL-3"], sm.writes
    assert "auto_deployed_to" not in result, result
    assert "240" in result["failures"], result


def test_auto_slot_passes_over_a_slot_whose_head_runs_another_spool():
    """No slot named; slot 1 feeds the PRINTING XL-3, which runs #99 from LR-MDB-2.
    Auto-slot used to take slot 1 AFTER the pre-flight, so the caller's confirm
    was never about XL-3 and the chain skipped the deploy with a warning
    (this test was test_confirm_does_not_cover_the_head_of_an_auto_picked_slot).
    Group 40.0e picks before anything is asked, by the slot picker's rule: slot 2
    is unbound and loads no busy head, so #240 is stored there and XL-3 is never
    touched. (A pick that does feed a busy head is asked about, with
    `target_slot`: test_auto_slot_before_preflight_40_0e.py.)"""
    sm = FakeSpoolman({
        240: {"location": "CR", "extra": {}},
        99: {"location": "XL-3",
             "extra": {"physical_source": "LR-MDB-2", "physical_source_slot": "1"}},
    })

    result = _run(sm, probe=_probe_for({"XL"}), locations=LOCATIONS_SLOT1_BOUND,
                  target="LR-MDB-1", raw_spools=[240], origin="test",
                  confirm_active_print=True)

    assert sm.spools[240]["location"] == "LR-MDB-1", sm.writes
    assert (sm.spools[240].get("extra") or {}).get("container_slot") == "2", sm.spools[240]
    assert sm.direct_at("XL-3") == [99], sm.writes
    assert "auto_deployed_to" not in result and "auto_deploy_skipped" not in result, result


def test_several_spools_into_one_bound_slot_deploy_only_the_last():
    """One slot feeds one toolhead. Each spool sent to slot 3 unseats the one
    before it, so only the last is still in the slot and only it may deploy.
    The chain used to put every spool onto XL-3."""
    sm = FakeSpoolman({240: {"location": "CR", "extra": {}},
                       241: {"location": "CR", "extra": {}}})

    result = _run(sm, probe=IDLE, target="LR-MDB-1", raw_spools=[240, 241],
                  target_slot="3", origin="test")

    assert sm.direct_at("XL-3") == [241], sm.writes
    assert "240" in (result.get("auto_deploy_skipped") or {}), result


def test_a_crashing_autodeploy_leaves_the_box_placement_and_says_why():
    sm = FakeSpoolman({240: {"location": "CR", "extra": {}}})
    real_move = logic.perform_smart_move

    def move(*args, **kwargs):
        if str(kwargs.get("origin", "")).startswith("auto_deploy_from_"):
            raise RuntimeError("boom")
        return real_move(*args, **kwargs)

    def call():
        with patch.object(logic, "perform_smart_move", side_effect=move):
            return logic.perform_smart_move("LR-MDB-1", [240], target_slot="3", origin="test")

    result = _run(sm, probe=IDLE, call=call)

    assert sm.spools[240]["location"] == "LR-MDB-1", sm.writes
    assert "auto_deployed_to" not in result, result
    assert "crashed" in (result.get("auto_deploy_skipped") or {}).get("240", ""), result


@pytest.mark.parametrize("move_result, expected", [
    ({"status": "success", "failures": {}}, ""),
    ({"status": "success"}, ""),
    ({"status": "success", "failures": {"42": "400: nope"}}, "400: nope"),
    ({"status": "error", "msg": "Not loaded: XL-1 still holds #99."}, "Not loaded: XL-1 still holds #99."),
    ({"status": "error"}, "move error"),
    (None, "the move returned no result"),
])
def test_smart_move_failure_reads_the_per_spool_outcome(move_result, expected):
    assert logic.smart_move_failure(move_result, 42) == expected


# ---------------------------------------------------------------------------
# B. Smart Load — the resident of a single-occupancy head must really leave
# ---------------------------------------------------------------------------

def _assert_single_occupancy(sm, result, head="XL-1", incoming=42):
    on_head = sm.direct_at(head)
    assert len(on_head) <= 1, (
        f"{head} holds {on_head} — Smart Load must never leave two spools on one "
        f"head; writes={sm.writes!r}")
    if incoming not in on_head:
        # Refusing the placement is acceptable; doing it SILENTLY is not.
        failed = str(incoming) in (result.get("failures") or {})
        assert result.get("status") != "success" or failed, (
            f"#{incoming} was not placed on {head}, but the result says a clean "
            f"success: {result!r}")


def test_confirmed_active_print_smart_load_ejects_the_resident():
    """Replacing the loaded spool of a PRINTING head with the user's confirm:
    the resident goes home to its box and the new spool is the only one on
    the head."""
    sm = FakeSpoolman({
        42: {"location": "CR", "extra": {}},
        99: {"location": "XL-1",
             "extra": {"physical_source": "LR-MDB-1", "physical_source_slot": "2"}},
    })

    result = _run(sm, probe=_probe_for({"XL"}),
                  target="XL-1", raw_spools=[42], origin="test",
                  confirm_active_print=True)

    assert sm.spools[42]["location"] == "XL-1", sm.writes
    assert sm.spools[99]["location"] == "LR-MDB-1", (
        f"the resident must return to its box; writes={sm.writes!r}")
    _assert_single_occupancy(sm, result)


def test_smart_load_resident_without_a_home_does_not_double_occupy():
    """Idle printer, but the resident has no saved source, so
    perform_smart_eject answers "REQUIRE_CONFIRM" (a truthy string) instead of
    ejecting. That must not be mistaken for a completed eject."""
    sm = FakeSpoolman({
        42: {"location": "CR", "extra": {}},
        99: {"location": "XL-1", "extra": {}},
    })

    result = _run(sm, probe=IDLE, target="XL-1", raw_spools=[42], origin="test")

    _assert_single_occupancy(sm, result)


def test_smart_load_resident_eject_rejected_by_spoolman_does_not_double_occupy():
    """The resident's return write is rejected (perform_smart_eject -> False).
    The incoming spool must not be stacked on top of it."""
    sm = FakeSpoolman({
        42: {"location": "CR", "extra": {}},
        99: {"location": "XL-1",
             "extra": {"physical_source": "LR-MDB-1", "physical_source_slot": "2"}},
    }, reject_locations={"LR-MDB-1"})

    result = _run(sm, probe=IDLE, target="XL-1", raw_spools=[42], origin="test")

    _assert_single_occupancy(sm, result)


def test_smart_load_resident_without_a_home_goes_to_the_printers_room():
    """The tree knows XL-1 -> XL -> Room LR, so the homeless resident lands in
    LR (not Unassigned) and the Activity Log says where it went."""
    sm = FakeSpoolman({
        42: {"location": "CR", "extra": {}},
        99: {"location": "XL-1", "extra": {}},
    })

    result = _run(sm, probe=IDLE, locations=LOCATIONS_PRINTER_IN_ROOM,
                  target="XL-1", raw_spools=[42], origin="test")

    assert sm.spools[42]["location"] == "XL-1", sm.writes
    assert sm.spools[99]["location"] == "LR", (
        f"a homeless resident goes to its printer's room; writes={sm.writes!r}")
    assert [e for e in _logs("#99", types={"WARNING"}) if "LR" in e["msg"]], (
        state.RECENT_LOGS)
    _assert_single_occupancy(sm, result)


def test_smart_load_resident_without_a_home_is_unassigned_when_no_room_is_known():
    """Flat tree: the room can only be guessed from the prefix ("XL" is the
    printer, not a Room row), so the resident is Unassigned — and logged."""
    sm = FakeSpoolman({
        42: {"location": "CR", "extra": {}},
        99: {"location": "XL-1", "extra": {}},
    })

    result = _run(sm, probe=IDLE, target="XL-1", raw_spools=[42], origin="test")

    assert sm.spools[42]["location"] == "XL-1", sm.writes
    assert sm.spools[99]["location"] == "", sm.writes
    assert _logs("#99", types={"WARNING"}), state.RECENT_LOGS
    _assert_single_occupancy(sm, result)


def test_smart_load_refuses_the_incoming_spool_when_the_resident_cannot_move():
    """Spoolman rejects the resident's return write: the incoming spool stays
    where it was, the failure is attributed to it, and an ERROR names it."""
    sm = FakeSpoolman({
        42: {"location": "CR", "extra": {}},
        99: {"location": "XL-1",
             "extra": {"physical_source": "LR-MDB-1", "physical_source_slot": "2"}},
    }, reject_locations={"LR-MDB-1"})

    result = _run(sm, probe=IDLE, target="XL-1", raw_spools=[42], origin="test")

    assert sm.spools[42]["location"] == "CR", sm.writes
    assert sm.spools[99]["location"] == "XL-1", sm.writes
    assert "42" in (result.get("failures") or {}), result
    assert _logs("#42", types={"ERROR"}), state.RECENT_LOGS


def test_an_unreadable_resident_refuses_the_load():
    """#99 really is on XL-1 but Spoolman can't return its record: loading
    blind would stack #42 on it, so the load is refused."""
    sm = FakeSpoolman({
        42: {"location": "CR", "extra": {}},
        99: {"location": "XL-1",
             "extra": {"physical_source": "LR-MDB-1", "physical_source_slot": "2"}},
    }, unreadable={99})

    result = _run(sm, probe=IDLE, target="XL-1", raw_spools=[42], origin="test")

    assert sm.spools[42]["location"] == "CR", sm.writes
    assert "could not be read" in (result.get("failures") or {}).get("42", ""), result


def test_an_unreadable_ghost_does_not_refuse_a_load_onto_an_empty_head():
    """#7 is loaded on XL-3 with a legacy trail naming XL-1, so the matcher lists
    it at XL-1, and its record can't be read. XL-1 is empty: the load proceeds."""
    sm = FakeSpoolman({
        7: {"location": "XL-3", "extra": {"physical_source": "XL-1"}},
        42: {"location": "CR", "extra": {}},
    }, unreadable={7})

    result = _run(sm, probe=IDLE, target="XL-1", raw_spools=[42], origin="test")

    assert result.get("status") == "success" and not result.get("failures"), result
    assert sm.direct_at("XL-1") == [42], sm.writes


def test_a_refused_load_after_a_partial_unload_leaves_an_undo_for_what_moved():
    """A doubled XL-1: #98 goes home, #99 can't. #42 is refused, but #98 did
    move, so that must stay undoable, under a summary that names it."""
    sm = FakeSpoolman({
        42: {"location": "CR", "extra": {}},
        98: {"location": "XL-1",
             "extra": {"physical_source": "LR-MDB-1", "physical_source_slot": "2"}},
        99: {"location": "XL-1", "extra": {"physical_source": "CR-CT-1"}},
    }, reject_locations={"CR-CT-1"})

    result = _run(sm, probe=IDLE, target="XL-1", raw_spools=[42], origin="test")

    assert result.get("status") == "error", result
    assert sm.spools[98]["location"] == "LR-MDB-1", sm.writes
    assert len(state.UNDO_STACK) == 1, state.UNDO_STACK
    assert "#98" in state.UNDO_STACK[-1]["summary"], state.UNDO_STACK[-1]


def test_loading_a_printer_row_never_unloads_its_toolheads():
    """The matcher lists every XL-n spool at the Printer row "XL" (first-segment
    prefix). Loading the row itself must not unload them."""
    locations = LOCATIONS + [{"LocationID": "XL", "Type": "Printer", "Max Spools": "0", "Name": "XL"}]
    sm = FakeSpoolman({
        10: {"location": "XL-1", "extra": {"physical_source": "LR-MDB-1", "physical_source_slot": "1"}},
        11: {"location": "XL-3", "extra": {"physical_source": "LR-MDB-1", "physical_source_slot": "3"}},
        42: {"location": "CR", "extra": {}},
    })
    assert sm.at_location("XL") == [10, 11]  # the matcher's prefix hits

    _run(sm, probe=IDLE, locations=locations, target="XL", raw_spools=[42], origin="test")

    assert sm.direct_at("XL-1") == [10], sm.writes
    assert sm.direct_at("XL-3") == [11], sm.writes


# ---------------------------------------------------------------------------
# C / D. Ghost trails: never a toolhead, and really cleared
# ---------------------------------------------------------------------------

def test_head_to_head_move_takes_the_new_heads_bound_box():
    """#77 moves XL-1 -> XL-3. Its trail used to become "XL-1"; now it starts
    empty and the 13.6 reverse-binding fills in the box slot feeding XL-3."""
    sm = FakeSpoolman({77: {"location": "XL-1", "extra": {
        "physical_source": "LR-MDB-1", "physical_source_slot": "1", "container_slot": ""}}})

    _run(sm, probe=IDLE, target="XL-3", raw_spools=[77], origin="test")

    extra = sm.spools[77].get("extra") or {}
    assert sm.spools[77]["location"] == "XL-3", sm.writes
    assert (extra.get("physical_source"), extra.get("physical_source_slot")) == ("LR-MDB-1", "3"), extra


def test_head_to_head_move_does_not_claim_an_occupied_bound_slot():
    """#240 is staged in LR-MDB-1 slot 3, the slot feeding XL-3. #77 moving onto
    XL-3 must not also claim slot 3, or a later Return unseats #240."""
    sm = FakeSpoolman({
        240: {"location": "LR-MDB-1", "extra": {"container_slot": "3"}},
        77: {"location": "XL-1",
             "extra": {"physical_source": "LR-MDB-1", "physical_source_slot": "1"}},
    })

    _run(sm, probe=IDLE, target="XL-3", raw_spools=[77], origin="test")

    assert (sm.spools[77].get("extra") or {}).get("physical_source") == "", sm.spools[77]
    assert sm.spools[240]["extra"]["container_slot"] == "3", sm.spools[240]


def test_smart_load_skips_a_ghost_resident_from_another_head():
    """Legacy data: #7 is loaded on XL-3 but still carries physical_source XL-1
    from an old head -> head move, so the matcher lists it as a ghost resident of
    XL-1. Loading XL-1 used to "eject" #7 back to its saved source, XL-1, which
    put it next to the incoming spool and emptied XL-3."""
    sm = FakeSpoolman({
        7: {"location": "XL-3", "extra": {"physical_source": "XL-1", "physical_source_slot": ""}},
        42: {"location": "CR", "extra": {}},
    })

    result = _run(sm, probe=IDLE, target="XL-1", raw_spools=[42], origin="test")

    assert sm.direct_at("XL-1") == [42], sm.writes
    assert sm.direct_at("XL-3") == [7], sm.writes
    _assert_single_occupancy(sm, result)


def test_eject_never_returns_a_spool_onto_a_toolhead_trail():
    """#7 (on XL-3) carries a stale physical_source of XL-1, where #99 is
    loaded. Ejecting #7 must not "return" it onto XL-1."""
    sm = FakeSpoolman({
        7: {"location": "XL-3", "extra": {"physical_source": "XL-1"}},
        99: {"location": "XL-1",
             "extra": {"physical_source": "LR-MDB-1", "physical_source_slot": "1"}},
    })

    res = _run(sm, probe=IDLE, call=lambda: logic.perform_smart_eject(7, confirmed_unassign=True))

    assert res is True, res
    assert sm.direct_at("XL-1") == [99], sm.writes
    assert sm.spools[7]["location"] == "", sm.writes


def test_eject_never_returns_onto_a_toolhead_row_outside_the_printer_map():
    """Same, for a toolhead that is a location ROW but not a printer_map key
    (the Group 21.3 'No MMU Direct Load' case)."""
    locations = LOCATIONS + [{"LocationID": "CORE1-M0", "Type": "No MMU Direct Load",
                              "Max Spools": "1", "Name": "Core One Direct Load"}]
    sm = FakeSpoolman({
        7: {"location": "XL-3", "extra": {"physical_source": "CORE1-M0"}},
        99: {"location": "CORE1-M0", "extra": {}},
    })

    res = _run(sm, probe=IDLE, locations=locations,
               call=lambda: logic.perform_smart_eject(7, confirmed_unassign=True))

    assert res is True, res
    assert sm.direct_at("CORE1-M0") == [99], sm.writes


@pytest.mark.parametrize("dest, slot", [("CR", None), ("LR-MDB-2", "1")], ids=["room", "dryer-box"])
def test_moving_off_a_toolhead_clears_the_trail_through_the_real_extras_merge(dest, slot):
    """update_spool read-merge-writes extras, so an OMITTED key keeps its old
    value: the branches used to pop() the trail and the PATCH still carried it.
    The wire body must carry an explicit empty value, and siblings survive."""
    locations = LOCATIONS + [{"LocationID": "LR-MDB-2", "Type": "Dryer Box", "Max Spools": "4",
                              "Name": "LR MDB 2", "extra": {"slot_targets": {}}}]
    sm = WireSpoolman({240: {"location": "XL-3", "extra": {
        "physical_source": "LR-MDB-1", "physical_source_slot": "3", "container_slot": "",
        "sheet_link": "keep-me"}}})
    kwargs = {"target": dest, "raw_spools": [240], "origin": "test"}
    if slot:
        kwargs["target_slot"] = slot

    result = _run(sm, probe=IDLE, locations=locations, **kwargs)

    assert result.get("status") == "success" and not result.get("failures"), result
    _, body = sm.patch_bodies[-1]
    assert body.get("location") == dest, body
    assert body["extra"].get("physical_source") == '""', body
    assert body["extra"].get("physical_source_slot") == '""', body
    assert body["extra"].get("sheet_link") == '"keep-me"', body


# ---------------------------------------------------------------------------
# E. A single-slot box is released by a real eject, never a refused one, and
#    only its OWN spool releases it (Group 20.2's detach-after-write, made
#    spool-keyed by Group 42.1). The real binding helpers run on a live store.
# ---------------------------------------------------------------------------

PM_DB_1_ON_XL_1 = {"LocationID": "PM-DB-1", "Type": "Dryer Box", "Max Spools": "1", "Name": "PolyDryer",
                   "extra": {"slot_targets": {"1": "XL-1"}}}


def test_refused_eject_leaves_the_single_slot_box_bound():
    """#99 on XL-1 has no saved home, so an interactive eject answers
    "REQUIRE_CONFIRM" and writes nothing. It used to detach XL-1's single-slot
    box first, so cancelling the unassign prompt left the box unbound."""
    store = LocationsStore(LOCATIONS + [PM_DB_1_ON_XL_1])
    sm = FakeSpoolman({99: {"location": "XL-1", "extra": {}}})

    res = run_move(sm, probe=IDLE, store=store, printer_map=PRINTER_MAP,
                   call=lambda: logic.perform_smart_eject(99))

    assert res == "REQUIRE_CONFIRM", res
    assert not sm.writes, sm.writes
    assert store.saves == [] and store.bound("PM-DB-1") == "XL-1"


@pytest.mark.parametrize("extra, landed, released", [
    ({"physical_source": "PM-DB-1", "physical_source_slot": "1"}, "PM-DB-1", True),
    ({"physical_source": "LR-MDB-1", "physical_source_slot": "2"}, "LR-MDB-1", False),
    ({}, "", False),
], ids=["own-single-slot-box", "multi-slot-trail", "no-home"])
def test_successful_eject_releases_only_its_own_box_after_the_spool_write(extra, landed, released):
    """Group 42.1 rewrite of the 2026-09-12 pin. The release runs once the
    spool's write has landed, and only for the spool's own single-slot box:
    before, any spool leaving XL-1 (the multi-slot and no-home cases here)
    detached every single-slot box bound to XL-1."""
    store = LocationsStore(LOCATIONS + [PM_DB_1_ON_XL_1])
    sm = FakeSpoolman({99: {"location": "XL-1", "extra": extra}})
    seen = []
    real_detach = logic.locations_db.detach_single_slot_box

    def eject():
        def spy(box, head):
            seen.append((box, head, sm.spools[99]["location"]))
            return real_detach(box, head)
        with patch.object(logic.locations_db, "detach_single_slot_box", side_effect=spy):
            return logic.perform_smart_eject(99, confirmed_unassign=True)

    assert run_move(sm, probe=IDLE, store=store, printer_map=PRINTER_MAP, call=eject) is True
    assert sm.spools[99]["location"] == landed
    if released:
        # Exactly once, and only after #99 had actually left XL-1.
        assert seen == [("PM-DB-1", "XL-1", "PM-DB-1")], seen
        assert store.bound("PM-DB-1") == ""
    else:
        assert store.bound("PM-DB-1") == "XL-1", "a box that wasn't #99's was released"
        assert store.saves == []


# ---------------------------------------------------------------------------
# F. Undo
# ---------------------------------------------------------------------------

def test_undo_of_a_smart_load_puts_the_resident_back_on_the_head():
    """Undo must be a true rollback of a Smart Load: the incoming spool back to
    its origin AND the ejected resident back on the head, ghost trail intact
    (so Return-to-slot still knows its box)."""
    sm = FakeSpoolman({
        42: {"location": "CR", "extra": {}},
        99: {"location": "XL-1",
             "extra": {"physical_source": "LR-MDB-1", "physical_source_slot": "2"}},
    })

    _run(sm, probe=IDLE, target="XL-1", raw_spools=[42], origin="test")
    assert sm.spools[99]["location"] == "LR-MDB-1", sm.writes

    undo = _run(sm, probe=IDLE, call=logic.perform_undo)

    assert undo.get("success") is True, undo
    assert sm.spools[42]["location"] == "CR", sm.writes
    assert sm.spools[99]["location"] == "XL-1", (
        f"undo must put the ejected resident back on the head; writes={sm.writes!r}")
    assert (sm.spools[99].get("extra") or {}).get("physical_source") == "LR-MDB-1", (
        sm.spools[99])


def test_undo_leaves_the_resident_off_a_head_that_is_still_loaded():
    """The incoming spool's restore is rejected, so #42 is still on XL-1. Putting
    #99 back as well would stack two spools on the head; undo must refuse that
    restore, log it, and not answer a clean success."""
    sm = FakeSpoolman({
        42: {"location": "CR", "extra": {}},
        99: {"location": "XL-1",
             "extra": {"physical_source": "LR-MDB-2", "physical_source_slot": "2"}},
    })
    _run(sm, probe=IDLE, target="XL-1", raw_spools=[42], origin="test")
    sm.reject_locations = {"CR"}

    undo = _run(sm, probe=IDLE, call=logic.perform_undo)

    assert sm.direct_at("XL-1") == [42], sm.writes
    assert sm.spools[99]["location"] == "LR-MDB-2", sm.writes
    assert undo.get("success") is False, undo
    assert _logs("#99", types={"ERROR"}), state.RECENT_LOGS


def test_undo_after_the_head_was_reloaded_does_not_double_it_up():
    """Smart Load #42 onto XL-1, eject #42 (no undo record), then a writer that
    records no undo puts #50 there. Undo must not put #99 back on top of #50."""
    sm = FakeSpoolman({
        42: {"location": "CR", "extra": {}},
        50: {"location": "CR", "extra": {}},
        99: {"location": "XL-1",
             "extra": {"physical_source": "LR-MDB-2", "physical_source_slot": "2"}},
    })
    _run(sm, probe=IDLE, target="XL-1", raw_spools=[42], origin="test")
    assert _run(sm, probe=IDLE,
                call=lambda: logic.perform_smart_eject(42, confirmed_unassign=True)) is True
    sm.update_spool(50, {"location": "XL-1"})

    _run(sm, probe=IDLE, call=logic.perform_undo)

    assert sm.direct_at("XL-1") == [50], sm.writes


def test_undo_of_an_autodeploy_is_one_step_and_restores_the_resident():
    """A box-slot assign that auto-deploys onto XL-3, unloading #99 there, is one
    user action. It used to push two undo records (the first undo only pulled
    the spool back into the box), and neither put #99 back. (#99 runs from
    LR-MDB-2, so since Group 40.0c the load is confirmed: confirmed_fed_heads.)"""
    sm = FakeSpoolman({
        240: {"location": "CR", "extra": {}},
        99: {"location": "XL-3",
             "extra": {"physical_source": "LR-MDB-2", "physical_source_slot": "1"}},
    })

    result = _run(sm, probe=IDLE,
                  target="LR-MDB-1", raw_spools=[240], target_slot="3", origin="test",
                  confirmed_fed_heads=["XL-3"])
    assert result.get("auto_deployed_to") == "XL-3", result
    assert sm.spools[99]["location"] == "LR-MDB-2", sm.writes
    assert len(state.UNDO_STACK) == 1, state.UNDO_STACK

    _run(sm, probe=IDLE, call=logic.perform_undo)

    assert sm.spools[240]["location"] == "CR", sm.writes
    assert sm.spools[99]["location"] == "XL-3", sm.writes
    assert (sm.spools[99].get("extra") or {}).get("physical_source") == "LR-MDB-2", sm.spools[99]
    assert not state.UNDO_STACK


# ---------------------------------------------------------------------------
# G. Quick-Swap Return / Quick-Swap / slot-QR assign through the real engine
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("printing", [False, True], ids=["idle", "printing"])
def test_quickswap_return_parks_the_spool_in_its_box(client, printing):
    """#240 sits on XL-3 exactly as a real deploy from LR-MDB-1 slot 3 leaves
    it, and that slot feeds XL-3. Return used to put it in the box and let the
    auto-deploy chain move it straight back onto XL-3 while answering
    return_done (every Return on dev was a round trip); once the chain honoured
    Return's confirm, it would have done that mid-print too."""
    sm = FakeSpoolman({240: {"location": "XL-3", "extra": {
        "physical_source": "LR-MDB-1", "physical_source_slot": "3", "container_slot": ""}}})

    # Mid-print, the overlay showed the banner and the user confirmed XL-3
    # (Group 39.1/39.2: Return now reads `confirmed_toolheads`).
    r = _run(sm, probe=_probe_for({"XL"} if printing else set()),
             call=lambda: client.post("/api/quickswap/return", json={
                 "toolhead": "XL-3", "confirmed_toolheads": ["XL-3"] if printing else []}))

    body = r.get_json()
    assert r.status_code == 200 and body["action"] == "return_done", body
    assert sm.spools[240]["location"] == "LR-MDB-1", sm.writes
    assert (sm.spools[240].get("extra") or {}).get("container_slot") == "3", sm.spools[240]
    assert sm.direct_at("XL-3") == [], sm.writes
    assert not _logs("Auto-deployed"), state.RECENT_LOGS


def test_quickswap_return_off_a_printing_head_asks_first(client):
    """Group 39.2: Return passed confirm_active_print=True unconditionally, so a
    Return whose overlay probe missed the print (it fails open on a timeout)
    emptied a printing head with no warning. 39.4's source check now probes the
    head Return empties and answers return_requires_confirm, in the 29.B3 shape,
    before any write. HEAD proof: return_done."""
    sm = FakeSpoolman({240: {"location": "XL-3", "extra": {
        "physical_source": "LR-MDB-1", "physical_source_slot": "3", "container_slot": ""}}})
    r = _run(sm, probe=_probe_for({"XL"}),
             call=lambda: client.post("/api/quickswap/return", json={"toolhead": "XL-3"}))
    body = r.get_json()
    assert r.status_code == 200 and body["action"] == "return_requires_confirm", body
    assert body["toolhead"] == "XL-3" and body["active_toolhead"] == "XL-3" and body["requested"] == "XL-3"
    assert [(a["toolhead"], a["role"]) for a in body["active_prints"]] == [("XL-3", "source")], body
    assert sm.writes == [] and sm.spools[240]["location"] == "XL-3", sm.writes
    assert _logs("waits for a confirm"), state.RECENT_LOGS


def test_quickswap_return_does_not_unseat_a_spool_staged_in_its_slot(client):
    """#77's trail names LR-MDB-1 slot 3, but #240 is staged there. Return must
    park #77 in a free slot and say which, leaving #240 seated."""
    sm = FakeSpoolman({
        240: {"location": "LR-MDB-1", "extra": {"container_slot": "3"}},
        77: {"location": "XL-3",
             "extra": {"physical_source": "LR-MDB-1", "physical_source_slot": "3"}},
    })

    r = _run(sm, probe=IDLE,
             call=lambda: client.post("/api/quickswap/return", json={"toolhead": "XL-3"}))

    body = r.get_json()
    assert r.status_code == 200 and body["action"] == "return_done", body
    assert sm.spools[240]["extra"]["container_slot"] == "3", sm.spools[240]
    landed = sm.spools[77]["extra"].get("container_slot")
    assert sm.spools[77]["location"] == "LR-MDB-1" and landed not in ("", "3"), sm.spools[77]
    assert body["slot"] == landed, body


def test_quickswap_return_ignores_a_ghost_resident(client):
    """#7 is loaded on XL-3 with a stale physical_source of XL-1, so the matcher
    lists it first (lower id) among XL-1's residents. With slot 1 feeding XL-1,
    Return on XL-1 used to pull #7 off XL-3 into the box and deploy it onto
    XL-1. It must act on #42, which is really there."""
    sm = FakeSpoolman({
        7: {"location": "XL-3", "extra": {"physical_source": "XL-1"}},
        42: {"location": "XL-1",
             "extra": {"physical_source": "LR-MDB-1", "physical_source_slot": "1"}},
    })

    r = _run(sm, probe=IDLE, locations=LOCATIONS_BOTH_BOUND,
             call=lambda: client.post("/api/quickswap/return", json={"toolhead": "XL-1"}))

    body = r.get_json()
    assert body.get("moved") == 42, body
    assert sm.direct_at("XL-3") == [7], sm.writes
    assert sm.spools[42]["location"] == "LR-MDB-1", sm.writes


def test_quickswap_return_refuses_a_head_holding_two_spools(client):
    sm = FakeSpoolman({
        42: {"location": "XL-1",
             "extra": {"physical_source": "LR-MDB-1", "physical_source_slot": "1"}},
        43: {"location": "XL-1",
             "extra": {"physical_source": "LR-MDB-1", "physical_source_slot": "2"}},
    })

    r = _run(sm, probe=IDLE,
             call=lambda: client.post("/api/quickswap/return", json={"toolhead": "XL-1"}))

    body = r.get_json()
    assert r.status_code == 409 and body["action"] == "return_ambiguous", body
    assert body["spools"] == [42, 43], body
    assert (body["toolhead"], body["requested"], body["active_toolhead"]) == ("XL-1", "XL-1", "XL-1"), body
    assert not sm.writes, sm.writes


def test_quickswap_return_reports_a_rejected_box_write(client):
    sm = FakeSpoolman({240: {"location": "XL-3", "extra": {
        "physical_source": "LR-MDB-1", "physical_source_slot": "3"}}},
        reject_locations={"LR-MDB-1"})

    r = _run(sm, probe=IDLE,
             call=lambda: client.post("/api/quickswap/return", json={"toolhead": "XL-3"}))

    body = r.get_json()
    assert r.status_code == 409 and body["action"] == "return_failed", body
    assert sm.spools[240]["location"] == "XL-3", sm.writes
    assert not _logs("Return: Spool", types={"SUCCESS"}), state.RECENT_LOGS


def test_quickswap_return_failure_names_the_requested_toolhead(client):
    """29.B3: in every Return error branch `toolhead` is the REQUESTED value and
    the head actually acted on is `active_toolhead`."""
    sm = FakeSpoolman({240: {"location": "XL-3", "extra": {
        "physical_source": "LR-MDB-1", "physical_source_slot": "3"}}},
        reject_locations={"LR-MDB-1"})

    r = _run(sm, probe=IDLE,
             call=lambda: client.post("/api/quickswap/return", json={"toolhead": "XL"}))

    body = r.get_json()
    assert r.status_code == 409 and body["action"] == "return_failed", body
    assert (body["toolhead"], body["requested"], body["active_toolhead"]) == ("XL", "XL", "XL-3"), body


def test_quickswap_return_reports_an_unreadable_resident_as_a_failure(client):
    """A spool Spoolman can't read is not an empty toolhead: Return must say the
    read failed, not "nothing to return"."""
    sm = FakeSpoolman({240: {"location": "XL-3", "extra": {
        "physical_source": "LR-MDB-1", "physical_source_slot": "3"}}}, unreadable={240})

    r = _run(sm, probe=IDLE,
             call=lambda: client.post("/api/quickswap/return", json={"toolhead": "XL-3"}))

    body = r.get_json()
    assert r.status_code == 409 and body["action"] == "return_failed", body
    assert body["active_toolhead"] == "XL-3" and "could not read #240" in body["error"], body
    assert not sm.writes, sm.writes


def test_slot_qr_assign_reports_a_rejected_load_and_keeps_the_buffer(client):
    """A scanned LOC:box:SLOT:n whose box write Spoolman rejects. The route used
    to log "✅", drop the spool from the buffer and answer assignment_done while
    the spool never moved."""
    state.GLOBAL_BUFFER = [{"id": 42, "display": "#42"}]
    sm = FakeSpoolman({42: {"location": "CR", "extra": {}}}, reject_locations={"LR-MDB-1"})

    r = _run(sm, probe=IDLE, call=lambda: client.post(
        "/api/identify_scan", json={"text": "LOC:LR-MDB-1:SLOT:2", "source": "barcode"}))

    body = r.get_json()
    assert body["action"] == "assignment_failed", body
    assert "rejected" in body["msg"], body
    assert sm.spools[42]["location"] == "CR", sm.writes
    assert [i["id"] for i in state.GLOBAL_BUFFER] == [42], state.GLOBAL_BUFFER
    assert not _logs("✅ Spool #42"), state.RECENT_LOGS


def test_slot_qr_assign_says_why_the_spool_was_not_deployed(client):
    """The spool is loaded into the box slot, but the chain can't deploy it
    (XL-3's resident can't go home). The response must not imply a deploy and
    must carry the reason for the toast. (#99 runs from LR-MDB-2, so the scan is
    the "Load it instead" replay of Group 40.0c's question.)"""
    state.GLOBAL_BUFFER = [{"id": 240, "display": "#240"}]
    sm = FakeSpoolman({
        240: {"location": "CR", "extra": {}},
        99: {"location": "XL-3",
             "extra": {"physical_source": "LR-MDB-2", "physical_source_slot": "1"}},
    }, reject_locations={"LR-MDB-2"})

    r = _run(sm, probe=IDLE, call=lambda: client.post(
        "/api/identify_scan", json={"text": "LOC:LR-MDB-1:SLOT:3", "source": "barcode",
                                    "confirmed_fed_heads": ["XL-3"]}))

    body = r.get_json()
    assert body["action"] == "assignment_done", body
    assert not body.get("auto_deployed_to"), body
    assert body.get("not_deployed_target") == "XL-3", body
    assert "still holds #99" in (body.get("not_deployed") or ""), body
    assert sm.spools[240]["location"] == "LR-MDB-1", sm.writes
    assert state.GLOBAL_BUFFER == [], state.GLOBAL_BUFFER


def test_quickswap_reports_a_rejected_toolhead_write(client):
    sm = FakeSpoolman({240: {"location": "LR-MDB-1", "extra": {"container_slot": "3"}}},
                      reject_locations={"XL-3"})

    r = _run(sm, probe=IDLE, call=lambda: client.post(
        "/api/quickswap", json={"toolhead": "XL-3", "box": "LR-MDB-1", "slot": "3"}))

    body = r.get_json()
    assert r.status_code == 409 and body["action"] == "quickswap_failed", body
    assert sm.spools[240]["location"] == "LR-MDB-1", sm.writes
    assert not _logs("Quick-swap: Spool", types={"SUCCESS"}), state.RECENT_LOGS
