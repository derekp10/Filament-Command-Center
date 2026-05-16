"""Filament Attributes choice cleanup migration.

Spoolman's API rejects choice removal via POST (`400 "Cannot remove
existing choices."`), so removing dead/duplicate dropdown entries
requires the snapshot → force_reset → recreate → restore pattern that
`migrate_container_slot_to_text` pioneered.

Confirmed-safe deletions (Derek 2026-04-28):
  - `Carbon-Fiber`   duplicate of `Carbon Fiber`
  - `Tran`           truncated typo
  - `Transparent; High-Speed`  semicolon-bogus
  - `Wood`           superseded by `Wood Filled`
  - `F`              typo

Kept:
  - `+`              intentional PLA+ marker (e.g. Filament #132 Creality Rainbow)

Pending Derek's prod investigation (NOT touched by this script - will
print a warning if found in use):
  - `For Infill`     was used to flag color-switch / prototype-only filaments
                     not meant for visible prints. Derek isn't sure whether
                     he still uses this flag or has a different mechanism.
                     Script prints which filaments use it so he can decide.
  - `Matte Pro`      likely orphaned from a prior wipe-and-replace; Derek
                     wants to confirm origin before deleting.

Generalizable: the `DELETE_CHOICES` set at the top is the only thing
to edit for future cleanup runs against `filament_attributes` or any
other choice-type extras field. The snapshot → force_reset → restore
flow is the same for every such migration.

Usage:
  python setup-and-rebuild/migrate_filament_attributes.py --dry-run
      Walks the field, lists deletions + flagged choices, shows what
      would be restored. No writes.

  python setup-and-rebuild/migrate_filament_attributes.py
      Performs the migration. Snapshots all filaments' filament_attributes
      values, force_reset the field, recreates with the cleaned choice
      list, and restores the snapshotted values (with deleted-choice
      entries stripped out per record).

Prereqs:
  - The target Spoolman instance pointed at by config.json must be
    reachable. The script targets whichever URL config_loader.get_api_urls()
    returns - this is dev by default. For prod, point your shell at the
    prod config.json before running.
  - BACKUP YOUR SPOOLMAN DB BEFORE RUNNING WITHOUT --dry-run. Spoolman's
    field DELETE is destructive at the schema level.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

import requests

# Reuse setup_fields.py's plumbing for the create_field + _get_field_definition
# helpers. Same import shape so the SPOOLMAN_IP / config_loader path resolution
# stays in one place.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'inventory-hub')))
import config_loader  # noqa: E402

SPOOLMAN_IP, _ = config_loader.get_api_urls()


# -------- Customize this block for future similar cleanups --------------------
DELETE_CHOICES = {
    "Carbon-Fiber",            # dupe of "Carbon Fiber"
    "Tran",                    # truncated
    "Transparent; High-Speed", # semicolon-bogus
    "Wood",                    # superseded by "Wood Filled"
    "F",                       # typo
}
FLAG_CHOICES = {
    "For Infill",   # Derek to confirm against prod whether this flag is in use
    "Matte Pro",    # Derek wants to confirm origin before deleting
}
FIELD_ENTITY = "filament"
FIELD_KEY = "filament_attributes"
FIELD_NAME = "Filament Attributes"
# ------------------------------------------------------------------------------


def _get_field_definition(entity_type: str, key: str) -> dict[str, Any] | None:
    try:
        r = requests.get(f"{SPOOLMAN_IP}/api/v1/field/{entity_type}", timeout=10)
        if not r.ok:
            return None
        for f in r.json() or []:
            if f.get("key") == key:
                return f
    except requests.RequestException as e:
        print(f"   [warn]  Network error fetching field def: {e}")
    return None


def _parse_attrs(raw: Any) -> list[str]:
    """filament_attributes is stored as a JSON-encoded string list, e.g. `'["+", "Silk"]'`.
    Be tolerant of both wire-form and python-list inputs (Spoolman has
    historically round-tripped one or the other depending on version)."""
    if raw is None or raw == "":
        return []
    if isinstance(raw, list):
        return [str(x) for x in raw]
    if isinstance(raw, str):
        # Try JSON first; fall back to a single bare string.
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return [str(x) for x in parsed]
            return [str(parsed)]
        except (ValueError, TypeError):
            return [raw]
    return []


def _list_filaments() -> list[dict[str, Any]]:
    try:
        r = requests.get(f"{SPOOLMAN_IP}/api/v1/filament", timeout=20)
        if not r.ok:
            print(f"   [err] Could not list filaments ({r.status_code}); aborting.")
            return []
        return r.json() or []
    except requests.RequestException as e:
        print(f"   [err] Network error listing filaments: {e}")
        return []


def main(dry_run: bool) -> int:
    print(f"[i] Target Spoolman: {SPOOLMAN_IP}")
    print(f"   Mode: {'DRY-RUN (no writes)' if dry_run else 'LIVE (will write)'}")

    field = _get_field_definition(FIELD_ENTITY, FIELD_KEY)
    if field is None:
        print(f"   [err] Field {FIELD_ENTITY}/{FIELD_KEY} not found on Spoolman. Aborting.")
        return 2

    existing_choices = set(field.get("choices") or [])
    print(f"\n[list] Current {FIELD_KEY} choices ({len(existing_choices)}):")
    for c in sorted(existing_choices):
        marker = " [del]  [DELETE]" if c in DELETE_CHOICES else (" [warn]  [FLAGGED - investigating]" if c in FLAG_CHOICES else "")
        print(f"   - {c!r}{marker}")

    will_delete = DELETE_CHOICES & existing_choices
    missing_in_field = DELETE_CHOICES - existing_choices
    if missing_in_field:
        print(f"\n[i]  Already absent from field (no-op): {sorted(missing_in_field)}")
    if not will_delete:
        print("\n[ok] Nothing to delete - every target choice is already absent. Done.")
        return 0

    new_choices = sorted(existing_choices - DELETE_CHOICES)
    print(f"\n[plan] Will delete {len(will_delete)}: {sorted(will_delete)}")
    print(f"   Resulting choice list ({len(new_choices)}): {new_choices}")

    # Snapshot which filaments use the deleted choices so the user can
    # eyeball before committing. Also flag any usage of FLAG_CHOICES.
    print("\n[snap] Snapshotting filament_attributes values...")
    filaments = _list_filaments()
    if not filaments:
        return 2
    snapshot: dict[int, list[str]] = {}
    affected_by_deletion: list[tuple[int, str, list[str], list[str]]] = []  # (fid, name, before, after)
    flagged_usage: list[tuple[int, str, list[str]]] = []

    for f in filaments:
        fid = f.get("id")
        if fid is None:
            continue
        extra = f.get("extra") or {}
        attrs = _parse_attrs(extra.get(FIELD_KEY))
        if not attrs:
            continue
        snapshot[fid] = attrs
        cleaned = [a for a in attrs if a not in DELETE_CHOICES]
        if cleaned != attrs:
            affected_by_deletion.append((fid, f.get("name") or "?", attrs, cleaned))
        used_flags = [a for a in attrs if a in FLAG_CHOICES]
        if used_flags:
            flagged_usage.append((fid, f.get("name") or "?", used_flags))

    print(f"   Snapshotted {len(snapshot)} filaments with non-empty attributes.")
    if affected_by_deletion:
        print(f"\n[edit]  {len(affected_by_deletion)} filament(s) will have entries stripped:")
        for fid, name, before, after in affected_by_deletion:
            print(f"   #{fid} {name!r}: {before} → {after}")
    if flagged_usage:
        print(f"\n[warn]  {len(flagged_usage)} filament(s) currently use FLAGGED choices "
              f"(NOT deleted - Derek to investigate):")
        for fid, name, used in flagged_usage:
            print(f"   #{fid} {name!r}: uses {used}")
    else:
        print("\n[i]  No filaments currently use any FLAGGED choices. Safe to delete those next "
              "round if Derek confirms.")

    if dry_run:
        print("\n[dry]  DRY-RUN complete. Re-run without --dry-run to commit.")
        return 0

    # --- LIVE PATH ---
    confirm = input("\n[warn]  About to force_reset the schema and rebuild. Type 'yes' to proceed: ")
    if confirm.strip().lower() != "yes":
        print("Aborted.")
        return 1

    # Force-reset the field with the new choice list.
    try:
        r_del = requests.delete(f"{SPOOLMAN_IP}/api/v1/field/{FIELD_ENTITY}/{FIELD_KEY}", timeout=15)
        if not r_del.ok and r_del.status_code != 404:
            print(f"   [err] Field DELETE failed ({r_del.status_code}): {r_del.text[:300]}")
            print("   Snapshot still in memory; no values changed on disk. Aborting.")
            return 2
    except requests.RequestException as e:
        print(f"   [err] Field DELETE network error: {e}; aborting.")
        return 2

    try:
        r_create = requests.post(
            f"{SPOOLMAN_IP}/api/v1/field/{FIELD_ENTITY}/{FIELD_KEY}",
            json={
                "name": FIELD_NAME,
                "field_type": "choice",
                "multi_choice": True,
                "choices": new_choices,
            },
            timeout=15,
        )
        if not r_create.ok:
            print(f"   [err] Field POST failed ({r_create.status_code}): {r_create.text[:300]}")
            print("   [err] Field is now DELETED but new schema didn't land. Manual cleanup needed.")
            return 2
    except requests.RequestException as e:
        print(f"   [err] Field POST network error: {e}; field may be in DELETED state.")
        return 2

    print(f"   [ok] Field rebuilt with {len(new_choices)} cleaned choices.")

    # Restore each filament's values (minus the deleted choices).
    restored = 0
    failed = 0
    for fid, attrs in snapshot.items():
        cleaned = [a for a in attrs if a not in DELETE_CHOICES]
        if cleaned == attrs:
            # Unchanged - Spoolman likely preserved it across the rebuild,
            # but writing explicitly is cheap and idempotent.
            pass
        try:
            r = requests.patch(
                f"{SPOOLMAN_IP}/api/v1/filament/{fid}",
                json={"extra": {FIELD_KEY: json.dumps(cleaned)}},
                timeout=10,
            )
            if r.ok:
                restored += 1
            else:
                failed += 1
                print(f"   [warn]  Restore failed for filament #{fid}: {r.status_code} {r.text[:200]}")
        except requests.RequestException as e:
            failed += 1
            print(f"   [warn]  Network error restoring filament #{fid}: {e}")

    print(f"\n[ok] Migration complete: {restored} restored, {failed} failed.")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would change without writing.")
    args = parser.parse_args()
    sys.exit(main(args.dry_run))
