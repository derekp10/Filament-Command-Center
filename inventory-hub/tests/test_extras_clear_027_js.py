"""The pages that clear a Spoolman extra send the clear (2026-10-21), as hermetic
JS checks under node's `vm` (the stub DOM of test_core1_return_ejectall_js.py;
the real inv_core.js, inv_wizard.js, ui_builder.js and inv_details.js, no browser,
no container).

Spoolman 0.26+ (dev and prod run 0.27.0) KEEPS an extra a PATCH leaves out, and
so does FCC's own read-merge on any Spoolman, so a page that drops a key to clear
it changed nothing. Each of these sends window.FCC_DELETE_EXTRA instead, which
the server turns into the write that clears that field:

  - the wizard's Edit Spool: an emptied Purchase / Product Link is sent as the
    sentinel. The Spool Extras section also rendered the two links as dynamic
    fields, collected AFTER the dedicated inputs, so their copies (the old link,
    or a blank over a newly typed one) overwrote what the user did;
  - the wizard's Edit Spool: a chip field whose last chip was removed (Filament
    Attributes) is sent as cleared; it was left out, so the old list stayed (and
    the label-reprint nudge still fired for it);
  - but only a field the user changed (wizardState.touchedExtras, filled by the
    wizard's input / change / chip-click listener): a field the page drew blank
    is never sent as cleared (2026-10-21 review: a ➕ redrew every extra blank,
    and Save then erased them all; tests/test_wizard_extras_touched.py drives
    the listener and the ➕ in a browser);
  - the Filament Details slicer-profile pencil's "(none)" and the Swatch Printed
    editor's "Unknown / clear" send the sentinel; both deleted the key client-side;
  - each of them, and the Edit Filament modal, shows the server's `warning` (a
    field Spoolman kept) as a 7 s toast.

Base proof (74d780a): every test here fails there; see the commit message.
"""
from __future__ import annotations

import json

from test_core1_return_ejectall_js import pytestmark, run_js  # noqa: F401  (pytestmark: skip without node)
from test_head_load_confirm_js import PRELUDE
from test_wizard_location_save_js import WIZARD

SENTINEL = "__FCC_DELETE_EXTRA__"
WIZ_MODULES = ["inv_core.js", "inv_wizard.js"]
DETAILS_MODULES = ["inv_core.js", "ui_builder.js", "inv_details.js"]


def _js(value):
    return json.dumps(value)


def _run(tmp_path, modules, body):
    res = run_js(tmp_path, modules, PRELUDE + body)
    assert res["unhandled"] == [], res["unhandled"]
    return res


# The dynamic Spool Extras fields a page would have collected, as the stub DOM's
# querySelectorAll never returns any: `copies` stand in for them.
DYNAMIC = r"""
const el = (key, value, type) => ({ getAttribute: (k) => (k === 'data-key' ? key : null), type: type || 'text', value });
const __qsa = document.querySelectorAll.bind(document);
const serve = (map) => { document.querySelectorAll = (sel) => (sel in map ? map[sel] : __qsa(sel)); };
"""


def test_an_emptied_or_retyped_spool_link_is_sent_as_the_user_left_it(tmp_path):
    """RED on the base: the dynamic copy of product_url re-sent the old link over
    the emptied field, and the blank copy of purchase_url sent a clear over the
    newly typed one."""
    res = _run(tmp_path, WIZ_MODULES, WIZARD + DYNAMIC + f"""
editing(57, '');
(wizardState.touchedExtras || new Set()).add('spool:spool_type');          // the user emptied it
document.getElementById('wiz-spool-product_url').value = '';
document.getElementById('wiz-spool-purchase_url').value = 'https://new.example/buy';
serve({{ '.dynamic-extra-spool-field': [el('product_url', 'https://old.example/p'), el('purchase_url', ''),
                                         el('spool_type', ''), el('prusament_length_m', '330')] }});
answerFor({{ '/api/edit_spool_wizard': [{_js({"success": True, "spool_id": 57})}] }});
await window.wizardSubmit();
await __settle(100);
return {{ body: posts('/api/edit_spool_wizard')[0] }};
""")
    extra = res["body"]["spool_data"]["extra"]
    assert extra["product_url"] == SENTINEL, extra
    assert extra["purchase_url"] == "https://new.example/buy", extra
    assert extra["spool_type"] == SENTINEL and extra["prusament_length_m"] == "330", extra   # still collected


def test_the_spool_links_are_not_rendered_twice(tmp_path):
    """RED on the base: no such rule (both links rendered as Spool Extras too)."""
    res = _run(tmp_path, WIZ_MODULES, """
const shown = window.wizardSpoolExtraShown || (() => 'missing');
return { out: ['product_url', 'purchase_url', 'container_slot', 'physical_source', 'needs_label_print',
               'spool_type', 'prusament_length_m'].map(k => [k, shown(k)]) };
""")
    assert dict(res["out"]) == {"product_url": False, "purchase_url": False, "container_slot": False,
                                "physical_source": False, "needs_label_print": False,
                                "spool_type": True, "prusament_length_m": True}, res


CHIP_FIELDS = r"""
wizardState.extraFields = { filament: [
  { key: 'filament_attributes', field_type: 'choice', multi_choice: true, choices: ['Silk', 'Matte'] },
  { key: 'slicer_profile', field_type: 'choice', multi_choice: false, choices: ['Basic PLA'] },
], spool: [] };
const chip = (key, value) => ({ getAttribute: (k) => ({ 'data-key': key, 'data-value': value })[k] || null });
"""


def test_removing_the_last_chip_clears_the_field_on_edit(tmp_path):
    """RED on the base: the field was left out, so the old list stayed."""
    res = _run(tmp_path, WIZ_MODULES, WIZARD + DYNAMIC + CHIP_FIELDS + f"""
editing(57, '');
(wizardState.touchedExtras || new Set()).add('fil:filament_attributes');   // the user removed its last chip
answerFor({{ '/api/edit_spool_wizard': [{_js({"success": True, "spool_id": 57})}] }});
await window.wizardSubmit();
await __settle(100);
return {{ body: posts('/api/edit_spool_wizard')[0] }};
""")
    extra = res["body"]["filament_data"]["extra"]
    assert extra.get("filament_attributes") == SENTINEL, extra
    assert "slicer_profile" not in extra, extra        # single choice: its own select sends it


def test_a_field_the_page_drew_blank_is_never_cleared(tmp_path):
    """Review browser-3 (red): a blank the user didn't make (the page drew the
    field again, blank) is left out, so the record keeps its value; only the
    fields the user emptied are sent as cleared. RED on 87533d7 (every blank
    extra and the empty chip box were sent as cleared)."""
    res = _run(tmp_path, WIZ_MODULES, WIZARD + DYNAMIC + CHIP_FIELDS + f"""
editing(57, '');
(wizardState.touchedExtras || new Set()).add('fil:original_color');        // the one the user emptied
serve({{ '.dynamic-extra-field': [el('drying_temp', ''), el('original_color', ''), el('slicer_profile', 'Basic PLA')],
         '.dynamic-extra-spool-field': [el('spool_temp', ''), el('spool_type', 'Refill')] }});
answerFor({{ '/api/edit_spool_wizard': [{_js({"success": True, "spool_id": 57})}] }});
await window.wizardSubmit();
await __settle(100);
return {{ body: posts('/api/edit_spool_wizard')[0] }};
""")
    fil = res["body"]["filament_data"]["extra"]
    spool = res["body"]["spool_data"]["extra"]
    assert fil.get("original_color") == SENTINEL, fil
    assert "drying_temp" not in fil and "filament_attributes" not in fil, fil
    assert fil["slicer_profile"] == "Basic PLA", fil
    assert "spool_temp" not in spool and spool["spool_type"] == "Refill", spool


def test_chips_left_on_edit_are_sent_as_a_list(tmp_path):
    res = _run(tmp_path, WIZ_MODULES, WIZARD + DYNAMIC + CHIP_FIELDS + f"""
editing(57, '');
serve({{ '.dynamic-chip[data-selected="true"]': [chip('filament_attributes', 'Silk')] }});
answerFor({{ '/api/edit_spool_wizard': [{_js({"success": True, "spool_id": 57})}] }});
await window.wizardSubmit();
await __settle(100);
return {{ body: posts('/api/edit_spool_wizard')[0], helper: typeof window.wizardClearEmptyChipFields }};
""")
    assert res["body"]["filament_data"]["extra"]["filament_attributes"] == ["Silk"], res["body"]
    assert res["helper"] == "function", res     # RED on the base: no such helper


def test_the_label_diff_reads_a_cleared_chip_field_as_empty(tmp_path):
    """RED on the base: the sentinel read as a one-chip list, so clearing a field
    that had no chips still asked to reprint the label."""
    res = _run(tmp_path, WIZ_MODULES, f"""
const d = window.wizardBuildFilamentLabelDiff;
const cleared = {{ extra: {{ filament_attributes: window.FCC_DELETE_EXTRA }} }};
return {{
  fromEmpty: d({{ extra: {{ filament_attributes: [] }} }}, cleared).changedExtras,
  fromNone: d({{ extra: {{}} }}, cleared).changedExtras,
  fromSilk: d({{ extra: {{ filament_attributes: '["Silk"]' }} }}, cleared).changedExtras,
}};
""")
    assert res["fromEmpty"] == {} and res["fromNone"] == {}, res
    assert res["fromSilk"] == {"filament_attributes": True}, res


DETAILS = r"""
let __updateAnswer = { success: true };
window.__respond = (url) => {
  if (url === '/api/external/fields') return { body: { success: true, fields: { filament: [
    { key: 'slicer_profile', field_type: 'choice', multi_choice: false, choices: ['Basic PLA'] }] } } };
  if (url === '/api/filaments/12') return { body: { success: true, data: { id: 12, name: 'Gold', extra: {
    slicer_profile: 'Basic PLA', sample_printed: true, sheet_link: 'https://example.com/sheet' } } } };
  if (url === '/api/update_filament') return { body: __updateAnswer };
  return { body: { success: true } };
};
let __swalAnswer = null;
globalThis.Swal = {
  fire: () => Promise.resolve(__swalAnswer || { isConfirmed: false }),
  getPopup: () => null, close: () => {}, clickConfirm: () => {}, showValidationMessage: () => {},
};
"""


def test_the_slicer_pencils_none_sends_the_clear(tmp_path):
    """RED on the base: "(none)" deleted the key, and the server kept it."""
    res = _run(tmp_path, DETAILS_MODULES, DETAILS + """
__swalAnswer = { isConfirmed: true, value: { value: '', isNew: false } };
__updateAnswer = { success: true, warning: 'Filament #12: slicer_profile was not cleared (test).' };
window.promptEditSlicerProfile(12, 'Basic PLA');
await __settle(300);
return { body: posts('/api/update_filament')[0], toasts: toasts() };
""")
    extra = res["body"]["data"]["extra"]
    assert extra["slicer_profile"] == SENTINEL, extra
    assert extra["sheet_link"] == "https://example.com/sheet", extra          # siblings ride along
    assert {"msg": "Filament #12: slicer_profile was not cleared (test).", "type": "warning"} in res["toasts"], res


def test_the_swatch_editors_unknown_sends_the_clear(tmp_path):
    """RED on the base: "Unknown / clear" deleted the key, and the server kept it."""
    res = _run(tmp_path, DETAILS_MODULES, DETAILS + """
__swalAnswer = { isConfirmed: true, value: '' };
window.promptEditSampleStatus(12, 'true');
await __settle(300);
return { body: posts('/api/update_filament')[0], toasts: toasts() };
""")
    extra = res["body"]["data"]["extra"]
    assert extra["sample_printed"] == SENTINEL, extra
    assert extra["slicer_profile"] == "Basic PLA", extra
    assert any(t["msg"] == "Swatch status updated" for t in res["toasts"]), res
