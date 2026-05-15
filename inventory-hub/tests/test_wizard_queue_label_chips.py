"""Group 17.3 — after a successful create-wizard run, each just-created
spool id renders a "🖨️ #N" chip in the wizard's status message area.
Clicking the chip enqueues a label without leaving the wizard.
"""
from __future__ import annotations

import json

import pytest
from playwright.sync_api import Page, expect


@pytest.mark.usefixtures("require_server")
def test_wizard_success_state_renders_queue_label_chips(page: Page, base_url: str):
    page.goto(base_url)
    page.wait_for_function("typeof window.openWizardModal === 'function' && typeof window.wizardSubmit === 'function'", timeout=10000)

    # Mock the create endpoint so we can drive the success branch without
    # needing valid form input.
    captured = {}
    def handle(route):
        req = route.request
        if req.method == 'POST' and req.url.endswith('/api/create_inventory_wizard'):
            captured['hit'] = True
            route.fulfill(
                status=200,
                content_type='application/json',
                body=json.dumps({"success": True, "filament_id": 999, "created_spools": [9991, 9992]}),
            )
        else:
            route.continue_()
    page.route("**/api/create_inventory_wizard", handle)

    # Open the wizard so wizardState is initialized; then patch the DOM
    # field-reads inside wizardSubmit by setting safe defaults on the
    # required inputs. Anything missing throws — so we cover the few
    # inputs wizardSubmit always reads.
    page.evaluate("window.openWizardModal && window.openWizardModal()")
    expect(page.locator("#wizardModal")).to_be_visible(timeout=5000)

    # Seed required values so wizardSubmit's getVal() calls don't throw.
    page.evaluate(
        """() => {
            const setVal = (id, v) => { const el = document.getElementById(id); if (el) el.value = v; };
            setVal('wiz-spool-qty', '1');
            setVal('wiz-spool-used', '0');
            setVal('wiz-spool-empty_weight', '');
            setVal('wiz-spool-initial_weight', '');
            setVal('wiz-spool-location', '');
            setVal('wiz-spool-comment', '');
            setVal('wiz-spool-price', '');
            // Fall through to filament create mode.
            wizardState.mode = 'create';
            setVal('wiz-fil-color_name', 'Test');
            setVal('wiz-fil-material', 'PLA');
            setVal('wiz-fil-weight', '1000');
            setVal('wiz-fil-empty_weight', '');
            setVal('wiz-fil-diameter', '1.75');
            setVal('wiz-fil-density', '1.24');
            setVal('wiz-fil-settings_extruder_temp', '');
            setVal('wiz-fil-settings_bed_temp', '');
        }"""
    )

    # Fire submit — should hit our mocked endpoint and run my chip render.
    page.evaluate("window.wizardSubmit()")
    page.wait_for_function("() => document.querySelectorAll('#wiz-status-msg .fcc-wiz-queue-label').length === 2", timeout=5000)

    chips = page.locator("#wiz-status-msg .fcc-wiz-queue-label")
    expect(chips).to_have_count(2)
    ids = sorted(int(c.get_attribute("data-spool-id")) for c in chips.element_handles())
    assert ids == [9991, 9992], f"expected chips for [9991, 9992], got {ids}"

    # Clear labelQueue in-place — inv_queue.js holds its own `let labelQueue`
    # reference that aliases window.labelQueue at module init. Replacing
    # window.labelQueue would orphan the inner reference, so mutate in place.
    page.evaluate("() => { window.labelQueue.length = 0; }")
    chips.first.click()
    # Give the click handler a beat to push.
    page.wait_for_function("() => Array.isArray(window.labelQueue) && window.labelQueue.length > 0", timeout=3000)
    queued = page.evaluate("() => (window.labelQueue || []).map(q => q.id)")
    assert 9991 in queued, f"chip click should enqueue the spool; got {queued}"

    # Chip should be disabled and re-styled to indicate "done".
    first = page.locator("#wiz-status-msg .fcc-wiz-queue-label").first
    expect(first).to_be_disabled()
