"""The 🛑 Review card, the review's findings on what a person reads and does
(hotfix 2026-11-11).

Runs the REAL overlay_mount.js and cancel_review.js under node's `vm` (scope D's
driver, test_cancel_review_picker_scan_js.py: events, focus, keys, values; no
browser, no container). Pinned:

  - a set's header claims only what FCC knows: "had 2 spools this print" when
    the swaps FCC recorded account for every spool (and for a split head), else
    "FCC saw 2 spools on it" (a spool seen only when the print ended may never
    have printed there);
  - a set whose grams aren't all placed, or add up to more than FCC computed, is
    never applied by one press: the first press says so inside the set and on
    the card, and posts nothing; a second press goes ahead (Derek's rule for a
    hard-to-undo yes: more resistance, no typed words). A set placed exactly
    posts at once (round 2: how the wait looks, and what the button says while
    it waits, is test_cancel_review_set_yes_js.py);
  - a no_spool card whose set has no grams says what is missing on the card
    ("type the grams each spool used"), never "pick the spool";
  - every refusal of an Apply (the page's own and the server's) is said on the
    card, in a role=alert line, as well as in its toast (the toast layer is drawn
    under the review panel);
  - a no_spool card built from the print-end read is headed "spool not certain",
    as its banner says; an older one keeps "no spool bound";
  - an auto-split card with a head still to fill in never says "Just Confirm";
  - the card's header total counts its held lines' grams, as the record's total
    and the Activity Log do;
  - a set card's words ask for each spool's grams, not for one spool;
  - a scan read while the keyboard is in a grams box goes to the scan path
    (inv_core.js's installFieldScanCapture, the real one): the box keeps what it
    held and the spool joins the scan buffer, never typed into the grams;
  - the new words are readable on the card and use a named size.

The browser contrast case is tests/test_contrast_guard.py's
test_review_card_notices_are_readable; this file checks the colours offline.

HEAD proof: run on 9b16a9e (before these fixes), every test here fails except
test_a_set_placed_exactly_posts_at_once, which pins what already worked.
"""
from __future__ import annotations

import re
from pathlib import Path

from test_cancel_review_picker_scan_js import (  # noqa: F401  (pytestmark: skip without node)
    CARD_BG, RESPOND_JS, SPOOLS, _base, pytestmark, run)

INV_CORE = Path(__file__).resolve().parent.parent / "static" / "js" / "modules" / "inv_core.js"


def _row(sid, toolhead, pos, grams, remaining=300.0, **extra):
    row = {"sid": sid, "toolhead": toolhead, "position": pos, "grams": grams, "current_used": 700.0,
           "initial_weight": 1000.0, "remaining_before": remaining, "remaining_after": remaining - grams,
           "display": f"#{sid} Test Spool", "color": "ff0000", "ambiguous": False}
    row.update(extra)
    return row

SET_END = [{"sid": 42, "when": "start", "display": "#42 Test", "remaining": 12.5},
           {"sid": 229, "when": "end", "display": "#229 Test", "remaining": 800.0}]
SET_SWAP = [{"sid": 42, "when": "start", "display": "#42 Test", "remaining": 12.5},
            {"sid": 229, "when": "during", "display": "#229 Test", "remaining": 800.0}]
HEADS = [{"toolhead": "HEAD-5", "position": 4, "sid": 229, "sids": [229]},
         {"toolhead": "HEAD-7", "position": 6, "sid": 243, "sids": [243]},
         {"toolhead": "HEAD-5", "position": 4, "sid": 42, "when": "start"}]
NOTE = ("FCC saw #42 when the print started and #229 when the print ended, but not when it changed: "
        "split the 84.28 g between them, or put it all on one.")

PARTIAL_SET = _base("ps", "partial", spools=[_row(243, "HEAD-7", 6, 75.32)], unresolved_usage={"4": 84.28},
                    total_grams=159.6, heads_at_end=HEADS, unresolved_sets={"4": SET_END},
                    unresolved_notes={"4": NOTE})
SWAP_SET = _base("sw", "partial", spools=[], unresolved_usage={"4": 84.28}, heads_at_end=HEADS,
                 unresolved_sets={"4": SET_SWAP},
                 unresolved_notes={"4": "HEAD-5's spool was swapped during the print (#42 to #229 at ~19%), "
                                        "but FCC couldn't split its grams at the swap: split the 84.28 g "
                                        "between them, or put it all on one."})
SPLIT = _base("sp", "partial", heads_at_end=HEADS,
              spools=[_row(42, "HEAD-5", 4, 30.0, auto_split=True, runout=True,
                           segments=[{"from": None, "to": 0.19, "runout": True}]),
                      _row(229, "HEAD-5", 4, 54.28, auto_split=True,
                           segments=[{"from": 0.19, "to": 0.42, "runout": False}])])
NOSPOOL_SET = _base("nss", "no_spool", usage_map={"4": 84.28}, heads_at_end=HEADS,
                    unresolved_sets={"4": SET_END}, unresolved_notes={"4": NOTE})
NOSPOOL_OLD = {"printer_name": "TESTER", "job_id": "nso", "filename": "/usb/F.BGC", "progress": 1.0,
               "total_grams": 50.0, "spools": [], "ambiguous": False, "kind": "no_spool",
               "usage_map": {"0": 50.0}, "heads_at_end": [{"toolhead": "HEAD-1", "position": 0, "sid": None}]}
SPLIT_PLUS_SET = _base("sps", "spool_changed", auto_split=True, changed_positions=[4, 6], progress=1.0,
                       heads_at_end=HEADS, total_grams=104.28, unresolved_usage={"6": 20.0},
                       unresolved_sets={"6": [{"sid": 243, "when": "start", "display": "#243 Test"},
                                              {"sid": 300, "when": "end", "display": "#300 Test"}]},
                       unresolved_notes={"6": "FCC saw #243 when the print started and #300 when the print "
                                              "ended, but not when it changed: split the 20 g between them, "
                                              "or put it all on one."},
                       spools=[_row(42, "HEAD-5", 4, 30.0, auto_split=True, runout=True,
                                    segments=[{"from": None, "to": 0.19, "runout": True}]),
                               _row(229, "HEAD-5", 4, 54.28, auto_split=True,
                                    segments=[{"from": 0.19, "to": None, "runout": False}])])
CHANGED_HELD = _base("ch", "spool_changed", auto_split=False, changed_positions=[4], progress=1.0,
                     heads_at_end=HEADS, spools=[_row(243, "HEAD-7", 6, 20.0)], unresolved_usage={"4": 50.0},
                     unresolved_sets={"4": SET_END}, unresolved_notes={"4": NOTE})

AMBER = "#e6c074"


def _go(tmp_path, body, pending, pre="", **data):
    data.setdefault("spools", SPOOLS)
    return run(tmp_path, pre + RESPOND_JS + body, dict(data, pending=pending))


# --------------------------------------------------------------------------- #
# The set's header                                                             #
# --------------------------------------------------------------------------- #

HEADERS_JS = r"""
const out = {};
['ps', 'sw', 'sp'].forEach((j) => {
  out[j] = cardOf(j).querySelectorAll('.fcc-cr-set-head').map((h) => h.textContent.replace(/\s+/g, ' ').trim());
});
return out;
"""


def test_a_sets_header_claims_only_what_fcc_saw(tmp_path):
    # On 9b16a9e: AssertionError: ['T4 · HEAD-5 had 2 spools this print 84.28 g to split'] (a spool
    # seen only when the print ended was said to have printed there).
    res = _go(tmp_path, HEADERS_JS, [PARTIAL_SET, SWAP_SET, SPLIT])
    assert res["ps"][0].startswith("T4 · HEAD-5: FCC saw 2 spools on it"), res["ps"]
    assert "this print" not in res["ps"][0]
    # The swaps FCC recorded account for both spools: they printed there.
    assert res["sw"][0].startswith("T4 · HEAD-5 had 2 spools this print"), res["sw"]
    assert res["sp"][0].startswith("T4 · HEAD-5 had 2 spools this print"), res["sp"]


# --------------------------------------------------------------------------- #
# Apply over a set that isn't placed exactly                                   #
# --------------------------------------------------------------------------- #

CONFIRMED = r"""
const old = window.__respond;
window.__respond = (url, m, b) => url.startsWith('/api/cancel_deduct/confirm')
  ? { body: { status: 'confirmed', applied: [{ sid: 243, grams: 75.32 }], errors: [], shortfall_g: 84.28 } }
  : old(url, m, b);
"""

EMPTY_SET_JS = CONFIRMED + r"""
const c = cardOf('ps');
const btn = c.querySelector('.fcc-cr-confirm');
const scrolled = [];
btn.scrollIntoView = (o) => { scrolled.push(o); };
btn.click();
await settle(40);
const after1 = posts('/api/cancel_deduct/confirm').length;
const alert = c.querySelector('.fcc-cr-heldset .fcc-cr-set-alert');
const notice = c.querySelector('.fcc-cr-card-notice');
const said = { alert: alert && alert.textContent, alertRole: alert && alert.getAttribute('role'),
               alertShown: !!alert && alert.style.display !== 'none',
               notice: notice && notice.textContent, noticeRole: notice && notice.getAttribute('role'),
               noticeShown: !!notice && notice.style.display !== 'none', enabled: !btn.disabled };
// A double click's second press is no second press: under 700 ms after the
// press that asked, and the second click of a double click, post nothing.
btn.click();
await settle(40);
const quick = { posted: posts('/api/cancel_deduct/confirm').length,
                alertShown: alert.style.display !== 'none' };
await settle(720);
btn.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, detail: 2 }));
await settle(40);
const dbl = { posted: posts('/api/cancel_deduct/confirm').length,
              alertShown: alert.style.display !== 'none' };
btn.click();
await settle(60);
return { after1, said, scrolled, quick, dbl, posted: posts('/api/cancel_deduct/confirm') };
"""


def test_a_set_left_empty_is_never_applied_by_one_press(tmp_path):
    # On 9b16a9e: AssertionError: assert 1 == 0 (one press posted {updates: {243: 75.32}};
    # the server closed the review with HEAD-5's 84.28 g uncharged).
    res = _go(tmp_path, EMPTY_SET_JS, [PARTIAL_SET])
    assert res["after1"] == 0, res
    s = res["said"]
    assert s["alertShown"] and s["alertRole"] == "alert", s
    # Round 2 (R1): with a ⚠️, pointing at the button as it reads while it waits
    # (test_cancel_review_set_yes_js.py pins the button and the orange look).
    assert s["alert"] == ("⚠️ T4 · HEAD-5: none of its 84.28 g are placed. Type the grams each spool used, "
                          "or put them all on one; or press ⚠️ Yes below to leave them uncharged."), s
    # One set's words are said in the set alone: held sets are among a card's last
    # lines, just above its buttons, and the card's notice said them again a line
    # below (the picture check, 2026-11-12). On 4c2b750 the notice repeated the alert.
    assert not s["noticeShown"] and s["noticeRole"] == "alert", s
    # The words make the card taller: the button just pressed is kept in view.
    assert res["scrolled"] == [{"block": "nearest"}], res
    assert s["enabled"], s
    # A double click's second press does nothing, and the words stay up. On 4c2b750
    # the quick second press posted.
    assert res["quick"] == {"posted": 0, "alertShown": True}, res
    assert res["dbl"] == {"posted": 0, "alertShown": True}, res
    # A second press goes ahead: what nobody placed is the job's shortfall.
    assert res["posted"] == [{"printer_name": "TESTER", "job_id": "ps", "updates": {"243": 75.32}}], res


TWO_SETS = _base("ts", "partial", spools=[], unresolved_usage={"4": 84.28, "6": 20.0}, total_grams=104.28,
                 heads_at_end=HEADS + [{"toolhead": "HEAD-7", "position": 6, "sid": 243, "when": "start"}],
                 unresolved_sets={"4": SET_END,
                                  "6": [{"sid": 243, "when": "start", "display": "#243 Test", "remaining": 300.0},
                                        {"sid": 300, "when": "end", "display": "#300 Test", "remaining": 900.0}]},
                 unresolved_notes={"4": NOTE})

TWO_SETS_JS = CONFIRMED + r"""
const c = cardOf('ts');
const btn = c.querySelector('.fcc-cr-confirm');
btn.click();
await settle(40);
const after1 = posts('/api/cancel_deduct/confirm').length;
const alerts = c.querySelectorAll('.fcc-cr-heldset .fcc-cr-set-alert')
  .map((a) => (a.style.display !== 'none' ? a.textContent : null));
const notice = c.querySelector('.fcc-cr-card-notice');
const said = { alerts, notice: notice && notice.textContent,
               noticeShown: !!notice && notice.style.display !== 'none' };
await settle(720);
btn.click();
await settle(60);
return { after1, said, posted: posts('/api/cancel_deduct/confirm').length };
"""


def test_two_sets_left_empty_say_so_in_each_and_once_by_the_buttons(tmp_path):
    # Passes on 4c2b750 by design: two sets get one line by the buttons, each its own words.
    res = _go(tmp_path, TWO_SETS_JS, [TWO_SETS])
    assert res["after1"] == 0, res
    s = res["said"]
    assert len(s["alerts"]) == 2 and all(a and "none of its" in a for a in s["alerts"]), s
    assert s["noticeShown"] and s["notice"] == (
        "2 heads' grams don't add up, as each says above. Press ⚠️ Yes below to leave them uncharged."), s
    assert res["posted"] == 1, res


OVER_JS = CONFIRMED + r"""
const c = cardOf('ps');
const boxes = c.querySelectorAll('.fcc-cr-heldset .fcc-cr-pgrams');
boxes[0].value = '84.28'; fire(boxes[0], 'input');
boxes[1].value = '84.28'; fire(boxes[1], 'input');
const btn = c.querySelector('.fcc-cr-confirm');
btn.click();
await settle(40);
const after1 = posts('/api/cancel_deduct/confirm').length;
const alert = c.querySelector('.fcc-cr-heldset .fcc-cr-set-alert');
const said = alert && alert.textContent;
// The person changes a box: the set is asked about again, with the new figure.
boxes[1].value = '90'; fire(boxes[1], 'input');
const gone = !c.querySelector('.fcc-cr-heldset .fcc-cr-set-alert') || c.querySelector('.fcc-cr-heldset .fcc-cr-set-alert').style.display === 'none';
btn.click();
await settle(40);
const after2 = posts('/api/cancel_deduct/confirm').length;
const said2 = c.querySelector('.fcc-cr-heldset .fcc-cr-set-alert').textContent;
await settle(720);
btn.click();
await settle(60);
return { after1, said, gone, after2, said2, posted: posts('/api/cancel_deduct/confirm') };
"""


def test_a_sets_picks_over_its_grams_ask_before_they_charge(tmp_path):
    # On 9b16a9e: AssertionError: assert 1 == 0 (168.56 g of a head that used 84.28 g, charged at once)
    res = _go(tmp_path, OVER_JS, [PARTIAL_SET])
    assert res["after1"] == 0, res
    assert res["said"] == ("⚠️ T4 · HEAD-5: its spools add up to 168.56 g, 84.28 g more than the 84.28 g "
                           "FCC computed. Press ⚠️ Yes below to charge the spools as typed."), res
    assert res["gone"], "a changed box takes the old words away"
    assert res["after2"] == 0 and "174.28 g, 90 g more" in res["said2"], res
    assert len(res["posted"]) == 1, res
    assert res["posted"][0]["charges"] == [
        {"row": 243, "sid": 243, "grams": 75.32},
        {"position": 4, "sid": 42, "grams": 84.28}, {"position": 4, "sid": 229, "grams": 90}], res


EXACT_JS = CONFIRMED + r"""
const c = cardOf('ps');
const boxes = c.querySelectorAll('.fcc-cr-heldset .fcc-cr-pgrams');
boxes[0].value = '30'; fire(boxes[0], 'input');
boxes[1].value = '54.28'; fire(boxes[1], 'input');
c.querySelector('.fcc-cr-confirm').click();
await settle(60);
return { posted: posts('/api/cancel_deduct/confirm') };
"""


def test_a_set_placed_exactly_posts_at_once(tmp_path):
    # Passes on 9b16a9e by design.
    res = _go(tmp_path, EXACT_JS, [PARTIAL_SET])
    assert len(res["posted"]) == 1 and res["posted"][0]["charges"] == [
        {"row": 243, "sid": 243, "grams": 75.32},
        {"position": 4, "sid": 42, "grams": 30}, {"position": 4, "sid": 229, "grams": 54.28}], res


NOSPOOL_EMPTY_JS = r"""
const c = cardOf('nss');
const btn = c.querySelector('.fcc-cr-confirm');
btn.click();
await settle(30);
btn.click();
await settle(30);
const notice = c.querySelector('.fcc-cr-card-notice');
return { posted: posts('/api/cancel_deduct/confirm'), toasts: window.__rec.toasts.map((t) => t.msg),
         notice: notice && notice.textContent, shown: !!notice && notice.style.display !== 'none' };
"""


def test_a_no_spool_set_with_no_grams_says_what_is_missing_on_the_card(tmp_path):
    # On 9b16a9e: AssertionError: assert None == "Type the grams each spool on T4 · HEAD-5 used ..."
    # (only a toast, "Pick the spool this print used (or type its #id) first.", under the panel).
    res = _go(tmp_path, NOSPOOL_EMPTY_JS, [NOSPOOL_SET])
    assert res["posted"] == [], res
    want = ("Type the grams each spool on T4 · HEAD-5 used (or put them all on one), then Apply. "
            "Or Discard the review.")
    assert res["shown"] and res["notice"] == want, res
    assert not any("Pick the spool this print used" in m for m in res["toasts"]), res["toasts"]


REFUSED_JS = r"""
const c = cardOf('ps');
const old = window.__respond;
window.__respond = (url, m, b) => url.startsWith('/api/cancel_deduct/confirm')
  ? { body: { status: 'error', msg: 'spool #229 was picked twice for tool 4' } } : old(url, m, b);
const a = lineOf(c, 'set:4:42');
pickIn(a.sel, '229');
const boxes = c.querySelectorAll('.fcc-cr-heldset .fcc-cr-pgrams');
boxes[0].value = '40'; fire(boxes[0], 'input');
boxes[1].value = '44.28'; fire(boxes[1], 'input');
const btn = c.querySelector('.fcc-cr-confirm');
btn.click();
await settle(40);
const notice = c.querySelector('.fcc-cr-card-notice');
return { posted: posts('/api/cancel_deduct/confirm').length, notice: notice && notice.textContent,
         shown: !!notice && notice.style.display !== 'none', enabled: !btn.disabled };
"""


def test_a_refused_apply_says_why_on_the_card(tmp_path):
    # On 9b16a9e: AssertionError: assert None == 'spool #229 was picked twice for tool 4'
    res = _go(tmp_path, REFUSED_JS, [PARTIAL_SET])
    assert res["posted"] == 1, res
    assert res["shown"] and res["notice"] == "spool #229 was picked twice for tool 4", res
    assert res["enabled"], res


# --------------------------------------------------------------------------- #
# What the card's header and banner say                                       #
# --------------------------------------------------------------------------- #

WORDS_JS = r"""
const text = (j) => cardOf(j).textContent.replace(/\s+/g, ' ');
const banner = (j) => cardOf(j).innerHTML.replace(/\s+/g, ' ');
return { nss: text('nss'), nso: text('nso'), sps: banner('sps'), ps: text('ps'), ch: text('ch'),
         lead: cardOf('ps').querySelector('.fcc-cr-unresolved-note').textContent.replace(/\s+/g, ' ').trim() };
"""


def test_the_card_says_what_it_knows_and_what_it_needs(tmp_path):
    # On 9b16a9e: AssertionError: '⚠️ TESTER — 84.28g computed, no spool bound' (a card whose
    # banner says FCC isn't sure which spool printed was headed "no spool bound").
    res = _go(tmp_path, WORDS_JS, [NOSPOOL_SET, NOSPOOL_OLD, SPLIT_PLUS_SET, PARTIAL_SET, CHANGED_HELD])
    assert "TESTER — 84.28g computed, spool not certain" in res["nss"], res["nss"]
    assert "no spool bound" not in res["nss"]
    assert "TESTER — 50g computed, no spool bound" in res["nso"], res["nso"]       # an older card
    # An auto-split card with a head still to fill in.
    assert "Just <b>Confirm</b>" not in res["sps"], res["sps"]
    assert "One head listed below still needs your grams: fill it in, then <b>Confirm</b>." in res["sps"]
    # The header total counts the held line's grams: 75.32 + 84.28.
    assert "159.6g total" in res["ps"], res["ps"]
    # A card whose held lines are sets asks for each spool's grams, not for one spool.
    assert res["lead"] == ("⚠️ FCC isn't sure which spool printed on this head. Type the grams each "
                           "spool used (or put them all on one), or leave it: its grams are then logged "
                           "as uncharged."), res["lead"]
    assert "Type the grams each spool used" in res["nss"], res["nss"]
    assert "Type the grams each spool used" in res["ch"], res["ch"]
    assert "Pick the spool it used" not in res["ch"], res["ch"]


# --------------------------------------------------------------------------- #
# A scan with the keyboard in a grams box                                      #
# --------------------------------------------------------------------------- #

def _inv_core_capture():
    """The real installFieldScanCapture and looksLikeScanPayload, from inv_core.js
    (the dashboard loads it before any review opens)."""
    src = INV_CORE.read_text(encoding="utf-8")
    cap = re.search(r"const installFieldScanCapture = .*?\nwindow\.installFieldScanCapture = installFieldScanCapture;",
                    src, re.S)
    look = re.search(r"window\.looksLikeScanPayload = \(txt\) =>.*?;\n", src, re.S)
    assert cap and look, "inv_core.js's scan capture moved: teach this test where"
    return cap.group(0) + "\n" + look.group(0) + "\nwindow.__scans = [];\n" \
        "window.processScan = (t, src) => { window.__scans.push([t, src]); };\n"


SCAN_JS = r"""
const c = cardOf('ps');
const box = c.querySelector('.fcc-cr-pgrams[data-line="set:4:42"]');
box.focus();
box.value = '30'; fire(box, 'input');            // what the person typed first
// A scanner's label, at its speed: a number box keeps only the digits it sends.
for (const ch of 'ID:229') { key(box, ch); if (/\d/.test(ch)) { box.value = box.value + ch; fire(box, 'input'); } }
const during = box.value;
const ev = key(box, 'Enter');
await settle(20);
const left = c.querySelector('.fcc-cr-set-left').textContent;
// A person typing slowly is never taken for a scan.
const other = c.querySelector('.fcc-cr-pgrams[data-line="set:4:229"]');
other.focus();
key(other, '1'); other.value = '1'; fire(other, 'input');
await settle(200);
key(other, '2'); other.value = '12'; fire(other, 'input');
await settle(200);
key(other, 'Enter');
await settle(20);
return { during, value: box.value, scans: window.__scans, prevented: ev.defaultPrevented, left,
         typed: other.value, posted: posts('/api/cancel_deduct/confirm') };
"""


def test_a_scan_in_a_grams_box_goes_to_the_scan_path(tmp_path):
    # On 9b16a9e: AssertionError: assert '30229' == '30' (the label's digits went into #42's grams)
    res = _go(tmp_path, SCAN_JS, [PARTIAL_SET], pre=_inv_core_capture())
    assert res["during"] == "30229", res
    assert res["value"] == "30", res
    assert res["scans"] == [["ID:229", "barcode"]], res
    assert res["prevented"], res
    assert res["left"] == "54.28 g of 84.28 g still to place", res
    assert res["typed"] == "12", res
    assert res["posted"] == [], res


# --------------------------------------------------------------------------- #
# The new words are readable and use a named size                              #
# --------------------------------------------------------------------------- #

LOOK_JS = CONFIRMED + r"""
const c = cardOf('ps');
c.querySelector('.fcc-cr-confirm').click();
await settle(40);
return { alert: c.querySelector('.fcc-cr-set-alert').getAttribute('style'),
         notice: c.querySelector('.fcc-cr-card-notice').getAttribute('style') };
"""


def _lum(hexcol):
    hexcol = hexcol.lstrip("#")
    chans = []
    for i in (0, 2, 4):
        c = int(hexcol[i:i + 2], 16) / 255
        chans.append(c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4)
    return 0.2126 * chans[0] + 0.7152 * chans[1] + 0.0722 * chans[2]


def _contrast(fg, bg=CARD_BG):
    a, b = sorted((_lum(fg), _lum(bg)), reverse=True)
    return (a + 0.05) / (b + 0.05)


def test_the_new_words_are_readable_and_use_a_named_size(tmp_path):
    # On 9b16a9e: AttributeError ... (no set alert, no card notice).
    res = _go(tmp_path, LOOK_JS, [PARTIAL_SET])
    for style in (res["alert"], res["notice"]):
        colour = re.search(r"(?<![-\w])color:\s*(#[0-9a-fA-F]{6})", style).group(1)
        # Round 2 (R1): the set's words are drawn on a ground of their own (an orange box).
        ground = re.search(r"background(?:-color)?:\s*(#[0-9a-fA-F]{6})", style)
        assert _contrast(colour, ground.group(1) if ground else CARD_BG) >= 4.5, (colour, style)
        assert re.search(r"font-size:\s*var\(--fcc-fs-(small|row)\)", style), style
