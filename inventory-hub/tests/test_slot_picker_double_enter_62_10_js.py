"""Group 62.10: the slot picker ignores a scanner's second Enter, hermetic.

A scanner whose end-of-scan key sends two Enters (CR LF arriving as two keydowns)
puts a second Enter right behind the scan's own. Everywhere else FCC reads an Enter
under 100 ms after a scan's Enter as the scan's (`window.enterIsAScan`,
`state.lastScanEnterAt`, Group 50's review), but the slot picker's own rule,
`_enterIsAScans` (slot_picker.js), never got that clause. Its key handler listens in
the capture phase, so it hears each Enter before the scan accumulator does, and the
second one found an empty buffer and read as a person's:
- after a scan the picker refused, it picked the highlighted ⭐ slot (the grid), or
  answered the occupied slot's question with its first button (Swap);
- after an occupied slot's own label, which opens that question, it answered it:
  Swap for a stored spool, "Swap it out" for the slot's spool loaded on its head.

Derek can't tell whether his scanner sends CR, LF or CR LF (2026-11-17); the rule
assumes neither: one Enter changes nothing, and a doubled one loses its second.

Runs the REAL scan accumulator (scripts.html's keydown block, as
test_slow_scan_slash_js.py lifts it), the REAL processScan (inv_cmd.js) and the REAL
overlay_mount.js, inv_core.js and slot_picker.js in `isolated_page` (no network), with
every key typed on a fake clock, so it runs under --offline. RED on 761359a for every
doubled-Enter case; the person's Enter after the window is the control.
"""
from __future__ import annotations

import pytest

from test_slow_scan_confirms_js import BOX_MODEL, MODULES, PICKER_SCAN_STUBS, _SLOTS
from test_slow_scan_slash_js import TYPE_JS, _accumulator

SPEEDS = [1, 8, 40]          # ms a key, so the second Enter lands 1 to 40 ms after the first

STORED = dict(_SLOTS[1], free=False, occupant_state="stored", claimants=[60], swap_to="",
              spool={"id": 60, "display": "PLA Red", "color": "ff0000"})
ON_FEED = dict(_SLOTS[2], free=False, occupant_state="on_feed", claimants=[61],
               feeds={"kind": "toolhead", "id": "XL-1", "printer": "XL", "residents": []},
               spool={"id": 61, "display": "PETG Blue", "color": "0000ff", "deployed_to": "XL-1", "is_ghost": True})
OCCUPIED_MODEL = dict(BOX_MODEL, slots=[_SLOTS[0], STORED, ON_FEED, _SLOTS[3]])


@pytest.fixture
def picker(isolated_page):
    """The page, and open_(model): the picker opened for CR-MDB-1 on `model`,
    its slots drawn and the ⭐ (slot 1) highlighted."""
    page = isolated_page
    page.set_content("<!doctype html><html><head><meta charset='utf-8'></head><body></body></html>")
    page.add_script_tag(content=PICKER_SCAN_STUBS)
    for name in ("overlay_mount.js", "inv_core.js", "ui_builder.js", "slot_picker.js", "inv_cmd.js"):
        page.add_script_tag(content=(MODULES / name).read_text(encoding="utf-8"))
    page.add_script_tag(content="window.setInterval = window.__si;")
    page.add_script_tag(content=_accumulator())          # last, as on the page
    page.evaluate(TYPE_JS, ["", 0, False, {}])            # the fake clock, before anything is typed

    def open_(model=BOX_MODEL):
        page.evaluate("(m) => { window.__models = m; }", {"CR-MDB-1": model})
        page.evaluate("""() => { window.__picked = undefined;
            window.openSlotPicker({ location: 'CR-MDB-1', spool: 6 }).then((r) => { window.__picked = r; }); }""")
        page.wait_for_function("() => document.querySelectorAll('#fcc-slot-picker .fcc-sp-tile').length > 0")
        page.wait_for_function("""() => { const a = document.activeElement;
            return !!(a && a.classList.contains('fcc-sp-tile') && a.classList.contains('kb-active')); }""")

    return page, open_


def _type(page, keys, ms):
    """Keys on the fake clock, `ms` apart: a string's characters, then each named key."""
    page.evaluate(TYPE_JS, [keys, ms, False, {}])


def _scan_twice_entered(page, text, ms):
    """A scan whose end-of-scan key arrives as two Enters, `ms` apart."""
    _type(page, list(text) + ["Enter", "Enter"], ms)


def _person_enter(page):
    """A person's Enter, well after the scan's (the fake clock moves 300 ms)."""
    page.evaluate("() => { window.__T += 300; }")
    _type(page, ["Enter"], 0)


def _seen(page):
    return page.evaluate("""() => ({
        open: !!document.getElementById('fcc-slot-picker'),
        view: (document.querySelector('#fcc-slot-picker .fcc-sp-panel') || {}).dataset
            ? document.querySelector('#fcc-slot-picker .fcc-sp-panel').dataset.spState : null,
        picked: window.__picked === undefined ? 'open'
            : (window.__picked === null ? 'cancelled'
                : { slot: window.__picked.slot, choice: window.__picked.choice || null }),
        // What went to the server, less the Activity Log lines a refusal writes.
        posts: window.__posts.map((p) => p.url).filter((u) => u !== '/api/log_event') })""")


@pytest.mark.parametrize("ms", SPEEDS)
def test_a_refused_scans_second_enter_never_picks_the_star(picker, ms):
    """Another box's slot label is refused; its second Enter must not pick the
    highlighted ⭐ (slot 1). RED on 761359a: the picker resolved with slot 1."""
    page, open_ = picker
    open_()
    _scan_twice_entered(page, "LOC:LR-MDB-1:SLOT:2", ms)
    page.wait_for_timeout(150)
    s = _seen(page)
    assert s["open"] and s["picked"] == "open" and s["view"] == "ready", (ms, s)
    assert s["posts"] == [], s
    # Control: a person's Enter, after the window, still picks the ⭐.
    _person_enter(page)
    page.wait_for_function("() => window.__picked !== undefined")
    assert _seen(page)["picked"] == {"slot": "1", "choice": None}


@pytest.mark.parametrize("ms", SPEEDS)
def test_a_refused_scans_second_enter_never_answers_the_slots_question(picker, ms):
    """Slot 2 (holding #60) clicked: the picker asks Swap / Overwrite / Back, with
    Swap focused. A scan it refuses there; its second Enter must not answer Swap.
    RED on 761359a: the picker resolved with choice 'swap'."""
    page, open_ = picker
    open_(OCCUPIED_MODEL)
    page.click("#fcc-slot-picker .fcc-sp-tile[data-sp-idx='1']")
    page.wait_for_selector("#fcc-slot-picker .fcc-sp-panel[data-sp-state='choice']")
    page.wait_for_function("() => document.activeElement && document.activeElement.dataset.spChoice === 'swap'")
    _scan_twice_entered(page, "ID:57", ms)
    page.wait_for_timeout(150)
    s = _seen(page)
    assert s["open"] and s["picked"] == "open" and s["view"] == "choice", (ms, s)
    assert s["posts"] == [], s
    # Control: a person's Enter on Swap answers it.
    _person_enter(page)
    page.wait_for_function("() => window.__picked !== undefined")
    assert _seen(page)["picked"] == {"slot": "2", "choice": "swap"}


@pytest.mark.parametrize("ms", SPEEDS)
@pytest.mark.parametrize("slot, choice", [pytest.param("2", "swap", id="stored"),
                                          pytest.param("3", "swap_out", id="on-feed")])
def test_an_occupied_slots_label_opens_its_question_and_the_second_enter_answers_nothing(picker, ms, slot, choice):
    """An occupied slot's own label scanned: the picker asks what happens to its
    spool, the first button focused (Swap for a stored #60; "Swap it out" for #61,
    loaded on XL-1, which the slot feeds). The scan's second Enter must leave the
    question up. RED on 761359a: it answered the first button."""
    page, open_ = picker
    open_(OCCUPIED_MODEL)
    _scan_twice_entered(page, f"LOC:CR-MDB-1:SLOT:{slot}", ms)
    page.wait_for_timeout(150)
    s = _seen(page)
    assert s["open"] and s["picked"] == "open" and s["view"] == "choice", (ms, s)
    assert page.evaluate("() => document.activeElement && document.activeElement.dataset.spChoice") == choice
    assert s["posts"] == [], s
    # Control: a person's Enter on the focused button answers it.
    _person_enter(page)
    page.wait_for_function("() => window.__picked !== undefined")
    assert _seen(page)["picked"] == {"slot": slot, "choice": choice}


def test_one_enter_still_picks_a_scanned_free_slot(picker):
    """A scanner that sends one Enter: a free slot's label picks it, as before."""
    page, open_ = picker
    open_()
    _type(page, list("LOC:CR-MDB-1:SLOT:3") + ["Enter"], 1)
    page.wait_for_function("() => window.__picked !== undefined")
    assert _seen(page)["picked"] == {"slot": "3", "choice": None}
