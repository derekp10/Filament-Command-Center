"""Group 66.4: a label scanned while one of the search panel's boxes has the keyboard is a
scan, never words to search for.

🔍 FIND SPOOL (the global search, `#offcanvasSearch`) focuses its query box, and its
boxes had no scan capture: a spool's label scanned there was searched as words ("No
matching spools found"), and it never reached the scan path. They get the audit Find's
install (labels mode, the page's payload rule, the default scan path): the label goes on
as a scan does anywhere outside a box (a spool's joins the scan buffer), and the box keeps
what was typed, its own search running again for that (Derek's call 2 (a): in the
wizard's select mode too).

Hermetic: the real offcanvas_search.html, overlay_mount.js, inv_core.js and inv_search.js
in `isolated_page` with a Bootstrap stand-in (Group 66.8's), the scan path a stub. Each
case marked RED fails on the commit before this one for the reason it names.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from test_scanner_safe_dialogs_61_js import TYPE_BOX_JS
from test_wizard_advanced_search_66_8_js import PANEL_PRELUDE

HUB = Path(__file__).resolve().parent.parent
MODULES = HUB / "static" / "js" / "modules"
SEARCH_HTML = HUB / "templates" / "components" / "offcanvas_search.html"

RECORD = r"""
window.__si = window.setInterval; window.setInterval = () => 0;
window.__searches = [];
window.fetch = (url) => {
    const u = String(url);
    if (u.startsWith('/api/search')) window.__searches.push(decodeURIComponent(u.replace(/\+/g, ' ')));
    return Promise.resolve({ ok: true, status: 200,
        json: () => Promise.resolve({ success: true, materials: [], results: [] }) });
};
"""


@pytest.fixture
def panel(isolated_page):
    page = isolated_page
    page.set_content('<!doctype html><html><head><meta charset="utf-8"></head><body>'
                     '<div id="toast-container"></div>'
                     + SEARCH_HTML.read_text(encoding="utf-8") + '</body></html>')
    page.add_script_tag(content=PANEL_PRELUDE)
    page.add_script_tag(content=RECORD)
    for name in ("overlay_mount.js", "inv_core.js", "inv_search.js"):
        page.add_script_tag(content=(MODULES / name).read_text(encoding="utf-8"))
    page.evaluate("""() => {
        window.setInterval = window.__si;
        window.__scans = [];
        window.processScan = (t, s) => { window.__scans.push([t, s]); };
        window.SearchEngine.init();      // its DOMContentLoaded has passed
    }""")
    return page


def _type_box(page, box, text, ms, enter=True):
    page.focus(box)
    page.evaluate(TYPE_BOX_JS, [text, ms, enter, {}])


def _settled(page):
    """The panel's 300 ms debounce, and its search's answer."""
    page.wait_for_timeout(600)
    return page.evaluate("() => ({ scans: window.__scans.map((s) => s[0]), searches: window.__searches,"
                         " errors: window.__errors })")


def test_a_label_in_the_search_box_is_a_scan_not_words(panel):
    """"sunlu" typed by hand, then a spool's label scanned: one scan, the box reads
    "sunlu", and nothing searched for the label. RED: "sunluID:57" searched, no scan."""
    _type_box(panel, "#global-search-query", "sunlu", 120, enter=False)
    panel.evaluate("() => { window.__T += 700; }")
    _type_box(panel, "#global-search-query", "ID:57", 5)
    got = _settled(panel)
    assert got["scans"] == ["ID:57"], got
    assert panel.locator("#global-search-query").input_value() == "sunlu"
    assert not [u for u in got["searches"] if "ID:57" in u], got["searches"]
    assert got["searches"] and "q=sunlu" in got["searches"][-1], got["searches"]
    assert got["errors"] == [], got


def test_a_label_in_the_colour_box_is_a_scan(panel):
    """RED: the label stayed in the colour box as text."""
    _type_box(panel, "#global-search-color-hex", "ID:57", 5)
    got = _settled(panel)
    assert got["scans"] == ["ID:57"] and panel.locator("#global-search-color-hex").input_value() == "", got


def test_a_label_in_a_weight_box_is_a_scan(panel):
    """A number box keeps only a label's digits. RED: the box read 57 (a minimum weight)."""
    panel.focus("#global-search-min-weight")
    panel.keyboard.type("ID:57", delay=5)
    panel.keyboard.press("Enter")
    got = _settled(panel)
    assert got["scans"] == ["ID:57"], got
    assert panel.locator("#global-search-min-weight").input_value() == ""


def test_a_persons_words_with_a_colon_are_searched(panel):
    """A pin: words typed at a person's pace stay theirs, and are searched."""
    _type_box(panel, "#global-search-query", "Prusament: Galaxy", 120)
    got = _settled(panel)
    assert got["scans"] == [] and panel.locator("#global-search-query").input_value() == "Prusament: Galaxy", got
    assert got["searches"] and "q=Prusament: Galaxy" in got["searches"][-1], got["searches"]
