"""Group 40.0a + item H — nothing is filed on a Printer row that is not itself a
toolhead.

Derek's D3 (2026-09-13): "a picker, not a refusal… Underneath, the server refuses
placement on the Printer row itself, keyed on 'this row is not itself one of its
printer's toolheads' so CORE1 stays loadable." Since the 2026-09-29 INDX hotfix a
multi-head Printer row is a generic target, so `LOC:XL` / `LOC:RCOI` with a buffer
filed every buffered spool on the row itself. Claude's call 26 (g40-q7, no veto):
a Printer row with no toolheads set up is refused too, pointing at Settings →
Toolheads; the refusal names the printer's heads, and a Printer Pool only when it
has one. Call 27 (g40-q8): Bulk Move onto XL / RCOI stays refused, in printer
wording, and a spool filed on a Printer row itself becomes movable.

The real engine runs over move_engine_harness's fakes and a live locations store.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import app as app_module  # noqa: E402
import logic  # noqa: E402
import state  # noqa: E402
from move_engine_harness import IDLE, FakeSpoolman, LocationsStore, run_move  # noqa: E402

XL, INDX = "🦝 XL", "🦝 Core One INDX"
PRINTER_MAP = {
    **{f"XL-{n}": {"printer_name": XL, "position": n - 1} for n in range(1, 6)},
    **{f"RCOI-{n}": {"printer_name": INDX, "position": n - 1} for n in range(1, 9)},
    "CORE1": {"printer_name": "Core One", "position": 0},
}
ROWS = [
    {"LocationID": "LR", "Type": "Room", "Max Spools": "0"},
    {"LocationID": "XL", "Name": "XL", "Type": "Printer", "Max Spools": "0", "parent_id": "LR",
     "toolheads": [{"location_id": f"XL-{n}", "position": n - 1} for n in range(1, 6)]},
    *[{"LocationID": f"XL-{n}", "Type": "Tool Head", "Max Spools": "1", "parent_id": "XL"} for n in range(1, 6)],
    {"LocationID": "CR", "Type": "Room", "Max Spools": "0"},
    {"LocationID": "RCOI", "Name": "Core One INDX", "Type": "Printer", "Max Spools": "0", "parent_id": "CR",
     "toolheads": [{"location_id": f"RCOI-{n}", "position": n - 1} for n in range(1, 9)]},
    *[{"LocationID": f"RCOI-{n}", "Type": "Tool Head", "Max Spools": "1", "parent_id": "RCOI"} for n in range(1, 9)],
    {"LocationID": "CORE1", "Name": "Core One", "Type": "Printer", "Max Spools": "1", "parent_id": "CR",
     "toolheads": [{"location_id": "CORE1", "position": 0}]},
    {"LocationID": "MK4", "Name": "MK4", "Type": "Printer", "Max Spools": "1", "parent_id": "CR", "toolheads": []},
    {"LocationID": "LR-MDB-1", "Type": "Dryer Box", "Max Spools": "4", "parent_id": "LR",
     "extra": {"slot_targets": {"1": "XL-1", "4": "PRINTER:XL"}}},
    {"LocationID": "CR-CT-2-R1", "Type": "Cart Row", "Max Spools": "0", "parent_id": "CR"},
]

XL_MSG = "XL is a printer, not a toolhead — pick one of its toolheads (XL-1 to XL-5) or a Printer Pool slot."
RCOI_MSG = "RCOI (Core One INDX) is a printer, not a toolhead — pick one of its toolheads (RCOI-1 to RCOI-8)."
MK4_MSG = "MK4 has no toolheads set up yet — add them in ⚙️ Settings → Toolheads."


@pytest.fixture(autouse=True)
def _quiet(monkeypatch):
    monkeypatch.setattr(state, "UNDO_STACK", [])
    monkeypatch.setattr(state, "GLOBAL_BUFFER", [])
    monkeypatch.setattr(state, "BULK_MOVE_SESSION", {"active": False})
    monkeypatch.setattr(state, "AUDIT_SESSION", {"active": False})


@pytest.fixture
def logs(monkeypatch):
    calls = []
    monkeypatch.setattr(state, "add_log_entry", lambda msg, *a, **k: calls.append((msg, a)))
    return calls


@pytest.fixture
def client():
    app_module.app.config["TESTING"] = True
    return app_module.app.test_client()


def _go(sm, call=None, **kw):
    return run_move(sm, probe=IDLE, store=LocationsStore(ROWS), printer_map=PRINTER_MAP, call=call, **kw)


@pytest.mark.parametrize("target, msg", [("XL", XL_MSG), ("RCOI", RCOI_MSG), ("MK4", MK4_MSG)],
                         ids=["multi-head-with-pool", "multi-head", "no-heads-yet"])
def test_a_printer_row_that_is_not_a_head_takes_no_spool(logs, target, msg):
    sm = FakeSpoolman({42: {"location": "CR-CT-2-R1", "extra": {}},
                       7: {"location": "XL-3", "extra": {}}})
    res = _go(sm, target=target, raw_spools=[42])
    assert res["status"] == "error" and res["blocked_reason"] == "printer_row", res
    assert res["msg"] == msg and res["failures"] == {"42": msg}, res
    assert sm.writes == [] and sm.spools[42]["location"] == "CR-CT-2-R1"
    assert (f"⚠️ Not moved: {msg}", ("WARNING", "ffaa00")) in logs, logs


def test_a_buffer_of_several_spools_is_refused_too(logs):
    """The dashboard's L124 trim misses a Printer row (Max 0), so LOC:XL sent the
    whole buffer, and every spool was filed on XL itself."""
    sm = FakeSpoolman({42: {"location": "CR-CT-2-R1", "extra": {}}, 43: {"location": "CR-CT-2-R1", "extra": {}}})
    res = _go(sm, target="XL", raw_spools=[42, 43])
    assert res["blocked_reason"] == "printer_row" and set(res["failures"]) == {"42", "43"}, res
    assert sm.writes == []


def test_a_printer_that_is_its_own_head_still_loads(logs):
    """CORE1 lists itself as its toolhead: it stays loadable, Smart Load included."""
    sm = FakeSpoolman({99: {"location": "CORE1", "extra": {}}, 42: {"location": "CR-CT-2-R1", "extra": {}}})
    res = _go(sm, target="CORE1", raw_spools=[42])
    assert logic.smart_move_failure(res, 42) == "", res
    assert sm.direct_at("CORE1") == [42]


def test_the_scan_routes_say_why(client, logs):
    sm = FakeSpoolman({42: {"location": "CR-CT-2-R1", "extra": {}}})
    body = _go(sm, call=lambda: client.post(
        "/api/smart_move", json={"location": "XL", "spools": [42]})).get_json()
    assert body["status"] == "error" and body["msg"] == XL_MSG, body
    assert sm.writes == []


# --- item H: Bulk Move --------------------------------------------------------------

def _plan(sm, source, dest):
    return _go(sm, call=lambda: logic.plan_bulk_move(source, dest))


@pytest.mark.parametrize("dest", ["XL", "RCOI"])
def test_bulk_move_onto_a_printer_row_is_refused_in_printer_words(logs, dest):
    sm = FakeSpoolman({42: {"location": "CR-CT-2-R1", "extra": {}}})
    plan = _plan(sm, "CR-CT-2-R1", dest)
    assert plan["ok"] is False and plan["blocked_reason"] == "printer_row", plan
    assert plan["msg"] == (f"{dest} is a printer, not a toolhead — bulk move needs a Room / Shelf / "
                           f"Cart / Dryer Box destination."), plan


def test_bulk_move_onto_a_head_keeps_its_single_spool_refusal(logs):
    plan = _plan(FakeSpoolman({}), "CR-CT-2-R1", "XL-1")
    assert plan["blocked_reason"] == "single_occupancy", plan


def test_a_spool_filed_on_a_printer_row_itself_is_movable(logs):
    """Legacy data (none on dev or prod today): Bulk Move can clean it up, while
    a spool loaded on a head stays a skip."""
    sm = FakeSpoolman({42: {"location": "XL", "extra": {}}, 7: {"location": "XL-3", "extra": {}}})
    plan = _plan(sm, "XL", "CR-CT-2-R1")
    assert plan["ok"] is True and plan["movable_ids"] == [42], plan
    assert {"id": 7, "reason": "loaded in a toolhead slot"} in plan["skipped"], plan
