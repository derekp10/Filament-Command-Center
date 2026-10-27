"""Persistent store of PENDING cancelled-print partial deducts awaiting Derek's
review/confirm (FilaBridge absorption design §9.7).

The cancelled-print detector (slice 2a) computes the per-tool partial but — for a
cancel — does NOT auto-write it. It stashes a computed-but-unwritten record here
and raises a "🛑 Review" affordance. The user previews the per-tool grams, nudges
if needed, and confirms (apply) or dismisses. This store survives a restart AND
the activity-log scroll-off, so a pending review is never silently lost — the
exact weight-drift problem §9 is built to solve.

Keyed on (printer_name, job_id) like print_deduct_ledger; bounded to the most
recent N, and a review the bound pushes out is reported in the Activity Log, never
dropped silently. `pop_pending` is atomic under the lock so a double-click confirm/dismiss
can't double-apply (the pop IS the claim — a concurrent second caller gets None).
"""
from __future__ import annotations

import json
import os
import threading

import atomic_store

# Overridable by tests (monkeypatch this attribute to a tmp path).
_STORE_PATH = os.path.join(os.path.dirname(__file__), "data", "pending_cancel_deducts.json")
_LOCK = threading.Lock()
_MAX_ENTRIES = 100


def _key(printer_name, job_id) -> str:
    return f"{str(printer_name).strip()}::{str(job_id).strip()}"


def _load() -> dict:
    try:
        with open(_STORE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError, OSError, ValueError):
        return {}


def _report_evicted(rec) -> None:
    """A review pushed out by the cap is a job neither the ledger nor a review owns
    any more, its grams never asked about again, so it is never dropped silently
    (Group 56 review, round 2: 56.3's "couldn't measure" cards stay until
    Discard). Best-effort: the store's write never depends on the log line."""
    try:
        import html
        import state
        state.add_log_entry(
            f"❌ The 🛑 Review list is full ({_MAX_ENTRIES} pending), so its oldest review was "
            f"dropped: {rec.get('printer_name')} job {rec.get('job_id')} "
            f"('{html.escape(str(rec.get('filename')), quote=False)}', "
            f"{float(rec.get('total_grams') or 0):.2f}g, {rec.get('kind') or 'partial'}) — weigh "
            f"that spool to true it up, and Discard the reviews you've settled.",
            "ERROR", "ff4444")
    except Exception:
        pass


def _save(data: dict) -> None:
    evicted = []
    if len(data) > _MAX_ENTRIES:
        items = list(data.items())
        evicted = [rec for _key_, rec in items[:-_MAX_ENTRIES]]
        data = dict(items[-_MAX_ENTRIES:])
    os.makedirs(os.path.dirname(_STORE_PATH), exist_ok=True)
    tmp = _STORE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    # 32.1 — retry on the Windows host↔container bind-mount sharing collision.
    atomic_store.replace_with_retry(tmp, _STORE_PATH)
    for rec in evicted:
        _report_evicted(rec)


def add_pending(record: dict) -> None:
    """Stash a pending review. `record` must carry `printer_name` + `job_id`.
    Re-adding the same key overwrites (idempotent)."""
    with _LOCK:
        data = _load()
        data[_key(record["printer_name"], record["job_id"])] = record
        _save(data)


def has_pending(printer_name, job_id) -> bool:
    with _LOCK:
        return _key(printer_name, job_id) in _load()


def get_pending(printer_name, job_id):
    with _LOCK:
        return _load().get(_key(printer_name, job_id))


def list_pending() -> list:
    """All pending review records (newest last, insertion order)."""
    with _LOCK:
        return list(_load().values())


def pop_pending(printer_name, job_id):
    """Atomically remove + return the pending record (or None). The atomic pop is
    the confirm/dismiss CLAIM: a concurrent second call gets None and no-ops, so
    a double-submit can't double-apply."""
    with _LOCK:
        data = _load()
        rec = data.pop(_key(printer_name, job_id), None)
        if rec is not None:
            _save(data)
        return rec
