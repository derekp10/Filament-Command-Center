"""A slot needs a box: CMD:SLOT:<n> with the Location Manager closed moves nothing.

Found by Group 40's door review (2026-10-14). Closing the Location Manager blanks
#manage-loc-id but keeps state.currentGrid, and handleSlotInteraction had no
open-manager guard (CMD:TRASH and CMD:EJECTALL both do). So a CMD:SLOT:3 scan
with #57 buffered called doAssign('', 57, 3), which posted manage_contents add
with location "", and the engine's generic branch wrote #57 to Unassigned with
container_slot "3" while the toast said "Assigned".

Two guards, each pinned here:
  - the browser ignores a slot scan unless a location is open in the Location
    Manager (a >= 7 s warning and an Activity Log line), like CMD:EJECTALL;
  - manage_contents refuses `add` with a blank location before any read or
    write (unassigning goes through force_unassign).

The browser half runs the REAL inv_cmd.js + inv_loc_mgr.js under node's vm
module (tests/test_core1_return_ejectall_js.run_js), so it needs node on PATH
(CLAUDE.md "Testing"); the server half runs the Flask app with the engine
patched out. HEAD proof (dev 1a1ce18): every refusal test fails there (the
scan POSTs manage_contents add with location "", and the route calls the
engine); the open-manager control passes on HEAD by design.
"""
from __future__ import annotations

import json
import os
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import state  # noqa: E402
from test_core1_return_ejectall_js import NODE, NODE_MISSING_MSG, run_js  # noqa: E402

needs_node = pytest.mark.skipif(NODE is None, reason=NODE_MISSING_MSG)


@pytest.fixture(autouse=True)
def _isolate_state():
    prior = (state.RECENT_LOGS, state.UNDO_STACK, state.GLOBAL_BUFFER)
    state.RECENT_LOGS, state.UNDO_STACK, state.GLOBAL_BUFFER = [], [], []
    try:
        yield
    finally:
        state.RECENT_LOGS, state.UNDO_STACK, state.GLOBAL_BUFFER = prior


# ---- the server: manage_contents add refuses a blank location -------------------

@pytest.mark.parametrize("loc", ["", "   ", None], ids=["blank", "spaces", "null"])
def test_manage_contents_add_with_no_location_moves_nothing(loc):
    import app as app_module
    app_module.app.config["TESTING"] = True
    client = app_module.app.test_client()
    with patch.object(app_module.logic, "perform_smart_move") as engine, \
         patch.object(app_module.logic, "resolve_scan", return_value={"type": "spool", "id": 57}):
        r = client.post("/api/manage_contents", json={
            "action": "add", "location": loc, "spool_id": "ID:57", "slot": "3", "origin": "buffer",
            "confirmed_toolheads": []})
    body = r.get_json()
    assert body["status"] == "error" and body["success"] is False, body
    assert "No location given" in body["msg"], body
    engine.assert_not_called()
    assert any(e.get("type") == "WARNING" and "no location was given" in e.get("msg", "")
               for e in state.RECENT_LOGS), state.RECENT_LOGS


# ---- the browser: a slot scan needs a location open -------------------------------

SLOT_SCAN_SCENARIO = """
window.__respond = (url, method, body) => {
  if (url === '/api/identify_scan') return { body: { type: 'command', cmd: 'slot', value: 3 } };
  if (url === '/api/manage_contents') return { body: { status: 'success', failures: {} } };
  return { body: [] };
};
state.heldSpools = [{ id: 57, display: '#57', color: 'ff0000' }];
state.currentGrid = {};
if (__OPEN__) document.getElementById('manageModal').classList.add('show');
document.getElementById('manage-loc-id').value = __LOC__;
processScan('CMD:SLOT:3', 'barcode');
await __settle(150);
return { toasts: __rec.toasts, logs: __rec.logs, fetches: __rec.fetches, held: state.heldSpools.map(s => s.id) };
"""


def _slot_scan(tmp_path, *, manager_open, loc):
    return run_js(tmp_path, ["inv_cmd.js", "inv_loc_mgr.js"], (SLOT_SCAN_SCENARIO
                                                                .replace("__OPEN__", json.dumps(manager_open))
                                                                .replace("__LOC__", json.dumps(loc))))


def _adds(res):
    return [f["body"] for f in res["fetches"]
            if f["url"] == "/api/manage_contents" and (f.get("body") or {}).get("action") == "add"]


@needs_node
@pytest.mark.parametrize("manager_open,loc", [
    pytest.param(False, "", id="manager-closed"),
    pytest.param(False, "LR-MDB-1", id="manager-closed-stale-id"),
    pytest.param(True, "   ", id="manager-open-blank-id"),
])
def test_a_slot_scan_with_no_location_open_moves_nothing(tmp_path, manager_open, loc):
    res = _slot_scan(tmp_path, manager_open=manager_open, loc=loc)
    assert _adds(res) == [], res["fetches"]
    assert res["held"] == [57], res
    warnings = [t for t in res["toasts"] if t["type"] == "warning" and "Slot 3 scan ignored" in t["msg"]]
    assert len(warnings) == 1 and warnings[0]["duration"] >= 7000, res["toasts"]
    assert [lg["level"] for lg in res["logs"] if "CMD:SLOT:3 ignored" in lg["msg"]] == ["WARNING"], res["logs"]
    assert res["unhandled"] == []


@needs_node
def test_a_slot_scan_with_a_box_open_still_assigns_into_it(tmp_path):
    """Control: LR-MDB-1 open, slot 3 empty, #57 buffered. The tile was drawn
    empty, so the slot goes as `picked_slot` (Group 51 review, engine-3: filled
    only while still free, never an Overwrite)."""
    res = _slot_scan(tmp_path, manager_open=True, loc="LR-MDB-1")
    adds = _adds(res)
    assert len(adds) == 1 and adds[0]["location"] == "LR-MDB-1" and adds[0]["picked_slot"] == "3", res["fetches"]
    assert adds[0].get("slot") in (None, ""), adds[0]
    assert not [t for t in res["toasts"] if "ignored" in t["msg"]], res["toasts"]
    assert res["unhandled"] == []
