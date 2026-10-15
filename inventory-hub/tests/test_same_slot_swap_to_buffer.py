"""Group 40 — the same-slot swap sends the slot's old spool to the scan buffer
(Derek, 2026-10-15; buglist "A same-slot swap files the old spool in the box
with no slot", engine review `engine:s2-swap-old-spool-unslotted`).

XL-1 runs #99, deployed from LR-MDB-1 slot 1. Derek buffers a new spool #42 and
scans `LOC:LR-MDB-1:SLOT:1`: #42 goes into slot 1 and the chain loads it onto
XL-1. Smart Load used to send #99 "home" to LR-MDB-1 slot 1, which #42 now
holds, so the eject's slot-collision check filed #99 in the box with no slot:
the box read 5/4 and #99 had no Quick-Swap tile. Derek only swaps a slot's spool
once it has run out (or to fix a record), so #99 is in his hand and usually
needs zeroing. It now goes to the scan buffer: Unassigned in Spoolman with its
trail cleared, at the END of the server's buffer (behind spools already
waiting, so the next slot scan still loads the next new spool), and named in
the move's answer as `to_buffer` so the page adds it to its own buffer.

Only the slot's OWN spool (its trail is exactly the box and slot being filled)
goes to the buffer; a spool from elsewhere (a PolyDryer) still goes home, and a
toolhead-QR scan (no slot is being filled) still sends the head's spool back to
its slot. Undo puts #99 back on XL-1 and takes it out of the buffer.

The REAL engine runs over tests/move_engine_harness.py ([[mocked engine hides
chain bugs]]); the doors run through the Flask test client.
HEAD proof (d8f6128): 17 of these 22 fail there (#99 lands in LR-MDB-1 with no
slot, the answers carry no `to_buffer`, nothing reaches GLOBAL_BUFFER, Undo
answers no `unbuffered`). The 5 that pass there do so by design: the controls
(a PolyDryer spool goes home, another slot's spool goes home, a toolhead scan
returns the spool to its slot, a rejected swap-out leaves the head alone) and
the no-double-add pin (HEAD never touches the buffer at all).
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
    {"LocationID": "PM-DB-2", "Type": "Dryer Box", "Max Spools": "1", "parent_id": "LR",
     "extra": {"slot_targets": {"1": "XL-1"}}},
    {"LocationID": "CR-CT-2-R1", "Type": "Cart Row", "Max Spools": "0", "parent_id": "LR"},
]


def _trail(box, slot):
    return {"physical_source": box, "physical_source_slot": str(slot), "container_slot": ""}


OWN_SLOT_1 = _trail("LR-MDB-1", 1)


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


def _sm(resident_extra=None, more=None, **kw):
    """#42 waits in the cart row; XL-1 runs #99 with `resident_extra` (none when None)."""
    spools = {42: {"location": "CR-CT-2-R1", "extra": {}}}
    if resident_extra is not None:
        spools[99] = {"location": "XL-1", "extra": dict(resident_extra)}
    spools.update(more or {})
    return FakeSpoolman(spools, **kw)


def _move(sm, store=None, probe=IDLE, target="LR-MDB-1", slot="1", spools=(42,), **kw):
    store = store or LocationsStore(ROWS)
    res = run_move(sm, probe=probe, store=store, printer_map=PRINTER_MAP,
                   target=target, raw_spools=list(spools), target_slot=slot, origin="test", **kw)
    return res, store


def _call(sm, fn, store=None, probe=IDLE):
    return run_move(sm, probe=probe, store=store or LocationsStore(ROWS), printer_map=PRINTER_MAP, call=fn)


def _buffer_ids():
    return [b.get("id") for b in state.GLOBAL_BUFFER if isinstance(b, dict)]


def _trail_of(sm, sid):
    extra = sm.spools[sid].get("extra") or {}
    return (extra.get("physical_source", ""), extra.get("physical_source_slot", ""), extra.get("container_slot", ""))


# ---- the swap -------------------------------------------------------------------------------------

@pytest.mark.parametrize("trail_slot, slot", [("1", "1"), ('"1"', "1"), ("1", 1), ("01", "1")],
                         ids=["plain", "quoted-trail", "int-slot", "zero-padded"])
def test_the_slots_own_spool_goes_to_the_scan_buffer_not_back_into_the_box(trail_slot, slot):
    sm = _sm(_trail("LR-MDB-1", trail_slot))
    res, _ = _move(sm, slot=slot)
    assert res.get("status") == "success" and res.get("auto_deployed_to") == "XL-1", res
    assert sm.direct_at("XL-1") == [42]
    # In the user's hand: Unassigned, with no trail left to make it a ghost in LR-MDB-1.
    assert sm.spools[99]["location"] == "", sm.writes
    assert _trail_of(sm, 99) == ("", "", ""), sm.spools[99]
    assert sm.direct_at("LR-MDB-1") == [], "nothing is filed in the box any more"
    assert [i["id"] for i in res.get("to_buffer") or []] == [99], res
    assert _buffer_ids() == [99]


def test_the_box_no_longer_reads_one_over_after_the_swap():
    """The bug as Derek saw it: after the swap LR-MDB-1 listed #99 with no slot
    beside #42's slot 1. Now the box holds only #42 (deployed from slot 1)."""
    sm = _sm(OWN_SLOT_1, more={7: {"location": "LR-MDB-1", "extra": {"container_slot": "2"}}})
    _move(sm)
    in_box = {i["id"]: (i["is_ghost"], i["slot"]) for i in sm.at_location_detailed("LR-MDB-1")}
    assert in_box == {7: (False, "2"), 42: (True, "1")}, in_box


def test_the_buffer_entry_carries_what_the_buffer_card_shows():
    sm = _sm(OWN_SLOT_1)
    res, _ = _move(sm)
    item = (res.get("to_buffer") or [{}])[0]
    assert item.get("id") == 99 and item.get("display") == "#99", item
    assert item.get("location") == "" and item.get("is_ghost") is False and item.get("deployed_to") is None, item
    assert item.get("off_head") == "XL-1", item   # for the page's toast: "taken off XL-1"
    assert state.GLOBAL_BUFFER == [item]


def test_the_swapped_out_spool_waits_behind_the_spools_already_buffered():
    """The next slot scan must still load the next NEW spool, not the empty one."""
    state.GLOBAL_BUFFER = [{"id": 43, "display": "#43"}, {"id": 44, "display": "#44"}]
    sm = _sm(OWN_SLOT_1)
    _move(sm)
    assert _buffer_ids() == [43, 44, 99]


def test_a_spool_already_in_the_buffer_is_not_added_twice():
    state.GLOBAL_BUFFER = [{"id": 99, "display": "#99"}]
    sm = _sm(OWN_SLOT_1)
    _move(sm)
    assert _buffer_ids() == [99]


def test_the_activity_log_says_where_it_went_and_why():
    sm = _sm(OWN_SLOT_1)
    _move(sm)
    msgs = [str(e.get("msg", "")) for e in state.RECENT_LOGS]
    assert any("Ejected #99 from XL-1 into the scan buffer" in m for m in msgs), msgs
    assert any("unloaded #99 from XL-1 into the scan buffer: it came from LR-MDB-1 slot 1, which #42 now takes"
               in m for m in msgs), msgs


# ---- what does NOT change ---------------------------------------------------------------------------

def test_a_spool_from_elsewhere_still_goes_home():
    """A control: XL-1 runs a PolyDryer spool; "Load it instead" sends it back to
    PM-DB-2, as 40.0c built. Only the slot's own spool is in the user's hand."""
    sm = _sm(_trail("PM-DB-2", 1))
    res, _ = _move(sm, confirmed_fed_heads=["XL-1#99"])
    assert res.get("auto_deployed_to") == "XL-1", res
    assert sm.spools[99]["location"] == "PM-DB-2"
    assert not res.get("to_buffer") and state.GLOBAL_BUFFER == []


def test_a_spool_from_another_slot_of_the_same_box_still_goes_home():
    """A control: #99 came from LR-MDB-1 slot 3 (re-pointed since); filling slot 1
    sends it back to slot 3, not to the buffer."""
    sm = _sm(_trail("LR-MDB-1", 3))
    res, _ = _move(sm, confirmed_fed_heads=["XL-1#99"])
    assert res.get("auto_deployed_to") == "XL-1", res
    assert sm.spools[99]["location"] == "LR-MDB-1" and _trail_of(sm, 99)[2] == "3", sm.spools[99]
    assert not res.get("to_buffer") and state.GLOBAL_BUFFER == []


def test_a_toolhead_scan_still_returns_the_heads_spool_to_its_slot():
    """A control: scanning XL-1's own label fills no slot, so #99 goes back into
    LR-MDB-1 slot 1 (its slot is free) exactly as before."""
    sm = _sm(OWN_SLOT_1)
    res, _ = _move(sm, target="XL-1", slot=None)
    assert res.get("status") == "success", res
    assert sm.spools[99]["location"] == "LR-MDB-1" and _trail_of(sm, 99)[2] == "1", sm.spools[99]
    assert not res.get("to_buffer") and state.GLOBAL_BUFFER == []


def test_a_rejected_swap_out_leaves_the_head_and_the_buffer_alone():
    """A control: Spoolman rejects #99's write, so XL-1 still holds it; #42 stays
    stored in slot 1 (not deployed), and nothing goes to the buffer."""
    sm = _sm(OWN_SLOT_1, reject_ids=[99])
    res, _ = _move(sm)
    assert sm.direct_at("XL-1") == [99] and _trail_of(sm, 99)[0] == "LR-MDB-1"
    assert sm.spools[42]["location"] == "LR-MDB-1"
    assert "42" in (res.get("auto_deploy_skipped") or {}), res
    assert not res.get("to_buffer") and state.GLOBAL_BUFFER == []


def test_a_printing_head_asks_first_and_the_yes_still_buffers_the_old_spool():
    probe = _probe_for({"XL"})
    sm = _sm(OWN_SLOT_1)
    asked, store = _move(sm, probe=probe)
    assert asked.get("status") == "requires_confirm", asked
    assert sm.writes == [] and state.GLOBAL_BUFFER == []
    res, _ = _move(sm, store=store, probe=probe, confirm_active_print=["XL-1"], expected_feed="XL-1")
    assert res.get("auto_deployed_to") == "XL-1", res
    assert sm.spools[99]["location"] == "" and _buffer_ids() == [99]


# ---- undo --------------------------------------------------------------------------------------------

def test_undo_puts_the_old_spool_back_on_the_head_and_out_of_the_buffer():
    state.GLOBAL_BUFFER = [{"id": 42, "display": "#42"}]
    sm = _sm(OWN_SLOT_1)
    store = LocationsStore(ROWS)
    res = run_move(sm, probe=IDLE, store=store, printer_map=PRINTER_MAP,
                   target="LR-MDB-1", raw_spools=[42], target_slot="1", origin="buffer")
    assert res.get("auto_deployed_to") == "XL-1", res
    state.GLOBAL_BUFFER = [b for b in state.GLOBAL_BUFFER if b.get("id") != 42]   # the page consumed #42
    assert _buffer_ids() == [99]
    undone = _call(sm, lambda: logic.perform_undo(), store=store)
    assert undone.get("success") is True, undone
    assert sm.direct_at("XL-1") == [99] and _trail_of(sm, 99) == ("LR-MDB-1", "1", ""), sm.spools[99]
    assert sm.spools[42]["location"] == "CR-CT-2-R1"
    assert undone.get("unbuffered") == [99], undone
    # #42 is back in the buffer (a buffer move's undo), #99 is not.
    assert _buffer_ids() == [42]


def test_an_undo_that_cant_put_the_old_spool_back_keeps_it_in_the_buffer():
    sm = _sm(OWN_SLOT_1)
    store = LocationsStore(ROWS)
    _move(sm, store=store)
    sm.reject_ids = {99}
    undone = _call(sm, lambda: logic.perform_undo(), store=store)
    assert undone.get("success") is False and undone.get("unbuffered") == [], undone
    assert _buffer_ids() == [99]


# ---- the doors ----------------------------------------------------------------------------------------

def _door(sm, client, path, body, store=None, probe=IDLE):
    return _call(sm, lambda: client.post(path, json=body), store=store, probe=probe)


def test_the_slot_scan_answers_done_and_hands_the_old_spool_back(client):
    """Derek's S2: one buffered spool. The answer is assignment_done (the spool he
    buffered is placed), names #99 in to_buffer, and the server's buffer replica
    holds #99: it was rebuilt from a snapshot taken BEFORE the move, which dropped
    the swapped-out spool again."""
    state.GLOBAL_BUFFER = [{"id": 42, "display": "#42"}]
    sm = _sm(OWN_SLOT_1)
    body = _door(sm, client, "/api/identify_scan", {
        "text": "LOC:LR-MDB-1:SLOT:1", "source": "barcode", "confirmed_fed_heads": []}).get_json()
    assert body["action"] == "assignment_done" and body["remaining_buffer"] == 0, body
    assert body["auto_deployed_to"] == "XL-1" and body["moved"] == 42, body
    assert [i["id"] for i in body["to_buffer"]] == [99], body
    assert _buffer_ids() == [99]


def test_the_slot_scan_counts_only_the_users_spools_as_still_in_the_buffer(client):
    state.GLOBAL_BUFFER = [{"id": 42, "display": "#42"}, {"id": 43, "display": "#43"}]
    sm = _sm(OWN_SLOT_1, more={43: {"location": "CR-CT-2-R1", "extra": {}}})
    body = _door(sm, client, "/api/identify_scan", {
        "text": "LOC:LR-MDB-1:SLOT:1", "source": "barcode", "confirmed_fed_heads": []}).get_json()
    assert body["action"] == "assignment_partial" and body["remaining_buffer"] == 1, body
    assert _buffer_ids() == [43, 99]


def test_a_slot_scan_with_nothing_swapped_answers_as_before(client):
    """An empty idle head: to_buffer is empty and the buffer is just the user's
    remaining spools. (It fails on d8f6128 only because the door answered no
    `to_buffer` key there; the behaviour is unchanged.)"""
    state.GLOBAL_BUFFER = [{"id": 42, "display": "#42"}]
    sm = _sm()
    body = _door(sm, client, "/api/identify_scan", {
        "text": "LOC:LR-MDB-1:SLOT:1", "source": "barcode", "confirmed_fed_heads": []}).get_json()
    assert body["action"] == "assignment_done" and body["to_buffer"] == [], body
    assert state.GLOBAL_BUFFER == []


@pytest.mark.parametrize("path, body", [
    ("/api/manage_contents", {"action": "add", "location": "LR-MDB-1", "slot": "1",
                              "spool_id": "ID:42", "origin": "buffer"}),
    ("/api/smart_move", {"location": "LR-MDB-1", "slot": "1", "spools": [42], "origin": "buffer"}),
], ids=["manage_contents", "smart_move"])
def test_the_other_doors_answer_to_buffer(client, path, body):
    sm = _sm(OWN_SLOT_1)
    res = _door(sm, client, path, dict(body, confirmed_toolheads=[], confirmed_fed_heads=[])).get_json()
    assert res.get("auto_deployed_to") == "XL-1", res
    assert [i["id"] for i in res.get("to_buffer") or []] == [99], res
    assert _buffer_ids() == [99]


# ---- the review's fixes (wf_0b3cc1a9-578) ---------------------------------------------------------
# HEAD proof (f5f3ba2): each fails there except where marked a control: the second
# read reversed the swap, a timed-out swap-out lost the spool from the buffer and
# the undo, and an undo dropped a spool the user had buffered.

def _scan(client, sm, body, store=None):
    return _door(sm, client, "/api/identify_scan", dict(
        {"text": "LOC:LR-MDB-1:SLOT:1", "source": "barcode", "confirmed_fed_heads": []}, **body),
        store=store).get_json()


def test_a_second_read_of_the_slot_label_never_puts_the_old_spool_back(client):
    """The red: one buffered spool, the same-slot swap, then the label read again
    (a scanner double-read, a "did it take?" re-scan). The buffer's only entry
    is #99, the spool just taken out; the second scan loaded it back onto XL-1
    and handed #42 to the buffer. It is held back now, nothing written."""
    state.GLOBAL_BUFFER = [{"id": 42, "display": "#42"}]
    sm = _sm(OWN_SLOT_1)
    store = LocationsStore(ROWS)
    first = _scan(client, sm, {}, store=store)
    assert first["action"] == "assignment_done" and _buffer_ids() == [99], first
    entry = state.GLOBAL_BUFFER[0]
    assert entry["swapped_from"] == "LR-MDB-1:1" and entry["swapped_for"] == [42], entry
    writes = len(sm.writes)
    second = _scan(client, sm, {}, store=store)
    assert second["action"] == "assignment_held" and second["spool"] == 99, second
    assert "#99 just came out of LR-MDB-1 slot 1 (#42 took its place)" in second["msg"], second
    assert "Undo Last Move" in second["msg"] and second["toast"].startswith("↩️ #99"), second
    assert len(sm.writes) == writes, "nothing is written"
    assert sm.direct_at("XL-1") == [42] and _buffer_ids() == [99]
    assert any("not loaded" in str(e.get("msg", "")) and e.get("type") == "WARNING" for e in state.RECENT_LOGS)


def test_the_hold_back_ends_after_its_window_and_never_stops_a_named_spool(client):
    """Controls: two minutes later the same scan is a deliberate one (it loads),
    and a door that names the spool (the deposit) is never held back."""
    state.GLOBAL_BUFFER = [{"id": 42, "display": "#42"}]
    sm = _sm(OWN_SLOT_1)
    store = LocationsStore(ROWS)
    _scan(client, sm, {}, store=store)
    named = _scan(client, sm, {"spool_id": 99}, store=store)
    assert named["action"] == "assignment_done" and sm.direct_at("XL-1") == [99], named
    # Swap back again, then age the entry past the window: a blind scan loads it.
    state.GLOBAL_BUFFER = [{"id": 42, "display": "#42"}]
    _scan(client, sm, {}, store=store)
    state.GLOBAL_BUFFER[0]["swapped_at"] -= (logic.SWAP_BACK_GUARD_S + 5) * 1000
    later = _scan(client, sm, {}, store=store)
    assert later["action"] == "assignment_done" and later["moved"] == 99, later


def test_a_swap_out_that_lands_but_times_out_still_reaches_the_buffer_and_the_undo():
    """Spoolman commits the swap-out PATCH but answers after update_spool's read
    timeout. A re-read shows it landed: #99 is buffered and recorded for Undo,
    and #42 is loaded (it used to say "XL-1 still holds #99", with #99 in no
    buffer and no undo record)."""
    sm = _sm(OWN_SLOT_1, landed_but_failed=[99])
    res, store = _move(sm)
    assert res.get("auto_deployed_to") == "XL-1", res
    assert [i["id"] for i in res.get("to_buffer") or []] == [99] and _buffer_ids() == [99]
    assert sm.direct_at("XL-1") == [42] and sm.spools[99]["location"] == ""
    rec = state.UNDO_STACK[-1]
    assert rec["ejections"] == {99: "XL-1"} and rec["buffered"] == [99], rec
    assert any("a re-read shows it there" in str(e.get("msg", "")) for e in state.RECENT_LOGS)


def test_undo_keeps_a_spool_the_user_had_buffered_before_the_swap():
    """#99 was already in the buffer when the swap took it off XL-1: the move
    adds nothing, so Undo takes nothing out (it used to drop #99)."""
    state.GLOBAL_BUFFER = [{"id": 99, "display": "#99"}]
    sm = _sm(OWN_SLOT_1)
    store = LocationsStore(ROWS)
    res, _ = _move(sm, store=store)
    assert [i["id"] for i in res["to_buffer"]] == [99] and not state.UNDO_STACK[-1].get("buffered")
    undone = _call(sm, lambda: logic.perform_undo(), store=store)
    assert undone.get("success") is True and undone.get("unbuffered") == [], undone
    assert _buffer_ids() == [99]


def test_a_doubled_head_that_refuses_still_reports_the_buffered_spool():
    """XL-1 holds #99 (slot 1's own) and #77 (from the PolyDryer). The load is
    confirmed, #99 goes to the buffer, then #77's eject is rejected: the move is
    refused, but #99, already Unassigned, is still answered as to_buffer and
    recorded for Undo."""
    sm = _sm(OWN_SLOT_1, more={77: {"location": "XL-1", "extra": _trail("PM-DB-2", 1)}}, reject_ids=[77])
    res, _ = _move(sm, confirmed_fed_heads=["XL-1#77"])
    assert sm.spools[99]["location"] == "" and _buffer_ids() == [99]
    assert [i["id"] for i in res.get("to_buffer") or []] == [99], res
    assert "42" in (res.get("auto_deploy_skipped") or {}), res
    assert state.UNDO_STACK[-1]["buffered"] == [99] and 99 in state.UNDO_STACK[-1]["ejections"]


def test_undo_through_the_route_answers_unbuffered(client):
    sm = _sm(OWN_SLOT_1)
    store = LocationsStore(ROWS)
    _move(sm, store=store)
    rec = state.UNDO_STACK[-1]
    res = _call(sm, lambda: client.post("/api/undo", json={"confirm": True, "undo_id": rec["id"]}),
                store=store).get_json()
    assert res.get("success") is True and res.get("unbuffered") == [99], res
    assert state.GLOBAL_BUFFER == []
