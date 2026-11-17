"""Group 62.3: a double click answers no question, hermetic.

A question can open with its yes under the pointer, and the second click of a double
click on the button that asked it then answers a question nobody has read. Group 58 gave
window.confirmActivePrint `armAfterMs` (the yes takes no click until that long after it
opens) for the audit's Done, and only there. Now every question's answers that do
something wait 700 ms (Group 58's double-press figure) for a click:
- confirmActivePrint's yes and its "Just store it", unless a door passes its own
  `armAfterMs` (0 only with a comment saying why);
- the Quick-Swap confirm's Yes;
- the "Record it as coming from…" question's slots and No box (it opens where the
  Printer picker's question was, right after "Load it instead");
- the slot picker's Swap / Overwrite / Swap it out / Put it in slot N (an occupied tile
  opens them in the panel under the pointer).
Cancel (and Back) takes a click at once, and Enter and the QRs never wait: neither is a
second click. Harnesses set `window.fccQuestionArmMs` to 0 (read as each question
opens); these tests take it away, so the default is what runs.

The real overlay_mount.js, inv_core.js, ui_builder.js, inv_cmd.js, slot_picker.js and
inv_quickswap.js in `isolated_page` (no network), real clicks, the clock a fake one
(`Date.now`) the test moves. RED on the commit before 62.3 for every "takes no click"
check; the "at once" checks pin what was right.
"""
from __future__ import annotations

import pytest

from test_slot_picker_double_enter_62_10_js import OCCUPIED_MODEL
from test_slow_scan_confirms_js import MODULES

PAGE = "<!doctype html><html><head><meta charset='utf-8'></head><body></body></html>"

STUBS = r"""
window.__said = [];
window.__posts = [];
window.__models = {};
window.fetch = function (url, opts) {
    url = String(url);
    const method = (opts && opts.method) || 'GET';
    if (method !== 'GET') window.__posts.push({ url, body: opts && opts.body ? JSON.parse(opts.body) : null });
    let ans = {};
    if (url.includes('/api/placement_options')) {
        const loc = (new URL(url, 'http://x/')).searchParams.get('location');
        ans = window.__models[loc] || { read_ok: false, read_error: 'no model' };
    }
    return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(JSON.parse(JSON.stringify(ans))),
                             text: () => Promise.resolve(JSON.stringify(ans)) });
};
window.__si = window.setInterval; window.setInterval = () => 0;
// The fake clock: Date.now moves only when the test says so.
(() => { const base = Date.now(); window.__T = 0; Date.now = () => base + window.__T; })();
"""

THREE_WAY = r"""() => { window.__said = []; const rec = (w) => () => window.__said.push(w);
    window.confirmActivePrint({ title: 'Load #57 onto XL-1?', msg: 'LR-MDB-1 slot 1 feeds XL-1.',
        loadLabel: 'Load it instead', storeLabel: 'Just store it in LR-MDB-1 slot 1',
        onConfirm: rec('load'), onStore: rec('store'), onCancel: rec('no') }); }"""
YES_NO = r"""(arm) => { window.__said = []; const rec = (w) => () => window.__said.push(w);
    const o = { activePrint: { toolhead: 'XL-3', printer_name: 'XL', state: 'PRINTING' },
        msg: 'Moving #57 now will disrupt the print. Continue?', onConfirm: rec('yes'), onCancel: rec('no') };
    if (arm !== null) o.armAfterMs = arm;
    window.confirmActivePrint(o); }"""
Q = "#fcc-active-print-confirm-overlay"


@pytest.fixture
def apage(isolated_page):
    page = isolated_page
    page.set_content(PAGE)
    page.add_script_tag(content=STUBS)
    for name in ("overlay_mount.js", "inv_core.js", "ui_builder.js", "inv_cmd.js", "slot_picker.js", "inv_quickswap.js"):
        page.add_script_tag(content=(MODULES / name).read_text(encoding="utf-8"))
    page.evaluate("() => { window.setInterval = window.__si; delete window.fccQuestionArmMs; }")
    return page


def _later(page, ms):
    page.evaluate("(ms) => { window.__T += ms; }", ms)


def _said(page):
    return page.evaluate("() => window.__said.slice()")


def test_the_yes_and_the_store_take_no_click_for_700_ms_and_cancel_takes_one_at_once(apage):
    page = apage
    page.evaluate(THREE_WAY)
    page.wait_for_selector(f"{Q} .fcc-apc-yes")
    page.click(f"{Q} .fcc-apc-yes")
    page.click(f"{Q} .fcc-apc-store")
    _later(page, 699)
    page.click(f"{Q} .fcc-apc-yes")
    assert _said(page) == [] and page.locator(Q).count() == 1, "a click inside 700 ms answered the question"
    _later(page, 1)
    page.click(f"{Q} .fcc-apc-store")
    assert _said(page) == ["store"]
    page.evaluate(THREE_WAY)
    page.wait_for_selector(f"{Q} .fcc-apc-no")
    page.click(f"{Q} .fcc-apc-no")                       # Cancel never waits
    assert _said(page) == ["no"]


@pytest.mark.parametrize("arm, at_once", [(None, False), (0, True), (300, False)], ids=["default", "zero", "300"])
def test_the_yes_no_waits_unless_its_door_says_otherwise(apage, arm, at_once):
    page = apage
    page.evaluate(YES_NO, arm)
    page.wait_for_selector(f"{Q} .fcc-apc-yes")
    page.click(f"{Q} .fcc-apc-yes")
    assert (_said(page) == ["yes"]) is at_once
    if not at_once:
        _later(page, 700)
        page.click(f"{Q} .fcc-apc-yes")
        assert _said(page) == ["yes"]


def test_enter_and_the_qrs_never_wait(apage):
    """A pin: neither is a second click."""
    page = apage
    page.evaluate(THREE_WAY)
    page.wait_for_function(f"() => document.activeElement && document.activeElement.matches('{Q} .fcc-apc-store')")
    page.keyboard.press("Enter")
    assert _said(page) == ["store"]
    page.evaluate(THREE_WAY)
    page.wait_for_selector(f"{Q} .fcc-apc-yes")
    sid = page.evaluate("() => Object.keys(window._fccActiveConfirms || {}).pop()")
    assert page.evaluate("(t) => window.routeConfirmScan(t)", f"CMD:CONFIRM:{sid}") is True
    assert _said(page) == ["load"]


def test_the_harness_seam_is_set_on_every_isolated_page(isolated_page):
    """conftest's isolated_page sets window.fccQuestionArmMs = 0 (an init script), and it
    survives set_content, so the other tests press a question's yes at once."""
    isolated_page.set_content(PAGE)
    assert isolated_page.evaluate("() => window.fccQuestionArmMs") == 0


def test_the_seam_lets_a_harness_click_at_once(apage):
    """window.fccQuestionArmMs, read as a question opens: 0 takes the click at once."""
    page = apage
    page.evaluate("() => { window.fccQuestionArmMs = 0; }")
    page.evaluate(THREE_WAY)
    page.wait_for_selector(f"{Q} .fcc-apc-yes")
    page.click(f"{Q} .fcc-apc-yes")
    assert _said(page) == ["load"]


def test_the_quickswap_confirms_yes_waits_and_no_does_not(apage):
    page = apage
    open_ = """() => { window.checkPrinterForHead = () => Promise.resolve({ active: false, known: true, state: 'IDLE', printer_name: 'XL' });
        const b = document.createElement('button');
        Object.assign(b.dataset, { toolhead: 'XL-1', box: 'LR-MDB-1', slot: '1', spoolId: '57' });
        window.quickSwapTap(b); }"""
    page.evaluate(open_)
    page.wait_for_selector("#fcc-quickswap-yes")
    page.click("#fcc-quickswap-yes")
    page.wait_for_timeout(50)
    assert page.locator("#fcc-quickswap-confirm-overlay").count() == 1
    assert [p for p in page.evaluate("() => window.__posts.map((p) => p.url)") if p != "/api/log_event"] == []
    _later(page, 700)
    page.click("#fcc-quickswap-yes")
    page.wait_for_function("() => window.__posts.some((p) => p.url === '/api/quickswap')")
    _later(page, 5000)
    page.evaluate(open_)
    page.wait_for_selector("#fcc-quickswap-no")
    page.click("#fcc-quickswap-no")                      # No never waits
    assert page.locator("#fcc-quickswap-confirm-overlay").count() == 0


RECORD = r"""() => { window.__rs = undefined;
    _askRecordSource({ head: 'XL-1', spool_location: '', feeds: [
        { box: 'LR-MDB-1', slot: '1', free: true }, { box: 'LR-MDB-1', slot: '3', free: true }] }, 57, null)
      .then((r) => { window.__rs = r; }); }"""


def test_the_record_source_questions_answers_wait_and_cancel_does_not(apage):
    page = apage
    page.evaluate(RECORD)
    page.wait_for_selector("#fcc-record-source .fcc-rs-none")
    page.click("#fcc-record-source .fcc-rs-opt[data-rs-i='0']")
    page.click("#fcc-record-source .fcc-rs-none")
    page.wait_for_timeout(50)
    assert page.evaluate("() => window.__rs") is None and page.locator("#fcc-record-source").count() == 1
    _later(page, 700)
    page.click("#fcc-record-source .fcc-rs-opt[data-rs-i='0']")
    page.wait_for_function("() => window.__rs !== undefined")
    assert page.evaluate("() => window.__rs") == {"box": "LR-MDB-1", "slot": "1"}
    page.evaluate(RECORD)
    page.wait_for_selector("#fcc-record-source .fcc-rs-cancel")
    page.click("#fcc-record-source .fcc-rs-cancel")      # Cancel never waits
    page.wait_for_function("() => window.__rs !== undefined")
    assert page.evaluate("() => window.__rs") is None


def test_the_slot_pickers_swap_waits_and_back_does_not(apage):
    """An occupied tile opens Swap / Overwrite / Back in the panel under the pointer."""
    page = apage
    page.evaluate("(m) => { window.__models = { 'CR-MDB-1': m }; window.__picked = undefined;"
                  " window.openSlotPicker({ location: 'CR-MDB-1', spool: 6 }).then((r) => { window.__picked = r; }); }",
                  OCCUPIED_MODEL)
    page.wait_for_function("() => document.querySelectorAll('#fcc-slot-picker .fcc-sp-tile').length > 0")
    page.click("#fcc-slot-picker .fcc-sp-tile[data-sp-idx='1']")
    page.wait_for_selector("#fcc-slot-picker [data-sp-choice='swap']")
    page.click("#fcc-slot-picker [data-sp-choice='swap']")
    page.click("#fcc-slot-picker [data-sp-choice='overwrite']")
    page.wait_for_timeout(50)
    assert page.evaluate("() => window.__picked === undefined"), "a click inside 700 ms chose for the slot's spool"
    page.click("#fcc-slot-picker [data-sp-choice='back']")          # Back never waits
    page.wait_for_selector("#fcc-slot-picker .fcc-sp-tile")
    page.click("#fcc-slot-picker .fcc-sp-tile[data-sp-idx='1']")
    page.wait_for_selector("#fcc-slot-picker [data-sp-choice='swap']")
    _later(page, 700)
    page.click("#fcc-slot-picker [data-sp-choice='swap']")
    page.wait_for_function("() => window.__picked !== undefined")
    assert page.evaluate("() => window.__picked && window.__picked.choice") == "swap"
