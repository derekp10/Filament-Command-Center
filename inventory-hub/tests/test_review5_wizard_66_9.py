"""Group 66.9 review round 5 (2026-11-26), the wizard half: R5W1-R5W9, pinned.

  - R5W1: a create that landed, a change, then a second create whose answer was lost within
    3 s: the first create's "Make a change to add more" note (a 3 s timer that read only the
    lock, which round 4's catch now sets) replaced the second's "search for them before
    creating them again", as if it had landed. The note's timer belongs to its own Save now
    (cleared as each Save starts and in the catch, and checking its session).
  - R5W7: after a lost create, Create was off and nothing said a change turns it back on.
  - R5W5 (older than 66.9): Backspace in an empty attribute box removed the last chip with
    nothing noticing: no change counted, the field not touched, so in Edit Spool removing
    the only attribute was never saved, under "Success! Spool Updated.".
  - R5W3 (older than 66.9): a second QR still being checked when the Save that carried the
    first one landed left that link unsettled: a refusal then said it "still links at Save"
    (two ✕ and the next Save cleared the saved link), and an accepted QR replaced it unasked.
  - R5W2: the link row's ✕ pressed while its Save was out changed no count, so the answer
    marked the form saved and the ✕ was lost (Spoolman kept the link, date and length).
  - R5W4: after a link, a Product Link typed over the QR's by hand (or emptied) was saved,
    and the row said "🔗 Linked to this QR"; a scan of that QR finds the spool by its
    Product Link, so it doesn't. A row settled as not linked keeps its text unchecked, as a
    linked row does (a Tab through it filled the emptied Product Link again).
  - R5W6 (older than 66.9): the colour ➕ and 🗑️ changed the filament without counting.
  - R5W8: a label read onto a wizard dropdown left the change count raised, so the answer of
    a Save that was out read the form as changed.
  - R5W9: round 4's rules no test held (mutants B, D, E, J and K of the review survived).

Hermetic, on the Group 58.5 wizard page (the 66.3 link-row page for the link cases), so it
runs under --offline. Each case marked RED fails on 9420b750 for the reason it names; the
R5W9 cases are pins of round 4's rules, each killed by the mutant it names.
"""
from __future__ import annotations

import pytest

from test_prusament_link_page_66_3 import CANONICAL, ROW, TEMPLATE, _open, _row, _scan, _value
from test_review1_linkrow_66 import HOLD_QUEUE
from test_vendor_merge_page_66_9 import CREATE_STUB, LABEL_FIELDS, SAVE_STUB, _save_n, _set_link, _wiz_edit
from test_wizard_label_status_58_5 import MODULES, SAMPLE_BOX, _open_edit, wizard  # noqa: F401  (the fixture)
from test_wizard_native_clear_54_5 import _details as _nc_details
from test_wizard_price_mark_54_8 import _open_new_spool, wiz  # noqa: F401  (the fixture)
from test_wizard_vendor_66_1 import _brand

EDIT = "/api/edit_spool_wizard"
CREATE = "/api/create_inventory_wizard"
PRODUCT = "#wiz-spool-product_url"
PURCHASE = "#wiz-spool-purchase_url"
DATE = "#wiz_spool_ef_prusament_manufacturing_date"
LENGTH = "#wiz_spool_ef_prusament_length_m"
CLEAR = "[data-spool-row-idx='0'] .wiz-row-clear-btn"
SENTINEL = "__FCC_DELETE_EXTRA__"
LOCK_WORDS = " Create stays off until you change something in the form."
# Another spool of the same product (its QR's own code), and one of another product.
QR_B = "https://prusament.com/spool/17705/bbb222ccc3"
CANONICAL_B = "https://prusament.com/spool/17705/bbb222ccc3/"
OTHER_PRODUCT = dict(TEMPLATE, color_name="Jet Black", name="Prusament PLA Jet Black")
PRUSA_PAGE = "https://www.prusa3d.com/product/prusament-pla-galaxy-black/"


def _status(page):
    return page.locator("#wiz-status-msg").inner_text()


def _creates(page, n):
    """Wait until the n-th create went out and its Save is over."""
    page.wait_for_function("(n) => wizardState.saving == null"
                           " && window.__posts.filter((p) => p.url === '/api/create_inventory_wizard').length >= n", arg=n)


def _type_comment(page, words):
    page.evaluate("""(w) => { const c = document.getElementById('wiz-spool-comment'); c.value = w;
        c.dispatchEvent(new Event('input', { bubbles: true })); }""", words)


def _save_off_and_locked(page):
    return page.evaluate("() => [document.getElementById('btn-wiz-submit').disabled, wizardState.lockedAfterSuccess]")


def _hold_save(page):
    """A Save held on its way (SAVE_STUB's 'hold'); window.__releaseSave(answer) answers it."""
    page.evaluate(SAVE_STUB)
    page.evaluate("() => { window.__saveMode = 'hold'; window.wizardSubmit(); }")
    page.wait_for_function("(u) => window.__posts.filter((p) => p.url === u).length >= 1", arg=EDIT)


def _release_save(page, answer=None):
    page.evaluate("(a) => window.__releaseSave(a)", answer or {"success": True, "spool_id": 57})
    page.wait_for_function("() => wizardState.saving == null")


def _boxes(page):
    return {k: _value(page, sel) for k, sel in (("product", PRODUCT), ("purchase", PURCHASE),
                                                ("date", DATE), ("length", LENGTH))}


# --- R5W1 / R5W7: a create's words, and its note's timer ------------------------------------

def test_a_lost_create_soon_after_one_that_landed_keeps_its_words(wiz):  # noqa: F811
    """R5W1, R5W7. RED: 3 s after the first create landed its note replaced the second's
    "search for them before creating them again" with "Make a change to add more", and the
    words never said Create waits for a change."""
    _open_new_spool(wiz)
    wiz.evaluate(CREATE_STUB)
    wiz.evaluate("() => { window.wizardSubmit(); }")
    _creates(wiz, 1)
    assert _status(wiz) == "Success! Spool(s) Generated."
    _type_comment(wiz, "the next spool")          # a change lifts the lock, as for the next spool
    wiz.evaluate("() => { window.__createMode = 'reject'; window.wizardSubmit(); }")
    _creates(wiz, 2)
    said = ("FCC didn't answer, so the new spool(s) may or may not have been created (Failed to fetch): "
            "search for them before creating them again.")
    assert _status(wiz).startswith(said)
    wiz.wait_for_timeout(3300)                     # past the first create's note
    assert _status(wiz) == said + LOCK_WORDS
    assert _save_off_and_locked(wiz) == [True, True]
    assert wiz.evaluate("window.__errors") == []


def test_a_create_whose_page_error_comes_after_its_note_was_set_keeps_the_errors_words(wiz):  # noqa: F811
    """R5W1 (the catch clears this Save's own note), R5W7. RED: the create landed, the page
    hit an error placing its spools, and 3 s later its own note wrote over the error's
    words."""
    _open_new_spool(wiz)
    wiz.evaluate("""() => { window.__answers['/api/create_inventory_wizard'] = { success: true, created_spools: [58],
        filament_id: 7, location_results: { '58': { status: 'success' } } };
        window.wizardSettleCreatePlacements = () => { throw new Error('boom'); }; }""")
    wiz.evaluate("() => { window.wizardSubmit(); }")
    _creates(wiz, 1)
    said = ("FCC answered, but this page hit an error showing it (boom): "
            "search for the new spool(s) before creating them again.")
    assert _status(wiz).startswith(said)
    wiz.wait_for_timeout(3300)
    assert _status(wiz) == said + LOCK_WORDS
    assert _save_off_and_locked(wiz) == [True, True]


def test_each_creates_note_comes_three_seconds_after_that_create(wiz):  # noqa: F811
    """R5W1 (each Save clears the last one's note as it starts). RED: a second create 1.5 s
    after the first had its "Success!" replaced 1.5 s later by the first create's note."""
    _open_new_spool(wiz)
    wiz.evaluate("() => { window.wizardSubmit(); }")
    _creates(wiz, 1)
    wiz.wait_for_timeout(1500)
    _type_comment(wiz, "the next spool")
    wiz.evaluate("() => { window.wizardSubmit(); }")
    _creates(wiz, 2)
    wiz.wait_for_timeout(1800)                     # 3.3 s after the first create, 1.8 s after the second
    assert _status(wiz) == "Success! Spool(s) Generated."
    wiz.wait_for_timeout(1700)                     # 3.5 s after the second
    assert _status(wiz).startswith("Make a change to add more")
    assert _save_off_and_locked(wiz) == [True, True]


# --- R5W5: Backspace on the last attribute ---------------------------------------------------

def test_backspace_on_the_only_attribute_is_a_change_and_edit_spools_save_clears_it(wiz):  # noqa: F811
    """R5W5 (older than 66.9). RED: after the Backspace the form read as unchanged, the field
    wasn't touched, and Save sent the filament's extra as {} ("Success! Spool Updated.",
    while Spoolman kept Matte)."""
    wiz.evaluate("(f) => { window.__answers['/api/external/fields'] = f; }", LABEL_FIELDS)
    d = _nc_details()
    d["filament"]["extra"] = {"filament_attributes": '["Matte"]'}
    wiz.evaluate("""(a) => { window.__answers['/api/spool_details'] = a.d;
        window.__answers['/api/external/vendors'] = { success: true, vendors: [a.v] }; }""",
                 {"d": d, "v": _brand(2)})
    wiz.evaluate("() => { window.openEditWizard(57); }")
    wiz.wait_for_function("() => wizardState.mode === 'edit_spool' && document.getElementById('wiz-fil-color_name').value === 'Red'"
                          " && !document.getElementById('btn-wiz-submit').disabled"
                          " && document.querySelectorAll('#chip-container-fil-filament_attributes .dynamic-chip').length === 1")
    wiz.evaluate(SAVE_STUB)
    assert wiz.evaluate("() => [wizardState.isDirty, wizardState.changeSeq]") == [False, 0]
    wiz.evaluate("() => { const p = document.getElementById('wiz-fil-extras-panel'); if (p) p.classList.add('show'); }")
    box = wiz.locator("#wiz_fil_ef_filament_attributes")
    box.focus()
    box.press("Backspace")                         # the person's key: its own handler takes the last chip
    after = wiz.evaluate("() => ({ dirty: wizardState.isDirty, seq: wizardState.changeSeq,"
                         " touched: Array.from(wizardState.touchedExtras),"
                         " chips: document.querySelectorAll('#chip-container-fil-filament_attributes .dynamic-chip').length })")
    assert after["chips"] == 0
    assert after["dirty"] is True and after["seq"] > 0, after
    assert "fil:filament_attributes" in after["touched"], after
    assert _save_n(wiz, 1)["filament_data"]["extra"].get("filament_attributes") == SENTINEL


# --- R5W6: the colour ➕ and 🗑️ ------------------------------------------------------------

def test_the_colour_bin_and_plus_are_changes_and_filling_the_colours_is_not(wiz):  # noqa: F811
    """R5W6 (older than 66.9). RED: 🗑️ (and ➕) left the form unchanged, so a close asked
    nothing and a Save that was out marked them saved."""
    d = _nc_details()
    d["filament"]["multi_color_hexes"] = "FF0000,00FF00"
    d["filament"]["multi_color_direction"] = "longitudinal"
    wiz.evaluate("""(a) => { window.__answers['/api/spool_details'] = a.d;
        window.__answers['/api/external/vendors'] = { success: true, vendors: [a.v] }; }""",
                 {"d": d, "v": _brand(2)})
    wiz.evaluate("() => { window.openEditWizard(57); }")
    wiz.wait_for_function("() => wizardState.mode === 'edit_spool' && document.getElementById('wiz-fil-color_name').value === 'Red'"
                          " && !document.getElementById('btn-wiz-submit').disabled"
                          " && document.querySelectorAll('#wiz-fil-color-extra-container .input-group').length === 1")
    # Filling the second colour in is code, never the person's change.
    assert wiz.evaluate("() => [wizardState.isDirty, wizardState.changeSeq]") == [False, 0]
    wiz.evaluate("() => document.querySelector('#wiz-fil-color-extra-container .btn-outline-danger').click()")
    binned = wiz.evaluate("() => [wizardState.isDirty, wizardState.changeSeq,"
                          " document.querySelectorAll('#wiz-fil-color-extra-container .input-group').length]")
    assert binned[0] is True and binned[1] > 0 and binned[2] == 0, binned
    wiz.evaluate("() => document.querySelector('#wiz-fil-color-container button').click()")      # ➕
    added = wiz.evaluate("() => [wizardState.changeSeq,"
                         " document.querySelectorAll('#wiz-fil-color-extra-container .input-group').length]")
    assert added[0] > binned[1] and added[1] == 1, added


# --- R5W8: a label read onto a dropdown while a Save is out ----------------------------------

SELECT_FIELDS = {"success": True, "fields": {
    "filament": [
        {"entity_type": "filament", "field_type": "choice", "multi_choice": False, "key": "slicer_profile",
         "name": "Slicer Profile", "order": 5, "choices": ["Generic PLA", "Ideal PLA", "Prusament PLA"]},
        {"entity_type": "filament", "field_type": "boolean", "key": "needs_label_print",
         "name": "Needs Label Print", "order": 14},
    ],
    "spool": [],
}}


def test_a_label_read_onto_a_dropdown_while_a_save_is_out_leaves_nothing_unsaved(wiz):  # noqa: F811
    """R5W8. RED: the type-ahead's pick and the rollback's change each counted one, and the
    rollback put the rest back but not the count: the Save's answer read the form as
    changed, and closing asked about changes that were all saved."""
    wiz.evaluate("(f) => { window.__answers['/api/external/fields'] = f; }", SELECT_FIELDS)
    _wiz_edit(wiz)
    wiz.wait_for_selector("#wiz_fil_ef_slicer_profile", state="attached")
    _type_comment(wiz, "a note")                   # a real change, so the Save carries a count
    seq0 = wiz.evaluate("() => wizardState.changeSeq")
    assert seq0 > 0
    wiz.evaluate("() => { const p = document.getElementById('wiz-fil-extras-panel'); if (p) p.classList.add('show'); }")
    wiz.evaluate("() => { window.__saveMode = 'hold'; window.wizardSubmit(); }")
    wiz.wait_for_function("(u) => window.__posts.filter((p) => p.url === u).length === 1", arg=EDIT)
    sel = wiz.locator("#wiz_fil_ef_slicer_profile")
    sel.focus()
    wiz.keyboard.type("ID:57")
    wiz.keyboard.press("Enter")
    wiz.wait_for_timeout(50)
    mid = wiz.evaluate("() => ({ value: document.getElementById('wiz_fil_ef_slicer_profile').value,"
                       " seq: wizardState.changeSeq })")
    assert mid == {"value": "", "seq": seq0}, mid
    _release_save(wiz)
    assert wiz.evaluate("() => wizardState.isDirty") is False


# --- R5W2: the link row's ✕ while its Save is out --------------------------------------------

def test_the_rows_clear_while_its_save_is_out_stays_a_change_and_clears_all_four_next(wizard):  # noqa: F811
    """R5W2. RED: after the answer the form read as saved (a close asked nothing), and the
    next Save cleared only the two links, leaving the date and length the first Save wrote
    in Spoolman under blank boxes."""
    _open(wizard)
    _scan(wizard)
    assert _row(wizard)["status"] == "linked-new"
    _hold_save(wizard)
    first = wizard.evaluate("(u) => window.__posts.filter((p) => p.url === u)[0].body", EDIT)["spool_data"]["extra"]
    assert first["product_url"] == CANONICAL and first["prusament_length_m"] == "336"
    seq0 = wizard.evaluate("() => wizardState.changeSeq")
    wizard.locator(CLEAR).click()                  # the person's ✕, with the Save on its way
    wizard.wait_for_timeout(60)
    assert _boxes(wizard) == {"product": "", "purchase": "", "date": "", "length": ""}
    assert wizard.evaluate("() => wizardState.changeSeq") > seq0
    _release_save(wizard)
    assert wizard.evaluate("() => [wizardState.isDirty, wizardState.spoolRows[0].status]") == [True, "empty"]
    extra = _save_n(wizard, 2)["spool_data"]["extra"]
    for key in ("product_url", "purchase_url", "prusament_manufacturing_date", "prusament_length_m"):
        assert extra.get(key) == SENTINEL, (key, extra)


# --- R5W3: a newer QR still being checked when the Save lands --------------------------------

@pytest.mark.parametrize("b", ["refused", "accepted"])
def test_a_newer_qr_checked_when_the_save_lands_settles_the_saved_link(wizard, b):  # noqa: F811
    """R5W3 (older than 66.9). RED: the pending row kept the saved link as one waiting.
    Refused: its note said the earlier QR "still links at Save", and two ✕ and the next Save
    cleared the saved links. Accepted: the second QR replaced the saved link unasked."""
    _open(wizard)
    _scan(wizard)
    _hold_save(wizard)
    wizard.evaluate(HOLD_QUEUE)
    wizard.evaluate("() => { window.__answers['/api/prusament/linked_spools'] = '__hold__'; }")
    if b == "refused":
        wizard.evaluate("(t) => { window.__answers['/api/external/search'] = { success: true, results: [t] }; }",
                        OTHER_PRODUCT)
    wizard.locator(ROW).fill(QR_B)                 # a second QR into the row, the Save still out
    wizard.locator(ROW).press("Tab")
    wizard.wait_for_function("() => (window.__heldQ['/api/prusament/linked_spools'] || []).length === 1"
                             " && wizardState.spoolRows[0].status === 'pending'")
    _release_save(wizard)
    assert wizard.evaluate("() => wizardState.spoolRows[0].status") == "pending"    # the second check is still out
    wizard.evaluate("() => window.__heldQ['/api/prusament/linked_spools'].shift()({ success: true, spools: [] })")
    wizard.wait_for_function("() => wizardState.spoolRows[0].status !== 'pending'")
    wizard.wait_for_timeout(50)
    row = _row(wizard)
    assert row["status"] == "refused" and "still links at Save" not in row["note"], row
    if b == "accepted":
        assert row["badge"].startswith("✗ Its Product Link holds another link"), row
    else:
        assert row["note"].startswith("That QR is Prusament PLA Jet Black"), row
        wizard.evaluate("() => { window.wizardClearSpoolRow(0); window.wizardClearSpoolRow(0); }")   # ✕, then ✕ again
        wizard.wait_for_timeout(60)
    assert _boxes(wizard) == {"product": CANONICAL, "purchase": TEMPLATE["purchase_link"],
                              "date": "2026-03-01 10:00:00", "length": "336"}
    extra = _save_n(wizard, 2)["spool_data"]["extra"]
    assert "product_url" not in extra and "purchase_url" not in extra, extra


# --- R5W4: a link changed by hand after it filled Product Link ---------------------------------

SPOOL_SAVED_FILAMENT_REFUSED = {"success": False, "spool_saved": True, "filament_may_have_saved": False,
                                "msg": "Spool saved, but filament #7's changes weren't saved: Spoolman refused it: nope."}


@pytest.mark.parametrize("answer", [{"success": True, "spool_id": 57}, SPOOL_SAVED_FILAMENT_REFUSED],
                         ids=["landed", "spool saved, filament refused"])
def test_a_link_typed_over_by_hand_is_saved_and_said_as_not_linked(wizard, answer):  # noqa: F811
    """R5W4, both callers. RED: the row said "🔗 Linked to this QR" for a spool whose saved
    Product Link is the page typed over it."""
    _open(wizard)
    _scan(wizard)
    _set_link(wizard, PRUSA_PAGE)
    wizard.evaluate("(a) => { window.__answers['/api/edit_spool_wizard'] = a; }", answer)
    assert _save_n(wizard, 1)["spool_data"]["extra"]["product_url"] == PRUSA_PAGE
    row = _row(wizard)
    assert row["status"] == "refused" and row["badge"].startswith("✗ Not linked"), row
    assert row["note"] == "Saved with the 📄 Product Link you typed, so #57 isn't linked to this QR.", row
    assert row["noteShown"]
    shown = _boxes(wizard)
    wizard.locator(CLEAR).click()                  # its ✕ empties the row, and keeps every box
    wizard.wait_for_timeout(60)
    assert _row(wizard)["status"] == "empty"
    assert _boxes(wizard) == shown == {"product": PRUSA_PAGE, "purchase": TEMPLATE["purchase_link"],
                                       "date": "2026-03-01 10:00:00", "length": "336"}


def test_a_link_emptied_by_hand_is_said_as_not_linked_and_a_tab_through_the_row_links_nothing(wizard):  # noqa: F811
    """R5W4. RED: "🔗 Linked to this QR", though nothing was saved as its Product Link. And
    the row's text, unchanged since its link, isn't checked again (a Tab through it filled
    the emptied Product Link again and read "Links at Save")."""
    _open(wizard)
    _scan(wizard)
    _set_link(wizard, "")
    assert "product_url" not in _save_n(wizard, 1)["spool_data"]["extra"]     # blank, as it opened
    row = _row(wizard)
    assert row["status"] == "refused" and row["badge"].startswith("✗ Not linked"), row
    assert row["note"] == "Saved with 📄 Product Link empty, so #57 isn't linked to this QR.", row
    wizard.locator(ROW).focus()
    wizard.locator(ROW).press("Tab")
    wizard.wait_for_timeout(1000)
    assert _row(wizard)["status"] == "refused"
    assert _value(wizard, PRODUCT) == ""


def test_after_not_linked_a_refusal_is_checked_again_once_its_cause_is_cleared(wizard):  # noqa: F811
    """R5W4: a check of other text ends the settled row's "checked no more", so a refusal
    over it is checked again as any refusal is. RED: the row read "Linked to this QR" after
    the Save. (Kept up, the mark made the next QR's refusal stick: the person cleared Product
    Link as it said, scanned the QR again, and nothing happened.)"""
    _open(wizard)
    _scan(wizard)
    _set_link(wizard, PRUSA_PAGE)
    _save_n(wizard, 1)
    assert _row(wizard)["badge"].startswith("✗ Not linked")
    _scan(wizard, QR_B)                            # the right spool's QR: Product Link holds another link
    assert _row(wizard)["badge"].startswith("✗ Its Product Link holds another link")
    _set_link(wizard, "")                          # cleared, as the refusal says
    _scan(wizard, QR_B)                            # and scanned again
    row = _row(wizard)
    assert row["status"] == "linked-new", row
    assert _value(wizard, PRODUCT) == CANONICAL_B


# --- R5W9: round 4's rules, pinned (each killed by the review's mutant it names) ---------------

def test_a_chip_picked_from_the_list_while_a_save_is_out_stays_a_change(wiz):  # noqa: F811
    """Mutant B (the chip add's count dropped): a chip picked with the mouse (its mousedown
    fires no input event) while a Save was out was marked saved."""
    wiz.evaluate("(f) => { window.__answers['/api/external/fields'] = f; }", LABEL_FIELDS)
    _wiz_edit(wiz)
    wiz.wait_for_selector("#chip-container-fil-filament_attributes", state="attached")
    wiz.evaluate("() => { window.__saveMode = 'hold'; window.wizardSubmit(); }")
    wiz.wait_for_function("(u) => window.__posts.filter((p) => p.url === u).length === 1", arg=EDIT)
    wiz.evaluate("""() => document.querySelector('#dropdown-fil-filament_attributes .autocomplete-option')
        .dispatchEvent(new MouseEvent('mousedown', { bubbles: true, cancelable: true }))""")
    assert wiz.evaluate("() => document.querySelectorAll('#chip-container-fil-filament_attributes .dynamic-chip').length") == 1
    _release_save(wiz)
    assert wiz.evaluate("() => wizardState.isDirty") is True


def test_an_edit_whose_answer_was_lost_leaves_save_on_and_unlocked(wiz):  # noqa: F811
    """Mutant D (an edit locked too): Save off under "Save again to send it again."."""
    _wiz_edit(wiz)
    wiz.evaluate("() => { window.__saveMode = 'reject'; }")
    _save_n(wiz, 1)
    assert _status(wiz) == ("FCC didn't answer this Save, so it may or may not have landed (Failed to fetch). "
                            "Save again to send it again.")
    assert _save_off_and_locked(wiz) == [False, False]


def test_a_create_that_threw_before_its_request_leaves_create_on_and_unlocked(wiz):  # noqa: F811
    """Mutant K (a create locked though nothing was sent): Create off under "Nothing was
    sent.", until a change."""
    _open_new_spool(wiz)
    wiz.evaluate("() => { window.wizardCommitSuggestedChoices = () => { throw new Error('early'); }; }")
    wiz.evaluate("() => { window.wizardSubmit(); }")
    wiz.wait_for_function("() => wizardState.saving == null")
    assert _status(wiz) == "Frontend Error: early. Nothing was sent."
    assert _save_off_and_locked(wiz) == [False, False]
    assert wiz.evaluate("(u) => window.__posts.filter((p) => p.url === u).length", CREATE) == 0


def test_a_settled_refusal_redraws_its_note_and_frees_save_at_once(wizard):  # noqa: F811
    """Mutant E (the refused settle redraws nothing): the note still ended "still links at
    Save: ✕ goes back to it." about a saved link, and Save stayed off for 3 s."""
    _open(wizard)
    _scan(wizard)
    wizard.evaluate("(t) => { window.__answers['/api/external/search'] = { success: true, results: [t] }; }",
                    OTHER_PRODUCT)
    _scan(wizard, "https://prusament.com/spool/17705/fff999eee8")
    assert "still links at Save" in _row(wizard)["note"]
    assert _save_n(wizard, 1)["spool_data"]["extra"]["product_url"] == CANONICAL
    row = _row(wizard)
    assert row["status"] == "refused" and row["noteShown"], row
    assert row["note"].startswith("That QR is Prusament PLA Jet Black") and "still links" not in row["note"], row
    assert row["badge"].startswith("✗ A different product"), row
    assert wizard.evaluate("() => document.getElementById('btn-wiz-submit').disabled") is False


def test_a_swatch_ticked_and_saved_is_what_the_reprint_question_reads_next(wizard):  # noqa: F811
    """Mutant J (sample_printed left out of the moved baseline): a Save that ticked Sample
    Printed, then a rename, asked no reprint question. The real gate (inv_details.js)."""
    wizard.add_script_tag(content=(MODULES / "inv_details.js").read_text(encoding="utf-8"))
    _open_edit(wizard, {"needs_label_print": True, "sample_printed": False})
    wizard.evaluate("""() => { window.__labelRaw = []; const real = window._maybePromptLabelReprint;
        window._maybePromptLabelReprint = (...a) => { window.__labelRaw.push(a[4]); return real(...a); }; }""")
    wizard.locator(SAMPLE_BOX).click()             # a swatch printed
    assert _save_n(wizard, 1)["filament_data"]["extra"]["sample_printed"] is True
    assert wizard.locator("#fcc-label-reprint-prompt").count() == 0
    wizard.evaluate("""() => { const n = document.getElementById('wiz-fil-color_name'); n.value = 'Red Renamed';
        n.dispatchEvent(new Event('input', { bubbles: true })); }""")
    _save_n(wizard, 2)
    assert wizard.evaluate("() => window.__labelRaw[window.__labelRaw.length - 1].sample_printed") is True
    wizard.wait_for_selector("#fcc-label-reprint-prompt", state="visible")
    assert "Name" in wizard.locator("#fcc-label-reprint-prompt").inner_text()
    assert wizard.evaluate("window.__errors") == []


@pytest.mark.parametrize("how", ["landed", "an answered move"])
def test_an_edits_three_second_step_never_frees_save_under_a_second_save(wizard, how):  # noqa: F811
    """Round 5 (found by the wizard fixer, older than 66.9): Save 1 lands (or its move
    question is answered) and frees Save at once (its link settled); Save 2 goes out; Save
    1's 3 s step must not free Save, nor wipe "Processing…", while Save 2 is still out."""
    _open(wizard)
    _scan(wizard)                                   # a link waits for Save
    wizard.evaluate(SAVE_STUB)
    if how == "an answered move":
        wizard.evaluate("""() => { window.wizardEditLocationNotMoved = (data, opts) => opts.onDone('moved', {}, {});
            window.__answers['/api/edit_spool_wizard'] = { success: false, spool_saved: true, location_moved: false,
                location_result: { status: 'requires_confirm' }, msg: 'asks' }; }""")
    _save_n(wizard, 1)
    wizard.evaluate("() => { window.__answers['/api/edit_spool_wizard'] = { success: true, spool_id: 57 }; }")
    assert wizard.evaluate("() => !document.getElementById('btn-wiz-submit').disabled")
    wizard.evaluate("""() => { const c = document.getElementById('wiz-spool-comment'); c.value = 'more';
        c.dispatchEvent(new Event('input', { bubbles: true })); window.__saveMode = 'hold'; window.wizardSubmit(); }""")
    wizard.wait_for_function("() => window.__posts.filter((p) => p.url === '/api/edit_spool_wizard').length === 2")
    during = _status(wizard)
    wizard.wait_for_timeout(3300)
    assert wizard.evaluate("() => wizardState.saving != null")            # Save 2 still out
    assert wizard.evaluate("() => document.getElementById('btn-wiz-submit').disabled") is True
    assert _status(wizard) == during
    wizard.evaluate("() => window.__releaseSave({ success: true, spool_id: 57 })")
    wizard.wait_for_function("() => wizardState.saving == null")
