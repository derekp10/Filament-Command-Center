"""Persistent snapshot of the in-flight print latch (`_PRINT_TRACKER`) so a
cancel in progress survives an FCC / host restart (FilaBridge absorption slice 7
— power-loss latch persistence).

Why this exists: the cancel monitor latches the active job (filename, job_id,
monotonic progress) in memory while a print runs, and fires the partial deduct
on the PRINTING→STOPPED/ERROR edge. If FCC (or the whole TrueNAS box) restarts
DURING a print, that in-memory latch is lost — so on reboot there's no
"previous in-progress" state and a cancel that happened (or happens) during the
outage is missed. Persisting the latch each monitor tick + reconciling it on
monitor start closes that gap.

Single-snapshot store (NOT keyed records like cancel_fetch_store): the whole
`{printer_name: entry}` dict, atomically replaced each tick and read once on
monitor start. Best-effort — a read/write failure must never break the tick or
the daemon start.
"""
from __future__ import annotations

import json
import os
import threading

# Overridable by tests (monkeypatch this attribute to a tmp path).
_STORE_PATH = os.path.join(os.path.dirname(__file__), "data", "print_tracker_latch.json")
_LOCK = threading.RLock()


def save(tracker: dict) -> None:
    """Atomically persist the latch snapshot. Best-effort: swallow any error so a
    write failure never breaks a monitor tick."""
    try:
        with _LOCK:
            os.makedirs(os.path.dirname(_STORE_PATH), exist_ok=True)
            tmp = _STORE_PATH + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(tracker if isinstance(tracker, dict) else {}, f, indent=2)
            os.replace(tmp, _STORE_PATH)
    except Exception:
        pass


def load() -> dict:
    """Return the persisted snapshot, or {} if missing/corrupt."""
    try:
        with _LOCK:
            with open(_STORE_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data if isinstance(data, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError, OSError, ValueError):
        return {}


def clear() -> None:
    """Remove the snapshot file (best-effort)."""
    try:
        with _LOCK:
            if os.path.exists(_STORE_PATH):
                os.remove(_STORE_PATH)
    except Exception:
        pass
