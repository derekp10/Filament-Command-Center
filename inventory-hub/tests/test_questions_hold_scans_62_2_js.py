"""Group 62.2: every question on screen holds off other scans, hermetic.

The three-way move question ("Load it instead / Just store it / Cancel") has held off
every other scan since Group 40.3: processScan refuses a scan while it is open, its own
QRs and a bare CMD:CANCEL still answer it, and the refusal is said on the question,
because toasts sit under it. The shorter printing yes / no ("Continue Anyway / Cancel":
a move straight onto or off a printing head, Undo, EJECT ALL, a location delete, Force
Location to Unassigned, the wizard) registered nothing, so a slot label scanned
meanwhile started a second move behind it, and a bare CMD:CANCEL reached no handler:
with the audit panel hidden it went on to the server and ended the audit. The
Quick-Swap confirm (the swap, the deposit, Return) had the same gap (found grounding
62.2).

The real overlay_mount.js, inv_core.js, ui_builder.js, inv_cmd.js (processScan) and
inv_quickswap.js in `isolated_page` (a browser with no network), every request answered
by a stub, so it runs under --offline. test_head_load_confirm_js.py is the three-way's
twin. RED on 152cb6e wherever a test says a scan is held.
"""
from __future__ import annotations

import pytest

from test_head_load_confirm_js import LEAVING, SLOT_DONE, _slot
from test_slow_scan_confirms_js import MODULES

PRINTING = {"toolhead": "XL-3", "printer_name": "XL", "state": "PRINTING"}

PAGE = """<!doctype html><html><head><meta charset="utf-8"></head><body>
<div id="manageModal" class="modal show"><input id="manage-loc-id" value="XL-1"><div id="quickswap-grid">
  <button class="fcc-qs-slot" data-toolhead="XL-1" data-box="LR-MDB-1" data-slot="1" data-spool-id="57"
          onclick="window.quickSwapTap(this)">slot 1</button>
</div></div>
<div id="hostModal" class="modal show"></div>
</body></html>"""

STUBS = r"""
window.__posts = [];
window.__answers = {};
window.__said = [];
window.fetch = function (url, opts) {
    url = String(url);
    const method = (opts && opts.method) || 'GET';
    const body = opts && opts.body ? JSON.parse(opts.body) : null;
    if (method !== 'GET') window.__posts.push({ url, body });
    const path = url.split('?')[0];
    const list = window.__answers[path];
    let ans = [];
    if (list && list.length) ans = list.length > 1 ? list.shift() : list[0];
    return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(JSON.parse(JSON.stringify(ans))),
                             text: () => Promise.resolve(JSON.stringify(ans)) });
};
window.__si = window.setInterval; window.setInterval = () => 0;     // inv_cmd.js's polls: off
"""

SEED = r"""() => {
    window.setInterval = window.__si;
    state.heldSpools = [{ id: 57, display: '#57' }];
    state.allLocations = [
        { LocationID: 'XL', Name: 'XL', Type: 'Printer', toolheads: [{ location_id: 'XL-3', position: 2 }] },
        { LocationID: 'XL-3', Name: 'XL-3', Type: 'Tool Head', 'Max Spools': '1' },
        { LocationID: 'LR-MDB-1', Name: 'LR box', Type: 'Dryer Box', 'Max Spools': '4' },
    ];
    window.refreshManageView = () => {}; window.fetchLocations = () => {}; window.openSpoolDetails = () => {};
    window.checkPrinterForHead = () => Promise.resolve(window.__printing
        ? { active: true, known: true, state: 'PRINTING', printer_name: 'XL' }
        : { active: false, known: true, state: 'IDLE', printer_name: 'XL' });
    // A direct question, as a door shows one: its answers are recorded.
    window.__ask = (id, host) => window.confirmActivePrint({
        activePrint: { toolhead: 'XL-3', printer_name: 'XL', state: 'PRINTING' },
        msg: 'Moving #57 now will disrupt the print. Continue?',
        ids: { overlay: id }, host: host ? document.getElementById(host) : null,
        onConfirm: () => window.__said.push(id + ':yes'),
        onCancel: (why) => window.__said.push(id + ((why && why.superseded) ? ':superseded' : ':no')),
    });
}"""


@pytest.fixture
def qpage(isolated_page):
    page = isolated_page
    page.set_content(PAGE)
    page.add_script_tag(content=STUBS)
    for name in ("overlay_mount.js", "inv_core.js", "ui_builder.js", "inv_cmd.js", "inv_quickswap.js"):
        page.add_script_tag(content=(MODULES / name).read_text(encoding="utf-8"))
    page.evaluate(SEED)
    return page


def _scan(page, text):
    page.evaluate("(t) => window.processScan(t, 'barcode')", text)
    page.wait_for_timeout(120)


def _server_scans(page):
    return page.evaluate("() => window.__posts.filter((p) => p.url === '/api/identify_scan').map((p) => p.body.text)")


def _toasts(page, part):
    return page.evaluate("""(part) => Array.from(document.querySelectorAll('#toast-container > *'))
        .map((t) => ({ msg: t.innerText, cls: t.className })).filter((t) => t.msg.includes(part))""", part)


def _held(page):
    return page.evaluate("() => (window._fccOpenMoveQuestions || []).length")


def _open_slot_question(page):
    """The slot-scan door's printing yes / no: a slot label scanned while #57 runs a
    printing XL-3, which the server answers with the question."""
    page.evaluate("(a) => { window.__answers['/api/identify_scan'] = [a, a]; }", _slot(LEAVING))
    _scan(page, "LOC:LR-MDB-1:SLOT:1")
    page.wait_for_selector("#fcc-active-print-scan-overlay .fcc-apc-yes")
    assert "Continue Anyway" in page.text_content("#fcc-active-print-scan-overlay .fcc-apc-yes")


def test_the_printing_yes_no_holds_off_other_scans_and_cmd_cancel_cancels_it(qpage):
    """RED on 152cb6e: ID:99 and the second slot label went on to the server, behind
    the question, and the bare CMD:CANCEL went there too."""
    page = qpage
    _open_slot_question(page)
    _scan(page, "ID:99")
    _scan(page, "LOC:LR-MDB-1:SLOT:2")
    assert _server_scans(page) == ["LOC:LR-MDB-1:SLOT:1"]
    warned = _toasts(page, "Answer the question on screen first: Continue Anyway or Cancel")
    assert len(warned) == 2 and all("warning" in t["cls"] for t in warned), warned
    status = page.locator("#fcc-active-print-scan-overlay .fcc-apc-status")
    assert status.is_visible() and "(Ignored: LOC:LR-MDB-1:SLOT:2)" in status.text_content()
    _scan(page, "CMD:CANCEL")
    assert page.locator("#fcc-active-print-scan-overlay").count() == 0 and _held(page) == 0
    assert _server_scans(page) == ["LOC:LR-MDB-1:SLOT:1"]
    _scan(page, "ID:99")                                   # free again
    assert _server_scans(page) == ["LOC:LR-MDB-1:SLOT:1", "ID:99"]


def test_its_own_confirm_qr_still_answers_it(qpage):
    """A pin: the question's own CMD:CONFIRM:<sid> replays the move with XL-3
    confirmed, through the scan path."""
    page = qpage
    _open_slot_question(page)
    page.evaluate("(a) => { window.__answers['/api/identify_scan'] = [a]; }", SLOT_DONE)
    sid = page.evaluate("() => Object.keys(window._fccActiveConfirms || {}).pop()")
    _scan(page, f"CMD:CONFIRM:{sid}")
    page.wait_for_timeout(150)
    bodies = page.evaluate("() => window.__posts.filter((p) => p.url === '/api/identify_scan').map((p) => p.body)")
    assert len(bodies) == 2 and bodies[1]["confirmed_toolheads"] == ["XL-3"], bodies
    assert page.locator("#fcc-active-print-scan-overlay").count() == 0 and _held(page) == 0


@pytest.mark.parametrize("how", ["continue", "cancel-button", "escape", "host-closed", "superseded"])
def test_each_way_out_of_the_question_frees_scans(qpage, how):
    """Held while it is open (RED on 152cb6e), free once it is answered, escaped,
    its host window closed, or another question replaced it and was answered."""
    page = qpage
    page.evaluate("() => window.__ask('fcc-q-a', 'hostModal')")
    page.wait_for_selector("#fcc-q-a .fcc-apc-no")
    _scan(page, "ID:99")
    assert _server_scans(page) == [] and _held(page) == 1
    if how == "continue":
        page.wait_for_timeout(800)                          # past any arming of the yes
        page.click("#fcc-q-a .fcc-apc-yes")
    elif how == "cancel-button":
        page.click("#fcc-q-a .fcc-apc-no")
    elif how == "escape":
        page.keyboard.press("Escape")
    elif how == "host-closed":
        page.evaluate("() => document.getElementById('hostModal').dispatchEvent(new Event('hidden.bs.modal'))")
    else:
        page.evaluate("() => window.__ask('fcc-q-a', 'hostModal')")       # the same overlay id
        page.wait_for_timeout(50)
        _scan(page, "ID:98")
        assert _server_scans(page) == [] and _held(page) == 1          # the new one holds them
        page.click("#fcc-q-a .fcc-apc-no")
    page.wait_for_timeout(50)
    assert _held(page) == 0 and page.locator("#fcc-q-a").count() == 0
    _scan(page, "ID:97")
    assert _server_scans(page) == ["ID:97"]


def test_two_open_questions_hold_scans_until_both_are_answered(qpage):
    """RED on 152cb6e: neither held anything."""
    page = qpage
    page.evaluate("() => { window.__ask('fcc-q-a'); window.__ask('fcc-q-b'); }")
    page.wait_for_selector("#fcc-q-b .fcc-apc-no")
    _scan(page, "ID:99")
    page.click("#fcc-q-b .fcc-apc-no")                     # the newer one answered
    _scan(page, "ID:98")
    assert _server_scans(page) == [] and _held(page) == 1
    page.click("#fcc-q-a .fcc-apc-no")
    _scan(page, "ID:97")
    assert _server_scans(page) == ["ID:97"]
    assert page.evaluate("() => window.__said") == ["fcc-q-b:no", "fcc-q-a:no"]


def test_during_an_audit_cmd_cancel_cancels_the_question_not_the_audit(qpage):
    """With the audit panel hidden, a bare CMD:CANCEL at a printing question cancels
    the question. RED on 152cb6e: it went on to the server, whose audit gate reads it
    as the audit's own Cancel and ends the audit."""
    page = qpage
    page.evaluate("() => { state.auditActive = true; state.auditId = 'a1b2-3'; }")
    page.evaluate("() => window.__ask('fcc-q-a')")
    page.wait_for_selector("#fcc-q-a .fcc-apc-no")
    _scan(page, "CMD:CANCEL")
    assert _server_scans(page) == []
    assert page.evaluate("() => window.__said") == ["fcc-q-a:no"]
    assert page.evaluate("() => state.auditActive") is True


@pytest.mark.parametrize("printing", [True, False], ids=["printing", "idle"])
def test_the_quickswap_confirm_holds_off_other_scans(qpage, printing):
    """The Quick-Swap confirm: another label scanned while it is up is refused and
    said on it; a bare CMD:CANCEL cancels it, sending nothing. RED on 152cb6e: the
    label went to the server behind the confirm, and CMD:CANCEL with it."""
    page = qpage
    page.evaluate("(p) => { window.__printing = p; }", printing)
    page.evaluate("() => window.quickSwapTap(document.querySelector('.fcc-qs-slot'))")
    page.wait_for_selector("#fcc-quickswap-confirm-overlay #fcc-quickswap-yes")
    _scan(page, "LOC:LR-MDB-1:SLOT:2")
    assert _server_scans(page) == [] and _held(page) == 1
    status = page.locator("#fcc-quickswap-confirm-status")
    assert status.is_visible() and "Answer the question on screen first: Yes, swap or No, cancel" in status.text_content()
    assert _toasts(page, "Answer the question on screen first: Yes, swap or No, cancel")
    _scan(page, "CMD:CANCEL")
    assert page.locator("#fcc-quickswap-confirm-overlay").count() == 0 and _held(page) == 0
    assert page.evaluate("() => window.__posts.map((p) => p.url).filter((u) => u !== '/api/log_event')") == []
    _scan(page, "ID:99")
    assert _server_scans(page) == ["ID:99"]


def test_the_quickswap_confirms_own_confirm_qr_still_swaps(qpage):
    """A pin: on a printing head its own CMD:CONFIRM:<sid> swaps, with XL-1 confirmed."""
    page = qpage
    page.evaluate("() => { window.__printing = true; window.__answers['/api/quickswap'] = [{ status: 'success' }]; }")
    page.evaluate("() => window.quickSwapTap(document.querySelector('.fcc-qs-slot'))")
    page.wait_for_selector("#fcc-quickswap-confirm-overlay .fcc-confirm-qr-row")
    sid = page.evaluate("() => Object.keys(window._fccActiveConfirms || {}).pop()")
    _scan(page, f"CMD:CONFIRM:{sid}")
    page.wait_for_function("() => window.__posts.some((p) => p.url === '/api/quickswap')")
    body = page.evaluate("() => window.__posts.find((p) => p.url === '/api/quickswap').body")
    assert body["confirmed_toolheads"] == ["XL-1"], body
    assert _held(page) == 0
