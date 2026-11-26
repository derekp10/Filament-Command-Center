"""Group 66, review round 1: Edit Spool's "Link this spool to its Prusament QR" row (66.3(B)).

R4-02: an Edit Spool Save leaves the wizard open, and the row still said "Links at Save":
its ✕ then put back what the boxes held before the link, and the next Save cleared the
link the first one wrote. Now a landed Save settles the row ("Linked to this QR").
R5-01: a check that was refused (a Tab through the row re-ran it, or a different
product's QR scanned over a good link) first emptied the boxes the earlier link had
filled, and said "nothing changed"; the next Save cleared the link. Now a refusal leaves
the earlier link as it was, and the row's text unchanged since its link is not checked
again.
R4-03: two checks of one link in flight: the second's empty fill list replaced the
first's, so ✕ emptied the row but left the link in every box. Now each check has its own
token, and a check of the same text already on its way starts no other.
R4-06: the colour half of the product check compared the two names as text: Derek's
"Black (Galaxy Black)" against Prusament's "Prusa Galaxy Black" refused the spool's own
QR. Now the colours are compared by their words.

Hermetic, on the Group 66.3 page harness. Each case fails on the commit before the fix
for the reason it names.
"""
from __future__ import annotations

import json

from test_prusament_link_page_66_3 import CANONICAL, EDIT, QR, ROW, TEMPLATE, _open, _row, _scan, _value
from test_wizard_label_status_58_5 import _save, wizard  # noqa: F401  (the fixture)

PRODUCT = "#wiz-spool-product_url"
PURCHASE = "#wiz-spool-purchase_url"


def _clear_row(page):
    page.locator("[data-spool-row-idx='0'] button").first.click()
    page.wait_for_timeout(60)


def _second_save(page):
    """A comment, then Save again: what the second Save sends."""
    page.evaluate("() => { const b = document.getElementById('wiz-spool-comment'); b.value = 'note';"
                  " b.dispatchEvent(new Event('input', { bubbles: true })); }")
    page.locator("#btn-wiz-submit").click()
    page.wait_for_function("(u) => window.__posts.filter((p) => p.url === u).length >= 2", arg=EDIT)
    return page.evaluate("(u) => window.__posts.filter((p) => p.url === u)[1].body", EDIT)


def test_a_save_settles_the_row_and_its_clear_keeps_the_saved_link(wizard):  # noqa: F811
    """R4-02. RED: after the Save the row still said "Links at Save"; its ✕ emptied the
    link boxes, and the next Save cleared the link."""
    _open(wizard)
    _scan(wizard)
    assert _row(wizard)["status"] == "linked-new"
    first = _save(wizard, EDIT)
    assert first["spool_data"]["extra"]["product_url"].strip('"') == CANONICAL
    wizard.wait_for_function("() => wizardState.spoolRows[0].status === 'linked'")
    assert "Linked" in _row(wizard)["badge"]
    _clear_row(wizard)
    assert _value(wizard, PRODUCT) == CANONICAL
    assert "__FCC_DELETE_EXTRA__" not in json.dumps(_second_save(wizard)["spool_data"])


def test_a_refused_recheck_leaves_the_earlier_link_as_it_was(wizard):  # noqa: F811
    """R5-01. A good link, then the QR of another product scanned over it: refused, and
    the earlier link's boxes are as they were ("nothing changed" is true). RED: both link
    boxes were emptied before the refusal."""
    _open(wizard)
    _scan(wizard)
    assert _value(wizard, PRODUCT) == CANONICAL
    other = dict(TEMPLATE, material="PETG", color_name="Jet Black")
    wizard.evaluate("(t) => { window.__answers['/api/external/search'] = { success: true, results: [t] }; }", other)
    _scan(wizard, "https://prusament.com/spool/17999/ffff000011")
    assert _row(wizard)["status"] == "refused"
    assert (_value(wizard, PRODUCT), _value(wizard, PURCHASE)) == (CANONICAL, TEMPLATE["purchase_link"])


def test_a_tab_through_an_unchanged_row_checks_nothing_again(wizard):  # noqa: F811
    """R5-01. After the link, Prusament's page can't be read; a Tab through the row (its
    blur) must not run the check again. RED: the re-check emptied the link boxes, said
    "nothing changed", and the next Save cleared the link."""
    _open(wizard)
    _scan(wizard)
    wizard.evaluate("() => { window.__answers['/api/external/search'] = { success: false }; }")
    wizard.locator(ROW).focus()
    wizard.locator(ROW).press("Tab")
    wizard.wait_for_timeout(100)
    assert _row(wizard)["status"] == "linked-new"
    assert _value(wizard, PRODUCT) == CANONICAL


HOLD_QUEUE = r"""() => {
    const orig = window.fetch;
    window.__heldQ = {};
    window.fetch = function (url, opts) {
        const path = String(url).split('?')[0];
        if (window.__answers[path] !== '__hold__') return orig(url, opts);
        return new Promise((resolve) => {
            (window.__heldQ[path] = window.__heldQ[path] || []).push((b) => {
                const t = JSON.stringify(b);
                resolve({ ok: true, status: 200, json: () => Promise.resolve(JSON.parse(t)) });
            });
        });
    };
}"""


def test_two_checks_of_one_link_never_lose_its_fills(wizard):  # noqa: F811
    """R4-03. The row's Enter and its blur both check the link; the second check of the
    same text starts nothing, so ✕ puts every box back. RED: the second check's empty
    fill list replaced the first's, and ✕ left the link in the boxes."""
    _open(wizard)
    wizard.evaluate(HOLD_QUEUE)
    wizard.evaluate("() => { window.__answers['/api/external/search'] = '__hold__'; }")
    wizard.locator(ROW).fill(QR)
    wizard.evaluate("(u) => { window.wizardScanSpoolRow(0, u); window.wizardScanSpoolRow(0, u); }", QR)
    wizard.wait_for_function("() => (window.__heldQ['/api/external/search'] || []).length >= 1")
    wizard.wait_for_timeout(100)        # a second check, if one started, is held too
    wizard.evaluate("""(t) => { const q = window.__heldQ['/api/external/search'];
        while (q.length) q.shift()({ success: true, results: [t] }); }""", TEMPLATE)
    wizard.wait_for_function("() => wizardState.spoolRows[0].status === 'linked-new'")
    wizard.wait_for_timeout(60)
    _clear_row(wizard)
    assert (_value(wizard, PRODUCT), _value(wizard, PURCHASE)) == ("", "")


def test_a_colour_named_in_other_words_is_the_same_product(wizard):  # noqa: F811
    """R4-06. Derek's "Black (Galaxy Black)" and Prusament's "Prusa Galaxy Black". RED:
    the spool's own QR was refused as a different product."""
    _open(wizard, name="Black (Galaxy Black)", template=dict(TEMPLATE, color_name="Prusa Galaxy Black"))
    _scan(wizard)
    assert _row(wizard)["status"] == "linked-new", _row(wizard)


def test_a_different_colour_is_still_refused(wizard):  # noqa: F811
    """A pin: "Jet Black" is not "Black (Galaxy Black)"."""
    _open(wizard, name="Black (Galaxy Black)", template=dict(TEMPLATE, color_name="Jet Black"))
    _scan(wizard)
    assert _row(wizard)["status"] == "refused"


def test_the_rows_clear_empties_its_box_so_a_tab_links_nothing(wizard):  # noqa: F811
    """R4-04. RED: ✕ left the link's text in the row, and a Tab through it linked again
    (every box filled, and Save wrote them)."""
    _open(wizard)
    _scan(wizard)
    _clear_row(wizard)
    assert _value(wizard, ROW) == ""
    wizard.locator(ROW).focus()
    wizard.locator(ROW).press("Tab")
    wizard.wait_for_timeout(100)
    assert _row(wizard)["status"] == "empty"
    assert (_value(wizard, PRODUCT), _value(wizard, PURCHASE)) == ("", "")


def test_an_upper_cased_qr_is_looked_up_by_its_canonical_link(wizard):  # noqa: F811
    """R4-05: Prusament's lookup reads only a lower-case link. RED: the raw upper-cased QR
    was sent, and the row said "couldn't read its Prusament page"."""
    _open(wizard)
    wizard.evaluate("""() => { window.__gets = []; const orig = window.fetch;
        window.fetch = function (url, opts) { window.__gets.push(String(url)); return orig(url, opts); }; }""")
    _scan(wizard, QR.upper())
    sent = [u for u in wizard.evaluate("window.__gets") if u.startswith("/api/external/search")]
    assert sent and all("prusament.com%2Fspool%2F17705%2Fabc123def0" in u for u in sent), sent


def test_a_product_link_typed_while_the_check_was_out_is_kept_and_nothing_fills(wizard):  # noqa: F811
    """R4-07. RED: the QR still filled the other boxes and said "Links at Save"."""
    _open(wizard)
    wizard.evaluate(HOLD_QUEUE)
    wizard.evaluate("() => { window.__answers['/api/external/search'] = '__hold__'; }")
    wizard.locator(ROW).fill(QR)
    wizard.locator(ROW).press("Tab")
    wizard.wait_for_function("() => (window.__heldQ['/api/external/search'] || []).length === 1")
    wizard.evaluate("() => { const b = document.getElementById('wiz-spool-product_url');"
                    " b.value = 'https://example.com/my-link'; b.dispatchEvent(new Event('input', { bubbles: true })); }")
    wizard.evaluate("(t) => window.__heldQ['/api/external/search'].shift()({ success: true, results: [t] })", TEMPLATE)
    wizard.wait_for_function("() => wizardState.spoolRows[0].status !== 'pending'")
    assert _row(wizard)["status"] == "refused"
    assert (_value(wizard, PRODUCT), _value(wizard, PURCHASE)) == ("https://example.com/my-link", "")


def test_a_qr_another_spool_holds_says_how_to_free_it(wizard):  # noqa: F811
    """R4-09. RED: "Scan #57's own QR.", with no way forward."""
    _open(wizard, owners=[{"id": 24, "display": "#24 Galaxy Black", "archived": True}])
    _scan(wizard)
    assert _row(wizard)["status"] == "refused"
    assert "clear #24's 📄 Product Link first" in _row(wizard)["note"], _row(wizard)
