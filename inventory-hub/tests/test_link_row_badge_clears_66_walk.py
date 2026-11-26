"""Group 66's picture walk: a link row's "✗ … ✕" badge clears the row as its ✕ does.

The badge says "Click to clear this row" (its title), and both of the box's badges took a
click: Edit Spool's yellow refusal ("✗ Not a Prusament spool's link ✕", Group 66.3) and
the Add wizard's red failed scan ("✗ Not a Prusament URL ✕", 2026-04-26). The click ran
the row's check with no link, which dropped the badge but left the link's text in the box:
the box looked filled with nothing said about it, and the next Tab through it checked the
same text again. Round 1's R4-04 made the ✕ beside the box empty it first
(`wizardClearSpoolRow`); the badges now call that same clear.

Hermetic, on the Group 66.3 page harness (the 58.5 wizard page), so it runs under
--offline. Each case marked RED fails on a93605bf for the reason it names.
"""
from __future__ import annotations

from test_prusament_link_page_66_3 import ROW, _open, _row, _scan, _value
from test_wizard_label_status_58_5 import wizard  # noqa: F401  (the fixture)

BADGE = "[data-spool-row-idx='0'] .badge"
NOT_A_SPOOL = "https://example.com/not-a-spool"


def _tab_through(page):
    page.locator(ROW).focus()
    page.locator(ROW).press("Tab")
    page.wait_for_timeout(100)


def test_edit_spools_refusal_badge_empties_the_box(wizard):  # noqa: F811
    """RED: the click left "https://example.com/not-a-spool" in the box with no badge, and a
    Tab through it refused it again."""
    _open(wizard)
    _scan(wizard, NOT_A_SPOOL)
    assert _row(wizard)["status"] == "refused"
    wizard.locator(BADGE).click()
    wizard.wait_for_timeout(60)
    assert _value(wizard, ROW) == ""
    assert _row(wizard)["status"] == "empty"
    _tab_through(wizard)
    assert _row(wizard)["status"] == "empty"
    assert wizard.locator(BADGE).count() == 0


def test_a_refusal_over_a_link_goes_back_to_the_link(wizard):  # noqa: F811
    """A different product's QR scanned over a link waiting for Save is refused, and the
    earlier link stays (round 1's R5-01). The badge's click then clears only the refused
    QR, as its ✕ does: the box shows the earlier QR again, waiting for Save (review round
    3, R3-05; tests/test_review3_link_row_66.py has the rest). RED on a93605bf: the box kept
    the refused QR's text."""
    from test_prusament_link_page_66_3 import TEMPLATE
    _open(wizard)
    _scan(wizard)
    assert _row(wizard)["status"] == "linked-new"
    wizard.evaluate("(t) => { window.__answers['/api/external/search'] = { success: true, results: [t] }; }",
                    dict(TEMPLATE, color_name="Jet Black", name="Prusament PLA Jet Black"))
    _scan(wizard, "https://prusament.com/spool/17705/fff999eee8")
    assert _row(wizard)["status"] == "refused"
    assert _value(wizard, "#wiz-spool-product_url") != ""        # the earlier link stays
    wizard.locator(BADGE).click()
    wizard.wait_for_timeout(60)
    assert _value(wizard, ROW).lower() == "https://prusament.com/spool/17705/abc123def0"
    assert _row(wizard)["status"] == "linked-new"
    assert _value(wizard, "#wiz-spool-product_url") != ""        # still waiting for Save


def test_the_adds_failed_scan_badge_empties_the_box(wizard):  # noqa: F811
    """The Add wizard's red badge the same way. RED: its click left the text in the box."""
    wizard.evaluate("() => window.openWizardModal()")
    wizard.wait_for_function("() => wizardState.mode === 'manual' && (wizardState.spoolRows || []).length >= 1")
    wizard.locator(ROW).fill(NOT_A_SPOOL)
    wizard.locator(ROW).press("Tab")
    wizard.wait_for_function("() => wizardState.spoolRows[0].status === 'error'")
    wizard.locator(BADGE).click()
    wizard.wait_for_timeout(60)
    assert _value(wizard, ROW) == ""
    assert wizard.evaluate("() => wizardState.spoolRows[0].status") == "empty"
    assert wizard.locator(BADGE).count() == 0
