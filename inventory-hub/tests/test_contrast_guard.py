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


@pytest.mark.usefixtures("require_server")
def test_low_stock_title_bar_button_is_readable(page: Page, base_url: str, assert_contrast):
    """Group 57.2 — the ⚠️ count in the title bar (Bootstrap's outline-warning
    on the dark bar): out of the box Low and Out in count pills (57.3: white on
    #444), and as one number (Settings -> Low stock count), hovered, and stale
    after a read that failed: "Out 11?" (and the 🏷️ Backlog count's "(53)?",
    Group 57 review round 2, whose "?" is drawn in the button's padding). Read-only: the heartbeat is
    dev's own; the failed read is stubbed, without a reload, so the count kept
    is the one painted before it. The guard scores a root's descendants, so the
    bar's buttons row is the root, and the counts are shown to be among what
    it scores."""
    import json as _json
    import conftest   # local: keeps this file's header out of other branches' merges
    from test_text_size_guard import _read_only
    _read_only(page)
    failing = {"on": False}

    def pulse(route):
        resp = route.fetch()
        body = resp.json()
        if failing["on"]:
            for key in ("low_stock", "label_backlog"):
                if key in body:
                    body[key] = {"read_ok": False, "read_error": "couldn't read Spoolman's spools (test)"}
        route.fulfill(response=resp, body=_json.dumps(body))
    page.route("**/api/dashboard_pulse*", pulse)
    page.goto(base_url)
    num = page.locator("#btn-low-stock-count [data-low-stock-count]")
    page.wait_for_function("() => { const n = document.querySelector('#btn-low-stock-count [data-low-stock-count]');"
                           " return !!n && /^\\d+$/.test(n.textContent.trim()); }", timeout=20000)
    row = page.locator("nav.navbar .fcc-titlebar-actions")
    assert_contrast(row)
    scored = lambda: [o.get("text", "").strip() for o in conftest.contrast_offenders(row, min_ratio=100)]
    pills = [page.locator(f"#btn-low-stock-count [data-{k}-count]").text_content().strip() for k in ("low", "out")]
    assert all(n in scored() for n in pills), (pills, scored())
    page.locator("#btn-low-stock-count").hover()
    assert_contrast(row)
    # One number (Settings -> Low stock count), shown live.
    page.evaluate("() => document.documentElement.setAttribute('data-fcc-low-count', 'one')")
    assert_contrast(row)
    assert num.text_content().strip() in scored(), scored()
    page.evaluate("() => document.documentElement.setAttribute('data-fcc-low-count', 'both')")

    page.wait_for_function(r"() => /\(\d+\)/.test(document.getElementById('btn-backlog-count').textContent)",
                           timeout=20000)
    failing["on"] = True
    page.wait_for_function("() => ['btn-low-stock-count', 'btn-backlog-count'].every((id) =>"
                           " document.getElementById(id).dataset.read === 'failed')", timeout=20000)
    page.mouse.move(5, 300)
    assert_contrast(row)
    marks = [o.get("text", "").strip() for o in conftest.contrast_offenders(row, min_ratio=100)]
    assert marks.count("?") >= 2, marks             # both "?" marks are scored


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
@pytest.mark.parametrize("size", ["Standard", "Extra Large"])
def test_qr_questions_are_readable(page: Page, base_url: str, assert_contrast, size):
    """Each "📷 Scan to …" QR wears its button's colour (Derek, 2026-10-21):
    amber, cyan, grey, light, dark and purple captions on the dark dialogs,
    and the captions are now label size. The move question in its four shapes
    and "Record it as coming from…" are opened with no-op answers and closed
    with Escape: nothing is moved or recorded.

    Since 2026-10-22 each QR sits under its own button, the buttons spread to
    match (test_qr_under_buttons_e2e.py): the buttons and their QRs share one
    grid, the record-source's slots without a QR sit on a line above it. Both
    are judged here, at Standard and Extra Large.

    Since 2026-10-23 "No box" is purple (btn-purple: white on #6f42c1, 6.5:1;
    hovered #5e38a4) and so is its QR caption (#a98eda): Derek found the grey
    too close to Cancel's. RED on 15ce8f4 (product files at 15ce8f4 under
    this test): No box was white on grey rgb(108, 117, 125)."""
    import conftest
    page.add_init_script("(() => { try { localStorage.setItem('fcc.textSize', %r); } catch (e) {} })();" % size)
    page.goto(base_url)
    page.wait_for_function("() => typeof window.confirmActivePrint === 'function'"
                           " && typeof _askRecordSource === 'function'")
    questions = (
        "{ title: 'Load #57 onto XL-1?', msg: 'A test question.', printing: false,"
        "  onConfirm() {}, onCancel() {}, onStore() {}, ids: { overlay: 'fcc-cg-question' } }",
        "{ title: 'Load #57 onto XL-1?', msg: 'A test question.', printing: true,"
        "  onConfirm() {}, onCancel() {}, onStore() {}, ids: { overlay: 'fcc-cg-question' } }",
        "{ title: 'Store #57 in LR-MDB-1 slot 1?', msg: 'A test question.', noLoad: true, printing: false,"
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
    # The buttons with QRs and the QRs themselves (one grid): the free slot,
    # No box, Cancel. Not the line above them, which holds the disabled slot
    # button ("holds #99", Bootstrap's btn-outline-secondary): 3.56:1, and was
    # before these changes (a disabled control; reported separately, colours
    # untouched here).
    row = page.locator("#fcc-record-source .fcc-rs-btns")
    expect(row.locator(".fcc-confirm-qr-row")).to_be_visible()
    assert_contrast(row)
    scored = [o["text"] for o in conftest.contrast_offenders(row, min_ratio=100)]
    assert sum("SCAN" in t.upper() for t in scored) == 3, scored
    # The slot's box id and "slot 1" are each kept whole in a span
    # (2026-10-22 review), so each is judged as its own text.
    assert any(t.startswith("No box") for t in scored) and "LR-MDB-1" in scored and "slot 1" in scored, scored
    # No box has its own purple (Derek, 2026-10-23: grey, it and its QR were
    # too close to Cancel's): white on Bootstrap's purple, hovered too, and its
    # QR caption the lighter purple, each judged above.
    def no_box_and_its_caption():
        by_text = {o["text"]: o for o in conftest.contrast_offenders(row, min_ratio=100)}
        caption = next((o for t, o in by_text.items() if "SCAN: NO BOX" in t.upper()), None)
        return by_text.get("No box"), caption, by_text
    no_box_settled = """() => { const b = document.querySelector('#fcc-record-source .fcc-rs-none');
        return !!b && b.getAnimations().length === 0; }"""   # Bootstrap's 0.15 s colour transition
    page.wait_for_function(no_box_settled, timeout=5000)
    nobox, caption, seen = no_box_and_its_caption()
    assert nobox and (nobox["fg"], nobox["bg"]) == ("rgb(255, 255, 255)", "rgb(111, 66, 193)"), seen
    assert caption and caption["fg"] == "rgb(169, 142, 218)", seen
    page.hover("#fcc-record-source .fcc-rs-none")
    page.wait_for_timeout(50)
    page.wait_for_function(no_box_settled, timeout=5000)
    assert_contrast(row)
    nobox, _caption, seen = no_box_and_its_caption()
    assert nobox and (nobox["fg"], nobox["bg"]) == ("rgb(255, 255, 255)", "rgb(94, 56, 164)"), seen
    page.keyboard.press("Escape")
    expect(page.locator("#fcc-record-source")).to_have_count(0)
    # Two free slots: they sit on the line above (cyan, enabled), No box and
    # Cancel share the grid with their two QRs.
    page.evaluate("""() => { window.__cgRs = _askRecordSource({ head: 'XL-1', spool_location: '', feeds: [
        { box: 'LR-MDB-1', slot: '1', free: true }, { box: 'PM-DB-XL-L', slot: '1', free: true }] }, 57, null); }""")
    panel = page.locator("#fcc-record-source .fcc-rs-panel")
    expect(panel.locator(".fcc-confirm-qr-row")).to_be_visible()
    assert_contrast(panel)
    scored = [o["text"] for o in conftest.contrast_offenders(panel, min_ratio=100)]
    assert "PM-DB-XL-L" in scored and "slot 1" in scored, scored
    # No box (it has the focus here) and its QR, the first, are purple too:
    # with the focus Bootstrap draws it in its hover purple.
    page.wait_for_function(no_box_settled, timeout=5000)
    by_text = {o["text"]: o for o in conftest.contrast_offenders(panel, min_ratio=100)}
    nobox = by_text.get("No box")
    assert nobox and nobox["bg"] in ("rgb(111, 66, 193)", "rgb(94, 56, 164)"), by_text
    assert any("SCAN: NO BOX" in t.upper() and o["fg"] == "rgb(169, 142, 218)" for t, o in by_text.items()), by_text
    page.keyboard.press("Escape")


# Two printers as the INDX and the XL are (8 heads and 5), with spools and
# their material lines, for the even rows under each name (Derek, 2026-10-22
# and 2026-10-23).
EVEN_ROWS_FLEET = {
    "ZZ Contrast INDX": {"state": {"state": "IDLE", "is_active": False}, "heads": [
        (f"ZC-{i}", i in (1, 4), {"id": 9500 + i, "color": "E0A030" if i == 1 else "1B1B1B",
                                  "color_direction": "longitudinal", "remaining_weight": 64 if i == 4 else 811,
                                  "initial_weight": 1000, "display": f"#{9500 + i} Contrast Spool",
                                  "details": {"material": "Polycarbonate" if i == 1 else "PETG"}}
         if i in (1, 4) else None) for i in range(1, 9)]},
    "ZZ Contrast XL": {"state": {"state": "PRINTING", "is_active": True}, "heads": [
        (f"ZD-{i}", True, {"id": 9510 + i, "color": "F0F0F0", "color_direction": "longitudinal",
                           "remaining_weight": 432, "initial_weight": 1000, "display": f"#{9510 + i} Contrast White",
                           "details": {"material": "PLA"}} if i == 2 else None) for i in range(1, 6)]},
}


@pytest.mark.usefixtures("require_server")
def test_printer_status_even_rows_are_readable(page: Page, base_url: str, assert_contrast):
    """Printer Status with each printer's name, the info line under it
    (2026-10-24: the state badge, then the 🛑 review count) and its tiles
    under that in even rows (Derek, 2026-10-22 / 2026-10-23: the 8 heads
    4 + 4 at this size), at Extra Large, the material lines 1.2 high: every
    tile, name, badge and 🛑 review count readable, the red ATTENTION badge
    too. A made-up fleet and made-up reviews in this page only
    (conftest.stub_printer_fleet); nothing is written."""
    import json as _json
    import conftest
    fleet = dict(EVEN_ROWS_FLEET)
    fleet["ZZ Contrast Attention"] = {"state": {"state": "ATTENTION", "is_active": False}, "heads": [
        (f"ZT-{i}", True, None) for i in range(1, 3)]}
    conftest.stub_printer_fleet(page, fleet)
    pending = [{"printer_name": "ZZ Contrast INDX", "job_id": f"c{i}", "kind": "cancel"} for i in range(3)] + \
              [{"printer_name": "ZZ Contrast Attention", "job_id": "t0", "kind": "cancel"}]
    page.route("**/api/cancel_deduct/pending*", lambda route: route.fulfill(
        status=200, content_type="application/json", body=_json.dumps({"pending": pending})))
    page.add_init_script("(() => { try { localStorage.setItem('fcc.textSize', 'Extra Large'); } catch (e) {} })();")
    page.goto(base_url)
    page.wait_for_function("() => document.querySelectorAll('#printer-status-widget .fcc-ps-row').length === 3"
                           " && document.querySelector('#printer-status-widget .fcc-ps-toolheads[data-rows=\"4+4\"]')"
                           " && document.querySelectorAll('#printer-status-widget .fcc-ps-info .fcc-ps-count .fcc-cr-chip').length === 2",
                           timeout=45_000)
    widget = page.locator("#printer-status-widget")
    assert_contrast(widget)
    scored = [o["text"] for o in conftest.contrast_offenders(widget, min_ratio=100)]
    assert any(t == "Polycarbonate" for t in scored) and any(t.startswith("ZC-8") for t in scored), scored
    assert "ZZ Contrast INDX" in scored and "🛑 3" in scored and "🛑 1" in scored, scored
    assert {"IDLE", "PRINTING", "ATTENTION"} <= set(scored), scored


@pytest.mark.usefixtures("require_server")
def test_printer_status_on_a_phone_and_its_wrapped_strip_are_readable(page: Page, base_url: str, assert_contrast):
    """The 2026-10-23 review's layouts: on a 390 px phone the tiles start at
    the row's edge, a printer between two others shows both arrows beside
    its name, and the collapsed strip wraps a printer's chips onto a
    second line. Every tile, name, arrow, badge, chip and 🛑 count readable
    there. A made-up fleet and reviews in this page only; nothing written."""
    import json as _json
    import conftest
    fleet = dict(EVEN_ROWS_FLEET)
    fleet["ZZ Contrast Middle"] = {"state": {"state": "PAUSED", "is_active": False}, "heads": [
        (f"ZM-{i}", True, None) for i in range(1, 4)]}
    conftest.stub_printer_fleet(page, fleet)
    pending = [{"printer_name": "ZZ Contrast Middle", "job_id": f"m{i}", "kind": "cancel"} for i in range(2)]
    page.route("**/api/cancel_deduct/pending*", lambda route: route.fulfill(
        status=200, content_type="application/json", body=_json.dumps({"pending": pending})))
    page.add_init_script("(() => { try { localStorage.setItem('fcc.printerStatus.order', JSON.stringify("
                         "['ZZ Contrast INDX', 'ZZ Contrast Middle', 'ZZ Contrast XL'])); } catch (e) {} })();")
    page.set_viewport_size({"width": 390, "height": 900})
    page.goto(base_url)
    page.wait_for_function("() => document.querySelectorAll('#printer-status-widget .fcc-ps-row.fcc-ps-edge').length === 3"
                           " && document.querySelector('#printer-status-widget .fcc-ps-info .fcc-cr-chip')",
                           timeout=45_000)
    widget = page.locator("#printer-status-widget")
    assert_contrast(widget)
    scored = [o["text"] for o in conftest.contrast_offenders(widget, min_ratio=100)]
    assert "▲" in scored and "▼" in scored and "🛑 2" in scored and "PAUSED" in scored, scored
    page.locator("#printer-status-widget .fcc-ps-header-bar").click()
    expect(page.locator("#printer-status-widget .fcc-ps-header-chips")).to_be_visible(timeout=2000)
    page.set_viewport_size({"width": 700, "height": 900})
    # The INDX's heads don't fit in 700 px: they scroll sideways in their own
    # box (Group 50.1, Derek's fallback; they wrapped onto a second line before).
    scrolls = page.evaluate("""() => { const box = document.querySelector('#printer-status-widget .fcc-ps-printer-group .fcc-ps-strip-heads');
        return !!box && box.scrollWidth > box.clientWidth + 1; }""")
    assert scrolls, "the INDX's heads should scroll sideways at 700 px"
    assert_contrast(widget)
    scored = [o["text"] for o in conftest.contrast_offenders(widget, min_ratio=100)]
    assert any(t.startswith("ZC-8") for t in scored) and "🛑 2" in scored, scored


@pytest.mark.usefixtures("require_server")
def test_settings_this_browser_section_is_readable(page: Page, base_url: str, assert_contrast):
    """Settings -> 🖥️ This Browser, with the per-browser Text size control
    (readability, 2026-10-21): its label, the help lines under each setting
    (now the section help's 0.55 grey: at 0.45 they were 4.4:1 on the black
    card) and the selects. Read-only: Settings is opened and closed, nothing
    is saved."""
    import conftest
    page.goto(base_url)
    page.wait_for_function("() => typeof window.openConfigModal === 'function'")
    page.evaluate("() => window.openConfigModal()")
    select = page.locator('.cfgset-input[data-key="fcc.textSize"]')
    expect(select).to_be_visible(timeout=15000)
    section = page.locator("#config-generated-settings > div.mb-3", has=select)
    assert "This Browser" in section.inner_text()
    assert_contrast(section)
    # The help lines and the labels are judged (the walker skips only the root).
    scored = [o["text"] for o in conftest.contrast_offenders(section, min_ratio=100)]
    assert any(t.startswith("Text size") for t in scored), scored
    assert any(t.startswith("How big FCC's text is") for t in scored), scored
    # The select itself: light text on its dark field.
    colours = select.evaluate("(el) => { const s = getComputedStyle(el); return [s.color, s.backgroundColor]; }")
    assert colours == ["rgb(255, 255, 255)", "rgb(33, 37, 41)"], colours


@pytest.mark.usefixtures("require_server")
def test_unmeasured_review_cards_are_readable(page: Page, base_url: str, assert_contrast):
    """Group 56.3: the 🛑 Review's "couldn't measure" cards, one per reason (a
    completion whose footer couldn't be read, one that lists no filament, one
    whose file FCC couldn't download, and the older "replaced" card): the header,
    the filename, the banner with its bold reason, and Discard all readable. Made-up
    reviews in this page only; nothing is written."""
    import json as _json
    import conftest
    pending = []
    for i, reason in enumerate(["no_footer", "empty_footer", "no_download", None,
                                "unreadable_moves", "unsampled"]):
        rec = {"printer_name": "ZZ Contrast XL", "job_id": f"u{i}", "filename": "/usb/RACCOON~1.BGC",
               "progress": 1.0, "total_grams": 0.0, "spools": [], "ambiguous": False,
               "kind": "progress_unknown", "usage_map": None}
        if reason:
            rec["unmeasured_reason"] = reason
        pending.append(rec)
    page.route("**/api/cancel_deduct/pending*", lambda route: route.fulfill(
        status=200, content_type="application/json", body=_json.dumps({"pending": pending})))
    page.goto(base_url)
    page.wait_for_function("() => typeof window.openCancelReview === 'function'")
    page.evaluate("() => window.openCancelReview()")
    page.wait_for_selector('#fcc-cancel-review-overlay .fcc-cr-card[data-job="u3"]', timeout=15000)
    overlay = page.locator("#fcc-cancel-review-overlay")
    assert_contrast(overlay)
    scored = " | ".join(o["text"] for o in conftest.contrast_offenders(overlay, min_ratio=100))
    for words in ("filament footer couldn't be read", "filament footer lists no filament",
                  "download or read the print's file", "replaced", "read the moves",
                  "ended before FCC read its progress", "/usb/RACCOON~1.BGC", "Discard"):
        assert words in scored, (words, scored)
    page.keyboard.press("Escape")


@pytest.mark.usefixtures("require_server")
def test_scan_holding_pickers_notice_lines_are_readable(page: Page, base_url: str, assert_contrast):
    """Group 61 review: the notice line of each picker that holds scans (the
    legacy-ID duplicate picker's and the parent tree picker's), with the note a
    refused scan is given. Opened from the page's own functions with made-up
    spools and places; nothing is read or written."""
    import conftest
    page.goto(base_url)
    page.wait_for_function("() => typeof window.showLegacySpoolPicker === 'function'"
                           " && typeof _renderParentTreePicker === 'function'")
    note = "#999 isn't one of the spools listed: pick one of them, print a new label, add a new spool, or Cancel"
    page.evaluate("""(note) => {
        const spool = (id) => ({ id, remaining_weight: 800, location: 'ZZ-CONTRAST-1', archived: false, filament_id: 7,
            filament_name: 'Contrast Black', material: 'PLA', vendor_name: 'FCC Test', display: '#' + id });
        window.showLegacySpoolPicker({ legacy_id: '999120', candidates: [spool(999134), spool(999135)] });
        document.getElementById('fcc-legacy-picker-flash').textContent = note;
    }""", note)
    picker = page.locator("#fcc-legacy-picker-overlay")
    expect(picker).to_be_visible(timeout=5000)
    assert_contrast(picker)
    assert any(o.get("id") == "fcc-legacy-picker-flash"
               for o in conftest.contrast_offenders(picker, min_ratio=100)), "the picker's notice line was never scored"
    page.click("#fcc-legacy-picker-cancel")
    page.evaluate("""() => {
        const rows = [{ LocationID: 'ZZ-CONTRAST-ROOM', Name: 'Contrast Room', Type: 'Room' },
                      { LocationID: 'ZZ-CONTRAST-BOX', Name: 'Contrast Box', Type: 'Dryer Box' }];
        _renderParentTreePicker(rows, 'ZZ-CONTRAST-BOX', document.getElementById('edit-parent'),
            document.getElementById('locModal'));
    }""")
    tree = page.locator("#fcc-parent-tree-picker")
    expect(tree).to_be_visible(timeout=5000)
    page.evaluate("""() => { document.querySelector('#fcc-parent-tree-picker .fcc-tp-flash').textContent =
        "ZZ-CONTRAST-BOX isn't one of the parents offered here (this location itself, one inside it, or not a place): pick a parent, or Cancel"; }""")
    assert_contrast(tree)
    assert any("fcc-tp-flash" in (o.get("className") or "")
               for o in conftest.contrast_offenders(tree, min_ratio=100)), "the tree picker's notice line was never scored"
    page.click("#fcc-parent-tree-picker [data-tp='cancel']")
