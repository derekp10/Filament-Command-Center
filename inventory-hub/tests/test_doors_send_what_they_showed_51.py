"""Group 51.5-51.7 — a move does what the screen showed, and nothing else.

Three doors showed a spool in a dialog but sent less than they showed, so a
spool another user (or another tab) put there meanwhile was moved unseen:
  - 51.5 the Quick-Swap tap named the slot's spool, but /api/quickswap loaded
    whatever spool is in the slot now: `expected_spool` (409
    quickswap_spool_mismatch, Return's shape);
  - 51.6 the Printer picker's head pick asked "XL-3 holds #99", but sent only
    the head, so a different resident was unloaded unasked: `expected_residents`
    (blocked_reason residents_changed, at step 4's strict read and at step 6's
    re-list after the printer probe);
  - 51.7 the grid's (and the slot picker's) Swap / Overwrite named the slot's
    stored spool, but sent only the slot: `expected_occupant` (blocked_reason
    occupant_changed, at step 6's strict slot read).
Every field is optional (absent = today's behaviour), and only the accidental
case is refused: a head that emptied, or a slot whose spool left, is filled as
asked (Derek: guard only the accidental case).

Runs the REAL routes and move engine (tests/move_engine_harness.py; nothing
mocks perform_smart_move). Base proof (52741e6): every test fails there except
the ones marked "control".
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

PRINTER_MAP = {f"XL-{n}": {"printer_name": "XL", "position": n - 1} for n in (1, 2, 3)}
ROWS = [
    {"LocationID": "LR", "Type": "Room", "Max Spools": "0"},
    {"LocationID": "XL", "Type": "Printer", "Max Spools": "0", "parent_id": "LR",
     "toolheads": [{"location_id": f"XL-{n}", "position": n - 1} for n in (1, 2, 3)]},
    *[{"LocationID": f"XL-{n}", "Type": "Tool Head", "Max Spools": "1", "parent_id": "XL"} for n in (1, 2, 3)],
    {"LocationID": "LR-MDB-1", "Type": "Dryer Box", "Max Spools": "4", "parent_id": "LR",
     "extra": {"slot_targets": {"1": "XL-1", "2": "XL-2", "3": "XL-3"}}},
    {"LocationID": "LR-MDB-2", "Type": "Dryer Box", "Max Spools": "2", "parent_id": "LR", "extra": {}},
    {"LocationID": "CR-CT-2-R1", "Type": "Cart Row", "Max Spools": "0", "parent_id": "LR"},
]
DOOR = {"confirmed_toolheads": [], "confirmed_fed_heads": []}


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


def _call(sm, fn, probe=IDLE, store=None):
    return run_move(sm, probe=probe, store=store or LocationsStore(ROWS), printer_map=PRINTER_MAP, call=fn)


def _post(client, sm, url, body, probe=IDLE):
    r = _call(sm, lambda: client.post(url, json=body), probe=probe)
    return r.status_code, r.get_json()


def _in_slot(box, slot):
    return {"location": box, "extra": {"container_slot": str(slot)}}


def _on_head(head, box="", slot=""):
    extra = {"physical_source": box, "physical_source_slot": str(slot)} if box else {}
    return {"location": head, "extra": extra}


# ---- 51.5 Quick-Swap: expected_spool ---------------------------------------------------------------

def _quickswap(client, sm, **extra):
    return _post(client, sm, "/api/quickswap", dict({"toolhead": "XL-3", "box": "LR-MDB-1", "slot": "3",
                                                     "confirmed_toolheads": []}, **extra))


def test_quickswap_refuses_a_spool_the_card_did_not_show(client):
    """The card showed #57 in LR-MDB-1 slot 3; #77 is there now."""
    sm = FakeSpoolman({77: _in_slot("LR-MDB-1", 3)})
    status, body = _quickswap(client, sm, expected_spool=57)
    assert status == 409 and body["action"] == "quickswap_spool_mismatch", body
    assert body["spool"] == 77 and body["expected_spool"] == 57, body
    assert "LR-MDB-1 slot 3 holds #77 now, not #57" in body["error"], body
    assert sm.writes == [] and sm.direct_at("XL-3") == [], sm.writes


def test_control_quickswap_loads_the_spool_the_card_showed(client):
    """Control (green on the base too: it ignored the field)."""
    sm = FakeSpoolman({57: _in_slot("LR-MDB-1", 3)})
    status, body = _quickswap(client, sm, expected_spool="57")
    assert status == 200 and body["action"] == "quickswap_done" and body["moved"] == 57, body
    assert sm.direct_at("XL-3") == [57]


def test_control_quickswap_without_the_field_loads_what_is_there(client):
    """Control: a page from before the release sends no expected_spool."""
    sm = FakeSpoolman({77: _in_slot("LR-MDB-1", 3)})
    status, body = _quickswap(client, sm)
    assert status == 200 and body["moved"] == 77, body


def test_quickswap_refuses_a_malformed_expected_spool(client):
    sm = FakeSpoolman({57: _in_slot("LR-MDB-1", 3)})
    status, body = _quickswap(client, sm, expected_spool="#57x")
    assert status == 400 and body["action"] == "quickswap_bad_request", body
    assert sm.writes == []


# ---- 51.6 the Printer picker's head pick: expected_residents ---------------------------------------

def _head_pick(client, sm, url="/api/smart_move", probe=IDLE, **extra):
    body = {"location": "XL-2", "spools": [42], "origin": "buffer", **DOOR, **extra}
    if url == "/api/manage_contents":
        body = {"action": "add", "location": "XL-2", "spool_id": "ID:42", "origin": "manual_override", **DOOR,
                **extra}
    return _post(client, sm, url, body, probe=probe)


@pytest.mark.parametrize("url", ["/api/smart_move", "/api/manage_contents"], ids=["smart-move", "force-location"])
def test_a_head_shown_empty_that_holds_a_spool_now_is_refused(client, url):
    """The picker showed XL-2 empty; #99 was loaded onto it before the pick landed."""
    sm = FakeSpoolman({42: {"location": "CR-CT-2-R1", "extra": {}}, 99: _on_head("XL-2", "LR-MDB-1", 2)})
    _status, body = _head_pick(client, sm, url=url, expected_residents=[])
    assert body["blocked_reason"] == "residents_changed", body
    assert "XL-2 now holds #99, which wasn't on it when you picked XL-2 (it was empty)" in body["msg"], body
    assert sm.writes == [] and sm.direct_at("XL-2") == [99], sm.writes


def test_a_head_whose_resident_was_swapped_meanwhile_is_refused(client):
    """The picker said "XL-2 holds #99"; #77 is on it now (#99 went elsewhere)."""
    sm = FakeSpoolman({42: {"location": "CR-CT-2-R1", "extra": {}}, 77: _on_head("XL-2")})
    _status, body = _head_pick(client, sm, expected_residents=[99])
    assert body["blocked_reason"] == "residents_changed", body
    assert "XL-2 now holds #77" in body["msg"] and "(it held #99)" in body["msg"], body
    assert sm.writes == [], sm.writes


@pytest.mark.parametrize("residents, now", [([99], {99: _on_head("XL-2", "LR-MDB-1", 2)}), ([99], {})],
                         ids=["as-shown", "emptied-meanwhile"])
def test_a_head_as_shown_or_emptied_meanwhile_is_loaded(client, residents, now):
    """The resident shown is unloaded as the question said; a head that emptied
    meanwhile is simply loaded (only a spool nobody was shown is protected).
    The as-shown case is a control (green on the base too)."""
    sm = FakeSpoolman({42: {"location": "CR-CT-2-R1", "extra": {}}, **now})
    _status, body = _head_pick(client, sm, expected_residents=residents)
    assert body["status"] == "success" and not body["failures"], body
    assert sm.direct_at("XL-2") == [42], sm.spools


def test_control_a_head_pick_without_the_field_unloads_whatever_is_there(client):
    """Control: a page from before the release (today's behaviour)."""
    sm = FakeSpoolman({42: {"location": "CR-CT-2-R1", "extra": {}}, 77: _on_head("XL-2")})
    _status, body = _head_pick(client, sm)
    assert body["status"] == "success" and sm.direct_at("XL-2") == [42], body


def _probe_loading(sm, sid, head):
    """A printer probe during which another request loads `sid` onto `head`
    (step 4 read the head before it; step 6 re-lists it after)."""
    def probe(_url, printer_name):
        sm.spools[sid] = {"location": head, "extra": {}}
        return {"state": "IDLE", "is_active": False}
    return probe


def test_a_spool_loaded_during_the_printer_probe_is_refused_not_unloaded_unseen(client):
    sm = FakeSpoolman({42: {"location": "CR-CT-2-R1", "extra": {}}})
    _status, body = _head_pick(client, sm, probe=_probe_loading(sm, 77, "XL-2"), expected_residents=[])
    assert body["blocked_reason"] == "residents_changed", body
    assert sm.direct_at("XL-2") == [77] and sm.spools[42]["location"] == "CR-CT-2-R1", sm.spools


def test_control_without_the_field_a_spool_loaded_during_the_probe_is_unloaded(client):
    """Control: review engine-2's rule for a request that names nothing."""
    sm = FakeSpoolman({42: {"location": "CR-CT-2-R1", "extra": {}}})
    _status, body = _head_pick(client, sm, probe=_probe_loading(sm, 77, "XL-2"))
    assert body["status"] == "success" and sm.direct_at("XL-2") == [42], body


def test_the_wizard_edit_drops_a_held_head_pick_whose_head_changed(client):
    """The wizard holds the pick until Save: XL-2 was empty when picked."""
    sm = FakeSpoolman({42: {"location": "CR-CT-2-R1", "extra": {}}, 99: _on_head("XL-2")})
    _status, body = _post(client, sm, "/api/edit_spool_wizard",
                          dict({"spool_id": 42, "spool_data": {"location": "XL-2"}, "expected_residents": []}, **DOOR))
    assert body["location_result"]["blocked_reason"] == "residents_changed", body
    assert body["location_moved"] is False and body.get("pick_refused") is True, body
    assert sm.direct_at("XL-2") == [99]


# ---- 51.7 Swap / Overwrite: expected_occupant ------------------------------------------------------

def _swap(client, sm, url="/api/manage_contents", **extra):
    if url == "/api/smart_move":
        body = {"location": "LR-MDB-2", "spools": [42], "slot": "1", "origin": "buffer", **DOOR, **extra}
    else:
        body = {"action": "add", "location": "LR-MDB-2", "slot": "1", "spool_id": "ID:42", **DOOR, **extra}
    return _post(client, sm, url, body)


@pytest.mark.parametrize("url", ["/api/manage_contents", "/api/smart_move"], ids=["grid", "slot-picker"])
@pytest.mark.parametrize("swap", [True, False], ids=["swap", "overwrite"])
def test_a_slot_whose_spool_changed_since_the_prompt_is_refused(client, url, swap):
    """The prompt named #57 in LR-MDB-2 slot 1; #77 is there now."""
    sm = FakeSpoolman({42: {"location": "CR-CT-2-R1", "extra": {}}, 77: _in_slot("LR-MDB-2", 1)})
    _status, body = _swap(client, sm, url=url, expected_occupant=57, **({"swap": True} if swap else {}))
    assert body.get("blocked_reason") == "occupant_changed", body
    assert "LR-MDB-2 slot 1 holds #77 now, not #57" in logic.smart_move_failure(body, 42), body
    assert sm.writes == [], sm.writes
    assert state.GLOBAL_BUFFER == [], state.GLOBAL_BUFFER


def test_control_the_spool_shown_is_swapped_out(client):
    """Control (green on the base too): #57 is still there."""
    sm = FakeSpoolman({42: {"location": "CR-CT-2-R1", "extra": {}}, 57: _in_slot("LR-MDB-2", 1)})
    _status, body = _swap(client, sm, expected_occupant=57, swap=True)
    assert body["status"] == "success" and not body["failures"], body
    assert sm.spools[42]["location"] == "LR-MDB-2" and [i["id"] for i in body["to_buffer"]] == [57], body


def test_a_slot_whose_spool_left_meanwhile_is_filled_as_asked(client):
    """#57 left the slot: nobody unseen is moved, so #42 goes in (a control too)."""
    sm = FakeSpoolman({42: {"location": "CR-CT-2-R1", "extra": {}}})
    _status, body = _swap(client, sm, expected_occupant=57, swap=True)
    assert body["status"] == "success" and not body["failures"], body
    assert sm.spools[42]["location"] == "LR-MDB-2" and sm.spools[42]["extra"]["container_slot"] == "1"


def test_control_an_overwrite_without_the_field_unseats_whatever_is_there(client):
    sm = FakeSpoolman({42: {"location": "CR-CT-2-R1", "extra": {}}, 77: _in_slot("LR-MDB-2", 1)})
    _status, body = _swap(client, sm)
    assert body["status"] == "success" and not body["failures"], body
    assert sm.spools[77]["extra"]["container_slot"] == "", sm.spools[77]


# ---- the request readers ---------------------------------------------------------------------------

@pytest.mark.parametrize("raw, expected", [
    (None, None), ("x", None), ([], []), ([99, "57", '"12"'], [99, 57, 12]), (["#9"], None), ((7,), [7]),
])
def test_expected_residents_from(raw, expected):
    data = {} if raw is None else {"expected_residents": raw}
    assert logic.expected_residents_from(data) == expected
    assert logic.expected_residents_from(None) is None


@pytest.mark.parametrize("raw, expected", [(None, None), ("", None), (57, 57), ("57", 57), ('"57"', 57), ("x", None)])
def test_expected_occupant_from(raw, expected):
    assert logic.expected_occupant_from({"expected_occupant": raw}) == expected
    assert logic.expected_occupant_from({}) is None
