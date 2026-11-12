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
    does nothing.

The browser contrast case is tests/test_contrast_guard.py's
test_review_card_notices_are_readable, which scores the waiting state as drawn;
this file checks its colours offline.

HEAD proof: run on d8876bd (before R1), every test here fails (the button kept
its green "Confirm deduct" through the wait, the set's words were amber with no
box, and a set's grams changed and put back went ahead on the first ask, with no
words up).
"""
from __future__ import annotations

import colorsys
import re

from test_cancel_review_picker_scan_js import _contrast, pytestmark  # noqa: F401  (pytestmark: skip without node)
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
