# Group 54: 🧷 Group 36 Leftovers

**Branch name (when started):** `feature/group-54-group36-leftovers`
**Estimated effort:** SMALL–MEDIUM (~5–9 h, 1 session). 54.1–54.4 ~3–6 h · 54.5 ~1.5–3 h (with its check on dev) · 54.6 ~0.5–1 h.
**Risk:** **LOW–MEDIUM.** 54.1–54.4 are dormant on today's data. `setup_fields.py` runs on every prod deploy, but the change sits inside a branch that returns early. 54.5 changes the wizard's edit-mode save, a live path; 54.6 the archive edge of `update_spool`, a rare path.

> **Status: `TODO` — filed 2026-10-19 (`/refresh-groups`). No Derek decision needed.** Not in the 48 + 49 + 51 + 52 bundle.
> **🔄 2026-10-25 (`/refresh-groups`): gains 54.5 and 54.6**, two small items of the same shape (a clear or an edge that silently doesn't fire), filed 2026-10-21 by the extras-clear fix and 2026-10-19 by the Group 51 review. Still no Derek decision; 54.5 needs a check on dev first.
> Four small hardening fixes from Group 36's lineage (the filament-attribute work and its review). Group 36's other follow-up, the retry on the pre-merge extras read, is [Group 52](52-spoolman-read-load.md) 52.2. Every decision: [refresh-2026-10-19.md](refresh-2026-10-19.md).
> Code anchors were read on `dev` @ `c5c5aa6` (the refresh's grounding) and spot-checked at `08c4b10`. Line numbers drift, so re-grep before editing.

## Items covered (quoted from `Feature-Buglist.md`)

| # | Buglist item | Direction |
|---|---|---|
| **54.1** | 🧪 Attribute-suite residual (1), narrowed 2026-10-12: *"A malformed payload still gets a generic answer… That generic message is what hid the `_restore` no-op for months. Reject an unrecognized payload shape loudly instead, naming the missing `data` key."* | 400 naming a missing or non-dict `data`. |
| **54.2** | Residual (2), Derek: *"Highly unlikely in reality, but we should make sure that having that many attributes doesn't break things like it might be doing right now, so we should probably put in some tests for this kind of thing, so that it's supported, even though it might not currently be possible."* | A browser test that renders all 28 chips. |
| **54.3** | 🟡 Group 36 follow-up (2): *"`_parse_filament_attrs_value` collapses a non-JSON string such as 'Silk, Matte' into one pseudo-tag, so real tags can read as zero-usage and therefore sweepable."* | Split a comma list when the string isn't JSON. |
| **54.4** | Follow-up (3): *"`setup-and-rebuild/setup_fields.py` still sends a partial-`extra` spool PATCH (`{"extra": {"container_slot": value}}`), the replace-the-whole-`extra` landmine, inside `migrate_container_slot_to_text`, the function CLAUDE.md names as the template for type migrations (dormant, guarded)."* | Snapshot each spool's whole `extra` and restore it whole. |
| **54.5** | *"Emptying a plain field in the wizard doesn't clear it (found 2026-10-21 by the extras-clear fix). The wizard drops a native field it reads as empty from its payload (`settings_extruder_temp`, `settings_bed_temp`, price, the spool's and the filament's empty weight), so erasing one and saving keeps the old value. Not an extra, so the sentinel doesn't cover it: an edit-mode clear would send `null` for these (Spoolman takes null for its own optional fields; check each on dev first)."* | In edit mode, send `null` for a native field the user emptied (touched fields only), after checking each field on dev. |
| **54.6** | *"The archive edge doesn't read `remaining_weight` (Group 51 review note, 2026-10-19). Since the review, a `remaining_weight` write (the weigh-out row's fallback when the spool's details can't be read) un-archives a spool weighed back into stock, but weighing one to 0 g that way still doesn't archive it (it never did). Rare path: make `spoolman_api._auto_archive_on_empty` read it too."* | The archive edge reads `remaining_weight` too, as the unarchive edge already does. |

## Decisions

- **No Derek decision.**

## Today's code (anchors, `dev` @ `c5c5aa6`)

- **54.1:** `/api/update_filament` reads `data = payload.get('data') or {}` (`routes_scan.py:174`); a missing, empty or non-dict `data` all answer 200 `{success: false, msg: "No fields to update."}` (`:177-178`). Every current caller sends `{id, data}` (`inv_cmd.js:1257`, `inv_details.js:773`, `:912`, `:1539`, `:2535`, `inv_wizard.js:4990`).
- **54.2:** `tests/test_max_attributes_supported.py` covers the backend only (28 choices at `:39-45`). No test renders 28 chips: `renderReadonlyAttributeChips` (`inv_details.js:34`; used by the spool window `:186` and the filament window `:394`) and the wizard's chip container (`inv_wizard.js:1903`; `wizardAddMultiChoiceChip` `:1963`).
- **54.3:** `_parse_filament_attrs_value` returns `[raw]` for a non-JSON string (`spoolman_api.py:1191-1206`, the fallback at `:1204-1205`). It feeds the attribute report (`routes_config_attrs.py:236`) and `sweep_unused` (`:848`), and is also read at `:308`, `:455`, `:562`. Group 49.1's attribute search should use it too.
- **54.4:** `migrate_container_slot_to_text` restores with `{'extra': {'container_slot': value}}` (`setup-and-rebuild/setup_fields.py:242-248`). Dormant: it returns early when `container_slot` is already text (`:204-207`). It runs on every prod deploy (`update.sh:62`, with no `set -e`). `tests/test_setup_fields_idempotent.py` pins the partial shape (`:128`, `:160-165`) and never checks that siblings survive.
- **54.5 (read on `dev` @ `d4b1ad7`):** the wizard's save builds `null` for an empty field (the spool's empty weight, `inv_wizard.js:3805`; the filament's, `:3862`; the temperatures, `:3866-3867`), then drops every `null` key before sending: the spool payload at `:3843` (null, undefined or NaN), the filament payload at `:3964-3966` (every null except `multi_color_hexes` / `multi_color_direction`). The empty-weight cross-inherit (`:3888-3903`) also fills a null empty weight from the filament or vendor, so an emptied spool empty weight is refilled on purpose: decide per field which clears and which inherits. Extras already clear only for a touched field (`wizardState.touchedExtras`, CLAUDE.md's wizard write-surface row); reuse that idea for native fields.
- **54.6 (read on `dev` @ `d4b1ad7`):** `spoolman_api._auto_archive_on_empty` (`spoolman_api.py:281+`) returns early unless the write carries `used_weight` or `initial_weight` (`:308`) and computes remaining from them (`:310-323`); the unarchive edge, `_auto_unarchive_on_refill` (`:355+`), already reads `remaining_weight` (`:394`). Called from `update_spool` (`:543`).

## Design, by sub-task

- **54.1:** answer 400 naming a missing or non-dict `data` key; keep today's answer for a present-but-empty `data` (a no-change modal save sends it).
- **54.2:** a browser test on stubbed data (no dev writes) rendering all 28 chips on the spool window, the filament window and the wizard: they wrap, nothing overflows, all are visible. The search half follows Group 49.1.
- **54.3:** split a comma list when the string isn't JSON (none of the 28 choices contains a comma).
- **54.4:** snapshot each spool's whole `extra` and restore it whole (still plain `requests` inside `setup_fields.py`, no Flask import); add a sibling-survival assertion to the test.
- **54.5:** first check on dev, with throwaway records deleted afterwards (dev spools are agent fixtures), that Spoolman 0.27 takes `null` for each field: `price`, `spool_weight` (spool and filament), `settings_extruder_temp`, `settings_bed_temp`. Then, in edit mode only, send `null` for such a field the user emptied (a touched-field set like `touchedExtras`); create mode and untouched fields keep today's drop. Check that `api_edit_spool_wizard` and `sanitize_outbound_data` pass a `null` through, and that the edit log says "→ (cleared)". The empty-weight cross-inherit stays for an untouched field.
- **54.6:** in `_auto_archive_on_empty`, treat a write carrying `remaining_weight` (and neither `used_weight` nor `initial_weight`) as a weight write: remaining ≤ 0 archives, with the same pre-archive note and location handling as today's path.

## Tests

- As above, each mutation-proven (red on the base).
- 54.5: a browser test on the edit wizard: empty the bed temperature, save, and the filament reads it empty; an untouched empty field sends nothing; create mode unchanged. Plus an offline test of the payload builder if it can be reached from the node-vm harness.
- 54.6: an offline `update_spool` test on `tests/spoolman_extra_fake.SpoolmanHTTPFake` (or the existing archive-edge harness): `remaining_weight: 0` archives a spool; `remaining_weight: 40` on an archived spool still un-archives it.

## Risks

- `setup_fields.py` runs on every prod deploy; the change sits inside the dormant branch.
- A comma split would mis-split a future attribute that contains a comma.
- 54.5: a field Spoolman refuses as `null` would make the whole PATCH fail; that is why each field is checked on dev first. A clear sent for an untouched field would erase data (the 2026-10-21 ➕ lesson): touched fields only.
- 54.6: archiving also takes the spool off its place (the archive edge's own outcome); the weigh-out's fallback row must say so as the other weigh paths do.
