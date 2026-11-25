"""Group 66, review round 1: Edit Filament's fixes (R2-01, R2-02).

R2-01: Edit Filament reads three lists after it opens (materials, manufacturers, extra
fields). The window is reused, so a read of an EARLIER open that landed after the next
open drew into the next open's form: the first filament's slicer profile showed in the
second's, its close asked though nothing was changed, and a Save of the second sent the
first's profile. A late read now draws only while its open is still the open one.

R2-02: with a Save on its way, Cancel, ✕ and a click outside asked "Close without
saving?", and the edit landed after the person answered Close Anyway. Now the window
stays while it saves, and says so in a toast.

Hermetic, on the shared Edit Filament harness (tests/edit_filament_harness.py). Each case
fails on the commit before the fix for the reason it names.
"""
from __future__ import annotations

import pytest

from edit_filament_harness import FIELDS, asked, errors, filament, load, open_form, posts_to, shown


@pytest.fixture
def ef(isolated_page):
    return load(isolated_page)


def _cancel(page):
    page.locator("#editFilamentModal .modal-footer [data-bs-dismiss='modal']").click()
    page.wait_for_timeout(60)


def _toasts(page):
    return page.evaluate("() => Array.from(document.querySelectorAll('#toast-container .toast-msg'))"
                         ".map((t) => t.innerText)")


def test_a_late_read_of_an_earlier_open_draws_nothing_in_the_next(ef):
    """R2-01. RED: the second filament's form showed the first's slicer profile, its
    untouched Cancel asked, and its Save sent the first's profile."""
    ef.evaluate("() => { window.__answers['/api/external/fields'] = '__hold__'; }")
    open_form(ef, filament(id=7, name="Red", extra={"slicer_profile": "Basic PLA"}))
    _cancel(ef)
    assert not shown(ef)
    ef.evaluate("(f) => { window.__answers['/api/external/fields'] = f; }", FIELDS)
    open_form(ef, filament(id=8, name="Blue", extra={}))
    assert ef.locator("#editfil-slicer-profile").input_value() == ""
    ef.evaluate("(f) => window.__held['/api/external/fields'](f)", FIELDS)    # the first open's read
    ef.wait_for_timeout(60)
    assert ef.locator("#editfil-slicer-profile").input_value() == ""
    _cancel(ef)
    assert not asked(ef) and not shown(ef)
    assert errors(ef) == []


def test_a_late_vendor_read_of_an_earlier_open_draws_nothing(ef):
    """R2-01, the manufacturer list. The first open's list lands after the second open:
    it names another manufacturer under the second filament's manufacturer's name, and
    the first open's look-up moved the second's box onto it. RED: the box held #5, and the
    untouched second form's Cancel asked."""
    ef.evaluate("() => { window.__answers['/api/vendors'] = '__hold__'; window.__answers['/api/materials'] = '__hold__'; }")
    open_form(ef, filament(id=7, name="Red", vendor={"id": 3, "name": "Another", "extra": {}}))
    _cancel(ef)
    ef.evaluate("() => { window.__answers['/api/vendors'] = { success: true, vendors: [] };"
                " window.__answers['/api/materials'] = { success: true, materials: ['PLA'] }; }")
    open_form(ef, filament(id=8, name="Blue", vendor={"id": 2, "name": "Some Brand", "extra": {}}))
    assert ef.evaluate("() => document.getElementById('editfil-vendor-id').value") == "2"
    ef.evaluate("""() => { window.__held['/api/vendors']({ success: true, vendors: [
        { id: 5, name: 'Some Brand', extra: {} }] });
        window.__held['/api/materials']({ success: true, materials: ['PETG'] }); }""")
    ef.wait_for_timeout(60)
    assert ef.evaluate("() => document.getElementById('editfil-vendor-id').value") == "2"
    _cancel(ef)
    assert not asked(ef) and not shown(ef)


def test_a_colour_row_added_and_removed_again_is_no_change(ef):
    """R2-03. RED: Cancel asked "Close without saving?" (the rows' ids had moved on)."""
    open_form(ef, filament(multi_color_hexes="72071C,00FF00"))
    ef.locator("#editfil-tab-colors-btn").click()
    ef.locator("#editfil-add-color").click()
    ef.locator("[data-role='remove']").last.click()
    ef.wait_for_timeout(60)
    _cancel(ef)
    assert not asked(ef) and not shown(ef)


def test_keep_editing_gives_the_keyboard_back_to_its_box(ef):
    """R2-04 (older than this group). RED: the keyboard was left on the page."""
    open_form(ef, filament())
    ef.locator("#editfil-name").fill("Red (edit")
    ef.locator("#editfil-name").press("Escape")
    ef.wait_for_selector("#editfil-esc-no")
    ef.locator("#editfil-esc-no").click()
    ef.wait_for_timeout(60)
    assert ef.evaluate("() => document.activeElement && document.activeElement.id") == "editfil-name"


def test_a_refused_typed_tag_stops_the_save_and_keeps_the_window(ef):
    """R2-05. RED: Save said "No changes to save", closed the window, and the typed tag was
    gone."""
    ef.add_script_tag(path=str(__import__("edit_filament_harness").MODULES / "choice_validation.js"))
    open_form(ef, filament())
    ef.locator("#editfil-attr-input").fill("Silky")
    ef.locator("#editfil-save").click()
    ef.wait_for_timeout(100)
    assert shown(ef)
    assert ef.locator("#editfil-attr-input").input_value() == "Silky"
    assert posts_to(ef, "/api/update_filament") == []


def test_a_list_read_that_fails_never_shows_the_last_opens_manufacturer(ef):
    """R1-01. RED: the pill still said the first manufacturer's "167g empty", and its ✏️
    showed, beside the second's name."""
    sunlu = {"id": 4, "name": "Sunlu", "empty_spool_weight": 167.0, "extra": {}}
    ef.evaluate("(v) => { window.__answers['/api/vendors'] = { success: true, vendors: [v] }; }", sunlu)
    open_form(ef, filament(id=7, vendor=sunlu))
    assert "167" in ef.locator("#editfil-vendor-info").inner_text()
    _cancel(ef)
    ef.evaluate("() => { window.__answers['/api/vendors'] = { __status: 502, __body: { success: false } }; }")
    acme = {"id": 9, "name": "Acme", "extra": {}}
    open_form(ef, filament(id=8, vendor=acme))
    pill = ef.evaluate("() => { const p = document.getElementById('editfil-vendor-info');"
                       " return { shown: getComputedStyle(p).display !== 'none', text: p.innerText }; }")
    assert "167" not in pill["text"] or not pill["shown"], pill
    assert ef.evaluate("() => document.getElementById('editfil-vendor-id').value") == "9"


def test_an_old_empty_or_mixed_attribute_value_is_mended_at_save(ef):
    """R1-03. RED: '' and ['Silk', 5] went out as stored, and Spoolman 0.27 refuses the whole
    write for either."""
    for stored, sent in (("", "[]"), (["Silk", 5], '["Silk"]')):
        open_form(ef, filament(extra={"filament_attributes": stored}))
        ef.locator("#editfil-tab-advanced-btn").click()
        ef.evaluate("() => { const b = document.getElementById('editfil-product-url');"
                    " if (b) { b.value = 'https://example.com/p'; b.dispatchEvent(new Event('input', { bubbles: true })); } }")
        ef.locator("#editfil-save").click()
        ef.wait_for_function("() => !document.getElementById('editFilamentModal').classList.contains('show')")
        body = posts_to(ef, "/api/update_filament")[-1]["body"]
        assert body["data"]["extra"]["filament_attributes"] == sent, (stored, body)


def test_the_window_stays_while_its_save_is_on_its_way(ef):
    """R2-02. RED: Cancel asked "Close without saving?" over a Save on its way, and Close
    Anyway closed it before the edit landed."""
    ef.evaluate("() => { window.__answers['/api/update_filament'] = '__hold__'; }")
    open_form(ef, filament())
    ef.locator("#editfil-name").fill("Red (edited)")
    ef.locator("#editfil-save").click()
    ef.wait_for_function("() => !!(window.__held && window.__held['/api/update_filament'])")
    _cancel(ef)
    assert shown(ef) and not asked(ef)
    assert any("saving" in t.lower() for t in _toasts(ef)), _toasts(ef)
    ef.evaluate("() => window.__held['/api/update_filament']({ success: true })")
    ef.wait_for_function("() => !document.getElementById('editFilamentModal').classList.contains('show')")
    assert len(posts_to(ef, "/api/update_filament")) == 1
    assert errors(ef) == []
