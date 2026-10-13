"""Group 39.4 (D6): ask before moving a spool OFF a printing head.

The move pre-flight asked only about the destination and a named slot's bound
head. A spool moved off a printing toolhead (Location Manager assign, a buffer
location scan, Force Location "add") was never asked about, and FCC silently
stopped charging the print to it. The engine now reads each moving spool's own
record (step 4 of the shared pre-write contract): a spool on a printer head is
role 'source', and source, destination and feeds heads go through ONE
_uncovered_active_heads call, so one probe per printer and one answer.

The message is Derek's D6 wording ("#42 is loaded on XL-3. Moving it to
CR-CT-2-R1 means FCC stops charging this print to it. Continue?").

The REAL engine runs through tests/move_engine_harness.py, and the route tests
go through the Flask client. The probe is stubbed below the per-move memo.
HEAD proof: on the pre-39.4 engine every "asks" test moves the spool instead,
and the head -> head test answers about the destination only.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import state  # noqa: E402
from move_engine_harness import WireSpoolman, run_move  # noqa: E402

PRINTER_MAP = {
    "XL-1": {"printer_name": "XL", "position": 0},
    "XL-3": {"printer_name": "XL", "position": 2},
    "CORE1-M0": {"printer_name": "Core One", "position": 0},
}
LOCATIONS = [
    {"LocationID": "XL-1", "Type": "Tool Head", "Max Spools": "1", "Name": "XL-1"},
    {"LocationID": "XL-3", "Type": "Tool Head", "Max Spools": "1", "Name": "XL-3"},
    {"LocationID": "CORE1-M0", "Type": "No MMU Direct Load", "Max Spools": "1", "Name": "Core One"},
    {"LocationID": "CR-CT-2-R1", "Type": "Cart", "Max Spools": "0", "Name": "Cart 2 row 1"},
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
    import app as app_module
    app_module.app.config["TESTING"] = True
    return app_module.app.test_client()


def _state_probe(printing, state_name="PRINTING"):
    calls = []

    def probe(_url, printer_name):
        calls.append(printer_name)
        active = printer_name in printing
        return {"state": state_name if active else "IDLE", "is_active": active}
    return probe, calls


def _run(sm, probe, **kw):
    return run_move(sm, probe=probe, locations=LOCATIONS, printer_map=PRINTER_MAP, **kw)


@pytest.mark.parametrize("printer_state", ["PRINTING", "PAUSING", "RESUMING"])
def test_manage_contents_add_off_a_printing_head_asks_first(client, printer_state):
    sm = WireSpoolman({42: {"location": "XL-3", "extra": {}}})
    probe, _ = _state_probe({"XL"}, printer_state)
    r = _run(sm, probe, call=lambda: client.post("/api/manage_contents", json={
        "action": "add", "location": "CR-CT-2-R1", "spool_id": "ID:42"}))
    res = r.get_json()
    assert res["status"] == "requires_confirm", res
    assert res["active_prints"] == [{"toolhead": "XL-3", "printer_name": "XL", "state": printer_state,
                                     "role": "source", "spools": [42]}]
    assert res["msg"] == ("#42 is loaded on XL-3. Moving it to CR-CT-2-R1 means FCC stops "
                          "charging this print to it. Continue?")
    assert sm.patch_bodies == [], f"wrote {sm.patch_bodies} before the confirm"
    assert sm.spools[42]["location"] == "XL-3"


def test_a_paused_printer_does_not_ask():
    """PAUSED is not active (prusalink_api maps it so): the move goes ahead."""
    sm = WireSpoolman({42: {"location": "XL-3", "extra": {}}})

    def probe(_url, printer_name):
        return {"state": "PAUSED", "is_active": False}
    res = _run(sm, probe, target="CR-CT-2-R1", raw_spools=[42])
    assert res.get("status") == "success", res
    assert sm.spools[42]["location"] == "CR-CT-2-R1"


def test_head_to_head_on_one_printer_is_one_answer_and_one_probe():
    sm = WireSpoolman({42: {"location": "XL-1", "extra": {}}})
    probe, calls = _state_probe({"XL"})
    res = _run(sm, probe, target="XL-3", raw_spools=[42])
    assert res.get("status") == "requires_confirm", res
    assert [(a["toolhead"], a["role"]) for a in res["active_prints"]] == [
        ("XL-1", "source"), ("XL-3", "destination")]
    assert calls == ["XL"], f"probed {calls}: one printer, one probe"
    assert res["msg"] == ("#42 is loaded on XL-1. Moving it to XL-3 means FCC stops "
                          "charging this print to it. Continue?")
    assert sm.patch_bodies == []


def test_smart_move_with_two_spools_on_two_heads_is_one_answer(client):
    """/api/smart_move (the buffer location scan) with #42 on XL-3 and #57 on
    XL-1: one answer naming both, nothing written."""
    sm = WireSpoolman({42: {"location": "XL-3", "extra": {}},
                       57: {"location": "XL-1", "extra": {}}})
    probe, calls = _state_probe({"XL"})
    r = _run(sm, probe, call=lambda: client.post("/api/smart_move", json={
        "location": "CR-CT-2-R1", "spools": [42, 57]}))
    res = r.get_json()
    assert res["status"] == "requires_confirm", res
    assert sorted((a["toolhead"], tuple(a["spools"])) for a in res["active_prints"]) == [
        ("XL-1", (57,)), ("XL-3", (42,))]
    assert res["msg"] == ("#42 is loaded on XL-3 and #57 on XL-1. Moving them to CR-CT-2-R1 "
                          "means FCC stops charging this XL print to them. Continue?")
    assert calls == ["XL"]
    assert sm.patch_bodies == []


def test_a_rescan_onto_its_own_head_does_not_ask():
    sm = WireSpoolman({42: {"location": "XL-3", "extra": {"physical_source": "LR-MDB-1",
                                                          "physical_source_slot": "3"}}})
    probe, calls = _state_probe({"XL"})
    res = _run(sm, probe, target="XL-3", raw_spools=[42], confirm_active_print=["XL-3"])
    assert res.get("status") == "success", res
    assert calls == [], "a re-scan onto the head the spool sits on probed the printer"


def test_confirming_both_heads_moves_both():
    sm = WireSpoolman({42: {"location": "XL-3", "extra": {}},
                       57: {"location": "XL-1", "extra": {}}})
    probe, calls = _state_probe({"XL"})
    res = _run(sm, probe, target="CR-CT-2-R1", raw_spools=[42, 57],
               confirm_active_print=["XL-3", "XL-1"])
    assert res.get("status") == "success", res
    assert sm.direct_at("CR-CT-2-R1") == [42, 57]
    assert calls == [], "covered heads were probed"


def test_confirming_one_of_two_heads_asks_about_the_other():
    sm = WireSpoolman({42: {"location": "XL-3", "extra": {}},
                       57: {"location": "CORE1-M0", "extra": {}}})
    probe, _ = _state_probe({"XL", "Core One"})
    res = _run(sm, probe, target="CR-CT-2-R1", raw_spools=[42, 57], confirm_active_print=["XL-3"])
    assert res.get("status") == "requires_confirm", res
    assert [a["toolhead"] for a in res["active_prints"]] == ["CORE1-M0"]
    assert sm.patch_bodies == []


def test_loading_onto_a_printing_head_names_the_spool_it_unloads():
    """The destination row of Derek's table: the resident is read before the
    confirm (step 4), so the message can name it."""
    sm = WireSpoolman({57: {"location": "CR", "extra": {}},
                       196: {"location": "XL-1", "extra": {}}})
    probe, _ = _state_probe({"XL"})
    res = _run(sm, probe, target="XL-1", raw_spools=[57])
    assert res.get("status") == "requires_confirm", res
    assert res["msg"] == ("XL is PRINTING. Loading #57 onto XL-1 unloads #196, so FCC stops "
                          "charging this print to #196. Continue?")
    assert sm.patch_bodies == []


def test_an_unreadable_moving_spool_refuses_before_any_probe():
    """Step 4 fails closed: with #42's record unreadable FCC can't tell whether
    it is leaving a printing head, so nothing is probed or written."""
    sm = WireSpoolman({42: {"location": "XL-3", "extra": {}}}, unreadable=[42])
    probe, calls = _state_probe({"XL"})
    res = _run(sm, probe, target="CR-CT-2-R1", raw_spools=[42])
    assert res.get("status") == "error", res
    assert res["failures"] == {"42": "could not read the spool from Spoolman"}
    assert calls == [] and sm.patch_bodies == []


def test_the_true_path_reads_nothing_extra():
    """Internal callers (bulk-move commit, the chain) pass True: no source pass,
    no probe, and the move goes ahead even off a printing head."""
    sm = WireSpoolman({42: {"location": "XL-3", "extra": {}}})
    reads = []
    real_get = sm.get_spool

    def counting_get(sid):
        reads.append(int(sid))
        return real_get(sid)
    sm.get_spool = counting_get
    probe, calls = _state_probe({"XL"})
    res = _run(sm, probe, target="CR-CT-2-R1", raw_spools=[42], confirm_active_print=True)
    assert res.get("status") == "success", res
    assert calls == []
    # The write loop's read plus update_spool's own read-merge, as before 39.4.
    assert reads.count(42) == 2, f"#42 read {reads.count(42)} times: the True path gained a read"
