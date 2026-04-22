# `.githooks/` — tracked git hooks

Git doesn't apply hooks committed into `.git/hooks/` automatically because
that directory isn't under version control. To enable the hooks shipped
here, run once per clone:

```bash
git config core.hooksPath .githooks
```

## `pre-commit`

Rejects commits that would stage runtime-state files:

- `inventory-hub/locations.json` (legacy path — should be under `data/` now)
- `inventory-hub/locations.json.*.bak` (migration backups)
- Anything under `inventory-hub/data/` except `README.md` and
  `locations.json.example`

This is a backstop behind the `.gitignore` rules. Both layers exist because
a single accidental commit of `locations.json` will overwrite prod's real
bindings on the next `git pull`. See
[`inventory-hub/data/README.md`](../inventory-hub/data/README.md) for why.

If you know what you're doing and truly need to commit one of these:

```bash
git commit --no-verify ...
```

…but 99% of the time the answer is "unstage and don't."
