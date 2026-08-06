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
