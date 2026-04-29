"""Playwright tests for the buried delete-action UI on the spool and
filament details modals.

These tests cover the UX flow only — open the gear-icon dropdown, render
the inline overlay, walk through the two-step confirmation, exercise
cancel / wrong-input / Escape paths. They do NOT actually trigger the
DELETE endpoint (no destruction of dev data).

The actual server-side delete is covered by `test_delete_helpers.py`
(unit tests with mocked HTTP) and a manual QA pass once the user is
comfortable that the UX is right.
"""
from __future__ import annotations

import pytest
import requests
from playwright.sync_api import Page, expect


def _open_first_spool_modal(page: Page) -> None:
    page.goto("http://localhost:8000")
    page.locator('nav button:has-text("SEARCH")').click()
    page.wait_for_selector("#offcanvasSearch", timeout=5000)
    page.locator('#global-search-query').fill("a")
    page.wait_for_selector(".fcc-card-action-btn[title='View Details']", timeout=10000)
    page.click(".fcc-card-action-btn[title='View Details']")
    expect(page.locator("#spoolModal")).to_be_visible()


def _pick_filament_with_spools(api_base_url: str):
    """Find a filament that has at least one child spool (for cascade prompt
    coverage)."""
    try:
        r = requests.get(f"{api_base_url}/api/filaments", timeout=5)
    except requests.exceptions.RequestException:
        pytest.skip("filaments API unreachable")
    if not r.ok:
        pytest.skip(f"/api/filaments returned {r.status_code}")
    payload = r.json() or {}
    filaments = payload.get("filaments") or payload if isinstance(payload, list) else payload.get("filaments", [])
    if not filaments:
        pytest.skip("no filaments to test against")
    for f in filaments:
        fid = f.get("id")
        if not fid:
            continue
        c = requests.get(f"{api_base_url}/api/spools_by_filament?id={fid}&allow_archived=true", timeout=5)
        if not c.ok:
            continue
        spools = c.json() or []
        if spools:
            return fid, len(spools)
    pytest.skip("no filament with child spools available")


# ---------------------------------------------------------------------------
# Spool delete flow
# ---------------------------------------------------------------------------

def test_spool_gear_dropdown_exposes_delete(page: Page):
    _open_first_spool_modal(page)
    # Gear button + dropdown item are present and the item is text-danger styled.
    gear = page.locator("#btn-spool-gear")
    expect(gear).to_be_visible()
    gear.click()
    delete_item = page.locator("#btn-spool-delete")
    expect(delete_item).to_be_visible()
    # Confirm it's styled as a destructive action (text-danger class).
    classes = delete_item.get_attribute("class") or ""
    assert "text-danger" in classes, f"Expected text-danger styling, got: {classes}"


def test_spool_delete_step1_renders_warning(page: Page):
    _open_first_spool_modal(page)
    page.locator("#btn-spool-gear").click()
    page.locator("#btn-spool-delete").click()
    overlay = page.locator("#fcc-spool-delete-overlay")
    expect(overlay).to_be_visible()
    # Step 1 wording.
    expect(overlay).to_contain_text("Delete this spool")
    expect(overlay).to_contain_text("cannot be undone")
    # No type-to-confirm input on Step 1.
    assert overlay.locator("input").count() == 0
    # Cancel returns to the modal cleanly.
    overlay.locator("[data-fcc-delete-cancel]").click()
    expect(overlay).not_to_be_visible()
    expect(page.locator("#spoolModal")).to_be_visible()


def test_spool_delete_step2_requires_id_match(page: Page):
    _open_first_spool_modal(page)
    sid = (page.locator("#detail-id").inner_text() or "").strip()
    assert sid, "spool details modal didn't render an ID"
    page.locator("#btn-spool-gear").click()
    page.locator("#btn-spool-delete").click()
    # Walk to Step 2.
    page.locator("#fcc-spool-delete-overlay [data-fcc-delete-confirm]").click()
    overlay = page.locator("#fcc-spool-delete-overlay")
    expect(overlay).to_contain_text("Final confirmation")
    expect(overlay).to_contain_text(sid)
    # Type something WRONG and try to confirm — should show inline error.
    inp = overlay.locator("input").first
    inp.fill("not-the-id")
    overlay.locator("[data-fcc-delete-confirm]").click()
    err = overlay.locator(f"#fcc-spool-delete-overlay-err")
    expect(err).to_contain_text("Doesn't match")
    # Cancel out — overlay closes, modal stays.
    overlay.locator("[data-fcc-delete-cancel]").click()
    expect(overlay).not_to_be_visible()
    expect(page.locator("#spoolModal")).to_be_visible()


def test_spool_delete_escape_closes_overlay(page: Page):
    _open_first_spool_modal(page)
    page.locator("#btn-spool-gear").click()
    page.locator("#btn-spool-delete").click()
    overlay = page.locator("#fcc-spool-delete-overlay")
    expect(overlay).to_be_visible()
    # NB: page.keyboard.press("Escape") AND locator.press("Escape") both
    # silently fail to reach DOM keydown handlers in this Bootstrap-modal +
    # Playwright + Chromium combo (verified via capture-phase probe — count
    # stays at 0). Synthetic dispatchEvent works correctly and exercises
    # the same code path the real Escape would hit.
    page.locator("#fcc-spool-delete-overlay [data-fcc-delete-cancel]").focus()
    page.evaluate("""
        document.activeElement.dispatchEvent(
            new KeyboardEvent('keydown', {key: 'Escape', bubbles: true, cancelable: true})
        );
    """)
    expect(overlay).not_to_be_visible()
    # Modal must still be open — Escape on the delete overlay only dismisses
    # the overlay, not the underlying modal.
    expect(page.locator("#spoolModal")).to_be_visible()


def test_spool_delete_overlay_clears_when_modal_closes(page: Page):
    _open_first_spool_modal(page)
    page.locator("#btn-spool-gear").click()
    page.locator("#btn-spool-delete").click()
    overlay = page.locator("#fcc-spool-delete-overlay")
    expect(overlay).to_be_visible()
    # Close the modal mid-flow.
    page.evaluate("modals.spoolModal && modals.spoolModal.hide()")
    expect(page.locator("#spoolModal")).to_be_hidden()
    # Re-open — overlay should NOT be re-rendered with stale state.
    _open_first_spool_modal(page)
    expect(page.locator("#fcc-spool-delete-overlay")).not_to_be_visible()


# ---------------------------------------------------------------------------
# Filament delete flow (cascade messaging)
# ---------------------------------------------------------------------------

def test_filament_delete_shows_cascade_count(page: Page, api_base_url: str):
    fid, child_count = _pick_filament_with_spools(api_base_url)
    page.goto("http://localhost:8000")
    page.wait_for_selector("#buffer-zone", timeout=10000)
    # `openFilamentDetails` is a top-level const in inv_details.js (not on
    # window), so call it directly via a lexical reference.
    page.evaluate(f"openFilamentDetails({fid})")
    expect(page.locator("#filamentModal")).to_be_visible(timeout=10000)
    # Wait for the spool count to populate from /api/spools_by_filament.
    page.wait_for_function(
        "() => { const el = document.getElementById('fil-spool-count');"
        " return el && /\\d+/.test(el.innerText); }",
        timeout=10000,
    )
    # Wait for the spool count fetch to populate. The handler does its own
    # /api/spools_by_filament call, but that's after the click — we just
    # need the gear button mounted.
    page.locator("#btn-fil-gear").click()
    page.locator("#btn-fil-delete").click()
    overlay = page.locator("#fcc-filament-delete-overlay")
    expect(overlay).to_be_visible()
    # Step 1 should mention the cascade count and the filament ID.
    expect(overlay).to_contain_text(f"#{fid}")
    expect(overlay).to_contain_text(str(child_count))
    expect(overlay).to_contain_text("spool")  # singular or plural
    # Continue to Step 2 — should require typing CONFIRM (cascade case).
    overlay.locator("[data-fcc-delete-confirm]").click()
    expect(overlay).to_contain_text("Final confirmation")
    expect(overlay).to_contain_text("CONFIRM")
    inp = overlay.locator("input").first
    expect(inp).to_be_visible()
    # Cancel — no destruction.
    overlay.locator("[data-fcc-delete-cancel]").click()
    expect(overlay).not_to_be_visible()
    expect(page.locator("#filamentModal")).to_be_visible()
