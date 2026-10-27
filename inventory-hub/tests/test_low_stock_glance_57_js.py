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
const __take = (q) => (q.length > 1 ? q.shift() : q[0]);
const __respond = (a) => {
    if (!a || a.network) return Promise.reject(new TypeError('Failed to fetch'));
    // a.notJson: an error page that isn't JSON (a proxy's 502, say).
    const go = () => Promise.resolve({ ok: a.status >= 200 && a.status < 300, status: a.status,
                                      json: () => (a.notJson ? Promise.reject(new SyntaxError("Unexpected token '<'"))
                                          : Promise.resolve(JSON.parse(JSON.stringify(a.body)))) });
    return a.delay ? new Promise((r) => setTimeout(r, a.delay)).then(go) : go();
};
window.fetch = function (url, opts) {
    url = String(url);
    if (url.indexOf('/api/dashboard_pulse') === 0) { window.__pulseUrls.push(url); return __respond(__take(window.__pulse)); }
    if (url.indexOf('/api/stock_report') === 0) { window.__reports += 1; return __respond(__take(window.__answers)); }
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

def test_before_the_first_heartbeat_it_reads_an_ellipsis(bar):
    b = _btn(bar)
    assert b["text"] == "⚠️ …" and b["read"] is None, b
    assert b["label"] == "Low stock: opens the list." == b["title"]
    assert bar.evaluate("(s) => document.querySelector(s).hasAttribute('data-count-pending')", NUM)


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
    """The scan accumulator (scripts.html) keeps the Space that pressed a
    focused button for 2 s: an Enter in the list became a scan of " ", and a
    label scanned meanwhile arrived as " CMD:WEIGH", "Malformed Command"
    (Group 57 review, round 2). The button takes that space back out; a buffer
    that holds a scan keeps it, and a mouse click leaves the buffer alone."""
    # The accumulator's part that matters here: a key typed outside a field.
    bar.evaluate("""() => document.addEventListener('keydown', (e) => {
        if (e.key.length === 1 && !['INPUT', 'TEXTAREA'].includes(e.target.tagName)) state.scanBuffer += e.key; })""")
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
    bar.keyboard.press("Escape")
    bar.evaluate("() => { state.scanBuffer = ' '; }")
    bar.locator(BTN).click()
    bar.wait_for_selector(PANEL)
    assert bar.evaluate("() => state.scanBuffer") == " "


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



QUEUE = [{"id": 7, "type": "spool", "display": "#7"}, {"id": 8, "type": "spool", "display": "#8"}]
QUEUE_PAGE_JS = r"""(saved) => {
    // A localStorage holding this browser's queue (set_content leaves the page
    // on about:blank, where the real one is refused), and the server's queue.
    const store = { fcc_label_queue: saved };
    Object.defineProperty(window, 'localStorage', { configurable: true, get: () => ({
        getItem: (k) => (k in store ? store[k] : null), setItem: (k, v) => { store[k] = String(v); } }) });
    window.__posts = 0;
    window.fetch = (url, opts) => {
        if (String(url).indexOf('/api/state/queue') === 0) {
            if (opts && opts.method === 'POST') { window.__posts += 1; return Promise.resolve({ json: () => Promise.resolve({}) }); }
            return Promise.resolve({ json: () => Promise.resolve(JSON.parse(saved)) });
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
    assert m and "data-count-pending>(…)" in m.group(0), "the Queue's placeholder should read (…), never (0)"
    page.set_content(f"<!doctype html><html><body>{m.group(0)}</body></html>")
    page.evaluate(QUEUE_PAGE_JS, json.dumps(QUEUE))
    page.add_script_tag(content=(MODULES / "inv_queue.js").read_text(encoding="utf-8"))
    text = lambda: page.evaluate("() => document.getElementById('btn-queue-count').textContent.trim()")
    assert text() == "🛒 Queue (2)"
    page.wait_for_timeout(2400)                      # one 2 s poll: the server's queue is the same
    assert text() == "🛒 Queue (2)" and page.evaluate("() => window.__posts") == 0
