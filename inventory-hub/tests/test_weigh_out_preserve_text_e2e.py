import time

import requests
from playwright.sync_api import Page, expect


def _wait_for_server_buffer(api_base_url: str, want_ids, timeout: float = 15.0):
    """Block until the SERVER-side buffer holds every id in `want_ids`.

    Group 38.3 — the seeding step is the divergence window. `processScan`
    (inv_cmd.js) does NOT return its fetch, so two back-to-back
    `page.evaluate("window.processScan(...)")` calls launch two INDEPENDENT
    chains, each ending in `renderBuffer()` → `persistBuffer()`, which POSTs the
    WHOLE `state.heldSpools` list with no sequencing. Their POSTs can therefore
    land out of order, leaving the server holding only `[1]` while the client
    shows `[1, 2]`.

    That matters because `loadBuffer` runs every 2 s and its ONLY defence is a
    hard-coded wall-clock grace — `if (localAge < 3000)`. Once the test's step
    sequence outruns 3 s (trivial under sweep load: a `/api/spool_details`
    prefetch, a deck click, two fills and a save round-trip), the poll wins and
    replaces the client list with the server's — silently dropping row 2 and
    taking its un-submitted text with it. Same root cause as the archived Group
    26.8 `test_doassign_buffer_safety` flake.

    Waiting for the two to AGREE removes the precondition entirely: from here on
    `loadBuffer` sees `currentStr === serverStr` and is a no-op, so the poll can
    no longer overwrite anything regardless of how long the rest of the test
    takes. That is strictly better than widening a timeout, which would not have
    helped — the list was already gone.
    """
    want = {str(i) for i in want_ids}
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        try:
            body = requests.get(f"{api_base_url}/api/state/buffer", timeout=5).json()
            last = {str(s.get("id")) for s in (body or []) if isinstance(s, dict)}
            if want <= last:
                return last
        except requests.RequestException:
            pass
        time.sleep(0.25)
    raise AssertionError(
        f"server buffer never converged on {sorted(want)} (last seen: "
        f"{sorted(last) if last is not None else 'unreadable'}). The scans' "
        f"persistBuffer POSTs are unsequenced, so this is the divergence the "
        f"2s loadBuffer poll would later 'fix' by discarding the client's rows."
    )


def test_weigh_out_preserves_sibling_text_on_save_redraw(page: Page, clean_buffer):
    """31.3 — Saving one row in the Bulk Weigh-Out modal must NOT wipe the
    un-submitted text the user has already keyed into the OTHER rows.

    Before the fix, saving a row rebuilt the whole list via innerHTML, blowing
    away every sibling row's input. This drives two spools into the buffer,
    types a value into row #2 WITHOUT saving it, saves row #1 (which triggers
    the list redraw), and asserts row #2 still shows what was typed.
    """
    page.goto("http://localhost:8000")
    page.wait_for_selector("#buffer-zone")

    # Two spools into the buffer. (These ids are assumed to exist in dev — the
    # old comment called them "guaranteed-seeded", but nothing seeds them;
    # `clean_buffer` only clears the buffer.)
    page.evaluate("window.processScan('ID:1', 'keyboard')")
    page.evaluate("window.processScan('ID:2', 'keyboard')")
    expect(page.locator(".buffer-item[data-spool-id='1']")).to_be_visible(timeout=5000)
    expect(page.locator(".buffer-item[data-spool-id='2']")).to_be_visible(timeout=5000)
    # Group 38.3 — the CLIENT showing both rows is not enough. Wait for the
    # server to agree, or the 2s loadBuffer poll will later replace the client
    # list with the server's and take row 2's un-submitted text with it.
    _wait_for_server_buffer(clean_buffer, ("1", "2"))

    # Open the Weigh-Out modal.
    page.locator("#btn-deck-weigh").click()
    modal = page.locator("#weighOutModal")
    expect(modal).to_be_visible()
    expect(page.locator("#weigh-out-count")).to_contain_text("2 Spools")

    row1_input = page.locator(".weigh-input[data-id='1']")
    row2_input = page.locator(".weigh-input[data-id='2']")
    expect(row1_input).to_be_visible()
    expect(row2_input).to_be_visible()

    # Key an un-submitted value into row #2 first.
    row2_input.fill("500")

    # Now save row #1 (Enter submits its row) — this is what triggers the redraw.
    row1_input.fill("850")
    row1_input.press("Enter")

    # Row #1 fades out and is removed from the list once the save succeeds.
    expect(page.locator(".weigh-row[data-id='1']")).to_have_count(0, timeout=6000)

    # The un-submitted row #2 value must survive the redraw.
    expect(page.locator(".weigh-input[data-id='2']")).to_have_value("500")

    modal.locator(".btn-close").click()
    expect(modal).not_to_be_visible()


def test_weigh_out_discards_unsaved_text_on_close_reopen(page: Page, clean_buffer):
    """31.3 review fix: preserve-text is for the in-SESSION redraw only. An
    un-submitted value must NOT survive a close→reopen — a reopened Weigh-Out is
    a fresh session, not a resurrection of the abandoned one (the value would
    otherwise read as a fresh scale reading and get blind-saved)."""
    page.goto("http://localhost:8000")
    page.wait_for_selector("#buffer-zone")

    page.evaluate("window.processScan('ID:1', 'keyboard')")
    expect(page.locator(".buffer-item[data-spool-id='1']")).to_be_visible(timeout=5000)
    # Group 38.3 — same convergence wait as the sibling above.
    _wait_for_server_buffer(clean_buffer, ("1",))

    page.locator("#btn-deck-weigh").click()
    modal = page.locator("#weighOutModal")
    expect(modal).to_be_visible()

    row1_input = page.locator(".weigh-input[data-id='1']")
    expect(row1_input).to_be_visible()
    row1_input.fill("500")  # typed but NOT saved

    # Abandon the session.
    modal.locator(".btn-close").click()
    expect(modal).not_to_be_visible()

    # Reopen — the spool is still held, so its row reappears...
    page.locator("#btn-deck-weigh").click()
    expect(modal).to_be_visible()
    reopened = page.locator(".weigh-input[data-id='1']")
    expect(reopened).to_be_visible()
    # ...but it must be BLANK, not pre-filled with the abandoned "500".
    expect(reopened).to_have_value("")

    modal.locator(".btn-close").click()
    expect(modal).not_to_be_visible()
