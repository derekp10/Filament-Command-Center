"""Group 19.1 — hermetic unit coverage for reset_dev.py's restore-decision logic.

These tests exercise the PURE comparison helpers (`_values_equal`,
`_drifted_payload`) that decide which fields get PATCHed back to the seed.
They touch no network and no Spoolman — the network round-trips (capture,
PATCH, DELETE, docker restart) are validated by running the script against
the live dev backend, but the drift logic that gates every write is locked
down here so a regression can't silently start over- or under-writing.

Group 45.6 added: reset_dev.py's printer-login handling, its capture and
restore driven through an in-memory Spoolman (archived spools included, and
the stop when a local seed is missing), and refresh_dev_from_prod.py's guards
(prod read-only for HTTP and files, the dev marker, the swap's target checks).
Still no network: urlopen is a tripwire, and no UNC path is ever opened.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import shutil
import types
from pathlib import Path

import pytest

# reset_dev.py lives in setup-and-rebuild/ (a sibling of inventory-hub/),
# which isn't a package. Load it by path.
_RESET_DEV_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "setup-and-rebuild", "reset_dev.py")
)


@pytest.fixture(scope="module")
def reset_dev():
    if not os.path.exists(_RESET_DEV_PATH):
        pytest.skip(f"reset_dev.py not found at {_RESET_DEV_PATH}")
    spec = importlib.util.spec_from_file_location("reset_dev", _RESET_DEV_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# --- _values_equal --------------------------------------------------------

def test_values_equal_float_tolerance(reset_dev):
    # Spoolman serializes 1.24 with float noise; a sub-epsilon delta is NOT drift.
    assert reset_dev._values_equal(1.24, 1.2400000001)
    assert reset_dev._values_equal(1000.0, 1000)
    # A real change IS drift.
    assert not reset_dev._values_equal(1.24, 1.25)


def test_values_equal_strings_and_none(reset_dev):
    assert reset_dev._values_equal("PM-DB-3", "PM-DB-3")
    assert not reset_dev._values_equal("PM-DB-3", "")
    assert reset_dev._values_equal(None, None)
    assert not reset_dev._values_equal(None, "x")


def test_values_equal_dicts(reset_dev):
    assert reset_dev._values_equal({"a": "1"}, {"a": "1"})
    # None and {} treated as the empty dict (Spoolman returns {} for no extras).
    assert reset_dev._values_equal(None, {})
    assert not reset_dev._values_equal({"a": "1"}, {"a": "2"})


# --- _drifted_payload -----------------------------------------------------

def test_no_drift_returns_empty_payload(reset_dev):
    """A live spool identical to the seed yields no PATCH (idempotency)."""
    seed = {
        "id": 1, "location": "PM-DB-3", "archived": False,
        "initial_weight": 1000.0, "spool_weight": 0.0, "used_weight": 150.0,
        "lot_nr": None, "comment": "[Fan: On]",
        "extra": {"container_slot": '"\\"\\"\\""', "needs_label_print": "true"},
    }
    live = dict(seed)
    assert reset_dev._drifted_payload("spool", seed, live) == {}


def test_location_drift_is_restored(reset_dev):
    """The headline contamination: a sweep moved the spool's location."""
    seed = {"id": 1, "location": "PM-DB-3", "archived": False, "extra": {}}
    live = {"id": 1, "location": "SOME-TEST-LOC", "archived": False, "extra": {}}
    payload = reset_dev._drifted_payload("spool", seed, live)
    assert payload == {"location": "PM-DB-3"}


def test_archived_and_extra_drift_restored_together(reset_dev):
    seed = {
        "id": 1, "location": "PM-DB-3", "archived": False,
        "extra": {"container_slot": '""', "needs_label_print": "false"},
    }
    live = {
        "id": 1, "location": "PM-DB-3", "archived": True,
        "extra": {"container_slot": '"XL-1"', "needs_label_print": "true"},
    }
    payload = reset_dev._drifted_payload("spool", seed, live)
    assert payload["archived"] is False
    # Whole-extra overwrite: the seed's whole dict goes back.
    assert payload["extra"] == seed["extra"]
    assert "location" not in payload  # unchanged → not sent


def test_extra_overwrite_drops_sweep_added_keys(reset_dev):
    """If a sweep ADDED an extra key, the stray key must be gone after the restore.
    Spoolman 0.26+ merges a PATCH's extra key by key, so leaving it out of the
    seed's (smaller) dict KEPT it: it is sent as null, which drops it (2026-10-21;
    an older Spoolman replaced a vendor's whole extra, and gets no null)."""
    seed = {"id": 9, "extra": {"website": '""'}}
    live = {"id": 9, "extra": {"website": '""', "junk_key": '"oops"'}}
    payload = reset_dev._drifted_payload("vendor", seed, live)
    assert payload == {"extra": {"website": '""', "junk_key": None}}


def test_filament_attributes_extra_restored(reset_dev):
    """L319/L58 contamination: filament_attributes got rewritten on the
    filament's extra. Restore overwrites the whole extra back to seed."""
    seed = {"id": 3, "material": "PLA",
            "extra": {"filament_attributes": '["Silk"]', "sample_printed": "true"}}
    live = {"id": 3, "material": "PLA",
            "extra": {"filament_attributes": '["Silk","Wood"]', "sample_printed": "true"}}
    payload = reset_dev._drifted_payload("filament", seed, live)
    assert payload == {"extra": {"filament_attributes": '["Silk"]', "sample_printed": "true"}}


def test_weight_triple_drift_restored(reset_dev):
    """Weigh-out / auto-deduct tests move used_weight; restore puts it back."""
    seed = {"id": 1, "location": "X", "archived": False,
            "initial_weight": 1000.0, "spool_weight": 0.0, "used_weight": 150.0,
            "extra": {}}
    live = dict(seed, used_weight=812.5)
    payload = reset_dev._drifted_payload("spool", seed, live)
    assert payload == {"used_weight": 150.0}


def test_only_restorable_fields_considered(reset_dev):
    """A drift in a field NOT on the restore list (e.g. remaining_weight, a
    derived read-only field) must not produce a PATCH."""
    seed = {"id": 1, "location": "X", "archived": False, "extra": {},
            "remaining_weight": 850.0}
    live = {"id": 1, "location": "X", "archived": False, "extra": {},
            "remaining_weight": 123.0}
    assert reset_dev._drifted_payload("spool", seed, live) == {}


def test_restore_field_sets_are_sane(reset_dev):
    """Guard the field config: extra must be restorable on every entity (it's
    the primary contamination vector), and spool must restore location+archived."""
    rf = reset_dev.RESTORE_FIELDS
    for entity in ("vendor", "filament", "spool"):
        assert "extra" in rf[entity], f"{entity} must restore extra"
    assert "location" in rf["spool"]
    assert "archived" in rf["spool"]


# --- printer logins and the locations seed (Group 45.6) --------------------
#
# The locations seed is a file that gets copied around (it was committed and pushed
# until 2026-11-13; it is local since), and dev's locations.json holds a
# PrusaLink IP and API key on each Printer row (printer_creds). --capture copied
# the live file verbatim, logins included, and a restore overwrote the live file
# with the seed, wiping dev's logins. Every value below is made up.

LOGIN = {"ip_address": "10.9.8.7", "api_key": "made-up-key-0001"}
LIVE_ROWS = [
    {"LocationID": "SHELF-1", "Type": "Room", "Name": "Shelf one", "parent_id": None},
    {"LocationID": "PRINTER-1", "Type": "Printer", "Name": "Printer one", "parent_id": "SHELF-1",
     "printer_creds": LOGIN, "toolheads": [{"location_id": "HEAD-1", "position": 0}]},
    {"LocationID": "HEAD-1", "Type": "Tool Head", "Name": "Head one", "Max Spools": "1",
     "parent_id": "PRINTER-1"},
]


def _without_login(rows):
    return [{k: v for k, v in r.items() if k != "printer_creds"} for r in rows]


def _write_rows(path, rows):
    path.write_text(json.dumps(rows, indent=4), encoding="utf-8")


@pytest.fixture
def seed_files(reset_dev, tmp_path, monkeypatch):
    """reset_dev's live locations.json and seeds folder, moved to tmp_path."""
    live = tmp_path / "data" / "locations.json"
    live.parent.mkdir()
    seeds = tmp_path / "seeds"
    seeds.mkdir()
    monkeypatch.setattr(reset_dev, "LIVE_LOCATIONS", str(live))
    monkeypatch.setattr(reset_dev, "SEEDS_DIR", str(seeds))
    monkeypatch.setattr(reset_dev, "LOCATIONS_SEED", str(seeds / "locations-seed.json"))
    monkeypatch.setattr(reset_dev, "SPOOLMAN_SEED", str(seeds / "spoolman-dev-seed.json"))
    return live, seeds / "locations-seed.json"


def test_capture_never_writes_a_printer_login_into_the_seed(reset_dev, seed_files, monkeypatch, capsys):
    live, seed = seed_files
    _write_rows(live, LIVE_ROWS)
    monkeypatch.setattr(reset_dev, "_check_spoolman_reachable", lambda: None)
    monkeypatch.setattr(reset_dev, "_get", lambda path: [])
    reset_dev.capture()
    text = seed.read_text(encoding="utf-8")
    assert "printer_creds" not in text
    assert LOGIN["api_key"] not in text and LOGIN["ip_address"] not in text
    assert json.loads(text) == _without_login(LIVE_ROWS), "everything but the login is kept"
    out = capsys.readouterr().out
    assert LOGIN["api_key"] not in out and LOGIN["ip_address"] not in out
    assert "PRINTER-1" in out, "the capture names the row it left a login out of"


def test_restore_keeps_the_live_files_printer_logins_by_location_id(reset_dev, seed_files, capsys):
    live, seed = seed_files
    old_seed_login = {"ip_address": "10.0.0.1", "api_key": "made-up-seed-key"}
    seed_rows = [
        {"LocationID": "SHELF-1", "Type": "Room", "Name": "Shelf one (seed)", "parent_id": None},
        {"LocationID": "printer-1 ", "Type": "Printer", "Name": "Printer one", "parent_id": "SHELF-1",
         "toolheads": [{"location_id": "HEAD-1", "position": 0}]},
        {"LocationID": "PRINTER-2", "Type": "Printer", "Name": "Printer two", "parent_id": None,
         "printer_creds": old_seed_login},
    ]
    _write_rows(seed, seed_rows)
    _write_rows(live, LIVE_ROWS)
    reset_dev.restore_locations(dry_run=False)
    rows = {r["LocationID"].strip().upper(): r for r in json.loads(live.read_text(encoding="utf-8"))}
    assert set(rows) == {"SHELF-1", "PRINTER-1", "PRINTER-2"}, "the seed decides the rows"
    assert rows["SHELF-1"]["Name"] == "Shelf one (seed)", "the seed's values are restored"
    assert rows["PRINTER-1"]["printer_creds"] == LOGIN, "dev's login is kept, matched by LocationID"
    assert "printer_creds" not in rows["PRINTER-2"], "a seed never brings a login back"
    out = capsys.readouterr().out
    for value in list(LOGIN.values()) + list(old_seed_login.values()):
        assert value not in out


def test_a_login_alone_is_no_drift(reset_dev, seed_files, capsys):
    live, seed = seed_files
    _write_rows(seed, _without_login(LIVE_ROWS))
    _write_rows(live, LIVE_ROWS)
    before = live.read_bytes()
    reset_dev.restore_locations(dry_run=False)
    assert live.read_bytes() == before, "the restore rewrote the file (and its login) for nothing"
    assert "already matches seed" in capsys.readouterr().out


def test_a_dry_run_restore_writes_nothing_and_names_the_kept_logins(reset_dev, seed_files, capsys):
    live, seed = seed_files
    seed_rows = _without_login(LIVE_ROWS)
    seed_rows[0] = dict(seed_rows[0], Name="Shelf one (seed)")
    _write_rows(seed, seed_rows)
    _write_rows(live, LIVE_ROWS)
    before = live.read_bytes()
    reset_dev.restore_locations(dry_run=True)
    assert live.read_bytes() == before
    out = capsys.readouterr().out
    assert "WOULD restore" in out and "PRINTER-1" in out
    assert LOGIN["api_key"] not in out and LOGIN["ip_address"] not in out


# --- refresh_dev_from_prod.py: prod stays read-only, in code (Group 45.6) ---
#
# Its sibling script copies prod's data into dev. Its guards are the promise that
# it can't write to prod, so they are pinned here, hermetically: no request is
# ever sent (urlopen is replaced by a tripwire) and no file outside tmp_path is
# written.

_REFRESH_PATH = os.path.join(os.path.dirname(_RESET_DEV_PATH), "refresh_dev_from_prod.py")


def _load_refresh(monkeypatch, tmp_path):
    """A fresh copy of the script (it reads its env overrides at import), with urlopen a tripwire
    and its stage and data folders in tmp_path."""
    if not os.path.exists(_REFRESH_PATH):
        pytest.skip(f"refresh_dev_from_prod.py not found at {_REFRESH_PATH}")
    spec = importlib.util.spec_from_file_location("refresh_dev_from_prod", _REFRESH_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    def tripwire(*args, **kwargs):
        raise AssertionError("refresh_dev_from_prod sent a real request in a unit test")

    monkeypatch.setattr(mod.urllib.request, "urlopen", tripwire)
    monkeypatch.setattr(mod, "STAGE_DIR", str(tmp_path / "stage"))
    monkeypatch.setattr(mod, "DEV_DATA_DIR", str(tmp_path / "data"))
    return mod


@pytest.fixture
def refresh(monkeypatch, tmp_path):
    return _load_refresh(monkeypatch, tmp_path)


@pytest.mark.parametrize("method", ["POST", "PATCH", "PUT", "DELETE"])
@pytest.mark.parametrize("url", [
    "http://192.168.1.29:7912/api/v1/spool/1",      # prod Spoolman by address
    "http://TRUENAS:7912/api/v1/spool/1",           # ...and by host name
])
def test_refresh_never_sends_a_write_to_prod_spoolman(refresh, monkeypatch, method, url):
    # Even with the prod address overridden to something else, the known one is refused.
    monkeypatch.setattr(refresh, "PROD_SPOOLMAN_URL", "http://10.0.0.99:7912")
    with pytest.raises(refresh.Refused, match="read-only"):
        refresh.http(method, url, {"location": "x"})


def test_refresh_talks_only_to_its_three_addresses(refresh):
    with pytest.raises(refresh.Refused, match="not dev Spoolman"):
        refresh.http("GET", "http://example.invalid/api")
    with pytest.raises(refresh.Refused, match="only reads dev FCC"):
        refresh.http("POST", refresh.DEV_FCC_URL + "/api/locations", {})


@pytest.mark.parametrize("path", [
    r"\\TRUENAS\App_Data\Spoolman\SPOOLMAN_DIR_DATA\spoolman.db",
    r"\\truenas\app_data\spoolman\spoolman_dir_data\spoolman.db",
    "//TRUENAS/App_Data/Spoolman/SPOOLMAN_DIR_DATA/spoolman.db",
    r"\\192.168.1.29\App_Data\InventoryHub\inventory-hub\data\locations.json",
    r"\\ANOTHER-NAME\App_Data\InventoryHub\x.json",
])
def test_refresh_never_writes_on_prods_share(refresh, path):
    assert refresh.is_prod_path(path)
    with pytest.raises(refresh.Refused, match="prod's share"):
        refresh._guard_write(path)


def test_refresh_writes_only_its_stage_folder_dev_data_and_devs_database(refresh, tmp_path, monkeypatch):
    monkeypatch.setattr(refresh, "DEV_SPOOLMAN_DB", r"\\TRUENAS\App_Data\Spoolman_Dev\spoolman.db")
    assert not refresh.is_prod_path(r"\\TRUENAS\App_Data\Spoolman_Dev\spoolman.db"), \
        "Spoolman_Dev only shares a prefix with prod's Spoolman folder"
    refresh._guard_write(r"\\TRUENAS\App_Data\Spoolman_Dev\spoolman.db")
    refresh._guard_write(str(tmp_path / "stage" / "report.json"))
    refresh._guard_write(str(tmp_path / "data" / "locations.json"))
    for elsewhere in (r"\\TRUENAS\App_Data\Spoolman_Dev\backups\x.db", str(tmp_path / "other.json")):
        with pytest.raises(refresh.Refused, match="outside"):
            refresh._guard_write(elsewhere)
    monkeypatch.setattr(refresh, "DEV_SPOOLMAN_DB", r"\\TRUENAS\App_Data\Spoolman\SPOOLMAN_DIR_DATA\spoolman.db")
    with pytest.raises(refresh.Refused):
        refresh._guard_write(r"\\TRUENAS\App_Data\Spoolman\SPOOLMAN_DIR_DATA\spoolman.db")


def _spoolman_db(path, spools, filaments=3, vendors=2):
    import sqlite3
    con = sqlite3.connect(path)
    for table, n in (("spool", spools), ("filament", filaments), ("vendor", vendors)):
        con.execute(f"CREATE TABLE {table} (id INTEGER PRIMARY KEY)")
        con.executemany(f"INSERT INTO {table} (id) VALUES (?)", [(i,) for i in range(1, n + 1)])
    con.commit()
    con.close()


def test_the_swap_proves_its_target_is_devs_database_first(refresh, tmp_path, monkeypatch):
    target = tmp_path / "share" / "spoolman.db"
    target.parent.mkdir()
    _spoolman_db(str(target), spools=5)
    monkeypatch.setattr(refresh, "DEV_SPOOLMAN_DB", str(target))
    snapshot = {"vendor": {"count": 2, "max_id": 2}, "filament": {"count": 3, "max_id": 3},
                "spool": {"count": 5, "max_id": 5}}
    ok, ident = refresh.check_target_identity(snapshot)
    assert ok and ident == snapshot
    other = dict(snapshot, spool={"count": 7, "max_id": 9})      # prod's numbers, say
    ok, ident = refresh.check_target_identity(other)
    assert not ok, "a file whose counts differ from dev's snapshot is not dev's database"
    assert not os.listdir(tmp_path / "stage"), "the local copy it opened is removed"


def test_the_swap_waits_for_every_printer_to_be_idle(refresh, tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    latch = data / "print_tracker_latch.json"
    latch.write_text(json.dumps({"Printer one": {"state": "IDLE"}, "Printer two": {"state": "IDLE"}}),
                     encoding="utf-8")
    assert refresh.latch_state()[0] is True
    latch.write_text(json.dumps({"Printer one": {"state": "PRINTING", "job_id": "7"},
                                 "Printer two": {"state": "IDLE"}}), encoding="utf-8")
    idle, why = refresh.latch_state()
    assert idle is False and "Printer one=PRINTING" in why
    latch.write_text("{not json", encoding="utf-8")
    assert refresh.latch_state()[0] is False, "a latch it can't read is not idle"


def test_the_refresh_builds_devs_locations_from_prods_rows(refresh):
    prod_login = {"ip_address": "10.1.1.1", "api_key": "made-up-prod-key"}
    prod = [
        {"LocationID": "SHELF-1", "Type": "Room", "Name": "Shelf one", "parent_id": None},
        {"LocationID": "", "Type": "Virtual Room", "Name": "Unknown place", "parent_id": None},
        {"LocationID": "PRINTER-1", "Type": "Printer", "Name": "Printer one", "printer_creds": prod_login,
         "toolheads": [], "parent_id": "SHELF-1"},
        {"LocationID": "PRINTER-2", "Type": "Printer", "Name": "Printer two", "printer_creds": prod_login,
         "toolheads": [], "parent_id": None},
        {"LocationID": "DRYBOX-1", "Type": "Dryer Box", "Name": "Box", "Max Spools": "1", "parent_id": None,
         "extra": {"slot_targets": {"1": "HEAD-1"}, "slot_order": "ltr"}},
    ]
    dev = [
        {"LocationID": "printer-1", "Type": "Printer", "Name": "Printer one", "printer_creds": LOGIN},
        {"LocationID": "CART-T", "Type": "Cart", "Name": "Test cart", "parent_id": "SHELF-1"},
    ]
    rows, rep = refresh.build_dev_locations(prod, dev, {"DRYBOX-1": {}}, ("CART-T",))
    assert [r["LocationID"] for r in rows] == ["SHELF-1", "PRINTER-1", "PRINTER-2", "DRYBOX-1", "CART-T"], \
        "prod's rows in prod's order, the blank one dropped, dev's test cart after them"
    assert rep["dropped_blank"] == [{"Type": "Virtual Room", "Name": "Unknown place", "parent_id": None}]
    by = {r["LocationID"]: r for r in rows}
    assert by["PRINTER-1"]["printer_creds"] == LOGIN, "dev's login, matched by LocationID"
    assert "printer_creds" not in by["PRINTER-2"], "never prod's login"
    assert rep["logins_kept"] == [{"LocationID": "PRINTER-1", "prod_differs": True}]
    assert rep["prod_logins_not_taken"] == ["PRINTER-2"]
    assert by["DRYBOX-1"]["extra"] == {"slot_targets": {}, "slot_order": "ltr"}, \
        "the test box is at its baseline, its other extra keys kept"
    assert rep["bindings_replaced"] == [{"box": "DRYBOX-1", "prod_slot_targets": {"1": "HEAD-1"}}]
    assert prod[4]["extra"]["slot_targets"] == {"1": "HEAD-1"}, "prod's rows are never changed in place"
    assert "made-up-prod-key" not in json.dumps(rows)


# --- refresh_dev_from_prod.py, round 2: every spelling, the overrides, the share allowlist ---
#
# The 2026-11-13 check of round 1 found the path guard read a few valid spellings of prod's share as
# somewhere else (\\?\UNC\, \\.\UNC\, //?/UNC/, a trailing dot), and nothing pinned the part that
# honours the FCC_REFRESH_PROD_* overrides. Every path here is made up or on prod's share by name;
# none is ever opened (UNC paths are never resolved, so nothing reaches the network).

def test_refresh_honours_the_prod_folder_overrides(monkeypatch, tmp_path):
    """The folders FCC_REFRESH_PROD_SPOOLMAN_DB and FCC_REFRESH_PROD_FCC_DATA_DIR name are prod's,
    wherever they are (here, on this PC and on a share outside App_Data)."""
    db_dir, data_dir = tmp_path / "prod-db", tmp_path / "prod-fcc-data"
    monkeypatch.setenv("FCC_REFRESH_PROD_SPOOLMAN_DB", str(db_dir / "spoolman.db"))
    monkeypatch.setenv("FCC_REFRESH_PROD_FCC_DATA_DIR", str(data_dir))
    mod = _load_refresh(monkeypatch, tmp_path)
    assert mod.PROD_FCC_DATA_DIR == str(data_dir), "the override is read at import"
    for path in (db_dir / "spoolman.db", db_dir / "other.db", data_dir / "locations.json",
                 data_dir / "sub" / "x.json"):
        assert mod.is_prod_path(str(path)), path
    assert not mod.is_prod_path(str(tmp_path / "prod-fcc-data-old" / "x.json")), \
        "a sibling folder that only shares a prefix isn't prod's"
    monkeypatch.setattr(mod, "DEV_DATA_DIR", str(data_dir))       # even named as dev's own data folder
    with pytest.raises(mod.Refused, match="prod's share"):
        mod._guard_write(str(data_dir / "locations.json"))
    monkeypatch.setattr(mod, "STAGE_DIR", str(db_dir / "stage"))  # or as a stage folder inside it
    with pytest.raises(mod.Refused, match="prod's share"):
        mod._guard_write(str(db_dir / "stage" / "stage-report.json"))
    assert mod.main(["checklist"]) == 2, "main() refuses a stage or data folder inside an override"
    monkeypatch.setattr(mod, "PROD_FCC_DATA_DIR", r"\\NAS2\Data\FCC")   # a share outside App_Data
    assert mod.is_prod_path(r"\\NAS2\Data\FCC\locations.json")
    assert not mod.is_prod_path(r"\\NAS2\Data\FCC-old\locations.json")


def test_refresh_honours_the_overrides_in_any_spelling(refresh, monkeypatch):
    monkeypatch.setattr(refresh, "PROD_FCC_DATA_DIR", r"\\?\UNC\NAS2\Data\FCC")
    monkeypatch.setattr(refresh, "PROD_SPOOLMAN_DB", "//NAS2/Data/Spoolman./db/spoolman.db")
    for path in (r"\\NAS2\Data\FCC\locations.json", "//nas2/data/fcc/sub/x.json", r"\\NAS2\Data\FCC.\locations.json",
                 r"\\nas2\DATA\spoolman\db\spoolman.db", r"\\?\UNC\NAS2\Data\Spoolman\db\other.db"):
        assert refresh.is_prod_path(path), path
        with pytest.raises(refresh.Refused, match="prod's share"):
            refresh._guard_write(path)
    assert not refresh.is_prod_path(r"\\NAS2\Data\FCC-old\locations.json")


@pytest.mark.parametrize("path", [
    r"\\?\UNC\TRUENAS\App_Data\Spoolman\SPOOLMAN_DIR_DATA\spoolman.db",
    "//?/UNC/TRUENAS/App_Data/Spoolman/SPOOLMAN_DIR_DATA/spoolman.db",
    r"\\.\UNC\TRUENAS\App_Data\InventoryHub\inventory-hub\data\locations.json",
    r"\??\UNC\TRUENAS\App_Data\Spoolman\SPOOLMAN_DIR_DATA\spoolman.db",
    r"\\?\GLOBALROOT\Device\Mup\TRUENAS\App_Data\Spoolman\SPOOLMAN_DIR_DATA\spoolman.db",
    r"\\TRUENAS\App_Data\Spoolman.\SPOOLMAN_DIR_DATA\spoolman.db",
    r"\\TRUENAS.\App_Data \Spoolman. \SPOOLMAN_DIR_DATA\spoolman.db",
    r"\\?\UNC\ANOTHER-NAME\App_Data\InventoryHub\x.json",
])
def test_refresh_reads_every_spelling_of_prods_share(refresh, path):
    assert refresh.is_prod_path(path)
    with pytest.raises(refresh.Refused, match="prod's share"):
        refresh._guard_write(path)


def test_on_a_network_share_it_writes_only_devs_database_and_marker(refresh, monkeypatch):
    dev_db = r"\\TRUENAS\App_Data\Spoolman_Dev\spoolman.db"
    monkeypatch.setattr(refresh, "DEV_SPOOLMAN_DB", dev_db)
    for allowed in (dev_db, r"\\?\UNC\truenas\app_data\spoolman_dev\SPOOLMAN.DB",
                    "//TRUENAS/App_Data/Spoolman_Dev/spoolman.db",
                    r"\\TRUENAS\App_Data\Spoolman_Dev\FCC_DEV_SPOOLMAN.marker"):
        refresh._guard_write(allowed)
    for refused in (r"\\TRUENAS\App_Data\Spoolman_Dev\spoolman.db-journal",
                    r"\\TRUENAS\App_Data\Spoolman_Dev\backups\spoolman.db",
                    r"\\TRUENAS\App_Data\notes.txt",
                    r"\\TRUENAS\Spoolman\SPOOLMAN_DIR_DATA\spoolman.db",   # another share name for a dataset
                    r"\\NAS2\scratch\x.json"):
        with pytest.raises(refresh.Refused, match="outside"):
            refresh._guard_write(refused)
    monkeypatch.setattr(refresh, "STAGE_DIR", r"\\NAS2\scratch\stage")  # a stage folder on a share
    with pytest.raises(refresh.Refused, match="outside"):
        refresh._guard_write(r"\\NAS2\scratch\stage\stage-report.json")


@pytest.mark.parametrize("stage_dir", [
    r"\\?\UNC\TRUENAS\App_Data\InventoryHub\x-stage",
    r"\\TRUENAS\App_Data\InventoryHub.\x-stage",
    r"\\NAS2\scratch\stage",
])
def test_main_refuses_a_stage_folder_on_prods_share_or_off_this_pc(refresh, stage_dir, capsys):
    assert refresh.main(["checklist", "--stage-dir", stage_dir]) == 2
    assert "REFUSED" in capsys.readouterr().out


# --- the dev marker and the swap's target guards (round 2) -------------------------------------
#
# Round 1's identity guard compared the target's counts and max ids with dev's: after a refresh
# dev's and prod's are equal, so it couldn't tell the two files apart. The swap now needs dev's
# marker in the target's folder (none in prod's), and refuses prod's own file (samefile) and prod's
# live bytes (sha256). Each scene is hermetic: two folders in tmp_path stand for the two shares.

MARKER = "FCC_DEV_SPOOLMAN.marker"
MARKER_FIRST_LINE = "FCC_DEV_SPOOLMAN marker v1"   # the marker on dev's share starts with this


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _swap_scene(refresh, tmp_path, monkeypatch, *, marker=True, prod_marker=False, target="own",
                snapshot=True, dev_up=False):
    stage = tmp_path / "stage"
    stage.mkdir(exist_ok=True)
    (tmp_path / "data").mkdir(exist_ok=True)
    devshare, prodshare = tmp_path / "devshare", tmp_path / "prodshare"
    devshare.mkdir()
    prodshare.mkdir()
    prod = prodshare / "spoolman.db"
    _spoolman_db(str(prod), spools=9, filaments=4)
    staged = stage / "prod-spoolman.db"
    _spoolman_db(str(staged), spools=7, filaments=4)
    db = devshare / "spoolman.db"
    if target == "own":
        _spoolman_db(str(db), spools=5)
    elif target == "prod-bytes":
        shutil.copyfile(prod, db)
    elif target == "staged-bytes":
        shutil.copyfile(staged, db)
    elif target == "prod-link":
        try:
            os.link(prod, db)                   # prod's own file under another name
        except OSError as exc:
            pytest.skip(f"no hard links here: {exc}")
    report = {"prod_db": {"sha256": _sha(staged)}}
    if snapshot:
        report["dev_identity"] = refresh.identity_from_db(str(db))
    (stage / "stage-report.json").write_text(json.dumps(report), encoding="utf-8")
    if marker:
        (devshare / MARKER).write_text(MARKER_FIRST_LINE + "\nmade-up test marker\n", encoding="utf-8")
    if prod_marker:
        (prodshare / MARKER).write_text(MARKER_FIRST_LINE + "\n", encoding="utf-8")
    monkeypatch.setattr(refresh, "DEV_SPOOLMAN_DB", str(db))
    monkeypatch.setattr(refresh, "PROD_SPOOLMAN_DB", str(prod))
    monkeypatch.setattr(refresh, "spoolman_answers",
                        lambda base, timeout=5: (base != refresh.DEV_SPOOLMAN_URL or dev_up, "stub"))
    return types.SimpleNamespace(stage=stage, db=db, prod=prod, staged=staged, devshare=devshare,
                                 prodshare=prodshare)


def test_the_swap_needs_devs_marker_in_the_targets_folder(refresh, tmp_path, monkeypatch, capsys):
    scene = _swap_scene(refresh, tmp_path, monkeypatch, marker=False)
    before = scene.db.read_bytes()
    assert refresh.main(["swap", "--apply"]) == 2
    assert scene.db.read_bytes() == before, "nothing overwritten"
    assert not (scene.stage / "dev-spoolman-before.db").exists()
    assert "no dev marker" in capsys.readouterr().out
    (scene.devshare / MARKER).write_text(MARKER_FIRST_LINE + "\nmade-up test marker\n", encoding="utf-8")
    assert refresh.main(["swap", "--apply"]) == 0, "with the marker every guard passes"
    out = capsys.readouterr().out
    assert "matches dev's snapshot" in out and "SAME: it is dev's database" not in out
    assert _sha(scene.db) == _sha(scene.staged), "the target is now the staged copy"
    assert (scene.stage / "dev-spoolman-before.db").read_bytes() == before, "and the old target is backed up"
    assert not (scene.prodshare / MARKER).exists()


def test_the_swap_refuses_while_prods_folder_holds_a_marker(refresh, tmp_path, monkeypatch, capsys):
    scene = _swap_scene(refresh, tmp_path, monkeypatch, prod_marker=True)
    before = scene.db.read_bytes()
    assert refresh.main(["swap", "--apply"]) == 2
    assert scene.db.read_bytes() == before
    assert "prod's database folder holds a dev marker" in capsys.readouterr().out


@pytest.mark.parametrize("target, why", [
    ("prod-bytes", "exactly prod's live database bytes"),
    ("staged-bytes", "already is the staged copy"),
])
def test_the_swap_refuses_a_target_with_nothing_to_swap(refresh, tmp_path, monkeypatch, capsys, target, why):
    scene = _swap_scene(refresh, tmp_path, monkeypatch, target=target)
    before = scene.db.read_bytes()
    assert refresh.main(["swap", "--apply"]) == 2
    assert scene.db.read_bytes() == before
    assert why in capsys.readouterr().out


def test_the_swap_refuses_prods_own_file_under_another_name(refresh, tmp_path, monkeypatch, capsys):
    scene = _swap_scene(refresh, tmp_path, monkeypatch, target="prod-link")
    before = _sha(scene.prod)
    assert refresh.main(["swap", "--apply"]) == 2
    assert _sha(scene.prod) == before, "prod's file is untouched"
    assert "IS prod's database file" in capsys.readouterr().out


def test_the_swap_refuses_when_it_cant_tell_whether_the_target_is_prods(refresh, tmp_path, monkeypatch, capsys):
    scene = _swap_scene(refresh, tmp_path, monkeypatch)
    monkeypatch.setattr(refresh, "same_file", lambda a, b: (None, "made-up: no file ids"))
    before = scene.db.read_bytes()
    assert refresh.main(["swap", "--apply"]) == 2
    assert scene.db.read_bytes() == before
    assert "couldn't tell whether the target is prod's" in capsys.readouterr().out


def test_samefile_cant_tell_on_a_filesystem_with_no_file_ids(refresh, tmp_path, monkeypatch):
    a, b = tmp_path / "a.db", tmp_path / "b.db"
    a.write_bytes(b"a")
    b.write_bytes(b"b")
    assert refresh.same_file(str(a), str(b)) == (False, None)
    assert refresh.same_file(str(a), str(a)) == (True, None)
    real_stat = os.stat

    def no_ids(path, *args, **kwargs):
        st = real_stat(path, *args, **kwargs)
        return os.stat_result((st.st_mode, 0, st.st_dev, st.st_nlink, st.st_uid, st.st_gid, st.st_size,
                               int(st.st_atime), int(st.st_mtime), int(st.st_ctime)))

    monkeypatch.setattr(refresh.os, "stat", no_ids)
    same, why = refresh.same_file(str(a), str(b))
    assert same is None and "file ids" in why, "st_ino 0 everywhere would make samefile say True for any two"


def test_the_swap_never_reads_devs_api_for_its_identity(refresh, tmp_path, monkeypatch, capsys):
    """No stage snapshot: refused, even in a dry run with dev up. Round 1 read dev's API instead,
    which is served from the very file being checked, so its match proved nothing."""
    _swap_scene(refresh, tmp_path, monkeypatch, snapshot=False, dev_up=True)
    assert refresh.main(["swap"]) == 2           # urlopen is a tripwire: a read of dev's API raises
    assert "no dev identity snapshot" in capsys.readouterr().out


def test_init_marker_needs_apply_and_the_flag(refresh, tmp_path, monkeypatch, capsys):
    devshare, prodshare = tmp_path / "devshare", tmp_path / "prodshare"
    devshare.mkdir()
    prodshare.mkdir()
    _spoolman_db(str(devshare / "spoolman.db"), spools=5)
    _spoolman_db(str(prodshare / "spoolman.db"), spools=9)
    monkeypatch.setattr(refresh, "DEV_SPOOLMAN_DB", str(devshare / "spoolman.db"))
    monkeypatch.setattr(refresh, "PROD_SPOOLMAN_DB", str(prodshare / "spoolman.db"))
    marker = devshare / MARKER
    assert refresh.main(["init-marker"]) == 0
    assert not marker.exists(), "a dry run writes nothing"
    assert refresh.main(["init-marker", "--apply"]) == 2
    assert not marker.exists(), "--apply alone isn't enough"
    assert "--i-checked-this-is-dev" in capsys.readouterr().out
    assert refresh.main(["init-marker", "--apply", "--i-checked-this-is-dev", "--note", "made-up proof"]) == 0
    text = marker.read_text(encoding="utf-8")
    assert text.startswith(MARKER_FIRST_LINE) and "made-up proof" in text
    before = marker.read_bytes()
    assert refresh.main(["init-marker", "--apply", "--i-checked-this-is-dev"]) == 0
    assert marker.read_bytes() == before, "a second run leaves the marker as it is"
    assert not (prodshare / MARKER).exists()


def test_init_marker_never_writes_on_prods_side(refresh, tmp_path, monkeypatch, capsys):
    prodshare = tmp_path / "prodshare"
    prodshare.mkdir()
    _spoolman_db(str(prodshare / "spoolman.db"), spools=9)
    monkeypatch.setattr(refresh, "PROD_SPOOLMAN_DB", str(prodshare / "spoolman.db"))
    monkeypatch.setattr(refresh, "DEV_SPOOLMAN_DB", str(prodshare / "spoolman.db"))   # an override gone wrong
    assert refresh.main(["init-marker", "--apply", "--i-checked-this-is-dev"]) == 2
    assert not (prodshare / MARKER).exists()
    for spelling in (r"\\?\UNC\TRUENAS\App_Data\Spoolman\SPOOLMAN_DIR_DATA\spoolman.db",
                     r"\\TRUENAS\App_Data\Spoolman.\SPOOLMAN_DIR_DATA\spoolman.db"):
        monkeypatch.setattr(refresh, "DEV_SPOOLMAN_DB", spelling)     # refused before the share is touched
        assert refresh.main(["init-marker", "--apply", "--i-checked-this-is-dev"]) == 2
    devshare = tmp_path / "devshare"
    devshare.mkdir()
    _spoolman_db(str(devshare / "spoolman.db"), spools=5)
    monkeypatch.setattr(refresh, "DEV_SPOOLMAN_DB", str(devshare / "spoolman.db"))
    (prodshare / MARKER).write_text(MARKER_FIRST_LINE + "\n", encoding="utf-8")
    capsys.readouterr()
    assert refresh.main(["init-marker", "--apply", "--i-checked-this-is-dev"]) == 2, \
        "prod's folder holding a marker means the two may be one folder"
    assert not (devshare / MARKER).exists()
    assert "prod's database folder already holds a dev marker" in capsys.readouterr().out
    (devshare / MARKER).write_text(MARKER_FIRST_LINE + "\n", encoding="utf-8")   # dev marked too
    assert refresh.main(["init-marker"]) == 2, "a marker on both sides is a problem, said even when dev's is there"
    assert "prod's database folder already holds a dev marker" in capsys.readouterr().out


def test_the_count_gives_the_rule_as_filed_and_in_stock(refresh):
    """45.7 as filed counts every spool with a trail that isn't on a head, archived ones too; the
    in-stock number is the narrower one. Round 1's report gave only the narrower number."""
    rows = [{"LocationID": "PRINTER-1", "Type": "Printer", "toolheads": [{"location_id": "HEAD-1", "position": 0}]},
            {"LocationID": "HEAD-1", "Type": "Tool Head", "Max Spools": "1"},
            {"LocationID": "BOX-1", "Type": "Dryer Box", "Max Spools": "4"},
            {"LocationID": "SHELF-1", "Type": "Shelf"}]

    def spool(sid, loc, archived=False, src="", slot=""):
        extra = {}
        if src:
            extra["physical_source"] = json.dumps(src)
        if slot:
            extra["physical_source_slot"] = json.dumps(slot)
        return {"id": sid, "location": loc, "archived": archived, "extra": extra}

    spools = [spool(1, "HEAD-1", src="BOX-1", slot="1"),           # loaded, with its trail: normal
              spool(2, "SHELF-1", src="BOX-1", slot="2"),          # in stock, a trail, not on a head
              spool(3, "OLD-HEAD", archived=True, src="BOX-1"),    # archived at a retired head with no row
              spool(4, "SHELF-1", slot="3"),                        # slot-only residue
              spool(5, "SHELF-1")]
    res = refresh.drift_count(spools, rows, frozenset({"Tool Head"}))
    assert res["number"] == 1 and [e["id"] for e in res["counted"]] == [2]
    assert res["number_as_filed"] == 2 and [e["id"] for e in res["as_filed"]] == [2, 3]
    assert [e["id"] for e in res["companions"]["slot_only_residue"]] == [4]


# --- reset_dev.py, round 2: archived spools, and the local seed ---------------------------------
#
# Capture and reconcile read spools without allow_archived, so the seed held 267 of dev's 301
# spools: a sweep that archived a seed spool read as "deleted", and one that un-archived an
# archived spool read as sweep-made, so --prune would have deleted it. Since 2026-11-13 the seed is
# local to this PC (the repo is public), so a missing one must stop the run, not half-restore.

class _FakeSpoolman:
    """GET / PATCH / DELETE over in-memory records with Spoolman's list rule: archived spools are
    listed only with allow_archived=true."""

    def __init__(self, spools, vendors=(), filaments=()):
        self.records = {"vendor": {v["id"]: dict(v) for v in vendors},
                        "filament": {f["id"]: dict(f) for f in filaments},
                        "spool": {s["id"]: dict(s) for s in spools}}
        self.gets, self.patches, self.deletes = [], [], []

    def get(self, path):
        self.gets.append(path)
        base, _, query = path.partition("?")
        entity = base.rstrip("/").rsplit("/", 1)[-1]
        rows = [json.loads(json.dumps(r)) for r in self.records[entity].values()]
        if entity == "spool" and "allow_archived=true" not in query:
            rows = [r for r in rows if not r.get("archived")]
        return rows

    def patch(self, entity, eid, payload):
        self.patches.append((entity, eid, json.loads(json.dumps(payload))))
        self.records[entity][eid].update(payload)
        return True, ""

    def delete(self, entity, eid):
        self.deletes.append((entity, eid))
        self.records[entity].pop(eid, None)
        return True, ""


def _use_fake(reset_dev, monkeypatch, fake):
    monkeypatch.setattr(reset_dev, "_check_spoolman_reachable", lambda: None)
    monkeypatch.setattr(reset_dev, "_get", fake.get)
    monkeypatch.setattr(reset_dev, "_patch", fake.patch)
    monkeypatch.setattr(reset_dev, "_delete", fake.delete)


def _write_spoolman_seed(reset_dev, spools, include_archived=True):
    seed = {"vendors": [], "filaments": [], "spools": spools}
    if include_archived:
        seed["spools_include_archived"] = True
    Path(reset_dev.SPOOLMAN_SEED).write_text(json.dumps(seed), encoding="utf-8")


def test_capture_takes_archived_spools_and_marks_the_seed(reset_dev, seed_files, monkeypatch):
    fake = _FakeSpoolman([{"id": 1, "location": "SHELF-1", "archived": False, "extra": {}, "filament": {"id": 3}},
                          {"id": 2, "location": "", "archived": True, "extra": {}, "filament": {"id": 3}}])
    _use_fake(reset_dev, monkeypatch, fake)
    reset_dev.capture()
    seed = json.loads(Path(reset_dev.SPOOLMAN_SEED).read_text(encoding="utf-8"))
    assert sorted(s["id"] for s in seed["spools"]) == [1, 2], "the archived spool is in the seed"
    assert seed["spools_include_archived"] is True
    assert seed["counts"]["spools"] == 2


def test_a_restore_puts_back_a_sweeps_archive_and_unarchive(reset_dev, seed_files, monkeypatch, capsys):
    _write_spoolman_seed(reset_dev, [{"id": 1, "location": "SHELF-1", "archived": False, "extra": {}},
                                     {"id": 2, "location": "", "archived": True, "extra": {}}])
    # What a sweep left: #1 archived (FCC's archive edge blanks its place and notes it), #2 back in
    # stock on a shelf, and #3 made by a test and archived.
    fake = _FakeSpoolman([{"id": 1, "location": "", "archived": True,
                           "extra": {"fcc_pre_archive_location": '"SHELF-1"'}},
                          {"id": 2, "location": "SHELF-1", "archived": False, "extra": {}},
                          {"id": 3, "location": "", "archived": True, "extra": {}}])
    _use_fake(reset_dev, monkeypatch, fake)
    assert reset_dev.restore(dry_run=False, prune=True, do_locations=False, do_spoolman=True,
                             do_restart=False) == 0
    sent = {eid: payload for entity, eid, payload in fake.patches if entity == "spool"}
    assert sent[1] == {"location": "SHELF-1", "archived": False, "extra": {"fcc_pre_archive_location": None}}, \
        "an archived seed spool is restored in stock, where it was, its archive note dropped"
    assert sent[2] == {"location": "", "archived": True}, "an un-archived one goes back to archived"
    assert fake.deletes == [("spool", 3)], "only the sweep's own spool is pruned, never #2"
    assert "2 drifted" in capsys.readouterr().out


def test_an_old_seed_never_prunes_an_archived_spool_it_never_took(reset_dev, seed_files, monkeypatch, capsys):
    _write_spoolman_seed(reset_dev, [{"id": 1, "location": "SHELF-1", "archived": False, "extra": {}}],
                         include_archived=False)
    fake = _FakeSpoolman([{"id": 1, "location": "SHELF-1", "archived": False, "extra": {}},
                          {"id": 2, "location": "", "archived": True, "extra": {}},
                          {"id": 3, "location": "SHELF-1", "archived": False, "extra": {}}])
    _use_fake(reset_dev, monkeypatch, fake)
    reset_dev.restore(dry_run=False, prune=True, do_locations=False, do_spoolman=True, do_restart=False)
    assert ("spool", 2) not in fake.deletes, "a real archived spool the old seed never took is never deleted"
    assert ("spool", 3) in fake.deletes, "an in-stock spool the seed lacks is still sweep-made"
    assert "archived not in the seed" in capsys.readouterr().out


def test_a_restore_stops_first_when_a_seed_file_is_missing(reset_dev, seed_files, monkeypatch, capsys):
    live, _seed = seed_files
    _write_rows(live, LIVE_ROWS)
    before = live.read_bytes()

    def tripwire(*args, **kwargs):
        raise AssertionError("reset_dev read or wrote before it checked its seed files")

    for name in ("_check_spoolman_reachable", "_get", "_patch", "_delete"):
        monkeypatch.setattr(reset_dev, name, tripwire)
    for kwargs in ({"do_locations": True, "do_spoolman": True}, {"do_locations": True, "do_spoolman": False},
                   {"do_locations": False, "do_spoolman": True}):
        for dry_run in (False, True):
            with pytest.raises(SystemExit) as exc:
                reset_dev.restore(dry_run=dry_run, prune=False, do_restart=False, **kwargs)
            assert exc.value.code == 2
            out = capsys.readouterr().out
            assert "--capture" in out and "only on this PC" in out, out
    assert live.read_bytes() == before
