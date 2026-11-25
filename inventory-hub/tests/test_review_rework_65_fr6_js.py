"""Group 65 fix review, round 6: an Enter in How far it got while the 🛑 card is busy
(hermetic: the real cancel_review.js under node).

  - CU1 / AU2 (yellow): a double press of Enter works the card out once: the second Enter's
    figure is the one the first just worked out (33.33 went out again as 33.3).
  - CU2 (yellow): a queued copy of a figure FCC refused goes with the refusal's own words,
    never "press Enter again" after it.
  - CU3 / AU3 (yellow): a box changed after the queued Enter (put back to the old figure, or to
    the card's new one) is said, never overwritten and worked out at the queued figure.
  - CU4 (yellow): an Enter on a card kept as drawn after a read that failed reads the card again
    first and works its figure out on the revision FCC holds, never refused as stale.
  - AU1 (yellow): a double press on a card another device changed: the figure refused as stale
    isn't worked out over the other device's choice by the second Enter.
  - CZ1 (a) / (c) (yellow): a typo pressed while the card is busy is still said once the card
    is drawn again; a stale Confirm's redraw says when How far it got holds a figure the card
    isn't worked out at.

Red on 04ce498f (fix review 5's fixes).
"""
from __future__ import annotations

from test_cancel_review_picker_scan_js import (  # noqa: F401  (pytestmark: skip without node)
    RESPOND_JS, SPOOLS, pytestmark, run)
from test_review_basis_65_1_js import SERVER_JS, _cards
from test_review_rework_65_fr5_js import BUSY_JS
from test_review_rework_65_r1_js import LOOKUP_JS

JS = RESPOND_JS + SERVER_JS + LOOKUP_JS + BUSY_JS


def test_a_double_enter_works_the_card_out_once(tmp_path):
    res = run(tmp_path, JS + r"""
const box = cardOf('a').querySelector('.fcc-cr-pct');
box.focus();
box.value = '33.33';
key(box, 'Enter');
await settle(30);
key(box, 'Enter');                         // the double press's second Enter, the card busy
await settle(900);
return { worked: worked(), said: said() };
""", {"pending": _cards(), "spools": SPOOLS})
    assert res["worked"] == [33.33], res


def test_a_queued_copy_of_a_refused_figure_goes_with_the_refusal(tmp_path):
    res = run(tmp_path, JS + r"""
answer = () => ({ status: 'error', msg: "T0's spool was changed later in the print than that, so it got further: type a higher percentage." });
const box = cardOf('a').querySelector('.fcc-cr-pct');
box.focus();
box.value = '40';
key(box, 'Enter');
await settle(30);
key(box, 'Enter');
await settle(900);
return { worked: worked(), notice: notice('a') };
""", {"pending": _cards(), "spools": SPOOLS})
    assert res["worked"] == [40], res
    assert "type a higher percentage" in res["notice"] and "press Enter again" not in res["notice"], res


def test_a_box_put_back_after_a_queued_enter_is_said_never_worked_out(tmp_path):
    for back in ("30", "100"):              # the old card's figure, or the new card's
        res = run(tmp_path, JS + r"""
const c = cardOf('a');
c.querySelector('.fcc-cr-whole').click();
await settle(30);
const box = c.querySelector('.fcc-cr-pct');
box.focus();
box.value = '40';
key(box, 'Enter');                         // queued
await settle(20);
box.value = '__BACK__';                    // he puts it back, with no Enter
await settle(900);
return { worked: worked(), notice: notice('a') };
""".replace("__BACK__", back), {"pending": _cards(), "spools": SPOOLS})
        assert res["worked"] == ["whole"], (back, res)
        assert "40% wasn’t worked out: How far it got changed after you pressed Enter." in res["notice"], (back, res)


def test_an_enter_on_a_card_kept_as_drawn_reads_it_again_first(tmp_path):
    res = run(tmp_path, JS + r"""
// FCC worked the card out for the whole print (rev 1), but this page couldn't read the list.
pending = pending.map((r) => r.job_id === 'a' ? atBasis(r, 'whole', r.spools) : r);
const c = cardOf('a');
c.dataset.stale = '1';
const box = c.querySelector('.fcc-cr-pct');
box.focus();
box.value = '70';
key(box, 'Enter');                         // as the card's words say: press Enter again
await settle(900);
return { worked: posts('/api/cancel_deduct/recompute').map((p) => [p.rev, p.percent]), said: said() };
""", {"pending": _cards(), "spools": SPOOLS})
    assert res["worked"] == [[1, 70]], res
    assert res["said"] == "Worked out at 70%.", res


def test_a_double_enter_on_a_card_another_device_changed_leaves_its_choice(tmp_path):
    res = run(tmp_path, JS + r"""
pending = pending.map((r) => r.job_id === 'a' ? atBasis(r, 'whole', r.spools) : r);   // rev 1, whole
const box = cardOf('a').querySelector('.fcc-cr-pct');
box.focus();
box.value = '70';
key(box, 'Enter');                         // refused as stale
await settle(30);
key(box, 'Enter');                         // the double press's second Enter
await settle(900);
return { worked: posts('/api/cancel_deduct/recompute').map((p) => [p.rev, p.percent]), said: said(),
         notice: notice('a') };
""", {"pending": _cards(), "spools": SPOOLS})
    assert res["worked"] == [[0, 70]], res
    assert res["said"] == "Worked out for the whole print.", res
    assert "70% wasn’t worked out: type it again if you still mean it." in res["notice"], res


def test_a_typo_pressed_while_the_card_is_busy_is_said_after_the_redraw(tmp_path):
    res = run(tmp_path, JS + r"""
const c = cardOf('a');
c.querySelector('.fcc-cr-whole').click();
await settle(30);
const box = c.querySelector('.fcc-cr-pct');
box.focus();
box.value = '7o';
key(box, 'Enter');
await settle(900);
return { worked: worked(), notice: notice('a') };
""", {"pending": _cards(), "spools": SPOOLS})
    assert res["worked"] == ["whole"], res
    assert "“7o” in How far it got isn’t a percentage from 0 to 100, so it wasn’t worked out." in res["notice"], res


def test_a_stale_confirms_redraw_says_a_figure_the_card_isnt_worked_out_at(tmp_path):
    res = run(tmp_path, JS + r"""
pending = pending.map((r) => r.job_id === 'a' ? atBasis(r, 'whole', r.spools) : r);
const c = cardOf('a');
c.dataset.stale = '1';
c.querySelector('.fcc-cr-pct').value = '70';   // typed, never worked out
c.querySelector('.fcc-cr-confirm').click();
await settle(600);
return { notice: notice('a'), said: said(), worked: worked() };
""", {"pending": _cards(), "spools": SPOOLS})
    assert res["worked"] == [], res
    assert "How far it got reads 70%, which isn’t worked out: press Enter to work it out." in res["notice"], res
