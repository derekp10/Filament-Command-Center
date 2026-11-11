"""In-app help (Group 55.3), in a browser on dev.

A dialog's ? button opens its help in the shortcut window, above the dialog; Escape
closes only the help; the help closes with its dialog; the ? key opens the help of the
dialog on top (again: every shortcut; again: closed), and with no dialog open the full
list, as before; a double click on the ? button leaves the help up; a scan that starts
with '?' opens nothing. The scanner case with no dialog open is
test_quickswap_ui_e2e.py's test_shortcuts_overlay_question_mark_at_start_of_scan_does_not_trigger.

Read-only on dev: it opens the dashboard and a location's window, and reads.
"""
from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.usefixtures("require_server")

OVERLAY = "#fcc-shortcuts-overlay"
BACKDROP = "#fcc-shortcuts-overlay-backdrop"
HELP = "#fcc-help-view"
LIST = "#fcc-shortcuts-list"
TITLE = "#fcc-shortcuts-title"
WINDOW_HELP = '#manageModal [data-fcc-help="location-window"]'


def _open_a_location(page: Page, base_url: str) -> str:
    """Open the location window of a place in dev's list (a dryer box when there is one)."""
    page.goto(base_url)
    page.wait_for_selector("#command-buffer, #buffer-zone", timeout=10000)
    page.wait_for_function(
        "() => typeof state === 'object' && Array.isArray(state.allLocations) && state.allLocations.length > 0",
        timeout=10000)
    loc = page.evaluate("""() => {
        const rows = state.allLocations || [];
        const pick = rows.find((r) => r.Type === 'Dryer Box') || rows[0];
        return pick && pick.LocationID;
    }""")
    assert loc, "dev has no locations"
    page.evaluate("(id) => window.openManage(id)", loc)
    expect(page.locator("#manageModal")).to_be_visible(timeout=8000)
    page.wait_for_function(
        "() => { const m = bootstrap.Modal.getInstance(document.getElementById('manageModal'));"
        " return !!m && !m._isTransitioning; }", timeout=5000)
    return loc


def _press_question_mark(page: Page) -> None:
    """A person's '?': nothing follows it, so the 120 ms defer runs out."""
    page.evaluate("() => { if (document.activeElement && document.activeElement.blur) document.activeElement.blur(); }")
    page.keyboard.press("?")


def test_the_help_button_opens_the_windows_help_above_it(page: Page, base_url: str):
    _open_a_location(page, base_url)
    page.locator(WINDOW_HELP).click()
    expect(page.locator(OVERLAY)).to_be_visible()
    expect(page.locator(HELP)).to_be_visible()
    expect(page.locator(LIST)).to_be_hidden()
    title = page.evaluate("() => window.fccHelpFor('location-window').title")
    expect(page.locator(TITLE)).to_have_text("❓ " + title)
    # Above the window: the overlay's middle is the overlay, not the dialog under it.
    on_top = page.evaluate("""() => {
        const ov = document.getElementById('fcc-shortcuts-overlay');
        const r = ov.getBoundingClientRect();
        const hit = document.elementFromPoint(r.left + r.width / 2, r.top + 24);
        return ov.contains(hit);
    }""")
    assert on_top, "the help is drawn under its window"
    # Its words are the entry's lines, escaped as text.
    first = page.evaluate("() => window.fccHelpFor('location-window').lines[0]")
    expect(page.locator(f"{HELP} .fcc-help-lines li").first).to_have_text(first)


def test_escape_closes_only_the_help(page: Page, base_url: str):
    _open_a_location(page, base_url)
    page.locator(WINDOW_HELP).click()
    expect(page.locator(OVERLAY)).to_be_visible()
    page.keyboard.press("Escape")
    expect(page.locator(OVERLAY)).to_be_hidden()
    expect(page.locator(BACKDROP)).to_be_hidden()
    page.wait_for_timeout(400)
    expect(page.locator("#manageModal")).to_be_visible()


def test_the_help_closes_with_its_window(page: Page, base_url: str):
    """A scan goes on under the help (CMD:DONE closes the window): the help goes with it."""
    _open_a_location(page, base_url)
    page.locator(WINDOW_HELP).click()
    expect(page.locator(OVERLAY)).to_be_visible()
    page.evaluate("() => window.closeManage()")
    expect(page.locator("#manageModal")).to_be_hidden(timeout=5000)
    expect(page.locator(OVERLAY)).to_be_hidden(timeout=3000)
    assert not page.evaluate("() => document.body.classList.contains('fcc-shortcuts-up')")


def test_question_mark_in_the_window_shows_its_help_then_every_shortcut_then_closes(page: Page, base_url: str):
    _open_a_location(page, base_url)
    assert page.evaluate("() => window.fccHelpContextKey()") == "location-window"
    _press_question_mark(page)
    expect(page.locator(OVERLAY)).to_be_visible()
    expect(page.locator(HELP)).to_be_visible()
    expect(page.locator(LIST)).to_be_hidden()
    page.keyboard.press("?")
    expect(page.locator(LIST)).to_be_visible()
    expect(page.locator(f"{HELP} [data-fcc-help-back]")).to_be_visible()
    page.keyboard.press("?")
    expect(page.locator(OVERLAY)).to_be_hidden()
    expect(page.locator("#manageModal")).to_be_visible()


def test_all_shortcuts_and_back(page: Page, base_url: str):
    _open_a_location(page, base_url)
    page.locator(WINDOW_HELP).click()
    page.locator(f"{HELP} [data-fcc-help-all]").click()
    expect(page.locator(LIST)).to_be_visible()
    expect(page.locator(TITLE)).to_contain_text("Keyboard")
    page.locator(f"{HELP} [data-fcc-help-back]").click()
    expect(page.locator(LIST)).to_be_hidden()
    expect(page.locator(f"{HELP} .fcc-help-lines").first).to_be_visible()


def test_question_mark_with_nothing_open_shows_every_shortcut(page: Page, base_url: str):
    page.goto(base_url)
    page.wait_for_selector("#btn-shortcuts-help", timeout=10000)
    assert page.evaluate("() => window.fccHelpContextKey()") is None
    _press_question_mark(page)
    expect(page.locator(OVERLAY)).to_be_visible()
    expect(page.locator(LIST)).to_be_visible()
    expect(page.locator(HELP)).to_be_hidden()
    expect(page.locator(TITLE)).to_contain_text("Keyboard")


def test_a_double_click_on_the_help_button_leaves_the_help_up(page: Page, base_url: str):
    """The second press lands on the backdrop where the button was: it must not close it."""
    _open_a_location(page, base_url)
    page.locator(WINDOW_HELP).dblclick()
    page.wait_for_timeout(800)
    expect(page.locator(OVERLAY)).to_be_visible()
    # A press on the backdrop later, elsewhere, still closes it.
    page.locator(BACKDROP).click(position={"x": 10, "y": 10})
    expect(page.locator(OVERLAY)).to_be_hidden()


def test_a_scan_starting_with_a_question_mark_in_the_window_opens_nothing(page: Page, base_url: str):
    """A legacy label can start with '?': the rest of the burst arrives inside the 120 ms."""
    _open_a_location(page, base_url)
    page.evaluate("""() => {
        if (document.activeElement && document.activeElement.blur) document.activeElement.blur();
        const fire = (k) => document.dispatchEvent(new KeyboardEvent('keydown', {key: k, bubbles: true}));
        fire('?'); fire('i'); fire('d'); fire('='); fire('4'); fire('2');
    }""")
    page.wait_for_timeout(400)
    expect(page.locator(OVERLAY)).to_be_hidden()
