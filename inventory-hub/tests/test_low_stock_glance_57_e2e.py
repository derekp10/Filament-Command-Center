"""Group 57.2: the ⚠️ Low stock button inside the real dashboard (needs the dev
container; skipped under --offline). Read-only: every write the page makes is
answered in the browser (test_text_size_guard._read_only), and the reads are
dev's own heartbeat and Low-stock list, or stubs.

Pinned: the button sits in the title bar between 🛒 Queue and ?; its count is
the list's Low + Out (the real heartbeat against the real /api/stock_report);
it opens the list on its own, and the list it reads sets the count; a heartbeat
that couldn't read draws "?" before any count, and "12?" with a dashed border
after one, as the 🏷️ Backlog count does, and a blip moves nothing on the bar
(the "?" takes no room); on the real page (Bootstrap loaded) the list doesn't
move when it arrives, and "/" while it reads leaves the list open and the
search panel shut.
The panel and the button themselves are pinned hermetically by
test_low_stock_glance_57_js.py and test_low_stock_panel.py; the bar at every
Text size by test_text_size_setting_e2e.py; its contrast by
test_contrast_guard.py.
"""
from __future__ import annotations

import json
import re

import pytest
from playwright.sync_api import Page, expect

from conftest import quiet_heartbeat
from test_text_size_guard import _read_only

BTN = "#btn-low-stock-count"
NUM = BTN + " [data-low-stock-count]"
PANEL = "#fcc-low-stock-overlay .fcc-stock-panel"
BODY = "#fcc-low-stock-overlay [data-stock-body]"

REPORT = {
    "success": True, "threshold_g": 250.0, "filaments": 3, "spools": 6, "excluded": [],
    "low": [{"filament_id": 164, "display": "Prusament - PLA - Galaxy Black", "color": "222222",
             "color_direction": "longitudinal", "grams": 151.0, "spools": 1, "spools_total": 3,
             "attributes": [], "excluded": None, "buy_url": None},
            {"filament_id": 88, "display": "Overture - PETG - Red Blue", "color": "BA0C2F,0047BB",
             "color_direction": "coaxial", "grams": 220.4, "spools": 2, "spools_total": 2,
             "attributes": [], "excluded": None, "buy_url": None}],
    "out": [{"filament_id": 20, "display": "Generic - PLA - Lipstick Red", "color": "ff0000",
             "color_direction": "longitudinal", "grams": 0, "spools": 0, "spools_total": 2,
             "attributes": [], "excluded": None, "buy_url": None}],
}


# The count as the button says it: the total (painted in both of its forms,
# Group 57.3) and a "?" when the form shown has its stale mark.
COUNT_JS = """(sel) => { const b = document.querySelector(sel);
    const total = b.querySelector('[data-low-stock-count]').textContent.trim();
    const mark = Array.from(b.querySelectorAll('.fcc-tb-count > .fcc-stale-mark')).some((m) => m.getClientRects().length);
    return total + (mark ? '?' : ''); }"""


def _count(page):
    return page.evaluate(COUNT_JS, BTN)


def _wait_count(page, pattern):
    page.wait_for_function("([js, sel, re]) => new RegExp(re).test((0, eval)('(' + js + ')')(sel))",
                           arg=[COUNT_JS, BTN, pattern], timeout=20_000)


def _painted(page):
    # Painted once its painter has dropped the placeholder's marker (titlebar_fit.js).
    page.wait_for_function("(s) => { const n = document.querySelector(s); return !!n && !n.hasAttribute('data-count-pending'); }",
                           arg=NUM, timeout=20_000)
    return _count(page)


@pytest.mark.usefixtures("require_server")
def test_the_button_sits_between_queue_and_help(page: Page, base_url: str):
    _read_only(page)
    page.goto(base_url)
    _painted(page)
    boxes = page.evaluate("""() => ['btn-queue-count', 'btn-low-stock-count', 'btn-shortcuts-help'].map((id) => {
        const r = document.getElementById(id).getBoundingClientRect(); return [r.left, r.right, r.top, r.height]; })""")
    (q_l, q_r, q_t, _), (l_l, l_r, l_t, l_h), (h_l, _h_r, h_t, _) = boxes
    assert q_r <= l_l and l_r <= h_l, boxes
    assert abs(q_t - l_t) < 2 and abs(h_t - l_t) < 2 and l_h >= 30, boxes


@pytest.mark.usefixtures("require_server")
def test_the_count_is_the_lists_low_and_out(page: Page, base_url: str):
    """The real heartbeat's count against the real list (both read from dev
    Spoolman; nothing is written). They are read at different moments, so a
    count dev's data moved in between gets a few heartbeats to agree."""
    _read_only(page)
    page.goto(base_url)
    _painted(page)
    btn = page.locator(BTN)
    seen = []
    for _ in range(4):
        report = page.evaluate("() => fetch('/api/stock_report', {cache: 'no-store'}).then((r) => r.json())")
        assert report.get("success") is True, report
        low, out = len(report["low"]), len(report["out"])
        shown = _count(page)
        seen.append((shown, low, out))
        assert not shown.endswith("?"), f"the heartbeat couldn't count (dev Spoolman slow?): {seen}"
        if shown == str(low + out):
            assert (btn.get_attribute("data-low"), btn.get_attribute("data-out")) == (str(low), str(out))
            # Out of the box the button shows Low and Out apart (57.3).
            assert f"Low {low}, Out {out} (" in (btn.get_attribute("aria-label") or "")
            return
        page.wait_for_timeout(6000)                       # one more heartbeat
    pytest.fail(f"the count never matched the list: {seen}")


@pytest.mark.usefixtures("require_server")
def test_it_opens_the_list_and_the_list_sets_the_count(page: Page, base_url: str):
    """Every heartbeat cut off (quiet_heartbeat), so the only count is the
    list's own read: 2 low + 1 out. Until then the button says FCC didn't
    answer, with "?" and no count, never a 0 and never its "–" as if nothing
    had been tried (Group 57 review, round 3). The search panel stays shut."""
    _read_only(page)
    quiet_heartbeat(page)
    page.route("**/api/stock_report", lambda route: route.fulfill(
        status=200, content_type="application/json", body=json.dumps(REPORT)))
    page.goto(base_url)
    page.wait_for_function("() => typeof window.openLowStockPanel === 'function'")
    _wait_count(page, r"^\?$")
    expect(page.locator(BTN)).to_have_attribute("aria-label", re.compile(r"\(FCC didn't answer just now\)"))
    page.locator(BTN).click()
    expect(page.locator(PANEL)).to_be_visible()
    page.wait_for_function("(s) => document.querySelector(s).dataset.stockState === 'ready'", arg=BODY)
    # The list's read sets it; a heartbeat cut off after that read began marks
    # it stale again ("3?"), as it should.
    _wait_count(page, r"^3\??$")
    expect(page.locator(BTN)).to_have_attribute("data-low", "2")
    expect(page.locator(BTN)).to_have_attribute("data-out", "1")
    expect(page.locator("#offcanvasSearch")).not_to_be_visible()
    page.keyboard.press("Escape")
    expect(page.locator("#fcc-low-stock-overlay")).to_have_count(0)


@pytest.mark.usefixtures("require_server")
def test_the_list_doesnt_move_when_it_arrives_on_the_real_page(page: Page, base_url: str):
    """With Bootstrap loaded: its [hidden]{display:none!important} made the
    first fix's tabs row (a [hidden] rule) collapse while the list read, and the
    list jumped 42 px when it arrived (Group 57 review, RED on 2d166e5)."""
    _read_only(page)
    page.add_init_script("""(() => { const real = window.fetch;
        window.fetch = function (url, opts) {
            if (String(url).indexOf('/api/stock_report') === 0) {
                return new Promise((r) => setTimeout(r, 1500)).then(() => real(url, opts));
            }
            return real(url, opts);
        }; })();""")
    page.route("**/api/stock_report", lambda route: route.fulfill(
        status=200, content_type="application/json", body=json.dumps(REPORT)))
    page.goto(base_url)
    page.wait_for_function("() => typeof window.openLowStockPanel === 'function'")
    page.locator(BTN).click()
    expect(page.locator(PANEL)).to_be_visible()
    frame = """(s) => { const p = document.querySelector(s); const b = p.querySelector('[data-stock-body]');
        const t = p.querySelector('[data-stock-tools]');
        return [Math.round(p.getBoundingClientRect().top), Math.round(p.getBoundingClientRect().height),
                Math.round(b.getBoundingClientRect().top), Math.round(t.getBoundingClientRect().height)]; }"""
    assert page.evaluate("(s) => document.querySelector(s).dataset.stockState", BODY) == "loading"
    reading = page.evaluate(frame, PANEL)
    page.wait_for_function("(s) => document.querySelector(s).dataset.stockState === 'ready'", arg=BODY)
    assert page.evaluate(frame, PANEL) == reading
    assert reading[3] > 20, reading                         # the tabs row has its room while it reads


@pytest.mark.usefixtures("require_server")
def test_a_slash_while_it_reads_leaves_the_list_open(page: Page, base_url: str):
    """"/" is the global search key too (fab_drag.js): while the list read it
    went on to the search panel, whose opening closed a list opened from the
    title bar (Group 57 review)."""
    _read_only(page)
    page.add_init_script("""(() => { const real = window.fetch;
        window.fetch = function (url, opts) {
            if (String(url).indexOf('/api/stock_report') === 0) {
                return new Promise((r) => setTimeout(r, 2500)).then(() => real(url, opts));
            }
            return real(url, opts);
        }; })();""")
    page.route("**/api/stock_report", lambda route: route.fulfill(
        status=200, content_type="application/json", body=json.dumps(REPORT)))
    page.goto(base_url)
    page.wait_for_function("() => typeof window.openLowStockPanel === 'function'")
    page.locator(BTN).click()
    expect(page.locator(PANEL)).to_be_visible()
    assert page.evaluate("(s) => document.querySelector(s).dataset.stockState", BODY) == "loading"
    page.keyboard.press("/")
    page.wait_for_timeout(600)
    expect(page.locator(PANEL)).to_be_visible()
    expect(page.locator("#offcanvasSearch")).not_to_be_visible()


@pytest.mark.usefixtures("require_server")
def test_a_count_that_could_not_be_read_again_looks_stale(page: Page, base_url: str):
    """After a good count, a heartbeat that couldn't read keeps it with a "?"
    after it and a dashed border (Group 57 review: it looked exactly like a
    fresh one)."""
    _read_only(page)
    failing = {"on": False}

    def pulse(route):
        resp = route.fetch()
        body = resp.json()
        if failing["on"] and "low_stock" in body:
            body["low_stock"] = {"read_ok": False, "read_error": "couldn't read Spoolman's spools (test)"}
        route.fulfill(response=resp, body=json.dumps(body))
    page.route("**/api/dashboard_pulse*", pulse)
    page.goto(base_url)
    good = _painted(page)
    assert good.isdigit(), good
    failing["on"] = True
    page.wait_for_function("(s) => document.querySelector(s).dataset.read === 'failed'", arg=BTN, timeout=20_000)
    assert _count(page) == good + "?"
    assert page.evaluate("(s) => getComputedStyle(document.querySelector(s)).borderTopStyle", BTN) == "dashed"


@pytest.mark.usefixtures("require_server")
def test_a_heartbeat_that_could_not_read_draws_a_question_mark(page: Page, base_url: str):
    """Before any count, a failed read is "?", never 0 (Group 52's rule)."""
    _read_only(page)

    def pulse(route):
        resp = route.fetch()
        body = resp.json()
        if "low_stock" in body:
            body["low_stock"] = {"read_ok": False, "read_error": "couldn't read Spoolman's spools (test)"}
        route.fulfill(response=resp, body=json.dumps(body))
    page.route("**/api/dashboard_pulse*", pulse)
    page.goto(base_url)
    assert _painted(page) == "?"
    assert page.locator(BTN).get_attribute("data-read") == "failed"


@pytest.mark.usefixtures("require_server")
def test_a_blip_moves_nothing_on_the_bar(page: Page, base_url: str):
    """At Standard on a 1600 px window (Derek's) the bar has a few px to spare.
    The "?" of a stale count made the button 7 px wider, the bar took its first
    step (titlebar_fit.js) and gave it back on the next good read: SEARCH moved
    112 px and back on every Spoolman blip (Group 57 review, round 2). The "?"
    is drawn in the button's padding now. The counts are fixed (Backlog 53,
    Queue 0, Low stock 12) and the failed reads stubbed, in this page only."""
    _read_only(page)
    failing = {"on": False}
    down = {"read_ok": False, "read_error": "couldn't read Spoolman's spools (test)"}

    def pulse(route):
        resp = route.fetch()
        body = resp.json()
        if "label_backlog" in body:
            body["label_backlog"] = down if failing["on"] else {"read_ok": True, "count": 53, "spools": 53,
                                                                 "filaments": 0}
        if "low_stock" in body:
            body["low_stock"] = down if failing["on"] else {"read_ok": True, "count": 12, "low": 1, "out": 11,
                                                             "threshold_g": 250.0}
        route.fulfill(response=resp, body=json.dumps(body))

    def queue(route):
        body = "[]" if route.request.method == "GET" else '{"success": true}'
        route.fulfill(status=200, content_type="application/json", body=body)
    page.route("**/api/dashboard_pulse*", pulse)
    page.route("**/api/state/queue", queue)
    page.goto(base_url)
    _wait_count(page, r"^12$")
    page.wait_for_function("() => /\\(53\\)/.test(document.getElementById('btn-backlog-count').textContent)",
                           timeout=20_000)
    page.wait_for_timeout(300)
    where = """() => { const bar = document.querySelector('.fcc-titlebar');
        const xs = Array.from(document.querySelectorAll('.fcc-titlebar-actions > *')).map((el) =>
            Math.round(el.getBoundingClientRect().left * 10) / 10);
        return { steps: ['fcc-tb-tight', 'fcc-tb-icons', 'fcc-tb-add', 'fcc-tb-shortver', 'fcc-tb-wrap'].filter((c) => bar.classList.contains(c)),
                 xs, width: document.getElementById('btn-low-stock-count').getBoundingClientRect().width }; }"""
    fresh = page.evaluate(where)
    failing["on"] = True
    page.wait_for_function("() => ['btn-low-stock-count', 'btn-backlog-count'].every((id) =>"
                           " document.getElementById(id).dataset.read === 'failed')", timeout=20_000)
    page.wait_for_timeout(300)
    stale = page.evaluate(where)
    assert _count(page) == "12?"
    assert "(53)?" in page.locator("#btn-backlog-count").text_content()
    assert stale == fresh, (fresh, stale)
    for sel in (BTN, "#btn-backlog-count"):
        box = page.evaluate("""(sel) => { const b = document.querySelector(sel); const m = b.querySelector('.fcc-stale-mark');
            const r = b.getBoundingClientRect(); const mr = m.getBoundingClientRect();
            return { inside: mr.right <= r.right - parseFloat(getComputedStyle(b).borderRightWidth) + 0.01,
                     dashed: getComputedStyle(b).borderTopStyle }; }""", sel)
        assert box == {"inside": True, "dashed": "dashed"}, (sel, box)
