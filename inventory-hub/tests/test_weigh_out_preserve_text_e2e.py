from playwright.sync_api import Page, expect


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

    # Two guaranteed-seeded spools into the buffer.
    page.evaluate("window.processScan('ID:1', 'keyboard')")
    page.evaluate("window.processScan('ID:2', 'keyboard')")
    expect(page.locator(".buffer-item[data-spool-id='1']")).to_be_visible(timeout=5000)
    expect(page.locator(".buffer-item[data-spool-id='2']")).to_be_visible(timeout=5000)

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
