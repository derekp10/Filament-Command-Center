"""Group 52 (Spoolman read load & honest empties), the browser half.

WRITTEN 2026-10-19 ON feature/group-52-spoolman-read-load AND NOT RUN THERE: the
dev container serves the main checkout, so the builder couldn't drive these. The
same behaviour is pinned hermetically by tests/test_spoolman_read_load_52_js.py
(node, offline); these confirm it in a real browser.

  52.1b  the Location Manager keeps its cards and says "Spoolman didn't answer"
         when a refresh or the heartbeat can't read Spoolman; a fresh open that
         can't read draws no EMPTY slots; a genuinely empty box still draws EMPTY;
  52.1a  the heartbeat carries the 🏷️ Backlog count, and the page no longer polls
         /api/print_queue/pending while the backlog window is closed;
  52.1c  the Quick-Swap grid reads its boxes in one request.

HERMETIC AGAINST DEV DATA (the Location Manager tests): one context route answers
every non-GET synthetically, serves its own buffer, answers /api/get_contents for
the fake FCC-TEST-HONEST-BOX (a Spoolman outage is a 502 for the strict read and
[] for the plain one, as the server answers), rewrites the heartbeat's manage
section for that box, and passes /api/locations and the heartbeat through
read-only with the fake row appended. Spool ids are fake (9995xx).
"""
from __future__ import annotations

import json
import re
from urllib.parse import parse_qs, urlsplit

import pytest
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page, expect

from test_quickswap_visual import GRID_CONTENTS, _open_hermetic_grid, hermetic_grid  # noqa: F401

BOX = "FCC-TEST-HONEST-BOX"
BOX_ROW = {"LocationID": BOX, "Name": "FCC Test Honest Box", "Type": "Dryer Box", "Max Spools": "4"}
SPOOL = {"id": 999521, "display": "#999521 FCC Test PLA Honest Red", "color": "c0392b",
         "remaining_weight": 640, "initial_weight": 1000, "location": BOX, "slot": "2",
         "is_ghost": False, "archived": False, "deployed_to": None,
         "details": {"brand": "FCC Test", "material": "PLA", "color_name": "Honest Red"}}
OK = {"success": True}
NOTICE = "#manage-read-notice"

pytestmark = pytest.mark.usefixtures("require_server")


class FakeBackend:
    """Spoolman "goes down" for the fake box when `up` is False."""

    def __init__(self, page: Page, contents=(SPOOL,)):
        self.up = True
        self.contents = [dict(c) for c in contents]
        self.reads = []
        self.buffer = []
        page.context.route("**/*", self._handle)

    @staticmethod
    def _json(route, payload, status=200):
        route.fulfill(status=status, content_type="application/json", body=json.dumps(payload))

    def _handle(self, route):
        try:
            self._route(route)
        except PlaywrightError as e:
            if "closed" not in str(e).lower():
                raise

    def _manage(self):
        if self.up:
            return {"id": BOX, "contents": self.contents, "read_ok": True}
        return {"id": BOX, "read_ok": False, "read_error": "couldn't read Spoolman (Read timed out.)"}

    def _with_row(self, rows):
        if isinstance(rows, list) and not any(isinstance(r, dict) and r.get("LocationID") == BOX for r in rows):
            rows.append(dict(BOX_ROW))
        return rows

    def _route(self, route):
        req = route.request
        parts = urlsplit(req.url)
        path = parts.path
        if req.method in ("GET", "HEAD", "OPTIONS"):
            if path == "/api/state/buffer":
                self._json(route, self.buffer)
                return
            if path == "/api/get_contents":
                query = parse_qs(parts.query)
                if (query.get("id") or [""])[0].upper() == BOX:
                    self.reads.append(req.url)
                    if self.up:
                        self._json(route, self.contents)
                    elif "strict" in query:
                        self._json(route, {"error": f"Couldn't read {BOX} from Spoolman (Read timed out.)."}, 502)
                    else:
                        self._json(route, [])
                    return
            if path == "/api/locations" and req.method == "GET":
                resp = route.fetch()
                self._json(route, self._with_row(resp.json()), status=resp.status)
                return
            if path == "/api/dashboard_pulse":
                resp = route.fetch()
                data = resp.json()
                if isinstance(data, dict):
                    if "locations" in data:
                        data["locations"] = self._with_row(data["locations"])
                    if isinstance(data.get("manage"), dict) and str(data["manage"].get("id", "")).upper() == BOX:
                        data["manage"] = self._manage()
                self._json(route, data, status=resp.status)
                return
            route.continue_()
            return
        if path == "/api/state/buffer":
            try:
                buf = json.loads(req.post_data or "{}").get("buffer")
            except (TypeError, ValueError, AttributeError):
                buf = None
            self.buffer = buf if isinstance(buf, list) else []
        self._json(route, OK)


@pytest.fixture(autouse=True)
def _drop_routes_in_flight(page: Page):
    """Close the page FIRST: un-routing a live page lets its next buffer poll or
    persist reach the real dev server."""
    yield
    try:
        page.close()
    except PlaywrightError:
        pass
    try:
        page.context.unroute_all(behavior="ignoreErrors")
    except PlaywrightError:
        pass


def _boot(page: Page, base_url: str) -> None:
    page.goto(base_url.rstrip("/") + "/", wait_until="domcontentloaded")
    page.wait_for_function(
        "typeof state !== 'undefined' && typeof window.openManage === 'function'"
        f" && (state.allLocations || []).some(l => l.LocationID === {json.dumps(BOX)})",
        timeout=20_000)


def _open(page: Page) -> None:
    page.evaluate("(id) => window.openManage(id)", BOX)
    expect(page.locator("#manageModal")).to_be_visible(timeout=10_000)


def _grid_text(page: Page) -> str:
    return page.evaluate("() => document.getElementById('slot-grid-container').textContent || ''")


def test_a_refresh_that_cant_read_keeps_the_cards_and_says_so(page: Page, base_url, assert_contrast):
    be = FakeBackend(page)
    _boot(page, base_url)
    _open(page)
    page.wait_for_function("() => (document.getElementById('slot-grid-container').textContent || '').includes('999521')",
                           timeout=10_000)
    expect(page.locator(NOTICE)).to_be_hidden()

    be.up = False
    page.evaluate("(id) => window.refreshManageView(id)", BOX)
    notice = page.locator(NOTICE)
    expect(notice).to_be_visible(timeout=8_000)
    expect(notice).to_contain_text("Spoolman didn't answer")
    expect(notice).to_contain_text("These cards are from its last answer")
    assert "999521" in _grid_text(page), "a refresh that couldn't read redrew the box"
    assert_contrast(notice)

    # The heartbeat's manage section can't read either: the cards still stay.
    page.wait_for_timeout(6_500)
    assert "999521" in _grid_text(page), "the heartbeat redrew the box empty"
    expect(notice).to_be_visible()

    be.up = True
    page.evaluate("(id) => window.refreshManageView(id)", BOX)
    expect(notice).to_be_hidden(timeout=8_000)
    assert any("strict=1" in u for u in be.reads), be.reads


def test_an_open_that_cant_read_draws_no_empty_box(page: Page, base_url):
    be = FakeBackend(page)
    be.up = False
    _boot(page, base_url)
    _open(page)
    notice = page.locator(NOTICE)
    expect(notice).to_be_visible(timeout=8_000)
    expect(notice).to_contain_text("Spoolman didn't answer")
    expect(page.locator("#manage-grid-view")).to_be_hidden()
    assert "EMPTY" not in _grid_text(page)

    be.up = True   # the next heartbeat (or refresh) draws the box
    page.wait_for_function("() => (document.getElementById('slot-grid-container').textContent || '').includes('999521')",
                           timeout=15_000)
    expect(page.locator("#manage-grid-view")).to_be_visible()
    expect(notice).to_be_hidden()


def test_a_genuinely_empty_box_still_draws_empty(page: Page, base_url):
    FakeBackend(page, contents=())
    _boot(page, base_url)
    _open(page)
    page.wait_for_function("() => (document.getElementById('slot-grid-container').textContent || '').includes('EMPTY')",
                           timeout=10_000)
    assert _grid_text(page).count("EMPTY") == 4
    expect(page.locator(NOTICE)).to_be_hidden()


def test_the_heartbeat_counts_the_backlog_and_the_page_no_longer_polls_it(page: Page, base_url):
    """Read-only against dev: the page's own GETs. Watched for 8 s, under the
    10 s load fallback, so a slow first tick can't fetch the backlog either."""
    pending, pulses = [], []
    page.on("request", lambda r: pending.append(r.url) if "/api/print_queue/pending" in r.url else None)

    def _on_response(resp):
        if "/api/dashboard_pulse" in resp.url:
            try:
                pulses.append((resp.url, resp.json()))
            except Exception:
                pass

    page.on("response", _on_response)
    page.goto(base_url)
    page.wait_for_selector("#btn-backlog-count", timeout=10_000)
    page.wait_for_timeout(8_000)
    assert pending == [], f"the page polled the backlog with its window closed: {pending}"
    assert pulses and all("label_backlog" in u for u, _ in pulses), [u for u, _ in pulses]
    counted = [b["label_backlog"]["count"] for _, b in pulses
               if isinstance(b.get("label_backlog"), dict) and b["label_backlog"].get("read_ok")]
    if counted:
        expect(page.locator("#btn-backlog-count")).to_have_text(re.compile(rf"Backlog \({counted[-1]}\)"))


@pytest.mark.usefixtures("hermetic_grid")
def test_the_quickswap_grid_reads_its_boxes_in_one_request(page: Page, open_manage_modal):
    """The hermetic Quick-Swap grid of test_quickswap_visual.py: every read of
    its boxes is one ?ids= request, never one per box."""
    reads = []
    page.on("request", lambda r: reads.append(r.url) if "/api/get_contents" in r.url else None)
    _open_hermetic_grid(page, open_manage_modal)
    batched = [u for u in reads if "ids=" in u]
    per_box = [u for u in reads if "ids=" not in u
               and any(f"id={b}" in u for b in GRID_CONTENTS)]
    assert batched and per_box == [], reads
    assert all(all(f"ids={b}" in u for b in GRID_CONTENTS) for u in batched), batched
