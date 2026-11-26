"""Review round 3 of Group 66: an answer that lands while a label is being scanned into a
wizard box (scan-journal R3-01, tests-adversary R3-02 and R3-03).

Round 2's key journal undoes what a label's keys changed, each thing only while it holds
what that key left it. Round 3 found three ways an answer landing mid-label still went wrong:
  - R3-01: a key the box rejects (a letter in a number box) fires no `input`, so its record
    stayed open until a 0 ms timer; a lookup's answer queued meanwhile was journaled as that
    key's change and undone at the label's Enter: Step 2's fill blanked and Save greyed out.
  - R3-02: an answer works things out FROM the boxes: a Prusament lookup landing while a
    label was in Scale Gross worked Total Used out from the label's digit, and the undo kept
    that (no key changed it): Create made the new spool empty.
  - R3-03: no test pinned the journal's own rule (an unconditional undo passed every case).
Now the wizard's answers that fill its form (the Prusament lookups, the filament follow,
the vendor, location and extra-field lists, the global search's pick) wait while a label
may be arriving in a wizard box, and apply on the form as the label left it; and a key's
record ends with its own dispatch (its keydown, then its text's beforeinput to input), so
nothing that lands between keys is journaled as theirs.

Hermetic, on the Group 58.5 harness (the 54.5 `wiz` page), so it runs under --offline.
Each case marked RED fails on 41c55db2 for the reason it names; the others are pins.
"""
from __future__ import annotations

from test_review2_wizard_scan_66 import LOOKUP, _open_manual, scanning  # noqa: F401  (the fixture)
from test_wizard_label_status_58_5 import _save
from test_wizard_native_clear_54_5 import _tab_in, wiz  # noqa: F401  (scanning's fixture)
from test_wizard_scan_capture_66_4 import PRUSAMENT, _scans

CREATE = "/api/create_inventory_wizard"

HOLD = """(answer) => {
    const real = window.fetch;
    window.__held = null;
    window.fetch = (url, opts) => {
        if (String(url).indexOf('/api/external/search') >= 0) {
            return new Promise((res) => {
                window.__held = () => res({ ok: true, status: 200, json: () => Promise.resolve(answer) });
            });
        }
        return real(url, opts);
    };
}"""


def _qr_in_spool_1(page):
    page.focus("[data-spool-row-idx='0'] input[type='url']")
    page.keyboard.type(PRUSAMENT, delay=5)
    page.keyboard.press("Enter")
    page.wait_for_function("() => !!window.__held")


def _filled(page):
    return page.evaluate("""() => ({ save: document.getElementById('btn-wiz-submit').disabled,
        rows: wizardState.spoolRows.map((r) => r.status),
        material: document.getElementById('wiz-fil-material').value,
        colour: document.getElementById('wiz-fil-color_name').value })""")


def test_an_answer_queued_inside_a_rejected_keys_keydown_is_kept(scanning):
    """R3-01. Two Spool boxes, a QR in the first (its lookup held); a spool label scanned into
    Price Paid, a number box that rejects its letters; the lookup answers in a task queued
    while the label's first key is handled. RED: Save disabled with every row ok, Step 2
    blank, and wizardScanUntracked named externalMetaData and filamentLockedFromScan."""
    _open_manual(scanning)
    scanning.fill("#wiz-spool-qty", "2")
    scanning.evaluate(HOLD, LOOKUP)
    _qr_in_spool_1(scanning)
    scanning.focus("#wiz-spool-price")
    scanning.keyboard.press("End")
    scanning.wait_for_timeout(300)
    scanning.evaluate("""() => {
        window.addEventListener('keydown', function once(e) {
            if (e.key !== 'I' || e.target.id !== 'wiz-spool-price') return;
            window.removeEventListener('keydown', once, true);
            setTimeout(() => window.__held(), 0);
        }, true);
    }""")
    scanning.keyboard.type("ID:57", delay=8)
    scanning.keyboard.press("Enter")
    scanning.wait_for_function("() => wizardState.spoolRows[0].status === 'ok'")
    scanning.wait_for_timeout(100)
    assert _filled(scanning) == {"save": False, "rows": ["ok", "empty"], "material": "PLA",
                                 "colour": "Galaxy Black"}, _filled(scanning)
    assert _scans(scanning) == ["ID:57"]


def _scale(page):
    return page.evaluate("""() => ({ scale: document.getElementById('wiz-spool-scale').value,
        used: document.getElementById('wiz-spool-used').value,
        remaining: document.getElementById('wiz-spool-remaining').value })""")


def test_an_answer_landing_mid_label_in_scale_gross_works_from_the_persons_reading(scanning):
    """R3-02. The person's reading (1186 g) in Scale Gross, a QR in Spool 1 (its lookup held),
    then a label read into Scale Gross; the lookup lands mid-label. RED: Total Used 1000 and
    Remaining 0 (worked out from the label's '5'), and Create sent used_weight 1000."""
    _open_manual(scanning)
    scanning.evaluate(HOLD, LOOKUP)
    scanning.focus("#wiz-spool-scale")
    scanning.keyboard.type("1186", delay=120)
    _qr_in_spool_1(scanning)
    _tab_in(scanning, "#wiz-spool-scale")
    scanning.keyboard.type("ID:5", delay=8)
    scanning.evaluate("() => window.__held()")
    scanning.wait_for_timeout(50)
    scanning.keyboard.type("7", delay=8)
    scanning.keyboard.press("Enter")
    scanning.wait_for_function("() => wizardState.spoolRows[0].status === 'ok'")
    scanning.wait_for_timeout(150)
    assert _scale(scanning) == {"scale": "1186", "used": "0", "remaining": "1000"}, _scale(scanning)
    assert _save(scanning, CREATE)["spool_data"].get("used_weight") in (0, None)
    assert _scans(scanning) == ["ID:57"]


def test_an_answer_landing_mid_label_in_an_empty_scale_box_leaves_used_alone(scanning):
    """R3-02, the empty variant: nothing on the scale. RED: Total Used 1000 from the label's
    '5'."""
    _open_manual(scanning)
    scanning.evaluate(HOLD, LOOKUP)
    _qr_in_spool_1(scanning)
    _tab_in(scanning, "#wiz-spool-scale")
    scanning.keyboard.type("ID:5", delay=8)
    scanning.evaluate("() => window.__held()")
    scanning.wait_for_timeout(50)
    scanning.keyboard.type("7", delay=8)
    scanning.keyboard.press("Enter")
    scanning.wait_for_function("() => wizardState.spoolRows[0].status === 'ok'")
    scanning.wait_for_timeout(150)
    got = _scale(scanning)
    assert got["scale"] == "" and got["used"] in ("", "0"), got


def test_a_write_between_a_labels_keys_stays_the_journals_rule(scanning):
    """R3-03, a pin of the journal's own rule: a label scanned into the filament's Spool Wt
    box, whose digits the spool's box follows (66.5), and code that writes the spool's box
    between two of its keys (a writer the wait doesn't hold). The label's Enter puts back
    what its keys changed only where each still holds what that key left: the spool's box
    keeps the code's 186. RED with the rule removed: the box went back to ''."""
    _open_manual(scanning)
    _tab_in(scanning, "#wiz-fil-empty_weight")
    scanning.keyboard.type("ID:5", delay=8)
    assert scanning.evaluate("() => document.getElementById('wiz-spool-empty_weight').value") == "5"
    scanning.evaluate("() => { document.getElementById('wiz-spool-empty_weight').value = '186'; }")
    scanning.keyboard.type("7", delay=8)
    scanning.keyboard.press("Enter")
    scanning.wait_for_timeout(150)
    got = scanning.evaluate("""() => ({ fil: document.getElementById('wiz-fil-empty_weight').value,
        spool: document.getElementById('wiz-spool-empty_weight').value })""")
    assert got == {"fil": "", "spool": "186"}, got
    assert _scans(scanning) == ["ID:57"]


def test_a_rows_answer_after_the_row_was_scanned_again_fills_nothing(scanning):
    """The lookup of a QR the row no longer holds (another scanned into it meanwhile) changes
    nothing when it lands: only the row's newest answer does. RED: the first QR's late
    answer marked the row ok with its own data over the second's."""
    _open_manual(scanning)
    scanning.evaluate("""(answer) => {
        const real = window.fetch;
        window.__heldQ = [];
        window.fetch = (url, opts) => {
            if (String(url).indexOf('/api/external/search') >= 0) {
                return new Promise((res) => {
                    window.__heldQ.push((a) => res({ ok: true, status: 200, json: () => Promise.resolve(a) }));
                });
            }
            return real(url, opts);
        };
    }""", LOOKUP)
    box = "[data-spool-row-idx='0'] input[type='url']"
    scanning.focus(box)
    scanning.keyboard.type(PRUSAMENT, delay=5)
    scanning.keyboard.press("Enter")
    scanning.wait_for_function("() => (window.__heldQ || []).length === 1")
    other = "https://prusament.com/spool/17706/fff999eee8/"
    scanning.fill(box, other)
    scanning.locator(box).press("Enter")
    scanning.wait_for_function("() => window.__heldQ.length === 2")
    first = {"success": True, "results": [dict(LOOKUP["results"][0], spool_weight=111)]}
    scanning.evaluate("(a) => window.__heldQ[0](a)", first)       # the first QR's, late
    scanning.wait_for_timeout(150)
    row = scanning.evaluate("() => ({ status: wizardState.spoolRows[0].status, url: wizardState.spoolRows[0].url,"
                            " sw: (wizardState.spoolRows[0].override || {}).spool_weight })")
    assert row == {"status": "pending", "url": other, "sw": None}, row
    scanning.evaluate("(a) => window.__heldQ[1](a)", LOOKUP)
    scanning.wait_for_function("() => wizardState.spoolRows[0].status === 'ok'")
    assert scanning.evaluate("() => wizardState.spoolRows[0].override.spool_weight") == 186
