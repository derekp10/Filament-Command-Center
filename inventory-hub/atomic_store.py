"""Shared atomic-write helper for the small bind-mounted JSON stores
(`cancel_fetch_store`, `cancel_review_store`, `print_deduct_ledger`,
`print_tracker_store`).

Why this exists (Group 32.1): each store writes `data/<name>.json` via a
temp-file + ``os.replace`` swap. In DEV that `data/` directory is bind-mounted
into the Docker container, so the in-container cancel-monitor daemon and a
host-side pytest can `os.replace` the SAME target at the same instant. On
Windows that momentary sharing collision raises ``PermissionError`` (WinError 5
"access denied" / WinError 32 "sharing violation") even though the write itself
is fine — the flake behind `test_process_fetch_gated_off_while_locked` under the
saturated `RUN_INTEGRATION=1` sweep. A few short backoff retries ride the
collision out.

On POSIX (prod is Linux) ``os.replace`` is atomic and never raises for this
reason, so the retry is a harmless no-op there. On persistent failure the last
error propagates so a genuinely stuck write is NOT masked.
"""
from __future__ import annotations

import os
import time

# Kept small + module-level so tests can monkeypatch the pacing if needed.
_REPLACE_ATTEMPTS = 5
_REPLACE_BACKOFF = 0.05  # seconds; scaled by attempt index


def replace_with_retry(src, dst, *, attempts=_REPLACE_ATTEMPTS, backoff=_REPLACE_BACKOFF):
    """``os.replace(src, dst)`` with a bounded retry on Windows PermissionError.

    Retries ONLY on ``PermissionError`` (the host↔container bind-mount sharing
    collision); any other error propagates immediately. After the final attempt
    the last ``PermissionError`` is re-raised so a persistently-held target
    still surfaces rather than silently dropping the write.
    """
    attempts = max(1, attempts)  # always make at least one real attempt
    for i in range(attempts):
        try:
            os.replace(src, dst)
            return
        except PermissionError:
            if i == attempts - 1:
                raise
            time.sleep(backoff * (i + 1))
