"""/api/search with `strict=1` (Group 58, the audit's 🔎 Find a spool; Derek's answers of
2026-11-03, A2): a search that couldn't be made answers success: false, so the page says
"Couldn't search", never "No matches" (Group 52's rule: a read that fails says so).
Without it the search panel's answers stand as they were: an empty list on a Spoolman
that didn't answer.

The real route and the real search over tests/spoolman_extra_fake.SpoolmanHTTPFake.
RED on 2fd8a2d: `strict` was ignored there, and every failure answered success: true
with no results (the without-strict pins say they were right already).
"""
from __future__ import annotations

from unittest.mock import patch
from urllib.parse import urlsplit

import pytest
import requests

import app as app_module
import config_loader
import spoolman_api
from spoolman_extra_fake import SpoolmanHTTPFake, _Resp


@pytest.fixture
def fake(monkeypatch):
    sm = SpoolmanHTTPFake(fields={"spool": []})
    monkeypatch.setattr(spoolman_api.requests, "get", sm.get)
    monkeypatch.setattr(config_loader, "load_config", lambda: {"server_ip": "spoolman.test", "spoolman_port": 7000})
    sm.add("spool", 57, {}, location="LR-MDB-1", remaining_weight=500.0, used_weight=100.0,
           initial_weight=1000.0, archived=False,
           filament={"id": 1057, "name": "Glow Red", "material": "PLA", "color_hex": "72071C",
                     "vendor": {"id": 1, "name": "Some Brand"}, "extra": {}})
    app_module.app.config["TESTING"] = True
    return sm


def _search(query, strict=True):
    client = app_module.app.test_client()
    return client.get("/api/search", query_string=dict({"q": query, "type": "spool"}, **({"strict": "1"} if strict else {})))


def test_a_strict_search_finds_as_the_plain_one_does(fake):
    """Pins already-right code: the rows are the search's own."""
    got = _search("glow").get_json()
    assert got["success"] is True and [r["id"] for r in got["results"]] == [57]
    assert _search("glow", strict=False).get_json()["results"] == got["results"]


def test_a_strict_search_spoolman_answered_with_an_error_says_so(fake):
    fake.list_reads_fail = True
    got = _search("glow").get_json()
    assert got == {"success": False, "msg": "Spoolman answered HTTP 503."}


def test_a_strict_search_spoolman_didnt_answer_says_so(fake):
    fake.down = True
    got = _search("glow").get_json()
    assert got["success"] is False and got["msg"].startswith("Spoolman didn't answer (")


class _NotJson(_Resp):
    """A 200 whose body isn't JSON (a proxy's page), as requests reads one."""

    def __init__(self, error):
        super().__init__(200, None)
        self._error = error

    def json(self):
        raise self._error


def _answering(fake, monkeypatch, path, resp):
    """Spoolman answering `resp` on one list path, the fake on every other."""
    def get(url, timeout=None, **kw):
        if urlsplit(str(url)).path.rstrip("/") == path:
            fake.gets.append(path)
            return resp(url, timeout) if callable(resp) else resp
        return fake.get(url, timeout=timeout, **kw)
    monkeypatch.setattr(spoolman_api.requests, "get", get)


def _broken_record(fake):
    """The list Spoolman sends, plus a spool FCC can't read (its filament null)."""
    def answer(url, timeout):
        rows = fake.get(url, timeout=timeout).json()
        rows.append({"id": 58, "location": "", "extra": {}, "filament": None, "remaining_weight": 1.0})
        return _Resp(200, rows)
    return answer


@pytest.mark.parametrize("how", ["requests-json-error", "value-error", "a-dict", "a-broken-record"])
def test_a_strict_search_spoolman_answered_with_what_fcc_cant_read_says_so(fake, monkeypatch, how):
    """Spoolman answered, so the words never say it didn't, and never show a Python
    error. Review of 7e3720f, S-4: RED there, "Spoolman didn't answer ('NoneType'
    object has no attribute 'get')." and the like."""
    resp = {"requests-json-error": _NotJson(requests.exceptions.JSONDecodeError("Expecting value", "<html>", 0)),
            "value-error": _NotJson(ValueError("Expecting value: line 1 column 1 (char 0)")),
            "a-dict": _Resp(200, {"detail": "not a list"}),
            "a-broken-record": _broken_record(fake)}[how]
    _answering(fake, monkeypatch, "/api/v1/spool", resp)
    assert _search("glow").get_json() == {"success": False, "msg": "Spoolman's answer couldn't be read."}


def _filaments(query, strict=True):
    client = app_module.app.test_client()
    return client.get("/api/search", query_string=dict({"q": query, "type": "filament"},
                                                         **({"strict": "1"} if strict else {})))


@pytest.mark.parametrize("how, msg", [("503", "Spoolman answered HTTP 503."), ("down", "Spoolman didn't answer (")])
def test_a_strict_filament_search_whose_spool_count_read_fails_says_it_couldnt_search(fake, monkeypatch, how, msg):
    """The docstring's promise for a filament search: its spool counts aren't read as 0.
    No page sends this today. Review of 7e3720f, S-4: RED there (success, every count 0)."""
    fake.add("filament", 1057, {}, name="Glow Red", material="PLA", color_hex="72071C",
             vendor={"id": 1, "name": "Some Brand"})

    def failing(url, timeout):
        if how == "down":
            raise TimeoutError("Spoolman isn't answering (test)")
        return _Resp(503, {"message": "unavailable (test)"})
    _answering(fake, monkeypatch, "/api/v1/spool", failing)
    got = _filaments("glow").get_json()
    assert got["success"] is False and got["msg"].startswith(msg), got
    plain = _filaments("glow", strict=False).get_json()            # the search panel's, as it was
    assert plain["success"] is True and [(r["id"], r["spools_count"]) for r in plain["results"]] == [(1057, 0)]


@pytest.mark.parametrize("how", ["list_reads_fail", "down"])
def test_without_strict_the_search_panels_answer_is_as_it_was(fake, how):
    """Pins already-right code: the search panel's own call is the one it was."""
    setattr(fake, how, True)
    assert _search("glow", strict=False).get_json() == {"success": True, "results": []}


def test_the_route_passes_strict_only_when_asked():
    """test_search_api.test_api_endpoint pins the call without it, keyword for keyword."""
    with patch("spoolman_api.search_inventory", return_value=[]) as mock_search:
        _search("glow")
        assert mock_search.call_args.kwargs["strict"] is True
        _search("glow", strict=False)
        assert "strict" not in mock_search.call_args.kwargs
