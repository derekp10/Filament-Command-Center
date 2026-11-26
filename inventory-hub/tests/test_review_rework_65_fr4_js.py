"""Group 65 fix review, round 4: the 🛑 card's page (hermetic: the real cancel_review.js under
node).

  - Fix review 3's known gap: an uncharged-grams card holding a spool FCC weighed while it
    couldn't see the print says so at its head and in its banner, never "after this print
    ended"; Group 64's two kinds keep their words.
  - CY1: a stale card's Confirm whose card leaves the page while FCC reads the list again (🛑
    Review closed) says nothing, never "That card was already settled"; its other buttons
    wait while it reads.
  - CY2: an Enter in How far it got while the card is being worked out is worked out once the
    card is drawn again, never dropped without a word.
  - CY3: a card worked out again isn't drawn while a scan's first keys wait in the scan
    buffer, or a weight box holds a label's letters (a scanner stalled inside a label).
  - CY4: a percentage refused as stale on a card FCC already holds at that percentage says
    so, never "wasn't worked out"; an Enter on the figure the card was drawn with says it is
    worked out there already.

Red on cbfea058 (fix review 3's fixes).
"""
from __future__ import annotations

from test_cancel_review_picker_scan_js import (  # noqa: F401  (pytestmark: skip without node)
    RESPOND_JS, SPOOLS, _base, pytestmark, run)
from test_review_basis_65_1_js import SERVER_JS, _cards
from test_review_rework_65_r1_js import LOOKUP_JS


def _held(job, kinds):
    """An uncharged-grams card whose lines are held for a weighing, one line per kind."""
    un, causes, fill, heads = {}, {}, {}, []
    for i, kind in enumerate(kinds):
        sid = 200 + i
        un[str(i)] = 12.4
        cause = {"why": "weighed", "sid": sid, "toolhead": f"HEAD-{i + 1}", "archived": False,
                 "known_order": kind in ("known", "seen"), "words": f"#{sid} on HEAD-{i + 1} was weighed"}
        if kind in ("seen", "unseen"):
            cause[kind] = True
        causes[str(i)] = cause
        fill[str(i)] = 0.0 if kind in ("known", "seen") else 12.4
        heads.append({"toolhead": f"HEAD-{i + 1}", "position": i, "sid": sid, "sids": [sid]})
    return _base(job, "shortfall", rev=0, total_grams=round(12.4 * len(kinds), 2), unresolved_usage=un,
                 shortfall_prefill=fill, shortfall_causes=causes, heads_at_end=heads)


HEAD_JS = r"""
const out = {};
for (const c of document.querySelectorAll('.fcc-cr-card')) {
  out[c.dataset.job] = { title: c.querySelector('.fcc-cr-short-title').textContent.replace(/\s+/g, ' ').trim(),
                         banner: c.querySelector('.fcc-cr-short-banner').textContent.replace(/\s+/g, ' ').trim() };
}
return out;
"""


def test_a_card_held_for_a_weighing_fcc_couldnt_place_against_the_print_says_when(tmp_path):
    cards = [_held("u#shortfall", ["unseen"]), _held("s#shortfall", ["seen"]),
             _held("ks#shortfall", ["known", "seen"]), _held("uu#shortfall", ["unseen", "unsure"]),
             _held("k#shortfall", ["known"]), _held("n#shortfall", ["unsure"])]
    part = _held("p#shortfall", ["unseen"])
    part["unresolved_usage"]["1"] = 3.0
    part["shortfall_causes"]["1"] = {"why": "no_spool", "sid": None, "toolhead": "HEAD-2", "archived": False}
    part["total_grams"] = 15.4
    res = run(tmp_path, RESPOND_JS + HEAD_JS, {"pending": cards + [part], "spools": SPOOLS})
    u, s = res["u#shortfall"], res["s#shortfall"]
    assert u["title"] == "⚖️ TESTER — 12.4g held: #200 was weighed while FCC couldn’t see this print", u
    assert "was weighed on FCC while FCC couldn’t see this print" in u["banner"], u
    assert s["title"] == "⚖️ TESTER — 12.4g held: #200 was weighed after FCC last saw this print", s
    assert "were all printed before that, so the scale already counted them" in s["banner"], s
    for job in ("u#shortfall", "s#shortfall", "ks#shortfall", "uu#shortfall"):
        assert "after this print ended" not in res[job]["banner"], res[job]
        assert "changed weight after this print" not in res[job]["title"], res[job]
    assert res["ks#shortfall"]["title"].endswith("changed weight during or after this print"), res
    assert "were weighed on FCC after the grams on their lines were printed" in res["ks#shortfall"]["banner"], res
    assert "FCC can’t tell for every line whether the scale counted its grams" in res["uu#shortfall"]["banner"], res
    assert "The 12.4g on #200 is held, not charged: it was weighed while FCC couldn’t see this print, as its " \
           "line says." in res["p#shortfall"]["banner"], res
    # Group 64's two kinds keep their words.
    assert res["k#shortfall"]["title"] == "⚖️ TESTER — 12.4g held: #200 was weighed after this print", res
    assert res["n#shortfall"]["title"] == "⚖️ TESTER — 12.4g held: #200 changed weight after this print", res


def test_a_stale_confirm_whose_card_leaves_the_page_meanwhile_says_nothing(tmp_path):
    res = run(tmp_path, RESPOND_JS + SERVER_JS + r"""
let slow = false;
const base = window.__respond;
window.__respond = (url, method, body) => {
  const r = base(url, method, body);
  return (slow && url.startsWith('/api/cancel_deduct/pending')) ? Object.assign({}, r, { delay: 300 }) : r;
};
const c = cardOf('a');
c.dataset.stale = '1';                   // an earlier redraw couldn't read the list
slow = true;
c.querySelector('.fcc-cr-confirm').click();
await settle(60);
const waiting = ['.fcc-cr-whole', '.fcc-cr-workout', '.fcc-cr-discard'].map((s) => !!(c.querySelector(s) || {}).disabled);
c.remove();                               // 🛑 Review closed while FCC reads the list
await settle(500);
return { waiting, toasts: window.__rec.toasts.map((t) => t.msg),
         confirms: posts('/api/cancel_deduct/confirm').length };
""", {"pending": _cards(), "spools": SPOOLS})
    assert res["waiting"] == [True, True, True], res
    assert not any("already settled" in t for t in res["toasts"]), res
    assert res["confirms"] == 0, res


def test_an_enter_on_a_figure_typed_while_the_card_is_worked_out_is_worked_out_after(tmp_path):
    res = run(tmp_path, RESPOND_JS + SERVER_JS + LOOKUP_JS + r"""
const base = window.__respond;
window.__respond = (url, method, body) => {
  const r = base(url, method, body);
  return url.startsWith('/api/cancel_deduct/recompute') ? Object.assign({}, r, { delay: 120 }) : r;
};
answer = (b) => b.whole ? whole40() : ({ status: 'recomputed', record: atBasis(
  pending.find((r) => r.job_id === 'a'), b.percent,
  [Object.assign({}, D.pending[0].spools[0], { grams: 28 })]) });
const c = cardOf('a');
c.querySelector('.fcc-cr-whole').click();
await settle(30);
const box = c.querySelector('.fcc-cr-pct');
box.focus();
box.value = '70';                         // he meant 70 %
key(box, 'Enter');
await settle(60);
const meanwhile = notice('a');
await settle(900);
const fresh = cardOf('a');
return { posted: posts('/api/cancel_deduct/recompute').map((p) => p.whole ? 'whole' : p.percent),
         said: (fresh.querySelector('.fcc-cr-basis-said') || {}).textContent, meanwhile, notice: notice('a') };
""", {"pending": _cards(), "spools": SPOOLS})
    assert res["posted"] == ["whole", 70], res
    assert res["said"] == "Worked out at 70%.", res
    assert "70% is worked out once it is drawn again" in res["meanwhile"], res


def test_a_redraw_waits_for_a_scan_waiting_in_the_scan_buffer(tmp_path):
    res = run(tmp_path, RESPOND_JS + SERVER_JS + LOOKUP_JS + r"""
answer = whole40;
state.scanBuffer = 'ID';                   // a scanner stalled after the label's first keys
const c = cardOf('a');
c.querySelector('.fcc-cr-whole').click();
await settle(500);
const early = cardOf('a') === c;
state.scanBuffer = '';                     // the scan is done
await settle(200);
return { early, late: cardOf('a') !== c };
""", {"pending": _cards(), "spools": SPOOLS})
    assert res == {"early": True, "late": True}, res


def test_a_redraw_waits_for_a_label_a_weight_box_holds(tmp_path):
    res = run(tmp_path, RESPOND_JS + SERVER_JS + LOOKUP_JS + r"""
answer = whole40;
let held = true;
window.fccWeightKeysHeld = () => held;     // a grams box holds "ID" of a stalled scan
const c = cardOf('a');
c.querySelector('.fcc-cr-whole').click();
await settle(500);
const early = cardOf('a') === c;
held = false;
await settle(200);
return { early, late: cardOf('a') !== c };
""", {"pending": _cards(), "spools": SPOOLS})
    assert res == {"early": True, "late": True}, res


def test_a_stale_percentage_the_card_is_at_already_says_so(tmp_path):
    res = run(tmp_path, RESPOND_JS + SERVER_JS + LOOKUP_JS + r"""
// Another device worked the card out at 62 %: FCC holds it there (rev 1).
pending = pending.map((r) => r.job_id === 'a' ? atBasis(r, 62, r.spools) : r);
answer = () => ({ status: 'error', stale: true, msg: "This card changed since it was drawn: it's drawn again as it is now." });
const box = cardOf('a').querySelector('.fcc-cr-pct');
box.focus();
box.value = '62';
key(box, 'Enter');
await settle(500);
const first = notice('a');
await settle(800);
const again = cardOf('a').querySelector('.fcc-cr-pct');
again.focus();
key(again, 'Enter');                       // the same figure again, a while later
await settle(80);
return { first, second: notice('a'), posted: posts('/api/cancel_deduct/recompute').length };
""", {"pending": _cards(), "spools": SPOOLS})
    assert "wasn’t worked out" not in res["first"], res
    assert "It is worked out at 62% already: check the grams, then Confirm." in res["first"], res
    assert res["second"] == "It is worked out at 62% already: check the grams, then Confirm.", res
    assert res["posted"] == 1, res
