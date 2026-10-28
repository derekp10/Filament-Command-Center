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
window.__answerMs = 50;
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
    if (m) ans = window.__spools[m[1]] || {};
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
    const ms = url.includes('/api/identify_scan') ? window.__answerMs : 0;
    return new Promise((res) => setTimeout(() => res({ ok: true, status: 200, json: () => Promise.resolve(ans) }), ms));
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
    page.wait_for_function("() => window.__posts.some((p) => p.url === '/api/identify_scan')")
    page.wait_for_timeout(120)
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
    page.evaluate("() => { window.__answerMs = 500; }")
    open_()
    press(page, "ID:57", 5)
    later(page, 300)
    press(page, "4", 0, enter=False)          # the server hasn't answered yet
    assert _box(page, 6) == "4"
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
