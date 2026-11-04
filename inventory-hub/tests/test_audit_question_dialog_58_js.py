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
TITLE = QUESTION + " .fcc-apc-title"
QRS = QUESTION + " .fcc-confirm-qr-row"
LOOSE_BTN = "#fcc-audit-panel-loose"
LOOSE = "#fcc-loose-list"


def _look(color, grams=500.0):
    """A row's tile look, as the route gives every row of the question (Derek,
    2026-11-03, H S1: from the rows stored at each scan)."""
    return {"color": color, "color_direction": "longitudinal", "remaining_weight": grams}


def _question(park=3, stays=0, file=0):
    """/api/identify_scan's audit_done_question, as pinned by
    test_the_samples_shape_is_the_routes below. `file`: how many Extras Done files
    here (Derek's C3), from LR-MDB-2, so the multi-slot box's words come with them.
    PIN UPDATED DELIBERATELY (review of 7e3720f, S-7): the words name the real gesture.
    And again (H S1): every row carries its tile's look."""
    note = {0: "", 1: "It goes in with no slot: scan it, then its slot's label, to set one."}.get(
        file, "They go in with no slot: scan each one, then its slot's label, to set it.")
    return {"type": "audit_done_question", "audit_id": "boot-1", "location": "LR-MDB-1", "found": 2,
            "expected": 2 + park + stays,
            "park": [{"id": 100 + n, "display": f"#{100 + n} Some Brand PLA (Red {n})",
                      "where": f"LR-MDB-1 slot {n + 1}", "slot": str(n + 1), **_look("C0392B")}
                     for n in range(park)],
            "stays": [{"id": 300 + n, "display": f"#{300 + n} Some Brand PETG (Clear {n})", "where": "XL-4",
                       "why": "moved to XL-4", **_look("E8F1F2", 120.0)} for n in range(stays)],
            "file": [{"id": 200 + n, "display": f"#{200 + n} Some Brand PLA (Blue {n})",
                      "where": f"LR-MDB-2 slot {n + 1}", **_look("1F5FBF", 845.5)} for n in range(file)],
            "file_note": note}


# The Yes's answer. PIN UPDATED DELIBERATELY (Derek, 2026-11-03, H S3): it carries the
# report as data, for the window that opens after it (its shape pinned to the route's
# below, as the question's is).
PARKED = {"success": True, "parked": [100, 101, 102], "filed": [], "stayed": [], "failed": [],
          "msg": "Parked 3 spools at Unknown. Undo Last Move puts them back.",
          "audit_ended": {"id": "boot-1", "why": "done"},
          "report": {"audit_id": "boot-1", "place": "LR-MDB-1", "why": "done", "summary": "Found 2 of 5.",
                     "found": 2, "expected": 5, "extras": 0, "loaded": 0, "perfect": False,
                     "groups": [{"kind": "parked", "title": "Parked at Unknown",
                                 "rows": [{"id": 100 + n, "display": f"#{100 + n} Some Brand PLA (Red {n})",
                                           "where": f"LR-MDB-1 slot {n + 1}", "why": "", "needs_label": False,
                                           **_look("C0392B")} for n in range(3)]}]}}

# Derek's C (review of 7e3720f, P-3): a question with long names in every list and C's
# real reasons, in the route's shape (its keys are _question's, pinned below).
HEAD_WHY = "loaded on XL-1: an audit never takes a spool off a printer"
LONG_QUESTION = {
    "type": "audit_done_question", "audit_id": "boot-1", "location": "LR-MDB-1", "found": 2, "expected": 4,
    "park": [{"id": 101, "display": "#101 Another Maker PETG (Transparent Orange Glow)", "where": "LR-MDB-1 slot 2",
              "slot": "2", **_look("FF8C1A")},
             {"id": 102, "display": "#102 Some Brand PLA (Galaxy Black)", "where": "LR-MDB-1 slot 3", "slot": "3",
              **_look("1A1A1A")}],
    "file": [{"id": 201, "display": "#201 Some Brand PLA (Glow Teal)", "where": "LR-MDB-2 slot 3", **_look("2EC4B6")},
             {"id": 202, "display": "#202 Another Maker PETG (Transparent Orange)", "where": "Unassigned",
              **_look("FF9F43")}],
    "stays": [{"id": 301, "display": "#301 Some Brand PETG (Clear)", "where": "XL-1", "why": HEAD_WHY,
               **_look("E8F1F2")},
              {"id": 302, "display": "#302 Some Brand PLA (Red)", "where": "LR-MDB-2 slot 2",
               "why": "FCC has it in LR-MDB-2 slot 2, inside LR", **_look("C0392B")},
              {"id": 303, "display": "#303 Some Brand ASA (Grey)", "where": "PM-DB-1",
               "why": "PM-DB-1 holds one spool, and #10 is there", **_look("8E8E8E")},
              {"id": 304, "display": "#304 Some Brand PLA (White)", "where": "CR-CT-1", "why": "in the scan buffer",
               **_look("F5F5F5")}],
    "file_note": "They go in with no slot: scan each one, then its slot's label, to set it.",
}
# Every name or reason the question cuts: what it shows against what it needs. PIN UPDATED
# DELIBERATELY (builder B, Q1): the question's spools are colour tiles, and so are what it
# reads (a line of the old kind would be counted too).
CUT = """(q) => Array.from(document.querySelectorAll(q + ' .fcc-apc-line-text, ' + q + ' .fcc-apc-line-where, '
        + q + ' .fcc-spool-tile-name, ' + q + ' .fcc-spool-tile-detail, ' + q + ' .fcc-spool-tile-where'))
    .filter((el) => el.scrollWidth > el.clientWidth + 1 || el.scrollHeight > el.clientHeight + 1)
    .map((el) => ({ text: el.textContent, shown: el.clientWidth, needs: el.scrollWidth }))"""
LISTS = QUESTION + " .fcc-apc-sections"


def test_the_samples_shape_is_the_routes(asked):
    """Pins the samples, here and in the guards, to the real route's answers."""
    real = asked["question"]
    for sample in (_question(stays=1), SAMPLE_QUESTION, LONG_QUESTION):
        assert set(sample) == set(real) and sample["type"] == real["type"]
        assert set(sample["park"][0]) == set(real["park"][0]) and set(sample["stays"][0]) == set(real["stays"][0])
    assert set(PARKED) == set(asked["parked"])
    sample, real_report = PARKED["report"], asked["parked"]["report"]
    assert set(sample) == set(real_report)
    assert set(sample["groups"][0]) == set(real_report["groups"][0])
    assert set(sample["groups"][0]["rows"][0]) == set(real_report["groups"][0]["rows"][0])


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
    # PIN UPDATED DELIBERATELY (Derek, 2026-11-03, H S1): the row carries its tile's look.
    assert real["file"] == [{"id": 200, "display": "#200 Some Brand PLA (Red)", "where": "LR-MDB-2 slot 1",
                             "color": "72071C", "color_direction": "longitudinal", "remaining_weight": 500.0}]
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
    # The report window says what the Yes did, in the panel's place. PIN UPDATED DELIBERATELY
    # (Derek's look of 2026-11-04, T3): its 4 s success toast went, as it peeked out around
    # a short report under the window.
    dialog.wait_for_selector("#fcc-audit-report #fcc-audit-report-close")
    assert PARKED["msg"] not in dialog.evaluate(
        "Array.from(document.querySelectorAll('#toast-container .toast-msg')).map((e) => e.textContent)")


# --- the window it has -------------------------------------------------------------

def _measure(page):
    """`scrolls`: the whole question scrolls; `lists`: its lists alone do (Q1's tiles), with
    the lists' own overflow, height and content height."""
    return page.evaluate("""([sheet, qrs]) => { const p = document.querySelector(sheet);
        const s = p.getBoundingClientRect(), q = document.querySelector(qrs).getBoundingClientRect();
        const l = p.querySelector('.fcc-apc-sections');
        return { top: s.top, bottom: s.bottom, left: s.left, right: s.right, qrTop: q.top, qrBottom: q.bottom,
                 vh: innerHeight, vw: document.documentElement.clientWidth,
                 scrolls: p.classList.contains('fcc-question-scroll'), wide: p.scrollWidth > p.clientWidth + 1,
                 lists: p.classList.contains('fcc-apc-lists-scroll'), overflow: l ? getComputedStyle(l).overflowY : '',
                 listsHigh: l ? l.clientHeight : 0, listsContent: l ? l.scrollHeight : 0 }; }""",
                         [SHEET, QRS])


def _every_tile_shows_in_the_lists(page):
    """Scrolled through, each tile is whole inside the lists' box at some point: none sits
    outside what the box can scroll to. The box goes back to its top."""
    return page.evaluate("""(lists) => { const box = document.querySelector(lists);
        const tiles = Array.from(box.querySelectorAll('.fcc-spool-tile'));
        const seen = new Set();
        for (let top = 0; ; top += Math.max(8, box.clientHeight / 2)) {
            box.scrollTop = top;
            const r = box.getBoundingClientRect();
            tiles.forEach((t, i) => { const b = t.getBoundingClientRect();
                if (b.top >= r.top - 0.5 && b.bottom <= r.bottom + 0.5) seen.add(i); });
            if (box.scrollTop + box.clientHeight >= box.scrollHeight - 1) break;
        }
        box.scrollTop = 0;
        return { tiles: tiles.length, seen: seen.size }; }""", LISTS)


def _show(page, park, stays):
    page.evaluate("(q) => window.askAuditDone(q)", _question(park, stays))
    page.wait_for_selector(QRS)
    page.wait_for_timeout(120)                   # the QR codes draw two frames later


@pytest.mark.parametrize("park, stays", [(20, 0), (10, 10), (20, 12), (40, 40)])
def test_every_spool_is_a_tile_and_the_lists_scroll_with_the_qrs_in_view_on_a_small_laptop(dialog, park, stays):
    """Derek, 2026-11-03: every spool as a colour tile, past 24, "scrolling inside the question
    while its words, buttons and QRs stay in view" (a scanner can't read a QR that has
    scrolled away). PIN UPDATED DELIBERATELY (builder B, Q1; was
    test_twenty_spools_fit_with_the_qrs_in_view_on_a_small_laptop: 8 lines a list, the lists
    side by side). The lists sit one above the other, three tiles to a row, and they scroll
    alone; the question as a whole never does. RED on 9d1163f: no tiles."""
    dialog.set_viewport_size({"width": 1366, "height": 768})
    _show(dialog, park, stays)
    m = _measure(dialog)
    assert not m["scrolls"] and m["lists"] and m["overflow"] == "auto", m
    assert m["listsContent"] > m["listsHigh"] >= 80, m          # LISTS_MIN_REM, a row of tiles at least
    assert m["top"] >= 0 and m["bottom"] <= m["vh"], m
    assert m["qrTop"] >= 0 and m["qrBottom"] <= m["vh"], m
    assert _on_top(dialog, BACK) and _on_top(dialog, YES) and _on_top(dialog, TITLE) and _on_top(dialog, HINT)
    assert _on_top(dialog, QRS + " .fcc-confirm-qr-cell[data-qr='confirm']")
    assert _on_top(dialog, QRS + " .fcc-confirm-qr-cell[data-qr='cancel']")
    assert _every_tile_shows_in_the_lists(dialog) == {"tiles": park + stays, "seen": park + stays}
    tops = dialog.evaluate("""() => Array.from(document.querySelectorAll('#fcc-audit-done-question .fcc-apc-section'))
        .map((s) => Math.round(s.getBoundingClientRect().top))""")
    assert len(tops) == (2 if stays else 1) and tops == sorted(tops) and len(set(tops)) == len(tops), tops   # one above the other
    lefts = dialog.evaluate("""() => new Set(Array.from(document.querySelectorAll(
        '#fcc-audit-done-question .fcc-apc-section:first-child .fcc-spool-tile')).map((t) => Math.round(t.getBoundingClientRect().left))).size""")
    assert lefts == 3, lefts                                     # three to a row on a laptop


def test_a_question_that_fits_is_no_scroller_and_its_lists_take_no_tab(dialog):
    """fccFitQuestion's rule, kept for the tiles: a scroller draws its text without the
    screen's sub-pixel smoothing, so a question that fits has none, and its lists, with
    nothing to scroll, are no stop for Tab (Back, Park them, Back)."""
    _show(dialog, 3, 1)
    m = _measure(dialog)
    assert not m["scrolls"] and not m["lists"] and m["overflow"] == "visible", m
    dialog.focus(BACK)
    seen = []
    for _ in range(3):
        dialog.keyboard.press("Tab")
        seen.append(dialog.evaluate("document.activeElement.className"))
    assert all("fcc-apc-sections" not in c for c in seen), seen


def test_the_scrolling_lists_are_a_keyboard_stop_and_enter_there_goes_back(dialog):
    """The keyboard reaches the lists while they scroll (Tab from Back goes round to them),
    the hint says what Enter does there, the arrow and page keys scroll them, and Enter
    there does what the hint says: it goes back, as anywhere but on the yes. RED on 9d1163f."""
    dialog.set_viewport_size({"width": 1366, "height": 768})
    _show(dialog, 24, 0)
    dialog.focus(BACK)
    dialog.keyboard.press("Tab")                                 # Back is last: round to the lists
    assert dialog.evaluate("(s) => document.activeElement === document.querySelector(s)", LISTS)
    assert dialog.text_content(HINT) == "Enter goes back · Esc goes back"
    assert dialog.evaluate("(s) => document.querySelector(s).scrollTop", LISTS) == 0
    dialog.keyboard.press("ArrowDown")
    dialog.wait_for_function("(s) => document.querySelector(s).scrollTop > 0", arg=LISTS)
    dialog.keyboard.press("End")
    dialog.wait_for_function("(s) => { const b = document.querySelector(s); return b.scrollTop + b.clientHeight >= b.scrollHeight - 1; }",
                             arg=LISTS)
    dialog.keyboard.press("PageUp")
    dialog.wait_for_function("(s) => { const b = document.querySelector(s); return b.scrollTop + b.clientHeight < b.scrollHeight - 1; }",
                             arg=LISTS)
    dialog.keyboard.press("Tab")                                 # on to the yes, and back
    assert dialog.evaluate("(sel) => document.activeElement === document.querySelector(sel)", YES)
    dialog.keyboard.press("Shift+Tab")
    assert dialog.evaluate("(s) => document.activeElement === document.querySelector(s)", LISTS)
    dialog.keyboard.press("Enter")
    _closed(dialog)
    assert dialog.evaluate("window.__parks") == []
    assert dialog.is_visible(DONE) and dialog.evaluate("state.auditActive") is True


def test_a_scans_enter_on_the_lists_answers_nothing(dialog):
    """A scanner's Enter with the keyboard on the lists is the scan's, which the open
    question holds off."""
    dialog.set_viewport_size({"width": 1366, "height": 768})
    _show(dialog, 24, 0)
    dialog.focus(LISTS)
    dialog.keyboard.type("ID:57", delay=0)
    dialog.keyboard.press("Enter")
    dialog.wait_for_selector(STATUS, state="visible")
    assert dialog.is_visible(QUESTION) and dialog.evaluate("window.__parks") == []
    assert "(Ignored: ID:57)" in dialog.text_content(STATUS)


def test_on_a_phone_the_lists_scroll_in_one_column_and_never_sideways(dialog):
    """PIN UPDATED DELIBERATELY (builder B, Q1; was ..._scrolls_whole_...: the whole question
    scrolled, QRs and all, on a phone). On a phone too the lists alone scroll, one tile to a
    row, and the words, the buttons and the QRs stay in view. Nothing scrolls sideways."""
    dialog.set_viewport_size({"width": 360, "height": 640})
    _show(dialog, 20, 12)
    m = _measure(dialog)
    assert not m["scrolls"] and m["lists"], m
    assert m["left"] >= 0 and m["right"] <= m["vw"] and not m["wide"], m
    assert m["qrTop"] >= 0 and m["qrBottom"] <= m["vh"] and _on_top(dialog, BACK) and _on_top(dialog, YES), m
    assert _every_tile_shows_in_the_lists(dialog) == {"tiles": 32, "seen": 32}
    lefts = dialog.evaluate("""() => new Set(Array.from(document.querySelectorAll('#fcc-audit-done-question .fcc-spool-tile'))
        .map((t) => Math.round(t.getBoundingClientRect().left))).size""")
    assert lefts == 1, lefts
    assert dialog.evaluate(CUT, QUESTION) == []


def test_a_window_too_short_for_the_lists_scrolls_the_whole_question_as_before(dialog):
    """A window whose words, buttons and QRs alone take nearly all of it, so the lists would
    keep less than a row of tiles (LISTS_MIN_REM): the nearest safe thing, the whole
    question scrolls (fccFitQuestion's rule for any question), its QRs reachable at its end.
    300 px tall here: this page has no Bootstrap and no QR library, so its question is
    shorter than the dashboard's, where a phone held sideways (844 x 390) does this
    (test_audit_done_question_58_e2e.py)."""
    dialog.set_viewport_size({"width": 844, "height": 300})
    _show(dialog, 20, 12)
    m = _measure(dialog)
    assert m["scrolls"] and not m["lists"] and not m["wide"], str(m)
    dialog.evaluate("(sel) => { const p = document.querySelector(sel); p.scrollTop = p.scrollHeight; }", SHEET)
    m = _measure(dialog)
    assert m["qrTop"] >= 0 and m["qrBottom"] <= m["vh"], m


def test_a_long_name_wraps_whole_and_its_reason_stays_whole(dialog):
    """PIN UPDATED DELIBERATELY (review of 7e3720f, P-3; was ..._stays_on_one_line_...): the
    name gave way, its full text only in the line's title, which a touch screen can't show.
    Done's lists wrap now: the name reads whole on its own lines, its reason under it, and
    the title stays for a mouse. The question is no wider for it."""
    # PIN UPDATED DELIBERATELY (builder B, Q1): its line is a tile now, the name on its
    # lines, then the grams, then the reason, each whole; the tile has no title to need.
    name = "#300 " + "A very long maker's name " * 6 + "PETG (Clear)"
    question = _question(1, 1)
    question["stays"][0].update(display=name, why="moved to LR-MDB-2 slot 3")
    dialog.evaluate("(q) => window.askAuditDone(q)", question)
    dialog.wait_for_selector(QRS)
    line = dialog.evaluate("""() => { const l = document.querySelectorAll('#fcc-audit-done-question .fcc-spool-tile')[1];
        const t = l.querySelector('.fcc-spool-tile-name'), w = l.querySelector('.fcc-spool-tile-where');
        return { high: l.getBoundingClientRect().height, text: t.textContent, name: t.scrollWidth <= t.clientWidth + 1,
                 lines: Math.round(t.getBoundingClientRect().height / parseFloat(getComputedStyle(t).lineHeight)),
                 why: w.textContent, whole: w.scrollWidth <= w.clientWidth + 1,
                 under: w.getBoundingClientRect().top >= t.getBoundingClientRect().bottom - 1,
                 sheetWide: document.querySelector('#fcc-audit-done-question .fcc-apc-panel').getBoundingClientRect().width }; }""")
    assert line["text"] == name and line["name"] and line["lines"] >= 3, line
    assert line["why"] == "moved to LR-MDB-2 slot 3" and line["whole"] and line["under"], line
    assert line["sheetWide"] == 800              # the wide window: the name didn't widen it


@pytest.mark.parametrize("width, height", [(1366, 768), (390, 844)])
def test_c_long_names_and_reasons_are_never_cut(dialog, width, height):
    """Review of 7e3720f, P-3: C's stays carry long reasons and its question a third list;
    each line was one row that never wrapped, so names and reasons were cut at every size.
    Nothing is cut now, the question never scrolls sideways, and the Yes, Back and both QRs
    stay reachable, in view or by the question's own scroll."""
    dialog.set_viewport_size({"width": width, "height": height})
    dialog.evaluate("(q) => window.askAuditDone(q)", LONG_QUESTION)
    dialog.wait_for_selector(QRS)
    dialog.wait_for_timeout(120)                 # the QR codes draw two frames later
    assert dialog.evaluate(CUT, QUESTION) == []
    m = _measure(dialog)
    assert m["left"] >= 0 and m["right"] <= m["vw"] and not m["wide"], m
    if m["scrolls"]:
        dialog.evaluate("(sel) => { const p = document.querySelector(sel); p.scrollTop = p.scrollHeight; }", SHEET)
        m = _measure(dialog)
    assert m["qrTop"] >= 0 and m["qrBottom"] <= m["vh"], m
    assert _on_top(dialog, BACK) and _on_top(dialog, YES)


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
