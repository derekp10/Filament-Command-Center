"""Group 39.3 — budget canary for the shared printer check (inv_core.js).

The "⏳ Checking XL…" pill shows after PRINTER_CHECK_DELAY_MS, so a fast answer
never flashes it, and the client gives up after PRINTER_CHECK_TIMEOUT_MS (the
probe fails open; the overlay then says FCC couldn't tell). The E2E waits in
test_move_result_consumers_e2e.py and the Quick-Swap overlay's wait-budget
floor (test_overlay_wait_budgets.py, 3000 ms) are sized against these, so a
change to either must be deliberate. Hermetic: reads the source, no browser.
"""
from __future__ import annotations

import re
from pathlib import Path

CORE = Path(__file__).resolve().parents[1] / "static" / "js" / "modules" / "inv_core.js"


def _const(src: str, name: str) -> int:
    m = re.search(rf"const {name} = (\d+);", src)
    assert m, f"{name} is no longer a plain constant in inv_core.js"
    return int(m.group(1))


def test_the_pill_waits_300ms_before_showing():
    assert _const(CORE.read_text(encoding="utf-8"), "PRINTER_CHECK_DELAY_MS") == 300


def test_the_client_gives_up_on_a_printer_after_3s():
    assert _const(CORE.read_text(encoding="utf-8"), "PRINTER_CHECK_TIMEOUT_MS") == 3000


def test_the_pill_is_not_a_toast():
    """Escape dismisses the newest .toast-msg; a pill with that class would
    swallow an Escape meant for a modal while it shows."""
    src = CORE.read_text(encoding="utf-8")
    start = src.index("const _printerCheckPill = ")
    body = src[start:src.index("\n};", start)]
    assert "toast-msg" not in body
