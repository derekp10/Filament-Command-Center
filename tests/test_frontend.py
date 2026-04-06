import os
import re

def test_modal_interceptor_exists():
    """
    Ensures that scripts.html contains a global Bootstrap modal event listener
    that resets the deck modes when any modal opens.
    """
    html_path = os.path.join(os.path.dirname(__file__), "..", "inventory-hub", "templates", "components", "scripts.html")
    assert os.path.exists(html_path)
    
    with open(html_path, "r", encoding="utf-8") as f:
        content = f.read()

    # The file must contain a listener for show.bs.modal
    assert "show.bs.modal" in content, "Missing global modal open interceptor"
    assert "resetCommandModes" in content, "Missing resetCommandModes logic in modal interceptor"

def test_reset_command_modes_exists():
    """
    Ensures that inv_cmd.js contains the resetCommandModes() function 
    to successfully turn off dropMode and ejectMode.
    """
    js_path = os.path.join(os.path.dirname(__file__), "..", "inventory-hub", "static", "js", "modules", "inv_cmd.js")
    assert os.path.exists(js_path)
    
    with open(js_path, "r", encoding="utf-8") as f:
        content = f.read()

    assert "const resetCommandModes = () =>" in content or "window.resetCommandModes = () =>" in content
    assert "state.dropMode = false" in content
    assert "state.ejectMode = false" in content
    assert "updateDeckVisuals()" in content

def test_nosleep_video_injected():
    """
    Ensures scripts.html loads the NoSleep fallback to bypass laptop screen timeouts.
    """
    html_path = os.path.join(os.path.dirname(__file__), "..", "inventory-hub", "templates", "components", "scripts.html")
    with open(html_path, "r", encoding="utf-8") as f:
        content = f.read()

    assert "NoSleep.min.js" in content

def test_request_wakelock_fallback():
    """
    Ensures inv_core.js initiates the NoSleep fallback polyfill on user click
    if the native navigator.wakelock fails.
    """
    js_path = os.path.join(os.path.dirname(__file__), "..", "inventory-hub", "static", "js", "modules", "inv_core.js")
    with open(js_path, "r", encoding="utf-8") as f:
        content = f.read()

    assert "window.NoSleep" in content
    assert "noSleepInstance.enable()" in content or "noSleep.enable()" in content

def test_location_list_features_exist():
    """
    Ensures that the Location List has the explicit sorting logic and 
    column definitions in place as requested in the Glow-up feature.
    """
    js_path = os.path.join(os.path.dirname(__file__), "..", "inventory-hub", "static", "js", "modules", "inv_core.js")
    with open(js_path, "r", encoding="utf-8") as f:
        js_content = f.read()

    assert "state.locSortBy" in js_content, "Missing sorting state injection for Location List"
    assert "window.sortLocations =" in js_content, "Missing sortLocations handler"
    assert "Unassigned" in js_content, "Missing Unassigned fall-back injection"

    html_path = os.path.join(os.path.dirname(__file__), "..", "inventory-hub", "templates", "components", "modals_loc_mgr.html")
    with open(html_path, "r", encoding="utf-8") as f:
        html_content = f.read()

    assert "onclick=\"sortLocations('LocationID')\"" in html_content, "Missing column sorting UI binds"
    assert "locQrViewModal" in html_content, "Missing QR Overlay in Loc Mgr Modal"
