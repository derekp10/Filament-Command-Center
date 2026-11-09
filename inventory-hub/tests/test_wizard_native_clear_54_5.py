"""Group 54.5: emptying a plain field in Edit Spool clears it.

Five of the wizard's boxes are Spoolman's own fields, not extras: the spool's
Price Paid and empty weight, and the filament's empty weight, Nozzle Min and Bed
Min. Save read an empty one as `null` and then dropped every null from the
payload, so erasing one and saving kept the old value: the field could never be
cleared from the wizard. The delete sentinel is for extras only.

The rule now (edit mode only): a box the user changed this session
(`wizardState.touchedNative`, filled by the wizard's input / change listener,
read per key through `wizardNativeTouched`) and left empty is sent as `null`,
which the server passes through and Spoolman takes as "no value" (checked on
dev's Spoolman 0.27.1, 2026-11-09: each of the six fields PATCHed to null read
back absent, and no other field changed). A box the page drew empty, or blanked
itself, is still left out, so the record keeps what it has. Create, clone and
external modes build a fresh record and are unchanged.

The empty-weight cross-inherit at Save (Spool -> Filament -> Vendor) never
refills a box the user emptied in edit mode. Re-checked here against what the
code really does: it only ever fills the FILAMENT's side. The spool payload's
nulls are dropped before that block runs, so its spool line could never fire
(not since 13654bb, 2026-04-06), and it is gone. An emptied spool empty weight
was therefore missing from the request, never refilled with the filament's
value, and an emptied filament empty weight was refilled with the brand's.

Hermetic and page-level, on the Group 58.5 harness: the REAL
modals_wizard.html, overlay_mount.js, inv_core.js, choice_validation.js,
weight_utils.js, empty_weight_field.js and inv_wizard.js in `isolated_page` (no
network), so it runs under --offline. The boxes are real number inputs, typed
into with real keys, and Save is the real button. One real-dashboard case (the
container) and one offline server pin (the route over SpoolmanHTTPFake) close it.
"""
from __future__ import annotations

import copy
import json
from unittest.mock import patch

import pytest

from spoolman_extra_fake import SpoolmanHTTPFake
from test_wizard_label_status_58_5 import FIELDS, MODULES, PRELUDE, WIZARD_HTML, _save

EDIT = "/api/edit_spool_wizard"
CREATE = "/api/create_inventory_wizard"

# (box, the payload it goes in, its key there)
BOXES = [
    ("#wiz-spool-price", "spool_data", "price"),
    ("#wiz-spool-empty_weight", "spool_data", "spool_weight"),
    ("#wiz-fil-empty_weight", "filament_data", "spool_weight"),
    ("#wiz-fil-settings_extruder_temp", "filament_data", "settings_extruder_temp"),
    ("#wiz-fil-settings_bed_temp", "filament_data", "settings_bed_temp"),
]


def _vendor(vendor_wt):
    v = {"extra": {}, "id": 2, "name": "Some Brand", "registered": "2026-02-11T04:07:24Z"}
    if vendor_wt is not None:
        v["empty_spool_weight"] = vendor_wt
    return v


def _details(*, price=30.0, spool_wt=196.0, fil_wt=200.0, nozzle=215, bed=60, fil_price=25.0, vendor_wt=None):
    """/api/spool_details for spool #57 of filament #7. A field with no value is
    left out of the record, as Spoolman does (dev 0.27.1, 2026-11-09)."""
    filament = {
        "color_hex": "72071C", "comment": "", "density": 1.24, "diameter": 1.75, "external_id": "3",
        "extra": {}, "id": 7, "material": "PLA", "name": "Red", "registered": "2026-02-11T04:07:24Z",
        "tags": [], "weight": 1000.0, "vendor": _vendor(vendor_wt),
    }
    for key, value in (("spool_weight", fil_wt), ("settings_extruder_temp", nozzle),
                       ("settings_bed_temp", bed), ("price", fil_price)):
        if value is not None:
            filament[key] = value
    spool = {
        "archived": False, "extra": {}, "id": 57, "initial_weight": 1000.0, "location": "SHELF-1",
        "registered": "2026-02-11T04:07:24Z", "remaining_weight": 500.0, "tags": [], "used_weight": 500.0,
        "filament": filament,
    }
    for key, value in (("price", price), ("spool_weight", spool_wt)):
        if value is not None:
            spool[key] = value
    return spool


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


def _open_edit(page, **kw):
    details = _details(**kw)
    page.evaluate("""(a) => {
        window.__answers['/api/spool_details'] = a.details;
        window.__answers['/api/external/vendors'] = { success: true, vendors: [a.vendor] };
    }""", {"details": details, "vendor": details["filament"]["vendor"]})
    # Not awaited: openEditWizard holds no answer the test needs, and the states
    # are waited on below.
    page.evaluate("() => { window.openEditWizard(57); }")
    page.wait_for_function("() => wizardState.mode === 'edit_spool' && wizardState.selectedFilamentId === 7"
                           " && !!document.getElementById('wiz_fil_ef_needs_label_print')"
                           " && document.getElementById('wiz-fil-color_name').value === 'Red'"
                           " && !document.getElementById('btn-wiz-submit').disabled")


def _open_new_filament(page):
    page.evaluate("() => window.openWizardModal()")
    page.wait_for_function("() => !!document.getElementById('wiz_fil_ef_needs_label_print')")
    page.evaluate("() => wizardSelectType('manual')")
    page.locator("#wiz-fil-color_name").fill("Test Red")
    page.locator("#wiz-fil-material").fill("PLA")


def _value(page, box):
    return page.locator(box).input_value()


def _touched(page):
    return page.evaluate("() => Array.from(wizardState.touchedNative || []).sort()")


def _got(part, key):
    """What the request carried for `key`: its value, or "<missing>"."""
    return part[key] if key in part else "<missing>"


# --- an emptied box is a clear --------------------------------------------------------

@pytest.mark.parametrize("box,part,key", BOXES, ids=[b[0][1:] for b in BOXES])
def test_an_emptied_box_is_sent_as_null(wiz, box, part, key):
    """The bug: erase the box, Save, and the key was missing from the request, so
    Spoolman kept the old value. RED on the base for all five: the key is missing."""
    _open_edit(wiz)
    assert _value(wiz, box) != ""                     # the box really held the record's value
    wiz.locator(box).fill("")
    body = _save(wiz, EDIT)
    assert _got(body[part], key) is None, (key, _got(body[part], key))


def test_the_emptied_spool_empty_weight_is_null_although_the_filament_has_200(wiz):
    """The spool's own 196 g emptied, with 200 g on its filament and 180 g on its
    brand: the request says null, never the filament's or the brand's value. RED on
    the base, because the key is missing. (The planning pass expected 200 from the
    cross-inherit, but the spool's nulls were dropped before that block, so it
    never filled the spool's side.)"""
    _open_edit(wiz, vendor_wt=180.0)
    assert _value(wiz, "#wiz-spool-empty_weight") == "196"
    wiz.locator("#wiz-spool-empty_weight").fill("")
    body = _save(wiz, EDIT)
    assert _got(body["spool_data"], "spool_weight") is None, _got(body["spool_data"], "spool_weight")
    assert body["filament_data"]["spool_weight"] == 200, body["filament_data"]   # its own box, untouched


def test_an_emptied_filament_empty_weight_is_not_refilled_from_the_brand(wiz):
    """The cross-inherit fills an empty filament box from the spool's box or the
    brand. In edit mode a box the user emptied means "no value of its own", so it
    is sent as null. RED on the base: 180, the brand's, written as the filament's
    own. (The filament's box copies itself into the spool's on screen, so the
    spool's own 196 g is no candidate here: its box is empty too.)"""
    _open_edit(wiz, vendor_wt=180.0)
    wiz.locator("#wiz-fil-empty_weight").fill("")
    body = _save(wiz, EDIT)
    assert _got(body["filament_data"], "spool_weight") is None, _got(body["filament_data"], "spool_weight")


def test_emptying_the_filament_empty_weight_never_clears_the_spools(wiz):
    """The filament's box copies itself into the spool's on screen
    (wizardSetupFieldSync, set by code). The spool's box is then empty, but the
    user didn't empty it, so the spool keeps its own 196 g: its key is left out,
    as before. A pin: green on the base, red on a copy of the fix that sends every
    empty box in edit mode as null."""
    _open_edit(wiz)
    wiz.locator("#wiz-fil-empty_weight").fill("")
    assert _value(wiz, "#wiz-spool-empty_weight") == ""          # emptied by the copy, not by the user
    body = _save(wiz, EDIT)
    assert "spool_weight" not in body["spool_data"], _got(body["spool_data"], "spool_weight")


def test_typed_then_emptied_is_null(wiz):
    """RED on the base: the key is missing."""
    _open_edit(wiz)
    wiz.locator("#wiz-spool-price").fill("45")
    wiz.locator("#wiz-spool-price").fill("")
    body = _save(wiz, EDIT)
    assert _got(body["spool_data"], "price") is None, _got(body["spool_data"], "price")


def test_emptied_then_retyped_is_the_number(wiz):
    """A pin: green on the base, and on the fix."""
    _open_edit(wiz)
    wiz.locator("#wiz-fil-settings_bed_temp").fill("")
    wiz.locator("#wiz-fil-settings_bed_temp").fill("65")
    wiz.locator("#wiz-spool-price").fill("")
    wiz.locator("#wiz-spool-price").fill("27.5")
    body = _save(wiz, EDIT)
    assert body["filament_data"]["settings_bed_temp"] == 65, body["filament_data"]
    assert body["spool_data"]["price"] == 27.5, body["spool_data"]


# --- what is never a clear -------------------------------------------------------------

def test_an_untouched_save_sends_what_the_boxes_show_and_no_null(wiz):
    """Control: nothing touched, nothing cleared. Green on the base, and on the fix."""
    _open_edit(wiz)
    assert _touched(wiz) == []
    body = _save(wiz, EDIT)
    sp, fil = body["spool_data"], body["filament_data"]
    assert (sp["price"], sp["spool_weight"]) == (30, 196), sp
    assert (fil["spool_weight"], fil["settings_extruder_temp"], fil["settings_bed_temp"]) == (200, 215, 60), fil
    assert [k for k, v in sp.items() if v is None] == [], sp
    assert [k for k, v in fil.items() if v is None and not k.startswith("multi_color_")] == [], fil


def test_an_untouched_empty_box_sends_nothing(wiz):
    """Control: a filament with no temperatures, a spool and filament with no price.
    The page draws the boxes empty, and the record keeps having none. Green on the
    base, and on the fix (proved on a copy that sends every empty box as null)."""
    _open_edit(wiz, price=None, fil_price=None, nozzle=None, bed=None)
    for box in ("#wiz-spool-price", "#wiz-fil-settings_extruder_temp", "#wiz-fil-settings_bed_temp"):
        assert _value(wiz, box) == "", box
    body = _save(wiz, EDIT)
    assert "price" not in body["spool_data"], body["spool_data"]
    for key in ("settings_extruder_temp", "settings_bed_temp"):
        assert key not in body["filament_data"], body["filament_data"]


def test_a_half_typed_number_is_never_a_clear(wiz):
    """A number box holding text that isn't a number yet ("-") reads as '' while it
    shows the text (validity.badInput). The user didn't empty it, so Save leaves
    the field as it is, as before. A pin: green on the base, red on a copy of the
    fix that reads only the box's value."""
    _open_edit(wiz)
    price = wiz.locator("#wiz-spool-price")
    price.fill("")
    price.press_sequentially("-")
    assert wiz.evaluate("() => { const e = document.getElementById('wiz-spool-price');"
                        " return [e.value, e.validity.badInput]; }") == ["", True]
    body = _save(wiz, EDIT)
    assert "price" not in body["spool_data"], body["spool_data"]


def test_create_mode_an_emptied_box_sends_nothing(wiz):
    """Control: a new filament and spool are a fresh record, so an empty box is
    simply left out, as before. Green on the base, and on the fix."""
    _open_new_filament(wiz)
    for box in ("#wiz-fil-settings_bed_temp", "#wiz-spool-price"):
        wiz.locator(box).fill("60")
        wiz.locator(box).fill("")
    body = _save(wiz, CREATE)
    assert "settings_bed_temp" not in body["filament_data"], body["filament_data"]
    assert "price" not in body["spool_data"], body["spool_data"]


def test_create_mode_still_cross_inherits_the_spools_empty_weight_to_the_filament(wiz):
    """Control: on a create the cross-inherit still fills the filament's empty box
    from the spool's, even after the user emptied it (only Edit Spool reads an
    emptied box as a clear). Green on the base, and on the fix (proved on a copy
    that skips the cross-inherit for any touched box)."""
    _open_new_filament(wiz)
    wiz.locator("#wiz-fil-empty_weight").fill("200")
    assert _value(wiz, "#wiz-spool-empty_weight") == "200"          # the copy into the spool's box
    wiz.locator("#wiz-fil-empty_weight").fill("")
    wiz.locator("#wiz-spool-empty_weight").fill("196")
    body = _save(wiz, CREATE)
    assert body["spool_data"]["spool_weight"] == 196, body["spool_data"]
    assert body["filament_data"]["spool_weight"] == 196, body["filament_data"]


def test_only_the_boxes_the_user_changes_count_as_touched(wiz):
    """Values set by code (the edit's prefill, the filament box's copy into the
    spool's) are no touch; a typed value is. Red on the base: there is no set."""
    _open_edit(wiz)
    assert _touched(wiz) == []
    wiz.locator("#wiz-fil-settings_extruder_temp").fill("220")
    wiz.locator("#wiz-fil-empty_weight").fill("205")
    assert _value(wiz, "#wiz-spool-empty_weight") == "205"
    assert _touched(wiz) == ["fil:settings_extruder_temp", "fil:spool_weight"]
    assert wiz.evaluate("() => [wizardNativeTouched('fil', 'spool_weight'),"
                        " wizardNativeTouched('spool', 'spool_weight'), wizardNativeTouched('spool', 'price')]"
                        ) == [True, False, False]


def test_the_next_wizard_session_forgets_a_touch(wiz):
    """A box emptied in one session says nothing about the next spool edited: its
    filament has no bed temperature, the box is drawn empty, and nothing is sent.
    RED on the base at its first step (there is no touched set); its last step is
    a pin, red on a copy of the fix whose wizardReset keeps the set.

    The box keeps the focus from the first session here, so the Save click's blur
    fires a `change` on it in the second (Chromium fires it for an edit made
    before the reset). A first build that counted `change` too sent the new
    spool's empty bed temperature as a clear: only `input` counts as a touch."""
    _open_edit(wiz)
    wiz.locator("#wiz-fil-settings_bed_temp").fill("")
    assert _touched(wiz) == ["fil:settings_bed_temp"]
    _open_edit(wiz, bed=None)
    assert _touched(wiz) == []
    body = _save(wiz, EDIT)
    assert "settings_bed_temp" not in body["filament_data"], body["filament_data"]


# --- a scanner's label in a number box (Group 54 review, R2-2) --------------------------
#
# With a box's value selected (the focus came by Tab), Chromium's number box rejects
# a scanned label's letters, but its first rejected key still deletes the selection
# and fires ONE `input` (insertText, the box now '' with no badInput). The scan goes
# nowhere (the scan accumulator leaves a box's keys to the box, and the wizard has no
# field scan capture), and the emptied box counted as the person's: 54.5's touched
# set took it as a clear, and Spoolman wiped the field at Save. A key the box can't
# take is no edit now: the box gets its value back, still selected, and nothing counts
# it. A label with none of [0-9eE+-.] in it does this (LOC:XL, CMD:UNDO, CMD:AUDIT).

LABELS = ["LOC:XL", "CMD:UNDO"]


def _tab_in(page, box):
    """The focus arrives by Tab, so the box's value is selected, as Chromium does."""
    page.focus(box)
    page.keyboard.press("Shift+Tab")
    page.keyboard.press("Tab")
    assert page.evaluate("(s) => document.activeElement === document.querySelector(s)", box)


def _scan_into(page, box, label):
    _tab_in(page, box)
    page.keyboard.type(label, delay=8)          # a scanner types its label, then Enter
    page.keyboard.press("Enter")


@pytest.mark.parametrize("label", LABELS)
def test_a_scanned_label_never_clears_the_bed_temperature(wiz, label):
    """RED on the base: the box empty and `settings_bed_temp: null` sent, which
    Spoolman takes as "no value"."""
    _open_edit(wiz)
    _scan_into(wiz, "#wiz-fil-settings_bed_temp", label)
    assert _value(wiz, "#wiz-fil-settings_bed_temp") == "60"
    assert _touched(wiz) == []
    body = _save(wiz, EDIT)
    assert body["filament_data"]["settings_bed_temp"] == 60, _got(body["filament_data"], "settings_bed_temp")


@pytest.mark.parametrize("box,part,key", BOXES, ids=[b[0][1:] for b in BOXES])
def test_a_scanned_label_clears_none_of_the_five_boxes(wiz, box, part, key):
    """Every box the touched set reads. RED on the base for all five: null sent."""
    _open_edit(wiz)
    shown = _value(wiz, box)
    assert shown != ""
    _scan_into(wiz, box, "LOC:XL")
    assert _value(wiz, box) == shown
    assert _touched(wiz) == []
    body = _save(wiz, EDIT)
    assert _got(body[part], key) is not None, (key, _got(body[part], key))


def test_a_scanned_label_leaves_a_marked_price_marked_and_unsent(wiz):
    """A spool with no price of its own shows its filament's 25 "↩ from filament"
    (Group 54.8). RED on the base: the box emptied, the mark gone, and `price: null`
    sent."""
    _open_edit(wiz, price=None)
    _scan_into(wiz, "#wiz-spool-price", "LOC:XL")
    assert _value(wiz, "#wiz-spool-price") == "25"
    assert wiz.evaluate("() => [wizardSpoolPriceIsFilaments(), getComputedStyle("
                        "document.getElementById('wiz-spool-price-inherited-badge')).display !== 'none']") == [True, True]
    body = _save(wiz, EDIT)
    assert "price" not in body["spool_data"], _got(body["spool_data"], "price")


def test_a_scanned_label_leaves_an_inherited_empty_weight_marked_and_unsent(wiz):
    """The spool's empty weight it only inherits (its filament's 200, "↩ from
    filament"). RED on the base: the box emptied, its badge hidden, and
    `spool_weight: null` sent."""
    _open_edit(wiz, spool_wt=None)
    _scan_into(wiz, "#wiz-spool-empty_weight", "CMD:UNDO")
    assert _value(wiz, "#wiz-spool-empty_weight") == "200"
    assert wiz.evaluate("() => [wizardSpoolEmptyWeightIsInherited(), getComputedStyle("
                        "document.getElementById('wiz-spool-empty-inherited-badge')).display !== 'none']") == [True, True]
    body = _save(wiz, EDIT)
    assert "spool_weight" not in body["spool_data"], _got(body["spool_data"], "spool_weight")


def test_a_scanned_label_never_zeroes_the_used_weight(wiz):
    """Claude's call: every number box in the wizard, not just the five. An emptied
    Total Used box is sent as 0, a refill of a spool with 500 g used. RED on the
    base: `used_weight: 0`."""
    _open_edit(wiz)
    assert _value(wiz, "#wiz-spool-used") == "500"
    _scan_into(wiz, "#wiz-spool-used", "LOC:XL")
    assert _value(wiz, "#wiz-spool-used") == "500"
    assert _save(wiz, EDIT)["spool_data"]["used_weight"] == 500


def test_a_persons_backspace_still_empties_the_box(wiz):
    """A person's own Delete or Backspace is an edit, and in Edit Spool a clear. A
    pin: green on the base, red on a fix that also undoes a deletion."""
    _open_edit(wiz)
    _tab_in(wiz, "#wiz-fil-settings_bed_temp")
    wiz.keyboard.press("Backspace")
    assert _value(wiz, "#wiz-fil-settings_bed_temp") == ""
    body = _save(wiz, EDIT)
    assert _got(body["filament_data"], "settings_bed_temp") is None, _got(body["filament_data"], "settings_bed_temp")


def test_a_persons_digits_over_the_selected_value_are_an_edit(wiz):
    """A key the box takes replaces the selection, as before. A pin: green on the
    base, red on a fix that undoes every insert into a selected box."""
    _open_edit(wiz)
    _tab_in(wiz, "#wiz-fil-settings_bed_temp")
    wiz.keyboard.type("65")
    assert _value(wiz, "#wiz-fil-settings_bed_temp") == "65"
    assert _touched(wiz) == ["fil:settings_bed_temp"]
    assert _save(wiz, EDIT)["filament_data"]["settings_bed_temp"] == 65


# --- the real dashboard ------------------------------------------------------------------

@pytest.mark.usefixtures("require_server")
def test_the_real_page_sends_null_for_an_emptied_bed_temperature(page, base_url):
    """The bug on the real dashboard and real Bootstrap: empty the filament's Bed
    Min, Save. Dev's spool data is a stub, and Save's POST is read and answered in
    the browser, so nothing reaches dev. RED on the base: the key is missing."""
    from test_text_size_guard import _read_only

    seen = []

    def grab(route):
        seen.append(route.request.post_data_json)
        route.fulfill(status=200, content_type="application/json", body='{"success": true, "spool_id": 57}')

    _read_only(page, extra_get={"/api/spool_details": _details()})
    page.route("**/api/edit_spool_wizard", grab)
    page.goto(base_url)
    page.wait_for_function("() => typeof window.openEditWizard === 'function' && typeof state !== 'undefined'"
                           " && state.locationsLoaded", timeout=45_000)
    page.evaluate("() => { window.openEditWizard(57); }")
    page.wait_for_function("() => wizardState.mode === 'edit_spool'"
                           " && document.getElementById('wiz-fil-settings_bed_temp').value === '60'"
                           " && !document.getElementById('btn-wiz-submit').disabled", timeout=15_000)
    # Every optional section opens collapsed, edit mode too: open Print Temperatures
    # as a person would.
    page.locator('button.fcc-wiz-section-toggle[data-bs-target="#wiz-fil-temps-panel"]').click()
    page.wait_for_function("() => { const p = document.getElementById('wiz-fil-temps-panel');"
                           " return p.classList.contains('show') && !p.classList.contains('collapsing'); }")
    page.locator("#wiz-fil-settings_bed_temp").fill("")
    with page.expect_response("**/api/edit_spool_wizard"):
        page.locator("#btn-wiz-submit").click()
    assert len(seen) == 1, seen
    fil = seen[0]["filament_data"]
    assert "settings_bed_temp" in fil and fil["settings_bed_temp"] is None, fil
    assert fil["settings_extruder_temp"] == 215, fil                   # its neighbour, untouched


# --- the server half needs nothing -------------------------------------------------------

def test_the_route_passes_each_null_through_to_spoolman(monkeypatch):
    """The server half, pinned: the edit's nulls reach Spoolman's PATCH as nulls,
    on the real route and the real update_spool / update_filament over
    SpoolmanHTTPFake. Green on the base: only the page changed."""
    import app as app_module
    import spoolman_api
    import state

    monkeypatch.setattr(state, "add_log_entry", lambda *a, **k: None)
    for name in ("_FIELD_SCHEMA_CACHE", "_SPOOLMAN_VERSION_CACHE"):
        getattr(spoolman_api, name, {}).clear()
    fake = SpoolmanHTTPFake(version="0.27.1")
    fake.add("filament", 7, {}, name="Red", material="PLA", spool_weight=200.0, price=25.0,
             settings_extruder_temp=215, settings_bed_temp=60, weight=1000.0)
    fake.add("spool", 57, {}, location="SHELF-1", used_weight=500.0, initial_weight=1000.0,
             price=30.0, spool_weight=196.0, comment="", archived=False)
    client = app_module.app.test_client()
    with patch.object(spoolman_api.config_loader, "get_api_urls", return_value=("http://sm.test", "http://fb")), \
            patch.object(spoolman_api.requests, "get", side_effect=fake.get), \
            patch.object(spoolman_api.requests, "patch", side_effect=fake.patch):
        res = client.post(EDIT, json={
            "spool_id": 57, "filament_id": 7,
            "spool_data": {"used_weight": 500.0, "initial_weight": 1000.0, "location": "SHELF-1", "comment": "",
                           "price": None, "spool_weight": None, "archived": False, "extra": {}},
            "filament_data": {"name": "Red", "material": "PLA", "weight": 1000.0, "spool_weight": None,
                              "settings_extruder_temp": None, "settings_bed_temp": None, "extra": {}},
        }).get_json()
    for name in ("_FIELD_SCHEMA_CACHE", "_SPOOLMAN_VERSION_CACHE"):
        getattr(spoolman_api, name, {}).clear()
    assert res["success"] is True, res
    spool_patch = [b for e, i, b in fake.patches if (e, i) == ("spool", 57)]
    fil_patch = [b for e, i, b in fake.patches if (e, i) == ("filament", 7)]
    assert len(spool_patch) == 1 and len(fil_patch) == 1, fake.patches
    assert spool_patch[0]["price"] is None and spool_patch[0]["spool_weight"] is None, spool_patch
    assert "price" in spool_patch[0] and "spool_weight" in spool_patch[0], spool_patch
    for key in ("spool_weight", "settings_extruder_temp", "settings_bed_temp"):
        assert key in fil_patch[0] and fil_patch[0][key] is None, fil_patch
    rec = copy.deepcopy(fake.records)
    assert rec["spool"][57]["price"] is None and rec["spool"][57]["spool_weight"] is None, rec["spool"][57]
    assert json.dumps(rec["filament"][7]["settings_bed_temp"]) == "null", rec["filament"][7]
