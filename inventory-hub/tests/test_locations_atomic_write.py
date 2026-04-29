"""Regression test for the atomic-write fix on `locations_db.save_locations_list`.

The 2026-04-28 dev corruption ("valid content + duplicate `}\\n]` tail") was
caused by a non-atomic `open('w') + json.dump` write that left a partially
overwritten file when interrupted or raced. The fix uses a temp-file + fsync
+ os.replace pattern. These tests pin the contract:

  - On success, JSON_FILE contains exactly the new content (no leftover
    bytes from a longer prior version).
  - On a write that fails mid-stream, JSON_FILE retains the OLD content
    (atomic-or-nothing semantics) and no `.tmp` file is left behind.
  - The temp file lives in the same directory as the target (so os.replace
    can be atomic — cross-filesystem renames are not atomic).
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from unittest.mock import patch

import pytest


@pytest.fixture
def temp_locations(monkeypatch, tmp_path):
    """Point locations_db at a fresh temp file with known initial content."""
    target = tmp_path / "locations.json"
    initial = [{"LocationID": "TEST-A", "Type": "Tool Head"}]
    target.write_text(json.dumps(initial, indent=4), encoding="utf-8")

    # Import lazily because locations_db pulls in `state` which has app deps.
    sys.path.insert(0, str(tmp_path.parent.parent / "inventory-hub"))
    import locations_db
    monkeypatch.setattr(locations_db, "JSON_FILE", str(target))
    monkeypatch.setattr(locations_db, "_DATA_DIR", str(tmp_path))
    return locations_db, target, initial


def test_successful_write_replaces_file_exactly(temp_locations):
    locations_db, target, initial = temp_locations
    new_list = [
        {"LocationID": "NEW-1", "Type": "Buffer"},
        {"LocationID": "NEW-2", "Type": "Tool Head"},
    ]
    locations_db.save_locations_list(new_list)
    on_disk = json.loads(target.read_text(encoding="utf-8"))
    assert on_disk == new_list


def test_shorter_new_content_does_not_leave_old_tail(temp_locations):
    """If the new content is SHORTER than the old, the file shouldn't have
    leftover bytes from the old content. (Non-atomic write would, if the
    old approach somehow appended; the atomic approach can't fail this way.)"""
    locations_db, target, initial = temp_locations
    # Write a 5-entry list first
    big = [{"LocationID": f"BIG-{i}", "Type": "Buffer"} for i in range(5)]
    locations_db.save_locations_list(big)

    # Now write a 1-entry list — file should have ONLY the small content.
    small = [{"LocationID": "SMALL", "Type": "Buffer"}]
    locations_db.save_locations_list(small)

    raw = target.read_text(encoding="utf-8")
    parsed = json.loads(raw)
    assert parsed == small
    # Belt-and-suspenders: file should not contain any BIG-* prefix anywhere.
    assert "BIG-" not in raw


def test_failed_write_leaves_old_content_intact(temp_locations):
    """If json.dump raises mid-write, the original file must remain valid
    and unchanged (atomic-or-nothing). The old open('w')+json.dump approach
    fails this test because open('w') truncates the original to 0 before
    json.dump even runs."""
    locations_db, target, initial = temp_locations

    class DumpExploder:
        """Stand-in for an unserializable value that json.dump trips on."""
        pass

    bad_list = [{"LocationID": "X", "exploder": DumpExploder()}]
    locations_db.save_locations_list(bad_list)

    # Original content must still be parseable and equal to what we put there.
    on_disk = json.loads(target.read_text(encoding="utf-8"))
    assert on_disk == initial


def test_failed_write_cleans_up_tmp_file(temp_locations):
    locations_db, target, initial = temp_locations

    class DumpExploder:
        pass

    bad_list = [{"LocationID": "X", "exploder": DumpExploder()}]
    locations_db.save_locations_list(bad_list)

    tmp_path = str(target) + ".tmp"
    assert not os.path.exists(tmp_path), \
        f"expected .tmp file to be cleaned up after failure, found {tmp_path}"


def test_empty_list_is_no_op(temp_locations):
    """save_locations_list short-circuits on empty input (existing behavior).
    Confirm the original file is untouched."""
    locations_db, target, initial = temp_locations
    locations_db.save_locations_list([])
    on_disk = json.loads(target.read_text(encoding="utf-8"))
    assert on_disk == initial


def test_tmp_file_is_in_same_directory_as_target(temp_locations):
    """os.replace is atomic only when source and dest are on the same
    filesystem. Putting the tmp file in the same directory as the target
    is the simplest way to guarantee that — pin this so a future refactor
    doesn't accidentally move it to /tmp or similar."""
    locations_db, target, initial = temp_locations

    captured = {}
    real_open = open

    def spy_open(path, *args, **kwargs):
        if str(path).endswith(".tmp"):
            captured["tmp_path"] = str(path)
        return real_open(path, *args, **kwargs)

    with patch("builtins.open", side_effect=spy_open):
        locations_db.save_locations_list([{"LocationID": "Z", "Type": "Buffer"}])

    assert "tmp_path" in captured, "expected a .tmp write during save"
    assert os.path.dirname(captured["tmp_path"]) == os.path.dirname(str(target))
