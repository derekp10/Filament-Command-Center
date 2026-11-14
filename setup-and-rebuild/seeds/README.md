# The reset-dev snapshot (kept on one PC)

`setup-and-rebuild/reset_dev.py` puts dev back to a snapshot. The snapshot is two files in
`setup-and-rebuild/seeds/local/`:

- `spoolman-dev-seed.json`: dev Spoolman's vendors, filaments and spools, archived spools included.
- `locations-seed.json`: dev FCC's `inventory-hub/data/locations.json`, with every printer login left out.

## Where it lives

The snapshot lives only on the PC that made it, in `seeds/local/`, and git ignores that folder.
Since 2026-11-13 dev's data is a copy of prod's, so the snapshot is a copy of the real inventory
(names, prices, purchase links, comments), and the GitHub repo is public.

No commit has ever tracked `seeds/local/`, so checking out another branch (`main`, or a hotfix
branch cut from it) can't overwrite the snapshot or delete it. The folder also ignores itself: it
holds a `.gitignore` of its own (`reset_dev.py --capture` writes it) that ignores everything in it,
so it stays out of git even on a branch whose top-level `.gitignore` doesn't name it yet.
`git clean -xd` (e.g. `git clean -xdf`) would delete it, as it deletes ignored folders.

## What git history still holds

Until 2026-11-13 git tracked two older snapshots at `seeds/spoolman-dev-seed.json` and
`seeds/locations-seed.json`. They were removed from the tree that day, but git history still holds
them, and they carry most of the same records: all 37 of the last one's vendor names and 147 of its
148 filaments (by name and material) are in today's snapshot, and it holds 65 spool prices. Taking
the files out of git stops new copies; it doesn't take back what is already public. Derek decided
(2026-11-13) that this is fine, and wants no history rewrite.

## How to make it

From the repo root, against a dev you know is in a good state:

```
python setup-and-rebuild/reset_dev.py --capture
python setup-and-rebuild/reset_dev.py --dry-run --no-restart
```

The dry run right after a capture should report no drift. After a refresh from prod,
`setup-and-rebuild/refresh_dev_from_prod.py seeds --apply` does both and checks the result.

The capture never writes a printer login (`printer_creds`). A restore keeps the logins dev's own
`locations.json` holds.

## Without it

A fresh clone, or a PC that never made a snapshot, has none. Until one is made:

- `reset_dev.py` (a restore, a dry run, and `pytest --reset-dev`) stops with a message saying so,
  before it reads or changes anything;
- `tests/test_box_binding_loans.py::test_baselines_match_the_reset_dev_seed` skips, saying why.

## What uses it

- `setup-and-rebuild/reset_dev.py`: restores dev to it (`pytest --reset-dev` runs the same restore
  before a sweep).
- `setup-and-rebuild/refresh_dev_from_prod.py`: its `seeds` phase retakes and checks it; its
  `locations` phase reads `locations-seed.json` for a test box or test cart that neither prod's nor
  dev's file has.
- `inventory-hub/tests/test_box_binding_loans.py`: checks that `conftest.DEV_BOX_BINDING_BASELINES`
  matches the test boxes in `locations-seed.json`.

Before you refresh dev from prod, copy `seeds/local/` somewhere if you may want the old snapshot
back: git won't have the snapshot you replace (its history has only the copies from before
2026-11-13).
