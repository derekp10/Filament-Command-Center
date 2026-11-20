"""Group 63 review, round 4: the page half of its findings, hermetic.

Round 4 read round 3's fixes (7a4f9ab..3612032) and found, on the page:
  - (orange, the critic) a refill question's turn that ended in a dialog its move
    opened (the move's print question, the slot picker, Force Location's "Cancel
    Override?") never stamped the line's answer time, so a double Enter or Escape
    there answered the next question unread, or saved the post-archive prompt's
    figure as the filament's empty weight;
  - the line's rule held for Leave only: Back, the room and Pick a place… still
    took a keyboard's click inside the 700 ms (an arrow, then Enter, moved the next
    spool unread);
  - a double Space's second press replaced the post-archive prompt's figure with a
    space;
  - FCC's own answer for a locations.json it can't read (a 500 with a JSON error)
    drew Force Location with only "-- Unassigned --", and asked nothing again;
  - a Quick-Weigh from a window over the weigh-out list handed the question the
    list, under that window;
  - a double Enter on a Gross reading took the missing-tare question's offered
    figure, unread, as the spool's own empty weight;
  - the refusal for a spool with nothing used told the person to check a correct
    number and never said how to record an empty spool.

Node tests run on test_core1_return_ejectall_js.run_js; browser tests on
test_weigh_out_scan_focus_js's `wo` harness and test_missing_tare_and_grams_63_7_9_js's
`entry` (the Quick-Weigh), isolated pages with no network. Every test is RED on
3612032 (the group's head before round 4's fixes) unless its docstring says control.
"""
from __future__ import annotations

import json

import pytest

from test_core1_return_ejectall_js import NODE, NODE_MISSING_MSG
from test_missing_tare_and_grams_63_7_9_js import PROMPT_ID, entry  # noqa: F401
from test_missing_tare_and_grams_63_7_9_js import _prompt_up
from test_missing_tare_and_grams_63_7_9_js import _saved as _entry_saved
from test_quick_weigh_scan_js import later, press
from test_refill_question_review_63_js import ANSWERS
from test_review2_page_63_js import ASK, _question_up, _real, _two_questions, _wait_question
from test_review3_page_63_js import QUICK_WEIGH_SAVE, REFILL_THEN_PROMPT, _err, _filament_writes, _focus_on
from test_weigh_out_scan_focus_js import wo  # noqa: F401

needs_node = pytest.mark.skipif(NODE is None, reason=NODE_MISSING_MSG)

HEADS = [{"LocationID": "HEAD-1", "Name": "Head one", "Type": "Tool Head"},
         {"LocationID": "HEAD-2", "Name": "Head two", "Type": "Tool Head"},
         {"LocationID": "LR", "Name": "Living room", "Type": "Room"}]


@pytest.fixture
def wo2(wo):
    page, open_ = wo
    page.evaluate(ANSWERS)
    return page, open_


def _moves_answer(answer):
    """The page's fetch, with the place list and every move answered `answer`."""
    return r"""() => {
        const base = window.fetch;
        window.fetch = function (url, opts) {
            url = String(url);
            if (url.includes('/api/locations')) {
                return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(%s) });
            }
            if (url.includes('/api/manage_contents')) {
                window.__posts.push({ url, body: JSON.parse(opts.body) });
                return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(%s) });
            }
            return base(url, opts);
        };
    }""" % (json.dumps(HEADS), json.dumps(answer))


MOVES_LAND = _moves_answer({"status": "success"})
MOVES_ASK_PRINTING = _moves_answer({
    "status": "requires_confirm", "confirm_type": "active_print",
    "active_print": {"toolhead": "HEAD-1", "printer_name": "Printer one", "state": "PRINTING"},
    "active_prints": [{"toolhead": "HEAD-1", "printer_name": "Printer one", "state": "PRINTING", "role": "destination"}],
    "msg": "Printer one is printing on HEAD-1. Load #6 onto it anyway?"})


def _moves(page):
    return page.evaluate("() => window.__posts.filter((p) => p.url === '/api/manage_contents')"
                         ".map((p) => [String(p.body.spool_id), p.body.location])")


# ---- a turn that ended in the move's own question (orange, the critic) ------------------------------------

def _back_to_the_print_question(page):
    page.evaluate("() => { delete window.fccQuestionArmMs; }")
    _focus_on(page, "fcc-refill-leave")
    later(page, 900)
    page.locator("#fcc-refill-back").click()
    page.wait_for_function("() => document.activeElement && document.activeElement.classList"
                           " && document.activeElement.classList.contains('fcc-apc-no')", timeout=5000)
    later(page, 900)


@pytest.mark.parametrize("key", ["Enter", "Escape"])
def test_a_double_key_press_on_the_moves_own_question_answers_only_it(wo2, key):
    """#6's Back on HEAD-1 asks about a print; a double Enter (or Escape) on its
    Cancel answers that question only: #134's refill question opens and stays up.
    RED on 3612032: the line's stamp was the press on Back, seconds before, and the
    second press answered #134's question unread."""
    page, open_ = wo2
    page.evaluate(MOVES_ASK_PRINTING)
    open_(held=(6, 134))
    _two_questions(page)
    _back_to_the_print_question(page)
    page.keyboard.press(key)
    _wait_question(page, 134)
    _focus_on(page, "fcc-refill-leave")
    later(page, 120)
    page.keyboard.press(key)
    page.wait_for_timeout(200)
    assert page.evaluate("() => window.__closedQs") == [[6, "back"]]
    assert _question_up(page) == 134


def test_control_a_key_a_moment_after_the_moves_question_answers_the_next(wo2):
    page, open_ = wo2
    page.evaluate(MOVES_ASK_PRINTING)
    open_(held=(6, 134))
    _two_questions(page)
    _back_to_the_print_question(page)
    page.keyboard.press("Enter")
    _wait_question(page, 134)
    _focus_on(page, "fcc-refill-leave")
    later(page, 800)
    page.keyboard.press("Enter")
    page.wait_for_function("() => !document.getElementById('fcc-refill-place')", timeout=5000)
    assert page.evaluate("() => window.__closedQs") == [[6, "back"], [134, "leave"]]


def test_a_double_enter_on_the_moves_own_question_never_saves_the_prompts_figure(wo2):
    """The same, the post-archive prompt (filled in with 245 g) next in line: the
    second Enter never saves it as the filament's empty weight. RED on 3612032 (the
    critic): it saved 245 g, unread."""
    page, _ = wo2
    page.evaluate(MOVES_ASK_PRINTING)
    page.evaluate(REFILL_THEN_PROMPT)
    _back_to_the_print_question(page)
    page.keyboard.press("Enter")
    _focus_on(page, "fcc-archive-empty-wt")
    later(page, 120)
    page.keyboard.press("Enter")
    page.wait_for_timeout(200)
    assert page.locator("#fcc-archive-empty-overlay").count() == 1
    assert _filament_writes(page) == []


# ---- Back, the room and Pick a place… keep the line's rule -------------------------------------------------

@pytest.mark.parametrize("keys", [["ArrowLeft", "Enter"], ["ArrowLeft", "ArrowLeft", "Enter"]], ids=["room", "back"])
def test_an_arrow_and_an_enter_right_after_an_answer_move_nothing(wo2, keys):
    """#6's question answered with Leave; #134's opens, and 250 ms later an arrow
    and an Enter land on In LR for now (or two arrows on Back on HEAD-2): nothing
    moves and the question stays up. RED on 3612032: the keyboard's click went
    through, and #134 was filed on LR (or HEAD-2) unread."""
    page, open_ = wo2
    page.evaluate(MOVES_LAND)
    open_(held=(6, 134))
    page.evaluate("() => { delete window.fccQuestionArmMs; }")
    _two_questions(page)
    later(page, 900)
    page.keyboard.press("Enter")
    _wait_question(page, 134)
    _focus_on(page, "fcc-refill-leave")
    later(page, 250)
    for k in keys:
        page.keyboard.press(k)
    page.wait_for_timeout(250)
    assert page.evaluate("() => window.__closedQs") == [[6, "leave"]]
    assert _question_up(page) == 134
    assert _moves(page) == []


def test_control_an_arrow_and_an_enter_a_moment_later_move_the_spool(wo2):
    page, open_ = wo2
    page.evaluate(MOVES_LAND)
    open_(held=(6, 134))
    page.evaluate("() => { delete window.fccQuestionArmMs; }")
    _two_questions(page)
    later(page, 900)
    page.keyboard.press("Enter")
    _wait_question(page, 134)
    _focus_on(page, "fcc-refill-leave")
    later(page, 800)
    page.keyboard.press("ArrowLeft")
    page.keyboard.press("Enter")
    page.wait_for_function("() => window.__posts.some((p) => p.url === '/api/manage_contents')", timeout=5000)
    assert _moves(page) == [["134", "LR"]]


# ---- the post-archive prompt's figure and a double Space ---------------------------------------------------

def test_a_double_space_leaves_the_prompts_figure_alone(wo2):
    """A double Space on #6's Leave, the prompt (filled in with 245 g) next in line:
    its figure stays, and an Enter a moment later saves it. RED on 3612032: the
    second Space replaced 245 with a space, and the Enter said "Enter a positive
    weight"."""
    page, _ = wo2
    page.evaluate("() => { delete window.fccQuestionArmMs; }")
    page.evaluate(REFILL_THEN_PROMPT)
    _focus_on(page, "fcc-refill-leave")
    later(page, 900)
    page.keyboard.press("Space")
    _focus_on(page, "fcc-archive-empty-wt")
    later(page, 120)
    page.keyboard.press("Space")
    page.wait_for_timeout(100)
    assert page.evaluate("() => document.getElementById('fcc-archive-empty-wt').value") == "245"
    later(page, 800)
    page.keyboard.press("Enter")
    page.wait_for_function("() => window.__posts.some((p) => p.url === '/api/update_filament')", timeout=5000)
    assert _filament_writes(page) == [{"id": 5, "data": {"spool_weight": 245}}]


# ---- FCC's own answer for a place list it can't read -------------------------------------------------------

@needs_node
def test_fccs_own_unreadable_place_list_answer_asks_again_with_the_reason(tmp_path):
    """Pick a place…, and /api/locations answers FCC's 500 for a locations.json it
    can't read: no list is drawn, and the question asks again with the reason. RED
    on 3612032: Force Location opened with only "-- Unassigned --", said nothing,
    and nothing asked again."""
    res = _real(tmp_path, f"""
window.fetchT = (u, o) => (String(u) === '/api/locations'
    ? Promise.resolve({{ ok: false, status: 500, json: () => Promise.resolve({{ error: 'locations_corrupt',
        path: '/data/locations.json', line: 3, col: 1, msg: 'Expecting value' }}) }})
    : globalThis.fetch(u, o));
const fired = [];
window.Swal = {{ fire: (o) => {{ fired.push(o.html || ''); return Promise.resolve({{ isConfirmed: false }}); }},
                 getPopup: () => null, isVisible: () => false, close() {{}} }};
window.askRefillPlace(57, {json.dumps(ASK)});
await __settle(60);
__overlayEls[0].querySelector('#fcc-refill-pick').onclick({{ type: 'click', detail: 1 }});
await __settle(150);
return {{ fired: fired.length, again: refills().map((o) => o.content) }};
""")
    assert res["fired"] == 0, res
    assert len(res["again"]) == 2 and 'id="fcc-refill-notice"' in res["again"][1], res
    assert "read the list of places" in res["again"][1], res


# ---- the Quick-Weigh over the weigh-out list ---------------------------------------------------------------

@needs_node
@pytest.mark.parametrize("stack, host", [
    (["manageModal", "weighOutModal"], "manageModal"),
    (["weighOutModal"], "weighOutModal"),
    (["confirmModal", "weighOutModal"], "weighOutModal"),
], ids=["a-window-over-the-list", "control-the-list-alone", "control-a-gating-dialog-on-top"])
def test_the_quick_weighs_question_is_handed_the_window_on_top(tmp_path, stack, host):
    """The Quick-Weigh's save from the Location Manager opened over the weigh-out
    list: the question is handed the manager, on top. RED on 3612032: handed the
    list under it, so Pick a place… drew its list there. Controls: the list alone is
    the host; a gating dialog on top (a few seconds' question) never is."""
    z = {"weighOutModal": 1055, "manageModal": 1065, "confirmModal": 1075}
    res = _real(tmp_path, f"""
const ids = {json.dumps(stack)};
const zs = {json.dumps(z)};
ids.forEach((id) => {{ const el = document.getElementById(id); el.classList.add('show'); el.style.zIndex = String(zs[id]); }});
document.querySelectorAll = (sel) => (sel === '.modal.show' ? ids.map((id) => document.getElementById(id)) : []);
globalThis.getComputedStyle = (el) => ({{ zIndex: (el.style && el.style.zIndex) || 'auto' }});
const asked = [];
window.askRefillPlace = (sid, ask, o) => asked.push(o && o.host ? o.host.id : null);
""" + QUICK_WEIGH_SAVE + """
await __settle(600);
return { asked };
""", modules=("inv_weigh_out.js",))
    assert res["asked"] == [host], res


# ---- the missing-tare question's offered figure and a double Enter -----------------------------------------

def test_a_double_enter_on_a_gross_reading_never_takes_the_offered_figure(entry):
    """Gross 1255 on a 1000 g spool with nothing used, no empty weight known: the
    question opens offering 255 g, and the second Enter of a double press, 90 ms
    later, takes nothing (since Derek's option 2 the box opens empty, the figure a
    button of its own). RED on 3612032: it saved 255 g, filled in and selected,
    unread, as the spool's own empty weight."""
    page, open_ = entry
    page.evaluate("() => { delete window.fccQuestionArmMs; }")
    open_("gross", initial=1000, used=0)
    press(page, "1255", 150)
    _prompt_up(page)
    later(page, 90)
    page.keyboard.press("Enter")
    page.wait_for_timeout(100)
    assert page.evaluate("() => window.__saved.length") == 0
    assert page.locator(f"#{PROMPT_ID}").count() == 1


@pytest.mark.parametrize("how", ["the-offer-and-an-enter", "a-figure-typed-at-once"])
def test_control_a_deliberate_answer_is_never_held_up(entry, how):
    """Controls: the offer's own button and an Enter take its figure; a figure typed
    is taken at once, whatever the time."""
    page, open_ = entry
    page.evaluate("() => { delete window.fccQuestionArmMs; }")
    open_("gross", initial=1000, used=0)
    press(page, "1255", 150)
    _prompt_up(page)
    if how == "the-offer-and-an-enter":
        page.click(f"#{PROMPT_ID}-use-offer")
        page.keyboard.press("Enter")
        expected = 255
    else:
        # A person's pace (digits 40 ms apart are a scanner's: inv_core's weight capture),
        # its Enter still inside the 700 ms the offered figure waits.
        press(page, "250", 100)
        expected = 250
    page.wait_for_function("() => window.__saved.length === 1", timeout=5000)
    assert _entry_saved(page) == [{"mode": "gross", "value": 1255, "tare": expected, "typed": expected}]


def test_the_wizards_part_used_spool_is_never_recorded_full_by_one_enter(isolated_page):
    """Derek's option 2 (2026-11-19): cataloguing a part-used spool in the wizard's
    Weigh from Scale (nothing used on a new record, its filament's net 1000 g, 1050 g
    on the scale), the question opens with its box empty, and an Enter takes nothing:
    the person types the empty weight, or presses the offer's own button. RED on
    3612032: the offer, 50 g, was filled in and selected, and one Enter recorded the
    spool as full (used 0, empty 50: every later Gross weigh 200 g high)."""
    from test_quick_weigh_scan_js import FAKE_CLOCK, INPUT
    from test_review3_page_63_js import WIZARD_PAGE
    from test_slow_scan_slash_js import _accumulator
    from test_weigh_out_scan_focus_js import MODULES
    page = isolated_page
    page.set_content(WIZARD_PAGE)
    page.add_script_tag(content="window.registerShortcut = () => {}; window.fetch = () => Promise.resolve("
                                "{ ok: true, status: 200, json: () => Promise.resolve({ success: true, fields: {} }) });")
    for name in ("overlay_mount.js", "inv_core.js", "weight_utils.js", "weight_entry.js", "choice_validation.js",
                 "inv_wizard.js"):
        page.add_script_tag(content=(MODULES / name).read_text(encoding="utf-8"))
    page.add_script_tag(content=_accumulator())
    page.evaluate(FAKE_CLOCK)
    page.evaluate("() => { window.fccQuestionArmMs = 0; window.wizardOpenWeightEntry(); }")
    page.wait_for_function("(s) => document.activeElement === document.querySelector(s)", arg=INPUT, timeout=5000)
    press(page, "1050", 150)
    _prompt_up(page)
    later(page, 900)
    page.keyboard.press("Enter")
    page.wait_for_timeout(150)
    assert page.locator(f"#{PROMPT_ID}").count() == 1
    assert page.evaluate("() => [document.getElementById('wiz-spool-used').value,"
                         " document.getElementById('wiz-spool-empty_weight').value]") == ["", ""]


# ---- the refusal's words for a spool with nothing used ---------------------------------------------------

def test_the_refusal_says_how_to_record_a_spool_that_is_empty_after_all(entry):
    """A sample spool FCC never charged (100 g net), empty on the scale at 250 g, its
    empty weight typed as 250: refused (it can't be weighed empty in Gross), in words
    that say the net is FCC's record and how to record it empty. RED on 3612032:
    "this spool's 100 g of filament", and "Check the number." about a right number."""
    page, open_ = entry
    open_("gross", initial=100, used=0)
    press(page, "250", 150)
    _prompt_up(page)
    later(page, 700)
    press(page, "250", 150)
    page.wait_for_timeout(50)
    assert _err(page) == ("250 g can't be its empty weight: it must be less than the 250 g on the scale, which is "
                          "more than the 100 g of filament FCC has on this spool. If the spool on the scale is "
                          "empty, Cancel and weigh it in Net as 0; otherwise check the number."), _err(page)
