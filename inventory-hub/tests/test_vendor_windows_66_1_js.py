"""Group 66.1 and 66.7 in Edit Filament: a manufacturer saved reaches the open window, the
window keeps a filament's manufacturer by its id, and a weight it only inherits is never
saved as the filament's own.

Derek, 2026-11-11: "you have to close out of the modals before updating the vendor data
(spool weight) gets propagated into the auto fills". The vendor editor told Edit Filament
only the vendor's new name: its "ⓘ … g empty" pill, the "(vendor: N g)" hint, Use Vendor
and the box kept the old weight until the window was opened again. After a rename from
inside the window the stale list didn't know the new name, so the box was marked "+ NEW"
and Save created a second vendor and moved the filament onto it. The window looked a
vendor up by NAME, first in list order, so a Save of a filament on one of Derek's
duplicated names (Sunlu #35) moved it onto Sunlu #4; and a vendor list that came back
empty after a Spoolman blip marked the filament's own vendor "+ NEW", and Save created a
duplicate. And a filament with no empty weight of its own showed its vendor's in the box,
unmarked, and every Save wrote it as the filament's own (66.7).

Now: the window keeps the vendor it holds by its id while its box shows that vendor's
name (a typed name is looked up, the filament's own vendor first, else the lowest id);
"+ NEW" only once the list was read and holds no such name; a saved or created vendor
updates the list at once, then the list is read again; what comes from the vendor (the
name, the pill, the hint, the placeholder, Use Vendor, and a box that only shows what it
inherits) is redrawn, as code (no edit of the form); the box shows "↩ from vendor" while
it inherits (Derek's D2 (a)) and Save leaves such a value out; a name another vendor has
uses that vendor (the server's 409) and says so; the combobox binds once.

On the shared hermetic page (tests/edit_filament_harness.py), so it runs under --offline.
"""
from __future__ import annotations

import pytest

from edit_filament_harness import asked, errors, filament, load, open_form, posts_to

BRAND = {"id": 2, "name": "Some Brand", "empty_spool_weight": 180.0, "external_id": "", "extra": {}}
SUNLU4 = {"id": 4, "name": "Sunlu", "empty_spool_weight": 167.0, "external_id": "", "extra": {}}
SUNLU35 = {"id": 35, "name": "Sunlu", "empty_spool_weight": None, "external_id": "Sunlu", "extra": {}}
VENDORS = {"success": True, "vendors": [BRAND, SUNLU4, SUNLU35]}


@pytest.fixture
def ef(isolated_page):
    return load(isolated_page, {"/api/vendors": VENDORS})


def _ui(page):
    return page.evaluate("""() => ({
        box: document.getElementById('editfil-spool-weight').value,
        placeholder: document.getElementById('editfil-spool-weight').placeholder,
        hint: document.getElementById('editfil-vendor-wt-hint').innerText,
        badge: (() => { const b = document.getElementById('editfil-spool-weight-inherited-badge');
                        return !!b && b.style.display !== 'none' && b.getClientRects().length > 0; })(),
        pill: (() => { const p = document.getElementById('editfil-vendor-info');
                       return p && p.style.display !== 'none' ? p.innerText : ''; })(),
        isNew: document.getElementById('editfil-vendor-new-badge').style.display !== 'none',
        vendorId: document.getElementById('editfil-vendor-id').value,
        vendorName: document.getElementById('editfil-vendor-name').value,
        useVendor: (() => { const u = document.getElementById('editfil-copy-vendor-wt');
                            return u.style.display === 'none' ? null : u.title; })() })""")


def _specs(page):
    page.locator("#editfil-tab-specs-btn").click()


def _server_has(page, vendors):
    """What /api/vendors answers from now on (the window reads the list again after a save)."""
    page.evaluate("(v) => { window.__answers['/api/vendors'] = { success: true, vendors: v }; }", vendors)


def _vendor_saved(page, v, event="vendor:updated"):
    page.evaluate("([v, ev]) => document.dispatchEvent(new CustomEvent(ev, { detail: { id: String(v.id), vendor: v } }))",
                  [v, event])
    page.wait_for_timeout(80)


def _save_body(page):
    page.locator("#editfil-save").click()
    page.wait_for_timeout(120)
    sent = posts_to(page, "/api/update_filament")
    assert len(sent) == 1, page.evaluate("window.__posts")
    return sent[0]["body"]["data"]


def test_a_vendor_saved_over_the_window_redraws_what_comes_from_it(ef):
    """RED on the base: the pill, the hint, Use Vendor and the box kept 180."""
    open_form(ef, filament(vendor=dict(BRAND), spool_weight=None))
    _specs(ef)
    ui = _ui(ef)
    assert (ui["box"], ui["badge"], ui["pill"], ui["hint"]) == ("180", True, "ⓘ 180g empty", "(vendor: 180g)"), ui
    reads = len([f for f in ef.evaluate("window.__fetches") if f["url"] == "/api/vendors"])
    saved = dict(BRAND, empty_spool_weight=200.0)
    _server_has(ef, [saved, SUNLU4, SUNLU35])     # the list read again after the save
    _vendor_saved(ef, saved)
    ui = _ui(ef)
    assert (ui["box"], ui["badge"], ui["pill"], ui["hint"], ui["placeholder"]) == \
        ("200", True, "ⓘ 200g empty", "(vendor: 200g)", "200"), ui
    assert "200g" in (ui["useVendor"] or ""), ui
    assert len([f for f in ef.evaluate("window.__fetches") if f["url"] == "/api/vendors"]) == reads + 1
    # Code redrew it: no edit of the form, so the window closes with no question.
    ef.locator("#editFilamentModal .modal-footer [data-bs-dismiss='modal']").click()
    ef.wait_for_timeout(50)
    assert not asked(ef)
    assert errors(ef) == []


def test_a_typed_weight_stays_through_a_vendor_save_and_is_saved(ef):
    open_form(ef, filament(vendor=dict(BRAND), spool_weight=None))
    _specs(ef)
    ef.locator("#editfil-spool-weight").fill("205")
    saved = dict(BRAND, empty_spool_weight=200.0)
    _server_has(ef, [saved, SUNLU4, SUNLU35])
    _vendor_saved(ef, saved)
    ui = _ui(ef)
    assert (ui["box"], ui["badge"]) == ("205", False), ui
    assert _save_body(ef)["spool_weight"] == 205


def test_a_weight_the_filament_only_inherits_is_never_saved_as_its_own(ef):
    """66.7. RED on the base: every Save wrote the vendor's 180 as the filament's own."""
    open_form(ef, filament(vendor=dict(BRAND), spool_weight=None))
    ef.locator("#editfil-name").fill("Red Two")
    assert _save_body(ef) == {"name": "Red Two"}


def test_use_vendor_makes_it_the_filaments_own(ef):
    """A pin: the person's Use Vendor is their choice, saved as the filament's own."""
    open_form(ef, filament(vendor=dict(BRAND), spool_weight=None))
    _specs(ef)
    ef.locator("#editfil-copy-vendor-wt").click()
    assert _ui(ef)["badge"] is False
    assert _save_body(ef)["spool_weight"] == 180


def test_an_own_weight_emptied_is_cleared(ef):
    """A pin (54.5's rule): a box the person emptied sends null."""
    open_form(ef, filament(vendor=dict(BRAND), spool_weight=150.0))
    _specs(ef)
    assert _ui(ef)["badge"] is False
    ef.locator("#editfil-spool-weight").fill("")
    assert _save_body(ef)["spool_weight"] is None


def test_a_filament_storing_0_with_no_vendor_weight_isnt_rewritten(ef):
    """66.7's grounding: such a filament shows an empty box (0 reads as no value), and
    every Save of any edit wrote null over the 0. Only a box the person changed is sent
    now. RED on the base: spool_weight null went out with a name change."""
    open_form(ef, filament(vendor=dict(SUNLU35), spool_weight=0.0))     # no weight of its own, nor its vendor
    assert _ui(ef)["box"] == ""
    ef.locator("#editfil-name").fill("Red Two")
    assert _save_body(ef) == {"name": "Red Two"}


def test_a_filament_on_a_shared_name_keeps_its_own_vendor(ef):
    """Derek's Sunlu #4 and #35. RED on the base: the list moved the hidden id to #4, and
    a Save of the name alone moved the filament onto it."""
    open_form(ef, filament(vendor=dict(SUNLU35), spool_weight=150.0))
    assert _ui(ef)["vendorId"] == "35"
    ef.locator("#editfil-name").fill("Orange Two")
    assert _save_body(ef) == {"name": "Orange Two"}


@pytest.mark.parametrize("answer", [{"__status": 502, "__body": {"success": False, "msg": "x"}},
                                    {"success": True, "vendors": []}, "__reject__"])
def test_a_vendor_list_it_couldnt_read_never_marks_its_own_vendor_new(ef, answer):
    """RED on the base for the empty list (what the old server answered after a blip): the
    filament's own vendor was "+ NEW" and Save created a second vendor of that name."""
    ef.evaluate("(a) => { window.__answers['/api/vendors'] = a; }", answer)
    open_form(ef, filament(vendor=dict(BRAND), spool_weight=150.0))
    ui = _ui(ef)
    assert (ui["isNew"], ui["vendorId"]) == (False, "2"), ui
    ef.locator("#editfil-name").fill("Red Two")
    assert _save_body(ef) == {"name": "Red Two"}
    assert posts_to(ef, "/api/vendors") == []


def test_a_rename_from_inside_the_window_makes_no_second_vendor(ef):
    """RED on the base: the stale list didn't know the new name, the box was marked
    "+ NEW", and Save created a second vendor and moved the filament onto it."""
    open_form(ef, filament(vendor=dict(BRAND), spool_weight=150.0))
    renamed = dict(BRAND, name="Some Brand Two")
    ef.evaluate("(v) => { window.__answers['/api/vendors'] = { success: true, vendors: [v] }; }", renamed)
    _vendor_saved(ef, renamed)
    ui = _ui(ef)
    assert (ui["vendorName"], ui["vendorId"], ui["isNew"]) == ("Some Brand Two", "2", False), ui
    ef.locator("#editfil-name").fill("Red Two")
    assert _save_body(ef) == {"name": "Red Two"}
    assert posts_to(ef, "/api/vendors") == []


def test_a_vendor_created_elsewhere_is_known_at_once(ef):
    """A name typed as new, then a vendor of that name created (the vendor window, over
    the window): the box takes it, and Save uses it instead of creating another."""
    open_form(ef, filament(vendor=dict(BRAND), spool_weight=150.0))
    ef.locator("#editfil-vendor-name").fill("Fresh Brand")
    assert _ui(ef)["isNew"] is True
    fresh = {"id": 50, "name": "Fresh Brand", "empty_spool_weight": None, "external_id": "", "extra": {}}
    _server_has(ef, [BRAND, SUNLU4, SUNLU35, fresh])
    _vendor_saved(ef, fresh, event="vendor:created")
    ui = _ui(ef)
    assert (ui["vendorId"], ui["isNew"]) == ("50", False), ui
    assert _save_body(ef)["vendor_id"] == 50
    assert posts_to(ef, "/api/vendors") == []


def test_a_new_name_another_vendor_has_uses_that_vendor_and_says_so(ef):
    """The server's 409 (66.1): Save takes the vendor it names. RED on the base: the
    Save stopped with "Couldn't create vendor"."""
    ef.evaluate("""() => { window.__answers['POST /api/vendors'] = { __status: 409, __body: { success: false,
        msg: 'A manufacturer named "Brand X" already exists (#7), so nothing was created.',
        existing: { id: 7, name: 'Brand X' } } }; }""")
    open_form(ef, filament(vendor=dict(BRAND), spool_weight=150.0))
    ef.locator("#editfil-vendor-name").fill("Brand X")
    assert _save_body(ef)["vendor_id"] == 7
    assert "Brand X (#7)" in ef.locator("#toast-container").inner_text()


def test_add_filament_shows_a_picked_vendors_weight_and_leaves_it_out(ef):
    """A new filament inherits its vendor's weight (the grounding's C15): the box shows
    it, marked, and the create sends none. RED on the base: the box stayed empty."""
    ef.evaluate("() => window.openAddFilamentForm()")
    ef.wait_for_function("() => document.getElementById('editFilamentModal').classList.contains('show')")
    ef.wait_for_timeout(80)
    ef.locator("#editfil-name").fill("New One")
    ef.locator("#editfil-material").fill("PLA")
    ef.locator("#editfil-vendor-name").fill("Some Brand")
    _specs(ef)
    ui = _ui(ef)
    assert (ui["vendorId"], ui["box"], ui["badge"]) == ("2", "180", True), ui
    ef.locator("#editfil-save").click()
    ef.wait_for_timeout(120)
    sent = posts_to(ef, "/api/create_filament")
    assert len(sent) == 1 and sent[0]["body"]["data"].get("spool_weight") is None, sent


def test_the_vendor_combobox_binds_once(ef):
    """Each open added its four listeners again, so after a second open one ArrowDown
    moved the highlight twice (and a keyboard pick used the first open's list). RED on
    the base."""
    open_form(ef, filament(vendor=dict(BRAND), spool_weight=150.0))
    ef.evaluate("() => bootstrap.Modal.getInstance(document.getElementById('editFilamentModal')).hide()")
    ef.wait_for_timeout(50)
    open_form(ef, filament(vendor=dict(BRAND), spool_weight=150.0))
    box = ef.locator("#editfil-vendor-name")
    box.fill("")
    box.focus()
    ef.keyboard.press("ArrowDown")
    rows = ef.evaluate("""() => Array.from(document.querySelectorAll('#editfil-vendor-dropdown .dropdown-item'))
        .map((r) => r.classList.contains('active'))""")
    assert rows[:2] == [True, False], rows


def test_the_filament_window_reads_its_filament_again_on_its_vendors_save(ef):
    """RED on the base: only the brand's text changed; its "↩ vendor" weight stayed."""
    ef.evaluate("""() => { const m = document.getElementById('filamentModal'); m.classList.add('show');
        document.getElementById('fil-detail-id').innerText = '7';
        document.getElementById('fil-detail-vendor').dataset.vendorId = '2'; }""")
    _vendor_saved(ef, dict(BRAND, empty_spool_weight=200.0))
    assert any(f["url"].startswith("/api/filament_details?id=7") for f in ef.evaluate("window.__fetches"))
