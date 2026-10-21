"""Group 49.2a: the ⚠️ Low-stock panel (static/js/modules/inv_stock.js), hermetic.

Runs the REAL overlay_mount.js, inv_core.js and inv_stock.js with the real
static/css/global.css in `isolated_page` (a chromium with no route to any
network), so it RUNS under --offline. `fetch` is stubbed in the page with the
/api/stock_report answers below; `openFilamentDetails` is a recorder.

Pinned: rows (Low then Out, names, grams, spools, tags, swatch), the Buy More
link only when a web link resolves, the empty state ("Nothing is low"), the error
state (Spoolman didn't answer, never an empty list) and its retry, keyboard
navigation (arrows wrap, Enter opens the filament, Escape closes, a scanner's
Enter is left alone), escaping of every piece of text, the contrast guard on
every state, one request per opening (nothing on a heartbeat), a stale answer
never painting, and the panel closing with the search panel it was opened from.

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

# Set up before the modules load: the registerShortcut queue (scripts.html's
# shim), a fetch that answers from window.__answers (one per request; the last
# repeats; {network:true} rejects like a dropped connection, {delay:ms} holds the
# answer), and a recording openFilamentDetails (inv_details.js's global).
PRELUDE = r"""
window.__pendingShortcuts = [];
window.registerShortcut = function (s) { window.__pendingShortcuts.push(s); };
window.__fetches = [];
window.__answers = [];
window.__opened = [];
window.__errors = [];
window.addEventListener('error', (e) => window.__errors.push(String(e.message)));
window.fetch = function (url, opts) {
    window.__fetches.push(String(url));
    const a = window.__answers.length > 1 ? window.__answers.shift() : window.__answers[0];
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
         attrs=(), buy=None):
    brand, material, colour = display.split(" - ")
    return {"filament_id": fid, "brand": brand, "material": material, "color_name": colour,
            "display": display, "color": color, "color_direction": direction,
            "grams": grams, "spools": spools, "spools_total": total,
            "attributes": list(attrs), "one_off": any(a.lower().replace("-", "").replace(" ", "") == "oneoff"
                                                      for a in attrs),
            "buy_url": buy}


REPORT = {
    "success": True, "threshold_g": 250.0, "filaments": 3, "spools": 6,
    "low": [
        _row(164, "Prusament - PLA - Galaxy Black", 151.0, 1, 3,
             buy="https://www.prusa3d.com/product/prusament-pla-galaxy-black/"),
        _row(88, "Overture - PETG - Red Blue", 220.4, 2, 2, color="BA0C2F,0047BB",
             direction="coaxial", attrs=("Silk", "One-off")),
    ],
    "out": [
        _row(20, "Generic - PLA - Lipstick Red", 0, 0, 2, color="ff0000", attrs=("For Infill",),
             buy="https://shop.example/s?q=Generic+PLA+Lipstick%20Red"),
    ],
}
EMPTY = {"success": True, "threshold_g": 250.0, "low": [], "out": [], "filaments": 40, "spools": 90}
DOWN = {"success": False, "error": "spoolman_unreachable",
        "msg": "Spoolman didn't answer, so FCC can't tell what is low right now. Try again in a moment."}


def _answer(body, status=200, **kw):
    a = {"status": status, "body": body}
    a.update(kw)
    return a


@pytest.fixture
def panel(isolated_page):
    """The page with the real modules loaded; returns (page, open(answers...))."""
    page = isolated_page
    page.set_content(PAGE.format(css=GLOBAL_CSS.read_text(encoding="utf-8")))
    page.add_script_tag(content=PRELUDE)
    for name in ("overlay_mount.js", "inv_core.js", "inv_stock.js"):
        page.add_script_tag(content=(MODULES / name).read_text(encoding="utf-8"))

    def _open(*answers, click=True):
        page.evaluate("(a) => { window.__answers = a; }", list(answers))
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
    return page.evaluate(f"""() => Array.from(document.querySelectorAll({json.dumps(PANEL)} + ' .fcc-stock-row'))
        .map((r) => {{
            const nameEl = r.querySelector('.fcc-stock-name');
            const own = Array.from(nameEl.childNodes).filter((n) => n.nodeType === Node.TEXT_NODE)
                .map((n) => n.textContent).join('').replace(/\\s+/g, ' ').trim();
            return {{fid: r.dataset.fid, kind: r.dataset.kind, name: own,
                     tags: Array.from(nameEl.querySelectorAll('.fcc-stock-tag')).map((t) => t.textContent),
                     meta: r.querySelector('.fcc-stock-meta').textContent.trim(),
                     active: r.classList.contains('kb-active')}};
        }})""")


# --- what it shows -------------------------------------------------------------------

def test_rows_show_low_then_out_with_names_grams_spools_and_tags(panel):
    page, open_ = panel
    open_(_answer(REPORT))
    _wait_state(page, "ready")
    rows = _row_texts(page)
    assert [(r["fid"], r["kind"]) for r in rows] == [("164", "low"), ("88", "low"), ("20", "out")]
    assert rows[0]["name"] == "Prusament - PLA - Galaxy Black" and rows[0]["tags"] == []
    assert rows[0]["meta"] == "151 g left in 1 spool"
    assert rows[1]["name"] == "Overture - PETG - Red Blue"
    assert rows[1]["tags"] == ["Silk", "One-off"]           # its tags show, One-off included
    assert rows[1]["meta"] == "220 g left in 2 spools"
    assert rows[2]["tags"] == ["For Infill"]
    assert rows[2]["meta"] == "0 g · none in stock (2 spools archived or empty)"
    heads = page.locator(PANEL + " .fcc-stock-h").all_text_contents()
    assert heads == ["Low: under 250 g (2)", "Out: none left in stock (1)"]
    assert "under 250 g" in page.locator(PANEL + " [data-stock-sub]").text_content()
    # The first row is highlighted, ready for Enter.
    assert [r["active"] for r in rows] == [True, False, False]
    # Each row has its filament's swatch (getFilamentStyle: a gradient for multi-colour).
    bgs = page.evaluate(f"""() => Array.from(document.querySelectorAll({json.dumps(PANEL)} + ' .fcc-stock-swatch'))
        .map((s) => getComputedStyle(s).backgroundImage + '|' + getComputedStyle(s).backgroundColor)""")
    assert bgs[0].endswith("|rgb(34, 34, 34)")
    assert "gradient" in bgs[1]


def test_a_buy_more_link_only_when_a_web_link_resolves(panel):
    page, open_ = panel
    report = copy.deepcopy(REPORT)
    report["low"][1]["buy_url"] = "javascript:alert(1)"     # never put in an href
    open_(_answer(report))
    _wait_state(page, "ready")
    links = page.evaluate(f"""() => Array.from(document.querySelectorAll({json.dumps(PANEL)} + ' .fcc-stock-row'))
        .map((r) => {{ const a = r.querySelector('a.fcc-stock-buy');
                       return a ? [a.getAttribute('href'), a.target, a.rel, a.textContent.trim()] : null; }})""")
    assert links[0] == ["https://www.prusa3d.com/product/prusament-pla-galaxy-black/", "_blank",
                        "noopener noreferrer", "🛒 Buy More"]
    assert links[1] is None
    assert links[2][0] == "https://shop.example/s?q=Generic+PLA+Lipstick%20Red"


def test_nothing_low_is_its_own_state(panel):
    page, open_ = panel
    open_(_answer(EMPTY))
    _wait_state(page, "empty")
    text = page.locator(BODY).inner_text()
    assert "Nothing is low." in text and "under 250 g" in text and "none has run out" in text
    assert page.locator(PANEL + " .fcc-stock-row").count() == 0


def test_one_empty_list_says_so_under_its_heading(panel):
    page, open_ = panel
    report = copy.deepcopy(REPORT)
    report["out"] = []
    open_(_answer(report))
    _wait_state(page, "ready")
    out = page.locator(PANEL + " [data-stock-section='out']").inner_text()
    assert "Out: none left in stock (0)" in out and "Nothing is out." in out


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


def test_try_again_asks_again_and_shows_the_list(panel):
    page, open_ = panel
    open_(_answer(DOWN, status=502), _answer(REPORT))
    _wait_state(page, "error")
    page.locator(PANEL + " [data-stock-retry]").click()
    _wait_state(page, "ready")
    assert page.evaluate("window.__fetches.length") == 2
    assert len(_row_texts(page)) == 3


def test_its_own_failure_is_named_as_such(panel):
    page, open_ = panel
    open_(_answer({"success": False, "error": "report_failed", "msg": "FCC couldn't build the Low-stock list: boom"},
                  status=500))
    _wait_state(page, "error")
    text = page.locator(BODY).inner_text()
    assert "FCC couldn't build the list" in text and "boom" in text


# --- keyboard -------------------------------------------------------------------------

def _active_fid(page):
    return page.evaluate(f"""() => {{ const r = document.querySelector({json.dumps(PANEL)} + ' .fcc-stock-row.kb-active');
                                      return r ? r.dataset.fid : null; }}""")


def test_arrows_move_and_wrap_enter_opens_the_filament(panel):
    page, open_ = panel
    open_(_answer(REPORT))
    _wait_state(page, "ready")
    assert _active_fid(page) == "164"
    page.keyboard.press("ArrowDown")
    assert _active_fid(page) == "88"
    page.keyboard.press("ArrowDown")
    assert _active_fid(page) == "20"
    page.keyboard.press("ArrowDown")                    # wraps to the top
    assert _active_fid(page) == "164"
    page.keyboard.press("ArrowUp")                      # and back to the bottom
    assert _active_fid(page) == "20"
    page.keyboard.press("Enter")
    assert page.evaluate("window.__opened") == [20]
    # Opening the filament window closes the panel (a modal would sit under it).
    assert page.locator("#fcc-low-stock-overlay").count() == 0
    assert page.evaluate("window.__errors") == []


def test_escape_closes_and_stops_listening(panel):
    page, open_ = panel
    open_(_answer(REPORT))
    _wait_state(page, "ready")
    page.keyboard.press("Escape")
    assert page.locator("#fcc-low-stock-overlay").count() == 0
    page.keyboard.press("ArrowDown")
    page.keyboard.press("Enter")
    assert page.evaluate("window.__opened") == []
    assert page.evaluate("window.__errors") == []


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
    # A person's Enter (empty buffer) then opens the highlighted filament.
    page.evaluate("state.scanBuffer = ''; state.scanStartTime = 0;")
    page.keyboard.press("Enter")
    assert page.evaluate("window.__opened") == [164]


def test_enter_on_the_close_button_closes(panel):
    page, open_ = panel
    open_(_answer(REPORT))
    _wait_state(page, "ready")
    page.locator(PANEL + " [data-stock-close]").focus()
    page.keyboard.press("Enter")
    assert page.locator("#fcc-low-stock-overlay").count() == 0
    assert page.evaluate("window.__opened") == []


# --- mouse ----------------------------------------------------------------------------

def test_a_click_on_a_row_opens_its_filament_but_buy_more_does_not(panel):
    page, open_ = panel
    open_(_answer(REPORT))
    _wait_state(page, "ready")
    # Keep the link from navigating anywhere; the panel's own handler still runs.
    page.evaluate(f"""() => document.querySelectorAll({json.dumps(PANEL)} + ' a.fcc-stock-buy')
        .forEach((a) => a.addEventListener('click', (e) => e.preventDefault()))""")
    page.locator(PANEL + " .fcc-stock-row[data-fid='164'] a.fcc-stock-buy").click()
    assert page.evaluate("window.__opened") == []
    assert page.locator("#fcc-low-stock-overlay").count() == 1
    page.locator(PANEL + " .fcc-stock-row[data-fid='88'] .fcc-stock-name").click()
    assert page.evaluate("window.__opened") == [88]


def test_a_click_outside_the_panel_closes_it(panel):
    page, open_ = panel
    open_(_answer(REPORT))
    _wait_state(page, "ready")
    page.mouse.click(5, 5)
    assert page.locator("#fcc-low-stock-overlay").count() == 0


# --- safety ---------------------------------------------------------------------------

def test_every_piece_of_text_is_escaped(panel):
    page, open_ = panel
    report = copy.deepcopy(REPORT)
    report["low"][0]["display"] = 'Evil - PLA - <img src=x onerror="window.__xss=1">'
    report["low"][0]["attributes"] = ["<b>Bold</b>"]
    report["out"][0]["filament_id"] = '20"><script>window.__xss=2</script>'
    open_(_answer(report))
    _wait_state(page, "ready")
    page.wait_for_timeout(100)
    assert page.evaluate("window.__xss") is None
    assert page.locator(PANEL + " img").count() == 0
    assert page.locator(PANEL + " b").count() == 0
    assert '<img src=x onerror="window.__xss=1">' in page.locator(PANEL + " .fcc-stock-name").first.text_content()


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
    slow["out"] = []
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
    assert {"low-stock-arrows", "low-stock-enter", "low-stock-escape"} <= set(ids)


# --- contrast (standing order) ---------------------------------------------------------

def test_the_list_is_readable(panel, assert_contrast):
    page, open_ = panel
    open_(_answer(REPORT))
    _wait_state(page, "ready")
    assert_contrast(page.locator(PANEL))
    page.keyboard.press("ArrowDown")                        # a highlighted row too
    assert_contrast(page.locator(PANEL))


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


# --- Derek, 2026-10-20: the One-off hint, and the list comes back -------------------

def test_the_out_section_says_how_a_filament_leaves_it(panel):
    """RED on 2ec9f46: no hint there."""
    page, open_ = panel
    open_(_answer(REPORT))
    _wait_state(page, "ready")
    out = page.locator(PANEL + " [data-stock-section='out']")
    hint = out.locator("[data-stock-hint]")
    assert hint.count() == 1, out.inner_html()
    text = " ".join(hint.text_content().split())
    assert text == ('Won\'t buy one again? Tag it One-off and it leaves this list: add "One-off" in '
                    '⚙️ → 🏷️ Filament Attributes, then give it to the filament (✏️ Edit Filament → Attributes).'), text
    assert page.locator(PANEL + " [data-stock-section='low'] [data-stock-hint]").count() == 0


def _back(page, fid, fetches):
    page.wait_for_function(
        "(n) => window.__fetches.length === n && document.querySelector('#fcc-low-stock-overlay .fcc-stock-row.kb-active')",
        arg=fetches, timeout=5000)
    return page.evaluate("() => document.querySelector('#fcc-low-stock-overlay .fcc-stock-row.kb-active').dataset.fid")


def test_the_list_comes_back_on_the_same_row_after_the_filament_window_closes(panel):
    """RED on 2ec9f46: it stayed closed."""
    page, open_ = panel
    open_(_answer(REPORT))
    _wait_state(page, "ready")
    page.locator(PANEL + " .fcc-stock-row[data-fid='88'] .fcc-stock-name").click()
    assert page.evaluate("window.__opened") == [88]
    assert page.locator("#fcc-low-stock-overlay").count() == 0
    page.evaluate("window.__closeModal('filamentModal')")
    assert _back(page, "88", 2) == "88"                       # read afresh, on the row it left
    # Once: a later window closing doesn't bring it back again.
    page.locator(PANEL + " [data-stock-close]").click()
    page.evaluate("window.__showModal('spoolModal'); window.__closeModal('spoolModal')")
    page.wait_for_timeout(700)
    assert page.locator("#fcc-low-stock-overlay").count() == 0
    assert page.evaluate("window.__errors") == []


def test_it_waits_while_another_window_is_up(panel):
    """A spool opened from the filament window takes its place: the list comes
    back only once nothing else is up."""
    page, open_ = panel
    open_(_answer(REPORT))
    _wait_state(page, "ready")
    page.keyboard.press("ArrowDown")
    page.keyboard.press("ArrowDown")
    page.keyboard.press("Enter")                              # opens #20 (the Out row)
    assert page.evaluate("window.__opened") == [20]
    page.evaluate("window.__showModal('spoolModal'); window.__closeModal('filamentModal')")
    page.wait_for_timeout(700)
    assert page.locator("#fcc-low-stock-overlay").count() == 0   # the spool window is up
    page.evaluate("window.__closeModal('spoolModal')")
    assert _back(page, "20", 2) == "20"


# --- the 2026-10-20 review's three cases ----------------------------------------------

def test_a_filament_window_that_never_opens_leaves_no_arm(panel):
    """browser-4: the read failed, so no window opened; a later, unrelated window
    closing must not pop the list up."""
    page, open_ = panel
    open_(_answer(REPORT))
    _wait_state(page, "ready")
    page.evaluate("window.__failOpen = true")
    page.locator(PANEL + " .fcc-stock-row[data-fid='88'] .fcc-stock-name").click()
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
    page.locator(PANEL + " .fcc-stock-row[data-fid='164'] .fcc-stock-name").click()
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
    assert _back(page, "164", 2) == "164"


def test_a_list_that_came_back_closes_under_a_new_window_and_returns_after(panel):
    """browser-3: with no search panel to close it with, a window opened over the
    restored list used to sit under it."""
    page, open_ = panel
    open_(_answer(REPORT))
    _wait_state(page, "ready")
    page.locator(PANEL + " .fcc-stock-row[data-fid='20'] .fcc-stock-name").click()
    page.evaluate("window.__closeModal('filamentModal')")
    assert _back(page, "20", 2) == "20"
    page.evaluate("window.__showModal('spoolModal')")                   # a scan opens a window
    page.wait_for_timeout(200)
    assert page.locator("#fcc-low-stock-overlay").count() == 0
    page.evaluate("window.__closeModal('spoolModal')")
    assert _back(page, "20", 3) == "20"
    assert page.evaluate("window.__errors") == []
