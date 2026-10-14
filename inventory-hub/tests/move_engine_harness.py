"""Shared move-engine test harness (Group 39.1, extracted from
tests/test_active_print_chain_confirm.py, 2026-10-13).

Drives the REAL logic.perform_smart_move: Spoolman, both locations.json writers
(Group 20.2 attach/detach) and the PrusaLink HTTP probe are faked. The probe is
patched BELOW the per-move memo (prusalink_api._probe_printer_state), so a move
sees the same cached printer state production does. FakeSpoolman's location
readers mirror spoolman_api._build_location_match (first-segment prefix and
ghost matches), and WireSpoolman runs the REAL update_spool merge with only its
HTTP calls faked ([[mocked engine hides chain bugs]]: never mock the engine).
Flat module, like tests/source_family.py.
"""
from __future__ import annotations

import copy
import json
from contextlib import ExitStack
from unittest.mock import MagicMock, patch

import logic

REAL_UPDATE_SPOOL = logic.spoolman_api.update_spool


class FakeSpoolman:
    """A tiny in-memory Spoolman: reads reflect earlier writes, so a multi-hop
    move (box placement -> chained toolhead deploy -> resident eject -> undo)
    sees the state its own previous hop produced.

    The location readers decide matches the way spoolman_api._build_location_match
    does: the spool's location equals the target or has it as its first
    '-'-segment (direct), else its physical_source does (ghost). Assertions use
    direct_at(), which counts only spools really AT a location. Ids in
    `unreadable` read as None, like get_spool on a Spoolman timeout.
    """

    def __init__(self, spools, reject_locations=(), unreadable=(), reject_ids=(), landed_but_failed=()):
        self.spools = {int(k): copy.deepcopy(v) for k, v in spools.items()}
        self.reject_locations = {str(r).upper() for r in reject_locations}
        self.unreadable = {int(u) for u in unreadable}
        # Group 41.2: Spoolman rejects every write to these spools.
        self.reject_ids = {int(r) for r in reject_ids}
        # Group 41 review: writes to these spools LAND but answer as failed, like
        # a PATCH Spoolman committed after update_spool's read timeout.
        self.landed_but_failed = {int(r) for r in landed_but_failed}
        # True = Spoolman's spool LIST is down: the fail-open readers answer []
        # (they swallow the error) and the strict reader raises.
        self.list_reads_fail = False
        # Every spool-LIST read, counted in order; `fail_list_reads` holds the
        # 0-based numbers of the reads that fail (list_reads_fail fails them all).
        self.list_reads = 0
        self.fail_list_reads = set()
        self.writes = []

    def get_spool(self, sid):
        rec = self.spools.get(int(sid))
        if rec is None or int(sid) in self.unreadable:
            return None
        return {"id": int(sid), **copy.deepcopy(rec)}

    def update_spool(self, sid, data):
        self.writes.append((int(sid), copy.deepcopy(data)))
        if int(sid) in self.reject_ids or str(data.get("location", "")).upper() in self.reject_locations:
            logic.spoolman_api.LAST_SPOOLMAN_ERROR = "400: rejected by test"
            return None
        rec = self.spools.setdefault(int(sid), {"location": "", "extra": {}})
        if "location" in data:
            rec["location"] = data["location"]
        if "extra" in data:
            rec["extra"] = copy.deepcopy(data["extra"])
        if int(sid) in self.landed_but_failed:
            logic.spoolman_api.LAST_SPOOLMAN_ERROR = "Read timed out. (read timeout=15) (test)"
            return None
        return {"id": int(sid), **copy.deepcopy(rec)}

    def _list_read_fails(self):
        n = self.list_reads
        self.list_reads += 1
        return self.list_reads_fail or n in self.fail_list_reads

    def direct_at(self, loc):
        loc = str(loc).upper()
        return sorted(sid for sid, rec in self.spools.items()
                      if str(rec.get("location", "")).upper() == loc)

    def _match(self, rec, loc):
        prefix = logic.locations_db.location_prefix
        sloc = str(rec.get("location") or "").strip().upper()
        if sloc and (sloc == loc or prefix(sloc) == loc):
            return "direct"
        src = str((rec.get("extra") or {}).get("physical_source") or "").strip().strip('"').upper()
        if src and (src == loc or prefix(src) == loc):
            return "ghost"
        return None

    def at_location(self, loc):
        if self._list_read_fails():
            return []
        loc = str(loc).upper()
        return sorted(sid for sid, rec in self.spools.items() if self._match(rec, loc))

    def at_location_detailed_strict(self, loc):
        if self._list_read_fails():
            raise logic.spoolman_api.requests.ConnectionError("Spoolman spool list unreachable (test)")
        return self._detailed(loc)

    def at_location_detailed(self, loc):
        if self._list_read_fails():
            return []
        return self._detailed(loc)

    def _detailed(self, loc):
        loc = str(loc).upper()
        items = []
        for sid in sorted(self.spools):
            rec = self.spools[sid]
            kind = self._match(rec, loc)
            extra = rec.get("extra") or {}
            if kind == "direct":
                items.append({"id": sid, "is_ghost": False, "location": rec.get("location", ""),
                              "slot": extra.get("container_slot", "")})
            elif kind == "ghost":
                items.append({"id": sid, "is_ghost": True, "location": extra.get("physical_source", ""),
                              "slot": extra.get("physical_source_slot", ""),
                              "deployed_to": rec.get("location", "")})
        return items


def _wire(value):
    return ("true" if value else "false") if isinstance(value, bool) else json.dumps(value)


def _unwire(value):
    if isinstance(value, str):
        try:
            return json.loads(value)
        except ValueError:
            return value
    return value


class WireSpoolman(FakeSpoolman):
    """FakeSpoolman whose update_spool runs the REAL spoolman_api.update_spool
    (sanitize + read-merge-write of extras) with only its HTTP calls faked, and
    keeps every PATCH body: exactly what Spoolman would receive."""

    def __init__(self, spools, reject_locations=(), unreadable=()):
        super().__init__(spools, reject_locations, unreadable)
        self.patch_bodies = []

    def _http_get(self, url, *a, **k):
        tail = str(url).split("?")[0].rstrip("/").rsplit("/", 1)[-1]
        rec = self.spools.get(int(tail)) if tail.isdigit() else None
        if rec is None:
            return MagicMock(ok=False, status_code=404, text="not found",
                             json=MagicMock(return_value={}))
        body = {"id": int(tail), "location": rec.get("location", ""),
                "extra": {key: _wire(val) for key, val in (rec.get("extra") or {}).items()}}
        return MagicMock(ok=True, status_code=200, json=MagicMock(return_value=body))

    def _http_patch(self, url, json=None, **k):
        sid = int(str(url).rstrip("/").rsplit("/", 1)[-1])
        body = copy.deepcopy(json)
        self.patch_bodies.append((sid, body))
        rec = self.spools.setdefault(sid, {"location": "", "extra": {}})
        if "location" in body:
            rec["location"] = body["location"]
        if "extra" in body:
            rec["extra"] = {key: _unwire(val) for key, val in body["extra"].items()}
        return MagicMock(ok=True, status_code=200,
                         json=MagicMock(return_value={"id": sid, **copy.deepcopy(rec)}))

    def update_spool(self, sid, data):
        self.writes.append((int(sid), copy.deepcopy(data)))
        with patch.object(logic.spoolman_api.requests, "get", side_effect=self._http_get), \
             patch.object(logic.spoolman_api.requests, "patch", side_effect=self._http_patch):
            return REAL_UPDATE_SPOOL(sid, copy.deepcopy(data))


def _probe_for(printing):
    """PrusaLink HTTP probe stub: printers named in `printing` are PRINTING."""
    def probe(_url, printer_name):
        active = printer_name in printing
        return {"state": "PRINTING" if active else "IDLE", "is_active": active}
    return probe


IDLE = _probe_for(set())


class LocationsStore:
    """A real, mutable locations.json for lifecycle tests (Group 42). Pass it as
    run_move(store=...): load / save go through it, and the REAL single-slot
    attach / release helpers run against it, so a binding is observable across
    hops ([[mocked engine hides chain bugs]]). `saves` keeps every saved list."""

    def __init__(self, rows):
        self.rows = copy.deepcopy(list(rows))
        self.saves = []

    def load(self, *a, **k):
        return copy.deepcopy(self.rows)

    def save(self, rows, *a, **k):
        self.rows = copy.deepcopy(list(rows))
        self.saves.append(copy.deepcopy(self.rows))
        return True

    def row(self, lid):
        return next(r for r in self.rows if str(r.get("LocationID", "")).upper() == str(lid).upper())

    def bound(self, box, slot="1"):
        """What `box`'s slot is bound to now ('' when unbound)."""
        return logic.locations_db.bindings_from_row(self.row(box)).get(str(slot), "")


def run_move(sm, *, probe, printer_map, locations=None, store=None, call=None, **move_kwargs):
    """Run perform_smart_move(**move_kwargs), or `call()`, against the fakes:
    `locations` is what locations.json holds, `printer_map` the active map.
    With `store` (a LocationsStore) instead, locations.json is that live store
    and the single-slot box attach / release run for real against it."""
    if store is not None:
        locations_patches = (
            patch.object(logic.locations_db, "load_locations_list", side_effect=store.load),
            patch.object(logic.locations_db, "save_locations_list", side_effect=store.save),
        )
    else:
        locs = locations
        locations_patches = (
            patch.object(logic.locations_db, "load_locations_list",
                         side_effect=lambda *a, **k: copy.deepcopy(locs)),
            # The single-slot box attach / release persist locations.json, and
            # save_locations_list isn't patched here: keep them off the real file.
            patch.object(logic.locations_db, "attach_single_slot_box_to_toolhead",
                         return_value=(False, "mocked")),
            patch.object(logic.locations_db, "detach_single_slot_box", return_value=False),
        )
    with ExitStack() as stack:
        for p in locations_patches + (
            patch.object(logic.config_loader, "load_config",
                         return_value={"printer_map": printer_map}),
            patch.object(logic.config_loader, "get_api_urls",
                         return_value=("http://spoolman", "http://filabridge")),
            patch.object(logic.locations_db, "get_active_printer_map",
                         return_value=printer_map),
            patch.object(logic.locations_db, "is_descendant", return_value=False),
            patch.object(logic.spoolman_api, "LAST_SPOOLMAN_ERROR", None),
            patch.object(logic.spoolman_api, "get_spool", side_effect=sm.get_spool),
            patch.object(logic.spoolman_api, "update_spool", side_effect=sm.update_spool),
            patch.object(logic.spoolman_api, "get_spools_at_location",
                         side_effect=sm.at_location),
            patch.object(logic.spoolman_api, "get_spools_at_location_detailed",
                         side_effect=sm.at_location_detailed),
            patch.object(logic.spoolman_api, "get_spools_at_location_detailed_strict",
                         side_effect=sm.at_location_detailed_strict),
            patch.object(logic.spoolman_api, "format_spool_display",
                         side_effect=lambda s: {"text": f"#{(s or {}).get('id')}",
                                                "color": "ff0000"}),
            # Below the per-move memo, as in production.
            patch("prusalink_api._probe_printer_state", side_effect=probe),
            patch.object(logic.requests, "post", return_value=MagicMock(ok=True)),
            patch.object(logic.requests, "get",
                         return_value=MagicMock(ok=False, status_code=404)),
        ):
            stack.enter_context(p)
        if call is not None:
            return call()
        return logic.perform_smart_move(**move_kwargs)
