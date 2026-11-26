"""Group 66.4: a label scanned into one of the wizard's boxes goes on as a scan, and the
wizard is as it was before the scan's first key.

The wizard's boxes had no scan capture: a label scanned while one had the keyboard was
typed there ("ID:57" in Comment, its digits in a number box), and its keys ran the
wizard's listeners as a person's typing does. So a scan meant for the dashboard changed
the form: Bed Min read 57, the box counted as the person's (Group 54.5's touched set, so
an emptied one became a clear), the inherited empty weight and the filament's price lost
their marks and were saved as the spool's own (54.8), a label in Scale Gross worked out
a used weight from its digits (Save wrote it), a label in Location blanked the place the
field held (Save moved the spool to Unassigned), and the form counted as changed (66.2's
guard then asked about nothing).

The rules now (window.wizardScanSnapshot / wizardScanRestore / wizardTookScan, on the
shared capture's new hooks):
  - a label (an FCC prefix, a web address, digits at scanner pace) scanned into a text or
    number box goes on as a scan, and every box, mark, touched set, the dirty flag and the
    weight grid's sums are put back as they stood before its first key;
  - a box that takes a web address (the Spool boxes, Purchase and Product Link, Import
    Database's search) keeps one; an FCC label there is a scan (Claude's call (c));
  - a place's label scanned into Location picks that place (a box's slot label picks its
    box and opens its picker); a place the list doesn't offer is refused, on the status
    line, in a warning toast and an Activity Log line;
  - a person's typing stays theirs.

Hermetic and page-level, on the Group 58.5 harness, so it runs under --offline; the
scan path is a stub recording what it is sent. Each case marked RED fails on the commit
before this one for the reason it names.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from test_scanner_safe_dialogs_61_js import TYPE_BOX_JS
from test_wizard_label_status_58_5 import _save
from test_wizard_label_status_58_5 import _touched as _extras_touched
from test_wizard_native_clear_54_5 import _details, _got, _open_edit, _open_new_filament, _scan_into, _tab_in, _touched, _value, wiz  # noqa: F401
from test_wizard_price_mark_54_8 import _badge
from test_wizard_vendor_66_1 import _brand, _open_edit_with

EDIT = "/api/edit_spool_wizard"
CREATE = "/api/create_inventory_wizard"
LOCATION = "#wiz-spool-location-search"
PRUSAMENT = "https://prusament.com/spool/17705/abc123def0/"

SCAN_STUB = r"""() => {
    window.__scans = [];
    window.processScan = (t, s) => { window.__scans.push([t, s]); };
    window.__logs = [];
    window.logClientEvent = (m, lvl) => { window.__logs.push([lvl, m]); };
}"""


@pytest.fixture
def scanning(wiz):  # noqa: F811
    wiz.evaluate(SCAN_STUB)
    yield wiz
    # Review round 2 of Group 66 (Q4-02): every case, not only those that save, fails on an
    # error thrown on the page (the slot label's case passed over one), and on a key that
    # changed a wizardState key the undo leaves alone.
    assert wiz.evaluate("() => window.__errors") == []
    assert wiz.evaluate("() => window.wizardScanUntracked") == []


def _scans(page):
    return page.evaluate("() => window.__scans.map((s) => s[0])")


def _dirty(page):
    return page.evaluate("() => wizardState.isDirty")


def _type_box(page, box, text, ms, enter=True):
    """Keys typed into a text box on the page's own clock (Group 61's helper)."""
    page.focus(box)
    page.evaluate(TYPE_BOX_JS, [text, ms, enter, {}])


def _keys_into(page, box, text):
    """Real keys at a scanner's pace, then Enter: for a box Group 61's helper doesn't type
    into (a link box is type="url")."""
    page.focus(box)
    page.keyboard.type(text, delay=5)
    page.keyboard.press("Enter")


# --- a label is a scan, and the wizard is as it was -------------------------------------------

@pytest.mark.parametrize("box", ["#wiz-spool-comment", "#wiz-fil-color_name", "#wiz_fil_ef_drying_temp"])
def test_a_label_in_a_text_box_is_a_scan_and_the_wizard_is_as_it_was(scanning, box):
    """RED: no scan; "ID:57" stayed in the box, and the form counted as changed."""
    _open_edit(scanning)
    before = _value(scanning, box)
    _scan_into(scanning, box, "ID:57")
    assert _scans(scanning) == ["ID:57"]
    assert _value(scanning, box) == before
    assert (_dirty(scanning), _touched(scanning), _extras_touched(scanning)) == (False, [], [])
    scanning.keyboard.press("Tab")                  # its blur: no change counted either
    assert _dirty(scanning) is False


def test_a_label_over_a_tab_selected_bed_min_leaves_it_and_its_touch(scanning):
    """RED: Bed Min read 57 (the label's digits), counted as the person's, and was sent."""
    _open_edit(scanning)
    _scan_into(scanning, "#wiz-fil-settings_bed_temp", "ID:57")
    assert (_value(scanning, "#wiz-fil-settings_bed_temp"), _touched(scanning)) == ("60", [])
    assert _scans(scanning) == ["ID:57"] and _dirty(scanning) is False
    assert _save(scanning, EDIT)["filament_data"]["settings_bed_temp"] == 60


def test_a_label_leaves_an_inherited_empty_weight_marked_and_unsent(scanning):
    """54.8's mark. RED: 57 sent as the spool's own empty weight."""
    _open_edit(scanning, spool_wt=None)
    _scan_into(scanning, "#wiz-spool-empty_weight", "ID:57")
    assert (_value(scanning, "#wiz-spool-empty_weight"), _badge(scanning, "#wiz-spool-empty-inherited-badge")) == ("200", True)
    assert "spool_weight" not in _save(scanning, EDIT)["spool_data"]


def test_a_label_leaves_the_filaments_price_marked_and_unsent(scanning):
    """54.8's price mark. RED: the label's digits sent as the spool's own price."""
    _open_edit(scanning, price=None)
    _scan_into(scanning, "#wiz-spool-price", "ID:57")
    assert (_value(scanning, "#wiz-spool-price"), _badge(scanning)) == ("25", True)
    assert "price" not in _save(scanning, EDIT)["spool_data"]


def test_a_label_leaves_the_filaments_brand_weight_marked_and_unsent(scanning):
    """66.7's mark. RED: the label's digits taken as the filament's own empty weight."""
    _open_edit(scanning, spool_wt=None, fil_wt=None, vendor_wt=167.0)
    _scan_into(scanning, "#wiz-fil-empty_weight", "ID:57")
    assert (_value(scanning, "#wiz-fil-empty_weight"), _badge(scanning, "#wiz-fil-empty-inherited-badge")) == ("167", True)
    assert scanning.evaluate("() => wizardState.spoolEmptyWeightFrom") == "vendor"
    body = _save(scanning, EDIT)
    assert "spool_weight" not in body["filament_data"], _got(body["filament_data"], "spool_weight")


def test_a_label_in_the_vendor_box_keeps_the_manufacturer_it_held(scanning):
    """66.1's held id under a shared name. RED: the box lost its id (the label's text
    matched no manufacturer), and Save sent none."""
    _open_edit_with(scanning, {"success": True, "vendors": [_brand(1), _brand(2)]})
    _scan_into(scanning, "#wiz-fil-vendor-search", "ID:57")
    assert (_value(scanning, "#wiz-fil-vendor-search"), _value(scanning, "#wiz-fil-vendor-sel")) == ("Some Brand", "2")
    assert _save(scanning, EDIT)["filament_data"].get("vendor_id") is None  # unchanged: left out (Group 66.9 review: Edit Spool sends a manufacturer only when it changed), so the filament keeps #2


def test_a_label_in_scale_gross_works_out_no_used_weight(scanning):
    """RED: a used weight worked out from the label's digits, and sent."""
    _open_edit(scanning)
    _scan_into(scanning, "#wiz-spool-scale", "ID:57")
    assert (_value(scanning, "#wiz-spool-scale"), _value(scanning, "#wiz-spool-used")) == ("", "500")
    assert "used_weight" not in _save(scanning, EDIT)["spool_data"]


def test_a_label_in_total_used_keeps_the_scale_reading(scanning):
    """A reading typed in Scale Gross (Total Used worked out from it), then a label scanned
    into Total Used: both stay. RED: the label's keys blanked the Scale box."""
    _open_edit(scanning)
    _tab_in(scanning, "#wiz-spool-scale")
    scanning.keyboard.type("1100", delay=120)
    used = _value(scanning, "#wiz-spool-used")
    # The keyboard goes to Total Used with no key (a click): any key's keyup there works
    # the sums out again and empties Scale Gross (the weight grid's own rule), a Tab's too.
    scanning.focus("#wiz-spool-used")
    scanning.keyboard.type("ID:57", delay=8)
    scanning.keyboard.press("Enter")
    assert (_value(scanning, "#wiz-spool-scale"), _value(scanning, "#wiz-spool-used")) == ("1100", used)
    assert _scans(scanning) == ["ID:57"]


def test_a_label_in_location_keeps_a_place_the_list_doesnt_show(scanning):
    """An edit of a spool on a head (the list leaves heads out). RED: the field lost its
    place, and Save moved the spool to Unassigned."""
    scanning.evaluate("() => { window.__answers['/api/locations'] = ["
                      " { LocationID: 'SHELF-1', Name: 'Shelf', Type: 'Section' },"
                      " { LocationID: 'HEAD-1', Name: 'HEAD-1', Type: 'Tool Head' }]; }")
    details = _details()
    details["location"] = "HEAD-1"
    scanning.evaluate("(d) => { window.__answers['/api/spool_details'] = d; window.openEditWizard(57); }", details)
    scanning.wait_for_function("() => wizardState.mode === 'edit_spool' && wizardState.selectedFilamentId === 7"
                               " && document.getElementById('wiz-fil-color_name').value === 'Red'"
                               " && !document.getElementById('btn-wiz-submit').disabled")
    shown = _value(scanning, LOCATION)
    _scan_into(scanning, LOCATION, "ID:57")
    assert (_value(scanning, LOCATION), _value(scanning, "#wiz-spool-location")) == (shown, "HEAD-1")
    assert _scans(scanning) == ["ID:57"]
    assert _got(_save(scanning, EDIT)["spool_data"], "location") in ("HEAD-1", "<missing>")


@pytest.mark.parametrize("label", ["LOC:SHELF-1", "loc:shelf-1"])
def test_a_place_label_in_location_picks_it(scanning, label):
    """RED: the label stayed in the field as text, and no place was picked."""
    _open_new_filament(scanning)
    _scan_into(scanning, LOCATION, label)
    assert (_value(scanning, LOCATION), _value(scanning, "#wiz-spool-location")) == ("Shelf (SHELF-1)", "SHELF-1")
    assert _scans(scanning) == []


@pytest.mark.parametrize("label, said", [
    ("LOC:SHELF-9", "LOC:SHELF-9"),
    ("LOC:HEAD-1", "LOC:HEAD-1"),
    ("LOC:<b>X</b>", "LOC:&lt;B&gt;X&lt;/B&gt;"),
], ids=["unknown", "not-offered", "escaped"])
def test_a_place_the_list_doesnt_offer_is_refused(scanning, label, said):
    """Said on the status line, in a warning toast and one Activity Log WARNING (the scan's
    text escaped); nothing goes to the scan path and the field is as it was. RED: the
    label stayed in the field as text."""
    scanning.evaluate("() => { window.__answers['/api/locations'] = ["
                      " { LocationID: 'SHELF-1', Name: 'Shelf', Type: 'Section' },"
                      " { LocationID: 'HEAD-1', Name: 'HEAD-1', Type: 'Tool Head' }]; }")
    _open_new_filament(scanning)
    _scan_into(scanning, LOCATION, label)
    assert (_value(scanning, LOCATION), _value(scanning, "#wiz-spool-location")) == ("", "")
    assert _scans(scanning) == []
    assert "isn't a place this list offers" in scanning.locator("#wiz-status-msg").inner_text()
    logs = scanning.evaluate("() => window.__logs")
    assert len(logs) == 1 and logs[0][0] == "WARNING" and said in logs[0][1], logs
    assert scanning.locator("#toast-container .toast-warning").count() >= 1


def test_a_slot_label_picks_its_box_and_opens_its_picker(scanning):
    """A box's slot label picks the box, and its slot picker opens as a mouse pick opens
    it. RED: the label stayed in the field as text."""
    scanning.evaluate("() => { window.__answers['/api/locations'] = ["
                      " { LocationID: 'SHELF-1', Name: 'Shelf', Type: 'Section' },"
                      " { LocationID: 'BOX-1', Name: 'Dryer', Type: 'Dryer Box', 'Max Spools': '4' }];"
                      " window.__picker = []; window.placeOneWithPicker = (o) => { window.__picker.push(o && o.loc);"
                      "   return Promise.resolve({ outcome: 'moved' }); };"
                      " window.openSlotPicker = () => {}; }")
    _open_new_filament(scanning)
    _scan_into(scanning, LOCATION, "LOC:BOX-1:SLOT:2")
    assert _value(scanning, "#wiz-spool-location") == "BOX-1"
    assert scanning.evaluate("() => window.__picker") == ["BOX-1"]
    assert _scans(scanning) == []


# --- boxes that take a web address -------------------------------------------------------------

@pytest.mark.parametrize("box", ["#wiz-spool-purchase_url", "#wiz-spool-product_url", "#wiz-search-external"])
def test_a_web_address_stays_in_a_box_that_takes_one(scanning, box):
    """A pin: a Prusament QR (or a shop link) scanned into a link box stays there."""
    _open_new_filament(scanning)
    if box == "#wiz-search-external":
        scanning.evaluate("() => wizardSelectType('external')")
    _keys_into(scanning, box, PRUSAMENT)
    assert _value(scanning, box) == PRUSAMENT
    assert _scans(scanning) == []


def test_a_spool_label_in_a_link_box_is_a_scan(scanning):
    """Claude's call (c): an FCC label in a link box goes on as a scan. RED: "ID:57" saved as
    the spool's product link."""
    _open_edit(scanning)
    _keys_into(scanning, "#wiz-spool-product_url", "ID:57")
    assert (_value(scanning, "#wiz-spool-product_url"), _scans(scanning)) == ("", ["ID:57"])
    assert "ID:57" not in json.dumps(_save(scanning, EDIT))


def test_a_web_address_scanned_into_comment_is_a_scan_and_changes_nothing(scanning):
    """The cross-check's C7: a Prusament QR scanned into a box that takes no link goes on as
    a scan, and the form doesn't count as changed (66.2's guard then reads the truth).
    RED: the address stayed in Comment, and the form counted as changed."""
    _open_edit(scanning)
    _type_box(scanning, "#wiz-spool-comment", PRUSAMENT, 5)
    assert (_value(scanning, "#wiz-spool-comment"), _scans(scanning), _dirty(scanning)) == ("", [PRUSAMENT], False)


# --- a person's typing stays theirs ---------------------------------------------------------------

@pytest.mark.parametrize("words", ["Box ID:3", "Grid:2", "Shelf: top"])
def test_a_persons_typing_stays(scanning, words):
    """A pin: words with a colon typed at a person's pace stay in the box."""
    _open_edit(scanning)
    _type_box(scanning, "#wiz-spool-comment", words, 120)
    assert (_value(scanning, "#wiz-spool-comment"), _scans(scanning)) == (words, [])


def test_a_cr_lf_scanners_second_enter_does_nothing_more(scanning):
    """One scan, whatever the scanner's line end. RED: no scan, the label in the box."""
    _open_edit(scanning)
    scanning.focus("#wiz-spool-comment")
    scanning.evaluate(TYPE_BOX_JS, [list("ID:57") + ["Enter", "Enter"], 5, False, {}])
    assert (_value(scanning, "#wiz-spool-comment"), _scans(scanning)) == ("", ["ID:57"])


def test_after_a_create_a_scan_into_a_box_keeps_save_locked(scanning):
    """After a create, Save stays locked until the person changes something: a scan isn't a
    change. RED: the label's keys unlocked Save (a second click makes the same spools)."""
    _open_new_filament(scanning)
    _save(scanning, CREATE)
    scanning.wait_for_function("() => document.getElementById('btn-wiz-submit').disabled")
    status = scanning.locator("#wiz-status-msg").inner_html()
    _type_box(scanning, "#wiz-spool-comment", "ID:57", 5)
    assert _scans(scanning) == ["ID:57"]
    assert scanning.evaluate("() => document.getElementById('btn-wiz-submit').disabled") is True
    assert scanning.locator("#wiz-status-msg").inner_html() == status


def test_the_existing_search_lists_for_what_its_box_holds(scanning):
    """"sun" typed in Existing Filament's search, then a label scanned there: the list is
    the one for "sun". RED: the list was searched for the label's text (nothing)."""
    sunlu = dict(_details()["filament"], id=9, name="Sunlu Black")
    sunlu["vendor"] = dict(_brand(4, name="Sunlu"))
    scanning.evaluate("(f) => { window.__answers['/api/filaments'] = { success: true, filaments: [f] }; }", sunlu)
    scanning.evaluate("() => window.openWizardModal()")
    scanning.wait_for_function("() => !!document.getElementById('wiz_fil_ef_needs_label_print')")
    scanning.locator("#btn-type-existing").click()
    _type_box(scanning, "#wiz-search-existing", "sun", 120, enter=False)
    scanning.evaluate("() => window.wizardSearchExisting()")
    scanning.wait_for_function("() => !!document.querySelector(\"#wiz-existing-results option[value='9']\")")
    scanning.evaluate("() => { window.__T += 700; }")      # a moment later, the scan
    _type_box(scanning, "#wiz-search-existing", "ID:57", 5)
    scanning.wait_for_timeout(200)
    assert _value(scanning, "#wiz-search-existing") == "sun"
    assert scanning.locator("#wiz-existing-results option[value='9']").count() == 1
    assert _scans(scanning) == ["ID:57"]


# --- every wizardState key is put back, or said not to be (the cross-check's C6) -------------

JS = Path(__file__).resolve().parents[1] / "static" / "js"


def _js_list(src, name):
    m = re.search(r"window\." + name + r"\s*=\s*\[(.*?)\];", src, re.S)
    assert m, f"inv_wizard.js has no window.{name}"
    return re.findall(r"'([^']+)'", m.group(1))


def test_every_wizard_state_key_is_put_back_or_said_not_to_be():
    """A key a label's keys can change has to be put back by the restore, or the scan
    leaves its trace (66.1, 66.5 and 66.7 each added one after 66.4 was designed). Every
    `wizardState` key in the page's code is listed once: in WIZ_SCAN_STATE_KEYS (put
    back) or WIZ_SCAN_STATE_SKIPS (a label's keys can't change it). A new key fails here
    until someone decides. RED: no lists."""
    wiz = (JS / "modules" / "inv_wizard.js").read_text(encoding="utf-8")
    keys = set()
    for p in JS.rglob("*.js"):
        keys |= set(re.findall(r"wizardState\.([A-Za-z_]\w*)", p.read_text(encoding="utf-8")))
    start = wiz.index("let wizardState = {")
    keys |= set(re.findall(r"^\s{4}(\w+):", wiz[start:wiz.index("};", start)], re.M))
    snap, skip = set(_js_list(wiz, "WIZ_SCAN_STATE_KEYS")), set(_js_list(wiz, "WIZ_SCAN_STATE_SKIPS"))
    assert not snap & skip, sorted(snap & skip)
    missing = sorted(keys - snap - skip)
    assert not missing, (f"wizardState keys neither put back nor said not to be: {missing}. Add each to "
                         f"WIZ_SCAN_STATE_KEYS (a label's keys can change it) or WIZ_SCAN_STATE_SKIPS "
                         f"(they can't) in inv_wizard.js.")
    assert not (snap | skip) - keys, f"listed but no longer a wizardState key: {sorted((snap | skip) - keys)}"


# --- the touched set hears `input` only --------------------------------------------------------

def test_a_change_with_no_input_is_no_touch(scanning):
    """A `change` with no `input` before it (the blur of an edit made before the last
    reset, Chromium's stale change) touches no extra. RED: drying_temp counted."""
    _open_edit(scanning)
    scanning.evaluate("() => document.getElementById('wiz_fil_ef_drying_temp')"
                      ".dispatchEvent(new Event('change', { bubbles: true }))")
    assert _extras_touched(scanning) == []
