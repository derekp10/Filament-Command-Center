"""Group 63.7, 63.9(a) and 63.9(c), hermetic: a tare typed into the missing-tare
question is saved as the spool's own, the weigh-out list offers a new spool its
tare, and the wizard's Scale Gross box no longer counts a missing tare as 0 g.

  63.7: the question says "FCC keeps it as this spool's own empty weight" (54.8's
        rule: a tare the weigh window fills in is the spool's own). The Quick-Weigh
        kept it for its window only and the weigh-out list for its session, so the
        next weigh asked again. Now both send it as the spool's `spool_weight` in
        the same /api/spool/update (no weight key, so no archive edge), and the
        success toast says so.
  63.9(a): the weigh-out list's Gross row on a new spool (0 g used, its net known)
        opens the question filled in with the reading less the net, its sum shown.
  63.9(c): the wizard's inline Scale Gross box (wizardCalcUsedWeight) read a missing
        tare as 0 g, so a gross reading counted the empty spool as filament; with no
        empty weight at any level it now computes nothing and says what's missing.

Every test marked RED fails on e1b22f4. Harness: node's `vm`
(test_core1_return_ejectall_js.run_js).
"""
from __future__ import annotations

import pytest

from test_core1_return_ejectall_js import NODE, NODE_MISSING_MSG, run_js

needs_node = pytest.mark.skipif(NODE is None, reason=NODE_MISSING_MSG)

PRELUDE = r"""
window.fetchT = (u, o) => window.fetch(u, o);
const toasts = () => (document.getElementById('toast-container').children || [])
  .map((c) => [c.innerText, String(c.className).replace('toast-msg toast-', '')]);
const updates = () => __rec.fetches.filter((f) => f.url === '/api/spool/update').map((f) => f.body.updates);
"""
WEIGH = ["inv_core.js", "weight_utils.js", "inv_weigh_out.js"]


def _run(tmp_path, modules, body):
    res = run_js(tmp_path, modules, PRELUDE + body)
    assert res["unhandled"] == [], res
    return res


@needs_node
def test_the_quick_weigh_saves_a_typed_tare_as_the_spools_own(tmp_path):
    """RED: the tare stayed in the window, so the next weigh asked again."""
    res = _run(tmp_path, WEIGH, r"""
window.__respond = (url) => {
    if (String(url).startsWith('/api/spool_details')) return { body: { id: 57, initial_weight: 1000, used_weight: 31,
        filament: { weight: 1000, name: 'Blue', material: 'PLA', vendor: { name: 'Brand' } } } };
    if (url === '/api/spool/update') return { body: { status: 'success', auto_archived: false, location_now: '' } };
    return { body: {} };
};
let opened = null;
window.WeightEntry = { openModal: (o) => { opened = o; } };
window.openQuickWeigh(57);
await __settle(60);
opened.onSubmit({ used_weight: 400, mode: 'gross', auto_archive: true, empty_spool_weight: 167, typed_tare: 167 });
await __settle(80);
return { updates: updates(), toasts: toasts() };
""")
    assert res["updates"] == [{"used_weight": 400, "spool_weight": 167}], res
    assert ["Updated Spool #57: its empty spool weight (167 g) is saved too", "success"] in res["toasts"], res


@needs_node
def test_control_a_tare_from_the_filament_is_not_saved_as_the_spools(tmp_path):
    """Control: a tare the window inherited (no question asked) is not the spool's own."""
    res = _run(tmp_path, WEIGH, r"""
window.__respond = (url) => {
    if (String(url).startsWith('/api/spool_details')) return { body: { id: 57, initial_weight: 1000, used_weight: 31,
        filament: { weight: 1000, spool_weight: 167, name: 'Blue', material: 'PLA', vendor: { name: 'Brand' } } } };
    if (url === '/api/spool/update') return { body: { status: 'success', auto_archived: false, location_now: '' } };
    return { body: {} };
};
let opened = null;
window.WeightEntry = { openModal: (o) => { opened = o; } };
window.openQuickWeigh(57);
await __settle(60);
opened.onSubmit({ used_weight: 400, mode: 'gross', auto_archive: true, empty_spool_weight: 167, typed_tare: null });
await __settle(80);
return { updates: updates() };
""")
    assert res["updates"] == [{"used_weight": 400}], res


# The weigh-out list's Gross row for #57 with no tare known anywhere: its save reads
# its details, asks for the tare (the stub question answers), and saves.
ROW = r"""
window.weighOutMode = 'gross';
const DETAILS = { id: 57, initial_weight: 1000, used_weight: __USED__, archived: false,
                  filament: { weight: 1000, name: 'Blue', material: 'PLA', vendor: { name: 'Brand' } } };
window.__respond = (url) => {
    if (String(url).startsWith('/api/spool_details')) return { body: DETAILS };
    if (url === '/api/spool/update') return { body: { status: 'success', auto_archived: false, location_now: '' } };
    return { body: {} };
};
const asked = [];
window.promptMissingEmptyWeight = (o) => { asked.push({ prefill: o.prefill, offer: o.offer }); return Promise.resolve(__TARE__); };
const box = document.querySelector('#weigh-out-list .weigh-input[data-id="57"]:not(:disabled)');
const plainBox = document.querySelector('.weigh-input[data-id="57"]');
box.value = plainBox.value = '1245';
box.dataset.id = plainBox.dataset.id = '57';
await window.saveWeighOutRow('57');
await __settle(80);
return { asked, updates: updates(), toasts: toasts() };
"""


@needs_node
def test_the_weigh_out_list_offers_a_new_spool_its_tare_and_saves_it_as_its_own(tmp_path):
    """RED: no figure was offered, and the tare stayed in the list's session."""
    res = _run(tmp_path, WEIGH, ROW.replace("__USED__", "0").replace("__TARE__", "245"))
    assert res["asked"] == [{"prefill": 245, "offer":
        "A new spool: 1245 g on the scale − 1000 g of filament = 245 g. Check it, then Save & Continue."}], res
    assert res["updates"] == [{"used_weight": 0, "spool_weight": 245}], res


@needs_node
def test_a_used_spool_in_the_weigh_out_list_is_offered_nothing_but_keeps_its_tare(tmp_path):
    res = _run(tmp_path, WEIGH, ROW.replace("__USED__", "31").replace("__TARE__", "167"))
    assert res["asked"] == [{"prefill": None, "offer": ""}], res
    assert res["updates"] == [{"used_weight": 0, "spool_weight": 167}], res


# ---- 63.9(c): the wizard's Scale Gross box --------------------------------------------------------------

WIZ = r"""
const set = (id, v) => { document.getElementById(id).value = v; };
set('wiz-spool-scale', '1245');
set('wiz-spool-empty_weight', __SPOOL__);
set('wiz-fil-empty_weight', __FIL__);
set('wiz-spool-initial_weight', '1000');
set('wiz-spool-used', 'untouched');
set('wiz-spool-remaining', 'untouched');
window.wizardCalcUsedWeight();
const note = document.getElementById('wiz-spool-scale-note');
return { used: document.getElementById('wiz-spool-used').value, note: note.textContent, shown: note.style.display };
"""


@needs_node
def test_the_wizards_scale_box_computes_nothing_with_no_tare_and_says_why(tmp_path):
    """RED: a missing tare read as 0 g: used = 1000 + 0 - 1245, clamped to 0, as if
    the 245 g spool were filament."""
    res = _run(tmp_path, ["inv_core.js", "weight_utils.js", "inv_wizard.js"], WIZ.replace("__SPOOL__", "''").replace("__FIL__", "''"))
    assert res["used"] == "untouched", res
    assert res["note"] == "Enter the spool's empty weight first: FCC needs it to tell the filament from the spool.", res
    assert res["shown"] == "", res


@needs_node
@pytest.mark.parametrize("spool, fil", [("'245'", "''"), ("''", "'245'")], ids=["spool-box", "filament-box"])
def test_control_with_a_tare_the_scale_box_computes_as_before(tmp_path, spool, fil):
    """Control: with a tare at any level it computes as on e1b22f4 (RED there only for
    the note, which is new and stays hidden)."""
    res = _run(tmp_path, ["inv_core.js", "weight_utils.js", "inv_wizard.js"], WIZ.replace("__SPOOL__", spool).replace("__FIL__", fil))
    assert res["used"] == "0", res
    assert res["note"] == "" and res["shown"] == "none", res
