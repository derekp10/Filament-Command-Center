"""Group 66.1, the wizard: its manufacturer is kept by id, and a manufacturer saved
while the wizard is open reaches it.

Derek, 2026-11-11: "you have to close out of the modals before updating the vendor
data (spool weight) gets propagated into the auto fills". The wizard heard a saved
manufacturer only when its own Vendor box held it, and then filled only an EMPTY
filament Spool Wt box: a renamed manufacturer kept its old name in the box, and a new
empty weight never reached a box that showed the old one. New Spool and Clone hide the
filament's form, so their spool box (the brand's weight, saved as the new spool's own
by L34) kept the old weight. Edit Spool picked the filament's manufacturer BY NAME,
the first in the list: Derek's data has three pairs of manufacturers sharing a name
(prod and dev, 2026-11-24), and an Edit Spool Save of a filament on Sunlu #35 moved it
onto Sunlu #4. A vendor list FCC couldn't read left the box with no id at all.

The rules now:
  - Edit Spool keeps the filament's own manufacturer by its id; only a record with no
    id is looked up by name (the lowest id). A list that couldn't be read still knows
    the filament's own manufacturer.
  - The Vendor box keeps the manufacturer it holds under a name two share: typing
    that name, then Enter or Tab, keeps it.
  - A manufacturer saved or created while the wizard is open (`vendor:updated` /
    `vendor:created`, window.wizardVendorSaved) reaches it at once: its record in the
    lists, its name in the box, the filament box that shows its weight, and a spool
    box that shows its weight; then the list is read again (a failed read keeps the
    saved record). Code fills, never the person: no box counts as typed in, and the
    wizard isn't marked changed.

Hermetic and page-level, on the Group 58.5 harness (the REAL modals_wizard.html and
modules in `isolated_page`), so it runs under --offline. Each case marked RED fails on
1969bb4a (before this commit) for the reason it names.
"""
from __future__ import annotations

import pytest

from test_wizard_label_status_58_5 import _save
from test_wizard_native_clear_54_5 import _details, _touched, _value, _vendor
from test_wizard_price_mark_54_8 import _badge, _open_clone, _open_new_spool, wiz  # noqa: F401

EDIT = "/api/edit_spool_wizard"
CREATE = "/api/create_inventory_wizard"
SEARCH = "#wiz-fil-vendor-search"
HIDDEN = "#wiz-fil-vendor-sel"
FIL = "#wiz-fil-empty_weight"
EMPTY = "#wiz-spool-empty_weight"
EMPTY_BADGE = "#wiz-spool-empty-inherited-badge"


def _brand(vid, name="Some Brand", weight=None):
    v = dict(_vendor(weight), id=vid, name=name)
    return v


def _open_edit_with(page, vendors_answer, **kw):
    """Edit Spool on spool #57 of filament #7 (its manufacturer #2), with the vendor
    list answering `vendors_answer`."""
    details = _details(**kw)
    page.evaluate("""(a) => {
        window.__answers['/api/spool_details'] = a.details;
        window.__answers['/api/external/vendors'] = a.vendors;
    }""", {"details": details, "vendors": vendors_answer})
    page.evaluate("() => { window.openEditWizard(57); }")
    page.wait_for_function("() => wizardState.mode === 'edit_spool' && wizardState.selectedFilamentId === 7"
                           " && !!document.getElementById('wiz_fil_ef_needs_label_print')"
                           " && document.getElementById('wiz-fil-color_name').value === 'Red'"
                           " && !document.getElementById('btn-wiz-submit').disabled")


def _saved(page, vendor, *, created=False, reread=None):
    """The vendor window saved (or created) `vendor`; the list read after it answers
    `reread` (default: that vendor alone)."""
    page.evaluate("""(a) => {
        window.__answers['/api/external/vendors'] = a.reread || { success: true, vendors: [a.vendor] };
        const name = a.created ? 'vendor:created' : 'vendor:updated';
        const detail = a.created ? { vendor: a.vendor } : { id: String(a.vendor.id), vendor: a.vendor };
        document.dispatchEvent(new CustomEvent(name, { detail }));
    }""", {"vendor": vendor, "created": created, "reread": reread})
    page.wait_for_timeout(250)


def _held(page):
    return page.locator(HIDDEN).input_value()


def _spool_source(page):
    return page.evaluate("() => wizardState.spoolEmptyWeightFrom")


# --- the manufacturer is kept by id --------------------------------------------------------

def test_edit_spool_keeps_the_filaments_own_manufacturer_under_a_shared_name(wiz):
    """Two manufacturers named "Some Brand" (#1 and #2), the filament on #2. RED: the
    box held #1 (the first by name), and Save moved the filament onto it."""
    _open_edit_with(wiz, {"success": True, "vendors": [_brand(1), _brand(2)]})
    assert (_value(wiz, SEARCH), _held(wiz)) == ("Some Brand", "2")
    body = _save(wiz, EDIT)
    assert body["filament_data"].get("vendor_id") is None, body["filament_data"].get("vendor_id")  # unchanged: left out (Group 66.9 review: Edit Spool sends a manufacturer only when it changed), so the filament keeps #2


def test_edit_spool_keeps_its_manufacturer_when_the_list_couldnt_be_read(wiz):
    """The vendor list's read failed (FCC's 502 since 66.1's server half). The
    filament's own manufacturer is known from its record. RED: the box held no id,
    and Save sent none."""
    _open_edit_with(wiz, {"success": False, "msg": "Couldn't read the manufacturer list from Spoolman."})
    assert (_value(wiz, SEARCH), _held(wiz)) == ("Some Brand", "2")
    body = _save(wiz, EDIT)
    assert body["filament_data"].get("vendor_id") is None, body["filament_data"].get("vendor_id")  # unchanged: left out (Group 66.9 review: Edit Spool sends a manufacturer only when it changed), so the filament keeps #2


@pytest.mark.parametrize("key", ["Enter", "Tab"])
def test_retyping_a_shared_name_keeps_the_held_manufacturer(wiz, key):
    """The person types the name again (two manufacturers share it), then Enter or
    Tab. RED: the first of that name (#1) took the box."""
    _open_edit_with(wiz, {"success": True, "vendors": [_brand(1), _brand(2)]})
    wiz.locator(SEARCH).fill("Some Brand")
    assert _held(wiz) == "2"
    wiz.locator(SEARCH).press(key)
    assert (_value(wiz, SEARCH), _held(wiz)) == ("Some Brand", "2")


def test_picking_the_other_of_two_shared_names_still_picks_it(wiz):
    """A pin: the person picks #1 from the list by the mouse, and the box holds #1."""
    _open_edit_with(wiz, {"success": True, "vendors": [_brand(1), _brand(2)]})
    wiz.locator(SEARCH).click()
    wiz.locator('#dropdown-vendor .autocomplete-option[data-value="1"]').click()
    assert _held(wiz) == "1"


# --- a manufacturer saved while the wizard is open -----------------------------------------

def test_a_manufacturer_renamed_while_edit_spool_is_open_renames_its_box(wiz):
    """RED: the box kept the old name (the re-read rebuilt the list, not the box)."""
    _open_edit_with(wiz, {"success": True, "vendors": [_brand(2)]})
    _saved(wiz, _brand(2, name="Brand Two"))
    assert (_value(wiz, SEARCH), _held(wiz)) == ("Brand Two", "2")
    assert wiz.evaluate("() => wizardState.isDirty") is False


def test_a_brands_new_weight_reaches_edit_spools_inherited_boxes(wiz):
    """Spool and filament have no empty weight of their own; the brand's 180 shows in
    both boxes. The brand is saved at 200: both boxes show 200, the spool's still
    marked as the brand's, and Save writes neither as its own. RED: both stayed 180."""
    _open_edit_with(wiz, {"success": True, "vendors": [_brand(2, weight=180.0)]},
                    spool_wt=None, fil_wt=None, vendor_wt=180.0)
    assert (_value(wiz, FIL), _value(wiz, EMPTY)) == ("180", "180")
    _saved(wiz, _brand(2, weight=200.0))
    assert (_value(wiz, FIL), _value(wiz, EMPTY)) == ("200", "200")
    assert (_badge(wiz, EMPTY_BADGE), _spool_source(wiz)) == (True, "vendor")
    body = _save(wiz, EDIT)
    assert "spool_weight" not in body["filament_data"], body["filament_data"].get("spool_weight")
    assert "spool_weight" not in body["spool_data"], body["spool_data"].get("spool_weight")


def test_a_typed_spool_empty_weight_stays_when_the_brand_is_saved(wiz):
    """A pin: the person's 205 is theirs, whatever the brand says now."""
    _open_edit_with(wiz, {"success": True, "vendors": [_brand(2, weight=180.0)]},
                    spool_wt=None, fil_wt=None, vendor_wt=180.0)
    wiz.locator(EMPTY).fill("205")
    _saved(wiz, _brand(2, weight=200.0))
    assert _value(wiz, EMPTY) == "205"
    assert _save(wiz, EDIT)["spool_data"]["spool_weight"] == 205


def test_a_new_spool_follows_the_brands_weight_saved_meanwhile(wiz):
    """New Spool of a filament with no empty weight of its own: its box shows the
    brand's 180, and the brand is saved at 200. RED: the box kept 180 (the wizard
    heard the save only when its own Vendor box held the brand, and New Spool's
    filament form is hidden), and the new spool was created with 180 as its own."""
    _open_new_spool(wiz, fil_wt=None, vendor_wt=180.0)
    assert _value(wiz, EMPTY) == "180"
    _saved(wiz, _brand(2, weight=200.0))
    assert (_value(wiz, EMPTY), _badge(wiz, EMPTY_BADGE)) == ("200", True)
    assert _save(wiz, CREATE)["spool_data"]["spool_weight"] == 200


def test_a_clone_follows_the_brands_weight_saved_meanwhile(wiz):
    """The same for a Clone of a spool with no empty weight of its own. RED: 180."""
    _open_clone(wiz, spool_wt=None, fil_wt=None, vendor_wt=180.0)
    assert _value(wiz, EMPTY) == "180"
    _saved(wiz, _brand(2, weight=200.0))
    assert (_value(wiz, EMPTY), _badge(wiz, EMPTY_BADGE)) == ("200", True)
    assert _save(wiz, CREATE)["spool_data"]["spool_weight"] == 200


def test_another_brands_save_changes_nothing(wiz):
    """A pin: a save of manufacturer #3 leaves a box showing #2's weight alone."""
    _open_new_spool(wiz, fil_wt=None, vendor_wt=180.0)
    _saved(wiz, _brand(3, name="Other Brand", weight=200.0),
           reread={"success": True, "vendors": [_brand(2, weight=180.0), _brand(3, name="Other Brand", weight=200.0)]})
    assert _value(wiz, EMPTY) == "180"


def test_a_failed_reread_keeps_the_saved_record(wiz):
    """The list read after the save fails: the wizard keeps the saved record (its
    name and weight), not the list from before. RED: the list kept the old record."""
    _open_edit_with(wiz, {"success": True, "vendors": [_brand(2, weight=180.0)]},
                    spool_wt=None, fil_wt=None, vendor_wt=180.0)
    _saved(wiz, _brand(2, name="Brand Two", weight=200.0), reread={"success": False, "msg": "no"})
    rec = wiz.evaluate("() => (wizardState.vendors || []).find((v) => String(v.id) === '2')")
    assert (rec["name"], rec["empty_spool_weight"]) == ("Brand Two", 200.0)
    assert (_value(wiz, SEARCH), _value(wiz, FIL)) == ("Brand Two", "200")


def test_a_manufacturer_made_from_the_wizard_is_picked_and_fills_as_code(wiz):
    """The wizard's ➕ made a manufacturer with a 180 g empty weight: the box picks it
    and the empty filament box shows its weight, marked as the brand's. Code filled it:
    the box isn't counted as typed in. RED: the fill was a synthetic `input`, which
    counted as the person's edit (touched, so Edit Spool would save it as the filament's
    own). The pick is the person's choice for this filament, so the wizard is marked
    changed (review round 2 of Group 66, Q4-05: this case pinned the opposite, and a
    close or an opener dropped the brand the person had just made)."""
    wiz.evaluate("() => window.openWizardModal()")
    wiz.wait_for_function("() => !!document.getElementById('wiz_fil_ef_needs_label_print')")
    wiz.evaluate("() => wizardSelectType('manual')")
    assert wiz.evaluate("() => wizardState.isDirty") is False
    _saved(wiz, _brand(5, name="New Brand", weight=180.0), created=True,
           reread={"success": True, "vendors": [_brand(2), _brand(5, name="New Brand", weight=180.0)]})
    assert (_value(wiz, SEARCH), _held(wiz)) == ("New Brand", "5")
    assert _value(wiz, FIL) == "180"
    assert "fil:spool_weight" not in _touched(wiz)
    assert wiz.evaluate("() => wizardState.isDirty") is True
    assert _badge(wiz, "#wiz-fil-empty-inherited-badge") is True
    assert wiz.evaluate("window.__errors") == []


def test_a_manufacturer_made_during_new_spool_leaves_its_spool_box_alone(wiz):
    """New Spool hides the filament's form: the selected filament gives the spool's box
    its 200. A manufacturer made meanwhile is picked in that hidden form, and its weight
    goes nowhere near the spool's box. RED: its 180 went into the spool's box (the fill's
    synthetic `input` ran the copy), and the new spool was created with it."""
    _open_new_spool(wiz)
    assert _value(wiz, EMPTY) == "200"
    _saved(wiz, _brand(5, name="New Brand", weight=180.0), created=True,
           reread={"success": True, "vendors": [_brand(2), _brand(5, name="New Brand", weight=180.0)]})
    assert (_value(wiz, EMPTY), _spool_source(wiz)) == ("200", "filament")
    assert _save(wiz, CREATE)["spool_data"]["spool_weight"] == 200
