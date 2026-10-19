"""Bulk Moves feature gate (2026-10-08).

Bulk Moves (L298) is built and covered by the automated suite but has not had a
hands-on pass, and it is destructive and multi-spool. It therefore ships OFF:
prod inherits the schema default and stays dark, while dev turns it on in its
own git-ignored config.json. That let ~100 commits of fixes — several of them
data-loss fixes — reach prod without waiting on the one feature Derek was
blocked on testing.

What these pin:
  * the DEFAULT is False (the whole point — a prod install with no key is dark),
  * the gate FAILS CLOSED when config can't be read,
  * the backend refuses independently of the UI, so a stale tab / queued scan /
    direct POST can't drive a bulk move on an install where it's off,
  * 'cancel' is ALWAYS allowed, so turning the flag off mid-session can't strand
    an armed session with no way to clear it,
  * EVERY backend door is gated, not only /api/bulk_move_session (2026-10-13):
    Group 47's skeptic found that `POST /api/bulk_move`, the server-side
    CMD:BULKMOVE interceptor and an already-armed session (a location scan, or
    a scanned CMD:DONE that commits it) all ignored the flag.
"""
from __future__ import annotations

import os
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import config_loader  # noqa: E402
import config_schema  # noqa: E402
import logic  # noqa: E402
import routes_scan  # noqa: E402
import state  # noqa: E402

KEY = "fcc.bulkMove.enabled"


def test_flag_exists_and_defaults_to_off():
    field = next((f for f in config_schema.CONFIG_SCHEMA if f.key == KEY), None)
    assert field is not None, f"{KEY} is not declared in CONFIG_SCHEMA"
    assert field.type == "bool"
    assert field.default is False, (
        "the default MUST be False — a prod install has no key, and inherits this")


def test_flag_is_server_scope_not_a_browser_preference():
    """Server scope puts it in each install's config.json, so dev can be ON while
    prod is dark. A 'client' scope would live in browser localStorage, which is
    per-browser and can be cleared — the wrong semantics for a safety gate."""
    field = next(f for f in config_schema.CONFIG_SCHEMA if f.key == KEY)
    assert field.scope == "server"
    assert KEY in config_schema.SERVER_KEYS


@pytest.mark.parametrize("cfg,expected", [
    ({}, False),                      # prod: key absent
    ({KEY: False}, False),
    ({KEY: True}, True),
    ({KEY: "yes"}, True),             # truthy strings from a hand-edited config
    ({KEY: 0}, False),
])
def test_enabled_helper_reads_the_config(cfg, expected):
    with patch.object(config_loader, "load_config", return_value=cfg):
        assert routes_scan._bulk_moves_enabled() is expected


def test_enabled_helper_fails_closed_when_config_is_unreadable():
    with patch.object(config_loader, "load_config", side_effect=RuntimeError("boom")):
        assert routes_scan._bulk_moves_enabled() is False
    with patch.object(config_loader, "load_config", return_value=None):
        assert routes_scan._bulk_moves_enabled() is False


# --------------------------------------------------------------------------- #
# The route refuses independently of the UI                                    #
# --------------------------------------------------------------------------- #
@pytest.fixture
def client():
    import app as app_module
    app_module.app.config["TESTING"] = True
    with app_module.app.test_client() as c:
        yield c


@pytest.mark.parametrize("action", ["start", "set_dest", "commit"])
def test_route_refuses_mutating_actions_when_off(client, action):
    with patch.object(routes_scan, "_bulk_moves_enabled", return_value=False):
        resp = client.post("/api/bulk_move_session", json={"action": action})
    assert resp.status_code == 403
    body = resp.get_json()
    assert body["success"] is False
    assert "turned off" in body["msg"].lower()


def test_route_still_allows_cancel_when_off(client):
    """Turning the flag off while a session is armed must not strand it."""
    with patch.object(routes_scan, "_bulk_moves_enabled", return_value=False):
        resp = client.post("/api/bulk_move_session", json={"action": "cancel"})
    assert resp.status_code != 403, "cancel must stay reachable so an armed session can be cleared"


def test_route_does_not_refuse_when_on(client):
    """The gate must not be the thing that breaks bulk moves on an install that
    has turned it on — anything but the 403 is fine here."""
    with patch.object(routes_scan, "_bulk_moves_enabled", return_value=True):
        resp = client.post("/api/bulk_move_session", json={"action": "cancel"})
    assert resp.status_code != 403


# --------------------------------------------------------------------------- #
# The other three doors (found 2026-10-12 by Group 47's skeptic)               #
# --------------------------------------------------------------------------- #
@pytest.fixture
def no_session():
    state.reset_bulk_move()
    yield
    state.reset_bulk_move()


@pytest.fixture
def armed_session():
    """A session armed while the flag was ON (the only way one exists once the
    flag is off), then left standing when the flag was turned off."""
    state.reset_bulk_move()
    state.BULK_MOVE_SESSION.update({
        "active": True, "stage": "awaiting_dest",
        "source_id": "FCC-TEST-SRC", "last_activity_ts": 1.0,
    })
    yield state.BULK_MOVE_SESSION
    state.reset_bulk_move()


def _logs(monkeypatch):
    calls = []
    monkeypatch.setattr(state, "add_log_entry", lambda msg, *a, **k: calls.append((msg, a)))
    return calls


def _must_not_run(name):
    def _f(*a, **k):
        raise AssertionError(f"{name} ran although Bulk Moves is turned off")
    return _f


def test_direct_bulk_move_post_is_refused_when_off(client, monkeypatch):
    """Door 1: POST /api/bulk_move moved every spool regardless of the flag."""
    monkeypatch.setattr(logic, "plan_bulk_move", _must_not_run("plan_bulk_move"))
    monkeypatch.setattr(logic, "execute_bulk_move", _must_not_run("execute_bulk_move"))
    with patch.object(routes_scan, "_bulk_moves_enabled", return_value=False):
        resp = client.post("/api/bulk_move", json={"source": "CR-CT-1", "dest": "CR-CT-2"})
    assert resp.status_code == 403
    body = resp.get_json()
    assert body["success"] is False and "turned off" in body["msg"].lower()


def test_direct_bulk_move_post_still_works_when_on(client, monkeypatch):
    seen = []
    monkeypatch.setattr(logic, "plan_bulk_move",
                        lambda s, d, confirm_active_print=False: seen.append((s, d)) or
                        {"ok": True, "movable_ids": [], "skipped": [], "msg": "Nothing to move"})
    with patch.object(routes_scan, "_bulk_moves_enabled", return_value=True):
        resp = client.post("/api/bulk_move", json={"source": "CR-CT-1", "dest": "CR-CT-2"})
    assert resp.status_code == 200 and seen == [("CR-CT-1", "CR-CT-2")]


def test_cmd_bulkmove_scan_does_not_arm_when_off(client, monkeypatch, no_session):
    """Door 2: the server-side CMD:BULKMOVE interceptor armed a session."""
    monkeypatch.setattr(logic, "start_bulk_move_session", _must_not_run("start_bulk_move_session"))
    logs = _logs(monkeypatch)
    with patch.object(routes_scan, "_bulk_moves_enabled", return_value=False):
        resp = client.post("/api/identify_scan", json={"text": "CMD:BULKMOVE"})
    body = resp.get_json()
    assert body["type"] == "error" and "turned off" in body["msg"].lower(), body
    assert not state.BULK_MOVE_SESSION.get("active")
    assert any("turned off" in m.lower() for m, _ in logs), "no Activity Log line for the refusal"


def test_cmd_bulkmove_rescan_on_a_stale_session_is_refused_when_off(client, monkeypatch, armed_session):
    """Re-scanning CMD:BULKMOVE over a stale session must not refresh its idle
    watchdog (that would keep a session the user can't drive alive)."""
    _logs(monkeypatch)
    with patch.object(routes_scan, "_bulk_moves_enabled", return_value=False):
        resp = client.post("/api/identify_scan", json={"text": "CMD:BULKMOVE"})
    body = resp.get_json()
    assert body["type"] == "error" and "CMD:CANCEL" in body["msg"], body
    assert armed_session["last_activity_ts"] == 1.0


@pytest.mark.parametrize("text", ["LOC:CR-CT-2", "CMD:DONE", "ID:999101"])
def test_an_armed_session_cannot_be_driven_when_off(client, monkeypatch, armed_session, text):
    """Door 3: a location scan set the destination, and a scanned CMD:DONE (the
    deck's COMMIT QR) committed the move, with the flag off."""
    monkeypatch.setattr(logic, "process_bulk_move_scan", _must_not_run("process_bulk_move_scan"))
    monkeypatch.setattr(logic, "commit_bulk_move_session", _must_not_run("commit_bulk_move_session"))
    logs = _logs(monkeypatch)
    with patch.object(routes_scan, "_bulk_moves_enabled", return_value=False):
        resp = client.post("/api/identify_scan", json={"text": text})
    body = resp.get_json()
    assert body["type"] == "error", body
    assert "turned off" in body["msg"].lower() and "CMD:CANCEL" in body["msg"], body
    assert armed_session["active"] is True, "only a cancel may clear the session"
    assert armed_session["last_activity_ts"] == 1.0, "a refused scan refreshed the idle watchdog"
    assert any("turned off" in m.lower() for m, _ in logs), "no Activity Log line for the refusal"


def test_cmd_cancel_still_clears_an_armed_session_when_off(client, monkeypatch, armed_session):
    _logs(monkeypatch)
    with patch.object(routes_scan, "_bulk_moves_enabled", return_value=False):
        resp = client.post("/api/identify_scan", json={"text": "CMD:CANCEL"})
    assert resp.get_json().get("type") != "error", resp.get_json()
    assert not state.BULK_MOVE_SESSION.get("active"), "CMD:CANCEL must clear a stale session"


def test_an_armed_session_is_still_driven_when_on(client, monkeypatch, armed_session):
    seen = []
    monkeypatch.setattr(logic, "process_bulk_move_scan",
                        lambda res: seen.append(res) or {"status": "success"})
    with patch.object(routes_scan, "_bulk_moves_enabled", return_value=True):
        resp = client.post("/api/identify_scan", json={"text": "LOC:CR-CT-2"})
    assert resp.get_json() == {"type": "command", "cmd": "clear"}
    assert seen and seen[0].get("type") == "location"
