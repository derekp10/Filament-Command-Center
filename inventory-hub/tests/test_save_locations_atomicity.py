"""Stage 3 / Feature-Buglist L37 — hardening tests for save_locations_list.

The 2026-04-28 / 2026-05-11 dev corruption ("valid content + duplicate
tail") was caused by a fixed `.tmp` filename that two concurrent Flask
threads could share, plus a silent post-write success even when the
on-disk content didn't actually parse. These tests pin the two hardening
fixes:

  (1) Per-call unique temp filename — concurrent writes don't share a
      `.tmp` and so can't corrupt each other's in-flight content.
  (2) Post-write read-back-and-verify with one retry — if the on-disk
      file fails to parse after `os.replace`, the write is retried once
      and a critical log is emitted for operator inspection.

Companion to the existing test_locations_atomic_write.py (which covers
the original atomic-replace contract: atomicity, no leftover bytes,
tmp lives in target dir).
"""
from __future__ import annotations

import json
import logging
import os
import sys
import threading
import time
from unittest.mock import patch

import pytest


@pytest.fixture
def temp_locations(monkeypatch, tmp_path):
    """Point locations_db at a fresh temp file with known initial content.

    Same shape as the fixture in test_locations_atomic_write.py; duplicated
    so this test file can be deleted/skipped independently.
    """
    target = tmp_path / "locations.json"
    initial = [{"LocationID": "TEST-A", "Type": "Tool Head"}]
    target.write_text(json.dumps(initial, indent=4), encoding="utf-8")

    sys.path.insert(0, str(tmp_path.parent.parent / "inventory-hub"))
    import locations_db
    monkeypatch.setattr(locations_db, "JSON_FILE", str(target))
    monkeypatch.setattr(locations_db, "_DATA_DIR", str(tmp_path))
    return locations_db, target, initial


# ---------------------------------------------------------------------------
# (2) Per-call unique temp filename
# ---------------------------------------------------------------------------


def test_temp_filename_is_unique_per_call(temp_locations):
    """Two back-to-back writes must use DIFFERENT temp paths. Pre-hardening
    every call shared `JSON_FILE + '.tmp'`, which made concurrent writes
    race for the same name."""
    locations_db, target, initial = temp_locations

    captured_paths: list[str] = []
    real_NamedTemporaryFile = locations_db.tempfile.NamedTemporaryFile

    def spy(*args, **kwargs):
        f = real_NamedTemporaryFile(*args, **kwargs)
        captured_paths.append(f.name)
        return f

    with patch.object(locations_db.tempfile, "NamedTemporaryFile", side_effect=spy):
        locations_db.save_locations_list([{"LocationID": "FIRST", "Type": "Buffer"}])
        locations_db.save_locations_list([{"LocationID": "SECOND", "Type": "Buffer"}])

    assert len(captured_paths) == 2, f"expected 2 temp files, got {captured_paths!r}"
    assert captured_paths[0] != captured_paths[1], (
        f"two save calls reused the same temp path {captured_paths[0]!r}"
    )
    # Both temp paths must live in the same directory as JSON_FILE so
    # os.replace can be atomic (cross-filesystem renames are not).
    for p in captured_paths:
        assert os.path.dirname(p) == os.path.dirname(str(target)), (
            f"temp path {p!r} is not in JSON_FILE's directory"
        )


def test_concurrent_writes_do_not_corrupt_final_file(temp_locations):
    """N threads each call save_locations_list with a distinct, well-formed
    payload. Final on-disk content must parse as a list AND equal exactly
    one of the inputs (last-writer-wins, atomic). Pre-hardening, two
    threads sharing JSON_FILE+'.tmp' could interleave bytes and leave a
    corrupt final file."""
    locations_db, target, initial = temp_locations

    n_threads = 12
    payloads = [
        [{"LocationID": f"THREAD-{i:02d}", "Type": "Buffer", "ord": i}]
        for i in range(n_threads)
    ]

    barrier = threading.Barrier(n_threads)
    errors: list[BaseException] = []

    def write(payload):
        try:
            barrier.wait(timeout=5)
            locations_db.save_locations_list(payload)
        except BaseException as exc:  # noqa: BLE001 — we re-raise via the list
            errors.append(exc)

    threads = [threading.Thread(target=write, args=(p,)) for p in payloads]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    assert not errors, f"thread(s) raised: {errors!r}"

    final = json.loads(target.read_text(encoding="utf-8"))
    assert isinstance(final, list), f"final file is not a JSON list: {final!r}"
    # The final content must equal exactly one of the inputs — i.e. one of
    # the threads' writes won the os.replace race, and no in-flight bytes
    # bled across.
    assert final in payloads, (
        f"final on-disk content {final!r} does not match any of the {n_threads} "
        f"thread payloads — concurrent-write corruption"
    )


# ---------------------------------------------------------------------------
# (1) Post-write read-back-and-verify + retry
# ---------------------------------------------------------------------------


def test_verify_after_write_logs_critical_on_corruption(temp_locations, caplog):
    """If os.replace lands but the resulting file fails to parse, we log
    critical (so the operator sees it) and retry once."""
    locations_db, target, initial = temp_locations

    call_count = {"replace": 0}
    real_replace = os.replace

    def sabotaging_replace(src, dst):
        """First call: replace into the target, then overwrite the target
        with garbage so the verify-after-write reads garbage. Second call
        (the retry): forward to the real os.replace — verify will pass."""
        call_count["replace"] += 1
        if call_count["replace"] == 1:
            real_replace(src, dst)
            with open(dst, "w", encoding="utf-8") as f:
                f.write("THIS IS NOT JSON")
        else:
            real_replace(src, dst)

    with caplog.at_level(logging.CRITICAL, logger="InventoryHub"):
        with patch.object(locations_db.os, "replace", side_effect=sabotaging_replace):
            locations_db.save_locations_list([
                {"LocationID": "RECOVERY", "Type": "Buffer"}
            ])

    # Both os.replace calls happened (initial write + retry).
    assert call_count["replace"] == 2, f"expected one initial write + one retry, got {call_count['replace']}"

    # The retry succeeded — file parses and equals our payload.
    final = json.loads(target.read_text(encoding="utf-8"))
    assert final == [{"LocationID": "RECOVERY", "Type": "Buffer"}]

    # And a critical-level message named the tripwire so the operator
    # can grep hub.log after the fact.
    critical_msgs = [r.message for r in caplog.records if r.levelno >= logging.CRITICAL]
    assert any("verify-after-write FAILED" in m for m in critical_msgs), (
        f"expected 'verify-after-write FAILED' critical log, got: {critical_msgs!r}"
    )


def test_verify_after_write_no_retry_when_clean(temp_locations, caplog):
    """The happy path stays silent (no critical noise per successful write)
    and does NOT issue a second write."""
    locations_db, target, initial = temp_locations

    call_count = {"replace": 0}
    real_replace = os.replace

    def counting_replace(src, dst):
        call_count["replace"] += 1
        return real_replace(src, dst)

    with caplog.at_level(logging.WARNING, logger="InventoryHub"):
        with patch.object(locations_db.os, "replace", side_effect=counting_replace):
            locations_db.save_locations_list([{"LocationID": "HAPPY", "Type": "Buffer"}])

    assert call_count["replace"] == 1, (
        f"expected exactly one os.replace on the happy path, got {call_count['replace']}"
    )
    # No critical-level chatter for a clean write.
    critical_msgs = [r.message for r in caplog.records if r.levelno >= logging.CRITICAL]
    assert not critical_msgs, f"unexpected critical log on happy path: {critical_msgs!r}"


def test_verify_after_write_retry_failure_logs_critical(temp_locations, caplog):
    """If the retry ALSO produces a non-parseable file, we log critical
    again (so the operator knows the second write didn't recover) and
    do NOT raise — the caller already got 'success' control flow."""
    locations_db, target, initial = temp_locations

    real_replace = os.replace

    def always_sabotage(src, dst):
        real_replace(src, dst)
        with open(dst, "w", encoding="utf-8") as f:
            f.write("STILL NOT JSON")

    with caplog.at_level(logging.CRITICAL, logger="InventoryHub"):
        with patch.object(locations_db.os, "replace", side_effect=always_sabotage):
            # Should not raise.
            locations_db.save_locations_list([{"LocationID": "DOOMED", "Type": "Buffer"}])

    critical_msgs = [r.message for r in caplog.records if r.levelno >= logging.CRITICAL]
    # We expect at least two critical lines — the initial tripwire + the
    # "retry STILL failed" follow-up.
    assert sum("verify-after-write" in m for m in critical_msgs) >= 2, (
        f"expected ≥2 verify-after-write critical lines, got: {critical_msgs!r}"
    )
