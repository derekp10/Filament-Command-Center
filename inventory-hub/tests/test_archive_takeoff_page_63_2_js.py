"""Group 63.2: the "Take it off" button on the Activity Log line that lists a spool a
weigh archived at its place and FCC couldn't take off, hermetic.

The line holds the button itself (archive_takeoff._button: `.fcc-takeoff-btn`,
`data-takeoff-spool`), so #live-logs and the 📡 pill's list both have it; one
delegated click (window.fccArchiveTakeoffClick, inv_weigh_out.js) posts
/api/spool/archive_takeoff {id} and toasts the answer's words, also on the pill
list's own line, whose overlay covers the toast layer. A second press while one
is out for that spool, and the second click of a double click, ask nothing.

Every test is RED on e1b22f4 (the button and its click are new).
Harness: node's `vm` (test_core1_return_ejectall_js.run_js).
"""
from __future__ import annotations

import json

import pytest

from test_core1_return_ejectall_js import NODE, NODE_MISSING_MSG, run_js

needs_node = pytest.mark.skipif(NODE is None, reason=NODE_MISSING_MSG)

# A button inside `where` ('#live-logs' or '#fcc-log-pill-overlay'), pressed
# `presses` times (each {detail}), the route answering ANSWER after `delay` ms.
PRESS = """
const ANSWER = __ANSWER__;
const WHERE = __WHERE__;
const notices = [];
window.logPillNotice = (m) => notices.push(m);
let release = null;
window.__respond = (url) => (url === '/api/spool/archive_takeoff' ? { body: ANSWER } : { body: {} });
const container = { id: WHERE.slice(1) };
const btn = {
  getAttribute: (k) => (k === 'data-takeoff-spool' ? __SID__ : null),
  closest: (sel) => {
    if (sel === '.fcc-takeoff-btn') return btn;
    if (sel === '#live-logs, #fcc-log-pill-overlay') return container;
    if (sel === '#fcc-log-pill-overlay') return WHERE === '#fcc-log-pill-overlay' ? container : null;
    return null;
  },
};
const press = (detail) => window.fccArchiveTakeoffClick({ target: btn, detail, preventDefault() {} });
for (const d of __PRESSES__) press(d);
await __settle(80);
return { toasts: __rec.toasts, notices,
         posts: __rec.fetches.filter((f) => f.method === 'POST').map((f) => [f.url, f.body]) };
"""


def _press(tmp_path, answer, where="#live-logs", presses=(1,), sid="'57'"):
    scen = (PRESS.replace("__ANSWER__", json.dumps(answer)).replace("__WHERE__", json.dumps(where))
            .replace("__PRESSES__", json.dumps(list(presses))).replace("__SID__", sid))
    res = run_js(tmp_path, ["inv_weigh_out.js"], scen)
    assert res["unhandled"] == [], res
    return res


@needs_node
def test_a_press_takes_it_off_and_says_so(tmp_path):
    res = _press(tmp_path, {"success": True, "msg": "Took #57 off XL-1: it is Unassigned now."})
    assert res["posts"] == [["/api/spool/archive_takeoff", {"id": 57}]], res
    assert [(t["msg"], t["type"], t["duration"]) for t in res["toasts"]] == [
        ("Took #57 off XL-1: it is Unassigned now.", "success", 4000)], res
    assert res["notices"] == [], res


@needs_node
def test_a_press_that_still_cant_warns_for_7_s(tmp_path):
    msg = "Couldn't take #57 off XL-1: Spoolman refused it: database is locked FCC keeps trying."
    res = _press(tmp_path, {"success": False, "msg": msg})
    assert [(t["msg"], t["type"], t["duration"]) for t in res["toasts"]] == [(msg, "warning", 7000)], res


@needs_node
def test_from_the_pill_list_the_words_are_on_its_own_line_too(tmp_path):
    res = _press(tmp_path, {"success": True, "msg": "Took #57 off XL-1: it is Unassigned now."},
                 where="#fcc-log-pill-overlay")
    assert res["notices"] == ["", "Took #57 off XL-1: it is Unassigned now."], res


@needs_node
@pytest.mark.parametrize("presses", [(1, 1), (1, 2)], ids=["second-press-while-out", "double-click"])
def test_a_second_press_asks_nothing(tmp_path, presses):
    res = _press(tmp_path, {"success": True, "msg": "ok"}, presses=presses)
    assert len(res["posts"]) == 1, res


@needs_node
def test_a_button_with_no_spool_asks_nothing(tmp_path):
    res = _press(tmp_path, {"success": True, "msg": "ok"}, sid="'x'")
    assert res["posts"] == [], res
