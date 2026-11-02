"""Group 58, build spec section 7: the audit panel, its notice and its pill on a real
DOM, hermetic: the REAL overlay_mount.js, inv_core.js, inv_cmd.js, draggable_pill.js
and fab_drag.js, the real scan accumulator, global.css and the pill's and the deck
tile's own markup from dashboard.html, in `isolated_page` (no route to any network),
so it runs under --offline. test_audit_page_58_js.py has the logic on the stub DOM;
test_audit_page_58_e2e.py the real dashboard, with Bootstrap.

RED on 25738af unless a test says it pins what was already right.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from test_audit_page_58_js import SESSION
from test_scanner_safe_dialogs_61_js import MODULES, page61  # noqa: F401  (page61: the fixture)

HUB = Path(__file__).resolve().parent.parent
PANEL = "#fcc-audit-panel-overlay"
PILL = "#fcc-audit-pill"
TILE = "#btn-deck-audit"
NOTICE = "#fcc-audit-panel-notice"
NOTE = "#fcc-audit-panel-note"
DONE = "#fcc-audit-panel-done"
CANCEL = "#fcc-audit-panel-cancel"
REFUSED = "Already auditing LR-MDB-1. Finish first!"
AUDIT_SCAN = {"type": "command", "cmd": "audit_scan"}


def _dashboard_markup():
    """The pill and the deck tile, as the page has them."""
    src = (HUB / "templates" / "dashboard.html").read_text(encoding="utf-8")
    pill = re.search(r'<button type="button" id="fcc-audit-pill".*?</button>', src, re.S)
    tile = re.search(r'<div id="btn-deck-audit".*?</div>\s*</div>', src, re.S)
    assert pill and tile
    return f'<div class="cmd-deck">{tile.group(0)}</div>{pill.group(0)}'


@pytest.fixture
def audit(page61):
    """A running audit with its panel up: `window.__session` is what
    /api/audit_session answers, and `window.__held`, when set, holds a scan's answer
    until `window.__release()`."""
    page = page61
    page.add_style_tag(content=(HUB / "static" / "css" / "global.css").read_text(encoding="utf-8"))
    page.evaluate("""(markup) => {
        document.body.insertAdjacentHTML('beforeend', markup);
        // about:blank has no localStorage of its own.
        const kept = {};
        Object.defineProperty(window, 'localStorage', { configurable: true, value: {
            getItem: (k) => (k in kept ? kept[k] : null), setItem: (k, v) => { kept[k] = String(v); } } });
        const answers = window.fetch;
        window.__session = null;
        window.__sessionReads = 0;
        window.fetch = (url, opts) => {
            if (String(url).indexOf('/api/audit_session') !== -1) {
                window.__sessionReads += 1;
                return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(window.__session) });
            }
            const answered = answers(url, opts);
            if (window.__held && String(url).indexOf('/api/identify_scan') !== -1) {
                return new Promise((resolve) => { window.__release = () => resolve(answered); });
            }
            return answered;
        };
    }""", _dashboard_markup())
    page.add_script_tag(content=(MODULES / "fab_drag.js").read_text(encoding="utf-8"))
    page.evaluate("""(session) => {
        window.__session = session;
        window.__pillAtLoad = getComputedStyle(document.getElementById('fcc-audit-pill')).display;
        window.__answers['LOC:LR-MDB-2'] = { type: 'error', msg: 'Already auditing LR-MDB-1. Finish first!' };
        window.__answers['ID:57'] = { type: 'command', cmd: 'audit_scan' };
        window.__answers['CMD:DONE'] = { type: 'error', msg: 'Try Done again in a moment.' };
        state.auditActive = true;
        state.lastAuditState = true;
        window.updateAuditVisuals();
    }""", SESSION)
    page.wait_for_selector(DONE)
    return page


def _on_top(page, selector):
    return page.evaluate("""(sel) => { const el = document.querySelector(sel);
        const r = el.getBoundingClientRect();
        return el.contains(document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2)); }""", selector)


def _refuse(page):
    page.evaluate("window.processScan('LOC:LR-MDB-2', 'barcode')")
    page.wait_for_function("(sel) => document.querySelector(sel).textContent.length > 0", arg=NOTICE)


def _redraw(page, note):
    page.evaluate("(note) => { window.__session = Object.assign({}, window.__session, { note }); window.refreshAuditSession(); }", note)
    page.wait_for_function("([sel, note]) => document.querySelector(sel).textContent === note", arg=[NOTE, note])


def test_a_refusal_is_said_on_top_of_the_panel_and_a_redraw_keeps_it(audit):
    """The toast layer (z 11000) is under the panel (z 20000), so a refusal was said
    where nobody could read it."""
    _refuse(audit)
    assert audit.is_visible(NOTICE) and _on_top(audit, NOTICE)
    assert audit.get_attribute(NOTICE, "role") == "alert"
    assert audit.text_content(NOTICE) == REFUSED
    _redraw(audit, "A new note")
    assert audit.text_content(NOTICE) == REFUSED and audit.is_visible(NOTICE)


def test_a_good_scan_takes_the_notice_away(audit):
    _refuse(audit)
    audit.evaluate("window.processScan('ID:57', 'barcode')")
    audit.wait_for_function("(sel) => !document.querySelector(sel).textContent", arg=NOTICE)
    assert not audit.is_visible(NOTICE)


def test_the_note_stays_in_view_however_long_the_list_is(audit):
    """Outside the scrolling body: with a room's tiles the body scrolls it away."""
    audit.evaluate("""() => { const row = window.__session.expected[0];
        window.__session = Object.assign({}, window.__session, { note: 'A note',
            expected: Array.from({ length: 200 }, (_, i) => Object.assign({}, row, { id: 1000 + i, display: '#' + (1000 + i) })) });
        window.refreshAuditSession(); }""")
    audit.wait_for_function("() => document.querySelectorAll('#fcc-audit-panel-body [title]').length >= 200")
    audit.evaluate("() => { document.getElementById('fcc-audit-panel-body').scrollTop = 100000; }")
    assert audit.is_visible(NOTE) and _on_top(audit, NOTE)


def test_hide_then_the_tile_brings_it_back_and_sends_nothing(audit):
    """The tile read FINISH, and a click on it sent CMD:CANCEL."""
    audit.click("#fcc-audit-panel-close")
    audit.wait_for_selector(PANEL, state="detached")
    audit.click(TILE)
    audit.wait_for_selector(DONE)
    assert audit.evaluate("window.__ids") == []
    assert audit.evaluate("state.auditActive") is True


def test_escape_is_a_hide_too_and_the_pill_brings_it_back(audit):
    assert audit.is_hidden(PANEL) is False
    audit.keyboard.press("Escape")
    audit.wait_for_selector(PANEL, state="detached")
    assert audit.is_visible(PILL) and _on_top(audit, PILL)
    audit.click(PILL)
    audit.wait_for_selector(DONE)
    assert audit.evaluate("window.__ids") == []


def test_with_no_audit_there_is_no_pill(audit):
    assert audit.evaluate("window.__pillAtLoad") == "none"


def test_the_pill_says_what_runs_and_goes_with_the_audit(audit):
    audit.click("#fcc-audit-panel-close")
    assert audit.inner_text(PILL).split() == ["🕵️", "audit:", "LR-MDB-1"]
    assert audit.get_attribute(PILL, "title").startswith("An audit is running")
    audit.evaluate("""() => { window.__answers['CMD:CANCEL'] = { type: 'command', cmd: 'audit_scan',
        audit_ended: { id: 'boot-1', why: 'cancel' } }; window.processScan('CMD:CANCEL', 'barcode'); }""")
    audit.wait_for_selector(PILL, state="hidden")


def test_the_pill_drags_and_remembers_and_a_drag_opens_nothing(audit):
    audit.click("#fcc-audit-panel-close")
    box = audit.locator(PILL).bounding_box()
    x, y = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
    audit.mouse.move(x, y)
    audit.mouse.down()
    audit.mouse.move(x - 120, y - 60, steps=4)
    audit.mouse.up()
    assert not audit.locator(PANEL).count()
    saved = audit.evaluate("JSON.parse(localStorage.getItem('fcc.auditPill.pos'))")
    moved = audit.locator(PILL).bounding_box()
    assert round(saved["left"]) == round(moved["x"])
    assert abs(moved["x"] - (box["x"] - 120)) <= 1 and abs(moved["y"] - (box["y"] - 60)) <= 1


def test_the_pill_answers_a_persons_enter_and_not_a_scans(audit):
    """Pins draggable_pill.js's rule (Group 61) on the new pill."""
    audit.click("#fcc-audit-panel-close")
    audit.focus(PILL)
    audit.keyboard.type("ID:57", delay=0)
    audit.keyboard.press("Enter")
    audit.wait_for_function("() => window.__ids.length === 1")
    assert not audit.locator(PANEL).count()
    assert audit.evaluate("window.__ids") == [{"text": "ID:57", "source": "barcode"}]
    audit.wait_for_timeout(150)          # past a scanner's second Enter
    audit.focus(PILL)
    audit.keyboard.press("Enter")
    audit.wait_for_selector(DONE)


def test_a_long_place_stays_on_screen(audit):
    """A rem cap, and the words clipped: the pill is the way back to the panel."""
    audit.click("#fcc-audit-panel-close")
    audit.evaluate("() => { state.auditLocation = 'A-PLACE-WITH-A-VERY-LONG-NAME-'.repeat(6); window.updateAuditPill(); }")
    box = audit.locator(PILL).bounding_box()
    viewport = audit.viewport_size
    assert box["x"] >= 0 and box["x"] + box["width"] <= viewport["width"]


def test_enter_on_done_presses_it_once(audit):
    """Pins Group 50.6's rule on the new button: a person's Enter presses it, and a
    held key's repeats don't."""
    audit.evaluate("() => { window.__held = true; }")
    audit.focus(DONE)
    audit.keyboard.press("Enter")
    audit.wait_for_function("() => window.__ids.length === 1")
    assert audit.is_disabled(DONE) and audit.is_disabled(CANCEL)
    audit.keyboard.down("Enter")
    audit.keyboard.down("Enter")
    audit.keyboard.up("Enter")
    assert audit.evaluate("window.__ids") == [{"text": "CMD:DONE", "source": "keyboard"}]
    audit.evaluate("window.__release()")
    audit.wait_for_function("(sel) => !document.querySelector(sel).disabled", arg=DONE)


def test_the_keyboard_comes_back_with_the_answer(audit):
    """A disabled button drops the focus, and a Done the server refused is pressed
    again from where it was."""
    audit.evaluate("() => { window.__held = true; }")
    audit.focus(DONE)
    audit.keyboard.press("Enter")
    audit.wait_for_function("() => window.__ids.length === 1")
    audit.evaluate("window.__release()")
    audit.wait_for_function("(sel) => !document.querySelector(sel).disabled", arg=DONE)
    assert audit.evaluate("document.activeElement.id") == DONE[1:]


def test_a_redraw_while_the_answer_is_out_keeps_the_buttons_down(audit):
    """A scan's answer redraws the body, with new buttons."""
    audit.evaluate("() => { window.__held = true; }")
    audit.click(DONE)
    audit.wait_for_function("() => window.__ids.length === 1")
    _redraw(audit, "A new note")
    assert audit.is_disabled(DONE) and audit.is_disabled(CANCEL)
    audit.evaluate("window.__release()")
    audit.wait_for_function("(sel) => !document.querySelector(sel).disabled", arg=DONE)


def test_a_redraw_keeps_the_keyboard_on_done_or_cancel(audit):
    """Every scan rewrites the body, and Done went with it. The next Enter went
    to the page."""
    audit.focus(CANCEL)
    _redraw(audit, "A new note")
    assert audit.evaluate("document.activeElement.id") == CANCEL[1:]


def test_a_scans_enter_on_done_presses_nothing(audit):
    """Pins Group 50.6's rule on the new button: CMD:DONE's own Enter ends the scan."""
    audit.focus(DONE)
    audit.keyboard.type("ID:57", delay=0)
    audit.keyboard.press("Enter")
    audit.wait_for_function("() => window.__ids.length === 1")
    assert audit.evaluate("window.__ids") == [{"text": "ID:57", "source": "barcode"}]
