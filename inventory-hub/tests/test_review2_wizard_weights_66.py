"""Review round 2 of Group 66, the wizard's empty weights (Q2-01, Q2-02, Q2-03 / Q5-03,
Q2-04, Q4-05).

  - Q2-01: wizardReset drew the plain Add's spool box from the brand the last session's
    Vendor box still held (it cleared that box after redrawing): after an Edit Spool of a
    filament on a 167 g brand, the title bar's ADD opened with 167 "↩ from vendor" in the
    spool box, and Create saved it as the new spool's and the new filament's own.
  - Q2-02: in Edit Spool, a key typed in the Vendor box that matched no manufacturer
    followed Generic and emptied the inherited boxes for good; the brand then picked never
    filled them, and Save's cross-inherit wrote its weight as the filament's own.
  - Q2-03 / Q5-03: Edit Spool of a filament with none of its own whose brand gives none: a
    brand picked over the empty box left it empty, and Save wrote that brand's weight as the
    filament's own (older than the group; its Done-when says no window does that).
  - Q2-04: in a create, the badge's words said the filament keeps none of its own, while
    Create saves it as the new filament's own (C15).
  - Q4-05: a manufacturer made with the ➕ and picked into the form wasn't an unsaved change.

Hermetic and page-level, on the Group 58.5 harness, so it runs under --offline. Each case
marked RED fails on f09bdc9c for the reason it names.
"""
from __future__ import annotations

import pytest

from test_wizard_label_status_58_5 import _save
from test_wizard_native_clear_54_5 import _touched, _value
from test_wizard_price_mark_54_8 import _badge, wiz  # noqa: F401
from test_wizard_vendor_66_1 import _brand, _open_edit_with, _saved

EDIT = "/api/edit_spool_wizard"
CREATE = "/api/create_inventory_wizard"
SEARCH = "#wiz-fil-vendor-search"
FIL = "#wiz-fil-empty_weight"
FIL_BADGE = "#wiz-fil-empty-inherited-badge"
EMPTY = "#wiz-spool-empty_weight"
EMPTY_BADGE = "#wiz-spool-empty-inherited-badge"
TWO_BRANDS = {"success": True, "vendors": [_brand(2, weight=167.0), _brand(3, name="Other Brand", weight=200.0)]}


def _got(part, key):
    return part[key] if key in part else "<missing>"


def _closed(page):
    """The wizard closed (its window no longer shown), as the ✕ leaves it."""
    page.evaluate("() => { document.getElementById('wizardModal').classList.remove('show'); }")


# --- Q2-01: a plain Add after a session that held a brand ------------------------------------

def test_a_plain_add_after_an_edit_spool_shows_no_brand_weight(wiz):
    """RED: the spool box opened at 167 "↩ from vendor" (the Edit Spool's brand), and Create
    saved 167 as the new spool's and the new filament's own empty weight."""
    _open_edit_with(wiz, {"success": True, "vendors": [_brand(2, weight=167.0)]},
                    spool_wt=None, fil_wt=None, vendor_wt=167.0)
    assert _value(wiz, EMPTY) == "167"
    _closed(wiz)
    wiz.evaluate("() => { window.openWizardModal(); }")
    wiz.wait_for_function("() => wizardState.mode === 'manual' && !!document.getElementById('wiz_fil_ef_needs_label_print')")
    assert (_value(wiz, EMPTY), _badge(wiz, EMPTY_BADGE)) == ("", False)
    assert (_value(wiz, "#wiz-fil-vendor-sel"), _value(wiz, SEARCH)) == ("", "")
    wiz.locator("#wiz-fil-color_name").fill("Test Red")
    wiz.locator("#wiz-fil-material").fill("PLA")
    body = _save(wiz, CREATE)
    assert _got(body["spool_data"], "spool_weight") == "<missing>"
    assert _got(body["filament_data"], "spool_weight") == "<missing>"


# --- Q2-02: typing in the Vendor box keeps the boxes following the brand -----------------------

@pytest.mark.parametrize("typed, vid, weight", [
    ("Some Brand", 2, "167"), ("Other Brand", 3, "200"), ("Oth", 3, "200"),
], ids=["retyped", "another", "filter-then-enter"])
def test_a_brand_typed_in_edit_spool_keeps_both_boxes_the_brands(wiz, typed, vid, weight):
    """RED: the first key that matched no manufacturer emptied both boxes and took their
    marks; the brand typed after never filled them, and Save wrote its weight (167 or 200)
    as the filament's own."""
    _open_edit_with(wiz, TWO_BRANDS, spool_wt=None, fil_wt=None, vendor_wt=167.0)
    wiz.locator(SEARCH).click()
    wiz.keyboard.press("Control+a")
    wiz.keyboard.type(typed, delay=30)
    wiz.keyboard.press("Enter")
    assert (_value(wiz, FIL), _badge(wiz, FIL_BADGE)) == (weight, True)
    assert (_value(wiz, EMPTY), _badge(wiz, EMPTY_BADGE)) == (weight, True)
    assert "fil:spool_weight" not in _touched(wiz)
    body = _save(wiz, EDIT)
    assert body["filament_data"]["vendor_id"] == vid
    assert _got(body["filament_data"], "spool_weight") == "<missing>"
    assert _got(body["spool_data"], "spool_weight") == "<missing>"


# --- Q2-03 / Q5-03: a brand picked over an empty box ----------------------------------------------

@pytest.mark.parametrize("fil_wt", [None, 0.0], ids=["none", "stored-0"])
def test_a_brand_picked_over_an_empty_box_is_the_brands_and_isnt_saved(wiz, fil_wt):
    """The filament has none of its own and its brand gives none, so Spool Wt is empty;
    the person picks a brand with 200 g. RED: the box stayed empty, and Save's cross-inherit
    wrote 200 as the filament's own."""
    _open_edit_with(wiz, {"success": True, "vendors": [_brand(2), _brand(3, name="Other Brand", weight=200.0)]},
                    spool_wt=None, fil_wt=fil_wt, vendor_wt=None)
    assert (_value(wiz, FIL), _badge(wiz, FIL_BADGE)) == ("", False)
    wiz.locator(SEARCH).click()
    wiz.locator('#dropdown-vendor .autocomplete-option[data-value="3"]').click()
    assert (_value(wiz, FIL), _badge(wiz, FIL_BADGE)) == ("200", True)
    body = _save(wiz, EDIT)
    assert body["filament_data"]["vendor_id"] == 3
    assert _got(body["filament_data"], "spool_weight") == "<missing>"


def test_the_spools_own_weight_still_goes_to_a_filament_with_none(wiz):
    """A pin (the cross-inherit's old rule, where the brand gives nothing): the spool's own
    196 goes to its filament, which has none of its own."""
    _open_edit_with(wiz, {"success": True, "vendors": [_brand(2)]}, spool_wt=196.0, fil_wt=None, vendor_wt=None)
    assert _got(_save(wiz, EDIT)["filament_data"], "spool_weight") == 196


def test_an_emptied_box_is_still_a_clear(wiz):
    """A pin (Group 54.5): the person empties the filament box; Save sends null."""
    _open_edit_with(wiz, {"success": True, "vendors": [_brand(2, weight=167.0)]},
                    spool_wt=None, fil_wt=None, vendor_wt=167.0)
    wiz.locator(FIL).fill("")
    assert _got(_save(wiz, EDIT)["filament_data"], "spool_weight") is None


# --- Q2-04: the badge's words in a create ------------------------------------------------------

def test_a_creates_badge_says_create_saves_the_brands_weight(wiz):
    """RED: the words said the new filament keeps none of its own, and Create saved 180 as
    its own (C15)."""
    wiz.evaluate("() => window.openWizardModal()")
    wiz.wait_for_function("() => !!document.getElementById('wiz_fil_ef_needs_label_print')")
    wiz.evaluate("() => wizardSelectType('manual')")
    wiz.locator("#wiz-fil-color_name").fill("Test Red")
    wiz.locator("#wiz-fil-material").fill("PLA")
    _saved(wiz, _brand(5, name="New Brand", weight=180.0), created=True)
    assert (_value(wiz, FIL), _badge(wiz, FIL_BADGE)) == ("180", True)
    title = wiz.locator(FIL_BADGE).get_attribute("title")
    assert "Create saves it as the new filament's own" in title, title
    assert "none of its own" not in title
    assert _got(_save(wiz, CREATE)["filament_data"], "spool_weight") == 180


def test_edit_spools_badge_says_the_filament_has_none_of_its_own(wiz):
    """A pin: Edit Spool's words, where Save leaves the brand's weight out."""
    _open_edit_with(wiz, {"success": True, "vendors": [_brand(2, weight=167.0)]},
                    spool_wt=None, fil_wt=None, vendor_wt=167.0)
    assert "this filament has none of its own" in wiz.locator(FIL_BADGE).get_attribute("title")


# --- Q4-05: a manufacturer made with the ➕ is a change ------------------------------------------

def test_a_manufacturer_made_with_the_plus_is_an_unsaved_change(wiz):
    """RED: the form stayed unchanged, so an opener started over unasked and the brand the
    person made for this filament was dropped."""
    _open_edit_with(wiz, {"success": True, "vendors": [_brand(2, weight=167.0)]},
                    spool_wt=None, fil_wt=None, vendor_wt=167.0)
    _saved(wiz, _brand(5, name="New Brand", weight=180.0), created=True)
    assert _value(wiz, "#wiz-fil-vendor-sel") == "5"
    assert wiz.evaluate("() => wizardState.isDirty") is True
    assert "fil:spool_weight" not in _touched(wiz)
    wiz.evaluate("() => { window.openWizardModal(); }")
    wiz.wait_for_selector("#fcc-wiz-dirty-confirm")
    assert wiz.evaluate("() => wizardState.mode") == "edit_spool"


def test_a_manufacturer_saved_over_the_wizard_is_no_change(wiz):
    """A pin: a save of the held manufacturer (its weight pushed in) is code, no change."""
    _open_edit_with(wiz, {"success": True, "vendors": [_brand(2, weight=167.0)]},
                    spool_wt=None, fil_wt=None, vendor_wt=167.0)
    _saved(wiz, _brand(2, weight=170.0))
    assert _value(wiz, FIL) == "170"
    assert wiz.evaluate("() => wizardState.isDirty") is False
