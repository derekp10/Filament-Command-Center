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
                     "seed_via_ui", "scan"):
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
