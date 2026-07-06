"""
Visual baselines for Phase 3 — Quick-Swap grid and shortcuts overlay.
"""
from __future__ import annotations

import pytest
import requests
from playwright.sync_api import Page, expect

TEST_BOX = "PM-DB-1"
TEST_TOOLHEAD = "XL-1"


@pytest.fixture
def bound_slot(api_base_url):
    snap = requests.get(f"{api_base_url}/api/dryer_box/{TEST_BOX}/bindings", timeout=5).json()
    original = snap.get("slot_targets", {})
    requests.put(
        f"{api_base_url}/api/dryer_box/{TEST_BOX}/bindings",
        json={"slot_targets": {"1": TEST_TOOLHEAD}},
        timeout=5,
    )
    yield
    requests.put(
        f"{api_base_url}/api/dryer_box/{TEST_BOX}/bindings",
        json={"slot_targets": original},
        timeout=5,
    )


@pytest.mark.usefixtures("require_server", "bound_slot", "clean_buffer")
def test_visual_quickswap_grid(page: Page, open_manage_modal, snapshot):
    # A populated buffer turns the empty-slot row into a green "Deposit from
    # buffer" affordance — visible content that changes the grid's height
    # (~22px taller per slot row). The baseline is captured with an empty
    # buffer, so the test pins clean_buffer to keep render reproducible in
    # the sweep regardless of prior tests' buffer state. Group 14.4.
    open_manage_modal(TEST_TOOLHEAD)
    expect(page.locator(".fcc-qs-slot").first).to_be_visible()
    snapshot(page.locator("#manage-quickswap-section"), "quickswap-grid-default")


@pytest.mark.usefixtures("require_server", "bound_slot", "clean_buffer")
def test_visual_quickswap_kb_active(page: Page, open_manage_modal, snapshot):
    open_manage_modal(TEST_TOOLHEAD)
    expect(page.locator(".fcc-qs-slot").first).to_be_visible()
    page.keyboard.press("q")
    page.wait_for_timeout(200)
    snapshot(page.locator("#manage-quickswap-section"), "quickswap-grid-kb-active")


# The confirm overlay has TWO layouts, and which one renders depends on the
# live active-print probe (`window.fetchPrinterStateForToolhead`), NOT on any
# markup change:
#   - probe → null  (printer idle/offline/unknown): the plain confirm card.
#   - probe → active state: the card ALSO grows an "⚠️ … is PRINTING" warning
#     banner + a scan-to-confirm QR pair (the 2026-04-23 active-print safety
#     feature), ~218px taller.
# Because `bound_loaded_slot` yields whatever loaded slot exists — sometimes a
# toolhead on a live printer, sometimes not — a single baseline that lets the
# real probe run is inherently nondeterministic (it flip-flops 284px⇄502px on
# the same code). So each variant is pinned in its own test with the probe
# STUBBED to a fixed answer, making both captures deterministic. (Group 33.4.)
def _open_confirm_overlay(page: Page, open_manage_modal, bound_loaded_slot, probe_stub_js: str):
    box, slot, toolhead = (
        bound_loaded_slot["box"], bound_loaded_slot["slot"], bound_loaded_slot["toolhead"]
    )
    open_manage_modal(toolhead)
    # Pin the active-print probe BEFORE the slot click (showConfirmOverlay reads
    # window.fetchPrinterStateForToolhead at click time) so the overlay renders
    # a deterministic variant regardless of what the real fleet is doing.
    page.evaluate(f"window.fetchPrinterStateForToolhead = {probe_stub_js};")
    page.locator(f".fcc-qs-slot[data-box='{box}'][data-slot='{slot}']").first.click()
    expect(page.locator("#fcc-quickswap-confirm-overlay")).to_be_visible(timeout=8000)
    # Snapshot the bounded confirm CARD, not the full-viewport backdrop: the
    # backdrop is semi-transparent, so capturing it bakes the live dashboard
    # (activity-log timestamps, backlog count) into the baseline and guarantees
    # a >1% drift on every run. The card (`.border-info`, min-width 420px) is
    # the only bordered panel inside the overlay and pins the layout/styling.
    card = page.locator("#fcc-quickswap-confirm-overlay .border-info").first
    expect(card).to_be_visible()
    return card


@pytest.mark.usefixtures("require_server")
def test_visual_quickswap_confirm_overlay(page: Page, open_manage_modal, snapshot, bound_loaded_slot):
    # Base variant: probe fails open (null) → plain confirm card, no banner/QRs.
    # Matches the long-standing baseline captured when dev printers were idle.
    card = _open_confirm_overlay(
        page, open_manage_modal, bound_loaded_slot,
        "() => Promise.resolve(null)",
    )
    snapshot(card, "quickswap-confirm-overlay")


@pytest.mark.usefixtures("require_server")
def test_visual_quickswap_confirm_overlay_active_print(page: Page, open_manage_modal, snapshot, bound_loaded_slot):
    # Active-print variant: probe reports a printing printer → the card grows
    # the "⚠️ … is PRINTING" warning banner + scan-to-confirm QR pair. Pinned
    # separately so a regression in the SAFETY banner (not just the base card)
    # is caught, and so this layout is captured deterministically.
    card = _open_confirm_overlay(
        page, open_manage_modal, bound_loaded_slot,
        "() => Promise.resolve({ state: 'PRINTING', printer_name: 'DEV-PRINTER' })",
    )
    # The QR pair renders async into the banner; wait for both codes to paint so
    # the card reaches its final height before capture (attachConfirmQRs draws a
    # canvas/img per code, giving each QR container its 70px size).
    page.wait_for_function(
        "() => { const c = document.querySelector('#fcc-quickswap-confirm-overlay .border-info');"
        " return c && c.querySelectorAll('canvas, img, svg').length >= 2; }",
        timeout=8000,
    )
    # MASK the QR row out of the pixel diff: each QR encodes a per-render session
    # id (fcc-cqr-<seq>-<Date.now>), so its pixels change every run and would
    # otherwise drift the baseline — the exact flake class this group removes.
    # Masking blanks only the QR row (Playwright paints it a solid color); the
    # warning banner, spool text, and buttons stay pixel-pinned so a real layout
    # regression is still caught. The wait above still guarantees the row is at
    # full height so the mask covers the right area. (Group 33.4 review fix.)
    snapshot(
        card, "quickswap-confirm-overlay-active",
        mask=[page.locator("#fcc-quickswap-confirm-overlay .fcc-confirm-qr-row")],
    )


@pytest.mark.usefixtures("require_server")
def test_visual_shortcuts_overlay(page: Page, base_url: str, snapshot):
    page.goto(base_url)
    page.wait_for_selector("#btn-shortcuts-help", timeout=10000)
    page.locator("#btn-shortcuts-help").click()
    expect(page.locator("#fcc-shortcuts-overlay")).to_be_visible()
    page.wait_for_timeout(300)
    snapshot(page.locator("#fcc-shortcuts-overlay"), "shortcuts-overlay-default")
