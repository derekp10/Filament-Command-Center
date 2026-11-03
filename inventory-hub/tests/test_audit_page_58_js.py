"""Group 58, build spec section 7 up to the question: the page's half of an audit,
on the real modules under node's `vm` (test_head_load_confirm_js's harness), so it
runs with no browser and no container.

Wherever it matters the page is fed what the REAL route answers on the real session
(`real`: the Flask client on tests/spoolman_extra_fake.SpoolmanHTTPFake), never a
copy of those answers: a stub of an answer's shape is how a page and its server
drift apart unseen.

The audit's panel used to be reached only by a flip of a local flag, so:
  - a printed CMD:AUDIT label, or the deck tile, cancelled the audit it was meant
    to show;
  - after Hide nothing but a reload brought the panel back;
  - a refused start left the page believing an audit ran, and its next press sent
    CMD:CANCEL at the armed bulk move;
  - Cancel was a toggle, so a press with the flag already false sent CMD:AUDIT;
  - an audit that ended under the page (the 30-minute watchdog, another device, a
    restart) said nothing, and the scans it was taking went live;
  - every refusal's toast sat under the panel;
  - the commands the page runs itself skipped the audit altogether.

RED on 25738af unless a test says it pins what was already right.
tests/test_audit_page_58_e2e.py has the real dashboard.
"""
from __future__ import annotations

import json
import os
import re
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import app as app_module  # noqa: E402
import state  # noqa: E402
from test_audit_session_58 import add_spool, env, scan, scan_answer, session, start  # noqa: E402,F401  (env: the fixture)
from test_core1_return_ejectall_js import pytestmark, run_js  # noqa: E402,F401  (pytestmark: skip without node)
from test_head_load_confirm_js import PRELUDE, SCAN  # noqa: E402
from test_text_size_guard import SAMPLE_AUDIT, SAMPLE_AUDIT_EMPTY  # noqa: E402

# The panel, the pill and the heartbeat, on the stub DOM. `__session` is what
# /api/audit_session answers, `__heartbeat` what /api/logs answers. A heartbeat in a
# test is the real render path: window._renderLogsPayload.
AUDIT_PRELUDE = r"""
let __session = { active: false, audit_end: null };
let __heartbeat = null;
// The stub DOM's querySelector hands each element its own fake child: the panel's
// buttons are the body's, as they are on a real page.
const __mountPlain = window.mountOverlay;
window.mountOverlay = (opts) => {
  const h = __mountPlain(opts);
  if (opts.id === 'fcc-audit-panel-overlay') {
    const own = h.element.querySelector.bind(h.element);
    h.element.querySelector = (sel) => (/-(done|cancel)$/.test(sel)
      ? own('#fcc-audit-panel-body').querySelector(sel) : own(sel));
  }
  return h;
};
document.getElementById('fcc-log-pill').style.setProperty = function (k, v) { this[k] = v; };
window.__extra = (url) => {
  if (url.startsWith('/api/audit_session')) return { body: __session };
  if (url.startsWith('/api/logs')) return { body: __heartbeat || [] };
  return null;
};
window.openLocationsModal = () => { __rec.opened = (__rec.opened || []).concat('locations'); };
window.openWeighOutModal = () => { __rec.opened = (__rec.opened || []).concat('weigh'); };
window.printLabel = (id) => { __rec.opened = (__rec.opened || []).concat('print:' + id); };
window.triggerEjectAll = (loc) => { __rec.opened = (__rec.opened || []).concat('ejectall:' + loc); };
const __realEjectSpool = window.ejectSpool;       // inv_loc_mgr.js's, where the test loads it
window.ejectSpool = (id) => { __rec.opened = (__rec.opened || []).concat('eject:' + id); };
const panelUp = () => __rec.overlays.some(o => o.id === 'fcc-audit-panel-overlay' && !o.closed);
const panelCount = () => __rec.overlays.filter(o => o.id === 'fcc-audit-panel-overlay').length;
const panel = () => __mounts.filter(m => m.opts.id === 'fcc-audit-panel-overlay').pop().el;
const bodyHtml = () => panel().querySelector('#fcc-audit-panel-body').innerHTML;
// The tally, above the scrolling body since Derek's 2026-11-03 look (sample 2a).
const tallyHtml = () => panel().querySelector('#fcc-audit-panel-tally').innerHTML;
const shell = () => __rec.overlays.filter(o => o.id === 'fcc-audit-panel-overlay').pop().content;
const noticeText = () => panel().querySelector('#fcc-audit-panel-notice').textContent;
const noteText = () => panel().querySelector('#fcc-audit-panel-note').textContent;
const doneBtn = () => panel().querySelector('#fcc-audit-panel-done');
const cancelBtn = () => panel().querySelector('#fcc-audit-panel-cancel');
const pill = () => document.getElementById('fcc-audit-pill');
const pillText = () => pill().querySelector('#fcc-audit-pill-text').innerText;
const sessionReads = () => __rec.fetches.filter(f => f.url === '/api/audit_session').length;
const scans = () => posts('/api/identify_scan').map(p => p.text);
const warnings = () => toasts().filter(t => t.type === 'warning').map(t => t.msg);
const logLines = () => posts('/api/log_event').map(p => p.msg);
// An audit this page knows about, its panel up on `session`.
const running = async (session) => {
  __session = session;
  state.auditActive = true;
  state.lastAuditState = true;
  window.updateAuditVisuals();
  await __settle(40);
};
const heartbeat = async (src, opts) => { window._renderLogsPayload(src, false, opts); await __settle(40); };
// The toast's own timer says how long it stays up (the real showToast's `dismiss`).
const __plainTimeout = window.setTimeout;
window.setTimeout = (fn, ms, ...rest) => {
  if (fn && fn.name === 'dismiss') { const c = document.getElementById('toast-container').children; c[c.length - 1].ms = ms; }
  return __plainTimeout(fn, ms, ...rest);
};
const timed = () => (document.getElementById('toast-container').children || [])
  .map(c => ({ msg: c.innerText, type: String(c.className).replace('toast-msg toast-', ''), ms: c.ms }));
"""


def _run(tmp_path, body, session=None, modules=SCAN):
    head = "const SESSION = %s;\n" % json.dumps(session or SESSION)
    res = run_js(tmp_path, modules, PRELUDE + AUDIT_PRELUDE + head + body)
    assert res["unhandled"] == [], res["unhandled"]
    return res


def _row(sid, slot, found=False, **more):
    return {"id": sid, "display": f"#{sid} Some Brand PLA (Red)", "color": "72071C", "color_direction": "longitudinal",
            "remaining_weight": 500.0, "slot": slot, "location": "LR-MDB-1", "where": f"LR-MDB-1 slot {slot}",
            "label_status": None, "label_read": False, "flagged_here": False, "found": found, **more}


# /api/audit_session's shape, kept honest by test_the_session_above_is_the_routes_shape.
SESSION = {
    "active": True, "audit_id": "boot-1", "location_id": "LR-MDB-1", "idle_timeout_min": 30,
    "note": "1 is filed here. 2 more are in the places inside it, and this audit doesn't check those: audit each of them.",
    "stats": {"total_expected": 2, "found": 1, "missing": 1, "rogue": 1, "trail": 1},
    "expected": [_row(57, "1", found=True), _row(99, "2")],
    # `at_done` (Derek's C6): what Done will do with this Extra, from its scan's read.
    "rogue": [dict(_row(200, "3", found=True, rogue=True), location="LR-MDB-2", where="LR-MDB-2 slot 3",
                   at_done={"files": True})],
    "trail": [dict(_row(242, "4", found=True, trail=True), location="XL-1", where="XL-1")],
    "last_found": None,
}
ENDED = {"active": False, "audit_end": None}
LOG_KEYS = {"logs": [], "status": {"spoolman": True}}


@pytest.fixture
def real(env):
    """What the real route answers through one audit, on the real session."""
    add_spool(env, 57, "LR-MDB-1", container_slot="1")
    add_spool(env, 99, "LR-MDB-1", container_slot="2")
    add_spool(env, 200, "LR-MDB-2", container_slot="3")
    add_spool(env, 242, "XL-1", physical_source="LR-MDB-1", physical_source_slot="4")
    add_spool(env, 300, "LR", container_slot="")
    client = app_module.app.test_client()
    answers = {"start": scan(env, "CMD:AUDIT"), "heartbeat_no_place": client.get("/api/logs").get_json(),
               "again": scan(env, "CMD:AUDIT"), "no_place": scan(env, "ID:57"),
               "place": scan(env, "LOC:LR-MDB-1"), "second_place": scan(env, "LOC:LR-MDB-2"),
               "slot_label": scan(env, "LOC:LR-MDB-1:SLOT:1"), "filament": scan(env, "FIL:1057"),
               "found": scan(env, "ID:57"), "extra": scan(env, "ID:200"), "loaded": scan(env, "ID:242"),
               "not_there": scan(env, "ID:999999")}
    answers["session"] = client.get("/api/audit_session").get_json()
    answers["question"] = scan(env, "CMD:DONE")
    answers["heartbeat_active"] = client.get("/api/logs").get_json()
    answers["cancel"] = scan(env, "CMD:CANCEL")
    answers["heartbeat_ended"] = client.get("/api/logs").get_json()
    # Done on a place with nothing missing: it ends with no question.
    scan(env, "CMD:AUDIT")
    scan(env, "LOC:LR")
    scan(env, "ID:300")
    answers["done"] = scan(env, "CMD:DONE")
    answers["heartbeat_done"] = client.get("/api/logs").get_json()
    # A refused start: a bulk move is armed.
    state.BULK_MOVE_SESSION["active"] = True
    try:
        answers["refused_start"] = scan(env, "CMD:AUDIT")
    finally:
        state.BULK_MOVE_SESSION["active"] = False
    return answers


def test_the_session_above_is_the_routes_shape(real):
    """The sample the panel tests draw is what the route answers. Pins already-right
    code; it is here so the sample can't drift."""
    got, want = real["session"], SESSION
    assert set(got) == set(want), got
    assert set(got["stats"]) == set(want["stats"])
    for key in ("expected", "rogue", "trail"):
        assert got[key], key
        assert set(want[key][0]) - {"lost_from"} <= set(got[key][0]) | {"rogue", "trail"}, key
    assert got["stats"] == {"total_expected": 2, "found": 1, "missing": 1, "rogue": 1, "trail": 1}
    assert got["rogue"][0]["where"] == "LR-MDB-2 slot 3" and got["trail"][0]["where"] == "XL-1"
    assert got["rogue"][0]["at_done"] == want["rogue"][0]["at_done"]


def test_the_guards_samples_are_the_routes_shape(real, env):
    """The contrast and text-size guards draw these on the real dashboard, so a key a
    tile reads can't be one the route doesn't send. Pins already-right code."""
    got = real["session"]
    assert set(SAMPLE_AUDIT) == set(got) and set(SAMPLE_AUDIT["stats"]) == set(got["stats"])
    for key in ("expected", "rogue", "trail"):
        for row in SAMPLE_AUDIT[key]:
            assert set(row) - {"rogue", "trail"} <= set(got[key][0]), (key, row)
    assert set(SAMPLE_AUDIT["last_found"]) <= set(got["expected"][0])
    scan(env, "CMD:AUDIT")
    before_a_place = app_module.app.test_client().get("/api/audit_session").get_json()
    assert dict(before_a_place, audit_id="boot-1") == SAMPLE_AUDIT_EMPTY


# --- the tile and a CMD:AUDIT scan ------------------------------------------------

def test_a_cmd_audit_scan_during_an_audit_shows_the_panel_and_cancels_nothing(tmp_path):
    """RED on 25738af: the flag flipped and CMD:CANCEL went out, ending the audit."""
    res = _run(tmp_path, """
__session = SESSION;
state.auditActive = true; state.lastAuditState = true;
window.processScan('CMD:AUDIT', 'barcode');
await __settle(60);
return { scans: scans(), up: panelUp(), active: state.auditActive };
""")
    assert res == {"scans": [], "up": True, "active": True, "unhandled": []}


def test_hide_then_the_tile_brings_the_panel_back_and_sends_nothing(tmp_path):
    """RED on 25738af: the tile sent CMD:CANCEL. Decision 5, for Derek's veto."""
    res = _run(tmp_path, """
await running(SESSION);
const before = panelUp();
panel().querySelector('#fcc-audit-panel-close').onclick();
const hidden = panelUp();
toggleAudit();
await __settle(60);
return { before, hidden, after: panelUp(), active: state.auditActive, scans: scans() };
""")
    assert res["before"] is True and res["hidden"] is False
    assert res["after"] is True and res["active"] is True
    assert res["scans"] == []


def test_the_tile_starts_an_audit_and_the_panel_shows_from_the_answer(tmp_path, real):
    """RED on 25738af: the panel waited for the next heartbeat, up to 30 s."""
    res = _run(tmp_path, """
answerWith('/api/identify_scan', [%s]);
__session = SESSION;
toggleAudit();
await __settle(60);
return { scans: scans(), up: panelUp(), active: state.auditActive, shown: pill().style.display };
""" % json.dumps(real["start"]))
    assert res["scans"] == ["CMD:AUDIT"]
    assert res["up"] is True and res["active"] is True and res["shown"] == "inline-flex"


def test_a_printed_audit_label_read_twice_starts_one_audit(tmp_path, real):
    """A scanner's double read while the first is on its way. RED on 25738af: the
    second read flipped the flag and sent CMD:CANCEL."""
    res = _run(tmp_path, """
answerWith('/api/identify_scan', [%s]);
__session = SESSION;
window.processScan('CMD:AUDIT', 'barcode');
window.processScan('CMD:AUDIT', 'barcode');
await __settle(60);
return { scans: scans(), active: state.auditActive };
""" % json.dumps(real["start"]))
    assert res["scans"] == ["CMD:AUDIT"] and res["active"] is True


def test_a_refused_start_leaves_the_page_truthful(tmp_path, real):
    """The real route's refusal with a bulk move armed. RED on 25738af: the answer
    was never read, the flag stayed true, and the next press sent CMD:CANCEL, which
    with no audit running cancels the armed bulk move."""
    assert real["refused_start"]["type"] == "error"
    res = _run(tmp_path, """
answerWith('/api/identify_scan', [%s]);
toggleAudit();
await __settle(60);
const first = { active: state.auditActive, up: panelUp(), toasts: timed(), pill: pill().style.display };
toggleAudit();
await __settle(60);
return { first, scans: scans() };
""" % json.dumps(real["refused_start"]))
    first = res["first"]
    assert first["active"] is False and first["up"] is False and first["pill"] == "none"
    assert {"msg": real["refused_start"]["msg"], "type": "error", "ms": 7000} in first["toasts"]
    assert res["scans"] == ["CMD:AUDIT", "CMD:AUDIT"]


def test_a_start_that_gets_no_answer_puts_the_page_back(tmp_path):
    """RED on 25738af: as the refusal above, with no error handling at all."""
    res = _run(tmp_path, """
window.fetchT = () => Promise.reject(new Error('no route to FCC'));
toggleAudit();
await __settle(60);
return { active: state.auditActive, up: panelUp(), toasts: toasts(), out: state.auditRequestsOut };
""")
    assert res["active"] is False and res["up"] is False and res["out"] == 0
    assert any("Couldn't start the audit" in t["msg"] for t in res["toasts"])


def test_a_press_with_a_running_audit_the_page_hasnt_heard_of_shows_it(tmp_path, real):
    """Right after a reload the flag reads false. The real route's "already in
    progress" answer is no refusal: the panel shows the audit."""
    assert real["again"] == real["start"]
    res = _run(tmp_path, """
answerWith('/api/identify_scan', [%s]);
__session = SESSION;
toggleAudit();
await __settle(60);
return { active: state.auditActive, up: panelUp(), location: state.auditLocation, pill: pillText() };
""" % json.dumps(real["again"]))
    assert res["active"] is True and res["up"] is True
    assert res["location"] == "LR-MDB-1" and res["pill"] == "audit: LR-MDB-1"


# --- Cancel and Done --------------------------------------------------------------

def test_cancel_never_sends_cmd_audit(tmp_path, real):
    """The flag is already false with the panel still up (a Done just landed, or a
    double press). RED on 25738af: the toggle flipped it and sent CMD:AUDIT, a new
    audit if the last one had just ended."""
    res = _run(tmp_path, """
answerWith('/api/identify_scan', [%s]);
await running(SESSION);
state.auditActive = false;
cancelBtn().onclick();
await __settle(60);
return { scans: scans() };
""" % json.dumps(real["cancel"]))
    assert res["scans"] == ["CMD:CANCEL"]


def test_cancel_ends_the_audit_from_its_answer(tmp_path, real):
    res = _run(tmp_path, """
answerWith('/api/identify_scan', [%s]);
await running(SESSION);
cancelBtn().onclick();
await __settle(60);
return { up: panelUp(), active: state.auditActive, here: state.auditEndedHere, toasts: toasts(),
         pill: pill().style.display, id: state.auditId, place: state.auditLocation };
""" % json.dumps(real["cancel"]))
    assert res["up"] is False and res["active"] is False and res["pill"] == "none"
    assert res["id"] is None and res["place"] == ""      # kept, every later scan would be stamped with it
    assert res["here"] == real["cancel"]["audit_ended"]["id"]
    assert res["toasts"] == [{"msg": "Audit cancelled: nothing moved.", "type": "info"}]


def test_a_refused_cancel_says_so_and_flips_nothing(tmp_path):
    """RED on 25738af: the answer was never read, and the page had flipped."""
    words = "The audit is already finishing."
    res = _run(tmp_path, """
answerWith('/api/identify_scan', [{ type: 'error', msg: %s }]);
await running(SESSION);
cancelBtn().onclick();
await __settle(60);
return { up: panelUp(), active: state.auditActive, toasts: toasts(), notice: noticeText(),
         disabled: cancelBtn().disabled };
""" % json.dumps(words))
    assert res["up"] is True and res["active"] is True and res["disabled"] is False
    assert {"msg": words, "type": "error"} in res["toasts"] and res["notice"] == words


def test_a_cancel_that_gets_no_answer_says_the_audit_still_runs(tmp_path):
    res = _run(tmp_path, """
await running(SESSION);
window.fetchT = () => Promise.reject(new Error('no route to FCC'));
cancelBtn().onclick();
await __settle(60);
return { active: state.auditActive, up: panelUp(), toasts: toasts(), notice: noticeText() };
""")
    assert res["active"] is True and res["up"] is True
    assert "still running" in res["notice"] and any("still running" in t["msg"] for t in res["toasts"])


def test_a_cancel_nothing_took_asks_the_server_why(tmp_path):
    """The server had no audit: CMD:CANCEL fell through the gate. The heartbeat
    this asks for corrects the page, with the reason."""
    res = _run(tmp_path, """
answerWith('/api/identify_scan', [{ type: 'command', cmd: 'cancel' }]);
await running(SESSION);
__heartbeat = { logs: [], status: {}, audit_active: false,
                audit_end: { id: 'boot-1', why: 'idle', location: 'LR-MDB-1' } };
cancelBtn().onclick();
await __settle(80);
return { active: state.auditActive, warnings: warnings() };
""")
    assert res["active"] is False
    assert res["warnings"] == ["The audit of LR-MDB-1 ended (idle for 30 minutes): scans go to the buffer again."]


def test_done_is_the_scan_path_with_no_label_read(tmp_path, real):
    """RED on 25738af: the button posted a bare CMD:DONE itself, flipped the flag
    first, and never read the answer, and a bare CMD:DONE hears "reload" now. PIN
    UPDATED DELIBERATELY (Group 58 review): it says which audit it was pressed for."""
    res = _run(tmp_path, """
answerWith('/api/identify_scan', [%s]);
await running(SESSION);
doneBtn().onclick();
await __settle(60);
return { posts: posts('/api/identify_scan'), committed: typeof window.commitAuditWithAutoPark,
         active: state.auditActive };
""" % json.dumps(real["question"]))
    assert res["posts"] == [{"text": "CMD:DONE", "source": "keyboard", "confirmed_fed_heads": [], "audit_ask": True,
                             "audit_seen": SESSION["audit_id"]}]
    assert res["committed"] == "undefined"
    assert res["active"] is True           # the question's answer ended nothing


def test_done_and_cancel_disable_until_the_answer(tmp_path, real):
    """RED on 25738af: a slow answer took a second press. A redraw in the middle
    must not hand the buttons back."""
    res = _run(tmp_path, """
let release;
const answer = new Promise((r) => { release = r; });
const real = window.fetch;
window.fetchT = (u, o) => (u === '/api/identify_scan'
    ? answer.then(() => real(u, o)) : real(u, o));
answerWith('/api/identify_scan', [%s]);
await running(SESSION);
doneBtn().onclick();
const pressed = [doneBtn().disabled, cancelBtn().disabled];
doneBtn().onclick();
cancelBtn().onclick();
__session = Object.assign({}, SESSION, { note: 'changed' });
window.refreshAuditSession();
await __settle(60);
const redrawn = [doneBtn().disabled, cancelBtn().disabled];
release();
await __settle(60);
return { pressed, redrawn, answered: [doneBtn().disabled, cancelBtn().disabled], scans: scans() };
""" % json.dumps(real["question"]))
    assert res["pressed"] == [True, True] and res["redrawn"] == [True, True]
    assert res["answered"] == [False, False]
    assert res["scans"] == ["CMD:DONE"]    # one press, one request


def test_cancel_disables_both_too_and_a_second_press_sends_nothing(tmp_path, real):
    res = _run(tmp_path, """
let release;
const answer = new Promise((r) => { release = r; });
const real = window.fetch;
window.fetchT = (u, o) => (u === '/api/identify_scan' ? answer.then(() => real(u, o)) : real(u, o));
answerWith('/api/identify_scan', [{ type: 'error', msg: 'The audit is already finishing.' }]);
await running(SESSION);
cancelBtn().onclick();
const pressed = [doneBtn().disabled, cancelBtn().disabled];
cancelBtn().onclick();
window.cancelAudit();
doneBtn().onclick();
await __settle(20);
release();
await __settle(60);
return { pressed, answered: [doneBtn().disabled, cancelBtn().disabled], scans: scans() };
""")
    assert res["pressed"] == [True, True] and res["answered"] == [False, False]
    assert res["scans"] == ["CMD:CANCEL"]


def test_done_under_a_gating_dialog_says_so_instead_of_vanishing(tmp_path):
    """processScan drops a scan without a word while one is armed, and the button
    used to post past it. RED on 25738af: nothing said so (it posted straight past)."""
    res = _run(tmp_path, """
await running(SESSION);
state.activeModal = 'confirm';
doneBtn().onclick();
await __settle(60);
return { scans: scans(), notice: noticeText(), disabled: doneBtn().disabled };
""")
    assert res["scans"] == [] and "behind this panel" in res["notice"] and res["disabled"] is False


# --- what a scan's answer does ----------------------------------------------------

@pytest.mark.parametrize("text", ["LOC:LR-MDB-1", "ID:57", "CMD:DONE", "CMD:CANCEL", "57", "some junk"])
def test_every_scan_says_this_page_can_show_the_question(tmp_path, text):
    """`audit_ask`, a real true. RED on 25738af: without it a Done hears "reload"."""
    res = _run(tmp_path, """
answerWith('/api/identify_scan', [{ type: 'error', msg: 'whatever' }]);
window.processScan(%s, 'barcode');
await __settle(60);
return { posts: posts('/api/identify_scan') };
""" % json.dumps(text))
    assert [p.get("audit_ask") for p in res["posts"]] == [True]


def test_a_scan_the_audit_took_refreshes_the_panel_at_once(tmp_path, real):
    """As refreshBulkMoveSession does. RED on 25738af: the tile waited for the next
    2 s tick."""
    res = _run(tmp_path, """
answerWith('/api/identify_scan', [%s]);
await running(SESSION);
const before = sessionReads();
window.processScan('ID:57', 'barcode');
await __settle(60);
return { reads: sessionReads() - before };
""" % json.dumps(real["found"]))
    assert res["reads"] == 1


def test_a_refresh_while_a_poll_is_out_waits_and_then_reads_once(tmp_path):
    """Slow polls never stack, and a scan's "read now" isn't lost behind one, or its
    tile would wait for the next tick."""
    res = _run(tmp_path, """
await running(SESSION);
let release;
const held = new Promise((r) => { release = r; });
const plain = window.fetchT;
let hold = 1;
window.fetchT = (u, o) => (u === '/api/audit_session' && hold-- > 0 ? held.then(() => plain(u, o)) : plain(u, o));
const before = sessionReads();
window.refreshAuditSession();
window.refreshAuditSession();
window.refreshAuditSession();
await __settle(20);
const waiting = sessionReads() - before;
release();
await __settle(40);
return { waiting, reads: sessionReads() - before };
""")
    assert res["waiting"] == 0 and res["reads"] == 2


def test_a_scan_right_after_a_reload_shows_the_audit_at_once(tmp_path, real):
    """The flag reads false until the first heartbeat, and the server's answer
    already says an audit runs. RED on 25738af: the scan's answer changed nothing."""
    res = _run(tmp_path, """
answerWith('/api/identify_scan', [%s]);
__session = SESSION;
window.processScan('ID:57', 'barcode');
await __settle(60);
return { active: state.auditActive, up: panelUp() };
""" % json.dumps(real["found"]))
    assert res["active"] is True and res["up"] is True


def test_a_spool_in_the_buffer_raises_no_clear_buffer_prompt(tmp_path, real):
    """The real answers with an audit up. Pins s2's server fix from the page's side:
    a hidden "Clear entire Buffer?" (z 1100, under the z 20000 panel) ate every
    later scan. RED on bf517da's parent, green since."""
    res = _run(tmp_path, """
answerWith('/api/identify_scan', [%s]);
await running(SESSION);
for (const text of ['LOC:LR-MDB-1', 'ID:57', 'ID:99']) { window.processScan(text, 'barcode'); await __settle(40); }
return { modal: state.activeModal, pending: !!state.pendingConfirm, scans: scans(), held: state.heldSpools.map(s => s.id) };
""" % ", ".join(json.dumps(real[k]) for k in ("place", "found", "extra")))
    assert res["modal"] is None and res["pending"] is False
    assert res["scans"] == ["LOC:LR-MDB-1", "ID:57", "ID:99"] and res["held"] == [57]


def test_a_location_scan_after_the_audit_ended_moves_nothing(tmp_path):
    """The server has no audit (it answered a plain location) and the page hasn't
    heard. In an audit a second location is refused; left to run on it filed the
    whole buffer there, unasked. RED on 25738af: the buffer moved."""
    res = _run(tmp_path, """
answerWith('/api/identify_scan', [{ type: 'location', id: 'LR-MDB-1', display: 'LOC: LR-MDB-1', contents: [] }]);
__heartbeat = Object.assign({}, %s, { audit_active: false, audit_end: { id: 'boot-1', why: 'cancel', location: 'LR-MDB-1' } });
await running(SESSION);
window.processScan('LOC:LR-MDB-1', 'barcode');
await __settle(80);
return { moves: posts('/api/manage_contents'), smart: posts('/api/smart_move'), held: state.heldSpools.map(s => s.id),
         active: state.auditActive, toasts: timed() };
""" % json.dumps(LOG_KEYS))
    assert res["moves"] == [] and res["smart"] == [] and res["held"] == [57]
    assert res["active"] is False          # the answer sent the page to ask why
    warned = {t["msg"]: t["ms"] for t in res["toasts"] if t["type"] == "warning"}
    assert warned == {"The audit has ended, so LR-MDB-1 did nothing. Scan it again if you meant it.": 7000,
                      "The audit of LR-MDB-1 ended (elsewhere): scans go to the buffer again.": 7000}


def test_a_done_on_a_panel_the_server_has_no_audit_for_asks_why_at_once(tmp_path):
    """The panel is at most 2 s behind. CMD:DONE fell through the gate, and only
    closed a Location Manager."""
    res = _run(tmp_path, """
window.closeManage = () => {};
answerWith('/api/identify_scan', [{ type: 'command', cmd: 'done' }]);
__heartbeat = Object.assign({}, %s, { audit_active: false, audit_end: { id: 'boot-1', why: 'cancel', location: 'LR-MDB-1' } });
await running(SESSION);
doneBtn().onclick();
await __settle(80);
return { active: state.auditActive, up: panelUp(), warnings: warnings() };
""" % json.dumps(LOG_KEYS))
    assert res["active"] is False and res["up"] is False
    assert res["warnings"] == ["The audit of LR-MDB-1 ended (elsewhere): scans go to the buffer again."]


def test_a_spool_scan_after_the_audit_ended_asks_why_at_once(tmp_path):
    """It joins the buffer, as the warning says it will. RED on 25738af: not a word
    until a heartbeat, up to 30 s on."""
    res = _run(tmp_path, """
answerWith('/api/identify_scan', [{ type: 'spool', id: 99, display: '#99', color: '123456' }]);
__heartbeat = Object.assign({}, %s, { audit_active: false, audit_end: null });
await running(SESSION);
window.processScan('ID:99', 'barcode');
await __settle(80);
return { active: state.auditActive, warnings: warnings(), held: state.heldSpools.map(s => s.id) };
""" % json.dumps(LOG_KEYS))
    assert res["active"] is False and sorted(res["held"]) == [57, 99]
    assert res["warnings"] == ["The audit of LR-MDB-1 ended (FCC restarted): scans go to the buffer again."]


# --- an audit that ended under the page -------------------------------------------

@pytest.mark.parametrize("end, words", [
    ({"id": "boot-1", "why": "idle", "location": "LR-MDB-1"},
     "The audit of LR-MDB-1 ended (idle for 30 minutes): scans go to the buffer again."),
    ({"id": "boot-1", "why": "cancel", "location": "LR-MDB-1"},
     "The audit of LR-MDB-1 ended (elsewhere): scans go to the buffer again."),
    ({"id": "boot-1", "why": "done", "location": "LR-MDB-1"},
     "The audit of LR-MDB-1 ended (elsewhere): scans go to the buffer again."),
    (None, "The audit of LR-MDB-1 ended (FCC restarted): scans go to the buffer again."),
    ({"id": "boot2-1", "why": "cancel", "location": "DR"},
     "The audit of LR-MDB-1 ended (FCC restarted): scans go to the buffer again."),
    ({"id": "boot-2", "why": "cancel", "location": "DR"},
     "The audit of LR-MDB-1 ended (elsewhere): scans go to the buffer again."),
    ({"id": "boot-2", "why": "idle", "location": "DR"},
     "The audit of LR-MDB-1 ended (elsewhere): scans go to the buffer again."),
], ids=["watchdog", "cancelled-elsewhere", "done-elsewhere", "restarted", "another-boots-audit",
        "a-later-audit-of-this-run", "a-later-audit-of-this-run-left-idle"])
def test_an_audit_ended_without_this_page_warns_once_and_logs_it(tmp_path, end, words):
    """RED on 25738af: the panel just closed. The next location label then moved
    the whole buffer with no question."""
    res = _run(tmp_path, """
await running(SESSION);
const end = %s;
const beat = { logs: [], status: {}, audit_active: false, audit_end: end };
__session = { active: false, audit_end: end };
await heartbeat(beat);
await heartbeat(Object.assign({}, beat, { logs: [{ time: '1', msg: 'next tick', type: 'info' }] }));
return { toasts: timed(), log: logLines(), active: state.auditActive, up: panelUp(),
         pill: pill().style.display, tile: document.getElementById('lbl-audit').innerText,
         id: state.auditId, place: state.auditLocation };
""" % json.dumps(end))
    assert res["toasts"] == [{"msg": words, "type": "warning", "ms": 7000}]
    assert res["id"] is None and res["place"] == ""
    assert res["log"] == [f"⚠️ {words}"]
    assert res["active"] is False and res["up"] is False and res["pill"] == "none"
    assert res["tile"] == "AUDIT"


def test_a_later_audit_of_this_run_ending_is_no_restart(tmp_path, env):
    """On the real ids and the real heartbeat: this page's audit ended and another
    started and ended inside one heartbeat, with its panel hidden. Nothing restarted,
    and the two ids share their boot token. RED on 8373ecd: "FCC restarted"."""
    add_spool(env, 57, "LR-MDB-1", container_slot="1")
    add_spool(env, 58, "LR-MDB-2", container_slot="1")
    start(env, "LR-MDB-1")
    first = session()["audit_id"]
    scan(env, "CMD:CANCEL")
    start(env, "LR-MDB-2")
    second = session()["audit_id"]
    scan(env, "CMD:CANCEL")
    beat = app_module.app.test_client().get("/api/logs").get_json()
    assert beat["audit_end"]["id"] == second != first
    res = _run(tmp_path, """
await running(Object.assign({}, SESSION, { audit_id: %s }));
panel().querySelector('#fcc-audit-panel-close').onclick();
await heartbeat(%s);
return { warnings: warnings() };
""" % (json.dumps(first), json.dumps(beat)))
    assert res["warnings"] == ["The audit of LR-MDB-1 ended (elsewhere): scans go to the buffer again."]


def test_an_audit_with_no_place_yet_says_so_in_fewer_words(tmp_path):
    res = _run(tmp_path, """
await running(Object.assign({}, SESSION, { location_id: null }));
await heartbeat({ logs: [], status: {}, audit_active: false, audit_end: { id: 'boot-1', why: 'idle', location: '' } });
return { warnings: warnings() };
""")
    assert res["warnings"] == ["The audit ended (idle for 30 minutes): scans go to the buffer again."]


def test_a_page_that_never_polled_still_says_idle_without_a_number(tmp_path):
    """The panel's poll gives the page its limit, and a Hide can beat it."""
    res = _run(tmp_path, """
state.auditActive = true; state.lastAuditState = true;
state.auditLocation = 'LR-MDB-1';
await heartbeat({ logs: [], status: {}, audit_active: false, audit_end: { id: 'boot-1', why: 'idle', location: 'LR-MDB-1' } });
return { warnings: warnings() };
""")
    assert res["warnings"] == ["The audit of LR-MDB-1 ended (left idle): scans go to the buffer again."]


def test_a_place_with_odd_text_reaches_the_log_escaped(tmp_path):
    """The Activity Log draws its lines as HTML."""
    res = _run(tmp_path, """
await running(SESSION);
await heartbeat({ logs: [], status: {}, audit_active: false, audit_end: { id: 'boot-1', why: 'idle', location: '<b>X' } });
return { log: logLines() };
""")
    assert "&lt;b&gt;X" in res["log"][0] and "<b>" not in res["log"][0]


def test_the_panels_own_poll_sees_the_end_first_and_only_it_warns(tmp_path):
    """The poll lands up to 28 s before a heartbeat. RED on 25738af: it closed the
    panel without a word."""
    res = _run(tmp_path, """
await running(SESSION);
const end = { id: 'boot-1', why: 'idle', location: 'LR-MDB-1' };
__session = { active: false, audit_end: end };
window.refreshAuditSession();
await __settle(40);
const after = { up: panelUp(), active: state.auditActive };
await heartbeat({ logs: [], status: {}, audit_active: false, audit_end: end });
return { after, warnings: warnings() };
""")
    assert res["after"] == {"up": False, "active": False}
    assert res["warnings"] == ["The audit of LR-MDB-1 ended (idle for 30 minutes): scans go to the buffer again."]


@pytest.mark.parametrize("ender", ["cancel", "done"])
def test_a_scanned_done_or_cancel_on_this_page_warns_nothing(tmp_path, real, ender):
    """The real answer, then the real heartbeats that follow it. A page-side guess
    would fire on every scanned Done: the answer's `audit_ended` is the word."""
    answer = real[ender]
    beat = real["heartbeat_ended" if ender == "cancel" else "heartbeat_done"]
    assert answer["audit_ended"]["id"] == beat["audit_end"]["id"], (answer, beat)
    res = _run(tmp_path, """
answerWith('/api/identify_scan', [%s]);
await running(SESSION);
window.processScan('CMD:%s', 'barcode');
await __settle(60);
const answered = { up: panelUp(), active: state.auditActive };
await heartbeat(%s);
return { answered, warnings: warnings(), log: logLines(), toasts: toasts() };
""" % (json.dumps(answer), ender.upper(), json.dumps(beat)))
    assert res["answered"] == {"up": False, "active": False}
    assert res["warnings"] == [] and res["log"] == []
    assert len(res["toasts"]) == 1


@pytest.mark.parametrize("ender", ["cancel", "done"])
def test_the_panels_poll_landing_before_the_answer_warns_nothing(tmp_path, real, ender):
    """The server has ended it and the POST's answer is still on its way: the 2 s
    poll sees "no audit" with an id this page hasn't been told about yet."""
    answer = real[ender]
    res = _run(tmp_path, """
let release;
const held = new Promise((r) => { release = r; });
const real = window.fetch;
window.fetchT = (u, o) => (u === '/api/identify_scan' ? held.then(() => real(u, o)) : real(u, o));
answerWith('/api/identify_scan', [%s]);
await running(SESSION);
window.processScan('CMD:%s', 'barcode');
__session = { active: false, audit_end: Object.assign({ location: 'LR-MDB-1' }, %s) };
window.refreshAuditSession();
await __settle(40);
const during = { up: panelUp(), active: state.auditActive };
release();
await __settle(60);
return { during, up: panelUp(), active: state.auditActive, warnings: warnings() };
""" % (json.dumps(answer), ender.upper(), json.dumps(answer["audit_ended"])))
    assert res["during"] == {"up": True, "active": True}      # waits for its own answer
    assert res["up"] is False and res["active"] is False and res["warnings"] == []


def test_a_heartbeat_sent_before_the_start_cant_undo_it(tmp_path):
    """A heartbeat can take seconds. One asked for before the tile was pressed lands
    after the answer: it says "no audit" of a moment that has passed."""
    res = _run(tmp_path, """
answerWith('/api/identify_scan', [{ type: 'command', cmd: 'audit_scan' }]);
__session = SESSION;
const sentAt = window.fccPageClock() - 1;
toggleAudit();
await __settle(60);
await heartbeat({ logs: [], status: {}, audit_active: false, audit_end: null }, { sentAt });
return { active: state.auditActive, up: panelUp(), warnings: warnings() };
""")
    assert res["active"] is True and res["up"] is True and res["warnings"] == []


def test_a_heartbeat_sent_before_an_end_cant_bring_the_audit_back(tmp_path, real):
    res = _run(tmp_path, """
answerWith('/api/identify_scan', [%s]);
await running(SESSION);
const sentAt = window.fccPageClock() - 1;
window.processScan('CMD:CANCEL', 'barcode');
await __settle(60);
await heartbeat({ logs: [], status: {}, audit_active: true, audit_location: 'LR-MDB-1', audit_end: null }, { sentAt });
return { active: state.auditActive, up: panelUp(), panels: panelCount() };
""" % json.dumps(real["cancel"]))
    assert res["active"] is False and res["up"] is False and res["panels"] == 1


def test_two_heartbeats_passing_each_other_warn_once(tmp_path):
    """The newer lands first. The older still says the audit runs: believed, it
    would reopen the panel, and the next tick would warn again."""
    res = _run(tmp_path, """
await running(SESSION);
const end = { id: 'boot-1', why: 'cancel', location: 'LR-MDB-1' };
const older = window.fccPageClock();
await __settle(5);
const newer = window.fccPageClock();
await heartbeat({ logs: [], status: {}, audit_active: false, audit_end: end }, { sentAt: newer });
await heartbeat({ logs: [], status: {}, audit_active: true, audit_location: 'LR-MDB-1', audit_end: null }, { sentAt: older });
const after = { active: state.auditActive, up: panelUp() };
await heartbeat({ logs: [], status: {}, audit_active: false, audit_end: end }, { sentAt: window.fccPageClock() });
return { after, warnings: warnings(), panels: panelCount() };
""")
    assert res["after"] == {"active": False, "up": False}
    assert len(res["warnings"]) == 1 and res["panels"] == 1


def test_a_poll_still_out_when_the_audit_ended_leaves_nothing_behind(tmp_path, real):
    """It answers for the audit that just ended. Its id, kept, would make the next
    audit's end read as a restart."""
    res = _run(tmp_path, """
answerWith('/api/identify_scan', [%s]);
await running(SESSION);
state.auditId = null;
let release;
const held = new Promise((r) => { release = r; });
const real = window.fetchT;
window.fetchT = (u, o) => (u === '/api/audit_session' ? held.then(() => real(u, o)) : real(u, o));
window.refreshAuditSession();
window.processScan('CMD:CANCEL', 'barcode');
await __settle(40);
release();
await __settle(40);
return { id: state.auditId, place: state.auditLocation, up: panelUp(), active: state.auditActive };
""" % json.dumps(real["cancel"]))
    assert res == {"id": None, "place": "", "up": False, "active": False, "unhandled": []}


def test_a_scans_answer_landing_after_the_end_cant_bring_the_audit_back(tmp_path, real):
    """Scans aren't serial. "An audit took it" was true when the scan was sent. The
    wait between the two is the clock's: node's vm has no `performance`, so the page's
    clock is whole milliseconds here, the scan and the Cancel's answer can tie, and a
    tie reads as "not older". No real answer comes back inside its own millisecond."""
    res = _run(tmp_path, """
answerWith('/api/identify_scan', [%s, %s]);
await running(SESSION);
let release;
const held = new Promise((r) => { release = r; });
let sent = 0;
const plain = window.fetch;
window.fetchT = (u, o) => {
  if (u !== '/api/identify_scan' || sent++ > 0) return plain(u, o);
  const answer = plain(u, o);
  return held.then(() => answer);
};
window.processScan('ID:57', 'barcode');
await __settle(5);
window.processScan('CMD:CANCEL', 'barcode');
await __settle(40);
const ended = state.auditActive;
release();
await __settle(40);
return { ended, active: state.auditActive, up: panelUp(), panels: panelCount() };
""" % (json.dumps(real["found"]), json.dumps(real["cancel"])))
    assert res["ended"] is False
    assert res["active"] is False and res["up"] is False and res["panels"] == 1


def test_an_end_this_page_was_told_about_never_warns(tmp_path):
    """Build spec: the warning is for an audit with no `audit_ended` of this page's
    own. An answer that ended the audit flips the page at once, so this is the belt:
    a heartbeat naming that very end says nothing, whatever the page believes.
    Passes on 25738af, where nothing warned: it bites with the warning (a mutant
    without the check goes red)."""
    res = _run(tmp_path, """
await running(SESSION);
state.auditEndedHere = 'boot-1';
await heartbeat({ logs: [], status: {}, audit_active: false,
                  audit_end: { id: 'boot-1', why: 'cancel', location: 'LR-MDB-1' } });
return { active: state.auditActive, warnings: warnings() };
""")
    assert res["active"] is False and res["warnings"] == []


@pytest.mark.parametrize("section", ["logs", "status"])
def test_a_pulse_sent_before_the_start_cant_undo_it(tmp_path, section):
    """Through the real tick, which takes seconds on a slow Spoolman. RED on 25738af:
    the tile's press flipped a flag the next heartbeat knew nothing about."""
    res = _run(tmp_path, """
answerWith('/api/identify_scan', [{ type: 'command', cmd: 'audit_scan' }]);
__session = SESSION;
const part = { audit_active: false, audit_location: '', audit_end: null, spoolman: true, logs: [] };
const pulse = %s === 'logs' ? { logs: part } : { status: part };
let release;
const held = new Promise((r) => { release = r; });
const before = window.__extra;
window.__extra = (url) => (url.startsWith('/api/dashboard_pulse') ? { body: pulse } : before(url));
const plain = window.fetch;
window.fetch = (u, o) => (String(u).startsWith('/api/dashboard_pulse') ? held.then(() => plain(u, o)) : plain(u, o));
window._dashboardPulseTickOnce();
await __settle(5);
toggleAudit();
await __settle(40);
release();
await __settle(40);
return { active: state.auditActive, up: panelUp(), warnings: warnings() };
""" % json.dumps(section))
    assert res["active"] is True and res["up"] is True and res["warnings"] == []


def test_a_log_poll_sent_before_the_start_cant_undo_it(tmp_path):
    """/api/logs, as a pulse: the page's forced read goes the same way."""
    res = _run(tmp_path, """
answerWith('/api/identify_scan', [{ type: 'command', cmd: 'audit_scan' }]);
__session = SESSION;
__heartbeat = { logs: [], status: {}, audit_active: false, audit_end: null };
let release;
const held = new Promise((r) => { release = r; });
const plain = window.fetch;
window.fetch = (u, o) => (String(u).startsWith('/api/logs') ? held.then(() => plain(u, o)) : plain(u, o));
updateLogState(true);
await __settle(5);
toggleAudit();
await __settle(40);
release();
await __settle(40);
return { active: state.auditActive, up: panelUp(), warnings: warnings() };
""")
    assert res["active"] is True and res["up"] is True and res["warnings"] == []


def _two_audits(env):
    """An audit that has ended, the real heartbeat of the one running after it, and
    that one's id."""
    add_spool(env, 57, "LR-MDB-1", container_slot="1")
    add_spool(env, 58, "LR-MDB-2", container_slot="1")
    start(env, "LR-MDB-1")
    first = session()["audit_id"]
    scan(env, "CMD:CANCEL")
    start(env, "LR-MDB-2")
    return first, app_module.app.test_client().get("/api/logs").get_json(), session()["audit_id"]


def test_the_heartbeat_keeps_a_hidden_panels_id_current(tmp_path, env):
    """A hidden panel has no poll. With the old id every scan would be stamped with an
    audit that has gone, and refused while another runs. RED on 8373ecd."""
    first, beat, second = _two_audits(env)
    assert beat["audit_id"] == second != first
    res = _run(tmp_path, """
await running(Object.assign({}, SESSION, { audit_id: %s }));
panel().querySelector('#fcc-audit-panel-close').onclick();
const beat = %s;
__session = Object.assign({}, SESSION, { audit_id: beat.audit_id });
await heartbeat(beat);
answerWith('/api/identify_scan', [{ type: 'command', cmd: 'audit_scan' }]);
window.processScan('ID:58', 'barcode');
await __settle(40);
return { id: state.auditId, seen: posts('/api/identify_scan')[0].audit_seen, warnings: warnings() };
""" % (json.dumps(first), json.dumps(beat)))
    assert res["id"] == second and res["seen"] == second and res["warnings"] == []


@pytest.mark.parametrize("section", ["logs", "status"])
def test_both_heartbeat_shapes_carry_the_id(tmp_path, section):
    """Each section's own keys, as routes_state_pulse.py sends them, through the real
    tick. RED on 8373ecd."""
    res = _run(tmp_path, """
await running(SESSION);
panel().querySelector('#fcc-audit-panel-close').onclick();
const part = { audit_active: true, audit_id: 'boot-2', audit_location: 'LR-MDB-1', audit_end: null, spoolman: true, logs: [] };
const pulse = %s === 'logs' ? { logs: part } : { status: part };
const before = window.__extra;
window.__extra = (url) => (url.startsWith('/api/dashboard_pulse') ? { body: pulse } : before(url));
window._dashboardPulseTickOnce();
await __settle(60);
return { id: state.auditId };
""" % json.dumps(section))
    assert res["id"] == "boot-2"


def test_a_heartbeat_sent_before_the_page_changed_its_mind_leaves_the_id_alone(tmp_path):
    """The id goes after the heartbeat's sentAt check, or an old one would name the
    audit this page has just heard the end of. A pin of the order: proved on a copy with
    the id above the check."""
    res = _run(tmp_path, """
await running(SESSION);
const sentAt = window.fccPageClock() - 1;
state.auditChangedAt = window.fccPageClock();
await heartbeat({ logs: [], status: {}, audit_active: true, audit_id: 'boot-0', audit_location: 'LR-MDB-1', audit_end: null }, { sentAt });
return { id: state.auditId };
""")
    assert res["id"] == SESSION["audit_id"]


def test_an_older_heartbeat_cant_take_the_place_back(tmp_path, real):
    """The heartbeat's real shape, from before the place was scanned. It takes seconds
    (printer probes run after the keys are read), and it lands after the scan's own
    answer. RED on 8373ecd: the pill read "scan a location" again, and a person who
    scanned the place again was refused."""
    beat = real["heartbeat_no_place"]
    assert beat["audit_active"] is True and beat["audit_location"] == ""
    res = _run(tmp_path, """
answerWith('/api/identify_scan', [%s]);
await running(Object.assign({}, SESSION, { location_id: null }));
panel().querySelector('#fcc-audit-panel-close').onclick();
const sentAt = window.fccPageClock();
await __settle(5);
__session = SESSION;
window.processScan('LOC:LR-MDB-1', 'barcode');
await __settle(60);
const learned = pillText();
await heartbeat(%s, { sentAt });
return { learned, pill: pillText(), place: state.auditLocation };
""" % (json.dumps(real["place"]), json.dumps(beat)))
    assert res == {"learned": "audit: LR-MDB-1", "pill": "audit: LR-MDB-1", "place": "LR-MDB-1", "unhandled": []}


def test_a_heartbeat_sent_after_the_place_was_learned_still_counts(tmp_path):
    """The control. A pin: proved on a copy where a learned place never changes."""
    res = _run(tmp_path, """
await running(SESSION);
panel().querySelector('#fcc-audit-panel-close').onclick();
await __settle(5);
await heartbeat({ logs: [], status: {}, audit_active: true, audit_id: 'boot-1', audit_location: 'LR-MDB-2', audit_end: null },
                { sentAt: window.fccPageClock() });
return { pill: pillText() };
""")
    assert res["pill"] == "audit: LR-MDB-2"


def test_an_older_poll_cant_take_back_a_place_a_newer_heartbeat_learned(tmp_path):
    """The other half: the panel's own poll, with the same stamp. RED on 8373ecd."""
    res = _run(tmp_path, """
await running(Object.assign({}, SESSION, { location_id: null }));
let release;
const held = new Promise((r) => { release = r; });
const plain = window.fetchT;
window.fetchT = (u, o, ms) => (u === '/api/audit_session' ? held.then(() => plain(u, o, ms)) : plain(u, o, ms));
window.refreshAuditSession();
await __settle(5);
await heartbeat({ logs: [], status: {}, audit_active: true, audit_id: 'boot-1', audit_location: 'LR-MDB-1', audit_end: null },
                { sentAt: window.fccPageClock() });
const learned = state.auditLocation;
release();
await __settle(40);
return { learned, place: state.auditLocation, pill: pillText() };
""")
    assert res == {"learned": "LR-MDB-1", "place": "LR-MDB-1", "pill": "audit: LR-MDB-1", "unhandled": []}


def test_the_first_heartbeat_paints_the_tile(tmp_path):
    """Pins what was already right: a page's first word from the server paints the
    deck, audit or no audit."""
    res = _run(tmp_path, """
await heartbeat({ logs: [], status: {}, audit_active: false, audit_end: null });
return { tile: document.getElementById('lbl-audit').innerText, last: state.lastAuditState };
""")
    assert res["tile"] == "AUDIT" and res["last"] is False


def test_a_stale_heartbeat_dropped_doesnt_hide_the_same_words_next_tick(tmp_path):
    """The log's hash check would skip a second, identical answer."""
    res = _run(tmp_path, """
await running(SESSION);
state.auditChangedAt = window.fccPageClock();
const beat = { logs: [], status: {}, audit_active: false, audit_end: null };
await heartbeat(beat, { sentAt: state.auditChangedAt - 1 });
const dropped = state.auditActive;
await heartbeat(beat, { sentAt: window.fccPageClock() + 1 });
return { dropped, active: state.auditActive };
""")
    assert res == {"dropped": True, "active": False, "unhandled": []}


def test_a_wrong_belief_heals_at_the_next_heartbeat(tmp_path):
    """The heartbeat used to act only when it changed, so a page wrong about the
    audit stayed wrong until a reload. RED on 25738af."""
    res = _run(tmp_path, """
state.auditActive = true;
state.lastAuditState = false;
await heartbeat({ logs: [], status: {}, audit_active: false, audit_end: null });
return { active: state.auditActive };
""")
    assert res["active"] is False


def test_an_audit_started_elsewhere_opens_here_with_its_place(tmp_path, real):
    beat = real["heartbeat_active"]
    assert beat["audit_active"] is True and beat["audit_location"] == "LR-MDB-1"
    res = _run(tmp_path, """
__session = SESSION;
await heartbeat(%s);
return { active: state.auditActive, up: panelUp(), pill: pillText(), warnings: warnings() };
""" % json.dumps(beat))
    assert res["active"] is True and res["up"] is True and res["pill"] == "audit: LR-MDB-1"
    assert res["warnings"] == []


def test_a_new_place_in_the_heartbeat_names_the_pill_and_leaves_a_hide_alone(tmp_path):
    """updateAuditVisuals opens the panel, so the pill's words go their own way."""
    res = _run(tmp_path, """
__session = Object.assign({}, SESSION, { location_id: null });
await running(__session);
panel().querySelector('#fcc-audit-panel-close').onclick();
await heartbeat({ logs: [], status: {}, audit_active: true, audit_location: 'LR-MDB-1', audit_end: null });
return { up: panelUp(), pill: pillText() };
""")
    assert res == {"up": False, "pill": "audit: LR-MDB-1", "unhandled": []}


@pytest.mark.parametrize("section", ["logs", "status"])
def test_both_heartbeat_shapes_carry_the_signal(tmp_path, section):
    """A paused Activity Log takes the `status` branch. Each section's own keys, as
    routes_state_pulse.py sends them, through the real tick. RED on 25738af."""
    res = _run(tmp_path, """
await running(SESSION);
const end = { id: 'boot-1', why: 'idle', location: 'LR-MDB-1' };
const part = { audit_active: false, audit_location: '', audit_end: end, spoolman: true, logs: [] };
const pulse = %s === 'logs' ? { logs: part } : { status: part };
const before = window.__extra;
window.__extra = (url) => (url.startsWith('/api/dashboard_pulse') ? { body: pulse } : before(url));
window._dashboardPulseTickOnce();
await __settle(60);
return { active: state.auditActive, warnings: warnings() };
""" % json.dumps(section))
    assert res["active"] is False
    assert res["warnings"] == ["The audit of LR-MDB-1 ended (idle for 30 minutes): scans go to the buffer again."]


# --- which audit a scan was read for (Group 58 review) ---------------------------------

def test_a_scan_says_which_audit_it_was_read_for(tmp_path):
    """`audit_seen`, logic.audit_seen_gone's question: true while the page has no id
    yet. RED on 8373ecd: nothing was sent, so a slot label read at a hidden panel after
    an idle end loaded the buffered spool."""
    res = _run(tmp_path, """
answerWith('/api/identify_scan', [{ type: 'error', msg: 'whatever' }]);
await running(SESSION);
window.processScan('ID:57', 'barcode');
await __settle(40);
state.auditId = null;
window.processScan('ID:57', 'barcode');
await __settle(40);
return { seen: posts('/api/identify_scan').map(p => p.audit_seen) };
""")
    assert res["seen"] == [SESSION["audit_id"], True]


def test_a_queued_scan_goes_out_with_the_stamp_it_was_read_with(tmp_path):
    """Not what the page believes by then. One read with no audit running asks no
    check at all. RED on 8373ecd."""
    res = _run(tmp_path, """
answerWith('/api/identify_scan', [{ type: 'error', msg: 'whatever' }]);
await running(SESSION);
window.processScan('ID:57', 'barcode', null, null, 'boot-0');
await __settle(40);
window.processScan('ID:57', 'barcode', null, null, null);
await __settle(40);
return { posts: posts('/api/identify_scan') };
""")
    assert res["posts"][0]["audit_seen"] == "boot-0" and "audit_seen" not in res["posts"][1]


def test_with_no_audit_a_scan_says_nothing_of_one(tmp_path):
    """The key is left out, so the server checks nothing and a request is as it was,
    byte for byte. A pin: proved on a copy that sends a null."""
    res = _run(tmp_path, """
answerWith('/api/identify_scan', [{ type: 'error', msg: 'whatever' }]);
window.processScan('ID:57', 'barcode');
await __settle(40);
return { posts: posts('/api/identify_scan') };
""")
    assert "audit_seen" not in res["posts"][0]


def _gone_answer(env, text):
    """The real route's answer to a scan read for an audit that has ended."""
    add_spool(env, 57, "LR-MDB-1", container_slot="1")
    start(env, "LR-MDB-1")
    audit_id = session()["audit_id"]
    scan(env, "CMD:CANCEL")
    answer = scan(env, text, audit_seen=audit_id)
    assert answer["type"] == "audit_gone"
    return answer, audit_id


def test_the_servers_audit_gone_is_said_for_7_seconds_on_the_panel_too(tmp_path, env):
    """The toast layer is under the panel. "Log nothing more": the server logged it.
    RED on 8373ecd: no branch read it, so the scan did nothing without a word."""
    answer, audit_id = _gone_answer(env, "LOC:LR-MDB-2:SLOT:2")
    res = _run(tmp_path, """
answerWith('/api/identify_scan', [%s]);
await running(Object.assign({}, SESSION, { audit_id: %s }));
window.processScan('LOC:LR-MDB-2:SLOT:2', 'barcode');
await __settle(60);
return { toasts: timed(), notice: noticeText(), log: logLines(), held: state.heldSpools.map(s => s.id) };
""" % (json.dumps(answer), json.dumps(audit_id)))
    words = "The audit has ended, so LOC:LR-MDB-2:SLOT:2 did nothing. Scan it again if you meant it."
    assert answer["msg"] == words
    assert res["toasts"] == [{"msg": words, "type": "warning", "ms": 7000}]
    assert res["notice"] == words and res["log"] == [] and res["held"] == [57]


def test_the_servers_audit_gone_asks_the_heartbeat_why_at_once(tmp_path, env):
    """The panel is up to 2 s behind, and a hidden one has no poll. RED on 8373ecd."""
    answer, audit_id = _gone_answer(env, "ID:57")
    beat = app_module.app.test_client().get("/api/logs").get_json()
    res = _run(tmp_path, """
answerWith('/api/identify_scan', [%s]);
__heartbeat = %s;
await running(Object.assign({}, SESSION, { audit_id: %s }));
window.processScan('ID:57', 'barcode');
await __settle(80);
return { active: state.auditActive, up: panelUp(), warnings: warnings() };
""" % (json.dumps(answer), json.dumps(beat), json.dumps(audit_id)))
    assert res["active"] is False and res["up"] is False
    assert "The audit of LR-MDB-1 ended (elsewhere): scans go to the buffer again." in res["warnings"]


OUTLIVED = [
    # (stamp, the page believes in an audit, its id, the scan's text), gone
    ((None, False, None, "LOC:LR-MDB-1"), False),         # read with no audit running
    ((None, True, "boot-2", "LOC:LR-MDB-1"), False),      # read before this one started
    (("boot-1", True, "boot-1", "LOC:LR-MDB-1"), False),  # still running
    (("boot-1", True, None, "LOC:LR-MDB-1"), False),      # no id to tell by: the server has it
    ((True, True, None, "LOC:LR-MDB-1"), False),
    ((True, True, "boot-1", "LOC:LR-MDB-1"), False),      # read before the id was heard
    (("boot-1", False, None, "LOC:LR-MDB-1"), True),
    ((True, False, None, "LOC:LR-MDB-1"), True),
    (("boot-1", True, "boot-2", "LOC:LR-MDB-1"), True),   # another audit runs now
    (("boot-1", False, None, "CMD:AUDIT"), False),        # it means the next audit
    (("boot-1", False, None, " cmd:audit "), False),
    (("boot-1", False, None, "CMD:DONE"), True),
]


@pytest.mark.parametrize("case, gone", OUTLIVED)
def test_which_queued_scans_have_outlived_their_audit(tmp_path, case, gone):
    """The rule of window.auditScanOutlived, and what a drop says and leaves behind. RED
    on 8373ecd: it doesn't exist. test_audit_no_label_58_js has it on the real routes."""
    stamp, active, audit_id, text = case
    res = _run(tmp_path, """
state.auditActive = %s; state.auditId = %s;
const gone = window.auditScanOutlived({ text: %s, auditOf: %s });
await __settle(10);
return { gone, toasts: timed(), log: logLines(), scans: scans() };
""" % (json.dumps(active), json.dumps(audit_id), json.dumps(text), json.dumps(stamp)))
    assert res["gone"] is gone and res["scans"] == []
    if gone:
        words = f"The audit has ended, so {text.strip()} did nothing. Scan it again if you meant it."
        assert res["toasts"] == [{"msg": words, "type": "warning", "ms": 7000}]
        assert res["log"] == [f"⚠️ {words}"]
    else:
        assert res["toasts"] == [] and res["log"] == []


def test_a_dropped_scans_text_reaches_the_log_escaped(tmp_path):
    """The Activity Log draws its lines as HTML. RED on 8373ecd."""
    res = _run(tmp_path, """
state.auditActive = false;
window.auditScanOutlived({ text: 'LOC:<b>X', auditOf: 'boot-1' });
await __settle(10);
return { log: logLines() };
""")
    assert "LOC:&lt;b&gt;X" in res["log"][0] and "<b>" not in res["log"][0]


# --- a hidden panel, and what a scan did ------------------------------------------------

def _audit_answers(env):
    """The real route's answers to the first two scans of an audit: `heard` kept.
    PIN UPDATED DELIBERATELY (Derek, 2026-11-03, H S2): the page below reads both as a
    scanner's ('barcode'), so the route is asked the same way; a typed id's `heard`
    now says no label was read."""
    add_spool(env, 57, "LR-MDB-1", container_slot="1")
    add_spool(env, 99, "LR-MDB-1", container_slot="2")
    scan(env, "CMD:AUDIT")
    return [scan_answer("LOC:LR-MDB-1", source="barcode"), scan_answer("ID:57", source="barcode")]


def test_a_hidden_panel_hears_what_each_scan_did(tmp_path, env):
    """Every scan outcome is owed a toast, and the panel that shows this one is hidden.
    RED on 8373ecd: the page ignored `heard`."""
    res = _run(tmp_path, """
answerWith('/api/identify_scan', %s);
await running(Object.assign({}, SESSION, { location_id: null }));
panel().querySelector('#fcc-audit-panel-close').onclick();
window.processScan('LOC:LR-MDB-1', 'barcode');
await __settle(40);
window.processScan('ID:57', 'barcode');
await __settle(40);
return { toasts: timed(), up: panelUp() };
""" % json.dumps(_audit_answers(env)))
    assert res["up"] is False
    assert res["toasts"] == [{"msg": "Auditing LR-MDB-1: 2 expected", "type": "info", "ms": 4000},
                             {"msg": "Found #57 (1 left)", "type": "info", "ms": 4000}]


def test_a_panel_on_screen_shows_it_itself(tmp_path, env):
    """A toast there would sit under it. A pin: proved on a copy that always toasts."""
    res = _run(tmp_path, """
answerWith('/api/identify_scan', %s);
await running(Object.assign({}, SESSION, { location_id: null }));
window.processScan('LOC:LR-MDB-1', 'barcode');
await __settle(40);
window.processScan('ID:57', 'barcode');
await __settle(40);
return { toasts: timed() };
""" % json.dumps(_audit_answers(env)))
    assert res["toasts"] == []


def test_a_scan_that_brings_the_panel_up_toasts_nothing_either(tmp_path, env):
    """Right after a reload: the answer proves an audit runs, and the panel opens on
    it. Asked first, the page would call that panel hidden. A pin of the order: proved
    on a copy that asks before the sync."""
    res = _run(tmp_path, """
answerWith('/api/identify_scan', %s);
__session = SESSION;
window.processScan('LOC:LR-MDB-1', 'barcode');
await __settle(40);
return { toasts: timed(), up: panelUp() };
""" % json.dumps(_audit_answers(env)))
    assert res["up"] is True and res["toasts"] == []


# --- a gating dialog behind the panel ---------------------------------------------------

GATED = {"confirm": "pendingConfirm", "safety": "pendingSafety"}


@pytest.mark.parametrize("modal", ["confirm", "safety", "action"])
def test_the_cancel_that_closes_a_gating_dialog_read_twice_leaves_the_audit_running(tmp_path, modal):
    """Its second read had no dialog left to take it, and a bare CMD:CANCEL is the
    audit's real Cancel. RED on 8373ecd: it went out, and every scan was gone."""
    res = _run(tmp_path, """
await running(SESSION);
state.activeModal = %s;
const read = Date.now();
window.processScan('CMD:CANCEL', 'barcode', read);
const closed = state.activeModal;
window.processScan('CMD:CANCEL', 'barcode', read + 40);
await __settle(60);
return { closed, scans: scans(), active: state.auditActive, up: panelUp(), toasts: toasts() };
""" % json.dumps(modal))
    assert res["closed"] is None and res["scans"] == []
    assert res["active"] is True and res["up"] is True
    assert {"msg": "Ignored a second read of CMD:CANCEL", "type": "info"} in res["toasts"]


def test_a_cancel_scanned_after_a_double_reads_window_is_meant(tmp_path):
    """Derek's rule: guard only the accidental case. A pin: proved on a copy with a
    longer window."""
    res = _run(tmp_path, """
answerWith('/api/identify_scan', [{ type: 'command', cmd: 'audit_scan', audit_ended: { id: 'boot-1', why: 'cancel' } }]);
await running(SESSION);
state.activeModal = 'confirm';
window.processScan('CMD:CANCEL', 'barcode', Date.now());
window.processScan('CMD:CANCEL', 'barcode', Date.now() + 1600);
await __settle(60);
return { scans: scans(), active: state.auditActive };
""")
    assert res["scans"] == ["CMD:CANCEL"] and res["active"] is False


@pytest.mark.parametrize("modal", GATED)
@pytest.mark.parametrize("text", ["ID:57", "LOC:LR-MDB-2", "CMD:DONE", "57"])
def test_a_scan_a_gating_dialog_would_swallow_says_so_on_the_panel(tmp_path, modal, text):
    """#confirmModal draws at z 1100 and the panel at 20000: the scan vanished, with
    nothing on screen to say why. RED on 8373ecd."""
    res = _run(tmp_path, """
await running(SESSION);
state.activeModal = %s;
window.processScan(%s, 'barcode');
await __settle(60);
return { scans: scans(), notice: noticeText(), toasts: toasts(), log: logLines(), modal: state.activeModal };
""" % (json.dumps(modal), json.dumps(text)))
    words = "A dialog behind this panel is still open: press Hide and answer it first."
    assert res["scans"] == [] and res["notice"] == words and res["modal"] == modal
    assert res["toasts"] == [{"msg": words, "type": "warning"}]
    assert len(res["log"]) == 1 and text in res["log"][0]


@pytest.mark.parametrize("modal", GATED)
def test_with_the_panel_hidden_the_dialog_is_on_screen_and_says_it_itself(tmp_path, modal):
    """Today's behaviour stands. A pin: proved on a copy with no panel test."""
    res = _run(tmp_path, """
await running(SESSION);
panel().querySelector('#fcc-audit-panel-close').onclick();
state.activeModal = %s;
window.processScan('ID:57', 'barcode');
await __settle(60);
return { scans: scans(), toasts: toasts(), log: logLines() };
""" % json.dumps(modal))
    assert res == {"scans": [], "toasts": [], "log": [], "unhandled": []}


@pytest.mark.parametrize("modal, slot", GATED.items())
def test_confirm_and_cancel_still_reach_the_dialog(tmp_path, modal, slot):
    """A pin: proved on a copy that refuses them too."""
    res = _run(tmp_path, """
await running(SESSION);
window.isGatingModalOnScreen = () => true;
let said = 0;
state.activeModal = %s; state[%s] = () => { said += 1; };
window.processScan('CMD:CONFIRM', 'barcode');
await __settle(40);
const yes = { said, modal: state.activeModal, notice: noticeText() };
state.activeModal = %s; state[%s] = () => { said += 1; };
window.processScan('CMD:CANCEL', 'barcode', Date.now() + 2000);
await __settle(40);
return { yes, said, modal: state.activeModal, scans: scans() };
""" % (json.dumps(modal), json.dumps(slot), json.dumps(modal), json.dumps(slot)))
    assert res["yes"] == {"said": 1, "modal": None, "notice": ""}
    assert res["said"] == 1 and res["modal"] is None and res["scans"] == []


def test_with_no_audit_a_gating_dialog_swallows_as_it_did(tmp_path):
    """The control. A pin: proved on a copy with no test of the panel."""
    res = _run(tmp_path, """
state.activeModal = 'confirm';
window.processScan('ID:57', 'barcode');
await __settle(40);
return { scans: scans(), toasts: toasts(), log: logLines(), panels: panelCount() };
""")
    assert res == {"scans": [], "toasts": [], "log": [], "panels": 0, "unhandled": []}


# --- the deck's tiles and the Location Manager ------------------------------------------

TILES = {"toggleDropMode": ("dropMode", "Drop mode waits until the audit is finished or cancelled."),
         "toggleEjectMode": ("ejectMode", "Eject mode waits until the audit is finished or cancelled.")}


@pytest.mark.parametrize("hidden", [False, True], ids=["panel-up", "panel-hidden"])
@pytest.mark.parametrize("tile", TILES)
def test_a_deck_tile_cant_arm_a_mode_during_an_audit(tmp_path, tile, hidden):
    """Only the scan was refused: armed by a press, a mode outlived the audit, and
    ejected the first spool scanned after it. RED on 8373ecd."""
    mode, words = TILES[tile]
    res = _run(tmp_path, """
await running(SESSION);
if (%s) panel().querySelector('#fcc-audit-panel-close').onclick();
%s();
await __settle(10);
return { mode: !!state[%s], toasts: timed(), notice: panelUp() ? noticeText() : null };
""" % (json.dumps(hidden), tile, json.dumps(mode)))
    assert res["mode"] is False
    assert res["toasts"] == [{"msg": words, "type": "warning", "ms": 7000}]
    assert res["notice"] == (None if hidden else words)


@pytest.mark.parametrize("tile", TILES)
def test_a_mode_armed_before_the_audit_can_still_be_turned_off(tmp_path, tile):
    """Refusing that would strand it. A pin: proved on a copy that refuses both ways."""
    mode, words = TILES[tile]
    res = _run(tmp_path, """
state[%s] = true;
await running(SESSION);
%s();
await __settle(10);
return { mode: !!state[%s], notice: noticeText() };
""" % (json.dumps(mode), tile, json.dumps(mode)))
    assert res["mode"] is False and res["notice"] == ""


@pytest.mark.parametrize("tile", TILES)
def test_with_no_audit_a_tile_arms_its_mode(tmp_path, tile):
    """The control. A pin."""
    mode, _words = TILES[tile]
    res = _run(tmp_path, """
%s();
await __settle(10);
return { mode: !!state[%s] };
""" % (tile, json.dumps(mode)))
    assert res["mode"] is True


LM = SCAN + ["inv_loc_mgr.js"]


def test_a_typed_id_in_the_location_manager_is_a_scan_of_the_audit(tmp_path, env):
    """The real answer. It posted as a manual entry and read that as "Invalid Code",
    though the audit had taken it. RED on 8373ecd."""
    answers = _audit_answers(env)
    res = _run(tmp_path, """
answerWith('/api/identify_scan', [%s]);
await running(SESSION);
panel().querySelector('#fcc-audit-panel-close').onclick();
document.getElementById('manual-spool-id').value = '57';
window.manualAddSpool();
await __settle(60);
return { posts: posts('/api/identify_scan'), toasts: toasts(), field: document.getElementById('manual-spool-id').value,
         held: state.heldSpools.map(s => s.id) };
""" % json.dumps(answers[1]), modules=LM)
    assert [(p["text"], p["source"], p.get("audit_ask")) for p in res["posts"]] == [("57", "keyboard", True)]
    assert res["toasts"] == [{"msg": answers[1]["heard"], "type": "info"}] and res["held"] == [57]
    assert res["field"] == ""


def test_with_no_audit_a_typed_id_is_looked_up_as_it_was(tmp_path):
    """The control. A pin: proved on a copy that sends every id through processScan."""
    res = _run(tmp_path, """
answerWith('/api/identify_scan', [{ type: 'spool', id: 99, display: '#99', color: '123456' }]);
document.getElementById('manual-spool-id').value = '99';
window.manualAddSpool();
await __settle(60);
return { posts: posts('/api/identify_scan'), held: state.heldSpools.map(s => s.id) };
""", modules=LM)
    assert res["posts"] == [{"text": "99", "source": "keyboard"}] and sorted(res["held"]) == [57, 99]


@pytest.mark.parametrize("hidden", [False, True], ids=["panel-up", "panel-hidden"])
def test_the_managers_pickup_is_refused_during_an_audit_and_sends_nothing(tmp_path, hidden):
    """The buffer is kept during an audit, and the pickup's ID: went to the audit as a
    scan, so a press counted as finding the spool. RED on 8373ecd."""
    res = _run(tmp_path, """
await running(SESSION);
if (%s) panel().querySelector('#fcc-audit-panel-close').onclick();
__realEjectSpool(99, 'LR-MDB-1', true);
await __settle(40);
return { scans: scans(), toasts: timed(), held: state.heldSpools.map(s => s.id), flying: !!window._pickInFlight };
""" % json.dumps(hidden), modules=LM)
    words = "The buffer is kept during an audit: finish or cancel it first."
    assert res["scans"] == [] and res["held"] == [57] and res["flying"] is False
    assert res["toasts"] == [{"msg": words, "type": "warning", "ms": 7000}]


def test_with_no_audit_the_pickup_works_as_it_did(tmp_path):
    """The control. A pin."""
    res = _run(tmp_path, """
answerWith('/api/identify_scan', [{ type: 'spool', id: 99, display: '#99', color: '123456' }]);
__realEjectSpool(99, 'LR-MDB-1', true);
await __settle(60);
return { scans: scans(), held: state.heldSpools.map(s => s.id) };
""", modules=LM)
    assert res["scans"] == ["ID:99"] and sorted(res["held"]) == [57, 99]


# --- the guard: commands the page runs itself -------------------------------------

ALWAYS = ["CMD:DROP", "CMD:EJECT", "CMD:EJECTALL", "CMD:CLEAR", "CMD:TRASH:57"]
UNDER_THE_PANEL = ["CMD:LOCATIONS", "CMD:WEIGH", "CMD:PRINT:57", "CMD:PREV", "CMD:NEXT"]
WITH_REASON = {"CMD:UNDO": "Undo Last Move is off while an audit is running",
               "CMD:BULKMOVE": "A bulk move waits until the audit is finished"}

# Nothing the command does is visible on the stub's state: what each would have run.
EFFECTS = """
({ drop: state.dropMode, eject: state.ejectMode, modal: state.activeModal, opened: __rec.opened || [],
   held: state.heldSpools.map(s => s.id), undo: __rec.fetches.filter(f => f.url === '/api/undo').length,
   bulk: __rec.fetches.filter(f => f.url === '/api/bulk_move_session').length })
"""
QUIET = {"drop": False, "eject": False, "modal": None, "opened": [], "held": [57, 99], "undo": 0, "bulk": 0}


def _command(tmp_path, text, audit=True, hidden=False):
    return _run(tmp_path, """
window.FCC_BULK_MOVE_ENABLED = true;
state.dropMode = false; state.ejectMode = false;
// A location open in the Location Manager, where CMD:EJECTALL and CMD:TRASH: act.
document.getElementById('manageModal').classList.add('show');
document.getElementById('manage-loc-id').value = 'LR-MDB-1';
state.heldSpools = [{ id: 57, display: '#57' }, { id: 99, display: '#99' }];
if (%s) await running(SESSION);
if (%s) panel().querySelector('#fcc-audit-panel-close').onclick();
window.processScan(%s, 'barcode');
await __settle(60);
return { effects: %s, notice: panelUp() ? noticeText() : null, toasts: toasts(),
         log: logLines(), scans: scans() };
""" % (json.dumps(audit), json.dumps(hidden), json.dumps(text), EFFECTS))


@pytest.mark.parametrize("hidden", [False, True], ids=["panel-up", "panel-hidden"])
@pytest.mark.parametrize("text", ALWAYS)
def test_a_command_that_would_arm_or_empty_something_is_refused_all_through_an_audit(tmp_path, text, hidden):
    """CMD:EJECT used to arm eject mode with its toast under the panel, and the
    first spool scanned after the audit was ejected. RED on 25738af."""
    res = _command(tmp_path, text, hidden=hidden)
    assert res["effects"] == QUIET, res
    assert res["scans"] == []
    assert len(res["toasts"]) == 1 and res["toasts"][0]["type"] == "warning"
    assert res["notice"] == (None if hidden else res["toasts"][0]["msg"])
    assert len(res["log"]) == 1 and text in res["log"][0]


@pytest.mark.parametrize("text", UNDER_THE_PANEL)
def test_a_command_that_opens_a_window_waits_while_the_panel_covers_it(tmp_path, text):
    res = _command(tmp_path, text)
    assert res["effects"] == QUIET, res
    assert "press Hide" in res["notice"]


@pytest.mark.parametrize("text", UNDER_THE_PANEL)
def test_with_the_panel_hidden_the_page_can_be_used(tmp_path, text):
    """Hide exists for that. The opens of these pin what was already right."""
    res = _command(tmp_path, text, hidden=True)
    assert res["toasts"] == [] and res["log"] == []
    assert res["effects"] != QUIET, res


@pytest.mark.parametrize("text, why", WITH_REASON.items())
@pytest.mark.parametrize("hidden", [False, True], ids=["panel-up", "panel-hidden"])
def test_undo_and_bulk_move_say_why_from_the_panel_too(tmp_path, text, why, hidden):
    """Both were refused by the server, with the reason in a toast under the panel."""
    res = _command(tmp_path, text, hidden=hidden)
    assert res["effects"] == QUIET, res
    assert why in res["toasts"][0]["msg"]
    if not hidden:
        assert why in res["notice"]


@pytest.mark.parametrize("text", ALWAYS + UNDER_THE_PANEL + ["CMD:UNDO", "CMD:BULKMOVE"])
def test_with_no_audit_the_commands_run_as_they_did(tmp_path, text):
    """The control: the guard is an audit's. Pins what was already right."""
    res = _command(tmp_path, text, audit=False)
    assert res["effects"] != QUIET, res
    assert not any("audit" in t["msg"].lower() for t in res["toasts"]), res


def test_a_command_with_the_audit_refused_still_reads_the_open_question_first(tmp_path):
    """The guard sits below the question's hold-off: a question on screen still
    takes CMD:CANCEL, the guard's words never reach it. Pins the order."""
    res = _run(tmp_path, """
await running(SESSION);
let cancelled = 0;
window._fccOpenMoveQuestion = { element: { isConnected: true }, title: 'A question', cancel() { cancelled += 1; } };
window.processScan('CMD:CANCEL', 'barcode');
window.processScan('CMD:EJECT', 'barcode');
await __settle(40);
return { cancelled, eject: state.ejectMode, notice: noticeText() };
""")
    assert res["cancelled"] == 1 and not res["eject"] and "behind" not in res["notice"]


# --- the notice, the note, the words ----------------------------------------------

@pytest.mark.parametrize("key, words", [
    ("second_place", "Already auditing LR-MDB-1. Finish first!"),
    ("slot_label", "That's a slot label: scan the box's own label to audit it, or a spool's label"),
    ("filament", "That's a filament label, not a spool"),
    ("not_there", "Spool #999999 not found"),
], ids=["second-place", "slot-label", "filament", "no-such-spool"])
def test_a_refused_scan_says_why_in_the_panel_beside_its_toast(tmp_path, real, key, words):
    """The real route's refusals. The toast layer is under the panel. RED on 25738af."""
    assert real[key] == {"type": "error", "msg": words}
    res = _run(tmp_path, """
answerWith('/api/identify_scan', [%s]);
await running(SESSION);
window.processScan('LOC:X', 'barcode');
await __settle(60);
return { notice: noticeText(), display: panel().querySelector('#fcc-audit-panel-notice').style.display, toasts: toasts() };
""" % json.dumps(real[key]))
    assert res["notice"] == words and res["display"] == "block"
    assert res["toasts"] == [{"msg": words, "type": "error"}]


def test_a_good_scan_clears_the_notice(tmp_path, real):
    res = _run(tmp_path, """
answerWith('/api/identify_scan', [%s, %s]);
await running(SESSION);
window.processScan('LOC:X', 'barcode');
await __settle(40);
const refused = noticeText();
window.processScan('ID:57', 'barcode');
await __settle(40);
return { refused, notice: noticeText(), display: panel().querySelector('#fcc-audit-panel-notice').style.display };
""" % (json.dumps(real["second_place"]), json.dumps(real["found"])))
    assert res["refused"] and res["notice"] == "" and res["display"] == "none"


def test_a_scan_no_answer_came_for_is_said_in_the_panel_too(tmp_path):
    res = _run(tmp_path, """
await running(SESSION);
window.fetchT = () => Promise.reject(new Error('no route to FCC'));
window.processScan('ID:57', 'barcode');
await __settle(40);
return { notice: noticeText(), toasts: toasts() };
""")
    assert "didn't answer" in res["notice"]
    assert res["toasts"] == [{"msg": "Scan Error", "type": "error"}]


def test_a_refusal_outside_an_audit_touches_no_panel(tmp_path):
    """Pins what was already right, past the new branch."""
    res = _run(tmp_path, """
answerWith('/api/identify_scan', [{ type: 'error', msg: 'Unknown Code' }]);
window.processScan('junk', 'barcode');
await __settle(40);
return { panels: panelCount(), toasts: toasts() };
""")
    assert res["panels"] == 0 and res["toasts"] == [{"msg": "Unknown Code", "type": "error"}]


def test_scan_errors_stay_up_for_7_seconds(tmp_path):
    """CLAUDE.md: blind-scanning failures mustn't slip past. No inv_core.js here: the
    driver's own showToast records the duration. RED on 25738af (the 2 s default)."""
    res = run_js(tmp_path, ["ui_builder.js", "inv_cmd.js"], """
let answer = { body: { type: 'error', msg: 'That label is no good' } };
window.__respond = () => answer;
window.processScan('junk', 'barcode');
await __settle(40);
const refused = __rec.toasts.slice();
window.fetchT = () => Promise.reject(new Error('no route to FCC'));
window.processScan('junk 2', 'barcode');
await __settle(40);
return { refused, all: __rec.toasts };
""")
    assert res["unhandled"] == []
    assert res["refused"] == [{"msg": "That label is no good", "type": "error", "duration": 7000}]
    assert res["all"][1] == {"msg": "Scan Error", "type": "error", "duration": 7000}


def test_the_note_stays_on_the_panel_and_goes_with_its_audit(tmp_path):
    """RED on 25738af: the note reached the log only."""
    res = _run(tmp_path, """
await running(SESSION);
const shown = { text: noteText(), display: panel().querySelector('#fcc-audit-panel-note').style.display };
__session = Object.assign({}, SESSION, { note: '' });
window.refreshAuditSession();
await __settle(40);
return { shown, display: panel().querySelector('#fcc-audit-panel-note').style.display };
""")
    assert res["shown"] == {"text": SESSION["note"], "display": "block"}
    assert res["display"] == "none"


def test_the_notice_and_the_note_sit_outside_the_body_a_redraw_rewrites(tmp_path):
    """RED on 25738af: neither exists. The real redraw is the isolated page's test."""
    res = _run(tmp_path, """
await running(SESSION);
return { shell: shell(), body: bodyHtml() };
""")
    shell, body = res["shell"], res["body"]
    assert 'id="fcc-audit-panel-notice" role="alert"' in shell
    assert shell.index("fcc-audit-panel-notice") < shell.index("fcc-audit-panel-body")
    assert shell.index("fcc-audit-panel-note\"") < shell.index("fcc-audit-panel-body")
    assert "fcc-audit-panel-notice" not in body and "fcc-audit-panel-note" not in body


def _text(html):
    return " ".join(re.sub(r"<[^>]+>", " ", html).split())


def test_the_panel_says_extra_and_loaded_from_here_each_with_where(tmp_path, real):
    """On the route's own session. RED on 25738af: "rogue", no where, no group."""
    res = _run(tmp_path, """
await running(SESSION);
return { body: bodyHtml(), tally: tallyHtml() };
""", session=real["session"])
    text = _text(res["body"])
    assert "Extra (found here, filed elsewhere)" in text and "Loaded from here" in text
    assert "📍 LR-MDB-2 slot 3" in text
    assert "🔗 on XL-1" in text
    # The tally sits above the body since Derek's 2026-11-03 look (PIN UPDATED DELIBERATELY).
    tally = _text(res["tally"])
    assert "1 extra" in tally and "1 loaded from here" in tally
    assert "rogue" not in text.lower() and "rogue" not in tally.lower()


def test_an_extras_tile_says_a_lost_spool_is_one(tmp_path):
    """Its `where` is the server's sentence (section 8)."""
    where = "Unknown (marked lost by the audit of LR-MDB-1 slot 2 on 2026-11-01)"
    session = dict(SESSION, rogue=[dict(SESSION["rogue"][0], location="UNKNOWN", where=where)])
    res = _run(tmp_path, "await running(SESSION); return { body: bodyHtml() };", session=session)
    assert where in _text(res["body"])


def test_a_tile_names_its_spool_once(tmp_path):
    """The server's rows start with "#57", and the tile added another. RED on
    25738af: "#57 #57 Some Brand". A bare `#id` fallback and an older row keep one."""
    session = dict(SESSION, expected=[dict(_row(57, "1"), display="Old row, no number"), dict(_row(99, "2"), display="#99")])
    res = _run(tmp_path, "await running(SESSION); return { body: bodyHtml() };", session=session)
    text = _text(res["body"])
    assert "#57 Old row, no number" in text and "#99 #99" not in text
    res = _run(tmp_path, "await running(SESSION); return { body: bodyHtml() };")
    assert "#57 Some Brand" in _text(res["body"]) and "#57 #57" not in _text(res["body"])


def test_the_panels_words(tmp_path):
    """Done asks now, and the idle line no longer says "nothing is moved either
    way" just above a button that moves spools. RED on 25738af."""
    res = _run(tmp_path, "await running(SESSION); return { body: bodyHtml(), shell: shell() };")
    text = _text(res["body"])
    assert "✅ Done…" in text and "Asks before moving anything" in text
    assert "Ends it, nothing moves" in text
    assert "then clears itself with nothing moved." in text
    assert "Auto-Park" not in text and "Nothing is moved either way" not in text
    # Hide's tooltip used to send people to a tile that cancelled the audit.
    assert "audit pill brings it back" in res["shell"]
    assert "AUDIT deck button" not in res["shell"]


def test_a_name_with_a_quote_cant_break_its_tile(tmp_path):
    session = dict(SESSION, expected=[dict(_row(57, "1"), display='#57 Brand "Red" <b>')])
    res = _run(tmp_path, "await running(SESSION); return { body: bodyHtml() };", session=session)
    assert 'title="#57 Brand &quot;Red&quot; &lt;b&gt;"' in res["body"]


def test_with_no_place_yet_and_with_nothing_filed_the_panel_says_which(tmp_path):
    none_yet = dict(SESSION, location_id=None, expected=[], rogue=[], trail=[], note="",
                    stats={"total_expected": 0, "found": 0, "missing": 0, "rogue": 0, "trail": 0})
    res = _run(tmp_path, "await running(SESSION); return { body: bodyHtml() };", session=none_yet)
    assert "Scan a location's label to start." in _text(res["body"])
    res = _run(tmp_path, "await running(SESSION); return { body: bodyHtml() };",
               session=dict(none_yet, location_id="CR-CT-2"))
    assert "Nothing is filed here." in _text(res["body"])
    # A note says so itself, with where the spools are.
    res = _run(tmp_path, "await running(SESSION); return { body: bodyHtml() };",
               session=dict(none_yet, location_id="CR-CT-2", note="Nothing is filed here itself. 8 more are inside it."))
    assert "Nothing is filed here" not in _text(res["body"])


# --- the pill ---------------------------------------------------------------------

def test_the_pill_shows_for_as_long_as_an_audit_runs_and_names_the_place(tmp_path, real):
    """RED on 25738af: after Hide nothing on screen said an audit was taking every
    scan, or where to find it."""
    res = _run(tmp_path, """
await running(Object.assign({}, SESSION, { location_id: null }));
const start = pillText();
__session = SESSION;
window.refreshAuditSession();
await __settle(40);
const place = pillText();
panel().querySelector('#fcc-audit-panel-close').onclick();
const hidden = pill().style.display;
answerWith('/api/identify_scan', [%s]);
window.processScan('CMD:CANCEL', 'barcode');
await __settle(60);
return { start, place, hidden, ended: pill().style.display };
""" % json.dumps(real["cancel"]))
    assert res["start"] == "audit: scan a location" and res["place"] == "audit: LR-MDB-1"
    assert res["hidden"] == "inline-flex" and res["ended"] == "none"


def test_a_hidden_audit_still_names_a_new_place_on_the_pill_at_once(tmp_path, real):
    res = _run(tmp_path, """
answerWith('/api/identify_scan', [%s]);
await running(Object.assign({}, SESSION, { location_id: null }));
panel().querySelector('#fcc-audit-panel-close').onclick();
__session = SESSION;
window.processScan('LOC:LR-MDB-1', 'barcode');
await __settle(60);
return { pill: pillText(), up: panelUp() };
""" % json.dumps(real["place"]))
    assert res == {"pill": "audit: LR-MDB-1", "up": False, "unhandled": []}
