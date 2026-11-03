"""Derek's answers of 2026-11-03 on Group 58, C (built for his look, in commits of its own
so it can come out): Done's question on the real dashboard, with Bootstrap and the page's
own polls, at the window and text sizes Derek uses. C's stays carry long reasons ("loaded
on XL-1: an audit never takes a spool off a printer") and its question a third section;
each line used to be one row that never wrapped, so names and reasons were cut at every
size, with the whole text only in the line's title, which a touch screen can't show
(review of 7e3720f, P-3). Nothing is cut now, and the Yes, Back and both QRs stay
reachable, in view or by the question's own scroll.

FCC's routes are answered in this browser on their real shapes (test_audit_done_question_
58_e2e's `Asked`: Done answers with the question, and every write is answered here), so
nothing reaches dev but reads. The question's words and Yes are proved on the real routes
in test_audit_file_extras_page_58_js.py.

RED on dc83196 unless a test says it pins what was already right.
"""
from __future__ import annotations

import pytest
from playwright.sync_api import Page

from test_audit_done_question_58_e2e import AUDIT_ID, BACK, QRS, QUESTION, SHEET, YES, Asked, _ask, _on_top
from test_audit_page_58_e2e import _dashboard, _start
from test_audit_question_dialog_58_js import CUT, LONG_QUESTION

pytestmark = pytest.mark.usefixtures("require_server")

# C's real reasons and long names in every list, for this page's audit.
LONG = dict(LONG_QUESTION, audit_id=AUDIT_ID)

SIZES = [(1600, 1300, "Standard"), (1366, 768, "Standard"), (390, 844, "Standard"), (1366, 768, "Extra Large")]


def _writes_answered_here(route):
    """Every request that isn't a GET is answered in this browser: nothing is written to dev."""
    if route.request.method == "GET":
        route.continue_()
        return
    route.fulfill(status=200, content_type="application/json", body='{"success": true, "status": "success"}')


def _asked(page: Page, base_url: str, width: int, height: int, size: str, question=None):
    page.set_viewport_size({"width": width, "height": height})
    page.add_init_script("(() => { try { localStorage.setItem('fcc.textSize', %r); } catch (e) {} })();" % size)
    page.route("**/*", _writes_answered_here)    # first: the harness's own routes, added after, win
    server = Asked(page, question or LONG)
    _dashboard(page, base_url)
    _start(page)
    _ask(page)
    page.wait_for_selector(QRS)
    page.wait_for_timeout(250)                   # the QR codes draw two frames later, then the fit
    return server


def _reachable(page: Page):
    """The Yes, Back and both QRs: in view, or once the question is scrolled to its end."""
    if page.evaluate("(s) => document.querySelector(s).classList.contains('fcc-question-scroll')", SHEET):
        page.evaluate("(s) => { const p = document.querySelector(s); p.scrollTop = p.scrollHeight; }", SHEET)
        page.wait_for_timeout(50)
    got = page.evaluate("""([qrs, sheet]) => { const r = document.querySelector(qrs).getBoundingClientRect();
        const p = document.querySelector(sheet);
        return { top: r.top, bottom: r.bottom, vh: innerHeight, n: document.querySelectorAll(qrs + ' canvas, ' + qrs + ' img').length,
                 sideways: p.scrollWidth > p.clientWidth + 1 }; }""", [QRS, SHEET])
    assert got["top"] >= 0 and got["bottom"] <= got["vh"] and not got["sideways"], got
    assert _on_top(page, YES) and _on_top(page, BACK)


@pytest.mark.parametrize("width, height, size", SIZES)
def test_nothing_in_dones_question_is_cut(page: Page, base_url: str, width, height, size):
    """P-3: every name and every reason reads whole, at each size, and the question's
    answers stay reachable."""
    server = _asked(page, base_url, width, height, size)
    assert page.evaluate(CUT, QUESTION) == []
    assert page.evaluate("(q) => document.querySelectorAll(q + ' .fcc-apc-line').length", QUESTION) == 8
    _reachable(page)
    assert server.parks == []


@pytest.mark.parametrize("width, height, size", [(1600, 1300, "Standard"), (1366, 768, "Extra Large")])
def test_a_list_alone_in_the_last_row_takes_the_whole_width(page: Page, base_url: str, width, height, size):
    """P-3: the third list sat alone in half of the grid's second row, beside an empty
    column, and its reasons were cut at the column's edge."""
    _asked(page, base_url, width, height, size)
    got = page.evaluate("""(q) => { const s = document.querySelectorAll(q + ' .fcc-apc-section');
        const box = document.querySelector(q + ' .fcc-apc-sections').getBoundingClientRect();
        return { n: s.length, first: s[0].getBoundingClientRect().width, last: s[2].getBoundingClientRect().width,
                 row: Math.round(s[0].getBoundingClientRect().top) === Math.round(s[1].getBoundingClientRect().top),
                 box: box.width }; }""", QUESTION)
    assert got["n"] == 3 and got["row"], got                  # two side by side, then the third
    assert got["first"] < got["box"] / 2 and abs(got["last"] - got["box"]) <= 1, got


def test_a_reason_that_fits_stays_on_its_names_line(page: Page, base_url: str):
    """Pins what the change keeps: a line that fits is one row, its reason at its end, so a
    question with short lines is as short as it was (a scanner can't read a QR that has
    scrolled away)."""
    short = dict(LONG, stays=[{"id": 304, "display": "#304 Some Brand PLA (White)", "where": "CR-CT-1",
                               "why": "in the scan buffer"}])
    _asked(page, base_url, 1366, 768, "Standard", short)
    got = page.evaluate("""(q) => { const l = Array.from(document.querySelectorAll(q + ' .fcc-apc-line'))
            .find((e) => e.textContent.includes('#304'));
        const t = l.querySelector('.fcc-apc-line-text').getBoundingClientRect();
        const w = l.querySelector('.fcc-apc-line-where').getBoundingClientRect();
        return { sameRow: Math.abs(t.top - w.top) < 4, whereRight: w.right, lineRight: l.getBoundingClientRect().right }; }""",
                        QUESTION)
    assert got["sameRow"] and abs(got["whereRight"] - got["lineRight"]) <= 1, got
