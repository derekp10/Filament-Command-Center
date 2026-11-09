"""Group 54 review (S2): the wizard's attribute chips keep an attribute's text whole.

Found by Group 54.2's builder: the wizard built its chips' HTML with the value
unescaped (`data-value="${val}">${val} &times;`), in both builders, the chip added
from the field (wizardAddMultiChoiceChip) and Edit Spool's prefill of a filament's
stored list. An attribute like `Odd "Quote" <b>Tag</b> & Co` read "Odd" in the
wizard's chip (the quote ended the attribute, and `<b>` became an element), and
Save, which collects the chips by `data-value`, sent "Odd ": Spoolman 0.27 refuses a
value that isn't one of the field's choices, so the filament's save failed (were
"Odd" a choice, the attribute would have been swapped silently). The spool window,
the filament window and Edit Filament already escape it. The chip field's own
dropdown, which a pick reads back by its text, and a single-choice field's options
had the same unescaped text.

Hermetic and page-level, on the Group 58.5 harness (the REAL modals_wizard.html and
modules in `isolated_page`, the real Save), so it runs under --offline.
"""
from __future__ import annotations

import copy

import pytest

from test_wizard_label_status_58_5 import MODULES, PRELUDE, WIZARD_HTML, _save
from test_wizard_native_clear_54_5 import _details, _vendor

EDIT = "/api/edit_spool_wizard"
ODD = 'Odd "Quote" <b>Tag</b> & Co'
CHIPS = "#chip-container-fil-filament_attributes"

FIELDS = {"success": True, "fields": {
    "filament": [
        {"entity_type": "filament", "field_type": "choice", "multi_choice": True, "key": "filament_attributes",
         "name": "Filament Attributes", "order": 5, "choices": ["Matte", "Silk", ODD]},
        {"entity_type": "filament", "field_type": "choice", "multi_choice": False, "key": "finish_note",
         "name": "Finish Note", "order": 6, "choices": ["Plain", ODD]},
        {"entity_type": "filament", "field_type": "boolean", "key": "needs_label_print",
         "name": "Needs Label Print", "order": 14},
    ],
    "spool": [],
}}


@pytest.fixture
def wiz(isolated_page):
    page = isolated_page
    page.set_content('<!doctype html><html><head><meta charset="utf-8"></head><body>'
                     '<div id="toast-container"></div>' + WIZARD_HTML.read_text(encoding="utf-8")
                     + '</body></html>')
    page.add_script_tag(content=PRELUDE)
    for name in ("overlay_mount.js", "inv_core.js", "choice_validation.js", "weight_utils.js",
                 "empty_weight_field.js", "inv_wizard.js"):
        page.add_script_tag(content=(MODULES / name).read_text(encoding="utf-8"))
    page.evaluate("""(a) => { Object.assign(window.__answers, a); }""", {
        "/api/external/fields": FIELDS,
        "/api/external/vendors": {"success": True, "vendors": [_vendor(None)]},
        "/api/locations": [{"LocationID": "SHELF-1", "Name": "Shelf", "Type": "Section"}],
        "/api/filaments": {"success": True, "filaments": []},
        "/api/edit_spool_wizard": {"success": True, "spool_id": 57},
    })
    return page


def _open_edit(page, attrs, finish=None):
    details = _details()
    details["filament"]["extra"] = {"filament_attributes": attrs}
    if finish is not None:
        details["filament"]["extra"]["finish_note"] = finish
    page.evaluate("(d) => { window.__answers['/api/spool_details'] = d; }", copy.deepcopy(details))
    page.evaluate("() => { window.openEditWizard(57); }")
    page.wait_for_function("() => wizardState.mode === 'edit_spool' && !!document.querySelector('" + CHIPS + "')"
                           " && document.getElementById('wiz-fil-color_name').value === 'Red'"
                           " && !document.getElementById('btn-wiz-submit').disabled")


def _chips(page):
    """Each chip as the page has it: [its data-value, its text]."""
    return page.evaluate("(s) => Array.from(document.querySelectorAll(s + ' .dynamic-chip'))"
                         ".map(c => [c.getAttribute('data-value'), c.textContent.trim()])", CHIPS)


def test_edit_spool_draws_a_stored_attribute_whole(wiz):
    """RED on the base: the chip's data-value is 'Odd ' and its text loses the rest."""
    _open_edit(wiz, [ODD, "Matte"])
    assert _chips(wiz) == [[ODD, ODD + " ×"], ["Matte", "Matte ×"]]
    assert wiz.evaluate("(s) => document.querySelector(s).querySelectorAll('b').length", CHIPS) == 0


def test_edit_spool_saves_a_stored_attribute_whole(wiz):
    """Save collects the chips by their data-value. RED on the base: 'Odd ' sent,
    which Spoolman refuses as no choice of the field."""
    _open_edit(wiz, [ODD, "Matte"])
    extra = _save(wiz, EDIT)["filament_data"]["extra"]
    assert extra["filament_attributes"] == [ODD, "Matte"], extra


def test_a_chip_added_from_the_field_is_whole(wiz):
    """The chip the field adds (a pick, Enter, or the ➕). RED on the base."""
    _open_edit(wiz, ["Matte"])
    wiz.evaluate("(v) => window.wizardAddMultiChoiceChip('fil', 'filament_attributes', v)", ODD)
    assert _chips(wiz) == [["Matte", "Matte ×"], [ODD, ODD + " ×"]]
    assert _save(wiz, EDIT)["filament_data"]["extra"]["filament_attributes"] == ["Matte", ODD]


def test_the_same_value_twice_is_one_chip(wiz):
    """The duplicate guard compares the value as the chip holds it (data-value reads
    back unescaped). RED on the base (the broken chip never matched), and on a fix
    that compares the escaped text."""
    _open_edit(wiz, [ODD])
    wiz.evaluate("(v) => window.wizardAddMultiChoiceChip('fil', 'filament_attributes', v)", ODD)
    assert _chips(wiz) == [[ODD, ODD + " ×"]]


def test_a_pick_from_the_fields_list_is_whole(wiz):
    """The field's dropdown shows each choice as text, and a pick reads it back by
    its text. RED on the base: the option drew `<b>`, so the pick read
    'Odd "Quote" Tag & Co', a value that is no choice."""
    _open_edit(wiz, ["Matte"])
    option = wiz.locator("#dropdown-fil-filament_attributes .autocomplete-option").nth(2)
    assert option.evaluate("(o) => [o.textContent, o.querySelectorAll('b').length]") == [ODD, 0]
    option.dispatch_event("mousedown")
    assert _chips(wiz)[-1] == [ODD, ODD + " ×"]


def test_a_material_from_the_list_is_whole(wiz):
    """The Material field's list of the materials on record had the same unescaped
    text, and its pick passed the name as a JS string inside the handler's attribute
    (only a ' was escaped). RED on the base: the option drew `<b>`, and the quote
    ended the handler's attribute, so the rest of the handler showed as the
    option's text."""
    odd_material = 'PLA "Odd" <b>X</b> & Co'
    wiz.evaluate("(m) => { window.__answers['/api/filaments'] = { success: true, filaments: ["
                 "{ id: 3, material: m, name: 'Red' }, { id: 4, material: 'PETG', name: 'Blue' }] }; }",
                 odd_material)
    wiz.evaluate("() => window.openWizardModal()")
    options = wiz.locator("#dropdown-material .autocomplete-option")
    options.nth(1).wait_for(state="attached")
    assert options.count() == 2
    option = options.nth(1)                             # sorted: PETG, then PLA ...
    assert option.evaluate("(o) => [o.textContent, o.querySelectorAll('b').length]") == [odd_material, 0]
    option.dispatch_event("mousedown")
    assert wiz.locator("#wiz-fil-material").input_value() == odd_material


def test_a_single_choice_fields_option_is_whole(wiz):
    """A single-choice field's options had the same unescaped text: the option's
    value was 'Odd ', so the filament's stored value showed as nothing. RED on the
    base."""
    _open_edit(wiz, ["Matte"], finish=ODD)
    sel = wiz.locator("#wiz_fil_ef_finish_note")
    assert sel.evaluate("(s) => Array.from(s.options).map(o => o.value)") == ["", "Plain", ODD]
    assert sel.input_value() == ODD
    assert _save(wiz, EDIT)["filament_data"]["extra"]["finish_note"] == ODD
