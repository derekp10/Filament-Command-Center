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
  python setup-and-rebuild/migrate_filament_attributes.py

      The script ALWAYS analyzes first (no separate --dry-run flag to
      remember). It prints the plan, asks `yes` to commit, and does
      nothing destructive otherwise. So a casual run is safe — you'll
      see exactly what would change before anything happens.

      Optional flag --auto-yes skips the confirmation prompt for CI /
      scripted use. Don't use that on prod without a backup.

Safety net (Derek 2026-05-16): any choice in `FLAG_CHOICES` that's
ACTUALLY USED by at least one filament in the database is auto-kept
and reported, never deleted. Only zero-usage flagged choices get
promoted to the delete list. `DELETE_CHOICES` keeps the "confirmed
safe — delete regardless" semantics; usage gets logged per-filament
so you can see what got stripped.

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


def main(auto_yes: bool) -> int:
    print(f"[i] Target Spoolman: {SPOOLMAN_IP}")
    print("   Mode: ANALYZE-then-CONFIRM (no writes until you type 'yes')")

    field = _get_field_definition(FIELD_ENTITY, FIELD_KEY)
    if field is None:
        print(f"   [err] Field {FIELD_ENTITY}/{FIELD_KEY} not found on Spoolman. Aborting.")
        return 2

    existing_choices = set(field.get("choices") or [])

    # --- USAGE SCAN drives both the report AND the auto-decision for
    # FLAG_CHOICES (Derek 2026-05-16: keep flagged choices that are in
    # use; auto-promote unused ones into the delete list).
    print("\n[snap] Snapshotting filament_attributes values...")
    filaments = _list_filaments()
    if not filaments:
        return 2
    snapshot: dict[int, list[str]] = {}
    usage: dict[str, list[tuple[int, str]]] = {}   # choice -> [(fid, name), ...]
    name_by_fid: dict[int, str] = {}
    for f in filaments:
        fid = f.get("id")
        if fid is None:
            continue
        name_by_fid[fid] = f.get("name") or "?"
        extra = f.get("extra") or {}
        attrs = _parse_attrs(extra.get(FIELD_KEY))
        if not attrs:
            continue
        snapshot[fid] = attrs
        for a in attrs:
            usage.setdefault(a, []).append((fid, name_by_fid[fid]))
    print(f"   Snapshotted {len(snapshot)} filaments with non-empty attributes.")

    # FLAG_CHOICES auto-decision: kept if any filament uses it; promoted
    # to delete-list if zero usage on this DB. Never silently dropped.
    promoted_from_flag: set[str] = set()
    kept_flagged: dict[str, list[tuple[int, str]]] = {}
    for choice in FLAG_CHOICES:
        if choice not in existing_choices:
            continue
        if choice in usage and usage[choice]:
            kept_flagged[choice] = usage[choice]
        else:
            promoted_from_flag.add(choice)

    effective_delete = (DELETE_CHOICES | promoted_from_flag) & existing_choices

    # --- DISPLAY: every current choice with per-line decision marker
    print(f"\n[list] Current {FIELD_KEY} choices ({len(existing_choices)}):")
    for c in sorted(existing_choices):
        marker = ""
        if c in DELETE_CHOICES:
            n = len(usage.get(c, []))
            marker = f" [del] [DELETE - confirmed safe]" + (f" ({n} filament(s) use it)" if n else "")
        elif c in promoted_from_flag:
            marker = " [del] [DELETE - flagged, but UNUSED on this DB]"
        elif c in kept_flagged:
            marker = f" [keep] [FLAGGED but IN USE - keeping, {len(kept_flagged[c])} filament(s)]"
        print(f"   - {c!r:35s}{marker}")

    missing_in_field = DELETE_CHOICES - existing_choices
    if missing_in_field:
        print(f"\n[i]  Confirmed-safe entries already absent (no-op): {sorted(missing_in_field)}")

    if not effective_delete:
        print("\n[ok] Nothing to delete - every target is either already absent or in use. Done.")
        return 0

    new_choices = sorted(existing_choices - effective_delete)
    print(f"\n[plan] Will delete {len(effective_delete)}: {sorted(effective_delete)}")
    if promoted_from_flag:
        print(f"   Auto-promoted from FLAG (unused on this DB): {sorted(promoted_from_flag)}")
    if kept_flagged:
        print("   KEPT (flagged but in use on this DB):")
        for c, used_by in sorted(kept_flagged.items()):
            preview = ", ".join(f"#{fid} {nm!r}" for fid, nm in used_by[:5])
            tail = f" ... +{len(used_by) - 5} more" if len(used_by) > 5 else ""
            print(f"     - {c!r}: {preview}{tail}")
    print(f"\n   Resulting choice list ({len(new_choices)}):")
    for c in new_choices:
        print(f"     - {c!r}")

    # Per-filament strip preview against the EFFECTIVE delete set.
    affected_by_deletion: list[tuple[int, str, list[str], list[str]]] = []
    for fid, attrs in snapshot.items():
        cleaned = [a for a in attrs if a not in effective_delete]
        if cleaned != attrs:
            affected_by_deletion.append((fid, name_by_fid.get(fid, "?"), attrs, cleaned))
    if affected_by_deletion:
        print(f"\n[edit] {len(affected_by_deletion)} filament(s) will have entries stripped on restore:")
        for fid, name, before, after in affected_by_deletion:
            print(f"   #{fid} {name!r}: {before} -> {after}")
    else:
        print("\n[ok] No filaments use any to-be-deleted choices - restore phase is a no-op.")

    # --- CONFIRMATION ---
    if auto_yes:
        print("\n[warn] --auto-yes passed; proceeding without prompt.")
    else:
        confirm = input("\n[warn] About to force_reset the schema and rebuild. Type 'yes' to commit: ")
        if confirm.strip().lower() != "yes":
            print("Aborted - no changes made.")
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

    # Restore each filament's values (minus the EFFECTIVE delete set —
    # confirmed + auto-promoted-from-flag).
    restored = 0
    failed = 0
    for fid, attrs in snapshot.items():
        cleaned = [a for a in attrs if a not in effective_delete]
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
    parser.add_argument(
        "--auto-yes", action="store_true",
        help="Skip the 'type yes to commit' prompt. Use for scripted runs; "
             "DON'T use on prod without a backup.",
    )
    args = parser.parse_args()
    sys.exit(main(args.auto_yes))
