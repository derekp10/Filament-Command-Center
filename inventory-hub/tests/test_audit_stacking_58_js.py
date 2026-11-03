"""Group 58's review: what sits on what during an audit, and where the keyboard goes.

Hermetic, so it runs under --offline: test_audit_no_label_58_js's `live` page (the real
overlay_mount.js, inv_core.js, inv_cmd.js, duplicate_picker.js, the real scan
accumulator and global.css, every request through the REAL routes and the real session
over tests/spoolman_extra_fake.SpoolmanHTTPFake), with the real inv_loose.js, the real
shortcuts_registry.js and the ⌨️ list's own markup from dashboard.html. A legacy label
two spools share is a real one on the fake, so the picker opens from the route's own
`ambiguous` answer. Keys and clicks are real ones: Space and Tab do what they do in the
browser, and no helper stands in for them.

test_audit_stacking_58_e2e.py has the same flows on the real dashboard, with Bootstrap.

  - The ⌨️ list draws over every overlay (findings 24 and 42): behind the panel it left
    N, the arrows and Enter dead with nothing on screen saying why.
  - The legacy picker draws over the 🧺 list (finding 25): behind it, scans went dead
    the same way.
  - Tab stays in what is on top (finding 27): it walked out of the list onto the panel's
    buttons, where Space pressed Cancel Audit.

RED on 1f8e03a unless a test says it pins what was already right.
"""
from __future__ import annotations

import pytest

from test_audit_no_label_58_js import (BACK, BUTTON, DONE, FOUND_URL, HIDE, HIT, LOOSE_BTN, MODULES, PANEL,  # noqa: F401
                                       PARK_URL, PAST_A_DOUBLE_PRESS, PAST_N, QUESTION, SHORTCUTS, UNDO, YES, _on_top,
                                       audit, begin, double_click, env, lay_over, live, page61, question_up,
                                       real_shortcut_list, scanned, sent, session, show_shortcut_list, three, tile,
                                       tile_says, two, wire)
from test_audit_panel_58_js import CANCEL
from test_audit_session_58 import add_spool

LOOSE = "#fcc-loose-list"
LOOSE_ROW = LOOSE + " .fcc-loose-row"
LOOSE_CLOSE = LOOSE + " [data-loose-close]"
PICKER = "#fcc-legacy-picker-overlay"
PICKER_USE = "#fcc-legacy-picker-use"
PICKER_LIST = "#fcc-legacy-picker-sel"
PICKER_FLASH = "#fcc-legacy-picker-flash"

# /api/loose_spools through the real route, as FCC_ROUTES takes the audit's.
LOOSE_ROUTE = r"""() => {
    const before = window.fetch;
    window.fetch = async (url, opts) => {
        const u = String(url);
        if (u.indexOf('/api/loose_spools') === -1) return before(url, opts);
        const text = await window.__fcc(u, 'GET', null);
        return { ok: true, status: 200, json: async () => JSON.parse(text) };
    };
}"""


def real_loose_list(page):
    page.add_script_tag(content=(MODULES / "inv_loose.js").read_text(encoding="utf-8"))
    page.evaluate(LOOSE_ROUTE)


def shared_label(env, ids=(57, 99), legacy="120"):
    """A legacy label two spools share, both expected at LR-MDB-1: the real route answers
    `ambiguous` for it, from the fake's own filament and spool lists."""
    filament = {"id": 7, "name": "Red", "material": "PLA", "color_hex": "72071C", "external_id": legacy,
                "vendor": {"id": 1, "name": "Some Brand"}, "extra": {}}
    env["fake"].add("filament", 7, {}, name="Red", material="PLA", color_hex="72071C", external_id=legacy)
    for slot, sid in enumerate(ids, start=1):
        env["fake"].add("spool", sid, {"container_slot": f'"{slot}"'}, location="LR-MDB-1", remaining_weight=500.0,
                        used_weight=100.0, initial_weight=1000.0, archived=False, filament=filament)


def scan_keys(page, text):
    """Through the real accumulator, as a scanner types."""
    page.keyboard.type(text, delay=0)
    page.keyboard.press("Enter")


def up_with_the_loose_list(page, env):
    """The panel up, its 🧺 list over it, opened by the panel's own button."""
    real_loose_list(page)
    add_spool(env, 86, "LR")
    begin(page, env)
    page.click(LOOSE_BTN)
    page.wait_for_selector(LOOSE_ROW + ".kb-active")


def picker_up(page, label="LEG:120"):
    """The label scanned, the picker up, and a person's Enter a person's again: for 100 ms
    after a scan's Enter another is its second (a scanner set to end with CR LF)."""
    scan_keys(page, label)
    page.wait_for_selector(PICKER)
    page.wait_for_function("(s) => document.activeElement === document.querySelector(s)", arg=PICKER_USE)
    page.wait_for_timeout(120)


def active(page):
    return page.evaluate("""() => { const a = document.activeElement;
        return a.id || (a.dataset && a.dataset.auditTile) || (a.classList.contains('fcc-loose-row') && 'row')
            || (a.hasAttribute('data-loose-close') && 'close') || a.tagName; }""")


def inside(page, root):
    return page.evaluate("(s) => !!document.activeElement.closest(s)", root)


def is_top(page, root):
    return page.evaluate("(s) => window.isTopOverlay(document.querySelector(s))", root)


def list_is_up(page):
    return page.evaluate("(s) => document.querySelector(s).style.display === 'block'", SHORTCUTS)


# --- the ⌨️ list --------------------------------------------------------------------------

def test_the_shortcut_list_draws_over_the_panel(live, env):
    """Findings 24 and 42. It opened at z 10001, under the panel at 20000: a person who
    pressed ? to read the panel's keys saw a sliver of it, and the keys went dead."""
    real_shortcut_list(live)
    two(env)
    begin(live, env)
    show_shortcut_list(live)
    assert _on_top(live, SHORTCUTS)
    assert live.evaluate("(s) => getComputedStyle(document.querySelector(s)).zIndex", SHORTCUTS) == "20201"
    assert live.evaluate("(s) => getComputedStyle(document.querySelector(s + '-backdrop')).zIndex", SHORTCUTS) == "20200"


def test_the_shortcut_list_draws_over_the_confirm_tier(live, env):
    """Over the question and over the 🧺 list: every guard reads it as on top."""
    real_shortcut_list(live)
    two(env)
    up_with_the_loose_list(live, env)
    show_shortcut_list(live)
    assert _on_top(live, SHORTCUTS)
    live.keyboard.press("Escape")
    live.keyboard.press("Escape")
    live.wait_for_selector(LOOSE, state="detached")
    question_up(live)
    live.wait_for_selector(QUESTION)
    show_shortcut_list(live)
    assert _on_top(live, SHORTCUTS)


def test_the_page_has_the_tiers_the_list_sits_above(live):
    """If the ladder grows, the list has to grow with it. A pin."""
    tiers = live.evaluate("() => Object.values(window.OVERLAY_Z)")
    assert max(tiers) < 20200


def test_escape_closes_only_the_list_and_the_panels_keys_come_back(live, env):
    """Its capture-phase Escape runs before mountOverlay's, so Escape can't hide the panel
    too, and the panel's keys stand down only for as long as the list is up. On a base
    with the list under the panel this passes: the guards are the same. The pin is that
    they still hold with the list on top."""
    real_shortcut_list(live)
    two(env)
    begin(live, env)
    scanned(live, "ID:57")
    live.wait_for_selector(BUTTON)
    live.focus(BUTTON)
    show_shortcut_list(live)

    live.keyboard.press("Enter")                 # nothing is pressed through it
    live.keyboard.press("n")
    live.wait_for_timeout(PAST_N)
    live.keyboard.press("ArrowRight")
    assert active(live) == BUTTON[1:]
    assert sent(live).count("CMD:NEEDLABEL") == 0 and wire(env, 57) is None

    live.keyboard.press("Escape")
    assert not list_is_up(live)
    assert live.is_visible(PANEL) and live.evaluate("state.auditActive") is True

    live.wait_for_timeout(520)                   # the n sits in the scan buffer, and an Enter
    #                                              under 500 ms would be a scan of it
    # The arrows. #99, not scanned, is drawn before #57, found (Derek, 2026-11-03, sample
    # 5a(i); PIN UPDATED DELIBERATELY: they went 57, then 99).
    live.keyboard.press("ArrowRight")
    assert active(live) == "99"
    live.keyboard.press("ArrowRight")
    assert active(live) == "57"
    live.keyboard.press("ArrowLeft")
    assert active(live) == "99"
    live.keyboard.press("Enter")                 # Enter on a tile
    tile_says(live, 99, "found, no label read")
    live.wait_for_timeout(120)
    live.keyboard.press("n")                     # and N, on the spool it found
    live.wait_for_selector(UNDO)
    assert wire(env, 99) == "true"


def test_a_second_question_mark_closes_it_too(live, env):
    """A pin: the panel stays up and its keys come back the same way. Proved on a copy
    whose ? never closes it."""
    real_shortcut_list(live)
    two(env)
    begin(live, env)
    show_shortcut_list(live)
    live.keyboard.press("?")
    live.wait_for_function("() => document.getElementById('fcc-shortcuts-overlay').style.display === 'none'")
    assert live.is_visible(PANEL)
    live.keyboard.press("ArrowRight")
    assert active(live) == "57"


def test_a_click_on_the_lists_backdrop_closes_only_the_list(live, env):
    """A pin of L218 over the panel: this click closes the list and reaches nothing. Proved
    on a copy whose backdrop does nothing."""
    real_shortcut_list(live)
    two(env)
    begin(live, env)
    show_shortcut_list(live)
    live.mouse.click(4, 4)
    assert not list_is_up(live)
    assert live.is_visible(PANEL) and sent(live) == []


@pytest.mark.parametrize("button", [CANCEL, DONE, BUTTON], ids=["cancel-audit", "done", "needs-a-label"])
def test_space_presses_nothing_under_the_shortcut_list(live, env, button):
    """personMayPress stopped a person's Enter there, and nothing stopped a Space. With the
    list on top the focused button can't be seen, and Space on Cancel Audit ended the
    audit and every scan in it."""
    real_shortcut_list(live)
    two(env)
    begin(live, env)
    scanned(live, "ID:57")
    live.wait_for_selector(BUTTON)
    live.focus(button)
    show_shortcut_list(live)
    before = list(sent(live))
    live.keyboard.press(" ")
    live.wait_for_timeout(150)
    assert sent(live) == before and session()["active"] is True
    assert live.is_visible(PANEL) and not live.locator(QUESTION).count()


def test_a_persons_enter_answers_no_question_under_the_list(live, env):
    """A dialog's own Enter handler doesn't go through the press rule. With the list drawn
    over the question, an Enter on Park parked every spool behind it, unseen. It still
    answers once the list has gone. RED on 1f8e03a: Enter parked them."""
    real_shortcut_list(live)
    three(env)
    begin(live, env)
    question_up(live)
    live.wait_for_selector(YES)
    live.focus(YES)
    show_shortcut_list(live)
    live.keyboard.press("Enter")
    live.wait_for_timeout(150)
    assert live.is_visible(QUESTION) and sent(live, PARK_URL) == []
    live.keyboard.press("Escape")
    assert live.is_visible(QUESTION)
    assert live.evaluate("(s) => document.activeElement === document.querySelector(s)", YES)
    live.keyboard.press("Enter")
    live.wait_for_selector(QUESTION, state="detached")
    assert len(sent(live, PARK_URL)) == 1


def test_a_persons_enter_picks_no_spool_under_the_list(live, env):
    """The picker's own Enter too. RED on 1f8e03a: it picked #57 behind the list."""
    real_shortcut_list(live)
    shared_label(env)
    begin(live, env)
    picker_up(live)
    live.select_option(PICKER_LIST, "57")
    live.focus(PICKER_USE)
    show_shortcut_list(live)
    live.keyboard.press("Enter")
    live.wait_for_timeout(150)
    assert live.is_visible(PICKER) and session()["scanned_items"] == []


def test_a_scan_goes_on_under_the_list(live, env):
    """A pin: the list stops a person's Enter, never a scan's. It takes no focus and asks
    nothing, so scans go on as they did. Proved on a copy with no enterIsAScan test."""
    real_shortcut_list(live)
    two(env)
    begin(live, env)
    live.wait_for_selector(tile(57))
    show_shortcut_list(live)
    scan_keys(live, "ID:57")
    live.wait_for_function("() => window.__sent.some((p) => p.body.text === 'ID:57')")
    live.wait_for_function("() => !state.processing")
    assert session()["scanned_items"] == [57]
    assert live.evaluate("state.scanBuffer") == ""


def test_enter_on_the_lists_own_close_button_still_closes_it(live, env):
    """A pin of the guard's exception: proved on a copy without it."""
    real_shortcut_list(live)
    two(env)
    begin(live, env)
    show_shortcut_list(live)
    live.focus(SHORTCUTS + " .btn-close")
    live.keyboard.press("Enter")
    assert not list_is_up(live)
    assert live.is_visible(PANEL)


def test_space_presses_again_once_the_list_has_gone(live, env):
    """A pin: the rule stops only what a mouse couldn't reach either. Proved on a copy whose
    Space never presses."""
    real_shortcut_list(live)
    two(env)
    begin(live, env)
    live.wait_for_selector(tile(57))
    live.focus(tile(57))
    show_shortcut_list(live)
    live.keyboard.press("Escape")
    live.keyboard.press(" ")
    tile_says(live, 57, "found, no label read")


# --- the legacy picker over the 🧺 list ---------------------------------------------------

def test_a_legacy_label_scanned_under_the_loose_list_opens_on_top(live, env):
    """Finding 25. The picker mounted at the standard tier, behind the list at the confirm
    tier and smaller than it, so it was wholly covered, and registered as the open
    question: every later scan went dead with nothing on screen saying why."""
    shared_label(env)
    up_with_the_loose_list(live, env)
    picker_up(live)
    assert _on_top(live, PICKER_USE) and _on_top(live, "#fcc-legacy-picker-cancel") and _on_top(live, PICKER_LIST)
    assert is_top(live, PICKER) and not is_top(live, LOOSE)
    assert live.get_attribute(PICKER, "data-overlay-tier") == "confirm"
    assert live.locator(LOOSE).count() == 1 and live.is_visible(PANEL)


def test_a_persons_enter_reaches_the_picker_over_the_loose_list(live, env):
    """The list's own key handler asks isTopOverlay, and stands down."""
    shared_label(env)
    up_with_the_loose_list(live, env)
    picker_up(live)
    live.select_option(PICKER_LIST, "99")
    live.focus(PICKER_USE)
    live.keyboard.press("Enter")
    live.wait_for_function("() => window.__sent.some((p) => p.body.text === 'ID:99')")
    live.wait_for_function("() => !state.processing")
    live.wait_for_selector(PICKER, state="detached")
    assert session()["scanned_items"] == [99]
    assert live.locator(LOOSE).count() == 1


def test_a_listed_spools_own_label_reaches_the_picker_over_the_loose_list(live, env):
    """A pin: a scan goes by the open question, not by what is drawn on top. Proved on a copy
    whose question takes no label."""
    shared_label(env)
    up_with_the_loose_list(live, env)
    picker_up(live)
    scan_keys(live, "ID:57")
    live.wait_for_function("() => window.__sent.some((p) => p.body.text === 'ID:57')")
    live.wait_for_function("() => !state.processing")
    live.wait_for_selector(PICKER, state="detached")
    assert session()["scanned_items"] == [57]


def test_a_refused_scan_is_said_where_it_can_be_read(live, env):
    """The picker's words sat in its flash, behind the list."""
    shared_label(env)
    up_with_the_loose_list(live, env)
    picker_up(live)
    scan_keys(live, "LOC:CR-CT-1")
    live.wait_for_function("(s) => document.querySelector(s).textContent.length > 0", arg=PICKER_FLASH)
    assert _on_top(live, PICKER_FLASH)
    assert live.is_visible(PICKER)


def test_escape_closes_only_the_picker_and_the_list_has_its_keys_back(live, env):
    shared_label(env)
    up_with_the_loose_list(live, env)
    picker_up(live)
    live.keyboard.press("Escape")
    live.wait_for_selector(PICKER, state="detached")
    assert live.locator(LOOSE).count() == 1 and live.is_visible(PANEL)
    assert is_top(live, LOOSE)
    live.keyboard.press("Escape")
    live.wait_for_selector(LOOSE, state="detached")
    assert live.is_visible(PANEL) and session()["active"] is True


def test_the_picker_is_at_the_confirm_tier_outside_an_audit_too(live, env):
    shared_label(env)
    live.evaluate("() => { state.auditActive = false; state.auditId = null; }")
    picker_up(live)
    assert live.get_attribute(PICKER, "data-overlay-tier") == "confirm"
    assert _on_top(live, PICKER_USE)


# --- Tab ----------------------------------------------------------------------------------

def test_the_reviews_shift_tab_walk_stays_in_the_loose_list(live, env):
    """Finding 27: ['fcc-loose-close', 'fcc-audit-panel-cancel', 'fcc-audit-panel-done', a
    tile, a tile, ...]. It goes between ✕ and the highlighted row now."""
    up_with_the_loose_list(live, env)
    walk = []
    for _ in range(4):
        live.keyboard.press("Shift+Tab")
        walk.append(active(live))
        assert inside(live, LOOSE), walk
    assert walk == ["close", "row", "close", "row"]


def test_tab_forward_stays_in_the_loose_list_too(live, env):
    up_with_the_loose_list(live, env)
    walk = []
    for _ in range(4):
        live.keyboard.press("Tab")
        walk.append(active(live))
    assert walk == ["close", "row", "close", "row"]


def test_the_keyboard_comes_back_to_the_rows_after_tab(live, env):
    """A pin of the arrows from ✕: they find the highlighted row."""
    up_with_the_loose_list(live, env)
    add_spool(env, 87, "LR")
    live.keyboard.press("Tab")
    assert active(live) == "close"
    live.keyboard.press("ArrowDown")
    assert inside(live, LOOSE) and active(live) == "row"


def test_space_cant_reach_cancel_audit_under_the_loose_list(live, env):
    """Finding 27. Two Shift+Tabs and a Space ended the audit: the walk now stays in the
    list, and a focus left under it (a script's, say) is refused by the press rule."""
    up_with_the_loose_list(live, env)
    live.keyboard.press("Shift+Tab")
    live.keyboard.press("Shift+Tab")
    live.keyboard.press(" ")
    live.wait_for_timeout(150)
    assert "CMD:CANCEL" not in sent(live) and session()["active"] is True
    live.focus(CANCEL)
    live.keyboard.press(" ")
    live.wait_for_timeout(150)
    assert "CMD:CANCEL" not in sent(live) and session()["active"] is True
    assert live.locator(LOOSE).count() == 1


def test_a_focus_left_behind_the_list_comes_to_its_first_control(live, env):
    up_with_the_loose_list(live, env)
    live.evaluate("() => document.activeElement.blur()")
    live.keyboard.press("Tab")
    assert active(live) == "close"


def test_tab_stays_in_the_picker_over_the_panel(live, env):
    """The list, then each of its buttons, and round again. Past the last it reached the
    page behind."""
    shared_label(env)
    begin(live, env)
    picker_up(live)
    walk = []
    for _ in range(10):
        live.keyboard.press("Tab")
        walk.append(active(live))
        assert inside(live, PICKER), walk
    order = ["fcc-legacy-picker-sel", "fcc-legacy-picker-cancel", "fcc-legacy-picker-addnew", "fcc-legacy-picker-print",
             "fcc-legacy-picker-use"]
    assert walk == order * 2


def test_shift_tab_stays_in_the_picker_too(live, env):
    shared_label(env)
    begin(live, env)
    picker_up(live)
    walk = []
    for _ in range(5):
        live.keyboard.press("Shift+Tab")
        walk.append(active(live))
    assert walk == ["fcc-legacy-picker-print", "fcc-legacy-picker-addnew", "fcc-legacy-picker-cancel",
                    "fcc-legacy-picker-sel", "fcc-legacy-picker-use"]


def test_a_tab_in_the_picker_is_still_a_persons_key(live, env):
    """Its handler ends what a person typed in the list, so the next Enter is no scan of
    it (Group 61 review 2). A pin: the trap stops the event with stopPropagation, not
    stopImmediatePropagation, so the document's other listeners still hear it. Proved on
    a copy that stops it dead."""
    shared_label(env)
    begin(live, env)
    picker_up(live)
    live.focus(PICKER_LIST)
    live.keyboard.type("#99", delay=120)
    assert live.evaluate("state.scanBuffer") == "#99"
    live.keyboard.press("Tab")
    assert active(live) == "fcc-legacy-picker-cancel"
    assert live.evaluate("state.scanBuffer") == ""


def test_tab_stays_on_the_panel_and_never_reaches_the_page_behind(live, env):
    """The page's boxes and buttons lie behind it, where a mouse can't reach. The walk
    goes round: every stop on the panel, then the first again."""
    two(env)
    begin(live, env)
    scanned(live, "ID:57")
    live.wait_for_selector(BUTTON)
    # PIN UPDATED DELIBERATELY (Derek, 2026-11-03, A2): 🔎 Find a spool is the header's first stop.
    # And again (his second look, sample 5a(i)): the spools still to find come first, so
    # #99, not scanned, before #57, found.
    stops = ["fcc-audit-panel-find", "fcc-audit-panel-loose", "fcc-audit-panel-close", "99", "57", BUTTON[1:],
             DONE[1:], CANCEL[1:]]
    live.focus(CANCEL)
    walk = []
    for _ in range(len(stops) * 2):
        live.keyboard.press("Tab")
        walk.append(active(live))
        assert inside(live, PANEL), walk
    assert walk == stops * 2


def test_shift_tab_stays_on_the_panel_too(live, env):
    two(env)
    begin(live, env)
    live.wait_for_selector(tile(99))
    # PIN UPDATED DELIBERATELY (Derek, 2026-11-03, A2): 🔎 Find a spool is the header's first stop.
    live.focus("#fcc-audit-panel-find")
    live.keyboard.press("Shift+Tab")
    assert active(live) == CANCEL[1:]


def test_a_focus_left_on_the_page_comes_to_the_panels_first_control(live, env):
    two(env)
    begin(live, env)
    live.wait_for_selector(tile(99))
    live.evaluate("() => document.activeElement.blur()")
    # PIN UPDATED DELIBERATELY (Derek, 2026-11-03, A2): 🔎 Find a spool is the header's first stop.
    live.keyboard.press("Tab")
    assert active(live) == "fcc-audit-panel-find"


def test_tab_leaves_done_while_it_is_down(live, env):
    """A disabled button is no stop: Done and Cancel are down while a press is answered."""
    three(env)
    begin(live, env)
    live.wait_for_selector(tile(99))
    live.evaluate("() => window.auditPanelBusy(true)")
    live.focus(tile(99))
    walk = []
    # PIN UPDATED DELIBERATELY (Derek, 2026-11-03, A2): 🔎 Find a spool is the header's first stop.
    # And again (his second look, sample 1b): Needs a label is in the dock from the start,
    # and stays a stop while Done and Cancel are down.
    for _ in range(5):
        live.keyboard.press("Tab")
        walk.append(active(live))
    assert walk == ["134", BUTTON[1:], "fcc-audit-panel-find", LOOSE_BTN[1:], HIDE[1:]]


def test_the_panels_trap_stands_down_under_the_question(live, env):
    """A pin: what is on top owns Tab, and the question's own handler walks its buttons."""
    three(env)
    begin(live, env)
    question_up(live)
    live.wait_for_function("(s) => document.activeElement === document.querySelector(s + ' .fcc-apc-no')", arg=QUESTION)
    live.keyboard.press("Tab")
    assert inside(live, QUESTION)
    live.keyboard.press("Tab")
    assert inside(live, QUESTION)


def test_the_panels_keys_come_back_when_the_list_closes(live, env):
    """A pin: the keyboard goes back to the button that opened the list, and Tab walks the
    panel from there. Proved on a copy that gives it no focus back."""
    up_with_the_loose_list(live, env)
    live.keyboard.press("Escape")
    live.wait_for_selector(LOOSE, state="detached")
    assert active(live) == LOOSE_BTN[1:]             # back on the button that opened it
    live.keyboard.press("Tab")
    assert active(live) == HIDE[1:]


# --- nothing picked, in an audit ----------------------------------------------------------

def test_use_selected_with_nothing_picked_finds_no_spool_and_says_so(live, env):
    """Finding 39. The picker's green default closed with no spool and no word, the person
    holding the spool believed it counted, and Done went on to offer it for parking. Not
    preselected either: a stray Enter would then find the wrong spool."""
    shared_label(env)
    begin(live, env)
    picker_up(live)
    assert live.evaluate("(s) => document.querySelector(s).selectedIndex", PICKER_LIST) == -1
    before = list(sent(live))
    live.keyboard.press("Enter")
    assert live.text_content(PICKER_FLASH) == "Pick a spool first"
    assert live.is_visible(PICKER) and sent(live) == before and session()["scanned_items"] == []
    assert _on_top(live, PICKER_FLASH)
    # The keyboard is in the list: a person picks there and answers.
    assert active(live) == PICKER_LIST[1:]
    live.keyboard.press("ArrowDown")
    live.keyboard.press("Enter")
    live.wait_for_function("() => window.__sent.some((p) => p.body.text === 'ID:57')")
    live.wait_for_function("() => !state.processing")
    live.wait_for_selector(PICKER, state="detached")
    assert session()["scanned_items"] == [57]


# --- a Space after a key left in the scan buffer (re-review finding 2) ----------------------

STRAY_MS = 600          # past the 500 ms a scan's first key counts as one in flight
SPACE_ON = {"cancel-audit": CANCEL, "park": YES, "a-tile": tile(57)}


@pytest.mark.parametrize("target", SPACE_ON.values(), ids=SPACE_ON.keys())
def test_a_space_after_a_stray_key_presses_nothing_under_the_list(live, env, target):
    """Re-review finding 2. The rule ran only with an empty scan buffer. The list teaches N,
    which stands down under it and stays in the buffer for 2 s, and a Space then pressed
    the hidden button: Cancel Audit ended the audit and its scans, Park sent the spools to
    Unknown unseen, and a tile found a spool nobody had. RED on 681232a."""
    real_shortcut_list(live)
    three(env)
    begin(live, env)
    live.wait_for_selector(tile(57))
    if target == YES:
        question_up(live)
        live.wait_for_timeout(PAST_A_DOUBLE_PRESS)          # its yes takes a press now
    live.focus(target)
    show_shortcut_list(live)
    live.keyboard.press("n")
    live.wait_for_timeout(STRAY_MS)
    assert live.evaluate("state.scanBuffer") == "n"
    before = (list(sent(live)), list(sent(live, PARK_URL)), list(sent(live, FOUND_URL)))
    live.keyboard.press(" ")
    live.wait_for_timeout(150)
    assert (sent(live), sent(live, PARK_URL), sent(live, FOUND_URL)) == before
    assert session()["active"] is True and list_is_up(live)


def test_a_space_after_a_stray_key_presses_nothing_under_the_dim(live, env):
    """Finding 2's last case: with no overlay up, the processing dim is what no mouse gets
    past. RED on 681232a: the button behind it took the press."""
    live.focus("#loc-cancel")
    live.evaluate("() => { state.processing = true; }")
    try:
        live.keyboard.press("x")
        live.wait_for_timeout(STRAY_MS)
        live.keyboard.press(" ")
        live.wait_for_timeout(100)
        assert live.evaluate("window.__clicks.cancel") == 0
    finally:
        live.evaluate("() => { state.processing = false; }")


def test_a_stray_key_then_a_space_where_a_mouse_could_click_still_presses(live, env):
    """A Space after a stray key on an uncovered button presses it, as it always did, and a
    press that waits takes its turn. A pin: proved on a copy that refuses every Space with
    a key in the buffer."""
    three(env)
    begin(live, env)
    live.focus(DONE)
    live.keyboard.press("x")
    live.wait_for_timeout(STRAY_MS)
    live.keyboard.press(" ")
    live.wait_for_selector(QUESTION)
    assert sent(live).count("CMD:DONE") == 1


# --- a scan's toast over the list (re-review finding 3) -------------------------------------

TOAST_ON_TOP = r"""(list) => {
    const c = document.getElementById('toast-container');
    const t = c && c.querySelector('.toast-msg');
    if (!t) return null;
    // Toasts take no pointer, so elementFromPoint can't see them: hit-testable for this look.
    c.style.pointerEvents = 'auto';
    t.style.pointerEvents = 'auto';
    const r = t.getBoundingClientRect();
    const hit = document.elementFromPoint(r.left + r.width / 2, r.top + 8);
    c.style.pointerEvents = '';
    t.style.pointerEvents = '';
    const l = document.querySelector(list).getBoundingClientRect();
    return { onTop: t.contains(hit),
             overlaps: r.left < l.right && r.right > l.left && r.top < l.bottom && r.bottom > l.top };
}"""


def test_a_scans_toast_reads_over_the_shortcut_list(live, env):
    """Re-review finding 3. The list draws over every overlay, and toasts under them: a scan
    read under the list (scans work there) toasted behind it, a failed one's 7 s included,
    and was gone before the list closed. Over the list only while it is up. RED on
    681232a."""
    real_shortcut_list(live)
    two(env)
    begin(live, env)
    show_shortcut_list(live)
    scan_keys(live, "LOC:LR-MDB-2")                         # refused: an audit is running
    live.wait_for_selector("#toast-container .toast-msg")
    assert live.evaluate(TOAST_ON_TOP, SHORTCUTS) == {"onTop": True, "overlaps": True}
    live.keyboard.press("Escape")
    assert live.evaluate("getComputedStyle(document.getElementById('toast-container')).zIndex") == "11000"


# --- the list gives the keyboard back (re-review finding 4) ---------------------------------

@pytest.mark.parametrize("close", ["backdrop", "its-close-button", "escape"])
def test_closing_the_list_gives_the_keyboard_back_to_the_question(live, env, close):
    """Re-review finding 4. Done's question was up with the keyboard on Back, its hint saying
    Enter goes back. A click on the list's ✕ or its backdrop took the focus to the page,
    and the question's keys, on its own overlay, heard nothing: Enter did nothing, with the
    question still up. RED on 681232a for the backdrop and the ✕; Escape kept the focus (a
    pin)."""
    real_shortcut_list(live)
    three(env)
    begin(live, env)
    question_up(live)
    live.wait_for_function("(s) => document.activeElement === document.querySelector(s)", arg=BACK)
    show_shortcut_list(live)
    if close == "backdrop":
        live.mouse.click(4, 4)
    elif close == "its-close-button":
        live.click(SHORTCUTS + " .btn-close")
    else:
        live.keyboard.press("Escape")
    assert not list_is_up(live)
    assert live.evaluate("(s) => document.activeElement === document.querySelector(s)", BACK)
    live.keyboard.press("Enter")
    live.wait_for_selector(QUESTION, state="detached")
    assert sent(live, PARK_URL) == [] and session()["active"] is True


def test_closing_the_list_leaves_a_keyboard_put_somewhere_since(live, env):
    """Only where the list left the keyboard nowhere (the page, or the list itself). A pin:
    proved on a copy that always gives it back."""
    real_shortcut_list(live)
    two(env)
    begin(live, env)
    live.wait_for_selector(tile(99))
    live.focus(tile(57))
    show_shortcut_list(live)
    live.evaluate("(s) => document.querySelector(s).focus()", tile(99))
    live.keyboard.press("Escape")
    assert active(live) == "99"


# --- a double click on what sits over the panel (re-review, item f) -------------------------
# Its first click closes it, and the second lands on the panel under it. Here Cancel Audit is
# laid under the control; test_audit_double_click_58_e2e.py has the real page's own spots.

def _cancel_under(page, control):
    """Cancel Audit moved under `control` (measured where it is now), above the rest of the
    panel (a spool the control finds brings the Last found strip up there). Answers its
    middle."""
    page.add_style_tag(content=f"{CANCEL} {{ z-index: 50 !important; }}")
    return lay_over(page, CANCEL, control)


def test_a_double_click_on_the_loose_lists_close_presses_nothing_on_the_panel(live, env):
    """RED on 681232a: the second click ended the audit."""
    up_with_the_loose_list(live, env)
    live.wait_for_timeout(PAST_A_DOUBLE_PRESS)              # past the press that opened it
    xy = _cancel_under(live, LOOSE_CLOSE)
    double_click(live, xy, then=LOOSE, state="detached")
    live.wait_for_timeout(150)
    assert live.evaluate(HIT, xy) == CANCEL[1:]
    assert "CMD:CANCEL" not in sent(live) and session()["active"] is True and live.is_visible(PANEL)


def test_a_double_click_on_a_loose_row_presses_nothing_on_the_panel(live, env):
    """During an audit a row opens nothing, so the list stays and takes the second click too.
    A pin: proved on a copy whose row closes the list."""
    up_with_the_loose_list(live, env)
    live.wait_for_timeout(PAST_A_DOUBLE_PRESS)
    xy = _cancel_under(live, LOOSE_ROW)
    double_click(live, xy)
    live.wait_for_timeout(150)
    assert live.is_visible(LOOSE) and "CMD:CANCEL" not in sent(live) and session()["active"] is True


def test_a_double_click_on_the_shortcut_lists_close_presses_nothing_on_the_panel(live, env):
    """On the real page its ✕ lands on or beside the panel's Hide. RED on 681232a: the second
    click ended the audit."""
    real_shortcut_list(live)
    two(env)
    begin(live, env)
    show_shortcut_list(live)
    xy = _cancel_under(live, SHORTCUTS + " .btn-close")
    double_click(live, xy, then=SHORTCUTS, state="hidden")
    live.wait_for_timeout(150)
    assert live.evaluate(HIT, xy) == CANCEL[1:]
    assert "CMD:CANCEL" not in sent(live) and session()["active"] is True and live.is_visible(PANEL)


def test_a_double_click_on_the_pickers_use_selected_presses_nothing_on_the_panel(live, env):
    """It closes the picker and finds the spool picked; the second click lands on the panel.
    RED on 681232a: the second click ended the audit."""
    shared_label(env)
    begin(live, env)
    picker_up(live)
    live.select_option(PICKER_LIST, "57")
    xy = _cancel_under(live, PICKER_USE)
    double_click(live, xy, then=PICKER, state="detached")
    live.wait_for_function("() => !state.processing")
    live.wait_for_timeout(150)
    assert live.evaluate(HIT, xy) == CANCEL[1:]
    assert "CMD:CANCEL" not in sent(live) and session()["active"] is True
    assert session()["scanned_items"] == [57]
