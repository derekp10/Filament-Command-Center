"""Group 66.5: the spool's empty-weight box follows the filament's Spool Wt by one rule,
in every mode of the wizard.

Group 54's review (S1) gave Edit Spool a rule for the copy of the filament's Spool Wt
into the spool's box: never over a value the person typed or emptied there, or one of
the spool's own; a box that shows what the spool inherits (marked), or nothing, shows
what it inherits now (the filament's value "↩ from filament", else the brand's "↩ from
vendor", else nothing). Every other mode kept a plain copy: the filament's value went
into the spool's box whatever it held, unmarked, and the mark it had stayed. So:
  - a spool weight typed before the filament's was overwritten (plain Add, and a
    Clone's own empty weight after a switch to New Manual Form);
  - New Spool and Clone, switched to New Manual Form, showed the typed value unmarked,
    and a later Existing pick didn't follow it (the follow takes only marked boxes);
  - a box marked "↩ from vendor" kept that badge over the filament's typed value;
  - emptying the filament's box emptied the spool's, never showing the brand's.

Now the one rule holds in every mode (wizardFilamentEmptyWeightChanged through the
shared helper). New spools still take what their box shows as their own (L34: a create
sends a marked value), and Edit Spool still leaves an inherited one out (54.8). The
filament box listens to `input` only (a stale `change` from the last session ran the
copy against the new one). And in the plain wizard (whose boxes never fill from a
pick), a spool box marked from New Manual Form is no longer kept after a switch to
Existing Filament, whose filament isn't the one it came from (Claude's call 6b).

Hermetic and page-level, on the Group 58.5 harness, so it runs under --offline. Each
case marked RED fails on the commit before this one for the reason it names.
"""
from __future__ import annotations

from test_wizard_label_status_58_5 import _save
from test_wizard_native_clear_54_5 import _got, _open_new_filament, _value
from test_wizard_price_mark_54_8 import FIL_A, FIL_C, _badge, _list, _open_clone, _open_new_spool, _pick, wiz  # noqa: F401
from test_wizard_vendor_66_1 import _brand

CREATE = "/api/create_inventory_wizard"
FIL = "#wiz-fil-empty_weight"
EMPTY = "#wiz-spool-empty_weight"
EMPTY_BADGE = "#wiz-spool-empty-inherited-badge"


def _source(page):
    return page.evaluate("() => wizardState.spoolEmptyWeightFrom")


def _spool(page):
    """The spool box: (its value, its badge shown, where it says the value comes from)."""
    return (_value(page, EMPTY), _badge(page, EMPTY_BADGE), _source(page))


def _manual(page):
    page.locator("#btn-type-manual").click()
    page.wait_for_function("() => wizardState.mode === 'manual'")


def _existing(page):
    page.locator("#btn-type-existing").click()
    page.wait_for_function("() => wizardState.mode === 'existing'")


def _with_brand(page, weight):
    """The vendor list answers brand #2 with `weight` (set before the wizard opens)."""
    page.evaluate("(v) => { window.__answers['/api/external/vendors'] = { success: true, vendors: [v] }; }",
                  _brand(2, weight=weight))


def _pick_brand(page):
    page.evaluate("() => window.wizardComboboxSet('wiz-fil-vendor-search', 'wiz-fil-vendor-sel', '2', 'Some Brand')")


def test_a_new_filaments_weight_shows_in_the_spools_box_as_the_filaments(wiz):
    """Plain Add, New Manual Form: the spool's box shows the filament's 210 marked "↩ from
    filament", and the new spool takes it as its own (L34). RED: shown plain."""
    _open_new_filament(wiz)
    wiz.locator(FIL).fill("210")
    assert _spool(wiz) == ("210", True, "filament")
    assert _save(wiz, CREATE)["spool_data"]["spool_weight"] == 210


def test_a_spool_weight_typed_first_stays_when_the_filaments_is_typed(wiz):
    """Plain Add: the person typed 196 for the spool, then 210 for the filament. RED: the
    spool's 196 was overwritten with 210."""
    _open_new_filament(wiz)
    wiz.locator(EMPTY).fill("196")
    wiz.locator(FIL).fill("210")
    assert _spool(wiz) == ("196", False, None)
    assert _save(wiz, CREATE)["spool_data"]["spool_weight"] == 196


def test_a_clones_own_weight_stays_through_new_manual_form(wiz):
    """A Clone of a spool with its own 196, switched to New Manual Form, the filament's
    210 typed. RED: 210 over the clone's own 196."""
    _open_clone(wiz, spool_wt=196.0)
    _manual(wiz)
    wiz.locator(FIL).fill("210")
    assert _value(wiz, EMPTY) == "196"
    assert _save(wiz, CREATE)["spool_data"]["spool_weight"] == 196


def test_a_new_spool_through_new_manual_form_follows_a_later_pick(wiz):
    """New Spool (Red, 200) → New Manual Form → 210 typed for the filament → back to
    Existing → Blue (180) picked: the box shows Blue's 180 as the filament's, and the new
    spool takes 180. RED: 210 unmarked, kept through the pick and created as the spool's."""
    _list(wiz, FIL_A, FIL_C)
    _open_new_spool(wiz)
    _manual(wiz)
    wiz.locator(FIL).fill("210")
    assert _spool(wiz) == ("210", True, "filament")
    _existing(wiz)
    _pick(wiz, 9)
    assert _spool(wiz) == ("180", True, "filament")
    assert _save(wiz, CREATE)["spool_data"]["spool_weight"] == 180


def test_a_weight_typed_for_the_filament_takes_the_vendor_badge_away(wiz):
    """New Spool of a filament with no weight, its brand at 180, switched to New Manual
    Form with the brand picked: the box shows 180 "↩ from vendor". 210 typed for the
    filament: it shows 210 "↩ from filament". RED: 210 under "↩ from vendor"."""
    _open_new_spool(wiz, fil_wt=None, vendor_wt=180.0)
    _pick_brand(wiz)
    _manual(wiz)
    assert _spool(wiz) == ("180", True, "vendor")
    wiz.locator(FIL).fill("210")
    assert _spool(wiz) == ("210", True, "filament")
    assert wiz.locator("#wiz-spool-empty-inherited-source").inner_text() == "filament"


def test_emptying_the_filaments_weight_shows_the_brands(wiz):
    """Plain Add with the brand (180) picked: 210 typed for the filament, then emptied.
    The spool's box shows the brand's 180 as the brand's. RED: emptied."""
    _with_brand(wiz, 180.0)
    _open_new_filament(wiz)
    _pick_brand(wiz)
    wiz.locator(FIL).fill("210")
    wiz.locator(FIL).fill("")
    assert _spool(wiz) == ("180", True, "vendor")


def test_the_plain_wizard_drops_a_marked_box_after_a_switch_to_existing(wiz):
    """Claude's call 6b. The plain wizard: 210 typed in New Manual Form shows in the
    spool's box as the filament's; the person switches to Existing Filament and picks
    Blue. That box's filament is gone: it is empty again, as a direct pick leaves it,
    and the new spool has none of its own. RED: 210 kept, and created as the spool's."""
    _list(wiz, FIL_A, FIL_C)
    _open_new_filament(wiz)
    wiz.locator(FIL).fill("210")
    _existing(wiz)
    _pick(wiz, 9)
    assert _spool(wiz) == ("", False, None)
    body = _save(wiz, CREATE)
    assert "spool_weight" not in body["spool_data"], _got(body["spool_data"], "spool_weight")


def test_a_typed_spool_weight_survives_the_switch_to_existing(wiz):
    """A pin for 6b: a value the person typed in the spool's box stays."""
    _list(wiz, FIL_A, FIL_C)
    _open_new_filament(wiz)
    wiz.locator(EMPTY).fill("196")
    _existing(wiz)
    _pick(wiz, 9)
    assert _value(wiz, EMPTY) == "196"
    assert _save(wiz, CREATE)["spool_data"]["spool_weight"] == 196


def test_a_stale_change_from_the_last_session_copies_nothing(wiz):
    """New Spool's box shows its filament's 200. The filament's box (hidden in New Spool,
    emptied by the open's reset) hears a `change`: the blur of an edit made in the last
    session, which Chromium fires in the new one when the box kept the focus (Group
    54.5's finding). Only `input` is the person's edit, so nothing is copied. RED: the
    spool's 200 was emptied (and the new spool created with none)."""
    _open_new_spool(wiz)
    assert _spool(wiz) == ("200", True, "filament")
    wiz.evaluate("() => document.getElementById('wiz-fil-empty_weight')"
                 ".dispatchEvent(new Event('change', { bubbles: true }))")
    assert _spool(wiz) == ("200", True, "filament")
