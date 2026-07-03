"""L316 characterization tests — pins pre-carve behavior of the monitor/boot
seam (app.py 6096-7429). Generated from the 2026-07-01 coverage audit. Do not
weaken these to make a refactor pass.

Covers, WITHOUT ever starting the cancel-monitor daemon thread:

1. _fcc_owns_completion_deduct — the REAL body (every deduct test patches it
   as a seam; the actual config read / default / exception-swallow was unpinned).
2. _seed_printer_credentials_from_filabridge — the boot path that can WRITE
   locations.json + a .bak. All disk/network is mocked.
3. _cancel_monitor_loop resilience — recovery-before-first-tick, tick errors
   swallowed, adaptive sleep cadence. The infinite loop is escaped with a
   BaseException-derived sentinel (the loop's protections catch `Exception`
   only, so the sentinel passes through them untouched — meaning every assert
   below exercised the REAL try/except structure).
4. _check_audit_idle_timeout — ONLY the branches test_audit_auto_park_unknown.py
   does not already pin (inactive no-op; exact log-line details).

No live server, no live Spoolman, no daemon threads, no real file writes.
"""
from __future__ import annotations

import os
import sys
import time as _time
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import app as app_module
import startup_migrations  # L316: the seed calls the prune helper module-qualified
import print_monitor  # L316: patch targets for moved symbols  # noqa: E402
import state  # noqa: E402


class _StopLoop(BaseException):
    """Sentinel to escape _cancel_monitor_loop's `while True`.

    Derives from BaseException ON PURPOSE: the loop's tick guard is
    `except Exception`, so this sentinel is NOT swallowed by the very
    protection under test — raising it from tick or sleep is the only way
    to exit the loop while still proving the `except Exception` clause
    caught what it was supposed to catch.
    """


# ---------------------------------------------------------------------------
# 1. _fcc_owns_completion_deduct — real config read
# ---------------------------------------------------------------------------

def test_completion_flag_absent_defaults_false():
    """The Phase-2 cutover flag defaults OFF: an absent key must read False so
    a fresh/blank config never fires FCC's completion deduct (double-deduct
    risk if FilaBridge were ever revived)."""
    with patch.object(app_module.config_loader, "load_config", return_value={}):
        assert app_module._fcc_owns_completion_deduct() is False


def test_completion_flag_true():
    """Flag present and True -> True. This is the live prod configuration since
    the 2026-06-13 cutover; if a carve breaks this read, completion deducts
    silently stop with zero signal."""
    with patch.object(app_module.config_loader, "load_config",
                      return_value={"fcc_owns_completion_deduct": True}):
        assert app_module._fcc_owns_completion_deduct() is True


def test_completion_flag_explicit_false():
    """Flag present and False -> False (rollback posture)."""
    with patch.object(app_module.config_loader, "load_config",
                      return_value={"fcc_owns_completion_deduct": False}):
        assert app_module._fcc_owns_completion_deduct() is False


def test_completion_flag_config_read_exception_swallowed_to_false():
    """A raising load_config must be swallowed to False — the flag check runs
    on the FINISHED edge inside the monitor; it must never propagate."""
    with patch.object(app_module.config_loader, "load_config",
                      side_effect=RuntimeError("config unreadable")):
        assert app_module._fcc_owns_completion_deduct() is False


def test_completion_flag_none_config_swallowed_to_false():
    """load_config returning None (not a dict) -> the AttributeError from
    None.get() is swallowed by the same except -> False."""
    with patch.object(app_module.config_loader, "load_config", return_value=None):
        assert app_module._fcc_owns_completion_deduct() is False


def test_completion_flag_truthiness_coercion():
    """The flag value is bool()-coerced, NOT parsed: any non-empty string —
    including the string 'false' — reads as True, while ''/0 read as False.
    # NOTE: pins current behavior; see suspected_bugs (a hand-edited config
    # with "fcc_owns_completion_deduct": "false" would ENABLE the deduct).
    """
    for raw, expected in [("false", True), ("yes", True), (1, True),
                          ("", False), (0, False), (None, False)]:
        with patch.object(app_module.config_loader, "load_config",
                          return_value={"fcc_owns_completion_deduct": raw}):
            assert app_module._fcc_owns_completion_deduct() is expected, (
                f"bool coercion drifted for raw={raw!r}"
            )


# ---------------------------------------------------------------------------
# 2. _seed_printer_credentials_from_filabridge — boot seed orchestration
# ---------------------------------------------------------------------------

def _seeded_rows():
    """Steady-state fleet: every Printer row already has creds. Includes a
    Tool Head without creds and a non-dict junk entry, neither of which may
    trigger the seed."""
    return [
        {"LocationID": "XL", "Type": "Printer", "Name": "XL",
         "printer_creds": {"ip_address": "192.168.1.50", "api_key": "K"}},
        {"LocationID": "XL-1", "Type": "Tool Head", "Name": "XL T1"},
        "junk-non-dict-row",
    ]


def _unseeded_rows():
    """One Printer row missing creds entirely -> needs seed."""
    return [
        {"LocationID": "XL", "Type": "Printer", "Name": "XL",
         "printer_creds": {"ip_address": "192.168.1.50", "api_key": "K"}},
        {"LocationID": "CORE1", "Type": "Printer", "Name": "Core One"},
    ]


def test_seed_steady_state_no_network_no_write():
    """The path that runs on EVERY prod boot now that FilaBridge is
    decommissioned: all Printer rows have creds -> NO FilaBridge pull, NO
    seed, NO save. Tool Head rows without creds and non-dict rows must not
    count as needing seed."""
    with patch.object(app_module.locations_db, "load_locations_list",
                      return_value=_seeded_rows()), \
         patch.object(app_module.prusalink_api, "fetch_all_filabridge_printers") as fetch, \
         patch.object(app_module.locations_db, "seed_printer_credentials") as seed, \
         patch.object(app_module.locations_db, "save_locations_list") as save, \
         patch.object(app_module.state, "logger", MagicMock()):
        app_module._seed_printer_credentials_from_filabridge()
    fetch.assert_not_called()
    seed.assert_not_called()
    save.assert_not_called()


def test_seed_nonprinter_row_missing_creds_never_triggers():
    """A credential-less NON-Printer row alone must not trigger the network
    pull — the needs-seed predicate is scoped to Type=='printer' rows."""
    rows = [{"LocationID": "XL-1", "Type": "Tool Head", "Name": "XL T1"}]
    with patch.object(app_module.locations_db, "load_locations_list",
                      return_value=rows), \
         patch.object(app_module.prusalink_api, "fetch_all_filabridge_printers") as fetch, \
         patch.object(app_module.locations_db, "save_locations_list") as save, \
         patch.object(app_module.state, "logger", MagicMock()):
        app_module._seed_printer_credentials_from_filabridge()
    fetch.assert_not_called()
    save.assert_not_called()


def test_seed_locations_load_failure_warns_and_returns():
    """locations.json unreadable at boot -> warning + early return; the seed
    must never take FilaBridge's word over an unreadable local store, and
    boot must not die."""
    with patch.object(app_module.locations_db, "load_locations_list",
                      side_effect=OSError("corrupt")), \
         patch.object(app_module.prusalink_api, "fetch_all_filabridge_printers") as fetch, \
         patch.object(app_module.locations_db, "save_locations_list") as save, \
         patch.object(app_module.state, "logger", MagicMock()) as logger:
        app_module._seed_printer_credentials_from_filabridge()  # must not raise
    fetch.assert_not_called()
    save.assert_not_called()
    warn_msgs = [str(c.args[0]) for c in logger.warning.call_args_list]
    assert any("could not load locations" in m for m in warn_msgs), warn_msgs


def test_seed_filabridge_pull_failure_warns_no_write():
    """Row needs creds but the FilaBridge pull raises (the decommissioned-FB
    reality) -> warning, NO save, boot continues."""
    with patch.object(app_module.locations_db, "load_locations_list",
                      return_value=_unseeded_rows()), \
         patch.object(app_module.config_loader, "get_api_urls",
                      return_value=("http://sm", "http://fb")), \
         patch.object(app_module.prusalink_api, "fetch_all_filabridge_printers",
                      side_effect=ConnectionError("FB is gone")), \
         patch.object(app_module.locations_db, "seed_printer_credentials") as seed, \
         patch.object(app_module.locations_db, "save_locations_list") as save, \
         patch.object(app_module.state, "logger", MagicMock()) as logger:
        app_module._seed_printer_credentials_from_filabridge()
    seed.assert_not_called()
    save.assert_not_called()
    warn_msgs = [str(c.args[0]) for c in logger.warning.call_args_list]
    assert any("FilaBridge pull failed" in m for m in warn_msgs), warn_msgs


def test_seed_filabridge_empty_logs_retry_no_seed_call():
    """FB reachable but /printers empty -> info log ('will retry next boot'),
    NO seed, NO save. Also pins two predicate details: Type matching is
    case-insensitive ('printer') and a creds dict with a BLANK ip_address
    counts as still-missing (it triggered the pull)."""
    rows = [{"LocationID": "CORE1", "Type": "printer", "Name": "Core One",
             "printer_creds": {"ip_address": "   ", "api_key": "k"}}]
    with patch.object(app_module.locations_db, "load_locations_list",
                      return_value=rows), \
         patch.object(app_module.config_loader, "get_api_urls",
                      return_value=("http://sm", "http://fb")), \
         patch.object(app_module.prusalink_api, "fetch_all_filabridge_printers",
                      return_value=[]) as fetch, \
         patch.object(app_module.locations_db, "seed_printer_credentials") as seed, \
         patch.object(app_module.locations_db, "save_locations_list") as save, \
         patch.object(app_module.state, "logger", MagicMock()) as logger:
        app_module._seed_printer_credentials_from_filabridge()
    fetch.assert_called_once_with("http://fb")  # blank-ip creds DID trigger the pull
    seed.assert_not_called()
    save.assert_not_called()
    info_msgs = [str(c.args[0]) for c in logger.info.call_args_list]
    assert any("will retry next boot" in m for m in info_msgs), info_msgs


def test_seed_happy_path_backup_prune_save_and_log():
    """Seed-needed happy path: seed called prime_only=True with the loaded
    rows + FB printers; a timestamped .pre-printer-creds-seed-*.bak is
    copied from locations_db.JSON_FILE; _prune_locations_backups runs; the
    MIGRATED list is saved exactly once; the 'credential gate primed' info
    line fires and no error is logged."""
    rows = _unseeded_rows()
    fb_printers = {"Core One": {"ip_address": "10.0.0.9", "api_key": "C1KEY"}}
    migrated = [{"LocationID": "CORE1", "Type": "Printer",
                 "printer_creds": {"ip_address": "10.0.0.9", "api_key": "C1KEY"}}]
    json_file = app_module.locations_db.JSON_FILE
    with patch.object(app_module.locations_db, "load_locations_list",
                      return_value=rows), \
         patch.object(app_module.config_loader, "get_api_urls",
                      return_value=("http://sm", "http://fb")), \
         patch.object(app_module.prusalink_api, "fetch_all_filabridge_printers",
                      return_value=fb_printers), \
         patch.object(app_module.locations_db, "seed_printer_credentials",
                      return_value=(migrated, True)) as seed, \
         patch.object(app_module.locations_db, "save_locations_list",
                      return_value=True) as save, \
         patch.object(startup_migrations, "_prune_locations_backups") as prune, \
         patch("shutil.copy2") as copy2, \
         patch.object(app_module.state, "logger", MagicMock()) as logger:
        app_module._seed_printer_credentials_from_filabridge()

    seed.assert_called_once_with(rows, fb_printers, prime_only=True)
    copy2.assert_called_once()
    src, dst = copy2.call_args.args
    assert src == json_file
    assert dst.startswith(f"{json_file}.pre-printer-creds-seed-")
    assert dst.endswith(".bak")
    prune.assert_called_once_with()
    save.assert_called_once_with(migrated)
    info_msgs = [str(c.args[0]) for c in logger.info.call_args_list]
    assert any("credential gate primed" in m for m in info_msgs), info_msgs
    logger.error.assert_not_called()


def test_seed_save_failure_logs_error_no_exception():
    """save_locations_list returning False must log an ERROR naming the
    failure ('save FAILED') and return WITHOUT raising — boot survives a
    failed persist and retries next boot."""
    rows = _unseeded_rows()
    with patch.object(app_module.locations_db, "load_locations_list",
                      return_value=rows), \
         patch.object(app_module.config_loader, "get_api_urls",
                      return_value=("http://sm", "http://fb")), \
         patch.object(app_module.prusalink_api, "fetch_all_filabridge_printers",
                      return_value={"Core One": {"ip_address": "10.0.0.9"}}), \
         patch.object(app_module.locations_db, "seed_printer_credentials",
                      return_value=(rows, True)), \
         patch.object(app_module.locations_db, "save_locations_list",
                      return_value=False), \
         patch.object(startup_migrations, "_prune_locations_backups"), \
         patch("shutil.copy2"), \
         patch.object(app_module.state, "logger", MagicMock()) as logger:
        app_module._seed_printer_credentials_from_filabridge()  # must not raise
    err_msgs = [str(c.args[0]) for c in logger.error.call_args_list]
    assert any("save FAILED" in m for m in err_msgs), err_msgs


def test_seed_unchanged_skips_backup_and_save():
    """seed_printer_credentials reporting changed=False (e.g. FB only knows
    printers whose rows are already primed) -> NO backup and NO save. The
    changed-guard is what makes the boot path idempotent."""
    rows = _unseeded_rows()
    with patch.object(app_module.locations_db, "load_locations_list",
                      return_value=rows), \
         patch.object(app_module.config_loader, "get_api_urls",
                      return_value=("http://sm", "http://fb")), \
         patch.object(app_module.prusalink_api, "fetch_all_filabridge_printers",
                      return_value={"Other": {"ip_address": "1.1.1.1"}}), \
         patch.object(app_module.locations_db, "seed_printer_credentials",
                      return_value=(rows, False)), \
         patch.object(app_module.locations_db, "save_locations_list") as save, \
         patch("shutil.copy2") as copy2, \
         patch.object(app_module.state, "logger", MagicMock()):
        app_module._seed_printer_credentials_from_filabridge()
    copy2.assert_not_called()
    save.assert_not_called()


def test_seed_backup_failure_still_saves():
    """The .bak write is best-effort: shutil.copy2 raising logs a warning
    ('Could not write pre-printer-creds-seed backup') and the SAVE STILL
    PROCEEDS — a backup problem must not block the credential gate."""
    rows = _unseeded_rows()
    migrated = [{"LocationID": "CORE1", "Type": "Printer",
                 "printer_creds": {"ip_address": "10.0.0.9"}}]
    with patch.object(app_module.locations_db, "load_locations_list",
                      return_value=rows), \
         patch.object(app_module.config_loader, "get_api_urls",
                      return_value=("http://sm", "http://fb")), \
         patch.object(app_module.prusalink_api, "fetch_all_filabridge_printers",
                      return_value={"Core One": {"ip_address": "10.0.0.9"}}), \
         patch.object(app_module.locations_db, "seed_printer_credentials",
                      return_value=(migrated, True)), \
         patch.object(app_module.locations_db, "save_locations_list",
                      return_value=True) as save, \
         patch.object(startup_migrations, "_prune_locations_backups") as prune, \
         patch("shutil.copy2", side_effect=OSError("disk full")), \
         patch.object(app_module.state, "logger", MagicMock()) as logger:
        app_module._seed_printer_credentials_from_filabridge()
    save.assert_called_once_with(migrated)
    prune.assert_not_called()  # prune lives inside the same try as the backup
    warn_msgs = [str(c.args[0]) for c in logger.warning.call_args_list]
    assert any("Could not write pre-printer-creds-seed backup" in m
               for m in warn_msgs), warn_msgs


def test_seed_inner_seed_exception_propagates():
    """locations_db.seed_printer_credentials raising PROPAGATES out of
    _seed_printer_credentials_from_filabridge — it is NOT inside any of the
    function's try/excepts, and the __main__ call site (app.py:7428) is also
    unwrapped, so this would kill the serving-process launch path before
    _start_cancel_monitor despite the docstring's 'never blocks startup'.
    # NOTE: pins current behavior; see suspected_bugs.
    """
    rows = _unseeded_rows()
    with patch.object(app_module.locations_db, "load_locations_list",
                      return_value=rows), \
         patch.object(app_module.config_loader, "get_api_urls",
                      return_value=("http://sm", "http://fb")), \
         patch.object(app_module.prusalink_api, "fetch_all_filabridge_printers",
                      return_value={"Core One": {"ip_address": "10.0.0.9"}}), \
         patch.object(app_module.locations_db, "seed_printer_credentials",
                      side_effect=RuntimeError("seed exploded")), \
         patch.object(app_module.locations_db, "save_locations_list") as save, \
         patch.object(app_module.state, "logger", MagicMock()):
        with pytest.raises(RuntimeError, match="seed exploded"):
            app_module._seed_printer_credentials_from_filabridge()
    save.assert_not_called()


# ---------------------------------------------------------------------------
# 3. _cancel_monitor_loop — resilience contract (loop escaped via sentinel,
#    daemon thread NEVER started; _start_cancel_monitor is not called here)
# ---------------------------------------------------------------------------

def test_monitor_loop_recovery_first_tick_error_swallowed_adaptive_sleep():
    """The daemon loop's whole resilience contract in one pass:
    - _recover_print_tracker_on_start runs exactly once, BEFORE the first tick;
    - a RuntimeError from _cancel_monitor_tick is swallowed (logged via
      state.logger.warning 'cancel-monitor tick error') and the loop keeps
      ticking — one bad tick must never kill the thread, or the entire
      cancel/completion deduct pipeline silently stops for the process life;
    - adaptive cadence: sleep(FAST) after a busy tick, sleep(IDLE) after an
      erroring tick (busy resets to False first) and after an idle tick.
    The loop is exited by raising a BaseException-derived sentinel from the
    3rd sleep, which the `except Exception` tick guard cannot swallow — so
    the swallowed RuntimeError genuinely exercised the real guard."""
    fast = app_module._CANCEL_MONITOR_FAST_S
    idle = app_module._CANCEL_MONITOR_IDLE_S
    assert (fast, idle) == (10, 30)  # pin the current cadence values

    order = []
    tick_script = [True, RuntimeError("boom"), False]

    def fake_recover():
        order.append("recover")

    def fake_tick():
        order.append("tick")
        result = tick_script.pop(0)
        if isinstance(result, BaseException):
            raise result
        return result

    sleeps = []

    def fake_sleep(secs):
        sleeps.append(secs)
        if len(sleeps) >= 3:
            raise _StopLoop()

    with patch.object(print_monitor, "_recover_print_tracker_on_start",
                      side_effect=fake_recover) as recover, \
         patch.object(print_monitor, "_cancel_monitor_tick", side_effect=fake_tick), \
         patch.object(app_module.time, "sleep", fake_sleep), \
         patch.object(app_module.state, "logger", MagicMock()) as logger:
        with pytest.raises(_StopLoop):
            app_module._cancel_monitor_loop()

    recover.assert_called_once()
    assert order == ["recover", "tick", "tick", "tick"], (
        "recovery must run once BEFORE the first tick; the erroring 2nd tick "
        f"must not stop the 3rd. Got {order}"
    )
    assert sleeps == [fast, idle, idle], (
        f"adaptive cadence drifted: expected [FAST, IDLE, IDLE], got {sleeps}"
    )
    warn_msgs = [str(c.args[0]) for c in logger.warning.call_args_list]
    assert any("cancel-monitor tick error" in m and "boom" in m
               for m in warn_msgs), warn_msgs


def test_monitor_loop_recovery_failure_does_not_prevent_ticks():
    """A raising _recover_print_tracker_on_start is swallowed (logged
    'print-latch recovery pass failed') and the loop STILL reaches tick #1 —
    a bad persisted latch must not prevent the monitor from starting."""
    order = []

    def fake_tick():
        order.append("tick")
        raise _StopLoop()  # BaseException -> escapes the Exception guard

    # Backstop escape: if the tick patch ever stops intercepting (the exact
    # carve failure mode this suite guards) the loop would otherwise spin
    # forever with REAL 30s sleeps and hang the whole sweep — a patched
    # sleep turns that into a fast _StopLoop failure instead.
    def _sleep_escape(_secs):
        raise _StopLoop()

    with patch.object(print_monitor, "_recover_print_tracker_on_start",
                      side_effect=RuntimeError("recovery boom")), \
         patch.object(print_monitor, "_cancel_monitor_tick", side_effect=fake_tick), \
         patch.object(app_module.time, "sleep", _sleep_escape), \
         patch.object(app_module.state, "logger", MagicMock()) as logger:
        with pytest.raises(_StopLoop):
            app_module._cancel_monitor_loop()

    assert order == ["tick"], f"loop never reached the first tick: {order}"
    warn_msgs = [str(c.args[0]) for c in logger.warning.call_args_list]
    assert any("print-latch recovery pass failed" in m and "recovery boom" in m
               for m in warn_msgs), warn_msgs


# ---------------------------------------------------------------------------
# 4. _check_audit_idle_timeout — complements to test_audit_auto_park_unknown.py
#    (which already pins: stale->cancel, fresh->alone, missing-ts->seeded).
# ---------------------------------------------------------------------------

@pytest.fixture
def audit_session_guard():
    """Snapshot/restore the module-global AUDIT_SESSION so these tests can't
    leak an active session into other test files (the same global the audit
    glue tests mutate)."""
    before = dict(state.AUDIT_SESSION)
    try:
        yield
    finally:
        state.AUDIT_SESSION.clear()
        state.AUDIT_SESSION.update(before)


def test_audit_idle_inactive_session_is_a_pure_noop(audit_session_guard):
    """active=False returns before ANY other branch: no log entry, no
    reset, and — the subtle pin — the stale last_activity_ts is NOT
    overwritten by the seed-missing-timestamp branch. This function runs on
    every /api/logs poll (5s heartbeat), so the inactive path must stay
    side-effect free."""
    state.AUDIT_SESSION.update({"active": False, "location_id": None,
                                "last_activity_ts": 123.0})
    calls = []
    with patch.object(app_module.state, "add_log_entry",
                      side_effect=lambda *a, **k: calls.append((a, k))):
        app_module._check_audit_idle_timeout()
    assert calls == []
    assert state.AUDIT_SESSION["active"] is False
    assert state.AUDIT_SESSION["last_activity_ts"] == 123.0


def test_audit_idle_expiry_log_details_with_location(audit_session_guard):
    """The auto-cancel log line's exact anatomy (the parts the existing test
    doesn't pin): WARNING level, ffaa00 color, the timeout rendered in
    MINUTES (AUDIT_IDLE_TIMEOUT_SECONDS // 60), the '(was on <loc>)' suffix
    when a location was set, and the 'no spools moved' reassurance."""
    state.AUDIT_SESSION.update({
        "active": True,
        "location_id": "LR-MDB-1",
        "expected_items": [101],
        "scanned_items": [],
        "rogue_items": [],
        "last_activity_ts": _time.time() - (state.AUDIT_IDLE_TIMEOUT_SECONDS + 61),
    })
    calls = []
    with patch.object(app_module.state, "add_log_entry",
                      side_effect=lambda *a, **k: calls.append((a, k))):
        app_module._check_audit_idle_timeout()
    assert state.AUDIT_SESSION["active"] is False, "stale session must cancel"
    assert len(calls) == 1, f"expected exactly one log entry, got {calls}"
    args, _kwargs = calls[0]
    msg = args[0]
    minutes = state.AUDIT_IDLE_TIMEOUT_SECONDS // 60
    assert f"{minutes} min of inactivity" in msg, msg
    assert "(was on LR-MDB-1)" in msg, msg
    assert "no spools moved" in msg, msg
    assert args[1] == "WARNING"
    assert args[2] == "ffaa00"


def test_audit_idle_expiry_log_omits_location_suffix_when_unset(audit_session_guard):
    """No location_id on the stale session -> the '(was on ...)' suffix is
    omitted entirely (not rendered empty)."""
    state.AUDIT_SESSION.update({
        "active": True,
        "location_id": None,
        "expected_items": [],
        "scanned_items": [],
        "rogue_items": [],
        "last_activity_ts": _time.time() - (state.AUDIT_IDLE_TIMEOUT_SECONDS + 61),
    })
    calls = []
    with patch.object(app_module.state, "add_log_entry",
                      side_effect=lambda *a, **k: calls.append((a, k))):
        app_module._check_audit_idle_timeout()
    assert state.AUDIT_SESSION["active"] is False
    assert len(calls) == 1
    msg = calls[0][0][0]
    assert "(was on" not in msg, msg
