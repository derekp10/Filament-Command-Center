"""Group 63 review, round 3: the page half of its findings, hermetic.

Round 3 read round 2's fixes and found, on the page:
  - (orange) the missing-tare question's new-spool limit refused the true empty
    weight of any spool FCC has nothing used from that isn't full (a part-used spool
    being catalogued in the wizard's Weigh from Scale, a spool under a filament whose
    net is wrong), and said the spool was new;
  - with no net known (the wizard), an empty weight at or above the reading was
    taken, and wrote a total of 0 g into the form;
  - (orange, the critic) the double-press guard covered refill → refill only: a
    double Escape or Enter across the post-archive empty-weight prompt answered the
    question behind it unread, and in one order saved the prompt's figure as the
    filament's empty weight;
  - a double Enter or Space on Leave it Unassigned answered two refill questions
    (a keyboard's click was let through);
  - Pick a place… from a Quick-Weigh opened in the search panel over a window drew
    Force Location's list in that window, under the panel and its focus trap; and
    the window handed on was the last in the page's order, not the one on top;
  - a question's own Cancel QR held a person's Cancel Audit off for 1.5 s;
  - a CMD:CANCEL dropped as a double read said nothing on the question;
  - the slot picker's own Cancel, read twice, cancelled the refill question that
    opened behind it;
  - a place list that couldn't be read asked again with no reason on the question;
  - a refill move that failed asked again with none of the weigh-out list's waits,
    and took the keyboard from a spool scanned during the move.

Node tests run on test_core1_return_ejectall_js.run_js; browser tests on
test_weigh_out_scan_focus_js's `wo` harness and test_missing_tare_and_grams_63_7_9_js's
`entry` (the Quick-Weigh), isolated pages with no network. Every test is RED on
7a4f9ab (the group's head before round 3's fixes) unless its docstring says control.
"""
from __future__ import annotations

import json

import pytest

from test_core1_return_ejectall_js import NODE, NODE_MISSING_MSG
from test_missing_tare_and_grams_63_7_9_js import PROMPT_ID, entry  # noqa: F401
from test_missing_tare_and_grams_63_7_9_js import _prompt_up
from test_missing_tare_and_grams_63_7_9_js import _saved as _entry_saved
from test_quick_weigh_scan_js import FAKE_CLOCK, INPUT, later, press
from test_refill_question_review_63_js import ANSWERS
from test_review2_page_63_js import ASK, SEARCH_PANEL, _question_up, _real, _two_questions, _wait_question
from test_slow_scan_slash_js import _accumulator
from test_weigh_out_scan_focus_js import MODULES, _answered, _focus, _saved, _scans, _updates, wo  # noqa: F401

needs_node = pytest.mark.skipif(NODE is None, reason=NODE_MISSING_MSG)


@pytest.fixture
def wo2(wo):
    page, open_ = wo
    page.evaluate(ANSWERS)
    return page, open_


def _err(page):
    return page.evaluate(f"() => document.getElementById('{PROMPT_ID}-err').textContent")


# ---- the missing-tare question's limit (orange) ----------------------------------------------------------

@pytest.mark.parametrize("initial, reading, typed", [
    (1000, "1050", "250"), (1000, "1010", "260"), (500, "550", "200"), (1000, "1001", "250"),
], ids=["800g-on-a-1kg-spool", "a-750g-spool-under-a-1kg-filament", "a-500g-spool", "just-over-its-net"])
def test_a_part_used_spool_with_nothing_used_on_record_takes_its_true_empty_weight(entry, initial, reading, typed):
    """The Quick-Weigh in Gross, a spool FCC has nothing used from (a new record, or a
    filament whose net is wrong) that holds less than its net: its true empty weight
    is taken. RED on 7a4f9ab: refused, "a new spool's 1000 g of filament is in the
    1050 g on the scale" (round 2's limit, the reading less 85% of its net)."""
    page, open_ = entry
    open_("gross", initial=initial, used=0)
    press(page, reading, 150)
    _prompt_up(page)
    later(page, 700)
    press(page, typed, 150)
    page.wait_for_function("() => window.__saved.length === 1", timeout=5000)
    assert _entry_saved(page) == [{"mode": "gross", "value": int(reading), "tare": int(typed), "typed": int(typed)}]


def test_a_figure_at_the_reading_on_a_spool_with_nothing_used_is_refused_in_words(entry):
    """Its reading is more than its net, so the spool isn't empty: an empty weight as
    heavy as the reading is refused, in words that don't call it new. RED on 7a4f9ab:
    "a new spool's 1000 g of filament is in the 1050 g on the scale"."""
    page, open_ = entry
    open_("gross", initial=1000, used=0)
    press(page, "1050", 150)
    _prompt_up(page)
    later(page, 700)
    press(page, "1050", 150)
    page.wait_for_timeout(50)
    # PIN UPDATED DELIBERATELY (review round 4): the net is FCC's record, and the words
    # say how to record a spool that is empty after all.
    assert _err(page) == ("1050 g can't be its empty weight: it must be less than the 1050 g on the scale, which "
                          "is more than the 1000 g of filament FCC has on this spool. If the spool on the scale "
                          "is empty, Cancel and weigh it in Net as 0; otherwise check the number."), _err(page)
    assert page.evaluate("() => window.__saved.length") == 0


def test_the_weigh_out_list_takes_a_part_used_spools_true_empty_weight(wo2):
    """The list's Gross row, #8 with nothing used on record (1000 g net, no empty
    weight): 1050 on the scale and 250 empty is 800 g left. RED on 7a4f9ab: refused,
    and the list's question has no Skip."""
    page, open_ = wo2
    open_(held=(8,), mode="gross")
    press(page, "1050", 150)
    page.wait_for_function("() => document.activeElement && document.activeElement.id"
                           " === 'fcc-missing-empty-weight-overlay-input'", timeout=5000)
    later(page, 700)
    press(page, "250", 150)
    _saved(page)
    ups = _updates(page)
    assert [u["id"] for u in ups] == [8], ups
    assert ups[0]["updates"]["used_weight"] == 200 and ups[0]["updates"]["spool_weight"] == 250, ups


WIZARD_PAGE = """<!doctype html><html><head><meta charset="utf-8"></head><body>
<div id="toast-container"></div>
<div id="wizardModal" class="modal show">
  <input id="wiz-fil-weight" value="1000"><input id="wiz-fil-empty_weight" value="">
  <input id="wiz-fil-vendor-search" value="Acme"><input id="wiz-fil-material" value="PLA">
  <input id="wiz-fil-color_name" value="Blue">
  <input id="wiz-spool-initial_weight" value=""><input id="wiz-spool-used" value="">
  <input id="wiz-spool-empty_weight" value=""><input id="wiz-spool-scale" value="">
  <input id="wiz-spool-remaining" value="">
</div>
</body></html>"""


def test_the_wizards_weigh_from_scale_catalogues_a_part_used_spool(isolated_page):
    """The wizard's Weigh from Scale, cataloguing a part-used spool (nothing used yet
    on its new record, its filament's net 1000 g): 1050 on the scale, 250 empty, so
    200 used. RED on 7a4f9ab: refused, and calling the spool new."""
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
    later(page, 700)
    press(page, "250", 150)
    page.wait_for_function("() => document.getElementById('wiz-spool-used').value !== ''", timeout=5000)
    assert page.evaluate("() => [document.getElementById('wiz-spool-used').value,"
                         " document.getElementById('wiz-spool-empty_weight').value]") == ["200", "250"]


@pytest.mark.parametrize("reading, typed", [("745", "800"), ("245", "245")],
                         ids=["above-the-reading", "the-reading-again"])
def test_with_no_net_known_a_figure_at_or_above_the_reading_is_refused(entry, reading, typed):
    """The wizard's no-net path (allowUnknownInitial): what is on the spool is the
    reading less its empty weight, so a figure at or above the reading is refused.
    RED on 7a4f9ab: taken, and the wizard wrote a total of 0 g into the form."""
    page, open_ = entry
    open_("gross", initial=0, used=0, unknown=True)
    press(page, reading, 150)
    _prompt_up(page)
    later(page, 700)
    press(page, typed, 150)
    page.wait_for_timeout(50)
    assert _err(page) == (f"{typed} g can't be its empty weight: it must be less than the {reading} g on the "
                          f"scale, which is the spool with its filament. Check the number."), _err(page)
    assert page.evaluate("() => window.__saved.length") == 0


def test_control_with_no_net_known_a_figure_under_the_reading_is_taken(entry):
    page, open_ = entry
    open_("gross", initial=0, used=0, unknown=True)
    press(page, "745", 150)
    _prompt_up(page)
    later(page, 700)
    press(page, "245", 150)
    page.wait_for_function("() => window.__saved.length === 1", timeout=5000)
    assert _entry_saved(page) == [{"mode": "gross", "value": 745, "tare": 245, "typed": 245}]


# ---- a double press across the line of weigh questions --------------------------------------------------

PROMPT_THEN_REFILL = r"""() => {
    window.__closedQs = [];
    window.showArchiveEmptyWeightPrompt(8, 5, null, {});
    window.askRefillPlace(6, { place: 'HEAD-1', room: 'LR', held_by: [] },
        { onClosed: (how) => window.__closedQs.push([6, how]) });
}"""

REFILL_THEN_PROMPT = r"""() => {
    window.__closedQs = [];
    window.askRefillPlace(6, { place: 'HEAD-1', room: 'LR', held_by: [] },
        { onClosed: (how) => window.__closedQs.push([6, how]) });
    window.showArchiveEmptyWeightPrompt(8, 5, 245, {});
}"""


def _focus_on(page, el_id):
    page.wait_for_function("(id) => document.activeElement && document.activeElement.id === id", arg=el_id,
                           timeout=5000)


def _filament_writes(page):
    return page.evaluate("() => window.__posts.filter((p) => p.url === '/api/update_filament').map((p) => p.body)")


def test_a_double_escape_on_the_empty_weight_prompt_leaves_the_refill_question_up(wo2):
    """The post-archive prompt, the refill question waiting behind it: two Escapes at
    once close the prompt only. RED on 7a4f9ab (the critic): the second answered the
    refill question unread, #6 left Unassigned."""
    page, _ = wo2
    page.evaluate("() => { delete window.fccQuestionArmMs; }")
    page.evaluate(PROMPT_THEN_REFILL)
    _focus_on(page, "fcc-archive-empty-wt")
    later(page, 900)
    page.keyboard.press("Escape")
    page.keyboard.press("Escape")
    page.wait_for_timeout(200)
    assert page.locator("#fcc-archive-empty-overlay").count() == 0
    assert page.evaluate("() => window.__closedQs") == []
    assert _question_up(page) == 6


def test_control_an_escape_a_moment_later_answers_the_refill_question_behind_the_prompt(wo2):
    page, _ = wo2
    page.evaluate("() => { delete window.fccQuestionArmMs; }")
    page.evaluate(PROMPT_THEN_REFILL)
    _focus_on(page, "fcc-archive-empty-wt")
    later(page, 900)
    page.keyboard.press("Escape")
    _wait_question(page, 6)
    later(page, 800)
    page.keyboard.press("Escape")
    page.wait_for_function("() => !document.getElementById('fcc-refill-place')", timeout=5000)
    assert page.evaluate("() => window.__closedQs") == [[6, "leave"]]


@pytest.mark.parametrize("key", ["Enter", "Escape"])
def test_a_double_key_press_on_the_refill_question_leaves_the_prompt_behind_it_up(wo2, key):
    """The refill question, the post-archive prompt (filled in with 245 g) waiting
    behind it: a double Enter on Leave it Unassigned (or a double Escape) answers the
    refill question only. RED on 7a4f9ab (the critic): the second Enter saved 245 g as
    the filament's empty weight, which every later spool of it inherits, unread (the
    second Escape dismissed the prompt as Later, unread)."""
    page, _ = wo2
    page.evaluate("() => { delete window.fccQuestionArmMs; }")
    page.evaluate(REFILL_THEN_PROMPT)
    _focus_on(page, "fcc-refill-leave")
    later(page, 900)
    page.keyboard.press(key)
    _focus_on(page, "fcc-archive-empty-wt")
    later(page, 120)
    page.keyboard.press(key)
    page.wait_for_timeout(200)
    assert page.evaluate("() => window.__closedQs") == [[6, "leave"]]
    assert page.locator("#fcc-archive-empty-overlay").count() == 1
    assert _filament_writes(page) == []


def test_control_an_enter_a_moment_later_saves_the_prompts_figure(wo2):
    page, _ = wo2
    page.evaluate("() => { delete window.fccQuestionArmMs; }")
    page.evaluate(REFILL_THEN_PROMPT)
    _focus_on(page, "fcc-refill-leave")
    later(page, 900)
    page.keyboard.press("Enter")
    _focus_on(page, "fcc-archive-empty-wt")
    later(page, 800)
    page.keyboard.press("Enter")
    page.wait_for_function("() => window.__posts.some((p) => p.url === '/api/update_filament')", timeout=5000)
    assert _filament_writes(page) == [{"id": 5, "data": {"spool_weight": 245}}]


@pytest.mark.parametrize("key", ["Enter", "Space"])
def test_a_double_key_press_answers_one_refill_question(wo2, key):
    """Two refill questions in line: a double Enter (or Space) on #6's Leave it
    Unassigned answers #6's only; #134's opens with the keyboard on its Leave, and
    stays up. RED on 7a4f9ab: a keyboard's click was let through, and answered #134's
    question unread."""
    page, open_ = wo2
    open_(held=(6, 134))
    page.evaluate("() => { delete window.fccQuestionArmMs; }")
    _two_questions(page)
    later(page, 900)
    page.keyboard.press(key)
    _wait_question(page, 134)
    _focus_on(page, "fcc-refill-leave")
    later(page, 150)
    page.keyboard.press(key)
    page.wait_for_timeout(200)
    assert page.evaluate("() => window.__closedQs") == [[6, "leave"]]
    assert _question_up(page) == 134


def test_control_an_enter_a_moment_later_answers_the_next_question(wo2):
    page, open_ = wo2
    open_(held=(6, 134))
    page.evaluate("() => { delete window.fccQuestionArmMs; }")
    _two_questions(page)
    later(page, 900)
    page.keyboard.press("Enter")
    _wait_question(page, 134)
    _focus_on(page, "fcc-refill-leave")
    later(page, 800)
    page.keyboard.press("Enter")
    page.wait_for_function("() => !document.getElementById('fcc-refill-place')", timeout=5000)
    assert page.evaluate("() => window.__closedQs") == [[6, "leave"], [134, "leave"]]


# ---- Pick a place… with the search panel over a window --------------------------------------------------

@needs_node
def test_over_a_window_the_list_closes_the_search_panel_first(tmp_path):
    """The list is drawn inside the window it was asked over, and a search panel up
    over that window is closed first. RED on 7a4f9ab: the panel stayed open, the list
    drawn in the window under the panel's backdrop and focus trap."""
    res = _real(tmp_path, SEARCH_PANEL + r"""
const host = document.getElementById('manageModal');
host.classList.add('show');
window.promptEditLocation(57, '', { fromCard: true, host });
await __settle(60);
return { order };
""")
    assert res["order"] == ["hide", "fire:manageModal"], res


QUICK_WEIGH_SAVE = r"""
window.__respond = (url) => (url === '/api/spool/update'
    ? { body: { status: 'success', auto_archived: false, needs_empty_weight_prompt: false,
                location_now: '', refill_ask: { place: 'XL-3', room: 'LR', held_by: [] } } }
    : (url === '/api/locations' ? { body: [] } : { body: {} }));
window.saveSpoolWeight(57, null, { used_weight: 600 }, false, null,
                       { archiveSwitch: true, empties: false, wasArchived: true });
"""


@needs_node
def test_a_quick_weigh_from_the_search_panel_over_a_window_closes_the_panel_for_its_list(tmp_path):
    """The Quick-Weigh's save (from a search card, the Location Manager open under the
    search panel) weighs a spool back after it left a head; Pick a place… closes the
    panel and draws the list in the Location Manager. RED on 7a4f9ab: drawn there with
    the panel left open over it."""
    res = _real(tmp_path, SEARCH_PANEL + r"""
const mgr = document.getElementById('manageModal');
mgr.classList.add('show');
document.querySelectorAll = (sel) => (sel === '.modal.show' ? [mgr] : []);
""" + QUICK_WEIGH_SAVE + r"""
await __settle(700);
const q = __overlayEls.filter((el) => el.id === 'fcc-refill-place').pop();
q.querySelector('#fcc-refill-pick').onclick({ type: 'click', detail: 1 });
await __settle(150);
return { order };
""", modules=("inv_details.js", "inv_weigh_out.js"))
    assert res["order"] == ["hide", "fire:manageModal"], res


@needs_node
@pytest.mark.parametrize("on_top", ["spoolModal", "manageModal"])
def test_a_quick_weigh_hands_the_question_the_window_on_top(tmp_path, on_top):
    """Two windows up, the spool window over the Location Manager (or the other way
    round): the question is handed the one on top, by its z-index. RED on 7a4f9ab
    (the spool window on top): the last in the page's order, the Location Manager
    under it. The other order is the control."""
    under = "manageModal" if on_top == "spoolModal" else "spoolModal"
    res = _real(tmp_path, f"""
const top = document.getElementById({json.dumps(on_top)});
const low = document.getElementById({json.dumps(under)});
top.classList.add('show'); top.style.zIndex = '1065';
low.classList.add('show'); low.style.zIndex = '1055';
document.querySelectorAll = (sel) => (sel === '.modal.show'
    ? [document.getElementById('spoolModal'), document.getElementById('manageModal')] : []);
globalThis.getComputedStyle = (el) => ({{ zIndex: (el.style && el.style.zIndex) || 'auto' }});
const asked = [];
window.askRefillPlace = (sid, ask, o) => asked.push(o && o.host ? o.host.id : null);
""" + QUICK_WEIGH_SAVE + """
await __settle(600);
return { asked };
""", modules=("inv_weigh_out.js",))
    assert res["asked"] == [on_top], res


# ---- a place list that couldn't be read ----------------------------------------------------------------

@needs_node
def test_a_place_list_fcc_couldnt_read_asks_again_with_the_reason(tmp_path):
    """Pick a place…, and the list of places doesn't come (an error page): the
    question opens again with the reason on it, since its overlay covers the toast.
    RED on 7a4f9ab: "#57 wasn't moved: ask again, or Leave it Unassigned.", the reason
    only in a 7 s toast under it."""
    res = _real(tmp_path, f"""
window.fetchT = (u, o) => (String(u) === '/api/locations'
    ? Promise.resolve({{ ok: false, status: 502, json: () => Promise.reject(new Error('not JSON')) }})
    : globalThis.fetch(u, o));
window.Swal = {{ fire: () => Promise.resolve({{ isConfirmed: false }}), getPopup: () => null,
                 isVisible: () => false, close() {{}} }};
window.askRefillPlace(57, {json.dumps(ASK)});
await __settle(60);
__overlayEls[0].querySelector('#fcc-refill-pick').onclick({{ type: 'click', detail: 1 }});
await __settle(150);
return {{ again: refills().map((o) => o.content), toasts: __rec.toasts.map((t) => t.msg) }};
""")
    assert len(res["again"]) == 2, res
    assert 'id="fcc-refill-notice"' in res["again"][1] and "read the list of places" in res["again"][1], res


# ---- CMD:CANCEL read twice ---------------------------------------------------------------------------------

def test_a_questions_own_cancel_qr_never_holds_off_the_audits_cancel(wo2):
    """During an audit, a question's own Cancel QR answers it; a bare CMD:CANCEL (the
    dock's Cancel Audit) 600 ms later is a person's next scan, and goes to FCC. RED
    on 7a4f9ab: dropped as "a second read of CMD:CANCEL", its toast under the panel."""
    page, _ = wo2
    page.evaluate("""() => {
        state.auditActive = true;
        window.__qrCancelled = 0;
        const host = document.createElement('div');
        document.body.appendChild(host);
        window.__qr = window.attachConfirmQRs({ host, onConfirm: () => {},
                                                onCancel: () => { window.__qrCancelled += 1; } });
    }""")
    sid = page.evaluate("() => window.__qr.sessionId")
    page.evaluate("(t) => window.processScan(t, 'barcode')", "CMD:CANCEL:" + sid)
    assert page.evaluate("() => window.__qrCancelled") == 1
    later(page, 600)
    page.evaluate("() => window.processScan('CMD:CANCEL', 'barcode')")
    page.wait_for_timeout(150)
    assert "CMD:CANCEL" in _scans(page), _scans(page)


def test_control_a_bare_cancel_read_twice_during_an_audit_is_still_one(wo2):
    """Control (Group 58): during an audit, a bare CMD:CANCEL that closed a question,
    read again 300 ms later, is its double read: it never reaches FCC (where it would
    cancel the audit)."""
    page, _ = wo2
    page.evaluate("""() => {
        state.auditActive = true;
        window.__closedQs = [];
        window.askRefillPlace(6, { place: 'HEAD-1', room: 'LR', held_by: [] },
            { onClosed: (how) => window.__closedQs.push([6, how]) });
    }""")
    _wait_question(page, 6)
    page.evaluate("() => window.processScan('CMD:CANCEL', 'barcode')")
    page.wait_for_function("() => !document.getElementById('fcc-refill-place')", timeout=5000)
    later(page, 300)
    page.evaluate("() => window.processScan('CMD:CANCEL', 'barcode')")
    page.wait_for_timeout(150)
    assert page.evaluate("() => window.__closedQs") == [[6, "leave"]]
    assert _scans(page) == [], _scans(page)


def test_a_cancel_read_twice_says_so_on_the_question_it_left_up(wo2):
    """#6's question is cancelled by a bare CMD:CANCEL; #134's opens; the scanner's
    second read is dropped, and #134's question says why. RED on 7a4f9ab: nothing on
    the question (a log line only), so the scan seemed to do nothing."""
    page, open_ = wo2
    open_(held=(6, 134))
    _two_questions(page)
    page.evaluate("() => window.processScan('CMD:CANCEL', 'barcode')")
    _wait_question(page, 134)
    later(page, 150)
    page.evaluate("() => window.processScan('CMD:CANCEL', 'barcode')")
    page.wait_for_timeout(100)
    note = page.evaluate("() => { const n = document.getElementById('fcc-refill-scan-note');"
                         " return n ? [n.textContent, n.style.display] : null; }")
    assert note == ["Ignored a second read of Cancel: it answered the question before this one. Scan it again "
                    "in a moment to cancel this one.", ""], note
    assert _question_up(page) == 134


PICKER_THEN_QUESTION = r"""() => {
    window.__closedQs = [];
    let pickerOpen = true;
    // The slot picker a refill question's scanned box label opened: its own bare
    // Cancel closes it, and the line goes on to the next question (#134's).
    window.routePickerScan = (t) => {
        if (!pickerOpen) return false;
        if (/CMD:CANCEL$/.test(String(t).toUpperCase())) {
            pickerOpen = false;
            window.askRefillPlace(134, { place: 'HEAD-2', room: 'LR', held_by: [] },
                { onClosed: (how) => window.__closedQs.push([134, how]) });
            return true;
        }
        return 'refused';
    };
}"""


def test_a_cancel_the_slot_picker_took_read_twice_leaves_the_next_question_up(wo2):
    """The slot picker takes its own bare CMD:CANCEL and the next refill question
    opens; the scanner's second read 120 ms later is that Cancel again. RED on 7a4f9ab
    (the critic): it cancelled #134's question unread."""
    page, _ = wo2
    page.evaluate(PICKER_THEN_QUESTION)
    page.evaluate("() => window.processScan('CMD:CANCEL', 'barcode')")
    _wait_question(page, 134)
    later(page, 120)
    page.evaluate("() => window.processScan('CMD:CANCEL', 'barcode')")
    page.wait_for_timeout(150)
    assert page.evaluate("() => window.__closedQs") == []
    assert _question_up(page) == 134


def test_control_a_cancel_a_moment_after_the_pickers_answers_the_next_question(wo2):
    page, _ = wo2
    page.evaluate(PICKER_THEN_QUESTION)
    page.evaluate("() => window.processScan('CMD:CANCEL', 'barcode')")
    _wait_question(page, 134)
    later(page, 1600)
    page.evaluate("() => window.processScan('CMD:CANCEL', 'barcode')")
    page.wait_for_function("() => !document.getElementById('fcc-refill-place')", timeout=5000)
    assert page.evaluate("() => window.__closedQs") == [[134, "leave"]]


# ---- a refill move that fails asks again only once the list is free --------------------------------------

MOVE_REFUSED_HELD = r"""() => {
    const base = window.fetch;
    window.fetch = function (url, opts) {
        url = String(url);
        if (url.includes('/api/locations')) {
            return Promise.resolve({ ok: true, status: 200,
                json: () => Promise.resolve([{ LocationID: 'HEAD-1', Name: 'Head one', Type: 'Tool Head' }]) });
        }
        if (url.includes('/api/manage_contents')) {
            window.__posts.push({ url, body: JSON.parse(opts.body) });
            return new Promise((resolve) => {
                window.__answerMove = () => resolve({ ok: true, status: 200, json: () => Promise.resolve(
                    { status: 'error', msg: 'HEAD-1 holds #99 now: #6 was not moved' }) });
            });
        }
        return base(url, opts);
    };
}"""


def test_a_refill_move_that_fails_never_takes_the_keyboard_from_a_spool_scanned_meanwhile(wo2):
    """#6, weighed back, goes Back on HEAD-1; while that move is out, #57 is scanned
    into the list and its box takes the keyboard; the move is refused. The question
    isn't asked again over #57's box (a spool was scanned since the save: a note says
    where #6 came off), and #57's reading is saved. RED on 7a4f9ab (the critic): the
    question asked again at once, took the keyboard, and #57's reading went out as a
    scan."""
    page, open_ = wo2
    page.evaluate(MOVE_REFUSED_HELD)
    page.evaluate("() => { window.__refillFor[6] = { place: 'HEAD-1', room: '', held_by: [] }; }")
    open_(held=(6, 134))
    press(page, "300", 150)
    _saved(page)
    page.wait_for_function("() => !!document.getElementById('fcc-refill-back')", timeout=5000)
    later(page, 900)
    page.locator("#fcc-refill-back").click()
    page.wait_for_function("() => typeof window.__answerMove === 'function'", timeout=5000)
    press(page, "ID:57", 5)
    _answered(page, 57)
    page.wait_for_function("() => document.activeElement && document.activeElement.dataset"
                           " && document.activeElement.dataset.id === '57'", timeout=5000)
    page.evaluate("() => window.__answerMove()")
    page.wait_for_timeout(400)
    assert page.locator("#fcc-refill-place").count() == 0
    assert _focus(page) == "57", _focus(page)
    later(page, 900)
    press(page, "450", 150)
    _saved(page, 2)
    ups = _updates(page)
    assert [u["id"] for u in ups] == [6, 57], ups
    assert ups[1]["updates"]["used_weight"] == 300, ups
