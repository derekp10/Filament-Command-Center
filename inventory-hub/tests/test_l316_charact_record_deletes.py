"""L316 characterization tests — pins pre-carve behavior of the three destructive
record-delete routes (app.py 1943-2295: api_delete_spool, api_delete_filament,
api_delete_location). Generated from the 2026-07-01 coverage audit. Do not weaken
these to make a refactor pass.

What is pinned and why:
  - DELETE /api/spool/<sid>      — label snapshot taken BEFORE the delete (once the
    spool is gone the name is unrecoverable), the 502 + LAST_SPOOLMAN_ERROR contract
    on rejection, and the WARNING/ERROR activity-log entries. The route has never
    been executed by any test (test_delete_ui_e2e.py deliberately stops short).
  - DELETE /api/filament/<fid>   — the cascade's ABORT SEMANTICS: any child-spool
    failure returns 502 with a spool_errors list and the filament delete is NEVER
    attempted; the sweep order is spools-first-then-filament. Compare the sibling
    api_merge_filament, whose equivalent branches are all pinned.
  - DELETE /api/locations        — the ROUTE-level contract only (status codes,
    response keys, save-once ordering, best-effort Spoolman unassign, activity-log
    detail assembly). The toolhead-cascade INTERNALS are unit-tested in
    test_l271_toolhead_delete_cascade.py and are stubbed here, not re-tested.

Pure host-runnable unit tests: Flask test_client + monkeypatched
spoolman_api / locations_db / logic / state. No live server, no live Spoolman.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import app as app_module  # noqa: E402


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _capture_logs(monkeypatch):
    """Capture every state.add_log_entry call as (msg, args, kwargs)."""
    calls = []
    monkeypatch.setattr(
        app_module.state, "add_log_entry",
        lambda msg, *a, **k: calls.append((msg, a, k)),
    )
    return calls


def _capture_logger_warnings(monkeypatch):
    """Capture state.logger.warning(...) messages (the best-effort-cascade sink)."""
    warnings = []
    monkeypatch.setattr(
        app_module.state.logger, "warning",
        lambda msg, *a, **k: warnings.append(str(msg)),
    )
    return warnings


def _patch_locations(monkeypatch, rows):
    """Stub the locations store; returns the list of save_locations_list payloads."""
    saves = []
    monkeypatch.setattr(app_module.locations_db, "load_locations_list", lambda: rows)
    monkeypatch.setattr(
        app_module.locations_db, "save_locations_list",
        lambda lst: saves.append(lst) or True,
    )
    return saves


def _cascade_result(**over):
    """A perform_toolhead_delete_cascade 'ok' result with every key the route reads."""
    res = {
        "status": "ok",
        "unassigned": [],
        "undeployed": [],
        "slot_bindings_cleared": [],
        "toolhead_pruned_from": [],
        "errors": [],
    }
    res.update(over)
    return res


# ---------------------------------------------------------------------------
# DELETE /api/spool/<sid>  (api_delete_spool)
# ---------------------------------------------------------------------------

def test_delete_spool_success_snapshots_label_before_delete(monkeypatch):
    """Happy path: the filament-name label is snapshotted via get_spool BEFORE
    delete_spool runs (after the delete the name is gone from Spoolman), the
    response carries deleted_spool_id, and a WARNING/ff8800 activity-log entry
    names the spool as '#<id> (<filament name>)'."""
    client = app_module.app.test_client()
    order = []
    monkeypatch.setattr(
        app_module.spoolman_api, "get_spool",
        lambda sid: order.append(("get_spool", sid)) or {"id": sid, "filament": {"name": "PLA X"}},
    )
    monkeypatch.setattr(
        app_module.spoolman_api, "delete_spool",
        lambda sid: order.append(("delete_spool", sid)) or True,
    )
    calls = _capture_logs(monkeypatch)

    r = client.delete("/api/spool/42")

    assert r.status_code == 200
    assert r.get_json() == {"success": True, "deleted_spool_id": 42}
    # Snapshot ordering is the safety property: label read BEFORE the delete.
    assert order == [("get_spool", 42), ("delete_spool", 42)]
    assert len(calls) == 1
    msg, args, _ = calls[0]
    assert "Deleted Spool #42 (PLA X)" in msg
    assert args == ("WARNING", "ff8800")


def test_delete_spool_rejection_surfaces_spoolman_error_as_502(monkeypatch):
    """Rejection path: delete_spool -> False surfaces LAST_SPOOLMAN_ERROR verbatim
    in the response 'error' field with HTTP 502, plus an ERROR/ff4444 log entry
    containing the Spoolman body (the 2026-04-27 error-surfacing convention)."""
    client = app_module.app.test_client()
    monkeypatch.setattr(
        app_module.spoolman_api, "get_spool",
        lambda sid: {"id": sid, "filament": {"name": "PLA X"}},
    )
    monkeypatch.setattr(app_module.spoolman_api, "delete_spool", lambda sid: False)
    monkeypatch.setattr(
        app_module.spoolman_api, "LAST_SPOOLMAN_ERROR",
        "HTTP 409: has dependencies", raising=False,
    )
    calls = _capture_logs(monkeypatch)

    r = client.delete("/api/spool/42")

    assert r.status_code == 502
    assert r.get_json() == {"success": False, "error": "HTTP 409: has dependencies"}
    assert len(calls) == 1
    msg, args, _ = calls[0]
    assert "Failed to delete Spool #42 (PLA X): HTTP 409: has dependencies" in msg
    assert args == ("ERROR", "ff4444")


def test_delete_spool_rejection_fallback_error_when_no_spoolman_body(monkeypatch):
    """When LAST_SPOOLMAN_ERROR is unset (None) the route substitutes the literal
    fallback string 'Spoolman rejected the delete'."""
    client = app_module.app.test_client()
    monkeypatch.setattr(app_module.spoolman_api, "get_spool", lambda sid: None)
    monkeypatch.setattr(app_module.spoolman_api, "delete_spool", lambda sid: False)
    monkeypatch.setattr(app_module.spoolman_api, "LAST_SPOOLMAN_ERROR", None, raising=False)
    _capture_logs(monkeypatch)

    r = client.delete("/api/spool/42")

    assert r.status_code == 502
    assert r.get_json()["error"] == "Spoolman rejected the delete"


def test_delete_spool_missing_snapshot_falls_back_to_bare_id_label(monkeypatch):
    """get_spool -> None (already gone / Spoolman blip): the label falls back to
    '#<id>' with no parenthesized name, no exception, and the delete proceeds."""
    client = app_module.app.test_client()
    monkeypatch.setattr(app_module.spoolman_api, "get_spool", lambda sid: None)
    monkeypatch.setattr(app_module.spoolman_api, "delete_spool", lambda sid: True)
    calls = _capture_logs(monkeypatch)

    r = client.delete("/api/spool/42")

    assert r.status_code == 200
    assert r.get_json() == {"success": True, "deleted_spool_id": 42}
    msg, args, _ = calls[0]
    assert "Deleted Spool #42" in msg
    assert "(" not in msg  # no filament-name suffix
    assert args == ("WARNING", "ff8800")


def test_delete_routes_require_integer_ids(monkeypatch):
    """Both delete routes use Flask's <int:> converter: a non-integer id never
    reaches the handler and 404s at routing time (no Spoolman call fires)."""
    client = app_module.app.test_client()
    called = []
    monkeypatch.setattr(
        app_module.spoolman_api, "delete_spool",
        lambda sid: called.append(sid) or True,
    )
    monkeypatch.setattr(
        app_module.spoolman_api, "delete_filament",
        lambda fid: called.append(fid) or True,
    )

    assert client.delete("/api/spool/notanint").status_code == 404
    assert client.delete("/api/filament/notanint").status_code == 404
    assert called == []


# ---------------------------------------------------------------------------
# DELETE /api/filament/<fid>  (api_delete_filament)
# ---------------------------------------------------------------------------

def _patch_filament_cascade(monkeypatch, *, children, spool_ok, filament_ok=True,
                            name="Galaxy PLA"):
    """Wire the filament-cascade mocks; returns the shared call-order list.

    spool_ok: callable sid -> bool controlling per-child delete_spool success.
    """
    order = []
    monkeypatch.setattr(
        app_module.spoolman_api, "get_filament",
        lambda fid: {"id": fid, "name": name} if name else {"id": fid},
    )
    monkeypatch.setattr(
        app_module.spoolman_api, "get_spools_for_filament",
        lambda fid: list(children),
    )
    monkeypatch.setattr(
        app_module.spoolman_api, "delete_spool",
        lambda sid: order.append(("delete_spool", sid)) or spool_ok(sid),
    )
    monkeypatch.setattr(
        app_module.spoolman_api, "delete_filament",
        lambda fid: order.append(("delete_filament", fid)) or filament_ok,
    )
    return order


def test_delete_filament_cascade_deletes_spools_first_then_filament(monkeypatch):
    """Success cascade: every child spool is deleted BEFORE the filament (Spoolman
    rejects a filament delete while children exist), the response lists the ids,
    and the WARNING/ff8800 log names the cascade count."""
    client = app_module.app.test_client()
    order = _patch_filament_cascade(
        monkeypatch,
        children=[{"id": 1}, {"id": 2}, {"id": 3}],
        spool_ok=lambda sid: True,
    )
    calls = _capture_logs(monkeypatch)

    r = client.delete("/api/filament/7")

    assert r.status_code == 200
    assert r.get_json() == {
        "success": True,
        "deleted_filament_id": 7,
        "deleted_spool_ids": [1, 2, 3],
    }
    assert order == [
        ("delete_spool", 1),
        ("delete_spool", 2),
        ("delete_spool", 3),
        ("delete_filament", 7),
    ]
    assert len(calls) == 1
    msg, args, _ = calls[0]
    assert "Deleted Filament #7 (Galaxy PLA)" in msg
    assert "cascade: 3 child spool(s)" in msg
    assert args == ("WARNING", "ff8800")


def test_delete_filament_child_failure_aborts_filament_delete(monkeypatch):
    """ABORT SEMANTICS: any child-spool failure -> 502 with a spool_errors list and
    the filament delete is NEVER attempted. The child sweep itself CONTINUES past
    the failure (spool 3 is still deleted after spool 2 fails), so
    deleted_spool_ids reports every success — pin both halves.
    # NOTE: pins current behavior; see suspected_bugs — the sweep is best-effort
    # (keeps deleting remaining children after a failure), only the filament
    # delete is aborted."""
    client = app_module.app.test_client()
    order = _patch_filament_cascade(
        monkeypatch,
        children=[{"id": 1}, {"id": 2}, {"id": 3}],
        spool_ok=lambda sid: sid != 2,
    )
    monkeypatch.setattr(
        app_module.spoolman_api, "LAST_SPOOLMAN_ERROR", "HTTP 409: in use", raising=False,
    )
    calls = _capture_logs(monkeypatch)

    r = client.delete("/api/filament/7")

    assert r.status_code == 502
    body = r.get_json()
    assert body == {
        "success": False,
        "error": "Some child spools could not be deleted; filament left in place.",
        "deleted_spool_ids": [1, 3],
        "spool_errors": [{"spool_id": 2, "error": "HTTP 409: in use"}],
    }
    # The filament delete must never have been attempted.
    assert ("delete_filament", 7) not in order
    assert order == [("delete_spool", 1), ("delete_spool", 2), ("delete_spool", 3)]
    # Per-failed-spool ERROR log naming the parent filament.
    assert len(calls) == 1
    msg, args, _ = calls[0]
    assert "Cascade delete: failed to delete Spool #2" in msg
    assert "parent Filament #7 (Galaxy PLA)" in msg
    assert "HTTP 409: in use" in msg
    assert args == ("ERROR", "ff4444")


def test_delete_filament_filament_rejection_still_reports_deleted_children(monkeypatch):
    """All children deleted OK but the filament delete itself fails: 502 with the
    LAST_SPOOLMAN_ERROR body AND deleted_spool_ids still reported — the partial-
    state recoverability contract (the user must know the children are gone)."""
    client = app_module.app.test_client()
    _patch_filament_cascade(
        monkeypatch,
        children=[{"id": 1}, {"id": 2}],
        spool_ok=lambda sid: True,
        filament_ok=False,
    )
    monkeypatch.setattr(
        app_module.spoolman_api, "LAST_SPOOLMAN_ERROR", "HTTP 500: db locked", raising=False,
    )
    calls = _capture_logs(monkeypatch)

    r = client.delete("/api/filament/7")

    assert r.status_code == 502
    assert r.get_json() == {
        "success": False,
        "error": "HTTP 500: db locked",
        "deleted_spool_ids": [1, 2],
    }
    assert len(calls) == 1
    msg, args, _ = calls[0]
    assert "Failed to delete Filament #7 (Galaxy PLA): HTTP 500: db locked" in msg
    assert args == ("ERROR", "ff4444")


def test_delete_filament_child_without_id_is_skipped(monkeypatch):
    """A child entry with id None (or missing) is silently skipped — no delete
    attempt, no error entry — and the cascade proceeds with the rest."""
    client = app_module.app.test_client()
    order = _patch_filament_cascade(
        monkeypatch,
        children=[{"id": None}, {}, {"id": 4}],
        spool_ok=lambda sid: True,
    )
    _capture_logs(monkeypatch)

    r = client.delete("/api/filament/7")

    assert r.status_code == 200
    assert r.get_json()["deleted_spool_ids"] == [4]
    assert order == [("delete_spool", 4), ("delete_filament", 7)]


def test_delete_filament_zero_children_plain_delete_no_cascade_wording(monkeypatch):
    """No children: plain delete, deleted_spool_ids is [], and the log line has
    NO 'cascade' wording (the two-branch log message split)."""
    client = app_module.app.test_client()
    order = _patch_filament_cascade(monkeypatch, children=[], spool_ok=lambda sid: True)
    calls = _capture_logs(monkeypatch)

    r = client.delete("/api/filament/7")

    assert r.status_code == 200
    assert r.get_json() == {
        "success": True,
        "deleted_filament_id": 7,
        "deleted_spool_ids": [],
    }
    assert order == [("delete_filament", 7)]
    assert len(calls) == 1
    msg, args, _ = calls[0]
    assert "Deleted Filament #7 (Galaxy PLA)" in msg
    assert "cascade" not in msg
    assert args == ("WARNING", "ff8800")


# ---------------------------------------------------------------------------
# DELETE /api/locations  (api_delete_location — route layer only)
# ---------------------------------------------------------------------------

def test_delete_location_blank_id_returns_200_success_false_no_save(monkeypatch):
    """Missing/blank ?id short-circuits to a bare {'success': False} — with HTTP
    200, no error/msg key, and no load or save of the locations store.
    # NOTE: pins current behavior; see suspected_bugs — a validation failure
    # answering 200 (not 400) with no message is the shipped contract."""
    client = app_module.app.test_client()
    saves = _patch_locations(monkeypatch, [])
    _capture_logs(monkeypatch)

    r = client.delete("/api/locations")

    assert r.status_code == 200
    assert r.get_json() == {"success": False}
    assert saves == []


def test_delete_location_toolhead_requires_confirm_maps_to_409(monkeypatch):
    """A toolhead row whose cascade answers status=requires_confirm maps to HTTP
    409 with the cascade's payload spread into the body alongside success:False,
    and locations.json is NOT saved (nothing was mutated)."""
    client = app_module.app.test_client()
    rows = [{"LocationID": "XL-1", "Type": "Tool Head", "Name": "XL Tool 1"}]
    saves = _patch_locations(monkeypatch, rows)
    monkeypatch.setattr(
        app_module.logic, "perform_toolhead_delete_cascade",
        lambda target, current, confirm_active_print=False: {
            "status": "requires_confirm",
            "confirm_type": "active_print",
            "printer_name": "XL",
        },
    )
    _capture_logs(monkeypatch)

    r = client.delete("/api/locations?id=XL-1")

    assert r.status_code == 409
    assert r.get_json() == {
        "success": False,
        "status": "requires_confirm",
        "confirm_type": "active_print",
        "printer_name": "XL",
    }
    assert saves == []


def test_delete_location_toolhead_happy_path_saves_mutated_list_once(monkeypatch):
    """Toolhead happy path pins the save-once ordering contract: the cascade
    mutates `current` IN PLACE (locations.json-side cleanup), THEN the route
    filters out the deleted row and saves EXACTLY once — so the saved list
    carries both the cascade's mutations and the row removal. The WARNING log
    joins the detail bits in cascade-result order."""
    client = app_module.app.test_client()
    toolhead_row = {"LocationID": "XL-1", "Type": "Tool Head"}
    dryer_row = {"LocationID": "PM-DB-1", "Type": "Dryer Box",
                 "extra": {"slot_targets": {"1": "XL-1", "2": "XL-2"}}}
    rows = [toolhead_row, dryer_row]
    saves = _patch_locations(monkeypatch, rows)
    order = []

    def _cascade(target, current, confirm_active_print=False):
        order.append("cascade")
        # Mutate `current` in place exactly like the real cascade does — the
        # route must save THIS mutation (it relies on shared list identity).
        del current[1]["extra"]["slot_targets"]["1"]
        return _cascade_result(
            unassigned=[5],
            undeployed=[9],
            slot_bindings_cleared=["PM-DB-1:1"],
            toolhead_pruned_from=["XL"],
        )

    monkeypatch.setattr(app_module.logic, "perform_toolhead_delete_cascade", _cascade)
    monkeypatch.setattr(
        app_module.locations_db, "save_locations_list",
        lambda lst: (order.append("save"), saves.append(lst)) and True,
    )
    calls = _capture_logs(monkeypatch)

    r = client.delete("/api/locations?id=XL-1")

    assert r.status_code == 200
    body = r.get_json()
    assert body["success"] is True
    assert body["cascade"]["unassigned"] == [5]
    assert body["cascade"]["status"] == "ok"
    # Ordering: cascade mutates first, save happens after — exactly once.
    assert order == ["cascade", "save"]
    assert len(saves) == 1
    saved = saves[0]
    assert saved == [dryer_row]                      # toolhead row filtered out
    assert saved[0]["extra"]["slot_targets"] == {"2": "XL-2"}  # cascade mutation kept
    # Detail assembly: bits joined with '; ' in fixed order.
    assert len(calls) == 1
    msg, args, _ = calls[0]
    assert "Deleted toolhead XL-1" in msg
    assert msg.endswith(
        "1 spool(s) → UNASSIGNED; 1 un-deployed; "
        "1 slot binding(s) cleared; pruned from XL"
    )
    assert args == ("WARNING",)


def test_delete_location_toolhead_cascade_errors_add_second_error_log(monkeypatch):
    """A cascade with a non-empty errors[] still succeeds (200) but writes a
    SECOND log entry at ERROR/ff4444 joining the errors; the first WARNING entry
    falls back to 'nothing referenced it' when every detail list is empty."""
    client = app_module.app.test_client()
    rows = [{"LocationID": "XL-1", "Type": "Tool Head"}]
    saves = _patch_locations(monkeypatch, rows)
    monkeypatch.setattr(
        app_module.logic, "perform_toolhead_delete_cascade",
        lambda target, current, confirm_active_print=False: _cascade_result(
            errors=["boom", "bang"]),
    )
    calls = _capture_logs(monkeypatch)

    r = client.delete("/api/locations?id=XL-1")

    assert r.status_code == 200
    assert r.get_json()["success"] is True
    assert len(saves) == 1
    assert len(calls) == 2
    warn_msg, warn_args, _ = calls[0]
    assert "Deleted toolhead XL-1" in warn_msg
    assert "nothing referenced it" in warn_msg
    assert warn_args == ("WARNING",)
    err_msg, err_args, _ = calls[1]
    assert "Toolhead-delete cascade for XL-1 had errors: boom; bang" in err_msg
    assert err_args == ("ERROR", "ff4444")


def test_delete_location_confirm_active_print_query_param_forwarding(monkeypatch):
    """?confirm_active_print=1 forwards confirm_active_print=True into the
    cascade; an absent param forwards False."""
    client = app_module.app.test_client()
    rows = [{"LocationID": "XL-1", "Type": "Tool Head"}]
    _patch_locations(monkeypatch, rows)
    seen = []

    def _cascade(target, current, confirm_active_print=False):
        seen.append(confirm_active_print)
        return _cascade_result()

    monkeypatch.setattr(app_module.logic, "perform_toolhead_delete_cascade", _cascade)
    _capture_logs(monkeypatch)

    assert client.delete("/api/locations?id=XL-1").status_code == 200
    assert client.delete("/api/locations?id=XL-1&confirm_active_print=1").status_code == 200
    assert seen == [False, True]


def test_delete_location_non_toolhead_best_effort_unassign_continues_on_failure(monkeypatch):
    """Non-toolhead delete: every direct spool gets a best-effort
    update_spool(sid, {'location': ''}); a failing unassign logs a
    state.logger.warning naming LAST_SPOOLMAN_ERROR but does NOT abort — the
    row is still removed, save still fires once, and the response is a plain
    200 {'success': True} with a 'Deleted: <id>' WARNING log entry."""
    client = app_module.app.test_client()
    box_row = {"LocationID": "BOX-1", "Type": "Box"}
    keep_row = {"LocationID": "BOX-2", "Type": "Box"}
    saves = _patch_locations(monkeypatch, [box_row, keep_row])
    monkeypatch.setattr(
        app_module.spoolman_api, "get_spools_at_location", lambda loc: [1, 2],
    )
    updates = []

    def _update(sid, data):
        updates.append((sid, data))
        return {"id": sid} if sid == 1 else None  # spool 2 fails

    monkeypatch.setattr(app_module.spoolman_api, "update_spool", _update)
    monkeypatch.setattr(
        app_module.spoolman_api, "LAST_SPOOLMAN_ERROR", "HTTP 500: nope", raising=False,
    )
    warnings = _capture_logger_warnings(monkeypatch)
    calls = _capture_logs(monkeypatch)

    r = client.delete("/api/locations?id=BOX-1")

    assert r.status_code == 200
    assert r.get_json() == {"success": True}
    assert updates == [(1, {"location": ""}), (2, {"location": ""})]
    assert len(warnings) == 1
    assert "failed to unassign Spool #2 from BOX-1: HTTP 500: nope" in warnings[0]
    assert saves == [[keep_row]]  # row removed, save exactly once
    assert len(calls) == 1
    msg, args, _ = calls[0]
    assert "Deleted: BOX-1" in msg
    assert args == ("WARNING",)


def test_delete_location_non_toolhead_cascade_exception_still_deletes(monkeypatch):
    """get_spools_at_location raising is swallowed into a logger.warning and the
    delete still completes: row removed, saved once, 200 success."""
    client = app_module.app.test_client()
    box_row = {"LocationID": "BOX-1", "Type": "Box"}
    saves = _patch_locations(monkeypatch, [box_row])

    def _boom(loc):
        raise RuntimeError("spoolman down")

    monkeypatch.setattr(app_module.spoolman_api, "get_spools_at_location", _boom)
    warnings = _capture_logger_warnings(monkeypatch)
    calls = _capture_logs(monkeypatch)

    r = client.delete("/api/locations?id=BOX-1")

    assert r.status_code == 200
    assert r.get_json() == {"success": True}
    assert len(warnings) == 1
    assert "cascade unassign failed" in warnings[0]
    assert "spoolman down" in warnings[0]
    assert saves == [[]]
    msg, args, _ = calls[0]
    assert "Deleted: BOX-1" in msg
    assert args == ("WARNING",)
