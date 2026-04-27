"""Integration tests against the real dev Spoolman at 192.168.1.29:7913.

These tests are gated behind `@pytest.mark.integration` and skipped by
default. Opt in via `pytest --run-integration` or `RUN_INTEGRATION=1`.

Why these exist:
  Every existing test mocks `/api/filaments`, `/api/update_filament`,
  `/api/update_spool`. Mocks always echo what we send, so server-side
  behavior — Spoolman's PATCH-replaces-extras semantics, text-type
  validation that 400s on naked numeric strings, the field-schema
  delete-on-deploy that wipes container_slot — is invisible to the
  suite. This gap let through the 2026-04-26 product_url/purchase_url
  data-loss bug AND the 2026-04-27 prod-breaking sanitize bug, both of
  which would have failed loudly here with a single round-trip test.

Each test:
  1. creates a fresh filament + spool on dev Spoolman (throwaway fixtures)
  2. exercises the path under test (either via local Flask app or
     directly against Spoolman)
  3. reads back the record and asserts the field survived
  4. cleans up via fixture teardown (best-effort delete)
"""
from __future__ import annotations

import json
import time

import pytest
import requests


pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _get_spool_raw(spoolman_url: str, sid: int) -> dict:
    """Fetch a spool from Spoolman without going through parse_inbound_data.
    Returns Spoolman's raw form (extras still JSON-wrapped)."""
    r = requests.get(f"{spoolman_url}/api/v1/spool/{sid}", timeout=5)
    r.raise_for_status()
    return r.json() or {}


def _get_filament_raw(spoolman_url: str, fid: int) -> dict:
    r = requests.get(f"{spoolman_url}/api/v1/filament/{fid}", timeout=5)
    r.raise_for_status()
    return r.json() or {}


def _ensure_extra_field(spoolman_url: str, entity: str, key: str, name: str,
                        ftype: str = "text") -> None:
    """Idempotently register an extra-field schema. Tests need this because
    Spoolman 400s on PATCHes that include unknown extra keys; the local
    Flask app calls setup_fields.py at boot to register them, but tests
    that pre-seed extras directly via the Spoolman API need the schema
    registered too."""
    payload = {"name": name, "field_type": ftype}
    try:
        requests.post(
            f"{spoolman_url}/api/v1/field/{entity}/{key}", json=payload, timeout=5
        )
    except requests.RequestException:
        pass


# ---------------------------------------------------------------------------
# Test 1 — PATCH preserves siblings (filament 157 regression)
# ---------------------------------------------------------------------------

def test_partial_patch_preserves_sibling_extras(
    require_spoolman: str,
    throwaway_spool_with_extras,
):
    """Regression for the 2026-04-26 incident where a single 'Use Scanned'
    click on filament 157 wiped product_url, purchase_url, original_color.

    Reproduce by pre-seeding three sibling extras, then PATCHing only ONE
    of them via the local Flask wrapper (`spoolman_api.update_spool`).
    Without our internal read-merge-write guard, Spoolman would replace
    the entire extras dict and the unmentioned siblings would vanish.
    """
    _ensure_extra_field(require_spoolman, "spool", "product_url", "Product Page Link")
    _ensure_extra_field(require_spoolman, "spool", "purchase_url", "Purchase Link")
    _ensure_extra_field(require_spoolman, "spool", "original_color", "Original Color")

    spool = throwaway_spool_with_extras({
        "product_url": "https://example.com/product",
        "purchase_url": "https://example.com/buy",
        "original_color": "ORIG-RED",
    })
    sid = spool["id"]

    # Import the local Flask app's spoolman_api wrapper so we exercise
    # the same code path the production endpoints use.
    import spoolman_api
    result = spoolman_api.update_spool(sid, {
        "extra": {"product_url": "https://example.com/UPDATED"},
    })
    assert result is not None, (
        f"update_spool returned None — Spoolman likely rejected the PATCH. "
        f"LAST_SPOOLMAN_ERROR={getattr(spoolman_api, 'LAST_SPOOLMAN_ERROR', '<unset>')}"
    )

    fresh = _get_spool_raw(require_spoolman, sid)
    extra = fresh.get("extra") or {}
    # Wire form is JSON-encoded; values come back as quoted strings.
    assert extra.get("product_url") == json.dumps("https://example.com/UPDATED"), \
        f"product_url not updated: {extra.get('product_url')!r}"
    assert extra.get("purchase_url") == json.dumps("https://example.com/buy"), \
        f"purchase_url WIPED by partial PATCH (extras-clobber regression): {extra.get('purchase_url')!r}"
    assert extra.get("original_color") == json.dumps("ORIG-RED"), \
        f"original_color WIPED by partial PATCH (extras-clobber regression): {extra.get('original_color')!r}"


# ---------------------------------------------------------------------------
# Test 2 — Text-type numeric string survives round-trip (2026-04-27 sanitize bug)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("key,value", [
    ("prusament_length_m", "330"),
    ("nozzle_temp_max", "260"),
    ("bed_temp_max", "85"),
])
def test_text_type_numeric_string_survives_roundtrip(
    require_spoolman: str,
    throwaway_spool_with_extras,
    key: str,
    value: str,
):
    """Regression for the 2026-04-27 prod outage: text-type extras storing
    numeric-looking strings (e.g. `prusament_length_m: "330"`) got
    unwrapped by parse_inbound_data → re-sanitized as int → Spoolman 400'd
    → slot assignments stuck, label-confirms missing, force-moves no-op.

    Fix in spoolman_api.py JSON_STRING_FIELDS expansion (2026-04-27).
    Test: pre-seed the value, run an unrelated PATCH, confirm value
    still equals the literal string."""
    _ensure_extra_field(require_spoolman, "spool", key, key.replace("_", " ").title())

    spool = throwaway_spool_with_extras({key: value, "spool_temp": "70"})
    sid = spool["id"]

    import spoolman_api
    # Force the merge path — touch a different key so the canonical
    # extras-clobber guard fires.
    result = spoolman_api.update_spool(sid, {"extra": {"spool_temp": "75"}})
    assert result is not None, (
        f"update_spool returned None for unrelated PATCH — sanitize bug? "
        f"LAST_SPOOLMAN_ERROR={getattr(spoolman_api, 'LAST_SPOOLMAN_ERROR', '<unset>')}"
    )

    fresh = _get_spool_raw(require_spoolman, sid)
    extra = fresh.get("extra") or {}
    assert extra.get(key) == json.dumps(value), \
        f"{key} round-trip lost: expected {json.dumps(value)!r}, got {extra.get(key)!r}"


# ---------------------------------------------------------------------------
# Test 3 — Label-scan flips needs_label_print without wiping siblings
# ---------------------------------------------------------------------------

def test_spool_label_scan_flips_needs_label_print_without_wiping_siblings(
    require_spoolman: str,
    require_server: str,
    throwaway_spool_with_extras,
):
    """Pre-seed needs_label_print=true plus several siblings, scan
    `ID:<n>` via the local Flask /api/identify_scan, assert needs_label_print
    is now False AND siblings survive.

    Covers Item 3 (spool label-confirm 2026-04-27 regression) and Item 1
    (extras-clobber on label-confirm path)."""
    _ensure_extra_field(require_spoolman, "spool", "needs_label_print", "Needs Label Print", "boolean")
    _ensure_extra_field(require_spoolman, "spool", "product_url", "Product Page Link")
    _ensure_extra_field(require_spoolman, "spool", "purchase_url", "Purchase Link")

    spool = throwaway_spool_with_extras({
        "needs_label_print": True,
        "product_url": "https://example.com/p",
        "purchase_url": "https://example.com/b",
    })
    sid = spool["id"]

    # Must use source='barcode' — the label-confirm path at
    # app.py:1317 gates on source=='barcode' so manual keyboard typing
    # doesn't accidentally clear the flag.
    r = requests.post(
        f"{require_server}/api/identify_scan",
        json={"text": f"ID:{sid}", "source": "barcode"},
        timeout=10,
    )
    assert r.ok, f"/api/identify_scan failed: {r.status_code} {r.text}"

    # Brief settle window — the scan handler is synchronous but Spoolman's
    # PATCH may take a moment to be visible on a follow-up GET.
    time.sleep(0.2)

    fresh = _get_spool_raw(require_spoolman, sid)
    extra = fresh.get("extra") or {}
    assert extra.get("needs_label_print") in ("false", json.dumps("false"), False), \
        f"needs_label_print not cleared after scan: {extra.get('needs_label_print')!r}"
    assert extra.get("product_url") == json.dumps("https://example.com/p"), \
        f"product_url WIPED by label-confirm scan: {extra.get('product_url')!r}"
    assert extra.get("purchase_url") == json.dumps("https://example.com/b"), \
        f"purchase_url WIPED by label-confirm scan: {extra.get('purchase_url')!r}"


# ---------------------------------------------------------------------------
# Test 4 — Slot assignment scan succeeds with prusament_* extras present
# ---------------------------------------------------------------------------

def test_slot_assignment_succeeds_with_prusament_extras_loaded(
    require_spoolman: str,
    throwaway_spool_with_extras,
):
    """Pre-seed every JSON_STRING_FIELDS key with a representative value,
    then update via the local wrapper. The 2026-04-27 sanitize bug
    manifested specifically when these text-type extras were present —
    any unrelated PATCH would silently 400 on the round-trip.

    This test pins the JSON_STRING_FIELDS list: if a new text-type extra
    is added that stores numeric-looking strings, this test will fail
    until JSON_STRING_FIELDS is updated."""
    text_extras = {
        "spool_type": "PETG",
        "container_slot": "STAGING",
        "physical_source": "PM-DB-XL-L",
        "physical_source_slot": "1",
        "original_color": "RED",
        "spool_temp": "70",
        "product_url": "https://example.com/p",
        "purchase_url": "https://example.com/b",
        "nozzle_temp_max": "260",
        "bed_temp_max": "85",
        "prusament_length_m": "330",
    }
    for k in text_extras:
        _ensure_extra_field(require_spoolman, "spool", k, k.replace("_", " ").title())

    spool = throwaway_spool_with_extras(text_extras)
    sid = spool["id"]

    import spoolman_api
    # Touch a SINGLE key. Must not cause Spoolman to reject due to one of
    # the others being mis-sanitized.
    result = spoolman_api.update_spool(sid, {"extra": {"original_color": "BLUE"}})
    assert result is not None, (
        f"update_spool 400'd while sibling extras were loaded. "
        f"This is the 2026-04-27 prod regression class — JSON_STRING_FIELDS "
        f"likely missing a key. LAST_SPOOLMAN_ERROR="
        f"{getattr(spoolman_api, 'LAST_SPOOLMAN_ERROR', '<unset>')}"
    )

    fresh = _get_spool_raw(require_spoolman, sid)
    extra = fresh.get("extra") or {}
    for k, v in text_extras.items():
        if k == "original_color":
            assert extra.get(k) == json.dumps("BLUE"), \
                f"{k} not updated: {extra.get(k)!r}"
        else:
            assert extra.get(k) == json.dumps(v), \
                f"{k} round-trip lost: expected {json.dumps(v)!r}, got {extra.get(k)!r}"


# ---------------------------------------------------------------------------
# Test 5 — update_spool populates LAST_SPOOLMAN_ERROR on rejection
# ---------------------------------------------------------------------------

def test_update_spool_populates_last_spoolman_error_on_rejection(
    require_spoolman: str,
    throwaway_spool,
):
    """Pin the Phase B.1 symmetry fix: today `update_filament` populates
    `LAST_SPOOLMAN_ERROR` but `update_spool` does NOT — silent failures
    in label-confirm, slot-assignment, force-move all fail mute. After
    Phase B.1, both functions populate the global on rejection.

    Trigger: send a payload with a deliberately broken numeric field
    (Spoolman rejects with a clear 400)."""
    import spoolman_api
    spoolman_api.LAST_SPOOLMAN_ERROR = None  # reset before assertion

    sid = throwaway_spool["id"]
    # Negative weight is rejected by Spoolman's validator with HTTP 422.
    result = spoolman_api.update_spool(sid, {"used_weight": -9999, "initial_weight": 1000})

    assert result is None, "update_spool should return None on rejection"
    assert spoolman_api.LAST_SPOOLMAN_ERROR, (
        "LAST_SPOOLMAN_ERROR was not set by update_spool. This is the "
        "Phase B.1 symmetry fix — without it, every silent-fail caller "
        "is blind to WHY Spoolman rejected the PATCH."
    )


# ---------------------------------------------------------------------------
# Test 6 — Wizard edit on slotted spool preserves container_slot
# ---------------------------------------------------------------------------

def test_wizard_edit_preserves_container_slot_on_slotted_spool(
    require_spoolman: str,
    require_server: str,
    throwaway_spool_with_extras,
):
    """Item 4 regression: editing a spool's filament data while it's
    slotted into a toolhead should NOT wipe `container_slot`.

    Setup: pre-seed container_slot="XL-1" plus a side extras key.
    Action: POST to /api/edit_spool_wizard with a payload that changes
    the side key (mimicking a wizard save where the user only edited
    purchase_url).
    Assert: container_slot survived.

    Today's behavior: depending on whether the wizard JS sends
    container_slot in its payload, this either passes (the merge
    works) or fails (a stray empty value clobbers it). Phase D adds a
    backend allow-list that strips system-managed keys before the diff,
    making this safe regardless of what the JS sends."""
    _ensure_extra_field(require_spoolman, "spool", "container_slot", "Container / MMU Slot")
    _ensure_extra_field(require_spoolman, "spool", "purchase_url", "Purchase Link")

    spool = throwaway_spool_with_extras({
        "container_slot": "XL-1",
        "purchase_url": "https://example.com/before",
    })
    sid = spool["id"]

    # Mimic the wizard's edit payload: a sparse extras dict that includes
    # ONLY purchase_url. (Real wizards may also include a stray empty
    # container_slot — see Phase D.) Try with-and-without to cover both.
    edit_payload = {
        "spool_id": sid,
        "spool_data": {
            "extra": {
                "purchase_url": "https://example.com/AFTER",
            },
        },
    }
    r = requests.post(
        f"{require_server}/api/edit_spool_wizard",
        json=edit_payload,
        timeout=10,
    )
    # If the endpoint shape is wrong the test still should not silently pass.
    assert r.status_code in (200, 201, 400, 422), (
        f"/api/edit_spool_wizard returned unexpected {r.status_code}: {r.text[:200]}"
    )

    fresh = _get_spool_raw(require_spoolman, sid)
    extra = fresh.get("extra") or {}
    assert extra.get("container_slot") == json.dumps("XL-1"), (
        f"container_slot LOST after wizard edit (Item 4 regression). "
        f"Expected {json.dumps('XL-1')!r}, got {extra.get('container_slot')!r}"
    )


# ---------------------------------------------------------------------------
# Test 7 — setup_fields.py is idempotent and non-destructive
# ---------------------------------------------------------------------------

def test_setup_fields_does_not_wipe_container_slot_values(
    require_spoolman: str,
    throwaway_spool_with_extras,
):
    """Item 5 regression: spools lose `container_slot` when a new version
    is deployed to production. The smoking gun is
    setup-and-rebuild/setup_fields.py:178 calling
    `create_field('spool', 'container_slot', ..., force_reset=True)` —
    DELETES the field schema and recreates on every deploy.

    Test: pre-seed a spool with container_slot, run setup_fields against
    dev Spoolman, confirm the value survives. Then run it AGAIN — also
    survives.

    Phase C.1 removes force_reset=True (steady-state idempotent create).
    Phase C.2 adds a guarded one-time migration if the field type ever
    needs to change."""
    _ensure_extra_field(require_spoolman, "spool", "container_slot", "Container / MMU Slot")

    spool = throwaway_spool_with_extras({"container_slot": "PROD-DEPLOY-1"})
    sid = spool["id"]

    # Run setup_fields. We invoke it via subprocess because the script's
    # top-level executes on import; a clean subprocess matches the deploy
    # path exactly.
    import os
    import subprocess
    script_path = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "setup-and-rebuild", "setup_fields.py")
    )
    if not os.path.isfile(script_path):
        pytest.skip(f"setup_fields.py not found at {script_path}")

    env = os.environ.copy()
    # Make sure the script targets the dev Spoolman (it reads the URL via
    # config_loader which respects FCC_SPOOLMAN_URL or the default).
    # PYTHONIOENCODING handles the emoji prints in the script on Windows
    # (cp1252 console can't encode 🔗 / ✅ etc.); in prod the script runs
    # inside the utf-8 Docker container so this is purely test-env hygiene.
    env["PYTHONIOENCODING"] = "utf-8"
    proc = subprocess.run(
        ["python", script_path],
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0, (
        f"setup_fields.py failed: stdout={proc.stdout[:500]!r} stderr={proc.stderr[:500]!r}"
    )

    fresh = _get_spool_raw(require_spoolman, sid)
    extra = fresh.get("extra") or {}
    assert extra.get("container_slot") == json.dumps("PROD-DEPLOY-1"), (
        f"container_slot WIPED by setup_fields.py — this is the deployment-"
        f"triggered slot-loss bug. Phase C.1 fix: remove force_reset=True. "
        f"Got {extra.get('container_slot')!r}"
    )


# ---------------------------------------------------------------------------
# Test 8 — Filament label-confirm preserves extras
# ---------------------------------------------------------------------------

def test_filament_label_scan_flips_needs_label_print_without_wiping(
    require_spoolman: str,
    require_server: str,
    throwaway_filament,
):
    """Item 6 regression: filament 126 label scan didn't verify (silent-
    failure class). Same shape as test 3 but for FIL:<n> scans hitting
    the filament-side branch at app.py:1360-1378."""
    _ensure_extra_field(require_spoolman, "filament", "needs_label_print", "Needs Label Print", "boolean")
    _ensure_extra_field(require_spoolman, "filament", "product_url", "Product Page Link")

    fid = throwaway_filament["id"]
    # Seed the filament's extras directly via Spoolman PATCH so the
    # filament-side label-confirm path has work to do.
    seed_resp = requests.patch(
        f"{require_spoolman}/api/v1/filament/{fid}",
        json={"extra": {
            "needs_label_print": "true",
            "product_url": json.dumps("https://example.com/preserve-me"),
        }},
        timeout=5,
    )
    assert seed_resp.ok, f"Failed to seed filament extras: {seed_resp.status_code} {seed_resp.text}"

    r = requests.post(
        f"{require_server}/api/identify_scan",
        json={"text": f"FIL:{fid}", "source": "barcode"},
        timeout=10,
    )
    assert r.ok, f"/api/identify_scan FIL:<n> failed: {r.status_code} {r.text}"

    time.sleep(0.2)
    fresh = _get_filament_raw(require_spoolman, fid)
    extra = fresh.get("extra") or {}
    assert extra.get("needs_label_print") in ("false", json.dumps("false"), False), (
        f"filament needs_label_print not cleared after FIL:<n> scan "
        f"(Item 6 regression): {extra.get('needs_label_print')!r}"
    )
    assert extra.get("product_url") == json.dumps("https://example.com/preserve-me"), (
        f"filament product_url WIPED by label-confirm: {extra.get('product_url')!r}"
    )
