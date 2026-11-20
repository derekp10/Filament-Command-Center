"""Group 63 review: the refill question, the empty-weight prompt and the weigh-out
list's keyboard, the page half of the review's findings.

The refill question (window.askRefillPlace, inv_details.js) asks where a spool goes
when a weigh or an edit brings it back into stock after it left a toolhead. The
review found:
  - K07 / K14 / K19: a second question replaced the first, unanswered (its spool's
    note already used up, nobody ever asked about it), and one opened over the
    post-archive empty-weight prompt while a weight was typed in it. Now both wait
    in one line, each opening once the one before has closed (and once any move it
    started has settled);
  - K13: it opened over a scan being answered and took its spool's reading. Now it
    waits for `settle` / `scanPending` / `waitWhile`, and skips with a note when a
    spool was scanned since the save;
  - K20: a refused scan's note replaced the reason Back on <head> is greyed out;
  - K22: a scanned label (read upper case) missed its row in a list that names it in
    another case, and a place list that couldn't be read moved the spool blind;
  - K23: a spool it put back stayed in the scan buffer;
  - K02: the wizard heard the target, not where the spool landed;
  - K03 / K15: Pick a place… drew Force Location's list on the page body, under the
    open window's focus trap;
  - Derek's picture walk (2026-11-18): "needs QR codes";
  - K04 / K06: closed over the weigh-out list, it left the keyboard on the page,
    and the next reading went to the scan path as a spool id;
  - K21: its arrows were heard only on its own overlay;
  - K39: a save refused as "changed since" left the keyboard on the next row, where
    the Enter its toast asked for saved the next spool;
  - K11 / K12: the empty-weight prompt checked for typing and scans only before its
    filament read;
  - K05: the missing-tare question's offered figure wasn't selected, so a figure
    typed over it was joined to it (250245 g), and an empty weight as heavy as the
    whole spool was taken;
  - K03: a digit typed on a dialog drawn inside the weigh-out window went into a
    spool's weight box.

Node tests run on test_core1_return_ejectall_js.run_js; browser tests on
test_weigh_out_scan_focus_js's `wo` harness (an isolated page, no network). Every
test is RED on 8153b81 (the group's head before the review's fixes) unless its
docstring says control.
"""
from __future__ import annotations

import json

import pytest

from test_core1_return_ejectall_js import NODE, NODE_MISSING_MSG, run_js
from test_quick_weigh_scan_js import later, press
from test_refill_question_63_1_js import PRELUDE as BASE_PRELUDE
from test_weigh_out_scan_focus_js import _box, _focus, _saved, _scans, _updates, wo  # noqa: F401

needs_node = pytest.mark.skipif(NODE is None, reason=NODE_MISSING_MSG)

ASK = {"place": "XL-3", "room": "LR", "held_by": []}

PRELUDE = BASE_PRELUDE + r"""
// inv_core.js's, which these modules leave out: a landed move hands its buffer note on.
window.takeIntoBuffer = window.takeIntoBuffer || (() => []);
const refills = () => __rec.overlays.filter((o) => o.id === 'fcc-refill-place');
const promptsUp = () => __rec.overlays.filter((o) => o.id === 'fcc-archive-empty-overlay');
const picks = [];
window.promptEditLocation = (sid, loc, o) => picks.push({ sid, loc, host: o && o.host ? o.host.id : null });
const FILAMENT = { id: 7, name: 'Blue', material: 'PLA', spool_weight: null, vendor: { id: 3, name: 'Brand' } };
window.__respond = (url) => {
    if (url === '/api/manage_contents') return { body: { status: 'success' } };
    if (url === '/api/locations') return { body: [] };
    if (/filament_details/.test(url)) return { body: FILAMENT };
    return { body: {} };
};
"""


def _run(tmp_path, body, modules=("inv_details.js",)):
    res = run_js(tmp_path, list(modules), PRELUDE + body)
    assert res["unhandled"] == [], res
    return res


# ---- one question at a time ----------------------------------------------------------------------------

@needs_node
def test_a_second_refill_question_waits_for_the_first(tmp_path):
    """K07 / K14. RED on 8153b81: the second mounted over the first (one overlay id),
    tearing it down unanswered."""
    res = _run(tmp_path, f"""
window.askRefillPlace(57, {json.dumps(ASK)});
window.askRefillPlace(58, {json.dumps(ASK)});
await __settle(60);
const first = {{ up: refills().length, html: refills()[0] && refills()[0].content }};
__overlayEls[0].querySelector('#fcc-refill-leave').onclick({{ type: 'click', detail: 1 }});
await __settle(60);
return {{ first, up: refills().length, second: refills()[1] && refills()[1].content }};
""")
    assert res["first"]["up"] == 1 and "#57 is back in stock" in res["first"]["html"], res
    assert res["up"] == 2 and "#58 is back in stock" in res["second"], res


@needs_node
def test_the_refill_question_waits_its_turn_behind_the_empty_weight_prompt(tmp_path):
    """K19. RED on 8153b81: it mounted over the prompt at once."""
    res = _run(tmp_path, f"""
window.showArchiveEmptyWeightPrompt(99, 7);
window.askRefillPlace(57, {json.dumps(ASK)});
await __settle(80);
const before = {{ prompt: promptsUp().length, refill: refills().length }};
__overlayEls[0].querySelector('#fcc-archive-later').onclick();
await __settle(80);
return {{ before, refill: refills().length }};
""")
    assert res["before"] == {"prompt": 1, "refill": 0}, res
    assert res["refill"] == 1, res


@needs_node
@pytest.mark.parametrize("skip", [False, True], ids=["opens-once-answered", "skips-for-a-scanned-spool"])
def test_it_waits_for_a_scan_being_answered(tmp_path, skip):
    """K13: not over a scan being answered; once it is answered, a spool scanned since
    the save is the one being weighed now, so a note says where #57 came off instead.
    RED on 8153b81: it mounted at once, over the scan."""
    res = _run(tmp_path, f"""
let pending = true, wake = null, skip = false;
window.askRefillPlace(57, {json.dumps(ASK)}, {{
    settle: () => (pending ? new Promise((r) => {{ wake = r; }}) : Promise.resolve()),
    scanPending: () => pending,
    skipIf: () => skip,
}});
await __settle(60);
const during = refills().length;
skip = {json.dumps(skip)};
pending = false;
if (wake) wake();
await __settle(60);
return {{ during, after: refills().length, toasts: __rec.toasts.map((t) => t.msg) }};
""")
    assert res["during"] == 0, res
    if skip:
        assert res["after"] == 0, res
        assert res["toasts"] == ["#57 is back in stock, Unassigned: it came off XL-3. Scan it to where you put it."], res
    else:
        assert res["after"] == 1, res


# ---- what it says, and what it does --------------------------------------------------------------------

@needs_node
def test_a_refused_scan_says_why_on_its_own_line(tmp_path):
    """K20. RED on 8153b81: the note under the buttons, which says why Back on XL-3 is
    greyed out, was replaced by the refused scan's words."""
    res = _run(tmp_path, f"""
await window.askRefillPlace(57, {json.dumps(dict(ASK, held_by=[99]))});
window._fccOpenMoveQuestion.flash('Answer the question first. (Ignored: ID:57)');
const ov = __overlayEls[0];
return {{ reason: ov.querySelector('#fcc-refill-note').textContent,
          scan: ov.querySelector('#fcc-refill-scan-note').textContent }};
""")
    assert res["scan"] == "Answer the question first. (Ignored: ID:57)", res
    assert res["reason"] != res["scan"], res


PICKER = r"""
const picked = [];
window.isMultiSlotBox = (row) => !!row && row.Type === 'Dryer Box';
window.openSlotPicker = () => {};
window.placeOneWithPicker = (o) => { picked.push(o.loc); return Promise.resolve({ outcome: 'stopped' }); };
"""


@needs_node
def test_a_scanned_label_finds_its_place_whatever_its_case(tmp_path):
    """K22. A box named "Garage-Box" in the place list, its label read upper case: its
    picker opens, by the list's own name. RED on 8153b81: no row matched, so a
    slotless move was posted, and the engine's slot pick could load a head unasked."""
    res = _run(tmp_path, PICKER + f"""
window.__respond = (url) => (url === '/api/locations'
    ? {{ body: [{{ LocationID: 'Garage-Box', Name: 'Garage', Type: 'Dryer Box', 'Max Spools': '4' }}] }}
    : {{ body: {{ status: 'success' }} }});
await window.askRefillPlace(57, {json.dumps(ASK)});
window._fccOpenMoveQuestion.route('LOC:Garage-Box', 'barcode');
await __settle(80);
return {{ picked, posts: posts() }};
""")
    assert res["picked"] == ["Garage-Box"] and res["posts"] == [], res


@needs_node
def test_a_place_list_that_cant_be_read_moves_nothing(tmp_path):
    """K22. RED on 8153b81: an unreadable list read as [], and the move was posted blind."""
    res = _run(tmp_path, PICKER + f"""
window.__respond = (url) => (url === '/api/locations'
    ? {{ status: 502, body: {{ message: 'no' }} }} : {{ body: {{ status: 'success' }} }});
await window.askRefillPlace(57, {json.dumps(ASK)});
window._fccOpenMoveQuestion.route('LOC:CR-SHELF-2', 'barcode');
await __settle(80);
return {{ posts: posts(), toasts: __rec.toasts.map((t) => t.msg) }};
""")
    assert res["posts"] == [], res
    assert res["toasts"] == ["Couldn't read the list of places, so #57 wasn't moved to CR-SHELF-2. "
                             "Try again in a moment."], res


@needs_node
def test_a_spool_put_back_leaves_the_scan_buffer(tmp_path):
    """K23. RED on 8153b81: #57 stayed buffered, so the next location scan of the buffer
    moved it off XL-3 again."""
    res = _run(tmp_path, f"""
state.heldSpools = [{{ id: 57 }}, {{ id: 60 }}];
await window.askRefillPlace(57, {json.dumps(ASK)});
__overlayEls[0].querySelector('#fcc-refill-back').onclick({{ type: 'click', detail: 1 }});
await __settle(80);
return {{ held: state.heldSpools.map((s) => s.id), posts: posts().length }};
""")
    assert res["posts"] == 1 and res["held"] == [60], res


@needs_node
def test_the_caller_hears_where_the_spool_landed(tmp_path):
    """K02. A slot's label scanned: the box's slot loads its head, and the wizard's
    Location field must show the head, not the box. RED on 8153b81: onMoved heard the
    box (the target)."""
    res = _run(tmp_path, f"""
window.__respond = (url) => (url === '/api/manage_contents'
    ? {{ body: {{ status: 'success', auto_deployed_to: 'XL-2' }} }} : {{ body: [] }});
const heard = [];
await window.askRefillPlace(57, {json.dumps(ASK)}, {{ onMoved: (where) => heard.push(where) }});
window._fccOpenMoveQuestion.route('LOC:DRYBOX-1:SLOT:2', 'barcode');
await __settle(80);
return {{ heard }};
""")
    assert res["heard"] == ["XL-2"], res


@needs_node
def test_pick_a_place_is_drawn_inside_the_window_it_was_asked_over(tmp_path):
    """K03 / K15. RED on 8153b81: no window was handed on, and the list mounted on the
    page body, under that window's focus trap."""
    res = _run(tmp_path, f"""
const host = document.getElementById('weighOutModal');
host.classList.add('show');
await window.askRefillPlace(57, {json.dumps(ASK)}, {{ host }});
__overlayEls[0].querySelector('#fcc-refill-pick').onclick({{ type: 'click', detail: 1 }});
await __settle(40);
return {{ picks }};
""")
    assert res["picks"] == [{"sid": "57", "loc": "", "host": "weighOutModal"}], res


@needs_node
def test_force_locations_list_mounts_inside_the_host_and_says_when_it_was_cancelled(tmp_path):
    """K03 / K15, the list itself: with a `host` window open, the Swal's target is that
    window, and Cancel is heard (`onSettled`). RED on 8153b81: the target was the page
    body, and nothing heard a cancel."""
    # The base prelude's stub of promptEditLocation is left out: the real one runs.
    res = run_js(tmp_path, ["inv_details.js"], BASE_PRELUDE.replace(
        "window.promptEditLocation = (sid, loc, o) => opened.push({ sid, loc, fromCard: !!(o && o.fromCard) });", "")
        + r"""
const host = document.getElementById('wizardModal');
host.classList.add('show');
const fired = [], settled = [];
window.Swal = { fire: (o) => { fired.push(o.target === host ? 'host' : (o.target === document.body ? 'body' : 'other'));
                               return Promise.resolve({ isConfirmed: false }); },
                getPopup: () => null };
window.promptEditLocation(57, '', { fromCard: true, host, onSettled: (o) => settled.push(o) });
await __settle(60);
return { fired, settled };
""")
    assert res["unhandled"] == [], res
    assert res["fired"] == ["host"] and res["settled"] == ["cancelled"], res


# ---- its QR codes (Derek's picture walk, 2026-11-18: "needs QR codes") --------------------------------

QR = r"""
const sids = () => Object.keys(window._fccActiveConfirms || {});
"""


@needs_node
@pytest.mark.parametrize("answer, location", [("CONFIRM", "XL-3"), ("STORE", "LR"), ("CANCEL", None)])
def test_each_answer_has_a_qr(tmp_path, answer, location):
    """Back on it, In the room, Leave it: each answer's QR answers it. RED on
    8153b81: the question had no QR codes."""
    res = _run(tmp_path, QR + f"""
await window.askRefillPlace(57, {json.dumps(ASK)});
const one = sids();
window.routeConfirmScan(`CMD:{answer}:${{one[0]}}`);
await __settle(80);
return {{ one: one.length, posts: posts(), toasts: __rec.toasts.map((t) => t.msg), left: sids().length }};
""", modules=("inv_core.js", "inv_details.js"))
    assert res["one"] == 1, res
    if location:
        assert [p[1]["location"] for p in res["posts"]] == [location], res
    else:
        # (inv_core.js's own toast draws into the page, not the record: nothing moved.)
        assert res["posts"] == [], res
    assert res["left"] == 0, res


@needs_node
def test_a_greyed_out_answers_qr_only_says_why(tmp_path):
    """Another spool is on XL-3: Back's QR moves nothing, says why on the scan line, and
    the question's other QRs still answer. RED on 8153b81: no QR codes."""
    res = _run(tmp_path, QR + f"""
await window.askRefillPlace(57, {json.dumps(dict(ASK, held_by=[99]))});
const one = sids();
window.routeConfirmScan(`CMD:CONFIRM:${{one[0]}}`);
await __settle(40);
const after = {{ posts: posts().length, left: sids().length,
                 said: __overlayEls[0].querySelector('#fcc-refill-scan-note').textContent }};
window.routeConfirmScan(`CMD:STORE:${{one[0]}}`);
await __settle(80);
return {{ after, posts: posts() }};
""", modules=("inv_core.js", "inv_details.js"))
    assert res["after"]["posts"] == 0 and res["after"]["left"] == 1, res
    assert res["after"]["said"] == "XL-3 holds #99 now, so it can't go back on it. Pick another answer.", res
    assert [p[1]["location"] for p in res["posts"]] == ["LR"], res


# ---- the weigh-out list: the keyboard (browser) --------------------------------------------------------

ANSWERS = r"""() => {
    const base = window.fetch;
    window.__refillFor = {};            // spool id -> refill_ask its save answers
    window.__changedOnce = {};          // spool id -> answer its next save with details_changed
    window.fetch = function (url, opts) {
        url = String(url);
        if (url.includes('/api/spool/update')) {
            const body = JSON.parse(opts.body);
            if (window.__changedOnce[body.id]) {
                const fresh = window.__changedOnce[body.id];
                delete window.__changedOnce[body.id];
                window.__posts.push({ url, body });
                return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({
                    status: 'details_changed', changed: 'capacity', fresh,
                    msg: `#${body.id}'s weight changed since this was read: check its preview and press Enter in its box again` }) });
            }
            const ask = window.__refillFor[body.id];
            if (ask) {
                return base(url, opts).then((r) => r.json()).then((ans) => ({ ok: true, status: 200,
                    json: () => Promise.resolve(Object.assign({}, ans, { refill_ask: ask, location_now: '' })) }));
            }
        }
        return base(url, opts);
    };
}"""


@pytest.fixture
def wo2(wo):
    page, open_ = wo
    page.evaluate(ANSWERS)
    return page, open_


@pytest.mark.parametrize("how", ["leave-click", "escape"])
def test_the_keyboard_comes_back_to_the_list_when_the_question_closes(wo2, how):
    """K04 / K06. #6 weighed back into stock after it left HEAD-1: the question asks.
    Answered with Leave it Unassigned (a click) or Escape, the keyboard is back in a
    box, and the next reading goes there. RED on 8153b81: the focus was left on the
    page, and "450" went to the scan path as a spool id."""
    page, open_ = wo2
    page.evaluate("() => { window.__refillFor[6] = { place: 'HEAD-1', room: 'LR', held_by: [] }; }")
    open_(held=(6, 134))
    press(page, "300", 150)
    _saved(page)
    page.wait_for_function("() => document.activeElement && document.activeElement.id === 'fcc-refill-leave'",
                           timeout=5000)
    if how == "escape":
        page.keyboard.press("Escape")
    else:
        page.locator("#fcc-refill-leave").click()
    page.wait_for_function("() => !document.getElementById('fcc-refill-place')")
    page.wait_for_timeout(50)
    assert _focus(page) == "134", _focus(page)
    later(page, 700)
    press(page, "450", 150, enter=False)
    assert _box(page, 134) == "450" and _scans(page) == [], (_box(page, 134), _scans(page))


def test_the_questions_arrows_work_after_a_click_on_its_words(wo2):
    """K21 (Group 62.4's rule). RED on 8153b81: a click on its words left the focus on
    the page, and its arrows did nothing until a Tab."""
    page, open_ = wo2
    page.evaluate("() => { window.__refillFor[6] = { place: 'HEAD-1', room: 'LR', held_by: [] }; }")
    open_(held=(6, 134))
    press(page, "300", 150)
    _saved(page)
    page.wait_for_function("() => document.activeElement && document.activeElement.id === 'fcc-refill-leave'",
                           timeout=5000)
    page.locator("#fcc-refill-place p").click()
    page.keyboard.press("ArrowRight")
    assert page.evaluate("() => document.activeElement && document.activeElement.classList"
                         ".contains('fcc-refill-answer')"), _focus(page)


def test_a_refused_save_gives_its_row_the_keyboard_back(wo2):
    """K39. #6's save is refused (its total changed since it was read): its row's box
    takes the keyboard back, its reading selected, so the Enter the toast asks for
    saves #6. RED on 8153b81: the keyboard stayed on #134's box, where that Enter
    moved on (or saved #134 with whatever it held)."""
    page, open_ = wo2
    page.evaluate("() => { window.__changedOnce[6] = { initial: 1200, used: 31, archived: false }; }")
    open_(held=(6, 134))
    press(page, "300", 150)
    _saved(page)
    page.wait_for_function("() => document.activeElement && document.activeElement.dataset"
                           " && document.activeElement.dataset.id === '6'", timeout=5000)
    assert page.evaluate("() => { const b = document.activeElement; return b.value === '300'"
                         " && b.selectionStart === 0 && b.selectionEnd === 3; }")
    later(page, 700)
    press(page, "", 0)
    _saved(page, 2)
    ups = _updates(page)
    assert [u["id"] for u in ups] == [6, 6], ups


def test_the_empty_weight_prompt_waits_for_a_reading_typed_during_its_read(wo2):
    """K11. #8 weighed to 0 g is archived; its prompt reads the filament, and while that
    read is out the person types the next row's reading. The prompt doesn't open over
    it. RED on 8153b81: it opened once the read came, took the keyboard, and the rest
    of the reading was saved as the filament's empty weight."""
    page, open_ = wo2
    open_(held=(8, 6))
    page.evaluate("() => { window.__holdFilament = true; }")
    press(page, "0", 150)
    _saved(page)
    page.wait_for_function("() => window.__held.filament.length >= 1", timeout=5000)
    later(page, 700)
    press(page, "4", 150, enter=False)
    page.evaluate("() => { window.__holdFilament = false; window.__release('filament'); }")
    page.wait_for_timeout(400)
    assert page.locator("#fcc-archive-empty-overlay").count() == 0
    assert _focus(page) == "6" and _box(page, 6) == "4", (_focus(page), _box(page, 6))


def test_the_offered_empty_weight_is_selected_and_one_as_heavy_as_the_spool_is_refused(wo2):
    """K05. #8 is a new spool with no empty weight on record; Gross 1245 offers 245 g
    (1245 less its 1000 g). Since Derek's option 2 (2026-11-19, round 4) the box opens
    empty and the offer is a button of its own, so 1300 typed is 1300, and as heavy as
    the whole spool on the scale it is refused in words; 250 typed over it (selected
    by the refusal) is 250. RED on 8153b81: the caret sat in front of the offer,
    250245 g was saved, and the 1300 would have been taken."""
    page, open_ = wo2
    open_(held=(8,), mode="gross")
    press(page, "1245", 150)
    page.wait_for_function("() => document.activeElement && document.activeElement.id"
                           " === 'fcc-missing-empty-weight-overlay-input'", timeout=5000)
    page.wait_for_timeout(50)
    later(page, 700)
    press(page, "1300", 150)
    err = page.locator("#fcc-missing-empty-weight-overlay-err").inner_text()
    # PIN UPDATED DELIBERATELY (review round 2: the first rule, "at or above the reading", refused an
    # empty spool's own reading; round 3: a spool FCC has nothing used from, its reading above its net,
    # can't be empty, so it is refused at or above the reading, in words that don't call it new: round
    # 2's "the reading less 85% of its net" refused a part-used spool's true empty weight; round 4: the
    # net is FCC's record, and the words say how to record a spool that is empty after all).
    assert err == ("1300 g can't be its empty weight: it must be less than the 1245 g on the scale, which is "
                   "more than the 1000 g of filament FCC has on this spool. If the spool on the scale is "
                   "empty, Cancel and weigh it in Net as 0; otherwise check the number."), err
    assert _updates(page) == []
    later(page, 700)
    press(page, "250", 150)
    _saved(page)
    ups = _updates(page)
    assert ups[0]["updates"]["spool_weight"] == 250, ups


def test_a_digit_on_a_dialog_inside_the_weigh_window_stays_out_of_the_weight_boxes(wo2):
    """K03 (inv_core.js's weight capture): a dialog drawn inside the weigh-out window
    (Force Location's list, from the refill question's Pick a place…) keeps its own
    keys. RED on 8153b81: a digit typed on its button went into the target's box."""
    page, open_ = wo2
    open_(held=(6, 134))
    page.evaluate("""() => {
        const c = document.createElement('div');
        c.className = 'swal2-container';
        c.innerHTML = '<button type="button" id="swal-ok">Force Move</button>';
        document.getElementById('weighOutModal').appendChild(c);
        document.getElementById('swal-ok').focus();
    }""")
    later(page, 700)
    press(page, "2", 150, enter=False)
    assert _box(page, 6) == "" and _focus(page) == "swal-ok", (_box(page, 6), _focus(page))
