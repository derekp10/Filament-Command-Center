"""Group 66.3 (Derek's (B)), the page: in Edit Spool the Prusament box links the spool.

Edit Spool showed the Add wizard's "📷 Per-spool Prusament scan" box: a scan there showed
a ✓ with the weights and date it read, and Save sent none of it (only a create reads
spool_overrides), saying "Spool Updated". Derek's pick (B): in Edit Spool the box is
"📷 Link this spool to its Prusament QR". A QR scanned there puts the QR's own link in
the spool's 📄 Product Link and fills its BLANK Prusament details (purchase link,
manufacturing date, length), as if typed, so Save sends them through the edit's own diff.
Prusament's weights are shown, never sent: the dashboard scan offers them, checked against
the live spool. It changes nothing, and says why, when the spool's own Product Link holds
another link, another spool already holds the QR (or FCC couldn't check), the Prusament
page couldn't be read, or the QR is a different product; a refusal never blocks Save.

Dev's data (2026-11-24): 10 of 38 Prusament spools in stock have no link of their own,
so a dashboard scan of their QR opened the Add wizard as if each were new; this is the
in-app way to link them.

Hermetic, on the Group 58.5 wizard harness (the real modals_wizard.html and modules in
`isolated_page`), so it runs under --offline.
"""
from __future__ import annotations

import copy

import pytest

from test_wizard_label_status_58_5 import FIELDS as WIZ_FIELDS
from test_wizard_label_status_58_5 import _save, wizard  # noqa: F401  (the fixture)

EDIT = "/api/edit_spool_wizard"
QR = "https://prusament.com/spool/17705/ABC123DEF0"
CANONICAL = "https://prusament.com/spool/17705/abc123def0/"
ROW = "[data-spool-row-idx='0'] input"

TEMPLATE = {
    "name": "Prusament PLA Galaxy Black", "material": "PLA", "vendor": {"name": "Prusament"},
    "color_name": "Galaxy Black", "weight": 1012.0, "weight_is_default": False, "spool_weight": 193.0,
    "external_link": QR, "purchase_link": "https://www.prusa3d.com/product/prusament-pla-galaxy-black/",
    "extra": {"prusament_manufacturing_date": "2026-03-01 10:00:00", "prusament_length_m": "336"},
}


def _fields():
    fields = copy.deepcopy(WIZ_FIELDS)
    fields["fields"]["spool"] += [
        {"entity_type": "spool", "field_type": "text", "key": "prusament_manufacturing_date",
         "name": "Manufacturing Date", "order": 20},
        {"entity_type": "spool", "field_type": "text", "key": "prusament_length_m", "name": "Length (m)", "order": 21},
    ]
    return fields


def _details(spool_extra=None, name="Galaxy Black", material="PLA"):
    return {
        "archived": False, "extra": dict(spool_extra or {}), "id": 57, "initial_weight": 1000.0,
        "location": "SHELF-1", "registered": "2026-02-11T04:07:24Z", "remaining_weight": 500.0,
        "spool_weight": 0.0, "tags": [], "used_weight": 500.0,
        "filament": {
            "color_hex": "111111", "comment": "", "density": 1.24, "diameter": 1.75, "external_id": "",
            "extra": {}, "id": 7, "material": material, "name": name, "price": 0.0,
            "registered": "2026-02-11T04:07:24Z", "settings_bed_temp": 60, "settings_extruder_temp": 215,
            "spool_weight": 193.0, "tags": [], "weight": 1000.0,
            "vendor": {"extra": {}, "id": 9, "name": "Prusament", "registered": "2026-02-11T04:07:24Z"},
        },
    }


def _open(page, spool_extra=None, owners=None, template=TEMPLATE, name="Galaxy Black", material="PLA"):
    page.evaluate("""(a) => Object.assign(window.__answers, a)""", {
        "/api/external/fields": _fields(),
        "/api/external/vendors": {"success": True, "vendors": [{"id": 9, "name": "Prusament", "extra": {}}]},
        "/api/spool_details": _details(spool_extra, name=name, material=material),
        "/api/prusament/linked_spools": {"success": True, "spool_id": "17705", "spool_hash": "abc123def0",
                                          "spools": owners or []},
        "/api/external/search": {"success": True, "results": [template] if template else []},
    })
    page.evaluate("() => { window.openEditWizard(57); }")
    page.wait_for_function("() => wizardState.mode === 'edit_spool'"
                           " && !!document.getElementById('wiz_spool_ef_prusament_length_m')"
                           " && document.getElementById('wiz-fil-color_name').value !== ''"
                           " && !document.getElementById('btn-wiz-submit').disabled")


def _scan(page, url=QR):
    page.locator(ROW).fill(url)
    page.locator(ROW).press("Tab")          # its blur reads it, as a scanner's Enter does
    page.wait_for_function("() => (wizardState.spoolRows[0] || {}).status !== 'pending'")
    page.wait_for_timeout(50)


def _row(page):
    return page.evaluate("""() => ({ status: wizardState.spoolRows[0].status,
        badge: (document.querySelector("[data-spool-row-idx='0'] .badge") || {}).textContent || '',
        note: document.getElementById('wiz-spool-link-note').textContent,
        noteShown: document.getElementById('wiz-spool-link-note').style.display !== 'none' })""")


def _value(page, sel):
    return page.locator(sel).input_value()


def test_edit_spool_says_what_its_box_does(wizard):  # noqa: F811
    """RED on the base: the Add wizard's "Per-spool Prusament scan" words."""
    _open(wizard)
    assert wizard.locator("#wiz-spool-rows-label").inner_text().startswith("📷 Link this spool to its Prusament QR")
    # The Add wizard's words come back with the next Add.
    wizard.evaluate("() => window.openWizardModal()")
    wizard.wait_for_function("() => wizardState.mode === 'manual'")
    assert wizard.locator("#wiz-spool-rows-label").inner_text().startswith("📷 Per-spool Prusament scan")


def test_a_qr_links_the_spool_at_save_and_sends_no_weights(wizard):  # noqa: F811
    """RED on the base: ✓ shown, and Save sent none of it (no product_url, no date)."""
    _open(wizard)
    _scan(wizard)
    row = _row(wizard)
    assert row["status"] == "linked-new", row
    assert "1012 g of filament" in row["note"] and "193 g empty" in row["note"], row
    assert "scan this QR on the dashboard" in row["note"]
    assert _value(wizard, "#wiz-spool-product_url") == CANONICAL
    sent = _save(wizard, EDIT)["spool_data"]
    extra = sent["extra"]
    assert extra["product_url"] == CANONICAL
    assert extra["purchase_url"] == TEMPLATE["purchase_link"]
    assert extra["prusament_manufacturing_date"] == "2026-03-01 10:00:00"
    assert extra["prusament_length_m"] == "336"
    assert "spool_overrides" not in _last_post(wizard)
    assert sent.get("initial_weight") != 1012.0 and sent.get("spool_weight") != 193.0, sent


def _last_post(page):
    return page.evaluate("() => window.__posts[window.__posts.length - 1].body")


def test_a_spool_already_linked_to_this_qr_says_so(wizard):  # noqa: F811
    _open(wizard, spool_extra={"product_url": "https://prusament.com/spool/?spoolId=abc123def0"})
    _scan(wizard)
    assert _row(wizard)["status"] == "linked"
    assert _value(wizard, "#wiz-spool-product_url") == "https://prusament.com/spool/?spoolId=abc123def0"


def test_a_spool_with_another_link_is_left_alone_and_save_still_works(wizard):  # noqa: F811
    _open(wizard, spool_extra={"product_url": "https://example.com/my-own-link"})
    _scan(wizard)
    row = _row(wizard)
    assert row["status"] == "refused", row
    assert "Product Link holds another link" in row["note"]
    assert _value(wizard, "#wiz-spool-product_url") == "https://example.com/my-own-link"
    # A refusal never blocks Save.
    assert _save(wizard, EDIT)["spool_data"]["extra"]["product_url"] == "https://example.com/my-own-link"


def test_a_qr_another_spool_holds_is_refused(wizard):  # noqa: F811
    _open(wizard, owners=[{"id": 60, "display": "#60 Prusament PLA (<b>Galaxy</b> Black)", "archived": True}])
    _scan(wizard)
    row = _row(wizard)
    assert row["status"] == "refused"
    assert "already linked to #60 Prusament PLA (<b>Galaxy</b> Black) (archived)" in row["note"]
    assert wizard.evaluate("() => document.querySelectorAll('#wiz-spool-link-note b').length") == 0
    assert _value(wizard, "#wiz-spool-product_url") == ""


def test_an_owner_check_fcc_couldnt_make_changes_nothing(wizard):  # noqa: F811
    _open(wizard)
    wizard.evaluate("() => { window.__answers['/api/prusament/linked_spools'] = { success: false, msg: 'x' }; }")
    _scan(wizard)
    row = _row(wizard)
    assert row["status"] == "refused" and "couldn't check" in row["note"], row
    assert _value(wizard, "#wiz-spool-product_url") == ""


def test_a_different_product_is_refused_naming_both(wizard):  # noqa: F811
    petg = dict(TEMPLATE, material="PETG", color_name="Prusa Orange", name="Prusament PETG Prusa Orange")
    _open(wizard, template=petg)
    _scan(wizard)
    row = _row(wizard)
    assert row["status"] == "refused", row
    assert "That QR is Prusament PETG Prusa Orange, and #57 is Prusament PLA Galaxy Black" in row["note"]
    assert _value(wizard, "#wiz-spool-product_url") == ""


def test_the_rows_clear_puts_the_boxes_back_and_a_hand_edit_wins(wizard):  # noqa: F811
    _open(wizard)
    _scan(wizard)
    assert _value(wizard, "#wiz-spool-product_url") == CANONICAL
    wizard.locator("[data-spool-row-idx='0'] .wiz-row-clear-btn").click()
    wizard.wait_for_timeout(50)
    assert _value(wizard, "#wiz-spool-product_url") == ""
    assert _value(wizard, "#wiz_spool_ef_prusament_length_m") == ""
    assert _row(wizard)["status"] == "empty"
    # Linked again, then the person types their own Product Link: Save sends theirs.
    _scan(wizard)
    wizard.locator("#wiz-spool-product_url").fill("https://example.com/theirs")
    assert _save(wizard, EDIT)["spool_data"]["extra"]["product_url"] == "https://example.com/theirs"


def test_an_answer_after_the_wizard_moved_on_changes_nothing(wizard):  # noqa: F811
    """A link check answered after the wizard was reset fills nothing in the new form."""
    _open(wizard)
    wizard.evaluate("""() => {
        window.__answers['/api/prusament/linked_spools'] = '__hold__';
        const orig = window.fetch;
        window.fetch = function (url, opts) {
            const path = String(url).split('?')[0];
            if (window.__answers[path] !== '__hold__') return orig(url, opts);
            return new Promise((resolve) => { (window.__held = window.__held || {})[path] = (b) => {
                const t = JSON.stringify(b);
                resolve({ ok: true, status: 200, json: () => Promise.resolve(JSON.parse(t)) }); }; });
        };
    }""")
    wizard.locator(ROW).fill(QR)
    wizard.locator(ROW).press("Tab")
    wizard.wait_for_function("() => !!(window.__held && window.__held['/api/prusament/linked_spools'])")
    # The typed link is an unsaved change: since Group 66.2 the open asks first, and its
    # Discard is what starts the form over (never awaited here: it waits on that answer).
    wizard.evaluate("() => { window.openWizardModal(); }")
    wizard.wait_for_selector("#fcc-wiz-dirty-confirm")
    wizard.locator("#fcc-wiz-dirty-confirm").click()
    wizard.wait_for_function("() => wizardState.mode === 'manual'")
    wizard.evaluate("() => window.__held['/api/prusament/linked_spools']({ success: true, spools: [] })")
    wizard.wait_for_timeout(100)
    assert _value(wizard, "#wiz-spool-product_url") == ""
    assert wizard.evaluate("() => window.__errors") == []
