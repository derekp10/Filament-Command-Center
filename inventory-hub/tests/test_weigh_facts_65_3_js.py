"""Group 65.3, the page half: every weigh save says what it did, hermetic.

The weigh-out list's two saves (a row's computed save, and the Net save made with no
details) and the Quick-Weigh hand saveSpoolWeight `weigh` {source, mode, reading, tare,
tare_skipped}, posted beside `id` and `updates`: the server words the Activity Log line
from it (test_weigh_line_65_3). An Additive figure is grams typed, no reading, so it
sends none; Gross sends the empty-spool weight it used; <WeightEntry>'s Skip (the
reading saved as filament left, with no empty weight) says so as `tare_skipped`. Both
empty-spool prompts say to take off a clip, cap or edge guards first.

Node's `vm` for the saves (the 63.6 harness), the real page in `isolated_page` for
WeightEntry and the prompts. RED on 1be96d6e (no `weigh` was sent, no `tare_skipped`,
no add-ons line).
"""
from __future__ import annotations

import pytest

from test_missing_tare_and_grams_63_7_9_js import PROMPT_ID, _prompt_up, entry  # noqa: F401  (a fixture)
from test_quick_weigh_scan_js import press
from test_weigh_based_on_page_63_6_js import _run, needs_node


def _weighs(res):
    return [(b["updates"], b.get("weigh")) for b in res["updates"]]


@needs_node
@pytest.mark.parametrize("mode,typed,used,weigh", [
    ("net", "250", 750, {"source": "weigh_out", "mode": "net", "reading": 250, "tare": None, "tare_skipped": False}),
    ("gross", "450", 750, {"source": "weigh_out", "mode": "gross", "reading": 450, "tare": 200,
                           "tare_skipped": False}),
    ("additive", "+25", 725, {"source": "weigh_out", "mode": "additive", "reading": None, "tare": None,
                              "tare_skipped": False}),
    ("set_used", "300", 300, {"source": "weigh_out", "mode": "set_used", "reading": 300, "tare": None,
                              "tare_skipped": False}),
])
def test_a_rows_save_says_what_it_was(tmp_path, mode, typed, used, weigh):
    res = _run(tmp_path, f"""
window.weighOutMode = '{mode}';
typeIn('{typed}');
await window.saveWeighOutRow('57');
await __settle(80);
return {{ updates: updates() }};
""")
    assert _weighs(res) == [({"used_weight": used}, weigh)], res


@needs_node
def test_the_net_save_made_with_no_details_says_it_was_a_net_reading(tmp_path):
    res = _run(tmp_path, """
const before = window.__respond;
window.__respond = (url, ...rest) => String(url).startsWith('/api/spool_details')
    ? { status: 500, body: {} } : before(url, ...rest);
typeIn('250');
await window.saveWeighOutRow('57');
await __settle(120);
return { updates: updates() };
""")
    assert _weighs(res) == [({"remaining_weight": 250},
                             {"source": "weigh_out", "mode": "net", "reading": 250, "tare": None,
                              "tare_skipped": False})], res


@needs_node
def test_the_quick_weigh_says_what_each_save_was(tmp_path):
    res = _run(tmp_path, """
let opened = null;
window.WeightEntry = { openModal: (o) => { opened = o; } };
window.openQuickWeigh(57);
await __settle(60);
for (const p of [
    { used_weight: 345, mode: 'gross', value: 875, empty_spool_weight: 220, tare_skipped: false },
    { used_weight: 725, mode: 'additive', value: 25, empty_spool_weight: 200 },
    { used_weight: 355, mode: 'net', value: 645, empty_spool_weight: null, tare_skipped: true },
    { used_weight: 300, mode: 'set_used', value: 300, empty_spool_weight: 200 },
]) {
    opened.onSubmit(Object.assign({ auto_archive: false }, p));
    await __settle(80);
}
return { updates: updates() };
""")
    assert [w for _, w in _weighs(res)] == [
        {"source": "quick_weigh", "mode": "gross", "reading": 875, "tare": 220, "tare_skipped": False},
        {"source": "quick_weigh", "mode": "additive", "reading": None, "tare": None, "tare_skipped": False},
        {"source": "quick_weigh", "mode": "net", "reading": 645, "tare": None, "tare_skipped": True},
        {"source": "quick_weigh", "mode": "set_used", "reading": 300, "tare": None, "tare_skipped": False},
    ], res


# ---- <WeightEntry> reports a skipped empty weight ---------------------------------------------------

def _skipped(page):
    return page.evaluate("() => window.__saved.map((p) => [p.mode, p.tare_skipped])")


def test_skip_says_the_empty_weight_was_skipped(entry):  # noqa: F811
    page, open_ = entry
    open_("gross")
    press(page, "645", 150)
    _prompt_up(page)
    page.click(f"#{PROMPT_ID}-skip")
    page.wait_for_function("() => window.__saved.length === 1")
    assert _skipped(page) == [["net", True]]


def test_a_typed_empty_weight_is_no_skip(entry):  # noqa: F811
    page, open_ = entry
    open_("gross")
    press(page, "645", 150)
    _prompt_up(page)
    press(page, "167", 150)
    page.wait_for_function("() => window.__saved.length === 1")
    assert _skipped(page) == [["gross", False]]


def test_the_missing_tare_question_says_to_take_the_add_ons_off(entry):  # noqa: F811
    page, open_ = entry
    open_("gross")
    press(page, "645", 150)
    _prompt_up(page)
    line = page.evaluate(f"() => document.getElementById('{PROMPT_ID}-addons').innerText")
    assert line == "Take off any clip, cap or edge guards first: FCC counts them as filament.", line
    style = page.evaluate(f"() => document.getElementById('{PROMPT_ID}-addons').getAttribute('style')")
    assert "font-size:var(--fcc-fs-small)" in style.replace(" ", ""), style    # a named size, never typed
