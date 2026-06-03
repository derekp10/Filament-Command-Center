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
def test_widget_shows_unbound_printers_with_placeholder(page: Page, base_url, api_base_url):
    """L140 + box-bounding fix: with zero bound dryer-slots the widget
    previously hid EVERY printer (the symptom that hid Core One on prod
    when only XL had slot_targets). After the fix, every printer in
    printer_map renders. An unbound toolhead that is EMPTY gets the
    "🔗 no bound slot" placeholder; an unbound toolhead that HOLDS a spool
    surfaces the spool (occupancy keys off the toolhead, not the dryer
    box) while keeping the fcc-ps-th-unbound class + 🔗 hint. Both kinds
    carry the fcc-ps-th-unbound class, so the L140 assert below still
    holds AND the box-bounding regression is pinned: a loaded toolhead
    with no dryer box is no longer masked."""
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
        # Wait for the widget body to populate (aggregation takes a sec).
        page.wait_for_function(
            "() => { const w = document.getElementById('printer-status-widget');"
            "       return w && getComputedStyle(w).display !== 'none'"
            "         && w.querySelectorAll('.fcc-ps-row').length > 0; }",
            timeout=5000,
        )
        widget = page.locator("#printer-status-widget")
        # The widget should now show printers (rather than be hidden).
        rows = widget.locator(".fcc-ps-row")
        assert rows.count() > 0, "Widget should render rows even when no toolheads are bound"
        # Every rendered toolhead now carries the unbound class (bindings cleared),
        # whether it's an empty placeholder OR a loaded-but-unbound tile.
        unbound = widget.locator(".fcc-ps-th-unbound")
        assert unbound.count() > 0, (
            "With all bindings cleared, every rendered toolhead should carry the unbound class"
        )
        # Box-bounding regression guard: any toolhead that physically holds a
        # spool must still surface it (data-spool-id present on the unbound
        # tile) — occupancy is NOT masked by the absence of a dryer-box
        # binding. Tolerant of an empty dev: only asserts when the live
        # payload reports a loaded toolhead.
        ps = requests.get(
            f"{api_base_url}/api/dashboard_pulse?include=printer_status", timeout=15
        ).json().get("printer_status", {})
        any_loaded = any(
            th.get("item") for p in ps.values() for th in p.get("toolheads", [])
        )
        if any_loaded:
            occupied_unbound = widget.locator(".fcc-ps-th-unbound[data-spool-id]")
            assert occupied_unbound.count() > 0, (
                "A loaded toolhead with no dryer-box binding must still render its "
                "spool (box-bounding fix), not a bare placeholder"
            )
    finally:
        for b, original in box_originals.items():
            requests.put(
                f"{api_base_url}/api/dryer_box/{b}/bindings",
                json={"slot_targets": original},
                timeout=5,
            )


@pytest.mark.usefixtures("require_server")
def test_occupied_unbound_toolhead_shows_spool(page: Page, base_url):
    """Box-bounding fix (deterministic, injected payload — no live-data
    dependency): a toolhead with NO dryer-box binding (`unbound: true`) but
    a spool loaded must render the SPOOL, not the bare "no bound slot"
    placeholder, while keeping the fcc-ps-th-unbound class + a 🔗 hint. Pins
    both the expanded tile and the collapsed compact chip."""
    page.goto(base_url)
    page.wait_for_selector("#printer-status-widget", timeout=10000)
    page.wait_for_function(
        "() => typeof window.refreshPrinterStatusWidgetFromAggregate === 'function'",
        timeout=8000,
    )
    # Inject a synthetic printer whose only toolhead is unbound + loaded.
    page.evaluate(
        """() => window.refreshPrinterStatusWidgetFromAggregate({
            'ZZ Test Printer': {
                state: null,
                toolheads: [{
                    id: 'ZZ-1', position: 0, unbound: true,
                    item: { id: 9001, color: '00AAFF', color_direction: 'longitudinal',
                            remaining_weight: 712, display: '#9001 Test Spool' }
                }]
            }
        })"""
    )
    widget = page.locator("#printer-status-widget")
    # Expanded: the unbound tile carries the spool id (occupancy surfaced) AND
    # the 🔗 "no bound slot" hint (discoverability retained).
    tile = widget.locator(".fcc-ps-th-unbound[data-spool-id='9001']").first
    expect(tile).to_be_visible(timeout=4000)
    assert "no bound slot" in tile.inner_text(), "🔗 unbound hint must remain on the loaded tile"
    # It must NOT be the bare placeholder (placeholder has no data-spool-id and
    # no weight body); confirm the spool weight chip rendered.
    assert "712" in tile.inner_text(), "loaded spool weight must render, not be masked"
    # Collapsed: the compact chip shows the swatch + weight + 🔗, not just 🔗.
    page.locator("#printer-status-widget .fcc-ps-header-bar").click()
    chip = widget.locator(".fcc-ps-header-chips .fcc-ps-mini[data-toolhead='ZZ-1']").first
    expect(chip).to_be_visible(timeout=3000)
    chip_txt = chip.inner_text()
    assert "712" in chip_txt, "collapsed chip must show occupancy weight for a loaded unbound toolhead"


@pytest.mark.usefixtures("require_server")
def test_l56_printer_status_payload_includes_state(api_base_url):
    """L56 — dashboard_pulse's printer_status section must carry each
    printer's PrusaLink state alongside the toolhead list, so a printer's
    live PRINTING / IDLE / OFFLINE shows even between weight changes. The
    state probe reads PrusaLink directly and has no dryer-box dependency
    (neither does occupancy or auto-deduct — both key off the toolhead).
    Probe direct from PrusaLink and pass through; widget rendering tested
    separately."""
    r = requests.get(
        f"{api_base_url}/api/dashboard_pulse?include=printer_status", timeout=15
    )
    assert r.ok, f"dashboard_pulse failed: {r.status_code} {r.text}"
    payload = r.json().get("printer_status") or {}
    assert payload, "expected at least one printer in printer_status"
    for name, info in payload.items():
        assert "state" in info, f"printer {name!r} missing 'state' key"
        st = info["state"]
        # PrusaLink reachable → dict with state + is_active; unreachable → None.
        # Both are valid per L56 (we surface OFFLINE in the UI for None).
        assert st is None or (
            isinstance(st, dict) and "state" in st and "is_active" in st
        ), f"printer {name!r} state malformed: {st!r}"


@pytest.mark.usefixtures("require_server", "bound_xl1")
def test_l56_state_badge_renders_in_widget(page: Page, base_url):
    """L56 — the printer-state badge renders for every printer the widget
    shows. Critically, the badge must SURVIVE a subsequent sync-pulse:
    the legacy `_aggregate()` path returns rows without `state`, and an
    earlier draft of this fix let that path wipe the badge between bulk
    pulses. Wait through a sync-pulse cycle and assert the badge sticks."""
    page.goto(base_url)
    page.wait_for_selector("#buffer-zone", timeout=10000)
    page.wait_for_function(
        "() => document.querySelectorAll('#printer-status-widget .fcc-ps-state').length > 0",
        timeout=12000,
    )
    initial_count = page.evaluate(
        "() => document.querySelectorAll('#printer-status-widget .fcc-ps-state').length"
    )
    assert initial_count > 0, "no state badges rendered on first pulse"
    # Force a sync-pulse to trigger the legacy `_aggregate()` re-render.
    page.evaluate(
        "() => document.dispatchEvent(new CustomEvent('inventory:sync-pulse'))"
    )
    page.wait_for_timeout(500)
    after_count = page.evaluate(
        "() => document.querySelectorAll('#printer-status-widget .fcc-ps-state').length"
    )
    assert after_count == initial_count, (
        f"sync-pulse wiped state badges (initial={initial_count}, after={after_count})"
    )


@pytest.mark.usefixtures("require_server", "bound_xl1")
def test_l361_toolhead_click_survives_rerender(page: Page, base_url):
    """L361 — clicking a toolhead tile must still open the manage modal
    even when the widget has just re-rendered (which happens frequently
    when a printer is actively PRINTING and the state badge / weight
    tick over). The fix moved the click handler to event delegation on
    the widget root, so the handler survives an arbitrary number of
    body re-renders. Without delegation, clicks that landed on a newly-
    rendered toolhead element silently dropped because the per-element
    listener belonged to the prior render generation.
    """
    page.goto(base_url)
    page.wait_for_selector("#buffer-zone", timeout=10000)
    page.wait_for_function(
        "() => document.querySelector('.fcc-ps-th')",
        timeout=12000,
    )
    # Force several full re-renders (mimics rapid sync-pulse during print).
    page.evaluate(
        """() => {
            const w = document.getElementById('printer-status-widget');
            const body = w.querySelector('.fcc-ps-body');
            const saved = body.innerHTML;
            // Wipe + restore three times so any per-element listener is
            // orphaned. Delegation on the widget root survives.
            for (let i = 0; i < 3; i++) {
                body.innerHTML = '';
                body.innerHTML = saved;
            }
        }"""
    )
    page.locator(f".fcc-ps-th[data-toolhead='{TEST_TOOLHEAD}']").first.click()
    expect(page.locator("#manageModal")).to_be_visible(timeout=5000)


@pytest.mark.usefixtures("require_server")
def test_dashboard_primes_all_locations_for_openmanage(page: Page, base_url, api_base_url):
    """Regression (2026-06-01): the L206 adaptive pulse only fetched
    /api/locations when the Location Manager TABLE was visible, so on the
    bare dashboard `state.allLocations` stayed [] — and openManage() looks the
    id up in allLocations and bails silently if missing. That silently broke
    clicking ANY dashboard surface that calls openManage (Printer Status
    widget tiles, spool-card location badges): the click did nothing, no error.
    Fix primes allLocations at startup. This pins it: WITHOUT opening the
    Location Manager, openManage() on a real location must open the modal."""
    # Pick a real location id from the live payload (prefer a toolhead — the
    # reported surface — else any location).
    loc_payload = requests.get(f"{api_base_url}/api/locations", timeout=10).json()
    loc_list = loc_payload if isinstance(loc_payload, list) else loc_payload.get("locations", [])
    toolhead_types = {"tool head", "no mmu direct load", "mmu slot"}
    target = next(
        (l.get("LocationID") for l in loc_list
         if str(l.get("Type", "")).lower() in toolhead_types and l.get("LocationID")),
        None,
    ) or next((l.get("LocationID") for l in loc_list if l.get("LocationID")), None)
    assert target, "no locations available to test openManage against"

    page.goto(base_url)
    page.wait_for_selector("#buffer-zone", timeout=10000)
    page.wait_for_function("() => typeof window.openManage === 'function'", timeout=8000)
    # Let the startup fetchLocations() prime land (single cold fetch populates
    # the location table rows).
    page.wait_for_function(
        "() => document.querySelector('#location-table tr')", timeout=8000
    )
    # Crucially: do NOT open the Location Manager first. openManage must work
    # straight off the dashboard.
    page.evaluate("(id) => window.openManage(id)", target)
    expect(page.locator("#manageModal")).to_be_visible(timeout=5000)
