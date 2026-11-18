"""Group 63.8: the post-archive empty-weight prompt waits for a pause, hermetic.

"📦 Spool archived — record the empty weight?" (window.showArchiveEmptyWeightPrompt,
inv_details.js) opened about half a second after the save that archived a spool and
took the focus: a person already typing the next row's reading in the weigh-out list
typed it into the prompt instead, and Enter saved it as the filament's empty weight,
which every later spool of it inherits. Now (Claude's call, no veto 2026-11-18; still
Derek's "one pre-filled confirm", only its moment moves):
  - the weigh-out list hands it `waitWhile`: true while the list's focused box
    holds a reading or the missing-tare question is up over it; the prompt opens
    once that is false (checked every 250 ms), at once when nothing is typed;
  - prompts open one at a time, in the order their archives came, and one whose
    filament a prompt before it recorded is not asked again;
  - the refill question (Group 63.1) waits the same way in the list.

Every test marked RED fails on e1b22f4. Harness: node's `vm`
(test_core1_return_ejectall_js.run_js).
"""
from __future__ import annotations

import pytest

from test_core1_return_ejectall_js import NODE, NODE_MISSING_MSG, run_js

needs_node = pytest.mark.skipif(NODE is None, reason=NODE_MISSING_MSG)

PRELUDE = r"""
window.fetchT = (u, o) => window.fetch(u, o);
const FILAMENTS = { 7: { id: 7, name: 'Blue', material: 'PLA', spool_weight: null, vendor: { id: 3, name: 'Brand' } },
                    8: { id: 8, name: 'Red', material: 'PLA', spool_weight: null, vendor: { id: 3, name: 'Brand' } } };
window.__respond = (url, method, body) => {
    const m = /filament_details\?id=(\d+)/.exec(String(url));
    if (m) return { body: JSON.parse(JSON.stringify(FILAMENTS[m[1]])) };
    if (url === '/api/update_filament') { FILAMENTS[body.id].spool_weight = body.data.spool_weight; return { body: { success: true } }; }
    return { body: {} };
};
const mounted = () => __rec.overlays.filter((o) => o.id === 'fcc-archive-empty-overlay' && !o.closed).length;
const opened = () => __rec.overlays.filter((o) => o.id === 'fcc-archive-empty-overlay').length;
"""


def _run(tmp_path, modules, body):
    res = run_js(tmp_path, modules, PRELUDE + body)
    assert res["unhandled"] == [], res
    return res


@needs_node
def test_the_prompt_waits_while_a_reading_is_being_typed(tmp_path):
    """RED: it opened at once, whatever was being typed."""
    res = _run(tmp_path, ["inv_details.js"], r"""
let typing = true;
window.showArchiveEmptyWeightPrompt(99, 7, null, { waitWhile: () => typing });
await __settle(700);
const whileTyping = opened();
typing = false;
await __settle(400);
return { whileTyping, after: opened() };
""")
    assert res["whileTyping"] == 0 and res["after"] == 1, res


@needs_node
def test_control_with_nothing_typed_it_opens_at_once(tmp_path):
    res = _run(tmp_path, ["inv_details.js"], r"""
window.showArchiveEmptyWeightPrompt(99, 7, null, { waitWhile: () => false });
await __settle(100);
return { opened: opened() };
""")
    assert res["opened"] == 1, res


@needs_node
def test_prompts_open_one_at_a_time_in_order(tmp_path):
    """RED: the second replaced the first (one overlay id), and the first spool's
    prompt was lost."""
    res = _run(tmp_path, ["inv_details.js"], r"""
window.showArchiveEmptyWeightPrompt(99, 7);
window.showArchiveEmptyWeightPrompt(98, 8);
await __settle(150);
const first = { opened: opened(), html: __rec.overlays[0] && __rec.overlays[0].content };
document.querySelector('#fcc-archive-later');   // stub element per selector
__overlayEls[0].querySelector('#fcc-archive-later').onclick();
await __settle(150);
return { first, opened: opened(), second: __rec.overlays[1] && __rec.overlays[1].content };
""")
    assert res["first"]["opened"] == 1 and "#99" in res["first"]["html"], res
    assert res["opened"] == 2 and "#98" in res["second"], res


@needs_node
def test_a_filament_a_prompt_before_it_recorded_is_not_asked_again(tmp_path):
    """RED: both prompts asked for filament #7's empty weight."""
    res = _run(tmp_path, ["inv_details.js"], r"""
window.showArchiveEmptyWeightPrompt(99, 7);
window.showArchiveEmptyWeightPrompt(98, 7);
await __settle(150);
const ov = __overlayEls[0];
ov.querySelector('#fcc-archive-empty-wt').value = '168';
await ov.querySelector('#fcc-archive-save').onclick();
await __settle(200);
return { opened: opened() };
""")
    assert res["opened"] == 1, res


# ---- the weigh-out list says when a reading is being typed ------------------------------------------

LIST = r"""
// The stub DOM finds an element for any id; a page has no missing-tare question up here.
const __get = document.getElementById.bind(document);
document.getElementById = (id) => (id === 'fcc-missing-empty-weight-overlay' ? null : __get(id));
const modal = document.getElementById('weighOutModal');
modal.classList.add('show');
const box = document.createElement('input');
box.classList.add('weigh-input');
box.value = __TYPED__;
document.activeElement = box;
let got = null;
window.showArchiveEmptyWeightPrompt = (sid, fid, pre, o) => { got = o; };
const asked = [];
window.askRefillPlace = (sid, ask) => asked.push(sid);
window.__respond = (url) => (url === '/api/spool/update'
    ? { body: { status: 'success', auto_archived: true, needs_empty_weight_prompt: true, filament_id: 7,
                location_now: '', refill_ask: __REFILL__ } }
    : { body: {} });
window.saveSpoolWeight(57, null, { used_weight: 1000 }, true, null, { archiveSwitch: true, empties: true, wasArchived: false });
await __settle(600);
const waiting = { prompt: got && typeof got.waitWhile === 'function' ? got.waitWhile() : 'none', asked: asked.slice() };
box.value = '';
await __settle(400);
return { waiting, prompt: got && typeof got.waitWhile === 'function' ? got.waitWhile() : 'none', asked };
"""


@needs_node
def test_the_list_holds_the_prompt_while_its_box_holds_a_reading(tmp_path):
    """RED: the list handed the prompt no `waitWhile`."""
    res = _run(tmp_path, ["inv_weigh_out.js"], LIST.replace("__TYPED__", "'42'").replace("__REFILL__", "null"))
    assert res["waiting"]["prompt"] is True and res["prompt"] is False, res


@needs_node
def test_the_refill_question_waits_for_the_typing_too(tmp_path):
    """RED (the question is new): it opens once the box is empty again."""
    res = _run(tmp_path, ["inv_weigh_out.js"], LIST.replace("__TYPED__", "'42'").replace(
        "__REFILL__", "{ place: 'HEAD-1', room: '', held_by: [] }"))
    assert res["waiting"]["asked"] == [] and res["asked"] == [57], res
