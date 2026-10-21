"""Group 49.2a: the ⚠️ Low-stock panel (static/js/modules/inv_stock.js), hermetic,
with Derek's 2026-10-20 sample: three lists (Low / Out / Excluded) as tabs with
counts, a filter, one line per filament, and excluding a filament from Low and Out
with a reason, from the list ("Excluded", not "Not buying again", since
2026-10-21).

Runs the REAL overlay_mount.js, inv_core.js and inv_stock.js with the real
static/css/global.css in `isolated_page` (a chromium with no route to any
network), so it RUNS under --offline. `fetch` is stubbed in the page:
/api/stock_report answers from window.__answers, and the exclusion writes (POST / DELETE /api/filament/<id>/stock_exclusion) from window.__writeAnswers,
each recorded in window.__sent. openFilamentDetails, showToast and processScan
are recorders.

Pinned: the tabs (counts, the list it opens on, ← / → and clicks), the rows (one
line, names, grams, spools, tags, swatch, the no-spool and excluded wording), the Buy link only when a web link resolves, the filter (/, words in any
order across names, tags, reasons and notes, the counts it shows, ↓ into the
list, Enter from it, a scan typed into it going to the scan path), the reason
dialog (🔕 and Del, a reason needed and a note for Other, Save and Include again,
its keys, a scan never answering it, a failure kept on screen, closing with its
search panel), the empty and error states, keyboard navigation, escaping of
every piece of text, the contrast guard on every state, one request per opening
(and one after a change), a stale answer never painting, and the list coming
back to the same list, filter and row after the window opened from it closes.

The same panel inside the real dashboard is covered by
test_low_stock_panel_e2e.py and test_contrast_guard.py (they need the container).
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

HUB = Path(__file__).resolve().parent.parent
MODULES = HUB / "static" / "js" / "modules"
GLOBAL_CSS = HUB / "static" / "css" / "global.css"
PANEL = "#fcc-low-stock-overlay .fcc-stock-panel"
BODY = "#fcc-low-stock-overlay [data-stock-body]"
DIALOG = "#fcc-low-stock-reason [data-stock-dialog]"
FILTER = "#fcc-low-stock-overlay [data-stock-filter]"

# Set up before the modules load: the registerShortcut queue (scripts.html's
# shim), a fetch that answers /api/stock_report from window.__answers and the
# stock_exclusion writes from window.__writeAnswers (one per request; the last repeats;
# {network:true} rejects like a dropped connection, {delay:ms} holds the
# answer), and recorders for openFilamentDetails (inv_details.js's global) and
# processScan (inv_cmd.js's).
PRELUDE = r"""
window.__pendingShortcuts = [];
window.registerShortcut = function (s) { window.__pendingShortcuts.push(s); };
window.__fetches = [];
window.__answers = [];
window.__sent = [];
window.__writeAnswers = [];
window.__opened = [];
window.__toasts = [];
window.__scans = [];
window.__errors = [];
window.addEventListener('error', (e) => window.__errors.push(String(e.message)));
window.fetch = function (url, opts) {
    url = String(url);
    let queue;
    if (url.indexOf('/stock_exclusion') >= 0) {
        window.__sent.push({ url, method: (opts && opts.method) || 'GET',
                             body: opts && opts.body ? JSON.parse(opts.body) : null });
        queue = window.__writeAnswers;
    } else {
        window.__fetches.push(url);
        queue = window.__answers;
    }
    const a = queue.length > 1 ? queue.shift() : queue[0];
    const go = () => {
        if (!a || a.network) return Promise.reject(new TypeError('Failed to fetch'));
        return Promise.resolve({
            ok: a.status >= 200 && a.status < 300, status: a.status,
            json: () => (a.badJson ? Promise.reject(new SyntaxError('Unexpected token <'))
                                   : Promise.resolve(JSON.parse(JSON.stringify(a.body)))),
        });
    };
    return a && a.delay ? new Promise((r) => setTimeout(r, a.delay)).then(go) : go();
};
window.processScan = function (txt, source) { window.__scans.push([txt, source]); };
// Open / close a Bootstrap window the way Bootstrap does: show.bs.modal, then the
// class; class off, then hidden.bs.modal.
window.__showModal = function (id) {
    const m = document.getElementById(id);
    m.dispatchEvent(new Event('show.bs.modal', { bubbles: true }));
    m.classList.add('show');
};
window.__closeModal = function (id) {
    const m = document.getElementById(id);
    m.classList.remove('show');
    m.dispatchEvent(new Event('hidden.bs.modal', { bubbles: true }));
};
// The filament window opens (and closes the search panel, as inv_core.js does),
// unless a test makes its read fail (window.__failOpen: no window, as
// openFilamentDetails' "Filament Data Missing!" path).
function openFilamentDetails(fid) {
    window.__opened.push(fid);
    if (window.__failOpen) return;
    const o = document.getElementById('offcanvasSearch');
    if (o) o.classList.remove('show');
    window.__showModal('filamentModal');
}
// A scanner: every character as its own keydown within a millisecond, typed into
// the focused field, then Enter (the timing installFieldScanCapture reads).
window.__scanInto = function (el, txt) {
    el.focus();
    for (const ch of txt) {
        el.dispatchEvent(new KeyboardEvent('keydown', { key: ch, bubbles: true, cancelable: true }));
        if ('value' in el && el.type !== 'radio') { el.value += ch; el.dispatchEvent(new Event('input', { bubbles: true })); }
    }
    el.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true }));
};
"""

PAGE = """<!doctype html><html><head><meta charset="utf-8"><style>{css}</style></head><body>
<div id="offcanvasSearch" class="offcanvas offcanvas-end text-bg-dark fcc-offcanvas-search show">
  <div class="offcanvas-header">
    <button type="button" id="global-search-low-stock">⚠️ Low stock</button>
    <select id="global-search-material"><option value="">Any Mat</option></select>
  </div>
</div>
<div id="filamentModal" class="modal"></div>
<div id="spoolModal" class="modal"></div>
<div id="wizardModal" class="modal"></div>
</body></html>"""


def _row(fid, display, grams, spools, total, color="222222", direction="longitudinal",
         attrs=(), buy=None, marked=None, **more):
    brand, material, colour = display.split(" - ")
    r = {"filament_id": fid, "brand": brand, "material": material, "color_name": colour,
         "display": display, "color": color, "color_direction": direction,
         "grams": grams, "spools": spools, "spools_total": total,
         "attributes": list(attrs), "excluded": marked, "buy_url": buy}
    r.update(more)
    return r


MARK = {"reason": "Discontinued", "code": "discontinued", "note": "Prusa stopped making it", "at": "2026-10-20"}

REPORT = {
    "success": True, "threshold_g": 250.0, "filaments": 5, "spools": 9,
    "low": [
        _row(164, "Prusament - PLA - Galaxy Black", 151.0, 1, 3,
             buy="https://www.prusa3d.com/product/prusament-pla-galaxy-black/"),
        _row(88, "Overture - PETG - Red Blue", 220.4, 2, 2, color="BA0C2F,0047BB",
             direction="coaxial", attrs=("Silk", "Matte")),
    ],
    "out": [
        _row(20, "Generic - PLA - Lipstick Red", 0, 0, 2, color="ff0000", attrs=("For Infill",),
             buy="https://shop.example/s?q=Generic+PLA+Lipstick%20Red"),
        _row(29, "Polymaker - PC - Clear", 0, 0, 0, color="eeeeee", no_spools=True),
    ],
    "excluded": [
        _row(41, "Sunlu - PLA - Glow Green", 120.0, 2, 3, color="55ff55", marked=MARK, stock_unknown=True),
    ],
}
EMPTY = {"success": True, "threshold_g": 250.0, "low": [], "out": [], "filaments": 40, "spools": 90}
DOWN = {"success": False, "error": "spoolman_unreachable",
        "msg": "Spoolman didn't answer, so FCC can't tell what is low right now. Try again in a moment."}


def _after_marking(report, fid, mark=None):
    """The report after `fid` was excluded (or, mark=False, included again into
    Low)."""
    rep = copy.deepcopy(report)
    for key in ("low", "out", "excluded"):
        for r in list(rep[key]):
            if r["filament_id"] == fid:
                rep[key].remove(r)
                if mark is False:
                    r["excluded"] = None
                    rep["low"].append(r)
                else:
                    r["excluded"] = mark or MARK
                    rep["excluded"].append(r)
    return rep


def _answer(body, status=200, **kw):
    a = {"status": status, "body": body}
    a.update(kw)
    return a


def _ok(display, mark=MARK):
    return _answer({"success": True, "filament_id": 1, "display": display, "excluded": mark,
                    "msg": "ok"})


@pytest.fixture
def panel(isolated_page):
    """The page with the real modules loaded; returns (page, open(answers...))."""
    page = isolated_page
    page.set_content(PAGE.format(css=GLOBAL_CSS.read_text(encoding="utf-8")))
    page.add_script_tag(content=PRELUDE)
    for name in ("overlay_mount.js", "inv_core.js", "inv_stock.js"):
        page.add_script_tag(content=(MODULES / name).read_text(encoding="utf-8"))
    # inv_core.js draws its own toasts: record them instead.
    # (A statement: Playwright calls an expression that evaluates to a function.)
    page.evaluate("() => { window.showToast = (msg, type, ms) => window.__toasts.push({msg, type, ms}); }")

    def _open(*answers, click=True, writes=None):
        page.evaluate("(a) => { window.__answers = a; }", list(answers))
        if writes is not None:
            page.evaluate("(a) => { window.__writeAnswers = a; }", list(writes))
        if click:
            page.locator("#global-search-low-stock").click()
        else:
            page.evaluate("window.openLowStockPanel()")
        page.wait_for_selector(PANEL)

    return page, _open


def _state(page):
    return page.locator(BODY).get_attribute("data-stock-state")


def _wait_state(page, name):
    page.wait_for_function(
        "(n) => { const b = document.querySelector(" + json.dumps(BODY) + "); return b && b.dataset.stockState === n; }",
        arg=name, timeout=5000)


def _row_texts(page):
    return page.evaluate(f"""() => Array.from(document.querySelectorAll({json.dumps(BODY)} + ' .fcc-stock-row'))
        .map((r) => {{
            const nameEl = r.querySelector('.fcc-stock-name');
            const own = Array.from(nameEl.childNodes).filter((n) => n.nodeType === Node.TEXT_NODE)
                .map((n) => n.textContent).join('').replace(/\\s+/g, ' ').trim();
            const why = r.querySelector('[data-stock-why]');
            const note = r.querySelector('[data-stock-note]');
            return {{fid: r.dataset.fid, kind: r.dataset.kind, name: own,
                     tags: Array.from(nameEl.querySelectorAll('.fcc-stock-tag')).map((t) => t.textContent),
                     meta: r.querySelector('.fcc-stock-meta').textContent.trim(),
                     why: why ? why.textContent.trim() : null,
                     note: note ? note.textContent.trim() : null,
                     buy: !!r.querySelector('a.fcc-stock-buy'),
                     // One line: every part but the note starts within a few px of the others.
                     tops: Array.from(r.children).filter((c) => !c.hasAttribute('data-stock-note'))
                         .map((c) => c.getBoundingClientRect().top),
                     mark: !!r.querySelector('[data-stock-exclude]'),
                     edit: !!r.querySelector('[data-stock-edit]'),
                     height: r.getBoundingClientRect().height,
                     active: r.classList.contains('kb-active')}};
        }})""")


def _tabs(page):
    return page.evaluate(f"""() => Array.from(document.querySelectorAll({json.dumps(PANEL)} + ' [data-stock-tab]'))
        .map((t) => [t.dataset.stockTab, t.querySelector('[data-stock-count]').textContent,
                     t.getAttribute('aria-selected') === 'true'])""")


def _active_fid(page):
    return page.evaluate(f"""() => {{ const r = document.querySelector({json.dumps(BODY)} + ' .fcc-stock-row.kb-active');
                                      return r ? r.dataset.fid : null; }}""")


def _cap(page):
    return page.locator(BODY + " [data-stock-cap]").text_content().strip()


def _tab(page, key):
    page.locator(f"{PANEL} [data-stock-tab='{key}']").click()


def _dialog_open(page):
    return page.locator(DIALOG).count() == 1


def _dialog_msg(page):
    return page.locator(DIALOG + " [data-stock-dlg-msg]").text_content().strip()


def _focused(page):
    return page.evaluate("""() => { const a = document.activeElement;
        return a ? {tag: a.tagName, value: a.value, fid: a.dataset ? a.dataset.fid : null,
                    filter: a.hasAttribute('data-stock-filter'), note: a.hasAttribute('data-stock-note-input'),
                    text: (a.textContent || '').trim()} : null; }""")


# --- what it shows -------------------------------------------------------------------

def test_it_opens_on_low_with_tabs_counts_and_one_line_rows(panel):
    """RED on 68a9b9d: no tabs (Low and Out were two sections of one long list)."""
    page, open_ = panel
    open_(_answer(REPORT))
    _wait_state(page, "ready")
    assert _tabs(page) == [["low", "2", True], ["out", "2", False], ["excluded", "1", False]]
    rows = _row_texts(page)
    assert [(r["fid"], r["kind"]) for r in rows] == [("164", "low"), ("88", "low")]
    assert rows[0]["name"] == "Prusament - PLA - Galaxy Black" and rows[0]["tags"] == []
    assert rows[0]["meta"] == "151 g · 1 spool"
    assert rows[1]["name"] == "Overture - PETG - Red Blue" and rows[1]["tags"] == ["Silk", "Matte"]
    assert rows[1]["meta"] == "220 g · 2 spools"
    assert all(r["mark"] and not r["edit"] for r in rows)
    assert all(r["height"] <= 36 and max(r["tops"]) - min(r["tops"]) < 6 for r in rows), rows   # one line each
    assert [r["active"] for r in rows] == [True, False]                      # ready for Enter
    assert _cap(page) == "Under 250 g in stock, fewest grams first."
    assert "low is under 250 g" in page.locator(PANEL + " [data-stock-sub]").text_content()
    assert page.locator(PANEL + " [data-stock-foot]").text_content() == (
        "↑ ↓ move · ← → lists · / filter · Enter opens the filament · Del exclude… · Esc closes")
    # Each row has its filament's swatch (getFilamentStyle: a gradient for multi-colour).
    bgs = page.evaluate(f"""() => Array.from(document.querySelectorAll({json.dumps(BODY)} + ' .fcc-stock-swatch'))
        .map((s) => getComputedStyle(s).backgroundImage + '|' + getComputedStyle(s).backgroundColor)""")
    assert bgs[0].endswith("|rgb(34, 34, 34)")
    assert "gradient" in bgs[1]


def test_a_long_name_stays_on_one_line(panel):
    page, open_ = panel
    report = copy.deepcopy(REPORT)
    report["low"][0]["display"] = "Prusament - PLA - " + "Galaxy Black With Extra Words " * 6
    report["low"][0]["attributes"] = ["Silk", "Glow", "For Infill"]
    open_(_answer(report))
    _wait_state(page, "ready")
    rows = _row_texts(page)
    assert rows[0]["height"] <= 36 and max(rows[0]["tops"]) - min(rows[0]["tops"]) < 6, rows[0]
    clipped = page.evaluate(f"""() => {{ const n = document.querySelector({json.dumps(BODY)} + ' .fcc-stock-name');
        return [getComputedStyle(n).textOverflow, n.scrollWidth > n.clientWidth]; }}""")
    assert clipped == ["ellipsis", True]
    # The whole name is in the row's tooltip.
    title = page.locator(BODY + " .fcc-stock-row").first.get_attribute("title")
    assert title == report["low"][0]["display"]


def test_the_out_list_says_which_never_had_a_spool(panel):
    page, open_ = panel
    open_(_answer(REPORT))
    _wait_state(page, "ready")
    _tab(page, "out")
    assert _tabs(page) == [["low", "2", False], ["out", "2", True], ["excluded", "1", False]]
    rows = _row_texts(page)
    assert [(r["fid"], r["kind"], r["meta"]) for r in rows] == [
        ("20", "out", "0 g · 2 spools archived or empty"),
        ("29", "out", "0 g · no spool on record")]
    assert rows[0]["tags"] == ["For Infill"]
    assert _cap(page) == "None left in stock. The ones with no spool on record come last."
    assert _active_fid(page) == "20"


def test_the_excluded_list_shows_why(panel):
    page, open_ = panel
    open_(_answer(REPORT))
    _wait_state(page, "ready")
    _tab(page, "excluded")
    rows = _row_texts(page)
    assert len(rows) == 1
    r = rows[0]
    assert (r["fid"], r["kind"], r["why"]) == ("41", "excluded", "Discontinued")
    assert r["meta"] == "≥ 120 g · 2 spools"                 # a spool of unknown weight: a floor
    assert r["note"] == "since 2026-10-20 · “Prusa stopped making it”"
    assert not r["buy"] and not r["mark"] and r["edit"]
    assert _cap(page) == "Left off Low and Out: ones you can't get or won't restock. ✏️ changes why, or includes one again."
    assert page.locator(PANEL + " [data-stock-foot]").text_content().endswith(
        "Del change why or include again · Esc closes")


def test_a_buy_link_only_when_a_web_link_resolves(panel):
    page, open_ = panel
    report = copy.deepcopy(REPORT)
    report["low"][1]["buy_url"] = "javascript:alert(1)"     # never put in an href
    open_(_answer(report))
    _wait_state(page, "ready")
    links = page.evaluate(f"""() => Array.from(document.querySelectorAll({json.dumps(BODY)} + ' .fcc-stock-row'))
        .map((r) => {{ const a = r.querySelector('a.fcc-stock-buy');
                       return a ? [a.getAttribute('href'), a.target, a.rel, a.textContent.trim()] : null; }})""")
    assert links == [["https://www.prusa3d.com/product/prusament-pla-galaxy-black/", "_blank",
                      "noopener noreferrer", "🛒 Buy"], None]
    _tab(page, "out")
    assert page.locator(BODY + " a.fcc-stock-buy").first.get_attribute("href") == \
        "https://shop.example/s?q=Generic+PLA+Lipstick%20Red"


def test_it_opens_on_the_first_list_with_something_in_it(panel):
    page, open_ = panel
    report = copy.deepcopy(REPORT)
    report["low"] = []
    open_(_answer(report))
    _wait_state(page, "ready")
    assert [t[2] for t in _tabs(page)] == [False, True, False]
    report["out"] = []
    open_(_answer(report), click=False)
    _wait_state(page, "ready")
    page.wait_for_function(f"() => document.querySelector({json.dumps(BODY)} + ' .fcc-stock-row[data-kind=excluded]')")
    assert [t[2] for t in _tabs(page)] == [False, False, True]


def test_nothing_at_all_is_its_own_state(panel):
    """An answer without `excluded` (a server from before the sample) reads as none."""
    page, open_ = panel
    open_(_answer(EMPTY))
    _wait_state(page, "empty")
    text = page.locator(BODY).inner_text()
    assert "Nothing is low." in text and "under 250 g" in text and "none has run out" in text
    assert page.locator(PANEL + " .fcc-stock-row").count() == 0
    assert page.locator(PANEL + " [data-stock-tools]").is_hidden()


def test_an_empty_list_says_so(panel):
    page, open_ = panel
    report = copy.deepcopy(REPORT)
    report["out"], report["excluded"] = [], []
    open_(_answer(report))
    _wait_state(page, "ready")
    _tab(page, "out")
    assert page.locator(BODY + " .fcc-stock-none").text_content().strip() == "Nothing is out."
    _tab(page, "excluded")
    assert page.locator(BODY + " .fcc-stock-none").text_content().strip() == (
        "None yet. 🔕 on a Low or Out row (or Del) leaves a filament you can't get or won't restock off "
        "those lists, with your reason.")


@pytest.mark.parametrize("answer", [
    _answer(DOWN, status=502),
    _answer(None, network=True),
    _answer(None, status=502, badJson=True),
    _answer({"success": True}, status=200),          # no lists: not a report
])
def test_a_failed_read_is_an_error_never_an_empty_list(panel, answer):
    page, open_ = panel
    open_(answer)
    _wait_state(page, "error")
    text = page.locator(BODY).inner_text()
    assert "Spoolman didn't answer" in text
    assert "Nothing is low" not in text
    assert page.locator(PANEL + " .fcc-stock-row").count() == 0
    assert page.locator(PANEL + " [role=alert]").count() == 1
    assert page.locator(PANEL + " [data-stock-tools]").is_hidden()


def test_try_again_asks_again_and_shows_the_list(panel):
    page, open_ = panel
    open_(_answer(DOWN, status=502), _answer(REPORT))
    _wait_state(page, "error")
    page.locator(PANEL + " [data-stock-retry]").click()
    _wait_state(page, "ready")
    assert page.evaluate("window.__fetches.length") == 2
    assert len(_row_texts(page)) == 2


def test_its_own_failure_is_named_as_such(panel):
    page, open_ = panel
    open_(_answer({"success": False, "error": "report_failed", "msg": "FCC couldn't build the Low-stock list: boom"},
                  status=500))
    _wait_state(page, "error")
    text = page.locator(BODY).inner_text()
    assert "FCC couldn't build the list" in text and "boom" in text


# --- keyboard -------------------------------------------------------------------------

def test_arrows_move_and_wrap_enter_opens_the_filament(panel):
    page, open_ = panel
    open_(_answer(REPORT))
    _wait_state(page, "ready")
    assert _active_fid(page) == "164"
    page.keyboard.press("ArrowDown")
    assert _active_fid(page) == "88"
    page.keyboard.press("ArrowDown")                    # wraps to the top
    assert _active_fid(page) == "164"
    page.keyboard.press("ArrowUp")                      # and back to the bottom
    assert _active_fid(page) == "88"
    page.keyboard.press("Enter")
    assert page.evaluate("window.__opened") == [88]
    # Opening the filament window closes the panel (a modal would sit under it).
    assert page.locator("#fcc-low-stock-overlay").count() == 0
    assert page.evaluate("window.__errors") == []


def test_left_and_right_switch_lists_and_wrap(panel):
    page, open_ = panel
    open_(_answer(REPORT))
    _wait_state(page, "ready")
    page.keyboard.press("ArrowRight")
    assert [t[2] for t in _tabs(page)] == [False, True, False] and _active_fid(page) == "20"
    page.keyboard.press("ArrowRight")
    assert [t[2] for t in _tabs(page)] == [False, False, True] and _active_fid(page) == "41"
    page.keyboard.press("ArrowRight")                   # wraps to Low
    assert [t[2] for t in _tabs(page)] == [True, False, False] and _active_fid(page) == "164"
    page.keyboard.press("ArrowLeft")
    assert [t[2] for t in _tabs(page)] == [False, False, True]


def test_slash_filters_every_list_and_the_counts_say_what_matches(panel):
    page, open_ = panel
    open_(_answer(REPORT))
    _wait_state(page, "ready")
    page.keyboard.press("/")
    assert _focused(page)["filter"] is True
    assert page.locator(FILTER).input_value() == ""          # the '/' itself isn't typed
    page.keyboard.type("red")
    assert _tabs(page) == [["low", "1/2", True], ["out", "1/2", False], ["excluded", "0/1", False]]
    assert [r["fid"] for r in _row_texts(page)] == ["88"] and _active_fid(page) == "88"
    assert _focused(page)["filter"] is True                  # still typing
    page.keyboard.type(" blue")                               # every word, in any order
    assert _tabs(page)[1] == ["out", "0/2", False]
    page.keyboard.press("ArrowDown")                          # into the list
    assert _focused(page)["fid"] == "88"
    page.keyboard.press("/")                                  # back to the filter, its text selected
    page.keyboard.type("zzz")
    assert page.locator(FILTER).input_value() == "zzz"
    assert page.locator(BODY + " .fcc-stock-none").text_content().strip() == "Nothing in Low matches “zzz”."
    page.keyboard.press("ArrowRight")                         # the caret's key in the filter, not a tab switch
    assert [t[2] for t in _tabs(page)] == [True, False, False]


def test_the_filter_reads_tags_reasons_and_notes(panel):
    page, open_ = panel
    open_(_answer(REPORT))
    _wait_state(page, "ready")
    page.locator(FILTER).fill("matte")
    assert [t[1] for t in _tabs(page)] == ["1/2", "0/2", "0/1"]
    page.locator(FILTER).fill("stopped")
    assert [t[1] for t in _tabs(page)] == ["0/2", "0/2", "1/1"]
    page.locator(FILTER).fill("DISCONTINUED sunlu")
    assert [t[1] for t in _tabs(page)] == ["0/2", "0/2", "1/1"]
    page.locator(FILTER).fill("")
    assert [t[1] for t in _tabs(page)] == ["2", "2", "1"]


def test_enter_in_the_filter_opens_the_highlighted_row(panel):
    page, open_ = panel
    open_(_answer(REPORT))
    _wait_state(page, "ready")
    page.keyboard.press("/")
    page.keyboard.type("galaxy")
    page.keyboard.press("Enter")
    assert page.evaluate("window.__opened") == [164]


def test_a_scan_typed_into_the_filter_goes_to_the_scan_path(panel):
    """The filter keeps what was typed before the scan, and the list with it."""
    page, open_ = panel
    open_(_answer(REPORT))
    _wait_state(page, "ready")
    page.keyboard.press("/")
    page.keyboard.type("gal", delay=200)                      # a person
    page.evaluate(f"window.__scanInto(document.querySelector({json.dumps(FILTER)}), 'ID:42')")
    assert page.evaluate("window.__scans") == [["ID:42", "barcode"]]
    assert page.locator(FILTER).input_value() == "gal"
    assert [r["fid"] for r in _row_texts(page)] == ["164"]
    assert page.evaluate("window.__opened") == []


def test_slash_during_a_scan_is_left_to_the_scan(panel):
    """A Prusament QR's URL carries '/': mid-scan it is a character, not a key."""
    page, open_ = panel
    open_(_answer(REPORT))
    _wait_state(page, "ready")
    page.evaluate("state.scanBuffer = 'https:'; state.scanStartTime = Date.now();")
    page.keyboard.press("/")
    assert _focused(page)["filter"] is False


def test_a_scanners_enter_is_left_to_the_scan_accumulator(panel):
    """An Enter that ends a scan (characters still in the scan buffer) opens
    nothing: the accumulator owns it (window.enterIsAScan)."""
    page, open_ = panel
    open_(_answer(REPORT))
    _wait_state(page, "ready")
    page.evaluate("state.scanBuffer = 'ID:42'; state.scanStartTime = Date.now();")
    page.keyboard.press("Enter")
    assert page.evaluate("window.__opened") == []
    assert page.locator("#fcc-low-stock-overlay").count() == 1
    # Nor does it press a focused button: the row's 🔕 stays unpressed.
    page.locator(BODY + " .fcc-stock-row[data-fid='164'] [data-stock-exclude]").focus()
    page.evaluate("state.scanBuffer = 'ID:42'; state.scanStartTime = Date.now();")
    page.keyboard.press("Enter")
    assert page.locator("#fcc-low-stock-reason").count() == 0
    # A person's Enter (empty buffer) then opens the highlighted filament.
    page.evaluate("state.scanBuffer = ''; state.scanStartTime = 0;")
    page.locator(BODY + " .fcc-stock-row[data-fid='164']").focus()
    page.keyboard.press("Enter")
    assert page.evaluate("window.__opened") == [164]


def test_escape_closes_and_stops_listening(panel):
    page, open_ = panel
    open_(_answer(REPORT))
    _wait_state(page, "ready")
    page.keyboard.press("Escape")
    assert page.locator("#fcc-low-stock-overlay").count() == 0
    page.keyboard.press("ArrowDown")
    page.keyboard.press("Enter")
    page.keyboard.press("Delete")
    assert page.evaluate("window.__opened") == []
    assert page.locator("#fcc-low-stock-reason").count() == 0
    assert page.evaluate("window.__errors") == []


def test_enter_on_the_close_button_closes(panel):
    page, open_ = panel
    open_(_answer(REPORT))
    _wait_state(page, "ready")
    page.locator(PANEL + " [data-stock-close]").focus()
    page.keyboard.press("Enter")
    assert page.locator("#fcc-low-stock-overlay").count() == 0
    assert page.evaluate("window.__opened") == []


# --- mouse ----------------------------------------------------------------------------

def test_a_click_on_a_row_opens_its_filament_but_buy_does_not(panel):
    page, open_ = panel
    open_(_answer(REPORT))
    _wait_state(page, "ready")
    # Keep the link from navigating anywhere; the panel's own handler still runs.
    page.evaluate(f"""() => document.querySelectorAll({json.dumps(BODY)} + ' a.fcc-stock-buy')
        .forEach((a) => a.addEventListener('click', (e) => e.preventDefault()))""")
    page.locator(BODY + " .fcc-stock-row[data-fid='164'] a.fcc-stock-buy").click()
    assert page.evaluate("window.__opened") == []
    assert page.locator("#fcc-low-stock-overlay").count() == 1
    page.locator(BODY + " .fcc-stock-row[data-fid='88'] .fcc-stock-name").click()
    assert page.evaluate("window.__opened") == [88]


def test_a_click_outside_the_panel_closes_it(panel):
    page, open_ = panel
    open_(_answer(REPORT))
    _wait_state(page, "ready")
    page.mouse.click(5, 5)
    assert page.locator("#fcc-low-stock-overlay").count() == 0


# --- excluded: the reason dialog --------------------------------------------------------

def test_the_mark_button_asks_why_and_needs_a_reason(panel):
    """RED on 68a9b9d: no such button (a One-off attribute was the only way)."""
    page, open_ = panel
    open_(_answer(REPORT))
    _wait_state(page, "ready")
    page.locator(BODY + " .fcc-stock-row[data-fid='164'] [data-stock-exclude]").click()
    assert _dialog_open(page)
    dlg = page.locator(DIALOG)
    assert dlg.locator(".fcc-stock-dlg-title").text_content() == "🔕 Exclude from Low and Out"
    assert dlg.locator(".fcc-stock-dlg-name").text_content() == "Prusament - PLA - Galaxy Black"
    radios = dlg.locator("input[name='fcc-stock-reason']")
    assert [radios.nth(i).get_attribute("value") for i in range(radios.count())] == [
        "discontinued", "cant_find", "one_off", "didnt_like", "other"]
    assert " ".join(dlg.locator("fieldset").inner_text().split()) == (
        "Why? Discontinued — the maker stopped making it Can't find it — the maker or your usual sellers "
        "don't have it One-off — bought once, on purpose Didn't like it Other — say why in the note")
    assert dlg.locator("input[name='fcc-stock-reason']:checked").count() == 0
    assert [b.strip() for b in dlg.locator("button").all_text_contents()] == ["🔕 Exclude", "Cancel"]
    assert _focused(page)["value"] == "discontinued"          # the first reason has the focus
    dlg.locator("[data-stock-dlg-save]").click()
    assert _dialog_msg(page) == "Pick why first."
    dlg.locator("input[value='other']").check()
    dlg.locator("[data-stock-dlg-save]").click()
    assert _dialog_msg(page) == "Say why in the note: Other needs one."
    assert _focused(page)["note"] is True
    assert page.evaluate("window.__sent") == []
    assert _active_fid(page) == "164"                         # the row it was opened from


def test_saving_marks_it_and_reads_the_list_again_in_place(panel):
    page, open_ = panel
    open_(_answer(REPORT), _answer(_after_marking(REPORT, 164)),
          writes=[_ok("Prusament - PLA - Galaxy Black")])
    _wait_state(page, "ready")
    page.locator(BODY + " .fcc-stock-row[data-fid='164'] [data-stock-exclude]").click()
    page.locator(DIALOG + " input[value='discontinued']").check()
    page.locator(DIALOG + " [data-stock-note-input]").fill("  Prusa stopped making it  ")
    page.locator(DIALOG + " [data-stock-dlg-save]").click()
    page.wait_for_function("() => window.__fetches.length === 2 && !document.querySelector('#fcc-low-stock-reason')")
    page.wait_for_function(f"() => document.querySelectorAll({json.dumps(BODY)} + ' .fcc-stock-row').length === 1")
    today = page.evaluate("(() => { const d = new Date(), p = (n) => String(n).padStart(2, '0');"
                          " return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`; })()")
    assert page.evaluate("window.__sent") == [{"url": "/api/filament/164/stock_exclusion", "method": "POST",
                                               "body": {"reason": "discontinued", "note": "Prusa stopped making it",
                                                        "today": today}}]   # the page's own day
    assert page.evaluate("window.__toasts") == [
        {"msg": "🔕 Prusament - PLA - Galaxy Black is excluded from Low and Out (Discontinued).", "type": "success",
         "ms": 4000}]
    assert _tabs(page) == [["low", "1", True], ["out", "2", False], ["excluded", "2", False]]
    assert _active_fid(page) == "88"                          # the next row took its place
    assert _focused(page)["fid"] == "88"


def test_the_dialog_by_keyboard(panel):
    """Del opens it on the highlighted row, the arrows pick a reason (the
    browser's own radio keys), Enter saves; Escape closes only the dialog."""
    page, open_ = panel
    open_(_answer(REPORT), _answer(_after_marking(REPORT, 88)),
          writes=[_ok("Overture - PETG - Red Blue")])
    _wait_state(page, "ready")
    page.keyboard.press("ArrowDown")
    page.keyboard.press("Delete")
    assert _dialog_open(page)
    page.keyboard.press("Escape")
    assert not _dialog_open(page)
    assert page.locator("#fcc-low-stock-overlay").count() == 1
    assert _focused(page)["fid"] == "88"
    page.keyboard.press("Delete")
    page.keyboard.press("ArrowDown")                          # Discontinued -> Can't find it
    assert page.locator(DIALOG + " input:checked").get_attribute("value") == "cant_find"
    page.keyboard.press("Enter")
    page.wait_for_function("() => window.__sent.length === 1")
    body = page.evaluate("window.__sent[0].body")
    assert (body["reason"], body["note"]) == ("cant_find", "")


def test_delete_in_the_filter_is_the_filters_own_key(panel):
    page, open_ = panel
    open_(_answer(REPORT))
    _wait_state(page, "ready")
    page.keyboard.press("/")
    page.keyboard.type("ab")
    page.keyboard.press("Home")
    page.keyboard.press("Delete")
    assert page.locator(FILTER).input_value() == "b"
    assert not _dialog_open(page)


def test_enter_on_cancel_cancels_and_ctrl_enter_in_the_note_saves(panel):
    page, open_ = panel
    open_(_answer(REPORT), _answer(REPORT), writes=[_ok("Prusament - PLA - Galaxy Black")])
    _wait_state(page, "ready")
    page.keyboard.press("Delete")
    page.locator(DIALOG + " [data-stock-dlg-cancel]").focus()
    page.keyboard.press("Enter")
    assert not _dialog_open(page) and page.evaluate("window.__sent") == []
    page.keyboard.press("Delete")
    page.locator(DIALOG + " input[value='other']").check()
    page.locator(DIALOG + " [data-stock-note-input]").focus()
    page.keyboard.type("first line")
    page.keyboard.press("Enter")                              # a new line, not a save
    page.keyboard.type("second")
    assert page.evaluate("window.__sent") == []
    page.keyboard.press("Control+Enter")
    page.wait_for_function("() => window.__sent.length === 1")
    body = page.evaluate("window.__sent[0].body")
    assert (body["reason"], body["note"]) == ("other", "first line\nsecond")


def test_a_scan_never_answers_the_dialog(panel):
    """Typed onto a reason or into the note, a scan goes to the scan path and
    the dialog stays as it was; a scan's Enter on a button is the accumulator's."""
    page, open_ = panel
    open_(_answer(REPORT))
    _wait_state(page, "ready")
    page.keyboard.press("Delete")
    page.locator(DIALOG + " input[value='discontinued']").check()
    page.evaluate(f"window.__scanInto(document.querySelector({json.dumps(DIALOG)} + ' input[value=discontinued]'), 'ID:42')")
    note = page.locator(DIALOG + " [data-stock-note-input]")
    note.fill("kept")
    page.evaluate(f"window.__scanInto(document.querySelector({json.dumps(DIALOG)} + ' [data-stock-note-input]'), 'LOC:XL')")
    assert note.input_value() == "kept"
    page.locator(DIALOG + " [data-stock-dlg-save]").focus()
    page.evaluate("state.scanBuffer = 'ID:43'; state.scanStartTime = Date.now();")
    page.keyboard.press("Enter")
    assert page.evaluate("window.__scans") == [["ID:42", "barcode"], ["LOC:XL", "barcode"]]
    assert page.evaluate("window.__sent") == [] and _dialog_open(page)


def test_a_failed_save_keeps_the_dialog_and_says_why(panel):
    page, open_ = panel
    refused = _answer({"success": False, "error": "write_failed",
                       "msg": "Spoolman didn't save it: HTTP 400: Unknown extra field fcc_stock_excluded"}, status=502)
    open_(_answer(REPORT), writes=[refused, _answer(None, network=True)])
    _wait_state(page, "ready")
    page.keyboard.press("Delete")
    page.locator(DIALOG + " input[value='discontinued']").check()
    page.locator(DIALOG + " [data-stock-dlg-save]").click()
    page.wait_for_function(f"() => document.querySelector({json.dumps(DIALOG)} + ' [data-stock-dlg-msg]').textContent.includes('Unknown')")
    assert _dialog_msg(page) == "Spoolman didn't save it: HTTP 400: Unknown extra field fcc_stock_excluded"
    assert page.evaluate("window.__toasts") == [
        {"msg": "Spoolman didn't save it: HTTP 400: Unknown extra field fcc_stock_excluded", "type": "error", "ms": 7000}]
    assert page.locator(DIALOG + " [data-stock-dlg-save]").is_enabled()
    page.locator(DIALOG + " [data-stock-dlg-save]").click()
    page.wait_for_function("() => window.__toasts.length === 2")
    assert _dialog_msg(page) == "FCC didn't answer, so nothing was changed. Try again in a moment."
    assert page.evaluate("window.__fetches.length") == 1      # nothing to read again


def test_escape_while_saving_keeps_the_dialog_until_the_answer(panel):
    page, open_ = panel
    open_(_answer(REPORT), _answer(_after_marking(REPORT, 164)),
          writes=[dict(_ok("Prusament - PLA - Galaxy Black"), delay=700)])
    _wait_state(page, "ready")
    page.keyboard.press("Delete")
    page.locator(DIALOG + " input[value='discontinued']").check()
    page.locator(DIALOG + " [data-stock-dlg-save]").click()
    assert _dialog_msg(page) == "Saving…"
    page.keyboard.press("Escape")
    assert _dialog_open(page)
    page.wait_for_function("() => !document.querySelector('#fcc-low-stock-reason') && window.__toasts.length === 1")
    assert page.locator("#fcc-low-stock-overlay").count() == 1


def test_editing_an_exclusion_changes_why_or_includes_it_again(panel):
    page, open_ = panel
    open_(_answer(REPORT), _answer(_after_marking(REPORT, 41, mark=False)),
          writes=[_answer({"success": True, "display": "Sunlu - PLA - Glow Green", "excluded": None,
                           "changed": True, "msg": "ok"})])
    _wait_state(page, "ready")
    _tab(page, "excluded")
    page.locator(BODY + " .fcc-stock-row[data-fid='41'] [data-stock-edit]").click()
    dlg = page.locator(DIALOG)
    assert dlg.locator("input:checked").get_attribute("value") == "discontinued"
    assert _focused(page)["value"] == "discontinued"
    assert dlg.locator("[data-stock-note-input]").input_value() == "Prusa stopped making it"
    assert dlg.locator(".fcc-stock-dlg-was").text_content() == "Excluded on 2026-10-20: Discontinued."
    assert [b.strip() for b in dlg.locator("button").all_text_contents()] == ["Save", "↩️ Include again", "Cancel"]
    dlg.locator("[data-stock-dlg-include]").click()
    page.wait_for_function("() => window.__fetches.length === 2 && !document.querySelector('#fcc-low-stock-reason')")
    assert page.evaluate("window.__sent") == [{"url": "/api/filament/41/stock_exclusion", "method": "DELETE", "body": None}]
    assert page.evaluate("window.__toasts")[0] == {
        "msg": "↩️ Sunlu - PLA - Glow Green is included again: it shows on Low or Out when it is low or out.",
        "type": "success", "ms": 4000}
    page.wait_for_function(f"() => !document.querySelector({json.dumps(BODY)} + ' .fcc-stock-row')")
    assert _tabs(page) == [["low", "3", False], ["out", "2", False], ["excluded", "0", True]]   # stays on its list


def test_delete_on_the_excluded_list_opens_its_reason(panel):
    page, open_ = panel
    open_(_answer(REPORT))
    _wait_state(page, "ready")
    page.keyboard.press("ArrowLeft")                          # wraps to Excluded
    page.keyboard.press("Delete")
    assert page.locator(DIALOG).get_attribute("data-fid") == "41"
    assert page.locator(DIALOG + " [data-stock-dlg-include]").count() == 1


def test_a_reason_typed_in_spoolman_by_hand_goes_into_the_note(panel):
    """It reads as Other (the server's rule), and a Save keeps its words."""
    page, open_ = panel
    report = copy.deepcopy(REPORT)
    report["excluded"][0]["excluded"] = {"reason": "too brittle", "code": "other", "note": "snaps", "at": ""}
    open_(_answer(report))
    _wait_state(page, "ready")
    _tab(page, "excluded")
    assert _row_texts(page)[0]["why"] == "too brittle"
    assert _row_texts(page)[0]["note"] == "“snaps”"
    page.keyboard.press("Delete")
    dlg = page.locator(DIALOG)
    assert dlg.locator("input:checked").get_attribute("value") == "other"
    assert dlg.locator("[data-stock-note-input]").input_value() == "too brittle — snaps"
    assert dlg.locator(".fcc-stock-dlg-was").text_content() == "Excluded: too brittle."


def test_the_dialog_closes_with_the_search_panel(panel):
    page, open_ = panel
    open_(_answer(REPORT))
    _wait_state(page, "ready")
    page.keyboard.press("Delete")
    assert _dialog_open(page)
    page.evaluate("document.getElementById('offcanvasSearch').dispatchEvent(new Event('hidden.bs.offcanvas'))")
    assert page.locator("#fcc-low-stock-overlay").count() == 0
    assert page.locator("#fcc-low-stock-reason").count() == 0
    page.keyboard.press("Enter")
    page.keyboard.press("ArrowDown")
    assert page.evaluate("window.__errors") == [] and page.evaluate("window.__sent") == []


# --- safety ---------------------------------------------------------------------------

def test_every_piece_of_text_is_escaped(panel):
    page, open_ = panel
    report = copy.deepcopy(REPORT)
    report["low"][0]["display"] = 'Evil - PLA - <img src=x onerror="window.__xss=1">'
    report["low"][0]["attributes"] = ["<b>Bold</b>"]
    report["out"][0]["filament_id"] = '20"><script>window.__xss=2</script>'
    report["excluded"][0]["excluded"] = {"reason": '<img src=x onerror="window.__xss=3">', "code": "other",
                                                 "note": "</textarea><img src=x onerror=\"window.__xss=4\">",
                                                 "at": "<i>x</i>"}
    open_(_answer(report))
    _wait_state(page, "ready")
    page.keyboard.press("Delete")                             # the dialog draws the name too
    page.keyboard.press("Escape")
    _tab(page, "out")
    _tab(page, "excluded")
    page.keyboard.press("Delete")
    page.wait_for_timeout(100)
    assert page.evaluate("window.__xss") is None
    assert page.locator(PANEL + " img, #fcc-low-stock-reason img").count() == 0
    assert page.locator(PANEL + " b, " + PANEL + " i").count() == 0
    assert page.locator(DIALOG + " [data-stock-note-input]").input_value().startswith("<img src=x")


def test_it_asks_only_when_opened_and_never_again_on_its_own(panel):
    page, open_ = panel
    assert page.evaluate("window.__fetches") == []          # loading the module asks nothing
    open_(_answer(REPORT))
    _wait_state(page, "ready")
    page.wait_for_timeout(1200)
    assert page.evaluate("window.__fetches") == ["/api/stock_report"]


def test_a_stale_answer_never_paints_over_a_newer_one(panel):
    page, open_ = panel
    slow = copy.deepcopy(REPORT)
    slow["low"] = slow["low"][:1]
    slow["out"], slow["excluded"] = [], []
    open_(_answer(slow, delay=500), _answer(EMPTY))
    page.evaluate("window.openLowStockPanel()")             # re-opened before the first answer
    _wait_state(page, "empty")
    page.wait_for_timeout(800)
    assert _state(page) == "empty"
    assert page.locator("#fcc-low-stock-overlay").count() == 1


def test_it_closes_with_the_search_panel_it_was_opened_from(panel):
    page, open_ = panel
    open_(_answer(REPORT))
    _wait_state(page, "ready")
    assert page.evaluate("getComputedStyle(document.getElementById('global-search-material')).pointerEvents") == "none"
    page.evaluate("document.getElementById('offcanvasSearch').dispatchEvent(new Event('hidden.bs.offcanvas'))")
    assert page.locator("#fcc-low-stock-overlay").count() == 0
    assert page.evaluate("getComputedStyle(document.getElementById('global-search-material')).pointerEvents") != "none"


def test_its_keys_are_in_the_shortcut_reference(panel):
    page, _ = panel
    ids = page.evaluate("window.__pendingShortcuts.map((s) => s.id)")
    assert {"low-stock-arrows", "low-stock-tabs", "low-stock-filter", "low-stock-enter", "low-stock-delete",
            "low-stock-reason-save", "low-stock-escape"} <= set(ids)


# --- contrast (standing order) ---------------------------------------------------------

def test_every_list_is_readable(panel, assert_contrast):
    page, open_ = panel
    open_(_answer(REPORT))
    _wait_state(page, "ready")
    assert_contrast(page.locator(PANEL))
    page.keyboard.press("ArrowDown")                        # a highlighted row too
    assert_contrast(page.locator(PANEL))
    for key in ("out", "excluded"):
        _tab(page, key)
        assert_contrast(page.locator(PANEL))
    page.locator(FILTER).fill("nothing matches this")
    assert_contrast(page.locator(PANEL))


def test_the_dialog_is_readable(panel, assert_contrast):
    page, open_ = panel
    open_(_answer(REPORT))
    _wait_state(page, "ready")
    page.keyboard.press("Delete")
    assert_contrast(page.locator(DIALOG))
    page.locator(DIALOG + " [data-stock-dlg-save]").click()   # with its message
    assert_contrast(page.locator(DIALOG))
    page.keyboard.press("Escape")
    _tab(page, "excluded")
    page.keyboard.press("Delete")                             # editing: Save / Include again / Cancel
    assert_contrast(page.locator(DIALOG))


_SIZES_JS = r"""(sel) => {
    const root = document.querySelector(sel);
    const out = [];
    const walk = (el) => {
        for (const c of el.children) walk(c);
        const own = Array.from(el.childNodes).some((n) => n.nodeType === 3 && n.textContent.trim());
        if (own && el.getClientRects().length) {
            out.push([String(el.className || el.tagName), parseFloat(getComputedStyle(el).fontSize),
                      el.textContent.trim().slice(0, 40)]);
        }
    };
    if (root) walk(root);
    return out;
}"""


def _too_small(page, sel):
    """Text in `sel` under 13.6 px (12.8 for a tag or a count badge) at the
    browser's default font size."""
    small = []
    for cls, px, text in page.evaluate(_SIZES_JS, sel):
        floor = 12.8 if ("fcc-stock-tag" in cls or "fcc-stock-count" in cls) else 13.6
        if px < floor - 0.05:
            small.append((cls, px, text))
    return small


def test_no_text_is_too_small_to_read(panel):
    """Derek, 2026-10-21: the line under the title, the caption above the list
    and the key legend were "really small", the rest "a little on the small
    side", a worry on other screens and zoom levels. Nothing read in the window
    or its dialog is under 13.6 px at the browser's default font size (tags and
    count badges 12.8). RED on 38dbdd2 (11.9 px legend, 12.5 px caption)."""
    page, open_ = panel
    open_(_answer(REPORT))
    _wait_state(page, "ready")
    assert page.evaluate("parseFloat(getComputedStyle(document.documentElement).fontSize)") == 16
    seen = []
    for key in ("low", "out", "excluded"):
        _tab(page, key)
        seen += _too_small(page, PANEL)
    page.keyboard.press("Delete")                            # the dialog, editing (Excluded list)
    seen += _too_small(page, DIALOG)
    page.locator(DIALOG + " [data-stock-dlg-save]").click()  # with its message line
    seen += _too_small(page, DIALOG)
    assert seen == [], seen


def test_the_empty_and_error_states_are_readable(panel, assert_contrast):
    page, open_ = panel
    open_(_answer(EMPTY))
    _wait_state(page, "empty")
    assert_contrast(page.locator(PANEL))
    open_(_answer(DOWN, status=502), click=False)
    _wait_state(page, "error")
    assert_contrast(page.locator(PANEL))


def test_the_loading_state_is_readable(panel, assert_contrast):
    page, open_ = panel
    open_(_answer(REPORT, delay=1500))
    assert _state(page) == "loading"
    assert_contrast(page.locator(PANEL))


# --- Derek, 2026-10-20: the list comes back -------------------------------------------

def _back(page, fetches):
    page.wait_for_function(
        "(n) => window.__fetches.length === n && document.querySelector('#fcc-low-stock-overlay .fcc-stock-row.kb-active')",
        arg=fetches, timeout=5000)
    return page.evaluate("() => document.querySelector('#fcc-low-stock-overlay .fcc-stock-row.kb-active').dataset.fid")


def test_the_list_comes_back_on_the_same_row_after_the_filament_window_closes(panel):
    """RED on 2ec9f46: it stayed closed."""
    page, open_ = panel
    open_(_answer(REPORT))
    _wait_state(page, "ready")
    page.locator(BODY + " .fcc-stock-row[data-fid='88'] .fcc-stock-name").click()
    assert page.evaluate("window.__opened") == [88]
    assert page.locator("#fcc-low-stock-overlay").count() == 0
    page.evaluate("window.__closeModal('filamentModal')")
    assert _back(page, 2) == "88"                            # read afresh, on the row it left
    # Once: a later window closing doesn't bring it back again.
    page.locator(PANEL + " [data-stock-close]").click()
    page.evaluate("window.__showModal('spoolModal'); window.__closeModal('spoolModal')")
    page.wait_for_timeout(700)
    assert page.locator("#fcc-low-stock-overlay").count() == 0
    assert page.evaluate("window.__errors") == []


def test_it_comes_back_on_the_same_list_and_filter(panel):
    """RED on 68a9b9d: no lists or filter to come back to."""
    page, open_ = panel
    open_(_answer(REPORT))
    _wait_state(page, "ready")
    page.keyboard.press("ArrowRight")                        # Out
    page.keyboard.press("/")
    page.keyboard.type("red")
    page.keyboard.press("Enter")                             # opens #20 (Lipstick Red)
    assert page.evaluate("window.__opened") == [20]
    page.evaluate("window.__closeModal('filamentModal')")
    assert _back(page, 2) == "20"
    assert [t[2] for t in _tabs(page)] == [False, True, False]
    assert page.locator(FILTER).input_value() == "red"
    assert [r["fid"] for r in _row_texts(page)] == ["20"]


def test_it_waits_while_another_window_is_up(panel):
    """A spool opened from the filament window takes its place: the list comes
    back only once nothing else is up."""
    page, open_ = panel
    open_(_answer(REPORT))
    _wait_state(page, "ready")
    page.keyboard.press("ArrowRight")
    page.keyboard.press("Enter")                              # opens #20 (the first Out row)
    assert page.evaluate("window.__opened") == [20]
    page.evaluate("window.__showModal('spoolModal'); window.__closeModal('filamentModal')")
    page.wait_for_timeout(700)
    assert page.locator("#fcc-low-stock-overlay").count() == 0   # the spool window is up
    page.evaluate("window.__closeModal('spoolModal')")
    assert _back(page, 2) == "20"


# --- the 2026-10-20 review's three cases ----------------------------------------------

def test_a_filament_window_that_never_opens_leaves_no_arm(panel):
    """browser-4: the read failed, so no window opened; a later, unrelated window
    closing must not pop the list up."""
    page, open_ = panel
    open_(_answer(REPORT))
    _wait_state(page, "ready")
    page.evaluate("window.__failOpen = true")
    page.locator(BODY + " .fcc-stock-row[data-fid='88'] .fcc-stock-name").click()
    assert page.evaluate("window.__opened") == [88]
    page.evaluate("document.getElementById('offcanvasSearch').classList.remove('show');"
                  "window.__showModal('spoolModal'); window.__closeModal('spoolModal')")
    page.wait_for_timeout(700)
    assert page.locator("#fcc-low-stock-overlay").count() == 0
    assert page.evaluate("window.__fetches.length") == 1


def test_it_waits_for_a_window_still_opening_in_the_filaments_place(panel):
    """browser-2: the wizard opened from the filament window closes, and its own
    close handler reopens the filament window 200 ms later, after a read. The
    list stays away until that window closes."""
    page, open_ = panel
    open_(_answer(REPORT))
    _wait_state(page, "ready")
    page.locator(BODY + " .fcc-stock-row[data-fid='164'] .fcc-stock-name").click()
    page.evaluate("window.__showModal('wizardModal'); window.__closeModal('filamentModal')")
    page.wait_for_timeout(600)
    assert page.locator("#fcc-low-stock-overlay").count() == 0          # the wizard is up
    page.evaluate("""() => {
        window.__closeModal('wizardModal');
        setTimeout(() => { state.processing = true; }, 200);              // openFilamentDetails reads...
        setTimeout(() => { window.__showModal('filamentModal'); state.processing = false; }, 650);
    }""")
    page.wait_for_timeout(1200)
    assert page.locator("#fcc-low-stock-overlay").count() == 0          # never over the returning window
    page.evaluate("window.__closeModal('filamentModal')")
    assert _back(page, 2) == "164"


def test_a_list_that_came_back_closes_under_a_new_window_and_returns_after(panel):
    """browser-3: with no search panel to close it with, a window opened over the
    restored list used to sit under it."""
    page, open_ = panel
    open_(_answer(REPORT))
    _wait_state(page, "ready")
    page.keyboard.press("ArrowRight")                                    # Out
    page.locator(BODY + " .fcc-stock-row[data-fid='29'] .fcc-stock-name").click()
    page.evaluate("window.__closeModal('filamentModal')")
    assert _back(page, 2) == "29"
    page.keyboard.press("Delete")                                        # its dialog goes with it
    page.evaluate("window.__showModal('spoolModal')")                   # a scan opens a window
    page.wait_for_timeout(200)
    assert page.locator("#fcc-low-stock-overlay").count() == 0
    assert page.locator("#fcc-low-stock-reason").count() == 0
    page.evaluate("window.__closeModal('spoolModal')")
    assert _back(page, 3) == "29"
    assert [t[2] for t in _tabs(page)] == [False, True, False]
    assert page.evaluate("window.__errors") == []
