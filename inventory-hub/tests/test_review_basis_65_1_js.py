"""Group 65.1 (1b), the card (Derek, 2026-11-09: "we should have a charge the whole print,
or a way to change the percentage"), hermetic (the real cancel_review.js under node).

A card whose download kept its figures offers Charge the whole print (a ❓ card, and the
no-spool card of an ambiguous end) and "How far it got: [ 30 ] %" with Work it out (those,
and a 🛑 card FCC saw after it lost contact), the box filled in with the last percentage
FCC saw. Each posts POST /api/cancel_deduct/recompute with the card's revision and draws
the card again as FCC holds it. Enter in the box works it out and never applies; a
double click's second press works nothing out again; a percentage outside 0-100 posts
nothing. A card without figures keeps its look. Red on 5b97b2d4 (no controls).
"""
from __future__ import annotations

from test_cancel_review_picker_scan_js import (  # noqa: F401  (pytestmark: skip without node)
    RESPOND_JS, SPOOLS, _base, _row, pytestmark, run)

FIG = {"footer": {"0": 40.0, "1": 10.0},
       "by_pct": {"0": [round(0.4 * i, 4) for i in range(101)], "1": [round(0.1 * i, 4) for i in range(101)]}}
LOST = {"progress": 0.3, "seen_at": 1000.0, "lost_at": 1010.0, "back_at": 9000.0, "back_state": "STOPPED",
        "why": "lost"}
HEADS = [{"toolhead": "HEAD-1", "position": 0, "sid": 57, "sids": [57]},
         {"toolhead": "HEAD-2", "position": 1, "sid": None, "sids": []}]


def _cards():
    return [
        _base("a", "partial", ambiguous=True, progress=0.3, total_grams=15.0, spools=[_row(57, "HEAD-1", 0, 12.0)],
              unresolved_usage={"1": 3.0}, heads_at_end=HEADS, figures=FIG),
        _base("c", "partial", progress=0.3, total_grams=12.0, spools=[_row(58, "HEAD-1", 0, 12.0)],
              heads_at_end=HEADS, figures=FIG, lost_contact=LOST),
        _base("o", "partial", ambiguous=True, progress=0.3, total_grams=12.0, spools=[_row(59, "HEAD-1", 0, 12.0)]),
        _base("n", "no_spool", ambiguous=True, progress=0.3, total_grams=15.0, usage_map={"0": 12.0, "1": 3.0},
              heads_at_end=HEADS, figures=FIG),
    ]


LOOK_JS = r"""
const out = {};
for (const j of ['a', 'c', 'o', 'n']) {
  const c = cardOf(j);
  const box = c.querySelector('.fcc-cr-pct');
  out[j] = { whole: !!c.querySelector('.fcc-cr-whole'), work: !!c.querySelector('.fcc-cr-workout'),
             pct: box ? box.value : null, weightBox: box ? box.classList.contains('fcc-weight-box') : null };
}
return out;
"""


def test_the_controls_go_on_cards_with_figures_only(tmp_path):
    res = run(tmp_path, RESPOND_JS + LOOK_JS, {"pending": _cards(), "spools": SPOOLS})
    assert res["a"] == {"whole": True, "work": True, "pct": "30", "weightBox": True}, res
    assert res["c"] == {"whole": False, "work": True, "pct": "30", "weightBox": True}, res      # 🛑 seen late
    assert res["o"] == {"whole": False, "work": False, "pct": None, "weightBox": None}, res     # from before
    assert res["n"] == {"whole": True, "work": True, "pct": "30", "weightBox": True}, res


# The server: a recompute answers the new record, which the next list read hands back.
SERVER_JS = r"""
let pending = JSON.parse(JSON.stringify(D.pending));
const asJson = (b) => (typeof b === 'string' ? JSON.parse(b) : b);
let answer = null;
window.__respond = (url, method, body) => {
  if (url.startsWith('/api/cancel_deduct/pending')) return { body: { pending } };
  if (url.startsWith('/api/cancel_deduct/candidates')) return { body: { heads: [] } };
  if (url.startsWith('/api/cancel_deduct/recompute')) {
    const a = answer ? answer(asJson(body)) : { status: 'error', msg: 'stub' };
    if (a.status === 'recomputed') pending = pending.map((r) => r.job_id === a.record.job_id ? a.record : r);
    return { body: a };
  }
  if (url.startsWith('/api/cancel_deduct/confirm')) return { body: { status: 'error', msg: 'stub: nothing applied' } };
  return { body: {} };
};
const posts = (part) => window.__rec.fetches.filter((f) => f.method === 'POST' && f.url.startsWith(part))
  .map((f) => asJson(f.body));
const notice = (j) => ((cardOf(j) || {}).querySelector ? (cardOf(j).querySelector('.fcc-cr-card-notice') || {}).textContent : '') || '';
const atBasis = (rec, basis, rows) => Object.assign({}, rec, { basis, progress: basis === 'whole' ? 1 : basis / 100,
  seen_progress: rec.progress, rev: (rec.rev || 0) + 1, spools: rows });
"""


def test_work_it_out_posts_the_percentage_and_draws_the_card_again(tmp_path):
    res = run(tmp_path, RESPOND_JS + SERVER_JS + r"""
answer = (b) => ({ status: 'recomputed', record: atBasis(D.pending[0], b.percent,
                   [Object.assign({}, D.pending[0].spools[0], { grams: 24.8 })]) });
const c = cardOf('a');
c.querySelector('.fcc-cr-pct').value = '62';
c.querySelector('.fcc-cr-workout').click();
await settle(80);
const fresh = cardOf('a');
return { posted: posts('/api/cancel_deduct/recompute'), grams: fresh.querySelector('.fcc-cr-grams').value,
         pct: fresh.querySelector('.fcc-cr-pct').value, said: (fresh.querySelector('.fcc-cr-basis-said') || {}).textContent,
         rev: fresh.dataset.rev, notice: notice('a'), applied: posts('/api/cancel_deduct/confirm').length };
""", {"pending": _cards(), "spools": SPOOLS})
    assert res["posted"] == [{"printer_name": "TESTER", "job_id": "a", "rev": 0, "percent": 62}], res
    assert res["grams"] == "24.8" and res["pct"] == "62" and res["rev"] == "1", res
    assert res["said"] == "Worked out at 62%." and "check the grams, then Confirm" in res["notice"], res
    assert res["applied"] == 0, res


def test_charge_the_whole_print_posts_whole(tmp_path):
    res = run(tmp_path, RESPOND_JS + SERVER_JS + r"""
answer = (b) => ({ status: 'recomputed', record: atBasis(D.pending[0], 'whole',
                   [Object.assign({}, D.pending[0].spools[0], { grams: 40 })]) });
cardOf('a').querySelector('.fcc-cr-whole').click();
await settle(80);
const fresh = cardOf('a');
return { posted: posts('/api/cancel_deduct/recompute'), pct: fresh.querySelector('.fcc-cr-pct').value,
         header: fresh.textContent.includes('worked out for the whole print') };
""", {"pending": _cards(), "spools": SPOOLS})
    assert res["posted"] == [{"printer_name": "TESTER", "job_id": "a", "rev": 0, "whole": True}], res
    assert res["pct"] == "100" and res["header"] is True, res


def test_enter_in_the_box_works_it_out_and_never_applies(tmp_path):
    res = run(tmp_path, RESPOND_JS + SERVER_JS + r"""
answer = (b) => ({ status: 'recomputed', record: atBasis(D.pending[0], b.percent, D.pending[0].spools) });
const box = cardOf('a').querySelector('.fcc-cr-pct');
box.value = '45.5';
const ev = key(box, 'Enter');
await settle(80);
return { posted: posts('/api/cancel_deduct/recompute'), applied: posts('/api/cancel_deduct/confirm').length,
         prevented: ev.defaultPrevented };
""", {"pending": _cards(), "spools": SPOOLS})
    assert res["posted"] == [{"printer_name": "TESTER", "job_id": "a", "rev": 0, "percent": 45.5}], res
    assert res["applied"] == 0 and res["prevented"] is True, res


def test_a_double_clicks_second_press_works_nothing_out_again(tmp_path):
    res = run(tmp_path, RESPOND_JS + SERVER_JS + r"""
answer = (b) => ({ status: 'recomputed', record: atBasis(D.pending[0], 'whole', D.pending[0].spools) });
const btn = cardOf('a').querySelector('.fcc-cr-whole');
btn.click();
btn.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, detail: 2 }));
await settle(80);
const again = cardOf('a').querySelector('.fcc-cr-whole');
again.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, detail: 2 }));
await settle(60);
return { posted: posts('/api/cancel_deduct/recompute').length };
""", {"pending": _cards(), "spools": SPOOLS})
    assert res["posted"] == 1, res


def test_a_percentage_outside_0_to_100_posts_nothing_and_says_why(tmp_path):
    res = run(tmp_path, RESPOND_JS + SERVER_JS + r"""
const out = [];
for (const v of ['150', '-1', 'abc', '']) {
  const c = cardOf('a');
  c.querySelector('.fcc-cr-pct').value = v;
  c.querySelector('.fcc-cr-workout').click();
  await settle(30);
  out.push(notice('a'));
}
return { posted: posts('/api/cancel_deduct/recompute').length, notices: out };
""", {"pending": _cards(), "spools": SPOOLS})
    assert res["posted"] == 0, res
    assert all("from 0 to 100 %" in n for n in res["notices"]), res


def test_a_refusal_is_said_on_the_card_and_a_stale_card_is_drawn_again(tmp_path):
    res = run(tmp_path, RESPOND_JS + SERVER_JS + r"""
answer = () => ({ status: 'error', msg: 'Part of this print is already charged, so it can\'t be worked out again: charge the rest as shown, or Discard and weigh the spools.' });
cardOf('a').querySelector('.fcc-cr-whole').click();
await settle(60);
const refused = { notice: notice('a'), enabled: !cardOf('a').querySelector('.fcc-cr-whole').disabled };
pending = pending.map((r) => r.job_id === 'a' ? Object.assign({}, r, { rev: 3 }) : r);
answer = () => ({ status: 'error', stale: true, msg: "This card changed since it was drawn: it's drawn again as it is now." });
cardOf('a').querySelector('.fcc-cr-whole').click();
await settle(80);
return { refused, staleRev: cardOf('a').dataset.rev, staleNotice: notice('a') };
""", {"pending": _cards(), "spools": SPOOLS})
    assert "already charged" in res["refused"]["notice"] and res["refused"]["enabled"] is True, res
    assert res["staleRev"] == "3" and "drawn again" in res["staleNotice"], res
