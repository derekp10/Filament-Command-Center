"""Group 65 fix review, round 5: the 🛑 card's page (hermetic: the real cancel_review.js under
node).

  - RZ2 (yellow): a finished print's card (a completion FCC saw only after it lost contact: its
    no-spool card, its spool-changed card) says FCC next saw it finished, never that it "may
    have printed further before it was cancelled"; a cancel's card keeps its words.
  - CZ1 (yellow): an Enter in How far it got while the card is being worked out keeps its
    figure: a typo is said at once and never promised; a figure the box changed from after the
    Enter is said as not worked out, never a figure nobody pressed Enter on worked out; a card
    that couldn't be drawn again says the figure wasn't worked out.
  - CZ2 (yellow): the same Enter on the figure the card showed before the press is worked out
    after the redraw too (it was dropped without a word).
  - CZ3 (yellow): an Enter in How far it got while a stale card's Confirm reads it again waits
    and is worked out on the card drawn again, never sent on the old revision.

Red on 22c87e02 (fix review 4's fixes).
"""
from __future__ import annotations

from test_cancel_review_picker_scan_js import (  # noqa: F401  (pytestmark: skip without node)
    RESPOND_JS, SPOOLS, _base, _row, pytestmark, run)
from test_review_basis_65_1_js import SERVER_JS, _cards
from test_review_rework_65_r1_js import LOOKUP_JS

FINISHED = {"progress": 0.8, "seen_at": 1000.0, "lost_at": 1010.0, "back_at": 9000.0, "back_state": "FINISHED",
            "why": "lost"}
STOPPED = dict(FINISHED, back_state="STOPPED", progress=0.3)


def test_a_finished_prints_card_never_says_it_may_have_been_cancelled(tmp_path):
    cards = [_base("ns", "no_spool", progress=1.0, usage_map={"0": 40.0}, lost_contact=FINISHED,
                   heads_at_end=[{"toolhead": "HEAD-1", "position": 0, "sid": 57, "sids": [57]}]),
             _base("sc", "spool_changed", progress=1.0, total_grams=40.0, spools=[_row(57, "HEAD-1", 0, 40.0)],
                   lost_contact=FINISHED),
             _base("c", "partial", progress=0.3, total_grams=12.0, spools=[_row(58, "HEAD-1", 0, 12.0)],
                   lost_contact=STOPPED)]
    res = run(tmp_path, RESPOND_JS + r"""
const out = {};
for (const c of document.querySelectorAll('.fcc-cr-card')) {
  const lost = c.querySelector('.fcc-cr-lost');
  out[c.dataset.job] = lost ? lost.textContent.replace(/\s+/g, ' ').trim() : null;
}
return out;
""", {"pending": cards, "spools": SPOOLS})
    for job in ("ns", "sc"):
        assert res[job] and "next saw it finished" in res[job], res
        assert "cancelled" not in res[job] and "may have" not in res[job], res
        assert res[job].endswith("."), res
    assert "may have printed further before it was cancelled" in res["c"], res


# The server: a recompute is answered after `wait` ms, at the basis asked, refused as stale for
# an older revision than the one FCC holds.
BUSY_JS = r"""
let wait = 150;
const base = window.__respond;
window.__respond = (url, method, body) => {
  const r = base(url, method, body);
  return url.startsWith('/api/cancel_deduct/recompute') ? Object.assign({}, r, { delay: wait }) : r;
};
answer = (b) => {
  const cur = pending.find((r) => r.job_id === 'a');
  if (Number(b.rev) !== Number(cur.rev || 0)) {
    return { status: 'error', stale: true, msg: "This card changed since it was drawn: it's drawn again as it is now." };
  }
  return b.whole ? whole40() : { status: 'recomputed', record: atBasis(cur, b.percent,
    [Object.assign({}, D.pending[0].spools[0], { grams: Math.round(40 * b.percent) / 100 })]) };
};
const worked = () => posts('/api/cancel_deduct/recompute').map((p) => p.whole ? 'whole' : p.percent);
const said = () => (cardOf('a').querySelector('.fcc-cr-basis-said') || {}).textContent;
"""


def test_a_typo_typed_while_the_card_is_worked_out_is_said_at_once(tmp_path):
    res = run(tmp_path, RESPOND_JS + SERVER_JS + LOOKUP_JS + BUSY_JS + r"""
const c = cardOf('a');
c.querySelector('.fcc-cr-whole').click();
await settle(30);
const box = c.querySelector('.fcc-cr-pct');
box.focus();
box.value = '7o';
key(box, 'Enter');
await settle(20);
const meanwhile = notice('a');
await settle(900);
return { meanwhile, worked: worked() };
""", {"pending": _cards(), "spools": SPOOLS})
    assert res["meanwhile"] == "Type how far the print got, from 0 to 100 %, then press Enter.", res
    assert res["worked"] == ["whole"], res


def test_a_figure_changed_after_its_enter_is_said_never_worked_out_unasked(tmp_path):
    res = run(tmp_path, RESPOND_JS + SERVER_JS + LOOKUP_JS + BUSY_JS + r"""
const c = cardOf('a');
c.querySelector('.fcc-cr-whole').click();
await settle(30);
const box = c.querySelector('.fcc-cr-pct');
box.focus();
box.value = '70';
key(box, 'Enter');
await settle(20);
box.value = '7';                           // he starts putting it right, and pauses
await settle(900);
return { worked: worked(), notice: notice('a') };
""", {"pending": _cards(), "spools": SPOOLS})
    assert res["worked"] == ["whole"], res
    assert res["notice"].startswith("70% wasn’t worked out: How far it got changed after you pressed Enter."), res


def test_a_queued_figure_on_a_card_that_couldnt_be_drawn_again_is_said(tmp_path):
    res = run(tmp_path, RESPOND_JS + SERVER_JS + LOOKUP_JS + BUSY_JS + r"""
let failList = false;
const listed = window.__respond;
window.__respond = (url, method, body) => (failList && url.startsWith('/api/cancel_deduct/pending'))
  ? { fail: true } : listed(url, method, body);
const c = cardOf('a');
c.querySelector('.fcc-cr-whole').click();
await settle(30);
const box = c.querySelector('.fcc-cr-pct');
box.focus();
box.value = '70';
key(box, 'Enter');
failList = true;                           // the read after FCC's answer fails
await settle(900);
return { worked: worked(), notice: notice('a') };
""", {"pending": _cards(), "spools": SPOOLS})
    assert res["worked"] == ["whole"], res
    assert "70% wasn’t worked out: press Enter again." in res["notice"], res


def test_an_enter_on_the_figure_the_card_showed_is_worked_out_after_the_redraw(tmp_path):
    res = run(tmp_path, RESPOND_JS + SERVER_JS + LOOKUP_JS + BUSY_JS + r"""
const c = cardOf('a');
c.querySelector('.fcc-cr-whole').click();   // by mistake: the card showed 30 %
await settle(30);
const box = c.querySelector('.fcc-cr-pct');
box.focus();                               // still 30, as drawn
key(box, 'Enter');
await settle(900);
return { worked: worked(), said: said() };
""", {"pending": _cards(), "spools": SPOOLS})
    assert res["worked"] == ["whole", 30], res
    assert res["said"] == "Worked out at 30%.", res


def test_an_enter_while_a_stale_confirm_reads_waits_for_the_card_drawn_again(tmp_path):
    res = run(tmp_path, RESPOND_JS + SERVER_JS + LOOKUP_JS + BUSY_JS + r"""
// Another device worked the card out for the whole print (rev 1); this page's card is stale.
pending = pending.map((r) => r.job_id === 'a' ? atBasis(r, 'whole', r.spools) : r);
let slow = false;
const listed = window.__respond;
window.__respond = (url, method, body) => {
  const r = listed(url, method, body);
  return (slow && url.startsWith('/api/cancel_deduct/pending')) ? Object.assign({}, r, { delay: 300 }) : r;
};
const c = cardOf('a');
c.dataset.stale = '1';
slow = true;
c.querySelector('.fcc-cr-confirm').click();
await settle(40);
const box = c.querySelector('.fcc-cr-pct');
box.focus();
box.value = '70';                          // he meant 70 %
key(box, 'Enter');
await settle(40);
const during = worked().length;
slow = false;
await settle(1200);
return { during, worked: posts('/api/cancel_deduct/recompute').map((p) => [p.rev, p.percent]), said: said() };
""", {"pending": _cards(), "spools": SPOOLS})
    assert res["during"] == 0, res
    assert res["worked"] == [[1, 70]], res
    assert res["said"] == "Worked out at 70%.", res
