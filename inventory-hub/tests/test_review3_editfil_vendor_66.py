"""Review round 3 of Group 66, Edit Filament's manufacturer list and box (weights-vendor
R3-03, tests-adversary R3-04).

  - weights-vendor R3-03: round 2's Q1-03 fix takes an older list read once a newer one
    failed. The open's read, still out when a vendor is saved over the window, holds the
    list as it was BEFORE the save; taken after the re-read failed, it put the vendor's old
    record back over the one the save put in the list (the box, the pill, the note and
    Use Vendor back to the old weight). Now each record a save puts in the list is laid
    over any list from a read sent before that save.
  - tests-adversary R3-04: Q1-05's "the vendor the box held when it took the focus" had no
    test of its own (every case opened a filament already on the vendor kept).

On the shared hermetic page (tests/edit_filament_harness.py), so it runs under --offline.
Each case marked RED fails on 41c55db2 for the reason it names; the others are pins.
"""
from __future__ import annotations

import pytest

from edit_filament_harness import errors, filament, load, open_form
from test_vendor_windows_66_1_js import BRAND, SUNLU4, SUNLU35, VENDORS, _save_body, _specs, _ui, _vendor_saved

UNREAD = {"__status": 502, "__body": {"success": False, "msg": "Couldn't read the manufacturer list from Spoolman."}}


@pytest.fixture
def ef(isolated_page):
    return load(isolated_page, {"/api/vendors": VENDORS})


def _open_with_the_read_held(isolated_page):
    ef = load(isolated_page, {"/api/vendors": "__hold__"})      # the open's read: still out
    open_form(ef, filament(vendor=dict(BRAND), spool_weight=None))
    _specs(ef)
    ef.evaluate("() => { window.__openRead = window.__held['/api/vendors']; }")
    return ef


def test_the_opens_older_list_keeps_a_vendor_saved_meanwhile(isolated_page):
    """RED: the open's list, answered before the save and landing after the re-read
    failed, put Some Brand's old 180 g back (the box, the pill, Use Vendor)."""
    ef = _open_with_the_read_held(isolated_page)
    ef.evaluate("(a) => { window.__answers['/api/vendors'] = a; }", UNREAD)   # the re-read fails
    saved = dict(BRAND, empty_spool_weight=200.0)
    _vendor_saved(ef, saved)
    assert _ui(ef)["box"] == "200"
    ef.evaluate("(l) => window.__openRead({ success: true, vendors: l })", [BRAND, SUNLU4, SUNLU35])
    ef.wait_for_timeout(100)
    ui = _ui(ef)
    assert (ui["box"], ui["badge"], ui["pill"], ui["useVendor"]) == (
        "200", True, "ⓘ 200g empty", "Copy vendor default empty-spool weight (200g)"), ui
    assert errors(ef) == []


def test_a_vendor_created_meanwhile_stays_in_the_older_list(isolated_page):
    """RED: a manufacturer made over the window (the ➕) left the list when the open's older
    list was taken after the re-read failed, so its name read as unknown."""
    ef = _open_with_the_read_held(isolated_page)
    ef.evaluate("(a) => { window.__answers['/api/vendors'] = a; }", UNREAD)
    made = {"id": 50, "name": "New Brand", "empty_spool_weight": 190.0, "external_id": "", "extra": {}}
    _vendor_saved(ef, made, event="vendor:created")
    ef.evaluate("(l) => window.__openRead({ success: true, vendors: l })", [BRAND, SUNLU4, SUNLU35])
    ef.wait_for_timeout(100)
    box = ef.locator("#editfil-vendor-name")
    box.focus()
    ef.keyboard.press("Control+A")
    ef.keyboard.type("New Brand", delay=20)
    ef.keyboard.press("Enter")
    ef.wait_for_timeout(60)
    ui = _ui(ef)
    assert (ui["vendorId"], ui["isNew"]) == ("50", False), ui


def test_a_list_read_after_the_save_is_taken_as_spoolman_has_it(ef):
    """A pin: the re-read sent after the save is Spoolman's word, a change made elsewhere
    included (210 g, not the 200 g this window saved)."""
    open_form(ef, filament(vendor=dict(BRAND), spool_weight=None))
    _specs(ef)
    saved = dict(BRAND, empty_spool_weight=200.0)
    ef.evaluate("(v) => { window.__answers['/api/vendors'] = { success: true, vendors: v }; }",
                [dict(BRAND, empty_spool_weight=210.0), SUNLU4, SUNLU35])
    _vendor_saved(ef, saved)
    ef.wait_for_timeout(100)
    assert _ui(ef)["box"] == "210"


def test_the_vendor_held_at_focus_wins_a_shared_names_tie(ef):
    """tests-adversary R3-04. The person picks Sunlu #35 with the arrows on a filament of
    Some Brand, leaves the box, comes back, types part of the name and presses Enter: #35,
    the vendor the box held when it took the focus, not the first Sunlu (#4). RED with
    vendorHeldAtFocus dropped from preferValue (the filament's own, #2, isn't listed, so the
    first row won). At a person's pace: the box's blur closes its list 150 ms later (see the
    quick-return case below)."""
    open_form(ef, filament(vendor=dict(BRAND), spool_weight=150.0))
    box = ef.locator("#editfil-vendor-name")
    box.focus()
    ef.keyboard.press("Control+A")
    ef.keyboard.type("Sun", delay=40)
    ef.keyboard.press("ArrowDown")
    ef.keyboard.press("ArrowDown")
    ef.keyboard.press("Enter")
    ef.wait_for_timeout(60)
    assert _ui(ef)["vendorId"] == "35"
    ef.locator("#editfil-name").click()
    ef.wait_for_timeout(250)
    box.focus()
    ef.keyboard.press("Control+A")
    ef.keyboard.type("Sun", delay=40)
    ef.keyboard.press("Enter")
    ef.wait_for_timeout(60)
    assert (_ui(ef)["vendorId"], _ui(ef)["vendorName"]) == ("35", "Sunlu")
    assert _save_body(ef).get("vendor_id") == 35


def test_a_quick_return_to_the_box_keeps_its_list_open(ef):
    """Found while writing the case above (older than Group 66): the box's blur closes its
    list 150 ms later, so a mouse press on a row lands first; the timer still fired after the
    box took the keyboard back (Tab away and straight back), closing the list under the
    person's typing, and Enter then picked nothing: the box kept "Sun" with no manufacturer.
    RED: vendorId '' and the name 'Sun'."""
    open_form(ef, filament(vendor=dict(SUNLU35), spool_weight=150.0))
    box = ef.locator("#editfil-vendor-name")
    box.focus()
    ef.locator("#editfil-name").focus()
    box.focus()                                   # back within the 150 ms
    ef.keyboard.press("Control+A")
    ef.keyboard.type("Sun", delay=40)
    ef.keyboard.press("Enter")
    ef.wait_for_timeout(60)
    assert (_ui(ef)["vendorId"], _ui(ef)["vendorName"]) == ("35", "Sunlu")
