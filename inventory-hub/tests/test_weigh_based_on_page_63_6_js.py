"""Group 63.6, the page half: a weigh save sends what its preview was worked out
from, and a refusal redraws the row from the fresh figures, hermetic.

The weigh-out list's row save (window.saveWeighOutRow) and the Quick-Weigh
(window.openQuickWeigh's onSubmit) hand saveSpoolWeight `basedOn` {mode, capacity,
used}: the figures the reading was worked out from, sent as `based_on`. When the
server answers `details_changed` (test_weigh_based_on_63_6), the row's cached
figures become the fresh ones, its preview is drawn again, its reading stays in
its box, a 7 s warning says so, and the next Enter saves against the new figures.

PIN UPDATED DELIBERATELY (Group 63 review, C3): each save says which screen sent it
(`screen`: 'list' or 'quick'), so the server's refusal line says what to do there.
Every test is RED on e1b22f4 (no `based_on` was sent, and a `details_changed`
answer read as a refusal). Harness: node's `vm` (test_core1_return_ejectall_js.run_js)
with inv_core.js, weight_utils.js and inv_weigh_out.js loaded.
"""
from __future__ import annotations

import json

import pytest

from test_core1_return_ejectall_js import NODE, NODE_MISSING_MSG, run_js

needs_node = pytest.mark.skipif(NODE is None, reason=NODE_MISSING_MSG)

MODULES = ["inv_core.js", "weight_utils.js", "inv_weigh_out.js"]

PRELUDE = r"""
window.fetchT = (u, o) => window.fetch(u, o);
window.weighOutMode = 'net';
const DETAILS = { id: 57, initial_weight: 1000, used_weight: 700, archived: false, spool_weight: 200,
                  filament: { weight: 1000, spool_weight: 200, name: 'Blue', material: 'PLA',
                              vendor: { name: 'Brand' } } };
let answer = { status: 'success', auto_archived: false, needs_empty_weight_prompt: false, location_now: 'SHELF-1' };
window.__respond = (url) => {
    if (String(url).startsWith('/api/spool_details')) return { body: DETAILS };
    if (url === '/api/spool/update') return { body: answer };
    return { body: {} };
};
const updates = () => __rec.fetches.filter((f) => f.url === '/api/spool/update').map((f) => f.body);
const box = document.querySelector('#weigh-out-list .weigh-input[data-id="57"]:not(:disabled)');
const plainBox = document.querySelector('.weigh-input[data-id="57"]');
const preview = document.querySelector('.weigh-row-preview[data-id="57"]');
// inv_core.js's own showToast (a top-level const) draws into the stub's toast container.
const toasts = () => (document.getElementById('toast-container').children || [])
  .map((c) => [c.innerText, String(c.className).replace('toast-msg toast-', '')]);
const typeIn = (v) => { box.value = v; plainBox.value = v; box.dataset.id = '57'; plainBox.dataset.id = '57'; };
"""


def _run(tmp_path, body):
    res = run_js(tmp_path, MODULES, PRELUDE + body)
    assert res["unhandled"] == [], res
    return res


@needs_node
def test_a_row_save_sends_what_its_preview_was_worked_out_from(tmp_path):
    res = _run(tmp_path, """
typeIn('250');
await window.saveWeighOutRow('57');
await __settle(80);
return { updates: updates() };
""")
    (body,) = res["updates"]
    assert body["updates"] == {"used_weight": 750} and body["based_on"] == {"mode": "net", "capacity": 1000, "used": 700, "screen": "list"}, body


@needs_node
def test_a_refused_save_redraws_the_row_keeps_the_reading_and_the_next_enter_saves(tmp_path):
    res = _run(tmp_path, """
typeIn('250');
answer = { status: 'details_changed', changed: 'capacity',
           msg: "#57's weight changed since this was read: check its preview and press Enter again",
           fresh: { initial: 1200, used: 700, archived: false } };
await window.saveWeighOutRow('57');
await __settle(80);
const afterRefusal = { preview: preview.innerHTML, value: plainBox.value, disabled: plainBox.disabled,
                       toasts: toasts() };
answer = { status: 'success', auto_archived: false, needs_empty_weight_prompt: false, location_now: 'SHELF-1' };
await window.saveWeighOutRow('57');
await __settle(80);
return { afterRefusal, updates: updates() };
""")
    after = res["afterRefusal"]
    assert "→ used <strong>950g</strong> · remaining <strong>250g</strong>" in after["preview"], after
    assert after["value"] == "250" and after["disabled"] is False, after
    assert ["#57's weight changed since this was read: check its preview and press Enter again",
            "warning"] in after["toasts"], after
    first, second = res["updates"]
    assert first["based_on"]["capacity"] == 1000 and first["updates"] == {"used_weight": 750}, first
    assert second["based_on"] == {"mode": "net", "capacity": 1200, "used": 700, "screen": "list"}, second
    assert second["updates"] == {"used_weight": 950}, second


@needs_node
def test_the_quick_weigh_sends_the_figures_it_read_when_it_opened(tmp_path):
    res = _run(tmp_path, """
let opened = null;
window.WeightEntry = { openModal: (o) => { opened = o; } };
window.openQuickWeigh(57);
await __settle(60);
opened.onSubmit({ used_weight: 725, mode: 'additive', auto_archive: true, empty_spool_weight: 200 });
await __settle(80);
answer = { status: 'details_changed', changed: 'used', fresh: { initial: 1000, used: 750, archived: false } };
opened.onSubmit({ used_weight: 725, mode: 'additive', auto_archive: true, empty_spool_weight: 200 });
await __settle(80);
return { updates: updates(), toasts: toasts() };
""")
    first = res["updates"][0]
    assert first["based_on"] == {"mode": "additive", "capacity": 1000, "used": 700, "screen": "quick"}, first
    assert ["#57's weight changed since this window read it, so nothing was saved: open it again to weigh it.",
            "warning"] in res["toasts"], res
