"""A '/' in a scan still arriving is the scan's, however slow the scanner
(Group 57 review, round 3), hermetic.

Runs the REAL scan accumulator (the keydown block of
templates/components/scripts.html, lifted as it is), the REAL fab_drag.js (the
global search's '/') and the REAL overlay_mount.js, inv_core.js and
inv_stock.js, with the ⚠️ button's real markup, in `isolated_page` (a chromium
with no route to any network), so it RUNS under --offline. The keys are typed
on a fake clock (Date.now and performance.now), one every `ms`, so a scanner's
speed is exact whatever the machine's load.

The defect: a Prusament spool QR is a URL ending in '/'. isScanInFlight's
500 ms runs from a scan's FIRST key, and a slower scanner (about 12 ms a key or
more) is still typing the 45-character URL after it, so a late '/' read as a
person's. The Low stock reason dialog claimed it and emptied the scan buffer
(d1fcea3), and the scan's Enter then pressed the dialog's focused button: a
scan saved an exclusion, or "Include again" removed one. The list claimed it
too (its filter key) and opened a filament window, and fab_drag.js opened the
search.

Pinned, at every speed from 1 to 40 ms a key: the URL reaches processScan whole
and once; the dialog writes nothing and stays up; the search never opens; the
list opens no filament window and keeps its filter as it was. A person's lone
'/' (the buffer empty, or its last key over 500 ms ago) is still the dialog's,
the list's (its filter) and the page's (the search). RED on 2749590.
"""
from __future__ import annotations

import copy
from pathlib import Path

import pytest

from test_low_stock_glance_57_js import (BOOTSTRAP_HIDDEN, BODY, BTN, GLOBAL_CSS, MARK, MODULES, PAGE, PANEL,
                                         PRELUDE, REPORT, _answer, _button_markup)

HUB = Path(__file__).resolve().parent.parent
SCRIPTS = HUB / "templates" / "components" / "scripts.html"
URL = "https://prusament.com/spool/17705/5b1a183b26/"     # FCC's Prusament QR shape (logic.py)
SPEEDS = [1, 8, 13, 18, 26, 40]                            # ms a key: fast to a slow Bluetooth scanner
DIALOG = "#fcc-low-stock-reason"


def _accumulator():
    """The scan accumulator, exactly as the page has it."""
    src = SCRIPTS.read_text(encoding="utf-8")
    a = src.index("state.scanStartTime = 0;")
    b = src.index("// L206", a)
    block = src[a:b]
    assert "processScan(state.scanBuffer" in block and "state.scanBuffer += e.key" in block, block[:300]
    return block


STUBS = r"""
window.__scans = [];
window.processScan = function (buf) { window.__scans.push(buf); };
window.__search = 0;
window.SearchEngine = { open: function () { window.__search += 1; } };
"""

# Typing on the page's fake clock: each key `ms` after the one before, Enter last.
TYPE_JS = r"""([text, ms, enter]) => {
    if (!window.__fakeClock) {
        const base = Date.now(), pbase = performance.now();
        window.__T = 0;
        Date.now = () => base + window.__T;
        performance.now = () => pbase + window.__T;
        window.__fakeClock = true;
    }
    const keys = [...text];
    if (enter) keys.push('Enter');
    for (const key of keys) {
        window.__T += ms;
        const t = document.activeElement || document.body;
        t.dispatchEvent(new KeyboardEvent('keydown', { key, bubbles: true, cancelable: true }));
    }
}"""


def _type(page, text, ms, enter=True):
    page.evaluate(TYPE_JS, [text, ms, enter])


def _later(page, ms):
    """The fake clock moves on (no key)."""
    page.evaluate("(ms) => { window.__T += ms; }", ms)


@pytest.fixture
def scan_page(isolated_page):
    page = isolated_page
    page.set_content(PAGE.format(css=GLOBAL_CSS.read_text(encoding="utf-8") + BOOTSTRAP_HIDDEN,
                                 button=_button_markup()))
    page.add_script_tag(content=PRELUDE + STUBS)
    for name in ("overlay_mount.js", "inv_core.js", "inv_stock.js", "fab_drag.js"):
        page.add_script_tag(content=(MODULES / name).read_text(encoding="utf-8"))
    page.add_script_tag(content=_accumulator())        # last, as on the page (after fab_drag.js)
    page.evaluate("() => { window.__toasts = []; window.showToast = (m, t, ms) => window.__toasts.push({m, t, ms}); }")
    _type(page, "", 0, enter=False)                   # the fake clock, before anything is typed
    return page


def _open_list(page, report=None):
    page.evaluate("(a) => { window.__answers = a; }", [_answer(report or REPORT)])
    page.locator(BTN).click()
    page.wait_for_selector(PANEL)
    page.wait_for_function("(s) => document.querySelector(s).dataset.stockState === 'ready'", arg=BODY)


def _seen(page):
    return page.evaluate(f"""() => ({{ scans: window.__scans.slice(), sent: window.__sent.slice(),
        search: window.__search, opened: window.__opened.slice(),
        dialog: !!document.querySelector('{DIALOG}'), list: !!document.querySelector('{PANEL}'),
        filter: !!(document.activeElement && document.activeElement.hasAttribute('data-stock-filter')),
        filterValue: (document.querySelector('[data-stock-filter]') || {{}}).value,
        buffer: state.scanBuffer }})""")


def _reset(page):
    page.evaluate("() => { window.__scans = []; }")
    _later(page, 3000)


@pytest.mark.parametrize("where", ["exclude", "dialog", "include"])
def test_a_slow_scanners_url_never_answers_the_reason_dialog(scan_page, where):
    """The dialog's focused button (Exclude, or Include again on an Excluded
    row), or the dialog itself (a click on its text), and a Prusament URL
    scanned at every speed: the scan goes to the scan path whole, nothing is
    written, the dialog stays. RED on 2749590 from 13 ms a key: POST
    /api/filament/164/stock_exclusion (or DELETE on Include again)."""
    page = scan_page
    if where == "include":
        report = copy.deepcopy(REPORT)
        row = report["low"].pop(0)
        row["excluded"] = MARK
        report["excluded"].append(row)
        _open_list(page, report)
        page.locator('[data-stock-tab="excluded"]').click()
    else:
        _open_list(page)
    page.keyboard.press("Delete")
    page.wait_for_selector(DIALOG)
    if where != "include":
        page.locator(f"{DIALOG} input[value='discontinued']").check()
    target = {"exclude": f"{DIALOG} [data-stock-dlg-save]", "include": f"{DIALOG} [data-stock-dlg-include]",
              "dialog": f"{DIALOG} .fcc-stock-dlg-name"}[where]
    for ms in SPEEDS:
        if where == "dialog":
            page.locator(target).click()                       # the focus on the dialog itself
        else:
            page.locator(target).focus()
        _type(page, URL, ms)
        s = _seen(page)
        assert s["sent"] == [] and s["dialog"], (where, ms, s)
        assert s["scans"] == [URL] and s["search"] == 0 and s["buffer"] == "", (where, ms, s)
        _reset(page)


def test_a_slow_scanners_url_never_works_the_list(scan_page):
    """The list up, a row highlighted, and a URL scanned at every speed: no
    filament window, no filter, no search; the scan goes to the scan path
    whole. RED on 2749590 from 13 ms a key: the late '/' focused the filter,
    the rest of the URL went into it, and its Enter opened #164's window."""
    page = scan_page
    _open_list(page)
    for ms in SPEEDS:
        page.locator("#fcc-low-stock-overlay .fcc-stock-row.kb-active").focus()
        _type(page, URL, ms)
        s = _seen(page)
        assert s["opened"] == [] and not s["filter"] and s["filterValue"] == "" and s["list"], (ms, s)
        assert s["scans"] == [URL] and s["search"] == 0, (ms, s)
        _reset(page)


def test_a_slow_scanners_url_never_opens_the_search(scan_page):
    """No list open: fab_drag.js's '/' has the same rule. RED on 2749590 from
    13 ms a key: the late '/' opened the search panel and was lost."""
    page = scan_page
    for ms in SPEEDS:
        page.evaluate("() => document.activeElement && document.activeElement.blur()")
        _type(page, URL, ms)
        s = _seen(page)
        assert s["scans"] == [URL] and s["search"] == 0, (ms, s)
        _reset(page)


def test_a_persons_slash_is_still_theirs(scan_page):
    """The buffer empty, or its last key over 500 ms ago (a key pressed and
    left): the page's '/' opens the search, the list's focuses its filter, the
    dialog's keeps the search away; none goes into the scan buffer."""
    page = scan_page
    _type(page, "/", 10, enter=False)
    assert _seen(page)["search"] == 1 and _seen(page)["buffer"] == ""
    _later(page, 3000)
    _type(page, "x", 10, enter=False)                    # a key pressed and left
    _later(page, 600)
    _type(page, "/", 10, enter=False)
    assert _seen(page)["search"] == 2, _seen(page)
    page.evaluate("() => window.clearScanBuffer()")
    _later(page, 3000)

    _open_list(page)
    page.locator("#fcc-low-stock-overlay .fcc-stock-row.kb-active").focus()
    _type(page, "x", 10, enter=False)
    _later(page, 600)
    _type(page, "/", 10, enter=False)
    s = _seen(page)
    assert s["filter"] and s["search"] == 2 and s["buffer"] == "", s

    page.locator("#fcc-low-stock-overlay .fcc-stock-row.kb-active").focus()
    page.keyboard.press("Delete")
    page.wait_for_selector(DIALOG)
    page.locator(f"{DIALOG} [data-stock-dlg-save]").focus()
    _later(page, 3000)
    _type(page, "/", 10, enter=False)
    s = _seen(page)
    assert s["dialog"] and s["search"] == 2 and s["buffer"] == "" and s["sent"] == [], s
