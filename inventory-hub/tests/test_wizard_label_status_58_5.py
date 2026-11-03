"""Group 58.5: a wizard Save never writes a label status the user didn't set.

Reproduced on dev before the fix (2026-11-01, a real page, the POST read and not
sent): Edit Spool on spool #2, whose filament has no `needs_label_print`, with
nothing touched, sent `filament_data.extra.needs_label_print: false`. That write
reads as "✅ Confirmed" in the filament window, on a filament nobody had
scanned. The box has two states and the status three, and it was sent as drawn. A
new filament was worse off: the server flags one for the 🏷️ Backlog only when the
key is left out, and the box always sent it.

The rule now: the box is sent only when the user changed it
(`wizardExtraTouched('fil', 'needs_label_print')`), and a deliberate untick still
sends false, which the server honours (test_print_queue.py).

`sample_printed` is its twin (Group 58's review; reproduced the same way on
2026-11-02: an untouched box sent `sample_printed: false`). The filament window reads
it in three states too (Yes / No / unknown), so every Save turned "unknown" into "No"
on a filament nobody had looked at. The same gate, and the same cases.

Hermetic and page-level: the REAL modals_wizard.html, overlay_mount.js, inv_core.js,
choice_validation.js, weight_utils.js, empty_weight_field.js and inv_wizard.js in
`isolated_page` (no network), so it runs under --offline. Clicks are real clicks on
the real checkbox, and Save is the real button. `fetch` answers from the shapes
dev answered on 2026-11-01. Only Bootstrap is a stand-in (the page has no CDN):
show() and hide() on the modal, which no case here turns on.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

HUB = Path(__file__).resolve().parent.parent
MODULES = HUB / "static" / "js" / "modules"
WIZARD_HTML = HUB / "templates" / "components" / "modals_wizard.html"
BOX = "#wiz_fil_ef_needs_label_print"
SAMPLE_BOX = "#wiz_fil_ef_sample_printed"

# /api/external/fields, cut down to the fields that matter here.
FIELDS = {"success": True, "fields": {
    "filament": [
        {"entity_type": "filament", "field_type": "text", "key": "drying_temp", "name": "Drying Temp", "order": 10},
        {"entity_type": "filament", "field_type": "boolean", "key": "needs_label_print",
         "name": "Needs Label Print", "order": 14},
        {"entity_type": "filament", "field_type": "boolean", "key": "sample_printed",
         "name": "Sample Printed", "order": 15},
    ],
    "spool": [
        {"entity_type": "spool", "field_type": "text", "key": "original_color", "name": "Original Color", "order": 7},
    ],
}}


def _spool_details(filament_extra):
    """/api/spool_details for dev's spool #2, whose filament's `extra` is the case."""
    return {
        "archived": False, "extra": {"is_refill": False}, "id": 57, "initial_weight": 1000.0,
        "location": "SHELF-1", "registered": "2026-02-11T04:07:24Z", "remaining_length": 167641.8,
        "remaining_weight": 500.0, "spool_weight": 0.0, "tags": [], "used_length": 167641.8, "used_weight": 500.0,
        "filament": {
            "color_hex": "72071C", "comment": "", "density": 1.24, "diameter": 1.75, "external_id": "3",
            "extra": filament_extra, "id": 7, "material": "PLA", "name": "Red", "price": 0.0,
            "registered": "2026-02-11T04:07:24Z", "settings_bed_temp": 30, "settings_extruder_temp": 210,
            "spool_weight": 0.0, "tags": [], "weight": 1000.0,
            "vendor": {"extra": {}, "id": 2, "name": "Some Brand", "registered": "2026-02-11T04:07:24Z"},
        },
    }


PRELUDE = r"""
window.__pendingShortcuts = [];
window.registerShortcut = function (s) { window.__pendingShortcuts.push(s); };
window.__posts = [];
window.__answers = {};
window.__errors = [];
window.addEventListener('error', (e) => window.__errors.push(String(e.message)));
window.addEventListener('unhandledrejection', (e) => window.__errors.push(String(e.reason)));
window.fetch = function (url, opts) {
    url = String(url);
    const method = (opts && opts.method) || 'GET';
    if (method !== 'GET') window.__posts.push({ url, body: opts.body ? JSON.parse(opts.body) : null });
    let body = { success: true };
    const path = url.split('?')[0];
    if (path in window.__answers) body = window.__answers[path];
    return Promise.resolve({ ok: true, status: 200,
        json: () => Promise.resolve(JSON.parse(JSON.stringify(body))) });
};
// The page has no CDN: the wizard's modal shows and hides, nothing more.
class FakeModal {
    constructor(el) { this.el = el; }
    show() { this.el.classList.add('show'); }
    hide() { this.el.classList.remove('show'); }
    static getInstance() { return null; }
}
window.bootstrap = { Modal: FakeModal };
"""


@pytest.fixture
def wizard(isolated_page):
    page = isolated_page
    page.set_content('<!doctype html><html><head><meta charset="utf-8"></head><body>'
                     '<div id="toast-container"></div>' + WIZARD_HTML.read_text(encoding="utf-8")
                     + '</body></html>')
    page.add_script_tag(content=PRELUDE)
    for name in ("overlay_mount.js", "inv_core.js", "choice_validation.js", "weight_utils.js",
                 "empty_weight_field.js", "inv_wizard.js"):
        page.add_script_tag(content=(MODULES / name).read_text(encoding="utf-8"))
    page.evaluate("""(a) => { Object.assign(window.__answers, a); }""", {
        "/api/external/fields": FIELDS,
        "/api/external/vendors": {"success": True, "vendors": [{"id": 2, "name": "Some Brand", "extra": {}}]},
        "/api/locations": [{"LocationID": "SHELF-1", "Name": "Shelf", "Type": "Section"}],
        "/api/filaments": {"success": True, "filaments": []},
        "/api/edit_spool_wizard": {"success": True, "spool_id": 57},
        "/api/create_inventory_wizard": {"success": True, "created_spools": [58], "filament_id": 7},
    })
    return page


def _open_edit(page, filament_extra):
    page.evaluate("(d) => { window.__answers['/api/spool_details'] = d; }", _spool_details(filament_extra))
    # Not awaited: openEditWizard holds no answer the test needs, and the states
    # are waited on below.
    page.evaluate("() => { window.openEditWizard(57); }")
    page.wait_for_function("() => wizardState.mode === 'edit_spool' && wizardState.selectedFilamentId === 7"
                           " && !!document.getElementById('wiz_fil_ef_needs_label_print')"
                           " && document.getElementById('wiz-fil-color_name').value === 'Red'"
                           " && !document.getElementById('btn-wiz-submit').disabled")


def _open_new_filament(page):
    page.evaluate("() => window.openWizardModal()")
    page.wait_for_function("() => !!document.getElementById('wiz_fil_ef_needs_label_print')")
    page.evaluate("() => wizardSelectType('manual')")
    page.locator("#wiz-fil-color_name").fill("Test Red")
    page.locator("#wiz-fil-material").fill("PLA")


def _save(page, url):
    """Press the real Save and answer with what it posted to `url`."""
    page.locator("#btn-wiz-submit").click()
    page.wait_for_function("(u) => window.__posts.some((p) => p.url === u)", arg=url)
    sent = page.evaluate("(u) => window.__posts.filter((p) => p.url === u)", url)
    assert len(sent) == 1, sent
    assert page.evaluate("window.__errors") == []
    return sent[0]["body"]


def _touched(page):
    return page.evaluate("() => Array.from(wizardState.touchedExtras)")


EDIT = "/api/edit_spool_wizard"
CREATE = "/api/create_inventory_wizard"


def test_an_edit_of_a_filament_with_no_status_sends_no_status(wizard):
    """Case 1, the reproduction: nothing touched, nothing written. RED before the
    fix: `needs_label_print: false`, a false "confirmed"."""
    _open_edit(wizard, {"filament_attributes": ["Matte"]})
    assert wizard.locator(BOX).is_checked() is False        # drawn unticked: it says nothing
    extra = _save(wizard, EDIT)["filament_data"]["extra"]
    assert "needs_label_print" not in extra, extra


def test_a_new_filament_leaves_the_status_to_the_server(wizard):
    """Case 2: the key left out, so the server's own rule flags it for the Backlog
    (routes_inventory.py: `if 'needs_label_print' not in extra`). RED before the
    fix: false, so a new filament never reached the Backlog."""
    _open_new_filament(wizard)
    data = _save(wizard, CREATE)["filament_data"]
    assert data["name"] == "Test Red"                       # this really is the new-filament path
    assert "needs_label_print" not in data["extra"], data["extra"]


def test_ticking_the_box_sends_true(wizard):
    """Case 3: a person's tick, by a real click, reaches the touched set."""
    _open_edit(wizard, {})
    wizard.locator(BOX).check()
    assert _touched(wizard) == ["fil:needs_label_print"]
    assert _save(wizard, EDIT)["filament_data"]["extra"]["needs_label_print"] is True


def test_ticking_then_unticking_sends_false(wizard):
    """Case 4: a deliberate "this label is fine" stays possible."""
    _open_edit(wizard, {})
    wizard.locator(BOX).check()
    wizard.locator(BOX).uncheck()
    assert _touched(wizard) == ["fil:needs_label_print"]
    assert _save(wizard, EDIT)["filament_data"]["extra"]["needs_label_print"] is False


def test_a_new_filament_can_still_be_ticked_or_unticked(wizard):
    """Cases 3 and 4 on a create."""
    _open_new_filament(wizard)
    wizard.locator(BOX).check()
    wizard.locator(BOX).uncheck()
    assert _save(wizard, CREATE)["filament_data"]["extra"]["needs_label_print"] is False


@pytest.mark.parametrize("stored,ticked", [(True, True), ("true", True), (False, False), ("false", False)])
def test_an_edit_leaves_a_stored_status_alone(wizard, stored, ticked):
    """A status on record is drawn as it stands, and an untouched box leaves it: a
    key left out is kept by the server's read-merge and by Spoolman 0.26+."""
    _open_edit(wizard, {"needs_label_print": stored})
    assert wizard.locator(BOX).is_checked() is ticked
    extra = _save(wizard, EDIT)["filament_data"]["extra"]
    assert "needs_label_print" not in extra, extra


def test_unticking_a_stored_true_sends_false(wizard):
    """The box drawn ticked, unticked by a person: "labelled now"."""
    _open_edit(wizard, {"needs_label_print": True})
    wizard.locator(BOX).uncheck()
    assert _save(wizard, EDIT)["filament_data"]["extra"]["needs_label_print"] is False


def test_the_next_wizard_session_forgets_a_touch(wizard):
    """A tick in one session says nothing about the next filament edited."""
    _open_edit(wizard, {})
    wizard.locator(BOX).check()
    assert _touched(wizard) == ["fil:needs_label_print"]
    _open_edit(wizard, {})
    assert _touched(wizard) == []
    extra = _save(wizard, EDIT)["filament_data"]["extra"]
    assert "needs_label_print" not in extra, extra


def test_an_edit_of_a_filament_with_no_swatch_status_sends_none(wizard):
    """The twin's case 1, the reproduction: nothing touched, nothing written. RED on
    1f8e03a: `sample_printed: false`, "No" on a filament whose status is unknown."""
    _open_edit(wizard, {"filament_attributes": ["Matte"]})
    assert wizard.locator(SAMPLE_BOX).is_checked() is False
    extra = _save(wizard, EDIT)["filament_data"]["extra"]
    assert "sample_printed" not in extra, extra


def test_a_new_filament_writes_no_swatch_status(wizard):
    """The twin's case 2: nobody has said, so the filament window reads "unknown". RED on
    1f8e03a: false."""
    _open_new_filament(wizard)
    data = _save(wizard, CREATE)["filament_data"]
    assert data["name"] == "Test Red"
    assert "sample_printed" not in data["extra"], data["extra"]


def test_ticking_the_swatch_box_sends_true(wizard):
    """The twin's case 3. A pin: proved on a copy that never sends the box."""
    _open_edit(wizard, {})
    wizard.locator(SAMPLE_BOX).check()
    assert _touched(wizard) == ["fil:sample_printed"]
    assert _save(wizard, EDIT)["filament_data"]["extra"]["sample_printed"] is True


def test_ticking_then_unticking_the_swatch_box_sends_false(wizard):
    """The twin's case 4: a deliberate "no swatch" stays possible. A pin, as above."""
    _open_edit(wizard, {})
    wizard.locator(SAMPLE_BOX).check()
    wizard.locator(SAMPLE_BOX).uncheck()
    assert _touched(wizard) == ["fil:sample_printed"]
    assert _save(wizard, EDIT)["filament_data"]["extra"]["sample_printed"] is False


def test_a_new_filament_can_still_say_either_about_its_swatch(wizard):
    """Cases 3 and 4 on a create. A pin, as above."""
    _open_new_filament(wizard)
    wizard.locator(SAMPLE_BOX).check()
    assert _save(wizard, CREATE)["filament_data"]["extra"]["sample_printed"] is True


@pytest.mark.parametrize("stored,ticked", [(True, True), ("true", True), (False, False), ("false", False)])
def test_an_edit_leaves_a_stored_swatch_status_alone(wizard, stored, ticked):
    """A status on record is drawn as it stands, and an untouched box leaves it. A key left
    out is kept by the server's read-merge and by Spoolman 0.26+."""
    _open_edit(wizard, {"sample_printed": stored})
    assert wizard.locator(SAMPLE_BOX).is_checked() is ticked
    extra = _save(wizard, EDIT)["filament_data"]["extra"]
    assert "sample_printed" not in extra, extra


def test_unticking_a_stored_swatch_status_sends_false(wizard):
    """The box drawn ticked, unticked by a person: the swatch is gone. A pin, as above."""
    _open_edit(wizard, {"sample_printed": True})
    wizard.locator(SAMPLE_BOX).uncheck()
    assert _save(wizard, EDIT)["filament_data"]["extra"]["sample_printed"] is False


def test_a_touch_of_one_box_says_nothing_about_the_other(wizard):
    """Each box answers for itself. A pin, as above."""
    _open_edit(wizard, {})
    wizard.locator(SAMPLE_BOX).check()
    extra = _save(wizard, EDIT)["filament_data"]["extra"]
    assert extra["sample_printed"] is True, extra
    assert "needs_label_print" not in extra, extra


def test_the_rule_is_only_the_three_state_boxes(wizard):
    """Control: an extra with two states of its own still goes out as drawn, and so does
    the spool's own boolean, so this changes the two keys it names. A pin: proved on a
    copy that gates every box."""
    fields = json.loads(json.dumps(FIELDS))
    fields["fields"]["filament"].append({"entity_type": "filament", "field_type": "boolean", "key": "fcc_test_flag",
                                         "name": "A test flag", "order": 16})
    fields["fields"]["spool"].append({"entity_type": "spool", "field_type": "boolean", "key": "is_refill",
                                      "name": "Is Refill", "order": 8})
    wizard.evaluate("(a) => { window.__answers['/api/external/fields'] = a; }", fields)
    _open_edit(wizard, {})
    body = _save(wizard, EDIT)
    assert body["filament_data"]["extra"]["fcc_test_flag"] is False, body
    assert body["spool_data"]["extra"]["is_refill"] is False, body


@pytest.mark.usefixtures("require_server")
def test_the_real_page_sends_no_status_for_an_untouched_box(page, base_url):
    """The reproduction as a test: the real dashboard and real Bootstrap. Dev's
    spool data is a stub, and Save's POST is read and answered in the browser, so
    nothing reaches dev."""
    from test_text_size_guard import _read_only

    seen = []

    def grab(route):
        seen.append(route.request.post_data_json)
        route.fulfill(status=200, content_type="application/json", body='{"success": true, "spool_id": 57}')

    _read_only(page, extra_get={"/api/spool_details": _spool_details({})})
    page.route("**/api/edit_spool_wizard", grab)
    page.goto(base_url)
    page.wait_for_function("() => typeof window.openEditWizard === 'function' && typeof state !== 'undefined'"
                           " && state.locationsLoaded", timeout=45_000)
    page.evaluate("() => { window.openEditWizard(57); }")
    page.wait_for_function("() => wizardState.mode === 'edit_spool' && !!document.getElementById('wiz_fil_ef_needs_label_print')"
                           " && !document.getElementById('btn-wiz-submit').disabled", timeout=15_000)
    assert page.locator(BOX).is_checked() is False
    assert page.locator(SAMPLE_BOX).is_checked() is False
    with page.expect_response("**/api/edit_spool_wizard"):
        page.locator("#btn-wiz-submit").click()
    assert len(seen) == 1, seen
    assert "needs_label_print" not in seen[0]["filament_data"]["extra"], seen[0]
    assert "sample_printed" not in seen[0]["filament_data"]["extra"], seen[0]


def test_the_new_filament_payload_is_flagged_by_the_real_server_rule():
    """The other half of case 2: the page's payload through the REAL route. With the
    key left out the filament is created flagged, so it reaches the Backlog; with
    a false (what the page sent before the fix) it isn't."""
    from unittest.mock import patch

    import app as app_module
    import spoolman_api

    client = app_module.app.test_client()
    made = []

    def create_filament(data):
        made.append(json.loads(json.dumps(data)))
        return {"id": 7}

    with patch.object(spoolman_api, "create_filament", side_effect=create_filament), \
            patch.object(spoolman_api, "create_spool", return_value={"id": 58}):
        for extra in ({}, {"needs_label_print": False}):
            res = client.post("/api/create_inventory_wizard", json={
                "filament_data": {"name": "Test Red", "material": "PLA", "extra": extra},
                "spool_data": {"used_weight": 0, "location": "", "extra": {}},
                "quantity": 1, "placements": [None]})
            assert res.get_json()["success"] is True
    assert made[0]["extra"]["needs_label_print"] is True
    assert made[1]["extra"]["needs_label_print"] is False
