"""Group 62.1: the scan ladder answers each command with itself.

`logic.resolve_scan` matches its commands as SUBSTRINGS of the scan, in order, so a
command whose text holds another's must be tested first. CMD:EJECTALL came after
CMD:EJECT, so every EJECTALL text the page's exact match missed (a key left in front
of the scan, "qCMD:EJECTALL") came back as `eject`. That turned Eject mode on, and
the next spool scanned was ejected. The page's own `ejectall` branch was reached by
no text at all.

Offline: no container, no Spoolman. Pinned here:
- every command answers itself alone, with a key or a label in front, and in lower
  case; one with no payload also with another label glued after it;
- for every pair of ladder commands where one text holds the other, the ladder tests
  the longer one first (read from resolve_scan's own source, so a command added later
  is held to it too);
- every command in the ladder is in this file's table, so a new one is added here;
- a code only the page reads (processScan's exact matches), misread with a key in
  front, reaches the server as no OTHER command: its own where the server reads it
  too, else "Malformed Command".
"""
from __future__ import annotations

import inspect
import re
from pathlib import Path

import pytest

import logic

INV_CMD = Path(__file__).resolve().parent.parent / "static" / "js" / "modules" / "inv_cmd.js"

AUDIT_ID = "a1b2c3-7"


def _cmd(name: str, **extra) -> dict:
    return {"type": "command", "cmd": name, **extra}


# Every plain command in the ladder: the text its QR carries, and its answer.
PLAIN = {
    "CMD:UNDO": _cmd("undo"),
    "CMD:CLEAR": _cmd("clear"),
    "CMD:EJECTALL": _cmd("ejectall"),
    "CMD:EJECT": _cmd("eject"),
    "CMD:CONFIRM": _cmd("confirm"),
    "CMD:CYCLE": _cmd("next"),
    "CMD:NEXT": _cmd("next"),
    "CMD:PREV": _cmd("prev"),
    "CMD:DONE": _cmd("done"),
    "CMD:CANCEL": _cmd("cancel"),
    "CMD:AUDIT": _cmd("audit"),
    "CMD:BULKMOVE": _cmd("bulkmove"),
    "CMD:NEEDLABEL": _cmd("needlabel"),
}

# Every command that carries a payload: the ladder's own pattern -> a sample text
# and its answer.
PAYLOAD = {
    "CMD:SLOT:": ("CMD:SLOT:3", _cmd("slot", value="3")),
    "CMD:FOUND": (f"CMD:FOUND:{AUDIT_ID}:57", _cmd("found", audit=AUDIT_ID, id=57)),
}

EVERY_COMMAND = [pytest.param(text, answer, id=text) for text, answer in PLAIN.items()] + [
    pytest.param(text, answer, id=pattern) for pattern, (text, answer) in PAYLOAD.items()]

FORMS = {
    "alone": lambda t: t,
    "key in front": lambda t: "q" + t,
    "label in front": lambda t: "ID:57" + t,
    # Not a LOC: label: "LOC:SHELF-1 CMD:SLOT:3" is a slot assignment (LOC:…:SLOT:n),
    # which resolve_scan reads before any command, on purpose.
    "label and a space in front": lambda t: "ID:57 " + t,
    "lower case": lambda t: t.lower(),
}


def _ladder() -> list[str]:
    """The command patterns resolve_scan tests, in the order it tests them."""
    src = inspect.getsource(logic.resolve_scan)
    return re.findall(r'if\s+"(CMD:[A-Z]+:?)"\s+in\s+upper_text', src)


@pytest.mark.parametrize("form", list(FORMS))
@pytest.mark.parametrize("text,answer", EVERY_COMMAND)
def test_each_command_answers_itself(text, answer, form):
    """FAILS on the old ladder for CMD:EJECTALL in every form: it answered `eject`."""
    assert logic.resolve_scan(FORMS[form](text)) == answer


@pytest.mark.parametrize("glued", ["ID:57", " ID:57", "LOC:SHELF-1", " LOC:SHELF-1"])
@pytest.mark.parametrize("text,answer", [pytest.param(t, a, id=t) for t, a in PLAIN.items()])
def test_a_label_glued_after_a_command_leaves_it_that_command(text, answer, glued):
    """A scanner's double read, or the next label run on. A payload command reads its
    payload from the end, so it is left out here (CMD:FOUND reads such a text as
    unread on purpose: test_audit_no_label_58.py)."""
    assert logic.resolve_scan(text + glued) == answer


def test_every_ladder_command_is_in_this_files_table():
    """A command added to resolve_scan is added to PLAIN or PAYLOAD above, so the
    tests here hold it to answering itself."""
    ladder = _ladder()
    assert len(ladder) >= len(PLAIN) + len(PAYLOAD), f"couldn't read resolve_scan's ladder: {ladder}"
    missing = [c for c in ladder if c not in PLAIN and c not in PAYLOAD]
    assert not missing, f"resolve_scan tests {missing}, which this file's table doesn't list: add them"
    gone = [c for c in list(PLAIN) + list(PAYLOAD) if c not in ladder]
    assert not gone, f"this file lists {gone}, which resolve_scan no longer tests"


def test_a_command_whose_text_holds_another_is_tested_first():
    """FAILS on the old ladder: CMD:EJECT was tested before CMD:EJECTALL."""
    ladder = _ladder()
    late = [(short, long_) for i, short in enumerate(ladder) for long_ in ladder[i + 1:]
            if short != long_ and short in long_]
    assert not late, ("resolve_scan tests a command before a longer one that holds its text, so the "
                      f"longer one can never be answered: {late}. Test the longer one first.")


def _page_codes() -> list[str]:
    """The codes processScan matches exactly (upper === 'CMD:…', or a prefix with a
    sample payload), read from inv_cmd.js."""
    src = INV_CMD.read_text(encoding="utf-8")
    exact = set(re.findall(r"upper === '(CMD:[A-Z]+)'", src))
    prefix = set(re.findall(r"upper\.startsWith\('(CMD:[A-Z]+:)'\)", src))
    assert exact and prefix, "couldn't read processScan's exact matches from inv_cmd.js"
    return sorted(exact) + sorted(p + "57" for p in prefix)


@pytest.mark.parametrize("code", _page_codes())
def test_a_page_code_misread_reaches_the_server_as_no_other_command(code):
    """A key left in front of a page code makes the page's exact match miss, and the
    text goes to the server. There it must answer as that code (a code both read) or
    not at all, never as another command (CMD:EJECTALL's answer was Eject mode)."""
    answer = logic.resolve_scan("q" + code)
    if code in PLAIN:
        assert answer == PLAIN[code]
    else:
        assert answer == {"type": "error", "msg": "Malformed Command"}, (
            f"{code} is read only by the page, yet the server reads it as {answer}")
