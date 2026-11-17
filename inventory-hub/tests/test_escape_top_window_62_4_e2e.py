"""Group 62.4 (from Group 73's task file, 2026-11-17): an Escape reaches only the window
on top.

The location manager's Escape handler listens on the document in the capture phase, so
it hears an Escape before any window does. With a place's window (the Location Manager)
open anywhere underneath, it closed or stepped back that window, while the window on
top (a spool's window, a filament's, Edit Filament, the QR view) stayed open; with no
place's window, it hid the top window itself, past that window's own Escape code (Edit
Filament's "Close without saving?" among it). Checked in a browser on 2026-11-17 before
the fix: a spool window over LR-MDB-1's window, the focus on the page or inside the spool
window, and Escape closed LR-MDB-1's window.

Now the place's window takes an Escape only when it is on top; any other window on top
answers its own (with the focus on the page, the Escape is handed to it).

On the real dashboard, read-only: every write is answered in the browser
(test_text_size_guard._read_only), the heartbeat quieted, and the place and the spool
picked from what dev holds at the time (never a fixed id). RED on 697bc4f for the first
two; the third pins what was right.
"""
from __future__ import annotations

import pytest
from playwright.sync_api import Page

PICK = """async () => {
    const rows = (state.allLocations || []).filter((l) => l && l.LocationID && l.Type === 'Dryer Box');
    for (const r of rows) {
        const items = await fetch('/api/get_contents?id=' + encodeURIComponent(r.LocationID)).then((x) => x.json());
        const s = (Array.isArray(items) ? items : []).find((i) => i && i.id);
        if (s) return { box: r.LocationID, sid: s.id };
    }
    return null;
}"""


def _shown(page: Page):
    return page.evaluate("() => Array.from(document.querySelectorAll('.modal.show')).map((m) => m.id).sort()")


def _ready(page: Page, base_url: str):
    import conftest   # local: keeps this file's header out of other branches' merges
    from test_text_size_guard import _read_only
    _read_only(page)
    conftest.quiet_heartbeat(page)
    page.goto(base_url, wait_until="domcontentloaded")
    page.wait_for_function("() => typeof window.openManage === 'function' && typeof openSpoolDetails === 'function'"
                           " && typeof state !== 'undefined' && state.locationsLoaded", timeout=45_000)
    pick = page.evaluate(PICK)
    if not pick:
        pytest.skip("dev holds no Dryer Box with a spool in it to open")
    return pick


def _place_window(page: Page, box: str):
    page.evaluate("(id) => window.openManage(id)", box)
    page.wait_for_function("() => document.getElementById('manageModal').classList.contains('show')", timeout=15_000)
    page.wait_for_timeout(600)


def _spool_window(page: Page, sid):
    page.evaluate("(id) => openSpoolDetails(id)", sid)
    page.wait_for_function("() => document.getElementById('spoolModal').classList.contains('show')", timeout=15_000)
    page.wait_for_timeout(600)


@pytest.mark.usefixtures("require_server")
@pytest.mark.parametrize("focus", ["page", "spool-window"])
def test_escape_with_a_spool_window_over_a_place_window_closes_only_the_spool_window(page: Page, base_url: str, focus):
    pick = _ready(page, base_url)
    _place_window(page, pick["box"])
    _spool_window(page, pick["sid"])
    assert _shown(page) == ["manageModal", "spoolModal"]
    if focus == "page":
        page.evaluate("() => document.activeElement && document.activeElement.blur()")
    else:
        page.evaluate("() => { const m = document.getElementById('spoolModal'); m.focus(); }")
        assert page.evaluate("() => document.getElementById('spoolModal').contains(document.activeElement)")
    page.keyboard.press("Escape")
    page.wait_for_function("() => !document.getElementById('spoolModal').classList.contains('show')", timeout=5_000)
    page.wait_for_timeout(400)
    assert _shown(page) == ["manageModal"], "the place's window under the spool window answered the Escape"


@pytest.mark.usefixtures("require_server")
def test_escape_with_only_a_place_window_still_closes_it(page: Page, base_url: str):
    """A pin: the place's window on top still takes its Escape (closeManage)."""
    pick = _ready(page, base_url)
    _place_window(page, pick["box"])
    page.evaluate("() => document.activeElement && document.activeElement.blur()")
    page.keyboard.press("Escape")
    page.wait_for_function("() => !document.getElementById('manageModal').classList.contains('show')", timeout=5_000)
