# Group 54: 🧷 Group 36 Leftovers

**Branch name (when started):** `feature/group-54-group36-leftovers`
**Estimated effort:** SMALL (~3–6 h, 1 session).
**Risk:** **LOW.** All four are dormant on today's data. `setup_fields.py` runs on every prod deploy, but the change sits inside a branch that returns early.

> **Status: `TODO` — filed 2026-10-19 (`/refresh-groups`). No Derek decision needed.** Not in the 48 + 49 + 51 + 52 bundle.
> Four small hardening fixes from Group 36's lineage (the filament-attribute work and its review). Group 36's other follow-up, the retry on the pre-merge extras read, is [Group 52](52-spoolman-read-load.md) 52.2. Every decision: [refresh-2026-10-19.md](refresh-2026-10-19.md).
> Code anchors were read on `dev` @ `c5c5aa6` (the refresh's grounding) and spot-checked at `08c4b10`. Line numbers drift, so re-grep before editing.

## Items covered (quoted from `Feature-Buglist.md`)

| # | Buglist item | Direction |
|---|---|---|
| **54.1** | 🧪 Attribute-suite residual (1), narrowed 2026-10-12: *"A malformed payload still gets a generic answer… That generic message is what hid the `_restore` no-op for months. Reject an unrecognized payload shape loudly instead, naming the missing `data` key."* | 400 naming a missing or non-dict `data`. |
| **54.2** | Residual (2), Derek: *"Highly unlikely in reality, but we should make sure that having that many attributes doesn't break things like it might be doing right now, so we should probably put in some tests for this kind of thing, so that it's supported, even though it might not currently be possible."* | A browser test that renders all 28 chips. |
| **54.3** | 🟡 Group 36 follow-up (2): *"`_parse_filament_attrs_value` collapses a non-JSON string such as 'Silk, Matte' into one pseudo-tag, so real tags can read as zero-usage and therefore sweepable."* | Split a comma list when the string isn't JSON. |
| **54.4** | Follow-up (3): *"`setup-and-rebuild/setup_fields.py` still sends a partial-`extra` spool PATCH (`{"extra": {"container_slot": value}}`), the replace-the-whole-`extra` landmine, inside `migrate_container_slot_to_text`, the function CLAUDE.md names as the template for type migrations (dormant, guarded)."* | Snapshot each spool's whole `extra` and restore it whole. |

## Decisions

- **No Derek decision.**

## Today's code (anchors, `dev` @ `c5c5aa6`)

- **54.1:** `/api/update_filament` reads `data = payload.get('data') or {}` (`routes_scan.py:174`); a missing, empty or non-dict `data` all answer 200 `{success: false, msg: "No fields to update."}` (`:177-178`). Every current caller sends `{id, data}` (`inv_cmd.js:1257`, `inv_details.js:773`, `:912`, `:1539`, `:2535`, `inv_wizard.js:4990`).
- **54.2:** `tests/test_max_attributes_supported.py` covers the backend only (28 choices at `:39-45`). No test renders 28 chips: `renderReadonlyAttributeChips` (`inv_details.js:34`; used by the spool window `:186` and the filament window `:394`) and the wizard's chip container (`inv_wizard.js:1903`; `wizardAddMultiChoiceChip` `:1963`).
- **54.3:** `_parse_filament_attrs_value` returns `[raw]` for a non-JSON string (`spoolman_api.py:1191-1206`, the fallback at `:1204-1205`). It feeds the attribute report (`routes_config_attrs.py:236`) and `sweep_unused` (`:848`), and is also read at `:308`, `:455`, `:562`. Group 49.1's attribute search should use it too.
- **54.4:** `migrate_container_slot_to_text` restores with `{'extra': {'container_slot': value}}` (`setup-and-rebuild/setup_fields.py:242-248`). Dormant: it returns early when `container_slot` is already text (`:204-207`). It runs on every prod deploy (`update.sh:62`, with no `set -e`). `tests/test_setup_fields_idempotent.py` pins the partial shape (`:128`, `:160-165`) and never checks that siblings survive.

## Design, by sub-task

- **54.1:** answer 400 naming a missing or non-dict `data` key; keep today's answer for a present-but-empty `data` (a no-change modal save sends it).
- **54.2:** a browser test on stubbed data (no dev writes) rendering all 28 chips on the spool window, the filament window and the wizard: they wrap, nothing overflows, all are visible. The search half follows Group 49.1.
- **54.3:** split a comma list when the string isn't JSON (none of the 28 choices contains a comma).
- **54.4:** snapshot each spool's whole `extra` and restore it whole (still plain `requests` inside `setup_fields.py`, no Flask import); add a sibling-survival assertion to the test.

## Tests

- As above, each mutation-proven (red on the base).

## Risks

- `setup_fields.py` runs on every prod deploy; the change sits inside the dormant branch.
- A comma split would mis-split a future attribute that contains a comma.
