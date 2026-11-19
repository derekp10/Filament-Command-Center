"""Group 63 review, round 2: the page half of its findings, hermetic.

The refill question (window.askRefillPlace, inv_details.js), Force Location's list
(window.promptEditLocation and window.fccForceMove) and the weigh screens
(inv_weigh_out.js, weight_entry.js, weight_utils.js). Round 2 found:
  - red: Pick a place… onto a shelf, a room or a single-slot box told its caller
    '' (Unassigned), so the wizard's next Save force-unassigned the spool it had
    just placed (round 1's K01 / K02 fix held only for the picker path);
  - a scanner's double read of a closed question's Cancel QR, or of a bare
    CMD:CANCEL, cancelled the next refill question in the line, unread;
  - Force Location drawn inside a window that closed while its place list was
    read: out of sight, taking every Escape, and the line of weigh questions
    waiting on it for good; and drawn inside a window that closes under it, left
    there;
  - a refill move that failed freed the line at once, and the next question
    mounted over its 7 s toast (the spool, its note used up, never asked about
    again);
  - typing in Force Location's search, drawn inside the wizard, marked the wizard
    changed;
  - the missing-tare question refused an empty spool's own reading (the one
    figure an empty spool on the scale has) as its empty weight;
  - a save refused as "changed since" lost its keyboard back when the list was
    redrawn while the save was out;
  - a spool whose own total is 0 g previewed "Invalid input", and one learned
    from a refusal said "Could not compute used weight";
  - over the search panel, Pick a place… drew the list on the page body, under
    the panel's focus trap; a Quick-Weigh over a spool window handed the
    question no window;
  - a take-off FCC couldn't write down still said "keeps trying";
  - one double click (or two Escapes) answered two refill questions in line.

Node tests run on test_core1_return_ejectall_js.run_js; browser tests on
test_weigh_out_scan_focus_js's `wo` harness, test_missing_tare_and_grams_63_7_9_js's
`entry` (the Quick-Weigh) and test_wizard_extras_touched's `wizard` (isolated
pages, no network). A test of the search panel's real focus trap needs Bootstrap
from its CDN, which an isolated page can't reach: the node pin checks that the
list closes the panel before it is drawn, as moveSpoolFromCard does. Every test
is RED on 0f3162c (the group's head before round 2's fixes) unless its docstring
says control.
"""
from __future__ import annotations

import json

import pytest

from test_core1_return_ejectall_js import NODE, NODE_MISSING_MSG, run_js
from test_head_load_confirm_js import PRELUDE as HEAD_PRELUDE
from test_missing_tare_and_grams_63_7_9_js import PROMPT_ID, entry  # noqa: F401
from test_missing_tare_and_grams_63_7_9_js import _prompt_up
from test_missing_tare_and_grams_63_7_9_js import _saved as _entry_saved
from test_quick_weigh_scan_js import later, press
from test_refill_question_63_1_js import PRELUDE as BASE_PRELUDE
from test_refill_question_review_63_js import ANSWERS
from test_refill_question_review_63_js import PRELUDE as REVIEW_PRELUDE
from test_weigh_archive_unassign_js import _save as _save_77
from test_weigh_archive_unassign_js import _toasts as _toasts_77
from test_weigh_out_scan_focus_js import _saved, _toasts, _updates, wo  # noqa: F401
from test_wizard_extras_touched import wizard  # noqa: F401
from test_wizard_location_save_js import WIZARD

needs_node = pytest.mark.skipif(NODE is None, reason=NODE_MISSING_MSG)

ASK = {"place": "XL-3", "room": "LR", "held_by": []}

# The base prelude with its promptEditLocation stub left out: the real one runs,
# and with it the real fccForceMove.
_STUB = "window.promptEditLocation = (sid, loc, o) => opened.push({ sid, loc, fromCard: !!(o && o.fromCard) });"
assert _STUB in BASE_PRELUDE
REAL = BASE_PRELUDE.replace(_STUB, "") + r"""
window.takeIntoBuffer = window.takeIntoBuffer || (() => []);
window.addEventListener = window.addEventListener || (() => {});
window.removeEventListener = window.removeEventListener || (() => {});
const refills = () => __rec.overlays.filter((o) => o.id === 'fcc-refill-place');
"""

LOCS = [
    {"LocationID": "SHELF-1", "Name": "Shelf one", "Type": "Shelf"},
    {"LocationID": "PM-DB-1", "Name": "Single dryer", "Type": "Dryer Box", "Max Spools": "1"},
    {"LocationID": "LR", "Name": "Living room", "Type": "Room"},
    {"LocationID": "Garage-Box", "Name": "Garage", "Type": "Dryer Box", "Max Spools": "4"},
]

PICKERS = r"""
window.isMultiSlotBox = (row) => !!row && row.Type === 'Dryer Box' && Number(row['Max Spools']) > 1;
window.isPrinterRowNotHead = () => false;
window.openSlotPicker = () => {};
window.placeOneWithPicker = (o) => new Promise((resolve) => {
    o.send({ location: o.loc, picked_slot: '2', label: `${o.loc} slot 2` }, resolve);
});
"""


def _real(tmp_path, body, modules=("inv_details.js",)):
    res = run_js(tmp_path, list(modules), REAL + body)
    assert res["unhandled"] == [], res
    return res


# ---- Pick a place… tells its caller where the spool went (red) ------------------------------------------

@needs_node
@pytest.mark.parametrize("pick", ["SHELF-1", "PM-DB-1", "LR", "Garage-Box"],
                         ids=["shelf", "single-slot-box", "room", "control-multi-slot-box"])
def test_pick_a_place_tells_the_caller_where_it_put_the_spool(tmp_path, pick):
    """The real Force Location list and move: a pick that opens no picker (a shelf,
    a single-slot box, a room) is heard as that place. RED on 0f3162c: heard ''
    (Unassigned). Control: a multi-slot box's picker was heard right before."""
    res = _real(tmp_path, PICKERS + f"""
const PICK = {json.dumps(pick)};
window.__respond = (url) => {{
    if (url === '/api/locations') return {{ body: {json.dumps(LOCS)} }};
    if (url === '/api/manage_contents') return {{ body: {{ status: 'success' }} }};
    return {{ body: {{}} }};
}};
window.Swal = {{ fire: () => Promise.resolve({{ isConfirmed: true, value: PICK }}), getPopup: () => null,
                 isVisible: () => false, close() {{}} }};
const host = document.getElementById('wizardModal');
host.classList.add('show');
const heard = [];
await window.askRefillPlace(57, {json.dumps(ASK)}, {{ host, onMoved: (where) => heard.push(where) }});
__overlayEls[0].querySelector('#fcc-refill-pick').onclick({{ type: 'click', detail: 1 }});
await __settle(150);
return {{ heard, moved: posts().map((p) => p[1].location) }};
""")
    assert res["moved"] == [pick], res
    assert res["heard"] == [pick], res


WIZ_LOCS = [{"LocationID": "SHELF-1", "Name": "Shelf one", "Type": "Shelf"}]


@needs_node
def test_after_pick_a_place_the_wizards_next_save_keeps_the_spool_there(tmp_path):
    """The red finding end to end: Edit Spool weighs #57 back after it left XL-1;
    the refill question's Pick a place… puts it on SHELF-1; the Location field
    says SHELF-1, and the next Save sends SHELF-1 (it moves nothing). RED on
    0f3162c: the field said Unassigned, and the next Save sent '', which the server
    turns into a force-unassign of the spool just placed."""
    first = {"success": True, "spool_id": 57, "archived_now": False, "location_now": "",
             "location_where": "Unassigned", "refill_ask": {"place": "XL-1", "room": "LR", "held_by": []}}
    second = {"success": True, "spool_id": 57, "archived_now": False}
    res = run_js(tmp_path, ["inv_core.js", "weight_utils.js", "inv_details.js", "inv_wizard.js"],
                 HEAD_PRELUDE + WIZARD + f"""
window.addEventListener = window.addEventListener || (() => {{}});
window.removeEventListener = window.removeEventListener || (() => {{}});
document.getElementById('wizardModal').classList.add('show');
window.Swal = {{ fire: () => Promise.resolve({{ isConfirmed: true, value: 'SHELF-1' }}), getPopup: () => null,
                 isVisible: () => false, close() {{}} }};
editing(57, 'XL-1');
answerFor({{ '/api/edit_spool_wizard': [{json.dumps(first)}, {json.dumps(second)}],
            '/api/locations': [{json.dumps(WIZ_LOCS)}, {json.dumps(WIZ_LOCS)}],
            '/api/manage_contents': [{{ status: 'success' }}] }});
await window.wizardSubmit();
await __settle(200);
const qs = __mounts.filter((m) => m.opts.id === 'fcc-refill-place');
qs[qs.length - 1].el.querySelector('#fcc-refill-pick').onclick({{ type: 'click', detail: 1 }});
await __settle(200);
const shown = document.getElementById('wiz-spool-location').value;
await window.wizardSubmit();
await __settle(150);
return {{ qs: qs.length, field: shown, saves: posts('/api/edit_spool_wizard').map((b) => b.spool_data.location),
          moves: posts('/api/manage_contents').map((b) => b.location) }};
""")
    assert res["unhandled"] == [], res["unhandled"]
    assert res["qs"] == 1 and res["moves"] == ["SHELF-1"], res
    assert res["field"] == "SHELF-1", res
    assert res["saves"] == ["XL-1", "SHELF-1"], res


# ---- Force Location and its window ----------------------------------------------------------------------

@needs_node
def test_force_location_is_never_drawn_inside_a_window_closed_during_its_read(tmp_path):
    """The weigh-out window closes while Force Location reads its place list: the
    list is drawn on the page body, where it can be seen and answered, and once it
    is closed the next refill question opens. RED on 0f3162c: it was drawn inside
    the closed window, out of sight, and #58's question waited behind it for good."""
    res = _real(tmp_path, f"""
const host = document.getElementById('weighOutModal');
host.classList.add('show');
const fired = [];
let closeList = null;
window.Swal = {{ fire: (o) => {{ fired.push(o.target === document.body ? 'body' : (o.target && o.target.id));
                                 return new Promise((r) => {{ closeList = r; }}); }},
                 getPopup: () => null, isVisible: () => false, close() {{}} }};
window.__respond = (url) => {{
    if (url === '/api/locations') {{ host.classList.remove('show'); return {{ body: [] }}; }}
    return {{ body: {{ status: 'success' }} }};
}};
await window.askRefillPlace(57, {json.dumps(ASK)}, {{ host }});
__overlayEls[0].querySelector('#fcc-refill-pick').onclick({{ type: 'click', detail: 1 }});
await __settle(60);
host.classList.add('show');
window.askRefillPlace(58, {json.dumps(ASK)}, {{ host }});
await __settle(60);
const before = refills().length;
if (closeList) closeList({{ isConfirmed: false }});
await __settle(60);
return {{ fired, before, after: refills().map((o) => /#(\\d+) is back in stock/.exec(o.content)[1]) }};
""")
    assert res["fired"] == ["body"], res
    assert res["before"] == 1 and res["after"] == ["57", "58"], res


@needs_node
def test_force_location_drawn_inside_a_window_closes_with_it(tmp_path):
    """Drawn inside the wizard, the list closes when the wizard does, heard as a
    Cancel, and its listener goes with it. RED on 0f3162c: it stayed up inside the
    closed window, and nothing heard it end."""
    res = _real(tmp_path, r"""
const host = document.getElementById('wizardModal');
host.classList.add('show');
const hl = {};
host.addEventListener = (t, fn) => { (hl[t] = hl[t] || []).push(fn); };
host.removeEventListener = (t, fn) => { hl[t] = (hl[t] || []).filter((f) => f !== fn); };
const popup = document.createElement('div');
let o = null, resolveList = null;
const closes = [];
window.Swal = {
    fire: (opts) => { o = opts; const p = new Promise((r) => { resolveList = r; }); if (o.didOpen) o.didOpen(); return p; },
    getPopup: () => popup,
    isVisible: () => !!resolveList,
    close: () => { closes.push(1); if (o && o.willClose) o.willClose(); const r = resolveList; resolveList = null;
                   if (r) r({ isConfirmed: false, isDismissed: true }); },
};
window.__respond = (url) => (url === '/api/locations' ? { body: [] } : { body: {} });
const settled = [];
window.promptEditLocation(57, '', { fromCard: true, host, onSettled: (x) => settled.push(x) });
await __settle(60);
const listening = (hl['hidden.bs.modal'] || []).length;
(hl['hidden.bs.modal'] || []).slice().forEach((fn) => fn());
await __settle(60);
return { listening, closes: closes.length, settled, left: (hl['hidden.bs.modal'] || []).length };
""")
    assert res["listening"] == 1, res
    assert res["closes"] == 1 and res["settled"] == ["cancelled"] and res["left"] == 0, res


SEARCH_PANEL = r"""
const order = [];
window.bootstrap.Offcanvas = { getOrCreateInstance: (p) => ({ hide: () => order.push('hide') }) };
window.Swal = { fire: (o) => { order.push('fire:' + (o.target === document.body ? 'body' : (o.target && o.target.id)));
                               return Promise.resolve({ isConfirmed: false }); },
                getPopup: () => null, isVisible: () => false, close() {} };
window.__respond = (url) => (url === '/api/locations' ? { body: [] } : { body: {} });
"""


@needs_node
def test_over_the_search_panel_the_list_closes_the_panel_first(tmp_path):
    """A Quick-Weigh from a search card has no window to draw in: the list closes
    the search panel before it is drawn on the page body, as moveSpoolFromCard
    does, so the panel's focus trap can't take the list's keyboard. RED on
    0f3162c: drawn on the body with the panel left open."""
    res = _real(tmp_path, SEARCH_PANEL + r"""
window.promptEditLocation(57, '', { fromCard: true, host: null });
await __settle(60);
return { order };
""")
    assert res["order"] == ["hide", "fire:body"], res


@needs_node
def test_control_inside_a_window_the_list_leaves_the_search_panel_alone(tmp_path):
    res = _real(tmp_path, SEARCH_PANEL + r"""
const host = document.getElementById('wizardModal');
host.classList.add('show');
window.promptEditLocation(57, '', { fromCard: true, host });
await __settle(60);
return { order };
""")
    assert res["order"] == ["fire:wizardModal"], res


@needs_node
def test_a_quick_weigh_over_a_spool_window_hands_the_question_that_window(tmp_path):
    """The Quick-Weigh's save, opened over a spool window (no weigh-out list): the
    refill question is asked over that window, so Pick a place… draws its list in
    it. RED on 0f3162c: no window was handed on."""
    res = run_js(tmp_path, ["inv_weigh_out.js"], r"""
window.__respond = (url) => (url === '/api/spool/update'
    ? { body: { status: 'success', auto_archived: false, needs_empty_weight_prompt: false,
                location_now: '', refill_ask: { place: 'XL-3', room: 'LR', held_by: [] } } }
    : { body: {} });
const spoolWin = document.getElementById('spoolModal');
spoolWin.classList.add('show');
document.querySelectorAll = (sel) => (sel === '.modal.show' ? [spoolWin] : []);
const asked = [];
window.askRefillPlace = (sid, ask, o) => asked.push(o && o.host ? o.host.id : null);
window.saveSpoolWeight(57, null, { used_weight: 600 }, false, null, { archiveSwitch: true, empties: false, wasArchived: true });
await __settle(600);
return { asked };
""")
    assert res["unhandled"] == [], res
    assert res["asked"] == ["spoolModal"], res


# ---- a refill move that fails asks again ------------------------------------------------------------------

@needs_node
def test_a_refill_move_that_fails_asks_again_with_its_words(tmp_path):
    """#57's Back on XL-3 is refused (another spool reached XL-3): its question opens
    again with the refusal on it, ahead of #58's, which opens once #57's is
    answered. RED on 0f3162c: #58's question mounted over the 7 s failure toast,
    and #57, Unassigned with its note used up, was never asked about again."""
    res = run_js(tmp_path, ["inv_details.js"], REVIEW_PRELUDE + f"""
// inv_core.js's, which reads the harness's fccQuestionArmMs (0): without it the question
// arms for 700 ms, and a Leave pressed this soon after the failed Back would be ignored
// as the second half of a double press (the browser tests below pin that).
window.questionArmMs = () => 0;
window.__respond = (url) => {{
    if (url === '/api/locations') return {{ body: [{{ LocationID: 'XL-3', Name: 'Head 3', Type: 'Tool Head' }}] }};
    if (url === '/api/manage_contents') return {{ body: {{ status: 'error', msg: 'XL-3 holds #99 now: #57 was not moved' }} }};
    return {{ body: {{}} }};
}};
window.askRefillPlace(57, {json.dumps(ASK)});
window.askRefillPlace(58, {json.dumps(ASK)});
await __settle(60);
__overlayEls[0].querySelector('#fcc-refill-back').onclick({{ type: 'click', detail: 1 }});
await __settle(120);
const again = refills().map((o) => o.content);
__overlayEls[1].querySelector('#fcc-refill-leave').onclick({{ type: 'click', detail: 1 }});
await __settle(60);
return {{ again, after: refills().map((o) => /#(\\d+) is back in stock/.exec(o.content)[1]),
          toasts: __rec.toasts.map((t) => t.msg) }};
""")
    assert res["unhandled"] == [], res
    assert len(res["again"]) == 2 and "#57 is back in stock" in res["again"][1], res
    assert 'id="fcc-refill-notice"' in res["again"][1], res
    assert "XL-3 holds #99 now: #57 was not moved" in res["again"][1], res
    assert res["after"] == ["57", "57", "58"], res
    assert "XL-3 holds #99 now: #57 was not moved" in res["toasts"], res


@needs_node
def test_a_throw_after_a_landed_move_asks_nothing_again(tmp_path):
    """Control (passes on 0f3162c, which asked nothing again after any move): the
    re-ask is for a move that failed, with its words. Here #57's Back landed and
    FCC's own code threw while handling the answer, so whether it moved is unknown:
    the line goes on to #58's question, and #57's isn't asked again (round 2's first
    re-ask did, about a spool that had moved)."""
    res = run_js(tmp_path, ["inv_details.js"], REVIEW_PRELUDE + f"""
window.questionArmMs = () => 0;
window.takeIntoBuffer = () => {{ throw new Error('a bug of our own'); }};
window.__respond = (url) => {{
    if (url === '/api/locations') return {{ body: [{{ LocationID: 'XL-3', Name: 'Head 3', Type: 'Tool Head' }}] }};
    if (url === '/api/manage_contents') return {{ body: {{ status: 'success' }} }};
    return {{ body: {{}} }};
}};
window.askRefillPlace(57, {json.dumps(ASK)});
window.askRefillPlace(58, {json.dumps(ASK)});
await __settle(60);
__overlayEls[0].querySelector('#fcc-refill-back').onclick({{ type: 'click', detail: 1 }});
await __settle(120);
return {{ after: refills().map((o) => /#(\\d+) is back in stock/.exec(o.content)[1]),
          moved: posts().map((p) => p[1].location) }};
""")
    assert res["moved"] == ["XL-3"], res
    assert res["after"] == ["57", "58"], res


# ---- the take-off that couldn't be written down -----------------------------------------------------------

@needs_node
def test_a_take_off_fcc_couldnt_write_down_never_says_it_keeps_trying(tmp_path):
    """The weigh to empty landed, its take-off was refused, and the disk refused the
    note to try again (`still_at_unrecorded`): the warning says what finishes it.
    RED on 0f3162c: "…and keeps trying", while nothing would ever try."""
    update = {"status": "success", "auto_archived": True, "needs_empty_weight_prompt": False,
              "filament_id": None, "location_now": "XL-1", "still_at": "XL-1", "still_at_unrecorded": True}
    toasts = _toasts_77(_save_77(tmp_path, update))
    assert ("Spool #77 is archived but still at XL-1: FCC couldn't take it off there, and couldn't note it to "
            "try again: weigh it to 0 g again to take it off.", "warning", 7000) in toasts, toasts
    assert not any("keeps trying" in t[0] for t in toasts), toasts


# ---- a cancel read twice (browser) ------------------------------------------------------------------------

TWO = r"""() => {
    window.__closedQs = [];
    window.askRefillPlace(6, { place: 'HEAD-1', room: 'LR', held_by: [] },
        { onClosed: (how) => window.__closedQs.push([6, how]) });
    window.askRefillPlace(134, { place: 'HEAD-2', room: 'LR', held_by: [] },
        { onClosed: (how) => window.__closedQs.push([134, how]) });
}"""


def _two_questions(page):
    page.evaluate(TWO)
    page.wait_for_function("() => document.activeElement && document.activeElement.id === 'fcc-refill-leave'",
                           timeout=5000)


def _question_up(page):
    return page.evaluate(r"""() => {
        const t = document.getElementById('fcc-refill-title');
        const m = t && /#(\d+)/.exec(t.textContent);
        return m ? Number(m[1]) : null;
    }""")


def _wait_question(page, sid):
    page.wait_for_function(r"""(sid) => {
        const t = document.getElementById('fcc-refill-title');
        return !!t && t.textContent.includes('#' + sid + ' ');
    }""", arg=sid, timeout=5000)


def _its_cancel_qr(page):
    return page.evaluate("""() => {
        const keys = Object.keys(window._fccActiveConfirms || {});
        const ov = document.getElementById('fcc-refill-place');
        const own = keys.find((k) => ov && ov.querySelector('#' + CSS.escape(k + '-row')));
        return 'CMD:CANCEL:' + (own || keys[keys.length - 1]);
    }""")


@pytest.mark.parametrize("form", ["its-qr", "bare"])
def test_a_cancel_read_twice_leaves_the_next_question_up(wo2, form):
    """#6's question is answered by a scan of its Leave QR (or a bare CMD:CANCEL);
    #134's opens at once; the scanner reads the same code again 150 ms later. RED on
    0f3162c: the second read cancelled #134's question, unread."""
    page, open_ = wo2
    open_(held=(6, 134))
    _two_questions(page)
    text = "CMD:CANCEL" if form == "bare" else _its_cancel_qr(page)
    page.evaluate("(t) => { window.processScan(t, 'barcode'); }", text)
    _wait_question(page, 134)
    later(page, 150)
    page.evaluate("(t) => { window.processScan(t, 'barcode'); }", text)
    page.wait_for_timeout(150)
    assert _question_up(page) == 134, page.evaluate("() => window.__closedQs")
    assert page.evaluate("() => window.__closedQs") == [[6, "leave"]]


def test_control_a_bare_cancel_read_later_answers_the_next_question(wo2):
    """Control: a CMD:CANCEL read 1.6 s after the one that answered #6's question is
    a person's next scan, and answers #134's."""
    page, open_ = wo2
    open_(held=(6, 134))
    _two_questions(page)
    page.evaluate("() => { window.processScan('CMD:CANCEL', 'barcode'); }")
    _wait_question(page, 134)
    later(page, 1600)
    page.evaluate("() => { window.processScan('CMD:CANCEL', 'barcode'); }")
    page.wait_for_function("() => !document.getElementById('fcc-refill-place')", timeout=5000)
    assert page.evaluate("() => window.__closedQs") == [[6, "leave"], [134, "leave"]]


# ---- one double press answers one question (browser, a real mouse) -----------------------------------------

@pytest.fixture
def wo2(wo):
    page, open_ = wo
    page.evaluate(ANSWERS)
    return page, open_


@pytest.mark.parametrize("size", [(1600, 1300), (1280, 720), (390, 844)], ids=["desktop", "laptop", "phone"])
@pytest.mark.parametrize("how", ["double-click", "double-escape"])
def test_one_double_press_answers_one_question(wo2, size, how):
    """Two refill questions in line, the arming on (as on the page). A double click
    on #6's Leave it Unassigned, or two Escapes at once, answers #6's question
    only: #134's opens under the pointer and the keyboard, and stays up. RED on
    0f3162c: the second press answered #134's question unread."""
    page, open_ = wo2
    page.set_viewport_size({"width": size[0], "height": size[1]})
    open_(held=(6, 134))
    page.evaluate("() => { delete window.fccQuestionArmMs; }")
    _two_questions(page)
    later(page, 900)
    if how == "double-click":
        b = page.locator("#fcc-refill-leave").bounding_box()
        page.mouse.dblclick(b["x"] + b["width"] / 2, b["y"] + b["height"] / 2)
    else:
        page.keyboard.press("Escape")
        page.keyboard.press("Escape")
    page.wait_for_timeout(200)
    assert page.evaluate("() => window.__closedQs") == [[6, "leave"]]
    assert _question_up(page) == 134


def test_control_an_escape_a_moment_later_answers_the_next_question(wo2):
    page, open_ = wo2
    open_(held=(6, 134))
    page.evaluate("() => { delete window.fccQuestionArmMs; }")
    _two_questions(page)
    later(page, 900)
    page.keyboard.press("Escape")
    _wait_question(page, 134)
    later(page, 800)
    page.keyboard.press("Escape")
    page.wait_for_function("() => !document.getElementById('fcc-refill-place')", timeout=5000)
    assert page.evaluate("() => window.__closedQs") == [[6, "leave"], [134, "leave"]]


# ---- the wizard isn't changed by a dialog drawn inside it (browser) ----------------------------------------

DIALOG_IN_WIZARD = """() => {
    wizardState.isDirty = false;
    const c = document.createElement('div');
    c.className = 'swal2-container';
    c.innerHTML = '<input id="swal-override-search" type="text">';
    document.getElementById('wizardModal').appendChild(c);
    document.getElementById('swal-override-search').focus();
}"""

HIDE = """() => { const e = new Event('hide.bs.modal', { cancelable: true });
    document.getElementById('wizardModal').dispatchEvent(e); return e.defaultPrevented; }"""


def test_typing_in_a_dialog_drawn_inside_the_wizard_changes_nothing_in_it(wizard):
    """Force Location's list, drawn inside the wizard: a filter typed in its search
    is no edit of the wizard, so closing the wizard asks nothing. RED on 0f3162c:
    the wizard read it as a change, and its close asked about unsaved changes."""
    page = wizard
    page.evaluate(DIALOG_IN_WIZARD)
    page.keyboard.type("shel")
    assert page.evaluate("() => document.getElementById('swal-override-search').value") == "shel"
    assert page.evaluate("() => wizardState.isDirty") is False
    assert page.evaluate(HIDE) is False
    assert page.locator("#fcc-wiz-unsaved-changes").count() == 0


def test_control_typing_in_the_wizards_own_box_is_a_change(wizard):
    page = wizard
    page.evaluate("() => { wizardState.isDirty = false; document.getElementById('wiz_fil_ef_drying_temp').focus(); }")
    page.keyboard.type("5")
    assert page.evaluate("() => wizardState.isDirty") is True
    assert page.evaluate(HIDE) is True


# ---- an empty spool's own reading is its empty weight (browser) --------------------------------------------

@pytest.mark.parametrize("typed", ["245", "250"], ids=["its-own-reading", "the-makers-figure-a-little-above"])
def test_the_quick_weigh_takes_an_empty_spools_own_reading_as_its_empty_weight(entry, typed):
    """An empty spool (980 of its 1000 g used) on the scale in Gross, with no empty
    weight known: its own reading, or the maker's figure a little above it, is its
    empty weight. RED on 0f3162c: refused as "An empty spool weighs less than the
    245 g on the scale", so an empty spool couldn't be weighed empty."""
    page, open_ = entry
    open_("gross", initial=1000, used=980)
    press(page, "245", 150)
    _prompt_up(page)
    press(page, typed, 150)
    page.wait_for_function("() => window.__saved.length === 1", timeout=5000)
    assert _entry_saved(page) == [{"mode": "gross", "value": 245, "tare": int(typed), "typed": int(typed)}]


def test_a_figure_far_above_the_reading_is_refused_in_words(entry):
    """A figure typed onto the end of another (250245) is still refused, in words
    that say why. RED on 0f3162c: its words were the old rule's."""
    page, open_ = entry
    open_("gross", initial=1000, used=980)
    press(page, "245", 150)
    _prompt_up(page)
    press(page, "250245", 150)
    page.wait_for_timeout(50)
    err = page.evaluate(f"() => document.getElementById('{PROMPT_ID}-err').textContent")
    assert err == "250245 g can't be its empty weight: the spool on the scale weighs 245 g. Check the number.", err
    assert page.evaluate("() => window.__saved.length") == 0


def test_the_weigh_out_list_takes_an_empty_spools_own_reading_as_its_empty_weight(wo2):
    """The list's Gross row, #8 empty (990 of 1000 g used, no empty weight known):
    245 on the scale, 245 as its empty weight, saved as empty. RED on 0f3162c:
    refused, and the list's question has no Skip."""
    page, open_ = wo2
    page.evaluate("() => { window.__spools[8].used_weight = 990; }")
    open_(held=(8,), mode="gross")
    press(page, "245", 150)
    page.wait_for_function("() => document.activeElement && document.activeElement.id"
                           " === 'fcc-missing-empty-weight-overlay-input'", timeout=5000)
    later(page, 700)
    press(page, "245", 150)
    _saved(page)
    ups = _updates(page)
    assert [u["id"] for u in ups] == [8], ups
    assert ups[0]["updates"]["used_weight"] == 1000 and ups[0]["updates"]["spool_weight"] == 245, ups


# ---- the list's keyboard and words (browser) ---------------------------------------------------------------

HOLD_6_REFUSED = r"""() => {
    const base = window.fetch;
    window.fetch = function (url, opts) {
        url = String(url);
        if (url.includes('/api/spool/update')) {
            const body = JSON.parse(opts.body);
            if (body.id === 6 && !window.__refused6) {
                window.__refused6 = true;
                window.__posts.push({ url, body });
                return new Promise((resolve) => {
                    window.__answer6 = () => resolve({ ok: true, status: 200, json: () => Promise.resolve({
                        status: 'details_changed', changed: 'capacity',
                        fresh: { initial: 1200, used: 31, archived: false },
                        msg: "#6's weight changed since this was read: check its preview and press Enter in its box again" }) });
                });
            }
        }
        return base(url, opts);
    };
}"""


def test_a_refused_save_gets_the_keyboard_back_after_the_list_was_redrawn(wo):
    """#6's save is out, the keyboard has moved on to #134's box, and the list is
    drawn again (a buffer update) before the refusal comes: #6's box takes the
    keyboard back, its reading selected. RED on 0f3162c: the redraw replaced the
    box the keyboard was on, the check read that as the person moving on, and the
    Enter the toast asks for landed in #134's box."""
    page, open_ = wo
    page.evaluate(HOLD_6_REFUSED)
    open_(held=(6, 134))
    press(page, "300", 150)
    page.wait_for_function("() => typeof window.__answer6 === 'function'", timeout=5000)
    page.wait_for_function("() => document.activeElement && document.activeElement.dataset"
                           " && document.activeElement.dataset.id === '134'", timeout=5000)
    page.evaluate("() => document.dispatchEvent(new CustomEvent('inventory:buffer-updated'))")
    page.wait_for_timeout(100)
    page.evaluate("() => window.__answer6()")
    page.wait_for_function("() => document.activeElement && document.activeElement.dataset"
                           " && document.activeElement.dataset.id === '6'", timeout=5000)
    assert page.evaluate("() => { const b = document.activeElement; return b.value === '300'"
                         " && b.selectionStart === 0 && b.selectionEnd === 3; }")


def _preview(page, sid):
    return page.evaluate("(id) => (document.querySelector(`.weigh-row-preview[data-id=\"${id}\"]`) || {}).textContent"
                         " || ''", str(sid))


def test_a_spool_whose_own_total_is_0_g_says_so_in_its_preview(wo):
    """#57's own total is 0 g in Spoolman: its preview says so under a reading. RED on
    0f3162c: "Invalid input" under a valid reading."""
    page, open_ = wo
    page.evaluate("() => { window.__spools[57].initial_weight = 0; }")
    open_(held=(57,))
    press(page, "450", 150, enter=False)
    page.wait_for_timeout(50)
    assert _preview(page, 57).strip() == "Its total is 0 g: set it in Edit Spool first", _preview(page, 57)


def test_a_total_of_0_g_learned_from_a_refusal_says_so_at_enter(wo2):
    """#6's save is refused: its total is 0 g now. Its preview says so, and the next
    Enter says what to do, posting nothing. RED on 0f3162c: "Could not compute used
    weight"."""
    page, open_ = wo2
    page.evaluate("() => { window.__changedOnce[6] = { initial: 0, used: 31, archived: false }; }")
    open_(held=(6, 134))
    press(page, "300", 150)
    _saved(page)
    page.wait_for_function("() => document.activeElement && document.activeElement.dataset"
                           " && document.activeElement.dataset.id === '6'", timeout=5000)
    assert _preview(page, 6).strip() == "Its total is 0 g: set it in Edit Spool first", _preview(page, 6)
    later(page, 700)
    press(page, "", 0)
    page.wait_for_timeout(100)
    toasts = _toasts(page)
    assert any("#6's total weight is 0 g in Spoolman: set its total in Edit Spool first, then weigh it" in t
               for t in toasts), toasts
    assert not any("Could not compute used weight" in t for t in toasts), toasts
    assert len(_updates(page)) == 1
