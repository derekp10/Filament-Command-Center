"""Source-presence regression guards for frontend wiring.

Moved here from the legacy project-root `tests/` directory (2026-05-12, Group
16.1). These are brittle grep-style checks that pin specific strings in
templates / JS modules / app.py so deletions don't slip past unnoticed. They
complement, but don't replace, the e2e tests — they exist as cheap canaries
for invariants the e2e tests don't directly assert.
"""
import os


# Paths are relative to inventory-hub/tests/, so one ".." reaches inventory-hub/
_HUB = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _read(*parts):
    path = os.path.join(_HUB, *parts)
    assert os.path.exists(path), f"missing: {path}"
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def test_modal_interceptor_exists():
    """Ensures scripts.html contains a global Bootstrap modal event listener
    that resets the deck modes when any modal opens."""
    content = _read("templates", "components", "scripts.html")
    assert "show.bs.modal" in content, "Missing global modal open interceptor"
    assert "resetCommandModes" in content, "Missing resetCommandModes logic in modal interceptor"


def test_reset_command_modes_exists():
    """Ensures inv_cmd.js contains the resetCommandModes() function to turn
    off dropMode and ejectMode."""
    content = _read("static", "js", "modules", "inv_cmd.js")
    assert "const resetCommandModes = () =>" in content or "window.resetCommandModes = () =>" in content
    assert "state.dropMode = false" in content
    assert "state.ejectMode = false" in content
    assert "updateDeckVisuals()" in content


def test_nosleep_video_injected():
    """Ensures scripts.html loads the NoSleep fallback to bypass laptop screen timeouts."""
    content = _read("templates", "components", "scripts.html")
    assert "NoSleep.min.js" in content


def test_request_wakelock_fallback():
    """Ensures inv_core.js initiates the NoSleep fallback polyfill on user
    click if the native navigator.wakelock fails."""
    content = _read("static", "js", "modules", "inv_core.js")
    assert "window.NoSleep" in content
    assert "noSleepInstance.enable()" in content or "noSleep.enable()" in content


def test_location_list_features_exist():
    """Ensures Location List has the explicit sorting logic and column
    definitions in place (Glow-up feature)."""
    js_content = _read("static", "js", "modules", "inv_core.js")
    assert "state.locSortBy" in js_content, "Missing sorting state injection for Location List"
    assert "window.sortLocations =" in js_content, "Missing sortLocations handler"
    assert "Unassigned" in js_content, "Missing Unassigned fall-back injection"

    html_content = _read("templates", "components", "modals_loc_mgr.html")
    assert "onclick=\"sortLocations('LocationID')\"" in html_content, "Missing column sorting UI binds"
    assert "locQrViewModal" in html_content, "Missing QR Overlay in Loc Mgr Modal"


def test_quick_weigh_triggers_in_ui_builder():
    """Ensures that window.openQuickWeigh is bound in the card builder."""
    content = _read("static", "js", "modules", "ui_builder.js")
    assert "window.openQuickWeigh" in content, "Missing quick weigh trigger in UI builder"


def test_inv_weigh_out_logic_exists():
    """Ensures quick weigh and unassign logic exists in the weigh out module."""
    content = _read("static", "js", "modules", "inv_weigh_out.js")
    assert "window.openQuickWeigh =" in content, "Missing openQuickWeigh function"
    assert "action: 'force_unassign'" in content, "Missing auto-unassign logic for 0g spools"


def test_app_spools_by_filament_allow_archived():
    """Ensures the backend handles allow_archived fallback for spools_by_filament.

    L316: the handler moves to print_deduct.py — read the whole app-module
    family (see tests/source_family.py)."""
    import source_family
    content = source_family.read_app_family()
    assert "allow_archived = request.args.get('allow_archived'," in content, "Missing allow_archived query param parser"
