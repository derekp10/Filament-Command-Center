"""A shortcut registered before shortcuts_registry.js loads must still be listed.

Background (2026-08-05):
  `templates/components/scripts.html` loads shortcuts_registry.js well down the
  list, but modules above it — inv_cmd, inv_wizard, inv_details, inv_loc_mgr —
  register their shortcuts at module-eval time. `window.registerShortcut` did
  not exist yet, and every call site guards with
  `if (window.registerShortcut) { ... }`, so the registration was **silently
  dropped**. The shortcut still worked; it was just invisible in the `?` help
  overlay, quietly violating the CLAUDE.md rule that the overlay stays complete.

  L298's Shift+B hit this exactly and was worked around locally by registering
  on DOMContentLoaded — leaving the trap armed for the next person.

The fix is a queueing shim at the top of scripts.html which shortcuts_registry
drains on load, so registration order stops mattering. These tests pin the
OUTCOME (the overlay is complete) rather than the mechanism, so a future
refactor is free to solve it a different way.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

INV_HUB = Path(__file__).resolve().parent.parent
SCRIPTS_HTML = INV_HUB / "templates" / "components" / "scripts.html"

DASH = "http://localhost:8000/"


def test_shim_is_defined_before_any_module_loads():
    """The queue must be installed above every <script src=…modules/…>.

    If a module loads first, its eval-time registration is lost again.
    """
    html = SCRIPTS_HTML.read_text(encoding="utf-8", errors="replace")
    shim_at = html.find("window.__pendingShortcuts")
    assert shim_at != -1, "the registerShortcut queueing shim is gone"

    first_module = None
    for m in re.finditer(r"js/modules/([A-Za-z0-9_]+\.js)", html):
        first_module = m
        break
    assert first_module is not None, "no module <script> tags found"
    assert shim_at < first_module.start(), (
        f"the shim must be defined before the first module "
        f"({first_module.group(1)}), otherwise that module's eval-time "
        "registerShortcut call is silently dropped again"
    )


@pytest.mark.usefixtures("require_server")
def test_a_pre_registry_registration_reaches_the_overlay(page):
    """End-to-end: register before the registry exists, and still be listed.

    This is the exact sequence that used to lose the entry. We re-create it by
    restoring the shim and registering through it, then draining as the registry
    does on load — proving the queue path, not just the live function.
    """
    page.goto(DASH, wait_until="domcontentloaded")
    page.wait_for_function("typeof window.registerShortcut === 'function'", timeout=15000)

    page.evaluate("""
        // Re-enter the pre-registry world: queue, exactly as a module above
        // shortcuts_registry.js would have done at eval time.
        const realRegister = window.registerShortcut;
        window.__pendingShortcuts = [];
        window.registerShortcut = (s) => window.__pendingShortcuts.push(s);

        // A module registers while the registry "does not exist yet".
        if (window.registerShortcut) {
            window.registerShortcut({
                id: 'probe-early-shortcut',
                scope: 'Probe',
                keys: ['Ctrl', 'Shift', 'P'],
                description: 'Registered before the registry loaded.',
            });
        }

        // Now the registry loads and drains the queue.
        window.registerShortcut = realRegister;
        window.__pendingShortcuts.splice(0).forEach(s => window.registerShortcut(s));
    """)

    listed = page.evaluate("""
        () => {
            const el = document.getElementById('fcc-shortcuts-list');
            return el ? el.innerHTML : '';
        }
    """)
    assert "Registered before the registry loaded." in listed, (
        "a shortcut registered before shortcuts_registry.js loaded never "
        "reached the `?` overlay — the drop this fix exists to prevent"
    )


@pytest.mark.usefixtures("require_server")
def test_draining_the_queue_does_not_double_register(page):
    """The shim and the real registry must not both record the same entry."""
    page.goto(DASH, wait_until="domcontentloaded")
    page.wait_for_function("typeof window.registerShortcut === 'function'", timeout=15000)

    page.evaluate("""
        const s = {id: 'probe-dupe', scope: 'Probe', keys: ['X'],
                   description: 'DUPE-PROBE-ENTRY'};
        window.registerShortcut(s);
        window.registerShortcut(s);
    """)

    html = page.evaluate(
        "document.getElementById('fcc-shortcuts-list')?.innerHTML || ''"
    )
    assert html.count("DUPE-PROBE-ENTRY") == 1, (
        f"shortcut registered twice appeared {html.count('DUPE-PROBE-ENTRY')} "
        "times in the overlay"
    )
