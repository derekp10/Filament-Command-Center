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

Round 3 (2026-11-13) added: the snapshot's folder (seeds/local/, which no
commit tracks and which ignores itself), the prod refusals on a parsed address
(reset_dev.py, the refresh, and the by-hand scripts in utilities/, whose
requests are recorded and never sent), the locations phase building from the
stage copy, review cards it couldn't read, a swap copy that fails part-way,
and the refresh's REFUSED line for an address that doesn't answer.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import runpy
import shutil
import subprocess
import sys
import types
import urllib.error
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


def test_the_swap_identity_check_compares_the_file_with_devs_stage_snapshot(refresh, tmp_path, monkeypatch):
    """Guard (b), last: the target file's counts and max ids against dev's stage snapshot. It shows
    only that nothing wrote dev after `stage`; the marker and the other target checks come first."""
    target = tmp_path / "share" / "spoolman.db"
    target.parent.mkdir()
    _spoolman_db(str(target), spools=5)
    monkeypatch.setattr(refresh, "DEV_SPOOLMAN_DB", str(target))
    snapshot = {"vendor": {"count": 2, "max_id": 2}, "filament": {"count": 3, "max_id": 3},
                "spool": {"count": 5, "max_id": 5}}
    ok, ident = refresh.check_target_identity(snapshot)
    assert ok and ident == snapshot
    other = dict(snapshot, spool={"count": 7, "max_id": 9})      # written after `stage`, say
    ok, ident = refresh.check_target_identity(other)
    assert not ok, "counts that differ from dev's stage snapshot are refused"
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
        "a seed spool the sweep archived is restored in stock, where it was, its archive note dropped"
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
            assert "--capture" in out and "only on the PC that made it" in out, out
    assert live.read_bytes() == before


# --- round 3: the snapshot's folder, and no write to prod in any spelling ------------------------
#
# The snapshot sat at paths main still tracks, so a checkout of main swapped it for June's copy and
# switching back deleted it; it lives in seeds/local/ now, a folder no commit has tracked, which
# ignores itself. reset_dev.py, the refresh and the by-hand scripts in utilities/ compared prod's
# address as a string, or not at all: a zero-padded port or a host alias passed. Every address below
# is made up or prod's by name, and nothing is ever sent: each request is recorded by a stand-in.

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_UTILITIES = os.path.join(_REPO, "utilities")
PROD_SPELLINGS = ["http://192.168.1.29:7912", "http://192.168.1.29:07912", "http://truenas.lan:7912",
                  "https://TRUENAS.:7912/", "http://192.168.1.29:79x2"]


def _same_path(a, b):
    return os.path.normcase(os.path.abspath(str(a))) == os.path.normcase(os.path.abspath(str(b)))


class _Answer:
    """What a recorded request gets back: an empty 200, or Spoolman's info for /info."""

    ok = True
    status_code = 200
    text = ""

    def __init__(self, url):
        self.url = url

    def json(self):
        return {"version": "0.27.1", "db_type": "sqlite"} if self.url.rstrip("/").endswith("/info") else []

    def raise_for_status(self):
        pass


def _record_requests(monkeypatch):
    """requests.get/post/patch/put/delete record what would have been sent and send nothing; any
    other way out through requests is a tripwire."""
    import requests
    sent = []

    def recorder(method):
        def call(url, *args, **kwargs):
            sent.append((method, url))
            return _Answer(url)
        return call

    for name in ("get", "post", "patch", "put", "delete"):
        monkeypatch.setattr(requests, name, recorder(name.upper()))

    def tripwire(*args, **kwargs):
        raise AssertionError("a request went past the recording stand-ins")

    monkeypatch.setattr(requests.Session, "request", tripwire)
    return sent


@pytest.mark.parametrize("url", PROD_SPELLINGS)
def test_reset_dev_refuses_a_dev_spoolman_url_that_names_prod(reset_dev, seed_files, monkeypatch, capsys, url):
    """Since 2026-11-13 the seed holds prod's records under prod's ids: a restore aimed at prod would
    put prod back to the snapshot, and --prune would delete what prod made since. Every mode refuses
    before any request or write."""
    live, seed = seed_files
    _write_rows(live, LIVE_ROWS)
    _write_rows(seed, [dict(r, Name=r["Name"] + " (seed)") for r in _without_login(LIVE_ROWS)])  # drift
    _write_spoolman_seed(reset_dev, [{"id": 1, "location": "SHELF-1", "archived": False, "extra": {}}])
    before = (live.read_bytes(), seed.read_bytes(), Path(reset_dev.SPOOLMAN_SEED).read_bytes())
    sent = _record_requests(monkeypatch)

    def no_command(*args, **kwargs):
        raise AssertionError("reset_dev.py ran a command (docker restart)")

    monkeypatch.setattr(reset_dev.subprocess, "run", no_command)
    monkeypatch.setattr(reset_dev, "SPOOLMAN_URL", url.rstrip("/"))
    for argv in ([], ["--dry-run", "--no-restart"], ["--capture"], ["--prune", "--no-restart"],
                 ["--no-locations", "--no-restart"]):
        monkeypatch.setattr(sys, "argv", ["reset_dev.py"] + argv)
        try:
            rc = reset_dev.main()
        except SystemExit as exc:
            rc = exc.code
        out = capsys.readouterr().out
        assert rc == 2, (argv, rc, out)
        assert "REFUSED" in out and "prod Spoolman" in out, out
    assert sent == [], "a request was sent to an address that names prod"
    assert (live.read_bytes(), seed.read_bytes(), Path(reset_dev.SPOOLMAN_SEED).read_bytes()) == before
    assert reset_dev.prod_refusal("http://192.168.1.29:7913") is None, "dev itself is never refused"
    assert reset_dev.prod_refusal("http://192.168.1.29:07913") is None


def test_capture_makes_the_snapshot_folder_ignore_itself(reset_dev, tmp_path, monkeypatch):
    """--capture on a clone that has no seeds/local/ yet makes it, with a .gitignore that ignores the
    whole folder: on a branch whose own .gitignore doesn't name it (main, until dev is merged), a
    `git add -A` still can't publish the inventory."""
    seeds = tmp_path / "fresh-clone" / "local"
    live = tmp_path / "data" / "locations.json"
    live.parent.mkdir()
    _write_rows(live, LIVE_ROWS)
    monkeypatch.setattr(reset_dev, "LIVE_LOCATIONS", str(live))
    monkeypatch.setattr(reset_dev, "SEEDS_DIR", str(seeds))
    monkeypatch.setattr(reset_dev, "LOCATIONS_SEED", str(seeds / "locations-seed.json"))
    monkeypatch.setattr(reset_dev, "SPOOLMAN_SEED", str(seeds / "spoolman-dev-seed.json"))
    _use_fake(reset_dev, monkeypatch, _FakeSpoolman([]))
    reset_dev.capture()
    ignore = seeds / ".gitignore"
    assert "*" in [line.strip() for line in ignore.read_text(encoding="utf-8").splitlines()]
    assert (seeds / "spoolman-dev-seed.json").exists() and (seeds / "locations-seed.json").exists()
    ignore.write_text("*\n# a person's note\n", encoding="utf-8")
    reset_dev.capture()
    assert ignore.read_text(encoding="utf-8") == "*\n# a person's note\n", "an existing one is left as it is"
    # Git's own answer, in a throwaway repository whose top-level .gitignore names nothing.
    repo = tmp_path / "repo"
    (repo / "seeds").mkdir(parents=True)
    shutil.copytree(seeds, repo / "seeds" / "local")
    try:
        subprocess.run(["git", "init", "-q", str(repo)], check=True, capture_output=True, timeout=60)
        status = subprocess.run(["git", "-C", str(repo), "status", "--porcelain", "--untracked-files=all"],
                                check=True, capture_output=True, text=True, timeout=60).stdout
    except (OSError, subprocess.SubprocessError) as exc:
        pytest.skip(f"git isn't usable here: {exc}")
    assert status.strip() == "", f"git still sees the snapshot: {status!r}"


def test_the_snapshot_lives_in_seeds_local_which_git_never_tracks(reset_dev, refresh):
    """Every reader points at seeds/local/: reset_dev.py, the refresh and the seed canary. A path a
    commit tracks gets swapped by a checkout of main, then deleted by the switch back."""
    local = os.path.join(_REPO, "setup-and-rebuild", "seeds", "local")
    assert _same_path(reset_dev.SEEDS_DIR, local)
    assert _same_path(reset_dev.LOCATIONS_SEED, os.path.join(local, "locations-seed.json"))
    assert _same_path(reset_dev.SPOOLMAN_SEED, os.path.join(local, "spoolman-dev-seed.json"))
    assert _same_path(refresh.SEEDS_DIR, local)
    assert _same_path(refresh.LOCATIONS_SEED, reset_dev.LOCATIONS_SEED)
    assert _same_path(refresh.SPOOLMAN_SEED, reset_dev.SPOOLMAN_SEED)
    import test_box_binding_loans        # the seed canary
    assert _same_path(test_box_binding_loans.SEED, reset_dev.LOCATIONS_SEED)
    try:
        tracked = subprocess.run(["git", "-C", _REPO, "ls-files", "--", "setup-and-rebuild/seeds/local"],
                                 capture_output=True, text=True, timeout=60)
        ignored = subprocess.run(["git", "-C", _REPO, "check-ignore", "-q", "--no-index",
                                  "setup-and-rebuild/seeds/local/spoolman-dev-seed.json"],
                                 capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError) as exc:
        pytest.skip(f"git isn't usable here: {exc}")
    if tracked.returncode != 0:
        pytest.skip("not a git checkout")
    assert tracked.stdout.strip() == "", f"git tracks the snapshot: {tracked.stdout!r}"
    assert ignored.returncode == 0, "the top-level .gitignore doesn't name setup-and-rebuild/seeds/local/"


@pytest.mark.parametrize("alias", ["http://192.168.1.29:07912", "http://truenas.lan:7912", "http://TRUENAS.:7912",
                                   "https://nas.example:7912"])
def test_refresh_sends_no_write_to_prods_port_in_any_spelling(refresh, monkeypatch, capsys, alias):
    """The address is compared by its parsed parts: prod's port gets no write on any host name, even
    with DEV_SPOOLMAN_URL set to it, and main() refuses such a DEV_SPOOLMAN_URL before any phase."""
    monkeypatch.setattr(refresh, "DEV_SPOOLMAN_URL", alias)        # a wrongly set environment variable
    for method in ("POST", "PATCH", "PUT", "DELETE"):
        with pytest.raises(refresh.Refused, match="read-only"):
            refresh.http(method, alias + "/api/v1/spool/123", {"location": "TEST-BOX"})
    assert refresh.main(["checklist"]) == 2          # urlopen is a tripwire: a read would raise
    out = capsys.readouterr().out
    assert "REFUSED" in out and "DEV_SPOOLMAN_URL" in out and "7912" in out, out


def test_refresh_reads_an_address_by_its_parts(refresh, monkeypatch):
    with pytest.raises(refresh.Refused, match="port can't be read"):
        refresh.http("GET", "http://192.168.1.29:79x2/api/v1/info")
    assert refresh.dev_spoolman_refusal("http://192.168.1.29:79x2") == "its port can't be read"
    assert refresh.dev_spoolman_refusal("http://192.168.1.29:7913") is None
    for dev in ("http://192.168.1.29:7913/api/v1/spool/1", "http://192.168.1.29:07913/api/v1/spool/1"):
        with pytest.raises(AssertionError, match="sent a real request"):     # dev gets its writes
            refresh.http("PATCH", dev, {"location": "TEST-BOX"})
    monkeypatch.setattr(refresh, "PROD_SPOOLMAN_URL", "http://10.0.0.99:7999")   # an override's port is prod's too
    with pytest.raises(refresh.Refused, match="read-only"):
        refresh.http("PATCH", "http://192.168.1.29:7999/api/v1/spool/1", {})


def test_refresh_names_the_address_that_didnt_answer(refresh, tmp_path, monkeypatch, capsys):
    def refused(req, timeout=None):
        raise urllib.error.URLError(ConnectionRefusedError(10061, "made-up: nothing listens there"))

    monkeypatch.setattr(refresh.urllib.request, "urlopen", refused)
    assert refresh.main(["checklist"]) == 2
    out = capsys.readouterr().out
    assert ("REFUSED: http://192.168.1.29:7913/api/v1/spool?allow_archived=true didn't answer "
            "(ConnectionRefusedError: [Errno 10061] made-up: nothing listens there); nothing was written.") in out, out

    def patch_phase(args):
        refresh.http("PATCH", refresh.DEV_SPOOLMAN_URL + "/api/v1/spool/123", {"location": "TEST-BOX"})
        return 0

    monkeypatch.setitem(refresh.PHASES, "fixtures", patch_phase)
    assert refresh.main(["fixtures", "--apply"]) == 2
    out = capsys.readouterr().out
    assert "didn't answer the PATCH" in out and "may or may not have landed" in out, out
    assert "written by then: PATCH http://192.168.1.29:7913/api/v1/spool/123 (sent)" in out, out

    monkeypatch.setattr(refresh, "get_json", lambda url, timeout=60: [])     # Spoolman answers; dev's file is gone
    assert refresh.main(["checklist"]) == 2
    out = capsys.readouterr().out
    assert "REFUSED: couldn't use %s" % os.path.join(str(tmp_path / "data"), "locations.json") in out, out
    assert out.rstrip().endswith("nothing was written."), out


def test_review_cards_says_when_it_couldnt_read_the_file(refresh, tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    assert refresh.review_cards() == ([], None), "no file: no cards"
    cards_file = data / "pending_cancel_deducts.json"
    cards_file.write_text(json.dumps({"7#x": {"kind": "no_spool", "job_id": "7", "total_grams": 7.5}}),
                          encoding="utf-8")
    assert refresh.review_cards() == ([{"key": "7#x", "kind": "no_spool", "job_id": "7", "total_grams": 7.5}], None)
    for text, words in (("{not json", "couldn't read"), ("[1, 2]", "not a JSON object")):
        cards_file.write_text(text, encoding="utf-8")
        cards, why = refresh.review_cards()
        assert cards is None and words in why and "pending_cancel_deducts.json" in why, why


def test_the_refresh_never_empties_a_pending_file_it_couldnt_read(refresh, tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    cards, queue = data / "pending_cancel_deducts.json", data / "pending_cancel_fetches.json"
    cards.write_text("{not json", encoding="utf-8")
    queue.write_text(json.dumps({"7": {"printer": "Printer one"}}), encoding="utf-8")
    emptied, left = refresh.empty_pending()
    assert emptied == ["pending_cancel_fetches.json"] and [name for name, _ in left] == ["pending_cancel_deducts.json"]
    assert cards.read_text(encoding="utf-8") == "{not json", "a file it couldn't read is left as it is"
    assert queue.read_text(encoding="utf-8") == "{}"
    emptied, left = refresh.empty_pending(empty_unreadable=True)
    assert left == [] and cards.read_text(encoding="utf-8") == "{}", "the flag empties it"


PROD_LOGIN = {"ip_address": "10.2.2.2", "api_key": "made-up-prod-key-2"}


def _locations_scene(refresh, tmp_path, monkeypatch, *, live_changed=False, db_changed=False, stage_copy=True,
                     cards_text=None):
    """The locations phase over tmp_path: prod's share folders, the stage folder and dev's data are
    folders here, dev FCC's Docker commands and answers are stand-ins, and dev Spoolman lists no spool.
    The stage copy holds one row prod's file lacks (AT-STAGE-ONLY), which shows which file the build
    read; the stage report's hash is the live file's, as `stage` writes it."""
    stage, data, prodfcc, prodshare = (tmp_path / n for n in ("stage", "data", "prodfcc", "prodshare"))
    for folder in (stage, data, prodfcc, prodshare):
        folder.mkdir(exist_ok=True)
    prod_rows = [
        {"LocationID": "SHELF-1", "Type": "Room", "Name": "Shelf one", "parent_id": None},
        {"LocationID": "PRINTER-1", "Type": "Printer", "Name": "Printer one", "parent_id": "SHELF-1",
         "printer_creds": PROD_LOGIN, "toolheads": [{"location_id": "HEAD-1", "position": 0}]},
        {"LocationID": "HEAD-1", "Type": "Tool Head", "Name": "Head one", "Max Spools": "1", "parent_id": "PRINTER-1"},
        {"LocationID": "DRYBOX-1", "Type": "Dryer Box", "Name": "Box one", "Max Spools": "4", "parent_id": "SHELF-1",
         "extra": {"slot_targets": {}}},
    ]
    live_text = json.dumps(prod_rows, indent=4)
    (prodfcc / "locations.json").write_text(live_text, encoding="utf-8", newline="\n")
    db = prodshare / "spoolman.db"
    _spoolman_db(str(db), spools=3)
    report = {"prod_locations": {"sha256": hashlib.sha256(live_text.encode("utf-8")).hexdigest(),
                                 "mtime": "2026-11-09T19:06:31", "rows": len(prod_rows)},
              "prod_db": {"mtime": refresh._iso(os.stat(db).st_mtime)}}
    (stage / "stage-report.json").write_text(json.dumps(report), encoding="utf-8")
    at_stage = refresh.strip_creds(prod_rows) + [
        {"LocationID": "AT-STAGE-ONLY", "Type": "Cart", "Name": "Only in the stage copy", "parent_id": "SHELF-1"}]
    if stage_copy:
        (stage / "prod-locations-at-stage.json").write_text(json.dumps(at_stage, indent=4), encoding="utf-8")
    if live_changed:
        (prodfcc / "locations.json").write_text(live_text.replace("Shelf one", "Shelf one, renamed on prod"),
                                                encoding="utf-8", newline="\n")
    if db_changed:
        st = os.stat(db)
        os.utime(db, (st.st_atime, st.st_mtime + 120))
    dev_rows = [{"LocationID": "PRINTER-1", "Type": "Printer", "Name": "Printer one", "printer_creds": LOGIN},
                {"LocationID": "CART-T", "Type": "Cart", "Name": "Test cart", "parent_id": "SHELF-1"}]
    (data / "locations.json").write_text(json.dumps(dev_rows, indent=4), encoding="utf-8")
    if cards_text is not None:
        (data / "pending_cancel_deducts.json").write_text(cards_text, encoding="utf-8")
    monkeypatch.setattr(refresh, "PROD_FCC_DATA_DIR", str(prodfcc))
    monkeypatch.setattr(refresh, "PROD_SPOOLMAN_DB", str(db))
    monkeypatch.setattr(refresh, "LOCATIONS_SEED", str(tmp_path / "no-seed-here.json"))
    monkeypatch.setattr(refresh, "conftest_constants",
                        lambda: {"baselines": {"DRYBOX-1": {}}, "box": "DRYBOX-1", "slot": "1"})
    monkeypatch.setattr(refresh, "backend_constants",
                        lambda: {"toolhead_types": frozenset({"Tool Head"}), "pseudo_rooms": frozenset()})
    monkeypatch.setattr(refresh, "FLEET", ())
    monkeypatch.setattr(refresh, "NAME_MUST_STAY", ())
    monkeypatch.setattr(refresh, "TEST_CARTS", ("CART-T",))
    monkeypatch.setattr(refresh, "migration_fixpoint", lambda rows: [])
    monkeypatch.setattr(refresh, "get_json", lambda url, timeout=60: [])
    docker = []
    monkeypatch.setattr(refresh, "docker", lambda *args, **kwargs: docker.append(args) or "")
    monkeypatch.setattr(refresh, "container_running", lambda: True)
    monkeypatch.setattr(refresh, "wait_for_fcc", lambda timeout=240: True)

    def fcc_get(path, timeout=30, tries=15):
        if path == "/api/locations":
            return 200, json.loads((data / "locations.json").read_text(encoding="utf-8")), "", {"X-FCC-Spool-Read": "ok"}
        return 200, {"slot_targets": {}}, "", {}

    monkeypatch.setattr(refresh, "fcc_get", fcc_get)
    return types.SimpleNamespace(stage=stage, data=data, docker=docker, at_stage=at_stage,
                                 dev_before=(data / "locations.json").read_bytes())


def test_the_locations_phase_builds_from_the_stage_copy(refresh, tmp_path, monkeypatch, capsys):
    """The copy `stage` saved with the database is what dev's file is built from, not prod's file as it
    reads it later; prod's live rows only tell the report which rows have a login."""
    scene = _locations_scene(refresh, tmp_path, monkeypatch)
    assert refresh.main(["locations", "--apply"]) == 0, capsys.readouterr().out
    rows = {r["LocationID"]: r for r in json.loads((scene.data / "locations.json").read_text(encoding="utf-8"))}
    assert "AT-STAGE-ONLY" in rows, "built from prod's live file, not the stage copy"
    assert rows["PRINTER-1"]["printer_creds"] == LOGIN, "dev keeps its own login"
    assert PROD_LOGIN["api_key"] not in (scene.data / "locations.json").read_text(encoding="utf-8")
    report = json.loads((scene.stage / "locations-report.json").read_text(encoding="utf-8"))
    assert report["build"]["logins_kept"] == [{"LocationID": "PRINTER-1", "prod_differs": True}]
    assert json.loads((scene.stage / "prod-locations-as-read.json").read_text(encoding="utf-8")) == scene.at_stage
    out = capsys.readouterr().out
    assert PROD_LOGIN["api_key"] not in out and PROD_LOGIN["ip_address"] not in out


@pytest.mark.parametrize("change, words", [("live_changed", "locations.json changed after the stage"),
                                           ("db_changed", "Spoolman was written after the copy")])
def test_the_locations_phase_refuses_when_prod_moved_on_after_the_stage(refresh, tmp_path, monkeypatch, capsys,
                                                                         change, words):
    scene = _locations_scene(refresh, tmp_path, monkeypatch, **{change: True})
    for argv in (["locations"], ["locations", "--apply"]):
        assert refresh.main(argv) == 2
        out = capsys.readouterr().out
        assert words in out and "--use-live-locations" in out, out
    assert (scene.data / "locations.json").read_bytes() == scene.dev_before, "nothing written"
    assert not (scene.stage / "dev-data-before").exists() and scene.docker == [], "FCC never stopped"
    assert refresh.main(["locations", "--apply", "--use-live-locations"]) == 0, capsys.readouterr().out
    rows = {r["LocationID"]: r for r in json.loads((scene.data / "locations.json").read_text(encoding="utf-8"))}
    assert "AT-STAGE-ONLY" not in rows, "--use-live-locations builds from prod's file as it reads it now"
    if change == "live_changed":
        assert rows["SHELF-1"]["Name"] == "Shelf one, renamed on prod"


def test_the_locations_phase_needs_the_stage_copy(refresh, tmp_path, monkeypatch, capsys):
    scene = _locations_scene(refresh, tmp_path, monkeypatch, stage_copy=False)
    assert refresh.main(["locations", "--apply"]) == 2
    assert "no stage copy of prod's locations.json" in capsys.readouterr().out
    assert (scene.data / "locations.json").read_bytes() == scene.dev_before
    assert refresh.main(["locations", "--apply", "--use-live-locations"]) == 0, capsys.readouterr().out


def test_the_locations_phase_never_empties_review_cards_it_couldnt_read(refresh, tmp_path, monkeypatch, capsys):
    scene = _locations_scene(refresh, tmp_path, monkeypatch, cards_text="{not json")
    cards = scene.data / "pending_cancel_deducts.json"
    for argv in (["locations"], ["locations", "--apply"]):
        assert refresh.main(argv) == 2
        out = capsys.readouterr().out
        assert "couldn't read" in out and "pending_cancel_deducts.json" in out and "--empty-unreadable" in out, out
    assert cards.read_text(encoding="utf-8") == "{not json"
    assert (scene.data / "locations.json").read_bytes() == scene.dev_before
    assert refresh.main(["locations", "--apply", "--empty-unreadable"]) == 0, capsys.readouterr().out
    assert cards.read_text(encoding="utf-8") == "{}", "the flag empties it"
    assert (scene.stage / "dev-data-before" / "pending_cancel_deducts.json").read_text(encoding="utf-8") == "{not json", \
        "after the backup kept its bytes"


def test_the_build_reads_prods_logins_only_for_its_report(refresh):
    live = [{"LocationID": "PRINTER-1", "Type": "Printer", "Name": "Printer one", "printer_creds": PROD_LOGIN},
            {"LocationID": "PRINTER-2", "Type": "Printer", "Name": "Printer two", "printer_creds": PROD_LOGIN}]
    stage_copy = refresh.strip_creds(live)
    dev = [{"LocationID": "PRINTER-1", "Type": "Printer", "Name": "Printer one", "printer_creds": LOGIN}]
    rows, rep = refresh.build_dev_locations(stage_copy, dev, {}, (), logins_rows=live)
    by = {r["LocationID"]: r for r in rows}
    assert by["PRINTER-1"]["printer_creds"] == LOGIN and "printer_creds" not in by["PRINTER-2"]
    assert rep["logins_kept"] == [{"LocationID": "PRINTER-1", "prod_differs": True}]
    assert rep["prod_logins_not_taken"] == ["PRINTER-2"]
    assert PROD_LOGIN["api_key"] not in json.dumps(rows) + json.dumps(rep)
    same = [dict(live[0], printer_creds=LOGIN), live[1]]
    _, rep = refresh.build_dev_locations(stage_copy, dev, {}, (), logins_rows=same)
    assert rep["logins_kept"] == [{"LocationID": "PRINTER-1", "prod_differs": False}]


def test_a_swap_copy_that_fails_part_way_names_the_backup_to_put_back(refresh, tmp_path, monkeypatch, capsys):
    scene = _swap_scene(refresh, tmp_path, monkeypatch)
    original = scene.db.read_bytes()
    real_copyfile = shutil.copyfile

    def copyfile(src, dst, *args, **kwargs):
        if _same_path(dst, scene.db):
            with open(dst, "wb") as fh:        # shutil.copyfile opens the target 'wb', so it is cut short
                fh.write(b"partial")
            raise OSError(5, "made-up: the share went away mid-copy")
        return real_copyfile(src, dst, *args, **kwargs)

    monkeypatch.setattr(refresh.shutil, "copyfile", copyfile)
    assert refresh.main(["swap", "--apply"]) == 2
    out = capsys.readouterr().out
    backup = scene.stage / "dev-spoolman-before.db"
    assert "failed part-way" in out and "may now be partial" in out, out
    assert "Before you start dev Spoolman, put the backup %s back" % backup in out, out
    assert backup.read_bytes() == original, "the backup holds dev's database as it was"


def test_the_count_reads_the_stage_copy_before_prods_live_file(refresh, tmp_path, monkeypatch, capsys):
    stage = tmp_path / "stage"
    stage.mkdir()
    rows = [{"LocationID": "SHELF-1", "Type": "Shelf"}]
    (stage / "prod-locations-at-stage.json").write_text(json.dumps(rows), encoding="utf-8")

    def no_live_read():
        raise AssertionError("the count read prod's live locations.json while the stage holds a copy")

    monkeypatch.setattr(refresh, "read_prod_locations", no_live_read)
    monkeypatch.setattr(refresh, "get_json", lambda url, timeout=60: [])
    monkeypatch.setattr(refresh, "backend_constants",
                        lambda: {"toolhead_types": frozenset({"Tool Head"}), "pseudo_rooms": frozenset()})
    assert refresh.main(["count"]) == 0
    assert "prod-locations-at-stage.json" in capsys.readouterr().out
    (stage / "prod-locations-as-read.json").write_text(json.dumps(rows), encoding="utf-8")
    assert _same_path(refresh.count_prod_locations_path(), stage / "prod-locations-as-read.json"), \
        "the copy `locations --apply` built from comes first"
    assert refresh.count_prod_locations_path("given.json") == "given.json"


def test_the_fixtures_check_says_what_it_found(refresh):
    good = [{"id": 123, "slot": '"1"', "display": "#123 made-up"}]
    assert refresh.fixture_verdict("TEST-BOX", "1", 6, 123, 200, good) == (
        True, "OK: TEST-BOX slot 1 holds #123, and its other slots (2-6) are empty")
    ok, line = refresh.fixture_verdict("TEST-BOX", "3", 6, 123, 200, [dict(good[0], slot="3")])
    assert ok and "other slots (1-2, 4-6)" in line, line
    assert refresh.fixture_verdict("TEST-BOX", "1", 1, 123, 200, good) == (True, "OK: TEST-BOX slot 1 holds #123")
    assert refresh.fixture_verdict("TEST-BOX", "1", 6, 123, 200, []) == (
        False, "CHECK FAILED: TEST-BOX should hold only #123 in slot 1; FCC lists nothing there")
    ok, line = refresh.fixture_verdict("TEST-BOX", "1", 6, 123, 200,
                                       good + [{"id": 7, "slot": "2", "display": "#7 made-up"}])
    assert not ok and "#7 in slot 2" in line and "holds #123" not in line, line
    ok, line = refresh.fixture_verdict("TEST-BOX", "1", 6, 123, 502, None)
    assert not ok and line.endswith("FCC answered HTTP 502"), line
    ok, line = refresh.fixture_verdict("TEST-BOX", "1", 6, 123, 200, good, want_display="#123 another")
    assert not ok and "reading '#123 another'" in line, line
    assert not hasattr(refresh, "SPOOLS_TESTS_NAME"), "no test scans #1 or #2 any more (throwaway spools)"


def test_every_phase_says_in_the_help_what_it_does_and_when(refresh, capsys):
    for name, phase in refresh.PHASES.items():
        assert (phase.__doc__ or "").strip(), f"{name} has no one-line docstring for --help"
    with pytest.raises(SystemExit):
        refresh.main(["--help"])
    out = capsys.readouterr().out
    assert "Run order" in out and "dev Spoolman DOWN" in out and "(by hand)" in out, out
    for name in refresh.PHASES:
        assert name in out


# --- utilities/: the by-hand scripts that write go to dev, never prod --------------------------

def _load_by_path(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def utilities(monkeypatch, tmp_path):
    """utilities/ loaded by path, with project_config reading a made-up repo config.json, and every
    request recorded, never sent."""
    pc = _load_by_path("project_config", os.path.join(_UTILITIES, "project_config.py"))
    monkeypatch.setitem(sys.modules, "project_config", pc)
    config = tmp_path / "config.json"
    monkeypatch.setattr(pc, "REPO_CONFIG", str(config), raising=False)
    sent = _record_requests(monkeypatch)

    def write_config(port, host="192.168.1.29"):
        config.write_text(json.dumps({"server_ip": host, "spoolman_port": port}), encoding="utf-8")

    def load(name):
        return _load_by_path("utility_" + name, os.path.join(_UTILITIES, name + ".py"))

    return types.SimpleNamespace(load=load, sent=sent, config=write_config, path=lambda n: os.path.join(_UTILITIES, n))


@pytest.mark.parametrize("port, host", [(7912, "192.168.1.29"), ("07912", "192.168.1.29"), (7912, "truenas.lan")])
def test_the_spool_63_probe_refuses_prod(utilities, capsys, port, host):
    utilities.config(port, host)
    mod = utilities.load("test_assignment")
    assert utilities.sent == [], "importing it sends nothing"
    with pytest.raises(SystemExit) as exc:
        mod.main()
    assert exc.value.code == 2 and utilities.sent == [], utilities.sent
    assert "REFUSED" in capsys.readouterr().out


def test_the_spool_63_probe_writes_to_dev_by_default(utilities):
    mod = utilities.load("test_assignment")
    mod.main()                                            # no config.json: dev's default address
    assert [m for m, _ in utilities.sent] == ["PATCH", "PATCH"]
    assert all(url == "http://192.168.1.29:7913/api/v1/spool/63" for _, url in utilities.sent), utilities.sent
    utilities.config(7913, "dev.example")                  # the repo-root config.json, when it names one
    del utilities.sent[:]
    mod.main()
    assert {url for _, url in utilities.sent} == {"http://dev.example:7913/api/v1/spool/63"}


def test_the_field_probe_is_no_pytest_test_and_never_writes_prod(utilities, capsys):
    mod = utilities.load("debug_test")
    assert not hasattr(mod, "test_create_field"), "`pytest utilities/debug_test.py` would collect and run it"
    for url in ("http://192.168.1.29:7912", "http://truenas.lan:07912"):
        with pytest.raises(SystemExit):
            mod.probe_create_field(url)
    assert utilities.sent == []
    mod.probe_create_field()
    assert utilities.sent == [("POST", "http://192.168.1.29:7913/api/v1/field/filament/debug_test_field")]


def test_the_field_rebuild_never_writes_prod(utilities, capsys):
    """repair_db_fields.py deletes the container_slot field, which wipes it on every spool: it named
    prod, and nothing stopped a by-hand run."""
    utilities.config(7912)
    with pytest.raises(SystemExit) as exc:
        runpy.run_path(utilities.path("repair_db_fields.py"), run_name="__main__")
    assert exc.value.code == 2 and utilities.sent == [], utilities.sent
    mod = utilities.load("repair_db_fields")
    with pytest.raises(SystemExit):
        mod.nuke_and_pave("container_slot", "Container / MMU Slot", "text", "http://truenas.lan:7912")
    assert utilities.sent == []
