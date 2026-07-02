"""L316 characterization tests — pins pre-carve behavior of the L58
filament-attributes manager endpoints (app.py ~5590-6095). Generated from
the 2026-07-01 coverage audit. Do not weaken these to make a refactor pass.

Surface under test (all host-runnable, everything outbound mocked):
  GET  /api/filament_attributes/report        — aggregation shape + sort
  POST /api/filament_attributes/bulk_set      — per-id error surface
  POST /api/filament_attributes/add_choice    — delegation + passthrough
  POST /api/filament_attributes/remove_choice — the ~170-line destructive
        schema migration (DELETE -> POST recreate -> per-filament restore)
  POST /api/filament_attributes/sweep_unused  — transient guard + schema
        failure branches

Why unit: every prior behavioral test for these routes lives in
test_filament_attributes_bulk_api.py and needs BOTH the live dev container
and live Spoolman — an offline refactor sweep skips them and goes
false-green. These tests are the offline tripwire.

Mocking layer: the handlers do `import requests as _req` FUNCTION-LOCALLY,
which resolves to the singleton `requests` module — so patching
requests.get/delete/post/patch covers every wire call. bulk_set is the
exception: it goes through spoolman_api.get_filament/update_filament, so
those are patched at the spoolman_api layer instead.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import app as app_module  # noqa: E402
import requests as requests_module  # noqa: E402

SM_URL = "http://spoolman.test"


@pytest.fixture
def client():
    app_module.app.config['TESTING'] = True
    with app_module.app.test_client() as c:
        yield c


class _Resp:
    """Minimal stand-in for requests.Response — just what the handlers read."""

    def __init__(self, *, ok=True, status_code=200, payload=None, text=""):
        self.ok = ok
        self.status_code = status_code
        self._payload = payload
        self.text = text

    def json(self):
        return self._payload


def _attr_field(choices, **over):
    d = {"key": "filament_attributes", "name": "Filament Attributes",
         "field_type": "choice", "multi_choice": True, "choices": list(choices)}
    d.update(over)
    return d


def _install_wire(monkeypatch, *, fields=None, filaments=None,
                  field_resp=None, filament_resp=None,
                  delete_resp=None, post_resp=None, patch_resps=None):
    """Patch the module-global `requests` verbs + config_loader.get_api_urls.

    Returns the ordered call log: [(method, url, json_payload), ...] so
    tests can pin operation ORDERING (the destructive-migration contract).
    A `filament_resp`/`field_resp` that is an Exception instance is raised
    (to exercise the `except Exception` wrappers).
    """
    calls = []
    if field_resp is None:
        field_resp = _Resp(payload=fields if fields is not None else [])
    if filament_resp is None:
        filament_resp = _Resp(payload=filaments if filaments is not None else [])
    delete_resp = delete_resp or _Resp(status_code=204)
    post_resp = post_resp or _Resp()
    patch_resps = patch_resps or {}

    def fake_get(url, **kw):
        calls.append(("GET", url, None))
        if url.endswith("/api/v1/field/filament"):
            r = field_resp
        elif url.endswith("/api/v1/filament"):
            r = filament_resp
        else:
            raise AssertionError(f"unexpected GET {url}")
        if isinstance(r, Exception):
            raise r
        return r

    def fake_delete(url, **kw):
        calls.append(("DELETE", url, None))
        return delete_resp

    def fake_post(url, json=None, **kw):
        calls.append(("POST", url, json))
        return post_resp

    def fake_patch(url, json=None, **kw):
        calls.append(("PATCH", url, json))
        fid = int(url.rstrip("/").rsplit("/", 1)[-1])
        return patch_resps.get(fid, _Resp())

    monkeypatch.setattr(requests_module, "get", fake_get)
    monkeypatch.setattr(requests_module, "delete", fake_delete)
    monkeypatch.setattr(requests_module, "post", fake_post)
    monkeypatch.setattr(requests_module, "patch", fake_patch)
    monkeypatch.setattr(app_module.config_loader, "get_api_urls",
                        lambda: (SM_URL, SM_URL))
    return calls


def _methods(calls):
    return [m for (m, _u, _j) in calls]


def _capture_logs(monkeypatch):
    """Capture every state.add_log_entry call as (msg, args, kwargs)."""
    entries = []
    monkeypatch.setattr(
        app_module.state, "add_log_entry",
        lambda msg, *a, **k: entries.append((msg, a, k)),
    )
    return entries


# ---------------------------------------------------------------------------
# GET /api/filament_attributes/report
# ---------------------------------------------------------------------------

def test_report_aggregation_shape_and_sort(client, monkeypatch):
    """Pins the report envelope: choices verbatim from the field def,
    per-choice counts seeded to 0, per-filament entry shape (with defaults
    for missing keys), id-less rows skipped, and the sort key —
    archived LAST, then vendor/material/name case-insensitive, then id."""
    fields = [{"key": "other_field"}, _attr_field(["Silk", "Matte"])]
    filaments = [
        {"id": 5, "name": "Zed", "material": "PLA",
         "vendor": {"name": "Zebra"}, "color_hex": "112233",
         "archived": False,
         "extra": {"filament_attributes": '["Silk"]'}},
        # lowercase vendor sorts before "Zebra" ONLY if the compare is
        # case-insensitive ('acme' < 'zebra'; case-sensitive ASCII would
        # put 'Zebra' first).
        {"id": 4, "name": "Alpha", "material": "PETG",
         "vendor": {"name": "acme"},
         "extra": {"filament_attributes": '["Silk"]'}},
        # archived sorts last regardless of vendor.
        {"id": 9, "name": "Old", "material": "PLA",
         "vendor": {"name": "Acme"}, "archived": True, "extra": None},
        # no id -> skipped entirely.
        {"name": "no-id-row", "extra": {"filament_attributes": '["Silk"]'}},
    ]
    _install_wire(monkeypatch, fields=fields, filaments=filaments)

    r = client.get("/api/filament_attributes/report")
    assert r.status_code == 200
    body = r.get_json()
    assert body["success"] is True
    assert body["choices"] == ["Silk", "Matte"]
    assert [f["id"] for f in body["filaments"]] == [4, 5, 9]
    # zero-usage choices still appear in counts (seeded from choices).
    assert body["counts"] == {"Silk": 2, "Matte": 0}
    # Entry shape incl. defaults: no archived key -> False, no color_hex -> "".
    assert body["filaments"][0] == {
        "id": 4, "name": "Alpha", "material": "PETG", "vendor": "acme",
        "color_hex": "", "archived": False, "attributes": ["Silk"],
    }
    # extra=None tolerated -> attributes [].
    assert body["filaments"][2]["archived"] is True
    assert body["filaments"][2]["attributes"] == []


def test_report_counts_can_gain_keys_outside_choices(client, monkeypatch):
    """A filament carrying an attribute NOT in the schema choice list adds
    that rogue key to `counts`.
    # NOTE: pins current behavior; see suspected_bugs — the live test
    # (test_filament_attributes_bulk_api.test_report_shape) asserts counts
    # keys are a SUBSET of choices, which this data would violate."""
    fields = [_attr_field(["Silk"])]
    filaments = [{"id": 1, "extra": {"filament_attributes": '["Rogue"]'}}]
    _install_wire(monkeypatch, fields=fields, filaments=filaments)

    body = client.get("/api/filament_attributes/report").get_json()
    assert body["success"] is True
    assert body["counts"] == {"Silk": 0, "Rogue": 1}


def test_report_field_list_http_error(client, monkeypatch):
    """A non-ok field-list fetch short-circuits with HTTP 200 + success:false
    and the status code in msg; the filament list is never fetched."""
    calls = _install_wire(monkeypatch,
                          field_resp=_Resp(ok=False, status_code=503))
    r = client.get("/api/filament_attributes/report")
    assert r.status_code == 200
    assert r.get_json() == {"success": False,
                            "msg": "Spoolman field list HTTP 503"}
    assert _methods(calls) == ["GET"]  # only the field-list call fired


def test_report_filament_list_exception(client, monkeypatch):
    """A raising filament-list fetch is swallowed into success:false with the
    exception text — no 500."""
    _install_wire(monkeypatch, fields=[_attr_field(["Silk"])],
                  filament_resp=RuntimeError("conn boom"))
    r = client.get("/api/filament_attributes/report")
    assert r.status_code == 200
    assert r.get_json() == {"success": False,
                            "msg": "Spoolman filament list error: conn boom"}


# ---------------------------------------------------------------------------
# POST /api/filament_attributes/bulk_set
# ---------------------------------------------------------------------------

def test_bulk_set_rejects_missing_or_nonlist_ids(client):
    """filament_ids absent, empty, or not-a-list -> 400 with the exact msg."""
    for payload in ({}, {"filament_ids": []}, {"filament_ids": "notalist"}):
        payload = dict(payload, add=["X"])
        r = client.post("/api/filament_attributes/bulk_set", json=payload)
        assert r.status_code == 400
        assert r.get_json() == {
            "success": False, "msg": "filament_ids must be a non-empty list"}


def test_bulk_set_rejects_noop_payload(client):
    """ids present but neither add nor remove -> 400."""
    r = client.post("/api/filament_attributes/bulk_set",
                    json={"filament_ids": [1]})
    assert r.status_code == 400
    body = r.get_json()
    assert body["success"] is False
    assert body["msg"].startswith("Nothing to do")


def test_bulk_set_per_id_error_surface_and_warning_log(client, monkeypatch):
    """The per-id error taxonomy: non-integer id -> 'not an integer id',
    get_filament None -> 'filament not found', update_filament None ->
    LAST_SPOOLMAN_ERROR propagated verbatim into errors[]. Partial success
    still counts `updated`, and errors escalate the summary log to
    WARNING/ffaa00.
    # NOTE: pins current behavior — top-level success stays True even when
    # some ids errored; callers must read errors[], not success."""
    fils = {
        5: {"id": 5, "extra": {"filament_attributes": '["Old"]'}},
        7: {"id": 7, "extra": {}},
    }
    monkeypatch.setattr(app_module.spoolman_api, "get_filament",
                        lambda fid: fils.get(fid))
    update_calls = []

    def fake_update(fid, data):
        update_calls.append((fid, data))
        return None if fid == 5 else {"id": fid}

    monkeypatch.setattr(app_module.spoolman_api, "update_filament", fake_update)
    monkeypatch.setattr(app_module.spoolman_api, "LAST_SPOOLMAN_ERROR",
                        "HTTP 422: nope")
    logs = _capture_logs(monkeypatch)

    r = client.post("/api/filament_attributes/bulk_set",
                    json={"filament_ids": ["abc", 999, 5, 7], "add": ["New"]})
    assert r.status_code == 200
    body = r.get_json()
    assert body["success"] is True
    assert body["updated"] == 1
    assert body["unchanged"] == 0
    assert body["errors"] == [
        {"id": "abc", "msg": "not an integer id"},
        {"id": 999, "msg": "filament not found"},
        {"id": 5, "msg": "HTTP 422: nope"},
    ]
    assert [c[0] for c in update_calls] == [5, 7]
    assert len(logs) == 1
    msg, a, _k = logs[0]
    assert "bulk-set" in msg
    assert a == ("WARNING", "ffaa00")


def test_bulk_set_null_last_error_falls_back_to_unknown(client, monkeypatch):
    """update_filament None while LAST_SPOOLMAN_ERROR is unset -> the per-id
    msg falls back to 'unknown error' (the `or` guard)."""
    monkeypatch.setattr(app_module.spoolman_api, "get_filament",
                        lambda fid: {"id": fid, "extra": {}})
    monkeypatch.setattr(app_module.spoolman_api, "update_filament",
                        lambda fid, data: None)
    monkeypatch.setattr(app_module.spoolman_api, "LAST_SPOOLMAN_ERROR", None)
    _capture_logs(monkeypatch)

    body = client.post("/api/filament_attributes/bulk_set",
                       json={"filament_ids": [3], "add": ["X"]}).get_json()
    assert body["errors"] == [{"id": 3, "msg": "unknown error"}]


def test_bulk_set_partial_success_counts_and_merge_order(client, monkeypatch):
    """Pins the merge contract: surviving existing attrs keep their order,
    newly-added attrs append in user order, and a filament whose set is
    already correct counts as `unchanged` WITHOUT a Spoolman write. The
    written payload is the JSON-string wire form under extra."""
    fils = {
        1: {"id": 1, "extra": {"filament_attributes": '["Silk", "Matte"]'}},
        2: {"id": 2, "extra": {"filament_attributes": '["Zeta", "Silk"]'}},
    }
    monkeypatch.setattr(app_module.spoolman_api, "get_filament",
                        lambda fid: fils.get(fid))
    update_calls = []

    def fake_update(fid, data):
        update_calls.append((fid, data))
        return {"id": fid}

    monkeypatch.setattr(app_module.spoolman_api, "update_filament", fake_update)
    logs = _capture_logs(monkeypatch)

    body = client.post(
        "/api/filament_attributes/bulk_set",
        json={"filament_ids": [1, 2], "add": ["Zeta", "Silk"],
              "remove": ["Matte"]},
    ).get_json()
    assert body == {"success": True, "updated": 1, "unchanged": 1,
                    "errors": []}
    # fid 1: keep "Silk" (order preserved), drop "Matte", append "Zeta".
    assert update_calls == [
        (1, {"extra": {"filament_attributes": '["Silk", "Zeta"]'}}),
    ]
    # No errors -> INFO/00ccff summary line.
    assert len(logs) == 1
    assert logs[0][1] == ("INFO", "00ccff")


# ---------------------------------------------------------------------------
# POST /api/filament_attributes/add_choice
# ---------------------------------------------------------------------------

def test_add_choice_requires_choice(client):
    """Blank / missing choice -> 400 with the exact msg."""
    r = client.post("/api/filament_attributes/add_choice", json={"choice": "  "})
    assert r.status_code == 400
    assert r.get_json() == {"success": False, "msg": "choice is required"}


def test_add_choice_rejects_over_80_chars(client):
    r = client.post("/api/filament_attributes/add_choice",
                    json={"choice": "x" * 81})
    assert r.status_code == 400
    assert r.get_json() == {"success": False,
                            "msg": "choice too long (max 80 chars)"}


def test_add_choice_delegates_and_passes_through(client, monkeypatch):
    """The handler is a thin wrapper: choice is stripped, delegated to
    update_extra_field_choices('filament', 'filament_attributes', [choice]),
    the delegate's dict is returned VERBATIM, and success writes an
    INFO/00ccff activity-log line naming the choice."""
    delegate_calls = []
    sentinel = {"success": True, "merged": ["A", "Silk"], "anything": 1}

    def fake_delegate(entity, key, new_choices):
        delegate_calls.append((entity, key, new_choices))
        return sentinel

    monkeypatch.setattr(app_module.spoolman_api, "update_extra_field_choices",
                        fake_delegate)
    logs = _capture_logs(monkeypatch)

    r = client.post("/api/filament_attributes/add_choice",
                    json={"choice": "  Silk  "})
    assert r.status_code == 200
    assert r.get_json() == sentinel
    assert delegate_calls == [("filament", "filament_attributes", ["Silk"])]
    assert len(logs) == 1
    msg, a, _k = logs[0]
    assert "added choice 'Silk'" in msg
    assert a == ("INFO", "00ccff")


def test_add_choice_failure_passthrough_no_log(client, monkeypatch):
    """A failing delegate result is passed through untouched (still HTTP 200)
    and does NOT write an activity-log entry."""
    monkeypatch.setattr(app_module.spoolman_api, "update_extra_field_choices",
                        lambda *a: {"success": False, "msg": "boom"})
    logs = _capture_logs(monkeypatch)

    r = client.post("/api/filament_attributes/add_choice",
                    json={"choice": "Silk"})
    assert r.status_code == 200
    assert r.get_json() == {"success": False, "msg": "boom"}
    assert logs == []


# ---------------------------------------------------------------------------
# POST /api/filament_attributes/remove_choice — the destructive migration
# ---------------------------------------------------------------------------

def _remove_fixture():
    fields = [_attr_field(["A", "B"])]
    filaments = [
        # carries the doomed choice + a sibling extra that MUST survive.
        {"id": 1, "extra": {"filament_attributes": '["A"]',
                            "product_url": '"http://x"'}},
        # siblings only — still snapshotted + restored (full-extras cycle).
        {"id": 2, "extra": {"product_url": '"y"'}},
        # no extras at all — never snapshotted, never PATCHed.
        {"id": 3},
    ]
    return fields, filaments


def test_remove_choice_requires_choice(client):
    r = client.post("/api/filament_attributes/remove_choice", json={})
    assert r.status_code == 400
    assert r.get_json() == {"success": False, "msg": "choice is required"}


def test_remove_choice_unknown_choice_and_missing_field(client, monkeypatch):
    """Choice not in the schema list -> HTTP 200 success:false (repr'd name)
    and the filament list is never fetched. Missing filament_attributes
    field entirely -> its own success:false msg."""
    fields, filaments = _remove_fixture()
    calls = _install_wire(monkeypatch, fields=fields, filaments=filaments)
    r = client.post("/api/filament_attributes/remove_choice",
                    json={"choice": "Z"})
    assert r.status_code == 200
    assert r.get_json() == {"success": False,
                            "msg": "'Z' is not a current choice"}
    assert _methods(calls) == ["GET"]  # field list only

    _install_wire(monkeypatch, fields=[{"key": "other"}])
    body = client.post("/api/filament_attributes/remove_choice",
                       json={"choice": "A"}).get_json()
    assert body == {"success": False,
                    "msg": "filament_attributes field not found"}


def test_remove_choice_usage_requires_force(client, monkeypatch):
    """usage > 0 without force -> needs_confirm + usage_count, and NOTHING
    destructive fires (no DELETE)."""
    fields, filaments = _remove_fixture()
    calls = _install_wire(monkeypatch, fields=fields, filaments=filaments)

    body = client.post("/api/filament_attributes/remove_choice",
                       json={"choice": "A"}).get_json()
    assert body["success"] is False
    assert body["needs_confirm"] is True
    assert body["usage_count"] == 1
    assert "force=true" in body["msg"]
    assert "DELETE" not in _methods(calls)


def test_remove_choice_schema_delete_failure_aborts(client, monkeypatch):
    """A non-404 DELETE failure aborts the whole migration: success:false
    with the status + body in msg, and neither the recreate POST nor any
    restore PATCH is issued."""
    fields, filaments = _remove_fixture()
    calls = _install_wire(monkeypatch, fields=fields, filaments=filaments,
                          delete_resp=_Resp(ok=False, status_code=500,
                                            text="boom"))
    body = client.post("/api/filament_attributes/remove_choice",
                       json={"choice": "A", "force": True}).get_json()
    assert body == {"success": False,
                    "msg": "Schema DELETE failed (500): boom"}
    methods = _methods(calls)
    assert "POST" not in methods
    assert "PATCH" not in methods


def test_remove_choice_delete_404_tolerated(client, monkeypatch):
    """A 404 on the schema DELETE (field already gone) is tolerated — the
    migration proceeds to recreate + restore and succeeds."""
    fields, filaments = _remove_fixture()
    calls = _install_wire(monkeypatch, fields=fields, filaments=filaments,
                          delete_resp=_Resp(ok=False, status_code=404,
                                            text="not found"))
    body = client.post("/api/filament_attributes/remove_choice",
                       json={"choice": "A", "force": True}).get_json()
    assert body["success"] is True
    assert body["restored"] == 2
    assert _methods(calls) == ["GET", "GET", "DELETE", "POST", "PATCH", "PATCH"]


def test_remove_choice_recreate_failure_reports_missing_schema(client, monkeypatch):
    """DELETE ok + recreate POST failing is the worst case: the field is now
    MISSING from Spoolman. Pins the response msg naming that state + the
    setup_fields.py remediation, the ERROR/ff4444 activity-log entry, and
    that NO restore PATCH is attempted afterward."""
    fields, filaments = _remove_fixture()
    calls = _install_wire(monkeypatch, fields=fields, filaments=filaments,
                          post_resp=_Resp(ok=False, status_code=500,
                                          text="kaput"))
    logs = _capture_logs(monkeypatch)

    body = client.post("/api/filament_attributes/remove_choice",
                       json={"choice": "A", "force": True}).get_json()
    assert body == {
        "success": False,
        "msg": ("Schema POST failed: kaput. Schema is now MISSING — "
                "re-run setup_fields.py."),
    }
    assert "PATCH" not in _methods(calls)
    assert len(logs) == 1
    msg, a, _k = logs[0]
    assert "POST recreate failed (500)" in msg
    assert "Re-run setup_fields.py" in msg
    assert a == ("ERROR", "ff4444")


def test_remove_choice_restore_failure_collected_and_continues(client, monkeypatch):
    """A failing per-filament restore PATCH is collected into
    restore_failures (with the HTTP status + body) but the loop CONTINUES —
    the remaining filaments are still restored, the overall response stays
    success:true, and the summary log escalates to WARNING/ffaa00."""
    fields, filaments = _remove_fixture()
    calls = _install_wire(
        monkeypatch, fields=fields, filaments=filaments,
        patch_resps={1: _Resp(ok=False, status_code=422, text="bad value")})
    logs = _capture_logs(monkeypatch)

    body = client.post("/api/filament_attributes/remove_choice",
                       json={"choice": "A", "force": True}).get_json()
    assert body["success"] is True
    assert body["stripped"] == 1
    assert body["restored"] == 1
    assert body["restore_failures"] == [{"id": 1, "msg": "HTTP 422: bad value"}]
    # Both restores were ATTEMPTED (failure did not abort the loop).
    patch_urls = [u for (m, u, _j) in calls if m == "PATCH"]
    assert [u.rsplit("/", 1)[-1] for u in patch_urls] == ["1", "2"]
    assert len(logs) == 1
    msg, a, _k = logs[0]
    assert "1 restore failure(s)" in msg
    assert a == ("WARNING", "ffaa00")


def test_remove_choice_happy_path_order_and_payloads(client, monkeypatch):
    """Pins the full destructive-migration contract:
      - operation ORDER: snapshot reads (GET field, GET filaments) ->
        schema DELETE -> schema POST recreate -> restore PATCHes. Restores
        fire ONLY after a successful recreate.
        # NOTE: pins current behavior; see suspected_bugs — the handler's
        # docstring claims filaments are stripped BEFORE the schema delete,
        # but the implementation deletes/recreates the schema FIRST and
        # strips during the restore loop afterward.
      - recreate payload carries name/field_type/multi_choice from the old
        field def and the sorted survivor choice list.
      - every restore body is the filament's FULL extras dict (siblings
        preserved) with the removed choice filtered out of
        filament_attributes; filaments with no extras are never PATCHed —
        but sibling-only filaments ARE (full restore cycle), so `restored`
        counts snapshot entries, not just carriers.
      - INFO/00ccff summary log on the clean path."""
    fields, filaments = _remove_fixture()
    calls = _install_wire(monkeypatch, fields=fields, filaments=filaments)
    logs = _capture_logs(monkeypatch)

    r = client.post("/api/filament_attributes/remove_choice",
                    json={"choice": "A", "force": True})
    assert r.status_code == 200
    assert r.get_json() == {"success": True, "stripped": 1, "restored": 2,
                            "restore_failures": []}

    assert _methods(calls) == ["GET", "GET", "DELETE", "POST", "PATCH", "PATCH"]
    assert calls[0][1].endswith("/api/v1/field/filament")
    assert calls[1][1].endswith("/api/v1/filament")
    assert calls[2][1].endswith("/api/v1/field/filament/filament_attributes")
    # Recreate payload: survivors only, metadata copied from the old def.
    assert calls[3][2] == {"name": "Filament Attributes",
                           "field_type": "choice",
                           "multi_choice": True,
                           "choices": ["B"]}
    # Restore bodies: FULL extras, choice stripped, siblings intact.
    patches = {u.rsplit("/", 1)[-1]: j for (m, u, j) in calls if m == "PATCH"}
    assert patches["1"] == {"extra": {"filament_attributes": "[]",
                                      "product_url": '"http://x"'}}
    assert patches["2"] == {"extra": {"product_url": '"y"'}}
    assert "3" not in patches  # no extras -> never snapshotted
    assert len(logs) == 1
    msg, a, _k = logs[0]
    assert "removed choice 'A'" in msg
    assert a == ("INFO", "00ccff")


# ---------------------------------------------------------------------------
# POST /api/filament_attributes/sweep_unused
# ---------------------------------------------------------------------------

def _sweep_fixture():
    fields = [_attr_field(["A", "B", "C"])]
    filaments = [
        {"id": 1, "extra": {"filament_attributes": '["A"]',
                            "product_url": '"px"'}},
        {"id": 2, "extra": {"nozzle_temp_max": '"240"'}},
        {"id": 3},
    ]
    return fields, filaments


def test_sweep_choices_must_be_list(client):
    """`choices` present but not a list -> 400 before any wire call."""
    r = client.post("/api/filament_attributes/sweep_unused",
                    json={"choices": "notalist"})
    assert r.status_code == 400
    assert r.get_json() == {"success": False,
                            "msg": "`choices` must be a list when provided"}


def test_sweep_zero_filaments_transient_guard(client, monkeypatch):
    """Spoolman returning 0 filaments while the field exists must REFUSE to
    compute usage (a transient empty read would otherwise classify every
    choice as unused and nuke them all). Nothing destructive fires."""
    calls = _install_wire(monkeypatch, fields=[_attr_field(["A", "B"])],
                          filaments=[])
    body = client.post("/api/filament_attributes/sweep_unused",
                       json={"force": True}).get_json()
    assert body["success"] is False
    assert "refusing to compute usage" in body["msg"]
    assert "DELETE" not in _methods(calls)


def test_sweep_missing_field(client, monkeypatch):
    _install_wire(monkeypatch, fields=[{"key": "other"}])
    body = client.post("/api/filament_attributes/sweep_unused",
                       json={}).get_json()
    assert body == {"success": False,
                    "msg": "filament_attributes field not found"}


def test_sweep_preview_lists_unused(client, monkeypatch):
    """No force -> preview shape {success, unused (sorted), total_choices}
    and NOTHING destructive fires."""
    fields, filaments = _sweep_fixture()
    calls = _install_wire(monkeypatch, fields=fields, filaments=filaments)
    body = client.post("/api/filament_attributes/sweep_unused",
                       json={}).get_json()
    assert body == {"success": True, "unused": ["B", "C"],
                    "total_choices": 3}
    assert "DELETE" not in _methods(calls)


def test_sweep_commit_intersects_away_in_use_choice(client, monkeypatch):
    """A stale client asking to sweep a NOW-TAGGED choice gets it silently
    intersected away server-side; with nothing left the commit no-ops with
    the empty commit shape and no schema DELETE."""
    fields, filaments = _sweep_fixture()
    calls = _install_wire(monkeypatch, fields=fields, filaments=filaments)
    body = client.post("/api/filament_attributes/sweep_unused",
                       json={"force": True, "choices": ["A"]}).get_json()
    assert body == {"success": True, "removed": [], "restored": 0,
                    "restore_failures": []}
    assert "DELETE" not in _methods(calls)


def test_sweep_schema_delete_failure(client, monkeypatch):
    """Non-404 DELETE failure aborts the sweep before the recreate POST."""
    fields, filaments = _sweep_fixture()
    calls = _install_wire(monkeypatch, fields=fields, filaments=filaments,
                          delete_resp=_Resp(ok=False, status_code=500,
                                            text="boom"))
    body = client.post("/api/filament_attributes/sweep_unused",
                       json={"force": True}).get_json()
    assert body == {"success": False,
                    "msg": "Schema DELETE failed (500): boom"}
    assert "POST" not in _methods(calls)


def test_sweep_recreate_failure_reports_missing_schema(client, monkeypatch):
    """DELETE ok + POST recreate failing -> success:false naming the
    now-MISSING schema + setup_fields.py remediation, an ERROR/ff4444
    activity-log entry, and no restore PATCH afterward."""
    fields, filaments = _sweep_fixture()
    calls = _install_wire(monkeypatch, fields=fields, filaments=filaments,
                          post_resp=_Resp(ok=False, status_code=500,
                                          text="kaput"))
    logs = _capture_logs(monkeypatch)

    body = client.post("/api/filament_attributes/sweep_unused",
                       json={"force": True}).get_json()
    assert body == {
        "success": False,
        "msg": ("Schema POST failed: kaput. Schema is now MISSING — "
                "re-run setup_fields.py."),
    }
    assert "PATCH" not in _methods(calls)
    assert len(logs) == 1
    msg, a, _k = logs[0]
    assert "sweep deleted field but POST recreate failed" in msg
    assert a == ("ERROR", "ff4444")


def test_sweep_commit_happy_path_selected_subset(client, monkeypatch):
    """Commit with a `choices` subset: only the intersection with the
    freshly-computed unused list is swept. Pins operation order
    (GETs -> DELETE -> POST -> PATCH restores), the recreate payload
    (survivors sorted), and full-extras restore bodies with in-use
    attributes left intact."""
    fields, filaments = _sweep_fixture()
    calls = _install_wire(monkeypatch, fields=fields, filaments=filaments)
    logs = _capture_logs(monkeypatch)

    body = client.post("/api/filament_attributes/sweep_unused",
                       json={"force": True, "choices": ["B"]}).get_json()
    assert body == {"success": True, "removed": ["B"], "restored": 2,
                    "restore_failures": []}
    assert _methods(calls) == ["GET", "GET", "DELETE", "POST", "PATCH", "PATCH"]
    # Recreate keeps A (in use) and C (unused but not selected).
    assert calls[3][2] == {"name": "Filament Attributes",
                           "field_type": "choice",
                           "multi_choice": True,
                           "choices": ["A", "C"]}
    patches = {u.rsplit("/", 1)[-1]: j for (m, u, j) in calls if m == "PATCH"}
    # In-use attribute 'A' survives the wire round-trip; sibling preserved.
    assert patches["1"] == {"extra": {"filament_attributes": '["A"]',
                                      "product_url": '"px"'}}
    assert patches["2"] == {"extra": {"nozzle_temp_max": '"240"'}}
    assert len(logs) == 1
    assert logs[0][1] == ("INFO", "00ccff")
