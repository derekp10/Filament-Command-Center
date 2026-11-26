"""Group 66.7, the wizard: a filament's Spool Wt that only shows its brand's empty
weight is marked as the brand's, and Edit Spool never saves it as the filament's own.

Edit Spool fills the filament's Spool Wt box with the filament's own empty weight,
else its brand's (the cascade), unmarked: the brand's value looked like the
filament's own, and every Edit Spool Save wrote it as the filament's own (whatever
was edited), so the filament stopped following its brand. Dev's data, 2026-11-24: 10
filaments that only inherit their brand's weight, most of them stored as 0, which
the cascade reads as none.

The rules now (`wizardState.filEmptyWeightFrom`, `wizardFilEmptyWeightIsInherited`):
  - while the box shows the brand's weight and the person hasn't typed in it, a
    "↩ from vendor" badge sits beside its label (Derek's D2 (a), the spool box's look)
    and the closed Physical Specs summary says so ("167g tare ↩ from vendor");
  - Edit Spool's Save leaves such a value out, so the filament keeps having none of
    its own; a typed value (167 too), an emptied box (null, Group 54.5's clear) and
    an own value go as before;
  - the vendor push (a manufacturer saved or made while the wizard is open) is code,
    never the person's edit: it fills only an empty or marked box, marked;
  - a marked box follows the manufacturer the Vendor box holds (a pick included);
  - a create still saves what the box shows as the new filament's own (the
    cross-check's C15: the wizard's create keeps today's outcome).

Hermetic and page-level, on the Group 58.5 harness, so it runs under --offline. Each
case marked RED fails on 1969bb4a for the reason it names.
"""
from __future__ import annotations

import pytest

from test_wizard_label_status_58_5 import _save
from test_wizard_native_clear_54_5 import _open_new_filament, _touched, _value
from test_wizard_price_mark_54_8 import _badge, wiz  # noqa: F401
from test_wizard_vendor_66_1 import _brand, _open_edit_with, _saved

EDIT = "/api/edit_spool_wizard"
CREATE = "/api/create_inventory_wizard"
FIL = "#wiz-fil-empty_weight"
FIL_BADGE = "#wiz-fil-empty-inherited-badge"
EMPTY = "#wiz-spool-empty_weight"
EMPTY_BADGE = "#wiz-spool-empty-inherited-badge"
PHYSICAL = 'button.fcc-wiz-section-toggle[data-bs-target="#wiz-fil-physical-panel"] .fcc-wiz-section-summary'


def _open_edit(page, **kw):
    """Edit Spool, the list answering the filament's own brand (#2)."""
    vendor_wt = kw.get("vendor_wt")
    _open_edit_with(page, {"success": True, "vendors": [_brand(2, weight=vendor_wt)]}, **kw)


def _physical(page):
    page.evaluate("() => window.wizardRefreshSectionSummary('wiz-fil-physical-panel')")
    return page.evaluate("(s) => document.querySelector(s).textContent.trim()", PHYSICAL)


def _fil_weight(body):
    part = body["filament_data"]
    return part["spool_weight"] if "spool_weight" in part else "<missing>"


# --- what Edit Spool's Save sends -----------------------------------------------------------

@pytest.mark.parametrize("fil_wt", [None, 0.0], ids=["none", "stored-0"])
def test_edit_spool_never_saves_the_brands_weight_as_the_filaments(wiz, fil_wt):
    """The filament has none of its own (dev's usual case stores 0); its brand's 167
    shows in the box. RED: every Save wrote 167 as the filament's own."""
    _open_edit(wiz, spool_wt=None, fil_wt=fil_wt, vendor_wt=167.0)
    assert _value(wiz, FIL) == "167"
    assert _fil_weight(_save(wiz, EDIT)) == "<missing>"


def test_a_spool_with_its_own_weight_doesnt_give_it_to_the_filament(wiz):
    """The spool's own 196 stays the spool's; the filament box shows the brand's 167
    and isn't saved. RED: 167 written as the filament's own."""
    _open_edit(wiz, spool_wt=196.0, fil_wt=None, vendor_wt=167.0)
    body = _save(wiz, EDIT)
    assert _fil_weight(body) == "<missing>"
    assert body["spool_data"]["spool_weight"] == 196


@pytest.mark.parametrize("typed", ["170", "167"])
def test_a_typed_weight_is_the_filaments_own(wiz, typed):
    """A pin: the person's value goes, the brand's own 167 too (typed, it is theirs)."""
    _open_edit(wiz, spool_wt=None, fil_wt=None, vendor_wt=167.0)
    wiz.locator(FIL).fill(typed)
    assert _fil_weight(_save(wiz, EDIT)) == float(typed)


def test_an_emptied_box_is_still_a_clear(wiz):
    """A pin (Group 54.5): emptied, the box sends null, and the spool box shows the
    brand's weight as the brand's."""
    _open_edit(wiz, spool_wt=None, fil_wt=None, vendor_wt=167.0)
    wiz.locator(FIL).fill("")
    assert (_value(wiz, EMPTY), _badge(wiz, EMPTY_BADGE)) == ("167", True)
    assert wiz.evaluate("() => wizardState.spoolEmptyWeightFrom") == "vendor"
    assert _fil_weight(_save(wiz, EDIT)) is None


def test_the_filaments_own_weight_goes_as_before(wiz):
    """A pin: an own 200, untouched, is sent as it is."""
    _open_edit(wiz, spool_wt=None, fil_wt=200.0, vendor_wt=167.0)
    assert _fil_weight(_save(wiz, EDIT)) == 200


def test_a_weight_typed_over_the_brands_reaches_the_spool_box_at_once(wiz):
    """A pin against reading the marks before the touch is noted: both boxes show the
    brand's 167; one `input` of 170 in the filament box makes the spool box "170 ↩ from
    filament" (the filament's own now), not the brand's 167."""
    _open_edit(wiz, spool_wt=None, fil_wt=None, vendor_wt=167.0)
    wiz.locator(FIL).fill("170")
    assert _value(wiz, EMPTY) == "170"
    assert wiz.evaluate("() => wizardState.spoolEmptyWeightFrom") == "filament"


# --- the vendor push is code ------------------------------------------------------------------

def test_a_brands_weight_saved_meanwhile_fills_the_box_as_the_brands(wiz):
    """The filament stores 0 and its brand had no weight; the brand is saved at 167.
    The box shows 167 marked, and Save leaves it out. RED: the push was a synthetic
    `input`, read as the person's edit, and Save wrote 167 as the filament's own."""
    _open_edit(wiz, spool_wt=None, fil_wt=0.0, vendor_wt=None)
    assert _value(wiz, FIL) == ""
    _saved(wiz, _brand(2, weight=167.0))
    assert _value(wiz, FIL) == "167"
    assert "fil:spool_weight" not in _touched(wiz)
    assert _badge(wiz, FIL_BADGE) is True
    assert _fil_weight(_save(wiz, EDIT)) == "<missing>"


def test_picking_another_brand_moves_an_inherited_weight_with_it(wiz):
    """Claude's call, the mark's truth: the box shows brand #2's 167 (marked); the person
    picks #3 (180) in the Vendor box. Both boxes show 180 as the brand's, and Save sends
    #3 and no filament weight. RED: the box kept #2's 167, and Save wrote it as the
    filament's own."""
    _open_edit_with(wiz, {"success": True, "vendors": [_brand(2, weight=167.0),
                                                       _brand(3, name="Other Brand", weight=180.0)]},
                    spool_wt=None, fil_wt=None, vendor_wt=167.0)
    wiz.locator("#wiz-fil-vendor-search").click()
    wiz.locator('#dropdown-vendor .autocomplete-option[data-value="3"]').click()
    assert (_value(wiz, FIL), _badge(wiz, FIL_BADGE)) == ("180", True)
    assert (_value(wiz, EMPTY), _badge(wiz, EMPTY_BADGE)) == ("180", True)
    body = _save(wiz, EDIT)
    assert body["filament_data"]["vendor_id"] == 3
    assert _fil_weight(body) == "<missing>"


def test_a_create_still_saves_the_brands_weight_as_the_new_filaments(wiz):
    """A pin (the cross-check's C15): New Manual Form with a brand at 180 and the box
    left empty; the create's cross-inherit gives the new filament 180."""
    wiz.evaluate("(v) => { window.__answers['/api/external/vendors'] = { success: true, vendors: [v] }; }",
                 _brand(2, weight=180.0))
    _open_new_filament(wiz)
    wiz.evaluate("() => window.wizardComboboxSet('wiz-fil-vendor-search', 'wiz-fil-vendor-sel', '2', 'Some Brand')")
    assert _fil_weight(_save(wiz, CREATE)) == 180


# --- the mark -------------------------------------------------------------------------------

def test_the_mark_shows_exactly_while_the_box_shows_the_brands_weight(wiz):
    """RED: there was no mark (no such badge)."""
    _open_edit(wiz, spool_wt=None, fil_wt=None, vendor_wt=167.0)
    assert _badge(wiz, FIL_BADGE) is True
    assert wiz.locator(FIL_BADGE).inner_text().strip() == "↩ from vendor"
    wiz.locator(FIL).fill("170")
    assert _badge(wiz, FIL_BADGE) is False
    # A new session starts unmarked.
    wiz.evaluate("() => { window.openWizardModal(); }")
    wiz.locator("#fcc-wiz-dirty-confirm").click()
    wiz.wait_for_function("() => wizardState.mode === 'manual'")
    assert _badge(wiz, FIL_BADGE) is False


def test_an_own_weight_has_no_mark(wiz):
    _open_edit(wiz, spool_wt=None, fil_wt=200.0, vendor_wt=167.0)
    assert _badge(wiz, FIL_BADGE) is False


def test_the_physical_specs_summary_says_whose_weight_it_is(wiz):
    """The closed section's summary marks the brand's weight, as the Weight & Scale one
    does the spool's (Group 54 review, L1). RED: "167g tare", unmarked."""
    _open_edit(wiz, spool_wt=None, fil_wt=None, vendor_wt=167.0)
    assert _physical(wiz).endswith("167g tare ↩ from vendor"), _physical(wiz)
    wiz.locator(FIL).fill("170")
    assert _physical(wiz).endswith("170g tare"), _physical(wiz)
