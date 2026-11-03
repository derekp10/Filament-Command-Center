"""Group 58, build spec section 7: Done's question on a real DOM, hermetic: the REAL
overlay_mount.js, inv_core.js, inv_cmd.js and inv_loose.js, the real scan accumulator
and global.css, in `isolated_page` (no route to any network), so it runs under
--offline. test_audit_done_question_58_js.py has its logic on the real routes'
answers; test_audit_done_question_58_e2e.py the real dashboard, with Bootstrap.

What a stub DOM can't say: what is really on top, where the keyboard really is, what
a real Enter does, and whether the QRs are still on screen.

RED on f59485a unless a test says it pins what was already right.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from test_audit_done_question_58_js import asked  # noqa: F401  (asked: the fixture)
from test_audit_panel_58_js import CANCEL, DONE, NOTICE, PANEL, _on_top, audit  # noqa: F401  (audit: the fixture)
from test_audit_session_58 import env  # noqa: F401  (env: the fixture)
from test_scanner_safe_dialogs_61_js import page61  # noqa: F401  (page61: the fixture)
from test_text_size_guard import SAMPLE_QUESTION

HUB = Path(__file__).resolve().parent.parent
QUESTION = "#fcc-audit-done-question"
SHEET = QUESTION + " .fcc-apc-panel"
YES = QUESTION + " .fcc-apc-yes"
BACK = QUESTION + " .fcc-apc-no"
STATUS = QUESTION + " .fcc-apc-status"
HINT = QUESTION + " .fcc-apc-hint"
QRS = QUESTION + " .fcc-confirm-qr-row"
LOOSE_BTN = "#fcc-audit-panel-loose"
LOOSE = "#fcc-loose-list"


def _question(park=3, stays=0, file=0):
    """/api/identify_scan's audit_done_question, as pinned by
    test_the_samples_shape_is_the_routes below. `file`: how many Extras Done files
    here (Derek's C3), from LR-MDB-2, so the multi-slot box's words come with them.
    PIN UPDATED DELIBERATELY (review of 7e3720f, S-7): the words name the real gesture."""
    note = {0: "", 1: "It goes in with no slot: scan it, then its slot's label, to set one."}.get(
        file, "They go in with no slot: scan each one, then its slot's label, to set it.")
    return {"type": "audit_done_question", "audit_id": "boot-1", "location": "LR-MDB-1", "found": 2,
            "expected": 2 + park + stays,
            "park": [{"id": 100 + n, "display": f"#{100 + n} Some Brand PLA (Red {n})",
                      "where": f"LR-MDB-1 slot {n + 1}", "slot": str(n + 1)} for n in range(park)],
            "stays": [{"id": 300 + n, "display": f"#{300 + n} Some Brand PETG (Clear {n})", "where": "XL-4",
                       "why": "moved to XL-4"} for n in range(stays)],
            "file": [{"id": 200 + n, "display": f"#{200 + n} Some Brand PLA (Blue {n})",
                      "where": f"LR-MDB-2 slot {n + 1}"} for n in range(file)],
            "file_note": note}


PARKED = {"success": True, "parked": [100, 101, 102], "filed": [], "stayed": [], "failed": [],
          "msg": "Parked 3 spools at Unknown. Undo Last Move puts them back.",
          "audit_ended": {"id": "boot-1", "why": "done"}}


def test_the_samples_shape_is_the_routes(asked):
    """Pins the samples, here and in the guards, to the real route's answers."""
    real = asked["question"]
    for sample in (_question(stays=1), SAMPLE_QUESTION):
        assert set(sample) == set(real) and sample["type"] == real["type"]
        assert set(sample["park"][0]) == set(real["park"][0]) and set(sample["stays"][0]) == set(real["stays"][0])
    assert set(PARKED) == set(asked["parked"])


def test_the_samples_file_rows_are_the_routes(env):
    """Derek's C3: the question's Extras, from a real Done, against both samples.
    Pins the shape C added."""
    from test_audit_session_58 import add_spool, scan, start
    add_spool(env, 1, "LR-MDB-1", container_slot="1")
    add_spool(env, 200, "LR-MDB-2", container_slot="1")
    start(env, "LR-MDB-1")
    scan(env, "ID:1")
    scan(env, "ID:200")
    real = scan(env, "CMD:DONE")
    assert real["file"] == [{"id": 200, "display": "#200 Some Brand PLA (Red)", "where": "LR-MDB-2 slot 1"}]
    for sample in (_question(file=1), SAMPLE_QUESTION):
        assert set(sample["file"][0]) == set(real["file"][0])
        assert sample["file_note"] == real["file_note"]


@pytest.fixture
def dialog(audit):
    """`audit`, with Done answered by the route's question and /api/audit/park by
    `window.__park`, its requests in `window.__parks`."""
    page = audit
    page.add_script_tag(content=(HUB / "static" / "js" / "modules" / "inv_loose.js").read_text(encoding="utf-8"))
    page.evaluate("""([question, parked]) => {
        window.__answers['CMD:DONE'] = question;
        window.__park = parked;
        window.__parks = [];
        const answers = window.fetch;
        window.fetch = (url, opts) => {
            if (String(url).indexOf('/api/audit/park') !== -1) {
                window.__parks.push(JSON.parse(opts.body));
                return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(window.__park) });
            }
            if (String(url).indexOf('/api/loose_spools') !== -1) {
                return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ read_ok: true, read_error: null, count: 1,
                    places: [{ id: 'LR', name: 'Living Room', type: 'Room', spools: [{ id: 5, display: '#5 A spool', color: '72071C',
                        color_direction: 'longitudinal', remaining_weight: 500 }] }] }) });
            }
            return answers(url, opts);
        };
    }""", [_question(), PARKED])
    return page


def _ask(page):
    page.click(DONE)
    page.wait_for_function("(sel) => document.activeElement === document.querySelector(sel)", arg=BACK)


def _active(page):
    return page.evaluate("document.activeElement.id || document.activeElement.className")


def _scans(page):
    return [s["text"] for s in page.evaluate("window.__ids")]


def _closed(page):
    page.wait_for_selector(QUESTION, state="detached")


def _past_a_double_press(page):
    """DOUBLE_PRESS_MS (inv_cmd.js): the question's yes takes no click that long after
    it opens, and the panel none that long after it goes."""
    page.wait_for_timeout(720)


def _yes(page):
    """A person who has read the question. PIN UPDATED DELIBERATELY (Group 58 review):
    a click right after it opened was the second click of a double click on Done."""
    _past_a_double_press(page)
    page.click(YES)


def test_the_question_draws_above_the_panel(dialog):
    """Hit tests. #confirmModal would have drawn behind it (z 1100 against 20000)."""
    _ask(dialog)
    assert _on_top(dialog, YES) and _on_top(dialog, BACK)
    box = dialog.evaluate("""(sel) => { const r = document.querySelector(sel).getBoundingClientRect();
        const hit = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
        return !!hit.closest('#fcc-audit-done-question'); }""", DONE)
    assert box                                   # the panel's Done is under its backdrop
    assert dialog.evaluate("(sel) => window.isTopOverlay(document.querySelector(sel))", QUESTION)


def test_it_opens_on_back_to_the_audit_and_the_hint_says_what_enter_does(dialog):
    _ask(dialog)
    assert dialog.text_content(BACK) == "Back to the audit" and dialog.text_content(YES) == "Park them"
    assert dialog.text_content(HINT) == "Enter goes back · Esc goes back"
    dialog.keyboard.press("Tab")                 # from the last button, round to the first
    assert dialog.evaluate("(sel) => document.activeElement === document.querySelector(sel)", YES)
    assert dialog.text_content(HINT) == "Enter parks them · Esc goes back"
    dialog.keyboard.press("ArrowRight")
    assert dialog.evaluate("(sel) => document.activeElement === document.querySelector(sel)", BACK)
    assert dialog.text_content(HINT) == "Enter goes back · Esc goes back"


def test_enter_goes_back_and_the_keyboard_lands_on_done(dialog):
    _ask(dialog)
    dialog.keyboard.press("Enter")
    _closed(dialog)
    assert dialog.evaluate("window.__parks") == []
    assert dialog.is_visible(DONE) and dialog.evaluate("state.auditActive") is True
    assert _active(dialog) == DONE[1:]


def test_escape_goes_back_and_leaves_the_panel_up(dialog):
    _ask(dialog)
    dialog.keyboard.press("Escape")
    _closed(dialog)
    assert dialog.is_visible(DONE) and dialog.evaluate("window.__parks") == []


def test_a_held_enter_does_nothing(dialog):
    """The Enter that pressed Done, held: its repeats reach the question. Chrome
    clicks a focused button on each one, so a key held a moment too long used to
    answer the next dialog under it."""
    dialog.focus(DONE)
    dialog.keyboard.down("Enter")
    dialog.wait_for_function("(sel) => document.activeElement === document.querySelector(sel)", arg=BACK)
    for _ in range(3):
        dialog.keyboard.down("Enter")            # a repeat
    dialog.wait_for_timeout(120)
    assert dialog.is_visible(QUESTION) and dialog.evaluate("window.__parks") == []
    dialog.keyboard.up("Enter")
    assert dialog.is_visible(QUESTION)


def test_a_held_enter_on_park_it_parks_once(dialog):
    _ask(dialog)
    dialog.focus(YES)
    dialog.keyboard.down("Enter")
    dialog.keyboard.down("Enter")
    dialog.keyboard.up("Enter")
    dialog.wait_for_selector(PANEL, state="detached")
    assert len(dialog.evaluate("window.__parks")) == 1


@pytest.mark.parametrize("on", [BACK, YES], ids=["on-back", "on-park-them"])
def test_a_scans_enter_presses_nothing(dialog, on):
    """Wherever the focus is. The scan itself is held off and says why."""
    _ask(dialog)
    dialog.focus(on)
    dialog.keyboard.type("ID:57", delay=0)
    dialog.keyboard.press("Enter")
    dialog.wait_for_selector(STATUS, state="visible")
    assert dialog.is_visible(QUESTION) and dialog.evaluate("window.__parks") == []
    assert _scans(dialog) == ["CMD:DONE"]
    assert "Park them or Back to the audit" in dialog.text_content(STATUS)
    assert "(Ignored: ID:57)" in dialog.text_content(STATUS)


def test_a_slow_scanners_enter_presses_nothing(dialog):
    """Its keys arrive over more than 500 ms, past "a scan in flight". Its Enter still
    isn't a person's: two characters are in the scan buffer."""
    _ask(dialog)
    dialog.keyboard.type("ID:57", delay=150)
    dialog.keyboard.press("Enter")
    dialog.wait_for_selector(STATUS, state="visible")
    assert dialog.is_visible(QUESTION) and dialog.evaluate("window.__parks") == []


def test_the_qrs_answer_it(dialog):
    """Read through the real accumulator, as a scanner types them."""
    _ask(dialog)
    sid = dialog.evaluate("Object.keys(window._fccActiveConfirms).pop()")
    dialog.keyboard.type(f"CMD:CANCEL:{sid}", delay=0)
    dialog.keyboard.press("Enter")
    _closed(dialog)
    assert dialog.evaluate("window.__parks") == [] and dialog.is_visible(DONE)
    _past_a_double_press(dialog)                 # and the scanner's CR LF window
    _ask(dialog)
    sid = dialog.evaluate("Object.keys(window._fccActiveConfirms).pop()")
    dialog.keyboard.type(f"CMD:CONFIRM:{sid}", delay=0)
    dialog.keyboard.press("Enter")
    dialog.wait_for_selector(PANEL, state="detached")
    parks = dialog.evaluate("window.__parks")
    assert len(parks) == 1 and parks[0]["ids"] == [100, 101, 102] and parks[0]["audit_id"] == "boot-1"


def test_the_qrs_are_captioned_and_stand_under_their_buttons(dialog):
    _ask(dialog)
    cells = dialog.evaluate("""() => Array.from(document.querySelectorAll('#fcc-audit-done-question .fcc-confirm-qr-cell'))
        .map((c) => { const r = c.getBoundingClientRect(); return { role: c.dataset.qr, text: c.textContent.trim(),
            middle: r.left + r.width / 2, tone: c.dataset.qrTone }; })""")
    buttons = dialog.evaluate("""() => ['.fcc-apc-yes', '.fcc-apc-no'].map((s) => {
        const r = document.querySelector('#fcc-audit-done-question ' + s).getBoundingClientRect();
        return r.left + r.width / 2; })""")
    assert [(c["role"], c["text"], c["tone"]) for c in cells] == [("confirm", "📷 Scan to Park", "warning"),
                                                                  ("cancel", "📷 Scan to go back", "secondary")]
    assert abs(cells[0]["middle"] - buttons[0]) <= 1 and abs(cells[1]["middle"] - buttons[1]) <= 1


def test_a_second_done_is_refused_and_the_question_says_why(dialog):
    """The toast sits under the question, so the refusal is on it, on top."""
    _ask(dialog)
    dialog.evaluate("window.processScan('CMD:DONE', 'barcode')")
    dialog.wait_for_selector(STATUS, state="visible")
    assert _on_top(dialog, STATUS)
    assert dialog.text_content(STATUS).startswith("Answer the question on screen first: Park them or Back to the audit")
    assert _scans(dialog) == ["CMD:DONE"]
    assert dialog.locator(QUESTION).count() == 1


def test_a_bare_cmd_cancel_closes_only_the_question(dialog):
    _ask(dialog)
    dialog.keyboard.type("CMD:CANCEL", delay=0)
    dialog.keyboard.press("Enter")
    _closed(dialog)
    assert dialog.is_visible(DONE) and dialog.evaluate("state.auditActive") is True
    assert _scans(dialog) == ["CMD:DONE"]


def test_close_audit_panel_closes_an_open_question(dialog):
    _ask(dialog)
    sid = dialog.evaluate("Object.keys(window._fccActiveConfirms).pop()")
    dialog.evaluate("window.closeAuditPanel()")
    _closed(dialog)
    assert not dialog.locator(PANEL).count()
    assert dialog.evaluate("Object.keys(window._fccActiveConfirms)") == []
    dialog.evaluate("(sid) => window.processScan('CMD:CONFIRM:' + sid, 'barcode')", sid)   # a late read of its QR
    dialog.wait_for_timeout(120)
    assert dialog.evaluate("window.__parks") == []


def test_a_refused_yes_hands_the_keyboard_back_to_done_and_says_why_on_top(dialog):
    """Nothing was written, and the audit runs on. Pressing Done again has to work
    from where the person is."""
    words = "Couldn't read LR-MDB-1 from Spoolman, so nothing was moved. Try Done again in a moment."
    dialog.evaluate("(msg) => { window.__park = { success: false, msg }; }", words)
    _ask(dialog)
    _yes(dialog)
    dialog.wait_for_function("([sel, words]) => document.querySelector(sel).textContent === words", arg=[NOTICE, words])
    assert _on_top(dialog, NOTICE)
    dialog.wait_for_function("(sel) => !document.querySelector(sel).disabled", arg=DONE)
    assert _active(dialog) == DONE[1:]
    assert dialog.is_enabled(CANCEL)
    assert dialog.evaluate("state.processing") is False


def test_a_park_that_landed_leaves_no_panel_no_question_and_no_dim(dialog):
    _ask(dialog)
    _yes(dialog)
    dialog.wait_for_selector(PANEL, state="detached")
    assert not dialog.locator(QUESTION).count()
    assert dialog.evaluate("state.processing") is False and dialog.evaluate("state.auditActive") is False
    assert dialog.evaluate("getComputedStyle(document.getElementById('processing-overlay')).display") == "none"
    assert PARKED["msg"] in dialog.evaluate(
        "Array.from(document.querySelectorAll('#toast-container .toast-msg')).map((e) => e.textContent)")


# --- the window it has -------------------------------------------------------------

def _measure(page):
    return page.evaluate("""([sheet, qrs]) => { const p = document.querySelector(sheet);
        const s = p.getBoundingClientRect(), q = document.querySelector(qrs).getBoundingClientRect();
        return { top: s.top, bottom: s.bottom, left: s.left, right: s.right, qrTop: q.top, qrBottom: q.bottom,
                 vh: innerHeight, vw: document.documentElement.clientWidth,
                 scrolls: p.classList.contains('fcc-question-scroll'), wide: p.scrollWidth > p.clientWidth + 1 }; }""",
                         [SHEET, QRS])


def _show(page, park, stays):
    page.evaluate("(q) => window.askAuditDone(q)", _question(park, stays))
    page.wait_for_selector(QRS)
    page.wait_for_timeout(120)                   # the QR codes draw two frames later


@pytest.mark.parametrize("park, stays", [(20, 0), (10, 10), (20, 12), (40, 40)])
def test_twenty_spools_fit_with_the_qrs_in_view_on_a_small_laptop(dialog, park, stays):
    """A long list must stay short: a scanner can't read a QR that has scrolled away.
    However the spools split between the lists, the height is one list's."""
    dialog.set_viewport_size({"width": 1366, "height": 768})
    _show(dialog, park, stays)
    m = _measure(dialog)
    assert not m["scrolls"], m
    assert m["top"] >= 0 and m["bottom"] <= m["vh"], m
    assert m["qrBottom"] <= m["vh"], m
    assert _on_top(dialog, BACK) and _on_top(dialog, YES)
    tops = dialog.evaluate("""() => Array.from(document.querySelectorAll('#fcc-audit-done-question .fcc-apc-section'))
        .map((s) => Math.round(s.getBoundingClientRect().top))""")
    assert len(tops) == (2 if stays else 1) and len(set(tops)) == 1, tops     # side by side


def test_a_question_taller_than_a_phone_scrolls_whole_and_never_sideways(dialog):
    """fccFitQuestion: top and bottom never cut. The lists go one above the other."""
    dialog.set_viewport_size({"width": 360, "height": 640})
    _show(dialog, 20, 12)
    m = _measure(dialog)
    assert m["scrolls"] and m["left"] >= 0 and m["right"] <= m["vw"] and not m["wide"], m
    dialog.evaluate("(sel) => { const p = document.querySelector(sel); p.scrollTop = p.scrollHeight; }", SHEET)
    m = _measure(dialog)
    assert m["qrBottom"] <= m["vh"], m


def test_a_long_name_stays_on_one_line_and_its_reason_stays_whole(dialog):
    """The name gives way, and its full text is in the line's title."""
    name = "#300 " + "A very long maker's name " * 6 + "PETG (Clear)"
    question = _question(1, 1)
    question["stays"][0].update(display=name, why="moved to LR-MDB-2 slot 3")
    dialog.evaluate("(q) => window.askAuditDone(q)", question)
    dialog.wait_for_selector(QRS)
    line = dialog.evaluate("""() => { const l = document.querySelectorAll('#fcc-audit-done-question .fcc-apc-line')[1];
        const w = l.querySelector('.fcc-apc-line-where');
        return { high: l.getBoundingClientRect().height, title: l.title, whole: w.scrollWidth <= w.clientWidth,
                 sheetWide: document.querySelector('#fcc-audit-done-question .fcc-apc-panel').getBoundingClientRect().width }; }""")
    assert line["high"] < 30 and line["whole"] and line["title"] == f"{name} · moved to LR-MDB-2 slot 3"
    assert line["sheetWide"] == 800              # the two-list width: the name didn't widen it


# --- the Loose spools list, from the panel ------------------------------------------

def test_the_loose_list_opens_from_the_panel_on_top_and_escape_closes_only_it(dialog):
    dialog.click(LOOSE_BTN)
    dialog.wait_for_selector(LOOSE + " .fcc-loose-row.kb-active")
    assert _on_top(dialog, LOOSE + " .fcc-loose-panel")
    dialog.keyboard.press("Enter")               # a row opens nothing during an audit
    dialog.wait_for_timeout(60)
    assert dialog.locator(LOOSE).count() == 1
    dialog.keyboard.press("Escape")
    dialog.wait_for_selector(LOOSE, state="detached")
    assert dialog.is_visible(DONE)
    assert _active(dialog) == LOOSE_BTN[1:]      # back to the button that opened it


def test_the_audit_ending_takes_the_panels_loose_list_with_it(dialog):
    dialog.click(LOOSE_BTN)
    dialog.wait_for_selector(LOOSE + " .fcc-loose-row.kb-active")
    dialog.evaluate("window.closeAuditPanel()")
    dialog.wait_for_selector(LOOSE, state="detached")


def test_a_list_opened_elsewhere_stays_when_a_hidden_panels_audit_ends(dialog):
    """The Locations window's own list has its own parent."""
    dialog.click(LOOSE_BTN)
    dialog.wait_for_selector(LOOSE + " .fcc-loose-row.kb-active")
    dialog.keyboard.press("Escape")
    dialog.wait_for_selector(LOOSE, state="detached")
    dialog.evaluate("window.openLooseList({})")
    dialog.wait_for_selector(LOOSE + " .fcc-loose-row.kb-active")
    dialog.evaluate("window.closeAuditPanel()")
    dialog.wait_for_timeout(60)
    assert dialog.locator(LOOSE).count() == 1


def test_a_question_over_the_panels_loose_list_goes_back_to_it(dialog):
    """A CMD:DONE scanned with the list up: the newest of two on the confirm tier is
    on top, and Back leaves the list where it was."""
    dialog.click(LOOSE_BTN)
    dialog.wait_for_selector(LOOSE + " .fcc-loose-row.kb-active")
    dialog.evaluate("window.processScan('CMD:DONE', 'barcode')")
    dialog.wait_for_function("(sel) => document.activeElement === document.querySelector(sel)", arg=BACK)
    assert _on_top(dialog, BACK)
    dialog.keyboard.press("Enter")
    _closed(dialog)
    assert dialog.locator(LOOSE).count() == 1
