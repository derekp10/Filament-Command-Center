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


class TestShippedDrain:
    """Group 38.11 — pin the SHIPPED drain, not a re-implementation of it.

    `test_a_pre_registry_registration_reaches_the_overlay` below rebuilds the
    shim AND the drain inside `page.evaluate` and then asserts its own inline
    copy worked. That passes against pre-fix code: it never executes the drain
    line in shortcuts_registry.js at all. The real hazard is an ORDERING one,
    and it is invisible to that test.

    The drain must be the LAST statement in the IIFE. `registerShortcut` calls
    `renderList()`, which is a `const` declared partway down the same IIFE, so
    draining any earlier throws a temporal-dead-zone ReferenceError — which
    wiped out EVERY shortcut, including the module's own. That regression was
    caught only indirectly, by a Bulk-Moves overlay test that has nothing to do
    with load order.

    Source-level and hermetic on purpose: this is a static ordering property,
    so it needs no browser and runs in the offline sweep.
    """

    def _registry_src(self):
        from pathlib import Path
        p = (Path(__file__).resolve().parent.parent
             / "static" / "js" / "modules" / "shortcuts_registry.js")
        return p.read_text(encoding="utf-8", errors="replace")

    def test_the_drain_exists_in_the_shipped_registry(self):
        src = self._registry_src()
        assert "window.__pendingShortcuts" in src, (
            "shortcuts_registry.js no longer drains the pre-registry queue — "
            "every shortcut registered by a module loaded before it is lost "
            "from the `?` overlay"
        )

    def test_the_drain_runs_AFTER_renderList_is_declared(self):
        """The TDZ trap. Draining before `renderList` exists throws and wipes
        every shortcut."""
        src = self._registry_src()
        decl = src.index("const renderList")
        drain = src.index("_pending.splice(")
        assert drain > decl, (
            "the queue drain runs BEFORE `const renderList` is initialised. "
            "registerShortcut() calls renderList(), so this throws a "
            "temporal-dead-zone ReferenceError and silently wipes EVERY "
            "shortcut from the help overlay. Keep the drain last in the IIFE."
        )

    def test_the_drain_CONSUMES_the_queue(self):
        """`splice(0)` empties as it reads. A plain forEach would leave the
        queue populated, so anything re-running the drain double-registers."""
        src = self._registry_src()
        assert "_pending.splice(0)" in src, (
            "the drain must consume the queue (splice), not just iterate it"
        )


@pytest.mark.usefixtures("require_server")
def test_the_shipped_drain_actually_emptied_the_queue(page):
    """Live counterpart: after a real page load the queue must be EMPTY.

    Nothing is re-implemented here — this observes the shipped shim and the
    shipped drain having run. A non-empty queue means the drain threw (the TDZ
    crash) or never executed, and every early-module shortcut is missing from
    the overlay.
    """
    page.goto(DASH, wait_until="domcontentloaded")
    page.wait_for_function("typeof window.registerShortcut === 'function'", timeout=15000)
    page.wait_for_function(
        "Array.isArray(window.__pendingShortcuts) === false || "
        "window.__pendingShortcuts.length === 0",
        timeout=15000,
    )

    pending = page.evaluate("(window.__pendingShortcuts || []).length")
    assert pending == 0, (
        f"{pending} shortcut(s) are still queued after load — the shipped drain "
        f"in shortcuts_registry.js did not run to completion"
    )
    # And the registry is populated, so "empty queue" isn't just "nothing ever
    # registered".
    listed = page.evaluate(
        "document.getElementById('fcc-shortcuts-list')?.innerHTML || ''"
    )
    assert len(listed) > 0, "the `?` overlay list is empty — nothing registered at all"


@pytest.mark.usefixtures("require_server")
def test_a_pre_registry_registration_reaches_the_overlay(page):
    """End-to-end: register before the registry exists, and still be listed.

    ⚠️ Group 38.11 — this re-creates the shim and the drain INSIDE the page, so
    it exercises its own inline copy rather than the shipped one and would pass
    against pre-fix code. Kept because it still documents the sequence
    end-to-end, but the load-bearing pins are in `TestShippedDrain` above and
    in `test_the_shipped_drain_actually_emptied_the_queue`.
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
