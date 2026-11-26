"""Group 65 fix review, round 3: the 🛑 card's page (hermetic: the real cancel_review.js
under node).

  - CX2 / CX3 / CX4 (orange): a card worked out again is drawn anew only once the keyboard
    is quiet (no character in the last 300 ms, no scan arriving), so a scan read meanwhile
    finishes whole where it started, never split across the old card and the fresh one.
  - CX4: a How far it got figure is carried over a redraw only when it is a figure (a scan's
    letters are none).
  - CX5: a percentage FCC refused as stale isn't carried over the card drawn again, and the
    card says it wasn't worked out.
  - CX1 / AX2: a stale card's Confirm draws it again with the keyboard where Enter applies
    nothing (the first pick or grams box), never on Confirm or in How far it got.
  - CX6: an Enter in How far it got on the figure the card was drawn with works nothing out.
  - RX5: the Apply's toast says each kind of weighed spool in its own words.

Red on dcfa4a4b (the third fix review's head).
"""
from __future__ import annotations

from test_cancel_review_picker_scan_js import (  # noqa: F401  (pytestmark: skip without node)
    RESPOND_JS, SPOOLS, _base, _row, pytestmark, run)
from test_review_basis_65_1_js import SERVER_JS, _cards
from test_review_rework_65_r1_js import LOOKUP_JS


def test_the_card_is_drawn_again_only_once_the_keys_stop(tmp_path):
    res = run(tmp_path, RESPOND_JS + SERVER_JS + LOOKUP_JS + r"""
answer = () => {
  key(cardOf('a').querySelector('.fcc-cr-grams'), '5');     // a scan's first digit, as the answer lands
  return whole40();
};
const c = cardOf('a');
c.querySelector('.fcc-cr-whole').click();
await settle(150);
const early = cardOf('a') === c;
await settle(400);
return { early, late: cardOf('a') !== c, grams: cardOf('a').querySelector('.fcc-cr-grams').value };
""", {"pending": _cards(), "spools": SPOOLS})
    assert res == {"early": True, "late": True, "grams": "40"}, res


def test_the_card_is_drawn_again_only_once_a_scan_has_arrived(tmp_path):
    res = run(tmp_path, RESPOND_JS + SERVER_JS + LOOKUP_JS + r"""
let arriving = false;
window.scanIsArriving = () => arriving;
answer = () => { arriving = true; setTimeout(() => { arriving = false; }, 250); return whole40(); };
const c = cardOf('a');
c.querySelector('.fcc-cr-whole').click();
await settle(150);
const early = cardOf('a') === c;
await settle(300);
return { early, late: cardOf('a') !== c };
""", {"pending": _cards(), "spools": SPOOLS})
    assert res == {"early": True, "late": True}, res


def test_a_scans_letters_in_how_far_it_got_are_not_carried(tmp_path):
    res = run(tmp_path, RESPOND_JS + SERVER_JS + LOOKUP_JS + r"""
answer = () => {
  const p = cardOf('a').querySelector('.fcc-cr-pct');
  p.focus();
  p.value = '30ID';                    // a label's first keys, left there by a scanner too slow to wait for
  return whole40();
};
cardOf('a').querySelector('.fcc-cr-whole').click();
await settle(150);
return { pct: cardOf('a').querySelector('.fcc-cr-pct').value };
""", {"pending": _cards(), "spools": SPOOLS})
    assert res == {"pct": "100"}, res


def test_a_percentage_refused_as_stale_is_not_carried_and_is_said(tmp_path):
    res = run(tmp_path, RESPOND_JS + SERVER_JS + LOOKUP_JS + r"""
pending = pending.map((r) => r.job_id === 'a' ? Object.assign({}, r, { rev: 3, basis: 'whole', progress: 1 }) : r);
answer = () => ({ status: 'error', stale: true, msg: "This card changed since it was drawn: it's drawn again as it is now." });
const box = cardOf('a').querySelector('.fcc-cr-pct');
box.focus();
box.value = '62';
key(box, 'Enter');
await settle(150);
const fresh = cardOf('a');
return { pct: fresh.querySelector('.fcc-cr-pct').value, notice: notice('a') };
""", {"pending": _cards(), "spools": SPOOLS})
    assert res["pct"] == "100", res
    assert "62% wasn’t worked out" in res["notice"], res


def test_a_stale_cards_confirm_leaves_the_keyboard_off_its_buttons_and_the_percentage(tmp_path):
    res = run(tmp_path, RESPOND_JS + SERVER_JS + LOOKUP_JS + r"""
const out = {};
for (const how of ['on-confirm', 'from-nowhere']) {
  const c = cardOf('a');
  c.dataset.stale = '1';
  const btn = c.querySelector('.fcc-cr-confirm');
  if (how === 'on-confirm') btn.focus(); else if (document.activeElement && document.activeElement.blur) document.activeElement.blur();
  btn.click();
  await settle(150);
  const a = document.activeElement;
  out[how] = String((a && a.className) || '').split(/\s+/).filter((x) => x.startsWith('fcc-cr-'))[0] || 'none';
}
return out;
""", {"pending": _cards(), "spools": SPOOLS})
    assert res == {"on-confirm": "fcc-cr-grams", "from-nowhere": "fcc-cr-grams"}, res


def test_an_enter_on_the_figure_the_card_was_drawn_with_works_nothing_out(tmp_path):
    res = run(tmp_path, RESPOND_JS + SERVER_JS + LOOKUP_JS + r"""
answer = whole40;
const w = cardOf('a').querySelector('.fcc-cr-whole');
w.focus();                                                    // pressed from the keyboard
w.click();
await settle(150);
const box = cardOf('a').querySelector('.fcc-cr-pct');       // the keyboard lands here, 100 selected
const on = document.activeElement === box;
key(box, 'Enter');                                            // a double press's second Enter
await settle(150);
return { on, posted: posts('/api/cancel_deduct/recompute').length, basis: cardOf('a').dataset.rev };
""", {"pending": _cards(), "spools": SPOOLS})
    assert res == {"on": True, "posted": 1, "basis": "1"}, res


def test_the_apply_toast_says_each_kind_of_weighed_spool_in_its_own_words(tmp_path):
    cards = [_base("a", "partial", ambiguous=True, progress=0.3, total_grams=24.0,
                   spools=[_row(57, "HEAD-1", 0, 12.0), _row(58, "HEAD-2", 1, 12.0)])]
    res = run(tmp_path, RESPOND_JS + r"""
window.__respond = (url) => {
  if (url.startsWith('/api/cancel_deduct/confirm')) {
    return { body: { status: 'confirmed', applied: [], errors: [], left_weighed: [
      { line: '0', sid: 57, grams: 12, known_order: false, unseen: true },
      { line: '1', sid: 58, grams: 12, known_order: true }] } };
  }
  if (url.startsWith('/api/cancel_deduct/pending')) return { body: { pending: [] } };
  return { body: {} };
};
cardOf('a').querySelector('.fcc-cr-confirm').click();
await settle(150);
return { toasts: window.__rec.toasts.map((t) => t.msg) };
""", {"pending": cards, "spools": SPOOLS})
    said = " ".join(res["toasts"])
    assert "#58: it was weighed after the print" in said, res
    assert "#57 as set: it was weighed while FCC couldn’t see the print" in said, res
    assert "#57 and #58" not in said, res
