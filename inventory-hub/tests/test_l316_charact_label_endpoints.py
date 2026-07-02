"""L316 characterization tests — pins pre-carve behavior of the label-CSV
endpoints (/api/print_location_label and /api/print_batch_csv location +
filament/swatch modes). Generated from the 2026-07-01 coverage audit. Do not
weaken these to make a refactor pass.

Host-runnable unit tests: no live server, no live Spoolman. Every outbound
call (Spoolman via spoolman_api / requests, locations.json via locations_db,
config via config_loader) is patched, and ALL CSV output is redirected into
tmp_path — the real label CSVs are P-touch database sources and must never
be written by tests.

The exact row dicts asserted here are the P-touch template contract: the
.lbx label templates map columns by name/order, so any drift in keys, QR
string formats (LOC:/SLOT:/FIL:), or header order silently corrupts printed
labels.
"""
from __future__ import annotations

import builtins
import csv
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import app as app_module  # noqa: E402


@pytest.fixture
def client():
    return app_module.app.test_client()


# ---------------------------------------------------------------------------
# shared plumbing
# ---------------------------------------------------------------------------

def _mount_output(monkeypatch, tmp_path):
    """Point print_settings.csv_path into tmp_path so both endpoints derive
    ALL their output files (labels_locations.csv / slots_to_print.csv /
    labels_swatch.csv / labels_spool.csv) inside the sandbox."""
    monkeypatch.setattr(
        app_module.config_loader, "load_config",
        lambda: {"print_settings": {"csv_path": str(tmp_path / "labels.csv")}})


def _set_locations(monkeypatch, rows):
    monkeypatch.setattr(app_module.locations_db, "load_locations_list", lambda: rows)


def _capture_logs(monkeypatch):
    logs = []
    monkeypatch.setattr(app_module.state, "add_log_entry",
                        lambda msg, *a, **k: logs.append((msg,) + tuple(a)))
    return logs


class _WriterSpy:
    """Fake _write_label_csv that records every call instead of touching disk."""

    def __init__(self):
        self.calls = []

    def __call__(self, path, fieldnames, rows, *, overwrite, write_header):
        self.calls.append({
            "path": path,
            "fieldnames": list(fieldnames),
            "rows": [dict(r) for r in rows],
            "overwrite": overwrite,
            "write_header": write_header,
        })


class _FakeResp:
    def __init__(self, ok=True, payload=None):
        self.ok = ok
        self._payload = payload or {}

    def json(self):
        return self._payload


def _csv_lines(path):
    return [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]


def _csv_rows(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _stub_label_helpers(monkeypatch):
    """Decouple batch-endpoint tests from the data-extraction helpers
    (same idiom as tests/test_label_csv_export.py)."""
    monkeypatch.setattr(app_module, "get_color_name", lambda f: "TestColor")
    monkeypatch.setattr(app_module, "get_smart_type", lambda m, e: "TestType")
    monkeypatch.setattr(app_module, "get_best_hex", lambda f: "AABBCC")


LOC_ROWS = [
    {"LocationID": "PM-DB-XL-L", "Name": "XL Left Box", "Max Spools": "4"},
    # weird-cased/whitespaced keys — the handler matches keys case-insensitively
    {"locationid": "ODD-1", "NAME": "Odd Row", "MAX SPOOLS": "2"},
    {"LocationID": "SHELF-1", "Name": "Wall Shelf 1"},              # no Max Spools
    {"LocationID": "BAD-MAX", "Name": "Bad Max", "Max Spools": "lots"},  # unparsable
]


# ===========================================================================
# 1. /api/print_location_label  (app.py api_print_location_label)
# ===========================================================================

def test_location_label_normal_append_writes_main_and_slot_rows(client, tmp_path, monkeypatch):
    """Pins the whole happy path: lowercase scanned id is uppercased, the main
    label row lands in labels_locations.csv with the exact 4-column header and
    LOC: QR prefix, and Max Spools=4 fans out 4 slot rows into
    slots_to_print.csv with LOC:<id>:SLOT:<n> QR strings (the physical-label
    contract)."""
    _mount_output(monkeypatch, tmp_path)
    _set_locations(monkeypatch, LOC_ROWS)

    resp = client.post("/api/print_location_label", json={"id": "pm-db-xl-l"})
    body = resp.get_json()
    assert body["success"] is True
    assert body["msg"].startswith("Queue: PM-DB-XL-L (+4 Slots) in ")

    loc_file = tmp_path / "labels_locations.csv"
    assert _csv_lines(loc_file)[0] == "LocationID,Name,Cleaned_Name,QR_Code"
    assert _csv_rows(loc_file) == [{
        "LocationID": "PM-DB-XL-L",
        "Name": "XL Left Box",
        "Cleaned_Name": "XL Left Box",
        "QR_Code": "LOC:PM-DB-XL-L",
    }]

    slot_file = tmp_path / "slots_to_print.csv"
    assert _csv_lines(slot_file)[0] == "LocationID,Slot,Name,Cleaned_Name,QR_Code"
    assert _csv_rows(slot_file) == [
        {
            "LocationID": "PM-DB-XL-L",
            "Slot": f"Slot {i}",
            "Name": f"XL Left Box Slot {i}",
            "Cleaned_Name": f"XL Left Box Slot {i}",
            "QR_Code": f"LOC:PM-DB-XL-L:SLOT:{i}",
        }
        for i in range(1, 5)
    ]


def test_location_label_second_post_appends_without_duplicate_header(client, tmp_path, monkeypatch):
    """Pins the append semantics: the endpoint always opens in append mode and
    only writes a header when the file did not exist, so re-queueing a label
    must add data rows without a second header line (P-touch reads the CSV as
    a database — a mid-file header row becomes a garbage label)."""
    _mount_output(monkeypatch, tmp_path)
    _set_locations(monkeypatch, LOC_ROWS)

    for _ in range(2):
        assert client.post("/api/print_location_label",
                           json={"id": "PM-DB-XL-L"}).get_json()["success"] is True

    loc_lines = _csv_lines(tmp_path / "labels_locations.csv")
    assert loc_lines.count("LocationID,Name,Cleaned_Name,QR_Code") == 1
    assert len(_csv_rows(tmp_path / "labels_locations.csv")) == 2

    slot_lines = _csv_lines(tmp_path / "slots_to_print.csv")
    assert slot_lines.count("LocationID,Slot,Name,Cleaned_Name,QR_Code") == 1
    assert len(_csv_rows(tmp_path / "slots_to_print.csv")) == 8  # 4 slots x 2 posts


def test_location_label_unassigned_special_case_no_slots(client, tmp_path, monkeypatch):
    """Pins the UNASSIGNED synthetic row: no DB lookup, Name 'Unassigned',
    Max Spools 0 so no slots file is created, and the WRITTEN LocationID is
    the uppercased scanned id ('UNASSIGNED'), not the synthetic row's
    'Unassigned' — the handler always writes target_id."""
    _mount_output(monkeypatch, tmp_path)
    _set_locations(monkeypatch, [])  # lookup list is irrelevant for UNASSIGNED

    resp = client.post("/api/print_location_label", json={"id": "Unassigned"})
    body = resp.get_json()
    assert body["success"] is True
    assert body["msg"].startswith("Queue: UNASSIGNED in ")
    assert "Slots" not in body["msg"]

    assert _csv_rows(tmp_path / "labels_locations.csv") == [{
        "LocationID": "UNASSIGNED",
        "Name": "Unassigned",
        "Cleaned_Name": "Unassigned",
        "QR_Code": "LOC:UNASSIGNED",
    }]
    assert not (tmp_path / "slots_to_print.csv").exists()


def test_location_label_matches_row_keys_case_insensitively(client, tmp_path, monkeypatch):
    """Pins the tolerant lookup: a row stored with keys 'locationid' / 'NAME' /
    'MAX SPOOLS' still matches (str(k).strip().lower() comparison), the name is
    read from the odd-cased key, and Max Spools '2' fans out 2 slots."""
    _mount_output(monkeypatch, tmp_path)
    _set_locations(monkeypatch, LOC_ROWS)

    resp = client.post("/api/print_location_label", json={"id": "odd-1"})
    body = resp.get_json()
    assert body["success"] is True
    assert body["msg"].startswith("Queue: ODD-1 (+2 Slots) in ")

    assert _csv_rows(tmp_path / "labels_locations.csv") == [{
        "LocationID": "ODD-1",
        "Name": "Odd Row",
        "Cleaned_Name": "Odd Row",
        "QR_Code": "LOC:ODD-1",
    }]
    assert [r["QR_Code"] for r in _csv_rows(tmp_path / "slots_to_print.csv")] == [
        "LOC:ODD-1:SLOT:1", "LOC:ODD-1:SLOT:2"]


def test_location_label_max_spools_missing_or_unparsable_means_no_slots(client, tmp_path, monkeypatch):
    """Pins the slot-count default: a row with NO 'Max Spools' key and a row
    with an unparsable value ('lots') both resolve to max_spools=1, which is
    not > 1, so neither creates slots_to_print.csv."""
    _mount_output(monkeypatch, tmp_path)
    _set_locations(monkeypatch, LOC_ROWS)

    for loc_id in ("SHELF-1", "BAD-MAX"):
        body = client.post("/api/print_location_label", json={"id": loc_id}).get_json()
        assert body["success"] is True
        assert "Slots" not in body["msg"]

    assert not (tmp_path / "slots_to_print.csv").exists()
    assert len(_csv_rows(tmp_path / "labels_locations.csv")) == 2


def test_location_label_no_id_and_unknown_id_guards(client, tmp_path, monkeypatch):
    """Pins the two guard responses (exact msg strings the frontend toasts)
    and that neither guard writes any file."""
    _mount_output(monkeypatch, tmp_path)
    _set_locations(monkeypatch, LOC_ROWS)

    assert client.post("/api/print_location_label", json={}).get_json() == {
        "success": False, "msg": "No ID provided"}
    assert client.post("/api/print_location_label", json={"id": "NOPE"}).get_json() == {
        "success": False, "msg": "ID Not Found in DB"}

    assert not (tmp_path / "labels_locations.csv").exists()
    assert not (tmp_path / "slots_to_print.csv").exists()


def test_location_label_write_failure_is_quiet_no_activity_log_no_locked_flag(client, tmp_path, monkeypatch):
    """A locked labels_locations.csv (P-touch holding the handle) surfaces as
    a bare {'success': False, 'msg': str(e)} — NO 'locked' flag and NO
    Activity Log entry, unlike /api/print_batch_csv's loud-lock contract.

    # NOTE: pins current behavior; see suspected_bugs — this endpoint predates
    # the 2026-06-18 loud-error work and is the known-open 'single-label
    # endpoint' buglist item. Also pins that it uses a raw open('a') instead
    # of _write_label_csv (no atomicity, no fcc_locked_name tagging)."""
    _mount_output(monkeypatch, tmp_path)
    _set_locations(monkeypatch, LOC_ROWS)
    logs = _capture_logs(monkeypatch)

    real_open = builtins.open

    def _fake_open(file, *args, **kwargs):
        if str(file).endswith("labels_locations.csv"):
            raise PermissionError(13, "locked by test")
        return real_open(file, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", _fake_open)

    body = client.post("/api/print_location_label", json={"id": "PM-DB-XL-L"}).get_json()
    assert body["success"] is False
    assert body["msg"] == "[Errno 13] locked by test"   # raw str(e), no friendly wording
    assert "locked" not in body                          # no lock flag for the UI
    assert logs == []                                    # no Activity Log entry (silent failure)
    assert not (tmp_path / "labels_locations.csv").exists()


# ===========================================================================
# 2. /api/print_batch_csv — mode='location'
# ===========================================================================

def test_batch_location_dedup_fallback_and_slot_fanout_exact_rows(client, tmp_path, monkeypatch):
    """Pins the whole location-mode pipeline: batch dedup (repeated id
    processed once), local lookup vs live-Spoolman name fallback (patched
    requests.get, timeout=2), the LOC: QR strings, the exact 4-key row dicts,
    AND the second _write_label_csv call for slots_to_print.csv with the
    pinned 5-column header order."""
    _mount_output(monkeypatch, tmp_path)
    _set_locations(monkeypatch, [{"LocationID": "SH-A1", "Name": "Shelf A1", "Max Spools": "3"}])
    monkeypatch.setattr(app_module.config_loader, "get_api_urls",
                        lambda: ("http://sm.test", "http://fb.test/api"))
    logs = _capture_logs(monkeypatch)

    get_calls = []

    def _fake_get(url, *a, **k):
        get_calls.append((url, k))
        return _FakeResp(ok=True, payload={"name": "Remote Loc"})

    monkeypatch.setattr(app_module.requests, "get", _fake_get)

    spy = _WriterSpy()
    monkeypatch.setattr(app_module, "_write_label_csv", spy)

    resp = client.post("/api/print_batch_csv",
                       json={"ids": ["SH-A1", "SH-A1", "999"],
                             "mode": "location", "clear_old": True})
    body = resp.get_json()
    assert body["success"] is True
    assert body["count"] == 2                       # SH-A1 deduped
    assert body["file"] == "labels_locations.csv"
    assert body["msg"] == "Overwritten 2 items. (+3 Slots)"

    # Spoolman fallback hit exactly once, for the unknown id, with timeout=2
    assert get_calls == [("http://sm.test/api/v1/location/999", {"timeout": 2})]

    assert len(spy.calls) == 2
    main = spy.calls[0]
    assert main["path"] == str(tmp_path / "labels_locations.csv")
    assert main["fieldnames"] == ["LocationID", "Name", "Cleaned_Name", "QR_Code"]
    assert main["overwrite"] is True and main["write_header"] is True
    assert main["rows"] == [
        {"LocationID": "SH-A1", "Name": "Shelf A1",
         "QR_Code": "LOC:SH-A1", "Cleaned_Name": "Shelf A1"},
        {"LocationID": "999", "Name": "Remote Loc",
         "QR_Code": "LOC:999", "Cleaned_Name": "Remote Loc"},
    ]

    slots = spy.calls[1]
    assert slots["path"] == str(tmp_path / "slots_to_print.csv")
    assert slots["fieldnames"] == ["LocationID", "Slot", "Name", "Cleaned_Name", "QR_Code"]
    assert slots["overwrite"] is True and slots["write_header"] is True
    assert slots["rows"] == [
        {"LocationID": "SH-A1", "Slot": f"Slot {i}", "Name": f"Shelf A1 Slot {i}",
         "Cleaned_Name": f"Shelf A1 Slot {i}", "QR_Code": f"LOC:SH-A1:SLOT:{i}"}
        for i in range(1, 4)
    ]

    # success Activity Log names the file and the slot count
    assert any("labels_locations.csv" in t[0] and "+ 3 slot label(s)" in t[0]
               for t in logs), logs


@pytest.mark.parametrize("failure", ["raises", "not_ok"])
def test_batch_location_spoolman_fallback_failure_uses_raw_id(client, tmp_path, monkeypatch, failure):
    """Pins the bare-except fallback around the live Spoolman location fetch:
    whether requests.get raises OR returns not-ok, the Name (and Cleaned_Name)
    silently degrade to the raw id string and the export still succeeds."""
    _mount_output(monkeypatch, tmp_path)
    _set_locations(monkeypatch, [])
    monkeypatch.setattr(app_module.config_loader, "get_api_urls",
                        lambda: ("http://sm.test", "http://fb.test/api"))

    if failure == "raises":
        def _fake_get(url, *a, **k):
            raise RuntimeError("spoolman down")
    else:
        def _fake_get(url, *a, **k):
            return _FakeResp(ok=False)

    monkeypatch.setattr(app_module.requests, "get", _fake_get)

    spy = _WriterSpy()
    monkeypatch.setattr(app_module, "_write_label_csv", spy)

    body = client.post("/api/print_batch_csv",
                       json={"ids": ["999"], "mode": "location",
                             "clear_old": True}).get_json()
    assert body["success"] is True and body["count"] == 1
    assert len(spy.calls) == 1  # no loc_data -> max_spools 0 -> no slots write
    assert spy.calls[0]["rows"] == [
        {"LocationID": "999", "Name": "999", "QR_Code": "LOC:999", "Cleaned_Name": "999"}]


def test_batch_location_max_spools_key_case_insensitive(client, tmp_path, monkeypatch):
    """Pins the ' max SPOOLS ' -> 'max spools' strip/lower key matching in the
    batch handler's slot fan-out (independent of the sibling endpoint's)."""
    _mount_output(monkeypatch, tmp_path)
    _set_locations(monkeypatch,
                   [{"LocationID": "SH-B2", "Name": "B2 Shelf", " max SPOOLS ": "2"}])
    spy = _WriterSpy()
    monkeypatch.setattr(app_module, "_write_label_csv", spy)

    body = client.post("/api/print_batch_csv",
                       json={"ids": ["SH-B2"], "mode": "location",
                             "clear_old": True}).get_json()
    assert body["success"] is True
    assert body["msg"] == "Overwritten 1 items. (+2 Slots)"
    assert len(spy.calls) == 2
    assert [r["QR_Code"] for r in spy.calls[1]["rows"]] == [
        "LOC:SH-B2:SLOT:1", "LOC:SH-B2:SLOT:2"]


def test_batch_location_max_spools_one_writes_no_slots_file(client, tmp_path, monkeypatch):
    """Pins that slot fan-out requires Max Spools > 1 (a 1-slot location gets
    no slots_to_print.csv write) and the singular-count message grammar
    ('Overwritten 1 items.') as-is."""
    _mount_output(monkeypatch, tmp_path)
    _set_locations(monkeypatch, [{"LocationID": "SH-C1", "Name": "C1", "Max Spools": "1"}])
    spy = _WriterSpy()
    monkeypatch.setattr(app_module, "_write_label_csv", spy)

    body = client.post("/api/print_batch_csv",
                       json={"ids": ["SH-C1"], "mode": "location",
                             "clear_old": True}).get_json()
    assert body["success"] is True
    assert body["msg"] == "Overwritten 1 items."
    assert len(spy.calls) == 1
    assert spy.calls[0]["path"] == str(tmp_path / "labels_locations.csv")


def test_batch_location_row_missing_exact_locationid_key_fails_whole_export(client, tmp_path, monkeypatch):
    """The location-mode pre-load builds loc_lookup via row['LocationID'] —
    an EXACT key access. One row stored with a differently-cased key (e.g.
    'locationid') raises KeyError and the generic handler fails the ENTIRE
    batch with msg \"'LocationID'\" plus an ERROR Activity Log entry.

    # NOTE: pins current behavior; see suspected_bugs — inconsistent with the
    # case-insensitive key matching used for 'Max Spools' later in this same
    # handler and with api_print_location_label's tolerant lookup."""
    _mount_output(monkeypatch, tmp_path)
    _set_locations(monkeypatch, [{"locationid": "WEIRD-1", "Name": "W"}])
    logs = _capture_logs(monkeypatch)
    spy = _WriterSpy()
    monkeypatch.setattr(app_module, "_write_label_csv", spy)

    body = client.post("/api/print_batch_csv",
                       json={"ids": ["WEIRD-1"], "mode": "location",
                             "clear_old": True}).get_json()
    assert body["success"] is False
    assert body["msg"] == "'LocationID'"        # raw str(KeyError)
    assert spy.calls == []
    assert any(len(t) > 1 and t[1] == "ERROR"
               and "Label CSV export failed (labels_locations.csv)" in t[0]
               for t in logs), logs


# ===========================================================================
# 3. /api/print_batch_csv — filament/swatch mode
# ===========================================================================

FILAMENT_7 = {
    "id": 7,
    "material": "PETG",
    "vendor": {"name": "Acme"},
    "extra": {},
    "settings_extruder_temp": 240,
    "settings_bed_temp": 85,
    "density": 1.27,
}

SWATCH_CORE_HEADERS = ["ID", "Brand", "Color", "Type", "Hex", "Red", "Green",
                       "Blue", "Temp_Nozzle", "Temp_Bed", "Density", "QR_Code"]


def test_batch_filament_mode_exact_row_headers_and_temp_formatting(client, tmp_path, monkeypatch):
    """Pins the swatch-label contract: filename labels_swatch.csv, FIL: QR
    prefix, degree-formatted temps ('240°C'), density ('1.27 g/cm³'),
    hex->RGB split, and the flatten_json spillover columns appended to the
    core headers in sorted order — the exact dict P-touch's swatch template
    maps by column name."""
    _mount_output(monkeypatch, tmp_path)
    _stub_label_helpers(monkeypatch)
    monkeypatch.setattr(app_module.spoolman_api, "get_filament",
                        lambda fid: FILAMENT_7 if fid == 7 else None)
    spy = _WriterSpy()
    monkeypatch.setattr(app_module, "_write_label_csv", spy)

    body = client.post("/api/print_batch_csv",
                       json={"ids": [7], "mode": "filament",
                             "clear_old": True}).get_json()
    assert body["success"] is True
    assert body["file"] == "labels_swatch.csv"
    assert body["count"] == 1

    assert len(spy.calls) == 1
    call = spy.calls[0]
    assert call["path"] == str(tmp_path / "labels_swatch.csv")
    # core headers first, then flatten_json extras sorted alphabetically
    assert call["fieldnames"] == SWATCH_CORE_HEADERS + [
        "density", "id", "material", "settings_bed_temp",
        "settings_extruder_temp", "vendor_name"]
    assert call["rows"] == [{
        "ID": 7,
        "Brand": "Acme",
        "Color": "TestColor",
        "Type": "TestType",
        "Hex": "AABBCC",
        "Red": 170, "Green": 187, "Blue": 204,
        "Temp_Nozzle": "240°C",
        "Temp_Bed": "85°C",
        "Density": "1.27 g/cm³",
        "QR_Code": "FIL:7",
        # flatten_json spillover (keys not already in the row)
        "id": 7,
        "material": "PETG",
        "vendor_name": "Acme",
        "settings_extruder_temp": 240,
        "settings_bed_temp": 85,
        "density": 1.27,
    }]


def test_batch_filament_mode_absent_or_zero_temps_render_empty_and_brand_unsanitized(client, tmp_path, monkeypatch):
    """Pins the falsy-temp rendering: absent nozzle temp AND a literal 0 bed
    temp both become '' (a deliberate 0°C prints blank), absent density
    becomes '', and — unlike spool/location modes — the filament branch does
    NOT run sanitize_label_text, so emoji survive into Brand.

    # NOTE: pins current behavior; see suspected_bugs (0-temp rendered blank;
    # sanitize asymmetry between spool and filament modes)."""
    _mount_output(monkeypatch, tmp_path)
    monkeypatch.setattr(app_module, "get_color_name", lambda f: "TestColor")
    monkeypatch.setattr(app_module, "get_smart_type", lambda m, e: "TestType")
    monkeypatch.setattr(app_module, "get_best_hex", lambda f: "")
    monkeypatch.setattr(
        app_module.spoolman_api, "get_filament",
        lambda fid: {"id": 8, "material": "PLA", "vendor": {"name": "\U0001f99d Labs"},
                     "extra": {}, "settings_bed_temp": 0})
    spy = _WriterSpy()
    monkeypatch.setattr(app_module, "_write_label_csv", spy)

    body = client.post("/api/print_batch_csv",
                       json={"ids": [8], "mode": "filament",
                             "clear_old": True}).get_json()
    assert body["success"] is True

    row = spy.calls[0]["rows"][0]
    assert row["Temp_Nozzle"] == ""
    assert row["Temp_Bed"] == ""       # 0 is falsy -> blank, not '0°C'
    assert row["Density"] == ""
    assert row["QR_Code"] == "FIL:8"
    assert row["Brand"] == "\U0001f99d Labs"  # raccoon emoji NOT sanitized in filament mode
    assert (row["Red"], row["Green"], row["Blue"]) == ("", "", "")


def test_batch_append_reuses_existing_header_order(client, tmp_path, monkeypatch):
    """Pins the smart-header append: with clear_old=False and an existing CSV,
    the handler re-reads the file's first row and reuses its column ORDER
    (P-touch's linked .lbx template maps columns positionally at link time),
    appending the new row's values under the matching columns and silently
    dropping columns not in the existing header."""
    _mount_output(monkeypatch, tmp_path)
    _stub_label_helpers(monkeypatch)
    monkeypatch.setattr(app_module.spoolman_api, "get_filament",
                        lambda fid: FILAMENT_7 if fid == 7 else None)

    seeded = tmp_path / "labels_swatch.csv"
    seeded.write_text("QR_Code,ID,Brand\nFIL:1,1,Old\n", encoding="utf-8")

    body = client.post("/api/print_batch_csv",
                       json={"ids": [7], "mode": "filament",
                             "clear_old": False}).get_json()
    assert body["success"] is True
    assert body["msg"] == "Appended 1 items."

    assert _csv_lines(seeded) == [
        "QR_Code,ID,Brand",   # single header, ORIGINAL custom order preserved
        "FIL:1,1,Old",
        "FIL:7,7,Acme",       # new values landed under the right columns
    ]


# ===========================================================================
# 4. /api/print_batch_csv — guards + generic error branch
# ===========================================================================

def test_batch_empty_queue_and_no_valid_data_guards(client, tmp_path, monkeypatch):
    """Pins the two guard messages verbatim: empty ids short-circuits before
    any config/IO, and a batch where every lookup returns None yields
    'No valid data found' without any writer call."""
    _mount_output(monkeypatch, tmp_path)
    spy = _WriterSpy()
    monkeypatch.setattr(app_module, "_write_label_csv", spy)

    assert client.post("/api/print_batch_csv",
                       json={"ids": [], "mode": "spool"}).get_json() == {
        "success": False, "msg": "Empty Queue"}

    monkeypatch.setattr(app_module.spoolman_api, "get_spool", lambda sid: None)
    assert client.post("/api/print_batch_csv",
                       json={"ids": [1, 2], "mode": "spool",
                             "clear_old": True}).get_json() == {
        "success": False, "msg": "No valid data found"}
    assert spy.calls == []


def test_batch_generic_writer_exception_surfaces_str_and_error_log(client, tmp_path, monkeypatch):
    """Pins the generic (non-PermissionError) failure branch: response is
    {'success': False, 'msg': str(e)} with NO 'locked' flag, and an ERROR
    Activity Log entry naming the target filename fires. (The PermissionError
    branch is pinned by tests/test_label_csv_export.py.)"""
    _mount_output(monkeypatch, tmp_path)
    _stub_label_helpers(monkeypatch)
    monkeypatch.setattr(
        app_module.spoolman_api, "get_spool",
        lambda sid: {"id": sid, "remaining_weight": 500,
                     "filament": {"material": "PLA", "vendor": {"name": "Acme"},
                                  "extra": {}, "color_hex": "AABBCC"}})
    logs = _capture_logs(monkeypatch)

    def _boom(*a, **k):
        raise ValueError("boom simulated")

    monkeypatch.setattr(app_module, "_write_label_csv", _boom)

    body = client.post("/api/print_batch_csv",
                       json={"ids": [1], "mode": "spool",
                             "clear_old": True}).get_json()
    assert body["success"] is False
    assert body["msg"] == "boom simulated"
    assert "locked" not in body
    assert any(len(t) > 1 and t[1] == "ERROR"
               and "Label CSV export failed (labels_spool.csv)" in t[0]
               and "boom simulated" in t[0]
               for t in logs), logs
