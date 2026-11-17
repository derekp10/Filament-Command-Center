"""Group 54.3 — `_parse_filament_attrs_value` splits a comma list.

The one parser of a filament's `filament_attributes` read a string that isn't
JSON ('Silk, Matte') as ONE pseudo-tag, and so did a JSON string ('"Silk, Matte"',
what a text-type field leaves behind). Where that pseudo-tag went:
  - the attribute report counted Silk and Matte 0 and listed a rogue "Silk, Matte";
  - sweep_unused read Silk and Matte as unused, so it offered to delete two tags
    in use;
  - bulk add / remove and a purge's restore wrote ["Silk, Matte"] back, which
    Spoolman 0.27 refuses as not a choice (in a purge that filament lost its
    attributes);
  - the remove / hide carrier scan, the boot cleanup and the attribute search
    read it the same way.

Now such a string is a comma list: split on commas, each piece trimmed, blanks
and repeats dropped (the first kept). A list, JSON or parsed, is the multi-choice
shape and is returned as it was, its items never split (an item with a comma
could only be a real choice). A JSON string that holds a JSON list (encoded
twice) is that list (Claude's call). None, '', other types and a JSON number keep
their old results. Dormant: Spoolman 0.27 checks every write to the multi-choice
field, so only an old record can hold such a value.

Base proof (013f56e): every test marked RED fails there; the controls pass.
"""
from __future__ import annotations

import copy
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import attr_migration  # noqa: E402
import spoolman_api  # noqa: E402
from spoolman_extra_fake import SpoolmanHTTPFake  # noqa: E402
from test_l316_charact_filament_attributes_unit import (  # noqa: E402
    _attr_field,
    _capture_logs,
    _install_wire,
    client,  # noqa: F401  (pytest fixture, imported for use)
)

parse = spoolman_api._parse_filament_attrs_value


# ---- the parser -----------------------------------------------------------------------------------------

@pytest.mark.parametrize("raw, want", [
    ("Silk, Matte", ["Silk", "Matte"]),
    ('"Silk, Matte"', ["Silk", "Matte"]),
    ("Silk,Matte,", ["Silk", "Matte"]),
    (" Silk , Silk ", ["Silk"]),
    ('" Silk ,, Matte , Silk"', ["Silk", "Matte"]),
    ('""', []),
    ("  ", []),
], ids=["raw-text", "json-text", "trailing-comma", "repeat", "json-text-messy", "json-empty", "blank"])
def test_a_comma_list_in_a_string_is_split(raw, want):
    """RED on the base: each came back as one pseudo-tag ('' and '  ' included)."""
    assert parse(raw) == want


def test_a_list_encoded_twice_is_that_list():
    """A JSON string holding a JSON list (a list once written through a text
    field) is that list, never split into '["Silk"' and '"Matte"]'. RED on the
    base: one pseudo-tag, the list's text."""
    assert parse(json.dumps(json.dumps(["Silk", "Matte"]))) == ["Silk", "Matte"]


@pytest.mark.parametrize("raw, want", [
    ('["Silk, Matte"]', ["Silk, Matte"]),
    ('["+", "Silk"]', ["+", "Silk"]),
    (["Silk, Matte", "Glow"], ["Silk, Matte", "Glow"]),
    (None, []),
    ("", []),
    (42, []),
    ({"Silk": True}, []),
    ("7", ["7"]),
    ('"Silk"', ["Silk"]),
    ("Silk", ["Silk"]),
], ids=["json-list-one-item", "json-list", "parsed-list", "none", "empty", "number", "dict",
        "json-number", "json-text-one", "raw-one"])
def test_control_lists_and_odd_values_read_as_before(raw, want):
    """Control (green on the base too): a list's items are never split, and the
    other shapes keep their old results."""
    assert parse(raw) == want


# ---- the attribute report and the sweep (the spec's route harness) --------------------------------------

FIELDS = [_attr_field(["Silk", "Matte", "Glow"])]
FILAMENTS = [
    {"id": 1, "name": "Old text", "material": "PLA", "extra": {"filament_attributes": "Silk, Matte"}},
    {"id": 2, "name": "Proper", "material": "PLA", "extra": {"filament_attributes": '["Silk"]'}},
]


@pytest.fixture
def no_hidden(monkeypatch):
    """No choice hidden: the hidden list is a file on disk (attr_migration), and
    dev's must not decide these counts."""
    monkeypatch.setattr(attr_migration, "load_hidden_choices", lambda: [])


def test_the_report_counts_each_tag_of_a_comma_list(client, monkeypatch, no_hidden):
    """RED on the base: Silk 1, Matte 0, and a rogue "Silk, Matte"."""
    _install_wire(monkeypatch, fields=FIELDS, filaments=copy.deepcopy(FILAMENTS))
    body = client.get("/api/filament_attributes/report").get_json()
    assert body["success"] is True, body
    assert body["counts"] == {"Silk": 2, "Matte": 1, "Glow": 0}, body
    assert not body.get("rogue_counts"), body
    row = next(f for f in body["filaments"] if f["id"] == 1)
    assert row["attributes"] == ["Silk", "Matte"], row


def test_the_sweep_preview_no_longer_offers_a_tag_in_use(client, monkeypatch, no_hidden):
    """RED on the base: it offered Matte (held only by the comma list) for
    deletion beside Glow."""
    calls = _install_wire(monkeypatch, fields=FIELDS, filaments=copy.deepcopy(FILAMENTS))
    body = client.post("/api/filament_attributes/sweep_unused", json={}).get_json()
    assert body["success"] is True, body
    assert body["unused"] == ["Glow"], body
    assert not [m for (m, _u, _j) in calls if m in ("DELETE", "PATCH", "POST")], calls


# ---- the next write mends the record (the real update_filament over a Spoolman 0.27) ---------------------

@pytest.mark.parametrize("stored", ['"Silk, Matte"', "Silk, Matte"], ids=["json-text", "raw-text"])
def test_a_bulk_add_writes_the_valid_list_and_mends_the_record(client, monkeypatch, stored):
    """Bulk add Glow to a filament whose attributes are the comma list: the PATCH
    carries ["Silk", "Matte", "Glow"], which Spoolman 0.27 takes, so the record is
    mended. RED on the base: it sent ["Silk, Matte", "Glow"], Spoolman refused it
    as not a choice, and the add failed."""
    fake = SpoolmanHTTPFake(version="0.27.0", fields={"filament": copy.deepcopy(FIELDS)})
    fake.add("filament", 1, {"filament_attributes": stored}, name="Old text", material="PLA")
    monkeypatch.setattr(spoolman_api.config_loader, "get_api_urls", lambda: ("http://sm.test", "http://fb"))
    monkeypatch.setattr(spoolman_api.requests, "get", fake.get)
    monkeypatch.setattr(spoolman_api.requests, "patch", fake.patch)
    for name in ("_FIELD_SCHEMA_CACHE", "_SPOOLMAN_VERSION_CACHE"):
        getattr(spoolman_api, name, {}).clear()
    _capture_logs(monkeypatch)
    body = client.post("/api/filament_attributes/bulk_set",
                       json={"filament_ids": [1], "add": ["Glow"]}).get_json()
    assert body["success"] is True and body["updated"] == 1 and not body["errors"], body
    assert json.loads(fake.records["filament"][1]["extra"]["filament_attributes"]) == ["Silk", "Matte", "Glow"]
