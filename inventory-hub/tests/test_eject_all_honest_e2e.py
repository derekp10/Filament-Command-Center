"""Group 41.1 end to end, against the real backend: a CMD:EJECTALL scan on a
Room or a Printer view is refused before the "Nuke all unslotted in …?" prompt,
with the server's own wording, and nothing moves. Dev's LR (a Room) and XL (a
Printer with heads XL-1 … XL-5) are the views; a refused view writes only an
Activity Log line, so dev data is untouched.
"""
from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect


def _scan_eject_all_on(page: Page, open_manage_modal, loc: str):
    open_manage_modal(loc)
    page.evaluate("processScan('CMD:EJECTALL', 'barcode')")


@pytest.mark.usefixtures("require_server")
@pytest.mark.parametrize("loc,text", [
    ("LR", "Eject All is off for rooms"),
    ("XL", "Eject All is off for printers"),
])
def test_a_room_or_printer_view_refuses_before_the_nuke_prompt(page: Page, open_manage_modal, loc, text):
    _scan_eject_all_on(page, open_manage_modal, loc)
    toasts = page.locator("#toast-container")
    expect(toasts).to_contain_text(text, timeout=8000)
    expect(toasts).to_contain_text("nothing was moved")
    # The refusal came back before any prompt: the safety dialog never opened.
    expect(page.locator("#safetyModal")).not_to_be_visible()
