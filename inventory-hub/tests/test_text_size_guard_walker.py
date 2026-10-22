"""The text-size guard's walker, on markup it is handed (readability review,
2026-10-21).

`conftest.text_size_offenders` (behind the `assert_text_size` fixture that
test_text_size_guard.py and test_contrast_guard.py use) judged only elements
with a text node of their own, so what a form control shows (a typed value, a
placeholder, a select's chosen option) was never judged: a 9 px input and a
9 px select each came back "checked 0, offenders []". It now judges every
visible input, select and textarea by its own font size; checkboxes, radios
and colour pickers show no text and are left alone.

Hermetic, and it RUNS under --offline: `isolated_page` is a private chromium
with no route to any network, the markup comes from set_content, and the real
static/css/global.css is read from disk (its named sizes and label rules).

Review proof (feat/readability-2026-10-21 4729579's walker swapped in): the
three form-control tests RED (the 9 px controls went unreported, and a page of
controls alone "has no visible text"); the other two pass there too.

A plain <select> with no Bootstrap class is the browser's 13.33 px, under the
floor: the app's selects carry .form-select (16 px, or 14 px small).
"""
from __future__ import annotations

import os

import pytest

import conftest

GLOBAL_CSS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "static", "css", "global.css")


def _page(page, body: str):
    with open(GLOBAL_CSS, encoding="utf-8") as fh:
        css = fh.read()
    page.set_content(f"<style>{css}</style><div id='t'>{body}</div>")


def test_form_controls_are_judged_by_their_own_size(isolated_page):
    _page(isolated_page, """
        <input id="i-small" style="font-size:9px" value="1000">
        <select id="s-small" style="font-size:9px"><option>Any Mat</option></select>
        <textarea id="ta-small" style="font-size:9px">a note</textarea>
        <input id="i-ok" style="font-size:14px" placeholder="g">
        <input type="checkbox" style="font-size:9px"> <input type="radio" style="font-size:9px">
        <input type="color" style="font-size:9px">
        <span style="font-size:14px">fine</span>""")
    offenders = conftest.text_size_offenders(isolated_page.locator("#t"))
    texts = sorted(o["text"] for o in offenders)
    assert texts == ["[input] 1000", "[select] Any Mat", "[textarea] a note"], offenders
    assert all(o["px"] == 9 and o["floor"] == conftest.TEXT_FLOOR_PX for o in offenders), offenders


def test_a_page_of_controls_alone_is_still_checked(isolated_page):
    """A guard that checked nothing must not pass: a root holding only form
    controls counts as checked now."""
    _page(isolated_page, '<input style="font-size:14px" value="2500">'
                         '<select style="font-size:14px"><option>PETG</option></select>')
    assert conftest.text_size_offenders(isolated_page.locator("#t")) == []


def test_a_label_sized_control_gets_the_label_floor(isolated_page):
    _page(isolated_page, """
        <select style="font-size:var(--fcc-fs-label)"><option>Low</option></select>
        <input style="font-size:12px" value="9">""")
    offenders = conftest.text_size_offenders(isolated_page.locator("#t"))
    assert [(o["text"], o["label"]) for o in offenders] == [("[input] 9", False)], offenders


def test_text_and_labels_are_judged_as_before(isolated_page):
    _page(isolated_page, """
        <span style="font-size:12px">small text</span>
        <span class="badge">a badge</span>
        <span style="font-size:var(--fcc-fs-label)">a label</span>
        <span style="font-size:11px; display:none">hidden</span>""")
    offenders = conftest.text_size_offenders(isolated_page.locator("#t"))
    assert [o["text"] for o in offenders] == ["small text"], offenders


def test_nothing_visible_raises(isolated_page):
    _page(isolated_page, '<span style="display:none">hidden</span><input type="hidden" value="x">')
    with pytest.raises(AssertionError, match="no visible text"):
        conftest.text_size_offenders(isolated_page.locator("#t"))
