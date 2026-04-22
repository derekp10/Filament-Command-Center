# `inventory-hub/data/` — runtime state

Everything in this directory (except this README and `locations.json.example`)
is **runtime state owned by a live install**. Files here are written by the
running app and must never be committed to the repo.

## Why this exists

During feature development, contributors kept accidentally committing
updated `locations.json` files into the repo. Every `git pull` on a
production install then overwrote the live bindings, occasionally clobbered
`container_slot` values on real spools, and caused cascading "dryerbox
weirdness" reports. The containing repo is a single source tree shared
between dev and prod, so there's no second mount point protecting prod.

Moving runtime state under `data/` lets one `.gitignore` rule blanket-ignore
everything here except the intentional seed + this doc, which is a stronger
guarantee than trying to remember to ignore individual files.

## Files you'll see here at runtime

| File | Purpose | Created by |
|---|---|---|
| `locations.json` | Canonical list of locations + per-slot `slot_targets` bindings | Written by `locations_db.py` whenever a location is added/edited or a Dryer Box binding changes |
| `locations.json.pre-feedermap-migration-*.bak` | Backup taken once, before the legacy `config.json:feeder_map` → `slot_targets` migration runs on first boot | Written by `app.py` startup the first time a non-empty `feeder_map` is seen |
| `filabridge_error_snapshots.json` | Cached Filabridge error snapshot store (ID → spool snapshot data) for the error-recovery flow | Written by the Filabridge error-recovery routines in `app.py` |

None of these should ever appear in `git status` as "modified" or "new."
The root `.gitignore` has the pattern:

```
inventory-hub/data/*
!inventory-hub/data/README.md
!inventory-hub/data/locations.json.example
```

If you see one of these files being staged for commit, something went
wrong — probably a .gitignore line got removed. The pre-commit hook
in `.githooks/pre-commit` will also refuse commits under this directory
for the same reason, if you've opted into `core.hooksPath .githooks`.

## Bootstrap / migration

- **Fresh install** (no `locations.json`, no CSV): `load_locations_list()`
  returns `[]`. First location add creates `data/locations.json`.
- **Install with legacy CSV**: `_ensure_json_migration()` reads
  `3D Print Supplies - Locations.csv` and writes `data/locations.json`,
  then renames the CSV to `_BACKUP.csv`.
- **Install upgrading from pre-`data/` layout**: `_ensure_runtime_migration()`
  moves `inventory-hub/locations.json` → `inventory-hub/data/locations.json`
  on first boot after the update. Logs a single "📦 Migrated runtime state"
  line so the operator can confirm.

## Seed file

`locations.json.example` holds one representative record per location
`Type` (Dryer Box, Tool Head, MMU Slot, Room, Cart, Shelf, Sliding Drawer,
No MMU Direct Load). Copy/rename it as `locations.json` and edit to bootstrap
a fresh install manually without going through the CSV path.
