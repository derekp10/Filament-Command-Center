"""31.1 — the wizard weight grid's guided scale-entry launcher.

Derek's pain: with a gross scale reading + a known empty-spool tare he couldn't
tell which of the six weight fields to fill to get the tare deducted into
remaining/total. The `⚖️ Weigh from scale…` button opens the shared
<WeightEntry> overlay; on Save it writes the computed values back into the grid.

These drive the overlay directly (the wizard's weight inputs live in the page
DOM), seed the grid, launch, type a gross reading, save, and assert the grid.
"""
from __future__ import annotations

from playwright.sync_api import Page, expect


def _open_dashboard(page: Page):
    page.goto("http://localhost:8000")
    page.wait_for_selector("#buffer-zone")
    page.wait_for_function(
        "typeof window.wizardOpenWeightEntry === 'function'", timeout=5_000
    )
    page.wait_for_function(
        "window.WeightEntry && typeof window.WeightEntry.openModal === 'function'",
        timeout=5_000,
    )


def _set(page: Page, field_id: str, value: str):
    page.evaluate(
        "([id, v]) => { const el = document.getElementById(id); if (el) el.value = v; }",
        [field_id, value],
    )


def test_wizard_weigh_launcher_known_net(page: Page):
    """Known original net (1000g) + tare 220 + gross 645 -> used 575,
    remaining 425, initial unchanged. This is the ordinary gross-mode path."""
    _open_dashboard(page)

    _set(page, "wiz-spool-initial_weight", "1000")
    _set(page, "wiz-spool-empty_weight", "220")
    _set(page, "wiz-spool-used", "0")
    _set(page, "wiz-fil-weight", "")
    # Vendor display name lives in the visible search box (hidden -sel holds id).
    _set(page, "wiz-fil-vendor-search", "Acme Filaments")
    _set(page, "wiz-fil-material", "PLA")

    page.evaluate("window.wizardOpenWeightEntry()")

    overlay = page.locator("#fcc-weight-entry-overlay")
    expect(overlay).to_be_visible()
    # The vendor context must surface in the overlay header (read from the
    # visible search field, not the hidden id-holder).
    expect(overlay).to_contain_text("Acme Filaments")
    # Force gross mode (a stored default-mode preference must not decide the test).
    overlay.locator('.fcc-we-tab[data-mode="gross"]').click()

    inp = page.locator("#fcc-we-input")
    inp.fill("645")
    expect(page.locator("#fcc-we-preview")).to_contain_text("425")

    page.locator("#fcc-we-save").click()
    expect(overlay).not_to_be_visible()

    assert page.eval_on_selector("#wiz-spool-used", "el => el.value") == "575"
    assert page.eval_on_selector("#wiz-spool-remaining", "el => el.value") == "425"
    # Original net capacity is untouched on the known path.
    assert page.eval_on_selector("#wiz-spool-initial_weight", "el => el.value") == "1000"


def test_wizard_weigh_launcher_unknown_net(page: Page):
    """No original net known anywhere (the reason we dropped hard-coded 1000g):
    gross 645 − tare 220 = 425 available, recorded as a FULL 425g spool
    (initial 425, used 0, remaining 425)."""
    _open_dashboard(page)

    # Blank every net source so the launcher takes the unknown-initial path.
    _set(page, "wiz-spool-initial_weight", "")
    _set(page, "wiz-fil-weight", "")
    _set(page, "wiz-spool-empty_weight", "220")
    _set(page, "wiz-spool-used", "0")

    page.evaluate("window.wizardOpenWeightEntry()")

    overlay = page.locator("#fcc-weight-entry-overlay")
    expect(overlay).to_be_visible()
    overlay.locator('.fcc-we-tab[data-mode="gross"]').click()

    inp = page.locator("#fcc-we-input")
    inp.fill("645")
    # Preview frames it as available + recorded-as-full.
    expect(page.locator("#fcc-we-preview")).to_contain_text("Available on spool")
    expect(page.locator("#fcc-we-preview")).to_contain_text("425")

    page.locator("#fcc-we-save").click()
    expect(overlay).not_to_be_visible()

    assert page.eval_on_selector("#wiz-spool-initial_weight", "el => el.value") == "425"
    assert page.eval_on_selector("#wiz-spool-used", "el => el.value") == "0"
    assert page.eval_on_selector("#wiz-spool-remaining", "el => el.value") == "425"


def test_wizard_weigh_launcher_missing_tare_prompts(page: Page):
    """Unknown net + gross mode + NO tare anywhere -> the shared missing-empty
    prompt fires on Save instead of silently miscomputing."""
    _open_dashboard(page)

    _set(page, "wiz-spool-initial_weight", "")
    _set(page, "wiz-fil-weight", "")
    _set(page, "wiz-spool-empty_weight", "")
    _set(page, "wiz-fil-empty_weight", "")

    page.evaluate("window.wizardOpenWeightEntry()")
    overlay = page.locator("#fcc-weight-entry-overlay")
    expect(overlay).to_be_visible()
    overlay.locator('.fcc-we-tab[data-mode="gross"]').click()

    page.locator("#fcc-we-input").fill("645")
    # Preview warns the tare is missing.
    expect(page.locator("#fcc-we-preview")).to_contain_text("Empty-spool weight is missing")

    page.locator("#fcc-we-save").click()
    # The shared missing-empty-weight overlay appears on the confirm tier.
    expect(page.locator("#fcc-missing-empty-weight-overlay")).to_be_visible()
    # 31.1 review fix: with NO known original net, the "Skip — save as Used"
    # button must NOT be offered — reinterpreting a gross reading as net would
    # book the spool tare as filament. Only Cancel + Save & Continue.
    expect(page.locator("#fcc-missing-empty-weight-overlay-skip")).to_have_count(0)
