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

Also pinned here, conftest's other guards (Group 45, round 3): --reset-dev
stops before reset_dev.py on a PC with no local snapshot and puts reset_dev.py's
own words in its exit message; a DEV_SPOOLMAN_URL on prod Spoolman's port is
refused before collection; the page fixture closes its page before its routes
come off; and a .build_info write that fails says so.

Hermetic: these run under --offline. The subprocess pins start Python or pytest
with this machine's interpreter and touch no network.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys

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


def _key_paths(value, key, path="$"):
    """Every place in a parsed JSON value where a dict holds `key`."""
    found = []
    if isinstance(value, dict):
        if key in value:
            found.append(f"{path}.{key}")
        for k, v in value.items():
            found += _key_paths(v, key, f"{path}.{k}")
    elif isinstance(value, list):
        for i, v in enumerate(value):
            found += _key_paths(v, key, f"{path}[{i}]")
    return found


def test_conftest_strips_the_key_the_backend_keeps_logins_under():
    """conftest names the key itself (it runs before locations_db can be
    imported). Renamed in locations_db alone, logins would ride into every
    run's copy with each other pin here still green."""
    assert locations_db.PRINTER_CREDS_KEY == "printer_creds", (
        "locations_db keeps printer logins under a new key: update the key "
        "tests/conftest.py's seed_session_locations drops, then this pin")


def test_the_session_copy_holds_no_printer_login():
    with open(os.path.join(_run_dir(), "locations.json"), encoding="utf-8") as f:
        rows = json.load(f)
    # Values are never printed: the paths say where, never what.
    held = _key_paths(rows, locations_db.PRINTER_CREDS_KEY)
    assert held == [], f"the run's copy carries printer logins at {held}"


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


def _run_reset_fixture(monkeypatch, tmp_path, calls, answer=None, snapshot=("locations", "spoolman")):
    """_reset_dev_baseline's own function, run with a config that asks for a
    reset. reset_dev.py's subprocess, the wait for the server and the seeding
    are stood in for and logged in `calls`, in order, so nothing runs and
    nothing is written. `answer()` plays reset_dev.py (returns its result or
    raises; default: it worked, saying nothing). The local snapshot is two files
    in tmp_path, `snapshot` naming the ones that exist. A pytest.exit
    propagates."""
    import inspect
    import types
    for name in ("RESET_DEV_BEFORE_SWEEP", "RESET_DEV_PRUNE"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("FCC_DATA_DIR", conftest.FCC_TEST_DATA_DIR)   # as the run set it
    files = []
    for name in ("locations", "spoolman"):
        path = tmp_path / f"snapshot-{name}.json"
        if name in snapshot:
            path.write_text("[]", encoding="utf-8")
        files.append(str(path))
    # raising=False: on code with no snapshot check this sets a name nothing
    # reads, so the pins below fail on what the fixture does, not on the name.
    monkeypatch.setattr(conftest, "RESET_DEV_SNAPSHOT", tuple(files), raising=False)

    def run(cmd, **kwargs):
        calls.append(("run", cmd, kwargs))
        if answer is not None:
            return answer()
        return types.SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(conftest, "subprocess", types.SimpleNamespace(run=run))
    monkeypatch.setattr(conftest, "_wait_for_server", lambda base_url, *a, **k: calls.append(("wait", base_url)))
    monkeypatch.setattr(conftest, "seed_session_locations", lambda data_dir, *a, **k: calls.append(("seed", data_dir)))
    request = types.SimpleNamespace(config=types.SimpleNamespace(getoption=lambda name: name == "--reset-dev"))
    gen = inspect.unwrap(conftest._reset_dev_baseline)(request)
    try:
        next(gen)      # up to its yield: the reset has run
    finally:
        gen.close()


def test_the_reset_fixture_hands_reset_dev_that_env_and_seeds_the_copy_again(monkeypatch, tmp_path):
    """The helper above is only half of it: _reset_dev_baseline must pass its env
    to reset_dev.py, and take the run's copy again once the container is back
    (the copy was made at conftest import, before the reset)."""
    calls = []
    _run_reset_fixture(monkeypatch, tmp_path, calls)
    assert [c[0] for c in calls] == ["run", "wait", "seed"], calls
    cmd, kwargs = calls[0][1], calls[0][2]
    assert os.path.basename(cmd[-1]) == "reset_dev.py" and "--prune" not in cmd, cmd
    env = kwargs.get("env")
    assert env is not None, "reset_dev.py would inherit this run's FCC_DATA_DIR"
    assert "FCC_DATA_DIR" not in env, "reset_dev.py was handed the run's folder"
    # The helper's env, plus UTF-8 for reset_dev.py's output, which is read back.
    assert env == conftest.env_without_test_data_dir(PYTHONIOENCODING="utf-8"), "not the env the helper builds"
    assert calls[2][1] == conftest.FCC_TEST_DATA_DIR, calls[2]


@pytest.mark.parametrize("present", [("spoolman",), ("locations",), ()])
def test_the_reset_fixture_stops_before_reset_dev_on_a_pc_with_no_snapshot(monkeypatch, tmp_path, present):
    """The snapshot is local since 2026-11-13, so a fresh clone has none. The run
    stops with a plain message naming what is missing and how to make it, before
    reset_dev.py starts (pytest.exit shows no captured output, so reset_dev.py's
    own refusal read as 'exit status 2')."""
    calls = []
    with pytest.raises(pytest.exit.Exception) as stopped:
        _run_reset_fixture(monkeypatch, tmp_path, calls, snapshot=present)
    assert calls == [], f"it went on to {[c[0] for c in calls]}"
    msg = str(stopped.value.msg)
    for name in ("locations", "spoolman"):
        path = str(tmp_path / f"snapshot-{name}.json")
        assert (path in msg) == (name not in present), (name, msg)
    assert "reset_dev.py --capture" in msg and "setup-and-rebuild/seeds/README.md" in msg, msg
    assert "nothing was reset" in msg, msg


@pytest.mark.parametrize("how", ["exit 2", "timeout"])
def test_a_failed_reset_puts_reset_devs_own_words_in_the_exit_message(monkeypatch, tmp_path, how):
    """reset_dev.py's output is read back, so the message that ends the run says
    what went wrong (pytest.exit shows no captured output); nothing waits for the
    server or takes the copy again."""
    import types
    said = "!! dev Spoolman refused a PATCH: HTTP 500 database is locked"

    def answer():
        if how == "timeout":
            # subprocess.run's own exception, with the output so far (bytes on POSIX).
            raise subprocess.TimeoutExpired(["reset_dev.py"], 300, output=("restoring...\n" + said).encode())
        return types.SimpleNamespace(returncode=2, stdout="restoring...\n" + said + "\n",
                                     stderr="Traceback (most recent call last):\n  boom\n")

    calls = []
    with pytest.raises(pytest.exit.Exception) as stopped:
        _run_reset_fixture(monkeypatch, tmp_path, calls, answer=answer)
    assert [c[0] for c in calls] == ["run"], calls
    kwargs = calls[0][2]
    assert kwargs.get("capture_output") or kwargs.get("stdout") is not None, \
        "reset_dev.py's output isn't read, so the message can't hold it"
    msg = str(stopped.value.msg)
    assert said in msg, msg
    assert "dirty baseline" in msg, msg
    if how == "exit 2":
        assert "exited 2" in msg and "boom" in msg, msg


def test_the_reset_fixture_checks_the_files_reset_dev_restores_from():
    """conftest names the snapshot files itself, so it can check them before
    reset_dev.py starts: they must be the ones reset_dev.py reads. Imported as
    tests/test_reset_dev.py imports it (by path; its module body only defines)."""
    import importlib.util
    path = os.path.join(HUB, "..", "setup-and-rebuild", "reset_dev.py")
    spec = importlib.util.spec_from_file_location("_reset_dev_for_the_snapshot_pin", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    norm = lambda p: os.path.normcase(os.path.abspath(p))   # noqa: E731
    assert sorted(map(norm, getattr(conftest, "RESET_DEV_SNAPSHOT", ()))) == \
        sorted(map(norm, (mod.LOCATIONS_SEED, mod.SPOOLMAN_SEED))), (
        "conftest.RESET_DEV_SNAPSHOT and reset_dev.py's LOCATIONS_SEED / SPOOLMAN_SEED name "
        "different files: move them together")


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
# Detached as conftest does it (from inventory-hub/ the relative 'hub.log' is the
# dev container's live log), so the migrations' log lines below never open it. A
# handler that opened the file at `import state` (delay=False) has made it by now.
state.logger.removeHandler(state.f_handler)
state.f_handler.close()
import app  # the startup migrations, the backup prune and both re-surfaces
import locations_db
print("@@" + json.dumps({"json_file": locations_db.JSON_FILE}))
"""


def _snapshot(folder):
    """{relative path: sha256} of every file under `folder`."""
    out = {}
    for root, _dirs, files in os.walk(folder):
        for name in files:
            path = os.path.join(root, name)
            with open(path, "rb") as f:
                out[os.path.relpath(path, folder)] = hashlib.sha256(f.read()).hexdigest()
    return out


def test_a_host_import_of_app_leaves_the_working_directorys_data_folder_alone(tmp_path):
    """From inventory-hub/ (the canonical run) the working directory's data/ IS
    dev's live folder. Here the import runs from a working directory of its own
    whose data/ holds rows the migrations have work on, a decoy for dev's: with
    FCC_DATA_DIR set, the migrations write in the FCC_DATA_DIR folder and nothing
    in the decoy, and importing creates no hub.log in the working directory. If
    the backend ever stopped honouring FCC_DATA_DIR, the decoy takes the
    migration and the prune, never dev's files, and dev's container writing its
    own folder meanwhile can't turn this red."""
    cwd = tmp_path / "cwd"
    decoy = cwd / "data"
    decoy.mkdir(parents=True)
    (decoy / "locations.json").write_text(json.dumps(_FIXTURE_ROWS), encoding="utf-8")
    d = tmp_path / "fcc-data"
    d.mkdir()
    (d / "locations.json").write_text(json.dumps(_FIXTURE_ROWS), encoding="utf-8")
    before = _snapshot(decoy)
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("FCC_", "RESET_DEV", "PYTEST_"))}
    env["FCC_DATA_DIR"] = str(d)
    proc = subprocess.run([sys.executable, "-B", "-X", "utf8", "-c", _IMPORT_APP_SCRIPT, HUB],
                          cwd=str(cwd), env=env, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=300)
    lines = [ln for ln in proc.stdout.splitlines() if ln.startswith("@@")]
    assert proc.returncode == 0 and lines, (proc.returncode, proc.stdout[-3000:], proc.stderr[-3000:])
    after = _snapshot(decoy)
    changed = sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))
    assert changed == [], f"importing app changed the working directory's data folder: {changed}"
    assert not (cwd / "hub.log").exists(), "importing app created a hub.log in the working directory"
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


# --- a DEV_SPOOLMAN_URL on prod's port ---------------------------------------

@pytest.mark.parametrize("url,prod", [
    ("http://192.168.1.29:7912", True),
    ("http://192.168.1.29:07912", True),            # the same port, zero-padded
    ("http://truenas.lan:7912/api/v1", True),       # another name for the NAS
    ("HTTP://[::1]:7912", True),
    (" http://192.168.1.29:7912 ", True),
    ("http://192.168.1.29:7913", False),            # dev Spoolman
    ("http://localhost:8000", False),
    ("http://192.168.1.29", False),
    ("http://192.168.1.29:notaport", False),        # requests can't reach it either
])
def test_prod_spoolmans_port_is_told_apart_from_devs(url, prod):
    names = getattr(conftest, "names_prod_spoolman", None)
    assert names, "conftest has no names_prod_spoolman"
    assert names(url) is prod, url


def test_a_dev_spoolman_url_on_prods_port_is_refused():
    """The tests write to the Spoolman DEV_SPOOLMAN_URL names (throwaway records,
    the integration tests, --reset-dev's reconcile), and since dev's 2026-11-13
    refresh dev and prod hold the same ids. A real pytest, --co, on a small test
    file: the refusal comes before collection, so nothing runs either way."""
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("FCC_", "RESET_DEV", "PYTEST_", "RUN_INTEGRATION"))}
    env["DEV_SPOOLMAN_URL"] = "http://192.168.1.29:07912"
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "--co", "-q", "-p", "no:cacheprovider",
         os.path.join("tests", "test_offline_mode.py")],
        cwd=HUB, env=env, capture_output=True, text=True, encoding="utf-8",
        errors="replace", timeout=300)
    out = proc.stdout + proc.stderr
    assert proc.returncode == pytest.ExitCode.USAGE_ERROR, (proc.returncode, out[-3000:])
    assert "prod Spoolman's" in out and "http://192.168.1.29:07912" in out, out[-3000:]
    assert "test_offline_mode.py::" not in out, "it collected: the refusal came too late"


# --- the page fixture's teardown ----------------------------------------------

class _TeardownPage:
    """Stands in for a Playwright page at conftest.page's teardown: logs what
    is done to it, and raises where a real one would (unroute_all on a closed
    page; close when the browser has gone away)."""

    def __init__(self, browser_gone=False):
        self.done = []
        self.closed = False
        self.browser_gone = browser_gone

    def on(self, event, handler):
        pass

    def close(self):
        self.done.append("close")
        if self.browser_gone:
            raise RuntimeError("Browser has been closed")
        self.closed = True     # Playwright's close of a closed page raises nothing

    def unroute_all(self, behavior=None):
        self.done.append(f"unroute_all({behavior})")
        if self.closed or self.browser_gone:
            raise RuntimeError("Target page, context or browser has been closed")


@pytest.mark.parametrize("screenshot,expected", [
    # Closed first: an un-routed live page's buffer poll or save could reach dev.
    ("off", ["close", "unroute_all(ignoreErrors)"]),
    # pytest-playwright takes its screenshots from the open page as the context closes.
    ("only-on-failure", ["unroute_all(ignoreErrors)"]),
    ("on", ["unroute_all(ignoreErrors)"]),
])
def test_the_page_fixture_closes_its_page_before_the_routes_come_off(screenshot, expected):
    import inspect
    import types
    page = _TeardownPage()
    opts = {"--screenshot": screenshot}
    request = types.SimpleNamespace(
        node=types.SimpleNamespace(),
        config=types.SimpleNamespace(getoption=lambda name, default=None: opts.get(name, default)))
    gen = inspect.unwrap(conftest.page)(page, request)
    assert next(gen) is page
    with pytest.raises(StopIteration):
        next(gen)          # the teardown, raising nothing
    assert page.done == expected


def test_the_page_fixture_takes_the_routes_off_when_the_close_fails():
    """A browser gone away: the teardown still marks the route handlers and
    raises nothing (a teardown error would turn a green test into an ERROR)."""
    import inspect
    import types
    page = _TeardownPage(browser_gone=True)
    request = types.SimpleNamespace(
        node=types.SimpleNamespace(),
        config=types.SimpleNamespace(getoption=lambda name, default=None: default))
    gen = inspect.unwrap(conftest.page)(page, request)
    next(gen)
    with pytest.raises(StopIteration):
        next(gen)
    assert page.done[-1] == "unroute_all(ignoreErrors)", page.done


# --- a plugin that imported the backend first --------------------------------

@pytest.mark.parametrize("module,words", [
    ("locations_db", "so this run would read and migrate whatever data/locations.json"),
    # app's import has run the migrations and the prune before conftest loads.
    ("app", "may already have migrated whatever data/locations.json"),
])
def test_a_plugin_that_imported_the_backend_first_is_refused(tmp_path, module, words):
    """A -p plugin's top-level import runs before tests/conftest.py, so the
    backend would take the working directory's data/ (from inventory-hub/: dev's
    live file), and conftest refuses the run. When app came in too, its startup
    migrations have already run, and the refusal says the harm may be done.

    The plugin's own import is given a folder of its own (FCC_DATA_DIR in its
    env; conftest refuses whatever the variable says) and runs from a tmp
    working directory, so even this run migrates nothing of dev's. --co: no
    fixture runs either way."""
    plug = tmp_path / "plug"
    plug.mkdir()
    (plug / "fcc_early_plugin_45_9.py").write_text(f"import {module}\n", encoding="utf-8")
    own = tmp_path / "data-of-its-own"
    own.mkdir()
    (own / "locations.json").write_text("[]", encoding="utf-8")
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("FCC_", "RESET_DEV", "PYTEST_", "RUN_INTEGRATION"))}
    env["FCC_DATA_DIR"] = str(own)
    env["PYTHONPATH"] = os.pathsep.join([str(plug), HUB])
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "--co", "-q", "-p", "no:cacheprovider",
         "-p", "fcc_early_plugin_45_9", os.path.join(HUB, "tests", "test_offline_mode.py")],
        cwd=str(tmp_path), env=env, capture_output=True, text=True, encoding="utf-8",
        errors="replace", timeout=300)
    out = proc.stdout + proc.stderr
    assert proc.returncode != 0, (proc.returncode, out[-3000:])
    assert "was imported before tests/conftest.py could set FCC_DATA_DIR" in out, out[-3000:]
    assert words in out, out[-3000:]
    assert "test_offline_mode.py::" not in out, "it collected: the refusal came too late"


# --- .build_info --------------------------------------------------------------

def test_build_info_is_written_only_when_its_bytes_change(tmp_path, monkeypatch, capsys):
    """Every host `import app` (each test run, each round-trip bridge) rewrote it
    on dev's bind mount, the same bytes unless HEAD moved. Dev's dashboard
    renders never did: its container has no .git, so the helper writes nothing
    there. Run by hand (before a prod image build), it says which it did."""
    import _gen_build_info
    sha = {"v": "abcd1234"}
    monkeypatch.setattr(_gen_build_info, "find_git_dir", lambda start: str(tmp_path))
    monkeypatch.setattr(_gen_build_info, "resolve_head_sha", lambda git_dir: sha["v"])
    monkeypatch.setattr(_gen_build_info, "resolve_head_timestamp", lambda git_dir: 1700000000)
    out = tmp_path / ".build_info"
    assert _gen_build_info.update_build_info(str(out)) == "written"
    assert out.read_text(encoding="utf-8") == "abcd1234|1700000000\n"
    os.utime(out, (1_000_000_000, 1_000_000_000))
    assert _gen_build_info.update_build_info(str(out)) == "unchanged"
    assert _gen_build_info.write_build_info(str(out)) is True   # app.py's call: up to date is a success
    assert os.path.getmtime(out) == 1_000_000_000, "the same bytes were written again"
    sha["v"] = "ef567890"
    assert _gen_build_info.write_build_info(str(out)) is True
    assert out.read_text(encoding="utf-8") == "ef567890|1700000000\n"

    # The command line says what it did: 'wrote' only for a write.
    capsys.readouterr()
    assert _gen_build_info.main(str(out)) == 0
    said = capsys.readouterr().out
    assert "up to date" in said and "wrote" not in said, said
    sha["v"] = "0123abcd"
    assert _gen_build_info.main(str(out)) == 0
    said = capsys.readouterr().out
    assert said.startswith("wrote ") and "0123abcd|1700000000" in said, said
    monkeypatch.setattr(_gen_build_info, "find_git_dir", lambda start: None)
    assert _gen_build_info.update_build_info(str(out)) is None
    assert _gen_build_info.write_build_info(str(out)) is False
    assert _gen_build_info.main(str(out)) == 1
    assert "nothing written" in capsys.readouterr().err


def test_a_build_info_write_that_fails_says_so(tmp_path, monkeypatch, capsys):
    """Its own outcome, never the .git message: a failed write says it couldn't
    write the file and why (a write that fails after the open may have emptied
    it, so 'nothing written' could be false). app.py's call still gets False."""
    import _gen_build_info
    monkeypatch.setattr(_gen_build_info, "find_git_dir", lambda start: str(tmp_path))
    monkeypatch.setattr(_gen_build_info, "resolve_head_sha", lambda git_dir: "abcd1234")
    monkeypatch.setattr(_gen_build_info, "resolve_head_timestamp", lambda git_dir: 1700000000)
    out = tmp_path / "a-folder"
    out.mkdir()          # opening a folder to write fails on every OS
    capsys.readouterr()
    assert _gen_build_info.main(str(out)) == 1
    said = capsys.readouterr()
    assert said.err.startswith(f"couldn't write {out}: "), said
    assert ".git" not in said.err and said.out == "", said
    assert _gen_build_info.write_build_info(str(out)) is False
    with pytest.raises(OSError):
        _gen_build_info.update_build_info(str(out))
