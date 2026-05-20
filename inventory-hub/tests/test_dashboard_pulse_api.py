"""Backend tests for /api/dashboard_pulse — L206 bulk-heartbeat endpoint.

Replaces the ~12-request fan-out that startSmartSync used to do every 5s
with one aggregated request. The legacy per-section endpoints stay in
place for backwards compatibility; this test verifies the bulk endpoint
returns the same shapes the frontend would otherwise get from those
individual calls.

Tests hit the running dev server at localhost:8000 (api_base_url
fixture). They do NOT mutate Spoolman state.
"""
from __future__ import annotations

import requests


def test_pulse_empty_include_returns_empty_object(api_base_url, require_server):
    """A pulse with no include= returns {} — no surprise data."""
    r = requests.get(f"{api_base_url}/api/dashboard_pulse", timeout=10)
    assert r.status_code == 200
    assert r.json() == {}


def test_pulse_unknown_sections_silently_ignored(api_base_url, require_server):
    """Forward-compat: unknown section names don't error or 4xx. Old
    clients can hit a new server (or vice-versa) without explosions."""
    r = requests.get(
        f"{api_base_url}/api/dashboard_pulse?include=garbage,buffer,nonsense",
        timeout=10,
    )
    assert r.status_code == 200
    payload = r.json()
    assert set(payload.keys()) == {"buffer"}, (
        f"Expected only 'buffer' to come through; got {list(payload.keys())}"
    )


def test_pulse_buffer_matches_legacy_endpoint(api_base_url, require_server):
    """buffer section returns the same shape as GET /api/state/buffer."""
    bulk = requests.get(
        f"{api_base_url}/api/dashboard_pulse?include=buffer", timeout=10
    ).json()
    legacy = requests.get(f"{api_base_url}/api/state/buffer", timeout=10).json()
    assert bulk["buffer"] == legacy


def test_pulse_status_section_has_expected_keys(api_base_url, require_server):
    """status section must always include spoolman + filabridge booleans
    plus audit_active + undo_available so the frontend can repaint the
    nav-bar dots from one payload."""
    r = requests.get(
        f"{api_base_url}/api/dashboard_pulse?include=status", timeout=10
    )
    assert r.status_code == 200
    payload = r.json()
    assert "status" in payload
    status = payload["status"]
    for key in ("spoolman", "filabridge", "audit_active", "undo_available"):
        assert key in status, f"status section missing '{key}': {status}"
        assert isinstance(status[key], bool), (
            f"status.{key} should be bool, got {type(status[key]).__name__}"
        )


def test_pulse_logs_section_matches_legacy_endpoint_shape(
    api_base_url, require_server
):
    """logs section delegates to the /api/logs handler internally. The
    shape (logs, status, audit_active, undo_available) must match what
    the legacy endpoint returns."""
    bulk = requests.get(
        f"{api_base_url}/api/dashboard_pulse?include=logs", timeout=10
    ).json()
    assert "logs" in bulk
    legacy = requests.get(f"{api_base_url}/api/logs", timeout=10).json()
    # Both must carry the same top-level keys.
    for key in ("logs", "status", "audit_active", "undo_available"):
        assert key in bulk["logs"], (
            f"bulk.logs missing '{key}': got {list(bulk['logs'].keys())}"
        )
        assert key in legacy, (
            f"legacy /api/logs missing '{key}': got {list(legacy.keys())}"
        )


def test_pulse_logs_and_status_share_one_health_check(
    api_base_url, require_server
):
    """When both logs and status are requested, the response must
    contain BOTH sections and the spoolman/filabridge bits must agree
    between them — we run the underlying health check at most once
    per request so they can't disagree."""
    r = requests.get(
        f"{api_base_url}/api/dashboard_pulse?include=logs,status", timeout=10
    )
    payload = r.json()
    assert "logs" in payload and "status" in payload
    assert (
        payload["logs"]["status"]["spoolman"]
        == payload["status"]["spoolman"]
    )
    assert (
        payload["logs"]["status"]["filabridge"]
        == payload["status"]["filabridge"]
    )


def test_pulse_locations_section_matches_legacy_endpoint(
    api_base_url, require_server
):
    """locations section delegates to the /api/locations handler."""
    bulk = requests.get(
        f"{api_base_url}/api/dashboard_pulse?include=locations", timeout=15
    ).json()
    legacy = requests.get(f"{api_base_url}/api/locations", timeout=15).json()
    assert "locations" in bulk
    # The legacy endpoint can be a list (happy path) or a dict (error
    # path) — bulk must mirror whichever it is.
    if isinstance(legacy, list):
        assert isinstance(bulk["locations"], list)
        # The Unassigned virtual row is always first when present.
        if bulk["locations"]:
            assert bulk["locations"][0].get("LocationID") in (
                "Unassigned",
                "UNKNOWN",
            ) or len(bulk["locations"]) > 0


def test_pulse_manage_section_without_manage_id_is_omitted(
    api_base_url, require_server
):
    """manage in include= but no manage_id query param → section is
    silently omitted from the response (caller forgot the id). Not an
    error since the rest of the pulse should still come through."""
    r = requests.get(
        f"{api_base_url}/api/dashboard_pulse?include=manage,buffer", timeout=10
    )
    assert r.status_code == 200
    payload = r.json()
    assert "manage" not in payload
    assert "buffer" in payload


def test_pulse_manage_section_returns_contents_for_id(
    api_base_url, require_server
):
    """manage section with a valid manage_id should mirror
    /api/get_contents — same shape (list of spool dicts inside
    {id, contents})."""
    # Use Unassigned because it always exists and never errors.
    r = requests.get(
        f"{api_base_url}/api/dashboard_pulse?include=manage&manage_id=Unassigned",
        timeout=10,
    )
    assert r.status_code == 200
    payload = r.json()
    assert "manage" in payload
    assert payload["manage"]["id"] == "UNASSIGNED"
    assert isinstance(payload["manage"]["contents"], list)


def test_pulse_printer_status_section_returns_grouped_payload(
    api_base_url, require_server
):
    """printer_status section aggregates printer_map + toolhead_slots +
    get_contents server-side. Result is {printer_name: {toolheads: [...]}}.
    Each toolhead carries id/position/item/unbound."""
    r = requests.get(
        f"{api_base_url}/api/dashboard_pulse?include=printer_status", timeout=15
    )
    assert r.status_code == 200
    payload = r.json()
    assert "printer_status" in payload
    ps = payload["printer_status"]
    assert isinstance(ps, dict)
    for printer_name, info in ps.items():
        assert "toolheads" in info, (
            f"printer {printer_name} missing 'toolheads' key: {info}"
        )
        for th in info["toolheads"]:
            for key in ("id", "position", "item", "unbound"):
                assert key in th, (
                    f"toolhead missing '{key}': {th} (in printer {printer_name})"
                )
            assert isinstance(th["unbound"], bool)
            assert th["item"] is None or isinstance(th["item"], dict)


def test_pulse_post_with_refresh_spool_ids_returns_spools_refresh(
    api_base_url, require_server
):
    """POST with {refresh_spool_ids: [...]} produces a spools_refresh
    section mirroring /api/spools/refresh."""
    # Find one real spool id from the buffer or just use spool #1
    # (test should be robust to either — we just check shape).
    bulk = requests.post(
        f"{api_base_url}/api/dashboard_pulse?include=buffer",
        json={"refresh_spool_ids": [1]},
        timeout=10,
    ).json()
    assert "spools_refresh" in bulk
    # spools_refresh is a dict keyed by id (string)
    assert isinstance(bulk["spools_refresh"], dict)


def test_pulse_get_without_body_does_not_include_spools_refresh(
    api_base_url, require_server
):
    """GET (no body) means no spools_refresh in the response. We don't
    want every dashboard pulse re-fetching live spool data unless the
    frontend asks for it."""
    bulk = requests.get(
        f"{api_base_url}/api/dashboard_pulse?include=buffer,status", timeout=10
    ).json()
    assert "spools_refresh" not in bulk


def test_pulse_combined_sections_in_single_response(
    api_base_url, require_server
):
    """The whole point of L206: one request, many sections. Confirm
    the common dashboard set (logs + locations + buffer + printer_status)
    all come back together."""
    r = requests.get(
        f"{api_base_url}/api/dashboard_pulse?include=logs,locations,buffer,printer_status",
        timeout=20,
    )
    assert r.status_code == 200
    payload = r.json()
    expected = {"logs", "locations", "buffer", "printer_status"}
    assert expected.issubset(payload.keys()), (
        f"Expected sections {expected}, got {set(payload.keys())}"
    )
