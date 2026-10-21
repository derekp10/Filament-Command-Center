"""How Spoolman stores a PATCH's `extra`, faithfully, for the test fakes (2026-10-21).

Spoolman has stored a PATCH's `extra` two ways (read from its source, tags v0.21.0
to v0.27.0, and probed on dev's 0.27.0):

  - MERGE: key by key. A key the PATCH leaves out is KEPT, a key sent with a value
    replaces its row, and (0.26 and newer) a key sent as JSON null loses its row,
    so it is gone from every read. Every entity from 0.26 (dev and prod run
    0.27.0); a spool's from 0.22.
  - REPLACE: the PATCH's `extra` replaces the stored one, so a key left out is
    dropped. A filament's and a vendor's up to 0.25; every entity's before 0.22.
    Before 0.26 a null value is refused (422) for the whole PATCH.

Every value is checked like Spoolman's validate_extra_field_value (0.27.0; the
per-type checks are unchanged since 0.23.1 except the 65,535-character cap): one
bad key refuses the whole PATCH and nothing is stored. A body with `"extra": null`
is a 500 (0.27 iterates it).

The harnesses that keep spools in memory (move_engine_harness, deduct_wire_harness,
the low-stock and archived-spool fakes) apply every PATCH through `apply_extra_patch`
in DEFAULT_MODE: merge, as dev and prod do. `FCC_FAKE_SPOOLMAN_EXTRA=replace` runs
them the old way, and the suite passes both ways: FCC re-sends a record's whole
extras on every write, so the two differ only where FCC leaves a key out to clear it.

`SpoolmanHTTPFake` is a whole Spoolman over HTTP (records, field lists, version)
for driving spoolman_api's REAL update_spool / update_filament / update_vendor.
Flat module, like tests/source_family.py.
"""
from __future__ import annotations

import copy
import json
import os
import re
from urllib.parse import urlsplit

MERGE = "merge"
REPLACE = "replace"
DEFAULT_MODE = (os.environ.get("FCC_FAKE_SPOOLMAN_EXTRA") or MERGE).strip().lower()
if DEFAULT_MODE not in (MERGE, REPLACE):
    raise ValueError(f"FCC_FAKE_SPOOLMAN_EXTRA must be '{MERGE}' or '{REPLACE}', not {DEFAULT_MODE!r}")

MAX_VALUE_LENGTH = 2 ** 16 - 1
NULLS_FROM = (0, 26, 0)          # a JSON null clears an extra from this version
SPOOL_MERGES_FROM = (0, 22, 0)   # a spool's extra merged key by key from this version


class ExtraRejected(Exception):
    """Spoolman refused the PATCH: `status` and its `message` body."""

    def __init__(self, status, message):
        super().__init__(message)
        self.status = status
        self.message = message


def version_tuple(version):
    nums = [int(n) for n in re.findall(r"\d+", str(version))][:3]
    return tuple(nums + [0] * (3 - len(nums)))


def mode_for(version, entity):
    """How this Spoolman version stores `entity`'s PATCHed extra."""
    v = version_tuple(version)
    if v >= NULLS_FROM:
        return MERGE
    if entity == "spool" and v >= SPOOL_MERGES_FROM:
        return MERGE
    return REPLACE


def wire(value):
    """A parsed extra value in Spoolman's wire form (what a GET answers)."""
    if isinstance(value, bool):
        return "true" if value else "false"
    return json.dumps(value)


def unwire(value):
    """A wire value parsed, as spoolman_api.parse_inbound_data reads it."""
    if isinstance(value, str):
        try:
            return json.loads(value)
        except ValueError:
            return value
    return value


def check_value(field, raw, *, nulls_ok=True):
    """Spoolman's check of one extra value in wire form; raises ExtraRejected."""
    if raw is None:
        if not nulls_ok:
            raise ExtraRejected(422, "Input should be a valid string")
        return
    if not isinstance(raw, str):
        raise ExtraRejected(422, "Input should be a valid string")
    if len(raw) > MAX_VALUE_LENGTH:
        raise ExtraRejected(400, f"Value is too big, max size is {MAX_VALUE_LENGTH} characters.")
    try:
        data = json.loads(raw)
    except ValueError:
        raise ExtraRejected(400, "Value is not valid JSON.")
    if field is None:
        return
    ftype = field.get("field_type")
    if ftype in ("text", "datetime"):
        if not isinstance(data, str):
            raise ExtraRejected(400, "Value is not a string.")
    elif ftype == "integer":
        if not isinstance(data, int):            # bool passes, as in Spoolman
            raise ExtraRejected(400, "Value is not an integer.")
    elif ftype == "integer_range":
        if not isinstance(data, list):
            raise ExtraRejected(400, "Value is not a list.")
        if len(data) != 2:
            raise ExtraRejected(400, "Value list must have exactly two values.")
        if not all(isinstance(item, int) or item is None for item in data):
            raise ExtraRejected(400, "Value list must contain only integers or null.")
    elif ftype == "float":
        if not isinstance(data, (float, int)) or isinstance(data, bool):
            raise ExtraRejected(400, "Value is not a float.")
    elif ftype == "float_range":
        if not isinstance(data, list):
            raise ExtraRejected(400, "Value is not a list.")
        if len(data) != 2:
            raise ExtraRejected(400, "Value list must have exactly two values.")
        if not all((isinstance(item, (float, int)) or item is None) and not isinstance(item, bool)
                   for item in data):
            raise ExtraRejected(400, "Value list must contain only floats or null.")
    elif ftype == "boolean":
        if not isinstance(data, bool):
            raise ExtraRejected(400, "Value is not a boolean.")
    elif ftype == "choice":
        choices = field.get("choices")
        if field.get("multi_choice"):
            if not isinstance(data, list):
                raise ExtraRejected(400, "Value is not a list.")
            if not all(isinstance(item, str) for item in data):
                raise ExtraRejected(400, "Value list must contain only strings.")
            if choices is not None and not all(item in choices for item in data):
                raise ExtraRejected(400, "Value list contains invalid choices.")
        else:
            if not isinstance(data, str):
                raise ExtraRejected(400, "Value is not a string.")
            if choices is not None and data not in choices:
                raise ExtraRejected(400, "Value is not a valid choice.")


def apply_extra_patch(stored, patch_extra, *, mode=None, schema=None, nulls_ok=None):
    """The stored extra (wire values) after a PATCH whose body carried
    `"extra": patch_extra`, or ExtraRejected (nothing stored).

    `schema` ({key: field definition}) checks each value by its type and refuses
    a key it doesn't list, as Spoolman does; without one (the in-memory harnesses)
    a value only has to be a JSON string. `nulls_ok` defaults to the mode's
    Spoolman (a merging one is 0.26+ here)."""
    mode = mode or DEFAULT_MODE
    if nulls_ok is None:
        nulls_ok = mode == MERGE
    if patch_extra is None:
        raise ExtraRejected(500, "Internal Server Error")
    if not isinstance(patch_extra, dict):
        raise ExtraRejected(422, "Input should be a valid dictionary")
    for key, raw in patch_extra.items():
        field = None
        if schema is not None:
            field = schema.get(key)
            if field is None:
                raise ExtraRejected(400, f"Unknown extra field {key}.")
        check_value(field, raw, nulls_ok=nulls_ok)
    if mode == REPLACE:
        return {k: v for k, v in patch_extra.items() if v is not None}
    out = {k: v for k, v in (stored or {}).items() if k not in patch_extra}
    out.update({k: v for k, v in patch_extra.items() if v is not None})
    return out


def apply_parsed(stored_parsed, patch_extra, *, mode=None):
    """apply_extra_patch for a harness that keeps extras PARSED."""
    raw = {k: wire(v) for k, v in (stored_parsed or {}).items()}
    return {k: unwire(v) for k, v in apply_extra_patch(raw, patch_extra, mode=mode).items()}


def fcc_update_spool_extra(stored_parsed, requested):
    """What spoolman_api.update_spool stores for a caller's `extra`, for a fake that
    stands in for update_spool itself (move_engine_harness.FakeSpoolman): FCC merges
    the caller's keys into the record's whole extras first, so a key the caller
    leaves out, or sends as None (sanitize_outbound_data drops it), is KEPT on any
    Spoolman; the delete sentinel clears the key (read back blank)."""
    out = copy.deepcopy(stored_parsed or {})
    for key, value in (requested or {}).items():
        if value is None:
            continue
        if str(value).strip().strip('"') == "__FCC_DELETE_EXTRA__":
            if key in out:
                out[key] = ""
            continue
        out[key] = copy.deepcopy(value)
    return out


class _Resp:
    def __init__(self, status, body):
        self.status_code = status
        self.ok = 200 <= status < 300
        self._body = body
        self.text = json.dumps(body)

    def json(self):
        return copy.deepcopy(self._body)


class SpoolmanHTTPFake:
    """Spoolman over HTTP: records per entity with WIRE extras, a field list per
    entity and a version. `get` / `patch` stand in for requests.get /
    requests.patch (patch them on spoolman_api.requests). Each entity's extra is
    stored as `version` would (mode_for), or as `mode` says for every entity.

    `gets` lists every GET path in order; `patches` every PATCH as (entity, id,
    body). `field_reads_fail` / `info_fails` make those reads answer a 503."""

    def __init__(self, *, version="0.27.0", mode=None, fields=None):
        self.version = version
        self.mode = mode
        self.fields = {e: list(fs) for e, fs in (fields or {}).items()}
        self.records = {"spool": {}, "filament": {}, "vendor": {}}
        self.gets = []
        self.patches = []
        self.field_reads_fail = False
        self.info_fails = False

    def add(self, entity, eid, extra=None, **fields):
        rec = {"id": int(eid), **fields, "extra": dict(extra or {})}
        self.records[entity][int(eid)] = rec
        return rec

    def extra(self, entity, eid):
        return dict(self.records[entity][int(eid)]["extra"])

    def schema(self, entity):
        return {f["key"]: f for f in self.fields.get(entity, [])}

    def mode_of(self, entity):
        return self.mode or mode_for(self.version, entity)

    def nulls_ok(self):
        return version_tuple(self.version) >= NULLS_FROM

    def get(self, url, timeout=None, **kw):
        path = urlsplit(str(url)).path.rstrip("/")
        self.gets.append(path)
        if path == "/api/v1/info":
            if self.info_fails:
                return _Resp(503, {"message": "unavailable (test)"})
            return _Resp(200, {"version": self.version, "db_type": "sqlite"})
        m = re.fullmatch(r"/api/v1/field/(spool|filament|vendor)", path)
        if m:
            if self.field_reads_fail:
                return _Resp(503, {"message": "unavailable (test)"})
            return _Resp(200, copy.deepcopy(self.fields.get(m.group(1), [])))
        m = re.fullmatch(r"/api/v1/(spool|filament|vendor)/(\d+)", path)
        if m:
            rec = self.records[m.group(1)].get(int(m.group(2)))
            if rec is None:
                return _Resp(404, {"message": f"No {m.group(1)} with ID {m.group(2)} found."})
            return _Resp(200, copy.deepcopy(rec))
        return _Resp(404, {"message": "no such route (test)"})

    def patch(self, url, json=None, timeout=None, **kw):  # noqa: A002 — requests' kwarg
        path = urlsplit(str(url)).path.rstrip("/")
        m = re.fullmatch(r"/api/v1/(spool|filament|vendor)/(\d+)", path)
        if not m:
            return _Resp(404, {"message": "no such route (test)"})
        entity, eid = m.group(1), int(m.group(2))
        body = copy.deepcopy(json)
        self.patches.append((entity, eid, body))
        rec = self.records[entity].get(eid)
        if rec is None:
            return _Resp(404, {"message": f"No {entity} with ID {eid} found."})
        if "extra" in body:
            try:
                new_extra = apply_extra_patch(rec.get("extra"), body["extra"], mode=self.mode_of(entity),
                                              schema=self.schema(entity), nulls_ok=self.nulls_ok())
            except ExtraRejected as e:
                return _Resp(e.status, {"message": f"Invalid extra field: {e.message}"})
            rec["extra"] = new_extra
        for key, value in body.items():
            if key not in ("extra", "id"):
                rec[key] = value
        return _Resp(200, copy.deepcopy(rec))
