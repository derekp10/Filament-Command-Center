"""Group 54.4 — `migrate_container_slot_to_text`, the type-migration template.

`setup-and-rebuild/setup_fields.py` runs on every prod deploy (`update.sh`), with
FCC still running. Its `migrate_container_slot_to_text` is dormant (it returns
while `container_slot` is already `text`, as it is on dev and prod), but CLAUDE.md
names it as the template for any future type migration: snapshot every value,
delete and re-create the field (a field DELETE drops that extra from every
record), restore. The planning pass's probe found three defects in it:

  - the snapshot listed `/api/v1/spool` without `allow_archived=true`, so an
    archived spool's slot was never snapshotted and was lost on any Spoolman;
  - the restore sent the OLD type's value into the new `text` field, so an
    integer field's `2` was refused ("Value is not a string.") and every value
    of a real type change was lost;
  - the restore was the partial `{"extra": {"container_slot": value}}`, which on
    a Spoolman before 0.22 (a spool PATCH replaced the whole `extra`) wiped every
    sibling extra of every restored spool.

Now: archived spools are snapshotted too; every value is put in the new type's
wire form before anything is deleted (`_as_text_wire`); and each spool is restored
through a fresh read-merge-write of its whole `extra`. That read also takes one
last look before the write: a spool deleted since counts "gone", one given a slot
value since the rebuild (FCC wrote it) or moved since the snapshot is left as it
is ("kept"), and one that can't be read is sent nothing ("failed"). A write that
reports failure is read again before it is called failed (a timeout is a READ
timeout). Every value not restored for a failure is printed, so it can be put back
by hand, and so is every value when the rebuild itself fails after the delete.

The real `migrate_container_slot_to_text` runs on `FieldFake`, the shared
`tests/spoolman_extra_fake.SpoolmanHTTPFake` plus Spoolman's field DELETE and POST.

Base proof (224bc63): every test marked RED fails there; the controls pass.
"""
from __future__ import annotations

import copy
import json
import os
import re
import sys
from unittest.mock import patch
from urllib.parse import urlencode, urlsplit

import pytest
import requests

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from spoolman_extra_fake import SpoolmanHTTPFake, _Resp  # noqa: E402
from test_setup_fields_idempotent import _load_setup_fields  # noqa: E402

SLOT = "container_slot"


class _Unreadable:
    """A 200 whose body isn't JSON."""
    status_code = 200
    ok = True
    text = "<html>not JSON</html>"

    def json(self):
        raise ValueError("Expecting value: line 1 column 1 (char 0)")


class FieldFake(SpoolmanHTTPFake):
    """SpoolmanHTTPFake plus Spoolman's field DELETE and POST, as setup_fields
    drives them, and a few ways for a test to make one call go wrong.

    DELETE /api/v1/field/<entity>/<key> drops the field from the field list and
    its value from every record of that entity, archived ones included (Spoolman
    keeps extras in a child table, so the delete is key-scoped). POST adds the
    field, or updates it. `get` turns requests' `params` into the query string
    the base class reads (`allow_archived=true`).

    `read_fails`: spool ids whose own GET answers 503. `patch_refused`: spool ids
    whose PATCH answers 500 with nothing stored. `patch_times_out`: spool ids
    whose PATCH lands and then raises, as a read timeout does. `post_fails` /
    `delete_fails`: the field POST / DELETE answers 500. `on_post`: runs right
    after the field POST, standing in for FCC writing in the window between the
    rebuild and the restore. `list_unreadable`: the spool list's 200 isn't JSON."""

    def __init__(self, **kw):
        super().__init__(**kw)
        self.events = []
        self.read_fails = set()
        self.patch_refused = set()
        self.patch_times_out = set()
        self.post_fails = False
        self.delete_fails = False
        self.on_post = None
        self.list_unreadable = False

    @staticmethod
    def _path(url):
        return urlsplit(str(url)).path.rstrip("/")

    def get(self, url, params=None, timeout=None, **kw):
        if params:
            url = f"{url}?{urlencode(params)}"
        path = self._path(url)
        self.events.append(("GET", path, urlsplit(str(url)).query))
        m = re.fullmatch(r"/api/v1/spool/(\d+)", path)
        if m and int(m.group(1)) in self.read_fails:
            return _Resp(503, {"message": "unavailable (test)"})
        if path == "/api/v1/spool" and self.list_unreadable:
            return _Unreadable()
        return super().get(url, timeout=timeout, **kw)

    def delete(self, url, timeout=None, **kw):
        path = self._path(url)
        self.events.append(("DELETE", path, ""))
        m = re.fullmatch(r"/api/v1/field/(spool|filament|vendor)/([^/]+)", path)
        if not m:
            return _Resp(404, {"message": "no such route (test)"})
        if self.delete_fails:
            return _Resp(500, {"message": "database is locked (test)"})
        entity, key = m.groups()
        fields = self.fields.get(entity, [])
        if not any(f["key"] == key for f in fields):
            return _Resp(404, {"message": f"Field {key} not found."})
        self.fields[entity] = [f for f in fields if f["key"] != key]
        for rec in self.records[entity].values():
            rec["extra"].pop(key, None)
        return _Resp(200, copy.deepcopy(self.fields[entity]))

    def post(self, url, json=None, timeout=None, **kw):  # noqa: A002 — requests' kwarg
        path = self._path(url)
        self.events.append(("POST", path, ""))
        m = re.fullmatch(r"/api/v1/field/(spool|filament|vendor)/([^/]+)", path)
        if not m:
            return _Resp(404, {"message": "no such route (test)"})
        if self.post_fails:
            return _Resp(500, {"message": "database is locked (test)"})
        entity, key = m.groups()
        field = {"key": key, **copy.deepcopy(json or {})}
        self.fields[entity] = [f for f in self.fields.get(entity, []) if f["key"] != key] + [field]
        if self.on_post:
            self.on_post(self)
        return _Resp(200, copy.deepcopy(self.fields[entity]))

    def patch(self, url, json=None, timeout=None, **kw):  # noqa: A002 — requests' kwarg
        path = self._path(url)
        self.events.append(("PATCH", path, ""))
        m = re.fullmatch(r"/api/v1/spool/(\d+)", path)
        sid = int(m.group(1)) if m else None
        if sid in self.patch_refused:
            self.patches.append(("spool", sid, copy.deepcopy(json)))
            return _Resp(500, {"message": "database is locked (test)"})
        resp = super().patch(url, json=json, timeout=timeout, **kw)
        if sid in self.patch_times_out:
            raise requests.exceptions.ReadTimeout("Read timed out. (read timeout=10) (test)")
        return resp

    # --- what a test reads back ---
    def slot(self, sid):
        return self.records["spool"][sid]["extra"].get(SLOT)

    def field_type(self, key=SLOT):
        for f in self.fields.get("spool", []):
            if f["key"] == key:
                return f.get("field_type")
        return None

    def patched_ids(self):
        return [eid for entity, eid, _body in self.patches if entity == "spool"]

    def deleted(self):
        return [e for e in self.events if e[0] == "DELETE"]


def _fake(old_type="choice", version="0.27.0"):
    """A Spoolman whose spool `container_slot` is still `old_type`, beside a
    boolean sibling extra, as on an install that predates the text type."""
    slot_field = {"key": SLOT, "name": "Container / MMU Slot", "field_type": old_type}
    if old_type == "choice":
        slot_field.update({"multi_choice": False, "choices": ["1", "2", "3", "4"]})
    return FieldFake(version=version, fields={"spool": [
        slot_field,
        {"key": "needs_label_print", "name": "Needs Label Print", "field_type": "boolean"},
    ]})


@pytest.fixture(scope="module")
def setup_fields_mod():
    return _load_setup_fields()


def _run(mod, fake, capsys):
    """Run the REAL migration with every HTTP call answered by `fake`; return
    what it printed."""
    capsys.readouterr()
    with patch.object(mod.requests, "get", side_effect=fake.get), \
         patch.object(mod.requests, "delete", side_effect=fake.delete), \
         patch.object(mod.requests, "post", side_effect=fake.post), \
         patch.object(mod.requests, "patch", side_effect=fake.patch):
        mod.migrate_container_slot_to_text()
    return capsys.readouterr().out


# ---- the value converter ------------------------------------------------------------------------

@pytest.mark.parametrize("raw, expected", [
    ('"2"', '"2"'),                       # a JSON string stays as it is
    ('"LR-MDB-1:2"', '"LR-MDB-1:2"'),
    (' "2" ', '"2"'),                     # ...less the space around it
    ("2", '"2"'),                         # an integer field's value, as text
    ("2.50", '"2.50"'),                   # a number keeps the text it was stored as
    ("true", '"true"'),                   # JSON's own word, not Python's "True"
    ("[1, 2]", '"[1, 2]"'),               # any other JSON: its own text
    ("slot 2", '"slot 2"'),               # text that isn't JSON: that text
    ("null", None),                       # nothing to keep
    ("", None),
    ("   ", None),
    ('""', None),
    ('"  "', None),
    (None, None),
])
def test_as_text_wire(setup_fields_mod, raw, expected):
    """RED on the base (no helper). Every value comes out as a JSON string a `text`
    field takes, or None when there is nothing to keep."""
    assert setup_fields_mod._as_text_wire(raw) == expected


def test_as_text_wire_answers_what_a_text_field_takes(setup_fields_mod):
    """Each converted value passes Spoolman's own check for a `text` field."""
    from spoolman_extra_fake import check_value
    for raw in ('"2"', "2", "2.5", "true", "false", "[1, 2]", '{"a": 1}', "slot 2", "LR-MDB-1:2"):
        check_value({"field_type": "text"}, setup_fields_mod._as_text_wire(raw))


# ---- the spec's six cases (a) to (f) --------------------------------------------------------------

def test_a_sibling_extras_survive_on_a_spoolman_whose_patch_replaces_extra(setup_fields_mod, capsys):
    """(a) RED. Spoolman 0.21.0: a spool PATCH's `extra` replaces the stored one, so
    the old partial restore `{"extra": {"container_slot": ...}}` wiped every
    sibling extra of every restored spool."""
    fake = _fake(version="0.21.0")
    fake.add("spool", 1, location="LR-MDB-1", extra={SLOT: '"2"', "needs_label_print": "true"})
    _run(setup_fields_mod, fake, capsys)
    assert fake.field_type() == "text"
    assert fake.records["spool"][1]["extra"] == {SLOT: '"2"', "needs_label_print": "true"}


def test_b_an_archived_spools_slot_is_restored(setup_fields_mod, capsys):
    """(b) RED. The snapshot listed spools without `allow_archived=true`, so an
    archived spool's slot was never snapshotted, and the field DELETE dropped it."""
    fake = _fake()
    fake.add("spool", 1, location="LR-MDB-1", extra={SLOT: '"2"'})
    fake.add("spool", 2, location="LR-MDB-1", archived=True, extra={SLOT: '"3"'})
    out = _run(setup_fields_mod, fake, capsys)
    assert fake.slot(1) == '"2"'
    assert fake.slot(2) == '"3"', out
    snapshot_reads = [q for verb, path, q in fake.events if verb == "GET" and path == "/api/v1/spool"]
    assert snapshot_reads == ["allow_archived=true"], fake.events


def test_c_an_integer_fields_value_is_restored_as_text(setup_fields_mod, capsys):
    """(c) RED. The restore sent the old type's `2` into the new text field, which
    Spoolman refuses ("Value is not a string."): every value of a real type change
    was lost, and the run said "0 restored, 1 failed"."""
    fake = _fake(old_type="integer")
    fake.add("spool", 1, location="LR-MDB-1", extra={SLOT: "2", "needs_label_print": "false"})
    out = _run(setup_fields_mod, fake, capsys)
    assert fake.slot(1) == '"2"', out
    assert fake.records["spool"][1]["extra"]["needs_label_print"] == "false"
    assert "1 restored, 0 kept, 0 gone, 0 failed" in out, out


def test_d_a_slot_written_after_the_rebuild_is_kept(setup_fields_mod, capsys):
    """(d) RED. FCC keeps running through the deploy: a move in the window between
    the rebuild and the restore writes a newer slot, which the old restore
    overwrote with the snapshot's."""
    fake = _fake()
    fake.add("spool", 1, location="LR-MDB-1", extra={SLOT: '"2"'})
    fake.add("spool", 3, location="LR-MDB-2", extra={SLOT: '"1"'})
    fake.on_post = lambda f: f.records["spool"][1]["extra"].__setitem__(SLOT, '"4"')
    out = _run(setup_fields_mod, fake, capsys)
    assert fake.slot(1) == '"4"', out
    assert 1 not in fake.patched_ids()
    assert fake.slot(3) == '"1"'
    assert "1 restored, 1 kept, 0 gone, 0 failed" in out, out


def test_e_a_spool_that_cant_be_read_again_is_sent_nothing(setup_fields_mod, capsys):
    """(e) RED (the new rule). A failed re-read sends no PATCH for that spool (never a
    partial `extra`), the others still restore, and the value not restored is
    printed so it can be put back by hand."""
    fake = _fake()
    fake.add("spool", 1, location="LR-MDB-1", extra={SLOT: '"2"', "needs_label_print": "true"})
    fake.add("spool", 3, location="LR-MDB-2", extra={SLOT: '"1"'})
    fake.read_fails = {1}
    out = _run(setup_fields_mod, fake, capsys)
    assert 1 not in fake.patched_ids(), fake.patches
    assert fake.slot(3) == '"1"'
    assert fake.records["spool"][1]["extra"] == {"needs_label_print": "true"}
    assert "1 restored, 0 kept, 0 gone, 1 failed" in out, out
    assert re.search(r"#1: 2 \(at LR-MDB-1\)", out), out


def test_f_control_a_string_value_on_spoolman_0_27(setup_fields_mod, capsys):
    """(f) Control, green on the base too: Spoolman 0.27 merges a spool PATCH's extra,
    and a JSON string is already what a text field takes."""
    fake = _fake()
    fake.add("spool", 1, location="LR-MDB-1", extra={SLOT: '"2"', "needs_label_print": "true"})
    fake.add("spool", 4, location="CR-SHELF", extra={"needs_label_print": "false"})
    _run(setup_fields_mod, fake, capsys)
    assert fake.field_type() == "text"
    assert fake.records["spool"][1]["extra"] == {SLOT: '"2"', "needs_label_print": "true"}
    assert fake.records["spool"][4]["extra"] == {"needs_label_print": "false"}
    assert 4 not in fake.patched_ids()


# ---- the last look before each write ---------------------------------------------------------------

def test_a_blank_slot_written_since_the_rebuild_is_kept(setup_fields_mod, capsys):
    """RED. A move to a place with no slot writes `container_slot` as "" since the
    rebuild: the key is there, so that newer write stands and the old slot doesn't
    come back over it."""
    fake = _fake()
    fake.add("spool", 1, location="LR-MDB-1", extra={SLOT: '"2"'})
    fake.on_post = lambda f: f.records["spool"][1]["extra"].__setitem__(SLOT, '""')
    out = _run(setup_fields_mod, fake, capsys)
    assert fake.slot(1) == '""', out
    assert 1 not in fake.patched_ids()
    assert "0 restored, 1 kept, 0 gone, 0 failed" in out, out


def test_a_spool_moved_since_the_snapshot_is_left_as_it_is(setup_fields_mod, capsys):
    """RED. A spool that is somewhere else now than at the snapshot doesn't get its old
    slot back: the slot was a place in the box it has left."""
    fake = _fake()
    fake.add("spool", 1, location="LR-MDB-1", extra={SLOT: '"2"'})
    fake.add("spool", 3, location="LR-MDB-2", extra={SLOT: '"1"'})
    fake.on_post = lambda f: f.records["spool"][1].__setitem__("location", "CR-SHELF")
    out = _run(setup_fields_mod, fake, capsys)
    assert fake.slot(1) is None, out
    assert 1 not in fake.patched_ids()
    assert fake.slot(3) == '"1"'
    assert "1 restored, 1 kept, 0 gone, 0 failed" in out, out
    assert "LR-MDB-1" in out and "CR-SHELF" in out, out


def test_a_spool_deleted_since_the_snapshot_counts_as_gone(setup_fields_mod, capsys):
    """RED. A spool deleted in the window is sent nothing and isn't a failure."""
    fake = _fake()
    fake.add("spool", 1, location="LR-MDB-1", extra={SLOT: '"2"'})
    fake.add("spool", 3, location="LR-MDB-2", extra={SLOT: '"1"'})
    fake.on_post = lambda f: f.records["spool"].pop(1)
    out = _run(setup_fields_mod, fake, capsys)
    assert 1 not in fake.patched_ids()
    assert fake.slot(3) == '"1"'
    assert "1 restored, 0 kept, 1 gone, 0 failed" in out, out


def test_a_restore_that_timed_out_but_landed_counts_as_restored(setup_fields_mod, capsys):
    """RED. A PATCH's timeout is a READ timeout, so the write may have landed: the
    spool is read again before the restore is called failed."""
    fake = _fake()
    fake.add("spool", 1, location="LR-MDB-1", extra={SLOT: '"2"', "needs_label_print": "true"})
    fake.patch_times_out = {1}
    out = _run(setup_fields_mod, fake, capsys)
    assert fake.slot(1) == '"2"'
    assert "1 restored, 0 kept, 0 gone, 0 failed" in out, out
    assert "#1: 2" not in out, out


def test_a_refused_restore_is_counted_failed_and_its_value_printed(setup_fields_mod, capsys):
    """RED. A restore Spoolman refuses is a failure, said with Spoolman's answer, and
    the value it couldn't put back is printed, since Spoolman no longer holds it."""
    fake = _fake()
    fake.add("spool", 1, location="LR-MDB-1", extra={SLOT: '"2"'})
    fake.add("spool", 3, location="LR-MDB-2", extra={SLOT: '"1"'})
    fake.patch_refused = {1}
    out = _run(setup_fields_mod, fake, capsys)
    assert fake.slot(1) is None
    assert fake.slot(3) == '"1"'
    assert "database is locked" in out, out
    assert "1 restored, 0 kept, 0 gone, 1 failed" in out, out
    assert re.search(r"#1: 2 \(at LR-MDB-1\)", out), out
    assert "#3: 1" not in out, out


def test_a_value_that_isnt_json_is_restored_as_text(setup_fields_mod, capsys):
    """RED. A value from before Spoolman checked one (text that isn't JSON) was sent
    back as it was, which Spoolman refuses ("Value is not valid JSON.")."""
    fake = _fake(old_type="integer")
    fake.add("spool", 1, location="LR-MDB-1", extra={SLOT: "slot 2"})
    out = _run(setup_fields_mod, fake, capsys)
    assert fake.slot(1) == '"slot 2"', out
    assert "1 restored, 0 kept, 0 gone, 0 failed" in out, out


def test_a_null_value_is_nothing_to_restore(setup_fields_mod, capsys):
    """RED. A JSON null holds no slot: it isn't snapshotted, so no PATCH is sent for it
    and nothing fails (the base sent "null" back and Spoolman refused it)."""
    fake = _fake(old_type="integer")
    fake.add("spool", 1, location="LR-MDB-1", extra={SLOT: "null"})
    fake.add("spool", 3, location="LR-MDB-2", extra={SLOT: "1"})
    out = _run(setup_fields_mod, fake, capsys)
    assert fake.patched_ids() == [3], fake.patches
    assert fake.slot(3) == '"1"'
    assert "1 restored, 0 kept, 0 gone, 0 failed" in out, out


# ---- when the rebuild itself fails ------------------------------------------------------------------

def test_a_rebuild_that_fails_after_the_delete_prints_every_value(setup_fields_mod, capsys):
    """RED. The field was deleted (so Spoolman no longer holds a single value) and
    then couldn't be created again: every snapshotted value is printed, to be put
    back by hand (or from the backup the deploy takes first)."""
    fake = _fake()
    fake.add("spool", 1, location="LR-MDB-1", extra={SLOT: '"2"'})
    fake.add("spool", 2, location="LR-MDB-1", archived=True, extra={SLOT: '"3"'})
    fake.post_fails = True
    out = _run(setup_fields_mod, fake, capsys)
    assert fake.patched_ids() == []
    assert re.search(r"#1: 2 \(at LR-MDB-1\)", out), out
    assert re.search(r"#2: 3 \(at LR-MDB-1\)", out), out


def test_a_rebuild_refused_at_the_delete_leaves_every_value_where_it_is(setup_fields_mod, capsys):
    """A DELETE Spoolman refuses deletes nothing: every value is still in Spoolman,
    nothing is written, and the run says there is nothing to put back (the base said
    the values were "snapshotted but not restored", as if they were lost)."""
    fake = _fake()
    fake.add("spool", 1, location="LR-MDB-1", extra={SLOT: '"2"'})
    fake.delete_fails = True
    out = _run(setup_fields_mod, fake, capsys)
    assert fake.slot(1) == '"2"'
    assert fake.field_type() == "choice"
    assert fake.patched_ids() == []
    assert "still in Spoolman" in out, out
    assert "#1: 2" not in out, out


def test_an_unreadable_spool_list_deletes_nothing_and_raises_nothing(setup_fields_mod, capsys):
    """RED. A 200 whose body isn't JSON raised out of the migration (only a
    RequestException was caught), which stops setup_fields before every field set up
    after it. Now the migration stops before the delete, with nothing touched."""
    fake = _fake()
    fake.add("spool", 1, location="LR-MDB-1", extra={SLOT: '"2"'})
    fake.list_unreadable = True
    out = _run(setup_fields_mod, fake, capsys)
    assert fake.deleted() == []
    assert fake.slot(1) == '"2"'
    assert fake.field_type() == "choice"
    assert "aborting migration" in out, out


def test_control_already_text_is_a_no_op(setup_fields_mod, capsys):
    """Control, green on the base: the steady state on dev and prod. Nothing is read
    beyond the field list, and nothing is written."""
    fake = _fake(old_type="text")
    fake.add("spool", 1, location="LR-MDB-1", extra={SLOT: '"2"'})
    _run(setup_fields_mod, fake, capsys)
    assert [e[:2] for e in fake.events] == [("GET", "/api/v1/field/spool")]
    assert fake.slot(1) == '"2"'


def test_the_migration_imports_nothing_from_the_app():
    """setup_fields.py runs on the deploy host with plain `requests`: importing the
    app's spoolman_api would pull in Flask and FCC's state."""
    src = open(os.path.join(os.path.dirname(__file__), "..", "..", "setup-and-rebuild", "setup_fields.py"),
               encoding="utf-8").read()
    assert not re.search(r"^\s*(import|from)\s+spoolman_api\b", src, re.M)
    assert "import spoolman_api" not in src
