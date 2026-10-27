"""Every weight box hands a scan to the scan path, never saves it, and the
weigh-out list keeps the focus where a person types (Group 57 review, round 6),
hermetic.

Runs the REAL overlay_mount.js, inv_core.js, weight_utils.js and
inv_weigh_out.js (its real rows, save and redraw), with the weigh-out window's
real markup (templates/components/modals_weigh_out.html), in `isolated_page` (a
chromium with no route to any network), so it RUNS under --offline. Real keys
on the page's fake clock, as test_quick_weigh_scan_js.py types them.

The defects (RED on 5b5a18e, each test says how): after a row's Enter saved
it, the focus fell to the page (the next box was looked for among the enabled
ones after the saved one was disabled), and so did it after every redraw (a
captured scan, a heartbeat that changed a spool): the person's next reading
went to the scan path as a spool id, and a spool joined the scan buffer unseen.
The list focused its first box half a second after it opened even while a scan
was arriving, splitting it: the label's digits that reached the box were saved
as that spool's weight. The post-archive empty-weight prompt's box (its shape:
a number box with its own Enter handler) saved a label scanned into it as the
filament's empty weight. And Escape went to the overlay mounted first, not the
one on top. Pinned too: every weight box FCC draws carries the class the one
capture serves.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from test_quick_weigh_scan_js import FAKE_CLOCK, later, press
from test_slow_scan_slash_js import _accumulator

HUB = Path(__file__).resolve().parent.parent
MODULES = HUB / "static" / "js" / "modules"
WEIGH_OUT = (HUB / "templates" / "components" / "modals_weigh_out.html").read_text(encoding="utf-8")

PAGE = ("<!doctype html><html><head><meta charset='utf-8'><style>.modal{display:none}.modal.show{display:block}"
        "</style></head><body>" + WEIGH_OUT + "</body></html>")

STUBS = r"""
window.__scans = [];
window.processScan = function (t) { window.__scans.push(t); };
window.showToast = function () {};
window.__posts = [];
window.__spools = {
    6: { id: 6, initial_weight: 1000, used_weight: 31, spool_weight: 167,
         filament: { name: 'Red', material: 'PLA', vendor: { name: 'Acme' } } },
    134: { id: 134, initial_weight: 1000, used_weight: 0, spool_weight: 200,
           filament: { name: 'Blue', material: 'PETG', vendor: { name: 'Acme' } } },
    57: { id: 57, initial_weight: 750, used_weight: 100, spool_weight: 150,
          filament: { name: 'Green', material: 'PLA', vendor: { name: 'Acme' } } },
};
window.fetch = function (url, opts) {
    url = String(url);
    if (opts && opts.method && opts.method !== 'GET') window.__posts.push({ url, body: opts.body ? JSON.parse(opts.body) : null });
    const m = /spool_details\?id=(\d+)/.exec(url);
    const body = m ? (window.__spools[m[1]] || {}) : { status: 'success', success: true };
    return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(body) });
};
"""

SETUP = r"""() => {
    modals.weighOutModal = { show: () => document.getElementById('weighOutModal').classList.add('show') };
    window.renderBuffer = () => {};
    state.heldSpools = [
        { id: 6, display: 'Acme - PLA - Red', color: 'cc0000', remaining_weight: 969 },
        { id: 134, display: 'Acme - PETG - Blue', color: '0000cc', remaining_weight: 1000 },
        { id: 57, display: 'Acme - PLA - Green', color: '00cc00', remaining_weight: 650 },
    ];
}"""


@pytest.fixture
def wo(isolated_page):
    page = isolated_page
    page.set_content(PAGE)
    page.add_script_tag(content=STUBS)
    for name in ("overlay_mount.js", "inv_core.js", "weight_utils.js", "inv_weigh_out.js"):
        page.add_script_tag(content=(MODULES / name).read_text(encoding="utf-8"))
    page.add_script_tag(content=_accumulator())          # last, as on the page
    page.evaluate(SETUP)
    page.evaluate(FAKE_CLOCK)
    return page


def _focus(page):
    return page.evaluate("() => { const a = document.activeElement; return a && a.dataset && a.dataset.id ? a.dataset.id : (a ? a.tagName : null); }")


def _box(page, sid):
    return page.evaluate("(id) => (document.querySelector(`.weigh-input[data-id=\"${id}\"]`) || {}).value", sid)


def _open(page):
    page.evaluate("() => window.openWeighOutModal()")
    page.wait_for_function("() => document.activeElement && document.activeElement.dataset"
                           " && document.activeElement.dataset.id === '6'")


def test_after_a_save_the_next_box_keeps_the_focus(wo):
    """A row's reading and Enter save it, and the next row's box has the focus,
    through the saved row's fade and the redraw after it: the next reading goes
    into it. RED on 5b5a18e: the focus fell to the page, and the next reading
    ("42", then Enter) went to the scan path as spool #42."""
    page = wo
    _open(page)
    press(page, "500", 200)
    page.wait_for_function("() => window.__posts.some((p) => p.url === '/api/spool/update')")
    assert _focus(page) == "134"
    page.wait_for_timeout(500)                     # the saved row fades and the list is drawn again
    assert _focus(page) == "134"
    later(page, 600)
    press(page, "42", 200, enter=False)
    assert _box(page, 134) == "42" and page.evaluate("() => window.__scans") == []


def test_a_redraw_keeps_the_focus_and_a_label_still_arriving(wo):
    """The list is drawn again (a heartbeat that changed a spool) while a
    person types a reading: the box keeps the focus and the reading. One drawn
    again while a label is still arriving: the label finishes in the box that
    took its place and reaches the scan path whole, the reading kept and
    nothing saved. RED on 5b5a18e: the focus fell to the page, so the person's
    next key went to the scan path, and the label's last keys too."""
    page = wo
    _open(page)
    press(page, "42", 200, enter=False)
    page.evaluate("() => document.dispatchEvent(new CustomEvent('inventory:buffer-updated'))")
    assert _focus(page) == "6" and _box(page, 6) == "42"
    later(page, 300)
    press(page, "3", 200, enter=False)
    assert _box(page, 6) == "423"
    later(page, 3000)
    press(page, "ID:5", 5, enter=False)
    page.evaluate("() => document.dispatchEvent(new CustomEvent('inventory:buffer-updated'))")
    press(page, "7", 5)
    page.wait_for_timeout(20)
    assert page.evaluate("() => window.__scans") == ["ID:57"]
    assert _box(page, 6) == "423" and page.evaluate("() => window.__posts") == []


def test_a_label_carries_on_where_a_redraw_sends_no_focusout(wo):
    """The same redraw in a browser that sends no focusout for the box it
    removes (Chromium sends one, and its label goes to the scan buffer and back
    into the new box): the label carries on in the box that took its place, and
    nothing is saved. Simulated by stopping focusout before the page sees it.
    Unpinned until it was written: Chromium's own focusout kept every test
    green without it."""
    page = wo
    _open(page)
    press(page, "42", 200, enter=False)
    page.evaluate("() => window.addEventListener('focusout', (e) => e.stopImmediatePropagation(), true)")
    later(page, 300)
    press(page, "ID:5", 5, enter=False)
    page.evaluate("() => document.dispatchEvent(new CustomEvent('inventory:buffer-updated'))")
    press(page, "7", 5)
    page.wait_for_timeout(20)
    assert page.evaluate("() => window.__scans") == ["ID:57"]
    assert _box(page, 6) == "42" and page.evaluate("() => window.__posts") == []


def test_a_slower_scanners_label_in_a_row_is_the_scans(wo):
    """A label scanned at 250 ms a key into a row's box: it reaches the scan
    path, and the row's own Enter (which saves) never sees it. RED on 5b5a18e:
    the box kept "57" and its Enter saved 57 g left for spool #6."""
    page = wo
    _open(page)
    press(page, "ID:57", 250)
    page.wait_for_timeout(50)
    assert page.evaluate("() => [window.__scans, window.__posts]") == [["ID:57"], []]
    assert _box(page, 6) == ""


def test_the_first_box_waits_for_a_scan_to_finish(wo):
    """The window opened while a label is still arriving (the WEIGH QR and the
    first spool's label scanned back to back): its first box takes the focus
    only once the scan is done. RED on 5b5a18e: the box took it half a second
    after the window opened, splitting the scan, and the label's digits that
    reached the box were saved as spool #6's weight."""
    page = wo
    page.evaluate("() => { state.scanBuffer = 'ID:'; state.scanStartTime = Date.now(); window.openWeighOutModal(); }")
    page.wait_for_timeout(800)                     # real time: past the half second it waits
    assert _focus(page) != "6"
    page.evaluate("() => { state.scanBuffer = ''; }")
    page.wait_for_function("() => document.activeElement && document.activeElement.dataset"
                           " && document.activeElement.dataset.id === '6'", timeout=3000)


BOX_PAGE = ("<!doctype html><html><head><meta charset='utf-8'></head><body>"
            "<input type='number' class='form-control fcc-weight-box' id='b'></body></html>")


@pytest.mark.parametrize("ms", [5, 250])
def test_a_weight_box_with_its_own_enter_handler_sees_only_a_persons_enter(isolated_page, ms):
    """A weight box whose own keydown listener saves on Enter (the post-archive
    empty-weight prompt's shape): a label scanned into it goes to the scan path
    and that listener never sees its Enter; a person's tare and Enter reach it.
    RED on 5b5a18e: the prompt's box had no capture, so the label's digits
    ("57") were saved as the filament's empty weight."""
    page = isolated_page
    page.set_content(BOX_PAGE)
    page.add_script_tag(content=STUBS)
    page.add_script_tag(content=(MODULES / "inv_core.js").read_text(encoding="utf-8"))
    page.evaluate("""() => { window.__saved = []; document.getElementById('b').addEventListener('keydown', (e) => {
        if (e.key === 'Enter') { e.preventDefault(); window.__saved.push(e.target.value); } }); }""")
    page.evaluate(FAKE_CLOCK)
    page.locator("#b").focus()
    press(page, "ID:57", ms)
    assert page.evaluate("() => [window.__scans, window.__saved, document.getElementById('b').value]") \
        == [["ID:57"], [], ""]
    later(page, 600)
    press(page, "167", 200)
    assert page.evaluate("() => window.__saved") == ["167"]


def test_every_weight_box_fcc_draws_is_a_weight_box():
    """The one capture (inv_core.js) serves the class: the Quick-Weigh field,
    the weigh-out list's boxes, the missing-tare prompt's box and the
    post-archive empty-weight prompt's box each carry it, and no speed-only
    rule is left for a weight box."""
    def src(name):
        return (MODULES / name).read_text(encoding="utf-8").replace("\r\n", "\n")
    checks = {
        "weight_entry.js": r'id="fcc-we-input" class="[^"]*\bfcc-weight-box\b',
        "inv_weigh_out.js": r'class="[^"]*\bweigh-input fcc-weight-box\b',
        "weight_utils.js": r'id="\$\{overlayId\}-input"\s+class="[^"]*\bfcc-weight-box\b',
        "inv_details.js": r'id="fcc-archive-empty-wt"\s+class="[^"]*\bfcc-weight-box\b',
    }
    for name, pattern in checks.items():
        assert re.search(pattern, src(name)), name
    core = src("inv_core.js")
    assert "installWeightScanCapture({ match: (el) => !!(el.classList && el.classList.contains('fcc-weight-box')) });" in core
    assert "perKey" not in core
    for name in ("weight_entry.js", "inv_weigh_out.js"):
        assert "installFieldScanCapture" not in src(name), name


MOUNT_JS = """([id, tier]) => { window.__esc = window.__esc || [];
    window.mountOverlay({ id, tier, content: `<div><button id="${id}-b">x</button></div>`,
        onEscape: () => { window.__esc.push(id); window.closeOverlay(id); } }); }"""


def test_escape_goes_to_the_overlay_on_top(isolated_page):
    """Two overlays up: Escape is answered by the one on top (the higher tier,
    then the last mounted), and window.isTopOverlay says which that is. RED on
    5b5a18e: the first one mounted answered it (Escape in the missing-tare
    prompt cancelled the Quick-Weigh under it, the prompt left up)."""
    page = isolated_page
    page.set_content("<!doctype html><html><head><meta charset='utf-8'></head><body></body></html>")
    page.add_script_tag(content=(MODULES / "overlay_mount.js").read_text(encoding="utf-8"))
    page.evaluate(MOUNT_JS, ["ov-a", "standard"])
    page.evaluate(MOUNT_JS, ["ov-b", "standard"])
    assert page.evaluate("() => [window.isTopOverlay(document.getElementById('ov-a')),"
                         " window.isTopOverlay(document.getElementById('ov-b'))]") == [False, True]
    page.keyboard.press("Escape")
    assert page.evaluate("() => [window.__esc, !!document.getElementById('ov-a'), !!document.getElementById('ov-b')]") \
        == [["ov-b"], True, False]
    page.keyboard.press("Escape")
    assert page.evaluate("() => window.__esc") == ["ov-b", "ov-a"]
    page.evaluate(MOUNT_JS, ["ov-c", "confirm"])
    page.evaluate(MOUNT_JS, ["ov-d", "standard"])
    page.keyboard.press("Escape")
    page.keyboard.press("Escape")
    assert page.evaluate("() => window.__esc") == ["ov-b", "ov-a", "ov-c", "ov-d"]
