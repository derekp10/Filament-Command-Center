"""The weigh-out list puts a reading in the box of the spool it is for (Group
57 review, round 7: RED), hermetic.

Runs the REAL overlay_mount.js, inv_core.js, ui_builder.js, weight_utils.js,
inv_details.js (the post-archive empty-weight prompt), inv_cmd.js (processScan,
the scan router) and inv_weigh_out.js, with the weigh-out window's real markup
(templates/components/modals_weigh_out.html) and the real scan accumulator, in
`isolated_page` (a chromium with no route to any network), so it RUNS under
--offline. The server is the page's `fetch`: /api/identify_scan answers a
spool label as the server does, `__answerMs` later. inv_cmd.js's 2 s buffer
poll is held off. Real keys on the page's fake clock
(test_quick_weigh_scan_js.press).

The defects (RED on 4ac78d0, each test says how): the window's flow is "Scan
new items to add to this list. Type weight and press Enter to save.", and a
scanned spool's row is drawn at the top, but the focus stayed in the box that
had it, so the reading for the spool in the person's hand was saved to another
spool (a 0 g reading archived that spool and took it off its place). A spool
already listed, scanned to pick it, kept the focus where it was too (older).
The focus fell to the page after the missing-tare prompt was cancelled and
after the post-archive empty-weight prompt closed, and after a click on the
Auto-Archive switch (it blurred itself), and a reading typed on a mode button
stayed on the button: the reading went to the scan path as a spool id, and
that spool joined the scan buffer unseen.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from test_quick_weigh_scan_js import FAKE_CLOCK, later, press
from test_slow_scan_slash_js import _accumulator

HUB = Path(__file__).resolve().parent.parent
MODULES = HUB / "static" / "js" / "modules"
WEIGH_OUT = (HUB / "templates" / "components" / "modals_weigh_out.html").read_text(encoding="utf-8")
PAGE = ("<!doctype html><html><head><meta charset='utf-8'><style>.modal{display:none}.modal.show{display:block}"
        "</style></head><body>" + WEIGH_OUT + "</body></html>")

# Spool #8 has no empty-spool weight anywhere (spool, filament or vendor), so
# Gross asks for one; its filament (#5) has none either, so emptying it opens
# the post-archive empty-weight prompt.
STUBS = r"""
window.__errors = [];
window.addEventListener('error', (e) => window.__errors.push(String(e.message)));
window.__posts = [];
window.__answerMs = 50;              // /api/identify_scan's answer, ms later (real time)
window.__answerMsFor = {};           // ... for one scan's text
window.__saveMs = 0;                 // /api/spool/update's
window.__filamentMs = 0;             // /api/filament_details' (the empty-weight prompt reads it first)
window.__detailsMs = 0;              // /api/spool_details'
window.__detailsFail = false;        // /api/spool_details answers nothing a spool's details can be read from
window.__answeredScans = 0;
// Answers held until the test lets them go (window.__release('scan' | 'save')),
// so a test that types "before the answer" never races a timer: __holdScans
// is true (every scan) or a list of scan texts, __holdSaves true or false.
window.__holdScans = false;
window.__holdSaves = false;
window.__held = { scan: [], save: [] };
window.__release = (kind) => { const fs = window.__held[kind]; window.__held[kind] = []; fs.forEach((f) => f()); };
window.__spools = {
    6: { id: 6, initial_weight: 1000, used_weight: 31, spool_weight: 167,
         filament: { id: 2, name: 'Red', material: 'PLA', vendor: { name: 'Acme' } } },
    134: { id: 134, initial_weight: 1000, used_weight: 0, spool_weight: 200,
           filament: { id: 3, name: 'Blue', material: 'PETG', vendor: { name: 'Acme' } } },
    57: { id: 57, initial_weight: 750, used_weight: 100, spool_weight: 150,
          filament: { id: 4, name: 'Green', material: 'PLA', vendor: { name: 'Acme' } } },
    8: { id: 8, initial_weight: 1000, used_weight: 0,
         filament: { id: 5, name: 'Grey', material: 'PLA', vendor: { id: 9, name: 'Acme' } } },
};
window.__rows = {
    6: { id: 6, display: 'Acme - PLA - Red', color: 'cc0000', remaining_weight: 969 },
    134: { id: 134, display: 'Acme - PETG - Blue', color: '0000cc', remaining_weight: 1000 },
    57: { id: 57, display: 'Acme - PLA - Green', color: '00cc00', remaining_weight: 650 },
    8: { id: 8, display: 'Acme - PLA - Grey', color: '888888', remaining_weight: 1000 },
};
window.fetch = function (url, opts) {
    url = String(url);
    const body = opts && opts.body ? JSON.parse(opts.body) : null;
    if (opts && opts.method && opts.method !== 'GET') window.__posts.push({ url, body });
    let ans = { status: 'success', success: true };
    let m = /spool_details\?id=(\d+)/.exec(url);
    if (m) ans = window.__detailsFail ? {} : (window.__spools[m[1]] || {});
    m = /filament_details\?id=(\d+)/.exec(url);
    if (m) ans = { id: Number(m[1]), name: 'Grey', material: 'PLA', vendor: { id: 9, name: 'Acme' } };
    if (url.includes('/api/spool/update') && body.updates.archived) {
        ans = { status: 'success', needs_empty_weight_prompt: true, filament_id: window.__spools[body.id].filament.id };
    }
    if (url.includes('/api/identify_scan')) {
        const s = /^ID:(\d+)$/.exec(body.text);
        ans = s && window.__rows[s[1]] ? Object.assign({ type: 'spool' }, window.__rows[s[1]])
            : { type: 'error', msg: 'Unknown Code' };
    }
    const scan = url.includes('/api/identify_scan');
    const ms = scan ? (body.text in window.__answerMsFor ? window.__answerMsFor[body.text] : window.__answerMs)
        : url.includes('/api/spool/update') ? window.__saveMs
        : url.includes('/api/filament_details') ? window.__filamentMs
        : url.includes('/api/spool_details') ? window.__detailsMs : 0;
    const save = url.includes('/api/spool/update');
    const held = scan ? (window.__holdScans === true
        || (Array.isArray(window.__holdScans) && window.__holdScans.includes(body.text))) : (save && window.__holdSaves);
    return new Promise((res) => {
        const answer = () => {
            if (scan) window.__answeredScans += 1;
            res({ ok: true, status: 200, json: () => Promise.resolve(ans) });
        };
        if (held) window.__held[scan ? 'scan' : 'save'].push(answer);
        else setTimeout(answer, ms);
    });
};
window.__si = window.setInterval; window.setInterval = () => 0;   // inv_cmd.js's 2 s buffer poll: off
"""

SETUP = r"""(held) => {
    modals.weighOutModal = { show: () => document.getElementById('weighOutModal').classList.add('show') };
    state.heldSpools = held.map((id) => Object.assign({}, window.__rows[id]));
}"""


@pytest.fixture
def wo(isolated_page):
    page = isolated_page
    page.set_content(PAGE)
    page.add_script_tag(content=STUBS)
    for name in ("overlay_mount.js", "inv_core.js", "ui_builder.js", "weight_utils.js", "inv_details.js",
                 "inv_cmd.js", "inv_weigh_out.js"):
        page.add_script_tag(content=(MODULES / name).read_text(encoding="utf-8"))
    page.add_script_tag(content="window.setInterval = window.__si;")
    page.add_script_tag(content=_accumulator())          # last, as on the page
    page.evaluate(FAKE_CLOCK)

    def open_(held=(6, 134), mode="net"):
        page.evaluate(SETUP, list(held))
        page.evaluate("(m) => { window.weighOutMode = m; window.openWeighOutModal(); }", mode)
        page.wait_for_function("(id) => document.activeElement && document.activeElement.dataset"
                               " && document.activeElement.dataset.id === id", arg=str(held[0]))

    return page, open_


def _focus(page):
    return page.evaluate("() => { const a = document.activeElement; return a && a.dataset && a.dataset.id ? a.dataset.id : (a ? (a.id || a.tagName) : null); }")


def _box(page, sid):
    return page.evaluate("(id) => (document.querySelector(`.weigh-input[data-id=\"${id}\"]`) || {}).value", sid)


def _updates(page):
    return page.evaluate("() => window.__posts.filter((p) => p.url === '/api/spool/update').map((p) => p.body)")


def _scans(page):
    return page.evaluate("() => window.__posts.filter((p) => p.url === '/api/identify_scan').map((p) => p.body.text)")


def _answered(page, sid):
    """The scan of spool `sid` answered and handled (it is in the buffer)."""
    page.wait_for_function("(id) => state.heldSpools.some((s) => s.id === id)", arg=sid, timeout=5000)
    page.wait_for_timeout(30)


def _saved(page, n=1):
    """`n` weights posted (a short wait: where none comes, the test fails at once)."""
    page.wait_for_function("(n) => window.__posts.filter((p) => p.url === '/api/spool/update').length >= n",
                           arg=n, timeout=3000)
    page.wait_for_timeout(30)


def _scan_answered(page, n=1):
    """The server's answer to the `n`th scan in, and handled."""
    page.wait_for_function("(n) => window.__answeredScans >= n", arg=n, timeout=5000)
    page.wait_for_timeout(30)


def _held(page, kind, n=1):
    """`n` answers of `kind` ('scan' / 'save') held, waiting on the test."""
    page.wait_for_function("([k, n]) => window.__held[k].length >= n", arg=[kind, n], timeout=5000)


def _release(page, kind):
    page.evaluate("(k) => window.__release(k)", kind)


def _unassigned(page):
    return page.evaluate("() => window.__posts.filter((p) => p.url === '/api/manage_contents').map((p) => p.body.spool_id)")


def _filament_writes(page):
    return page.evaluate("() => window.__posts.filter((p) => p.url === '/api/update_filament').length")


def _toasts(page):
    return page.evaluate("() => Array.from(document.querySelectorAll('#toast-container .toast-msg')).map((t) => t.innerText)")


@pytest.mark.parametrize("reading, used", [("425", 325), ("0", 750)])
def test_a_scanned_spools_box_takes_the_focus_and_its_reading(wo, reading, used):
    """#6's box has the focus and spool #57's label is scanned into it, as the
    window's footer asks: #57's row is drawn first and its box takes the
    focus, so the reading typed next is #57's (Net: 750 g - 425 g = 325 g
    used). RED on 4ac78d0: the focus stayed in #6's box and the reading was
    saved to #6; a 0 g reading archived #6 and took it off its place."""
    page, open_ = wo
    open_()
    press(page, "ID:57", 5)
    _answered(page, 57)
    assert _focus(page) == "57"
    later(page, 900)
    press(page, reading, 150)
    _saved(page)
    ups = _updates(page)
    assert [u["id"] for u in ups] == [57] and ups[0]["updates"]["used_weight"] == used, ups
    unassigned = page.evaluate("() => window.__posts.filter((p) => p.url === '/api/manage_contents').map((p) => p.body.spool_id)")
    assert unassigned == ([57] if reading == "0" else []), unassigned
    assert page.evaluate("() => window.__errors") == []


@pytest.mark.parametrize("stale", ["", "300"])
def test_a_listed_spool_scanned_to_pick_it_takes_the_focus(wo, stale):
    """A spool already in the list, scanned to pick it: its box takes the
    focus, and the reading typed next is saved to it, in place of a reading
    left in its box earlier (it is selected). RED on 4ac78d0 (and before Group
    57): the focus stayed in #6's box, and the reading was saved to #6."""
    page, open_ = wo
    open_()
    if stale:
        page.evaluate("(v) => { document.querySelector('.weigh-input[data-id=\"134\"]').value = v; }", stale)
    press(page, "ID:134", 5)
    _scan_answered(page)
    assert _focus(page) == "134"
    later(page, 900)
    press(page, "425", 150)
    _saved(page)
    ups = _updates(page)
    assert [u["id"] for u in ups] == [134] and ups[0]["updates"]["used_weight"] == 575, (stale, ups)


def test_a_reading_typed_before_the_scan_is_answered_goes_with_it(wo):
    """The person starts typing the reading before the server has answered the
    scan (a slow Spoolman): what they typed moves to the scanned spool's box,
    and the box that had the focus keeps what it held. RED on 4ac78d0: it all
    went into #6's box and was saved to #6."""
    page, open_ = wo
    page.evaluate("() => { window.__holdScans = true; }")
    open_()
    press(page, "ID:57", 5)
    _held(page, "scan")
    later(page, 300)
    press(page, "4", 0, enter=False)          # the server hasn't answered yet
    assert _box(page, 6) == "4"
    _release(page, "scan")
    _answered(page, 57)
    assert (_focus(page), _box(page, 57), _box(page, 6)) == ("57", "4", "")
    later(page, 150)
    press(page, "25", 150)
    _saved(page)
    ups = _updates(page)
    assert [u["id"] for u in ups] == [57] and ups[0]["updates"]["used_weight"] == 325, ups


def test_save_then_scan_the_next_spool_then_its_reading(wo):
    """The natural order: #6's reading saved, the next new spool scanned a
    moment later, and its reading typed: saved to it. RED on 4ac78d0: the focus
    had gone on to #134 after the save and stayed there, so #57's reading was
    saved to #134."""
    page, open_ = wo
    open_()
    press(page, "500", 150)
    _saved(page)
    later(page, 600)
    press(page, "ID:57", 5)
    _answered(page, 57)
    page.wait_for_function("() => !document.querySelector('.weigh-input[data-id=\"6\"]')")   # the saved row's fade
    assert _focus(page) == "57"
    later(page, 900)
    press(page, "425", 150)
    _saved(page, 2)
    assert [u["id"] for u in _updates(page)] == [6, 57]


def test_a_reading_left_unsaved_stays_in_its_box(wo):
    """A reading typed into #6's box and left unsaved when #57 is scanned: #6's
    box keeps it, and the reading typed next goes into #57's. RED on 4ac78d0:
    it joined #6's ("300425"), and Enter saved that to #6."""
    page, open_ = wo
    open_()
    press(page, "300", 150, enter=False)
    later(page, 600)
    press(page, "ID:57", 5)
    _answered(page, 57)
    later(page, 900)
    press(page, "425", 150)
    _saved(page)
    assert [u["id"] for u in _updates(page)] == [57] and _box(page, 6) == "300"


@pytest.mark.parametrize("focused", [True, False])
def test_a_dialog_over_the_window_keeps_the_focus_when_a_scan_names_a_spool(wo, focused):
    """A spool scanned while a dialog sits over the window (the missing-tare
    prompt, here: a probe overlay), its own field focused or nothing focused:
    the list takes no focus from under it. Pins the rule above's limit (green
    on 4ac78d0 too)."""
    page, open_ = wo
    open_()
    page.evaluate("""() => window.mountOverlay({ id: 'fcc-probe-over',
        content: '<div><input id="fcc-probe-in"></div>', initialFocus: '#fcc-probe-in' })""")
    page.wait_for_function("() => document.activeElement && document.activeElement.id === 'fcc-probe-in'")
    if not focused:
        page.evaluate("() => document.activeElement.blur()")
    page.evaluate("() => window.processScan('ID:57', 'barcode')")
    _answered(page, 57)
    assert _focus(page) == ("fcc-probe-in" if focused else "BODY")


@pytest.mark.parametrize("how", ["Escape", "click", "enter"])
def test_the_focus_comes_back_after_the_tare_prompt_is_cancelled(wo, how):
    """Gross, and a spool with no empty-spool weight on record: Save asks for
    it. Cancelled (Escape, a click on Cancel, Enter on it), the focus is back in
    the row's box, and the reading typed next goes there. RED on 4ac78d0: the
    focus fell to the page, and the next reading ("8", then Enter) went to the
    scan path as spool #8, which joined the buffer unseen."""
    page, open_ = wo
    open_(held=(8, 6), mode="gross")
    press(page, "645", 150)
    prompt = "#fcc-missing-empty-weight-overlay"
    page.wait_for_function("(s) => document.activeElement === document.querySelector(s + '-input')", arg=prompt)
    if how == "Escape":
        page.keyboard.press("Escape")
    elif how == "click":
        page.locator(f"{prompt}-cancel").click()
    else:
        page.locator(f"{prompt}-cancel").focus()
        later(page, 700)
        page.keyboard.press("Enter")
    page.wait_for_function("(s) => !document.querySelector(s)", arg=prompt)
    assert _focus(page) == "8", how
    later(page, 700)
    press(page, "8", 150, enter=False)
    assert len(_box(page, 8)) == 4 and _scans(page) == [], (how, _box(page, 8))   # 645 and the 8


@pytest.mark.parametrize("how", ["later", "escape", "save", "redrawn"])
def test_the_focus_comes_back_after_the_empty_weight_prompt_closes(wo, how):
    """#8 weighed empty (0 g, Auto-Archive on) is archived, and its filament
    has no empty weight: the post-archive prompt asks for it. Closed (Later,
    Escape, or its weight saved; or Later after a heartbeat drew the list
    again under it), the focus is back in the box that had it, and the reading
    typed next goes there. RED on 4ac78d0: the focus fell to the page, and the
    next reading went to the scan path as a spool id."""
    page, open_ = wo
    open_(held=(8, 6))
    press(page, "0", 150)
    _saved(page)
    page.wait_for_function("() => document.activeElement && document.activeElement.id === 'fcc-archive-empty-wt'")
    if how == "redrawn":
        page.evaluate("() => document.dispatchEvent(new CustomEvent('inventory:buffer-updated'))")
        page.locator("#fcc-archive-later").click()
    elif how == "later":
        page.locator("#fcc-archive-later").click()
    elif how == "escape":
        page.keyboard.press("Escape")
    else:
        later(page, 300)
        press(page, "167", 150)
        page.wait_for_function("() => window.__posts.some((p) => p.url === '/api/update_filament')")
    page.wait_for_function("() => !document.getElementById('fcc-archive-empty-overlay')")
    page.wait_for_function("() => !document.querySelector('.weigh-input[data-id=\"8\"]')")   # the saved row's fade
    assert _focus(page) == "6", how
    later(page, 700)
    press(page, "5", 150, enter=False)
    assert _box(page, 6) == "5" and _scans(page) == [], how


def test_a_reading_typed_after_a_click_on_the_auto_archive_switch_goes_in_the_box(wo):
    """A click on the Auto-Archive switch (to keep an empty spool, say), then
    the reading and Enter: it goes into the box that had the focus and is
    saved. A label scanned with the focus there still reaches the scan path.
    RED on 4ac78d0: the switch blurred itself, the focus fell to the page, and
    the reading went to the scan path as a spool id."""
    page, open_ = wo
    open_()
    page.locator("#weigh-auto-archive").click()
    assert page.evaluate("() => document.getElementById('weigh-auto-archive').checked") is False
    later(page, 700)
    press(page, "500", 150)
    _saved(page)
    assert [u["id"] for u in _updates(page)] == [6] and _scans(page) == []
    page.locator("#weigh-auto-archive").click()
    later(page, 700)
    press(page, "ID:57", 5)
    _answered(page, 57)
    assert _scans(page) == ["ID:57"] and _focus(page) == "57"


def test_a_reading_typed_on_a_mode_button_goes_in_the_box(wo):
    """The person in #134's box, a click on Gross, then the reading and Enter:
    the reading goes into the box that had the focus (not the first) and is
    saved in Gross (1000 g - (645 g - 200 g) = 555 g used). RED on 4ac78d0: it
    went to the scan path as a spool id."""
    page, open_ = wo
    open_()
    page.locator(".weigh-input[data-id='134']").click()
    page.locator("#weigh-out-mode [data-mode='gross']").click()
    later(page, 700)
    press(page, "645", 150)
    _saved(page)
    ups = _updates(page)
    assert [u["id"] for u in ups] == [134] and ups[0]["updates"]["used_weight"] == 555 and _scans(page) == [], ups


def test_a_weight_typed_after_ticking_the_empty_weight_prompts_vendor_box_goes_into_its_box(wo):
    """The post-archive empty-weight prompt: its "Also set as Acme's default"
    box ticked first, then the weight typed and Enter: the weight goes into its
    box and is saved to the filament and the vendor, and nothing goes to the
    scan path. RED on 4ac78d0: the scan accumulator reads a checkbox's keys
    since round 6, so the weight went to the scan path as a spool id (#167
    joined the buffer unseen) and nothing was saved."""
    page, open_ = wo
    open_()
    page.evaluate("() => window.showArchiveEmptyWeightPrompt(8, 5, null)")
    page.wait_for_function("() => document.activeElement && document.activeElement.id === 'fcc-archive-empty-wt'")
    page.locator("#fcc-archive-propagate").click()
    assert page.evaluate("() => document.activeElement.id") == "fcc-archive-propagate"
    later(page, 700)
    press(page, "167", 150)
    page.wait_for_function("() => window.__posts.some((p) => p.url === '/api/vendors/9')", timeout=3000)
    filament = page.evaluate("() => window.__posts.filter((p) => p.url === '/api/update_filament').map((p) => p.body)")
    assert filament == [{"id": 5, "data": {"spool_weight": 167}}] and _scans(page) == [], filament


# --- Group 57 review, round 8 -------------------------------------------------
# The list keeps a target, the spool whose reading is being entered: a scan,
# a click or Tab into a box, a click on a row and the save moving on set it.
# Each test below is RED on b114fd7 unless it says it pins a limit.


@pytest.mark.parametrize("mode, used", [("net", 575), ("gross", 742)])
def test_a_spools_own_box_keeps_the_reading_typed_before_its_scan_was_answered(wo, mode, used):
    """The list opens on #6's box, the person scans #6's own label to pick it
    and starts the reading before the server has answered (a slow Spoolman):
    the reading stays whole (Net: 1000 g - 425 g = 575 g used; Gross: 1000 g -
    (425 g - 167 g) = 742 g, nothing archived). RED on b114fd7: the answer
    selected what was in the box, the '4' typed meanwhile with it, so the next
    key replaced it and 25 g was saved (in Gross, under the 167 g spool, so #6
    was archived and taken off its place)."""
    page, open_ = wo
    page.evaluate("() => { window.__holdScans = true; }")
    open_(mode=mode)
    press(page, "ID:6", 5)
    _held(page, "scan")
    later(page, 300)
    press(page, "4", 0, enter=False)          # the server hasn't answered yet
    _release(page, "scan")
    _scan_answered(page)
    later(page, 150)
    press(page, "25", 150)
    _saved(page)
    ups = _updates(page)
    assert [u["id"] for u in ups] == [6] and ups[0]["updates"] == {"used_weight": used}, ups
    assert _unassigned(page) == []


def _focus_off_a_box(page, where):
    if where == "mode button":
        page.locator("#weigh-out-mode [data-mode='net']").click()
    elif where == "switch":
        page.locator("#weigh-auto-archive").focus()
    else:                                     # the window itself, as a click on its empty space leaves it
        page.evaluate("() => document.getElementById('weighOutModal').focus()")


@pytest.mark.parametrize("where", ["mode button", "switch", "window"])
def test_a_scan_read_off_a_box_takes_the_reading_typed_before_its_answer(wo, where):
    """The focus on a mode button, the Auto-Archive switch or the window
    itself, #57's label scanned, and the reading started before the server has
    answered: the whole reading goes to #57 (750 g - 425 g = 325 g used), and
    #6's box, where the first key went meanwhile (the target's), is empty
    again. RED on b114fd7: the '4' stayed in #6's box and 25 g was saved to
    #57."""
    page, open_ = wo
    page.evaluate("() => { window.__holdScans = true; }")
    open_()
    _focus_off_a_box(page, where)
    later(page, 700)
    press(page, "ID:57", 5)
    _held(page, "scan")
    later(page, 300)
    press(page, "4", 0, enter=False)
    _release(page, "scan")
    _scan_answered(page)
    assert (_focus(page), _box(page, 57), _box(page, 6)) == ("57", "4", ""), where
    later(page, 150)
    press(page, "25", 150)
    _saved(page)
    ups = _updates(page)
    assert [u["id"] for u in ups] == [57] and ups[0]["updates"]["used_weight"] == 325, (where, ups)


def test_enter_before_a_scan_is_answered_saves_nothing(wo):
    """The whole reading and Enter typed before the server has answered #57's
    scan, the focus on a mode button: nothing is saved then (a toast says to
    press Enter again), and once the answer is in, the reading is in #57's box
    and Enter saves it there. RED on b114fd7: the reading went into #6's box,
    and Enter saved it to #6."""
    page, open_ = wo
    page.evaluate("() => { window.__holdScans = true; }")
    open_()
    page.locator("#weigh-out-mode [data-mode='net']").click()
    later(page, 700)
    press(page, "ID:57", 5)
    _held(page, "scan")
    later(page, 300)
    press(page, "425", 150)                   # with its Enter, before the answer
    page.wait_for_timeout(50)
    assert _updates(page) == []
    _release(page, "scan")
    _scan_answered(page)
    assert (_focus(page), _box(page, 57), _box(page, 6)) == ("57", "425", "")
    later(page, 300)
    press(page, "", 0)                        # Enter
    _saved(page)
    ups = _updates(page)
    assert [u["id"] for u in ups] == [57] and ups[0]["updates"]["used_weight"] == 325, ups


def test_a_reading_typed_before_a_scan_is_answered_on_an_empty_list_is_kept_for_it(wo):
    """The list opened empty (the focus on the window, as Bootstrap leaves it),
    #57's label scanned, and the reading started before the answer: the first
    key is kept for #57, and its box takes the whole reading (325 g used).
    RED on b114fd7: the '4' stayed in the scan buffer, and 25 g was saved."""
    page, _ = wo
    page.evaluate("() => { window.__holdScans = true; }")
    page.evaluate(SETUP, [])
    page.evaluate("() => { window.weighOutMode = 'net'; window.openWeighOutModal(); }")
    page.evaluate("() => document.getElementById('weighOutModal').focus()")
    later(page, 700)
    press(page, "ID:57", 5)
    _held(page, "scan")
    later(page, 300)
    press(page, "4", 0, enter=False)
    _release(page, "scan")
    _scan_answered(page)
    # ... and nowhere else: a key left in the scan buffer would join the next scan.
    assert (_focus(page), _box(page, 57), page.evaluate("() => state.scanBuffer")) == ("57", "4", "")
    later(page, 150)
    press(page, "25", 150)
    _saved(page)
    ups = _updates(page)
    assert [u["id"] for u in ups] == [57] and ups[0]["updates"]["used_weight"] == 325, ups


@pytest.mark.parametrize("scanned, early", [(57, False), (134, False), (57, True)])
def test_a_spool_scanned_over_the_empty_weight_prompt_closes_it_and_takes_the_reading(wo, scanned, early):
    """Empties weighed in Net: #8 at 0 g is archived, and the empty-weight
    prompt asks for its filament's empty spool weight, its box focused. The
    person scans the next spool instead (#57, new, or #134, listed) and types
    its reading: the prompt closes (Later), the scanned spool's box takes the
    focus, and the reading is saved to it, never as an empty weight. A first
    key typed into the prompt's box before the answer goes along. RED on
    b114fd7: the prompt stayed up, its box took the reading (Enter saved it as
    the filament's empty weight), and once it closed the focus came back to
    #6's box."""
    page, open_ = wo
    open_(held=(8, 6, 134))
    press(page, "0", 150)
    _saved(page)
    page.wait_for_function("() => document.activeElement && document.activeElement.id === 'fcc-archive-empty-wt'")
    if early:
        page.evaluate("() => { window.__holdScans = true; }")
    later(page, 700)
    press(page, f"ID:{scanned}", 5)
    if early:
        _held(page, "scan")
        later(page, 300)
        press(page, "4", 0, enter=False)
        _release(page, "scan")
    _scan_answered(page)
    assert page.locator("#fcc-archive-empty-overlay").count() == 0 and _focus(page) == str(scanned)
    later(page, 150)
    press(page, "25" if early else "425", 150)
    _saved(page, 2)
    ups = _updates(page)
    used = {57: 325, 134: 575}[scanned]
    assert [u["id"] for u in ups] == [8, scanned] and ups[1]["updates"]["used_weight"] == used, ups
    assert _filament_writes(page) == 0


def test_a_spool_scanned_over_the_missing_tare_prompt_cancels_it(wo):
    """Gross, and #8 with no empty spool weight on record: Enter asks for it.
    The person scans the next spool (#57) instead and types its reading: the
    prompt is cancelled (a warning says #8 wasn't saved), #57's box takes the
    focus, and the reading is saved to #57 (750 g - (425 g - 150 g) = 475 g
    used); nothing is saved to #8. RED on b114fd7: the prompt stayed up, the
    reading went into its box as #8's tare, and Enter saved #8 with it."""
    page, open_ = wo
    open_(held=(8, 6), mode="gross")
    press(page, "645", 150)
    prompt = "#fcc-missing-empty-weight-overlay"
    page.wait_for_function("(s) => document.activeElement === document.querySelector(s + '-input')", arg=prompt)
    later(page, 700)
    press(page, "ID:57", 5)
    _scan_answered(page)
    assert page.locator(prompt).count() == 0 and _focus(page) == "57"
    assert any("#8 wasn't saved" in t for t in _toasts(page)), _toasts(page)
    later(page, 150)
    press(page, "425", 150)
    _saved(page)
    ups = _updates(page)
    assert [u["id"] for u in ups] == [57] and ups[0]["updates"]["used_weight"] == 475, ups


def test_the_tare_prompt_isnt_opened_once_the_next_spool_is_scanned(wo):
    """Gross, #8 with no empty spool weight on record, and its details still
    being read (a slow Spoolman) when Enter is pressed; meanwhile the next
    spool, #57, is scanned: no prompt asks for #8's tare once its details are
    in (a warning says #8 wasn't saved), and #57's box keeps the focus for its
    reading. RED on b114fd7: the prompt opened over the list and took the
    focus, so #57's reading went into its box as #8's tare."""
    page, open_ = wo
    page.evaluate("() => { window.__detailsMs = 800; }")
    open_(held=(8, 6), mode="gross")
    press(page, "645", 150)                   # its Enter: #8's details aren't in yet
    page.evaluate("() => window.processScan('ID:57', 'barcode')")
    _scan_answered(page)
    assert _focus(page) == "57"
    page.wait_for_timeout(1200)               # #8's details are in
    assert page.locator("#fcc-missing-empty-weight-overlay").count() == 0 and _focus(page) == "57"
    assert any("#8 wasn't saved" in t for t in _toasts(page)), _toasts(page)
    assert _updates(page) == []


@pytest.mark.parametrize("typed, remaining", [("645g", 645), ("6,45", None)])
def test_with_no_details_a_reading_is_still_read_as_grams(wo, typed, remaining):
    """A spool whose details can't be read (the save then sends the reading as
    what is left on the spool): a reading in grams with its unit is saved as
    645 g left; a decimal comma is refused, with nothing saved. Pins the
    strict read on that path too."""
    page, open_ = wo
    page.evaluate("() => { window.__detailsFail = true; }")
    open_()
    press(page, typed, 150)
    page.wait_for_timeout(150)
    ups = _updates(page)
    assert [u["updates"].get("remaining_weight") for u in ups] == ([remaining] if remaining else []), (typed, ups)


def test_the_empty_weight_prompt_isnt_opened_once_the_next_spool_is_scanned(wo):
    """#8 weighed empty (0 g) is archived, and before its empty-weight prompt
    opens (400 ms later, after it reads the filament) the next spool, #57, is
    scanned: the prompt isn't opened, and #57's box keeps the focus for its
    reading. RED on b114fd7: the prompt opened over the list after the scan and
    took the focus, so #57's reading went into its box as the filament's empty
    weight."""
    page, open_ = wo
    page.evaluate("() => { window.__filamentMs = 600; }")
    open_(held=(8, 6))
    press(page, "0", 150)
    _saved(page)
    page.evaluate("() => window.processScan('ID:57', 'barcode')")
    _scan_answered(page)
    page.wait_for_timeout(1300)
    assert page.locator("#fcc-archive-empty-overlay").count() == 0 and _focus(page) == "57"
    later(page, 700)
    press(page, "425", 150)
    _saved(page, 2)
    assert [u["id"] for u in _updates(page)] == [8, 57] and _filament_writes(page) == 0


@pytest.mark.parametrize("when", ["faded", "fading", "saving"])
def test_a_spool_weighed_this_session_scanned_again_takes_the_reading(wo, when):
    """#6 saved (500 g) and then scanned again to weigh it again (a misread),
    once its row has faded away, while it fades, or while its save is still on
    its way: its row is drawn again and its box takes the focus, so the new
    reading is saved to #6 (1000 g - 480 g = 520 g used), never to #134, whose
    box the save moved the focus to. RED on b114fd7: "Already in Buffer", and
    the reading was saved to #134."""
    page, open_ = wo
    open_()
    if when == "saving":
        page.evaluate("() => { window.__holdSaves = true; }")
    press(page, "500", 150)
    page.wait_for_function("() => window.__posts.some((p) => p.url === '/api/spool/update')")
    if when == "faded":
        page.wait_for_function("() => !document.querySelector('.weigh-input[data-id=\"6\"]')")
    if when == "fading":
        page.wait_for_timeout(40)                 # landed: its row's 300 ms fade has begun
    listed = page.evaluate("""() => { window.__answerMs = 0;
        const listed = !!document.querySelector('.weigh-row[data-id="6"]');
        window.processScan('ID:6', 'barcode'); return listed; }""")
    if when == "fading" and not listed:
        pytest.skip("the row's fade ended before the scan (a slow machine)")
    _scan_answered(page)
    if when == "saving":
        assert _focus(page) not in ("6", "134")   # no other spool's box keeps it meanwhile,
        press(page, "4", 0, enter=False)          # nor takes a key typed then
        assert _box(page, 134) == ""
        page.evaluate("() => window.clearScanBuffer()")
        page.evaluate("() => { window.__holdSaves = false; }")
        _release(page, "save")                # its save lands now
        page.wait_for_function("() => { const b = document.querySelector('.weigh-input[data-id=\"6\"]'); return b && !b.disabled; }")
    page.wait_for_timeout(450)                    # past the 300 ms fade the scan stops
    assert _focus(page) == "6" and _box(page, 6) == "", when
    later(page, 700)
    press(page, "480", 150)
    _saved(page, 2)
    ups = _updates(page)
    assert [u["id"] for u in ups] == [6, 6] and ups[1]["updates"]["used_weight"] == 520, (when, ups)


def test_a_decimal_point_survives_a_redraw(wo):
    """'645.' typed, then the list drawn again (a heartbeat that changed a
    spool does that), then '5' and Enter: 645.5 g is saved (1000 g - 645.5 g =
    354.5 g used). RED on b114fd7: a number box reads '645.' as 645, the
    redraw kept 645, and 6455 was saved (Net: 0 g used; in Set Used the spool
    read empty and was archived)."""
    page, open_ = wo
    open_()
    press(page, "645.", 150, enter=False)
    page.evaluate("() => document.dispatchEvent(new CustomEvent('inventory:buffer-updated'))")
    assert (_focus(page), _box(page, 6)) == ("6", "645.")
    later(page, 150)
    press(page, "5", 150)
    _saved(page)
    assert _updates(page)[0]["updates"]["used_weight"] == 354.5


@pytest.mark.parametrize("typed, used", [("6,45", None), ("0.645kg", None), ("645 g", 355), ("645g", 355), (" 645", 355)])
def test_a_weigh_out_box_saves_only_grams(wo, typed, used):
    """A reading typed by hand: in grams, with or without its unit or a blank
    in front, it is saved (1000 g - 645 g = 355 g used); a decimal comma or a
    kilogram reading is refused, with nothing saved and the box still holding
    it. RED on b114fd7 for the refusals: a number box kept only the digits, and
    saved "6,45" as 645 g and "0.645kg" as 0.645 g."""
    page, open_ = wo
    open_()
    press(page, typed, 150)
    page.wait_for_timeout(150)
    ups = _updates(page)
    if used is None:
        assert ups == [] and (_focus(page), _box(page, 6)) == ("6", typed), (typed, ups)
    else:
        assert [u["updates"]["used_weight"] for u in ups] == [used], (typed, ups)


@pytest.mark.parametrize("where", ["name", "current", "save button"])
def test_a_reading_typed_after_a_click_on_another_row_goes_in_that_row(wo, where):
    """#6's box has the focus; the person clicks #134's row (its name, its
    "Current" line, or its 💾 with its box empty) and types the reading: it
    goes into #134's box and is saved to #134 (1000 g - 425 g = 575 g used).
    RED on b114fd7: the focus went to the window (or the 💾), and the reading
    went into #6's box, which had had the focus, and was saved to #6."""
    page, open_ = wo
    open_()
    row = page.locator(".weigh-row[data-id='134']")
    if where == "name":
        row.locator(".fw-bold").click()
    elif where == "current":
        row.locator(".text-white-50").click()
    else:
        row.locator(".weigh-save-btn").click()
    later(page, 700)
    press(page, "425", 150)
    _saved(page)
    ups = _updates(page)
    assert [u["id"] for u in ups] == [134] and ups[0]["updates"]["used_weight"] == 575, (where, ups)


def test_a_spool_scanned_under_another_window_gets_the_focus_when_it_closes(wo):
    """A window over the list (a stand-in for one of Bootstrap's: the filament
    details, say) with its own field focused, and #57 scanned: the focus stays
    in that window (pins the guard); when it closes, #57's box takes it, and
    the reading typed then is saved to #57 (325 g used). RED on b114fd7: when
    it closed the focus went nowhere, and the reading went to the scan path as
    a spool id."""
    page, open_ = wo
    open_()
    page.evaluate("""() => { const m = document.createElement('div'); m.className = 'modal show'; m.id = 'fccProbeModal';
        m.innerHTML = '<input id="fcc-probe-in">'; document.body.appendChild(m);
        document.getElementById('fcc-probe-in').focus(); }""")
    page.evaluate("() => window.processScan('ID:57', 'barcode')")
    _answered(page, 57)
    assert _focus(page) == "fcc-probe-in"
    page.evaluate("""() => { const m = document.getElementById('fccProbeModal');
        m.classList.remove('show'); m.style.display = 'none';
        m.dispatchEvent(new Event('hidden.bs.modal', { bubbles: true })); }""")
    assert _focus(page) == "57"
    later(page, 700)
    press(page, "425", 150)
    _saved(page)
    ups = _updates(page)
    assert [u["id"] for u in ups] == [57] and ups[0]["updates"]["used_weight"] == 325, ups


def test_a_weighed_spool_scanned_again_under_another_window_gets_its_box_when_it_closes(wo):
    """#6 saved and its row faded away; a window over the list, and #6 scanned
    again (to weigh it again): when the window closes, #6's row is back and its
    box takes the focus, so the new reading is saved to #6 (520 g used), never
    to #134, the only other box. RED on b114fd7 (the reading went to #134), and
    on a fix that drew the row again only when nothing covered the list."""
    page, open_ = wo
    open_()
    press(page, "500", 150)
    _saved(page)
    page.wait_for_function("() => !document.querySelector('.weigh-input[data-id=\"6\"]')")   # faded
    page.evaluate("""() => { const m = document.createElement('div'); m.className = 'modal show'; m.id = 'fccProbeModal';
        m.innerHTML = '<input id="fcc-probe-in">'; document.body.appendChild(m);
        document.getElementById('fcc-probe-in').focus(); }""")
    page.evaluate("() => window.processScan('ID:6', 'barcode')")
    _scan_answered(page)
    assert _focus(page) == "fcc-probe-in"
    page.evaluate("""() => { const m = document.getElementById('fccProbeModal');
        m.classList.remove('show'); m.style.display = 'none';
        m.dispatchEvent(new Event('hidden.bs.modal', { bubbles: true })); }""")
    assert (_focus(page), _box(page, 6)) == ("6", "")
    later(page, 700)
    press(page, "480", 150)
    _saved(page, 2)
    ups = _updates(page)
    assert [u["id"] for u in ups] == [6, 6] and ups[1]["updates"]["used_weight"] == 520, ups


def test_a_box_moved_to_while_a_scan_is_answered_keeps_what_was_typed_there(wo):
    """#57 scanned from #6's box, and while the answer is on its way the person
    moves to #134's box and types there: that stays in #134's box (they went
    there on purpose), and #57's box takes the focus empty. Pins the move's
    limit: only what was typed where the focus was as the scan went out, or in
    the target's box, goes with the scan."""
    page, open_ = wo
    page.evaluate("() => { window.__holdScans = true; }")
    open_()
    press(page, "ID:57", 5)
    _held(page, "scan")
    later(page, 300)
    page.locator(".weigh-input[data-id='134']").focus()
    press(page, "9", 0, enter=False)
    _release(page, "scan")
    _scan_answered(page)
    assert (_focus(page), _box(page, 134), _box(page, 57)) == ("57", "9", "")


def test_a_reading_edited_in_the_old_box_while_a_scan_is_answered_stays_there(wo):
    """A reading left in #6's box ('300'), #57 scanned into it, and while the
    answer is on its way the person edits #6's reading (Backspace, then more
    digits): an edit, not an addition, so it stays in #6's box as typed, and
    #57's box takes the focus empty. Pins the move's other limit."""
    page, open_ = wo
    page.evaluate("() => { window.__holdScans = true; }")
    open_()
    press(page, "300", 150, enter=False)
    later(page, 600)
    press(page, "ID:57", 5)
    _held(page, "scan")
    later(page, 300)
    press(page, ["Backspace", "4", "2", "5", "1"], 150, enter=False)
    _release(page, "scan")
    _scan_answered(page)
    assert (_focus(page), _box(page, 6), _box(page, 57)) == ("57", "304251", "")


def test_a_weight_key_on_a_control_never_goes_to_a_guessed_box(wo):
    """The target's spool taken out of the buffer, two spools left: a reading
    typed on a mode button goes into neither box (to the scan path, as before
    Group 57), never into one picked by guess; with one spool left, it goes
    into that one's box and is saved. RED on b114fd7: it went into the first
    empty box."""
    page, open_ = wo
    open_(held=(6, 134, 57))
    drop = "(id) => { state.heldSpools = state.heldSpools.filter((s) => s.id !== id); renderBuffer(); }"
    page.evaluate(drop, 6)
    page.locator("#weigh-out-mode [data-mode='net']").click()
    later(page, 700)
    press(page, "425", 150)
    page.wait_for_function("() => window.__posts.some((p) => ['/api/identify_scan', '/api/spool/update'].includes(p.url))")
    page.wait_for_timeout(50)
    assert _updates(page) == [] and _scans(page) == ["425"] and (_box(page, 134), _box(page, 57)) == ("", "")
    _scan_answered(page)                          # the scan path answered it (Unknown Code)
    page.evaluate(drop, 57)
    page.locator("#weigh-out-mode [data-mode='net']").click()
    later(page, 700)
    press(page, "425", 150)
    _saved(page)
    assert [u["id"] for u in _updates(page)] == [134]


def test_only_the_latest_scan_moves_the_focus(wo):
    """Two spools scanned back to back, the first answered last (#57 slow,
    then #134): the focus ends in #134's box, the spool scanned last, and the
    reading is saved to it. RED on b114fd7: #57's late answer moved the focus
    to #57's box."""
    page, open_ = wo
    page.evaluate("() => { window.__holdScans = ['ID:57']; }")
    open_()
    press(page, "ID:57", 5)
    _held(page, "scan")
    later(page, 300)
    press(page, "ID:134", 5)
    _scan_answered(page, 1)
    assert _focus(page) == "134"
    _release(page, "scan")                    # #57's answer comes last
    _scan_answered(page, 2)
    assert _focus(page) == "134"
    later(page, 700)
    press(page, "425", 150)
    _saved(page)
    assert [u["id"] for u in _updates(page)] == [134]
