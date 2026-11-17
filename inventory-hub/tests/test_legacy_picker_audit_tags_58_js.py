"""Group 58, Derek's second look (2026-11-03, section H): the legacy shared-label picker,
during an audit, says which candidates are on this audit's list and whether they're found
yet (builder B, Q3). From what the page already knows, the audit session it read last
(window.auditStandingOf), never a request of its own; outside an audit nothing changes.

On a real DOM, hermetic: the REAL overlay_mount.js, inv_core.js, inv_cmd.js,
duplicate_picker.js, the real scan accumulator and global.css (test_audit_panel_58_js's
`audit`: the panel up on test_audit_page_58_js.SESSION, the route's shape), in
`isolated_page`, so it runs under --offline. The picker's scan rules are
test_scanner_safe_dialogs_61_js.py's; the contrast and text-size guards' are on the real
dashboard.

RED on the commit before Q3's unless a test says it pins what was already right.
"""
from __future__ import annotations

import pytest

from test_audit_panel_58_js import PANEL, audit  # noqa: F401  (audit: the fixture)
from test_audit_page_58_js import SESSION
from test_scanner_safe_dialogs_61_js import page61  # noqa: F401  (page61: the fixture)

PICKER = "#fcc-legacy-picker-overlay"
SEL = "#fcc-legacy-picker-sel"
LINE = "#fcc-legacy-picker-audit"


def _candidate(sid, location):
    return {"id": sid, "remaining_weight": 500, "location": location, "archived": False, "filament_id": 7,
            "filament_name": "Galaxy Black", "material": "PLA", "vendor_name": "Some Brand", "display": f"#{sid}"}


# SESSION (the route's shape): #57 found and #99 not scanned on LR-MDB-1's list, #200 an
# Extra, #242 loaded from LR-MDB-1. #300 is on no list of this audit.
SHARED = {"type": "ambiguous", "legacy_id": "120", "candidates": [
    _candidate(300, "LR"), _candidate(242, "XL-1"), _candidate(57, "LR-MDB-1"), _candidate(200, "LR-MDB-2"),
    _candidate(99, "LR-MDB-1")]}


def _open(page, answer=None):
    page.evaluate("(a) => { window.__answers['LEG:120'] = a; window.processScan('LEG:120', 'barcode'); }", answer or SHARED)
    page.wait_for_selector(PICKER)
    page.wait_for_function("() => document.activeElement && document.activeElement.id === 'fcc-legacy-picker-use'")


def _groups(page):
    """The list as drawn: [heading, [spool ids]] per group, [None, ids] with none."""
    return page.evaluate("""(sel) => { const s = document.querySelector(sel);
        const groups = Array.from(s.querySelectorAll('optgroup'));
        if (!groups.length) return [[null, Array.from(s.options).map((o) => Number(o.value))]];
        return groups.map((g) => [g.label, Array.from(g.querySelectorAll('option')).map((o) => Number(o.value))]); }""", SEL)


def test_each_candidate_says_where_it_stands_in_the_audit(audit):
    """On the list and not scanned yet, on the list and found, found here as an Extra,
    loaded from here, or not on its list; in that order, each in the server's order, the
    audit's place named once above the list. Still nothing is picked (Group 58 review: a
    stray Enter would find the wrong spool)."""
    _open(audit)
    assert _groups(audit) == [["⬜ Expected there, not scanned yet", [99]], ["✅ Expected there, found already", [57]],
                              ["⚠️ Found there as an Extra", [200]], ["🔗 Loaded on a printer from there", [242]],
                              ["Not expected there", [300]]]
    assert audit.text_content(LINE) == "🕵️ The audit of LR-MDB-1 is running: the spools are listed by where each stands in it."
    assert audit.evaluate("(s) => document.querySelector(s).selectedIndex", SEL) == -1
    assert audit.get_attribute(SEL, "size") == "8"                     # five spools and five headings, at most 8 rows
    # Every option still starts with its number: a person's jump finds it.
    assert all(t.startswith(f"#{sid} — ") for sid, t in audit.evaluate(
        "(s) => Array.from(document.querySelector(s).options).map((o) => [Number(o.value), o.textContent])", SEL))


def test_no_request_of_its_own(audit):
    """What the page already knows: the session it read last, no new read."""
    reads = audit.evaluate("window.__sessionReads")
    _open(audit)
    audit.wait_for_timeout(100)
    assert audit.evaluate("window.__sessionReads") == reads


def test_outside_an_audit_the_list_is_as_it_always_was(audit):
    """No audit: no headings, no line, its old size. Pins what was right."""
    audit.evaluate("() => { window.closeAuditPanel(); state.auditActive = false; window.updateAuditVisuals(); }")
    _open(audit)
    assert _groups(audit) == [[None, [300, 242, 57, 200, 99]]]
    assert audit.locator(LINE).count() == 0
    assert audit.get_attribute(SEL, "size") == "5"


def test_an_audit_with_no_place_yet_tags_nothing(audit):
    """Before a location is scanned there is no list to be on."""
    audit.evaluate("""() => { window.__session = Object.assign({}, window.__session, { location_id: null, expected: [],
        rogue: [], trail: [] }); window.refreshAuditSession(); }""")
    audit.wait_for_function("() => document.querySelector('#fcc-audit-panel-body').textContent.includes('Scan a location')")
    _open(audit)
    assert _groups(audit) == [[None, [300, 242, 57, 200, 99]]] and audit.locator(LINE).count() == 0


def test_a_hidden_panel_still_tags_from_the_session_read_after_the_last_scan(audit):
    """With the panel hidden, each scan the audit takes reads the session again
    (window.refreshAuditSession): #99, found since, is found here too."""
    audit.click("#fcc-audit-panel-close")
    audit.wait_for_selector(PANEL, state="detached")
    found = dict(SESSION, expected=[dict(r, found=True) for r in SESSION["expected"]],
                 stats=dict(SESSION["stats"], found=2, missing=0))
    audit.evaluate("(s) => { window.__session = s; }", found)
    reads = audit.evaluate("window.__sessionReads")
    audit.evaluate("() => window.refreshAuditSession()")
    audit.wait_for_function("(n) => window.__sessionReads > n", arg=reads)
    audit.wait_for_timeout(50)
    _open(audit)
    assert _groups(audit)[0] == ["✅ Expected there, found already", [57, 99]]


def test_another_audits_session_tags_nothing(audit):
    """What the page read last is another audit's (one started since): no word of it."""
    audit.evaluate("() => { state.auditId = 'boot-2'; }")
    _open(audit)
    assert _groups(audit) == [[None, [300, 242, 57, 200, 99]]] and audit.locator(LINE).count() == 0


def test_a_persons_jump_and_enter_pick_the_spool_the_list_shows(audit):
    """Pins Group 61's rule under the headings: "#200" typed in the list jumps to it, and
    Enter picks it, as no label read."""
    _open(audit)
    audit.focus(SEL)
    audit.keyboard.type("#200", delay=120)
    assert audit.input_value(SEL) == "200"
    audit.keyboard.press("Enter")
    audit.wait_for_function("() => window.__ids.length === 2", timeout=5000)
    assert audit.evaluate("window.__ids")[1] == {"text": "ID:200", "source": "keyboard"}
    audit.wait_for_selector(PICKER, state="detached")


@pytest.mark.parametrize("label, source", [("ID:99", "barcode"), ("SPL:57", "keyboard")])
def test_a_listed_spools_own_label_still_picks_it(audit, label, source):
    """Pins Group 61's scan rule under the headings (test_scanner_safe_dialogs_61_js)."""
    _open(audit)
    audit.keyboard.type(label, delay=0)
    audit.keyboard.press("Enter")
    audit.wait_for_function("() => window.__ids.length === 2")
    sid = label.split(":")[1]
    assert audit.evaluate("window.__ids")[1] == {"text": f"ID:{sid}", "source": source}


def test_every_word_is_escaped(audit):
    bad = dict(SESSION, location_id="A<B")
    audit.evaluate("(s) => { window.__session = s; window.refreshAuditSession(); }", bad)
    audit.wait_for_function("() => document.querySelector('#fcc-audit-panel-tally').textContent.includes('A<B')")
    _open(audit)
    assert audit.text_content(LINE).startswith("🕵️ The audit of A<B is running")
    assert "<B" not in audit.inner_html(LINE).replace("&lt;B", "")
