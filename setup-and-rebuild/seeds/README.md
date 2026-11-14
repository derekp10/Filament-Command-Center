# The reset-dev snapshot (local files)

This folder holds the snapshot that `setup-and-rebuild/reset_dev.py` puts dev back to:

- `spoolman-dev-seed.json`: dev Spoolman's vendors, filaments and spools, archived spools included.
- `locations-seed.json`: dev FCC's `inventory-hub/data/locations.json`, with every printer login left out.

## Why the files aren't in git

Since 2026-11-13 dev's data is a copy of prod's, so the snapshot is a copy of the real inventory
(names, prices, purchase links, comments). The GitHub repo is public, so the two `.json` files stay
on the PC that made them: `.gitignore` leaves them out, and only this README is tracked. Copies
from before 2026-11-13 are still in git history, up to the commit that stopped tracking the files.

A fresh clone, or a PC that never made a snapshot, has none. Until one is made:

- `reset_dev.py` (a restore, a dry run, and `pytest --reset-dev`) stops with a message saying so,
  before it reads or changes anything;
- `tests/test_box_binding_loans.py::test_baselines_match_the_reset_dev_seed` skips, saying why.

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

## What uses it

- `setup-and-rebuild/reset_dev.py`: restores dev to it (`pytest --reset-dev` runs the same restore
  before a sweep).
- `setup-and-rebuild/refresh_dev_from_prod.py`: its `seeds` phase retakes and checks it; its
  `locations` phase reads `locations-seed.json` for a test box or test cart that neither prod's nor
  dev's file has.
- `inventory-hub/tests/test_box_binding_loans.py`: checks that `conftest.DEV_BOX_BINDING_BASELINES`
  matches the test boxes in `locations-seed.json`.

Keep a copy before refreshing dev from prod if you may want the old snapshot back: git no longer has one.
