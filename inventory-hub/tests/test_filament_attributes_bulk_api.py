"""L58 — Filament Attributes manager endpoints.

Integration tests against the running dev container. Each test
snapshots the target filament's attribute list and restores it on
teardown so the real Spoolman dev DB never drifts.
"""
from __future__ import annotations

import json

import pytest
import requests


def _pick_target(api_base_url: str):
    """Pull a deterministic target filament from the report endpoint.
    Picks the first non-archived filament so the test runs the same
    against any seeded dev DB."""
    r = requests.get(f"{api_base_url}/api/filament_attributes/report", timeout=10)
    assert r.ok, r.text
    body = r.json()
    assert body.get("success"), body
    fil = next((f for f in body["filaments"] if not f["archived"]), None)
    assert fil is not None, "expected at least one non-archived filament in dev DB"
    return fil, body.get("choices", [])


def _snapshot_attrs(api_base_url: str, fid: int):
    r = requests.get(f"{api_base_url}/api/filaments/{fid}", timeout=5)
    if not r.ok:
        # fall back to the report — same shape, just slower
        r2 = requests.get(f"{api_base_url}/api/filament_attributes/report", timeout=10)
        body = r2.json()
        fil = next((f for f in body["filaments"] if f["id"] == fid), None)
        assert fil is not None
        return list(fil["attributes"])
    body = r.json() or {}
    # /api/filaments/<id> returns {success: true, data: {...filament...}}
    fil = body.get("data") if isinstance(body.get("data"), dict) else body
    extras = (fil or {}).get("extra") or {}
    raw = extras.get("filament_attributes")
    if raw is None or raw == "":
        return []
    if isinstance(raw, list):
        return [str(x) for x in raw]
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return [str(x) for x in parsed]
    except Exception:
        pass
    return [str(raw)]


def _restore(api_base_url: str, fid: int, original):
    """Restore the filament's attribute list to its original snapshot.
    Used in test teardown so the dev DB is never left drifted."""
    requests.post(
        f"{api_base_url}/api/update_filament",
        json={"id": fid, "field": "extra.filament_attributes",
              "value": json.dumps(original)},
        timeout=10,
    )


@pytest.mark.usefixtures("require_server")
def test_report_shape(api_base_url):
    """Report returns choices, filaments, counts in the documented shape."""
    r = requests.get(f"{api_base_url}/api/filament_attributes/report", timeout=10)
    assert r.ok, r.text
    body = r.json()
    assert body.get("success") is True
    assert isinstance(body.get("choices"), list)
    assert isinstance(body.get("filaments"), list)
    assert isinstance(body.get("counts"), dict)
    # counts keys must be a subset of choices.
    extra_keys = set(body["counts"].keys()) - set(body["choices"])
    assert not extra_keys, f"counts has keys not in choices: {extra_keys}"
    # Every filament entry has the documented keys.
    if body["filaments"]:
        f = body["filaments"][0]
        for key in ("id", "name", "material", "vendor", "color_hex", "archived", "attributes"):
            assert key in f, f"filament entry missing key: {key}"


@pytest.mark.usefixtures("require_server")
def test_bulk_set_add_then_remove(api_base_url):
    """Bulk-add a choice, verify it lands, then bulk-remove and verify
    the list is back to the original."""
    target, choices = _pick_target(api_base_url)
    fid = target["id"]
    original = _snapshot_attrs(api_base_url, fid)
    # Pick a choice that the filament does NOT currently have so add is
    # a real change, not a no-op. "Basic" is almost always in the dev
    # choice set; fall back to the first available choice if not.
    candidate = next((c for c in choices if c not in original), None)
    assert candidate, "no candidate choice available — every choice already on target"

    try:
        r = requests.post(
            f"{api_base_url}/api/filament_attributes/bulk_set",
            json={"filament_ids": [fid], "add": [candidate]},
            timeout=10,
        )
        assert r.ok, r.text
        body = r.json()
        assert body.get("success") is True, body
        assert body.get("updated") == 1, body
        assert body.get("unchanged") == 0
        assert not body.get("errors"), body["errors"]
        after_add = _snapshot_attrs(api_base_url, fid)
        assert candidate in after_add, after_add

        # Idempotent re-add → unchanged.
        r2 = requests.post(
            f"{api_base_url}/api/filament_attributes/bulk_set",
            json={"filament_ids": [fid], "add": [candidate]},
            timeout=10,
        )
        body2 = r2.json()
        assert body2.get("updated") == 0
        assert body2.get("unchanged") == 1

        # Remove brings it back out.
        r3 = requests.post(
            f"{api_base_url}/api/filament_attributes/bulk_set",
            json={"filament_ids": [fid], "remove": [candidate]},
            timeout=10,
        )
        body3 = r3.json()
        assert body3.get("updated") == 1
        after_remove = _snapshot_attrs(api_base_url, fid)
        assert candidate not in after_remove
        # And we're back to where we started.
        assert sorted(after_remove) == sorted(original)
    finally:
        _restore(api_base_url, fid, original)


@pytest.mark.usefixtures("require_server")
def test_bulk_set_validates_payload(api_base_url):
    """Empty filament_ids or empty add+remove → 400 with a useful message."""
    r1 = requests.post(
        f"{api_base_url}/api/filament_attributes/bulk_set",
        json={"filament_ids": [], "add": ["x"]},
        timeout=5,
    )
    assert r1.status_code == 400
    assert "filament_ids" in r1.json().get("msg", "").lower()

    target, _ = _pick_target(api_base_url)
    r2 = requests.post(
        f"{api_base_url}/api/filament_attributes/bulk_set",
        json={"filament_ids": [target["id"]]},
        timeout=5,
    )
    assert r2.status_code == 400


@pytest.mark.usefixtures("require_server")
def test_add_choice_then_remove_unused_round_trips(api_base_url):
    """Schema-level add + remove on an unused test choice — verifies the
    DELETE+POST recreate path lands the new choices array without
    corrupting siblings. Test choice name is deliberately distinctive
    so a leftover from a crashed test is easy to spot + manually clean."""
    test_choice = "L58_TEST_unused_choice"
    # Be safe: if a prior run left it, remove first.
    r0 = requests.get(f"{api_base_url}/api/filament_attributes/report", timeout=10).json()
    if test_choice in r0.get("choices", []):
        requests.post(
            f"{api_base_url}/api/filament_attributes/remove_choice",
            json={"choice": test_choice, "force": True}, timeout=20,
        )
    try:
        r_add = requests.post(
            f"{api_base_url}/api/filament_attributes/add_choice",
            json={"choice": test_choice}, timeout=10,
        )
        assert r_add.ok and r_add.json().get("success"), r_add.text
        report = requests.get(f"{api_base_url}/api/filament_attributes/report", timeout=10).json()
        assert test_choice in report["choices"]
        assert report["counts"].get(test_choice, 0) == 0

        # Unused choice → remove should succeed without needing force.
        r_rm = requests.post(
            f"{api_base_url}/api/filament_attributes/remove_choice",
            json={"choice": test_choice}, timeout=20,
        )
        body = r_rm.json()
        assert body.get("success") is True, body
        assert body.get("stripped") == 0
        # Sanity: every filament that previously had attrs still has them.
        report_after = requests.get(f"{api_base_url}/api/filament_attributes/report", timeout=10).json()
        assert test_choice not in report_after["choices"]
        # Total non-empty attribute lists should match (the test choice
        # was unused, so stripping it cannot have changed any count).
        for c, n in report["counts"].items():
            if c == test_choice:
                continue
            assert report_after["counts"].get(c, 0) == n, (
                f"sibling choice {c!r} count drifted: {n} → {report_after['counts'].get(c, 0)}"
            )
    finally:
        # Make absolutely sure the test choice is gone even on failure.
        rr = requests.get(f"{api_base_url}/api/filament_attributes/report", timeout=10).json()
        if test_choice in rr.get("choices", []):
            requests.post(
                f"{api_base_url}/api/filament_attributes/remove_choice",
                json={"choice": test_choice, "force": True}, timeout=20,
            )


@pytest.mark.usefixtures("require_server")
def test_remove_choice_in_use_requires_force(api_base_url):
    """Remove without `force` on an in-use choice → 200 with
    success=false, needs_confirm=true, usage_count>0. The schema is
    NOT modified — the next report still shows the choice."""
    test_choice = "L58_TEST_in_use_choice"
    target, _ = _pick_target(api_base_url)
    fid = target["id"]
    original = _snapshot_attrs(api_base_url, fid)
    # Add the choice + tag the target filament with it.
    requests.post(
        f"{api_base_url}/api/filament_attributes/add_choice",
        json={"choice": test_choice}, timeout=10,
    )
    requests.post(
        f"{api_base_url}/api/filament_attributes/bulk_set",
        json={"filament_ids": [fid], "add": [test_choice]}, timeout=10,
    )
    try:
        r = requests.post(
            f"{api_base_url}/api/filament_attributes/remove_choice",
            json={"choice": test_choice}, timeout=20,
        )
        body = r.json()
        assert body.get("success") is False
        assert body.get("needs_confirm") is True
        assert body.get("usage_count") == 1
        # Choice still present in the schema.
        rep = requests.get(f"{api_base_url}/api/filament_attributes/report", timeout=10).json()
        assert test_choice in rep["choices"]
        assert test_choice in _snapshot_attrs(api_base_url, fid)

        # Re-send with force → succeeds, strips the tag, removes the choice.
        r2 = requests.post(
            f"{api_base_url}/api/filament_attributes/remove_choice",
            json={"choice": test_choice, "force": True}, timeout=20,
        )
        body2 = r2.json()
        assert body2.get("success") is True
        assert body2.get("stripped") == 1
        rep2 = requests.get(f"{api_base_url}/api/filament_attributes/report", timeout=10).json()
        assert test_choice not in rep2["choices"]
        assert test_choice not in _snapshot_attrs(api_base_url, fid)
    finally:
        _restore(api_base_url, fid, original)
        rr = requests.get(f"{api_base_url}/api/filament_attributes/report", timeout=10).json()
        if test_choice in rr.get("choices", []):
            requests.post(
                f"{api_base_url}/api/filament_attributes/remove_choice",
                json={"choice": test_choice, "force": True}, timeout=20,
            )


@pytest.mark.usefixtures("require_server")
def test_add_choice_validation(api_base_url):
    """add_choice rejects empty / oversized choice names."""
    r1 = requests.post(
        f"{api_base_url}/api/filament_attributes/add_choice",
        json={"choice": "   "}, timeout=5,
    )
    assert r1.status_code == 400
    r2 = requests.post(
        f"{api_base_url}/api/filament_attributes/add_choice",
        json={"choice": "x" * 200}, timeout=5,
    )
    assert r2.status_code == 400


@pytest.mark.usefixtures("require_server")
def test_bulk_set_preserves_sibling_extras(api_base_url):
    """Regression for the L58 root cause: a bulk-op stripping siblings.
    Spoolman PATCH on `extra` REPLACES the dict, so a partial payload
    can silently wipe nozzle_temp_max, product_url, etc. Our endpoint
    routes through spoolman_api.update_filament which merges. Pick a
    filament that already has at least one non-attribute extra and
    confirm it survives the bulk-set."""
    r = requests.get(f"{api_base_url}/api/filament_attributes/report", timeout=10)
    body = r.json()
    choices = body.get("choices", [])

    target_fid = None
    sibling_key = None
    sibling_val = None
    for f in body["filaments"]:
        if f["archived"]:
            continue
        full = requests.get(f"{api_base_url}/api/filaments/{f['id']}", timeout=5)
        if not full.ok:
            continue
        body_full = full.json() or {}
        fil = body_full.get("data") if isinstance(body_full.get("data"), dict) else body_full
        extras = (fil or {}).get("extra") or {}
        for k, v in extras.items():
            if k != "filament_attributes" and v not in (None, "", "[]"):
                target_fid = f["id"]
                sibling_key = k
                sibling_val = v
                break
        if target_fid:
            break

    if not target_fid:
        pytest.skip("no filament with a sibling extra in dev DB — can't test merge guard")

    candidate = next((c for c in choices if c not in (
        _snapshot_attrs(api_base_url, target_fid))), None)
    if not candidate:
        pytest.skip("no available choice for add — target has every choice")

    original = _snapshot_attrs(api_base_url, target_fid)
    try:
        requests.post(
            f"{api_base_url}/api/filament_attributes/bulk_set",
            json={"filament_ids": [target_fid], "add": [candidate]},
            timeout=10,
        )
        full_after = requests.get(f"{api_base_url}/api/filaments/{target_fid}", timeout=5).json()
        fil_after = full_after.get("data") if isinstance(full_after.get("data"), dict) else full_after
        after_extras = (fil_after or {}).get("extra") or {}
        assert sibling_key in after_extras, (
            f"sibling extra {sibling_key!r} was wiped by bulk-set "
            f"(had {sibling_val!r}, got {after_extras.get(sibling_key)!r})"
        )
        # Value preserved too (modulo Spoolman's JSON-string wire form).
        assert str(after_extras[sibling_key]) == str(sibling_val), (
            f"sibling extra {sibling_key!r} value changed: "
            f"{sibling_val!r} → {after_extras[sibling_key]!r}"
        )
    finally:
        _restore(api_base_url, target_fid, original)
