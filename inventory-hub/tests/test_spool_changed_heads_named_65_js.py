"""Group 65's picture walk (Derek, 2026-11-24): the 🔁 spool-changed card's banner names
each changed head as its rows do.

"I noticed that the spools are listed as head 1, but in the notice, it says toolhead
position 0. We may want to resolve any 0 and 1 based positioning so there is consistency
here in the two locations." The banner said "at toolhead position(s) 0" (the slicer's
0-based Position) over rows that said "HEAD-1"; it now says "on HEAD-1", in bold, from the
rows (else the card's heads), and "T2" (the slicer's tool, as the card's lines say it) only
for a head FCC has no name for.

Runs the real cancel_review.js under node's `vm` (no browser, no container). Red on
fadc6409. The Activity Log line's twin is test_spool_changed_heads_named_65.py.
"""
from __future__ import annotations

import html
import json
import re

import pytest

from test_core1_return_ejectall_js import pytestmark, run_js  # noqa: F401  (pytestmark: skip without node)

WORDS = {"end": "when the print ended", "start": "when the print started", "during": "during the print"}
CAPTURE = [{"toolhead": f"RCOI-{i + 1}", "position": i, "sid": sid, "sids": [sid]}
           for i, sid in enumerate([72, 77, 71, 26, 229, 96, 243, 231])]


def _base(job, **extra):
    rec = {"printer_name": "INDX", "job_id": job, "filename": "/usb/F.BGC", "progress": 1.0,
           "total_grams": 10.0, "spools": [], "ambiguous": False, "kind": "spool_changed"}
    rec.update(extra)
    return rec


def _row(sid, toolhead, pos, grams, **more):
    r = {"sid": sid, "toolhead": toolhead, "position": pos, "grams": grams, "current_used": 700.0,
         "initial_weight": 1000.0, "remaining_before": 300.0, "remaining_after": 300.0 - grams,
         "display": f"Spool {sid}", "color": "ff0000", "ambiguous": False}
    r.update(more)
    return r


PENDING = [
    # Auto-split at one head: named from its rows.
    _base("split", auto_split=True, changed_positions=[4], heads_source="print_end", heads_words=WORDS,
          spools=[_row(42, "RCOI-5", 4, 20.0, runout=True, auto_split=True),
                  _row(229, "RCOI-5", 4, 30.0, auto_split=True)], heads_at_end=CAPTURE),
    # Held (no split): the changed head has no row, so its name comes from the card's heads.
    _base("held", auto_split=False, changed_positions=[4], heads_source="print_end", heads_words=WORDS,
          spools=[_row(243, "RCOI-7", 6, 20.0)], unresolved_usage={"4": 50.0},
          heads_at_end=CAPTURE + [{"toolhead": "RCOI-5", "position": 4, "sid": 42, "when": "start"}],
          unresolved_notes={"4": "RCOI-5 had #42 when the print started and #229 when the print ended. "
                                 "Pick the spool it used."}),
    # A card from before the print-end read: the replacement rows only.
    _base("old", auto_split=False, changed_positions=[0], spools=[_row(999, "XL-1", 0, 5.0)]),
    # Two heads changed.
    _base("two", auto_split=True, changed_positions=[4, 6], heads_source="print_end", heads_words=WORDS,
          spools=[_row(42, "RCOI-5", 4, 20.0, runout=True, auto_split=True),
                  _row(229, "RCOI-5", 4, 30.0, auto_split=True),
                  _row(243, "RCOI-7", 6, 10.0, runout=True, auto_split=True),
                  _row(231, "RCOI-7", 6, 5.0, auto_split=True)], heads_at_end=CAPTURE),
    # A head FCC has no name for: the slicer's tool, as the card's lines say it.
    _base("unnamed", auto_split=False, changed_positions=[2], spools=[_row(999, "XL-1", 0, 5.0)]),
    # A name holding markup is drawn as text.
    _base("markup", auto_split=False, changed_positions=[0], spools=[_row(999, "<i>H</i>", 0, 5.0)]),
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
return { html: last ? last.content : '', overlays: __rec.overlays.length };
"""


@pytest.fixture(scope="module")
def drawn(tmp_path_factory):
    res = run_js(tmp_path_factory.mktemp("crn"), ["cancel_review.js"],
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


def _squash(fragment):
    return re.sub(r"\s+", " ", fragment)


@pytest.mark.parametrize("job, said", [
    ("split", "changed mid-print (a filament run-out or M600) on RCOI-5 . FCC auto-split"),
    ("held", "changed mid-print on RCOI-5 , so the slicer total was NOT auto-applied"),
    ("old", "changed mid-print (a filament run-out or M600) on XL-1 , so the full slicer total"),
    ("two", "changed mid-print (a filament run-out or M600) on RCOI-5 and RCOI-7 . FCC auto-split"),
    ("unnamed", "changed mid-print (a filament run-out or M600) on T2 , so the full slicer total"),
])
def test_the_banner_names_each_changed_head_as_its_rows_do(drawn, job, said):
    text = _text(drawn[job])
    assert said in text, (job, text)
    assert "position" not in text, (job, text)


def test_the_names_are_bold_as_the_cards_other_head_names_are(drawn):
    assert "M600) on <b>RCOI-5</b>. FCC" in _squash(drawn["split"])
    assert "on <b>RCOI-5</b> and <b>RCOI-7</b>." in _squash(drawn["two"])


def test_a_name_holding_markup_is_drawn_as_text(drawn):
    card = _squash(drawn["markup"])
    assert "on <b>&lt;i&gt;H&lt;/i&gt;</b>," in card, card
    assert "<i>H</i>" not in card
