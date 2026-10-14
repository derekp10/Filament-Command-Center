"""Group 42, frontend half: hermetic checks of the real modules under node's
`vm` (the harness of test_core1_return_ejectall_js.py).

42.5a: the eject toast says where the spool went and which single-slot box let
go of the head, in Derek's short arrow form (2026-10-13: "short arrows for
toast. And a full sentence in the activity log"). It used to say "Ejected".
"""
from __future__ import annotations

import json

import pytest

from test_core1_return_ejectall_js import pytestmark, run_js  # noqa: F401  (pytestmark: skip without node)

EJECT = """
state.allLocations = [
  { LocationID: 'PM-DB-2', Type: 'Dryer Box' },
  { LocationID: 'LR-MDB-1', Type: 'Dryer Box' },
  { LocationID: 'CR-CT-2-R1', Type: 'Cart Row' },
];
const answer = __ANSWER__;
window.__respond = (url) => (url === '/api/manage_contents' ? { body: answer } : { body: [] });
globalThis.fetchLocations = () => {};
window.doEject(__SID__, 'Scan');
await __settle(60);
return { toasts: __rec.toasts };
"""


def _ok(**kw):
    return {"success": True, "slot": "", "released_boxes": [], **kw}


@pytest.mark.parametrize("sid, answer, text", [
    (50, _ok(spool_id=50, **{"from": "XL-2"}, to="PM-DB-2", home=True, released_boxes=["PM-DB-2"]),
     "⏏️ #50 → back in PM-DB-2 (PM-DB-2 detached from XL-2)"),
    (134, _ok(spool_id=134, **{"from": "XL-3"}, to="LR-MDB-1", slot="3", home=True),
     "⏏️ #134 → back in LR-MDB-1 slot 3"),
    (50, _ok(spool_id=50, **{"from": "PM-DB-2"}, to="CR-CT-2-R1", home=True),
     "⏏️ #50 → back on CR-CT-2-R1"),
    (88, _ok(spool_id=88, **{"from": "CR-CT-2-R1"}, to="", home=False),
     "⏏️ #88 → Unassigned"),
    (60, _ok(spool_id=60, **{"from": "RCOI-1"}, to="CR", home=False),
     "⏏️ #60 → Room CR"),
    (7, {"success": True}, "Ejected"),   # an answer with no report (an older server)
], ids=["own-box-released", "box-slot", "cart-row", "unassigned", "room", "no-report"])
def test_the_eject_toast_says_where_it_went(tmp_path, sid, answer, text):
    res = run_js(tmp_path, ["inv_loc_mgr.js"],
                 EJECT.replace("__ANSWER__", json.dumps(answer)).replace("__SID__", str(sid)))
    assert res["unhandled"] == [], res
    assert [(t["msg"], t["type"], t["duration"]) for t in res["toasts"]] == [(text, "success", 4000)], res
