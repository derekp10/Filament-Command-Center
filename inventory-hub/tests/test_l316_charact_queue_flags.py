"""L316 characterization tests — pins pre-carve behavior of the print-queue
flag endpoints (/api/print_queue/set_flag and the uncovered filament branch of
/api/print_queue/mark_printed, app.py ~3864-3938). Generated from the
2026-07-01 coverage audit. Do not weaken these to make a refactor pass.

Scope:
  * api_print_queue_set_flag — ZERO direct coverage pre-audit. Pins the
    full-extra read-modify-write payload shape passed to update_spool /
    update_filament, the LAST_SPOOLMAN_ERROR surfacing contract (the
    2026-04-27 outage-class fix), and the undocumented quirks (no id
    validation, no int-coercion, bare {success: false} fall-through).
  * api_print_queue_mark_printed — filament branch (get_filament ->
    update_filament with needs_label_print lowered) + its Spoolman-rejection
    path. The spool happy path + legacy-ID rejection already live in
    tests/test_print_queue.py and are deliberately NOT duplicated here.

All tests are host-runnable unit tests: Flask test_client only, every
Spoolman call mocked. No live server, no live Spoolman.
"""
from __future__ import annotations

import os
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import app as app_module  # noqa: E402


@pytest.fixture
def client():
    app_module.app.config["TESTING"] = True
    return app_module.app.test_client()


# ---------------------------------------------------------------------------
# /api/print_queue/set_flag — spool flavor
# ---------------------------------------------------------------------------

def test_set_flag_spool_full_extra_readback_payload(client):
    """Happy path pins the read-modify-write full-extra semantics: the handler
    fetches the spool, flips needs_label_print=True on the FETCHED extra dict
    (in place), and passes that whole dict back to update_spool — siblings
    (including system-managed keys like container_slot) ride along in the SENT
    payload; dedup/merge is update_spool's job, not this handler's. The
    payload must contain ONLY the 'extra' key (no weight fields, so no
    auto-archive side effects — per the CLAUDE.md write-surface table)."""
    fetched = {
        "id": 10,
        "extra": {
            "needs_label_print": False,
            "container_slot": '"2"',
            "physical_source": "PM-DB-XL-L",
            "purchase_url": "https://example.com/x",
        },
    }
    with patch.object(app_module.spoolman_api, "get_spool", return_value=fetched) as mock_get, \
         patch.object(app_module.spoolman_api, "update_spool", return_value={"id": 10}) as mock_update:
        res = client.post("/api/print_queue/set_flag", json={"id": 10, "type": "spool"})

    assert res.status_code == 200
    assert res.get_json() == {"success": True}

    mock_get.assert_called_once_with(10)
    mock_update.assert_called_once()
    args, kwargs = mock_update.call_args
    assert kwargs == {}
    assert args[0] == 10
    payload = args[1]
    # Only 'extra' — no location/weight fields that could trigger side effects.
    assert set(payload.keys()) == {"extra"}
    assert payload["extra"] == {
        "needs_label_print": True,
        "container_slot": '"2"',
        "physical_source": "PM-DB-XL-L",
        "purchase_url": "https://example.com/x",
    }
    # Read-modify-write: the handler mutates and forwards the FETCHED extra
    # dict itself (not a copy). A pure move must preserve this.
    assert payload["extra"] is fetched["extra"]


def test_set_flag_spool_missing_extra_key_defaults_to_flag_only(client):
    """A spool record with no 'extra' key at all gets a fresh {} default, so
    the sent extra dict is exactly {'needs_label_print': True}."""
    with patch.object(app_module.spoolman_api, "get_spool", return_value={"id": 11}), \
         patch.object(app_module.spoolman_api, "update_spool", return_value={"id": 11}) as mock_update:
        res = client.post("/api/print_queue/set_flag", json={"id": 11, "type": "spool"})

    assert res.get_json() == {"success": True}
    args, _ = mock_update.call_args
    assert args[1] == {"extra": {"needs_label_print": True}}


def test_set_flag_spool_rejection_surfaces_last_spoolman_error(client):
    """update_spool -> None must surface LAST_SPOOLMAN_ERROR verbatim in the
    response msg AND write a state.logger.error naming the spool id + the
    Spoolman body. This is the 2026-04-27 outage-class contract: a rejected
    write must never fail silently."""
    with patch.object(app_module.spoolman_api, "get_spool",
                      return_value={"id": 10, "extra": {"needs_label_print": False}}), \
         patch.object(app_module.spoolman_api, "update_spool", return_value=None), \
         patch.object(app_module.spoolman_api, "LAST_SPOOLMAN_ERROR",
                      "HTTP 400: Unknown extra field"), \
         patch.object(app_module.state.logger, "error") as mock_err:
        res = client.post("/api/print_queue/set_flag", json={"id": 10, "type": "spool"})

    assert res.status_code == 200
    assert res.get_json() == {"success": False, "msg": "HTTP 400: Unknown extra field"}
    mock_err.assert_called_once()
    logged = mock_err.call_args[0][0]
    assert "set_flag" in logged
    assert "spool 10" in logged
    assert "HTTP 400: Unknown extra field" in logged


def test_set_flag_spool_rejection_fallback_msg_when_error_unset(client):
    """When update_spool returns None but LAST_SPOOLMAN_ERROR is None (e.g. a
    transport-level failure that never got a body), the msg falls back to the
    literal 'Spoolman rejected the update'."""
    with patch.object(app_module.spoolman_api, "get_spool",
                      return_value={"id": 10, "extra": {}}), \
         patch.object(app_module.spoolman_api, "update_spool", return_value=None), \
         patch.object(app_module.spoolman_api, "LAST_SPOOLMAN_ERROR", None), \
         patch.object(app_module.state.logger, "error"):
        res = client.post("/api/print_queue/set_flag", json={"id": 10, "type": "spool"})

    assert res.get_json() == {"success": False, "msg": "Spoolman rejected the update"}


# ---------------------------------------------------------------------------
# /api/print_queue/set_flag — filament flavor
# ---------------------------------------------------------------------------

def test_set_flag_filament_full_extra_readback_payload(client):
    """Filament mirror of the spool happy path: get_filament -> full fetched
    extra with needs_label_print raised -> update_filament. The spool-side
    functions must not be touched."""
    fetched = {
        "id": 5,
        "extra": {
            "needs_label_print": False,
            "slicer_profile": "Prusament PETG @0.4",
            "sample_printed": True,
        },
    }
    with patch.object(app_module.spoolman_api, "get_filament", return_value=fetched) as mock_get, \
         patch.object(app_module.spoolman_api, "update_filament", return_value={"id": 5}) as mock_update, \
         patch.object(app_module.spoolman_api, "get_spool") as mock_get_spool, \
         patch.object(app_module.spoolman_api, "update_spool") as mock_update_spool:
        res = client.post("/api/print_queue/set_flag", json={"id": 5, "type": "filament"})

    assert res.status_code == 200
    assert res.get_json() == {"success": True}
    mock_get.assert_called_once_with(5)
    mock_get_spool.assert_not_called()
    mock_update_spool.assert_not_called()

    args, _ = mock_update.call_args
    assert args[0] == 5
    assert set(args[1].keys()) == {"extra"}
    assert args[1]["extra"] == {
        "needs_label_print": True,
        "slicer_profile": "Prusament PETG @0.4",
        "sample_printed": True,
    }
    assert args[1]["extra"] is fetched["extra"]


def test_set_flag_filament_rejection_surfaces_last_spoolman_error(client):
    """Filament mirror of the rejection contract: update_filament -> None
    surfaces LAST_SPOOLMAN_ERROR in msg + logger.error names the filament."""
    with patch.object(app_module.spoolman_api, "get_filament",
                      return_value={"id": 5, "extra": {}}), \
         patch.object(app_module.spoolman_api, "update_filament", return_value=None), \
         patch.object(app_module.spoolman_api, "LAST_SPOOLMAN_ERROR",
                      "HTTP 422: value is not a valid boolean"), \
         patch.object(app_module.state.logger, "error") as mock_err:
        res = client.post("/api/print_queue/set_flag", json={"id": 5, "type": "filament"})

    assert res.get_json() == {"success": False, "msg": "HTTP 422: value is not a valid boolean"}
    mock_err.assert_called_once()
    logged = mock_err.call_args[0][0]
    assert "filament 5" in logged
    assert "HTTP 422: value is not a valid boolean" in logged


# ---------------------------------------------------------------------------
# /api/print_queue/set_flag — fall-throughs and quirks (pinned AS-IS)
# ---------------------------------------------------------------------------

def test_set_flag_unknown_type_returns_bare_falsy(client):
    """Unknown type falls through to HTTP 200 {'success': False} with NO 'msg'
    key — inv_queue.js turns this into its generic 'Failed to flag' toast.
    # NOTE: pins current behavior; see suspected_bugs (no msg, no 4xx)."""
    with patch.object(app_module.spoolman_api, "get_spool") as mock_gs, \
         patch.object(app_module.spoolman_api, "get_filament") as mock_gf:
        res = client.post("/api/print_queue/set_flag", json={"id": 10, "type": "gizmo"})

    assert res.status_code == 200
    assert res.get_json() == {"success": False}
    assert "msg" not in res.get_json()
    mock_gs.assert_not_called()
    mock_gf.assert_not_called()


def test_set_flag_spool_not_found_returns_bare_falsy(client):
    """get_spool -> None (unknown id) also lands on the bare {'success': False}
    fall-through — no msg, no 404, and update_spool is never attempted.
    # NOTE: pins current behavior; see suspected_bugs."""
    with patch.object(app_module.spoolman_api, "get_spool", return_value=None), \
         patch.object(app_module.spoolman_api, "update_spool") as mock_update:
        res = client.post("/api/print_queue/set_flag", json={"id": 999, "type": "spool"})

    assert res.status_code == 200
    assert res.get_json() == {"success": False}
    mock_update.assert_not_called()


def test_set_flag_missing_id_is_forwarded_as_none_not_4xx(client):
    """There is NO missing-id validation (asymmetric with mark_printed's
    'Missing ID or Type' check): a payload without 'id' calls get_spool(None)
    and — when that returns None — falls through to 200 {'success': False}.
    # NOTE: pins current behavior; see suspected_bugs (None hits the live
    Spoolman lookup in prod, and the client gets no reason string)."""
    with patch.object(app_module.spoolman_api, "get_spool", return_value=None) as mock_get:
        res = client.post("/api/print_queue/set_flag", json={"type": "spool"})

    assert res.status_code == 200
    assert res.get_json() == {"success": False}
    mock_get.assert_called_once_with(None)


def test_set_flag_missing_type_returns_bare_falsy(client):
    """No 'type' in the payload skips both branches -> bare {'success': False}
    at HTTP 200, and neither getter fires.
    # NOTE: pins current behavior; see suspected_bugs."""
    with patch.object(app_module.spoolman_api, "get_spool") as mock_gs, \
         patch.object(app_module.spoolman_api, "get_filament") as mock_gf:
        res = client.post("/api/print_queue/set_flag", json={"id": 10})

    assert res.status_code == 200
    assert res.get_json() == {"success": False}
    mock_gs.assert_not_called()
    mock_gf.assert_not_called()


def test_set_flag_string_id_passed_through_uncoerced(client):
    """Quirk pin: set_flag does NOT int-coerce the id (mark_printed does, and
    rejects non-numeric legacy ids with a dedicated msg). A string id like
    'legacy_foo' is handed to get_spool verbatim.
    # NOTE: pins current behavior; see suspected_bugs (asymmetry with
    mark_printed's legacy-ID rejection)."""
    with patch.object(app_module.spoolman_api, "get_spool", return_value=None) as mock_get:
        res = client.post("/api/print_queue/set_flag",
                          json={"id": "legacy_foo", "type": "spool"})

    assert res.get_json() == {"success": False}
    mock_get.assert_called_once_with("legacy_foo")


def test_set_flag_exception_surfaces_str_of_exception(client):
    """Any exception inside the handler body is caught, logged via
    state.logger.error('Error setting needs_label_print: ...'), and returned
    as HTTP 200 {'success': False, 'msg': str(e)}."""
    with patch.object(app_module.spoolman_api, "get_spool",
                      side_effect=RuntimeError("kaboom")), \
         patch.object(app_module.state.logger, "error") as mock_err:
        res = client.post("/api/print_queue/set_flag", json={"id": 10, "type": "spool"})

    assert res.status_code == 200
    assert res.get_json() == {"success": False, "msg": "kaboom"}
    mock_err.assert_called_once()
    assert "Error setting needs_label_print" in mock_err.call_args[0][0]


def test_set_flag_malformed_json_is_framework_400(client):
    """`data = request.json` runs BEFORE the handler's try block, so a
    malformed JSON body never reaches the {'success': False, 'msg': ...}
    contract — Flask answers with its own 400. A carve that switches to
    request.get_json(silent=True) (the api_quickswap idiom) would flip this
    to 200; that must be a conscious decision.
    # NOTE: pins current behavior; see suspected_bugs."""
    res = client.post("/api/print_queue/set_flag",
                      data="{not json", content_type="application/json")
    assert res.status_code == 400


def test_set_flag_non_json_content_type_is_framework_415(client):
    """Same strict-request.json pin for the wrong content type: Flask 3.x
    raises UnsupportedMediaType -> HTTP 415, bypassing the endpoint's JSON
    error contract entirely.
    # NOTE: pins current behavior; see suspected_bugs."""
    res = client.post("/api/print_queue/set_flag",
                      data="id=10", content_type="text/plain")
    assert res.status_code == 415


# ---------------------------------------------------------------------------
# /api/print_queue/mark_printed — filament branch (spool happy path + legacy
# rejection are already pinned in tests/test_print_queue.py; not duplicated)
# ---------------------------------------------------------------------------

def test_mark_printed_filament_lowers_flag_with_full_extra(client):
    """Filament happy path: get_filament -> the FETCHED extra dict has
    needs_label_print lowered to False and is passed whole to update_filament
    (siblings like sample_printed preserved in the sent dict). The string id
    '5' is int-coerced before the lookup — the legacy-ID gate shared with the
    spool branch."""
    fetched = {
        "id": 5,
        "extra": {"needs_label_print": True, "sample_printed": True},
    }
    with patch.object(app_module.spoolman_api, "get_filament", return_value=fetched) as mock_get, \
         patch.object(app_module.spoolman_api, "update_filament", return_value={"id": 5}) as mock_update:
        res = client.post("/api/print_queue/mark_printed",
                          json={"id": "5", "type": "filament"})

    assert res.status_code == 200
    assert res.get_json() == {"success": True}
    # int-coercion pin: "5" (string) arrives at get_filament as int 5.
    mock_get.assert_called_once_with(5)

    args, _ = mock_update.call_args
    assert args[0] == 5
    assert set(args[1].keys()) == {"extra"}
    assert args[1]["extra"] == {"needs_label_print": False, "sample_printed": True}
    assert args[1]["extra"] is fetched["extra"]


def test_mark_printed_filament_rejection_surfaces_last_spoolman_error(client):
    """update_filament -> None surfaces LAST_SPOOLMAN_ERROR in the response
    msg and logs an error naming the filament — the exact contract the
    CLAUDE.md write-surface table cites for app.py mark_printed (filament)."""
    with patch.object(app_module.spoolman_api, "get_filament",
                      return_value={"id": 5, "extra": {"needs_label_print": True}}), \
         patch.object(app_module.spoolman_api, "update_filament", return_value=None), \
         patch.object(app_module.spoolman_api, "LAST_SPOOLMAN_ERROR", "HTTP 400: boom"), \
         patch.object(app_module.state.logger, "error") as mock_err:
        res = client.post("/api/print_queue/mark_printed",
                          json={"id": 5, "type": "filament"})

    assert res.status_code == 200
    assert res.get_json() == {"success": False, "msg": "HTTP 400: boom"}
    mock_err.assert_called_once()
    logged = mock_err.call_args[0][0]
    assert "mark_printed" in logged
    assert "filament 5" in logged
    assert "HTTP 400: boom" in logged


def test_mark_printed_filament_rejection_fallback_msg_when_error_unset(client):
    """LAST_SPOOLMAN_ERROR unset at rejection time -> the fallback literal
    'Spoolman rejected the update'."""
    with patch.object(app_module.spoolman_api, "get_filament",
                      return_value={"id": 5, "extra": {}}), \
         patch.object(app_module.spoolman_api, "update_filament", return_value=None), \
         patch.object(app_module.spoolman_api, "LAST_SPOOLMAN_ERROR", None), \
         patch.object(app_module.state.logger, "error"):
        res = client.post("/api/print_queue/mark_printed",
                          json={"id": 5, "type": "filament"})

    assert res.get_json() == {"success": False, "msg": "Spoolman rejected the update"}


def test_mark_printed_filament_not_found_generic_msg(client):
    """get_filament -> None falls through to the shared
    'Item not found or update failed' msg at HTTP 200; no update attempted."""
    with patch.object(app_module.spoolman_api, "get_filament", return_value=None), \
         patch.object(app_module.spoolman_api, "update_filament") as mock_update:
        res = client.post("/api/print_queue/mark_printed",
                          json={"id": 404, "type": "filament"})

    assert res.status_code == 200
    assert res.get_json() == {"success": False, "msg": "Item not found or update failed"}
    mock_update.assert_not_called()


@pytest.mark.parametrize("payload", [
    {"type": "filament"},          # no id
    {"id": 5},                     # no type
    {"id": 0, "type": "filament"}, # falsy id — `if not item_id` treats 0 as missing
])
def test_mark_printed_missing_id_or_type(client, payload):
    """Missing (or falsy — id 0 counts) id/type short-circuits to
    'Missing ID or Type' before any Spoolman call.
    # NOTE: pins current behavior; see suspected_bugs (id=0 is swallowed by
    the truthiness check — harmless today since Spoolman ids start at 1)."""
    with patch.object(app_module.spoolman_api, "get_filament") as mock_gf, \
         patch.object(app_module.spoolman_api, "get_spool") as mock_gs:
        res = client.post("/api/print_queue/mark_printed", json=payload)

    assert res.status_code == 200
    assert res.get_json() == {"success": False, "msg": "Missing ID or Type"}
    mock_gf.assert_not_called()
    mock_gs.assert_not_called()


def test_mark_printed_unknown_type_generic_msg(client):
    """An unknown type skips both branches and lands on the same generic
    'Item not found or update failed' fall-through (no dedicated wording).
    # NOTE: pins current behavior; see suspected_bugs."""
    with patch.object(app_module.spoolman_api, "get_spool") as mock_gs, \
         patch.object(app_module.spoolman_api, "get_filament") as mock_gf:
        res = client.post("/api/print_queue/mark_printed",
                          json={"id": 5, "type": "gizmo"})

    assert res.get_json() == {"success": False, "msg": "Item not found or update failed"}
    mock_gs.assert_not_called()
    mock_gf.assert_not_called()


def test_mark_printed_non_intable_id_type_returns_json_error(client):
    """27.3 FIX — the legacy-ID gate now catches TypeError as well as
    ValueError, so a JSON-array id (which raises TypeError from int()) returns
    the JSON error contract at HTTP 200 instead of escaping the handler as an
    unhandled 500."""
    res = client.post("/api/print_queue/mark_printed",
                      json={"id": ["nested"], "type": "spool"})
    assert res.status_code == 200
    assert res.get_json() == {
        "success": False,
        "msg": "Legacy IDs cannot be manually marked printed. Please scan.",
    }
