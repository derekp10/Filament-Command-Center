"""Review round 3 of Group 66 (weights-vendor R3-02): the wizard's twin of Q1-05.

Round 2 made Edit Filament keep the vendor its box held when part of a name two
manufacturers share is typed and Enter pressed. The wizard's Vendor box (wizardBindCombobox)
had no such rule: typing blanks the held id (only an exact name is looked up), so Enter and
Tab took the first row of that name, the lowest id, and Edit Spool's Save moved the
filament onto it (Derek's data has three same-name pairs). Now, with no row highlighted,
Enter and Tab take the field's own item from before the typing when it is listed under the
first row's name; any other search takes the first row as before. Older than Group 66.

Hermetic, on the 54.8 wizard harness, so it runs under --offline. RED on 41c55db2: the
held id became '1' and Save sent vendor_id 1.
"""
from __future__ import annotations

import pytest

from test_wizard_label_status_58_5 import _save
from test_wizard_native_clear_54_5 import _value
from test_wizard_price_mark_54_8 import wiz  # noqa: F401  (the fixture)
from test_wizard_vendor_66_1 import _brand, _open_edit_with

EDIT = "/api/edit_spool_wizard"
SEARCH = "#wiz-fil-vendor-search"
HIDDEN = "#wiz-fil-vendor-sel"


@pytest.mark.parametrize("key", ["Enter", "Tab"])
def test_part_of_a_shared_name_keeps_the_manufacturer_the_box_held(wiz, key):
    # Two manufacturers named "Some Brand" (#1 and #2); the filament is on #2.
    _open_edit_with(wiz, {"success": True, "vendors": [_brand(1), _brand(2)]})
    assert _value(wiz, HIDDEN) == "2"
    wiz.locator(SEARCH).click()
    wiz.keyboard.press("Control+a")
    wiz.keyboard.type("Some", delay=30)
    wiz.keyboard.press(key)
    assert _value(wiz, HIDDEN) == "2"
    assert _save(wiz, EDIT)["filament_data"]["vendor_id"] == 2


def test_part_of_another_name_takes_its_first_row(wiz):
    """A pin: the tie rule changes nothing else. Part of another manufacturer's name and
    Enter takes that name's first row, as before."""
    other = {"id": 7, "name": "Other Brand", "empty_spool_weight": None, "external_id": "", "extra": {}}
    _open_edit_with(wiz, {"success": True, "vendors": [_brand(1), _brand(2), other]})
    wiz.locator(SEARCH).click()
    wiz.keyboard.press("Control+a")
    wiz.keyboard.type("Oth", delay=30)
    wiz.keyboard.press("Enter")
    assert _value(wiz, HIDDEN) == "7"


def test_an_arrowed_row_is_still_the_persons_pick(wiz):
    """A pin: the person arrows to the first Some Brand (#1) and presses Enter: #1 it is."""
    _open_edit_with(wiz, {"success": True, "vendors": [_brand(1), _brand(2)]})
    wiz.locator(SEARCH).click()
    wiz.keyboard.press("Control+a")
    wiz.keyboard.type("Some", delay=30)
    wiz.keyboard.press("ArrowDown")
    wiz.keyboard.press("Enter")
    assert _value(wiz, HIDDEN) == "1"
