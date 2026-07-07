"""Regression guard for L28 — frontend lock-up under polling load.

The 2026-05-18 prod repro produced net::ERR_NO_BUFFER_SPACE in Chrome's
console because the six dashboard polling functions fired concurrent
fetches without deduplication. Once a request hung, subsequent 2s/5s
ticks piled up until the OS socket buffer was exhausted, at which point
*every* fetch failed and the frontend appeared frozen.

The fix adds an in-flight guard to each polling function so the next
tick skips while a previous one is still pending. This file pins that
pattern so a future refactor can't quietly remove it.

Each test reads the JS source and asserts the guard variable + early
return + .finally() reset are all present. Pure structural; no server
required.
"""
import os
import re


_HUB = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _read(*parts):
    path = os.path.join(_HUB, *parts)
    assert os.path.exists(path), f"missing: {path}"
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _assert_guard(src, guard_var, fn_signature_pattern, label):
    """Assert a polling function uses guard_var with the canonical pattern:
    declare the flag, early-return when truthy, set to true before fetch,
    reset to false in .finally() (or matching catch).
    """
    assert guard_var in src, f"{label}: missing guard variable '{guard_var}'"
    # Function signature must appear
    assert re.search(fn_signature_pattern, src), (
        f"{label}: missing function signature matching {fn_signature_pattern}"
    )
    # Early-return pattern: `if (<guard>) return`
    assert re.search(rf"if\s*\(\s*{re.escape(guard_var)}\s*\)\s*return", src), (
        f"{label}: missing 'if ({guard_var}) return' early-return"
    )
    # Set to true before fetch
    assert re.search(rf"{re.escape(guard_var)}\s*=\s*true", src), (
        f"{label}: missing '{guard_var} = true' before fetch"
    )
    # Reset to false (in .finally or .catch — either is acceptable)
    assert re.search(rf"{re.escape(guard_var)}\s*=\s*false", src), (
        f"{label}: missing '{guard_var} = false' reset"
    )


def test_update_log_state_inflight_guard():
    """updateLogState (5s heartbeat → /api/logs) was the worst offender:
    no guard AND no .catch(), producing 'Uncaught (in promise) TypeError:
    Failed to fetch' cascades visible in the 2026-05-18 console capture."""
    src = _read("static", "js", "modules", "inv_core.js")
    _assert_guard(
        src,
        guard_var="_updateLogStateInflight",
        fn_signature_pattern=r"const\s+updateLogState\s*=",
        label="updateLogState",
    )
    # And a .catch() must exist on the /api/logs chain — the missing one
    # was the source of the uncaught-rejection cascade.
    assert re.search(
        r"fetch\(['\"]/api/logs['\"]\).*?\.catch\(",
        src,
        flags=re.DOTALL,
    ), "updateLogState: missing .catch() on /api/logs fetch chain"


def test_fetch_locations_inflight_guard():
    """fetchLocations (5s heartbeat when the locations table is visible)."""
    src = _read("static", "js", "modules", "inv_core.js")
    _assert_guard(
        src,
        guard_var="_fetchLocationsInflight",
        fn_signature_pattern=r"const\s+fetchLocations\s*=",
        label="fetchLocations",
    )
    assert re.search(
        r"fetch\(['\"]/api/locations['\"]\).*?\.catch\(",
        src,
        flags=re.DOTALL,
    ), "fetchLocations: missing .catch() on /api/locations fetch chain"


def test_load_buffer_inflight_guard():
    """loadBuffer (2s setInterval → /api/state/buffer). Reuses the
    existing window.isBufferSyncing flag — already cleared in both
    .then() and .catch() branches — and now also early-returns when set.
    """
    src = _read("static", "js", "modules", "inv_cmd.js")
    assert re.search(r"const\s+loadBuffer\s*=", src), "loadBuffer: signature missing"
    assert re.search(
        r"const\s+loadBuffer\s*=\s*\(\s*\)\s*=>\s*\{[^}]*?if\s*\(\s*window\.isBufferSyncing\s*\)\s*return",
        src,
        flags=re.DOTALL,
    ), "loadBuffer: missing 'if (window.isBufferSyncing) return' early-return at function head"


def test_live_refresh_buffer_inflight_guard():
    """liveRefreshBuffer (5s sync-pulse → /api/spools/refresh)."""
    src = _read("static", "js", "modules", "inv_cmd.js")
    _assert_guard(
        src,
        guard_var="_liveRefreshInflight",
        fn_signature_pattern=r"const\s+liveRefreshBuffer\s*=",
        label="liveRefreshBuffer",
    )


def test_refresh_manage_view_inflight_guard():
    """refreshManageView (5s sync-pulse while the manage modal is open
    → /api/get_contents)."""
    src = _read("static", "js", "modules", "inv_loc_mgr.js")
    _assert_guard(
        src,
        guard_var="_refreshManageViewInflight",
        fn_signature_pattern=r"window\.refreshManageView\s*=",
        label="refreshManageView",
    )
    assert re.search(
        r"fetch\(`?/api/get_contents.*?\.catch\(",
        src,
        flags=re.DOTALL,
    ), "refreshManageView: missing .catch() on get_contents fetch chain"


def test_load_queue_inflight_guard():
    """loadQueue (2s setInterval → /api/state/queue) is the structural twin
    of loadBuffer (same cadence, same tiny /api/state/* local-JSON endpoint,
    same socket-exhaustion vector) but was left OUT of the original L28 sweep.
    Guarded 2026-07-06 after the buglist fixability triage surfaced it."""
    src = _read("static", "js", "modules", "inv_queue.js")
    _assert_guard(
        src,
        guard_var="_loadQueueInflight",
        fn_signature_pattern=r"const\s+loadQueue\s*=",
        label="loadQueue",
    )
    assert re.search(
        r"fetch\(['\"]/api/state/queue['\"]\).*?\.catch\(",
        src,
        flags=re.DOTALL,
    ), "loadQueue: missing .catch() on /api/state/queue fetch chain"


def test_printer_status_inflight_guard_unchanged():
    """Printer Status widget already had an inflight guard before L28;
    pin it so the regression net catches anyone who removes it."""
    src = _read("static", "js", "modules", "inv_printer_status.js")
    assert "inFlight: false" in src, "printer status: state.inFlight default missing"
    assert re.search(
        r"if\s*\(\s*_state\.inFlight\s*\)\s*return",
        src,
    ), "printer status: missing 'if (_state.inFlight) return' guard"
    assert re.search(
        r"_state\.inFlight\s*=\s*false",
        src,
    ), "printer status: missing reset of _state.inFlight"


# ---------------------------------------------------------------------------
# Runtime verification (the "this actually works in a real browser" test).
#
# The structural tests above pin the source-level pattern. This one drives
# a real Chrome via Playwright with /api/logs hung indefinitely (route
# handler never calls fulfill/continue/abort) and confirms the heartbeat
# guard prevents subsequent ticks from piling up requests.
# ---------------------------------------------------------------------------

def test_updateLogState_runtime_guard_when_logs_endpoint_hangs(
    page, require_server, base_url
):
    """The L28 prod repro in test form: when /api/logs is slow/hung, the
    heartbeat guard must prevent subsequent ticks from firing more requests
    on top of the in-flight one. Pre-fix, the initial poll + every 5s
    heartbeat fired regardless — that pile-up was the socket-buffer-
    exhaustion vector.

    Strategy: route /api/logs to a handler that never resolves. The fetch
    promise stays pending forever, .finally() never runs, so
    _updateLogStateInflight stays true. With the guard, only the initial
    force=true poll on DOMContentLoaded fires; every subsequent heartbeat
    tick bails. Without the guard, we'd see initial + 2+ ticks.
    """
    log_request_count = {"n": 0}

    def track(req):
        if "/api/logs" in req.url:
            log_request_count["n"] += 1

    page.on("request", track)

    # Hang: handler intentionally does nothing. Playwright keeps the
    # request pending until the page closes. From JS's perspective, the
    # fetch promise never settles. (Playwright may emit a warning about
    # an unhandled route — expected.)
    page.route("**/api/logs", lambda route: None)

    page.goto(base_url, wait_until="domcontentloaded")

    # Smart Sync = 5s. Wait through initial force=true + 2 heartbeat ticks.
    # Post-fix expectation: 1 request (initial only — subsequent ticks
    # guarded out). Pre-fix this would be 3 (initial + ticks at t=5, t=10).
    page.wait_for_timeout(12_000)

    assert log_request_count["n"] == 1, (
        f"Expected exactly 1 /api/logs request (initial force=true; guard "
        f"should skip subsequent heartbeats while the first is pending), "
        f"got {log_request_count['n']}. The in-flight guard isn't working."
    )
