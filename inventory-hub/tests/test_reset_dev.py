"""Group 19.1 — hermetic unit coverage for reset_dev.py's restore-decision logic.

These tests exercise the PURE comparison helpers (`_values_equal`,
`_drifted_payload`) that decide which fields get PATCHed back to the seed.
They touch no network and no Spoolman — the network round-trips (capture,
PATCH, DELETE, docker restart) are validated by running the script against
the live dev backend, but the drift logic that gates every write is locked
down here so a regression can't silently start over- or under-writing.
"""
from __future__ import annotations

import importlib.util
import json
import os

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
# The locations seed is committed and pushed, and dev's locations.json holds a
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


@pytest.fixture
def refresh(monkeypatch, tmp_path):
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
