"""Group 40.0e — auto-slot picks its slot BEFORE anything is asked, by the one
recommendation rule the slot picker will use (logic.recommend_box_slot).

A slotless single spool into a multi-slot box used to get the lowest free slot
AFTER the active-print pre-flight, so the head that slot feeds was never asked
about: the chain then skipped a printing head's deploy with a warning, or
unloaded an idle head's spool unasked. Now, at step 3 of the pre-write contract:
  1. a spool already sitting in the box keeps its slot;
  2. else the lowest free slot that would load no busy head (unbound, a Printer
     Pool slot, or a head with no spool on it; any free slot for a store-only
     move; never a binding to something that isn't a head);
  3. else the lowest free slot, and the question covers its head;
  4. else (a full box) the spool goes in unslotted, as before.
The pick is a named slot from then on: step 5 probes its head, 40.0c checks
whether that head runs a spool from elsewhere, the answer carries it as
`target_slot`, and the chain carries the caller's confirm. A pick never unseats
anyone: the replay sends it back as `picked_slot` (kept only while still free),
and a spool that takes it during the printer check makes the move refuse (or, in
a single-slot box, go in unslotted). A pick that feeds the head the spool is
leaving stores it there instead of loading it straight back.

The REAL engine runs over tests/move_engine_harness.py with a live locations store.
HEAD proof (97d05aa): the pool-slot test picks slot 1 and unloads #99; the
printing test writes #42 into slot 2 before any question; the rule-3 test loads
over #99 unasked; the own-slot test moves #42 to slot 1; the picked-slot tests
ignore `picked_slot`; the probe-race test unseats #77; the off-the-head test
reloads #42 onto XL-2; the non-head test sends #42 to XL. The full-box,
store-only and box-read-failure tests are controls and pass on HEAD, and so does
the single-slot probe-race test: HEAD picked after the probe, so it pins that
picking first kept 42.2's rule.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import logic  # noqa: E402
import state  # noqa: E402
from move_engine_harness import IDLE, FakeSpoolman, LocationsStore, _probe_for, run_move  # noqa: E402
from test_fed_head_confirm_40_0c import FROM_POLYDRYER, PRINTER_MAP, ROWS  # noqa: E402

# PM-DB-5 is a PolyDryer whose spool runs on XL-2; TST-MDB-1's slot 1 is bound to
# the XL printer row itself (not a head), as a hand-edited binding could be.
ROWS_E = ROWS + [
    {"LocationID": "PM-DB-5", "Type": "Dryer Box", "Max Spools": "1", "parent_id": "LR",
     "extra": {"slot_targets": {"1": "XL-2"}}},
    {"LocationID": "TST-MDB-1", "Type": "Dryer Box", "Max Spools": "4", "parent_id": "LR",
     "extra": {"slot_targets": {"1": "XL"}}},
]


@pytest.fixture(autouse=True)
def _isolate_state():
    prior = (state.RECENT_LOGS, state.UNDO_STACK, state.GLOBAL_BUFFER)
    state.RECENT_LOGS, state.UNDO_STACK, state.GLOBAL_BUFFER = [], [], []
    try:
        yield
    finally:
        state.RECENT_LOGS, state.UNDO_STACK, state.GLOBAL_BUFFER = prior


class _Reads(FakeSpoolman):
    """Records which location each strict spool-list read was for."""
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.read_locs = []

    def at_location_detailed_strict(self, loc):
        self.read_locs.append(str(loc).upper())
        return super().at_location_detailed_strict(loc)


def _in(slot, box="LR-MDB-1"):
    return {"location": box, "extra": {"container_slot": slot}}


def _move(sm, probe=IDLE, store=None, target="LR-MDB-1", **kw):
    return run_move(sm, probe=probe, store=store or LocationsStore(ROWS_E), printer_map=PRINTER_MAP,
                    target=target, raw_spools=[42], origin="test", **kw)


def _slot_of(sm, sid):
    return sm.spools[sid]["extra"].get("container_slot")


def _during_the_probe(change):
    """A probe stub that runs `change()` while FCC asks the XL for its state."""
    def probe(url, name):
        change()
        return IDLE(url, name)
    return probe


def test_a_slot_whose_head_runs_a_spool_from_elsewhere_is_passed_over():
    """The spec's first case: slots 2 and 3 are full, slot 1 is free but XL-1 runs
    #99 from PM-DB-2, and slot 4 (Printer Pool) is free. Slot 4, no question."""
    sm = FakeSpoolman({42: {"location": "CR-CT-2-R1", "extra": {}}, 20: _in("2"), 30: _in("3"),
                       99: {"location": "XL-1", "extra": dict(FROM_POLYDRYER)}})
    res = _move(sm)
    assert res.get("status") == "success" and not res.get("failures"), res
    assert sm.spools[42]["location"] == "LR-MDB-1" and _slot_of(sm, 42) == "4", sm.spools[42]
    assert "auto_deployed_to" not in res and sm.direct_at("XL-1") == [99], res


def test_a_picked_slot_bound_to_a_printing_head_is_asked_about_and_the_replay_loads():
    """The spec's second case: slots 2 (XL-2, empty) and 4 are free and the XL is
    printing. The rule picks slot 2, so the question names XL-2 before anything
    is written, carries target_slot "2" and offers "Just store it". The replay
    (picked_slot "2", XL-2 confirmed) loads #42 onto XL-2: the chain carries the
    confirm (it used to drop it for a slot it picked itself)."""
    sm = FakeSpoolman({42: {"location": "CR-CT-2-R1", "extra": {}}, 10: _in("1"), 30: _in("3")})
    store = LocationsStore(ROWS_E)
    printing = _probe_for({"XL"})
    res = _move(sm, probe=printing, store=store)
    assert res.get("status") == "requires_confirm" and res.get("confirm_type") == "active_print", res
    assert [(a["toolhead"], a["role"]) for a in res["active_prints"]] == [("XL-2", "feeds")], res
    assert res["target_slot"] == "2" and res["can_store"] is True and res["spools"] == [42], res
    assert "LR-MDB-1 slot 2 feeds XL-2" in res["msg"], res["msg"]
    assert sm.writes == [], f"wrote {sm.writes} before the question"

    done = _move(sm, probe=printing, store=store, picked_slot=res["target_slot"],
                 confirm_active_print=["XL-2"])
    assert done.get("auto_deployed_to") == "XL-2", done
    assert sm.direct_at("XL-2") == [42]
    assert (sm.spools[42]["extra"].get("physical_source"),
            sm.spools[42]["extra"].get("physical_source_slot")) == ("LR-MDB-1", "2")


def test_a_picked_slot_taken_while_the_user_decided_moves_nothing():
    """The question picked slot 2. Before the Yes, #77 was put in slot 2. The
    replay must not unseat #77 (an explicit slot would: Overwrite), nor quietly
    pick another slot the user never saw: nothing moves, and it says why."""
    sm = FakeSpoolman({42: {"location": "CR-CT-2-R1", "extra": {}}, 10: _in("1"), 30: _in("3"),
                       77: {"location": "CR-CT-2-R1", "extra": {}}})
    store = LocationsStore(ROWS_E)
    asked = _move(sm, probe=_probe_for({"XL"}), store=store)
    assert asked["target_slot"] == "2", asked
    sm.spools[77] = _in("2")
    res = _move(sm, probe=_probe_for({"XL"}), store=store, picked_slot="2", confirm_active_print=["XL-2"])
    assert res.get("status") == "error" and res.get("blocked_reason") == "picked_slot_taken", res
    assert "LR-MDB-1 slot 2 was taken by #77" in res["msg"], res
    assert sm.writes == [] and _slot_of(sm, 77) == "2"


def test_a_slot_filled_during_the_printer_check_is_never_unseated():
    """The pick is read before the printer probe, which can take seconds. #77 is
    stored in slot 2 meanwhile. Unseating it (the old explicit-slot path) would
    leave it floating; the pick refuses #42 instead, and writes nothing."""
    sm = FakeSpoolman({42: {"location": "CR-CT-2-R1", "extra": {}}, 10: _in("1"), 30: _in("3"),
                       77: {"location": "CR-CT-2-R1", "extra": {}}})
    probe = _during_the_probe(lambda: sm.spools.__setitem__(77, _in("2")))
    res = _move(sm, probe=probe)
    assert "was filled by #77 while FCC was checking the printer" in res["failures"].get("42", ""), res
    assert sm.spools[42]["location"] == "CR-CT-2-R1" and _slot_of(sm, 77) == "2", sm.writes
    assert "auto_deployed_to" not in res, res


def test_a_single_slot_box_filled_during_the_printer_check_takes_the_spool_unslotted():
    """42.2's rule, kept across the probe: #42 leaves XL-3 for PM-DB-3, whose
    slot 1 is free when it looks. Meanwhile PM-DB-3's own #50 goes back in, so
    #42 goes in unslotted and #50 keeps slot 1."""
    sm = FakeSpoolman({42: {"location": "XL-3", "extra": {}},
                       50: {"location": "CR-CT-2-R1", "extra": {}}})
    probe = _during_the_probe(lambda: sm.spools.__setitem__(50, _in("1", box="PM-DB-3")))
    res = _move(sm, probe=probe, target="PM-DB-3")
    assert res.get("status") == "success" and not res.get("failures"), res
    assert sm.spools[42]["location"] == "PM-DB-3" and _slot_of(sm, 42) == "", sm.spools[42]
    assert _slot_of(sm, 50) == "1"


def test_a_slotless_move_off_a_head_into_the_box_feeding_it_stores_without_reloading():
    """The review's round trip: #42 runs on XL-2 from PM-DB-5. Force Location ->
    LR-MDB-1 picks slot 2 (slot 1's XL-1 runs another spool), and slot 2 feeds
    XL-2, the head #42 is leaving. It used to go into slot 2 and be loaded
    straight back onto XL-2 with a new trail. Now it is stored in slot 2, XL-2 is
    empty, and PM-DB-5 lets go of XL-2 (its spool left)."""
    sm = FakeSpoolman({42: {"location": "XL-2", "extra": {"physical_source": "PM-DB-5",
                                                          "physical_source_slot": "1"}},
                       99: {"location": "XL-1", "extra": dict(FROM_POLYDRYER)}})
    store = LocationsStore(ROWS_E)
    res = _move(sm, store=store)
    assert res.get("status") == "success" and "auto_deployed_to" not in res, res
    assert sm.spools[42]["location"] == "LR-MDB-1" and _slot_of(sm, 42) == "2", sm.spools[42]
    assert sm.direct_at("XL-2") == [] and sm.direct_at("XL-1") == [99]
    assert store.bound("PM-DB-5") == ""


def test_a_slot_bound_to_something_that_isnt_a_head_is_passed_over():
    """TST-MDB-1 slot 1 is bound to the XL printer row (hand-edited). The chain
    would move the spool out of the box to it, so the pick takes slot 2."""
    sm = FakeSpoolman({42: {"location": "CR-CT-2-R1", "extra": {}}})
    res = _move(sm, target="TST-MDB-1")
    assert res.get("status") == "success", res
    assert sm.spools[42]["location"] == "TST-MDB-1" and _slot_of(sm, 42) == "2", sm.spools[42]


def test_when_every_free_slot_would_ask_it_takes_the_lowest_and_asks_once():
    """Only slot 1 is free, and XL-1 runs a PolyDryer spool: the lowest free slot,
    and 40.0c's question about XL-1. The box and XL-1 are each read once (the
    pick and the fed check share the head's read)."""
    sm = _Reads({42: {"location": "CR-CT-2-R1", "extra": {}}, 20: _in("2"), 30: _in("3"),
                 40: _in("4"), 99: {"location": "XL-1", "extra": dict(FROM_POLYDRYER)}})
    res = _move(sm)
    assert res.get("confirm_type") == "head_fed" and res["target_slot"] == "1", res
    assert [f["toolhead"] for f in res["fed_heads"]] == ["XL-1"], res
    assert sm.writes == []
    assert sm.read_locs == ["LR-MDB-1", "XL-1"], sm.read_locs


@pytest.mark.parametrize("auto_deploy", [False, True], ids=["store", "deploy"])
def test_a_spool_already_in_the_box_keeps_its_slot(auto_deploy):
    """#42 sits in slot 3 and slot 1 is free. A slotless move into its own box
    keeps it in slot 3 (the picker's rule 1); it used to hop to slot 1, which
    feeds XL-1."""
    sm = FakeSpoolman({42: _in("3")})
    res = _move(sm, auto_deploy=auto_deploy)
    assert res.get("status") == "success", res
    if auto_deploy:
        assert res.get("auto_deployed_to") == "XL-3" and sm.direct_at("XL-3") == [42], res
        assert sm.spools[42]["extra"].get("physical_source_slot") == "3"
    else:
        assert sm.spools[42]["location"] == "LR-MDB-1" and _slot_of(sm, 42) == "3", sm.spools[42]
    assert sm.direct_at("XL-1") == []


def test_a_full_box_still_takes_the_spool_unslotted_without_a_question():
    sm = FakeSpoolman({42: {"location": "CR-CT-2-R1", "extra": {}}, 10: _in("1"), 20: _in("2"),
                       30: _in("3"), 40: _in("4")})
    res = _move(sm, probe=_probe_for({"XL"}))
    assert res.get("status") == "success", res
    assert sm.spools[42]["location"] == "LR-MDB-1" and _slot_of(sm, 42) == "", sm.spools[42]


def test_a_store_only_move_takes_the_lowest_free_slot():
    """Nothing loads with auto_deploy off, so no slot can ask: slot 1, although
    XL-1 runs a PolyDryer spool, and XL-1 is left alone."""
    sm = _Reads({42: {"location": "CR-CT-2-R1", "extra": {}},
                 99: {"location": "XL-1", "extra": dict(FROM_POLYDRYER)}})
    res = _move(sm, auto_deploy=False)
    assert res.get("status") == "success", res
    assert _slot_of(sm, 42) == "1" and sm.direct_at("XL-1") == [99]
    assert "XL-1" not in sm.read_locs, f"a store-only pick read a head: {sm.read_locs}"


def test_a_head_spoolman_cant_list_while_picking_refuses_before_writing():
    """The box reads fine; XL-1 (slot 1's head) can't be read. The pick can't
    tell whether slot 1 would ask, so nothing moves."""
    sm = FakeSpoolman({42: {"location": "CR-CT-2-R1", "extra": {}}})
    sm.fail_list_reads = {1}
    res = _move(sm)
    assert res.get("status") == "error", res
    assert "couldn't read XL-1 from Spoolman to pick a slot in LR-MDB-1" in res["msg"], res
    assert "42" in res["failures"] and sm.writes == []


def test_a_box_spoolman_cant_list_refuses_before_writing():
    sm = FakeSpoolman({42: {"location": "CR-CT-2-R1", "extra": {}}})
    sm.fail_list_reads = {0}
    res = _move(sm)
    assert res.get("status") == "error" and "pick a free slot" in res["msg"], res
    assert sm.writes == []


# ---- the rule itself (the picker's ⭐ will call it too) --------------------------

def test_recommend_box_slot_rules():
    asked = []

    def busy(heads):
        def would_prompt(slot):
            asked.append(slot)
            return slot in heads
        return would_prompt

    assert logic.recommend_box_slot(4, ["2"], own_slot="3", would_prompt=busy({"1"})) == ("3", "own_slot")
    assert logic.recommend_box_slot(4, ["3"], own_slot="3", would_prompt=None) == ("1", "no_prompt")
    asked.clear()
    assert logic.recommend_box_slot("4", ["2"], would_prompt=busy({"1"})) == ("3", "no_prompt")
    assert asked == ["1", "3"], "lazy, lowest slot first, stopping at the first that won't ask"
    assert logic.recommend_box_slot(4, ["2", "3", "4"], would_prompt=busy({"1"})) == ("1", "lowest_empty")
    assert logic.recommend_box_slot(2, ['"1"', "02"], would_prompt=busy(set())) == (None, "full")
    assert logic.recommend_box_slot("x", [], would_prompt=None) == (None, "full")
    assert logic.recommend_box_slot(4, [], own_slot="9", would_prompt=None) == ("1", "no_prompt")


# ---- the Group 40 review's deferred notes, pinned with 40.3 ------------------------------

# CR-MDB-1 feeds nothing (as on dev); GHOST-MDB's slot 1 is bound to XL-9, a head
# that doesn't exist (deleted, or a hand edit).
ROWS_X = ROWS_E + [
    {"LocationID": "CR-MDB-1", "Type": "Dryer Box", "Max Spools": "4", "parent_id": "LR",
     "extra": {"slot_targets": {}}},
    {"LocationID": "GHOST-MDB", "Type": "Dryer Box", "Max Spools": "4", "parent_id": "LR",
     "extra": {"slot_targets": {"1": "XL-9"}}},
]


def test_the_lowest_slots_question_answered_load_and_store():
    """The review's tests:auto-picked-head-fed-replays-unpinned: the question
    above, answered. "Load it instead" sends the pick back as picked_slot with
    XL-1's confirm key: #42 loads, #99 goes home and PM-DB-2 lets go of XL-1.
    "Just store it" sends the pick with auto_deploy off: #42 waits in slot 1 and
    no head is read. A control."""
    spools = {42: {"location": "CR-CT-2-R1", "extra": {}}, 20: _in("2"), 30: _in("3"),
              40: _in("4"), 99: {"location": "XL-1", "extra": dict(FROM_POLYDRYER)}}
    sm = _Reads(spools)
    store = LocationsStore(ROWS_E)
    res = _move(sm, store=store)
    assert res.get("confirm_type") == "head_fed" and res["target_slot"] == "1", res
    loaded = _move(sm, store=store, picked_slot=res["target_slot"],
                   confirmed_fed_heads=[res["fed_heads"][0]["confirm_key"]])
    assert loaded.get("auto_deployed_to") == "XL-1", loaded
    assert sm.direct_at("XL-1") == [42] and sm.spools[99]["location"] == "PM-DB-2", sm.writes
    assert store.bound("PM-DB-2") == ""

    sm2 = _Reads(spools)
    stored = _move(sm2, picked_slot="1", auto_deploy=False)
    assert stored.get("status") == "success" and "auto_deployed_to" not in stored, stored
    assert sm2.spools[42]["location"] == "LR-MDB-1" and _slot_of(sm2, 42) == "1"
    assert sm2.direct_at("XL-1") == [99]
    assert "XL-1" not in sm2.read_locs, sm2.read_locs


class _FilledAtRead(FakeSpoolman):
    """Puts #77 in CR-MDB-1 slot 1 just before the `nth` strict list read of
    CR-MDB-1 (read 1 is step 3's pick, read 2 step 6's slot read)."""

    def __init__(self, spools, nth):
        super().__init__(spools)
        self.nth, self.box_reads = nth, 0

    def at_location_detailed_strict(self, loc):
        if str(loc).upper() == "CR-MDB-1":
            self.box_reads += 1
            if self.box_reads == self.nth:
                self.spools[77] = _in("1", box="CR-MDB-1")
        return super().at_location_detailed_strict(loc)


def test_a_slot_filled_without_a_printer_check_says_meanwhile():
    """The review's io:race-refusal-text-says-printer: CR-MDB-1 feeds nothing,
    so no printer is asked, yet the refusal said "while FCC was checking the
    printer". #77 takes the picked slot between the pick and the write."""
    sm = _FilledAtRead({42: {"location": "CR-CT-2-R1", "extra": {}},
                        77: {"location": "CR-CT-2-R1", "extra": {}}}, nth=2)
    probes = []

    def probe(url, name):
        probes.append(name)
        return IDLE(url, name)

    res = _move(sm, probe=probe, store=LocationsStore(ROWS_X), target="CR-MDB-1")
    assert res["failures"].get("42") == ("CR-MDB-1 slot 1 was filled by #77 meanwhile, so nothing moved "
                                         "— try again"), res
    assert probes == [] and sm.box_reads == 2, (probes, sm.box_reads)
    assert sm.spools[42]["location"] == "CR-CT-2-R1" and _slot_of(sm, 77) == "1", sm.writes


def test_a_picked_slot_that_no_longer_exists_says_so():
    """The review's narrow branch (b): a replayed pick of slot 9 in a 4-slot box
    (its Max Spools lowered while the user decided). It was "taken while you
    were deciding", by nobody; without the range check slot 9 was written."""
    sm = FakeSpoolman({42: {"location": "CR-CT-2-R1", "extra": {}}})
    res = _move(sm, picked_slot="9")
    assert res.get("status") == "error" and res.get("blocked_reason") == "picked_slot_taken", res
    assert res["msg"] == "Not moved: LR-MDB-1 has no slot 9 any more, so nothing moved — try again.", res
    assert sm.writes == []


@pytest.mark.parametrize("box, bound", [("TST-MDB-1", "XL"), ("GHOST-MDB", "XL-9")],
                         ids=["printer-row", "no-such-head"])
def test_a_named_slot_bound_to_something_that_isnt_a_head_keeps_the_spool_in_the_box(box, bound):
    """The review's tests:non-head-binding-chain-unpinned: slot 1 is bound to the
    XL printer row, or to XL-9, which doesn't exist. The chain moved #42 out of
    the box ("Auto-deployed → XL-9"), or was refused at the printer row. It now
    stays in its slot, and the answer says why."""
    sm = FakeSpoolman({42: {"location": "CR-CT-2-R1", "extra": {}}})
    res = _move(sm, store=LocationsStore(ROWS_X), target=box, target_slot="1")
    assert res.get("status") == "success" and "auto_deployed_to" not in res, res
    assert sm.spools[42]["location"] == box and _slot_of(sm, 42) == "1", sm.spools[42]
    assert res["auto_deploy_skipped"] == {"42": (f"{box} slot 1 is bound to {bound}, which isn't a toolhead — "
                                                 f"fix it in {box}'s 🔗 Slot → Toolhead Feeds")}, res
    assert res["auto_deploy_target"] == bound, res
    assert sm.direct_at(bound) == []


def test_storing_over_a_deployed_spools_slot_bound_to_a_non_head_is_refused():
    """The companion gap: with no chain to swap it out, a spool put in a slot
    whose own spool is deployed (#5 runs on XL-1 from GHOST-MDB slot 1) left two
    spools claiming the slot. Refused, nothing written."""
    sm = FakeSpoolman({42: {"location": "CR-CT-2-R1", "extra": {}},
                       5: {"location": "XL-1", "extra": {"physical_source": "GHOST-MDB",
                                                         "physical_source_slot": "1", "container_slot": ""}}})
    res = _move(sm, store=LocationsStore(ROWS_X), target="GHOST-MDB", target_slot="1")
    assert "GHOST-MDB slot 1 still holds #5, loaded on XL-1" in logic.smart_move_failure(res, 42), res
    assert sm.writes == []
