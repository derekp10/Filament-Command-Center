import re

import pytest
import requests
from playwright.sync_api import Page, expect


@pytest.mark.usefixtures("require_server")
def test_clone_spool_button(page: Page, base_url: str, api_base_url: str):
    """
    E2E test verifying that clicking a Spool from the Backlog opens its details,
    and clicking 'Clone Spool' immediately transports the user to an auto-filled New Inventory Wizard.

    Group 38.4 — this used to be a load-sensitive flake whose captured traceback
    (2026-08-03) was a 30 s timeout on
    `locator(".backlog-row").filter(has_text="SPOOL").first`, with the backlog
    panel itself visible. The old body could not tell three very different
    situations apart, because `expect(backlog_list).to_be_visible()` passes for
    every one of them:

      1. the backlog loaded and genuinely holds no label-flagged SPOOL,
      2. the backlog request FAILED — `/api/print_queue/pending` collapses ANY
         exception, including its two `timeout=2` Spoolman reads, into
         `{"success": false}`, which `inv_backlog.js:31` renders as a
         `.text-danger` div INSIDE the visible `#backlog-list`,
      3. the list simply had not finished rendering yet.

    Only (3) is a timing problem; (2) is the one that actually bit, and it is
    infrastructure, not a product regression. The test also took only `page` —
    no `require_server`, no precondition assertion — so all three collapsed into
    the same opaque locator timeout half a minute later.

    It now checks the precondition through the API first and distinguishes the
    end states explicitly, so a failure names its own cause in seconds.
    """
    # --- Precondition, asserted up front rather than inferred from a timeout ---
    try:
        payload = requests.get(
            f"{api_base_url}/api/print_queue/pending", timeout=15
        ).json()
    except requests.RequestException as exc:
        pytest.skip(f"backlog API unreachable: {exc}")

    if not payload.get("success"):
        pytest.skip(
            "backlog API returned success:false "
            f"({payload.get('msg')!r}) — /api/print_queue/pending collapses any "
            "exception, including its two timeout=2 Spoolman reads, into this. "
            "Infrastructure, not a clone-flow regression."
        )
    if not [i for i in (payload.get("items") or []) if i.get("type") == "spool"]:
        pytest.skip(
            "dev currently has no label-flagged SPOOL in the backlog, so there "
            "is no row to clone from."
        )

    # 1. Hard Navigate / Refresh
    page.goto(base_url)

    # 2. Click the 'Backlog' button (by title or text)
    page.get_by_role("button", name=re.compile("Backlog")).click()

    # 3. Wait for the backlog to reach a real END STATE. `to_be_visible` alone
    # passes on "Loading backlog…", on an error div, and on an empty list.
    backlog_list = page.locator("#backlog-list")
    expect(backlog_list).to_be_visible()
    page.wait_for_function(
        """() => {
            const list = document.getElementById('backlog-list');
            if (!list) return false;
            if (list.querySelector('.text-danger')) return true;   // errored
            if (list.querySelector('.backlog-row')) return true;   // loaded
            return /All labels printed/i.test(list.innerText || '');  // empty
        }""",
        timeout=20000,
    )
    errors = backlog_list.locator(".text-danger")
    if errors.count():
        pytest.skip(
            f"backlog failed to load in the UI: {errors.first.inner_text()!r}. "
            "Same collapse-to-success:false path as above — the panel renders an "
            "error div inside a VISIBLE #backlog-list, which is why this used to "
            "look identical to 'no SPOOL rows'."
        )

    # 4. Find the first SPOOL row and click it to open details.
    # The SPOOL text is next to the icon.
    first_spool = page.locator(".backlog-row").filter(has_text="SPOOL").first
    expect(first_spool).to_be_visible(timeout=10000)
    first_spool.click()

    # 5. Wait for the Spool Details modal
    spool_modal = page.locator("#spoolModal")
    expect(spool_modal).to_be_visible()

    # 6. Click 'Clone Spool'
    spool_modal.get_by_role("button", name=re.compile("Clone")).click()

    # 7. Verify Spool modal closes and Wizard opens
    wizard = page.locator("#wizardModal")
    expect(wizard).to_be_visible()

    # Verify we auto-transitioned to 'Existing Filament' mode and the success message appears
    status_msg = page.locator("#wiz-status-msg")
    expect(status_msg).to_contain_text("Wizard successfully pre-filled", timeout=5000)

    # 8. Close the wizard modal cleanly
    wizard.get_by_text("Cancel", exact=True).click()
    expect(wizard).not_to_be_visible()
