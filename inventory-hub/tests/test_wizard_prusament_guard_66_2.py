"""Group 66.2: nothing starts an open wizard over without asking.

A new Prusament spool's QR read while the wizard was open (the keyboard not in a box)
answered prusament_new, and the scan path called openWizardModal unasked: wizardReset
cleared every box and marked the form clean, show() did nothing on the open window, so
the Unsaved Changes guard (on hide.bs.modal) never ran, and an Edit silently became an
Add. The legacy picker's Add new spool, and an Edit / Clone / New Spool opened over the
wizard, went the same way.

Now openWizardModal asks first while the wizard is open with changes (the Unsaved
Changes question, wizardAskDiscard: opening on Keep Editing, Discard waiting out a double
click, both answers shielding the next press, scans held while it is up), refuses while a
Save is on its way, and answers false when kept, so each opener stops with nothing
changed. A new Prusament spool's QR goes into an Add's empty Spool box with no question.
The dashboard's matched-spool question holds its weight correction while that very spool
is open in Edit Spool (its next Save would write the old weights back). A text box's
stale blur `change` after a reset no longer marks the new session changed. A list read
that fails no longer stops the open half-way.

Hermetic: the REAL modals_wizard.html and the scan path (inv_cmd.js's processScan) in
`isolated_page`, the Bootstrap stand-in of tests/edit_filament_harness.py (its 5.3
dismiss paths), so it runs under --offline.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from edit_filament_harness import PRELUDE as BOOT_PRELUDE

HUB = Path(__file__).resolve().parent.parent
MODULES = HUB / "static" / "js" / "modules"
WIZARD_HTML = HUB / "templates" / "components" / "modals_wizard.html"
QR = "https://prusament.com/spool/17705/abc123def0/"
QUESTION = "#fcc-wiz-unsaved-changes"

FIELDS = {"success": True, "fields": {
    "filament": [{"entity_type": "filament", "field_type": "text", "key": "drying_temp", "name": "Drying Temp", "order": 1}],
    "spool": [{"entity_type": "spool", "field_type": "text", "key": "original_color", "name": "Original Color", "order": 1}],
}}


def _details(sid=57):
    return {"archived": False, "extra": {}, "id": sid, "initial_weight": 1000.0, "location": "SHELF-1",
            "registered": "2026-02-11T04:07:24Z", "remaining_weight": 500.0, "spool_weight": 0.0, "used_weight": 500.0,
            "filament": {"color_hex": "72071C", "comment": "", "density": 1.24, "diameter": 1.75, "external_id": "",
                         "extra": {}, "id": 7, "material": "PLA", "name": "Red", "price": 0.0,
                         "settings_bed_temp": 60, "settings_extruder_temp": 215, "spool_weight": 0.0, "weight": 1000.0,
                         "vendor": {"extra": {}, "id": 2, "name": "Some Brand"}}}


TEST_PRELUDE = r"""
window.bootstrap.Collapse = { getOrCreateInstance: () => ({ toggle() {}, show() {}, hide() {} }) };
window.__si = window.setInterval; window.setInterval = () => 0;   // inv_cmd.js's buffer poll: off
"""


@pytest.fixture
def wiz(isolated_page):
    page = isolated_page
    page.set_content('<!doctype html><html><head><meta charset="utf-8"><style>.modal{display:none}'
                     '.modal.show{display:block}</style></head><body><div id="toast-container"></div>'
                     + WIZARD_HTML.read_text(encoding="utf-8") + '</body></html>')
    page.add_script_tag(content=BOOT_PRELUDE)
    page.add_script_tag(content=TEST_PRELUDE)
    page.evaluate("(a) => Object.assign(window.__answers, a)", {
        "/api/external/fields": FIELDS,
        "/api/external/vendors": {"success": True, "vendors": [{"id": 2, "name": "Some Brand", "extra": {}}]},
        "/api/locations": [{"LocationID": "SHELF-1", "Name": "Shelf", "Type": "Section"}],
        "/api/materials": {"success": True, "materials": ["PLA"]},
        "/api/filaments": {"success": True, "filaments": []},
        "/api/spool_details": _details(),
        "/api/filament_details": _details()["filament"],
        "/api/identify_scan": {"type": "prusament_new", "spool_id": "17705", "spool_hash": "abc123def0", "url": QR},
        "/api/external/search": {"success": True, "results": []},
        "/api/edit_spool_wizard": {"success": True, "spool_id": 57},
    })
    for name in ("overlay_mount.js", "inv_core.js", "ui_builder.js", "inv_details.js", "inv_cmd.js",
                 "duplicate_picker.js", "choice_validation.js", "weight_utils.js", "empty_weight_field.js",
                 "inv_wizard.js"):
        page.add_script_tag(content=(MODULES / name).read_text(encoding="utf-8"))
    page.add_script_tag(content="window.setInterval = window.__si;")
    return page


def _toasts(page):
    """The toasts drawn (the page's own showToast: most callers use its bare name, so a
    stand-in on window.showToast would miss them), with their kind."""
    return page.evaluate("""() => Array.from(document.querySelectorAll('#toast-container .toast-msg')).map((t) => {
        const kind = t.className.match(/toast-(warning|error|success|info)/);
        return { m: t.innerText, k: kind ? kind[1] : null };
    })""")


def _open_edit(page, sid=57):
    page.evaluate("(s) => { window.openEditWizard(s); }", sid)
    page.wait_for_function("() => wizardState.mode === 'edit_spool'"
                           " && document.getElementById('wiz-fil-color_name').value === 'Red'"
                           " && !document.getElementById('btn-wiz-submit').disabled")


def _scan(page, text=QR):
    page.evaluate("(t) => window.processScan(t, 'barcode')", text)
    page.wait_for_timeout(150)


def _state(page):
    return page.evaluate("""() => ({ mode: wizardState.mode, session: wizardState.session,
        comment: document.getElementById('wiz-spool-comment').value,
        button: document.getElementById('btn-wiz-submit').innerText,
        asked: !!document.getElementById('fcc-wiz-unsaved-changes') })""")


def _changed_edit(page):
    _open_edit(page)
    page.locator("#wiz-spool-comment").fill("hand note")
    assert page.evaluate("() => wizardState.isDirty") is True


def test_a_new_prusament_qr_over_a_changed_edit_asks_first(wiz):
    """T1. RED on the base: no question; the Edit reset into an Add, its Comment gone."""
    _changed_edit(wiz)
    _scan(wiz)
    st = _state(wiz)
    assert st["asked"], st
    assert wiz.evaluate("() => document.activeElement && document.activeElement.id") == "fcc-wiz-dirty-cancel"
    assert (st["mode"], st["comment"], st["button"]) == ("edit_spool", "hand note", "SAVE CHANGES"), st


@pytest.mark.parametrize("how", ["click", "enter", "escape"])
def test_keep_editing_keeps_the_edit_and_says_the_qr_was_not_added(wiz, how):
    """T2. RED on the base: already reset."""
    _changed_edit(wiz)
    session = wiz.evaluate("() => wizardState.session")
    _scan(wiz)
    wiz.wait_for_selector("#fcc-wiz-dirty-cancel")
    if how == "click":
        wiz.locator("#fcc-wiz-dirty-cancel").click()
    elif how == "enter":
        wiz.keyboard.press("Enter")
    else:
        wiz.keyboard.press("Escape")
    wiz.wait_for_timeout(100)
    st = _state(wiz)
    assert not st["asked"]
    assert (st["mode"], st["comment"], st["button"], st["session"]) == ("edit_spool", "hand note", "SAVE CHANGES", session)
    toasts = _toasts(wiz)
    assert any("Kept the wizard as it was" in t["m"] and t["k"] == "warning" for t in toasts), toasts
    logs = [p for p in wiz.evaluate("window.__posts") if p["url"].startswith("/api/log_event")]
    assert len(logs) == 1 and "Kept the wizard as it was" in logs[0]["body"]["msg"], logs


def test_discard_starts_the_add_with_the_qr_in_its_spool_box(wiz):
    """T3, with the arming on: a mouse click on Discard at once does nothing, after the
    700 ms it starts over, and the QR goes into Spool 1."""
    wiz.evaluate("() => { delete window.fccQuestionArmMs; }")
    _changed_edit(wiz)
    _scan(wiz)
    wiz.wait_for_selector("#fcc-wiz-dirty-confirm")
    wiz.locator("#fcc-wiz-dirty-confirm").click()
    wiz.wait_for_timeout(50)
    assert _state(wiz)["asked"]                      # the first click waited out the double click
    wiz.wait_for_timeout(750)
    wiz.locator("#fcc-wiz-dirty-confirm").click()
    wiz.wait_for_function("() => wizardState.mode === 'manual'")
    wiz.wait_for_timeout(150)
    st = _state(wiz)
    assert not st["asked"] and st["comment"] == "" and st["button"] == "CREATE INVENTORY", st
    assert wiz.locator("[data-spool-row-idx='0'] input").input_value() == QR


def test_an_unchanged_edit_starts_over_with_no_question(wiz):
    """T4, a pin (green on the base): nothing to lose, nothing asked."""
    _open_edit(wiz)
    _scan(wiz)
    wiz.wait_for_function("() => wizardState.mode === 'manual'")
    assert not _state(wiz)["asked"]


def test_a_changed_add_takes_the_qr_into_an_empty_spool_box(wiz):
    """T5. RED on the base: the name typed was wiped and the session started over."""
    wiz.evaluate("() => window.openWizardModal()")
    wiz.wait_for_function("() => wizardState.mode === 'manual' && !!document.querySelector('[data-spool-row-idx]')")
    wiz.evaluate("() => wizardSelectType('manual')")
    wiz.locator("#wiz-fil-color_name").fill("Test Red")
    session = wiz.evaluate("() => wizardState.session")
    _scan(wiz)
    st = _state(wiz)
    assert not st["asked"] and st["session"] == session, st
    assert wiz.locator("#wiz-fil-color_name").input_value() == "Test Red"
    assert wiz.locator("[data-spool-row-idx='0'] input").input_value() == QR
    assert any("scanning it into Spool 1" in t["m"] for t in _toasts(wiz))


def test_a_save_on_its_way_is_never_started_over(wiz):
    """T7. RED on the base: the reset happened under the Save."""
    _changed_edit(wiz)
    wiz.evaluate("() => { window.__answers['/api/edit_spool_wizard'] = '__hold__'; }")
    wiz.locator("#btn-wiz-submit").click()
    wiz.wait_for_function("() => !!(window.__held && window.__held['/api/edit_spool_wizard'])")
    _scan(wiz)
    st = _state(wiz)
    assert not st["asked"] and st["mode"] == "edit_spool" and st["comment"] == "hand note", st
    assert any("The wizard is saving" in t["m"] and t["k"] == "warning" for t in _toasts(wiz))
    wiz.evaluate("() => window.__held['/api/edit_spool_wizard']({ success: true, spool_id: 57 })")
    wiz.wait_for_function("() => wizardState.saving == null")


def test_the_question_holds_scans_and_a_cancel_keeps_editing(wiz):
    """T8. RED on the base: no question; every scan went on behind the wizard."""
    _changed_edit(wiz)
    _scan(wiz)
    wiz.wait_for_selector(QUESTION)
    posted = len([p for p in wiz.evaluate("window.__posts") if p["url"] == "/api/identify_scan"])
    _scan(wiz, "LOC:SHELF-1")
    assert len([p for p in wiz.evaluate("window.__posts") if p["url"] == "/api/identify_scan"]) == posted
    assert "Ignored: LOC:SHELF-1" in wiz.locator("#fcc-wiz-dirty-flash").inner_text()
    _scan(wiz, "CMD:CANCEL")
    wiz.wait_for_timeout(100)
    st = _state(wiz)
    assert not st["asked"] and st["mode"] == "edit_spool" and st["comment"] == "hand note", st


def test_the_legacy_pickers_add_new_spool_asks_too(wiz):
    """T9. RED on the base: the edit reset, and its close retargeted to filament #7."""
    _changed_edit(wiz)
    wiz.evaluate("""() => window.showLegacySpoolPicker({ legacy_id: '120', candidates: [
        { id: 134, remaining_weight: 800, location: '', archived: false, filament_id: 7,
          filament_name: 'Red', material: 'PLA', vendor_name: 'Some Brand', display: '#134' }] })""")
    wiz.wait_for_selector("#fcc-legacy-picker-addnew")
    wiz.locator("#fcc-legacy-picker-addnew").click()
    wiz.wait_for_selector(QUESTION)
    wiz.locator("#fcc-wiz-dirty-cancel").click()
    wiz.wait_for_timeout(100)
    st = _state(wiz)
    assert (st["mode"], st["comment"]) == ("edit_spool", "hand note"), st
    assert wiz.evaluate("() => wizardState.returnToFilamentId") is None


def test_a_late_prefill_lands_nowhere(wiz):
    """T10. An Edit whose spool read is still out, started over by a QR (nothing changed
    yet), then the read lands: the Add stays an Add. RED on the base: the late prefill
    turned the Add back into an edit of #57."""
    wiz.evaluate("() => { window.__answers['/api/spool_details'] = '__hold__'; }")
    wiz.evaluate("() => { window.openEditWizard(57); }")
    wiz.wait_for_function("() => !!(window.__held && window.__held['/api/spool_details'])")
    _scan(wiz)
    wiz.wait_for_function("() => wizardState.mode === 'manual'")
    wiz.evaluate("(d) => window.__held['/api/spool_details'](d)", _details())
    wiz.wait_for_timeout(150)
    assert wiz.evaluate("() => wizardState.mode") == "manual"
    assert wiz.evaluate("() => wizardState.editSpoolId") in (None, 57)   # the reset may keep the id
    assert wiz.locator("#btn-wiz-submit").inner_text() == "CREATE INVENTORY"


def test_the_close_guard_still_asks_and_a_dropped_hide_never_leaks(wiz):
    """T11 and the grounding's C18: Discard & Close closes; a hide Bootstrap drops leaves
    no bypass set for the person's next close."""
    _changed_edit(wiz)
    wiz.evaluate("() => window.modals.wizardModal.hide()")
    wiz.wait_for_selector("#fcc-wiz-dirty-confirm")
    wiz.evaluate("() => { window.__dropNextHide = true; }")
    wiz.locator("#fcc-wiz-dirty-confirm").click()
    wiz.wait_for_timeout(50)
    assert wiz.evaluate("window.__droppedHides") == 1
    assert wiz.evaluate("() => wizardState.forceClose") is False
    wiz.locator("#wiz-spool-comment").fill("another note")
    wiz.evaluate("() => window.modals.wizardModal.hide()")
    wiz.wait_for_timeout(50)
    assert _state(wiz)["asked"]


def test_a_stale_blur_change_never_makes_a_new_session_changed(wiz):
    """The grounding's 66.4 step 9: a text box's blur `change` that comes after the reset
    is no edit of the new session. RED on the base: isDirty."""
    wiz.evaluate("() => window.openWizardModal()")
    wiz.wait_for_function("() => wizardState.mode === 'manual'")
    wiz.evaluate("() => { wizardState.isDirty = false; const c = document.getElementById('wiz-spool-comment');"
                 " c.dispatchEvent(new Event('change', { bubbles: true })); }")
    assert wiz.evaluate("() => wizardState.isDirty") is False
    wiz.locator("#wiz-spool-comment").fill("typed")
    assert wiz.evaluate("() => wizardState.isDirty") is True


def test_a_list_read_that_fails_never_stops_the_open(wiz):
    """openWizardModal rejected when a list read failed, and the opener stopped half-way."""
    wiz.evaluate("() => { window.__answers['/api/locations'] = '__reject__'; }")
    ok = wiz.evaluate("() => window.openWizardModal()")
    assert ok is True
    assert wiz.evaluate("() => wizardState.mode") == "manual"


def test_the_dashboard_holds_the_weight_fix_while_the_spool_is_open_in_edit_spool(wiz):
    """The grounding's C5. RED on the base: the Apply was offered, and the wizard's next
    Save wrote the old weights back over it."""
    _open_edit(wiz)
    res = {"type": "prusament_matched", "spool_id": 57, "filament_id": 7, "filament_name": "Red",
           "filled": [], "conflicts": [],
           "spool_weight": {"rows": [{"label": "Total (filament)", "current": 1000, "scanned": 1012}],
                            "updates": {"initial_weight": 1012}, "remaining": {"current": 500, "new": 512}, "used": 500}}
    wiz.evaluate("(r) => window.promptPrusamentMatched(r)", res)
    wiz.wait_for_selector("#fcc-prusament-matched-overlay")
    assert wiz.locator("#pm-update-weights").count() == 0
    assert "#57 is open in the wizard" in wiz.locator("#pm-weight-section").inner_text()
    assert any("#57 is open in the wizard" in t["m"] and t["k"] == "warning" for t in _toasts(wiz))
    # Another spool's correction is offered as before.
    wiz.evaluate("() => document.getElementById('pm-done').click()")
    wiz.evaluate("(r) => window.promptPrusamentMatched(Object.assign({}, r, { spool_id: 58 }))", res)
    wiz.wait_for_selector("#pm-update-weights")
