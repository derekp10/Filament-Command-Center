"""Group 45.9: host test runs read and write their own data folder, never dev's
live inventory-hub/data/.

Before 45.9, locations_db fixed its folder at import as 'data', relative to the
working directory, and about 140 test files import app, whose import runs the
startup migrations and the backup prune against it (app.py:153-157). So a run
from inventory-hub/ (the canonical one) opened dev's live locations.json from
the host, ready to rewrite it the day a migration had work and to delete its
oldest backup the day there were six; the four JSON stores and attr_migration,
module-relative, sat in the same live folder. state.py opened 'hub.log' in the
working directory at import.

Now tests/conftest.py, above every backend import, points FCC_DATA_DIR at a
folder made for the run, outside inventory-hub/: a copy of dev's locations.json
with every printer login dropped, and no store files. The backend reads the
variable once at import and keeps today's exact paths when it is unset (dev's
container and prod never set it). --offline with a reset is refused.

Hermetic: these run under --offline. The subprocess pins start Python or pytest
with this machine's interpreter and touch no network.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time

import pytest

import attr_migration
import cancel_fetch_store
import cancel_review_store
import conftest
import locations_db
import print_deduct_ledger
import print_tracker_store
import state

HUB = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DEV_DATA = os.path.join(HUB, "data")


def _inside(path, folder):
    """`path` is `folder` or under it. Drive-safe on purpose: os.path.commonpath
    raises ValueError for two Windows drives (Derek's TEMP is on C:, the repo on
    D:). Kept here rather than imported from conftest, so on the old code each
    pin fails on its own assert."""
    p = os.path.normcase(os.path.realpath(path))
    f = os.path.normcase(os.path.realpath(folder))
    return p == f or p.startswith(f.rstrip("\\/") + os.sep)


def _run_dir():
    d = os.environ.get("FCC_DATA_DIR")
    assert d, "conftest set no FCC_DATA_DIR, so the backend took the working directory's data/"
    return d


# --- the run's own folder ----------------------------------------------------

def test_the_run_has_its_own_data_folder_outside_inventory_hub():
    d = _run_dir()
    assert d == getattr(conftest, "FCC_TEST_DATA_DIR", None)
    assert os.path.isabs(d) and os.path.isdir(d), d
    # Outside the folder dev's container mounts, so the container never sees the
    # copy, and app._compute_build_mtime (which skips only folders named 'data')
    # never counts it.
    assert not _inside(d, HUB), f"{d} is inside {HUB}"


def test_every_data_path_was_set_inside_the_runs_folder_at_import(monkeypatch):
    """Red if a backend module is imported before conftest's block (an import
    moved above it, a -p plugin), or stops reading FCC_DATA_DIR: the run would
    be back on dev's live files."""
    d = _run_dir()
    # conftest's autouse _isolate_attr_migration_state points attr_migration at
    # this test's tmp_path; undo it to see the paths the module set at import.
    monkeypatch.undo()
    for name, path in (
            ("locations_db._DATA_DIR", locations_db._DATA_DIR),
            ("locations_db.JSON_FILE", os.path.dirname(locations_db.JSON_FILE)),
            ("cancel_fetch_store._STORE_PATH", os.path.dirname(cancel_fetch_store._STORE_PATH)),
            ("cancel_review_store._STORE_PATH", os.path.dirname(cancel_review_store._STORE_PATH)),
            ("print_deduct_ledger._LEDGER_PATH", os.path.dirname(print_deduct_ledger._LEDGER_PATH)),
            ("print_tracker_store._STORE_PATH", os.path.dirname(print_tracker_store._STORE_PATH)),
            ("attr_migration._DATA_DIR", attr_migration._DATA_DIR),
            ("attr_migration._HIDDEN_PATH", os.path.dirname(attr_migration._HIDDEN_PATH))):
        assert os.path.normcase(os.path.abspath(path)) == os.path.normcase(d), (name, path, d)
    # The legacy sources sit beside the folder, never in the working directory.
    for name, path in (("locations_db._LEGACY_JSON_FILE", locations_db._LEGACY_JSON_FILE),
                       ("locations_db.CSV_FILE", locations_db.CSV_FILE)):
        assert os.path.dirname(path) == os.path.dirname(d), (name, path)


def test_the_runs_folder_began_with_the_copy_alone():
    """No store file: app's import re-surfaces no review card and lists no
    attribute snapshot from dev's live files."""
    assert getattr(conftest, "SESSION_DATA_DIR_STARTED_WITH", None) == ["locations.json"]


def test_the_session_copy_holds_no_printer_login():
    with open(os.path.join(_run_dir(), "locations.json"), encoding="utf-8") as f:
        rows = json.load(f)
    held = [r.get("LocationID") for r in rows if isinstance(r, dict) and "printer_creds" in r]
    assert held == [], f"the run's copy carries printer logins for {held}"


# --- conftest's helpers ------------------------------------------------------

def test_seeding_drops_logins_and_keeps_every_other_field(tmp_path):
    seed = getattr(conftest, "seed_session_locations", None)
    assert seed, "conftest has no seed_session_locations"
    rows = [
        {"LocationID": "PRN", "Type": "Printer", "Name": "Printer",
         "printer_creds": {"ip_address": "203.0.113.5", "api_key": "made-up"},
         "toolheads": [{"location_id": "PRN-1", "position": 0}]},
        {"LocationID": "PRN-1", "Type": "Tool Head", "Name": "Head 1 é", "parent_id": "PRN"},
        "not a row",
    ]
    src = tmp_path / "src.json"
    src.write_text(json.dumps(rows), encoding="utf-8")
    out = tmp_path / "run"
    out.mkdir()
    assert seed(str(out), source=str(src)) == "copied"
    copy = json.loads((out / "locations.json").read_text(encoding="utf-8"))
    expected = [dict(rows[0]), rows[1], rows[2]]
    del expected[0]["printer_creds"]
    assert copy == expected


@pytest.mark.parametrize("content,kind,reads_as", [
    (None, "missing", []),                        # a fresh checkout or a worktree
    (b'{"LocationID": "A"}', "not a list", []),   # locations_db reads a non-list root as []
    (b'[{"LocationID": "A"},', "unparseable", None),
])
def test_seeding_a_missing_odd_or_broken_dev_file(tmp_path, content, kind, reads_as):
    """Never left missing (locations_db would then move a locations.json or a
    CSV from the folder above into the run's folder), and a broken dev file
    reads as broken, never as empty, without carrying dev's bytes."""
    seed = getattr(conftest, "seed_session_locations", None)
    reads = getattr(conftest, "_read_dev_locations", None)
    assert seed and reads, "conftest has no seed_session_locations / _read_dev_locations"
    src = tmp_path / "src.json"
    if content is not None:
        src.write_bytes(content)
    out = tmp_path / "run"
    out.mkdir()
    if content is not None and kind == "unparseable":
        # No retry pause in a unit test.
        assert reads(str(src), pause_s=0) == ("unparseable", None)
    assert seed(str(out), source=str(src)) == kind
    written = (out / "locations.json").read_bytes()
    if reads_as is None:
        with pytest.raises(ValueError):
            json.loads(written.decode("utf-8"))
        assert content not in written
    else:
        assert json.loads(written.decode("utf-8")) == reads_as


def test_prune_takes_only_day_old_run_folders(tmp_path):
    prune = getattr(conftest, "_prune_stale_data_dirs", None)
    assert prune, "conftest has no _prune_stale_data_dirs"
    old, young, other = tmp_path / "run-1-a", tmp_path / "run-2-b", tmp_path / "keep"
    for p in (old, young, other):
        p.mkdir()
    t = os.path.getmtime(young)
    for p in (old, other):
        os.utime(p, (t - 2 * 86400, t - 2 * 86400))
    prune(str(tmp_path), now=t)
    assert not old.exists() and young.exists() and other.exists()


def test_reset_dev_is_never_handed_the_runs_folder(monkeypatch):
    """reset_dev.py writes dev's real locations.json by absolute path."""
    env_without = getattr(conftest, "env_without_test_data_dir", None)
    assert env_without, "conftest has no env_without_test_data_dir"
    monkeypatch.setenv("FCC_DATA_DIR", "somewhere")
    env = env_without(EXTRA="1")
    assert "FCC_DATA_DIR" not in env and env["EXTRA"] == "1"


# --- the backend's paths, with and without FCC_DATA_DIR ----------------------

# Imports ONLY the modules that read FCC_DATA_DIR, plus state; never app, and it
# calls nothing that reads a data file.
_PATHS_SCRIPT = r"""
import json, sys
sys.path.insert(0, sys.argv[1])
import locations_db, cancel_fetch_store, cancel_review_store, print_deduct_ledger
import print_tracker_store, attr_migration, state
print("@@" + json.dumps({
    "locations_db._DATA_DIR": locations_db._DATA_DIR,
    "locations_db.JSON_FILE": locations_db.JSON_FILE,
    "locations_db._LEGACY_JSON_FILE": locations_db._LEGACY_JSON_FILE,
    "locations_db.CSV_FILE": locations_db.CSV_FILE,
    "cancel_fetch_store._STORE_PATH": cancel_fetch_store._STORE_PATH,
    "cancel_review_store._STORE_PATH": cancel_review_store._STORE_PATH,
    "print_deduct_ledger._LEDGER_PATH": print_deduct_ledger._LEDGER_PATH,
    "print_tracker_store._STORE_PATH": print_tracker_store._STORE_PATH,
    "attr_migration._DATA_DIR": attr_migration._DATA_DIR,
    "attr_migration._HIDDEN_PATH": attr_migration._HIDDEN_PATH,
    "state.f_handler.baseFilename": state.f_handler.baseFilename,
    "app imported": "app" in sys.modules,
}))
"""


def _clean_env(**extra):
    """Only what Python needs to start on this PC (APPDATA finds the user
    site-packages, where requests lives): no FCC_* variable at all."""
    keep = ("SYSTEMROOT", "WINDIR", "PATH", "PATHEXT", "COMSPEC", "TEMP", "TMP",
            "APPDATA", "LOCALAPPDATA", "USERPROFILE", "HOMEDRIVE", "HOMEPATH")
    env = {k: os.environ[k] for k in keep if k in os.environ}
    env.update(extra)
    return env


def _paths(env):
    proc = subprocess.run([sys.executable, "-E", "-B", "-X", "utf8", "-c", _PATHS_SCRIPT, HUB],
                          cwd=HUB, env=env, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=120)
    lines = [ln for ln in proc.stdout.splitlines() if ln.startswith("@@")]
    assert proc.returncode == 0 and lines, (proc.returncode, proc.stdout[-3000:], proc.stderr[-3000:])
    got = json.loads(lines[-1][2:])
    assert got.pop("app imported") is False
    return got


def test_with_fcc_data_dir_unset_every_path_is_todays():
    """Dev's container and prod never set it: every path is the one they always
    had, written out here rather than computed from the modules."""
    got = _paths(_clean_env())
    sep = os.sep
    expected = {
        "locations_db._DATA_DIR": "data",
        "locations_db.JSON_FILE": "data" + sep + "locations.json",
        "locations_db._LEGACY_JSON_FILE": "locations.json",
        "locations_db.CSV_FILE": "3D Print Supplies - Locations.csv",
        "cancel_fetch_store._STORE_PATH": HUB + sep + "data" + sep + "pending_cancel_fetches.json",
        "cancel_review_store._STORE_PATH": HUB + sep + "data" + sep + "pending_cancel_deducts.json",
        "print_deduct_ledger._LEDGER_PATH": HUB + sep + "data" + sep + "print_deduct_ledger.json",
        "print_tracker_store._STORE_PATH": HUB + sep + "data" + sep + "print_tracker_latch.json",
        "attr_migration._DATA_DIR": HUB + sep + "data",
        "attr_migration._HIDDEN_PATH": HUB + sep + "data" + sep + "attr_hidden_choices.json",
    }
    log = got.pop("state.f_handler.baseFilename")
    assert got == expected
    assert os.path.normcase(log) == os.path.normcase(HUB + sep + "hub.log")


def test_with_fcc_data_dir_set_every_data_path_moves_into_it(tmp_path):
    d = str(tmp_path / "fcc-data")
    os.mkdir(d)
    got = _paths(_clean_env(FCC_DATA_DIR=d))
    j = os.path.join
    expected = {
        "locations_db._DATA_DIR": d,
        "locations_db.JSON_FILE": j(d, "locations.json"),
        # The legacy sources beside the folder, never in the working directory.
        "locations_db._LEGACY_JSON_FILE": j(str(tmp_path), "locations.json"),
        "locations_db.CSV_FILE": j(str(tmp_path), "3D Print Supplies - Locations.csv"),
        "cancel_fetch_store._STORE_PATH": j(d, "pending_cancel_fetches.json"),
        "cancel_review_store._STORE_PATH": j(d, "pending_cancel_deducts.json"),
        "print_deduct_ledger._LEDGER_PATH": j(d, "print_deduct_ledger.json"),
        "print_tracker_store._STORE_PATH": j(d, "print_tracker_latch.json"),
        "attr_migration._DATA_DIR": d,
        "attr_migration._HIDDEN_PATH": j(d, "attr_hidden_choices.json"),
    }
    log = got.pop("state.f_handler.baseFilename")
    assert got == expected
    # The server's log isn't data: it stays in the working directory.
    assert os.path.normcase(log) == os.path.normcase(j(HUB, "hub.log"))


def test_state_opens_hub_log_only_at_the_first_log_line():
    """RotatingFileHandler(..., delay=True). A 'stream is None' check can't tell:
    conftest closes the handler, and a closed delay=False handler's stream is
    None too."""
    assert state.f_handler.delay is True


# --- a host `import app` -----------------------------------------------------

# Rows the startup migrations have work on (no parent_id), so the import really
# writes, and the pin can see where.
_FIXTURE_ROWS = [
    {"LocationID": "LR", "Name": "Living Room", "Type": "Room"},
    {"LocationID": "LR-MDB-1", "Name": "Box 1", "Type": "Dryer Box", "Max Spools": "4"},
]

_IMPORT_APP_SCRIPT = r"""
import json, sys
sys.path.insert(0, sys.argv[1])
import state
# Detached as conftest does it: from inventory-hub/ the relative 'hub.log' is
# the dev container's live log, and the migrations below log.
state.logger.removeHandler(state.f_handler)
state.f_handler.close()
import app  # the startup migrations, the backup prune and both re-surfaces
import locations_db
print("@@" + json.dumps({"json_file": locations_db.JSON_FILE}))
"""

# Files the running container writes on its own: the print latch every monitor
# tick, the stores and the ledger at a print's start or end (their .tmp siblings
# too). `import app` only reads them (the review re-surface), so leaving them out
# loses nothing here, and a print ending during the pin can't turn it red. That
# the stores follow FCC_DATA_DIR is pinned above.
_CONTAINER_RUNTIME_FILES = ("print_tracker_latch.json", "pending_cancel_fetches.json",
                            "pending_cancel_deducts.json", "print_deduct_ledger.json")


def _snapshot(folder):
    """{relative path: sha256} of every file under `folder` but the container's
    runtime files."""
    out = {}
    for root, _dirs, files in os.walk(folder):
        for name in files:
            if name.startswith(_CONTAINER_RUNTIME_FILES):
                continue
            path = os.path.join(root, name)
            for attempt in range(5):
                try:
                    with open(path, "rb") as f:
                        out[os.path.relpath(path, folder)] = hashlib.sha256(f.read()).hexdigest()
                    break
                except FileNotFoundError:
                    break   # replaced and gone this instant: the diff says so
                except OSError:  # held by a write this instant
                    time.sleep(0.2)
            else:
                out[os.path.relpath(path, folder)] = "unreadable"
    return out


def test_a_host_import_of_app_leaves_devs_data_folder_alone(tmp_path):
    """From inventory-hub/, where the relative data/ IS dev's live folder: with
    FCC_DATA_DIR set, the migrations write in that folder and nothing in dev's,
    and importing creates no hub.log in the working directory."""
    d = tmp_path / "data"
    d.mkdir()
    (d / "locations.json").write_text(json.dumps(_FIXTURE_ROWS), encoding="utf-8")
    log = os.path.join(HUB, "hub.log")
    log_was_there = os.path.exists(log)
    before = _snapshot(DEV_DATA)
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("FCC_", "RESET_DEV", "PYTEST_"))}
    env["FCC_DATA_DIR"] = str(d)
    proc = subprocess.run([sys.executable, "-B", "-X", "utf8", "-c", _IMPORT_APP_SCRIPT, HUB],
                          cwd=HUB, env=env, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=300)
    after = _snapshot(DEV_DATA)
    lines = [ln for ln in proc.stdout.splitlines() if ln.startswith("@@")]
    assert proc.returncode == 0 and lines, (proc.returncode, proc.stdout[-3000:], proc.stderr[-3000:])
    changed = sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))
    assert changed == [], f"importing app changed dev's data folder: {changed}"
    if not log_was_there:
        assert not os.path.exists(log), "importing app created a hub.log in the working directory"
    assert _inside(json.loads(lines[-1][2:])["json_file"], str(d))
    baks = [n for n in os.listdir(d) if n.startswith("locations.json.pre-") and n.endswith(".bak")]
    assert baks, f"the migrations wrote nothing in the FCC_DATA_DIR folder: {os.listdir(d)}"


# --- --offline with a reset --------------------------------------------------

@pytest.mark.parametrize("args,env_extra", [
    (["--offline", "--reset-dev"], {}),
    (["--offline", "--reset-dev-prune"], {}),
    ([], {"FCC_OFFLINE": "1", "RESET_DEV_BEFORE_SWEEP": "1"}),
])
def test_offline_with_a_reset_is_refused(args, env_extra):
    """--offline promises that nothing touches dev, and a reset rewrites dev's
    locations.json and Spoolman and restarts the container. A real pytest, the
    canonical way (tests/conftest.py as the initial conftest), on a small test
    file. --co, so even on code that doesn't refuse, no fixture runs, and
    reset_dev.py can't start; the refusal comes before collection."""
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("FCC_", "RESET_DEV", "PYTEST_", "RUN_INTEGRATION"))}
    env.update(env_extra)
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "--co", "-q", "-p", "no:cacheprovider", *args,
         os.path.join("tests", "test_offline_mode.py")],
        cwd=HUB, env=env, capture_output=True, text=True, encoding="utf-8",
        errors="replace", timeout=300)
    out = proc.stdout + proc.stderr
    assert proc.returncode == pytest.ExitCode.USAGE_ERROR, (proc.returncode, out[-3000:])
    assert "can't be combined" in out, out[-3000:]
    assert "test_offline_mode.py::" not in out, "it collected: the refusal came too late"
    assert "[reset-dev]" not in out


# --- .build_info --------------------------------------------------------------

def test_build_info_is_written_only_when_its_bytes_change(tmp_path, monkeypatch):
    """Every host `import app` and every dashboard render rewrote it on dev's
    bind mount, the same bytes unless HEAD moved."""
    import _gen_build_info
    sha = {"v": "abcd1234"}
    monkeypatch.setattr(_gen_build_info, "find_git_dir", lambda start: str(tmp_path))
    monkeypatch.setattr(_gen_build_info, "resolve_head_sha", lambda git_dir: sha["v"])
    monkeypatch.setattr(_gen_build_info, "resolve_head_timestamp", lambda git_dir: 1700000000)
    out = tmp_path / ".build_info"
    assert _gen_build_info.write_build_info(str(out)) is True
    assert out.read_text(encoding="utf-8") == "abcd1234|1700000000\n"
    os.utime(out, (1_000_000_000, 1_000_000_000))
    assert _gen_build_info.write_build_info(str(out)) is True
    assert os.path.getmtime(out) == 1_000_000_000, "the same bytes were written again"
    sha["v"] = "ef567890"
    assert _gen_build_info.write_build_info(str(out)) is True
    assert out.read_text(encoding="utf-8") == "ef567890|1700000000\n"
