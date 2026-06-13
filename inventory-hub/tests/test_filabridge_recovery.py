"""Unit/integration tests for FilaBridge recovery endpoints and parsers.

Moved here from the legacy project-root `tests/` directory (2026-05-12, Group
16.1). Covers `/api/fb_recovery_spools`, `/api/fb_aggressive_parse`, the
prusalink fast/RAM parser fallback, and the FB error snapshot hook.
Companion to `test_filabridge_move_ordering.py` (different surface — that
file covers move ordering against FB rather than recovery).
"""
import json
import os

import pytest
from unittest.mock import patch


@pytest.fixture(autouse=True)
def _printer_map_from_config(monkeypatch):
    """L271 P4 step 2: app.py fb-recovery reads printer_map via
    locations_db.get_active_printer_map() now; these tests inject printer_map
    through the app.config_loader.load_config stub, so make the accessor delegate
    to it — mirrors the pre-swap `cfg.get('printer_map')` source exactly."""
    import app
    monkeypatch.setattr(
        app.locations_db, "get_active_printer_map",
        lambda loc_list=None: (app.config_loader.load_config() or {}).get("printer_map", {}) or {},
    )


@pytest.fixture
def mock_app():
    with patch("app.spoolman_api"), \
         patch("app.config_loader"), \
         patch("app.state") as mock_state:

        mock_state.AUDIT_SESSION = {"active": False}
        mock_state.UNDO_STACK = []
        mock_state.RECENT_LOGS = []
        mock_state.ACKNOWLEDGED_FILABRIDGE_ERRORS = set()

        import app as flask_app
        flask_app.app.config['TESTING'] = True
        yield flask_app.app.test_client()

def test_fb_recovery_spools(mock_app):
    with patch("app.config_loader.load_config") as mock_load:
        mock_load.return_value = {
            "printer_map": {
                "l-1": {"printer_name": "TestPrinter"}
            }
        }
        with patch("app.spoolman_api.get_spools_at_location_detailed") as mock_detailed:
            mock_detailed.return_value = [{"id": 1, "extra": {}}]

            res = mock_app.get("/api/fb_recovery_spools?printer_name=TestPrinter")
            assert res.status_code == 200
            data = res.get_json()
            assert data["success"] is True
            assert len(data["spools"]) == 1
            assert data["spools"][0]["id"] == 1

def test_fb_aggressive_parse(mock_app):
    with patch("app.config_loader.get_api_urls", return_value=("http://spool", "http://fb/api")), \
         patch("app.prusalink_api.fetch_printer_credentials", return_value={"ip_address": "1.2.3.4", "api_key": "abc"}), \
         patch("app.prusalink_api.download_gcode_and_parse_usage", return_value={0: 10.5}), \
         patch("app.config_loader.load_config") as mock_load, \
         patch("app.spoolman_api.get_spools_at_location", return_value=[123]), \
         patch("app.spoolman_api.get_spool", return_value={"id": 123, "used_weight": 10}), \
         patch("app.spoolman_api.format_spool_display", return_value={"color": "000000"}), \
         patch("app.spoolman_api.update_spool", return_value=True) as mock_update, \
         patch("app.prusalink_api.acknowledge_filabridge_error", return_value=True) as mock_ack:

        mock_load.return_value = {
            "printer_map": {
                "l-1": {"printer_name": "MyPrinter", "position": 0}
            }
        }

        res = mock_app.post("/api/fb_aggressive_parse", json={
            "printer_name": "MyPrinter",
            "filename": "test.gcode",
            "error_id": "err_1"
        })

        assert res.status_code == 200
        data = res.get_json()
        assert data["success"] is True

        # Verify it deducted 10.5g
        mock_update.assert_called_once_with(123, {"used_weight": 20.5})
        mock_ack.assert_called_once_with("http://fb/api", "err_1")

def test_prusalink_parser_ascii():
    """Plain-ASCII gcode: the footer parses straight through the decode chain.
    (Phase-2: the parser now routes through download_gcode_content, which decodes
    .bgcode and passes ASCII through — so we mock the byte download, not requests.)"""
    import prusalink_api as pa

    ascii_bytes = b"; metadata block\n; filament used [g] = 3.14, 5.22\n; end"
    with patch("prusalink_api._download_file_bytes", return_value=ascii_bytes):
        usage = pa.download_gcode_and_parse_usage("1.2.3.4", "key", "test.gcode")
    assert usage == {0: 3.14, 1: 5.22}
    assert pa.FB_PARSE_STATUS == "Decoded"


def test_prusalink_parser_bgcode_roundtrip():
    """The real fleet slices to binary .bgcode — the footer lives in the PrintMeta
    block, so the OLD text parser read ZERO. The decoder must lift it. This is the
    regression the old ASCII-only tests structurally couldn't catch."""
    import struct
    import prusalink_api as pa

    def _block(btype, payload, enc=0):  # uncompressed block (comp=0, checksum=0)
        return struct.pack("<HHI", btype, 0, len(payload)) + struct.pack("<H", enc) + payload

    body = b"M83\nT0\nG1 X10 E5\nG1 X20 E5\n"
    meta = b"filament used [mm] = 10\nfilament used [g] = 25\n"
    raw = (b"GCDE" + struct.pack("<I", 1) + struct.pack("<H", 0)
           + _block(4, meta) + _block(1, body))  # PrintMeta, GCode

    with patch("prusalink_api._download_file_bytes", return_value=raw):
        usage = pa.download_gcode_and_parse_usage("1.2.3.4", "key", "real.bgcode")
    assert usage == {0: 25.0}  # footer lifted out of the binary container
    assert pa.FB_PARSE_STATUS == "Decoded"


def test_prusalink_parser_download_failure_returns_none():
    import prusalink_api as pa
    with patch("prusalink_api._download_file_bytes", return_value=None):
        usage = pa.download_gcode_and_parse_usage("1.2.3.4", "key", "x.bgcode")
    assert usage is None
    assert "Failed to download" in pa.FB_PARSE_STATUS

# NOTE: the FilaBridge error-snapshot hook in /api/logs (the error-poll +
# _auto_recover_task) was retired in the FilaBridge Phase-2 cutover, Phase E
# Slice 2 — its test (`test_fb_error_snapshotting`) was removed with it. The
# /api/fb_* recovery endpoints + the snapshot store itself go in Slice 3.


# L347 — bounded snapshot store. The dict-cap helper is the seam: tests
# operate on synthetic dicts so they don't have to wire up the entire
# /api/logs polling loop just to assert the eviction policy.

def test_evict_old_fb_snapshots_returns_unchanged_under_cap():
    import app as flask_app
    snaps = {f"err_{i}": [{"id": i}] for i in range(50)}
    out = flask_app._evict_old_fb_snapshots(snaps, cap=100)
    assert out is snaps  # under cap → same dict, no copy
    assert len(out) == 50


def test_evict_old_fb_snapshots_caps_at_threshold():
    import app as flask_app
    # Insert 150 entries with monotonic timestamp-style suffixes so the
    # tail-N survivors are deterministically the highest-numbered ones.
    snaps = {f"err_{i:04d}": [{"id": i}] for i in range(150)}
    out = flask_app._evict_old_fb_snapshots(snaps, cap=100)
    assert len(out) == 100
    # The 100 newest (insertion-order) entries survive.
    assert "err_0050" in out
    assert "err_0149" in out
    # The oldest 50 were evicted.
    assert "err_0049" not in out
    assert "err_0000" not in out


def test_evict_old_fb_snapshots_handles_non_dict_input():
    import app as flask_app
    # Defensive — if the on-disk file is corrupt and parses to a list
    # or None, the helper must not crash. It just returns the input as-is
    # so the surrounding try/except can log + recover.
    assert flask_app._evict_old_fb_snapshots(None) is None
    assert flask_app._evict_old_fb_snapshots([]) == []


# L347 follow-up — locations.json pre-migration backup pruning. Each
# migration that fires writes a timestamped .bak; nothing deletes them.
# The prune helper keeps the most-recently-modified MAX_LOCATIONS_BACKUPS.

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
    import time
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


# L347 robustness — verify the recovery endpoint falls through to live
# data when the requested error_id has been evicted from the bounded
# snapshot store. Derek 2026-05-28: "Unless our code actively does
# something with the error codes we don't have to worry about external."

def test_fb_recovery_spools_evicted_error_id_falls_back_to_live_data(mock_app, tmp_path, monkeypatch):
    """An error_id that's been evicted from the snapshot cap must NOT
    cause the endpoint to error — it falls back to the live
    `get_spools_at_location_detailed` path so the user can still recover.
    This pins the fallback the L347 cap depends on for graceful aging."""
    import app as flask_app
    # Point the snapshot path at a tmp file containing 2 OTHER error_ids.
    # The one we request ("err_evicted_long_ago") is intentionally absent.
    snap_path = tmp_path / "filabridge_error_snapshots.json"
    snap_path.write_text(json.dumps({
        "err_recent_1": [{"id": 5, "extra": {}}],
        "err_recent_2": [{"id": 6, "extra": {}}],
    }))
    # Patch os.path.dirname(__file__) → tmp_path inside the endpoint via
    # the join call. Easier: monkeypatch the data path resolution.
    real_join = os.path.join
    def fake_join(*parts):
        # Catch the specific snapshots-file resolution and redirect.
        if parts and parts[-1] == "filabridge_error_snapshots.json":
            return str(snap_path)
        return real_join(*parts)
    monkeypatch.setattr(flask_app.os.path, "join", fake_join)

    with patch("app.config_loader.load_config") as mock_cfg, \
         patch("app.spoolman_api.get_spools_at_location_detailed",
               return_value=[{"id": 999, "extra": {}}]) as mock_live:
        mock_cfg.return_value = {
            "printer_map": {"l-1": {"printer_name": "TestPrinter"}}
        }
        res = mock_app.get(
            "/api/fb_recovery_spools"
            "?printer_name=TestPrinter&error_id=err_evicted_long_ago"
        )

    assert res.status_code == 200
    data = res.get_json()
    # Fall-through path: live spool data, not a snapshot reference.
    assert data["success"] is True
    assert len(data["spools"]) == 1
    assert data["spools"][0]["id"] == 999
    # The live path was actually exercised — not the cached snapshot.
    assert mock_live.called


def test_fb_recovery_spools_missing_snapshot_file_falls_back_to_live(mock_app, tmp_path, monkeypatch):
    """If the snapshot file doesn't exist at all (fresh install, pruned,
    or deleted), the endpoint still recovers via the live path."""
    import app as flask_app
    snap_path = tmp_path / "filabridge_error_snapshots.json"
    # Intentionally don't create the file.
    real_join = os.path.join
    def fake_join(*parts):
        if parts and parts[-1] == "filabridge_error_snapshots.json":
            return str(snap_path)
        return real_join(*parts)
    monkeypatch.setattr(flask_app.os.path, "join", fake_join)

    with patch("app.config_loader.load_config") as mock_cfg, \
         patch("app.spoolman_api.get_spools_at_location_detailed",
               return_value=[{"id": 42, "extra": {}}]):
        mock_cfg.return_value = {
            "printer_map": {"l-1": {"printer_name": "TestPrinter"}}
        }
        res = mock_app.get(
            "/api/fb_recovery_spools"
            "?printer_name=TestPrinter&error_id=any_error_id"
        )
    assert res.status_code == 200
    data = res.get_json()
    assert data["success"] is True
    assert data["spools"][0]["id"] == 42
