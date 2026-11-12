"""The 🛑 Review card shows a head's spools as a set (hotfix 2026-11-11, scope B).

Runs the real cancel_review.js under node's `vm` (the shared driver in
test_core1_return_ejectall_js.py; no browser, no container), opens the review over
one card of each shape, and reads the overlay's HTML as a tree.

Pinned:
  - a head whose grams FCC split at the swaps it recorded (a cancel's or a
    completion's) is one set: a header naming the head and saying it had N spools
    this print, then its rows in the order they printed, each with its segment
    ("start → 19%, ran out", "19% → 42%", "19% → end") and its grams box
    pre-filled, as rows are; another head's row stays outside the set;
  - a head FCC couldn't split, or whose spool changed with no swap recorded, is a
    set of every spool it had: each with its own grams box, nothing pre-filled,
    its own "charge to" picker on that spool, the words for when FCC saw it there,
    a "to split" count and the note. Its lines are the card's ordinary uncharged
    lines (`fcc-cr-unline` on a partial card, `fcc-cr-pickline` on a no_spool one,
    with `data-pos`), so the card's Apply charges each by position and spool;
  - a card from before scope B: split rows with no segments are grouped and keep
    their "ran out" badge; a held line with no set is one line, as before;
  - the new text is readable on the card and uses the named sizes.

The browser contrast case is tests/test_contrast_guard.py's
test_review_sets_are_readable; this file checks the colours offline.

HEAD proof: run on 6a9b3ef (before scope B), every test here fails.
"""
from __future__ import annotations

import json
import re
from html.parser import HTMLParser

import pytest

from test_core1_return_ejectall_js import pytestmark, run_js  # noqa: F401  (pytestmark: skip without node)

CARD_BG = "#17181b"
WORDS = {"end": "when the print ended", "start": "when the print started", "during": "during the print"}
HEADS = [{"toolhead": "RCOI-5", "position": 4, "sid": 229, "sids": [229]},
         {"toolhead": "RCOI-7", "position": 6, "sid": 243, "sids": [243]},
         {"toolhead": "RCOI-5", "position": 4, "sid": 42, "when": "start"}]
SET_NOTE = ("FCC saw #42 when the print started and #229 when the print ended, but not when it "
            "changed: split the 84.28 g between them, or put it all on one.")


def _row(sid, toolhead, pos, grams, **extra):
    row = {"sid": sid, "toolhead": toolhead, "position": pos, "grams": grams, "current_used": 700.0,
           "initial_weight": 1000.0, "remaining_before": 300.0, "remaining_after": 300.0 - grams,
           "display": f"#{sid} Spool", "color": "ff0000", "ambiguous": False}
    row.update(extra)
    return row


def _base(job, kind, **extra):
    rec = {"printer_name": "INDX", "job_id": job, "filename": "/usb/F.BGC", "progress": 0.42,
           "total_grams": 10.0, "spools": [], "ambiguous": False, "kind": kind}
    rec.update(extra)
    return rec


SET_SPOOLS = [{"sid": 42, "when": "start", "display": "#42 Galaxy Black", "color": "222222", "remaining": 12.5},
              {"sid": 229, "when": "end", "display": "#229 <b>Red</b>", "color": "ff0000", "remaining": 800.0}]

PENDING = [
    # A cancel split at a run-out recorded at 19% (its rows given out of order).
    _base("cancel-split", "partial", heads_source="print_end", heads_words=WORDS, heads_at_end=HEADS,
          spools=[_row(229, "RCOI-5", 4, 54.28, auto_split=True,
                       segments=[{"from": 0.19, "to": 0.42, "runout": False}]),
                  _row(243, "RCOI-7", 6, 75.32),
                  _row(42, "RCOI-5", 4, 32.0, auto_split=True, runout=True,
                       segments=[{"from": None, "to": 0.19, "runout": True}])]),
    # A completion's split: its last segment runs to the end.
    _base("complete-split", "spool_changed", auto_split=True, changed_positions=[4], heads_source="print_end",
          heads_words=WORDS, heads_at_end=HEADS, progress=1.0,
          spools=[_row(42, "RCOI-5", 4, 20.0, auto_split=True, runout=True,
                       segments=[{"from": None, "to": 0.19, "runout": True}]),
                  _row(229, "RCOI-5", 4, 30.0, auto_split=True,
                       segments=[{"from": 0.19, "to": None, "runout": False}])]),
    # A head whose spool changed with no swap recorded: a set, nothing pre-filled.
    _base("held-set", "partial", heads_source="print_end", heads_words=WORDS, heads_at_end=HEADS,
          spools=[_row(243, "RCOI-7", 6, 75.32)], unresolved_usage={"4": 84.28},
          unresolved_sets={"4": SET_SPOOLS}, unresolved_notes={"4": SET_NOTE}),
    # The same on a no_spool card (every used head held).
    _base("nospool-set", "no_spool", heads_source="print_end", heads_words=WORDS, heads_at_end=HEADS,
          usage_map={"4": 84.28}, unresolved_sets={"4": SET_SPOOLS}, unresolved_notes={"4": SET_NOTE}),
    # A completion split from before scope B: no segments on its rows.
    _base("old-split", "spool_changed", auto_split=True, changed_positions=[0], progress=1.0,
          spools=[_row(126, "XL-1", 0, 25.78, auto_split=True, runout=True),
                  _row(127, "XL-1", 0, 85.98, auto_split=True)]),
    # A held line from before scope B: no set.
    _base("old-held", "partial", spools=[_row(96, "XL-1", 0, 5.0)], unresolved_usage={"2": 5.0},
          heads_at_end=[{"toolhead": "XL-3", "position": 2, "sid": None}]),
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


# --------------------------------------------------------------------------- #
# A small HTML tree, so a row's place in a set can be read                    #
# --------------------------------------------------------------------------- #

_VOID = {"input", "br", "img", "meta", "link", "hr", "source", "wbr"}


class _Node:
    def __init__(self, tag, attrs, parent):
        self.tag, self.attrs, self.parent, self.children = tag, dict(attrs), parent, []

    def classes(self):
        return (self.attrs.get("class") or "").split()

    def walk(self):
        yield self
        for c in self.children:
            if isinstance(c, _Node):
                yield from c.walk()

    def all(self, cls):
        return [n for n in self.walk() if cls in n.classes()]

    def where(self, **attrs):
        return [n for n in self.walk() if all(n.attrs.get(k.replace("_", "-")) == v for k, v in attrs.items())]

    def text(self):
        out = []
        for c in self.children:
            out.append(c.text() if isinstance(c, _Node) else c)
        return re.sub(r"\s+", " ", "".join(out)).strip()

    def inside(self, other):
        n = self.parent
        while n is not None:
            if n is other:
                return True
            n = n.parent
        return False


class _Tree(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = _Node("root", [], None)
        self.cur = self.root

    def handle_starttag(self, tag, attrs):
        node = _Node(tag, attrs, self.cur)
        self.cur.children.append(node)
        if tag not in _VOID:
            self.cur = node

    def handle_startendtag(self, tag, attrs):
        self.cur.children.append(_Node(tag, attrs, self.cur))

    def handle_endtag(self, tag):
        n = self.cur
        while n is not None and n.tag != tag:
            n = n.parent
        if n is not None and n.parent is not None:
            self.cur = n.parent

    def handle_data(self, data):
        self.cur.children.append(data)


def _tree(html_text):
    t = _Tree()
    t.feed(html_text)
    return t.root


@pytest.fixture(scope="module")
def drawn(tmp_path_factory):
    res = run_js(tmp_path_factory.mktemp("crsets"), ["cancel_review.js"],
                 SCENARIO.replace("__PENDING__", json.dumps(PENDING)))
    assert res["unhandled"] == [], res["unhandled"]
    assert res["overlays"] == 1 and res["html"], res
    root = _tree(res["html"])
    cards = {c.attrs.get("data-job"): c for c in root.all("fcc-cr-card")}
    assert set(cards) == {r["job_id"] for r in PENDING}, sorted(cards)
    return {"cards": cards, "html": res["html"]}


def _row_el(card, sid):
    rows = [r for r in card.all("fcc-cr-row") if r.attrs.get("data-sid") == str(sid)]
    assert len(rows) == 1, (sid, len(rows))
    return rows[0]


def _style(node):
    return node.attrs.get("style") or ""


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


def _colour(node):
    m = re.search(r"(?<![-\w])color:\s*(#[0-9a-fA-F]{3,6})", _style(node))
    if m:
        return m.group(1)
    return _colour(node.parent) if node.parent is not None else None


# --------------------------------------------------------------------------- #

def test_a_head_split_at_its_recorded_swap_is_one_set_in_the_order_it_printed(drawn):
    card = drawn["cards"]["cancel-split"]
    sets = card.all("fcc-cr-set")
    assert len(sets) == 1, len(sets)
    box = sets[0]
    assert box.attrs.get("data-pos") == "4"
    head = box.all("fcc-cr-set-head")[0].text()
    assert "T4 · RCOI-5 had 2 spools this print" in head, head
    first, second = _row_el(card, 42), _row_el(card, 229)
    assert first.inside(box) and second.inside(box)
    order = [r.attrs.get("data-sid") for r in box.all("fcc-cr-row")]
    assert order == ["42", "229"], order                  # the spool that printed first, first
    assert not _row_el(card, 243).inside(box)              # another head stays outside
    assert first.all("fcc-cr-seg")[0].text() == "start → 19%, ran out"
    assert second.all("fcc-cr-seg")[0].text() == "19% → 42%"
    # Pre-filled, as rows are.
    grams = {r.attrs.get("data-sid"): r.attrs.get("value") for r in box.all("fcc-cr-grams")}
    assert grams == {"42": "32", "229": "54.28"}, grams


def test_a_completions_last_segment_runs_to_the_end(drawn):
    card = drawn["cards"]["complete-split"]
    assert _row_el(card, 229).all("fcc-cr-seg")[0].text() == "19% → end"
    assert len(card.all("fcc-cr-set")) == 1


def test_a_held_set_offers_each_spool_with_its_own_empty_grams_box(drawn):
    card = drawn["cards"]["held-set"]
    box = card.all("fcc-cr-set")[0]
    assert box.attrs.get("data-pos") == "4"
    head = box.all("fcc-cr-set-head")[0].text()
    assert "T4 · RCOI-5 had 2 spools this print" in head, head
    assert box.all("fcc-cr-set-left")[0].text() == "84.28 g to split"
    lines = box.all("fcc-cr-setline")
    assert [ln.attrs.get("data-line") for ln in lines] == ["set:4:42", "set:4:229"]
    for ln, sid, when in ((lines[0], 42, "when the print started"), (lines[1], 229, "when the print ended")):
        # The card's ordinary uncharged line, so its Apply charges it by position and spool.
        assert "fcc-cr-unline" in ln.classes() and ln.attrs.get("data-pos") == "4"
        boxes = ln.all("fcc-cr-pgrams")
        assert len(boxes) == 1 and boxes[0].attrs.get("value") == "", "nothing pre-filled"
        assert boxes[0].attrs.get("data-line") == f"set:4:{sid}"
        pick = ln.all("fcc-cr-pick")[0]
        assert pick.attrs.get("data-line") == f"set:4:{sid}" and pick.attrs.get("data-own") == str(sid)
        chosen = [o for o in pick.walk() if o.tag == "option" and "selected" in o.attrs]
        assert [o.attrs.get("value") for o in chosen] == [str(sid)]
        assert when in ln.text(), ln.text()
    assert "#42 Galaxy Black" in lines[0].text() and "12.5g left" in lines[0].text()
    # Spoolman's text is escaped.
    assert "#229 <b>Red</b>" in lines[1].text()
    assert not [n for n in lines[1].walk() if n.tag == "b"], "markup from Spoolman was drawn"
    note = box.all("fcc-cr-line-note")
    assert len(note) == 1 and note[0].text() == SET_NOTE
    # No single held line for that head beside the set.
    assert not [ln for ln in card.all("fcc-cr-unline") if ln.attrs.get("data-line") == "pos:4"]


def test_a_no_spool_cards_set_lines_are_its_pick_lines(drawn):
    card = drawn["cards"]["nospool-set"]
    box = card.all("fcc-cr-set")[0]
    lines = box.all("fcc-cr-setline")
    assert [ln.attrs.get("data-line") for ln in lines] == ["set:4:42", "set:4:229"]
    assert all("fcc-cr-pickline" in ln.classes() and ln.attrs.get("data-pos") == "4" for ln in lines)
    assert all(ln.all("fcc-cr-pgrams")[0].attrs.get("value") == "" for ln in lines)
    assert not [ln for ln in card.all("fcc-cr-pickline") if ln.attrs.get("data-line") == "4"]
    assert box.all("fcc-cr-line-note")[0].text() == SET_NOTE


def test_cards_from_before_the_sets_keep_their_look(drawn):
    old = drawn["cards"]["old-split"]
    box = old.all("fcc-cr-set")
    assert len(box) == 1 and _row_el(old, 126).inside(box[0]) and _row_el(old, 127).inside(box[0])
    assert not old.all("fcc-cr-seg")
    assert "ran out" in _row_el(old, 126).text()           # its badge, as before
    held = drawn["cards"]["old-held"]
    assert not held.all("fcc-cr-set")
    assert [ln.attrs.get("data-line") for ln in held.all("fcc-cr-unline")] == ["pos:2"]


def test_the_set_text_is_readable_and_uses_the_named_sizes(drawn):
    card = drawn["cards"]["held-set"]
    split = drawn["cards"]["cancel-split"]
    nodes = (card.all("fcc-cr-set-head") + card.all("fcc-cr-set-left") + split.all("fcc-cr-seg")
             + split.all("fcc-cr-seg-out"))
    assert len(nodes) >= 4, len(nodes)
    for node in nodes:
        colour = _colour(node)
        assert colour and _contrast(colour) >= 4.5, (node.classes(), colour)
        sized = node
        while sized is not None and "font-size" not in _style(sized):
            sized = sized.parent
        assert sized is not None and re.search(r"font-size:\s*var\(--fcc-fs-(small|row|label)\)", _style(sized)), \
            (node.classes(), _style(sized) if sized is not None else None)
