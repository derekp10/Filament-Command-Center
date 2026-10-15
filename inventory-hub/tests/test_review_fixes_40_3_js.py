"""Group 40.3 review (wf_ca12a7f0-f09) — the browser fixes, pinned under node's
`vm` with the stub DOM of test_head_load_confirm_js.py.

- B2 (orange): the Quick-Swap deposit takes one tap at a time: a second tap
  while the first is probing / posting is refused with a toast, never a second
  deposit and a second dialog.
- B2 / B3: a dialog mounted on the same overlay id over an unanswered one
  supersedes it: no "Cancelled — nothing moved" toast for a question the user
  never answered (an INFO log line instead), and its scan hold-off goes with
  it. A hold-off whose dialog has left the page lets scans through.
- C1 / B5 (orange): a deposit whose probe saw the print sends `seen_printing`,
  so FCC still asks when its own printer check fails.
- C3: the spool being deposited is not the head's resident, so a head whose
  only spool is that one keeps the deposit's own confirm.
- C4: the dialog draws a question as printing when the server says so
  (`printing`), not only when active_prints lists a head.
- B4: a store that took the spool off the head the slot feeds says "taken off
  XL-1", never "XL-1 left as it was".
HEAD proof (run on c1c2c38: all 8 fail): the double tap posts twice; the
replaced dialog keeps its hold-off and logs nothing; the stale hold-off refuses
the next scan; the deposit sends no `seen_printing`; the deposited spool counts
as the head's resident, so it posts with no confirm; the dialog ignores
`printing`; the store toast says "XL-1 left as it was" after taking #57 off
XL-1; and window.storeToastTail, which the last test (otherwise a control for
the unchanged "left as it was" wording) calls, doesn't exist there.
"""
from __future__ import annotations

from test_core1_return_ejectall_js import pytestmark  # noqa: F401  (skip without node)
from test_head_load_confirm_js import CORE, FED, QS, SCAN, SLOT_DONE, _js, _run, _slot

PRINTING_STATE = r"""
const __respondIdle = window.__respond;
window.__respond = (url) => url.startsWith('/api/printer_state/')
  ? { body: { known: true, is_active: true, state: 'PRINTING', printer_name: 'XL' } } : __respondIdle(url);
"""

TAKEN_OFF = {
    "status": "requires_confirm", "confirm_type": "active_print", "can_store": True, "can_load": True,
    "fed_heads": [], "target_slot": "1", "spools": [57], "feed": "XL-1", "target": "LR-MDB-1",
    "slot_picked": False, "printing": True,
    "active_print": {"toolhead": "XL-1", "printer_name": "XL", "state": "PRINTING"},
    "active_prints": [{"toolhead": "XL-1", "printer_name": "XL", "state": "PRINTING", "role": "source",
                       "spools": [57]}],
    "title": "Load #57 onto XL-1?",
    "body": "#57 is loaded on XL-1. Moving it to LR-MDB-1 means FCC stops charging this print to it.",
    "msg": "#57 is loaded on XL-1. Moving it to LR-MDB-1 means FCC stops charging this print to it. Continue?",
}

DEPOSIT_BTN = "{ dataset: { box: 'LR-MDB-1', slot: '1', toolhead: 'XL-1' } }"


def test_a_second_tap_during_a_deposit_is_one_deposit(tmp_path):
    """XL-1 runs #99, so the deposit posts and the server asks. The tile was
    tapped twice before anything showed: one POST, one dialog, and a toast."""
    res = _run(tmp_path, QS, f"""
window.__extra = (url) => url.startsWith('/api/get_contents?id=XL-1&strict=1')
  ? {{ body: [{{ id: 99, location: 'XL-1', is_ghost: false }}] }} : null;
answerWith('/api/identify_scan', [{_js(_slot(FED))}, {_js(_slot(FED))}]);
window.quickSwapDeposit({DEPOSIT_BTN});
window.quickSwapDeposit({DEPOSIT_BTN});
await __settle(250);
return {{ posts: posts('/api/identify_scan'), shown: html().length, toasts: toasts() }};
""")
    assert len(res["posts"]) == 1 and res["shown"] == 1, res
    assert any("Still working on the last deposit" in t["msg"] for t in res["toasts"]), res["toasts"]


def test_a_second_dialog_on_the_same_overlay_supersedes_the_first_quietly(tmp_path):
    res = _run(tmp_path, CORE, f"""
const sent = [];
window.askMoveConfirm({_js(_slot(FED))}, {{ door: 'slot_scan', original: {{ text: 'LOC:LR-MDB-1:SLOT:1' }},
                                           send: (b) => sent.push(b) }});
const held = !!window._fccOpenMoveQuestion;
window.confirmActivePrint({{ activePrints: [{{ toolhead: 'XL-2', printer_name: 'XL', state: 'PRINTING' }}],
                            msg: 'XL is PRINTING. Continue?', onConfirm() {{}} }});
await __settle(80);
return {{ held, after: !!window._fccOpenMoveQuestion, sent, toasts: toasts(), logs: posts('/api/log_event') }};
""")
    assert res["held"] is True and res["after"] is False, res
    assert res["sent"] == [] and not any("Cancelled" in t["msg"] for t in res["toasts"]), res["toasts"]
    assert any("was replaced by another question" in (lg.get("msg") or "") for lg in res["logs"]), res["logs"]


def test_a_hold_off_whose_dialog_left_the_page_lets_scans_through(tmp_path):
    res = _run(tmp_path, SCAN, f"""
answerWith('/api/identify_scan', [{_js(_slot(FED))}, {_js(SLOT_DONE)}]);
window.processScan('LOC:LR-MDB-1:SLOT:1', 'barcode');
await __settle(150);
window._fccOpenMoveQuestion.element.isConnected = false;   // removed without an answer
window.processScan('LOC:LR-MDB-1:SLOT:2', 'barcode');
await __settle(150);
return {{ posts: posts('/api/identify_scan'), toasts: toasts() }};
""")
    assert len(res["posts"]) == 2, res
    assert not any("Answer the question on screen first" in t["msg"] for t in res["toasts"]), res["toasts"]


def test_a_deposit_that_saw_the_print_tells_the_server(tmp_path):
    res = _run(tmp_path, QS, PRINTING_STATE + f"""
answerWith('/api/identify_scan', [{_js(SLOT_DONE)}]);
window.quickSwapDeposit({DEPOSIT_BTN});
await __settle(250);
return {{ posts: posts('/api/identify_scan') }};
""")
    assert res["posts"] and res["posts"][0].get("seen_printing") == ["XL-1"], res["posts"]


def test_the_deposited_spool_is_not_the_heads_resident(tmp_path):
    """#57 is on XL-1 and in the buffer: FCC asks nothing for it, so the
    deposit keeps its own confirm instead of posting unasked."""
    res = _run(tmp_path, QS, f"""
window.__extra = (url) => url.startsWith('/api/get_contents?id=XL-1&strict=1')
  ? {{ body: [{{ id: 57, location: 'XL-1', is_ghost: false }}] }} : null;
answerWith('/api/identify_scan', [{_js(SLOT_DONE)}]);
window.quickSwapDeposit({DEPOSIT_BTN});
await __settle(250);
return {{ shown: html().slice(), posts: posts('/api/identify_scan') }};
""")
    assert res["posts"] == [] and len(res["shown"]) == 1, res
    assert "fcc-quickswap-confirm-title" in res["shown"][0]


def test_the_dialog_is_drawn_printing_when_the_server_says_so(tmp_path):
    res = _run(tmp_path, CORE, f"""
window.confirmHeadLoad({{ answer: {_js(dict(FED, printing=True))}, onLoad() {{}}, onStore() {{}} }});
const printing = html().pop();
window.confirmHeadLoad({{ answer: {_js(dict(FED, printing=False))}, onLoad() {{}}, onStore() {{}} }});
return {{ printing, idle: html().pop() }};
""")
    assert "⚠️ Load #57 onto XL-1?" in res["printing"] and "#ff8800" in res["printing"], res["printing"]
    assert "🔁 Load #57 onto XL-1?" in res["idle"] and "#0dcaf0" in res["idle"]


def test_a_store_that_took_the_spool_off_its_head_says_so(tmp_path):
    """#57 runs on XL-1 and is scanned into the slot that feeds XL-1 while the
    XL prints: Enter stores, which takes it OFF XL-1."""
    res = _run(tmp_path, SCAN, f"""
answerWith('/api/identify_scan', [{_js(_slot(TAKEN_OFF))}, {_js(SLOT_DONE)}]);
window.processScan('LOC:LR-MDB-1:SLOT:1', 'barcode');
await __settle(150);
await click('.fcc-apc-store');
return {{ toasts: toasts() }};
""")
    assert any(t["msg"] == "📦 #57 stored in LR-MDB-1 slot 1 — taken off XL-1" for t in res["toasts"]), res["toasts"]


STORE_ONLY = {
    "status": "requires_confirm", "confirm_type": "feed_changed", "feed_changed": {"was": "XL-1", "now": ""},
    "fed_heads": [], "active_prints": [], "active_print": None, "can_store": True, "can_load": False,
    "target": "LR-MDB-1", "target_slot": "1", "slot_picked": False, "feed": "", "spools": [57],
    "title": "Store #57 in LR-MDB-1 slot 1?", "printing": False,
    "body": "LR-MDB-1 slot 1 is now a Printer Pool slot (it fed XL-1 when you were asked).",
    "msg": "LR-MDB-1 slot 1 is now a Printer Pool slot (it fed XL-1 when you were asked). Store #57 in LR-MDB-1 slot 1?",
}


def test_a_store_only_question_offers_store_and_cancel_and_replays_the_new_feed(tmp_path):
    """The engine's store-only re-ask (can_load false; Group 40.3 review, D7: no
    browser pin rendered one): no Load button, Enter stores, and the replay
    names the feed the question showed ("")."""
    res = _run(tmp_path, SCAN, f"""
answerWith('/api/identify_scan', [{_js(_slot(STORE_ONLY))}, {_js(SLOT_DONE)}]);
window.processScan('LOC:LR-MDB-1:SLOT:1', 'barcode');
await __settle(150);
const shown = html().pop();
document.activeElement = null;
await key('Enter');
return {{ shown, posts: posts('/api/identify_scan') }};
""")
    h = res["shown"]
    assert "Store #57 in LR-MDB-1 slot 1?" in h and "Just store it in LR-MDB-1 slot 1" in h, h
    assert "Load it instead" not in h and "Enter stores it" in h
    store = res["posts"][1]
    assert store["auto_deploy"] is False and store["expected_feed"] == "" and store["spool_id"] == 57, store


def test_a_store_onto_the_head_it_left_alone_still_says_so(tmp_path):
    """A control: the fed question's store leaves XL-1 (which runs #99) alone."""
    res = _run(tmp_path, CORE, f"""
const r = window.buildMoveReplay('slot_scan', {{ text: 'LOC:LR-MDB-1:SLOT:1' }}, {_js(FED)}, 'store', {{}});
return {{ tail: window.storeToastTail(r.prior), sources: r.prior.sources }};
""")
    assert res["tail"] == " — XL-1 left as it was" and res["sources"] == [], res
