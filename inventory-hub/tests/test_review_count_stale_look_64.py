"""Group 64 (Derek, 2026-11-23, at the picture walk, sample (d)): the 🛑 review count in
the Live Activity header after a review list FCC couldn't read (fix review 4, UP7, keeps
its last number) wears the title bar counts' stale look: a dashed edge in its own
colour and a "?" after the count, its tooltip saying why. Derek: "we should match ... as
the ? alone just make it seem more like a statement than denoting anything being wrong
with it ... Mousing over should still say what the issue was."

The "?" and the tooltip are pinned under node (test_weighed_card_64_js.py's
test_a_review_list_fcc_couldnt_read_is_never_no_reviews); this draws global.css in a
real page (`isolated_page`, offline). Red on 26daffc2 (no dashed edge).
"""
from __future__ import annotations

import pathlib

CSS = pathlib.Path(__file__).resolve().parent.parent / "static" / "css" / "global.css"

LOOK = """() => { const b = document.getElementById('cancel-review-badge'); const s = getComputedStyle(b);
    return { style: s.borderTopStyle, colour: s.borderTopColor, width: s.borderTopWidth }; }"""


def test_the_review_count_wears_a_dashed_edge_only_while_its_read_failed(isolated_page):
    page = isolated_page
    page.set_content("<!doctype html><html><head><meta charset='utf-8'></head><body style='background:#111'>"
                     "<span id='cancel-review-badge' style='color:#ffae42;font-weight:bold;'>🛑 2 reviews</span>"
                     "</body></html>")
    page.add_style_tag(content=CSS.read_text(encoding="utf-8"))
    assert page.evaluate(LOOK)["style"] == "none"
    page.evaluate("() => { document.getElementById('cancel-review-badge').dataset.read = 'failed'; }")
    assert page.evaluate(LOOK) == {"style": "dashed", "colour": "rgb(255, 174, 66)", "width": "1px"}
    page.evaluate("() => { delete document.getElementById('cancel-review-badge').dataset.read; }")
    assert page.evaluate(LOOK)["style"] == "none"
