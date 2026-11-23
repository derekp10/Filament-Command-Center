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


MMU_JS = r"""
const c = cardOf('m#shortfall');
return { why: (c.querySelector('.fcc-cr-why') || {}).textContent || null };
"""


def test_mmu_slots_sharing_one_number_say_so_on_the_uncharged_grams_card(tmp_path):
    """Group 64.6: the card names the slots and how to set them up, never "MMU-1 had
    two spools". RED on 6b76460."""
    rec = _base("m#shortfall", "shortfall", rev=0, total_grams=5.0, unresolved_usage={"0": 5.0},
                shortfall_causes={"0": {"why": "two_spools", "sid": None, "toolhead": "MMU-1",
                                        "archived": False, "sids": [401, 402],
                                        "mmu_shared": ["MMU-1", "MMU-2"]}},
                heads_at_end=[{"toolhead": "MMU-1", "position": 0, "sid": None, "sids": [401, 402],
                               "mmu_shared": ["MMU-1", "MMU-2"]}])
    res = run(tmp_path, RESPOND_JS + MMU_JS, {"pending": [rec], "spools": SPOOLS})
    why = " ".join((res["why"] or "").split())
    assert why.startswith("MMU slots MMU-1 and MMU-2 share one Position and each held a spool "
                          "(#401 and #402), so FCC charged none of them"), why
    # Group 64 review (O2): in the editor's own terms, its 0-based Position.
    assert "own Position in Settings (slot 1 = Position 0, slot 2 = Position 1, …)" in why, why


PICK_JS = r"""
const c = cardOf('k#shortfall');
const sel = c.querySelector('.fcc-cr-pick');
return { options: Array.from(sel.querySelectorAll('option')).map((o) => o.textContent.trim()),
         groups: Array.from(sel.querySelectorAll('optgroup')).map((g) => g.getAttribute('label')) };
"""


def test_the_picker_marks_only_the_run_out_spool_and_names_a_picked_one(tmp_path):
    """Group 64.2 (7) / (8). RED on 9fc269b: both of the head's spools read as
    usable (no per-spool mark), and the picked spool read as "on HEAD-1"."""
    rec = _base("k#shortfall", "shortfall", rev=0, total_grams=2.0, unresolved_usage={"0": 2.0},
                shortfall_causes={"0": {"why": "not_charged", "sid": None, "toolhead": "HEAD-1",
                                        "archived": False}},
                heads_at_end=[{"toolhead": "HEAD-1", "position": 0, "sid": None, "sids": [100, 101],
                               "archived_sids": [100]},
                              {"toolhead": "HEAD-1", "position": 0, "sid": 300, "archived": True,
                               "when": "picked"}])
    res = run(tmp_path, RESPOND_JS + PICK_JS, {"pending": [rec], "spools": SPOOLS})
    opts = res["options"]
    assert any(o.startswith("#100 — on HEAD-1") and o.endswith("(ran out, archived)") for o in opts), opts
    assert any(o.startswith("#101 — on HEAD-1") and "ran out" not in o for o in opts), opts
    assert "#300 — picked for HEAD-1 on this card (ran out, archived)" in opts, opts
    assert "Picked on this card" in res["groups"], res["groups"]


SET_UP_JS = r"""
const c = cardOf('ps');
const boxes = c.querySelectorAll('.fcc-cr-heldset .fcc-cr-pgrams');
boxes[0].value = '84.28';
boxes[0].dispatchEvent(new Event('input', { bubbles: true }));
c.querySelector('.fcc-cr-confirm').click();
await settle(60);
return { posted: posts('/api/cancel_deduct/confirm') };
"""


def test_a_set_that_adds_up_goes_out_on_one_press_with_no_set_ack(tmp_path):
    """Group 64.2 (2): `set_ack` rides only on the press that answered the set's
    question; a set whose grams add up asks nothing and says nothing."""
    from test_cancel_review_review_fixes_js import PARTIAL_SET
    res = run(tmp_path, RESPOND_JS + SET_UP_JS, {"pending": [PARTIAL_SET], "spools": SPOOLS})
    assert len(res["posted"]) == 1, res
    assert "set_ack" not in res["posted"][0], res["posted"][0]
    assert any(c.get("grams") == 84.28 for c in res["posted"][0].get("charges") or []), res["posted"][0]


# --------------------------------------------------------------------------- #
# Group 64 review, the page half (O2, O3, O4, R1, Y2)                         #
# --------------------------------------------------------------------------- #

def test_the_settings_mmu_sentence_names_the_editors_position():
    """O2, red on 82dbb38 ("slot 1 = Toolhead 1": the editor's only number is a
    0-based Position, so following it charged each slot the next slot's filament)."""
    import pathlib
    src = (pathlib.Path(__file__).resolve().parent.parent / "static" / "js" / "modules"
           / "inv_settings.js").read_text(encoding="utf-8")
    flat = " ".join(src.split())
    assert "give each slot its own Position, the slicer's tool number (slot 1 = Position 0 for T0, " \
           "slot 2 = Position 1 for T1, and so on)" in flat
    assert "Toolhead 1" not in flat


CONFIRM_ANSWER_JS = r"""
const __base = window.__respond;
window.__respond = (url, method, body) => (url.startsWith('/api/cancel_deduct/confirm')
    ? { body: D.confirm } : __base(url, method, body));
"""


def _mixed(job):
    return _base(job, "shortfall", rev=0, total_grams=15.4, unresolved_usage={"0": 12.4, "1": 3.0},
                 shortfall_prefill={"0": 0.0},
                 shortfall_causes={"0": {"why": "weighed", "sid": 200, "toolhead": "HEAD-1", "archived": False,
                                         "known_order": True, "words": WORDS_KNOWN},
                                   "1": {"why": "no_spool", "toolhead": "HEAD-2"}},
                 heads_at_end=[{"toolhead": "HEAD-1", "position": 0, "sid": 200, "sids": [200]},
                               {"toolhead": "HEAD-2", "position": 1, "sid": None}])


MIXED_JS = r"""
const c = cardOf('x#shortfall');
const L = lineOf(c, 'pos:1');
pickIn(L.sel, 'other');
L.box.value = '57'; key(L.box, 'Enter');
await settle(40);
const box = c.querySelector('.fcc-cr-shortline[data-pos="1"] .fcc-cr-pgrams');
box.value = '3'; box.dispatchEvent(new Event('input', { bubbles: true }));
c.querySelector('.fcc-cr-confirm').click();
await settle(60);
return { posted: posts('/api/cancel_deduct/confirm'), toasts: __rec.toasts,
         gone: !cardOf('x#shortfall') };
"""


def test_a_pick_beside_a_weighed_line_left_at_0g_sends_settle_held_with_it(tmp_path):
    """O3, red on 82dbb38 (it posted the pick alone, and the card kept asking for a
    spool for the 12.40 g the scale already counted). One toast says both."""
    confirm = {"status": "confirmed", "applied": [{"sid": 57, "grams": 3.0, "remaining": 409.4}],
               "errors": [], "settled_held": True, "shortfall_g": 12.4, "settled_unsure": False,
               "left_weighed": [{"line": "0", "sid": 200, "grams": 12.4, "known_order": True}]}
    res = run(tmp_path, RESPOND_JS + CONFIRM_ANSWER_JS + MIXED_JS,
              {"pending": [_mixed("x#shortfall")], "spools": SPOOLS, "confirm": confirm})
    assert res["posted"] == [{"printer_name": "TESTER", "job_id": "x#shortfall", "rev": 0,
                              "charges": [{"position": 1, "sid": 57, "grams": 3}],
                              "settle_held": True}], res["posted"]
    assert res["toasts"] == [{"msg": "Deducted from 1 spool(s); left 12.4g uncharged on #200: it was "
                                     "weighed after the print.", "type": "success", "duration": 2000}], res["toasts"]
    assert res["gone"] is True


SETTLE_TOAST_JS = r"""
const c = cardOf(__JOB__);
c.querySelector('.fcc-cr-confirm').click();
await settle(60);
return { posted: posts('/api/cancel_deduct/confirm'), toasts: __rec.toasts };
"""


def _settle(tmp_path, job, known, confirm):
    body = SETTLE_TOAST_JS.replace("__JOB__", repr(job))
    return run(tmp_path, RESPOND_JS + CONFIRM_ANSWER_JS + body,
               {"pending": [_held(job, known)], "spools": SPOOLS, "confirm": confirm})


def test_a_settle_raises_one_toast_and_no_weigh_it_warning(tmp_path):
    """Y2, red on 82dbb38 (a second, 7 s toast: "12.4g couldn't be applied — weigh
    that spool to true up", against the settle the person chose)."""
    confirm = {"status": "confirmed", "applied": [], "settled_held": True, "shortfall_g": 12.4,
               "settled_unsure": False,
               "left_weighed": [{"line": "0", "sid": 200, "grams": 12.4, "known_order": True}]}
    res = _settle(tmp_path, "k", True, confirm)
    assert res["toasts"] == [{"msg": "Left 12.4g uncharged on #200: it was weighed after the print.",
                              "type": "success", "duration": 2000}], res["toasts"]


def test_a_settle_of_a_change_fcc_cant_place_says_it_was_left_as_set(tmp_path):
    """Y2's words: a change FCC couldn't place in time is no weighing FCC knows of."""
    confirm = {"status": "confirmed", "applied": [], "settled_held": True, "shortfall_g": 12.4,
               "settled_unsure": True,
               "left_weighed": [{"line": "0", "sid": 200, "grams": 12.4, "known_order": False}]}
    body = SETTLE_TOAST_JS.replace("__JOB__", repr("u"))
    rec = _held("u", False)
    rec["shortfall_prefill"] = {"0": 0.0}      # the person set it to 0 (as if typed)
    res = run(tmp_path, RESPOND_JS + CONFIRM_ANSWER_JS + body,
              {"pending": [rec], "spools": SPOOLS, "confirm": confirm})
    assert res["posted"][0].get("settle_held") is True, res["posted"]
    assert res["toasts"] == [{"msg": "Left 12.4g uncharged on #200 as set: its weight changed after the print.",
                              "type": "success", "duration": 2000}], res["toasts"]


ROW_LEFT_JS = r"""
const c = cardOf('r');
c.querySelector('.fcc-cr-confirm').click();
await settle(60);
return { posted: posts('/api/cancel_deduct/confirm'), toasts: __rec.toasts };
"""


def test_a_cancels_weighed_row_left_at_0g_is_said_by_name(tmp_path):
    """O4, red on 82dbb38 ("Nothing was charged: the spool picked has 0 g left on
    record", false: the row was left at the 0 g filled in, the spool weighed)."""
    rec = _base("r", "partial", total_grams=12.4,
                spools=[_row(200, 12.4, prefill=0.0, weighed={"words": WORDS_KNOWN, "known_order": True})],
                heads_at_end=[{"toolhead": "HEAD-1", "position": 0, "sid": 200, "sids": [200]}])
    confirm = {"status": "confirmed", "applied": [], "errors": [], "shortfall_g": 0.0, "settled_unsure": False,
               "left_weighed": [{"line": "0", "sid": 200, "grams": 12.4, "known_order": True}]}
    res = run(tmp_path, RESPOND_JS + CONFIRM_ANSWER_JS + ROW_LEFT_JS,
              {"pending": [rec], "spools": SPOOLS, "confirm": confirm})
    assert res["posted"] == [{"printer_name": "TESTER", "job_id": "r", "updates": {}, "rev": 0}], res["posted"]
    assert res["toasts"] == [{"msg": "Left 12.4g uncharged on #200: it was weighed after the print.",
                              "type": "success", "duration": 2000}], res["toasts"]


def test_nothing_charged_with_no_weighed_row_left_keeps_its_words(tmp_path):
    """A clamp (the spool picked had nothing left) keeps its 7 s warning. Passes on
    82dbb38 by design."""
    rec = _base("r", "partial", total_grams=12.4, spools=[_row(200, 12.4)],
                heads_at_end=[{"toolhead": "HEAD-1", "position": 0, "sid": 200, "sids": [200]}])
    confirm = {"status": "confirmed", "applied": [{"sid": 200, "grams": 0.0, "remaining": 0.0}],
               "errors": [], "shortfall_g": 0.0}
    res = run(tmp_path, RESPOND_JS + CONFIRM_ANSWER_JS + ROW_LEFT_JS,
              {"pending": [rec], "spools": SPOOLS, "confirm": confirm})
    assert res["toasts"] == [{"msg": "Nothing was charged: the spool picked has 0 g left on record.",
                              "type": "warning", "duration": 7000}], res["toasts"]


DOUBLE_JS = r"""
window.__shields = 0;
window.fccShieldNextPress = () => { window.__shields += 1; };
const c1 = cardOf('a'), c2 = cardOf('b');
c1.querySelector('.fcc-cr-confirm').click();
await settle(60);
const second = c2.querySelector('.fcc-cr-confirm');
second.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, detail: 2 }));
await settle(60);
const after = posts('/api/cancel_deduct/confirm').map((p) => p.job_id);
second.click();                          // a press of its own, later: an Apply
await settle(60);
return { after, then: posts('/api/cancel_deduct/confirm').map((p) => p.job_id),
         gone: !cardOf('a'), shields: window.__shields };
"""


def test_a_double_clicks_second_press_never_applies_the_next_card(tmp_path):
    """R1, red on 82dbb38 (card b was applied too, unread: card a's Apply took it
    away and b slid up under the pointer). The removal shields the second press;
    the Confirm handler refuses a click with detail 2 besides."""
    cards = [_base(j, "partial", total_grams=3.6,
                   spools=[_row(300, 3.6, toolhead="HEAD-2", position=1)],
                   heads_at_end=[{"toolhead": "HEAD-2", "position": 1, "sid": 300, "sids": [300]}])
             for j in ("a", "b")]
    confirm = {"status": "confirmed", "applied": [{"sid": 300, "grams": 3.6, "remaining": 896.4}],
               "errors": [], "shortfall_g": 0.0}
    res = run(tmp_path, RESPOND_JS + CONFIRM_ANSWER_JS + DOUBLE_JS,
              {"pending": cards, "spools": SPOOLS, "confirm": confirm})
    assert res["gone"] is True and res["shields"] >= 1, res
    assert res["after"] == ["a"], res
    assert res["then"] == ["a", "b"], res


KEPT_JS = r"""
const c = cardOf('x#shortfall');
const L = lineOf(c, 'pos:1');
pickIn(L.sel, 'other');
L.box.value = '57'; key(L.box, 'Enter');
await settle(40);
const box = c.querySelector('.fcc-cr-shortline[data-pos="1"] .fcc-cr-pgrams');
box.value = '3'; box.dispatchEvent(new Event('input', { bubbles: true }));
cardOf('x#shortfall').querySelector('.fcc-cr-confirm').click();
await settle(80);
return { toasts: __rec.toasts };
"""


def test_a_kept_cards_toast_counts_its_weighed_line_apart(tmp_path):
    """Group 64 fix review (FS2), red on abb67aa ("14.4g still have no spool — pick
    another spool", the weighed line's 12.4 g among them, which the scale counted).
    The picked spool took 1 g of its 3, so the card is kept: 2 g with no spool, and
    #200's weighed line waiting apart."""
    confirm = {"status": "confirmed", "kept": True, "rev": 1, "shortfall_g": 14.4,
               "applied": [{"sid": 57, "grams": 1.0, "remaining": 0.0}], "errors": [],
               "kept_weighed": [{"line": "0", "sid": 200, "grams": 12.4, "known_order": True}]}
    res = run(tmp_path, RESPOND_JS + CONFIRM_ANSWER_JS + KEPT_JS,
              {"pending": [_mixed("x#shortfall")], "spools": SPOOLS, "confirm": confirm})
    warned = [t for t in res["toasts"] if t["type"] == "warning"]
    assert warned and warned[0]["msg"] == (
        "Charged 1g. 2g still have no spool — pick another spool, or Discard. 12.4g on #200, weighed "
        "after the print, stay on the card: Apply again to leave them uncharged, or Discard."), res["toasts"]


def test_a_kept_cards_toast_with_no_weighed_line_keeps_its_words(tmp_path):
    """Passes on abb67aa by design (an answer with no kept_weighed, as from an older
    server, reads as before)."""
    confirm = {"status": "confirmed", "kept": True, "rev": 1, "shortfall_g": 2.0,
               "applied": [{"sid": 57, "grams": 1.0, "remaining": 0.0}], "errors": []}
    res = run(tmp_path, RESPOND_JS + CONFIRM_ANSWER_JS + KEPT_JS,
              {"pending": [_mixed("x#shortfall")], "spools": SPOOLS, "confirm": confirm})
    warned = [t for t in res["toasts"] if t["type"] == "warning"]
    assert warned and warned[0]["msg"] == "Charged 1g. 2g still have no spool — pick another spool, or Discard.", \
        res["toasts"]


DISCARD_JS = r"""
window.__shields = 0;
window.fccShieldNextPress = () => { window.__shields += 1; };
const __base2 = window.__respond;
window.__respond = (url, method, body) => (url.startsWith('/api/cancel_deduct/dismiss')
    ? { body: { status: 'dismissed' } } : __base2(url, method, body));
const btn = cardOf('a').querySelector('.fcc-cr-discard');
btn.click();                              // arms it
await settle(750);                        // past the double-press window
btn.click();                              // the discard itself
await settle(60);
return { gone: !cardOf('a'), shields: window.__shields };
"""


def test_a_discard_shields_the_press_behind_it_too(tmp_path):
    """Group 64 fix review (the page reviewer's note on R1), red on 89fa17b: a
    Discard's card goes, the next card slides up under the pointer, and a press under
    700 ms there would land on it; the removal shields it, as Confirm's does."""
    cards = [_base(j, "partial", total_grams=3.6, spools=[_row(300, 3.6, toolhead="HEAD-2", position=1)],
                   heads_at_end=[{"toolhead": "HEAD-2", "position": 1, "sid": 300, "sids": [300]}])
             for j in ("a", "b")]
    res = run(tmp_path, RESPOND_JS + DISCARD_JS, {"pending": cards, "spools": SPOOLS})
    assert res["gone"] is True and res["shields"] == 1, res


HELD_JS = r"""
const c = cardOf('h');
c.querySelector('.fcc-cr-confirm').click();
await settle(120);
const again = cardOf('h');
return { toasts: __rec.toasts, kept: !!again,
         notice: again ? ((again.querySelector('.fcc-cr-card-notice') || {}).textContent || '') : null };
"""


def test_a_held_line_keeps_the_card_on_screen_and_says_why(tmp_path):
    """Group 64 full review (RW1 / OR1 / SP3 / PR1), red on c7073d8 (the card was taken
    off the screen as if done, and the toast said a spool had failed). The Apply's
    answer holds #200 (weighed after the card was made): the card is drawn again from
    the server's, its words on the card and in a warning."""
    words = "#200 on HEAD-1 was weighed on the Quick-Weigh at 14:05, after this print ended (at 13:50), " \
            "so the scale already counted its 12.40 g"
    rec = _base("h", "partial", total_grams=16.0,
                spools=[_row(200, 12.4), _row(300, 3.6, toolhead="HEAD-2", position=1)],
                heads_at_end=[{"toolhead": "HEAD-1", "position": 0, "sid": 200, "sids": [200]},
                              {"toolhead": "HEAD-2", "position": 1, "sid": 300, "sids": [300]}])
    confirm = {"status": "confirmed", "applied": [{"sid": 300, "grams": 3.6, "remaining": 896.4}],
               "errors": [{"sid": 200, "error": words + ". Nothing was charged to it: check its line and Apply again."}],
               "held": [{"sid": 200, "words": words, "known_order": True}]}
    res = run(tmp_path, RESPOND_JS + CONFIRM_ANSWER_JS + HELD_JS, {"pending": [rec], "spools": SPOOLS, "confirm": confirm})
    assert res["kept"] is True, res
    warned = [t for t in res["toasts"] if t["type"] == "warning"]
    # Group 64 fix review 2 (CP5): the charged spool leaves the redrawn card; its charge
    # is said on the card's own line, before the hold's words.
    assert warned and warned[0]["msg"] == ("Charged 3.6g to #300. " + words
                                           + ". Nothing was charged to it: check its line and Apply again."), res
    assert not any("failed" in t["msg"] for t in res["toasts"]), res["toasts"]
    assert " ".join(res["notice"].split()).startswith("Charged 3.6g to #300."), res["notice"]
    assert "Nothing was charged to it" in " ".join(res["notice"].split()), res["notice"]


# --------------------------------------------------------------------------- #
# Group 64 full review, chunk 2: a hold with nothing else applied (FX3), and   #
# every card's revision (FX7)                                                  #
# --------------------------------------------------------------------------- #

def test_a_hold_with_nothing_else_applied_is_a_hold_not_a_failed_apply(tmp_path):
    """FX3, red on 89faa0b (a 7 s error toast, as if the Apply had failed). A one-row
    card's only spool is held: the server answers status 'error' with `held`; the
    page warns, keeps the card and draws it again, as for a hold beside a charge."""
    words = "#200 on HEAD-1 was weighed on the Quick-Weigh at 14:05, after this print ended (at 13:50), " \
            "so the scale already counted its 12.40 g"
    rec = _base("h", "partial", total_grams=12.4, spools=[_row(200, 12.4)],
                heads_at_end=[{"toolhead": "HEAD-1", "position": 0, "sid": 200, "sids": [200]}])
    confirm = {"status": "error", "applied": [],
               "errors": [{"sid": 200, "error": words + ". Nothing was charged to it: check its line and Apply again."}],
               "held": [{"sid": 200, "words": words, "known_order": True}]}
    res = run(tmp_path, RESPOND_JS + CONFIRM_ANSWER_JS + HELD_JS, {"pending": [rec], "spools": SPOOLS, "confirm": confirm})
    assert res["kept"] is True, res
    assert not [t for t in res["toasts"] if t["type"] == "error"], res["toasts"]
    warned = [t for t in res["toasts"] if t["type"] == "warning"]
    assert warned and warned[0]["msg"] == words + ". Nothing was charged to it: check its line and Apply again.", res
    assert "Nothing was charged to it" in " ".join(res["notice"].split()), res["notice"]


def test_a_hold_beside_a_failed_write_says_both(tmp_path):
    """FX3's other side: a write that failed beside the hold is said too, in red."""
    words = "#200 on HEAD-1 was weighed on the Quick-Weigh at 14:05, after this print ended (at 13:50), " \
            "so the scale already counted its 12.40 g"
    rec = _base("h", "partial", total_grams=16.0,
                spools=[_row(200, 12.4), _row(300, 3.6, toolhead="HEAD-2", position=1)],
                heads_at_end=[{"toolhead": "HEAD-1", "position": 0, "sid": 200, "sids": [200]},
                              {"toolhead": "HEAD-2", "position": 1, "sid": 300, "sids": [300]}])
    confirm = {"status": "error", "applied": [],
               "errors": [{"sid": 200, "error": words + ". Nothing was charged to it: check its line and Apply again."},
                          {"sid": 300, "error": "HTTP 500: database is locked"}],
               "held": [{"sid": 200, "words": words, "known_order": True}]}
    res = run(tmp_path, RESPOND_JS + CONFIRM_ANSWER_JS + HELD_JS, {"pending": [rec], "spools": SPOOLS, "confirm": confirm})
    assert res["kept"] is True, res
    said = [t for t in res["toasts"] if t["type"] == "error"]
    assert said and "1 other spool(s) failed" in said[0]["msg"] and said[0]["msg"].startswith(words), res["toasts"]


REV_JS = r"""
for (const j of ['p', 'n']) {
  const c = cardOf(j);
  if (j === 'n') {
    const L = c.querySelector('.fcc-cr-pickline');
    const sel = L.querySelector('.fcc-cr-pick');
    pickIn(sel, '229');
    const g = L.querySelector('.fcc-cr-pgrams'); g.value = '84.28';
    g.dispatchEvent(new Event('input', { bubbles: true }));
  }
  c.querySelector('.fcc-cr-confirm').click();
  await settle(120);
}
return { posted: posts('/api/cancel_deduct/confirm') };
"""


def test_every_cards_apply_sends_its_revision(tmp_path):
    """FX7, red on 89faa0b (only an uncharged-grams card sent one): a review card
    and a no_spool card each send the revision they were drawn with, so an Apply
    from a view drawn before a hold is refused instead of charging the held row."""
    held = _base("p", "partial", rev=1, total_grams=12.4, spools=[_row(200, 12.4)],
                 heads_at_end=[{"toolhead": "HEAD-1", "position": 0, "sid": 200, "sids": [200]}])
    plain = _base("n", "no_spool", usage_map={"4": 84.28},
                  heads_at_end=[{"toolhead": "HEAD-5", "position": 4, "sid": 229, "sids": [229]}])
    res = run(tmp_path, RESPOND_JS + REV_JS, {"pending": [held, plain], "spools": SPOOLS})
    revs = {str(b.get("job_id")): b.get("rev") for b in res["posted"]}
    assert revs == {"p": 1, "n": 0}, res["posted"]



# --------------------------------------------------------------------------- #
# Group 64 full review, chunk 2: the held card's head words (WD1), a weighed   #
# row's preview (WD6), an outcome said on the panel (PI1)                      #
# --------------------------------------------------------------------------- #

HEAD_JS = r"""
const out = {};
for (const j of ['k', 'u', 'x#shortfall']) {
  const c = cardOf(j);
  out[j] = { title: c.querySelector('.fcc-cr-short-title').textContent.replace(/\s+/g, ' ').trim(),
             banner: c.querySelector('.fcc-cr-short-banner').textContent.replace(/\s+/g, ' ').trim() };
}
return out;
"""


def test_a_card_of_held_lines_says_why_they_are_held_not_that_they_went_nowhere(tmp_path):
    """WD1, red on 1c5a85f ("12.4g went to no spool", and a banner sending the person
    to look for a joined spool). A card whose only line FCC held on purpose says the
    grams are held and why; a card with other lines too counts them apart."""
    res = run(tmp_path, RESPOND_JS + HEAD_JS,
              {"pending": [_held("k", True), _held("u", False), _mixed("x#shortfall")], "spools": SPOOLS})
    assert res["k"]["title"] == "⚖️ TESTER — 12.4g held: #200 was weighed after this print", res["k"]
    assert res["k"]["banner"].startswith("FCC held these grams instead of charging them: #200 was weighed"), res["k"]
    assert "went to no spool" not in res["k"]["banner"] and "joined spool" not in res["k"]["banner"], res["k"]
    assert res["u"]["title"] == "⚖️ TESTER — 12.4g held: #200 changed weight after this print", res["u"]
    assert "can't tell whether the scale counted this print" in res["u"]["banner"], res["u"]
    assert res["x#shortfall"]["title"] == "⚖️ TESTER — 3g went to no spool; 12.4g held", res["x#shortfall"]
    assert "but 3g went to no spool" in res["x#shortfall"]["banner"], res["x#shortfall"]
    assert "The 12.4g on #200 is held, not charged: it was weighed after this print ended" \
        in res["x#shortfall"]["banner"], res["x#shortfall"]


PREVIEW_JS = r"""
const c = cardOf('w');
return { preview: c.querySelector('.fcc-cr-preview[data-sid="200"]').textContent.replace(/\s+/g, ' ').trim(),
         plain: c.querySelector('.fcc-cr-preview[data-sid="300"]').textContent.replace(/\s+/g, ' ').trim(),
         box: c.querySelector('.fcc-cr-grams[data-sid="200"]').value };
"""


def test_a_weighed_rows_preview_follows_the_0g_filled_in(tmp_path):
    """WD6, red on 1c5a85f ("0 → 887.6g": the spool losing the print the note says it
    won't be charged). A plain row keeps the server's figure."""
    rec = _base("w", "partial", total_grams=16.0,
                spools=[_row(200, 12.4, prefill=0.0, weighed={"words": WORDS_KNOWN, "known_order": True}),
                        _row(300, 3.6, toolhead="HEAD-2", position=1)],
                heads_at_end=[{"toolhead": "HEAD-1", "position": 0, "sid": 200, "sids": [200]},
                              {"toolhead": "HEAD-2", "position": 1, "sid": 300, "sids": [300]}])
    res = run(tmp_path, RESPOND_JS + PREVIEW_JS, {"pending": [rec], "spools": SPOOLS})
    assert res["box"] == "0" and res["preview"] == "→ 900g", res
    assert res["plain"] == "→ 896.4g", res


PANEL_JS = r"""
const notice = () => {
  const n = document.getElementById('fcc-cr-panel-notice');
  return { shown: n.style.display !== 'none', text: n.textContent };
};
cardOf('a').querySelector('.fcc-cr-confirm').click();
await settle(120);
const afterConfirm = notice();
const __base3 = window.__respond;
window.__respond = (url, method, body) => (url.startsWith('/api/cancel_deduct/dismiss')
    ? { body: { status: 'dismissed' } } : __base3(url, method, body));
const btn = cardOf('b').querySelector('.fcc-cr-discard');
btn.click();                              // arms it: a press clears the last outcome
const afterArm = notice();
await settle(750);
btn.click();
await settle(60);
return { afterConfirm, afterArm, afterDiscard: notice(), gone: !cardOf('a') && !cardOf('b') };
"""


def test_an_outcome_is_said_on_the_panel_while_another_card_keeps_it_up(tmp_path):
    """PI1, red on 1c5a85f (the words were only a toast, drawn under the panel, and the
    card that could carry them was gone): Confirm's words go on the panel's own line
    while the next card keeps it up, a press clears them, and a Discard says its own."""
    cards = [_base(j, "partial", total_grams=12.4,
                   spools=[_row(200, 12.4, prefill=0.0, weighed={"words": WORDS_KNOWN, "known_order": True})],
                   heads_at_end=[{"toolhead": "HEAD-1", "position": 0, "sid": 200, "sids": [200]}])
             for j in ("a", "b", "c")]
    confirm = {"status": "confirmed", "applied": [], "errors": [], "shortfall_g": 0.0, "settled_unsure": False,
               "left_weighed": [{"line": "0", "sid": 200, "grams": 12.4, "known_order": True}]}
    res = run(tmp_path, RESPOND_JS + CONFIRM_ANSWER_JS + PANEL_JS,
              {"pending": cards, "spools": SPOOLS, "confirm": confirm})
    assert res["afterConfirm"] == {"shown": True, "text": "Left 12.4g uncharged on #200: it was weighed after the print."}, res
    assert res["afterArm"]["shown"] is False, res
    assert res["afterDiscard"] == {"shown": True, "text": "Review discarded (no deduct)."}, res
    assert res["gone"] is True, res



SETTLE_ROW_JS = r"""
cardOf('s#shortfall').querySelector('.fcc-cr-confirm').click();
await settle(120);
return { posted: posts('/api/cancel_deduct/confirm'),
         notice: ((cardOf('s#shortfall') || document).querySelector('.fcc-cr-card-notice') || {}).textContent || '' };
"""


def test_a_held_pick_left_at_0g_on_an_uncharged_grams_card_settles(tmp_path):
    """FX6, red on c1ee3e0 ("Pick the spool that took these grams (or Discard)", and
    nothing sent). The card an earlier Apply kept holds #300 as a row marked weighed,
    0 g filled in: Apply sends settle_held."""
    rec = _base("s#shortfall", "shortfall", rev=1, total_grams=12.4, unresolved_usage={},
                spools=[_row(300, 12.4, toolhead="HEAD-2", position=1, prefill=0.0,
                             weighed={"words": WORDS_KNOWN, "known_order": True})],
                heads_at_end=[{"toolhead": "HEAD-2", "position": 1, "sid": 300, "sids": [300]}])
    res = run(tmp_path, RESPOND_JS + SETTLE_ROW_JS, {"pending": [rec], "spools": SPOOLS})
    assert res["posted"] == [{"printer_name": "TESTER", "job_id": "s#shortfall", "settle_held": True,
                              "charges": [], "rev": 1}], res



# --------------------------------------------------------------------------- #
# Group 64 fix review 2 (2026-11-22): CX4, CP2 / CX3, CP4, CP7, CP3, CS4 (page) #
# --------------------------------------------------------------------------- #

WORDS_BACK = ("#42 left HEAD-1 at a swap (at 14:00) and was weighed on the Quick-Weigh at 14:02, before it "
              "went back on (at 14:20): the scale already counted its 40.00 g before that swap, so only the "
              "24.28 g it printed after going back on is filled in")
NOTE_JS = r"""
const c = cardOf('b');
const n = c.querySelector('.fcc-cr-weighed');
return { note: n.textContent.replace(/\s+/g, ' ').trim(), box: c.querySelector('.fcc-cr-grams').value,
         preview: c.querySelector('.fcc-cr-preview').textContent.replace(/\s+/g, ' ').trim() };
"""


def test_a_spool_weighed_while_off_its_head_says_what_is_filled_in(tmp_path):
    """CX4, red on d0d51d7 ("Weighed after this print ended: 0 g filled in ... Charging
    these grams would count the print twice" beside a box holding 24.28): FX5's mark has
    its own words."""
    rec = _base("b", "partial", total_grams=64.28,
                spools=[_row(42, 64.28, prefill=24.28,
                             weighed={"words": WORDS_BACK, "known_order": True, "left": True, "back": True})],
                heads_at_end=[{"toolhead": "HEAD-1", "position": 0, "sid": 42, "sids": [42]}])
    res = run(tmp_path, RESPOND_JS + NOTE_JS, {"pending": [rec], "spools": SPOOLS})
    assert res["box"] == "24.28", res
    assert res["note"].startswith("⚠️ Weighed while off its head: only its stretch after going back on is filled in"), res
    assert "0 g filled in" not in res["note"] and "count the print twice" not in res["note"], res
    assert res["note"].endswith("type 0 only if it was weighed again after this print."), res
    assert res["preview"] == "→ 875.7g", res


def _held_row_card(job, with_line):
    words_300 = ("#300 on HEAD-2 was weighed on the Quick-Weigh at 14:05, after this print ended (at 13:50), "
                 "so the scale already counted its 12.40 g")
    extra = {"unresolved_usage": {"1": 3.6}, "shortfall_causes": {"1": {"why": "no_spool", "toolhead": "HEAD-2"}},
             "total_grams": 16.0} if with_line else {"unresolved_usage": {}, "total_grams": 12.4}
    return _base(job, "shortfall", rev=1,
                 spools=[_row(300, 12.4, toolhead="HEAD-2", position=0, prefill=0.0,
                              weighed={"words": words_300, "known_order": True})],
                 heads_at_end=[{"toolhead": "HEAD-2", "position": 1, "sid": 300, "sids": [300]}], **extra)


ROWHEAD_JS = r"""
const out = {};
for (const j of ['r1#shortfall', 'r2#shortfall']) {
  const c = cardOf(j);
  out[j] = { title: c.querySelector('.fcc-cr-short-title').textContent.replace(/\s+/g, ' ').trim(),
             banner: c.querySelector('.fcc-cr-short-banner').textContent.replace(/\s+/g, ' ').trim() };
}
return out;
"""


def test_a_card_kept_with_a_held_pick_row_says_it_is_held(tmp_path):
    """CP2 / CX3, red on d0d51d7 ("12.4g went to no spool" and the joined-spool banner
    over a row FCC held on purpose): a held row counts with the held lines; beside a
    line with no spool the two are counted apart."""
    res = run(tmp_path, RESPOND_JS + ROWHEAD_JS,
              {"pending": [_held_row_card("r1#shortfall", False), _held_row_card("r2#shortfall", True)],
               "spools": SPOOLS})
    assert res["r1#shortfall"]["title"] == "⚖️ TESTER — 12.4g held: #300 was weighed after this print", res
    assert "joined spool" not in res["r1#shortfall"]["banner"], res
    assert res["r2#shortfall"]["title"] == "⚖️ TESTER — 3.6g went to no spool; 12.4g held", res
    assert "The 12.4g on #300 is held, not charged" in res["r2#shortfall"]["banner"], res


RETRY_JS = r"""
const c = cardOf('t');
const row = c.querySelector('.fcc-cr-row[data-sid="200"]');
return { box: row.querySelector('.fcc-cr-grams').value, weighed: row.getAttribute('data-weighed'),
         note: !!row.querySelector('.fcc-cr-weighed') };
"""


def test_a_retry_row_is_drawn_from_its_own_grams_never_as_a_hold(tmp_path):
    """CP4 (page), red on d0d51d7 (0 g and the hold's note on a charge the person chose,
    whose write failed): a 43.6 retry row, even one still carrying a mark, is drawn
    from its grams."""
    rec = _base("t", "partial", total_grams=5.0,
                spools=[_row(200, 5.0, prefill=0.0, weighed={"words": WORDS_KNOWN, "known_order": True},
                             attempt_used_before=130.0, attempt_used_after=135.0)],
                heads_at_end=[{"toolhead": "HEAD-1", "position": 0, "sid": 200, "sids": [200]}])
    res = run(tmp_path, RESPOND_JS + RETRY_JS, {"pending": [rec], "spools": SPOOLS})
    assert res == {"box": "5", "weighed": None, "note": False}, res


PARTFAIL_JS = r"""
let rec = JSON.parse(JSON.stringify(D.pending[0]));
const other = JSON.parse(JSON.stringify(D.pending[1]));
const __base4 = window.__respond;
window.__respond = (url, method, body) => {
  if (url.startsWith('/api/cancel_deduct/pending')) return { body: { pending: [rec, other] } };
  if (url.startsWith('/api/cancel_deduct/confirm')) {
    rec = Object.assign({}, rec, { spools: [Object.assign({}, rec.spools[0], {
      attempt_used_before: 100.0, attempt_used_after: 112.4 })] });
    return { body: { status: 'confirmed', applied: [{ sid: 300, grams: 3.6, remaining: 896.4 }],
                     errors: [{ sid: 200, error: 'HTTP 500: database is locked' }] } };
  }
  return __base4(url, method, body);
};
cardOf('h').querySelector('.fcc-cr-confirm').click();
await settle(150);
const c = cardOf('h');
return { kept: !!c, rows: c ? Array.from(c.querySelectorAll('.fcc-cr-row')).map((r) => r.dataset.sid) : [],
         notice: c ? ((c.querySelector('.fcc-cr-card-notice') || {}).textContent || '') : '',
         panel: document.getElementById('fcc-cr-panel-notice').style.display !== 'none' };
"""


def test_a_partly_failed_apply_keeps_its_retry_card_on_the_panel(tmp_path):
    """CP7, red on d0d51d7 (the card taken off the panel while the server kept it for a
    retry): a charge beside a write that failed redraws the card, both outcomes on it."""
    h = _base("h", "partial", total_grams=16.0,
              spools=[_row(200, 12.4), _row(300, 3.6, toolhead="HEAD-2", position=1)],
              heads_at_end=[{"toolhead": "HEAD-1", "position": 0, "sid": 200, "sids": [200]},
                            {"toolhead": "HEAD-2", "position": 1, "sid": 300, "sids": [300]}])
    o = _base("o", "partial", total_grams=3.6, spools=[_row(300, 3.6, toolhead="HEAD-2", position=1)],
              heads_at_end=[{"toolhead": "HEAD-2", "position": 1, "sid": 300, "sids": [300]}])
    res = run(tmp_path, RESPOND_JS + PARTFAIL_JS, {"pending": [h, o], "spools": SPOOLS})
    assert res["kept"] is True and res["rows"] == ["200"], res
    words = " ".join(res["notice"].split())
    # Group 64 fix review 3 (TP2): each spool's own words, never one sentence for all.
    assert words == ("Deducted from 1 spool(s). Not charged: #200 (HTTP 500: database is locked). The card "
                     "stays: check it, then Apply again or Discard."), res
    assert res["panel"] is False, res


HANDLED_JS = r"""
cardOf('a').querySelector('.fcc-cr-confirm').click();
await settle(120);
const n = document.getElementById('fcc-cr-panel-notice');
return { gone: !cardOf('a'), shown: n.style.display !== 'none', text: n.textContent };
"""


def test_confirms_already_handled_is_said_on_the_panel(tmp_path):
    """CP3, red on d0d51d7 (only a toast, under the panel): another card keeps the panel
    up, so the words go on its line, as a Discard's do."""
    cards = [_base(j, "partial", total_grams=3.6, spools=[_row(300, 3.6, toolhead="HEAD-2", position=1)],
                   heads_at_end=[{"toolhead": "HEAD-2", "position": 1, "sid": 300, "sids": [300]}])
             for j in ("a", "b")]
    res = run(tmp_path, RESPOND_JS + CONFIRM_ANSWER_JS + HANDLED_JS,
              {"pending": cards, "spools": SPOOLS, "confirm": {"status": "already_handled"}})
    assert res == {"gone": True, "shown": True, "text": "Already handled elsewhere."}, res


ONCE_JS = r"""
cardOf('k').querySelector('.fcc-cr-confirm').click();
await settle(120);
return { toasts: __rec.toasts };
"""


def test_a_held_rows_grams_left_at_0g_are_never_also_couldnt_be_applied(tmp_path):
    """CS4 (page), red on d0d51d7 ("Left 12.4g uncharged on #200" and then "12.4g
    couldn't be applied — weigh that spool to true up"): the grams the answer names as
    left uncharged are taken off the shortfall the page warns about."""
    rec = _base("k", "partial", rev=1, total_grams=12.4,
                spools=[_row(200, 12.4, prefill=0.0, weighed={"words": WORDS_KNOWN, "known_order": True})],
                heads_at_end=[{"toolhead": "HEAD-1", "position": 0, "sid": 200, "sids": [200]}])
    confirm = {"status": "confirmed", "applied": [], "errors": [], "shortfall_g": 12.4, "settled_unsure": False,
               "left_weighed": [{"line": "0", "sid": 200, "grams": 12.4, "known_order": True}],
               "left_in_shortfall_g": 12.4}
    res = run(tmp_path, RESPOND_JS + CONFIRM_ANSWER_JS + ONCE_JS, {"pending": [rec], "spools": SPOOLS, "confirm": confirm})
    msgs = [t["msg"] for t in res["toasts"]]
    assert msgs == ["Left 12.4g uncharged on #200: it was weighed after the print."], msgs



# --------------------------------------------------------------------------- #
# Group 64 fix review 3 (2026-11-22): TP1, TP3, TP4, TP6, TP7, TP8 (page)      #
# --------------------------------------------------------------------------- #

def test_a_first_applys_unpicked_head_is_said_beside_a_weighed_row_left_at_0g(tmp_path):
    """TP1, red on a5857f84 (no "couldn't be applied" toast: the page took #200's 12.4 g
    off a shortfall of 8.96 g that never counted them): the server says what of the
    shortfall the weighed spools account for (here none)."""
    rec = _base("f", "partial", total_grams=21.36,
                spools=[_row(200, 12.4, prefill=0.0, weighed={"words": WORDS_KNOWN, "known_order": True})],
                unresolved_usage={"2": 8.96},
                heads_at_end=[{"toolhead": "HEAD-1", "position": 0, "sid": 200, "sids": [200]}])
    confirm = {"status": "confirmed", "applied": [], "errors": [], "shortfall_g": 8.96, "settled_unsure": False,
               "left_weighed": [{"line": "0", "sid": 200, "grams": 12.4, "known_order": True}],
               "left_in_shortfall_g": 0.0}
    res = run(tmp_path, RESPOND_JS + CONFIRM_ANSWER_JS + ONCE_JS.replace("cardOf('k')", "cardOf('f')"),
              {"pending": [rec], "spools": SPOOLS, "confirm": confirm})
    msgs = [t["msg"] for t in res["toasts"]]
    assert msgs == ["Left 12.4g uncharged on #200: it was weighed after the print.",
                    "8.96g couldn't be applied — weigh that spool to true up."], msgs


def test_the_new_cards_toast_says_the_new_cards_own_grams(tmp_path):
    """TP8 (page), red on a5857f84 ("12.12g ... on a new card" for a 2.6 g card)."""
    rec = _base("n", "partial", rev=1, total_grams=13.12,
                spools=[_row(200, 12.4, prefill=0.0, weighed={"words": WORDS_KNOWN, "known_order": True})],
                heads_at_end=[{"toolhead": "HEAD-1", "position": 0, "sid": 200, "sids": [200]}])
    confirm = {"status": "confirmed", "applied": [{"sid": 300, "grams": 1.0, "remaining": 0.0}], "errors": [],
               "shortfall_g": 15.0, "shortfall_card": "n#shortfall", "shortfall_card_g": 2.6, "settled_unsure": False,
               "left_weighed": [{"line": "0", "sid": 200, "grams": 12.4, "known_order": True}],
               "left_in_shortfall_g": 12.4}
    res = run(tmp_path, RESPOND_JS + CONFIRM_ANSWER_JS + ONCE_JS.replace("cardOf('k')", "cardOf('n')"),
              {"pending": [rec], "spools": SPOOLS, "confirm": confirm})
    new = [t["msg"] for t in res["toasts"] if "new card" in t["msg"]]
    assert new == ["2.6g couldn't be charged to the spool picked — they're on a new card: pick another spool, or Discard."], res


def _shortfall_with_rows(job, rows, total, lines=None, causes=None):
    return _base(job, "shortfall", rev=1, total_grams=total, unresolved_usage=lines or {},
                 shortfall_causes=causes or {}, spools=rows,
                 heads_at_end=[{"toolhead": "HEAD-1", "position": 0, "sid": 200, "sids": [200]},
                               {"toolhead": "HEAD-2", "position": 1, "sid": None, "sids": []}])


TITLES_JS = r"""
const out = {};
for (const c of document.querySelectorAll('.fcc-cr-card')) {
  out[c.dataset.job] = { title: c.querySelector('.fcc-cr-short-title').textContent.replace(/\s+/g, ' ').trim(),
                         banner: c.querySelector('.fcc-cr-short-banner').textContent.replace(/\s+/g, ' ').trim() };
}
return out;
"""


def test_the_card_head_names_one_spool_once_and_a_retry_row_apart(tmp_path):
    """TP3, red on a5857f84 ("16g held: #200 and #200 were weighed"), and TP4 (older: a
    failed write's retry row read "5g went to no spool" with the joined-spool banner)."""
    words_200 = WORDS_KNOWN
    dup = _shortfall_with_rows(
        "d#shortfall", [_row(200, 3.6, toolhead="HEAD-2", position=1, prefill=0.0,
                             weighed={"words": words_200, "known_order": True})], 16.0,
        lines={"0": 12.4}, causes={"0": {"why": "weighed", "sid": 200, "toolhead": "HEAD-1", "archived": False,
                                         "known_order": True, "words": words_200}})
    retry = _shortfall_with_rows(
        "r#shortfall", [_row(300, 12.4, toolhead="HEAD-2", position=1, prefill=0.0,
                             weighed={"words": WORDS_KNOWN.replace("#200", "#300"), "known_order": True}),
                        _row(200, 5.0, attempt_used_before=100.0, attempt_used_after=105.0)], 17.4)
    res = run(tmp_path, RESPOND_JS + TITLES_JS, {"pending": [dup, retry], "spools": SPOOLS})
    assert res["d#shortfall"]["title"] == "⚖️ TESTER — 16g held: #200 was weighed after this print", res
    assert res["r#shortfall"]["title"] == "⚖️ TESTER — 12.4g held; 5g to retry on #200", res
    assert "joined spool" not in res["r#shortfall"]["banner"], res
    # Fix review 4 (UP6): a write FCC couldn't confirm, worded for one spool.
    assert ("The 5g picked for #200 couldn't be confirmed as written (Spoolman didn't take the write, or "
            "didn't answer): Apply tries again, and FCC first checks whether it landed.") in res["r#shortfall"]["banner"], res


NULLREAD_JS = r"""
let confirmed = false;
const __b5 = window.__respond;
window.__respond = (url, method, body) => {
  if (url.startsWith('/api/cancel_deduct/pending') && confirmed) return { status: 500, body: {} };
  if (url.startsWith('/api/cancel_deduct/confirm')) {
    confirmed = true;
    return { body: { status: 'confirmed', applied: [{ sid: 300, grams: 3.6, remaining: 896.4 }],
                     errors: [{ sid: 200, error: 'HTTP 500: database is locked' }] } };
  }
  return __b5(url, method, body);
};
cardOf('h').querySelector('.fcc-cr-confirm').click();
await settle(150);
const c = cardOf('h');
return { kept: !!c, enabled: c ? !c.querySelector('.fcc-cr-confirm').disabled : null,
         notice: c ? ((c.querySelector('.fcc-cr-card-notice') || {}).textContent || '') : '' };
"""


def test_a_card_whose_list_couldnt_be_read_after_a_partly_failed_apply_stays(tmp_path):
    """TP6, red on a5857f84 (the card taken off the panel, its words nowhere, while the
    server held it): a failed read of the list is no card gone."""
    h = _base("h", "partial", total_grams=16.0,
              spools=[_row(200, 12.4), _row(300, 3.6, toolhead="HEAD-2", position=1)],
              heads_at_end=[{"toolhead": "HEAD-1", "position": 0, "sid": 200, "sids": [200]},
                            {"toolhead": "HEAD-2", "position": 1, "sid": 300, "sids": [300]}])
    o = _base("o", "partial", total_grams=3.6, spools=[_row(300, 3.6, toolhead="HEAD-2", position=1)],
              heads_at_end=[{"toolhead": "HEAD-2", "position": 1, "sid": 300, "sids": [300]}])
    res = run(tmp_path, RESPOND_JS + NULLREAD_JS, {"pending": [h, o], "spools": SPOOLS})
    assert res["kept"] is True and res["enabled"] is True, res
    assert "Not charged: #200 (HTTP 500: database is locked)" in " ".join(res["notice"].split()), res


ZERO_JS = r"""
const __b6 = window.__respond;
window.__respond = (url, method, body) => (url.startsWith('/api/cancel_deduct/confirm')
  ? { body: { status: 'confirmed',
              applied: [{ sid: 300, grams: 3.6, remaining: 896.4 }, { sid: 301, grams: 0.0, remaining: 0.0 }],
              errors: [{ sid: 200, error: 'held' }],
              held: [{ sid: 200, words: D.words, known_order: true }] } }
  : __b6(url, method, body));
cardOf('z').querySelector('.fcc-cr-confirm').click();
await settle(150);
return { toasts: __rec.toasts.map((t) => t.msg) };
"""


def test_a_spool_that_took_0g_is_never_named_as_charged(tmp_path):
    """TP7, red on a5857f84 ("Charged 3.6g to #300 and #301.")."""
    z = _base("z", "partial", total_grams=21.0,
              spools=[_row(200, 12.4), _row(300, 3.6, toolhead="HEAD-2", position=1),
                      _row(301, 5.0, toolhead="HEAD-3", position=2)],
              heads_at_end=[{"toolhead": "HEAD-1", "position": 0, "sid": 200, "sids": [200]},
                            {"toolhead": "HEAD-2", "position": 1, "sid": 300, "sids": [300]},
                            {"toolhead": "HEAD-3", "position": 2, "sid": 301, "sids": [301]}])
    res = run(tmp_path, RESPOND_JS + ZERO_JS, {"pending": [z], "spools": SPOOLS, "words": WORDS_KNOWN})
    assert res["toasts"][0].startswith(
        "Charged 3.6g to #300. #301's record was at 0 g, so nothing was charged to it. #200 on HEAD-1"), res



# --------------------------------------------------------------------------- #
# Group 64 fix review 4 (2026-11-23): UP1, UP2, UP3, UP6, UP7, US1 (page)       #
# --------------------------------------------------------------------------- #

STALE_WORDS = ("FCC couldn't read the review list just now, so this card may be out of date: Apply reads "
               "it again first, or close 🛑 Review and open it again.")
REFUSED = {"sid": 200, "error": 'HTTP 500: {"message": "database is locked"}',
           "words": "Spoolman refused it: database is locked"}


def _two_rows(job):
    return _base(job, "partial", total_grams=16.0,
                 spools=[_row(200, 12.4), _row(300, 3.6, toolhead="HEAD-2", position=1)],
                 heads_at_end=[{"toolhead": "HEAD-1", "position": 0, "sid": 200, "sids": [200]},
                               {"toolhead": "HEAD-2", "position": 1, "sid": 300, "sids": [300]}])


ANSWER_JS = r"""
let rec = JSON.parse(JSON.stringify(D.pending[0]));
let confirmed = false;
window.__readFails = !!D.readFails;
const __b9 = window.__respond;
window.__respond = (url, method, body) => {
  if (url.startsWith('/api/cancel_deduct/pending')) {
    if (confirmed && window.__readFails) return { status: 500, body: {} };
    return { body: { pending: [rec] } };
  }
  if (url.startsWith('/api/cancel_deduct/confirm')) {
    confirmed = true;
    if (D.retryRow) rec = Object.assign({}, rec, { spools: [Object.assign({}, rec.spools[0], {
      attempt_used_before: 100.0, attempt_used_after: 112.4 })] });
    return { body: D.confirm };
  }
  return __b9(url, method, body);
};
const noticeOf = (c) => c ? ((c.querySelector('.fcc-cr-card-notice') || {}).textContent || '').replace(/\s+/g, ' ').trim() : null;
const rowsOf = (c) => c ? Array.from(c.querySelectorAll('.fcc-cr-row')).map((r) => r.dataset.sid) : null;
"""

PRESS_JS = r"""
cardOf('h').querySelector('.fcc-cr-confirm').click();
await settle(150);
return { notice: noticeOf(cardOf('h')), rows: rowsOf(cardOf('h')), toasts: __rec.toasts.map((t) => [t.type, t.msg]) };
"""


def test_a_refused_write_is_said_in_words_never_spoolmans_raw_answer(tmp_path):
    """UP1, red on 5af23516 ('Not charged: #200 (HTTP 500: {"message": "database is
    locked"})' on the card and in the toast, or requests' text with Spoolman's address):
    the server's words, beside a charge and with nothing charged alike."""
    beside = {"status": "confirmed", "applied": [{"sid": 300, "grams": 3.6, "remaining": 896.4}], "errors": [REFUSED]}
    res = run(tmp_path, RESPOND_JS + ANSWER_JS + PRESS_JS,
              {"pending": [_two_rows("h")], "spools": SPOOLS, "confirm": beside, "retryRow": True})
    assert res["notice"] == ("Deducted from 1 spool(s). Not charged: #200 (Spoolman refused it: database is locked). "
                             "The card stays: check it, then Apply again or Discard."), res
    alone = {"status": "error", "applied": [], "errors": [REFUSED]}
    sub = tmp_path / "alone"
    sub.mkdir()
    res2 = run(sub, RESPOND_JS + ANSWER_JS + PRESS_JS, {"pending": [_two_rows("h")], "spools": SPOOLS, "confirm": alone})
    assert res2["notice"] == "Spoolman refused it: database is locked", res2
    for r in (res, res2):
        assert not [m for _t, m in r["toasts"] if "HTTP 500" in m or "{" in m], r["toasts"]


STALE_PRESSES_JS = r"""
cardOf('h').querySelector('.fcc-cr-confirm').click();
await settle(150);
const first = { notice: noticeOf(cardOf('h')), rows: rowsOf(cardOf('h')) };
cardOf('h').querySelector('.fcc-cr-confirm').click();
await settle(150);
const second = { notice: noticeOf(cardOf('h')), posts: posts('/api/cancel_deduct/confirm').length,
                 enabled: !cardOf('h').querySelector('.fcc-cr-confirm').disabled };
window.__readFails = false;
cardOf('h').querySelector('.fcc-cr-confirm').click();
await settle(150);
return { first, second, third: { notice: noticeOf(cardOf('h')), rows: rowsOf(cardOf('h')),
                                 posts: posts('/api/cancel_deduct/confirm').length },
         toasts: __rec.toasts.map((t) => [t.type, t.msg]) };
"""


def test_a_card_kept_as_drawn_after_a_failed_read_says_so_and_reads_again_before_posting(tmp_path):
    """UP2, red on 5af23516 (the card kept as drawn said nothing of it, and its next Apply
    posted #300 again, which the first Apply had charged: "1 spool(s) failed"). After a
    partly failed Apply the list can't be read: the card says it may be out of date; its
    next Apply reads the list again first and posts nothing, still unread or drawn again."""
    beside = {"status": "confirmed", "applied": [{"sid": 300, "grams": 3.6, "remaining": 896.4}], "errors": [REFUSED]}
    res = run(tmp_path, RESPOND_JS + ANSWER_JS + STALE_PRESSES_JS,
              {"pending": [_two_rows("h")], "spools": SPOOLS, "confirm": beside, "retryRow": True, "readFails": True})
    assert res["first"]["rows"] == ["200", "300"], res
    assert res["first"]["notice"] == ("Deducted from 1 spool(s). Not charged: #200 (Spoolman refused it: database "
                                      "is locked). The card stays: check it, then Apply again or Discard. "
                                      + STALE_WORDS), res
    assert res["second"] == {"notice": STALE_WORDS, "posts": 1, "enabled": True}, res
    assert ["warning", STALE_WORDS] in res["toasts"], res["toasts"]
    assert res["third"] == {"notice": "Drawn again as FCC holds this card now: check it, then Apply.",
                            "rows": ["200"], "posts": 1}, res


def test_a_spool_no_longer_on_the_card_is_no_failure(tmp_path):
    """UP2's other half, red on 5af23516 ("1 spool(s) failed — check the log." for a spool
    an earlier Apply had charged): said as no longer on the card, nothing more charged."""
    gone = {"status": "confirmed", "applied": [{"sid": 200, "grams": 12.4, "remaining": 887.6}],
            "errors": [{"sid": 300, "error": "not in this review"}]}
    res = run(tmp_path, RESPOND_JS + ANSWER_JS + PRESS_JS, {"pending": [_two_rows("h")], "spools": SPOOLS, "confirm": gone})
    assert res["toasts"] == [["success", "Deducted from 1 spool(s)."],
                             ["info", "#300 was no longer on this card (an earlier Apply settled it): nothing more "
                                      "was charged to it."]], res["toasts"]


def test_an_unpicked_heads_grams_are_said_beside_a_new_card_too(tmp_path):
    """UP3, red on 5af23516 (only the new card's 2.6 g were said; XL-3's 8.96 g, a head
    nobody picked, appeared nowhere on the page). An older FCC's answer, with no
    shortfall_card_g, says only the card's figure, as before."""
    confirm = {"status": "confirmed", "errors": [], "shortfall_g": 11.56, "shortfall_card": "h#shortfall",
               "shortfall_card_g": 2.6, "applied": [{"sid": 200, "grams": 12.4, "remaining": 887.6},
                                                    {"sid": 300, "grams": 1.0, "remaining": 0.0}]}
    res = run(tmp_path, RESPOND_JS + ANSWER_JS + PRESS_JS, {"pending": [_two_rows("h")], "spools": SPOOLS, "confirm": confirm})
    assert [m for _t, m in res["toasts"]] == [
        "Deducted from 2 spool(s).",
        "2.6g couldn't be charged to the spool picked — they're on a new card: pick another spool, or Discard.",
        "8.96g couldn't be applied — weigh that spool to true up."], res["toasts"]
    older = dict(confirm)
    del older["shortfall_card_g"]
    sub = tmp_path / "older"
    sub.mkdir()
    res2 = run(sub, RESPOND_JS + ANSWER_JS + PRESS_JS, {"pending": [_two_rows("h")], "spools": SPOOLS, "confirm": older})
    assert [m for _t, m in res2["toasts"]] == [
        "Deducted from 2 spool(s).",
        "11.56g couldn't be charged to the spool picked — they're on a new card: pick another spool, or Discard."], res2


def test_weighed_spools_settled_beside_a_failed_write_are_named(tmp_path):
    """US1 (page), red on 5af23516 (the server kept the row on the retry card; an Apply that
    settles it beside a failed write now names it, and the page says so whatever else the
    answer says)."""
    confirm = {"status": "error", "applied": [],
               "errors": [{"sid": 300, "error": "Max retries exceeded (test)", "words": "FCC couldn't reach Spoolman."}],
               "left_weighed": [{"line": "0", "sid": 200, "grams": 12.4, "known_order": False}], "settled_unsure": True}
    res = run(tmp_path, RESPOND_JS + ANSWER_JS + PRESS_JS, {"pending": [_two_rows("h")], "spools": SPOOLS, "confirm": confirm})
    words = "FCC couldn't reach Spoolman. Left 12.4g uncharged on #200 as set: its weight changed after the print."
    assert res["notice"] == words and ["error", words] in res["toasts"], res


def test_several_retry_rows_are_worded_for_several_writes(tmp_path):
    """UP6, red on 5af23516 ("The 9g picked for #200 and #300 weren't written (Spoolman
    didn't take the write) ... whether it landed"): several writes, and none of them
    known not to have landed."""
    card = _shortfall_with_rows(
        "r#shortfall", [_row(200, 5.0, attempt_used_before=100.0, attempt_used_after=105.0),
                        _row(300, 4.0, toolhead="HEAD-2", position=1, attempt_used_before=50.0,
                             attempt_used_after=54.0)], 9.0)
    res = run(tmp_path, RESPOND_JS + TITLES_JS, {"pending": [card], "spools": SPOOLS})
    assert ("The 9g picked for #200 and #300 couldn't be confirmed as written (Spoolman didn't take their "
            "writes, or didn't answer): Apply tries again, and FCC first checks whether each landed.") \
        in res["r#shortfall"]["banner"], res


FAILED_READ_JS = r"""
const D = __DATA__;
let mode = 'ok';
window.__respond = (url) => {
  if (url.startsWith('/api/cancel_deduct/pending')) {
    if (mode === 'ok') return { body: { pending: D.pending } };
    if (mode === '500') return { status: 500, body: {} };
    return { fail: true };
  }
  return { body: {} };
};
const badge = document.createElement('span');
badge.id = 'cancel-review-badge'; badge.style.display = 'none'; badge.setAttribute('title', 'Reviews waiting');
document.body.appendChild(badge);
const look = () => ({ text: badge.textContent, shown: badge.style.display !== 'none',
                      read: badge.dataset.read || null, title: badge.getAttribute('title') });
await window.refreshCancelReviewBadge(); await settle(20);
const good = look();
mode = '500';
await window.refreshCancelReviewBadge(); await settle(20);
const failed = look();
mode = 'net';
await window.openCancelReview(); await settle(40);
const opened = !!document.getElementById('fcc-cr-body');
mode = 'ok';
await window.refreshCancelReviewBadge(); await settle(20);
return { good, failed, opened, back: look(), toasts: __rec.toasts.map((t) => [t.type, t.msg]) };
"""


def test_a_review_list_fcc_couldnt_read_is_never_no_reviews(tmp_path):
    """UP7, red on 5af23516 (a failed read hid the 🛑 pill and every printer's count, and
    🛑 Review said "No pending cancel reviews."): the counts stay, the pill's tooltip says
    why, and the review says it couldn't read the list."""
    recs = [_base(j, "partial", total_grams=3.6, spools=[_row(300, 3.6, toolhead="HEAD-2", position=1)],
                  heads_at_end=[{"toolhead": "HEAD-2", "position": 1, "sid": 300, "sids": [300]}]) for j in ("1", "2")]
    res = run(tmp_path, FAILED_READ_JS, {"pending": recs})
    assert res["good"] == {"text": "🛑 2 reviews", "shown": True, "read": None, "title": "Reviews waiting"}, res
    assert res["failed"]["text"] == "🛑 2 reviews" and res["failed"]["shown"] is True, res
    assert res["failed"]["read"] == "failed" and "couldn't read the review list just now" in res["failed"]["title"], res
    assert res["opened"] is False, res
    assert res["toasts"] == [["warning", "FCC couldn't read the review list just now, so it can't be shown. "
                                         "Try again in a moment."]], res["toasts"]
    assert res["back"] == res["good"], res
