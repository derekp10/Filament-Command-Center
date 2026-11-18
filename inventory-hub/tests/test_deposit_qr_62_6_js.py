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
