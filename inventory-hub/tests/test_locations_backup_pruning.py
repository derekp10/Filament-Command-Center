"""Unit tests for `app._prune_locations_backups` (L347 follow-up).

Each locations.json pre-migration backup writes a timestamped `.bak`; nothing
deletes them. The prune helper keeps the most-recently-modified
MAX_LOCATIONS_BACKUPS and drops the rest.

These tests were relocated here from `test_filabridge_recovery.py` during the
FilaBridge Phase-2 cutover (Phase E Slice 3): the backup-pruning helper has
nothing to do with FilaBridge — it shared that file only by historical
accident — so it outlives the retired FB-recovery surface.
"""
import os
import time


def test_prune_locations_backups_under_cap_does_nothing(tmp_path):
    import app as flask_app
    json_file = tmp_path / "locations.json"
    json_file.write_text("{}")
    # 3 backups, cap of 5 → no eviction.
    for i in range(3):
        (tmp_path / f"locations.json.pre-test-{i:04d}.bak").write_text(f"backup {i}")
    deleted = flask_app._prune_locations_backups(str(json_file), keep=5)
    assert deleted == []
    surviving = sorted(p.name for p in tmp_path.glob("locations.json.pre-*.bak"))
    assert len(surviving) == 3


def test_prune_locations_backups_keeps_most_recent_n(tmp_path):
    import app as flask_app
    json_file = tmp_path / "locations.json"
    json_file.write_text("{}")
    # 8 backups with monotonically increasing mtime so "newest" is
    # deterministic. tmp_path is fresh per test so no interference.
    paths = []
    for i in range(8):
        p = tmp_path / f"locations.json.pre-test-{i:04d}.bak"
        p.write_text(f"backup {i}")
        # Stamp mtime forward so the newest file has the largest mtime
        # regardless of FS time resolution.
        os.utime(p, (time.time() + i, time.time() + i))
        paths.append(p)
    deleted = flask_app._prune_locations_backups(str(json_file), keep=5)
    # 8 backups, keep 5 → 3 deleted.
    assert len(deleted) == 3
    surviving = sorted(p.name for p in tmp_path.glob("locations.json.pre-*.bak"))
    assert len(surviving) == 5
    # The 5 newest (highest mtime = highest index) survive.
    assert "locations.json.pre-test-0007.bak" in surviving
    assert "locations.json.pre-test-0003.bak" in surviving
    # The 3 oldest are gone.
    assert "locations.json.pre-test-0000.bak" not in surviving
    assert "locations.json.pre-test-0002.bak" not in surviving


def test_prune_locations_backups_handles_missing_dir(tmp_path):
    """If the .bak pattern matches nothing (fresh install / wrong dir),
    the helper must return an empty list without erroring."""
    import app as flask_app
    json_file = tmp_path / "subdir-does-not-exist" / "locations.json"
    # Don't create the path. glob just returns [].
    deleted = flask_app._prune_locations_backups(str(json_file), keep=5)
    assert deleted == []
