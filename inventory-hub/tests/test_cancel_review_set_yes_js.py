"""The 🛑 Review card's set check stands out while it waits for its second press
(hotfix round 2, R1; Derek's picture check, 2026-11-12).

Derek: "make it a little more apparent that the text changed ... the confirm
looks exactly the same, I'm sure someone could misread it. So a color change to
bring more attention to both of them would probably be a good idea. And maybe a
button text change to yes-confirm or something to that effect. Just so the user
is made aware that they are about to not perform a deduct."

Runs the REAL overlay_mount.js and cancel_review.js under node's `vm` (the
driver in test_cancel_review_picker_scan_js.py: events, focus, values; no
browser, no container). Pinned:

  - the first press over a held set whose boxes don't add up says so in the set,
    in an orange box with a ⚠️ (role=alert, a named size): an orange edge, a
    dark orange ground and light words, unlike the amber note above it and the
    card's amber banner;
  - while that press waits for a second one, the card's button is orange with
    dark words and says what the second press does, the same on every card,
    whatever the button's own words ("Confirm deduct", "Apply to the picked
    spool(s)"): "⚠️ Yes, leave 84.28 g uncharged" when every set is short (the
    grams not placed, added up), "⚠️ Yes, charge 84.28 g more" when every set is
    over (the grams over, added up), "⚠️ Yes, go ahead as typed" for a mix;
  - neither the set's words nor the line by the buttons (two sets or more) tell
    the person to press the button's old words: they say what the orange
    ⚠️ Yes does;
  - the button goes back to its own words, classes and colour, and the sets'
    words go, when a set's box changes, when the second press goes out (whatever
    the answer) and when the card is drawn again; the next press over a set
    that still doesn't add up then asks again, so a green button never goes
    ahead over grams nobody placed with no words up;
  - the keyboard stays on the button, and a double click's second press still
    does nothing;
  - round 2's review: the Yes counts every gram its press leaves uncharged, a
    held line that isn't a set and that the press charges nothing to (no spool
    picked, or no grams) included, and the line by the buttons names those
    heads; a change on such a line ends the wait; a press refused before the set
    check ends it too, so the button never promises a press that can't go
    ahead; and a double click's second press keeps the line by the buttons up.

The browser contrast cases are tests/test_contrast_guard.py's
test_review_card_notices_are_readable, which scores the waiting state as drawn,
and test_review_yes_naming_a_plain_line_is_readable; this file checks the colours
offline.

HEAD proof: run on d8876bd (before R1), every test here fails (the button kept
its green "Confirm deduct" through the wait, the set's words were amber with no
box, and a set's grams changed and put back went ahead on the first ask, with no
words up).
"""
from __future__ import annotations

import colorsys
import re

from test_cancel_review_picker_scan_js import SHORTFALL, _contrast, pytestmark  # noqa: F401  (pytestmark: skip without node)
from test_cancel_review_review_fixes_js import NOSPOOL_SET, PARTIAL_SET, TWO_SETS, _go

# The card's own button, as every card template draws it.
NORMAL_CLASSES = "btn btn-sm btn-success fw-bold fcc-cr-confirm"
CONFIRM = "Confirm deduct"
APPLY = "Apply to the picked spool(s)"
# The card's amber words and banner, which the set's warning must not look like.
AMBER = "#e6c074"
BANNER_BG = "#221d12"
BANNER_EDGE = "#3a2f17"

_HEX = re.compile(r"#(?:[0-9a-fA-F]{6}|[0-9a-fA-F]{3})(?![0-9a-fA-F])")


def _decls(style):
    """A style attribute's declarations, by lower-case name."""
    out = {}
    for part in (style or "").split(";"):
        if ":" in part:
            name, value = part.split(":", 1)
            out[name.strip().lower()] = value.strip()
    return out


def _hex(value):
    m = _HEX.search(value or "")
    if not m:
        return None
    h = m.group(0)[1:].lower()
    return "#" + ("".join(c * 2 for c in h) if len(h) == 3 else h)


def _hsv(hexcol):
    h = hexcol.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    hue, sat, val = colorsys.rgb_to_hsv(r, g, b)
    return hue * 360, sat, val


def _orange(hexcol):
    """A bright orange: not Bootstrap's green, nor the card's amber (#e6c074 is
    40° at half saturation), nor Bootstrap's warning yellow (#ffc107, 45°), nor
    a pale peach."""
    hue, sat, val = _hsv(hexcol)
    return 15 <= hue <= 38 and sat >= 0.65 and val >= 0.85


def _dark_orange(hexcol):
    """A dark ground tinted orange (red over green over blue)."""
    h = hexcol.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    hue, sat, val = _hsv(hexcol)
    return r > g > b and 10 <= hue <= 38 and sat >= 0.6 and val <= 0.3


def _waiting(state):
    cls = (state["cls"] or "").split()
    return "fcc-cr-yes" in cls and "btn-success" not in cls and "fcc-cr-confirm" in cls


def _normal(state, text=CONFIRM):
    return state["text"] == text and state["cls"] == NORMAL_CLASSES and state["style"] is None


# What a scenario reads off a card: its button, and the set words and line on show.
HELPERS_JS = r"""
const stateOf = (btn) => ({ text: btn.textContent, cls: btn.className, style: btn.getAttribute('style'),
                            disabled: !!btn.disabled });
const said = (c) => {
  const n = c.querySelector('.fcc-cr-card-notice');
  return { alerts: c.querySelectorAll('.fcc-cr-set-alert').filter((a) => a.style.display !== 'none')
                    .map((a) => a.textContent),
           notice: n && n.style.display !== 'none' ? n.textContent : null };
};
const fill = (c, line, grams) => {
  const b = c.querySelector(`.fcc-cr-pgrams[data-line="${CSS.escape(line)}"]`);
  b.value = String(grams); fire(b, 'input');
  return b;
};
"""


def _run(tmp_path, body, pending, **data):
    return _go(tmp_path, HELPERS_JS + body, pending, **data)


# --------------------------------------------------------------------------- #
# What the button and the sets say while the check waits                       #
# --------------------------------------------------------------------------- #

CASES = [
    {"job": "ps", "fill": {}},                                                # one set, none placed
    {"job": "pp", "fill": {"set:4:42": 30}},                                  # one set, part placed
    {"job": "po", "fill": {"set:4:42": 84.28, "set:4:229": 84.28}},          # one set, over
    {"job": "ts", "fill": {}},                                                # two sets, both short
    {"job": "tm", "fill": {"set:6:243": 15, "set:6:300": 15}},               # two sets: short and over
    {"job": "to", "fill": {"set:4:42": 50, "set:4:229": 50,
                           "set:6:243": 15, "set:6:300": 15}},               # two sets, both over
    {"job": "nsp", "fill": {"set:4:42": 30}},                                 # a no_spool card ("Apply")
]
PENDING = [PARTIAL_SET, dict(PARTIAL_SET, job_id="pp"), dict(PARTIAL_SET, job_id="po"), TWO_SETS,
           dict(TWO_SETS, job_id="tm"), dict(TWO_SETS, job_id="to"), dict(NOSPOOL_SET, job_id="nsp")]

CASES_JS = r"""
const out = {};
for (const k of D.cases) {
  const c = cardOf(k.job);
  Object.entries(k.fill).forEach(([line, g]) => fill(c, line, g));
  const btn = c.querySelector('.fcc-cr-confirm');
  const before = stateOf(btn);
  btn.focus();
  btn.click();
  await settle(30);
  const alert = c.querySelector('.fcc-cr-set-alert');
  out[k.job] = Object.assign({ before, waiting: stateOf(btn), focused: document.activeElement === btn,
                               alertRole: alert.getAttribute('role'), alertStyle: alert.getAttribute('style') },
                             said(c));
}
return { out, posted: posts('/api/cancel_deduct/confirm').length };
"""

NONE_PLACED = ("⚠️ T4 · HEAD-5: none of its 84.28 g are placed. Type the grams each spool used, or put "
               "them all on one; or press ⚠️ Yes below to leave them uncharged.")
PART_PLACED = "⚠️ T4 · HEAD-5: 54.28 g of its 84.28 g aren't placed. Press ⚠️ Yes below to leave them uncharged."
T6_NONE = ("⚠️ T6 · HEAD-7: none of its 20 g are placed. Type the grams each spool used, or put them all "
           "on one; or press ⚠️ Yes below to leave them uncharged.")
T6_OVER = ("⚠️ T6 · HEAD-7: its spools add up to 30 g, 10 g more than the 20 g FCC computed. Press "
           "⚠️ Yes below to charge the spools as typed.")


def test_the_button_says_what_the_second_press_does(tmp_path):
    # On d8876bd: AssertionError: 'Confirm deduct' == '⚠️ Yes, leave 84.28 g uncharged' (the button
    # looked exactly as before while the first press waited for a second).
    res = _run(tmp_path, CASES_JS, PENDING, cases=CASES)
    out = res["out"]
    assert res["posted"] == 0, res
    want = {"ps": "⚠️ Yes, leave 84.28 g uncharged",
            "pp": "⚠️ Yes, leave 54.28 g uncharged",
            "po": "⚠️ Yes, charge 84.28 g more",
            "ts": "⚠️ Yes, leave 104.28 g uncharged",      # 84.28 + 20, both sets left empty
            "tm": "⚠️ Yes, go ahead as typed",
            "to": "⚠️ Yes, charge 25.72 g more",           # 15.72 + 10
            "nsp": "⚠️ Yes, leave 54.28 g uncharged"}      # the same words on an "Apply" card
    for job, text in want.items():
        o = out[job]
        assert _normal(o["before"], APPLY if job == "nsp" else CONFIRM), (job, o["before"])
        assert o["waiting"]["text"] == text, (job, o["waiting"])
        assert _waiting(o["waiting"]), (job, o["waiting"])
        assert not o["waiting"]["disabled"], (job, o["waiting"])
        # The keyboard stays on the button: its next Enter is the second press.
        assert o["focused"], job


def test_the_sets_words_point_at_the_orange_yes(tmp_path):
    # On d8876bd: AssertionError: the set's words said "press Confirm deduct again to log them as
    # uncharged", while the button would read "⚠️ Yes, ...".
    res = _run(tmp_path, CASES_JS, PENDING, cases=CASES)
    out = res["out"]
    assert out["ps"]["alerts"] == [NONE_PLACED] and out["ps"]["notice"] is None, out["ps"]
    assert out["pp"]["alerts"] == [PART_PLACED] and out["pp"]["notice"] is None, out["pp"]
    assert out["po"]["alerts"] == [
        "⚠️ T4 · HEAD-5: its spools add up to 168.56 g, 84.28 g more than the 84.28 g FCC computed. "
        "Press ⚠️ Yes below to charge the spools as typed."] and out["po"]["notice"] is None, out["po"]
    # Two sets or more: each says its own, and one line by the buttons says what the press does.
    lead = "2 heads' grams don't add up, as each says above. Press ⚠️ Yes below to "
    assert out["ts"]["alerts"] == [NONE_PLACED, T6_NONE], out["ts"]
    assert out["ts"]["notice"] == lead + "leave them uncharged.", out["ts"]
    assert out["tm"]["alerts"] == [NONE_PLACED, T6_OVER], out["tm"]
    assert out["tm"]["notice"] == lead + "go ahead as typed.", out["tm"]
    assert out["to"]["alerts"] == [
        "⚠️ T4 · HEAD-5: its spools add up to 100 g, 15.72 g more than the 84.28 g FCC computed. "
        "Press ⚠️ Yes below to charge the spools as typed.", T6_OVER], out["to"]
    assert out["to"]["notice"] == lead + "charge the spools as typed.", out["to"]
    # An "Apply" card's set says the same: the words never name the button's old words.
    assert out["nsp"]["alerts"] == [PART_PLACED] and out["nsp"]["notice"] is None, out["nsp"]
    for job, o in out.items():
        for words in o["alerts"] + [o["notice"] or ""]:
            assert CONFIRM not in words and "Apply" not in words and "again" not in words, (job, words)


def test_the_waiting_look_is_orange_and_readable(tmp_path):
    # On d8876bd: AssertionError: ('ps', '', None) (the waiting button had no colours of its own,
    # still btn-success's green; the set's words were amber on the card, with no box).
    res = _run(tmp_path, CASES_JS, PENDING, cases=CASES)
    for job, o in res["out"].items():
        # The button: dark words on orange, as Bootstrap's own button colours, so it stays
        # orange when pointed at, pressed or reached by the keyboard.
        btn = _decls(o["waiting"]["style"])
        for state in ("", "hover-", "active-"):
            bg, fg = _hex(btn.get(f"--bs-btn-{state}bg")), _hex(btn.get(f"--bs-btn-{state}color"))
            assert bg and fg and _orange(bg), (job, state, o["waiting"]["style"])
            assert _contrast(fg, bg) >= 4.5, (job, state, fg, bg, _contrast(fg, bg))
            assert _orange(_hex(btn.get(f"--bs-btn-{state}border-color"))), (job, state, btn)
        # The set's words: an orange box with a ⚠️, apart from the amber note above it
        # and the card's amber banner.
        box = _decls(o["alertStyle"])
        assert o["alertRole"] == "alert", job
        ground = _hex(box.get("background-color") or box.get("background"))
        words = _hex(box.get("color"))
        edge = _hex(box.get("border-left") or box.get("border"))
        assert ground and _dark_orange(ground) and ground != BANNER_BG, (job, o["alertStyle"])
        assert edge and _orange(edge) and edge != BANNER_EDGE, (job, o["alertStyle"])
        assert words and words != AMBER and _contrast(words, ground) >= 7, (job, words, ground)
        assert re.search(r"font-size:\s*var\(--fcc-fs-(small|row)\)", o["alertStyle"]), (job, o["alertStyle"])
        assert all(a.startswith("⚠️ ") for a in o["alerts"]), (job, o["alerts"])


# --------------------------------------------------------------------------- #
# It goes back                                                                 #
# --------------------------------------------------------------------------- #

BOX_CHANGE_JS = r"""
const c = cardOf('ps');
const btn = c.querySelector('.fcc-cr-confirm');
btn.click();
await settle(30);
const waiting = stateOf(btn);
// A double click's second press does nothing: the button keeps waiting.
btn.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, detail: 2 }));
await settle(30);
const dbl = stateOf(btn);
// A set's box changes: the button is its own again, and the set's words go.
const box = fill(c, 'set:4:42', 30);
const changed = Object.assign({ btn: stateOf(btn) }, said(c));
// ... and back as they were when the first press asked. A press long after asks
// again: it never goes ahead on the first ask (on d8876bd it went ahead with no
// words up, the button reading "Confirm deduct").
box.value = ''; fire(box, 'input');
const back = stateOf(btn);
await settle(720);
btn.click();
await settle(30);
const again = Object.assign({ btn: stateOf(btn) }, said(c));
// A press with the grams changed asks about the grams as they are now.
fill(c, 'set:4:42', 30);
btn.click();
await settle(30);
const now = Object.assign({ btn: stateOf(btn) }, said(c));
// Two sets: a change in one takes both sets' words and the line by the buttons
// away, since each told the person to press a "⚠️ Yes" that reads its own
// words again.
const t = cardOf('ts');
const tb = t.querySelector('.fcc-cr-confirm');
tb.click();
await settle(30);
const twoAsked = said(t);
fill(t, 'set:6:243', 5);
const twoChanged = Object.assign({ btn: stateOf(tb) }, said(t));
return { waiting, dbl, changed, back, again, now, twoAsked, twoChanged,
         posted: posts('/api/cancel_deduct/confirm').length };
"""


def test_a_box_change_puts_the_button_back_and_the_next_press_asks_again(tmp_path):
    # On d8876bd: AssertionError: assert 1 == 0 (the grams changed and put back, a press went ahead
    # on the first ask with no words up).
    res = _run(tmp_path, BOX_CHANGE_JS, [PARTIAL_SET, TWO_SETS])
    assert res["posted"] == 0, res
    assert res["waiting"]["text"] == "⚠️ Yes, leave 84.28 g uncharged" and _waiting(res["waiting"]), res
    assert res["dbl"] == res["waiting"], res
    ch = res["changed"]
    assert _normal(ch["btn"]) and ch["alerts"] == [] and ch["notice"] is None, ch
    assert _normal(res["back"]), res["back"]
    again = res["again"]
    assert again["btn"]["text"] == "⚠️ Yes, leave 84.28 g uncharged" and _waiting(again["btn"]), again
    assert again["alerts"] == [NONE_PLACED], again
    now = res["now"]
    assert now["btn"]["text"] == "⚠️ Yes, leave 54.28 g uncharged" and now["alerts"] == [PART_PLACED], now
    assert len(res["twoAsked"]["alerts"]) == 2 and res["twoAsked"]["notice"], res["twoAsked"]
    two = res["twoChanged"]
    assert _normal(two["btn"]) and two["alerts"] == [] and two["notice"] is None, two


GOES_OUT_JS = r"""
const c = cardOf('ps');
const btn = c.querySelector('.fcc-cr-confirm');
const old = window.__respond;
let atPost = null;
window.__respond = (url, m, b) => {
  if (url.startsWith('/api/cancel_deduct/confirm')) atPost = Object.assign({ btn: stateOf(btn) }, said(c));
  return old(url, m, b);                      // refused: "stub: nothing applied"
};
btn.click();
await settle(30);
const waiting = stateOf(btn);
await settle(720);
btn.click();                                  // the second press goes out
await settle(60);
const answered = Object.assign({ btn: stateOf(btn) }, said(c));
// The button reads its own words again, so a press asks again before anything goes.
btn.click();
await settle(30);
const next = Object.assign({ btn: stateOf(btn), posted: posts('/api/cancel_deduct/confirm').length }, said(c));
return { waiting, atPost, answered, next };
"""


def test_the_second_press_puts_the_button_back_whatever_the_answer(tmp_path):
    # On d8876bd: AssertionError: assert False, where False = _waiting({... 'text': 'Confirm
    # deduct'}) (the button never said what the second press did).
    res = _run(tmp_path, GOES_OUT_JS, [PARTIAL_SET])
    assert _waiting(res["waiting"]), res["waiting"]
    # As the press goes out: its own words and colour, pressed down, and no set words up.
    at = res["atPost"]
    assert at["btn"]["text"] == CONFIRM and at["btn"]["cls"] == NORMAL_CLASSES and at["btn"]["style"] is None, at
    assert at["btn"]["disabled"] and at["alerts"] == [], at
    # The answer refused it: the card says so, and the button is its own again.
    ans = res["answered"]
    assert _normal(ans["btn"]) and not ans["btn"]["disabled"], ans
    assert ans["notice"] == "stub: nothing applied", ans
    nxt = res["next"]
    assert nxt["posted"] == 1, nxt
    assert nxt["btn"]["text"] == "⚠️ Yes, leave 84.28 g uncharged" and _waiting(nxt["btn"]), nxt
    assert nxt["alerts"] == [NONE_PLACED], nxt


REDRAWN_JS = r"""
let c = cardOf('ps');
let btn = c.querySelector('.fcc-cr-confirm');
btn.click();
await settle(30);
const waiting = stateOf(btn);
// The review is closed while the button waits, and opened again: the card is drawn
// again, its button its own.
key(btn, 'Escape');
await settle(20);
const closed = !document.getElementById('fcc-cancel-review-overlay');
await window.openCancelReview();
await settle(40);
c = cardOf('ps');
btn = c.querySelector('.fcc-cr-confirm');
const reopened = Object.assign({ btn: stateOf(btn) }, said(c));
btn.click();
await settle(30);
const reasked = stateOf(btn);
// An answer that keeps the card draws it again from what the server stored.
const old = window.__respond;
window.__respond = (url, m, b) => url.startsWith('/api/cancel_deduct/confirm')
  ? { body: { status: 'confirmed', kept: true, applied: [{ sid: 243, grams: 75.32 }], shortfall_g: 84.28 } }
  : old(url, m, b);
await settle(720);
btn.click();
await settle(80);
const fresh = cardOf('ps');
const fb = fresh.querySelector('.fcc-cr-confirm');
const redrawn = Object.assign({ same: fresh === c, btn: stateOf(fb) }, said(fresh));
fb.click();
await settle(30);
const freshAsks = Object.assign({ btn: stateOf(fb), posted: posts('/api/cancel_deduct/confirm').length },
                                said(fresh));
return { waiting, closed, reopened, reasked, redrawn, freshAsks };
"""


def test_a_card_drawn_again_has_its_own_button_and_asks_again(tmp_path):
    # On d8876bd: AssertionError: assert (False), where False = _waiting({... 'text': 'Confirm
    # deduct'}) (the waiting button read as it always did).
    res = _run(tmp_path, REDRAWN_JS, [PARTIAL_SET])
    assert _waiting(res["waiting"]) and res["closed"], res
    ro = res["reopened"]
    assert _normal(ro["btn"]) and ro["alerts"] == [] and ro["notice"] is None, ro
    assert res["reasked"]["text"] == "⚠️ Yes, leave 84.28 g uncharged", res["reasked"]
    rd = res["redrawn"]
    assert rd["same"] is False and _normal(rd["btn"]) and rd["alerts"] == [], rd
    assert rd["notice"] == "Charged 75.32g. 84.28g still have no spool — pick another spool, or Discard.", rd
    fa = res["freshAsks"]
    assert fa["posted"] == 1 and fa["btn"]["text"] == "⚠️ Yes, leave 84.28 g uncharged", fa
    assert fa["alerts"] == [NONE_PLACED], fa


# --------------------------------------------------------------------------- #
# Round 2's review (2026-11-12): the Yes names every gram its press leaves     #
# --------------------------------------------------------------------------- #
# A held line that isn't a set and that the press charges nothing to (no spool
# picked, or no grams) is left uncharged too: the server keeps its record's grams
# on the review's `unresolved_usage`, or (no_spool) counts its whole usage, and the
# Activity Log's uncharged line names them. The Yes adds them in, and the line by
# the buttons says which heads they are; a change on such a line ends the wait. A
# press refused before the set check ends the wait too, and a double click's second
# press keeps the line by the buttons up.

_HEAD_1 = {"toolhead": "HEAD-1", "position": 0, "sid": 72, "sids": [72]}
_SET_6 = [{"sid": 243, "when": "start", "display": "#243 Test", "remaining": 300.0},
          {"sid": 300, "when": "end", "display": "#300 Test", "remaining": 900.0}]
# A partial card: T4 a set (84.28 g), T6 a plain held line (20 g).
SET_PLUS_LINE = dict(PARTIAL_SET, job_id="psl", spools=[], unresolved_usage={"4": 84.28, "6": 20.0},
                     total_grams=104.28,
                     unresolved_notes=dict(PARTIAL_SET["unresolved_notes"], **{"6": "HEAD-7 had #243 and #300 "
                                                                                    "when the print ended."}))
# The money review's case: T4 a set, and a plain line on T0 (30 g).
SET_PLUS_T0 = dict(PARTIAL_SET, job_id="st0", unresolved_usage={"0": 30.0, "4": 84.28},
                   heads_at_end=PARTIAL_SET["heads_at_end"] + [_HEAD_1],
                   unresolved_notes=dict(PARTIAL_SET["unresolved_notes"], **{"0": "No spool was loaded on "
                                                                                  "HEAD-1 when the print ended."}))
# A no_spool card: T4 a set, T6 a plain line.
NOSPOOL_PLUS_LINE = dict(NOSPOOL_SET, job_id="nsl", usage_map={"4": 84.28, "6": 20.0}, total_grams=104.28)
# Two sets and a plain line on T0.
TWO_SETS_PLUS_T0 = dict(TWO_SETS, job_id="t2p", unresolved_usage={"0": 30.0, "4": 84.28, "6": 20.0},
                        heads_at_end=TWO_SETS["heads_at_end"] + [_HEAD_1], total_grams=134.28)

PLAIN_CASES = [
    {"job": "psl", "fill": {}, "pick": {}},                                  # T6 left unpicked
    {"job": "pk", "fill": {}, "pick": {"pos:6": "243"}},                     # T6 picked: charged
    {"job": "st0", "fill": {}, "pick": {}},                                  # T0 left unpicked
    {"job": "pov", "fill": {"set:4:42": 84.28, "set:4:229": 84.28}, "pick": {}},  # set over, T6 left
    {"job": "nsl", "fill": {"set:4:42": 30}, "pick": {}},                    # a no_spool card, T6 left
    {"job": "nsg", "fill": {"set:4:42": 30, "6": ""}, "pick": {"6": "243"}},  # T6 picked with no grams
    {"job": "t2p", "fill": {}, "pick": {}},                                  # two sets and T0
]
PLAIN_PENDING = [SET_PLUS_LINE, dict(SET_PLUS_LINE, job_id="pk"), SET_PLUS_T0, dict(SET_PLUS_LINE, job_id="pov"),
                 NOSPOOL_PLUS_LINE, dict(NOSPOOL_PLUS_LINE, job_id="nsg"), TWO_SETS_PLUS_T0]

PLAIN_JS = r"""
const out = {};
for (const k of D.cases) {
  const c = cardOf(k.job);
  Object.entries(k.pick).forEach(([line, sid]) => pickIn(c.querySelector(`.fcc-cr-pick[data-line="${CSS.escape(line)}"]`), sid));
  Object.entries(k.fill).forEach(([line, g]) => fill(c, line, g));
  const btn = c.querySelector('.fcc-cr-confirm');
  btn.click();
  await settle(30);
  out[k.job] = Object.assign({ btn: stateOf(btn) }, said(c));
}
// The second press of the first card's ask goes ahead with T6 unpicked.
await settle(720);
cardOf('psl').querySelector('.fcc-cr-confirm').click();
await settle(40);
return { out, posted: posts('/api/cancel_deduct/confirm') };
"""

T6_LEFT = "⚠️ Yes below charges nothing to T6 · HEAD-7, leaving its 20 g uncharged."
T0_LEFT = "⚠️ Yes below charges nothing to T0 · HEAD-1, leaving its 30 g uncharged."


def test_the_yes_counts_every_plain_line_its_press_leaves_uncharged(tmp_path):
    # On e777bcd: AssertionError: ('psl', '⚠️ Yes, leave 84.28 g uncharged') (T6's 20 g, which the
    # press also leaves uncharged, weren't counted, nor said anywhere on the card)
    res = _run(tmp_path, PLAIN_JS, PLAIN_PENDING, cases=PLAIN_CASES)
    out = res["out"]
    want = {"psl": ("⚠️ Yes, leave 104.28 g uncharged", [NONE_PLACED], T6_LEFT),
            "pk": ("⚠️ Yes, leave 84.28 g uncharged", [NONE_PLACED], None),
            "st0": ("⚠️ Yes, leave 114.28 g uncharged", [NONE_PLACED], T0_LEFT),
            "pov": ("⚠️ Yes, go ahead as typed", None, T6_LEFT),
            "nsl": ("⚠️ Yes, leave 74.28 g uncharged", [PART_PLACED], T6_LEFT),
            "nsg": ("⚠️ Yes, leave 74.28 g uncharged", [PART_PLACED], T6_LEFT),
            "t2p": ("⚠️ Yes, leave 134.28 g uncharged", [NONE_PLACED, T6_NONE],
                    "2 heads' grams don't add up, as each says above. Press ⚠️ Yes below to leave them "
                    "uncharged. " + T0_LEFT)}
    for job, (text, alerts, notice) in want.items():
        o = out[job]
        assert o["btn"]["text"] == text and _waiting(o["btn"]), (job, o)
        if alerts is not None:
            assert o["alerts"] == alerts, (job, o)
        assert o["notice"] == notice, (job, o)
    # The second press goes ahead as asked: nothing for T6, whose grams the server
    # leaves uncharged, as the button said.
    assert res["posted"] == [{"printer_name": "TESTER", "job_id": "psl", "updates": {}}], res["posted"]


PLAIN_CHANGE_JS = r"""
const c = cardOf('psl');
const btn = c.querySelector('.fcc-cr-confirm');
btn.click();
await settle(30);
const asked = stateOf(btn);
// A spool picked for T6: what the press leaves changed, so the wait ends.
pickIn(c.querySelector('.fcc-cr-pick[data-line="pos:6"]'), '243');
const picked = Object.assign({ btn: stateOf(btn) }, said(c));
btn.click();
await settle(30);
const reasked = Object.assign({ btn: stateOf(btn) }, said(c));
// T6's grams emptied: it is left again, so the wait ends again.
fill(c, 'pos:6', '');
const emptied = Object.assign({ btn: stateOf(btn) }, said(c));
btn.click();
await settle(30);
const again = Object.assign({ btn: stateOf(btn) }, said(c));
return { asked, picked, reasked, emptied, again, posted: posts('/api/cancel_deduct/confirm').length };
"""


def test_a_change_on_a_plain_line_ends_the_wait(tmp_path):
    # On e777bcd: AssertionError: ('⚠️ Yes, leave 84.28 g uncharged' ...) (T6 was never counted, and
    # a pick there left the button saying "⚠️ Yes" over grams that had changed)
    res = _run(tmp_path, PLAIN_CHANGE_JS, [SET_PLUS_LINE])
    assert res["posted"] == 0, res
    assert res["asked"]["text"] == "⚠️ Yes, leave 104.28 g uncharged", res["asked"]
    p = res["picked"]
    assert _normal(p["btn"]) and p["alerts"] == [] and p["notice"] is None, p
    r = res["reasked"]
    assert r["btn"]["text"] == "⚠️ Yes, leave 84.28 g uncharged" and r["notice"] is None, r
    e = res["emptied"]
    assert _normal(e["btn"]) and e["alerts"] == [] and e["notice"] is None, e
    a = res["again"]
    assert a["btn"]["text"] == "⚠️ Yes, leave 104.28 g uncharged" and a["notice"] == T6_LEFT, a


REFUSED_JS = r"""
const out = {};
const typeBox = (c, line, text) => {
  const b = c.querySelector(`.fcc-cr-other[data-line="${CSS.escape(line)}"]`);
  b.value = text; fire(b, 'input');
};
// D.cases: a line moved to "Another spool by #ID…" with a spool's number in its box,
// a first press that asks, the box then left unreadable, and a press long after.
for (const k of D.cases) {
  const c = cardOf(k.job);
  pickIn(c.querySelector(`.fcc-cr-pick[data-line="${CSS.escape(k.line)}"]`), 'other');
  typeBox(c, k.line, k.sid);
  await settle(20);
  const btn = c.querySelector('.fcc-cr-confirm');
  btn.click();
  await settle(30);
  const asked = stateOf(btn);
  typeBox(c, k.line, 'abc');
  await settle(720);
  btn.click();
  await settle(30);
  out[k.job] = Object.assign({ asked, btn: stateOf(btn) }, said(c));
}
return { out, posted: posts('/api/cancel_deduct/confirm').length };
"""
REFUSED_CASES = [{"job": "nsl", "line": "6", "sid": "243"},        # no_spool: a plain line
                 {"job": "psl", "line": "pos:6", "sid": "243"},    # partial: a plain held line
                 {"job": "ps", "line": "243", "sid": "243"}]       # partial: a row


def test_a_press_refused_before_the_set_check_ends_the_wait(tmp_path):
    # On e777bcd: AssertionError: ('nsl', ... 'text': '⚠️ Yes, leave 84.28 g uncharged' ...) (the
    # refused press left the orange Yes and the set's "press ⚠️ Yes below" up, though no press of
    # it could go ahead)
    res = _run(tmp_path, REFUSED_JS, [NOSPOOL_PLUS_LINE, SET_PLUS_LINE, PARTIAL_SET], cases=REFUSED_CASES)
    assert res["posted"] == 0, res
    words = {"nsl": "Type the #id of the spool T6 used (or pick one).",
             "psl": "Type the #id of the spool T6 used (or pick one).",
             "ps": "Type the #id of the spool to charge (or pick one)."}
    for job, notice in words.items():
        o = res["out"][job]
        assert _waiting(o["asked"]), (job, o)
        # The refusal is said, and the button and the sets say their own words again.
        assert _normal(o["btn"], APPLY if job == "nsl" else CONFIRM), (job, o)
        assert o["alerts"] == [] and o["notice"] == notice, (job, o)


DOUBLE_JS = r"""
const c = cardOf('ts');
const btn = c.querySelector('.fcc-cr-confirm');
btn.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, detail: 1 }));
await settle(20);
const first = Object.assign({ btn: stateOf(btn) }, said(c));
btn.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, detail: 2 }));
await settle(20);
const second = Object.assign({ btn: stateOf(btn) }, said(c));
return { first, second, posted: posts('/api/cancel_deduct/confirm').length };
"""


def test_a_double_clicks_second_press_keeps_the_line_by_the_buttons(tmp_path):
    # On e777bcd: AssertionError: assert None == "2 heads' grams don't add up, ..." (the second click
    # of a double click cleared the card's line while the button still waited; at phone width the
    # panel scrolls the button back under the pointer, so the second click lands on it)
    res = _run(tmp_path, DOUBLE_JS, [TWO_SETS])
    assert res["posted"] == 0, res
    lead = "2 heads' grams don't add up, as each says above. Press ⚠️ Yes below to leave them uncharged."
    assert res["first"]["notice"] == lead, res["first"]
    assert res["second"]["notice"] == lead, res["second"]
    assert res["second"]["btn"] == res["first"]["btn"] and _waiting(res["second"]["btn"]), res


# --------------------------------------------------------------------------- #
# Derek's picture check of round 2 (2026-11-12): a head's name reads as a head #
# --------------------------------------------------------------------------- #
# "I think there should be some bolding on T6, like there was on the others, so
# that it reads as a toolhead, instead of perhaps another part of the ui." A set's
# header and its orange words were bold; a plain line's label ("T6 · HEAD-7 used")
# and the line by the buttons ("... charges nothing to T6 · HEAD-7, ...") were
# not, so T6's grams read as part of the set above them.

_ODD = {"toolhead": "HEAD<i>9", "position": 8, "sid": 77, "sids": [77]}
# T4 a set, T0 and T6 plain lines: two heads named in the one line.
SET_PLUS_TWO = dict(PARTIAL_SET, job_id="s2l", spools=[], unresolved_usage={"0": 30.0, "4": 84.28, "6": 20.0},
                    total_grams=134.28, heads_at_end=PARTIAL_SET["heads_at_end"] + [_HEAD_1])
# A head whose name holds markup: words on the card, never HTML.
SET_PLUS_ODD = dict(PARTIAL_SET, job_id="odd", spools=[], unresolved_usage={"4": 84.28, "8": 12.0},
                    total_grams=96.28, heads_at_end=PARTIAL_SET["heads_at_end"] + [_ODD])

BOLD_CASES = [
    {"job": "psl", "fill": {}, "press": True},                   # partial: T4 a set, T6 a plain line
    {"job": "s2l", "fill": {}, "press": True},                   # partial: T4 a set, T0 and T6 plain
    {"job": "nsl", "fill": {"set:4:42": 30}, "press": True},     # no_spool: T4 a set, T6 a plain line
    {"job": "odd", "fill": {}, "press": True},                   # a head named "HEAD<i>9"
    {"job": "s#shortfall", "fill": {}, "press": False},          # an uncharged-grams card's line
]
BOLD_PENDING = [SET_PLUS_LINE, SET_PLUS_TWO, NOSPOOL_PLUS_LINE, SET_PLUS_ODD, SHORTFALL]

BOLD_JS = r"""
const bold = (el) => el.querySelectorAll('b').map((b) => b.className + '=' + b.textContent);
const out = {};
for (const k of D.cases) {
  const c = cardOf(k.job);
  const o = { labels: c.querySelectorAll('.fcc-cr-line-head').map((b) => b.tagName + ':' + b.textContent),
              tags: c.querySelectorAll('i').length };
  Object.entries(k.fill).forEach(([line, g]) => fill(c, line, g));
  if (k.press) {
    const btn = c.querySelector('.fcc-cr-confirm');
    const n = c.querySelector('.fcc-cr-card-notice');
    btn.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, detail: 1 }));
    await settle(20);
    o.first = { text: n.textContent, bold: bold(n), tags: n.querySelectorAll('i').length };
    // A double click's second press says the line again, its heads still bold.
    btn.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, detail: 2 }));
    await settle(20);
    o.second = { text: n.textContent, bold: bold(n), tags: n.querySelectorAll('i').length };
  }
  out[k.job] = o;
}
return { out, posted: posts('/api/cancel_deduct/confirm').length };
"""


def test_a_heads_name_is_bold_on_its_line_and_by_the_buttons(tmp_path):
    # On 82524e4: AssertionError: ('psl', {'first': {'bold': [], ...}, 'labels': [], ...}) (a plain
    # line's head and the line by the buttons were drawn in the words' own weight, so T6's grams
    # read as part of T4's set above them)
    res = _run(tmp_path, BOLD_JS, BOLD_PENDING, cases=BOLD_CASES)
    assert res["posted"] == 0, res
    out = res["out"]
    two = ("⚠️ Yes below charges nothing to T0 · HEAD-1 or T6 · HEAD-7, leaving their 50 g uncharged.")
    odd = "⚠️ Yes below charges nothing to T8 · HEAD<i>9, leaving its 12 g uncharged."
    want = {"psl": (["B:T6 · HEAD-7"], T6_LEFT, ["fcc-cr-notice-head=T6 · HEAD-7"]),
            "s2l": (["B:T0 · HEAD-1", "B:T6 · HEAD-7"], two,
                    ["fcc-cr-notice-head=T0 · HEAD-1", "fcc-cr-notice-head=T6 · HEAD-7"]),
            "nsl": (["B:T6 · HEAD-7"], T6_LEFT, ["fcc-cr-notice-head=T6 · HEAD-7"]),
            "odd": (["B:T8 · HEAD<i>9"], odd, ["fcc-cr-notice-head=T8 · HEAD<i>9"]),
            "s#shortfall": (["B:T0 · HEAD-1"], None, None)}
    for job, (labels, text, bold) in want.items():
        o = out[job]
        # Each plain line's head, bold, in the words it was given (an odd name too).
        assert o["labels"] == labels and o["tags"] == 0, (job, o)
        if text is None:
            continue
        # The line by the buttons: the same words, each head it names bold, and
        # the same again after a double click's second press.
        for press in ("first", "second"):
            assert o[press] == {"text": text, "bold": bold, "tags": 0}, (job, press, o)
