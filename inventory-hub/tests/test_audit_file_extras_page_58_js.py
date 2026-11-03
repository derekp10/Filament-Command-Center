"""Derek's answers of 2026-11-03 on Group 58, C (built for his look, in commits of its own
so it can come out): Done files the Extras here. The page half: Done's question names
them in a section of their own, its title and its Yes say what it does, the Yes sends
`file_ids` beside `ids`, and the Last found strip says what Done will do with an Extra
(C6). On a real DOM and the REAL routes over tests/spoolman_extra_fake.SpoolmanHTTPFake,
hermetic (test_audit_find_and_tiles_58_js's `live`): every question, park and session row
here is the server's own. The server's rules are in test_audit_file_extras_58.py.

RED on 2fd8a2d (the question asked only about the park, the Yes sent no file_ids, and the
strip said nothing of Done) unless a test says it pins what was already right.
"""
from __future__ import annotations

import pytest

from test_audit_find_and_tiles_58_js import begin, live, posts, scanned  # noqa: F401  (live: the fixture)
from test_audit_no_label_58_js import strip_says, toasts
from test_audit_panel_58_js import audit  # noqa: F401  (the fixture `live` stands on)
from test_audit_session_58 import add_spool, env, session  # noqa: F401  (env: the fixture)
from test_scanner_safe_dialogs_61_js import page61  # noqa: F401  (the fixture `audit` stands on)

QUESTION = "#fcc-audit-done-question"
TITLE = QUESTION + " .fcc-apc-title"
MSG = QUESTION + " .fcc-apc-msg"
YES = QUESTION + " .fcc-apc-yes"
PAST_THE_ARMING = 760                      # armAfterMs (DOUBLE_PRESS_MS, inv_cmd.js) and a little
NOTE_ONE = "It goes in with no slot: scan its slot label afterwards to set one."
STAYS_ON_A_HEAD = "loaded on XL-1: an audit never takes a spool off a printer"


def ask(page):
    """Done, through the page's own scan path, and its question drawn."""
    scanned(page, "CMD:DONE")
    page.wait_for_selector(YES)


def sections(page):
    return page.evaluate("""(q) => Array.from(document.querySelectorAll(q + ' .fcc-apc-section')).map((s) => [
        s.querySelector('.fcc-apc-section-head').textContent,
        Array.from(s.querySelectorAll('.fcc-apc-line')).map((l) => [l.querySelector('.fcc-apc-line-text').textContent,
            (l.querySelector('.fcc-apc-line-where') || { textContent: '' }).textContent])])""", QUESTION)


def say_yes(page):
    page.wait_for_timeout(PAST_THE_ARMING)
    page.click(YES)
    page.wait_for_selector(QUESTION, state="detached")
    page.wait_for_function("() => !state.processing")


def record(env, sid):
    return env["fake"].records["spool"][sid]


def test_with_only_an_extra_to_file_done_asks_to_file_it_here(live, env):
    add_spool(env, 1, "LR-MDB-1", container_slot="1")
    add_spool(env, 200, "LR-MDB-2", container_slot="1")
    begin(live, env)
    aid = session()["audit_id"]
    scanned(live, "ID:1")
    scanned(live, "ID:200")
    ask(live)
    assert live.text_content(TITLE).strip().endswith("File #200 here?")
    assert sections(live) == [["Found here, FCC had them elsewhere", [["#200 Some Brand PLA (Red)", "from LR-MDB-2 slot 1"]]]]
    msg = live.text_content(MSG)
    assert "1 of 1 found at LR-MDB-1." in msg and "filed in LR-MDB-1" in msg and NOTE_ONE in msg
    assert "Undo Last Move puts it back." in msg and "Unknown" not in msg
    assert live.text_content(YES) == "File it here"
    say_yes(live)
    live.wait_for_function("() => !state.auditActive")
    sent = posts(live, "/api/audit/park")
    assert [(p["audit_id"], p["ids"], p["file_ids"]) for p in sent] == [(aid, [], [200])]
    assert record(env, 200)["location"] == "LR-MDB-1"
    assert any("Filed #200 here" in t["msg"] for t in toasts(live))


def test_with_spools_to_park_and_an_extra_to_file_the_yes_does_both(live, env):
    add_spool(env, 1, "LR-MDB-1", container_slot="1")
    add_spool(env, 2, "LR-MDB-1", container_slot="2")
    add_spool(env, 200, "LR-MDB-2", container_slot="1")
    begin(live, env)
    scanned(live, "ID:1")
    scanned(live, "ID:200")
    ask(live)
    assert live.text_content(TITLE).strip().endswith("Park 1 at Unknown and file 1 here?")
    assert [s[0] for s in sections(live)] == ["Not scanned", "Found here, FCC had them elsewhere"]
    assert sections(live)[0][1] == [["#2 Some Brand PLA (Red)", "slot 2"]]
    msg = live.text_content(MSG)
    assert "The one not scanned goes to Unknown" in msg and "filed in LR-MDB-1" in msg
    assert "Undo Last Move puts them back." in msg
    assert live.text_content(YES) == "Do both"
    say_yes(live)
    live.wait_for_function("() => !state.auditActive")
    sent = posts(live, "/api/audit/park")
    assert [(p["ids"], p["file_ids"]) for p in sent] == [([2], [200])]
    assert record(env, 2)["location"] == "UNKNOWN" and record(env, 200)["location"] == "LR-MDB-1"


def test_the_yes_sends_where_the_question_showed_each_extra(live, env):
    """Review of 7e3720f, R-1: a move sends what its screen showed. The Yes sends each
    Extra's `where` as the question showed it (`file_where`, {id: where}), and an Extra
    filed elsewhere while the question sat open stays where it went."""
    add_spool(env, 1, "LR-MDB-1", container_slot="1")
    add_spool(env, 200, "LR-MDB-2", container_slot="1")
    begin(live, env)
    scanned(live, "ID:1")
    scanned(live, "ID:200")
    ask(live)
    record(env, 200)["location"] = "CR-CT-1"          # another tab files it on the cart
    record(env, 200)["extra"]["container_slot"] = '""'
    say_yes(live)
    live.wait_for_function("() => !state.auditActive")
    sent = posts(live, "/api/audit/park")
    assert [(p["file_ids"], p["file_where"]) for p in sent] == [([200], {"200": "LR-MDB-2 slot 1"})]
    assert record(env, 200)["location"] == "CR-CT-1"
    assert not any("Filed #200" in t["msg"] for t in toasts(live))


def test_with_nothing_to_file_the_question_is_the_parks_and_the_yes_files_nothing(live, env):
    """The park's words, as before; its Yes now says `file_ids: []` (a Yes without the key
    files nothing on the server either, an older page's)."""
    add_spool(env, 1, "LR-MDB-1", container_slot="1")
    add_spool(env, 2, "LR-MDB-1", container_slot="2")
    begin(live, env)
    scanned(live, "ID:1")
    ask(live)
    assert live.text_content(TITLE).strip().endswith("Park 1 spool at Unknown?")
    assert [s[0] for s in sections(live)] == ["Not scanned"]
    assert live.text_content(YES) == "Park it"
    say_yes(live)
    live.wait_for_function("() => !state.auditActive")
    assert [(p["ids"], p["file_ids"]) for p in posts(live, "/api/audit/park")] == [([2], [])]


def test_an_extra_on_a_head_stays_and_the_question_says_why(live, env):
    """Pins already-right code: the server puts an Extra that stays in `stays`, which the
    page already listed; it asks to park, and files nothing."""
    add_spool(env, 1, "LR-MDB-1", container_slot="1")
    add_spool(env, 2, "LR-MDB-1", container_slot="2")
    add_spool(env, 242, "XL-1")
    begin(live, env)
    scanned(live, "ID:1")
    scanned(live, "ID:242")
    ask(live)
    got = dict((head, lines) for head, lines in sections(live))
    assert got["Left where they are"] == [["#242 Some Brand PLA (Red)", STAYS_ON_A_HEAD]]
    assert "Found here, FCC had them elsewhere" not in got
    assert live.text_content(YES) == "Park it"


@pytest.mark.parametrize("case, line", [
    ("files", "Extra: FCC has #200 at LR-MDB-2 slot 1; Done files it here."),
    ("stays", f"Extra: FCC has #200 at XL-1; it stays: {STAYS_ON_A_HEAD}."),
    ("one-spool place", "Extra: FCC has #200 at LR-MDB-2 slot 1; PM-DB-1 holds one spool, so Done files it here only if "
                        "nothing else is there."),
    ("unread", "Extra: #200: couldn't read where FCC has it."),
])
def test_the_strip_says_what_done_will_do_with_an_extra(live, env, case, line):
    """C6: from the row stored at the scan (`at_done`), so a poll reads nothing. The
    unread case pins the line as it was: nothing is said of Done."""
    place = "LR-MDB-1"
    if case == "one-spool place":
        env["rows"].append({"LocationID": "PM-DB-1", "Name": "One", "Type": "Dryer Box", "Max Spools": "1",
                            "parent_id": None})
        place = "PM-DB-1"
    add_spool(env, 1, place, container_slot="1")
    add_spool(env, 200, "XL-1" if case == "stays" else "LR-MDB-2", container_slot="" if case == "stays" else "1")
    begin(live, env, place)
    if case == "unread":
        env["fake"].down = True
    scanned(live, "ID:200")
    env["fake"].down = False
    strip_says(live, line)
    if case == "unread":
        assert "Done" not in live.text_content("#fcc-audit-last-found [role=status]")


def test_the_strip_says_nothing_of_done_for_a_spool_on_the_list(live, env):
    """Pins already-right code: only an Extra is filed."""
    add_spool(env, 1, "LR-MDB-1", container_slot="1")
    begin(live, env)
    scanned(live, "ID:1")
    strip_says(live, "No label was read for #1")
    assert "Done" not in live.text_content("#fcc-audit-last-found [role=status]")
