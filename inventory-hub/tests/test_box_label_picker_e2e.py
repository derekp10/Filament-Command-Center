"""Group 40.2 — a multi-slot box's own label, scanned with spools in the buffer,
opens the slot picker (Derek's D2.1), in a real browser over stubbed data.

HERMETIC AGAINST DEV DATA: test_slot_picker_e2e's PickerStub answers the
picker's model (built by the REAL placement.build_placement_options over fixed
rows), the location scan (/api/identify_scan answers the box as a location),
the move (/api/smart_move, recorded, never forwarded) and the buffer (the page's
own, never dev's shared one). The box row is added to the page's location list
only. The loop's logic is pinned hermetically in test_box_label_picker_js.py;
this file checks the real picker and the real door together.

HEAD proof (d8f6128): there the label posts the whole buffer to /api/smart_move
with no slot and no picker opens, so every test here fails.
"""
from __future__ import annotations

import pytest
from playwright.sync_api import expect

from test_slot_picker_e2e import CHOICE, READY, SPOOLS, _sp, build_model, picker_page  # noqa: F401  (fixture)

pytestmark = pytest.mark.usefixtures("require_server")

BOX_ROW = {"LocationID": "FCC-TEST-BOX", "Name": "FCC-TEST-BOX (test)", "Type": "Dryer Box", "Max Spools": "4"}
TWO = SPOOLS + [_sp(999203, "FCC-TEST-SHELF", name="Test Purple", color="7722cc")]


def _model(spools=SPOOLS):
    """The real model for whichever spool the picker asks about."""
    return lambda q: build_model("FCC-TEST-BOX", spools=spools, spool=int(q["spool"]) if q.get("spool") else None)


def _location_answer(body):
    if str(body.get("text", "")).upper() == "LOC:FCC-TEST-BOX":
        return {"type": "location", "id": "FCC-TEST-BOX", "contents": []}
    return None


def _buffer(ids):
    return [{"id": i, "display": f"#{i}", "color": "cc2222"} for i in ids]


def _start(page, setup, ids, moves, spools=SPOOLS):
    """Install the stub, buffer `ids`, add the box row to the page, and scan its label."""
    answers = {"/api/identify_scan": _location_answer, "/api/smart_move": lambda body: moves.pop(0)}
    stub = setup({"FCC-TEST-BOX": _model(spools)}, answers=answers, buffer=_buffer(ids))
    # The page's first location load must have landed, or it replaces the row
    # added below (state.allLocations starts as an empty array).
    page.wait_for_function("() => Array.isArray(state.allLocations) && state.allLocations.length > 0",
                           timeout=15_000)
    page.evaluate("""([row, held]) => {
        state.allLocations = state.allLocations.filter(l => l.LocationID !== row.LocationID).concat([row]);
        window.lastLocalBufferChange = Date.now();
        state.heldSpools = held;
        if (window.renderBuffer) window.renderBuffer();
    }""", [BOX_ROW, _buffer(ids)])
    page.evaluate("() => processScan('LOC:FCC-TEST-BOX', 'barcode')")
    return stub


def _held(page):
    return page.evaluate("() => state.heldSpools.map(s => s.id)")


def test_a_box_label_opens_the_picker_and_enter_places_the_spool_in_the_star(picker_page):
    page, setup, _open = picker_page
    stub = _start(page, setup, [999201], [{"status": "success", "failures": {}, "auto_deployed_to": "FCCX-3"}])
    page.wait_for_selector(READY, timeout=10_000)
    expect(page.locator("#fcc-slot-picker")).to_contain_text("Which slot of FCC-TEST-BOX should #999201 go in?")
    page.keyboard.press("Enter")                         # the ⭐: slot 3, feeds FCCX-3
    page.wait_for_function("() => state.heldSpools.length === 0", timeout=10_000)
    moves = stub.posted("/api/smart_move")
    assert moves == [{"location": "FCC-TEST-BOX", "spools": [999201], "slot": None, "origin": "buffer",
                      "confirmed_toolheads": [], "confirmed_fed_heads": [],
                      "picked_slot": "3", "expected_feed": "FCCX-3"}], moves


def test_two_buffered_spools_get_a_picker_each_and_escape_keeps_the_rest(picker_page):
    page, setup, _open = picker_page
    stub = _start(page, setup, [999201, 999203], [{"status": "success", "failures": {}}], spools=TWO)
    page.wait_for_selector(READY, timeout=10_000)
    expect(page.locator("#fcc-slot-picker .fcc-sp-step")).to_have_text("1 of 2")
    page.keyboard.press("Enter")
    expect(page.locator("#fcc-slot-picker .fcc-sp-step")).to_have_text("2 of 2", timeout=10_000)
    page.wait_for_selector(READY, timeout=10_000)
    expect(page.locator("#fcc-slot-picker")).to_contain_text("should #999203 go in?")
    page.keyboard.press("Escape")
    expect(page.locator("#fcc-slot-picker")).to_have_count(0)
    assert [m["spools"] for m in stub.posted("/api/smart_move")] == [[999201]]
    assert _held(page) == [999203]
    toasts = page.evaluate("() => window.__toastLog")
    assert any(t["text"] == "📦 FCC-TEST-BOX: #999201 → slot 3; #999203 stays in your buffer" for t in toasts), toasts


def test_cancel_on_the_load_question_steps_back_to_the_picker(picker_page):
    """Slot 1's head runs a PolyDryer spool: the server asks the three-way
    question; Cancel brings the picker back for the same spool."""
    page, setup, _open = picker_page
    fed = {"status": "requires_confirm", "confirm_type": "head_fed", "target": "FCC-TEST-BOX",
           "fed_heads": [{"toolhead": "FCCX-1", "printer_name": "FCC Test XL", "box": "FCC-TEST-BOX", "slot": "1",
                          "resident": {"id": 999299, "from": "FCC-TEST-PM", "goes": "back to FCC-TEST-PM"},
                          "residents": [{"id": 999299, "from": "FCC-TEST-PM", "goes": "back to FCC-TEST-PM"}],
                          "confirm_key": "FCCX-1#999299"}],
           "active_prints": [], "active_print": None, "can_store": True, "can_load": True,
           "target_slot": "1", "slot_picked": True, "feed": "FCCX-1", "spools": [999201], "leaving": [],
           "title": "Load #999201 onto FCCX-1?",
           "body": "FCC-TEST-BOX slot 1 feeds FCCX-1, and FCCX-1 is running #999299 (from FCC-TEST-PM).",
           "msg": "FCC-TEST-BOX slot 1 feeds FCCX-1, and FCCX-1 is running #999299 (from FCC-TEST-PM)."}
    stub = _start(page, setup, [999201], [fed])
    page.wait_for_selector(READY, timeout=10_000)
    page.locator("#fcc-slot-picker .fcc-sp-tile[data-sp-slot='1']").click()
    question = page.locator(".fcc-apc-panel")
    expect(question).to_contain_text("Load #999201 onto FCCX-1?", timeout=10_000)
    question.locator(".fcc-apc-no").click()
    page.wait_for_selector(READY, timeout=10_000)       # the same spool's picker, again
    expect(page.locator("#fcc-slot-picker")).to_contain_text("should #999201 go in?")
    page.keyboard.press("Escape")
    expect(page.locator("#fcc-slot-picker")).to_have_count(0)
    assert len(stub.posted("/api/smart_move")) == 1 and _held(page) == [999201]


def test_swap_into_an_occupied_slot_puts_its_old_spool_in_the_buffer(picker_page):
    page, setup, _open = picker_page
    stub = _start(page, setup, [999201], [{"status": "success", "failures": {}}])
    page.wait_for_selector(READY, timeout=10_000)
    page.locator("#fcc-slot-picker .fcc-sp-tile[data-sp-slot='2']").click()
    page.wait_for_selector(CHOICE, timeout=5_000)
    page.locator("#fcc-slot-picker [data-sp-choice='swap']").click()
    page.wait_for_function("() => state.heldSpools.length === 1 && state.heldSpools[0].id === 999202",
                           timeout=10_000)
    move = stub.posted("/api/smart_move")[0]
    assert move["slot"] == "2" and "picked_slot" not in move and move["expected_feed"] == "FCCX-2", move
