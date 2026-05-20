"""L144 round 2 (Group 17.1 edit-toggle follow-up) — both
`sample_printed` and `needs_label_print` should appear as boolean
toggle checkboxes in the wizard's Filament dynamic-fields panel.
Both fields are already registered in setup_fields.py:filament_standards
as `boolean`; only the UI filter in `wizardFetchExtraFields` was hiding
needs_label_print. After the un-hide, the dynamic-field renderer turns
both into native checkbox inputs.
"""
from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect


@pytest.mark.usefixtures("require_server")
def test_wizard_filament_extras_include_sample_and_label_toggles(page: Page, base_url: str, reset_dom_state_js: str):
    page.goto(base_url)
    page.wait_for_selector("#command-buffer, #buffer-zone", timeout=10000)
    page.evaluate(reset_dom_state_js)
    # `wizardFetchExtraFields` is a script-scope const, not on window
    # (same shape as `state` / `openFilamentDetails`). Probe via bare name.
    page.wait_for_function(
        "typeof window.openWizardModal === 'function' && typeof wizardFetchExtraFields === 'function'",
        timeout=10000,
    )

    page.evaluate("window.openWizardModal()")
    expect(page.locator("#wizardModal")).to_be_visible(timeout=5000)

    # The dynamic filament-extras host gets populated on open. Wait until
    # both expected inputs render.
    page.wait_for_function(
        """() => {
            const host = document.getElementById('wiz-fil-dynamic-extra-fields');
            if (!host) return false;
            return !!host.querySelector('[data-key="sample_printed"]')
                && !!host.querySelector('[data-key="needs_label_print"]');
        }""",
        timeout=5000,
    )

    sample = page.locator("#wiz-fil-dynamic-extra-fields [data-key='sample_printed']")
    label = page.locator("#wiz-fil-dynamic-extra-fields [data-key='needs_label_print']")
    # Both inputs are RENDERED into the DOM at wizard-open time; they may
    # be hidden inside a collapsed extras panel until the user expands it.
    # Visibility-after-expand is a Bootstrap concern, not the regression
    # we're guarding here — assert presence + correct shape.
    expect(sample).to_have_count(1)
    expect(label).to_have_count(1)

    sample_type = sample.evaluate("el => el.type")
    label_type = label.evaluate("el => el.type")
    assert sample_type == "checkbox", f"sample_printed should render as checkbox, got type={sample_type!r}"
    assert label_type == "checkbox", f"needs_label_print should render as checkbox, got type={label_type!r}"
