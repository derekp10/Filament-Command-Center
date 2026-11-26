"""Group 63.3: the pre-archive note is text, whatever it says.

When a spool is weighed or printed to 0 g, the archive edge
(`spoolman_api._auto_archive_on_empty`) writes the place it left into the text
extra `fcc_pre_archive_location`. `JSON_STRING_FIELDS` didn't list it, so
`sanitize_outbound_data` sent a note whose text parses as JSON bare: a place named
"12" went out as the number 12, one named "TRUE" as the boolean true. Spoolman
refuses either for a text field ("Value is not a string."), and one bad extra
refuses the whole PATCH: the spool was neither archived nor weighed.

Dormant on Derek's data (no LocationID parses as a number or a boolean; checked
2026-11-16 on dev's copy of prod's rows), so this is a guard. These run the REAL
update_spool over tests/spoolman_extra_fake.SpoolmanHTTPFake, whose field check
refuses a number in a text field as Spoolman 0.27 does.

RED on dev @ e1b22f4 (the place-named-like-JSON cases): the PATCH carried `12` /
`true`, Spoolman refused it, and update_spool answered None.
"""
from __future__ import annotations

import copy
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import spoolman_api as sm_api  # noqa: E402
import state  # noqa: E402
from spoolman_extra_fake import SpoolmanHTTPFake  # noqa: E402

SPOOL_FIELDS = [
    {"key": k, "field_type": "text", "name": k} for k in (
        "container_slot", "physical_source", "physical_source_slot",
        "fcc_pre_archive_location", "fcc_pre_box_location", "fcc_pre_audit_location")
]


@pytest.fixture(autouse=True)
def _isolate_state():
    prior = (state.RECENT_LOGS, state.UNDO_STACK, state.GLOBAL_BUFFER)
    state.RECENT_LOGS, state.UNDO_STACK, state.GLOBAL_BUFFER = [], [], []
    try:
        yield
    finally:
        state.RECENT_LOGS, state.UNDO_STACK, state.GLOBAL_BUFFER = prior


@pytest.fixture
def http(monkeypatch):
    fake = SpoolmanHTTPFake(version="0.27.0", fields={"spool": copy.deepcopy(SPOOL_FIELDS)})
    monkeypatch.setattr(sm_api.config_loader, "get_api_urls", lambda: ("http://sm.test", "http://fb"))
    monkeypatch.setattr(sm_api.requests, "get", fake.get)
    monkeypatch.setattr(sm_api.requests, "patch", fake.patch)
    monkeypatch.setattr(sm_api.locations_db, "get_active_printer_map", lambda: {})
    monkeypatch.setattr(sm_api.locations_db, "load_locations_list", lambda *a, **k: [])
    for name in ("_FIELD_SCHEMA_CACHE", "_SPOOLMAN_VERSION_CACHE"):
        getattr(sm_api, name, {}).clear()
    yield fake
    for name in ("_FIELD_SCHEMA_CACHE", "_SPOOLMAN_VERSION_CACHE"):
        getattr(sm_api, name, {}).clear()


def test_the_note_is_a_listed_text_field():
    assert "fcc_pre_archive_location" in sm_api.JSON_STRING_FIELDS


@pytest.mark.parametrize("place", ["12", "TRUE", "false", "3.5", "null"],
                         ids=["number", "true", "false", "decimal", "null-word"])
def test_a_spool_on_a_place_named_like_json_is_archived_with_its_note_as_text(http, place):
    """RED on e1b22f4: the note went out bare (12, true, ...) and Spoolman refused
    the whole PATCH, so the spool stayed in stock at its place."""
    http.add("spool", 57, {}, location=place, initial_weight=1000.0, used_weight=700.0, archived=False)
    out = sm_api.update_spool(57, {"used_weight": 1000.0})
    assert out is not None, sm_api.LAST_SPOOLMAN_ERROR
    (_entity, _sid, body), = http.patches
    assert body["extra"]["fcc_pre_archive_location"] == f'"{place}"', body
    rec = http.records["spool"][57]
    assert rec["archived"] is True and rec["location"] == "", rec
    assert rec["extra"]["fcc_pre_archive_location"] == f'"{place}"', rec


def test_control_an_ordinary_place_was_always_text(http):
    """Control (green on e1b22f4 too): a place that doesn't parse as JSON was
    always wrapped as a string."""
    http.add("spool", 57, {}, location="CR-SHELF", initial_weight=1000.0, used_weight=700.0, archived=False)
    assert sm_api.update_spool(57, {"used_weight": 1000.0}) is not None, sm_api.LAST_SPOOLMAN_ERROR
    (_entity, _sid, body), = http.patches
    assert body["extra"]["fcc_pre_archive_location"] == '"CR-SHELF"', body


def test_the_archive_edge_docstring_names_its_only_caller():
    """63.3's second half: the docstring said create_spool calls the edge too;
    only update_spool does."""
    doc = sm_api._auto_archive_on_empty.__doc__ or ""
    assert "create_spool" not in doc, doc
