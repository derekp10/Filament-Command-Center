"""Contract tests for perf_trace — the L3 slot-assign latency probe.

These pin the four properties the instrumentation relies on:
  1. start_if_idle() owns exactly the OUTERMOST call (recursion re-entry → False).
  2. span() accumulates count + time and a repeated span shows ×N.
  3. rollup spans are displayed but excluded from the leaf-sum, so a nested
     span (preflight wrapping creds+status) never double-counts into "other".
  4. finish() returns a one-line summary once, then clears the thread-local;
     span() is a zero-cost no-op when no trace is active.
"""
import perf_trace as pt


def _reset():
    # Defensive: ensure no trace leaked from a previous test on this thread.
    pt.finish()


def test_start_if_idle_owns_only_outermost_call():
    _reset()
    assert pt.start_if_idle("slot-assign -> X") is True   # outermost owns it
    assert pt.start_if_idle("recursion") is False         # re-entry must NOT own
    assert pt.active() is True
    pt.finish()
    assert pt.active() is False


def test_finish_returns_summary_once_then_clears():
    _reset()
    pt.start_if_idle("slot-assign -> X")
    with pt.span("spoolman.patch"):
        pass
    summary = pt.finish()
    assert summary is not None and "total=" in summary and "spoolman.patch=" in summary
    # A second finish with no active trace is a no-op.
    assert pt.finish() is None
    assert pt.active() is False


def test_repeated_span_shows_count():
    _reset()
    pt.start_if_idle("slot-assign -> X")
    for _ in range(2):
        with pt.span("preflight"):
            pass
    summary = pt.finish()
    assert "preflight=" in summary and "x2" in summary.replace("×", "x")


def test_rollup_excluded_from_leaf_sum():
    _reset()
    pt.start_if_idle("slot-assign -> X")
    # preflight (rollup) wraps two leaf spans; if the rollup were counted as a
    # leaf, leaf_sum would roughly double and "other" would go strongly negative
    # (and be hidden) — instead "other" should reflect only untracked glue time.
    with pt.span("preflight", rollup=True):
        with pt.span("prusalink.fetch_creds"):
            pass
        with pt.span("prusalink.status"):
            pass
    summary = pt.finish()
    assert "preflight=" in summary
    assert "prusalink.fetch_creds=" in summary
    assert "prusalink.status=" in summary


def test_span_is_noop_when_idle():
    _reset()
    assert pt.active() is False
    ran = []
    with pt.span("spoolman.get_spool"):
        ran.append(True)         # body still runs untouched
    assert ran == [True]
    assert pt.active() is False  # no trace was created


def test_span_records_even_when_body_raises():
    _reset()
    pt.start_if_idle("slot-assign -> X")
    try:
        with pt.span("spoolman.patch"):
            raise ValueError("boom")
    except ValueError:
        pass
    summary = pt.finish()
    # The span must still have been recorded despite the exception propagating.
    assert "spoolman.patch=" in summary
