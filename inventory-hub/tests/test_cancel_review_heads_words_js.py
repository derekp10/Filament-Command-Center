"""The 🛑 Review card's words for where FCC read the heads (hotfix 2026-11-11).

Runs the real cancel_review.js under node's `vm` (the shared driver in
test_core1_return_ejectall_js.py; no browser, no container), opens the review over
one card of every kind, and reads the overlay's HTML. One `cardHtml` draws every
card, so an error there would break the 🛑 Review on prod, the job 1141 card
included: every kind is drawn here, a card from before the hotfix among them.

Pinned:
  - a card built from a read of the heads says where it was read: the words ride
    on the record (`heads_words`, print_deduct._HEADS_WORDS, the one map the
    server's notes use too); a card from before has none and reads "when FCC
    logged the print" (that map's `late`), everywhere, the lead too: "when the
    print ended" is said only of a read taken then;
  - spools offered from the start snapshot or the swap log sit in their own
    groups ("When the print started", "During the print"), a head that had two
    spools offers both, and a spool row's picker offers the heads too;
  - a held line's note and the note under a row (a spool loaded since the end)
    are drawn, escaped, in readable colours and a named size;
  - a card with notes leads neutrally ("FCC isn't sure which spool printed").

The browser contrast case is tests/test_contrast_guard.py's
test_print_end_review_notes_are_readable; this file checks the colours offline.
"""
from __future__ import annotations

import html
import json
import re

import pytest

from test_core1_return_ejectall_js import pytestmark, run_js  # noqa: F401  (pytestmark: skip without node)

import print_deduct

CARD_BG = "#17181b"
WORDS = {"end": "when the print ended", "start": "when the print started", "during": "during the print"}

CAPTURE = [{"toolhead": f"RCOI-{i + 1}", "position": i, "sid": sid, "sids": [sid]}
           for i, sid in enumerate([72, 77, 71, 26, 229, 96, 243, 231])]


def _base(job, kind, **extra):
    rec = {"printer_name": "INDX", "job_id": job, "filename": "/usb/F.BGC", "progress": 0.42,
           "total_grams": 10.0, "spools": [], "ambiguous": False, "kind": kind}
    rec.update(extra)
    return rec


def _row(sid, toolhead, pos, grams):
    return {"sid": sid, "toolhead": toolhead, "position": pos, "grams": grams, "current_used": 700.0,
            "initial_weight": 1000.0, "remaining_before": 300.0, "remaining_after": 300.0 - grams,
            "display": f"Spool {sid}", "color": "ff0000", "ambiguous": False}


PENDING = [
    # A partial card from before the hotfix: no new keys at all.
    _base("old-partial", "partial", spools=[_row(96, "RCOI-1", 0, 5.0)], unresolved_usage={"2": 5.0},
          heads_at_end=[{"toolhead": "RCOI-1", "position": 0, "sid": 96},
                        {"toolhead": "RCOI-3", "position": 2, "sid": None}]),
    # The same, built from the print-end read: a held head, a row whose head holds another spool now.
    _base("new-partial", "partial", spools=[_row(243, "RCOI-7", 6, 75.32), _row(231, "RCOI-8", 7, 21.9)],
          unresolved_usage={"4": 84.28}, heads_source="print_end", heads_read_at="2026-11-11 14:30:48",
          heads_words=WORDS,
          heads_at_end=CAPTURE + [{"toolhead": "RCOI-5", "position": 4, "sid": 42, "when": "start"},
                                  {"toolhead": "RCOI-5", "position": 4, "sid": 300, "when": "during"}],
          unresolved_notes={"4": "RCOI-5 had #42 when the print started and #229 when the print ended. "
                                 "Pick the spool it used. <b>x</b>"},
          row_notes={"243": "#229 is on RCOI-7 now; #243 was on it when the print ended."}),
    _base("new-nospool", "no_spool", usage_map={"4": 84.28}, heads_source="print_end", heads_words=WORDS,
          heads_at_end=[{"toolhead": "RCOI-5", "position": 4, "sid": None, "sids": [42, 229]}],
          unresolved_notes={"4": "RCOI-5 had two spools when the print ended (#42 and #229), so FCC "
                                 "can't tell which one printed. Pick the spool it used."}),
    _base("old-nospool", "no_spool", usage_map={"0": 5.0},
          heads_at_end=[{"toolhead": "XL-1", "position": 0, "sid": 5}]),
    _base("new-short#shortfall", "shortfall", rev=0, unresolved_usage={"0": 3.0},
          shortfall_causes={"0": {"why": "not_charged", "sid": 5, "toolhead": "XL-1", "archived": False}},
          heads_at_end=[{"toolhead": "XL-1", "position": 0, "sid": 5, "sids": [5]}],
          heads_source="restart", heads_words=dict(WORDS, end="when FCC restarted after the print")),
    _base("old-short#shortfall", "shortfall", rev=0, unresolved_usage={"0": 3.0},
          shortfall_causes={"0": {"why": "not_charged", "sid": 5, "toolhead": "XL-1", "archived": False}},
          heads_at_end=[{"toolhead": "XL-1", "position": 0, "sid": 5}]),
    _base("split", "spool_changed", auto_split=True, changed_positions=[4], heads_source="print_end",
          heads_words=WORDS, spools=[dict(_row(42, "RCOI-5", 4, 20.0), runout=True, auto_split=True),
                                     dict(_row(229, "RCOI-5", 4, 30.0), auto_split=True)],
          heads_at_end=CAPTURE),
    _base("held", "spool_changed", auto_split=False, changed_positions=[4], heads_source="print_end",
          heads_words=WORDS, spools=[_row(243, "RCOI-7", 6, 20.0)], unresolved_usage={"4": 50.0},
          heads_at_end=CAPTURE + [{"toolhead": "RCOI-5", "position": 4, "sid": 42, "when": "start"}],
          unresolved_notes={"4": "RCOI-5 had #42 when the print started and #229 when the print ended. "
                                 "Pick the spool it used."}),
    _base("old-changed", "spool_changed", auto_split=False, changed_positions=[0],
          spools=[_row(999, "XL-1", 0, 5.0)]),
    _base("unmeasured", "progress_unknown", unmeasured_reason="no_footer", usage_map=None),
]

SCENARIO = """
const pending = __PENDING__;
window.__respond = (url) => {
  if (url.startsWith('/api/cancel_deduct/pending')) return { body: { pending } };
  if (url.startsWith('/api/cancel_deduct/candidates')) return { body: { heads: [] } };
  return { body: {} };
};
await window.openCancelReview();
await __settle(80);
const last = __rec.overlays[__rec.overlays.length - 1];
return { html: last ? last.content : '', overlays: __rec.overlays.length, toasts: __rec.toasts };
"""


@pytest.fixture(scope="module")
def drawn(tmp_path_factory):
    res = run_js(tmp_path_factory.mktemp("cr"), ["cancel_review.js"],
                 SCENARIO.replace("__PENDING__", json.dumps(PENDING)))
    assert res["unhandled"] == [], res["unhandled"]
    assert res["overlays"] == 1 and res["html"], res
    cards = {}
    for chunk in res["html"].split('class="fcc-cr-card"')[1:]:
        job = html.unescape(re.search(r'data-job="([^"]*)"', chunk).group(1))
        cards[job] = chunk
    assert set(cards) == {r["job_id"] for r in PENDING}, sorted(cards)
    return cards


def _text(fragment):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", fragment))).strip()


def _options(fragment, cls):
    out = []
    for m in re.finditer(r'<optgroup label="([^"]*)" class="%s">(.*?)</optgroup>' % re.escape(cls), fragment, re.S):
        out.append((html.unescape(m.group(1)),
                    [html.unescape(o) for o in re.findall(r"<option[^>]*>([^<]*)</option>", m.group(2))]))
    return out


def _lum(hexcol):
    hexcol = hexcol.lstrip("#")
    if len(hexcol) == 3:
        hexcol = "".join(c * 2 for c in hexcol)
    chans = []
    for i in (0, 2, 4):
        c = int(hexcol[i:i + 2], 16) / 255
        chans.append(c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4)
    return 0.2126 * chans[0] + 0.7152 * chans[1] + 0.0722 * chans[2]


def _contrast(fg, bg=CARD_BG):
    a, b = sorted((_lum(fg), _lum(bg)), reverse=True)
    return (a + 0.05) / (b + 0.05)


def _styled(fragment, cls):
    """The inline styles of every element with `cls`."""
    return re.findall(r'class="[^"]*\b%s\b[^"]*"[^>]*style="([^"]*)"' % re.escape(cls), fragment)


# --------------------------------------------------------------------------- #

def test_a_card_from_before_the_hotfix_keeps_its_words(drawn):
    card = drawn["old-partial"]
    late = print_deduct._HEADS_WORDS["late"]              # the one map's word for no source
    assert late == "when FCC logged the print"
    groups = _options(card, "fcc-cr-ended")
    assert groups and all(label == "When FCC logged the print" for label, _ in groups), groups
    assert any(f"#96 — on RCOI-1 {late}" in opt for _, opts in groups for opt in opts), groups
    text = _text(card)
    assert f"No spool was loaded on this head {late}." in text, text
    assert "when the print ended" not in text
    for cls in ("fcc-cr-line-note", "fcc-cr-row-note", "fcc-cr-started", "fcc-cr-during"):
        assert cls not in card, cls


def test_a_card_built_from_the_print_end_read_says_so(drawn):
    card = drawn["new-partial"]
    ended = _options(card, "fcc-cr-ended")
    started = _options(card, "fcc-cr-started")
    during = _options(card, "fcc-cr-during")
    assert ended and all(label == "When the print ended" for label, _ in ended), ended
    assert started and all(label == "When the print started" for label, _ in started), started
    assert during and all(label == "During the print" for label, _ in during), during
    assert "#42 — on RCOI-5 when the print started" in started[0][1]
    assert "#300 — on RCOI-5 during the print" in during[0][1]
    # The start spool is never listed as if it was on the head at the end.
    assert not any("#42 " in opt for _, opts in ended for opt in opts), ended
    # A row's own picker offers the heads too (it used to offer nothing but #id).
    row = card.split('data-sid="243"', 1)[1].split('class="fcc-cr-row"', 1)[0]
    assert any("#229 — on RCOI-5 when the print ended" in o for _, opts in _options(row, "fcc-cr-ended") for o in opts)


def test_a_held_line_shows_its_note_escaped_under_a_neutral_lead(drawn):
    card = drawn["new-partial"]
    text = _text(card)
    assert "FCC isn't sure which spool printed on this head." in text, text
    assert "No spool was loaded" not in text
    assert "&lt;b&gt;x&lt;/b&gt;" in card and "<b>x</b>" not in card
    assert ("RCOI-5 had #42 when the print started and #229 when the print ended. Pick the spool it used."
            in text)
    note_at = card.index("fcc-cr-line-note")
    assert card.index('data-pos="4"') < note_at, "the note sits under its line"


def test_a_spool_loaded_since_the_end_is_noted_under_its_row(drawn):
    card = drawn["new-partial"]
    row = card.split('data-sid="243"', 1)[1].split('class="fcc-cr-row"', 1)[0]
    assert "fcc-cr-row-note" in row
    assert "#229 is on RCOI-7 now; #243 was on it when the print ended." in _text(row)
    assert "fcc-cr-row-note" not in card.split('data-sid="231"', 1)[1]


def test_a_no_spool_card_offers_both_spools_of_a_two_spool_head(drawn):
    card = drawn["new-nospool"]
    text = _text(card)
    assert "isn't sure which spool it came from" in text, text
    assert "RCOI-5 had two spools when the print ended (#42 and #229)" in text
    opts = [o for _, os_ in _options(card, "fcc-cr-ended") for o in os_]
    assert "#42 — on RCOI-5 when the print ended" in opts and "#229 — on RCOI-5 when the print ended" in opts


def test_an_older_no_spool_card_says_when_fcc_read_its_heads(drawn):
    text = _text(drawn["old-nospool"])
    assert "no spool was loaded on the head it was sliced for when FCC logged the print" in text, text
    assert "isn't sure" not in text


def test_a_shortfall_card_names_its_spool_in_the_words_of_its_source(drawn):
    assert "#5 — on XL-1 when FCC restarted after the print" in _text(drawn["new-short#shortfall"])
    assert "#5 — on XL-1 when FCC logged the print" in _text(drawn["old-short#shortfall"])


def test_the_spool_changed_cards(drawn):
    split = _text(drawn["split"])
    assert "auto-split" in split
    assert "fcc-cr-ended" in drawn["split"]               # its rows' pickers offer the heads
    held = _text(drawn["held"])
    assert "FCC can't tell which spool printed" in held, held
    assert "replacement</b>" not in drawn["held"]
    assert "FCC isn't sure which spool printed on this head." in held
    old = drawn["old-changed"]
    assert "are the <b>replacement</b> spool(s) at completion" in re.sub(r"\s+", " ", old)


def test_an_unmeasured_card_is_unchanged(drawn):
    text = _text(drawn["unmeasured"])
    assert "filament footer couldn't be read" in text
    assert "fcc-cr-pick" not in drawn["unmeasured"]


def test_the_new_notes_are_readable_and_use_a_named_size(drawn):
    """The browser contrast guard can't run offline; this checks the colours the
    notes are drawn in against the card, and their size."""
    styles = _styled(drawn["new-partial"], "fcc-cr-line-note") + _styled(drawn["new-partial"], "fcc-cr-row-note")
    assert len(styles) == 2, styles
    for style in styles:
        colour = re.search(r"(?<![-\w])color:\s*(#[0-9a-fA-F]{3,6})", style).group(1)
        assert _contrast(colour) >= 4.5, (colour, _contrast(colour))
        assert re.search(r"font-size:\s*var\(--fcc-fs-(small|row)\)", style), style
