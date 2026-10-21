"""Clearing a Spoolman extra actually clears it, on Spoolman 0.27 and on a
Spoolman that replaces `extra` (2026-10-21).

Spoolman 0.26+ merges a PATCH's `extra` key by key: a key the PATCH leaves out is
KEPT, and only a JSON null drops one. FCC cleared an extra by leaving it out (the
23.4 delete sentinel was popped by the merge), which cleared it only where
Spoolman REPLACES `extra`: a filament's and a vendor's up to 0.25. Dev and prod
run 0.27.0, where emptying a Product Link, a max temperature or a website kept
the old value (and a spool's extra never cleared at all: spools have merged since
0.22). Now the sentinel becomes a WRITE of the value that clears the field: JSON
null for every type on a Spoolman that takes it (0.26+, read from its version),
the type's own empty value on an older one (or an unreadable version) where it
has one ('""' for text), and otherwise the key is left out (which clears it where
the PATCH replaces) and the write says so when Spoolman kept it.

Everything here runs the REAL spoolman_api.update_spool / update_filament /
update_vendor (and the routes over them) against tests/spoolman_extra_fake.py's
SpoolmanHTTPFake, which stores and validates a PATCH's extra the way each
Spoolman version does, field type by field type (as the dev probe showed).

Base proof (a worktree at 74d780a with only the test files copied in): see the
commit message for the exact count; every 0.27 clear, the
field-list / version reads, the uncleared report, `extra: null`, the
compute_dirty_extras blank forms, the reset-dev null and the stale trail slot
fail there.
"""
from __future__ import annotations

import ast
import copy
import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import spoolman_api  # noqa: E402
import state  # noqa: E402
from spoolman_extra_fake import (  # noqa: E402
    MERGE, REPLACE, SpoolmanHTTPFake, apply_extra_patch, mode_for, version_tuple,
)

SENTINEL = spoolman_api.DELETE_EXTRA_SENTINEL
REPO = Path(__file__).resolve().parents[2]

# --- Spoolman's field lists, as dev's 0.27 has them (plus one of every type) -----

FILAMENT_FIELDS = [
    {"key": "product_url", "field_type": "text", "name": "Product Page Link"},
    {"key": "sheet_link", "field_type": "text", "name": "Sheet Row Link"},
    {"key": "nozzle_temp_max", "field_type": "text", "name": "Nozzle Temp Max"},
    {"key": "fcc_t_int", "field_type": "integer", "name": "An integer"},
    {"key": "fcc_t_float", "field_type": "float", "name": "A float"},
    {"key": "fcc_t_irange", "field_type": "integer_range", "name": "An integer range"},
    {"key": "fcc_t_frange", "field_type": "float_range", "name": "A float range"},
    {"key": "fcc_t_date", "field_type": "datetime", "name": "A date"},
    {"key": "sample_printed", "field_type": "boolean", "name": "Sample Printed"},
    {"key": "slicer_profile", "field_type": "choice", "multi_choice": False,
     "choices": ["Basic PLA", "Silk PLA"], "name": "Slicer Profile"},
    {"key": "filament_attributes", "field_type": "choice", "multi_choice": True,
     "choices": ["Silk", "Matte"], "name": "Filament Attributes"},
]
FILAMENT_EXTRA = {
    "product_url": '"https://example.com/p"',
    "sheet_link": '"https://example.com/sheet"',
    "nozzle_temp_max": '"230"',
    "fcc_t_int": "42",
    "fcc_t_float": "1.5",
    "fcc_t_irange": "[1, 2]",
    "fcc_t_frange": "[1.5, 2.5]",
    "fcc_t_date": '"2026-10-21T01:02:03"',
    "sample_printed": "true",
    "slicer_profile": '"Basic PLA"',
    "filament_attributes": '["Silk"]',
}
SPOOL_FIELDS = [
    {"key": "product_url", "field_type": "text", "name": "Product Page Link"},
    {"key": "purchase_url", "field_type": "text", "name": "Purchase Link"},
    {"key": "container_slot", "field_type": "text", "name": "Container / MMU Slot"},
    {"key": "physical_source", "field_type": "text", "name": "Physical Source"},
    {"key": "physical_source_slot", "field_type": "text", "name": "Physical Source Slot"},
    {"key": "spool_type", "field_type": "choice", "multi_choice": False,
     "choices": ["Cardboard", "Plastic"], "name": "Spool Type"},
    {"key": "needs_label_print", "field_type": "boolean", "name": "Needs Label Print"},
]
SPOOL_EXTRA = {
    "product_url": '"https://example.com/s"',
    "purchase_url": '"https://example.com/buy"',
    "container_slot": '"2"',
    "spool_type": '"Plastic"',
    "needs_label_print": "true",
}
VENDOR_FIELDS = [{"key": "website", "field_type": "text", "name": "Vendor Website"}]

TYPE_OF = {f["key"]: f for f in FILAMENT_FIELDS}
UNIVERSAL_BLANK_TYPES = {"text", "datetime", "integer_range", "float_range"}   # + a multi choice


def _clearable_without_null(field):
    """A field a Spoolman older than 0.26 can still be cleared on, PATCH merging."""
    ftype = field["field_type"]
    return ftype in UNIVERSAL_BLANK_TYPES or (ftype == "choice" and field.get("multi_choice"))


def _expect_cleared(entity, field, version):
    if version_tuple(version) >= (0, 26, 0):
        return True
    if mode_for(version, entity) == REPLACE:
        return True          # leaving the key out clears it there
    return _clearable_without_null(field)


def _blank(raw):
    """Absent, or a stored value FCC reads back as blank ('""', '[]', '[null, null]').
    Its own reading, so a base without spoolman_api._extra_is_blank still runs
    the behaviour tests (and fails them on what Spoolman stored)."""
    if raw is None:
        return True
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return not str(raw).strip()
    if isinstance(data, str):
        return not data.strip()
    if isinstance(data, list):
        return all(item is None for item in data)
    return data is None


def _clear_caches():
    for name in ("_FIELD_SCHEMA_CACHE", "_SPOOLMAN_VERSION_CACHE"):
        getattr(spoolman_api, name, {}).clear()


@pytest.fixture(autouse=True)
def _fresh_caches():
    _clear_caches()
    yield
    _clear_caches()


@pytest.fixture
def logs(monkeypatch):
    calls = []
    monkeypatch.setattr(state, "add_log_entry", lambda msg, *a, **k: calls.append((msg, a[0] if a else None)))
    return calls


def _fake(version="0.27.0", **kw):
    fake = SpoolmanHTTPFake(version=version, fields={"filament": copy.deepcopy(FILAMENT_FIELDS),
                                                     "spool": copy.deepcopy(SPOOL_FIELDS),
                                                     "vendor": copy.deepcopy(VENDOR_FIELDS)}, **kw)
    fake.add("filament", 12, dict(FILAMENT_EXTRA), name="Gold", material="PLA")
    fake.add("spool", 5, dict(SPOOL_EXTRA), location="CR-SHELF", used_weight=100.0, initial_weight=1000.0)
    fake.add("vendor", 3, {"website": '"https://vendor.example"'}, name="Acme")
    return fake


def _wired(fake):
    """spoolman_api's HTTP seam on the fake."""
    return [
        patch.object(spoolman_api.config_loader, "get_api_urls", return_value=("http://sm.test", "http://fb")),
        patch.object(spoolman_api.requests, "get", side_effect=fake.get),
        patch.object(spoolman_api.requests, "patch", side_effect=fake.patch),
    ]


class _On:
    def __init__(self, fake):
        self.ctx = _wired(fake)

    def __enter__(self):
        for c in self.ctx:
            c.start()
        return self

    def __exit__(self, *exc):
        for c in reversed(self.ctx):
            c.stop()


def _no_sentinel_sent(fake):
    for _entity, _eid, body in fake.patches:
        assert SENTINEL not in repr(body), body


# --- every field type, through the REAL write functions --------------------------

FILAMENT_KEYS = [f["key"] for f in FILAMENT_FIELDS if f["key"] != "sheet_link"]
VERSIONS = ["0.27.0", "0.23.1", "0.21.0"]


@pytest.mark.parametrize("version", VERSIONS)
@pytest.mark.parametrize("key", FILAMENT_KEYS)
def test_a_filament_clear_lands_for_every_field_type(logs, key, version):
    """RED on the base for 0.27 (every type): the sentinel was popped and 0.27 keeps
    a key a PATCH leaves out. 0.23.1 / 0.21.0 replace a filament's extra, so the
    old pop cleared there too: those pin that the new writes still work there."""
    fake = _fake(version)
    with _On(fake):
        res = spoolman_api.update_filament(12, {"extra": {key: SENTINEL}})
    assert res is not None, spoolman_api.LAST_SPOOLMAN_ERROR
    stored = fake.extra("filament", 12)
    assert _blank(stored.get(key)), (key, stored.get(key))
    for other, raw in FILAMENT_EXTRA.items():
        if other != key:
            assert stored.get(other) == raw, (other, stored)          # siblings untouched
    assert "fcc_uncleared_extras" not in res, res
    _no_sentinel_sent(fake)
    if version_tuple(version) < (0, 26, 0):
        # an older Spoolman refuses a null for the whole PATCH: none is ever sent
        assert all(v is not None for _e, _i, b in fake.patches for v in (b.get("extra") or {}).values())


SPOOL_CASES = [("product_url", "text"), ("purchase_url", "text"), ("spool_type", "choice"),
               ("needs_label_print", "boolean")]


@pytest.mark.parametrize("version", VERSIONS)
@pytest.mark.parametrize("key,ftype", SPOOL_CASES)
def test_a_spool_clear_lands_or_says_it_did_not(logs, key, ftype, version):
    """A spool's extra has merged key by key since Spoolman 0.22, so the old pop
    never cleared one (RED on the base for 0.27 and for a text key on 0.23.1).
    On 0.23.1 a choice or boolean has no value that clears it and null is refused:
    the key is left out, the rest of the write lands, and the answer says so."""
    fake = _fake(version)
    field = {f["key"]: f for f in SPOOL_FIELDS}[key]
    with _On(fake):
        res = spoolman_api.update_spool(5, {"extra": {key: SENTINEL}, "comment": "edited"})
    assert res is not None, spoolman_api.LAST_SPOOLMAN_ERROR
    rec = fake.records["spool"][5]
    assert rec["comment"] == "edited"                                   # the write landed
    stored = rec["extra"]
    _no_sentinel_sent(fake)
    if _expect_cleared("spool", field, version):
        assert _blank(stored.get(key)), (key, stored)
        assert "fcc_uncleared_extras" not in res, res
    else:
        assert stored.get(key) == SPOOL_EXTRA[key], stored               # Spoolman kept it
        assert res["fcc_uncleared_extras"] == [key], res
        assert res["fcc_uncleared_note"] == (
            f"Spool #5: {field['name']} was not cleared (Spoolman 0.23.1 can't clear that kind of field; "
            f"0.26 or newer can)."), res
        assert [m for m, cat in logs if cat == "WARNING" and field["name"] in m], logs
    assert stored["container_slot"] == SPOOL_EXTRA["container_slot"]   # siblings untouched


@pytest.mark.parametrize("version", VERSIONS)
def test_a_vendor_website_clear_lands(logs, version):
    """RED on the base for 0.27 (the Manufacturer modal's emptied Website stayed)."""
    fake = _fake(version)
    with _On(fake):
        res = spoolman_api.update_vendor(3, {"name": "Acme", "extra": {"website": SENTINEL}})
    assert res is not None, spoolman_api.LAST_SPOOLMAN_ERROR
    if version_tuple(version) >= (0, 26, 0):
        assert fake.extra("vendor", 3) == {}                       # sent as null: the row is dropped
    else:
        assert fake.extra("vendor", 3) == {"website": '""'}        # no null before 0.26: a JSON empty string
    _no_sentinel_sent(fake)


def test_every_type_is_cleared_with_a_json_null_on_027(logs):
    """The exact wire values on 0.27: JSON null for every cleared key, text
    included (the row is dropped, as Spoolman's own form clears a field), and
    nothing else changes: the siblings go back as they were."""
    fake = _fake("0.27.0")
    with _On(fake):
        spoolman_api.update_filament(12, {"extra": {"product_url": SENTINEL, "sample_printed": SENTINEL,
                                                    "filament_attributes": SENTINEL,
                                                    "slicer_profile": SENTINEL}})
    [(_e, _i, body)] = fake.patches
    sent = body["extra"]
    cleared = {"product_url", "sample_printed", "filament_attributes", "slicer_profile"}
    assert {k for k, v in sent.items() if v is None} == cleared, sent  # null for exactly those keys
    assert "null" not in sent.values()                                 # never the STRING "null"
    assert {k: v for k, v in sent.items() if k not in cleared} == {
        k: v for k, v in FILAMENT_EXTRA.items() if k not in cleared}  # FCC still re-sends siblings
    stored = fake.extra("filament", 12)
    for gone in ("product_url", "sample_printed", "filament_attributes", "slicer_profile"):
        assert gone not in stored
    assert stored["sheet_link"] == FILAMENT_EXTRA["sheet_link"]


def test_an_older_spoolman_gets_each_types_own_empty_value_and_never_a_null(logs):
    """0.23.1: null is a 422 for the whole PATCH, so it is never sent; a type with
    an empty value of its own gets it, the rest are left out (a filament's PATCH
    replaces extra there, so leaving out clears)."""
    fake = _fake("0.23.1")
    keys = ["product_url", "fcc_t_date", "fcc_t_irange", "fcc_t_frange", "filament_attributes",
            "fcc_t_int", "fcc_t_float", "sample_printed", "slicer_profile"]
    with _On(fake):
        res = spoolman_api.update_filament(12, {"extra": {k: SENTINEL for k in keys}})
    assert res is not None, spoolman_api.LAST_SPOOLMAN_ERROR
    [(_e, _i, body)] = fake.patches
    sent = body["extra"]
    assert sent["product_url"] == '""' and sent["fcc_t_date"] == '""'
    assert sent["fcc_t_irange"] == "[null, null]" and sent["fcc_t_frange"] == "[null, null]"
    assert sent["filament_attributes"] == "[]"
    for left_out in ("fcc_t_int", "fcc_t_float", "sample_printed", "slicer_profile"):
        assert left_out not in sent
    assert None not in sent.values()
    assert fake.extra("filament", 12) == {**{k: v for k, v in sent.items()}}


def test_a_clear_of_an_empty_key_writes_nothing_and_reads_nothing(logs):
    fake = _fake("0.27.0")
    fake.records["filament"][12]["extra"]["sheet_link"] = '""'
    with _On(fake):
        spoolman_api.update_filament(12, {"extra": {"drying_temp": SENTINEL, "sheet_link": SENTINEL}})
    [(_e, _i, body)] = fake.patches
    assert "drying_temp" not in body["extra"] and body["extra"]["sheet_link"] == '""'
    assert not [p for p in fake.gets if p.startswith("/api/v1/field/") or p == "/api/v1/info"], fake.gets


# --- when the field list and the version are read -------------------------------

def test_the_field_list_is_read_only_for_a_clear_and_kept_briefly(logs):
    """RED on the base: it never read the field list (it popped every key)."""
    fake = _fake("0.27.0")
    with _On(fake):
        spoolman_api.update_filament(12, {"extra": {"sheet_link": '"https://example.com/new"'}})
        spoolman_api.update_spool(5, {"comment": "no extras"})
        assert [p for p in fake.gets if p.startswith("/api/v1/field/") or p == "/api/v1/info"] == []
        spoolman_api.update_filament(12, {"extra": {"product_url": SENTINEL}})
        assert fake.gets.count("/api/v1/field/filament") == 1
        assert fake.gets.count("/api/v1/info") == 1                  # null only on a Spoolman known to take it
        spoolman_api.update_filament(12, {"extra": {"sample_printed": SENTINEL}})
        spoolman_api.update_filament(12, {"extra": {"fcc_t_int": SENTINEL}})
    assert fake.gets.count("/api/v1/field/filament") == 1, fake.gets   # kept
    assert fake.gets.count("/api/v1/info") == 1, fake.gets              # kept
    stored = fake.extra("filament", 12)
    assert not {"product_url", "sample_printed", "fcc_t_int"} & set(stored), stored


def test_the_field_list_is_read_again_once_it_is_stale(logs, monkeypatch):
    fake = _fake("0.27.0")
    now = [1000.0]
    monkeypatch.setattr(spoolman_api.time, "monotonic", lambda: now[0])
    with _On(fake):
        spoolman_api.update_filament(12, {"extra": {"product_url": SENTINEL}})
        now[0] += spoolman_api._FIELD_SCHEMA_TTL_S + 1
        spoolman_api.update_filament(12, {"extra": {"sheet_link": SENTINEL}})
    assert fake.gets.count("/api/v1/field/filament") == 2, fake.gets


def _with_unlisted_fields(fake):
    """Two fields FCC doesn't register, holding values, and Spoolman's field list
    unreadable: FCC's own fields then go by its registry, these by their values."""
    fake.fields["filament"] += [{"key": "fcc_x_count", "field_type": "integer", "name": "x"},
                                {"key": "fcc_x_note", "field_type": "text", "name": "y"}]
    fake.records["filament"][12]["extra"].update({"fcc_x_count": "7", "fcc_x_note": '"hello"'})
    fake.field_reads_fail = True
    return ["sample_printed", "slicer_profile", "product_url", "fcc_x_count", "fcc_x_note"]


def test_an_unreadable_field_list_still_clears_every_type_with_null_on_027(logs):
    """0.27 takes a null for every type, so a clear needs no type at all."""
    fake = _fake("0.27.0")
    keys = _with_unlisted_fields(fake)
    with _On(fake):
        res = spoolman_api.update_filament(12, {"extra": {k: SENTINEL for k in keys}})
    assert res is not None, spoolman_api.LAST_SPOOLMAN_ERROR
    [(_e, _i, body)] = fake.patches
    assert all(body["extra"][k] is None for k in keys), body
    stored = fake.extra("filament", 12)
    assert not set(keys) & set(stored), stored
    assert "fcc_uncleared_extras" not in res


def test_an_unreadable_field_list_falls_back_to_fccs_registry_then_the_values_shape(logs):
    """0.23.1 (no null) and Spoolman's field list can't be read: FCC's own fields
    go by the registry (product_url is text: '""'; sample_printed a boolean and
    slicer_profile a choice: left out), a field FCC doesn't know by its stored
    value (a number has no empty value: left out; a string may be a single
    choice, which refuses '""': left out). A filament's PATCH replaces its extra
    on 0.23.1, so every one of them is cleared."""
    fake = _fake("0.23.1")
    keys = _with_unlisted_fields(fake)
    with _On(fake):
        res = spoolman_api.update_filament(12, {"extra": {k: SENTINEL for k in keys}})
    assert res is not None, spoolman_api.LAST_SPOOLMAN_ERROR
    [(_e, _i, body)] = fake.patches
    assert body["extra"]["product_url"] == '""'
    for left_out in ("sample_printed", "slicer_profile", "fcc_x_count", "fcc_x_note"):
        assert left_out not in body["extra"], body
    assert None not in body["extra"].values()
    stored = fake.extra("filament", 12)
    assert all(_blank(stored.get(k)) for k in keys), stored
    assert "fcc_uncleared_extras" not in res


def test_a_type_guessed_from_a_string_never_gets_an_empty_string(logs):
    """A spool field FCC doesn't register (a single choice), Spoolman's field list
    unreadable, on 0.23.1 (no null; a spool's PATCH merges there): '""' would be
    refused for the whole write ("Value is not a valid choice."), so the key is
    left out, the rest of the write lands, and the answer says it was kept."""
    fake = _fake("0.23.1")
    fake.fields["spool"] = fake.fields["spool"] + [
        {"key": "fcc_x_pick", "field_type": "choice", "multi_choice": False, "choices": ["a", "b"], "name": "Pick"}]
    fake.records["spool"][5]["extra"]["fcc_x_pick"] = '"a"'
    fake.field_reads_fail = True
    with _On(fake):
        res = spoolman_api.update_spool(5, {"extra": {"fcc_x_pick": SENTINEL}, "comment": "edited"})
    assert res is not None, spoolman_api.LAST_SPOOLMAN_ERROR
    rec = fake.records["spool"][5]
    assert rec["comment"] == "edited" and rec["extra"]["fcc_x_pick"] == '"a"', rec
    assert res["fcc_uncleared_extras"] == ["fcc_x_pick"], res
    _no_sentinel_sent(fake)


def test_an_unreadable_version_leaves_a_non_text_clear_out_and_says_so(logs):
    """Without the version FCC can't know a null is safe (an older Spoolman refuses
    the whole PATCH for one), so a boolean clear is left out: 0.27 keeps it, the
    text clear and the rest of the write land, and the answer and the log say so."""
    fake = _fake("0.27.0")
    fake.info_fails = True
    with _On(fake):
        res = spoolman_api.update_filament(12, {"extra": {"sample_printed": SENTINEL, "product_url": SENTINEL}})
    assert res is not None, spoolman_api.LAST_SPOOLMAN_ERROR
    [(_e, _i, body)] = fake.patches
    assert "sample_printed" not in body["extra"] and None not in body["extra"].values()
    stored = fake.extra("filament", 12)
    assert stored["product_url"] == '""' and stored["sample_printed"] == "true"
    assert res["fcc_uncleared_extras"] == ["sample_printed"]
    assert res["fcc_uncleared_note"] == (
        "Filament #12: Sample Printed was not cleared (FCC couldn't read Spoolman's version to pick how "
        "to clear that kind of field: try again in a moment).")
    assert [m for m, cat in logs if cat == "WARNING" and "Sample Printed was not cleared" in m], logs


def test_a_key_spoolman_does_not_list_is_left_out_not_guessed():
    plan = spoolman_api._clear_field_def("filament", "gone_key", '"x"', {"product_url": {"field_type": "text"}})
    assert plan is None
    with patch.object(spoolman_api, "_extra_field_schema", return_value={"product_url": {"field_type": "text"}}):
        clears = spoolman_api._plan_extra_clears("filament", {"gone_key": '"x"'}, {"gone_key": SENTINEL})
    assert clears == {"gone_key": spoolman_api._LEAVE_OUT}
    merged = spoolman_api._merge_extras_with_existing({"gone_key": '"x"', "a": '"1"'}, {"gone_key": SENTINEL}, clears)
    assert merged == {"a": '"1"'}


def test_a_system_managed_key_is_never_cleared_by_the_sentinel(logs):
    fake = _fake("0.27.0")
    with _On(fake):
        spoolman_api.update_spool(5, {"extra": {"container_slot": SENTINEL, "purchase_url": SENTINEL}})
    stored = fake.extra("spool", 5)
    assert stored["container_slot"] == '"2"' and "purchase_url" not in stored, stored
    [(_e, _i, body)] = fake.patches
    assert body["extra"]["container_slot"] == '"2"' and body["extra"]["purchase_url"] is None, body


def test_extra_null_is_never_sent(logs):
    """RED on the base: `"extra": None` went out as `"extra": null`, a 500 on 0.27."""
    fake = _fake("0.27.0")
    with _On(fake):
        res_s = spoolman_api.update_spool(5, {"comment": "x", "extra": None})
        res_f = spoolman_api.update_filament(12, {"comment": "y", "extra": None})
        res_v = spoolman_api.update_vendor(3, {"comment": "z", "extra": None})
    assert res_s is not None and res_f is not None and res_v is not None, spoolman_api.LAST_SPOOLMAN_ERROR
    for _e, _i, body in fake.patches:
        assert "extra" not in body, body
    assert fake.extra("spool", 5) == SPOOL_EXTRA


@pytest.mark.parametrize("mode", [MERGE, REPLACE])
def test_a_partial_write_keeps_every_sibling_either_way(logs, mode):
    fake = _fake("0.27.0", mode=mode)
    with _On(fake):
        spoolman_api.update_filament(12, {"extra": {"nozzle_temp_max": '"245"'}})
    assert fake.extra("filament", 12) == {**FILAMENT_EXTRA, "nozzle_temp_max": '"245"'}


# --- the helpers' own rules ------------------------------------------------------

@pytest.mark.parametrize("value", [None, "", "  ", '""', '" "', "[]", "[null, null]", "null", [], [None, None]])
def test_blank_values_in_either_form(value):
    assert spoolman_api._extra_is_blank(value) is True


@pytest.mark.parametrize("value", [False, 0, "false", "0", '"x"', "x", "Basic PLA", ["Silk"], '["Silk"]',
                                   "[1, 2]", [1, None], "1.5", True])
def test_values_that_are_values(value):
    assert spoolman_api._extra_is_blank(value) is False


@pytest.mark.parametrize("field,null_ok,expected", [
    ({"field_type": "text"}, True, None),
    ({"field_type": "text"}, False, '""'),
    ({"field_type": "text", "type_guessed": True}, True, None),
    ({"field_type": "datetime"}, True, None),
    ({"field_type": "choice", "multi_choice": True}, True, None),
    ({"field_type": "integer_range"}, True, None),
    ({"field_type": "integer"}, True, None),
    ({"field_type": "boolean"}, True, None),
    ({"field_type": "choice", "choices": ["a"]}, True, None),
    ({"field_type": "some_future_type"}, True, None),
    ({"field_type": "datetime"}, False, '""'),
    ({"field_type": "integer_range"}, False, "[null, null]"),
    ({"field_type": "float_range"}, False, "[null, null]"),
    ({"field_type": "choice", "multi_choice": True}, False, "[]"),
    ({"field_type": "choice", "choices": ["", "a"]}, False, '""'),
])
def test_the_clear_value_for_each_type(field, null_ok, expected):
    assert spoolman_api._clear_value(field, null_ok) == expected


@pytest.mark.parametrize("field", [{"field_type": "integer"}, {"field_type": "float"}, {"field_type": "boolean"},
                                   {"field_type": "choice", "choices": ["a"]}, {"field_type": "unknown"},
                                   {"field_type": "text", "type_guessed": True}])
def test_no_value_clears_these_before_026(field):
    assert spoolman_api._clear_value(field, False) is spoolman_api._LEAVE_OUT


def test_every_clear_value_is_one_spoolman_takes():
    """Each value _clear_value picks passes Spoolman's own check for its type."""
    for field in FILAMENT_FIELDS:
        for null_ok in (True, False):
            value = spoolman_api._clear_value(field, null_ok)
            if value is spoolman_api._LEAVE_OUT:
                continue
            apply_extra_patch({}, {field["key"]: value}, schema=TYPE_OF, nulls_ok=null_ok)


@pytest.mark.parametrize("version,takes_null", [("0.27.0", True), ("0.26.0", True), ("v0.26.1", True),
                                                ("0.26", True), ("0.25.9", False), ("0.23.1", False),
                                                ("edge", False), (None, False)])
def test_the_version_decides_whether_a_null_is_sent(version, takes_null):
    fake = SpoolmanHTTPFake(version=version or "")
    if version is None:
        fake.info_fails = True
    with _On(fake):
        assert spoolman_api._spoolman_takes_null() is takes_null


def test_the_values_shape_reads_as_a_field():
    assert spoolman_api._field_def_from_value("true") == {"field_type": "boolean"}
    assert spoolman_api._field_def_from_value("7")["field_type"] == "float"
    assert spoolman_api._field_def_from_value('["a", "b"]') == {"field_type": "choice", "multi_choice": True}
    assert spoolman_api._field_def_from_value("[1, 2]") == {"field_type": "float_range"}
    assert spoolman_api._field_def_from_value('"text"') == {"field_type": "text", "type_guessed": True}
    assert spoolman_api._field_def_from_value("not json") == {"field_type": "text", "type_guessed": True}


def test_the_merge_without_a_plan_clears_as_text():
    merged = spoolman_api._merge_extras_with_existing({"product_url": '"https://x"', "a": '"1"', "b": '""'},
                                                      {"product_url": SENTINEL, "b": SENTINEL, "c": SENTINEL})
    assert merged == {"product_url": '""', "a": '"1"', "b": '""'}


# --- compute_dirty_extras: a stored '""' reads as blank ---------------------------

@pytest.mark.parametrize("stored", ['""', "", None, "[]", [], "[null, null]"])
def test_no_spurious_clear_of_a_blank_key_in_either_form(stored):
    """RED on the base for a raw '""' / '[]' / '[null, null]': it compared str()s."""
    dirty, _ = spoolman_api.compute_dirty_extras({"product_url": stored}, {"product_url": SENTINEL})
    assert dirty == {}


@pytest.mark.parametrize("stored", [False, 0, "https://x", ["Silk"]])
def test_a_clear_of_a_held_value_is_dirty(stored):
    """RED on the base for False and 0, which read as blank there."""
    dirty, _ = spoolman_api.compute_dirty_extras({"k": stored}, {"k": SENTINEL})
    assert dirty == {"k": SENTINEL}


# --- the doors say what wasn't cleared ---------------------------------------------

@pytest.fixture
def client():
    import app as app_module
    app_module.app.config["TESTING"] = True
    return app_module.app.test_client()


def test_update_filament_route_clears_and_says_what_was_not_cleared(client, logs):
    fake = _fake("0.27.0")
    fake.info_fails = True
    with _On(fake):
        res = client.post("/api/update_filament", json={"id": 12, "data": {"extra": {
            "product_url": SENTINEL, "sample_printed": SENTINEL}}}).get_json()
    assert res["success"] is True, res
    assert res["warning"].startswith("Filament #12: Sample Printed was not cleared"), res
    line = [m for m, cat in logs if cat == "SUCCESS" and m.startswith("✏️ Filament #12 edited")][0]
    assert "extra.product_url: https://example.com/p → (cleared)" in line, line
    assert "extra.sample_printed: True → (not cleared)" in line, line
    assert fake.extra("filament", 12)["product_url"] == '""'


def test_update_filament_route_has_no_warning_when_everything_cleared(client, logs):
    fake = _fake("0.27.0")
    with _On(fake):
        res = client.post("/api/update_filament", json={"id": 12, "data": {"extra": {
            "product_url": SENTINEL, "sample_printed": SENTINEL}}}).get_json()
    assert res["success"] is True and "warning" not in res, res
    stored = fake.extra("filament", 12)
    assert "product_url" not in stored and "sample_printed" not in stored, stored


def test_vendor_route_clears_the_website(client, logs):
    fake = _fake("0.27.0")
    with _On(fake):
        res = client.patch("/api/vendors/3", json={"data": {"name": "Acme", "extra": {"website": SENTINEL}}}).get_json()
    assert res["success"] is True and "warning" not in res, res
    assert fake.extra("vendor", 3) == {}
    # (the vendor read isn't parsed, so the old value shows in its wire form)
    assert any('extra.website: "https://vendor.example" → (cleared)' in m for m, _c in logs), logs


def test_wizard_edit_clears_spool_and_filament_extras(client, logs):
    fake = _fake("0.27.0")
    with _On(fake):
        res = client.post("/api/edit_spool_wizard", json={
            "spool_id": 5, "filament_id": 12,
            "spool_data": {"location": "CR-SHELF", "extra": {"purchase_url": SENTINEL, "product_url": SENTINEL}},
            "filament_data": {"extra": {"nozzle_temp_max": SENTINEL, "slicer_profile": SENTINEL,
                                        "fcc_t_date": SENTINEL}},
        }).get_json()
    assert res["success"] is True and "warning" not in res, res
    spool = fake.extra("spool", 5)
    assert "purchase_url" not in spool and "product_url" not in spool, spool
    assert spool["container_slot"] == '"2"'                                  # untouched
    fil = fake.extra("filament", 12)
    assert not {"nozzle_temp_max", "slicer_profile", "fcc_t_date"} & set(fil), fil


def test_wizard_edit_passes_on_what_spoolman_kept(client, logs):
    """0.23.1 can't clear a spool's choice field: the Save says so (the page
    toasts `warning` at 7 s), and the rest of it is saved."""
    fake = _fake("0.23.1")
    with _On(fake):
        res = client.post("/api/edit_spool_wizard", json={
            "spool_id": 5, "spool_data": {"location": "CR-SHELF",
                                          "extra": {"spool_type": SENTINEL, "purchase_url": SENTINEL}},
        }).get_json()
    assert res["success"] is True, res
    assert "Spool #5: Spool Type was not cleared" in res["warning"], res
    spool = fake.extra("spool", 5)
    assert spool["purchase_url"] == '""' and spool["spool_type"] == '"Plastic"'


# --- reset-dev drops the keys a sweep added ------------------------------------------

@pytest.fixture
def reset_dev():
    import importlib.util
    path = REPO / "setup-and-rebuild" / "reset_dev.py"
    spec = importlib.util.spec_from_file_location("reset_dev_027", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_reset_dev_restore_drops_a_key_a_sweep_added_and_is_idempotent(reset_dev):
    """RED on the base: the seed's dict alone left container_slot / physical_source
    on a 0.27 spool, and the next run found the same drift."""
    seed = {"id": 5, "location": "CR-SHELF", "archived": False, "extra": {"container_slot": '""'}}
    fake = SpoolmanHTTPFake(version="0.27.0", fields={"spool": SPOOL_FIELDS})
    fake.add("spool", 5, {"container_slot": '"2"', "physical_source": '"LR-MDB-1"'},
             location="CR-SHELF", archived=False)
    payload = reset_dev._drifted_payload("spool", seed, fake.records["spool"][5])
    assert payload == {"extra": {"container_slot": '""', "physical_source": None}}
    assert fake.patch("http://sm/api/v1/spool/5", json=payload).ok
    assert fake.extra("spool", 5) == {"container_slot": '""'}
    assert reset_dev._drifted_payload("spool", seed, fake.records["spool"][5]) == {}


def test_reset_dev_sends_no_null_to_an_older_spoolman(reset_dev, monkeypatch):
    monkeypatch.setattr(reset_dev, "NULL_CLEARS", False)
    seed = {"id": 9, "extra": {"website": '""'}}
    live = {"id": 9, "extra": {"website": '""', "junk_key": '"oops"'}}
    assert reset_dev._drifted_payload("vendor", seed, live) == {"extra": {"website": '""'}}


@pytest.mark.parametrize("version,expected", [("0.27.0", True), ("0.26.0", True), ("0.25.0", False),
                                              ("0.23.1", False), (None, True), ("?", True)])
def test_reset_dev_reads_whether_its_spoolman_takes_a_null(reset_dev, version, expected):
    assert reset_dev._null_clears_for(version) is expected


# --- the move engine's trail never keeps a stale slot --------------------------------

def test_ghost_trail_slot_is_blank_not_none():
    """RED on the base: None, which update_spool drops (keep)."""
    import logic
    assert logic._ghost_trail_from("CR-SHELF", {}, {}, {}) == ("CR-SHELF", "")
    assert logic._ghost_trail_from("LR-MDB-1", {"container_slot": "2"}, {}, {}) == ("LR-MDB-1", "2")


def test_a_spool_from_a_shelf_onto_a_head_keeps_no_stale_trail_slot():
    """A spool on a shelf (no container_slot) still carrying an old
    physical_source_slot: loading it onto XL-1 records the shelf as its home with
    no slot. RED on the base: the old slot 3 stayed under the new trail."""
    import logic  # noqa: F401
    from move_engine_harness import IDLE, LocationsStore, WireSpoolman, run_move
    rows = [
        {"LocationID": "LR", "Type": "Room", "Max Spools": "0"},
        {"LocationID": "XL", "Type": "Printer", "Max Spools": "0", "parent_id": "LR",
         "toolheads": [{"location_id": "XL-1", "position": 0}]},
        {"LocationID": "XL-1", "Type": "Tool Head", "Max Spools": "1", "parent_id": "XL"},
        {"LocationID": "CR-SHELF", "Type": "Shelf", "Max Spools": "12", "parent_id": "LR"},
    ]
    printer_map = {"XL-1": {"printer_name": "XL", "position": 0}}
    sm = WireSpoolman({57: {"location": "CR-SHELF", "extra": {"physical_source_slot": "3"}}})
    prior = (state.RECENT_LOGS, state.UNDO_STACK, state.GLOBAL_BUFFER)
    state.RECENT_LOGS, state.UNDO_STACK, state.GLOBAL_BUFFER = [], [], []
    try:
        res = run_move(sm, probe=IDLE, store=LocationsStore(rows), printer_map=printer_map,
                       target="XL-1", raw_spools=[57], origin="buffer", confirm_active_print=[])
    finally:
        state.RECENT_LOGS, state.UNDO_STACK, state.GLOBAL_BUFFER = prior
    assert res["status"] == "success" and not res.get("failures"), res
    rec = sm.spools[57]
    assert rec["location"] == "XL-1", rec
    assert rec["extra"]["physical_source"] == "CR-SHELF", rec
    assert rec["extra"]["physical_source_slot"] == "", rec


# --- FCC's registry of its own fields matches setup_fields.py ------------------------

def _setup_fields_registry():
    """{entity: {key: (type, multi)}} from setup_fields.py's create_field calls and
    its filament_standards list, minus the fields it deletes."""
    tree = ast.parse((REPO / "setup-and-rebuild" / "setup_fields.py").read_text(encoding="utf-8"))
    out = {"spool": {}, "filament": {}, "vendor": {}}
    standards = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(getattr(t, "id", None) == "filament_standards" for t in node.targets):
            standards = [tuple(c.value for c in elt.elts) for elt in node.value.elts]
        if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "create_field":
            args = [a.value if isinstance(a, ast.Constant) else None for a in node.args]
            if len(args) >= 4 and all(isinstance(a, str) for a in args[:4]):
                kw = {k.arg: k.value for k in node.keywords}
                multi = bool(getattr(kw.get("multi"), "value", False))
                out[args[0]][args[1]] = (args[3], multi)
    for key, _name, ftype in standards:
        out["filament"][key] = (ftype, False)
    return out


def test_fccs_field_registry_matches_setup_fields():
    expected = _setup_fields_registry()
    for entity, key, _name, ftype in (
            [("filament",) + t for t in spoolman_api.REQUIRED_FILAMENT_EXTRAS]
            + [("spool",) + t for t in spoolman_api.REQUIRED_SPOOL_EXTRAS]
            + [("vendor",) + t for t in spoolman_api.REQUIRED_VENDOR_EXTRAS]):
        expected[entity].setdefault(key, (ftype, False))
    actual = {entity: {key: (ftype, (entity, key) in spoolman_api._FCC_MULTI_CHOICE_EXTRAS)
                       for key, ftype in keys.items()}
              for entity, keys in spoolman_api._FCC_EXTRA_FIELD_TYPES.items()}
    assert actual == expected
