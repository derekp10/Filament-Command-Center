"""Group 64.4: the "↻ Try again now" button on the Activity Log line FCC writes the
first time a queued print's file downloads but can't be read, or its deduct fails,
hermetic.

The line holds the button itself (print_deduct._fetch_retry_button:
`.fcc-fetch-retry-btn`, `data-fetch-printer`, `data-fetch-job`), so #live-logs and
the 📡 pill's list both have it; one delegated click (window.fccFetchRetryClick,
cancel_review.js) posts /api/cancel_deduct/retry_fetch {printer_name, job_id} and
toasts the answer's words, also on the pill list's own line, whose overlay covers
the toast layer. A second press while one is out for that print, and the second
click of a double click, ask nothing.

Every test is RED on d16b858 (the button and its click are new).
Harness: node's `vm` (test_core1_return_ejectall_js.run_js).
"""
from __future__ import annotations

import json

import pytest

from test_core1_return_ejectall_js import NODE, NODE_MISSING_MSG, run_js

needs_node = pytest.mark.skipif(NODE is None, reason=NODE_MISSING_MSG)

PRESS = """
const ANSWER = __ANSWER__;
const WHERE = __WHERE__;
const ATTRS = __ATTRS__;
const notices = [];
window.logPillNotice = (m) => notices.push(m);
window.__respond = (url) => (url === '/api/cancel_deduct/retry_fetch' ? { body: ANSWER } : { body: {} });
const container = { id: WHERE.slice(1) };
const btn = {
  getAttribute: (k) => (k in ATTRS ? ATTRS[k] : null),
  closest: (sel) => {
    if (sel === '.fcc-fetch-retry-btn') return btn;
    if (sel === '#live-logs, #fcc-log-pill-overlay') return WHERE ? container : null;
    if (sel === '#fcc-log-pill-overlay') return WHERE === '#fcc-log-pill-overlay' ? container : null;
    return null;
  },
};
const press = (detail) => window.fccFetchRetryClick({ target: btn, detail, preventDefault() {} });
for (const d of __PRESSES__) press(d);
await __settle(80);
return { toasts: __rec.toasts, notices,
         posts: __rec.fetches.filter((f) => f.method === 'POST').map((f) => [f.url, f.body]) };
"""

ATTRS = {"data-fetch-printer": "INDX", "data-fetch-job": "1141"}


def _press(tmp_path, answer, where="#live-logs", presses=(1,), attrs=None):
    scen = (PRESS.replace("__ANSWER__", json.dumps(answer)).replace("__WHERE__", json.dumps(where))
            .replace("__PRESSES__", json.dumps(list(presses)))
            .replace("__ATTRS__", json.dumps(attrs if attrs is not None else ATTRS)))
    res = run_js(tmp_path, ["cancel_review.js"], scen)
    assert res["unhandled"] == [], res
    return res


@needs_node
def test_a_press_asks_fcc_to_try_again_and_says_so(tmp_path):
    msg = "FCC tries job 1141 on INDX again as soon as the printer is idle."
    res = _press(tmp_path, {"success": True, "msg": msg})
    assert res["posts"] == [["/api/cancel_deduct/retry_fetch",
                             {"printer_name": "INDX", "job_id": "1141"}]], res
    assert [(t["msg"], t["type"], t["duration"]) for t in res["toasts"]] == [(msg, "success", 4000)], res
    assert res["notices"] == [], res


@needs_node
def test_a_print_fcc_has_finished_with_warns_for_7_s(tmp_path):
    msg = "Nothing is waiting for job 1141 on INDX any more: FCC has finished with it."
    res = _press(tmp_path, {"success": False, "msg": msg})
    assert [(t["msg"], t["type"], t["duration"]) for t in res["toasts"]] == [(msg, "warning", 7000)], res


@needs_node
def test_from_the_pill_list_the_words_are_on_its_own_line_too(tmp_path):
    msg = "FCC tries job 1141 on INDX again as soon as the printer is idle."
    res = _press(tmp_path, {"success": True, "msg": msg}, where="#fcc-log-pill-overlay")
    assert res["notices"] == ["", msg], res


@needs_node
@pytest.mark.parametrize("presses", [(1, 1), (1, 2)], ids=["second-press-while-out", "double-click"])
def test_a_second_press_asks_nothing(tmp_path, presses):
    res = _press(tmp_path, {"success": True, "msg": "ok"}, presses=presses)
    assert len(res["posts"]) == 1, res


@needs_node
def test_a_button_outside_the_log_or_naming_no_print_asks_nothing(tmp_path):
    assert _press(tmp_path, {"success": True, "msg": "ok"}, where="")["posts"] == []
    assert _press(tmp_path, {"success": True, "msg": "ok"},
                  attrs={"data-fetch-printer": "INDX"})["posts"] == []
