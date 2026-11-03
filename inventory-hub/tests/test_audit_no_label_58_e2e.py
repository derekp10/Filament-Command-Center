"""Group 58.2 on the real dashboard, with Bootstrap, real QR codes, the real accumulator
and the page's own polls. Every test but the last answers FCC's routes in this
browser, on their real shapes (test_audit_page_58_js.SESSION and the guards' sample
are pinned to them), so nothing reaches a real session. The last runs one real audit
from the tile through a press, a mark, its undo, a label read and Cancel, on
throwaway dev spools, with nothing stubbed but the page's buffer.

The rules are proved in test_audit_no_label_58.py, and the page on the real routes in
test_audit_no_label_58_js.py; this is the same flows where the real panel, a hidden
Bootstrap dialog and a real heartbeat can get in the way.
"""
from __future__ import annotations

import json

import pytest
import requests
from playwright.sync_api import Page, expect

import conftest
from test_audit_done_question_58_e2e import _empty_box, _on_top, _scan_keys
from test_audit_page_58_e2e import AUDIT_SCAN, DONE, PANEL, TILE, Server, _dashboard, _start
from test_audit_page_58_js import SESSION

pytestmark = pytest.mark.usefixtures("require_server")

STRIP = "#fcc-audit-last-found"
STATUS = STRIP + " [role=status]"
BUTTON = "#fcc-audit-panel-needlabel"
QR = "#fcc-audit-panel-qr-needlabel"
UNDO = "#fcc-audit-label-undo"
BODY = "#fcc-audit-panel-body"
MARK = "CMD:NEEDLABEL"
NOT_SCANNED = SESSION["expected"][1]["id"]      # #99
FOUND = SESSION["expected"][0]["id"]            # #57


def tile(sid):
    return f"[data-audit-tile='{sid}']"


def _found(row, **more):
    return dict(row, found=True, **more)


class Marks(Server):
    """Server, with the session a real one would answer as scans land: `press` and
    `mark` turn it as the routes turn theirs, on the same rows."""

    def __init__(self, page):
        super().__init__(page)
        self.answers[MARK] = dict(AUDIT_SCAN, said="#99 is marked: it needs a label.")
        self.pressed, self.undone = [], []
        page.route("**/api/audit/found", self._press)
        page.route("**/api/audit/needs_label_undo", self._undo)

    def _set(self, row):
        """`row` is the last found, drawn in its list."""
        expected = [row if r["id"] == row["id"] else r for r in self.session["expected"]]
        self.session = dict(self.session, expected=expected, last_found=row)

    def _scan(self, route):
        text = (route.request.post_data_json or {}).get("text")
        if text == MARK:
            self._set(dict(self.session["last_found"], label_status=True, flagged_here=True))
        super()._scan(route)

    def _press(self, route):
        body = route.request.post_data_json or {}
        self.pressed.append(body)
        row = next(r for r in self.session["expected"] if r["id"] == body["id"])
        if body["found"]:
            self._set(_found(row))
        else:
            expected = [dict(r, found=False) if r["id"] == body["id"] else r for r in self.session["expected"]]
            self.session = dict(self.session, expected=expected, last_found=None)
        self._json(route, {"success": True, "found": body["found"]})

    def _undo(self, route):
        self.undone.append(route.request.post_data_json)
        self._set(dict(self.session["last_found"], label_status=None, flagged_here=False))
        self._json(route, {"success": True, "msg": "Undone: #99 has no label status again."})


# A scanner's keys, all in one tick, so its speed can't depend on this machine's load.
SCANNER = """(text) => { const t = document.activeElement || document.body;
    for (const key of [...text, 'Enter']) t.dispatchEvent(new KeyboardEvent('keydown', { key, bubbles: true, cancelable: true })); }"""


def _running(page: Page, base_url: str):
    server = Marks(page)
    _dashboard(page, base_url)
    _start(page)
    page.wait_for_selector(tile(FOUND))
    return server


def test_the_strip_its_button_and_a_real_qr_under_it(page: Page, base_url: str):
    server = _running(page, base_url)
    page.click(tile(NOT_SCANNED))
    strip = page.locator(STRIP)
    expect(strip).to_be_visible()
    expect(strip).to_contain_text("Last found")
    expect(strip).to_contain_text("#99 Some Brand PLA (Red)")
    expect(page.locator(STATUS)).to_contain_text("No label was read for #99")
    expect(page.locator(BUTTON)).to_have_text("🏷️ Needs a label")
    expect(page.locator(f"{QR} canvas, {QR} img").first).to_be_attached()
    page.wait_for_timeout(100)                  # the QR draws two frames later
    assert page.locator(QR).bounding_box()["height"] >= 80
    assert _on_top(page, BUTTON) and _on_top(page, QR)
    assert page.evaluate("""([s, d]) => document.querySelector(s).getBoundingClientRect().bottom
        <= document.querySelector(d).getBoundingClientRect().top""", [STRIP, DONE])
    assert server.pressed == [{"audit_id": "boot-1", "id": NOT_SCANNED, "found": True}]


def test_the_button_marks_and_undo_that_takes_it_back(page: Page, base_url: str):
    server = _running(page, base_url)
    page.click(tile(NOT_SCANNED))
    page.click(BUTTON)
    expect(page.locator(UNDO)).to_be_visible()
    expect(page.locator(tile(NOT_SCANNED))).to_contain_text("needs a label")
    assert server.scans == ["CMD:AUDIT", MARK]
    page.click(UNDO)
    expect(page.locator(UNDO)).to_have_count(0)
    assert server.undone == [{"audit_id": "boot-1", "id": NOT_SCANNED}]
    page.wait_for_function("(m) => Array.from(document.querySelectorAll('#toast-container .toast-msg'))"
                           ".some((e) => e.innerText === m)", arg="Undone: #99 has no label status again.")


def test_n_acts_on_the_real_page(page: Page, base_url: str):
    server = _running(page, base_url)
    page.click(tile(NOT_SCANNED))
    page.wait_for_selector(BUTTON)
    page.keyboard.press("n")
    expect(page.locator(UNDO)).to_be_visible()
    assert server.scans == ["CMD:AUDIT", MARK]
    assert page.evaluate("state.scanBuffer") == ""


def test_n_inside_a_scan_marks_nothing_and_the_scan_arrives_whole(page: Page, base_url: str):
    server = _running(page, base_url)
    page.click(tile(NOT_SCANNED))
    page.wait_for_selector(BUTTON)
    server.answers["loc:north"] = {"type": "error", "msg": "Already auditing LR-MDB-1. Finish first!"}
    _scan_keys(page, "loc:north")
    expect(page.locator("#fcc-audit-panel-notice")).to_contain_text("Already auditing")
    page.wait_for_timeout(220)                  # past the wait key N takes
    assert server.scans == ["CMD:AUDIT", "loc:north"]


def test_a_press_finds_a_second_press_unfinds_and_a_scan_never_does(page: Page, base_url: str):
    server = _running(page, base_url)
    target = page.locator(tile(NOT_SCANNED))
    target.click()
    expect(target).to_contain_text("found, no label read")
    _scan_keys(page, f"ID:{NOT_SCANNED}")       # answered, and nothing turns
    page.wait_for_function("() => !state.processing")
    expect(target).to_contain_text("found, no label read")
    page.wait_for_timeout(750)                  # past a double press
    target.click()
    expect(target).to_contain_text("not scanned")
    expect(page.locator(STRIP)).to_have_count(0)
    assert [(p["id"], p["found"]) for p in server.pressed] == [(NOT_SCANNED, True), (NOT_SCANNED, False)]
    assert server.scans == ["CMD:AUDIT", f"ID:{NOT_SCANNED}"]


def test_enter_presses_a_tile_through_the_real_accumulator(page: Page, base_url: str):
    server = _running(page, base_url)
    page.focus(tile(NOT_SCANNED))
    page.keyboard.press("Enter")
    expect(page.locator(tile(NOT_SCANNED))).to_contain_text("found, no label read")
    assert len(server.pressed) == 1


def test_the_tiles_are_clear_of_the_panels_edges_on_a_small_laptop(page: Page, base_url: str):
    """The panel's width and the grid's columns, with the real Bootstrap."""
    page.set_viewport_size({"width": 1366, "height": 768})
    _running(page, base_url)
    box = page.evaluate("""(sel) => { const t = document.querySelector(sel).getBoundingClientRect();
        const p = document.querySelector('#fcc-audit-panel-body').getBoundingClientRect();
        return { left: t.left - p.left, right: p.right - t.right }; }""", tile(NOT_SCANNED))
    assert box["left"] >= 0 and box["right"] >= 0, box


# --- no stubs ------------------------------------------------------------------------

def _extra(spoolman: str, sid: int) -> dict:
    rec = requests.get(f"{spoolman}/api/v1/spool/{sid}", timeout=10).json()
    return {k: json.loads(v) for k, v in (rec.get("extra") or {}).items()}


def test_a_real_audit_press_mark_undo_label_read(page: Page, base_url: str, api_base_url: str, require_spoolman: str,
                                                 throwaway_spool_with_extras):
    """Nothing stubbed but the page's buffer, which is dev's shared one. Three throwaway
    spools in an empty place, read back from dev's real Spoolman 0.27: a press writes
    nothing, a mark and its undo leave no trace, and a real label read confirms a
    missing status and leaves a flag up. Cancel moves nothing."""
    spoolman = require_spoolman
    if requests.get(f"{api_base_url}/api/audit_session", timeout=10).json().get("active"):
        pytest.skip("an audit is already running on dev")
    if requests.get(f"{api_base_url}/api/bulk_move_session", timeout=10).json().get("active"):
        pytest.skip("a bulk move is armed on dev")
    place, _slotted = _empty_box(api_base_url, spoolman)
    if not place:
        pytest.skip("dev has no empty box or cart to audit")
    pressed = throwaway_spool_with_extras({}, location=place)["id"]
    confirmed = throwaway_spool_with_extras({}, location=place)["id"]
    flagged = throwaway_spool_with_extras({"needs_label_print": True}, location=place)["id"]
    before = _extra(spoolman, pressed)
    conftest.own_the_buffer(page, [])
    _dashboard(page, base_url)
    page.wait_for_function("() => state.lastAuditState === false", timeout=30_000)
    try:
        page.click(TILE)
        page.wait_for_selector(DONE)
        page.evaluate("(p) => { window.processScan('LOC:' + p, 'keyboard'); }", place)
        expect(page.locator("#fcc-audit-panel-tally")).to_contain_text(f"Auditing {place}")   # above the list (2026-11-03)

        target = page.locator(tile(pressed))
        target.click()
        expect(target).to_contain_text("found, no label read")
        expect(page.locator(STATUS)).to_contain_text(f"No label was read for #{pressed}")
        assert _extra(spoolman, pressed) == before

        page.click(BUTTON)
        expect(page.locator(UNDO)).to_be_visible(timeout=15_000)
        assert _extra(spoolman, pressed)["needs_label_print"] is True
        assert {k: v for k, v in _extra(spoolman, pressed).items() if k != "needs_label_print"} == before
        page.click(UNDO)
        expect(page.locator(UNDO)).to_have_count(0, timeout=15_000)
        assert "needs_label_print" not in _extra(spoolman, pressed)
        assert _extra(spoolman, pressed) == before

        # A real label read, at a scanner's speed through the real accumulator.
        page.evaluate(SCANNER, f"ID:{confirmed}")
        expect(page.locator(STATUS)).to_contain_text(f"#{confirmed}'s label was read", timeout=15_000)
        assert _extra(spoolman, confirmed)["needs_label_print"] is False
        page.evaluate(SCANNER, f"ID:{flagged}")
        expect(page.locator(STATUS)).to_contain_text(f"#{flagged} is still flagged for a new label", timeout=15_000)
        assert _extra(spoolman, flagged)["needs_label_print"] is True

        page.click("#fcc-audit-panel-cancel")
        expect(page.locator(PANEL)).to_have_count(0, timeout=5_000)
    finally:
        if requests.get(f"{api_base_url}/api/audit_session", timeout=10).json().get("active"):
            requests.post(f"{api_base_url}/api/identify_scan", json={"text": "CMD:CANCEL"}, timeout=10)
