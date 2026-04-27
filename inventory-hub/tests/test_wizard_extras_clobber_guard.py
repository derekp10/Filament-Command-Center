"""Unit tests for the wizard's system-managed-keys guard (Phase D / Item 4).

Pre-fix: the wizard could write `container_slot` (and the related ghost-
trail keys) directly via /api/edit_spool_wizard, which silently re-deployed
or unseated a slotted spool when the user merely edited filament data.

Post-fix: api_edit_spool_wizard funnels its `extra` dict through
`compute_dirty_extras(..., system_managed=SYSTEM_MANAGED_EXTRAS)` so any
attempt to write those keys is dropped at the backend boundary regardless
of what the JS sends. This file pins that contract.
"""
from __future__ import annotations

import json
from unittest.mock import patch

import pytest

import app as fcc_app
import spoolman_api


@pytest.fixture
def client():
    fcc_app.app.config["TESTING"] = True
    with fcc_app.app.test_client() as c:
        yield c


def _existing_spool_with_slot():
    """Mock get_spool return value: a spool actively slotted to XL-1
    plus a few sibling extras that must survive the wizard edit."""
    return {
        "id": 42,
        "filament": {"id": 7},
        "spool_weight": 250,
        "extra": {
            "container_slot": "XL-1",
            "physical_source": "PM-DB-XL-L",
            "physical_source_slot": "1",
            "purchase_url": "https://example.com/before",
            "spool_temp": "70",
        },
    }


class TestWizardEditStripsSystemManagedKeys:
    def test_wizard_never_writes_container_slot_even_when_jspayload_includes_it(self):
        """The single most important guarantee: even if the JS or a malicious
        client posts `container_slot` in the wizard payload, the backend
        must NEVER pass it through to update_spool. Item 4 regression."""
        original = _existing_spool_with_slot()
        captured = {}

        def fake_update_spool(sid, data):
            captured["data"] = data
            return {"id": sid}

        with patch.object(spoolman_api, "get_spool", return_value=original), \
             patch.object(spoolman_api, "update_spool", side_effect=fake_update_spool):
            r = client_post(
                fcc_app.app.test_client(),
                "/api/edit_spool_wizard",
                {
                    "spool_id": 42,
                    "spool_data": {
                        "extra": {
                            # Legit user edit:
                            "purchase_url": "https://example.com/AFTER",
                            # The clobber attempt — must be dropped:
                            "container_slot": "",
                            "physical_source": "",
                            "physical_source_slot": "",
                        }
                    },
                },
            )
            assert r.status_code == 200
            body = r.get_json()
            assert body.get("success") is True

        # update_spool must have been called with ONLY the safe key.
        assert "data" in captured, "update_spool was never called"
        sent_extra = captured["data"].get("extra", {})
        assert "container_slot" not in sent_extra
        assert "physical_source" not in sent_extra
        assert "physical_source_slot" not in sent_extra
        assert sent_extra.get("purchase_url") == "https://example.com/AFTER"

    def test_no_op_wizard_save_with_only_system_managed_keys_does_not_call_update(self):
        """If the wizard payload contains ONLY system-managed keys (which
        should never happen in practice), the entire extras dict is
        stripped → nothing dirty → update_spool MUST NOT fire. Pre-fix,
        this would have happily PATCHed empty values onto the slot."""
        original = _existing_spool_with_slot()
        with patch.object(spoolman_api, "get_spool", return_value=original), \
             patch.object(spoolman_api, "update_spool") as mock_update:
            r = client_post(
                fcc_app.app.test_client(),
                "/api/edit_spool_wizard",
                {
                    "spool_id": 42,
                    "spool_data": {
                        "extra": {
                            "container_slot": "",
                            "physical_source": "",
                            "physical_source_slot": "",
                        }
                    },
                },
            )
            assert r.status_code == 200
            body = r.get_json()
            assert body.get("success") is True
            mock_update.assert_not_called()

    def test_legit_extra_change_passes_through_unaffected(self):
        original = _existing_spool_with_slot()
        captured = {}

        def fake_update_spool(sid, data):
            captured["data"] = data
            return {"id": sid}

        with patch.object(spoolman_api, "get_spool", return_value=original), \
             patch.object(spoolman_api, "update_spool", side_effect=fake_update_spool):
            r = client_post(
                fcc_app.app.test_client(),
                "/api/edit_spool_wizard",
                {
                    "spool_id": 42,
                    "spool_data": {
                        "extra": {
                            "spool_temp": "85",
                        }
                    },
                },
            )
            assert r.status_code == 200

        sent_extra = captured["data"].get("extra", {})
        assert sent_extra == {"spool_temp": "85"}

    def test_unchanged_extra_value_does_not_trigger_update(self):
        """If the user opens + saves the wizard without changing anything,
        compute_dirty_extras returns {} and update_spool MUST NOT fire.
        Sanity-check the diff still works after the helper extraction."""
        original = _existing_spool_with_slot()
        with patch.object(spoolman_api, "get_spool", return_value=original), \
             patch.object(spoolman_api, "update_spool") as mock_update:
            r = client_post(
                fcc_app.app.test_client(),
                "/api/edit_spool_wizard",
                {
                    "spool_id": 42,
                    "spool_data": {
                        "extra": {
                            "purchase_url": "https://example.com/before",  # same as existing
                            "spool_temp": "70",                              # same as existing
                        }
                    },
                },
            )
            assert r.status_code == 200
            mock_update.assert_not_called()


# Tiny shim so each `with` block can post JSON cleanly without having to
# nest a `with fcc_app.app.test_client() as c:` for each call.
def client_post(client, path: str, payload: dict):
    return client.post(path, data=json.dumps(payload),
                       content_type="application/json")
