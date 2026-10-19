"""Group 40.0d, frontend half: a toolhead scan's toast names the feed slot the
engine recorded as the spool's home. The choice is silent on purpose (a prompt
on every toolhead-QR scan would slow Derek's main path), so the toast is where
it becomes visible: "#42 → XL-1 (recorded as from LR-MDB-1 slot 1)". Runs the
real inv_cmd.js under node's `vm` (test_core1_return_ejectall_js.py's harness).
"""
from __future__ import annotations

import json

import pytest

from test_core1_return_ejectall_js import pytestmark, run_js  # noqa: F401  (pytestmark: skip without node)

ASSIGN = """
state.heldSpools = [{ id: 42, display: '#42' }, { id: 43, display: '#43' }];
const answer = __ANSWER__;
window.__respond = (url) => (url === '/api/smart_move' ? { body: answer } : { body: {} });
performContextAssign('XL-1', null, [], __IDS__);
await __settle(60);
return { toasts: __rec.toasts, buffer: state.heldSpools.map(s => s.id) };
"""


def _assign(tmp_path, answer, ids):
    res = run_js(tmp_path, ["inv_cmd.js"], ASSIGN.replace("__ANSWER__", json.dumps(answer))
                 .replace("__IDS__", json.dumps(ids)))
    assert res["unhandled"] == [], res
    return res


def test_the_toast_names_the_recorded_feed_slot(tmp_path):
    res = _assign(tmp_path, {"status": "success", "failures": {}, "recorded_source": "LR-MDB-1:1"}, [42])
    assert [(t["msg"], t["type"]) for t in res["toasts"]] == [
        ("#42 → XL-1 (recorded as from LR-MDB-1 slot 1)", "success")], res
    assert res["buffer"] == [43]


@pytest.mark.parametrize("answer, ids, toast", [
    ({"status": "success", "failures": {}}, [42], "Assigned 1 item!"),
    ({"status": "success", "failures": {}}, [42, 43], "Assigned 2 items!"),
], ids=["nothing-recorded", "several-spools"])
def test_without_a_recorded_slot_the_toast_is_unchanged(tmp_path, answer, ids, toast):
    """Control (passes before the change too)."""
    res = _assign(tmp_path, answer, ids)
    assert [(t["msg"], t["type"]) for t in res["toasts"]] == [(toast, "success")], res
