"""Derek's answers of 2026-11-03 on Group 58, on the real dashboard: a tile's real QR code
scanned as a scanner's keys (A1), 🔎 Find a spool by keyboard and by mouse (A2), and the
phone width, with Bootstrap, the real accumulator and the page's own polls.

FCC's routes are answered in this browser on their real shapes (the audit's session,
test_audit_page_58_js.SESSION; the search's rows, test_audit_find_and_tiles_58_js.SEARCH_ROWS;
both pinned to the real routes), and every request that isn't a GET is answered here and
recorded, so nothing reaches dev but reads and dev's own audit stays idle.

The rules are proved hermetically in test_audit_find_and_tiles_58_js.py; the double
click on a Find row and on an Extra tile, at five window sizes, in
test_audit_double_click_58_e2e.py; the contrast and text-size guards in
test_contrast_guard.py and test_text_size_guard.py.
"""
from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect

import conftest
from test_audit_find_and_tiles_58_js import SEARCH_ROWS
from test_audit_no_label_58_e2e import SCANNER, Marks, tile
from test_audit_page_58_e2e import _dashboard, _start

pytestmark = pytest.mark.usefixtures("require_server")

FIND = "#fcc-audit-find"
FIND_BTN = "#fcc-audit-panel-find"
FIND_BOX = FIND + " [data-find-box]"
FIND_BODY = FIND + " [data-find-body]"
NOT_SCANNED = 99


class Finds(Marks):
    """Marks, with every write answered here, the search answered from SEARCH_ROWS, and a
    find by a tile's QR or a Find pick turning the session as the routes turn it."""

    def __init__(self, page):
        self.writes, self.searches = [], []
        page.route("**/*", self._any)                   # first: every route after it wins
        super().__init__(page)
        page.route("**/api/search*", self._search)
        conftest.own_the_buffer(page, [])

    def _any(self, route):
        if route.request.method == "GET":
            route.continue_()
            return
        self.writes.append("/" + route.request.url.split("/", 3)[3].split("?")[0])
        self._json(route, {"success": True, "status": "success"})

    def _search(self, route):
        q = route.request.url.split("q=", 1)[1].split("&", 1)[0].replace("+", " ").lower()
        self.searches.append(route.request.url.split("/", 3)[3])
        rows = [r for r in SEARCH_ROWS if all(w in r["display"].lower() for w in q.split())]
        self._json(route, {"success": True, "results": rows})

    def _find(self, sid):
        rows = self.session["expected"]
        if any(r["id"] == sid for r in rows):
            self._set(dict(next(r for r in rows if r["id"] == sid), found=True, label_read=False))

    def _scan(self, route):
        body = route.request.post_data_json or {}
        text = str(body.get("text") or "")
        self.sources = getattr(self, "sources", []) + [(text, body.get("source"))]
        if text.upper().startswith("CMD:FOUND:"):
            self._find(int(text.rsplit(":", 1)[1]))
        elif text.startswith("ID:"):
            self._find(int(text[3:]))
        super()._scan(route)


def _running(page: Page, base_url: str):
    server = Finds(page)
    _dashboard(page, base_url)
    _start(page)
    page.wait_for_selector(tile(NOT_SCANNED))
    return server


def test_a_real_tile_qr_scanned_as_a_scanners_keys_finds_the_spool(page: Page, base_url: str):
    server = _running(page, base_url)
    qr = f"{tile(NOT_SCANNED)} .fcc-audit-tile-qr"
    expect(page.locator(f"{qr} canvas, {qr} img").first).to_be_attached()
    assert page.get_attribute(qr, "data-audit-qr") == "CMD:FOUND:boot-1:99"
    assert page.get_attribute(qr, "aria-hidden") == "true"
    box = page.locator(qr).bounding_box()
    assert round(box["width"]) == 78 and round(box["height"]) == 78          # 72 px and its quiet zone
    assert page.locator(f"{tile(57)} .fcc-audit-tile-qr").count() == 0        # found: none
    page.evaluate(SCANNER, "CMD:FOUND:boot-1:99")
    expect(page.locator(tile(NOT_SCANNED))).to_contain_text("found, no label read")
    expect(page.locator(qr)).to_have_count(0)
    assert ("CMD:FOUND:boot-1:99", "barcode") in server.sources
    assert server.writes == []


def test_find_by_keyboard(page: Page, base_url: str):
    server = _running(page, base_url)
    page.keyboard.press("/")
    expect(page.locator(FIND_BOX)).to_be_focused()
    page.keyboard.type("glow blue", delay=20)
    expect(page.locator(f"{FIND} .fcc-find-row")).to_have_count(1)
    expect(page.locator(f"{FIND} .fcc-find-row")).to_contain_text("📍 LR-MDB-1 slot 2")
    expect(page.locator(f"{FIND} .fcc-find-row")).to_contain_text("on the list")
    assert server.searches == ["api/search?q=glow+blue&type=spool&strict=1"]
    page.keyboard.press("ArrowDown")
    page.keyboard.press("Enter")
    expect(page.locator(FIND)).to_have_count(0)
    expect(page.locator(tile(NOT_SCANNED))).to_contain_text("found, no label read")
    assert ("ID:99", "search") in server.sources
    expect(page.locator(FIND_BTN)).to_be_focused()


def test_find_by_mouse(page: Page, base_url: str):
    server = _running(page, base_url)
    page.click(FIND_BTN)
    page.fill(FIND_BOX, "glow")
    expect(page.locator(f"{FIND} .fcc-find-row")).to_have_count(len(SEARCH_ROWS))
    expect(page.locator(f"{FIND} .fcc-find-row[data-find-id='242']")).to_contain_text("🔗 loaded from LR-MDB-2 slot 4")
    expect(page.locator(f"{FIND} .fcc-find-row[data-find-id='260']")).to_contain_text("❓ Lost: CR-CT-1 slot 2")
    expect(page.locator(f"{FIND} .fcc-find-row[data-find-id='270']")).to_contain_text("Unassigned")
    page.click(f"{FIND} .fcc-find-row[data-find-id='99']")
    expect(page.locator(FIND)).to_have_count(0)
    expect(page.locator(tile(NOT_SCANNED))).to_contain_text("found, no label read")
    assert ("ID:99", "search") in server.sources


@pytest.mark.parametrize("width, height", [(390, 844), (1600, 1300)])
def test_nothing_scrolls_sideways(page: Page, base_url: str, width, height):
    """At phone width too: the tiles with their QR, the strip with its 🖨️, and Find."""
    page.set_viewport_size({"width": width, "height": height})
    server = _running(page, base_url)
    page.click(tile(NOT_SCANNED))                    # the strip, with the spool not flagged
    page.evaluate(SCANNER, "CMD:NEEDLABEL")          # flagged: the strip's 🖨️ shows
    expect(page.locator("#fcc-audit-label-queue")).to_be_visible()

    def sideways():
        return page.evaluate("""() => { const p = document.querySelector('#fcc-audit-panel-overlay > div');
            const b = document.getElementById('fcc-audit-panel-body'); const r = p.getBoundingClientRect();
            return { page: document.documentElement.scrollWidth > innerWidth, body: b.scrollWidth > b.clientWidth + 1,
                     out: r.left < -0.5 || r.right > innerWidth + 0.5 }; }""")
    assert sideways() == {"page": False, "body": False, "out": False}
    page.click(FIND_BTN)
    page.fill(FIND_BOX, "glow")
    expect(page.locator(f"{FIND} .fcc-find-row")).to_have_count(len(SEARCH_ROWS))
    got = page.evaluate("""() => { const p = document.querySelector('#fcc-audit-find .fcc-find-panel');
        const body = p.querySelector('[data-find-body]'); const r = p.getBoundingClientRect();
        return { out: r.left < -0.5 || r.right > innerWidth + 0.5, body: body.scrollWidth > body.clientWidth + 1 }; }""")
    assert got == {"out": False, "body": False}
    assert page.evaluate("() => document.documentElement.scrollWidth > innerWidth") is False
    assert server.writes == []
