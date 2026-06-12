"""Persistent QUEUE of cancelled prints whose gcode couldn't be fetched yet
(FilaBridge absorption design §9.10 — the selected-file download LOCK).

Why this exists: PrusaLink/Buddy firmware 404s the raw-file download while the
file is the SELECTED/active print — i.e. while the printer sits in STOPPED with
the cancel-summary screen up, which is EXACTLY when the cancel monitor fires.
The file un-locks only once the print is cleared on the printer (→ IDLE). So a
cancel can't be computed at the edge; we stash it here and the monitor retries
the fetch every tick until the file is downloadable (or a max-age give-up).

This is the "awaiting fetch" stage that PRECEDES the "awaiting review" stage in
cancel_review_store: edge → [cancel_fetch_store, locked] → (file unlocks) →
compute → [cancel_review_store, computed] → confirm/dismiss. Kept SEPARATE from
the review store so the /api/cancel_deduct/pending UI never surfaces a
not-yet-computed entry.

Keyed on (printer_name, job_id) like print_deduct_ledger / cancel_review_store.
Survives a restart so an FCC reboot between cancel and screen-clear doesn't lose
the pending deduct. Record shape:
  {printer_name, job_id, filename, progress, first_seen (epoch s), attempts,
   last_status}
"""
from __future__ import annotations

import json
import os
import threading

# Overridable by tests (monkeypatch this attribute to a tmp path).
_STORE_PATH = os.path.join(os.path.dirname(__file__), "data", "pending_cancel_fetches.json")
_LOCK = threading.RLock()
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


def _save(data: dict) -> None:
    if len(data) > _MAX_ENTRIES:
        data = dict(list(data.items())[-_MAX_ENTRIES:])
    os.makedirs(os.path.dirname(_STORE_PATH), exist_ok=True)
    tmp = _STORE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, _STORE_PATH)


def add_pending(record: dict) -> None:
    """Stash / overwrite a pending fetch. `record` must carry `printer_name` +
    `job_id`. Re-adding the same key overwrites (idempotent — used to bump
    `attempts`/`last_status` without changing `first_seen`)."""
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
    """All pending fetch records (newest last, insertion order)."""
    with _LOCK:
        return list(_load().values())


def pop_pending(printer_name, job_id):
    """Atomically remove + return the pending fetch record (or None)."""
    with _LOCK:
        data = _load()
        rec = data.pop(_key(printer_name, job_id), None)
        if rec is not None:
            _save(data)
        return rec
