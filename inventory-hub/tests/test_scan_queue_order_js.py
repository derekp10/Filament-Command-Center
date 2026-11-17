"""Scans read while FCC is busy go out in the order they were read (Group 57
review, round 11), hermetic.

Runs the REAL scan accumulator (scripts.html's keydown block, lifted as the
other scan tests lift it) with processScan stubbed to record each scan and,
as the real one does for a scan the server answers, turn `state.processing`
on until the test answers it. The queue's 250 ms poll runs on a clock the test
moves by hand, so the order the old code gave is the same on every run.

Pinned: two scans queued behind a slow answer go out in the order they were
read, whichever poll would tick first (RED before round 11: each queued scan
had its own poll, so a slot label scanned 200 ms after a spool went out first,
and the server filed the spool scanned before them into the slot); a scan read
once the slow answer came, before the queue's poll ticked, waits behind the
scans read before it (RED before: it went out at once, ahead of them); the
focus guard holds scans the same way; a queued scan that throws doesn't hold
up the ones after it; a queued scan answered without going out ends its
weigh-out read; a scan read with nothing busy and nothing queued goes out at
once, with no poll, as before.

Group 58 review: a queued scan is stamped with the audit it was read for, as it
is read, in both pushes; a scan that audit has outlived (window.auditScanOutlived,
inv_cmd.js) never goes out, and still ends its weigh-out read; the stamp goes out
with a scan that does; and window.auditQueueMoved hears of every queued scan, sent
or not. Each passes with neither hook defined: the block is lifted as it is here.
The hooks themselves are in test_audit_page_58_js.py, on the real routes in
test_audit_no_label_58_js.py.
"""
from __future__ import annotations

import pytest

from test_slow_scan_slash_js import TYPE_JS, _accumulator

PAGE = """<!doctype html><html><head><meta charset="utf-8"></head><body>
<div id="focus-guard" style="display:none"></div>
</body></html>"""

PRELUDE = r"""
window.state = { scanBuffer: '', scanStartTime: 0, processing: false };
window.__sent = [];
window.__throwOn = null;
window.__instant = false;
// processScan, as the real one behaves for a scan the server answers: busy at
// once, until the test answers it (window.__answer()). __instant: answered
// without going out (a dialog's own QR, a second read dropped).
window.__stamps = [];
window.processScan = function (text, source, capturedAt, weighRead, auditOf) {
    window.__sent.push(text);
    window.__stamps.push(auditOf);
    if (window.__throwOn === text) throw new Error('boom');
    if (!window.__instant) state.processing = true;
};
window.__answer = function () { state.processing = false; };
// The queue's poll on a timeline the test moves (window.__advance(ms)).
window.__vt = 0;
window.__ivs = [];
window.setInterval = function (fn, ms) {
    const iv = { fn: fn, ms: ms, next: window.__vt + ms, id: window.__ivs.length + 1, live: true };
    window.__ivs.push(iv);
    return iv.id;
};
window.clearInterval = function (id) {
    const iv = window.__ivs.find((i) => i.id === id);
    if (iv) iv.live = false;
};
window.__advance = function (ms) {
    const to = window.__vt + ms;
    for (;;) {
        const due = window.__ivs.filter((i) => i.live && i.next <= to)
            .sort((a, b) => a.next - b.next || a.id - b.id)[0];
        if (!due) break;
        window.__vt = due.next;
        due.next += due.ms;
        try { due.fn(); } catch (e) { /* a poll's own error, as a timer's would be */ }
    }
    window.__vt = to;
};
"""


@pytest.fixture
def q(isolated_page):
    page = isolated_page
    page.set_content(PAGE)
    page.add_script_tag(content=PRELUDE)
    page.add_script_tag(content=_accumulator())
    page.evaluate(TYPE_JS, ["", 0, False, {}])           # the keys' fake clock
    return page


def _scan(page, text):
    """A scanner: 5 ms a key, then Enter."""
    page.evaluate(TYPE_JS, [text, 5, True, {}])


def _advance(page, ms):
    page.evaluate("(ms) => window.__advance(ms)", ms)


def _sent(page):
    return page.evaluate("() => window.__sent.slice()")


def _answer(page):
    page.evaluate("() => window.__answer()")


def test_scans_queued_behind_a_slow_answer_go_out_in_the_order_they_were_read(q):
    """A spool, then its slot label 200 ms later, both inside one slow answer.
    The old code gave each its own poll: the label's ticked first after the
    answer came (at 450 ms against the spool's 500), so the server filed the
    spool already in the buffer into the slot. RED before round 11."""
    _scan(q, "LOC:FIRST")                         # goes out; its answer is slow
    assert _sent(q) == ["LOC:FIRST"]
    _scan(q, "ID:57")                             # queued at 0 ms
    _advance(q, 200)
    _scan(q, "LOC:CR-MDB-1:SLOT:2")               # queued at 200 ms
    _advance(q, 100)
    _answer(q)                                    # 300 ms: the slow answer comes
    _advance(q, 400)
    assert _sent(q) == ["LOC:FIRST", "ID:57"], "the spool goes first, and the label waits for its answer"
    _answer(q)
    _advance(q, 300)
    assert _sent(q) == ["LOC:FIRST", "ID:57", "LOC:CR-MDB-1:SLOT:2"]
    assert q.evaluate("() => window.__ivs.filter((i) => i.live).length") == 0, "the poll stops once the queue is empty"


def test_a_scan_read_before_the_queue_went_out_waits_behind_it(q):
    """The slow answer came, and the queue's poll hasn't ticked yet: a label
    read now is not ahead of the spool still waiting. RED before round 11 (it
    went out at once, as nothing was busy)."""
    _scan(q, "LOC:FIRST")
    _scan(q, "ID:57")                             # queued
    _answer(q)                                    # the poll hasn't ticked
    _scan(q, "LOC:CR-MDB-1:SLOT:2")
    assert _sent(q) == ["LOC:FIRST", "ID:57"], "the waiting spool goes first"
    _answer(q)
    _advance(q, 250)
    assert _sent(q) == ["LOC:FIRST", "ID:57", "LOC:CR-MDB-1:SLOT:2"]


def test_the_focus_guard_holds_scans_in_their_order_too(q):
    q.evaluate("() => { window.__instant = true; document.getElementById('focus-guard').style.display = 'flex'; }")
    for text in ("ID:6", "ID:57", "LOC:CR-MDB-1:SLOT:2"):
        _scan(q, text)
        _advance(q, 120)
    assert _sent(q) == []
    q.evaluate("() => { document.getElementById('focus-guard').style.display = 'none'; }")
    _advance(q, 250)
    assert _sent(q) == ["ID:6", "ID:57", "LOC:CR-MDB-1:SLOT:2"]


def test_a_queued_scan_that_throws_does_not_hold_up_the_ones_after_it(q):
    q.evaluate("() => { window.__instant = true; window.__throwOn = 'BAD'; state.processing = true; }")
    _scan(q, "BAD")
    _scan(q, "ID:57")
    q.evaluate("() => { state.processing = false; }")
    _advance(q, 250)
    assert _sent(q) == ["BAD", "ID:57"]


def test_a_queued_scan_answered_without_going_out_ends_its_weigh_out_read(q):
    """The weigh-out list hears of a queued scan as it is read (round 9); one
    answered without going out (a dialog's own QR) ends that read."""
    q.evaluate("""() => { window.__reads = []; window.__done = [];
        window.weighOutScanStart = () => { const r = { sent: false, i: window.__reads.length };
            window.__reads.push(r); return r; };
        window.weighOutScanDone = (r) => window.__done.push(r.i);
        state.processing = true; }""")
    _scan(q, "CMD:CONFIRM:abc")
    assert q.evaluate("() => window.__reads.length") == 1, "read as it is queued"
    q.evaluate("() => { window.__instant = true; state.processing = false; }")
    _advance(q, 250)
    assert _sent(q) == ["CMD:CONFIRM:abc"]
    assert q.evaluate("() => window.__done") == [0]


def test_a_scan_read_with_nothing_busy_goes_out_at_once(q):
    q.evaluate("() => { window.__instant = true; }")
    _scan(q, "ID:57")
    assert _sent(q) == ["ID:57"]
    assert q.evaluate("() => window.__ivs.length") == 0, "no poll when nothing waits"


# --- the audit a scan was read for (Group 58 review) ---------------------------------

def _believing(page, active, audit_id):
    page.evaluate("([a, i]) => { state.auditActive = a; state.auditId = i; }", [active, audit_id])


@pytest.mark.parametrize("active, audit_id, stamp", [(True, "boot-1", "boot-1"), (True, None, True), (False, None, None),
                                                     (False, "boot-1", None)],
                         ids=["known", "id-not-heard-yet", "no-audit", "no-audit-a-stale-id"])
def test_a_queued_scan_is_stamped_with_the_audit_it_was_read_for(q, active, audit_id, stamp):
    """In both pushes: the accumulator's and a press's. RED on 8373ecd: no stamp, so
    nothing could tell a scan read during an audit from one read after it."""
    _scan(q, "LOC:FIRST")                         # busy
    _believing(q, active, audit_id)
    _scan(q, "ID:57")
    q.evaluate("() => window.sendInScanOrder('CMD:DONE', 'keyboard')")
    assert q.evaluate("() => state.scanQueue.map((s) => s.auditOf)") == [stamp, stamp]


def test_the_stamp_is_taken_as_it_is_read_and_goes_out_with_it(q):
    """Not as it goes out: the audit can be over by then, or another one running. RED
    on 8373ecd."""
    _scan(q, "LOC:FIRST")
    _believing(q, True, "boot-1")
    _scan(q, "ID:57")
    _believing(q, True, "boot-2")
    _answer(q)
    _advance(q, 250)
    assert _sent(q) == ["LOC:FIRST", "ID:57"]
    assert q.evaluate("() => window.__stamps[1]") == "boot-1"


def test_a_scan_with_no_queue_goes_out_with_no_stamp_of_its_own(q):
    """processScan stamps a scan read now itself (`auditOf` left out), so the two can
    never differ. A pin: RED only on a copy that passes one here."""
    q.evaluate("() => { window.__instant = true; }")
    _believing(q, True, "boot-1")
    _scan(q, "ID:57")
    assert q.evaluate("() => window.__stamps.length") == 1
    assert q.evaluate("() => window.__stamps[0] === undefined")


def test_a_scan_its_audit_outlived_never_goes_out_and_ends_its_weigh_out_read(q):
    """RED on 8373ecd: the queue sent it. window.auditScanOutlived's own rule and its
    words are test_audit_page_58_js's."""
    q.evaluate("""() => { window.__reads = []; window.__done = []; window.__asked = [];
        window.weighOutScanStart = () => { const r = { sent: false, i: window.__reads.length };
            window.__reads.push(r); return r; };
        window.weighOutScanDone = (r) => window.__done.push(r.i);
        window.auditScanOutlived = (s) => { window.__asked.push(s.text); return s.text === 'LOC:LR-MDB-1'; };
        const send = window.processScan;
        window.processScan = (t, s, c, w, a) => { if (w) w.sent = true; send(t, s, c, w, a); };
        state.processing = true; }""")
    _scan(q, "LOC:LR-MDB-1")
    _scan(q, "ID:57")
    q.evaluate("() => { state.processing = false; }")
    _advance(q, 250)
    assert _sent(q) == ["ID:57"]
    assert q.evaluate("() => window.__asked") == ["LOC:LR-MDB-1", "ID:57"]
    assert q.evaluate("() => window.__done") == [0]         # the dropped one's, and only its


def test_the_page_hears_of_every_queued_scan_sent_or_not(q):
    """window.auditQueueMoved frees the panel's buttons for a queued Done that never
    went out: no answer will. After the scan, so it can read the queue without it. RED
    on 8373ecd."""
    q.evaluate("""() => { window.__moved = [];
        window.auditScanOutlived = (s) => s.text === 'GONE';
        window.auditQueueMoved = () => window.__moved.push(state.scanQueue.map((s) => s.text));
        window.__instant = true; state.processing = true; }""")
    for text in ("ID:57", "GONE", "ID:99"):
        _scan(q, text)
    q.evaluate("() => { state.processing = false; }")
    _advance(q, 250)
    assert q.evaluate("() => window.__moved") == [["GONE", "ID:99"], ["ID:99"], []]
    assert _sent(q) == ["ID:57", "ID:99"]


def test_a_press_in_its_turn_is_heard_of_too_when_it_throws(q):
    """The hook is in the `finally`: a scan that throws can't leave the buttons down."""
    q.evaluate("""() => { window.__moved = 0; window.auditQueueMoved = () => { window.__moved += 1; };
        window.__instant = true; window.__throwOn = 'BAD'; state.processing = true; }""")
    q.evaluate("() => window.sendInScanOrder('BAD', 'keyboard')")
    q.evaluate("() => { state.processing = false; }")
    _advance(q, 250)
    assert q.evaluate("() => window.__moved") == 1
