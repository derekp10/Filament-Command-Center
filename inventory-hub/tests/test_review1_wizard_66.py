"""Group 66, review round 1: the wizard's fixes outside the link row.

R3-05: Weigh from Scale puts its reading in the form by code, which marked nothing
changed: 66.2's guard then started an Edit over with no question (a new Prusament
spool's QR, any open), and the reading was lost. A reading now counts as the person's
change, as a box they type in does (and lifts a create's lock the same way).

Hermetic, on the Group 58.5 harness. Each case fails on the commit before the fix for
the reason it names.
"""
from __future__ import annotations

from test_wizard_native_clear_54_5 import _open_edit, wiz  # noqa: F401  (the fixture)

WEIGH = r"""() => {
    window.WeightEntry = { openModal: (o) => { window.__we = o; } };
    window.wizardOpenWeightEntry();
}"""


def test_a_reading_from_weigh_from_scale_counts_as_a_change(wiz):  # noqa: F811
    """R3-05. RED: the reading marked nothing changed, and the next open started the edit
    over with no question."""
    _open_edit(wiz)
    assert wiz.evaluate("() => wizardState.isDirty") is False
    wiz.evaluate(WEIGH)
    wiz.evaluate("() => window.__we.onSubmit({ mode: 'gross', used_weight: 130, empty_spool_weight: null })")
    assert wiz.evaluate("() => document.getElementById('wiz-spool-used').value") == "130"
    assert wiz.evaluate("() => wizardState.isDirty") is True
    wiz.evaluate("() => { window.openWizardModal(); }")
    wiz.wait_for_selector("#fcc-wiz-dirty-confirm")
    assert wiz.evaluate("() => wizardState.mode") == "edit_spool"
