"""Review round 2 of Group 66 (Q3-01 / Q5-01, Q3-02 / Q5-02, Q3-03): what a scanned label's
keys changed in the wizard is undone key by key, and only that.

Group 66.4 put back a snapshot of the whole form taken at the label's first key. So:
  - Quantity's Spool rows weren't in it: a label scanned into Quantity left the box reading
    3 while the rows held the label's count (57, 357, or 1), and Create made that many
    spools (its `spool_overrides` drives the server's count);
  - a slicer profile FCC suggested wasn't in it: a label scanned into the brand box dropped
    the suggestion, its "(new, from …)" option and its note, and Save sent no profile;
  - an answer that landed while the label was being typed was undone with it: a Prusament
    QR's lookup answering mid-label had its Step 2 fill blanked and Save greyed out again.
Now each key typed into a wizard box is journaled with what it changed, and the undo puts
each thing back only while it holds what that key left it. Every case here also checks
that no key changed a wizardState key the undo leaves alone (window.wizardScanUntracked)
and that nothing threw on the page.

Hermetic, on the Group 58.5 harness (the 54.5 `wiz` page), so it runs under --offline.
Each case marked RED fails on 20265b12 (and f09bdc9c) for the reason it names.
"""
from __future__ import annotations

import copy
import json

import pytest

from test_wizard_label_status_58_5 import FIELDS, _save
from test_wizard_native_clear_54_5 import _open_new_filament, _tab_in, _value, wiz  # noqa: F401
from test_wizard_scan_capture_66_4 import PRUSAMENT, SCAN_STUB, _scans

CREATE = "/api/create_inventory_wizard"


@pytest.fixture
def scanning(wiz):  # noqa: F811
    wiz.evaluate(SCAN_STUB)
    yield wiz
    assert wiz.evaluate("() => window.__errors") == []
    assert wiz.evaluate("() => window.wizardScanUntracked") == []


def _open_manual(page):
    page.evaluate("() => window.openWizardModal()")
    page.wait_for_function("() => !!document.getElementById('wiz_fil_ef_needs_label_print')")
    page.evaluate("() => wizardSelectType('manual')")


def _type_label(page, label):
    """A scanner's label, at its pace, then its Enter."""
    page.keyboard.type(label, delay=8)
    page.keyboard.press("Enter")
    page.wait_for_timeout(100)


# --- Quantity's Spool rows ---------------------------------------------------------------------

def _three_rows_two_scanned(page):
    _open_new_filament(page)
    _tab_in(page, "#wiz-spool-qty")
    page.keyboard.type("3", delay=120)
    page.evaluate("""() => {
        const ov = { initial_weight: 1000, spool_weight: 186, extra: { prusament_manufacturing_date: '"2026-01-02"' } };
        [1, 2].forEach((i) => Object.assign(wizardState.spoolRows[i],
            { url: 'https://prusament.com/spool/1770' + i + '/abc/', status: 'ok', override: JSON.parse(JSON.stringify(ov)) }));
        wizardRenderSpoolRows(); wizardUpdateSubmitGate();
    }""")


def _rows(page):
    return page.evaluate("() => wizardState.spoolRows.map((r) => [r.idx, r.status, r.url, JSON.stringify(r.override)])")


@pytest.mark.parametrize("label, selected", [
    ("ID:57", True), ("ID:57", False), ("ID:1", True), ("LOC:SHELF-1", True), ("LOC:SHELF-1", False), (PRUSAMENT, True),
], ids=["57-selected", "57-caret-at-end", "1-selected", "place-selected", "place-caret-at-end", "prusament-link"])
def test_a_label_scanned_into_quantity_leaves_its_spool_rows(scanning, label, selected):
    """RED: Quantity read 3 again, the rows held the label's count (57, 357, or 1, the
    scanned rows' data gone), and Create sent that many overrides, which the server makes
    into spools."""
    _three_rows_two_scanned(scanning)
    before = _rows(scanning)
    if selected:
        _tab_in(scanning, "#wiz-spool-qty")
    else:
        scanning.focus("#wiz-spool-qty")
        scanning.keyboard.press("End")
        scanning.wait_for_timeout(300)
    _type_label(scanning, label)
    assert _scans(scanning) == [label]
    assert _value(scanning, "#wiz-spool-qty") == "3"
    assert _rows(scanning) == before
    assert scanning.locator("[data-spool-row-idx]").count() == 3
    assert scanning.locator("#wiz-spool-rows-summary").inner_text().startswith("2 of 3 spools have scan data")
    body = _save(scanning, CREATE)
    assert body["quantity"] == 3
    assert len(body["spool_overrides"]) == 3, len(body["spool_overrides"])
    assert [o.get("spool_weight") for o in body["spool_overrides"]] == [None, 186, 186]


def test_a_persons_quantity_still_draws_its_rows(scanning):
    """A pin: the count a person types still draws that many rows (the undo is the scan's)."""
    _three_rows_two_scanned(scanning)
    _tab_in(scanning, "#wiz-spool-qty")
    scanning.keyboard.type("5", delay=120)
    assert scanning.locator("[data-spool-row-idx]").count() == 5
    assert len(_save(scanning, CREATE)["spool_overrides"]) == 5


# --- a slicer profile FCC suggested --------------------------------------------------------------

def _with_profile_field(page):
    fields = copy.deepcopy(FIELDS)
    fields["fields"]["filament"].append({"entity_type": "filament", "field_type": "choice", "key": "slicer_profile",
                                         "name": "Slicer Profile", "order": 20, "multi_choice": False,
                                         "choices": ["Prusament PLA", "Generic PLA"]})
    page.evaluate("(f) => { window.__answers['/api/external/fields'] = f; }", fields)


def _profile(page):
    return page.evaluate("""() => {
        const sel = document.getElementById('wiz_fil_ef_slicer_profile');
        const note = document.getElementById('wiz-fil-profile-note');
        return { value: sel.value, suggested: sel.dataset.fccSuggested || null,
                 options: Array.from(sel.options).map((o) => [o.value, o.textContent]),
                 note: note ? [note.textContent, note.style.display] : null,
                 suggestion: wizardState.profileSuggestion };
    }""")


def _suggested(page, lookup):
    _with_profile_field(page)
    _open_new_filament(page)
    page.wait_for_function("() => !!document.getElementById('wiz_fil_ef_slicer_profile')")
    page.evaluate("() => wizardComboboxSet('wiz-fil-vendor-search', 'wiz-fil-vendor-sel', '2', 'Some Brand')")
    assert page.evaluate("(l) => !!wizardSuggestSlicerProfile({ lookup: l, source: 'Prusament' })", lookup)


@pytest.mark.parametrize("lookup", ["Prusament PLA", "Brand New Profile"], ids=["listed", "new"])
@pytest.mark.parametrize("box", ["#wiz-fil-vendor-search", "#wiz-fil-material"], ids=["brand", "material"])
def test_a_label_scanned_into_the_brand_or_material_keeps_a_suggested_profile(scanning, lookup, box):
    """RED (the brand box): the suggestion dropped, its "(new, from …)" option removed (the
    select then blank), and its note saying the brand changed, though the box was put back;
    Save sent no slicer profile. The Material box is a pin (its keys fire no `change`)."""
    _suggested(scanning, lookup)
    before = _profile(scanning)
    scanning.focus(box)
    scanning.keyboard.press("End")
    scanning.wait_for_timeout(300)
    _type_label(scanning, "ID:57")
    assert _scans(scanning) == ["ID:57"]
    assert _profile(scanning) == before
    sent = _save(scanning, CREATE)["filament_data"]["extra"].get("slicer_profile")
    if isinstance(sent, str) and sent.startswith('"'):
        sent = json.loads(sent)
    assert sent == lookup


def test_a_persons_new_brand_still_drops_the_suggestion(scanning):
    """A pin: a brand the person picks clears a profile named for another brand."""
    _suggested(scanning, "Prusament PLA")
    scanning.evaluate("() => wizardComboboxSet('wiz-fil-vendor-search', 'wiz-fil-vendor-sel', '3', 'Other Brand')")
    scanning.evaluate("() => document.getElementById('wiz-fil-vendor-sel')"
                      ".dispatchEvent(new Event('change', { bubbles: true }))")
    after = _profile(scanning)
    assert after["value"] == "" and after["suggestion"] is None
    assert "changed after Prusament named Prusament PLA" in after["note"][0]


# --- an answer that lands while the label is being typed -------------------------------------------

LOOKUP = {"success": True, "results": [{
    "name": "Galaxy Black", "color_name": "Galaxy Black", "material": "PLA", "brand": "Prusament",
    "vendor": "Prusament", "color_hex": "222222", "diameter": 1.75, "density": 1.24, "weight": 1000,
    "spool_weight": 186, "settings_extruder_temp": 215, "settings_bed_temp": 60}]}


def test_an_answer_that_lands_mid_label_keeps_what_it_wrote(scanning):
    """A Prusament QR in Spool 1 (its lookup held), then a spool label scanned into Spool 2,
    where the eager advance put the keyboard; the lookup answers between the label's first
    key and its Enter. RED: the Enter put back Save's "pending" state (greyed out with the
    row ok) and blanked Step 2's fill, while the one-way lock stayed set."""
    _open_manual(scanning)
    _tab_in(scanning, "#wiz-spool-qty")
    scanning.keyboard.type("2", delay=120)
    scanning.evaluate("""(answer) => {
        const real = window.fetch;
        window.__held = null;
        window.fetch = (url, opts) => {
            if (String(url).indexOf('/api/external/search') >= 0) {
                return new Promise((res) => {
                    window.__held = () => res({ ok: true, status: 200, json: () => Promise.resolve(answer) });
                });
            }
            return real(url, opts);
        };
    }""", LOOKUP)
    scanning.focus("[data-spool-row-idx='0'] input[type='url']")
    scanning.keyboard.type(PRUSAMENT, delay=5)
    scanning.keyboard.press("Enter")
    scanning.wait_for_function("() => !!window.__held")
    assert scanning.evaluate("() => document.activeElement.closest('[data-spool-row-idx]').dataset.spoolRowIdx") == "1"
    scanning.keyboard.type("ID:", delay=8)
    scanning.evaluate("() => window.__held()")
    scanning.wait_for_function("() => wizardState.spoolRows[0].status === 'ok'")
    scanning.wait_for_timeout(100)
    _type_label(scanning, "57")
    got = scanning.evaluate("""() => ({ save: document.getElementById('btn-wiz-submit').disabled,
                                         rows: wizardState.spoolRows.map((r) => r.status),
                                         material: document.getElementById('wiz-fil-material').value,
                                         colour: document.getElementById('wiz-fil-color_name').value,
                                         spool2: document.querySelector("[data-spool-row-idx='1'] input[type='url']").value })""")
    assert got == {"save": False, "rows": ["ok", "empty"], "material": "PLA", "colour": "Galaxy Black", "spool2": ""}, got
    assert _scans(scanning) == ["ID:57"]


# --- the slot label's picker (Q4-02) -------------------------------------------------------------------

def _boxes(page, outcome):
    page.evaluate("""(outcome) => {
        window.__answers['/api/locations'] = [
            { LocationID: 'SHELF-1', Name: 'Shelf', Type: 'Section' },
            { LocationID: 'BOX-1', Name: 'Dryer', Type: 'Dryer Box', 'Max Spools': '4' }];
        window.__picker = [];
        window.openSlotPicker = () => {};
        window.placeOneWithPicker = (o) => {
            window.__picker.push(o && o.loc);
            if (outcome === 'stopped') return Promise.resolve({ outcome: 'stopped' });
            return new Promise((res) => o.send({ location: 'BOX-1', slot: 2, label: 'slot 2' }, res));
        };
    }""", outcome)


def test_a_slot_label_whose_picker_is_closed_leaves_location_as_it_was(scanning):
    """The picker closed with nothing picked: Location is as it was, and nothing threw (its
    stub returned no Promise, and the case passed over a TypeError)."""
    _boxes(scanning, "stopped")
    _open_new_filament(scanning)
    _tab_in(scanning, "#wiz-spool-location-search")
    _type_label(scanning, "LOC:BOX-1:SLOT:2")
    assert scanning.evaluate("() => window.__picker") == ["BOX-1"]
    assert (_value(scanning, "#wiz-spool-location-search"), _value(scanning, "#wiz-spool-location")) == ("", "")
    assert scanning.evaluate("() => wizardState.pendingPlacement") is None
    assert _scans(scanning) == []


def test_a_slot_label_whose_slot_is_picked_holds_the_choice_for_save(scanning):
    """The picker's slot is held for Save, as a mouse pick's is."""
    _boxes(scanning, "moved")
    _open_new_filament(scanning)
    _tab_in(scanning, "#wiz-spool-location-search")
    _type_label(scanning, "LOC:BOX-1:SLOT:2")
    assert _value(scanning, "#wiz-spool-location") == "BOX-1"
    assert _value(scanning, "#wiz-spool-location-search") == "Dryer (BOX-1) — slot 2"
    held = scanning.evaluate("() => wizardState.pendingPlacement")
    assert (held["location"], held["slot"], held["via"]) == ("BOX-1", 2, "BOX-1")
    assert _scans(scanning) == []
