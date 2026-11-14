"""The Weigh Out window, end to end: it opens, takes a scanned spool and saves
its weight.

It weighs a spool of its own (Group 45, 2026-11-13): since dev's Spoolman became
a copy of prod's, dev's #1 is the dev copy of one of Derek's real spools, which
this test used to weigh at 850 g on every sweep. Now it makes a throwaway
filament and spool on dev's Spoolman (conftest's throwaway_spool, deleted at
teardown), and the page's buffer is its own (conftest.own_the_buffer, starting
empty), so the scanned spool never reaches dev's shared buffer and the
"1 Spools" count needs no clearing of dev's.
"""
import pytest
import requests
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page, expect

from conftest import own_the_buffer

pytestmark = pytest.mark.usefixtures("require_server")


@pytest.fixture(autouse=True)
def _close_page_before_unroute(page: Page):
    """Close the page FIRST: un-routed, a live page's next buffer poll within
    3 s of a change saves its buffer to dev's."""
    yield
    try:
        page.close()
    except PlaywrightError:
        pass


def test_weigh_out_modal_e2e(page: Page, throwaway_spool, require_spoolman):
    """
    E2E test verifying that the "Weigh Out" modal opens rapidly handles scanned
    spools, and submits weight successfully.
    """
    sid = throwaway_spool["id"]
    # 1. Navigate to the app and wait for scripts to load. The page's buffer
    # starts empty, so the "1 Spools" is deterministic.
    own_the_buffer(page, [])
    page.goto("http://localhost:8000")

    # 2. Wait for the DOM and initialization
    page.wait_for_selector("#buffer-zone")

    # 3. Scan this test's own spool into the buffer through the global
    # processScan, as a typed id (a 'keyboard' scan never verifies a label).
    page.evaluate("(id) => window.processScan('ID:' + id, 'keyboard')", sid)

    # Wait for the buffer to render
    buffer_card = page.locator(f".buffer-item[data-spool-id='{sid}']")
    expect(buffer_card).to_be_visible(timeout=5000)

    # 4. Open the Weigh Out Modal
    # The qr deck button WEIGH OUT
    page.locator("#btn-deck-weigh").click()

    # 5. Wait for the modal to be visible
    modal = page.locator("#weighOutModal")
    expect(modal).to_be_visible()

    # 6. Verify the count badge shows 1
    count_badge = page.locator("#weigh-out-count")
    expect(count_badge).to_contain_text("1 Spools")

    # 7. Locate the input field for this spool
    weight_input = page.locator(f".weigh-input[data-id='{sid}']")
    expect(weight_input).to_be_visible()

    # It should be focused after 500ms
    page.wait_for_timeout(600)
    expect(weight_input).to_be_focused()

    # 8. Enter a new weight and press Enter
    weight_input.fill("850")
    weight_input.press("Enter")

    # 9. The save lands: its row (⏳ while saving, ✅ once saved, disabled
    # throughout) fades out and is gone; a save that failed would give the 💾
    # back and keep the row. This step used to wait for the 💾 as "saved": the
    # save's own redraw drew the fading row again, enabled, which let a key
    # typed then save the spool a second time (Group 57 review, round 10).
    expect(page.locator(f".weigh-row[data-id='{sid}']")).to_have_count(0, timeout=5000)
    # And it landed on this spool: the list opens in Net, so 850 g are left of
    # its 1000 g.
    rec = requests.get(f"{require_spoolman}/api/v1/spool/{sid}", timeout=10).json()
    assert float(rec.get("used_weight") or 0) == pytest.approx(150.0), rec

    # 10. Close the modal cleanly.
    modal.locator(".btn-close").click()
    expect(modal).not_to_be_visible()
    # NOTE: earlier versions of this test also asserted the spool was
    # auto-removed from the buffer after weigh-out save. Current UX keeps
    # the spool in the buffer so the user can continue scanning. If the
    # auto-removal behavior comes back, add a dedicated test for it.
