"""In-app help (Group 55.3), in a browser on dev.

A dialog's ? button opens its help in the shortcut window, above the dialog; Escape
closes only the help; the help closes with its dialog; the ? key opens the help of the
dialog on top (again: every shortcut; again: closed), and with no dialog open the full
list, as before; a double click on the ? button leaves the help up; a scan that starts
with '?' opens nothing. The scanner case with no dialog open is
test_quickswap_ui_e2e.py's test_shortcuts_overlay_question_mark_at_start_of_scan_does_not_trigger.

Every covered dialog has its ? (each window's header, the Quick-Weigh, the move
question, both pickers), and a click on it leaves the keyboard where it was, so Escape
gives it back there; a ? reached by Tab gets it back.

Read-only on dev: it opens the dashboard and the dialogs, and reads; a write a dialog
could send is answered in the browser.
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


# --- the help has the keyboard while it is up (the Group 55 map's findings) ----------------

_ACTIVE_JS = """() => { const a = document.activeElement;
    return a ? (a.id || a.className || a.tagName) : null; }"""


def test_the_help_takes_the_keyboard_and_gives_it_back(page: Page, base_url: str):
    """It opens with the focus on itself (a person's keys landed on the window under it,
    where Bootstrap's focus trap also pulled a click on the help's own buttons back), Tab
    stays among its own buttons, and Escape gives the keyboard back to what had it before
    the press: a click on the ? never takes the keyboard (on a question, a person's next
    Enter opened the help again while its hint said "Enter stores it"), and a ? reached
    by Tab gets it back."""
    _open_a_location(page, base_url)
    before = page.evaluate(_ACTIVE_JS)
    page.locator(WINDOW_HELP).click()
    expect(page.locator(OVERLAY)).to_be_visible()
    assert page.evaluate("() => document.activeElement && document.activeElement.id") == "fcc-shortcuts-overlay"
    for _ in range(4):
        page.keyboard.press("Tab")
        assert page.evaluate("() => document.getElementById('fcc-shortcuts-overlay').contains(document.activeElement)")
    # A click on its own All shortcuts keeps the keyboard in it (no window pulls it back).
    page.locator(f"{HELP} [data-fcc-help-all]").click()
    assert page.evaluate("() => document.getElementById('fcc-shortcuts-overlay').contains(document.activeElement)")
    page.keyboard.press("Escape")
    expect(page.locator(OVERLAY)).to_be_hidden()
    assert page.evaluate(_ACTIVE_JS) == before, "the keyboard didn't go back to what had it before the click"
    assert not page.evaluate("() => !!document.activeElement.closest('[data-fcc-help]')")
    # By the keyboard: the ? reached by Tab, Enter opens the help, Escape gives it back.
    page.locator(WINDOW_HELP).focus()
    page.keyboard.press("Enter")
    expect(page.locator(OVERLAY)).to_be_visible()
    page.keyboard.press("Escape")
    expect(page.locator(OVERLAY)).to_be_hidden()
    assert page.evaluate("() => !!document.activeElement.closest('[data-fcc-help]')"), \
        "the keyboard didn't go back to the ? button it came from"


# Every daily window with a ? in its header (Group 55.3): its id, its help key, and how the
# page opens it. Read-only: each one reads, and the spool and filament windows show the
# first spool or filament dev's search finds.
WINDOWS = [
    ("locMgrModal", "location-list", "() => { window.openLocationsModal(); }"),
    ("spoolModal", "spool-window",
     "async () => { const r = await (await fetch('/api/search?q=a&type=spool')).json();"
     " const s = (r.results || [])[0]; if (!s) return false; openSpoolDetails(s.id); return true; }"),
    ("filamentModal", "filament-window",
     "async () => { const r = await (await fetch('/api/search?q=a&type=filament')).json();"
     " const f = (r.results || [])[0]; if (!f) return false; openFilamentDetails(f.id); return true; }"),
    ("wizardModal", "wizard", "() => { window.openWizardModal(); }"),
    ("weighOutModal", "weigh-out",
     "() => { bootstrap.Modal.getOrCreateInstance(document.getElementById('weighOutModal')).show(); }"),
    ("queueModal", "print-queue", "() => { window.openQueueModal(); }"),
    ("backlogModal", "label-backlog", "() => { window.openBacklogModal(); }"),
]


@pytest.mark.parametrize("modal_id, key, opener", WINDOWS, ids=[w[0] for w in WINDOWS])
def test_each_windows_help_button_opens_its_help(page: Page, base_url: str, modal_id, key, opener):
    """The ? sits in the window's header just left of its ✕, on the ✕'s line; a click opens
    that window's help above it; Escape closes only the help and gives the keyboard back
    to what had it; the window stays open."""
    from test_text_size_guard import _read_only
    _read_only(page)
    page.goto(base_url)
    page.wait_for_function(
        "() => typeof state === 'object' && typeof bootstrap !== 'undefined' && typeof window.openHelp === 'function'",
        timeout=15000)
    if page.evaluate(opener) is False:
        pytest.skip(f"dev's search found nothing to show in #{modal_id}")
    modal = page.locator(f"#{modal_id}")
    expect(modal).to_be_visible(timeout=10000)
    page.wait_for_function(
        "(id) => { const m = bootstrap.Modal.getInstance(document.getElementById(id)); return !!m && !m._isTransitioning; }",
        arg=modal_id, timeout=8000)
    btn = modal.locator(f'.modal-header [data-fcc-help="{key}"]')
    expect(btn).to_be_visible()
    geo = page.evaluate("""(id) => {
        const head = document.querySelector('#' + id + ' .modal-header');
        const q = head.querySelector('[data-fcc-help]').getBoundingClientRect();
        const x = head.querySelector('.btn-close').getBoundingClientRect();
        return { gap: x.left - q.right, dy: Math.abs((q.top + q.bottom) / 2 - (x.top + x.bottom) / 2) };
    }""", modal_id)
    assert 0 <= geo["gap"] <= 24 and geo["dy"] <= 12, f"the ? isn't beside the ✕: {geo}"
    before = page.evaluate(_ACTIVE_JS)
    btn.click()
    expect(page.locator(OVERLAY)).to_be_visible()
    title = page.evaluate("(k) => window.fccHelpFor(k).title", key)
    expect(page.locator(TITLE)).to_have_text("❓ " + title)
    first = page.evaluate("(k) => window.fccHelpFor(k).lines[0]", key)
    expect(page.locator(f"{HELP} .fcc-help-lines li").first).to_have_text(first)
    page.keyboard.press("Escape")
    expect(page.locator(OVERLAY)).to_be_hidden()
    page.wait_for_timeout(300)
    expect(modal).to_be_visible()
    assert page.evaluate(_ACTIVE_JS) == before


def test_the_wizard_opens_with_the_keyboard_on_its_close_button(page: Page, base_url: str):
    """The ? sits before the ✕ in the wizard's header; the ✕ keeps the first focus it had."""
    from test_text_size_guard import _read_only
    _read_only(page)
    page.goto(base_url)
    page.wait_for_function("() => typeof window.openWizardModal === 'function'", timeout=15000)
    page.evaluate("() => { window.openWizardModal(); }")
    expect(page.locator("#wizardModal")).to_be_visible(timeout=10000)
    page.wait_for_function(
        "() => document.activeElement && document.activeElement.closest && !!document.activeElement.closest('#wizardModal .modal-header')",
        timeout=8000)
    assert page.evaluate("() => document.activeElement.classList.contains('btn-close')")


def test_q_under_the_help_moves_nothing(page: Page, base_url: str):
    """A toolhead's window: Q moves the keyboard into the Quick-Swap grid, but not under the help."""
    page.goto(base_url)
    page.wait_for_function(
        "() => typeof state === 'object' && Array.isArray(state.allLocations) && state.allLocations.length > 0",
        timeout=10000)
    # A toolhead a dryer box slot feeds, so its Quick-Swap grid has tiles.
    head = page.evaluate("""() => {
        for (const r of state.allLocations) {
            const t = (r && r.extra && r.extra.slot_targets) || {};
            for (const v of Object.values(t)) {
                const h = state.allLocations.find((x) => x.LocationID === v);
                if (h && window.isToolheadType(h.Type)) return h.LocationID;
            }
        }
        return null;
    }""")
    if not head:
        pytest.skip("no dryer box slot on dev feeds a toolhead")
    page.evaluate("(id) => window.openManage(id)", head)
    expect(page.locator("#manageModal")).to_be_visible(timeout=8000)
    page.wait_for_function("() => document.querySelectorAll('#quickswap-grid .fcc-qs-slot').length > 0", timeout=10000)
    page.locator(WINDOW_HELP).click()
    expect(page.locator(OVERLAY)).to_be_visible()
    page.keyboard.press("q")
    page.wait_for_timeout(300)
    assert page.evaluate("() => document.getElementById('fcc-shortcuts-overlay').contains(document.activeElement)")
    assert page.evaluate("() => !document.querySelector('#quickswap-grid .fcc-qs-slot.kb-active')")
    # The help for a toolhead's window shows its Quick-Swap part and keys.
    expect(page.locator(f"{HELP} .fcc-help-sub")).to_contain_text("Quick-Swap")


def test_the_help_closes_when_another_window_opens_over_its_window(page: Page, base_url: str):
    """A scan goes on under the help: a place's window it opens over the Location List was
    drawn under the help, unseen. The help goes, and the new window shows."""
    page.goto(base_url)
    page.wait_for_function(
        "() => typeof state === 'object' && Array.isArray(state.allLocations) && state.allLocations.length > 0",
        timeout=10000)
    page.evaluate("() => window.openLocationsModal()")
    expect(page.locator("#locMgrModal")).to_be_visible(timeout=8000)
    page.wait_for_function(
        "() => { const m = bootstrap.Modal.getInstance(document.getElementById('locMgrModal')); return !!m && !m._isTransitioning; }")
    page.evaluate("() => window.openHelp('location-list', { el: document.getElementById('locMgrModal') })")
    expect(page.locator(OVERLAY)).to_be_visible()
    loc = page.evaluate("() => state.allLocations[0].LocationID")
    page.evaluate("(id) => window.openManage(id)", loc)
    expect(page.locator(OVERLAY)).to_be_hidden(timeout=5000)
    expect(page.locator("#manageModal")).to_be_visible(timeout=8000)


def test_enter_and_keys_under_the_help_never_reach_the_quick_weigh(page: Page, base_url: str):
    """The Quick-Weigh saved on any Enter that wasn't on its own buttons, D set its default
    and an arrow switched its mode. With its help up, none of them reach it. The spool is
    made up, and every write is answered in the browser."""
    saves = []
    spool = {"id": 9055, "initial_weight": 1000, "used_weight": 200, "spool_weight": 200, "archived": False,
             "filament": {"id": 9056, "name": "Help Test", "material": "PLA", "weight": 1000,
                          "spool_weight": 200, "color_hex": "336699", "vendor": {"id": 9057, "name": "Example"}}}

    def details(route):
        route.fulfill(status=200, content_type="application/json", body=__import__("json").dumps(spool))

    def write(route):
        if route.request.method != "GET":
            saves.append(route.request.url)
            route.fulfill(status=200, content_type="application/json", body='{"success": false}')
        else:
            route.continue_()

    page.route("**/api/spool_details*", details)
    page.route("**/api/spool/update*", write)
    page.goto(base_url)
    page.wait_for_function("() => typeof window.openQuickWeigh === 'function' && typeof state === 'object'")
    page.evaluate("() => window.openQuickWeigh(9055)")
    page.wait_for_selector("#fcc-weight-entry-overlay #fcc-we-auto-archive", timeout=10000)
    page.locator("#fcc-we-input").fill("500")
    assert page.evaluate("() => window.fccHelpContextKey()") == "quick-weigh"
    page.evaluate("() => window.openHelp('quick-weigh')")
    expect(page.locator(OVERLAY)).to_be_visible()
    mode_before = page.evaluate("() => (document.querySelector('#fcc-we-tabs .fcc-we-tab.btn-info') || {}).dataset?.mode || ''")
    page.keyboard.press("ArrowRight")
    page.keyboard.press("d")
    page.wait_for_timeout(200)
    page.keyboard.press("Enter")
    page.wait_for_timeout(600)
    assert saves == [], f"a key under the help saved the Quick-Weigh: {saves}"
    mode_after = page.evaluate("() => (document.querySelector('#fcc-we-tabs .fcc-we-tab.btn-info') || {}).dataset?.mode || ''")
    assert mode_after == mode_before
    page.keyboard.press("Escape")
    expect(page.locator(OVERLAY)).to_be_hidden()
    expect(page.locator("#fcc-weight-entry-overlay")).to_be_visible()


def test_the_wizards_weigh_from_scale_is_not_the_quick_weigh(page: Page, base_url: str):
    """The same window draws both; only the Quick-Weigh has the Auto Archive switch."""
    page.goto(base_url)
    page.wait_for_function("() => typeof window.WeightEntry === 'object' && typeof window.openHelp === 'function'")
    page.evaluate("""() => window.WeightEntry.openModal({ title: 'Weigh from Scale',
        spool: { id: null, initial_weight: 1000, used_weight: 0, display: 'New spool' },
        empty_spool_weight: 200, showAutoArchive: false, onSubmit: () => {} })""")
    page.wait_for_selector("#fcc-weight-entry-overlay", timeout=5000)
    assert page.evaluate("() => !!document.querySelector('#fcc-weight-entry-overlay #fcc-we-auto-archive')") is False
    assert page.evaluate("() => window.fccHelpContextKey()") is None
    # No ? either: its caller names no help.
    expect(page.locator("#fcc-weight-entry-overlay [data-fcc-help]")).to_have_count(0)


def test_the_quick_weighs_help_button_leaves_the_keyboard_in_its_field(page: Page, base_url: str):
    """The Quick-Weigh's ? sits beside its ×. A click opens its help, and Escape gives the
    keyboard back to the weight box, where Enter saves: the reading typed before the click
    is still there. The spool is made up, and every write is answered in the browser."""
    import json as _json
    saves = []
    spool = {"id": 9058, "initial_weight": 1000, "used_weight": 200, "spool_weight": 200, "archived": False,
             "filament": {"id": 9059, "name": "Help Test", "material": "PLA", "weight": 1000,
                          "spool_weight": 200, "color_hex": "336699", "vendor": {"id": 9060, "name": "Example"}}}

    def details(route):
        route.fulfill(status=200, content_type="application/json", body=_json.dumps(spool))

    def write(route):
        if route.request.method != "GET":
            saves.append(route.request.post_data_json)
            route.fulfill(status=200, content_type="application/json", body='{"success": false, "msg": "not saved"}')
        else:
            route.continue_()

    page.route("**/api/spool_details*", details)
    page.route("**/api/spool/update*", write)
    page.goto(base_url)
    page.wait_for_function("() => typeof window.openQuickWeigh === 'function' && typeof state === 'object'")
    page.evaluate("() => window.openQuickWeigh(9058)")
    overlay = page.locator("#fcc-weight-entry-overlay")
    page.wait_for_selector("#fcc-weight-entry-overlay #fcc-we-auto-archive", timeout=10000)
    btn = overlay.locator('[data-fcc-help="quick-weigh"]')
    expect(btn).to_be_visible()
    geo = page.evaluate("""() => {
        const o = document.getElementById('fcc-weight-entry-overlay');
        const q = o.querySelector('[data-fcc-help]').getBoundingClientRect();
        const x = o.querySelector('#fcc-we-close').getBoundingClientRect();
        return { gap: x.left - q.right, dy: Math.abs((q.top + q.bottom) / 2 - (x.top + x.bottom) / 2) };
    }""")
    assert 0 <= geo["gap"] <= 24 and geo["dy"] <= 12, f"the ? isn't beside the ×: {geo}"
    page.wait_for_function("() => document.activeElement && document.activeElement.id === 'fcc-we-input'")
    page.locator("#fcc-we-input").fill("500")
    btn.click()
    expect(page.locator(OVERLAY)).to_be_visible()
    expect(page.locator(TITLE)).to_have_text("❓ " + page.evaluate("() => window.fccHelpFor('quick-weigh').title"))
    page.keyboard.press("Escape")
    expect(page.locator(OVERLAY)).to_be_hidden()
    expect(overlay).to_be_visible()
    assert page.evaluate("() => document.activeElement && document.activeElement.id") == "fcc-we-input"
    assert page.locator("#fcc-we-input").input_value() == "500"
    assert saves == []
    page.keyboard.press("Enter")
    page.wait_for_function("() => !document.getElementById('fcc-weight-entry-overlay')", timeout=5000)
    assert len(saves) == 1 and saves[0]["id"] == 9058, saves


QUESTION = "#fcc-active-print-confirm-overlay"
THREE_WAY_JS = """(ids) => { window.__answer = null;
    window.confirmActivePrint({ title: 'Load #42 onto HEAD-1?',
        msg: 'DRYBOX-1 slot 2 feeds HEAD-1, and HEAD-1 is running #7 (from DRYBOX-2).',
        printing: false, loadLabel: 'Load it instead', storeLabel: 'Just store it in DRYBOX-1 slot 2', ids: ids || {},
        onConfirm: () => { window.__answer = 'load'; }, onStore: () => { window.__answer = 'store'; },
        onCancel: () => { window.__answer = 'cancel'; } }); }"""


def test_the_move_questions_help_button(page: Page, base_url: str):
    """The move question (window.confirmActivePrint, as the move doors show it) has a ? in
    its top right corner, clear of its title, whose words are as they were. A click opens
    its help and leaves the keyboard on Just store it, so after Escape a person's Enter
    stores, as the hint says. Enter on the ? itself opens the help and answers nothing.
    Nothing is sent: the answers are local."""
    page.goto(base_url)
    page.wait_for_function(
        "() => typeof window.confirmActivePrint === 'function' && typeof window.fccHelpKeyForOverlayId === 'function'")
    page.evaluate(THREE_WAY_JS)
    q = page.locator(QUESTION)
    btn = q.locator('[data-fcc-help="move-question"]')
    expect(btn).to_be_visible()
    expect(q.locator(".fcc-apc-title")).to_have_text("🔁 Load #42 onto HEAD-1?")
    geo = page.evaluate("""(sel) => {
        const o = document.querySelector(sel);
        const panel = o.querySelector('.fcc-apc-panel').getBoundingClientRect();
        const b = o.querySelector('.fcc-apc-help').getBoundingClientRect();
        const t = o.querySelector('.fcc-apc-title');
        const r = document.createRange(); r.selectNodeContents(t);
        const words = r.getBoundingClientRect();
        const tb = t.getBoundingClientRect();
        return { right: panel.right - b.right, top: b.top - panel.top, overlap: words.right > b.left && words.top < b.bottom,
                 centred: Math.abs((words.left + words.right) / 2 - (tb.left + tb.right) / 2) };
    }""", QUESTION)
    assert geo["right"] <= 16 and geo["top"] <= 16, f"the ? isn't in the top right corner: {geo}"
    assert not geo["overlap"], f"the title's words run under the ?: {geo}"
    assert geo["centred"] <= 2, f"the title isn't centred: {geo}"
    page.wait_for_function("() => document.activeElement && document.activeElement.classList.contains('fcc-apc-store')")
    btn.click()
    expect(page.locator(OVERLAY)).to_be_visible()
    expect(page.locator(TITLE)).to_have_text("❓ " + page.evaluate("() => window.fccHelpFor('move-question').title"))
    page.keyboard.press("Escape")
    expect(page.locator(OVERLAY)).to_be_hidden()
    expect(q).to_be_visible()
    assert page.evaluate("() => window.__answer") is None
    assert page.evaluate("() => document.activeElement.classList.contains('fcc-apc-store')")
    # Enter on the ? opens the help; it never stores or cancels.
    btn.focus()
    page.keyboard.press("Enter")
    expect(page.locator(OVERLAY)).to_be_visible()
    page.wait_for_timeout(200)
    assert page.evaluate("() => window.__answer") is None
    page.keyboard.press("Escape")
    expect(page.locator(OVERLAY)).to_be_hidden()
    expect(q).to_be_visible()
    page.evaluate("(sel) => document.querySelector(sel + ' .fcc-apc-store').focus()", QUESTION)
    page.keyboard.press("Enter")
    page.wait_for_function("() => window.__answer === 'store'")


def test_only_questions_with_help_draw_a_help_button(page: Page, base_url: str):
    """The ? shows where the ? key gives help: the scan door's question (the move
    question's help) and the Printer picker's toolhead question (the picker's). Done's
    question has no help, so no ?, and nothing it draws moves."""
    page.goto(base_url)
    page.wait_for_function(
        "() => typeof window.confirmActivePrint === 'function' && typeof window.fccHelpKeyForOverlayId === 'function'")
    for overlay_id, key in (("fcc-active-print-scan-overlay", "move-question"),
                            ("fcc-head-pick-confirm", "printer-picker"),
                            ("fcc-audit-done-question", None)):
        page.evaluate(THREE_WAY_JS, {"overlay": overlay_id})
        q = page.locator(f"#{overlay_id}")
        expect(q).to_be_visible()
        if key:
            expect(q.locator(f'[data-fcc-help="{key}"]')).to_be_visible()
            assert page.evaluate("() => window.fccHelpContextKey()") == key
        else:
            expect(q.locator("[data-fcc-help]")).to_have_count(0)
            assert page.evaluate("(id) => getComputedStyle(document.querySelector('#' + id + ' .fcc-apc-title')).paddingLeft",
                                 overlay_id) == "0px"
        page.keyboard.press("Escape")
        expect(q).to_have_count(0)
        assert page.evaluate("() => window.__answer") == "cancel"


@pytest.mark.parametrize("kind, key", [("box", "slot-picker"), ("printer", "printer-picker")])
def test_each_picker_gets_its_own_help(page: Page, base_url: str, kind, key):
    """The box picker and the Printer picker are one window, and its loading view draws no
    mode: the picker marks its root with its mode from the start (data-fcc-picker-mode), so
    ? opens the right help at once and once the slots are drawn. Read-only: the picker
    reads its places and is cancelled."""
    page.goto(base_url)
    page.wait_for_function(
        "() => typeof state === 'object' && Array.isArray(state.allLocations) && state.allLocations.length > 0",
        timeout=10000)
    loc = page.evaluate("""(kind) => {
        const rows = state.allLocations;
        if (kind === 'box') {
            const r = rows.find((x) => x.Type === 'Dryer Box' && parseInt(x['Max Spools'], 10) > 1);
            return r && r.LocationID;
        }
        const r = rows.find((x) => window.isPrinterRowNotHead(x));
        return r && r.LocationID;
    }""", kind)
    if not loc:
        pytest.skip(f"dev has no {kind} to pick in")
    page.evaluate("(loc) => { window.__picked = window.openSlotPicker({ location: loc, spool: 1 }); }", loc)
    page.wait_for_selector("#fcc-slot-picker", timeout=5000)
    assert page.evaluate("() => document.getElementById('fcc-slot-picker').dataset.fccPickerMode") == kind
    assert page.evaluate("() => window.fccHelpContextKey()") == key
    page.wait_for_selector("#fcc-slot-picker .fcc-sp-tile", timeout=15000)
    assert page.evaluate("() => window.fccHelpContextKey()") == key
    page.evaluate("() => { if (document.activeElement && document.activeElement.blur) document.activeElement.blur(); }")
    page.keyboard.press("?")
    expect(page.locator(OVERLAY)).to_be_visible()
    title = page.evaluate("(k) => window.fccHelpFor(k).title", key)
    expect(page.locator(TITLE)).to_have_text("❓ " + title)
    page.keyboard.press("Escape")                      # closes only the help
    expect(page.locator(OVERLAY)).to_be_hidden()
    expect(page.locator("#fcc-slot-picker")).to_be_visible()
    # Its ? button, beside its ✕: a click opens the same help, and Enter on it (Tab
    # reaches it: it is one of the picker's buttons) does too.
    btn = page.locator(f'#fcc-slot-picker .card-header [data-fcc-help="{key}"]')
    expect(btn).to_be_visible()
    btn.click()
    expect(page.locator(OVERLAY)).to_be_visible()
    expect(page.locator(TITLE)).to_have_text("❓ " + title)
    page.keyboard.press("Escape")
    expect(page.locator(OVERLAY)).to_be_hidden()
    btn.focus()
    page.keyboard.press("Enter")
    expect(page.locator(OVERLAY)).to_be_visible()
    page.keyboard.press("Escape")
    expect(page.locator(OVERLAY)).to_be_hidden()
    expect(page.locator("#fcc-slot-picker")).to_be_visible()
    page.keyboard.press("Escape")                      # the picker's own Escape: cancelled
    expect(page.locator("#fcc-slot-picker")).to_have_count(0)
    assert page.evaluate("() => window.__picked.then((r) => r)") is None
