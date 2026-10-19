"""Finish the slot_targets reader migration (standalone fix, 2026-10-13).

`locations_db.bindings_from_row` is the one guarded reader of a Dryer Box's
`extra.slot_targets` (2026-08-03; tests/test_bindings_from_row_malformed.py pins
it and its first four call sites). Ten more sites in nine functions still read
`extra.slot_targets` directly and raised on a row whose `extra` is not a dict,
so ONE malformed Dryer Box row could:
  - break a source-less move onto a toolhead (_find_box_slot_feeding_toolhead);
  - break a move into a Dryer Box slot (perform_smart_move's active-print
    pre-check, and its auto-deploy lookup — after the box write had landed);
  - 500 the Quick-Swap bind picker (GET /api/dryer_boxes/slots) and Quick-Swap
    Return's binding fallback;
  - block EVERY toolhead removal in Settings (the guard fails closed);
  - abort a single-slot box attach, or a detach for every box on that head;
  - 500 the Feeds save whenever any OTHER box is malformed;
  - break a toolhead delete's cascade.

Each test poisons one row next to a good one. The bad row must be ignored by a
reader, or replaced by a clean `extra` in a writer (a non-dict `extra` carries
no siblings worth keeping: the migrate_feeder_map_if_needed precedent), and the
good row must still be read. The engine tests run the REAL perform_smart_move
with only Spoolman faked.

HEAD proof: every test below except the source canary's "still delegates"
checks raises AttributeError/ValueError (or 500s) on the pre-fix code.
"""
from __future__ import annotations

import contextlib
import os
import re
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import app as app_module  # noqa: E402
import locations_db  # noqa: E402
import logic  # noqa: E402
import routes_bindings  # noqa: E402
import spoolman_api  # noqa: E402
import state  # noqa: E402

BOX = locations_db.DRYER_BOX_TYPE
POISON = "slot_targets: 1 -> XL-1"   # YAML-ish text typed where an object belongs


def _bad(loc_id="PM-DB-BAD", max_spools="4"):
    return {"LocationID": loc_id, "Type": BOX, "Max Spools": max_spools,
            "Name": loc_id, "extra": POISON}


def _good(loc_id="PM-DB-OK", targets=None, max_spools="4"):
    return {"LocationID": loc_id, "Type": BOX, "Max Spools": max_spools,
            "Name": loc_id, "extra": {"slot_targets": dict(targets or {})}}


@pytest.fixture
def client():
    app_module.app.config["TESTING"] = True
    return app_module.app.test_client()


@pytest.fixture(autouse=True)
def _quiet_log(monkeypatch):
    monkeypatch.setattr(state, "add_log_entry", lambda *a, **k: None)


# --------------------------------------------------------------------------- #
# Pure reads                                                                  #
# --------------------------------------------------------------------------- #

def test_find_box_slot_feeding_toolhead():
    """logic.py — called unguarded by the PRINTER MOVE branch, so one bad box
    broke every source-less move onto a toolhead."""
    rows = [_bad(), "not even a row", _good(targets={"2": "XL-1"})]
    assert logic._find_box_slot_feeding_toolhead("XL-1", rows) == ("PM-DB-OK", "2")
    assert logic._find_box_slot_feeding_toolhead("XL-9", rows) == (None, None)


MOVE_LOCS = [
    _bad("PM-DB-BAD"),
    {"LocationID": "XL-1", "Type": "Tool Head", "Max Spools": "1", "Name": "XL-1"},
    {"LocationID": "CR", "Type": "Room", "Max Spools": "0", "Name": "Computer Room"},
]


def _move_into_poisoned_box(confirm_active_print, auto_deploy, box_row=None):
    """The REAL engine, Spoolman faked: spool #42 (in CR) into PM-DB-BAD slot 1.
    `box_row` replaces the poisoned box (same LocationID) for other malformations."""
    writes = []
    locs = [dict(r) for r in MOVE_LOCS]
    if box_row is not None:
        locs[0] = dict(box_row)
    with contextlib.ExitStack() as st:
        st.enter_context(patch.object(logic.locations_db, "load_locations_list",
                                      return_value=locs))
        st.enter_context(patch.object(logic.locations_db, "get_active_printer_map",
                                      return_value={"XL-1": {"printer_name": "XL", "position": 0}}))
        st.enter_context(patch.object(logic.config_loader, "load_config", return_value={}))
        st.enter_context(patch.object(logic.config_loader, "get_api_urls",
                                      return_value=("http://sm", "http://fb")))
        st.enter_context(patch.object(logic.spoolman_api, "get_spools_at_location_detailed",
                                      return_value=[]))
        # Group 41.6: the engine reads a target slot strictly before seating.
        st.enter_context(patch.object(logic.spoolman_api, "get_spools_at_location_detailed_strict",
                                      return_value=[]))
        st.enter_context(patch.object(logic.spoolman_api, "get_spools_at_location", return_value=[]))
        st.enter_context(patch.object(logic.spoolman_api, "get_spool",
                                      return_value={"id": 42, "location": "CR", "extra": {}}))
        st.enter_context(patch.object(logic.spoolman_api, "format_spool_display",
                                      return_value={"text": "#42", "color": "ffffff"}))
        st.enter_context(patch.object(logic.spoolman_api, "update_spool",
                                      side_effect=lambda sid, data: writes.append((sid, data)) or {"id": sid}))
        result = logic.perform_smart_move("PM-DB-BAD", [42], target_slot="1", origin="test",
                                          auto_deploy=auto_deploy,
                                          confirm_active_print=confirm_active_print)
    return result, writes


def test_smart_move_active_print_precheck_survives_a_poisoned_target_box():
    """logic.py, the pre-check that walks a named slot's bound toolhead."""
    result, writes = _move_into_poisoned_box(confirm_active_print=False, auto_deploy=False)
    assert isinstance(result, dict) and result.get("status") != "requires_confirm", result
    assert writes and writes[0][0] == 42 and writes[0][1].get("location") == "PM-DB-BAD", writes


def test_smart_move_auto_deploy_lookup_survives_a_poisoned_target_box():
    """logic.py, the auto-deploy lookup. On HEAD it raised AFTER the box write
    had landed, so the caller saw a 500 for a move that half-happened."""
    result, writes = _move_into_poisoned_box(confirm_active_print=True, auto_deploy=True)
    assert isinstance(result, dict), result
    assert not result.get("auto_deployed_to"), "nothing is bound, so nothing deploys"
    assert len(writes) == 1 and writes[0][1].get("location") == "PM-DB-BAD", writes


@pytest.mark.parametrize("value", [False, 0, 0.0, [], "   "])
def test_a_falsy_binding_is_unbound_not_a_phantom_toolhead(value):
    """Review finding (2026-10-13): routing the auto-deploy read through
    bindings_from_row stringified a falsy non-string binding (False -> "False",
    0 -> "0"), so a hand-edited `{"1": false}` meant to say "unassigned" chained
    a SECOND write that moved the spool to a location named "FALSE". The raw read
    it replaced treated every falsy value as unbound; so must the helper."""
    box = {"LocationID": "PM-DB-BAD", "Type": BOX, "Max Spools": "4", "Name": "PM-DB-BAD",
           "extra": {"slot_targets": {"1": value, "2": "XL-1"}}}
    result, writes = _move_into_poisoned_box(confirm_active_print=True, auto_deploy=True, box_row=box)
    assert len(writes) == 1 and writes[0][1].get("location") == "PM-DB-BAD", writes
    assert not result.get("auto_deployed_to"), result
    assert locations_db.bindings_from_row(box) == {"1": None, "2": "XL-1"}


def test_settings_toolhead_removal_guard_is_not_failed_closed_by_a_bad_row(monkeypatch):
    """routes_bindings.py — the guard caught the error and FAILED CLOSED, so one
    bad row blocked every toolhead removal in Settings."""
    rows = [_bad(), _good(targets={"1": "XL-1"})]
    monkeypatch.setattr(locations_db, "load_locations_list", lambda: rows)
    monkeypatch.setattr(spoolman_api, "get_spools_at_location_strict", lambda loc: [])
    old = {"XL-1": {"printer_name": "XL", "position": 0}, "XL-2": {"printer_name": "XL", "position": 1}}
    new = {"XL-1": {"printer_name": "XL", "position": 0}}
    assert routes_bindings._printer_map_blocked_removals(old, new) == []
    # ...and a real binding still blocks:
    blocked = routes_bindings._printer_map_blocked_removals(old, {"XL-2": old["XL-2"]})
    assert [b["location_id"] for b in blocked] == ["XL-1"]
    assert any("bound" in r for r in blocked[0]["reasons"]), blocked


def test_dryer_box_slots_picker_survives_a_bad_row(client, monkeypatch):
    """routes_bindings.py — GET /api/dryer_boxes/slots (the Quick-Swap bind
    picker) answered 500."""
    rows = [_bad(max_spools="2"), _good(targets={"1": "XL-1", "2": ""}, max_spools="2")]
    monkeypatch.setattr(locations_db, "load_locations_list", lambda: rows)
    resp = client.get("/api/dryer_boxes/slots")
    assert resp.status_code == 200, resp.get_data(as_text=True)[:300]
    slots = {(s["box"], s["slot"]): s["target"] for s in resp.get_json()["slots"]}
    assert slots[("PM-DB-OK", "1")] == "XL-1"
    assert slots[("PM-DB-OK", "2")] is None, "a blank binding is unbound"
    assert slots[("PM-DB-BAD", "1")] is None and slots[("PM-DB-BAD", "2")] is None


def test_quickswap_return_binding_fallback_survives_a_bad_row(client, monkeypatch):
    """routes_bindings.py — Return's "first slot bound to this toolhead"
    fallback answered 500. The engine is spied, not run: this pins WHICH box and
    slot the route resolves, which is all the fallback decides. (Group 40.6:
    the fallback is now "the only free slot that feeds the head", read
    strictly, and the slot goes to the engine as `picked_slot`.)"""
    rows = [_bad(), _good(targets={"3": "XL-2"}),
            {"LocationID": "XL-2", "Type": "Tool Head", "Max Spools": "1", "Name": "XL-2"}]
    monkeypatch.setattr(locations_db, "load_locations_list", lambda: rows)
    monkeypatch.setattr(locations_db, "get_active_printer_map",
                        lambda *a, **k: {"XL-2": {"printer_name": "XL", "position": 1}})
    monkeypatch.setattr(spoolman_api, "get_spools_at_location", lambda loc: [42] if loc == "XL-2" else [])
    monkeypatch.setattr(spoolman_api, "get_spool", lambda sid: {"id": 42, "location": "XL-2", "extra": {}})
    monkeypatch.setattr(spoolman_api, "get_spools_at_location_detailed", lambda loc: [])
    monkeypatch.setattr(spoolman_api, "get_spools_at_location_detailed_strict", lambda loc: [])
    calls = []
    monkeypatch.setattr(logic, "perform_smart_move",
                        lambda target, spools, **kw: calls.append((target, spools, kw)) or {"status": "success"})

    resp = client.post("/api/quickswap/return", json={"toolhead": "XL-2"})
    assert resp.status_code == 200, resp.get_data(as_text=True)[:300]
    body = resp.get_json()
    assert body["action"] == "return_done" and body["box"] == "PM-DB-OK" and body["slot"] == "3", body
    assert calls and calls[0][0] == "PM-DB-OK" and calls[0][2].get("picked_slot") == "3", calls


# --------------------------------------------------------------------------- #
# Read-modify-writes                                                          #
# --------------------------------------------------------------------------- #

def _store(monkeypatch, rows):
    saves = []
    monkeypatch.setattr(locations_db, "load_locations_list", lambda: rows)
    monkeypatch.setattr(locations_db, "save_locations_list", lambda lst: saves.append(lst) or True)
    return saves


def test_single_slot_attach_replaces_a_malformed_extra(monkeypatch):
    """locations_db.attach_single_slot_box_to_toolhead — `dict("some string")`
    raised ValueError, so the attach failed (its caller catches it)."""
    rows = [_bad("PM-DB-2", max_spools="1")]
    saves = _store(monkeypatch, rows)
    ok, detail = locations_db.attach_single_slot_box_to_toolhead("PM-DB-2", "XL-2")
    assert ok is True, detail
    assert saves and saves[-1][0]["extra"] == {"slot_targets": {"1": "XL-2"}}


def test_single_slot_attach_replaces_a_malformed_slot_targets(monkeypatch):
    rows = [{"LocationID": "PM-DB-2", "Type": BOX, "Max Spools": "1",
             "extra": {"slot_targets": ["1", "XL-9"], "slot_order": "rtl"}}]
    saves = _store(monkeypatch, rows)
    ok, _ = locations_db.attach_single_slot_box_to_toolhead("PM-DB-2", "XL-2")
    assert ok is True
    assert saves[-1][0]["extra"] == {"slot_targets": {"1": "XL-2"}, "slot_order": "rtl"}, \
        "the sibling slot_order must survive; only the malformed slot_targets is replaced"


def test_single_slot_detach_is_untroubled_by_a_bad_row(monkeypatch):
    """locations_db.detach_single_slot_box (Group 42.1's spool-keyed release; the
    toolhead-keyed helper this pinned is gone): a bad box elsewhere neither
    stops the release nor is rewritten, and a bad box itself is a no-op."""
    rows = [_bad("PM-DB-1", max_spools="1"), _good("PM-DB-2", {"1": "XL-2"}, max_spools="1")]
    saves = _store(monkeypatch, rows)
    assert locations_db.detach_single_slot_box("PM-DB-2", "XL-2") is True
    assert saves[-1][1]["extra"]["slot_targets"] == {}
    assert saves[-1][0]["extra"] == POISON, "a reader-side skip must not rewrite the bad row"
    assert locations_db.detach_single_slot_box("PM-DB-1", "XL-2") is False


PRINTER_MAP = {"XL-1": {"printer_name": "XL", "position": 0},
               "XL-2": {"printer_name": "XL", "position": 1}}
TOOLHEADS = [{"LocationID": "XL-1", "Type": "Tool Head", "Max Spools": "1"},
             {"LocationID": "XL-2", "Type": "Tool Head", "Max Spools": "1"}]


def test_feeds_save_survives_another_malformed_box(monkeypatch):
    """locations_db._set_dryer_box_bindings_locked, the cross-box duplicate scan:
    the Feeds save answered 500 whenever ANY other box was malformed."""
    rows = [_bad("PM-DB-BAD"), _good("PM-DB-OK", {}), *TOOLHEADS]
    saves = _store(monkeypatch, rows)
    ok, errors, _warnings = locations_db.set_dryer_box_bindings("PM-DB-OK", {"1": "XL-1"}, PRINTER_MAP)
    assert ok is True, errors
    saved = {r["LocationID"]: r for r in saves[-1]}
    assert saved["PM-DB-OK"]["extra"]["slot_targets"] == {"1": "XL-1"}


def test_feeds_save_still_warns_about_a_toolhead_bound_by_another_box(monkeypatch):
    rows = [_bad("PM-DB-BAD"), _good("PM-DB-OTHER", {"2": "XL-1"}), _good("PM-DB-OK", {}), *TOOLHEADS]
    _store(monkeypatch, rows)
    ok, errors, warnings = locations_db.set_dryer_box_bindings("PM-DB-OK", {"1": "XL-1"}, PRINTER_MAP)
    assert ok is True, errors
    assert any("PM-DB-OTHER" in w[2] for w in warnings), warnings


def test_feeds_save_onto_the_malformed_box_itself(monkeypatch):
    """...and the box being saved: `dict("some string")` raised ValueError."""
    rows = [_bad("PM-DB-BAD"), *TOOLHEADS]
    saves = _store(monkeypatch, rows)
    ok, errors, _ = locations_db.set_dryer_box_bindings("PM-DB-BAD", {"1": "XL-2"}, PRINTER_MAP)
    assert ok is True, errors
    saved = {r["LocationID"]: r for r in saves[-1]}
    assert saved["PM-DB-BAD"]["extra"] == {"slot_targets": {"1": "XL-2"}}


def test_toolhead_delete_cascade_survives_a_bad_row(monkeypatch):
    """logic.perform_toolhead_delete_cascade guarded `slot_targets` but not
    `extra`."""
    rows = [_bad("PM-DB-BAD"), _good("PM-DB-OK", {"1": "XL-2", "2": "XL-1"}), *TOOLHEADS]
    monkeypatch.setattr(locations_db, "get_active_printer_map", lambda *a, **k: dict(PRINTER_MAP))
    monkeypatch.setattr(spoolman_api, "get_spools_at_location_detailed", lambda loc: [])
    summary = logic.perform_toolhead_delete_cascade("XL-2", rows, confirm_active_print=True)
    assert summary["status"] == "ok", summary
    assert summary["slot_bindings_cleared"] == ["PM-DB-OK:1"], summary
    assert rows[1]["extra"]["slot_targets"] == {"2": "XL-1"}
    assert rows[0]["extra"] == POISON


# --------------------------------------------------------------------------- #
# Source canary: no direct slot_targets read creeps back                      #
# --------------------------------------------------------------------------- #

HERE = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_DIRECT_READ = re.compile(r"""\.get\(\s*['"]extra['"]\s*\)\s*or\s*\{\}\s*\)\s*\.get\(\s*['"]slot_targets['"]""")


@pytest.mark.parametrize("module", ["logic.py", "routes_bindings.py", "locations_db.py", "placement.py"])
def test_no_unguarded_slot_targets_read_remains(module):
    """`(row.get('extra') or {}).get('slot_targets')` raises on a non-dict
    `extra` — read through locations_db.bindings_from_row instead (or guard the
    `extra` with isinstance when you must write it back)."""
    with open(os.path.join(HERE, module), encoding="utf-8") as f:
        offenders = [n for n, line in enumerate(f, 1) if _DIRECT_READ.search(line)]
    assert not offenders, f"{module}: unguarded slot_targets read(s) on line(s) {offenders}"
