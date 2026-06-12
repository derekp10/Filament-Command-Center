"""Regression guard for the search→buffer-add UI lock-up (2026-06-12).

Investigated repro: with the Location Manager toolhead modal open, an eject
followed by "add from search into the buffer" left the UI dead until a hard
refresh. Root cause class: a fetch whose handler toggles the global z-index:9999
processing-overlay can strand that overlay (blocking ALL input) if it never
settles, and two user-action fetches (`ejectSpool(pickup=true)`,
`triggerEjectAll`) lacked a `.catch`/in-flight guard — gaps the 2026-05-19 L28
poll-guard fix didn't cover (it only touched the six heartbeat polls).

Fix: a `window.fetchT` helper wraps fetch with a hard `AbortSignal.timeout` so a
hung request force-rejects → the caller's `.catch`/`.finally` clears the overlay;
the overlay-setting user-action fetches route through it; and the two unguarded
paths get `.catch` + an in-flight guard. This file pins that so a refactor can't
quietly remove it. Pure structural source grep; no server required.
"""
import os
import re

_HUB = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _read(*parts):
    path = os.path.join(_HUB, *parts)
    assert os.path.exists(path), f"missing: {path}"
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def test_fetcht_helper_defined_with_timeout():
    src = _read("static", "js", "modules", "inv_core.js")
    assert "window.fetchT" in src, "fetchT timeout helper missing"
    assert "AbortSignal.timeout" in src, "fetchT must enforce a wall-clock timeout"


def test_processscan_routes_through_fetcht():
    src = _read("static", "js", "modules", "inv_cmd.js")
    assert "window.fetchT('/api/identify_scan'" in src, (
        "processScan's overlay-setting identify_scan must use fetchT")


def test_locmgr_overlay_fetches_route_through_fetcht():
    src = _read("static", "js", "modules", "inv_loc_mgr.js")
    # ejectSpool(pickup) + doEject + manualAddSpool + triggerEjectAll.
    assert src.count("window.fetchT(") >= 4, (
        "the Location Manager overlay-setting fetches must use fetchT")


def test_pickup_has_inflight_guard_and_catch():
    src = _read("static", "js", "modules", "inv_loc_mgr.js")
    assert "if (window._pickInFlight) return;" in src, "pickup missing in-flight guard"
    assert "window._pickInFlight = true;" in src, "pickup must set the in-flight flag"
    assert "window._pickInFlight = false;" in src, "pickup must reset the flag (finally)"
    # The pickup fetch must now have a .catch (was the lone unguarded fetch).
    assert re.search(r"_pickInFlight\s*=\s*false", src), "pickup must clear in .finally"


def test_eject_all_uses_fetcht_and_clears_overlay_on_error():
    src = _read("static", "js", "modules", "inv_loc_mgr.js")
    assert "action: 'clear_location'" in src
    # triggerEjectAll must (a) use fetchT and (b) clear the overlay on rejection —
    # the missing .catch was a genuine stuck-overlay bug.
    assert re.search(r"window\.fetchT\('/api/manage_contents'.*?clear_location", src, re.S), (
        "triggerEjectAll must route through fetchT")
    assert re.search(r"clear_location.*?\.catch\(\(\)\s*=>\s*\{\s*setProcessing\(false\)", src, re.S), (
        "triggerEjectAll must clear the processing-overlay in a .catch")
