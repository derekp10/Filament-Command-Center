"""Group 45.1(c): a test run labels itself.

Two back-to-back sweeps on 2026-10-12 failed 13 and then 16 browser tests, only
5 of them in both, because the desktop was busy. A red was unreadable without a
re-run. So conftest.py now:
  - ends every run with one line: the wall-clock time and, for a run with
    browser tests, a load factor (each passed browser test's call time against
    the fastest time that test has taken on this PC, median over the run),
    labelled BUSY RUN at LOAD_WARN or above;
  - adds an "FCC request log" section to a failed browser test's report: the
    page's requests slower than SLOW_REQUEST_S, the ones still in flight, and
    the dev-Spoolman read timeouts FCC logged in hub.log during the test.

These pins drive the helpers and both hooks directly, with no browser and no
container.
"""
from __future__ import annotations

import json
import time
import types

import pytest

import conftest


# --- the load factor -------------------------------------------------------

def _history(n, fastest=1.0):
    return {f"t{i}": [fastest * 1.5, fastest, fastest * 1.2] for i in range(n)}


def test_the_load_factor_is_the_median_slowdown_against_each_tests_fastest_time():
    history = _history(31)
    times = {f"t{i}": 2.0 for i in range(31)}       # every test twice its best
    times["t0"] = 50.0                               # one outlier can't move a median
    assert conftest.load_factor(times, history) == pytest.approx(2.0)


def test_tests_without_a_history_are_left_out_of_the_factor():
    history = _history(30)
    times = {f"t{i}": 1.1 for i in range(30)}
    times.update({f"new{i}": 99.0 for i in range(40)})   # added since the last run
    assert conftest.load_factor(times, history) == pytest.approx(1.1)


def test_too_few_comparable_tests_give_no_factor():
    """A handful of browser tests (one file run by hand) can't say anything
    about the machine; the summary then prints only the time."""
    history = _history(5)
    times = {f"t{i}": 3.0 for i in range(5)}
    assert conftest.load_factor(times, history) is None


def test_junk_in_the_history_file_is_ignored():
    history = {f"t{i}": [0, -1, "x", None, 2.0] for i in range(30)}
    times = {f"t{i}": 4.0 for i in range(30)}
    assert conftest.load_factor(times, history) == pytest.approx(2.0)


def test_a_history_entry_that_is_not_a_list_reads_as_no_history():
    """Review test-infra-5: a bare number used to raise TypeError inside the
    summary hook, failing every later run until the file was deleted."""
    history = {f"t{i}": [1.0] for i in range(30)}
    history.update({"bare": 2.5, "text": "x", "none": None, "flag": [True]})
    times = {**{f"t{i}": 1.5 for i in range(30)}, "bare": 9.0, "text": 9.0, "none": 9.0, "flag": 9.0}
    assert conftest.load_factor(times, history) == pytest.approx(1.5)
    out = conftest.update_history(history, {"bare": 3.0, "flag": 4.0})
    assert out["bare"] == [3.0] and out["flag"] == [4.0]


def test_the_history_keeps_each_tests_most_recent_times():
    history = {"a": [1.0, 2.0, 3.0]}
    out = conftest.update_history(history, {"a": 4.0, "b": 5.0}, keep=3)
    assert out == {"a": [2.0, 3.0, 4.0], "b": [5.0]}
    assert history == {"a": [1.0, 2.0, 3.0]}, "the input was changed in place"


# --- hub.log: dev-Spoolman read timeouts during one test ----------------------

TIMEOUT = ("2026-10-13 15:52:11,023 - ERROR - get_all_spools failed: HTTPConnectionPool("
           "host='192.168.1.29', port=7913): Read timed out. (read timeout=5)\n")
MOCKED = ("2026-10-13 15:52:11,023 - ERROR - get_all_spools failed: HTTPConnectionPool("
          "host='mock-spoolman', port=7913): Read timed out. (read timeout=5)\n")
OTHER = "2026-10-13 15:52:12,000 - INFO - something else\n"


def test_only_timeouts_after_the_offset_and_to_dev_spoolman_count(tmp_path):
    log = tmp_path / "hub.log"
    log.write_text(TIMEOUT * 4, encoding="utf-8")
    offset = log.stat().st_size
    with open(log, "a", encoding="utf-8") as f:
        f.write(TIMEOUT + OTHER + MOCKED + TIMEOUT)
    assert conftest.count_spoolman_timeouts(offset, path=str(log)) == 2


def test_a_log_that_rotated_during_the_test_is_read_across_both_files(tmp_path):
    """FCC's handler rotates hub.log at ~1 MB. After a rotation the file is
    smaller than where the test started; the rest of the old file is hub.log.1."""
    log = tmp_path / "hub.log"
    before = (TIMEOUT * 7 + OTHER * 50).encode("utf-8")     # logged before the test began
    (tmp_path / "hub.log.1").write_bytes(before + (TIMEOUT * 3).encode("utf-8"))
    log.write_bytes(TIMEOUT.encode("utf-8"))
    assert conftest.count_spoolman_timeouts(len(before), path=str(log)) == 4, (
        "the old file is read from where the test began, not from its start")


def test_a_missing_log_counts_nothing(tmp_path):
    assert conftest.count_spoolman_timeouts(0, path=str(tmp_path / "nope.log")) == 0


# --- the failure section ------------------------------------------------------

def test_the_request_log_names_slow_and_unfinished_requests():
    net = {"slow": [("GET", "/api/locations", 6.25)],
           "pending": {object(): ("POST", "/api/identify_scan", 100.0)}}
    text = conftest.format_request_log(net, 7, now=104.5)
    assert "slow (6.2 s): GET /api/locations" in text
    assert "never finished (4.5 s so far): POST /api/identify_scan" in text
    assert "dev Spoolman read timeouts FCC logged during this test: 7" in text


def _req(**timing):
    return types.SimpleNamespace(timing=timing)


def test_a_request_is_timed_by_the_browser_not_by_event_dispatch():
    """Review test-infra-2: the sync API dispatches request events only inside
    a Playwright call, so Python's clock at dispatch can be seconds late. A
    finished request uses the browser's responseEnd (ms after its start)."""
    assert conftest.request_duration(_req(startTime=1_700_000_000_000, responseEnd=180.0),
                                     started=0.0, now=99.0) == pytest.approx(0.18)
    # No browser figure (a failed or cached request): wall time since the start.
    assert conftest.request_duration(_req(responseEnd=-1), started=10.0, now=12.5) == pytest.approx(2.5)
    assert conftest.request_duration(types.SimpleNamespace(), started=10.0, now=11.0) == pytest.approx(1.0)
    assert conftest.request_start(_req(startTime=1_700_000_000_000)) == pytest.approx(1_700_000_000.0)
    t0 = time.time()
    assert t0 <= conftest.request_start(_req(startTime=-1)) <= time.time()


def test_a_quiet_request_log_says_so():
    text = conftest.format_request_log({"slow": [], "pending": {}}, 0)
    assert "no request took over 2 s" in text


def _run_hook(item, rep):
    gen = conftest.pytest_runtest_makereport(item, None)
    next(gen)
    with pytest.raises(StopIteration):
        gen.send(types.SimpleNamespace(get_result=lambda: rep))


def _rep(when, outcome, duration=1.5):
    return types.SimpleNamespace(when=when, failed=outcome == "failed",
                                 passed=outcome == "passed", duration=duration,
                                 sections=[])


@pytest.fixture
def run_state(monkeypatch):
    monkeypatch.setattr(conftest, "_RUN", {"start": None, "browser": {}})
    return conftest._RUN


def test_a_failed_browser_test_gets_the_request_log(run_state, monkeypatch):
    calls = []
    monkeypatch.setattr(conftest, "count_spoolman_timeouts",
                        lambda offset: calls.append(("count", offset)) or 12)
    fake_page = types.SimpleNamespace(wait_for_timeout=lambda ms: calls.append(("pump", ms)))
    item = types.SimpleNamespace(nodeid="x::y", fixturenames=["page"], _fcc_hub_offset=73_912,
                                 _fcc_page=fake_page,
                                 _fcc_net={"slow": [("GET", "/api/locations", 9.0)], "pending": {}})
    rep = _rep("call", "failed")
    _run_hook(item, rep)
    (title, body), = rep.sections
    assert title == "FCC request log (Group 45.1)"
    assert "GET /api/locations" in body and ": 12" in body
    # Review: count from THIS test's hub.log offset, after letting the page
    # dispatch request events still queued behind the last Playwright call.
    assert calls == [("pump", 1), ("count", 73_912)], calls
    assert run_state["browser"] == {}, "a red's time must not enter the history"


def test_a_closed_page_never_turns_the_red_into_an_error(run_state, monkeypatch):
    monkeypatch.setattr(conftest, "count_spoolman_timeouts", lambda offset: 0)

    def closed(ms):
        raise RuntimeError("Target page, context or browser has been closed")

    item = types.SimpleNamespace(nodeid="x::y", fixturenames=["page"], _fcc_hub_offset=5,
                                 _fcc_page=types.SimpleNamespace(wait_for_timeout=closed),
                                 _fcc_net={"slow": [], "pending": {}})
    rep = _rep("setup", "failed")
    _run_hook(item, rep)
    assert [t for t, _ in rep.sections] == ["FCC request log (Group 45.1)"]


def test_a_passed_browser_test_records_its_call_time(run_state):
    item = types.SimpleNamespace(nodeid="x::y", fixturenames=["page"], _fcc_net={})
    _run_hook(item, _rep("call", "passed", duration=3.25))
    _run_hook(item, _rep("teardown", "passed", duration=9.0))
    assert run_state["browser"] == {"x::y": 3.25}


def test_a_test_without_a_browser_records_nothing(run_state):
    item = types.SimpleNamespace(nodeid="x::z", fixturenames=["tmp_path"])
    rep = _rep("call", "failed")
    _run_hook(item, rep)
    _run_hook(item, _rep("call", "passed"))
    assert run_state["browser"] == {} and rep.sections == []


# --- the host leaves the container's hub.log alone ----------------------------

def test_the_host_test_process_holds_no_handle_on_hub_log():
    """Review test-infra-1: state.py opens a RotatingFileHandler on 'hub.log'
    relative to the working directory, which from inventory-hub/ is the dev
    container's own log. Held by the host, the container's 1 MB rollover
    failed on Windows and the container's log records were dropped."""
    import logging.handlers
    import state
    held = [h for h in state.logger.handlers
            if isinstance(h, logging.handlers.RotatingFileHandler)]
    assert held == [], held
    assert state.f_handler.stream is None, "the handler's file is still open"


# --- 45.1(b): one default wait for `expect` -----------------------------------

def test_expect_waits_ten_seconds_by_default():
    """Playwright's own default is 5 s. conftest's pytest_configure raises it
    for the whole run, so an `expect` without a `timeout=` survives a loaded
    desktop. Read off the live object: nothing else may reset it."""
    expect = pytest.importorskip("playwright.sync_api").expect
    assert expect._timeout == conftest.EXPECT_TIMEOUT_MS == 10_000


# --- the summary line ---------------------------------------------------------

class _Reporter:
    def __init__(self, passed=0, failed=0):
        self.stats = {"passed": [None] * passed, "failed": [None] * failed}
        self.lines = []

    def write_sep(self, sep, msg):
        self.lines.append(msg)


def _summary(monkeypatch, tmp_path, run_state, times, history, elapsed=125):
    path = tmp_path / ".test-timings" / "browser-call-times.json"
    monkeypatch.setattr(conftest, "TIMING_FILE", str(path))
    if history is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(history), encoding="utf-8")
    run_state["start"] = time.time() - elapsed
    run_state["browser"].update(times)
    tr = _Reporter(passed=len(times) + 3, failed=1)
    conftest.pytest_terminal_summary(tr, 1, None)
    return tr.lines, (json.loads(path.read_text(encoding="utf-8")) if path.exists() else None)


def test_a_busy_run_says_so_and_still_records_its_times(monkeypatch, tmp_path, run_state):
    history = _history(40)
    times = {f"t{i}": 1.6 for i in range(40)}
    (line,), saved = _summary(monkeypatch, tmp_path, run_state, times, history)
    assert line.startswith("⏱️ 2:05 for 44 tests (40 browser tests passed)"), line
    assert "BUSY RUN" in line and "1.60x" in line, line
    assert saved["t0"][-1] == 1.6 and len(saved["t0"]) == 4


def test_a_normal_run_prints_its_factor_quietly(monkeypatch, tmp_path, run_state):
    times = {f"t{i}": 1.1 for i in range(40)}
    (line,), _ = _summary(monkeypatch, tmp_path, run_state, times, _history(40))
    assert "load 1.10x usual" in line and "BUSY" not in line, line


def test_the_first_run_on_a_pc_starts_the_history(monkeypatch, tmp_path, run_state):
    times = {f"t{i}": 1.0 for i in range(40)}
    (line,), saved = _summary(monkeypatch, tmp_path, run_state, times, None)
    assert "no baseline yet" in line, line
    assert saved == {f"t{i}": [1.0] for i in range(40)}


def test_a_run_without_browser_tests_prints_only_its_time(monkeypatch, tmp_path, run_state):
    (line,), saved = _summary(monkeypatch, tmp_path, run_state, {}, None, elapsed=42)
    assert line == "⏱️ 0:42 for 4 tests", line
    assert saved is None, "an offline run must not create the history file"
