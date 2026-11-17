"""Tests for the filament merge endpoint (Group 11.2).

Covers POST /api/filament/<src>/merge_into/<dst>:
  - Source == target is rejected.
  - Source / target not found are rejected.
  - Happy path re-parents every child spool, then deletes source.
  - Partial re-parent failure aborts before deleting source (atomic-ish).
  - Source-delete failure after successful re-parents is reported.
  - A spool list Spoolman refused, or one that isn't a list of spools, refuses
    the merge before anything is written (Group 53.2): it used to read as "no
    spools" and go straight on to delete the source.
  - Group 53 review (D1): every entry must be a spool record, a dict whose `id`
    is an int (not a bool) with a `filament` object whose `id` is an int: an
    entry with no id was skipped, and the source deleted. The list is read by
    `filament.id` (the old `filament_id` alias is deprecated), and a spool the
    list holds of another filament refuses the merge: Spoolman ignores a query
    parameter it doesn't know and answers every spool, which the merge would
    all have re-parented.
  - Group 53 review (D3b): a filament Spoolman has no record of is "not found"
    (404), and one it couldn't send (a 5xx, no answer) is "couldn't read"
    (502); both read nothing more and write nothing. get_filament handed back
    Spoolman's 404 or 5xx body as if it were the filament. A 200 holding another
    filament's record is "couldn't read" too (rd-2: nothing pinned the id rule).
  - Group 53 review (D2): every answer is in words, never Spoolman's address or
    raw JSON (refusal_words), "try again in a moment" only where a retry can
    help, and the Activity Log lines escape the names and Spoolman's text.
  - Group 53 review (rd-1): hub.log keeps what came back. A filament read that
    gives no filament leaves ONE WARNING line from get_filament_answer, with the
    status and the start of the body, or the exception (it logged "Merge:
    couldn't read filament 9: None"); a spool list that isn't JSON names its
    status and body (it logged only where JSON parsing stopped).

TestMergeFilament stubs the Spoolman helpers. TestMergeAgainstSpoolman runs the
real route, the real read and write helpers and the real requests calls they
make, against the repo's Spoolman fake. The endpoint enumerates children via
direct `requests.get` (not `get_spools_for_filament`, so it can include
archived), then calls `update_spool_or_raise` per spool, then `delete_filament`.
"""
from __future__ import annotations

import http.client
import re
from urllib.parse import parse_qs, urlsplit

import pytest
import requests
from unittest.mock import patch, MagicMock

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import app as flask_app
import spoolman_api
import state
from spoolman_extra_fake import SpoolmanHTTPFake, _Resp


@pytest.fixture()
def client():
    flask_app.config['TESTING'] = True
    with flask_app.test_client() as c:
        yield c


def _ok_json(payload):
    m = MagicMock()
    m.ok = True
    m.status_code = 200
    m.json = MagicMock(return_value=payload)
    return m


def _answer(status=200, body=None, text='', json_error=None):
    """Spoolman's answer to the spool-list read: `body` from .json(), or
    `json_error` raised by it, as requests does for a body that isn't JSON."""
    m = MagicMock()
    m.ok = 200 <= status < 400
    m.status_code = status
    m.text = text
    m.json = MagicMock(side_effect=json_error) if json_error else MagicMock(return_value=body)
    return m


class _Page:
    """An answer whose body isn't JSON (a proxy's page): requests' .json() raises."""

    def __init__(self, status, text):
        self.status_code, self.ok, self.text = status, 200 <= status < 300, text

    def json(self):
        raise requests.exceptions.JSONDecodeError("Expecting value", self.text, 0)


def _answered(*records):
    """spoolman_api.get_filament_answer's answers for these records, in order
    (Group 53 review, D3b: the route reads its two filaments through it)."""
    return [(rec, True) for rec in records]


def _no_such_filament(fid):
    """get_filament_answer's answer for a filament Spoolman has no record of:
    its 404 body, a dict with no id."""
    return ({'message': f'No filament with ID {fid} found.'}, True)


def _spools_of(fid, *sids):
    """Spool records as Spoolman's list answers them: each names its filament."""
    return [{'id': sid, 'filament': {'id': fid}} for sid in sids]


class TestMergeFilament:
    def test_rejects_same_source_and_target(self, client):
        r = client.post('/api/filament/7/merge_into/7')
        assert r.status_code == 400
        body = r.get_json()
        assert body['success'] is False
        assert 'differ' in body['error'].lower()

    def test_rejects_missing_source(self, client):
        # Group 53 review (D3b): "missing" is Spoolman's own answer for it, its
        # 404 body. This stubbed get_filament to None, which the real read never
        # answers for a 404 (it answered the body, read as found).
        with patch('spoolman_api.get_filament_answer', side_effect=[_no_such_filament(7)]):
            r = client.post('/api/filament/7/merge_into/9')
        assert r.status_code == 404
        body = r.get_json()
        assert body['success'] is False
        assert '#7' in body['error']

    def test_rejects_missing_target(self, client):
        # Source resolves, Spoolman has no record of the target.
        with patch('spoolman_api.get_filament_answer',
                   side_effect=_answered({'id': 7, 'name': 'src'}) + [_no_such_filament(9)]):
            r = client.post('/api/filament/7/merge_into/9')
        assert r.status_code == 404
        body = r.get_json()
        assert body['success'] is False
        assert '#9' in body['error']

    def test_happy_path_reparents_and_deletes_source(self, client):
        src = {'id': 7, 'name': 'PLA Old'}
        dst = {'id': 9, 'name': 'PLA New'}
        children = _spools_of(7, 101, 102, 103)

        with patch('spoolman_api.get_filament_answer', side_effect=_answered(src, dst)), \
             patch('app.requests.get', return_value=_ok_json(children)), \
             patch('spoolman_api.update_spool_or_raise', return_value={'id': 'ok'}) as mock_upd, \
             patch('spoolman_api.delete_filament', return_value=True) as mock_del:
            r = client.post('/api/filament/7/merge_into/9')

        assert r.status_code == 200
        body = r.get_json()
        assert body['success'] is True
        assert body['source_filament_id'] == 7
        assert body['target_filament_id'] == 9
        assert body['reparented_spool_ids'] == [101, 102, 103]
        # Each child should have been re-parented onto filament 9.
        assert mock_upd.call_count == 3
        for call in mock_upd.call_args_list:
            args, _kwargs = call
            assert args[1] == {'filament_id': 9}
        mock_del.assert_called_once_with(7)

    def test_partial_reparent_failure_aborts_without_deleting_source(self, client):
        src = {'id': 7, 'name': 'src'}
        dst = {'id': 9, 'name': 'dst'}
        children = _spools_of(7, 101, 102)

        def upd_side_effect(sid, data):
            if sid == 102:
                raise spoolman_api.SpoolmanRejection("HTTP 409: cannot reassign")
            return {'id': sid}

        with patch('spoolman_api.get_filament_answer', side_effect=_answered(src, dst)), \
             patch('app.requests.get', return_value=_ok_json(children)), \
             patch('spoolman_api.update_spool_or_raise', side_effect=upd_side_effect), \
             patch('spoolman_api.delete_filament') as mock_del:
            r = client.post('/api/filament/7/merge_into/9')

        assert r.status_code == 502
        body = r.get_json()
        assert body['success'] is False
        assert 'left in place' in body['error']
        assert body['reparented_spool_ids'] == [101]
        assert len(body['spool_errors']) == 1
        assert body['spool_errors'][0]['spool_id'] == 102
        # Critically: source filament must NOT be deleted when any spool fails.
        mock_del.assert_not_called()

    def test_source_delete_failure_after_full_reparent_is_reported(self, client):
        src = {'id': 7, 'name': 'src'}
        dst = {'id': 9, 'name': 'dst'}
        children = _spools_of(7, 101)

        spoolman_api.LAST_SPOOLMAN_ERROR = "HTTP 500: db locked"
        with patch('spoolman_api.get_filament_answer', side_effect=_answered(src, dst)), \
             patch('app.requests.get', return_value=_ok_json(children)), \
             patch('spoolman_api.update_spool_or_raise', return_value={'id': 101}), \
             patch('spoolman_api.delete_filament', return_value=False):
            r = client.post('/api/filament/7/merge_into/9')

        assert r.status_code == 502
        body = r.get_json()
        assert body['success'] is False
        assert 'db locked' in body['error']
        assert body['reparented_spool_ids'] == [101]

    def test_zero_children_still_deletes_source(self, client):
        # Edge: orphan filament with no spools at all — merge is essentially
        # a rename + delete, but the endpoint should still succeed cleanly.
        src = {'id': 7, 'name': 'src'}
        dst = {'id': 9, 'name': 'dst'}
        with patch('spoolman_api.get_filament_answer', side_effect=_answered(src, dst)), \
             patch('app.requests.get', return_value=_ok_json([])), \
             patch('spoolman_api.update_spool_or_raise') as mock_upd, \
             patch('spoolman_api.delete_filament', return_value=True) as mock_del:
            r = client.post('/api/filament/7/merge_into/9')

        assert r.status_code == 200
        body = r.get_json()
        assert body['success'] is True
        assert body['reparented_spool_ids'] == []
        mock_upd.assert_not_called()
        mock_del.assert_called_once_with(7)

    # --- Group 53.2: a spool list FCC can't read is not "no spools" ---------
    # Read as an empty list, a refused read went straight on to DELETE the
    # source filament. Spoolman refuses to delete a filament that still has
    # spools, so nothing was lost, but the answer blamed the delete and the
    # outcome rested on Spoolman's foreign key. A 200 whose body wasn't a list
    # iterated a dict's keys, or crashed part-way after re-parenting a spool.

    def _merge_with_list_answer(self, client, answer):
        src = {'id': 7, 'name': 'PLA Old'}
        dst = {'id': 9, 'name': 'PLA New'}
        with patch('spoolman_api.get_filament_answer', side_effect=_answered(src, dst)), \
             patch('app.requests.get', return_value=answer), \
             patch('spoolman_api.update_spool_or_raise', return_value={'id': 'ok'}) as mock_upd, \
             patch('spoolman_api.delete_filament', return_value=True) as mock_del, \
             patch.object(state.logger, 'error') as mock_log:
            r = client.post('/api/filament/7/merge_into/9')
        return r, mock_upd, mock_del, mock_log

    @staticmethod
    def _logged_for_filament_7(mock_log):
        return [c.args[0] for c in mock_log.call_args_list
                if c.args and 'enumerate spools for filament 7' in str(c.args[0])]

    @pytest.mark.parametrize('status', [404, 422, 500, 503])
    def test_a_refused_spool_list_refuses_the_merge_before_any_write(self, client, status):
        # Group 53 review (D2): Spoolman's refusal in its words (refusal_words),
        # "try again in a moment" only for a 5xx (a 4xx comes back the same).
        # It said "Spoolman answered HTTP 404. ... try again in a moment." for all.
        r, mock_upd, mock_del, mock_log = self._merge_with_list_answer(
            client, _answer(status, body={'message': 'database is locked'},
                            text='{"message": "database is locked"}'))

        assert r.status_code == 502
        body = r.get_json()
        assert body['success'] is False
        assert body['error'].startswith('Could not list source spools: ')
        assert 'Spoolman refused it: database is locked.' in body['error']
        assert 'Nothing was merged' in body['error']
        assert ('try again in a moment' in body['error']) is (status >= 500)
        assert '{' not in body['error'] and 'HTTP' not in body['error']
        mock_upd.assert_not_called()
        mock_del.assert_not_called()
        logged = self._logged_for_filament_7(mock_log)
        assert logged and f'HTTP {status}' in logged[0] and 'database is locked' in logged[0]

    @pytest.mark.parametrize('listed', [
        {},                             # read as "no spools": the source was deleted
        {'items': [{'id': 101}]},       # a dict: its keys were iterated
        None,                           # JSON null
        'spools',                       # a JSON string
        [101, 102],                     # ids, not spool records
        [{'id': 101}, 'x'],             # #101 re-parented, then a crash
        # Group 53 review (D1): an entry with no int id was skipped, then the
        # source deleted ("0 spools re-parented; source deleted").
        [{'name': 'x'}],
        [{'detail': 'Not authenticated'}],
        [{'id': None}],
        [{'id': True}],                 # a bool is not an id
        [{'id': '101'}],
        [{'id': 101}, {}],              # #101 re-parented, {} skipped, source deleted
        [{'id': 101, 'filament': {'id': 7}}, {}],
        [{'id': 101, 'filament': {'id': 7}}, {'id': None, 'filament': {'id': 7}}],
        # ... and every spool names its filament, as Spoolman's records do
        [{'id': 101}],
        [{'id': 101, 'filament': None}],
        [{'id': 101, 'filament': {'name': 'PLA Old'}}],
        [{'id': 101, 'filament': {'id': True}}],
    ])
    def test_a_spool_list_that_isnt_a_list_of_spools_refuses_the_merge_before_any_write(
            self, client, listed):
        r, mock_upd, mock_del, mock_log = self._merge_with_list_answer(client, _answer(200, body=listed))

        assert r.status_code == 502
        body = r.get_json()
        assert body['success'] is False
        assert body['error'].startswith('Could not list source spools: ')
        assert "Spoolman's answer couldn't be read" in body['error']
        assert 'Nothing was merged' in body['error']
        mock_upd.assert_not_called()
        mock_del.assert_not_called()
        assert self._logged_for_filament_7(mock_log)

    def test_a_spool_list_that_isnt_json_says_so_in_words(self, client):
        bad = requests.exceptions.JSONDecodeError('Expecting value', '<html>Bad Gateway</html>', 0)
        r, mock_upd, mock_del, mock_log = self._merge_with_list_answer(
            client, _answer(200, text='<html>Bad Gateway</html>', json_error=bad))

        assert r.status_code == 502
        body = r.get_json()
        assert body['success'] is False
        assert body['error'].startswith('Could not list source spools: ')
        assert "Spoolman's answer couldn't be read" in body['error']
        assert 'Expecting value' not in body['error']
        mock_upd.assert_not_called()
        mock_del.assert_not_called()
        assert self._logged_for_filament_7(mock_log)


# --- Group 53 review: the real route against the repo's Spoolman fake ----------

SM = "http://spoolman.test:7913"
LIST_PATH = "/api/v1/spool"
UNREAD_LIST = ("Could not list source spools: Spoolman's answer couldn't be read. "
               "Nothing was merged; try again in a moment.")


class _Spoolman(SpoolmanHTTPFake):
    """The repo's Spoolman fake, plus what Merge Filament also reaches: a spool
    list filtered as Spoolman filters it, a DELETE, and a canned answer, or an
    error raised as requests raises one when Spoolman doesn't answer, for one
    request (`canned[(verb, path)]`).

    `honours` names the list parameters this Spoolman filters by. Spoolman 0.27
    honours `filament.id` and its deprecated alias `filament_id`; a release that
    dropped the alias would ignore it, as Spoolman ignores any parameter it
    doesn't know, and answer every spool. A PATCH of `filament_id` moves the
    spool's nested filament, which is how Spoolman's records name it, and a
    filament that still has spools isn't deleted (the fake's own refusal)."""

    def __init__(self, honours=("filament.id", "filament_id")):
        super().__init__()
        self.honours = tuple(honours)
        self.get_urls = []
        self.deletes = []
        self.canned = {}

    def _canned(self, verb, path):
        answer = self.canned.get((verb, path))
        if isinstance(answer, BaseException):
            raise answer
        return answer

    def get(self, url, timeout=None, **kw):
        self.get_urls.append(str(url))
        parts = urlsplit(str(url))
        path = parts.path.rstrip("/")
        canned = self._canned("GET", path)
        if canned is not None:
            return canned
        r = super().get(url, timeout=timeout, **kw)
        if path == LIST_PATH and r.ok:
            query = parse_qs(parts.query)
            for name in self.honours:
                if name in query:
                    fid = int(query[name][0])
                    return _Resp(200, [s for s in r.json() if (s.get("filament") or {}).get("id") == fid])
        return r

    def patch(self, url, json=None, timeout=None, **kw):  # noqa: A002 (requests' kwarg)
        path = urlsplit(str(url)).path.rstrip("/")
        canned = self._canned("PATCH", path)
        if canned is not None:
            m = re.fullmatch(r"/api/v1/(spool|filament|vendor)/(\d+)", path)
            self.patches.append((m.group(1), int(m.group(2)), json))
            return canned
        r = super().patch(url, json=json, timeout=timeout, **kw)
        m = re.fullmatch(r"/api/v1/spool/(\d+)", path)
        if r.ok and m and "filament_id" in (json or {}):
            rec = self.records["spool"][int(m.group(1))]
            rec["filament"] = {"id": rec.pop("filament_id")}
        return r

    def delete(self, url, timeout=None, **kw):
        path = urlsplit(str(url)).path.rstrip("/")
        self.deletes.append(path)
        canned = self._canned("DELETE", path)
        if canned is not None:
            return canned
        m = re.fullmatch(r"/api/v1/(spool|filament)/(\d+)", path)
        if not m or int(m.group(2)) not in self.records[m.group(1)]:
            return _Resp(404, {"message": "No such record (test)."})
        entity, eid = m.group(1), int(m.group(2))
        if entity == "filament" and any(self.filament_of(s) == eid for s in self.records["spool"]):
            return _Resp(400, {"message": f"Filament {eid} still has spools (test)."})
        del self.records[entity][eid]
        return _Resp(200, {})

    def filament_of(self, sid):
        return self.records["spool"][sid]["filament"]["id"]

    def list_reads(self):
        return [u for u in self.get_urls if urlsplit(u).path.rstrip("/") == LIST_PATH]


def _stocked(**kw):
    """Filaments #7 (the source) and #9 (the target); #7 has spools #101 and #102
    (archived), #9 has #200, and filament #12 has #300."""
    fake = _Spoolman(**kw)
    fake.add("filament", 7, name="PLA Old", material="PLA")
    fake.add("filament", 9, name="PLA New", material="PLA")
    fake.add("spool", 101, filament={"id": 7}, location="SHELF")
    fake.add("spool", 102, filament={"id": 7}, location="SHELF", archived=True)
    fake.add("spool", 200, filament={"id": 9}, location="SHELF")
    fake.add("spool", 300, filament={"id": 12}, location="BIN")
    return fake


def _merge(client, fake, src=7, dst=9, hub=None):
    """POST the merge with every Spoolman request on `fake`. Answers (response,
    Activity Log lines as (msg, level), hub.log error lines). `hub`, a list, is
    handed every hub.log ERROR and WARNING line, as (LEVEL, text)."""
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
        r = client.post(f"/api/filament/{src}/merge_into/{dst}")
    return r, logged, [line for level, line in hub if level == "ERROR"]


def _about(hub, fid):
    """The hub.log lines that name filament `fid`."""
    return [(level, line) for level, line in hub if re.search(rf"\bfilament {fid}\b", line)]


class TestMergeAgainstSpoolman:
    def test_a_merge_moves_the_sources_spools_then_deletes_it(self, client):
        fake = _stocked()
        r, logged, _errors = _merge(client, fake)

        assert r.status_code == 200, r.get_json()
        assert r.get_json()["reparented_spool_ids"] == [101, 102]
        assert [fake.filament_of(s) for s in (101, 102, 200, 300)] == [9, 9, 9, 12]
        assert fake.records["spool"][102]["archived"] is True
        assert fake.deletes == ["/api/v1/filament/7"] and 7 not in fake.records["filament"]
        # D1 (a): by `filament.id`, archived spools too, as stock_report reads it.
        assert fake.list_reads() == [f"{SM}/api/v1/spool?filament.id=7&allow_archived=true"]
        assert [level for _msg, level in logged] == ["INFO"]

    def test_a_spoolman_without_the_old_filter_name_still_merges_only_the_sources_spools(self, client):
        # Spoolman deprecated `filament_id`. A release without it ignores it and
        # answers every spool, and the merge re-parented every spool of every
        # filament onto the target.
        fake = _stocked(honours=("filament.id",))
        r, _logged, _errors = _merge(client, fake)

        assert r.status_code == 200, r.get_json()
        assert r.get_json()["reparented_spool_ids"] == [101, 102]
        assert [(entity, sid) for entity, sid, _body in fake.patches] == [("spool", 101), ("spool", 102)]
        assert [fake.filament_of(s) for s in (101, 102, 200, 300)] == [9, 9, 9, 12]

    def test_a_list_holding_other_filaments_spools_refuses_the_merge_before_any_write(self, client):
        fake = _stocked(honours=())    # a filter it doesn't know: every spool
        r, logged, errors = _merge(client, fake)

        assert r.status_code == 502
        assert r.get_json() == {"success": False, "error": (
            "Spoolman listed spool #200 under filament #7, but it belongs to filament #9 "
            "(and 1 more spool of another filament). Nothing was merged.")}
        assert fake.patches == [] and fake.deletes == [] and logged == []
        assert [fake.filament_of(s) for s in (101, 102, 200, 300)] == [7, 7, 9, 12]
        assert any("#200 (filament 9)" in e and "#300 (filament 12)" in e for e in errors), errors

    def test_one_spool_of_another_filament_is_named(self, client):
        fake = _stocked()
        fake.canned[("GET", LIST_PATH)] = _Resp(200, [
            {"id": 101, "filament": {"id": 7}}, {"id": 200, "filament": {"id": 9}}])
        r, logged, _errors = _merge(client, fake)

        assert r.status_code == 502
        assert r.get_json()["error"] == ("Spoolman listed spool #200 under filament #7, but it belongs "
                                         "to filament #9. Nothing was merged.")
        assert fake.patches == [] and fake.deletes == [] and logged == []

    @pytest.mark.parametrize("listed", [
        [{"name": "x"}],
        [{"id": None}],
        [{"id": True, "filament": {"id": 7}}],
        [{"id": 101, "filament": {"id": 7}}, {}],
        [{"id": 101}],                                  # no filament: whose is it?
    ])
    def test_a_list_entry_that_isnt_a_spool_record_refuses_the_merge_before_any_write(self, client, listed):
        fake = _stocked()
        fake.canned[("GET", LIST_PATH)] = _Resp(200, listed)
        r, logged, errors = _merge(client, fake)

        assert r.status_code == 502
        assert r.get_json() == {"success": False, "error": UNREAD_LIST}
        assert fake.patches == [] and fake.deletes == [] and logged == []
        assert any("filament 7" in e for e in errors), errors

    # --- D3b: Spoolman's 404 body is "not found"; a 5xx or no answer is "couldn't read"

    @pytest.mark.parametrize("missing, words", [
        (7, "Source filament #7 not found."),
        (9, "Target filament #9 not found."),
    ])
    def test_a_filament_spoolman_has_no_record_of_is_not_found_and_nothing_follows(self, client, missing, words):
        fake = _stocked()
        del fake.records["filament"][missing]     # its read answers 404 {"message": "No filament with ID …"}
        hub = []
        r, logged, _errors = _merge(client, fake, hub=hub)

        assert r.status_code == 404
        assert r.get_json() == {"success": False, "error": words}
        assert fake.list_reads() == [] and fake.patches == [] and fake.deletes == [] and logged == []
        # rd-1: hub.log says what came back (a 404 logged nothing at all).
        [(level, line)] = _about(hub, missing)
        assert level == "WARNING", hub
        assert "HTTP 404" in line and f"No filament with ID {missing} found." in line, line

    @pytest.mark.parametrize("which", [7, 9])
    @pytest.mark.parametrize("answer, said", [
        (_Resp(500, {"message": "database is locked"}), ["HTTP 500", '{"message": "database is locked"}']),
        (_Resp(503, {"message": "Service Unavailable"}), ["HTTP 503", "Service Unavailable"]),
        (_Page(503, "<html><body>502 Bad Gateway nginx</body></html>"),
         ["HTTP 503", "<html><body>502 Bad Gateway nginx</body></html>"]),
        (requests.exceptions.ReadTimeout(
            "HTTPConnectionPool(host='spoolman.test', port=7913): Read timed out. (read timeout=3)"),
         ["no answer", "ReadTimeout", "host='spoolman.test', port=7913", "Read timed out"]),
    ], ids=["500", "503", "503 page", "no answer"])
    def test_a_filament_spoolman_couldnt_send_is_couldnt_read_and_nothing_follows(self, client, which, answer,
                                                                                  said):
        fake = _stocked()
        fake.canned[("GET", f"/api/v1/filament/{which}")] = answer
        hub = []
        r, logged, _errors = _merge(client, fake, hub=hub)

        assert r.status_code == 502
        assert r.get_json() == {"success": False, "error": (
            f"Couldn't read filament #{which} from Spoolman, so nothing was merged. Try again in a moment.")}
        assert fake.list_reads() == [] and fake.patches == [] and fake.deletes == [] and logged == []
        # rd-1: ONE hub.log line about the read, get_filament_answer's, saying what
        # came back. The merge logged its own at ERROR: "Merge: couldn't read
        # filament 9: None", or "... 7: Spoolman did not answer".
        [(level, line)] = _about(hub, which)
        assert level == "WARNING", hub
        for words in said:
            assert words in line, (words, line)
        assert "None" not in line

    @pytest.mark.parametrize("which", [7, 9], ids=["source", "target"])
    def test_a_record_of_another_filament_is_couldnt_read_and_nothing_follows(self, client, which):
        """rd-2: a read is the filament only when its id is the one asked for.
        Spoolman (or a proxy or cache before it) answering 200 with filament #8's
        record: read as the source (the id check dropped), the merge would
        re-parent #7's spools and delete #7 on #8's record; read as the target, it
        would re-parent them onto a filament it never read."""
        fake = _stocked()
        fake.canned[("GET", f"/api/v1/filament/{which}")] = _Resp(
            200, {"id": 8, "name": "PLA Other", "material": "PLA"})
        r, logged, _errors = _merge(client, fake)

        assert r.status_code == 502
        assert r.get_json() == {"success": False, "error": (
            f"Couldn't read filament #{which} from Spoolman, so nothing was merged. Try again in a moment.")}
        assert fake.list_reads() == [] and fake.patches == [] and fake.deletes == [] and logged == []
        assert [fake.filament_of(s) for s in (101, 102, 200, 300)] == [7, 7, 9, 12]
        assert set(fake.records["filament"]) == {7, 9}

    def test_a_spool_list_that_isnt_json_names_its_status_and_body_in_hub_log(self, client):
        """rd-1: hub.log keeps what came back. It logged only where JSON parsing
        stopped ("its answer isn't JSON (Expecting value: line 1 column 1 (char
        0))"), so a proxy's login page and a list cut off part-way read alike."""
        fake = _stocked()
        fake.canned[("GET", LIST_PATH)] = _Page(200, "<html>proxy login page</html>")
        r, logged, errors = _merge(client, fake)

        assert r.status_code == 502
        assert r.get_json() == {"success": False, "error": UNREAD_LIST}
        assert fake.patches == [] and fake.deletes == [] and logged == []
        [line] = [e for e in errors if "enumerate spools for filament 7" in e]
        assert "HTTP 200" in line and "<html>proxy login page</html>" in line, line

    # --- D2: every answer in words; hub.log and the Activity Log keep the whole text

    @pytest.mark.parametrize("raised, words", [
        (requests.exceptions.ReadTimeout(
            "HTTPConnectionPool(host='spoolman.test', port=7913): Read timed out. (read timeout=5)"),
         "Spoolman didn't answer in time."),
        (requests.exceptions.ConnectionError(
            "HTTPConnectionPool(host='spoolman.test', port=7913): Max retries exceeded with url: "
            "/api/v1/spool?filament.id=7&allow_archived=true (Caused by NewConnectionError("
            "'<urllib3.connection.HTTPConnection object>: Failed to establish a new connection'))"),
         "FCC couldn't reach Spoolman."),
        # A connection Spoolman (or a proxy) dropped: requests' words name no host, so
        # the line names the address it asked (final verification, v2).
        (requests.exceptions.ConnectionError(
            ("Connection aborted.", http.client.RemoteDisconnected("Remote end closed connection without response"))),
         "Spoolman dropped the connection before answering."),
    ], ids=["timeout", "down", "dropped"])
    def test_a_list_read_spoolman_didnt_answer_says_so_in_words(self, client, raised, words):
        fake = _stocked()
        fake.canned[("GET", LIST_PATH)] = raised
        r, logged, errors = _merge(client, fake)

        assert r.status_code == 502
        assert r.get_json() == {"success": False, "error": (
            f"Could not list source spools: {words} Nothing was merged; try again in a moment.")}
        assert fake.patches == [] and fake.deletes == [] and logged == []
        assert any("spoolman.test" in e for e in errors), errors     # the address stays in hub.log

    def test_a_list_read_spoolman_refused_says_its_words_and_no_retry(self, client):
        fake = _stocked()
        fake.canned[("GET", LIST_PATH)] = _Resp(422, {"detail": [
            {"loc": ["query", "filament.id"], "msg": "value is not a valid integer", "type": "type_error.integer"}]})
        r, logged, errors = _merge(client, fake)

        assert r.status_code == 502
        assert r.get_json()["error"] == ("Could not list source spools: Spoolman refused it: "
                                         "value is not a valid integer. Nothing was merged.")
        assert fake.patches == [] and fake.deletes == [] and logged == []
        assert any("HTTP 422" in e for e in errors), errors

    def test_a_refused_source_delete_is_said_in_words_and_logged_in_full(self, client):
        fake = _stocked()
        fake.canned[("DELETE", "/api/v1/filament/7")] = _Resp(500, {"message": "database is locked"})
        r, logged, _errors = _merge(client, fake)

        assert r.status_code == 502
        body = r.get_json()
        assert body["error"] == ("Spools re-parented, but source filament delete failed: "
                                 "Spoolman refused it: database is locked.")
        assert body["reparented_spool_ids"] == [101, 102]
        [(line, level)] = logged
        assert level == "ERROR" and 'HTTP 500: {"message": "database is locked"}' in line

    def test_a_refused_reparent_is_said_in_words_and_logged_in_full(self, client):
        fake = _stocked()
        fake.canned[("PATCH", "/api/v1/spool/102")] = _Resp(400, {"message": "Unknown extra field 'colour'"})
        r, logged, _errors = _merge(client, fake)

        assert r.status_code == 502
        body = r.get_json()
        assert body["error"] == "Some spools could not be re-parented; source filament left in place."
        assert body["reparented_spool_ids"] == [101]
        assert body["spool_errors"] == [
            {"spool_id": 102, "error": "Spoolman refused it: Unknown extra field 'colour'"}]
        assert fake.deletes == [] and 7 in fake.records["filament"]
        [(line, level)] = logged
        assert level == "ERROR" and "HTTP 400" in line and "Unknown extra field 'colour'" in line

    @pytest.mark.parametrize("outcome", ["merged", "reparent refused", "delete refused"])
    def test_the_activity_log_lines_escape_the_names_and_spoolmans_text(self, client, outcome):
        fake = _stocked()
        fake.records["filament"][7]["name"] = "PLA <b>Old</b> & Co"
        fake.records["filament"][9]["name"] = "PLA <i>New</i>"
        if outcome == "reparent refused":
            fake.canned[("PATCH", "/api/v1/spool/101")] = _Resp(400, {"message": "Unknown field <x>"})
        elif outcome == "delete refused":
            fake.canned[("DELETE", "/api/v1/filament/7")] = _Resp(500, {"message": "locked <y>"})
        _r, logged, _errors = _merge(client, fake)

        [(line, _level)] = logged
        assert "PLA &lt;b&gt;Old&lt;/b&gt; &amp; Co" in line and "PLA &lt;i&gt;New&lt;/i&gt;" in line
        assert "<b>" not in line and "<i>" not in line
        if outcome != "merged":
            assert "&lt;x&gt;" in line or "&lt;y&gt;" in line
            assert "<x>" not in line and "<y>" not in line
