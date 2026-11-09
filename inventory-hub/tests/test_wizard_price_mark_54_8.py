"""Group 54.8: a spool price the wizard takes from its filament is marked as the
filament's, and Save never writes it as the spool's own.

Derek, 2026-11-07, (a): *"mark the spool price as coming from the filament price.
Some times a filament's price might not be the price that exact spool costs,
because it was on sale or purchased at a lower (or higher) price than the time that
the filament entry was created."* The price cascade (buglist L349) put the
filament's price into the spool's "Price Paid ($)" box as a plain number whenever
the spool had none of its own: a new spool of an existing filament, a clone, an
edit. Save then sent the box as the spool's own price, so every new spool and every
edited spool with no price of its own got its filament's price written as its own,
and a person could no longer tell the two apart.

The rule now (`wizardState.spoolPriceFrom`, `wizardSpoolPriceIsFilaments`):
  - a price of the spool's own (an edit's, or a clone's source spool's) shows and
    saves as before, plain;
  - with none of its own and a filament price, the box shows the filament's price
    with a "↩ from filament" badge beside its label (the empty-weight box's look),
    and the section's collapsed summary says "$25 ↩ from filament";
  - typing in the box makes it the spool's own (54.5's touched set), and the mark
    goes;
  - Save sends a price only when it is the spool's own. An untouched box showing the
    filament's price sends nothing: a new spool is created with no price, an edited
    spool keeps none. 54.5's emptied box still sends null in edit mode.

The empty weight's twin (Claude's call, edit mode only): an edited spool with no
empty weight of its own shows its filament's (or brand's) with its badge, and Save
wrote it as the spool's own (the route's diff sees None against 200), so 54.5's
clear came back at the next Save. In edit mode an untouched box showing an
inherited empty weight now sends nothing. New spools and clones keep L34's rule:
they take the cascade's value as their own.

Hermetic and page-level, on the Group 58.5 harness (the REAL modals_wizard.html and
modules in `isolated_page`, real inputs typed into with real keys, the real Save),
so it runs under --offline. One real-dashboard case (the container) closes it.
"""
from __future__ import annotations

import pytest

from test_wizard_label_status_58_5 import FIELDS, MODULES, PRELUDE, WIZARD_HTML, _save
from test_wizard_native_clear_54_5 import _details, _got, _open_edit, _value, _vendor

EDIT = "/api/edit_spool_wizard"
CREATE = "/api/create_inventory_wizard"
PRICE = "#wiz-spool-price"
PRICE_BADGE = "#wiz-spool-price-inherited-badge"
EMPTY = "#wiz-spool-empty_weight"
EMPTY_BADGE = "#wiz-spool-empty-inherited-badge"
SUMMARY = 'button.fcc-wiz-section-toggle[data-bs-target="#wiz-spool-metadata-panel"] .fcc-wiz-section-summary'


@pytest.fixture
def wiz(isolated_page):
    page = isolated_page
    page.set_content('<!doctype html><html><head><meta charset="utf-8"></head><body>'
                     '<div id="toast-container"></div>' + WIZARD_HTML.read_text(encoding="utf-8")
                     + '</body></html>')
    page.add_script_tag(content=PRELUDE)
    for name in ("overlay_mount.js", "inv_core.js", "choice_validation.js", "weight_utils.js",
                 "empty_weight_field.js", "inv_wizard.js"):
        page.add_script_tag(content=(MODULES / name).read_text(encoding="utf-8"))
    page.evaluate("""(a) => { Object.assign(window.__answers, a); }""", {
        "/api/external/fields": FIELDS,
        "/api/external/vendors": {"success": True, "vendors": [_vendor(None)]},
        "/api/locations": [{"LocationID": "SHELF-1", "Name": "Shelf", "Type": "Section"}],
        "/api/filaments": {"success": True, "filaments": []},
        "/api/edit_spool_wizard": {"success": True, "spool_id": 57},
        "/api/create_inventory_wizard": {"success": True, "created_spools": [58], "filament_id": 7},
    })
    return page


def _open_new_spool(page, **kw):
    """A new spool of filament #7 (the filament window's "New Spool")."""
    filament = _details(**kw)["filament"]
    page.evaluate("""(a) => {
        window.__answers['/api/filament_details'] = a.filament;
        window.__answers['/api/external/vendors'] = { success: true, vendors: [a.filament.vendor] };
    }""", {"filament": filament})
    page.evaluate("() => { window.openNewSpoolFromFilamentWizard(7); }")
    page.wait_for_function("() => wizardState.mode === 'existing' && String(wizardState.selectedFilamentId) === '7'"
                           " && document.getElementById('wiz-status-msg').innerText.includes('pre-filled')"
                           " && !document.getElementById('btn-wiz-submit').disabled")


def _open_clone(page, **kw):
    """A copy of spool #57 (its window's "Clone")."""
    details = _details(**kw)
    page.evaluate("""(a) => {
        window.__answers['/api/spool_details'] = a.details;
        window.__answers['/api/external/vendors'] = { success: true, vendors: [a.details.filament.vendor] };
    }""", {"details": details})
    page.evaluate("() => { window.openCloneWizard(57); }")
    page.wait_for_function("() => wizardState.mode === 'existing' && String(wizardState.selectedFilamentId) === '7'"
                           " && document.getElementById('wiz-status-msg').innerText.includes('pre-filled')"
                           " && !document.getElementById('btn-wiz-submit').disabled")


def _badge(page, sel=PRICE_BADGE):
    """Whether the badge shows; None when the page has no such badge."""
    return page.evaluate("(s) => { const b = document.querySelector(s);"
                         " return b ? getComputedStyle(b).display !== 'none' : null; }", sel)


def _summary(page):
    page.evaluate("() => window.wizardRefreshSectionSummary('wiz-spool-metadata-panel')")
    return page.evaluate("(s) => document.querySelector(s).textContent.trim()", SUMMARY)


# --- what Save sends --------------------------------------------------------------------

def test_a_new_spool_of_a_25_dollar_filament_is_created_with_no_price(wiz):
    """The box shows the filament's 25 and nobody touched it, so the new spool gets
    no price of its own. RED on the base: `price: 25`, the filament's price written
    as the spool's."""
    _open_new_spool(wiz)
    assert _value(wiz, PRICE) == "25"
    body = _save(wiz, CREATE)
    assert "price" not in body["spool_data"], _got(body["spool_data"], "price")


def test_an_edit_of_a_spool_with_no_price_of_its_own_keeps_none(wiz):
    """RED on the base: the filament's 25 written as the spool's own at the Save."""
    _open_edit(wiz, price=None)
    assert _value(wiz, PRICE) == "25"
    body = _save(wiz, EDIT)
    assert "price" not in body["spool_data"], _got(body["spool_data"], "price")


def test_a_clone_of_a_spool_with_no_price_of_its_own_gets_none(wiz):
    """RED on the base: the filament's 25 written as the copy's own."""
    _open_clone(wiz, price=None)
    assert _value(wiz, PRICE) == "25"
    body = _save(wiz, CREATE)
    assert "price" not in body["spool_data"], _got(body["spool_data"], "price")


def test_a_price_typed_over_the_filaments_is_sent(wiz):
    """The person's own price. A pin: green on the base, and red on a copy of the fix
    that doesn't read typing as the spool's own."""
    _open_new_spool(wiz)
    wiz.locator(PRICE).fill("19.5")
    assert _save(wiz, CREATE)["spool_data"]["price"] == 19.5


def test_typing_the_filaments_own_price_makes_it_the_spools(wiz):
    """Typing is what makes a price the spool's own, even the same 25. A pin: green
    on the base, and red on a copy of the fix that reads only where the value came
    from (the same copy fails the cases above and below)."""
    _open_edit(wiz, price=None)
    wiz.locator(PRICE).fill("25")
    assert _save(wiz, EDIT)["spool_data"]["price"] == 25


@pytest.mark.parametrize("opener", ["edit", "clone"])
def test_a_price_of_the_spools_own_is_sent_as_before(wiz, opener):
    """An edit's own price, and a clone's source spool's (a sibling bought together):
    plain and saved as before. A pin: green on the base, and red on a copy of the
    fix that marks an own price as the filament's."""
    (_open_edit if opener == "edit" else _open_clone)(wiz, price=30.0)
    assert _value(wiz, PRICE) == "30"
    endpoint = EDIT if opener == "edit" else CREATE
    assert _save(wiz, endpoint)["spool_data"]["price"] == 30


def test_emptying_the_filaments_price_in_an_edit_is_still_a_clear(wiz):
    """54.5's rule: a box the person emptied in Edit Spool is sent as null (here a
    no-op for a spool with no price, and harmless). A pin: green on the base, and
    red on a copy of the fix that doesn't read typing as the spool's own."""
    _open_edit(wiz, price=None)
    wiz.locator(PRICE).fill("")
    body = _save(wiz, EDIT)
    assert _got(body["spool_data"], "price") is None, _got(body["spool_data"], "price")


def test_with_no_price_anywhere_nothing_is_sent(wiz):
    """Control: nothing to show, nothing to send. Green on the base and on the fix."""
    _open_new_spool(wiz, fil_price=None)
    assert _value(wiz, PRICE) == ""
    assert "price" not in _save(wiz, CREATE)["spool_data"]


# --- what the person sees ---------------------------------------------------------------

def test_the_filaments_price_is_marked_and_the_spools_own_is_not(wiz):
    """RED on the base: there is no badge."""
    _open_new_spool(wiz)
    assert _badge(wiz) is True
    _open_edit(wiz, price=30.0)
    assert _badge(wiz) is False
    _open_edit(wiz, price=None)
    assert _badge(wiz) is True
    _open_clone(wiz, price=30.0)
    assert _badge(wiz) is False
    _open_clone(wiz, price=None, fil_price=None)
    assert _badge(wiz) is False
    assert _value(wiz, PRICE) == ""


def test_the_badge_says_where_the_price_comes_from(wiz):
    """RED on the base: there is no badge."""
    _open_new_spool(wiz)
    badge = wiz.locator(PRICE_BADGE)
    assert badge.count() == 1
    assert badge.inner_text().strip() == "↩ from filament"
    assert "filament" in (badge.get_attribute("title") or "")


def test_typing_takes_the_mark_away(wiz):
    """A key typed in the box makes the price the spool's own. RED on the base:
    there is no badge."""
    _open_new_spool(wiz)
    assert _badge(wiz) is True
    price = wiz.locator(PRICE)
    price.click()
    price.press("End")
    price.press("Backspace")
    assert _badge(wiz) is False
    assert _value(wiz, PRICE) == "2"
    assert _save(wiz, CREATE)["spool_data"]["price"] == 2


def test_the_collapsed_summary_says_where_the_price_comes_from(wiz):
    """RED on the base: "$25", which reads as the spool's own."""
    _open_new_spool(wiz)
    assert _summary(wiz) == "$25 ↩ from filament"
    wiz.locator(PRICE).fill("22")
    assert _summary(wiz) == "$22"
    _open_edit(wiz, price=30.0)
    assert _summary(wiz) == "$30"


def test_the_next_wizard_session_forgets_the_mark(wiz):
    """An edit with no price of its own, then a new filament typed by hand: nothing
    is marked, and a price put in the box there is sent, even one set by the page
    (a mark left over from the edit would hold it back). RED on the base at its
    first step (no badge); its last steps are a pin, red on a copy of the fix whose
    wizardReset keeps the mark."""
    _open_edit(wiz, price=None)
    assert _badge(wiz) is True
    wiz.evaluate("() => { window.openWizardModal(); }")
    wiz.wait_for_function("() => wizardState.mode === 'manual' && document.getElementById('wiz-spool-price').value === ''")
    assert _badge(wiz) is False
    assert wiz.evaluate("() => wizardState.spoolPriceFrom") is None
    wiz.evaluate("() => wizardSelectType('manual')")
    wiz.locator("#wiz-fil-color_name").fill("Test Red")
    wiz.locator("#wiz-fil-material").fill("PLA")
    wiz.evaluate("() => { document.getElementById('wiz-spool-price').value = '25'; }")   # set, never typed
    assert _save(wiz, CREATE)["spool_data"]["price"] == 25


# --- the empty weight's twin (edit mode only) ---------------------------------------------

def test_an_edit_sends_no_empty_weight_the_spool_only_inherits(wiz):
    """The spool has no empty weight of its own: its box shows the filament's 200
    with "↩ from filament", and an untouched Save sends nothing, so 54.5's clear
    stays a clear. RED on the base: 200 written as the spool's own."""
    _open_edit(wiz, price=30.0, spool_wt=None)
    assert _value(wiz, EMPTY) == "200"
    assert _badge(wiz, EMPTY_BADGE) is True
    body = _save(wiz, EDIT)
    assert "spool_weight" not in body["spool_data"], _got(body["spool_data"], "spool_weight")
    assert body["spool_data"]["price"] == 30                     # the rest of the spool as before


def test_an_edit_sends_no_empty_weight_the_spool_inherits_from_its_brand(wiz):
    """RED on the base: the brand's 180 written as the spool's own."""
    _open_edit(wiz, spool_wt=None, fil_wt=None, vendor_wt=180.0)
    assert _value(wiz, EMPTY) == "180"
    assert wiz.locator("#wiz-spool-empty-inherited-source").inner_text() == "vendor"
    body = _save(wiz, EDIT)
    assert "spool_weight" not in body["spool_data"], _got(body["spool_data"], "spool_weight")


def test_an_inherited_empty_weight_follows_a_change_to_the_filaments(wiz):
    """The filament's 200 corrected to 205 in the same edit: the spool's box follows
    it on screen (still marked), and the spool still has none of its own, so only
    the filament gets 205. RED on the base: 205 written as the spool's own too."""
    _open_edit(wiz, spool_wt=None)
    wiz.locator("#wiz-fil-empty_weight").fill("205")
    assert _value(wiz, EMPTY) == "205"
    body = _save(wiz, EDIT)
    assert "spool_weight" not in body["spool_data"], _got(body["spool_data"], "spool_weight")
    assert body["filament_data"]["spool_weight"] == 205, body["filament_data"]


def test_an_empty_weight_typed_in_an_edit_is_sent(wiz):
    """A control: green on the base and on the fix."""
    _open_edit(wiz, spool_wt=None)
    wiz.locator(EMPTY).fill("190")
    assert _badge(wiz, EMPTY_BADGE) is False
    assert _save(wiz, EDIT)["spool_data"]["spool_weight"] == 190


def test_an_edits_own_empty_weight_is_sent_as_before(wiz):
    """A control: green on the base and on the fix."""
    _open_edit(wiz, spool_wt=196.0)
    assert _badge(wiz, EMPTY_BADGE) is False
    assert _save(wiz, EDIT)["spool_data"]["spool_weight"] == 196


def test_a_tare_entered_in_the_weigh_window_is_the_spools_own(wiz):
    """The weigh window fills an empty spool box with the tare the person gave it,
    which is theirs even where the box was marked as inherited (the filament's box
    emptied, and the spool's with it). RED on the base: the badge still said
    "↩ from filament" over that tare. With the twin and no change to the weigh
    window, Save would also have left the tare out."""
    _open_edit(wiz, spool_wt=None)
    wiz.locator("#wiz-fil-empty_weight").fill("")
    assert _value(wiz, EMPTY) == ""
    # The weigh window stands in for the real one: the person gives it a 190 g tare.
    wiz.evaluate("""() => { window.WeightEntry = { openModal: (o) => o.onSubmit(
        { empty_spool_weight: 190, used_weight: 300 }) }; }""")
    wiz.locator("#wiz-spool-weigh-launch").click()
    assert _value(wiz, EMPTY) == "190"
    assert _badge(wiz, EMPTY_BADGE) is False
    body = _save(wiz, EDIT)
    assert body["spool_data"]["spool_weight"] == 190, _got(body["spool_data"], "spool_weight")


@pytest.mark.parametrize("opener", ["new", "clone"])
def test_new_spools_and_clones_take_the_inherited_empty_weight_as_their_own(wiz, opener):
    """L34's rule, kept (Claude's call): a new spool and a clone are a fresh record and
    take the cascade's value as their own. A pin: green on the base, and red on a
    copy of the fix that applies the twin in every mode."""
    if opener == "new":
        _open_new_spool(wiz)
    else:
        _open_clone(wiz, spool_wt=None)
    assert _value(wiz, EMPTY) == "200"
    assert _badge(wiz, EMPTY_BADGE) is True
    assert _save(wiz, CREATE)["spool_data"]["spool_weight"] == 200


# --- the filament changes (Group 54 review, R2-1 / R2-3) -----------------------------------
#
# New Spool (or Clone) fills the spool's price and empty weight from its filament,
# marked as inherited. The person can still pick another filament before Save: in
# the Existing Filament list, by Advanced Search, by a scan that recognises one, or
# by switching to New Manual Form / Import Database. The marked boxes kept the first
# filament's values: the price "$25 ↩ from filament" under a filament with no price
# (or another price), and the empty weight 200 "↩ from filament" under a filament
# whose own is 180, which Create then saved as the new spool's own (L34). A box that
# still shows what its filament gives now follows the filament Save will use; a
# value the person typed, and a clone's own (its source spool's), stay.

WEIGHT_SUMMARY = 'button.fcc-wiz-section-toggle[data-bs-target="#wiz-spool-weight-panel"] .fcc-wiz-section-summary'


def _filament(fid, name, *, price=None, spool_wt=None, vendor_wt=None):
    """A filament as /api/filaments lists it: Spoolman's own record, a field with no
    value left out, its brand nested as `vendor`."""
    fil = _details(fil_price=price, fil_wt=spool_wt, vendor_wt=vendor_wt)["filament"]
    fil.update(id=fid, name=name)
    return fil


FIL_A = _filament(7, "Red", price=25.0, spool_wt=200.0)          # the opener's filament
FIL_B = _filament(8, "Green", spool_wt=200.0)                     # no price
FIL_C = _filament(9, "Blue", price=31.5, spool_wt=180.0)
FIL_D = _filament(10, "Black", vendor_wt=170.0)                   # no price, no empty weight; its brand has one


def _list(page, *fils):
    page.evaluate("(f) => { window.__answers['/api/filaments'] = { success: true, filaments: f }; }", list(fils))


def _pick(page, fid):
    """The person picks another filament in the Existing Filament list: the list as
    its search box fills it, then a click on the row (a real `change`)."""
    page.evaluate("() => window.wizardSearchExisting()")
    page.wait_for_function("(f) => !!document.querySelector(`#wiz-existing-results option[value='${f}']`)",
                           arg=str(fid))
    page.select_option("#wiz-existing-results", str(fid))
    page.wait_for_function("(f) => String(wizardState.selectedFilamentId) === f", arg=str(fid))


def _shown_summary(page, sel=SUMMARY):
    """The collapsed summary as it shows now (not redrawn by the test)."""
    return page.evaluate("(s) => document.querySelector(s).textContent.trim()", sel)


def test_a_marked_price_follows_a_pick_of_a_filament_with_no_price(wiz):
    """R2-1. RED on the base: the box kept 25 with "↩ from filament", and the summary
    "$25 ↩ from filament", under a filament with no price."""
    _list(wiz, FIL_A, FIL_B, FIL_C)
    _open_new_spool(wiz)
    assert (_value(wiz, PRICE), _badge(wiz)) == ("25", True)
    _pick(wiz, 8)
    assert _value(wiz, PRICE) == ""
    assert _badge(wiz) is False
    assert "$25" not in _shown_summary(wiz), _shown_summary(wiz)
    body = _save(wiz, CREATE)
    assert body["filament_id"] == "8", body
    assert "price" not in body["spool_data"], _got(body["spool_data"], "price")


def test_a_marked_price_follows_a_pick_of_a_filament_with_another_price(wiz):
    """R2-1. RED on the base: 25, the first filament's."""
    _list(wiz, FIL_A, FIL_B, FIL_C)
    _open_new_spool(wiz)
    _pick(wiz, 9)
    assert (_value(wiz, PRICE), _badge(wiz)) == ("31.5", True)
    assert _shown_summary(wiz).startswith("$31.5 ↩ from filament"), _shown_summary(wiz)
    body = _save(wiz, CREATE)
    assert body["filament_id"] == "9", body
    assert "price" not in body["spool_data"], _got(body["spool_data"], "price")


def test_an_inherited_empty_weight_follows_a_pick(wiz):
    """R2-3. RED on the base: 200, the first filament's, kept in the box with its
    badge and created as the new spool's own; the new filament's 180 never used."""
    _list(wiz, FIL_A, FIL_B, FIL_C)
    _open_new_spool(wiz)
    assert (_value(wiz, EMPTY), _badge(wiz, EMPTY_BADGE)) == ("200", True)
    _pick(wiz, 9)
    assert (_value(wiz, EMPTY), _badge(wiz, EMPTY_BADGE)) == ("180", True)
    assert wiz.locator("#wiz-spool-empty-inherited-source").inner_text() == "filament"
    assert "tare 180g" in _shown_summary(wiz, WEIGHT_SUMMARY), _shown_summary(wiz, WEIGHT_SUMMARY)
    assert _save(wiz, CREATE)["spool_data"]["spool_weight"] == 180


def test_an_inherited_empty_weight_follows_to_the_new_filaments_brand(wiz):
    """A filament with no empty weight of its own: its brand's, marked as the brand's
    ("vendor", the badge's word). RED on the base: 200 "↩ from filament"."""
    _list(wiz, FIL_A, FIL_D)
    _open_new_spool(wiz)
    _pick(wiz, 10)
    assert (_value(wiz, EMPTY), _badge(wiz, EMPTY_BADGE)) == ("170", True)
    assert wiz.locator("#wiz-spool-empty-inherited-source").inner_text() == "vendor"
    assert _save(wiz, CREATE)["spool_data"]["spool_weight"] == 170


def test_a_box_one_pick_left_empty_follows_the_next(wiz):
    """$25, then a filament with no price (the box empty), then one at $31.50: the box
    shows 31.5 marked, as a New Spool of that filament does. RED on the base: 25."""
    _list(wiz, FIL_A, FIL_B, FIL_C)
    _open_new_spool(wiz)
    _pick(wiz, 8)
    _pick(wiz, 9)
    assert (_value(wiz, PRICE), _badge(wiz)) == ("31.5", True)


def test_a_price_typed_before_the_pick_stays_and_is_sent(wiz):
    """The person's own price never follows a filament. A pin: green on the base, red
    on a fix that follows a typed price."""
    _list(wiz, FIL_A, FIL_B, FIL_C)
    _open_new_spool(wiz)
    wiz.locator(PRICE).fill("19.5")
    wiz.locator(EMPTY).fill("190")
    _pick(wiz, 9)
    assert (_value(wiz, PRICE), _badge(wiz)) == ("19.5", False)
    assert (_value(wiz, EMPTY), _badge(wiz, EMPTY_BADGE)) == ("190", False)
    sp = _save(wiz, CREATE)["spool_data"]
    assert (sp["price"], sp["spool_weight"]) == (19.5, 190), sp


def test_a_clones_own_price_and_empty_weight_stay_on_a_pick(wiz):
    """A clone's own values are its source spool's (a sibling bought together), not
    its filament's. A pin: green on the base, red on a fix that follows them."""
    _list(wiz, FIL_A, FIL_B, FIL_C)
    _open_clone(wiz, price=30.0, spool_wt=196.0)
    _pick(wiz, 9)
    assert (_value(wiz, PRICE), _badge(wiz)) == ("30", False)
    assert (_value(wiz, EMPTY), _badge(wiz, EMPTY_BADGE)) == ("196", False)
    sp = _save(wiz, CREATE)["spool_data"]
    assert (sp["price"], sp["spool_weight"]) == (30, 196), sp


def test_a_clone_with_nothing_of_its_own_follows_a_pick(wiz):
    """RED on the base: 25 and 200, the first filament's."""
    _list(wiz, FIL_A, FIL_B, FIL_C)
    _open_clone(wiz, price=None, spool_wt=None)
    _pick(wiz, 9)
    assert (_value(wiz, PRICE), _badge(wiz)) == ("31.5", True)
    assert (_value(wiz, EMPTY), _badge(wiz, EMPTY_BADGE)) == ("180", True)


def test_advanced_search_picks_follow_too(wiz):
    """The Existing Filament area's 🔍 Advanced Search (its pick's processFilament).
    RED on the base: 25 and 200."""
    _list(wiz, FIL_A, FIL_B)
    wiz.evaluate("""(c) => {
        window.__answers['/api/filaments/9'] = { success: true, data: c };
        window.SearchEngine = { open: (o) => o.callback(9, 'filament') };
    }""", FIL_C)
    _open_new_spool(wiz)
    wiz.locator("#area-existing button", has_text="Advanced Search").click()
    wiz.wait_for_function("() => String(wizardState.selectedFilamentId) === '9'")
    assert (_value(wiz, PRICE), _badge(wiz)) == ("31.5", True)
    assert (_value(wiz, EMPTY), _badge(wiz, EMPTY_BADGE)) == ("180", True)
    assert "price" not in _save(wiz, CREATE)["spool_data"]


def test_a_filament_fcc_couldnt_read_shows_nothing_of_the_old_ones(wiz):
    """Advanced Search picks a filament whose record FCC can't read: nothing is known
    of its price or empty weight, so the boxes show nothing, never the first
    filament's, and Create saves neither. RED on the base: 25 and 200, the 200 saved
    as the new spool's own."""
    _list(wiz, FIL_A)
    wiz.evaluate("""() => {
        window.__answers['/api/filaments/9'] = { success: false, msg: 'Filament not found' };
        window.SearchEngine = { open: (o) => o.callback(9, 'filament') };
    }""")
    _open_new_spool(wiz)
    wiz.locator("#area-existing button", has_text="Advanced Search").click()
    wiz.wait_for_function("() => String(wizardState.selectedFilamentId) === '9'")
    wiz.wait_for_timeout(100)                        # the record's read, answered
    assert (_value(wiz, PRICE), _badge(wiz)) == ("", False)
    assert (_value(wiz, EMPTY), _badge(wiz, EMPTY_BADGE)) == ("", False)
    sp = _save(wiz, CREATE)["spool_data"]
    assert "price" not in sp and "spool_weight" not in sp, sp


def test_a_new_manual_filament_takes_the_marks_away(wiz):
    """New Manual Form: the spool's filament is a new one, which has no price (the
    wizard has no price box for a filament) and only the empty weight its own form
    gives. RED on the base: 25 and 200 still marked as "the filament's"."""
    _list(wiz, FIL_A)
    _open_new_spool(wiz)
    wiz.locator("#btn-type-manual").click()
    assert (_value(wiz, PRICE), _badge(wiz)) == ("", False)
    assert (_value(wiz, EMPTY), _badge(wiz, EMPTY_BADGE)) == ("", False)
    assert "$25" not in _shown_summary(wiz), _shown_summary(wiz)
    wiz.locator("#wiz-fil-color_name").fill("Test Red")
    sp = _save(wiz, CREATE)["spool_data"]
    assert "price" not in sp and "spool_weight" not in sp, sp


def test_a_scan_that_recognises_a_filament_follows_it(wiz):
    """New Manual Form, then a Prusament scan that recognises a filament on record
    (wizardAutoSwitchToExisting): the boxes show that filament's. RED on the base:
    25 and 200 (the manual form never took them away either)."""
    _list(wiz, FIL_A, FIL_C)
    _open_new_spool(wiz)
    wiz.locator("#btn-type-manual").click()
    wiz.evaluate("(c) => window.wizardAutoSwitchToExisting(c, null)", FIL_C)
    assert wiz.evaluate("() => [wizardState.mode, String(wizardState.selectedFilamentId)]") == ["existing", "9"]
    assert (_value(wiz, PRICE), _badge(wiz)) == ("31.5", True)
    assert (_value(wiz, EMPTY), _badge(wiz, EMPTY_BADGE)) == ("180", True)


def test_the_plain_wizards_boxes_still_never_fill_from_a_pick(wiz):
    """Claude's call: only New Spool and Clone fill the spool's boxes from a filament,
    so only there do they follow one. The plain wizard (📦 Add Inventory) with a
    filament picked from the list keeps both boxes empty, as before. A pin: green on
    the base, red on a fix that fills them on every pick."""
    _list(wiz, FIL_A, FIL_C)
    wiz.evaluate("() => window.openWizardModal()")
    wiz.wait_for_function("() => !!document.getElementById('wiz_fil_ef_needs_label_print')")
    wiz.locator("#btn-type-existing").click()
    _pick(wiz, 9)
    assert (_value(wiz, PRICE), _badge(wiz)) == ("", False)
    assert (_value(wiz, EMPTY), _badge(wiz, EMPTY_BADGE)) == ("", False)


# --- the real dashboard -------------------------------------------------------------------

@pytest.mark.usefixtures("require_server")
def test_the_real_page_marks_the_filaments_price_and_saves_none(page, base_url):
    """On the real dashboard and real Bootstrap: a new spool of a filament priced 25,
    the Pricing & Metadata section opened as a person would. The badge shows beside
    the label, and Save creates the spool with no price. The filament is a stub, and
    every write is answered in the browser, so nothing reaches dev. RED on the base:
    no badge, and `price: 25` sent."""
    from test_text_size_guard import _read_only

    seen = []

    def grab(route):
        seen.append(route.request.post_data_json)
        route.fulfill(status=200, content_type="application/json",
                      body='{"success": true, "created_spools": [58], "filament_id": 7}')

    _read_only(page, extra_get={"/api/filament_details": _details()["filament"]})
    page.route("**/api/create_inventory_wizard", grab)
    page.goto(base_url)
    page.wait_for_function("() => typeof window.openNewSpoolFromFilamentWizard === 'function'"
                           " && typeof state !== 'undefined' && state.locationsLoaded", timeout=45_000)
    page.evaluate("() => { window.openNewSpoolFromFilamentWizard(7); }")
    page.wait_for_function("() => document.getElementById('wiz-status-msg').innerText.includes('pre-filled')"
                           " && document.getElementById('wiz-spool-price').value === '25'"
                           " && !document.getElementById('btn-wiz-submit').disabled", timeout=15_000)
    summary = page.locator(SUMMARY)
    assert summary.inner_text().strip() == "$25 ↩ from filament"
    page.locator('button.fcc-wiz-section-toggle[data-bs-target="#wiz-spool-metadata-panel"]').click()
    page.wait_for_function("() => { const p = document.getElementById('wiz-spool-metadata-panel');"
                           " return p.classList.contains('show') && !p.classList.contains('collapsing'); }")
    assert page.locator(PRICE_BADGE).is_visible()
    with page.expect_response("**/api/create_inventory_wizard"):
        page.locator("#btn-wiz-submit").click()
    assert len(seen) == 1, seen
    assert "price" not in seen[0]["spool_data"], seen[0]["spool_data"]
    assert seen[0]["spool_data"]["spool_weight"] == 200, seen[0]["spool_data"]     # L34, kept
