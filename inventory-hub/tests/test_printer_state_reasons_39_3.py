"""Group 39.3 (backend part): /api/printer_state tells "no credentials" apart
from "unreachable".

`_probe_printer_state` returns None both when the Printer row has no login and
when PrusaLink doesn't answer, and the route answered `prusalink_unreachable`
for both. The overlay would then say "couldn't reach XL" when the fix is
entering XL's login. The route now checks the credentials first (a
locations.json read, no network) and answers `no_credentials` without probing.

HEAD proof: on the pre-39.3 route the first test reads prusalink_unreachable.
"""
from __future__ import annotations

import os
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import app as app_module  # noqa: E402
import prusalink_api  # noqa: E402
import routes_bindings  # noqa: E402

PRINTER_MAP = {"XL-3": {"printer_name": "XL", "position": 2}}


@pytest.fixture
def client():
    app_module.app.config["TESTING"] = True
    return app_module.app.test_client()


def _get(client, creds, probe_result=None):
    with patch.object(routes_bindings.locations_db, "get_active_printer_map", return_value=PRINTER_MAP), \
         patch.object(routes_bindings.config_loader, "get_api_urls", return_value=("http://sm", "http://fb")), \
         patch.object(prusalink_api, "fetch_printer_credentials", return_value=creds), \
         patch.object(prusalink_api, "_probe_printer_state", return_value=probe_result) as probe:
        r = client.get("/api/printer_state/XL-3")
    return r.get_json(), probe


def test_a_printer_with_no_login_says_so_and_is_not_probed(client):
    body, probe = _get(client, creds=None)
    assert body == {"known": False, "reason": "no_credentials", "printer_name": "XL"}, body
    probe.assert_not_called()


def test_a_login_with_no_address_is_no_credentials_too(client):
    body, probe = _get(client, creds={"ip_address": "", "api_key": "k"})
    assert body["reason"] == "no_credentials", body
    probe.assert_not_called()


def test_a_printer_that_does_not_answer_is_unreachable(client):
    body, probe = _get(client, creds={"ip_address": "10.0.0.5", "api_key": "k"}, probe_result=None)
    assert body["reason"] == "prusalink_unreachable" and body["known"] is False, body
    probe.assert_called_once()


def test_an_answering_printer_reports_its_state(client):
    body, _ = _get(client, creds={"ip_address": "10.0.0.5", "api_key": "k"},
                   probe_result={"state": "PRINTING", "is_active": True})
    assert body == {"known": True, "state": "PRINTING", "is_active": True, "printer_name": "XL"}, body
