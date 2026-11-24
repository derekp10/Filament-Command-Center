"""Group 65 review, round 1: working a 🛑 card out again, the card (hermetic: the real
cancel_review.js under node).

  - CM5 (orange): a pick made before Charge the whole print or Work it out is kept on the
    card drawn again, and Confirm charges that spool; the words say the picks are kept.
  - WD5: on a no-spool card the words name its own button (Apply) and ask for a pick.
  - WD6: the worked-out "couldn't measure" card points below, where its controls are.
  - PI1: an answer that the card was settled elsewhere shields a double click's second
    press, as every other branch that takes a card away does.
  - PI2 / PI4: the keyboard comes back to How far it got with its figure selected, so a
    figure typed next replaces it (on Charge the whole print it went to the scan path).
  - PI5: a card the server says can't be worked out again offers no controls, and its
    words don't invite them.
  - OR2: Discard waits while the card is worked out.
  - OR1: a "couldn't measure" card with figures no longer says to weigh the spool and adjust
    it directly beside a button that charges the print; a spool weighed since is held.

Red on 681601f6 (the reviewed head).
"""
from __future__ import annotations

from test_cancel_review_picker_scan_js import (  # noqa: F401  (pytestmark: skip without node)
    RESPOND_JS, SPOOLS, _base, pytestmark, run)
from test_review_basis_65_1_js import FIG, SERVER_JS, _cards

# Another spool by #ID looks the spool up at /api/spools/<id>.
LOOKUP_JS = r"""
const baseRespond = window.__respond;
window.__respond = (url, method, body) => {
  if (url.startsWith('/api/spools/')) {
    const hit = (D.spools || {})[url.split('/').pop()];
    return hit || { status: 404, body: { success: false, msg: 'Spool not found' } };
  }
  return baseRespond(url, method, body);
};
const whole40 = () => ({ status: 'recomputed', record: atBasis(D.pending[0], 'whole',
                         [Object.assign({}, D.pending[0].spools[0], { grams: 40 })]) });
"""


def test_a_pick_made_before_working_it_out_is_kept_and_charged(tmp_path):
    res = run(tmp_path, RESPOND_JS + SERVER_JS + LOOKUP_JS + r"""
answer = whole40;
let c = cardOf('a');
let l = lineOf(c, '57');
pickIn(l.sel, 'other');
l.box.value = 'ID:42';
key(l.box, 'Enter');
await settle(60);
c.querySelector('.fcc-cr-whole').click();
await settle(120);
c = cardOf('a');
l = lineOf(c, '57');
const after = { value: l.sel.value, box: l.box.value, notice: notice('a') };
c.querySelector('.fcc-cr-confirm').click();
await settle(120);
return { after, confirms: posts('/api/cancel_deduct/confirm') };
""", {"pending": _cards(), "spools": SPOOLS})
    assert res["after"]["value"] == "other" and res["after"]["box"] == "ID:42", res
    assert res["after"]["notice"] == "Worked out for the whole print: your picks are kept: check the grams, then Confirm.", res
    assert [c.get("charges") for c in res["confirms"]] == [[{"row": 57, "sid": 42, "grams": 40}]], res


def test_a_no_spool_cards_words_name_its_apply_and_ask_for_a_pick(tmp_path):
    res = run(tmp_path, RESPOND_JS + SERVER_JS + r"""
answer = (b) => ({ status: 'recomputed', record: Object.assign({}, D.pending[3], { basis: 'whole', progress: 1,
                   seen_progress: 0.3, rev: 1, usage_map: { '0': 40, '1': 10 }, total_grams: 50 }) });
cardOf('n').querySelector('.fcc-cr-whole').click();
await settle(120);
return { notice: notice('n'), button: (cardOf('n').querySelector('.fcc-cr-confirm') || {}).textContent };
""", {"pending": _cards(), "spools": SPOOLS})
    assert res["notice"] == "Worked out for the whole print: pick the spool each head used, then Apply.", res
    assert res["button"] == "Apply to the picked spool(s)", res


def test_the_worked_out_couldnt_measure_card_points_below_to_its_controls(tmp_path):
    card = _base("u", "no_spool", ambiguous=True, progress=1.0, total_grams=50.0, usage_map={"0": 40.0, "1": 10.0},
                 figures=FIG, basis="whole", seen_progress=None, unmeasured_was="unsampled", rev=2)
    res = run(tmp_path, RESPOND_JS + r"""
const t = cardOf('u').textContent;
return { below: t.indexOf('again with the buttons below'), above: t.indexOf('again above'),
         whole: t.indexOf('Charge the whole print') };
""", {"pending": [card], "spools": SPOOLS})
    assert res["above"] == -1 and 0 <= res["below"] < res["whole"], res


def test_a_card_settled_elsewhere_shields_a_double_clicks_second_press(tmp_path):
    res = run(tmp_path, RESPOND_JS + SERVER_JS + r"""
let shields = 0;
window.fccShieldNextPress = () => { shields += 1; };
answer = () => ({ status: 'already_handled' });
pending = pending.filter((r) => r.job_id !== 'a');       // settled from another tab
cardOf('a').querySelector('.fcc-cr-whole').click();
await settle(120);
return { shields, gone: !cardOf('a') };
""", {"pending": _cards(), "spools": SPOOLS})
    assert res["gone"] and res["shields"] >= 1, res


def test_the_keyboard_comes_back_to_how_far_it_got_with_its_figure_selected(tmp_path):
    res = run(tmp_path, RESPOND_JS + SERVER_JS + LOOKUP_JS + r"""
answer = whole40;
const w = cardOf('a').querySelector('.fcc-cr-whole');
w.focus();                        // a button takes the keyboard when it is clicked
w.click();
await settle(120);
const box = cardOf('a').querySelector('.fcc-cr-pct');
return { focused: document.activeElement === box, value: box.value, selected: [box.selectionStart, box.selectionEnd] };
""", {"pending": _cards(), "spools": SPOOLS})
    assert res["focused"] and res["value"] == "100" and res["selected"] == [0, 3], res


def test_a_card_the_server_says_cant_be_worked_out_again_offers_no_controls(tmp_path):
    cards = _cards()
    cards[0] = dict(cards[0], requested_total=15.0, applied_g=4.0,
                    rework_refused="4.00g of this print is already charged, so it can't be worked out again: charge "
                                   "the rest as shown, or Discard and weigh the spools.")
    res = run(tmp_path, RESPOND_JS + r"""
const c = cardOf('a');
return { whole: !!c.querySelector('.fcc-cr-whole'), work: !!c.querySelector('.fcc-cr-workout'),
         box: !!c.querySelector('.fcc-cr-pct'), invites: c.textContent.indexOf('press Charge the whole print') };
""", {"pending": cards, "spools": SPOOLS})
    assert res == {"whole": False, "work": False, "box": False, "invites": -1}, res


def test_discard_waits_while_the_card_is_worked_out(tmp_path):
    res = run(tmp_path, RESPOND_JS + SERVER_JS + LOOKUP_JS + r"""
answer = whole40;
const c = cardOf('a');
c.querySelector('.fcc-cr-whole').click();
const during = c.querySelector('.fcc-cr-discard').disabled;
await settle(120);
return { during };
""", {"pending": _cards(), "spools": SPOOLS})
    assert res["during"] is True, res


def test_a_couldnt_measure_card_with_figures_no_longer_says_weigh_and_adjust(tmp_path):
    card = _base("p", "progress_unknown", ambiguous=True, progress=0.0, total_grams=0.0,
                 unmeasured_reason="unsampled", figures=FIG, rev=1)
    res = run(tmp_path, RESPOND_JS + "return { text: cardOf('p').textContent };",
              {"pending": [card], "spools": SPOOLS})
    assert "adjust it directly" not in res["text"], res
    assert "A spool FCC weighed since the print ended is held at 0 g" in " ".join(res["text"].split()), res
