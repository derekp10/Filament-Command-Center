"""Review round 2 of Group 66, Edit Filament's manufacturer box (Q1-01 to Q1-05, Q1-07).

  - Q1-01: emptying the Vendor box (Generic) left the old vendor's weight in Spool Wt,
    marked "↩ from vendor", with its hint and Use Vendor; Save left it out, so the filament
    ended with no vendor and no weight of its own while the window showed the old one's.
  - Q1-02: with the vendor list unread (a Spoolman blip: 502), a name typed in the box kept
    the old vendor's weight under the hint, the badge and Use Vendor, and Use Vendor saved
    it as the filament's own on the vendor typed.
  - Q1-03: a re-read that failed (after a vendor save) dropped the open's own list, which
    landed later: the dropdown offered one vendor for the rest of the session.
  - Q1-04: with the list unread, a mistyped name had no sign that Save would make it a new
    manufacturer, and the toast named none.
  - Q1-05: under a name two vendors share (Derek's Sunlu #4 and #35), part of the name and
    Enter picked the lowest id: a filament on #35 moved to #4.
  - Q1-07: an earlier open's late vendor read redrew the next open's Spool Wt box through
    the earlier open's weight handle (round 1's R2-01 stops the read; the handle itself is
    inert once torn down).

On the shared hermetic page (tests/edit_filament_harness.py), so it runs under --offline.
Each case marked RED fails on f09bdc9c for the reason it names.
"""
from __future__ import annotations

import pytest

from edit_filament_harness import errors, filament, load, open_form, posts_to
from test_vendor_windows_66_1_js import BRAND, SUNLU4, SUNLU35, VENDORS, _save_body, _specs, _ui

UNREAD = {"__status": 502, "__body": {"success": False, "msg": "Spoolman didn't answer"}}


@pytest.fixture
def ef(isolated_page):
    return load(isolated_page, {"/api/vendors": VENDORS})


def _note(page):
    n = page.locator("#editfil-vendor-unread-note")
    return n.inner_text() if n.is_visible() else ""


# --- Q1-01: an emptied Vendor box ----------------------------------------------------------

def test_an_emptied_vendor_box_shows_nothing_from_the_old_vendor(ef):
    """RED: the box kept 180 "↩ from vendor", the hint and Use Vendor (180g), and Save sent
    no weight with vendor_id null."""
    open_form(ef, filament(vendor=dict(BRAND), spool_weight=None))
    _specs(ef)
    assert _ui(ef)["box"] == "180"
    ef.locator("#editfil-vendor-name").fill("")
    ui = _ui(ef)
    assert (ui["box"], ui["badge"], ui["hint"], ui["useVendor"], ui["vendorId"]) == ("", False, "", None, ""), ui
    body = _save_body(ef)
    assert body.get("vendor_id", "<missing>") is None and "spool_weight" not in body, body


# --- Q1-02 / Q1-04: a list that couldn't be read -----------------------------------------------

def test_a_name_typed_while_the_list_is_unread_shows_no_old_vendor_weight(ef):
    """RED: the box kept Some Brand's 180 "↩ from vendor" beside "Sunlu", with Use Vendor
    (180g), and Use Vendor saved 180 as the filament's own on Sunlu."""
    ef.evaluate("(a) => { window.__answers['/api/vendors'] = a; }", UNREAD)
    open_form(ef, filament(vendor=dict(BRAND), spool_weight=None))
    _specs(ef)
    ef.locator("#editfil-vendor-name").fill("Sunlu")
    ui = _ui(ef)
    assert (ui["box"], ui["badge"], ui["hint"], ui["useVendor"]) == ("", False, "", None), ui
    assert errors(ef) == []


def test_a_name_typed_while_the_list_is_unread_says_save_may_make_it(ef):
    """RED: nothing said FCC couldn't check the name, and the toast named no manufacturer,
    though Save made "Snlu" (#41)."""
    ef.evaluate("""(a) => { window.__answers['/api/vendors'] = a;
        window.__answers['POST /api/vendors'] = { success: true, vendor: { id: 41, name: 'Snlu' } }; }""", UNREAD)
    open_form(ef, filament(vendor=dict(BRAND), spool_weight=150.0))
    ef.locator("#editfil-vendor-name").fill("Snlu")
    assert "Couldn't read the manufacturer list to check this name" in _note(ef)
    body = _save_body(ef)
    assert body["vendor_id"] == 41
    assert "made the new manufacturer Snlu (#41)" in ef.locator("#toast-container").inner_text()


def test_the_filaments_own_vendor_retyped_while_unread_says_nothing(ef):
    """A pin: the filament's own manufacturer is known without the list: no note."""
    ef.evaluate("(a) => { window.__answers['/api/vendors'] = a; }", UNREAD)
    open_form(ef, filament(vendor=dict(BRAND), spool_weight=150.0))
    ef.locator("#editfil-vendor-name").fill("some brand")
    assert (_note(ef), _ui(ef)["vendorId"]) == ("", "2")


def test_a_list_that_was_read_says_nothing_of_it(ef):
    """A pin: with the list read, a new name is marked "+ NEW", and there is no note."""
    open_form(ef, filament(vendor=dict(BRAND), spool_weight=150.0))
    ef.locator("#editfil-vendor-name").fill("Fresh Brand")
    assert (_ui(ef)["isNew"], _note(ef)) == (True, "")


# --- Q1-03: an older good list after a failed re-read ----------------------------------------------

def test_the_opens_list_lands_after_a_failed_reread(ef):
    """RED: the open's list, landing after a re-read that failed, was dropped (an older
    read), and the dropdown offered the one vendor just saved."""
    ef.evaluate("() => { window.__answers['/api/vendors'] = '__hold__'; }")
    open_form(ef, filament(vendor=dict(BRAND), spool_weight=150.0))
    ef.evaluate("""(u) => { window.__heldOpen = window.__held['/api/vendors'];
        window.__answers['/api/vendors'] = u; }""", UNREAD)
    ef.evaluate("(v) => document.dispatchEvent(new CustomEvent('vendor:updated', { detail: { id: '2', vendor: v } }))",
                dict(BRAND))
    ef.wait_for_timeout(100)
    ef.evaluate("(v) => window.__heldOpen(v)", VENDORS)
    ef.wait_for_timeout(100)
    box = ef.locator("#editfil-vendor-name")
    box.fill("")
    box.focus()
    rows = ef.evaluate("() => Array.from(document.querySelectorAll('#editfil-vendor-dropdown .dropdown-item'))"
                       ".map((r) => r.dataset.value)")
    assert rows == ["2", "4", "35"], rows


# --- Q1-05: part of a shared name, then Enter ---------------------------------------------------------

@pytest.mark.parametrize("typed", ["Sun", "sunl"])
def test_part_of_a_shared_name_and_enter_keeps_the_filaments_own_vendor(ef, typed):
    """RED: Enter took the first row, Sunlu #4, and Save moved the filament off #35."""
    open_form(ef, filament(vendor=dict(SUNLU35), spool_weight=150.0))
    box = ef.locator("#editfil-vendor-name")
    box.focus()
    ef.keyboard.press("Control+A")
    ef.keyboard.type(typed, delay=40)
    ef.keyboard.press("Enter")
    ef.wait_for_timeout(60)
    assert (_ui(ef)["vendorId"], _ui(ef)["vendorName"]) == ("35", "Sunlu")
    ef.locator("#editfil-name").fill("Orange Two")
    assert _save_body(ef) == {"name": "Orange Two"}


def test_an_arrowed_row_is_still_the_persons_pick(ef):
    """A pin: the person arrows to Sunlu #4 and presses Enter: #4 it is."""
    open_form(ef, filament(vendor=dict(SUNLU35), spool_weight=150.0))
    box = ef.locator("#editfil-vendor-name")
    box.focus()
    ef.keyboard.press("Control+A")
    ef.keyboard.type("Sun", delay=40)
    ef.keyboard.press("ArrowDown")
    ef.keyboard.press("Enter")
    assert _ui(ef)["vendorId"] == "4"


# --- Q1-07: an earlier open's late read, and a torn-down handle ---------------------------------------

def test_an_earlier_opens_late_vendor_read_leaves_the_next_open_alone(ef):
    """A pin (round 1's R2-01 drops the read): A's list, landing after B opened, leaves B's
    own 167 unmarked and unsent."""
    ef.evaluate("() => { window.__answers['/api/vendors'] = '__hold__'; }")
    brand_one = {"id": 2, "name": "Brand One", "empty_spool_weight": 167.0, "external_id": "", "extra": {}}
    brand_two = {"id": 3, "name": "Brand Two", "empty_spool_weight": 200.0, "external_id": "", "extra": {}}
    open_form(ef, filament(id=7, vendor=dict(brand_one), spool_weight=None))
    ef.evaluate("() => { window.__heldA = window.__held['/api/vendors']; }")
    ef.evaluate("() => bootstrap.Modal.getInstance(document.getElementById('editFilamentModal')).hide()")
    ef.wait_for_timeout(80)
    ef.evaluate("(v) => { window.__answers['/api/vendors'] = { success: true, vendors: v }; }", [brand_one, brand_two])
    open_form(ef, filament(id=8, name="Blue", vendor=dict(brand_two), spool_weight=167.0))
    ef.wait_for_function("() => document.getElementById('editfil-vendor-id').value === '3'"
                         " && document.getElementById('editfil-spool-weight').value === '167'")
    ef.wait_for_timeout(100)    # B's own reads land
    _specs(ef)
    ef.evaluate("(v) => window.__heldA({ success: true, vendors: v })", [brand_one, brand_two])
    ef.wait_for_timeout(100)
    ui = _ui(ef)
    assert (ui["box"], ui["badge"]) == ("167", False), ui
    ef.locator("#editfil-name").fill("Blue Two")
    assert _save_body(ef) == {"name": "Blue Two"}


def test_a_torn_down_weight_handle_writes_nothing(ef):
    """The box bound again: the old handle's setVendor, setValue and setFromCascade leave
    the box and its badge as the new binding drew them. RED: the old handle redrew the box."""
    open_form(ef, filament(vendor=dict(BRAND), spool_weight=None))
    got = ef.evaluate("""() => {
        const box = document.getElementById('editfil-spool-weight');
        const old = window.emptyWeightFieldOf(box);
        const fresh = window.bindEmptyWeightField({ input: box,
            badge: document.getElementById('editfil-spool-weight-inherited-badge') });
        fresh.setFromCascade({ spoolWt: 150 });
        old.setVendor({ id: 3, name: 'X', empty_spool_weight: 200 });
        old.setFromCascade({ spoolWt: null, vendor: { id: 3, name: 'X', empty_spool_weight: 200 } });
        old.setValue(999);
        return [box.value, fresh.inherited(), fresh.isTouched()];
    }""")
    assert got == ["150", None, False], got


# --- Q4-03: a vendor push, then a Save -----------------------------------------------------------

def test_a_vendor_push_then_a_save_sends_no_weight(ef):
    """The vendor window saves the filament's manufacturer at 200 g over the window: the box
    shows 200 as the vendor's (the binding says so), and a Save of another edit sends no
    weight. A pin (review round 2, Q4-03: the push's case never pressed Save, so a push that
    left the box read as touched, and Save writing 200 as the filament's own, passed it)."""
    from test_vendor_windows_66_1_js import _server_has, _vendor_saved
    open_form(ef, filament(vendor=dict(BRAND), spool_weight=None))
    _specs(ef)
    saved = dict(BRAND, empty_spool_weight=200.0)
    _server_has(ef, [saved, SUNLU4, SUNLU35])
    _vendor_saved(ef, saved)
    assert _ui(ef)["box"] == "200"
    assert ef.evaluate("() => window.emptyWeightFieldOf('editfil-spool-weight').inherited()") == "vendor"
    ef.locator("#editfil-name").fill("Red Two")
    assert _save_body(ef) == {"name": "Red Two"}
