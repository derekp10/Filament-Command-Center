"""Group 66, review round 1, R3-03: while a spool is open in Edit Spool, a matched Prusament
scan of it writes (blank temps filled, its canonical link) and offers more (Prusament's
temps, its weights). The wizard's next Save wrote its own old values back: a clear for
every blank max-temp box, the link boxes as drawn. Now a max temp is cleared only when the
person emptied it, the link boxes go out only when they changed since the edit opened, and
the scan's temperature update waits with its weights (C5's hold).

Hermetic, on Group 66.2's harness (the real wizard and inv_cmd.js). Each case fails on the
commit before the fix for the reason it names.
"""
from __future__ import annotations

from test_wizard_prusament_guard_66_2 import _details, _open_edit, _toasts, wiz  # noqa: F401

EDIT = "/api/edit_spool_wizard"


def _save(page):
    page.locator("#btn-wiz-submit").click()
    page.wait_for_function("(u) => window.__posts.some((p) => p.url === u)", arg=EDIT)
    return page.evaluate("(u) => window.__posts.filter((p) => p.url === u).pop().body", EDIT)


def _edit_a_comment(page):
    page.evaluate("() => { const b = document.getElementById('wiz-spool-comment'); b.value = 'note';"
                  " b.dispatchEvent(new Event('input', { bubbles: true })); }")


def test_blank_max_temps_nobody_touched_are_not_cleared(wiz):
    """RED: a Save of a comment sent a clear for both blank max-temp boxes."""
    _open_edit(wiz)
    _edit_a_comment(wiz)
    extra = _save(wiz)["filament_data"].get("extra") or {}
    assert "nozzle_temp_max" not in extra and "bed_temp_max" not in extra, extra


def test_an_emptied_max_temp_is_still_a_clear(wiz):
    """A pin: the person's own clear goes out."""
    d = _details()
    d["filament"]["extra"] = {"nozzle_temp_max": '"230"'}
    wiz.evaluate("(d) => { window.__answers['/api/spool_details'] = d; }", d)
    _open_edit(wiz)
    assert wiz.locator("#wiz-fil-nozzle_temp_max").input_value() == "230"
    wiz.locator("#wiz-fil-nozzle_temp_max").fill("")
    extra = _save(wiz)["filament_data"].get("extra") or {}
    assert extra.get("nozzle_temp_max") == "__FCC_DELETE_EXTRA__", extra


def test_link_boxes_nobody_changed_are_not_sent(wiz):
    """RED: a Save of a comment sent the drawn link (or a clear of a blank one), over a link
    the dashboard's scan of this QR saved meanwhile."""
    d = _details()
    d["extra"] = {"product_url": '"https://prusament.com/spool/?spoolId=abc123def0"'}
    wiz.evaluate("(d) => { window.__answers['/api/spool_details'] = d; }", d)
    _open_edit(wiz)
    _edit_a_comment(wiz)
    extra = _save(wiz)["spool_data"].get("extra") or {}
    assert "product_url" not in extra and "purchase_url" not in extra, extra


def test_a_link_box_the_person_changed_is_sent(wiz):
    """A pin: an emptied link box is a clear, a typed one goes as typed."""
    d = _details()
    d["extra"] = {"product_url": '"https://example.com/a"'}
    wiz.evaluate("(d) => { window.__answers['/api/spool_details'] = d; }", d)
    _open_edit(wiz)
    wiz.locator("#wiz-spool-product_url").fill("")
    wiz.locator("#wiz-spool-purchase_url").fill("https://example.com/shop")
    extra = _save(wiz)["spool_data"].get("extra") or {}
    assert extra.get("product_url") == "__FCC_DELETE_EXTRA__", extra
    assert extra.get("purchase_url") == "https://example.com/shop", extra


def test_the_scans_temperature_update_waits_while_the_spool_is_open(wiz):
    """C5's hold, now for the temps too. RED: "Update to Prusament's spec" was offered, and
    the wizard's next Save wrote the old temps back over it."""
    _open_edit(wiz)
    res = {"type": "prusament_matched", "spool_id": 57, "filament_id": 7, "filament_name": "Red", "filled": [],
           "conflicts": [{"field": "settings_extruder_temp", "native": True, "current": 215, "scanned": 225,
                          "label": "Nozzle (min)"}]}
    wiz.evaluate("(r) => window.promptPrusamentMatched(r)", res)
    wiz.wait_for_selector("#fcc-prusament-matched-overlay")
    assert wiz.locator("#pm-update-temps").count() == 0
    assert "#57 is open in the wizard" in wiz.locator("#pm-temp-section").inner_text()
    assert sum("#57 is open in the wizard" in t["m"] for t in _toasts(wiz)) == 1
