"""Bulk Weigh-Out keeps un-submitted text through an in-session redraw (31.3)
and drops it on a close and reopen.

These weigh spools of their own (Group 45, 2026-11-13): since dev's Spoolman
became a copy of prod's, dev's #1 and #2 are dev copies of Derek's real spools,
and one test saved 850 g to #1 on every sweep. Now each test makes throwaway
spools on dev's Spoolman (conftest's throwaway_spool_with_extras, deleted at
teardown), and the page's buffer is its own (conftest.own_the_buffer, starting
empty), so the scanned spools never reach dev's shared buffer.
"""
import time

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


def _wait_for_own_buffer(page: Page, held: dict, want_ids, timeout: float = 15.0):
    """Block until the page's buffer STORE (own_the_buffer's) holds every id in
    `want_ids`.

    Group 38.3 — the seeding step is the divergence window. `processScan`
    (inv_cmd.js) does NOT return its fetch, so two back-to-back
    `page.evaluate("window.processScan(...)")` calls launch two INDEPENDENT
    chains, each ending in `renderBuffer()` → `persistBuffer()`, which POSTs the
    WHOLE `state.heldSpools` list with no sequencing. Their POSTs can therefore
    land out of order, leaving the store holding only the first spool while the
    client shows both.

    That matters because `loadBuffer` runs every 2 s and its ONLY defence is a
    hard-coded wall-clock grace — `if (localAge < 3000)`. Once the test's step
    sequence outruns 3 s (trivial under sweep load: a `/api/spool_details`
    prefetch, a deck click, two fills and a save round-trip), the poll wins and
    replaces the client list with the store's — silently dropping row 2 and
    taking its un-submitted text with it. Same root cause as the archived Group
    26.8 `test_doassign_buffer_safety` flake.

    Waiting for the two to AGREE removes the precondition entirely: from here on
    `loadBuffer` sees `currentStr === serverStr` and is a no-op, so the poll can
    no longer overwrite anything regardless of how long the rest of the test
    takes. That is strictly better than widening a timeout, which would not have
    helped — the list was already gone. (The store was dev's server buffer until
    Group 45: the page owns it now, and the same race runs against its own.)
    """
    want = {str(i) for i in want_ids}
    deadline = time.time() + timeout
    last = set()
    while time.time() < deadline:
        last = {str(s.get("id")) for s in (held["buffer"] or []) if isinstance(s, dict)}
        if want <= last:
            return last
        page.wait_for_timeout(250)
    raise AssertionError(
        f"the page's buffer store never converged on {sorted(want)} (last seen: "
        f"{sorted(last)}). The scans' persistBuffer POSTs are unsequenced, so this "
        f"is the divergence the 2s loadBuffer poll would later 'fix' by discarding "
        f"the client's rows."
    )


def test_weigh_out_preserves_sibling_text_on_save_redraw(page: Page, throwaway_spool_with_extras):
    """31.3 — Saving one row in the Bulk Weigh-Out modal must NOT wipe the
    un-submitted text the user has already keyed into the OTHER rows.

    Before the fix, saving a row rebuilt the whole list via innerHTML, blowing
    away every sibling row's input. This drives two spools into the buffer,
    types a value into row #2 WITHOUT saving it, saves row #1 (which triggers
    the list redraw), and asserts row #2 still shows what was typed.
    """
    first = throwaway_spool_with_extras({})["id"]
    second = throwaway_spool_with_extras({})["id"]
    held = own_the_buffer(page, [])
    page.goto("http://localhost:8000")
    page.wait_for_selector("#buffer-zone")

    # Two spools of this test's own into the buffer.
    page.evaluate("(id) => window.processScan('ID:' + id, 'keyboard')", first)
    page.evaluate("(id) => window.processScan('ID:' + id, 'keyboard')", second)
    expect(page.locator(f".buffer-item[data-spool-id='{first}']")).to_be_visible(timeout=5000)
    expect(page.locator(f".buffer-item[data-spool-id='{second}']")).to_be_visible(timeout=5000)
    # Group 38.3 — the CLIENT showing both rows is not enough. Wait for the
    # store to agree, or the 2s loadBuffer poll will later replace the client
    # list with the store's and take row 2's un-submitted text with it.
    _wait_for_own_buffer(page, held, (first, second))

    # Open the Weigh-Out modal.
    page.locator("#btn-deck-weigh").click()
    modal = page.locator("#weighOutModal")
    expect(modal).to_be_visible()
    expect(page.locator("#weigh-out-count")).to_contain_text("2 Spools")

    row1_input = page.locator(f".weigh-input[data-id='{first}']")
    row2_input = page.locator(f".weigh-input[data-id='{second}']")
    expect(row1_input).to_be_visible()
    expect(row2_input).to_be_visible()

    # Key an un-submitted value into row #2 first.
    row2_input.fill("500")

    # Now save row #1 (Enter submits its row) — this is what triggers the redraw.
    row1_input.fill("850")
    row1_input.press("Enter")

    # Row #1 fades out and is removed from the list once the save succeeds.
    expect(page.locator(f".weigh-row[data-id='{first}']")).to_have_count(0, timeout=6000)

    # The un-submitted row #2 value must survive the redraw.
    expect(page.locator(f".weigh-input[data-id='{second}']")).to_have_value("500")

    modal.locator(".btn-close").click()
    expect(modal).not_to_be_visible()


def test_weigh_out_discards_unsaved_text_on_close_reopen(page: Page, throwaway_spool_with_extras,
                                                         require_spoolman):
    """31.3 review fix: preserve-text is for the in-SESSION redraw only. An
    un-submitted value must NOT survive a close→reopen — a reopened Weigh-Out is
    a fresh session, not a resurrection of the abandoned one (the value would
    otherwise read as a fresh scale reading and get blind-saved)."""
    sid = throwaway_spool_with_extras({})["id"]
    held = own_the_buffer(page, [])
    page.goto("http://localhost:8000")
    page.wait_for_selector("#buffer-zone")

    page.evaluate("(id) => window.processScan('ID:' + id, 'keyboard')", sid)
    expect(page.locator(f".buffer-item[data-spool-id='{sid}']")).to_be_visible(timeout=5000)
    # Group 38.3 — same convergence wait as the sibling above.
    _wait_for_own_buffer(page, held, (sid,))

    page.locator("#btn-deck-weigh").click()
    modal = page.locator("#weighOutModal")
    expect(modal).to_be_visible()

    row1_input = page.locator(f".weigh-input[data-id='{sid}']")
    expect(row1_input).to_be_visible()
    row1_input.fill("500")  # typed but NOT saved

    # Abandon the session.
    modal.locator(".btn-close").click()
    expect(modal).not_to_be_visible()

    # Reopen — the spool is still held, so its row reappears...
    page.locator("#btn-deck-weigh").click()
    expect(modal).to_be_visible()
    reopened = page.locator(f".weigh-input[data-id='{sid}']")
    expect(reopened).to_be_visible()
    # ...but it must be BLANK, not pre-filled with the abandoned "500".
    expect(reopened).to_have_value("")

    modal.locator(".btn-close").click()
    expect(modal).not_to_be_visible()
    # And nothing was saved: the abandoned "500" never reached the spool.
    rec = requests.get(f"{require_spoolman}/api/v1/spool/{sid}", timeout=10).json()
    assert float(rec.get("used_weight") or 0) == 0.0, rec
