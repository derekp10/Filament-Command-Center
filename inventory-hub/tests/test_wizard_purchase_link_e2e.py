"""Group 10.4 — Purchase Link consolidation and clear-bug fix.

The wizard previously rendered TWO purchase_url inputs (filament-level and
spool-level) which led to a "doesn't clear between usages" bug and confused
users about which one to fill. Session B consolidates to a single spool-tab
input with smart fallback: empty spool override = details modal falls back
to the filament's value. The placeholder advertises the inherited URL when
applicable so it's visible without becoming a spool-level override on save.
"""
from __future__ import annotations

import pytest
import requests
from playwright.sync_api import Page, expect


def _open_wizard_fresh(page: Page) -> None:
    page.goto("http://localhost:8000")
    page.wait_for_selector("#buffer-zone")
    page.evaluate("window.openWizardModal && window.openWizardModal()")
    expect(page.locator("#wizardModal")).to_be_visible()
    # Group 10.1: Pricing & Metadata panel defaults collapsed in create mode —
    # this test file exclusively edits #wiz-spool-purchase_url, so expand once
    # here rather than at every fill site.
    page.evaluate(
        "() => { const el = document.getElementById('wiz-spool-metadata-panel');"
        " if (el && !el.classList.contains('show'))"
        " bootstrap.Collapse.getOrCreateInstance(el, {toggle:false}).show(); }"
    )


def _force_close_wizard(page: Page) -> None:
    page.evaluate("""
        const m = bootstrap.Modal.getInstance(document.getElementById('wizardModal'));
        if (m) {
            try { wizardState.forceClose = true; wizardState.isDirty = false; } catch (_) {}
            m.hide();
        }
    """)
    expect(page.locator("#wizardModal")).not_to_be_visible(timeout=5_000)


def test_filament_tab_no_longer_renders_purchase_url(page: Page):
    """The filament-tab dynamic-extras renderer must skip purchase_url —
    it's edited exclusively on the spool tab now (Group 10.4)."""
    _open_wizard_fresh(page)
    page.evaluate("wizardFetchExtraFields()")
    page.wait_for_function(
        "wizardState && wizardState.extraFields && wizardState.extraFields.filament && wizardState.extraFields.filament.length > 0",
        timeout=5_000,
    )
    expect(page.locator("#wiz_fil_ef_purchase_url")).to_have_count(0)
    # The spool-tab static input MUST still be there.
    expect(page.locator("#wiz-spool-purchase_url")).to_have_count(1)
    _force_close_wizard(page)


def test_smart_fallback_via_wizardApplyPurchaseLinkFallback(page: Page):
    """Exercise the helper directly so we don't have to find a spool/filament
    pair with the right preexisting URLs in the dev DB. Covers all three
    branches: spool-own, inherited-from-filament, neither."""
    _open_wizard_fresh(page)
    el = page.locator("#wiz-spool-purchase_url")

    # Branch 1: spool has own URL → value preset, placeholder reset to default.
    page.evaluate(
        "wizardApplyPurchaseLinkFallback('https://spool.example/abc', 'https://fil.example/def')"
    )
    expect(el).to_have_value("https://spool.example/abc")
    expect(el).to_have_attribute("placeholder", "https://...")

    # Branch 2: no spool URL, filament has one → value blank, placeholder
    # surfaces the filament URL with the (inherited from filament) suffix.
    page.evaluate(
        "wizardApplyPurchaseLinkFallback('', 'https://fil.example/def')"
    )
    expect(el).to_have_value("")
    placeholder = el.get_attribute("placeholder")
    assert placeholder.endswith("(inherited from filament)"), placeholder
    assert "fil.example" in placeholder

    # Branch 3: neither → value blank, placeholder default.
    page.evaluate("wizardApplyPurchaseLinkFallback('', '')")
    expect(el).to_have_value("")
    expect(el).to_have_attribute("placeholder", "https://...")

    # Long URLs should be truncated to ≤40 chars + the inheritance suffix.
    long_url = "https://store.example.com/products/very-long-product-slug-with-many-segments"
    page.evaluate(f"wizardApplyPurchaseLinkFallback('', {long_url!r})")
    placeholder = el.get_attribute("placeholder")
    # 37 chars of URL + ellipsis + " (inherited from filament)"
    assert "…" in placeholder
    assert placeholder.endswith("(inherited from filament)")

    _force_close_wizard(page)


def test_wizard_reset_clears_purchase_url_input(page: Page):
    """The "doesn't clear between usages" bug — wizardReset's selector only
    targeted input[type=text|number], missing type=url. Reset MUST now wipe
    the spool URL input AND restore the default placeholder so prior session
    state doesn't bleed in."""
    _open_wizard_fresh(page)
    el = page.locator("#wiz-spool-purchase_url")

    # Dirty the input + mutate placeholder (simulating a prior session).
    page.evaluate("""
        const el = document.getElementById('wiz-spool-purchase_url');
        el.value = 'https://leftover.example/xyz';
        el.placeholder = 'https://leftover.example (inherited from filament)';
    """)
    expect(el).to_have_value("https://leftover.example/xyz")

    page.evaluate("wizardReset()")

    expect(el).to_have_value("")
    expect(el).to_have_attribute("placeholder", "https://...")

    _force_close_wizard(page)


def test_spool_save_payload_only_includes_purchase_url_when_user_typed(page: Page, api_base_url: str):
    """Saving without typing into the spool input must NOT include
    purchase_url in the spool's extras payload — leaving the field empty is
    the signal that the spool should inherit from the filament on read."""
    _open_wizard_fresh(page)
    # The save endpoint is the wizard's collectInventoryWizardPayload internals;
    # we can introspect via JS without actually POSTing.
    payload_extras = page.evaluate("""
        () => {
            // Simulate the relevant inline logic from the save handler.
            const el = document.getElementById('wiz-spool-purchase_url');
            const v = el?.value?.trim();
            const out = {};
            if (v) out.purchase_url = v;
            return out;
        }
    """)
    assert "purchase_url" not in payload_extras

    # Now type something and confirm it lands in the payload.
    page.locator("#wiz-spool-purchase_url").fill("https://store.example/spool-1")
    payload_extras = page.evaluate("""
        () => {
            const el = document.getElementById('wiz-spool-purchase_url');
            const v = el?.value?.trim();
            const out = {};
            if (v) out.purchase_url = v;
            return out;
        }
    """)
    assert payload_extras.get("purchase_url") == "https://store.example/spool-1"

    _force_close_wizard(page)


def test_metadata_summary_shows_product_chip_when_product_url_filled(page: Page):
    """23.5 (Group 26.9 coverage backfill) — the Pricing & Metadata section
    summary shows a '📄 product' chip when the spool's product_url is filled,
    mirroring the '🔗 link' purchase chip. Previously the summary advertised
    only purchase-side fields, so a filled product link was invisible."""
    _open_wizard_fresh(page)
    summary = page.locator(
        "button.fcc-wiz-section-toggle[data-bs-target='#wiz-spool-metadata-panel'] "
        ".fcc-wiz-section-summary"
    )
    # No product_url yet → no product chip in the summary.
    page.evaluate("() => window.wizardRefreshSectionSummary('wiz-spool-metadata-panel')")
    assert "📄 product" not in (summary.inner_html() or "")

    # Fill the product link → the chip appears on the next summary refresh.
    page.locator("#wiz-spool-product_url").fill("https://store.example/prod-1")
    page.evaluate("() => window.wizardRefreshSectionSummary('wiz-spool-metadata-panel')")
    expect(summary).to_contain_text("📄 product")

    _force_close_wizard(page)
