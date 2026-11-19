"""Groups 63.7 and 63.9 (a, b), in a real page: the missing-tare question says what
it does and keeps the tare, a new spool's tare is offered, and a weight in another
unit is refused in words.

  63.7: <WeightEntry>'s Gross with no tare known asks for the empty spool's weight
        (promptMissingEmptyWeight, weight_utils.js). It used to ask to "place the
        empty spool on the scale" in the middle of weighing a spool with filament on
        it, promise "We'll use it as the tare for this and future weigh-ins" (nothing
        kept it), and offer "Skip — save as Used Weight" (it saved as Net). Now it
        asks for what the spool weighs empty, says FCC keeps it as this spool's own,
        and its payload carries it as `typed_tare` for the caller to save
        (test_missing_tare_saved_63_7_js); Skip says it saves the number as the
        filament left (Net), and keeps none.
  63.9(a) (Derek's idea, Group 24): a new spool (0 g used, its net known) weighs its
        net plus its own empty spool, so the question opens filled in with the
        reading less the net, the sum shown under the box; never on a used spool,
        never saved unasked.
  63.9(b): the Gross, Net and Set Used boxes, and the question's own box, are text
        boxes read strictly as grams (window.parseGramsReading): "0.645kg", "1.4 lb",
        "6,45" or "7 oz" is refused in words, with no unit conversion. A number box
        kept only the digits and saved them.

Runs the REAL overlay_mount.js, inv_core.js, weight_utils.js and weight_entry.js
and the real scan accumulator in `isolated_page` (no network), on the page's fake
clock, as test_quick_weigh_scan_js does. Tests marked RED fail on e1b22f4.
"""
from __future__ import annotations

import pytest

from test_quick_weigh_scan_js import FAKE_CLOCK, INPUT, MODULES, STUBS, _accumulator, press

PROMPT_ID = "fcc-missing-empty-weight-overlay"
OPEN = """(o) => { window.__saved = []; window.__cancelled = 0;
    window.WeightEntry.openModal({ title: 'Weigh', spool: { id: 6, initial_weight: o.initial, used_weight: o.used },
        empty_spool_weight: o.tare, defaultMode: o.mode, showAutoArchive: true,
        allowUnknownInitial: !!o.unknown,
        onSubmit: (p) => window.__saved.push(p), onCancel: () => { window.__cancelled += 1; } }); }"""


@pytest.fixture
def entry(isolated_page):
    page = isolated_page
    page.set_content("<!doctype html><html><head><meta charset='utf-8'></head><body></body></html>")
    page.add_script_tag(content=STUBS)
    for name in ("overlay_mount.js", "inv_core.js", "weight_utils.js", "weight_entry.js"):
        page.add_script_tag(content=(MODULES / name).read_text(encoding="utf-8"))
    page.add_script_tag(content=_accumulator())
    page.evaluate(FAKE_CLOCK)

    def open_(mode, tare=None, initial=1000, used=31, unknown=False):
        page.evaluate(OPEN, {"mode": mode, "tare": tare, "initial": initial, "used": used, "unknown": unknown})
        page.wait_for_function("(s) => document.activeElement === document.querySelector(s)", arg=INPUT)

    return page, open_


def _prompt_up(page):
    page.wait_for_function("(id) => !!document.getElementById(id)", arg=PROMPT_ID, timeout=5000)


def _saved(page):
    return page.evaluate("() => window.__saved.map((p) => ({ mode: p.mode, value: p.value, "
                         "tare: p.empty_spool_weight, typed: p.typed_tare }))")


# ---- 63.7: what the question says, and what comes back ----------------------------------------------

def test_the_question_asks_for_the_empty_spool_and_says_it_is_kept(entry):
    """RED: it asked to place the empty spool on the scale, promised a tare kept for
    future weigh-ins that nothing kept, and its Skip said "save as Used Weight"."""
    page, open_ = entry
    open_("gross")
    press(page, "645", 150)
    _prompt_up(page)
    text = page.evaluate("(id) => document.getElementById(id).innerText", PROMPT_ID)
    assert "Enter what this spool weighs empty: weigh an empty spool of the same kind, or use the maker’s figure." in text, text
    assert "FCC keeps it as this spool’s own empty weight, so it isn’t asked again." in text, text
    assert "Place the empty spool on the scale" not in text and "future weigh-ins" not in text, text
    skip = page.evaluate(f"() => document.getElementById('{PROMPT_ID}-skip').textContent.trim()")
    # PIN UPDATED DELIBERATELY (Derek's picture walk, 2026-11-18: Skip on one line, "Skip: save as filament left";
    # the offer worded as an estimate, "some brands aren't 100% exact on the 1kg filament").
    assert skip == "Skip: save as filament left", skip


def test_a_tare_typed_into_the_question_comes_back_as_the_spools_own(entry):
    """RED: the payload had no `typed_tare`, so no caller could keep it."""
    page, open_ = entry
    open_("gross")
    press(page, "645", 150)
    _prompt_up(page)
    press(page, "167", 150)
    page.wait_for_function("() => window.__saved.length === 1")
    assert _saved(page) == [{"mode": "gross", "value": 645, "tare": 167, "typed": 167}], _saved(page)


def test_control_skip_saves_as_net_and_keeps_no_tare(entry):
    page, open_ = entry
    open_("gross")
    press(page, "645", 150)
    _prompt_up(page)
    page.click(f"#{PROMPT_ID}-skip")
    page.wait_for_function("() => window.__saved.length === 1")
    (saved,) = _saved(page)
    assert saved["mode"] == "net" and saved["typed"] is None, saved


# ---- 63.9(a): a new spool's tare is offered ----------------------------------------------------------

def test_a_new_spools_tare_is_offered_with_its_sum(entry):
    """RED: no figure was offered."""
    page, open_ = entry
    open_("gross", initial=1000, used=0)
    press(page, "1245", 150)
    _prompt_up(page)
    value = page.evaluate(f"() => document.getElementById('{PROMPT_ID}-input').value")
    offer = page.evaluate(f"() => (document.getElementById('{PROMPT_ID}-offer') || {{}}).textContent || ''")
    assert value == "245", value
    # PIN UPDATED DELIBERATELY (Derek's picture walk, 2026-11-18: Skip on one line, "Skip: save as filament left";
    # the offer worded as an estimate, "some brands aren't 100% exact on the 1kg filament").
    assert offer == "About 245 g: 1245 g on the scale less the 1000 g of filament its label says. A spool often holds a little more than its label, so this can read high: weigh an empty one to be sure.", offer
    assert page.evaluate("() => window.__saved.length") == 0   # never saved unasked
    press(page, "", 150)   # the person's Enter on it
    page.wait_for_function("() => window.__saved.length === 1")
    assert _saved(page) == [{"mode": "gross", "value": 1245, "tare": 245, "typed": 245}], _saved(page)


@pytest.mark.parametrize("initial, used, reading, unknown", [(1000, 31, "1245", False), (1000, 0, "900", False),
                                                            (0, 0, "1245", True)],
                         ids=["used-spool", "reading-under-its-net", "net-unknown"])
def test_control_nothing_is_offered_when_the_sum_cant_be_its_tare(entry, initial, used, reading, unknown):
    """Control: a used spool, a reading under its net, or a net nobody knows (the
    wizard's unknown-net path, allowUnknownInitial) gets no figure."""
    page, open_ = entry
    open_("gross", initial=initial, used=used, unknown=unknown)
    press(page, reading, 150)
    _prompt_up(page)
    value = page.evaluate(f"() => document.getElementById('{PROMPT_ID}-input').value")
    offer = page.evaluate(f"() => !!document.getElementById('{PROMPT_ID}-offer')")
    assert value == "" and offer is False, (value, offer)


# ---- 63.9(b): grams only, refused in words -------------------------------------------------------------

@pytest.mark.parametrize("mode", ["gross", "net", "set_used"])
@pytest.mark.parametrize("typed", ["0.645kg", "1.4 lb", "6,45", "7 oz"])
def test_a_reading_in_another_unit_is_refused_in_words(entry, mode, typed):
    """RED: a number box kept only its digits ("0.645"), and Save saved them."""
    page, open_ = entry
    open_(mode, tare=167)
    press(page, typed, 150)
    page.wait_for_timeout(50)
    warn = page.evaluate("() => document.getElementById('fcc-we-warn').textContent")
    assert warn == f'"{typed}" is not a weight in grams: type grams only, like 645 or 645.5', warn
    assert page.evaluate("() => window.__saved.length") == 0
    assert page.evaluate("(s) => document.querySelector(s).value", INPUT) == typed


@pytest.mark.parametrize("typed", ["0.2kg", "7 oz", "16,7"])
def test_the_question_refuses_a_tare_in_another_unit(entry, typed):
    """RED: its number box took the digits."""
    page, open_ = entry
    open_("gross")
    press(page, "645", 150)
    _prompt_up(page)
    press(page, typed, 150)
    page.wait_for_timeout(50)
    err = page.evaluate(f"() => document.getElementById('{PROMPT_ID}-err').textContent")
    assert err == f'"{typed}" is not a weight in grams: type grams only, like 167 or 167.5', err
    assert page.evaluate("() => window.__saved.length") == 0
    assert page.evaluate("(id) => !!document.getElementById(id)", PROMPT_ID)
