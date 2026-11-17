"""Group 62.4: a question's keys and Tab stay with what is on screen, hermetic.

- window.confirmActivePrint heard its keys on its own overlay. A click on the question's
  words or background moves the focus to the page, so Enter and the arrows reached
  nothing while its hint still said what Enter does, and Tab walked the page behind it
  (Done's question included): only Escape (mountOverlay's) and the mouse answered it. The
  "Record it as coming from…" question had the same shape (found 2026-11-02, Group 58's
  re-review).
- mountOverlay's trapTab was opt-in: Tab walked out of Bulk Move's panel, the
  empty-weight prompt and most other overlays onto the page behind.

Now the two questions hear their keys on the document while they are on top (the ⌨️
list down); Tab from anywhere comes back into them; in the yes / no an Enter on no button
cancels, as its hint says; and the hint says what Enter does once the focus has left.
trapTab is the default, and the four overlays that cycle Tab themselves opt out
(tests/test_overlay_tab_canary.py), so one Tab moves one step there.

The real overlay_mount.js, inv_core.js, ui_builder.js, inv_cmd.js, inv_details.js,
slot_picker.js and inv_quickswap.js in `isolated_page` (no network), real clicks and real
keys, so it runs under --offline. RED on 697bc4f unless a test says it pins what was right.
"""
from __future__ import annotations

import pytest

from test_slow_scan_confirms_js import BOX_MODEL, MODULES

PAGE = """<!doctype html><html><head><meta charset="utf-8"></head><body>
<button id="behind-1">behind 1</button><input id="behind-field"><button id="behind-2">behind 2</button>
</body></html>"""

STUBS = r"""
window.__said = [];
window.__models = {};
window.fetch = function (url, opts) {
    url = String(url);
    let ans = {};
    if (url.includes('/api/placement_options')) {
        const loc = (new URL(url, 'http://x/')).searchParams.get('location');
        ans = window.__models[loc] || { read_ok: false, read_error: 'no model' };
    } else if (url.startsWith('/api/filament_details')) {
        ans = { id: 7, name: 'Red', material: 'PLA', vendor: { id: 3, name: 'Some Brand' } };
    }
    return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(JSON.parse(JSON.stringify(ans))),
                             text: () => Promise.resolve(JSON.stringify(ans)) });
};
window.__si = window.setInterval; window.setInterval = () => 0;
"""

ASK = r"""(kind) => {
    window.__said = [];
    const rec = (w) => () => window.__said.push(w);
    if (kind === 'yes-no') return void window.confirmActivePrint({
        activePrint: { toolhead: 'XL-3', printer_name: 'XL', state: 'PRINTING' },
        msg: 'Moving #57 now will disrupt the print. Continue?', onConfirm: rec('yes'), onCancel: rec('no') });
    if (kind === 'three-way') return void window.confirmActivePrint({
        title: 'Load #57 onto XL-1?', msg: 'LR-MDB-1 slot 1 feeds XL-1, and XL-1 runs #99.',
        loadLabel: 'Load it instead', storeLabel: 'Just store it in LR-MDB-1 slot 1',
        onConfirm: rec('load'), onStore: rec('store'), onCancel: rec('no') });
    // Done's question's shape (askAuditDone): tiles, no store, its own Cancel words.
    window.confirmActivePrint({
        title: 'Park 2 at Unknown?', msg: 'The 2 not scanned go to Unknown.', printing: false,
        cancelLabel: 'Back to the audit', cancelVerb: 'goes back', loadVerb: 'parks them', loadLabel: 'Park them',
        onConfirm: rec('park'), onCancel: rec('back'),
        sections: [{ heading: 'Not scanned (2)', tiles: true, tone: 'missing',
                     lines: [{ text: '#1 PLA Red', detail: '500g' }, { text: '#2 PETG Blue', detail: '300g' }] }] });
}"""

# What Enter does with the focus on no button: the yes / no and Done's question cancel
# (Done's goes back), the three-way stores.
ENTER_AWAY = {"yes-no": "no", "three-way": "store", "tiles": "back"}
FIRST = {"yes-no": "Continue Anyway", "three-way": "Load it instead", "tiles": "Park them"}
KINDS = list(ENTER_AWAY)


@pytest.fixture
def kpage(isolated_page):
    page = isolated_page
    page.set_content(PAGE)
    page.add_script_tag(content=STUBS)
    for name in ("overlay_mount.js", "inv_core.js", "ui_builder.js", "inv_cmd.js", "inv_details.js",
                 "slot_picker.js", "inv_quickswap.js"):
        page.add_script_tag(content=(MODULES / name).read_text(encoding="utf-8"))
    page.evaluate("() => { window.setInterval = window.__si; }")
    return page


def _focused(page):
    return page.evaluate("""() => { const a = document.activeElement;
        if (!a || a === document.body) return 'body';
        return a.id || (a.textContent || '').trim().split('\\n')[0].trim() || a.tagName; }""")


def _open(page, kind):
    page.evaluate(ASK, kind)
    page.wait_for_selector("#fcc-active-print-confirm-overlay .fcc-apc-no")
    page.wait_for_function("() => document.activeElement && document.activeElement.closest('#fcc-active-print-confirm-overlay')")


def _click_words(page, sel="#fcc-active-print-confirm-overlay .fcc-apc-msg"):
    page.click(sel)
    assert _focused(page) == "body", "precondition: a click on the words moves the focus to the page"


@pytest.mark.parametrize("kind", KINDS)
def test_enter_still_answers_after_a_click_on_the_questions_words(kpage, kind):
    """RED on 697bc4f: the Enter reached nothing, and the question stayed up."""
    page = kpage
    _open(page, kind)
    _click_words(page)
    page.keyboard.press("Enter")
    page.wait_for_timeout(50)
    assert page.evaluate("() => window.__said") == [ENTER_AWAY[kind]]
    assert page.locator("#fcc-active-print-confirm-overlay").count() == 0


@pytest.mark.parametrize("kind", KINDS)
def test_tab_from_the_page_comes_back_into_the_question_and_wraps(kpage, kind):
    """RED on 697bc4f: Tab walked to the page's own controls behind the question."""
    page = kpage
    _open(page, kind)
    _click_words(page)
    page.keyboard.press("Tab")
    assert _focused(page) == FIRST[kind]
    seen = [FIRST[kind]]
    for _ in range(4):
        page.keyboard.press("Tab")
        seen.append(_focused(page))
    assert not any(s.startswith("behind") for s in seen), seen
    assert seen[0] in seen[1:], f"Tab never wrapped: {seen}"
    _click_words(page)
    page.keyboard.press("Shift+Tab")
    last = {"yes-no": "Cancel", "three-way": "Cancel", "tiles": "Back to the audit"}[kind]
    assert _focused(page) == last
    assert page.evaluate("() => window.__said") == []


def test_the_three_ways_arrows_come_back_after_a_click_on_its_words(kpage):
    """RED on 697bc4f: ← and → went to the page."""
    page = kpage
    _open(page, "three-way")
    _click_words(page)
    page.keyboard.press("ArrowRight")
    assert _focused(page) == "Load it instead"
    page.keyboard.press("ArrowRight")
    assert _focused(page).startswith("Just store it")


def test_the_hint_says_what_enter_does_once_the_focus_has_left(kpage):
    """With the focus on Continue Anyway the hint says Enter continues; after a click on
    the words, where Enter cancels, it says so. RED on 697bc4f: it went on saying
    "Enter continues", and the Enter did nothing."""
    page = kpage
    _open(page, "yes-no")
    page.keyboard.press("Shift+Tab")              # Cancel -> Continue Anyway
    hint = page.locator("#fcc-active-print-confirm-overlay .fcc-apc-hint")
    assert "Enter continues" in hint.text_content()
    _click_words(page)
    assert "Enter cancels" in hint.text_content()


def test_a_second_question_on_top_takes_the_keys_from_the_first(kpage):
    """"While it is on top": two questions open on two ids, the newer on top; Enter on no
    button answers only the newer one, and the older stays. RED on 697bc4f: the Enter
    reached neither."""
    page = kpage
    page.evaluate("""() => {
        window.__said = [];
        window.confirmActivePrint({ activePrint: { printer_name: 'XL', state: 'PRINTING' }, msg: 'A?',
            ids: { overlay: 'fcc-q-a' }, onConfirm: () => window.__said.push('a-yes'), onCancel: () => window.__said.push('a-no') });
        window.confirmActivePrint({ activePrint: { printer_name: 'XL', state: 'PRINTING' }, msg: 'B?',
            ids: { overlay: 'fcc-q-b' }, onConfirm: () => window.__said.push('b-yes'), onCancel: () => window.__said.push('b-no') }); }""")
    page.wait_for_selector("#fcc-q-b .fcc-apc-no")
    _click_words(page, "#fcc-q-b .fcc-apc-msg")
    page.keyboard.press("Enter")
    page.wait_for_timeout(50)
    assert page.evaluate("() => window.__said") == ["b-no"]
    assert page.locator("#fcc-q-a").count() == 1


# --- "Record it as coming from…" --------------------------------------------------------

RECORD = r"""() => { window.__rs = undefined;
    _askRecordSource({ head: 'XL-1', spool_location: '', feeds: [
        { box: 'LR-MDB-1', slot: '1', free: true },
        { box: 'LR-MDB-1', slot: '2', free: false, claimed_by: 99 }] }, 57, null)
      .then((r) => { window.__rs = r; }); }"""


def test_the_record_source_questions_keys_work_after_a_click_on_its_words(kpage):
    """After a click on its words: ← / → and Tab come back into it, and an Enter on no
    answer brings the keyboard back to the slot it opened on, choosing nothing; the next
    Enter chooses that slot. RED on 697bc4f: every key reached the page."""
    page = kpage
    page.evaluate(RECORD)
    page.wait_for_selector("#fcc-record-source .fcc-rs-none")
    _click_words(page, "#fcc-record-source .fcc-rs-msg")
    page.keyboard.press("ArrowRight")
    assert _focused(page).startswith("LR-MDB-1 slot 1")
    _click_words(page, "#fcc-record-source .fcc-rs-msg")
    page.keyboard.press("Tab")
    assert _focused(page).startswith("LR-MDB-1 slot 1")
    _click_words(page, "#fcc-record-source .fcc-rs-msg")
    page.keyboard.press("Enter")
    page.wait_for_timeout(50)
    assert page.evaluate("() => window.__rs") is None and _focused(page).startswith("LR-MDB-1 slot 1")
    page.keyboard.press("Enter")
    page.wait_for_function("() => window.__rs !== undefined")
    assert page.evaluate("() => window.__rs") == {"box": "LR-MDB-1", "slot": "1"}


# --- trapTab, the default -----------------------------------------------------------------

def test_tab_stays_inside_an_overlay_by_default_and_an_opt_out_lets_it_go(kpage):
    """RED on 697bc4f: from the overlay's last button Tab walked out of it."""
    page = kpage
    page.evaluate("""() => { window.__h = window.mountOverlay({ id: 'fcc-t',
        content: '<div><button id="t1">one</button><button id="t2">two</button></div>', initialFocus: '#t1' }); }""")
    page.wait_for_function("() => document.activeElement && document.activeElement.id === 't1'")
    page.keyboard.press("Tab")
    assert _focused(page) == "t2"
    page.keyboard.press("Tab")
    assert _focused(page) == "t1"
    page.keyboard.press("Shift+Tab")
    assert _focused(page) == "t2"
    page.focus("#behind-1")                           # a focus left behind it comes back
    page.keyboard.press("Tab")
    assert _focused(page) == "t1"
    page.evaluate("""() => { window.__h.cleanup(); window.__h = window.mountOverlay({ id: 'fcc-t',
        content: '<div><button id="t1">one</button><button id="t2">two</button></div>',
        initialFocus: '#t2', trapTab: false }); }""")
    page.wait_for_function("() => document.activeElement && document.activeElement.id === 't2'")
    page.keyboard.press("Tab")
    assert _focused(page) != "t1", "trapTab: false still trapped Tab"


def test_the_empty_weight_prompt_keeps_tab_inside(kpage):
    """Group 54's review, R6: after Save weight, Tab walked onto the dashboard. RED on
    697bc4f: Tab from its last button left the prompt."""
    page = kpage
    page.evaluate("() => window.showArchiveEmptyWeightPrompt(57, 7, null, {})")
    page.wait_for_selector("#fcc-archive-empty-overlay #fcc-archive-save")
    seen = []
    for _ in range(6):
        page.keyboard.press("Tab")
        seen.append(page.evaluate("() => !!document.activeElement.closest('#fcc-archive-empty-overlay')"))
    assert all(seen), seen


# --- the four that cycle Tab themselves: one Tab, one step --------------------------------

def test_one_tab_moves_one_step_in_the_quickswap_confirm(kpage):
    """A pin for the opt-out: with trapTab on too, Tab from Yes went to No and back again
    (two handlers), so the focus never moved."""
    page = kpage
    page.evaluate("""() => {
        window.checkPrinterForHead = () => Promise.resolve({ active: false, known: true, state: 'IDLE', printer_name: 'XL' });
        const b = document.createElement('button');
        Object.assign(b.dataset, { toolhead: 'XL-1', box: 'LR-MDB-1', slot: '1', spoolId: '57' });
        window.quickSwapTap(b); }""")
    page.wait_for_function("() => document.activeElement && document.activeElement.id === 'fcc-quickswap-yes'")
    page.keyboard.press("Tab")
    assert _focused(page) == "fcc-quickswap-no"
    page.keyboard.press("Tab")
    assert _focused(page) == "fcc-quickswap-yes"


def test_one_tab_moves_one_step_in_the_slot_picker_and_a_field_behind_tabs_into_it(kpage):
    """One Tab moves one tile (a pin for the opt-out), and with the focus on a field
    behind the picker, Tab comes into it. RED on 697bc4f for the field: Tab went on
    through the page behind (D1 let it through)."""
    page = kpage
    page.evaluate("(m) => { window.__models = { 'CR-MDB-1': m }; window.__picked = undefined;"
                  " window.openSlotPicker({ location: 'CR-MDB-1', spool: 6 }).then((r) => { window.__picked = r; }); }",
                  BOX_MODEL)
    page.wait_for_function("() => document.querySelectorAll('#fcc-slot-picker .fcc-sp-tile').length > 0")
    page.wait_for_function("() => document.activeElement && document.activeElement.classList.contains('fcc-sp-tile')")
    at = page.evaluate("() => document.activeElement.dataset.spIdx")
    page.keyboard.press("Tab")
    assert page.evaluate("() => document.activeElement.dataset.spIdx") == str(int(at) + 1)
    page.focus("#behind-field")
    page.keyboard.press("Tab")
    assert page.evaluate("() => !!document.activeElement.closest('#fcc-slot-picker')"), _focused(page)
