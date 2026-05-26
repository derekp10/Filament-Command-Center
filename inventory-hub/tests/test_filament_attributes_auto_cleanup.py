"""Auto-startup cleanup of filament_attributes choice dropdown.

Derek 2026-05-19: "Can this just run on its own first run and clean
things up? I don't like running things on prod myself."

`spoolman_api.ensure_filament_attributes_cleaned()` is called from
app startup right after `ensure_required_extras()`. These tests
mock the Spoolman HTTP layer to cover:

- Idempotent path (nothing to do → early return, no writes).
- First-boot delete path (confirmed-safe entries get removed; filament
  PATCHes happen with cleaned values).
- FLAG_CHOICES safety net (in-use flagged choice stays; zero-usage
  flagged choice gets auto-promoted to delete).
- Transient state guard (Spoolman returns 0 filaments → skip).
- Network failure guard (no exception bubbles up).
"""
from __future__ import annotations

import json as _json
import os
import sys
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import spoolman_api  # noqa: E402


def _mock_resp(ok=True, status=200, payload=None):
    m = MagicMock()
    m.ok = ok
    m.status_code = status
    m.text = ""
    m.json.return_value = payload if payload is not None else {}
    return m


def _field_def(choices):
    return {
        "entity_type": "filament",
        "field_type": "choice",
        "key": "filament_attributes",
        "multi_choice": True,
        "name": "Filament Attributes",
        "choices": list(choices),
    }


def _filament(fid, name, attrs):
    return {
        "id": fid,
        "name": name,
        "extra": {"filament_attributes": _json.dumps(attrs)},
    }


def _stub_calls(field_choices, filaments, delete_status=200, post_status=200, patch_status=200):
    """Build a (calls, dispatch) pair we can wire into mocked requests.

    The dispatch fakes both the read endpoints and the write endpoints in
    order; calls captures every request the function makes so the test
    can assert on it."""
    calls = []

    def fake_get(url, **_kw):
        calls.append(("GET", url))
        if "/api/v1/field/filament" in url:
            return _mock_resp(payload=[_field_def(field_choices)])
        if "/api/v1/filament" in url:
            return _mock_resp(payload=list(filaments))
        return _mock_resp(ok=False, status=404)

    def fake_delete(url, **_kw):
        calls.append(("DELETE", url))
        return _mock_resp(ok=delete_status == 200, status=delete_status)

    def fake_post(url, **_kw):
        calls.append(("POST", url, _kw.get("json")))
        return _mock_resp(ok=post_status == 200, status=post_status)

    def fake_patch(url, **_kw):
        calls.append(("PATCH", url, _kw.get("json")))
        return _mock_resp(ok=patch_status == 200, status=patch_status)

    return calls, fake_get, fake_delete, fake_post, fake_patch


@pytest.fixture(autouse=True)
def _silence_state_logging(monkeypatch):
    """Don't pollute stdout / hub.log during tests."""
    monkeypatch.setattr(spoolman_api.state, "add_log_entry", lambda *a, **k: None)
    monkeypatch.setattr(spoolman_api.state.logger, "info", lambda *a, **k: None)
    monkeypatch.setattr(spoolman_api.state.logger, "warning", lambda *a, **k: None)
    monkeypatch.setattr(spoolman_api.state.logger, "error", lambda *a, **k: None)


def test_no_targets_in_field_is_idempotent_noop(monkeypatch):
    """When none of the DELETE / FLAG choices are in the current field,
    the function does NOT touch Spoolman beyond the initial GETs."""
    clean_choices = ["+", "Basic", "Silk", "Matte"]  # none of our targets
    calls, fake_get, fake_delete, fake_post, fake_patch = _stub_calls(
        clean_choices, []
    )
    monkeypatch.setattr(spoolman_api.requests, "get", fake_get)
    monkeypatch.setattr(spoolman_api.requests, "delete", fake_delete)
    monkeypatch.setattr(spoolman_api.requests, "post", fake_post)
    monkeypatch.setattr(spoolman_api.requests, "patch", fake_patch)
    monkeypatch.setattr(
        spoolman_api.config_loader, "get_api_urls",
        lambda: ("http://spoolman", "http://filabridge"),
    )

    spoolman_api.ensure_filament_attributes_cleaned()

    # Should only have read the field def; no list-filaments, no writes.
    methods = [c[0] for c in calls]
    assert methods == ["GET"], f"Expected one GET only; got {calls}"


def test_first_boot_deletes_confirmed_safe_choices(monkeypatch):
    """All five confirmed-safe DELETE_CHOICES present → field gets
    rebuilt without them; one filament that used 'Wood' gets PATCHed
    with the cleaned value."""
    dirty = ["+", "Basic", "Carbon-Fiber", "Tran", "Transparent; High-Speed",
             "Wood", "Wood Filled", "F"]
    filaments = [
        _filament(1, "Wood Filament", ["Wood", "Basic"]),
        _filament(2, "Clean PLA", ["Basic"]),
    ]
    calls, fake_get, fake_delete, fake_post, fake_patch = _stub_calls(dirty, filaments)
    monkeypatch.setattr(spoolman_api.requests, "get", fake_get)
    monkeypatch.setattr(spoolman_api.requests, "delete", fake_delete)
    monkeypatch.setattr(spoolman_api.requests, "post", fake_post)
    monkeypatch.setattr(spoolman_api.requests, "patch", fake_patch)
    monkeypatch.setattr(
        spoolman_api.config_loader, "get_api_urls",
        lambda: ("http://spoolman", "http://filabridge"),
    )

    spoolman_api.ensure_filament_attributes_cleaned()

    methods = [c[0] for c in calls]
    assert "DELETE" in methods, f"Expected schema DELETE; got {methods}"
    assert "POST" in methods, f"Expected schema POST; got {methods}"

    # POST'd choice list excludes every DELETE_CHOICES entry.
    post_call = next(c for c in calls if c[0] == "POST")
    posted = set(post_call[2]["choices"])
    assert "Carbon-Fiber" not in posted
    assert "Tran" not in posted
    assert "Transparent; High-Speed" not in posted
    assert "Wood" not in posted
    assert "F" not in posted
    # Survivors preserved.
    assert "+" in posted
    assert "Basic" in posted
    assert "Wood Filled" in posted

    # Filament 1 had "Wood" → PATCHed to ["Basic"]. Filament 2 unchanged
    # by content but still PATCHed (idempotent restore).
    patch_calls = [c for c in calls if c[0] == "PATCH"]
    assert len(patch_calls) == 2
    by_url = {c[1]: c[2] for c in patch_calls}
    f1_payload = next(v for k, v in by_url.items() if k.endswith("/1"))
    assert _json.loads(f1_payload["extra"]["filament_attributes"]) == ["Basic"]


def test_flag_choice_in_use_is_kept(monkeypatch):
    """A FLAG_CHOICES entry that's actually in use by any filament
    must survive the cleanup. FLAG_CHOICES was drained to empty on
    2026-05-20 (Derek footgun avoidance), so this test pokes a
    non-empty set into place to keep the algorithm under coverage in
    case future maintenance flags choices again."""
    monkeypatch.setattr(
        spoolman_api, "FILAMENT_ATTRIBUTES_FLAG_CHOICES",
        frozenset({"For Infill", "Matte Pro"}),
    )
    dirty = ["+", "Basic", "For Infill", "Wood"]
    filaments = [
        _filament(10, "Prototype Filler", ["For Infill"]),  # uses the flagged one
    ]
    calls, fake_get, fake_delete, fake_post, fake_patch = _stub_calls(dirty, filaments)
    monkeypatch.setattr(spoolman_api.requests, "get", fake_get)
    monkeypatch.setattr(spoolman_api.requests, "delete", fake_delete)
    monkeypatch.setattr(spoolman_api.requests, "post", fake_post)
    monkeypatch.setattr(spoolman_api.requests, "patch", fake_patch)
    monkeypatch.setattr(
        spoolman_api.config_loader, "get_api_urls",
        lambda: ("http://spoolman", "http://filabridge"),
    )

    spoolman_api.ensure_filament_attributes_cleaned()

    post_call = next(c for c in calls if c[0] == "POST")
    posted = set(post_call[2]["choices"])
    # "For Infill" is in use → must remain. "Wood" still gets removed.
    assert "For Infill" in posted, "Flagged-and-in-use choice should be kept"
    assert "Wood" not in posted

    # The using filament's value must NOT have "For Infill" stripped.
    patch_call = next(c for c in calls if c[0] == "PATCH")
    restored = _json.loads(patch_call[2]["extra"]["filament_attributes"])
    assert "For Infill" in restored


def test_flag_choice_with_zero_usage_is_promoted_to_delete(monkeypatch):
    """When NO filament uses a FLAG_CHOICES entry, it gets auto-promoted
    into the delete list. Algorithm-level coverage only — production
    FLAG_CHOICES is empty as of 2026-05-20, so this path never fires
    on prod boots until/unless someone adds a choice to the set."""
    monkeypatch.setattr(
        spoolman_api, "FILAMENT_ATTRIBUTES_FLAG_CHOICES",
        frozenset({"For Infill", "Matte Pro"}),
    )
    dirty = ["+", "Basic", "For Infill", "Matte Pro"]
    filaments = [
        _filament(20, "Basic PLA", ["Basic"]),  # uses neither flagged choice
    ]
    calls, fake_get, fake_delete, fake_post, fake_patch = _stub_calls(dirty, filaments)
    monkeypatch.setattr(spoolman_api.requests, "get", fake_get)
    monkeypatch.setattr(spoolman_api.requests, "delete", fake_delete)
    monkeypatch.setattr(spoolman_api.requests, "post", fake_post)
    monkeypatch.setattr(spoolman_api.requests, "patch", fake_patch)
    monkeypatch.setattr(
        spoolman_api.config_loader, "get_api_urls",
        lambda: ("http://spoolman", "http://filabridge"),
    )

    spoolman_api.ensure_filament_attributes_cleaned()

    post_call = next(c for c in calls if c[0] == "POST")
    posted = set(post_call[2]["choices"])
    # Both flagged choices auto-promoted because zero usage.
    assert "For Infill" not in posted
    assert "Matte Pro" not in posted


def test_zero_filaments_returned_skips_cleanup(monkeypatch):
    """Transient state guard — if Spoolman has the field but returns
    zero filaments, treat as "ask me later" rather than "everything is
    unused, nuke the flagged choices". Avoids a transient-network
    blip from quietly stripping data."""
    dirty = ["+", "Wood", "For Infill"]  # at least one target present
    filaments = []  # but no filaments returned
    calls, fake_get, fake_delete, fake_post, fake_patch = _stub_calls(dirty, filaments)
    monkeypatch.setattr(spoolman_api.requests, "get", fake_get)
    monkeypatch.setattr(spoolman_api.requests, "delete", fake_delete)
    monkeypatch.setattr(spoolman_api.requests, "post", fake_post)
    monkeypatch.setattr(spoolman_api.requests, "patch", fake_patch)
    monkeypatch.setattr(
        spoolman_api.config_loader, "get_api_urls",
        lambda: ("http://spoolman", "http://filabridge"),
    )

    spoolman_api.ensure_filament_attributes_cleaned()

    methods = [c[0] for c in calls]
    # Two GETs (field def + filament list) but no DELETE/POST/PATCH.
    assert methods == ["GET", "GET"], f"Expected GET-only path; got {calls}"


def test_network_error_does_not_propagate(monkeypatch):
    """Connection error should be swallowed (logged WARNING) so it
    can't crash app startup."""
    def boom(*_a, **_kw):
        raise spoolman_api.requests.RequestException("simulated unreachable")
    monkeypatch.setattr(spoolman_api.requests, "get", boom)
    monkeypatch.setattr(
        spoolman_api.config_loader, "get_api_urls",
        lambda: ("http://spoolman", "http://filabridge"),
    )
    # Must not raise.
    spoolman_api.ensure_filament_attributes_cleaned()


def test_post_failure_logs_and_returns(monkeypatch):
    """If the schema POST that recreates the field fails AFTER the
    DELETE, we log an error and return — we don't crash, but the
    operator needs to know the field is currently MISSING."""
    dirty = ["+", "Wood"]
    filaments = [_filament(30, "X", ["Wood"])]
    calls, fake_get, fake_delete, _fake_post, fake_patch = _stub_calls(dirty, filaments)

    def fake_post(url, **_kw):
        calls.append(("POST", url, _kw.get("json")))
        return _mock_resp(ok=False, status=500)

    monkeypatch.setattr(spoolman_api.requests, "get", fake_get)
    monkeypatch.setattr(spoolman_api.requests, "delete", fake_delete)
    monkeypatch.setattr(spoolman_api.requests, "post", fake_post)
    monkeypatch.setattr(spoolman_api.requests, "patch", fake_patch)
    monkeypatch.setattr(
        spoolman_api.config_loader, "get_api_urls",
        lambda: ("http://spoolman", "http://filabridge"),
    )

    # No exception bubbles out.
    spoolman_api.ensure_filament_attributes_cleaned()

    methods = [c[0] for c in calls]
    # We tried POST (it failed) → no PATCH attempts after.
    assert "POST" in methods
    assert "PATCH" not in methods
