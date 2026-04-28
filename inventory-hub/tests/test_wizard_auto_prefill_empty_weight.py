"""
Tests for wizard auto-prefill of `wiz-spool-empty_weight` from the parent
filament/vendor cascade — Phase 1 (L34) of the weight-handling unification.

Covers `window.openNewSpoolFromFilamentWizard(filamentId)`:
  - When the parent filament has its own `spool_weight`, it pre-fills the
    spool empty-weight field and surfaces the "from filament" badge.
  - When the filament has none but the vendor has `empty_spool_weight`, the
    badge says "from vendor".
  - When neither level has a value, the field stays empty and the badge stays
    hidden.
  - Typing in the field clears the badge (the inherited value becomes a user
    override).
"""
from __future__ import annotations

from playwright.sync_api import Page, expect


def _open_dashboard_and_wait(page: Page):
    page.goto("http://localhost:8000")
    page.wait_for_selector("#buffer-zone")
    page.wait_for_function(
        "typeof window.openNewSpoolFromFilamentWizard === 'function'", timeout=5_000
    )
    page.wait_for_function(
        "typeof window.resolveEmptySpoolWeightSource === 'function'", timeout=5_000
    )


def _stub_filament_details(page: Page, filament: dict):
    """Stub /api/filament_details so the wizard's open flow loads our fixture."""
    page.evaluate(
        """(fil) => {
            const origFetch = window.fetch;
            window.fetch = async (url, opts) => {
                const u = typeof url === 'string' ? url : (url && url.url) || '';
                if (u.startsWith('/api/filament_details')) {
                    return new Response(JSON.stringify(fil),
                        { status: 200, headers: {'Content-Type': 'application/json'} });
                }
                return origFetch(url, opts);
            };
        }""",
        filament,
    )


def test_prefill_from_filament_shows_filament_badge(page: Page):
    _open_dashboard_and_wait(page)
    _stub_filament_details(page, {
        "id": 7,
        "name": "Crimson Red",
        "material": "PLA",
        "spool_weight": 180,  # filament has its own value
        "vendor": {"id": 1, "name": "CC3D", "empty_spool_weight": 200},
    })

    page.evaluate("() => { window.openNewSpoolFromFilamentWizard(7); }")
    page.wait_for_selector("#wizardModal.show", timeout=3_000)
    # Wait for async fetch + prefill to settle
    page.wait_for_function(
        "document.getElementById('wiz-spool-empty_weight').value === '180'", timeout=3_000
    )

    badge = page.locator("#wiz-spool-empty-inherited-badge")
    expect(badge).to_be_visible()
    source = page.locator("#wiz-spool-empty-inherited-source").inner_text()
    assert source == "filament", f"expected 'filament', got {source!r}"


def test_prefill_falls_back_to_vendor_shows_vendor_badge(page: Page):
    _open_dashboard_and_wait(page)
    _stub_filament_details(page, {
        "id": 7,
        "name": "Crimson Red",
        "material": "PLA",
        "spool_weight": None,  # no filament-level value
        "vendor": {"id": 1, "name": "CC3D", "empty_spool_weight": 200},
    })

    page.evaluate("() => { window.openNewSpoolFromFilamentWizard(7); }")
    page.wait_for_selector("#wizardModal.show", timeout=3_000)
    page.wait_for_function(
        "document.getElementById('wiz-spool-empty_weight').value === '200'", timeout=3_000
    )

    badge = page.locator("#wiz-spool-empty-inherited-badge")
    expect(badge).to_be_visible()
    source = page.locator("#wiz-spool-empty-inherited-source").inner_text()
    assert source == "vendor", f"expected 'vendor', got {source!r}"


def test_prefill_empty_when_neither_level_has_value(page: Page):
    _open_dashboard_and_wait(page)
    _stub_filament_details(page, {
        "id": 7,
        "name": "Crimson Red",
        "material": "PLA",
        "spool_weight": None,
        "vendor": {"id": 1, "name": "CC3D"},  # no empty_spool_weight
    })

    page.evaluate("() => { window.openNewSpoolFromFilamentWizard(7); }")
    page.wait_for_selector("#wizardModal.show", timeout=3_000)
    # Give the prefill a moment to run
    page.wait_for_function(
        "document.getElementById('wiz-status-msg').innerText.includes('pre-filled')",
        timeout=3_000,
    )

    field_value = page.evaluate(
        "() => document.getElementById('wiz-spool-empty_weight').value"
    )
    assert field_value == "", f"expected empty field, got {field_value!r}"

    badge = page.locator("#wiz-spool-empty-inherited-badge")
    expect(badge).to_be_hidden()


def test_user_edit_clears_inherited_badge(page: Page):
    _open_dashboard_and_wait(page)
    _stub_filament_details(page, {
        "id": 7,
        "name": "Crimson Red",
        "material": "PLA",
        "spool_weight": 180,
        "vendor": {"id": 1, "name": "CC3D"},
    })

    page.evaluate("() => { window.openNewSpoolFromFilamentWizard(7); }")
    page.wait_for_selector("#wizardModal.show", timeout=3_000)
    page.wait_for_function(
        "document.getElementById('wiz-spool-empty_weight').value === '180'", timeout=3_000
    )

    badge = page.locator("#wiz-spool-empty-inherited-badge")
    expect(badge).to_be_visible()

    # Type in the field — the badge should disappear.
    field = page.locator("#wiz-spool-empty_weight")
    field.click()
    # Append a digit; existing value 180 -> 1805
    field.press("End")
    field.press("5")

    expect(badge).to_be_hidden()
    new_value = page.evaluate("() => document.getElementById('wiz-spool-empty_weight').value")
    assert new_value == "1805", f"expected user override '1805', got {new_value!r}"
