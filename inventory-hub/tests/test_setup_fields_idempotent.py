"""Unit tests for `setup_fields.migrate_container_slot_to_text` (Phase C).

The previous setup_fields.py called create_field with `force_reset=True`
on every deploy — Spoolman wipes the value of an extra field when its
schema is deleted, so every deployment silently zeroed `container_slot`
on every spool that wasn't actively deployed at deploy-time. Item 5
in Feature-Buglist (confirmed reproducible 2026-04-26).

The replacement migration runs the destructive rebuild ONLY when the
field's current type is something other than `text`, AND it snapshots
+ restores every spool's value first. These tests pin both halves of
that contract using mocked HTTP — no real Spoolman.
"""
from __future__ import annotations

import importlib.util
import os
import sys
from unittest.mock import patch, MagicMock

import pytest


# Load the migration script as a module without executing its top-level
# (which would attempt to talk to the real Spoolman). We patch
# `requests` at the module level after import.
def _load_setup_fields():
    """Load setup_fields.py without running its top-level main block.

    We monkey-patch `__name__` to avoid the if-not-already-loaded protections,
    AND we wire `requests.get` / `requests.post` etc. to return harmless
    placeholder responses so the top-level `find_file` / CSV-reader / API
    discovery calls don't blow up the import."""
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    script_path = os.path.join(repo_root, "setup-and-rebuild", "setup_fields.py")

    # Stub config_loader if it's not on the path so the top-level import
    # of `import config_loader` doesn't fail.
    inv_hub = os.path.join(repo_root, "inventory-hub")
    if inv_hub not in sys.path:
        sys.path.insert(0, inv_hub)

    spec = importlib.util.spec_from_file_location("setup_fields_under_test", script_path)
    mod = importlib.util.module_from_spec(spec)

    # Provide a benign Spoolman URL so the top-level config_loader call
    # has something to return.
    fake_resp = MagicMock(ok=True, status_code=200)
    fake_resp.json.return_value = []
    fake_resp.text = ""

    with patch("requests.get", return_value=fake_resp), \
         patch("requests.post", return_value=fake_resp), \
         patch("requests.delete", return_value=fake_resp), \
         patch("requests.patch", return_value=fake_resp):
        spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def setup_fields_mod():
    return _load_setup_fields()


# ---------------------------------------------------------------------------
# migrate_container_slot_to_text — Phase C.2
# ---------------------------------------------------------------------------

class TestMigrationIsNoOpWhenAlreadyText:
    """The most important property: on every steady-state deploy, the
    migration must be a pure no-op. Pre-fix, force_reset=True wiped
    values on every deploy."""

    def test_returns_without_calling_delete_when_field_is_already_text(self, setup_fields_mod):
        get_resp = MagicMock(status_code=200)
        get_resp.json.return_value = [
            {"key": "container_slot", "field_type": "text", "name": "Container / MMU Slot"},
        ]
        with patch.object(setup_fields_mod.requests, "get", return_value=get_resp) as mock_get, \
             patch.object(setup_fields_mod.requests, "delete") as mock_delete, \
             patch.object(setup_fields_mod.requests, "post") as mock_post, \
             patch.object(setup_fields_mod.requests, "patch") as mock_patch:
            setup_fields_mod.migrate_container_slot_to_text()

        # Field schema lookup should have been queried ONCE.
        # (the field_type=='text' branch returns immediately so no spool list)
        get_calls = [c for c in mock_get.call_args_list if "/api/v1/field/spool" in str(c)]
        assert len(get_calls) >= 1, "Migration should fetch the field definition"
        # No destructive operations.
        mock_delete.assert_not_called()
        mock_post.assert_not_called()
        mock_patch.assert_not_called()

    def test_returns_without_action_when_field_does_not_exist(self, setup_fields_mod):
        get_resp = MagicMock(status_code=200)
        get_resp.json.return_value = []  # field not present yet
        with patch.object(setup_fields_mod.requests, "get", return_value=get_resp), \
             patch.object(setup_fields_mod.requests, "delete") as mock_delete, \
             patch.object(setup_fields_mod.requests, "post") as mock_post, \
             patch.object(setup_fields_mod.requests, "patch") as mock_patch:
            setup_fields_mod.migrate_container_slot_to_text()
        mock_delete.assert_not_called()
        mock_post.assert_not_called()
        mock_patch.assert_not_called()


class TestMigrationSnapshotsAndRestoresValues:
    """When the field type IS something other than `text` (the rare
    legitimate type-change case), the migration must snapshot every
    spool's value, force-reset, then restore via individual PATCHes."""

    def test_snapshots_then_restores_every_non_empty_value(self, setup_fields_mod):
        # Order matters: GET field schema → GET all spools → DELETE field
        # → POST field → PATCH each spool. Drive the mock through a
        # side_effect that responds based on URL.
        def fake_get(url, *args, **kwargs):
            if "/api/v1/field/spool" in url and url.endswith("/spool"):
                # First call: field listing
                m = MagicMock(status_code=200)
                m.json.return_value = [
                    {"key": "container_slot", "field_type": "integer", "name": "C"},
                ]
                return m
            if url.endswith("/api/v1/spool"):
                # Spool listing
                m = MagicMock(status_code=200)
                m.json.return_value = [
                    {"id": 1, "extra": {"container_slot": '"XL-1"', "other": "x"}},
                    {"id": 2, "extra": {"container_slot": ""}},   # empty — skipped
                    {"id": 3, "extra": {"container_slot": '"DRYER-A:2"'}},
                    {"id": 4, "extra": {}},                        # missing — skipped
                ]
                return m
            return MagicMock(status_code=404)

        del_resp = MagicMock(status_code=200, text="")
        post_resp = MagicMock(status_code=201, text="")
        patch_resps = []

        def fake_patch(url, *args, **kwargs):
            r = MagicMock(ok=True, status_code=200, text="")
            patch_resps.append((url, kwargs.get("json")))
            return r

        with patch.object(setup_fields_mod.requests, "get", side_effect=fake_get), \
             patch.object(setup_fields_mod.requests, "delete", return_value=del_resp), \
             patch.object(setup_fields_mod.requests, "post", return_value=post_resp), \
             patch.object(setup_fields_mod.requests, "patch", side_effect=fake_patch):
            setup_fields_mod.migrate_container_slot_to_text()

        # Two spools had non-empty container_slot values (#1 and #3) →
        # exactly two PATCHes, each restoring the snapshotted value.
        restores = [(url, body) for url, body in patch_resps if "/api/v1/spool/" in url]
        assert len(restores) == 2, f"expected 2 restores, got {len(restores)}: {restores}"
        restored_ids = sorted(int(url.rsplit("/", 1)[-1]) for url, _ in restores)
        assert restored_ids == [1, 3]
        # Every restore PATCH must include the snapshotted container_slot value.
        for url, body in restores:
            sid = int(url.rsplit("/", 1)[-1])
            assert "extra" in body
            assert "container_slot" in body["extra"]
            if sid == 1:
                assert body["extra"]["container_slot"] == '"XL-1"'
            elif sid == 3:
                assert body["extra"]["container_slot"] == '"DRYER-A:2"'

    def test_does_not_attempt_restore_if_snapshot_fails(self, setup_fields_mod):
        """If the spool list fetch fails, the migration must abort BEFORE
        force-resetting (which would wipe values without a snapshot to
        restore from)."""
        call_log = []

        def fake_get(url, *args, **kwargs):
            call_log.append(("GET", url))
            if url.endswith("/api/v1/field/spool"):
                m = MagicMock(status_code=200)
                m.json.return_value = [
                    {"key": "container_slot", "field_type": "integer", "name": "C"},
                ]
                return m
            if url.endswith("/api/v1/spool"):
                m = MagicMock(status_code=500, text="server explosion")
                m.json.return_value = []
                return m
            return MagicMock(status_code=404)

        with patch.object(setup_fields_mod.requests, "get", side_effect=fake_get), \
             patch.object(setup_fields_mod.requests, "delete") as mock_delete, \
             patch.object(setup_fields_mod.requests, "post") as mock_post:
            setup_fields_mod.migrate_container_slot_to_text()

        # Critical: no DELETE was issued — abort happened before destruction.
        mock_delete.assert_not_called()
        mock_post.assert_not_called()


# ---------------------------------------------------------------------------
# create_field error_check parameter — Phase C.3
# ---------------------------------------------------------------------------

class TestCreateFieldErrorCheck:
    def test_raises_on_post_failure_when_error_check_true(self, setup_fields_mod):
        bad_resp = MagicMock(status_code=500, text="server crashed")
        with patch.object(setup_fields_mod.requests, "post", return_value=bad_resp):
            with pytest.raises(RuntimeError) as excinfo:
                setup_fields_mod.create_field(
                    "spool", "container_slot", "X", "text", error_check=True
                )
            assert "500" in str(excinfo.value)

    def test_silent_on_post_failure_when_error_check_false(self, setup_fields_mod):
        """Default behavior preserved — silent failures keep deploys
        going on a flaky Spoolman, matching the pre-Phase-C semantics."""
        bad_resp = MagicMock(status_code=500, text="server crashed")
        with patch.object(setup_fields_mod.requests, "post", return_value=bad_resp):
            # Should not raise.
            setup_fields_mod.create_field(
                "spool", "container_slot", "X", "text"
            )

    def test_silent_on_already_exists_400(self, setup_fields_mod):
        """The 'already exists' 400 is a legitimate idempotent-create
        signal — must NOT raise even when error_check=True."""
        already_resp = MagicMock(status_code=400, text="field already exists")
        with patch.object(setup_fields_mod.requests, "post", return_value=already_resp):
            setup_fields_mod.create_field(
                "spool", "container_slot", "X", "text", error_check=True
            )
