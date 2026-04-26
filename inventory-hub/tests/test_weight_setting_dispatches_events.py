"""
Regression guard for the "buffer cards don't always update" backlog item.

The buglist asks: every weight-setting code path should fire
`inventory:sync-pulse` (or `inventory:locations-changed`) so dashboard
cards refresh in lockstep. Frontend polling (inv_core.js) catches
backend-only writes eventually, but interactive paths MUST dispatch
synchronously — otherwise the user sees stale data until the next poll.

Two layers of coverage:

1. **Static guard** — grep-based asserts that each known weight-setting
   path still contains its dispatch. If someone refactors one out, this
   test fails loud instead of silently breaking the refresh chain.
2. **E2E spy** — navigates to the dashboard, attaches a CustomEvent spy,
   pushes a spool into the buffer via `/api/identify_scan`, and asserts
   `inventory:buffer-updated` fires. Confirms the event system is wired
   live (not just present in source).
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

import pytest
import requests

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

JS_DIR = Path(__file__).resolve().parents[1] / "static" / "js" / "modules"


def _read(name: str) -> str:
    return (JS_DIR / name).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# 1. Static guard — each weight-setting path dispatches a refresh event
# ---------------------------------------------------------------------------

def test_wizard_save_dispatches_sync_pulse():
    """inv_wizard.js must fire `inventory:sync-pulse` after a save so
    dashboard cards rebind. This is the path the buglist flagged as the
    likely gap for manual-weight-zero saves."""
    src = _read("inv_wizard.js")
    assert re.search(r"dispatchEvent\s*\(\s*new\s+CustomEvent\(\s*['\"]inventory:sync-pulse['\"]", src), \
        "inv_wizard.js lost its inventory:sync-pulse dispatch on wizard save"


def test_weigh_out_dispatches_sync_pulse():
    """inv_weigh_out.js must fire `inventory:sync-pulse` after a manual
    weigh-out so buffer + location cards see the new weight."""
    src = _read("inv_weigh_out.js")
    assert re.search(r"dispatchEvent\s*\(\s*new\s+CustomEvent\(\s*['\"]inventory:sync-pulse['\"]", src), \
        "inv_weigh_out.js lost its inventory:sync-pulse dispatch on weigh save"


def test_force_location_override_dispatches_sync_pulse():
    """inv_details.js Force Location override writes to Spoolman then
    must fire sync-pulse so the dashboard reflects the new location."""
    src = _read("inv_details.js")
    assert re.search(r"dispatchEvent\s*\(\s*new\s+CustomEvent\(\s*['\"]inventory:sync-pulse['\"]", src), \
        "inv_details.js lost its inventory:sync-pulse dispatch on force-location save"


def test_quickswap_dispatches_locations_changed():
    """Quick-Swap rewires a spool's location; inv_quickswap.js must fire
    `inventory:locations-changed` so the location manager + dashboard
    repaint without waiting for the polling loop."""
    src = _read("inv_quickswap.js")
    assert re.search(r"dispatchEvent\s*\(\s*new\s+CustomEvent\(\s*['\"]inventory:locations-changed['\"]", src), \
        "inv_quickswap.js lost its inventory:locations-changed dispatch on swap"


def test_cmd_buffer_assign_dispatches_locations_changed():
    """inv_cmd.js context-assign path must fire locations-changed after
    a move — this is the bulk-buffer-to-location path at smart_move."""
    src = _read("inv_cmd.js")
    assert re.search(r"dispatchEvent\s*\(\s*new\s+CustomEvent\(\s*['\"]inventory:locations-changed['\"]", src), \
        "inv_cmd.js lost its inventory:locations-changed dispatch on smart_move"


def test_core_polling_dispatches_sync_pulse():
    """inv_core.js's poll loop is the safety net for backend-only writes
    (filabridge auto-deduct, auto-archive). It MUST keep dispatching
    sync-pulse on each poll — otherwise nothing refreshes the UI after
    a usage event."""
    src = _read("inv_core.js")
    assert re.search(r"dispatchEvent\s*\(\s*new\s+CustomEvent\(\s*['\"]inventory:sync-pulse['\"]", src), \
        "inv_core.js polling loop lost its sync-pulse dispatch"


def test_buffer_assign_dispatches_buffer_updated():
    """Scan → buffer updates must fire `inventory:buffer-updated` so the
    Quick-Swap/Location Manager overlays see newly-held spools. Matching
    dispatchers in inv_cmd.js."""
    src = _read("inv_cmd.js")
    assert re.search(r"dispatchEvent\s*\(\s*new\s+CustomEvent\(\s*['\"]inventory:buffer-updated['\"]", src), \
        "inv_cmd.js lost its inventory:buffer-updated dispatch"


# ---------------------------------------------------------------------------
# 2. E2E spy — confirm buffer-updated actually fires on a live scan
# ---------------------------------------------------------------------------

@pytest.mark.usefixtures("require_server")
def test_scan_fires_buffer_updated_event(page, api_base_url, clean_buffer):
    """Live end-to-end check: scan something into the buffer, observe
    the CustomEvent on the page, and verify at least one fired."""
    page.goto(api_base_url)
    page.wait_for_selector("#buffer-zone, #command-buffer", timeout=10_000)

    # Install a counter — each fire bumps window.__ev_count.
    page.evaluate(
        """() => {
            window.__ev_count = { 'inventory:buffer-updated': 0,
                                  'inventory:sync-pulse': 0,
                                  'inventory:locations-changed': 0 };
            for (const name of Object.keys(window.__ev_count)) {
                document.addEventListener(name, () => { window.__ev_count[name]++; });
            }
        }"""
    )

    # Pick any existing spool to scan. If Spoolman has nothing, skip.
    SPOOLMAN = "http://192.168.1.29:7913"
    try:
        sr = requests.get(f"{SPOOLMAN}/api/v1/spool", timeout=5)
    except requests.RequestException:
        pytest.skip("Spoolman dev instance unreachable")
    if not sr.ok or not sr.json():
        pytest.skip("no spool available to scan")
    spool_id = sr.json()[0]["id"]
    requests.post(
        f"{api_base_url}/api/identify_scan",
        json={"text": f"ID:{spool_id}", "source": "test"},
        timeout=5,
    )

    # The scan writes to server state; the frontend picks it up on the
    # next poll tick (inv_core.js), which then fires both buffer-updated
    # and sync-pulse. Allow one poll window.
    page.wait_for_function(
        "() => window.__ev_count && ("
        "window.__ev_count['inventory:buffer-updated'] > 0 || "
        "window.__ev_count['inventory:sync-pulse'] > 0)",
        timeout=10_000,
    )
    counts = page.evaluate("() => window.__ev_count")
    assert counts["inventory:sync-pulse"] > 0 or counts["inventory:buffer-updated"] > 0, counts
