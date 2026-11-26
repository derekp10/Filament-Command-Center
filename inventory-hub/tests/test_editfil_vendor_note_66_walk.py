"""Group 66's picture walk (Derek, 2026-11-25, (b)): Edit Filament's amber "(vendor: N g)"
note is hidden while the box shows the brand's empty weight marked "↩ from vendor".

The note is older than the group: it shows the brand's empty weight whenever the brand has
one. With 66.7's badge beside it, a filament with no empty weight of its own read
"(vendor: 167g) ↩ from vendor" over a box showing 167: the same thing said twice. Derek's
pick at the walk: hide the note while the badge shows; keep it where it says something the
box doesn't (a filament with its own figure: the brand's beside it), and bring it back as
soon as a person types in the box or presses Use Vendor (the figure is then the
filament's own).

The shared <EmptyWeightField> owns it (`hint`, beside `badge`): the note shows exactly
while the badge doesn't, and a binding torn down (the window opened again) touches neither.

On the shared hermetic page (tests/edit_filament_harness.py), so it runs under --offline.
Each case marked RED fails on a93605bf for the reason it names; the others are pins.
"""
from __future__ import annotations

import pytest

from edit_filament_harness import errors, filament, load, open_form
from test_vendor_windows_66_1_js import (BRAND, SUNLU4, SUNLU35, VENDORS, _save_body, _server_has, _specs,
                                         _ui, _vendor_saved)


@pytest.fixture
def ef(isolated_page):
    return load(isolated_page, {"/api/vendors": VENDORS})


def _note(page):
    """The note's words while it is on screen, else ''. (Its innerText alone can't tell: a
    span that isn't drawn still answers its text.)"""
    n = page.locator("#editfil-vendor-wt-hint")
    return n.inner_text() if n.is_visible() else ""


def _close(page):
    page.evaluate("() => bootstrap.Modal.getInstance(document.getElementById('editFilamentModal')).hide()")
    page.wait_for_timeout(80)


def _open(page, fil, box):
    open_form(page, fil)
    page.wait_for_function("(v) => document.getElementById('editfil-spool-weight').value === v", arg=box)
    _specs(page)


def test_a_box_showing_the_brands_weight_has_the_badge_and_no_note(ef):
    """RED: the note read "(vendor: 180g)" beside "↩ from vendor"."""
    _open(ef, filament(vendor=dict(BRAND), spool_weight=None), "180")
    ui = _ui(ef)
    assert (ui["box"], ui["badge"]) == ("180", True), ui
    assert _note(ef) == ""
    assert errors(ef) == []


def test_a_filaments_own_weight_keeps_the_brands_beside_it(ef):
    """The box holds the filament's own 200, no badge; the note shows the brand's 180."""
    _open(ef, filament(vendor=dict(BRAND), spool_weight=200.0), "200")
    ui = _ui(ef)
    assert (ui["box"], ui["badge"]) == ("200", False), ui
    assert _note(ef) == "(vendor: 180g)"


def test_typing_in_the_box_brings_the_note_back(ef):
    """RED (its first look): the badge goes as a person types, and the note comes back."""
    _open(ef, filament(vendor=dict(BRAND), spool_weight=None), "180")
    assert _note(ef) == ""
    ef.locator("#editfil-spool-weight").fill("190")
    ui = _ui(ef)
    assert (ui["box"], ui["badge"]) == ("190", False), ui
    assert _note(ef) == "(vendor: 180g)"


def test_an_emptied_box_brings_the_note_back(ef):
    """RED (its first look): a person empties the box; no badge, and the note and the
    placeholder show the brand's 180."""
    _open(ef, filament(vendor=dict(BRAND), spool_weight=None), "180")
    assert _note(ef) == ""
    ef.locator("#editfil-spool-weight").fill("")
    ui = _ui(ef)
    assert (ui["box"], ui["badge"], ui["placeholder"]) == ("", False, "180"), ui
    assert _note(ef) == "(vendor: 180g)"


def test_use_vendor_makes_the_brands_figure_the_filaments_own(ef):
    """RED (its first look): Use Vendor on a box that only shows the brand's 180 makes it the
    filament's own: the badge goes, the note comes back, and Save sends it."""
    _open(ef, filament(vendor=dict(BRAND), spool_weight=None), "180")
    assert _note(ef) == ""
    ef.locator("#editfil-copy-vendor-wt").click()
    ui = _ui(ef)
    assert (ui["box"], ui["badge"]) == ("180", False), ui
    assert _note(ef) == "(vendor: 180g)"
    assert _save_body(ef).get("spool_weight") == 180


def test_a_brands_new_weight_redraws_the_box_and_the_note_stays_hidden(ef):
    """RED: the vendor editor saves the brand at 200 g over the window; the box shows 200
    "↩ from vendor", and the note (200 g now) stays hidden."""
    _open(ef, filament(vendor=dict(BRAND), spool_weight=None), "180")
    saved = dict(BRAND, empty_spool_weight=200.0)
    _server_has(ef, [saved, SUNLU4, SUNLU35])
    _vendor_saved(ef, saved)
    ui = _ui(ef)
    assert (ui["box"], ui["badge"], ui["hint"]) == ("200", True, "(vendor: 200g)"), ui
    assert _note(ef) == ""


def test_a_brand_left_with_no_weight_shows_neither(ef):
    """The brand's weight cleared over the window: an empty box, no badge, no note."""
    _open(ef, filament(vendor=dict(BRAND), spool_weight=None), "180")
    saved = dict(BRAND, empty_spool_weight=None)
    _server_has(ef, [saved, SUNLU4, SUNLU35])
    _vendor_saved(ef, saved)
    ui = _ui(ef)
    assert (ui["box"], ui["badge"], ui["hint"]) == ("", False, ""), ui
    assert _note(ef) == ""


def test_each_open_shows_its_own_note(ef):
    """RED (its first and third looks): an open that hid the note leaves the next open, of a
    filament with its own weight, showing it, and the open after that hides it again."""
    _open(ef, filament(vendor=dict(BRAND), spool_weight=None), "180")
    assert _note(ef) == ""
    _close(ef)
    _open(ef, filament(id=8, name="Blue", vendor=dict(BRAND), spool_weight=200.0), "200")
    assert _note(ef) == "(vendor: 180g)"
    _close(ef)
    _open(ef, filament(id=9, name="Green", vendor=dict(BRAND), spool_weight=None), "180")
    assert _note(ef) == ""
    assert errors(ef) == []


def test_a_torn_down_handle_leaves_the_badge_and_the_note_alone(ef):
    """The box bound again with the note in the new binding's care: the old binding's
    clearBadge hides neither the new badge nor shows the note. RED: `hint` was no option
    (the note stayed drawn), and the old handle hid the new binding's badge."""
    _open(ef, filament(vendor=dict(BRAND), spool_weight=None), "180")
    got = ef.evaluate("""() => {
        const box = document.getElementById('editfil-spool-weight');
        const badge = document.getElementById('editfil-spool-weight-inherited-badge');
        const hint = document.getElementById('editfil-vendor-wt-hint');
        const old = window.emptyWeightFieldOf(box);
        const fresh = window.bindEmptyWeightField({ input: box, badge, hint });
        fresh.setFromCascade({ spoolWt: null, vendor: { id: 2, name: 'Some Brand', empty_spool_weight: 180 } });
        old.clearBadge();
        return [box.value, fresh.inherited(), badge.style.display, hint.style.display];
    }""")
    assert got == ["180", "vendor", "", "none"], got


def test_a_binding_with_no_note_draws_as_before(ef):
    """A pin: the wizard's boxes pass no `hint`; the badge still shows and goes, with no error."""
    _open(ef, filament(vendor=dict(BRAND), spool_weight=None), "180")
    got = ef.evaluate("""() => {
        const box = document.getElementById('editfil-spool-weight');
        const badge = document.getElementById('editfil-spool-weight-inherited-badge');
        const f = window.bindEmptyWeightField({ input: box, badge });
        f.setFromCascade({ spoolWt: null, vendor: { id: 2, name: 'Some Brand', empty_spool_weight: 180 } });
        const shown = badge.style.display;
        box.value = '190';
        box.dispatchEvent(new Event('input', { bubbles: true }));
        return [shown, badge.style.display, f.inherited()];
    }""")
    assert got == ["", "none", None], got
    assert errors(ef) == []
