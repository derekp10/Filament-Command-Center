"""Group 40 engine review (wf_6946f24e-3da): the 2 orange and 5 yellow findings,
each pinned here, proven red on the reviewed commit e8a2706 first.

- ghost-own-slot: a spool deployed from LR-MDB-1 slot 2, moved slotless into
  LR-MDB-1, took the lowest free slot and was loaded onto XL-1; it goes back
  into its own slot 2 and is only stored.
- store-over-own-deployed-spool: "Just store it" was offered while the head runs
  the slot's own spool, and a store there seated a second spool in the slot.
- guard-refusal-double-claim: the chain guard's advice pointed to a Quick-Swap
  that refuses a slot two spools claim.
- feeds-body-empty-head: covered in test_fed_head_confirm_40_0c.py and
  test_source_confirm_39_4.py (an empty head isn't "unloaded").
- mover-read-fail-open: an unreadable mover fails the slotless pick closed.
- door-accepts-bare-fed-head: at the doors only confirm keys count.
- picked-slot-door-unpinned: both box doors honour picked_slot only while free.

The REAL engine runs over tests/move_engine_harness.py with a live locations store.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import logic  # noqa: E402
import state  # noqa: E402
from move_engine_harness import IDLE, _probe_for  # noqa: E402
from test_fed_head_confirm_40_0c import FROM_POLYDRYER, _door, _move, _sm  # noqa: E402


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


def _in(slot):
    return {"location": "LR-MDB-1", "extra": {"container_slot": slot}}


def test_a_deployed_spool_moved_slotless_into_its_box_goes_back_to_its_own_slot():
    """#42 runs on XL-2, deployed from LR-MDB-1 slot 2; slots 3 and 4 are full and
    slot 1 is free with XL-1 empty. It used to land in slot 1 and be loaded onto
    XL-1. It goes back into slot 2, stored, and both heads are empty."""
    sm = _sm(more={30: _in("3"), 40: _in("4")})
    sm.spools[42] = {"location": "XL-2", "extra": {"physical_source": "LR-MDB-1", "physical_source_slot": "2"}}
    res, _ = _move(sm, slot=None)
    assert res.get("status") == "success" and "auto_deployed_to" not in res, res
    assert sm.spools[42]["location"] == "LR-MDB-1" and sm.spools[42]["extra"]["container_slot"] == "2"
    assert sm.direct_at("XL-1") == [] and sm.direct_at("XL-2") == []


def _own_spool_on_xl3():
    return _sm(more={99: {"location": "XL-3", "extra": {"physical_source": "LR-MDB-1",
                                                       "physical_source_slot": "3"}}})


def test_store_is_not_offered_while_the_head_runs_the_slots_own_spool():
    """Derek's S2 while printing: XL-3 runs #99 from LR-MDB-1 slot 3. Slot 3 still
    holds #99, so only "Load it instead" or Cancel make sense."""
    res, _ = _move(_own_spool_on_xl3(), slot="3", probe=_probe_for({"XL"}))
    assert res.get("confirm_type") == "active_print" and res["can_store"] is False, res


def test_storing_into_a_slot_whose_spool_is_deployed_is_refused():
    """The store itself is refused whatever a client sends: two spools claiming
    slot 3 broke XL-3's Quick-Swap (ambiguous slot) and Return of #99."""
    sm = _own_spool_on_xl3()
    res, _ = _move(sm, slot="3", auto_deploy=False)
    assert "LR-MDB-1 slot 3 still holds #99, loaded on XL-3" in logic.smart_move_failure(res, 42), res
    assert sm.writes == [] and sm.direct_at("XL-3") == [99]


def test_the_guards_advice_never_points_at_a_slot_two_spools_claim():
    """During the printer check a spare #200 lands on XL-1 with 40.0d's trail
    LR-MDB-1 slot 1, the slot #42 is being stored in. Quick-Swap refuses that
    slot (two claimants), so the warning says to sort the slot out instead."""
    sm = _sm(more={200: {"location": "", "extra": {}}})

    def probe(url, name):
        sm.spools[200] = {"location": "XL-1", "extra": {"physical_source": "LR-MDB-1",
                                                        "physical_source_slot": "1", "container_slot": ""}}
        return IDLE(url, name)

    res, _ = _move(sm, probe=probe)
    why = (res.get("auto_deploy_skipped") or {}).get("42", "")
    assert "#200 also claims that slot: open LR-MDB-1 and move one of them" in why, res
    assert "Quick-Swap" not in why, why


def test_an_unreadable_moving_spool_refuses_a_slotless_box_move():
    """The pick reads where the spool is (a slot feeding the head it leaves only
    stores it). A blip there used to read as "not on a head"."""
    sm = _sm()
    sm.unreadable = {42}
    res, _ = _move(sm, slot=None)
    assert res.get("status") == "error" and "couldn't read #42 from Spoolman" in res["msg"], res
    assert sm.writes == []


@pytest.mark.parametrize("path, body", [
    ("/api/identify_scan", {"text": "LOC:LR-MDB-1:SLOT:1", "source": "barcode"}),
    ("/api/manage_contents", {"action": "add", "location": "LR-MDB-1", "slot": "1", "spool_id": "ID:42"}),
    ("/api/smart_move", {"location": "LR-MDB-1", "slot": "1", "spools": [42]}),
], ids=["slot_scan", "manage_contents", "smart_move"])
def test_a_bare_head_id_at_a_door_is_not_a_confirm(client, path, body):
    """A bare head id would cover XL-1 whatever it runs, switching off the key
    scoping and the chain guard. At the doors only confirm keys count."""
    state.GLOBAL_BUFFER = [{"id": 42, "display": "#42"}]
    sm = _sm(FROM_POLYDRYER)
    r, _ = _door(sm, client, path, dict(body, confirmed_toolheads=[], confirmed_fed_heads=["XL-1"]))
    out = r.get_json()
    assert out.get("confirm_type") == "head_fed", out
    assert sm.writes == []


@pytest.mark.parametrize("path, body", [
    ("/api/manage_contents", {"action": "add", "location": "LR-MDB-1", "spool_id": "ID:42"}),
    ("/api/smart_move", {"location": "LR-MDB-1", "spools": [42]}),
], ids=["manage_contents", "smart_move"])
def test_a_box_door_takes_picked_slot_only_while_free(client, path, body):
    """The replay of a question about an auto-picked slot sends it back as
    picked_slot; #77 took slot 2 meanwhile, so nothing moves."""
    sm = _sm(more={77: _in("2")})
    r, _ = _door(sm, client, path, dict(body, confirmed_toolheads=[], confirmed_fed_heads=[], picked_slot="2"))
    out = r.get_json()
    assert out.get("blocked_reason") == "picked_slot_taken", out
    assert sm.writes == []
