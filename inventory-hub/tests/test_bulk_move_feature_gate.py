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
    an armed session with no way to clear it.
"""
from __future__ import annotations

import os
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import config_loader  # noqa: E402
import config_schema  # noqa: E402
import routes_scan  # noqa: E402

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
