"""Group 65 fix review, round 1: working a 🛑 card out again, the card (hermetic: the real
cancel_review.js under node).

  - CD1 (orange): a pick made while FCC works the card out is kept on the card drawn again
    (the picks are read when the answer comes, never at the press).
  - CD2: a recompute whose redraw can't read the review list gives every button back,
    Discard too, and says the card couldn't be drawn, never "Worked out" over the old grams.
  - CD3: a pick the fresh picker no longer lists is put back, its option listed again.
  - CD4: a worked-out card that can't be worked out again keeps its basis in its words.
  - CD5: the keyboard goes on where the person was typing on the card (the #ID box keeps it
    and its text); only from the basis controls does it go to How far it got.
  - PI3: while the card's Apply is out, Charge the whole print and Work it out wait.

Red on fddf1ceb (the fix review's head).
"""
from __future__ import annotations

from test_cancel_review_picker_scan_js import (  # noqa: F401  (pytestmark: skip without node)
    RESPOND_JS, SPOOLS, pytestmark, run)
from test_review_basis_65_1_js import SERVER_JS, _cards
from test_review_rework_65_r1_js import LOOKUP_JS


def test_a_pick_made_while_the_card_is_worked_out_is_kept(tmp_path):
    res = run(tmp_path, RESPOND_JS + SERVER_JS + LOOKUP_JS + r"""
answer = () => {
  const l = lineOf(cardOf('a'), '57');            // picked while FCC worked it out
  l.sel.value = 'other';
  l.box.value = 'ID:42';
  return whole40();
};
cardOf('a').querySelector('.fcc-cr-whole').click();
await settle(150);
const l = lineOf(cardOf('a'), '57');
return { value: l.sel.value, box: l.box.value, notice: notice('a') };
""", {"pending": _cards(), "spools": SPOOLS})
    assert (res["value"], res["box"]) == ("other", "ID:42"), res
    assert "your picks are kept" in res["notice"], res


def test_a_recompute_whose_redraw_cant_read_the_list_gives_every_button_back(tmp_path):
    res = run(tmp_path, RESPOND_JS + SERVER_JS + LOOKUP_JS + r"""
const before = window.__respond;
let listDown = false;
window.__respond = (url, method, body) => {
  if (listDown && url.startsWith('/api/cancel_deduct/pending')) return { status: 500, body: {} };
  return before(url, method, body);
};
answer = () => { listDown = true; return whole40(); };
const c = cardOf('a');
c.querySelector('.fcc-cr-whole').click();
await settle(150);
const now = cardOf('a');
return { same: now === c, discard: now.querySelector('.fcc-cr-discard').disabled,
         whole: now.querySelector('.fcc-cr-whole').disabled, notice: notice('a') };
""", {"pending": _cards(), "spools": SPOOLS})
    assert res["same"] and res["discard"] is False and res["whole"] is False, res
    # Group 65 fix review 2 (CA3): what the answer was, once; the card's own words say the
    # list couldn't be read.
    assert "FCC worked it out, but couldn’t draw it here." in res["notice"], res


def test_a_pick_the_fresh_picker_no_longer_lists_is_put_back(tmp_path):
    cards = _cards()
    cards[0] = dict(cards[0], heads_at_end=list(cards[0]["heads_at_end"])
                    + [{"toolhead": "HEAD-1", "position": 0, "sid": 99, "when": "start"}])
    res = run(tmp_path, RESPOND_JS + SERVER_JS + LOOKUP_JS + r"""
answer = () => {
  const r = whole40();
  r.record.heads_at_end = r.record.heads_at_end.filter((h) => String(h.sid) !== '99');   // offered no more
  return r;
};
let l = lineOf(cardOf('a'), '57');
pickIn(l.sel, '99');
cardOf('a').querySelector('.fcc-cr-whole').click();
await settle(150);
l = lineOf(cardOf('a'), '57');
return { value: l.sel.value, listed: Array.from(l.sel.options).some((o) => o.value === '99'), notice: notice('a') };
""", {"pending": cards, "spools": SPOOLS})
    assert res["value"] == "99" and res["listed"], res
    assert "couldn’t be kept" not in res["notice"], res


def test_a_worked_out_card_that_cant_be_worked_out_again_keeps_its_basis_words(tmp_path):
    cards = _cards()
    cards[0] = dict(cards[0], basis="whole", progress=1.0, seen_progress=0.3, rev=2, requested_total=40.0,
                    applied_g=10.0, rework_refused="10.00g of this print is already charged, so it can't be "
                                                   "worked out again.")
    res = run(tmp_path, RESPOND_JS + "return { text: cardOf('a').textContent };",
              {"pending": cards, "spools": SPOOLS})
    text = " ".join(res["text"].split())
    assert "worked out for the whole print (FCC last saw ~30%)" in text, text
    assert "nudge each spool up to the full amount" not in text, text


def test_the_keyboard_stays_where_the_person_was_typing(tmp_path):
    res = run(tmp_path, RESPOND_JS + SERVER_JS + LOOKUP_JS + r"""
answer = whole40;
let l = lineOf(cardOf('a'), '57');
pickIn(l.sel, 'other');
l.box.focus();
l.box.value = '4';                                 // typing a spool's number when the answer lands
cardOf('a').querySelector('.fcc-cr-whole').click();
await settle(150);
l = lineOf(cardOf('a'), '57');
return { onBox: document.activeElement === l.box, box: l.box.value };
""", {"pending": _cards(), "spools": SPOOLS})
    assert res == {"onBox": True, "box": "4"}, res


def test_the_basis_waits_while_the_cards_apply_is_out(tmp_path):
    res = run(tmp_path, RESPOND_JS + SERVER_JS + LOOKUP_JS + r"""
answer = whole40;
const c = cardOf('a');
c.querySelector('.fcc-cr-confirm').click();         // the Apply goes out
const whole = c.querySelector('.fcc-cr-whole');
const during = whole.disabled;
whole.disabled = false;                              // even pressed regardless, it waits
whole.click();
await settle(150);
return { during, recomputes: posts('/api/cancel_deduct/recompute').length };
""", {"pending": _cards(), "spools": SPOOLS})
    assert res == {"during": True, "recomputes": 0}, res
