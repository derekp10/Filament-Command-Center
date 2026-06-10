"""Lightweight, opt-in per-request timing trace — L3 slot-assign latency probe.

Investigation scaffolding for the 2026-06 "Processing… stays up too long on
slot assign" report. It answers ONE question with real numbers: on a live
assign, which leg of perform_smart_move (printer-state preflight, Spoolman
read-merge-write, FilaBridge map/unmap, config disk reads) actually eats the
wall-clock — and how much of it the auto-deploy recursion doubles.

Design contract:
  * ZERO overhead when no trace is active. Every span() call does a single
    thread-local attribute check and runs the body untouched. The spans
    sprinkled through the hot shared Spoolman / FilaBridge / config functions
    therefore cost nothing for the thousands of non-assign calls per minute.
  * A trace is started at a REQUEST boundary via start_if_idle() — the
    perform_smart_move wrapper and the /api/printer_state probe endpoint.
    Leaf IO wraps itself in span(name). finish() pops the trace and returns a
    one-line human-readable summary for hub.log + the Activity Log.
  * THREAD-LOCAL — the dev/prod Flask server is threaded, so concurrent
    requests each get their own accumulator and never interleave.
  * Behaviour-neutral. It never swallows exceptions, never changes a return
    value, and is safe to leave in or rip out wholesale.

`rollup=True` marks a span that CONTAINS other spans (e.g. `preflight` wraps
the FilaBridge cred fetch + the PrusaLink status probe). Rollups are displayed
but excluded from the "other=" unattributed-time math so nested spans don't
double-count.
"""
import time
import threading
from contextlib import contextmanager

_local = threading.local()


def start_if_idle(label):
    """Begin a trace if none is active on THIS thread.

    Returns True when this call started the trace (the caller owns finish()),
    False when a trace was already running — which is exactly the
    perform_smart_move auto-deploy recursion re-entering: its spans must
    accumulate into the outer trace and it must NOT finish early.
    """
    if getattr(_local, "trace", None) is not None:
        return False
    _local.trace = {"label": label, "t0": time.perf_counter(), "spans": {}}
    return True


def active():
    """True if a trace is currently collecting on this thread."""
    return getattr(_local, "trace", None) is not None


@contextmanager
def span(name, rollup=False):
    """Time the wrapped block and add it to the active trace under `name`
    (repeat calls with the same name accumulate count + total ms).

    No-op fast path when no trace is active: this is what keeps the shared
    instrumented functions free for every non-assign caller.
    """
    tr = getattr(_local, "trace", None)
    if tr is None:
        yield
        return
    t0 = time.perf_counter()
    try:
        yield
    finally:
        dt_ms = (time.perf_counter() - t0) * 1000.0
        agg = tr["spans"].get(name)
        if agg is None:
            tr["spans"][name] = [1, dt_ms, rollup]  # [count, total_ms, is_rollup]
        else:
            agg[0] += 1
            agg[1] += dt_ms


def finish():
    """Pop the active trace and return a one-line summary, or None if no trace
    was active. Always clears the thread-local."""
    tr = getattr(_local, "trace", None)
    if tr is None:
        return None
    _local.trace = None
    total_ms = (time.perf_counter() - tr["t0"]) * 1000.0
    spans = tr["spans"]
    if not spans:
        return f"⏱️ {tr['label']} total={total_ms:.0f}ms"
    # Dominant leg first so the trace reads top-down by cost.
    ordered = sorted(spans.items(), key=lambda kv: kv[1][1], reverse=True)
    leaf_ms = sum(ms for _cnt, ms, ru in spans.values() if not ru)
    untracked = total_ms - leaf_ms
    parts = [f"{name}={ms:.0f}ms×{cnt}" for name, (cnt, ms, _ru) in ordered]
    if untracked > 1:
        parts.append(f"other={untracked:.0f}ms")
    return f"⏱️ {tr['label']} total={total_ms:.0f}ms | " + "  ".join(parts)
