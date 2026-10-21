"""
Contrast guard — catches gray-on-gray text anywhere inside the Phase 2/3
overlays and sections.

Background: we've chased the same class of bug repeatedly this round —
someone drops a Bootstrap `text-muted` onto a `bg-dark` surface and the
text becomes unreadable. Visual snapshots only catch the specific
placements they happen to capture; this test walks EVERY text-bearing
element in each new surface and asserts computed contrast meets
WCAG AA. If any future change re-introduces low-contrast text, this
fires with a list of exactly which elements.

Uses the `assert_contrast` fixture from conftest.py.
"""
from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect


TEST_BOX = "PM-DB-1"
TEST_TOOLHEAD = "XL-1"


@pytest.fixture
def bound_slot(borrow_box_bindings):
    """Bind PM-DB-1 slot 1 -> XL-1 so the Quick-Swap grid and Bind picker
    render populated rows. PM-DB-1 must be at its fixed baseline first and is
    put back to that baseline afterwards (conftest `borrow_box_bindings`)."""
    borrow_box_bindings(TEST_BOX, {"1": TEST_TOOLHEAD})


# ---------------------------------------------------------------------------
# Bind picker — the immediate offender that prompted this fix
# ---------------------------------------------------------------------------

@pytest.mark.usefixtures("require_server", "bound_slot")
def test_bind_picker_has_no_gray_on_gray_text(page: Page, open_manage_modal, assert_contrast):
    """The exact surface the user reported. Opens the picker, asserts
    every slot-row label meets AA contrast."""
    open_manage_modal(TEST_TOOLHEAD)
    page.locator("#quickswap-bind-slot-btn").click()
    overlay = page.locator("#fcc-bind-picker-overlay")
    # Bind picker fetches /api/dryer_boxes/slots before opening; 8s gives
    # headroom under sweep load, same pattern as other Group 9 timeouts.
    expect(overlay).to_be_visible(timeout=8000)
    # Let the slots list populate.
    expect(page.locator(".fcc-bind-picker-item").first).to_be_visible(timeout=3000)
    assert_contrast(overlay)


# ---------------------------------------------------------------------------
# Quick-Swap grid — populated toolhead view
# ---------------------------------------------------------------------------

@pytest.mark.usefixtures("require_server", "bound_slot")
def test_quickswap_section_has_no_gray_on_gray_text(page: Page, open_manage_modal, assert_contrast):
    open_manage_modal(TEST_TOOLHEAD)
    expect(page.locator(".fcc-qs-slot").first).to_be_visible(timeout=8000)
    assert_contrast(page.locator("#manage-quickswap-section"))


# ---------------------------------------------------------------------------
# Feeds editor — open state on a Dryer Box
# ---------------------------------------------------------------------------

@pytest.mark.usefixtures("require_server", "bound_slot")
def test_feeds_section_has_no_gray_on_gray_text(page: Page, open_manage_modal, assert_contrast):
    open_manage_modal(TEST_BOX)
    # Feeds starts collapsed; open it so the rows render and get asserted.
    page.locator("#feeds-toggle-btn").click()
    page.wait_for_timeout(400)
    assert_contrast(page.locator("#manage-feeds-section"))


# ---------------------------------------------------------------------------
# Confirm overlay — swap prompt
# ---------------------------------------------------------------------------

@pytest.mark.usefixtures("require_server", "bound_slot")
def test_quickswap_confirm_overlay_has_no_gray_on_gray_text(page: Page, open_manage_modal, assert_contrast):
    open_manage_modal(TEST_TOOLHEAD)
    expect(page.locator(".fcc-qs-slot").first).to_be_visible(timeout=8000)
    # Return-to-Slot opens the confirm overlay without needing a loaded spool
    # (it'll land on "nothing to return" if the toolhead is empty, which
    # still renders the same overlay shell we want to check).
    page.locator("#quickswap-return-btn").click()
    overlay = page.locator("#fcc-quickswap-confirm-overlay")
    # Group 40.6: a spool with no obvious slot opens the slot picker before the
    # confirm; Enter takes its highlight (nothing is written: no Yes here).
    page.wait_for_function(
        "!!document.getElementById('fcc-quickswap-confirm-overlay')"
        " || !!document.querySelector('#fcc-slot-picker [data-sp-state=\"ready\"]')", timeout=8000)
    if page.evaluate("!!document.querySelector('#fcc-slot-picker [data-sp-state=\"ready\"]')"):
        page.keyboard.press("Enter")
    # Overlay mount awaits a 3s active-print probe; 8s gives headroom
    # under sweep load (same fix as Group 14.2).
    expect(overlay).to_be_visible(timeout=8000)
    assert_contrast(overlay)


# ---------------------------------------------------------------------------
# Shortcuts overlay (? help)
# ---------------------------------------------------------------------------

@pytest.mark.usefixtures("require_server")
def test_shortcuts_overlay_has_no_gray_on_gray_text(page: Page, base_url: str, assert_contrast):
    page.goto(base_url)
    page.wait_for_selector("#btn-shortcuts-help", timeout=10000)
    page.locator("#btn-shortcuts-help").click()
    overlay = page.locator("#fcc-shortcuts-overlay")
    expect(overlay).to_be_visible(timeout=3000)
    assert_contrast(overlay)


# ---------------------------------------------------------------------------
# Printer Status widget (Group 9.3) — both expanded and collapsed views
# ---------------------------------------------------------------------------

@pytest.mark.usefixtures("require_server", "bound_slot")
def test_printer_status_widget_expanded_has_no_gray_on_gray_text(
    page: Page, base_url: str, assert_contrast
):
    page.goto(base_url)
    page.wait_for_selector("#buffer-zone", timeout=10000)
    page.wait_for_function(
        "() => document.querySelector('#printer-status-widget .fcc-ps-th')",
        timeout=8000,
    )
    assert_contrast(page.locator("#printer-status-widget"))


@pytest.mark.usefixtures("require_server")
def test_low_stock_panel_has_no_gray_on_gray_text(page: Page, base_url: str, assert_contrast):
    """Group 49.2a — the ⚠️ Low-stock list over the real dashboard: its tabs and
    filter, its rows on every list (one highlighted), tags and Buy links, the
    exclusion dialog, its error state, and the search panel's button
    that opens it. /api/stock_report is stubbed, so no dev data is read, and
    nothing is saved. (Hermetic twin: test_low_stock_panel.py.)"""
    import json as _json
    answers = [
        (200, {
            "success": True, "threshold_g": 250.0, "filaments": 2, "spools": 3,
            "low": [{"filament_id": 88, "display": "Overture - PETG - Red Blue", "color": "BA0C2F,0047BB",
                     "color_direction": "coaxial", "grams": 220.4, "spools": 2, "spools_total": 2,
                     "attributes": ["Silk"], "excluded": None,
                     "buy_url": "https://shop.example/s?q=Overture"}],
            "out": [{"filament_id": 20, "display": "Generic - PLA - Lipstick Red", "color": "ff0000",
                     "color_direction": "longitudinal", "grams": 0, "spools": 0, "spools_total": 1,
                     "attributes": [], "excluded": None, "buy_url": None}],
            "excluded": [{"filament_id": 41, "display": "Sunlu - PLA - Glow Green", "color": "55ff55",
                              "color_direction": "longitudinal", "grams": 120.0, "spools": 2, "spools_total": 3,
                              "attributes": [], "buy_url": None,
                              "excluded": {"reason": "Discontinued", "code": "discontinued",
                                               "note": "Prusa stopped making it", "at": "2026-10-20"}}]}),
        (502, {"success": False, "error": "spoolman_unreachable", "msg": "x"}),
    ]

    def _answer(route):
        status, body = answers.pop(0) if len(answers) > 1 else answers[0]
        route.fulfill(status=status, content_type="application/json", body=_json.dumps(body))
    page.route("**/api/stock_report", _answer)
    page.goto(base_url)
    page.wait_for_function("() => window.SearchEngine && typeof window.openLowStockPanel === 'function'")
    page.evaluate("SearchEngine.open()")
    expect(page.locator("#global-search-low-stock")).to_be_visible()
    assert_contrast(page.locator("#global-search-low-stock"))
    page.locator("#global-search-low-stock").click()
    panel = page.locator("#fcc-low-stock-overlay .fcc-stock-panel")
    expect(panel.locator(".fcc-stock-row.kb-active")).to_have_count(1)
    assert_contrast(panel)
    for key in ("out", "excluded"):                  # every list, the excluded one with its note
        panel.locator(f"[data-stock-tab='{key}']").click()
        expect(panel.locator(".fcc-stock-row.kb-active")).to_have_count(1)
        assert_contrast(panel)
    panel.locator("[data-stock-filter]").fill("glow")
    assert_contrast(panel)
    page.keyboard.press("ArrowDown")                  # out of the filter, into the list
    page.keyboard.press("Delete")                     # the reason dialog (editing), over the real page
    dialog = page.locator("#fcc-low-stock-reason [data-stock-dialog]")
    expect(dialog).to_be_visible()
    assert_contrast(dialog)
    page.keyboard.press("Escape")
    page.evaluate("window.openLowStockPanel()")      # the error state
    expect(panel.locator("[role=alert]")).to_be_visible()
    assert_contrast(panel)


@pytest.mark.usefixtures("require_server", "bound_slot")
def test_printer_status_widget_collapsed_has_no_gray_on_gray_text(
    page: Page, base_url: str, assert_contrast
):
    """Collapsed strip recurringly hits the text-muted footgun — pinned
    here so it can't slip back in. Empty toolheads' "empty" label is a
    common offender (Bootstrap text-muted is too dark for our bg)."""
    page.goto(base_url)
    page.wait_for_selector("#buffer-zone", timeout=10000)
    page.wait_for_function(
        "() => document.querySelector('#printer-status-widget .fcc-ps-th')",
        timeout=8000,
    )
    page.locator("#printer-status-widget .fcc-ps-header-bar").click()
    expect(page.locator("#printer-status-widget .fcc-ps-header-chips")).to_be_visible(
        timeout=2000
    )
    assert_contrast(page.locator("#printer-status-widget"))


# ---------------------------------------------------------------------------
# Spool window — the slicer profile row (Group 48.2)
# ---------------------------------------------------------------------------

@pytest.mark.usefixtures("require_server")
def test_spool_window_slicer_profile_row_is_readable(page: Page, base_url: str, assert_contrast):
    """Stubbed spool, so dev data can't change what is drawn."""
    import json as _json
    payload = {"id": 999001, "archived": False, "location": "Room LR", "comment": "", "used_weight": 100.0,
               "remaining_weight": 900.0, "extra": {},
               "filament": {"id": 555001, "name": "Test Color", "material": "PLA", "color_hex": "ff8800",
                            "weight": 1000, "vendor": {"name": "TestVendor"},
                            "extra": {"slicer_profile": '"Prusament PLA"'}}}
    page.route("**/api/spool_details*", lambda route: route.fulfill(
        status=200, content_type="application/json", body=_json.dumps(payload)))
    page.goto(base_url)
    page.wait_for_function("typeof openSpoolDetails === 'function' && modals && modals.spoolModal", timeout=10000)
    page.evaluate("openSpoolDetails(999001)")
    row = page.locator("#spool-detail-slicer-profile-row")
    expect(row).to_contain_text("Prusament PLA", timeout=5000)
    assert_contrast(row)


# ---------------------------------------------------------------------------
# Group 52.1b: "Spoolman didn't answer" notices (Location Manager + backlog)
# ---------------------------------------------------------------------------

@pytest.mark.usefixtures("require_server")
def test_manage_read_notice_has_no_gray_on_gray_text(page: Page, open_manage_modal, assert_contrast):
    """Shown only when a contents read fails: the strict reads of TEST_BOX
    answer 502 here, as the server does when Spoolman times out. Read-only."""
    def _down(route):
        if "strict=1" in route.request.url:
            route.fulfill(status=502, content_type="application/json",
                          body='{"error": "Couldn\'t read PM-DB-1 from Spoolman (Read timed out.)."}')
        else:
            route.continue_()

    page.route(lambda url: f"/api/get_contents?id={TEST_BOX}&" in url, _down)
    # The heartbeat's manage section would read dev's real contents and clear
    # the notice before the check (conftest.quiet_heartbeat's move).
    page.route("**/api/dashboard_pulse*", lambda route: route.abort())
    open_manage_modal(TEST_BOX)
    notice = page.locator("#manage-read-notice")
    expect(notice).to_be_visible(timeout=8000)
    assert_contrast(notice)


@pytest.mark.usefixtures("require_server")
def test_backlog_read_notice_has_no_gray_on_gray_text(page: Page, base_url: str, assert_contrast):
    """Shown when a backlog refresh fails while the window lists rows: the
    first answer lists one (fake) row, every later one fails. Read-only."""
    import json   # local: keeps this file's header out of other branches' merges
    answers = {"n": 0}
    row = {"id": 999531, "type": "spool", "registered": "2026-10-19T00:00:00",
           "filament": {"material": "PLA", "name": "Contrast Red", "color_hex": "c0392b",
                        "vendor": {"name": "FCC Test"}}}

    def _pending(route):
        answers["n"] += 1
        body = ({"success": True, "items": [row]} if answers["n"] == 1
                else {"success": False, "msg": "Spoolman didn't answer the spool list (HTTP 503)"})
        route.fulfill(status=200, content_type="application/json", body=json.dumps(body))

    page.route("**/api/print_queue/pending*", _pending)
    page.goto(base_url)
    page.wait_for_selector("#btn-backlog-count", timeout=10000)
    page.evaluate("window.openBacklogModal()")
    expect(page.locator(".backlog-row").first).to_be_visible(timeout=8000)
    page.evaluate("window.fetchBacklog()")
    notice = page.locator("#backlog-read-notice")
    expect(notice).to_be_visible(timeout=8000)
    assert_contrast(notice)


# ---------------------------------------------------------------------------
# Group 52 review, reads-1: "Spoolman didn't answer" in the Printer Status
# widget and the Locations table (hermetic twin: test_pulse_spool_read_reads1_page.py)
# ---------------------------------------------------------------------------

_READS1_DOWN = {"ok": False, "error": "Spoolman didn't answer (Read timed out. (read timeout=5))"}


def _reads1_scored(root, element_id):
    """The guard walks a root's DESCENDANTS, never the root itself, so a
    text-only notice passed as its own root is never scored. Check it through
    its parent, and prove it is scored: at an impossible ratio it is reported."""
    import conftest   # local: keeps this file's header out of other branches' merges
    return any(o["id"] == element_id for o in conftest.contrast_offenders(root, min_ratio=100))


@pytest.mark.usefixtures("require_server")
def test_printer_status_read_notice_has_no_gray_on_gray_text(page: Page, base_url: str, assert_contrast):
    """Shown when the heartbeat's spool read fails: every heartbeat here answers
    a failed read for one made-up printer, whose head is then "? not read".
    Routed answers only: no dev data is read or written. Expanded and collapsed
    (the notice sits outside the body the collapsed view hides)."""
    import json
    pulse = {"printer_status": {"ZZ Read Printer": {"state": None, "toolheads": [
                 {"id": "ZR-1", "position": 0, "item": None, "unbound": False, "loaded_count": 0}]}},
             "spool_read": _READS1_DOWN}
    page.route("**/api/dashboard_pulse*", lambda route: route.fulfill(
        status=200, content_type="application/json", body=json.dumps(pulse)))
    page.goto(base_url)
    notice = page.locator("#printer-status-read-notice")
    expect(notice).to_be_visible(timeout=10000)
    expect(page.locator("#printer-status-widget .fcc-ps-th-unread").first).to_be_visible(timeout=5000)
    widget = page.locator("#printer-status-widget")
    assert _reads1_scored(widget, "printer-status-read-notice")
    assert_contrast(widget)
    page.locator("#printer-status-widget .fcc-ps-header-bar").click()
    expect(page.locator("#printer-status-widget .fcc-ps-header-chips")).to_be_visible(timeout=2000)
    expect(notice).to_be_visible()
    assert_contrast(widget)


@pytest.mark.usefixtures("require_server")
def test_location_table_read_notice_has_no_gray_on_gray_text(page: Page, base_url: str, assert_contrast):
    """Shown when the table's spool read fails: /api/locations answers its
    'failed' header and every heartbeat a failed read, with made-up rows FCC
    has no earlier count for (each then shows "?"). Routed answers only: no dev
    data is read or written. Only the notice and the "?" cells are judged
    here; the rest of the table is the same as ever."""
    import json
    import conftest
    rows = [{"LocationID": "Unassigned", "Name": "Workbench / Unsorted", "Type": "Virtual",
             "Occupancy": "0 items", "Max Spools": 0, "parent_id": None, "Synthesized": True},
            {"LocationID": "ZZ-RD-1", "Name": "Read Test Box", "Type": "Dryer Box", "Max Spools": "4",
             "Occupancy": "0/4", "OccupancyRaw": 0, "parent_id": None},
            {"LocationID": "UNKNOWN", "Name": "Unknown (Physically Lost)", "Type": "Unknown",
             "Occupancy": "0 items", "Max Spools": 0, "parent_id": None, "Synthesized": True}]

    def _locations(route):
        if route.request.method != "GET":
            route.continue_()
            return
        route.fulfill(status=200, content_type="application/json",
                      headers={"X-FCC-Spool-Read": "failed"}, body=json.dumps(rows))

    page.route("**/api/locations", _locations)
    page.route("**/api/dashboard_pulse*", lambda route: route.fulfill(
        status=200, content_type="application/json",
        body=json.dumps({"locations": rows, "spool_read": _READS1_DOWN})))
    page.goto(base_url)
    page.wait_for_selector(".deck-btn, #command-buffer", timeout=10000)
    page.evaluate("window.openLocationsModal && window.openLocationsModal()")
    conftest.wait_modal_settled(page, "locMgrModal")
    notice = page.locator("#loc-read-notice")
    expect(notice).to_be_visible(timeout=10000)
    expect(page.locator("#location-table .loc-count-unread").first).to_be_visible(timeout=5000)
    body = page.locator("#locMgrModal .modal-body")
    assert _reads1_scored(body, "loc-read-notice")
    offenders = [o for o in conftest.contrast_offenders(body)
                 if o["id"] == "loc-read-notice" or "loc-count-unread" in str(o.get("className") or "")]
    assert offenders == [], offenders
    for cell in page.locator("#location-table td.col-status").all():
        assert_contrast(cell)


@pytest.mark.usefixtures("require_server")
def test_qr_questions_are_readable(page: Page, base_url: str, assert_contrast):
    """Each "📷 Scan to …" QR wears its button's colour (Derek, 2026-10-21):
    amber, cyan, grey, light and dark captions on the dark dialogs, and the
    captions are now label size. The move question in its three shapes and
    "Record it as coming from…" are opened with no-op answers and closed with
    Escape: nothing is moved or recorded."""
    import conftest
    page.goto(base_url)
    page.wait_for_function("() => typeof window.confirmActivePrint === 'function'"
                           " && typeof _askRecordSource === 'function'")
    questions = (
        "{ title: 'Load #57 onto XL-1?', msg: 'A test question.', printing: false,"
        "  onConfirm() {}, onCancel() {}, onStore() {}, ids: { overlay: 'fcc-cg-question' } }",
        "{ title: 'Load #57 onto XL-1?', msg: 'A test question.', printing: true,"
        "  onConfirm() {}, onCancel() {}, onStore() {}, ids: { overlay: 'fcc-cg-question' } }",
        "{ activePrint: { printer_name: 'XL', state: 'PRINTING', toolhead: 'XL-1' }, msg: 'A test question.',"
        "  onConfirm() {}, onCancel() {}, ids: { overlay: 'fcc-cg-question' } }",
    )
    for opts in questions:
        page.evaluate("() => window.confirmActivePrint(" + opts + ")")
        overlay = page.locator("#fcc-cg-question")
        expect(overlay.locator(".fcc-confirm-qr-row")).to_be_visible()
        assert_contrast(overlay)
        # The captions are judged (the walker skips only the root).
        scored = [o["text"] for o in conftest.contrast_offenders(overlay, min_ratio=100)]
        assert sum("SCAN" in t.upper() for t in scored) >= 2, scored
        page.keyboard.press("Escape")
        expect(overlay).to_have_count(0)
    page.evaluate("""() => { window.__cgRs = _askRecordSource({ head: 'XL-1', spool_location: '', feeds: [
        { box: 'LR-MDB-1', slot: '1', free: true }, { box: 'LR-MDB-1', slot: '2', free: false, claimed_by: 99 }] }, 57, null); }""")
    # Its QR row only: the dialog's disabled slot button ("holds #99", Bootstrap's
    # btn-outline-secondary) is 3.56:1 and was before this change (a disabled
    # control; reported separately, colours untouched here).
    row = page.locator("#fcc-record-source .fcc-confirm-qr-row")
    expect(row).to_be_visible()
    assert_contrast(row)
    scored = [o["text"] for o in conftest.contrast_offenders(row, min_ratio=100)]
    assert sum("SCAN" in t.upper() for t in scored) == 3, scored
    page.keyboard.press("Escape")
