"""L298 Phase 3 — the Bulk Move preview/confirm panel (the first bulk-move E2E).

Phase 2 shipped the panel with NO Playwright coverage at all (its review lost
the frontend-integration + test-coverage verifiers to a token limit), so nothing
pinned the rendering contract while Phase 3 rewrote it.

These tests drive the panel against a STUBBED `/api/bulk_move_session` response
rather than a live armed session. That is deliberate:
  - the payload shape is the contract Phase 3 changed, and it is pinned on the
    backend side by tests/test_bulk_move_session.py (which uses the real plan);
  - a live session is global server state on a SHARED dev container, and arming
    one from a test would collide with any other sweep or a human at the screen
    (the Group 26/32/33 sweep-pollution class);
  - blocked / active-print / big-skip-list previews are not reproducible on
    demand from real inventory.

Everything below the fetch boundary is the real shipped code: mountOverlay, the
poll loop, the tile renderer, the grouping, the ack gate and the button wiring.
"""
from __future__ import annotations

import json

import pytest
from playwright.sync_api import Page, expect


def _stub_session(page: Page, payload: dict) -> None:
    """Intercept /api/bulk_move_session and answer from `payload`.

    BOTH verbs are intercepted. Letting POSTs through to the live container was
    a live-data hazard, not a nicety: a start POST would arm a REAL bulk-move
    session on the SHARED dev instance and leave it armed after the test — and
    an armed session's next location scan lands as its DESTINATION, so a human
    or another test scanning a label afterwards could stage a real move. (The
    sweep-pollution class that once wiped dev locations.json.) A POST answers
    with the same session payload so the client-side flow still resolves.

    Everything else (locations, logs, the pulse) still hits the live server, so
    the page around the panel behaves normally.
    """
    def _handler(route):
        if route.request.method == "GET":
            route.fulfill(status=200, content_type="application/json",
                          body=json.dumps(payload))
        else:
            route.fulfill(status=200, content_type="application/json",
                          body=json.dumps({"success": True, "session": payload}))
    page.route("**/api/bulk_move_session", _handler)


@pytest.fixture(autouse=True)
def _no_stray_session(api_base_url):
    """Belt-and-braces: clear any bulk-move session this module might leave on
    the shared dev container, before AND after each test."""
    import requests
    def _clear():
        try:
            requests.post(f"{api_base_url}/api/bulk_move_session",
                          json={"action": "cancel"}, timeout=5)
        except Exception:
            pass
    _clear()
    yield
    _clear()


def _open(page: Page, base_url: str, reset_dom_state_js: str, payload: dict):
    page.goto(base_url)
    page.wait_for_selector("#command-buffer, #buffer-zone", timeout=10_000)
    page.evaluate(reset_dom_state_js)
    page.wait_for_function(
        "typeof window.openBulkMovePanel === 'function'"
        " && typeof window.closeBulkMovePanel === 'function'"
        " && typeof window.mountOverlay === 'function'",
        timeout=10_000,
    )
    _stub_session(page, payload)
    # Pin the heartbeat signature to what the (idle) live server actually
    # reports. `state.lastBulkMoveState` starts null, so the FIRST /api/logs or
    # dashboard_pulse tick to land applies "false|idle" -> updateBulkMoveVisuals
    # -> set('idle') -> the idle state's onEnter -> closeBulkMovePanel(), tearing
    # the panel down under the test. The panel's own poll deliberately does not
    # write lastBulkMoveState, so nothing else suppresses it. Pre-seeding the
    # signature makes every real tick early-return. (This is a TEST-harness race
    # against a live heartbeat, not a product defect — but it is exactly the
    # load-sensitive flake class this repo has been burned by.)
    page.evaluate("() => { state.lastBulkMoveState = 'false|idle'; }")
    page.evaluate("window.openBulkMovePanel({ user: true })")
    overlay = page.locator("#fcc-bulkmove-panel-overlay")
    expect(overlay).to_be_visible(timeout=5_000)
    return overlay


def _row(sid, display, color="00aa55", slot="", weight=None, reason=None):
    r = {"id": sid, "display": display, "color": color,
         "color_direction": "longitudinal", "slot": slot, "remaining_weight": weight}
    if reason:
        r["reason"] = reason
    return r


_PREVIEW = {
    "active": True, "stage": "preview", "source_id": "PM-DB-A", "dest_id": "SHELF-B",
    "preview": {
        "ok": True, "msg": "", "blocked_reason": None, "require_confirm": False,
        "confirm_type": None, "active_print": None,
        "movable": [
            _row(101, "Sunlu PLA (Black)", "111111", slot="1", weight=812.4),
            _row(102, "Prusament Galaxy Black", "2b2b3a", slot="2", weight=245.0),
        ],
        "skipped": [
            _row(201, "Ghosted A", reason="deployed to a live toolhead"),
            _row(202, "Ghosted B", reason="deployed to a live toolhead"),
            _row(203, "Old Archived", reason="archived"),
        ],
        "stats": {"movable": 2, "skipped": 3},
    },
}


def _ap_payload(dest="SHELF-B"):
    """The standard preview, but with an ACTIVE PRINT require_confirm on it."""
    p = json.loads(json.dumps(_PREVIEW))
    p["dest_id"] = dest
    p["preview"].update({
        "ok": False, "require_confirm": True, "confirm_type": "active_print",
        "active_print": {"printer_name": "Core One", "state": "PRINTING"},
        "msg": "Core One is PRINTING - this will disrupt the print.",
    })
    return p


@pytest.mark.usefixtures("require_server")
def test_panel_renders_spool_tiles_with_weight_and_slot(
        page: Page, base_url: str, reset_dom_state_js: str):
    """Phase 2's rows were name-only. Phase 3 renders proper tiles: swatch,
    label, remaining weight and slot — the audit panel's tile grammar."""
    overlay = _open(page, base_url, reset_dom_state_js, _PREVIEW)

    expect(overlay).to_contain_text("PM-DB-A")
    expect(overlay).to_contain_text("SHELF-B")
    expect(overlay).to_contain_text("Will move (2)")

    tile = overlay.locator('.fcc-bulk-tile[data-spool-id="101"]')
    expect(tile).to_be_visible()
    expect(tile).to_contain_text("#101 Sunlu PLA (Black)")
    expect(tile).to_contain_text("812g")        # rounded remaining weight
    expect(tile).to_contain_text("slot 1")
    assert tile.get_attribute("data-kind") == "move"
    # 2 movable + 3 skipped tiles, all rendered.
    expect(overlay.locator(".fcc-bulk-tile")).to_have_count(5)


@pytest.mark.usefixtures("require_server")
def test_tile_does_not_double_print_the_spool_id(
        page: Page, base_url: str, reset_dom_state_js: str):
    """format_spool_display's text ALREADY starts with "#<id>" for real spools,
    so a hard-coded prefix rendered "#48 #48 [Legacy: 42] Sunlu PLA…" — caught
    on the live container, invisible to the synthetic fixtures above whose
    display strings happen to omit it."""
    payload = json.loads(json.dumps(_PREVIEW))
    payload["preview"]["movable"] = [
        _row(48, "#48 [Legacy: 42] Sunlu PLA (Blue)"),   # already prefixed
        _row(49, "Bare Name With No Id"),                # not prefixed
    ]
    payload["preview"]["stats"] = {"movable": 2, "skipped": 3}
    overlay = _open(page, base_url, reset_dom_state_js, payload)

    t48 = overlay.locator('.fcc-bulk-tile[data-spool-id="48"]').inner_text()
    assert "#48 #48" not in t48
    assert "#48 [Legacy: 42] Sunlu PLA (Blue)" in t48
    # ...but a display WITHOUT an id still gets one, so the id is never lost.
    assert "#49 Bare Name With No Id" in overlay.locator(
        '.fcc-bulk-tile[data-spool-id="49"]').inner_text()


@pytest.mark.usefixtures("require_server")
def test_skipped_rows_are_grouped_by_reason_with_counts(
        page: Page, base_url: str, reset_dom_state_js: str):
    """Phase 2 rendered one flat amber list with the reason repeated on every
    row. Phase 3 groups by reason so "why didn't these move?" is one glance."""
    overlay = _open(page, base_url, reset_dom_state_js, _PREVIEW)

    groups = overlay.locator(".fcc-bulk-skip-group")
    expect(groups).to_have_count(2)             # 'live toolhead' + 'archived'
    expect(overlay).to_contain_text("Left in place (3)")

    ghost = overlay.locator('.fcc-bulk-skip-group[data-reason="deployed to a live toolhead"]')
    expect(ghost).to_contain_text("deployed to a live toolhead")
    expect(ghost).to_contain_text("(2)")
    expect(ghost.locator(".fcc-bulk-tile")).to_have_count(2)
    # Small groups start expanded.
    assert ghost.evaluate("el => el.open") is True

    archived = overlay.locator('.fcc-bulk-skip-group[data-reason="archived"]')
    expect(archived).to_contain_text("(1)")
    expect(archived.locator('.fcc-bulk-tile[data-spool-id="203"]')).to_have_count(1)


@pytest.mark.usefixtures("require_server")
def test_large_skip_group_starts_collapsed(
        page: Page, base_url: str, reset_dom_state_js: str):
    """A Room-sized skip list must not bury the "will move" section."""
    payload = json.loads(json.dumps(_PREVIEW))
    payload["preview"]["skipped"] = [
        _row(300 + i, f"Buffered {i}", reason="in the scan buffer") for i in range(9)
    ]
    payload["preview"]["stats"] = {"movable": 2, "skipped": 9}
    overlay = _open(page, base_url, reset_dom_state_js, payload)

    grp = overlay.locator('.fcc-bulk-skip-group[data-reason="in the scan buffer"]')
    expect(grp).to_contain_text("(9)")
    assert grp.evaluate("el => el.open") is False


@pytest.mark.usefixtures("require_server")
def test_blocked_plan_shows_the_reason_and_the_refused_spools(
        page: Page, base_url: str, reset_dom_state_js: str):
    """A capacity block renders the message INLINE and still lists the spools it
    refused, and Commit stays disabled."""
    payload = {
        "active": True, "stage": "awaiting_dest",
        "source_id": "PM-DB-A", "dest_id": "PM-DB-B",
        "preview": {
            "ok": False, "blocked_reason": "capacity",
            "msg": "PM-DB-B has 2 free of 4; source has 5 to move — nothing moved.",
            "require_confirm": False, "confirm_type": None, "active_print": None,
            "movable": [_row(400 + i, f"Spool {i}") for i in range(5)],
            "skipped": [],
            "stats": {"movable": 5, "skipped": 0},
        },
    }
    overlay = _open(page, base_url, reset_dom_state_js, payload)

    expect(overlay.locator("#fcc-bulkmove-block")).to_contain_text("2 free of 4")
    expect(overlay).to_contain_text("Would have moved (5)")
    expect(overlay.locator('.fcc-bulk-tile[data-kind="blocked"]')).to_have_count(5)
    expect(overlay.locator("#fcc-bulkmove-commit")).to_be_disabled()

    # Isolate the `p.ok` term. Above, Commit is disabled for TWO independent
    # reasons (stage != 'preview' AND ok == false), so the assertion alone
    # cannot prove the ok gate exists. Re-stub with stage 'preview' — only
    # `ok` is left holding the button down.
    payload["stage"] = "preview"
    _stub_session(page, payload)
    expect(overlay).to_contain_text("Would have moved (5)", timeout=6_000)
    expect(overlay.locator("#fcc-bulkmove-commit")).to_be_disabled()


@pytest.mark.usefixtures("require_server")
def test_active_print_confirm_is_in_panel_and_gates_commit(
        page: Page, base_url: str, reset_dom_state_js: str):
    """THE Phase-3 safety fix. Phase 2 answered require_confirm by calling
    requestConfirmation, which opens Bootstrap's #confirmModal at z-index ~1100
    — BEHIND this overlay at 20000 — and set state.activeModal='confirm', which
    then swallowed the next scan. The confirm was effectively unreachable.

    It now lives in the panel: an explicit checkbox gates the Commit button, and
    the commit carries confirm_active_print only once it is ticked.
    """
    payload = json.loads(json.dumps(_PREVIEW))
    payload["preview"].update({
        "ok": False, "require_confirm": True, "confirm_type": "active_print",
        "active_print": {"printer_name": "Core One", "state": "PRINTING",
                         "toolhead": "PM-DB-A"},
        "msg": "Core One is PRINTING — bulk-moving from this location will disrupt the print.",
    })
    overlay = _open(page, base_url, reset_dom_state_js, payload)

    strip = overlay.locator("#fcc-bulkmove-ap")
    expect(strip).to_be_visible()
    expect(strip).to_contain_text("ACTIVE PRINT")
    expect(strip).to_contain_text("Core One is PRINTING")

    commit = overlay.locator("#fcc-bulkmove-commit")
    expect(commit).to_contain_text("Commit Anyway")
    expect(commit).to_be_disabled()             # unreachable until acknowledged

    # Capture the commit payload instead of firing a real move.
    # NOTE the arrow-function form: page.evaluate() INVOKES a script whose value
    # is a function, so `window.x = () => …` as the trailing expression calls the
    # stub once, immediately (it cost an hour of chasing a phantom commit).
    page.evaluate("""() => {
        window.__commitArgs = [];
        window.commitBulkMove = (c) => window.__commitArgs.push(c);
    }""")
    overlay.locator("#fcc-bulkmove-ap-ack").check()
    expect(commit).to_be_enabled()
    commit.click()
    assert page.evaluate("window.__commitArgs") == [True]


@pytest.mark.usefixtures("require_server")
def test_hide_latches_so_a_stage_change_cannot_reopen_the_panel(
        page: Page, base_url: str, reset_dom_state_js: str):
    """Hide's tooltip promises the panel stays armed but dismissed. Phase 2's
    panel re-opened itself on the very next stage change (every active state's
    shapeshift onEnter calls openBulkMovePanel unconditionally), and the deck
    button it named as the way back in actually CANCELLED the session."""
    _open(page, base_url, reset_dom_state_js, _PREVIEW)
    page.locator("#fcc-bulkmove-close").click()
    expect(page.locator("#fcc-bulkmove-panel-overlay")).to_have_count(0, timeout=3_000)

    # A stage change (the shapeshift onEnter path) must NOT drag it back open.
    page.evaluate("""() => {
        state.bulkMoveActive = true;
        state.bulkMoveStage = 'awaiting_dest';
        window.updateBulkMoveVisuals();
    }""")
    expect(page.locator("#fcc-bulkmove-panel-overlay")).to_have_count(0)
    assert page.evaluate("window.isBulkMovePanelOpen()") is False

    # The deck button, with the panel hidden, REOPENS it (rather than cancelling).
    # Arrow-function form again — a trailing function value would be CALLED by
    # page.evaluate, which would tick the counter before the toggle ever ran.
    page.evaluate("""() => {
        window.__cancelled = 0;
        window.cancelBulkMove = () => { window.__cancelled++; };
    }""")
    page.evaluate("window.toggleBulkMove()")
    expect(page.locator("#fcc-bulkmove-panel-overlay")).to_be_visible(timeout=3_000)
    assert page.evaluate("window.__cancelled") == 0

    # ...and with the panel OPEN it is the safe bail again.
    page.evaluate("window.toggleBulkMove()")
    assert page.evaluate("window.__cancelled") == 1


@pytest.mark.usefixtures("require_server")
def test_panel_closes_itself_when_the_session_ends(
        page: Page, base_url: str, reset_dom_state_js: str):
    """The 2 s poll seeing active:false is what tears the panel down after a
    commit / a cancel from another tab / the idle watchdog."""
    overlay = _open(page, base_url, reset_dom_state_js, _PREVIEW)
    expect(overlay).to_contain_text("Will move (2)")
    _stub_session(page, {"active": False, "stage": "idle"})
    expect(page.locator("#fcc-bulkmove-panel-overlay")).to_have_count(0, timeout=6_000)
    assert page.evaluate("state.bulkMoveActive") is False


# ---------------------------------------------------------------------------
# Review fixes (adversarial review, 2026-08-02)
# ---------------------------------------------------------------------------

@pytest.mark.usefixtures("require_server")
def test_ack_checkbox_does_not_disarm_the_barcode_scanner(
        page: Page, base_url: str, reset_dom_state_js: str):
    """THE checkbox's hidden cost. The global scan handler's FIRST line is
    `if (e.target.tagName === 'INPUT' || ...) return;` — so leaving the ack
    checkbox focused kills the scanner for every subsequent scan, including the
    CMD:DONE / CMD:CANCEL the panel's own QR codes tell the user to scan. The
    onchange handler must blur it."""
    overlay = _open(page, base_url, reset_dom_state_js, _ap_payload())

    overlay.locator("#fcc-bulkmove-ap-ack").check()
    assert page.evaluate("document.activeElement && document.activeElement.id") != "fcc-bulkmove-ap-ack"
    assert page.evaluate("document.activeElement && document.activeElement.tagName") != "INPUT"
    # ...and the ack still took effect.
    expect(overlay.locator("#fcc-bulkmove-commit")).to_be_enabled()
    assert page.evaluate("document.getElementById('fcc-bulkmove-ap-ack').checked") is True


@pytest.mark.usefixtures("require_server")
def test_ack_resets_when_the_destination_changes(
        page: Page, base_url: str, reset_dom_state_js: str):
    """The ack is keyed to the plan it acknowledged. Re-targeting the
    destination must drop the tick — otherwise a user who acknowledged
    "disrupt the print to fill SHELF-B" silently pre-authorises SHELF-C."""
    overlay = _open(page, base_url, reset_dom_state_js, _ap_payload("SHELF-B"))
    overlay.locator("#fcc-bulkmove-ap-ack").check()
    expect(overlay.locator("#fcc-bulkmove-commit")).to_be_enabled()

    _stub_session(page, _ap_payload("SHELF-C"))     # the user re-scans a dest
    expect(overlay).to_contain_text("SHELF-C", timeout=8_000)
    expect(overlay.locator("#fcc-bulkmove-ap-ack")).not_to_be_checked()
    expect(overlay.locator("#fcc-bulkmove-commit")).to_be_disabled()


@pytest.mark.usefixtures("require_server")
def test_ack_resets_when_the_movable_set_changes(
        page: Page, base_url: str, reset_dom_state_js: str):
    """Same principle for WHAT moves: re-scanning the SAME destination after the
    source contents changed yields an identical source|dest|printer|state tuple
    but a different spool list, which the user has not reviewed."""
    overlay = _open(page, base_url, reset_dom_state_js, _ap_payload())
    overlay.locator("#fcc-bulkmove-ap-ack").check()
    expect(overlay.locator("#fcc-bulkmove-commit")).to_be_enabled()

    changed = _ap_payload()
    changed["preview"]["movable"] = [_row(999, "A spool nobody reviewed")]
    changed["preview"]["stats"] = {"movable": 1, "skipped": 3}
    _stub_session(page, changed)
    expect(overlay).to_contain_text("A spool nobody reviewed", timeout=8_000)
    expect(overlay.locator("#fcc-bulkmove-ap-ack")).not_to_be_checked()
    expect(overlay.locator("#fcc-bulkmove-commit")).to_be_disabled()


@pytest.mark.usefixtures("require_server")
def test_ack_does_not_survive_hide_and_reopen(
        page: Page, base_url: str, reset_dom_state_js: str):
    """_apAck is module-scoped. Without an explicit reset on close, the panel
    reopened with the safety gate ALREADY satisfied — one click from disrupting
    a live print with no fresh acknowledgement in that view."""
    overlay = _open(page, base_url, reset_dom_state_js, _ap_payload())
    overlay.locator("#fcc-bulkmove-ap-ack").check()
    expect(overlay.locator("#fcc-bulkmove-commit")).to_be_enabled()

    page.locator("#fcc-bulkmove-close").click()
    expect(page.locator("#fcc-bulkmove-panel-overlay")).to_have_count(0, timeout=3_000)
    page.evaluate("window.openBulkMovePanel({ user: true })")
    reopened = page.locator("#fcc-bulkmove-panel-overlay")
    expect(reopened).to_be_visible(timeout=5_000)
    expect(reopened.locator("#fcc-bulkmove-ap-ack")).not_to_be_checked()
    expect(reopened.locator("#fcc-bulkmove-commit")).to_be_disabled()


@pytest.mark.usefixtures("require_server")
def test_commit_button_locks_out_while_a_commit_is_in_flight(
        page: Page, base_url: str, reset_dom_state_js: str):
    """A commit is an O(N) multi-second write, and this panel sits at z 20000 —
    ABOVE the z-9999 processing overlay — so the button stays physically
    clickable throughout. A second click was refused by the backend lock, but
    the client had already run setProcessing(false), unfreezing the whole
    dashboard (and its queued-scan gate) mid-write."""
    overlay = _open(page, base_url, reset_dom_state_js, _PREVIEW)

    # Hang the commit POST so the in-flight window stays open for the assertions.
    def _hang(route):
        if route.request.method == "GET":
            route.fulfill(status=200, content_type="application/json",
                          body=json.dumps(_PREVIEW))
        # POST: neither fulfil nor abort — leave it pending.

    page.route("**/api/bulk_move_session", _hang)

    commit = overlay.locator("#fcc-bulkmove-commit")
    expect(commit).to_be_enabled()
    commit.click()
    expect(commit).to_be_disabled()
    expect(commit).to_contain_text("Committing")
    assert page.evaluate("window.bulkMoveCommitInflight()") is True
    assert page.evaluate("state.processing") is True
    # A repaint mid-commit must NOT hand the button back.
    page.wait_for_timeout(2_500)
    expect(overlay.locator("#fcc-bulkmove-commit")).to_be_disabled()
    assert page.evaluate("state.processing") is True


@pytest.mark.usefixtures("require_server")
def test_dropped_commit_reconciles_instead_of_claiming_failure(
        page: Page, base_url: str, reset_dom_state_js: str):
    """Claim 8: a commit whose REQUEST drops may well have succeeded server-side
    (it is an O(N) write behind a 120 s timeout). Asserting "Bulk move failed"
    there is a lie that also skipped the location refresh."""
    overlay = _open(page, base_url, reset_dom_state_js, _PREVIEW)
    page.evaluate("""() => {
        window.__refreshed = 0;
        window.fetchLocations = () => { window.__refreshed++; };
    }""")

    def _abort_post(route):
        if route.request.method == "GET":
            route.fulfill(status=200, content_type="application/json",
                          body=json.dumps(_PREVIEW))
        else:
            route.abort()

    page.route("**/api/bulk_move_session", _abort_post)

    overlay.locator("#fcc-bulkmove-commit").click()
    expect(page.get_by_text("may still be running", exact=False)).to_be_visible(timeout=10_000)
    assert page.evaluate("window.__refreshed") >= 1
    # The in-flight latch is released so the user can retry.
    assert page.evaluate("window.bulkMoveCommitInflight()") is False
    assert page.evaluate("state.processing") is False


@pytest.mark.usefixtures("require_server")
def test_tile_renderer_escapes_hostile_spool_names_and_colours(
        page: Page, base_url: str, reset_dom_state_js: str):
    """Spool display names come from Spoolman (user-editable) and land in an
    HTML attribute AND a text node; the colour lands in a STYLE attribute. This
    repo has already shipped one stored-XSS through exactly this seam (the
    Group 34 escAttr export bug), so the escaping needs a pin, not a comment."""
    payload = json.loads(json.dumps(_PREVIEW))
    payload["preview"]["movable"] = [
        _row(701, 'Evil" onmouseover="window.__pwned=1'),
        _row(702, "<img src=x onerror=window.__pwned=2>", color="red;background:url(x)"),
    ]
    payload["preview"]["skipped"] = [
        _row(703, "Ghost", reason='deployed" onload="window.__pwned=3'),
    ]
    payload["preview"]["stats"] = {"movable": 2, "skipped": 1}
    overlay = _open(page, base_url, reset_dom_state_js, payload)

    assert page.evaluate("window.__pwned") is None
    assert overlay.locator("img").count() == 0
    # The hostile text renders as literal characters, not markup.
    expect(overlay.locator('.fcc-bulk-tile[data-spool-id="702"]')).to_contain_text(
        "<img src=x onerror=window.__pwned=2>")
    expect(overlay.locator('.fcc-bulk-tile[data-spool-id="701"]')).to_contain_text(
        'Evil" onmouseover="window.__pwned=1')
    page.wait_for_timeout(300)
    assert page.evaluate("window.__pwned") is None
