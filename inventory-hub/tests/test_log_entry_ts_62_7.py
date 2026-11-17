"""Group 62.7(d): every Activity Log entry carries `ts`, epoch milliseconds, strictly
increasing, offline.

The 📡 pill counted the entries newer than the last one seen by comparing their
'HH:MM:SS' text, so after midnight a line earlier than the last-seen time never raised
it. `ts` sorts across midnight; the page compares it (inv_core.js's _updateLogPill;
test_log_pill_midnight_62_7_js.py). Two entries in the same millisecond, or a clock that
steps back, still get increasing values. RED on the commit before 62.7(d): no `ts`.
"""
from __future__ import annotations

import time
from types import SimpleNamespace

import state


def test_log_entries_carry_a_strictly_increasing_ts(monkeypatch):
    clock = iter([1_700_000_000.0005, 1_700_000_000.0005, 1_699_999_999.0, 1_700_000_001.25])
    monkeypatch.setattr(state, "time", SimpleNamespace(time=lambda: next(clock), strftime=time.strftime))
    monkeypatch.setattr(state, "RECENT_LOGS", [])
    monkeypatch.setattr(state, "_LAST_LOG_TS", 0)
    for i in range(4):
        state.add_log_entry(f"line {i}", "INFO")
    entries = list(reversed(state.RECENT_LOGS))         # newest first in the list
    assert [e["ts"] for e in entries] == [1_700_000_000_000, 1_700_000_000_001,
                                          1_700_000_000_002, 1_700_000_001_250]
    assert all(isinstance(e["time"], str) and len(e["time"]) == 8 for e in entries)   # the text stays


def test_a_swatch_line_and_a_meta_line_carry_it_too(monkeypatch):
    monkeypatch.setattr(state, "RECENT_LOGS", [])
    state.add_log_entry("a swatch", "INFO", "ff0000")
    state.add_log_entry("a report", "INFO", meta={"type": "audit_report", "audit_id": "x-1"})
    a, b = state.RECENT_LOGS[1], state.RECENT_LOGS[0]
    assert isinstance(a["ts"], int) and b["ts"] > a["ts"] and b["meta"]["type"] == "audit_report"
