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
// Answers held until the test lets them go (window.__release('scan' | 'save' |
// 'details' | 'filament'), so a test that types "before the answer" never races
// a timer: __holdScans is true (every scan) or a list of scan texts,
// __holdSaves and __holdFilament true or false, __holdDetails true or a list
// of spool ids (one let go with __releaseDetails(id)).
window.__holdScans = false;
window.__holdSaves = false;
window.__holdDetails = false;        // /api/spool_details, the open's own read included (__release('details'))
window.__holdFilament = false;       // /api/filament_details (the empty-weight prompt's first read)
window.__held = { scan: [], save: [], details: [], filament: [] };
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
    // A save lands on the spool's record, so a re-read gives what it saved.
    const saved = url.includes('/api/spool/update') ? window.__spools[body.id] : null;
    if (saved && body.updates.used_weight != null) saved.used_weight = body.updates.used_weight;
    else if (saved && body.updates.remaining_weight != null) saved.used_weight = saved.initial_weight - body.updates.remaining_weight;
    if (url.includes('/api/identify_scan')) {
        // A spool's label, or a bare number, which the server reads as a spool
        // id first (logic.resolve_scan).
        const s = /^(?:ID:)?(\d+)$/.exec(body.text);
        ans = s && window.__rows[s[1]] ? Object.assign({ type: 'spool' }, window.__rows[s[1]])
            : { type: 'error', msg: 'Unknown Code' };
    }
    const scan = url.includes('/api/identify_scan');
    const ms = scan ? (body.text in window.__answerMsFor ? window.__answerMsFor[body.text] : window.__answerMs)
        : url.includes('/api/spool/update') ? window.__saveMs
        : url.includes('/api/filament_details') ? window.__filamentMs
        : url.includes('/api/spool_details') ? window.__detailsMs : 0;
    const save = url.includes('/api/spool/update');
    const details = url.includes('/api/spool_details');
    const fil = url.includes('/api/filament_details');
    const detailsId = details ? Number((/spool_details\?id=(\d+)/.exec(url) || [])[1]) : null;
    const held = scan ? (window.__holdScans === true
        || (Array.isArray(window.__holdScans) && window.__holdScans.includes(body.text)))
        : save ? window.__holdSaves : fil ? window.__holdFilament : (details && (window.__holdDetails === true
            || (Array.isArray(window.__holdDetails) && window.__holdDetails.includes(detailsId))));
    return new Promise((res) => {
        const answer = () => {
            if (scan) window.__answeredScans += 1;
            res({ ok: true, status: 200, json: () => Promise.resolve(ans) });
        };
        answer.sid = detailsId;
        if (held) window.__held[scan ? 'scan' : save ? 'save' : fil ? 'filament' : 'details'].push(answer);
        else setTimeout(answer, ms);
    });
};
// One spool's held details (__holdDetails a list of spool ids) let go.
window.__releaseDetails = (id) => {
    const go = window.__held.details.filter((f) => f.sid === id);
    window.__held.details = window.__held.details.filter((f) => f.sid !== id);
    go.forEach((f) => f());
};
window.__si = window.setInterval; window.setInterval = () => 0;   // inv_cmd.js's 2 s buffer poll: off
"""

# A saved row's 300 ms fade held until the test runs it (__runFades) or lets
# the page's timers go back to normal (__unholdFades): a toast's removal, the
# only other 300 ms timer, is held with it.
HOLD_FADES = r"""() => {
    const st = window.setTimeout, ct = window.clearTimeout;
    window.__fades = new Map(); let n = 900000;
    window.setTimeout = (f, ms, ...a) => { if (ms !== 300) return st(f, ms, ...a); n += 1; window.__fades.set(n, f); return n; };
    window.clearTimeout = (id) => { if (window.__fades.has(id)) window.__fades.delete(id); else ct(id); };
    window.__runFades = () => { const fs = Array.from(window.__fades.values()); window.__fades.clear(); fs.forEach((f) => f()); };
    window.__unholdFades = () => { window.setTimeout = st; window.clearTimeout = ct; };
}"""

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
    page.evaluate("() => { window.__holdDetails = true; }")
    open_(held=(8, 6), mode="gross")
    press(page, "645", 150)                   # its Enter: #8's details aren't in yet
    page.evaluate("() => window.processScan('ID:57', 'barcode')")
    _scan_answered(page)
    assert _focus(page) == "57"
    page.evaluate("() => { window.__holdDetails = false; }")
    _release(page, "details")                 # #8's details are in
    page.wait_for_timeout(300)
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
    box the save moved the focus to. A key typed while its save is on its way
    is kept for it and is in its box once that has landed. RED on b114fd7:
    "Already in Buffer", and the reading was saved to #134. Round 9 (RED on
    66f2c44): the key typed while it saved went to the scan path, and the scan
    buffer took it."""
    page, open_ = wo
    open_()
    if when == "saving":
        page.evaluate("() => { window.__holdSaves = true; }")
    if when == "fading":
        # Its row's fade held: the scan comes while it fades, on any machine
        # (it skipped itself when the fade had ended first).
        page.evaluate(HOLD_FADES)
    press(page, "500", 150)
    page.wait_for_function("() => window.__posts.some((p) => p.url === '/api/spool/update')")
    if when == "faded":
        page.wait_for_function("() => !document.querySelector('.weigh-input[data-id=\"6\"]')")
    if when == "fading":
        page.wait_for_function("() => window.__fades.size >= 1")      # landed: its fade has begun
        page.evaluate("() => window.__unholdFades()")
    listed = page.evaluate("""() => { window.__answerMs = 0;
        const listed = !!document.querySelector('.weigh-row[data-id="6"]');
        window.processScan('ID:6', 'barcode'); return listed; }""")
    assert listed == (when != "faded"), when
    _scan_answered(page)
    if when == "saving":
        assert _focus(page) not in ("6", "134")   # no other spool's box keeps it meanwhile,
        press(page, "4", 0, enter=False)          # nor takes a key typed then: it is kept for #6
        assert (_box(page, 134), page.evaluate("() => state.scanBuffer")) == ("", "")
        page.evaluate("() => { window.__holdSaves = false; }")
        _release(page, "save")                # its save lands now
        page.wait_for_function("() => { const b = document.querySelector('.weigh-input[data-id=\"6\"]'); return b && !b.disabled; }")
    page.wait_for_timeout(450)                    # past the 300 ms fade the scan stops
    assert _focus(page) == "6" and _box(page, 6) == ("4" if when == "saving" else ""), when
    later(page, 700)
    press(page, "80" if when == "saving" else "480", 150)
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
    reading is saved to it, Enter not waiting for #57's answer (it can no
    longer take the focus). RED on b114fd7: #57's late answer moved the focus
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
    later(page, 700)
    press(page, "425", 150)                   # and Enter, #57's answer still out
    _saved(page)
    assert _focus(page) == "6"                # the save moved it on
    _release(page, "scan")                    # #57's answer comes last
    _scan_answered(page, 2)
    assert _focus(page) == "6" and [u["id"] for u in _updates(page)] == [134]


def test_a_digits_only_label_scanned_into_a_weigh_out_box_goes_to_the_scan_path(wo):
    """#6's box holding a reading typed by hand ('300'), and an old
    digits-only label ("134") scanned into it: the label goes to the scan
    path, #6's box keeps '300', and nothing is saved (Derek, 2026-10-28). The
    server reads a bare number as a spool id, so #134 is the spool scanned and
    its box takes the focus, as any scanned spool's does (round 9: the docs
    said nothing happens). RED on e74350f: the digits joined the reading
    ("300134"), and Enter saved that to #6."""
    page, open_ = wo
    open_()
    press(page, "300", 150, enter=False)
    later(page, 600)
    press(page, "134", 5)
    page.wait_for_function("() => window.__posts.some((p) => p.url === '/api/identify_scan')")
    _scan_answered(page)
    assert (_scans(page), _box(page, 6), _updates(page), _focus(page)) == (["134"], "300", [], "134")


def test_a_digits_only_label_scanned_while_a_scan_is_answered_is_a_scan(wo):
    """The list empty, #57's label scanned and its answer on its way, a key
    typed by hand ('4', held for #57's reading), and then an old digits-only
    label ("1024") scanned: the label's keys, closer together than a person
    types, go to the scan path whole (after #57's answer, as the scan
    accumulator queues a scan while one is answered), and #57's box gets the
    person's '4' alone. RED on e74350f: the label was held as #57's reading
    too, its box took "41024", and the label never reached the scan path."""
    page, _ = wo
    page.evaluate("() => { window.__holdScans = ['ID:57']; }")
    page.evaluate(SETUP, [])
    page.evaluate("() => { window.weighOutMode = 'net'; window.openWeighOutModal(); }")
    page.evaluate("() => document.getElementById('weighOutModal').focus()")
    later(page, 700)
    press(page, "ID:57", 5)
    _held(page, "scan")
    later(page, 300)
    press(page, "4", 0, enter=False)
    later(page, 600)
    press(page, "1024", 5)
    _release(page, "scan")
    page.wait_for_function("() => window.__posts.filter((p) => p.url === '/api/identify_scan').length >= 2",
                           timeout=5000)
    _scan_answered(page, 2)
    assert (_scans(page), _box(page, 57), page.evaluate("() => state.scanBuffer")) == (["ID:57", "1024"], "4", "")


# --- Group 57 review, round 9 -------------------------------------------------
# Each test below is RED on 66f2c44 unless it says it pins a limit. A slow
# Spoolman is the premise throughout: the answers are held until the test lets
# them go.


@pytest.mark.parametrize("prompt", ["tare", "empty"])
def test_a_prompts_save_waits_while_a_scan_is_answered(wo, prompt):
    """A prompt over the list (Gross: #8's missing tare; Net: #8 weighed empty,
    its filament's empty weight), and the next spool, #57, scanned into its
    box; while the answer is on its way the person types #57's reading and
    Enter there. Nothing is saved then; once the answer is in, the prompt has
    closed, #57's box holds the reading, and Enter saves it to #57 (Gross: 750
    g - (425 g - 150 g) = 475 g used; Net: 325 g). RED on 66f2c44: the prompt's
    Enter saved #57's reading as #8's tare (#8: 780 g used) or as the
    filament's empty weight, which every later spool of it inherits."""
    page, open_ = wo
    if prompt == "tare":
        open_(held=(8, 6), mode="gross")
        press(page, "645", 150)
        box, overlay = "#fcc-missing-empty-weight-overlay-input", "#fcc-missing-empty-weight-overlay"
    else:
        open_(held=(8, 6, 134))
        press(page, "0", 150)
        _saved(page)
        box, overlay = "#fcc-archive-empty-wt", "#fcc-archive-empty-overlay"
    page.wait_for_function("(s) => document.activeElement === document.querySelector(s)", arg=box)
    page.evaluate("() => { window.__holdScans = true; }")
    later(page, 700)
    press(page, "ID:57", 5)
    _held(page, "scan")
    later(page, 300)
    press(page, "425", 150)                   # and Enter, in the prompt, before the answer
    page.wait_for_timeout(100)
    before = [u["id"] for u in _updates(page)]
    assert (before, _filament_writes(page)) == ([] if prompt == "tare" else [8], 0), prompt
    _release(page, "scan")
    _scan_answered(page)
    assert page.locator(overlay).count() == 0 and (_focus(page), _box(page, 57)) == ("57", "425"), prompt
    later(page, 300)
    press(page, "", 0)                        # Enter
    _saved(page, len(before) + 1)
    ups = _updates(page)
    used = 475 if prompt == "tare" else 325
    assert ups[len(before):] == [{"id": 57, "updates": {"used_weight": used}}] and _filament_writes(page) == 0, ups


@pytest.mark.parametrize("prompt", ["tare", "empty"])
def test_a_prompt_doesnt_open_while_a_scan_is_answered(wo, prompt):
    """#8's prompt is due (Gross: its details still being read when Enter is
    pressed, then its missing tare; Net: weighed empty, its empty-weight prompt
    opening after the save) when the next spool, #57, is scanned and its answer
    is slow: the prompt waits for the answer, which names a spool, so it never
    opens, and the reading typed meanwhile is saved to #57. RED on 66f2c44: the
    prompt opened over the scan and took the focus, and its Enter saved #57's
    reading as #8's tare or as the filament's empty weight."""
    page, open_ = wo
    if prompt == "tare":
        page.evaluate("() => { window.__holdDetails = true; }")
        open_(held=(8, 6), mode="gross")
        press(page, "645", 150)                   # its Enter: #8's details aren't in yet
    else:
        page.evaluate("() => { window.__holdFilament = true; }")
        open_(held=(8, 6, 134))
        press(page, "0", 150)
        _saved(page)
    page.evaluate("() => { window.__holdScans = true; window.processScan('ID:57', 'barcode'); }")
    _held(page, "scan")
    if prompt == "tare":
        page.evaluate("() => { window.__holdDetails = false; }")
        _release(page, "details")                 # #8's details are in: its prompt is due
        page.wait_for_timeout(300)
    else:
        # The empty-weight prompt's first read, held: it is due once let go
        # (round 11: a 1.3 s wait raced its read on a busy machine).
        _held(page, "filament")
        page.evaluate("() => { window.__holdFilament = false; }")
        _release(page, "filament")
        page.wait_for_timeout(300)
    assert page.locator("[data-overlay-mount='1']").count() == 0, prompt
    later(page, 700)
    press(page, "425", 150)                       # and Enter: held off until the answer
    _release(page, "scan")
    _scan_answered(page)
    page.wait_for_timeout(200)
    assert page.locator("[data-overlay-mount='1']").count() == 0 and (_focus(page), _box(page, 57)) == ("57", "425")
    later(page, 300)
    press(page, "", 0)
    saved_before = 0 if prompt == "tare" else 1
    _saved(page, saved_before + 1)
    ups = _updates(page)
    used = 475 if prompt == "tare" else 325
    assert ups[saved_before:] == [{"id": 57, "updates": {"used_weight": used}}] and _filament_writes(page) == 0, ups


def test_a_save_that_reads_its_details_first_moves_the_focus_on_at_once(wo):
    """#6's details still being read (a slow Spoolman) when its reading is
    entered: its row waits, disabled, and the focus moves on at once, as any
    save's does; #57, scanned meanwhile, takes the focus, and when #6's save
    goes out at last the focus stays in #57's box, so #57's reading is saved to
    #57 (325 g used). RED on 66f2c44: the focus stayed in #6's box until its
    details came, then jumped to the box after it, and the rest of #57's
    reading was saved there."""
    page, open_ = wo
    page.evaluate("() => { window.__holdDetails = true; }")
    open_()
    press(page, "500", 150)                       # #6's details aren't in yet
    disabled = page.evaluate("() => document.querySelector('.weigh-input[data-id=\"6\"]').disabled")
    assert (_focus(page), disabled) == ("134", True)
    later(page, 700)
    press(page, "ID:57", 5)
    _answered(page, 57)
    assert _focus(page) == "57"
    later(page, 600)
    press(page, "4", 0, enter=False)
    page.evaluate("() => { window.__holdDetails = false; }")
    _release(page, "details")
    _saved(page)                                  # #6's, once its details are in
    assert (_focus(page), _box(page, 57)) == ("57", "4")
    later(page, 150)
    press(page, "25", 150)
    _saved(page, 2)
    ups = _updates(page)
    assert ups == [{"id": 6, "updates": {"used_weight": 500}}, {"id": 57, "updates": {"used_weight": 325}}], ups


def test_after_the_last_box_is_saved_a_reading_typed_before_the_next_answer_is_kept_for_it(wo):
    """The list's only spool, #6, saved: the window keeps the focus, not the
    page. #57 scanned next, while #6's row still fades, and its reading typed
    before the answer: it is kept for #57 (not in #6's fading box) and goes in
    #57's box, and Enter saves it there (325 g used). RED on 66f2c44: the focus
    fell to the page, the reading went to the scan path as a spool id, and
    #57's box was empty. Round 10: the fade is held (the test raced it), and
    on 2942ba1 the reading went in #6's fading box, to vanish with the row."""
    page, open_ = wo
    page.evaluate(HOLD_FADES)
    open_(held=(6,))
    press(page, "500", 150)
    _saved(page)
    page.wait_for_function("() => window.__fades.size >= 1")      # #6's row fades, held
    assert _focus(page) == "weighOutModal"
    page.evaluate("() => { window.__holdScans = true; }")
    later(page, 700)
    press(page, "ID:57", 5)
    _held(page, "scan")
    later(page, 300)
    press(page, "425", 150)
    page.wait_for_timeout(50)
    assert (_box(page, 6), _updates(page)) == ("500", [{"id": 6, "updates": {"used_weight": 500}}])
    _release(page, "scan")
    _scan_answered(page)
    assert (_focus(page), _box(page, 57), _scans(page)) == ("57", "425", ["ID:57"])
    later(page, 300)
    press(page, "", 0)
    _saved(page, 2)
    assert _updates(page)[1] == {"id": 57, "updates": {"used_weight": 325}}


@pytest.mark.parametrize("mode, typed", [("additive", "+25"), ("set_used", "0"), ("gross", "645")])
def test_with_no_details_another_modes_reading_is_never_saved_as_grams_left(wo, mode, typed):
    """A spool whose details can't be read, in a mode whose reading needs them:
    nothing is saved (a warning says so), and the reading stays in its box for
    another try. Net's reading is what is left, which the save can send as it
    is (test_with_no_details_a_reading_is_still_read_as_grams). RED on
    66f2c44: the reading was saved as what is left whatever the mode (Additive
    '+25' as 25 g left; Set Used '0' as an empty spool, archived and taken off
    its place; Gross 645 g, the spool's own weight counted as filament)."""
    page, open_ = wo
    page.evaluate("() => { window.__detailsFail = true; }")
    open_(mode=mode)
    press(page, typed, 150)
    page.wait_for_timeout(200)
    assert (_updates(page), _unassigned(page), _box(page, 6)) == ([], [], typed), mode
    assert any("Couldn't read #6's details" in t for t in _toasts(page)), _toasts(page)


@pytest.mark.parametrize("mode, used", [("net", 575), ("set_used", 425)])
def test_a_reading_left_in_a_spools_own_box_is_replaced_by_the_one_typed_before_its_answer(wo, mode, used):
    """'300' left unsaved in #6's box, then #6's own label scanned to weigh it
    again, and the new reading started before the answer: the new reading
    takes the old one's place (Net: 1000 g - 425 g = 575 g used; Set Used: 425
    g), as it does when the answer is quick (the old one is selected). RED on
    66f2c44: the box held 300425 (Net: the spool read full; Set Used: empty,
    and it was archived and taken off its place)."""
    page, open_ = wo
    page.evaluate("() => { window.__holdScans = true; }")
    open_(mode=mode)
    press(page, "300", 150, enter=False)
    later(page, 600)
    press(page, "ID:6", 5)
    _held(page, "scan")
    later(page, 300)
    press(page, "4", 0, enter=False)
    _release(page, "scan")
    _scan_answered(page)
    assert (_focus(page), _box(page, 6)) == ("6", "4"), mode
    later(page, 150)
    press(page, "25", 150)
    _saved(page)
    assert (_updates(page), _unassigned(page)) == ([{"id": 6, "updates": {"used_weight": used}}], []), mode


def test_a_spool_scanned_again_while_it_saves_over_the_empty_weight_prompt_keeps_the_reading(wo):
    """#8 weighed empty (its empty-weight prompt opens late, after a slow
    filament read), then #6's reading saved, its save slow, the focus moving on
    to #134; the prompt opens; #6 is scanned again into it, to weigh it again:
    the prompt closes, and the reading typed next is kept for #6, in its box
    once its save has landed, and saved to #6 (1000 g - 480 g = 520 g used).
    RED on 66f2c44: #8's fade drew the list again, #6's box enabled though it
    was saving, so the scan gave that box the focus and the new reading, which
    vanished with the row when the old save landed; with the box disabled, the
    prompt's close gave #134's box the focus (the box that had it as the
    prompt opened), and the reading went there."""
    page, open_ = wo
    page.evaluate("() => { window.__filamentMs = 1200; }")
    open_(held=(8, 6, 134))
    press(page, "0", 150)
    _saved(page)                                   # #8: archived; its prompt opens in ~1.6 s
    page.evaluate("() => { window.__holdSaves = true; }")
    later(page, 600)
    press(page, "500", 150)                        # #6's, its save held
    _held(page, "save")
    assert _focus(page) == "134"
    page.wait_for_function("() => document.activeElement && document.activeElement.id === 'fcc-archive-empty-wt'",
                           timeout=5000)
    later(page, 700)
    press(page, "ID:6", 5)
    _scan_answered(page)
    assert page.locator("#fcc-archive-empty-overlay").count() == 0 and _focus(page) == "weighOutModal"
    later(page, 700)
    press(page, "480", 150, enter=False)
    assert (_box(page, 134), page.evaluate("() => state.scanBuffer")) == ("", "")
    page.evaluate("() => { window.__holdSaves = false; }")
    _release(page, "save")
    page.wait_for_function("() => { const b = document.querySelector('.weigh-input[data-id=\"6\"]'); return b && !b.disabled; }")
    assert (_focus(page), _box(page, 6)) == ("6", "480")
    press(page, "", 0)
    _saved(page, 3)
    ups = _updates(page)
    assert [u["id"] for u in ups] == [8, 6, 6] and ups[2]["updates"]["used_weight"] == 520 and _filament_writes(page) == 0, ups


def test_a_key_typed_on_another_rows_save_button_while_a_scan_is_answered_goes_with_it(wo):
    """#134's 💾 clicked with its box empty (nothing is saved; the focus stays
    on it), then #57 scanned and its reading started before the answer: the
    whole reading goes to #57 (750 g - 425 g = 325 g used), and #134's box
    stays empty. RED on 66f2c44: the first key went into #134's box and stayed
    there, and 25 g was saved to #57."""
    page, open_ = wo
    page.evaluate("() => { window.__holdScans = true; }")
    open_()
    page.locator(".weigh-row[data-id='134'] .weigh-save-btn").click()
    later(page, 700)
    press(page, "ID:57", 5)
    _held(page, "scan")
    later(page, 300)
    press(page, "4", 0, enter=False)
    _release(page, "scan")
    _scan_answered(page)
    assert (_focus(page), _box(page, 57), _box(page, 134), _box(page, 6)) == ("57", "4", "", "")
    later(page, 150)
    press(page, "25", 150)
    _saved(page)
    assert _updates(page) == [{"id": 57, "updates": {"used_weight": 325}}]


def test_a_backspace_takes_back_a_key_held_for_a_scan(wo):
    """The list empty (the focus on the window), #57 scanned, and its reading
    typed before the answer with a typo put right ('45', Backspace, '25'): the
    held keys are shown nowhere, so the Backspace takes the last one back, and
    #57's box takes 425 (325 g used). RED on 66f2c44: the Backspace was
    ignored, and 4525 was saved (the spool read empty)."""
    page, _ = wo
    page.evaluate("() => { window.__holdScans = true; }")
    page.evaluate(SETUP, [])
    page.evaluate("() => { window.weighOutMode = 'net'; window.openWeighOutModal(); }")
    page.evaluate("() => document.getElementById('weighOutModal').focus()")
    later(page, 700)
    press(page, "ID:57", 5)
    _held(page, "scan")
    later(page, 300)
    press(page, ["4", "5", "Backspace", "2", "5"], 150, enter=False)
    _release(page, "scan")
    _scan_answered(page)
    assert (_focus(page), _box(page, 57)) == ("57", "425")
    later(page, 150)
    press(page, "", 0)
    _saved(page)
    assert _updates(page) == [{"id": 57, "updates": {"used_weight": 325}}]


def test_a_scanners_second_enter_doesnt_move_the_focus_before_the_answer(wo):
    """A scanner that ends a label with two Enters (CR LF): #57's label read
    into #6's empty box, and the reading started before the answer: the second
    Enter leaves the focus where it was, so the reading goes to #57 (325 g
    used). RED on 66f2c44: the second Enter moved the focus to #134's box, the
    reading stayed there, and #57's box was empty."""
    page, open_ = wo
    page.evaluate("() => { window.__holdScans = true; }")
    open_()
    press(page, list("ID:57") + ["Enter"], 5)    # its Enter, and a second
    _held(page, "scan")
    assert _focus(page) == "6"
    later(page, 300)
    press(page, "4", 0, enter=False)
    _release(page, "scan")
    _scan_answered(page)
    assert (_focus(page), _box(page, 57), _box(page, 134)) == ("57", "4", "")
    later(page, 150)
    press(page, "25", 150)
    _saved(page)
    assert _updates(page) == [{"id": 57, "updates": {"used_weight": 325}}]


@pytest.mark.parametrize("scanned", [134, 57])
def test_a_labels_letters_typed_as_an_answer_lands_never_go_in_a_box(wo, scanned):
    """'300' in #6's box, a spool scanned into it (#134, listed, or #57, new,
    whose row is drawn), and before the answer the first letters of the next
    label: the answer moves no letter into the scanned spool's box, and #6's
    '300' never turns up there; the rest of that label (no spool) saves
    nothing. RED on 66f2c44: 'ID' went into #134's box as its reading, and
    when #57's row was drawn the label's carry put #6's '300' in #57's box."""
    page, open_ = wo
    page.evaluate("() => { window.__holdScans = true; }")
    open_()
    press(page, "300", 150, enter=False)
    later(page, 600)
    press(page, f"ID:{scanned}", 5)
    _held(page, "scan")
    later(page, 300)
    press(page, "ID", 5, enter=False)            # the next label's first letters
    _release(page, "scan")
    _scan_answered(page)
    press(page, ":480", 5)
    page.wait_for_timeout(100)
    assert (_focus(page), _box(page, scanned), _updates(page)) == (str(scanned), "", []), scanned


@pytest.mark.parametrize("when", ["split", "whole"])
def test_a_scan_queued_behind_another_takes_the_reading_typed_meanwhile(wo, when):
    """The focus on a mode button, #134 scanned and, while its answer is on its
    way, #57 (the scan accumulator queues it until #134's answer is in):
    #134's answer moves no focus, and #57's box takes the reading typed
    meanwhile, its first key before #134's answer ('split') or all of it and
    Enter ('whole'), saved to #57 (750 g - 645 g = 105 g used). RED on
    66f2c44: #134's answer counted as the latest scan, moved the focus to
    #134's box and took the first key, so 45 g was saved to #57; or the whole
    reading, typed before #57's scan went out, went to #134."""
    page, open_ = wo
    page.evaluate("() => { window.__holdScans = ['ID:134']; }")
    open_()
    page.locator("#weigh-out-mode [data-mode='net']").click()
    later(page, 700)
    press(page, "ID:134", 5)
    _held(page, "scan")
    later(page, 300)
    press(page, "ID:57", 5)                       # queued: #134's answer isn't in
    later(page, 300)
    if when == "split":
        press(page, "6", 0, enter=False)
    else:
        press(page, "645", 150)                   # and its Enter, held off
    _release(page, "scan")
    _scan_answered(page, 2)                       # #134's, then #57's
    assert (_focus(page), _box(page, 134)) == ("57", ""), when
    if when == "split":
        later(page, 150)
        press(page, "45", 150)
    else:
        assert (_box(page, 57), _updates(page)) == ("645", [])
        later(page, 300)
        press(page, "", 0)
    _saved(page)
    assert _updates(page) == [{"id": 57, "updates": {"used_weight": 105}}], when


def test_a_scan_queued_behind_a_spool_scan_that_names_no_spool_leaves_it_the_focus(wo):
    """The list empty (the focus on the window), #57 scanned, a key typed, then
    a label that names no spool read before #57's answer (the accumulator
    queues it), and another key: once that label is answered, #57's box takes
    the focus with both keys, and the reading is saved to #57 (325 g used).
    Pins the round-9 rule's limit: only a later scan that names a spool takes
    the focus from an earlier one."""
    page, _ = wo
    page.evaluate("() => { window.__holdScans = ['ID:57']; }")
    page.evaluate(SETUP, [])
    page.evaluate("() => { window.weighOutMode = 'net'; window.openWeighOutModal(); }")
    page.evaluate("() => document.getElementById('weighOutModal').focus()")
    later(page, 700)
    press(page, "ID:57", 5)
    _held(page, "scan")
    later(page, 300)
    press(page, "4", 0, enter=False)
    later(page, 600)
    press(page, "LOC:NOWHERE", 5)                 # queued behind #57's; Unknown Code
    later(page, 300)
    press(page, "2", 0, enter=False)
    _release(page, "scan")
    _scan_answered(page, 2)
    assert (_focus(page), _box(page, 57)) == ("57", "42")
    later(page, 150)
    press(page, "5", 150)
    _saved(page)
    assert _updates(page) == [{"id": 57, "updates": {"used_weight": 325}}]


def test_a_queued_scan_answered_without_the_server_holds_nothing_off(wo):
    """#57 scanned, and while its answer is on its way a scan that never goes
    to the server (a closed dialog's confirm QR, answered by processScan
    itself) is read and queued: once it has been answered, #57's box takes the
    reading typed meanwhile, and Enter saves it (325 g used). Pins the queue's
    end of a scan it never sent: Enter would wait for an answer for ever."""
    page, open_ = wo
    page.evaluate("() => { window.__holdScans = ['ID:57']; }")
    open_()
    page.locator("#weigh-out-mode [data-mode='net']").click()
    later(page, 700)
    press(page, "ID:57", 5)
    _held(page, "scan")
    later(page, 300)
    press(page, "CMD:CONFIRM:fcc-cqr-0-gone", 5)    # queued behind #57's
    later(page, 300)
    press(page, "425", 150, enter=False)
    _release(page, "scan")
    _scan_answered(page)
    page.wait_for_timeout(400)                     # the queue has run it
    assert (_focus(page), _box(page, 57), _scans(page)) == ("57", "425", ["ID:57"])
    later(page, 150)
    press(page, "", 0)
    _saved(page)
    assert _updates(page) == [{"id": 57, "updates": {"used_weight": 325}}]


def test_an_earlier_spool_scan_answered_after_a_later_one_that_named_none_takes_the_focus(wo):
    """#57's label scanned into #6's box (its answer slow), then a label that
    names no spool scanned into it too and answered first: when #57's answer
    comes, #57's box takes the focus, as the latest scan that named a spool
    (the fallback's other order). RED on 66f2c44: the focus stayed where it
    was."""
    page, open_ = wo
    page.evaluate("() => { window.__holdScans = ['ID:57']; }")
    open_()
    press(page, "ID:57", 5)
    _held(page, "scan")
    later(page, 600)
    press(page, "LOC:NOWHERE", 5)                  # sent at once from the box; Unknown Code
    _scan_answered(page)
    _release(page, "scan")
    _scan_answered(page, 2)
    assert _focus(page) == "57"


def test_keys_held_for_a_scan_another_spool_scan_took_over_are_said_to_be_gone(wo):
    """The list empty (the focus on the window), #57 scanned, a key typed for it
    ('4', held), and then #134 scanned before #57's answer (queued behind it):
    #134's box takes the focus with what was typed after its own read ('2'),
    and a warning says the '4' wasn't kept, never put in #134's box unseen.
    RED on 66f2c44: #57's answer, the first in, took the focus and both keys,
    and #134's queued scan then took the focus with nothing."""
    page, _ = wo
    page.evaluate("() => { window.__holdScans = ['ID:57']; }")
    page.evaluate(SETUP, [])
    page.evaluate("() => { window.weighOutMode = 'net'; window.openWeighOutModal(); }")
    page.evaluate("() => document.getElementById('weighOutModal').focus()")
    later(page, 700)
    press(page, "ID:57", 5)
    _held(page, "scan")
    later(page, 300)
    press(page, "4", 0, enter=False)
    later(page, 600)
    press(page, "ID:134", 5)                       # queued behind #57's
    later(page, 300)
    press(page, "2", 0, enter=False)
    _release(page, "scan")
    _scan_answered(page, 2)
    assert (_focus(page), _box(page, 134)) == ("134", "2")
    assert any('("4") wasn\'t kept' in t for t in _toasts(page)), _toasts(page)


def test_a_spool_scanned_again_while_its_details_are_read_gets_the_new_reading_when_its_save_fails(wo):
    """Additive, #6's details unreadable: '+25' entered (its row waits while
    they are read, the focus moving on), and #6 scanned again meanwhile, with
    '+30' typed for it; the save can't go out without its details, so #6's box
    opens again with the new reading in it and the focus. RED on 66f2c44: the
    focus stayed in #6's box while the details were read, and the reading was
    saved as 25 g left."""
    page, open_ = wo
    page.evaluate("() => { window.__detailsFail = true; window.__holdDetails = true; }")
    open_(mode="additive")
    press(page, "+25", 150)
    assert _focus(page) == "134"
    page.evaluate("() => { window.__answerMs = 0; window.processScan('ID:6', 'barcode'); }")
    _scan_answered(page)
    later(page, 700)
    press(page, "+30", 150, enter=False)
    page.evaluate("() => { window.__holdDetails = false; }")
    _release(page, "details")                     # its details read fails
    page.wait_for_function("() => { const b = document.querySelector('.weigh-input[data-id=\"6\"]'); return b && !b.disabled; }")
    page.wait_for_timeout(50)
    assert (_focus(page), _box(page, 6), _updates(page)) == ("6", "+30", [])


def test_a_spool_scanned_again_while_it_saves_takes_the_key_typed_before_the_answer(wo):
    """#6's reading saved, its save slow, the focus moving on to #134; #6
    scanned again into #134's box, its answer slow too, and the new reading
    started before it ('4', into #134's box): the key goes with the scan, kept
    for #6 while its save is on its way, and #6's box has the whole reading once
    the save has landed (1000 g - 480 g = 520 g used); #134's box keeps
    nothing. RED on 66f2c44: the '4' stayed in #134's box, and the rest of the
    reading, typed with the focus on the window, went to the scan path."""
    page, open_ = wo
    page.evaluate("() => { window.__holdSaves = true; window.__holdScans = true; }")
    open_()
    press(page, "500", 150)
    _held(page, "save")
    assert _focus(page) == "134"
    later(page, 700)
    press(page, "ID:6", 5)
    _held(page, "scan")
    later(page, 300)
    press(page, "4", 0, enter=False)              # the answer isn't in
    _release(page, "scan")
    _scan_answered(page)
    assert (_focus(page), _box(page, 134)) == ("weighOutModal", "")
    later(page, 700)
    press(page, "80", 150, enter=False)
    page.evaluate("() => { window.__holdSaves = false; }")
    _release(page, "save")
    page.wait_for_function("() => { const b = document.querySelector('.weigh-input[data-id=\"6\"]'); return b && !b.disabled; }")
    assert (_focus(page), _box(page, 6), page.evaluate("() => state.scanBuffer")) == ("6", "480", "")
    press(page, "", 0)
    _saved(page, 2)
    assert [u["updates"]["used_weight"] for u in _updates(page)] == [500, 520]


def test_a_save_by_its_button_moves_the_focus_on(wo):
    """#6's reading typed and saved with its 💾 (a click): the focus moves on to
    #134's box, as Enter's save does, and the next reading goes there. Pins
    round 9's rule that a save moves the focus only from its own row: its 💾 is
    part of the row."""
    page, open_ = wo
    open_()
    press(page, "500", 150, enter=False)
    page.locator(".weigh-row[data-id='6'] .weigh-save-btn").click()
    _saved(page)
    assert _focus(page) == "134"


def test_a_save_leaves_the_window_its_focus_while_it_holds_keys_for_a_rescanned_spool(wo):
    """#6's details slow, its reading entered (its row waits, the focus moving
    on); #6 scanned again while they are read (the window takes the focus and
    holds the keys typed for #6); its save goes out and is slow; the rest of
    the new reading typed then is held too, and #6's box has it all once the
    save has landed (1000 g - 480 g = 520 g used). Pins the save's focus rule:
    the window holding keys for a scan isn't "nowhere". RED on 66f2c44: the
    focus stayed in #6's box while its details were read, and the save's late
    move took it to #134's box."""
    page, open_ = wo
    page.evaluate("() => { window.__holdDetails = true; window.__holdSaves = true; }")
    open_()
    press(page, "500", 150)                        # #6's details aren't in yet
    assert _focus(page) == "134"
    page.evaluate("() => { window.__answerMs = 0; window.processScan('ID:6', 'barcode'); }")
    _scan_answered(page)
    assert _focus(page) == "weighOutModal"
    later(page, 700)
    press(page, "4", 0, enter=False)
    page.evaluate("() => { window.__holdDetails = false; }")
    _release(page, "details")
    _held(page, "save")                            # its details came, and its save went out
    later(page, 600)
    press(page, "80", 150, enter=False)
    assert (_focus(page), _box(page, 134)) == ("weighOutModal", "")
    page.evaluate("() => { window.__holdSaves = false; }")
    _release(page, "save")
    page.wait_for_function("() => { const b = document.querySelector('.weigh-input[data-id=\"6\"]'); return b && !b.disabled; }")
    assert (_focus(page), _box(page, 6)) == ("6", "480")
    press(page, "", 0)
    _saved(page, 2)
    assert [u["updates"]["used_weight"] for u in _updates(page)] == [500, 520]


def test_a_row_saving_stays_disabled_through_a_redraw(wo):
    """#6's reading saved, its save slow, and the list drawn again meanwhile
    (a heartbeat does that): #6's box stays disabled until the save lands, so
    #6 scanned again, to weigh it again, keeps the new reading typed then (in
    its box once the save has landed) and saves it (1000 g - 480 g = 520 g
    used). RED on 66f2c44: the redraw drew #6's box enabled, the scan gave it
    the focus and the new reading, and when the old save landed its row faded
    away with it: nothing was saved."""
    page, open_ = wo
    page.evaluate("() => { window.__holdSaves = true; }")
    open_()
    press(page, "500", 150)
    _held(page, "save")
    page.evaluate("() => document.dispatchEvent(new CustomEvent('inventory:buffer-updated'))")
    assert page.evaluate("() => document.querySelector('.weigh-input[data-id=\"6\"]').disabled")
    page.evaluate("() => { window.__answerMs = 0; window.processScan('ID:6', 'barcode'); }")
    _scan_answered(page)
    later(page, 700)
    press(page, "480", 150, enter=False)
    page.evaluate("() => { window.__holdSaves = false; }")
    _release(page, "save")
    page.wait_for_function("() => { const b = document.querySelector('.weigh-input[data-id=\"6\"]'); return b && !b.disabled; }")
    page.wait_for_timeout(450)                    # past the 300 ms a fade would take
    assert (_focus(page), _box(page, 6)) == ("6", "480")
    press(page, "", 0)
    _saved(page, 2)
    ups = _updates(page)
    assert [u["id"] for u in ups] == [6, 6] and ups[1]["updates"]["used_weight"] == 520, ups


def test_a_spool_weighed_again_counts_from_what_its_last_save_saved(wo):
    """Additive: #6 weighed (+10 g: 41 g used), its row faded, then scanned
    again and +10 entered while its details are still being read again (a slow
    Spoolman): the second save counts from what the first saved (51 g used).
    Pins showAgain's re-read: with its old details kept, 41 g was saved again."""
    page, open_ = wo
    open_(mode="additive")
    press(page, "+10", 150)
    _saved(page)
    page.wait_for_function("() => !document.querySelector('.weigh-input[data-id=\"6\"]')")    # faded
    page.evaluate("() => { window.__holdDetails = true; window.__answerMs = 0; window.processScan('ID:6', 'barcode'); }")
    _scan_answered(page)
    assert _focus(page) == "6"
    later(page, 700)
    press(page, "+10", 150)                       # its details aren't in yet
    _held(page, "details", 2)                     # showAgain's re-read, and the save's
    page.evaluate("() => { window.__holdDetails = false; }")
    _release(page, "details")
    _saved(page, 2)
    assert [u["updates"]["used_weight"] for u in _updates(page)] == [41, 51]


def test_a_session_closed_while_a_row_fades_keeps_that_spool_in_the_next(wo):
    """#6 saved, and the window closed and opened again before its row's 300 ms
    fade has ended: #6 is listed in the new session, and the old fade never
    takes it out. Pins open's fade cancel."""
    page, open_ = wo
    page.evaluate(HOLD_FADES)
    open_()
    press(page, "500", 150)
    page.wait_for_function("() => window.__fades.size >= 1")
    page.evaluate("""() => { const m = document.getElementById('weighOutModal'); m.classList.remove('show');
        m.dispatchEvent(new Event('hidden.bs.modal', { bubbles: true })); }""")
    open_()
    page.evaluate("() => window.__runFades()")
    page.wait_for_timeout(50)
    assert page.evaluate("() => !!document.querySelector('.weigh-input[data-id=\"6\"]')")


# --- Group 57 review, round 10 ------------------------------------------------
# Each test below is RED on 2942ba1 unless it says it pins a limit.


@pytest.mark.parametrize("mode", ["set_used", "net"])
def test_a_saved_row_takes_no_key_while_it_fades(wo, mode):
    """The list's only spool, #6, saved, and a quick key and Enter while its
    row fades (a correction, say): the fading row takes no key, so #6 is never
    saved again; the key goes on to the scan path, as any key with no box to
    go in does. RED on 2942ba1: the save's own redraw drew the fading row
    enabled, the key went into its box as the target's ('5004'), and Enter
    saved #6 again (Set Used: used 1000, archived and taken off its place; Net:
    the spool read full)."""
    page, open_ = wo
    page.evaluate(HOLD_FADES)
    open_(held=(6,), mode=mode)
    press(page, "500", 150)
    _saved(page)
    page.wait_for_function("() => window.__fades.size >= 1")      # its fade, held
    later(page, 100)
    press(page, "4", 30)                                          # and its Enter
    page.wait_for_timeout(150)
    assert (len(_updates(page)), _unassigned(page), _box(page, 6)) == (1, [], "500"), mode
    disabled = page.evaluate("() => document.querySelector('.weigh-input[data-id=\"6\"]').disabled")
    assert disabled and _scans(page) == ["4"], mode


def test_a_save_that_read_its_details_first_doesnt_open_its_tare_prompt_over_the_next_reading(wo):
    """Gross, #8 with no empty spool weight on record and its details still
    being read when Enter is pressed: the focus moves on to #6, the person
    starts #6's reading, and once #8's details are in no prompt opens over it
    (a warning says #8 wasn't saved and how to give it); #6's reading is saved
    to #6 (1000 g - (645 g - 167 g) = 522 g used), and Enter in #8's box again
    asks for its tare. RED on 2942ba1: the prompt opened over #6's reading and
    took the rest of it as #8's tare (#8: 400 g used)."""
    page, open_ = wo
    page.evaluate("() => { window.__holdDetails = true; }")
    open_(held=(8, 6), mode="gross")
    press(page, "645", 150)                       # #8's Enter: its details aren't in yet
    assert _focus(page) == "6"
    later(page, 600)
    press(page, "6", 0, enter=False)              # #6's reading begins
    page.evaluate("() => { window.__holdDetails = false; }")
    _release(page, "details")                     # #8's details come in
    page.wait_for_timeout(300)
    assert page.locator("#fcc-missing-empty-weight-overlay").count() == 0
    assert any("#8 wasn't saved" in t and "Enter in its box" in t for t in _toasts(page)), _toasts(page)
    later(page, 150)
    press(page, "45", 150)
    _saved(page)
    assert _updates(page) == [{"id": 6, "updates": {"used_weight": 522}}]
    assert page.evaluate("() => !document.querySelector('.weigh-input[data-id=\"8\"]').disabled") and _box(page, 8) == "645"
    page.locator(".weigh-input[data-id='8']").focus()
    later(page, 700)
    press(page, "", 0)                            # Enter in #8's box: its details are in now
    page.wait_for_function("() => document.activeElement && document.activeElement.id === 'fcc-missing-empty-weight-overlay-input'")


@pytest.mark.parametrize("meanwhile, opens", [("moved", False), ("redrawn", True), ("nothing", True)])
def test_a_late_tare_prompt_opens_only_where_the_person_was_left(wo, meanwhile, opens):
    """Gross, #8 with no empty spool weight and its details still being read
    when Enter is pressed (the focus moving on to #6): if the person moved on
    from there meanwhile (Tab), no prompt opens and the row waits for its Enter
    again; if nothing was done, or the list was only drawn again (a heartbeat:
    the same box, drawn anew), the prompt opens. Pins the late prompt's check
    (round 10)."""
    page, open_ = wo
    page.evaluate("() => { window.__holdDetails = true; }")
    open_(held=(8, 6), mode="gross")
    press(page, "645", 150)
    assert _focus(page) == "6"
    if meanwhile == "moved":
        page.keyboard.press("Tab")
    elif meanwhile == "redrawn":
        page.evaluate("() => document.dispatchEvent(new CustomEvent('inventory:buffer-updated'))")
        assert _focus(page) == "6"
    page.evaluate("() => { window.__holdDetails = false; }")
    _release(page, "details")                     # #8's details come in
    page.wait_for_timeout(300)
    assert page.locator("#fcc-missing-empty-weight-overlay").count() == (1 if opens else 0), meanwhile
    assert _updates(page) == []
    if opens:
        # Cancelled, the focus goes back where the person is, #6's box (round
        # 10: it went back to #8's, and the next reading joined #8's).
        page.keyboard.press("Escape")
        page.wait_for_function("() => !document.getElementById('fcc-missing-empty-weight-overlay')")
        assert _focus(page) == "6", meanwhile


def test_a_spools_details_are_read_with_a_timeout(wo):
    """The list's reads of a spool's details go through window.fetchT with a
    timeout (10 s): a save waits on one with its row disabled, and a read that
    never answered kept it so (round 10). Pins that the read can't hang."""
    page, open_ = wo
    page.evaluate("""() => { const orig = window.fetchT; window.__fetchT = [];
        window.fetchT = (url, opts, ms) => { window.__fetchT.push([String(url), ms]); return orig(url, opts, ms); }; }""")
    open_()
    calls = page.evaluate("() => window.__fetchT.filter(([u]) => u.includes('/api/spool_details'))")
    assert calls and all(ms == 10000 for _, ms in calls), calls


def _dimmed(page):
    return page.evaluate("() => { const o = document.getElementById('processing-overlay');"
                         " return !!state.processing || (!!o && o.style.display === 'block'); }")


@pytest.mark.parametrize("where", ["name", "box"])
def test_a_click_on_a_row_waiting_for_its_details_takes_it_back(wo, where):
    """#6's details still being read when '500' is entered: its row waits and
    the focus moves on to #134's box. Nothing is sent for #6 yet, so a click on
    its row (its name, or its disabled box) takes it back: its box open again,
    the focus there with '500' selected, and a toast saying it wasn't saved.
    The correction typed next replaces it, and #6 is saved once, with 470 (530
    used). RED on 1c593f5: the page was dimmed, so the click landed on the dim
    and did nothing, and the correction went to #134's box."""
    page, open_ = wo
    page.evaluate("() => { window.__holdDetails = [6]; }")
    open_()
    press(page, "500", 150)                       # its details aren't in yet
    assert _focus(page) == "134" and not _dimmed(page)
    target = '.weigh-row[data-id="6"] .fw-bold' if where == "name" else '.weigh-input[data-id="6"]'
    page.locator(target).click(force=True, timeout=2000)
    assert _focus(page) == "6" and _box(page, 6) == "500"
    assert page.evaluate("() => { const b = document.activeElement; return [b.selectionStart, b.selectionEnd]; }") == [0, 3]
    assert any("#6 wasn't saved: put its reading right" in t for t in _toasts(page)), _toasts(page)
    later(page, 900)
    press(page, "470", 150)
    page.evaluate("() => window.__releaseDetails(6)")
    _saved(page)
    page.wait_for_timeout(100)
    ups = _updates(page)
    assert [(u["id"], u["updates"]["used_weight"]) for u in ups] == [(6, 530)], ups


def test_a_row_taken_back_while_another_waits_too_never_saves_its_correction_elsewhere(wo):
    """Net, #6, #134 and #57, the details of #6 and #134 slow: '500' on #6 (a
    slip) and '480' on #134 both wait, the focus on #57. #6's details come and
    its save lands. A click on #134's name takes #134 back, and its correction,
    '470', is saved to #134 (530 used), never to #57. RED on 1c593f5 (the
    round-11 ORANGE): #6's save lifted the dim while #134 still waited, the
    click moved no focus, and '470' was saved to #57."""
    page, open_ = wo
    page.evaluate("() => { window.__holdDetails = [6, 134]; }")
    open_(held=(6, 134, 57))
    press(page, "500", 150)
    later(page, 900)
    press(page, "480", 150)
    assert _focus(page) == "57"
    page.evaluate("() => window.__releaseDetails(6)")
    _saved(page)                                  # #6's save went out and landed
    page.wait_for_timeout(100)
    page.locator('.weigh-row[data-id="134"] .fw-bold').click(force=True, timeout=2000)
    assert (_focus(page), _box(page, 134)) == ("134", "480")
    later(page, 900)
    press(page, "470", 150)
    page.evaluate("() => window.__releaseDetails(134)")
    _saved(page, 2)
    page.wait_for_timeout(100)
    ups = [(u["id"], u["updates"]["used_weight"]) for u in _updates(page)]
    assert ups == [(6, 500), (134, 530)], ups


def test_a_click_on_a_saving_row_says_so_and_the_focus_stays_where_the_keys_go(wo):
    """#6's save on its way (held) and a click that reaches its row (the dim a
    save keeps can be lifted by another answer): a toast says #6 is being
    saved, and the focus goes back to #134's box, where the keys go, never
    left on the window. Pins round 11's message; the keys went to #134 before
    it too, unseen."""
    page, open_ = wo
    page.evaluate("() => { window.__holdSaves = true; }")
    open_()
    press(page, "500", 150)                       # #6's details are in: its save goes out
    _held(page, "save")
    page.evaluate("""() => { document.getElementById('weighOutModal').focus();
        document.querySelector('.weigh-row[data-id="6"] .fw-bold').click(); }""")
    assert _focus(page) == "134"
    assert any("#6 is being saved" in t for t in _toasts(page)), _toasts(page)
    page.evaluate("() => { window.__holdSaves = false; }")
    _release(page, "save")


@pytest.mark.parametrize("typed", [False, True])
def test_a_late_tare_prompt_after_the_last_box_minds_a_key_sent_to_the_scan_path(wo, typed):
    """Gross, the list only #8 (no empty spool weight), its details slow: '645'
    entered, the focus left on the window (the last box). With nothing typed
    since, the tare prompt opens once the details come. With a key typed on the
    window meanwhile (it goes to the scan path: no box takes it), it doesn't,
    and a warning says #8 wasn't saved. RED on 1c593f5 with a key typed: the
    prompt opened and took the rest of the reading as #8's tare."""
    page, open_ = wo
    page.evaluate("() => { window.__holdDetails = [8]; }")
    open_(held=(8,), mode="gross")
    press(page, "645", 150)
    assert _focus(page) == "weighOutModal"
    if typed:
        later(page, 900)
        press(page, "1", 0, enter=False)
    page.evaluate("() => window.__releaseDetails(8)")
    page.wait_for_timeout(300)
    prompt = page.evaluate("() => !!document.querySelector('.fcc-weight-box:not(.weigh-input)')")
    if typed:
        assert not prompt
        assert any("#8 wasn't saved: it needs its empty spool weight" in t for t in _toasts(page)), _toasts(page)
    else:
        assert prompt, "nothing typed since: the prompt opens"
    assert _updates(page) == []


def test_enter_waits_for_an_earlier_spool_scan_after_a_later_one_named_none(wo):
    """#57's label scanned into #6's box (its answer slow), a key typed, then a
    label that names no spool scanned into it too and answered at once, and
    the rest of the reading and Enter: nothing is saved while #57's scan is
    out; once it is in, #57's box holds the whole reading and the focus, and
    Enter saves it there (325 g used). RED on 2942ba1: the later scan's answer
    freed Enter, and the reading was saved to #6."""
    page, open_ = wo
    page.evaluate("() => { window.__holdScans = ['ID:57']; }")
    open_()
    press(page, "ID:57", 5)
    _held(page, "scan")
    later(page, 300)
    press(page, "4", 0, enter=False)
    later(page, 600)
    press(page, "LOC:NOWHERE", 5)                 # sent at once from the box: Unknown Code
    _scan_answered(page)
    later(page, 300)
    press(page, "25", 150)                        # and Enter, before #57's answer
    page.wait_for_timeout(100)
    assert _updates(page) == []
    _release(page, "scan")
    _scan_answered(page, 2)
    assert (_focus(page), _box(page, 57), _box(page, 6)) == ("57", "425", "")
    later(page, 300)
    press(page, "", 0)
    _saved(page)
    assert _updates(page) == [{"id": 57, "updates": {"used_weight": 325}}]


def _queue_behind(page, labels_and_keys):
    """The list empty, the focus on the window, #57's scan read (its answer
    held), then each (label, key) in turn: the label read (queued behind #57's)
    and the key typed after it."""
    page.evaluate("() => { window.__holdScans = ['ID:57']; }")
    page.evaluate(SETUP, [])
    page.evaluate("() => { window.weighOutMode = 'net'; window.openWeighOutModal(); }")
    page.evaluate("() => document.getElementById('weighOutModal').focus()")
    later(page, 700)
    press(page, "ID:57", 5)
    _held(page, "scan")
    for label, key in labels_and_keys:
        later(page, 300)
        if label:
            press(page, label, 5)
            later(page, 300)
        press(page, key, 0, enter=False)


def test_keys_typed_under_scans_that_name_no_spool_go_to_the_spool_scan_before_them(wo):
    """#57 scanned (its answer slow), '4' typed; a label that names no spool
    read (queued), '2'; another one (queued), '5': once all are answered,
    #57's box has the whole reading, '425', and nothing is said to be lost.
    RED on 2942ba1: the middle scan's '2' was said to be gone, and #57 got
    '45'."""
    page, _ = wo
    _queue_behind(page, [(None, "4"), ("LOC:NOWHERE", "2"), ("LOC:NOPE", "5")])
    _release(page, "scan")
    _scan_answered(page, 3)
    page.wait_for_timeout(300)
    assert (_focus(page), _box(page, 57)) == ("57", "425")
    assert not any("wasn't kept" in t for t in _toasts(page)), _toasts(page)


def test_keys_held_for_a_scan_that_named_no_spool_with_no_spool_scan_before_it_are_said_to_be_gone(wo):
    """The list empty, a label that names no spool scanned (its answer slow),
    '2' typed, then #57 scanned (queued behind it): the '2' was typed for no
    spool, so a warning says it wasn't kept, and #57's box takes the focus with
    nothing in it. Pins the hand-on's limit: keys go only to a scan read
    before theirs."""
    page, _ = wo
    page.evaluate("() => { window.__holdScans = ['LOC:NOWHERE']; }")
    page.evaluate(SETUP, [])
    page.evaluate("() => { window.weighOutMode = 'net'; window.openWeighOutModal(); }")
    page.evaluate("() => document.getElementById('weighOutModal').focus()")
    later(page, 700)
    press(page, "LOC:NOWHERE", 5)
    _held(page, "scan")
    later(page, 300)
    press(page, "2", 0, enter=False)
    later(page, 600)
    press(page, "ID:57", 5)                       # queued behind it
    _release(page, "scan")
    _scan_answered(page, 2)
    page.wait_for_timeout(300)
    assert (_focus(page), _box(page, 57)) == ("57", "")
    assert any('("2") wasn\'t kept' in t for t in _toasts(page)), _toasts(page)


HOOK_OPEN = """() => { window.weighOutMode = 'net'; window.openWeighOutModal();
    document.getElementById('weighOutModal').focus(); }"""
# #57 joins the list, as processScan's answer adds it, and is answered as a spool.
HOOK_57 = """(from) => { state.heldSpools.unshift(Object.assign({}, window.__rows[57]));
    document.dispatchEvent(new CustomEvent('inventory:buffer-updated'));
    window.weighOutTakeScan(57, window[from]); window.weighOutScanDone(window[from]); }"""


def test_a_reading_typed_across_scans_answered_in_reverse_comes_out_in_the_order_typed(wo):
    """The pending model alone, its hooks called as processScan calls them: the
    list empty, #57's scan read and '4' typed, a label read and '2', another
    and '5'; #57 answered first, then the LAST label, then the middle one (a
    scan typed into a box goes out at once, so answers can come in any order).
    #57's box gets '425', with nothing said to be lost. RED on 1c593f5: the
    keys were handed on in the order the answers came, '452'."""
    page, _ = wo
    page.evaluate(SETUP, [])
    page.evaluate(HOOK_OPEN)
    later(page, 700)
    for name, key in (("__a", "4"), ("__b", "2"), ("__c", "5")):
        page.evaluate("(n) => { window[n] = window.weighOutScanStart(); }", name)
        press(page, key, 0, enter=False)
        later(page, 300)
    page.evaluate(HOOK_57, "__a")
    page.evaluate("() => { window.weighOutScanDone(window.__c); window.weighOutScanDone(window.__b); }")
    page.wait_for_timeout(150)
    assert (_focus(page), _box(page, 57)) == ("57", "425")
    assert not any("wasn't kept" in t for t in _toasts(page)), _toasts(page)


def test_a_label_answered_before_the_spool_scan_read_before_it_hands_its_keys_on(wo):
    """A label read after #57's scan is answered (naming no spool) before #57's
    is: what was typed under it waits on #57's scan, still out, and goes into
    #57's box with the rest. Before round 11 it was said to be gone, and #57
    got '4' of '425'."""
    page, _ = wo
    page.evaluate(SETUP, [])
    page.evaluate(HOOK_OPEN)
    later(page, 700)
    page.evaluate("() => { window.__a = window.weighOutScanStart(); }")
    press(page, "4", 0, enter=False)
    later(page, 300)
    page.evaluate("() => { window.__b = window.weighOutScanStart(); }")
    press(page, "25", 150, enter=False)
    page.evaluate("() => window.weighOutScanDone(window.__b)")
    page.evaluate(HOOK_57, "__a")
    page.wait_for_timeout(150)
    assert (_focus(page), _box(page, 57)) == ("57", "425")
    assert not any("wasn't kept" in t for t in _toasts(page)), _toasts(page)


def test_the_kept_spool_scan_takes_the_focus_while_a_scan_read_before_it_is_still_out(wo):
    """A label read first (its answer still out), then #57's scan, then another
    label: #57 answered while the later label is out (kept), then the later
    label (no spool): #57's box takes the focus and the reading typed under
    both, though the first label hasn't been answered. Pins the fallback's
    rule: it waits only for scans read after the kept one (a mutant waiting for
    any scan left #57 out for good)."""
    page, _ = wo
    page.evaluate(SETUP, [])
    page.evaluate(HOOK_OPEN)
    later(page, 700)
    page.evaluate("() => { window.__x = window.weighOutScanStart(); }")
    later(page, 300)
    page.evaluate("() => { window.__a = window.weighOutScanStart(); }")
    press(page, "4", 0, enter=False)
    later(page, 300)
    page.evaluate("() => { window.__y = window.weighOutScanStart(); }")
    press(page, "25", 150, enter=False)
    page.evaluate(HOOK_57, "__a")
    page.evaluate("() => window.weighOutScanDone(window.__y)")
    page.wait_for_timeout(150)
    assert (_focus(page), _box(page, 57)) == ("57", "425")
    page.evaluate("() => window.weighOutScanDone(window.__x)")


def test_the_fallback_goes_to_the_latest_spool_scan_read(wo):
    """Three scans into #6's box, all answered late: #57, #134, then a label
    that names no spool; answered #134 first, then #57, then the label: #134's
    box takes the focus, as the latest scan read that named a spool, never
    #57's. Pins the fallback's choice (a mutant that kept the oldest gave #57
    the focus)."""
    page, open_ = wo
    page.evaluate("() => { window.__holdScans = ['ID:57', 'ID:134', 'LOC:NOWHERE']; }")
    open_()
    for label in ("ID:57", "ID:134", "LOC:NOWHERE"):
        press(page, label, 5)
        later(page, 300)
    _held(page, "scan", 3)
    # The held answers, in the order the scans were sent: #57, #134, the label.
    page.evaluate("() => { window.__answers = window.__held.scan; window.__held.scan = []; window.__answers[1](); }")
    _scan_answered(page, 1)
    page.evaluate("() => window.__answers[0]()")
    _scan_answered(page, 2)
    page.evaluate("() => window.__answers[2]()")
    _scan_answered(page, 3)
    page.wait_for_timeout(200)
    assert _focus(page) == "134"

