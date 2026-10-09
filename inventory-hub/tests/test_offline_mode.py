"""`--offline` must stay genuinely hermetic.

Background (2026-08-03):
  The build cadence documented `pytest tests/ -q` as "the full OFFLINE sweep",
  with `RUN_INTEGRATION=1` as the separate integration/E2E sweep. That model was
  wrong. `--run-integration` gates only `@pytest.mark.integration`, which marks
  tests hitting the real dev SPOOLMAN on the NAS. Tests hitting the local FCC
  container go through the `require_server` fixture, which skips only when that
  container is DOWN — so with the container up, ~55 E2E files ran on every
  routine verification and mutated Derek's real dev inventory.

  That is also the leading suspect for the load-sensitive flake family: a
  captured traceback showed `test_clone_e2e` failing because the spool row it
  needed simply wasn't there, i.e. a concurrent test had moved it.

`--offline` / FCC_OFFLINE=1 makes the promise real. Measured on the full suite:
27 minutes -> 42 seconds, and nothing can touch dev data.

The skip happens at COLLECTION time and keys off FIXTURE NAMES, which is the
subtle part these tests defend: gating the `require_server` fixture alone is NOT
enough, because a Playwright test can request `page` without `require_server`
and would still launch a browser against localhost:8000.
"""
from __future__ import annotations

import conftest


class TestContainerFixtureCoverage:
    def test_page_is_treated_as_container_touching(self):
        """`page` is THE one that makes fixture-name gating necessary."""
        assert "page" in conftest.CONTAINER_FIXTURES, (
            "the Playwright `page` fixture must count as container-touching — "
            "a test can take it WITHOUT require_server and still drive the "
            "live dev container, which is exactly the hole --offline closes"
        )

    def test_require_server_is_covered(self):
        assert "require_server" in conftest.CONTAINER_FIXTURES

    def test_data_mutating_fixtures_are_covered(self):
        """These write to real dev inventory; offline must never select them."""
        for name in ("clean_buffer", "with_held_spool", "seed_dryer_box",
                     "seed_via_ui", "scan", "borrow_box_bindings"):
            assert name in conftest.CONTAINER_FIXTURES, (
                f"{name} mutates dev data but is not gated by --offline"
            )


class TestOfflineModeDetection:
    def test_env_var_enables_offline(self, monkeypatch):
        monkeypatch.setenv("FCC_OFFLINE", "1")
        assert conftest._offline_mode(_NoFlagConfig()) is True

    def test_env_var_accepts_the_usual_truthy_spellings(self, monkeypatch):
        for val in ("1", "true", "TRUE", "yes"):
            monkeypatch.setenv("FCC_OFFLINE", val)
            assert conftest._offline_mode(_NoFlagConfig()) is True, val

    def test_absent_env_and_flag_means_normal_run(self, monkeypatch):
        monkeypatch.delenv("FCC_OFFLINE", raising=False)
        assert conftest._offline_mode(_NoFlagConfig()) is False

    def test_arbitrary_env_value_does_not_enable_offline(self, monkeypatch):
        """A stray value must not silently make the sweep skip everything —
        that would look like a green run while testing almost nothing."""
        monkeypatch.setenv("FCC_OFFLINE", "0")
        assert conftest._offline_mode(_NoFlagConfig()) is False
        monkeypatch.setenv("FCC_OFFLINE", "later")
        assert conftest._offline_mode(_NoFlagConfig()) is False

    def test_missing_option_is_tolerated(self, monkeypatch):
        """_offline_mode must not explode when the option isn't registered
        (nested/!sub-configs), or it would break unrelated runs."""
        monkeypatch.delenv("FCC_OFFLINE", raising=False)

        class _Exploding:
            def getoption(self, name):
                raise ValueError("no such option")

        assert conftest._offline_mode(_Exploding()) is False


class _NoFlagConfig:
    """Stands in for a pytest config where --offline was not passed."""

    def getoption(self, name):
        return False


class TestCollectionHookItself:
    """Group 38.8 — the hook was never tested, only the constant and the parser.

    `test_page_is_treated_as_container_touching` proves `page` is in the SET;
    it proves nothing about whether the hook consults that set correctly. The
    hook is the part that actually stops a browser launching against Derek's
    live container, so it gets pinned directly. (It is exercised implicitly on
    every offline run — but an implicit exercise reports nothing when it breaks.)
    """

    class _Cfg:
        def __init__(self, offline):
            self._offline = offline

        def getoption(self, name):
            if name == "--offline":
                return self._offline
            if name == "--run-integration":
                return False
            return False

    class _Item:
        def __init__(self, name, fixturenames, keywords=()):
            self.name = name
            self.fixturenames = tuple(fixturenames)
            self.own_markers = []
            self.keywords = set(keywords)

        def add_marker(self, marker):
            self.own_markers.append(marker)

        def get_closest_marker(self, name):
            return None

        @property
        def skipped(self):
            return any(getattr(m, "name", "") == "skip" for m in self.own_markers)

    def _run(self, monkeypatch, offline, items):
        monkeypatch.delenv("FCC_OFFLINE", raising=False)
        monkeypatch.delenv("RUN_INTEGRATION", raising=False)
        conftest.pytest_collection_modifyitems(self._Cfg(offline), items)
        return items

    def test_offline_skips_an_item_requesting_a_container_fixture(self, monkeypatch):
        item = self._Item("t_e2e", ["page"])
        self._run(monkeypatch, True, [item])
        assert item.skipped, "an item taking `page` must be skipped offline"
        reason = getattr(item.own_markers[0], "kwargs", {}).get("reason", "")
        assert "offline" in reason.lower()

    def test_offline_leaves_a_hermetic_item_alone(self, monkeypatch):
        item = self._Item("t_unit", ["monkeypatch", "tmp_path"])
        self._run(monkeypatch, True, [item])
        assert not item.skipped, (
            "a test requesting no container fixture must still RUN offline — "
            "over-skipping would quietly hollow out the fast sweep"
        )

    def test_a_normal_run_skips_nothing_for_offline_reasons(self, monkeypatch):
        item = self._Item("t_e2e", ["page"])
        self._run(monkeypatch, False, [item])
        assert not item.skipped, "--offline is opt-in; a normal run must be unchanged"

    def test_every_gated_fixture_name_actually_triggers_the_hook(self, monkeypatch):
        """The set and the hook must agree for EVERY name, not just `page`."""
        for name in sorted(conftest.CONTAINER_FIXTURES):
            item = self._Item(f"t_{name}", [name])
            self._run(monkeypatch, True, [item])
            assert item.skipped, f"{name} is in CONTAINER_FIXTURES but did not skip"

    def test_offline_keeps_an_isolated_browser_test(self, monkeypatch):
        """A hermetic browser test (the contrast-guard compositing proof) takes
        `isolated_page` and must still RUN offline — that is its whole point."""
        item = self._Item("t_isolated", ["isolated_page", "_isolated_chromium", "playwright",
                                         "assert_contrast", "request"])
        self._run(monkeypatch, True, [item])
        assert not item.skipped


class _LocalListener:
    """A TCP listener on 127.0.0.1 with a random port. Records the first line of
    every connection that arrives, then hangs up, so a WebSocket handshake fails
    fast instead of waiting out a timeout."""

    def __enter__(self):
        import socket
        import threading

        self._sock = socket.socket()
        self._sock.bind(("127.0.0.1", 0))
        self._sock.listen(8)
        self._sock.settimeout(0.1)
        self.base = f"127.0.0.1:{self._sock.getsockname()[1]}"
        self.arrived = []
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()
        return self

    def _serve(self):
        import socket

        while not self._stop.is_set():
            try:
                conn, _ = self._sock.accept()
            except socket.timeout:
                continue
            except OSError:
                return
            with conn:
                conn.settimeout(1.0)
                try:
                    first = conn.recv(256).split(b"\r\n", 1)[0]
                except OSError:
                    first = b""
            self.arrived.append(first.decode("latin-1") or "<connected, sent nothing>")

    def connections_after_settling(self, settle=0.3):
        import time

        time.sleep(settle)  # let a late connection land before anyone says "none"
        return list(self.arrived)

    def __exit__(self, *exc_info):
        self._stop.set()
        self._thread.join(2)
        self._sock.close()


def _in_worker(body):
    """A page-side probe that runs `body` inside a dedicated (blob) worker."""
    return (
        "(base) => new Promise((done) => {"
        " const src = `" + body + "`;"
        " const worker = new Worker(URL.createObjectURL(new Blob([src], {type: 'text/javascript'})));"
        " worker.onmessage = (m) => done(m.data);"
        " worker.onerror = (e) => done('worker did not start: ' + e.message);"
        " setTimeout(() => done('timeout'), 5000); })"
    )


# Each probe takes the listener's host:port and resolves 'reached' if the
# connection opened (or the fetch got an answer) and 'blocked' if it failed.
_ESCAPE_PROBES = {
    "page-fetch": (
        "(base) => fetch(`http://${base}/api/locations`, {mode: 'no-cors'})"
        ".then(() => 'reached', () => 'blocked')"),
    "page-websocket": (
        "(base) => new Promise((done) => {"
        " const ws = new WebSocket(`ws://${base}/api/ws`);"
        " ws.onopen = () => done('reached');"
        " ws.onerror = ws.onclose = () => done('blocked');"
        " setTimeout(() => done('timeout'), 5000); })"),
    "frame-websocket": (
        "(base) => new Promise((done) => {"
        " addEventListener('message', (m) => done(m.data), {once: true});"
        " const frame = document.createElement('iframe');"
        " frame.srcdoc = `<script>const ws = new WebSocket('ws://${base}/api/ws');"
        " ws.onopen = () => parent.postMessage('reached', '*');"
        " ws.onerror = ws.onclose = () => parent.postMessage('blocked', '*');</script>`;"
        " document.body.appendChild(frame);"
        " setTimeout(() => done('timeout'), 5000); })"),
    "worker-fetch": _in_worker(
        "fetch('http://${base}/api/locations', {mode: 'no-cors'})"
        ".then(() => postMessage('reached'), () => postMessage('blocked'));"),
    "worker-websocket": _in_worker(
        "const ws = new WebSocket('ws://${base}/api/ws');"
        " ws.onopen = () => postMessage('reached');"
        " ws.onerror = ws.onclose = () => postMessage('blocked');"),
}


def _probe_every_channel(page):
    """{channel: (what the page saw, connections that reached a fresh listener)}.
    Navigation goes last: a failed goto leaves the page on an error page."""
    from playwright.sync_api import Error as PlaywrightError

    results = {}
    for channel, probe in _ESCAPE_PROBES.items():
        with _LocalListener() as listener:
            page.set_content("<p>isolated</p>")
            outcome = page.evaluate(probe, listener.base)
            results[channel] = (outcome, listener.connections_after_settling())
    with _LocalListener() as listener:
        try:
            page.goto(f"http://{listener.base}/api/locations", timeout=10000)
            outcome = "reached"
        except PlaywrightError as exc:
            outcome = str(exc).splitlines()[0]
        results["navigation"] = (outcome, listener.connections_after_settling())
    return results


def _assert_nothing_escaped(results):
    leaked = {channel: arrived for channel, (_, arrived) in results.items() if arrived}
    assert leaked == {}, f"these channels reached a local listener: {leaked}"
    unblocked = {channel: outcome for channel, (outcome, _) in results.items()
                 if channel != "navigation" and outcome != "blocked"}
    assert unblocked == {}, f"these probes did not fail cleanly: {unblocked}"
    assert results["navigation"][0] != "reached", results["navigation"]


class TestIsolatedBrowser:
    """2026-09-13 — a browser may run under --offline, but only one that cannot
    reach anything. The socket guard below only sees Python sockets, not the
    browser process, so the isolation has to live in the browser.

    Every probe aims at a Python listener on 127.0.0.1 with a random port: a
    real, reachable target that WOULD accept the connection if the isolation
    leaked, so a pass cannot come from a hostname that merely fails to resolve
    (which is all the old `.invalid` fetch check proved). Never the container.
    """

    def test_isolated_browser_fixtures_are_not_gated(self):
        for name in ("isolated_page", "_isolated_chromium", "playwright", "assert_contrast"):
            assert name not in conftest.CONTAINER_FIXTURES, name

    def test_isolated_page_reaches_nothing_on_any_channel(self, isolated_page):
        """Review 2026-09-13: the context route saw HTTP only, so a WebSocket
        from the page, a frame or a worker reached the listener. The route still
        answers HTTP first, which is what the ERR_FAILED on navigation shows."""
        results = _probe_every_channel(isolated_page)
        _assert_nothing_escaped(results)
        assert "net::ERR_FAILED" in results["navigation"][0], results["navigation"]

    def test_the_isolated_browser_blocks_every_channel_even_without_routes(self, _isolated_chromium):
        """The dead proxy is the layer that stops WebSockets. Prove it holds on
        its own, so losing the context route could not open a hole either."""
        context = _isolated_chromium.new_context()
        try:
            _assert_nothing_escaped(_probe_every_channel(context.new_page()))
        finally:
            context.close()


class TestOfflineSocketGuard:
    """Group 38.7 — fixture-name gating is only as complete as the set.

    A test that reaches the container with a literal URL while requesting none
    of CONTAINER_FIXTURES is invisible to the collection gate and still writes
    to real dev inventory. The socket guard makes offline structurally airtight
    rather than merely intended.
    """

    def test_the_container_and_spoolman_ports_are_blocked(self):
        for port in (8000, 7912, 7913):
            assert port in conftest._OFFLINE_BLOCKED_PORTS, (
                f"port {port} reaches the dev container or Spoolman and must be "
                f"blocked under --offline"
            )

    def test_an_offline_run_cannot_reach_the_container(self, pytestconfig):
        """The guard is live in THIS process whenever the suite runs offline.

        Self-verifying: if the run is offline the connect must be refused; if
        it is not offline the test states so rather than silently passing.

        `offline` comes from `conftest._offline_mode(pytestconfig)`, not from
        the env var — the `--offline` CLI flag and FCC_OFFLINE are two
        independent switches, and reading only one made this test disagree with
        the guard it is checking.
        """
        import socket

        offline = conftest._offline_mode(pytestconfig)
        s = socket.socket()
        s.settimeout(2)
        try:
            s.connect(("127.0.0.1", 8000))
            s.close()
            assert not offline, (
                "offline mode allowed a TCP connection to the dev container on "
                "port 8000 — the socket guard is not installed"
            )
        except conftest.OfflineNetworkAccess:
            assert offline, "the guard fired outside offline mode"
        except OSError:
            # Container simply not listening — says nothing either way.
            pass
        finally:
            try:
                s.close()
            except OSError:
                pass
