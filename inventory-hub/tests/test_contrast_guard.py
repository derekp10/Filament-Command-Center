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
def test_loose_spools_list_has_no_gray_on_gray_text(page: Page, base_url: str, assert_contrast):
    """Group 58.4 — the 🧺 Loose spools list over the real dashboard: its button in
    the Locations window, its rows (one highlighted) with their place headings and
    tags, a place with no row, its yellow notice, Try again hovered, and the good
    empty read. /api/loose_spools is stubbed, so no dev data is read, and the list
    writes nothing. (Hermetic twin: test_loose_spools_58_4_js.py.)"""
    import json as _json
    import conftest   # local: keeps this file's header out of other branches' merges
    answers = [
        {"read_ok": True, "read_error": None, "count": 3, "places": [
            {"id": "ZQ", "name": "A Room", "type": "Room", "spools": [
                {"id": 1, "display": "#1 Some Brand PLA (Gold)", "color": "F9E352",
                 "color_direction": "longitudinal", "remaining_weight": 912.5}]},
            {"id": "ZQ-CT-1", "name": "A Cart", "type": "Cart", "spools": [
                {"id": 2, "display": "#2 Some Brand PETG (Red Blue)", "color": "BA0C2F,0047BB",
                 "color_direction": "coaxial", "remaining_weight": None}]},
            {"id": "Old Shelf", "name": "Old Shelf", "type": "", "spools": [
                {"id": 3, "display": "#3 Some Brand PLA (White)", "color": "FFFFFF",
                 "color_direction": "longitudinal", "remaining_weight": 19}]}]},
        {"read_ok": False, "read_error": "couldn't read Spoolman (test)", "count": 0, "places": []},
        {"read_ok": True, "read_error": None, "count": 0, "places": []},
    ]

    def _answer(route):
        route.fulfill(status=200, content_type="application/json",
                      body=_json.dumps(answers.pop(0) if len(answers) > 1 else answers[0]))
    page.route("**/api/loose_spools", _answer)
    page.goto(base_url)
    page.wait_for_function("() => typeof window.openLooseList === 'function' && typeof state !== 'undefined'")
    page.evaluate("window.openLocationsModal()")
    button = page.locator("#loc-loose-list-btn")
    expect(button).to_be_visible()
    # The guard scores a root's descendants, so the row of buttons is the root,
    # and the button is shown to be among what it scores.
    row = button.locator("..")
    assert_contrast(row)
    assert any("Loose spools" in o.get("text", "") for o in conftest.contrast_offenders(row, min_ratio=100))
    button.hover()
    assert_contrast(row)
    button.click()
    panel = page.locator("#fcc-loose-list .fcc-loose-panel")
    expect(panel.locator(".fcc-loose-row.kb-active")).to_have_count(1)
    assert_contrast(panel)
    page.keyboard.press("ArrowDown")
    assert_contrast(panel)
    page.evaluate("window.openLooseList({ host: document.getElementById('locMgrModal') })")      # the notice
    expect(panel.locator("[data-loose-notice]")).to_be_visible()
    assert_contrast(panel)
    panel.locator("[data-loose-retry]").hover()
    assert_contrast(panel)
    panel.locator("[data-loose-retry]").click()                                                 # the good empty read
    expect(panel.locator("[data-loose-state='empty']")).to_be_visible()
    assert_contrast(panel)


@pytest.mark.usefixtures("require_server")
def test_audit_panel_and_pill_are_readable(page: Page, base_url: str, assert_contrast):
    """Group 58: the audit panel had no guard. Every kind of tile, the refusal
    notice, the note, the buttons, and the pill the panel leaves behind on the
    dark page, hovered too. Read-only: the session is a sample, and the heartbeat
    is stopped so nothing closes the panel."""
    import conftest   # local: keeps this file's header out of other branches' merges
    from test_text_size_guard import SAMPLE_AUDIT, _read_only
    _read_only(page, extra_get={"/api/audit_session": SAMPLE_AUDIT})
    conftest.quiet_heartbeat(page)      # after: the newest route answers first
    page.goto(base_url)
    page.wait_for_function("() => typeof window.openAuditPanel === 'function' && typeof state !== 'undefined'")
    page.evaluate("() => { state.auditActive = true; window.updateAuditVisuals(); }")
    panel = page.locator("#fcc-audit-panel-overlay")
    expect(panel.locator("#fcc-audit-panel-done")).to_be_visible()
    page.evaluate("() => window.auditPanelNotice('Already auditing LR-MDB-1. Finish first!')")
    assert_contrast(panel)
    scored = " ".join(o.get("text", "") for o in conftest.contrast_offenders(panel, min_ratio=100))
    for words in ("Already auditing", "is filed here", "Extra (found here", "Loaded from here", "#134", "#242",
                  "LR-MDB-2 slot 3", "on XL-4", "extra", "loaded", "scanned", "Asks before moving",
                  "Ends it, nothing moves", "clears itself",
                  # Group 58.2: the Last found strip and what a tile says about a label.
                  "Last found", "#57 is marked: it needs a label", "undo that", "Needs a label", "Scan to mark it",
                  "found, no label read", "needs a label", "label status unknown", "No label to scan?",
                  # Derek's answers of 2026-11-03: a tile's QR (its badge under its name), an
                  # Extra taken back, the strip's 🖨️ and 🔎 Find a spool.
                  "or scan its QR", "not scanned", "Not here after all?", "Add to print queue", "Find a spool",
                  # His second look (sample 5a(i)): the spools still to find first, each group headed;
                  # the Last found box's "↩ Put back" (P7).
                  "Not scanned (1)", "Found (2)", "Put back"):
        assert words in scored, (words, scored)
    # The tile with a QR: the QR's white box holds no text, and its badge moved under the name.
    assert panel.locator("[data-audit-tile='99'] .fcc-audit-tile-qr").count() == 1
    panel.locator("#fcc-audit-label-undo").hover()
    page.wait_for_timeout(200)          # Bootstrap's colour transition
    assert_contrast(panel)
    panel.locator("#fcc-audit-put-back").hover()   # his second look (P7): the box's "↩ Put back"
    page.wait_for_timeout(200)
    assert_contrast(panel)
    # The strip's 🖨️ (2026-11-03, B), for #57, flagged here: under the mouse, then once the
    # label is queued, when it says so and its hover looks like no press. The queue's own
    # 2 s read is answered here with the same queue, so dev's can't change it.
    import json
    panel.locator("#fcc-audit-label-queue").hover()
    page.wait_for_timeout(200)
    assert_contrast(panel)
    queued = [{"id": 57, "type": "spool", "display": "#57"}]
    page.route("**/api/state/queue", lambda route: route.fulfill(
        status=200, content_type="application/json", body=json.dumps(queued) if route.request.method == "GET" else "{}"))
    page.mouse.move(0, 0)
    page.evaluate("(q) => { window.labelQueue.push(q); window.updateQueueUI(); }", queued[0])
    expect(panel.locator("#fcc-audit-label-queue")).to_contain_text("In the print queue")
    assert_contrast(panel)
    panel.locator("#fcc-audit-label-queue").hover()
    page.wait_for_timeout(200)
    assert_contrast(panel)
    page.mouse.move(0, 0)
    # The strip's other lines are that one's own element and class; each is drawn here.
    for line, row in (("No label was read for #99", {"id": 99, "label_read": False, "flagged_here": False, "label_status": None}),
                      ("#100 is still flagged for a new label", {"id": 100, "label_read": True, "flagged_here": False, "label_status": True}),
                      ("#134's label was read", {"id": 134, "label_read": True, "flagged_here": False, "label_status": False}),
                      # Group 58's review: what a spool off the list is, on the same line.
                      ("Extra: FCC has #134 at LR-MDB-2 slot 3", {"id": 134, "label_read": True, "flagged_here": False,
                                                                  "label_status": False, "rogue": True, "where": "LR-MDB-2 slot 3"}),
                      ("#242 is loaded on XL-4 from here", {"id": 242, "label_read": False, "flagged_here": False,
                                                            "label_status": None, "trail": True, "where": "XL-4"})):
        sample = dict(SAMPLE_AUDIT, last_found=dict(SAMPLE_AUDIT["last_found"], **row))
        page.evaluate("(s) => { const plain = window.fetchT; window.fetchT = (u, ...r) => String(u).includes('/api/audit_session')"
                      " ? Promise.resolve({ json: () => Promise.resolve(s) }) : plain(u, ...r); window.refreshAuditSession(); }", sample)
        expect(panel.locator("#fcc-audit-last-found [role=status]")).to_contain_text(line)
        assert_contrast(panel)
    # Every button that changes colour under the mouse, and a tile of each kind you can
    # press: a tile's hover is a filter, and a brighter one would lift its dark band under
    # its light text. The guard reads brightness() (test_contrast_guard_compositing.py,
    # and test_audit_panel_58_js.py on a real tile).
    for hovered in ("#fcc-audit-panel-needlabel", "#fcc-audit-panel-done", "#fcc-audit-panel-cancel",
                    "#fcc-audit-panel-close", "[data-audit-tile='99']", "[data-audit-tile='57']",
                    # 2026-11-03: an Extra's tile is a button now, and the panel's 🔎.
                    "[data-audit-tile='134']", "#fcc-audit-panel-find",
                    # His second look (section H, (a)): a found tile's own 🏷️, marked here
                    # (#57, yellow with the tag on its dark backing) and not (#100, #134).
                    "[data-audit-tag='57']", "[data-audit-tag='100']", "[data-audit-tag='134']"):
        panel.locator(hovered).hover()
        page.wait_for_timeout(200)      # Bootstrap's colour transition
        assert_contrast(panel)
    # And a 🏷️ on a spool flagged before the audit: its dashed yellow edge.
    flagged = dict(SAMPLE_AUDIT, expected=[dict(r, label_status=True, flagged_here=False) if r["id"] == 100 else r
                                           for r in SAMPLE_AUDIT["expected"]])
    page.evaluate("(s) => { const plain = window.fetchT; window.fetchT = (u, ...r) => String(u).includes('/api/audit_session')"
                  " ? Promise.resolve({ json: () => Promise.resolve(s) }) : plain(u, ...r); window.refreshAuditSession(); }", flagged)
    expect(panel.locator("[data-audit-tag='100'][data-audit-tag-state='flagged']")).to_have_count(1)
    assert_contrast(panel)
    panel.locator("[data-audit-tag='100']").hover()
    page.wait_for_timeout(200)
    assert_contrast(panel)
    page.mouse.move(0, 0)
    # The Last found box with no spool in it, others found: "Nothing is selected" (P2, P7).
    page.evaluate("(s) => { const plain = window.fetchT; window.fetchT = (u, ...r) => String(u).includes('/api/audit_session')"
                  " ? Promise.resolve({ json: () => Promise.resolve(s) }) : plain(u, ...r); window.refreshAuditSession(); }",
                  dict(SAMPLE_AUDIT, last_found=None))
    expect(panel.locator("#fcc-audit-last-none")).to_contain_text("Nothing is selected")
    assert_contrast(panel)
    page.keyboard.press("Escape")
    pill = page.locator("#fcc-audit-pill")
    expect(pill).to_be_visible()
    assert_contrast(pill)
    assert "audit: LR-MDB-1" in " ".join(o.get("text", "") for o in conftest.contrast_offenders(pill, min_ratio=100))
    pill.hover()
    assert_contrast(pill)


@pytest.mark.usefixtures("require_server")
def test_audit_find_window_is_readable(page: Page, base_url: str, assert_contrast):
    """Derek's answers of 2026-11-03, A2: 🔎 Find a spool over the audit panel. Its box and
    hint, each kind of row (every "where", both tags) with the highlighted one and a
    hovered one, the panel's refusal said on it, "Searching…" over older rows (review of
    7e3720f, P-7), a failed search with Try again hovered, and "No spool matches". The session and the search are the routes' shapes, served to
    this browser alone; nothing is picked."""
    import conftest   # local: keeps this file's header out of other branches' merges
    from test_audit_find_and_tiles_58_js import SEARCH_ROWS
    from test_text_size_guard import SAMPLE_AUDIT, _read_only
    _read_only(page, extra_get={"/api/audit_session": SAMPLE_AUDIT,
                                "/api/search": {"success": True, "results": SEARCH_ROWS}})
    conftest.quiet_heartbeat(page)      # after: the newest route answers first
    page.goto(base_url)
    page.wait_for_function("() => typeof window.openAuditFind === 'function' && typeof state !== 'undefined'")
    page.evaluate("() => { state.auditActive = true; window.updateAuditVisuals(); }")
    panel = page.locator("#fcc-audit-panel-overlay")
    expect(panel.locator("#fcc-audit-panel-done")).to_be_visible()
    panel.locator("#fcc-audit-panel-find").click()
    find = page.locator("#fcc-audit-find")
    expect(find.locator("[data-find-box]")).to_be_focused()
    assert_contrast(find)
    scored = " ".join(o.get("text", "") for o in conftest.contrast_offenders(find, min_ratio=100))
    for words in ("Find a spool", "A spool here with no label", "Type a name, colour, brand or number.", "Esc closes"):
        assert words in scored, (words, scored)
    find.locator("[data-find-box]").fill("glow")
    expect(find.locator(".fcc-find-row")).to_have_count(len(SEARCH_ROWS))
    page.keyboard.press("ArrowDown")                 # the highlighted row, with the keyboard on it
    page.evaluate("() => window.auditPanelNotice('Already auditing LR-MDB-1. Finish first!')")
    assert_contrast(find)
    scored = " ".join(o.get("text", "") for o in conftest.contrast_offenders(find, min_ratio=100))
    for words in ("#99 Some Brand PLA (Glow Blue)", "📍 LR-MDB-1 slot 2", "on the list", "✅ found",
                  "🔗 loaded from LR-MDB-2 slot 4", "❓ Lost: CR-CT-1 slot 2", "Unassigned", "Already auditing"):
        assert words in scored, (words, scored)
    find.locator(".fcc-find-row[data-find-id='200']").hover()
    page.wait_for_timeout(200)
    assert_contrast(find)
    # A newer search on its way over the older rows: "Searching…" at the box's end (review
    # of 7e3720f, P-7). Its answer never comes here.
    page.mouse.move(0, 0)
    page.evaluate("() => { const plain = window.fetchT; window.fetchT = (u, ...r) => String(u).includes('/api/search')"
                  " ? new Promise(() => {}) : plain(u, ...r); }")
    find.locator("[data-find-box]").fill("glow blue")
    expect(find.locator("[data-find-busy]")).to_have_text("Searching…")
    assert_contrast(find)
    assert "Searching…" in " ".join(o.get("text", "") for o in conftest.contrast_offenders(find, min_ratio=100))
    # A failed search, and one that matches nothing.
    page.evaluate("() => { const plain = window.fetchT; window.fetchT = (u, ...r) => String(u).includes('/api/search')"
                  " ? Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ success: false,"
                  " msg: \"Spoolman didn't answer (timed out).\" }) }) : plain(u, ...r); }")
    find.locator("[data-find-box]").fill("glow b")
    expect(find.locator("[data-find-retry]")).to_be_visible()
    find.locator("[data-find-retry]").hover()
    page.wait_for_timeout(200)
    assert_contrast(find)
    assert "Couldn't search" in " ".join(o.get("text", "") for o in conftest.contrast_offenders(find, min_ratio=100))
    page.evaluate("() => { const plain = window.fetchT; window.fetchT = (u, ...r) => String(u).includes('/api/search')"
                  " ? Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ success: true, results: [] }) })"
                  " : plain(u, ...r); }")
    page.mouse.move(0, 0)
    find.locator("[data-find-box]").fill("nothing like it")
    expect(find).to_contain_text("No spool matches")
    assert_contrast(find)
    page.keyboard.press("Escape")
    expect(find).to_have_count(0)


@pytest.mark.usefixtures("require_server")
def test_audit_panel_with_nothing_to_list_is_readable(page: Page, base_url: str, assert_contrast):
    """Group 58: the panel's plain lines, which no sample with tiles draws: before its
    first answer, before a place is scanned, and at a place with nothing filed. Each
    line is proved scored: the guard skips an element it can't read."""
    import conftest   # local: keeps this file's header out of other branches' merges
    from test_text_size_guard import _read_only, walk_empty_audit_panel
    _read_only(page)
    conftest.quiet_heartbeat(page)      # after: the newest route answers first
    page.goto(base_url)
    page.wait_for_function("() => typeof window.openAuditPanel === 'function' && typeof state !== 'undefined'")
    lines = iter(("Loading audit state", "Scan a location's label to start.", "Nothing is filed here."))

    def check(panel):
        assert_contrast(panel)
        scored = " ".join(o.get("text", "") for o in conftest.contrast_offenders(panel, min_ratio=100))
        assert next(lines) in scored, scored
    walk_empty_audit_panel(page, page.locator("#fcc-audit-panel-overlay"), check)


@pytest.mark.usefixtures("require_server")
@pytest.mark.parametrize("size", ["Standard", "Extra Large"])
def test_audit_done_question_is_readable(page: Page, base_url: str, assert_contrast, size):
    """Group 58: Done's question over the panel: its two lists, each line's reason, "and
    N more", the hold-off's line, the QR captions in the buttons' tones, and the
    panel's Loose spools button, hovered. Drawn from the route's shape with nothing
    sent, and answered with Escape."""
    import conftest   # local: keeps this file's header out of other branches' merges
    from test_text_size_guard import SAMPLE_AUDIT, SAMPLE_QUESTION, _read_only
    page.add_init_script("(() => { try { localStorage.setItem('fcc.textSize', %r); } catch (e) {} })();" % size)
    _read_only(page, extra_get={"/api/audit_session": SAMPLE_AUDIT})
    conftest.quiet_heartbeat(page)      # after: the newest route answers first
    page.goto(base_url)
    page.wait_for_function("() => typeof window.askAuditDone === 'function' && typeof state !== 'undefined'")
    page.evaluate("() => { state.auditActive = true; window.updateAuditVisuals(); }")
    panel = page.locator("#fcc-audit-panel-overlay")
    expect(panel.locator("#fcc-audit-panel-done")).to_be_visible()
    assert_contrast(panel)
    assert "Loose spools" in " ".join(o.get("text", "") for o in conftest.contrast_offenders(panel, min_ratio=100))
    panel.locator("#fcc-audit-panel-loose").hover()
    page.wait_for_timeout(200)          # Bootstrap's colour transition
    assert_contrast(panel)
    page.mouse.move(0, 0)
    page.evaluate("(q) => window.askAuditDone(q)", SAMPLE_QUESTION)
    overlay = page.locator("#fcc-audit-done-question")
    expect(overlay.locator(".fcc-confirm-qr-row")).to_be_visible()
    page.evaluate("() => window.processScan('CMD:DONE', 'barcode')")      # the hold-off's line
    expect(overlay.locator(".fcc-apc-status")).to_be_visible()
    assert_contrast(overlay)
    scored = " ".join(o.get("text", "") for o in conftest.contrast_offenders(overlay, min_ratio=100))
    # PIN UPDATED DELIBERATELY (Derek's C, 2026-11-03, for his look): the sample files an
    # Extra here too, so its title and its Yes say both, and its own section lists it.
    # And again (builder B, Q1): every spool a colour tile, each of the tiles' looks
    # ("missing", "extra", "stay"), the place named instead of "here", and no "and N more".
    for words in ("Park 3 at Unknown and file 1 in LR-MDB-1?", "Not scanned, to park at Unknown (3)", "Left where they are (12)",
                  "#134", "605g (slot 2)", "605g", "moved to XL-4", "no longer in Spoolman", "#253", "Do both",
                  "Back to the audit", "Answer the question", "Enter goes back",
                  "Found in LR-MDB-1, FCC had it elsewhere (1)", "#500", "from LR-MDB-2 slot 3"):
        assert words in scored, (words, scored)
    assert "more" not in scored
    assert overlay.locator(".fcc-spool-tile").count() == 16
    # Its lists scrolled to their end, when they scroll: the last tiles under the frame.
    overlay.locator(".fcc-apc-sections").evaluate("(b) => { b.scrollTop = b.scrollHeight; }")
    assert_contrast(overlay)
    assert sum("SCAN" in t.upper() for t in [o["text"] for o in conftest.contrast_offenders(overlay, min_ratio=100)]) >= 2
    page.keyboard.press("Escape")
    expect(overlay).to_have_count(0)


@pytest.mark.usefixtures("require_server")
@pytest.mark.parametrize("width, height, size", [(1600, 1300, "Standard"), (1366, 768, "Extra Large"), (390, 844, "Standard")])
def test_audit_report_window_is_readable(page: Page, base_url: str, assert_contrast, width, height, size):
    """Group 58, Derek's second look (builder B, Q2): the report window after Done's Yes,
    every kind of group and tile (each its own look), the needs-a-label tag, the foot, the
    Close hovered, and scrolled to its end where it scrolls; and the report line's 📝 Read
    the report button on the Activity Log's dark rows, hovered. Drawn from the route's
    shape (test_audit_report_window_58_js.FULL, pinned there), nothing sent."""
    import conftest   # local: keeps this file's header out of other branches' merges
    from test_audit_report_window_58_js import FULL, LOG_ROW
    from test_text_size_guard import _read_only
    page.set_viewport_size({"width": width, "height": height})
    page.add_init_script("(() => { try { localStorage.setItem('fcc.textSize', %r); } catch (e) {} })();" % size)
    _read_only(page)
    conftest.quiet_heartbeat(page)      # after: the newest route answers first
    page.goto(base_url)
    page.wait_for_function("() => typeof window.openAuditReport === 'function' && typeof state !== 'undefined'")
    page.evaluate("(r) => window.openAuditReport(r, { after: true })", FULL)
    report = page.locator("#fcc-audit-report")
    expect(report.locator("#fcc-audit-report-close")).to_be_focused()
    # Its notice line (builder B, resumed): a scan read during the park, dropped once the
    # audit was over, says so on the window, as the real queue does it.
    page.evaluate("() => window.auditScanOutlived({ text: 'ID:57', auditOf: 'boot-1' })")
    expect(report.locator("#fcc-audit-report-notice")).to_be_visible()
    # Bootstrap's colour transition, to its end (a fixed wait read it halfway on a busy run):
    # the focused Close takes its hover colours (Bootstrap 5.3's .btn:focus-visible).
    settled = "(sel) => document.querySelector(sel).getAnimations().length === 0"
    page.wait_for_function(settled, arg="#fcc-audit-report-close")
    assert_contrast(report)
    scored = " ".join(o.get("text", "") for o in conftest.contrast_offenders(report, min_ratio=100))
    for words in ("Audit Report: LR-MDB-1", "Found 2 of 6.", "Parked at Unknown (2)", "Filed in LR-MDB-1 (1)",
                  "Left where they are (2)", "Couldn't be moved (1)", "Loaded from LR-MDB-1 (1)",
                  # Review 3, R3S-5: the group and the tag say the audit marked them.
                  "Marked as needing a label (1)", "from LR-MDB-2 slot 3", "marked as needing a label", "moved to CR-CT-1", "loaded on XL-2",
                  "Its line in the Activity Log", "Close", "ID:57 did nothing"):   # R3S-6's words
        assert words in scored, (words, scored)
    report.locator("#fcc-audit-report-close").hover()
    page.wait_for_timeout(50)
    page.wait_for_function(settled, arg="#fcc-audit-report-close")
    assert_contrast(report)
    page.mouse.move(0, 0)
    page.wait_for_timeout(50)
    page.wait_for_function(settled, arg="#fcc-audit-report-close")
    report.locator(".fcc-audit-report-body").evaluate("(b) => { b.scrollTop = b.scrollHeight; }")
    assert_contrast(report)
    page.keyboard.press("Escape")
    expect(report).to_have_count(0)
    page.evaluate("(row) => window._renderLogsPayload({ logs: [row], status: { spoolman: true } }, true)", LOG_ROW)
    logs = page.locator("#live-logs")
    expect(logs.locator(".fcc-audit-report-open")).to_have_count(1)
    assert_contrast(logs)
    assert "Read the report" in " ".join(o.get("text", "") for o in conftest.contrast_offenders(logs, min_ratio=100))
    logs.locator(".fcc-audit-report-open").hover()
    page.wait_for_timeout(50)
    page.wait_for_function(settled, arg="#live-logs .fcc-audit-report-open")
    assert_contrast(logs)


@pytest.mark.usefixtures("require_server")
def test_legacy_picker_during_an_audit_is_readable(page: Page, base_url: str, assert_contrast):
    """Group 58, Derek's second look (builder B, Q3): the legacy shared-label picker over the
    audit panel, its spools under where each stands in the audit, its line naming the
    audit's place. The session is the route's shape, served to this browser alone; nothing
    is picked."""
    import conftest   # local: keeps this file's header out of other branches' merges
    from test_text_size_guard import SAMPLE_AUDIT, _read_only
    _read_only(page, extra_get={"/api/audit_session": SAMPLE_AUDIT})
    conftest.quiet_heartbeat(page)      # after: the newest route answers first
    page.goto(base_url)
    page.wait_for_function("() => typeof window.showLegacySpoolPicker === 'function' && typeof state !== 'undefined'")
    page.evaluate("() => { state.auditActive = true; window.updateAuditVisuals(); }")
    expect(page.locator("#fcc-audit-panel-tally")).to_contain_text("Auditing LR-MDB-1")
    page.evaluate("""() => { const spool = (id, at) => ({ id, remaining_weight: 800, location: at, archived: false,
            filament_id: 7, filament_name: 'Contrast Black', material: 'PLA', vendor_name: 'FCC Test', display: '#' + id });
        window.showLegacySpoolPicker({ legacy_id: '999120', candidates: [spool(99, 'LR-MDB-1'), spool(57, 'LR-MDB-1'),
            spool(134, 'LR-MDB-2'), spool(242, 'XL-4'), spool(999135, 'ZZ-CONTRAST-1')] }); }""")
    picker = page.locator("#fcc-legacy-picker-overlay")
    expect(picker.locator("#fcc-legacy-picker-audit")).to_be_visible()
    assert picker.locator("optgroup").count() == 5
    assert_contrast(picker)
    scored = " ".join(o.get("text", "") for o in conftest.contrast_offenders(picker, min_ratio=100))
    assert "The audit of" in scored and "LR-MDB-1" in scored, scored
    page.click("#fcc-legacy-picker-cancel")


@pytest.mark.usefixtures("require_server")
def test_lost_spools_are_readable(page: Page, base_url: str, assert_contrast):
    """Group 58: a lost spool's badge on the buffer card (over its filament's colours),
    on the search card, and the sentence in the spool window. Read-only: the spool is a
    sample of the routes' shape, and the buffer is this page's own."""
    import conftest   # local: keeps this file's header out of other branches' merges
    from test_text_size_guard import SAMPLE_LOST, SAMPLE_LOST_DETAILS, _read_only, draw_lost_cards
    _read_only(page, extra_get={"/api/spool_details": SAMPLE_LOST_DETAILS})
    conftest.own_the_buffer(page, [SAMPLE_LOST])    # after: the newest route answers first
    page.goto(base_url)
    page.wait_for_function("() => typeof window.openLooseList === 'function' && state.heldSpools.length === 1")
    card = page.locator(f".buffer-item[data-spool-id='{SAMPLE_LOST['id']}']")
    badge = card.locator(".badge.bg-warning").first
    expect(badge).to_have_text("❓ Lost: LR-MDB-1 slot 2")
    assert_contrast(card)
    assert any("Lost: LR-MDB-1 slot 2" in o.get("text", "") for o in conftest.contrast_offenders(card, min_ratio=100))
    cards = draw_lost_cards(page)       # the search card and the Unknown list's
    assert_contrast(cards)
    scored = [o.get("text", "") for o in conftest.contrast_offenders(cards, min_ratio=100)]
    assert sum("Lost: LR-MDB-1 slot 2" in text for text in scored) == 2, scored
    cards.evaluate("(box) => box.remove()")
    page.evaluate("(sid) => { openSpoolDetails(sid); }", SAMPLE_LOST["id"])
    window_badge = page.locator("#detail-location-badge")
    expect(window_badge).to_have_text("❓ Marked lost by the audit of LR-MDB-1 slot 2 on 2026-11-01")
    row = window_badge.locator("..")    # the guard scores a root's descendants
    assert_contrast(row)
    assert any("Marked lost" in o.get("text", "") for o in conftest.contrast_offenders(row, min_ratio=100))


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
def test_load_report_with_its_lens_on_a_dark_backing_is_readable(page: Page, base_url: str, assert_contrast):
    """Group 58, Derek's second look (2026-11-03, sample 4(ii)): the 🔎 on the cyan Load
    report (Settings -> Filament Attributes) sits on a small dark round backing, as the 🏷️
    on Needs a label does. Its words are judged, at rest and hovered. Read-only: Settings is
    opened and closed, nothing is loaded. PIN UPDATED DELIBERATELY (review 3, Derek
    2026-11-04): the magnifier on the backing is drawn, an SVG with no text node for this
    guard to judge, so the backing holds no text; each colour the drawing paints stands out
    from the backing by 3:1 at least (WCAG's rule for a graphic), pinned by
    test_icon_on_dark_circle_js.py::test_each_drawn_colour_stands_out_from_the_backing."""
    import conftest
    page.goto(base_url)
    page.wait_for_function("() => typeof window.openConfigModal === 'function'")
    page.evaluate("() => window.openConfigModal()")
    button = page.locator("#btn-config-attrs-scan")
    expect(button).to_be_visible(timeout=15000)
    header = page.locator("#config-sections .card-header", has=button)
    assert_contrast(header)
    scored = [o["text"] for o in conftest.contrast_offenders(header, min_ratio=100)]
    assert any("Load report" in t for t in scored), scored
    assert button.locator(".fcc-ico-on-light > svg.fcc-ico-svg").count() == 1
    assert button.locator(".fcc-ico-on-light").evaluate("(e) => e.textContent") == ""
    button.hover()
    page.wait_for_timeout(200)          # Bootstrap's colour transition
    assert_contrast(header)


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


# The coloured dialog headers (Group 58, builder B, Q4). global.css's `.modal-title`
# cyan beat each header's own text colour: on #confirmModal's yellow (every Undo Last
# Move and "Clear entire Buffer?" question) 1.09:1, on the 🧵 Multi-Spool Search's cyan,
# and on the red of the safety interlock and "Clear Queue?". Each opened as the page
# opens it (the gating dialogs through their helpers), scored from its .modal-content
# (the guard scores descendants), and closed on its safe answer. Nothing is written.
# The safety interlock's header only: its message, Bootstrap's danger red on the dark
# body, is 3.84:1 (28 px bold, which WCAG's large-text 3:1 lets pass and FCC's 4.5 rule
# doesn't), a red Derek chose, left for him (builder B's open question).
COLOURED_HEADERS = {
    "confirmModal": ("() => requestConfirmation('Clear entire Buffer?', () => {})", "() => confirmAction(false)",
                     ".modal-content", ["Confirmation", "Clear entire Buffer?"]),
    "safetyModal": ("() => promptSafety('A probe of the header?', () => {})", "() => confirmSafety(false)",
                    ".modal-header", ["SAFETY INTERLOCK"]),
    "multiSpoolModal": ("() => bootstrap.Modal.getOrCreateInstance(document.getElementById('multiSpoolModal')).show()",
                        "() => bootstrap.Modal.getInstance(document.getElementById('multiSpoolModal')).hide()",
                        ".modal-content", ["Multi-Spool Search", "Add All to Queue"]),
    "clearQueueConfirmModal": (
        "() => bootstrap.Modal.getOrCreateInstance(document.getElementById('clearQueueConfirmModal')).show()",
        "() => bootstrap.Modal.getInstance(document.getElementById('clearQueueConfirmModal')).hide()",
        ".modal-content", ["Clear Queue?", "Are you sure"]),
}


def _show_dialog(page: Page, modal_id: str, opener: str):
    """`opener` run, and Bootstrap's shown.bs.modal waited for."""
    page.evaluate("""(id) => { window.__shown = window.__shown || {}; window.__shown[id] = false;
        document.getElementById(id).addEventListener('shown.bs.modal', () => { window.__shown[id] = true; }, { once: true }); }""",
                  modal_id)
    page.evaluate(opener)
    page.wait_for_function("(id) => window.__shown[id] === true", arg=modal_id, timeout=10_000)


@pytest.mark.usefixtures("require_server")
@pytest.mark.parametrize("modal_id", list(COLOURED_HEADERS))
def test_a_coloured_dialog_header_is_readable(page: Page, base_url: str, assert_contrast, modal_id):
    """RED on 1ad5de6: each title was the app-wide cyan on its header (1.09, 2.56, 1.11
    and 2.56:1). Now #confirmModal's header is dark with a yellow title (Derek's (b)), and
    every other coloured header's title takes the text colour its own markup names."""
    import conftest   # local: keeps this file's header out of other branches' merges
    from test_text_size_guard import _read_only
    opener, closer, root, words = COLOURED_HEADERS[modal_id]
    _read_only(page)
    conftest.quiet_heartbeat(page)      # after: the newest route answers first
    page.goto(base_url)
    page.wait_for_function("() => typeof requestConfirmation === 'function' && typeof bootstrap !== 'undefined'")
    _show_dialog(page, modal_id, opener)
    content = page.locator(f"#{modal_id} {root}")
    assert_contrast(content)
    scored = " ".join(o.get("text", "") for o in conftest.contrast_offenders(content, min_ratio=100))
    for word in words:
        assert word in scored, (word, scored)
    page.evaluate(closer)
    conftest.wait_modal_settled(page, modal_id)


@pytest.mark.usefixtures("require_server")
def test_the_confirm_header_is_dark_with_a_thick_yellow_line_and_a_bigger_yellow_title(page: Page, base_url: str):
    """Derek, 2026-11-03: (b), a dark header with a yellow title, "but A is functional and
    reads more like a warning because of the yellow used ... easier to scan and work with
    if the laptop doing the work is a bit of distance away": so a thicker yellow line under
    it and a bigger title. The ⚠️ on dark needs no backing."""
    import conftest   # local: keeps this file's header out of other branches' merges
    from test_text_size_guard import _read_only
    _read_only(page)
    conftest.quiet_heartbeat(page)
    page.goto(base_url)
    page.wait_for_function("() => typeof requestConfirmation === 'function' && typeof bootstrap !== 'undefined'")
    _show_dialog(page, "confirmModal", COLOURED_HEADERS["confirmModal"][0])
    look = page.evaluate("""() => {
        const head = document.querySelector('#confirmModal .modal-header');
        const title = head.querySelector('.modal-title');
        const h = getComputedStyle(head), t = getComputedStyle(title);
        return { bg: h.backgroundColor, line: parseFloat(h.borderBottomWidth), lineColour: h.borderBottomColor,
                 lineStyle: h.borderBottomStyle, colour: t.color, px: parseFloat(t.fontSize),
                 plainH5: parseFloat(getComputedStyle(document.documentElement).fontSize) * 1.25,
                 backing: !!title.querySelector('.fcc-ico-on-light') }; }""")
    assert look["bg"] == "rgb(43, 43, 43)", look                    # #2b2b2b, FCC's dark dialog header
    assert look["line"] >= 4 and look["lineStyle"] == "solid" and look["lineColour"] == "rgb(255, 193, 7)", look
    assert look["colour"] == "rgb(255, 193, 7)", look               # Bootstrap's warning yellow
    assert look["px"] >= look["plainH5"] * 1.25, look               # a quarter bigger than an h5, at least
    assert look["backing"] is False, look
    page.evaluate(COLOURED_HEADERS["confirmModal"][1])
    conftest.wait_modal_settled(page, "confirmModal")


@pytest.mark.usefixtures("require_server")
def test_the_wizards_price_from_the_filament_is_readable(page: Page, base_url: str, assert_contrast):
    """Group 54.8: a new spool of a filament priced 25 shows the filament's price
    marked "↩ from filament", in the Pricing & Metadata section's summary and beside
    Price Paid once the section is open. The filament is a stub, every write is
    answered in the browser, and nothing is saved. Each root is scored from its
    parent (the guard scores descendants only), and the mark is proved scored."""
    import conftest   # local: keeps this file's header out of other branches' merges
    from test_text_size_guard import _read_only
    filament = {"id": 9002, "name": "Ocean Blue", "material": "PLA", "color_hex": "1E6FD9", "weight": 1000.0,
                "spool_weight": 200.0, "price": 25.0, "extra": {},
                "vendor": {"id": 9003, "name": "Example Brand", "extra": {}}}
    _read_only(page, extra_get={"/api/filament_details": filament})
    page.goto(base_url)
    page.wait_for_function("() => typeof window.openNewSpoolFromFilamentWizard === 'function'"
                           " && typeof state !== 'undefined' && state.locationsLoaded", timeout=45_000)
    page.evaluate("() => { window.openNewSpoolFromFilamentWizard(9002); }")
    page.wait_for_function("() => document.getElementById('wiz-status-msg').innerText.includes('pre-filled')"
                           " && document.getElementById('wiz-spool-price').value === '25'", timeout=15_000)
    conftest.wait_modal_settled(page, "wizardModal")
    toggle = page.locator('button.fcc-wiz-section-toggle[data-bs-target="#wiz-spool-metadata-panel"]')
    expect(toggle.locator(".fcc-wiz-section-summary")).to_have_text("$25 ↩ from filament")
    # The toggle's ▾ is left out: a state glyph, not text (#6c757d on #1a1a1a, 3.71:1,
    # over WCAG's 3:1 for a control's parts), and older than 54.8.
    offenders = [o for o in conftest.contrast_offenders(toggle)
                 if "fcc-wiz-section-chevron" not in (o.get("className") or "")]
    assert offenders == [], offenders
    scored = [o.get("text") for o in conftest.contrast_offenders(toggle, min_ratio=100)]
    assert "↩ from filament" in scored and any(t.startswith("$25") for t in scored), scored
    page.evaluate("() => bootstrap.Collapse.getOrCreateInstance("
                  "document.getElementById('wiz-spool-metadata-panel'), { toggle: false }).show()")
    badge = page.locator("#wiz-spool-price-inherited-badge")
    expect(badge).to_be_visible()
    column = badge.locator("xpath=ancestor::div[contains(@class, 'col-md-4')][1]")
    assert_contrast(column)
    assert any(o.get("id") == "wiz-spool-price-inherited-badge"
               for o in conftest.contrast_offenders(column, min_ratio=100)), "the price's badge was never scored"
    conftest.close_wizard(page)


def test_the_wizards_tare_from_the_filament_is_readable(page: Page, base_url: str):
    """Group 54 review (L1): a new spool of a filament with a 200 g empty weight shows
    "tare 200g ↩ from filament" in the closed Weight & Scale summary, in the price
    summary's look (the same colours, scored here too). The filament is a stub, every
    write is answered in the browser, and nothing is saved. The summary is scored from
    its toggle (the guard scores descendants only), and the mark is proved scored."""
    import conftest   # local: keeps this file's header out of other branches' merges
    from test_text_size_guard import _read_only
    filament = {"id": 9002, "name": "Ocean Blue", "material": "PLA", "color_hex": "1E6FD9", "weight": 1000.0,
                "spool_weight": 200.0, "price": 25.0, "extra": {},
                "vendor": {"id": 9003, "name": "Example Brand", "extra": {}}}
    _read_only(page, extra_get={"/api/filament_details": filament})
    page.goto(base_url)
    page.wait_for_function("() => typeof window.openNewSpoolFromFilamentWizard === 'function'"
                           " && typeof state !== 'undefined' && state.locationsLoaded", timeout=45_000)
    page.evaluate("() => { window.openNewSpoolFromFilamentWizard(9002); }")
    page.wait_for_function("() => document.getElementById('wiz-status-msg').innerText.includes('pre-filled')"
                           " && document.getElementById('wiz-spool-empty_weight').value === '200'", timeout=15_000)
    conftest.wait_modal_settled(page, "wizardModal")
    toggle = page.locator('button.fcc-wiz-section-toggle[data-bs-target="#wiz-spool-weight-panel"]')
    expect(toggle.locator(".fcc-wiz-section-summary")).to_have_text("tare 200g ↩ from filament")
    # The toggle's ▾ is left out, as in the price case: a state glyph, older than 54.
    offenders = [o for o in conftest.contrast_offenders(toggle)
                 if "fcc-wiz-section-chevron" not in (o.get("className") or "")]
    assert offenders == [], offenders
    scored = [o.get("text") for o in conftest.contrast_offenders(toggle, min_ratio=100)]
    assert "↩ from filament" in scored and any(t.startswith("tare 200g") for t in scored), scored
    conftest.close_wizard(page)


def test_the_empty_weight_prompts_notice_is_readable(page: Page, base_url: str):
    """Group 54 review R5-1: the post-archive empty-weight prompt can carry a notice
    (the weigh page's "Spool #99 is archived but still at …", which the prompt
    would otherwise hide under it): its alert line in the prompt's own yellow label
    look, on the prompt's dark ground. The filament is a stub, every write is
    answered in the browser, and nothing is saved. Scored from the dialog (the
    guard scores descendants only), and the notice is proved scored."""
    import conftest   # local: keeps this file's header out of other branches' merges
    from test_text_size_guard import _read_only
    filament = {"id": 9004, "name": "Ocean Blue", "material": "PLA", "spool_weight": None,
                "vendor": {"id": 9005, "name": "Example Brand", "empty_spool_weight": None}}
    _read_only(page, extra_get={"/api/filament_details": filament})
    page.goto(base_url)
    page.wait_for_function("() => typeof window.showArchiveEmptyWeightPrompt === 'function'"
                           " && typeof state !== 'undefined' && state.locationsLoaded", timeout=45_000)
    page.evaluate("() => { window.showArchiveEmptyWeightPrompt(99, 9004, null,"
                  " { notice: \"Spool #99 is archived but still at Shelf 1: FCC couldn't take it off there.\" }); }")
    notice = page.locator("#fcc-archive-empty-overlay #fcc-archive-empty-notice")
    expect(notice).to_be_visible()
    dialog = page.locator("#fcc-archive-empty-overlay [data-fcc-weight-keys]")
    offenders = [o for o in conftest.contrast_offenders(dialog) if "still at Shelf 1" in (o.get("text") or "")]
    assert offenders == [], offenders
    scored = [o.get("text") for o in conftest.contrast_offenders(dialog, min_ratio=100)]
    assert any("still at Shelf 1" in (t or "") for t in scored), scored
    page.locator("#fcc-archive-later").click()


@pytest.mark.usefixtures("require_server")
def test_the_in_app_help_is_readable(page: Page, base_url: str, assert_contrast):
    """Group 55.3: a dialog's ? button (white on FCC's dark header) and the help it opens
    (its lines, its section title, its keys, All shortcuts), over a toolhead's window, whose
    help has its Quick-Swap part and keys (Group 55 review, R3-5: a dryer box's help has
    neither, so they were never scored). Every write is answered in the browser. Each part
    is proved scored: the guard scores descendants only, so the header is the root."""
    import conftest   # local: keeps this file's header out of other branches' merges
    from test_text_size_guard import _read_only
    _read_only(page)
    page.goto(base_url)
    page.wait_for_function(
        "() => typeof state === 'object' && Array.isArray(state.allLocations) && state.allLocations.length > 0",
        timeout=15_000)
    # A toolhead a dryer box slot feeds, so its window has the Quick-Swap grid.
    head = page.evaluate("""() => {
        for (const r of state.allLocations) {
            const t = (r && r.extra && r.extra.slot_targets) || {};
            for (const v of Object.values(t)) {
                const h = state.allLocations.find((x) => x.LocationID === v);
                if (h && window.isToolheadType(h.Type)) return h.LocationID;
            }
        }
        return null;
    }""")
    if not head:
        pytest.skip("no dryer box slot on dev feeds a toolhead")
    page.evaluate("(id) => window.openManage(id)", head)
    expect(page.locator("#manageModal")).to_be_visible(timeout=8000)
    page.wait_for_function("() => document.querySelectorAll('#quickswap-grid .fcc-qs-slot').length > 0", timeout=10_000)
    header = page.locator("#manageModal .modal-header")
    assert_contrast(header)
    scored = [o.get("text") for o in conftest.contrast_offenders(header, min_ratio=100)]
    assert "?" in scored, scored
    page.locator('#manageModal [data-fcc-help="location-window"]').click()
    overlay = page.locator("#fcc-shortcuts-overlay")
    expect(page.locator("#fcc-help-view .fcc-help-sub")).to_be_visible()
    assert_contrast(overlay)
    scored = " ".join(o.get("text") or "" for o in conftest.contrast_offenders(overlay, min_ratio=100))
    for words in ("Quick-Swap (a toolhead or a printer)", "Put the keyboard on the Quick-Swap grid", "All shortcuts"):
        assert words in scored, (words, scored[:400])


def _the_question_mark_is_scored(conftest, root):
    scored = [o.get("text") for o in conftest.contrast_offenders(root, min_ratio=100)]
    assert "?" in scored, scored


@pytest.mark.usefixtures("require_server")
@pytest.mark.parametrize("modal_id", ["locMgrModal", "spoolModal", "filamentModal", "wizardModal",
                                      "weighOutModal", "queueModal", "backlogModal"])
def test_each_windows_help_button_is_readable(page: Page, base_url: str, assert_contrast, modal_id):
    """Group 55.3: every daily window's ? in its header, plain and hovered: white on FCC's
    dark headers, dark on the Print Queue's yellow (global.css). Opened as the browser
    tests open them; every write is answered in the browser."""
    import conftest   # local: keeps this file's header out of other branches' merges
    from test_in_app_help_55_e2e import WINDOWS
    from test_text_size_guard import _read_only
    opener = {w[0]: w[2] for w in WINDOWS}[modal_id]
    _read_only(page)
    page.goto(base_url)
    page.wait_for_function(
        "() => typeof state === 'object' && typeof bootstrap !== 'undefined' && typeof window.openHelp === 'function'",
        timeout=15_000)
    if page.evaluate(opener) is False:
        pytest.skip(f"dev's search found nothing to show in #{modal_id}")
    expect(page.locator(f"#{modal_id}")).to_be_visible(timeout=10_000)
    conftest.wait_modal_settled(page, modal_id)
    header = page.locator(f"#{modal_id} .modal-header")
    assert_contrast(header)
    _the_question_mark_is_scored(conftest, header)
    header.locator("[data-fcc-help]").hover()
    page.wait_for_timeout(200)
    assert_contrast(header)
    page.mouse.move(0, 0)


@pytest.mark.usefixtures("require_server")
def test_the_help_buttons_scripts_draw_are_readable(page: Page, base_url: str, assert_contrast):
    """Group 55.3: the move question's ? (top right of its panel), the Quick-Weigh's
    (beside its ×) and the box picker's (beside its ✕), each scored on its own dark
    surface. Nothing is sent: the question's answers are local, the Quick-Weigh's spool
    is made up, and the picker only reads and is cancelled."""
    import json as _json
    import conftest   # local: keeps this file's header out of other branches' merges
    from test_in_app_help_55_e2e import THREE_WAY_JS
    from test_text_size_guard import _read_only
    spool = {"id": 9061, "initial_weight": 1000, "used_weight": 200, "spool_weight": 200, "archived": False,
             "filament": {"id": 9062, "name": "Help Test", "material": "PLA", "weight": 1000,
                          "spool_weight": 200, "color_hex": "336699", "vendor": {"id": 9063, "name": "Example"}}}
    _read_only(page, extra_get={"/api/spool_details": spool})
    page.goto(base_url)
    page.wait_for_function(
        "() => typeof window.confirmActivePrint === 'function' && typeof window.fccHelpKeyForOverlayId === 'function'"
        " && typeof state === 'object' && Array.isArray(state.allLocations) && state.allLocations.length > 0",
        timeout=15_000)
    page.evaluate(THREE_WAY_JS)
    question = page.locator("#fcc-active-print-confirm-overlay")
    expect(question.locator("[data-fcc-help]")).to_be_visible()
    assert_contrast(question)
    _the_question_mark_is_scored(conftest, question)
    page.keyboard.press("Escape")
    expect(question).to_have_count(0)
    # The Quick-Swap question's (Group 55 review, R4-3), on a made-up tile: nothing is answered.
    page.evaluate("""() => { const b = document.createElement('button');
        Object.assign(b.dataset, { toolhead: 'HEAD-1', box: 'DRYBOX-1', slot: '2', spoolLabel: '#42 Example PLA' });
        window.quickSwapTap(b); }""")
    swap = page.locator("#fcc-quickswap-confirm-overlay")
    expect(swap.locator("[data-fcc-help]")).to_be_visible(timeout=10_000)
    _the_question_mark_is_scored(conftest, swap)
    assert not [o for o in conftest.contrast_offenders(swap) if (o.get("text") or "").strip() == "?"]
    page.keyboard.press("Escape")
    expect(swap).to_have_count(0)
    page.evaluate("() => window.openQuickWeigh(9061)")
    weigh = page.locator("#fcc-weight-entry-overlay")
    expect(weigh.locator("[data-fcc-help]")).to_be_visible(timeout=10_000)
    _the_question_mark_is_scored(conftest, weigh)
    assert not [o for o in conftest.contrast_offenders(weigh) if (o.get("text") or "").strip() == "?"]
    page.keyboard.press("Escape")
    expect(weigh).to_have_count(0)
    box = page.evaluate("""() => { const r = state.allLocations.find((x) => x.Type === 'Dryer Box'
        && parseInt(x['Max Spools'], 10) > 1); return r && r.LocationID; }""")
    if not box:
        pytest.skip("dev has no dryer box with slots to open the picker on")
    page.evaluate("(loc) => { window.openSlotPicker({ location: loc, spool: 1 }); }", box)
    head = page.locator("#fcc-slot-picker .card-header")
    expect(head.locator("[data-fcc-help]")).to_be_visible(timeout=10_000)
    page.wait_for_selector("#fcc-slot-picker .fcc-sp-tile", timeout=15_000)
    assert_contrast(head)
    _the_question_mark_is_scored(conftest, head)
    page.keyboard.press("Escape")
    expect(page.locator("#fcc-slot-picker")).to_have_count(0)
