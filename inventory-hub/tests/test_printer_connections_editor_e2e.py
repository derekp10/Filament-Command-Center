"""Hotfix 2026-09-29 — Settings → toolhead editor + Printer Connections grid.

Derek's INDX setup on prod ended with no saved PrusaLink connection although he
had typed the IP + API key more than once. The grid's own per-row Save was easy
to miss, and "Save toolheads" re-rendered the whole editor — throwing the typed
IP + key away ("the ip address resets in the display field after it's saved").
The per-row Save did the reverse and wiped unsaved toolhead edits.

Pinned here (route-stubbed — /api/printer_map and /api/printer_creds are served
by an in-test fake, so nothing touches the real printer map or credentials):
- "Save toolheads" also saves a connection typed into the grid, addressed by
  the Printer row's LocationID, and the IP is still shown after the reload;
- the per-row Save addresses the row by LocationID and leaves unsaved toolhead
  edits alone;
- a printer with no saved connection is called out, and the callout clears
  once the connection is saved;
- a printer name typed on one toolhead row mirrors to that printer's other
  rows only, and a new row typed under a printer's prefix inherits its name
  and the next position.
"""
from __future__ import annotations

import copy
import json

import pytest
from playwright.sync_api import Page, expect

SENTINEL = "__secret_set__"
INDX = "🦝 Core One INDX"
HOST = "#config-printer-map"


class _FakePrinterApi:
    """Stateful stand-in for GET/PUT /api/printer_map and PUT /api/printer_creds."""

    def __init__(self):
        self.calls = []   # (method, path, body) in arrival order
        self.rows = [
            {"location_id": "RCOI", "name": INDX, "ip_address": "", "api_key": "", "toolhead_count": 2},
            {"location_id": "XL", "name": "🦝 XL", "ip_address": "192.168.1.121",
             "api_key": SENTINEL, "toolhead_count": 1},
        ]
        self.entries = [
            {"location_id": "RCOI-1", "printer_name": INDX, "position": 0},
            {"location_id": "RCOI-2", "printer_name": INDX, "position": 1},
            {"location_id": "XL-1", "printer_name": "🦝 XL", "position": 0},
        ]

    def _view(self):
        return {
            "printers": {},
            "entries": copy.deepcopy(self.entries),
            "printer_creds": {r["name"]: {"ip_address": r["ip_address"], "api_key": r["api_key"]}
                              for r in self.rows},
            "printer_rows": copy.deepcopy(self.rows),
        }

    def _reply(self, route, body, status=200):
        route.fulfill(status=status, content_type="application/json", body=json.dumps(body))

    def printer_map(self, route, request):
        if request.method == "GET":
            return self._reply(route, self._view())
        body = request.post_data_json or {}
        self.calls.append(("PUT", "/api/printer_map", body))
        return self._reply(route, {"ok": True, "error": None, "printer_map": body.get("printer_map"),
                                   "created_toolhead_rows": [], "removed_toolhead_rows": []})

    def printer_creds(self, route, request):
        body = request.post_data_json or {}
        self.calls.append(("PUT", "/api/printer_creds", body))
        row = next((r for r in self.rows if r["location_id"] == body.get("location_id")), None)
        if row is None:
            return self._reply(route, {"ok": False, "error": "No Printer"}, status=404)
        row["ip_address"] = body.get("ip_address", "")
        if not row["ip_address"]:
            row["api_key"] = ""
        elif body.get("api_key") and body.get("api_key") != SENTINEL:
            row["api_key"] = SENTINEL
        return self._reply(route, {"ok": True, "error": None})


def _open_editor(page: Page, base_url: str, reset_dom_state_js: str) -> _FakePrinterApi:
    api = _FakePrinterApi()
    page.goto(base_url)
    page.wait_for_selector("#command-buffer, #buffer-zone", timeout=10000)
    page.evaluate(reset_dom_state_js)
    page.route("**/api/printer_map", api.printer_map)
    page.route("**/api/printer_creds", api.printer_creds)
    page.wait_for_function("typeof window.openConfigModal === 'function'", timeout=10000)
    page.evaluate("window.openConfigModal()")
    expect(page.locator("#configModal")).to_be_visible(timeout=5000)
    page.wait_for_function(
        f"() => document.querySelectorAll('{HOST} .pc-row').length === 2", timeout=10000)
    return api


def _conn(page: Page, loc_id: str, part: str):
    return page.locator(f'{HOST} .pc-row[data-location-id="{loc_id}"] {part}')


def _pm_name(page: Page, loc_id: str):
    return page.locator(f"{HOST} .pm-row", has=page.locator(f'.pm-loc[value="{loc_id}"]')).locator(".pm-name")


@pytest.mark.usefixtures("require_server")
def test_save_toolheads_also_saves_a_typed_connection(page: Page, base_url: str, reset_dom_state_js: str):
    api = _open_editor(page, base_url, reset_dom_state_js)
    _conn(page, "RCOI", ".pc-ip").fill("192.168.1.120")
    _conn(page, "RCOI", ".pc-key").fill("INDXKEY")
    page.locator("#pm-save").click()
    # The reload re-renders from the fake server — the saved IP must be what shows.
    page.wait_for_function(
        f"""() => {{ const el = document.querySelector('{HOST} .pc-row[data-location-id="RCOI"] .pc-ip');
                    return el && el.getAttribute('data-initial') === '192.168.1.120'; }}""",
        timeout=10000)
    expect(_conn(page, "RCOI", ".pc-ip")).to_have_value("192.168.1.120")
    expect(_conn(page, "RCOI", ".pc-key-badge")).to_be_visible()
    paths = [c[1] for c in api.calls]
    assert paths == ["/api/printer_creds", "/api/printer_map"], paths
    creds_body = api.calls[0][2]
    assert creds_body["location_id"] == "RCOI"
    assert creds_body["ip_address"] == "192.168.1.120"
    assert creds_body["api_key"] == "INDXKEY"


@pytest.mark.usefixtures("require_server")
def test_row_save_keeps_unsaved_toolhead_edits(page: Page, base_url: str, reset_dom_state_js: str):
    api = _open_editor(page, base_url, reset_dom_state_js)
    _pm_name(page, "RCOI-1").fill("🦝 Core One+ INDX")
    _conn(page, "RCOI", ".pc-ip").fill("192.168.1.120")
    _conn(page, "RCOI", ".pc-save").click()
    expect(_conn(page, "RCOI", ".pc-status")).to_have_text("✓ Saved", timeout=10000)
    assert [c[1] for c in api.calls] == ["/api/printer_creds"]
    assert api.calls[0][2]["location_id"] == "RCOI"
    assert api.calls[0][2]["api_key"] == SENTINEL   # blank key field keeps the stored key
    # The unsaved rename survived the connection save (and was mirrored to RCOI-2).
    expect(_pm_name(page, "RCOI-1")).to_have_value("🦝 Core One+ INDX")
    expect(_pm_name(page, "RCOI-2")).to_have_value("🦝 Core One+ INDX")
    expect(_pm_name(page, "XL-1")).to_have_value("🦝 XL")


@pytest.mark.usefixtures("require_server")
def test_missing_connection_is_called_out_until_saved(page: Page, base_url: str, reset_dom_state_js: str):
    _open_editor(page, base_url, reset_dom_state_js)
    missing = page.locator(f"{HOST} .pc-missing")
    expect(missing).to_be_visible()
    expect(missing).to_contain_text("Core One INDX")
    expect(missing).not_to_contain_text("XL")
    _conn(page, "RCOI", ".pc-ip").fill("192.168.1.120")
    _conn(page, "RCOI", ".pc-save").click()
    expect(missing).to_be_hidden(timeout=10000)


@pytest.mark.usefixtures("require_server")
def test_new_toolhead_row_inherits_printer_name_and_next_position(page: Page, base_url: str,
                                                                 reset_dom_state_js: str):
    _open_editor(page, base_url, reset_dom_state_js)
    page.locator("#pm-add").click()
    new_row = page.locator(f"{HOST} .pm-row").last
    new_row.locator(".pm-loc").fill("RCOI-3")
    expect(new_row.locator(".pm-name")).to_have_value(INDX)
    expect(new_row.locator(".pm-pos")).to_have_value("2")
