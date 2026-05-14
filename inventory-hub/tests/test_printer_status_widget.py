"""
Group 9.3 — Printer Status at-a-glance widget.

Renders one row per printer with bound toolheads, each showing a stylized
schematic (color-tinted block + horizontal weight bar). Auto-refreshes on
`inventory:sync-pulse`. Click on a toolhead block opens the Location
Manager focused on that toolhead.
"""
from __future__ import annotations

import pytest
import requests
from playwright.sync_api import Page, expect


TEST_BOX = "PM-DB-1"
TEST_TOOLHEAD = "XL-1"


@pytest.fixture
def bound_xl1(api_base_url):
    """Ensure XL-1 has at least one bound source slot so the widget shows
    a row for the XL printer. Restore the original bindings on teardown."""
    snap = requests.get(
        f"{api_base_url}/api/dryer_box/{TEST_BOX}/bindings", timeout=5
    ).json()
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


@pytest.mark.usefixtures("require_server", "bound_xl1")
def test_widget_renders_for_bound_printer(page: Page, base_url):
    page.goto(base_url)
    page.wait_for_selector("#buffer-zone", timeout=10000)
    # Allow the initial aggregate fetch to land.
    page.wait_for_function(
        "() => { const w = document.getElementById('printer-status-widget'); "
        "return w && w.style.display !== 'none' && w.querySelector('.fcc-ps-row'); }",
        timeout=8000,
    )
    expect(page.locator("#printer-status-widget")).to_be_visible()
    # Other printers in the dev printer_map may also surface here; at
    # minimum the XL row must be present.
    assert page.locator(".fcc-ps-row").count() >= 1
    # Toolhead block should be present and clickable.
    th_block = page.locator(f".fcc-ps-th[data-toolhead='{TEST_TOOLHEAD}']").first
    expect(th_block).to_be_visible()


@pytest.mark.usefixtures("require_server", "bound_xl1")
def test_widget_toolhead_click_opens_quickswap(page: Page, base_url):
    page.goto(base_url)
    page.wait_for_selector("#buffer-zone", timeout=10000)
    page.wait_for_function(
        "() => document.querySelector('.fcc-ps-th')",
        timeout=12000,
    )
    # Click the toolhead block — should open the manage modal on that
    # toolhead so the user is one step from a Quick-Swap.
    page.locator(f".fcc-ps-th[data-toolhead='{TEST_TOOLHEAD}']").first.click()
    expect(page.locator("#manageModal")).to_be_visible(timeout=5000)
    # The Quick-Swap section should be visible since we opened a toolhead.
    expect(page.locator("#manage-quickswap-section")).to_be_visible(timeout=5000)


@pytest.mark.usefixtures("require_server", "bound_xl1")
def test_widget_collapsible(page: Page, base_url):
    """Collapsed mode hides the per-printer body and shows a single chip
    strip inline with the header — every toolhead from every printer in
    the user's printer order."""
    page.goto(base_url)
    page.wait_for_selector("#buffer-zone", timeout=10000)
    page.wait_for_function(
        "() => document.querySelector('.fcc-ps-th')",
        timeout=12000,
    )
    body = page.locator("#printer-status-widget .fcc-ps-body").first
    header_chips = page.locator("#printer-status-widget .fcc-ps-header-chips").first
    expect(body).to_be_visible()
    expect(header_chips).to_be_hidden()
    # Click header to collapse → header chip strip becomes the entire view.
    page.locator("#printer-status-widget .fcc-ps-header-bar").click()
    expect(body).to_be_hidden(timeout=2000)
    expect(header_chips).to_be_visible(timeout=2000)
    # Click again to re-expand.
    page.locator("#printer-status-widget .fcc-ps-header-bar").click()
    expect(body).to_be_visible(timeout=2000)
    expect(header_chips).to_be_hidden(timeout=2000)


@pytest.mark.usefixtures("require_server", "bound_xl1")
def test_collapsed_header_chip_clickable(page: Page, base_url):
    """A chip in the collapsed header strip is a Quick-Swap entry point,
    same as the expanded block."""
    page.goto(base_url)
    page.wait_for_selector("#buffer-zone", timeout=10000)
    page.wait_for_function(
        "() => document.querySelector('.fcc-ps-th')",
        timeout=12000,
    )
    page.locator("#printer-status-widget .fcc-ps-header-bar").click()
    chip = page.locator(
        f"#printer-status-widget .fcc-ps-header-chips .fcc-ps-mini[data-toolhead='{TEST_TOOLHEAD}']"
    ).first
    expect(chip).to_be_visible(timeout=3000)
    chip.click()
    expect(page.locator("#manageModal")).to_be_visible(timeout=5000)
    expect(page.locator("#manage-quickswap-section")).to_be_visible(timeout=5000)


@pytest.mark.usefixtures("require_server", "bound_xl1")
def test_widget_visual_collapsed_baseline(page: Page, base_url, snapshot):
    """Pin the collapsed-state header layout. Expanded snapshot would be
    too flaky against live spool weights/colors; collapsed shell stays
    structurally stable."""
    page.goto(base_url)
    page.wait_for_selector("#buffer-zone", timeout=10000)
    page.wait_for_function(
        "() => document.querySelector('.fcc-ps-th')",
        timeout=12000,
    )
    # Collapse via the toggle so only the header shell is visible.
    page.evaluate("() => { localStorage.setItem('fcc.printerStatus.collapsed', '1'); }")
    page.evaluate("() => { if (window.togglePrinterStatusWidget) {"
                  "  localStorage.setItem('fcc.printerStatus.collapsed', '0');"
                  "  window.togglePrinterStatusWidget();"
                  "} }")
    page.wait_for_timeout(300)
    snapshot(page.locator("#printer-status-widget"), "printer-status-widget-collapsed")


@pytest.mark.usefixtures("require_server")
def test_widget_hidden_when_no_bound_toolheads(page: Page, base_url, api_base_url):
    """If every dryer box has zero bindings, the widget stays hidden so it
    doesn't take up dashboard space for users not yet using bindings."""
    # Snapshot every dryer box's bindings, then clear them.
    boxes = requests.get(f"{api_base_url}/api/dryer_boxes/slots", timeout=5).json().get("slots", [])
    box_originals = {}
    seen_boxes = set()
    for s in boxes:
        b = s["box"]
        if b in seen_boxes:
            continue
        seen_boxes.add(b)
        snap = requests.get(
            f"{api_base_url}/api/dryer_box/{b}/bindings", timeout=5
        ).json().get("slot_targets", {})
        box_originals[b] = snap
        requests.put(
            f"{api_base_url}/api/dryer_box/{b}/bindings",
            json={"slot_targets": {}},
            timeout=5,
        )
    try:
        page.goto(base_url)
        page.wait_for_selector("#buffer-zone", timeout=10000)
        # Give the widget time to attempt aggregation.
        page.wait_for_timeout(1500)
        widget = page.locator("#printer-status-widget")
        # Should remain hidden (display:none) since nothing is bound.
        is_visible = widget.is_visible()
        assert not is_visible, "Widget should be hidden when no toolheads are bound"
    finally:
        for b, original in box_originals.items():
            requests.put(
                f"{api_base_url}/api/dryer_box/{b}/bindings",
                json={"slot_targets": original},
                timeout=5,
            )
