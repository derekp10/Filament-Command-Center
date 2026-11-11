"""A slot-label scan's target check reads locations_db's Types (Group 53 review, rb-6).

api_identify_scan's LOC:<place>:SLOT:<n> branch refuses a place that can't take a
spool in a slot: a 400 `assignment_bad_target` and an ERROR Activity Log line, and
nothing moves. It kept its own copy of the Types that can,
{'Dryer Box', 'MMU Slot', 'Tool Head', 'No MMU Direct Load', 'Printer'}, so a head
Type added to locations_db.TOOLHEAD_TYPES (the backend's one list, which the page's
window.TOOLHEAD_TYPES mirrors, Group 53.1) was refused as a slot-scan target until
someone found this copy too. The check now reads locations_db.TOOLHEAD_TYPES,
DRYER_BOX_TYPE and PRINTER_ROW_TYPE when it runs.

It still compares the row's Type as the row holds it, untrimmed, as the move engine
does (`logic._holds_one_spool` / `_is_single_occupancy`, its dryer branch): a Type
with a stray space (" Tool Head") is refused here, as before, rather than handed to
an engine that would file a spool there as a plain place without unloading the one
on it (the integrator's call, Group 53 review round 3; one trimmed Type read for
every door is a follow-up). Only a hand-edited locations.json holds such a Type: the
location editor trims a custom Type. The Quick-Swap deposit's `shown_empty` rule in
the same branch reads the same Type. A place that can't take a slot keeps the same
answer and the same ERROR line, its Type as the row holds it, and the match stays
exact and case-sensitive.

The real route; the location list is a fixture and logic.perform_smart_move a mock
(as test_assignment_logic.py does), so nothing reads Spoolman.
"""
from __future__ import annotations

import os
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import app as app_module  # noqa: E402
import locations_db  # noqa: E402
import state  # noqa: E402

# A head Type the backend doesn't know today, added to its one list by a test.
NEW_HEAD_TYPE = "Tool Changer Dock"


@pytest.fixture
def client():
    app_module.app.config["TESTING"] = True
    return app_module.app.test_client()


@pytest.fixture(autouse=True)
def buffer_and_logs(monkeypatch):
    """A buffered spool #42, and the Activity Log lines as (msg, level, colour)."""
    monkeypatch.setattr(state, "GLOBAL_BUFFER", [{"id": 42, "display": "Test Spool"}])
    lines = []
    monkeypatch.setattr(state, "add_log_entry",
                        lambda msg, *a, **k: lines.append((msg,) + tuple(a[:2])))
    return lines


def _row(type_, lid="PLACE-1", max_spools="1", **more):
    row = {"LocationID": lid, "Max Spools": max_spools, "Name": "A place"}
    if type_ is not _NO_TYPE:
        row["Type"] = type_
    row.update(more)
    return row


_NO_TYPE = object()


def _scan(client, rows, text, **body):
    """POST the scan with `rows` as locations.json; answers (response, the mock
    standing in for perform_smart_move)."""
    with patch.object(app_module.locations_db, "load_locations_list", return_value=rows), \
         patch.object(app_module.logic, "perform_smart_move", return_value={"status": "success"}) as mv:
        r = client.post("/api/identify_scan", json=dict({"text": text, "source": "barcode"}, **body))
    return r, mv


def _moved(r, mv, target, slot, **slot_kw):
    assert r.status_code == 200, r.get_json()
    assert r.get_json()["action"] == "assignment_done", r.get_json()
    mv.assert_called_once()
    args, kwargs = mv.call_args
    assert args == (target, [42])
    assert {k: kwargs.get(k) for k in ("target_slot", "picked_slot")} == dict(
        {"target_slot": None, "picked_slot": None}, **slot_kw)
    assert kwargs["origin"] == "slot_qr_scan"


# ---------------------------------------------------------------------------
# The backend's own list decides, when the scan runs
# ---------------------------------------------------------------------------

def test_a_head_type_added_to_the_backends_one_list_is_a_slot_scan_target(client, monkeypatch):
    """The review's case: a new head Type goes in locations_db.TOOLHEAD_TYPES (and the
    page's @fcc-toolhead-types block), nowhere else. The branch's own copy refused it."""
    monkeypatch.setattr(locations_db, "TOOLHEAD_TYPES",
                        frozenset(locations_db.TOOLHEAD_TYPES | {NEW_HEAD_TYPE}))
    r, mv = _scan(client, [_row(NEW_HEAD_TYPE, "DOCK-1")], "LOC:DOCK-1:SLOT:1")
    _moved(r, mv, "DOCK-1", "1", target_slot="1")


def test_a_type_taken_out_of_the_backends_one_list_is_refused(client, monkeypatch):
    """The other direction: the check holds no Type of its own. Taken out of
    locations_db.TOOLHEAD_TYPES, 'MMU Slot' is no slot-scan target."""
    monkeypatch.setattr(locations_db, "TOOLHEAD_TYPES",
                        frozenset(locations_db.TOOLHEAD_TYPES - {"MMU Slot"}))
    r, mv = _scan(client, [_row("MMU Slot", "MMU-1")], "LOC:MMU-1:SLOT:1")
    assert r.status_code == 400 and r.get_json()["action"] == "assignment_bad_target"
    mv.assert_not_called()


@pytest.mark.parametrize("type_, max_spools, slot", [
    ("Dryer Box", "4", "2"),
    ("Tool Head", "1", "1"),
    ("MMU Slot", "1", "1"),
    ("No MMU Direct Load", "1", "1"),
    ("Printer", "1", "1"),
])
def test_every_container_type_is_still_a_slot_scan_target(client, type_, max_spools, slot):
    r, mv = _scan(client, [_row(type_, "PLACE-1", max_spools)], f"LOC:PLACE-1:SLOT:{slot}")
    _moved(r, mv, "PLACE-1", slot, target_slot=slot)


@pytest.mark.parametrize("type_, max_spools, slot", [
    (" Tool Head", "1", "1"),
    ("MMU Slot ", "1", "1"),
    ("\tNo MMU Direct Load", "1", "1"),
    (" Dryer Box ", "4", "3"),
    ("Printer  ", "1", "1"),
])
def test_a_type_with_stray_spaces_is_refused_as_the_move_engine_would_misread_it(
        client, buffer_and_logs, type_, max_spools, slot):
    """The move engine compares a Type untrimmed: a padded head row outside the printer
    map would be filed as a plain place without unloading its resident, and a padded
    Dryer Box isn't a box to its dryer branch. So the door refuses it, as it always did,
    with the same answer and ERROR line, its Type as the row holds it."""
    r, mv = _scan(client, [_row(type_, "PLACE-1", max_spools)], f"LOC:PLACE-1:SLOT:{slot}")
    assert r.status_code == 400
    assert r.get_json() == {"type": "assignment", "action": "assignment_bad_target",
                            "location": "PLACE-1", "slot": slot, "found_type": type_}
    assert buffer_and_logs == [
        (f"❌ Slot scan target <b>PLACE-1</b> invalid (type={type_}) — scan dropped", "ERROR", "ff0000")]
    mv.assert_not_called()


# ---------------------------------------------------------------------------
# A place that can't take a slot: the same answer and the same ERROR line
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("type_", [
    "Room", "Virtual Room", "Section", "Wall Shelf", "Cart",
    "",                 # a row with a blank Type
    _NO_TYPE,           # a row with no Type at all
    "tool head",        # exact and case-sensitive, as the backend's other reads are
    "Toolbox", "MMU Buffer", "Direct Load Rack",    # a head Type's words aren't a head Type
], ids=["Room", "Virtual Room", "Section", "Wall Shelf", "Cart", "blank", "no Type",
        "lower case", "Toolbox", "MMU Buffer", "Direct Load Rack"])
def test_a_place_that_cant_take_a_slot_keeps_the_same_answer_and_error_line(client, buffer_and_logs, type_):
    r, mv = _scan(client, [_row(type_, "PLACE-1", "4")], "LOC:PLACE-1:SLOT:1")
    found = None if type_ is _NO_TYPE else type_
    assert r.status_code == 400
    assert r.get_json() == {"type": "assignment", "action": "assignment_bad_target",
                            "location": "PLACE-1", "slot": "1", "found_type": found}
    assert buffer_and_logs == [
        (f"❌ Slot scan target <b>PLACE-1</b> invalid (type={found}) — scan dropped", "ERROR", "ff0000")]
    mv.assert_not_called()
    assert state.GLOBAL_BUFFER == [{"id": 42, "display": "Test Spool"}]


def test_a_place_locations_json_doesnt_have_keeps_the_same_answer_and_error_line(client, buffer_and_logs):
    r, mv = _scan(client, [_row("Tool Head", "OTHER-1")], "LOC:PLACE-1:SLOT:1")
    assert r.status_code == 400
    assert r.get_json() == {"type": "assignment", "action": "assignment_bad_target",
                            "location": "PLACE-1", "slot": "1", "found_type": "missing"}
    assert buffer_and_logs == [
        ("❌ Slot scan target <b>PLACE-1</b> invalid (type=missing) — scan dropped", "ERROR", "ff0000")]
    mv.assert_not_called()


# ---------------------------------------------------------------------------
# The deposit's "shown empty" reads the same Type
# ---------------------------------------------------------------------------

def test_a_deposit_shown_empty_on_a_multi_slot_box_is_filled_only_while_free(client):
    """Group 51 review (engine-3): the Quick-Swap DEPOSIT tile that showed slot 2
    empty sends `shown_empty`, and a multi-slot box's slot then goes as
    `picked_slot` (filled only while still free), never as an Overwrite. The rule
    reads the same Type the target check does (locations_db.DRYER_BOX_TYPE)."""
    r, mv = _scan(client, [_row("Dryer Box", "BOX-1", "4")], "LOC:BOX-1:SLOT:2",
                  spool_id=42, shown_empty=True)
    _moved(r, mv, "BOX-1", "2", picked_slot="2")


@pytest.mark.parametrize("type_, max_spools", [("Tool Head", "1"), ("Dryer Box", "1"), ("Printer", "2")],
                         ids=["a head", "a single-slot box", "a multi-slot place that isn't a box"])
def test_a_deposit_shown_empty_elsewhere_keeps_its_slot(client, type_, max_spools):
    """The control: only a MULTI-slot Dryer Box reads `shown_empty` (a single-slot
    box keeps its own slot-1 rule, and a place with more than one slot that isn't
    a Dryer Box keeps its explicit slot: the Type half of the rule, which no other
    case here would miss)."""
    r, mv = _scan(client, [_row(type_, "PLACE-1", max_spools)], "LOC:PLACE-1:SLOT:1",
                  spool_id=42, shown_empty=True)
    _moved(r, mv, "PLACE-1", "1", target_slot="1")
