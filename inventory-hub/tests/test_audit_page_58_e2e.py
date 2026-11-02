"""Group 58, build spec section 7: the audit on the real dashboard, with Bootstrap and
the page's own polls. Reads and writes nothing of dev's but the last test: every
other one answers /api/identify_scan, /api/audit_session and the heartbeat in this
browser, on the routes' real shapes (test_audit_page_58_js.SESSION is pinned to
them), so nothing it does reaches a real session, and a test's audit can't be
closed by dev's own heartbeat saying there is none. The last test runs one real
audit from the tile to Cancel, which writes nothing to Spoolman.

The logic is proved on the real modules in test_audit_page_58_js.py and
test_audit_panel_58_js.py; this is the same flows where a hidden Bootstrap dialog,
a real heartbeat and a real panel can get in the way.
"""
from __future__ import annotations

import json

import pytest
import requests
from playwright.sync_api import Page, expect

import conftest
from test_audit_page_58_js import SESSION

pytestmark = pytest.mark.usefixtures("require_server")

PANEL = "#fcc-audit-panel-overlay"
PILL = "#fcc-audit-pill"
TILE = "#btn-deck-audit"
DONE = "#fcc-audit-panel-done"
CANCEL = "#fcc-audit-panel-cancel"
HIDE = "#fcc-audit-panel-close"
AUDIT_SCAN = {"type": "command", "cmd": "audit_scan"}
NO_SESSION = {"active": False, "audit_end": None}
WARNING = "The audit of LR-MDB-1 ended (idle for 30 minutes): scans go to the buffer again."


class Server:
    """What this browser hears from FCC: `answers` {scan's text: answer}, the session
    /api/audit_session answers, and the heartbeat's audit keys. `scans` records every
    scan that reached it. Install before page.goto."""

    def __init__(self, page, session=None, audit_active=False, audit_location=""):
        self.scans, self.logged, self.answers, self.session = [], [], {}, session or NO_SESSION
        self.beat = {"audit_active": audit_active, "audit_location": audit_location, "audit_end": None}
        conftest.quiet_heartbeat(page)
        page.route("**/api/logs*", self._logs)
        page.route("**/api/dashboard_pulse*", self._pulse)
        page.route("**/api/audit_session*", lambda route: self._json(route, self.session))
        page.route("**/api/identify_scan", self._scan)
        page.route("**/api/log_event", self._log_event)

    @staticmethod
    def _json(route, body):
        route.fulfill(status=200, content_type="application/json", body=json.dumps(body))

    def _payload(self):
        return {"logs": [], "status": {"spoolman": True}, **self.beat}

    def _logs(self, route):
        self._json(route, self._payload())

    def _pulse(self, route):
        self._json(route, {"logs": self._payload()})

    def _scan(self, route):
        text = (route.request.post_data_json or {}).get("text")
        self.scans.append(text)
        answer = self.answers.get(text, AUDIT_SCAN)
        if text == "CMD:AUDIT" and answer is AUDIT_SCAN:    # the server has started one
            self.session = SESSION
            self.beat.update(audit_active=True, audit_location="LR-MDB-1")
        if answer.get("audit_ended"):                       # the server has ended it
            end = dict(answer["audit_ended"], location="LR-MDB-1")
            self.session = {"active": False, "audit_end": end}
            self.beat.update(audit_active=False, audit_location="", audit_end=end)
        self._json(route, answer)

    def _log_event(self, route):
        self.logged.append((route.request.post_data_json or {}).get("msg"))
        self._json(route, {"success": True})


def _dashboard(page: Page, base_url: str):
    page.goto(base_url, wait_until="domcontentloaded")
    page.wait_for_function("() => typeof window.openAuditPanel === 'function' && typeof window.processScan === 'function'",
                           timeout=45_000)


def _start(page: Page):
    """The real tile, then the panel on the session."""
    page.click(TILE)
    page.wait_for_selector(DONE)


def _toasts(page):
    return page.evaluate("() => Array.from(document.querySelectorAll('#toast-container .toast-msg')).map((e) => e.innerText)")


def test_a_cmd_audit_scan_shows_the_panel_and_cancels_nothing(page: Page, base_url: str):
    server = Server(page)
    _dashboard(page, base_url)
    _start(page)
    page.click(HIDE)
    expect(page.locator(PANEL)).to_have_count(0)
    page.evaluate("window.processScan('CMD:AUDIT', 'barcode')")
    expect(page.locator(PANEL)).to_be_visible()
    assert server.scans == ["CMD:AUDIT"]        # the start only
    assert page.evaluate("state.auditActive") is True


def test_hide_then_the_tile_or_the_pill_brings_it_back(page: Page, base_url: str):
    server = Server(page)
    _dashboard(page, base_url)
    _start(page)
    page.click(HIDE)
    expect(page.locator(PANEL)).to_have_count(0)
    expect(page.locator(TILE)).to_contain_text("FINISH")
    page.click(TILE)
    expect(page.locator(PANEL)).to_be_visible()
    page.keyboard.press("Escape")
    expect(page.locator(PANEL)).to_have_count(0)
    expect(page.locator(PILL)).to_have_text("🕵️ audit: LR-MDB-1", use_inner_text=True)
    page.click(PILL)
    expect(page.locator(PANEL)).to_be_visible()
    assert server.scans == ["CMD:AUDIT"]


def test_the_pill_remembers_where_it_was_dragged(page: Page, base_url: str):
    server = Server(page)
    _dashboard(page, base_url)
    _start(page)
    page.click(HIDE)
    box = page.locator(PILL).bounding_box()
    x, y = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
    page.mouse.move(x, y)
    page.mouse.down()
    page.mouse.move(x - 200, y - 100, steps=4)
    page.mouse.up()
    expect(page.locator(PANEL)).to_have_count(0)
    saved = json.loads(page.evaluate("localStorage.getItem('fcc.auditPill.pos')"))
    assert abs(saved["left"] - (box["x"] - 200)) <= 2


def test_a_spool_in_the_buffer_no_longer_raises_clear_entire_buffer(page: Page, base_url: str):
    """With a spool buffered, every audit scan raised "Clear entire Buffer?" behind
    the panel, and that hidden prompt ate every later scan. A real audit answers
    audit_scan, the buffer is the page's own."""
    server = Server(page)
    conftest.own_the_buffer(page, [{"id": 8057, "display": "#8057 A buffered spool", "color": "72071C"}])
    _dashboard(page, base_url)
    page.wait_for_function("() => state.heldSpools.length === 1", timeout=15_000)
    _start(page)
    for text in ("LOC:LR-MDB-1", "ID:57", "ID:99"):
        page.evaluate("(text) => { window.processScan(text, 'barcode'); }", text)
        page.wait_for_function("(text) => !state.processing", arg=text)
    assert server.scans == ["CMD:AUDIT", "LOC:LR-MDB-1", "ID:57", "ID:99"]
    assert page.evaluate("state.activeModal") is None
    expect(page.locator("#confirmModal")).not_to_be_visible()
    assert page.evaluate("state.heldSpools.map((s) => s.id)") == [8057]


def test_a_refused_start_leaves_the_page_truthful(page: Page, base_url: str):
    msg = "A bulk move is armed — commit or cancel it before starting an audit."
    server = Server(page)
    server.answers["CMD:AUDIT"] = {"type": "error", "msg": msg}
    _dashboard(page, base_url)
    page.click(TILE)
    page.wait_for_function("(msg) => Array.from(document.querySelectorAll('#toast-container .toast-msg'))"
                           ".some((e) => e.innerText === msg)", arg=msg)
    assert page.evaluate("state.auditActive") is False
    expect(page.locator(PANEL)).to_have_count(0)
    expect(page.locator(PILL)).to_be_hidden()
    expect(page.locator(TILE)).to_contain_text("AUDIT")
    page.click(TILE)
    page.wait_for_function("() => document.querySelectorAll('#toast-container .toast-msg').length >= 1")
    page.wait_for_timeout(200)
    assert server.scans == ["CMD:AUDIT", "CMD:AUDIT"]


def test_cancel_never_sends_cmd_audit(page: Page, base_url: str):
    server = Server(page)
    _dashboard(page, base_url)
    _start(page)
    server.answers["CMD:CANCEL"] = dict(AUDIT_SCAN, audit_ended={"id": "boot-1", "why": "cancel"})
    page.evaluate("() => { state.auditActive = false; }")      # as a Done that has just landed left it
    page.click(CANCEL)
    expect(page.locator(PANEL)).to_have_count(0, timeout=5_000)
    assert server.scans == ["CMD:AUDIT", "CMD:CANCEL"]


def test_the_watchdogs_end_warns_once_and_a_scanned_cancel_doesnt(page: Page, base_url: str):
    """The real heartbeat path, then a second audit on the same page."""
    server = Server(page)
    _dashboard(page, base_url)
    _start(page)
    end = {"id": "boot-1", "why": "idle", "location": "LR-MDB-1"}
    server.session = {"active": False, "audit_end": end}
    server.beat.update(audit_active=False, audit_location="", audit_end=end)
    expect(page.locator(PANEL)).to_have_count(0, timeout=10_000)
    page.wait_for_function("(w) => Array.from(document.querySelectorAll('#toast-container .toast-msg'))"
                           ".some((e) => e.innerText === w)", arg=WARNING)
    page.evaluate("() => window._dashboardPulseTickOnce()")
    page.wait_for_timeout(300)
    assert _toasts(page).count(WARNING) == 1
    assert server.logged == [f"⚠️ {WARNING}"]
    expect(page.locator(PILL)).to_be_hidden()
    expect(page.locator(TILE)).to_contain_text("AUDIT")

    # A second audit, ended by a scan here: its answer says so, and the heartbeat
    # that follows stays quiet.
    server.logged.clear()
    _start(page)
    server.answers["CMD:CANCEL"] = dict(AUDIT_SCAN, audit_ended={"id": "boot-2", "why": "cancel"})
    page.evaluate("window.processScan('CMD:CANCEL', 'barcode')")
    expect(page.locator(PANEL)).to_have_count(0, timeout=5_000)
    page.evaluate("() => window._dashboardPulseTickOnce()")
    page.wait_for_timeout(300)
    assert server.logged == []
    assert "Audit cancelled: nothing moved." in _toasts(page)


def test_a_refused_scan_is_read_on_the_panel_over_the_real_deck(page: Page, base_url: str):
    server = Server(page)
    server.answers["LOC:LR-MDB-2"] = {"type": "error", "msg": "Already auditing LR-MDB-1. Finish first!"}
    _dashboard(page, base_url)
    _start(page)
    page.evaluate("window.processScan('LOC:LR-MDB-2', 'barcode')")
    notice = page.locator("#fcc-audit-panel-notice")
    expect(notice).to_have_text("Already auditing LR-MDB-1. Finish first!")
    assert page.evaluate("""() => { const el = document.getElementById('fcc-audit-panel-notice');
        const r = el.getBoundingClientRect();
        return el.contains(document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2)); }""")


def test_a_real_audit_from_the_tile_to_cancel(page: Page, base_url: str, api_base_url: str):
    """No stubs, on dev's real server and real place: nothing is written to Spoolman
    (a Cancel moves nothing) and the session is gone at the end."""
    if requests.get(f"{api_base_url}/api/audit_session", timeout=10).json().get("active"):
        pytest.skip("an audit is already running on dev")
    if requests.get(f"{api_base_url}/api/bulk_move_session", timeout=10).json().get("active"):
        pytest.skip("a bulk move is armed on dev")
    rows = requests.get(f"{api_base_url}/api/locations", timeout=30).json()
    places = [r["LocationID"] for r in rows if r.get("Type") == "Dryer Box"][:2]
    assert len(places) == 2, rows
    _dashboard(page, base_url)
    page.wait_for_function("() => state.lastAuditState === false", timeout=30_000)
    try:
        page.click(TILE)
        page.wait_for_selector(DONE)
        page.evaluate("(p) => { window.processScan('LOC:' + p, 'barcode'); }", places[0])
        expect(page.locator("#fcc-audit-panel-body")).to_contain_text(f"Auditing {places[0]}")
        expect(page.locator(PILL)).to_contain_text(places[0], use_inner_text=True, timeout=5_000)
        page.evaluate("(p) => { window.processScan('LOC:' + p, 'barcode'); }", places[1])
        expect(page.locator("#fcc-audit-panel-notice")).to_have_text(f"Already auditing {places[0]}. Finish first!")
        page.click(CANCEL)
        expect(page.locator(PANEL)).to_have_count(0, timeout=5_000)
        expect(page.locator(PILL)).to_be_hidden()
        assert requests.get(f"{api_base_url}/api/audit_session", timeout=10).json()["active"] is False
    finally:
        if requests.get(f"{api_base_url}/api/audit_session", timeout=10).json().get("active"):
            requests.post(f"{api_base_url}/api/identify_scan", json={"text": "CMD:CANCEL"}, timeout=10)
