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
