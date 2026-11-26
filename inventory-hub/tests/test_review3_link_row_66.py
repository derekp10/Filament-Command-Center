"""Review round 3 of Group 66: the Prusament box's rows after a refusal or a clear
(tests-adversary R3-05 and R3-07).

  - R3-05: in Edit Spool, a different product's QR scanned over a link waiting for Save is
    refused and leaves that link as it was (round 1's R5-01), but the row showed only the
    refusal, and its ✕ (or its badge, since the walk's cae8f1f2) dropped the waiting link
    too, unsaid. Now the refusal's note says the earlier QR still links at Save, and its ✕
    goes back to that link (the box shows its QR again, "Links at Save"); a second ✕
    clears it.
  - R3-07: a cleared row (its ✕, or a badge's click) left the keyboard on the window, so
    in a batch of blind scans the next QR went the dashboard's way and asked "Unsaved
    Changes" instead of going into the row just cleared ("Click to clear this row and
    retry"). The cleared row's box now takes the keyboard.

Hermetic, on the 66.3 page harness (58.5's wizard page) and 66.2's, so it runs under
--offline. Each case marked RED fails on 41c55db2 for the reason it names.
"""
from __future__ import annotations

from test_prusament_link_page_66_3 import CANONICAL, EDIT, ROW, TEMPLATE, _open, _row, _scan, _value
from test_wizard_label_status_58_5 import _save, wizard  # noqa: F401  (the fixture)
from test_wizard_prusament_guard_66_2 import QR as ADD_QR
from test_wizard_prusament_guard_66_2 import _fresh_add, _state, wiz  # noqa: F401  (the fixture)

PRODUCT = "#wiz-spool-product_url"
BADGE = "[data-spool-row-idx='0'] .badge"
CLEAR = "[data-spool-row-idx='0'] .wiz-row-clear-btn"
OTHER_QR = "https://prusament.com/spool/17705/fff999eee8"


def _refused_over_a_link(page):
    _open(page)
    _scan(page)
    assert _row(page)["status"] == "linked-new"
    page.evaluate("(t) => { window.__answers['/api/external/search'] = { success: true, results: [t] }; }",
                  dict(TEMPLATE, color_name="Jet Black", name="Prusament PLA Jet Black"))
    _scan(page, OTHER_QR)
    row = _row(page)
    assert row["status"] == "refused", row
    assert _value(page, PRODUCT) == CANONICAL                 # the earlier link stays (R5-01)
    return row


def test_a_refusal_over_a_link_says_the_link_still_holds(wizard):  # noqa: F811
    """RED: the note said only why the new QR was refused."""
    row = _refused_over_a_link(wizard)
    assert "still links at Save" in row["note"], row
    assert row["noteShown"]


def test_its_x_goes_back_to_the_link_and_a_second_x_clears_it(wizard):  # noqa: F811
    """RED: the ✕ emptied the box and dropped the waiting link (Product Link emptied)."""
    _refused_over_a_link(wizard)
    wizard.locator(CLEAR).click()
    wizard.wait_for_timeout(60)
    row = _row(wizard)
    assert (row["status"], _value(wizard, ROW).lower()) == ("linked-new", "https://prusament.com/spool/17705/abc123def0"), row
    assert "Links at Save" in row["badge"] and "1012 g of filament" in row["note"], row
    assert _value(wizard, PRODUCT) == CANONICAL
    wizard.locator(CLEAR).click()
    wizard.wait_for_timeout(60)
    assert _row(wizard)["status"] == "empty"
    assert (_value(wizard, ROW), _value(wizard, PRODUCT)) == ("", "")


def test_the_badge_goes_back_to_the_link_too_and_save_links_it(wizard):  # noqa: F811
    """The badge's click does as its ✕; a Tab through the box checks nothing again, and
    Save links the earlier QR. RED: the badge dropped the link, and Save sent none."""
    _refused_over_a_link(wizard)
    wizard.locator(BADGE).click()
    wizard.wait_for_timeout(60)
    assert _row(wizard)["status"] == "linked-new"
    wizard.locator(ROW).focus()
    wizard.locator(ROW).press("Tab")
    wizard.wait_for_timeout(100)
    assert _row(wizard)["status"] == "linked-new"
    assert _save(wizard, EDIT)["spool_data"]["extra"]["product_url"] == CANONICAL


def test_a_refusal_with_no_link_waiting_clears_as_before(wizard):  # noqa: F811
    """A pin: with no link waiting, ✕ on a refusal empties the row, its note says nothing
    of an earlier QR."""
    _open(wizard)
    _scan(wizard, "https://example.com/not-a-spool")
    row = _row(wizard)
    assert row["status"] == "refused" and "still links" not in row["note"], row
    wizard.locator(CLEAR).click()
    wizard.wait_for_timeout(60)
    assert (_row(wizard)["status"], _value(wizard, ROW)) == ("empty", "")


def test_a_cleared_row_takes_the_keyboard_in_edit_spool(wizard):  # noqa: F811
    """RED: after the badge's click the keyboard was on the window."""
    _open(wizard)
    _scan(wizard, "https://example.com/not-a-spool")
    wizard.locator(BADGE).click()
    wizard.wait_for_timeout(60)
    assert wizard.evaluate("() => document.activeElement === document.querySelector(\"[data-spool-row-idx='0'] input\")")


def test_a_batch_retry_goes_into_the_row_just_cleared(wiz):  # noqa: F811
    """The Add wizard, three Spool boxes, two scanned, the third misread: its red badge
    clears it, and the next QR, read as a scanner types it, goes into that box. RED: the
    keyboard was on the window, the QR went the dashboard's way and asked "Unsaved
    Changes", and the box stayed empty."""
    _fresh_add(wiz)
    wiz.evaluate("""() => {
        document.getElementById('wiz-spool-qty').value = 3; wizardSyncSpoolRows();
        const ov = { initial_weight: 1000, spool_weight: 186 };
        [0, 1].forEach((i) => Object.assign(wizardState.spoolRows[i],
            { url: 'https://prusament.com/spool/1770' + i + '/abc/', status: 'ok', override: Object.assign({}, ov) }));
        wizardRenderSpoolRows(); wizardUpdateSubmitGate();
        document.getElementById('wiz-fil-color_name').value = 'Galaxy Black';
        document.getElementById('wiz-fil-material').value = 'PLA';
        wizardState.filamentLockedFromScan = true; wizardState.isDirty = true;
    }""")
    box = "[data-spool-row-idx='2'] input"
    wiz.locator(box).fill("https://example.com/misread")
    wiz.locator(box).press("Tab")
    wiz.wait_for_function("() => wizardState.spoolRows[2].status === 'error'")
    wiz.locator("[data-spool-row-idx='2'] .badge").click()
    wiz.wait_for_timeout(60)
    wiz.keyboard.type(ADD_QR, delay=5)
    wiz.keyboard.press("Enter")
    wiz.wait_for_timeout(200)
    assert not _state(wiz)["asked"]
    assert wiz.locator(box).input_value() == ADD_QR
    assert wiz.evaluate("() => wizardState.spoolRows[2].status") != "empty"
