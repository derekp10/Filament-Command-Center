"""End-to-end backend tests for the vendor-create-from-modal flow.

The Group 6.2 cleanup retired the legacy `extras.external_vendor_name` path
that let the wizard send a name string and have the backend create a vendor
as a side-effect of filament creation. The new flow: the Vendor Edit modal
posts to /api/vendors in create mode, the wizard listens for `vendor:created`
and auto-selects the new vendor, and only then does the wizard submit with
`vendor_id`. This test exercises the full backend round-trip end-to-end
against the real dev Spoolman so any hidden state-sync or refresh bug
between the create and the subsequent filament-with-vendor_id POST surfaces.

Covers:
  - POST /api/vendors with the new full-payload shape persists every field.
  - The newly created vendor is immediately visible to GET /api/vendors.
  - A follow-up POST /api/create_inventory_wizard with that vendor_id
    succeeds (no race / no "non-existent manufacturer" rejection).
  - The created filament reports the correct nested `vendor.id`/`vendor.name`.
  - The retired `extras.external_vendor_name` path is gone: a wizard create
    with that key returns success ONLY if Spoolman happens to accept it as a
    normal extra (which it shouldn't, since the field isn't registered) —
    we assert it's no longer auto-translated into a vendor create.
"""
from __future__ import annotations

import uuid

import requests


def test_full_create_vendor_then_assign_to_new_filament(
    api_base_url: str, require_server: str, require_spoolman: str
):
    """Mirror the exact UI flow: POST /api/vendors with the modal's payload,
    then POST /api/create_inventory_wizard with that vendor_id. Cleanup
    deletes both records via Spoolman direct API."""
    suffix = uuid.uuid4().hex[:8]
    vendor_name = f"__fcc_test_e2e_vendor_{suffix}"
    website = f"https://e2e-{suffix}.example"

    created_vendor_id = None
    created_filament_id = None

    try:
        # Step 1: POST /api/vendors using the new full-payload shape that
        # the Vendor Edit modal's create mode sends.
        post_payload = {
            "data": {
                "name": vendor_name,
                "comment": "End-to-end test",
                "external_id": f"e2e-{suffix}",
                "empty_spool_weight": 187.5,
                "extra": {"website": f'"{website}"'},
            }
        }
        r = requests.post(
            f"{api_base_url}/api/vendors",
            json=post_payload,
            timeout=10,
        )
        assert r.ok, f"POST /api/vendors failed: {r.status_code} {r.text}"
        body = r.json()
        assert body.get("success") is True, body
        new_vendor = body.get("vendor") or {}
        created_vendor_id = new_vendor.get("id")
        assert created_vendor_id, "POST /api/vendors did not return a vendor id"
        assert new_vendor.get("name") == vendor_name
        assert new_vendor.get("comment") == "End-to-end test"
        assert new_vendor.get("external_id") == f"e2e-{suffix}"
        assert float(new_vendor.get("empty_spool_weight")) == 187.5
        # Website is stored as a JSON-quoted string per JSON_STRING_FIELDS.
        assert (new_vendor.get("extra") or {}).get("website") == f'"{website}"'

        # Step 2: the new vendor should be immediately visible to the
        # endpoint the wizard uses to repopulate its dropdown. This is
        # the hop the user worried about — a hidden cache between the
        # create and the dropdown refetch would surface here.
        r = requests.get(f"{api_base_url}/api/vendors", timeout=5)
        assert r.ok
        listing = r.json().get("vendors") or []
        assert any(v.get("id") == created_vendor_id for v in listing), (
            f"Newly created vendor #{created_vendor_id} missing from /api/vendors listing"
        )

        # Step 3: simulate the wizard submit with vendor_id pointing at the
        # brand-new vendor. This is the exact payload shape inv_wizard.js
        # sends from wizardSubmit after the cleanup.
        filament_name = f"__fcc_test_e2e_fil_{suffix}"
        wizard_payload = {
            "filament_data": {
                "name": filament_name,
                "material": "PLA",
                "vendor_id": created_vendor_id,
                "color_hex": "112233",
                "density": 1.24,
                "diameter": 1.75,
                "weight": 1000,
                "extra": {},
            },
            "spool_data": None,
            "quantity": 0,
        }
        r = requests.post(
            f"{api_base_url}/api/create_inventory_wizard",
            json=wizard_payload,
            timeout=15,
        )
        assert r.ok, f"Wizard submit failed: {r.status_code} {r.text}"
        wiz_body = r.json()
        assert wiz_body.get("success") is True, wiz_body
        created_filament_id = wiz_body.get("filament_id")
        assert created_filament_id, f"Wizard returned no filament_id: {wiz_body}"

        # Step 4: the created filament reports the correct nested vendor.
        r = requests.get(
            f"{require_spoolman}/api/v1/filament/{created_filament_id}",
            timeout=5,
        )
        assert r.ok, f"Filament fetch failed: {r.status_code} {r.text}"
        fil = r.json()
        assert (fil.get("vendor") or {}).get("id") == created_vendor_id
        assert (fil.get("vendor") or {}).get("name") == vendor_name

    finally:
        # Best-effort cleanup. Spoolman refuses to delete a vendor while
        # filaments reference it, so the filament goes first.
        if created_filament_id is not None:
            try:
                requests.delete(
                    f"{require_spoolman}/api/v1/filament/{created_filament_id}",
                    timeout=5,
                )
            except requests.RequestException:
                pass
        if created_vendor_id is not None:
            try:
                requests.delete(
                    f"{require_spoolman}/api/v1/vendor/{created_vendor_id}",
                    timeout=5,
                )
            except requests.RequestException:
                pass


def test_vendor_empty_weight_propagates_through_wizard_submit(
    api_base_url: str, require_server: str, require_spoolman: str
):
    """Vendor → filament → spool empty-weight propagation end-to-end.

    The frontend test (test_wizard_vendor_edit_button.py:
    test_vendor_created_autoselects_in_wizard) confirms the wizard UI
    fills wiz-fil-empty_weight + wiz-spool-empty_weight from the new
    vendor's empty_spool_weight after the vendor:created listener runs.

    This test covers the back-end half: the wizard's submit payload — which
    matches what inv_wizard.js sends after that cascade — persists those
    weights on the resulting filament AND spool. Together the two layers
    rule out a "value populated in the UI but dropped on the wire" bug.
    """
    suffix = uuid.uuid4().hex[:8]
    vendor_name = f"__fcc_test_cascade_vendor_{suffix}"
    vendor_weight = 198.0

    created_vendor_id = None
    created_filament_id = None
    created_spool_ids: list[int] = []

    try:
        # Step 1: create vendor with empty_spool_weight (the value the
        # cascade will inherit).
        r = requests.post(
            f"{api_base_url}/api/vendors",
            json={"data": {"name": vendor_name, "empty_spool_weight": vendor_weight}},
            timeout=10,
        )
        assert r.ok, f"POST /api/vendors failed: {r.status_code} {r.text}"
        new_vendor = r.json().get("vendor") or {}
        created_vendor_id = new_vendor.get("id")
        assert created_vendor_id
        assert float(new_vendor.get("empty_spool_weight")) == vendor_weight

        # Step 2: submit the wizard create with filament + spool. The
        # filament's spool_weight + the spool's spool_weight are both set
        # to the vendor's value — this is what the cascade-populated fields
        # would put on the wire (inv_wizard.js:wizardSubmit reads each
        # input and serializes whatever the cascade resolved).
        filament_name = f"__fcc_test_cascade_fil_{suffix}"
        wizard_payload = {
            "filament_data": {
                "name": filament_name,
                "material": "PLA",
                "vendor_id": created_vendor_id,
                "color_hex": "AABBCC",
                "density": 1.24,
                "diameter": 1.75,
                "weight": 1000,
                "spool_weight": vendor_weight,
                "extra": {},
            },
            "spool_data": {
                "used_weight": 0,
                "spool_weight": vendor_weight,
                "initial_weight": 1000,
                "extra": {},
            },
            "quantity": 1,
        }
        r = requests.post(
            f"{api_base_url}/api/create_inventory_wizard",
            json=wizard_payload,
            timeout=15,
        )
        assert r.ok, f"Wizard submit failed: {r.status_code} {r.text}"
        wiz_body = r.json()
        assert wiz_body.get("success") is True, wiz_body
        created_filament_id = wiz_body.get("filament_id")
        assert created_filament_id

        # Step 3: filament persists with the cascaded spool_weight.
        r = requests.get(
            f"{require_spoolman}/api/v1/filament/{created_filament_id}",
            timeout=5,
        )
        assert r.ok
        fil = r.json()
        assert float(fil.get("spool_weight")) == vendor_weight, (
            f"Filament spool_weight not persisted: expected {vendor_weight}, "
            f"got {fil.get('spool_weight')!r}"
        )

        # Step 4: at least one spool was created and it carries the cascaded
        # weight. /api/v1/spool listing filtered by filament catches any
        # spool the wizard generated under that quantity.
        r = requests.get(f"{require_spoolman}/api/v1/spool", timeout=5)
        assert r.ok
        spools = [
            s for s in (r.json() or [])
            if (s.get("filament") or {}).get("id") == created_filament_id
        ]
        assert spools, f"No spools created for filament #{created_filament_id}"
        created_spool_ids = [s.get("id") for s in spools]
        for sp in spools:
            assert float(sp.get("spool_weight")) == vendor_weight, (
                f"Spool #{sp.get('id')} spool_weight not persisted: "
                f"expected {vendor_weight}, got {sp.get('spool_weight')!r}"
            )

    finally:
        for sid in created_spool_ids:
            try:
                requests.delete(
                    f"{require_spoolman}/api/v1/spool/{sid}", timeout=5
                )
            except requests.RequestException:
                pass
        if created_filament_id is not None:
            try:
                requests.delete(
                    f"{require_spoolman}/api/v1/filament/{created_filament_id}",
                    timeout=5,
                )
            except requests.RequestException:
                pass
        if created_vendor_id is not None:
            try:
                requests.delete(
                    f"{require_spoolman}/api/v1/vendor/{created_vendor_id}",
                    timeout=5,
                )
            except requests.RequestException:
                pass


def test_legacy_external_vendor_name_no_longer_auto_creates(
    api_base_url: str, require_server: str, require_spoolman: str
):
    """The retired `extras.external_vendor_name` path used to silently
    create a vendor as a side-effect of /api/create_inventory_wizard. With
    Group 6.2's cleanup that handler is gone, so this payload now either
    fails outright (Spoolman rejects the unknown extra) or, at minimum,
    does NOT create a vendor with that name.

    The wizard frontend stopped sending this key entirely — the test below
    locks in the back-end side of the cleanup so a regression that re-adds
    the auto-translate gets caught.
    """
    suffix = uuid.uuid4().hex[:8]
    sneaky_name = f"__fcc_test_legacy_path_{suffix}"

    created_filament_id = None
    try:
        wizard_payload = {
            "filament_data": {
                "name": f"__fcc_test_legacy_fil_{suffix}",
                "material": "PLA",
                "extra": {"external_vendor_name": sneaky_name},
            },
            "spool_data": None,
            "quantity": 0,
        }
        r = requests.post(
            f"{api_base_url}/api/create_inventory_wizard",
            json=wizard_payload,
            timeout=10,
        )
        body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        # Either branch is acceptable for "the legacy translate is gone":
        #   (a) Spoolman rejects the unregistered extra → success=False.
        #   (b) Spoolman accepts the extra as a literal value → success=True
        #       but no vendor was created with that name.
        if body.get("success"):
            created_filament_id = body.get("filament_id")
        # In NEITHER case should a vendor named `sneaky_name` exist.
        v = requests.get(f"{require_spoolman}/api/v1/vendor", timeout=5).json() or []
        assert not any(x.get("name") == sneaky_name for x in v), (
            f"Legacy external_vendor_name path is still auto-creating vendors: "
            f"found vendor named {sneaky_name!r}"
        )
    finally:
        if created_filament_id is not None:
            try:
                requests.delete(
                    f"{require_spoolman}/api/v1/filament/{created_filament_id}",
                    timeout=5,
                )
            except requests.RequestException:
                pass
