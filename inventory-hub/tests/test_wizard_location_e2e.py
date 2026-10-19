"""Group 40.7 — browser checks of the wizard's Location move that node's `vm` can't
make: the engine's question opens OVER the open wizard modal (hit-tested, the
z-order a stub DOM can't see), its answer replays on /api/smart_move from the real
page, and closing the wizard cancels the question (its host cascade) with nothing
moved. The save handling itself is pinned hermetically in
test_wizard_location_save_js.py; the server half in
test_wizard_location_through_engine.py.

HERMETIC AGAINST DEV DATA: test_move_result_consumers_e2e.FakeBackend answers every
non-GET synthetically and records it; GET /api/spool_details is served a fake spool
(id 999701); the other GETs (vendors, fields, materials, locations) pass through
read-only. Toast durations are recorded by that file's init script.
"""
from __future__ import annotations

import json
from urllib.parse import urlsplit

from playwright.sync_api import Page

import conftest
from test_move_result_consumers_e2e import (  # noqa: F401  (_drop_routes_in_flight: autouse fixture)
    BOX, TH, FakeBackend, _boot, _drop_routes_in_flight, _toast, _until,
)

SID = 999701
SPOOL = {"id": SID, "location": "FCC-TEST-SHELF", "comment": "", "used_weight": 100, "initial_weight": 1000,
         "spool_weight": 200, "archived": False, "extra": {},
         "filament": {"id": 999702, "name": "FCC Test Black", "material": "PLA", "weight": 1000,
                      "color_hex": "000000", "extra": {}, "vendor": None}}
FED_KEY = f"{TH}#999900"
ASKED = {
    "success": False, "spool_saved": True, "location_moved": False,
    "msg": f"Saved your other changes, but #{SID} was not moved to {BOX}: FCC has to ask first",
    "location_result": {
        "status": "requires_confirm", "confirm_type": "head_fed", "target": BOX, "target_slot": "1",
        "slot_picked": False, "feed": TH, "can_load": True, "can_store": True, "leaving": [], "spools": [SID],
        "fed_heads": [{"toolhead": TH, "printer_name": "FCC Test XL", "box": BOX, "slot": "1",
                       "resident": {"id": 999900, "from": "FCC-TEST-PM", "goes": "back to FCC-TEST-PM"},
                       "residents": [{"id": 999900, "from": "FCC-TEST-PM", "goes": "back to FCC-TEST-PM"}],
                       "confirm_key": FED_KEY}],
        "active_prints": [], "active_print": None,
        "title": f"Load #{SID} onto {TH}?",
        "body": f"{BOX} slot 1 feeds {TH}, and {TH} is running #999900 (from FCC-TEST-PM).",
        "msg": f"{BOX} slot 1 feeds {TH}, and {TH} is running #999900 (from FCC-TEST-PM).",
    },
}
LOADED = {"status": "success", "failures": {}, "auto_deployed_to": TH}

YES_ON_TOP_JS = """() => {
  const b = document.querySelector('#fcc-active-print-confirm-overlay .fcc-apc-yes');
  if (!b) return false;
  const r = b.getBoundingClientRect();
  const top = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
  return !!top && (top === b || b.contains(top));
}"""


class WizardBackend(FakeBackend):
    """FakeBackend plus the fake spool the edit wizard opens on."""

    def _route(self, route):
        req = route.request
        if req.method == "GET" and urlsplit(req.url).path == "/api/spool_details":
            self._json(route, SPOOL)
            return
        super()._route(route)


def _open_edit_and_save(page: Page, base_url: str, reset_dom_state_js: str, be: WizardBackend) -> None:
    _boot(page, base_url, reset_dom_state_js)
    page.wait_for_function("typeof window.openEditWizard === 'function'"
                           " && typeof window.wizardEditLocationNotMoved === 'function'", timeout=10_000)
    page.evaluate("(sid) => { window.openEditWizard(sid); return true; }", SID)
    page.wait_for_function(f"typeof wizardState !== 'undefined' && wizardState.mode === 'edit_spool'"
                           f" && wizardState.editSpoolId === {SID}", timeout=15_000)
    page.evaluate("""([box, th]) => {
        window.wizardComboboxSet('wiz-spool-location-search', 'wiz-spool-location', box, box);
        wizardState.pendingPlacement = { location: box, slot: '1', expected_feed: th };
        window.wizardSubmit();
        return true;
    }""", [BOX, TH])
    _until(page, lambda: be.bodies("/api/edit_spool_wizard"), 8_000, "the wizard's Save sent nothing")
    page.wait_for_selector("#fcc-active-print-confirm-overlay .fcc-apc-yes", state="visible", timeout=8_000)


def test_the_wizards_move_question_opens_over_the_wizard_and_load_replays_on_smart_move(
        page: Page, base_url: str, reset_dom_state_js: str):
    be = WizardBackend(page, responders={"/api/edit_spool_wizard": lambda body: (200, ASKED)},
                       smart_move=lambda body: LOADED)
    _open_edit_and_save(page, base_url, reset_dom_state_js, be)

    sent = be.bodies("/api/edit_spool_wizard")[0]
    assert sent["confirmed_toolheads"] == [] and sent["confirmed_fed_heads"] == [], sent
    assert sent["slot"] == "1" and sent["expected_feed"] == TH and sent["spool_data"]["location"] == BOX, sent
    assert page.evaluate("() => document.getElementById('wizardModal').classList.contains('show')")
    assert page.evaluate(YES_ON_TOP_JS), "the question is under the wizard modal (z-order)"

    page.click("#fcc-active-print-confirm-overlay .fcc-apc-yes")
    _until(page, lambda: be.bodies("/api/smart_move"), 6_000, "Load it instead sent nothing")
    replay = be.bodies("/api/smart_move")[0]
    assert replay["location"] == BOX and replay["spools"] == [SID] and replay["slot"] == "1", replay
    assert replay["confirmed_fed_heads"] == [FED_KEY] and replay["expected_feed"] == TH, replay
    assert replay["origin"] == "wizard_edit", replay
    _toast(page, "no success toast for the replayed move", type_="success",
           contains=(f"#{SID} → {BOX} slot 1 → {TH}",))
    page.wait_for_function("document.getElementById('wiz-status-msg').textContent.includes('Spool Updated')",
                           timeout=5_000)


def test_picking_a_box_in_the_wizards_location_opens_the_slot_picker_and_save_sends_the_slot(
        page: Page, base_url: str, reset_dom_state_js: str):
    """Group 40.7 (Derek's answer 7): the wizard's Location behaves like Force
    Location. Picking a multi-slot box from the dropdown opens the slot picker;
    its choice (the ⭐, slot 3) is held and shown in the field, and Save sends it
    with the edit (`picked_slot`, the tile's feed)."""
    from test_slot_picker_e2e import ROWS as PICKER_ROWS, build_model
    done = {"success": True, "spool_id": SID, "spool_saved": True, "location_moved": True,
            "location_where": f"{BOX} slot 3 → FCCX-3",
            "location_result": {"status": "success", "failures": {}, "auto_deployed_to": "FCCX-3"}}
    be = WizardBackend(page, responders={"/api/edit_spool_wizard": lambda body: (200, done)},
                       extra_locations=list(PICKER_ROWS), placement={BOX: build_model(BOX, spool=SID)})
    _boot(page, base_url, reset_dom_state_js)
    page.wait_for_function("typeof window.openEditWizard === 'function'", timeout=10_000)
    page.evaluate("(sid) => { window.openEditWizard(sid); return true; }", SID)
    page.wait_for_function(f"typeof wizardState !== 'undefined' && wizardState.mode === 'edit_spool'"
                           f" && wizardState.editSpoolId === {SID}", timeout=15_000)
    conftest.wait_modal_settled(page, "wizardModal")
    page.wait_for_function("(wizardState.allLocationRows || []).some(r => r.LocationID === 'FCC-TEST-BOX')",
                           timeout=10_000)
    page.evaluate("() => { document.getElementById('wiz-spool-location-search').focus(); return true; }")
    option = f"#dropdown-location .autocomplete-option[data-value='{BOX}']"
    page.wait_for_selector(option, state="attached", timeout=5_000)
    page.dispatch_event(option, "mousedown")
    page.wait_for_selector("#fcc-slot-picker [data-sp-state='ready']", timeout=10_000)
    page.keyboard.press("Enter")                       # the ⭐: slot 3 (FCCX-3, free and empty)
    page.wait_for_function("wizardState.pendingPlacement && wizardState.pendingPlacement.picked_slot === '3'",
                           timeout=5_000)
    assert f"{BOX} slot 3" in page.input_value("#wiz-spool-location-search")
    page.evaluate("() => { window.wizardSubmit(); return true; }")
    _until(page, lambda: be.bodies("/api/edit_spool_wizard"), 8_000, "the wizard's Save sent nothing")
    sent = be.bodies("/api/edit_spool_wizard")[0]
    assert sent["spool_data"]["location"] == BOX and sent["picked_slot"] == "3", sent
    assert sent["expected_feed"] == "FCCX-3" and "slot" not in sent, sent


def test_closing_the_wizard_cancels_its_open_move_question(
        page: Page, base_url: str, reset_dom_state_js: str):
    be = WizardBackend(page, responders={"/api/edit_spool_wizard": lambda body: (200, ASKED)},
                       smart_move=lambda body: LOADED)
    _open_edit_and_save(page, base_url, reset_dom_state_js, be)

    # The Location isn't saved, so the wizard's unsaved-changes guard would ask
    # first; this is the close it allows (Discard & Close sets the same flag).
    # Bootstrap drops a hide() while the modal is still fading in, and with every
    # request stubbed the question arrives within that fade (CLAUDE.md, Group
    # 45.8): wait for the show transition first.
    conftest.wait_modal_settled(page, "wizardModal")
    page.evaluate("() => { wizardState.forceClose = true; window.modals.wizardModal.hide(); return true; }")
    page.wait_for_selector("#fcc-active-print-confirm-overlay", state="detached", timeout=6_000)
    page.wait_for_timeout(300)
    assert be.bodies("/api/smart_move") == [], json.dumps(be.posts)
