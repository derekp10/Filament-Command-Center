"""Group 58, Derek's look of 2026-11-04 (T4): a place id stays whole in the words of a
question. Undo Last Move's question read "SHELF-2- / R3" at 1600 px, and Done's file-only
question "LR- / MDB-1" on a phone: a line may break after any hyphen.
window.fccKeepWhole already kept a box id whole on a button's label; Done's question's
title and words now do too (confirmActivePrint's `keepWhole`, which only Done's question
passes), and so does #confirmModal's message (requestConfirmation). Both still wrap at
their spaces, and an id longer than the line itself breaks at its hyphens again rather
than running off the screen.

On a real DOM, hermetic: the REAL overlay_mount.js, inv_core.js, inv_cmd.js, the real scan
accumulator and global.css (test_audit_question_dialog_58_js's `dialog`), in
`isolated_page`, so it runs under --offline. #confirmModal is the real markup of
templates/components/modals_core.html, its width set here (the hermetic page has no
Bootstrap). RED on f3ebcdd unless a test says it pins what was already right.
"""
from __future__ import annotations

import re
from pathlib import Path

from test_audit_panel_58_js import DONE, audit  # noqa: F401  (audit: the fixture)
from test_audit_question_dialog_58_js import BACK, QUESTION, TITLE, _question, dialog  # noqa: F401  (dialog: the fixture)
from test_audit_session_58 import env  # noqa: F401  (env: the fixture)
from test_scanner_safe_dialogs_61_js import page61  # noqa: F401  (page61: the fixture)

HUB = Path(__file__).resolve().parent.parent
MSG = QUESTION + " .fcc-apc-msg"
CONFIRM_MSG = "#confirm-msg"
PLACE = "SHELF-2-R3"

# How many lines each occurrence of `id` spans in the text under `sel`: 1 when it is whole.
LINES = r"""([sel, id]) => {
    const root = document.querySelector(sel);
    if (!root) return null;
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    const out = [];
    let node;
    while ((node = walker.nextNode())) {
        for (let i = node.data.indexOf(id); i !== -1; i = node.data.indexOf(id, i + 1)) {
            const range = document.createRange();
            range.setStart(node, i);
            range.setEnd(node, i + id.length);
            out.push(new Set(Array.from(range.getClientRects()).filter((r) => r.width > 0)
                .map((r) => Math.round(r.top))).size);
        }
    }
    return out;
}"""


def _ask_with(page, question):
    page.evaluate("(q) => { window.__answers['CMD:DONE'] = q; }", question)
    page.click(DONE)
    page.wait_for_function("(sel) => document.activeElement === document.querySelector(sel)", arg=BACK)


def _broken(page, sels, id_, widths, height=844):
    """At each window width, every occurrence of `id_` under each of `sels` that spans more
    than one line, and each of `sels` wider than its box: [(width, sel, what)]."""
    bad = []
    for width in widths:
        page.set_viewport_size({"width": width, "height": height})
        page.wait_for_timeout(30)
        for sel in sels:
            lines = page.evaluate(LINES, [sel, id_])
            assert lines, (width, sel)                  # the id is there
            if any(n != 1 for n in lines):
                bad.append((width, sel, lines))
            if page.evaluate("(s) => { const e = document.querySelector(s); return e.scrollWidth > e.clientWidth + 1; }",
                             sel):
                bad.append((width, sel, "runs past its box"))
    return bad


def test_dones_question_keeps_the_place_whole_in_its_title_and_words(dialog):
    """A file-only question ("File #200 in SHELF-2-R3?") and one that parks and files ("Park 3
    at Unknown and file 1 in SHELF-2-R3?"), from a phone's width to a small tablet's: the
    place never breaks at a hyphen, in the title or the words, and nothing runs past its
    box. RED on f3ebcdd: it broke at many of these widths."""
    for park in (0, 3):
        question = dict(_question(park=park, file=1), location=PLACE)
        _ask_with(dialog, question)
        title = " ".join(dialog.text_content(TITLE).split())
        assert PLACE in title and PLACE in dialog.text_content(MSG), title
        assert _broken(dialog, [TITLE, MSG], PLACE, range(300, 470, 3)) == [], park
        dialog.keyboard.press("Escape")                  # back to the audit
        dialog.wait_for_selector(QUESTION, state="detached")
        dialog.set_viewport_size({"width": 1600, "height": 1300})
        dialog.wait_for_timeout(750)                     # past a double press, for the next Done


def _confirm(page):
    """#confirmModal's real markup on the page, shown (`.modal.show` is display: block on the
    hermetic page), in a dialog as wide as `--w`."""
    src = (HUB / "templates" / "components" / "modals_core.html").read_text(encoding="utf-8")
    markup = re.search(r'<div class="modal fade" id="confirmModal".*?\n</div>\n', src, re.S)
    assert markup
    page.evaluate("""(html) => { document.body.insertAdjacentHTML('beforeend', html);
        const m = document.getElementById('confirmModal'); m.classList.add('show');
        const st = document.createElement('style');
        st.textContent = '#confirmModal .modal-dialog { width: var(--w, 30rem); } #confirm-msg { font-size: 1.75rem; }';
        document.head.appendChild(st); }""", markup.group(0))


def _confirm_at(page, width):
    page.evaluate("(w) => { document.documentElement.style.setProperty('--w', w + 'px'); }", width)
    page.evaluate("() => { const m = document.getElementById('confirmModal');"
                  " m.dispatchEvent(new Event('shown.bs.modal', { bubbles: true })); }")


def test_the_confirm_dialogs_message_keeps_the_place_whole(dialog):
    """Undo Last Move's question ("Undo: put 12 spools back in SHELF-2-R3?", the server's
    describe_undo) in #confirmModal, from a phone's dialog to a laptop's: the place never
    breaks at a hyphen, and the message still wraps at its spaces. RED on f3ebcdd: innerText
    let it break ("SHELF-2- / R3")."""
    _confirm(dialog)
    dialog.evaluate("() => requestConfirmation('Undo: put 12 spools back in SHELF-2-R3?', () => {})")
    assert " ".join(dialog.text_content(CONFIRM_MSG).split()) == "Undo: put 12 spools back in SHELF-2-R3?"
    bad = []
    # From the narrowest dialog the id fits on a line of its own (its whole width and the
    # box's padding; narrower, it breaks at its hyphens, which the last test pins).
    for width in range(230, 500, 3):
        _confirm_at(dialog, width)
        lines = dialog.evaluate(LINES, [CONFIRM_MSG, PLACE])
        if lines != [1]:
            bad.append((width, lines))
    assert bad == []
    _confirm_at(dialog, 200)
    assert dialog.evaluate("(s) => document.querySelector(s).getClientRects().length > 0 && "
                           "document.querySelector(s).getBoundingClientRect().height > 60", CONFIRM_MSG)   # it wraps


def test_the_confirm_dialogs_message_is_escaped_keeps_its_line_breaks_and_never_runs_off(dialog):
    """What innerText gave and the whole id must not take away: markup in a message is its
    text, a line break is one, and an id longer than the line itself breaks at its hyphens
    once the dialog is shown, rather than running off a phone. Pins what was right."""
    _confirm(dialog)
    dialog.evaluate("() => requestConfirmation('Delete <b>LR-MDB-1</b>?\\nIts spool goes to Unassigned.', () => {})")
    got = dialog.evaluate("(s) => { const e = document.querySelector(s); return { text: e.textContent, "
                          "brs: e.querySelectorAll('br').length, bold: e.querySelectorAll('b').length }; }", CONFIRM_MSG)
    assert got == {"text": "Delete <b>LR-MDB-1</b>?Its spool goes to Unassigned.", "brs": 1, "bold": 0}, got
    long_id = "LIVING-ROOM-WALL-SHELF-12-ROW-3"
    dialog.evaluate("(id) => requestConfirmation('Delete ' + id + '?', () => {})", long_id)
    _confirm_at(dialog, 200)
    assert dialog.evaluate("(s) => { const e = document.querySelector(s); return e.scrollWidth <= e.clientWidth + 1; }",
                           CONFIRM_MSG)
    _confirm_at(dialog, 900)                                 # room again: whole once more
    assert dialog.evaluate(LINES, [CONFIRM_MSG, long_id]) == [1]
