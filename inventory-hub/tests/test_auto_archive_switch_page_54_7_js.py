"""Group 54.7, the page half: each weigh window sends its own "Auto-Archive 0g"
switch (Derek, 2026-11-07, (a): off means off), hermetic.

Two switches decide whether a spool weighed to 0 g is archived: the weigh-out
list's "Auto-Archive 0g" (`#weigh-auto-archive`) and the Quick-Weigh's own "Auto
Archive & Eject if Empty (0g)" (`#fcc-we-auto-archive`). Each only decided
whether `saveSpoolWeight` sent `archived: true` and unassigned the spool after,
while the server archived every weight write that left nothing, so with a switch
off the spool was archived and taken off its place anyway. The server half
(cac365d) reads an optional top-level `auto_archive` beside `id` and `updates`:
only JSON false turns the archive-on-empty edge off.

Now every save from the weigh-out list (a row's, and the row's fallback when its
details couldn't be read) sends the list's switch, and the Quick-Weigh's sends its
own switch, never the other window's: the switch, not the per-save verdict, so
with it on the server's rule still decides when the page's arithmetic disagrees.
With the switch off and a save that leaves 0 g by the page's own reading, the
success toast says the spool was kept in stock. With the switch on, nothing
changes: `archived: true` and the force-unassign after it, as before.

Runs the REAL overlay_mount.js, inv_core.js, ui_builder.js, weight_utils.js,
weight_entry.js, inv_details.js, inv_cmd.js and inv_weigh_out.js, the weigh-out
window's real markup and the real scan accumulator, in `isolated_page` (no route
to any network), so it RUNS under --offline. The server is the page's `fetch`,
test_weigh_out_scan_focus_js.py's stub; keys are real, on the page's fake clock.

Base proof (94f87de): every test marked RED fails there; the controls pass.

Group 54 review, R3-1 (2026-11-09): the switch is read when Enter is pressed, not
once the row's details have come. The tests under its heading are RED on c2f4222.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from test_quick_weigh_scan_js import FAKE_CLOCK, later, press
from test_slow_scan_slash_js import _accumulator
from test_weigh_out_scan_focus_js import PAGE, SETUP, STUBS

HUB = Path(__file__).resolve().parent.parent
MODULES = HUB / "static" / "js" / "modules"
# The page's own order (templates/components/scripts.html), less what these flows never call.
ORDER = ("overlay_mount.js", "inv_core.js", "ui_builder.js", "weight_utils.js", "weight_entry.js",
         "inv_details.js", "inv_cmd.js", "inv_weigh_out.js")
# The Quick-Weigh reads and writes its stored default mode; a page made with
# set_content has no storage of its own.
STORAGE = r"""
window.__store = {};
Object.defineProperty(window, 'localStorage', { configurable: true, get: () => ({
    getItem: (k) => (k in window.__store ? window.__store[k] : null),
    setItem: (k, v) => { window.__store[k] = String(v); },
    removeItem: (k) => { delete window.__store[k]; } }) });
"""
KEPT = "Updated Spool #57: 0 g left, kept in stock (Auto-Archive is off)"
PLAIN = "Updated Spool #57"


@pytest.fixture
def weigh(isolated_page):
    page = isolated_page
    page.set_content(PAGE)
    page.add_script_tag(content=STUBS + STORAGE)
    for name in ORDER:
        page.add_script_tag(content=(MODULES / name).read_text(encoding="utf-8"))
    page.add_script_tag(content="window.setInterval = window.__si;")
    page.add_script_tag(content=_accumulator())          # last, as on the page
    page.evaluate(FAKE_CLOCK)
    return page


def _open_list(page, held=(57, 6), mode="net"):
    page.evaluate(SETUP, list(held))
    page.evaluate("(m) => { window.weighOutMode = m; window.openWeighOutModal(); }", mode)
    page.wait_for_function("(id) => document.activeElement && document.activeElement.dataset"
                           " && document.activeElement.dataset.id === id", arg=str(held[0]))


def _list_switch(page, on):
    """The weigh-out list's switch set as a person sets it: a click (it starts on)."""
    if page.evaluate("() => document.getElementById('weigh-auto-archive').checked") != on:
        page.locator("#weigh-auto-archive").click()
        later(page, 700)
    assert page.evaluate("() => document.getElementById('weigh-auto-archive').checked") is on


def _open_quick_weigh(page, sid=57):
    page.evaluate("(id) => window.openQuickWeigh(id)", sid)
    page.wait_for_function("() => document.activeElement === document.querySelector('#fcc-we-input')")


def _updates(page):
    return page.evaluate("() => window.__posts.filter((p) => p.url === '/api/spool/update').map((p) => p.body)")


def _unassigned(page):
    return page.evaluate("() => window.__posts.filter((p) => p.url === '/api/manage_contents')"
                         ".map((p) => p.body.spool_id)")


def _saved_and_toasted(page):
    """The weight posted, and its success toast up (it comes once the save, and
    the force-unassign after an archive, have answered)."""
    page.wait_for_function("() => window.__posts.some((p) => p.url === '/api/spool/update')", timeout=5000)
    page.wait_for_function("() => Array.from(document.querySelectorAll('#toast-container .toast-msg'))"
                           ".some((t) => t.innerText.startsWith('Updated Spool #'))", timeout=5000)
    page.wait_for_timeout(50)


def _success_toasts(page):
    return page.evaluate("() => Array.from(document.querySelectorAll('#toast-container .toast-msg'))"
                         ".map((t) => t.innerText).filter((t) => t.startsWith('Updated Spool #'))")


def _check(page, *, switch_on, empties, body_key="used_weight", value=750):
    ups = _updates(page)
    assert len(ups) == 1, ups
    body = ups[0]
    assert body["id"] == 57, body
    assert "auto_archive" in body and body["auto_archive"] is switch_on, body
    assert body["updates"][body_key] == value, body
    archives = switch_on and empties
    assert ("archived" in body["updates"]) is archives, body
    assert _unassigned(page) == ([57] if archives else []), _unassigned(page)
    assert _success_toasts(page) == [KEPT if (not switch_on and empties) else PLAIN], _success_toasts(page)
    assert page.evaluate("() => window.__errors") == []


@pytest.mark.parametrize("switch_on", [True, False], ids=["switch-on", "switch-off"])
@pytest.mark.parametrize("reading, used, empties", [("0", 750, True), ("425", 325, False)],
                         ids=["empty", "425g-left"])
def test_a_row_save_sends_the_lists_switch(weigh, switch_on, reading, used, empties):
    """RED: a row's save (Net) sends the list's switch as `auto_archive`, a real
    boolean, whatever the reading. Off, #57 weighed to 0 g is sent no `archived`,
    isn't unassigned, and the toast says it was kept in stock; on, it is archived
    and unassigned as before. On the base the body had no `auto_archive`, so the
    server archived #57 at 0 g with the switch off, and the toast said only
    "Updated Spool #57"."""
    page = weigh
    _open_list(page)
    _list_switch(page, switch_on)
    press(page, reading, 150)
    _saved_and_toasted(page)
    _check(page, switch_on=switch_on, empties=empties, value=used)


@pytest.mark.parametrize("switch_on", [True, False], ids=["switch-on", "switch-off"])
@pytest.mark.parametrize("reading, empties", [("0", True), ("425", False)], ids=["empty", "425g-left"])
def test_the_fallback_row_sends_the_lists_switch(weigh, switch_on, reading, empties):
    """RED: a row whose details couldn't be read saves its Net reading as the weight
    left (`remaining_weight`), and sends the list's switch beside it."""
    page = weigh
    page.evaluate("() => { window.__detailsFail = true; }")
    _open_list(page)
    _list_switch(page, switch_on)
    press(page, reading, 150)
    _saved_and_toasted(page)
    _check(page, switch_on=switch_on, empties=empties, body_key="remaining_weight", value=int(reading))


@pytest.mark.parametrize("qw_on, list_on", [(True, False), (False, True), (False, False), (True, True)],
                         ids=["qw-on-list-off", "qw-off-list-on", "both-off", "both-on"])
@pytest.mark.parametrize("reading, empties", [("+650", True), ("+25", False)], ids=["empty", "125g-used"])
def test_the_quick_weigh_sends_its_own_switch(weigh, qw_on, list_on, reading, empties):
    """RED: the Quick-Weigh sends ITS switch, never the weigh-out list's (whose
    markup is on the page, hidden, with a state of its own). #57 holds 650 g, so
    "+650" (Additive) empties it."""
    page = weigh
    page.evaluate("(on) => { document.getElementById('weigh-auto-archive').checked = on; }", list_on)
    _open_quick_weigh(page)
    page.evaluate("(on) => { document.getElementById('fcc-we-auto-archive').checked = on; }", qw_on)
    press(page, reading, 200)
    _saved_and_toasted(page)
    _check(page, switch_on=qw_on, empties=empties, value=750 if empties else 125)


def test_the_kept_in_stock_toast_stays_up_for_a_success_toasts_4_seconds(weigh):
    """RED: the longer words stay up for CLAUDE.md's 4 s success toast; showToast's
    default, which the plain "Updated Spool #57" keeps, takes a toast down after
    2 s (and 300 ms of fade). One-sided on purpose: a timer never fires early."""
    page = weigh
    _open_list(page)
    _list_switch(page, False)
    press(page, "0", 150)
    _saved_and_toasted(page)
    page.wait_for_timeout(2700)
    assert KEPT in _success_toasts(page), _success_toasts(page)


def test_an_archived_spool_weighed_to_0_with_the_switch_off_isnt_called_kept_in_stock(weigh):
    """An archived spool (archived by hand, say) weighed to 0 g with the switch off
    stays archived where it is (the server's rule), so the toast doesn't say it was
    kept in stock. RED for the body (no `auto_archive` on the base); the toast's
    words are a control."""
    page = weigh
    page.evaluate("() => { window.__spools[57].archived = true; }")
    _open_quick_weigh(page)
    page.evaluate("() => { document.getElementById('fcc-we-auto-archive').checked = false; }")
    press(page, "+650", 200)
    _saved_and_toasted(page)
    body = _updates(page)[0]
    assert body["auto_archive"] is False and "archived" not in body["updates"], body
    assert _success_toasts(page) == [PLAIN], _success_toasts(page)
    assert _unassigned(page) == []


def test_an_archived_spool_in_the_list_isnt_called_kept_in_stock_either(weigh):
    """The same, from a weigh-out row: its details say the spool is archived."""
    page = weigh
    page.evaluate("() => { window.__spools[57].archived = true; window.__rows[57].archived = true; }")
    _open_list(page)
    _list_switch(page, False)
    press(page, "0", 150)
    _saved_and_toasted(page)
    body = _updates(page)[0]
    assert body["auto_archive"] is False and "archived" not in body["updates"], body
    assert _success_toasts(page) == [PLAIN], _success_toasts(page)


def test_control_an_older_caller_that_names_no_switch_sends_none(weigh):
    """Control, green on the base: a caller that passes its own verdict and names no
    switch (as test_single_slot_lifecycle_js does) sends no `auto_archive`, so the
    server's rule decides, as before."""
    page = weigh
    page.evaluate("() => window.saveSpoolWeight(57, null, { used_weight: 750 }, false)")
    _saved_and_toasted(page)
    body = _updates(page)[0]
    assert "auto_archive" not in body and "archived" not in body["updates"], body
    assert _success_toasts(page) == [PLAIN], _success_toasts(page)


# --- Group 54 review, R3-1 (2026-11-09): the switch is read when Enter is pressed ---


def _enter_then_click_the_switch(page, *, on_at_enter, fail_details):
    """#57 weighed empty (Net 0) and its Enter pressed with the list's switch as
    `on_at_enter`, while #57's details are still being read (held: a slow
    Spoolman), so its row waits; then the person clicks the switch (for the next
    spool, say), and only then do the details come (or fail to: the fallback)."""
    page.evaluate("(f) => { window.__holdDetails = [57]; window.__detailsFail = f; }", fail_details)
    _open_list(page)
    _list_switch(page, on_at_enter)
    press(page, "0", 150)
    later(page, 200)
    assert _updates(page) == [], "nothing is sent while #57's details are read"
    page.locator("#weigh-auto-archive").click()
    later(page, 200)
    assert page.evaluate("() => document.getElementById('weigh-auto-archive').checked") is (not on_at_enter)
    page.evaluate("() => window.__releaseDetails(57)")
    _saved_and_toasted(page)


@pytest.mark.parametrize("fail_details", [False, True], ids=["details", "fallback"])
@pytest.mark.parametrize("on_at_enter", [False, True], ids=["off-at-enter", "on-at-enter"])
def test_a_save_that_waits_for_its_details_sends_the_switch_as_it_was_at_enter(weigh, on_at_enter, fail_details):
    """RED: a row's save waits up to 10 s for its spool's details (the fallback too,
    when they can't be read), and the switch was read only once they came, so a
    click on it meanwhile decided the spool before it. Off at Enter and turned on:
    #57 was sent `archived: true` and `auto_archive: true`, then force-unassigned,
    archived and taken off its shelf against what was asked (the toast said only
    "Updated Spool #57"). On at Enter and turned off: #57, asked to be archived,
    was kept in stock. Now the switch is read at Enter: off sends `auto_archive:
    false`, no `archived` and no force-unassign, and says it was kept in stock; on
    sends `auto_archive: true`, `archived: true` and the force-unassign."""
    page = weigh
    _enter_then_click_the_switch(page, on_at_enter=on_at_enter, fail_details=fail_details)
    if fail_details:
        _check(page, switch_on=on_at_enter, empties=True, body_key="remaining_weight", value=0)
    else:
        _check(page, switch_on=on_at_enter, empties=True, value=750)


# --- Derek, 2026-11-09 (Group 54's picture walk): the list's switch is on each time the list opens ---


def _close_list(page):
    page.evaluate("""() => { const m = document.getElementById('weighOutModal'); m.classList.remove('show');
        m.dispatchEvent(new Event('hidden.bs.modal', { bubbles: true })); }""")


def _switch_checked(page):
    return page.evaluate("() => document.getElementById('weigh-auto-archive').checked")


def test_the_lists_switch_is_on_again_each_time_the_list_opens(weigh):
    """RED: Derek, 2026-11-09 (Group 54's picture walk, "Back on each open"). Since
    54.7 off means off, so a switch left off at one weigh-out kept every spool
    weighed to 0 g in stock at the next, until the page was reloaded. Like the
    Quick-Weigh's switch, which is drawn on each time it opens, the list's is on
    again each time the list opens; turned off, it stays off for the rest of that
    session, through a save. On the base it kept its last state: off at the second
    open, and that open's save sent `auto_archive: false`."""
    page = weigh
    _open_list(page)
    _list_switch(page, False)
    press(page, "425", 150)
    _saved_and_toasted(page)
    assert _updates(page)[-1]["auto_archive"] is False, _updates(page)
    assert _switch_checked(page) is False, "off stays off for the rest of the session"
    _close_list(page)
    _open_list(page)
    assert _switch_checked(page) is True, "on again at the next open"
    press(page, "425", 150)
    page.wait_for_function("() => window.__posts.filter((p) => p.url === '/api/spool/update').length === 2",
                           timeout=5000)
    assert _updates(page)[-1]["auto_archive"] is True, _updates(page)
    assert page.evaluate("() => window.__errors") == []


def test_control_a_scanned_weigh_command_opens_the_list_with_the_switch_on_too(weigh):
    """The WEIGH tile and a `CMD:WEIGH` scan both open the list through
    `openWeighOutModal`, so the scan's open starts with the switch on as well."""
    page = weigh
    _open_list(page)
    _list_switch(page, False)
    _close_list(page)
    page.evaluate("(held) => { state.heldSpools = held.map((id) => Object.assign({}, window.__rows[id])); }",
                  [57, 6])
    page.evaluate("() => window.processScan('CMD:WEIGH', 'barcode')")
    page.wait_for_function("() => document.getElementById('weighOutModal').classList.contains('show')",
                           timeout=5000)
    assert _switch_checked(page) is True
