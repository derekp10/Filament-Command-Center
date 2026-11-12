"""The 🛑 Review card with any number of spools on one head (hotfix round 2, R3;
Derek's picture check, 2026-11-12: "is this bound to only work with 2 spools or
is it unbound ... Probably should make sure that it can handle n+ spools.").

Runs the REAL overlay_mount.js and cancel_review.js under node's `vm` (the driver
in test_cancel_review_picker_scan_js.py: events, focus, values; no browser, no
container). Pinned:

  - a head split at three or four recorded swaps is one set: its header says it
    had 3 (or 4) spools this print, its rows sit in the order they printed, each
    with its own stretch of the print and its own pre-filled grams box;
  - a held set of three spools whose recorded swaps account for all of them is
    headed "had 3 spools this print"; a set of four, one of which FCC saw only
    when the print ended, is headed "FCC saw 4 spools on it"; each spool has its
    own empty grams box and says when FCC saw it there;
  - the set check adds up every box of the set: three boxes short of the head's
    grams ask once, the orange ⚠️ Yes naming the grams left over all three (or
    over, the grams over all three); placed exactly, the Apply posts at once, one
    charge per spool, on a partial card and a no_spool card alike;
  - an uncharged-grams card whose head held three spools says so in its words:
    "had 3 spools (#42, #229 and #300), so FCC charged none of them"; one whose
    head's split left two run-out spools short names both ("the records of #42
    and #229 hit 0 g"), and its picker still offers the spool on the head when
    the print ended, each run-out spool marked so where FCC saw it;
  - round 2's review: a completion card counts the spools in its banner, "so it
    charges none of them by itself" for a held head of three or more ("neither"
    for two), and "by the swap points ... (each run-out spool up to its swap,
    the next spool after it)" for a head split at two swaps or more (one swap
    keeps its words).

HEAD proof: run on 780a892 (R2, before R3), every test here passes by design
except test_a_shortfall_card_counts_three_spools_on_one_head (its words read
"had two spools (#42 and #229 and #300), so FCC charged neither") and
test_a_card_for_two_run_out_spools_names_both_and_offers_the_heads_own_spool
(it named only #42).
"""
from __future__ import annotations

from test_cancel_review_picker_scan_js import _base, pytestmark  # noqa: F401  (pytestmark: skip without node)
from test_cancel_review_review_fixes_js import _go

HEADS = [{"toolhead": "HEAD-5", "position": 4, "sid": 300, "sids": [300]},
         {"toolhead": "HEAD-7", "position": 6, "sid": 243, "sids": [243]},
         {"toolhead": "HEAD-5", "position": 4, "sid": 42, "when": "start"},
         {"toolhead": "HEAD-5", "position": 4, "sid": 229, "when": "during"}]


def _row(sid, pos, grams, toolhead="HEAD-5", **extra):
    row = {"sid": sid, "toolhead": toolhead, "position": pos, "grams": grams, "current_used": 700.0,
           "initial_weight": 1000.0, "remaining_before": 300.0, "remaining_after": 300.0 - grams,
           "display": f"#{sid} Test Spool", "color": "ff0000", "ambiguous": False}
    row.update(extra)
    return row


def _split(sid, grams, frm, to, runout=False):
    return _row(sid, 4, grams, auto_split=True, runout=runout,
                segments=[{"from": frm, "to": to, "runout": runout}])


def _entry(sid, when):
    return {"sid": sid, "when": when, "display": f"#{sid} Test", "remaining": 5.0}


SET3 = [_entry(42, "start"), _entry(229, "during"), _entry(300, "during")]
SET4 = SET3 + [_entry(301, "end")]

# A cancel split at two recorded run-outs (its rows given out of order).
SPLIT3 = _base("s3", "partial", heads_at_end=HEADS, total_grams=166.92,
               spools=[_split(300, 44.28, 0.25, 0.42), _row(243, 6, 75.32, toolhead="HEAD-7"),
                       _split(42, 17.0, None, 0.1, True), _split(229, 27.0, 0.1, 0.25, True)])
# A completion split at three recorded swaps: its last stretch runs to the end.
SPLIT4 = _base("s4", "spool_changed", auto_split=True, changed_positions=[4], progress=1.0,
               heads_at_end=HEADS, total_grams=90.28,
               spools=[_split(42, 17.0, None, 0.1, True), _split(229, 22.0, 0.1, 0.2, True),
                       _split(300, 22.0, 0.2, 0.3, True), _split(301, 29.28, 0.3, None)])
NOTE3 = ("HEAD-5's spool was swapped during the print (#42 to #229 at ~10%, then #229 to #300 at ~25%), "
         "but FCC couldn't split its grams at the swaps: split the 84.28 g among them, or put it all on one.")
HELD3 = _base("h3", "partial", spools=[_row(243, 6, 75.32, toolhead="HEAD-7")], heads_at_end=HEADS,
              total_grams=159.6, unresolved_usage={"4": 84.28}, unresolved_sets={"4": SET3},
              unresolved_notes={"4": NOTE3})
HELD4 = _base("h4", "partial", spools=[_row(243, 6, 75.32, toolhead="HEAD-7")], heads_at_end=HEADS,
              total_grams=159.6, unresolved_usage={"4": 84.28}, unresolved_sets={"4": SET4},
              unresolved_notes={"4": NOTE3})
NOSPOOL4 = _base("n4", "no_spool", usage_map={"4": 84.28}, heads_at_end=HEADS,
                 unresolved_sets={"4": SET4}, unresolved_notes={"4": NOTE3})
SHORT3 = _base("x#shortfall", "shortfall", rev=0, unresolved_usage={"4": 84.28},
               shortfall_causes={"4": {"why": "two_spools", "sids": [42, 229, 300], "toolhead": "HEAD-5"}},
               heads_at_end=[{"toolhead": "HEAD-5", "position": 4, "sid": None, "sids": [42, 229, 300]}])


# --------------------------------------------------------------------------- #
# How the sets are drawn                                                      #
# --------------------------------------------------------------------------- #

DRAWN_JS = r"""
const txt = (n) => (n ? n.textContent.replace(/\s+/g, ' ').trim() : null);
const setOf = (job) => {
  const c = cardOf(job);
  return c.querySelectorAll('.fcc-cr-set').map((s) => ({
    pos: s.getAttribute('data-pos'),
    head: txt(s.querySelector('.fcc-cr-set-head')),
    left: txt(s.querySelector('.fcc-cr-set-left')),
    rows: s.querySelectorAll('.fcc-cr-row').map((r) => ({
      sid: r.getAttribute('data-sid'), seg: txt(r.querySelector('.fcc-cr-seg')),
      boxes: r.querySelectorAll('.fcc-cr-grams').map((b) => b.value) })),
    lines: s.querySelectorAll('.fcc-cr-setline').map((l) => ({
      line: l.getAttribute('data-line'), pos: l.getAttribute('data-pos'), cls: l.className,
      text: txt(l), boxes: l.querySelectorAll('.fcc-cr-pgrams').map((b) => b.value) })),
  }));
};
const outside = (job, sid) => {
  const r = cardOf(job).querySelector(`.fcc-cr-row[data-sid="${sid}"]`);
  return !!r && !r.closest('.fcc-cr-set');
};
return { s3: setOf('s3'), s4: setOf('s4'), h3: setOf('h3'), h4: setOf('h4'), n4: setOf('n4'),
         s3own: outside('s3', '243'),
         why: cardOf('x#shortfall').querySelectorAll('.fcc-cr-why').map(txt) };
"""


def _drawn(tmp_path):
    return _go(tmp_path, DRAWN_JS, [SPLIT3, SPLIT4, HELD3, HELD4, NOSPOOL4, SHORT3])


def test_a_head_split_three_or_four_ways_is_one_set_in_the_order_it_printed(tmp_path):
    res = _drawn(tmp_path)
    (s3,) = res["s3"]
    assert s3["pos"] == "4" and s3["head"].startswith("T4 · HEAD-5 had 3 spools this print"), s3
    assert [(r["sid"], r["seg"], r["boxes"]) for r in s3["rows"]] == [
        ("42", "start → 10%, ran out", ["17"]), ("229", "10% → 25%, ran out", ["27"]),
        ("300", "25% → 42%", ["44.28"])]
    assert res["s3own"], "another head's row stays outside the set"
    (s4,) = res["s4"]
    assert s4["head"].startswith("T4 · HEAD-5 had 4 spools this print"), s4
    assert [(r["sid"], r["seg"]) for r in s4["rows"]] == [
        ("42", "start → 10%, ran out"), ("229", "10% → 20%, ran out"), ("300", "20% → 30%, ran out"),
        ("301", "30% → end")]
    assert all(len(r["boxes"]) == 1 and r["boxes"][0] for r in s4["rows"])


def test_a_held_set_of_three_or_four_gives_each_spool_its_own_empty_box(tmp_path):
    res = _drawn(tmp_path)
    (h3,) = res["h3"]
    # The recorded swaps account for all three: they printed there.
    assert h3["head"].startswith("T4 · HEAD-5 had 3 spools this print"), h3
    assert h3["left"] == "84.28 g to split"
    assert [ln["line"] for ln in h3["lines"]] == ["set:4:42", "set:4:229", "set:4:300"]
    assert all(ln["boxes"] == [""] and ln["pos"] == "4" and "fcc-cr-unline" in ln["cls"] for ln in h3["lines"])
    assert ["when the print started" in h3["lines"][0]["text"],
            "during the print" in h3["lines"][1]["text"],
            "during the print" in h3["lines"][2]["text"]] == [True, True, True], h3["lines"]
    (h4,) = res["h4"]
    # #301 was seen only when the print ended: the header claims no more than FCC saw.
    assert h4["head"].startswith("T4 · HEAD-5: FCC saw 4 spools on it"), h4
    assert [ln["line"] for ln in h4["lines"]] == ["set:4:42", "set:4:229", "set:4:300", "set:4:301"]
    assert "when the print ended" in h4["lines"][3]["text"]
    (n4,) = res["n4"]
    assert [ln["line"] for ln in n4["lines"]] == ["set:4:42", "set:4:229", "set:4:300", "set:4:301"]
    assert all("fcc-cr-pickline" in ln["cls"] and ln["boxes"] == [""] for ln in n4["lines"])


def test_a_shortfall_card_counts_three_spools_on_one_head(tmp_path):
    # On 780a892: AssertionError: ['HEAD-5 had two spools (#42 and #229 and #300), so FCC charged neither']
    res = _drawn(tmp_path)
    assert res["why"] == ["HEAD-5 had 3 spools (#42, #229 and #300), so FCC charged none of them"], res["why"]


# --------------------------------------------------------------------------- #
# The set check adds up every box, and the Apply posts one charge per spool    #
# --------------------------------------------------------------------------- #

FILL_JS = r"""
const fill = (c, line, grams) => {
  const b = c.querySelector(`.fcc-cr-pgrams[data-line="${CSS.escape(line)}"]`);
  b.value = String(grams); fire(b, 'input');
};
const look = (c) => {
  const btn = c.querySelector('.fcc-cr-confirm');
  const a = c.querySelector('.fcc-cr-set-alert');
  return { btn: btn.textContent, alert: a && a.style.display !== 'none' ? a.textContent : null,
           left: c.querySelector('.fcc-cr-set-left').textContent };
};
"""

SHORT_THEN_EXACT_JS = FILL_JS + r"""
const c = cardOf('h3');
fill(c, 'set:4:42', 10); fill(c, 'set:4:229', 30); fill(c, 'set:4:300', 40);
const before = look(c);
c.querySelector('.fcc-cr-confirm').click();
await settle(40);
const asked = Object.assign(look(c), { posted: posts('/api/cancel_deduct/confirm').length });
fill(c, 'set:4:300', 44.28);
const placed = look(c);
c.querySelector('.fcc-cr-confirm').click();
await settle(40);
return { before, asked, placed, posted: posts('/api/cancel_deduct/confirm') };
"""


def test_three_boxes_are_added_up_and_placed_exactly_post_one_charge_each(tmp_path):
    res = _go(tmp_path, SHORT_THEN_EXACT_JS, [HELD3])
    assert res["before"]["left"] == "4.28 g of 84.28 g still to place", res
    asked = res["asked"]
    assert asked["posted"] == 0, asked
    assert asked["btn"] == "⚠️ Yes, leave 4.28 g uncharged", asked
    assert asked["alert"] == ("⚠️ T4 · HEAD-5: 4.28 g of its 84.28 g aren't placed. Press ⚠️ Yes below to "
                              "leave them uncharged."), asked
    # A box changed: the button is its own again, and the set is placed.
    assert res["placed"] == {"btn": "Confirm deduct", "alert": None, "left": "All 84.28 g placed"}, res
    assert res["posted"] == [{"printer_name": "TESTER", "job_id": "h3", "charges": [
        {"row": 243, "sid": 243, "grams": 75.32},
        {"position": 4, "sid": 42, "grams": 10}, {"position": 4, "sid": 229, "grams": 30},
        {"position": 4, "sid": 300, "grams": 44.28}]}], res


OVER_JS = FILL_JS + r"""
const c = cardOf('h3');
fill(c, 'set:4:42', 50); fill(c, 'set:4:229', 30); fill(c, 'set:4:300', 40);
c.querySelector('.fcc-cr-confirm').click();
await settle(40);
return Object.assign(look(c), { posted: posts('/api/cancel_deduct/confirm').length });
"""


def test_three_boxes_over_the_heads_grams_name_the_grams_over_all_three(tmp_path):
    res = _go(tmp_path, OVER_JS, [HELD3])
    assert res["posted"] == 0, res
    assert res["left"] == "35.72 g more than the 84.28 g FCC computed", res
    assert res["btn"] == "⚠️ Yes, charge 35.72 g more", res


FOUR_JS = FILL_JS + r"""
for (const job of ['h4', 'n4']) {
  const c = cardOf(job);
  fill(c, 'set:4:42', 10); fill(c, 'set:4:229', 20); fill(c, 'set:4:300', 30); fill(c, 'set:4:301', 24.28);
  c.querySelector('.fcc-cr-confirm').click();
  await settle(40);
}
return { posted: posts('/api/cancel_deduct/confirm') };
"""


def test_four_boxes_placed_exactly_post_four_charges_on_either_card(tmp_path):
    res = _go(tmp_path, FOUR_JS, [HELD4, NOSPOOL4])
    four = [{"position": 4, "sid": 42, "grams": 10}, {"position": 4, "sid": 229, "grams": 20},
            {"position": 4, "sid": 300, "grams": 30}, {"position": 4, "sid": 301, "grams": 24.28}]
    assert res["posted"] == [
        {"printer_name": "TESTER", "job_id": "h4", "charges": [{"row": 243, "sid": 243, "grams": 75.32}] + four},
        {"printer_name": "TESTER", "job_id": "n4", "charges": four}], res


# Two run-out spools of one head that couldn't take their split: the card that
# holds their grams, as the server now builds it (test_many_spools_one_head_hotfix.py).
RUNOUT2 = _base("r#shortfall", "shortfall", rev=0, unresolved_usage={"4": 20.48},
                shortfall_causes={"4": {"why": "ran_out", "sid": 42, "sids": [42, 229], "toolhead": "HEAD-5",
                                        "archived": True}},
                heads_at_end=[{"toolhead": "HEAD-5", "position": 4, "sid": 300, "sids": [300]},
                              {"toolhead": "HEAD-5", "position": 4, "sid": 42, "when": "start", "archived": True},
                              {"toolhead": "HEAD-5", "position": 4, "sid": 229, "when": "during",
                               "archived": True}])

RUNOUT2_JS = r"""
const c = cardOf('r#shortfall');
return { why: c.querySelectorAll('.fcc-cr-why').map((n) => n.textContent.replace(/\s+/g, ' ').trim()),
         groups: groupsOf(lineOf(c, 'pos:4').sel).filter((g) => g.group) };
"""


def test_a_card_for_two_run_out_spools_names_both_and_offers_the_heads_own_spool(tmp_path):
    # On 780a892: AssertionError: ["#42's record hit 0 g on HEAD-5 (archived)"] (the second spool
    # wasn't named)
    res = _go(tmp_path, RUNOUT2_JS, [RUNOUT2])
    assert res["why"] == ["the records of #42 and #229 hit 0 g on HEAD-5 (archived)"], res["why"]
    assert [(g["group"], [o["text"] for o in g["options"]]) for g in res["groups"]] == [
        ("When the print ended", ["#300 — on HEAD-5 when the print ended"]),
        ("When the print started", ["#42 — on HEAD-5 when the print started (ran out, archived)"]),
        ("During the print", ["#229 — on HEAD-5 during the print (ran out, archived)"])], res["groups"]


# --------------------------------------------------------------------------- #
# Round 2's review (2026-11-12): the completion banners count the spools       #
# --------------------------------------------------------------------------- #
# A completion card whose held head had three spools said FCC "charges neither by
# itself"; one split at two or more swaps on a head said "by the swap point ... the
# run-out spool up to the swap, the replacement after it". One swap, and two spools,
# keep their words.

NOTE_LINE3 = ("HEAD-5 had 3 spools when the print ended (#42, #229 and #300), so FCC can't tell which one "
              "printed. Pick the spool it used.")
CHANGED3 = _base("c3", "spool_changed", auto_split=False, changed_positions=[4], progress=1.0,
                 heads_at_end=HEADS, total_grams=104.28, spools=[_row(243, 6, 20.0, toolhead="HEAD-7")],
                 unresolved_usage={"4": 84.28}, unresolved_sets={"4": SET3}, unresolved_notes={"4": NOTE3})
# Three spools on the head when the print ended: one held line, no set.
CHANGED3_LINE = _base("c3l", "spool_changed", auto_split=False, changed_positions=[4], progress=1.0,
                      heads_at_end=[{"toolhead": "HEAD-5", "position": 4, "sid": None, "sids": [42, 229, 300]},
                                    {"toolhead": "HEAD-7", "position": 6, "sid": 243, "sids": [243]}],
                      total_grams=104.28, spools=[_row(243, 6, 20.0, toolhead="HEAD-7")],
                      unresolved_usage={"4": 84.28}, unresolved_notes={"4": NOTE_LINE3})
CHANGED2 = _base("c2", "spool_changed", auto_split=False, changed_positions=[4], progress=1.0,
                 heads_at_end=HEADS, total_grams=104.28, spools=[_row(243, 6, 20.0, toolhead="HEAD-7")],
                 unresolved_usage={"4": 84.28}, unresolved_sets={"4": SET3[:2]}, unresolved_notes={"4": NOTE3})
# A completion split at one swap.
SPLIT2 = _base("s2", "spool_changed", auto_split=True, changed_positions=[4], progress=1.0,
               heads_at_end=HEADS, total_grams=84.28,
               spools=[_split(42, 30.0, None, 0.19, True), _split(229, 54.28, 0.19, None)])

BANNER_JS = r"""
const txt = (n) => (n ? n.textContent.replace(/\s+/g, ' ').trim() : null);
const out = {};
for (const j of ['c3', 'c3l', 'c2', 's4', 's2']) {
  out[j] = txt(cardOf(j).querySelectorAll('div').find((d) => (d.getAttribute('style') || '').includes('background:#221d12')));
}
return out;
"""


def test_the_completion_banners_count_the_spools(tmp_path):
    # On e777bcd: AssertionError: (c3's banner read "... so it charges neither by itself ..." over a
    # head of three spools; s4's "by the swap point ... the run-out spool up to the swap, the
    # replacement after it" over three swaps)
    res = _go(tmp_path, BANNER_JS, [CHANGED3, CHANGED3_LINE, CHANGED2, SPLIT4, SPLIT2])
    for job in ("c3", "c3l"):
        assert "so it charges none of them by itself: each such head is listed below with every spool it had" \
            in res[job], (job, res[job])
        assert "neither" not in res[job], (job, res[job])
    assert "so it charges neither by itself" in res["c2"], res["c2"]
    assert ("FCC auto-split the slicer total by the swap points — each row below is charged only its own "
            "segment (each run-out spool up to its swap, the next spool after it), pre-filled.") in res["s4"], \
        res["s4"]
    assert "Each run-out spool's sensor→nozzle remnant is included" in res["s4"], res["s4"]
    assert "the replacement after it" not in res["s4"] and "The run-out spool's" not in res["s4"], res["s4"]
    # One swap keeps its words, as they always were.
    assert ("FCC auto-split the slicer total by the swap point — each row below is charged only its own "
            "segment (the run-out spool up to the swap, the replacement after it), pre-filled.") in res["s2"], \
        res["s2"]
    assert "The run-out spool's sensor→nozzle remnant is included" in res["s2"], res["s2"]
