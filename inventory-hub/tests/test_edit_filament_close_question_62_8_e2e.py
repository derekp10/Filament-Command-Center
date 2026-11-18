"""Group 62.8 (and a finding of 62.4's browser check, 2026-11-17): Edit Filament's
"Close without saving?" keeps the window open until it is answered, on the real dashboard.

Edit Filament's Escape guard drew its question inside the window, and Bootstrap's own
Escape dismiss, registered on the window before the guard, closed the window anyway: the
question sat in a window already gone, and the edits were lost. Its comment said the
guard listened in the capture phase to run first; it didn't. With the keyboard outside a
text box, the location manager's Escape handler also hid the window past the guard (62.4
hands the Escape to the window on top now). The question is a mountOverlay now (62.8),
and the guard runs first.

Read-only: every request that isn't a GET is answered in this browser, the heartbeat is
quieted, and the filament is picked from what dev holds at the time. RED before 62.8 for
the first two (the window closed); the last pins what was right.
"""
from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.usefixtures("require_server")

MODAL = "#editFilamentModal"
QUESTION = "#editfil-esc-confirm"


def _open_dirty(page: Page, base_url: str, dirty: bool = True):
    import conftest   # local: keeps this file's header out of other branches' merges
    from test_text_size_guard import _read_only
    _read_only(page)
    conftest.quiet_heartbeat(page)
    page.goto(base_url, wait_until="domcontentloaded")
    page.wait_for_function("() => typeof window.openEditFilamentForm === 'function' && typeof state !== 'undefined'"
                           " && state.locationsLoaded", timeout=45_000)
    fil = page.evaluate("""async () => {
        const fs = await fetch('/api/filaments').then((r) => r.json()).catch(() => null);
        const list = Array.isArray(fs) ? fs : ((fs && fs.filaments) || []);
        const f = list.find((x) => x && x.id);
        return f ? fetch('/api/filament_details?id=' + f.id).then((r) => r.json()) : null; }""")
    if not fil or not fil.get("id"):
        pytest.skip("dev holds no filament to open")
    page.evaluate("(f) => window.openEditFilamentForm(f)", fil)
    page.wait_for_function("(s) => document.querySelector(s).classList.contains('show')", arg=MODAL, timeout=15_000)
    page.wait_for_timeout(800)
    if dirty:
        page.click("#editfil-name")
        page.keyboard.type(" (edited)")


def test_escape_in_a_dirty_box_asks_and_the_window_stays(page: Page, base_url: str):
    _open_dirty(page, base_url)
    page.keyboard.press("Escape")
    expect(page.locator(QUESTION)).to_be_visible()
    page.wait_for_timeout(500)
    assert page.evaluate("(s) => document.querySelector(s).classList.contains('show')", MODAL), \
        "Edit Filament closed behind its own question"
    page.keyboard.press("Escape")                     # Keep Editing
    expect(page.locator(QUESTION)).to_have_count(0)
    assert page.evaluate("(s) => document.querySelector(s).classList.contains('show')", MODAL)
    assert "(edited)" in page.input_value("#editfil-name")


def test_escape_with_the_keyboard_on_the_page_asks_too_and_close_anyway_closes(page: Page, base_url: str):
    _open_dirty(page, base_url)
    page.evaluate("() => document.activeElement && document.activeElement.blur()")
    page.keyboard.press("Escape")
    expect(page.locator(QUESTION)).to_be_visible()
    page.wait_for_timeout(500)
    assert page.evaluate("(s) => document.querySelector(s).classList.contains('show')", MODAL)
    page.click(f"{QUESTION} #editfil-esc-yes")
    page.wait_for_function("(s) => !document.querySelector(s).classList.contains('show')", arg=MODAL, timeout=5_000)
    expect(page.locator(QUESTION)).to_have_count(0)


def test_escape_on_a_clean_form_closes_it_without_asking(page: Page, base_url: str):
    """A pin."""
    _open_dirty(page, base_url, dirty=False)
    page.click("#editfil-name")
    page.keyboard.press("Escape")
    page.wait_for_function("(s) => !document.querySelector(s).classList.contains('show')", arg=MODAL, timeout=5_000)
    expect(page.locator(QUESTION)).to_have_count(0)
