"""Group 40, Swap option C — the browser half, under node's `vm` (no browser, no
container). The Location Manager grid's Swap and the slot picker's Swap send
`swap: true`; the server files the slot's old spool back where it sat before
the slot and names it in `to_buffer`, which is what puts it in this page's
buffer (the page used to push the spool itself while the server left it in the
box with no slot). The toast says where it was filed: "✋ #77 → your buffer
(filed back in CR-CT-2-R1)".

HEAD proof (0b0eeb7): see the commit message.
"""
from __future__ import annotations

import json

from test_core1_return_ejectall_js import pytestmark, run_js  # noqa: F401  (pytestmark: skip without node)
from test_head_load_confirm_js import FED, LM, PRELUDE, SCAN

OLD = {"id": 77, "display": "#77 Old", "color": "888888", "off_head": "", "filed_to": "CR-CT-2-R1"}
SWAPPED = {"status": "success", "failures": {}, "to_buffer": [OLD]}
DONE = {"status": "success", "failures": {}}
DISPLACED = "{ swapDisplaced: { id: 77, display: '#77 Old', color: '888888' } }"


def _run(tmp_path, modules, body):
    res = run_js(tmp_path, modules, PRELUDE + body)
    assert res["unhandled"] == [], res["unhandled"]
    return res


def _js(value):
    return json.dumps(value)


def test_the_grids_swap_sends_swap_and_buffers_what_the_server_names(tmp_path):
    res = _run(tmp_path, LM, f"""
answerWith('/api/manage_contents', [{_js(SWAPPED)}]);
window.doAssign('LR-MDB-1', 57, 4, true, {DISPLACED});
await __settle(200);
return {{ posts: posts('/api/manage_contents'), held: state.heldSpools.map(s => s.id), toasts: toasts() }};
""")
    [post] = res["posts"]
    assert post["swap"] is True and post["slot"] == 4 and post["spool_id"] == "ID:57", post
    assert res["held"] == [77], res
    assert any(t["msg"] == "✋ #77 → your buffer (filed back in CR-CT-2-R1)" for t in res["toasts"]), res["toasts"]


def test_the_grids_swap_buffers_nothing_the_server_did_not_swap_out(tmp_path):
    """The page no longer pushes the old spool itself: a Swap whose slot was
    emptied meanwhile (no `to_buffer`) adds nothing."""
    res = _run(tmp_path, LM, f"""
answerWith('/api/manage_contents', [{_js(DONE)}]);
window.doAssign('LR-MDB-1', 57, 4, true, {DISPLACED});
await __settle(200);
return {{ held: state.heldSpools.map(s => s.id) }};
""")
    assert res["held"] == [], res


def test_overwrite_sends_no_swap(tmp_path):
    res = _run(tmp_path, LM, f"""
answerWith('/api/manage_contents', [{_js(DONE)}]);
window.doAssign('LR-MDB-1', 57, 4, true);
await __settle(200);
return {{ posts: posts('/api/manage_contents') }};
""")
    assert "swap" not in res["posts"][0], res["posts"]


def test_a_failed_assign_still_takes_a_spool_the_move_already_buffered(tmp_path):
    """The old spool was swapped out before the incoming spool's write was
    rejected: it is in the user's hand, so it joins the buffer, and #57 stays."""
    failed = dict(SWAPPED, failures={"57": "400: rejected"})
    res = _run(tmp_path, LM, f"""
answerWith('/api/manage_contents', [{_js(failed)}]);
window.doAssign('LR-MDB-1', 57, 4, true, {DISPLACED});
await __settle(200);
return {{ held: state.heldSpools.map(s => s.id), toasts: toasts() }};
""")
    assert res["held"] == [57, 77], res
    assert any("#57 was NOT assigned to LR-MDB-1" in t["msg"] for t in res["toasts"]), res["toasts"]


def test_a_replay_of_the_grids_swap_is_still_a_swap(tmp_path):
    res = _run(tmp_path, LM, f"""
answerWith('/api/manage_contents', [{_js(FED)}, {_js(SWAPPED)}]);
window.doAssign('LR-MDB-1', 57, 1, true, {DISPLACED});
await __settle(200);
await click('.fcc-apc-yes');
await __settle(200);
return {{ posts: posts('/api/manage_contents'), held: state.heldSpools.map(s => s.id) }};
""")
    first, replay = res["posts"]
    assert first["swap"] is True and replay["swap"] is True, res["posts"]
    assert replay["confirmed_fed_heads"] == ["XL-1#99"], replay
    assert res["held"] == [77], res


def test_the_pickers_swap_sends_swap_through_smart_move(tmp_path):
    res = _run(tmp_path, SCAN, f"""
answerWith('/api/smart_move', [{_js(SWAPPED)}]);
performContextAssign('LR-MDB-1', '4', [], [57], null, {DISPLACED});
await __settle(200);
return {{ posts: posts('/api/smart_move'), held: state.heldSpools.map(s => s.id), toasts: toasts() }};
""")
    [post] = res["posts"]
    assert post["swap"] is True and post["slot"] == "4" and post["spools"] == [57], post
    assert res["held"] == [77], res
    assert any(t["msg"] == "✋ #77 → your buffer (filed back in CR-CT-2-R1)" for t in res["toasts"]), res["toasts"]


def test_an_error_answer_with_a_buffered_spool_still_takes_it(tmp_path):
    """Smart Load took a head's spool into the buffer, then couldn't empty the
    head (an error answer that carries `to_buffer`)."""
    stuck = {"status": "error", "msg": "Not loaded: XL-1 still holds #98", "failures": {"57": "x"},
             "to_buffer": [dict(OLD, off_head="XL-1", filed_to="")]}
    res = _run(tmp_path, SCAN, f"""
answerWith('/api/smart_move', [{_js(stuck)}]);
performContextAssign('XL-1', null, [], [57]);
await __settle(200);
return {{ held: state.heldSpools.map(s => s.id), toasts: toasts() }};
""")
    assert res["held"] == [57, 77], res
    assert any(t["msg"] == "✋ #77 → your buffer (taken off XL-1)" for t in res["toasts"]), res["toasts"]


def test_the_toast_names_both_the_head_and_where_it_was_filed(tmp_path):
    res = _run(tmp_path, SCAN, """
window.toastIntoBuffer([{ id: 99, off_head: 'XL-3', filed_to: 'LR-MDB-2 slot 1' }, { id: 98, filed_to: '' }]);
return { toasts: toasts().map(t => t.msg) };
""")
    assert res["toasts"] == ["✋ #99 → your buffer (taken off XL-3; filed back in LR-MDB-2 slot 1)",
                             "✋ #98 → your buffer"], res
