"""Group 58, build spec section 7's question: Done asks before it parks anything. On
the real modules under node's `vm`, with no browser and no container; the panel's
keys and the hit tests on a real DOM are in test_audit_question_dialog_58_js.py, and
the real dashboard, with one real park on dev, in test_audit_done_question_58_e2e.py.

The page is fed what the REAL routes answer (`asked`: the real session and the real
writes over tests/spoolman_extra_fake.SpoolmanHTTPFake), never a copy of an answer:
a stub of an answer's shape is how a page and its server drift apart unseen.

  - The question is window.confirmActivePrint's three-way, because #confirmModal
    draws behind the panel (z 1100 against 20000). Its new options must leave every
    existing door's dialog as it was, byte for byte.
  - It opens on Back to the audit, Enter goes back, and every other scan is held off.
  - Yes parks exactly what it asked about, through /api/audit/park, however few of
    the spools it had room to draw.
  - closeAuditPanel closes an open question: a Yes left up would answer a question
    about an audit that has gone.

RED on f59485a unless a test says it pins what was already right.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import app as app_module  # noqa: E402
import logic  # noqa: E402
import spoolman_api  # noqa: E402
import state  # noqa: E402
import stock_report  # noqa: E402
from test_audit_auto_park_unknown import _refuse  # noqa: E402
from test_audit_page_58_js import LOG_KEYS, _run  # noqa: E402
from test_audit_session_58 import add_spool, env, scan, start  # noqa: E402,F401  (env: the fixture)
from test_core1_return_ejectall_js import pytestmark, run_js  # noqa: E402,F401  (pytestmark: skip without node)
from test_head_load_confirm_js import CORE, PRELUDE, SCAN  # noqa: E402

BACK = "Back to the audit"
ENDED_HERE = {"active": False, "audit_end": {"id": "boot-1", "why": "done", "location": "LR-MDB-1"}}

QUESTION_PRELUDE = r"""
let __park = null;      // what /api/audit/park answers
const __plainExtra = window.__extra;
window.__extra = (url) => (url === '/api/audit/park' ? { body: __park } : __plainExtra(url));
const __events = [];
document.dispatchEvent = (e) => { __events.push(e.type); return true; };
const QID = 'fcc-audit-done-question';
const question = () => __mounts.filter(m => m.opts.id === QID).pop();
const questionUp = () => __rec.overlays.some(o => o.id === QID && !o.closed);
const questionsUp = () => __rec.overlays.filter(o => o.id === QID && !o.closed).length;
const questionHtml = () => __rec.overlays.filter(o => o.id === QID).pop().content;
const parks = () => posts('/api/audit/park');
const ask = async (answer) => {
  answerWith('/api/identify_scan', [answer]);
  await running(SESSION);
  doneBtn().onclick();
  await __settle(60);
};
// A click on the yes, on the clock's far side of the 700 ms it takes no click after
// the question opens (`armAfterMs`). PIN UPDATED DELIBERATELY (Group 58 review).
const parkThem = async () => {
  const plain = Date.now;
  Date.now = () => plain() + 700;
  await click('.fcc-apc-yes');
};
"""


def _q(tmp_path, body, modules=SCAN, **values):
    head = "".join(f"const {name} = {json.dumps(value)};\n" for name, value in values.items())
    return _run(tmp_path, QUESTION_PRELUDE + head + body, modules=modules)


def _text(html):
    import re
    return re.sub(r"<[^>]+>", "", html)


@pytest.fixture
def asked(env, monkeypatch):
    """What the real routes answer around one Done, on the real session. LR-MDB-1:
    #57 found, #100 to #111 not scanned, and three that stay: #200 moved off since,
    #201 deleted, #202 in the scan buffer. Then the Yes, every way it can end."""
    monkeypatch.setattr(state, "UNDO_STACK", [])
    monkeypatch.setattr(stock_report, "_server_day", lambda: "2026-11-02")
    add_spool(env, 57, "LR-MDB-1", container_slot="1")
    for n in range(12):
        add_spool(env, 100 + n, "LR-MDB-1", container_slot=str(n + 2))
    for sid in (200, 201, 202):
        add_spool(env, sid, "LR-MDB-1")
    start(env, "LR-MDB-1")
    scan(env, "ID:57")
    spools = env["fake"].records["spool"]
    spools[200]["location"] = "LR-MDB-2"
    del spools[201]
    state.GLOBAL_BUFFER = [{"id": 202}]
    out = {"question": scan(env, "CMD:DONE")}
    audit_id = out["question"]["audit_id"]
    ids = [row["id"] for row in out["question"]["park"]]

    def yes(ids=ids, audit_id=audit_id):
        body = {"audit_id": audit_id, "ids": ids, "today": "2026-11-02"}
        return app_module.app.test_client().post("/api/audit/park", json=body).get_json()

    out["stale"] = yes(audit_id="an-audit-long-gone")
    out["no_ids"] = yes(ids=[])
    env["fake"].list_reads_fail = True
    out["read_failed"] = yes()
    env["fake"].list_reads_fail = False
    real_patch = spoolman_api.requests.patch
    _refuse(env, monkeypatch, *ids)
    out["nothing_landed"] = yes()
    monkeypatch.setattr(spoolman_api.requests, "patch", real_patch)
    assert logic._AUDIT_END_LOCK.acquire(False)
    out["busy"] = yes()
    logic._AUDIT_END_LOCK.release()
    out["parked"] = yes()
    out["late_yes"] = yes()
    assert out["parked"]["success"] is True and out["parked"]["audit_ended"]["why"] == "done"

    # A second audit, one of whose writes is refused.
    add_spool(env, 300, "CR-CT-1")
    add_spool(env, 301, "CR-CT-1")
    start(env, "CR-CT-1")
    second = scan(env, "CMD:DONE")
    _refuse(env, monkeypatch, 301)
    body = {"audit_id": second["audit_id"], "ids": [300, 301], "today": "2026-11-02"}
    out["partial"] = app_module.app.test_client().post("/api/audit/park", json=body).get_json()
    assert out["partial"]["success"] is False and out["partial"]["parked"] == [300]

    # Undo of that one, whose spool has been found and moved on since.
    spools[300]["location"] = "LR-MDB-2"
    client = app_module.app.test_client()
    undo = client.post("/api/undo", json={}).get_json()
    out["undo_left_alone"] = client.post("/api/undo", json={"confirm": True, "undo_id": undo["undo_id"],
                                                            "confirmed_toolheads": []}).get_json()
    undo = client.post("/api/undo", json={}).get_json()
    out["undo_all"] = client.post("/api/undo", json={"confirm": True, "undo_id": undo["undo_id"],
                                                     "confirmed_toolheads": []}).get_json()
    assert out["undo_left_alone"]["left_alone"] and not out["undo_all"].get("left_alone")
    return out


def _small_question(asked, park=1):
    """The real answer, cut down to a few spools."""
    return dict(asked["question"], park=asked["question"]["park"][:park], stays=[])


# --- window.confirmActivePrint's new options --------------------------------------

# Every shape of call the doors make, and the sha-256 of what it drew on f59485a.
# A deliberate change to these dialogs changes these; a new option must not.
DEFAULTS = {
    "{}": "2ef2dbd65a28",
    "{ activePrint: { printer_name: 'XL', state: 'PRINTING' }, msg: 'Careful <b>now</b>.' }": "6860d5a6c705",
    "{ title: 'Load #57 onto XL-1?', msg: 'Body.', onConfirm() {}, onCancel() {} }": "33850cae1760",
    "{ title: 'Load #57 onto XL-1?', msg: 'Body.', onConfirm() {}, onCancel() {}, onStore() {},"
    " storeLabel: 'Just store it in LR-MDB-1 slot 1' }": "46ef246785ed",
    "{ title: 'T', msg: 'B', printing: true, onConfirm() {}, onCancel() {}, onStore() {} }": "39e7b1bf82ca",
    "{ title: 'T', msg: 'B', noLoad: true, onConfirm() {}, onStore() {},"
    " ids: { overlay: 'q', yes: 'y', no: 'n', store: 's' } }": "f6b9f311f5c5",
    # An empty list of sections is no list: the same bytes as the same call with none.
    "{ title: 'Load #57 onto XL-1?', msg: 'Body.', onConfirm() {}, onCancel() {}, sections: [] }": "33850cae1760",
}


@pytest.mark.parametrize("call", DEFAULTS)
def test_the_options_left_out_draw_what_every_door_drew(tmp_path, call):
    """Pins what was right: the same markup on f59485a and now, byte for byte, an empty
    `sections` included (no stray wrapper, no stray white space)."""
    res = run_js(tmp_path, CORE, PRELUDE + f"""
window.confirmActivePrint({call});
return {{ content: html().pop() }};
""")
    assert hashlib.sha256(res["content"].encode()).hexdigest()[:12] == DEFAULTS[call], res["content"]


def test_the_words_a_door_never_chose_stay_as_they_were(tmp_path):
    """Pins what was right: the QR captions, the hold-off's words and the hint on each
    button, for a door that passes none of the new options."""
    res = run_js(tmp_path, CORE, PRELUDE + r"""
const qrs = [];
const attach = window.attachConfirmQRs;
window.attachConfirmQRs = (o) => { qrs.push({ c: o.confirmLabel, s: o.storeLabel, x: o.cancelLabel }); return attach(o); };
window.confirmActivePrint({ title: 'T', msg: 'B', onConfirm() {}, onStore() {}, onCancel() {} });
const m = lastMount();
const fire = (sel) => { m.ls.filter(([t]) => t === 'focus').forEach(([, fn]) => fn({ target: m.el.querySelector(sel) }));
                        return m.el.querySelector('.fcc-apc-hint').textContent; };
return { qrs, hold: window._fccOpenMoveQuestion.hint, yes: fire('.fcc-apc-yes'), store: fire('.fcc-apc-store'),
         no: fire('.fcc-apc-no') };
""")
    assert res["qrs"] == [{"c": "Scan to Load", "s": "Scan to Store", "x": "Scan to Cancel"}]
    assert res["hold"] == "Answer the question on screen first: Load it instead, Just store it, or Cancel"
    assert (res["yes"], res["store"], res["no"]) == ("Enter loads it · Esc cancels", "Enter stores it · Esc cancels",
                                                     "Enter cancels · Esc cancels")


def test_a_doors_own_words_reach_the_buttons_the_captions_the_hint_and_the_hold_off(tmp_path):
    res = run_js(tmp_path, CORE, PRELUDE + r"""
const qrs = [];
const attach = window.attachConfirmQRs;
window.attachConfirmQRs = (o) => { qrs.push({ c: o.confirmLabel, x: o.cancelLabel, tones: [o.confirmTone, o.cancelTone] }); return attach(o); };
window.confirmActivePrint({ title: 'Park 2 spools?', msg: 'B', printing: true, onConfirm() {}, onCancel() {},
  loadLabel: 'Park them', loadVerb: 'parks them', loadCaption: 'Scan to Park',
  cancelLabel: 'Back to <it>', cancelVerb: 'goes back', cancelCaption: 'Scan to go back' });
const m = lastMount();
const fire = (sel) => { m.ls.filter(([t]) => t === 'focus').forEach(([, fn]) => fn({ target: m.el.querySelector(sel) }));
                        return m.el.querySelector('.fcc-apc-hint').textContent; };
return { html: html().pop(), qrs, hold: window._fccOpenMoveQuestion.hint, focus: m.opts.initialFocus,
         yes: fire('.fcc-apc-yes'), no: fire('.fcc-apc-no') };
""")
    assert "Back to &lt;it&gt;</button>" in res["html"] and "Park them" in res["html"]
    assert "Enter goes back · Esc goes back" in res["html"]
    assert res["qrs"] == [{"c": "Scan to Park", "x": "Scan to go back", "tones": ["warning", "secondary"]}]
    assert res["hold"] == "Answer the question on screen first: Park them or Back to <it>"
    assert (res["yes"], res["no"]) == ("Enter parks them · Esc goes back", "Enter goes back · Esc goes back")
    assert res["focus"] == ".fcc-apc-no"


def test_a_question_that_can_only_store_takes_the_doors_cancel_caption_too(tmp_path):
    """Finding 19(c). No door asks this yet. Pins what was right: proved on a copy that
    drops `cancelCaption` from the no-load path."""
    res = run_js(tmp_path, CORE, PRELUDE + r"""
const qrs = [];
const attach = window.attachConfirmQRs;
window.attachConfirmQRs = (o) => { qrs.push({ c: o.confirmLabel, x: o.cancelLabel }); return attach(o); };
window.confirmActivePrint({ title: 'T', msg: 'B', noLoad: true, onStore() {}, onCancel() {},
  cancelCaption: 'Scan to go back' });
return { qrs };
""")
    assert res["qrs"] == [{"c": "Scan to Store", "x": "Scan to go back"}]


def test_sections_sit_under_the_message_escaped_and_a_count_says_what_was_left_out(tmp_path):
    res = run_js(tmp_path, CORE, PRELUDE + r"""
window.confirmActivePrint({ title: 'T', msg: 'The words.', onConfirm() {}, sections: [
  { heading: 'One <b>list</b>', lines: [{ text: '#1 "A" <i>spool</i>', where: 'slot & 1' }, { text: '#2 no place' }], more: 12 },
  { heading: 'Two', lines: [{ text: '#3', where: 'moved to <X>' }], more: 0 }] });
return { html: html().pop() };
""")
    h = res["html"]
    assert h.index("The words.") < h.index("fcc-apc-sections") < h.index("fcc-apc-btns")
    assert "One &lt;b&gt;list&lt;/b&gt;" in h and "#1 &quot;A&quot; &lt;i&gt;spool&lt;/i&gt;" in h
    assert "slot &amp; 1" in h and "moved to &lt;X&gt;" in h and "<i>" not in h
    assert h.count('class="fcc-apc-line"') == 3 and h.count('class="fcc-apc-line-where"') == 2
    assert "and 12 more" in h and h.count("fcc-apc-more") == 1             # none for a list shown whole
    assert 'title="#1 &quot;A&quot; &lt;i&gt;spool&lt;/i&gt; · slot &amp; 1"' in h     # a line never wraps


def test_two_lists_get_the_wider_window_and_the_widths_are_rem(tmp_path):
    """Side by side, so the question's height is one list's and its QRs stay in view."""
    res = run_js(tmp_path, CORE, PRELUDE + r"""
const one = [{ heading: 'A', lines: [{ text: 'x' }] }];
window.confirmActivePrint({ title: 'T', msg: 'B', onConfirm() {}, sections: one });
const first = html().pop();
window.confirmActivePrint({ title: 'T', msg: 'B', onConfirm() {}, sections: one.concat(one), ids: { overlay: 'two' } });
return { first, second: html().pop() };
""")
    assert "width:min(35rem, calc(100vw - 16px));" in res["first"]
    assert "width:min(50rem, calc(100vw - 16px));" in res["second"]


# --- `armAfterMs`: the second click of a double click (Group 58 review) ----------------

def test_the_yes_takes_no_click_until_it_is_armed(tmp_path):
    """The question can open with its yes under the pointer. RED on 8373ecd: the click
    answered it, and a double click on Done parked a batch nobody had read about."""
    res = run_js(tmp_path, CORE, PRELUDE + r"""
let yes = 0;
let no = 0;
window.confirmActivePrint({ title: 'T', msg: 'B', armAfterMs: 700, onConfirm() { yes += 1; }, onCancel() { no += 1; } });
btn('.fcc-apc-yes').onclick();
const early = yes;
const plain = Date.now;
Date.now = () => plain() + 700;
btn('.fcc-apc-yes').onclick();
btn('.fcc-apc-yes').onclick();
return { early, yes, no, open: !!window._fccOpenMoveQuestion };
""")
    assert res["early"] == 0 and res["yes"] == 1 and res["no"] == 0 and res["open"] is False


def test_a_door_that_doesnt_ask_for_it_takes_a_click_at_once(tmp_path):
    """Every other door, as it was. A pin: proved on a copy that arms every yes."""
    res = run_js(tmp_path, CORE, PRELUDE + r"""
let yes = 0;
window.confirmActivePrint({ title: 'T', msg: 'B', onConfirm() { yes += 1; } });
btn('.fcc-apc-yes').onclick();
window.confirmActivePrint({ activePrint: { printer_name: 'XL', state: 'PRINTING' }, onConfirm() { yes += 1; } });
btn('.fcc-apc-yes').onclick();
return { yes };
""")
    assert res["yes"] == 2


def test_enter_and_the_qrs_are_no_second_click(tmp_path):
    """They don't wait: only a click can land there by accident. A pin: proved on a copy
    that arms the answer, not the click."""
    res = run_js(tmp_path, CORE, PRELUDE + r"""
let yes = 0;
const open = () => window.confirmActivePrint({ title: 'T', msg: 'B', armAfterMs: 700, onConfirm() { yes += 1; } });
open();
document.activeElement = btn('.fcc-apc-yes');
await key('Enter');
const entered = yes;
open();
window.routeConfirmScan('CMD:CONFIRM:' + sidOf());
return { entered, yes };
""")
    assert res["entered"] == 1 and res["yes"] == 2


def test_dones_question_takes_no_click_for_as_long_as_a_double_press(tmp_path, asked):
    """RED on 8373ecd: the park went out."""
    res = _q(tmp_path, """
__park = PARKED;
await ask(QUESTION);
await click('.fcc-apc-yes');
return { parks: parks(), up: questionUp(), active: state.auditActive };
""", QUESTION=asked["question"], PARKED=asked["parked"])
    assert res["parks"] == [] and res["up"] is True and res["active"] is True


# --- the question, from the real answer ---------------------------------------------

def test_done_asks_and_nothing_moves(tmp_path, asked):
    res = _q(tmp_path, """
await ask(QUESTION);
const m = question();
return { html: questionHtml(), tier: m.opts.tier, focus: m.opts.initialFocus, up: questionUp(), parks: parks(),
         active: state.auditActive, panel: panelUp(), toasts: toasts(), scans: scans(), title: window._fccOpenMoveQuestion.title };
""", QUESTION=asked["question"])
    assert res["up"] is True and res["tier"] == "confirm" and res["focus"] == ".fcc-apc-no"
    assert res["parks"] == [] and res["active"] is True and res["panel"] is True and res["scans"] == ["CMD:DONE"]
    text = _text(res["html"])
    assert "Park 12 spools at Unknown?" in text and "Park them" in text and BACK in text
    assert "1 of 16 found at LR-MDB-1." in text and "The 12 not scanned go to Unknown" in text
    assert "Undo Last Move puts them back." in text
    assert "#ff8800" in res["html"]                                        # the printing answer's border
    assert res["toasts"] == []
    assert res["title"] == "Park 12 spools at Unknown?"


def test_at_most_eight_lines_a_list_then_the_count(tmp_path, asked):
    res = _q(tmp_path, """
await ask(QUESTION);
return { html: questionHtml() };
""", QUESTION=asked["question"])
    h = _text(res["html"])
    for sid in range(100, 108):
        assert f"#{sid} Some Brand" in h, sid
    for sid in range(108, 112):
        assert f"#{sid} " not in h, sid
    assert "and 4 more" in h and h.count("Not scanned") == 1


def test_the_second_list_says_why_each_stays(tmp_path, asked):
    """`why`, not `where`: a deleted spool is nowhere."""
    res = _q(tmp_path, """
await ask(QUESTION);
return { html: questionHtml() };
""", QUESTION=asked["question"])
    h = _text(res["html"])
    assert "Left where they are" in h
    assert "#200 Some Brand PLA (Red)" in h and "moved to LR-MDB-2" in h
    assert "no longer in Spoolman" in h and "#202 Some Brand PLA (Red)" in h and "in the scan buffer" in h


def test_with_nothing_staying_there_is_no_second_list(tmp_path, asked):
    res = _q(tmp_path, """
await ask(QUESTION);
return { html: questionHtml() };
""", QUESTION=_small_question(asked, 2))
    assert "Left where they are" not in res["html"] and res["html"].count("fcc-apc-section-head") == 1


def test_a_slot_shows_on_its_line_and_no_slot_shows_none(tmp_path, asked):
    question = _small_question(asked, 2)
    question["park"][1]["slot"] = ""
    res = _q(tmp_path, """
await ask(QUESTION);
return { html: questionHtml() };
""", QUESTION=question)
    assert res["html"].count('class="fcc-apc-line-where"') == 1
    assert ">slot 2</span>" in res["html"]


def test_one_spool_reads_as_one(tmp_path, asked):
    res = _q(tmp_path, """
await ask(QUESTION);
const hold = window._fccOpenMoveQuestion.hint;
return { html: _text(questionHtml()), hold };
function _text(h) { return h.replace(/<[^>]+>/g, ''); }
""", QUESTION=_small_question(asked))
    assert "Park 1 spool at Unknown?" in res["html"] and "The one not scanned goes to Unknown" in res["html"]
    assert "Undo Last Move puts it back." in res["html"] and "Park it" in res["html"]
    assert res["hold"] == f"Answer the question on screen first: Park it or {BACK}"


def test_the_hold_off_names_the_two_buttons(tmp_path, asked):
    res = _q(tmp_path, """
await ask(QUESTION);
return { hold: window._fccOpenMoveQuestion.hint };
""", QUESTION=asked["question"])
    assert res["hold"] == f"Answer the question on screen first: Park them or {BACK}"


def test_every_word_of_a_spool_is_escaped(tmp_path, asked):
    question = _small_question(asked)
    question["park"][0]["display"] = "#100 <img src=x onerror=alert(1)> PLA"
    question["stays"] = [{"id": 5, "display": "#5 <b>x</b>", "where": "", "why": "moved to <i>y</i>"}]
    question["location"] = "A<B"
    res = _q(tmp_path, """
await ask(QUESTION);
return { html: questionHtml(), logs: logLines() };
""", QUESTION=question)
    assert "<img" not in res["html"] and "<b>x" not in res["html"] and "<i>y" not in res["html"]
    assert "A&lt;B" in res["html"]


# --- Back ------------------------------------------------------------------------

def test_back_moves_nothing_and_the_audit_runs_on(tmp_path, asked):
    res = _q(tmp_path, """
await ask(QUESTION);
await click('.fcc-apc-no');
return { up: questionUp(), parks: parks(), active: state.auditActive, panel: panelUp(), scans: scans(), toasts: timed(),
         logs: logLines(), held: window._fccOpenMoveQuestion || null, disabled: doneBtn().disabled };
""", QUESTION=asked["question"])
    assert res["up"] is False and res["parks"] == [] and res["active"] is True and res["panel"] is True
    assert res["scans"] == ["CMD:DONE"] and res["held"] is None and res["disabled"] is False
    assert res["toasts"] == [{"msg": "Back to the audit: nothing moved.", "type": "info", "ms": 4000}]
    assert any("back to the audit of LR-MDB-1" in line for line in res["logs"])


def test_enter_goes_back_wherever_the_focus_is_but_on_the_yes(tmp_path, asked):
    res = _q(tmp_path, """
await ask(QUESTION);
const shown = questionUp();
document.activeElement = null;
await key('Enter');
const away = { up: questionUp(), parks: parks() };
await ask(QUESTION);
const again = questionUp();
document.activeElement = btn('.fcc-apc-no');
await key('Enter');
return { shown, again, away, up: questionUp(), parks: parks() };
""", QUESTION=asked["question"])
    assert res["shown"] is True and res["again"] is True
    assert res["away"] == {"up": False, "parks": []}
    assert res["up"] is False and res["parks"] == []


def test_a_scans_enter_answers_nothing(tmp_path, asked):
    """On Back or on the yes: "Scan to Park" read by a slow scanner must not press the
    button that happens to have the focus."""
    res = _q(tmp_path, """
await ask(QUESTION);
for (const sel of ['.fcc-apc-no', '.fcc-apc-yes']) {
  document.activeElement = btn(sel);
  state.scanBuffer = 'ID:57'; state.scanStartTime = Date.now() - 5000;
  await key('Enter');
}
return { up: questionUp(), parks: parks() };
""", QUESTION=asked["question"])
    assert res["up"] is True and res["parks"] == []


def test_a_question_closed_from_the_panel_says_nothing(tmp_path, asked):
    res = _q(tmp_path, """
await ask(QUESTION);
window.closeAuditPanel();
await __settle(40);
const sid = Object.keys(window._fccActiveConfirms || {});
return { up: questionUp(), toasts: toasts(), logs: logLines(), parks: parks(), sessions: sid, panel: panelUp(),
         active: state.auditActive, held: window._fccOpenMoveQuestion || null };
""", QUESTION=asked["question"])
    assert res["up"] is False and res["toasts"] == [] and res["parks"] == []
    assert res["sessions"] == [] and res["held"] is None       # its QRs and its hold-off went with it
    assert res["panel"] is False and res["active"] is True     # a Hide: the audit runs on
    assert not any("back to the audit" in line for line in res["logs"])


def test_the_audit_ending_under_the_page_closes_the_question(tmp_path, asked):
    """The watchdog, or another device: the Yes must not stay up, and a late QR must
    not answer it."""
    res = _q(tmp_path, """
await ask(QUESTION);
const sid = sidOf();
await heartbeat(Object.assign({}, LOG_KEYS, { audit_active: false,
  audit_end: { id: QUESTION.audit_id, why: 'idle', location: 'LR-MDB-1' } }));
const after = { up: questionUp(), panel: panelUp(), warnings: warnings() };
__rec.fetches.length = 0;
window.processScan('CMD:CONFIRM:' + sid, 'barcode');
await __settle(60);
return { after, parks: parks() };
""", QUESTION=asked["question"], LOG_KEYS=LOG_KEYS)
    assert res["after"]["up"] is False and res["after"]["panel"] is False and res["parks"] == []
    assert len(res["after"]["warnings"]) == 1 and "ended" in res["after"]["warnings"][0]


def test_a_newer_question_replaces_an_older_one_quietly(tmp_path, asked):
    """Two Done answers landing together. One question, and nobody's "Back" toast for
    the one nobody answered."""
    res = _q(tmp_path, """
await ask(QUESTION);
window.askAuditDone(QUESTION);
await __settle(40);
const open = questionsUp();
window.closeAuditPanel();
await __settle(40);
return { open, after: questionsUp(), toasts: toasts(), held: (window._fccOpenMoveQuestions || []).length };
""", QUESTION=asked["question"])
    assert res["open"] == 1 and res["after"] == 0 and res["toasts"] == [] and res["held"] == 0


def test_a_done_scanned_behind_a_hidden_panel_asks_and_back_shows_the_panel(tmp_path, asked):
    """"Back to the audit" has to be true. Scanned from a printed CMD:DONE label (the
    deck's tile read FINISH over one until Derek's 2026-11-03 look)."""
    res = _q(tmp_path, """
answerWith('/api/identify_scan', [QUESTION]);
await running(SESSION);
window.closeAuditPanel();
window.processScan('CMD:DONE', 'barcode');
await __settle(60);
const hidden = { panel: panelUp(), up: questionUp() };
await click('.fcc-apc-no');
return { hidden, panel: panelUp(), up: questionUp() };
""", QUESTION=asked["question"])
    assert res["hidden"] == {"panel": False, "up": True}
    assert res["panel"] is True and res["up"] is False


def test_a_done_right_after_a_reload_shows_the_panel_under_the_question(tmp_path, asked):
    """The flag reads false until the first heartbeat, and the answer proves an audit
    runs, as a scan the audit took does."""
    res = _q(tmp_path, """
answerWith('/api/identify_scan', [QUESTION]);
__session = Object.assign({}, SESSION, { audit_id: QUESTION.audit_id });
window.processScan('CMD:DONE', 'barcode');
await __settle(60);
return { active: state.auditActive, panel: panelUp(), up: questionUp(), id: state.auditId };
""", QUESTION=asked["question"])
    assert res["active"] is True and res["panel"] is True and res["up"] is True
    assert res["id"] == asked["question"]["audit_id"]


def test_a_good_done_clears_an_old_refusal_off_the_panel(tmp_path, asked):
    res = _q(tmp_path, """
await running(SESSION);
window.auditPanelNotice('Already auditing LR-MDB-1. Finish first!');
await ask(QUESTION);
return { notice: noticeText() };
""", QUESTION=asked["question"])
    assert res["notice"] == ""


# --- scans while it is open --------------------------------------------------------

def test_a_second_done_is_refused_while_it_is_open(tmp_path, asked):
    """RED on f59485a: nothing held it, and the second press asked again."""
    res = _q(tmp_path, """
await ask(QUESTION);
window.processScan('CMD:DONE', 'barcode');
window.auditDone();
await __settle(60);
return { scans: scans(), open: questionsUp(), mounts: __mounts.filter(m => m.opts.id === QID).length,
         flash: question().el.querySelector('.fcc-apc-status').textContent, warnings: warnings(), logs: logLines(),
         disabled: doneBtn().disabled };
""", QUESTION=asked["question"])
    assert res["scans"] == ["CMD:DONE"] and res["open"] == 1 and res["mounts"] == 1
    assert res["disabled"] is False                            # nothing is out, so nothing stays locked
    assert res["flash"].startswith(f"Answer the question on screen first: Park them or {BACK}")
    assert "(Ignored: CMD:DONE)" in res["flash"]
    assert res["warnings"] == [f"Answer the question on screen first: Park them or {BACK}"] * 2
    assert any('"Park 12 spools at Unknown?" is still open' in line for line in res["logs"])


@pytest.mark.parametrize("text", ["ID:57", "LOC:LR-MDB-2", "CMD:UNDO", "CMD:AUDIT", "CMD:EJECT", "57"])
def test_every_other_scan_is_held_off(tmp_path, asked, text):
    res = _q(tmp_path, """
await ask(QUESTION);
window.processScan(TEXT, 'barcode');
await __settle(60);
return { scans: scans(), up: questionUp(), active: state.auditActive, eject: !!state.ejectMode };
""", QUESTION=asked["question"], TEXT=text)
    assert res["scans"] == ["CMD:DONE"] and res["up"] is True
    assert res["active"] is True and res["eject"] is False


def test_a_bare_cmd_cancel_closes_only_the_question(tmp_path, asked):
    """The panel's own CANCEL label. Cancelling the audit takes a second scan, with
    the question gone: a label mustn't end an audit from under a question."""
    res = _q(tmp_path, """
await ask(QUESTION);
window.processScan('CMD:CANCEL', 'barcode');
await __settle(60);
return { up: questionUp(), scans: scans(), active: state.auditActive, panel: panelUp(), parks: parks() };
""", QUESTION=asked["question"])
    assert res["up"] is False and res["scans"] == ["CMD:DONE"]
    assert res["active"] is True and res["panel"] is True and res["parks"] == []


def test_the_qrs_answer_it(tmp_path, asked):
    res = _q(tmp_path, """
__park = PARKED;
await ask(QUESTION);
window.processScan('CMD:CANCEL:' + sidOf(), 'barcode');
await __settle(60);
const back = { up: questionUp(), parks: parks(), scans: scans() };
await ask(QUESTION);
window.processScan('CMD:CONFIRM:' + sidOf(), 'barcode');
await __settle(120);
return { back, parks: parks().length, up: questionUp(), active: state.auditActive };
""", QUESTION=asked["question"], PARKED=asked["parked"])
    assert res["back"] == {"up": False, "parks": [], "scans": ["CMD:DONE"]}
    assert res["parks"] == 1 and res["up"] is False and res["active"] is False


def test_the_gate_stops_what_the_resolver_reads_as_cancel(env):
    """Why the page stops a stale one: resolve_scan reads any text holding CMD:CANCEL
    as cancel. PIN UPDATED DELIBERATELY (Group 58 review): sent on, a session's QR
    ended the audit. The server now stops it too, for a page that hasn't heard an
    audit runs (tests/test_audit_session_58.py has the gate)."""
    add_spool(env, 57, "LR-MDB-1")
    start(env, "LR-MDB-1")
    assert logic.resolve_scan("CMD:CANCEL:fcc-cqr-9-x") == {"type": "command", "cmd": "cancel"}
    assert scan(env, "CMD:CANCEL:fcc-cqr-9-x") == {
        "type": "error", "msg": "That cancel QR belongs to a dialog that has closed — ignored"}
    assert state.AUDIT_SESSION["active"] is True


def test_a_go_back_qr_read_twice_leaves_the_audit_running(tmp_path, asked):
    """A scanner's double read. The first closes the question, and the second, with no
    dialog left to claim it, went to the server: the audit and every scan in it gone."""
    res = _q(tmp_path, """
await ask(QUESTION);
const sid = sidOf();
window.processScan('CMD:CANCEL:' + sid, 'barcode');
window.processScan('CMD:CANCEL:' + sid, 'barcode');
await __settle(60);
return { scans: scans(), active: state.auditActive, panel: panelUp(), up: questionUp(), toasts: toasts(), logs: logLines() };
""", QUESTION=asked["question"])
    assert res["scans"] == ["CMD:DONE"] and res["active"] is True and res["panel"] is True and res["up"] is False
    said = "That cancel QR belongs to a dialog that has closed — ignored"
    assert {"msg": said, "type": "info"} in res["toasts"]
    assert any(said in line for line in res["logs"])


def test_a_stale_cancel_qr_leaves_a_bulk_move_armed_too(tmp_path):
    """The same gate: a stale QR cancelled whichever session was running."""
    res = _q(tmp_path, """
state.bulkMoveActive = true;
window.processScan('CMD:CANCEL:fcc-cqr-9-x', 'barcode');
await __settle(60);
return { scans: scans() };
""")
    assert res["scans"] == []


def test_with_no_session_a_stale_cancel_qr_still_goes_through(tmp_path):
    """Pins what was right: "cancelling is always safe" where nothing can be lost."""
    res = _q(tmp_path, """
answerWith('/api/identify_scan', [{ type: 'command', cmd: 'cancel' }]);
window.processScan('CMD:CANCEL:fcc-cqr-9-x', 'barcode');
await __settle(60);
return { scans: scans() };
""")
    assert res["scans"] == ["CMD:CANCEL:fcc-cqr-9-x"]


def test_a_bare_cancel_read_twice_closes_only_the_question(tmp_path, asked):
    """The panel's own QR. Its second read used to reach the server, and a bare
    CMD:CANCEL is the audit's real Cancel."""
    res = _q(tmp_path, """
await ask(QUESTION);
const read = Date.now();
window.processScan('CMD:CANCEL', 'barcode', read);
window.processScan('CMD:CANCEL', 'barcode', read + 40);
await __settle(60);
return { scans: scans(), active: state.auditActive, up: questionUp(), toasts: toasts() };
""", QUESTION=asked["question"])
    assert res["scans"] == ["CMD:DONE"] and res["active"] is True and res["up"] is False
    assert {"msg": "Ignored a second read of CMD:CANCEL", "type": "info"} in res["toasts"]


def test_a_cancel_scanned_after_that_is_meant(tmp_path, asked):
    """Derek's rule: guard only the accidental case. A deliberate second scan cancels."""
    res = _q(tmp_path, """
await ask(QUESTION);
window.processScan('CMD:CANCEL', 'barcode', Date.now());
await __settle(20);
answerWith('/api/identify_scan', [CANCEL]);
window.processScan('CMD:CANCEL', 'barcode', Date.now() + 1600);
await __settle(60);
return { scans: scans(), active: state.auditActive };
""", QUESTION=asked["question"], CANCEL={"type": "command", "cmd": "audit_scan",
                                         "audit_ended": {"id": "boot-1", "why": "cancel"}})
    assert res["scans"] == ["CMD:DONE", "CMD:CANCEL"] and res["active"] is False


def test_a_park_qr_read_twice_parks_once(tmp_path, asked):
    res = _q(tmp_path, """
__park = PARKED;
await ask(QUESTION);
const sid = sidOf();
window.processScan('CMD:CONFIRM:' + sid, 'barcode');
window.processScan('CMD:CONFIRM:' + sid, 'barcode');
await __settle(120);
return { parks: parks().length };
""", QUESTION=asked["question"], PARKED=asked["parked"])
    assert res["parks"] == 1


# --- Yes ---------------------------------------------------------------------------

def test_yes_parks_every_spool_it_counted_not_only_the_lines_it_drew(tmp_path, asked):
    res = _q(tmp_path, """
__park = PARKED;
const timeouts = [];
const plain = window.fetchT;
window.fetchT = (u, o, ms) => { if (u === '/api/audit/park') timeouts.push(ms); return plain(u, o, ms); };
await ask(QUESTION);
await parkThem();
return { parks: parks(), timeouts };
""", QUESTION=asked["question"], PARKED=asked["parked"])
    assert len(res["parks"]) == 1
    sent = res["parks"][0]
    assert sent["ids"] == list(range(100, 112)) and sent["audit_id"] == asked["question"]["audit_id"]
    assert 200 not in sent["ids"]                              # a spool that stays is never named
    assert res["timeouts"] == [120000]


def test_the_day_is_the_pages_own(tmp_path, asked):
    """Dev's container runs on UTC, where a late evening is already tomorrow."""
    res = _q(tmp_path, """
__park = PARKED;
const RealDate = Date;
window.Date = class extends RealDate { constructor(...a) { super(...(a.length ? a : [2026, 10, 2, 23, 30])); } };
await ask(QUESTION);
await parkThem();
return { today: parks()[0].today };
""", QUESTION=asked["question"], PARKED=asked["parked"])
    assert res["today"] == "2026-11-02"


def test_a_park_that_landed_ends_the_audit_and_says_so(tmp_path, asked):
    res = _q(tmp_path, """
__park = PARKED;
await ask(QUESTION);
await parkThem();
return { up: questionUp(), panel: panelUp(), active: state.auditActive, here: state.auditEndedHere, toasts: timed(),
         events: __events, processing: state.processing, out: state.auditRequestsOut, pill: pill().style.display };
""", QUESTION=asked["question"], PARKED=asked["parked"])
    assert res["up"] is False and res["panel"] is False and res["active"] is False and res["pill"] == "none"
    assert res["here"] == asked["parked"]["audit_ended"]["id"]
    assert res["toasts"] == [{"msg": asked["parked"]["msg"], "type": "success", "ms": 4000}]
    assert "Undo Last Move puts them back." in res["toasts"][0]["msg"]
    assert "inventory:locations-changed" in res["events"]
    assert res["processing"] is False and res["out"] == 0


def test_a_park_with_a_failure_stays_up_for_7_seconds_and_the_audit_is_over(tmp_path, asked):
    res = _q(tmp_path, """
__park = PARTIAL;
await ask(QUESTION);
await parkThem();
return { panel: panelUp(), active: state.auditActive, toasts: timed(), events: __events };
""", QUESTION=asked["question"], PARTIAL=asked["partial"])
    assert res["panel"] is False and res["active"] is False
    assert res["toasts"] == [{"msg": asked["partial"]["msg"], "type": "warning", "ms": 7000}]
    assert "inventory:locations-changed" in res["events"]


def test_the_page_is_held_while_the_park_is_out(tmp_path, asked):
    """The dim's `state.processing` queues scans, and Done and Cancel stay down: a
    park of 30 spools takes a while, and the panel stays up over it."""
    res = _q(tmp_path, """
let release;
const held = new Promise((r) => { release = r; });
const plain = window.fetchT;
window.fetchT = (u, o, ms) => (u === '/api/audit/park' ? held.then(() => plain(u, o, ms)) : plain(u, o, ms));
__park = PARKED;
await ask(QUESTION);
await parkThem();
const during = { processing: state.processing, done: doneBtn().disabled, cancel: cancelBtn().disabled,
                 notice: noticeText(), out: state.auditRequestsOut, up: questionUp() };
release();
await __settle(60);
return { during, processing: state.processing, out: state.auditRequestsOut };
""", QUESTION=asked["question"], PARKED=asked["parked"])
    assert res["during"] == {"processing": True, "done": True, "cancel": True, "notice": "Parking 12 spools…",
                             "out": 1, "up": False}
    assert res["processing"] is False and res["out"] == 0


def test_the_panels_poll_seeing_the_park_end_first_warns_nobody(tmp_path, asked):
    """The server has ended the audit and its answer is still on its way. RED without
    auditRequestOut around the Yes: the 2 s poll called it "ended elsewhere"."""
    res = _q(tmp_path, """
let release;
const held = new Promise((r) => { release = r; });
const plain = window.fetchT;
window.fetchT = (u, o, ms) => (u === '/api/audit/park' ? held.then(() => plain(u, o, ms)) : plain(u, o, ms));
__park = PARKED;
await ask(QUESTION);
await parkThem();
__session = ENDED;
window.refreshAuditSession();
await __settle(40);
const during = { warnings: warnings(), active: state.auditActive, panel: panelUp() };
release();
await __settle(60);
await heartbeat(Object.assign({}, LOG_KEYS, { audit_active: false, audit_end: ENDED.audit_end }));
return { during, warnings: warnings(), active: state.auditActive };
""", QUESTION=asked["question"], PARKED=asked["parked"], LOG_KEYS=LOG_KEYS,
             ENDED=dict(ENDED_HERE, audit_end=dict(ENDED_HERE["audit_end"], id=asked["parked"]["audit_ended"]["id"])))
    assert res["during"] == {"warnings": [], "active": True, "panel": True}
    assert res["warnings"] == [] and res["active"] is False


@pytest.mark.parametrize("key, words", [
    ("no_ids", "didn't say which spools"),
    ("read_failed", "Couldn't read LR-MDB-1 from Spoolman"),
    ("busy", "already finishing"),
    ("nothing_landed", "The audit is still open, so you can press Done again."),
])
def test_a_refused_yes_keeps_the_audit_and_says_so_on_the_panel(tmp_path, asked, key, words):
    """The real route's refusals, nothing written. The toast sits under the panel.
    A Yes whose every write failed reads the same (it pins page code that was already
    right): Done is pressable again, as its words say."""
    assert words in asked[key]["msg"] and "audit_ended" not in asked[key]
    res = _q(tmp_path, """
__park = ANSWER;
await ask(QUESTION);
await parkThem();
return { active: state.auditActive, panel: panelUp(), notice: noticeText(), toasts: timed(), done: doneBtn().disabled,
         processing: state.processing, events: __events };
""", QUESTION=asked["question"], ANSWER=asked[key])
    assert res["active"] is True and res["panel"] is True and res["notice"] == asked[key]["msg"]
    assert res["toasts"] == [{"msg": asked[key]["msg"], "type": "error", "ms": 7000}]
    assert res["done"] is False and res["processing"] is False
    assert "inventory:locations-changed" not in res["events"]


@pytest.mark.parametrize("key", ["stale", "late_yes"])
def test_a_yes_for_an_audit_that_has_gone_asks_the_server_why(tmp_path, asked, key):
    """The real route's answer. The heartbeat it asks for corrects the page, with the
    reason. A hidden panel isn't opened for an audit that has gone."""
    assert asked[key].get("stale") is True
    res = _q(tmp_path, """
__park = ANSWER;
__heartbeat = Object.assign({}, LOG_KEYS, { audit_active: false,
  audit_end: { id: QUESTION.audit_id, why: 'idle', location: 'LR-MDB-1' } });
await ask(QUESTION);
window.closeAuditPanel();
window.askAuditDone(QUESTION);
await __settle(20);
const reads = () => __rec.fetches.filter(f => f.url.startsWith('/api/logs') || f.url.startsWith('/api/dashboard_pulse')).length;
const before = reads();
const panelsBefore = panelCount();
await parkThem();
return { asked: reads() - before, panels: panelCount() - panelsBefore, toasts: timed().filter(t => t.msg === ANSWER.msg),
         active: state.auditActive };
""", QUESTION=asked["question"], ANSWER=asked[key], LOG_KEYS=LOG_KEYS)
    assert res["asked"] >= 1 and res["panels"] == 0
    assert res["toasts"] == [{"msg": asked[key]["msg"], "type": "error", "ms": 7000}]
    assert res["active"] is False


def test_a_yes_with_no_answer_says_the_park_may_not_have_finished(tmp_path, asked):
    """It may be running still: past the timeout Spoolman can be slow, not gone."""
    res = _q(tmp_path, """
await ask(QUESTION);
window.fetchT = () => Promise.reject(new Error('The operation timed out'));
await parkThem();
return { active: state.auditActive, panel: panelUp(), notice: noticeText(), toasts: timed(), processing: state.processing,
         out: state.auditRequestsOut, logs: logLines() };
""", QUESTION=asked["question"])
    assert res["active"] is True and res["panel"] is True
    assert "may not have finished" in res["notice"] and res["processing"] is False and res["out"] == 0
    assert res["toasts"][-1]["ms"] == 7000 and "may not have finished" in res["toasts"][-1]["msg"]
    assert any("may not have finished" in line for line in res["logs"])


def test_a_yes_the_server_answered_with_an_error_page_says_the_same(tmp_path, asked):
    res = _q(tmp_path, """
await ask(QUESTION);
window.fetchT = () => Promise.resolve({ json: () => Promise.reject(new SyntaxError('Unexpected token <')) });
await parkThem();
return { notice: noticeText(), processing: state.processing };
""", QUESTION=asked["question"])
    assert "may not have finished" in res["notice"] and res["processing"] is False


def test_an_exception_after_the_park_landed_doesnt_say_it_failed(tmp_path, asked):
    """Only a request that got no answer says so."""
    res = _q(tmp_path, """
__park = PARKED;
await ask(QUESTION);
const plain = window.noteAuditEnded;
window.noteAuditEnded = () => { throw new Error('a bug after the write'); };
const errors = [];
console.error = (e) => errors.push(String(e));
await parkThem();
return { toasts: timed(), errors, processing: state.processing, out: state.auditRequestsOut };
""", QUESTION=asked["question"], PARKED=asked["parked"])
    assert not any("may not have finished" in t["msg"] for t in res["toasts"])
    assert res["errors"] and res["processing"] is False and res["out"] == 0


# --- the panel's way to the Loose spools list ---------------------------------------

def test_the_panel_opens_the_loose_list_on_the_confirm_tier_and_closes_it_with_itself(tmp_path):
    res = _q(tmp_path, """
const opened = [];
const closed = [];
const list = { id: 'fcc-loose-list' };
window.openLooseList = (o) => { opened.push(o); return list; };
window.closeLooseList = (h) => { closed.push(h === list); };
await running(SESSION);
panel().querySelector('#fcc-audit-panel-loose').onclick();
const open = { opened: opened.slice(), closed: closed.slice() };
window.closeAuditPanel();
return { open, closed, shell: shell() };
""")
    assert res["open"] == {"opened": [{"tier": "confirm"}], "closed": []}
    assert res["closed"] == [True] and "🧺 Loose spools" in res["shell"]


# --- Undo --------------------------------------------------------------------------

UNDO_NOT_ANSWERED = "FCC didn't answer, so the Undo may not have finished. Check the Activity Log before pressing it again."


def test_undo_waits_as_long_as_a_big_park_takes_it(tmp_path, asked):
    """A park's Undo reads and writes every spool in it, one strict read per box too, so it
    is the slowest request FCC makes. It used no timeout at all. RED on 1f8e03a: plain
    fetch, so the timeout seen here was none."""
    res = _q(tmp_path, """
const timeouts = [];
const plain = window.fetchT;
window.fetchT = (u, o, ms) => { if (u === '/api/undo') timeouts.push(ms); return plain(u, o, ms); };
answerWith('/api/undo', [ALL]);
triggerUndo({ confirm: true, undoId: 'x', heads: [] });
await __settle(40);
return { timeouts, toasts: timed() };
""", ALL=asked["undo_all"])
    assert res["timeouts"] == [120000]
    assert res["toasts"] == [{"msg": asked["undo_all"]["msg"], "type": "success", "ms": 4000}]


@pytest.mark.parametrize("failing", ["Promise.reject(new Error('The operation timed out'))",
                                     "Promise.resolve({ json: () => Promise.reject(new SyntaxError('Unexpected token <')) })"],
                         ids=["no-answer-in-time", "an-error-page"])
def test_no_answer_to_an_undo_says_it_may_not_have_finished(tmp_path, failing):
    """Past the timeout the server may well still be putting spools back, and "Undo failed"
    invites a second press. The log line is what the toast sends the person to. RED on
    1f8e03a."""
    res = _q(tmp_path, """
window.fetchT = () => %s;
triggerUndo({ confirm: true, undoId: 'x', heads: [] });
await __settle(40);
return { toasts: timed(), logs: logLines() };
""" % failing)
    assert res["toasts"] == [{"msg": UNDO_NOT_ANSWERED, "type": "error", "ms": 7000}]
    assert any(UNDO_NOT_ANSWERED in line for line in res["logs"]), res["logs"]


UNDO_NOT_ASKED = "FCC didn't answer, so nothing was undone. Try again in a moment."


@pytest.mark.parametrize("failing", ["Promise.reject(new Error('The operation timed out'))",
                                     "Promise.resolve({ json: () => Promise.reject(new SyntaxError('Unexpected token <')) })"],
                         ids=["no-answer-in-time", "an-error-page"])
def test_no_answer_to_undos_question_says_nothing_was_undone(tmp_path, failing):
    """Re-review finding 5. The first press only asks the question (its body is {}, and
    the route writes nothing for it), so with no answer nothing had begun: "may not have
    finished" sent the person to an Activity Log holding nothing about it. The Yes keeps
    its words (the test above). RED on 681232a."""
    res = _q(tmp_path, """
const bodies = [];
window.fetchT = (u, o) => { bodies.push(JSON.parse(o.body)); return %s; };
triggerUndo();
await __settle(40);
return { toasts: timed(), logs: logLines(), bodies };
""" % failing)
    assert res["bodies"] == [{}]
    assert res["toasts"] == [{"msg": UNDO_NOT_ASKED, "type": "error", "ms": 7000}]
    assert any(UNDO_NOT_ASKED in line for line in res["logs"]), res["logs"]


def test_an_exception_after_an_undos_answer_doesnt_read_as_no_answer(tmp_path, asked):
    """The answer landed, so the words would be false: the park's rule, which has the same
    test. RED on 1f8e03a, in the old words: "Undo failed: no answer from the server"."""
    res = _q(tmp_path, """
answerWith('/api/undo', [ALL]);
window.fetchLocations = () => { throw new Error('a bug after the answer'); };
const errors = [];
console.error = (e) => errors.push(String(e));
triggerUndo({ confirm: true, undoId: 'x', heads: [] });
await __settle(40);
return { toasts: timed(), errors };
""", ALL=asked["undo_all"])
    assert res["toasts"] == [] and res["errors"]


def test_an_undo_that_left_a_spool_alone_stays_up_long_enough_to_read(tmp_path, asked):
    """Its sentence names where the spool went, and the rest of the batch is back."""
    res = _q(tmp_path, """
answerWith('/api/undo', [LEFT, ALL]);
triggerUndo({ confirm: true, undoId: 'x', heads: [] });
await __settle(40);
triggerUndo({ confirm: true, undoId: 'y', heads: [] });
await __settle(40);
return { toasts: timed() };
""", LEFT=asked["undo_left_alone"], ALL=asked["undo_all"])
    assert res["toasts"] == [{"msg": asked["undo_left_alone"]["msg"], "type": "success", "ms": 7000},
                             {"msg": asked["undo_all"]["msg"], "type": "success", "ms": 4000}]


def test_an_undo_held_back_by_a_place_thats_gone_stays_up_long_enough_to_read(tmp_path, env, monkeypatch):
    """The real route's answer. Those spools count as left alone (`left_alone`), which
    is what gives the page's toast its 7 s: nothing went back, and this says why."""
    monkeypatch.setattr(state, "UNDO_STACK", [])
    add_spool(env, 1, "LR-MDB-1", container_slot="1")
    start(env, "LR-MDB-1")
    question = scan(env, "CMD:DONE")
    client = app_module.app.test_client()
    client.post("/api/audit/park", json={"audit_id": question["audit_id"], "ids": [1], "today": "2026-11-02"})
    env["rows"][:] = [r for r in env["rows"] if r["LocationID"] != "LR-MDB-1"]
    undo = client.post("/api/undo", json={}).get_json()
    answer = client.post("/api/undo", json={"confirm": True, "undo_id": undo["undo_id"],
                                            "confirmed_toolheads": []}).get_json()
    assert answer["success"] is True and answer["place_gone"] == [1]
    res = _q(tmp_path, """
answerWith('/api/undo', [ANSWER]);
triggerUndo({ confirm: true, undoId: 'x', heads: [] });
await __settle(40);
return { toasts: timed() };
""", ANSWER=answer)
    assert res["toasts"] == [{"msg": answer["msg"], "type": "success", "ms": 7000}]
