"""Group 57.2: the ⚠️ Low stock button in the title bar, hermetic.

Runs the REAL overlay_mount.js, inv_core.js and inv_stock.js with the real
static/css/global.css and the button's real markup (lifted from
templates/dashboard.html) in `isolated_page` (a chromium with no route to any
network), so it RUNS under --offline. `fetch` is stubbed in the page:
/api/dashboard_pulse answers window.__pulse, /api/stock_report the queue in
window.__answers, and the exclusion writes window.__writeAnswers.

Pinned: the heartbeat's low_stock section paints the count (one number, Low +
Out) with the words in the tooltip and the accessible name, which holds the
number shown; a failed read keeps the last count with a "?" after it that takes
no room, and says why (Spoolman, FCC's own count, or no count sent), and before
any count reads "?" (never 0); reads are kept in order by when each was sent,
either way round (a heartbeat sent before the list's own read began never
paints over it, nor the list's read over a heartbeat sent after it began; a
failure older than the count shown is ignored, and a newer one keeps the
count's "?"), on the page's own clock, which a wall-clock step can't move; the
tick passes its send time; a click or Space opens the list on its own (no
search panel to host it), Space leaves no space in the scan buffer, a window
opened over the list closes it, Escape gives the focus back to the button (a
list that came back included), and "/" while it reads, and "/" or Ctrl+K while
the reason dialog is up, stay in the list; the list it reads, and a change made
there, set the count too; the tick asks for low_stock only when the button is
on the page and the backlog window is shut, and hands the section to it (or
marks the count stale when the answer had none).

The button over the real dashboard (Bootstrap's colours, the title bar at every
Text size) is covered by test_low_stock_glance_57_e2e.py,
test_contrast_guard.py and test_text_size_setting_e2e.py (they need the
container).
"""
from __future__ import annotations

import copy
import json
import re
from pathlib import Path

import pytest

HUB = Path(__file__).resolve().parent.parent
MODULES = HUB / "static" / "js" / "modules"
GLOBAL_CSS = HUB / "static" / "css" / "global.css"
DASHBOARD = HUB / "templates" / "dashboard.html"
BTN = "#btn-low-stock-count"
NUM = BTN + " [data-low-stock-count]"
PANEL = "#fcc-low-stock-overlay .fcc-stock-panel"
BODY = "#fcc-low-stock-overlay [data-stock-body]"


def _button_markup():
    html = DASHBOARD.read_text(encoding="utf-8")
    m = re.search(r'<button[^>]*id="btn-low-stock-count".*?</button>', html, re.S)
    assert m, "dashboard.html has no #btn-low-stock-count"
    return m.group(0)


PRELUDE = r"""
window.__pendingShortcuts = [];
window.registerShortcut = function (s) { window.__pendingShortcuts.push(s); };
window.__pulse = [];
window.__pulseUrls = [];
window.__answers = [];
window.__reports = 0;
window.__writeAnswers = [];
window.__sent = [];
window.__opened = [];
// What reached the page past the list's own key handler (the global search's
// '/' sits there on the real page: fab_drag.js).
window.__slashPassed = 0;
document.addEventListener('keydown', (e) => { if (e.key === '/') window.__slashPassed += 1; });
window.__backlogAnswers = [];
window.__backlogUrls = [];
const __take = (q) => (q.length > 1 ? q.shift() : q[0]);
const __respond = (a) => {
    // a.hang: a request that never settles (a link dropped without closing it).
    if (a && a.hang) return new Promise(() => {});
    // a.network: no answer at all (after a.delay, if it has one).
    // a.notJson: an error page that isn't JSON (a proxy's 502, say).
    const go = () => (!a || a.network) ? Promise.reject(new TypeError('Failed to fetch'))
        : Promise.resolve({ ok: a.status >= 200 && a.status < 300, status: a.status,
                            json: () => (a.notJson ? Promise.reject(new SyntaxError("Unexpected token '<'"))
                                : Promise.resolve(JSON.parse(JSON.stringify(a.body)))) });
    return a && a.delay ? new Promise((r) => setTimeout(r, a.delay)).then(go) : go();
};
window.fetch = function (url, opts) {
    url = String(url);
    if (url.indexOf('/api/dashboard_pulse') === 0) { window.__pulseUrls.push(url); return __respond(__take(window.__pulse)); }
    if (url.indexOf('/api/stock_report') === 0) { window.__reports += 1; return __respond(__take(window.__answers)); }
    if (url.indexOf('/api/print_queue/pending') === 0) { window.__backlogUrls.push(url); return __respond(__take(window.__backlogAnswers)); }
    if (url.indexOf('/stock_exclusion') >= 0) {
        window.__sent.push({ url, method: (opts && opts.method) || 'GET', body: opts && opts.body ? JSON.parse(opts.body) : null });
        return __respond(__take(window.__writeAnswers));
    }
    return Promise.reject(new TypeError('no network in this test: ' + url));
};
function openFilamentDetails(fid) { window.__opened.push(fid); }
"""

# Bootstrap 5.3's reboot rule, which the real page loads: it made 57.1's first
# "keep the tabs row's room" (a [hidden] rule) do nothing there (Group 57 review).
# And its button box, which a stale count's "?" is drawn in (round 2).
BOOTSTRAP_HIDDEN = ("[hidden]{display:none!important}"
                    ".btn{display:inline-block;padding:.375rem .75rem;font-size:1rem;line-height:1.5;"
                    "border:1px solid transparent;border-radius:.375rem}")

PAGE = """<!doctype html><html><head><meta charset="utf-8"><style>{css}</style></head><body>
<nav class="navbar"><div class="container-fluid fcc-titlebar"><div class="fcc-titlebar-actions">
  <button class="btn btn-info ms-4" id="btn-backlog-count">🏷️ Backlog (0)</button>
  {button}
</div></div></nav>
<div id="offcanvasSearch" class="offcanvas"></div>
<div id="filamentModal" class="modal"></div>
<div id="backlogModal" class="modal"></div>
</body></html>"""


def _row(fid, display, grams, spools, total, marked=None, **more):
    brand, material, colour = display.split(" - ")
    r = {"filament_id": fid, "brand": brand, "material": material, "color_name": colour, "display": display,
         "color": "336699", "color_direction": "longitudinal", "grams": grams, "spools": spools,
         "spools_total": total, "attributes": [], "excluded": marked, "buy_url": None}
    r.update(more)
    return r


REPORT = {
    "success": True, "threshold_g": 250.0, "filaments": 5, "spools": 9,
    "low": [_row(164, "Prusament - PLA - Galaxy Black", 151.0, 1, 3),
            _row(88, "Overture - PETG - Red Blue", 220.4, 2, 2)],
    "out": [_row(20, "Generic - PLA - Lipstick Red", 0, 0, 2),
            _row(29, "Polymaker - PC - Clear", 0, 0, 0, no_spools=True)],
    "excluded": [],
}
MARK = {"reason": "Discontinued", "code": "discontinued", "note": "", "at": "2026-10-26"}


def _answer(body, status=200, **kw):
    a = {"status": status, "body": body}
    a.update(kw)
    return a


@pytest.fixture
def bar(isolated_page):
    page = isolated_page
    page.set_content(PAGE.format(css=GLOBAL_CSS.read_text(encoding="utf-8") + BOOTSTRAP_HIDDEN,
                                 button=_button_markup()))
    page.add_script_tag(content=PRELUDE)
    for name in ("overlay_mount.js", "inv_core.js", "inv_stock.js"):
        page.add_script_tag(content=(MODULES / name).read_text(encoding="utf-8"))
    page.evaluate("() => { window.__toasts = []; window.showToast = (msg, type, ms) => window.__toasts.push({msg, type, ms}); }")
    return page


def _render(page, sec):
    return page.evaluate("(s) => window._renderLowStockCount(s)", sec)


def _btn(page):
    return page.evaluate("""(sel) => { const b = document.querySelector(sel);
        return { num: b.querySelector('[data-low-stock-count]').textContent, text: b.textContent.replace(/\\s+/g, ' ').trim(),
                 title: b.title, label: b.getAttribute('aria-label'), read: b.dataset.read || null,
                 low: b.dataset.low || null, out: b.dataset.out || null }; }""", BTN)


GOOD = {"read_ok": True, "count": 12, "low": 1, "out": 11, "threshold_g": 250.0}
DOWN = {"read_ok": False, "read_error": "couldn't read Spoolman's spools (Spoolman didn't answer)"}


# --- the count -----------------------------------------------------------------------

def test_before_the_first_heartbeat_it_reads_a_dash(bar):
    b = _btn(bar)
    assert b["text"] == "⚠️ –" and b["read"] is None, b
    assert b["label"] == "Low stock: opens the list." == b["title"]
    assert bar.evaluate("(s) => document.querySelector(s).hasAttribute('data-count-pending')", NUM)


# A count's placeholder as its button draws it (the button's markup from
# dashboard.html, in the title bar's font), against the narrowest count it
# stands for: one digit, in brackets where the placeholder has them.
PLACEHOLDER_JS = """(markup) => {
    const wrap = document.createElement('div');
    wrap.className = 'fcc-titlebar-actions';
    wrap.style.cssText = 'position:absolute; left:0; top:0;';
    wrap.innerHTML = markup;
    document.querySelector('.fcc-titlebar').appendChild(wrap);
    const pend = wrap.querySelector('[data-count-pending]');
    const text = pend.textContent;
    const width = (t) => { pend.textContent = t; return pend.getBoundingClientRect().width; };
    const shown = width(text);
    const paren = text.startsWith('(');
    const digit = Math.min(...'0123456789'.split('').map((d) => width(paren ? '(' + d + ')' : d)));
    wrap.remove();
    return { text, shown, digit };
}"""


def test_each_placeholder_is_no_wider_than_a_count(bar):
    """Round 4: round 3's "(…)" and "…" were about 3 px wider than a count
    under 10, so with small counts the first paint took a title-bar step the
    counts then gave back, half a second into every load (titlebar_fit.js keeps
    at least last time's steps while a count is pending, never fewer than the
    placeholders need). The placeholders are an en dash, no wider than any
    digit in the buttons' font. RED on dd81587."""
    html = DASHBOARD.read_text(encoding="utf-8")
    seen = {}
    for bid in ("btn-backlog-count", "btn-queue-count", "btn-low-stock-count"):
        m = re.search(rf'<button[^>]*id="{bid}".*?</button>', html, re.S)
        assert m, bid
        seen[bid] = bar.evaluate(PLACEHOLDER_JS, m.group(0))
    assert [v["text"] for v in seen.values()] == ["(–)", "(–)", "–"], seen
    for bid, v in seen.items():
        assert v["shown"] <= v["digit"] + 0.01, (bid, v)


def test_the_heartbeat_count_paints_the_button(bar):
    """One number, Low + Out (Group 57.2's option (a)); the words are its
    tooltip and accessible name, which holds the number shown (WCAG 2.5.3:
    "click 12" reaches it). RED before 57.2: no button, no renderer."""
    assert _render(bar, GOOD) is True
    b = _btn(bar)
    assert b["text"] == "⚠️ 12" and b["num"] == "12", b
    words = "Low stock: 12 (1 low under 250 g, 11 out). Opens the list."
    assert b["label"] == words == b["title"], b
    assert (b["read"], b["low"], b["out"]) == ("ok", "1", "11")
    # Painted: no longer a placeholder the title bar keeps last time's steps for.
    assert not bar.evaluate("(s) => document.querySelector(s).hasAttribute('data-count-pending')", NUM)
    _render(bar, {"read_ok": True, "count": 0, "low": 0, "out": 0, "threshold_g": 250.0})
    assert _btn(bar)["text"] == "⚠️ 0"


def test_a_failed_read_keeps_the_last_count_and_says_so(bar):
    """Group 52's rule: a blip is never drawn as 0; and a stale count never
    looks like a fresh one (Group 57 review): a "?" after it and a dashed
    border, and the words say why."""
    _render(bar, GOOD)
    assert _render(bar, DOWN) is False
    b = _btn(bar)
    assert b["text"] == "⚠️ 12?" and b["read"] == "failed", b
    assert b["label"] == ("Low stock: 12?, the last count (Spoolman didn't answer just now): "
                          "1 low under 250 g, 11 out. Opens the list."), b
    assert bar.evaluate("(s) => getComputedStyle(document.querySelector(s)).borderTopStyle", BTN) == "dashed"
    _render(bar, GOOD)
    b = _btn(bar)
    assert (b["text"], b["read"]) == ("⚠️ 12", "ok"), b
    assert bar.evaluate("(s) => getComputedStyle(document.querySelector(s)).borderTopStyle", BTN) != "dashed"


def _widths(page):
    return page.evaluate("""(sel) => { const b = document.querySelector(sel);
        const n = b.querySelector('[data-low-stock-count]'); const m = n.querySelector('.fcc-stale-mark');
        const r = (el) => { const q = el.getBoundingClientRect(); return [q.left, q.right]; };
        return { btn: b.getBoundingClientRect().width, num: r(n), mark: m ? r(m) : null, btnBox: r(b),
                 border: parseFloat(getComputedStyle(b).borderRightWidth) }; }""", BTN)


def test_a_stale_counts_question_mark_takes_no_room(bar):
    """The "?" sits right after the number, inside the button, and the button
    keeps its width: the title bar's steps follow its buttons' width
    (titlebar_fit.js), and a blip took a step and gave it back, moving every
    button 112 px and back (Group 57 review, round 2). RED on 6314386: the
    button grew 7 px."""
    _render(bar, GOOD)
    fresh = _widths(bar)
    assert fresh["mark"] is None, fresh
    _render(bar, DOWN)
    stale = _widths(bar)
    assert _btn(bar)["num"] == "12?", _btn(bar)
    assert abs(stale["btn"] - fresh["btn"]) < 0.01, (fresh, stale)
    assert stale["mark"] and abs(stale["mark"][0] - stale["num"][1]) < 0.5, stale       # right after "12"
    assert stale["mark"][1] <= stale["btnBox"][1] - stale["border"] + 0.01, stale       # inside the border
    _render(bar, GOOD)
    assert _widths(bar)["mark"] is None and _btn(bar)["num"] == "12"


# Where a stale count's "?" sits against its number, by their text (the same
# font, so equal tops are one baseline), and what the button's fill does.
MARK_JS = """(sel) => { const b = document.querySelector(sel);
    const num = b.querySelector('[data-low-stock-count], .fcc-count-num');
    const mark = num.querySelector('.fcc-stale-mark');
    const top = (node) => { const r = document.createRange(); r.selectNodeContents(node);
                            return r.getBoundingClientRect().top; };
    return { drop: mark ? top(mark.firstChild) - top(num.firstChild) : null,
             clip: getComputedStyle(b).backgroundClip }; }"""


def test_a_stale_counts_question_mark_sits_on_its_numbers_line(bar):
    """The "?" was its own box with the button's 1.5 line-height, so it sat a
    half-leading (1 px) under the digits it follows, in both buttons (round 3).
    And the fill stops inside the dashed border on both: Backlog is filled, and
    the ⚠️ outline button is filled while hovered or focused (Bootstrap), when
    its dashes vanished into the fill (round 3). RED on 2749590: a 1.0 px drop,
    and the ⚠️ fill under its border."""
    bar.add_style_tag(content='body { font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; }')
    bar.add_script_tag(content=(MODULES / "inv_backlog.js").read_text(encoding="utf-8"))
    _render(bar, GOOD)
    bar.evaluate("() => window._renderBacklogCount({read_ok: true, count: 53})")
    for sel in (BTN, "#btn-backlog-count"):
        fresh = bar.evaluate(MARK_JS, sel)
        assert fresh["drop"] is None and fresh["clip"] == "border-box", (sel, fresh)
    _render(bar, DOWN)
    bar.evaluate("() => window._renderBacklogCount({read_ok: false, read_error: 'down'})")
    for sel in (BTN, "#btn-backlog-count"):
        stale = bar.evaluate(MARK_JS, sel)
        assert stale["drop"] is not None and abs(stale["drop"]) < 0.5, (sel, stale)
        assert stale["clip"] == "padding-box", (sel, stale)


def test_a_failed_read_before_any_count_reads_a_question_mark(bar):
    _render(bar, DOWN)
    b = _btn(bar)
    assert b["text"] == "⚠️ ?" and b["read"] == "failed", b
    assert b["label"] == "Low stock: ?, no count yet (Spoolman didn't answer just now). Opens the list."


@pytest.mark.parametrize("sec", [
    {"read_ok": True},
    {"read_ok": True, "count": 3, "low": None, "out": 2},
    {"read_ok": True, "count": 3, "low": "x", "out": 2},
    {"read_ok": True, "count": 3, "low": -1, "out": 2},
    {"error": "boom", "read_ok": False},
])
def test_an_answer_without_its_numbers_is_no_count(bar, sec):
    """None of these is Spoolman's doing: FCC's own count failed (the section
    raised: {error, read_ok: false}), or its answer was malformed."""
    _render(bar, GOOD)
    assert _render(bar, sec) is False
    b = _btn(bar)
    assert b["text"] == "⚠️ 12?" and b["read"] == "failed", (sec, b)
    assert "(FCC couldn't count them just now)" in b["label"], (sec, b)


def test_an_answer_with_no_count_at_all_marks_it_stale(bar):
    """A heartbeat that was asked for the count and sent none (an FCC from
    before the count, say after a rollback) leaves it looking stale, not fresh."""
    _render(bar, GOOD)
    assert bar.evaluate("() => window._renderLowStockCount(undefined)") is False
    b = _btn(bar)
    assert b["text"] == "⚠️ 12?" and "(FCC didn't send a count)" in b["label"], b


def test_an_unknown_threshold_is_left_out_of_the_words(bar):
    _render(bar, {"read_ok": True, "count": 2, "low": 2, "out": 0})
    assert _btn(bar)["label"] == "Low stock: 2 (2 low, 0 out). Opens the list."


# --- it opens the list ------------------------------------------------------------------

def test_a_click_opens_the_list_on_its_own(bar):
    """The search panel isn't open, so the list has no host to close with: a
    window opened over it closes it (the "came back" path, 2026-10-20)."""
    bar.evaluate("(a) => { window.__answers = a; }", [_answer(REPORT)])
    bar.locator(BTN).click()
    bar.wait_for_selector(PANEL)
    bar.wait_for_function("(s) => document.querySelector(s).dataset.stockState === 'ready'", arg=BODY)
    assert bar.evaluate("() => window.__reports") == 1
    bar.keyboard.press("Escape")
    assert bar.locator("#fcc-low-stock-overlay").count() == 0
    # Again, and a window shows over it (Bootstrap's show.bs.modal bubbles up).
    bar.evaluate("(a) => { window.__answers = a; }", [_answer(REPORT)])
    bar.locator(BTN).click()
    bar.wait_for_function("(s) => document.querySelector(s).dataset.stockState === 'ready'", arg=BODY)
    bar.evaluate("() => document.getElementById('backlogModal').dispatchEvent(new Event('show.bs.modal', {bubbles: true}))")
    assert bar.locator("#fcc-low-stock-overlay").count() == 0


def test_space_on_the_focused_button_opens_the_list_and_escape_gives_the_focus_back(bar):
    """Keyboard (standing order): Tab reaches it, Space opens it, Escape closes
    it and the focus is back on the button, not at the top of the page (Group 57
    review). (Enter is the scan accumulator's on the real page: scripts.html
    cancels every Enter outside a field, the title bar's other buttons included.)"""
    bar.evaluate("(a) => { window.__answers = a; }", [_answer(REPORT)])
    bar.locator(BTN).focus()
    bar.keyboard.press("Space")
    bar.wait_for_selector(PANEL)
    bar.wait_for_function("(s) => document.querySelector(s).dataset.stockState === 'ready'", arg=BODY)
    bar.keyboard.press("Escape")
    assert bar.locator("#fcc-low-stock-overlay").count() == 0
    assert bar.evaluate("() => document.activeElement && document.activeElement.id") == "btn-low-stock-count"


def test_space_on_the_button_leaves_no_space_for_the_next_scan(bar):
    """The scan accumulator (scripts.html) kept the Space that pressed a
    focused button for 2 s: an Enter in the list became a scan of " ", and a
    label scanned meanwhile arrived as " CMD:WEIGH", "Malformed Command"
    (Group 57 review, round 2). The button took that space back out; since
    round 5 the REAL accumulator skips a Space while it holds nothing, so every
    button is covered. A buffer that holds a scan keeps it."""
    from test_slow_scan_slash_js import _accumulator          # that module imports this one
    bar.add_script_tag(content=_accumulator())
    bar.evaluate("(a) => { window.__answers = a; }", [_answer(REPORT)] * 3)
    bar.locator(BTN).focus()
    bar.keyboard.press("Space")
    bar.wait_for_selector(PANEL)
    assert bar.evaluate("() => state.scanBuffer") == ""
    bar.keyboard.press("Escape")
    bar.evaluate("() => { state.scanBuffer = 'ID:5'; document.getElementById('btn-low-stock-count').focus(); }")
    bar.keyboard.press("Space")
    bar.wait_for_selector(PANEL)
    assert bar.evaluate("() => state.scanBuffer") == "ID:5 "


def test_a_list_that_came_back_gives_the_focus_back_to_its_button(bar):
    """It reopens 400 ms after its filament window closes, when the focus is on
    the page: it used to take that as its opener, and Escape left the focus
    there (Group 57 review, round 2)."""
    bar.evaluate("(a) => { window.__answers = a; }", [_answer(REPORT)] * 2)
    bar.locator(BTN).focus()
    bar.keyboard.press("Space")
    bar.wait_for_function("(s) => document.querySelector(s).dataset.stockState === 'ready'", arg=BODY)
    bar.keyboard.press("Enter")                                 # the highlighted row's filament window
    assert bar.evaluate("() => window.__opened") == [164]
    bar.evaluate("""() => { const m = document.getElementById('filamentModal');
        m.dispatchEvent(new Event('show.bs.modal', {bubbles: true}));
        document.activeElement && document.activeElement.blur();
        m.dispatchEvent(new Event('hidden.bs.modal', {bubbles: true})); }""")
    bar.wait_for_function("(s) => !!document.querySelector(s)", arg=PANEL, timeout=5000)
    bar.wait_for_function("(s) => document.querySelector(s).dataset.stockState === 'ready'", arg=BODY)
    bar.keyboard.press("Escape")
    assert bar.locator("#fcc-low-stock-overlay").count() == 0
    assert bar.evaluate("() => document.activeElement && document.activeElement.id") == "btn-low-stock-count"


def test_slash_and_ctrl_k_stay_in_the_reason_dialog(bar):
    """'/' and Ctrl+K are the global search's (fab_drag.js), and its panel
    opening closes a list opened from the title bar, the reason dialog with it:
    the note typed into it was lost (Group 57 review, round 2). While the
    dialog is up they stay in it; '/' typed into the note is the note's."""
    bar.evaluate("""() => { window.__ctrlK = 0; document.addEventListener('keydown', (e) => {
        if ((e.key === 'k' || e.key === 'K') && (e.ctrlKey || e.metaKey)) window.__ctrlK += 1; }); }""")
    bar.evaluate("(a) => { window.__answers = a; }", [_answer(REPORT)])
    bar.locator(BTN).click()
    bar.wait_for_function("(s) => document.querySelector(s).dataset.stockState === 'ready'", arg=BODY)
    bar.keyboard.press("Delete")
    note = bar.locator("#fcc-low-stock-reason [data-stock-note-input]")
    note.fill("Discontinued in 2025")
    note.press("/")
    assert note.input_value() == "Discontinued in 2025/"
    passed = bar.evaluate("() => window.__slashPassed")
    up = lambda: bar.evaluate("() => !!document.getElementById('fcc-low-stock-reason')")
    bar.locator("#fcc-low-stock-reason .fcc-stock-dlg-name").click()      # the focus on the dialog itself
    bar.keyboard.press("/")
    bar.locator("#fcc-low-stock-reason [data-stock-dlg-save]").focus()
    bar.keyboard.press("/")
    assert bar.evaluate("() => window.__slashPassed") == passed and up()
    note.focus()
    bar.keyboard.press("Control+k")
    assert bar.evaluate("() => window.__ctrlK") == 0 and up()
    assert note.input_value() == "Discontinued in 2025/"
    assert bar.locator(PANEL).count() == 1


def test_a_slash_while_it_reads_stays_in_the_list(bar):
    """'/' is the list's filter key; while it reads (or shows an error) it went
    on to the global search, whose panel opening closed a list opened from the
    title bar (Group 57 review). RED before the fix: it reached the page."""
    bar.evaluate("(a) => { window.__answers = a; }", [_answer(REPORT, delay=1500)])
    bar.locator(BTN).click()
    bar.wait_for_selector(PANEL)
    assert bar.evaluate("(s) => document.querySelector(s).dataset.stockState", BODY) == "loading"
    bar.keyboard.press("/")
    assert bar.evaluate("() => window.__slashPassed") == 0
    bar.wait_for_function("(s) => document.querySelector(s).dataset.stockState === 'ready'", arg=BODY)
    bar.keyboard.press("/")                                   # ready: it focuses the filter
    assert bar.evaluate("() => document.activeElement.hasAttribute('data-stock-filter')")
    assert bar.evaluate("() => window.__slashPassed") == 0


def test_the_tabs_row_keeps_its_room_with_bootstraps_hidden_rule(bar):
    """The page here carries Bootstrap's [hidden]{display:none!important}: the
    row must not use the hidden attribute (RED on 2d166e5: its room collapsed
    on the real page while the list read, and the list jumped 42 px)."""
    bar.evaluate("(a) => { window.__answers = a; }", [_answer(REPORT, delay=1200)])
    bar.locator(BTN).click()
    bar.wait_for_selector(PANEL)
    top = lambda: bar.evaluate("(s) => Math.round(document.querySelector(s).getBoundingClientRect().top)", BODY)
    reading = top()
    # Measured while it reads, or the test compares ready with ready (round 2).
    assert bar.evaluate("(s) => document.querySelector(s).dataset.stockState", BODY) == "loading"
    bar.wait_for_function("(s) => document.querySelector(s).dataset.stockState === 'ready'", arg=BODY)
    assert top() == reading
    assert bar.evaluate("() => getComputedStyle(document.querySelector('[data-stock-tools]')).display") == "flex"


def test_the_list_it_reads_sets_the_count_and_a_change_made_there_too(bar):
    """The tabs and the title bar say the same: the list's own read sets the
    count (2 low + 2 out), and so does its re-read after an exclusion."""
    _render(bar, GOOD)
    after = copy.deepcopy(REPORT)
    moved = after["low"].pop(0)
    moved["excluded"] = MARK
    after["excluded"].append(moved)
    bar.evaluate("([a, w]) => { window.__answers = a; window.__writeAnswers = w; }",
                 [[_answer(REPORT), _answer(after)],
                  [_answer({"success": True, "filament_id": 164, "display": moved["display"], "excluded": MARK})]])
    bar.locator(BTN).click()
    bar.wait_for_function("(s) => document.querySelector(s).dataset.stockState === 'ready'", arg=BODY)
    assert _btn(bar)["text"] == "⚠️ 4"
    bar.keyboard.press("Delete")
    bar.locator("#fcc-low-stock-reason input[value='discontinued']").check()
    bar.locator("#fcc-low-stock-reason [data-stock-dlg-save]").click()
    bar.wait_for_function("() => window.__reports === 2")
    bar.wait_for_function("(s) => document.querySelector(s).textContent.trim() === '3'", arg=NUM)
    b = _btn(bar)
    assert (b["low"], b["out"]) == ("1", "2"), b


# --- the heartbeat ------------------------------------------------------------------------

def test_the_tick_asks_for_the_count_only_when_the_button_is_there(bar):
    assert "low_stock" in bar.evaluate("() => window._computePulseInclude().sections")
    # Not while the backlog window is open: label_backlog is left out then, and
    # the count would read the filament list on its own (Group 57 review).
    bar.evaluate("() => document.getElementById('backlogModal').classList.add('show')")
    assert "low_stock" not in bar.evaluate("() => window._computePulseInclude().sections")
    bar.evaluate("() => document.getElementById('backlogModal').classList.remove('show')")
    bar.evaluate("(s) => document.querySelector(s).remove()", BTN)
    assert "low_stock" not in bar.evaluate("() => window._computePulseInclude().sections")


def _beat(page, sec, at):
    return page.evaluate("([s, t]) => window._renderLowStockCount(s, {sentAt: t})", [sec, at])


def _clock(page):
    return page.evaluate("() => performance.now()")


def test_an_older_heartbeat_never_paints_over_the_lists_own_read(bar):
    """A heartbeat reads the spool list before its printer probes, so it can
    land seconds after a fresher read by the list itself: one sent before the
    list's read began is ignored, one sent after it paints (Group 57 review).
    The send times are on the page's own clock (performance.now)."""
    _render(bar, GOOD)                                        # 12
    before = _clock(bar)
    bar.evaluate("(a) => { window.__answers = a; }", [_answer(REPORT)])
    bar.locator(BTN).click()
    bar.wait_for_function("(s) => document.querySelector(s).dataset.stockState === 'ready'", arg=BODY)
    assert _btn(bar)["num"] == "4"
    assert _beat(bar, GOOD, before - 1) is False
    assert _btn(bar)["num"] == "4"
    assert _beat(bar, DOWN, before - 1) is False              # nor its failure: older than the count
    assert _btn(bar)["num"] == "4" and _btn(bar)["read"] == "ok"
    assert _beat(bar, GOOD, _clock(bar) + 1) is True
    assert _btn(bar)["num"] == "12"


def test_the_lists_own_read_never_paints_over_a_newer_heartbeat(bar):
    """The other way round (Group 57 review, round 2): the list's read is slow
    (two whole-list reads), and a heartbeat sent after it began lands first with
    a newer count; the list's older count must not paint over it."""
    _render(bar, GOOD)
    bar.evaluate("(a) => { window.__answers = a; }", [_answer(REPORT, delay=900)])
    bar.locator(BTN).click()
    bar.wait_for_selector(PANEL)
    assert _beat(bar, dict(GOOD, count=13, low=2), _clock(bar)) is True
    assert _btn(bar)["num"] == "13"
    bar.wait_for_function("(s) => document.querySelector(s).dataset.stockState === 'ready'", arg=BODY)
    assert _btn(bar)["num"] == "13" and _btn(bar)["read"] == "ok", _btn(bar)


def test_a_newer_failure_keeps_an_older_reads_count_stale(bar):
    """A heartbeat sent at t3 couldn't read; one sent at t2 lands after it with
    a count: that count is shown (it is newer than the one there), still marked
    stale, since the newest read failed."""
    _render(bar, GOOD)                                        # 12, sent now
    t = _clock(bar)
    assert _beat(bar, DOWN, t + 30) is False
    assert _btn(bar)["num"] == "12?"
    assert _beat(bar, dict(GOOD, count=14, low=3), t + 20) is True
    assert _btn(bar)["num"] == "14?" and _btn(bar)["read"] == "failed", _btn(bar)
    assert _beat(bar, GOOD, t + 40) is True
    assert (_btn(bar)["num"], _btn(bar)["read"]) == ("12", "ok")


def test_a_wall_clock_step_moves_nothing(bar):
    """The PC's clock corrected backwards (or a resume from sleep): with stamps
    from Date.now, a list read while the clock was an hour fast froze the count,
    failed reads included, until the clock caught up (Group 57 review, round 2).
    The stamps are the page's own clock, which no such step moves."""
    bar.evaluate("() => { window.__realNow = Date.now; const skew = 3600 * 1000; Date.now = () => window.__realNow() + skew; }")
    bar.evaluate("(a) => { window.__answers = a; }", [_answer(REPORT)])
    bar.locator(BTN).click()
    bar.wait_for_function("(s) => document.querySelector(s).dataset.stockState === 'ready'", arg=BODY)
    bar.keyboard.press("Escape")
    bar.evaluate("() => { Date.now = window.__realNow; }")
    bar.evaluate("(a) => { window.__pulse = a; }", [_answer({"low_stock": DOWN})])
    bar.evaluate("() => window._dashboardPulseTickOnce()")
    bar.wait_for_function("(s) => document.querySelector(s).dataset.read === 'failed'", arg=BTN, timeout=5000)
    assert _btn(bar)["num"] == "4?"


def test_a_tick_sent_before_the_lists_read_never_paints_over_it(bar):
    """Through the real tick (round 2: nothing pinned that the tick passes its
    send time): its answer is held back while the list reads and lands after
    the list's count; the count stays the list's. RED with the tick's
    {sentAt} dropped."""
    _render(bar, GOOD)
    bar.evaluate("(a) => { window.__pulse = a; }", [_answer({"low_stock": dict(GOOD, count=12)}, delay=900)])
    bar.evaluate("() => window._dashboardPulseTickOnce()")       # sent first, lands last
    bar.evaluate("(a) => { window.__answers = a; }", [_answer(REPORT)])
    bar.locator(BTN).click()
    bar.wait_for_function("(s) => document.querySelector(s).dataset.stockState === 'ready'", arg=BODY)
    assert _btn(bar)["num"] == "4"
    bar.wait_for_function("() => window.__pulseUrls.length === 1")
    bar.wait_for_timeout(1200)                                  # the held answer has landed
    assert _btn(bar)["num"] == "4", _btn(bar)


def test_a_tick_hands_its_count_to_the_button(bar):
    bar.evaluate("(a) => { window.__pulse = a; }", [_answer({"low_stock": GOOD})])
    bar.evaluate("() => window._dashboardPulseTickOnce()")
    bar.wait_for_function("(s) => document.querySelector(s).textContent.trim() === '12'", arg=NUM)
    assert "low_stock" in bar.evaluate("() => window.__pulseUrls[0]")
    # A later tick that couldn't read keeps the count, marked stale.
    bar.evaluate("(a) => { window.__pulse = a; }", [_answer({"low_stock": DOWN})])
    bar.evaluate("() => window._dashboardPulseTickOnce()")
    bar.wait_for_function("(s) => document.querySelector(s).dataset.read === 'failed'", arg=BTN)
    assert _btn(bar)["num"] == "12?"
    # And one whose answer had no count at all.
    bar.evaluate("(a) => { window.__pulse = a; }", [_answer({"low_stock": GOOD})])
    bar.evaluate("() => window._dashboardPulseTickOnce()")
    bar.wait_for_function("(s) => document.querySelector(s).dataset.read === 'ok'", arg=BTN)
    bar.evaluate("(a) => { window.__pulse = a; }", [_answer({})])
    bar.evaluate("() => window._dashboardPulseTickOnce()")
    bar.wait_for_function("(s) => document.querySelector(s).dataset.read === 'failed'", arg=BTN)
    assert "(FCC didn't send a count)" in _btn(bar)["label"]


def test_the_tick_hands_its_send_time_to_the_buffer_too(bar):
    """The buffer cards keep their answers in order by the same stamp
    (inv_cmd.js; round 2: nothing pinned that the tick passes it on). Taken
    before the request goes out, on the page's own clock."""
    bar.evaluate("""() => { window.__sr = [];
        window._renderSpoolsRefreshPayload = (d, o) => window.__sr.push(o); }""")
    before = bar.evaluate("() => performance.now()")
    bar.evaluate("(a) => { window.__pulse = a; }", [_answer({"spools_refresh": {"1": {"display": "x"}}}, delay=200)])
    bar.evaluate("() => window._dashboardPulseTickOnce()")
    bar.wait_for_function("() => window.__sr.length === 1")
    opts = bar.evaluate("() => window.__sr[0]")
    landed = bar.evaluate("() => performance.now()")
    assert isinstance(opts, dict) and before <= opts["sentAt"] <= landed - 150, (before, opts, landed)


def test_a_low_row_at_the_line_shows_its_tenth(bar):
    """Whole grams, except where rounding would put a Low row at the line it is
    under: "249.9 g", not "250 g" under "Under 250 g in stock" (round 2)."""
    report = copy.deepcopy(REPORT)
    report["low"][1]["grams"] = 249.9
    bar.evaluate("(a) => { window.__answers = a; }", [_answer(report)])
    bar.locator(BTN).click()
    bar.wait_for_function("(s) => document.querySelector(s).dataset.stockState === 'ready'", arg=BODY)
    metas = bar.evaluate("() => [...document.querySelectorAll('#fcc-low-stock-overlay .fcc-stock-meta')].map((m) => m.textContent)")
    assert metas[:2] == ["151 g · 1 spool", "249.9 g · 2 spools"], metas


def test_a_line_with_decimals_reads_as_it_is_set(bar):
    """⚙️ Behavior takes decimals, and the line was shown rounded: a line of
    250.4 g read "Under 250 g in stock" over a row of 250 g (round 3). Each
    place shows it as set: the caption, the line under the title, and the
    button's words."""
    report = copy.deepcopy(REPORT)
    report["threshold_g"] = 250.4
    report["low"][1]["grams"] = 250.3
    _render(bar, dict(GOOD, threshold_g=250.4))
    assert "1 low under 250.4 g" in _btn(bar)["label"], _btn(bar)
    bar.evaluate("(a) => { window.__answers = a; }", [_answer(report)])
    bar.locator(BTN).click()
    bar.wait_for_function("(s) => document.querySelector(s).dataset.stockState === 'ready'", arg=BODY)
    cap = bar.evaluate("() => document.querySelector('#fcc-low-stock-overlay [data-stock-cap]').textContent")
    sub = bar.evaluate("() => document.querySelector('#fcc-low-stock-overlay [data-stock-sub]').textContent")
    metas = bar.evaluate("() => [...document.querySelectorAll('#fcc-low-stock-overlay .fcc-stock-meta')].map((m) => m.textContent)")
    assert cap == "Under 250.4 g in stock, fewest grams first.", cap
    assert "low is under 250.4 g" in sub, sub
    assert metas[1] == "250 g · 2 spools", metas            # 250 g is under 250.4 g: no contradiction


def test_a_heartbeat_fcc_didnt_answer_marks_both_counts_stale(bar):
    """The tick's own request failing (the network gone, FCC restarting, an
    error page that isn't JSON) left both counts looking fresh for as long as
    it lasted (round 3). Each keeps its number with the stale look and says
    FCC didn't answer; the next good tick makes them fresh again."""
    bar.add_script_tag(content=(MODULES / "inv_backlog.js").read_text(encoding="utf-8"))
    good = {"low_stock": GOOD, "label_backlog": {"read_ok": True, "count": 53}}
    backlog = lambda: bar.evaluate("""() => { const b = document.getElementById('btn-backlog-count');
        return { text: b.textContent.replace(/\\s+/g, ' ').trim(), read: b.dataset.read || null,
                 title: b.title || '' }; }""")
    for failed in (_answer(None, network=True), _answer(None, status=502, notJson=True)):
        bar.evaluate("(a) => { window.__pulse = a; }", [_answer(good)])
        bar.evaluate("() => window._dashboardPulseTickOnce()")
        bar.wait_for_function("(s) => document.querySelector(s).dataset.read === 'ok'", arg=BTN)
        bar.wait_for_function("() => document.getElementById('btn-backlog-count').dataset.read === 'ok'")
        bar.evaluate("(a) => { window.__pulse = a; }", [failed])
        bar.evaluate("() => window._dashboardPulseTickOnce()")
        bar.wait_for_function("(s) => document.querySelector(s).dataset.read === 'failed'", arg=BTN)
        b = _btn(bar)
        assert b["num"] == "12?" and "(FCC didn't answer just now)" in b["label"], (failed, b)
        bar.wait_for_function("() => document.getElementById('btn-backlog-count').dataset.read === 'failed'")
        k = backlog()
        assert k["text"] == "🏷️ Backlog (53)?" and "(FCC didn't answer just now)" in k["title"], (failed, k)
    bar.evaluate("(a) => { window.__pulse = a; }", [_answer(good)])
    bar.evaluate("() => window._dashboardPulseTickOnce()")
    bar.wait_for_function("(s) => document.querySelector(s).dataset.read === 'ok'", arg=BTN)
    assert _btn(bar)["num"] == "12"


def test_the_lists_failed_read_marks_the_count_stale_too(bar):
    """The newest read sent decides the stale look, the list's own included:
    with Spoolman down the list said it couldn't read while the button's count
    still looked fresh (round 3)."""
    _render(bar, GOOD)
    down = _answer({"success": False, "error": "spoolman_unreachable", "msg": "Spoolman didn't answer"}, status=502)
    for answer, why in ((down, "Spoolman didn't answer just now"), (_answer(None, network=True), "FCC didn't answer just now")):
        bar.evaluate("(a) => { window.__answers = a; }", [answer])
        bar.locator(BTN).click()
        bar.wait_for_function("(s) => document.querySelector(s).dataset.stockState === 'error'", arg=BODY)
        b = _btn(bar)
        assert b["num"] == "12?" and b["read"] == "failed" and f"({why})" in b["label"], (why, b)
        bar.keyboard.press("Escape")
        _render(bar, GOOD)


def test_a_list_from_the_search_panels_button_gives_the_focus_to_the_title_bars(bar):
    """Opened from the 🔍 search panel's own Low stock button: the panel closes
    when the filament window opens, so the list that comes back can't give the
    focus to that button, and Escape left it on the page (round 3). It goes to
    the title bar's ⚠️, the list's other way in."""
    bar.evaluate("""() => { const host = document.getElementById('offcanvasSearch'); host.classList.add('show');
        const b = document.createElement('button'); b.id = 'global-search-low-stock'; b.textContent = 'Low stock';
        host.appendChild(b); b.focus(); }""")
    bar.evaluate("(a) => { window.__answers = a; }", [_answer(REPORT)] * 2)
    bar.evaluate("() => window.openLowStockPanel()")
    bar.wait_for_function("(s) => document.querySelector(s).dataset.stockState === 'ready'", arg=BODY)
    bar.keyboard.press("Enter")                                 # the highlighted row's filament window
    assert bar.evaluate("() => window.__opened") == [164]
    bar.evaluate("""() => { const host = document.getElementById('offcanvasSearch');
        host.classList.remove('show'); host.style.display = 'none';        // the panel closed for the window
        const m = document.getElementById('filamentModal');
        m.dispatchEvent(new Event('show.bs.modal', {bubbles: true}));
        document.activeElement && document.activeElement.blur();
        m.dispatchEvent(new Event('hidden.bs.modal', {bubbles: true})); }""")
    bar.wait_for_function("(s) => !!document.querySelector(s)", arg=PANEL, timeout=5000)
    bar.wait_for_function("(s) => document.querySelector(s).dataset.stockState === 'ready'", arg=BODY)
    bar.keyboard.press("Escape")
    assert bar.locator("#fcc-low-stock-overlay").count() == 0
    assert bar.evaluate("() => document.activeElement && document.activeElement.id") == "btn-low-stock-count"


# --- round 4 -------------------------------------------------------------------------

# Counts the heartbeat's own failure log line, so a test knows a held tick has
# settled (it logs "dashboard_pulse failed:" once its request has failed).
WARNS_JS = """() => { window.__pulseFails = 0; const warn = console.warn.bind(console);
    console.warn = (...a) => { if (String(a[0]).indexOf('dashboard_pulse failed') === 0) window.__pulseFails += 1;
                               return warn(...a); }; }"""

# The backlog window's own controls, as fetchBacklog reads them (dashboard.html).
BACKLOG_UI = """(filter) => { const m = document.getElementById('backlogModal');
    m.innerHTML = '<select id="backlog-filter"><option value="all">All</option><option value="spool">Spools</option>'
        + '<option value="filament">Filaments</option></select>'
        + '<select id="backlog-sort"><option value="created_newest">Newest</option></select>'
        + '<input type="checkbox" id="backlog-select-all"><button id="btn-backlog-queue-selected"></button>'
        + '<div id="backlog-list"></div>';
    document.getElementById('backlog-filter').value = filter || 'all'; }"""


def _items(n):
    """A backlog answer of `n` filaments needing a label."""
    return {"success": True, "items": [{"type": "filament", "id": 100 + i, "material": "PLA", "name": f"F{i}",
                                        "vendor": {"name": "V"}, "color_hex": "336699"} for i in range(n)]}


def _backlog_btn(page):
    return page.evaluate("""() => { const b = document.getElementById('btn-backlog-count');
        return { text: b.textContent.replace(/\\s+/g, ' ').trim(), read: b.dataset.read || null,
                 title: b.title || '' }; }""")


@pytest.fixture
def both(bar):
    """The bar with the 🏷️ Backlog count's module too, and the backlog window's
    controls."""
    bar.add_script_tag(content=(MODULES / "inv_backlog.js").read_text(encoding="utf-8"))
    bar.evaluate(BACKLOG_UI)
    bar.evaluate(WARNS_JS)
    return bar


def test_an_older_tick_fcc_didnt_answer_marks_no_newer_count_stale(both):
    """A tick sent before the list's and the backlog window's own reads fails
    after they painted: it is older than both counts and marks neither stale
    (Group 57 review, round 4: the failure branch's send time was unpinned, and
    the Backlog took whichever answer landed last). RED with the tick's send
    time dropped from its failure branch, and on dd81587 for the Backlog."""
    bar = both
    bar.evaluate("(a) => { window.__pulse = a; }", [_answer({"low_stock": GOOD, "label_backlog": {"read_ok": True, "count": 53}})])
    bar.evaluate("() => window._dashboardPulseTickOnce()")
    bar.wait_for_function("() => document.getElementById('btn-backlog-count').dataset.read === 'ok'")
    bar.evaluate("(a) => { window.__pulse = a; }", [_answer(None, network=True, delay=900)])
    bar.evaluate("() => window._dashboardPulseTickOnce()")          # sent first, fails last
    bar.evaluate("(a) => { window.__answers = a; window.__backlogAnswers = [a[1]]; }", [_answer(REPORT), _answer(_items(7))])
    bar.evaluate("() => window.fetchBacklog()")
    bar.locator(BTN).click()
    bar.wait_for_function("(s) => document.querySelector(s).dataset.stockState === 'ready'", arg=BODY)
    bar.wait_for_function("() => window.__backlogUrls.length === 1")
    bar.wait_for_function("() => document.getElementById('btn-backlog-count').textContent.indexOf('(7)') >= 0")
    bar.wait_for_function("() => window.__pulseFails === 1")
    assert (_btn(bar)["num"], _btn(bar)["read"]) == ("4", "ok"), _btn(bar)
    k = _backlog_btn(bar)
    assert (k["text"], k["read"]) == ("🏷️ Backlog (7)", "ok"), k


def test_an_older_ticks_backlog_count_never_paints_over_the_windows_read(both):
    """The heartbeat hands the Backlog its send time: a tick sent before the
    backlog window's read, landing after it, is older and its count is not
    shown (round 4: whichever answer landed last painted). The test waits for
    the held tick's own end (it signals inventory:sync-pulse once drawn), not a
    fixed time, which a slow run outlasted with nothing checked (round 5)."""
    bar = both
    bar.evaluate("() => { window.__drawn = 0; document.addEventListener('inventory:sync-pulse', () => { window.__drawn += 1; }); }")
    bar.evaluate("(a) => { window.__pulse = a; }", [_answer({"label_backlog": {"read_ok": True, "count": 53}}, delay=900)])
    bar.evaluate("() => window._dashboardPulseTickOnce()")          # sent first, lands last
    bar.evaluate("(a) => { window.__backlogAnswers = a; }", [_answer(_items(7))])
    bar.evaluate("() => window.fetchBacklog()")
    bar.wait_for_function("() => document.getElementById('btn-backlog-count').textContent.indexOf('(7)') >= 0")
    bar.wait_for_function("() => window.__drawn === 1", timeout=5000)        # the held tick has landed
    k = _backlog_btn(bar)
    assert (k["text"], k["read"]) == ("🏷️ Backlog (7)", "ok"), k


def test_a_backlog_list_that_fails_to_draw_keeps_its_count_fresh(both):
    """The window's read answered: a throw while drawing its rows is not FCC
    not answering (the request's own failure handler, as the heartbeat's)."""
    bar = both
    bar.evaluate("() => { window.updateBacklogQueueBtn = () => { throw new Error('boom'); }; }")
    bar.evaluate("(a) => { window.__backlogAnswers = a; }", [_answer(_items(2))])
    bar.evaluate("() => window.fetchBacklog()")
    bar.wait_for_function("""() => { const n = document.getElementById('backlog-read-notice');
                                     return !!n && n.textContent.indexOf('Connection error') >= 0; }""")
    k = _backlog_btn(bar)
    assert (k["text"], k["read"]) == ("🏷️ Backlog (2)", "ok"), k


def test_a_newer_failed_tick_keeps_an_older_backlog_read_stale(both):
    """The other way round, as the Low stock count does it: the window's read
    is slow, a tick sent after it fails first, then the read lands. Its count
    is shown (newer than the one there) but stays stale: the newest read sent
    failed. RED on dd81587: the slow read made the count look fresh."""
    bar = both
    bar.evaluate("(a) => { window.__pulse = a; }", [_answer({"label_backlog": {"read_ok": True, "count": 53}})])
    bar.evaluate("() => window._dashboardPulseTickOnce()")
    bar.wait_for_function("() => document.getElementById('btn-backlog-count').dataset.read === 'ok'")
    bar.evaluate("(a) => { window.__backlogAnswers = a; }", [_answer(_items(7), delay=900)])
    bar.evaluate("() => window.fetchBacklog()")                       # sent first, lands last
    bar.evaluate("(a) => { window.__pulse = a; }", [_answer(None, network=True)])
    bar.evaluate("() => window._dashboardPulseTickOnce()")
    bar.wait_for_function("() => document.getElementById('btn-backlog-count').dataset.read === 'failed'")
    assert _backlog_btn(bar)["text"] == "🏷️ Backlog (53)?"
    bar.wait_for_function("() => document.getElementById('btn-backlog-count').textContent.indexOf('(7)') >= 0")
    k = _backlog_btn(bar)
    assert (k["text"], k["read"]) == ("🏷️ Backlog (7)?", "failed") and "(FCC didn't answer just now)" in k["title"], k


@pytest.mark.parametrize("filter_", ["spool", "filament"])
def test_a_filtered_backlog_window_never_sets_the_count(both, filter_):
    """The button counts the whole backlog: the window filtered to spools or to
    filaments set it to what the filter showed (found in round 4). A good
    filtered read leaves the count as it was; a failed one marks it stale."""
    bar = both
    bar.evaluate(BACKLOG_UI, filter_)
    bar.evaluate("(a) => { window.__pulse = a; }", [_answer({"label_backlog": {"read_ok": True, "count": 53}})])
    bar.evaluate("() => window._dashboardPulseTickOnce()")
    bar.wait_for_function("() => document.getElementById('btn-backlog-count').dataset.read === 'ok'")
    bar.evaluate("(a) => { window.__backlogAnswers = a; }", [_answer(_items(7))])
    bar.evaluate("() => window.fetchBacklog()")
    bar.wait_for_function("() => document.querySelectorAll('#backlog-list .backlog-row').length === 7")
    assert (_backlog_btn(bar)["text"], _backlog_btn(bar)["read"]) == ("🏷️ Backlog (53)", "ok")
    bar.evaluate("(a) => { window.__backlogAnswers = a; }",
                 [_answer({"success": False, "msg": "Spoolman didn't answer the spool list (HTTP 503)"})])
    bar.evaluate("() => window.fetchBacklog()")
    bar.wait_for_function("() => document.getElementById('btn-backlog-count').dataset.read === 'failed'")
    k = _backlog_btn(bar)
    assert k["text"] == "🏷️ Backlog (53)?" and "(Spoolman didn't answer just now)" in k["title"], k


def test_the_backlog_windows_failed_read_marks_the_count_stale(both):
    """The newest read sent decides the stale look, the window's own included
    (it said "Connection error" while the button looked fresh); the next good
    read makes it fresh again. The window says it too: in the list on a first
    read, above the last list after that (round 5: the failure handler must
    pass the failure on to the one that writes this, and nothing pinned it;
    without it the window kept "Loading backlog..." with FCC not answering)."""
    bar = both
    bar.evaluate("(a) => { window.__pulse = a; }", [_answer({"label_backlog": {"read_ok": True, "count": 53}})])
    bar.evaluate("() => window._dashboardPulseTickOnce()")
    bar.wait_for_function("() => document.getElementById('btn-backlog-count').dataset.read === 'ok'")
    shown = 53
    said = """() => { const n = document.getElementById('backlog-read-notice');
        return (n && n.style.display !== 'none' && n.textContent) || document.getElementById('backlog-list').textContent.trim(); }"""
    for failed, why, words in ((_answer(None, network=True), "FCC didn't answer just now",
                                "Connection error fetching backlog."),
                               (_answer(None, status=502, notJson=True), "FCC didn't answer just now",
                                "⚠️ Connection error fetching backlog. Showing the last list; it tries again every few seconds."),
                               (_answer({"success": False, "msg": "x"}), "Spoolman didn't answer just now",
                                "⚠️ Error loading backlog: x Showing the last list; it tries again every few seconds.")):
        bar.evaluate("(a) => { window.__backlogAnswers = a; }", [failed])
        bar.evaluate("() => window.fetchBacklog()")
        bar.wait_for_function("() => document.getElementById('btn-backlog-count').dataset.read === 'failed'")
        k = _backlog_btn(bar)
        assert k["text"] == f"🏷️ Backlog ({shown})?" and f"({why})" in k["title"], (why, k)
        assert bar.evaluate(said) == words, why
        bar.evaluate("(a) => { window.__backlogAnswers = a; }", [_answer(_items(0))])
        bar.evaluate("() => window.fetchBacklog()")
        bar.wait_for_function("() => document.getElementById('btn-backlog-count').dataset.read === 'ok'")
        shown = 0
        assert _backlog_btn(bar)["text"] == "🏷️ Backlog (0)"


def test_an_older_failed_list_read_marks_no_newer_count_stale(bar):
    """The list's failed read is stamped with its own send time: one that fails
    after a newer heartbeat painted is older than that count and marks nothing
    (round 4: unpinned; stamped with the time it failed, it marked the
    heartbeat's fresh count stale)."""
    _render(bar, GOOD)
    bar.evaluate("(a) => { window.__answers = a; }", [_answer(None, network=True, delay=900)])
    bar.locator(BTN).click()
    bar.wait_for_selector(PANEL)
    bar.evaluate("(a) => { window.__pulse = a; }", [_answer({"low_stock": dict(GOOD, count=13, low=2)})])
    bar.evaluate("() => window._dashboardPulseTickOnce()")
    bar.wait_for_function("(s) => document.querySelector(s).textContent.trim() === '13'", arg=NUM)
    bar.wait_for_function("(s) => document.querySelector(s).dataset.stockState === 'error'", arg=BODY)
    assert (_btn(bar)["num"], _btn(bar)["read"]) == ("13", "ok"), _btn(bar)


def test_a_renderer_that_throws_is_not_fcc_not_answering(both):
    """The failure branch is the request's own (.then's second argument): a
    renderer that throws after the counts are painted (the Printer Status
    widget's, say) is only logged. As a .catch it marked both counts "FCC
    didn't answer just now" on every such tick (round 4: unpinned)."""
    bar = both
    bar.evaluate("() => { window.refreshPrinterStatusWidgetFromAggregate = () => { throw new Error('boom'); }; }")
    bar.evaluate("(a) => { window.__pulse = a; }", [_answer({"low_stock": GOOD, "label_backlog": {"read_ok": True, "count": 53},
                                                             "printer_status": {"XL": {}}})])
    bar.evaluate("() => window._dashboardPulseTickOnce()")
    bar.wait_for_function("() => window.__pulseFails === 1")
    assert (_btn(bar)["num"], _btn(bar)["read"]) == ("12", "ok"), _btn(bar)
    k = _backlog_btn(bar)
    assert (k["text"], k["read"]) == ("🏷️ Backlog (53)", "ok"), k


def test_a_tick_that_hangs_marks_both_counts_stale(both):
    """A request that never settles never fails (a link dropped without
    closing the connection), so the counts kept their fresh look for as long
    as it hung, and no other tick goes out meanwhile (round 4). After the
    heartbeat's stale time (30 s; short here) both say FCC didn't answer; an
    answer that comes after all paints them fresh again. RED on dd81587."""
    bar = both
    bar.evaluate("() => window._setPulseStaleMsForTest && window._setPulseStaleMsForTest(300)")
    bar.evaluate("(a) => { window.__pulse = a; }", [_answer({"low_stock": GOOD, "label_backlog": {"read_ok": True, "count": 53}})])
    bar.evaluate("() => window._dashboardPulseTickOnce()")
    bar.wait_for_function("(s) => document.querySelector(s).dataset.read === 'ok'", arg=BTN)
    # A tick that answered in time leaves no timer behind. A page timer started
    # now runs after the tick's own (it was set first, for less), however late
    # the page's timers run: a fixed wait proved nothing on a slow run (round 5).
    bar.evaluate("() => new Promise((r) => setTimeout(r, 400))")
    assert (_btn(bar)["read"], _backlog_btn(bar)["read"]) == ("ok", "ok"), (_btn(bar), _backlog_btn(bar))
    late = _answer({"low_stock": dict(GOOD, count=14, low=3), "label_backlog": {"read_ok": True, "count": 54}}, delay=1500)
    bar.evaluate("(a) => { window.__pulse = a; }", [late])
    bar.evaluate("() => window._dashboardPulseTickOnce()")
    bar.wait_for_function("(s) => document.querySelector(s).dataset.read === 'failed'", arg=BTN, timeout=1200)
    b = _btn(bar)
    assert b["num"] == "12?" and "(FCC didn't answer just now)" in b["label"], b
    k = _backlog_btn(bar)
    assert (k["text"], k["read"]) == ("🏷️ Backlog (53)?", "failed") and "(FCC didn't answer just now)" in k["title"], k
    bar.wait_for_function("(s) => document.querySelector(s).dataset.read === 'ok'", arg=BTN, timeout=5000)
    assert _btn(bar)["num"] == "14"
    assert (_backlog_btn(bar)["text"], _backlog_btn(bar)["read"]) == ("🏷️ Backlog (54)", "ok")
    bar.evaluate("() => window._setPulseStaleMsForTest && window._setPulseStaleMsForTest()")


def test_a_hung_tick_waits_thirty_seconds_before_the_counts_say_so(both):
    """The 30 s itself, on the page's own clock (Playwright's, paused, so the
    page's time and timers move only when the test says): fresh 29 s into a
    tick that hangs, stale after 30 (round 5: every test set the time short, so
    a 3 s value passed them all). 30 s is past the slowest real heartbeat, an
    offline printer's probes. Paused since round 6: installed alone the clock
    still ran in real time, so a busy run could pass the 30 s before the test
    looked at 29."""
    bar = both
    bar.clock.install()
    bar.clock.pause_at(bar.evaluate("() => Date.now()") + 1000)
    bar.evaluate("(a) => { window.__pulse = a; }",
                 [_answer({"low_stock": GOOD, "label_backlog": {"read_ok": True, "count": 53}}), _answer(None, hang=True)])
    bar.evaluate("() => window._dashboardPulseTickOnce()")
    assert (_btn(bar)["read"], _backlog_btn(bar)["read"]) == ("ok", "ok")
    bar.evaluate("() => window._dashboardPulseTickOnce()")          # hangs
    bar.clock.run_for(29_000)
    assert (_btn(bar)["read"], _backlog_btn(bar)["read"]) == ("ok", "ok")
    bar.clock.run_for(1_500)
    assert (_btn(bar)["num"], _btn(bar)["read"]) == ("12?", "failed"), _btn(bar)
    assert (_backlog_btn(bar)["text"], _backlog_btn(bar)["read"]) == ("🏷️ Backlog (53)?", "failed")


@pytest.mark.parametrize("answer, list_says, count_says", [
    (_answer(None, network=True), "FCC didn't answer", "FCC didn't answer just now"),
    (_answer(None, status=502, notJson=True), "FCC didn't answer", "FCC didn't answer just now"),
    (_answer({"success": False, "error": "spoolman_unreachable", "msg": "x"}, status=502),
     "Spoolman didn't answer", "Spoolman didn't answer just now"),
    (_answer({"success": False, "error": "report_failed", "msg": "boom"}, status=500),
     "FCC couldn't build the list", "FCC couldn't count them just now"),
])
def test_the_list_and_its_count_name_one_cause(bar, answer, list_says, count_says):
    """One failed read, one cause on screen (round 4: with FCC not answering,
    the list said Spoolman didn't answer while the button said FCC didn't)."""
    _render(bar, GOOD)
    bar.evaluate("(a) => { window.__answers = a; }", [answer])
    bar.locator(BTN).click()
    bar.wait_for_function("(s) => document.querySelector(s).dataset.stockState === 'error'", arg=BODY)
    title = bar.evaluate("(s) => document.querySelector(s + ' .fcc-stock-error-title').textContent", BODY)
    assert title == f"⚠️ {list_says}", title
    assert f"({count_says})" in _btn(bar)["label"], _btn(bar)


def test_a_list_from_the_open_search_panel_gives_the_focus_back_to_its_button(bar):
    """The opener first: with the search panel still open, Escape gives the
    focus to the panel's own Low stock button, and only a button that can't
    take it falls back to the title bar's ⚠️ (round 4: unpinned; the fallback
    first put the focus behind the open panel)."""
    bar.evaluate("""() => { const host = document.getElementById('offcanvasSearch'); host.classList.add('show');
        const b = document.createElement('button'); b.id = 'global-search-low-stock'; b.textContent = 'Low stock';
        host.appendChild(b); b.focus(); }""")
    bar.evaluate("(a) => { window.__answers = a; }", [_answer(REPORT)])
    bar.evaluate("() => window.openLowStockPanel()")
    bar.wait_for_function("(s) => document.querySelector(s).dataset.stockState === 'ready'", arg=BODY)
    bar.keyboard.press("Escape")
    assert bar.locator("#fcc-low-stock-overlay").count() == 0
    assert bar.evaluate("() => document.activeElement && document.activeElement.id") == "global-search-low-stock"


QUEUE = [{"id": 7, "type": "spool", "display": "#7"}, {"id": 8, "type": "spool", "display": "#8"}]
QUEUE_PAGE_JS = r"""(saved) => {
    // A localStorage holding this browser's queue (set_content leaves the page
    // on about:blank, where the real one is refused), and the server's queue.
    const store = { fcc_label_queue: saved };
    Object.defineProperty(window, 'localStorage', { configurable: true, get: () => ({
        getItem: (k) => (k in store ? store[k] : null), setItem: (k, v) => { store[k] = String(v); } }) });
    window.__posts = 0;
    window.__gets = 0;              // the poll's reads, counted once their answer is read
    window.fetch = (url, opts) => {
        if (String(url).indexOf('/api/state/queue') === 0) {
            if (opts && opts.method === 'POST') { window.__posts += 1; return Promise.resolve({ json: () => Promise.resolve({}) }); }
            return Promise.resolve({ json: () => { window.__gets += 1; return Promise.resolve(JSON.parse(saved)); } });
        }
        return Promise.reject(new TypeError('no network in this test'));
    };
}"""


def test_the_queue_count_shows_this_browsers_queue_from_the_load(isolated_page):
    """The 🛒 Queue count was painted only when the server's queue differed
    from this browser's (inv_queue.js's loadQueue), so a browser whose queue
    matched the server's read the page's "(0)" with labels queued (round 3).
    It shows this browser's queue from the load and keeps it when the server
    agrees, writing nothing. RED on 2749590: "(0)" for good."""
    page = isolated_page
    html = DASHBOARD.read_text(encoding="utf-8")
    m = re.search(r'<button[^>]*id="btn-queue-count".*?</button>', html, re.S)
    assert m and "data-count-pending>(–)" in m.group(0), "the Queue's placeholder should read (–), never (0)"
    page.set_content(f"<!doctype html><html><body>{m.group(0)}</body></html>")
    page.evaluate(QUEUE_PAGE_JS, json.dumps(QUEUE))
    page.add_script_tag(content=(MODULES / "inv_queue.js").read_text(encoding="utf-8"))
    text = lambda: page.evaluate("() => document.getElementById('btn-queue-count').textContent.trim()")
    assert text() == "🛒 Queue (2)"
    # One 2 s poll, read (round 4: a fixed 2.4 s wait passed without one on a slow
    # run): the server's queue is the same.
    page.wait_for_function("() => window.__gets >= 1", timeout=10000)
    assert text() == "🛒 Queue (2)" and page.evaluate("() => window.__posts") == 0
