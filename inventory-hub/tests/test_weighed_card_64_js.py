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
    assert res["posted"] == [{"printer_name": "TESTER", "job_id": "r", "updates": {}}], res["posted"]
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
