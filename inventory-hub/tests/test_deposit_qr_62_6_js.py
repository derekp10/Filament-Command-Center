"""Group 62.6: DEPOSIT HERE's QR does what its click does, hermetic.

The Location Manager's ⬇️ DEPOSIT HERE card placed only the spool READY TO SLOT shows
when clicked, but its QR was the place's own LOC: label, which files the whole buffer
there (or opens a picker for each spool in a box with slots or on a Printer row); the
code's comment said the two matched. Its QR is CMD:DEPOSIT:<place> now, a code only the
page reads: scanned while the Location Manager is open on that place, it runs the card's
click (the spool shown, through the slot or Printer picker where the click opens one);
anywhere else, during an audit or a bulk move, it is refused with a 7 s warning and a
log line, and nothing moves. The place's printed LOC: label still files the buffer.

The real inv_core.js, ui_builder.js, inv_cmd.js and inv_loc_mgr.js under node
(test_audit_page_58_js.py's harness). RED on the commit before 62.6 unless a test says it
pins what was right.
"""
from __future__ import annotations

import pytest

from test_audit_page_58_js import LM, SESSION, _run  # noqa: F401
from test_core1_return_ejectall_js import pytestmark  # noqa: F401  (skip without node)
from test_slow_scan_confirms_js import MODULES

SETUP = r"""
state.allLocations = (state.allLocations || []).concat([
  { LocationID: 'SHELF-1', Name: 'Shelf 1', Type: 'Shelf', 'Max Spools': '' }]);
state.heldSpools = [{ id: 57, display: '#57' }, { id: 99, display: '#99' }];
window.__picks = [];
window.openSlotPicker = () => Promise.resolve(null);
window._placeBufferWithPicker = (loc, ids) => { window.__picks.push([loc, ids]); };
answerWith('/api/manage_contents', [{ status: 'success', action: 'add', moved: 57 }]);
const openOn = (loc) => {
  document.getElementById('manageModal').classList.add('show');
  document.getElementById('manage-loc-id').value = loc;
};
const sent = () => __rec.fetches.filter(f => f.method !== 'GET' && f.url !== '/api/log_event')
  .map(f => [f.url, f.body && (f.body.spool_id || f.body.text || null)]);
"""


def test_the_cards_qr_is_its_own_code_drawn_where_the_card_is():
    src = (MODULES / "inv_loc_mgr.js").read_text(encoding="utf-8")
    assert src.count("generateSafeQR('qr-deposit-trigger', 'CMD:DEPOSIT:' + safeId") == 3
    assert "generateSafeQR('qr-deposit-trigger', 'LOC:'" not in src


def test_scanned_on_its_own_place_it_places_only_the_spool_shown(tmp_path):
    """RED on the commit before 62.6: the code went to the server as a scan."""
    res = _run(tmp_path, SETUP + """
openOn('SHELF-1');
window.processScan('CMD:DEPOSIT:SHELF-1', 'barcode');
await __settle(80);
return { sent: sent(), picks: window.__picks };
""", modules=LM)
    adds = [b for u, b in res["sent"] if u == "/api/manage_contents"]
    assert len(adds) == 1 and str(adds[0]) in ("57", "ID:57"), res     # #57 alone: the spool shown
    assert not any(u == "/api/identify_scan" for u, _ in res["sent"]), res
    assert res["picks"] == []


@pytest.mark.parametrize("place", ["LR-MDB-1", "XL"], ids=["box-with-slots", "printer-row"])
def test_on_a_box_with_slots_or_a_printer_row_it_opens_the_picker_for_that_one_spool(tmp_path, place):
    """As the click does (Group 40.5): one picker, for the spool shown."""
    res = _run(tmp_path, SETUP + """
openOn(%r);
window.processScan('CMD:DEPOSIT:' + %r, 'barcode');
await __settle(80);
return { sent: sent(), picks: window.__picks };
""" % (place, place), modules=LM)
    assert res["picks"] == [[place, [57]]] and res["sent"] == [], res


REFUSED = {
    "window-closed": "",
    "another-place": "openOn('SHELF-1');",
    "an-audit": "openOn('SHELF-1'); await running(SESSION);",
    "a-bulk-move": "openOn('SHELF-1'); window.FCC_BULK_MOVE_ENABLED = true; state.bulkMoveActive = true;",
}
TEXT = {"window-closed": "CMD:DEPOSIT:SHELF-1", "another-place": "CMD:DEPOSIT:LR-MDB-1",
        "an-audit": "CMD:DEPOSIT:SHELF-1", "a-bulk-move": "CMD:DEPOSIT:SHELF-1"}


@pytest.mark.parametrize("case", list(REFUSED))
def test_anywhere_else_it_is_refused_and_said_and_nothing_moves(tmp_path, case):
    """RED on the commit before 62.6: it went to the server."""
    res = _run(tmp_path, SETUP + """
%s
window.processScan(%r, 'barcode');
await __settle(80);
return { sent: sent(), picks: window.__picks, toasts: timed(), log: logLines() };
""" % (REFUSED[case], TEXT[case]), modules=LM)
    assert res["sent"] == [] and res["picks"] == [], res
    warned = [t for t in res["toasts"] if t["type"] in ("warning", "info")]
    assert warned, res["toasts"]
    assert any("DEPOSIT" in line for line in res["log"]), res["log"]


def test_the_places_own_label_still_files_the_whole_buffer(tmp_path):
    """A pin: the printed LOC: label goes to the server, which files every buffered
    spool there."""
    res = _run(tmp_path, SETUP + """
openOn('SHELF-1');
window.processScan('LOC:SHELF-1', 'barcode');
await __settle(80);
return { scans: scans() };
""", modules=LM)
    assert res["scans"] == ["LOC:SHELF-1"]


# --- the review round (2026-11-17) -------------------------------------------------------

def test_a_scanners_double_read_deposits_once(tmp_path):
    """All three reviewers: the QR read twice (a scanner's double read, the second
    queued behind the first's processing dim) deposited the NEXT spool too, since
    CMD:DEPOSIT: wasn't under the LOC: double-read rule the old QR had. RED before the
    review's fix: two adds, #57 then #99."""
    res = _run(tmp_path, SETUP + """
openOn('SHELF-1');
const t0 = Date.now();
window.processScan('CMD:DEPOSIT:SHELF-1', 'barcode', t0);
await __settle(80);
state.heldSpools = state.heldSpools.filter((s) => s.id !== 57);     // the first move landed
window.processScan('CMD:DEPOSIT:SHELF-1', 'barcode', t0 + 30);       // its double read, replayed
await __settle(80);
return { sent: sent(), toasts: toasts().map((t) => t.msg) };
""", modules=LM)
    adds = [b for u, b in res["sent"] if u == "/api/manage_contents"]
    assert len(adds) == 1 and str(adds[0]).endswith("57"), res
    assert any("second read" in t for t in res["toasts"]), res["toasts"]


def test_a_refused_read_is_no_read_and_the_label_acts_once_the_window_is_open(tmp_path):
    """A refusal (no window open) doesn't count as the label's read: scanned again a
    moment later, with the window open, it deposits (Derek: no hidden stop)."""
    res = _run(tmp_path, SETUP + """
const t0 = Date.now();
window.processScan('CMD:DEPOSIT:SHELF-1', 'barcode', t0);
await __settle(40);
openOn('SHELF-1');
window.processScan('CMD:DEPOSIT:SHELF-1', 'barcode', t0 + 400);
await __settle(80);
return { sent: sent() };
""", modules=LM)
    assert [u for u, _ in res["sent"]].count("/api/manage_contents") == 1, res


@pytest.mark.parametrize("what", ["an-audit", "a-bulk-move"])
def test_the_cards_click_waits_as_its_qr_does(tmp_path, what):
    """Two reviewers: during an audit or a bulk move the QR was refused while the card's
    click still moved the spool shown. RED before the review's fix: the click posted."""
    setup = {"an-audit": "await running(SESSION);",
             "a-bulk-move": "window.FCC_BULK_MOVE_ENABLED = true; state.bulkMoveActive = true;"}[what]
    res = _run(tmp_path, SETUP + """
openOn('SHELF-1');
%s
window.depositShownSpool('SHELF-1');
await __settle(80);
return { sent: sent(), picks: window.__picks, toasts: toasts().map((t) => t.msg) };
""" % setup, modules=LM)
    assert res["sent"] == [] and res["picks"] == [], res
    assert any("DEPOSIT HERE waits until" in t for t in res["toasts"]), res["toasts"]


@pytest.mark.parametrize("modal", ["confirm", "safety"])
def test_behind_a_gating_dialog_the_qr_moves_nothing(tmp_path, modal):
    """Two reviewers: CMD:DEPOSIT: ran before the gating-dialog gate, so with "Clear
    entire Buffer?" or "Nuke all?" up it moved the top spool behind the dialog (the old
    LOC: QR was dropped there). RED before the review's fix."""
    res = _run(tmp_path, SETUP + """
openOn('SHELF-1');
state.activeModal = %r;
window.processScan('CMD:DEPOSIT:SHELF-1', 'barcode');
await __settle(80);
return { sent: sent(), picks: window.__picks };
""" % modal, modules=LM)
    assert res["sent"] == [] and res["picks"] == [], res


# --- the second review round (2026-11-17) ------------------------------------------------

# The first move's answer held until the test releases it (a head whose printer is slow
# to answer, a slow Spoolman).
HOLD_MOVE = r"""
let release;
const held = new Promise((r) => { release = r; });
const real = window.fetch;
window.fetchT = (u, o) => (u === '/api/manage_contents' ? held.then(() => real(u, o)) : real(u, o));
"""


def test_a_second_read_while_the_first_move_is_out_deposits_nothing_more(tmp_path):
    """Two reviewers of the second round: the QR's read counted as answered as it was
    read, where a place's LOC: label stays in flight until the server answers. So a second
    read 1.5 s or more after the first, held by the scan queue while the first move was
    out, went out once it landed and deposited the NEXT spool there (on a head, Smart Load
    then took the first back off). RED before the fix: two adds, #57 then #99."""
    res = _run(tmp_path, SETUP + HOLD_MOVE + """
openOn('SHELF-1');
window.processScan('CMD:DEPOSIT:SHELF-1', 'barcode', Date.now());
await __settle(1600);                   // the first move is still out
const second = Date.now();              // its second read, which the scan queue holds
release();
await __settle(80);                     // the first move lands: #57 leaves the buffer
window.processScan('CMD:DEPOSIT:SHELF-1', 'barcode', second);   // the queue sends it on
await __settle(80);
return { sent: sent(), toasts: toasts().map((t) => t.msg) };
""", modules=LM)
    adds = [b for u, b in res["sent"] if u == "/api/manage_contents"]
    assert len(adds) == 1 and str(adds[0]).endswith("57"), res
    assert any("second read" in t for t in res["toasts"]), res["toasts"]


REFUSAL = {
    "an-audit": ("await running(SESSION);", "state.auditActive = false;"),
    "a-bulk-move": ("window.FCC_BULK_MOVE_ENABLED = true; state.bulkMoveActive = true;", "state.bulkMoveActive = false;"),
    "a-confirm-dialog": ("state.activeModal = 'confirm';", "state.activeModal = null;"),
    "a-safety-dialog": ("state.activeModal = 'safety';", "state.activeModal = null;"),
    "an-empty-buffer": ("state.heldSpools = [];",
                        "state.heldSpools = [{ id: 57, display: '#57' }, { id: 99, display: '#99' }];"),
}


@pytest.mark.parametrize("case", list(REFUSAL))
def test_a_read_refused_for_any_reason_is_no_read(tmp_path, case):
    """Scanned while something refuses it, then again 0.4 s later once that has gone: the
    second read deposits the spool shown. Two reviewers of the second round: an empty
    buffer's refusal counted as the QR's read, so the QR scanned right after a spool was
    dropped as a second read (RED before the fix); the other four pin the unread() the
    first round added, which nothing caught when it was taken out."""
    first, lift = REFUSAL[case]
    res = _run(tmp_path, SETUP + """
openOn('SHELF-1');
%s
const t0 = Date.now();
window.processScan('CMD:DEPOSIT:SHELF-1', 'barcode', t0);
await __settle(60);
%s
window.processScan('CMD:DEPOSIT:SHELF-1', 'barcode', t0 + 400);
await __settle(80);
return { sent: sent(), toasts: toasts().map((t) => t.msg) };
""" % (first, lift), modules=LM)
    adds = [b for u, b in res["sent"] if u == "/api/manage_contents"]
    assert len(adds) == 1 and str(adds[0]).endswith("57"), res


@pytest.mark.parametrize("opened", [True, False], ids=["the-picker-opened", "the-picker-didnt-open"])
def test_the_picker_is_the_answer_and_one_that_didnt_open_is_no_read(tmp_path, opened):
    """On a box with slots the QR's answer is its picker: once it is up, a second read
    within 1.5 s is the scanner's double read. A picker that didn't open (another window
    up, a bulk move armed: it says why) was no read, so the QR scanned again acts. RED
    before the fix for the second: it was dropped as a second read."""
    res = _run(tmp_path, SETUP + """
window.isSlotPickerOpen = () => %s;
openOn('LR-MDB-1');
const t0 = Date.now();
window.processScan('CMD:DEPOSIT:LR-MDB-1', 'barcode', t0);
await __settle(60);
window.processScan('CMD:DEPOSIT:LR-MDB-1', 'barcode', t0 + 400);
await __settle(80);
return { picks: window.__picks };
""" % ("true" if opened else "false"), modules=LM)
    assert len(res["picks"]) == (1 if opened else 2), res


@pytest.mark.parametrize("modal", ["confirm", "safety"])
def test_cmd_close_waits_behind_a_gating_dialog_and_acts_once_it_has_gone(tmp_path, modal):
    """Two reviewers of the second round: the first round's wait for CMD:CLOSE had no
    test. Behind "Clear entire Buffer?" or "Nuke all?" it closes nothing and says so;
    scanned again once the dialog has gone, it closes the window. A pin (RED on 295ea9e:
    it closed the window behind the dialog)."""
    res = _run(tmp_path, SETUP + """
window.__closed = 0;
window.closeManage = () => { window.__closed += 1; };
openOn('SHELF-1');
state.activeModal = %r;
window.processScan('CMD:CLOSE', 'barcode');
await __settle(40);
const behind = window.__closed;
state.activeModal = null;
window.processScan('CMD:CLOSE', 'barcode');
await __settle(40);
return { behind, after: window.__closed, toasts: toasts().map((t) => t.msg) };
""" % modal, modules=LM)
    assert res["behind"] == 0 and res["after"] == 1, res
    assert any("Answer the question on screen first" in t for t in res["toasts"]), res["toasts"]
