"""Review round 3 of Group 66 (scan-journal R3-02, older than the group): a label scanned
while one of the wizard's dropdowns has the keyboard leaves the dropdown as it was.

A dropdown's keys go to the scan accumulator (the field capture takes boxes only), and the
browser's type-ahead moved the dropdown by the label's first letters: with Existing
Filament's list, "ID:57" picked the first filament starting with I (its change made it the
filament Save uses) and Create made the new spool under it; "SPL:57" picked the next Sunlu.
The location editor's dropdowns had the rule already (Group 61): the keys typed on the
dropdown are judged at the Enter; a burst, a ':' or '/', or a search that starts none of
its options is a scan; the dropdown goes back to what it held before the scan's first key
(a person's jump just before it stays), its change runs again for that pick, and a toast
says so. In the wizard the changed flag, the post-create lock (Save and its status line)
and the touched sets go back too: a scan is no edit.

Hermetic, on the Group 58.5 wizard page, so it runs under --offline. That page has no scan
accumulator (scripts.html), so a stand-in plays its part: it collects a dropdown's keys in
state.scanBuffer and, at an Enter, sends what it holds. Each case marked RED fails on
41c55db2 for the reason it names; the others are pins.
"""
from __future__ import annotations

import pytest

from test_wizard_label_status_58_5 import wizard  # noqa: F401  (the fixture)

CREATE = "/api/create_inventory_wizard"


def _fil(fid, vendor, name):
    return {"id": fid, "name": name, "material": "PLA", "color_hex": "222222", "weight": 1000.0,
            "spool_weight": 200.0, "density": 1.24, "diameter": 1.75, "extra": {},
            "vendor": {"id": fid + 10, "name": vendor, "extra": {}}}


FILAMENTS = [_fil(1, "Generic", "Red"), _fil(2, "Inland", "Blue"), _fil(3, "Sunlu", "Black"), _fil(4, "Sunlu", "Grey")]

# The scan accumulator's part for a dropdown's keys (scripts.html reads keys typed anywhere
# but in a box): its buffer, sent at an Enter.
ACCUMULATOR = r"""() => {
    const st = (typeof state !== 'undefined') ? state : (window.state = window.state || {});
    st.scanBuffer = '';
    window.__scans = [];
    document.addEventListener('keydown', (e) => {
        const tag = (e.target && e.target.tagName) || '';
        if (tag === 'INPUT' || tag === 'TEXTAREA') return;
        if (e.key === 'Enter') { if (st.scanBuffer) window.__scans.push(st.scanBuffer); st.scanBuffer = ''; return; }
        if (e.key.length === 1) st.scanBuffer += e.key;
    });
}"""


def _existing(page, pick):
    page.evaluate("(a) => { Object.assign(window.__answers, a); }", {
        "/api/filaments": {"success": True, "filaments": FILAMENTS},
        CREATE: {"success": True, "created_spools": [58], "filament_id": int(pick)},
    })
    page.evaluate(ACCUMULATOR)
    page.evaluate("() => window.openWizardModal()")
    page.wait_for_function("() => !!document.getElementById('wiz_fil_ef_needs_label_print')")
    page.locator("#btn-type-existing").click()
    page.wait_for_function("() => !!document.querySelector(\"#wiz-existing-results option[value='1']\")")
    page.locator("#wiz-existing-results").select_option(pick)     # the person's pick
    page.focus("#wiz-existing-results")
    page.wait_for_timeout(1200)                                    # past the list's type-ahead reset


def _scan(page, label):
    page.keyboard.type(label, delay=8)
    page.keyboard.press("Enter")
    page.wait_for_timeout(200)


def _picked(page):
    return page.evaluate("() => String(wizardState.selectedFilamentId)")


def _toasts(page):
    return page.locator("#toast-container").inner_text()


def _created_filament(page):
    page.locator("#btn-wiz-submit").click()
    page.wait_for_function("(u) => window.__posts.some((p) => p.url === u)", arg=CREATE)
    body = page.evaluate("(u) => window.__posts.filter((p) => p.url === u).slice(-1)[0].body", CREATE)
    return str(body.get("filament_id", body.get("existing_filament_id")))


@pytest.mark.parametrize("label, pick", [("ID:57", "1"), ("SPL:57", "3")])
def test_a_label_scanned_on_the_filament_list_leaves_the_pick(wizard, label, pick):  # noqa: F811
    """RED: ID:57 moved the pick from #1 to #2 (Inland, the first starting with I), SPL:57
    from #3 to #4 (the next Sunlu), and Create made the spool under it."""
    _existing(wizard, pick)
    _scan(wizard, label)
    assert _picked(wizard) == pick
    assert wizard.evaluate("() => document.getElementById('wiz-existing-results').value") == pick
    assert wizard.evaluate("() => window.__scans") == [label]
    assert "back to" in _toasts(wizard)
    assert _created_filament(wizard) == pick
    assert wizard.evaluate("() => window.__errors") == []


def test_a_label_on_the_list_after_a_create_keeps_save_locked(wizard):  # noqa: F811
    """After a create, Save stays locked until the person changes something; a scan on the
    list is no change. RED: the scan's letters moved the list, its change lifted the lock
    (Save enabled, the status line cleared)."""
    _existing(wizard, "1")
    _created_filament(wizard)
    wizard.wait_for_function("() => document.getElementById('btn-wiz-submit').disabled")
    status = wizard.locator("#wiz-status-msg").inner_html()
    wizard.focus("#wiz-existing-results")
    wizard.wait_for_timeout(1200)
    _scan(wizard, "ID:57")
    assert wizard.evaluate("() => document.getElementById('btn-wiz-submit').disabled") is True
    assert wizard.locator("#wiz-status-msg").inner_html() == status
    assert wizard.evaluate("() => wizardState.lockedAfterSuccess") is True


def test_a_persons_jump_just_before_a_scan_stays(wizard):  # noqa: F811
    """The person types "In" (Inland, #2), and a second later a label is scanned: the list
    goes back to Inland, the person's jump, not to their earlier pick."""
    _existing(wizard, "1")
    wizard.keyboard.type("In", delay=150)
    wizard.wait_for_timeout(1200)
    assert _picked(wizard) == "2"
    _scan(wizard, "SPL:57")
    assert _picked(wizard) == "2"
    assert wizard.evaluate("() => window.__scans") == ["SPL:57"]      # without the jump's "In"


def test_a_persons_typeahead_moves_the_list(wizard):  # noqa: F811
    """A pin: letters a person types to jump to a filament ("Su") move the list, and
    nothing puts it back."""
    _existing(wizard, "1")
    wizard.keyboard.type("Su", delay=150)
    wizard.keyboard.press("Enter")
    wizard.wait_for_timeout(200)
    assert _picked(wizard) == "3"
    assert "back to" not in _toasts(wizard)


def test_a_label_that_moves_nothing_says_nothing(wizard):  # noqa: F811
    """A pin: a label no option starts with ("LOC:SHELF-1") leaves the list where it was,
    with no toast, and goes on as a scan."""
    _existing(wizard, "1")
    _scan(wizard, "LOC:SHELF-1")
    assert _picked(wizard) == "1"
    assert "back to" not in _toasts(wizard)
    assert wizard.evaluate("() => window.__scans") == ["LOC:SHELF-1"]
