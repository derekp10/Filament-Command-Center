"""The wizard never sends a clear the user didn't make (2026-10-21 review, browser-3,
red), hermetic: the REAL overlay_mount.js, inv_core.js, choice_validation.js and
inv_wizard.js in `isolated_page` (no network), so it runs under --offline.

Since the Spoolman 0.27 extras-clear fix, a blank extra that Edit Spool sends as
cleared really clears the record. The single-choice ➕ (adding a Slicer Profile,
say) used to call wizardFetchExtraFields(), which draws every extra again,
blank: Save then erased the filament's attributes, colour and drying data. Two
guards, both pinned here:

  - the ➕ adds its option to its own select and picks it, drawing nothing
    else again (as the multi-choice ➕ already did);
  - edit mode sends a blank extra as cleared only when the user changed that
    field: wizardState.touchedExtras, filled by the wizard's input / change
    listener and a capture-phase click on a chip (its own onclick removes it).
    The collectors' side is pinned by test_extras_clear_027_js.py.
"""
from __future__ import annotations

from pathlib import Path

import pytest

HUB = Path(__file__).resolve().parent.parent
MODULES = HUB / "static" / "js" / "modules"

PRELUDE = r"""
window.__pendingShortcuts = [];
window.registerShortcut = function (s) { window.__pendingShortcuts.push(s); };
window.__fetches = [];
window.fetch = function (url, opts) {
    window.__fetches.push([String(url), (opts && opts.method) || 'GET']);
    const body = String(url).indexOf('/add_choice') >= 0 ? { success: true } : { success: true, fields: {} };
    return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(body) });
};
"""

PAGE = """<!doctype html><html><head><meta charset="utf-8"></head><body>
<div id="toast-container"></div>
<div id="wizardModal" class="modal show">
  <div id="wiz-fil-dynamic-extra-fields"></div>
  <div id="wiz-spool-dynamic-extra-fields"></div>
</div>
</body></html>"""

SETUP = r"""() => {
    wizardState.mode = 'edit_spool';
    wizardState.extraFields = { filament: [
        { key: 'slicer_profile', name: 'Slicer Profile', field_type: 'choice', multi_choice: false,
          choices: ['Basic PLA'] },
        { key: 'drying_temp', name: 'Drying Temp', field_type: 'text' },
        { key: 'filament_attributes', name: 'Filament Attributes', field_type: 'choice', multi_choice: true,
          choices: ['Silk', 'Matte'] },
    ], spool: [
        { key: 'spool_temp', name: 'Temp Resistance', field_type: 'choice', multi_choice: false,
          choices: ['High', 'Low'] },
    ] };
    document.getElementById('wiz-fil-dynamic-extra-fields').innerHTML =
        wizardState.extraFields.filament.map((f) => wizardGenerateFieldHTML(f, 'fil')).join('');
    document.getElementById('wiz-spool-dynamic-extra-fields').innerHTML =
        wizardState.extraFields.spool.map((f) => wizardGenerateFieldHTML(f, 'spool')).join('');
    // The edit prefill: values set by code (no events), as openEditWizard does.
    document.getElementById('wiz_fil_ef_drying_temp').value = '50';
    document.getElementById('wiz_fil_ef_slicer_profile').value = 'Basic PLA';
    document.getElementById('wiz_spool_ef_spool_temp').value = 'High';
    document.getElementById('chip-container-fil-filament_attributes').insertAdjacentHTML('beforeend',
        '<span class="badge rounded-pill dynamic-chip" onclick="this.remove()" data-key="filament_attributes" '
        + 'data-selected="true" data-value="Silk">Silk &times;</span>');
    document.getElementById('wiz_fil_ef_drying_temp').__prefilled = true;
}"""


@pytest.fixture
def wizard(isolated_page):
    page = isolated_page
    page.set_content(PAGE)
    page.add_script_tag(content=PRELUDE)
    for name in ("overlay_mount.js", "inv_core.js", "choice_validation.js", "inv_wizard.js"):
        page.add_script_tag(content=(MODULES / name).read_text(encoding="utf-8"))
    page.evaluate(SETUP)
    return page


def _touched(page):
    return sorted(page.evaluate("() => Array.from(wizardState.touchedExtras)"))


def test_the_single_choice_plus_adds_its_option_without_drawing_the_form_again(wizard):
    """RED on 87533d7: the ➕ refetched the field list and drew every extra again,
    blank (the prefilled Drying Temp, the Silk chip, the spool's Temp
    Resistance), then picked the new profile."""
    page = wizard
    page.evaluate("window.wizardPromptNewChoice('fil', 'slicer_profile')")
    page.wait_for_selector("#fcc-wiz-newchoice-input")
    page.locator("#fcc-wiz-newchoice-input").fill("Zebra Custom Profile")
    page.locator("#fcc-wiz-newchoice-confirm").click()
    page.get_by_role("button", name="Add Permanently").click()            # its "permanent new choice?" step
    page.wait_for_function("() => document.getElementById('wiz_fil_ef_slicer_profile').value === 'Zebra Custom Profile'")
    state = page.evaluate("""() => ({
        drying: document.getElementById('wiz_fil_ef_drying_temp').value,
        same: document.getElementById('wiz_fil_ef_drying_temp').__prefilled === true,
        chips: Array.from(document.querySelectorAll('#chip-container-fil-filament_attributes .dynamic-chip'))
            .map((c) => c.dataset.value),
        spoolTemp: document.getElementById('wiz_spool_ef_spool_temp').value,
        options: Array.from(document.getElementById('wiz_fil_ef_slicer_profile').options).map((o) => o.value),
        choices: wizardState.extraFields.filament[0].choices,
    })""")
    assert state["drying"] == "50" and state["same"] is True, state      # the same element, untouched
    assert state["chips"] == ["Silk"] and state["spoolTemp"] == "High", state
    assert "Zebra Custom Profile" in state["options"] and "Zebra Custom Profile" in state["choices"], state
    fetched = page.evaluate("window.__fetches")
    assert ["/api/external/fields", "GET"] not in fetched, fetched          # no refetch, no redraw
    assert any(u.endswith("/api/external/fields/add_choice") and m == "POST" for u, m in fetched), fetched
    # Picking it is the user's change; nothing else is.
    assert _touched(page) == ["fil:slicer_profile"]


def test_only_the_fields_the_user_changes_count_as_touched(wizard):
    """RED on 87533d7: no such record."""
    page = wizard
    assert _touched(page) == []
    page.locator("#wiz_fil_ef_drying_temp").fill("")                        # emptied by the user
    page.locator("#wiz_spool_ef_spool_temp").select_option("Low")
    page.locator("#chip-container-fil-filament_attributes .dynamic-chip").click()   # removes the chip
    assert page.locator("#chip-container-fil-filament_attributes .dynamic-chip").count() == 0
    assert _touched(page) == ["fil:drying_temp", "fil:filament_attributes", "spool:spool_temp"]


def test_a_new_session_starts_with_nothing_touched(wizard):
    page = wizard
    page.locator("#wiz_fil_ef_drying_temp").fill("55")
    assert _touched(page) == ["fil:drying_temp"]
    # wizardReset goes on to the rest of the wizard's form, which this page
    # doesn't have; the touched record is reset first.
    page.evaluate("() => { try { wizardReset(); } catch (_) { /* the form this page lacks */ } }")
    assert _touched(page) == []
