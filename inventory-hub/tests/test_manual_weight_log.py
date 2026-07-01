"""Group 24.F — manual weight adjustments leave a before→after breakdown
in the Activity Log.

There are TWO manual weight funnels, both of which must log the breakdown
(they share the _log_manual_weight_change helper):
  - POST /api/spool/update → api_spool_update (the weigh-out modal / quick-weigh)
  - POST /api/edit_spool_wizard → api_edit_spool_wizard (the wizard edit-spool save)
Each already fetches the pre-update snapshot; 24.F adds a `state.add_log_entry`
describing remaining/used (and, when it changed, total) before vs after — but
ONLY when a weight field was actually dirty, so location/extra-only edits don't
spam the log. The L200 Prusament correction has its own dedicated log and does
NOT route through this helper.

These are pure backend unit tests (Flask test_client + monkeypatched
spoolman_api) — no server / Playwright needed.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import app as app_module  # noqa: E402


def _capture_logs(monkeypatch):
    """Capture every state.add_log_entry call as (msg, args, kwargs)."""
    calls = []
    monkeypatch.setattr(
        app_module.state, "add_log_entry",
        lambda msg, *a, **k: calls.append((msg, a, k)),
    )
    return calls


def _weight_logs(calls):
    return [c for c in calls if "Weight updated" in c[0]]


def test_weight_change_logs_before_after(monkeypatch):
    """A used_weight change logs the remaining + used before→after breakdown."""
    client = app_module.app.test_client()
    pre = {"id": 42, "archived": False, "initial_weight": 1000,
           "used_weight": 200, "remaining_weight": 800}
    post = {"id": 42, "archived": False, "initial_weight": 1000,
            "used_weight": 550, "remaining_weight": 450}
    monkeypatch.setattr(app_module.spoolman_api, "get_spool", lambda sid: pre)
    monkeypatch.setattr(app_module.spoolman_api, "update_spool", lambda sid, data: post)
    calls = _capture_logs(monkeypatch)

    r = client.post("/api/spool/update", json={"id": 42, "updates": {"used_weight": 550}})
    assert r.get_json()["status"] == "success"

    logs = _weight_logs(calls)
    assert len(logs) == 1, f"expected exactly one weight log, got {[c[0] for c in calls]}"
    msg = logs[0][0]
    assert "#42" in msg
    assert "800.0g ➔ 450.0g remaining" in msg
    assert "used 200.0g ➔ 550.0g" in msg
    # initial unchanged → no "total" segment.
    assert "total" not in msg


def test_weight_change_includes_total_when_initial_changes(monkeypatch):
    """When initial_weight itself changes, the breakdown surfaces total too."""
    client = app_module.app.test_client()
    pre = {"id": 7, "archived": False, "initial_weight": 1000,
           "used_weight": 100, "remaining_weight": 900}
    post = {"id": 7, "archived": False, "initial_weight": 750,
            "used_weight": 100, "remaining_weight": 650}
    monkeypatch.setattr(app_module.spoolman_api, "get_spool", lambda sid: pre)
    monkeypatch.setattr(app_module.spoolman_api, "update_spool", lambda sid, data: post)
    calls = _capture_logs(monkeypatch)

    client.post("/api/spool/update", json={"id": 7, "updates": {"initial_weight": 750}})
    logs = _weight_logs(calls)
    assert len(logs) == 1
    assert "total 1000.0g ➔ 750.0g" in logs[0][0]


def test_non_weight_edit_does_not_log(monkeypatch):
    """A location/comment-only edit must NOT emit the weight breakdown line."""
    client = app_module.app.test_client()
    pre = {"id": 9, "archived": False, "initial_weight": 1000,
           "used_weight": 300, "remaining_weight": 700}
    post = dict(pre)
    monkeypatch.setattr(app_module.spoolman_api, "get_spool", lambda sid: pre)
    monkeypatch.setattr(app_module.spoolman_api, "update_spool", lambda sid, data: post)
    calls = _capture_logs(monkeypatch)

    client.post("/api/spool/update", json={"id": 9, "updates": {"comment": "moved"}})
    assert _weight_logs(calls) == []


def test_remaining_weight_field_triggers_log(monkeypatch):
    """remaining_weight is also a weight field — editing it logs the breakdown."""
    client = app_module.app.test_client()
    pre = {"id": 11, "archived": False, "initial_weight": 1000,
           "used_weight": 0, "remaining_weight": 1000}
    post = {"id": 11, "archived": False, "initial_weight": 1000,
            "used_weight": 250, "remaining_weight": 750}
    monkeypatch.setattr(app_module.spoolman_api, "get_spool", lambda sid: pre)
    monkeypatch.setattr(app_module.spoolman_api, "update_spool", lambda sid, data: post)
    calls = _capture_logs(monkeypatch)

    client.post("/api/spool/update", json={"id": 11, "updates": {"remaining_weight": 750}})
    assert len(_weight_logs(calls)) == 1


def test_failed_update_does_not_log_weight(monkeypatch):
    """If update_spool fails (returns None), no before→after line is written."""
    client = app_module.app.test_client()
    pre = {"id": 5, "archived": False, "initial_weight": 1000,
           "used_weight": 100, "remaining_weight": 900}
    monkeypatch.setattr(app_module.spoolman_api, "get_spool", lambda sid: pre)
    monkeypatch.setattr(app_module.spoolman_api, "update_spool", lambda sid, data: None)
    monkeypatch.setattr(app_module.spoolman_api, "LAST_SPOOLMAN_ERROR", "boom", raising=False)
    calls = _capture_logs(monkeypatch)

    r = client.post("/api/spool/update", json={"id": 5, "updates": {"used_weight": 200}})
    assert r.get_json()["status"] == "error"
    assert _weight_logs(calls) == []


def test_empty_pre_snapshot_skips_weight_log(monkeypatch):
    """Review finding 1 — if the pre-update snapshot is missing (a transient
    get_spool blip) but the update still succeeds, skip the line rather than
    log fabricated 0.0g 'before' values."""
    client = app_module.app.test_client()
    post = {"id": 3, "archived": False, "initial_weight": 1000,
            "used_weight": 550, "remaining_weight": 450}
    monkeypatch.setattr(app_module.spoolman_api, "get_spool", lambda sid: None)
    monkeypatch.setattr(app_module.spoolman_api, "update_spool", lambda sid, data: post)
    calls = _capture_logs(monkeypatch)

    r = client.post("/api/spool/update", json={"id": 3, "updates": {"used_weight": 550}})
    assert r.get_json()["status"] == "success"
    assert _weight_logs(calls) == []


# --- wizard edit-spool funnel (/api/edit_spool_wizard) ----------------------


def test_wizard_edit_spool_logs_weight_before_after(monkeypatch):
    """24.F — the wizard edit-spool save is ALSO a manual weight surface and
    must emit the same before→after breakdown via the shared helper."""
    client = app_module.app.test_client()
    pre = {"id": 77, "archived": False, "initial_weight": 1000,
           "used_weight": 200, "remaining_weight": 800}
    post = {"id": 77, "archived": False, "initial_weight": 1000,
            "used_weight": 550, "remaining_weight": 450}
    monkeypatch.setattr(app_module.spoolman_api, "get_spool", lambda sid: pre)
    monkeypatch.setattr(app_module.spoolman_api, "update_spool", lambda sid, data: post)
    calls = _capture_logs(monkeypatch)

    r = client.post("/api/edit_spool_wizard", json={
        "spool_id": 77,
        "spool_data": {"used_weight": 550},
    })
    assert r.get_json()["success"] is True
    logs = _weight_logs(calls)
    assert len(logs) == 1, f"wizard edit should log one weight line, got {[c[0] for c in calls]}"
    assert "#77" in logs[0][0]
    assert "800.0g ➔ 450.0g remaining" in logs[0][0]


def test_wizard_edit_spool_non_weight_change_does_not_log(monkeypatch):
    """A wizard edit that changes only a non-weight field (e.g. comment) must
    not emit the weight breakdown line."""
    client = app_module.app.test_client()
    pre = {"id": 78, "archived": False, "initial_weight": 1000,
           "used_weight": 200, "remaining_weight": 800, "comment": "old"}
    post = dict(pre)
    post["comment"] = "new"
    monkeypatch.setattr(app_module.spoolman_api, "get_spool", lambda sid: pre)
    monkeypatch.setattr(app_module.spoolman_api, "update_spool", lambda sid, data: post)
    calls = _capture_logs(monkeypatch)

    client.post("/api/edit_spool_wizard", json={
        "spool_id": 78,
        "spool_data": {"comment": "new"},
    })
    assert _weight_logs(calls) == []
