import re

import requests
from playwright.sync_api import Page, expect


def test_wizard_manual_creation(page: Page, dev_spoolman_url: str):
    """
    E2E test verifying that the "Add Inventory" wizard opens, accepts inputs
    for a new manual filament and spool, and successfully submits the payload.

    Group 19 follow-up — self-cleaning. This test creates a REAL filament +
    spool on the dev Spoolman every run (it drives the actual create endpoint,
    on purpose — that's its end-to-end value). It used to leave them behind,
    which is where the 47 accumulated "Pytest-PLA" junk filaments came from. It
    now captures the created ids from the wizard's create response and deletes
    them in a `finally` (spool first — Spoolman refuses to delete a filament
    that still has spools). `finally` runs on assertion failure too, so only a
    hard process kill could leak; a leaked record is still recoverable via
    `reset_dev.py --prune`. Deletes go straight to dev Spoolman, mirroring
    test_vendor_create_end_to_end.py's cleanup pattern.
    """
    created_filament_id = None
    created_spool_ids = []
    try:
        # 1. Navigate to the app
        page.goto("http://localhost:8000")

        # 2. Click the 'ADD INVENTORY' button via its text
        page.get_by_role("button", name=re.compile("ADD INVENTORY")).click()

        # 3. Wait for the wizard modal to be clearly visible
        modal = page.locator("#wizardModal")
        expect(modal).to_be_visible()

        # 4. We expect the 'Manual' tab to be active by default, but let's click it to be safe.
        page.locator("#btn-type-manual").click()

        # 5. Fill out Filament details (Step 2)
        # Group 10.1: Color panel defaults collapsed in create mode — expand before fill.
        page.evaluate(
            "() => { const el = document.getElementById('wiz-fil-color-panel');"
            " if (el && !el.classList.contains('show'))"
            " bootstrap.Collapse.getOrCreateInstance(el, {toggle:false}).show(); }"
        )
        page.fill("#wiz-fil-material", "Pytest-PLA")
        page.fill("#wiz-fil-color_name", "E2E Ruby Red")

        # Locate the first wizard color hex input
        page.locator("#wiz-fil-color_hex_0").fill("#FF0044")

        # Group 19.4: Physical Specs (diameter/density/net/tare) now lives in a
        # panel that wizardApplyCollapseDefaults('create') collapses on open —
        # expand it before filling or the inputs are "not visible".
        page.evaluate(
            "() => { const el = document.getElementById('wiz-fil-physical-panel');"
            " if (el && !el.classList.contains('show'))"
            " bootstrap.Collapse.getOrCreateInstance(el, {toggle:false}).show(); }"
        )
        page.fill("#wiz-fil-density", "1.24")
        page.fill("#wiz-fil-diameter", "1.75")

        # Fill the Net Weight
        page.fill("#wiz-fil-weight", "1000")

        # Fill empty spool weight
        page.fill("#wiz-fil-empty_weight", "250")

        # 6. Fill out Spool details (Step 3)
        # 7. Submit the form — capture the create response so we can clean up.
        submit_btn = page.locator("#btn-wiz-submit")
        expect(submit_btn).not_to_be_disabled()
        with page.expect_response(
            lambda r: "/api/create_inventory_wizard" in r.url
            and r.request.method == "POST"
        ) as resp_info:
            submit_btn.click()

        # 8. Assert Success
        # The wizard-status-msg updates dynamically
        status_msg = page.locator("#wiz-status-msg")
        expect(status_msg).to_contain_text("Success!", timeout=5000)

        # Record the created ids for teardown (do this before closing the modal).
        try:
            body = resp_info.value.json()
            created_filament_id = body.get("filament_id")
            created_spool_ids = body.get("created_spools") or []
        except Exception:
            pass

        # 9. Ensure the modal can close
        modal.get_by_text("Cancel", exact=True).click()
        expect(modal).not_to_be_visible()
    finally:
        # Clean up the records this test created so dev doesn't accumulate junk.
        # Spools first (FK), then the filament. Best-effort / fail-quiet.
        for sid in created_spool_ids:
            try:
                requests.delete(f"{dev_spoolman_url}/api/v1/spool/{sid}", timeout=10)
            except requests.RequestException:
                pass
        if created_filament_id is not None:
            try:
                requests.delete(
                    f"{dev_spoolman_url}/api/v1/filament/{created_filament_id}",
                    timeout=10,
                )
            except requests.RequestException:
                pass
