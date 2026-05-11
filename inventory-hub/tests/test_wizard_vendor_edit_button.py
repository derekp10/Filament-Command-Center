"""Tests for the wizard's vendor buttons after the Group 6.2 cleanup.

The Add/Edit Wizard previously had a single ✏️ button that toggled to a
"type new vendor name" text input (the `wizardToggleVendorMode` flow), which
sent `extra.external_vendor_name` on submit and let the backend create the
vendor as a side-effect of the filament create. That legacy path was
retired (and so was the text input + backend handler) in favor of:

  - ✏️ (id wiz-fil-vendor-edit-btn) — opens the Vendor Edit modal, shown
    only when an existing vendor is selected.
  - ➕ — opens the Vendor Edit modal in CREATE mode, pre-filling the name
    field with whatever's typed in the search input. On save, the wizard
    listens for `vendor:created` and auto-selects the new vendor in the
    combobox so the user can continue without hunting it down.

Covers:
  - Both buttons render in the wizard.
  - ✏️ visibility tracks vendor selection state.
  - ✏️ click opens the Vendor Edit modal in edit mode.
  - ➕ click opens the Vendor Edit modal in CREATE mode, pre-filled from search.
  - `vendor:created` event refreshes the vendor dropdown and auto-selects
    the new vendor in the wizard.
  - Legacy `wizardToggleVendorMode` function is gone.
  - Legacy `wiz-fil-vendor-new` text input is gone from the markup.
"""
from __future__ import annotations

from playwright.sync_api import Page, expect


def _stub_wizard_vendors(page: Page) -> None:
    """Stub /api/external/vendors + /api/vendors so the wizard's vendor
    combobox and the Vendor Edit modal both find a deterministic dataset.

    POST /api/vendors records its payload and returns a synthesized new
    vendor with id=99 so the test can verify the create round-trip.
    """
    page.evaluate(
        """
        window.__lastVendorPost = null;
        window.__vendorsList = [
            {id: 11, name: 'WizAlpha', comment: 'wiz-alpha note',
             empty_spool_weight: 200, external_id: '',
             registered: '2026-01-15T00:00:00Z',
             extra: {website: '"https://wizalpha.example"'}},
            {id: 12, name: 'WizBeta', comment: '',
             empty_spool_weight: null, external_id: '',
             registered: '2026-02-15T00:00:00Z',
             extra: {}},
        ];
        const origFetch = window.fetch;
        window.fetch = async (url, opts) => {
            if (typeof url !== 'string') return origFetch(url, opts);
            const method = (opts && opts.method) || 'GET';
            if ((url === '/api/external/vendors' || url === '/api/vendors') && method === 'GET') {
                return new Response(JSON.stringify({success: true, vendors: window.__vendorsList}),
                    {status: 200, headers: {'Content-Type': 'application/json'}});
            }
            if (url === '/api/vendors' && method === 'POST') {
                window.__lastVendorPost = JSON.parse(opts.body);
                const sent = (window.__lastVendorPost.data) || {};
                const newV = {
                    id: 99,
                    name: sent.name || '',
                    comment: sent.comment || '',
                    external_id: sent.external_id || '',
                    empty_spool_weight: sent.empty_spool_weight,
                    registered: '2026-05-11T00:00:00Z',
                    extra: sent.extra || {},
                };
                // Appending to the cache mirrors what the backend would do
                // next time /api/external/vendors is fetched.
                window.__vendorsList.push(newV);
                return new Response(JSON.stringify({success: true, vendor: newV}),
                    {status: 200, headers: {'Content-Type': 'application/json'}});
            }
            return origFetch(url, opts);
        };
        """
    )


def _open_wizard(page: Page) -> None:
    page.evaluate("() => window.openWizardModal()")
    expect(page.locator("#wizardModal.show")).to_have_count(1)
    page.wait_for_function(
        "() => document.getElementById('wiz-fil-vendor-edit-btn') !== null"
    )


def _wait_ready(page: Page) -> None:
    page.goto("http://localhost:8000")
    page.wait_for_selector("#buffer-zone")
    page.wait_for_function("typeof window.openWizardModal === 'function'")
    page.wait_for_function("typeof window.openVendorEditModal === 'function'")
    page.wait_for_function("typeof window.openVendorCreateModal === 'function'")
    page.wait_for_function("typeof window.wizardComboboxSet === 'function'")


def test_both_vendor_buttons_render_in_wizard(page: Page):
    _wait_ready(page)
    _stub_wizard_vendors(page)
    _open_wizard(page)
    expect(page.locator("#wiz-fil-vendor-edit-btn")).to_have_count(1)
    # ➕ is identified by its onclick handler pointing at openVendorCreateModal.
    plus_btn = page.locator(
        '#wiz-fil-vendor-group button[onclick^="openVendorCreateModal"]'
    )
    expect(plus_btn).to_have_count(1)


def test_legacy_add_new_text_input_is_gone(page: Page):
    """Regression — the wiz-fil-vendor-new text input and the
    wizardToggleVendorMode function must not exist after the Group 6.2 cleanup."""
    _wait_ready(page)
    _stub_wizard_vendors(page)
    _open_wizard(page)
    expect(page.locator("#wiz-fil-vendor-new")).to_have_count(0)
    has_toggle = page.evaluate(
        "() => typeof window.wizardToggleVendorMode === 'function'"
    )
    assert has_toggle is False, "wizardToggleVendorMode should have been removed"


def test_edit_btn_hidden_when_no_vendor_selected(page: Page):
    _wait_ready(page)
    _stub_wizard_vendors(page)
    _open_wizard(page)
    expect(page.locator("#wiz-fil-vendor-edit-btn")).to_be_hidden()


def test_edit_btn_shows_after_vendor_selection(page: Page):
    _wait_ready(page)
    _stub_wizard_vendors(page)
    _open_wizard(page)
    page.evaluate(
        "() => window.wizardComboboxSet('wiz-fil-vendor-search', 'wiz-fil-vendor-sel', '11', 'WizAlpha')"
    )
    expect(page.locator("#wiz-fil-vendor-edit-btn")).to_be_visible()
    page.evaluate(
        "() => window.wizardComboboxSet('wiz-fil-vendor-search', 'wiz-fil-vendor-sel', '', '')"
    )
    expect(page.locator("#wiz-fil-vendor-edit-btn")).to_be_hidden()


def test_edit_btn_click_opens_vendor_edit_modal(page: Page):
    _wait_ready(page)
    _stub_wizard_vendors(page)
    _open_wizard(page)
    page.evaluate(
        "() => window.wizardComboboxSet('wiz-fil-vendor-search', 'wiz-fil-vendor-sel', '11', 'WizAlpha')"
    )
    page.locator("#wiz-fil-vendor-edit-btn").click()
    expect(page.locator("#vendorEditModal.show")).to_have_count(1)
    assert page.locator("#vendoredit-id").input_value() == "11"
    assert page.locator("#vendoredit-name").input_value() == "WizAlpha"


def test_plus_btn_opens_create_modal_prefilled_from_search(page: Page):
    """The ➕ button reads whatever is currently typed in the vendor search
    input and pre-fills the create-modal's name field with it — so a user
    who started typing a non-matching name doesn't have to retype."""
    _wait_ready(page)
    _stub_wizard_vendors(page)
    _open_wizard(page)
    # User types a name that doesn't match anything in the cache.
    page.locator("#wiz-fil-vendor-search").fill("Polymaker Plus")
    page.locator(
        '#wiz-fil-vendor-group button[onclick^="openVendorCreateModal"]'
    ).click()
    expect(page.locator("#vendorEditModal.show")).to_have_count(1)
    # Empty id → create mode; title flips to ➕.
    assert page.locator("#vendoredit-id").input_value() == ""
    assert page.locator("#vendoredit-name").input_value() == "Polymaker Plus"
    title = page.locator("#vendorEditModalLabel").inner_text()
    assert "Add Manufacturer" in title


def test_vendor_created_autoselects_in_wizard(page: Page):
    """End-to-end frontend flow: ➕ → fill name → save → wizard auto-selects."""
    _wait_ready(page)
    _stub_wizard_vendors(page)
    _open_wizard(page)
    page.locator("#wiz-fil-vendor-search").fill("Brand New Co")
    page.locator(
        '#wiz-fil-vendor-group button[onclick^="openVendorCreateModal"]'
    ).click()
    expect(page.locator("#vendorEditModal.show")).to_have_count(1)
    # User adds website + saves. Use evaluate-call rather than .click() to
    # sidestep Bootstrap's stacked-modal pointer-events quirk (the Save
    # button is occasionally non-actionable in Playwright for a few ticks
    # after the modal animation completes).
    # User adds website + saves. Use evaluate-call rather than .click() to
    # sidestep Bootstrap's stacked-modal pointer-events quirk (the Save
    # button is occasionally non-actionable in Playwright for a few ticks
    # after the modal animation completes).
    page.locator("#vendoredit-website").fill("https://brandnew.example")
    page.locator("#vendoredit-empty-weight").fill("180")
    page.evaluate("() => window.vendorEditSave()")
    page.wait_for_function("window.__lastVendorPost !== null")
    # POST payload includes name + extras.website + empty_spool_weight.
    posted = page.evaluate("() => window.__lastVendorPost.data")
    assert posted["name"] == "Brand New Co"
    assert posted["extra"]["website"] == '"https://brandnew.example"'
    assert posted["empty_spool_weight"] == 180
    # Wait for the auto-select to land (vendor:created → wizardFetchVendors → wizardComboboxSet).
    # The Vendor Edit modal's hide animation may still be running at this
    # point; the autoselect is the load-bearing assertion either way.
    page.wait_for_function(
        "() => document.getElementById('wiz-fil-vendor-sel').value === '99'"
    )
    assert page.locator("#wiz-fil-vendor-search").input_value() == "Brand New Co"
    # ✏️ button is now visible (existing vendor selected).
    expect(page.locator("#wiz-fil-vendor-edit-btn")).to_be_visible()
    # The vendor's empty_spool_weight (180) should propagate to the
    # filament's empty-weight cascade, and wizardSetupFieldSync mirrors that
    # into the spool empty-weight. This is the path the user explicitly
    # asked us to verify — without it, a brand-new vendor's weight value
    # would be lost the moment the user moved to the spool step.
    assert page.locator("#wiz-fil-empty_weight").input_value() == "180"
    assert page.locator("#wiz-spool-empty_weight").input_value() == "180"


def test_vendor_created_does_not_clobber_user_typed_empty_weight(page: Page):
    """If the user manually typed an empty-weight value before creating the
    vendor, the post-create cascade must NOT overwrite their input."""
    _wait_ready(page)
    _stub_wizard_vendors(page)
    _open_wizard(page)
    # User types a specific empty weight first.
    page.locator("#wiz-fil-empty_weight").fill("250")
    page.locator("#wiz-fil-vendor-search").fill("Custom Spool Brand")
    page.locator(
        '#wiz-fil-vendor-group button[onclick^="openVendorCreateModal"]'
    ).click()
    expect(page.locator("#vendorEditModal.show")).to_have_count(1)
    page.locator("#vendoredit-empty-weight").fill("180")
    page.evaluate("() => window.vendorEditSave()")
    page.wait_for_function("window.__lastVendorPost !== null")
    page.wait_for_function(
        "() => document.getElementById('wiz-fil-vendor-sel').value === '99'"
    )
    # User's explicit 250 wins over the cascade's would-be 180.
    assert page.locator("#wiz-fil-empty_weight").input_value() == "250"
