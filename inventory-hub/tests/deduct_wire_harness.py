"""Shared test harness: a Spoolman fake that speaks the WIRE, weights included.

`spoolman_api.get_spool` / `update_spool` run for REAL against it; only
`requests.get` / `requests.patch` are answered here. So the `used_weight <=
initial_weight` cap (which applies only to an OWN initial_weight), the
inherit-weight fallback and the auto-archive rule all run as in production
([[mocked engine hides chain bugs]]). Flat module, like tests/source_family.py.

Used by the Group 43 deduct-recovery tests.
"""
from __future__ import annotations

import copy
import json
from unittest.mock import MagicMock, patch

import print_deduct
import spoolman_api

def _unwire(value):
    if isinstance(value, str):
        try:
            return json.loads(value)
        except ValueError:
            return value
    return value


class WeightWireSpoolman:
    """Spoolman over the wire, weights included. get_spool / update_spool run for
    real; only `requests.get` / `requests.patch` are answered here, from records
    shaped like Spoolman's (own initial_weight may be null; filament.weight is the
    inherited net weight). A PATCH applies what Spoolman would store."""

    def __init__(self, spools, patch_fails=(), patch_lost=()):
        self.spools = {int(k): copy.deepcopy(v) for k, v in spools.items()}
        self.patches = []
        self.patch_fails = set(patch_fails)   # sids whose PATCH lands but answers as a failure
        self.patch_lost = set(patch_lost)     # sids whose PATCH never lands (and answers as a failure)
        self.blind = set()                    # sids Spoolman can't be read for (a GET fails)
        self.blind_after_patch = set()        # sids that go blind as soon as a PATCH to them lands

    def _get(self, url, *a, **k):
        tail = str(url).split("?")[0].rstrip("/").rsplit("/", 1)[-1]
        if tail.isdigit() and int(tail) in self.blind:
            raise spoolman_api.requests.exceptions.ConnectionError("unreachable (test)")
        rec = self.spools.get(int(tail)) if tail.isdigit() else None
        if rec is None:
            return MagicMock(ok=False, status_code=404, text="not found", json=MagicMock(return_value={}))
        body = copy.deepcopy(rec)
        body["id"] = int(tail)
        body["extra"] = {key: json.dumps(val) for key, val in (rec.get("extra") or {}).items()}
        return MagicMock(ok=True, status_code=200, json=MagicMock(return_value=body))

    def _patch(self, url, json=None, **k):  # noqa: A002 — mirrors requests' kwarg
        sid = int(str(url).rstrip("/").rsplit("/", 1)[-1])
        body = copy.deepcopy(json)
        self.patches.append((sid, body))
        if sid in self.patch_lost:
            raise spoolman_api.requests.exceptions.ReadTimeout("read timed out, not applied (test)")
        rec = self.spools[sid]
        for key in ("used_weight", "initial_weight", "archived", "location"):
            if key in body:
                rec[key] = body[key]
        if "extra" in body:
            rec["extra"] = {key: _unwire(val) for key, val in body["extra"].items()}
        if sid in self.blind_after_patch:
            self.blind.add(sid)
        if sid in self.patch_fails:
            # The write LANDED, but the answer reads as a failure (a timeout after
            # commit) — the 43.6 hazard.
            raise spoolman_api.requests.exceptions.ReadTimeout("read timed out (test)")
        return MagicMock(ok=True, status_code=200, json=MagicMock(return_value={"id": sid, **copy.deepcopy(rec)}))

    def used(self, sid):
        return self.spools[int(sid)]["used_weight"]



def _wire_ctx(sm, at=None, toolheads=(("XL-1", 0),), printer="XL"):
    at = at or {"XL-1": [100]}
    active = [(loc, {"position": pos, "printer_name": printer}) for loc, pos in toolheads]
    return [
        patch.object(print_deduct.locations_db, "get_active_printer_map", return_value={}),
        patch.object(print_deduct, "_resolve_active_locs_for_printer", return_value=active),
        patch.object(spoolman_api, "get_spools_at_location", side_effect=lambda loc: list(at.get(str(loc).upper(), []))),
        patch.object(spoolman_api.config_loader, "get_api_urls", return_value=("http://sm", "http://fb")),
        patch.object(spoolman_api, "format_spool_display", return_value={"text": "#s", "color": "ff0000"}),
        patch.object(spoolman_api.requests, "get", side_effect=sm._get),
        patch.object(spoolman_api.requests, "patch", side_effect=sm._patch),
    ]


def _start(ctx):
    for m in ctx:
        m.start()


def _stop(ctx):
    for m in reversed(ctx):
        m.stop()
