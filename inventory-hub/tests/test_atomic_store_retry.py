"""Group 32.1 — pin the shared atomic-write retry.

`atomic_store.replace_with_retry` rides out the Windows host↔container
bind-mounted-file sharing collision (PermissionError on os.replace) that flaked
`test_process_fetch_gated_off_while_locked` under the saturated
`RUN_INTEGRATION=1` sweep. These are pure unit tests — no server, no real store.
"""
from __future__ import annotations

import json
import os
from unittest.mock import patch, MagicMock

import pytest

import atomic_store
import cancel_fetch_store


def test_replace_with_retry_success(tmp_path):
    """Happy path: a normal replace moves the file with no retry."""
    src = tmp_path / "a.tmp"
    dst = tmp_path / "a.json"
    src.write_text("hello", encoding="utf-8")
    atomic_store.replace_with_retry(str(src), str(dst))
    assert dst.read_text(encoding="utf-8") == "hello"
    assert not src.exists()


def test_retries_on_permissionerror_then_succeeds():
    """PermissionError on the first attempts is retried; a later success returns."""
    calls = {"n": 0}

    def flaky(_src, _dst):
        calls["n"] += 1
        if calls["n"] < 3:
            raise PermissionError("[WinError 5] Access is denied")
        return None

    with patch.object(atomic_store.os, "replace", side_effect=flaky), \
         patch.object(atomic_store.time, "sleep") as slept:
        atomic_store.replace_with_retry("src", "dst")

    assert calls["n"] == 3           # failed twice, succeeded on the third
    assert slept.call_count == 2     # one backoff per failed attempt


def test_reraises_after_exhausting_attempts():
    """A persistently-held target still surfaces — the write is NOT masked."""
    with patch.object(atomic_store.os, "replace",
                      side_effect=PermissionError("held")) as rep, \
         patch.object(atomic_store.time, "sleep"):
        with pytest.raises(PermissionError):
            atomic_store.replace_with_retry("src", "dst", attempts=4)
    assert rep.call_count == 4


def test_non_permissionerror_propagates_immediately():
    """Only PermissionError is retried; anything else fails fast (no retry)."""
    with patch.object(atomic_store.os, "replace",
                      side_effect=OSError("disk gone")) as rep, \
         patch.object(atomic_store.time, "sleep") as slept:
        with pytest.raises(OSError):
            atomic_store.replace_with_retry("src", "dst")
    assert rep.call_count == 1
    slept.assert_not_called()


def test_cancel_fetch_store_save_routes_through_retry(tmp_path, monkeypatch):
    """Integration: cancel_fetch_store._save survives a one-shot PermissionError
    on os.replace (the real bind-mount collision) and still lands the record."""
    store = tmp_path / "pending_cancel_fetches.json"
    monkeypatch.setattr(cancel_fetch_store, "_STORE_PATH", str(store))

    real_replace = os.replace
    state = {"failed": False}

    def fail_once(src, dst):
        if not state["failed"]:
            state["failed"] = True
            raise PermissionError("[WinError 32] sharing violation")
        return real_replace(src, dst)

    with patch.object(atomic_store.os, "replace", side_effect=fail_once), \
         patch.object(atomic_store.time, "sleep"):
        cancel_fetch_store.add_pending({
            "printer_name": "XL", "job_id": "G-9", "filename": "f.gcode",
            "progress": 0.5, "first_seen": 0, "attempts": 1,
        })

    assert state["failed"] is True                       # the retry actually fired
    assert cancel_fetch_store.has_pending("XL", "G-9")   # and the write landed
    saved = json.loads(store.read_text(encoding="utf-8"))
    assert "XL::G-9" in saved
