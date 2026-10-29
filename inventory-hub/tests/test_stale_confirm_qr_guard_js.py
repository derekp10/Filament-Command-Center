"""A confirm QR whose dialog has closed never answers another one (Group 57
review, round 6), hermetic, under node's `vm`: the real inv_core.js,
ui_builder.js and inv_cmd.js (the repo's own harness, test_head_load_confirm_js).

The defect: processScan stops a session's CMD:CONFIRM:<sid> or
CMD:STORE:<sid> that no open dialog claims (its dialog has closed), so it
never falls through to the routes below, which match "CONFIRM" anywhere in a
scan and answer the gating dialog on screen (#confirmModal, #safetyModal).
Round 5 read the guard at the END of the scan (so a key a person left in front
never let one through), and a later scan glued after the stale QR with a Space
in it (a dialog that ate the first scan's Enter, then a location id with a
Space, or a person's Space between them) got past it: the gating dialog took
it as a Yes, silently. Read anywhere now. RED on 5b5a18e for the glued cases.
"""
from __future__ import annotations

import json

import pytest

from test_core1_return_ejectall_js import pytestmark, run_js  # noqa: F401  (pytestmark: skip without node)
from test_head_load_confirm_js import PRELUDE, SCAN

STALE = "CMD:CONFIRM:fcc-cqr-9-x"


def _scan(tmp_path, modal, text):
    body = """
window.__confirmed = 0; window.__safe = 0;
state.activeModal = %s;
state.pendingConfirm = () => { window.__confirmed += 1; };
state.pendingSafety = () => { window.__safe += 1; };
window.isGatingModalOnScreen = () => true;
const tb = toasts().length;
window.processScan(%s, 'barcode');
await __settle(120);
return { confirmed: window.__confirmed, safe: window.__safe, toasts: toasts().slice(tb).map((t) => t.msg) };
""" % (json.dumps(modal), json.dumps(text))
    return run_js(tmp_path, SCAN, PRELUDE + body)


@pytest.mark.parametrize("modal", ["confirm", "safety"])
@pytest.mark.parametrize("text", [
    STALE,                                    # the stale QR alone
    "x" + STALE,                              # a key a person left in front (round 5)
    STALE + "LOC:LR-MDB-1",                   # the next scan glued on
    STALE + " LOC:LR-MDB-1",                  # ... with a Space between (round 6)
    STALE + " LOC:GARAGE SHELF",              # ... a location id with a Space in it
    STALE + " 57",
    "CMD:STORE:fcc-cqr-9-x LOC:LR-MDB-1",     # a stale "Just store it"
])
def test_a_stale_confirm_qr_never_answers_the_dialog_on_screen(tmp_path, modal, text):
    """#confirmModal or #safetyModal on screen, and a stale session QR scanned,
    alone or with a later scan glued to it: the dialog stays unanswered and the
    scan is refused aloud. RED on 5b5a18e with a blank after the QR: the
    dialog's Yes ran, with no toast and no log line."""
    res = _scan(tmp_path, modal, text)
    assert (res["confirmed"], res["safe"]) == (0, 0), (modal, text, res)
    assert any("dialog that has closed" in t for t in res["toasts"]), (modal, text, res)


def test_the_dialogs_own_confirm_still_answers_it(tmp_path):
    """The gating dialog's own QR (a bare CMD:CONFIRM, no session) still
    answers it: the guard stops only a session's QR."""
    res = _scan(tmp_path, "confirm", "CMD:CONFIRM")
    assert res["confirmed"] == 1, res


@pytest.mark.parametrize("glued", [" 57", " LOC:LR-MDB-1:SLOT:2", "57", "ID:57", "LOC:LR-MDB-1:SLOT:2"])
def test_a_live_dialogs_qr_with_a_scan_glued_after_it_says_so(tmp_path, glued):
    """A live dialog's own QR read with a later scan glued after it (its Enter
    eaten, a Space between or none): stopped, as a stale one is, but the toast
    says what happened and the dialog stays live and unanswered. RED on
    4ac78d0: it said the QR belonged to a dialog that had closed, while it was
    on screen; and on b114fd7 with no Space between (round 8: the session id
    was read on into the next scan's letters)."""
    sid = "fcc-cqr-1-live"
    body = """
window.__live = 0;
window._fccActiveConfirms[%s] = { onConfirm: () => { window.__live += 1; }, onStore: null, onCancel: () => {} };
const tb = toasts().length;
window.processScan(%s, 'barcode');
await __settle(120);
return { live: window.__live, still: !!window._fccActiveConfirms[%s], toasts: toasts().slice(tb).map((t) => t.msg) };
""" % (json.dumps(sid), json.dumps("CMD:CONFIRM:" + sid + glued), json.dumps(sid))
    res = run_js(tmp_path, SCAN, PRELUDE + body)
    assert res["live"] == 0 and res["still"], res
    assert any("read together with another scan" in t for t in res["toasts"]), res
    assert not any("dialog that has closed" in t for t in res["toasts"]), res


@pytest.mark.parametrize("text, answer", [
    ("CMD:CONFIRM:FCC-CQR-1-LIVE", "confirm"),     # a scanner set to send upper case
    ("cmd:confirm:FCC-CQR-1-LIVE", "confirm"),     # Caps Lock on: a keyboard wedge swaps every letter
    ("CMD:STORE:FCC-CQR-1-LIVE", "store"),
    ("cmd:cancel:FCC-CQR-1-LIVE", "cancel"),
])
def test_a_live_dialogs_qr_read_in_another_case_answers_it(tmp_path, text, answer):
    """A live dialog's own QR read with its letters' case changed: it answers
    its dialog, as when it is read as printed (a session id is always in lower
    case). RED on 66f2c44: nothing was answered (the id was looked up in the
    case it was read in), and the toast said the QR had been read together
    with another scan, though it was read alone; an upper-case Cancel went on
    to the server."""
    sid = "fcc-cqr-1-live"
    body = """
window.__got = [];
window._fccActiveConfirms[%s] = { onConfirm: () => window.__got.push('confirm'),
    onStore: () => window.__got.push('store'), onCancel: () => window.__got.push('cancel') };
const tb = toasts().length;
window.processScan(%s, 'barcode');
await __settle(120);
return { got: window.__got, scans: posts('/api/identify_scan').map((p) => p.text), toasts: toasts().slice(tb).map((t) => t.msg) };
""" % (json.dumps(sid), json.dumps(text))
    res = run_js(tmp_path, SCAN, PRELUDE + body)
    assert res["got"] == [answer] and res["scans"] == [], res
    assert not any("read together with another scan" in t for t in res["toasts"]), res
