"""The global search's '/' and Ctrl/Cmd+K open nothing under a window FCC drew over the
page (Group 58 review of 7e3720f, P-2), hermetic.

The REAL fab_drag.js (the two keys), overlay_mount.js, inv_core.js and the REAL scan
accumulator (scripts.html's keydown block, lifted as it is), in `isolated_page` (a
chromium with no route to any network) through test_slow_scan_slash_js's `scan_page`, so
it runs under --offline. The keys are typed on its fake clock.

The defect: the search is a Bootstrap offcanvas (z 1045). Opened with a mountOverlay up
(z 20000 and over: the audit's 🧺 list, Done's question, the legacy picker, Find under
the ⌨️ shortcut list), it opened behind it, and its box took the keyboard 400 ms later,
so the next scan was typed into a box nobody could see. The real dashboard's cases are
in test_audit_find_and_tiles_58_e2e.py. RED on e7886e9 unless a test says it pins what
was already right.
"""
from __future__ import annotations

import pytest

from test_slow_scan_slash_js import _later, _seen, _type, scan_page  # noqa: F401  (scan_page: the fixture)

# An overlay mounted as every FCC window over the page is, with a button holding the
# keyboard, as on the audit's 🧺 list or Done's question.
MOUNT = """() => {
    window.__probe = window.mountOverlay({ id: 'fcc-probe-overlay', tier: 'confirm',
        content: '<div><button type="button" id="probe-inside">Back</button><input id="probe-field"></div>' });
    document.getElementById('probe-inside').focus();
}"""
SHORTCUT_LIST = """() => {
    const list = document.createElement('div');
    list.id = 'fcc-shortcuts-overlay';
    list.style.display = 'block';
    list.innerHTML = '<button type="button" class="btn-close" id="probe-list-close">x</button>';
    document.body.appendChild(list);
    document.getElementById('probe-list-close').focus();
}"""
CTRL_K = """() => {
    const t = document.activeElement || document.body;
    const e = new KeyboardEvent('keydown', { key: 'k', ctrlKey: true, bubbles: true, cancelable: true });
    t.dispatchEvent(e);
    return e.defaultPrevented;
}"""


def _fresh(page):
    page.evaluate("() => { window.clearScanBuffer(); window.__search = 0; window.__scans = []; }")
    _later(page, 3000)


@pytest.mark.parametrize("cover", ["an-overlay", "the-shortcut-list"])
def test_a_persons_slash_under_a_window_opens_nothing_and_joins_no_scan(scan_page, cover):
    """A person's '/' is taken (out of the scan buffer too, or it would start the next
    scan as "/ID:99") and opens nothing; the scan after it arrives whole. RED on e7886e9:
    the search opened (behind the window, on the dashboard)."""
    page = scan_page
    page.evaluate(MOUNT if cover == "an-overlay" else SHORTCUT_LIST)
    _fresh(page)
    _type(page, "/", 10, enter=False)
    s = _seen(page)
    assert s["search"] == 0 and s["buffer"] == "", s
    _later(page, 600)
    _type(page, "ID:99", 13)
    assert _seen(page)["scans"] == ["ID:99"]


def test_ctrl_k_under_a_window_opens_nothing(scan_page):
    """RED on e7886e9: Ctrl/Cmd+K opened the search behind the window."""
    page = scan_page
    page.evaluate(MOUNT)
    _fresh(page)
    assert page.evaluate(CTRL_K) is True             # the browser's own Ctrl+K still goes nowhere
    assert _seen(page)["search"] == 0


def test_with_nothing_over_the_page_both_keys_still_open_the_search(scan_page):
    """Pins what was already right, and the window closed again: a hidden audit panel
    mounts nothing, so '/' still opens the search there, as Hide means."""
    page = scan_page
    page.evaluate(MOUNT)
    page.evaluate("() => window.__probe.cleanup()")
    _fresh(page)
    _type(page, "/", 10, enter=False)
    assert _seen(page)["search"] == 1 and _seen(page)["buffer"] == ""
    page.evaluate(CTRL_K)
    assert _seen(page)["search"] == 2


def test_a_slash_typed_in_a_field_and_a_scans_slash_under_a_window_go_on(scan_page):
    """Pins what was already right: a '/' typed in a field is the field's (nothing takes
    it), and a scan's '/' under a window is the scan's (a Prusament URL), whole."""
    page = scan_page
    page.evaluate(MOUNT)
    _fresh(page)
    taken = page.evaluate("""() => { const f = document.getElementById('probe-field'); f.focus();
        const e = new KeyboardEvent('keydown', { key: '/', bubbles: true, cancelable: true });
        f.dispatchEvent(e); return e.defaultPrevented; }""")
    assert taken is False and _seen(page)["search"] == 0
    page.evaluate("() => document.getElementById('probe-inside').focus()")
    _fresh(page)
    url = "https://prusament.com/spool/17705/5b1a183b26/"
    _type(page, url, 13)
    assert _seen(page)["scans"] == [url] and _seen(page)["search"] == 0
