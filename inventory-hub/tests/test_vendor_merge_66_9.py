"""Group 66.9: Merge manufacturer, the server half.

POST /api/vendors/<src>/merge_into/<dst> moves every filament of one manufacturer
(Spoolman's vendor) onto another and deletes the emptied one; GET
/api/vendors/<id>/merge_options is the merge window's read-only list of possible
duplicates. Both run here as the real routes, through the real spoolman_api helpers
and the real requests calls they make, against a Spoolman fake that does what
Spoolman 0.27.1 does with vendors:

  - a vendor DELETE succeeds while filaments still name the vendor, and clears their
    vendor (its API text: "The vendor attribute of any filaments who refer to the
    deleted vendor will be cleared"; a dev probe on 2026-11-26 with vendor #42 and
    filament #192 confirmed it, both deleted afterwards). So the merge's strict
    re-list right before the delete is all that keeps a failed move from leaving a
    filament with no manufacturer, and these tests drive that guard;
  - the filament list honours ?vendor.id= and answers EVERY filament to a parameter
    it doesn't know (dev: ?nonsense_param= answered all 191);
  - a filament PATCH of vendor_id nests the vendor's record, and one naming a vendor
    that isn't there answers 404.

The data is Derek's three same-name pairs as dev (prod's copy) holds them on
2026-11-26: Sunlu #4 (167 g, 42 filaments there) and #35 (External ID "Sunlu", 4
filaments, #160-#163, each with its own 168 g), Prusament #9 and #34 (External ID
"Prusament", no filaments), Jessie Premium #38 (179 g, External ID "", website '""')
and #39 (nothing). Tests may name his setup (CLAUDE.md).

RED on the base (dev c5cb19ff): neither route exists (404 from Flask), and
spoolman_api has no delete_vendor, get_vendor_answer, vendor_dup_key or
vendor_names_look_alike.
"""
from __future__ import annotations

import copy
import os
import re
import sys
from urllib.parse import parse_qs, urlsplit

import pytest
import requests
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import app as flask_app  # noqa: E402
import routes_locations  # noqa: E402
import spoolman_api  # noqa: E402
import state  # noqa: E402
from spoolman_extra_fake import SpoolmanHTTPFake, _Resp  # noqa: E402


SM = "http://spoolman.test:7913"
VENDOR_FIELDS = [{"key": "website", "field_type": "text", "name": "Website"}]
SPOOL_FIELDS = [{"key": "needs_label_print", "field_type": "boolean", "name": "Needs Label Print"}]
FILAMENT_FIELDS = [
    {"key": "needs_label_print", "field_type": "boolean", "name": "Needs Label Print"},
    {"key": "sample_printed", "field_type": "boolean", "name": "Sample Printed"},
]


@pytest.fixture()
def client():
    flask_app.config['TESTING'] = True
    with flask_app.test_client() as c:
        yield c


class _Raw:
    """An answer whose body isn't JSON."""

    def __init__(self, status, text):
        self.status_code = status
        self.ok = 200 <= status < 300
        self.text = text

    def json(self):
        raise requests.exceptions.JSONDecodeError("Expecting value", self.text, 0)


class _VendorSpoolman(SpoolmanHTTPFake):
    """The repo's Spoolman fake, plus what a manufacturer merge reaches (see the
    module docstring). `honours` names the filament-list parameters this Spoolman
    filters by. `canned[(verb, path)]` answers (or raises) one request once;
    `canned[("LIST", n)]` the n-th filtered filament-list read. `land_then_raise`
    applies a write and then raises, as a lost answer does. `on_list_read(n)` runs
    before the n-th filtered read. `reads_fail_after_delete` makes every vendor read
    raise once a vendor DELETE has been tried."""

    def __init__(self, honours=("vendor.id", "vendor_id")):
        super().__init__(fields={"vendor": VENDOR_FIELDS, "spool": SPOOL_FIELDS,
                                 "filament": FILAMENT_FIELDS})
        self.honours = tuple(honours)
        self.get_urls = []
        self.deletes = []
        self.canned = {}
        self.land_then_raise = {}
        self.on_list_read = None
        self.list_reads = 0
        self.reads_fail_after_delete = False
        self._vendor_reads_fail = False
        # Every request in order, as (VERB, path[?query]); and get_hooks[path] = fn(n), run
        # on the n-th GET of that path: an answer or an exception to send instead, or None.
        self.ops = []
        self.get_hooks = {}
        self._get_counts = {}

    def nested(self, vid):
        """A vendor as Spoolman nests it in a filament: unset keys left out."""
        rec = copy.deepcopy(self.records["vendor"][vid])
        return {k: v for k, v in rec.items() if v is not None}

    def _canned(self, key):
        answer = self.canned.pop(key, None)
        if isinstance(answer, BaseException):
            raise answer
        return answer

    def get(self, url, timeout=None, **kw):
        self.get_urls.append(str(url))
        parts = urlsplit(str(url))
        path = parts.path.rstrip("/")
        self.ops.append(("GET", path + (f"?{parts.query}" if parts.query else "")))
        n = self._get_counts[path] = self._get_counts.get(path, 0) + 1
        hook = self.get_hooks.get(path)
        if hook is not None:
            answer = hook(n)
            if isinstance(answer, BaseException):
                raise answer
            if answer is not None:
                return answer
        if self._vendor_reads_fail and re.fullmatch(r"/api/v1/vendor/\d+", path):
            raise requests.exceptions.ConnectionError("Connection refused (test)")
        canned = self._canned(("GET", path))
        if canned is not None:
            return canned
        if path == "/api/v1/filament" and parts.query:
            query = parse_qs(parts.query)
            for name in self.honours:
                if name in query:
                    self.list_reads += 1
                    if self.on_list_read:
                        self.on_list_read(self.list_reads)
                    canned = self._canned(("LIST", self.list_reads))
                    if canned is not None:
                        return canned
                    vid = int(query[name][0])
                    rows = [copy.deepcopy(f) for f in self.records["filament"].values()
                            if ((f.get("vendor") or {}).get("id") if f.get("vendor") else -1) == vid]
                    return _Resp(200, rows)
        return super().get(url, timeout=timeout, **kw)

    def patch(self, url, json=None, timeout=None, **kw):  # noqa: A002 (requests' kwarg)
        path = urlsplit(str(url)).path.rstrip("/")
        self.ops.append(("PATCH", path))
        m = re.fullmatch(r"/api/v1/(spool|filament|vendor)/(\d+)", path)
        canned = self._canned(("PATCH", path))
        if canned is not None:
            self.patches.append((m.group(1), int(m.group(2)), copy.deepcopy(json)))
            return canned
        fil = re.fullmatch(r"/api/v1/filament/(\d+)", path)
        if fil and "vendor_id" in (json or {}):
            vid = json["vendor_id"]
            if vid is not None and vid not in self.records["vendor"]:
                self.patches.append(("filament", int(fil.group(1)), copy.deepcopy(json)))
                return _Resp(404, {"message": f"No vendor with ID {vid} found."})
        r = super().patch(url, json=json, timeout=timeout, **kw)
        if r.ok and fil and "vendor_id" in (json or {}):
            rec = self.records["filament"][int(fil.group(1))]
            vid = rec.pop("vendor_id")
            if vid is None:
                rec.pop("vendor", None)
            else:
                rec["vendor"] = self.nested(vid)
            r = _Resp(200, copy.deepcopy(rec))
        exc = self.land_then_raise.pop(("PATCH", path), None)
        if exc is not None:
            raise exc
        return r

    def delete(self, url, timeout=None, **kw):
        path = urlsplit(str(url)).path.rstrip("/")
        self.deletes.append(path)
        self.ops.append(("DELETE", path))
        if self.reads_fail_after_delete and path.startswith("/api/v1/vendor/"):
            self._vendor_reads_fail = True
        canned = self._canned(("DELETE", path))
        if canned is not None:
            return canned
        m = re.fullmatch(r"/api/v1/(vendor|filament|spool)/(\d+)", path)
        if not m:
            return _Resp(404, {"message": "no such route (test)"})
        entity, eid = m.group(1), int(m.group(2))
        if eid not in self.records[entity]:
            return _Resp(404, {"message": f"No {entity} with ID {eid} found."})
        del self.records[entity][eid]
        if entity == "vendor":
            # Spoolman 0.27.1: the vendor goes, and every filament naming it loses it.
            for f in self.records["filament"].values():
                if (f.get("vendor") or {}).get("id") == eid:
                    f.pop("vendor", None)
        exc = self.land_then_raise.pop(("DELETE", path), None)
        if exc is not None:
            raise exc
        return _Resp(200, {"message": "Success!"})

    # --- what the tests read back ---
    def vendor_of(self, fid):
        return (self.records["filament"][fid].get("vendor") or {}).get("id")

    def vendor_patches(self):
        return [(eid, body) for entity, eid, body in self.patches if entity == "vendor"]

    def filament_moves(self):
        return [eid for entity, eid, body in self.patches if entity == "filament" and "vendor_id" in body]

    def extra_writes(self, entity):
        return [eid for e, eid, body in self.patches if e == entity and "extra" in body]

    def list_urls(self):
        return [u for u in self.get_urls if urlsplit(u).path.rstrip("/") == "/api/v1/filament" and "?" in u]


def _stocked(**kw):
    """Derek's three pairs as dev held them on 2026-11-26, plus Overture #1."""
    fake = _VendorSpoolman(**kw)
    fake.add("vendor", 1, name="Overture", registered="2026-02-11T09:00:00Z")
    fake.add("vendor", 4, name="Sunlu", empty_spool_weight=167.0, registered="2026-02-11T10:00:00Z")
    fake.add("vendor", 9, name="Prusament", registered="2026-02-11T11:00:00Z")
    fake.add("vendor", 34, name="Prusament", external_id="Prusament", registered="2026-02-20T10:00:00Z")
    fake.add("vendor", 35, name="Sunlu", external_id="Sunlu", registered="2026-02-25T10:00:00Z")
    fake.add("vendor", 38, name="Jessie Premium", empty_spool_weight=179.0, external_id="", comment="",
             extra={"website": '""'}, registered="2026-04-10T00:52:30Z")
    fake.add("vendor", 39, name="Jessie Premium", registered="2026-04-10T00:52:57Z")
    for fid, name in ((160, "PETG Orange"), (161, "PETG Pink"), (162, "PETG Green"), (163, "PETG Yellow")):
        fake.add("filament", fid, name=name, material="PETG", spool_weight=168.0, vendor=fake.nested(35))
    # Sunlu #4 holds more filaments than #35, as in Derek's data (42 against 4).
    for fid, name in ((100, "PLA Black"), (101, "PLA White"), (102, "PLA Red"), (103, "PLA Blue"),
                      (104, "PLA Green")):
        fake.add("filament", fid, name=name, material="PLA", vendor=fake.nested(4))
    fake.add("filament", 200, name="PLA Galaxy Black", material="PLA", vendor=fake.nested(9))
    fake.add("filament", 175, name="Transition Spool", material="PETG", vendor=fake.nested(38))
    fake.add("filament", 300, name="PLA Grey", material="PLA", vendor=fake.nested(1),
             extra={"needs_label_print": "false"})
    fake.add("spool", 205, filament={"id": 160})
    fake.add("spool", 301, filament={"id": 300})
    fake.add("spool", 302, filament={"id": 300}, archived=True)
    fake.add("spool", 303, filament={"id": 300}, extra={"needs_label_print": "true"})
    return fake


def _call(client, fake, method, path, body=None, hub=None):
    """One request with every Spoolman call on `fake`. Answers (response, Activity
    Log lines as (msg, level)); `hub`, a list, gets each hub.log ERROR and WARNING
    line as (LEVEL, text)."""
    logged = []
    hub = [] if hub is None else hub
    with patch.object(spoolman_api.config_loader, "get_api_urls", return_value=(SM, "http://fb.test")), \
         patch.object(spoolman_api.requests, "get", side_effect=fake.get), \
         patch.object(spoolman_api.requests, "patch", side_effect=fake.patch), \
         patch.object(spoolman_api.requests, "delete", side_effect=fake.delete), \
         patch.object(state, "add_log_entry",
                      side_effect=lambda msg, *a, **k: logged.append((msg, a[0] if a else None))), \
         patch.object(state.logger, "error", side_effect=lambda msg, *a, **k: hub.append(("ERROR", str(msg)))), \
         patch.object(state.logger, "warning", side_effect=lambda msg, *a, **k: hub.append(("WARNING", str(msg)))):
        if method == "GET":
            r = client.get(path)
        else:
            r = client.post(path, json=body) if body is not None else client.post(path)
    return r, logged


MERGE = {"merge": True}


def _merge(client, fake, src, dst, body=MERGE, hub=None):
    """The merge (review round 1, S5: it asks for itself); `body` a dry run or another shape."""
    return _call(client, fake, "POST", f"/api/vendors/{src}/merge_into/{dst}", body, hub)


def _options(client, fake, vid, hub=None):
    return _call(client, fake, "GET", f"/api/vendors/{vid}/merge_options", hub=hub)


def _lines(logged, level=None):
    return [m for m, lv in logged if level is None or lv == level]


# --- the merge, on Derek's pairs --------------------------------------------------

class TestMergeOnDereksPairs:
    def test_sunlu_35_into_4_moves_its_filaments_takes_the_external_id_and_deletes_it(self, client):
        fake = _stocked()
        r, logged = _merge(client, fake, 35, 4)
        body = r.get_json()
        assert r.status_code == 200, body
        assert body["success"] is True
        assert body["moved_filament_ids"] == [160, 161, 162, 163]
        assert all(fake.vendor_of(fid) == 4 for fid in (160, 161, 162, 163))
        assert 35 not in fake.records["vendor"]
        assert fake.deletes == ["/api/v1/vendor/35"]
        # The kept one took the External ID, and kept its own 167 g.
        assert fake.records["vendor"][4]["external_id"] == "Sunlu"
        assert fake.records["vendor"][4]["empty_spool_weight"] == 167.0
        assert body["carried"] == ["external_id"]
        assert body["vendor"]["external_id"] == "Sunlu"
        # The carry went before any filament moved.
        kinds = [entity for entity, _eid, _b in fake.patches]
        assert kinds[0] == "vendor" and kinds.count("vendor") == 1
        assert fake.vendor_patches()[0][1] == {"external_id": "Sunlu"}
        # The list was read by vendor.id, twice (before the moves and before the delete).
        assert [u.split("?", 1)[1] for u in fake.list_urls()] == ["vendor.id=35", "vendor.id=35"]
        # One line for the carry, one per filament moved, one for the merge.
        moved_lines = [m for m in _lines(logged, "INFO") if m.startswith("🔗 Filament #")]
        assert len(moved_lines) == 4
        assert "Filament #160 (PETG Orange) moved from Sunlu #35 to Sunlu #4" in moved_lines[0]
        assert any("took Sunlu #35's External ID “Sunlu”" in m for m in _lines(logged, "INFO"))
        assert _lines(logged, "INFO")[-1] == "🔗 Merged Sunlu #35 into Sunlu #4: 4 filaments moved, Sunlu #35 deleted."
        assert body["msg"] == "Merged Sunlu #35 into Sunlu #4: 4 filaments moved, Sunlu #35 deleted."
        # Same names: nothing a label prints changed, so nothing is marked.
        assert body["label_change"] is False and body["labels_flagged"] is None
        assert fake.extra_writes("spool") == [] and fake.extra_writes("filament") == []

    def test_prusament_34_into_9_carries_the_external_id_and_moves_nothing(self, client):
        fake = _stocked()
        r, logged = _merge(client, fake, 34, 9)
        body = r.get_json()
        assert r.status_code == 200, body
        assert fake.filament_moves() == []
        assert fake.records["vendor"][9]["external_id"] == "Prusament"
        assert fake.deletes == ["/api/v1/vendor/34"]
        assert body["msg"] == "Merged Prusament #34 into Prusament #9: it held no filaments, Prusament #34 deleted."

    def test_jessie_39_into_38_writes_nothing_to_38_and_deletes_39(self, client):
        fake = _stocked()
        r, logged = _merge(client, fake, 39, 38)
        assert r.status_code == 200, r.get_json()
        assert fake.vendor_patches() == []      # 38's '' and '""' against 39's nothing: nothing to carry
        assert fake.deletes == ["/api/v1/vendor/39"]
        assert fake.records["vendor"][38]["empty_spool_weight"] == 179.0


# --- refusals before anything is written ----------------------------------------------

class TestRefusedBeforeAnyWrite:
    def test_a_manufacturer_cant_be_merged_into_itself(self, client):
        fake = _stocked()
        r, _ = _merge(client, fake, 35, 35)
        assert r.status_code == 400
        assert r.get_json() == {"success": False, "msg": "A manufacturer can't be merged into itself."}
        assert fake.get_urls == []

    @pytest.mark.parametrize("src,dst,missing", [(99, 4, 99), (35, 99, 99)])
    def test_an_end_spoolman_has_no_record_of_is_not_found(self, client, src, dst, missing):
        fake = _stocked()
        r, _ = _merge(client, fake, src, dst)
        assert r.status_code == 404
        assert r.get_json()["msg"] == f"Manufacturer #{missing} isn't in Spoolman any more: it was merged or deleted already."
        assert fake.list_urls() == [] and fake.patches == [] and fake.deletes == []

    @pytest.mark.parametrize("answer", [
        _Resp(503, {"message": "database is locked"}),
        requests.exceptions.ConnectionError("Connection refused (test)"),
        _Resp(200, {"id": 4, "name": "Sunlu"}),              # another vendor's record
        _Raw(200, "<html>Bad Gateway</html>"),
    ], ids=["5xx", "no-answer", "another-record", "not-json"])
    def test_an_end_spoolman_couldnt_send_is_couldnt_read(self, client, answer):
        fake = _stocked()
        fake.canned[("GET", "/api/v1/vendor/35")] = answer
        hub = []
        r, _ = _merge(client, fake, 35, 4, hub=hub)
        assert r.status_code == 502
        assert r.get_json()["msg"] == ("Couldn't read manufacturer #35 from Spoolman, so nothing was merged. "
                                       "Try again in a moment.")
        assert [line for lv, line in hub if "vendor 35" in line and lv == "WARNING"], hub
        assert fake.patches == [] and fake.deletes == []

    def test_a_list_that_ignores_the_filter_refuses_before_any_write(self, client):
        fake = _stocked(honours=())       # Spoolman answering every filament to a parameter it doesn't know
        r, _ = _merge(client, fake, 35, 4)
        assert r.status_code == 502
        msg = r.get_json()["msg"]
        assert msg.startswith("Spoolman listed filament #")
        assert "under Sunlu #35, but it belongs to manufacturer #" in msg
        assert msg.endswith("Nothing was merged.")
        assert fake.patches == [] and fake.deletes == []

    @pytest.mark.parametrize("answer,words", [
        (_Resp(503, {"message": "database is locked"}),
         "Couldn't list Sunlu #35's filaments: Spoolman refused it: database is locked. "
         "Nothing was merged; try again in a moment."),
        (_Resp(404, {"message": "Not found"}),
         "Couldn't list Sunlu #35's filaments: Spoolman refused it: Not found. Nothing was merged."),
        (_Raw(200, "<html>Bad Gateway</html>"),
         "Couldn't list Sunlu #35's filaments: Spoolman's answer couldn't be read. "
         "Nothing was merged; try again in a moment."),
        (_Resp(200, {"items": []}),
         "Couldn't list Sunlu #35's filaments: Spoolman's answer couldn't be read. "
         "Nothing was merged; try again in a moment."),
        (_Resp(200, [{"name": "x"}]),
         "Couldn't list Sunlu #35's filaments: Spoolman's answer couldn't be read. "
         "Nothing was merged; try again in a moment."),
        (_Resp(200, [{"id": True, "vendor": {"id": 35}}]),
         "Couldn't list Sunlu #35's filaments: Spoolman's answer couldn't be read. "
         "Nothing was merged; try again in a moment."),
        (_Resp(200, [{"id": 160}]),
         "Spoolman listed filament #160 under Sunlu #35, but it has no manufacturer. Nothing was merged."),
    ], ids=["5xx", "4xx", "not-json", "not-a-list", "no-id", "bool-id", "no-vendor"])
    def test_a_filament_list_fcc_cant_use_refuses_in_words(self, client, answer, words):
        fake = _stocked()
        fake.canned[("LIST", 1)] = answer
        r, _ = _merge(client, fake, 35, 4)
        assert r.status_code == 502
        assert r.get_json()["msg"] == words
        assert fake.patches == [] and fake.deletes == []

    def test_a_list_read_with_no_answer_names_no_spoolman_address(self, client):
        fake = _stocked()
        fake.canned[("LIST", 1)] = requests.exceptions.ConnectionError(
            "HTTPConnectionPool(host='spoolman.test', port=7913): Max retries exceeded")
        hub = []
        r, _ = _merge(client, fake, 35, 4, hub=hub)
        msg = r.get_json()["msg"]
        assert r.status_code == 502
        assert msg.startswith("Couldn't list Sunlu #35's filaments: ")
        assert "spoolman.test" not in msg and "7913" not in msg
        assert any("spoolman.test" in line for _lv, line in hub)   # hub.log keeps where it asked

    def test_a_second_merge_while_one_runs_is_refused_and_reads_nothing(self, client):
        fake = _stocked()
        assert routes_locations._VENDOR_MERGE_LOCK.acquire(False)
        try:
            r, _ = _merge(client, fake, 35, 4)
        finally:
            routes_locations._VENDOR_MERGE_LOCK.release()
        assert r.status_code == 409
        assert r.get_json() == {"success": False, "busy": True,
                                "msg": "Another manufacturer merge is running. Try again once it has finished."}
        assert fake.get_urls == []


# --- partial failures: the source is kept, and a second press finishes ------------------

class TestPartialFailure:
    def test_a_refused_move_keeps_the_source_and_a_second_press_finishes(self, client):
        fake = _stocked()
        fake.canned[("PATCH", "/api/v1/filament/162")] = _Resp(500, {"message": "database is locked"})
        r, logged = _merge(client, fake, 35, 4)
        body = r.get_json()
        assert r.status_code == 502
        assert body["success"] is False and body["source_kept"] is True
        assert body["moved_filament_ids"] == [160, 161, 163]
        assert body["still_on_source"] == [162]
        assert body["filament_errors"] == [{"filament_id": 162, "error": "Spoolman refused it: database is locked"}]
        assert body["msg"] == ("Moved 3 of 4 filaments onto Sunlu #4. Sunlu #35 still holds #162, so it was kept. "
                               "#162: Spoolman refused it: database is locked. Press Merge again to finish.")
        assert fake.deletes == []
        assert fake.vendor_of(162) == 35
        assert any(m.startswith("❌ Manufacturer merge Sunlu #35 → Sunlu #4: couldn't move Filament #162")
                   for m in _lines(logged, "ERROR"))
        # The second press: nothing left to carry, only #162 to move, then the delete.
        fake.patches.clear()
        r, _ = _merge(client, fake, 35, 4)
        assert r.status_code == 200, r.get_json()
        assert fake.vendor_patches() == []
        assert fake.filament_moves() == [162]
        assert fake.deletes == ["/api/v1/vendor/35"]
        assert r.get_json()["moved_filament_ids"] == [162]

    def test_a_filament_put_on_the_source_meanwhile_keeps_it(self, client):
        """Spoolman would clear its manufacturer at the delete: the re-list sees it first."""
        fake = _stocked()

        def put_one_on(n):
            if n == 2:
                fake.add("filament", 164, name="PETG Blue", material="PETG", vendor=fake.nested(35))
        fake.on_list_read = put_one_on
        r, _ = _merge(client, fake, 35, 4)
        body = r.get_json()
        assert r.status_code == 502
        assert body["still_on_source"] == [164]
        assert "Sunlu #35 still holds #164, so it was kept." in body["msg"]
        assert fake.deletes == []
        assert fake.vendor_of(164) == 35

    def test_a_relist_fcc_couldnt_read_keeps_the_source(self, client):
        fake = _stocked()
        fake.canned[("LIST", 2)] = _Resp(503, {"message": "database is locked"})
        r, _ = _merge(client, fake, 35, 4)
        body = r.get_json()
        assert r.status_code == 502
        assert body["source_kept"] is True
        assert body["moved_filament_ids"] == [160, 161, 162, 163]
        assert body["msg"] == ("Moved 4 of 4 filaments onto Sunlu #4, but couldn't check that Sunlu #35 holds none "
                               "now, so it was kept: Spoolman refused it: database is locked. "
                               "Press Merge again to finish.")
        assert fake.deletes == []

    def test_a_move_whose_answer_was_lost_but_landed_counts(self, client):
        fake = _stocked()
        fake.land_then_raise[("PATCH", "/api/v1/filament/161")] = requests.exceptions.ReadTimeout("read timed out")
        hub = []
        r, logged = _merge(client, fake, 35, 4, hub=hub)
        body = r.get_json()
        assert r.status_code == 200, body
        assert sorted(body["moved_filament_ids"]) == [160, 161, 162, 163]
        assert fake.deletes == ["/api/v1/vendor/35"]
        assert any("filament 161" in line and "but it landed" in line for lv, line in hub if lv == "WARNING")
        assert not _lines(logged, "ERROR")

    def test_a_refused_delete_keeps_the_source(self, client):
        fake = _stocked()
        fake.canned[("DELETE", "/api/v1/vendor/35")] = _Resp(500, {"message": "database is locked"})
        r, logged = _merge(client, fake, 35, 4)
        body = r.get_json()
        assert r.status_code == 502
        assert body["source_kept"] is True
        assert body["moved_filament_ids"] == [160, 161, 162, 163]
        assert body["msg"] == ("Moved 4 of 4 filaments onto Sunlu #4, but Sunlu #35 couldn't be "
                               "deleted: Spoolman refused it: database is locked. Press Merge again to finish.")
        assert any("couldn't be deleted" in m for m in _lines(logged, "ERROR"))

    def test_a_delete_whose_answer_was_lost_but_landed_succeeds(self, client):
        fake = _stocked()
        fake.land_then_raise[("DELETE", "/api/v1/vendor/35")] = requests.exceptions.ReadTimeout("read timed out")
        hub = []
        r, _ = _merge(client, fake, 35, 4, hub=hub)
        assert r.status_code == 200, r.get_json()
        assert 35 not in fake.records["vendor"]
        assert any("deleting vendor 35 reported a failure" in line for _lv, line in hub)

    def test_a_lost_delete_answer_fcc_cant_read_back_may_have_deleted(self, client):
        fake = _stocked()
        fake.land_then_raise[("DELETE", "/api/v1/vendor/35")] = requests.exceptions.ReadTimeout("read timed out")
        fake.reads_fail_after_delete = True
        r, logged = _merge(client, fake, 35, 4)
        body = r.get_json()
        assert r.status_code == 502
        assert body["may_have_deleted"] is True
        assert body["msg"].startswith("Moved 4 of 4 filaments onto Sunlu #4, but FCC couldn't tell "
                                      "whether Sunlu #35 was deleted: ")
        assert body["msg"].endswith("Press Merge again: it finishes the merge, or says Sunlu #35 is gone.")


# --- the carry ------------------------------------------------------------------------

class TestCarry:
    def test_a_field_both_hold_stays_the_kept_ones_and_is_named(self, client):
        fake = _stocked()
        fake.records["vendor"][35]["comment"] = "old <notes>"
        fake.records["vendor"][4]["comment"] = "new notes"
        r, logged = _merge(client, fake, 35, 4)
        body = r.get_json()
        assert r.status_code == 200, body
        assert fake.records["vendor"][4]["comment"] == "new notes"
        assert body["kept_own"] == {"comment": {"kept": "new notes", "other": "old <notes>"}}
        assert "Sunlu #35's notes “old <notes>” isn't kept: Sunlu #4 has its own (“new notes”)." in body["msg"]
        last = _lines(logged, "INFO")[-1]
        assert "“old &lt;notes&gt;”" in last and "<notes>" not in last

    def test_a_kept_weight_of_0_counts_as_blank(self, client):
        fake = _stocked()
        fake.records["vendor"][4]["empty_spool_weight"] = 0
        fake.records["vendor"][35]["empty_spool_weight"] = 170.0
        r, _ = _merge(client, fake, 35, 4)
        assert r.status_code == 200, r.get_json()
        assert fake.records["vendor"][4]["empty_spool_weight"] == 170.0

    def test_the_website_is_carried_and_the_name_never_is(self, client):
        fake = _stocked()
        fake.records["vendor"][39]["extra"] = {"website": '"https://jessie.example"'}
        fake.records["vendor"][39]["name"] = "JESSIE PREMIUM"
        r, _ = _merge(client, fake, 39, 38)
        assert r.status_code == 200, r.get_json()
        assert fake.records["vendor"][38]["extra"]["website"] == '"https://jessie.example"'
        assert fake.records["vendor"][38]["name"] == "Jessie Premium"
        assert all("name" not in body for _eid, body in fake.vendor_patches())

    def test_a_refused_carry_moves_nothing(self, client):
        fake = _stocked()
        fake.canned[("PATCH", "/api/v1/vendor/4")] = _Resp(500, {"message": "database is locked"})
        r, logged = _merge(client, fake, 35, 4)
        assert r.status_code == 502
        assert r.get_json()["msg"] == ("Couldn't copy Sunlu #35's External ID “Sunlu” onto Sunlu #4: Spoolman "
                                       "refused it: database is locked. Nothing was moved; try again in a moment.")
        assert fake.filament_moves() == [] and fake.deletes == []
        assert any("couldn't copy" in m for m in _lines(logged, "ERROR"))


# --- the dry run --------------------------------------------------------------------

class TestDryRun:
    def test_the_plan_writes_nothing_and_says_what_moves(self, client):
        fake = _stocked()
        r, logged = _merge(client, fake, 35, 4, body={"dry_run": True})
        body = r.get_json()
        assert r.status_code == 200, body
        assert body["dry_run"] is True and body["default_keep"] == 4
        plan = body["plan"]
        assert plan["source"]["id"] == 35 and plan["source"]["filaments"] == 4
        assert plan["target"]["id"] == 4 and plan["target"]["filaments"] == 5
        assert [f["id"] for f in plan["filaments"]] == [160, 161, 162, 163]
        assert plan["carry"] == {"external_id": "Sunlu"}
        assert plan["carry_words"] == ["External ID “Sunlu”"]
        assert plan["kept_own"] == {} and plan["kept_own_words"] == []
        assert plan["label_change"] is False
        assert plan["weight_note"] is None       # #160-#163 hold their own 168 g
        assert fake.patches == [] and fake.deletes == [] and logged == []

    def test_the_plan_says_which_to_keep_when_asked_the_other_way(self, client):
        fake = _stocked()
        r, _ = _merge(client, fake, 4, 35, body={"dry_run": True})
        assert r.get_json()["default_keep"] == 4

    def test_the_plan_runs_while_a_merge_holds_the_lock(self, client):
        fake = _stocked()
        assert routes_locations._VENDOR_MERGE_LOCK.acquire(False)
        try:
            r, _ = _merge(client, fake, 39, 38, body={"dry_run": True})
        finally:
            routes_locations._VENDOR_MERGE_LOCK.release()
        assert r.status_code == 200 and r.get_json()["default_keep"] == 38

    def test_the_plan_names_an_empty_weight_that_changes(self, client):
        fake = _stocked()
        r, _ = _merge(client, fake, 1, 4, body={"dry_run": True})
        plan = r.get_json()["plan"]
        assert plan["label_change"] is True
        assert plan["weight_note"] == {"moved_without_own": [300], "from_g": None, "to_g": 167.0,
                                       "kept_without_own": []}

    def test_a_carried_weight_the_moved_filaments_already_read_changes_nothing(self, client):
        fake = _stocked()
        r, _ = _merge(client, fake, 4, 35, body={"dry_run": True})
        plan = r.get_json()["plan"]
        assert plan["carry"] == {"empty_spool_weight": 167.0}
        # #160-#163 hold their own 168 g, and #100-#104 read 167 g before and after.
        assert plan["weight_note"] is None


# --- labels -------------------------------------------------------------------------

class TestLabels:
    def test_a_merge_of_two_different_names_marks_their_labels(self, client):
        fake = _stocked()
        r, logged = _merge(client, fake, 1, 4)
        body = r.get_json()
        assert r.status_code == 200, body
        assert body["label_change"] is True
        assert body["labels_flagged"] == {"spools": [301], "filaments": [300], "errors": []}
        assert fake.extra_writes("spool") == [301]           # not the archived #302, not #303 (flagged already)
        assert fake.records["spool"][301]["extra"]["needs_label_print"] == "true"
        assert fake.records["filament"][300]["extra"]["needs_label_print"] == "true"
        assert any(m.startswith("🏷️ 1 spool label and 1 filament swatch label marked as needing a reprint: "
                                "their Brand changed from Overture #1 to Sunlu #4")
                   for m in _lines(logged, "INFO"))

    def test_a_refused_label_mark_is_a_warning_and_the_merge_still_succeeds(self, client):
        fake = _stocked()
        fake.canned[("PATCH", "/api/v1/spool/301")] = _Resp(500, {"message": "database is locked"})
        r, logged = _merge(client, fake, 1, 4)
        body = r.get_json()
        assert r.status_code == 200, body
        assert body["labels_flagged"]["errors"] == [{"spool_id": 301, "error": "Spoolman refused it: database is locked"}]
        assert any("couldn't confirm that every label whose Brand changed is marked" in m for m in _lines(logged, "WARNING"))
        assert 1 not in fake.records["vendor"]


# --- escaping -----------------------------------------------------------------------

def test_names_and_spoolmans_text_are_escaped_in_every_log_line(client):
    fake = _stocked()
    fake.add("vendor", 50, name="<b>Acme & Co</b>", registered="2026-03-01T00:00:00Z")
    fake.add("filament", 500, name="<i>PLA</i>", material="PLA", vendor=fake.nested(50))
    fake.canned[("PATCH", "/api/v1/filament/500")] = _Resp(500, {"message": "<script>x</script>"})
    r, logged = _merge(client, fake, 50, 4)
    assert r.status_code == 502
    for msg, _lv in logged:
        assert "<b>" not in msg and "<i>" not in msg and "<script>" not in msg, msg
    assert any("&lt;b&gt;Acme &amp; Co&lt;/b&gt;" in m for m, _ in logged)


# --- merge_options ------------------------------------------------------------------

class TestMergeOptions:
    def test_the_three_same_name_groups_with_the_open_ones_first(self, client):
        fake = _stocked()
        r, _ = _options(client, fake, 35)
        body = r.get_json()
        assert r.status_code == 200, body
        assert body["vendor"]["id"] == 35 and body["vendor"]["filaments"] == 4
        assert [t["id"] for t in body["twins"]] == [4]
        assert [(g["kind"], g["ids"], g["keep"], g["mine"]) for g in body["groups"]] == [
            ("same_name", [4, 35], 4, True),
            ("same_name", [38, 39], 38, False),
            ("same_name", [9, 34], 9, False),
        ]
        rows = {v["id"]: v for v in body["vendors"]}
        assert rows[4]["filaments"] == 5 and rows[4]["empty_spool_weight"] == 167.0
        assert rows[34]["filaments"] == 0 and rows[34]["external_id"] == "Prusament"
        assert [v["name"] for v in body["vendors"]] == sorted((v["name"] for v in body["vendors"]), key=str.lower)

    def test_a_look_alike_name_makes_its_own_group(self, client):
        fake = _stocked()
        fake.add("vendor", 60, name="Jessie", registered="2026-05-01T00:00:00Z")
        r, _ = _options(client, fake, 60)
        groups = r.get_json()["groups"]
        # Only the pair across the two names: #39 is #38's twin under one name, its own
        # same_name group's pair (review round 1, S7: it was listed twice, once "similar").
        assert groups[0] == {"kind": "look_alike", "ids": [38, 60], "keep": 38, "mine": True}
        assert ("same_name", [38, 39]) in [(g["kind"], g["ids"]) for g in groups]
        assert r.get_json()["twins"] == []

    def test_a_vendor_list_fcc_couldnt_read_is_never_an_empty_list(self, client):
        fake = _stocked()
        fake.list_reads_fail = True
        r, _ = _options(client, fake, 35)
        assert r.status_code == 502
        assert r.get_json() == {"success": False, "msg": "Couldn't read the manufacturers from Spoolman, so the list "
                                                         "can't be shown. Try again in a moment."}

    @pytest.mark.parametrize("answer", [
        _Resp(503, {"message": "database is locked"}),
        _Resp(200, [{"id": 160, "vendor": {"id": "35"}}]),
    ], ids=["5xx", "bad-entry"])
    def test_a_filament_list_fcc_couldnt_read_is_never_an_empty_list(self, client, answer):
        fake = _stocked()
        fake.canned[("GET", "/api/v1/filament")] = answer
        r, _ = _options(client, fake, 35)
        assert r.status_code == 502
        assert r.get_json()["msg"].startswith("Couldn't count the manufacturers' filaments: ")

    def test_an_unknown_manufacturer_is_not_found(self, client):
        fake = _stocked()
        r, _ = _options(client, fake, 99)
        assert r.status_code == 404
        assert r.get_json()["msg"] == "Manufacturer #99 isn't in Spoolman any more (merged or deleted?)."


# --- the helpers --------------------------------------------------------------------

class TestHelpers:
    def _with(self, fake, fn):
        with patch.object(spoolman_api.config_loader, "get_api_urls", return_value=(SM, "http://fb.test")), \
             patch.object(spoolman_api.requests, "get", side_effect=fake.get), \
             patch.object(spoolman_api.requests, "delete", side_effect=fake.delete):
            return fn()

    def test_delete_vendor_answers_true_and_clears_the_last_error(self):
        fake = _stocked()
        spoolman_api.LAST_SPOOLMAN_ERROR = "earlier"
        assert self._with(fake, lambda: spoolman_api.delete_vendor(39)) is True
        assert spoolman_api.LAST_SPOOLMAN_ERROR is None

    @pytest.mark.parametrize("answer,last", [
        (_Resp(404, {"message": "No vendor with ID 77 found."}), 'HTTP 404: {"message": "No vendor with ID 77 found."}'),
        (_Resp(500, {"message": "database is locked"}), 'HTTP 500: {"message": "database is locked"}'),
        (requests.exceptions.ConnectionError("Connection refused (test)"), "Connection refused (test)"),
    ], ids=["4xx", "5xx", "no-answer"])
    def test_delete_vendor_answers_false_and_keeps_the_refusal(self, answer, last):
        fake = _stocked()
        fake.canned[("DELETE", "/api/v1/vendor/77")] = answer
        assert self._with(fake, lambda: spoolman_api.delete_vendor(77)) is False
        assert spoolman_api.LAST_SPOOLMAN_ERROR == last

    def test_get_vendor_answer_reads_as_get_filament_answer_does(self):
        fake = _stocked()
        rec, answered = self._with(fake, lambda: spoolman_api.get_vendor_answer(35))
        assert answered is True and spoolman_api.is_vendor_record(rec, 35)
        rec, answered = self._with(fake, lambda: spoolman_api.get_vendor_answer(77))
        assert answered is True and rec == {"message": "No vendor with ID 77 found."}
        fake.canned[("GET", "/api/v1/vendor/35")] = _Resp(500, {"message": "x"})
        assert self._with(fake, lambda: spoolman_api.get_vendor_answer(35)) == (None, True)
        fake.canned[("GET", "/api/v1/vendor/35")] = requests.exceptions.ConnectionError("down (test)")
        assert self._with(fake, lambda: spoolman_api.get_vendor_answer(35)) == (None, False)
        assert spoolman_api.is_vendor_record({"id": True}, 1) is False

    @pytest.mark.parametrize("a,b", [("Sun-lu", "Sunlu"), ("SUNLU", "sun lu"), ("Jessie  Premium", "jessie premium")])
    def test_the_same_name_ignoring_case_spaces_and_punctuation(self, a, b):
        assert spoolman_api.vendor_dup_key(a) == spoolman_api.vendor_dup_key(b)

    @pytest.mark.parametrize("a,b,alike", [
        ("Jessie", "Jessie Premium", True),
        ("Bambu", "Bambu Lab", True),
        ("Ziro", "ZIRO 3D", True),
        ("Overture", "Overtrue", True),
        ("3DO", "LDO", False), ("CC3D", "CR3D", False), ("CR3D", "R3D", False), ("Matter3D Inc", "R3D", False),
        ("Bambu", "Landu", False), ("eSun", "Sunlu", False), ("Sunlu", "Sunlu", False),
    ])
    def test_names_that_look_alike(self, a, b, alike):
        ka, kb = spoolman_api.vendor_dup_key(a), spoolman_api.vendor_dup_key(b)
        assert spoolman_api.vendor_names_look_alike(ka, kb) is alike


# --- review round 1 (2026-11-26): each finding that touches the server, pinned ------------

def _post_form(client, fake, path, form):
    """A POST whose body is a form, not JSON (curl -d), with Spoolman on `fake`."""
    with patch.object(spoolman_api.config_loader, "get_api_urls", return_value=(SM, "http://fb.test")), \
         patch.object(spoolman_api.requests, "get", side_effect=fake.get), \
         patch.object(spoolman_api.requests, "patch", side_effect=fake.patch), \
         patch.object(spoolman_api.requests, "delete", side_effect=fake.delete), \
         patch.object(state, "add_log_entry"):
        return client.post(path, data=form)


class TestTheMergeAsksForItself:
    """S5: any request but {"merge": true} (or a dry run) writes nothing. A dry run sent
    as a form reads as no JSON, and it merged."""

    @pytest.mark.parametrize("body", [None, {}, {"dry_run": "true"}, {"dry_run": 1}, {"merge": "yes"}, [1]],
                             ids=["no-body", "empty", "dry-run-text", "dry-run-1", "merge-text", "a-list"])
    def test_any_other_request_writes_nothing(self, client, body):
        fake = _stocked()
        r, _ = _call(client, fake, "POST", "/api/vendors/34/merge_into/9", body)
        assert r.status_code == 400
        assert "so nothing was merged" in r.get_json()["msg"]
        assert fake.get_urls == [] and fake.patches == [] and fake.deletes == []

    def test_a_dry_run_sent_as_a_form_merges_nothing(self, client):
        fake = _stocked()
        r = _post_form(client, fake, "/api/vendors/34/merge_into/9", {"dry_run": "true"})
        assert r.status_code == 400
        assert fake.deletes == [] and 34 in fake.records["vendor"]

    def test_a_dry_run_that_also_says_merge_is_a_dry_run(self, client):
        fake = _stocked()
        r, _ = _merge(client, fake, 34, 9, body={"dry_run": True, "merge": True})
        assert r.status_code == 200 and r.get_json()["dry_run"] is True
        assert fake.patches == [] and fake.deletes == []


class TestLastLookBeforeEachMove:
    """S6: each filament is read right before its write."""

    def test_a_filament_filed_elsewhere_meanwhile_is_left_where_it_is(self, client):
        fake = _stocked()

        def refile(n):
            if n == 1:      # its last look: someone filed it under Overture #1 just before
                fake.records["filament"][162]["vendor"] = fake.nested(1)
        fake.get_hooks["/api/v1/filament/162"] = refile
        r, _ = _merge(client, fake, 35, 4)
        body = r.get_json()
        assert r.status_code == 200, body
        assert body["moved_filament_ids"] == [160, 161, 163]
        assert body["left_meanwhile"] == [162] and fake.vendor_of(162) == 1
        assert 162 not in fake.filament_moves()
        assert "#162 left Sunlu #35 meanwhile, so FCC didn't move it." in body["msg"]

    def test_one_fcc_cant_read_just_before_its_move_is_not_written(self, client):
        fake = _stocked()
        fake.get_hooks["/api/v1/filament/162"] = (
            lambda n: _Resp(503, {"message": "database is locked"}) if n == 1 else None)
        r, _ = _merge(client, fake, 35, 4)
        body = r.get_json()
        assert r.status_code == 502 and body["still_on_source"] == [162]
        assert 162 not in fake.filament_moves() and fake.deletes == []


class TestReadBacks:
    """S3 / S4: a write that reported a failure is read back, and a read that fails is
    said as one, never as a fact."""

    def test_a_move_fcc_cant_read_back_is_said_as_unknown_and_its_labels_marked(self, client):
        fake = _stocked()
        fake.land_then_raise[("PATCH", "/api/v1/filament/300")] = requests.exceptions.ReadTimeout("read timed out")
        fake.get_hooks["/api/v1/filament/300"] = (
            lambda n: requests.exceptions.ConnectionError("down (test)") if n == 2 else None)
        r, logged = _merge(client, fake, 1, 4)
        body = r.get_json()
        assert r.status_code == 200, body
        assert body["unknown"] == [300] and body["left_meanwhile"] == [] and body["moved_filament_ids"] == []
        assert body["msg"].startswith("Merged Overture #1 into Sunlu #4: 0 filaments moved, Overture #1 deleted.")
        assert ("FCC couldn't tell where #300 went: its move's answer was lost, and it is no longer on "
                "Overture #1.") in body["msg"]
        assert "meanwhile" not in body["msg"]
        assert body["labels_flagged"]["spools"] == [301]
        assert any("couldn't tell where #300 went" in m for m in _lines(logged, "WARNING"))

    def test_a_carry_whose_answer_was_lost_but_landed_goes_on(self, client):
        fake = _stocked()
        fake.land_then_raise[("PATCH", "/api/v1/vendor/4")] = requests.exceptions.ReadTimeout("read timed out")
        hub = []
        r, logged = _merge(client, fake, 35, 4, hub=hub)
        body = r.get_json()
        assert r.status_code == 200, body
        assert body["carried"] == ["external_id"] and body["vendor"]["external_id"] == "Sunlu"
        assert any("took Sunlu #35's External ID" in m for m in _lines(logged, "INFO"))
        assert not _lines(logged, "ERROR")
        assert any("copying onto vendor 4 reported a failure" in line for _lv, line in hub)

    def test_a_carry_fcc_cant_read_back_says_so_and_moves_nothing(self, client):
        fake = _stocked()
        fake.land_then_raise[("PATCH", "/api/v1/vendor/4")] = requests.exceptions.ReadTimeout("read timed out")
        fake.get_hooks["/api/v1/vendor/4"] = (
            lambda n: requests.exceptions.ConnectionError("down (test)") if n >= 2 else None)
        r, logged = _merge(client, fake, 35, 4)
        msg = r.get_json()["msg"]
        assert r.status_code == 502
        assert msg.startswith("FCC couldn't tell whether Sunlu #35's External ID “Sunlu” was copied onto Sunlu #4: ")
        assert msg.endswith("Nothing was moved; try again in a moment.")
        assert fake.filament_moves() == [] and fake.deletes == []
        assert not _lines(logged, "ERROR") and _lines(logged, "WARNING")

    def test_a_refused_carry_answers_the_kept_ones_record(self, client):
        fake = _stocked()
        fake.canned[("PATCH", "/api/v1/vendor/4")] = _Resp(500, {"message": "database is locked"})
        r, _ = _merge(client, fake, 35, 4)
        assert r.status_code == 502 and r.get_json()["vendor"]["id"] == 4


class TestLabelsAfterTheDelete:
    """S1 / S2: the labels are marked after the delete, and on every return that stops
    before it."""

    def test_the_labels_are_marked_after_the_delete(self, client):
        fake = _stocked()
        r, _ = _merge(client, fake, 1, 4)
        assert r.status_code == 200, r.get_json()
        assert fake.ops.index(("DELETE", "/api/v1/vendor/1")) < fake.ops.index(("PATCH", "/api/v1/spool/301"))

    def test_a_relist_fcc_couldnt_read_still_marks_the_moved_ones_labels(self, client):
        fake = _stocked()
        fake.canned[("LIST", 2)] = _Resp(503, {"message": "database is locked"})
        r, logged = _merge(client, fake, 1, 4)
        body = r.get_json()
        assert r.status_code == 502 and body["source_kept"] is True
        assert body["labels_flagged"]["spools"] == [301] and body["labels_flagged"]["filaments"] == [300]
        assert any("couldn't check that Overture #1 holds none now, so it was kept" in m
                   for m in _lines(logged, "WARNING"))

    def test_a_relist_fcc_couldnt_read_names_the_moves_it_couldnt_decide(self, client):
        # A move whose answer never came (review round 2, S5: a refusal Spoolman answered
        # is told apart, below).
        fake = _stocked()
        fake.canned[("PATCH", "/api/v1/filament/162")] = requests.exceptions.ReadTimeout("read timed out")
        fake.canned[("LIST", 2)] = _Resp(503, {"message": "database is locked"})
        r, logged = _merge(client, fake, 35, 4)
        assert r.status_code == 502
        assert r.get_json()["unknown"] == [162]
        assert "FCC couldn't tell whether #162 moved: its move's answer was lost." in " ".join(
            _lines(logged, "WARNING"))

    def test_a_spool_list_fcc_couldnt_read_for_the_labels_is_a_warning(self, client):
        fake = _stocked()
        fake.get_hooks["/api/v1/spool"] = lambda n: _Resp(503, {"message": "database is locked"})
        r, logged = _merge(client, fake, 1, 4)
        body = r.get_json()
        assert r.status_code == 200, body
        flagged = body["labels_flagged"]
        assert flagged["spools"] == [] and flagged["filaments"] == [300]
        assert flagged["errors"] and "couldn't read the spool list" in flagged["errors"][0]["error"]
        assert any("couldn't confirm that every label" in m for m in _lines(logged, "WARNING"))


class TestLabelStatus:
    """T1: which moved filaments' swatches are marked."""

    def test_a_moved_filament_with_no_label_status_stays_unmarked(self, client):
        fake = _stocked()
        fake.records["filament"][300]["extra"] = {}
        r, _ = _merge(client, fake, 1, 4)
        flagged = r.get_json()["labels_flagged"]
        assert flagged["filaments"] == [] and flagged["spools"] == [301]

    def test_a_moved_filament_with_only_a_sample_printed_is_marked(self, client):
        fake = _stocked()
        fake.records["filament"][300]["extra"] = {"sample_printed": "true"}
        r, _ = _merge(client, fake, 1, 4)
        assert r.get_json()["labels_flagged"]["filaments"] == [300]


class TestKeepOrder:
    """T1: the tie-breaks of the manufacturer kept by default."""

    def test_equal_counts_keep_the_one_with_an_empty_weight(self, client):
        fake = _stocked()
        fake.add("vendor", 70, name="Acme", registered="2026-01-01T00:00:00Z")      # older, no weight
        fake.add("vendor", 71, name="Acme", empty_spool_weight=150.0, registered="2026-06-01T00:00:00Z")
        fake.add("filament", 700, name="A", material="PLA", vendor=fake.nested(70))
        fake.add("filament", 710, name="B", material="PLA", vendor=fake.nested(71))
        r, _ = _merge(client, fake, 71, 70, body={"dry_run": True})
        assert r.get_json()["default_keep"] == 71

    def test_equal_counts_and_no_weights_keep_the_older(self, client):
        fake = _stocked()
        fake.add("vendor", 70, name="Acme", registered="2026-06-01T00:00:00Z")
        fake.add("vendor", 71, name="Acme", registered="2026-01-01T00:00:00Z")
        r, _ = _merge(client, fake, 70, 71, body={"dry_run": True})
        assert r.get_json()["default_keep"] == 71

    def test_a_carried_weight_is_named_for_the_kept_ones_filaments_with_none(self, client):
        fake = _stocked()
        fake.add("filament", 164, name="PETG Blue", material="PETG", vendor=fake.nested(35))
        r, _ = _merge(client, fake, 4, 35, body={"dry_run": True})
        plan = r.get_json()["plan"]
        assert plan["carry"] == {"empty_spool_weight": 167.0}
        assert plan["weight_note"]["kept_without_own"] == [164]
        assert plan["weight_note"]["moved_without_own"] == []     # #100-#104 read 167 g before and after


class TestReviewRound2:
    """Review round 2: the re-list is the last read before the delete (S3), a landed move
    is marked whatever the re-list does (S2), and the words say what happened (S4-S6)."""

    def test_a_lost_answer_then_a_relist_fcc_couldnt_read_still_marks_the_landed_move(self, client):
        # S2: before, the lost answer waited for the re-list, which failed; the second
        # press listed nothing (#300 had moved) and #301's label was never marked.
        fake = _stocked()
        fake.land_then_raise[("PATCH", "/api/v1/filament/300")] = requests.exceptions.ReadTimeout("read timed out")
        fake.canned[("LIST", 2)] = _Resp(503, {"message": "database is locked"})
        r, logged = _merge(client, fake, 1, 4)
        body = r.get_json()
        assert r.status_code == 502 and body["source_kept"] is True
        assert body["moved_filament_ids"] == [300] and fake.vendor_of(300) == 4
        assert body["labels_flagged"]["spools"] == [301]
        assert "weren't marked" not in " ".join(_lines(logged))

    def test_a_lost_answer_fcc_cant_read_back_is_marked_in_case_it_moved(self, client):
        fake = _stocked()
        fake.land_then_raise[("PATCH", "/api/v1/filament/300")] = requests.exceptions.ReadTimeout("read timed out")
        fake.get_hooks["/api/v1/filament/300"] = (
            lambda n: requests.exceptions.ConnectionError("down (test)") if n == 2 else None)
        fake.canned[("LIST", 2)] = _Resp(503, {"message": "database is locked"})
        r, logged = _merge(client, fake, 1, 4)
        body = r.get_json()
        assert r.status_code == 502 and body["unknown"] == [300]
        assert body["labels_flagged"]["spools"] == [301]
        assert "FCC couldn't tell whether #300 moved: its move's answer was lost." in " ".join(
            _lines(logged, "WARNING"))

    def test_the_relist_is_the_last_read_before_the_delete(self, client):
        # S3: three moves whose answers were lost are read back BEFORE the re-list.
        fake = _stocked()
        for fid in (160, 161, 162):
            fake.land_then_raise[("PATCH", f"/api/v1/filament/{fid}")] = requests.exceptions.ReadTimeout(
                "read timed out")
        r, _ = _merge(client, fake, 35, 4)
        assert r.status_code == 200, r.get_json()
        assert sorted(r.get_json()["moved_filament_ids"]) == [160, 161, 162, 163]
        i = fake.ops.index(("DELETE", "/api/v1/vendor/35"))
        assert fake.ops[i - 1] == ("GET", "/api/v1/filament?vendor.id=35"), fake.ops[i - 4:i + 1]
        relist = i - 1
        for fid in (160, 161, 162):
            gets = [k for k, op in enumerate(fake.ops) if op == ("GET", f"/api/v1/filament/{fid}")]
            assert len(gets) == 2 and gets[-1] < relist      # the last look, then the read-back

    def test_a_refusal_spoolman_answered_is_never_read_back(self, client):
        fake = _stocked()
        fake.canned[("PATCH", "/api/v1/filament/162")] = _Resp(500, {"message": "database is locked"})
        r, logged = _merge(client, fake, 35, 4)
        assert r.status_code == 502 and r.get_json()["still_on_source"] == [162]
        assert fake.ops.count(("GET", "/api/v1/filament/162")) == 1        # the last look only
        assert any("couldn't move Filament #162" in m for m in _lines(logged, "ERROR"))

    def test_a_refused_delete_names_a_filament_that_left_meanwhile(self, client):
        # S4 (a): "All of Sunlu #35's filaments are on Sunlu #4 now" and "every filament
        # moved" of a merge that left #162 on Overture #1, which no line named.
        fake = _stocked()

        def refile(n):
            if n == 1:
                fake.records["filament"][162]["vendor"] = fake.nested(1)
        fake.get_hooks["/api/v1/filament/162"] = refile
        fake.canned[("DELETE", "/api/v1/vendor/35")] = _Resp(500, {"message": "database is locked"})
        r, logged = _merge(client, fake, 35, 4)
        body = r.get_json()
        assert r.status_code == 502 and body["left_meanwhile"] == [162]
        assert body["msg"] == ("Moved 3 of 4 filaments onto Sunlu #4, but Sunlu #35 couldn't be deleted: Spoolman "
                               "refused it: database is locked. #162 left Sunlu #35 meanwhile, so FCC didn't move "
                               "it. Press Merge again to finish.")
        assert any("#162 left Sunlu #35 meanwhile" in m for m in _lines(logged, "ERROR"))
        assert not any("every filament moved" in m for m in _lines(logged))

    def test_an_unconfirmed_delete_names_a_move_fcc_couldnt_place(self, client):
        # S4 (b): "couldn't tell where #160 went", then "All of … are on … now".
        fake = _stocked()
        fake.land_then_raise[("PATCH", "/api/v1/filament/160")] = requests.exceptions.ReadTimeout("read timed out")
        fake.get_hooks["/api/v1/filament/160"] = (
            lambda n: requests.exceptions.ConnectionError("down (test)") if n == 2 else None)
        fake.land_then_raise[("DELETE", "/api/v1/vendor/35")] = requests.exceptions.ReadTimeout("read timed out")
        fake.reads_fail_after_delete = True
        r, _ = _merge(client, fake, 35, 4)
        body = r.get_json()
        assert r.status_code == 502 and body["may_have_deleted"] is True and body["unknown"] == [160]
        assert body["msg"].startswith("Moved 3 of 4 filaments onto Sunlu #4, but FCC couldn't tell whether "
                                      "Sunlu #35 was deleted: ")
        assert "FCC couldn't tell where #160 went" in body["msg"]
        assert body["msg"].endswith("Press Merge again: it finishes the merge, or says Sunlu #35 is gone.")

    def test_a_refused_delete_of_one_that_held_none_says_so(self, client):
        # S4 (c): Derek's empty Prusament #34.
        fake = _stocked()
        fake.canned[("DELETE", "/api/v1/vendor/34")] = _Resp(500, {"message": "database is locked"})
        r, logged = _merge(client, fake, 34, 9)
        assert r.status_code == 502
        assert r.get_json()["msg"] == ("Prusament #34 held no filaments, but couldn't be deleted: Spoolman refused "
                                       "it: database is locked. Press Merge again to finish.")
        assert not any("every filament moved" in m for m in _lines(logged))

    def test_a_same_name_relist_failure_names_each_move_for_what_it_was(self, client):
        # S5: Sunlu #35 into #4 (no label changes); #161 never written, #162 refused.
        fake = _stocked()
        fake.get_hooks["/api/v1/filament/161"] = (
            lambda n: _Resp(503, {"message": "database is locked"}) if n == 1 else None)
        fake.canned[("PATCH", "/api/v1/filament/162")] = _Resp(500, {"message": "database is locked"})
        fake.canned[("LIST", 2)] = _Resp(503, {"message": "database is locked"})
        r, logged = _merge(client, fake, 35, 4)
        assert r.status_code == 502
        warned = " ".join(_lines(logged, "WARNING"))
        assert ("Moved 2 of 4 filaments onto Sunlu #4, but couldn't check that Sunlu #35 holds none now, "
                "so it was kept.") in warned
        assert "FCC didn't move #161: it couldn't read it from Spoolman first." in warned
        assert "Couldn't move #162 (HTTP 500" in warned
        assert "label" not in warned and "couldn't tell whether" not in warned

    def test_one_filament_reads_as_one(self, client):
        fake = _stocked()
        fake.canned[("LIST", 2)] = _Resp(503, {"message": "database is locked"})
        r, logged = _merge(client, fake, 1, 4)
        assert r.get_json()["msg"].startswith("Moved 1 of 1 filament onto Sunlu #4, but couldn't check")
        assert any("Moved 1 of 1 filament onto" in m for m in _lines(logged, "WARNING"))

    def test_a_filament_put_back_meanwhile_is_still_there_and_never_left_meanwhile(self, client):
        # S6: filed under Overture #1 at its last look, put back on #35 before the re-list.
        fake = _stocked()

        def refile(n):
            if n == 1:
                fake.records["filament"][162]["vendor"] = fake.nested(1)
        fake.get_hooks["/api/v1/filament/162"] = refile

        def put_back(n):
            if n == 2:
                fake.records["filament"][162]["vendor"] = fake.nested(35)
        fake.on_list_read = put_back
        r, _ = _merge(client, fake, 35, 4)
        body = r.get_json()
        assert r.status_code == 502 and body["still_on_source"] == [162]
        assert body["left_meanwhile"] == [] and "meanwhile" not in body["msg"]

    def test_a_carried_extra_the_record_holds_blank_never_counts_as_landed(self):
        # S7: str(None) is "None".
        assert routes_locations._carry_landed({"id": 4, "extra": {}}, {"extra": {"website": '"None"'}}) is False
        assert routes_locations._carry_landed({"id": 4, "extra": {"website": '""'}},
                                              {"extra": {"website": '"None"'}}) is False
        assert routes_locations._carry_landed({"id": 4, "extra": {"website": '"None"'}},
                                              {"extra": {"website": '"None"'}}) is True
