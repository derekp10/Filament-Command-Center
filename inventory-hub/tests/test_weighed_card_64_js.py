"""Group 64, Decision 1 (Derek, 2026-11-20): a spool weighed between its print's
end and FCC's charge, on the 🛑 Review card, hermetic.

Derek: "we want to make it obvious that this might be a 'double charge' ... So 0
Should be the default if we can tell the order of things, and a value if we aren't
sure but both should be heavily noted in the UI so its very clear that we be
pulling too much."

Runs the REAL overlay_mount.js and cancel_review.js under node's `vm` (the driver
in test_cancel_review_picker_scan_js.py). Pinned:
  - an uncharged-grams card's held line (cause "weighed") draws a loud note
    (`.fcc-cr-weighed`, role=note) with the server's words and says what FCC
    filled in, its grams box holds the server's figure (`shortfall_prefill`: 0 g
    when FCC knows the weighing came after the print, else the print's grams), and
    its spool is pre-picked;
  - a card whose every line is such a line, left at 0 g, Applies with
    `settle_held` and no pick, where it used to say "Pick the spool";
  - a held line given grams Applies them as a pick, as any line;
  - a review card's row whose spool was weighed after the print draws the same
    note and its box holds the row's `prefill`.

Three tests are RED on 7edb245 (the note, the figure and the settle are new); the
two that Apply grams typed or filled in pass there by design (an ordinary pick).
"""
from __future__ import annotations

from test_cancel_review_picker_scan_js import (  # noqa: F401  (pytestmark: skip without node)
    RESPOND_JS, SPOOLS, _base, pytestmark, run)

WORDS_KNOWN = ("#200 on HEAD-1 was weighed on the Quick-Weigh at 14:05, after this print ended "
               "(at 13:50), so the scale already counted its 12.40 g")
WORDS_UNSURE = ("#200 on HEAD-1 changed weight after this print ended (at 13:50) (100.00 g used then, "
                "104.00 g now), and FCC can't tell whether the scale counted this print's 12.40 g")


def _held(job, known):
    return _base(job, "shortfall", rev=0, total_grams=12.4, unresolved_usage={"0": 12.4},
                 shortfall_prefill={"0": 0.0 if known else 12.4},
                 shortfall_causes={"0": {"why": "weighed", "sid": 200, "toolhead": "HEAD-1",
                                         "archived": False, "known_order": known,
                                         "words": WORDS_KNOWN if known else WORDS_UNSURE}},
                 heads_at_end=[{"toolhead": "HEAD-1", "position": 0, "sid": 200, "sids": [200]}])


def _row(sid, grams, **extra):
    row = {"sid": sid, "toolhead": "HEAD-1", "position": 0, "grams": grams, "current_used": 100.0,
           "initial_weight": 1000.0, "remaining_before": 900.0, "remaining_after": 900.0 - grams,
           "display": f"#{sid} Test Spool", "color": "ff0000", "ambiguous": False}
    row.update(extra)
    return row


LOOK_JS = r"""
const out = {};
for (const j of ['k', 'u']) {
  const c = cardOf(j);
  const note = c.querySelector('.fcc-cr-weighed');
  const box = c.querySelector('.fcc-cr-pgrams');
  const pick = c.querySelector('.fcc-cr-pick');
  out[j] = { note: note && note.textContent.replace(/\s+/g, ' ').trim(), role: note && note.getAttribute('role'),
             box: box && box.value, pick: pick && pick.value,
             line: c.querySelector('.fcc-cr-shortline').getAttribute('data-weighed') };
}
return out;
"""


def test_a_held_line_says_it_loudly_and_holds_what_fcc_filled_in(tmp_path):
    res = run(tmp_path, RESPOND_JS + LOOK_JS,
              {"pending": [_held("k", True), _held("u", False)], "spools": SPOOLS})
    k, u = res["k"], res["u"]
    assert k["role"] == "note" and k["line"] == "1", k
    assert k["note"].startswith("⚠️ Weighed after this print ended: 0 g filled in"), k
    assert WORDS_KNOWN in k["note"] and "count the print twice" in k["note"], k
    assert float(k["box"]) == 0.0 and k["pick"] == "200", k
    assert u["note"].startswith("⚠️ Changed weight after this print ended: check before you Apply"), u
    assert WORDS_UNSURE in u["note"] and "may count this print twice" in u["note"], u
    assert float(u["box"]) == 12.4, u


APPLY_JS = r"""
const c = cardOf(__JOB__);
const box = c.querySelector('.fcc-cr-pgrams');
if (__GRAMS__ !== null) { box.value = String(__GRAMS__); box.dispatchEvent(new Event('input', { bubbles: true })); }
c.querySelector('.fcc-cr-confirm').click();
await settle(60);
return { posted: posts('/api/cancel_deduct/confirm'), notice: (c.querySelector('.fcc-cr-notice') || {}).textContent || null };
"""


def _apply(tmp_path, job, known, grams=None):
    body = APPLY_JS.replace("__JOB__", repr(job)).replace("__GRAMS__", "null" if grams is None else repr(grams))
    return run(tmp_path, RESPOND_JS + body, {"pending": [_held(job, known)], "spools": SPOOLS})


def test_a_card_of_held_lines_left_at_0g_settles_with_no_pick(tmp_path):
    res = _apply(tmp_path, "k", True)
    assert len(res["posted"]) == 1, res
    sent = res["posted"][0]
    assert sent.get("settle_held") is True and sent.get("charges") == [], sent
    assert sent.get("rev") == 0, sent


def test_a_held_line_given_grams_applies_them_as_a_pick(tmp_path):
    res = _apply(tmp_path, "k", True, grams=12.4)
    sent = res["posted"][0]
    assert "settle_held" not in sent, sent
    assert sent["charges"] == [{"position": 0, "sid": 200, "grams": 12.4}], sent


def test_a_held_line_whose_grams_are_filled_in_applies_them(tmp_path):
    res = _apply(tmp_path, "u", False)
    sent = res["posted"][0]
    assert "settle_held" not in sent and sent["charges"] == [{"position": 0, "sid": 200, "grams": 12.4}], sent


ROW_JS = r"""
const c = cardOf('r');
const row = c.querySelector('.fcc-cr-row[data-sid="200"]');
const note = row.querySelector('.fcc-cr-weighed');
const other = c.querySelector('.fcc-cr-row[data-sid="300"]');
return { note: note && note.textContent.replace(/\s+/g, ' ').trim(),
         box: row.querySelector('.fcc-cr-grams').value, weighed: row.getAttribute('data-weighed'),
         otherNote: !!other.querySelector('.fcc-cr-weighed'), otherBox: other.querySelector('.fcc-cr-grams').value };
"""


def test_a_review_rows_spool_weighed_after_the_print_says_so_and_holds_0g(tmp_path):
    rec = _base("r", "partial", total_grams=16.0,
                spools=[_row(200, 12.4, prefill=0.0,
                             weighed={"words": WORDS_KNOWN, "known_order": True}),
                        _row(300, 3.6, toolhead="HEAD-2", position=1)],
                heads_at_end=[{"toolhead": "HEAD-1", "position": 0, "sid": 200, "sids": [200]},
                              {"toolhead": "HEAD-2", "position": 1, "sid": 300, "sids": [300]}])
    res = run(tmp_path, RESPOND_JS + ROW_JS, {"pending": [rec], "spools": SPOOLS})
    assert res["weighed"] == "1" and float(res["box"]) == 0.0, res
    assert res["note"].startswith("⚠️ Weighed after this print ended: 0 g filled in"), res
    assert res["otherNote"] is False and float(res["otherBox"]) == 3.6, res
