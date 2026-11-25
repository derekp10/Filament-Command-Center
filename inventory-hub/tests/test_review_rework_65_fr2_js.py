"""Group 65 fix review, round 2: the 🛑 card's page (hermetic: the real cancel_review.js
under node).

  - RE1: a spool weighed while FCC couldn't see the print is headed as that, never as a
    weight that changed "after this print ended".
  - CA1 (orange): the keyboard comes back to a box as the person left it: a box whose figure
    the redraw replaced has the new figure selected (a digit typed next replaces it rather
    than joining it).
  - CA2 (orange): a key typed while the redraw reads the review list is kept (the card is
    read right before the fresh one takes its place).
  - CA5: a figure the person was typing in How far it got stays theirs, the keyboard with it.

Red on 2363aba3 (the second fix review's head).
"""
from __future__ import annotations

from test_cancel_review_picker_scan_js import (  # noqa: F401  (pytestmark: skip without node)
    RESPOND_JS, SPOOLS, pytestmark, run)
from test_review_basis_65_1_js import SERVER_JS, _cards
from test_review_rework_65_r1_js import LOOKUP_JS


def test_a_spool_weighed_while_fcc_couldnt_see_the_print_is_headed_as_that(tmp_path):
    cards = _cards()
    cards[0] = dict(cards[0], spools=[dict(cards[0]["spools"][0], prefill=12.0, weighed={
        "words": "#57 on HEAD-1 was weighed on Quick Weigh at 15:00, after FCC last saw the print (at 14:00) "
                 "and before it saw the printer again (at 16:00), so FCC can't tell whether the scale counted "
                 "this print's 12.00 g", "known_order": False, "unseen": True})])
    res = run(tmp_path, RESPOND_JS + "return { text: cardOf('a').querySelector('.fcc-cr-weighed').textContent };",
              {"pending": cards, "spools": SPOOLS})
    assert res["text"].strip().startswith("⚠️ Weighed while FCC couldn’t see the print: check before you Apply"), res
    assert "after this print ended" not in res["text"], res


def test_a_grams_box_comes_back_with_its_new_figure_selected(tmp_path):
    res = run(tmp_path, RESPOND_JS + SERVER_JS + LOOKUP_JS + r"""
answer = whole40;
const g = cardOf('a').querySelector('.fcc-cr-grams');
g.focus();
cardOf('a').querySelector('.fcc-cr-whole').click();
await settle(150);
const box = cardOf('a').querySelector('.fcc-cr-grams');
return { on: document.activeElement === box, value: box.value, selected: [box.selectionStart, box.selectionEnd] };
""", {"pending": _cards(), "spools": SPOOLS})
    assert res["on"] and res["value"] == "40" and res["selected"] == [0, 2], res


def test_a_key_typed_while_the_redraw_reads_the_list_is_kept(tmp_path):
    res = run(tmp_path, RESPOND_JS + SERVER_JS + LOOKUP_JS + r"""
answer = whole40;
let l = lineOf(cardOf('a'), '57');
pickIn(l.sel, 'other');
l.box.focus();
l.box.value = '4';
const before = window.__respond;
let answered = false;
window.__respond = (url, method, body) => {
  if (answered && url.startsWith('/api/cancel_deduct/pending')) {
    lineOf(cardOf('a'), '57').box.value = '42';      // typed while the redraw reads the list
  }
  if (url.startsWith('/api/cancel_deduct/recompute')) answered = true;
  return before(url, method, body);
};
cardOf('a').querySelector('.fcc-cr-whole').click();
await settle(150);
l = lineOf(cardOf('a'), '57');
return { box: l.box.value, on: document.activeElement === l.box };
""", {"pending": _cards(), "spools": SPOOLS})
    assert res == {"box": "42", "on": True}, res


def test_a_figure_being_typed_in_how_far_it_got_stays_the_persons(tmp_path):
    res = run(tmp_path, RESPOND_JS + SERVER_JS + LOOKUP_JS + r"""
answer = () => {
  const p = cardOf('a').querySelector('.fcc-cr-pct');   // typing 62 while FCC works it out
  p.focus();
  p.value = '62';
  return whole40();
};
cardOf('a').querySelector('.fcc-cr-whole').click();
await settle(150);
const box = cardOf('a').querySelector('.fcc-cr-pct');
return { value: box.value, on: document.activeElement === box, selected: [box.selectionStart, box.selectionEnd] };
""", {"pending": _cards(), "spools": SPOOLS})
    assert res == {"value": "62", "on": True, "selected": [2, 2]}, res
