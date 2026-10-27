"""
Shared pytest fixtures for the Filament Command Center test suite.

Usage:
- `page` (from pytest-playwright) is enhanced with a 1600x1300 viewport.
- `api_base_url` / `page_base_url` resolve from INVENTORY_HUB_URL env
  (default: http://localhost:8000) so tests can run against any environment.
- `clean_buffer`, `with_held_spool`, `seed_dryer_box`, `snapshot`, `scan`
  cover the common setup/teardown patterns used across the E2E suite.

Fixtures keep existing tests working unchanged — they only take effect when
imported or requested explicitly.
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
import typing
import uuid

import pytest
import requests

# Make the inventory-hub app modules importable from tests.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# ---------------------------------------------------------------------------
# Windows console UTF-8 (Group 26.2)
# ---------------------------------------------------------------------------
# The app's Activity-Log lines carry emoji (state.add_log_entry → logger via a
# `StreamHandler(sys.stdout)`; see state.py). On Windows the console defaults to
# cp1252, and under pytest's fd-level capture sys.stdout stays the real cp1252
# TextIOWrapper — so those emoji raise UnicodeEncodeError during logging emit
# and spew multi-line tracebacks that bury real test output. Reconfigure the std
# streams to UTF-8 HERE, at conftest import (before any test imports state.py, so
# its StreamHandler captures the reconfigured stream). No-op where reconfigure is
# unavailable (older streams) or the stream is already UTF-8.
for _utf8_stream in (sys.stdout, sys.stderr):
    try:
        _utf8_stream.reconfigure(encoding="utf-8", errors="backslashreplace")
    except (AttributeError, ValueError, OSError):
        pass

# ---------------------------------------------------------------------------
# The host never holds the container's hub.log (Group 45, review test-infra-1)
# ---------------------------------------------------------------------------
# state.py opens RotatingFileHandler('hub.log') relative to the working
# directory at import. From inventory-hub/ (the canonical run) that is the dev
# container's own bind-mounted log, so pytest held it open for the whole run.
# Windows can't rename a file another process holds, so the container's 1 MB
# rollover failed and Python's handler DROPPED the container's records until the
# host happened to rotate; dev's hub.log.1 and .5 with no .2-.4 between them are
# what those failed rollovers leave. It also mixed host unit-test lines ("DATA
# LOSS in remove_choice('Doomed')") into the container's log, and starved the
# request log's timeout count. Host log lines still reach stdout. Imported here,
# before any test module imports state.
import state as _fcc_state  # noqa: E402

if _fcc_state.f_handler in _fcc_state.logger.handlers:
    _fcc_state.logger.removeHandler(_fcc_state.f_handler)
_fcc_state.f_handler.close()


DEFAULT_BASE_URL = os.environ.get("INVENTORY_HUB_URL", "http://localhost:8000")
DEFAULT_DEV_SPOOLMAN = os.environ.get("DEV_SPOOLMAN_URL", "http://192.168.1.29:7913")
BASELINE_VIEWPORT = {"width": 1600, "height": 1300}

# Prefix used by every record the integration suite creates. The orphan-cleanup
# fixture relies on this exact prefix to identify records left behind by
# previous interrupted runs and the per-test teardown looks for it before
# deleting. Don't change without updating both sides.
TEST_RECORD_PREFIX = "__fcc_test_"


# ---------------------------------------------------------------------------
# Integration-test gating
# ---------------------------------------------------------------------------

def pytest_addoption(parser):
    """Add --run-integration so default `pytest` runs stay fast.

    Integration tests hit the real dev Spoolman at 192.168.1.29:7913 (or
    whatever DEV_SPOOLMAN_URL points at). Without this flag set, anything
    decorated `@pytest.mark.integration` is skipped at collection time.
    Setting RUN_INTEGRATION=1 in the environment is equivalent.
    """
    parser.addoption(
        "--run-integration",
        action="store_true",
        default=False,
        help="Run @pytest.mark.integration tests against the real dev Spoolman.",
    )
    # Group 19.1 — opt-in dev reset before a sweep. OFF by default so a
    # single-test run never triggers a docker restart / Spoolman reconcile.
    # For a FULL sweep, `pytest --reset-dev` restores the committed seed
    # baseline first so cross-test contamination can't accumulate. See
    # setup-and-rebuild/reset_dev.py + docs/agent_docs/tasks/19-*.md.
    # 2026-08-03 — a genuinely hermetic run. The plain `pytest` invocation was
    # documented as "the offline sweep" but never was one: --run-integration
    # gates only the dev-SPOOLMAN tests, while ~55 E2E files reach the local FCC
    # container via `require_server` (which skips only when it is DOWN) and
    # mutate real dev inventory on every routine verification. Use --offline
    # when you want a fast check that provably cannot touch Derek's data.
    parser.addoption(
        "--offline",
        action="store_true",
        default=False,
        help="Skip every test that touches the live FCC dev container, for a "
             "hermetic run that cannot mutate dev inventory. Equivalent env: "
             "FCC_OFFLINE=1.",
    )
    parser.addoption(
        "--reset-dev",
        action="store_true",
        default=False,
        help="Restore dev to the committed seed baseline (NON-destructive) "
             "before the session. Use for full sweeps. Equivalent env: "
             "RESET_DEV_BEFORE_SWEEP=1.",
    )
    parser.addoption(
        "--reset-dev-prune",
        action="store_true",
        default=False,
        help="Like --reset-dev but ALSO deletes sweep-created records "
             "(DESTRUCTIVE; agent-invoked with explicit OK — Derek never runs "
             "this). Equivalent env: RESET_DEV_PRUNE=1.",
    )


# Fixtures that imply "this test drives the live FCC dev container". Requesting
# any of them means the test cannot run in --offline mode. `page` is the
# important one: a Playwright test can take it WITHOUT require_server and still
# launch a browser against localhost:8000.
CONTAINER_FIXTURES = frozenset({
    "page", "context", "browser", "browser_context_args",
    "require_server", "api_base_url",
    "clean_buffer", "with_held_spool", "seed_dryer_box", "seed_via_ui",
    "snapshot", "scan", "borrow_box_bindings",
    "dev_spoolman_url", "throwaway_filament", "throwaway_spool",
})
# NOT in the set, deliberately: `playwright` and `isolated_page`. A test may run
# a browser under --offline only through `isolated_page`, whose browser has no
# route to any network (HTTP, WebSockets, frames and workers included), so it
# can render set_content markup but can never reach the container (pinned by
# test_offline_mode.py::TestIsolatedBrowser).


def _offline_mode(config) -> bool:
    """True when the caller asked for a genuinely hermetic run.

    `--offline` (or FCC_OFFLINE=1) skips every test that touches the live FCC
    dev container, so a verification run cannot write to Derek's real dev
    inventory. This exists because the plain `pytest` run was widely believed to
    be "the offline sweep" and never was: --run-integration gates only the tests
    that hit the dev SPOOLMAN on the NAS, while ~55 E2E files reach the local
    container through `require_server`, which skips only when that container is
    DOWN. Default behaviour is deliberately unchanged — this is opt-in.
    """
    try:
        flag = config.getoption("--offline")
    except (ValueError, AttributeError):  # option not registered (sub-config)
        flag = False
    return bool(flag) or os.environ.get("FCC_OFFLINE", "").lower() in (
        "1", "true", "yes",
    )


def pytest_collection_modifyitems(config, items):
    """Skip @pytest.mark.integration tests unless explicitly opted in.

    Two opt-in switches: the --run-integration CLI flag OR RUN_INTEGRATION=1
    in the environment. If neither is set, every integration item gets a
    skip marker added so the rest of the suite still runs.
    """
    # --offline first: deselect at COLLECTION time, not inside a fixture.
    # Gating only `require_server` isn't enough — a test can take the Playwright
    # `page` fixture without requesting require_server, and would still launch a
    # browser and drive the live container. Skipping by fixture name here also
    # keeps the run genuinely fast (no browser ever starts).
    if _offline_mode(config):
        offline_skip = pytest.mark.skip(
            reason="offline mode (--offline / FCC_OFFLINE=1): touches the live dev container"
        )
        for item in items:
            names = set(getattr(item, "fixturenames", ()))
            if names & CONTAINER_FIXTURES:
                item.add_marker(offline_skip)

    opted_in = config.getoption("--run-integration") or os.environ.get(
        "RUN_INTEGRATION", ""
    ).lower() in ("1", "true", "yes")
    if opted_in:
        return
    skip_marker = pytest.mark.skip(
        reason="integration test skipped (opt-in: --run-integration or RUN_INTEGRATION=1)"
    )
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip_marker)


# ---------------------------------------------------------------------------
# Group 45.1(c) — a run labels itself: wall-clock and a load factor
# ---------------------------------------------------------------------------
# A busy desktop, or the run's own traffic (it saturates dev Spoolman: 8,577
# five-second read timeouts in hub.log on 2026-10-13), slows every browser test
# by roughly the same factor, and fixed waits trip all over the suite. So a run
# says how slow it was: each passed browser test's call time against the fastest
# time the same test has taken on this PC in recent runs; the median ratio is the
# run's load factor. A fixed total-time limit would be wrong every time tests are
# added (2,707 -> 2,951 tests in five days). The history is git-ignored at the
# repo root, outside the inventory-hub/ bind mount the container sees.
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
TIMING_FILE = os.path.join(_REPO_ROOT, ".test-timings", "browser-call-times.json")
TIMING_KEEP = 8           # recent call times kept per test
LOAD_WARN = 1.25          # a median slowdown at or above this labels the run busy
LOAD_MIN_TESTS = 30       # fewer comparable browser tests: no factor, just the time
SLOW_REQUEST_S = 2.0      # a request slower than this is named on a failure
HUB_LOG = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "hub.log"))
DEV_SPOOLMAN_HOST = "192.168.1.29"
_RUN = {"start": None, "browser": {}}


def _times_of(entry):
    """A history entry's numeric times; anything else in the file reads as
    no history (a bare number used to crash the run's summary line)."""
    if not isinstance(entry, list):
        return []
    return [p for p in entry if isinstance(p, (int, float)) and not isinstance(p, bool)]


def load_factor(times, history, min_tests=LOAD_MIN_TESTS):
    """Median of (this run's call time / the test's fastest recorded time) over
    the tests that have a history; None with fewer than `min_tests` of them."""
    ratios = []
    for nodeid, t in times.items():
        past = [p for p in _times_of(history.get(nodeid)) if p > 0]
        if past and t > 0:
            ratios.append(t / min(past))
    if len(ratios) < min_tests:
        return None
    ratios.sort()
    mid = len(ratios) // 2
    return ratios[mid] if len(ratios) % 2 else (ratios[mid - 1] + ratios[mid]) / 2


def update_history(history, times, keep=TIMING_KEEP):
    """Append this run's call times, keeping each test's `keep` most recent."""
    out = dict(history)
    for nodeid, t in times.items():
        past = _times_of(out.get(nodeid))
        out[nodeid] = (past + [round(float(t), 3)])[-keep:]
    return out


def _read_json(path, default):
    try:
        import json as _json
        with open(path, encoding="utf-8") as f:
            data = _json.load(f)
        return data if isinstance(data, type(default)) else default
    except (OSError, ValueError):
        return default


def _write_json(path, data):
    try:
        import json as _json
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            _json.dump(data, f, indent=0, sort_keys=True)
        os.replace(tmp, path)
    except OSError:
        pass


def hub_log_size(path=HUB_LOG):
    try:
        return os.path.getsize(path)
    except OSError:
        return 0


def _read_from(path, offset):
    try:
        with open(path, "rb") as f:
            f.seek(offset)
            return f.read().decode("utf-8", errors="replace")
    except OSError:
        return ""


def count_spoolman_timeouts(offset, path=HUB_LOG, host=DEV_SPOOLMAN_HOST):
    """Read timeouts to dev Spoolman that FCC logged since byte `offset` of
    hub.log. Only lines naming the dev Spoolman host count: host-side unit tests
    can write a hub.log too (state.py opens a relative path), with mocked hosts.
    A file now smaller than `offset` rotated meanwhile: the rest of the old file
    is `<path>.1`, and the new one is read from its start."""
    try:
        size = os.path.getsize(path)
    except OSError:
        return 0
    if size < offset:
        text = _read_from(path + ".1", offset) + _read_from(path, 0)
    else:
        text = _read_from(path, offset)
    return sum(1 for ln in text.splitlines() if "Read timed out" in ln and host in ln)


def request_start(req):
    """When the browser started `req`, in epoch seconds by its own clock (else
    now). Playwright's sync API dispatches request events only inside a
    Playwright call, so Python's clock at dispatch can be late by however long
    the test spent between calls (a requests.get, a sleep)."""
    try:
        st = (req.timing or {}).get("startTime", -1)
        if st and st > 0:
            return st / 1000.0
    except Exception:
        pass
    return time.time()


def request_duration(req, started, now=None):
    """Seconds a finished request took: the browser's responseEnd (ms after its
    start) when it reported one, else the wall time since `started`."""
    try:
        end = (req.timing or {}).get("responseEnd", -1)
        if end is not None and end >= 0:
            return end / 1000.0
    except Exception:
        pass
    return (time.time() if now is None else now) - started


def format_request_log(net, timeouts, now=None):
    """The section a failed browser test's report gets: its slow requests, the
    ones that never finished, and FCC's dev-Spoolman timeouts during the test.
    It answers "was this red load noise?" without a re-run. `net["pending"]`
    maps each in-flight request to (method, url, start time in epoch seconds)."""
    now = time.time() if now is None else now
    lines = []
    for method, url, took in net.get("slow", []):
        lines.append(f"  slow ({took:.1f} s): {method} {url}")
    for method, url, started in list(net.get("pending", {}).values()):
        lines.append(f"  never finished ({now - started:.1f} s so far): {method} {url}")
    if not lines:
        lines.append(f"  no request took over {SLOW_REQUEST_S:.0f} s")
    lines.append(f"  dev Spoolman read timeouts FCC logged during this test: {timeouts}")
    return "\n".join(lines)


def _short_url(url):
    """Path + query only: the host is always the container."""
    try:
        from urllib.parse import urlsplit as _urlsplit
        parts = _urlsplit(url)
        return parts.path + (("?" + parts.query) if parts.query else "")
    except ValueError:
        return url


# Group 45.1(b): Playwright's `expect` waits 5 s by default, which a loaded
# desktop misses on checks that only say "this eventually shows". An expect
# passes the moment its condition holds, so a longer default slows only a red.
# An explicit `timeout=` still wins; those are triaged site by site (45.1(a)).
EXPECT_TIMEOUT_MS = 10_000


def pytest_configure(config):
    try:
        from playwright.sync_api import expect as _expect
    except ImportError:
        return
    _expect.set_options(timeout=EXPECT_TIMEOUT_MS)


def pytest_sessionstart(session):
    _RUN["start"] = time.time()


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    rep = outcome.get_result()
    net = getattr(item, "_fcc_net", None)
    if rep.when == "call" and rep.passed and "page" in getattr(item, "fixturenames", ()):
        _RUN["browser"][item.nodeid] = rep.duration
    if rep.failed and net is not None and rep.when in ("setup", "call"):
        page = getattr(item, "_fcc_page", None)
        if page is not None:
            try:
                # Let queued request events dispatch first: a request that
                # finished after the last Playwright call isn't still in flight.
                page.wait_for_timeout(1)
            except Exception:
                pass
        try:
            timeouts = count_spoolman_timeouts(getattr(item, "_fcc_hub_offset", 0))
            rep.sections.append(("FCC request log (Group 45.1)", format_request_log(net, timeouts)))
        except Exception:  # diagnostics must never turn a red into an error
            pass


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    """One line at the end of every run: how long it took and, for a run with
    browser tests, how loaded the machine was against this PC's usual times."""
    if _RUN["start"] is None:
        return
    elapsed = int(time.time() - _RUN["start"])
    stats = terminalreporter.stats
    ran = sum(len(stats.get(k, [])) for k in ("passed", "failed", "error"))
    msg = f"⏱️ {elapsed // 60}:{elapsed % 60:02d} for {ran} tests"
    times = dict(_RUN["browser"])
    if times:
        history = _read_json(TIMING_FILE, {})
        factor = load_factor(times, history)
        msg += f" ({len(times)} browser tests passed)"
        if factor is None:
            msg += " · load: no baseline yet for enough of these tests on this PC"
        elif factor >= LOAD_WARN:
            msg += (f" · BUSY RUN: browser tests took {factor:.2f}x their usual time here; "
                    f"re-check any red on its own before believing it")
        else:
            msg += f" · load {factor:.2f}x usual"
        _write_json(TIMING_FILE, update_history(history, times))
    terminalreporter.write_sep("=", msg)


# ---------------------------------------------------------------------------
# Base URL / context overrides
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def base_url() -> str:
    return DEFAULT_BASE_URL


@pytest.fixture(scope="session")
def api_base_url(base_url: str) -> str:
    return base_url.rstrip("/")


@pytest.fixture
def browser_context_args(browser_context_args):
    """Override pytest-playwright's default context args to use our baseline viewport."""
    return {
        **browser_context_args,
        "viewport": BASELINE_VIEWPORT,
    }


@pytest.fixture
def page(page, request):
    """pytest-playwright's page, logging its network for the failure report
    (Group 45.1(c)): requests slower than SLOW_REQUEST_S and requests still in
    flight when the test fails, plus where hub.log stood when the test began.
    Listeners only append to lists, so a passing test pays nothing visible."""
    net = {"slow": [], "pending": {}}

    def _started(req):
        net["pending"][req] = (req.method, _short_url(req.url), request_start(req))

    def _ended(req):
        entry = net["pending"].pop(req, None)
        if entry:
            took = request_duration(req, entry[2])
            if took > SLOW_REQUEST_S:
                net["slow"].append((entry[0], entry[1], took))

    page.on("request", _started)
    page.on("requestfinished", _ended)
    page.on("requestfailed", _ended)
    request.node._fcc_net = net
    request.node._fcc_page = page
    request.node._fcc_hub_offset = hub_log_size()
    return page


# ---------------------------------------------------------------------------
# Buffer helpers
# ---------------------------------------------------------------------------

# JS that defensively unwinds DOM state pollution between sweep tests.
# Use after `page.goto(...)` and before the first interaction. The JS is
# safe to run on a fresh page (everything is best-effort). Group 14
# observed several distinct pollution profiles, each handled below:
#   - Open offcanvas/modal not properly closed by the prior test → its
#     children (selects, buttons) intercept clicks on later-rendered cards.
#   - Orphan .offcanvas-backdrop / .modal-backdrop left at z-index 1040
#     after a hide that didn't run the bootstrap cleanup path.
#   - mountOverlay element (data-overlay-mount="1") left in DOM from a
#     test that crashed before cleanup().
#   - SweetAlert popup not closed.
#   - <select> with non-default selectedIndex keeping its option dropdown
#     open / hit-testable underneath the offcanvas (search material filter
#     was the documented culprit).
#   - Focused element from prior interaction trapping keyboard events.
RESET_DOM_STATE_JS = """() => {
    document.querySelectorAll('.offcanvas.show').forEach((el) => {
        try { bootstrap.Offcanvas.getOrCreateInstance(el).hide(); } catch (_) { /* noop */ }
    });
    document.querySelectorAll('.modal.show').forEach((el) => {
        try { bootstrap.Modal.getOrCreateInstance(el).hide(); } catch (_) { /* noop */ }
    });
    document.querySelectorAll('.offcanvas-backdrop, .modal-backdrop').forEach((bd) => {
        try { bd.remove(); } catch (_) { /* noop */ }
    });
    document.querySelectorAll('[data-overlay-mount="1"]').forEach((el) => {
        try { el.remove(); } catch (_) { /* noop */ }
    });
    if (window.Swal && typeof window.Swal.close === 'function') {
        try { window.Swal.close(); } catch (_) { /* noop */ }
    }
    document.querySelectorAll('select').forEach((s) => {
        try { s.selectedIndex = 0; s.blur(); } catch (_) { /* noop */ }
    });
    if (document.activeElement && document.activeElement.blur) {
        try { document.activeElement.blur(); } catch (_) { /* noop */ }
    }
}"""


@pytest.fixture(scope="session")
def reset_dom_state_js() -> str:
    """The defensive cross-test pollution-teardown JS as a string. Tests run
    it via `page.evaluate(reset_dom_state_js)` after `page.goto(...)`. See
    RESET_DOM_STATE_JS for the per-line pollution patterns it handles."""
    return RESET_DOM_STATE_JS


@pytest.fixture
def open_manage_modal(page, base_url):
    """Open the Location Manager modal for ``loc_id`` with the right
    readiness waits baked in.

    Consolidates the ``_open_manage`` helper that was duplicated across 10+
    e2e tests (Group 16.2, 2026-05-12). The crucial bit is the
    ``state.allLocations.length > 0`` wait — ``window.openManage`` looks up
    that array synchronously and silently no-ops when it's still empty, so
    tests that opened the modal too early would flake whenever sweep order
    pushed the locations fetch out past the fixed sleep (Group 14.4).

    Usage::

        def test_x(open_manage_modal):
            open_manage_modal("XL-1")
            ...
    """
    from playwright.sync_api import expect as _expect

    def _open(loc_id: str) -> None:
        page.goto(base_url)
        page.wait_for_selector("#command-buffer, #buffer-zone", timeout=10000)
        # Wait for state.allLocations to populate so openManage doesn't no-op.
        page.wait_for_function(
            "() => typeof state === 'object' "
            "&& Array.isArray(state.allLocations) "
            "&& state.allLocations.length > 0",
            timeout=10000,
        )
        page.evaluate(f"window.openManage({loc_id!r})")
        _expect(page.locator("#manageModal")).to_be_visible(timeout=8000)
        page.wait_for_timeout(600)

    return _open


# ---------------------------------------------------------------------------
# Bootstrap modal transitions (Group 45.8)
# ---------------------------------------------------------------------------
# Bootstrap 5.3's Modal.hide() returns silently while the modal's show
# transition is still running (its `_isTransitioning` flag; see CLAUDE.md on
# the gating dialogs). A test that opens the wizard and hides it inside that
# ~0.5 s loses the hide and fails on "still visible". Two files were fixed
# before: Group 26.7 retries the hide, and 38.6b waits for the public
# shown.bs.modal event when it opens the wizard (the better fix where a test
# controls the open). Once the dashboard stopped its per-tick fan-out (45.8)
# the page got fast enough that eleven wizard tests in four other files hit it
# in one sweep. This waits out the transition at close time instead.
MODAL_SETTLED_JS = """(id) => {
    const el = document.getElementById(id);
    const m = (el && window.bootstrap) ? bootstrap.Modal.getInstance(el) : null;
    return !m || !m._isTransitioning;
}"""


def wait_modal_settled(page, modal_id: str, timeout: int = 5_000) -> None:
    """Block until Bootstrap modal `modal_id` is not mid-transition, so a
    scripted hide() (or show()) isn't silently dropped."""
    page.wait_for_function(MODAL_SETTLED_JS, arg=modal_id, timeout=timeout)


def close_wizard(page, timeout: int = 5_000) -> None:
    """Close the add/edit wizard past its unsaved-changes guard, once its show
    transition is over, and wait until it is gone."""
    from playwright.sync_api import expect as _expect
    wait_modal_settled(page, "wizardModal", timeout)
    page.evaluate("""
        const m = bootstrap.Modal.getInstance(document.getElementById('wizardModal'));
        if (m) {
            // wizardState is script-scoped, not on window: reference it by name.
            try { wizardState.forceClose = true; wizardState.isDirty = false; } catch (_) {}
            m.hide();
        }
    """)
    _expect(page.locator("#wizardModal")).not_to_be_visible(timeout=timeout)


def own_the_buffer(page, initial):
    """Give `page` its own buffer endpoint (Group 45.8, family D). A test that
    injects spools into state.heldSpools otherwise talks to dev's SHARED server
    buffer: the page's 2 s poll overwrites the injected spool once its 3 s grace
    lapses, and renderBuffer's persist (or the grace path's) POSTs the test's
    spools, real or made-up (#99, #8001, #99999), into dev's buffer, where every
    later page loads them. /api/state/buffer then starts as `initial` and follows
    the page's own persists. Install before page.goto. Returns the stored dict."""
    import json as _json
    held = {"buffer": list(initial)}

    def handle(route):
        if route.request.method == "POST":
            try:
                held["buffer"] = (route.request.post_data_json or {}).get("buffer", [])
            except ValueError:
                pass
            route.fulfill(status=200, content_type="application/json", body='{"success": true}')
        else:
            route.fulfill(status=200, content_type="application/json",
                          body=_json.dumps(held["buffer"]))
    page.route("**/api/state/buffer", handle)
    return held


def quiet_heartbeat(page) -> None:
    """Abort the dashboard's own status polls (the cold /api/logs fetch and
    the /api/dashboard_pulse heartbeat) for a test that injects state those
    polls own: a synthetic log row, a local audit flag. A real answer landing
    between the injection and the assertion repaints that state, and is right
    to (Group 38's lesson); in one sweep it took a 🛑 Review row and closed
    the audit panel (Group 45.8). Install before page.goto."""
    page.route("**/api/dashboard_pulse*", lambda route: route.abort())
    page.route("**/api/logs*", lambda route: route.abort())


# A made-up printer fleet for visual snapshots (readability review,
# 2026-10-21). Once the snapshot comparator compared colours, a capture of the
# live Printer Status (dev's printers, their states, the spools on their heads
# and the grams left) could match its baseline only until the next print.
# Every source the widget reads answers this fixed fleet instead: the
# heartbeat's printer_status section (the heartbeat carries only that and a
# fixed ⚠️ Low stock count, VISUAL_LOW_STOCK, so the log, the other counts and
# the rest of the page stay as loaded) and the
# fan-out's printer map, slot bindings and head contents (which keeps the
# heartbeat's states, as PrusaLink reports them). Each head: (id, bound to a
# box slot, the spool on it).
VISUAL_FLEET = {
    "ZZ Visual XL": {"state": {"state": "PRINTING", "is_active": True}, "heads": [
        ("ZV-1", True, {"id": 9101, "color": "E0A030", "color_direction": "longitudinal", "remaining_weight": 811,
                        "initial_weight": 1000, "display": "#9101 Visual Gold PLA", "material": "PLA"}),
        ("ZV-2", True, None),
        ("ZV-3", True, {"id": 9103, "color": "7B2CBF", "color_direction": "longitudinal", "remaining_weight": 432,
                        "initial_weight": 1000, "display": "#9103 Visual Purple PETG", "material": "PETG"}),
    ]},
    "ZZ Visual INDX": {"state": {"state": "IDLE", "is_active": False}, "heads": [("ZW-1", False, None), ("ZW-2", False, None)]},
}


# The ⚠️ Low stock count the visual fleet's heartbeat carries (Group 57.2), so a
# snapshot shows a real count, the same on every run (Group 57 review: without
# it the button showed its "…" placeholder, the state before any heartbeat).
VISUAL_LOW_STOCK = {"read_ok": True, "count": 7, "low": 3, "out": 4, "threshold_g": 250.0}


def fixed_title_counts(page, backlog=53, queue=0, low=1, out=11) -> None:
    """The title bar's three counts, the same on every run (Group 57 review): the
    bar's room depends on their width, so a test that measures it must not read
    dev's live numbers (a Queue reaching 10 changed the answer). The heartbeat
    is read from dev and its label_backlog / low_stock sections are rewritten
    in this page; the queue answers `queue` made-up items. Install before
    page.goto, after any catch-all route (this one must win)."""
    import json as _json

    def pulse(route):
        resp = route.fetch()
        try:
            body = resp.json()
        except Exception:
            route.fulfill(response=resp)
            return
        if isinstance(body, dict):
            if "label_backlog" in body:
                body["label_backlog"] = {"read_ok": True, "count": backlog, "spools": backlog, "filaments": 0}
            if "low_stock" in body:
                body["low_stock"] = {"read_ok": True, "count": low + out, "low": low, "out": out,
                                     "threshold_g": 250.0}
        route.fulfill(response=resp, body=_json.dumps(body))

    def queue_items(route):
        if route.request.method == "GET":
            items = [{"id": 990000 + i, "type": "spool", "display": f"#{990000 + i}"} for i in range(queue)]
            route.fulfill(status=200, content_type="application/json", body=_json.dumps(items))
        else:
            route.fulfill(status=200, content_type="application/json", body='{"success": true}')

    page.route("**/api/dashboard_pulse*", pulse)
    page.route("**/api/state/queue", queue_items)


def stub_printer_fleet(page, fleet=None) -> None:
    """Answer every source of the Printer Status widget with `fleet`
    (VISUAL_FLEET by default) for this page, so a snapshot that shows the
    widget is the same on every run. Install before page.goto; GETs for
    anything else fall through to earlier routes and the network."""
    import json as _json
    from urllib.parse import parse_qs, unquote, urlsplit
    fleet = fleet or VISUAL_FLEET
    rows, pmap, items, bound = {}, {}, {}, {}
    for name, printer in fleet.items():
        heads = printer["heads"]
        rows[name] = {"state": printer["state"], "toolheads": [
            {"id": hid, "position": i, "unbound": not is_bound, "item": item, "loaded_count": 1 if item else 0}
            for i, (hid, is_bound, item) in enumerate(heads)]}
        pmap[name] = [{"location_id": hid, "position": i} for i, (hid, _b, _item) in enumerate(heads)]
        bound[name] = {hid: [{"box": "ZV-BOX", "slot": str(i + 1)}]
                       for i, (hid, is_bound, _item) in enumerate(heads) if is_bound}
        items.update({hid: item for (hid, _b, item) in heads})

    def handle(route):
        url = urlsplit(route.request.url)
        if url.path.startswith("/api/dashboard_pulse"):
            body = {"printer_status": rows, "low_stock": VISUAL_LOW_STOCK}
        elif url.path == "/api/printer_map":
            body = {"printers": pmap}
        elif url.path.startswith("/api/machine/") and url.path.endswith("/toolhead_slots"):
            name = unquote(url.path[len("/api/machine/"):-len("/toolhead_slots")])
            body = {"toolheads": bound.get(name, {}), "printer_pool": []}
        elif url.path == "/api/get_contents" and (parse_qs(url.query).get("id") or [""])[0].upper() in items:
            item = items[(parse_qs(url.query).get("id") or [""])[0].upper()]
            body = [item] if item else []
        else:
            route.fallback()
            return
        route.fulfill(status=200, content_type="application/json", body=_json.dumps(body))
    page.route("**/api/**", handle)


@pytest.fixture
def clean_buffer(api_base_url: str):
    """Ensure the buffer is empty before the test. Yields the base URL."""
    try:
        requests.post(f"{api_base_url}/api/buffer/clear", timeout=5)
    except requests.RequestException:
        pass
    yield api_base_url


@pytest.fixture
def with_held_spool(api_base_url: str, clean_buffer):
    """Factory: push a spool into the buffer and return its id."""
    def _push(spool_id: int) -> int:
        r = requests.post(
            f"{api_base_url}/api/identify_scan",
            json={"text": f"ID:{spool_id}", "source": "test"},
            timeout=5,
        )
        r.raise_for_status()
        return spool_id

    return _push


# ---------------------------------------------------------------------------
# Dryer box seeders (API + UI flavors)
# ---------------------------------------------------------------------------

@pytest.fixture
def seed_dryer_box(api_base_url: str):
    """API-path seeder: PUT bindings onto a Dryer Box via the new API.

    Signature: seed_dryer_box(box_id, slot_targets={'1': 'XL-1', '2': None, ...})

    Gracefully skips when the bindings endpoint isn't deployed yet (Phase 2
    hasn't shipped) — lets M0 baseline tests run without the new API.
    """
    def _seed(box_id: str, slot_targets: typing.Optional[dict] = None) -> dict:
        if slot_targets is None:
            slot_targets = {}
        try:
            r = requests.put(
                f"{api_base_url}/api/dryer_box/{box_id}/bindings",
                json={"slot_targets": slot_targets},
                timeout=5,
            )
        except requests.RequestException as exc:
            pytest.skip(f"Bindings endpoint unreachable: {exc}")
        if r.status_code == 404:
            pytest.skip("Bindings endpoint not deployed yet (expected before M3)")
        r.raise_for_status()
        return r.json()

    return _seed


@pytest.fixture
def seed_via_ui(api_base_url: str):
    """UI-path seeder: click through Location Manager to set per-slot bindings.

    Exists so every API-seeded test has a UI-path twin. Returns a callable that
    receives a Playwright Page plus the same args as `seed_dryer_box`.

    Phase 2 UI ships with M4 — until then this fixture skips.
    """
    def _seed(page, box_id: str, slot_targets: typing.Optional[dict] = None) -> None:
        pytest.skip("UI bindings path ships with M4; use seed_dryer_box until then.")

    return _seed


# ---------------------------------------------------------------------------
# Borrowing a real dev Dryer Box's slot bindings (2026-09-13 sweep triage, item 3)
# ---------------------------------------------------------------------------
#
# Many E2E tests need a binding such as PM-DB-1 slot 1 -> XL-1. They used to
# snapshot the box's slot_targets at setup and PUT that snapshot back at
# teardown. That restores whatever was OBSERVED, so one run interrupted before
# teardown turns its temporary binding into dev state that every later run
# faithfully restores (dev carried a stale PM-DB-1 slot 1 -> XL-1 until
# 2026-09-13). Borrowing now works against a FIXED baseline instead:
#   - before the first write, the box must hold exactly its baseline, or the
#     test fails loudly WITHOUT touching anything (the leftover might be
#     deliberate hand-made dev state, so it is never silently overwritten);
#   - teardown always PUTs the baseline back, never an observed snapshot.
#
# Why a baseline and not a test-only box: the tests need a single-slot box that
# already exists in dev AND the reset-dev seed (a new row would change every
# location list and visual baseline that renders locations). The PolyMaker boxes
# fit, and their seed state is unbound, so the baseline is simply "no bindings".
#
# Keep this in step with setup-and-rebuild/seeds/locations-seed.json so
# `pytest --reset-dev` restores exactly this state (pinned by
# tests/test_box_binding_loans.py). Borrowing a box that isn't listed fails.
DEV_BOX_BINDING_BASELINES: typing.Dict[str, typing.Dict[str, str]] = {
    "PM-DB-1": {},
    "PM-DB-2": {},
    "PM-DB-4": {},
    "PM-DB-5": {},
    # Group 45.5: the 6-slot test box (Quick-Swap overlays, the printer pool,
    # the multi-slot Feeds save). Its old seed binding {"1": "PRINTER:XL"} was
    # a leftover, not dev state anyone wanted (Derek, 2026-10-13).
    "TST-MDB-1": {},
}


def _normalized_slot_targets(slot_targets) -> typing.Dict[str, str]:
    """Slot keys as strings; unbound slots (None / blank) dropped, the way
    storage drops them (absence == unassigned)."""
    if not isinstance(slot_targets, dict):
        return {}
    return {
        str(k): str(v) for k, v in slot_targets.items()
        if v is not None and str(v).strip() != ""
    }


class BoxBindingLoans:
    """Tracks the dev Dryer Boxes one test has borrowed; see the section note.

    `http` is injectable so the precondition and restore rules can be unit
    tested without a container (tests/test_box_binding_loans.py).
    """

    def __init__(self, api_base_url: str, http=None,
                 baselines: typing.Optional[typing.Dict[str, dict]] = None):
        self.api = api_base_url.rstrip("/")
        self.http = http if http is not None else requests
        self.baselines = DEV_BOX_BINDING_BASELINES if baselines is None else baselines
        self.borrowed: typing.List[str] = []

    def _url(self, box: str) -> str:
        return f"{self.api}/api/dryer_box/{box}/bindings"

    def _current(self, box: str) -> typing.Dict[str, str]:
        try:
            r = self.http.get(self._url(box), timeout=5)
        except requests.RequestException as exc:
            pytest.fail(f"borrow_box_bindings: could not read {box}'s bindings: {exc}",
                        pytrace=False)
        if r.status_code != 200:
            pytest.fail(
                f"borrow_box_bindings: GET {self._url(box)} answered {r.status_code} "
                f"({r.text[:200]!r}). Is {box} still a Dryer Box in dev?",
                pytrace=False,
            )
        return _normalized_slot_targets((r.json() or {}).get("slot_targets"))

    def _put(self, box: str, slot_targets: dict) -> typing.Optional[str]:
        """PUT `slot_targets`; return None on success, else what went wrong."""
        try:
            r = self.http.put(self._url(box), json={"slot_targets": slot_targets}, timeout=5)
        except requests.RequestException as exc:
            return f"{exc}"
        if r.status_code != 200:
            return f"HTTP {r.status_code}: {r.text[:300]}"
        return None

    def borrow(self, box: str, slot_targets: typing.Optional[dict] = None) -> dict:
        """Claim `box` for this test, optionally writing `slot_targets` to it.

        Returns the box's baseline. The first borrow of a box in a test checks
        that it holds exactly its baseline; later borrows of the same box just
        write (the test already owns it).
        """
        if box not in self.baselines:
            pytest.fail(
                f"borrow_box_bindings: {box} has no fixed baseline. Add it to "
                f"conftest.DEV_BOX_BINDING_BASELINES (matching "
                f"setup-and-rebuild/seeds/locations-seed.json) before a test may "
                f"borrow it.",
                pytrace=False,
            )
        baseline = _normalized_slot_targets(self.baselines[box])
        if box not in self.borrowed:
            observed = self._current(box)
            if observed != baseline:
                pytest.fail(
                    f"borrow_box_bindings: {box} is not at its test baseline, so "
                    f"this test did not touch it.\n"
                    f"  expected slot_targets: {baseline!r}\n"
                    f"  found slot_targets:    {observed!r}\n"
                    f"This is usually a binding left behind by an earlier run that "
                    f"was interrupted before teardown (the old fixtures restored "
                    f"whatever they found, so a leftover became permanent). If "
                    f"nobody set it on purpose, put {box} back: Location Manager -> "
                    f"{box} -> Slot -> Toolhead Feeds -> clear every slot -> Save, "
                    f"or PUT {{\"slot_targets\": {baseline!r}}} to "
                    f"/api/dryer_box/{box}/bindings. If it IS deliberate dev "
                    f"state, leave it and point the test at another box.",
                    pytrace=False,
                )
            # Registered BEFORE the write, so a write that half-lands is still
            # put back at teardown.
            self.borrowed.append(box)
        if slot_targets is not None:
            problem = self._put(box, slot_targets)
            if problem:
                pytest.fail(
                    f"borrow_box_bindings: could not set {box} slot_targets to "
                    f"{slot_targets!r}: {problem}",
                    pytrace=False,
                )
        return dict(baseline)

    def restore_all(self) -> None:
        """PUT every borrowed box back to its baseline (latest borrow first).
        Tries every box, then fails loudly naming any that could not be restored."""
        problems = []
        for box in reversed(self.borrowed):
            baseline = _normalized_slot_targets(self.baselines[box])
            problem = self._put(box, baseline)
            if problem:
                problems.append(f"  {box} -> {baseline!r}: {problem}")
        self.borrowed.clear()
        if problems:
            pytest.fail(
                "borrow_box_bindings: teardown could NOT restore these dev boxes to "
                "their baseline; the next run that borrows them will refuse to "
                "start until they are put back:\n" + "\n".join(problems),
                pytrace=False,
            )


@pytest.fixture
def borrow_box_bindings(api_base_url: str):
    """Factory: borrow a dev Dryer Box's slot bindings for one test.

        def test_x(borrow_box_bindings):
            borrow_box_bindings("PM-DB-1", {"1": "XL-1"})   # check baseline, then bind
            borrow_box_bindings("PM-DB-5")                   # check baseline only

    Fails loudly (and changes nothing) when the box isn't at its fixed baseline
    in DEV_BOX_BINDING_BASELINES; teardown always restores that baseline, even
    when the test (or a fixture built on this one) fails or skips.
    """
    loans = BoxBindingLoans(api_base_url)
    yield loans.borrow
    loans.restore_all()


# ---------------------------------------------------------------------------
# Quick-Swap overlay fixture (Group 26.3)
# ---------------------------------------------------------------------------

# The Quick-Swap overlay tests' slot (Group 45.5). TST-MDB-1 is a dev TEST box
# (6 slots, no bindings at its baseline) whose slot 1 holds a virtual dev spool
# (#123 as of 2026-10-13). The fixture used to take the first loaded slot in ANY
# dryer box, which on dev meant Derek's real boxes (CR-MDB-1, then LR-MDB-1),
# and it put back whatever binding it had found there.
QUICKSWAP_TEST_BOX = "TST-MDB-1"
QUICKSWAP_TEST_SLOT = "1"
QUICKSWAP_TEST_TOOLHEAD = "XL-1"


@pytest.fixture
def bound_loaded_slot(api_base_url, borrow_box_bindings):
    """A fixed bound + loaded Quick-Swap slot for overlay/confirm tests.

    The Quick-Swap confirm overlay + bind-picker only render for a slot that is
    (a) bound to a REAL toolhead and (b) actually holds a spool. This borrows
    QUICKSWAP_TEST_BOX through `borrow_box_bindings` (so it must be at its
    fixed baseline, and teardown always restores that baseline) and binds
    QUICKSWAP_TEST_SLOT to QUICKSWAP_TEST_TOOLHEAD. No spool is ever moved.
    Yields ``{"box", "slot", "toolhead", "spool_id"}``.

    Fails, rather than skips, when the slot holds no spool or the toolhead has
    left the fleet: either is dev data drifting under the tests, and a skip
    would hide every test built on this fixture.
    """
    box, slot, toolhead = QUICKSWAP_TEST_BOX, QUICKSWAP_TEST_SLOT, QUICKSWAP_TEST_TOOLHEAD
    pm = requests.get(f"{api_base_url}/api/printer_map", timeout=8).json().get("printers", {})
    toolheads = {
        str(e.get("location_id", "")).strip().upper()
        for entries in pm.values() for e in (entries or [])
    }
    if toolhead not in toolheads:
        pytest.fail(f"bound_loaded_slot: {toolhead} is no longer a toolhead in dev's "
                    f"printer_map; point QUICKSWAP_TEST_TOOLHEAD at one that is.", pytrace=False)
    contents = requests.get(f"{api_base_url}/api/get_contents?id={box}", timeout=8).json() or []
    spool_id = next((it.get("id") for it in contents
                     if str(it.get("slot", "")).replace('"', '').strip() == slot), None)
    if spool_id is None:
        pytest.fail(f"bound_loaded_slot: {box} slot {slot} holds no spool. Put a virtual dev "
                    f"spool there (it held #123); the Quick-Swap overlays only open on a loaded "
                    f"slot.", pytrace=False)
    borrow_box_bindings(box, {slot: toolhead})
    yield {"box": box, "slot": slot, "toolhead": toolhead, "spool_id": spool_id}


@pytest.fixture
def real_toolhead(api_base_url):
    """A pure (non-dual-role) toolhead location id for the bind-slot picker.

    The bind-slot picker's single-toolhead branch only renders for a location
    row typed 'Tool Head' / 'MMU Slot' / 'No MMU Direct Load'. A dual-role
    Printer row (e.g. CORE1, whose sole toolhead is named after the printer
    rather than `<printer>-N`) makes the picker's printer-branch option list
    empty, so it never mounts — which is why `bound_loaded_slot` (which can
    yield CORE1) is wrong for the bind-picker test. Skips when the fleet has no
    pure toolhead.
    """
    pm = requests.get(f"{api_base_url}/api/printer_map", timeout=5).json().get("printers", {})
    toolhead_ids = [
        str(e.get("location_id", "")).strip().upper()
        for entries in pm.values() for e in (entries or [])
        if str(e.get("location_id", "")).strip()
    ]
    locs = requests.get(f"{api_base_url}/api/locations", timeout=8).json()
    rows = locs.get("locations") if isinstance(locs, dict) else locs
    types = {
        str(r.get("LocationID", "")).upper(): str(r.get("Type", ""))
        for r in (rows or [])
    }
    for tid in toolhead_ids:
        t = types.get(tid, "")
        if t and t != "Printer":
            return tid
    pytest.skip("No pure (non-Printer) toolhead in the fleet for the bind picker.")


# ---------------------------------------------------------------------------
# Snapshot / scan helpers
# ---------------------------------------------------------------------------

BASELINE_DIR = os.path.join(os.path.dirname(__file__), "__screenshots__", "chromium-1600x1300")
_UPDATE_BASELINES = os.environ.get("UPDATE_VISUAL_BASELINES", "").lower() in ("1", "true", "yes")

# Per-channel RGB delta a pixel may drift (sub-pixel AA, hinting) and still match.
SNAPSHOT_PIXEL_THRESHOLD = 15


def compare_screenshot(baseline_path: str, actual_bytes: bytes, *,
                       max_diff_pixel_ratio: float = 0.01) -> typing.Optional[str]:
    """Compare a screenshot with its baseline file: None if they match, else
    a human-readable summary (and `<name>.actual.png` / `<name>.diff.png`
    written next to the baseline).

    The images are compared in RGB. Pillow's getbbox() on an RGBA image looks
    at the alpha band only (its `alpha_only` default), and two opaque
    screenshots differ in no alpha at all, so every pair of the same size
    "matched" and only a size change could ever fail (readability review,
    2026-10-21: a solid green image matched confirm-qr-row.png)."""
    from PIL import Image, ImageChops
    import io

    baseline_img = Image.open(baseline_path).convert("RGB")
    actual_img = Image.open(io.BytesIO(actual_bytes)).convert("RGB")

    if baseline_img.size != actual_img.size:
        # Sub-pixel rounding diffs (±1 px in either dimension) routinely
        # appear between isolation runs and the full sweep depending on
        # what else is in the DOM at capture time. Allow ±1 px and let
        # the per-pixel comparison decide via its 1% tolerance. Group 14.4.
        bw, bh = baseline_img.size
        aw, ah = actual_img.size
        if abs(bw - aw) > 1 or abs(bh - ah) > 1:
            actual_path = baseline_path.replace(".png", ".actual.png")
            actual_img.save(actual_path)
            return (
                f"size mismatch: baseline={baseline_img.size} actual={actual_img.size}. See {actual_path}"
            )
        # Resize the smaller image to the larger image's dimensions so the
        # per-pixel diff has matching shapes. NEAREST avoids introducing
        # interpolation artefacts that would themselves count as drift.
        target_size = (max(bw, aw), max(bh, ah))
        if baseline_img.size != target_size:
            baseline_img = baseline_img.resize(target_size, Image.NEAREST)
        if actual_img.size != target_size:
            actual_img = actual_img.resize(target_size, Image.NEAREST)

    diff = ImageChops.difference(baseline_img, actual_img)
    if diff.getbbox() is None:
        return None

    # Count pixels that differ beyond a small per-channel threshold to
    # tolerate font/hinting noise.
    threshold = SNAPSHOT_PIXEL_THRESHOLD
    total_pixels = baseline_img.size[0] * baseline_img.size[1]
    worst = diff.point(lambda p: 255 if p > threshold else 0)
    r, g, b = worst.split()
    over = ImageChops.lighter(ImageChops.lighter(r, g), b)
    diff_pixels = over.histogram()[255]
    ratio = diff_pixels / total_pixels
    if ratio <= max_diff_pixel_ratio:
        return None

    # Write diff artifacts for debugging.
    actual_path = baseline_path.replace(".png", ".actual.png")
    diff_path = baseline_path.replace(".png", ".diff.png")
    actual_img.save(actual_path)
    # Amplify diff so it's visible.
    amplified = diff.point(lambda p: min(255, p * 10))
    amplified.save(diff_path)
    return (
        f"{diff_pixels}/{total_pixels} pixels differ "
        f"(ratio={ratio:.4f}, max allowed={max_diff_pixel_ratio}). "
        f"See {actual_path} and {diff_path}"
    )


@pytest.fixture
def snapshot(pytestconfig, request):
    """Visual regression snapshot helper.

    Usage:
        def test_something(page, snapshot):
            page.goto("/")
            snapshot(page, "dashboard-default")

    Behavior:
    - If the baseline file does not exist, it is created from the current
      screenshot and the test passes (with a captured note on `request.node`).
    - If the baseline exists, the current screenshot is diffed against it.
      Mismatches raise AssertionError with a diff image written next to the
      baseline as `<name>.actual.png` and `<name>.diff.png`.
    - Set env UPDATE_VISUAL_BASELINES=1 to force re-capture (overwrite).

    Tolerance defaults to 1% of pixels allowed to differ. The per-pixel
    threshold accepts tiny RGB drift (sub-pixel AA, hint diffs) without
    marking them as a mismatch.
    """
    from playwright.sync_api import Page, Locator

    def _save(screenshot_bytes: bytes, path: str) -> None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(screenshot_bytes)

    def _capture_locator(locator, screenshot_kwargs=None) -> bytes:
        """Screenshot a locator, expanding the viewport first if the
        element is taller/wider than the current window so content
        that would normally require scrolling inside the modal actually
        lands in the image.

        ``screenshot_kwargs`` are forwarded to ``locator.screenshot`` — use
        ``mask=[locator, ...]`` to blank intentionally-nondeterministic regions
        (e.g. QR codes whose payload embeds a per-render session id) so they
        can't drift the pixel diff. Masked regions are painted a solid color by
        Playwright, so the surrounding layout is still pinned.
        """
        page = locator.page
        # Measure the full scrollable dimensions of the locator (not just
        # the visible portion).
        size = locator.evaluate(
            "el => ({w: Math.max(el.scrollWidth, el.getBoundingClientRect().width),"
            "       h: Math.max(el.scrollHeight, el.getBoundingClientRect().height)})"
        )
        w, h = int(size.get("w", 0)) or BASELINE_VIEWPORT["width"], \
               int(size.get("h", 0)) or BASELINE_VIEWPORT["height"]
        # Pad a little so borders/shadows survive the crop.
        desired = {"width": max(w + 40, BASELINE_VIEWPORT["width"]),
                   "height": max(h + 80, BASELINE_VIEWPORT["height"])}
        try:
            page.set_viewport_size(desired)
            # Scroll the element into view so fixed-position overlays render
            # with their full body visible.
            locator.scroll_into_view_if_needed()
            return locator.screenshot(**(screenshot_kwargs or {}))
        finally:
            page.set_viewport_size(BASELINE_VIEWPORT)

    def _capture_page(page, screenshot_kwargs=None) -> bytes:
        """Full-page screenshot with the viewport expanded to the document
        height so Bootstrap fixed-position elements (navbar, modals) and
        tall scrollable content both end up captured. ``screenshot_kwargs``
        go to ``page.screenshot`` (``mask=[...]`` blanks live regions).
        """
        doc_h = page.evaluate(
            "() => Math.max(document.documentElement.scrollHeight, document.body.scrollHeight)"
        )
        desired = {"width": BASELINE_VIEWPORT["width"],
                   "height": max(int(doc_h or 0), BASELINE_VIEWPORT["height"])}
        try:
            page.set_viewport_size(desired)
            return page.screenshot(full_page=True, **(screenshot_kwargs or {}))
        finally:
            page.set_viewport_size(BASELINE_VIEWPORT)

    def _snap(page_or_locator, name: str, *, max_diff_pixel_ratio: float = 0.01, full_page: bool = True, **kwargs) -> None:
        filename = name if name.endswith(".png") else f"{name}.png"
        baseline_path = os.path.join(BASELINE_DIR, filename)

        # Capture current screenshot as bytes (don't write yet).
        if isinstance(page_or_locator, Locator):
            try:
                actual = _capture_locator(page_or_locator, kwargs)
            except Exception:
                # Fallback: plain locator screenshot if viewport resize
                # isn't supported (e.g. headless context quirk).
                actual = page_or_locator.screenshot(**kwargs)
        else:
            try:
                actual = _capture_page(page_or_locator, kwargs)
            except Exception:
                actual = page_or_locator.screenshot(full_page=full_page, **kwargs)

        baseline_exists = os.path.isfile(baseline_path)
        if _UPDATE_BASELINES or not baseline_exists:
            _save(actual, baseline_path)
            # Tag for reporter; not a failure.
            if not hasattr(request.node, "_visual_baselines_created"):
                request.node._visual_baselines_created = []
            request.node._visual_baselines_created.append(filename)
            return

        diff_msg = compare_screenshot(baseline_path, actual, max_diff_pixel_ratio=max_diff_pixel_ratio)
        if diff_msg is not None:
            raise AssertionError(f"Visual regression for {filename}: {diff_msg}")

    return _snap


@pytest.fixture
def scan(api_base_url: str):
    """Synthetic scan helper — posts directly to /api/identify_scan.

    This is the fast API-path variant. UI-path tests should type into the
    scan input on the dashboard instead of using this fixture.
    """
    def _scan(text: str, source: str = "test") -> dict:
        # `confirmed_fed_heads` as a current page sends it (Group 40.0c): a slot
        # scan whose head runs a spool from elsewhere then asks (head_fed)
        # instead of answering the stale-page "reload" refusal.
        r = requests.post(
            f"{api_base_url}/api/identify_scan",
            json={"text": text, "source": source, "confirmed_fed_heads": []},
            timeout=10,
        )
        r.raise_for_status()
        return r.json()

    return _scan


# ---------------------------------------------------------------------------
# Group 19.1 — opt-in dev-baseline reset before a sweep
# ---------------------------------------------------------------------------

def _wait_for_server(base_url: str, timeout: int = 60) -> None:
    """Poll until the FCC app answers (reset_dev.py docker-restarts it)."""
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        try:
            r = requests.get(base_url, timeout=3)
            if r.status_code < 500:
                return
            last = r.status_code
        except requests.RequestException as exc:
            last = exc
        time.sleep(1.5)
    pytest.exit(
        f"reset-dev: server at {base_url} did not come back within {timeout}s "
        f"(last: {last}).",
        returncode=3,
    )


@pytest.fixture(scope="session", autouse=True)
def _reset_dev_baseline(request):
    """Restore dev to the committed seed baseline before the session — OPT-IN.

    No-op unless `--reset-dev` / `--reset-dev-prune` (or RESET_DEV_BEFORE_SWEEP=1
    / RESET_DEV_PRUNE=1) is set, so a normal single-test run never triggers a
    docker restart or Spoolman reconcile. Intended for FULL sweeps: it runs the
    host `reset_dev.py` (non-destructive restore by default; `--prune` deletes
    sweep-created records too) and waits for the container to come back before
    any test executes. If the reset fails, the session aborts rather than run
    on a dirty baseline.

    Agent-invoked: Derek doesn't run pytest with these flags himself — Claude
    does, on his behalf, and only opts into `--reset-dev-prune` (destructive)
    with Derek's explicit OK. See setup-and-rebuild/reset_dev.py.
    """
    prune = (
        request.config.getoption("--reset-dev-prune")
        or os.environ.get("RESET_DEV_PRUNE", "").lower() in ("1", "true", "yes")
    )
    want = (
        prune
        or request.config.getoption("--reset-dev")
        or os.environ.get("RESET_DEV_BEFORE_SWEEP", "").lower() in ("1", "true", "yes")
    )
    if not want:
        yield
        return

    script = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..",
                     "setup-and-rebuild", "reset_dev.py")
    )
    if not os.path.exists(script):
        pytest.exit(f"reset-dev requested but {script} not found.", returncode=3)
    cmd = [sys.executable, script] + (["--prune"] if prune else [])
    print(f"\n[reset-dev] restoring dev baseline before session: {' '.join(cmd)}")
    try:
        subprocess.run(cmd, check=True, timeout=300)
    except Exception as exc:  # noqa: BLE001
        pytest.exit(
            f"reset-dev failed before sweep ({exc}); aborting so tests don't "
            f"run on a dirty baseline.",
            returncode=3,
        )
    # reset_dev.py docker-restarts inventory_hub — wait for it to answer again.
    _wait_for_server(DEFAULT_BASE_URL)
    yield


# ---------------------------------------------------------------------------
# Utility: skip everything if the dev server isn't reachable
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session", autouse=False)
def require_server(api_base_url: str, pytestconfig):
    """Opt-in fixture for tests that need the live server.

    Kept autouse=False so unit tests don't hit the network. Request it
    explicitly from E2E tests if you want a friendly skip instead of a
    connection error.

    ⚠️ This is NOT gated by --run-integration. That flag guards the real dev
    SPOOLMAN on the NAS; this fixture guards the local FCC container, and the
    two are different services. So whenever the container is UP, ~55 E2E files
    requesting this fixture run — and mutate real dev inventory — even on a
    plain `pytest` run. That surprised everyone (2026-08-03) because the build
    cadence called the plain run "the offline sweep", which it never was.

    `--offline` / FCC_OFFLINE=1 makes that promise real: it skips everything
    that touches the container, giving a genuinely hermetic sweep that cannot
    write to Derek's dev data. Default behaviour is unchanged.
    """
    if _offline_mode(pytestconfig):
        pytest.skip(
            "offline mode (--offline / FCC_OFFLINE=1): skipping tests that "
            "touch the live dev container"
        )
    try:
        r = requests.get(api_base_url, timeout=3)
        if r.status_code >= 500:
            pytest.skip(f"Dev server at {api_base_url} returned {r.status_code}")
    except requests.RequestException as exc:
        pytest.skip(f"Dev server unreachable at {api_base_url}: {exc}")
    return api_base_url


# ---------------------------------------------------------------------------
# Dev Spoolman fixtures (integration tests)
# ---------------------------------------------------------------------------
#
# Centralizes `http://192.168.1.29:7913` so test files don't keep
# duplicating the constant + a `_sm_ok()` helper. The two existing
# integration test files (test_backfill_spool_weights.py,
# test_large_spool_weight_tracking.py) can be migrated to these as a
# follow-up; for now they keep their inline copies to minimize churn.

@pytest.fixture(scope="session")
def dev_spoolman_url() -> str:
    """The URL of the dev Spoolman instance used for integration tests."""
    return DEFAULT_DEV_SPOOLMAN.rstrip("/")


@pytest.fixture(scope="session")
def require_spoolman(dev_spoolman_url: str) -> str:
    """Skip the test if the dev Spoolman isn't reachable.

    Pings `<spoolman>/api/v1/health`. Mirrors the shape of
    `require_server` so opt-in is consistent across the suite.
    """
    try:
        r = requests.get(f"{dev_spoolman_url}/api/v1/health", timeout=3)
    except requests.RequestException as exc:
        pytest.skip(f"Dev Spoolman unreachable at {dev_spoolman_url}: {exc}")
    if not r.ok:
        pytest.skip(f"Dev Spoolman at {dev_spoolman_url} returned {r.status_code}")
    return dev_spoolman_url


# ---------------------------------------------------------------------------
# Throwaway record fixtures (Spoolman integration tests)
# ---------------------------------------------------------------------------
#
# Each integration test creates a uniquely-named filament + spool, exercises
# the path under test, then deletes both in teardown. Names start with
# TEST_RECORD_PREFIX so the orphan-cleanup hook can pick up anything left
# behind by an interrupted run.

def _make_test_name(label: str) -> str:
    """Generate a unique test record name with the canonical prefix."""
    return f"{TEST_RECORD_PREFIX}{label}_{uuid.uuid4().hex[:8]}"


def _delete_record(spoolman_url: str, entity: str, eid) -> None:
    """Best-effort delete of a Spoolman record. Never raises."""
    try:
        requests.delete(f"{spoolman_url}/api/v1/{entity}/{eid}", timeout=5)
    except requests.RequestException:
        pass


def _ensure_test_vendor(spoolman_url: str) -> typing.Optional[int]:
    """Find or create a vendor named `__fcc_test_vendor__` to attach test
    filaments to. Returns the vendor ID or None if Spoolman is unreachable
    (the integration tests are gated by `require_spoolman`, so this is
    purely defensive)."""
    vendor_name = f"{TEST_RECORD_PREFIX}vendor__"
    try:
        r = requests.get(f"{spoolman_url}/api/v1/vendor", timeout=5)
        if r.ok:
            for v in r.json() or []:
                if v.get("name") == vendor_name:
                    return v.get("id")
        c = requests.post(
            f"{spoolman_url}/api/v1/vendor",
            json={"name": vendor_name, "comment": "Auto-created by FCC integration tests"},
            timeout=5,
        )
        if c.ok:
            return (c.json() or {}).get("id")
    except requests.RequestException:
        return None
    return None


@pytest.fixture
def throwaway_filament(require_spoolman: str):
    """Function-scope: create a fresh filament on dev Spoolman.

    Yields the filament dict (parsed from Spoolman's POST response). Hard-
    deletes the record in teardown via DELETE /api/v1/filament/<id>.

    The filament is attached to a long-lived `__fcc_test_vendor__` vendor
    that's auto-created on first use. Vendor records are cheap and rarely
    cause Spoolman validation issues, so we don't recreate them per-test.
    """
    spoolman_url = require_spoolman
    vendor_id = _ensure_test_vendor(spoolman_url)
    name = _make_test_name("filament")
    payload = {
        "name": name,
        "material": "PLA",
        "color_hex": "AABBCC",
        "spool_weight": 250,
        "weight": 1000,
        "density": 1.24,
        "diameter": 1.75,
    }
    if vendor_id is not None:
        payload["vendor_id"] = vendor_id
    r = requests.post(f"{spoolman_url}/api/v1/filament", json=payload, timeout=10)
    if not r.ok:
        pytest.skip(f"Could not create throwaway filament: {r.status_code} {r.text}")
    fil = r.json()
    fid = fil.get("id")
    try:
        yield fil
    finally:
        if fid is not None:
            _delete_record(spoolman_url, "filament", fid)


@pytest.fixture
def throwaway_spool(throwaway_filament, require_spoolman: str):
    """Function-scope: create a fresh spool attached to a fresh filament.

    The default 1000g initial weight matches the parent filament's weight
    so weight-related logic (auto-archive on zero, used_weight cap) doesn't
    fire by accident.
    """
    spoolman_url = require_spoolman
    payload = {
        "filament_id": throwaway_filament.get("id"),
        "initial_weight": 1000,
        "used_weight": 0,
        "first_used": None,
        "last_used": None,
        "comment": f"Created by FCC integration test ({_make_test_name('spool')})",
    }
    r = requests.post(f"{spoolman_url}/api/v1/spool", json=payload, timeout=10)
    if not r.ok:
        pytest.skip(f"Could not create throwaway spool: {r.status_code} {r.text}")
    spool = r.json()
    sid = spool.get("id")
    try:
        yield spool
    finally:
        if sid is not None:
            _delete_record(spoolman_url, "spool", sid)


@pytest.fixture
def throwaway_spool_with_extras(throwaway_filament, require_spoolman: str):
    """Factory fixture: create a spool with a pre-seeded `extra` dict.

    Usage:
        def test_x(throwaway_spool_with_extras):
            spool = throwaway_spool_with_extras({
                "container_slot": "1",
                "physical_source": "PM-DB-XL-L",
            })

    The factory wraps each value via json.dumps because Spoolman stores
    extras as JSON-encoded strings on the wire (see
    `inventory-hub/spoolman_api.py` `JSON_STRING_FIELDS` for context).
    Cleanup runs in fixture teardown for every spool created during the
    test.
    """
    import json as _json
    spoolman_url = require_spoolman
    created_ids: list[int] = []

    def _make(extras: typing.Optional[dict] = None, **kwargs) -> dict:
        wire_extras: dict = {}
        if extras:
            for k, v in extras.items():
                if isinstance(v, str):
                    wire_extras[k] = _json.dumps(v)
                elif isinstance(v, bool):
                    wire_extras[k] = "true" if v else "false"
                else:
                    wire_extras[k] = _json.dumps(v)
        payload = {
            "filament_id": throwaway_filament.get("id"),
            "initial_weight": 1000,
            "used_weight": 0,
            "extra": wire_extras,
        }
        payload.update(kwargs)
        r = requests.post(f"{spoolman_url}/api/v1/spool", json=payload, timeout=10)
        if not r.ok:
            pytest.skip(
                f"Could not create throwaway spool with extras: {r.status_code} {r.text}"
            )
        spool = r.json()
        sid = spool.get("id")
        if sid is not None:
            created_ids.append(sid)
        return spool

    try:
        yield _make
    finally:
        for sid in created_ids:
            _delete_record(spoolman_url, "spool", sid)


@pytest.fixture(autouse=True)
def _cleanup_orphan_test_records(request):
    """Best-effort orphan-cleanup before integration tests run.

    Looks for any filament/spool on dev Spoolman whose name or comment
    starts with `__fcc_test_` and deletes it. Spools are deleted before
    filaments so the FK constraint doesn't reject the filament delete.

    Runs only when integration tests are opted in (so unit-only test
    runs don't waste an HTTP roundtrip). Fails-quiet on every error so a
    transient Spoolman blip doesn't break the whole suite.
    """
    opted_in = (
        request.config.getoption("--run-integration")
        or os.environ.get("RUN_INTEGRATION", "").lower() in ("1", "true", "yes")
    )
    yield
    if not opted_in:
        return
    # Only run the sweep once per session — keyed off a session-scoped flag.
    sess = request.session
    if getattr(sess, "_fcc_orphan_sweep_ran", False):
        return
    sess._fcc_orphan_sweep_ran = True
    try:
        url = DEFAULT_DEV_SPOOLMAN.rstrip("/")
        spools = requests.get(f"{url}/api/v1/spool", timeout=5).json() or []
        for s in spools:
            comment = (s.get("comment") or "")
            if TEST_RECORD_PREFIX in comment:
                _delete_record(url, "spool", s.get("id"))
        fils = requests.get(f"{url}/api/v1/filament", timeout=5).json() or []
        for f in fils:
            name = (f.get("name") or "")
            if name.startswith(TEST_RECORD_PREFIX):
                _delete_record(url, "filament", f.get("id"))
    except requests.RequestException:
        pass


# ---------------------------------------------------------------------------
# Contrast guard
# ---------------------------------------------------------------------------
#
# Gray-on-gray text has been a recurring whack-a-mole: every round of UI
# work has at some point dropped a Bootstrap `text-muted` onto a dark
# surface and produced an unreadable element. A visual snapshot only
# catches the specific placements it happens to capture; this fixture
# catches ANY low-contrast text inside a given root element.
#
# Usage:
#     def test_something(page, assert_contrast):
#         page.goto(...)
#         assert_contrast(page.locator("#fcc-bind-picker-overlay"))

# Background compositing (2026-09-13 sweep triage, item 1). The guard used to
# take the FIRST ancestor background with alpha > 0.01 and use its RGB as if it
# were solid. A translucent tint therefore read as the full-strength colour: the
# printer-status PRINTING chip (#4ade80 text on rgba(16,185,129,0.18)) scored
# 1.46:1 although it renders at ~9.7:1 over the black dashboard, so both
# printer-status contrast tests went red whenever a sweep overlapped a real
# print. PAUSED, ATTENTION and IDLE were false reds too; only OFFLINE passed.
# Now every translucent layer is painted source-over, bottom up, onto the
# nearest opaque ancestor background (then the <html> background, then a default
# dark ground), and the ratio is taken against that composite.
#
# The FOREGROUND is composited too (Group 45.3): translucent text is painted
# source-over onto that composited background and scored as painted. Until then
# it scored at full strength, so white text at 25% on a white 8% tint over black
# (rgb(79,79,79) on rgb(20,20,20), 2.24:1) read as 18.36:1 and passed. The fix
# landed with the OFFLINE chip's text alpha raised 0.45 -> 0.50 in global.css
# (4.41:1 -> 5.28:1 as the guard measures it); the chip stays dimmer than IDLE's 0.6.
#
# Only `background-color` is read. Gradients / images (e.g. .fcc-ps-widget's
# linear-gradient) count as transparent and the walk continues past them.
CONTRAST_GUARD_JS = r"""
(root, opts) => {
    const { minRatio, skipEmpty } = opts;
    if (!root) return { error: 'root_not_found' };

    const relLum = (r, g, b) => {
        const srgb = [r, g, b].map(v => {
            v = v / 255;
            return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);
        });
        return 0.2126 * srgb[0] + 0.7152 * srgb[1] + 0.0722 * srgb[2];
    };
    const ratio = (l1, l2) => {
        const a = Math.max(l1, l2), b = Math.min(l1, l2);
        return (a + 0.05) / (b + 0.05);
    };
    const parseColor = (str) => {
        const m = String(str).match(/rgba?\(([^)]+)\)/);
        if (!m) return null;
        const parts = m[1].split(',').map(s => parseFloat(s.trim()));
        return { r: parts[0], g: parts[1], b: parts[2], a: parts.length > 3 ? parts[3] : 1 };
    };
    const OPAQUE = 0.999;
    const DEFAULT_GROUND = { r: 18, g: 18, b: 18, a: 1 };
    // Source-over: `top` (alpha top.a) painted onto an already-opaque `bottom`.
    const over = (top, bottom) => ({
        r: top.r * top.a + bottom.r * (1 - top.a),
        g: top.g * top.a + bottom.g * (1 - top.a),
        b: top.b * top.a + bottom.b * (1 - top.a),
        a: 1,
    });
    // The colour actually painted behind `el`'s text.
    const effectiveBg = (el) => {
        const translucent = [];   // nearest ancestor first
        let ground = null;
        for (let cur = el; cur && cur !== document.documentElement; cur = cur.parentElement) {
            const bg = parseColor(getComputedStyle(cur).backgroundColor);
            if (!bg || bg.a <= 0.01) continue;
            if (bg.a >= OPAQUE) { ground = bg; break; }
            translucent.push(bg);
        }
        if (!ground) {
            const htmlBg = parseColor(getComputedStyle(document.documentElement).backgroundColor);
            ground = (htmlBg && htmlBg.a >= OPAQUE) ? htmlBg : DEFAULT_GROUND;
        }
        let out = { r: ground.r, g: ground.g, b: ground.b, a: 1 };
        for (let i = translucent.length - 1; i >= 0; i--) out = over(translucent[i], out);
        return { color: out, layers: translucent.length };
    };

    const offenders = [];
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT);
    let el;
    while ((el = walker.nextNode())) {
        const cs = getComputedStyle(el);
        if (cs.display === 'none' || cs.visibility === 'hidden') continue;
        const opacity = parseFloat(cs.opacity || '1');
        if (opacity < 0.05) continue;
        const hasDirectText = Array.from(el.childNodes).some(n =>
            n.nodeType === Node.TEXT_NODE && n.textContent.trim().length > 0
        );
        if (!hasDirectText) continue;
        if (skipEmpty && !el.innerText.trim()) continue;

        const fg = parseColor(cs.color);
        if (!fg) continue;
        const { color: bg, layers } = effectiveBg(el);
        // Translucent text is seen as painted over that background.
        const fgPaint = fg.a >= OPAQUE ? fg : over(fg, bg);
        const r = ratio(relLum(fgPaint.r, fgPaint.g, fgPaint.b), relLum(bg.r, bg.g, bg.b));
        if (r < minRatio) {
            offenders.push({
                tag: el.tagName.toLowerCase(),
                id: el.id || null,
                className: el.className || null,
                text: (el.innerText || '').trim().slice(0, 80),
                fg: `rgb(${Math.round(fgPaint.r)}, ${Math.round(fgPaint.g)}, ${Math.round(fgPaint.b)})`,
                fgAlpha: fg.a >= OPAQUE ? null : fg.a,
                bg: `rgb(${Math.round(bg.r)}, ${Math.round(bg.g)}, ${Math.round(bg.b)})`,
                bgLayers: layers,
                ratio: Number(r.toFixed(2)),
            });
        }
    }
    return { offenders };
}
"""


def contrast_offenders(root_locator, min_ratio: float = 4.5, skip_empty: bool = True) -> list:
    """Every visible text element under `root_locator` whose contrast against
    its composited background is below `min_ratio`, as dicts (tag, id,
    className, text, fg, bg, bgLayers, ratio). Uses locator.evaluate so
    Playwright hands the real element to the JS; no selector-string extraction."""
    result = root_locator.evaluate(
        CONTRAST_GUARD_JS,
        {"minRatio": min_ratio, "skipEmpty": skip_empty},
    )
    if not isinstance(result, dict) or result.get('error') == 'root_not_found':
        raise AssertionError(f"assert_contrast: could not evaluate on locator {root_locator!r}")
    return result.get('offenders') or []


def check_contrast(root_locator, min_ratio: float = 4.5, skip_empty: bool = True) -> None:
    """Raise AssertionError naming every offender (see `contrast_offenders`)."""
    offenders = contrast_offenders(root_locator, min_ratio, skip_empty)
    if offenders:
        msg_lines = [f"Contrast < {min_ratio}:1 for {len(offenders)} element(s):"]
        for o in offenders:
            label = f"<{o['tag']}"
            if o.get('id'):
                label += f" id={o['id']!r}"
            if o.get('className'):
                label += f" class={o['className']!r}"
            label += ">"
            bg_note = ""
            if o.get('bgLayers'):
                bg_note = f" (composited from {o['bgLayers']} translucent layer(s))"
            fg_note = ""
            if o.get('fgAlpha') is not None:
                fg_note = f" (text at alpha {o['fgAlpha']}, as painted)"
            msg_lines.append(
                f"  {label} ratio={o['ratio']}:1  fg={o['fg']}{fg_note}  bg={o['bg']}{bg_note}  text={o['text']!r}"
            )
        raise AssertionError("\n".join(msg_lines))


@pytest.fixture
def assert_contrast():
    """Playwright-driven contrast check against WCAG AA thresholds.

    Walks every text-bearing element under `root_locator`, reads its
    resolved foreground color, composites the translucent ancestor
    backgrounds down to the first opaque one, computes the WCAG relative-
    luminance contrast ratio, and asserts every visible piece of text
    meets `min_ratio` (default 4.5:1, AA for normal text).

    The AssertionError names exactly which elements violated and by how much.
    """
    return check_contrast


# ---------------------------------------------------------------------------
# Text size guard (readability rule, Derek 2026-10-21)
# ---------------------------------------------------------------------------
# Text you read is never under 13.6 px; a label inside a pill or box never under
# 12.8 px (DESIGN.md "Typography"). An element counts as a LABEL when it, or an
# ancestor, is sized with the label name: an inline style that uses
# `--fcc-fs-label`, or a same-origin CSS rule whose font-size (or Bootstrap's
# --bs-badge-font-size) uses it — read from the page's own stylesheets, so a new
# label style needs no list here. Unlike the contrast walker, the ROOT itself is
# judged too, and so is every visible input, select and textarea, by its own
# font size (the text in a form control is no text node of its own). Measured at
# the browser's default size (16 px root): the floors are the Standard text size.
TEXT_FLOOR_PX = 13.6
LABEL_FLOOR_PX = 12.8

TEXT_SIZE_GUARD_JS = r"""
(root, args) => {
    if (!root) return { error: 'root_not_found' };
    const labelSels = ['[style*="--fcc-fs-label"]'];
    const visit = (rules) => {
        for (const r of Array.from(rules || [])) {
            if (r.cssRules && !r.selectorText) { visit(r.cssRules); continue; }   // @media, @supports
            if (!r.style || !r.selectorText) continue;
            const v = (r.style.getPropertyValue('font-size') || '') + ' '
                + (r.style.getPropertyValue('--bs-badge-font-size') || '');
            if (v.indexOf('--fcc-fs-label') !== -1) labelSels.push(r.selectorText);
        }
    };
    for (const sh of Array.from(document.styleSheets)) {
        try { visit(sh.cssRules); } catch (e) { /* a cross-origin sheet (Bootstrap's CDN) */ }
    }
    const usable = labelSels.filter((s) => { try { document.documentElement.matches(s); return true; } catch (e) { return false; } });
    const isLabel = (el) => usable.some((s) => { try { return !!el.closest(s); } catch (e) { return false; } });
    const vis = (el) => {
        try { return el.checkVisibility({ opacityProperty: true, visibilityProperty: true }); }
        catch (e) { return true; }
    };
    const where = (el) => {
        const out = [];
        for (let a = el; a && a.nodeType === 1 && out.length < 4; a = a.parentElement) {
            out.push(a.tagName.toLowerCase() + (a.id ? '#' + a.id : '')
                + ((typeof a.className === 'string' && a.className.trim())
                    ? '.' + a.className.trim().split(/\s+/).slice(0, 2).join('.') : ''));
            if (a.id) break;
        }
        return out.reverse().join(' > ');
    };
    // A form control's text (what was typed, its placeholder, a select's
    // shown choice) is no text node of its own: it is judged by the control's
    // own font size (readability review, 2026-10-21).
    const NO_TEXT_INPUT = /^(checkbox|radio|color|range|hidden|file|image)$/i;
    const isControl = (el) => (el.tagName === 'SELECT' || el.tagName === 'TEXTAREA'
        || (el.tagName === 'INPUT' && !NO_TEXT_INPUT.test(el.type || '')));
    const controlText = (el) => (el.tagName === 'SELECT'
        ? ((el.options[el.selectedIndex] || {}).text || '') : (el.value || el.placeholder || ''));
    const offenders = [];
    let checked = 0;
    let smallest = null;
    for (const el of [root, ...root.querySelectorAll('*')]) {
        if (['SCRIPT', 'STYLE', 'NOSCRIPT', 'TEMPLATE'].includes(el.tagName)) continue;
        const control = isControl(el);
        const own = control || Array.from(el.childNodes).some((n) => n.nodeType === 3 && n.textContent.trim());
        if (!own || !el.getClientRects().length || !vis(el)) continue;
        const r = el.getBoundingClientRect();
        if (r.width * r.height < 4) continue;                    // .visually-hidden and friends
        let op = 1;
        for (let a = el; a && a.nodeType === 1; a = a.parentElement) op *= parseFloat(getComputedStyle(a).opacity || '1');
        if (op < 0.05) continue;                                 // a faded-out layer is not on screen
        const px = parseFloat(getComputedStyle(el).fontSize);
        checked += 1;
        if (smallest === null || px < smallest) smallest = px;
        const label = isLabel(el);
        const floor = label ? args.labelFloor : args.textFloor;
        if (px < floor - 0.05) {
            const text = control ? '[' + el.tagName.toLowerCase() + '] ' + controlText(el)
                : Array.from(el.childNodes).filter((n) => n.nodeType === 3)
                    .map((n) => n.textContent).join(' ').replace(/\s+/g, ' ').trim();
            offenders.push({ px: Math.round(px * 100) / 100, floor, label, text: text.slice(0, 60), where: where(el) });
        }
    }
    return { offenders, checked, smallest };
}
"""


def text_size_offenders(root_locator, text_floor: float = TEXT_FLOOR_PX,
                        label_floor: float = LABEL_FLOOR_PX) -> list:
    """Every visible text element under (and including) `root_locator` whose
    font size is under its floor: 13.6 px for text you read, 12.8 px for a
    label sized with --fcc-fs-label. Dicts: px, floor, label, text, where.
    Raises when the root isn't on the page or no text was checked at all (a
    guard that checked nothing must not pass)."""
    result = root_locator.evaluate(TEXT_SIZE_GUARD_JS, {"textFloor": text_floor, "labelFloor": label_floor})
    if not isinstance(result, dict) or result.get("error"):
        raise AssertionError(f"assert_text_size: could not evaluate on locator {root_locator!r}")
    if not result.get("checked"):
        raise AssertionError(f"assert_text_size: no visible text under {root_locator!r}")
    return result.get("offenders") or []


def check_text_size(root_locator, text_floor: float = TEXT_FLOOR_PX,
                    label_floor: float = LABEL_FLOOR_PX) -> None:
    """Raise AssertionError naming every element under its floor."""
    offenders = text_size_offenders(root_locator, text_floor, label_floor)
    if offenders:
        lines = [f"Text under the size floor ({text_floor} px text, {label_floor} px labels) "
                 f"in {len(offenders)} element(s):"]
        for o in offenders:
            kind = "label" if o["label"] else "text"
            lines.append(f"  {o['px']} px < {o['floor']} ({kind})  {o['where']}  text={o['text']!r}")
        raise AssertionError("\n".join(lines))


@pytest.fixture
def assert_text_size():
    """Playwright-driven text-size check (DESIGN.md "Typography"): every
    visible text under the root is at least 13.6 px, or 12.8 px when it is a
    label sized with --fcc-fs-label. The AssertionError names each offender."""
    return check_text_size


# ---------------------------------------------------------------------------
# A browser that cannot reach anything (for hermetic, --offline browser tests)
# ---------------------------------------------------------------------------

# The browser-wide network block behind `isolated_page`. `context.route` sees
# HTTP(S) only: a WebSocket skips it, whether a page, a frame or a worker opens
# it (review 2026-09-13; a scratch probe had all three reach a local listener).
# `context.route_web_socket` does not close the hole: it mocks page and frame
# sockets, but a worker's still connects, and a handler that calls `ws.close()`
# deadlocks the sync API. So the browser itself is given nowhere to connect:
# every connection must go through a proxy whose hostname can never resolve,
# and the resolver rule fails every hostname inside chromium, so not even a DNS
# query leaves the machine. Loopback goes through the proxy too, which is what
# covers 127.0.0.1:8000 (TestIsolatedBrowser probes a 127.0.0.1 listener).
ISOLATED_PROXY = {"server": "http://fcc-offline-proxy.invalid:9"}
ISOLATED_BROWSER_ARGS = ("--host-resolver-rules=MAP * ~NOTFOUND",)


@pytest.fixture(scope="session")
def _isolated_chromium(playwright):
    """One private headless chromium for the whole session, with no network.

    Reuses pytest-playwright's session `playwright` instance: starting a second
    sync_playwright() while the E2E `page` fixture's instance is running fails.
    Skips (does not fail) when chromium isn't installed on this machine.
    """
    try:
        browser = playwright.chromium.launch(
            headless=True, proxy=ISOLATED_PROXY, args=list(ISOLATED_BROWSER_ARGS))
    except Exception as exc:  # noqa: BLE001 - playwright raises its own Error type
        pytest.skip(
            f"isolated_page: chromium could not launch ({exc}). Install it with "
            f"\"C:/Python314/python.exe\" -m playwright install chromium"
        )
    yield browser
    browser.close()


@pytest.fixture
def isolated_page(_isolated_chromium):
    """A fresh page that cannot reach any network. Build it with
    `page.set_content(...)`; nothing it references, no `goto`, and no fetch,
    WebSocket, frame or worker it starts can reach the FCC container, Spoolman
    or anything else.

    Two layers: the context aborts every HTTP(S) request (an immediate
    net::ERR_FAILED), and `_isolated_chromium`'s dead proxy stops every other
    kind of connection, WebSockets included, and would stop HTTP on its own.

    This is the only sanctioned way to use a browser under --offline: the
    socket guard below polices Python sockets only, not the browser process, so
    the isolation has to live in the browser itself.
    """
    context = _isolated_chromium.new_context(viewport=BASELINE_VIEWPORT)
    context.route("**/*", lambda route: route.abort())
    page = context.new_page()
    try:
        yield page
    finally:
        context.close()


@pytest.fixture(autouse=True)
def _isolate_attr_migration_state(tmp_path, monkeypatch):
    """Keep Group-36 recovery snapshots + the hidden-choice list out of `data/`.

    `attr_migration` writes a recovery snapshot to `inventory-hub/data/` BEFORE
    every destructive schema migration and only deletes it when the migration
    fully succeeds. Unit tests that deliberately drive a restore FAILURE would
    therefore leave a real `attr_recovery_*.json` behind in the repo — which the
    boot re-surface then reports as unresolved data loss on every subsequent
    container start. Same for the hidden-choice list: a test hiding a choice
    must not hide it in Derek's actual dev UI.

    Autouse and repo-wide on purpose: the failure mode is a test silently
    mutating real state, which is exactly the class of problem the `--offline`
    work exists to prevent. Redirecting both paths to `tmp_path` makes it
    structurally impossible rather than a convention each test must remember.

    Host-side only, so it has no effect on the E2E tests driving the container.
    """
    try:
        import attr_migration  # type: ignore
    except ImportError:  # pragma: no cover - backend not importable in this env
        return
    monkeypatch.setattr(attr_migration, "_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(
        attr_migration, "_HIDDEN_PATH", str(tmp_path / "attr_hidden_choices.json")
    )


# --- Group 38.7 — make `--offline` structurally airtight ---------------------
#
# The collection-time gate skips by FIXTURE NAME, which is the right primary
# mechanism (it stops a browser ever launching, which is where the ~27min ->
# ~42s win comes from). But it is only as complete as CONTAINER_FIXTURES: a
# test that reaches the container with a literal URL and takes none of those
# fixtures still runs, and still writes to Derek's real dev inventory. That is
# the whole failure mode `--offline` exists to prevent, so "offline" needs to
# be enforced, not merely intended.
#
# A lint on the string "localhost:8000" was the other option and is strictly
# weaker — it cannot see an f-string, a value read from an env var, or a URL
# built in a helper. Blocking at the socket layer catches every spelling.
#
# Ports, not hosts: 8000 is the FCC dev container, 7913 dev Spoolman, 7912 PROD
# Spoolman. Matching on port covers localhost / 127.0.0.1 / ::1 / the NAS IP
# uniformly (verified: an IPv6 `('::1', 8000, 0, 0)` tuple still exposes the
# port at index 1).
_OFFLINE_BLOCKED_PORTS = frozenset({8000, 7912, 7913})


class OfflineNetworkAccess(requests.exceptions.ConnectionError):
    """Raised when an --offline test tries to reach the container or Spoolman.

    Subclasses `requests.exceptions.ConnectionError` deliberately. Several
    tests already wrap a container call in
    `except requests.RequestException: pytest.skip("Container not responding")`
    — and under `--offline` the container IS unreachable, by policy rather than
    by accident. Inheriting makes those guards do the right thing untouched,
    instead of every one of them needing to learn about a new exception type.

    A test with NO such guard still fails loudly with the message below, which
    is the outcome we want: the leak stays visible rather than being silently
    swallowed.
    """


@pytest.fixture(autouse=True, scope="session")
def _offline_socket_guard(request):
    """Under --offline, refuse any TCP connect to the container / Spoolman.

    Session-scoped and autouse so there is nothing for a test author to
    remember. Outside offline mode this is a no-op, so normal and
    RUN_INTEGRATION runs are completely unaffected.
    """
    if not _offline_mode(request.config):
        yield
        return

    import socket as _socket

    real_connect = _socket.socket.connect

    def _guarded_connect(self, address, *args, **kwargs):
        try:
            port = address[1]
        except (TypeError, IndexError, KeyError):
            # A UNIX socket or anything not (host, port) — not our concern.
            return real_connect(self, address, *args, **kwargs)
        if port in _OFFLINE_BLOCKED_PORTS:
            raise OfflineNetworkAccess(
                f"offline mode blocked a connection to {address!r}. This test "
                f"reaches the live dev container or Spoolman without requesting "
                f"any of CONTAINER_FIXTURES, so the collection-time gate could "
                f"not see it. Either request a gated fixture (e.g. "
                f"`require_server`/`api_base_url`) so it skips offline, or mock "
                f"the call."
            )
        return real_connect(self, address, *args, **kwargs)

    _socket.socket.connect = _guarded_connect
    try:
        yield
    finally:
        _socket.socket.connect = real_connect
