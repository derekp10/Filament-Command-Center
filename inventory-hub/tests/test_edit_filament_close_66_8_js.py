"""Group 66.8 (i): Edit Filament asks before it closes unsaved, every way out.

Its Cancel and ✕ (data-bs-dismiss) and a click outside the dialog closed a changed form
with no question: only Escape asked, through a keydown guard of its own, while the wizard
asks on every way out. That Escape guard also stepped aside while a list was drawn, and a
vendor saved from inside the window left the vendor list drawn with its box unfocused, so
the next Escape closed a changed form unasked. And its dirty test read values code set
after the open as changes: a vendor list holding two vendors of one name (Derek's Sunlu
#4 and #35) moved the hidden vendor id when it landed, and an untouched form then asked.

Now one guard on the window's hide.bs.modal asks "Close without saving?" for every close
while the form differs from what it held when it opened; Save and Close Anyway close
without it (a flag set and cleared around the synchronous hide(), so a hide Bootstrap
drops never leaves it set); a value code sets (the late vendor list, a vendor saved over
the window) is no edit (codeSet); the Import from External panel's own controls are no
edit. Close Anyway waits out a double click (62.3) and both answers shield the next press;
the question holds scans while it is up (a bare CMD:CANCEL keeps editing).

On the shared hermetic page (tests/edit_filament_harness.py: the real modals_details.html
and modules, Bootstrap 5.3's dismiss paths in a stand-in), so it runs under --offline.
"""
from __future__ import annotations

import pytest

from edit_filament_harness import VENDOR, asked, errors, filament, load, open_form, posts_to, shown


@pytest.fixture
def ef(isolated_page):
    return load(isolated_page)


def _type_edit(page):
    page.locator("#editfil-name").fill("Red (edited)")


def _cancel(page):
    page.locator("#editFilamentModal .modal-footer [data-bs-dismiss='modal']").click()


def _x(page):
    page.locator("#editFilamentModal .modal-header [data-bs-dismiss='modal']").click()


def _outside(page):
    # The .modal's own surround (the backdrop): mousedown and click both on the .modal.
    page.mouse.click(8, 8)


DOORS = {"cancel": _cancel, "x": _x, "outside": _outside}


@pytest.mark.parametrize("door", list(DOORS))
def test_a_changed_form_asks_before_every_close(ef, door):
    """Cases 1-3. RED on the base: the window closed, the edit lost, no question."""
    open_form(ef, filament())
    _type_edit(ef)
    DOORS[door](ef)
    ef.wait_for_timeout(50)
    assert asked(ef), door
    assert shown(ef), door
    assert ef.locator("#editfil-name").input_value() == "Red (edited)"


@pytest.mark.parametrize("how", ["click", "enter", "escape"])
def test_keep_editing_keeps_the_window_and_the_edit(ef, how):
    """Case 4. RED on the base: no question to answer (Cancel closed the window)."""
    open_form(ef, filament())
    _type_edit(ef)
    _cancel(ef)
    ef.wait_for_selector("#editfil-esc-confirm #editfil-esc-no")
    if how == "click":
        ef.locator("#editfil-esc-no").click()
    elif how == "enter":
        assert ef.evaluate("() => document.activeElement && document.activeElement.id") == "editfil-esc-no"
        ef.keyboard.press("Enter")
    else:
        ef.keyboard.press("Escape")
    ef.wait_for_timeout(50)
    assert not asked(ef)
    assert shown(ef)
    assert ef.locator("#editfil-name").input_value() == "Red (edited)"


def test_close_anyway_closes_once_and_sends_nothing(ef):
    """Case 5. RED on the base: Cancel closed the window at once (no question)."""
    open_form(ef, filament())
    _type_edit(ef)
    _cancel(ef)
    ef.wait_for_selector("#editfil-esc-yes")
    ef.locator("#editfil-esc-yes").click()
    ef.wait_for_timeout(50)
    assert not asked(ef)
    assert not shown(ef)
    assert ef.evaluate("window.__posts") == []
    assert errors(ef) == []


def test_escape_in_a_box_asks_once(ef):
    """Case 6, a pin of 62.8 through the new path: one question, never two."""
    open_form(ef, filament())
    _type_edit(ef)
    ef.locator("#editfil-name").press("Escape")
    ef.wait_for_timeout(50)
    assert ef.locator("#editfil-esc-confirm").count() == 1
    assert shown(ef)


def test_escape_after_a_vendor_saved_over_the_window_still_asks(ef):
    """Case 7. RED on the base: the vendor:updated redraw left the vendor list drawn with
    its box unfocused, the Escape guard stepped aside for a 'list open', and Bootstrap
    closed the changed form unasked."""
    open_form(ef, filament())
    ef.evaluate("""(v) => document.dispatchEvent(new CustomEvent('vendor:updated',
        { detail: { id: '2', vendor: Object.assign({}, v, { name: 'Some Brand Renamed' }) } }))""", VENDOR)
    ef.locator("#editfil-tab-basic-btn").click()
    ef.locator("#editfil-comment").fill("a note")
    ef.locator("#editfil-name").focus()
    ef.keyboard.press("Escape")
    ef.wait_for_timeout(50)
    assert asked(ef)
    assert shown(ef)


def test_an_untouched_form_closes_with_no_question(ef):
    """Case 8, a pin: a guard that asked on an unchanged form would be a new trap."""
    open_form(ef, filament())
    _cancel(ef)
    ef.wait_for_timeout(50)
    assert not asked(ef) and not shown(ef)
    open_form(ef, filament())
    ef.locator("#editfil-name").press("Escape")
    ef.wait_for_timeout(50)
    assert not asked(ef) and not shown(ef)


def test_a_late_vendor_list_is_no_edit(ef):
    """Case 9. Derek's duplicated names: a filament on Sunlu #35, the list [#4 Sunlu,
    #35 Sunlu] landing after the window opened. The list moves the hidden vendor id (by
    name, the first: 66.1 keeps the id), which is code, not the person. RED on the base:
    Escape asked on an untouched form."""
    ef.evaluate("() => { window.__answers['/api/vendors'] = '__hold__'; }")
    sunlu35 = dict(VENDOR, id=35, name="Sunlu")
    open_form(ef, filament(vendor=sunlu35))
    ef.wait_for_timeout(50)     # shown.bs.modal has fired: the base took its baseline here
    ef.evaluate("""(v) => window.__held['/api/vendors']({ success: true, vendors: [
        Object.assign({}, v, { id: 4 }), v] })""", sunlu35)
    ef.wait_for_timeout(50)
    ef.locator("#editfil-name").press("Escape")
    ef.wait_for_timeout(50)
    assert not asked(ef)
    assert not shown(ef)


def test_a_vendor_renamed_over_an_untouched_form_is_no_edit(ef):
    """Case 10, a pin: red on a guard without codeSet (the name box changed by code)."""
    open_form(ef, filament())
    ef.evaluate("""(v) => document.dispatchEvent(new CustomEvent('vendor:updated',
        { detail: { id: '2', vendor: Object.assign({}, v, { name: 'Some Brand Renamed' }) } }))""", VENDOR)
    ef.wait_for_timeout(50)
    assert ef.locator("#editfil-vendor-name").input_value() == "Some Brand Renamed"
    _cancel(ef)
    ef.wait_for_timeout(50)
    assert not asked(ef) and not shown(ef)


def test_save_closes_without_the_question(ef):
    """Case 11, a pin: red on a guard without Save's bypass."""
    open_form(ef, filament())
    _type_edit(ef)
    ef.locator("#editfil-save").click()
    ef.wait_for_timeout(100)
    assert len(posts_to(ef, "/api/update_filament")) == 1
    assert not asked(ef) and not shown(ef)


def test_no_changes_to_save_closes_without_the_question(ef):
    """Case 12, a pin for the second bypass: a box changed to the same number sends
    nothing, says so, and closes."""
    open_form(ef, filament())
    ef.locator("#editfil-tab-specs-btn").click()
    ef.locator("#editfil-density").fill("1.240")
    ef.locator("#editfil-save").click()
    ef.wait_for_timeout(100)
    assert posts_to(ef, "/api/update_filament") == []
    assert "No changes to save." in ef.locator("#toast-container").inner_text()
    assert not asked(ef) and not shown(ef)


def test_a_failed_save_keeps_the_window_and_its_question(ef):
    """Case 13. RED on the base: Cancel after the failed Save closed the window."""
    ef.evaluate("() => { window.__answers['/api/update_filament'] = { success: false, msg: 'x' }; }")
    open_form(ef, filament())
    _type_edit(ef)
    ef.locator("#editfil-save").click()
    ef.wait_for_timeout(100)
    assert shown(ef)
    assert "x" in ef.locator("#editfil-error").inner_text()
    _cancel(ef)
    ef.wait_for_timeout(50)
    assert asked(ef) and shown(ef)


def test_a_search_in_the_import_panel_is_no_edit(ef):
    """Case 14, a pin for Claude's call 3: the Import from External panel's own controls
    hold no filament data."""
    open_form(ef, filament())
    ef.locator("#editfil-tab-advanced-btn").click()
    ef.evaluate("() => { const q = document.getElementById('editfil-external-query'); q.value = 'galaxy black';"
                " q.dispatchEvent(new Event('input', { bubbles: true })); }")
    _cancel(ef)
    ef.wait_for_timeout(50)
    assert not asked(ef) and not shown(ef)


def test_close_anyway_waits_out_a_double_click(ef):
    """Case 15, 62.3. A mouse click on Close Anyway at once does nothing; after the 700 ms
    it closes; a keyboard's Enter closes at once. RED on the base: Close Anyway (reached by
    Escape there) closed on the first click."""
    ef.evaluate("() => { delete window.fccQuestionArmMs; }")
    open_form(ef, filament())
    _type_edit(ef)
    _cancel(ef)
    ef.wait_for_selector("#editfil-esc-yes")
    ef.locator("#editfil-esc-yes").click()
    ef.wait_for_timeout(50)
    assert shown(ef) and asked(ef)
    ef.wait_for_timeout(750)
    ef.locator("#editfil-esc-yes").click()
    ef.wait_for_timeout(50)
    assert not shown(ef) and not asked(ef)
    # A keyboard's Enter on it does at once (its click has detail 0: no double click's).
    open_form(ef, filament())
    _type_edit(ef)
    _cancel(ef)
    ef.wait_for_function("() => document.activeElement && document.activeElement.id === 'editfil-esc-no'")
    ef.keyboard.press("Shift+Tab")
    assert ef.evaluate("() => document.activeElement.id") == "editfil-esc-yes"
    ef.keyboard.press("Enter")
    ef.wait_for_timeout(50)
    assert not shown(ef) and not asked(ef)


def test_a_dropped_hide_never_leaks_the_bypass(ef):
    """Case 16. Save's close is dropped (Bootstrap 5.3 drops a hide while the window is
    still fading in): the next person's Cancel still asks. RED on the base: no guard."""
    open_form(ef, filament())
    _type_edit(ef)
    ef.evaluate("() => { window.__dropNextHide = true; }")
    ef.locator("#editfil-save").click()
    ef.wait_for_timeout(100)
    assert ef.evaluate("window.__droppedHides") == 1
    assert shown(ef)
    ef.locator("#editfil-name").fill("Red (edited again)")
    _cancel(ef)
    ef.wait_for_timeout(50)
    assert asked(ef) and shown(ef)


def test_a_double_click_on_cancel_leaves_the_question_up(ef):
    """Case 17: the second click of a double click on Cancel lands on the question that
    the first opened, and answers nothing. RED on the base: the window closed."""
    ef.evaluate("() => { delete window.fccQuestionArmMs; }")
    open_form(ef, filament())
    _type_edit(ef)
    ef.locator("#editFilamentModal .modal-footer [data-bs-dismiss='modal']").dblclick()
    ef.wait_for_timeout(100)
    assert asked(ef) and shown(ef)
    assert ef.locator("#editfil-name").input_value() == "Red (edited)"


def test_the_question_holds_scans_and_a_cancel_keeps_editing(ef, assert_contrast):
    """C16: while it is up the question is the open question processScan brings every
    scan to (a scan acted behind it: a Prusament QR opened the wizard under it). A bare
    CMD:CANCEL keeps editing; a refused scan is said on its own line, which is readable.
    Closing it by either answer frees the scan path. RED on the base: not registered."""
    open_form(ef, filament())
    _type_edit(ef)
    _cancel(ef)
    ef.wait_for_selector("#editfil-esc-confirm")
    assert ef.evaluate("() => window._fccOpenMoveQuestion && window._fccOpenMoveQuestion.title") \
        == "Close without saving?"
    ef.evaluate("() => window._fccOpenMoveQuestion.flash('Answer the question on screen first. (Ignored: LOC:SHELF-1)')")
    question = ef.locator("#editfil-esc-confirm")
    assert "Ignored: LOC:SHELF-1" in ef.locator("#editfil-esc-flash").inner_text()
    assert_contrast(question)
    ef.evaluate("() => window._fccOpenMoveQuestion.cancel()")     # what a bare CMD:CANCEL calls
    ef.wait_for_timeout(50)
    assert not asked(ef) and shown(ef)
    assert ef.evaluate("() => window._fccOpenMoveQuestion") is None
    # Asked again and closed by Close Anyway: freed too.
    _cancel(ef)
    ef.wait_for_selector("#editfil-esc-yes")
    ef.locator("#editfil-esc-yes").click()
    ef.wait_for_timeout(50)
    assert ef.evaluate("() => window._fccOpenMoveQuestion") is None
    assert ef.evaluate("() => (window._fccOpenMoveQuestions || []).length") == 0
