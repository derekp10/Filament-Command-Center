"""Group 54.7, a real run: the Quick-Weigh's "Auto Archive & Eject if Empty (0g)"
switch turned off keeps a spool weighed to 0 g in stock where it is, through the
whole chain: the real page on the dev container, the real /api/spool/update and
update_spool, and dev's Spoolman.

The hermetic halves are tests/test_auto_archive_switch_page_54_7_js.py (what the
page sends) and tests/test_auto_archive_off_54_7.py (what the route and
update_spool do with it, over SpoolmanHTTPFake). This one checks the two meet on a
real Spoolman. It writes only to a throwaway filament and spool it creates on dev
(the conftest fixtures delete both), so it is gated like the other Spoolman
integration tests: `pytest --run-integration` or `RUN_INTEGRATION=1`.

Base proof (94f87de): red there, the spool archived and its location blanked.
"""
from __future__ import annotations

import pytest
import requests
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.integration

PLACE = "ZZ-TEST-SHELF-54-7"


def test_the_quick_weighs_switch_off_keeps_a_spool_weighed_to_0_in_stock(
        page: Page, require_server, throwaway_spool, require_spoolman):
    url = require_spoolman
    sid = throwaway_spool["id"]
    r = requests.patch(f"{url}/api/v1/spool/{sid}", json={"location": PLACE}, timeout=10)
    assert r.ok, r.text

    sent = []
    page.on("request", lambda req: sent.append(req.post_data_json)
            if req.method == "POST" and req.url.endswith("/api/spool/update") else None)
    page.goto("http://localhost:8000")
    page.wait_for_function("typeof window.openQuickWeigh === 'function'"
                           " && typeof window.WeightEntry === 'object'")
    page.evaluate("(id) => window.openQuickWeigh(id)", sid)
    box = page.locator("#fcc-we-input")
    expect(box).to_be_visible()
    page.locator(".fcc-we-tab[data-mode='set_used']").click()
    page.locator("#fcc-we-auto-archive").uncheck()           # a real click: on by default
    box.fill("1000")                                         # the spool's whole 1000 g used
    with page.expect_response(lambda resp: resp.url.endswith("/api/spool/update"), timeout=15_000) as answer:
        box.press("Enter")
    assert answer.value.json().get("auto_archived") is False, answer.value.json()

    rec = requests.get(f"{url}/api/v1/spool/{sid}", timeout=10).json()
    assert rec.get("archived") is False, rec
    assert rec.get("location") == PLACE, rec
    assert float(rec.get("used_weight") or 0) == pytest.approx(1000.0), rec
    assert not (rec.get("extra") or {}).get("fcc_pre_archive_location"), rec
    assert len(sent) == 1 and sent[0]["auto_archive"] is False, sent
    assert "archived" not in sent[0]["updates"], sent
    expect(page.locator("#toast-container .toast-msg",
                        has_text=f"Updated Spool #{sid}: 0 g left, kept in stock (Auto-Archive is off)")
           ).to_be_visible(timeout=10_000)
