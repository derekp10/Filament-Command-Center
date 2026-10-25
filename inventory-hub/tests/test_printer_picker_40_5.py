"""Group 40.5 — the engine half of the Printer picker (D3, item G) and the slot
read before a question (the 40.3 "Open, narrow" note and the 40.2 review's
stale-store note).

`record_source` (the Printer picker's "Record it as coming from…"): a spool put on
a head from no box records exactly the slot the user named (a multi-slot box's
slot feeding that head, held by no other spool, checked strictly before
anything is written and again at the write), or no box at all (''); without
it, the silent 13.6 rule still records a slot only when exactly one is free. A
spool arriving from somewhere keeps its own trail (`record_source_ignored`).

The slot read: a question about a box slot is asked only when its answers can
land. A slot whose own spool runs on another head refuses the load and the
store alike, so that refusal comes first, with nothing written; a slot a record
still claims (a deployed spool's trail, or a stale one) refuses a store, so the
question offers no "Just store it".

The REAL engine runs over tests/move_engine_harness.py ([[mocked engine hides
chain bugs]]); the doors run through the Flask test client.
HEAD proof: see the commit message.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import logic  # noqa: E402
import state  # noqa: E402
from move_engine_harness import IDLE, FakeSpoolman, LocationsStore, _probe_for, run_move  # noqa: E402

PRINTER_MAP = {f"XL-{n}": {"printer_name": "XL", "position": n - 1} for n in (1, 2, 3)}
ROWS = [
    {"LocationID": "LR", "Type": "Room", "Max Spools": "0"},
    {"LocationID": "XL", "Type": "Printer", "Max Spools": "0", "parent_id": "LR",
     "toolheads": [{"location_id": f"XL-{n}", "position": n - 1} for n in (1, 2, 3)]},
    *[{"LocationID": f"XL-{n}", "Type": "Tool Head", "Max Spools": "1", "parent_id": "XL"} for n in (1, 2, 3)],
    {"LocationID": "LR-MDB-1", "Type": "Dryer Box", "Max Spools": "4", "parent_id": "LR",
     "extra": {"slot_targets": {"1": "XL-1", "2": "XL-2", "3": "XL-3", "4": "PRINTER:XL"}}},
    {"LocationID": "TST-MDB-1", "Type": "Dryer Box", "Max Spools": "2", "parent_id": "LR",
     "extra": {"slot_targets": {"1": "XL-2"}}},
    {"LocationID": "PM-DB-2", "Type": "Dryer Box", "Max Spools": "1", "parent_id": "LR",
     "extra": {"slot_targets": {"1": "XL-2"}}},
    {"LocationID": "CR-CT-2-R1", "Type": "Cart Row", "Max Spools": "0", "parent_id": "LR"},
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


def _sp(loc, slot="", src="", src_slot=""):
    extra = {"container_slot": str(slot)}
    if src:
        extra["physical_source"] = src
        extra["physical_source_slot"] = str(src_slot)
    return {"location": loc, "extra": extra}


def _move(sm, target, spools=(42,), slot=None, probe=IDLE, store=None, **kw):
    return run_move(sm, probe=probe, store=store or LocationsStore(ROWS), printer_map=PRINTER_MAP,
                    target=target, raw_spools=list(spools), target_slot=slot, origin="test", **kw)


def _trail(sm, sid):
    extra = sm.spools[sid].get("extra") or {}
    return (extra.get("physical_source", ""), str(extra.get("physical_source_slot", "")).strip('"'))


# ---- record_source -----------------------------------------------------------------------------

def test_a_named_slot_is_recorded_even_when_two_are_free():
    """XL-2 is fed by LR-MDB-1 slot 2 and TST-MDB-1 slot 1, both free: the silent
    rule records nothing (no guess), the user's answer records exactly theirs."""
    sm = FakeSpoolman({42: _sp("")})
    res = _move(sm, "XL-2", record_source={"box": "TST-MDB-1", "slot": "1"})
    assert res["status"] == "success" and sm.direct_at("XL-2") == [42], res
    assert _trail(sm, 42) == ("TST-MDB-1", "1")
    assert res["recorded_source"] == "TST-MDB-1:1"


def test_without_an_answer_two_free_slots_still_record_nothing():
    sm = FakeSpoolman({42: _sp("")})
    res = _move(sm, "XL-2")
    assert res["status"] == "success" and _trail(sm, 42) == ("", "") and "recorded_source" not in res, res


def test_no_box_records_nothing_even_with_one_free_slot():
    """XL-1 has exactly one free feed (LR-MDB-1 slot 1): the silent rule would
    record it; "No box" doesn't."""
    sm = FakeSpoolman({42: _sp("")})
    silent = _move(FakeSpoolman({42: _sp("")}), "XL-1")
    assert silent["recorded_source"] == "LR-MDB-1:1", silent
    res = _move(sm, "XL-1", record_source="")
    assert res["status"] == "success" and _trail(sm, 42) == ("", "") and "recorded_source" not in res, res


@pytest.mark.parametrize("named, why", [
    ({"box": "LR-MDB-1", "slot": "1"}, "LR-MDB-1 slot 1 doesn't feed XL-2"),
    ({"box": "PM-DB-2", "slot": "1"}, "PM-DB-2 isn't a box with slots"),
    ({"box": "CR-CT-2-R1", "slot": "1"}, "CR-CT-2-R1 isn't a box with slots"),
    ({"box": "LR-MDB-1", "slot": "2"}, "LR-MDB-1 slot 2 holds #77"),
], ids=["feeds-another-head", "single-slot-box", "not-a-box", "held"])
def test_a_named_slot_that_cannot_be_its_source_moves_nothing(named, why):
    """Refused before anything is written: XL-2's own spool #99 stays loaded
    (Smart Load would have unloaded it) and #42 stays where it was."""
    sm = FakeSpoolman({42: _sp(""), 99: _sp("XL-2"), 77: _sp("LR-MDB-1", slot=2)})
    res = _move(sm, "XL-2", record_source=named)
    assert res["status"] == "error" and res["blocked_reason"] == "record_source", res
    assert why in res["msg"] and why in res["failures"]["42"], res
    assert sm.writes == [] and sm.direct_at("XL-2") == [99]


def test_an_unreadable_named_box_moves_nothing():
    sm = FakeSpoolman({42: _sp(""), 99: _sp("XL-2")})
    sm.list_reads_fail = True
    res = _move(sm, "XL-2", record_source={"box": "TST-MDB-1", "slot": "1"})
    assert res["status"] == "error", res
    assert sm.writes == []


def test_a_spool_arriving_from_a_cart_keeps_its_trail():
    sm = FakeSpoolman({42: _sp("CR-CT-2-R1")})
    res = _move(sm, "XL-2", record_source={"box": "TST-MDB-1", "slot": "1"})
    assert res["status"] == "success" and res["record_source_ignored"] is True, res
    assert _trail(sm, 42) == ("CR-CT-2-R1", "")


def test_a_named_slot_taken_during_the_printer_probe_is_not_recorded():
    """Checked at step 4, re-checked at the write: #80 went into TST-MDB-1 slot 1
    while FCC asked the printer, so #42 is loaded but nothing is recorded (never
    two spools claiming one slot), and a WARNING says why."""
    sm = FakeSpoolman({42: _sp("")})

    def probe(url, printer_name):
        sm.spools[80] = _sp("TST-MDB-1", slot=1)
        return {"state": "IDLE", "is_active": False}

    res = _move(sm, "XL-2", probe=probe, record_source={"box": "TST-MDB-1", "slot": "1"})
    assert res["status"] == "success" and sm.direct_at("XL-2") == [42], res
    assert _trail(sm, 42) == ("", "") and "recorded_source" not in res, res
    assert any("not recorded as from TST-MDB-1 slot 1" in str(r) for r in state.RECENT_LOGS), state.RECENT_LOGS


@pytest.mark.parametrize("value, expected", [
    ({}, None),
    ({"record_source": None}, None),
    ({"record_source": ""}, ""),
    ({"record_source": {"box": " tst-mdb-1 ", "slot": 1}}, {"box": "TST-MDB-1", "slot": "1"}),
    ({"record_source": {"box": "TST-MDB-1", "slot": '"01"'}}, {"box": "TST-MDB-1", "slot": "1"}),
    ({"record_source": {"box": "TST-MDB-1"}}, ""),
    ({"record_source": {"box": "", "slot": "1"}}, ""),
    ({"record_source": "TST-MDB-1:1"}, ""),
], ids=["absent", "null", "no-box", "named", "quoted", "no-slot", "no-box-id", "a-string"])
def test_record_source_from_reads_the_request(value, expected):
    assert logic.record_source_from(value) == expected
    assert logic.record_source_from(None) is None


@pytest.mark.parametrize("path, body", [
    ("/api/smart_move", {"location": "XL-2", "spools": [42], "origin": "buffer",
                         "confirmed_toolheads": [], "confirmed_fed_heads": []}),
    ("/api/manage_contents", {"action": "add", "location": "XL-2", "spool_id": "ID:42",
                              "confirmed_toolheads": [], "confirmed_fed_heads": []}),
], ids=["smart-move", "location-manager"])
def test_the_doors_pass_the_named_source(client, path, body):
    sm = FakeSpoolman({42: _sp("")})
    payload = dict(body, record_source={"box": "TST-MDB-1", "slot": "1"})
    res = run_move(sm, probe=IDLE, store=LocationsStore(ROWS), printer_map=PRINTER_MAP,
                   call=lambda: client.post(path, json=payload)).get_json()
    assert res["status"] == "success" and res["recorded_source"] == "TST-MDB-1:1", res
    assert _trail(sm, 42) == ("TST-MDB-1", "1")


# ---- the slot read before a question ----------------------------------------------------------

FROM_POLYDRYER = _sp("XL-1", src="PM-DB-2", src_slot=1)


def test_a_stale_record_in_the_slot_takes_no_store_in_the_fed_question():
    """XL-1 runs a PolyDryer spool, so a scan into LR-MDB-1 slot 1 asks. #60's
    record still claims slot 1 (it sits on a cart): a load ignores it, a store
    would be refused, so the question offers no "Just store it" (it used to,
    and the store was then refused)."""
    sm = FakeSpoolman({42: _sp("CR-CT-2-R1"), 99: FROM_POLYDRYER, 60: _sp("CR-CT-2-R1", src="LR-MDB-1", src_slot=1)})
    res = _move(sm, "LR-MDB-1", slot="1")
    assert res["status"] == "requires_confirm" and res["confirm_type"] == "head_fed", res
    assert res["can_store"] is False and res["can_load"] is True, res
    assert sm.writes == []


def test_a_stale_record_takes_no_store_in_the_printing_question():
    sm = FakeSpoolman({42: _sp("CR-CT-2-R1"), 60: _sp("", src="LR-MDB-1", src_slot=1)})
    res = _move(sm, "LR-MDB-1", slot="1", probe=_probe_for({"XL"}))
    assert res["status"] == "requires_confirm" and res["confirm_type"] == "active_print", res
    assert res["can_store"] is False and res.get("title"), res


def test_a_clean_slot_still_offers_the_store():
    """A control: nothing claims slot 1, so "Just store it" is offered as before."""
    sm = FakeSpoolman({42: _sp("CR-CT-2-R1"), 99: FROM_POLYDRYER})
    res = _move(sm, "LR-MDB-1", slot="1")
    assert res["status"] == "requires_confirm" and res["can_store"] is True, res


def test_a_slot_whose_spool_runs_on_another_head_is_refused_before_the_fed_question():
    """Slot 1 feeds XL-1 (running a PolyDryer spool, so it would ask), but slot
    1's own #60 runs on XL-3: both answers would be refused, so the refusal
    comes first."""
    sm = FakeSpoolman({42: _sp("CR-CT-2-R1"), 99: FROM_POLYDRYER, 60: _sp("XL-3", src="LR-MDB-1", src_slot=1)})
    res = _move(sm, "LR-MDB-1", slot="1")
    assert res["status"] == "error" and "still holds #60, loaded on XL-3, while the slot feeds XL-1" in res["msg"], res
    assert res["blocked_reason"] == "slot_claimed", res   # Group 51.3 (the question path's refusal)
    assert sm.writes == []


def test_an_unreadable_slot_asks_as_before():
    """The read is a refinement: when it fails the question is asked as it was
    (the store offered), and step 6 reads the slot again on the answer."""
    sm = FakeSpoolman({42: _sp("CR-CT-2-R1"), 99: FROM_POLYDRYER, 60: _sp("", src="LR-MDB-1", src_slot=1)})
    sm.fail_list_reads = {1}     # 0: XL-1's residents (the fed check); 1: the slot read before the question
    res = _move(sm, "LR-MDB-1", slot="1")
    assert res["status"] == "requires_confirm" and res["can_store"] is True, res


def test_the_same_slot_swap_is_still_asked_nothing():
    """A control on Derek's path: XL-1 runs slot 1's own spool; no question at all,
    so the slot read never runs."""
    sm = FakeSpoolman({42: _sp("CR-CT-2-R1"), 99: _sp("XL-1", src="LR-MDB-1", src_slot=1)})
    res = _move(sm, "LR-MDB-1", slot="1")
    assert res["status"] == "success" and res.get("auto_deployed_to") == "XL-1", res
