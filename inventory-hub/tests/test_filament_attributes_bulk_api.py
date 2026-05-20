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
