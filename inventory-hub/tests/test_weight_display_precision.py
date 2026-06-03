"""Weight display precision (buglist line 51).

Derek's scale only reads whole grams, so manual weights carry an inherent
sub-gram variance that originates in the fractional empty-spool tare. The
reported "off by ~1g" was actually INCONSISTENT rounding: the wizard rounded
`used`/`remaining` to whole grams (.toFixed(0)) and persisted that, while the
Details modal showed 1 decimal — so the numbers stopped reconciling and a
sub-gram delta looked like a whole-gram bug.

Decision (2026-06-03): MIXED precision.
- GLANCE surfaces (cards/search/buffer/quick-swap/printer-status): whole grams
  (already the case via Math.round — not retested here).
- PRECISE surfaces (Spool Details, wizard weight fields, weigh-out, WeightEntry):
  up to 1 decimal, trailing ".0" trimmed.
- Data stored exact; display-only formatting via window.fmtGramsGlance /
  window.fmtGramsPrecise (weight_utils.js).

These tests pin the formatter contract, the wizard's used+remaining
reconciliation (the core fix), and the Spool Details modal's precise display.
"""
from __future__ import annotations

import json

import pytest
from playwright.sync_api import Page, expect


def _boot(page: Page, base_url: str, reset_dom_state_js: str):
    page.goto(base_url)
    page.wait_for_selector("#command-buffer, #buffer-zone", timeout=10000)
    page.evaluate(reset_dom_state_js)


@pytest.mark.usefixtures("require_server")
def test_weight_formatters_contract(page: Page, base_url: str, reset_dom_state_js: str):
    _boot(page, base_url, reset_dom_state_js)
    page.wait_for_function(
        "typeof window.fmtGramsGlance === 'function' && typeof window.fmtGramsPrecise === 'function'",
        timeout=10000,
    )
    out = page.evaluate("""() => {
        const g = window.fmtGramsGlance, p = window.fmtGramsPrecise;
        return {
            glance: [g(849.6), g(150.4), g(150), g(0), g(849.5)],
            precise: [p(849.6), p(150), p(150.04), p(150.45), p(0), p(1000)],
            bad: [g(NaN), p(undefined), p(null)],
        };
    }""")
    # GLANCE = whole grams (nearest).
    assert out["glance"] == ["850", "150", "150", "0", "850"]
    # PRECISE = up to 1 decimal, trailing .0 trimmed.
    assert out["precise"] == ["849.6", "150", "150", "150.5", "0", "1000"]
    # Non-finite input → empty string (never "NaN"/"undefined" on screen).
    assert out["bad"] == ["", "", ""]


@pytest.mark.usefixtures("require_server")
def test_wizard_used_and_remaining_reconcile_at_one_decimal(page: Page, base_url: str, reset_dom_state_js: str):
    _boot(page, base_url, reset_dom_state_js)
    page.wait_for_function(
        "document.getElementById('wiz-spool-used') && typeof window.wizardCalcRemainingFromUsed === 'function'"
        " && typeof window.wizardCalcUsedWeight === 'function'",
        timeout=10000,
    )

    # (a) used -> remaining path: a fractional used must keep its decimal AND
    # produce a remaining that reconciles to initial (no surprise 1g).
    res_a = page.evaluate("""() => {
        document.getElementById('wiz-spool-initial_weight').value = '1000';
        document.getElementById('wiz-spool-used').value = '150.4';
        window.wizardCalcRemainingFromUsed();
        const used = document.getElementById('wiz-spool-used').value;
        const rem = document.getElementById('wiz-spool-remaining').value;
        return { used, rem, sum: Number(used) + Number(rem) };
    }""")
    assert res_a["rem"] == "849.6", f"remaining should keep the decimal, got {res_a['rem']!r}"
    assert res_a["sum"] == 1000, f"used + remaining must reconcile to initial, got {res_a}"

    # (b) gross-scale path: scale=1065, tare=215.4, net=1000 -> used=150.4.
    res_b = page.evaluate("""() => {
        document.getElementById('wiz-spool-initial_weight').value = '1000';
        document.getElementById('wiz-spool-empty_weight').value = '215.4';
        document.getElementById('wiz-spool-scale').value = '1065';
        window.wizardCalcUsedWeight();
        const used = document.getElementById('wiz-spool-used').value;
        const rem = document.getElementById('wiz-spool-remaining').value;
        return { used, rem, sum: Number(used) + Number(rem) };
    }""")
    assert res_b["used"] == "150.4", f"gross path should compute used=150.4, got {res_b['used']!r}"
    assert res_b["rem"] == "849.6", f"gross path remaining, got {res_b['rem']!r}"
    assert res_b["sum"] == 1000, f"used + remaining must reconcile, got {res_b}"


def _route_spool(page: Page, used, remaining):
    payload = {
        "id": 991100, "archived": False, "location": "Room LR", "comment": "",
        "used_weight": used, "remaining_weight": remaining, "extra": {},
        "filament": {"id": 55, "name": "T", "material": "PLA", "color_hex": "ff8800",
                     "weight": 1000, "settings_extruder_temp": 210, "settings_bed_temp": 60,
                     "vendor": {"name": "V"}, "extra": {}},
    }
    page.route("**/api/spool_details*", lambda r: r.fulfill(
        status=200, content_type="application/json", body=json.dumps(payload)))


@pytest.mark.usefixtures("require_server")
def test_spool_details_modal_precise_weight(page: Page, base_url: str, reset_dom_state_js: str):
    # Fractional case: 1 decimal kept.
    _route_spool(page, used=150.4, remaining=849.6)
    _boot(page, base_url, reset_dom_state_js)
    page.wait_for_function("typeof openSpoolDetails === 'function' && modals && modals.spoolModal", timeout=10000)
    page.evaluate("openSpoolDetails(991100)")
    expect(page.locator("#spoolModal")).to_be_visible(timeout=5000)
    assert page.locator("#detail-used").inner_text().strip() == "150.4g"
    assert page.locator("#detail-remaining").inner_text().strip() == "849.6g"


@pytest.mark.usefixtures("require_server")
def test_spool_details_modal_whole_weight_trims_trailing_zero(page: Page, base_url: str, reset_dom_state_js: str):
    # Whole case: no "850.0g" trailing zero (the old .toFixed(1) behaviour).
    _route_spool(page, used=150, remaining=850)
    _boot(page, base_url, reset_dom_state_js)
    page.wait_for_function("typeof openSpoolDetails === 'function' && modals && modals.spoolModal", timeout=10000)
    page.evaluate("openSpoolDetails(991100)")
    expect(page.locator("#spoolModal")).to_be_visible(timeout=5000)
    assert page.locator("#detail-used").inner_text().strip() == "150g"
    assert page.locator("#detail-remaining").inner_text().strip() == "850g"
