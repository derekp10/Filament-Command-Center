"""Exactly-once ledger for print-finish / cancel filament deducts.

Spoolman's `used_weight` deduct is NON-idempotent — a retry re-applies the grams
(Spoolman issue #608, ~2.6x on retry) — and the in-memory print tracker is lost
on restart. This persistent ledger keys on (printer_name, job_id) so a given
print's deduct commits AT MOST ONCE across poll ticks AND across a restart
(FilaBridge absorption design §9.4).

Contract (mirrors the design):
  - check `was_deducted(printer, job_id)` BEFORE deducting; skip if True.
  - call `record_deduct(printer, job_id, ...)` AFTER a successful deduct.
  - The in-memory print tracker (detection layer) prevents same-process
    cross-tick double-fire; this ledger closes the cross-RESTART window.
  - A falsy/empty job_id can't be deduped restart-safely: `was_deducted`
    returns False and `record_deduct` is a no-op, so the caller deducts once
    from the in-memory edge and accepts the tiny restart-window risk rather
    than skipping the cancel entirely.

The file is bounded to the most-recent N entries (dict preserves insertion
order on 3.7+), the same eviction shape as app.py's `_evict_old_fb_snapshots`.
"""
from __future__ import annotations

import json
import os
import threading

# Overridable by tests (monkeypatch this attribute to a tmp path).
_LEDGER_PATH = os.path.join(os.path.dirname(__file__), "data", "print_deduct_ledger.json")
_LOCK = threading.Lock()
_MAX_ENTRIES = 200


def _key(printer_name, job_id) -> str:
    return f"{str(printer_name).strip()}::{str(job_id).strip()}"


def _is_blank_job(job_id) -> bool:
    return job_id in (None, "", "0", 0)


def _load() -> dict:
    try:
        with open(_LEDGER_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError, OSError, ValueError):
        return {}


def _save(data: dict) -> None:
    if len(data) > _MAX_ENTRIES:
        data = dict(list(data.items())[-_MAX_ENTRIES:])
    os.makedirs(os.path.dirname(_LEDGER_PATH), exist_ok=True)
    tmp = _LEDGER_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, _LEDGER_PATH)


def was_deducted(printer_name, job_id) -> bool:
    """True if this (printer, job) already had its filament deducted. A
    blank/zero job_id always returns False (can't dedup an id-less job)."""
    if _is_blank_job(job_id):
        return False
    with _LOCK:
        return _key(printer_name, job_id) in _load()


def record_deduct(printer_name, job_id, **meta) -> None:
    """Mark (printer, job) as deducted. No-op for a blank/zero job_id."""
    if _is_blank_job(job_id):
        return
    with _LOCK:
        data = _load()
        data[_key(printer_name, job_id)] = {"job_id": str(job_id), **meta}
        _save(data)
