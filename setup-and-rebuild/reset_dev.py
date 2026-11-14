#!/usr/bin/env python3
"""reset-dev — restore the shared dev backend to a clean, reproducible baseline.

Group 19.1 (Dev-Env Reset & E2E Test-Debt Triage). The pytest+Playwright E2E
suite runs against the SHARED, MUTATING dev backend (Spoolman 7913 +
inventory-hub/data/locations.json), so a full ~986-test sweep contaminates dev
and reruns fail in clusters that have nothing to do with the code under test
(manage-modal won't open, quickswap/locmgr/returns, buffer-card refresh, …).
This script restores dev to a committed seed baseline so the reset can't be
forgotten or done wrong by hand.

WHO RUNS THIS (Derek, 2026-06-02): NOT Derek. This is an *agent-invoked* tool —
Claude runs it on Derek's behalf when asked to reset/clean dev. Derek will not
run it from the CLI, and will **never call `--prune`** ("don't even know how to
anyway"). So `--prune` (the destructive delete-sweep-junk path) only ever fires
when Claude runs it with Derek's explicit OK that session; the accumulated
Pytest-PLA junk stays in dev until then. It's also wired into pytest as an
OPT-IN session step — `pytest --reset-dev` runs the non-destructive restore
before a sweep, `pytest --reset-dev-prune` adds the delete; a flagless run is a
no-op (see inventory-hub/tests/conftest.py).

Two seed artifacts (captured from a known-good dev with `--capture`):
  - setup-and-rebuild/seeds/spoolman-dev-seed.json  (vendors/filaments/spools)
  - setup-and-rebuild/seeds/locations-seed.json      (full FCC locations.json)

PRINTER LOGINS (Group 45.6): a Printer row's `printer_creds` (a PrusaLink IP and
API key) never goes into the seed, which is committed and pushed: `--capture`
drops the key from every row. A restore keeps the live file's `printer_creds`
by LocationID, so resetting dev never wipes the logins it watches the printers
with, and a seed (even an old one that held some) never brings a login back.
A login alone is not drift.

NOTE on the .example stub: data/locations.json.example is the *fresh-install*
bootstrap (6 locations) — NOT a test baseline. Spools reference ~40 distinct
locations, so restoring from the stub would orphan most of them. The test
baseline is the richer locations-seed.json captured here. See the Group 19
triage doc for the full rationale.

Modes
-----
  reset_dev.py                 restore (non-destructive): locations.json <- seed;
                               PATCH drifted spool/filament/vendor fields back to
                               seed values (idempotent); docker restart.
  reset_dev.py --prune         also DELETE entities created during a sweep
                               (present in dev but absent from the seed).
  reset_dev.py --capture       snapshot CURRENT dev -> the two seed files.
  reset_dev.py --dry-run       report what WOULD change; write nothing.
  reset_dev.py --no-restart    skip the `docker restart inventory_hub` step.
  reset_dev.py --no-locations  skip the locations.json restore.
  reset_dev.py --no-spoolman   skip the Spoolman reconcile.

Runs on the HOST (not inside the container): it must orchestrate a
`docker restart` and rewrite the bind-mounted locations.json, and it reaches
dev Spoolman directly at DEV_SPOOLMAN_URL (default http://192.168.1.29:7913).

Env overrides: DEV_SPOOLMAN_URL, INVENTORY_HUB_CONTAINER (default inventory_hub).

Idempotent: a restore immediately after a clean restore makes zero writes.
Limitation: Spoolman assigns ids on create, so an entity a sweep *deleted*
cannot be restored with its original id. Such entities are REPORTED (not
silently recreated) so they don't break idempotency; recover real deleted data
with a Spoolman backup restore instead. In practice sweeps corrupt
location/extra/archived/weight on existing spools — all fully PATCH-restorable.
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import re
import subprocess
import sys
import tempfile

import requests

# --------------------------------------------------------------------------
# Paths & config
# --------------------------------------------------------------------------
HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
SEEDS_DIR = os.path.join(HERE, "seeds")
SPOOLMAN_SEED = os.path.join(SEEDS_DIR, "spoolman-dev-seed.json")
LOCATIONS_SEED = os.path.join(SEEDS_DIR, "locations-seed.json")
LIVE_LOCATIONS = os.path.join(REPO_ROOT, "inventory-hub", "data", "locations.json")

SPOOLMAN_URL = os.environ.get("DEV_SPOOLMAN_URL", "http://192.168.1.29:7913").rstrip("/")
CONTAINER = os.environ.get("INVENTORY_HUB_CONTAINER", "inventory_hub")
TIMEOUT = 15

# Fields restored per entity when they drift from the seed. `extra` is handled
# specially (whole-dict compare, then the seed's whole dict is sent back). Up to
# Spoolman 0.25 a filament's and a vendor's PATCH REPLACED the entire extra dict,
# which for a *reset* is exactly what we want; a spool's has merged key by key
# since 0.22, and every entity's since 0.26, so a key a sweep ADDED is also sent
# as null, which drops it (_drifted_payload; 2026-10-21).
RESTORE_FIELDS = {
    # The big contamination targets. location/archived/extra cover
    # quickswap/locmgr/returns/buffer drift + the volatile extras
    # (container_slot, physical_source*, needs_label_print, is_refill,
    # fcc_pre_archive_location); the weight triple covers weigh-out/deduct.
    "spool": ["location", "archived", "initial_weight", "spool_weight",
              "used_weight", "lot_nr", "comment", "extra"],
    # extra carries filament_attributes (the L319/L58 cleanup contamination);
    # the scalars cover edit-modal / wizard mutations.
    "filament": ["name", "material", "price", "density", "diameter", "weight",
                 "spool_weight", "comment", "settings_extruder_temp",
                 "settings_bed_temp", "color_hex", "multi_color_hexes",
                 "multi_color_direction", "external_id", "extra"],
    "vendor": ["name", "comment", "empty_spool_weight", "external_id", "extra"],
}
ENTITY_PLURAL = {"vendor": "vendors", "filament": "filaments", "spool": "spools"}
# Restore order (FK-safe): vendors before filaments before spools.
RESTORE_ORDER = ["vendor", "filament", "spool"]
# Prune (delete) order (reverse FK): spools before filaments before vendors.
PRUNE_ORDER = ["spool", "filament", "vendor"]

_FLOAT_EPS = 1e-4

# Whether this Spoolman takes a JSON null for an extra (0.26 or newer), which is
# how a key the seed doesn't have is dropped from a record whose PATCH merges
# `extra` key by key. Dev runs 0.27; _check_spoolman_reachable sets it from the
# version Spoolman reports (an older one is a 422 for the whole PATCH on a null,
# and replaces a filament's / vendor's extra anyway).
NULL_CLEARS = True
_NULL_CLEARS_FROM = (0, 26, 0)

# A Printer row's PrusaLink login (locations_db.PRINTER_CREDS_KEY). Never written
# into the seed, and never taken from it (see the module docstring).
PRINTER_CREDS_KEY = "printer_creds"


# --------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------
def _log(msg: str) -> None:
    print(msg, flush=True)


def _get(path: str):
    r = requests.get(f"{SPOOLMAN_URL}{path}", timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()


def _values_equal(a, b) -> bool:
    """Drift comparison that ignores float noise and treats None/'' the same
    only for scalars we know Spoolman normalizes."""
    if isinstance(a, dict) or isinstance(b, dict):
        return (a or {}) == (b or {})
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(float(a) - float(b)) < _FLOAT_EPS
    return a == b


def _null_clears_for(version) -> bool:
    """True for a Spoolman version (e.g. "0.27.0") that takes a JSON null for an
    extra; an unreadable version is taken as one that does (dev runs 0.27)."""
    nums = [int(n) for n in re.findall(r"\d+", str(version or ""))][:3]
    if len(nums) < 2:
        return True
    return tuple(nums + [0] * (3 - len(nums))) >= _NULL_CLEARS_FROM


def _location_key(row) -> str:
    return str(row.get("LocationID") or "").strip().upper() if isinstance(row, dict) else ""


def _strip_printer_creds(rows: list) -> tuple:
    """A copy of a locations list with no `printer_creds` on any row, and the
    LocationIDs that had one (names only: a login's value is never logged)."""
    out, stripped = [], []
    for row in rows:
        if isinstance(row, dict) and PRINTER_CREDS_KEY in row:
            stripped.append(str(row.get("LocationID") or "?"))
            row = {k: v for k, v in row.items() if k != PRINTER_CREDS_KEY}
        out.append(row)
    return out, stripped


def _with_live_printer_creds(seed_rows: list, live_rows) -> tuple:
    """The seed's rows, each carrying the live file's `printer_creds` for the same
    LocationID (compared trimmed and case-blind), and none taken from the seed.

    Returns (rows, kept, lost): the LocationIDs whose live login was kept, and
    those whose live login has no row in the seed (it goes with the row)."""
    live = {}
    for row in live_rows if isinstance(live_rows, list) else []:
        key = _location_key(row)
        if key and PRINTER_CREDS_KEY in row and key not in live:
            live[key] = row[PRINTER_CREDS_KEY]
    rows, kept, seed_keys = [], [], set()
    for row in seed_rows:
        if not isinstance(row, dict):
            rows.append(row)
            continue
        key = _location_key(row)
        seed_keys.add(key)
        new = {}
        for k, v in row.items():
            if k == PRINTER_CREDS_KEY:     # an old seed's login is never restored
                if key in live:
                    new[k] = copy.deepcopy(live[key])
                continue
            new[k] = v
        if key in live and PRINTER_CREDS_KEY not in new:
            new[PRINTER_CREDS_KEY] = copy.deepcopy(live[key])
        if key in live:
            kept.append(str(row.get("LocationID")))
        rows.append(new)
    lost = sorted(k for k in live if k not in seed_keys)
    return rows, kept, lost


def _check_spoolman_reachable() -> None:
    global NULL_CLEARS
    try:
        info = _get("/api/v1/info")
        _log(f"  Spoolman {info.get('version', '?')} @ {SPOOLMAN_URL} ({info.get('db_type', '?')})")
    except Exception as e:  # noqa: BLE001
        _log(f"!! Cannot reach dev Spoolman at {SPOOLMAN_URL}: {e}")
        _log("   Set DEV_SPOOLMAN_URL or check the NAS is up. Aborting.")
        sys.exit(2)
    NULL_CLEARS = _null_clears_for(info.get("version"))
    if not NULL_CLEARS:
        _log("  (a Spoolman older than 0.26: extras a sweep added are left out of the "
             "restore, which drops them from a filament or vendor but not from a spool)")


# --------------------------------------------------------------------------
# Capture
# --------------------------------------------------------------------------
def capture() -> None:
    """Snapshot current dev Spoolman + locations.json into the seed files."""
    _check_spoolman_reachable()
    _log("Capturing dev baseline -> seeds/ ...")

    vendors = _get("/api/v1/vendor")
    filaments_raw = _get("/api/v1/filament")
    spools_raw = _get("/api/v1/spool")

    # De-nest FKs so the seed isn't 280 redundant copies of filament+vendor.
    filaments = []
    for f in filaments_raw:
        f = dict(f)
        f["vendor_id"] = (f.get("vendor") or {}).get("id")
        f.pop("vendor", None)
        filaments.append(f)
    spools = []
    for s in spools_raw:
        s = dict(s)
        s["filament_id"] = (s.get("filament") or {}).get("id")
        s.pop("filament", None)
        spools.append(s)

    seed = {
        "_note": "Group 19.1 reset-dev baseline. Snapshot of dev Spoolman. "
                 "Re-capture with `python reset_dev.py --capture` from a known-good dev.",
        "spoolman_url": SPOOLMAN_URL,
        "counts": {"vendors": len(vendors), "filaments": len(filaments), "spools": len(spools)},
        "vendors": vendors,
        "filaments": filaments,
        "spools": spools,
    }
    os.makedirs(SEEDS_DIR, exist_ok=True)
    _atomic_write(SPOOLMAN_SEED, json.dumps(seed, indent=2, ensure_ascii=False))
    _log(f"  wrote {SPOOLMAN_SEED}  ({len(vendors)} vendors / {len(filaments)} filaments / {len(spools)} spools)")

    # locations.json snapshot (the full test baseline, not the .example stub),
    # with every printer login left out: the seed is committed and pushed. It is
    # written the way locations_db writes the live file (json.dump, indent 4,
    # ASCII), so apart from the logins it is the live text.
    if os.path.exists(LIVE_LOCATIONS):
        with open(LIVE_LOCATIONS, "r", encoding="utf-8") as fh:
            locs = fh.read()
        try:
            rows = json.loads(locs)
        except ValueError as e:
            rows = None
            _log(f"  !! {LIVE_LOCATIONS} doesn't parse ({e}); skipped the locations snapshot, "
                 "because its printer logins can't be left out of text that doesn't parse")
        if rows is not None and not isinstance(rows, list):
            rows = None
            _log(f"  !! {LIVE_LOCATIONS} isn't a list; skipped the locations snapshot")
        if rows is not None:
            seed_rows, stripped = _strip_printer_creds(rows)
            _atomic_write(LOCATIONS_SEED, json.dumps(seed_rows, indent=4))
            note = f"; printer logins left out of {', '.join(stripped)}" if stripped else ""
            _log(f"  wrote {LOCATIONS_SEED}  ({len(seed_rows)} locations{note})")
    else:
        _log(f"  !! {LIVE_LOCATIONS} not found — skipped locations snapshot")
    _log("Capture complete.")


def _atomic_write(path: str, text: str) -> None:
    d = os.path.dirname(path)
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".tmp-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


# --------------------------------------------------------------------------
# Restore
# --------------------------------------------------------------------------
def _load_seed() -> dict:
    if not os.path.exists(SPOOLMAN_SEED):
        _log(f"!! No seed at {SPOOLMAN_SEED}. Run `python reset_dev.py --capture` first.")
        sys.exit(2)
    with open(SPOOLMAN_SEED, "r", encoding="utf-8") as fh:
        return json.load(fh)


def restore_locations(dry_run: bool) -> None:
    """Put the seed's rows back, keeping the live file's printer logins by LocationID."""
    if not os.path.exists(LOCATIONS_SEED):
        _log(f"  !! No locations seed at {LOCATIONS_SEED} — skipping locations restore.")
        return
    with open(LOCATIONS_SEED, "r", encoding="utf-8") as fh:
        seed_text = fh.read()
    try:
        seed_rows = json.loads(seed_text)
    except ValueError as e:
        _log(f"  !! The locations seed doesn't parse ({e}) — skipping locations restore.")
        return
    if not isinstance(seed_rows, list):
        _log("  !! The locations seed isn't a list — skipping locations restore.")
        return
    current = None
    if os.path.exists(LIVE_LOCATIONS):
        with open(LIVE_LOCATIONS, "r", encoding="utf-8") as fh:
            current_text = fh.read()
        try:
            current = json.loads(current_text)
        except ValueError:
            _log("  locations.json doesn't parse, so no printer login can be kept from it.")
    # Compare parsed JSON so whitespace-only diffs don't trigger a rewrite. A login
    # alone is no drift: the restored rows carry the live logins.
    restored, kept, lost = _with_live_printer_creds(seed_rows, current)
    if restored == current:
        _log("  locations.json: already matches seed (no change).")
        return
    note = f" (keeping the printer logins of {', '.join(kept)})" if kept else ""
    if lost:
        note += f"; the seed has no row for {', '.join(lost)}, so their logins go with them"
    if dry_run:
        _log(f"  locations.json: WOULD restore from seed{note}.")
        return
    _atomic_write(LIVE_LOCATIONS, json.dumps(restored, indent=4))
    _log(f"  locations.json: restored from seed{note}.")


def _patch(entity: str, eid, payload: dict) -> tuple[bool, str]:
    url = f"{SPOOLMAN_URL}/api/v1/{entity}/{eid}"
    try:
        r = requests.patch(url, json=payload, timeout=TIMEOUT)
        if r.ok:
            return True, ""
        return False, f"HTTP {r.status_code} {(r.text or '')[:160]}"
    except Exception as e:  # noqa: BLE001
        return False, str(e)


def _delete(entity: str, eid) -> tuple[bool, str]:
    url = f"{SPOOLMAN_URL}/api/v1/{entity}/{eid}"
    try:
        r = requests.delete(url, timeout=TIMEOUT)
        if r.ok:
            return True, ""
        return False, f"HTTP {r.status_code} {(r.text or '')[:160]}"
    except Exception as e:  # noqa: BLE001
        return False, str(e)


def _drifted_payload(entity: str, seed_rec: dict, live_rec: dict) -> dict:
    """Return only the fields whose live value differs from the seed.

    A drifted `extra` goes back as the seed's whole dict, plus null for every key
    the live record has and the seed doesn't (NULL_CLEARS): Spoolman 0.26+ merges
    a PATCH's extra key by key, so a key left out of it is KEPT, and a stray
    container_slot / physical_source(_slot) / fcc_pre_box_location a sweep left
    kept claiming a slot (and the next run found the same drift again)."""
    payload = {}
    for field in RESTORE_FIELDS[entity]:
        seed_val = seed_rec.get(field)
        live_val = live_rec.get(field)
        if field == "extra":
            if (seed_val or {}) != (live_val or {}):
                restored = dict(seed_val or {})
                if NULL_CLEARS:
                    for key in (live_val or {}):
                        if key not in restored:
                            restored[key] = None
                payload["extra"] = restored
            continue
        if not _values_equal(seed_val, live_val):
            payload[field] = seed_val
    return payload


def reconcile_entity(entity: str, seed_records: list, dry_run: bool, prune: bool,
                     summary: dict) -> None:
    plural = ENTITY_PLURAL[entity]
    seed_by_id = {r["id"]: r for r in seed_records if r.get("id") is not None}
    live = _get(f"/api/v1/{entity}")
    live_by_id = {r["id"]: r for r in live}

    s = summary[plural]
    # 1. PATCH drifted fields back on entities present in both.
    for eid, seed_rec in seed_by_id.items():
        live_rec = live_by_id.get(eid)
        if live_rec is None:
            s["missing"].append(eid)
            continue
        payload = _drifted_payload(entity, seed_rec, live_rec)
        if not payload:
            continue
        s["drifted"] += 1
        s["fields"][eid] = sorted(payload.keys())
        if dry_run:
            continue
        ok, err = _patch(entity, eid, payload)
        if ok:
            s["restored"] += 1
        else:
            s["errors"].append(f"{entity} {eid}: {err}")

    # 2. Extra entities (present in dev, absent from seed) = sweep-created.
    extras = [eid for eid in live_by_id if eid not in seed_by_id]
    s["extra"] = list(extras)
    if prune and extras:
        for eid in extras:
            if dry_run:
                s["pruned_would"] += 1
                continue
            ok, err = _delete(entity, eid)
            if ok:
                s["pruned"] += 1
            else:
                s["errors"].append(f"delete {entity} {eid}: {err}")


def restore(dry_run: bool, prune: bool, do_locations: bool, do_spoolman: bool,
            do_restart: bool) -> int:
    _log(f"reset-dev {'(DRY RUN) ' if dry_run else ''}-> baseline restore")
    _log("")

    if do_locations:
        _log("locations.json:")
        restore_locations(dry_run)
        _log("")

    summary = {
        plural: {"drifted": 0, "restored": 0, "missing": [], "extra": [],
                 "pruned": 0, "pruned_would": 0, "fields": {}, "errors": []}
        for plural in ENTITY_PLURAL.values()
    }

    if do_spoolman:
        _check_spoolman_reachable()
        seed = _load_seed()
        _log("Spoolman reconcile (PATCH drifted fields back to seed):")
        # Restore FK-parents first; prune happens per-entity but we delete in
        # reverse-FK order so spools are gone before their filaments.
        for entity in (PRUNE_ORDER if prune else RESTORE_ORDER):
            reconcile_entity(entity, seed.get(ENTITY_PLURAL[entity], []),
                             dry_run, prune, summary)
        _print_summary(summary, dry_run, prune)
        _log("")

    total_errors = sum(len(summary[p]["errors"]) for p in summary)

    if do_restart and not dry_run:
        _log(f"Restarting container '{CONTAINER}' to clear in-memory state ...")
        try:
            subprocess.run(["docker", "restart", CONTAINER], check=True,
                           capture_output=True, text=True, timeout=120)
            _log(f"  {CONTAINER} restarted.")
        except Exception as e:  # noqa: BLE001
            _log(f"  !! docker restart failed: {e}")
            total_errors += 1
    elif do_restart:
        _log(f"(dry-run) WOULD `docker restart {CONTAINER}`")

    _log("")
    _log("reset-dev complete." if total_errors == 0 else f"reset-dev finished with {total_errors} error(s).")
    return 0 if total_errors == 0 else 1


def _print_summary(summary: dict, dry_run: bool, prune: bool) -> None:
    verb = "would restore" if dry_run else "restored"
    for plural in ("vendors", "filaments", "spools"):
        s = summary[plural]
        bits = [f"{s['drifted']} drifted ({verb} {s['restored'] if not dry_run else s['drifted']})"]
        if s["missing"]:
            bits.append(f"{len(s['missing'])} missing (deleted — not recreated)")
        if s["extra"]:
            if prune:
                pv = s["pruned_would"] if dry_run else s["pruned"]
                bits.append(f"{len(s['extra'])} sweep-created ({'would prune' if dry_run else 'pruned'} {pv})")
            else:
                bits.append(f"{len(s['extra'])} sweep-created (left; use --prune)")
        if s["errors"]:
            bits.append(f"{len(s['errors'])} ERROR(s)")
        _log(f"  {plural:9s}: " + ", ".join(bits))
        for e in s["errors"][:10]:
            _log(f"             - {e}")
    if any(summary[p]["missing"] for p in summary):
        _log("  NOTE: 'missing' = seed entities a sweep deleted. Spoolman can't "
             "re-create them with their original id; recover via a Spoolman backup if needed.")


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser(
        prog="reset_dev.py",
        description="Restore the shared dev backend to a clean seed baseline (Group 19.1).",
    )
    ap.add_argument("--capture", action="store_true",
                    help="Snapshot CURRENT dev Spoolman + locations.json into seeds/.")
    ap.add_argument("--prune", action="store_true",
                    help="Also DELETE entities created during a sweep (absent from "
                         "seed). DESTRUCTIVE + agent-invoked only — Derek never calls "
                         "this; Claude runs it with Derek's explicit OK. See header.")
    ap.add_argument("--dry-run", action="store_true",
                    help="Report what would change; write nothing.")
    ap.add_argument("--no-restart", action="store_true",
                    help="Skip `docker restart inventory_hub`.")
    ap.add_argument("--no-locations", action="store_true",
                    help="Skip the locations.json restore.")
    ap.add_argument("--no-spoolman", action="store_true",
                    help="Skip the Spoolman reconcile.")
    args = ap.parse_args()

    if args.capture:
        if args.dry_run:
            _log("--capture and --dry-run are mutually exclusive.")
            return 2
        capture()
        return 0

    return restore(
        dry_run=args.dry_run,
        prune=args.prune,
        do_locations=not args.no_locations,
        do_spoolman=not args.no_spoolman,
        do_restart=not args.no_restart,
    )


if __name__ == "__main__":
    sys.exit(main())
