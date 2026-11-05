"""Group 58, Derek's second look (2026-11-03, section H): the audit's report window, the page
half (builder B, Q2). "A window right after Done's Yes, and a 📝 Read the report button on
the report's Activity Log line": the server's report as data (section H, S3), each spool
once under what the end did with it, as colour tiles, where the panel was.

On a real DOM, hermetic: the REAL overlay_mount.js, inv_core.js, inv_cmd.js, the real scan
accumulator and global.css (test_audit_question_dialog_58_js's `dialog`), in
`isolated_page`, so it runs under --offline. Its samples are pinned to the real route's
answers (`asked`: the real park over tests/spoolman_extra_fake.SpoolmanHTTPFake). The
dashboard's own guards are test_contrast_guard.py's and test_text_size_guard.py's, and the
double click on the Yes and on the log line's button is test_audit_double_click_58_e2e.py's.

RED on the commit before Q2's unless a test says it pins what was already right.
"""
from __future__ import annotations

import pytest

from test_audit_done_question_58_js import asked  # noqa: F401  (asked: the fixture)
from test_audit_panel_58_js import DONE, PANEL, audit  # noqa: F401  (audit: the fixture)
from test_audit_question_dialog_58_js import PARKED, _look, dialog  # noqa: F401  (dialog: the fixture)
from test_audit_session_58 import env  # noqa: F401  (env: the fixture)
from test_scanner_safe_dialogs_61_js import page61  # noqa: F401  (page61: the fixture)

REPORT = "#fcc-audit-report"
SHEET = REPORT + " .fcc-audit-report-panel"
TITLE = REPORT + " #fcc-audit-report-title"
CLOSE = REPORT + " #fcc-audit-report-close"
BODY = REPORT + " .fcc-audit-report-body"
QUESTION = "#fcc-audit-done-question"
YES = QUESTION + " .fcc-apc-yes"
PAST_THE_ARMING = 720                       # armAfterMs (DOUBLE_PRESS_MS, inv_cmd.js) and a little
HEAD_WHY = "loaded on XL-1: an audit never takes a spool off a printer"
BUTTON = ('<button type="button" class="btn btn-sm btn-outline-info ms-2 py-0 px-1 fcc-audit-report-open" '
          'data-audit-report="boot-1">📝 Read the report</button>')


def _row(sid, name, where="", why="", needs_label=False, color="C0392B", grams=500.0):
    """A report row, as logic._audit_report_row builds it."""
    return {"id": sid, "display": f"#{sid} {name}", **_look(color, grams), "where": where, "why": why,
            "needs_label": needs_label}


# A Yes's report, every kind it can hold, in the route's shape (pinned below).
FULL = {"audit_id": "boot-1", "place": "LR-MDB-1", "why": "done", "summary": "Found 2 of 6.", "found": 2,
        "expected": 6, "extras": 2, "loaded": 1, "perfect": False, "groups": [
            {"kind": "parked", "title": "Parked at Unknown", "rows": [
                _row(101, "Some Brand PLA (Red)", "LR-MDB-1 slot 2"),
                _row(102, "Some Brand PLA (Galaxy Purple With Glitter Sparkles)", "LR-MDB-1 slot 3", color="4B2A6B")]},
            {"kind": "filed", "title": "Filed in LR-MDB-1", "rows": [
                _row(201, "Another Maker PETG (Glow Teal)", "LR-MDB-2 slot 3", needs_label=True, color="2EC4B6")]},
            {"kind": "stayed", "title": "Left where they are", "rows": [
                _row(301, "Some Brand PETG (Clear)", "XL-1", HEAD_WHY, color="E8F1F2"),
                _row(302, "Some Brand PLA (White)", "CR-CT-1", "moved to CR-CT-1", color="F5F5F5")]},
            {"kind": "failed", "title": "Couldn't be moved", "rows": [
                # Spoolman's words, as the route words them (spoolman_api.refusal_words, T5).
                _row(103, "Some Brand ASA (Grey)", "LR-MDB-1 slot 4", "Spoolman refused it: nope", color="8E8E8E")]},
            {"kind": "trail", "title": "Loaded from LR-MDB-1", "rows": [
                _row(242, "Some Brand PLA (Galaxy Black)", "XL-2", color="1A1A1A")]},
            {"kind": "needs_label", "title": "Needs a label", "rows": [
                _row(57, "Some Brand PLA (Blue)", "LR-MDB-1 slot 1", needs_label=True, color="1F5FBF")]}]}
# An end that moved nothing (a Cancel's, read later from its line).
CANCELLED = {"audit_id": "boot-2", "place": "SHELF-1", "why": "cancel", "summary": "Found 0 of 2.", "found": 0,
             "expected": 2, "extras": 1, "loaded": 0, "perfect": False, "groups": [
                 {"kind": "missing", "title": "Not scanned", "rows": [_row(30, "Some Brand PLA (Red)", "SHELF-1"),
                                                                      _row(40, "Some Brand PLA (Red)", "SHELF-1 slot 2")]},
                 {"kind": "extra", "title": "Extra (filed elsewhere)", "rows": [
                     _row(200, "Some Brand PLA (Red)", "LR-MDB-2 slot 3")]}]}
PERFECT = {"audit_id": "boot-1", "place": "SHELF-1", "why": "done",
           "summary": "Found 1 of 1. ✅ Perfect Match! All items accounted for.", "found": 1, "expected": 1,
           "extras": 0, "loaded": 0, "perfect": True, "groups": []}


def test_the_samples_are_the_routes_shape(asked):
    """Pins the samples to the real park's report (logic._audit_report_data)."""
    real = asked["parked"]["report"]
    for sample in (FULL, CANCELLED, PERFECT):
        assert set(sample) == set(real)
    group = real["groups"][0]
    assert set(FULL["groups"][0]) == set(group) and set(FULL["groups"][0]["rows"][0]) == set(group["rows"][0])
    assert set(PARKED["report"]["groups"][0]["rows"][0]) == set(group["rows"][0])


def _answer_done_with(page, answer):
    page.evaluate("(a) => { window.__answers['CMD:DONE'] = a; }", answer)


def _yes(page):
    page.click(DONE)
    page.wait_for_selector(YES)
    page.wait_for_timeout(PAST_THE_ARMING)
    page.click(YES)


def _shown(page):
    page.wait_for_selector(CLOSE)
    page.wait_for_function("(s) => document.activeElement === document.querySelector(s)", arg=CLOSE)


def _groups(page):
    """Each group's heading and its tiles, [name, small line, where, tag]."""
    return page.evaluate("""(r) => { const get = (t, c) => (t.querySelector(c) || { textContent: '' }).textContent;
        return Array.from(document.querySelectorAll(r + ' .fcc-audit-report-group')).map((g) => [
            g.querySelector('.fcc-audit-report-head').textContent,
            g.querySelector('.fcc-spool-tile') ? g.querySelector('.fcc-spool-tile').dataset.tone : '',
            Array.from(g.querySelectorAll('.fcc-spool-tile')).map((t) => [get(t, '.fcc-spool-tile-name'),
                get(t, '.fcc-spool-tile-detail'), get(t, '.fcc-spool-tile-where'), get(t, '.fcc-spool-tile-tag')])]); }""",
                         REPORT)


def _on_top(page, selector):
    return page.evaluate("""(sel) => { const el = document.querySelector(sel); const r = el.getBoundingClientRect();
        return el.contains(document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2)); }""", selector)


# --- when it opens -------------------------------------------------------------------

def test_the_yes_opens_the_report_where_the_panel_was(dialog):
    """The park's answer carries the report (section H, S3). The panel goes, and the window
    takes its place: on top, the keyboard on Close."""
    dialog.evaluate("(r) => { window.__park = Object.assign({}, window.__park, { report: r }); }", FULL)
    _yes(dialog)
    dialog.wait_for_selector(PANEL, state="detached")
    _shown(dialog)
    assert dialog.text_content(TITLE) == "📝 Audit Report: LR-MDB-1"
    assert dialog.text_content(REPORT + " .fcc-audit-report-summary") == "Found 2 of 6."
    assert dialog.evaluate("(s) => window.isTopOverlay(document.querySelector(s))", REPORT)
    assert _on_top(dialog, CLOSE) and _on_top(dialog, TITLE)
    assert dialog.evaluate("state.auditActive") is False
    assert dialog.get_attribute(REPORT + " .fcc-audit-report-panel", "role") == "dialog"


def test_a_done_with_nothing_to_ask_opens_its_report(dialog):
    """A Done that ended the audit with no question carries its report too."""
    _answer_done_with(dialog, {"type": "command", "cmd": "audit_scan", "audit_ended": {"id": "boot-1", "why": "done"},
                               "report": PERFECT})
    dialog.click(DONE)
    _shown(dialog)
    assert dialog.text_content(TITLE) == "📝 Audit Report: SHELF-1"
    assert dialog.text_content(REPORT + " .fcc-audit-report-summary") == PERFECT["summary"]
    assert dialog.locator(REPORT + " .fcc-spool-tile").count() == 0
    assert "Every spool FCC had at SHELF-1 was found." in dialog.text_content(BODY)


def test_the_window_stands_for_the_success_toast(dialog):
    """Derek's look of 2026-11-04 (T3): the Yes's 4 s success toast ("Parked 3 spools at
    Unknown. …") and a Done's "Audit finished" sat under the report window, toasts being
    under the overlays, and peeked out around a short report. When the window opens for the
    end, it says what the end did, and no success toast is raised. RED on 8e9fca2: both
    toasts were raised."""
    _yes(dialog)
    _shown(dialog)
    assert _toasts(dialog) == []
    dialog.keyboard.press("Escape")
    dialog.wait_for_selector(REPORT, state="detached")
    dialog.evaluate("() => { state.auditActive = true; state.auditId = 'boot-1'; window.openAuditPanel(); }")
    dialog.wait_for_selector(DONE)
    _answer_done_with(dialog, {"type": "command", "cmd": "audit_scan", "audit_ended": {"id": "boot-1", "why": "done"},
                               "report": PERFECT})
    dialog.wait_for_timeout(PAST_THE_ARMING)
    dialog.click(DONE)
    _shown(dialog)
    assert _toasts(dialog) == []


def test_with_no_window_the_toast_still_says_it(dialog):
    """An answer that carries no report opens no window, and its toast says what happened,
    as before; a Cancel's says so. Pins what was right."""
    dialog.evaluate("(a) => { window.__park = a; }", dict(PARKED, report=None))
    _yes(dialog)
    dialog.wait_for_selector(PANEL, state="detached")
    dialog.wait_for_function("() => document.querySelectorAll('#toast-container .toast-msg').length > 0")
    assert _toasts(dialog) == [["success", PARKED["msg"]]] and dialog.locator(REPORT).count() == 0
    dialog.evaluate("() => { document.querySelectorAll('#toast-container .toast-msg').forEach((t) => t.remove()); }")
    for why, words in (("done", ["success", "Audit finished: its report is in the Activity Log."]),
                       ("cancel", ["info", "Audit cancelled: nothing moved."])):
        dialog.evaluate("() => { state.auditActive = true; state.auditId = 'boot-1'; window.openAuditPanel(); }")
        dialog.wait_for_selector(DONE)
        _answer_done_with(dialog, {"type": "command", "cmd": "audit_scan", "audit_ended": {"id": "boot-1", "why": why}})
        dialog.wait_for_timeout(PAST_THE_ARMING)
        dialog.click(DONE)
        dialog.wait_for_selector(PANEL, state="detached")
        dialog.wait_for_function("() => document.querySelectorAll('#toast-container .toast-msg').length > 0")
        assert _toasts(dialog) == [words] and dialog.locator(REPORT).count() == 0
        dialog.evaluate("() => { document.querySelectorAll('#toast-container .toast-msg').forEach((t) => t.remove()); }")


@pytest.mark.parametrize("why", ["cancel", "idle"])
def test_a_cancel_or_an_idle_end_opens_no_report(dialog, why):
    """Their lines' button opens theirs: an end that wasn't Done shows no window. A
    Cancel's answer carries no report; one that did would still open nothing."""
    _answer_done_with(dialog, {"type": "command", "cmd": "audit_scan", "audit_ended": {"id": "boot-1", "why": why},
                               "report": CANCELLED})
    dialog.click(DONE)
    dialog.wait_for_selector(PANEL, state="detached")
    dialog.wait_for_timeout(150)
    assert dialog.locator(REPORT).count() == 0


def test_a_yes_that_left_the_audit_open_opens_no_report(dialog):
    """Nothing landed: no report, the panel stays, as before. Pins what was right."""
    dialog.evaluate("() => { window.__park = { success: false, msg: 'Nothing was moved.' }; }")
    _yes(dialog)
    dialog.wait_for_function("() => document.querySelector('#fcc-audit-panel-notice').textContent === 'Nothing was moved.'")
    assert dialog.locator(REPORT).count() == 0 and dialog.locator(PANEL).count() == 1


# --- what it shows -----------------------------------------------------------------------

def test_each_spool_once_under_what_done_did_with_it(dialog):
    """Each group its icon, its title and its count; each spool a tile in the group's look,
    with its grams and where it came from, where it is or why it stays; a spool marked in
    this audit says so on its own tile (the Needs a label group holds only the ones no
    other group lists, section H, S3)."""
    dialog.evaluate("(r) => window.openAuditReport(r, { after: true })", FULL)
    _shown(dialog)
    # A row at the audited place keeps only its slot, on its small line (Derek's look of
    # 2026-11-04, T2). PIN UPDATED DELIBERATELY: #101 read "from LR-MDB-1 slot 2", #57
    # "📍 LR-MDB-1 slot 1", and #103 had no slot.
    assert _groups(dialog) == [
        ["❓ Parked at Unknown (2)", "missing", [["#101 Some Brand PLA (Red)", "500g (slot 2)", "", ""],
                                              ["#102 Some Brand PLA (Galaxy Purple With Glitter Sparkles)",
                                               "500g (slot 3)", "", ""]]],
        ["📥 Filed in LR-MDB-1 (1)", "extra", [["#201 Another Maker PETG (Glow Teal)", "500g", "from LR-MDB-2 slot 3",
                                              "🏷️ needs a label"]]],
        ["📌 Left where they are (2)", "stay", [["#301 Some Brand PETG (Clear)", "500g", HEAD_WHY, ""],
                                              ["#302 Some Brand PLA (White)", "500g", "moved to CR-CT-1", ""]]],
        ["🛑 Couldn't be moved (1)", "failed", [["#103 Some Brand ASA (Grey)", "500g (slot 4)", "Spoolman refused it: nope",
                                               ""]]],
        ["🔗 Loaded from LR-MDB-1 (1)", "trail", [["#242 Some Brand PLA (Galaxy Black)", "500g", "loaded on XL-2", ""]]],
        ["🏷️ Needs a label (1)", "found", [["#57 Some Brand PLA (Blue)", "500g (slot 1)", "", ""]]]]
    assert dialog.locator(REPORT + " .fcc-spool-tile > span[style*='border-radius:50%']").count() == 8   # a swatch each
    foot = dialog.text_content(REPORT + " .fcc-audit-report-foot")
    assert "Undo Last Move puts the parked and filed spools back." in foot
    assert "Read the report" in foot


def test_the_foot_says_where_to_read_it_again_on_a_phone_too(dialog):
    """Derek's look of 2026-11-04 (T6): the foot pointed only to the Activity Log, whose box
    on a phone is too small to show the report's line; the list the 📡 log pill opens does
    show it, with its button. One short sentence says both. RED on 446b891."""
    dialog.set_viewport_size({"width": 390, "height": 844})
    dialog.evaluate("(r) => window.openAuditReport(r, { after: true })", FULL)
    _shown(dialog)
    foot = " ".join(dialog.text_content(REPORT + " .fcc-audit-report-foot").split())
    assert foot.startswith("The same report is in the Activity Log and the 📡 pill's list: its 📝 Read the report "
                           "button opens this window again."), foot
    assert foot.count(".") == 2                       # that sentence, then Undo's


def test_an_end_that_moved_nothing_lists_what_was_missing_and_the_extras(dialog):
    """A Cancel's report, read later from its line: where FCC has each, and no word of
    Undo (nothing moved), nor of the Activity Log (it was opened from there)."""
    dialog.evaluate("(r) => window.openAuditReport(r)", CANCELLED)
    _shown(dialog)
    # PIN UPDATED DELIBERATELY (T2): #30 read "📍 SHELF-1" and #40 "📍 SHELF-1 slot 2".
    assert _groups(dialog) == [
        ["❌ Not scanned (2)", "missing", [["#30 Some Brand PLA (Red)", "500g", "", ""],
                                         ["#40 Some Brand PLA (Red)", "500g (slot 2)", "", ""]]],
        ["⚠️ Extra (filed elsewhere) (1)", "extra", [["#200 Some Brand PLA (Red)", "500g", "📍 LR-MDB-2 slot 3", ""]]]]
    assert dialog.locator(REPORT + " .fcc-audit-report-foot").count() == 0


def test_a_row_at_the_audited_place_keeps_only_its_slot(dialog):
    """Derek's look of 2026-11-04 (T2): every parked tile of SHELF-3-R1's report read "from
    SHELF-3-R1", which its title already names, so each tile took three lines for two. A row
    at the place itself has no where line, and its slot, when it has one, is on its small
    line as the panel's tile says it; a row from anywhere else keeps its line. The place is
    compared without case, and only whole: LR-MDB-10 isn't LR-MDB-1."""
    rep = dict(FULL, place="LR-MDB-1", groups=[
        {"kind": "parked", "title": "Parked at Unknown", "rows": [
            _row(1, "Some Brand PLA (Red)", "LR-MDB-1"),
            _row(2, "Some Brand PLA (Red)", "lr-mdb-1 slot 3"),
            dict(_row(3, "Some Brand PLA (Red)", "LR-MDB-1 slot 4"), remaining_weight=None)]},
        {"kind": "missing", "title": "Not scanned", "rows": [
            _row(4, "Some Brand PLA (Red)", "LR-MDB-10 slot 2"),
            _row(5, "Some Brand PLA (Red)", "Unassigned")]},
        {"kind": "stayed", "title": "Left where it is", "rows": [
            _row(6, "Some Brand PLA (Red)", "LR-MDB-1 slot 1", "in the scan buffer")]}])
    dialog.evaluate("(r) => window.openAuditReport(r, { after: true })", rep)
    _shown(dialog)
    assert _groups(dialog) == [
        ["❓ Parked at Unknown (3)", "missing", [["#1 Some Brand PLA (Red)", "500g", "", ""],
                                              ["#2 Some Brand PLA (Red)", "500g (slot 3)", "", ""],
                                              ["#3 Some Brand PLA (Red)", "(slot 4)", "", ""]]],
        ["❌ Not scanned (2)", "missing", [["#4 Some Brand PLA (Red)", "500g", "📍 LR-MDB-10 slot 2", ""],
                                         ["#5 Some Brand PLA (Red)", "500g", "📍 Unassigned", ""]]],
        ["📌 Left where it is (1)", "stay", [["#6 Some Brand PLA (Red)", "500g (slot 1)", "in the scan buffer", ""]]]]
    # No empty line is drawn for the where that went: two lines, not three.
    assert dialog.evaluate("""(r) => Array.from(document.querySelectorAll(r + ' [data-report-kind="parked"] .fcc-spool-tile'))
        .map((t) => t.querySelectorAll('.fcc-spool-tile-where').length)""", REPORT) == [0, 0, 0]


def test_every_word_is_escaped(dialog):
    """Spoolman's free text and FCC's place ids are HTML text here."""
    bad = dict(FULL, place="A<B", summary="Found <b>2</b>.", groups=[
        {"kind": "stayed", "title": "Left <i>where</i> it is", "rows": [
            _row(5, "Robin's <Egg> & Blue", "X<Y", "moved to <Z>")]}])
    dialog.evaluate("(r) => window.openAuditReport(r)", bad)
    _shown(dialog)
    html = dialog.inner_html(REPORT)
    assert "<b>2</b>" not in html and "<i>" not in html and "<Egg>" not in html and "<Z>" not in html
    assert dialog.text_content(TITLE) == "📝 Audit Report: A<B"
    assert _groups(dialog)[0][2] == [["#5 Robin's <Egg> & Blue", "500g", "moved to <Z>", ""]]


CUT = """(r) => Array.from(document.querySelectorAll(r + ' .fcc-spool-tile-name, ' + r + ' .fcc-spool-tile-where, '
    + r + ' #fcc-audit-report-title, ' + r + ' .fcc-audit-report-summary, ' + r + ' .fcc-audit-report-head'))
    .filter((el) => el.scrollWidth > el.clientWidth + 1).map((el) => el.textContent)"""
MEASURE = """(r) => { const p = document.querySelector(r + ' .fcc-audit-report-panel');
    const s = p.getBoundingClientRect(), b = p.querySelector('.fcc-audit-report-body');
    return { top: s.top, bottom: s.bottom, left: s.left, right: s.right, vh: innerHeight,
             vw: document.documentElement.clientWidth, scrolls: p.classList.contains('fcc-audit-report-scroll'),
             overflow: getComputedStyle(b).overflowY, high: b.clientHeight, content: b.scrollHeight, tab: b.tabIndex,
             wide: p.scrollWidth > p.clientWidth + 1 }; }"""
COLUMNS = """(r) => Array.from(document.querySelectorAll(r + ' .fcc-audit-report-group')).map((g) =>
    new Set(Array.from(g.querySelectorAll('.fcc-spool-tile')).map((t) => Math.round(t.getBoundingClientRect().left))).size)"""


def _many(n):
    rows = [_row(100 + i, f"Some Brand PLA (Colour {i} With A Longer Name Than Most)", f"LR-MDB-1 slot {i + 1}",
                 color=("C0392B", "2EC4B6", "4B2A6B", "F5F5F5")[i % 4]) for i in range(n)]
    return dict(FULL, groups=[{"kind": "parked", "title": "Parked at Unknown", "rows": rows}] + FULL["groups"][1:])


def test_two_columns_where_there_is_room_and_nothing_cut(dialog):
    """A laptop: the tiles of a group two to a row, every name and reason whole, and the
    window, which fits, no scroller (fccFitQuestion's rule: a scroller draws its text
    without ClearType) and its body no stop for Tab."""
    dialog.set_viewport_size({"width": 1366, "height": 900})
    dialog.evaluate("(r) => window.openAuditReport(r)", FULL)
    _shown(dialog)
    assert dialog.evaluate(COLUMNS, REPORT)[0] == 2
    assert dialog.evaluate(CUT, REPORT) == []
    m = dialog.evaluate(MEASURE, REPORT)
    assert not m["scrolls"] and m["overflow"] == "visible" and m["tab"] == -1, m
    assert m["top"] >= 0 and m["bottom"] <= m["vh"], m


@pytest.mark.parametrize("width, height", [(1366, 768), (390, 844)])
def test_a_long_report_scrolls_its_body_with_the_title_and_close_in_view(dialog, width, height):
    """Past a screenful: the body scrolls, the title, the summary and Close stay, every tile
    can be scrolled to, one column on a phone, nothing cut or sideways. The body is then a
    stop for Tab, whose arrow and page keys scroll it."""
    dialog.set_viewport_size({"width": width, "height": height})
    dialog.evaluate("(r) => window.openAuditReport(r)", _many(30))
    _shown(dialog)
    m = dialog.evaluate(MEASURE, REPORT)
    assert m["scrolls"] and m["overflow"] == "auto" and m["content"] > m["high"] and m["tab"] == 0, m
    assert m["top"] >= 0 and m["bottom"] <= m["vh"] and m["left"] >= 0 and m["right"] <= m["vw"] and not m["wide"], m
    assert _on_top(dialog, CLOSE) and _on_top(dialog, TITLE) and _on_top(dialog, REPORT + " .fcc-audit-report-summary")
    assert dialog.evaluate(COLUMNS, REPORT)[0] == (1 if width < 600 else 2)
    assert dialog.evaluate(CUT, REPORT) == []
    dialog.keyboard.press("Tab")                                 # Close, then the body
    assert dialog.evaluate("(s) => document.activeElement === document.querySelector(s)", BODY)
    dialog.keyboard.press("End")
    dialog.wait_for_function("(s) => { const b = document.querySelector(s); return b.scrollTop + b.clientHeight >= b.scrollHeight - 1; }",
                             arg=BODY)
    last = dialog.evaluate("""(r) => { const b = document.querySelector(r + ' .fcc-audit-report-body').getBoundingClientRect();
        const ts = document.querySelectorAll(r + ' .fcc-spool-tile'); const t = ts[ts.length - 1].getBoundingClientRect();
        return t.top >= b.top - 0.5 && t.bottom <= b.bottom + 0.5; }""", REPORT)
    assert last
    dialog.keyboard.press("Tab")                                 # Tab stays inside: back to Close
    assert dialog.evaluate("(s) => document.activeElement === document.querySelector(s)", CLOSE)


# --- how it closes ------------------------------------------------------------------------

@pytest.mark.parametrize("how", ["Escape", "Close", "Enter on Close"])
def test_escape_close_and_a_persons_enter_on_close_close_it(dialog, how):
    dialog.evaluate("(r) => window.openAuditReport(r)", FULL)
    _shown(dialog)
    if how == "Close":
        dialog.click(CLOSE)
    else:
        dialog.keyboard.press("Escape" if how == "Escape" else "Enter")
    dialog.wait_for_selector(REPORT, state="detached")
    assert dialog.evaluate("window.__ids") == []


def test_a_scans_enter_on_close_closes_nothing_by_itself_and_the_scan_goes_on(dialog):
    """The window takes no scan: a scan read while it is up goes to processScan as usual
    (its Enter presses no Close), and the window goes, so the scan's answer (a toast, a
    dialog) isn't under it."""
    dialog.evaluate("(r) => window.openAuditReport(r)", FULL)
    _shown(dialog)
    dialog.keyboard.type("ID:57", delay=0)
    dialog.keyboard.press("Enter")
    dialog.wait_for_function("() => window.__ids.length === 1")
    assert dialog.evaluate("window.__ids") == [{"text": "ID:57", "source": "barcode"}]
    dialog.wait_for_selector(REPORT, state="detached")


def test_a_second_read_of_the_done_that_ended_the_audit_leaves_it_up(dialog):
    """A scanner's double read of a printed CMD:DONE: the first ends the audit and opens the
    report, the second (within 1.5 s) goes on as a scan and leaves the report up. Later,
    a CMD:DONE is a person's next scan, and closes it."""
    _answer_done_with(dialog, {"type": "command", "cmd": "audit_scan", "audit_ended": {"id": "boot-1", "why": "done"},
                               "report": FULL})
    dialog.evaluate("() => window.processScan('CMD:DONE', 'barcode')")
    _shown(dialog)
    # With no audit the server answers CMD:DONE as the Location Manager's close, which this
    # page has no window for.
    _answer_done_with(dialog, {"type": "command", "cmd": "done"})
    dialog.evaluate("() => { window.closeManage = () => { window.__closedManage = (window.__closedManage || 0) + 1; }; }")
    dialog.evaluate("() => window.processScan('CMD:DONE', 'barcode')")
    dialog.wait_for_function("() => window.__ids.length === 2")
    dialog.wait_for_timeout(100)
    assert dialog.locator(REPORT).count() == 1
    dialog.evaluate("() => { const plain = Date.now; Date.now = () => plain() + 1600; }")
    dialog.evaluate("() => window.processScan('CMD:DONE', 'barcode')")
    dialog.wait_for_selector(REPORT, state="detached")


def test_a_new_audit_panel_takes_its_place(dialog):
    """An audit started meanwhile (another device, a heartbeat): its panel is the window on
    top now, and the report, read, goes."""
    dialog.evaluate("(r) => window.openAuditReport(r)", FULL)
    _shown(dialog)
    dialog.evaluate("() => { window.closeAuditPanel(); state.auditActive = true; window.updateAuditVisuals(); }")
    dialog.wait_for_selector(DONE)
    assert dialog.locator(REPORT).count() == 0


# --- what it says while it is up ---------------------------------------------------------------

NOTICE = REPORT + " #fcc-audit-report-notice"
OUTLIVED = "The audit has ended, so ID:57 did nothing. Scan it again if you meant it."


def test_a_scan_read_during_the_park_that_did_nothing_says_so_on_the_report(dialog):
    """Builder B, resumed (the stacked-overlays lens): a scan read while the park is out waits
    in the queue (the dim), and once the audit is over the queue drops it with a 7 s warning
    (window.auditScanOutlived). That toast's layer (z 11000) is under this window, which
    opened in the meantime, so the window says it too, on a line of its own, as the panel
    does on its notice; and it stays up, since the scan was read before it opened. Through
    the real accumulator and queue. RED on 8cd63ab: the words were only in a toast under the
    report's backdrop."""
    dialog.evaluate("""(r) => {
        window.__park = Object.assign({}, window.__park, { report: r });
        const answers = window.fetch;
        window.fetch = (url, opts) => {
            const answered = answers(url, opts);
            if (String(url).indexOf('/api/audit/park') === -1) return answered;
            return new Promise((resolve) => { window.__releasePark = () => resolve(answered); });
        };
    }""", FULL)
    _yes(dialog)
    dialog.wait_for_function("() => typeof window.__releasePark === 'function' && state.processing")
    dialog.keyboard.type("ID:57", delay=0)          # a scanner, while the park is out
    dialog.keyboard.press("Enter")
    dialog.wait_for_function("() => (state.scanQueue || []).length === 1")
    dialog.evaluate("() => window.__releasePark()")
    _shown(dialog)
    dialog.wait_for_function("(s) => { const n = document.querySelector(s); return !!n && n.textContent.length > 0; }",
                             arg=NOTICE)
    assert dialog.text_content(NOTICE) == OUTLIVED
    assert dialog.get_attribute(NOTICE, "role") == "alert"
    assert dialog.is_visible(NOTICE) and _on_top(dialog, NOTICE)
    assert dialog.locator(REPORT).count() == 1                  # still up: the scan was read before it
    assert all(i["text"] != "ID:57" for i in dialog.evaluate("window.__ids"))   # it did nothing
    assert ["warning", OUTLIVED] in _toasts(dialog)            # and its toast, as before
    # Under the title and the summary, above the spools: in view however long the report is.
    order = dialog.evaluate("""(r) => Array.from(document.querySelector(r + ' .fcc-audit-report-panel').children)
        .map((e) => e.id || e.className)""", REPORT)
    assert order.index("fcc-audit-report-notice") == order.index("fcc-audit-report-summary") + 1, order


def test_a_report_with_nothing_to_say_shows_no_notice_line(dialog):
    """The line is there only when something was said. Pins it hidden at the start."""
    dialog.evaluate("(r) => window.openAuditReport(r, { after: true })", FULL)
    _shown(dialog)
    assert dialog.locator(NOTICE).count() == 1 and not dialog.is_visible(NOTICE)


PARTIAL_MSG = ("Parked 2 spools at Unknown. Couldn't park #103. Undo Last Move puts them back. "
               "The Activity Log lists each spool.")


@pytest.mark.parametrize("landed", ["some", "every"])
def test_a_yes_that_could_not_move_every_spool_says_so_on_the_report(dialog, landed):
    """A Yes whose writes partly failed still ends the audit, with a 7 s warning (the park's
    `msg`, logic._audit_park_msg: "Couldn't park #103."), and the report opens with it,
    over that toast's layer: the window says it too, beside its 🛑 Couldn't be moved group.
    A Yes that moved every spool says nothing there (its 4 s toast is a success). RED on
    761b2ab for "some": the words were only in the toast under the window."""
    if landed == "some":
        answer = dict(PARKED, success=False, parked=[101, 102],
                      failed=[{"id": 103, "display": "#103 Some Brand ASA (Grey)", "why": 'HTTP 400: {"message": "nope"}'}],
                      msg=PARTIAL_MSG, report=FULL)
    else:
        answer = dict(PARKED, report=FULL)
    dialog.evaluate("(a) => { window.__park = a; }", answer)
    _yes(dialog)
    _shown(dialog)
    if landed == "some":
        dialog.wait_for_function("(s) => document.querySelector(s).textContent.length > 0", arg=NOTICE)
        assert dialog.text_content(NOTICE) == PARTIAL_MSG and dialog.is_visible(NOTICE) and _on_top(dialog, NOTICE)
        assert ["warning", PARTIAL_MSG] in _toasts(dialog)
    else:
        dialog.wait_for_timeout(100)
        assert not dialog.is_visible(NOTICE)
        # PIN UPDATED DELIBERATELY (Derek's look of 2026-11-04, T3): the window stands for
        # the Yes's 4 s success toast, which peeked out around a short report.
        assert ["success", PARKED["msg"]] not in _toasts(dialog)


# --- from the report's Activity Log line ------------------------------------------------------

LOG_ROW = {"time": "11:18:13", "type": "INFO", "color": "ffaa00", "meta": {"type": "audit_report", "audit_id": "boot-1"},
           "msg": f"📝 <b>Audit Report: LR-MDB-1</b>{BUTTON}<br>Found 2 of 6."}


@pytest.fixture
def logged(dialog):
    """The dashboard's Live Activity box, the report's line in it as the heartbeat draws it,
    and /api/audit/report answered by `window.__report` (its requests in `window.__asked`)."""
    page = dialog
    page.evaluate("""(row) => {
        const box = document.createElement('div'); box.id = 'live-logs'; box.className = 'log-box';
        document.body.appendChild(box);
        window.__report = null; window.__asked = [];
        const plain = window.fetch;
        window.fetch = (url, opts) => {
            const u = String(url);
            if (u.indexOf('/api/audit/report') !== -1) {
                window.__asked.push(u);
                if (window.__report === 'down') return Promise.reject(new Error('down'));
                return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(window.__report) });
            }
            if (u.indexOf('/api/logs') !== -1) {
                return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ logs: [row] }) });
            }
            return plain(url, opts);
        };
        window._renderLogsPayload({ logs: [row], status: { spoolman: true } }, true);
    }""", LOG_ROW)
    page.evaluate("() => { window.closeAuditPanel(); state.auditActive = false; window.updateAuditVisuals(); }")
    page.wait_for_selector("#live-logs .fcc-audit-report-open")
    return page


def test_the_log_lines_button_opens_the_same_window(logged):
    """One delegated click on the button the server put in the line (section H, S3): GET
    /api/audit/report?id=<its data-audit-report>, then the window. No second button is drawn
    from the entry's meta."""
    assert logged.locator("#live-logs .fcc-audit-report-open").count() == 1
    logged.evaluate("(r) => { window.__report = { success: true, report: r }; }", CANCELLED)
    logged.click("#live-logs .fcc-audit-report-open")
    _shown(logged)
    assert logged.evaluate("window.__asked") == ["/api/audit/report?id=boot-1"]
    assert logged.text_content(TITLE) == "📝 Audit Report: SHELF-1"


def test_a_double_press_of_the_button_asks_once(logged):
    logged.evaluate("(r) => { window.__report = { success: true, report: r }; }", CANCELLED)
    logged.dblclick("#live-logs .fcc-audit-report-open")
    _shown(logged)
    logged.wait_for_timeout(150)
    assert logged.evaluate("window.__asked") == ["/api/audit/report?id=boot-1"]
    assert logged.locator(REPORT).count() == 1


def test_the_log_pill_windows_button_opens_it_too(logged):
    """The log pill's overlay draws the same line; the window opens over it, and Escape
    closes only the report."""
    logged.evaluate("(r) => { window.__report = { success: true, report: r }; }", CANCELLED)
    logged.evaluate("() => window.openLogPillOverlay()")
    logged.wait_for_selector("#fcc-log-pill-overlay .fcc-audit-report-open")
    logged.click("#fcc-log-pill-overlay .fcc-audit-report-open")
    _shown(logged)
    assert logged.evaluate("(s) => window.isTopOverlay(document.querySelector(s))", REPORT)
    logged.keyboard.press("Escape")
    logged.wait_for_selector(REPORT, state="detached")
    assert logged.locator("#fcc-log-pill-overlay").count() == 1


def _toasts(page):
    return page.evaluate("""() => Array.from(document.querySelectorAll('#toast-container .toast-msg'))
        .map((e) => [e.className.replace('toast-msg toast-', ''), e.innerText])""")


def test_a_report_fcc_no_longer_has_says_the_servers_words_in_a_7_second_warning(logged):
    gone = ("FCC no longer has that audit's report: it keeps the last 10, and a restart clears them. "
            "Its line in the Activity Log has the same report in words.")
    logged.evaluate("(msg) => { window.__report = { success: false, msg }; }", gone)
    logged.evaluate("""() => { const plain = window.setTimeout; window.__toastMs = [];
        window.setTimeout = (fn, ms, ...rest) => { if (fn && fn.name === 'dismiss') window.__toastMs.push(ms); return plain(fn, ms, ...rest); }; }""")
    logged.click("#live-logs .fcc-audit-report-open")
    logged.wait_for_function("() => document.querySelectorAll('#toast-container .toast-msg').length > 0")
    assert ["warning", gone] in _toasts(logged)
    assert 7000 in logged.evaluate("window.__toastMs")
    assert logged.locator(REPORT).count() == 0


def test_no_answer_says_so(logged):
    logged.evaluate("() => { window.__report = 'down'; }")
    logged.click("#live-logs .fcc-audit-report-open")
    logged.wait_for_function("() => document.querySelectorAll('#toast-container .toast-msg').length > 0")
    assert ["warning", "FCC didn't answer, so the report couldn't be shown. Try again in a moment."] in _toasts(logged)
    assert logged.locator(REPORT).count() == 0


# --- review 3 (2026-11-04) --------------------------------------------------------------------

# A button laid on the page under a spot, over the deck (z 10) and below every overlay (z 20000),
# that counts its presses: what lies under the report window's Close on the dashboard (a Printer
# Status head, the 🛒 Queue, the deck's AUDIT tile on this page).
LAY_UNDER = r"""([x, y]) => { const b = document.createElement('button'); b.id = 'fcc-test-under';
    b.type = 'button'; b.textContent = 'under';
    b.style.cssText = `position:fixed; left:${x - 40}px; top:${y - 16}px; width:80px; height:32px; z-index:1000;`;
    window.__under = 0; b.addEventListener('click', () => { window.__under += 1; });
    document.body.appendChild(b); }"""


def _middle(page, selector):
    return page.evaluate("""(s) => { const r = document.querySelector(s).getBoundingClientRect();
        return [r.left + r.width / 2, r.top + r.height / 2]; }""", selector)


def _double_click(page, xy, gap_ms=120):
    """A person's double click: two presses at one spot, the second one counted as such."""
    page.mouse.move(*xy)
    page.mouse.down(click_count=1)
    page.mouse.up(click_count=1)
    page.wait_for_timeout(gap_ms)
    page.mouse.down(click_count=2)
    page.mouse.up(click_count=2)


def test_a_double_click_on_close_presses_nothing_under_it(logged):
    """Review 3, R3-1: the window closes on Close's first click, and the second press of a
    double click landed on whatever lay under Close on the dashboard (on a phone, a Printer
    Status head opened the Location Manager; on a laptop, the title bar's 🛒 Queue opened its
    window). The panel's Hide already stopped it (_shieldPage); the report window's Close now
    does too. RED on 539ce88: the button under Close was pressed."""
    logged.evaluate("(r) => window.openAuditReport(r)", FULL)
    _shown(logged)
    logged.wait_for_timeout(750)                    # past the shield its opening armed
    xy = _middle(logged, CLOSE)
    logged.evaluate(LAY_UNDER, xy)
    _double_click(logged, xy)
    logged.wait_for_timeout(150)
    assert logged.locator(REPORT).count() == 0      # the first click closed it
    assert logged.evaluate("window.__under") == 0   # the second reached nothing
    logged.wait_for_timeout(750)                    # a person's next press there, later, is theirs
    logged.mouse.click(*xy)
    assert logged.evaluate("window.__under") == 1


@pytest.mark.parametrize("key", ["Enter", "Space"])
def test_a_double_key_press_on_close_closes_it_and_asks_nothing(logged, key):
    """Review 3, R3-3: Close gives the keyboard back to the line's 📝 Read the report button it
    was asked from, so a person's second Enter (or Space) of a double press pressed that
    button and the window opened again, and every double press after it looped the same way.
    A press of the button 700 ms after the close is a person's next one, and asks. RED on
    b059144: a second /api/audit/report request went out, and the window was up again."""
    button = "#live-logs .fcc-audit-report-open"
    logged.evaluate("(r) => { window.__report = { success: true, report: r }; }", CANCELLED)
    logged.focus(button)
    logged.keyboard.press(key)
    _shown(logged)
    logged.wait_for_timeout(800)                    # read for a while
    logged.keyboard.press(key)                      # Close
    logged.wait_for_timeout(90)
    logged.keyboard.press(key)                      # the second of the double press: on the 📝
    logged.wait_for_timeout(300)
    assert logged.locator(REPORT).count() == 0
    assert logged.evaluate("window.__asked") == ["/api/audit/report?id=boot-1"]
    assert logged.evaluate("(s) => document.activeElement === document.querySelector(s)", button)
    logged.wait_for_timeout(450)                    # later, a person's next press opens it
    logged.keyboard.press(key)
    _shown(logged)
    assert len(logged.evaluate("window.__asked")) == 2
