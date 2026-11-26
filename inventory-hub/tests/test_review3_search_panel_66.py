"""Review round 3 of Group 66 (scan-journal R3-03): only the search panel's newest search
paints its answer.

🔍 FIND SPOOL's searches kept no order: each answer painted whenever it landed. A scanner
that stalls inside a label (CLAUDE.md: up to 2 s) let the panel's 300 ms debounce send a
search for the label's first keys; 66.4 then put the box back (empty, "Type to search"),
and that partial search's late answer painted its results under the empty box. The same
for any two searches whose answers come back in the other order. Now every search is
numbered when it starts (the empty box's own state included) and only the newest paints.

Hermetic, on test_search_panel_scan_66_4.py's page with a fetch that holds each search's
answer, so it runs under --offline. Each case marked RED fails on 41c55db2.
"""
from __future__ import annotations

import pytest

from test_scanner_safe_dialogs_61_js import TYPE_BOX_JS
from test_search_panel_scan_66_4 import MODULES, SEARCH_HTML
from test_wizard_advanced_search_66_8_js import PANEL_PRELUDE

HOLD = r"""
window.__si = window.setInterval; window.setInterval = () => 0;
window.__searches = [];
window.__held = [];
window.fetch = (url) => {
    const u = String(url);
    if (u.startsWith('/api/search')) {
        window.__searches.push(decodeURIComponent(u.replace(/\+/g, ' ')));
        return new Promise((res) => window.__held.push((body) => res({ ok: true, status: 200,
            json: () => Promise.resolve(body) })));
    }
    return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ success: true, materials: [] }) });
};
"""

NONE_FOUND = {"success": True, "results": []}


@pytest.fixture
def held_panel(isolated_page):
    page = isolated_page
    page.set_content('<!doctype html><html><head><meta charset="utf-8"></head><body>'
                     '<div id="toast-container"></div>'
                     + SEARCH_HTML.read_text(encoding="utf-8") + '</body></html>')
    page.add_script_tag(content=PANEL_PRELUDE)
    page.add_script_tag(content=HOLD)
    for name in ("overlay_mount.js", "inv_core.js", "inv_search.js"):
        page.add_script_tag(content=(MODULES / name).read_text(encoding="utf-8"))
    page.evaluate("""() => {
        window.setInterval = window.__si;
        window.__scans = [];
        window.processScan = (t, s) => { window.__scans.push([t, s]); };
        window.SearchEngine.init();
    }""")
    return page


def _results(page):
    return page.locator("#global-search-results").inner_text().strip()


def _answer(page, i, body):
    page.evaluate("([i, b]) => window.__held[i](b)", [i, body])
    page.wait_for_timeout(150)


def test_a_stalled_labels_partial_search_paints_nothing_under_the_emptied_box(held_panel):
    """RED: "ID:" was searched during the stall; the box was put back empty ("Type to
    search"), and that search's late answer painted "No matching spools found." under it."""
    page = held_panel
    page.focus("#global-search-query")
    page.evaluate(TYPE_BOX_JS, [list("ID:"), 5, False, {}])        # the label's first keys
    page.wait_for_timeout(450)                                       # the stall: the debounce runs out
    page.evaluate(TYPE_BOX_JS, [list("57"), 5, True, {"0": 600}])   # the rest after 600 ms, then Enter
    page.wait_for_timeout(450)
    assert page.evaluate("() => window.__scans.map((s) => s[0])") == ["ID:57"]
    assert page.locator("#global-search-query").input_value() == ""
    assert page.evaluate("() => window.__searches.length") == 1      # the partial one, still out
    assert "Type to search" in _results(page)
    _answer(page, 0, NONE_FOUND)
    assert "Type to search" in _results(page)
    assert page.evaluate("() => window.__errors") == []


def test_an_older_answer_landing_last_is_dropped(held_panel):
    """Two searches out, the older answering last: the newest's answer stays. RED: the older
    answer's words ("OLD") replaced it."""
    page = held_panel
    page.fill("#global-search-query", "red")
    page.dispatch_event("#global-search-query", "input")
    page.wait_for_timeout(450)
    page.fill("#global-search-query", "red silk")
    page.dispatch_event("#global-search-query", "input")
    page.wait_for_timeout(450)
    assert page.evaluate("() => window.__searches.length") == 2
    _answer(page, 1, NONE_FOUND)                                     # the newest
    assert "No matching spools found" in _results(page)
    _answer(page, 0, {"success": False, "msg": "OLD"})               # the older, late
    assert "No matching spools found" in _results(page)
    assert "OLD" not in _results(page)


def test_the_newest_answer_paints(held_panel):
    """A pin: one search, answered: it paints, an error too."""
    page = held_panel
    page.fill("#global-search-query", "red")
    page.dispatch_event("#global-search-query", "input")
    page.wait_for_timeout(450)
    _answer(page, 0, {"success": False, "msg": "Spoolman didn't answer"})
    assert "Spoolman didn't answer" in _results(page)
